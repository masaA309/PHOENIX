from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from phoenix_core.formal_validation_runner import (
    FormalValidationRunner,
    _comparison_rows_from_run_rows,
    _flatten_run_for_csv,
    evaluate_formal_validation_acceptance,
)


ROOT = Path(__file__).resolve().parent.parent


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _criteria() -> dict:
    return {
        "schema_version": 1,
        "version": "PHOENIX Formal Validation Acceptance Criteria",
        "hard_gates": {
            "required_run_names": ["P1_OFF", "P1_ON", "P2_OFF", "P2_ON"],
            "aggregate_status": "SUCCESS",
            "run_status": "DONE",
            "run_summary_status": "SUCCESS",
            "require_report_consistency": True,
            "require_manifest_binding": True,
            "require_no_zero_byte_outputs": True,
            "require_no_non_finite_values": True,
            "forbid_old_namespace_contamination": True,
        },
        "safety_gates": {
            "allow_network_fetch": False,
            "no_rss": True,
            "no_real_orders": True,
            "orders_submitted": 0,
            "live_trading_enabled": False,
            "paper_maintained": True,
            "bridge_armed": False,
        },
        "performance_policy": {
            "outcome_mode": "separate",
            "delta_definition": "ON_MINUS_OFF",
            "pairs": [
                {"name": "P1", "off_run": "P1_OFF", "on_run": "P1_ON"},
                {"name": "P2", "off_run": "P2_OFF", "on_run": "P2_ON"},
            ],
            "metrics": {
                "cagr_delta_pct": {"operator": ">", "threshold": 0},
                "final_equity_delta_yen": {"operator": ">", "threshold": 0},
                "profit_factor_delta": {"operator": ">=", "threshold": 0},
                "max_drawdown_delta_pct": {
                    "operator": "<=",
                    "threshold": 2.0,
                    "positive_delta_means": "deterioration",
                },
                "trade_count_delta": {"informational_only": True},
            },
        },
        "closure_policy": {
            "requires_execution_success": True,
            "requires_artifact_acceptance": True,
            "requires_safety_acceptance": True,
            "requires_all_performance_outcomes_pass": True,
        },
    }


def _run_row(name: str, *, cagr: float, equity: float, profit_factor: float, drawdown: float, trades: int) -> dict:
    return {
        "schema_version": 1,
        "version": "PHOENIX Formal Validation 20Y",
        "generated_at": "2026-09-03T00:00:00+09:00",
        "run_name": name,
        "requested_start": "2020-01-01",
        "requested_end": "2020-12-31",
        "market_breadth_filter_enabled": name.endswith("_ON"),
        "status": "DONE",
        "resume_skipped": False,
        "input_manifest_sha256": "input-sha",
        "run_spec_sha256": f"{name}-spec-sha",
        "run_identity_sha256": f"{name}-identity-sha",
        "performance": {
            "cagr_pct": cagr,
            "final_equity_yen": equity,
            "profit_factor": profit_factor,
            "max_drawdown_pct": drawdown,
            "trade_count": trades,
        },
        "formal_validation": {
            "membership_ticker_count": 1,
            "cache_csv_ticker_count": 1,
            "simulation_ticker_count": 1,
            "excluded_cache_ticker_count": 0,
        },
        "output_files": {},
        "error": None,
    }


def _write_acceptance_fixture(root: Path, criteria: dict, run_rows: list[dict]) -> tuple[Path, Path]:
    config_dir = root / "config"
    output_dir = root / "reports" / "formal_validation_case"
    spec_path = config_dir / "formal_validation_runs_case.json"
    criteria_path = config_dir / "formal_validation_acceptance_criteria.json"
    _write_json(
        spec_path,
        {
            "schema_version": 1,
            "base_config_path": "config/base.json",
            "output_dir": "reports/formal_validation_case",
            "cache_dir": "data/market_cache",
            "universe_csv": "data/universe.csv",
            "allow_network_fetch": False,
            "stop_on_fail": True,
            "runs": [
                {
                    "name": row["run_name"],
                    "requested_start": row["requested_start"],
                    "requested_end": row["requested_end"],
                    "market_breadth_filter_enabled": row["market_breadth_filter_enabled"],
                }
                for row in run_rows
            ],
        },
    )
    _write_json(criteria_path, criteria)
    _write_json(output_dir / "input_manifest.json", {"schema_version": 1, "input_manifest_sha256": "input-sha"})
    _write_json(output_dir / "dry_run.json", {"schema_version": 1, "status": "DRY_RUN", "input_manifest_sha256": "input-sha"})
    for row in run_rows:
        run_dir = output_dir / "runs" / row["run_name"]
        output_file = run_dir / "trades.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("ticker,qty\n7203,100\n", encoding="utf-8")
        run_summary = dict(row)
        run_summary["status"] = "SUCCESS"
        run_summary["safety"] = {
            "no_rss": True,
            "no_real_orders": True,
            "orders_submitted": 0,
            "live_trading_enabled": False,
        }
        run_summary["output_files"] = {"trades_csv": str(output_file)}
        _write_json(run_dir / "summary.json", run_summary)
        _write_json(
            run_dir / "manifest.json",
            {
                "schema_version": 1,
                "run_name": row["run_name"],
                "run_spec_sha256": row["run_spec_sha256"],
                "input_manifest_sha256": row["input_manifest_sha256"],
                "run_identity_sha256": row["run_identity_sha256"],
                "status": "DONE",
            },
        )
        row["output_files"] = {"trades_csv": str(output_file)}
    summary = {
        "schema_version": 1,
        "version": "PHOENIX Formal Validation 20Y",
        "generated_at": "2026-09-03T00:00:00+09:00",
        "status": "SUCCESS",
        "input_manifest_sha256": "input-sha",
        "output_dir": "reports/formal_validation_case",
        "run_count": len(run_rows),
        "runs": run_rows,
        "comparisons": _comparison_rows_from_run_rows(run_rows),
        "warnings": [],
    }
    _write_json(output_dir / "summary.json", summary)
    (output_dir / "summary.csv").write_text(
        "run_name,status,resume_skipped,requested_start,requested_end,risk_v2_enabled,input_manifest_sha256,run_spec_sha256,run_identity_sha256,final_equity_yen,total_return_pct,cagr_pct,profit_factor,expectancy_per_trade_yen,max_drawdown_pct,win_rate_pct,trade_count,avg_holding_sessions,avg_cash_yen,max_consecutive_losses,longest_underwater_sessions,recovery_factor,rejected_due_to_lot,rejected_due_to_buying_power,membership_ticker_count,cache_csv_ticker_count,simulation_ticker_count,excluded_cache_ticker_count,summary_json,report_text,run_log\n"
        + "\n".join(
            f"{row['run_name']},{row['status']},False,{row['requested_start']},{row['requested_end']},{row['market_breadth_filter_enabled']},input-sha,{row['run_spec_sha256']},{row['run_identity_sha256']},{row['performance']['final_equity_yen']},,{row['performance']['cagr_pct']},{row['performance']['profit_factor']},,{row['performance']['max_drawdown_pct']},,{row['performance']['trade_count']},,,,,,,,,,,,,,"
            for row in run_rows
        )
        + "\n",
        encoding="utf-8-sig",
    )
    report_lines = [
        "PHOENIX FORMAL VALIDATION SUMMARY",
        "Status             : SUCCESS",
        "Input manifest SHA  : input-sha",
        "Output dir         : reports/formal_validation_case",
    ]
    for row in run_rows:
        report_lines.append(f"{row['run_name']} | DONE | resume_skipped=False")
    for comparison in summary["comparisons"]:
        report_lines.append(comparison["pair_name"])
    (output_dir / "report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return spec_path, criteria_path


class FormalValidationRunnerComparisonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = FormalValidationRunner(root=ROOT)

    def test_comparisons_and_csv_use_nested_performance(self) -> None:
        run_rows = [
            {
                "run_name": "P1_OFF",
                "status": "DONE",
                "performance": {
                    "final_equity_yen": 561859.05,
                    "cagr_pct": 2.625344,
                    "profit_factor": 1.044197,
                    "max_drawdown_pct": 36.622468,
                    "trade_count": 953,
                },
            },
            {
                "run_name": "P1_ON",
                "status": "DONE",
                "performance": {
                    "final_equity_yen": 582323.95,
                    "cagr_pct": 3.4443,
                    "profit_factor": 1.068604,
                    "max_drawdown_pct": 25.998596,
                    "trade_count": 887,
                },
            },
            {
                "run_name": "P2_OFF",
                "status": "DONE",
                "performance": {
                    "final_equity_yen": 1416343.11,
                    "cagr_pct": 25.833965,
                    "profit_factor": 1.432818,
                    "max_drawdown_pct": 11.58191,
                    "trade_count": 986,
                },
            },
            {
                "run_name": "P2_ON",
                "status": "DONE",
                "performance": {
                    "final_equity_yen": 1687506.03,
                    "cagr_pct": 30.793949,
                    "profit_factor": 1.521081,
                    "max_drawdown_pct": 12.512026,
                    "trade_count": 1009,
                },
            },
        ]

        summary = self.runner._summary_from_run_rows("manifest-sha", run_rows)
        self.assertEqual(
            [
                {
                    "pair_name": "P1_ON - P1_OFF",
                    "left_run": "P1_OFF",
                    "right_run": "P1_ON",
                    "final_equity_delta_yen": 20464.9,
                    "cagr_delta_pct": 0.818956,
                    "profit_factor_delta": 0.024407,
                    "max_drawdown_delta_pct": -10.623872,
                    "trade_count_delta": -66,
                },
                {
                    "pair_name": "P2_ON - P2_OFF",
                    "left_run": "P2_OFF",
                    "right_run": "P2_ON",
                    "final_equity_delta_yen": 271162.92,
                    "cagr_delta_pct": 4.959984,
                    "profit_factor_delta": 0.088263,
                    "max_drawdown_delta_pct": 0.930116,
                    "trade_count_delta": 23,
                },
            ],
            summary["comparisons"],
        )

        csv_row = _flatten_run_for_csv(run_rows[0])
        self.assertEqual(561859.05, csv_row["final_equity_yen"])
        self.assertEqual(2.625344, csv_row["cagr_pct"])
        self.assertEqual(1.044197, csv_row["profit_factor"])
        self.assertEqual(36.622468, csv_row["max_drawdown_pct"])
        self.assertEqual(953, csv_row["trade_count"])


class FormalValidationAcceptanceCriteriaTest(unittest.TestCase):
    def _evaluate(self, run_rows: list[dict], criteria: dict | None = None) -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            spec_path, criteria_path = _write_acceptance_fixture(root, criteria or _criteria(), run_rows)
            return evaluate_formal_validation_acceptance(
                root=root,
                spec_path=spec_path,
                criteria_path=criteria_path,
            )

    def _passing_rows(self) -> list[dict]:
        return [
            _run_row("P1_OFF", cagr=1.0, equity=100.0, profit_factor=1.00, drawdown=10.0, trades=10),
            _run_row("P1_ON", cagr=1.1, equity=101.0, profit_factor=1.00, drawdown=12.0, trades=1),
            _run_row("P2_OFF", cagr=2.0, equity=200.0, profit_factor=1.10, drawdown=20.0, trades=20),
            _run_row("P2_ON", cagr=3.0, equity=300.0, profit_factor=1.20, drawdown=19.0, trades=40),
        ]

    def _acceptance_outcome(self, report: dict, name: str) -> dict:
        return next(row for row in report["outcomes"] if row["name"] == name)

    def test_acceptance_passes_when_all_hard_safety_and_performance_gates_pass(self) -> None:
        report = self._evaluate(self._passing_rows())

        self.assertEqual("PASS", report["status"])
        self.assertTrue(report["formal_validation_closed"])
        self.assertTrue(report["execution_success"])
        self.assertTrue(report["artifact_acceptance"])
        self.assertTrue(report["safety_acceptance"])
        self.assertTrue(report["performance_acceptance"])
        self.assertEqual("PASS", self._acceptance_outcome(report, "P1")["status"])
        self.assertEqual("PASS", self._acceptance_outcome(report, "P2")["status"])

    def test_cagr_delta_zero_fails(self) -> None:
        rows = self._passing_rows()
        rows[1]["performance"]["cagr_pct"] = rows[0]["performance"]["cagr_pct"]

        report = self._evaluate(rows)

        self.assertEqual("FAIL", report["status"])
        self.assertFalse(report["formal_validation_closed"])
        self.assertEqual("FAIL", self._acceptance_outcome(report, "P1")["metric_results"]["cagr_delta_pct"]["status"])

    def test_final_equity_delta_zero_fails(self) -> None:
        rows = self._passing_rows()
        rows[1]["performance"]["final_equity_yen"] = rows[0]["performance"]["final_equity_yen"]

        report = self._evaluate(rows)

        self.assertEqual("FAIL", report["status"])
        self.assertEqual("FAIL", self._acceptance_outcome(report, "P1")["metric_results"]["final_equity_delta_yen"]["status"])

    def test_profit_factor_zero_passes_and_negative_fails(self) -> None:
        rows = self._passing_rows()
        rows[1]["performance"]["profit_factor"] = rows[0]["performance"]["profit_factor"]

        zero_report = self._evaluate(rows)

        self.assertEqual("PASS", self._acceptance_outcome(zero_report, "P1")["metric_results"]["profit_factor_delta"]["status"])

        rows = self._passing_rows()
        rows[1]["performance"]["profit_factor"] = rows[0]["performance"]["profit_factor"] - 0.01
        negative_report = self._evaluate(rows)

        self.assertEqual("FAIL", negative_report["status"])
        self.assertEqual("FAIL", self._acceptance_outcome(negative_report, "P1")["metric_results"]["profit_factor_delta"]["status"])

    def test_max_drawdown_two_points_passes_over_two_fails_and_negative_passes(self) -> None:
        rows = self._passing_rows()
        rows[1]["performance"]["max_drawdown_pct"] = rows[0]["performance"]["max_drawdown_pct"] + 2.0
        boundary_report = self._evaluate(rows)

        self.assertEqual("PASS", self._acceptance_outcome(boundary_report, "P1")["metric_results"]["max_drawdown_delta_pct"]["status"])

        rows = self._passing_rows()
        rows[1]["performance"]["max_drawdown_pct"] = rows[0]["performance"]["max_drawdown_pct"] + 2.0001
        failed_report = self._evaluate(rows)

        self.assertEqual("FAIL", failed_report["status"])
        self.assertEqual("FAIL", self._acceptance_outcome(failed_report, "P1")["metric_results"]["max_drawdown_delta_pct"]["status"])

        rows = self._passing_rows()
        rows[1]["performance"]["max_drawdown_pct"] = rows[0]["performance"]["max_drawdown_pct"] - 1.0
        improved_report = self._evaluate(rows)

        self.assertEqual("PASS", self._acceptance_outcome(improved_report, "P1")["metric_results"]["max_drawdown_delta_pct"]["status"])

    def test_trade_count_delta_is_informational_only(self) -> None:
        rows = self._passing_rows()
        rows[1]["performance"]["trade_count"] = rows[0]["performance"]["trade_count"] - 999

        report = self._evaluate(rows)

        self.assertEqual("PASS", report["status"])
        self.assertEqual("PASS", self._acceptance_outcome(report, "P1")["metric_results"]["trade_count_delta"]["status"])

    def test_p1_pass_and_p2_fail_keeps_formal_validation_open(self) -> None:
        rows = self._passing_rows()
        rows[3]["performance"]["cagr_pct"] = rows[2]["performance"]["cagr_pct"]

        report = self._evaluate(rows)

        self.assertEqual("PASS", self._acceptance_outcome(report, "P1")["status"])
        self.assertEqual("FAIL", self._acceptance_outcome(report, "P2")["status"])
        self.assertFalse(report["formal_validation_closed"])

    def test_hard_gate_failure_keeps_formal_validation_open(self) -> None:
        rows = self._passing_rows()
        rows[0]["status"] = "FAILED"

        report = self._evaluate(rows)

        self.assertEqual("FAIL", report["status"])
        self.assertFalse(report["formal_validation_closed"])
        self.assertFalse(report["artifact_acceptance"])

    def test_invalid_criteria_fail_closed(self) -> None:
        criteria = _criteria()
        del criteria["performance_policy"]["metrics"]["cagr_delta_pct"]

        report = self._evaluate(self._passing_rows(), criteria)

        self.assertEqual("FAIL", report["status"])
        self.assertFalse(report["formal_validation_closed"])
        self.assertIn("missing metric cagr_delta_pct", report["error"])

    def test_p1_and_p2_are_not_mixed(self) -> None:
        rows = self._passing_rows()
        rows[1]["performance"]["cagr_pct"] = rows[0]["performance"]["cagr_pct"]
        rows[3]["performance"]["cagr_pct"] = rows[2]["performance"]["cagr_pct"] + 10.0

        report = self._evaluate(rows)

        self.assertEqual("FAIL", self._acceptance_outcome(report, "P1")["status"])
        self.assertEqual("PASS", self._acceptance_outcome(report, "P2")["status"])

    def test_20260903_artifact_acceptance_passes_without_rerunning_validation(self) -> None:
        report = evaluate_formal_validation_acceptance(
            root=ROOT,
            spec_path="config/formal_validation_runs_20260903.json",
            criteria_path="config/formal_validation_acceptance_criteria.json",
        )

        self.assertEqual("PASS", report["status"])
        self.assertTrue(report["formal_validation_closed"])
        p1 = self._acceptance_outcome(report, "P1")["metric_results"]
        p2 = self._acceptance_outcome(report, "P2")["metric_results"]
        self.assertEqual(0.818956, p1["cagr_delta_pct"]["delta"])
        self.assertEqual(20464.9, p1["final_equity_delta_yen"]["delta"])
        self.assertEqual(-10.623872, p1["max_drawdown_delta_pct"]["delta"])
        self.assertEqual(0.024407, p1["profit_factor_delta"]["delta"])
        self.assertEqual(-66.0, p1["trade_count_delta"]["delta"])
        self.assertEqual(4.959984, p2["cagr_delta_pct"]["delta"])
        self.assertEqual(271162.92, p2["final_equity_delta_yen"]["delta"])
        self.assertEqual(0.930116, p2["max_drawdown_delta_pct"]["delta"])
        self.assertEqual(0.088263, p2["profit_factor_delta"]["delta"])
        self.assertEqual(23.0, p2["trade_count_delta"]["delta"])


if __name__ == "__main__":
    unittest.main()
