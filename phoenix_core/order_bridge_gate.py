from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from phoenix_core.broker import BrokerAdapter
from phoenix_core.candidate_input_guard import (
    CandidateInputAudit,
    CandidateInputError,
    CandidateInputPolicy,
    CandidateInputBatch,
    load_execution_candidates,
)
from phoenix_core.data_freshness import JST
from phoenix_core.factory import create_broker
from phoenix_core.performance_tracker import atomic_write, resolve_path
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    SizingDecision,
    build_order_requests,
    size_candidates,
)
from phoenix_core.risk_controller import (
    RiskConfig,
    RiskState,
    evaluate_orders,
    load_risk_state,
)


SCHEMA_VERSION = 1
VERSION = "PHOENIX v7 Step42"
CREATED_BY = "PHOENIX_STEP42_PREORDER_GATE"
TRADING_MODE = "PAPER"
EXECUTION_MODE = "DRY_RUN"
ORDER_TYPE = "LIMIT"
SIDE = "BUY"
MARKET = "TSE"
ALLOWED_OPERATING_SCOPES = {"MONITOR_ONLY", "OPERATIONAL"}
ALLOWED_TRADING_ACTIONS = {"DISABLED", "PAPER_ONLY"}
INSTRUCTION_TTL_MINUTES = 15
STATE_FILE = "state/v7_real_trade_preorder_state.json"
INSTRUCTION_FILE = "reports/v7_real_trade_preorder_instructions.csv"
REPORT_JSON_FILE = "reports/v7_real_trade_preorder_report.json"
REPORT_TEXT_FILE = "reports/v7_real_trade_preorder_report.txt"
AUDIT_JSONL_FILE = "reports/v7_real_trade_preorder_audit.jsonl"
DIRECT_PIPELINE_CONFIG = "config/v7_direct_pipeline_config.json"
POSITION_SIZER_CONFIG = "config/v7_position_sizer_config.json"
RISK_CONFIG_FILE = "config/v7_risk_config.json"
DEFAULT_CANDIDATE_PATH = "reports/trade_signals.csv"
OUTPUT_COLUMNS = [
    "schema_version",
    "intent_id",
    "idempotency_key",
    "generated_at",
    "expires_at",
    "trading_mode",
    "execution_mode",
    "signal_date",
    "ticker",
    "market",
    "side",
    "order_type",
    "quantity",
    "lot_size",
    "reference_price",
    "limit_price",
    "stop_loss_price",
    "take_profit_price",
    "estimated_notional",
    "estimated_max_loss",
    "source",
    "status",
    "blocked_reasons",
    "created_by",
]


def _now_jst() -> datetime:
    return datetime.now(JST)


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, f"Required file not found: {path}"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, f"Could not read {path}: {type(error).__name__}: {error}"
    if not isinstance(value, dict):
        return {}, f"JSON root is not an object: {path}"
    return value, None


def _position_sizing_config(payload: Mapping[str, Any]) -> PositionSizingConfig:
    sizing = payload.get("position_sizing", {})
    if not isinstance(sizing, Mapping):
        raise ValueError("position_sizing config must be an object")
    return PositionSizingConfig(
        risk_per_trade_pct=float(sizing.get("risk_per_trade_pct", 0.01)),
        max_position_pct=float(sizing.get("max_position_pct", 0.30)),
        max_total_invested_pct=float(sizing.get("max_total_invested_pct", 0.80)),
        minimum_cash_reserve_pct=float(sizing.get("minimum_cash_reserve_pct", 0.10)),
        fallback_stop_distance_pct=float(sizing.get("fallback_stop_distance_pct", 0.03)),
        lot_size=int(sizing.get("lot_size", 100)),
        maximum_quantity_per_ticker=int(sizing.get("maximum_quantity_per_ticker", 1000)),
        allow_pyramiding=bool(sizing.get("allow_pyramiding", False)),
        commission_buffer_pct=float(sizing.get("commission_buffer_pct", 0.001)),
    )


def _risk_config(payload: Mapping[str, Any]) -> RiskConfig:
    risk = payload.get("risk", {})
    if not isinstance(risk, Mapping):
        raise ValueError("risk config must be an object")
    return RiskConfig(
        max_daily_loss_pct=float(risk.get("max_daily_loss_pct", 0.03)),
        max_drawdown_pct=float(risk.get("max_drawdown_pct", 0.10)),
        max_positions=int(risk.get("max_positions", 5)),
        max_total_invested_pct=float(risk.get("max_total_invested_pct", 0.80)),
        max_single_position_pct=float(risk.get("max_single_position_pct", 0.30)),
        max_orders_per_run=int(risk.get("max_orders_per_run", 3)),
        max_consecutive_losses=int(risk.get("max_consecutive_losses", 3)),
        minimum_cash_reserve_pct=float(risk.get("minimum_cash_reserve_pct", 0.10)),
        block_on_broker_health_failure=bool(risk.get("block_on_broker_health_failure", True)),
    )


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _normalize_numeric(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not (number == number) or number <= 0:
        return None
    return round(number, 2)


def _first_text(row: Mapping[str, Any], names: Sequence[str], default: str = "") -> str:
    for name in names:
        if name in row:
            value = _normalize_text(row.get(name))
            if value:
                return value
    return default


def _first_numeric(row: Mapping[str, Any], names: Sequence[str]) -> float | None:
    for name in names:
        if name in row:
            value = _normalize_numeric(row.get(name))
            if value is not None:
                return value
    return None


def _parse_signal_timestamp(value: Any, generated_at: datetime) -> tuple[datetime | None, str | None]:
    text = _normalize_text(value)
    if not text:
        return None, "SIGNAL_DATE_MISSING"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, "SIGNAL_DATE_INVALID"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    else:
        parsed = parsed.astimezone(JST)
    if parsed > generated_at + timedelta(minutes=5):
        return None, "SIGNAL_DATE_IN_THE_FUTURE"
    if generated_at - parsed > timedelta(hours=24):
        return None, "SIGNAL_DATE_TOO_OLD"
    return parsed, None


def _parse_state(path: Path) -> tuple[set[str], str | None]:
    if not path.is_file():
        return set(), None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return set(), f"Could not read duplicate-prevention state: {type(error).__name__}: {error}"
    if not isinstance(payload, dict):
        return set(), "Duplicate-prevention state root is not an object"
    approved = payload.get("approved_idempotency_keys", [])
    if not isinstance(approved, list) or any(not isinstance(item, str) for item in approved):
        return set(), "Duplicate-prevention state is invalid"
    return set(approved), None


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _market_from_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if normalized.endswith(".T"):
        return MARKET
    return "UNKNOWN"


def _instruction_payload(
    *,
    generated_at: datetime,
    signal_date: str,
    ticker: str,
    side: str,
    order_type: str,
    quantity: int,
    lot_size: int,
    reference_price: float,
    limit_price: float,
    stop_loss_price: float,
    take_profit_price: float,
    source: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "signal_date": signal_date,
        "ticker": ticker,
        "market": _market_from_ticker(ticker),
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "lot_size": lot_size,
        "reference_price": reference_price,
        "limit_price": limit_price,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "trading_mode": TRADING_MODE,
        "execution_mode": EXECUTION_MODE,
        "source": source,
    }


def _idempotency_key(payload: Mapping[str, Any]) -> str:
    return _stable_hash(payload)


def _intent_id(signal_date: str, ticker: str, side: str, idempotency_key: str) -> str:
    compact_date = signal_date.replace("-", "") if signal_date else "UNKNOWN"
    return f"PHX42-{compact_date}-{ticker}-{side}-{idempotency_key[:10].upper()}"


def _row_blockers(
    *,
    operating_scope: str,
    trading_actions: str,
    decision: SizingDecision,
    risk_reason: str | None,
    signal_error: str | None,
    signal_timestamp: datetime | None,
    side: str,
    order_type: str,
    take_profit_price: float | None,
    reference_price: float,
    stop_loss_price: float,
    max_loss_limit_yen: float | None,
    approved_keys: set[str],
    idempotency_key: str,
    global_blockers: Sequence[str],
) -> list[str]:
    blockers = list(global_blockers)
    if operating_scope == "MONITOR_ONLY":
        blockers.append("MONITOR_ONLY_SCOPE")
    elif operating_scope not in ALLOWED_OPERATING_SCOPES:
        blockers.append("OPERATING_SCOPE_INVALID")
    if trading_actions not in ALLOWED_TRADING_ACTIONS:
        blockers.append("TRADING_ACTIONS_INVALID")
    if decision.status != "READY" or decision.recommended_quantity <= 0:
        blockers.append(f"POSITION_SIZER:{decision.reason}")
    if risk_reason:
        blockers.append(f"RISK:{risk_reason}")
    if signal_error:
        blockers.append(signal_error)
    if signal_timestamp is None:
        blockers.append("SIGNAL_DATE_INVALID")
    if side != SIDE:
        blockers.append("SIDE_NOT_ALLOWED")
    if order_type != ORDER_TYPE:
        blockers.append("ORDER_TYPE_NOT_ALLOWED")
    if take_profit_price is None:
        blockers.append("TAKE_PROFIT_MISSING")
    elif not (stop_loss_price > 0 and stop_loss_price < reference_price < take_profit_price):
        blockers.append("PRICE_RELATION_INVALID")
    estimated_max_loss = round(
        max(reference_price - stop_loss_price, 0.0)
        * max(int(decision.recommended_quantity), 0),
        2,
    )
    if max_loss_limit_yen is not None and estimated_max_loss > max_loss_limit_yen:
        blockers.append("MAX_LOSS_LIMIT_EXCEEDED")
    if idempotency_key in approved_keys:
        blockers.append("DUPLICATE_IDEMPOTENCY_KEY")
    return list(dict.fromkeys(blockers))


def _build_instruction_row(
    *,
    row: Mapping[str, Any],
    decision: SizingDecision,
    generated_at: datetime,
    expires_at: datetime,
    source: str,
    operating_scope: str,
    trading_actions: str,
    approved_keys: set[str],
    global_blockers: Sequence[str],
    lot_size: int = 100,
    max_loss_limit_yen: float | None = None,
) -> tuple[dict[str, Any], str, bool]:
    signal_text = _first_text(row, ["signal_date", "SignalDate", "生成日時", "generated_at", "signal_timestamp"])
    signal_timestamp, signal_error = _parse_signal_timestamp(signal_text, generated_at)
    signal_date = signal_timestamp.date().isoformat() if signal_timestamp else ""
    side = _first_text(row, ["side", "Side", "売買"], default=SIDE).upper()
    order_type = _first_text(row, ["order_type", "OrderType", "注文種別"], default=ORDER_TYPE).upper()
    take_profit_price = _first_numeric(row, ["take_profit_price", "TakeProfitPrice", "利確価格", "target_price", "目標価格"])
    reference_price = round(float(decision.entry_price), 2)
    limit_price = reference_price
    stop_loss_price = round(float(decision.stop_price), 2)
    quantity = int(decision.recommended_quantity) if decision.executable else 0
    canonical = _instruction_payload(
        generated_at=generated_at,
        signal_date=signal_date or "UNKNOWN",
        ticker=decision.ticker,
        side=side,
        order_type=order_type,
        quantity=quantity,
        lot_size=lot_size,
        reference_price=reference_price,
        limit_price=limit_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price or 0.0,
        source=source,
    )
    idempotency_key = _idempotency_key(canonical)
    blockers = _row_blockers(
        operating_scope=operating_scope,
        trading_actions=trading_actions,
        decision=decision,
        risk_reason=None,
        signal_error=signal_error,
        signal_timestamp=signal_timestamp,
        side=side,
        order_type=order_type,
        take_profit_price=take_profit_price,
        reference_price=reference_price,
        stop_loss_price=stop_loss_price,
        max_loss_limit_yen=max_loss_limit_yen,
        approved_keys=approved_keys,
        idempotency_key=idempotency_key,
        global_blockers=global_blockers,
    )
    approved = not blockers
    if approved:
        approved_keys.add(idempotency_key)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "intent_id": _intent_id(signal_date, decision.ticker, side, idempotency_key),
        "idempotency_key": idempotency_key,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "trading_mode": TRADING_MODE,
        "execution_mode": EXECUTION_MODE,
        "signal_date": signal_date,
        "ticker": decision.ticker,
        "market": _market_from_ticker(decision.ticker),
        "side": side,
        "order_type": order_type,
        "quantity": quantity if approved else 0,
        "lot_size": canonical["lot_size"],
        "reference_price": reference_price,
        "limit_price": limit_price,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price or 0.0,
        "estimated_notional": round((quantity if approved else 0) * limit_price, 2),
        "estimated_max_loss": round((quantity if approved else 0) * max(limit_price - stop_loss_price, 0.0), 2),
        "source": source,
        "status": "APPROVED" if approved else "BLOCKED",
        "blocked_reasons": ";".join(blockers),
        "created_by": CREATED_BY,
    }
    return payload, idempotency_key, approved


def _fallback_rows(
    *,
    candidate_batch: CandidateInputBatch,
    generated_at: datetime,
    expires_at: datetime,
    source: str,
    operating_scope: str,
    trading_actions: str,
    global_blockers: Sequence[str],
) -> list[dict[str, Any]]:
    approved_keys: set[str] = set()
    rows: list[dict[str, Any]] = []
    for _, raw_row in candidate_batch.candidates.iterrows():
        row_map = raw_row.to_dict()
        ticker = _first_text(row_map, ["ticker", "Ticker"], default="")
        entry_price = _first_numeric(row_map, ["entry_price", "繧ｨ繝ｳ繝医Μ繝ｼ萓｡譬ｼ", "謚ｼ縺礼岼萓｡譬ｼ", "蝓ｺ貅紋ｾ｡譬ｼ"])
        stop_price = _first_numeric(row_map, ["stop_price", "謳榊・萓｡譬ｼ", "stop_loss_price"])
        if not ticker or entry_price is None or stop_price is None:
            row_blockers = list(global_blockers) + ["ROW_NORMALIZATION_FAILED"]
            payload = {
                "schema_version": SCHEMA_VERSION,
                "intent_id": _intent_id("", ticker or "UNKNOWN", SIDE, _stable_hash({"ticker": ticker, "row": row_map})),
                "idempotency_key": _stable_hash({"ticker": ticker, "row": row_map}),
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "expires_at": expires_at.isoformat(timespec="seconds"),
                "trading_mode": TRADING_MODE,
                "execution_mode": EXECUTION_MODE,
                "signal_date": "",
                "ticker": ticker or "",
                "market": _market_from_ticker(ticker or ""),
                "side": SIDE,
                "order_type": ORDER_TYPE,
                "quantity": 0,
                "lot_size": 0,
                "reference_price": entry_price or 0.0,
                "limit_price": entry_price or 0.0,
                "stop_loss_price": stop_price or 0.0,
                "take_profit_price": 0.0,
                "estimated_notional": 0.0,
                "estimated_max_loss": 0.0,
                "source": source,
                "status": "BLOCKED",
                "blocked_reasons": ";".join(dict.fromkeys(row_blockers)),
                "created_by": CREATED_BY,
            }
            rows.append(payload)
            continue
        decision = SizingDecision(
            ticker=ticker,
            name=_first_text(row_map, ["name", "驫俶氛"], default=ticker),
            entry_price=entry_price,
            stop_price=stop_price,
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
            reason="BROKER_OR_RISK_CONFIGURATION_UNAVAILABLE",
            ranking_score=0.0,
        )
        payload, _, _ = _build_instruction_row(
            row=row_map,
            decision=decision,
            generated_at=generated_at,
            expires_at=expires_at,
            source=source,
            operating_scope=operating_scope,
            trading_actions=trading_actions,
            lot_size=100,
            max_loss_limit_yen=None,
            approved_keys=approved_keys,
            global_blockers=list(global_blockers) + ["BROKER_OR_RISK_CONFIGURATION_UNAVAILABLE"],
        )
        rows.append(payload)
    return rows


def _save_state(path: Path, approved_keys: set[str], report: Mapping[str, Any]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": report.get("generated_at", _now_jst().isoformat(timespec="seconds")),
        "last_report_sha256": _stable_hash(report),
        "last_approved_count": int(report.get("approved_count", 0) or 0),
        "last_blocked_count": int(report.get("blocked_count", 0) or 0),
        "approved_idempotency_keys": sorted(approved_keys),
    }
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_broker(root: Path, config: Mapping[str, Any]) -> tuple[BrokerAdapter | None, str | None]:
    try:
        broker = create_broker(dict(config), root)
    except Exception as error:
        return None, f"BROKER_CONFIGURATION_INVALID: {type(error).__name__}: {error}"
    try:
        health = broker.health_check()
    except Exception as error:
        return None, f"BROKER_HEALTH_ERROR: {type(error).__name__}: {error}"
    if not health.healthy:
        return None, f"BROKER_HEALTH_FAILED: {health.message}"
    return broker, None


def _load_candidate_batch(
    root: Path,
    policy: CandidateInputPolicy,
) -> tuple[CandidateInputBatch | None, str | None, Path]:
    candidate_path = resolve_path(root, policy.path)
    try:
        batch = load_execution_candidates(candidate_path, policy, repository_root=root)
    except (FileNotFoundError, CandidateInputError, UnicodeError, OSError) as error:
        return None, f"CANDIDATE_INPUT_INVALID: {type(error).__name__}: {error}", candidate_path
    return batch, None, candidate_path


def _decision_reason_map(decisions: Sequence[Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for decision in decisions:
        ticker = str(getattr(decision, "ticker", "")).strip().upper()
        if not ticker:
            continue
        mapping[ticker] = str(getattr(decision, "reason", ""))
    return mapping


def build_preorder_report(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at or _now_jst()
    expires_at = generated + timedelta(minutes=INSTRUCTION_TTL_MINUTES)
    report_blockers: list[str] = []

    direct_config, direct_error = _read_json(resolve_path(root, DIRECT_PIPELINE_CONFIG))
    if direct_error:
        report_blockers.append(direct_error)
    sizing_source, sizing_error = _read_json(resolve_path(root, POSITION_SIZER_CONFIG))
    if sizing_error:
        report_blockers.append(sizing_error)
    risk_source, risk_error = _read_json(resolve_path(root, RISK_CONFIG_FILE))
    if risk_error:
        report_blockers.append(risk_error)

    candidate_policy_payload = direct_config.get("candidate_input", {}) if isinstance(direct_config, dict) else {}
    try:
        candidate_policy = CandidateInputPolicy.from_mapping(candidate_policy_payload)
    except CandidateInputError as error:
        candidate_policy = None  # type: ignore[assignment]
        report_blockers.append(f"CANDIDATE_POLICY_INVALID: {error}")

    sizing_config = None
    if not sizing_error:
        try:
            sizing_config = _position_sizing_config(sizing_source)
            sizing_config.validate()
        except Exception as error:
            report_blockers.append(f"POSITION_SIZING_INVALID: {type(error).__name__}: {error}")
            sizing_config = None
    risk_config = None
    if not risk_error:
        try:
            risk_config = _risk_config(risk_source)
            risk_config.validate()
        except Exception as error:
            report_blockers.append(f"RISK_CONFIGURATION_INVALID: {type(error).__name__}: {error}")
            risk_config = None

    operating_scope = _normalize_text(os.environ.get("PHOENIX_OPERATING_SCOPE", "")).upper() or "UNKNOWN"
    trading_actions = _normalize_text(os.environ.get("PHOENIX_TRADING_ACTIONS", "")).upper() or "UNKNOWN"
    if operating_scope not in ALLOWED_OPERATING_SCOPES:
        report_blockers.append("OPERATING_SCOPE_INVALID")
    if trading_actions not in ALLOWED_TRADING_ACTIONS:
        report_blockers.append("TRADING_ACTIONS_INVALID")
    if operating_scope == "MONITOR_ONLY":
        report_blockers.append("MONITOR_ONLY_SCOPE")

    state_path = resolve_path(root, STATE_FILE)
    approved_before, state_error = _parse_state(state_path)
    if state_error:
        report_blockers.append(f"STATE_INVALID: {state_error}")

    candidate_batch: CandidateInputBatch | None = None
    candidate_error: str | None = None
    candidate_path = resolve_path(root, DEFAULT_CANDIDATE_PATH)
    if candidate_policy is not None:
        candidate_batch, candidate_error, candidate_path = _load_candidate_batch(root, candidate_policy)
        if candidate_error:
            report_blockers.append(candidate_error)
    if candidate_batch is None:
        rows = []
        source = str(candidate_path.relative_to(root)) if candidate_path.is_relative_to(root) else str(candidate_path)
        report = {
            "schema_version": SCHEMA_VERSION,
            "version": VERSION,
            "generated_at": generated.isoformat(timespec="seconds"),
            "expires_at": expires_at.isoformat(timespec="seconds"),
            "status": "BLOCKED",
            "mode": TRADING_MODE,
            "trading_mode": TRADING_MODE,
            "execution_mode": EXECUTION_MODE,
            "trading_actions": trading_actions,
            "operating_scope": operating_scope,
            "orders_submitted": 0,
            "external_orders_submitted": 0,
            "candidate_count": 0,
            "approved_count": 0,
            "blocked_count": 0,
            "blockers": list(dict.fromkeys(report_blockers)),
            "candidate_input_guard": None,
            "instructions": rows,
            "instruction_file": str(resolve_path(root, INSTRUCTION_FILE)),
            "report_json": str(resolve_path(root, REPORT_JSON_FILE)),
            "report_text": str(resolve_path(root, REPORT_TEXT_FILE)),
            "audit_jsonl": str(resolve_path(root, AUDIT_JSONL_FILE)),
            "state_file": str(state_path),
            "source": source,
            "created_by": CREATED_BY,
        }
        return report

    source = str(candidate_path.relative_to(root)) if candidate_path.is_relative_to(root) else str(candidate_path)
    rows: list[dict[str, Any]]
    approved_keys = set(approved_before)
    sizing_decisions: list[SizingDecision] = []
    risk_report: Any | None = None
    broker: BrokerAdapter | None = None
    max_loss_limit_yen: float | None = None
    if sizing_config is None or risk_config is None:
        rows = _fallback_rows(
            candidate_batch=candidate_batch,
            generated_at=generated,
            expires_at=expires_at,
            source=source,
            operating_scope=operating_scope,
            trading_actions=trading_actions,
            global_blockers=report_blockers,
        )
    else:
        broker, broker_error = _load_broker(root, sizing_source)
        if broker_error:
            report_blockers.append(broker_error)
            rows = _fallback_rows(
                candidate_batch=candidate_batch,
                generated_at=generated,
                expires_at=expires_at,
                source=source,
                operating_scope=operating_scope,
                trading_actions=trading_actions,
                global_blockers=report_blockers,
            )
        else:
            try:
                sizing_decisions = size_candidates(broker, candidate_batch.candidates, sizing_config)
            except Exception as error:
                report_blockers.append(f"SIZING_FAILED: {type(error).__name__}: {error}")
                rows = _fallback_rows(
                    candidate_batch=candidate_batch,
                    generated_at=generated,
                    expires_at=expires_at,
                    source=source,
                    operating_scope=operating_scope,
                    trading_actions=trading_actions,
                    global_blockers=report_blockers,
                )
            else:
                try:
                    account_snapshot = broker.get_account_snapshot()
                    max_loss_limit_yen = round(
                        float(account_snapshot.equity_yen) * float(risk_config.max_daily_loss_pct),
                        2,
                    )
                except Exception as error:
                    report_blockers.append(f"BROKER_SNAPSHOT_FAILED: {type(error).__name__}: {error}")
                    rows = _fallback_rows(
                        candidate_batch=candidate_batch,
                        generated_at=generated,
                        expires_at=expires_at,
                        source=source,
                        operating_scope=operating_scope,
                        trading_actions=trading_actions,
                        global_blockers=report_blockers,
                    )
                else:
                    executable_decisions = [decision for decision in sizing_decisions if decision.executable]
                    executable_orders = build_order_requests(
                        executable_decisions,
                        run_id=f"PHX42-{candidate_batch.audit.eligible_candidates_sha256[:16].upper()}",
                    )
                    risk_state: RiskState | None = None
                    if executable_orders:
                        try:
                            risk_state = load_risk_state(resolve_path(root, str(risk_source.get("files", {}).get("state", "state/v7_risk_state.json"))), account_snapshot.equity_yen)
                        except Exception as error:
                            report_blockers.append(f"RISK_STATE_INVALID: {type(error).__name__}: {error}")
                            risk_state = None
                    if executable_orders and risk_state is not None:
                        try:
                            risk_report = evaluate_orders(broker, executable_orders, risk_config, risk_state)
                        except Exception as error:
                            report_blockers.append(f"RISK_EVALUATION_FAILED: {type(error).__name__}: {error}")
                            risk_report = None
                    else:
                        risk_report = None
                    risk_reason_map = _decision_reason_map(getattr(risk_report, "decisions", ()))
                    rows = []
                    executable_index = 0
                    for row_index, (_, raw_row) in enumerate(candidate_batch.candidates.iterrows()):
                        decision = sizing_decisions[row_index]
                        risk_reason = None
                        if decision.executable and risk_report is not None and executable_index < len(risk_report.decisions):
                            risk_reason = None if risk_report.decisions[executable_index].accepted else risk_report.decisions[executable_index].reason
                            executable_index += 1
                        payload, idempotency_key, approved = _build_instruction_row(
                            row=raw_row.to_dict(),
                            decision=decision,
                            generated_at=generated,
                            expires_at=expires_at,
                            source=source,
                            operating_scope=operating_scope,
                            trading_actions=trading_actions,
                            approved_keys=approved_keys,
                            global_blockers=report_blockers + ([f"RISK:{risk_reason}"] if risk_reason else []),
                            lot_size=sizing_config.lot_size,
                            max_loss_limit_yen=max_loss_limit_yen,
                        )
                        rows.append(payload)

    rows_frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    approved_count = int((rows_frame.get("status", pd.Series(dtype=str)).astype(str) == "APPROVED").sum()) if not rows_frame.empty else 0
    blocked_count = len(rows_frame) - approved_count
    report_status = "APPROVED" if rows_frame is not None and not rows_frame.empty and blocked_count == 0 else "BLOCKED"
    if not rows_frame.empty and approved_count == 0 and "NO_APPROVED_ROWS" not in report_blockers:
        report_blockers.append("NO_APPROVED_ROWS")
        report_status = "BLOCKED"
    if "MONITOR_ONLY_SCOPE" in report_blockers:
        report_status = "BLOCKED"

    report = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generated_at": generated.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "status": report_status,
        "mode": TRADING_MODE,
        "trading_mode": TRADING_MODE,
        "execution_mode": EXECUTION_MODE,
        "trading_actions": trading_actions,
        "operating_scope": operating_scope,
        "orders_submitted": 0,
        "external_orders_submitted": 0,
        "candidate_count": len(rows_frame),
        "approved_count": approved_count,
        "blocked_count": blocked_count,
        "blockers": list(dict.fromkeys(report_blockers)),
        "candidate_input_guard": candidate_batch.audit.as_dict(),
        "instructions": rows,
        "instruction_file": str(resolve_path(root, INSTRUCTION_FILE)),
        "report_json": str(resolve_path(root, REPORT_JSON_FILE)),
        "report_text": str(resolve_path(root, REPORT_TEXT_FILE)),
        "audit_jsonl": str(resolve_path(root, AUDIT_JSONL_FILE)),
        "state_file": str(state_path),
        "source": source,
        "created_by": CREATED_BY,
    }
    return report


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP42 LOCAL REAL-TRADE BRIDGE PRE-ORDER GATE",
        "=" * 92,
        f"Status               : {report.get('status', '')}",
        f"Mode                 : {report.get('mode', TRADING_MODE)}",
        f"Trading mode         : {report.get('trading_mode', TRADING_MODE)}",
        f"Execution mode       : {report.get('execution_mode', EXECUTION_MODE)}",
        f"Trading actions      : {report.get('trading_actions', '')}",
        f"Operating scope      : {report.get('operating_scope', '')}",
        f"Orders submitted     : {report.get('orders_submitted', 0)}",
        f"Approved instructions: {report.get('approved_count', 0)}",
        f"Blocked instructions : {report.get('blocked_count', 0)}",
        f"Instruction file     : {report.get('instruction_file', '')}",
        f"Audit report         : {report.get('report_json', '')}",
        f"Audit JSONL          : {report.get('audit_jsonl', '')}",
        f"State file           : {report.get('state_file', '')}",
        "-" * 92,
    ]
    blockers = report.get("blockers", [])
    if blockers:
        lines.extend(["Blocking reasons:"] + [f"  - {value}" for value in blockers])
    else:
        lines.append("Blocking reasons: none")
    lines.extend(
        [
            "-" * 92,
            "This gate never submits RSS orders.",
            "Orders submitted: 0",
            "=" * 92,
            "",
        ]
    )
    return "\n".join(lines)


def save_preorder_outputs(root: Path, report: Mapping[str, Any]) -> None:
    instruction_path = resolve_path(root, str(report["instruction_file"]))
    report_json_path = resolve_path(root, str(report["report_json"]))
    report_text_path = resolve_path(root, str(report["report_text"]))
    audit_jsonl_path = resolve_path(root, str(report["audit_jsonl"]))
    state_path = resolve_path(root, str(report["state_file"]))

    rows = report.get("instructions", [])
    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    _write_csv(frame, instruction_path)
    atomic_write(report_json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(report_text_path, text_report(report))
    audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    audit_lines: list[str] = []
    for row in rows:
        audit_lines.append(
            json.dumps(
                {
                    "kind": "instruction",
                    "intent_id": row.get("intent_id", ""),
                    "idempotency_key": row.get("idempotency_key", ""),
                    "ticker": row.get("ticker", ""),
                    "status": row.get("status", ""),
                    "blocked_reasons": row.get("blocked_reasons", ""),
                    "quantity": row.get("quantity", 0),
                    "reference_price": row.get("reference_price", 0),
                    "limit_price": row.get("limit_price", 0),
                    "stop_loss_price": row.get("stop_loss_price", 0),
                    "take_profit_price": row.get("take_profit_price", 0),
                    "trading_mode": row.get("trading_mode", TRADING_MODE),
                    "execution_mode": row.get("execution_mode", EXECUTION_MODE),
                    "source": row.get("source", ""),
                    "created_by": row.get("created_by", CREATED_BY),
                },
                ensure_ascii=False,
            )
        )
    audit_lines.append(
        json.dumps(
            {
                "kind": "summary",
                "schema_version": report.get("schema_version", SCHEMA_VERSION),
                "status": report.get("status", ""),
                "generated_at": report.get("generated_at", ""),
                "expires_at": report.get("expires_at", ""),
                "trading_mode": report.get("trading_mode", TRADING_MODE),
                "execution_mode": report.get("execution_mode", EXECUTION_MODE),
                "trading_actions": report.get("trading_actions", ""),
                "operating_scope": report.get("operating_scope", ""),
                "orders_submitted": report.get("orders_submitted", 0),
                "approved_count": report.get("approved_count", 0),
                "blocked_count": report.get("blocked_count", 0),
                "blockers": list(report.get("blockers", [])),
                "candidate_input_guard": report.get("candidate_input_guard"),
            },
            ensure_ascii=False,
        )
    )
    atomic_write(audit_jsonl_path, "\n".join(audit_lines) + "\n")

    approved_keys = set()
    for row in rows:
        if row.get("status") == "APPROVED":
            key = str(row.get("idempotency_key", "")).strip()
            if key:
                approved_keys.add(key)
    _save_state(state_path, approved_keys, report)


def print_preorder_summary(report: Mapping[str, Any]) -> None:
    print("=" * 92)
    print("PHOENIX v7 STEP42 LOCAL REAL-TRADE BRIDGE PRE-ORDER GATE")
    print("=" * 92)
    print(f"Status               : {report.get('status', '')}")
    print(f"Trading mode         : {report.get('trading_mode', TRADING_MODE)}")
    print(f"Execution mode       : {report.get('execution_mode', EXECUTION_MODE)}")
    print(f"Trading actions      : {report.get('trading_actions', '')}")
    print(f"Approved instructions: {report.get('approved_count', 0)}")
    print(f"Blocked instructions : {report.get('blocked_count', 0)}")
    print(f"Orders submitted     : {report.get('orders_submitted', 0)}")
    print(f"Instruction file     : {report.get('instruction_file', '')}")
    print(f"Audit report         : {report.get('report_json', '')}")
    print(f"Audit JSONL          : {report.get('audit_jsonl', '')}")
    print("=" * 92)


def run_order_bridge_gate(root: Path) -> dict[str, Any]:
    report = build_preorder_report(root)
    save_preorder_outputs(root, report)
    return report
