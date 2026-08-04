from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pandas as pd

from phoenix_core.candidate_input_guard import CandidateInputAudit, CandidateInputBatch
from phoenix_core.data_freshness import JST
from phoenix_core.position_sizer import SizingDecision
from phoenix_core.risk_controller import RiskDecision

import phoenix_core.order_bridge_gate as gate


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
            }
        }
        sizing = {"position_sizing": {"lot_size": 100}}
        risk = {"risk": {"max_daily_loss_pct": 0.03}}
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


GENERATED_AT = datetime(2026, 8, 4, 12, 0, tzinfo=JST)


if __name__ == "__main__":
    unittest.main()
