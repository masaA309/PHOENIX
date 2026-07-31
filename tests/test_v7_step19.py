from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from phoenix_core.broker import PaperBroker
from phoenix_core.data_freshness import JPX_CALENDAR_SHA256
from phoenix_core.models import OrderRequest, OrderSide, OrderType
from phoenix_core.readiness_gate import build_readiness_report
from phoenix_core.staged_pilot_gate import (
    build_staged_pilot_report,
    run_staged_pilot_gate,
    text_report as pilot_text_report,
)
from phoenix_core.trading_economics import (
    build_economics_report,
    run_trading_economics,
    text_report as economics_text_report,
    verify_broker_economics_state,
    verify_economics_report,
)


JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 7, 31, 18, 0, tzinfo=JST)
ACCOUNT_PLAN_EVIDENCE = b"test-account-plan:SUPER_DISCOUNT\n"
FEE_SCHEDULE_EVIDENCE = b"test-fee-schedule:rakuten-cash-equities\n"
_ECONOMICS_EVIDENCE_TEMP = tempfile.TemporaryDirectory()
ECONOMICS_EVIDENCE_ROOT = Path(_ECONOMICS_EVIDENCE_TEMP.name)


def write_economics_evidence(root: Path) -> None:
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "account_plan.txt").write_bytes(ACCOUNT_PLAN_EVIDENCE)
    (evidence_dir / "fee_schedule.txt").write_bytes(FEE_SCHEDULE_EVIDENCE)


write_economics_evidence(ECONOMICS_EVIDENCE_ROOT)


def event_sha256(event: dict[str, object]) -> str:
    canonical = {key: value for key, value in event.items() if key != "event_sha256"}
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evidence_sha256(value: dict[str, object], field: str) -> str:
    canonical = {key: item for key, item in value.items() if key != field}
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def economics_settings() -> dict[str, object]:
    return {
        "enabled": True,
        "advisory_only": True,
        "live_trading_enabled": False,
        "automatic_promotion": False,
        "capital_plan": {
            "base_capital_yen": 300_000,
            "conditional_contribution_yen": 200_000,
            "maximum_funded_capital_yen": 500_000,
            "risk_capital_basis_yen": 300_000,
            "automatic_risk_scaling": False,
        },
        "fixed_monthly_operating_cost_yen": 7_000,
        "distribution": {
            "living_funds_rate": 0.20,
            "maximum_living_funds_rate": 0.30,
            "manual_approval_required": True,
            "unrealized_profit_eligible": False,
        },
        "tax_reserve": {
            "conservative_rate": 0.20315,
            "account_tax_treatment_verified": True,
        },
        "commission": {
            "unverified_plan_fee_reserve_per_filled_order_yen": 1_070,
            "account_plan": "SUPER_DISCOUNT",
            "account_plan_verified": True,
            "account_plan_evidence_file": "evidence/account_plan.txt",
            "account_plan_evidence_sha256": hashlib.sha256(
                ACCOUNT_PLAN_EVIDENCE
            ).hexdigest(),
            "published_fee_schedule_file": "evidence/fee_schedule.txt",
            "published_fee_schedule_sha256": hashlib.sha256(
                FEE_SCHEDULE_EVIDENCE
            ).hexdigest(),
            "sor_r_cross_agreement_verified": False,
        },
        "slippage": {"reserve_bps_per_side": 10},
    }


def fill_event(
    *,
    event_number: int,
    side: str,
    requested_price: float,
    filled_price: float,
    commission_yen: float = 100.0,
    cost_basis_released_yen: float = 0.0,
    eligible_realized_yen: float = 0.0,
) -> dict[str, object]:
    quantity = 100
    gross = round(filled_price * quantity, 2)
    realized = round(gross - cost_basis_released_yen, 2) if side == "SELL" else 0.0
    cash_delta = -(gross + commission_yen) if side == "BUY" else gross - commission_yen
    adverse = (
        max(0.0, filled_price - requested_price) * quantity
        if side == "BUY"
        else max(0.0, requested_price - filled_price) * quantity
    )
    event: dict[str, object] = {
        "schema_version": 1,
        "event_id": f"FILL|PAPER-{event_number}",
        "broker_name": "PAPER",
        "broker_order_id": f"PAPER-{event_number}",
        "client_order_id": f"CLIENT-{event_number}",
        "ticker": "1111.T",
        "side": side,
        "quantity": quantity,
        "requested_price": requested_price,
        "filled_quantity": quantity,
        "filled_price": filled_price,
        "gross_amount_yen": gross,
        "commission_yen": commission_yen,
        "commission_source": "BROKER_RESULT",
        "cash_delta_yen": round(cash_delta, 2),
        "cost_basis_released_yen": cost_basis_released_yen,
        "realized_pnl_before_commission_yen": realized,
        "economics_eligible_quantity": quantity,
        "economics_eligible_commission_yen": commission_yen,
        "economics_eligible_realized_pnl_before_commission_yen": (
            eligible_realized_yen if side == "SELL" else 0.0
        ),
        "adverse_slippage_yen": round(adverse, 2),
        "created_at": f"2026-07-{event_number:02d}T15:00:00+09:00",
    }
    event["event_sha256"] = event_sha256(event)
    return event


def broker_state_v2(*, profitable: bool = True) -> dict[str, object]:
    buy = fill_event(
        event_number=1,
        side="BUY",
        requested_price=100.0,
        filled_price=101.0,
    )
    sell_price = 700.0 if profitable else 80.0
    sell = fill_event(
        event_number=2,
        side="SELL",
        requested_price=sell_price + 1.0,
        filled_price=sell_price,
        cost_basis_released_yen=10_100.0,
        eligible_realized_yen=round(sell_price * 100 - 10_100.0, 2),
    )
    events = [buy, sell]
    cash = 300_000.0 + sum(float(event["cash_delta_yen"]) for event in events)
    realized = float(sell["realized_pnl_before_commission_yen"]) - float(
        sell["commission_yen"]
    )
    return {
        "state_version": 2,
        "broker_name": "PAPER",
        "account_type": "CASH",
        "live_trading_enabled": False,
        "margin_trading_enabled": False,
        "updated_at": "2026-07-31T18:00:00+09:00",
        "initial_cash_yen": 300_000.0,
        "cash_yen": round(cash, 2),
        "commission_rate": 0.0,
        "realized_pnl_yen": round(realized, 2),
        "positions": {},
        "processed_client_order_ids": ["CLIENT-1", "CLIENT-2"],
        "economics_baseline": {
            "schema_version": 1,
            "established_at": "2026-07-01T09:00:00+09:00",
            "cash_yen": 300_000.0,
            "realized_pnl_yen": 0.0,
            "positions": {},
            "processed_client_order_ids": [],
        },
        "fill_events": events,
    }


def broker_state_v1() -> dict[str, object]:
    return {
        "state_version": 1,
        "broker_name": "PAPER",
        "account_type": "CASH",
        "live_trading_enabled": False,
        "margin_trading_enabled": False,
        "cash_yen": 320_000.0,
        "realized_pnl_yen": 20_000.0,
        "positions": {},
        "processed_client_order_ids": [],
    }


def economics_report(state: dict[str, object] | None = None) -> dict[str, object]:
    return build_economics_report(
        state or broker_state_v2(),
        economics_settings(),
        now=NOW,
        evidence_root=ECONOMICS_EVIDENCE_ROOT,
    )


def shadow_evidence() -> dict[str, object]:
    sessions: list[dict[str, object]] = []
    dates = ("2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07")
    for index, trading_date in enumerate(dates, start=1):
        session: dict[str, object] = {
                "session_id": trading_date,
                "trading_date": trading_date,
                "source": "RAKUTEN_MARKETSPEED_II_RSS",
                "contract_id": "PHOENIX_RSS_SHADOW_V1",
                "integrity_status": "READY",
                "candidate_guard_status": "READY",
                "coverage_method": "THREE_POINT_SESSION_SAMPLING",
                "continuous_connection_claimed": False,
                "capture_count": 3,
                "capture_ids": [f"CAPTURE-{index}-{part}" for part in range(1, 4)],
                "rss_manifest_files": [
                    f"runtime/v7_rss_shadow/manifests/{trading_date}-{part}.json"
                    for part in range(1, 4)
                ],
                "rss_manifest_sha256s": [
                    ("a", "b", "c")[part - 1] * 64 for part in range(1, 4)
                ],
                "rss_snapshot_sha256s": [
                    ("d", "e", "f")[part - 1] * 64 for part in range(1, 4)
                ],
                "capture_id": f"CAPTURE-{index}-3",
                "first_capture_at": f"{trading_date}T09:30:00+09:00",
                "last_capture_at": f"{trading_date}T15:00:00+09:00",
                "rss_manifest_sha256": "c" * 64,
                "rss_snapshot_sha256": "f" * 64,
                "rss_producer_sha256": "1" * 64,
                "rss_workbook_sha256": "2" * 64,
                "rss_vba_project_sha256": "3" * 64,
                "rss_workbook_attestation_sha256": "4" * 64,
                "rss_settings_sha256": "5" * 64,
                "rss_universe_sha256": "6" * 64,
                "risk_halt_count": 0,
                "risk_override_count": 0,
                "external_orders_submitted": 0,
                "lifecycle_fill_ids": [f"SHADOW-LIFE-{index}"] if index <= 3 else [],
                "economics_fill_ids": [f"SHADOW-ECON-{index}"] if index <= 3 else [],
                "fill_links": ([{
                    "lifecycle_fill_id": f"SHADOW-LIFE-{index}",
                    "economics_fill_id": f"SHADOW-ECON-{index}",
                }] if index <= 3 else []),
        }
        session["session_sha256"] = evidence_sha256(session, "session_sha256")
        sessions.append(session)
    root: dict[str, object] = {
        "evidence_kind": "REALTIME_RSS_SHADOW",
        "integrity_status": "VERIFIED",
        "jpx_calendar_status": "VERIFIED",
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
        "external_orders_submitted": 0,
        "paper_days_credited": 0,
        "audited_live_fills_credited": 0,
        "sessions": sessions,
    }
    root["evidence_sha256"] = evidence_sha256(root, "evidence_sha256")
    return root


def pilot_evidence(*, new_buy_attempts: int = 1) -> dict[str, object]:
    sessions: list[dict[str, object]] = []
    dates = ("2026-07-08", "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14")
    for index, trading_date in enumerate(dates, start=1):
        session: dict[str, object] = {
                "session_id": trading_date,
                "trading_date": trading_date,
                "all_guards_status": "READY",
                "new_buy_submission_attempts": new_buy_attempts,
                "unreconciled_fill_count": 0,
                "risk_halt_count": 0,
                "lifecycle_fill_ids": [f"PILOT-LIFE-{index}"] if index <= 3 else [],
                "economics_fill_ids": [f"PILOT-ECON-{index}"] if index <= 3 else [],
                "fill_links": ([{
                    "lifecycle_fill_id": f"PILOT-LIFE-{index}",
                    "economics_fill_id": f"PILOT-ECON-{index}",
                }] if index <= 3 else []),
        }
        session["session_sha256"] = evidence_sha256(session, "session_sha256")
        sessions.append(session)
    root: dict[str, object] = {
        "integrity_status": "VERIFIED",
        "jpx_calendar_status": "VERIFIED",
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
        "maximum_drawdown_pct": 0.05,
        "sessions": sessions,
    }
    root["evidence_sha256"] = evidence_sha256(root, "evidence_sha256")
    return root


def pilot_settings() -> dict[str, object]:
    return {
        "enabled": True,
        "advisory_only": True,
        "cash_only": True,
        "margin_allowed": False,
        "short_selling_allowed": False,
        "manual_approval_required": True,
        "rss_required": True,
        "live_trading_enabled": False,
        "automatic_promotion": False,
        "automatic_funding": False,
        "automatic_risk_scaling": False,
        "base_capital_yen": 300_000,
        "conditional_contribution_yen": 200_000,
        "maximum_funded_capital_yen": 500_000,
        "risk_capital_basis_yen": 300_000,
        "minimum_shadow_sessions": 5,
        "minimum_shadow_fills": 3,
        "minimum_pilot_sessions_for_capital_increase": 5,
        "minimum_pilot_fills_for_capital_increase": 3,
        "max_new_buy_submissions_per_session": 1,
        "risk_reducing_sell_separate_path": True,
        "single_verified_trading_unit": True,
        "manual_approval_implementation_ready": True,
        "rss_implementation_ready": True,
        "rakuten_fee_plan_verified": True,
        "tax_treatment_verified": True,
        "cash_account_verified": True,
        "security_master_unit_verified": True,
        "daily_buy_cap_enforcement_ready": True,
        "risk_reducing_sell_path_ready": True,
        "limited_live_pilot_active": False,
        "conditional_funding_approved": False,
    }


def pilot_inputs() -> dict[str, object]:
    return {
        "performance": {
            "paper_evidence": {
                "status_counts": {"FAILED": 0},
                "risk_halt_count": 0,
            }
        },
        "operations": {"pipeline": {"candidate_input_status": "READY"}},
        "market_data": {"status": "READY"},
        "portfolio": {"action_counts": {"REVIEW": 0}},
        "lifecycle": {
            "status": "READY",
            "state_persisted": True,
            "audited_fill_count": 6,
            "audited_fill_ids": [
                "SHADOW-LIFE-1", "SHADOW-LIFE-2", "SHADOW-LIFE-3",
                "PILOT-LIFE-1", "PILOT-LIFE-2", "PILOT-LIFE-3",
            ],
            "audited_fill_crosswalk": [
                {
                    "lifecycle_fill_id": f"{phase}-LIFE-{index}",
                    "economics_fill_id": f"{phase}-ECON-{index}",
                    "broker_order_id": f"BROKER-{phase}-{index}",
                    "client_order_id": f"CLIENT-{phase}-{index}",
                    "ticker": f"{1100 + index}.T",
                    "side": "BUY",
                    "quantity": 100,
                    "created_at": f"2026-07-{index + (0 if phase == 'SHADOW' else 7):02d}T15:00:00+09:00",
                    "broker_fill_event_sha256": ("a" if phase == "SHADOW" else "b") * 64,
                }
                for phase in ("SHADOW", "PILOT")
                for index in range(1, 4)
            ],
        },
        "historical": {
            "gate_status": "READY",
            "execution_status": "COMPLETED",
            "evidence_kind": "HISTORICAL_WALK_FORWARD_REPLAY",
            "data_contract_status": "READY",
            "state_integrity_status": "READY",
            "post_save_integrity_status": "READY",
            "historical_evidence_verified": True,
            "risk_limits_unchanged": True,
            "input_files_unchanged": True,
            "replay_scope": "PRODUCTION_DECISION_PIPELINE",
            "sealed_holdout_status": "READY",
            "execution_model_status": "READY",
            "live_trading_enabled": False,
            "automatic_promotion": False,
            "external_orders_submitted": 0,
            "paper_days_credited": 0,
            "audited_fills_credited": 0,
        },
        "economics": {
            "economics_evidence_verified": True,
            "status": "READY",
            "ledger_integrity_status": "READY",
            "cost_input_status": "READY",
            "account_reconciliation_status": "READY",
            "performance": {
                "tracked_fill_event_ids": [
                    "SHADOW-ECON-1", "SHADOW-ECON-2", "SHADOW-ECON-3",
                    "PILOT-ECON-1", "PILOT-ECON-2", "PILOT-ECON-3",
                ],
                "tracked_fill_evidence": [
                    {
                        "economics_fill_id": f"{phase}-ECON-{index}",
                        "broker_order_id": f"BROKER-{phase}-{index}",
                        "client_order_id": f"CLIENT-{phase}-{index}",
                        "ticker": f"{1100 + index}.T",
                        "side": "BUY",
                        "quantity": 100,
                        "created_at": f"2026-07-{index + (0 if phase == 'SHADOW' else 7):02d}T15:00:00+09:00",
                        "broker_fill_event_sha256": ("a" if phase == "SHADOW" else "b") * 64,
                    }
                    for phase in ("SHADOW", "PILOT")
                    for index in range(1, 4)
                ],
                "business_net_after_all_reserved_costs_yen": 10_000,
                "cost_coverage": True,
                "unrecovered_loss_yen": 0,
            },
            "distribution": {"high_water_mark_reconciled": True},
            "safety": {
                "live_trading_enabled": False,
                "automatic_promotion": False,
            },
        },
        "shadow": shadow_evidence(),
        "pilot": pilot_evidence(),
        "rss_contract": {
            "rss_evidence_verified": True,
            "status": "READY",
            "evidence_verified": True,
            "safety": {
                "read_only": True,
                "orders_allowed": False,
                "orders_submitted": 0,
                "live_trading_enabled": False,
            },
        },
        "shadow_evidence_verified": True,
        "settings": pilot_settings(),
    }


def paper_order(order_id: str, side: OrderSide, price: float) -> OrderRequest:
    return OrderRequest(
        ticker="1111.T",
        side=side,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=price,
        client_order_id=order_id,
    )


class PaperBrokerEconomicsStateStep19Test(unittest.TestCase):
    def test_v1_baseline_migration_is_atomic_idempotent_and_credits_no_past_fill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            legacy = {
                "state_version": 1,
                "broker_name": "PAPER",
                "initial_cash_yen": 300_000.0,
                "cash_yen": 250_000.0,
                "commission_rate": 0.0,
                "realized_pnl_yen": 1_000.0,
                "positions": {
                    "1111.T": {
                        "quantity": 100,
                        "average_price": 500.0,
                        "market_price": 500.0,
                    }
                },
                "processed_client_order_ids": ["LEGACY-1"],
            }
            path.write_text(json.dumps(legacy), encoding="utf-8")
            broker = PaperBroker(state_file=path)
            self.assertTrue(broker.initialize_economics_baseline())
            first = path.read_bytes()
            self.assertFalse(broker.initialize_economics_baseline())
            self.assertEqual(first, path.read_bytes())
            migrated = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(2, migrated["state_version"])
            self.assertEqual([], migrated["fill_events"])
            self.assertEqual(["LEGACY-1"], migrated["economics_baseline"]["processed_client_order_ids"])
            self.assertEqual(0, migrated["positions"]["1111.T"]["economics_tracked_quantity"])

    def test_fill_event_is_saved_with_account_and_reloads_after_buy_and_sell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            broker = PaperBroker(
                initial_cash_yen=300_000,
                commission_rate=0.01,
                state_file=path,
            )
            broker.initialize_economics_baseline()
            broker.submit_order(paper_order("BUY-1", OrderSide.BUY, 100.0))
            reloaded = PaperBroker(
                initial_cash_yen=300_000,
                commission_rate=0.01,
                state_file=path,
            )
            reloaded.submit_order(paper_order("SELL-1", OrderSide.SELL, 120.0))
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(2, len(payload["fill_events"]))
            self.assertEqual({"BUY", "SELL"}, {event["side"] for event in payload["fill_events"]})
            self.assertEqual("BROKER_RESULT", payload["fill_events"][0]["commission_source"])
            self.assertEqual(100, payload["fill_events"][1]["economics_eligible_quantity"])
            self.assertEqual("READY", verify_broker_economics_state(payload)["status"])
            final = PaperBroker(
                initial_cash_yen=300_000,
                commission_rate=0.01,
                state_file=path,
            ).get_account_snapshot()
            self.assertEqual(0, len(final.positions))

    def test_tampered_atomic_fill_event_is_rejected_on_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            broker = PaperBroker(state_file=path)
            broker.initialize_economics_baseline()
            broker.submit_order(paper_order("BUY-1", OrderSide.BUY, 100.0))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["fill_events"][0]["commission_yen"] = 999.0
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                PaperBroker(state_file=path)

    def test_nonfinite_price_and_noninteger_quantity_never_mutate_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            broker = PaperBroker(state_file=path)
            broker.initialize_economics_baseline()
            before = path.read_bytes()
            invalid_orders = (
                OrderRequest("1111.T", OrderSide.BUY, 100, OrderType.LIMIT, float("nan"), "NAN"),
                OrderRequest("1111.T", OrderSide.BUY, True, OrderType.LIMIT, 100.0, "BOOL"),  # type: ignore[arg-type]
                OrderRequest("1111.T", OrderSide.BUY, 1.5, OrderType.LIMIT, 100.0, "FLOAT"),  # type: ignore[arg-type]
            )
            for order in invalid_orders:
                with self.subTest(order=order.client_order_id):
                    with self.assertRaises(ValueError):
                        broker.submit_order(order)
                    self.assertEqual(before, path.read_bytes())

    def test_buying_more_of_a_legacy_baseline_position_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            legacy = {
                "state_version": 1,
                "broker_name": "PAPER",
                "initial_cash_yen": 300_000.0,
                "cash_yen": 250_000.0,
                "commission_rate": 0.0,
                "realized_pnl_yen": 0.0,
                "positions": {"1111.T": {"quantity": 100, "average_price": 500.0, "market_price": 500.0}},
                "processed_client_order_ids": [],
            }
            path.write_text(json.dumps(legacy), encoding="utf-8")
            broker = PaperBroker(state_file=path)
            broker.initialize_economics_baseline()
            before = path.read_bytes()
            result = broker.submit_order(paper_order("ADD-LEGACY", OrderSide.BUY, 100.0))
            self.assertEqual("REJECTED", result.status.value)
            self.assertEqual(before, path.read_bytes())

    def test_self_hashed_tampered_eligible_pnl_is_rejected_on_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            broker = PaperBroker(state_file=path)
            broker.initialize_economics_baseline()
            broker.submit_order(paper_order("BUY-1", OrderSide.BUY, 100.0))
            broker.submit_order(paper_order("SELL-1", OrderSide.SELL, 120.0))
            payload = json.loads(path.read_text(encoding="utf-8"))
            sell = payload["fill_events"][1]
            sell["economics_eligible_realized_pnl_before_commission_yen"] += 1
            sell["event_sha256"] = event_sha256(sell)
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                PaperBroker(state_file=path)

    def test_tampered_position_average_is_rejected_on_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broker.json"
            broker = PaperBroker(state_file=path)
            broker.initialize_economics_baseline()
            broker.submit_order(paper_order("BUY-1", OrderSide.BUY, 100.0))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["positions"]["1111.T"]["average_price"] += 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                PaperBroker(state_file=path)


class TradingEconomicsPolicyStep19Test(unittest.TestCase):
    def test_v1_state_is_baseline_pending_and_credits_nothing(self) -> None:
        report = economics_report(broker_state_v1())
        self.assertEqual("BASELINE_PENDING", report["ledger_integrity_status"])
        self.assertEqual("NOT_READY", report["status"])
        self.assertEqual(0, report["distribution"]["approved_distribution_yen"])
        self.assertFalse(report["capital_plan"]["capital_contribution_executed"])
        self.assertFalse(report["safety"]["live_trading_enabled"])

    def test_monthly_fixed_cost_is_exactly_7000_yen(self) -> None:
        report = economics_report()
        self.assertEqual(7_000, report["costs"]["fixed_monthly_operating_cost_yen"])
        self.assertEqual(7_000, report["costs"]["fixed_operating_cost_total_yen"])

    def test_actual_fill_slippage_is_measured_but_not_deducted_twice(self) -> None:
        report = economics_report()
        performance = report["performance"]
        costs = report["costs"]
        gross = Decimal(str(performance["eligible_realized_pnl_before_costs_yen"]))
        expected = gross - Decimal(str(costs["commission_cost_used_yen"]))
        self.assertEqual(
            expected,
            Decimal(str(performance["strategy_net_realized_pnl_yen"])),
        )
        self.assertGreater(costs["broker_commission_actual_yen"], 0)
        self.assertGreater(costs["adverse_slippage_actual_yen"], 0)
        self.assertGreaterEqual(
            costs["commission_cost_used_yen"], costs["broker_commission_actual_yen"]
        )
        self.assertEqual(0, costs["slippage_cost_used_yen"])
        self.assertTrue(costs["slippage_already_reflected_in_fill_pnl"])

    def test_tax_reserve_is_exactly_20_315_percent_of_positive_realized_pnl(self) -> None:
        report = economics_report()
        realized = Decimal(str(report["performance"]["eligible_realized_pnl_before_costs_yen"]))
        expected = (realized * Decimal("0.20315")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        self.assertEqual(expected, Decimal(str(report["costs"]["tax_reserve_yen"])))

    def test_prior_year_loss_does_not_offset_unverified_current_year_tax_reserve(self) -> None:
        first_buy = fill_event(event_number=1, side="BUY", requested_price=100, filled_price=100)
        first_sell = fill_event(
            event_number=2,
            side="SELL",
            requested_price=80,
            filled_price=80,
            cost_basis_released_yen=10_000,
            eligible_realized_yen=-2_000,
        )
        second_buy = fill_event(event_number=3, side="BUY", requested_price=100, filled_price=100)
        second_sell = fill_event(
            event_number=4,
            side="SELL",
            requested_price=130,
            filled_price=130,
            cost_basis_released_yen=10_000,
            eligible_realized_yen=3_000,
        )
        for event, created_at in (
            (first_buy, "2025-12-01T15:00:00+09:00"),
            (first_sell, "2025-12-02T15:00:00+09:00"),
            (second_buy, "2026-01-05T15:00:00+09:00"),
            (second_sell, "2026-01-06T15:00:00+09:00"),
        ):
            event["created_at"] = created_at
            event["event_sha256"] = event_sha256(event)
        events = [first_buy, first_sell, second_buy, second_sell]
        state = broker_state_v2()
        state["economics_baseline"]["established_at"] = "2025-12-01T09:00:00+09:00"  # type: ignore[index]
        state["fill_events"] = events
        state["processed_client_order_ids"] = [event["client_order_id"] for event in events]
        state["cash_yen"] = 300_000 + sum(float(event["cash_delta_yen"]) for event in events)
        state["realized_pnl_yen"] = sum(
            float(event["realized_pnl_before_commission_yen"]) - float(event["commission_yen"])
            for event in events if event["side"] == "SELL"
        )
        state["updated_at"] = "2026-01-06T18:00:00+09:00"
        report = build_economics_report(
            state,
            economics_settings(),
            now=datetime(2026, 1, 6, 18, 0, tzinfo=JST),
            evidence_root=ECONOMICS_EVIDENCE_ROOT,
        )
        self.assertEqual({"2025": 0.0, "2026": 3000.0}, report["costs"]["taxable_profit_by_year_yen"])
        self.assertEqual(609.45, report["costs"]["tax_reserve_yen"])

    def test_unverified_commission_flag_without_evidence_uses_1070_per_fill(self) -> None:
        settings = economics_settings()
        settings["commission"]["account_plan_evidence_sha256"] = ""  # type: ignore[index]
        report = build_economics_report(
            broker_state_v2(), settings, now=NOW, evidence_root=ECONOMICS_EVIDENCE_ROOT
        )
        self.assertEqual(2_140, report["costs"]["commission_cost_used_yen"])
        self.assertEqual("NOT_READY", report["cost_input_status"])

    def test_arbitrary_hex_does_not_replace_commission_evidence_files(self) -> None:
        settings = economics_settings()
        commission = settings["commission"]  # type: ignore[assignment]
        commission["account_plan_evidence_file"] = "evidence/missing-account.txt"  # type: ignore[index]
        commission["account_plan_evidence_sha256"] = "a" * 64  # type: ignore[index]
        commission["published_fee_schedule_file"] = "evidence/missing-fees.txt"  # type: ignore[index]
        commission["published_fee_schedule_sha256"] = "b" * 64  # type: ignore[index]
        report = build_economics_report(
            broker_state_v2(),
            settings,
            now=NOW,
            evidence_root=ECONOMICS_EVIDENCE_ROOT,
        )
        self.assertEqual("NOT_READY", report["cost_input_status"])
        self.assertEqual(2_140, report["costs"]["commission_cost_used_yen"])

    def test_zero_course_requires_sor_r_cross_agreement_evidence(self) -> None:
        settings = economics_settings()
        commission = settings["commission"]  # type: ignore[assignment]
        commission["account_plan"] = "ZERO_COURSE"  # type: ignore[index]
        report = build_economics_report(
            broker_state_v2(), settings, now=NOW, evidence_root=ECONOMICS_EVIDENCE_ROOT
        )
        self.assertEqual("NOT_READY", report["cost_input_status"])
        self.assertEqual(2_140, report["costs"]["commission_cost_used_yen"])

    def test_distribution_is_20_percent_and_never_above_30_percent(self) -> None:
        distribution = economics_report()["distribution"]
        eligible = Decimal(str(distribution["preliminary_distributable_profit_yen"]))
        amount = Decimal(str(distribution["preliminary_living_funds_yen"]))
        expected = (eligible * Decimal("0.20")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        self.assertEqual(expected, amount)
        self.assertLessEqual(amount, eligible * Decimal("0.30"))
        self.assertEqual(0, distribution["approved_distribution_yen"])
        self.assertFalse(distribution["distribution_executed"])

    def test_loss_month_has_zero_tax_and_zero_distribution(self) -> None:
        report = economics_report(broker_state_v2(profitable=False))
        self.assertEqual(0, report["costs"]["tax_reserve_yen"])
        self.assertEqual(0, report["distribution"]["preliminary_living_funds_yen"])
        self.assertEqual(0, report["distribution"]["approved_distribution_yen"])

    def test_unrealized_gain_never_changes_tax_or_distribution(self) -> None:
        low_state = broker_state_v2()
        high_state = deepcopy(low_state)
        low_state["positions"] = {
            "9999.T": {"quantity": 100, "average_price": 100.0, "market_price": 50.0}
        }
        high_state["positions"] = {
            "9999.T": {"quantity": 100, "average_price": 100.0, "market_price": 50_000.0}
        }
        low = economics_report(low_state)
        high = economics_report(high_state)
        self.assertEqual(low["costs"]["tax_reserve_yen"], high["costs"]["tax_reserve_yen"])
        self.assertEqual(
            low["distribution"]["preliminary_living_funds_yen"],
            high["distribution"]["preliminary_living_funds_yen"],
        )
        self.assertEqual(0, high["performance"]["unrealized_profit_credited_yen"])

    def test_contribution_is_separate_from_profit_and_risk_basis(self) -> None:
        report = economics_report()
        plan = report["capital_plan"]
        self.assertEqual(300_000, plan["base_capital_yen"])
        self.assertEqual(200_000, plan["conditional_contribution_yen"])
        self.assertEqual(500_000, plan["maximum_funded_capital_yen"])
        self.assertEqual(300_000, plan["risk_capital_basis_yen"])
        self.assertEqual(0, plan["contribution_credited_as_profit_yen"])
        self.assertFalse(plan["automatic_risk_scaling"])
        self.assertFalse(plan["capital_contribution_executed"])

    def test_policy_cannot_relax_cost_tax_distribution_or_capital_rules(self) -> None:
        updates = (
            ("fixed_monthly_operating_cost_yen", 6_999),
            ("tax_reserve.conservative_rate", 0.20),
            ("distribution.living_funds_rate", 0.21),
            ("distribution.maximum_living_funds_rate", 0.31),
            ("capital_plan.conditional_contribution_yen", 200_001),
            ("capital_plan.maximum_funded_capital_yen", 500_001),
            ("capital_plan.risk_capital_basis_yen", 500_000),
            ("capital_plan.automatic_risk_scaling", True),
        )
        for dotted, value in updates:
            settings = economics_settings()
            target: dict[str, object] = settings
            parts = dotted.split(".")
            for part in parts[:-1]:
                target = target[part]  # type: ignore[assignment]
            target[parts[-1]] = value
            with self.subTest(setting=dotted):
                with self.assertRaises((TypeError, ValueError)):
                    build_economics_report(
                        broker_state_v2(),
                        settings,
                        now=NOW,
                        evidence_root=ECONOMICS_EVIDENCE_ROOT,
                    )


class TradingEconomicsStateStep19Test(unittest.TestCase):
    def test_valid_v2_state_verifies(self) -> None:
        result = verify_broker_economics_state(broker_state_v2())
        self.assertEqual("READY", result["status"])
        self.assertEqual([], result["errors"])

    def test_corrupt_v2_hash_fails_closed(self) -> None:
        state = broker_state_v2()
        state["fill_events"][0]["event_sha256"] = "0" * 64  # type: ignore[index]
        self.assertEqual("NOT_READY", verify_broker_economics_state(state)["status"])

    def test_v2_cash_reconciliation_corruption_fails_closed(self) -> None:
        state = broker_state_v2()
        state["cash_yen"] = float(state["cash_yen"]) + 1
        result = verify_broker_economics_state(state)
        self.assertEqual("NOT_READY", result["status"])
        self.assertTrue(any("cash" in message for message in result["errors"]))

    def test_duplicate_event_id_fails_closed(self) -> None:
        state = broker_state_v2()
        state["fill_events"].append(deepcopy(state["fill_events"][0]))  # type: ignore[attr-defined,index]
        self.assertEqual("NOT_READY", verify_broker_economics_state(state)["status"])

    def test_future_fill_timestamp_fails_closed_when_evaluated(self) -> None:
        state = broker_state_v2()
        event = state["fill_events"][1]  # type: ignore[index]
        event["created_at"] = "2026-08-01T15:00:00+09:00"
        event["event_sha256"] = event_sha256(event)
        state["updated_at"] = "2026-08-01T18:00:00+09:00"
        result = verify_broker_economics_state(state, now=NOW)
        self.assertEqual("NOT_READY", result["status"])
        self.assertTrue(any("future" in message for message in result["errors"]))

    def test_non_jst_or_out_of_order_fill_timestamp_fails_closed(self) -> None:
        for created_at in (
            "2026-07-02T15:00:00Z",
            "2026-06-30T15:00:00+09:00",
        ):
            state = broker_state_v2()
            event = state["fill_events"][0]  # type: ignore[index]
            event["created_at"] = created_at
            event["event_sha256"] = event_sha256(event)
            with self.subTest(created_at=created_at):
                self.assertEqual(
                    "NOT_READY", verify_broker_economics_state(state, now=NOW)["status"]
                )

    def test_nonfinite_money_fails_closed(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                state = broker_state_v2()
                state["fill_events"][0]["commission_yen"] = value  # type: ignore[index]
                result = verify_broker_economics_state(state)
                self.assertEqual("NOT_READY", result["status"])
                self.assertTrue(result["errors"])

    def test_same_input_and_clock_are_deterministic(self) -> None:
        state = broker_state_v2()
        first = build_economics_report(
            deepcopy(state),
            economics_settings(),
            now=NOW,
            evidence_root=ECONOMICS_EVIDENCE_ROOT,
        )
        second = build_economics_report(
            deepcopy(state),
            economics_settings(),
            now=NOW,
            evidence_root=ECONOMICS_EVIDENCE_ROOT,
        )
        self.assertEqual(first, second)
        self.assertEqual(economics_text_report(first), economics_text_report(second))

    def test_dry_run_does_not_change_broker_or_economics_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state").mkdir()
            state_path = root / "state/broker.json"
            economics_state = root / "state/economics.json"
            report_json = root / "reports/economics.json"
            report_text = root / "reports/economics.txt"
            state_path.write_text(
                json.dumps(broker_state_v2(), ensure_ascii=False, allow_nan=False),
                encoding="utf-8",
            )
            before = state_path.read_bytes()
            write_economics_evidence(root)
            config = {
                "trading_economics": {
                    **economics_settings(),
                    "broker_state": "state/broker.json",
                    "economics_state": "state/economics.json",
                    "report_json": "reports/economics.json",
                    "report_text": "reports/economics.txt",
                }
            }
            report = run_trading_economics(
                root, config, now=NOW, persist_state=False
            )
            self.assertEqual(before, state_path.read_bytes())
            self.assertFalse(economics_state.exists())
            self.assertFalse(report["safety"]["state_persisted"])
            self.assertEqual(0, report["safety"]["orders_submitted"])
            self.assertFalse(report["distribution"]["external_transfer_executed"])
            self.assertFalse(report["safety"]["live_trading_enabled"])
            self.assertTrue(report_json.is_file())
            self.assertTrue(report_text.is_file())

    def test_economics_report_lineage_rebuild_rejects_report_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state").mkdir()
            state_path = root / "state/broker.json"
            state = broker_state_v2()
            state_path.write_text(
                json.dumps(state, ensure_ascii=False, allow_nan=False), encoding="utf-8"
            )
            settings = {**economics_settings(), "broker_state": "state/broker.json"}
            config = {"trading_economics": settings}
            write_economics_evidence(root)
            report = build_economics_report(
                state, settings, now=NOW, evidence_root=root
            )
            valid, errors = verify_economics_report(root, config, report, now=NOW)
            self.assertTrue(valid, errors)
            tampered = deepcopy(report)
            tampered["performance"]["business_net_after_all_reserved_costs_yen"] += 1  # type: ignore[index]
            valid, errors = verify_economics_report(root, config, tampered, now=NOW)
            self.assertFalse(valid)
            self.assertTrue(errors)


class StagedPilotGateStep19Test(unittest.TestCase):
    def build(self, **changes: object) -> dict[str, object]:
        values = pilot_inputs()
        values.update(changes)
        return build_staged_pilot_report(**values, generated_at=NOW)

    def test_ready_requires_five_distinct_shadow_days_and_three_fills(self) -> None:
        report = self.build()
        self.assertEqual("READY", report["status"])
        self.assertTrue(report["pilot_candidate_eligible"])
        self.assertEqual(5, report["evidence"]["shadow_sessions"])
        self.assertEqual(3, report["evidence"]["shadow_fills"])

    def test_step19_readiness_cannot_omit_economics(self) -> None:
        report = build_readiness_report(
            {},
            {},
            {},
            {},
            {"step19_economics_required": True},
            economics=None,
        )
        economics_check = next(
            item for item in report["checks"] if item["name"] == "trading_economics"
        )
        self.assertFalse(economics_check["passed"])
        self.assertEqual("NOT_READY", report["status"])

        staged_report = build_readiness_report(
            {},
            {},
            {},
            {},
            {"step19_staged_pilot_required": True},
            staged=None,
        )
        staged_check = next(
            item
            for item in staged_report["checks"]
            if item["name"] == "staged_pilot_integration"
        )
        self.assertFalse(staged_check["passed"])
        self.assertEqual("NOT_READY", staged_report["status"])

    def test_same_day_repeats_do_not_count_as_distinct_shadow_days(self) -> None:
        shadow = shadow_evidence()
        for row in shadow["sessions"]:
            row["session_id"] = "2026-07-01"
            row["trading_date"] = "2026-07-01"
            row["session_sha256"] = evidence_sha256(row, "session_sha256")
        shadow["evidence_sha256"] = evidence_sha256(shadow, "evidence_sha256")
        report = self.build(shadow=shadow)
        self.assertEqual("NOT_READY", report["status"])
        self.assertEqual(1, report["evidence"]["shadow_sessions"])

    def test_two_fills_fail_closed(self) -> None:
        shadow = shadow_evidence()
        shadow["sessions"][2]["lifecycle_fill_ids"] = []
        shadow["sessions"][2]["economics_fill_ids"] = []
        shadow["sessions"][2]["session_sha256"] = evidence_sha256(
            shadow["sessions"][2], "session_sha256"
        )
        shadow["evidence_sha256"] = evidence_sha256(shadow, "evidence_sha256")
        report = self.build(shadow=shadow)
        self.assertEqual("NOT_READY", report["status"])
        self.assertIn("SHADOW_FILLS_INSUFFICIENT", report["blocking_codes"])

    def test_each_required_gate_fails_closed(self) -> None:
        cases: list[tuple[str, str, object]] = [
            ("historical", "gate_status", "NOT_READY"),
            ("market_data", "status", "FAILED"),
            ("lifecycle", "status", "FAILED"),
            ("economics", "status", "NOT_READY"),
        ]
        base = pilot_inputs()
        for section, key, value in cases:
            changed = deepcopy(base[section])
            changed[key] = value
            with self.subTest(section=section, key=key):
                self.assertEqual(
                    "NOT_READY", self.build(**{section: changed})["status"]
                )

    def test_manual_approval_and_rss_fail_closed_when_not_ready(self) -> None:
        for key in ("manual_approval_implementation_ready", "rss_implementation_ready"):
            settings = pilot_settings()
            settings[key] = False
            with self.subTest(setting=key):
                self.assertEqual("NOT_READY", self.build(settings=settings)["status"])

    def test_cash_only_and_single_unit_contract_cannot_be_relaxed(self) -> None:
        for key, value in (
            ("cash_only", False),
            ("margin_allowed", True),
            ("short_selling_allowed", True),
            ("single_verified_trading_unit", False),
        ):
            settings = pilot_settings()
            settings[key] = value
            with self.subTest(setting=key):
                with self.assertRaises((TypeError, ValueError)):
                    self.build(settings=settings)

    def test_more_than_one_new_buy_blocks_capital_promotion(self) -> None:
        settings = pilot_settings()
        settings["limited_live_pilot_active"] = True
        settings["conditional_funding_approved"] = True
        baseline = self.build(settings=settings)
        self.assertTrue(baseline["capital_increase_candidate_eligible"])
        report = self.build(
            settings=settings,
            pilot=pilot_evidence(new_buy_attempts=2),
        )
        self.assertFalse(report["capital_increase_candidate_eligible"])
        self.assertIn("PILOT_EVIDENCE_INVALID", report["blocking_codes"])

    def test_negative_float_and_boolean_buy_attempts_fail_closed(self) -> None:
        settings = pilot_settings()
        settings["limited_live_pilot_active"] = True
        settings["conditional_funding_approved"] = True
        for invalid in (-1, 1.5, True):
            with self.subTest(value=invalid):
                report = self.build(
                    settings=settings,
                    pilot=pilot_evidence(new_buy_attempts=invalid),  # type: ignore[arg-type]
                )
                self.assertFalse(report["capital_increase_candidate_eligible"])
                self.assertIn("PILOT_EVIDENCE_INVALID", report["blocking_codes"])

    def test_weekend_and_self_reported_hash_tampering_fail_closed(self) -> None:
        shadow = shadow_evidence()
        session = shadow["sessions"][0]
        session["session_id"] = "2026-07-04"
        session["trading_date"] = "2026-07-04"
        session["session_sha256"] = evidence_sha256(session, "session_sha256")
        shadow["evidence_sha256"] = evidence_sha256(shadow, "evidence_sha256")
        self.assertEqual("NOT_READY", self.build(shadow=shadow)["status"])

        tampered = shadow_evidence()
        tampered["sessions"][0]["risk_halt_count"] = 1
        self.assertEqual("NOT_READY", self.build(shadow=tampered)["status"])

    def test_future_session_and_untrusted_jpx_calendar_fail_closed(self) -> None:
        future = shadow_evidence()
        session = future["sessions"][0]
        session["session_id"] = "2027-07-01"
        session["trading_date"] = "2027-07-01"
        session["session_sha256"] = evidence_sha256(session, "session_sha256")
        future["evidence_sha256"] = evidence_sha256(future, "evidence_sha256")
        self.assertEqual("NOT_READY", self.build(shadow=future)["status"])

        untrusted = shadow_evidence()
        untrusted["jpx_calendar_sha256"] = "f" * 64
        untrusted["evidence_sha256"] = evidence_sha256(untrusted, "evidence_sha256")
        self.assertEqual("NOT_READY", self.build(shadow=untrusted)["status"])

    def test_fill_ids_require_explicit_one_to_one_cross_evidence_links(self) -> None:
        shadow = shadow_evidence()
        session = shadow["sessions"][0]
        session["fill_links"] = [{
            "lifecycle_fill_id": "SHADOW-LIFE-1",
            "economics_fill_id": "SHADOW-ECON-2",
        }]
        session["session_sha256"] = evidence_sha256(session, "session_sha256")
        shadow["evidence_sha256"] = evidence_sha256(shadow, "evidence_sha256")
        report = self.build(shadow=shadow)
        self.assertEqual("NOT_READY", report["status"])
        self.assertIn("SHADOW_EVIDENCE_INVALID", report["blocking_codes"])

        values = pilot_inputs()
        lifecycle = deepcopy(values["lifecycle"])
        lifecycle["audited_fill_crosswalk"][0]["ticker"] = "9999.T"
        report = self.build(lifecycle=lifecycle)
        self.assertEqual("NOT_READY", report["status"])
        self.assertIn("SHADOW_FILLS_UNRECONCILED", report["blocking_codes"])

    def test_capital_increase_requires_profit_hwm_fills_and_drawdown(self) -> None:
        settings = pilot_settings()
        settings["limited_live_pilot_active"] = True
        settings["conditional_funding_approved"] = True
        base = pilot_inputs()
        cases: list[tuple[str, object, str]] = [
            ("business_net_after_all_reserved_costs_yen", 0, "BUSINESS_NET_NOT_POSITIVE"),
            ("cost_coverage", False, "COST_COVERAGE_INSUFFICIENT"),
            ("unrecovered_loss_yen", 1, "UNRECOVERED_LOSS_EXISTS"),
        ]
        for key, value, code in cases:
            economics = deepcopy(base["economics"])
            economics["performance"][key] = value
            report = self.build(settings=settings, economics=economics)
            with self.subTest(key=key):
                self.assertFalse(report["capital_increase_candidate_eligible"])
                self.assertIn(code, report["blocking_codes"])
        economics = deepcopy(base["economics"])
        economics["distribution"]["high_water_mark_reconciled"] = False
        self.assertIn(
            "HIGH_WATER_MARK_NOT_RECONCILED",
            self.build(settings=settings, economics=economics)["blocking_codes"],
        )
        pilot = pilot_evidence()
        pilot["maximum_drawdown_pct"] = 0.1001
        pilot["evidence_sha256"] = evidence_sha256(pilot, "evidence_sha256")
        self.assertIn(
            "PILOT_DRAWDOWN_EXCEEDED",
            self.build(settings=settings, pilot=pilot)["blocking_codes"],
        )

    def test_daily_buy_cap_configuration_cannot_exceed_one(self) -> None:
        settings = pilot_settings()
        settings["max_new_buy_submissions_per_session"] = 2
        with self.assertRaises((TypeError, ValueError)):
            self.build(settings=settings)

    def test_gate_never_enables_live_auto_transfer_or_orders(self) -> None:
        report = self.build()
        safety = report["safety"]
        self.assertFalse(safety["live_trading_enabled"])
        self.assertFalse(safety["automatic_promotion"])
        self.assertFalse(safety["automatic_funding"])
        self.assertFalse(safety["automatic_risk_scaling"])
        self.assertFalse(safety["external_transfer_executed"])
        self.assertEqual(0, safety["orders_submitted"])
        self.assertIn("never enables orders", pilot_text_report(report))

    def test_run_gate_fails_closed_and_does_not_mutate_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            values = pilot_inputs()
            source_values = {
                name: values[name]
                for name in (
                    "performance",
                    "operations",
                    "market_data",
                    "portfolio",
                    "lifecycle",
                    "historical",
                    "economics",
                    "shadow",
                    "pilot",
                    "rss_contract",
                )
            }
            paths: dict[str, Path] = {}
            for name, payload in source_values.items():
                path = reports / f"{name}.json"
                path.write_text(
                    json.dumps(payload, ensure_ascii=False, allow_nan=False),
                    encoding="utf-8",
                )
                paths[name] = path
            before = {name: path.read_bytes() for name, path in paths.items()}
            settings = pilot_settings()
            for name, path in paths.items():
                settings[f"{name}_report"] = str(path.relative_to(root))
            settings["historical_replay_config"] = "config/missing.json"
            settings["report_json"] = "reports/pilot_gate.json"
            settings["report_text"] = "reports/pilot_gate.txt"
            config = {
                "staged_pilot_gate": settings
            }
            result = run_staged_pilot_gate(root, config)
            self.assertEqual("NOT_READY", result["status"])
            self.assertTrue(result["load_errors"])
            self.assertEqual(
                before, {name: path.read_bytes() for name, path in paths.items()}
            )
            self.assertTrue((reports / "pilot_gate.json").is_file())
            self.assertTrue((reports / "pilot_gate.txt").is_file())


if __name__ == "__main__":
    unittest.main()
