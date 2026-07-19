from __future__ import annotations

from phoenix_core import (
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperBroker,
)


def main() -> None:
    broker = PaperBroker(
        initial_cash_yen=300_000,
        commission_rate=0.0,
    )

    health = broker.health_check()
    assert health.healthy is True
    assert health.live_trading_enabled is False

    buy = broker.submit_order(
        OrderRequest(
            ticker="9501.T",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=500.0,
            client_order_id="VERIFY-BUY-001",
        )
    )
    assert buy.status is OrderStatus.FILLED

    duplicate = broker.submit_order(
        OrderRequest(
            ticker="9501.T",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=500.0,
            client_order_id="VERIFY-BUY-001",
        )
    )
    assert duplicate.status is OrderStatus.REJECTED

    too_expensive = broker.submit_order(
        OrderRequest(
            ticker="1605.T",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=3_500.0,
            client_order_id="VERIFY-BUY-002",
        )
    )
    assert too_expensive.status is OrderStatus.REJECTED

    broker.set_market_price("9501.T", 520.0)

    before_sell = broker.get_account_snapshot()
    assert before_sell.cash_yen == 250_000.0
    assert before_sell.market_value_yen == 52_000.0
    assert before_sell.equity_yen == 302_000.0
    assert before_sell.unrealized_pnl_yen == 2_000.0

    sell = broker.submit_order(
        OrderRequest(
            ticker="9501.T",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=520.0,
            client_order_id="VERIFY-SELL-001",
        )
    )
    assert sell.status is OrderStatus.FILLED

    after_sell = broker.get_account_snapshot()
    assert after_sell.cash_yen == 302_000.0
    assert after_sell.equity_yen == 302_000.0
    assert after_sell.realized_pnl_yen == 2_000.0
    assert len(after_sell.positions) == 0

    print("=" * 80)
    print("PHOENIX v7 CORE STEP1 VERIFY")
    print("=" * 80)
    print(f"Broker          : {broker.broker_name}")
    print(f"Health          : {'PASS' if health.healthy else 'FAIL'}")
    print(f"実売買          : {'有効' if health.live_trading_enabled else '無効'}")
    print(f"買付検証        : {buy.status.value}")
    print(f"二重発注防止    : {duplicate.status.value}")
    print(f"余力不足拒否    : {too_expensive.status.value}")
    print(f"売却検証        : {sell.status.value}")
    print(f"最終資産        : {after_sell.equity_yen:,.0f}円")
    print(f"確定損益        : {after_sell.realized_pnl_yen:+,.0f}円")
    print("=" * 80)
    print("PHOENIX v7 Broker Adapter基礎検証: PASS")


if __name__ == "__main__":
    main()
