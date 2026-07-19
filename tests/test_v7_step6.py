from __future__ import annotations

import unittest
import pandas as pd

from phoenix_core import PaperBroker
from phoenix_core.pipeline import run_direct_pipeline
from phoenix_core.position_sizer import PositionSizingConfig
from phoenix_core.risk_controller import RiskConfig, RiskState


class DirectPipelineV7Test(unittest.TestCase):
    def candidates(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"ticker": "9501.T", "銘柄": "東京電力HD", "エントリー価格": 500, "損切価格": 485, "ランキング点": 90},
            {"ticker": "4902.T", "銘柄": "コニカミノルタ", "エントリー価格": 600, "損切価格": 582, "ランキング点": 80},
        ])

    def test_direct_execution(self) -> None:
        broker = PaperBroker(initial_cash_yen=300000)
        result = run_direct_pipeline(
            broker,
            self.candidates(),
            PositionSizingConfig(),
            RiskConfig(max_orders_per_run=2),
            RiskState.new(300000),
            run_id="UNIT-DIRECT",
            execute_orders=True,
        )
        self.assertEqual(2, result.filled_count)
        self.assertEqual(2, len(broker.get_account_snapshot().positions))

    def test_dry_run_does_not_trade(self) -> None:
        broker = PaperBroker(initial_cash_yen=300000)
        result = run_direct_pipeline(
            broker,
            self.candidates(),
            PositionSizingConfig(),
            RiskConfig(max_orders_per_run=2),
            RiskState.new(300000),
            run_id="UNIT-DRY",
            execute_orders=False,
        )
        self.assertEqual(2, result.approved_count)
        self.assertEqual(0, result.filled_count)
        self.assertEqual(0, len(broker.get_account_snapshot().positions))

    def test_risk_rejection_prevents_execution(self) -> None:
        broker = PaperBroker(initial_cash_yen=300000)
        state = RiskState.new(300000)
        state.start_of_day_equity_yen = 310000
        result = run_direct_pipeline(
            broker,
            self.candidates(),
            PositionSizingConfig(),
            RiskConfig(max_daily_loss_pct=0.03),
            state,
            run_id="UNIT-HALT",
            execute_orders=True,
        )
        self.assertTrue(result.risk_report.halted)
        self.assertEqual(0, result.filled_count)
        self.assertEqual(0, len(broker.get_account_snapshot().positions))


if __name__ == "__main__":
    unittest.main()
