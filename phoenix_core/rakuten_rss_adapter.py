from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from phoenix_core.models import OrderRequest, OrderStatus


JST = ZoneInfo("Asia/Tokyo")


def _now_jst() -> datetime:
    return datetime.now(JST)


@dataclass(frozen=True, slots=True)
class RakutenRssAdapterHealth:
    healthy: bool
    live_trading_enabled: bool
    message: str
    checked_at: datetime = field(default_factory=_now_jst)


@dataclass(frozen=True, slots=True)
class RakutenRssSubmitAck:
    status: OrderStatus
    message: str
    submitted_at: datetime = field(default_factory=_now_jst)
    rss_order_id: int = 0
    rss_order_number: str = ""
    authoritative_rss_status: int = -1


@dataclass(frozen=True, slots=True)
class RakutenRssOrderUpdate:
    status: OrderStatus
    fill_quantity: int = 0
    fill_price: float = 0.0
    message: str = ""
    updated_at: datetime = field(default_factory=_now_jst)
    rss_order_status: str = ""
    rss_order_id: int = 0
    rss_order_number: str = ""
    authoritative_rss_status: int = -1


@dataclass(frozen=True, slots=True)
class RakutenRssCancelAck:
    status: OrderStatus
    message: str
    canceled_at: datetime = field(default_factory=_now_jst)
    rss_order_id: int = 0
    rss_order_number: str = ""
    authoritative_rss_status: int = -1


class RakutenRssAdapter(Protocol):
    def health_check(self) -> RakutenRssAdapterHealth:
        raise NotImplementedError

    def submit_order(
        self,
        order: OrderRequest,
        broker_order_id: str,
    ) -> RakutenRssSubmitAck:
        raise NotImplementedError

    def poll_order(self, broker_order_id: str) -> tuple[RakutenRssOrderUpdate, ...]:
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        raise NotImplementedError


@dataclass(slots=True)
class _MockScript:
    client_order_id: str
    submit_status: OrderStatus = OrderStatus.ACCEPTED
    submit_message: str = "MOCK_ACCEPTED"
    cancel_status: OrderStatus = OrderStatus.CANCELED
    cancel_message: str = "MOCK_CANCELED"
    updates: list[RakutenRssOrderUpdate] = field(default_factory=list)
    broker_order_id: str = ""
    rss_order_id: int = 0
    rss_order_number: str = ""
    submit_authoritative_rss_status: int = -1
    cancel_authoritative_rss_status: int = -1


class MockRakutenRssAdapter(RakutenRssAdapter):
    def __init__(
        self,
        *,
        healthy: bool = True,
        live_trading_enabled: bool = True,
        message: str = "MOCK_RSS_READY",
    ) -> None:
        self._healthy = healthy
        self._live_trading_enabled = live_trading_enabled
        self._message = message
        self._scripts_by_client_order_id: dict[str, _MockScript] = {}
        self._scripts_by_broker_order_id: dict[str, _MockScript] = {}
        self.submitted_requests: list[dict[str, Any]] = []

    @property
    def submitted_count(self) -> int:
        return len(self.submitted_requests)

    def set_health(
        self,
        *,
        healthy: bool | None = None,
        live_trading_enabled: bool | None = None,
        message: str | None = None,
    ) -> None:
        if healthy is not None:
            self._healthy = healthy
        if live_trading_enabled is not None:
            self._live_trading_enabled = live_trading_enabled
        if message is not None:
            self._message = message

    def reset(self) -> None:
        self._scripts_by_client_order_id.clear()
        self._scripts_by_broker_order_id.clear()
        self.submitted_requests.clear()

    def script_order(
        self,
        client_order_id: str,
        *,
        submit_status: OrderStatus = OrderStatus.ACCEPTED,
        submit_message: str = "MOCK_ACCEPTED",
        cancel_status: OrderStatus = OrderStatus.CANCELED,
        cancel_message: str = "MOCK_CANCELED",
        rss_order_id: int = 0,
        rss_order_number: str = "",
        submit_authoritative_rss_status: int = -1,
        cancel_authoritative_rss_status: int = -1,
        updates: list[RakutenRssOrderUpdate] | None = None,
    ) -> None:
        script = self._scripts_by_client_order_id.get(client_order_id)
        if script is None:
            script = _MockScript(client_order_id=client_order_id)
            self._scripts_by_client_order_id[client_order_id] = script
        script.submit_status = submit_status
        script.submit_message = submit_message
        script.cancel_status = cancel_status
        script.cancel_message = cancel_message
        script.rss_order_id = int(rss_order_id)
        script.rss_order_number = str(rss_order_number)
        script.submit_authoritative_rss_status = int(submit_authoritative_rss_status)
        script.cancel_authoritative_rss_status = int(cancel_authoritative_rss_status)
        if updates is not None:
            script.updates = list(updates)

    def queue_update(
        self,
        client_order_id: str,
        *,
        status: OrderStatus,
        fill_quantity: int = 0,
        fill_price: float = 0.0,
        message: str = "",
        rss_order_status: str = "",
        rss_order_id: int = 0,
        rss_order_number: str = "",
        authoritative_rss_status: int = -1,
    ) -> None:
        script = self._scripts_by_client_order_id.get(client_order_id)
        if script is None:
            script = _MockScript(client_order_id=client_order_id)
            self._scripts_by_client_order_id[client_order_id] = script
        script.updates.append(
            RakutenRssOrderUpdate(
                status=status,
                fill_quantity=fill_quantity,
                fill_price=fill_price,
                message=message,
                rss_order_status=rss_order_status,
                rss_order_id=int(rss_order_id),
                rss_order_number=str(rss_order_number),
                authoritative_rss_status=int(authoritative_rss_status),
            )
        )

    def health_check(self) -> RakutenRssAdapterHealth:
        return RakutenRssAdapterHealth(
            healthy=self._healthy,
            live_trading_enabled=self._live_trading_enabled,
            message=self._message,
        )

    def submit_order(
        self,
        order: OrderRequest,
        broker_order_id: str,
    ) -> RakutenRssSubmitAck:
        script = self._scripts_by_client_order_id.get(order.client_order_id)
        if script is None:
            script = _MockScript(client_order_id=order.client_order_id)
            self._scripts_by_client_order_id[order.client_order_id] = script
        script.broker_order_id = broker_order_id
        self._scripts_by_broker_order_id[broker_order_id] = script
        self.submitted_requests.append(
            {
                "client_order_id": order.client_order_id,
                "broker_order_id": broker_order_id,
                "ticker": order.ticker,
                "side": order.side.value,
                "quantity": order.quantity,
                "limit_price": order.limit_price,
                "rss_order_id": script.rss_order_id,
                "rss_order_number": script.rss_order_number,
                "authoritative_rss_status": script.submit_authoritative_rss_status,
                "submitted_at": _now_jst().isoformat(timespec="seconds"),
            }
        )
        return RakutenRssSubmitAck(
            status=script.submit_status,
            message=script.submit_message,
            rss_order_id=script.rss_order_id,
            rss_order_number=script.rss_order_number,
            authoritative_rss_status=script.submit_authoritative_rss_status,
        )

    def poll_order(
        self,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        script = self._scripts_by_broker_order_id.get(broker_order_id)
        if script is None or not script.updates:
            return ()
        updates = tuple(script.updates)
        script.updates = []
        return updates

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        script = self._scripts_by_broker_order_id.get(broker_order_id)
        if script is None:
            return RakutenRssCancelAck(
                status=OrderStatus.CANCELED,
                message="MOCK_CANCEL_NOOP",
            )
        script.updates = []
        return RakutenRssCancelAck(
            status=script.cancel_status,
            message=script.cancel_message,
            rss_order_id=script.rss_order_id,
            rss_order_number=script.rss_order_number,
            authoritative_rss_status=script.cancel_authoritative_rss_status,
        )
