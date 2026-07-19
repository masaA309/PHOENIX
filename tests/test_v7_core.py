from __future__ import annotations

import unittest

from phoenix_core import (
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperBroker,
)


class PaperBrokerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = PaperBroker(initial_cash_yen=300_000)

    def test_buy_and_sell(self) -> None:
        buy = self.broker.submit_order(
            OrderRequest(
                ticker="9501.T",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
                limit_price=500,
                client_order_id="TEST-BUY-001",
            )
        )
        self.assertEqual(OrderStatus.FILLED, buy.status)

        sell = self.broker.submit_order(
            OrderRequest(
                ticker="9501.T",
                side=OrderSide.SELL,
                quantity=100,
                order_type=OrderType.LIMIT,
                limit_price=520,
                client_order_id="TEST-SELL-001",
            )
        )
        self.assertEqual(OrderStatus.FILLED, sell.status)

        snapshot = self.broker.get_account_snapshot()
        self.assertEqual(302_000, snapshot.cash_yen)
        self.assertEqual(2_000, snapshot.realized_pnl_yen)
        self.assertEqual(0, len(snapshot.positions))

    def test_rejects_insufficient_cash(self) -> None:
        result = self.broker.submit_order(
            OrderRequest(
                ticker="1605.T",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
                limit_price=3_500,
                client_order_id="TEST-BUY-002",
            )
        )
        self.assertEqual(OrderStatus.REJECTED, result.status)

    def test_rejects_duplicate_client_order_id(self) -> None:
        order = OrderRequest(
            ticker="9501.T",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=500,
            client_order_id="TEST-DUPLICATE-001",
        )
        first = self.broker.submit_order(order)
        second = self.broker.submit_order(order)

        self.assertEqual(OrderStatus.FILLED, first.status)
        self.assertEqual(OrderStatus.REJECTED, second.status)


if __name__ == "__main__":
    unittest.main()
