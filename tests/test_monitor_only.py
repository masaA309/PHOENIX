from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import run_phoenix
from phoenix_disaster_recovery import (
    MONITOR_ONLY_SCOPE,
    RECOVERY_PHASE_BOOTSTRAP,
    RecoverySession,
    STATUS_BLOCKED,
    STATUS_READY,
    inspect_recovery_state_for_watchdog,
    run_disaster_recovery,
)
from phoenix_fail_safe import FailSafeController, FailSafeExit
from phoenix_heartbeat import (
    HeartbeatError,
    PhoenixHeartbeat,
    TRADING_ACTIONS_DISABLED,
    inspect_heartbeat,
)


JST = timezone(timedelta(hours=9), name="JST")


def monitor_result(**overrides: object) -> SimpleNamespace:
    checked = datetime(2026, 8, 3, 9, 0, 0, tzinfo=JST)
    values: dict[str, object] = {
        "checked_at": checked.isoformat(timespec="seconds"),
        "status": "WARNING",
        "reasons": ("POSITIONS_PRESENT",),
        "mode": "PAPER",
        "positions_count": 4,
        "orders_submitted": 0,
        "guardian_status": "READY",
        "source_timestamp": (checked - timedelta(minutes=1)).isoformat(
            timespec="seconds"
        ),
        "exit_code": 0,
        "report_error": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class MonitorOnlyGateTest(unittest.TestCase):
    def tearDown(self) -> None:
        run_phoenix._ACTIVE_RECOVERY_SESSION = None
        run_phoenix._ACTIVE_FAIL_SAFE = None
        run_phoenix._ACTIVE_HEARTBEAT = None

    def test_exact_warning_positions_present_state_is_monitor_only(self) -> None:
        self.assertTrue(
            run_phoenix._is_monitor_only_reconciliation(
                monitor_result(),
                guardian_status="READY",
            )
        )

    def test_stale_paper_warning_state_is_monitor_only(self) -> None:
        checked = datetime(2026, 8, 3, 9, 0, 0, tzinfo=JST)
        self.assertTrue(
            run_phoenix._is_monitor_only_reconciliation(
                monitor_result(
                    source_timestamp=(
                        checked - timedelta(hours=25)
                    ).isoformat(timespec="seconds")
                ),
                guardian_status="READY",
            )
        )

    def test_every_monitor_only_safety_condition_fails_closed(self) -> None:
        checked = datetime(2026, 8, 3, 9, 0, 0, tzinfo=JST)
        invalid_cases = {
            "other warning": {"reasons": ("SOURCE_STATE_STALE",)},
            "multiple reasons": {
                "reasons": ("POSITIONS_PRESENT", "SOURCE_STATE_STALE")
            },
            "blocked": {"status": "BLOCKED"},
            "non paper": {"mode": "LIVE"},
            "orders nonzero": {"orders_submitted": 1},
            "orders bool": {"orders_submitted": False},
            "positions zero": {"positions_count": 0},
            "guardian result blocked": {"guardian_status": "BLOCKED"},
            "report error": {"report_error": "write failed"},
            "nonzero exit": {"exit_code": 2},
            "missing source time": {"source_timestamp": None},
            "future source time": {
                "source_timestamp": (checked + timedelta(seconds=1)).isoformat()
            },
            "live stale source time": {
                "mode": "LIVE",
                "source_timestamp": (checked - timedelta(hours=25)).isoformat()
            },
        }
        for name, overrides in invalid_cases.items():
            with self.subTest(name=name):
                self.assertFalse(
                    run_phoenix._is_monitor_only_reconciliation(
                        monitor_result(**overrides),
                        guardian_status="READY",
                    )
                )
        self.assertFalse(
            run_phoenix._is_monitor_only_reconciliation(
                monitor_result(),
                guardian_status="BLOCKED",
            )
        )

    def test_monitor_only_environment_and_script_allowlist_disable_trading(self) -> None:
        environment = run_phoenix.build_environment(monitor_only=True)
        self.assertEqual("MONITOR_ONLY", environment["PHOENIX_OPERATING_SCOPE"])
        self.assertEqual("DISABLED", environment["PHOENIX_TRADING_ACTIONS"])
        self.assertEqual(
            {
                "market_risk_ai.py",
                "price_monitor.py",
                "get_nikkei225.py",
                "daily_report.py",
                "learning_engine.py",
                "ai_judgement.py",
                "trade_engine.py",
                "order_manager.py",
                "vba_bridge.py",
                "ranking_ai.py",
                "chart_generator.py",
                "notify.py",
            },
            set(run_phoenix.MONITOR_ONLY_ALLOWED_SCRIPTS),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                mock.patch.object(run_phoenix, "ROOT_DIR", root),
                mock.patch.object(run_phoenix, "LOG_DIR", root / "logs"),
                mock.patch.object(run_phoenix, "LOG_FILE", root / "logs" / "run.log"),
                mock.patch.object(run_phoenix.subprocess, "run") as subprocess_run,
            ):
                result = run_phoenix.run_script(
                    "Order submission",
                    "phoenix.py",
                    True,
                    monitor_only=True,
                )

        self.assertFalse(result[0])
        self.assertEqual(-20, result[2])
        subprocess_run.assert_not_called()

    def test_invalid_warning_exits_two_before_disaster_recovery(self) -> None:
        guardian = SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
        )
        position = monitor_result(reasons=("SOURCE_STATE_STALE",))

        class BlockingFailSafe:
            def __init__(self, **kwargs: object) -> None:
                pass

            def update_statuses(self, **kwargs: object) -> None:
                pass

            def fail_and_exit(self, reason: str, **kwargs: object) -> None:
                raise FailSafeExit(reason)

        with (
            mock.patch.object(run_phoenix, "FailSafeController", BlockingFailSafe),
            mock.patch.object(run_phoenix, "configure_console"),
            mock.patch.object(
                run_phoenix, "run_repository_guardian", return_value=guardian
            ),
            mock.patch.object(
                run_phoenix, "run_position_reconciliation", return_value=position
            ),
            mock.patch.object(run_phoenix, "run_disaster_recovery") as recovery,
            mock.patch("builtins.print"),
        ):
            with self.assertRaises(FailSafeExit) as stopped:
                run_phoenix._run_main()

        self.assertEqual(2, stopped.exception.code)
        recovery.assert_not_called()


class RunPhoenixMonitorOnlyIntegrationTest(unittest.TestCase):
    def tearDown(self) -> None:
        run_phoenix._ACTIVE_RECOVERY_SESSION = None
        run_phoenix._ACTIVE_FAIL_SAFE = None
        run_phoenix._ACTIVE_HEARTBEAT = None

    def test_monitor_only_reaches_existing_processing_without_operational_ready(self) -> None:
        events: list[str] = []
        constructor_arguments: dict[str, dict[str, object]] = {}
        guardian = SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
        )
        position = monitor_result()
        recovery = SimpleNamespace(
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

        class ReachedExistingProcessing(RuntimeError):
            pass

        class FakeFailSafe:
            triggered = False

            def __init__(self, **kwargs: object) -> None:
                events.append("fail_safe_created")

            def update_statuses(self, **kwargs: object) -> None:
                pass

            def enable_monitor_only(self) -> None:
                events.append("monitor_only_enabled")

            def register_background_stopper(self, *args: object) -> None:
                pass

            def start_monitoring(self, **kwargs: object) -> None:
                events.append("fail_safe_monitoring")

            def raise_if_triggered(self) -> None:
                pass

        class FakeRecoverySession:
            def __init__(self, **kwargs: object) -> None:
                constructor_arguments["session"] = kwargs

            def start(self) -> None:
                events.append("recovery_session")

        class FakeHeartbeat:
            heartbeat_path = "heartbeat.json"
            pid = 1234

            def __init__(self, **kwargs: object) -> None:
                constructor_arguments["heartbeat"] = kwargs

            def start(self, **kwargs: object) -> None:
                constructor_arguments["heartbeat_start"] = kwargs
                events.append("heartbeat")

            def set_stage(self, stage: str) -> None:
                pass

            def stop(self, **kwargs: object) -> None:
                pass

        def recovery_gate(**kwargs: object) -> SimpleNamespace:
            constructor_arguments["recovery"] = kwargs
            return recovery

        def initialize() -> None:
            events.append("existing_processing")
            raise ReachedExistingProcessing("reached")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                mock.patch.object(run_phoenix, "ROOT_DIR", root),
                mock.patch.object(run_phoenix, "LOG_DIR", root / "logs"),
                mock.patch.object(run_phoenix, "FailSafeController", FakeFailSafe),
                mock.patch.object(run_phoenix, "RecoverySession", FakeRecoverySession),
                mock.patch.object(run_phoenix, "PhoenixHeartbeat", FakeHeartbeat),
                mock.patch.object(run_phoenix, "configure_console"),
                mock.patch.object(
                    run_phoenix, "run_repository_guardian", return_value=guardian
                ),
                mock.patch.object(
                    run_phoenix, "run_position_reconciliation", return_value=position
                ),
                mock.patch.object(
                    run_phoenix, "run_disaster_recovery", side_effect=recovery_gate
                ),
                mock.patch.object(
                    run_phoenix, "initialize_directories", side_effect=initialize
                ),
                mock.patch.dict(
                    os.environ,
                    {"PHOENIX_WATCHDOG_RESTART_ATTEMPT": "0"},
                ),
                mock.patch("builtins.print") as printer,
            ):
                with self.assertRaises(ReachedExistingProcessing):
                    run_phoenix._run_main()

        self.assertIn("monitor_only_enabled", events)
        self.assertIn("existing_processing", events)
        self.assertTrue(constructor_arguments["recovery"]["monitor_only"])
        self.assertEqual(
            ("POSITIONS_PRESENT",),
            constructor_arguments["recovery"]["position_reasons"],
        )
        self.assertTrue(constructor_arguments["session"]["monitor_only"])
        self.assertTrue(constructor_arguments["heartbeat"]["monitor_only"])
        self.assertEqual(
            {"current_stage": "MONITOR_ONLY"},
            constructor_arguments["heartbeat_start"],
        )
        printed = [call.args[0] for call in printer.call_args_list if call.args]
        self.assertIn("PHOENIX MONITOR ONLY", printed)
        self.assertIn("Mode: PAPER", printed)
        self.assertIn("Orders submitted: 0", printed)
        self.assertIn("Trading actions: DISABLED", printed)
        self.assertNotIn("PHOENIX OPERATIONAL READY", printed)


class MonitorOnlyHeartbeatAndFailSafeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.heartbeat_path = self.root / "runtime" / "guardian" / "heartbeat.json"
        self.log_dir = self.root / "logs"
        self.now = datetime(2026, 8, 3, 9, 0, 0, tzinfo=JST)
        self.pid = 30941

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def heartbeat(self, **overrides: object) -> PhoenixHeartbeat:
        arguments: dict[str, object] = {
            "repository_root": self.root,
            "guardian_status": "READY",
            "position_reconciliation_status": "WARNING",
            "position_reconciliation_reasons": ("POSITIONS_PRESENT",),
            "monitor_only": True,
            "heartbeat_path": self.heartbeat_path,
            "log_dir": self.log_dir,
            "interval_seconds": 60.0,
            "pid": self.pid,
            "process_name": "run_phoenix.py",
            "git_commit": "a" * 40,
            "now_provider": lambda: self.now,
        }
        arguments.update(overrides)
        return PhoenixHeartbeat(**arguments)

    def test_monitor_only_heartbeat_is_auditable_and_healthy(self) -> None:
        heartbeat = self.heartbeat()
        heartbeat.start(current_stage="MONITOR_ONLY")
        try:
            payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
            validation = inspect_heartbeat(
                self.heartbeat_path,
                expected_pid=self.pid,
                expected_repository_root=self.root,
                expected_operating_scope=MONITOR_ONLY_SCOPE,
                now=self.now,
            )
        finally:
            heartbeat.stop("COMPLETED", "COMPLETED")

        self.assertTrue(validation.healthy)
        self.assertEqual("MONITOR_ONLY", payload["operating_scope"])
        self.assertEqual("DISABLED", payload["trading_actions"])
        self.assertEqual("WARNING", payload["position_reconciliation_status"])
        self.assertEqual(
            ["POSITIONS_PRESENT"],
            payload["position_reconciliation_reasons"],
        )
        self.assertEqual(0, payload["orders_submitted"])

    def test_heartbeat_rejects_any_other_warning_reason(self) -> None:
        heartbeat = self.heartbeat(
            position_reconciliation_reasons=("SOURCE_STATE_STALE",)
        )
        with self.assertRaises(HeartbeatError):
            heartbeat.start(current_stage="MONITOR_ONLY")

    def test_fail_safe_accepts_only_matching_monitor_only_heartbeat(self) -> None:
        heartbeat = self.heartbeat()
        heartbeat.start(current_stage="MONITOR_ONLY")
        controller = FailSafeController(
            repository_root=self.root,
            log_dir=self.log_dir,
            monitor_interval_seconds=60.0,
            now_provider=lambda: self.now,
        )
        controller.enable_monitor_only()
        controller.update_statuses(
            guardian_status="READY",
            position_status="WARNING",
        )
        controller.start_monitoring(
            heartbeat_path=self.heartbeat_path,
            expected_pid=self.pid,
        )
        try:
            self.assertFalse(controller.triggered)
            self.assertEqual(MONITOR_ONLY_SCOPE, controller.operating_scope)
            self.assertEqual(TRADING_ACTIONS_DISABLED, controller.trading_actions)
        finally:
            controller.stop_monitoring()
            heartbeat.stop("COMPLETED", "COMPLETED")

    def test_warning_without_monitor_only_triggers_fail_safe(self) -> None:
        controller = FailSafeController(
            repository_root=self.root,
            log_dir=self.log_dir,
        )
        controller.update_statuses(
            guardian_status="READY",
            position_status="WARNING",
        )

        self.assertFalse(controller.check_once())
        self.assertEqual("POSITION_BLOCKED", controller.result.reason)


class MonitorOnlyDisasterRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "runtime" / "guardian" / "recovery_state.json"
        self.log_dir = self.root / "logs"
        self.now = datetime(2026, 8, 3, 9, 0, 0, tzinfo=JST)
        self.commit = "a" * 40

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def recovery_payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "checked_at": (self.now - timedelta(seconds=1)).isoformat(),
            "previous_run_id": "monitor-only-run",
            "previous_status": "COMPLETED",
            "previous_started_at": (self.now - timedelta(minutes=10)).isoformat(),
            "previous_finished_at": (self.now - timedelta(minutes=1)).isoformat(),
            "previous_pid": 30942,
            "previous_git_commit": self.commit,
            "previous_repository_root": str(self.root),
            "previous_guardian_status": "READY",
            "previous_position_status": "WARNING",
            "previous_position_reasons": ["POSITIONS_PRESENT"],
            "previous_operating_scope": "MONITOR_ONLY",
            "previous_trading_actions": "DISABLED",
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
            json.dumps(self.recovery_payload(**overrides)),
            encoding="utf-8",
        )

    def run_recovery(self, **overrides: object):
        arguments: dict[str, object] = {
            "guardian_status": "READY",
            "position_status": "WARNING",
            "position_reasons": ("POSITIONS_PRESENT",),
            "monitor_only": True,
            "repository_root": self.root,
            "state_path": self.state_path,
            "report_dir": self.log_dir,
            "current_git_commit": self.commit,
            "now": self.now,
            "pid_checker": lambda pid: False,
        }
        arguments.update(overrides)
        return run_disaster_recovery(**arguments)

    def test_monitor_only_previous_state_is_ready_for_recovery_and_watchdog(self) -> None:
        bootstrap = self.run_recovery()

        self.assertEqual(STATUS_READY, bootstrap.recovery_status)
        self.assertEqual(RECOVERY_PHASE_BOOTSTRAP, bootstrap.recovery_phase)
        self.assertEqual("MONITOR_ONLY", bootstrap.current_operating_scope)
        self.assertEqual("DISABLED", bootstrap.current_trading_actions)
        self.assertEqual(["POSITIONS_PRESENT"], bootstrap.current_position_reasons)
        self.assertEqual("PAPER", bootstrap.current_mode)
        self.assertEqual(0, bootstrap.current_orders_submitted)

        self.write_state()

        result = self.run_recovery()
        watchdog_gate = inspect_recovery_state_for_watchdog(
            self.state_path,
            expected_repository_root=self.root,
        )

        self.assertEqual(STATUS_READY, result.recovery_status)
        self.assertEqual(STATUS_READY, watchdog_gate.status)
        self.assertEqual(0, result.previous_orders_submitted)

    def test_disaster_recovery_rejects_other_warning_and_non_paper_state(self) -> None:
        self.write_state()
        other_warning = self.run_recovery(
            position_reasons=("SOURCE_STATE_STALE",)
        )
        self.assertEqual(STATUS_BLOCKED, other_warning.recovery_status)

        self.write_state(previous_mode="LIVE")
        non_paper = self.run_recovery()
        self.assertEqual(STATUS_BLOCKED, non_paper.recovery_status)
        self.assertIn("MODE_NOT_PAPER", non_paper.recovery_reasons)

    def test_recovery_session_records_monitor_only_safety_fields(self) -> None:
        session = RecoverySession(
            state_path=self.state_path,
            repository_root=self.root,
            git_commit=self.commit,
            guardian_status="READY",
            position_status="WARNING",
            position_reasons=("POSITIONS_PRESENT",),
            monitor_only=True,
            now_provider=lambda: self.now,
            pid=30943,
            run_id="current-monitor-only",
        )
        session.start()

        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual("MONITOR_ONLY", payload["previous_operating_scope"])
        self.assertEqual("DISABLED", payload["previous_trading_actions"])
        self.assertEqual(["POSITIONS_PRESENT"], payload["previous_position_reasons"])
        self.assertEqual("PAPER", payload["previous_mode"])
        self.assertEqual(0, payload["previous_orders_submitted"])


if __name__ == "__main__":
    unittest.main()
