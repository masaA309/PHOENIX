from __future__ import annotations

from datetime import datetime, timedelta
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

import position_reconciliation
from position_reconciliation import (
    EXIT_BLOCKED,
    EXIT_READY,
    JST,
    MODE,
    ORDERS_SUBMITTED,
    run_position_reconciliation,
)


class PositionReconciliationStep37Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.state_path = self.root / "state" / "paper.json"
        self.report_dir = self.root / "logs"
        self.now = datetime(2026, 8, 3, 9, 0, tzinfo=JST)
        self.payload = {
            "mode": "PAPER",
            "orders_submitted": 0,
            "positions": {},
            "source_timestamp": self.now.isoformat(),
            "live_trading_enabled": False,
            "margin_trading_enabled": False,
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_state(self, payload: dict | None = None) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self.payload if payload is None else payload),
            encoding="utf-8",
        )

    def run_reconciliation(self, **overrides):
        arguments = {
            "guardian_status": "READY",
            "state_path": self.state_path,
            "report_dir": self.report_dir,
            "now": self.now,
        }
        arguments.update(overrides)
        return run_position_reconciliation(**arguments)

    def test_ready_for_fresh_paper_state_with_zero_positions(self) -> None:
        self.write_state()

        result = self.run_reconciliation()

        self.assertTrue(result.ready)
        self.assertEqual("READY", result.status)
        self.assertEqual(0, result.positions_count)
        self.assertEqual(EXIT_READY, result.exit_code)

    def test_orders_submitted_other_than_zero_is_blocked(self) -> None:
        self.payload["orders_submitted"] = 1
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("ORDERS_SUBMITTED_NOT_ZERO", result.reasons)
        self.assertEqual(EXIT_BLOCKED, result.exit_code)

    def test_mode_other_than_paper_is_blocked(self) -> None:
        self.payload["mode"] = "LIVE"
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("MODE_NOT_PAPER", result.reasons)

    def test_negative_positions_count_is_blocked(self) -> None:
        del self.payload["positions"]
        self.payload["positions_count"] = -1
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("POSITIONS_COUNT_NEGATIVE", result.reasons)

    def test_missing_json_is_blocked(self) -> None:
        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("STATE_JSON_MISSING", result.reasons)

    def test_corrupt_json_is_blocked(self) -> None:
        self.state_path.parent.mkdir(parents=True)
        self.state_path.write_text("{broken", encoding="utf-8")

        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("STATE_JSON_INVALID", result.reasons)

    def test_missing_required_field_is_blocked(self) -> None:
        del self.payload["positions"]
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("STATE_REQUIRED_FIELD_MISSING", result.reasons)

    def test_future_source_timestamp_is_blocked(self) -> None:
        self.payload["source_timestamp"] = (
            self.now + timedelta(seconds=1)
        ).isoformat()
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("SOURCE_TIMESTAMP_FUTURE", result.reasons)

    def test_stale_source_timestamp_is_blocked(self) -> None:
        self.payload["source_timestamp"] = (
            self.now - timedelta(hours=25)
        ).isoformat()
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("SOURCE_STATE_STALE", result.reasons)

    def test_json_and_text_logs_include_required_fields(self) -> None:
        self.write_state()

        result = self.run_reconciliation()

        payload = json.loads(
            Path(result.json_report_path).read_text(encoding="utf-8")
        )
        required = {
            "checked_at",
            "status",
            "reasons",
            "mode",
            "positions_count",
            "orders_submitted",
            "guardian_status",
            "previous_run_status",
            "source_timestamp",
            "exit_code",
        }
        self.assertTrue(required.issubset(payload))
        self.assertIsNotNone(datetime.fromisoformat(payload["checked_at"]).utcoffset())
        text = Path(result.text_report_path).read_text(encoding="utf-8")
        self.assertIn("Mode: PAPER", text)
        self.assertIn("Orders submitted: 0", text)
        self.assertIn("Status: READY", text)

    def test_reports_are_saved_with_atomic_replace(self) -> None:
        self.write_state()
        with mock.patch(
            "position_reconciliation.os.replace",
            wraps=os.replace,
        ) as replace:
            result = self.run_reconciliation()

        self.assertEqual(2, replace.call_count)
        self.assertTrue(Path(result.json_report_path).is_file())
        self.assertTrue(Path(result.text_report_path).is_file())
        self.assertEqual([], list(self.report_dir.glob("*.tmp")))

    def test_valid_nonzero_positions_returns_warning(self) -> None:
        self.payload["positions"] = {
            "1111.T": {"quantity": 100},
        }
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("WARNING", result.status)
        self.assertEqual(1, result.positions_count)
        self.assertIn("POSITIONS_PRESENT", result.reasons)
        self.assertEqual(EXIT_READY, result.exit_code)

    def test_previous_run_status_is_recorded(self) -> None:
        self.write_state()
        first = self.run_reconciliation()
        second = self.run_reconciliation()

        self.assertEqual("NOT_AVAILABLE", first.previous_run_status)
        self.assertEqual("READY", second.previous_run_status)

    def test_guardian_not_ready_short_circuits_position_provider(self) -> None:
        class ExplodingProvider:
            def get_snapshot(self):
                raise AssertionError("provider must not be called")

        result = self.run_reconciliation(
            guardian_status="BLOCKED",
            provider=ExplodingProvider(),
        )

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("GUARDIAN_NOT_READY", result.reasons)

    def test_fixed_safety_constants_remain_paper_and_zero_orders(self) -> None:
        self.write_state()

        result = self.run_reconciliation()

        self.assertEqual("PAPER", MODE)
        self.assertEqual(0, ORDERS_SUBMITTED)
        self.assertEqual("PAPER", result.mode)
        self.assertEqual(0, result.orders_submitted)


class RunPhoenixPositionReconciliationIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.run_phoenix = importlib.import_module("run_phoenix")

    def tearDown(self) -> None:
        self.run_phoenix._ACTIVE_RECOVERY_SESSION = None
        self.run_phoenix._ACTIVE_FAIL_SAFE = None
        self.run_phoenix._ACTIVE_HEARTBEAT = None

    def test_guardian_blocked_does_not_run_reconciliation(self) -> None:
        blocked = SimpleNamespace(
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
                return_value=blocked,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_position_reconciliation",
            ) as reconcile,
            mock.patch.object(self.run_phoenix, "initialize_directories") as initialize,
            mock.patch.object(sys, "argv", ["run_phoenix.py"]),
        ):
            with self.assertRaises(SystemExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(2, stopped.exception.code)
        reconcile.assert_not_called()
        initialize.assert_not_called()

    def test_reconciliation_blocked_exits_two_before_initialization(self) -> None:
        guardian = SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
        )
        blocked = SimpleNamespace(
            blocked=True,
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
                return_value=blocked,
            ) as reconcile,
            mock.patch.object(self.run_phoenix, "initialize_directories") as initialize,
            mock.patch.object(sys, "argv", ["run_phoenix.py"]),
        ):
            with self.assertRaises(SystemExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(2, stopped.exception.code)
        reconcile.assert_called_once_with(
            guardian_status="READY",
            report_dir=self.run_phoenix.LOG_DIR,
        )
        initialize.assert_not_called()

    def test_reconciliation_runs_between_guardian_and_initialization(self) -> None:
        events: list[str] = []
        guardian = SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
        )
        ready = SimpleNamespace(
            blocked=False,
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

        class FakeFailSafe:
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

        class FakeRecoverySession:
            def __init__(self, **kwargs: object) -> None:
                pass

            def start(self) -> None:
                pass

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

        def guard(**kwargs):
            events.append("guardian")
            return guardian

        def reconcile(**kwargs):
            events.append("reconciliation")
            return ready

        def stop_after_gates():
            events.append("initialization")
            raise RuntimeError("stop after startup gates")

        def capture_print(*args, **kwargs):
            if args and args[0] == "PHOENIX OPERATIONAL READY":
                events.append("operational_ready")

        with (
            mock.patch.object(self.run_phoenix, "FailSafeController", FakeFailSafe),
            mock.patch.object(self.run_phoenix, "RecoverySession", FakeRecoverySession),
            mock.patch.object(self.run_phoenix, "PhoenixHeartbeat", FakeHeartbeat),
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(self.run_phoenix, "run_repository_guardian", side_effect=guard),
            mock.patch.object(self.run_phoenix, "run_position_reconciliation", side_effect=reconcile),
            mock.patch.object(
                self.run_phoenix,
                "run_disaster_recovery",
                side_effect=lambda **kwargs: events.append("disaster_recovery") or recovery,
            ),
            mock.patch.object(self.run_phoenix, "initialize_directories", side_effect=stop_after_gates),
            mock.patch("builtins.print", side_effect=capture_print),
            mock.patch.dict(os.environ, {"PHOENIX_WATCHDOG_RESTART_ATTEMPT": "0"}),
            mock.patch.object(sys, "argv", ["run_phoenix.py"]),
        ):
            with self.assertRaisesRegex(RuntimeError, "stop after startup gates"):
                self.run_phoenix._run_main()

        self.assertEqual(
            [
                "guardian",
                "reconciliation",
                "disaster_recovery",
                "heartbeat",
                "fail_safe",
                "operational_ready",
                "initialization",
            ],
            events,
        )

    def test_unexpected_reconciliation_exception_propagates(self) -> None:
        transitions: list[str] = []
        guardian = SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
        )

        class RecordingFailSafe:
            def __init__(self, **kwargs: object) -> None:
                pass

            def update_statuses(self, **kwargs: object) -> None:
                pass

            def transition(self, reason: str, **kwargs: object) -> None:
                transitions.append(reason)

            def stop_monitoring(self) -> None:
                pass

        with (
            mock.patch.object(self.run_phoenix, "FailSafeController", RecordingFailSafe),
            mock.patch.object(self.run_phoenix, "configure_console"),
            mock.patch.object(
                self.run_phoenix,
                "run_repository_guardian",
                return_value=guardian,
            ),
            mock.patch.object(
                self.run_phoenix,
                "run_position_reconciliation",
                side_effect=RuntimeError("unexpected"),
            ),
            mock.patch.object(self.run_phoenix, "initialize_directories") as initialize,
            mock.patch.object(sys, "argv", ["run_phoenix.py"]),
        ):
            with self.assertRaises(self.run_phoenix.FailSafeExit) as stopped:
                self.run_phoenix.main()

        self.assertEqual(2, stopped.exception.code)
        self.assertEqual(["UNCAUGHT_EXCEPTION"], transitions)
        self.assertIsInstance(stopped.exception.__cause__, RuntimeError)
        self.assertEqual("unexpected", str(stopped.exception.__cause__))
        initialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
