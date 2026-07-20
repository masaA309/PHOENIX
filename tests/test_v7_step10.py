from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from phoenix_core.performance_tracker import load_history, record_from_operations, summarize, update_performance


def report(run: str, status: str = "SUCCESS", candidates: int = 10, ready: int = 2, approved: int = 1, filled: int = 1) -> dict:
    return {
        "generated_at": run, "status": status, "return_code": 0, "dry_run": False,
        "log": {"path": f"logs/{run}.log"},
        "pipeline": {"candidate_count": candidates, "ready_count": ready, "approved_count": approved, "filled_count": filled, "halted": False},
        "alerts": [] if status == "SUCCESS" else [{"code": "TEST_ALERT"}],
    }


class PerformanceTrackerStep10Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {"performance": {"history_jsonl": "reports/history.jsonl", "summary_json": "reports/summary.json", "summary_text": "reports/summary.txt", "retention_runs": 3, "window_runs": 2}}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_record_extracts_safe_metrics(self) -> None:
        item = record_from_operations(report("2026-07-20T09:00:00"))
        self.assertEqual(10, item["candidate_count"])
        self.assertEqual(1, item["filled_count"])
        self.assertNotIn("notification", item)

    def test_summary_calculates_rates(self) -> None:
        items = [record_from_operations(report("a")), record_from_operations(report("b", "WARNING", 10, 0, 0, 0))]
        value = summarize(items, 30)
        self.assertEqual(0.5, value["success_rate"])
        self.assertEqual(0.1, value["conversion_rates"]["candidate_to_ready"])
        self.assertEqual(1.0, value["conversion_rates"]["approved_to_filled"])

    def test_update_creates_all_reports(self) -> None:
        summary = update_performance(self.root, self.config, report("2026-07-20T09:00:00"))
        self.assertEqual(1, summary["run_count"])
        self.assertTrue(Path(summary["history_path"]).is_file())
        self.assertTrue(Path(summary["summary_json"]).is_file())
        self.assertTrue(Path(summary["summary_text"]).is_file())

    def test_duplicate_last_run_is_not_added(self) -> None:
        value = report("2026-07-20T09:00:00")
        update_performance(self.root, self.config, value)
        update_performance(self.root, self.config, value)
        self.assertEqual(1, len(load_history(self.root / "reports/history.jsonl")))

    def test_retention_and_window_are_enforced(self) -> None:
        for index in range(5):
            update_performance(self.root, self.config, report(f"run-{index}", "FAILED" if index == 4 else "SUCCESS"))
        history = load_history(self.root / "reports/history.jsonl")
        summary = json.loads((self.root / "reports/summary.json").read_text(encoding="utf-8"))
        self.assertEqual(3, len(history))
        self.assertEqual(2, summary["run_count"])
        self.assertEqual(0.5, summary["success_rate"])

    def test_corrupt_history_fails_closed(self) -> None:
        path = self.root / "reports/history.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("not-json\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_history(path)


if __name__ == "__main__":
    unittest.main()
