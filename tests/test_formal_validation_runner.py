from __future__ import annotations

import unittest
from pathlib import Path

from phoenix_core.formal_validation_runner import FormalValidationRunner, _flatten_run_for_csv


ROOT = Path(__file__).resolve().parent.parent


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


if __name__ == "__main__":
    unittest.main()
