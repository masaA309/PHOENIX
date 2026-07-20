from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from phoenix_core.performance_tracker import atomic_write, resolve_path


def as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "").replace("円", "").strip())
    except (TypeError, ValueError):
        return None


def first_number(data: Mapping[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        value = as_float(data.get(key))
        if value is not None:
            return value
    return None


def load_state(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.is_file():
        return {}, [f"Broker state not found: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, [f"Broker state could not be read: {type(error).__name__}: {error}"]
    if not isinstance(payload, dict):
        return {}, ["Broker state root is not a JSON object"]
    return payload, []


def position_items(state: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    raw = state.get("positions", {})
    items: list[tuple[str, dict[str, Any]]] = []
    if isinstance(raw, dict):
        for symbol, value in raw.items():
            if isinstance(value, dict):
                items.append((str(symbol), dict(value)))
            else:
                items.append((str(symbol), {"quantity": value}))
    elif isinstance(raw, list):
        for value in raw:
            if not isinstance(value, dict):
                continue
            symbol = str(value.get("symbol") or value.get("ticker") or value.get("code") or "")
            items.append((symbol, dict(value)))
    return items


def evaluate_position(
    symbol: str,
    position: Mapping[str, Any],
    stop_loss_pct: float,
    take_profit_pct: float,
) -> dict[str, Any]:
    quantity = first_number(position, ("quantity", "qty", "shares", "保有株数")) or 0.0
    entry = first_number(position, ("average_price", "avg_price", "entry_price", "cost_basis", "平均取得価格", "取得価格"))
    current = first_number(position, ("current_price", "market_price", "last_price", "price", "現在価格"))
    stored_stop = first_number(position, ("stop_price", "stop_loss", "stop", "損切価格"))
    stored_target = first_number(position, ("target_price", "take_profit", "profit_target", "利益確定価格"))
    warnings: list[str] = []
    if quantity <= 0:
        warnings.append("Quantity is missing or zero")
    if entry is None or entry <= 0:
        warnings.append("Entry price is missing")
    if current is None or current <= 0:
        warnings.append("Current price is missing")
    stop = stored_stop if stored_stop is not None else (entry * (1.0 - stop_loss_pct) if entry else None)
    target = stored_target if stored_target is not None else (entry * (1.0 + take_profit_pct) if entry else None)
    action = "REVIEW" if warnings else "HOLD"
    reason = "; ".join(warnings) if warnings else "Price is between stop and target"
    if not warnings and current is not None and stop is not None and current <= stop:
        action, reason = "EXIT", "Current price reached the stop level"
    elif not warnings and current is not None and target is not None and current >= target:
        action, reason = "TAKE_PROFIT", "Current price reached the profit target"
    market_value = quantity * current if current is not None else None
    unrealized = quantity * (current - entry) if current is not None and entry is not None else None
    return {
        "symbol": symbol,
        "quantity": quantity,
        "entry_price": entry,
        "current_price": current,
        "stop_price": round(stop, 4) if stop is not None else None,
        "target_price": round(target, 4) if target is not None else None,
        "stop_source": "stored" if stored_stop is not None else "advisory_default",
        "target_source": "stored" if stored_target is not None else "advisory_default",
        "market_value": round(market_value, 2) if market_value is not None else None,
        "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
        "action": action,
        "reason": reason,
        "warnings": warnings,
    }


def build_portfolio_report(
    state: Mapping[str, Any],
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.10,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    positions = [evaluate_position(symbol, value, stop_loss_pct, take_profit_pct) for symbol, value in position_items(state)]
    counts = {name: sum(item["action"] == name for item in positions) for name in ("HOLD", "EXIT", "TAKE_PROFIT", "REVIEW")}
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step12",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "ADVISORY",
        "orders_submitted": 0,
        "status": "REVIEW" if counts["EXIT"] or counts["TAKE_PROFIT"] or counts["REVIEW"] or warnings else "HEALTHY",
        "rules": {"default_stop_loss_pct": stop_loss_pct, "default_take_profit_pct": take_profit_pct},
        "position_count": len(positions),
        "action_counts": counts,
        "total_market_value": round(sum(item["market_value"] or 0 for item in positions), 2),
        "total_unrealized_pnl": round(sum(item["unrealized_pnl"] or 0 for item in positions), 2),
        "positions": positions,
        "warnings": list(warnings or []),
    }


def text_report(report: Mapping[str, Any]) -> str:
    counts = report.get("action_counts", {})
    lines = [
        "PHOENIX v7 STEP12 PORTFOLIO EXIT GUARD", "=" * 88,
        f"Mode             : {report.get('mode', '')} (no sell orders are submitted)",
        f"Status           : {report.get('status', '')}",
        f"Positions        : {report.get('position_count', 0)}",
        f"HOLD/EXIT/PROFIT : {counts.get('HOLD', 0)}/{counts.get('EXIT', 0)}/{counts.get('TAKE_PROFIT', 0)}",
        f"Needs review     : {counts.get('REVIEW', 0)}",
        f"Market value     : {report.get('total_market_value', 0):,.2f}",
        f"Unrealized P/L   : {report.get('total_unrealized_pnl', 0):,.2f}", "-" * 88,
    ]
    for item in report.get("positions", []):
        lines.append(
            f"{item.get('symbol', ''):<12} {item.get('action', ''):<12} "
            f"qty={item.get('quantity')} current={item.get('current_price')} "
            f"stop={item.get('stop_price')} target={item.get('target_price')}"
        )
        lines.append(f"  {item.get('reason', '')}")
    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["-" * 88, "Warnings:"] + [f"  - {value}" for value in warnings])
    return "\n".join(lines + ["=" * 88, ""])


def run_portfolio_guard(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    settings = config.get("portfolio_guard", {})
    state_path = resolve_path(root, str(settings.get("broker_state", "state/v7_paper_broker.json")))
    json_path = resolve_path(root, str(settings.get("report_json", "reports/v7_portfolio_guard.json")))
    text_path = resolve_path(root, str(settings.get("report_text", "reports/v7_portfolio_guard.txt")))
    state, warnings = load_state(state_path)
    report = build_portfolio_report(
        state,
        max(0.001, float(settings.get("default_stop_loss_pct", 0.05))),
        max(0.001, float(settings.get("default_take_profit_pct", 0.10))),
        warnings,
    )
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(text_path, text_report(report))
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    return report


def print_portfolio_summary(report: Mapping[str, Any]) -> None:
    print("=" * 80)
    print("PHOENIX v7 STEP12 PORTFOLIO EXIT GUARD")
    print("=" * 80)
    print(f"Mode       : {report.get('mode', '')}")
    print(f"Status     : {report.get('status', '')}")
    print(f"Positions  : {report.get('position_count', 0)}")
    print(f"Actions    : {report.get('action_counts', {})}")
    print(f"Report     : {report.get('report_text', '')}")
    print("=" * 80)
