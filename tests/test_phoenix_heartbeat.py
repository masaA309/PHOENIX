from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest import mock

from phoenix_heartbeat import (
    HEARTBEAT_INTERVAL_SECONDS,
    HEARTBEAT_TIMEOUT_SECONDS,
    JST,
    MODE,
    ORDERS_SUBMITTED,
    HeartbeatEventLogger,
    PhoenixHeartbeat,
    _atomic_write,
    inspect_heartbeat,
)
from phoenix_watchdog import (
    EXIT_CONFIGURATION_ERROR,
    EXIT_OK,
    EXIT_RESTART_LIMIT,
    MonitorConfig,
    PhoenixWatchdog,
)


class PhoenixHeartbeatStep38Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.heartbeat_path = self.root / "runtime" / "guardian" / "heartbeat.json"
        self.log_dir = self.root / "logs"
        self.now = datetime(2026, 8, 3, 9, 0, tzinfo=JST)
        self.pid = 43210
        self.payload = {
            "schema_version": 1,
            "timestamp": self.now.isoformat(),
            "started_at": (self.now - timedelta(minutes=1)).isoformat(),
            "status": "RUNNING",
            "mode": "PAPER",
            "pid": self.pid,
            "process_name": "run_phoenix.py",
            "repository_root": str(self.root.resolve()),
            "git_commit": "b1e5a4c",
            "guardian_status": "READY",
            "position_reconciliation_status": "READY",
            "current_stage": "TEST_STAGE",
            "sequence": 1,
            "orders_submitted": 0,
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_payload(self, payload: dict | None = None) -> None:
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path.write_text(
            json.dumps(self.payload if payload is None else payload),
            encoding="utf-8",
        )

    def inspect(self, **overrides):
        arguments = {
            "expected_pid": self.pid,
            "expected_repository_root": self.root,
            "now": self.now,
            "timeout_seconds": HEARTBEAT_TIMEOUT_SECONDS,
        }
        arguments.update(overrides)
        return inspect_heartbeat(self.heartbeat_path, **arguments)

    def make_heartbeat(self, **overrides) -> PhoenixHeartbeat:
        arguments = {
            "repository_root": self.root,
            "guardian_status": "READY",
            "position_reconciliation_status": "READY",
            "heartbeat_path": self.heartbeat_path,
            "log_dir": self.log_dir,
            "interval_seconds": 0.01,
            "pid": self.pid,
            "process_name": "run_phoenix.py",
            "git_commit": "b1e5a4c",
            "now_provider": lambda: self.now,
        }
        arguments.update(overrides)
        return PhoenixHeartbeat(**arguments)

    def test_initial_heartbeat_contains_required_paper_fields_and_jst(self) -> None:
        heartbeat = self.make_heartbeat()
        heartbeat.start(current_stage="OPERATIONAL_READY")
        try:
            payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
        finally:
            heartbeat.stop("COMPLETED", "COMPLETED")

        required = {
            "schema_version",
            "timestamp",
            "started_at",
            "status",
            "mode",
            "pid",
            "process_name",
            "repository_root",
            "git_commit",
            "guardian_status",
            "position_reconciliation_status",
            "current_stage",
            "sequence",
            "orders_submitted",
        }
        self.assertTrue(required.issubset(payload))
        self.assertEqual("PAPER", payload["mode"])
        self.assertEqual(0, payload["orders_submitted"])
        self.assertEqual(timedelta(hours=9), datetime.fromisoformat(payload["timestamp"]).utcoffset())
        self.assertEqual(timedelta(hours=9), datetime.fromisoformat(payload["started_at"]).utcoffset())

    def test_heartbeat_is_saved_with_atomic_replace(self) -> None:
        heartbeat = self.make_heartbeat(interval_seconds=60.0)
        with mock.patch("phoenix_heartbeat.os.replace", wraps=os.replace) as replace:
            heartbeat.start()
        try:
            self.assertEqual(1, replace.call_count)
            self.assertEqual([], list(self.heartbeat_path.parent.glob("*.tmp")))
        finally:
            heartbeat.stop("COMPLETED", "COMPLETED")

    def test_sequence_increases_monotonically(self) -> None:
        heartbeat = self.make_heartbeat(interval_seconds=60.0)
        heartbeat.start()
        try:
            first = heartbeat.sequence
            second = heartbeat.publish()["sequence"]
            third = heartbeat.publish()["sequence"]
        finally:
            heartbeat.stop("COMPLETED", "COMPLETED")

        self.assertEqual(first + 1, second)
        self.assertEqual(second + 1, third)

    def test_background_thread_updates_and_stops_safely(self) -> None:
        heartbeat = self.make_heartbeat(interval_seconds=0.01)
        heartbeat.start()
        self.assertTrue(heartbeat._thread is not None and heartbeat._thread.daemon)
        deadline = time.monotonic() + 1.0
        while heartbeat.sequence < 2 and time.monotonic() < deadline:
            time.sleep(0.005)
        heartbeat.stop("COMPLETED", "COMPLETED")

        self.assertGreaterEqual(heartbeat.sequence, 3)
        self.assertFalse(heartbeat.thread_is_alive)
        payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
        self.assertEqual("COMPLETED", payload["status"])

    def test_terminal_statuses_are_recorded(self) -> None:
        for status in ("COMPLETED", "STOPPED", "FAILED"):
            with self.subTest(status=status):
                heartbeat = self.make_heartbeat(interval_seconds=60.0)
                heartbeat.start()
                heartbeat.stop(status, status)
                payload = json.loads(self.heartbeat_path.read_text(encoding="utf-8"))
                self.assertEqual(status, payload["status"])
                self.assertEqual(status, payload["current_stage"])

    def test_default_intervals_are_thirty_and_ninety_seconds(self) -> None:
        self.assertEqual(30.0, HEARTBEAT_INTERVAL_SECONDS)
        self.assertEqual(90.0, HEARTBEAT_TIMEOUT_SECONDS)

    def test_healthy_heartbeat_is_accepted(self) -> None:
        self.write_payload()

        result = self.inspect()

        self.assertTrue(result.healthy)
        self.assertEqual("HEARTBEAT_OK", result.reason)
        self.assertEqual(1, result.sequence)

    def test_missing_heartbeat_is_abnormal(self) -> None:
        result = self.inspect()

        self.assertFalse(result.healthy)
        self.assertEqual("HEARTBEAT_MISSING", result.reason)

    def test_corrupt_json_is_abnormal(self) -> None:
        self.heartbeat_path.parent.mkdir(parents=True)
        self.heartbeat_path.write_text("{broken", encoding="utf-8")

        result = self.inspect()

        self.assertEqual("HEARTBEAT_JSON_INVALID", result.reason)

    def test_missing_required_field_is_abnormal(self) -> None:
        del self.payload["current_stage"]
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_REQUIRED_FIELD_MISSING", result.reason)

    def test_invalid_field_type_is_abnormal(self) -> None:
        self.payload["sequence"] = "1"
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_SEQUENCE_INVALID", result.reason)

    def test_future_timestamp_is_abnormal(self) -> None:
        self.payload["timestamp"] = (self.now + timedelta(seconds=1)).isoformat()
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_TIMESTAMP_FUTURE", result.reason)

    def test_timezone_free_timestamp_is_abnormal(self) -> None:
        self.payload["timestamp"] = self.now.replace(tzinfo=None).isoformat()
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_TIMESTAMP_TIMEZONE_MISSING", result.reason)

    def test_heartbeat_older_than_ninety_seconds_is_abnormal(self) -> None:
        self.payload["timestamp"] = (self.now - timedelta(seconds=91)).isoformat()
        self.payload["started_at"] = (self.now - timedelta(minutes=2)).isoformat()
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_STALE", result.reason)
        self.assertGreater(result.heartbeat_age_seconds or 0, 90)

    def test_pid_mismatch_is_abnormal(self) -> None:
        self.payload["pid"] = self.pid + 1
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_PID_MISMATCH", result.reason)
        self.assertFalse(result.restart_suppressed)

    def test_repository_root_mismatch_is_safety_stop(self) -> None:
        self.payload["repository_root"] = str(self.root / "copy")
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_REPOSITORY_ROOT_MISMATCH", result.reason)
        self.assertTrue(result.restart_suppressed)

    def test_mode_mismatch_is_safety_stop(self) -> None:
        self.payload["mode"] = "LIVE"
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_MODE_MISMATCH", result.reason)
        self.assertTrue(result.restart_suppressed)

    def test_orders_submitted_mismatch_is_safety_stop(self) -> None:
        self.payload["orders_submitted"] = 1
        self.write_payload()

        result = self.inspect()

        self.assertEqual("HEARTBEAT_ORDERS_SUBMITTED_MISMATCH", result.reason)
        self.assertTrue(result.restart_suppressed)

    def test_sequence_regression_is_abnormal(self) -> None:
        self.write_payload()

        result = self.inspect(previous_sequence=2, previous_timestamp=self.now)

        self.assertEqual("HEARTBEAT_SEQUENCE_REGRESSION", result.reason)

    def test_timestamp_change_without_sequence_increment_is_abnormal(self) -> None:
        self.write_payload()

        result = self.inspect(
            previous_sequence=1,
            previous_timestamp=self.now - timedelta(seconds=1),
        )

        self.assertEqual("HEARTBEAT_SEQUENCE_NOT_INCREMENTED", result.reason)

    def test_audit_logs_are_append_only_jsonl_and_text(self) -> None:
        logger = HeartbeatEventLogger(self.log_dir)
        for sequence in (1, 2):
            self.assertTrue(
                logger.emit(
                    "HEARTBEAT_HEALTHY",
                    status="HEALTHY",
                    reason="HEARTBEAT_OK",
                    pid=self.pid,
                    sequence=sequence,
                    heartbeat_age_seconds=0.1,
                    repository_root=str(self.root),
                    action="MONITOR",
                    restart_attempt=0,
                    checked_at=self.now,
                )
            )

        lines = logger.json_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(2, len(lines))
        payload = json.loads(lines[-1])
        required = {
            "checked_at",
            "event",
            "status",
            "reason",
            "pid",
            "sequence",
            "heartbeat_age_seconds",
            "mode",
            "orders_submitted",
            "repository_root",
            "action",
            "restart_attempt",
        }
        self.assertTrue(required.issubset(payload))
        self.assertIn("Orders submitted: 0", logger.text_path.read_text(encoding="utf-8"))

    def test_audit_log_failure_is_not_retried(self) -> None:
        logger = HeartbeatEventLogger(self.log_dir)
        with mock.patch.object(Path, "open", side_effect=OSError("read only")) as opened:
            result = logger.emit(
                "HEARTBEAT_INVALID",
                status="ABNORMAL",
                reason="test",
                pid=self.pid,
                sequence=1,
                heartbeat_age_seconds=None,
                repository_root=str(self.root),
                action="RESTART_PENDING",
                restart_attempt=0,
                checked_at=self.now,
            )

        self.assertFalse(result)
        self.assertEqual(1, logger.write_failures)
        self.assertEqual(1, opened.call_count)


class RunPhoenixHeartbeatIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.run_phoenix = importlib.import_module("run_phoenix")

    def tearDown(self) -> None:
        self.run_phoenix._ACTIVE_RECOVERY_SESSION = None
        self.run_phoenix._ACTIVE_FAIL_SAFE = None
        self.run_phoenix._ACTIVE_HEARTBEAT = None

    def test_guardian_blocked_does_not_start_heartbeat(self) -> None:
        guardian = SimpleNamespace(
            ready=False,
            status="BLOCKED",
            reasons=("GIT_ROOT_MISMATCH",),
            report_error=None,
        )
        with (
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(
                self.run_phoenix,
                "run_repository_guardian",
                return_value=guardian,
            ),
            mock.patch.object(self.run_phoenix, "PhoenixHeartbeat") as heartbeat,
        ):
            with self.assertRaises(SystemExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(2, stopped.exception.code)
        heartbeat.assert_not_called()

    def test_position_reconciliation_not_ready_does_not_start_heartbeat(self) -> None:
        guardian = SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
        )
        reconciliation = SimpleNamespace(
            status="BLOCKED",
            reasons=("STATE_JSON_MISSING",),
            report_error=None,
        )
        with (
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(
                self.run_phoenix,
                "run_repository_guardian",
                return_value=guardian,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_position_reconciliation",
                return_value=reconciliation,
            ),
            mock.patch.object(self.run_phoenix, "PhoenixHeartbeat") as heartbeat,
        ):
            with self.assertRaises(SystemExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(2, stopped.exception.code)
        heartbeat.assert_not_called()

    def test_heartbeat_starts_after_ready_gates_before_existing_processing(self) -> None:
        events: list[str] = []
        guardian = SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
        )
        reconciliation = SimpleNamespace(
            status="READY",
            reasons=(),
            report_error=None,
        )
        recovery = SimpleNamespace(
            blocked=False,
            recovery_required=False,
            recovery_status="READY",
            recovery_reasons=(),
            state_path="recovery.json",
            previous_git_commit="a" * 40,
            recovery_attempt=0,
            recovered_at=None,
        )
        heartbeat = mock.Mock()
        heartbeat.heartbeat_path = "heartbeat.json"
        heartbeat.pid = 1234
        heartbeat.start.side_effect = lambda **kwargs: events.append("heartbeat")

        class RecordingFailSafe:
            def __init__(self, **kwargs: object) -> None:
                self.stoppers = []

            def update_statuses(self, **kwargs: object) -> None:
                pass

            def register_background_stopper(self, name: str, stopper) -> None:
                self.stoppers.append(stopper)

            def start_monitoring(self, **kwargs: object) -> None:
                events.append("fail_safe")

            def raise_if_triggered(self) -> None:
                pass

            def transition(self, reason: str, **kwargs: object) -> None:
                for stopper in self.stoppers:
                    stopper()

            def stop_monitoring(self) -> None:
                pass

        def stop_after_gate() -> None:
            events.append("existing_processing")
            raise RuntimeError("stop after heartbeat")

        with (
            mock.patch.object(self.run_phoenix, "FailSafeController", RecordingFailSafe),
            mock.patch.object(self.run_phoenix, "RecoverySession"),
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(
                self.run_phoenix,
                "run_repository_guardian",
                side_effect=lambda **kwargs: events.append("guardian") or guardian,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_position_reconciliation",
                side_effect=lambda **kwargs: events.append("reconciliation") or reconciliation,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_disaster_recovery",
                side_effect=lambda **kwargs: events.append("disaster_recovery") or recovery,
            ),
            mock.patch.object(
                self.run_phoenix,
                "PhoenixHeartbeat",
                return_value=heartbeat,
            ),
            mock.patch.object(
                self.run_phoenix,
                "initialize_directories",
                side_effect=stop_after_gate,
            ),
            mock.patch("builtins.print"),
            mock.patch.dict(os.environ, {"PHOENIX_WATCHDOG_RESTART_ATTEMPT": "0"}),
        ):
            with self.assertRaises(self.run_phoenix.FailSafeExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(2, stopped.exception.code)
        self.assertIsInstance(stopped.exception.__cause__, RuntimeError)
        self.assertEqual("stop after heartbeat", str(stopped.exception.__cause__))
        self.assertEqual(
            [
                "guardian",
                "reconciliation",
                "disaster_recovery",
                "heartbeat",
                "fail_safe",
                "existing_processing",
            ],
            events,
        )
        heartbeat.stop.assert_called_once_with(
            status="FAILED",
            current_stage="FAIL_SAFE",
        )

    def test_main_records_completed_failed_and_interrupted_lifecycle(self) -> None:
        scenarios = (
            (None, "COMPLETED", "COMPLETED"),
            (RuntimeError("boom"), "FAILED", "FAILED"),
            (KeyboardInterrupt(), "STOPPED", "INTERRUPTED"),
        )
        for raised, status, stage in scenarios:
            with self.subTest(status=status):
                heartbeat = mock.Mock()

                def run() -> None:
                    self.run_phoenix._ACTIVE_HEARTBEAT = heartbeat
                    if raised is not None:
                        raise raised

                with mock.patch.object(
                    self.run_phoenix,
                    "_run_main",
                    side_effect=run,
                ):
                    if raised is None:
                        self.run_phoenix.main()
                    else:
                        with self.assertRaises(type(raised)):
                            self.run_phoenix.main()
                heartbeat.stop.assert_called_once_with(
                    status=status,
                    current_stage=stage,
                )


class WatchdogHeartbeatIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.log_dir = self.root / "logs"
        self.lock_file = self.log_dir / "phoenix_watchdog.lock"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_script(self, name: str, source: str) -> Path:
        path = self.root / name
        path.write_text(source, encoding="utf-8")
        return path

    def make_watchdog(
        self,
        target: Path,
        *,
        max_restarts: int = 0,
        heartbeat_timeout_seconds: float = 0.2,
    ) -> PhoenixWatchdog:
        return PhoenixWatchdog(
            target_script=target,
            root_dir=self.root,
            log_dir=self.log_dir,
            lock_file=self.lock_file,
            config=MonitorConfig(
                max_restarts=max_restarts,
                backoff_base_seconds=0.01,
                backoff_max_seconds=0.02,
                startup_grace_seconds=0.0,
                poll_seconds=0.005,
                termination_grace_seconds=2.0,
                stale_lock_seconds=1.0,
                heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            ),
        )

    def read_watchdog_events(self) -> list[dict[str, object]]:
        path = next(self.log_dir.glob("phoenix_watchdog_*.jsonl"))
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]

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
                events = self.read_watchdog_events()
                if any(event["event"] == event_name for event in events):
                    return events
            time.sleep(0.01)
        self.fail(f"timed out waiting for {event_name}")

    def write_heartbeat(
        self,
        pid: int,
        sequence: int,
        *,
        mode: str = "PAPER",
    ) -> None:
        path = self.root / "runtime" / "guardian" / "heartbeat.json"
        jst = timezone(timedelta(hours=9))
        now = datetime.now(jst)
        payload = {
            "schema_version": 1,
            "timestamp": now.isoformat(timespec="microseconds"),
            "started_at": (now - timedelta(seconds=1)).isoformat(
                timespec="microseconds"
            ),
            "status": "RUNNING",
            "mode": mode,
            "pid": pid,
            "process_name": "run_phoenix.py",
            "repository_root": str(self.root.resolve()),
            "git_commit": "b1e5a4c",
            "guardian_status": "READY",
            "position_reconciliation_status": "READY",
            "current_stage": "TEST",
            "sequence": sequence,
            "orders_submitted": 0,
        }
        _atomic_write(path, json.dumps(payload))

    def start_heartbeat_writer(
        self,
        watchdog: PhoenixWatchdog,
        *,
        updates: int,
        mode: str = "PAPER",
        interval_seconds: float = 0.02,
    ) -> threading.Thread:
        def write() -> None:
            deadline = time.monotonic() + 2.0
            while watchdog.child_pid is None and time.monotonic() < deadline:
                time.sleep(0.002)
            pid = watchdog.child_pid
            if pid is None:
                return
            for sequence in range(1, updates + 1):
                if watchdog.child_pid != pid:
                    return
                self.write_heartbeat(pid, sequence, mode=mode)
                time.sleep(interval_seconds)

        thread = threading.Thread(target=write, daemon=True)
        thread.start()
        return thread

    def test_valid_heartbeat_is_processed_while_child_runs(self) -> None:
        target = self.write_script(
            "heartbeat_child.py",
            "import time\ntime.sleep(0.3)\n",
        )
        watchdog = self.make_watchdog(target)
        writer = self.start_heartbeat_writer(watchdog, updates=12)
        results: list[int] = []
        thread = threading.Thread(target=lambda: results.append(watchdog.run()))
        thread.start()

        events = self.wait_for_watchdog_event("PROCESS_IDLE")
        self.assertIsNone(watchdog.child_pid)
        self.assertTrue(thread.is_alive())

        writer.join(timeout=1.0)
        watchdog.request_stop("unit_test")
        thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual([EXIT_OK], results)

        events = [
            json.loads(line)
            for line in (self.log_dir / "heartbeat.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        healthy = [event for event in events if event["event"] == "HEARTBEAT_HEALTHY"]
        self.assertGreaterEqual(len(healthy), 2)
        self.assertGreater(max(event["sequence"] for event in healthy), 1)
        self.assertTrue(all(event["mode"] == "PAPER" for event in healthy))
        self.assertTrue(all(event["orders_submitted"] == 0 for event in healthy))

    def test_missing_heartbeat_uses_bounded_restart(self) -> None:
        counter_file = self.root / "heartbeat_missing_launch_count.txt"
        target = self.write_script(
            "heartbeat_missing_child.py",
            f"""
from pathlib import Path
import time

counter = Path({str(counter_file)!r})
count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
counter.write_text(str(count + 1), encoding="utf-8")
time.sleep(1)
""".strip()
            + "\n",
        )
        watchdog = self.make_watchdog(
            target,
            max_restarts=1,
            heartbeat_timeout_seconds=0.15,
        )

        self.assertEqual(EXIT_RESTART_LIMIT, watchdog.run())
        self.assertEqual("2", counter_file.read_text(encoding="utf-8"))
        heartbeat_events = [
            json.loads(line)
            for line in (self.log_dir / "heartbeat.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        names = [event["event"] for event in heartbeat_events]
        self.assertIn("HEARTBEAT_LOST", names)
        self.assertIn("HEARTBEAT_RESTART_SCHEDULED", names)
        self.assertIn("HEARTBEAT_RESTART_LIMIT_REACHED", names)

    def test_heartbeat_stopping_while_process_lives_is_lost(self) -> None:
        target = self.write_script(
            "heartbeat_stops_child.py",
            "import time\ntime.sleep(1)\n",
        )
        watchdog = self.make_watchdog(
            target,
            heartbeat_timeout_seconds=0.05,
        )
        writer = self.start_heartbeat_writer(watchdog, updates=1)

        self.assertEqual(EXIT_RESTART_LIMIT, watchdog.run())
        writer.join(timeout=1.0)

        heartbeat_events = [
            json.loads(line)
            for line in (self.log_dir / "heartbeat.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        lost = [event for event in heartbeat_events if event["event"] == "HEARTBEAT_LOST"]
        self.assertEqual(1, len(lost))
        self.assertEqual("HEARTBEAT_STALE", lost[0]["reason"])

    def test_mode_mismatch_stops_without_restart(self) -> None:
        target = self.write_script(
            "heartbeat_live_mode_child.py",
            "import time\ntime.sleep(1)\n",
        )
        watchdog = self.make_watchdog(
            target,
            max_restarts=3,
            heartbeat_timeout_seconds=0.1,
        )
        writer = self.start_heartbeat_writer(
            watchdog,
            updates=1,
            mode="LIVE",
        )

        self.assertEqual(EXIT_CONFIGURATION_ERROR, watchdog.run())
        writer.join(timeout=1.0)

        names = [event["event"] for event in self.read_watchdog_events()]
        self.assertIn("HEARTBEAT_SAFETY_STOP", names)
        self.assertNotIn("RESTART_SCHEDULED", names)

    def test_position_reconciliation_exit_two_does_not_restart(self) -> None:
        counter_file = self.root / "position_reconciliation_launch_count.txt"
        target = self.write_script(
            "position_reconciliation_blocked_child.py",
            f"""
from pathlib import Path
import sys

counter = Path({str(counter_file)!r})
count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
counter.write_text(str(count + 1), encoding="utf-8")
sys.exit(2)
""".strip()
            + "\n",
        )
        watchdog = self.make_watchdog(target, max_restarts=3)

        self.assertEqual(EXIT_CONFIGURATION_ERROR, watchdog.run())
        self.assertEqual("1", counter_file.read_text(encoding="utf-8"))
        self.assertNotIn(
            "RESTART_SCHEDULED",
            [event["event"] for event in self.read_watchdog_events()],
        )


if __name__ == "__main__":
    unittest.main()
