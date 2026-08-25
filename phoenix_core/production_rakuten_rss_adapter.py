from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

from phoenix_core.models import OrderRequest, OrderStatus
from phoenix_core.rakuten_rss_adapter import (
    RakutenRssAdapterHealth,
    RakutenRssCancelAck,
    RakutenRssOrderUpdate,
    RakutenRssSubmitAck,
)


JST = ZoneInfo("Asia/Tokyo")
RSS_STOCK_ORDER_MACRO = "RssStockOrder_V"
TRANSPORT_SOURCE_COM_LIVE = "COM_LIVE"
TRANSPORT_SOURCE_FILE_READY = "FILE_READY"


def _now_jst() -> datetime:
    return datetime.now(JST)


@dataclass(frozen=True, slots=True)
class RakutenRssTransportHealth:
    connected: bool
    message: str
    transport_source: str = "DISCONNECTED"
    checked_at: datetime = field(default_factory=_now_jst)


@runtime_checkable
class RakutenRssTransport(Protocol):
    def health_check(self) -> RakutenRssTransportHealth:
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


class DisabledProductionRakutenRssTransport:
    """Fail-close transport stub.

    This is the default transport for the production adapter in this step.
    It keeps the Excel/RSS connection boundary isolated without issuing any
    real RSS call.
    """

    @property
    def submitted_count(self) -> int:
        return 0

    def health_check(self) -> RakutenRssTransportHealth:
        return RakutenRssTransportHealth(
            connected=False,
            message="Excel/RSS transport is not connected.",
        )

    def submit_order(
        self,
        order: OrderRequest,
        broker_order_id: str,
    ) -> RakutenRssSubmitAck:
        return RakutenRssSubmitAck(
            status=OrderStatus.REJECTED,
            message="Excel/RSS transport is not connected.",
        )

    def poll_order(self, broker_order_id: str) -> tuple[RakutenRssOrderUpdate, ...]:
        return ()

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        return RakutenRssCancelAck(
            status=OrderStatus.REJECTED,
            message="Excel/RSS transport is not connected.",
        )


class ProductionRakutenRssAdapter:
    """Adapter boundary for a future live Rakuten RSS transport.

    The adapter itself only owns gatekeeping and state-free routing. Real COM,
    Excel, or RSS wiring must be injected through the transport object.
    """

    def __init__(
        self,
        *,
        live_trading_enabled: bool = False,
        production_transport_enabled: bool = False,
        transport: RakutenRssTransport | None = None,
    ) -> None:
        self._live_trading_enabled = bool(live_trading_enabled)
        self._production_transport_enabled = bool(production_transport_enabled)
        self._transport = transport or DisabledProductionRakutenRssTransport()
        self._lock = RLock()

    @property
    def transport(self) -> RakutenRssTransport:
        return self._transport

    def _effective_live_enabled(self) -> bool:
        return self._live_trading_enabled and self._production_transport_enabled

    def _live_gate_message(self) -> str:
        if not self._live_trading_enabled:
            return "Rakuten RSS production adapter is disabled until live_trading_enabled=true."
        if not self._production_transport_enabled:
            return (
                "Rakuten RSS production adapter is disabled until "
                "production_transport_enabled=true."
            )
        return ""

    def _transport_health(self) -> RakutenRssTransportHealth:
        health = self._transport.health_check()
        if not isinstance(health, RakutenRssTransportHealth):
            raise TypeError("transport.health_check() must return RakutenRssTransportHealth")
        return health

    def health_check(self) -> RakutenRssAdapterHealth:
        try:
            gate_message = self._live_gate_message()
            if gate_message:
                return RakutenRssAdapterHealth(
                    healthy=False,
                    live_trading_enabled=False,
                    message=gate_message,
                )
            transport_health = self._transport_health()
            if not transport_health.connected:
                message = f"Excel/RSS transport is unavailable: {transport_health.message}"
            else:
                message = "Rakuten RSS production adapter ready."
            healthy = self._effective_live_enabled() and transport_health.connected
            return RakutenRssAdapterHealth(
                healthy=healthy,
                live_trading_enabled=self._effective_live_enabled(),
                message=message,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            return RakutenRssAdapterHealth(
                healthy=False,
                live_trading_enabled=False,
                message=f"Excel/RSS health check failed: {error}",
            )

    def submit_order(
        self,
        order: OrderRequest,
        broker_order_id: str,
    ) -> RakutenRssSubmitAck:
        order.validate()

        with self._lock:
            gate_message = self._live_gate_message()
            if gate_message:
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=gate_message,
                )

            try:
                transport_health = self._transport_health()
            except Exception as error:
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=f"Excel/RSS health check failed: {error}",
                )

            if not transport_health.connected:
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=f"Excel/RSS transport is unavailable: {transport_health.message}",
                )
            if transport_health.transport_source not in {
                TRANSPORT_SOURCE_COM_LIVE,
                TRANSPORT_SOURCE_FILE_READY,
            }:
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=f"Excel/RSS transport is unavailable: {transport_health.message}",
                )

            try:
                ack = self._transport.submit_order(order, broker_order_id)
            except Exception as error:
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=f"Excel/RSS submit failed: {error}",
                )

            if ack.status not in {OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.REJECTED}:
                raise ValueError("Rakuten RSS transport ack must be PENDING, ACCEPTED or REJECTED")
            return ack

    def poll_order(self, broker_order_id: str) -> tuple[RakutenRssOrderUpdate, ...]:
        with self._lock:
            gate_message = self._live_gate_message()
            if gate_message:
                raise RuntimeError(gate_message)

            transport_health = self._transport_health()
            if not transport_health.connected or transport_health.transport_source not in {
                TRANSPORT_SOURCE_COM_LIVE,
                TRANSPORT_SOURCE_FILE_READY,
            }:
                raise RuntimeError(
                    f"Excel/RSS transport is unavailable: {transport_health.message}"
                )

            return self._transport.poll_order(broker_order_id)

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        with self._lock:
            gate_message = self._live_gate_message()
            if gate_message:
                raise RuntimeError(gate_message)

            transport_health = self._transport_health()
            if not transport_health.connected or transport_health.transport_source not in {
                TRANSPORT_SOURCE_COM_LIVE,
                TRANSPORT_SOURCE_FILE_READY,
            }:
                raise RuntimeError(
                    f"Excel/RSS transport is unavailable: {transport_health.message}"
                )

            return self._transport.cancel_order(broker_order_id)
