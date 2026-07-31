from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from phoenix_core.readiness_gate import build_readiness_report, read_json, run_readiness_gate


def inputs(runs: int = 20, days: int = 20, success: float = 1.0, filled: int = 3):
    performance = {
        "run_count": runs,
        "paper_evidence": {
            "integrity_status": "VERIFIED",
            "eligibility_rule": "dry_run == false",
            "eligible_run_count": runs,
            "distinct_run_days": days,
            "success_rate": success,
            "status_counts": {"FAILED": 0},
            "totals": {"filled": filled},
            "risk_halt_count": 0,
        },
    }
    return performance, {"status": "SUCCESS", "dry_run": False}, {"status": "READY"}, {"action_counts": {"REVIEW": 0}}


def valid_historical():
    return {
        "gate_status": "READY",
        "execution_status": "COMPLETED",
        "evidence_kind": "HISTORICAL_WALK_FORWARD_REPLAY",
        "evidence_sha256": "a" * 64,
        "data_contract_status": "READY",
        "risk_limits_unchanged": True,
        "input_files_unchanged": True,
        "state_integrity_status": "READY",
        "post_save_integrity_status": "READY",
        "historical_evidence_verified": True,
        "replay_scope": "PRODUCTION_DECISION_PIPELINE",
        "sealed_holdout_status": "READY",
        "execution_model_status": "READY",
        "paper_days_credited": 0,
        "audited_fills_credited": 0,
        "external_orders_submitted": 0,
        "live_trading_enabled": False,
        "automatic_promotion": False,
    }


class ReadinessGateStep14Test(unittest.TestCase):
    def test_ready_when_every_check_passes(self):
        report = build_readiness_report(
            *inputs(),
            {"minimum_paper_days": 20, "minimum_success_rate": .95, "minimum_filled_orders": 3},
            historical=valid_historical(),
        )
        self.assertEqual("READY", report["status"])
        self.assertTrue(report["paper_to_live_eligible"])
        self.assertFalse(report["live_trading_enabled"])

    def test_historical_gate_cannot_be_omitted(self):
        report = build_readiness_report(*inputs(), {"minimum_paper_days": 20})
        item = next(
            value for value in report["checks"]
            if value["name"] == "historical_replay_gate"
        )
        self.assertFalse(item["passed"])
        self.assertEqual("NOT_READY", report["status"])

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
        values[0]["paper_evidence"]["status_counts"]["FAILED"] = 1
        report = build_readiness_report(*values, {})
        self.assertEqual("NOT_READY", report["status"])

    def test_missing_paper_evidence_fails_closed(self):
        values = list(inputs())
        values[0].pop("paper_evidence")
        report = build_readiness_report(*values, {})
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "paper_evidence")["passed"])

    def test_latest_dry_run_cannot_satisfy_gate(self):
        values = list(inputs())
        values[1]["dry_run"] = True
        report = build_readiness_report(*values, {})
        self.assertFalse(next(item for item in report["checks"] if item["name"] == "latest_paper_operation")["passed"])

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
            (root / "reports/lifecycle.json").write_text(json.dumps({"status": "READY", "state_persisted": True, "audited_fill_count": 3}), encoding="utf-8")
            config = {"readiness_gate": {"performance_report": "reports/performance.json", "operations_report": "reports/operations.json", "market_data_report": "reports/market.json", "portfolio_report": "reports/portfolio.json", "lifecycle_report": "reports/lifecycle.json", "report_json": "reports/gate.json", "report_text": "reports/gate.txt"}}
            report = run_readiness_gate(root, config)
            self.assertTrue(Path(report["report_json"]).is_file())
            self.assertTrue(Path(report["report_text"]).is_file())
            self.assertEqual("NOT_READY", report["status"])
            self.assertTrue(
                any("Historical replay" in value for value in report["load_errors"])
            )

if __name__ == "__main__": unittest.main()
