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
from phoenix_core.models import OrderRequest
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
    resolve_effective_total_invested_pct,
)


SCHEMA_VERSION = 1
VERSION = "PHOENIX v7 Step42"
CREATED_BY = "PHOENIX_STEP42_PREORDER_GATE"
DEFAULT_TRADING_MODE = "PAPER"
DEFAULT_EXECUTION_MODE = "DRY_RUN"
DEFAULT_TRADING_ACTIONS = "PAPER_ONLY"
DEFAULT_ALLOWED_TRADING_ACTIONS = frozenset({"DISABLED", "PAPER_ONLY"})
OPERATING_MODE_PROFILES: dict[str, dict[str, Any]] = {
    "PAPER_SAFE": {
        "trading_mode": "PAPER",
        "execution_mode": "DRY_RUN",
        "trading_actions": "PAPER_ONLY",
        "allowed_trading_actions": frozenset({"DISABLED", "PAPER_ONLY"}),
        "broker_type": "paper",
        "transport_mode": "paper",
        "live_trading_enabled": False,
        "production_transport_enabled": False,
        "production_live_fire_armed": False,
    },
    "LIVE_ACTIVE": {
        "trading_mode": "LIVE",
        "execution_mode": "LIVE",
        "trading_actions": "LIVE_ONLY",
        "allowed_trading_actions": frozenset({"LIVE_ONLY"}),
        "broker_type": "rakuten_rss",
        "transport_mode": "production",
        "live_trading_enabled": True,
        "production_transport_enabled": True,
        "production_live_fire_armed": True,
    },
    "LIVE_RECONCILE_ONLY": {
        "trading_mode": "LIVE",
        "execution_mode": "LIVE",
        "trading_actions": "RECONCILE_ONLY",
        "allowed_trading_actions": frozenset({"RECONCILE_ONLY"}),
        "broker_type": "rakuten_rss",
        "transport_mode": "production",
        "live_trading_enabled": True,
        "production_transport_enabled": True,
        "production_live_fire_armed": False,
    },
}
ORDER_TYPE = "LIMIT"
SIDE = "BUY"
MARKET = "TSE"
ALLOWED_OPERATING_SCOPES = {"MONITOR_ONLY", "OPERATIONAL"}
INSTRUCTION_TTL_MINUTES = 15
STATE_FILE = "state/v7_real_trade_preorder_state.json"
INSTRUCTION_FILE = "reports/v7_real_trade_preorder_instructions.csv"
REPORT_JSON_FILE = "reports/v7_real_trade_preorder_report.json"
REPORT_TEXT_FILE = "reports/v7_real_trade_preorder_report.txt"
AUDIT_JSONL_FILE = "reports/v7_real_trade_preorder_audit.jsonl"
NOTIFICATION_SOURCE_MANIFEST_FILE = "reports/notification_source_manifest.json"
TRADE_SIGNALS_MANIFEST_FILE = "reports/trade_signals_manifest.json"
MARKET_REGIME_FILE = "reports/market_regime.json"
DIRECT_PIPELINE_CONFIG = "config/v7_direct_pipeline_config.json"
POSITION_SIZER_CONFIG = "config/v7_position_sizer_config.json"
RISK_CONFIG_FILE = "config/v7_risk_config.json"
PRODUCTION_BRIDGE_ROOT_RELATIVE = "runtime/v7_rss_production/order_bridge"
PRODUCTION_BRIDGE_PENDING_RELATIVE = "runtime/v7_rss_production/order_bridge/outbox/pending"
PRODUCTION_BRIDGE_PROCESSING_RELATIVE = "runtime/v7_rss_production/order_bridge/outbox/processing"
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
_MISSING = object()


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
        risk_policy_id=str(payload.get("risk_policy_id", "RISK_V2_PRODUCTION_MA75_BREADTH_V1")),
        breadth_metric=str(payload.get("breadth_metric", "ABOVE_MA75_RATIO_ACTIVE225")),
        risk_v2_enabled=bool(payload.get("risk_v2_enabled", False)),
        breadth_threshold=float(payload.get("breadth_threshold", 0.40)),
        bear_max_total_invested_pct=float(payload.get("bear_max_total_invested_pct", 0.70)),
        market_regime_file=str(payload.get("market_regime_file", "reports/market_regime.json")),
        max_daily_loss_pct=float(risk.get("max_daily_loss_pct", 0.03)),
        max_drawdown_pct=float(risk.get("max_drawdown_pct", 0.10)),
        max_positions=(
            None
            if risk.get("max_positions", None) is None
            else int(risk.get("max_positions", None))
        ),
        max_total_invested_pct=float(risk.get("max_total_invested_pct", 0.95)),
        max_single_position_pct=float(risk.get("max_single_position_pct", 0.30)),
        max_orders_per_run=int(risk.get("max_orders_per_run", 3)),
        max_consecutive_losses=int(risk.get("max_consecutive_losses", 3)),
        minimum_cash_reserve_pct=float(risk.get("minimum_cash_reserve_pct", 0.10)),
        block_on_broker_health_failure=bool(risk.get("block_on_broker_health_failure", True)),
    )


def _market_regime_context(
    root: Path,
    risk_config: RiskConfig,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not risk_config.risk_v2_enabled:
        return None, []

    blockers: list[str] = []
    manifest_source, manifest_error = _read_json(resolve_path(root, NOTIFICATION_SOURCE_MANIFEST_FILE))
    if manifest_error:
        blockers.append(f"MARKET_REGIME_MANIFEST_INVALID: {manifest_error}")
        return None, blockers

    regime_path = resolve_path(root, risk_config.market_regime_file)
    regime_source, regime_error = _read_json(regime_path)
    if regime_error:
        blockers.append(f"MARKET_REGIME_INVALID: {regime_error}")
        return None, blockers

    try:
        manifest_run_id = _normalize_text(manifest_source.get("run_id"))
        manifest_report_sha256 = _normalize_text(manifest_source.get("report_sha256"))
        manifest_ticker_count = int(manifest_source.get("ticker_count", 0))
        manifest_expected_ticker_count = int(manifest_source.get("expected_ticker_count", manifest_ticker_count))
    except (TypeError, ValueError) as error:
        blockers.append(f"MARKET_REGIME_MANIFEST_INVALID: {type(error).__name__}: {error}")
        return None, blockers

    if not manifest_run_id or not manifest_report_sha256:
        blockers.append("MARKET_REGIME_MANIFEST_INVALID: missing run_id/report_sha256")
        return None, blockers
    if manifest_ticker_count != 225 or manifest_expected_ticker_count != 225:
        blockers.append("MARKET_REGIME_MANIFEST_INVALID: ticker_count")
        return None, blockers

    try:
        schema_version = int(regime_source.get("schema_version", 0))
        source_run_id = _normalize_text(regime_source.get("source_run_id"))
        source_report_sha256 = _normalize_text(regime_source.get("source_report_sha256"))
        source_ticker_count = int(regime_source.get("source_ticker_count", 0))
        risk_policy_id = _normalize_text(regime_source.get("risk_policy_id"))
        breadth_metric = _normalize_text(regime_source.get("breadth_metric"))
        breadth_ratio = float(regime_source.get("breadth_ratio"))
        breadth_threshold = float(regime_source.get("breadth_threshold"))
        regime = _normalize_text(regime_source.get("regime")).upper()
    except (TypeError, ValueError) as error:
        blockers.append(f"MARKET_REGIME_INVALID: {type(error).__name__}: {error}")
        return None, blockers

    if schema_version != 2:
        blockers.append("MARKET_REGIME_INVALID: SCHEMA_VERSION")
    if source_run_id != manifest_run_id or source_report_sha256 != manifest_report_sha256:
        blockers.append("MARKET_REGIME_STALE: MANIFEST_MISMATCH")
    if source_ticker_count != manifest_ticker_count:
        blockers.append("MARKET_REGIME_STALE: TICKER_COUNT_MISMATCH")
    if not risk_policy_id:
        blockers.append("MARKET_REGIME_INVALID: RISK_POLICY_ID")
    elif risk_policy_id != risk_config.risk_policy_id:
        blockers.append("MARKET_REGIME_STALE: RISK_POLICY_ID_MISMATCH")
    if not breadth_metric:
        blockers.append("MARKET_REGIME_INVALID: BREADTH_METRIC")
    elif breadth_metric != risk_config.breadth_metric:
        blockers.append("MARKET_REGIME_STALE: BREADTH_METRIC_MISMATCH")
    if not (0.0 <= breadth_ratio <= 1.0):
        blockers.append("MARKET_REGIME_INVALID: BREADTH_RATIO_RANGE")
    if not (0.0 <= breadth_threshold <= 1.0):
        blockers.append("MARKET_REGIME_INVALID: BREADTH_THRESHOLD_RANGE")
    if abs(breadth_threshold - risk_config.breadth_threshold) > 1e-9:
        blockers.append("MARKET_REGIME_STALE: BREADTH_THRESHOLD_MISMATCH")
    if regime not in {"BULL", "SIDEWAYS", "NEUTRAL", "BEAR"}:
        blockers.append("MARKET_REGIME_INVALID: REGIME")
    if breadth_ratio < risk_config.breadth_threshold and regime != "BEAR":
        blockers.append("MARKET_CONTEXT_INCONSISTENT: BEAR_REQUIRED")
    if breadth_ratio >= risk_config.breadth_threshold and regime == "BEAR":
        blockers.append("MARKET_CONTEXT_INCONSISTENT: BEAR_FORBIDDEN")

    if blockers:
        return None, blockers

    return (
        {
            "risk_policy_id": risk_policy_id,
            "breadth_metric": breadth_metric,
            "breadth_ratio": breadth_ratio,
            "breadth_threshold": breadth_threshold,
            "regime": regime,
            "source_run_id": source_run_id,
            "source_report_sha256": source_report_sha256,
            "source_ticker_count": source_ticker_count,
        },
        [],
    )


def _file_sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _trade_signals_context(
    root: Path,
    candidate_path: Path,
    source_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    blockers: list[str] = []
    manifest_source, manifest_error = _read_json(resolve_path(root, TRADE_SIGNALS_MANIFEST_FILE))
    if manifest_error:
        blockers.append(f"TRADE_SIGNALS_MANIFEST_INVALID: {manifest_error}")
        return None, blockers

    if not candidate_path.is_file():
        blockers.append(f"TRADE_SIGNALS_INVALID: FILE_MISSING: {candidate_path}")
        return None, blockers

    try:
        schema_version = int(manifest_source.get("schema_version", 0))
        source_run_id = _normalize_text(manifest_source.get("source_run_id"))
        source_report_sha256 = _normalize_text(manifest_source.get("source_report_sha256"))
        source_ticker_count = int(manifest_source.get("source_ticker_count", 0))
        trade_signals_sha256 = _normalize_text(manifest_source.get("trade_signals_sha256"))
        market_regime_sha256 = _normalize_text(manifest_source.get("market_regime_sha256"))
        trade_signals_row_count = int(manifest_source.get("trade_signals_row_count", 0))
        actual_trade_signals_sha256 = _file_sha256(candidate_path)
        actual_market_regime_sha256 = _file_sha256(resolve_path(root, MARKET_REGIME_FILE))
    except (OSError, TypeError, ValueError) as error:
        blockers.append(f"TRADE_SIGNALS_MANIFEST_INVALID: {type(error).__name__}: {error}")
        return None, blockers

    source_manifest_run_id = _normalize_text(source_manifest.get("run_id"))
    source_manifest_report_sha256 = _normalize_text(source_manifest.get("report_sha256"))
    source_manifest_ticker_count = int(source_manifest.get("ticker_count", 0))

    if schema_version != 1:
        blockers.append("TRADE_SIGNALS_MANIFEST_INVALID: SCHEMA_VERSION")
    if not source_run_id or not source_report_sha256:
        blockers.append("TRADE_SIGNALS_MANIFEST_INVALID: SOURCE_FIELDS")
    if source_run_id != source_manifest_run_id or source_report_sha256 != source_manifest_report_sha256:
        blockers.append("TRADE_SIGNALS_STALE: SOURCE_MISMATCH")
    if source_ticker_count != source_manifest_ticker_count or source_ticker_count != 225:
        blockers.append("TRADE_SIGNALS_INVALID: SOURCE_TICKER_COUNT")
    if trade_signals_sha256 != actual_trade_signals_sha256:
        blockers.append("TRADE_SIGNALS_STALE: HASH_MISMATCH")
    if market_regime_sha256 != actual_market_regime_sha256:
        blockers.append("TRADE_SIGNALS_STALE: MARKET_REGIME_HASH_MISMATCH")
    if trade_signals_row_count < 0:
        blockers.append("TRADE_SIGNALS_INVALID: ROW_COUNT")

    if blockers:
        return None, blockers

    return (
        {
            "schema_version": schema_version,
            "source_run_id": source_run_id,
            "source_report_sha256": source_report_sha256,
            "source_ticker_count": source_ticker_count,
            "trade_signals_sha256": trade_signals_sha256,
            "market_regime_sha256": market_regime_sha256,
            "trade_signals_row_count": trade_signals_row_count,
        },
        [],
    )


def _activation_config(payload: Mapping[str, Any]) -> tuple[str, str, str, str, frozenset[str]]:
    activation = payload if isinstance(payload, Mapping) else {}
    operating_mode = _normalize_text(activation.get("operating_mode", "")).upper()
    profile = OPERATING_MODE_PROFILES.get(operating_mode)
    if profile is None:
        raise ValueError(
            "operating_mode must be PAPER_SAFE, LIVE_ACTIVE, or LIVE_RECONCILE_ONLY"
        )

    trading_mode = _normalize_text(activation.get("trading_mode", profile["trading_mode"])).upper() or profile["trading_mode"]
    execution_mode = _normalize_text(activation.get("execution_mode", profile["execution_mode"])).upper() or profile["execution_mode"]
    trading_actions = _normalize_text(activation.get("trading_actions", profile["trading_actions"])).upper() or profile["trading_actions"]
    allowed_raw = activation.get("allowed_trading_actions", tuple(profile["allowed_trading_actions"]))
    if isinstance(allowed_raw, Sequence) and not isinstance(allowed_raw, (str, bytes)):
        allowed_trading_actions = frozenset(
            value
            for value in (_normalize_text(item).upper() for item in allowed_raw)
            if value
        )
    else:
        allowed_trading_actions = frozenset(profile["allowed_trading_actions"])
    if not allowed_trading_actions:
        allowed_trading_actions = frozenset(profile["allowed_trading_actions"])

    if trading_mode != profile["trading_mode"]:
        raise ValueError(f"operating_mode={operating_mode} requires trading_mode={profile['trading_mode']}")
    if execution_mode != profile["execution_mode"]:
        raise ValueError(f"operating_mode={operating_mode} requires execution_mode={profile['execution_mode']}")
    if trading_actions != profile["trading_actions"]:
        raise ValueError(f"operating_mode={operating_mode} requires trading_actions={profile['trading_actions']}")
    if allowed_trading_actions != frozenset(profile["allowed_trading_actions"]):
        raise ValueError(
            f"operating_mode={operating_mode} requires allowed_trading_actions={sorted(profile['allowed_trading_actions'])}"
        )
    return operating_mode, trading_mode, execution_mode, trading_actions, allowed_trading_actions


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
    trading_mode: str,
    execution_mode: str,
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
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
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
    allowed_trading_actions: frozenset[str] = DEFAULT_ALLOWED_TRADING_ACTIONS,
) -> list[str]:
    blockers = list(global_blockers)
    if operating_scope == "MONITOR_ONLY":
        blockers.append("MONITOR_ONLY_SCOPE")
    elif operating_scope not in ALLOWED_OPERATING_SCOPES:
        blockers.append("OPERATING_SCOPE_INVALID")
    if trading_actions not in allowed_trading_actions:
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
    client_order_id: str = "",
    lot_size: int = 100,
    max_loss_limit_yen: float | None = None,
    trading_mode: str = DEFAULT_TRADING_MODE,
    execution_mode: str = DEFAULT_EXECUTION_MODE,
    allowed_trading_actions: frozenset[str] = DEFAULT_ALLOWED_TRADING_ACTIONS,
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
        trading_mode=trading_mode,
        execution_mode=execution_mode,
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
        allowed_trading_actions=allowed_trading_actions,
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
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
        "signal_date": signal_date,
        "ticker": decision.ticker,
        "market": _market_from_ticker(decision.ticker),
        "side": side,
        "order_type": order_type,
        "client_order_id": client_order_id,
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
    trading_mode: str,
    execution_mode: str,
    allowed_trading_actions: frozenset[str],
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
                "trading_mode": trading_mode,
                "execution_mode": execution_mode,
                "signal_date": "",
                "ticker": ticker or "",
                "client_order_id": "",
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
            trading_mode=trading_mode,
            execution_mode=execution_mode,
            allowed_trading_actions=allowed_trading_actions,
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


def _order_request_lookup_by_ticker(
    orders: Sequence[OrderRequest],
    *,
    label: str,
) -> tuple[dict[str, OrderRequest], list[str]]:
    lookup: dict[str, OrderRequest] = {}
    blockers: list[str] = []
    for order in orders:
        ticker = _normalize_text(getattr(order, "ticker", "")).upper()
        if not ticker:
            blockers.append(f"{label}:TICKER_MISSING")
            continue
        if ticker in lookup:
            blockers.append(f"{label}:DUPLICATE_TICKER:{ticker}")
            continue
        lookup[ticker] = order
    return lookup, blockers


def _order_request_lookup_by_client_order_id(
    orders: Sequence[OrderRequest],
    *,
    label: str,
) -> tuple[dict[str, OrderRequest], list[str]]:
    lookup: dict[str, OrderRequest] = {}
    blockers: list[str] = []
    for order in orders:
        client_order_id = _normalize_text(getattr(order, "client_order_id", ""))
        if not client_order_id:
            blockers.append(f"{label}:CLIENT_ORDER_ID_MISSING")
            continue
        if client_order_id in lookup:
            blockers.append(f"{label}:DUPLICATE_CLIENT_ORDER_ID:{client_order_id}")
            continue
        lookup[client_order_id] = order
    return lookup, blockers


def _approved_payload_lookup_by_client_order_id(
    rows: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    lookup: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for row in rows:
        if _normalize_text(row.get("status", "")).upper() != "APPROVED":
            continue
        client_order_id = _normalize_text(row.get("client_order_id", ""))
        if not client_order_id:
            blockers.append(f"{label}:CLIENT_ORDER_ID_MISSING")
            continue
        if client_order_id in lookup:
            blockers.append(f"{label}:DUPLICATE_CLIENT_ORDER_ID:{client_order_id}")
            continue
        lookup[client_order_id] = dict(row)
    return lookup, blockers


def _count_bridge_queue_entries(root: Path, relative_path: str) -> int:
    path = resolve_path(root, relative_path)
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    try:
        return sum(1 for item in path.iterdir() if item.is_file())
    except OSError:
        return 1


def _live_submit_preflight(root: Path, broker: BrokerAdapter) -> list[str]:
    blockers: list[str] = []
    try:
        broker.refresh_pending_orders()
    except Exception as error:
        raise RuntimeError(f"BROKER_REFRESH_FAILED: {type(error).__name__}: {error}") from error

    nonterminal_count = 0
    if hasattr(broker, "nonterminal_order_count"):
        try:
            nonterminal_count = int(getattr(broker, "nonterminal_order_count")())
        except Exception as error:
            raise RuntimeError(f"BROKER_NONTERMINAL_COUNT_FAILED: {type(error).__name__}: {error}") from error
    if nonterminal_count != 0:
        blockers.append(f"RECONCILE_REQUIRED: BROKER_NONTERMINAL_ORDERS={nonterminal_count}")

    pending_count = _count_bridge_queue_entries(root, PRODUCTION_BRIDGE_PENDING_RELATIVE)
    processing_count = _count_bridge_queue_entries(root, PRODUCTION_BRIDGE_PROCESSING_RELATIVE)
    if pending_count != 0:
        blockers.append(f"RECONCILE_REQUIRED: BRIDGE_PENDING={pending_count}")
    if processing_count != 0:
        blockers.append(f"RECONCILE_REQUIRED: BRIDGE_PROCESSING={processing_count}")
    return blockers


def _resolve_live_dispatch_mode(
    operating_mode: str,
    *,
    broker_health_ok: bool | None = None,
    queue_clear: bool | None = None,
    submit_status: str | None = None,
    submit_error: bool = False,
) -> str:
    normalized_mode = _normalize_text(operating_mode).upper()
    if normalized_mode != "LIVE_ACTIVE":
        return "LIVE_RECONCILE_ONLY" if normalized_mode == "LIVE_RECONCILE_ONLY" else normalized_mode
    if broker_health_ok is False:
        return "LIVE_RECONCILE_ONLY"
    if queue_clear is False:
        return "LIVE_RECONCILE_ONLY"
    if submit_error:
        return "LIVE_RECONCILE_ONLY"
    normalized_status = _normalize_text(submit_status).upper()
    if normalized_status in {"PENDING", "ACCEPTED", "PARTIALLY_FILLED"}:
        return "LIVE_RECONCILE_ONLY"
    return "LIVE_ACTIVE"


@dataclass(frozen=True)
class PreorderDispatchContext:
    report: dict[str, Any]
    generated_at: datetime
    expires_at: datetime
    state_path: Path
    config: dict[str, Any]
    approved_idempotency_keys: frozenset[str]
    report_blockers: tuple[str, ...]
    trade_signals_context: dict[str, Any] | None
    executable_orders_by_client_order_id: dict[str, OrderRequest]
    accepted_orders_by_client_order_id: dict[str, OrderRequest]
    approved_payloads_by_client_order_id: dict[str, dict[str, Any]]


def _build_preorder_dispatch_context(
    *,
    report: dict[str, Any],
    generated: datetime,
    expires_at: datetime,
    state_path: Path,
    config: Mapping[str, Any],
    report_blockers: Sequence[str],
    approved_idempotency_keys: set[str],
    trade_signals_context: dict[str, Any] | None,
    executable_orders_by_client_order_id: dict[str, OrderRequest],
    accepted_orders_by_client_order_id: dict[str, OrderRequest],
    approved_payloads_by_client_order_id: dict[str, dict[str, Any]],
) -> PreorderDispatchContext:
    return PreorderDispatchContext(
        report=report,
        generated_at=generated,
        expires_at=expires_at,
        state_path=state_path,
        config=dict(config),
        approved_idempotency_keys=frozenset(approved_idempotency_keys),
        report_blockers=tuple(dict.fromkeys(str(value) for value in report_blockers)),
        trade_signals_context=trade_signals_context,
        executable_orders_by_client_order_id=executable_orders_by_client_order_id,
        accepted_orders_by_client_order_id=accepted_orders_by_client_order_id,
        approved_payloads_by_client_order_id=approved_payloads_by_client_order_id,
    )


def _build_preorder_report_artifacts(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], PreorderDispatchContext]:
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

    try:
        _operating_mode, trading_mode, execution_mode, trading_actions, allowed_trading_actions = _activation_config(direct_config)
    except Exception as error:
        report_blockers.append(f"ACTIVATION_CONFIG_INVALID: {type(error).__name__}: {error}")
        _operating_mode = "PAPER_SAFE"
        trading_mode = DEFAULT_TRADING_MODE
        execution_mode = DEFAULT_EXECUTION_MODE
        trading_actions = DEFAULT_TRADING_ACTIONS
        allowed_trading_actions = DEFAULT_ALLOWED_TRADING_ACTIONS

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
    source_manifest, source_manifest_error = _read_json(resolve_path(root, NOTIFICATION_SOURCE_MANIFEST_FILE))
    if source_manifest_error:
        report_blockers.append(f"NOTIFICATION_SOURCE_MANIFEST_INVALID: {source_manifest_error}")
        source_manifest = {}
    market_context: dict[str, Any] | None = None
    if risk_config is not None:
        market_context, market_context_blockers = _market_regime_context(root, risk_config)
        report_blockers.extend(market_context_blockers)

    operating_scope = _normalize_text(os.environ.get("PHOENIX_OPERATING_SCOPE", "")).upper() or "UNKNOWN"
    if operating_scope not in ALLOWED_OPERATING_SCOPES:
        report_blockers.append("OPERATING_SCOPE_INVALID")
    if trading_actions not in allowed_trading_actions:
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
        "mode": trading_mode,
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
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
        context = _build_preorder_dispatch_context(
            report=report,
            generated=generated,
            expires_at=expires_at,
            state_path=state_path,
            config=direct_config,
            report_blockers=report_blockers,
            approved_idempotency_keys=set(),
            trade_signals_context=None,
            executable_orders_by_client_order_id={},
            accepted_orders_by_client_order_id={},
            approved_payloads_by_client_order_id={},
        )
        return report, context

    source = str(candidate_path.relative_to(root)) if candidate_path.is_relative_to(root) else str(candidate_path)
    trade_signals_context: dict[str, Any] | None = None
    trade_signals_context_blockers: list[str] = []
    if source_manifest:
        trade_signals_context, trade_signals_context_blockers = _trade_signals_context(
            root,
            candidate_path,
            source_manifest,
        )
        report_blockers.extend(trade_signals_context_blockers)
        if trade_signals_context is not None and int(trade_signals_context.get("trade_signals_row_count", -1)) != len(candidate_batch.candidates):
            report_blockers.append("TRADE_SIGNALS_INVALID: ROW_COUNT_MISMATCH")
            trade_signals_context = None
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
            trading_mode=trading_mode,
            execution_mode=execution_mode,
            allowed_trading_actions=allowed_trading_actions,
        )
    else:
        broker, broker_error = _load_broker(root, direct_config)
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
                trading_mode=trading_mode,
                execution_mode=execution_mode,
                allowed_trading_actions=allowed_trading_actions,
            )
        else:
            try:
                effective_total_invested_pct_override = resolve_effective_total_invested_pct(
                    risk_config,
                    market_context,
                )
                sizing_decisions = size_candidates(
                    broker,
                    candidate_batch.candidates,
                    sizing_config,
                    max_total_invested_pct_override=effective_total_invested_pct_override,
                )
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
                    trading_mode=trading_mode,
                    execution_mode=execution_mode,
                    allowed_trading_actions=allowed_trading_actions,
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
                        trading_mode=trading_mode,
                        execution_mode=execution_mode,
                        allowed_trading_actions=allowed_trading_actions,
                    )
                else:
                    executable_decisions = [decision for decision in sizing_decisions if decision.executable]
                    run_id = f"PHX42-{candidate_batch.audit.eligible_candidates_sha256[:16].upper()}"
                    executable_orders = build_order_requests(
                        executable_decisions,
                        run_id=run_id,
                    )
                    risk_state: RiskState | None = None
                    if executable_orders:
                        try:
                            risk_state = load_risk_state(resolve_path(root, str(risk_source.get("files", {}).get("state", "state/v7_risk_state.json"))), account_snapshot.equity_yen)
                        except Exception as error:
                            report_blockers.append(f"RISK_STATE_INVALID: {type(error).__name__}: {error}")
                            risk_state = None
                    if executable_orders and risk_state is not None and (not risk_config.risk_v2_enabled or market_context is not None):
                        try:
                            risk_report = evaluate_orders(
                                broker,
                                executable_orders,
                                risk_config,
                                risk_state,
                                market_context=market_context,
                            )
                        except Exception as error:
                            report_blockers.append(f"RISK_EVALUATION_FAILED: {type(error).__name__}: {error}")
                            risk_report = None
                    else:
                        risk_report = None
                    risk_reason_map = _decision_reason_map(getattr(risk_report, "decisions", ()))
                    executable_orders_by_ticker, executable_lookup_blockers = _order_request_lookup_by_ticker(
                        executable_orders,
                        label="EXECUTABLE_ORDERS",
                    )
                    report_blockers.extend(executable_lookup_blockers)
                    executable_orders_by_client_order_id, executable_client_lookup_blockers = _order_request_lookup_by_client_order_id(
                        executable_orders,
                        label="EXECUTABLE_ORDERS",
                    )
                    report_blockers.extend(executable_client_lookup_blockers)
                    accepted_orders_by_client_order_id: dict[str, OrderRequest] = {}
                    accepted_orders_source = getattr(risk_report, "accepted_orders", _MISSING)
                    has_accepted_orders = accepted_orders_source is not _MISSING
                    if risk_report is not None and has_accepted_orders:
                        accepted_orders_by_client_order_id, accepted_client_lookup_blockers = _order_request_lookup_by_client_order_id(
                            accepted_orders_source,
                            label="ACCEPTED_ORDERS",
                        )
                        report_blockers.extend(accepted_client_lookup_blockers)
                        for client_order_id, accepted_order in accepted_orders_by_client_order_id.items():
                            executable_order = executable_orders_by_client_order_id.get(client_order_id)
                            if executable_order is None:
                                report_blockers.append(f"ACCEPTED_ORDER_NOT_IN_EXECUTABLES:{client_order_id}")
                                continue
                            if _normalize_text(accepted_order.client_order_id).upper() != _normalize_text(executable_order.client_order_id).upper():
                                report_blockers.append(f"CLIENT_ORDER_ID_MISMATCH:{client_order_id}")
                    rows = []
                    for row_index, (_, raw_row) in enumerate(candidate_batch.candidates.iterrows()):
                        decision = sizing_decisions[row_index]
                        risk_reason = None
                        client_order_id = ""
                        if decision.executable:
                            executable_order = executable_orders_by_ticker.get(decision.ticker)
                            if executable_order is None:
                                report_blockers.append(f"EXECUTABLE_ORDER_NOT_FOUND:{decision.ticker}")
                            else:
                                client_order_id = executable_order.client_order_id
                                if risk_report is not None and has_accepted_orders:
                                    accepted_order = accepted_orders_by_client_order_id.get(client_order_id)
                                    if accepted_order is None:
                                        risk_reason = risk_reason_map.get(decision.ticker) or "RISK_RESULT_MISSING"
                                    else:
                                        if _normalize_text(accepted_order.ticker).upper() != _normalize_text(executable_order.ticker).upper():
                                            report_blockers.append(f"ACCEPTED_ORDER_TICKER_MISMATCH:{client_order_id}")
                                        client_order_id = accepted_order.client_order_id
                        payload, idempotency_key, approved = _build_instruction_row(
                            row=raw_row.to_dict(),
                            decision=decision,
                            generated_at=generated,
                            expires_at=expires_at,
                            source=source,
                            operating_scope=operating_scope,
                            trading_actions=trading_actions,
                            client_order_id=client_order_id,
                            approved_keys=approved_keys,
                            global_blockers=report_blockers + ([f"RISK:{risk_reason}"] if risk_reason else []),
                            lot_size=sizing_config.lot_size,
                            max_loss_limit_yen=max_loss_limit_yen,
                            trading_mode=trading_mode,
                            execution_mode=execution_mode,
                            allowed_trading_actions=allowed_trading_actions,
                        )
                        rows.append(payload)

    approved_payloads_by_client_order_id, approved_payload_lookup_blockers = _approved_payload_lookup_by_client_order_id(
        rows,
        label="APPROVED_PAYLOADS",
    )
    report_blockers.extend(approved_payload_lookup_blockers)

    rows_frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    approved_count = int((rows_frame.get("status", pd.Series(dtype=str)).astype(str) == "APPROVED").sum()) if not rows_frame.empty else 0
    blocked_count = len(rows_frame) - approved_count
    report_status = "APPROVED" if rows_frame is not None and not rows_frame.empty and blocked_count == 0 and not report_blockers else "BLOCKED"
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
        "mode": trading_mode,
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
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
    context = _build_preorder_dispatch_context(
        report=report,
        generated=generated,
        expires_at=expires_at,
        state_path=state_path,
        config=direct_config,
        report_blockers=report_blockers,
        approved_idempotency_keys=approved_keys,
        trade_signals_context=trade_signals_context,
        executable_orders_by_client_order_id=executable_orders_by_client_order_id,
        accepted_orders_by_client_order_id=accepted_orders_by_client_order_id,
        approved_payloads_by_client_order_id=approved_payloads_by_client_order_id,
    )
    return report, context


def build_preorder_report(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    report, _ = _build_preorder_report_artifacts(root, generated_at=generated_at)
    return report


def build_preorder_dispatch_context(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> PreorderDispatchContext:
    _, context = _build_preorder_report_artifacts(root, generated_at=generated_at)
    return context


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP42 LOCAL REAL-TRADE BRIDGE PRE-ORDER GATE",
        "=" * 92,
        f"Status               : {report.get('status', '')}",
        f"Mode                 : {report.get('mode', DEFAULT_TRADING_MODE)}",
        f"Trading mode         : {report.get('trading_mode', DEFAULT_TRADING_MODE)}",
        f"Execution mode       : {report.get('execution_mode', DEFAULT_EXECUTION_MODE)}",
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
                    "trading_mode": row.get("trading_mode", DEFAULT_TRADING_MODE),
                    "execution_mode": row.get("execution_mode", DEFAULT_EXECUTION_MODE),
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
                "trading_mode": report.get("trading_mode", DEFAULT_TRADING_MODE),
                "execution_mode": report.get("execution_mode", DEFAULT_EXECUTION_MODE),
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
    print(f"Trading mode         : {report.get('trading_mode', DEFAULT_TRADING_MODE)}")
    print(f"Execution mode       : {report.get('execution_mode', DEFAULT_EXECUTION_MODE)}")
    print(f"Trading actions      : {report.get('trading_actions', '')}")
    print(f"Approved instructions: {report.get('approved_count', 0)}")
    print(f"Blocked instructions : {report.get('blocked_count', 0)}")
    print(f"Orders submitted     : {report.get('orders_submitted', 0)}")
    print(f"Instruction file     : {report.get('instruction_file', '')}")
    print(f"Audit report         : {report.get('report_json', '')}")
    print(f"Audit JSONL          : {report.get('audit_jsonl', '')}")
    print("=" * 92)


def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> list[Any]:
    report = context.report
    operating_mode, trading_mode, execution_mode, trading_actions, _ = _activation_config(context.config)

    if operating_mode == "PAPER_SAFE":
        return []

    report_blockers = tuple(dict.fromkeys(str(value) for value in report.get("blockers", [])))
    if _normalize_text(report.get("status", "")).upper() != "APPROVED":
        raise RuntimeError(f"Dispatch requires APPROVED preorder report: {report.get('status', '')}")
    if report_blockers != context.report_blockers:
        raise RuntimeError("Dispatch report blockers changed after report generation")

    state_approved_idempotency_keys, state_error = _parse_state(context.state_path)
    if state_error is not None:
        raise RuntimeError(f"STATE_INVALID: {state_error}")
    if state_approved_idempotency_keys != set(context.approved_idempotency_keys):
        raise RuntimeError("Approved idempotency keys changed after save")

    if int(report.get("approved_count", 0) or 0) != len(context.approved_payloads_by_client_order_id):
        raise RuntimeError("Approved payload count changed after report generation")

    candidate_path = resolve_path(root, str(report.get("source", DEFAULT_CANDIDATE_PATH)))
    current_source_manifest, source_error = _read_json(resolve_path(root, NOTIFICATION_SOURCE_MANIFEST_FILE))
    if source_error:
        raise RuntimeError(f"NOTIFICATION_SOURCE_MANIFEST_INVALID: {source_error}")
    current_trade_signals_context, trade_signals_blockers = _trade_signals_context(
        root,
        candidate_path,
        current_source_manifest,
    )
    if trade_signals_blockers:
        raise RuntimeError("; ".join(trade_signals_blockers))
    if context.trade_signals_context is None:
        raise RuntimeError("TRADE_SIGNALS_CONTEXT_MISSING")
    if current_trade_signals_context != context.trade_signals_context:
        raise RuntimeError("TRADE_SIGNALS_CONTEXT_CHANGED")

    broker = create_broker(dict(context.config), root)
    preflight_ran = False
    effective_mode = operating_mode
    try:
        broker_health = broker.health_check()
    except Exception as error:
        broker_health = None
        if operating_mode == "LIVE_ACTIVE":
            effective_mode = _resolve_live_dispatch_mode(
                operating_mode,
                broker_health_ok=False,
            )
        else:
            effective_mode = _resolve_live_dispatch_mode(operating_mode)
    else:
        if operating_mode == "LIVE_ACTIVE":
            effective_mode = _resolve_live_dispatch_mode(
                operating_mode,
                broker_health_ok=bool(broker_health.healthy),
            )

    if effective_mode == "LIVE_ACTIVE" and operating_mode == "LIVE_ACTIVE":
        live_preflight_blockers = _live_submit_preflight(root, broker)
        preflight_ran = True
        if live_preflight_blockers:
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                queue_clear=False,
            )

    if effective_mode == "LIVE_RECONCILE_ONLY":
        if not preflight_ran:
            try:
                broker.refresh_pending_orders()
            except Exception as error:
                raise RuntimeError(f"BROKER_REFRESH_FAILED: {type(error).__name__}: {error}") from error
        return []

    results: list[Any] = []
    for client_order_id, payload in context.approved_payloads_by_client_order_id.items():
        if _normalize_text(payload.get("client_order_id", "")).upper() != _normalize_text(client_order_id).upper():
            raise RuntimeError(f"CLIENT_ORDER_ID_MISMATCH:{client_order_id}")
        accepted_order = context.accepted_orders_by_client_order_id.get(client_order_id)
        if accepted_order is None:
            raise RuntimeError(f"ACCEPTED_ORDER_NOT_FOUND:{client_order_id}")
        if _normalize_text(accepted_order.client_order_id).upper() != _normalize_text(client_order_id).upper():
            raise RuntimeError(f"ACCEPTED_ORDER_IDENTITY_MISMATCH:{client_order_id}")

        live_preflight_blockers = _live_submit_preflight(root, broker)
        if live_preflight_blockers:
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                queue_clear=False,
            )
            break

        try:
            submit_result = broker.submit_order(accepted_order)
        except Exception as error:
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                submit_error=True,
            )
            raise RuntimeError(f"BROKER_SUBMIT_FAILED:{client_order_id}: {type(error).__name__}: {error}") from error

        submit_status = getattr(submit_result, "status", None)
        submit_status_name = _normalize_text(getattr(submit_status, "value", submit_status)).upper()
        if submit_status_name == "REJECTED":
            submit_message = _normalize_text(getattr(submit_result, "message", ""))
            raise RuntimeError(f"BROKER_REJECTED:{client_order_id}:{submit_message}")
        if submit_status_name in {"PENDING", "ACCEPTED", "PARTIALLY_FILLED"}:
            results.append(submit_result)
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                submit_status=submit_status_name,
            )
            break
        if submit_status_name != "FILLED":
            raise RuntimeError(f"UNEXPECTED_BROKER_STATUS:{client_order_id}:{submit_status_name}")
        results.append(submit_result)

    return results


def run_order_bridge_gate(
    root: Path,
    *,
    context: PreorderDispatchContext | None = None,
) -> dict[str, Any]:
    if context is None:
        context = build_preorder_dispatch_context(root)
    report = context.report
    save_preorder_outputs(root, report)
    dispatch_approved_orders(root, context)
    return report
