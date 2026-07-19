from __future__ import annotations

import unittest

from phoenix_core import (
    OrderRequest,
    OrderSide,
    OrderType,
    PaperBroker,
)
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    build_order_requests,
    calculate_sizing,
)


class PositionSizerV7Test(unittest.TestCase):
    def setUp(self) -> None:
        self.config = PositionSizingConfig(
            risk_per_trade_pct=0.01,
            max_position_pct=0.30,
            max_total_invested_pct=0.80,
            minimum_cash_reserve_pct=0.10,
            fallback_stop_distance_pct=0.03,
            lot_size=100,
            maximum_quantity_per_ticker=1000,
            allow_pyramiding=False,
            commission_buffer_pct=0.001,
        )

    def test_risk_based_quantity(self) -> None:
        broker = PaperBroker(
            initial_cash_yen=300000
        )
        decision = calculate_sizing(
            snapshot=broker.get_account_snapshot(),
            ticker="9501.T",
            name="東京電力",
            entry_price=500,
            stop_price=485,
            ranking_score=90,
            config=self.config,
        )

        self.assertEqual(
            100,
            decision.recommended_quantity,
        )
        self.assertEqual(
            50000,
            decision.estimated_cost_yen,
        )
        self.assertEqual(
            1500,
            decision.estimated_risk_yen,
        )
        self.assertEqual(
            "READY",
            decision.status,
        )

    def test_existing_position_is_skipped(self) -> None:
        broker = PaperBroker(
            initial_cash_yen=300000
        )
        broker.submit_order(
            OrderRequest(
                ticker="4005.T",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
                limit_price=500,
                client_order_id="HELD-001",
            )
        )

        decision = calculate_sizing(
            snapshot=broker.get_account_snapshot(),
            ticker="4005.T",
            name="住友化学",
            entry_price=520,
            stop_price=500,
            ranking_score=80,
            config=self.config,
        )

        self.assertEqual(
            0,
            decision.recommended_quantity,
        )
        self.assertEqual(
            "SKIP",
            decision.status,
        )

    def test_expensive_stock_is_skipped(self) -> None:
        broker = PaperBroker(
            initial_cash_yen=300000
        )
        decision = calculate_sizing(
            snapshot=broker.get_account_snapshot(),
            ticker="9984.T",
            name="ソフトバンクG",
            entry_price=5500,
            stop_price=5300,
            ranking_score=70,
            config=self.config,
        )

        self.assertEqual(
            0,
            decision.recommended_quantity,
        )
        self.assertEqual(
            "SKIP",
            decision.status,
        )

    def test_order_request_generation(self) -> None:
        broker = PaperBroker(
            initial_cash_yen=300000
        )
        decision = calculate_sizing(
            snapshot=broker.get_account_snapshot(),
            ticker="9501.T",
            name="東京電力",
            entry_price=500,
            stop_price=485,
            ranking_score=90,
            config=self.config,
        )

        orders = build_order_requests(
            [decision],
            run_id="UNIT-TEST",
        )

        self.assertEqual(1, len(orders))
        self.assertEqual(
            100,
            orders[0].quantity,
        )
        self.assertEqual(
            "9501.T",
            orders[0].ticker,
        )

    def test_duplicate_and_alias_columns(self) -> None:
        from pathlib import Path
        import tempfile
        import pandas as pd

        from phoenix_core.position_sizer import (
            normalize_candidates,
        )

        with tempfile.TemporaryDirectory(
            prefix="phoenix_step4_alias_"
        ) as temp_name:
            csv_path = Path(temp_name) / "candidates.csv"

            frame = pd.DataFrame(
                [
                    {
                        "ticker": "9501.T",
                        "銘柄": "東京電力HD",
                        "エントリー価格": 480,
                        "現在値": 500,
                        "押し目価格": 490,
                        "損切り価格": 470,
                        "PortfolioScore": 88,
                    }
                ]
            )
            frame.to_csv(
                csv_path,
                index=False,
                encoding="utf-8-sig",
            )

            normalized = normalize_candidates(
                csv_path
            )

            self.assertEqual(1, len(normalized))
            self.assertEqual(
                "9501.T",
                normalized.loc[0, "ticker"],
            )
            self.assertEqual(
                480,
                normalized.loc[
                    0,
                    "エントリー価格",
                ],
            )
            self.assertEqual(
                470,
                normalized.loc[0, "損切価格"],
            )
            self.assertEqual(
                88,
                normalized.loc[0, "ランキング点"],
            )


if __name__ == "__main__":
    unittest.main()
