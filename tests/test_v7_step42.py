from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from phoenix_core import historical_validation_20y as historical_validation
from phoenix_core.candidate_input_guard import CandidateInputAudit, CandidateInputBatch
from phoenix_core.data_freshness import JST
from phoenix_core.models import OrderRequest, OrderSide, OrderStatus, OrderType
from phoenix_core.position_sizer import SizingDecision
import phoenix_core.risk_controller as risk_controller
from phoenix_core.risk_controller import RiskDecision

import market_regime_ai as market_regime_ai_module
import phoenix_core.order_bridge_gate as gate
import trade_engine as trade_engine_module


class Step42PreOrderGateTest(unittest.TestCase):
    def _candidate_batch(self, *, generated_at: datetime) -> CandidateInputBatch:
        frame = pd.DataFrame(
            [
                {
                    "ticker": "1301.T",
                    "name": "Sample",
                    "signal_date": generated_at.isoformat(timespec="seconds"),
                    "side": "BUY",
                    "order_type": "LIMIT",
                    "entry_price": 1000.0,
                    "stop_price": 950.0,
                    "take_profit_price": 1100.0,
                    "lot_size": 100,
                }
            ]
        )
        audit = CandidateInputAudit(
            status="READY",
            source_path="reports/trade_signals.csv",
            input_sha256="a" * 64,
            eligible_candidates_sha256="b" * 64,
            input_rows=1,
            eligible_rows=1,
            rejected_rows=0,
            decision_counts=(("BUY", 1), ("WATCH", 0), ("SKIP", 0)),
            rejection_counts=(),
        )
        return CandidateInputBatch(frame, audit)

    def _decision(self, *, quantity: int = 100, stop_price: float = 950.0) -> SizingDecision:
        return SizingDecision(
            ticker="1301.T",
            name="Sample",
            entry_price=1000.0,
            stop_price=stop_price,
            held_quantity=0,
            risk_quantity=quantity,
            position_limit_quantity=quantity,
            cash_limit_quantity=quantity,
            portfolio_limit_quantity=quantity,
            maximum_quantity_limit=quantity,
            recommended_quantity=quantity,
            estimated_cost_yen=1000.0 * quantity,
            estimated_risk_yen=max(1000.0 - stop_price, 0.0) * quantity,
            status="READY",
            reason="",
            ranking_score=1.0,
        )

    def _configs(self) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        direct = {
            "candidate_input": {
                "enabled": True,
                "path": "reports/trade_signals.csv",
                "decision_column": "Trade判定",
                "execution_price_column": "押し目価格",
                "executable_values": ["BUY"],
                "known_values": ["BUY", "WATCH", "SKIP"],
                "fallback": False,
            },
            "operating_mode": "PAPER_SAFE",
        }
        sizing = {
            "position_sizing": {
                "lot_size": 100,
                "max_total_invested_pct": 0.95,
                "minimum_cash_reserve_pct": 0.0,
                "commission_buffer_pct": 0.0,
            }
        }
        risk = {
            "risk": {
                "max_daily_loss_pct": 0.03,
                "max_drawdown_pct": 0.10,
                "max_positions": None,
                "max_total_invested_pct": 0.95,
                "max_single_position_pct": 0.30,
                "max_orders_per_run": 3,
                "max_consecutive_losses": 3,
                "minimum_cash_reserve_pct": 0.10,
                "block_on_broker_health_failure": True,
            },
            "risk_v2_enabled": False,
            "breadth_threshold": 0.40,
            "bear_max_total_invested_pct": 0.70,
            "market_regime_file": "reports/market_regime.json",
            "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
        }
        return direct, sizing, risk

    def _patch_configs(self):
        direct, sizing, risk = self._configs()

        def fake_read_json(path: Path) -> tuple[dict[str, object], str | None]:
            name = path.name
            if name == "v7_direct_pipeline_config.json":
                return direct, None
            if name == "v7_position_sizer_config.json":
                return sizing, None
            if name == "v7_risk_config.json":
                return risk, None
            return {}, f"unexpected file: {path}"

        return mock.patch.object(gate, "_read_json", side_effect=fake_read_json)

    def _patch_pipeline(self, *, decision: SizingDecision, accepted: bool = True):
        fake_broker = SimpleNamespace(
            get_account_snapshot=lambda: SimpleNamespace(equity_yen=300_000.0)
        )
        fake_risk_report = SimpleNamespace(
            decisions=(
                RiskDecision(
                    ticker="1301.T",
                    side="BUY",
                    quantity=decision.recommended_quantity,
                    price=decision.entry_price,
                    accepted=accepted,
                    reason="" if accepted else "RISK_BLOCK",
                    estimated_value_yen=decision.entry_price * decision.recommended_quantity,
                ),
            )
        )
        return (
            mock.patch.object(gate, "_load_candidate_batch", return_value=(self._candidate_batch(generated_at=GENERATED_AT), None, Path("reports/trade_signals.csv"))),
            mock.patch.object(gate, "_load_broker", return_value=(fake_broker, None)),
            mock.patch.object(gate, "size_candidates", return_value=(decision,)),
            mock.patch.object(gate, "load_risk_state", return_value=SimpleNamespace()),
            mock.patch.object(gate, "evaluate_orders", return_value=fake_risk_report),
        )

    def _write_provenance_files(
        self,
        root: Path,
        *,
        source_manifest: dict[str, object],
        market_regime: dict[str, object],
    ) -> tuple[str, str]:
        reports_dir = root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        trade_signals_path = reports_dir / "trade_signals.csv"
        trade_signals_path.write_text(
            "ticker,signal_date\n1301.T,2026-08-04T12:00:00+09:00\n",
            encoding="utf-8-sig",
        )
        market_regime_path = reports_dir / "market_regime.json"
        market_regime_path.write_text(
            json.dumps(market_regime, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return (
            hashlib.sha256(trade_signals_path.read_bytes()).hexdigest(),
            hashlib.sha256(market_regime_path.read_bytes()).hexdigest(),
        )

    def _live_order(
        self,
        client_order_id: str,
        *,
        ticker: str = "1301.T",
        quantity: int = 75,
        limit_price: float = 1000.0,
    ) -> OrderRequest:
        return OrderRequest(
            ticker=ticker,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            client_order_id=client_order_id,
            strategy_name="PHOENIX_AUTO_LIVE",
        )

    def _dispatch_context(
        self,
        *,
        root: Path,
        operating_mode: str,
        orders: list[OrderRequest],
        trade_signals_context: dict[str, object],
    ) -> gate.PreorderDispatchContext:
        report = {
            "schema_version": gate.SCHEMA_VERSION,
            "version": gate.VERSION,
            "generated_at": "2026-08-04T12:00:00+09:00",
            "expires_at": "2026-08-04T12:15:00+09:00",
            "status": "APPROVED",
            "mode": "LIVE" if operating_mode != "PAPER_SAFE" else "PAPER",
            "trading_mode": "LIVE" if operating_mode != "PAPER_SAFE" else "PAPER",
            "execution_mode": "LIVE" if operating_mode != "PAPER_SAFE" else "DRY_RUN",
            "trading_actions": "LIVE_ONLY"
            if operating_mode == "LIVE_ACTIVE"
            else "RECONCILE_ONLY"
            if operating_mode == "LIVE_RECONCILE_ONLY"
            else "PAPER_ONLY",
            "operating_scope": "OPERATIONAL",
            "orders_submitted": 0,
            "external_orders_submitted": 0,
            "candidate_count": len(orders),
            "approved_count": len(orders),
            "blocked_count": 0,
            "blockers": [],
            "candidate_input_guard": {"status": "READY"},
            "instructions": [{"client_order_id": order.client_order_id} for order in orders],
            "instruction_file": str(root / "reports" / "v7_real_trade_preorder_instructions.csv"),
            "report_json": str(root / "reports" / "v7_real_trade_preorder_report.json"),
            "report_text": str(root / "reports" / "v7_real_trade_preorder_report.txt"),
            "audit_jsonl": str(root / "reports" / "v7_real_trade_preorder_audit.jsonl"),
            "state_file": str(root / "state" / "v7_real_trade_preorder_state.json"),
            "source": "reports/trade_signals.csv",
            "created_by": gate.CREATED_BY,
        }
        approved_payloads = {
            order.client_order_id: {"client_order_id": order.client_order_id}
            for order in orders
        }
        return gate.PreorderDispatchContext(
            report=report,
            generated_at=datetime(2026, 8, 4, 12, 0, tzinfo=JST),
            expires_at=datetime(2026, 8, 4, 12, 15, tzinfo=JST),
            state_path=root / "state" / "v7_real_trade_preorder_state.json",
            config=self._dispatch_config(operating_mode=operating_mode),
            approved_idempotency_keys=frozenset(),
            report_blockers=(),
            trade_signals_context=trade_signals_context,
            executable_orders_by_client_order_id={
                order.client_order_id: order for order in orders
            },
            accepted_orders_by_client_order_id={
                order.client_order_id: order for order in orders
            },
            approved_payloads_by_client_order_id=approved_payloads,
        )

    def _dispatch_config(self, *, operating_mode: str) -> dict[str, object]:
        if operating_mode == "LIVE_ACTIVE":
            trading_actions = "LIVE_ONLY"
            armed = True
        elif operating_mode == "LIVE_RECONCILE_ONLY":
            trading_actions = "RECONCILE_ONLY"
            armed = False
        else:
            trading_actions = "PAPER_ONLY"
            armed = False
        return {
            "operating_mode": operating_mode,
            "trading_mode": "LIVE" if operating_mode != "PAPER_SAFE" else "PAPER",
            "execution_mode": "LIVE" if operating_mode != "PAPER_SAFE" else "DRY_RUN",
            "trading_actions": trading_actions,
            "allowed_trading_actions": [trading_actions] if operating_mode != "PAPER_SAFE" else ["DISABLED", "PAPER_ONLY"],
            "live_authorization_enabled": operating_mode == "LIVE_ACTIVE",
            "broker": {
                "type": "rakuten_rss" if operating_mode != "PAPER_SAFE" else "paper",
                "transport_mode": "production" if operating_mode != "PAPER_SAFE" else "paper",
                "live_trading_enabled": operating_mode != "PAPER_SAFE",
                "production_transport_enabled": operating_mode != "PAPER_SAFE",
                "production_live_fire_armed": armed,
            },
        }

    class _FakeLiveDispatchBroker:
        def __init__(
            self,
            *,
            healthy: bool = True,
            nonterminal_count: int = 0,
            submit_results: list[object] | None = None,
        ) -> None:
            self.broker_name = "FAKE_LIVE_BROKER"
            self._healthy = healthy
            self._nonterminal_count = nonterminal_count
            self._submit_results = list(submit_results or [])
            self.refresh_calls = 0
            self.submit_calls = 0
            self.submitted_client_order_ids: list[str] = []

        def health_check(self) -> SimpleNamespace:
            return SimpleNamespace(healthy=self._healthy, message="OK")

        def refresh_pending_orders(self) -> list[object]:
            self.refresh_calls += 1
            return []

        def nonterminal_order_count(self) -> int:
            return self._nonterminal_count

        def submit_order(self, order: OrderRequest) -> object:
            self.submit_calls += 1
            self.submitted_client_order_ids.append(order.client_order_id)
            if self._submit_results:
                return self._submit_results.pop(0)
            return SimpleNamespace(status=OrderStatus.FILLED, message="FILLED")

    def test_signal_timestamp_and_row_blockers_fail_closed(self) -> None:
        generated_at = datetime(2026, 8, 4, 12, 0, tzinfo=JST)
        future, future_error = gate._parse_signal_timestamp(
            (generated_at + timedelta(minutes=6)).isoformat(),
            generated_at,
        )
        self.assertIsNone(future)
        self.assertEqual("SIGNAL_DATE_IN_THE_FUTURE", future_error)

        stale, stale_error = gate._parse_signal_timestamp(
            (generated_at - timedelta(hours=25)).isoformat(),
            generated_at,
        )
        self.assertIsNone(stale)
        self.assertEqual("SIGNAL_DATE_TOO_OLD", stale_error)

        blockers = gate._row_blockers(
            operating_scope="OPERATIONAL",
            trading_actions="PAPER_ONLY",
            decision=self._decision(quantity=100, stop_price=950.0),
            risk_reason=None,
            signal_error=None,
            signal_timestamp=generated_at,
            side="BUY",
            order_type="LIMIT",
            take_profit_price=None,
            reference_price=1000.0,
            stop_loss_price=950.0,
            max_loss_limit_yen=4_000.0,
            approved_keys={"dup"},
            idempotency_key="dup",
            global_blockers=[],
        )
        self.assertIn("TAKE_PROFIT_MISSING", blockers)
        self.assertIn("MAX_LOSS_LIMIT_EXCEEDED", blockers)
        self.assertIn("DUPLICATE_IDEMPOTENCY_KEY", blockers)

        quantity_blockers = gate._row_blockers(
            operating_scope="OPERATIONAL",
            trading_actions="PAPER_ONLY",
            decision=SizingDecision(
                ticker="1301.T",
                name="Sample",
                entry_price=1000.0,
                stop_price=950.0,
                held_quantity=0,
                risk_quantity=0,
                position_limit_quantity=0,
                cash_limit_quantity=0,
                portfolio_limit_quantity=0,
                maximum_quantity_limit=0,
                recommended_quantity=0,
                estimated_cost_yen=0.0,
                estimated_risk_yen=0.0,
                status="SKIP",
                reason="NO_SIGNAL",
                ranking_score=0.0,
            ),
            risk_reason=None,
            signal_error=None,
            signal_timestamp=generated_at,
            side="BUY",
            order_type="LIMIT",
            take_profit_price=1100.0,
            reference_price=1000.0,
            stop_loss_price=950.0,
            max_loss_limit_yen=10_000.0,
            approved_keys=set(),
            idempotency_key="unique",
            global_blockers=[],
        )
        self.assertIn("POSITION_SIZER:NO_SIGNAL", quantity_blockers)

        price_blockers = gate._row_blockers(
            operating_scope="OPERATIONAL",
            trading_actions="PAPER_ONLY",
            decision=self._decision(quantity=100, stop_price=950.0),
            risk_reason=None,
            signal_error=None,
            signal_timestamp=generated_at,
            side="BUY",
            order_type="LIMIT",
            take_profit_price=990.0,
            reference_price=1000.0,
            stop_loss_price=950.0,
            max_loss_limit_yen=10_000.0,
            approved_keys=set(),
            idempotency_key="unique",
            global_blockers=[],
        )
        self.assertIn("PRICE_RELATION_INVALID", price_blockers)

    def test_monitor_only_report_is_blocked_and_writes_utf8_csv_and_audit_jsonl(self) -> None:
        generated_at = datetime(2026, 8, 4, 12, 0, tzinfo=JST)
        decision = self._decision(quantity=100, stop_price=950.0)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_manifest = {
                "schema_version": 1,
                "run_id": "RUN-OK",
                "generated_at": "2026-08-04T12:00:00+09:00",
                "report_file": "reports/report_20260804.csv",
                "report_sha256": "1" * 64,
                "ticker_count": 225,
                "expected_ticker_count": 225,
                "ticker_universe_sha256": "2" * 64,
                "market_data_evidence": {"status": "READY"},
            }
            market_regime = {
                "schema_version": 2,
                "source_run_id": "RUN-OK",
                "source_report_sha256": "1" * 64,
                "source_ticker_count": 225,
                "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
                "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
                "breadth_ratio": 0.55,
                "breadth_threshold": 0.40,
                "regime": "BULL",
            }
            trade_signals_sha256, market_regime_sha256 = self._write_provenance_files(
                root,
                source_manifest=source_manifest,
                market_regime=market_regime,
            )
            trade_signals_manifest = {
                "schema_version": 1,
                "generated_at": "2026-08-04T12:00:00+09:00",
                "source_run_id": source_manifest["run_id"],
                "source_report_sha256": source_manifest["report_sha256"],
                "source_ticker_count": source_manifest["ticker_count"],
                "ai_judgement_sha256": "4" * 64,
                "market_regime_sha256": market_regime_sha256,
                "trade_signals_sha256": trade_signals_sha256,
                "trade_signals_row_count": 1,
            }
            patches = [
                self._patch_configs(),
                mock.patch.object(
                    gate,
                    "_load_candidate_batch",
                    return_value=(self._candidate_batch(generated_at=generated_at), None, root / "reports" / "trade_signals.csv"),
                ),
                mock.patch.object(gate, "_load_broker", return_value=(SimpleNamespace(get_account_snapshot=lambda: SimpleNamespace(equity_yen=300_000.0)), None)),
                mock.patch.object(gate, "size_candidates", return_value=(decision,)),
                mock.patch.object(gate, "load_risk_state", return_value=SimpleNamespace()),
                mock.patch.object(
                    gate,
                    "evaluate_orders",
                    return_value=SimpleNamespace(
                        decisions=(
                            RiskDecision(
                                ticker="1301.T",
                                side="BUY",
                                quantity=decision.recommended_quantity,
                                price=decision.entry_price,
                                accepted=True,
                                reason="",
                                estimated_value_yen=decision.entry_price * decision.recommended_quantity,
                            ),
                        )
                    ),
                ),
            ]
            with (
                mock.patch.dict(
                    gate.os.environ,
                    {
                        "PHOENIX_OPERATING_SCOPE": "MONITOR_ONLY",
                        "PHOENIX_TRADING_ACTIONS": "DISABLED",
                    },
                    clear=False,
                ),
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patches[4],
                patches[5],
            ):
                def fake_read_json(path: Path) -> tuple[dict[str, object], str | None]:
                    name = path.name
                    if name == "v7_direct_pipeline_config.json":
                        return self._configs()[0], None
                    if name == "v7_position_sizer_config.json":
                        return self._configs()[1], None
                    if name == "v7_risk_config.json":
                        return self._configs()[2], None
                    if name == "notification_source_manifest.json":
                        return source_manifest, None
                    if name == "trade_signals_manifest.json":
                        return trade_signals_manifest, None
                    if name == "market_regime.json":
                        return market_regime, None
                    return {}, f"unexpected file: {path}"

                with mock.patch.object(gate, "_read_json", side_effect=fake_read_json):
                    report = gate.build_preorder_report(root, generated_at=generated_at)
                gate.save_preorder_outputs(root, report)

            self.assertEqual("BLOCKED", report["status"])
            self.assertEqual("PAPER", report["mode"])
            self.assertEqual("PAPER", report["trading_mode"])
            self.assertEqual("DRY_RUN", report["execution_mode"])
            self.assertEqual(0, report["orders_submitted"])
            self.assertIn("MONITOR_ONLY_SCOPE", report["blockers"])
            self.assertEqual("BLOCKED", report["instructions"][0]["status"])

            instruction_path = Path(report["instruction_file"])
            audit_path = Path(report["audit_jsonl"])
            self.assertTrue(instruction_path.exists())
            self.assertTrue(audit_path.exists())
            self.assertTrue(instruction_path.read_bytes().startswith(b"\xef\xbb\xbf"))

            csv_text = instruction_path.read_text(encoding="utf-8-sig")
            self.assertIn("BLOCKED", csv_text)

            audit_lines = audit_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(2, len(audit_lines))
            self.assertEqual("instruction", json.loads(audit_lines[0])["kind"])
            self.assertEqual("summary", json.loads(audit_lines[1])["kind"])
            self.assertEqual(0, json.loads(audit_lines[1])["orders_submitted"])

    def test_operational_report_is_approved_without_submitting_orders(self) -> None:
        generated_at = datetime(2026, 8, 4, 12, 0, tzinfo=JST)
        decision = self._decision(quantity=100, stop_price=950.0)
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_manifest = {
                "schema_version": 1,
                "run_id": "RUN-OK",
                "generated_at": "2026-08-04T12:00:00+09:00",
                "report_file": "reports/report_20260804.csv",
                "report_sha256": "1" * 64,
                "ticker_count": 225,
                "expected_ticker_count": 225,
                "ticker_universe_sha256": "2" * 64,
                "market_data_evidence": {"status": "READY"},
            }
            market_regime = {
                "schema_version": 2,
                "source_run_id": "RUN-OK",
                "source_report_sha256": "1" * 64,
                "source_ticker_count": 225,
                "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
                "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
                "breadth_ratio": 0.55,
                "breadth_threshold": 0.40,
                "regime": "BULL",
            }
            trade_signals_sha256, market_regime_sha256 = self._write_provenance_files(
                root,
                source_manifest=source_manifest,
                market_regime=market_regime,
            )
            trade_signals_manifest = {
                "schema_version": 1,
                "generated_at": "2026-08-04T12:00:00+09:00",
                "source_run_id": source_manifest["run_id"],
                "source_report_sha256": source_manifest["report_sha256"],
                "source_ticker_count": source_manifest["ticker_count"],
                "ai_judgement_sha256": "4" * 64,
                "market_regime_sha256": market_regime_sha256,
                "trade_signals_sha256": trade_signals_sha256,
                "trade_signals_row_count": 1,
            }
            patches = [
                self._patch_configs(),
                mock.patch.object(
                    gate,
                    "_load_candidate_batch",
                    return_value=(self._candidate_batch(generated_at=generated_at), None, root / "reports" / "trade_signals.csv"),
                ),
                mock.patch.object(gate, "_load_broker", return_value=(SimpleNamespace(get_account_snapshot=lambda: SimpleNamespace(equity_yen=300_000.0)), None)),
                mock.patch.object(gate, "size_candidates", return_value=(decision,)),
                mock.patch.object(gate, "load_risk_state", return_value=SimpleNamespace()),
                mock.patch.object(
                    gate,
                    "evaluate_orders",
                    return_value=SimpleNamespace(
                        decisions=(
                            RiskDecision(
                                ticker="1301.T",
                                side="BUY",
                                quantity=decision.recommended_quantity,
                                price=decision.entry_price,
                                accepted=True,
                                reason="",
                                estimated_value_yen=decision.entry_price * decision.recommended_quantity,
                            ),
                        )
                    ),
                ),
            ]
            with (
                mock.patch.dict(
                    gate.os.environ,
                    {
                        "PHOENIX_OPERATING_SCOPE": "OPERATIONAL",
                        "PHOENIX_TRADING_ACTIONS": "PAPER_ONLY",
                    },
                    clear=False,
                ),
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patches[4],
                patches[5],
            ):
                def fake_read_json(path: Path) -> tuple[dict[str, object], str | None]:
                    name = path.name
                    if name == "v7_direct_pipeline_config.json":
                        return self._configs()[0], None
                    if name == "v7_position_sizer_config.json":
                        return self._configs()[1], None
                    if name == "v7_risk_config.json":
                        return self._configs()[2], None
                    if name == "notification_source_manifest.json":
                        return source_manifest, None
                    if name == "trade_signals_manifest.json":
                        return trade_signals_manifest, None
                    if name == "market_regime.json":
                        return market_regime, None
                    return {}, f"unexpected file: {path}"

                with mock.patch.object(gate, "_read_json", side_effect=fake_read_json):
                    report = gate.build_preorder_report(root, generated_at=generated_at)
                gate.save_preorder_outputs(root, report)

            self.assertEqual("APPROVED", report["status"])
            self.assertEqual(1, report["approved_count"])
            self.assertEqual(0, report["blocked_count"])
            self.assertEqual(0, report["orders_submitted"])
            self.assertEqual("APPROVED", report["instructions"][0]["status"])
            self.assertEqual("", report["instructions"][0]["blocked_reasons"])

            instruction_path = Path(report["instruction_file"])
            audit_path = Path(report["audit_jsonl"])
            self.assertTrue(instruction_path.read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertTrue(audit_path.exists())

            audit_lines = audit_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(2, len(audit_lines))
            self.assertEqual("APPROVED", json.loads(audit_lines[1])["status"])
            self.assertEqual(0, json.loads(audit_lines[1])["orders_submitted"])

    def test_risk_v2_manifest_mismatch_fail_closed(self) -> None:
        generated_at = datetime(2026, 8, 4, 12, 0, tzinfo=JST)
        decision = self._decision(quantity=100, stop_price=950.0)
        direct, sizing, risk = self._configs()
        risk["risk_v2_enabled"] = True
        source_manifest = {
            "schema_version": 1,
            "run_id": "RUN-OK",
            "generated_at": "2026-08-04T12:00:00+09:00",
            "report_file": "reports/report_20260804.csv",
            "report_sha256": "1" * 64,
            "ticker_count": 225,
            "expected_ticker_count": 225,
            "ticker_universe_sha256": "2" * 64,
            "market_data_evidence": {"status": "READY"},
        }
        market_regime = {
            "schema_version": 2,
            "source_run_id": "RUN-OK",
            "source_report_sha256": "3" * 64,
            "source_ticker_count": 225,
            "breadth_ratio": 0.55,
            "breadth_threshold": 0.40,
            "regime": "BULL",
        }
        def fake_read_json(path: Path) -> tuple[dict[str, object], str | None]:
            name = path.name
            if name == "v7_direct_pipeline_config.json":
                return direct, None
            if name == "v7_position_sizer_config.json":
                return sizing, None
            if name == "v7_risk_config.json":
                return risk, None
            if name == "notification_source_manifest.json":
                return source_manifest, None
            if name == "trade_signals_manifest.json":
                return {
                    "schema_version": 1,
                    "generated_at": "2026-08-04T12:00:00+09:00",
                    "source_run_id": source_manifest["run_id"],
                    "source_report_sha256": source_manifest["report_sha256"],
                    "source_ticker_count": source_manifest["ticker_count"],
                    "ai_judgement_sha256": "4" * 64,
                    "market_regime_sha256": market_regime_sha256,
                    "trade_signals_sha256": trade_signals_sha256,
                    "trade_signals_row_count": 1,
                }, None
            if name == "market_regime.json":
                return market_regime, None
            return {}, f"unexpected file: {path}"

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            trade_signals_sha256, market_regime_sha256 = self._write_provenance_files(
                root,
                source_manifest=source_manifest,
                market_regime=market_regime,
            )
            with (
                mock.patch.object(gate, "_read_json", side_effect=fake_read_json),
                mock.patch.object(
                    gate,
                    "_load_candidate_batch",
                    return_value=(self._candidate_batch(generated_at=generated_at), None, root / "reports" / "trade_signals.csv"),
                ),
                mock.patch.object(gate, "_load_broker", return_value=(SimpleNamespace(get_account_snapshot=lambda: SimpleNamespace(equity_yen=300_000.0)), None)),
                mock.patch.object(gate, "size_candidates", return_value=(decision,)),
                mock.patch.object(gate, "load_risk_state", return_value=SimpleNamespace()),
                mock.patch.object(gate, "evaluate_orders") as evaluate_orders_mock,
                mock.patch.dict(
                    gate.os.environ,
                    {
                        "PHOENIX_OPERATING_SCOPE": "OPERATIONAL",
                        "PHOENIX_TRADING_ACTIONS": "PAPER_ONLY",
                    },
                    clear=False,
                ),
            ):
                report = gate.build_preorder_report(root, generated_at=generated_at)

        self.assertEqual("BLOCKED", report["status"])
        self.assertIn("MARKET_REGIME_STALE", " ".join(report["blockers"]))
        self.assertIn("MANIFEST_MISMATCH", " ".join(report["blockers"]))
        evaluate_orders_mock.assert_not_called()

    def test_trade_engine_provenance_and_manifest_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            reports_dir = root / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_file = reports_dir / "report_20260804.csv"
            report_file.write_text("ticker,価格\n1301.T,1000\n", encoding="utf-8-sig")
            report_sha256 = hashlib.sha256(report_file.read_bytes()).hexdigest()
            ai_csv_file = reports_dir / "ai_judgement.csv"
            ai_csv_file.write_text("ticker,AI判断点\n1301.T,90\n", encoding="utf-8-sig")
            ai_sha256 = hashlib.sha256(ai_csv_file.read_bytes()).hexdigest()
            source_manifest = {
                "schema_version": 1,
                "run_id": "RUN-ROUND-TRIP",
                "generated_at": "2026-08-04T12:00:00+09:00",
                "report_file": report_file.name,
                "report_sha256": report_sha256,
                "ticker_count": 225,
                "expected_ticker_count": 225,
                "ticker_universe_sha256": "2" * 64,
                "market_data_evidence": {"status": "READY"},
            }
            ai_manifest = {
                "schema_version": 1,
                "run_id": source_manifest["run_id"],
                "generated_at": "2026-08-04T12:00:00+09:00",
                "input_report_file": source_manifest["report_file"],
                "input_report_sha256": source_manifest["report_sha256"],
                "ai_judgement_file": ai_csv_file.name,
                "ai_judgement_sha256": ai_sha256,
                "ticker_count": 1,
            }
            market_regime = {
                "schema_version": 2,
                "source_run_id": source_manifest["run_id"],
                "source_report_sha256": source_manifest["report_sha256"],
                "source_ticker_count": 225,
                "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
                "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
                "breadth_ratio": 0.55,
                "breadth_threshold": 0.40,
                "regime": "BULL",
            }
            source_manifest_path = reports_dir / "notification_source_manifest.json"
            ai_manifest_path = reports_dir / "ai_judgement_manifest.json"
            market_regime_path = reports_dir / "market_regime.json"
            source_manifest_path.write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            ai_manifest_path.write_text(json.dumps(ai_manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            market_regime_path.write_text(json.dumps(market_regime, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            trade_signal_df = pd.DataFrame(
                [
                    {
                        "銘柄": "Sample",
                        "ticker": "1301.T",
                        "Trade判定": "BUY",
                        "AI判断": "BUY",
                        "AI判断点": 90,
                        "PHOENIX_SCORE": 90,
                        "RSI": 50,
                        "MACD判定": "OK",
                        "基準価格": 1000,
                        "押し目価格": 990,
                        "利確価格": 1100,
                        "損切価格": 950,
                        "ロット比率": 1.0,
                        "MarketRiskScore": 50,
                        "MarketRiskLevel": "NORMAL",
                        "判定理由": "OK",
                        "生成日時": "2026-08-04 12:00:00",
                    }
                ]
            )
            watchlist_df = pd.DataFrame(columns=trade_signal_df.columns)
            with (
                mock.patch.object(trade_engine_module, "REPORT_DIR", reports_dir),
                mock.patch.object(trade_engine_module, "NOTIFICATION_SOURCE_MANIFEST_FILE", source_manifest_path),
                mock.patch.object(trade_engine_module, "AI_JUDGEMENT_MANIFEST_FILE", ai_manifest_path),
                mock.patch.object(trade_engine_module, "MARKET_REGIME_FILE", market_regime_path),
                mock.patch.object(trade_engine_module, "TRADE_SIGNAL_FILE", reports_dir / "trade_signals.csv"),
                mock.patch.object(trade_engine_module, "TRADE_SIGNAL_MANIFEST_FILE", reports_dir / "trade_signals_manifest.json"),
                mock.patch.object(trade_engine_module, "TEXT_REPORT_FILE", reports_dir / "trade_engine_report.txt"),
            ):
                loaded_source_manifest, loaded_ai_manifest, loaded_market_regime = trade_engine_module.load_trade_signal_provenance()
                trade_engine_module.save_outputs(
                    trade_signal_df,
                    watchlist_df,
                    {"score": 50, "level": "NORMAL"},
                    loaded_source_manifest,
                    loaded_ai_manifest,
                    loaded_market_regime,
                )

            manifest = json.loads((reports_dir / "trade_signals_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(source_manifest["run_id"], loaded_source_manifest["run_id"])
            self.assertEqual(source_manifest["report_sha256"], loaded_ai_manifest["input_report_sha256"])
            self.assertEqual(source_manifest["run_id"], loaded_market_regime["source_run_id"])
            self.assertEqual(source_manifest["run_id"], manifest["source_run_id"])
            self.assertEqual(source_manifest["report_sha256"], manifest["source_report_sha256"])
            self.assertTrue(market_regime_path.is_file())
            self.assertEqual(1, manifest["trade_signals_row_count"])
            self.assertEqual(64, len(manifest["trade_signals_sha256"]))

    def test_risk_v2_static_equivalence_and_max_positions_none_no_count_reject(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        historical_config = json.loads(
            (repo_root / "config" / "v7_historical_validation_20y.json").read_text(encoding="utf-8")
        )
        live_config = json.loads(
            (repo_root / "config" / "v7_risk_config.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            historical_validation.DEFAULT_MAX_TOTAL_INVESTED_PCT,
            historical_config["historical_validation_20y"]["max_total_invested_pct"],
        )
        self.assertEqual(
            historical_validation.DEFAULT_MARKET_BREADTH_BEAR_THRESHOLD,
            live_config["breadth_threshold"],
        )
        self.assertEqual(
            historical_validation.DEFAULT_MARKET_BREADTH_BEAR_MAX_TOTAL_INVESTED_PCT,
            live_config["bear_max_total_invested_pct"],
        )
        self.assertEqual(0.95, live_config["risk"]["max_total_invested_pct"])
        self.assertEqual(80_000.0, risk_controller._portfolio_capacity_yen(100_000.0, 15_000.0, 0.95))
        self.assertEqual(55_000.0, risk_controller._portfolio_capacity_yen(100_000.0, 15_000.0, 0.70))

        config = risk_controller.RiskConfig(
            max_positions=None,
            max_total_invested_pct=0.95,
            max_single_position_pct=1.0,
            risk_v2_enabled=True,
            risk_policy_id="RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            breadth_metric="ABOVE_MA75_RATIO_ACTIVE225",
            breadth_threshold=0.40,
            bear_max_total_invested_pct=0.70,
        )
        broker = SimpleNamespace(
            broker_name="FAKE_BROKER",
            health_check=lambda: SimpleNamespace(healthy=True, message="OK"),
            get_account_snapshot=lambda: SimpleNamespace(
                equity_yen=100_000.0,
                cash_yen=85_000.0,
                market_value_yen=15_000.0,
                positions=(SimpleNamespace(ticker="7203.T", market_value=15_000.0),),
            ),
        )
        state = risk_controller.RiskState.new(100_000.0)
        orders = [
            OrderRequest(
                ticker="1301.T",
                side=OrderSide.BUY,
                quantity=10,
                order_type=OrderType.LIMIT,
                limit_price=1_000.0,
                client_order_id="LIVE-COUNT-001",
                strategy_name="PHOENIX_AUTO_LIVE",
            ),
            OrderRequest(
                ticker="1302.T",
                side=OrderSide.BUY,
                quantity=10,
                order_type=OrderType.LIMIT,
                limit_price=1_000.0,
                client_order_id="LIVE-COUNT-002",
                strategy_name="PHOENIX_AUTO_LIVE",
            ),
        ]
        market_context = {
            "breadth_ratio": 0.50,
            "breadth_threshold": 0.40,
            "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
            "regime": "BULL",
            "source_run_id": "RUN-COUNT",
            "source_report_sha256": "1" * 64,
            "source_ticker_count": 225,
        }

        report = risk_controller.evaluate_orders(broker, orders, config, state, market_context=market_context)

        self.assertEqual(2, len(report.accepted_orders))

    def test_risk_v2_breadth_threshold_boundary_and_bear_overlay(self) -> None:
        config = risk_controller.RiskConfig(
            max_positions=None,
            max_total_invested_pct=0.95,
            max_single_position_pct=1.0,
            risk_v2_enabled=True,
            risk_policy_id="RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            breadth_metric="ABOVE_MA75_RATIO_ACTIVE225",
            breadth_threshold=0.40,
            bear_max_total_invested_pct=0.70,
        )
        broker = SimpleNamespace(
            broker_name="FAKE_BROKER",
            health_check=lambda: SimpleNamespace(healthy=True, message="OK"),
            get_account_snapshot=lambda: SimpleNamespace(
                equity_yen=100_000.0,
                cash_yen=85_000.0,
                market_value_yen=15_000.0,
                positions=(SimpleNamespace(ticker="7203.T", market_value=15_000.0),),
            ),
        )
        order = OrderRequest(
            ticker="1301.T",
            side=OrderSide.BUY,
            quantity=75,
            order_type=OrderType.LIMIT,
            limit_price=1_000.0,
            client_order_id="LIVE-BREADTH-001",
            strategy_name="PHOENIX_AUTO_LIVE",
        )
        bull_context = {
            "breadth_ratio": 0.4000,
            "breadth_threshold": 0.40,
            "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
            "regime": "BULL",
            "source_run_id": "RUN-BULL",
            "source_report_sha256": "2" * 64,
            "source_ticker_count": 225,
        }
        bear_context = {
            "breadth_ratio": 0.3999,
            "breadth_threshold": 0.40,
            "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
            "regime": "BEAR",
            "source_run_id": "RUN-BEAR",
            "source_report_sha256": "2" * 64,
            "source_ticker_count": 225,
        }

        bull_report = risk_controller.evaluate_orders(
            broker,
            [order],
            config,
            risk_controller.RiskState.new(100_000.0),
            market_context=bull_context,
        )
        bear_report = risk_controller.evaluate_orders(
            broker,
            [order],
            config,
            risk_controller.RiskState.new(100_000.0),
            market_context=bear_context,
        )

        self.assertEqual(1, len(bull_report.accepted_orders))
        self.assertEqual(0, len(bear_report.accepted_orders))

    def test_market_regime_ai_ma75_contract_ignores_legacy_bear_override_and_fail_closes_invalid_reports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)
            (root / "data").mkdir(parents=True, exist_ok=True)

            risk_config = {
                "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
                "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
                "breadth_threshold": 0.40,
                "bear_max_total_invested_pct": 0.70,
            }
            (root / "config" / "v7_risk_config.json").write_text(
                json.dumps(risk_config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            rows = []
            for index in range(225):
                above = index < 150
                price_raw = 100.0049 if above else 100.0041
                ma75_raw = 100.0041 if above else 100.0049
                rows.append(
                    {
                        "ticker": f"{1301 + index}.T",
                        "価格": round(price_raw, 2),
                        "MA25": 99.99,
                        "MA75": round(ma75_raw, 2),
                        "price_raw": price_raw,
                        "ma75_raw": ma75_raw,
                        "前日比%": 0.5 if above else -0.5,
                        "MACD判定": "GC" if above else "DC",
                        "RSI": 55.0 if above else 45.0,
                    }
                )
            report = pd.DataFrame(rows)
            report_path = root / "reports" / "report_20260825.csv"
            report.to_csv(report_path, index=False, encoding="utf-8-sig")
            report_sha256 = hashlib.sha256(report_path.read_bytes()).hexdigest()
            manifest = {
                "schema_version": 1,
                "run_id": "RUN-MA75-225",
                "generated_at": "2026-08-25T09:00:00+09:00",
                "report_file": "reports/report_20260825.csv",
                "report_sha256": report_sha256,
                "ticker_count": 225,
                "expected_ticker_count": 225,
                "ticker_universe_sha256": "9" * 64,
                "market_data_evidence": {"status": "READY"},
            }
            (root / "reports" / "notification_source_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "data" / "market_risk_latest.json").write_text(
                json.dumps({"regime": "BEAR", "score": -9.9}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            payload = market_regime_ai_module.build_market_regime(root)

            self.assertEqual("RISK_V2_PRODUCTION_MA75_BREADTH_V1", payload["risk_policy_id"])
            self.assertEqual("ABOVE_MA75_RATIO_ACTIVE225", payload["breadth_metric"])
            self.assertEqual(225, payload["source_ticker_count"])
            self.assertEqual("BULL", payload["regime"])
            self.assertAlmostEqual(150 / 225, payload["breadth_ratio"], places=6)

            invalid_rows = list(rows)
            invalid_rows[0] = {**invalid_rows[0], "ma75_raw": 0.0}
            invalid_report = pd.DataFrame(invalid_rows[:224])
            invalid_report_path = root / "reports" / "report_20260825_invalid.csv"
            invalid_report.to_csv(invalid_report_path, index=False, encoding="utf-8-sig")
            invalid_manifest = {
                **manifest,
                "report_file": "reports/report_20260825_invalid.csv",
                "report_sha256": hashlib.sha256(invalid_report_path.read_bytes()).hexdigest(),
                "ticker_count": 225,
                "expected_ticker_count": 225,
            }
            (root / "reports" / "notification_source_manifest.json").write_text(
                json.dumps(invalid_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "daily report row count does not match manifest"):
                market_regime_ai_module.build_market_regime(root)

            invalid_225 = pd.DataFrame(rows)
            invalid_225.loc[0, "ma75_raw"] = 0.0
            invalid_225_path = root / "reports" / "report_20260825_invalid_ma75.csv"
            invalid_225.to_csv(invalid_225_path, index=False, encoding="utf-8-sig")
            invalid_225_manifest = {
                **manifest,
                "report_file": "reports/report_20260825_invalid_ma75.csv",
                "report_sha256": hashlib.sha256(invalid_225_path.read_bytes()).hexdigest(),
            }
            (root / "reports" / "notification_source_manifest.json").write_text(
                json.dumps(invalid_225_manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "ma75_raw column must be positive for every active row"):
                market_regime_ai_module.build_market_regime(root)

    def test_risk_v2_override_transmits_effective_cap_and_rechecks_context(self) -> None:
        generated_at = datetime(2026, 8, 4, 12, 0, tzinfo=JST)
        decision = self._decision(quantity=100, stop_price=950.0)
        direct, sizing, risk = self._configs()
        risk["risk_v2_enabled"] = True
        source_manifest = {
            "schema_version": 1,
            "run_id": "RUN-BEAR-CAP",
            "generated_at": "2026-08-04T12:00:00+09:00",
            "report_file": "reports/report_20260804.csv",
            "report_sha256": "1" * 64,
            "ticker_count": 225,
            "expected_ticker_count": 225,
            "ticker_universe_sha256": "2" * 64,
            "market_data_evidence": {"status": "READY"},
        }
        market_regime = {
            "schema_version": 2,
            "source_run_id": "RUN-BEAR-CAP",
            "source_report_sha256": "1" * 64,
            "source_ticker_count": 225,
            "risk_policy_id": "RISK_V2_PRODUCTION_MA75_BREADTH_V1",
            "breadth_metric": "ABOVE_MA75_RATIO_ACTIVE225",
            "breadth_ratio": 0.3999,
            "breadth_threshold": 0.40,
            "regime": "BEAR",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            trade_signals_sha256, market_regime_sha256 = self._write_provenance_files(
                root,
                source_manifest=source_manifest,
                market_regime=market_regime,
            )
            trade_signals_manifest = {
                "schema_version": 1,
                "generated_at": "2026-08-04T12:00:00+09:00",
                "source_run_id": source_manifest["run_id"],
                "source_report_sha256": source_manifest["report_sha256"],
                "source_ticker_count": source_manifest["ticker_count"],
                "ai_judgement_sha256": "4" * 64,
                "market_regime_sha256": market_regime_sha256,
                "trade_signals_sha256": trade_signals_sha256,
                "trade_signals_row_count": 1,
            }
            captured: dict[str, object] = {}

            def fake_size_candidates(broker, candidates, config, max_total_invested_pct_override=None):
                captured["override"] = max_total_invested_pct_override
                return (decision,)

            def fake_evaluate_orders(broker, orders, config, state, market_context=None):
                captured["market_context"] = market_context
                return SimpleNamespace(
                    accepted_orders=tuple(orders),
                    decisions=(
                        RiskDecision(
                            ticker=orders[0].ticker,
                            side=orders[0].side.value,
                            quantity=orders[0].quantity,
                            price=orders[0].limit_price,
                            accepted=True,
                            reason="",
                            estimated_value_yen=orders[0].quantity * orders[0].limit_price,
                        ),
                    ),
                )

            def fake_read_json(path: Path) -> tuple[dict[str, object], str | None]:
                name = path.name
                if name == "v7_direct_pipeline_config.json":
                    return direct, None
                if name == "v7_position_sizer_config.json":
                    return sizing, None
                if name == "v7_risk_config.json":
                    return risk, None
                if name == "notification_source_manifest.json":
                    return source_manifest, None
                if name == "trade_signals_manifest.json":
                    return trade_signals_manifest, None
                if name == "market_regime.json":
                    return market_regime, None
                return {}, f"unexpected file: {path}"

            with (
                mock.patch.object(gate, "_read_json", side_effect=fake_read_json),
                mock.patch.object(
                    gate,
                    "_load_candidate_batch",
                    return_value=(self._candidate_batch(generated_at=generated_at), None, root / "reports" / "trade_signals.csv"),
                ),
                mock.patch.object(gate, "_load_broker", return_value=(SimpleNamespace(get_account_snapshot=lambda: SimpleNamespace(equity_yen=300_000.0)), None)),
                mock.patch.object(gate, "size_candidates", side_effect=fake_size_candidates),
                mock.patch.object(gate, "load_risk_state", return_value=SimpleNamespace()),
                mock.patch.object(gate, "evaluate_orders", side_effect=fake_evaluate_orders),
                mock.patch.dict(
                    gate.os.environ,
                    {
                        "PHOENIX_OPERATING_SCOPE": "OPERATIONAL",
                        "PHOENIX_TRADING_ACTIONS": "PAPER_ONLY",
                    },
                    clear=False,
                ),
            ):
                report = gate.build_preorder_report(root, generated_at=generated_at)

            self.assertEqual("APPROVED", report["status"])
            self.assertEqual(0.70, captured["override"])
            self.assertEqual("BEAR", captured["market_context"]["regime"])
            self.assertEqual(0.3999, captured["market_context"]["breadth_ratio"])
            self.assertEqual(0, report["orders_submitted"])

    def test_live_dispatch_mode_transition_helper(self) -> None:
        self.assertEqual(
            "PAPER_SAFE",
            gate._resolve_live_dispatch_mode(
                "PAPER_SAFE",
                broker_health_ok=False,
                queue_clear=False,
            ),
        )
        self.assertEqual(
            "LIVE_ACTIVE",
            gate._resolve_live_dispatch_mode(
                "LIVE_ACTIVE",
                broker_health_ok=True,
                queue_clear=True,
            ),
        )
        self.assertEqual(
            "LIVE_RECONCILE_ONLY",
            gate._resolve_live_dispatch_mode(
                "LIVE_ACTIVE",
                broker_health_ok=False,
                queue_clear=True,
            ),
        )
        self.assertEqual(
            "LIVE_RECONCILE_ONLY",
            gate._resolve_live_dispatch_mode(
                "LIVE_ACTIVE",
                broker_health_ok=True,
                queue_clear=False,
            ),
        )
        self.assertEqual(
            "LIVE_RECONCILE_ONLY",
            gate._resolve_live_dispatch_mode("LIVE_ACTIVE", submit_status="PENDING"),
        )
        self.assertEqual(
            "LIVE_RECONCILE_ONLY",
            gate._resolve_live_dispatch_mode("LIVE_ACTIVE", submit_error=True),
        )
        self.assertEqual(
            "LIVE_RECONCILE_ONLY",
            gate._resolve_live_dispatch_mode("LIVE_RECONCILE_ONLY", broker_health_ok=True, queue_clear=True),
        )

    def test_live_reconcile_only_skips_new_submit_and_refreshes_pending_orders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            order = self._live_order("LIVE-RECON-001")
            trade_signals_context = {
                "schema_version": 1,
                "source_run_id": "RUN-LIVE-RECON",
                "source_report_sha256": "3" * 64,
                "source_ticker_count": 225,
                "trade_signals_sha256": "4" * 64,
                "market_regime_sha256": "5" * 64,
                "trade_signals_row_count": 1,
            }
            context = self._dispatch_context(
                root=root,
                operating_mode="LIVE_RECONCILE_ONLY",
                orders=[order],
                trade_signals_context=trade_signals_context,
            )
            broker = self._FakeLiveDispatchBroker(healthy=True)
            source_manifest = {
                "schema_version": 1,
                "run_id": "RUN-LIVE-RECON",
                "generated_at": "2026-08-04T12:00:00+09:00",
                "report_file": "reports/report_20260804.csv",
                "report_sha256": "3" * 64,
                "ticker_count": 225,
                "expected_ticker_count": 225,
                "ticker_universe_sha256": "2" * 64,
                "market_data_evidence": {"status": "READY"},
            }

            def fake_read_json(path: Path) -> tuple[dict[str, object], str | None]:
                if path.name == "notification_source_manifest.json":
                    return source_manifest, None
                return {}, f"unexpected file: {path}"

            with (
                mock.patch.object(gate, "create_broker", return_value=broker),
                mock.patch.object(gate, "_trade_signals_context", return_value=(trade_signals_context, [])),
                mock.patch.object(gate, "_read_json", side_effect=fake_read_json),
            ):
                results = gate.dispatch_approved_orders(root, context)

            self.assertEqual([], results)
            self.assertEqual(0, broker.submit_calls)
            self.assertGreaterEqual(broker.refresh_calls, 1)

    def test_live_active_stops_after_first_nonterminal_submit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            orders = [
                self._live_order("LIVE-SUBMIT-001", ticker="1301.T"),
                self._live_order("LIVE-SUBMIT-002", ticker="1302.T"),
            ]
            trade_signals_context = {
                "schema_version": 1,
                "source_run_id": "RUN-LIVE-ACTIVE",
                "source_report_sha256": "6" * 64,
                "source_ticker_count": 225,
                "trade_signals_sha256": "7" * 64,
                "market_regime_sha256": "8" * 64,
                "trade_signals_row_count": 2,
            }
            context = self._dispatch_context(
                root=root,
                operating_mode="LIVE_ACTIVE",
                orders=orders,
                trade_signals_context=trade_signals_context,
            )
            broker = self._FakeLiveDispatchBroker(
                healthy=True,
                submit_results=[
                    SimpleNamespace(status=OrderStatus.PENDING, message="PENDING"),
                ],
            )
            source_manifest = {
                "schema_version": 1,
                "run_id": "RUN-LIVE-ACTIVE",
                "generated_at": "2026-08-04T12:00:00+09:00",
                "report_file": "reports/report_20260804.csv",
                "report_sha256": "6" * 64,
                "ticker_count": 225,
                "expected_ticker_count": 225,
                "ticker_universe_sha256": "2" * 64,
                "market_data_evidence": {"status": "READY"},
            }

            def fake_read_json(path: Path) -> tuple[dict[str, object], str | None]:
                if path.name == "notification_source_manifest.json":
                    return source_manifest, None
                return {}, f"unexpected file: {path}"

            with (
                mock.patch.object(gate, "create_broker", return_value=broker),
                mock.patch.object(gate, "_trade_signals_context", return_value=(trade_signals_context, [])),
                mock.patch.object(gate, "_read_json", side_effect=fake_read_json),
            ):
                results = gate.dispatch_approved_orders(root, context)

            self.assertEqual(1, len(results))
            self.assertEqual(1, broker.submit_calls)
            self.assertEqual(["LIVE-SUBMIT-001"], broker.submitted_client_order_ids)


GENERATED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=JST)


if __name__ == "__main__":
    unittest.main()
