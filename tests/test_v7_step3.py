from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from phoenix_core import (
    OrderRequest,
    OrderSide,
    OrderType,
    PaperBroker,
)
from phoenix_core.portfolio import (
    build_portfolio_summary,
    update_market_prices,
)


class PortfolioManagerV7Test(
    unittest.TestCase
):
    def test_portfolio_summary_from_broker(
        self,
    ) -> None:
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
                client_order_id="PORTFOLIO-001",
            )
        )
        broker.set_market_price(
            "4005.T",
            525,
        )

        payload = build_portfolio_summary(
            broker
        )

        self.assertEqual(
            250000,
            payload["account"]["cash_yen"],
        )
        self.assertEqual(
            52500,
            payload["account"]["market_value_yen"],
        )
        self.assertEqual(
            302500,
            payload["account"]["equity_yen"],
        )
        self.assertEqual(
            2500,
            payload["account"]["unrealized_pnl_yen"],
        )

    def test_update_prices_from_csv(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quote_file = root / "quotes.csv"

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
                    client_order_id="PORTFOLIO-002",
                )
            )

            pd.DataFrame(
                [
                    {
                        "symbol": "4005.T",
                        "price": 530,
                    }
                ]
            ).to_csv(
                quote_file,
                index=False,
            )

            count = update_market_prices(
                broker,
                quote_file,
            )
            snapshot = (
                broker.get_account_snapshot()
            )

            self.assertEqual(1, count)
            self.assertEqual(
                530,
                snapshot.positions[0].market_price,
            )


if __name__ == "__main__":
    unittest.main()
