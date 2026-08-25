from __future__ import annotations

from datetime import datetime, timedelta
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import phoenix_disaster_recovery
from phoenix_disaster_recovery import (
    DEFAULT_MAX_RECOVERY_ATTEMPTS,
    EXIT_BLOCKED,
    EXIT_RECOVERY_REQUIRED,
    JST,
    MAX_RECOVERY_ATTEMPTS_HARD_LIMIT,
    MODE,
    ORDERS_SUBMITTED,
    RECOVERY_PHASE_BOOTSTRAP,
    RecoveryRequiredExit,
    RecoverySession,
    STATE_KIND_PHOENIX_RUN,
    STATE_KIND_RECOVERY_DECISION,
    STATUS_BLOCKED,
    STATUS_READY,
    STATUS_RECOVERY_REQUIRED,
    inspect_recovery_state_for_watchdog,
    recover_stale_lock,
    run_disaster_recovery,
)
from phoenix_fail_safe import FailSafeExit
from phoenix_watchdog import (
    EXIT_CONFIGURATION_ERROR,
    EXIT_OK,
    MonitorConfig,
    PhoenixWatchdog,
)


class DisasterRecoveryStep40Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "PHOENIX"
        self.root.mkdir()
        self.state_path = self.root / "runtime" / "guardian" / "recovery_state.json"
        self.log_dir = self.root / "logs"
        self.now = datetime(2026, 8, 3, 9, 0, 0, tzinfo=JST)
        self.commit = "a" * 40
        self.previous_pid = 30940

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "checked_at": (self.now - timedelta(seconds=1)).isoformat(
                timespec="seconds"
            ),
            "previous_run_id": "run-step39",
            "previous_status": "COMPLETED",
            "previous_started_at": (self.now - timedelta(minutes=10)).isoformat(
                timespec="seconds"
            ),
            "previous_finished_at": (self.now - timedelta(minutes=1)).isoformat(
                timespec="seconds"
            ),
            "previous_pid": self.previous_pid,
            "previous_git_commit": self.commit,
            "previous_repository_root": str(self.root),
            "previous_guardian_status": "READY",
            "previous_position_status": "READY",
            "previous_heartbeat_status": "COMPLETED",
            "previous_fail_safe_status": "NOT_TRIGGERED",
            "previous_orders_submitted": 0,
            "previous_mode": "PAPER",
            "recovery_status": "READY",
            "recovery_reasons": [],
            "recovery_attempt": 0,
            "recovered_at": None,
            "exit_code": 0,
        }
        payload.update(overrides)
        return payload

    def write_state(self, **overrides: object) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.payload(**overrides), ensure_ascii=False),
            encoding="utf-8",
        )

    def run_recovery(self, **overrides: object):
        arguments: dict[str, object] = {
            "guardian_status": "READY",
            "position_status": "READY",
            "repository_root": self.root,
            "expected_repository_root": self.root,
            "state_path": self.state_path,
            "report_dir": self.log_dir,
            "current_git_commit": self.commit,
            "now": self.now,
            "pid_checker": lambda pid: False,
        }
        arguments.update(overrides)
        return run_disaster_recovery(**arguments)

    def legacy_uninitialized_payload(self) -> dict[str, object]:
        payload = self.payload()
        for field in (
            "previous_run_id",
            "previous_status",
            "previous_started_at",
            "previous_finished_at",
            "previous_pid",
            "previous_git_commit",
            "previous_repository_root",
            "previous_guardian_status",
            "previous_position_status",
            "previous_position_reasons",
            "previous_operating_scope",
            "previous_trading_actions",
            "previous_heartbeat_status",
            "previous_fail_safe_status",
            "previous_orders_submitted",
            "previous_mode",
        ):
            payload[field] = None
        payload.update(
            {
                "recovery_status": "BLOCKED",
                "recovery_reasons": [
                    "PREVIOUS_STARTED_AT_TIMESTAMP_TYPE_INVALID",
                    "PREVIOUS_RUN_ID_INVALID",
                    "PREVIOUS_STATUS_INVALID",
                    "PREVIOUS_PID_INVALID",
                    "PREVIOUS_GIT_COMMIT_INVALID",
                    "REPOSITORY_ROOT_MISMATCH",
                    "GUARDIAN_NOT_READY",
                    "PREVIOUS_OPERATING_SCOPE_INVALID",
                    "POSITION_NOT_READY",
                    "HEARTBEAT_STATUS_INVALID",
                    "FAIL_SAFE_STATUS_INVALID",
                    "MODE_NOT_PAPER",
                    "ORDERS_SUBMITTED_NOT_ZERO",
                    "PREVIOUS_RECOVERY_BLOCKED",
                ],
                "recovery_attempt": 0,
                "recovered_at": None,
                "exit_code": 2,
            }
        )
        return payload

    def test_missing_state_bootstraps_only_after_current_ready_scope_is_safe(self) -> None:
        result = self.run_recovery()

        self.assertEqual(STATUS_READY, result.recovery_status)
        self.assertEqual(RECOVERY_PHASE_BOOTSTRAP, result.recovery_phase)
        self.assertEqual(STATE_KIND_RECOVERY_DECISION, result.state_kind)
        self.assertEqual(self.commit, result.current_git_commit)
        self.assertEqual(str(self.root), result.current_repository_root)
        self.assertEqual("READY", result.current_guardian_status)
        self.assertEqual("READY", result.current_position_status)
        self.assertEqual("OPERATIONAL", result.current_operating_scope)
        self.assertEqual("PAPER_ONLY", result.current_trading_actions)
        self.assertEqual("PAPER", result.current_mode)
        self.assertEqual(0, result.current_orders_submitted)
        self.assertIsNone(result.previous_run_id)
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        watchdog_gate = inspect_recovery_state_for_watchdog(
            self.state_path,
            expected_repository_root=self.root,
        )
        self.assertEqual(RECOVERY_PHASE_BOOTSTRAP, persisted["recovery_phase"])
        self.assertEqual(STATUS_RECOVERY_REQUIRED, watchdog_gate.status)
        self.assertTrue(watchdog_gate.restart_allowed)

    def test_legacy_self_generated_all_null_blocked_state_bootstraps(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.legacy_uninitialized_payload()),
            encoding="utf-8",
        )

        result = self.run_recovery()

        self.assertEqual(STATUS_READY, result.recovery_status)
        self.assertEqual(RECOVERY_PHASE_BOOTSTRAP, result.recovery_phase)
        self.assertEqual([], result.recovery_reasons)
        self.assertIsNone(result.previous_status)

    def test_partial_null_previous_record_is_blocked_not_bootstrapped(self) -> None:
        self.write_state(previous_run_id=None)

        result = self.run_recovery()

        self.assertEqual(STATUS_BLOCKED, result.recovery_status)
        self.assertIn("PREVIOUS_RUN_ID_INVALID", result.recovery_reasons)
        self.assertNotEqual(RECOVERY_PHASE_BOOTSTRAP, result.recovery_phase)

    def test_bootstrap_current_safety_violations_remain_blocked(self) -> None:
        cases = (
            ({"current_mode": "LIVE"}, "MODE_NOT_PAPER"),
            ({"current_orders_submitted": 1}, "ORDERS_SUBMITTED_NOT_ZERO"),
            (
                {"expected_repository_root": self.root / "other"},
                "REPOSITORY_ROOT_MISMATCH",
            ),
        )
        for arguments, reason in cases:
            with self.subTest(reason=reason):
                result = self.run_recovery(**arguments)
                self.assertEqual(STATUS_BLOCKED, result.recovery_status)
                self.assertEqual(RECOVERY_PHASE_BOOTSTRAP, result.recovery_phase)
                self.assertIn(reason, result.recovery_reasons)

    def test_completed_previous_run_is_ready(self) -> None:
        self.write_state()

        result = self.run_recovery()

        self.assertEqual(STATUS_READY, result.recovery_status)
        self.assertEqual(0, result.exit_code)
        self.assertEqual([], result.recovery_reasons)

    def test_running_previous_run_requires_recovery_and_dead_pid_is_recorded(self) -> None:
        self.write_state(
            previous_status="RUNNING",
            previous_finished_at=None,
            previous_heartbeat_status="RUNNING",
        )

        result = self.run_recovery()

        self.assertEqual(STATUS_RECOVERY_REQUIRED, result.recovery_status)
        self.assertEqual(EXIT_RECOVERY_REQUIRED, result.exit_code)
        self.assertIn("PREVIOUS_STATUS_RUNNING", result.recovery_reasons)
        self.assertIn("PREVIOUS_PID_NOT_RUNNING", result.recovery_reasons)
        self.assertEqual(1, result.recovery_attempt)

        self.write_state(
            previous_status="RUNNING",
            previous_finished_at=None,
            previous_heartbeat_status="RUNNING",
            previous_git_commit="b" * 40,
        )

        mismatched = self.run_recovery()

        self.assertEqual(STATUS_BLOCKED, mismatched.recovery_status)
        self.assertIn("GIT_COMMIT_MISMATCH", mismatched.recovery_reasons)

    def test_failed_previous_run_requires_recovery(self) -> None:
        self.write_state(
            previous_status="FAILED",
            previous_heartbeat_status="FAILED",
        )

        result = self.run_recovery()

        self.assertEqual(STATUS_RECOVERY_REQUIRED, result.recovery_status)
        self.assertIn("PREVIOUS_STATUS_FAILED", result.recovery_reasons)

    def test_interrupted_previous_run_requires_recovery(self) -> None:
        self.write_state(
            previous_status="INTERRUPTED",
            previous_heartbeat_status="STOPPED",
        )

        result = self.run_recovery()

        self.assertEqual(STATUS_RECOVERY_REQUIRED, result.recovery_status)
        self.assertIn("PREVIOUS_STATUS_INTERRUPTED", result.recovery_reasons)

    def test_live_previous_pid_blocks_recovery(self) -> None:
        self.write_state(
            previous_status="RUNNING",
            previous_finished_at=None,
            previous_heartbeat_status="RUNNING",
        )

        result = self.run_recovery(pid_checker=lambda pid: True)

        self.assertEqual(STATUS_BLOCKED, result.recovery_status)
        self.assertIn("PREVIOUS_PID_STILL_RUNNING", result.recovery_reasons)

    def test_second_pass_recovers_matching_stale_lock_and_becomes_ready(self) -> None:
        self.write_state(
            previous_status="RUNNING",
            previous_finished_at=None,
            previous_heartbeat_status="RUNNING",
        )
        first = self.run_recovery()
        lock_path = self.root / "runtime" / "guardian" / "previous_run.lock"
        lock_path.write_text(
            json.dumps({"pid": self.previous_pid, "token": "stale"}),
            encoding="utf-8",
        )

        second = self.run_recovery(
            now=self.now + timedelta(seconds=1),
            stale_lock_path=lock_path,
        )

        self.assertEqual(STATUS_RECOVERY_REQUIRED, first.recovery_status)
        self.assertEqual(STATUS_READY, second.recovery_status)
        self.assertFalse(lock_path.exists())
        self.assertIsNotNone(second.recovered_at)

    def test_guardian_and_position_blocked_fail_closed(self) -> None:
        for field, arguments, expected in (
            (
                "guardian",
                {"guardian_status": "BLOCKED"},
                "GUARDIAN_NOT_READY",
            ),
            (
                "position",
                {"position_status": "BLOCKED"},
                "POSITION_NOT_READY",
            ),
        ):
            with self.subTest(field=field):
                self.write_state()
                result = self.run_recovery(**arguments)
                self.assertEqual(STATUS_BLOCKED, result.recovery_status)
                self.assertIn(expected, result.recovery_reasons)

    def test_fail_safe_activation_is_blocked(self) -> None:
        self.write_state(previous_fail_safe_status="BLOCKED")

        result = self.run_recovery()

        self.assertEqual(STATUS_BLOCKED, result.recovery_status)
        self.assertIn("FAIL_SAFE_TRIGGERED", result.recovery_reasons)

    def test_mode_orders_and_repository_mismatch_are_blocked(self) -> None:
        cases = (
            ({"previous_mode": "LIVE"}, "MODE_NOT_PAPER"),
            ({"previous_orders_submitted": 1}, "ORDERS_SUBMITTED_NOT_ZERO"),
            (
                {"previous_repository_root": str(self.root / "other")},
                "REPOSITORY_ROOT_MISMATCH",
            ),
        )
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                self.write_state(**overrides)
                result = self.run_recovery()
                self.assertEqual(STATUS_BLOCKED, result.recovery_status)
                self.assertIn(reason, result.recovery_reasons)

    def test_corrupt_json_is_blocked_and_cannot_become_bootstrap(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text("{broken", encoding="utf-8")
        first = self.run_recovery()
        second = self.run_recovery()

        self.assertEqual(STATUS_BLOCKED, first.recovery_status)
        self.assertIn("RECOVERY_STATE_JSON_INVALID", first.recovery_reasons)
        self.assertEqual(STATUS_BLOCKED, second.recovery_status)
        self.assertNotEqual(RECOVERY_PHASE_BOOTSTRAP, second.recovery_phase)

    def test_missing_required_field_is_blocked(self) -> None:
        payload = self.payload()
        del payload["previous_mode"]
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")

        result = self.run_recovery()

        self.assertIn("RECOVERY_STATE_REQUIRED_FIELD_MISSING", result.recovery_reasons)

    def test_invalid_types_are_blocked(self) -> None:
        cases = (
            ({"previous_pid": True}, "PREVIOUS_PID_INVALID"),
            ({"recovery_attempt": "1"}, "RECOVERY_ATTEMPT_INVALID"),
            ({"recovery_reasons": "none"}, "RECOVERY_REASONS_INVALID"),
            ({"exit_code": False}, "EXIT_CODE_INVALID"),
        )
        for overrides, reason in cases:
            with self.subTest(reason=reason):
                self.write_state(**overrides)
                result = self.run_recovery()
                self.assertEqual(STATUS_BLOCKED, result.recovery_status)
                self.assertIn(reason, result.recovery_reasons)

    def test_future_timestamp_is_blocked(self) -> None:
        self.write_state(
            checked_at=(self.now + timedelta(seconds=1)).isoformat(
                timespec="seconds"
            )
        )

        result = self.run_recovery()

        self.assertIn("TIMESTAMP_FUTURE", result.recovery_reasons)

    def test_completed_previous_run_with_stale_blocked_state_bootstraps(self) -> None:
        self.write_state(
            previous_git_commit="b" * 40,
            recovery_status="BLOCKED",
        )

        result = self.run_recovery()

        self.assertEqual(STATUS_READY, result.recovery_status)
        self.assertEqual([], result.recovery_reasons)

    def test_recovery_attempt_limits_are_bounded(self) -> None:
        self.write_state(
            previous_status="RUNNING",
            previous_finished_at=None,
            previous_heartbeat_status="RUNNING",
            recovery_status="RECOVERY_REQUIRED",
            recovery_attempt=DEFAULT_MAX_RECOVERY_ATTEMPTS,
        )

        result = self.run_recovery()

        self.assertEqual(STATUS_BLOCKED, result.recovery_status)
        self.assertIn("RECOVERY_ATTEMPT_LIMIT_EXCEEDED", result.recovery_reasons)
        self.assertEqual(10, MAX_RECOVERY_ATTEMPTS_HARD_LIMIT)

    def test_atomic_state_and_logs_include_jst_and_required_fields(self) -> None:
        self.write_state()

        with mock.patch(
            "phoenix_disaster_recovery.os.replace", wraps=os.replace
        ) as replace:
            result = self.run_recovery()

        self.assertEqual(3, replace.call_count)
        self.assertEqual([], list(self.root.rglob("*.tmp")))
        self.assertTrue(result.checked_at.endswith("+09:00"))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(result.as_dict(), state)
        self.assertTrue((self.log_dir / "disaster_recovery.json").is_file())
        self.assertTrue((self.log_dir / "disaster_recovery.txt").is_file())

    def test_recovery_session_tracks_running_and_completed_paper_state(self) -> None:
        session = RecoverySession(
            state_path=self.state_path,
            repository_root=self.root,
            git_commit=self.commit,
            guardian_status="READY",
            position_status="READY",
            now_provider=lambda: self.now,
            pid=self.previous_pid,
            run_id="current-run",
        )
        session.start()
        running = json.loads(self.state_path.read_text(encoding="utf-8"))

        session.finish(
            status="COMPLETED",
            heartbeat_status="COMPLETED",
            fail_safe_status="NOT_TRIGGERED",
        )
        completed = json.loads(self.state_path.read_text(encoding="utf-8"))

        self.assertEqual("RUNNING", running["previous_status"])
        self.assertEqual(STATE_KIND_PHOENIX_RUN, running["state_kind"])
        self.assertEqual("COMPLETED", completed["previous_status"])
        self.assertEqual("READY", completed["recovery_status"])
        self.assertEqual("PAPER", completed["previous_mode"])
        self.assertEqual(0, completed["previous_orders_submitted"])

    def test_recovery_session_fail_safe_finish_is_blocked(self) -> None:
        session = RecoverySession(
            state_path=self.state_path,
            repository_root=self.root,
            git_commit=self.commit,
            guardian_status="READY",
            position_status="READY",
            now_provider=lambda: self.now,
        )
        session.start()
        session.finish(
            status="FAILED",
            heartbeat_status="FAILED",
            fail_safe_status="BLOCKED",
        )

        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("BLOCKED", payload["recovery_status"])
        self.assertEqual(2, payload["exit_code"])

    def test_watchdog_gate_allows_recovery_required_but_blocks_safety_violation(self) -> None:
        self.write_state(
            previous_status="RUNNING",
            previous_finished_at=None,
            previous_heartbeat_status="RUNNING",
            recovery_status="RECOVERY_REQUIRED",
            recovery_attempt=1,
            exit_code=1,
        )
        allowed = inspect_recovery_state_for_watchdog(
            self.state_path,
            expected_repository_root=self.root,
        )
        self.write_state(previous_mode="LIVE")
        blocked = inspect_recovery_state_for_watchdog(
            self.state_path,
            expected_repository_root=self.root,
        )

        self.assertTrue(allowed.restart_allowed)
        self.assertEqual(STATUS_RECOVERY_REQUIRED, allowed.status)
        self.assertFalse(blocked.restart_allowed)
        self.assertEqual(STATUS_BLOCKED, blocked.status)

    def test_stale_lock_recovery_rejects_active_or_mismatched_pid(self) -> None:
        lock_path = self.root / "stale.lock"
        lock_path.write_text(json.dumps({"pid": self.previous_pid}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "STALE_LOCK_PROCESS_ACTIVE"):
            recover_stale_lock(
                lock_path,
                previous_pid=self.previous_pid,
                pid_checker=lambda pid: True,
            )
        self.assertTrue(lock_path.exists())


class RunPhoenixDisasterRecoveryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.run_phoenix = importlib.import_module("run_phoenix")

    def setUp(self) -> None:
        self.events: list[str] = []

    def tearDown(self) -> None:
        self.run_phoenix._ACTIVE_RECOVERY_SESSION = None
        self.run_phoenix._ACTIVE_FAIL_SAFE = None
        self.run_phoenix._ACTIVE_HEARTBEAT = None

    def test_integration_order_is_guardian_position_recovery_heartbeat_fail_safe(self) -> None:
        events = self.events
        guardian = mock.Mock(ready=True, status="READY", reasons=(), report_error=None)
        position = mock.Mock(
            status="READY",
            reasons=(),
            report_error=None,
            mode="PAPER",
            orders_submitted=0,
        )
        recovery = mock.Mock(
            blocked=False,
            recovery_required=False,
            recovery_status="READY",
            recovery_reasons=[],
            state_path="recovery.json",
            previous_git_commit="a" * 40,
            current_git_commit="a" * 40,
            recovery_attempt=0,
            recovered_at=None,
        )

        class FakeFailSafe:
            triggered = False

            def __init__(self, **kwargs: object) -> None:
                pass

            def update_statuses(self, **kwargs: object) -> None:
                pass

            def register_background_stopper(self, *args: object) -> None:
                pass

            def start_monitoring(self, **kwargs: object) -> None:
                events.append("fail_safe")

            def raise_if_triggered(self) -> None:
                pass

        class FakeSession:
            def __init__(self, **kwargs: object) -> None:
                pass

            def start(self) -> None:
                events.append("recovery_session")

        class FakeHeartbeat:
            heartbeat_path = "heartbeat.json"
            pid = 1234

            def __init__(self, **kwargs: object) -> None:
                pass

            def start(self, **kwargs: object) -> None:
                events.append("heartbeat")

            def set_stage(self, value: str) -> None:
                pass

            def stop(self, **kwargs: object) -> None:
                pass

        def initialize() -> None:
            events.append("existing")
            raise RuntimeError("stop after startup order")

        with (
            mock.patch.object(self.run_phoenix, "FailSafeController", FakeFailSafe),
            mock.patch.object(self.run_phoenix, "RecoverySession", FakeSession),
            mock.patch.object(self.run_phoenix, "PhoenixHeartbeat", FakeHeartbeat),
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(
                self.run_phoenix,
                "run_repository_guardian",
                side_effect=lambda **kwargs: events.append("guardian") or guardian,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_position_reconciliation",
                side_effect=lambda **kwargs: events.append("position") or position,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_disaster_recovery",
                side_effect=lambda **kwargs: events.append("recovery") or recovery,
            ),
            mock.patch.object(self.run_phoenix, "initialize_directories", side_effect=initialize),
            mock.patch.dict(os.environ, {"PHOENIX_WATCHDOG_RESTART_ATTEMPT": "0"}),
            mock.patch("builtins.print"),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop after startup order"):
                self.run_phoenix._run_main()

        self.assertEqual(
            [
                "guardian",
                "position",
                "recovery",
                "recovery_session",
                "heartbeat",
                "fail_safe",
                "existing",
            ],
            events,
        )

    def test_recovery_required_stops_before_heartbeat_and_existing_processing(self) -> None:
        guardian = mock.Mock(ready=True, status="READY", reasons=(), report_error=None)
        position = mock.Mock(
            status="READY",
            reasons=(),
            report_error=None,
            mode="PAPER",
            orders_submitted=0,
        )
        recovery = mock.Mock(
            blocked=False,
            recovery_required=True,
            recovery_reasons=["PREVIOUS_STATUS_RUNNING"],
        )
        with (
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(self.run_phoenix, "run_repository_guardian", return_value=guardian),
            mock.patch.object(self.run_phoenix, "run_position_reconciliation", return_value=position),
            mock.patch.object(self.run_phoenix, "run_disaster_recovery", return_value=recovery),
            mock.patch.object(self.run_phoenix, "PhoenixHeartbeat") as heartbeat,
            mock.patch.object(self.run_phoenix, "initialize_directories") as initialize,
            mock.patch("builtins.print"),
        ):
            with self.assertRaises(RecoveryRequiredExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(1, stopped.exception.code)
        heartbeat.assert_not_called()
        initialize.assert_not_called()

    def test_recovery_blocked_exits_two(self) -> None:
        guardian = mock.Mock(ready=True, status="READY", reasons=(), report_error=None)
        position = mock.Mock(
            status="READY",
            reasons=(),
            report_error=None,
            mode="PAPER",
            orders_submitted=0,
        )
        recovery = mock.Mock(
            blocked=True,
            recovery_required=False,
            recovery_reasons=["GIT_COMMIT_MISMATCH"],
        )

        class BlockingFailSafe:
            def __init__(self, **kwargs: object) -> None:
                pass

            def update_statuses(self, **kwargs: object) -> None:
                pass

            def stop_monitoring(self) -> None:
                pass

            def fail_and_exit(self, reason: str, **kwargs: object) -> None:
                raise FailSafeExit(reason)

        with (
            mock.patch.object(self.run_phoenix, "FailSafeController", BlockingFailSafe),
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(self.run_phoenix, "run_repository_guardian", return_value=guardian),
            mock.patch.object(self.run_phoenix, "run_position_reconciliation", return_value=position),
            mock.patch.object(self.run_phoenix, "run_disaster_recovery", return_value=recovery),
            mock.patch("builtins.print"),
        ):
            with self.assertRaises(FailSafeExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(EXIT_BLOCKED, stopped.exception.code)


class WatchdogDisasterRecoveryIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.log_dir = self.root / "logs"
        self.lock_file = self.log_dir / "phoenix_watchdog.lock"
        self.state_path = self.root / "runtime" / "guardian" / "recovery_state.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def make_watchdog(self, target: Path, max_restarts: int) -> PhoenixWatchdog:
        return PhoenixWatchdog(
            target_script=target,
            root_dir=self.root,
            log_dir=self.log_dir,
            lock_file=self.lock_file,
            recovery_state_path=self.state_path,
            config=MonitorConfig(
                max_restarts=max_restarts,
                backoff_base_seconds=0.0,
                backoff_max_seconds=0.0,
                startup_grace_seconds=0.0,
                poll_seconds=0.005,
                termination_grace_seconds=1.0,
                stale_lock_seconds=1.0,
                heartbeat_timeout_seconds=0.2,
            ),
        )

    def wait_for_watchdog_event(
        self,
        event_name: str,
        *,
        timeout: float = 3.0,
    ) -> list[dict[str, object]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            files = list(self.log_dir.glob("phoenix_watchdog_*.jsonl"))
            if files:
                path = files[0]
                events = [
                    json.loads(line)
                    for line in path.read_text(encoding="utf-8").splitlines()
                ]
                if any(event["event"] == event_name for event in events):
                    return events
            time.sleep(0.01)
        self.fail(f"timed out waiting for {event_name}")

    def recovery_payload(self, *, status: str = "RECOVERY_REQUIRED") -> dict[str, object]:
        now = datetime.now(JST)
        return {
            "schema_version": 1,
            "checked_at": now.isoformat(timespec="seconds"),
            "previous_run_id": "watchdog-run",
            "previous_status": "RUNNING" if status == "RECOVERY_REQUIRED" else "COMPLETED",
            "previous_started_at": now.isoformat(timespec="seconds"),
            "previous_finished_at": None if status == "RECOVERY_REQUIRED" else now.isoformat(timespec="seconds"),
            "previous_pid": 999999999,
            "previous_git_commit": "a" * 40,
            "previous_repository_root": str(self.root),
            "previous_guardian_status": "READY",
            "previous_position_status": "READY",
            "previous_heartbeat_status": "RUNNING" if status == "RECOVERY_REQUIRED" else "COMPLETED",
            "previous_fail_safe_status": "NOT_TRIGGERED",
            "previous_orders_submitted": 0,
            "previous_mode": "PAPER",
            "recovery_status": status,
            "recovery_reasons": [],
            "recovery_attempt": 1 if status == "RECOVERY_REQUIRED" else 0,
            "recovered_at": None,
            "exit_code": 1 if status == "RECOVERY_REQUIRED" else 0,
        }

    def test_watchdog_restarts_only_when_recovery_state_allows(self) -> None:
        counter = self.root / "count.txt"
        target = self.root / "run_phoenix.py"
        target.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            f"p=Path({str(counter)!r})\n"
            "n=int(p.read_text()) if p.exists() else 0\n"
            "p.write_text(str(n+1))\n"
            "sys.exit(1 if n == 0 else 0)\n",
            encoding="utf-8",
        )
        self.state_path.parent.mkdir(parents=True)
        self.state_path.write_text(
            json.dumps(self.recovery_payload()), encoding="utf-8"
        )
        watchdog = self.make_watchdog(target, max_restarts=2)
        results: list[int] = []
        thread = threading.Thread(target=lambda: results.append(watchdog.run()))
        thread.start()

        events = self.wait_for_watchdog_event("PROCESS_IDLE")
        self.assertIsNone(watchdog.child_pid)
        self.assertTrue(thread.is_alive())

        watchdog.request_stop("unit_test")
        thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual([EXIT_OK], results)
        self.assertEqual("2", counter.read_text(encoding="utf-8"))
        self.assertIn("PROCESS_EXITED", [event["event"] for event in events])
        self.assertIn("PROCESS_IDLE", [event["event"] for event in events])

    def test_disaster_recovery_exit_two_is_not_retried(self) -> None:
        counter = self.root / "count.txt"
        target = self.root / "run_phoenix.py"
        target.write_text(
            "from pathlib import Path\n"
            "import sys\n"
            f"p=Path({str(counter)!r})\n"
            "n=int(p.read_text()) if p.exists() else 0\n"
            "p.write_text(str(n+1))\n"
            "sys.exit(2)\n",
            encoding="utf-8",
        )

        result = self.make_watchdog(target, max_restarts=3).run()

        self.assertEqual(EXIT_CONFIGURATION_ERROR, result)
        self.assertEqual("1", counter.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
