from __future__ import annotations

from datetime import datetime
import json
import tempfile
import unittest
from pathlib import Path

from phoenix_core.operations_monitor import (
    build_operations_report,
    run_operations_monitor,
)


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class OperationsMonitorStep9Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        (self.root / "logs" / "scheduler").mkdir(parents=True)
        (self.root / "reports").mkdir()
        (self.root / "state").mkdir()
        self.log_path = self.root / "logs" / "scheduler" / "run.log"
        self.log_path.write_text("pipeline complete\n", encoding="utf-8")
        self.summary_path = self.root / "reports" / "v7_direct_pipeline_summary.json"
        self.state_path = self.root / "state" / "v7_scheduler_state.json"
        self.write_summary()
        self.state_path.write_text(
            json.dumps({"last_success_at": "2026-07-20T08:30:00"}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_summary(
        self,
        *,
        halted: bool = False,
        approved: int = 1,
        filled: int = 1,
    ) -> None:
        self.summary_path.write_text(
            json.dumps(
                {
                    "candidate_count": 3,
                    "ready_count": 2,
                    "approved_count": approved,
                    "filled_count": filled,
                    "halted": halted,
                    "halt_reason": "daily loss" if halted else "",
                }
            ),
            encoding="utf-8",
        )

    def config(self, notification_enabled: bool = False) -> dict:
        return {
            "scheduler": {"dry_run": False},
            "files": {"scheduler_state": "state/v7_scheduler_state.json"},
            "operations": {
                "pipeline_summary": "reports/v7_direct_pipeline_summary.json",
                "report_json": "reports/v7_operations_report.json",
                "report_text": "reports/v7_operations_report.txt",
                "notification": {
                    "enabled": notification_enabled,
                    "notify_on_success": True,
                    "notify_on_failure": True,
                    "webhook_env": "TEST_WEBHOOK",
                    "timeout_seconds": 5,
                },
            },
        }

    def test_success_report(self) -> None:
        report = build_operations_report(
            self.root,
            self.config(),
            0,
            self.log_path,
            generated_at=datetime(2026, 7, 20, 9, 0, 0),
        )
        self.assertEqual("SUCCESS", report["status"])
        self.assertEqual(1, report["pipeline"]["filled_count"])
        self.assertEqual([], report["alerts"])

    def test_failed_return_code_is_critical(self) -> None:
        report = build_operations_report(
            self.root,
            self.config(),
            7,
            self.log_path,
        )
        self.assertEqual("FAILED", report["status"])
        self.assertIn("PIPELINE_FAILED", {item["code"] for item in report["alerts"]})

    def test_risk_halt_is_failed(self) -> None:
        self.write_summary(halted=True, approved=0, filled=0)
        report = build_operations_report(
            self.root,
            self.config(),
            0,
            self.log_path,
        )
        self.assertEqual("FAILED", report["status"])
        self.assertIn("RISK_HALTED", {item["code"] for item in report["alerts"]})

    def test_unfilled_orders_warn(self) -> None:
        self.write_summary(approved=2, filled=1)
        report = build_operations_report(
            self.root,
            self.config(),
            0,
            self.log_path,
        )
        self.assertEqual("WARNING", report["status"])
        self.assertIn(
            "UNFILLED_APPROVED_ORDERS",
            {item["code"] for item in report["alerts"]},
        )

    def test_report_files_are_saved(self) -> None:
        report = run_operations_monitor(
            self.root,
            self.config(),
            0,
            self.log_path,
        )
        json_path = Path(report["report_json"])
        text_path = Path(report["report_text"])
        self.assertTrue(json_path.is_file())
        self.assertTrue(text_path.is_file())
        saved = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual("SUCCESS", saved["status"])

    def test_discord_notification_uses_safe_payload(self) -> None:
        calls: list[dict] = []

        def fake_post(url: str, **kwargs: object) -> FakeResponse:
            calls.append({"url": url, **kwargs})
            return FakeResponse(204)

        report = run_operations_monitor(
            self.root,
            self.config(notification_enabled=True),
            0,
            self.log_path,
            environment={"TEST_WEBHOOK": "https://example.invalid/webhook"},
            post=fake_post,
        )
        self.assertTrue(report["notification"]["success"])
        self.assertEqual(1, len(calls))
        payload = calls[0]["json"]
        self.assertEqual({"parse": []}, payload["allowed_mentions"])
        self.assertNotIn("example.invalid", json.dumps(report))

    def test_missing_webhook_is_reported_without_request(self) -> None:
        report = run_operations_monitor(
            self.root,
            self.config(notification_enabled=True),
            3,
            self.log_path,
            environment={},
        )
        self.assertFalse(report["notification"]["success"])
        self.assertFalse(report["notification"]["attempted"])
        self.assertIn("NOTIFICATION_FAILED", {item["code"] for item in report["alerts"]})


if __name__ == "__main__":
    unittest.main()
