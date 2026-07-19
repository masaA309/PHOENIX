from __future__ import annotations

import unittest

from phoenix_core import OrderRequest, OrderSide, OrderType, PaperBroker
from phoenix_core.risk_controller import RiskConfig, RiskState, evaluate_orders


def make_order(ticker: str, price: float, cid: str) -> OrderRequest:
    return OrderRequest(
        ticker=ticker,
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=price,
        client_order_id=cid,
    )


class RiskControllerV7Test(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = PaperBroker(initial_cash_yen=300000)
        self.config = RiskConfig(
            max_daily_loss_pct=0.03,
            max_drawdown_pct=0.10,
            max_positions=3,
            max_total_invested_pct=0.80,
            max_single_position_pct=0.30,
            max_orders_per_run=2,
            max_consecutive_losses=3,
            minimum_cash_reserve_pct=0.10,
        )

    def test_approves_safe_order(self) -> None:
        report = evaluate_orders(
            self.broker,
            [make_order("9501.T", 500, "SAFE-1")],
            self.config,
            RiskState.new(300000),
        )
        self.assertEqual(1, len(report.accepted_orders))
        self.assertTrue(report.decisions[0].accepted)

    def test_blocks_daily_loss(self) -> None:
        state = RiskState.new(300000)
        state.start_of_day_equity_yen = 310000
        report = evaluate_orders(
            self.broker,
            [make_order("9501.T", 500, "LOSS-1")],
            self.config,
            state,
        )
        self.assertTrue(report.halted)
        self.assertEqual(0, len(report.accepted_orders))

    def test_blocks_too_many_orders(self) -> None:
        report = evaluate_orders(
            self.broker,
            [
                make_order("9501.T", 500, "M-1"),
                make_order("4902.T", 600, "M-2"),
                make_order("3697.T", 700, "M-3"),
            ],
            self.config,
            RiskState.new(300000),
        )
        self.assertEqual(2, len(report.accepted_orders))
        self.assertFalse(report.decisions[2].accepted)

    def test_blocks_single_position_limit(self) -> None:
        report = evaluate_orders(
            self.broker,
            [make_order("9984.T", 1000, "BIG-1")],
            self.config,
            RiskState.new(300000),
        )
        self.assertEqual(0, len(report.accepted_orders))
        self.assertIn("1銘柄", report.decisions[0].reason)


if __name__ == "__main__":
    unittest.main()
