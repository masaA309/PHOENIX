from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from phoenix_core import (
    MockRakutenRssAdapter,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperBroker,
    RakutenRssBroker,
    create_broker,
)
from phoenix_core.broker import _MutablePosition
from phoenix_core.rakuten_rss_broker import _phoenix_protective_ledger


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


def _sell_order(
    client_order_id: str,
    *,
    quantity: int = 100,
    limit_price: float = 2326.8,
) -> OrderRequest:
    return OrderRequest(
        ticker="6473.T",
        side=OrderSide.SELL,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
        client_order_id=client_order_id,
        strategy_name="PHOENIX_AUTO_LIVE",
    )


class RakutenRssBrokerStep47Test(unittest.TestCase):
    def _make_broker(
        self,
        root: Path,
        *,
        live_enabled: bool = True,
        timeout_seconds: int = 300,
        adapter: MockRakutenRssAdapter | None = None,
    ) -> RakutenRssBroker:
        return RakutenRssBroker(
            initial_cash_yen=300_000,
            commission_rate=0.0,
            state_file=root / "state.json",
            adapter=adapter or MockRakutenRssAdapter(),
            live_enabled=live_enabled,
            timeout_seconds=timeout_seconds,
        )

    def test_submit_accepted_keeps_position_unconfirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.script_order(
                "ACCEPT-001",
                submit_status=OrderStatus.ACCEPTED,
                submit_message="accepted",
            )
            broker = self._make_broker(root, adapter=adapter)

            result = broker.submit_order(_buy_order("ACCEPT-001"))
            snapshot = broker.get_account_snapshot()

            self.assertEqual(OrderStatus.ACCEPTED, result.status)
            self.assertEqual(0, result.filled_quantity)
            self.assertEqual(1, adapter.submitted_count)
            self.assertEqual(300_000, snapshot.cash_yen)
            self.assertEqual(0, len(snapshot.positions))

    def test_submit_rejected_is_recorded_without_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.script_order(
                "REJECT-001",
                submit_status=OrderStatus.REJECTED,
                submit_message="rejected by mock adapter",
            )
            broker = self._make_broker(root, adapter=adapter)

            result = broker.submit_order(_buy_order("REJECT-001"))
            snapshot = broker.get_account_snapshot()

            self.assertEqual(OrderStatus.REJECTED, result.status)
            self.assertEqual("rejected by mock adapter", result.message)
            self.assertEqual(300_000, snapshot.cash_yen)
            self.assertEqual(0, len(snapshot.positions))

    def test_pending_submit_remains_pending_until_acceptance_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.script_order(
                "PENDING-001",
                submit_status=OrderStatus.PENDING,
                submit_message="awaiting VBA receipt",
            )
            adapter.queue_update(
                "PENDING-001",
                status=OrderStatus.ACCEPTED,
                message="有効",
                rss_order_status="有効",
            )
            broker = self._make_broker(root, adapter=adapter)

            submit_result = broker.submit_order(_buy_order("PENDING-001"))
            refresh_results = broker.refresh_pending_orders()

            self.assertEqual(OrderStatus.PENDING, submit_result.status)
            self.assertEqual(1, len(refresh_results))
            self.assertEqual(OrderStatus.ACCEPTED, refresh_results[0].status)
            self.assertEqual(1, adapter.submitted_count)

    def test_pending_cancel_remains_pending_until_final_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.script_order(
                "PENDING-CANCEL-001",
                submit_status=OrderStatus.PENDING,
                submit_message="awaiting VBA receipt",
                cancel_status=OrderStatus.PENDING,
                cancel_message="cancel awaiting VBA receipt",
            )
            broker = self._make_broker(root, adapter=adapter)

            submit_result = broker.submit_order(_buy_order("PENDING-CANCEL-001"))
            cancel_result = broker.cancel_order("PENDING-CANCEL-001")
            adapter.queue_update(
                "PENDING-CANCEL-001",
                status=OrderStatus.CANCELED,
                message="cancel accepted",
                rss_order_status="無効",
            )
            refresh_results = broker.refresh_pending_orders()

            self.assertEqual(OrderStatus.PENDING, submit_result.status)
            self.assertEqual(OrderStatus.PENDING, cancel_result.status)
            self.assertEqual(1, len(refresh_results))
            self.assertEqual(OrderStatus.CANCELED, refresh_results[0].status)
            self.assertEqual(1, adapter.submitted_count)

    def test_partial_fill_updates_position_with_actual_price_and_qty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.queue_update(
                "PARTIAL-001",
                status=OrderStatus.PARTIALLY_FILLED,
                fill_quantity=40,
                fill_price=98.75,
                message="partial fill",
            )
            broker = self._make_broker(root, adapter=adapter)

            submit_result = broker.submit_order(_buy_order("PARTIAL-001"))
            refresh_results = broker.refresh_pending_orders()
            snapshot = broker.get_account_snapshot()

            self.assertEqual(OrderStatus.ACCEPTED, submit_result.status)
            self.assertEqual(1, len(refresh_results))
            self.assertEqual(OrderStatus.PARTIALLY_FILLED, refresh_results[0].status)
            self.assertEqual(40, refresh_results[0].filled_quantity)
            self.assertEqual(40, snapshot.positions[0].quantity)
            self.assertEqual(98.75, snapshot.positions[0].average_price)
            self.assertEqual(296_050, snapshot.cash_yen)

    def test_full_fill_updates_position_with_actual_price_and_qty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.queue_update(
                "FULL-001",
                status=OrderStatus.FILLED,
                fill_quantity=100,
                fill_price=99.25,
                message="full fill",
            )
            broker = self._make_broker(root, adapter=adapter)

            broker.submit_order(_buy_order("FULL-001"))
            refresh_results = broker.refresh_pending_orders()
            snapshot = broker.get_account_snapshot()

            self.assertEqual(1, len(refresh_results))
            self.assertEqual(OrderStatus.FILLED, refresh_results[0].status)
            self.assertEqual(100, refresh_results[0].filled_quantity)
            self.assertEqual(1, len(snapshot.positions))
            self.assertEqual(100, snapshot.positions[0].quantity)
            self.assertEqual(99.25, snapshot.positions[0].average_price)
            self.assertEqual(290_075, snapshot.cash_yen)

    def test_protective_sell_confirms_only_after_rss_status_is_valid(self) -> None:
        from phoenix_core.protective_orders import PROTECTED, PROTECTING

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.script_order(
                "EXIT-001",
                submit_status=OrderStatus.ACCEPTED,
                submit_message="protective submitted",
            )
            adapter.queue_update(
                "EXIT-001",
                status=OrderStatus.ACCEPTED,
                message="有効",
                rss_order_status="有効",
            )
            broker = self._make_broker(root, adapter=adapter)
            broker._positions["6473.T"] = _MutablePosition(
                quantity=100,
                average_price=2210.0,
                market_price=2141.0,
            )
            ledger = _phoenix_protective_ledger(broker)
            ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-EXIT-001")
            submit_result = broker.submit_order(_sell_order("EXIT-001"))
            pending_snapshot = ledger.snapshot("6473.T")

            refresh_results = broker.refresh_pending_orders()
            confirmed_snapshot = ledger.snapshot("6473.T")

            self.assertEqual(OrderStatus.ACCEPTED, submit_result.status)
            self.assertEqual(PROTECTING, pending_snapshot.protective_order_state)
            self.assertEqual("PENDING", pending_snapshot.protective_order_acceptance_state)
            self.assertEqual(1, len(refresh_results))
            self.assertEqual(OrderStatus.ACCEPTED, refresh_results[0].status)
            self.assertEqual(PROTECTED, confirmed_snapshot.protective_order_state)
            self.assertTrue(broker.can_submit_new_buy())

    def test_protective_sell_rejects_invalid_rss_status(self) -> None:
        from phoenix_core.protective_orders import CRITICAL, PROTECTING

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.script_order(
                "EXIT-002",
                submit_status=OrderStatus.ACCEPTED,
                submit_message="protective submitted",
            )
            adapter.queue_update(
                "EXIT-002",
                status=OrderStatus.REJECTED,
                message="無効",
                rss_order_status="無効",
            )
            broker = self._make_broker(root, adapter=adapter)
            broker._positions["6473.T"] = _MutablePosition(
                quantity=100,
                average_price=2210.0,
                market_price=2141.0,
            )
            ledger = _phoenix_protective_ledger(broker)
            ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-EXIT-002")
            broker.submit_order(_sell_order("EXIT-002"))
            broker.refresh_pending_orders()

            self.assertEqual(CRITICAL, ledger.snapshot("6473.T").protective_order_state)
            self.assertFalse(broker.can_submit_new_buy())

    def test_cancel_keeps_partial_fills_and_finalizes_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            adapter.queue_update(
                "CANCEL-001",
                status=OrderStatus.PARTIALLY_FILLED,
                fill_quantity=30,
                fill_price=99.5,
                message="partial before cancel",
            )
            broker = self._make_broker(root, adapter=adapter)

            broker.submit_order(_buy_order("CANCEL-001"))
            broker.refresh_pending_orders()
            cancel_result = broker.cancel_order("CANCEL-001")
            snapshot = broker.get_account_snapshot()

            self.assertEqual(OrderStatus.PARTIALLY_FILLED, cancel_result.status)
            self.assertEqual(30, cancel_result.filled_quantity)
            self.assertIn("RSS order number is missing for cancel", cancel_result.message)
            self.assertEqual(30, snapshot.positions[0].quantity)
            self.assertEqual(99.5, snapshot.positions[0].average_price)

    def test_timeout_finalizes_without_state_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            broker = self._make_broker(root, timeout_seconds=0)

            submit_result = broker.submit_order(_buy_order("TIMEOUT-001"))
            timeout_results = broker.refresh_pending_orders(
                now=submit_result.created_at + timedelta(seconds=1),
            )
            snapshot = broker.get_account_snapshot()

            self.assertEqual(OrderStatus.ACCEPTED, submit_result.status)
            self.assertEqual(0, len(timeout_results))
            self.assertEqual(300_000, snapshot.cash_yen)
            self.assertEqual(0, len(snapshot.positions))

    def test_duplicate_restart_suppresses_second_submit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter1 = MockRakutenRssAdapter()
            broker1 = self._make_broker(root, adapter=adapter1)
            order = _buy_order("DUPLICATE-001")

            first = broker1.submit_order(order)
            adapter2 = MockRakutenRssAdapter()
            broker2 = self._make_broker(root, adapter=adapter2)
            second = broker2.submit_order(order)

            self.assertEqual(OrderStatus.ACCEPTED, first.status)
            self.assertEqual(OrderStatus.ACCEPTED, second.status)
            self.assertEqual(1, adapter1.submitted_count)
            self.assertEqual(0, adapter2.submitted_count)

    def test_kill_switch_fail_closes_pending_orders_and_blocks_new_submits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adapter = MockRakutenRssAdapter()
            broker = self._make_broker(root, adapter=adapter)

            pending = broker.submit_order(_buy_order("KILL-001"))
            canceled = broker.engage_kill_switch("manual stop")
            new_result = broker.submit_order(_buy_order("KILL-002"))
            snapshot = broker.get_account_snapshot()

            self.assertEqual(OrderStatus.ACCEPTED, pending.status)
            self.assertEqual(1, len(canceled))
            self.assertEqual(OrderStatus.CANCELED, canceled[0].status)
            self.assertEqual(OrderStatus.REJECTED, new_result.status)
            self.assertEqual(300_000, snapshot.cash_yen)
            self.assertEqual(0, len(snapshot.positions))

    def test_live_flag_off_rejects_orders_and_factory_defaults_to_paper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            paper_broker = create_broker({}, root)
            self.assertIsInstance(paper_broker, PaperBroker)

            with self.assertRaises(ValueError):
                create_broker(
                    {
                        "broker": {
                            "type": "rakuten_rss",
                            "live_trading_enabled": False,
                        }
                    },
                    root,
                )

            broker = RakutenRssBroker(
                initial_cash_yen=300_000,
                state_file=root / "state_off.json",
                adapter=MockRakutenRssAdapter(),
                live_enabled=False,
            )
            result = broker.submit_order(_buy_order("OFF-001"))

            self.assertEqual(OrderStatus.REJECTED, result.status)
            self.assertEqual(0, len(broker.get_account_snapshot().positions))


if __name__ == "__main__":
    unittest.main()
