from __future__ import annotations

import unittest
from types import SimpleNamespace

import pandas as pd

from phoenix_core import OrderRequest, OrderSide, OrderType, PaperBroker
from phoenix_core.position_sizer import PositionSizingConfig, size_candidates
import phoenix_core.risk_controller as risk_controller
from phoenix_core.risk_controller import RiskConfig, RiskState, evaluate_orders


def make_order(ticker: str, price: float, cid: str, side: OrderSide = OrderSide.BUY) -> OrderRequest:
    return OrderRequest(
        ticker=ticker,
        side=side,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=price,
        client_order_id=cid,
    )


class RiskControllerV7Test(unittest.TestCase):
    def setUp(self) -> None:
        self.broker = PaperBroker(initial_cash_yen=300000)
        self.config = self._risk_config()

    def _risk_config(
        self,
        *,
        max_positions: int | None = 3,
        max_orders_per_run: int = 2,
        max_total_invested_pct: float = 0.95,
        bear_max_total_invested_pct: float = 0.70,
        max_single_position_pct: float = 0.30,
        risk_v2_enabled: bool = False,
        risk_policy_id: str = "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
        breadth_metric: str = "ABOVE_MA75_RATIO_ACTIVE225",
    ) -> RiskConfig:
        return RiskConfig(
            max_daily_loss_pct=0.03,
            max_drawdown_pct=0.10,
            max_positions=max_positions,
            max_total_invested_pct=max_total_invested_pct,
            max_single_position_pct=max_single_position_pct,
            max_orders_per_run=max_orders_per_run,
            max_consecutive_losses=3,
            minimum_cash_reserve_pct=0.10,
            risk_v2_enabled=risk_v2_enabled,
            breadth_threshold=0.40,
            bear_max_total_invested_pct=bear_max_total_invested_pct,
            risk_policy_id=risk_policy_id,
            breadth_metric=breadth_metric,
            market_regime_file="reports/market_regime.json",
        )

    def _market_context(
        self,
        *,
        breadth_ratio: float,
        threshold: float = 0.40,
        regime: str = "BULL",
    ) -> dict[str, object]:
        return {
            "breadth_ratio": breadth_ratio,
            "breadth_threshold": threshold,
            "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
            "regime": regime,
            "source_run_id": "RUN-001",
            "source_report_sha256": "a" * 64,
            "source_ticker_count": 225,
        }

    def test_approves_safe_order(self) -> None:
        report = evaluate_orders(
            self.broker,
            [make_order("9501.T", 500, "SAFE-1")],
            self.config,
            RiskState.new(300000),
        )
        self.assertEqual(1, len(report.accepted_orders))
        self.assertTrue(report.decisions[0].accepted)

    def test_blocks_daily_loss(self) -> None:
        state = RiskState.new(300000)
        state.start_of_day_equity_yen = 310000
        report = evaluate_orders(
            self.broker,
            [make_order("9501.T", 500, "LOSS-1")],
            self.config,
            state,
        )
        self.assertTrue(report.halted)
        self.assertEqual(0, len(report.accepted_orders))

    def test_blocks_too_many_orders(self) -> None:
        report = evaluate_orders(
            self.broker,
            [
                make_order("9501.T", 500, "M-1"),
                make_order("4902.T", 600, "M-2"),
                make_order("3697.T", 700, "M-3"),
            ],
            self.config,
            RiskState.new(300000),
        )
        self.assertEqual(2, len(report.accepted_orders))
        self.assertFalse(report.decisions[2].accepted)

    def test_blocks_single_position_limit(self) -> None:
        report = evaluate_orders(
            self.broker,
            [make_order("9984.T", 1000, "BIG-1")],
            self.config,
            RiskState.new(300000),
        )
        self.assertEqual(0, len(report.accepted_orders))
        self.assertIn("1銘柄", report.decisions[0].reason)

    def test_accepts_sell_risk_reduction_even_when_buy_limits_are_hit(self) -> None:
        config = self._risk_config(risk_v2_enabled=True)
        state = RiskState.new(300000)
        state.start_of_day_equity_yen = 400000
        report = evaluate_orders(
            self.broker,
            [make_order("9501.T", 500, "SELL-1", side=OrderSide.SELL)],
            config,
            state,
            market_context=self._market_context(breadth_ratio=0.50, regime="BULL"),
        )
        self.assertEqual(1, len(report.accepted_orders))
        self.assertTrue(report.decisions[0].accepted)

    def test_max_positions_none_skips_position_count_reject(self) -> None:
        config = self._risk_config(
            max_positions=None,
            max_orders_per_run=10,
            risk_v2_enabled=True,
        )
        report = evaluate_orders(
            self.broker,
            [
                make_order("9501.T", 500, "NONE-1"),
                make_order("4902.T", 600, "NONE-2"),
                make_order("3697.T", 700, "NONE-3"),
            ],
            config,
            RiskState.new(300000),
            market_context=self._market_context(breadth_ratio=0.55, regime="BULL"),
        )
        self.assertEqual(3, len(report.accepted_orders))
        self.assertTrue(all(decision.accepted for decision in report.decisions))

    def test_bear_cap_and_base_cap_are_applied_by_regime(self) -> None:
        config = self._risk_config(
            max_positions=None,
            max_orders_per_run=5,
            max_single_position_pct=1.0,
            risk_v2_enabled=True,
        )
        self.assertEqual(
            0.70,
            risk_controller.resolve_effective_total_invested_pct(
                config,
                self._market_context(breadth_ratio=0.3999, regime="BEAR"),
            ),
        )
        self.assertEqual(
            0.95,
            risk_controller.resolve_effective_total_invested_pct(
                config,
                self._market_context(breadth_ratio=0.4000, regime="BULL"),
            ),
        )
        bear_report = evaluate_orders(
            self.broker,
            [make_order("9501.T", 2200, "BEAR-1")],
            config,
            RiskState.new(300000),
            market_context=self._market_context(breadth_ratio=0.39, regime="BEAR"),
        )
        self.assertEqual(0, len(bear_report.accepted_orders))
        self.assertIn("総投資率上限", bear_report.decisions[0].reason)

        bull_report = evaluate_orders(
            self.broker,
            [make_order("9501.T", 2200, "BULL-1")],
            config,
            RiskState.new(300000),
            market_context=self._market_context(breadth_ratio=0.55, regime="BULL"),
        )
        self.assertEqual(1, len(bull_report.accepted_orders))
        self.assertTrue(bull_report.decisions[0].accepted)

    def test_size_candidates_downsizes_by_effective_cap_override(self) -> None:
        config = PositionSizingConfig(
            risk_per_trade_pct=1.0,
            max_position_pct=1.0,
            max_total_invested_pct=0.95,
            minimum_cash_reserve_pct=0.0,
            fallback_stop_distance_pct=0.03,
            lot_size=100,
            maximum_quantity_per_ticker=1000,
            allow_pyramiding=False,
            commission_buffer_pct=0.0,
        )
        broker = SimpleNamespace(
            broker_name="FAKE_BROKER",
            get_account_snapshot=lambda: SimpleNamespace(
                equity_yen=300000.0,
                cash_yen=300000.0,
                market_value_yen=50000.0,
                positions=(SimpleNamespace(ticker="7203.T", quantity=100, market_value=50000.0),),
            ),
        )
        candidates = pd.DataFrame(
            [
                {
                    "ticker": "1301.T",
                    "銘柄": "Sample",
                    "エントリー価格": 1000.0,
                    "損切価格": 900.0,
                    "ランキング点": 1.0,
                }
            ]
        )

        base_decision = size_candidates(broker, candidates, config)[0]
        bear_decision = size_candidates(
            broker,
            candidates,
            config,
            max_total_invested_pct_override=0.70,
        )[0]

        self.assertEqual(200, base_decision.recommended_quantity)
        self.assertEqual(100, bear_decision.recommended_quantity)
        self.assertLess(bear_decision.recommended_quantity, base_decision.recommended_quantity)

    def test_market_context_missing_or_inconsistent_fails_closed(self) -> None:
        config = self._risk_config(risk_v2_enabled=True)
        with self.assertRaises(ValueError):
            evaluate_orders(
                self.broker,
                [make_order("9501.T", 500, "CTX-1")],
                config,
                RiskState.new(300000),
            )

        with self.assertRaises(ValueError):
            evaluate_orders(
                self.broker,
                [make_order("9501.T", 500, "CTX-2")],
                config,
                RiskState.new(300000),
                market_context=self._market_context(breadth_ratio=0.39, regime="BULL"),
            )

        with self.assertRaises(ValueError):
            evaluate_orders(
                self.broker,
                [make_order("9501.T", 500, "CTX-3")],
                config,
                RiskState.new(300000),
                market_context={
                    **self._market_context(breadth_ratio=0.55, regime="BULL"),
                    "risk_policy_id": "WRONG_POLICY",
                },
            )

        with self.assertRaises(ValueError):
            evaluate_orders(
                self.broker,
                [make_order("9501.T", 500, "CTX-4")],
                config,
                RiskState.new(300000),
                market_context={
                    **self._market_context(breadth_ratio=0.55, regime="BULL"),
                    "breadth_metric": "WRONG_METRIC",
                },
            )


if __name__ == "__main__":
    unittest.main()
