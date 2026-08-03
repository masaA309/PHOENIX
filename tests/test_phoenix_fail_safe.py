from __future__ import annotations

from datetime import datetime, timedelta
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import phoenix_fail_safe
from phoenix_fail_safe import (
    EXIT_FAIL_SAFE,
    MODE,
    ORDERS_SUBMITTED,
    FailSafeController,
    FailSafeExit,
    JST,
)


class PhoenixFailSafeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "PHOENIX"
        self.root.mkdir()
        self.log_dir = self.root / "logs"
        self.heartbeat_path = self.root / "runtime" / "guardian" / "heartbeat.json"
        self.now = datetime(2026, 8, 3, 9, 0, 0, tzinfo=JST)
        self.pid = 30939

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def heartbeat_payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": 1,
            "timestamp": self.now.isoformat(timespec="seconds"),
            "started_at": (self.now - timedelta(seconds=1)).isoformat(
                timespec="seconds"
            ),
            "status": "RUNNING",
            "mode": "PAPER",
            "pid": self.pid,
            "process_name": "run_phoenix.py",
            "repository_root": str(self.root),
            "git_commit": "a" * 40,
            "guardian_status": "READY",
            "position_reconciliation_status": "READY",
            "current_stage": "OPERATIONAL_READY",
            "sequence": 1,
            "orders_submitted": 0,
        }
        payload.update(overrides)
        return payload

    def write_heartbeat(self, **overrides: object) -> None:
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path.write_text(
            json.dumps(self.heartbeat_payload(**overrides)),
            encoding="utf-8",
        )

    def controller(self, **overrides: object) -> FailSafeController:
        arguments: dict[str, object] = {
            "repository_root": self.root,
            "log_dir": self.log_dir,
            "monitor_interval_seconds": 60.0,
            "now_provider": lambda: self.now,
        }
        arguments.update(overrides)
        controller = FailSafeController(**arguments)
        controller.update_statuses(
            guardian_status="READY",
            position_status="READY",
        )
        return controller

    def assert_exit_two(self, controller: FailSafeController) -> None:
        with self.assertRaises(FailSafeExit) as stopped:
            controller.raise_if_triggered()
        self.assertEqual(EXIT_FAIL_SAFE, stopped.exception.code)

    def test_normal_paper_state_remains_safe(self) -> None:
        self.write_heartbeat()
        controller = self.controller()

        controller.start_monitoring(
            heartbeat_path=self.heartbeat_path,
            expected_pid=self.pid,
        )
        try:
            self.assertFalse(controller.triggered)
            self.assertTrue(controller.monitor_is_alive)
            self.assertEqual("HEALTHY", controller.heartbeat_status)
            self.assertFalse((self.log_dir / "fail_safe.json").exists())
        finally:
            controller.stop_monitoring()

    def test_guardian_blocked_triggers_fail_safe_exit_two(self) -> None:
        controller = self.controller()
        controller.update_statuses(guardian_status="BLOCKED")

        self.assertFalse(controller.check_once())

        self.assertEqual("GUARDIAN_BLOCKED", controller.result.reason)
        self.assert_exit_two(controller)

    def test_position_blocked_triggers_fail_safe(self) -> None:
        controller = self.controller()
        controller.update_statuses(position_status="BLOCKED")

        self.assertFalse(controller.check_once())

        self.assertEqual("POSITION_BLOCKED", controller.result.reason)

    def test_watchdog_abnormal_triggers_fail_safe(self) -> None:
        controller = self.controller(
            watchdog_status_provider=lambda: "ABNORMAL",
        )

        self.assertFalse(controller.check_once())

        self.assertEqual("WATCHDOG_ABNORMAL", controller.result.reason)
        self.assertEqual("ABNORMAL", controller.result.watchdog_status)

    def test_stale_heartbeat_is_lost(self) -> None:
        stale = self.now - timedelta(seconds=91)
        self.write_heartbeat(
            timestamp=stale.isoformat(timespec="seconds"),
            started_at=(stale - timedelta(seconds=1)).isoformat(timespec="seconds"),
        )
        controller = self.controller()

        with self.assertRaises(FailSafeExit) as stopped:
            controller.start_monitoring(
                heartbeat_path=self.heartbeat_path,
                expected_pid=self.pid,
            )

        self.assertEqual(EXIT_FAIL_SAFE, stopped.exception.code)
        self.assertEqual("HEARTBEAT_LOST", controller.result.reason)
        self.assertEqual("LOST", controller.result.heartbeat_status)

    def test_corrupt_heartbeat_json_triggers_fail_safe(self) -> None:
        self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_path.write_text("{broken", encoding="utf-8")
        controller = self.controller()

        with self.assertRaises(FailSafeExit):
            controller.start_monitoring(
                heartbeat_path=self.heartbeat_path,
                expected_pid=self.pid,
            )

        self.assertEqual("JSON_CORRUPT", controller.result.reason)

    def test_pid_repository_mode_and_order_mismatches_fail_closed(self) -> None:
        scenarios = (
            ({"pid": self.pid + 1}, {}, "PID_MISMATCH"),
            (
                {"repository_root": str(self.root / "other")},
                {},
                "REPOSITORY_MISMATCH",
            ),
            ({"mode": "LIVE"}, {}, "MODE_NOT_PAPER"),
            ({"orders_submitted": 1}, {}, "ORDERS_SUBMITTED_NONZERO"),
            ({}, {"mode": "LIVE"}, "MODE_NOT_PAPER"),
            ({}, {"orders_submitted": 1}, "ORDERS_SUBMITTED_NONZERO"),
        )
        for payload_changes, controller_changes, expected_reason in scenarios:
            with self.subTest(reason=expected_reason, changes=controller_changes):
                self.write_heartbeat(**payload_changes)
                controller = self.controller(**controller_changes)
                with self.assertRaises(FailSafeExit):
                    controller.start_monitoring(
                        heartbeat_path=self.heartbeat_path,
                        expected_pid=self.pid,
                    )
                self.assertEqual(expected_reason, controller.result.reason)

    def test_atomic_json_and_text_logs_contain_required_fields(self) -> None:
        controller = self.controller()

        with mock.patch(
            "phoenix_fail_safe.os.replace",
            wraps=os.replace,
        ) as replace:
            result = controller.transition("HEARTBEAT_LOST", heartbeat_status="LOST")

        self.assertEqual(2, replace.call_count)
        self.assertEqual([], list(self.log_dir.glob("*.tmp")))
        payload = json.loads(
            (self.log_dir / "fail_safe.json").read_text(encoding="utf-8")
        )
        required = {
            "timestamp",
            "reason",
            "status",
            "mode",
            "orders_submitted",
            "repository_root",
            "guardian_status",
            "position_status",
            "heartbeat_status",
            "watchdog_status",
            "exit_code",
        }
        self.assertTrue(required.issubset(payload))
        self.assertEqual(result.as_dict(), payload)
        self.assertTrue(payload["timestamp"].endswith("+09:00"))
        text = (self.log_dir / "fail_safe.txt").read_text(encoding="utf-8")
        self.assertIn("Status: FAIL_SAFE", text)
        self.assertIn("Orders submitted: 0", text)

    def test_transition_stops_all_registered_backgrounds_once(self) -> None:
        controller = self.controller()
        first = mock.Mock()
        second = mock.Mock()
        controller.register_background_stopper("first", first)
        controller.register_background_stopper("second", second)

        first_result = controller.transition("UNCAUGHT_EXCEPTION")
        second_result = controller.transition("IGNORED_SECOND_TRIGGER")

        first.assert_called_once_with()
        second.assert_called_once_with()
        self.assertIs(first_result, second_result)

    def test_fixed_safety_constants_are_paper_and_zero_orders(self) -> None:
        controller = self.controller()
        result = controller.transition("TEST_STOP")

        self.assertEqual("PAPER", MODE)
        self.assertEqual(0, ORDERS_SUBMITTED)
        self.assertEqual("PAPER", result.mode)
        self.assertEqual(0, result.orders_submitted)


class RunPhoenixFailSafeIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.run_phoenix = importlib.import_module("run_phoenix")

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "PHOENIX"
        self.root.mkdir()
        self.log_dir = self.root / "logs"
        self.events: list[str] = []

    def tearDown(self) -> None:
        self.run_phoenix._ACTIVE_RECOVERY_SESSION = None
        self.run_phoenix._ACTIVE_FAIL_SAFE = None
        self.run_phoenix._ACTIVE_HEARTBEAT = None
        self.temporary_directory.cleanup()

    def test_run_order_and_uncaught_exception_enter_fail_safe(self) -> None:
        events = self.events
        root = self.root

        class RecordingController(FailSafeController):
            def start_monitoring(self, **kwargs: object) -> None:
                events.append("fail_safe_monitor")
                super().start_monitoring(**kwargs)

        class FakeHeartbeat:
            def __init__(self, **kwargs: object) -> None:
                self.repository_root = Path(kwargs["repository_root"])
                self.heartbeat_path = (
                    self.repository_root / "runtime" / "guardian" / "heartbeat.json"
                )
                self.pid = os.getpid()
                self.stop = mock.Mock()

            def start(self, **kwargs: object) -> None:
                events.append("heartbeat")
                now = datetime.now(JST)
                payload = {
                    "schema_version": 1,
                    "timestamp": now.isoformat(timespec="seconds"),
                    "started_at": now.isoformat(timespec="seconds"),
                    "status": "RUNNING",
                    "mode": "PAPER",
                    "pid": self.pid,
                    "process_name": "run_phoenix.py",
                    "repository_root": str(self.repository_root),
                    "git_commit": "a" * 40,
                    "guardian_status": "READY",
                    "position_reconciliation_status": "READY",
                    "current_stage": "OPERATIONAL_READY",
                    "sequence": 1,
                    "orders_submitted": 0,
                }
                self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
                self.heartbeat_path.write_text(json.dumps(payload), encoding="utf-8")

            def set_stage(self, stage: str) -> None:
                pass

        heartbeat_instances: list[FakeHeartbeat] = []

        def heartbeat_factory(**kwargs: object) -> FakeHeartbeat:
            heartbeat = FakeHeartbeat(**kwargs)
            heartbeat_instances.append(heartbeat)
            return heartbeat

        guardian = mock.Mock(ready=True, status="READY", reasons=(), report_error=None)
        position = mock.Mock(status="READY", reasons=(), report_error=None)
        recovery = mock.Mock(
            blocked=False,
            recovery_required=False,
            recovery_status="READY",
            recovery_reasons=(),
            state_path=root / "runtime" / "guardian" / "recovery_state.json",
            previous_git_commit="a" * 40,
            recovery_attempt=0,
            recovered_at=None,
        )

        def initialize() -> None:
            events.append("existing_processing")
            raise RuntimeError("unexpected")

        with (
            mock.patch.object(self.run_phoenix, "ROOT_DIR", root),
            mock.patch.object(self.run_phoenix, "LOG_DIR", self.log_dir),
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
                side_effect=lambda **kwargs: events.append("disaster_recovery") or recovery,
            ),
            mock.patch.object(self.run_phoenix, "RecoverySession"),
            mock.patch.object(self.run_phoenix, "PhoenixHeartbeat", side_effect=heartbeat_factory),
            mock.patch.object(self.run_phoenix, "FailSafeController", RecordingController),
            mock.patch.object(self.run_phoenix, "initialize_directories", side_effect=initialize),
            mock.patch.object(sys, "argv", ["run_phoenix.py"]),
            mock.patch("builtins.print"),
        ):
            with self.assertRaises(FailSafeExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(EXIT_FAIL_SAFE, stopped.exception.code)
        self.assertEqual(
            [
                "guardian",
                "position",
                "disaster_recovery",
                "heartbeat",
                "fail_safe_monitor",
                "existing_processing",
            ],
            events,
        )
        payload = json.loads(
            (self.log_dir / "fail_safe.json").read_text(encoding="utf-8")
        )
        self.assertEqual("UNCAUGHT_EXCEPTION", payload["reason"])
        heartbeat_instances[0].stop.assert_called_once_with(
            status="FAILED",
            current_stage="FAIL_SAFE",
        )

    def test_guardian_blocked_exits_two_before_position_and_heartbeat(self) -> None:
        guardian = mock.Mock(
            ready=False,
            status="BLOCKED",
            reasons=("REPOSITORY_MISMATCH",),
            report_error=None,
        )
        with (
            mock.patch.object(self.run_phoenix, "ROOT_DIR", self.root),
            mock.patch.object(self.run_phoenix, "LOG_DIR", self.log_dir),
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(
                self.run_phoenix,
                "run_repository_guardian",
                return_value=guardian,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_position_reconciliation",
            ) as position,
            mock.patch.object(self.run_phoenix, "PhoenixHeartbeat") as heartbeat,
            mock.patch("builtins.print"),
        ):
            with self.assertRaises(FailSafeExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(EXIT_FAIL_SAFE, stopped.exception.code)
        position.assert_not_called()
        heartbeat.assert_not_called()
        payload = json.loads(
            (self.log_dir / "fail_safe.json").read_text(encoding="utf-8")
        )
        self.assertEqual("GUARDIAN_BLOCKED", payload["reason"])


if __name__ == "__main__":
    unittest.main()
