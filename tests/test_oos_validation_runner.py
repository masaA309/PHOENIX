from __future__ import annotations

from datetime import datetime, timezone
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from phoenix_core.oos_validation_runner import (
    ROOT,
    _base_settings,
    _build_dry_run_payload,
    _fixed_run_settings,
    _summarize_oos_performance,
    build_run_specs,
)


BASE_CONFIG_PATH = Path("config/v7_historical_validation_risk_v2_quick.json")


class OOSValidationRunnerSpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runs = build_run_specs()
        self.base_settings = {
            "slippage_rate": 0.0005,
            "market_breadth_bear_threshold": 0.4,
            "market_breadth_bear_max_total_invested_pct": 0.7,
            "benchmark_enabled": True,
            "initial_capital_yen": 500000,
            "lot_size": 100,
            "requested_start": "2017-08-01",
            "requested_end": "2026-08-14",
            "allow_network_fetch": False,
        }

    def test_run_specs_have_three_fixed_windows(self) -> None:
        self.assertEqual(
            [
                ("OOS-1", "OOS_1", "2017-08-01", "2020-12-31"),
                ("OOS-2", "OOS_2", "2021-01-01", "2023-12-31"),
                ("OOS-3", "OOS_3", "2024-01-01", "2026-08-14"),
            ],
            [(run.name, run.slug, run.requested_start, run.requested_end) for run in self.runs],
        )

    def test_fixed_run_settings_lock_risk_v2_parameters(self) -> None:
        run = self.runs[0]
        settings = _fixed_run_settings(
            self.base_settings,
            run,
            Path("reports/oos_validation/runs/OOS_1"),
            0.0005,
        )
        self.assertEqual(500000, settings["initial_capital_yen"])
        self.assertEqual(0.4, settings["market_breadth_bear_threshold"])
        self.assertEqual(0.7, settings["market_breadth_bear_max_total_invested_pct"])
        self.assertEqual(0.0005, settings["slippage_rate"])
        self.assertEqual("2017-08-01", settings["requested_start"])
        self.assertEqual("2020-12-31", settings["requested_end"])
        self.assertFalse(settings["allow_network_fetch"])

    def test_dry_run_payload_has_three_planned_runs(self) -> None:
        base_settings, base_config_sha256 = _base_settings(ROOT, BASE_CONFIG_PATH)
        payload = _build_dry_run_payload(
            root=ROOT,
            base_config_path=BASE_CONFIG_PATH,
            base_config_sha256=base_config_sha256,
            base_settings=base_settings,
            runs=self.runs,
        )
        self.assertEqual("DRY_RUN", payload["status"])
        self.assertTrue(payload["checks"]["base_config_exists"])
        self.assertTrue(payload["checks"]["market_cache_dir_exists"])
        self.assertTrue(payload["checks"]["universe_csv_exists"])
        self.assertEqual(3, len(payload["planned_runs"]))
        self.assertEqual(
            {
                "market_breadth_filter_enabled": True,
                "market_breadth_bear_threshold": 0.4,
                "market_breadth_bear_max_total_invested_pct": 0.7,
                "slippage_rate": "baseline from base config",
                "initial_capital_yen": 500000,
            },
            payload["fixed_validation"],
        )


class OOSValidationRunnerMetricsTest(unittest.TestCase):
    def test_oos_performance_includes_extra_metrics(self) -> None:
        result = SimpleNamespace(
            trades=pd.DataFrame(
                [
                    {"profit_yen": 100.0, "return_pct": 1.0, "holding_sessions": 3},
                    {"profit_yen": -50.0, "return_pct": -0.5, "holding_sessions": 2},
                    {"profit_yen": -20.0, "return_pct": -0.2, "holding_sessions": 1},
                    {"profit_yen": 40.0, "return_pct": 0.4, "holding_sessions": 4},
                ]
            ),
            equity_curve=pd.DataFrame(
                [
                    {"date": "2020-01-01", "equity_yen": 500000.0, "cash_yen": 500000.0},
                    {"date": "2020-01-02", "equity_yen": 520000.0, "cash_yen": 495000.0},
                    {"date": "2020-01-03", "equity_yen": 510000.0, "cash_yen": 490000.0},
                    {"date": "2020-01-04", "equity_yen": 505000.0, "cash_yen": 480000.0},
                    {"date": "2020-01-05", "equity_yen": 530000.0, "cash_yen": 470000.0},
                ]
            ),
            annual_returns=pd.DataFrame(),
            monthly_returns=pd.DataFrame(),
            diagnostics=pd.DataFrame(),
            risk_v2_research=pd.DataFrame(),
            rejected_due_to_lot=2,
            rejected_due_to_buying_power=3,
        )

        performance = _summarize_oos_performance(result, 500000.0)
        self.assertEqual(530000.0, performance["final_equity_yen"])
        self.assertEqual(6.0, performance["total_return_pct"])
        self.assertEqual(6.0, performance["total_return"])
        self.assertAlmostEqual(17.5, performance["expectancy_per_trade_yen"])
        self.assertEqual(2, performance["max_consecutive_losses"])
        self.assertEqual(2, performance["longest_underwater_sessions"])
        self.assertEqual(2.0, performance["recovery_factor"])
        self.assertEqual(2, performance["rejected_due_to_lot"])
        self.assertEqual(3, performance["rejected_due_to_buying_power"])


if __name__ == "__main__":
    unittest.main()
class ProtectiveOrdersStateMachineTest(unittest.TestCase):
    def test_a_buy_fill_acceptance(self):
        from phoenix_core.protective_orders import PROTECTED, PROTECTING, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        record = ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-1")
        self.assertEqual(record.protective_order_state, PROTECTING)

        record = ledger.register_protective_order_submitted("6473.T", "EXIT-1")
        self.assertEqual(record.protective_order_state, PROTECTING)
        self.assertEqual("PENDING", record.protective_order_acceptance_state)

        record = ledger.confirm_rss_order_status("6473.T", "有効", protective_order_id="EXIT-1")
        self.assertEqual(record.protective_order_state, PROTECTED)
        self.assertTrue(ledger.can_submit_new_buy())

    def test_b_rejected_blocks_buy(self):
        from phoenix_core.protective_orders import CRITICAL, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-2")
        ledger.register_protective_order_submitted("6473.T", "EXIT-2")
        record = ledger.confirm_rss_order_status("6473.T", "無効", protective_order_id="EXIT-2")
        self.assertEqual(record.protective_order_state, CRITICAL)
        self.assertFalse(ledger.can_submit_new_buy())

    def test_c_disconnect_keeps_protected_but_blocks_buy(self):
        from phoenix_core.protective_orders import PROTECTED, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-3")
        record = ledger.register_protective_order_accepted("6473.T", "EXIT-3")
        self.assertEqual(record.protective_order_state, PROTECTED)

        ledger.mark_transport_disconnected()
        self.assertEqual(ledger.snapshot("6473.T").protective_order_state, PROTECTED)
        self.assertFalse(ledger.can_submit_new_buy())

    def test_d_reconnect_and_reconcile_restores_eligibility(self):
        from phoenix_core.protective_orders import PROTECTED, RECONCILING, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-4")
        ledger.register_protective_order_accepted("6473.T", "EXIT-4")
        ledger.mark_transport_disconnected()
        ledger.mark_transport_reconnected()
        self.assertEqual(ledger.snapshot("6473.T").protective_order_state, RECONCILING)

        record = ledger.reconcile(
            "6473.T",
            position_matches=True,
            open_order_matches=True,
            protective_order_matches=True,
            protective_order_id="EXIT-4",
        )
        self.assertEqual(record.protective_order_state, PROTECTED)
        self.assertTrue(ledger.can_submit_new_buy())

    def test_e_missing_protective_order_becomes_critical(self):
        from phoenix_core.protective_orders import CRITICAL, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-5")
        ledger.register_protective_order_accepted("6473.T", "EXIT-5")
        ledger.mark_transport_disconnected()
        ledger.mark_transport_reconnected()
        record = ledger.reconcile(
            "6473.T",
            position_matches=True,
            open_order_matches=True,
            protective_order_matches=False,
        )
        self.assertEqual(record.protective_order_state, CRITICAL)
        self.assertFalse(ledger.can_submit_new_buy())

    def test_f_disconnect_before_protection_is_critical(self):
        from phoenix_core.protective_orders import CRITICAL, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-6")
        ledger.mark_transport_disconnected()
        self.assertEqual(ledger.snapshot("6473.T").protective_order_state, CRITICAL)
        self.assertFalse(ledger.can_submit_new_buy())

    def test_g_next_day_reconcile_matches_full_protective_snapshot(self):
        from phoenix_core.protective_orders import PROTECTED, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-7")
        ledger.register_protective_order_submitted(
            "6473.T",
            "EXIT-7",
            protective_order_expiration="20260820",
        )
        ledger.register_protective_order_accepted("6473.T", "EXIT-7")
        ledger.mark_transport_disconnected()
        ledger.mark_transport_reconnected()

        record = ledger.reconcile(
            "6473.T",
            position_matches=True,
            open_order_matches=True,
            protective_order_matches=True,
            reported_ticker="6473.T",
            order_number="EXIT-7",
            quantity=100,
            target_price=2326.8,
            stop_price=2149.52,
            expiration="20260820",
            regular_order_status="有効",
            stop_order_status="有効",
            verified_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        self.assertEqual(record.protective_order_state, PROTECTED)
        self.assertEqual("20260820", record.protective_order_expiration)
        self.assertEqual("有効", record.regular_order_status)
        self.assertEqual("有効", record.stop_order_status)
        self.assertTrue(ledger.can_submit_new_buy())

    def test_h_next_day_reconcile_rejects_expired_or_mismatched_snapshot(self):
        from phoenix_core.protective_orders import CRITICAL, ProtectiveOrderLedger

        ledger = ProtectiveOrderLedger()
        ledger.register_buy_fill("6473.T", 100, 2210.0, 2326.8, 2149.52, buy_order_id="BUY-8")
        ledger.register_protective_order_submitted(
            "6473.T",
            "EXIT-8",
            protective_order_expiration="20260820",
        )
        ledger.register_protective_order_accepted("6473.T", "EXIT-8")
        ledger.mark_transport_disconnected()
        ledger.mark_transport_reconnected()

        record = ledger.reconcile(
            "6473.T",
            position_matches=True,
            open_order_matches=True,
            protective_order_matches=True,
            reported_ticker="6473.T",
            order_number="EXIT-8",
            quantity=100,
            target_price=2326.8,
            stop_price=2149.52,
            expiration="20260819",
            regular_order_status="有効",
            stop_order_status="有効",
            verified_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        self.assertEqual(record.protective_order_state, CRITICAL)
        self.assertFalse(ledger.can_submit_new_buy())
import unittest
