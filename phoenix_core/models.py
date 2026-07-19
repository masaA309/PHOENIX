from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    ticker: str
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: float
    client_order_id: str
    strategy_name: str = "PHOENIX"
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        ticker = self.ticker.strip().upper()

        if not ticker:
            raise ValueError("tickerが空です")

        if self.quantity <= 0:
            raise ValueError("quantityは1以上にしてください")

        if self.order_type is not OrderType.LIMIT:
            raise ValueError("PHOENIX v7 Step1では指値注文のみ許可します")

        if self.limit_price <= 0:
            raise ValueError("limit_priceは0より大きい値にしてください")

        if not self.client_order_id.strip():
            raise ValueError("client_order_idが空です")


@dataclass(frozen=True, slots=True)
class OrderResult:
    broker_name: str
    broker_order_id: str
    client_order_id: str
    ticker: str
    side: OrderSide
    quantity: int
    requested_price: float
    filled_quantity: int
    filled_price: float
    status: OrderStatus
    message: str
    created_at: datetime

    @property
    def gross_amount(self) -> float:
        return round(self.filled_quantity * self.filled_price, 2)


@dataclass(frozen=True, slots=True)
class Position:
    ticker: str
    quantity: int
    average_price: float
    market_price: float

    @property
    def market_value(self) -> float:
        return round(self.quantity * self.market_price, 2)

    @property
    def unrealized_pnl(self) -> float:
        return round(
            self.quantity * (self.market_price - self.average_price),
            2,
        )


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    broker_name: str
    cash_yen: float
    positions: tuple[Position, ...]
    realized_pnl_yen: float
    generated_at: datetime

    @property
    def market_value_yen(self) -> float:
        return round(
            sum(position.market_value for position in self.positions),
            2,
        )

    @property
    def unrealized_pnl_yen(self) -> float:
        return round(
            sum(position.unrealized_pnl for position in self.positions),
            2,
        )

    @property
    def equity_yen(self) -> float:
        return round(self.cash_yen + self.market_value_yen, 2)


@dataclass(frozen=True, slots=True)
class BrokerHealth:
    broker_name: str
    healthy: bool
    live_trading_enabled: bool
    message: str
    checked_at: datetime
