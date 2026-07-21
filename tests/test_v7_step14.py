from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from phoenix_core.readiness_gate import build_readiness_report, read_json, run_readiness_gate


def inputs(runs: int = 20, days: int = 20, success: float = 1.0, filled: int = 3):
    performance = {"run_count": runs, "distinct_run_days": days, "success_rate": success, "status_counts": {"FAILED": 0}, "totals": {"filled": filled}, "risk_halt_count": 0}
    return performance, {"status": "SUCCESS"}, {"status": "READY"}, {"action_counts": {"REVIEW": 0}}


class ReadinessGateStep14Test(unittest.TestCase):
    def test_ready_when_every_check_passes(self):
        report = build_readiness_report(*inputs(), {"minimum_paper_days": 20, "minimum_success_rate": .95, "minimum_filled_orders": 3})
        self.assertEqual("READY", report["status"])
        self.assertTrue(report["paper_to_live_eligible"])
        self.assertFalse(report["live_trading_enabled"])

    def test_too_few_runs_blocks(self):
        report = build_readiness_report(*inputs(runs=100, days=5), {"minimum_paper_days": 20})
        self.assertEqual("NOT_READY", report["status"])

    def test_repeated_runs_on_one_day_do_not_satisfy_gate(self):
        report = build_readiness_report(*inputs(runs=100, days=1), {"minimum_paper_days": 20})
        item = next(value for value in report["checks"] if value["name"] == "paper_days")
        self.assertFalse(item["passed"])

    def test_no_fills_blocks(self):
        report = build_readiness_report(*inputs(filled=0), {"minimum_filled_orders": 3})
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "filled_orders")["passed"])

    def test_stale_market_data_blocks(self):
        values = list(inputs())
        values[2] = {"status": "WARNING"}
        report = build_readiness_report(*values, {})
        self.assertEqual("NOT_READY", report["status"])

    def test_failed_run_blocks(self):
        values = list(inputs())
        values[0]["status_counts"]["FAILED"] = 1
        report = build_readiness_report(*values, {})
        self.assertEqual("NOT_READY", report["status"])

    def test_load_error_blocks(self):
        report = build_readiness_report(*inputs(), {}, ["missing report"])
        self.assertEqual("NOT_READY", report["status"])
        self.assertIn("missing report", report["blocking_reasons"])

    def test_invalid_json_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.json"
            path.write_text("bad", encoding="utf-8")
            _, error = read_json(path)
            self.assertIsNotNone(error)

    def test_run_creates_reports(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "reports").mkdir()
            performance, operations, market, portfolio = inputs()
            for name, value in (("performance", performance), ("operations", operations), ("market", market), ("portfolio", portfolio)):
                (root / f"reports/{name}.json").write_text(json.dumps(value), encoding="utf-8")
            config = {"readiness_gate": {"performance_report": "reports/performance.json", "operations_report": "reports/operations.json", "market_data_report": "reports/market.json", "portfolio_report": "reports/portfolio.json", "report_json": "reports/gate.json", "report_text": "reports/gate.txt"}}
            report = run_readiness_gate(root, config)
            self.assertTrue(Path(report["report_json"]).is_file())
            self.assertTrue(Path(report["report_text"]).is_file())

if __name__ == "__main__": unittest.main()
