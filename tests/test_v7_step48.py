from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from phoenix_core import (
    MockRakutenRssAdapter,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductionRakutenRssAdapter,
    RakutenRssBroker,
    RakutenRssAdapterHealth,
    RakutenRssCancelAck,
    RakutenRssSubmitAck,
    RakutenRssTransportHealth,
    create_broker,
)


def _buy_order(
    client_order_id: str,
    *,
    quantity: int = 100,
    limit_price: float = 100.0,
) -> OrderRequest:
    return OrderRequest(
        ticker="1301.T",
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
        client_order_id=client_order_id,
        strategy_name="PHOENIX_AUTO_LIVE",
    )


class _CountingTransport:
    def __init__(self, *, connected: bool = True, message: str = "COUNTING_READY") -> None:
        self._connected = connected
        self._message = message
        self.submit_count = 0
        self.poll_count = 0
        self.cancel_count = 0

    def health_check(self) -> RakutenRssTransportHealth:
        return RakutenRssTransportHealth(
            connected=self._connected,
            message=self._message,
            transport_source="COM_LIVE" if self._connected else "DISCONNECTED",
        )

    def submit_order(
        self,
        order: OrderRequest,
        broker_order_id: str,
    ) -> RakutenRssSubmitAck:
        self.submit_count += 1
        return RakutenRssSubmitAck(
            status=OrderStatus.ACCEPTED,
            message="COUNTING_ACCEPTED",
        )

    def poll_order(self, broker_order_id: str) -> tuple[object, ...]:
        self.poll_count += 1
        return ()

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        self.cancel_count += 1
        return RakutenRssCancelAck(
            status=OrderStatus.CANCELED,
            message="COUNTING_CANCELED",
        )


class ProductionRakutenRssAdapterStep48Test(unittest.TestCase):
    def test_import_and_construct_defaults_to_fail_closed_transport(self) -> None:
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=True,
            production_transport_enabled=True,
        )

        health = adapter.health_check()

        self.assertIsInstance(health, RakutenRssAdapterHealth)
        self.assertFalse(health.healthy)
        self.assertIn("Excel/RSS transport", health.message)

    def test_live_off_rejects_submit_without_transport_calls(self) -> None:
        transport = _CountingTransport(connected=True)
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=False,
            production_transport_enabled=True,
            transport=transport,
        )

        result = adapter.submit_order(_buy_order("LIVE-OFF-001"), "RSS-LIVE-OFF-001")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("live_trading_enabled=true", result.message)
        self.assertEqual(0, transport.submit_count)

    def test_production_transport_off_rejects_submit_without_transport_calls(self) -> None:
        transport = _CountingTransport(connected=True)
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=True,
            production_transport_enabled=False,
            transport=transport,
        )

        result = adapter.submit_order(
            _buy_order("TRANSPORT-OFF-001"),
            "RSS-TRANSPORT-OFF-001",
        )

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("production_transport_enabled=true", result.message)
        self.assertEqual(0, transport.submit_count)

    def test_excel_rss_unconnected_fail_closes_submit_poll_and_cancel(self) -> None:
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=True,
            production_transport_enabled=True,
        )

        result = adapter.submit_order(_buy_order("DISCONNECTED-001"), "RSS-DISCONNECTED-001")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("Excel/RSS transport is unavailable", result.message)
        self.assertEqual(0, adapter.transport.submitted_count)
        with self.assertRaises(RuntimeError):
            adapter.poll_order("RSS-DISCONNECTED-001")
        with self.assertRaises(RuntimeError):
            adapter.cancel_order("RSS-DISCONNECTED-001")

    def test_mock_interface_compat_and_no_real_calls(self) -> None:
        mock_adapter = MockRakutenRssAdapter()
        transport = _CountingTransport(connected=True)
        production_adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=False,
            production_transport_enabled=True,
            transport=transport,
        )
        order = _buy_order("COMPAT-001")

        public_methods = {
            name
            for name in ("health_check", "submit_order", "poll_order", "cancel_order")
            if callable(getattr(production_adapter, name, None))
        }

        self.assertEqual(
            {"health_check", "submit_order", "poll_order", "cancel_order"},
            public_methods,
        )
        self.assertIsInstance(production_adapter.health_check(), type(mock_adapter.health_check()))
        self.assertIsInstance(
            production_adapter.submit_order(order, "RSS-COMPAT-001"),
            type(mock_adapter.submit_order(order, "MOCK-COMPAT-001")),
        )
        self.assertEqual(0, transport.submit_count)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            broker = create_broker(
                {
                    "broker": {
                        "type": "rakuten_rss",
                        "transport_mode": "production",
                        "live_trading_enabled": True,
                        "production_transport_enabled": True,
                    }
                },
                root,
            )

            self.assertIsInstance(broker, RakutenRssBroker)
            self.assertEqual(OrderStatus.REJECTED, broker.submit_order(order).status)


if __name__ == "__main__":
    unittest.main()
