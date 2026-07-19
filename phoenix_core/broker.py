from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from threading import RLock
from typing import Any
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
    永続化対応Paper Broker。

    state_fileを指定すると、現金・保有株・確定損益・処理済み注文IDを
    JSONへ保存し、次回実行時に復元する。
    """

    STATE_VERSION = 1

    def __init__(
        self,
        initial_cash_yen: float = 300_000.0,
        commission_rate: float = 0.0,
        state_file: Path | None = None,
    ) -> None:
        if initial_cash_yen < 0:
            raise ValueError("initial_cash_yenは0以上にしてください")
        if commission_rate < 0:
            raise ValueError("commission_rateは0以上にしてください")

        self._initial_cash_yen = round(float(initial_cash_yen), 2)
        self._cash_yen = self._initial_cash_yen
        self._commission_rate = float(commission_rate)
        self._state_file = state_file
        self._positions: dict[str, _MutablePosition] = {}
        self._realized_pnl_yen = 0.0
        self._processed_client_order_ids: set[str] = set()
        self._lock = RLock()

        self._load_state()

    @property
    def broker_name(self) -> str:
        return "PAPER"

    def health_check(self) -> BrokerHealth:
        try:
            if self._state_file is not None:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
            return BrokerHealth(
                broker_name=self.broker_name,
                healthy=True,
                live_trading_enabled=False,
                message="Paper Broker正常。実売買は無効です。",
                checked_at=datetime.now(),
            )
        except OSError as error:
            return BrokerHealth(
                broker_name=self.broker_name,
                healthy=False,
                live_trading_enabled=False,
                message=f"状態保存先異常: {error}",
                checked_at=datetime.now(),
            )

    def reset(self) -> None:
        with self._lock:
            self._cash_yen = self._initial_cash_yen
            self._positions.clear()
            self._realized_pnl_yen = 0.0
            self._processed_client_order_ids.clear()
            self._save_state()

    def set_market_price(self, ticker: str, market_price: float) -> None:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise ValueError("tickerが空です")
        if market_price <= 0:
            raise ValueError("market_priceは0より大きい値にしてください")

        with self._lock:
            position = self._positions.get(normalized_ticker)
            if position is not None:
                position.market_price = round(float(market_price), 2)
                self._save_state()

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
                    order,
                    ticker,
                    "同じclient_order_idの注文は既に処理済みです",
                )

            if order.side is OrderSide.BUY:
                result = self._buy(order, ticker)
            elif order.side is OrderSide.SELL:
                result = self._sell(order, ticker)
            else:
                result = self._rejected_result(
                    order,
                    ticker,
                    "未対応の売買区分です",
                )

            if result.status is OrderStatus.FILLED:
                self._processed_client_order_ids.add(order.client_order_id)
                self._save_state()

            return result

    def _buy(self, order: OrderRequest, ticker: str) -> OrderResult:
        gross = round(order.quantity * order.limit_price, 2)
        commission = round(gross * self._commission_rate, 2)
        total_cost = round(gross + commission, 2)

        if total_cost > self._cash_yen:
            return self._rejected_result(
                order,
                ticker,
                (
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
            order,
            ticker,
            (
                f"仮想買付完了: {ticker} {order.quantity}株 "
                f"{order.limit_price:,.2f}円"
            ),
        )

    def _sell(self, order: OrderRequest, ticker: str) -> OrderResult:
        current = self._positions.get(ticker)
        if current is None or current.quantity < order.quantity:
            held = 0 if current is None else current.quantity
            return self._rejected_result(
                order,
                ticker,
                (
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
            order,
            ticker,
            (
                f"仮想売却完了: {ticker} {order.quantity}株 "
                f"{order.limit_price:,.2f}円 / "
                f"確定損益 {realized_pnl:+,.2f}円"
            ),
        )

    def _state_payload(self) -> dict[str, Any]:
        return {
            "state_version": self.STATE_VERSION,
            "broker_name": self.broker_name,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "initial_cash_yen": self._initial_cash_yen,
            "cash_yen": self._cash_yen,
            "commission_rate": self._commission_rate,
            "realized_pnl_yen": self._realized_pnl_yen,
            "positions": {
                ticker: {
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "market_price": position.market_price,
                }
                for ticker, position in sorted(self._positions.items())
            },
            "processed_client_order_ids": sorted(
                self._processed_client_order_ids
            ),
        }

    def _save_state(self) -> None:
        if self._state_file is None:
            return

        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_file.with_suffix(
            self._state_file.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                self._state_payload(),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self._state_file)

    def _load_state(self) -> None:
        if self._state_file is None or not self._state_file.exists():
            return

        try:
            payload = json.loads(
                self._state_file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Paper Broker状態ファイルを読み込めません: "
                f"{self._state_file}"
            ) from error

        if int(payload.get("state_version", 0)) != self.STATE_VERSION:
            raise ValueError("未対応のPaper Broker状態バージョンです")

        self._cash_yen = round(
            float(payload.get("cash_yen", self._initial_cash_yen)),
            2,
        )
        self._realized_pnl_yen = round(
            float(payload.get("realized_pnl_yen", 0.0)),
            2,
        )
        self._processed_client_order_ids = {
            str(value)
            for value in payload.get(
                "processed_client_order_ids",
                [],
            )
        }

        positions = payload.get("positions", {})
        if not isinstance(positions, dict):
            raise ValueError("positionsはJSONオブジェクトにしてください")

        self._positions = {}
        for ticker, value in positions.items():
            if not isinstance(value, dict):
                continue
            quantity = int(value.get("quantity", 0))
            if quantity <= 0:
                continue
            self._positions[str(ticker).upper()] = _MutablePosition(
                quantity=quantity,
                average_price=round(
                    float(value.get("average_price", 0.0)),
                    4,
                ),
                market_price=round(
                    float(value.get("market_price", 0.0)),
                    2,
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
