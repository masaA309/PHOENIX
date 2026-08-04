from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import run_phoenix


class FakeFailSafe:
    triggered = False

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.monitor_only_enabled = False
        self.triggered = False

    def update_statuses(self, **kwargs: object) -> None:
        self.status_updates = kwargs

    def enable_monitor_only(self) -> None:
        self.monitor_only_enabled = True

    def register_background_stopper(self, *args: object) -> None:
        self.background_stopper = args

    def start_monitoring(self, **kwargs: object) -> None:
        self.monitoring = kwargs

    def transition(self, reason: str, **kwargs: object) -> None:
        self.transitioned = {"reason": reason, **kwargs}
        self.triggered = True

    def stop_monitoring(self) -> None:
        self.stop_monitoring_called = True

    def raise_if_triggered(self) -> None:
        return None

    def fail_and_exit(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("fail_and_exit should not be reached in this test")


class FakeHeartbeat:
    heartbeat_path = "heartbeat.json"
    pid = 4321

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.stages: list[str] = []

    def start(self, **kwargs: object) -> None:
        self.start_kwargs = kwargs

    def set_stage(self, stage: str) -> None:
        self.stages.append(stage)

    def stop(self, **kwargs: object) -> None:
        self.stop_kwargs = kwargs


class FakeRecoverySession:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def start(self) -> None:
        self.started = True

    def finish(
        self,
        *,
        status: str,
        heartbeat_status: str,
        fail_safe_status: str,
    ) -> None:
        self.finished = {
            "status": status,
            "heartbeat_status": heartbeat_status,
            "fail_safe_status": fail_safe_status,
        }


class WeeklySignalComparisonRunPhoenixTest(unittest.TestCase):
    def setUp(self) -> None:
        run_phoenix._ACTIVE_RECOVERY_SESSION = None
        run_phoenix._ACTIVE_FAIL_SAFE = None
        run_phoenix._ACTIVE_HEARTBEAT = None
        self.fail_safe_instances: list[FakeFailSafe] = []

    def tearDown(self) -> None:
        run_phoenix._ACTIVE_RECOVERY_SESSION = None
        run_phoenix._ACTIVE_FAIL_SAFE = None
        run_phoenix._ACTIVE_HEARTBEAT = None
        self.fail_safe_instances = []

    def _guardian(self) -> SimpleNamespace:
        return SimpleNamespace(
            ready=True,
            status="READY",
            reasons=(),
            report_error=None,
            expected_root=Path.cwd(),
        )

    def _ready_position(self) -> SimpleNamespace:
        timestamp = datetime(2026, 8, 4, 9, 0, 0, tzinfo=timezone.utc).isoformat()
        source_timestamp = datetime(2026, 8, 4, 8, 0, 0, tzinfo=timezone.utc).isoformat()
        return SimpleNamespace(
            status="READY",
            reasons=(),
            mode="PAPER",
            orders_submitted=0,
            guardian_status="READY",
            report_error=None,
            exit_code=0,
            checked_at=timestamp,
            source_timestamp=source_timestamp,
            positions_count=0,
        )

    def _monitor_only_position(self) -> SimpleNamespace:
        timestamp = datetime(2026, 8, 4, 9, 0, 0, tzinfo=timezone.utc).isoformat()
        source_timestamp = datetime(2026, 8, 4, 8, 0, 0, tzinfo=timezone.utc).isoformat()
        return SimpleNamespace(
            status="WARNING",
            reasons=("POSITIONS_PRESENT",),
            mode="PAPER",
            orders_submitted=0,
            guardian_status="READY",
            report_error=None,
            exit_code=0,
            checked_at=timestamp,
            source_timestamp=source_timestamp,
            positions_count=1,
        )

    def _recovery_result(self) -> SimpleNamespace:
        return SimpleNamespace(
            blocked=False,
            recovery_required=False,
            recovery_status="READY",
            recovery_reasons=[],
            state_path=Path("recovery_state.json"),
            previous_git_commit="a" * 40,
            current_git_commit="a" * 40,
            recovery_attempt=0,
            recovered_at=None,
        )

    def _patch_daily_run(
        self,
        stack: ExitStack,
        *,
        run_script_result: tuple[bool, float, int, str],
        position_result: SimpleNamespace,
    ) -> None:
        test_case = self
        stack.enter_context(mock.patch.object(run_phoenix, "write_log"))
        stack.enter_context(mock.patch.object(run_phoenix, "configure_console"))
        stack.enter_context(mock.patch.object(run_phoenix, "initialize_directories"))
        stack.enter_context(mock.patch.object(run_phoenix, "reset_log_file"))
        stack.enter_context(
            mock.patch.object(
                run_phoenix,
                "configure_quote_transport",
                return_value={
                    "status": "READY",
                    "ca_bundle_mode": "LOCAL_MATERIALIZED_COPY",
                    "code": "READY",
                },
            )
        )
        stack.enter_context(
            mock.patch.object(
                run_phoenix,
                "run_repository_guardian",
                return_value=self._guardian(),
            )
        )
        stack.enter_context(
            mock.patch.object(
                run_phoenix,
                "run_position_reconciliation",
                return_value=position_result,
            )
        )
        stack.enter_context(
            mock.patch.object(
                run_phoenix,
                "run_disaster_recovery",
                return_value=self._recovery_result(),
            )
        )
        stack.enter_context(mock.patch.object(run_phoenix, "PhoenixHeartbeat", FakeHeartbeat))
        stack.enter_context(mock.patch.object(run_phoenix, "RecoverySession", FakeRecoverySession))
        self.fail_safe_instances = []

        class CapturingFailSafe(FakeFailSafe):
            def __init__(self, **kwargs: object) -> None:
                super().__init__(**kwargs)
                test_case.fail_safe_instances.append(self)

        stack.enter_context(
            mock.patch.object(run_phoenix, "FailSafeController", CapturingFailSafe)
        )
        stack.enter_context(
            mock.patch.object(
                run_phoenix,
                "TASKS",
                [
                    {
                        "name": "Daily Report",
                        "script": "daily_report.py",
                        "required": True,
                        "enabled": True,
                    }
                ],
            )
        )
        stack.enter_context(
            mock.patch.object(
                run_phoenix,
                "verify_output_files",
                return_value={"日次レポートCSV": True},
            )
        )
        stack.enter_context(mock.patch.object(run_phoenix, "print_final_summary"))
        stack.enter_context(mock.patch.object(run_phoenix, "print_morning_run_summary"))
        stack.enter_context(mock.patch.object(run_phoenix.sys, "argv", ["run_phoenix.py"]))
        stack.enter_context(
            mock.patch.dict(
                run_phoenix.os.environ,
                {"PHOENIX_WATCHDOG_RESTART_ATTEMPT": "0"},
                clear=False,
            )
        )

        def run_script_side_effect(
            task_name: str,
            script_name: str,
            required: bool,
            args: list[str] | None = None,
            monitor_only: bool = False,
        ) -> tuple[bool, float, int, str]:
            self.assertEqual("daily_report.py", script_name)
            self.assertEqual(position_result.status == "WARNING", monitor_only)
            return run_script_result

        stack.enter_context(
            mock.patch.object(
                run_phoenix,
                "run_script",
                side_effect=run_script_side_effect,
            )
        )

    def test_monitor_only_success_triggers_weekly_comparison(self) -> None:
        comparison_mock = mock.Mock(return_value={"status": "READY"})
        with ExitStack() as stack:
            self._patch_daily_run(
                stack,
                run_script_result=(True, 0.1, 0, "ok"),
                position_result=self._monitor_only_position(),
            )
            stack.enter_context(
                mock.patch.object(
                    run_phoenix,
                    "_run_weekly_signal_comparison",
                    comparison_mock,
                )
            )
            run_phoenix.main()

        comparison_mock.assert_called_once()
        self.assertTrue(self.fail_safe_instances)
        self.assertTrue(self.fail_safe_instances[-1].monitor_only_enabled)

    def test_ready_success_triggers_weekly_comparison(self) -> None:
        comparison_mock = mock.Mock(return_value={"status": "READY"})
        with ExitStack() as stack:
            self._patch_daily_run(
                stack,
                run_script_result=(True, 0.1, 0, "ok"),
                position_result=self._ready_position(),
            )
            stack.enter_context(
                mock.patch.object(
                    run_phoenix,
                    "_run_weekly_signal_comparison",
                    comparison_mock,
                )
            )
            run_phoenix.main()

        comparison_mock.assert_called_once()
        self.assertTrue(self.fail_safe_instances)
        self.assertFalse(self.fail_safe_instances[-1].monitor_only_enabled)

    def test_weekly_comparison_failure_is_optional(self) -> None:
        with (
            mock.patch.object(run_phoenix, "write_log"),
            mock.patch.object(
                run_phoenix,
                "run_latest_weekly_signal_comparison",
                side_effect=RuntimeError("boom"),
            ) as comparison,
        ):
            result = run_phoenix._run_weekly_signal_comparison()

        self.assertIsNone(result)
        comparison.assert_called_once()

    def test_daily_report_failure_skips_weekly_comparison(self) -> None:
        comparison_mock = mock.Mock(return_value={"status": "READY"})
        with ExitStack() as stack:
            self._patch_daily_run(
                stack,
                run_script_result=(False, 0.1, 1, "failed"),
                position_result=self._ready_position(),
            )
            stack.enter_context(
                mock.patch.object(
                    run_phoenix,
                    "_run_weekly_signal_comparison",
                    comparison_mock,
                )
            )
            with self.assertRaises(SystemExit) as cm:
                run_phoenix.main()

        self.assertEqual(1, cm.exception.code)
        comparison_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
