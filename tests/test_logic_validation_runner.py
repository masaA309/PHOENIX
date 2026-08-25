from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from phoenix_core.logic_validation_runner import (
    ROOT,
    _base_settings,
    _build_dry_run_payload,
    _case_settings,
    _concentration_summary,
    build_case_specs,
)


BASE_CONFIG_PATH = Path("config/v7_historical_validation_risk_v2_quick.json")


class LogicValidationRunnerSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = build_case_specs()
        self.base_settings = {
            "slippage_rate": 0.0005,
            "market_breadth_bear_threshold": 0.4,
            "market_breadth_bear_max_total_invested_pct": 0.7,
            "benchmark_enabled": True,
            "initial_capital_yen": 500000,
            "lot_size": 100,
            "requested_start": "2022-02-01",
            "requested_end": "2026-08-14",
            "allow_network_fetch": False,
        }

    def test_case_matrix_has_expected_groups(self) -> None:
        self.assertEqual(13, len(self.cases))
        counts = Counter(case.group for case in self.cases)
        self.assertEqual({"A": 9, "B": 3, "C": 1}, dict(counts))
        self.assertEqual(9, sum(1 for case in self.cases if case.group == "A" and case.kind == "simulation"))
        self.assertEqual(3, sum(1 for case in self.cases if case.group == "B" and case.kind == "simulation"))
        self.assertEqual(1, sum(1 for case in self.cases if case.group == "C" and case.kind == "concentration"))

    def test_case_settings_apply_requested_parameters(self) -> None:
        a_case = next(
            case for case in self.cases if case.group == "A" and case.breadth_threshold == 0.35 and case.bear_cap == 0.65
        )
        a_settings = _case_settings(
            self.base_settings,
            a_case,
            Path("reports/logic_validation/runs/A_b35_c65"),
            "2022-02-01",
            "2026-08-14",
            0.0005,
        )
        self.assertTrue(a_settings["market_breadth_filter_enabled"])
        self.assertEqual(0.35, a_settings["market_breadth_bear_threshold"])
        self.assertEqual(0.65, a_settings["market_breadth_bear_max_total_invested_pct"])
        self.assertEqual(0.0005, a_settings["slippage_rate"])
        self.assertEqual("2022-02-01", a_settings["requested_start"])
        self.assertEqual("2026-08-14", a_settings["requested_end"])

        b_case = next(case for case in self.cases if case.group == "B" and case.slippage_multiplier == 2.0)
        b_settings = _case_settings(
            self.base_settings,
            b_case,
            Path("reports/logic_validation/runs/B_slip_2x"),
            "2022-02-01",
            "2026-08-14",
            0.0005,
        )
        self.assertTrue(b_settings["market_breadth_filter_enabled"])
        self.assertEqual(0.4, b_settings["market_breadth_bear_threshold"])
        self.assertEqual(0.7, b_settings["market_breadth_bear_max_total_invested_pct"])
        self.assertEqual(0.001, b_settings["slippage_rate"])

        c_case = next(case for case in self.cases if case.group == "C")
        c_settings = _case_settings(
            self.base_settings,
            c_case,
            Path("reports/logic_validation"),
            "2022-02-01",
            "2026-08-14",
            0.0005,
        )
        self.assertFalse(c_settings["market_breadth_filter_enabled"])
        self.assertEqual(0.0005, c_settings["slippage_rate"])

    def test_dry_run_payload_has_thirteen_planned_cases(self) -> None:
        base_settings, base_config_sha256 = _base_settings(ROOT, BASE_CONFIG_PATH)
        payload = _build_dry_run_payload(
            root=ROOT,
            base_config_path=BASE_CONFIG_PATH,
            base_config_sha256=base_config_sha256,
            base_settings=base_settings,
            requested_start="2022-02-01",
            requested_end="2026-08-14",
            cases=self.cases,
        )
        self.assertEqual("DRY_RUN", payload["status"])
        self.assertTrue(payload["checks"]["base_config_exists"])
        self.assertTrue(payload["checks"]["market_cache_dir_exists"])
        self.assertTrue(payload["checks"]["universe_csv_exists"])
        self.assertTrue(payload["checks"]["concentration_input_p1_exists"])
        self.assertTrue(payload["checks"]["concentration_input_p2_exists"])
        self.assertEqual(13, len(payload["planned_cases"]))
        counts = Counter(case["case_group"] for case in payload["planned_cases"])
        self.assertEqual({"A": 9, "B": 3, "C": 1}, dict(counts))


class LogicValidationRunnerConcentrationTest(unittest.TestCase):
    def test_concentration_summary_aggregates_only_existing_trade_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            p1 = root / "reports/formal_validation/runs/P1_ON/trades.csv"
            p2 = root / "reports/formal_validation/runs/P2_ON/trades.csv"
            p1.parent.mkdir(parents=True, exist_ok=True)
            p2.parent.mkdir(parents=True, exist_ok=True)

            pd.DataFrame(
                [
                    {"ticker": "AAA", "company_name": "Alpha", "profit_yen": 100},
                    {"ticker": "BBB", "company_name": "Beta", "profit_yen": -20},
                    {"ticker": "CCC", "company_name": "Gamma", "profit_yen": 30},
                ]
            ).to_csv(p1, index=False, encoding="utf-8-sig")
            pd.DataFrame(
                [
                    {"ticker": "AAA", "company_name": "Alpha", "profit_yen": 50},
                    {"ticker": "DDD", "company_name": "Delta", "profit_yen": 10},
                ]
            ).to_csv(p2, index=False, encoding="utf-8-sig")

            output_dir = root / "reports/logic_validation"
            record = _concentration_summary(root, output_dir)

            self.assertEqual("DONE", record["status"])
            self.assertEqual(170.0, record["metrics"]["total_profit_yen"])
            self.assertAlmostEqual(88.235294, record["metrics"]["top1_contribution_pct"], places=6)
            self.assertEqual(100.0, record["metrics"]["top5_contribution_pct"])
            self.assertEqual(100.0, record["metrics"]["top10_contribution_pct"])
            self.assertEqual(20.0, record["metrics"]["top1_profit_excluding_yen"])
            self.assertEqual(0.0, record["metrics"]["top5_profit_excluding_yen"])
            self.assertEqual(0.0, record["metrics"]["top10_profit_excluding_yen"])
            self.assertEqual(3, record["metrics"]["profitable_ticker_count"])
            self.assertEqual(1, record["metrics"]["losing_ticker_count"])
            summary_path = root / record["summary_json"]
            summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual("AAA", summary_data["ticker_profit_rows"][0]["ticker"])
            self.assertTrue((output_dir / "concentration_summary.json").is_file())
            self.assertTrue((output_dir / "concentration_report.txt").is_file())
            self.assertTrue((output_dir / "ticker_profit.csv").is_file())


if __name__ == "__main__":
    unittest.main()
