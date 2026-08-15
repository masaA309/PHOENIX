from __future__ import annotations

import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from phoenix_core.broker import PaperBroker
from phoenix_core.performance_tracker import atomic_write, resolve_path
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    build_order_requests,
    normalize_candidate_frame,
    size_candidates,
)
from phoenix_core.risk_controller import RiskConfig, RiskState, evaluate_orders


SCHEMA_VERSION = 2
VERSION = "PHOENIX v7 Step46 Manual Ticket Draft"
CREATED_BY = "PHOENIX_STEP46_MANUAL_TICKET_DRAFT"
STATUS = "REVIEW_REQUIRED"
TRADING_MODE = "PAPER"
EXECUTION_MODE = "MANUAL_ONLY"
SIDE = "BUY"
ORDER_TYPE = "LIMIT"
MANUAL_LOT_SIZE = 100
MANUAL_APPROVAL_REQUIRED = True
RSS_SEND_ALLOWED = False
ORDERS_SUBMITTED = 0
TTL_MINUTES = 15
CAPITAL_BASIS_YEN = 500000.0
JST = ZoneInfo("Asia/Tokyo")

REPORT_JSON_FILE = "reports/v7_manual_trade_ticket.json"
REPORT_CSV_FILE = "reports/v7_manual_trade_ticket.csv"
REPORT_TEXT_FILE = "reports/v7_manual_trade_ticket.txt"

SOURCE_FILES = [
    "reports/trade_signals.csv",
    "reports/ai_judgement.csv",
    "reports/ai_judgement_manifest.json",
    "reports/report_20260807.csv",
    "reports/market_regime.json",
    "data/market_risk_latest.json",
    "state/v7_paper_broker.json",
    "config/v7_position_sizer_config.json",
]


def _now_jst() -> datetime:
    return datetime.now(JST)


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and value != value:
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _stable_hash(payload: Any) -> str:
    encoded = _canonical_json_text(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite values are not allowed in canonical JSON")
        if value.is_integer():
            return str(int(value))
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, Mapping):
        items = []
        for key in sorted(value.keys(), key=lambda item: str(item)):
            items.append(
                f"{json.dumps(str(key), ensure_ascii=False, separators=(',', ':'))}:{_canonical_json_text(value[key])}"
            )
        return "{" + ",".join(items) + "}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            frame = pd.read_csv(path, encoding=encoding)
            return frame if not frame.empty else pd.DataFrame()
        except Exception:
            continue
    raise ValueError(f"Could not read CSV: {path}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def _column_name(frame: pd.DataFrame, *candidates: str) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return ""


def _column_series(
    frame: pd.DataFrame,
    *candidates: str,
    default: Any = "",
) -> pd.Series:
    column = _column_name(frame, *candidates)
    if not column:
        return pd.Series([default] * len(frame), index=frame.index)
    value = frame.loc[:, column]
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]
    return value


def _mapping_value(mapping: Mapping[str, Any], *candidates: str, default: Any = "") -> Any:
    for candidate in candidates:
        if candidate not in mapping:
            continue
        value = mapping[candidate]
        if value is None:
            continue
        if isinstance(value, float) and value != value:
            continue
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() == "nan":
                continue
        return value
    return default


def _copy_first_present_column(frame: pd.DataFrame, target: str, *sources: str) -> None:
    if target in frame.columns:
        return
    for source in sources:
        if source in frame.columns:
            frame[target] = frame[source]
            return


def _signal_date(report_path: Path, daily_report: pd.DataFrame) -> str:
    for column in (
        "signal_date",
        "SignalDate",
        "signalDate",
        "execution_date",
        "ExecutionDate",
    ):
        if column not in daily_report.columns:
            continue
        values = pd.to_datetime(daily_report[column], errors="coerce").dropna()
        if values.empty:
            continue
        return values.dt.date.max().isoformat()

    match = re.search(r"report_(\d{8})", report_path.stem)
    if match:
        return (
            datetime.strptime(match.group(1), "%Y%m%d").date()
            + timedelta(days=1)
        ).isoformat()

    for column in ("基準日", "Date", "date", "report_date", "ReportDate"):
        if column not in daily_report.columns:
            continue
        values = pd.to_datetime(daily_report[column], errors="coerce").dropna()
        if values.empty:
            continue
        return (
            values.dt.date.max()
            + timedelta(days=1)
        ).isoformat()

    return ""


def _load_market_context(
    market_regime: Mapping[str, Any],
    market_risk: Mapping[str, Any],
) -> dict[str, Any]:
    settings = market_regime.get("settings", {})
    if not isinstance(settings, Mapping):
        settings = {}

    risk_score = _safe_float(
        _mapping_value(
            market_risk,
            "market_risk_score",
            "risk_score",
            "score",
            "MarketRiskScore",
            "total_score",
            default=50.0,
        ),
        50.0,
    )
    risk_level = _safe_text(
        _mapping_value(
            market_risk,
            "market_risk_level",
            "risk_level",
            "level",
            "status",
            "MarketRiskLevel",
            default="WATCH",
        ),
        "WATCH",
    ).upper()

    return {
        "regime": _safe_text(market_regime.get("regime"), "SIDEWAYS").upper(),
        "confidence": _safe_float(market_regime.get("confidence"), 0.0),
        "regime_score": _safe_float(market_regime.get("score"), 0.0),
        "strategy": _safe_text(market_regime.get("strategy"), "NEUTRAL"),
        "capital_usage_percent": _safe_float(
            settings.get("capital_usage_percent"), 100.0
        ),
        "risk_per_trade_multiplier": _safe_float(
            settings.get("risk_per_trade_multiplier"), 1.0
        ),
        "stop_multiplier": _safe_float(settings.get("stop_multiplier"), 1.0),
        "target_multiplier": _safe_float(settings.get("target_multiplier"), 1.0),
        "max_positions": max(1, _safe_int(settings.get("max_positions"), 5)),
        "market_risk_score": risk_score,
        "market_risk_level": risk_level,
    }


def _load_position_sizing_config(
    root: Path,
    market_context: Mapping[str, Any],
) -> PositionSizingConfig:
    payload = _read_json(resolve_path(root, "config/v7_position_sizer_config.json"))
    config = payload.get("position_sizing", payload)
    if not isinstance(config, Mapping):
        raise ValueError("config/v7_position_sizer_config.json is invalid")

    capital_usage_ratio = max(
        0.0,
        min(_safe_float(market_context.get("capital_usage_percent"), 100.0) / 100.0, 1.0),
    )
    risk_multiplier = max(
        0.0,
        _safe_float(market_context.get("risk_per_trade_multiplier"), 1.0),
    )
    stop_multiplier = max(
        0.0,
        _safe_float(market_context.get("stop_multiplier"), 1.0),
    )

    return PositionSizingConfig(
        risk_per_trade_pct=_safe_float(config.get("risk_per_trade_pct"), 0.01)
        * risk_multiplier,
        max_position_pct=min(
            _safe_float(config.get("max_position_pct"), 0.30),
            capital_usage_ratio,
        ),
        max_total_invested_pct=min(
            _safe_float(config.get("max_total_invested_pct"), 0.80),
            capital_usage_ratio,
        ),
        minimum_cash_reserve_pct=_safe_float(
            config.get("minimum_cash_reserve_pct"), 0.10
        ),
        fallback_stop_distance_pct=_safe_float(
            config.get("fallback_stop_distance_pct"), 0.03
        )
        * stop_multiplier,
        lot_size=MANUAL_LOT_SIZE,
        maximum_quantity_per_ticker=_safe_int(
            config.get("maximum_quantity_per_ticker"), 1000
        ),
        allow_pyramiding=bool(config.get("allow_pyramiding", False)),
        commission_buffer_pct=_safe_float(
            config.get("commission_buffer_pct"), 0.001
        ),
    )


def _load_risk_config(
    market_context: Mapping[str, Any],
    *,
    candidate_count: int,
) -> RiskConfig:
    max_positions = max(
        _safe_int(market_context.get("max_positions"), 5),
        1,
    )
    max_orders_per_run = max(candidate_count, 1)
    return RiskConfig(
        max_daily_loss_pct=0.03,
        max_drawdown_pct=0.10,
        max_positions=max_positions,
        max_total_invested_pct=min(
            _safe_float(market_context.get("capital_usage_percent"), 100.0) / 100.0,
            0.80,
        ),
        max_single_position_pct=min(
            _safe_float(market_context.get("capital_usage_percent"), 100.0) / 100.0,
            0.30,
        ),
        max_orders_per_run=max_orders_per_run,
        max_consecutive_losses=3,
        minimum_cash_reserve_pct=0.10,
        block_on_broker_health_failure=True,
    )


def _prepare_candidate_frame(
    trade_signals: pd.DataFrame,
    market_context: Mapping[str, Any],
) -> pd.DataFrame:
    if trade_signals.empty:
        raise ValueError("trade_signals.csv is empty")

    decision_column = _column_name(
        trade_signals,
        "Trade判定",
        "TradeDecision",
        "decision",
        "Decision",
        "Trade蛻､螳・",
    )
    if not decision_column:
        raise ValueError("trade_signals.csv must contain a BUY decision column")

    buy_mask = (
        trade_signals[decision_column]
        .astype(str)
        .str.strip()
        .str.upper()
        .eq("BUY")
    )
    buy_candidates = trade_signals.loc[buy_mask].copy()
    if buy_candidates.empty:
        raise ValueError("No BUY candidates were found in trade_signals.csv")

    # Normalize alternate column names so the shared position sizing logic can
    # be reused without a second implementation.
    _copy_first_present_column(
        buy_candidates,
        "entry_price",
        "entry_price",
        "limit_price",
        "EntryPrice",
        "Entry",
        "Price",
        "price",
        "謚ｼ縺礼岼萓｡譬ｼ",
        "押し目価格",
    )
    _copy_first_present_column(
        buy_candidates,
        "stop_price",
        "stop_price",
        "stop_loss_price",
        "StopPrice",
        "stop",
        "Stop",
        "謳榊・萓｡譬ｼ",
        "損切価格",
    )
    _copy_first_present_column(
        buy_candidates,
        "AI判断点",
        "AI判断点",
        "ai_score",
        "AI_score",
        "AI Score",
        "AI蛻､譁ｭ轤ｹ",
    )
    _copy_first_present_column(
        buy_candidates,
        "PHOENIX_SCORE",
        "PHOENIX_SCORE",
        "phoenix_score",
        "PhoenixScore",
        "PHOENIX SCORE",
    )
    _copy_first_present_column(
        buy_candidates,
        "MarketRiskScore",
        "MarketRiskScore",
        "market_risk_score",
        "risk_score",
        "MarketRisk",
        "total_score",
    )
    _copy_first_present_column(
        buy_candidates,
        "MarketRiskLevel",
        "MarketRiskLevel",
        "market_risk_level",
        "risk_level",
        "MarketRisk",
    )

    ai_scores = pd.to_numeric(
        _column_series(
            buy_candidates,
            "AI判断点",
            "ai_score",
            "AI_score",
            "AI Score",
            "AI蛻､譁ｭ轤ｹ",
            default=0.0,
        ),
        errors="coerce",
    ).fillna(0.0)
    phoenix_scores = pd.to_numeric(
        _column_series(
            buy_candidates,
            "PHOENIX_SCORE",
            "phoenix_score",
            "PhoenixScore",
            "PHOENIX SCORE",
            default=0.0,
        ),
        errors="coerce",
    ).fillna(0.0)
    market_risk_scores = pd.to_numeric(
        _column_series(
            buy_candidates,
            "MarketRiskScore",
            "market_risk_score",
            "risk_score",
            "MarketRisk",
            "total_score",
            default=0.0,
        ),
        errors="coerce",
    ).fillna(0.0)

    buy_candidates["PortfolioScore"] = (
        ai_scores * 100.0
        + phoenix_scores
        - market_risk_scores
        - _safe_float(market_context.get("market_risk_score"), 0.0)
    )

    normalized = normalize_candidate_frame(
        buy_candidates,
        apply_portfolio_filter=False,
    )
    if normalized.empty:
        raise ValueError("No BUY candidates remained after normalization")
    return normalized


def _lookup_ticker_row(frame: pd.DataFrame, ticker: str) -> Mapping[str, Any]:
    if frame.empty or "ticker" not in frame.columns:
        raise ValueError(f"Ticker lookup failed: {ticker}")
    normalized = frame["ticker"].astype(str).str.strip().str.upper()
    matched = frame.loc[normalized == ticker.strip().upper()]
    if matched.empty:
        raise ValueError(f"Ticker not found: {ticker}")
    return matched.iloc[0].to_dict()


def _build_selection_reason(
    *,
    trade_row: Mapping[str, Any],
    ai_row: Mapping[str, Any],
    decision_reason: str,
    market_context: Mapping[str, Any],
) -> str:
    trade_decision = _safe_text(
        _mapping_value(
            trade_row,
            "Trade判定",
            "TradeDecision",
            "decision",
            "Decision",
            default="BUY",
        ),
        "BUY",
    )
    ai_decision = _safe_text(
        _mapping_value(
            ai_row,
            "AI判断",
            "ai_decision",
            "decision",
            "Decision",
            default=_mapping_value(trade_row, "AI判断", "ai_decision", default="買い候補"),
        ),
        "買い候補",
    )
    ai_score = _safe_int(
        _mapping_value(
            ai_row,
            "AI判断点",
            "ai_score",
            "AI_score",
            "AI Score",
            default=_mapping_value(trade_row, "AI判断点", "ai_score", default=0),
        ),
        0,
    )
    phoenix_score = _safe_int(
        _mapping_value(
            trade_row,
            "PHOENIX_SCORE",
            "phoenix_score",
            "PhoenixScore",
            "PHOENIX SCORE",
            default=_mapping_value(ai_row, "PHOENIX_SCORE", "phoenix_score", default=0),
        ),
        0,
    )
    phoenix_reason = _safe_text(
        _mapping_value(
            ai_row,
            "PHOENIX理由",
            "phoenix_reason",
            "reason",
            "判定理由",
            default=_mapping_value(trade_row, "判定理由", "reason", default=""),
        ),
        "",
    )
    return (
        f"Trade判定={trade_decision} / "
        f"AI判断={ai_decision} / "
        f"AI判断点={ai_score} / "
        f"PHOENIX_SCORE={phoenix_score} / "
        f"MarketRegime={market_context['regime']} / "
        f"MarketRisk={market_context['market_risk_level']}({market_context['market_risk_score']:.0f}) / "
        f"PositionSizer={decision_reason} / "
        f"PHOENIX reason: {phoenix_reason}"
    )


def _pullback_state(quantity: int, reference_price: float, limit_price: float) -> str:
    if quantity <= 0:
        return "RECHECK_REQUIRED"
    if limit_price <= 0:
        return "RECHECK_REQUIRED"
    if reference_price > 0 and limit_price < reference_price:
        return "PULLBACK_WAIT"
    return "POST_TOUCH_RECHECK"


def _build_candidate(
    *,
    generated_at: datetime,
    expires_at: datetime,
    signal_date: str,
    trade_row: Mapping[str, Any],
    ai_row: Mapping[str, Any],
    sizing_decision: Any,
    market_context: Mapping[str, Any],
) -> dict[str, Any]:
    ticker = _safe_text(_mapping_value(trade_row, "ticker", "symbol", "Symbol", default=""))
    company_name = _safe_text(
        _mapping_value(
            trade_row,
            "驫俶氛",
            "name",
            "Name",
            "銘柄",
            default=ticker,
        ),
        ticker,
    )
    market = _safe_text(
        _mapping_value(trade_row, "market", "Market", default="TSE"),
        "TSE",
    )
    reference_price = round(
        _safe_float(
            _mapping_value(
                trade_row,
                "reference_price",
                "基準価格",
                "base_price",
                "current_price",
                "price",
                "Price",
                "終値",
                default=0.0,
            ),
            0.0,
        ),
        2,
    )
    limit_price = round(float(getattr(sizing_decision, "entry_price", 0.0)), 2)
    stop_loss_price = round(float(getattr(sizing_decision, "stop_price", 0.0)), 2)
    take_profit_price = round(
        _safe_float(
            _mapping_value(
                trade_row,
                "take_profit_price",
                "利確価格",
                "target_price",
                "target",
                "goal_price",
                default=0.0,
            ),
            0.0,
        ),
        2,
    )
    ai_score = _safe_int(
        _mapping_value(
            ai_row,
            "AI判断点",
            "ai_score",
            "AI_score",
            "AI Score",
            default=_mapping_value(trade_row, "AI判断点", "ai_score", default=0),
        ),
        0,
    )
    phoenix_score = _safe_int(
        _mapping_value(
            trade_row,
            "PHOENIX_SCORE",
            "phoenix_score",
            "PhoenixScore",
            "PHOENIX SCORE",
            default=_mapping_value(ai_row, "PHOENIX_SCORE", "phoenix_score", default=0),
        ),
        0,
    )
    portfolio_score = round(
        _safe_float(
            _mapping_value(trade_row, "PortfolioScore", "portfolio_score", default=0.0),
            0.0,
        ),
        4,
    )
    market_risk_score = round(
        _safe_float(
            _mapping_value(
                trade_row,
                "MarketRiskScore",
                "market_risk_score",
                "risk_score",
                "MarketRisk",
                "total_score",
                default=market_context["market_risk_score"],
            ),
            market_context["market_risk_score"],
        ),
        2,
    )
    market_risk_level = _safe_text(
        _mapping_value(
            trade_row,
            "MarketRiskLevel",
            "market_risk_level",
            "risk_level",
            "MarketRisk",
            default=market_context["market_risk_level"],
        ),
        market_context["market_risk_level"],
    ).upper()

    quantity = _safe_int(getattr(sizing_decision, "recommended_quantity", 0), 0)
    estimated_notional = round(limit_price * quantity, 2)
    estimated_max_loss = round(max(limit_price - stop_loss_price, 0.0) * quantity, 2)
    pullback_state = _pullback_state(quantity, reference_price, limit_price)
    watch_state = pullback_state
    recheck_required = watch_state != "PULLBACK_WAIT"
    sizing_status = _safe_text(getattr(sizing_decision, "status", ""), "SKIP")
    decision_reason = _safe_text(getattr(sizing_decision, "reason", ""), "")
    blocked_reasons = decision_reason if quantity <= 0 else ""

    selection_reason = _build_selection_reason(
        trade_row=trade_row,
        ai_row=ai_row,
        decision_reason=decision_reason,
        market_context=market_context,
    )

    payload = {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "signal_date": signal_date,
        "ticker": ticker,
        "company_name": company_name,
        "market": market,
        "side": SIDE,
        "order_type": ORDER_TYPE,
        "quantity": quantity,
        "lot_size": MANUAL_LOT_SIZE,
        "reference_price": reference_price,
        "limit_price": limit_price,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price,
        "estimated_notional": estimated_notional,
        "estimated_max_loss": estimated_max_loss,
        "ai_score": ai_score,
        "phoenix_score": phoenix_score,
        "portfolio_score": portfolio_score,
        "market_risk_score": market_risk_score,
        "market_risk_level": market_risk_level,
        "pullback_state": pullback_state,
        "watch_state": watch_state,
        "recheck_required": recheck_required,
        "sizing_status": sizing_status,
        "selection_reason": selection_reason,
        "risk_check_result": "MANUAL_ONLY",
        "blocked_reasons": blocked_reasons,
        "manual_approval_required": True,
        "rss_send_allowed": False,
        "orders_submitted": 0,
        "source_files": ";".join(SOURCE_FILES),
        "created_by": CREATED_BY,
        "status": STATUS,
    }
    payload["idempotency_key"] = _stable_hash(
        {
            key: value
            for key, value in payload.items()
            if key not in {"idempotency_key", "checksum"}
        }
    )
    payload["checksum"] = _stable_hash(
        {
            key: value
            for key, value in payload.items()
            if key != "checksum"
        }
    )
    return payload


def _read_root_files(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Path, dict[str, Any], dict[str, Any]]:
    trade_signals = _read_csv(resolve_path(root, "reports/trade_signals.csv"))
    ai_judgement = _read_csv(resolve_path(root, "reports/ai_judgement.csv"))
    daily_report_path = resolve_path(root, "reports/report_20260807.csv")
    daily_report = _read_csv(daily_report_path)
    _read_json(resolve_path(root, "reports/ai_judgement_manifest.json"))
    market_regime = _read_json(resolve_path(root, "reports/market_regime.json"))
    market_risk = _read_json(resolve_path(root, "data/market_risk_latest.json"))
    _read_json(resolve_path(root, "state/v7_paper_broker.json"))
    _read_json(resolve_path(root, "config/v7_position_sizer_config.json"))
    return trade_signals, ai_judgement, daily_report, daily_report_path, market_regime, market_risk


def build_manual_trade_ticket(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    actual_generated_at = generated_at or _now_jst()
    expires_at = actual_generated_at + timedelta(minutes=TTL_MINUTES)
    trade_signals, ai_judgement, daily_report, daily_report_path, market_regime, market_risk = _read_root_files(root)
    market_context = _load_market_context(market_regime, market_risk)
    signal_date = _signal_date(daily_report_path, daily_report)

    candidates = _prepare_candidate_frame(trade_signals, market_context)
    sizing_config = _load_position_sizing_config(root, market_context)
    broker = PaperBroker(
        initial_cash_yen=CAPITAL_BASIS_YEN,
    )
    decisions = size_candidates(
        broker,
        candidates,
        sizing_config,
    )
    decision_map = {decision.ticker: decision for decision in decisions}
    positive_orders = build_order_requests(
        decisions,
        run_id=actual_generated_at.strftime("%Y%m%d_%H%M%S"),
    )

    # Reuse the existing risk controller for an internal validation pass.
    risk_report = evaluate_orders(
        broker=broker,
        orders=positive_orders,
        config=_load_risk_config(market_context, candidate_count=len(candidates)),
        state=RiskState.new(max(broker.get_account_snapshot().equity_yen, 0.0)),
    )
    _ = risk_report

    ai_lookup = {
        str(row.get("ticker", "")).strip().upper(): row.to_dict()
        for _, row in ai_judgement.iterrows()
    }

    candidate_rows = []
    for _, row in candidates.iterrows():
        ticker = str(row.get("ticker", "")).strip().upper()
        decision = decision_map.get(ticker)
        if decision is None:
            raise ValueError(f"Candidate sizing decision missing: {ticker}")
        ai_row = ai_lookup.get(ticker, {})
        candidate_rows.append(
            _build_candidate(
                generated_at=actual_generated_at,
                expires_at=expires_at,
                signal_date=signal_date,
                trade_row=row.to_dict(),
                ai_row=ai_row,
                sizing_decision=decision,
                market_context=market_context,
            )
        )

    total_required_funds = round(
        sum(candidate["estimated_notional"] for candidate in candidate_rows),
        2,
    )
    total_estimated_max_loss = round(
        sum(candidate["estimated_max_loss"] for candidate in candidate_rows),
        2,
    )
    positive_quantity_count = sum(
        1 for candidate in candidate_rows if candidate["quantity"] > 0
    )
    zero_quantity_count = len(candidate_rows) - positive_quantity_count
    cash_available_yen = round(
        max(broker.get_account_snapshot().cash_yen, 0.0),
        2,
    )
    capital_basis_remaining_yen = round(
        CAPITAL_BASIS_YEN - total_required_funds,
        2,
    )
    cash_remaining_yen = round(
        cash_available_yen - total_required_funds,
        2,
    )

    blockers = ["MANUAL_ONLY"]

    return {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generated_at": actual_generated_at.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "signal_date": signal_date,
        "status": STATUS,
        "manual_approval_required": MANUAL_APPROVAL_REQUIRED,
        "rss_send_allowed": RSS_SEND_ALLOWED,
        "orders_submitted": ORDERS_SUBMITTED,
        "candidate_count": len(candidate_rows),
        "approved_count": 0,
        "blocked_count": 0,
        "review_count": len(candidate_rows),
        "blockers": blockers,
        "selected_ticker": None,
        "capital_basis_yen": CAPITAL_BASIS_YEN,
        "account_equity_yen": round(broker.get_account_snapshot().equity_yen, 2),
        "cash_available_yen": cash_available_yen,
        "source_files": list(SOURCE_FILES),
        "created_by": CREATED_BY,
        "market_context": market_context,
        "totals": {
            "required_funds_yen": total_required_funds,
            "estimated_max_loss_yen": total_estimated_max_loss,
            "positive_quantity_count": positive_quantity_count,
            "zero_quantity_count": zero_quantity_count,
            "cash_remaining_yen": cash_remaining_yen,
            "capital_basis_remaining_yen": capital_basis_remaining_yen,
            "lot_size": MANUAL_LOT_SIZE,
        },
        "candidates": candidate_rows,
    }


def _csv_frame(report: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    for candidate in report.get("candidates", []):
        row = dict(candidate)
        row["manual_approval_required"] = (
            "TRUE" if row.get("manual_approval_required") else "FALSE"
        )
        row["rss_send_allowed"] = "TRUE" if row.get("rss_send_allowed") else "FALSE"
        rows.append(row)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        column_order = [
            "generated_at",
            "expires_at",
            "signal_date",
            "ticker",
            "company_name",
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
            "ai_score",
            "phoenix_score",
            "portfolio_score",
            "market_risk_score",
            "market_risk_level",
            "pullback_state",
            "watch_state",
            "recheck_required",
            "sizing_status",
            "selection_reason",
            "risk_check_result",
            "blocked_reasons",
            "idempotency_key",
            "checksum",
            "manual_approval_required",
            "rss_send_allowed",
            "orders_submitted",
            "source_files",
            "created_by",
            "status",
        ]
        available_columns = [column for column in column_order if column in frame.columns]
        frame = frame[available_columns]
    return frame


def text_report(report: Mapping[str, Any]) -> str:
    candidates = report.get("candidates", [])
    market_context = report.get("market_context", {})
    totals = report.get("totals", {})
    source_files = report.get("source_files", [])
    if isinstance(source_files, list):
        source_files_text = ";".join(str(item) for item in source_files)
    else:
        source_files_text = str(source_files)
    lines = [
        "PHOENIX v7 STEP46 MANUAL TRADE TICKET",
        "=" * 92,
        f"Status               : {report.get('status', '')}",
        f"Signal date          : {report.get('signal_date', '')}",
        f"Manual approval      : {report.get('manual_approval_required', False)}",
        f"RSS send allowed     : {report.get('rss_send_allowed', False)}",
        f"Orders submitted     : {report.get('orders_submitted', 0)}",
        f"Candidate count      : {report.get('candidate_count', 0)}",
        f"Approved count       : {report.get('approved_count', 0)}",
        f"Blocked count        : {report.get('blocked_count', 0)}",
        f"Review count         : {report.get('review_count', 0)}",
        f"Manual only reason   : {', '.join(report.get('blockers', [])) or 'none'}",
        f"Capital basis        : {report.get('capital_basis_yen', 0):,.2f}",
        f"Account equity       : {report.get('account_equity_yen', 0):,.2f}",
        f"Cash available       : {report.get('cash_available_yen', 0):,.2f}",
        f"Market regime        : {market_context.get('regime', '')}",
        f"Market regime score  : {market_context.get('regime_score', 0):,.2f}",
        f"Market risk          : {market_context.get('market_risk_level', '')}",
        f"Market risk score    : {market_context.get('market_risk_score', 0):,.2f}",
        f"Required funds total : {totals.get('required_funds_yen', 0):,.2f}",
        f"Max loss total       : {totals.get('estimated_max_loss_yen', 0):,.2f}",
        f"Residual cash        : {totals.get('cash_remaining_yen', 0):,.2f}",
        f"Residual basis       : {totals.get('capital_basis_remaining_yen', 0):,.2f}",
        "-" * 92,
    ]
    for candidate in candidates:
        lines.extend(
            [
                f"Ticker               : {candidate.get('ticker', '')}",
                f"Company              : {candidate.get('company_name', '')}",
                f"Qty / lot            : {candidate.get('quantity', 0)} / {candidate.get('lot_size', 0)}",
                f"Reference / limit    : {candidate.get('reference_price', 0):,.2f} / {candidate.get('limit_price', 0):,.2f}",
                f"Stop / target        : {candidate.get('stop_loss_price', 0):,.2f} / {candidate.get('take_profit_price', 0):,.2f}",
                f"Pullback state       : {candidate.get('pullback_state', '')}",
                f"Watch state          : {candidate.get('watch_state', '')}",
                f"Recheck required     : {candidate.get('recheck_required', False)}",
                f"Blocked reasons      : {candidate.get('blocked_reasons', '') or 'none'}",
                f"Sizing status        : {candidate.get('sizing_status', '')}",
                f"Required funds       : {candidate.get('estimated_notional', 0):,.2f}",
                f"Max loss             : {candidate.get('estimated_max_loss', 0):,.2f}",
                f"Ticket status        : {candidate.get('status', '')}",
                f"Risk check           : {candidate.get('risk_check_result', '')}",
                f"Selection reason     : {candidate.get('selection_reason', '')}",
                "-" * 92,
            ]
        )
    lines.extend(
        [
            f"Source files         : {source_files_text}",
            f"Created by           : {report.get('created_by', '')}",
            "=" * 92,
            "",
        ]
    )
    return "\n".join(lines)


def save_manual_trade_ticket_outputs(root: Path, report: Mapping[str, Any]) -> None:
    json_path = resolve_path(root, REPORT_JSON_FILE)
    csv_path = resolve_path(root, REPORT_CSV_FILE)
    text_path = resolve_path(root, REPORT_TEXT_FILE)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)

    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _csv_frame(report).to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
    )
    atomic_write(text_path, text_report(report))


def run_manual_trade_ticket(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    report = build_manual_trade_ticket(root, generated_at=generated_at)
    save_manual_trade_ticket_outputs(root, report)
    return report
