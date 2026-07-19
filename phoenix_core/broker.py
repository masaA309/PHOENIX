from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from uuid import uuid4

from phoenix_core.models import (
    AccountSnapshot,
    BrokerHealth,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
)


class BrokerAdapter(ABC):
    """
    証券会社固有処理をPHOENIX本体から分離するための共通インターフェース。

    将来の楽天証券接続は、このクラスと同じメソッドを持つ
    RakutenBrokerAdapterとして実装する。
    """

    @property
    @abstractmethod
    def broker_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> BrokerHealth:
        raise NotImplementedError

    @abstractmethod
    def get_account_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError


@dataclass(slots=True)
class _MutablePosition:
    quantity: int
    average_price: float
    market_price: float


class PaperBroker(BrokerAdapter):
    """
    PHOENIX v7の共通Broker Adapterを検証するための仮想証券会社。

    Step1では以下を固定する。
    - 現物のみ
    - 指値のみ
    - 信用取引なし
    - 空売りなし
    - 注文価格で即時約定
    - 同じclient_order_idの二重発注を拒否
    """

    def __init__(
        self,
        initial_cash_yen: float = 300_000.0,
        commission_rate: float = 0.0,
    ) -> None:
        if initial_cash_yen < 0:
            raise ValueError("initial_cash_yenは0以上にしてください")

        if commission_rate < 0:
            raise ValueError("commission_rateは0以上にしてください")

        self._cash_yen = round(float(initial_cash_yen), 2)
        self._commission_rate = float(commission_rate)
        self._positions: dict[str, _MutablePosition] = {}
        self._realized_pnl_yen = 0.0
        self._processed_client_order_ids: set[str] = set()
        self._lock = RLock()

    @property
    def broker_name(self) -> str:
        return "PAPER"

    def health_check(self) -> BrokerHealth:
        return BrokerHealth(
            broker_name=self.broker_name,
            healthy=True,
            live_trading_enabled=False,
            message="Paper Broker正常。実売買は無効です。",
            checked_at=datetime.now(),
        )

    def set_market_price(
        self,
        ticker: str,
        market_price: float,
    ) -> None:
        normalized_ticker = ticker.strip().upper()

        if not normalized_ticker:
            raise ValueError("tickerが空です")

        if market_price <= 0:
            raise ValueError("market_priceは0より大きい値にしてください")

        with self._lock:
            position = self._positions.get(normalized_ticker)

            if position is not None:
                position.market_price = round(float(market_price), 2)

    def get_account_snapshot(self) -> AccountSnapshot:
        with self._lock:
            positions = tuple(
                Position(
                    ticker=ticker,
                    quantity=position.quantity,
                    average_price=position.average_price,
                    market_price=position.market_price,
                )
                for ticker, position in sorted(self._positions.items())
                if position.quantity > 0
            )

            return AccountSnapshot(
                broker_name=self.broker_name,
                cash_yen=round(self._cash_yen, 2),
                positions=positions,
                realized_pnl_yen=round(self._realized_pnl_yen, 2),
                generated_at=datetime.now(),
            )

    def submit_order(self, order: OrderRequest) -> OrderResult:
        order.validate()
        ticker = order.ticker.strip().upper()

        with self._lock:
            if order.client_order_id in self._processed_client_order_ids:
                return self._rejected_result(
                    order=order,
                    ticker=ticker,
                    message="同じclient_order_idの注文は既に処理済みです",
                )

            if order.side is OrderSide.BUY:
                result = self._buy(order, ticker)
            elif order.side is OrderSide.SELL:
                result = self._sell(order, ticker)
            else:
                result = self._rejected_result(
                    order=order,
                    ticker=ticker,
                    message="未対応の売買区分です",
                )

            if result.status is OrderStatus.FILLED:
                self._processed_client_order_ids.add(order.client_order_id)

            return result

    def _buy(
        self,
        order: OrderRequest,
        ticker: str,
    ) -> OrderResult:
        gross = round(order.quantity * order.limit_price, 2)
        commission = round(gross * self._commission_rate, 2)
        total_cost = round(gross + commission, 2)

        if total_cost > self._cash_yen:
            return self._rejected_result(
                order=order,
                ticker=ticker,
                message=(
                    f"買付余力不足: 必要額 {total_cost:,.2f}円 / "
                    f"現金 {self._cash_yen:,.2f}円"
                ),
            )

        current = self._positions.get(ticker)

        if current is None:
            new_quantity = order.quantity
            new_average = order.limit_price
        else:
            old_cost = current.quantity * current.average_price
            new_quantity = current.quantity + order.quantity
            new_average = (
                old_cost + order.quantity * order.limit_price
            ) / new_quantity

        self._positions[ticker] = _MutablePosition(
            quantity=new_quantity,
            average_price=round(new_average, 4),
            market_price=round(order.limit_price, 2),
        )
        self._cash_yen = round(self._cash_yen - total_cost, 2)

        return self._filled_result(
            order=order,
            ticker=ticker,
            message=(
                f"仮想買付完了: {ticker} {order.quantity}株 "
                f"{order.limit_price:,.2f}円"
            ),
        )

    def _sell(
        self,
        order: OrderRequest,
        ticker: str,
    ) -> OrderResult:
        current = self._positions.get(ticker)

        if current is None or current.quantity < order.quantity:
            held = 0 if current is None else current.quantity
            return self._rejected_result(
                order=order,
                ticker=ticker,
                message=(
                    f"保有株数不足: 売却 {order.quantity}株 / "
                    f"保有 {held}株"
                ),
            )

        gross = round(order.quantity * order.limit_price, 2)
        commission = round(gross * self._commission_rate, 2)
        proceeds = round(gross - commission, 2)
        acquisition_cost = round(
            order.quantity * current.average_price,
            2,
        )
        realized_pnl = round(proceeds - acquisition_cost, 2)

        current.quantity -= order.quantity
        current.market_price = round(order.limit_price, 2)
        self._cash_yen = round(self._cash_yen + proceeds, 2)
        self._realized_pnl_yen = round(
            self._realized_pnl_yen + realized_pnl,
            2,
        )

        if current.quantity == 0:
            del self._positions[ticker]

        return self._filled_result(
            order=order,
            ticker=ticker,
            message=(
                f"仮想売却完了: {ticker} {order.quantity}株 "
                f"{order.limit_price:,.2f}円 / "
                f"確定損益 {realized_pnl:+,.2f}円"
            ),
        )

    def _filled_result(
        self,
        order: OrderRequest,
        ticker: str,
        message: str,
    ) -> OrderResult:
        return OrderResult(
            broker_name=self.broker_name,
            broker_order_id=f"PAPER-{uuid4().hex[:16].upper()}",
            client_order_id=order.client_order_id,
            ticker=ticker,
            side=order.side,
            quantity=order.quantity,
            requested_price=round(order.limit_price, 2),
            filled_quantity=order.quantity,
            filled_price=round(order.limit_price, 2),
            status=OrderStatus.FILLED,
            message=message,
            created_at=datetime.now(),
        )

    def _rejected_result(
        self,
        order: OrderRequest,
        ticker: str,
        message: str,
    ) -> OrderResult:
        return OrderResult(
            broker_name=self.broker_name,
            broker_order_id="",
            client_order_id=order.client_order_id,
            ticker=ticker,
            side=order.side,
            quantity=order.quantity,
            requested_price=round(order.limit_price, 2),
            filled_quantity=0,
            filled_price=0.0,
            status=OrderStatus.REJECTED,
            message=message,
            created_at=datetime.now(),
        )
