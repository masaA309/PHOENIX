from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from phoenix_core.performance_tracker import atomic_write, load_history, resolve_path
from phoenix_core.portfolio_guard import as_float, load_state, position_items


def broker_snapshot(state: Mapping[str, Any], observed_at: datetime) -> dict[str, Any]:
    positions: dict[str, float] = {}
    for symbol, position in position_items(state):
        quantity = None
        for key in ("quantity", "qty", "shares", "保有株数"):
            quantity = as_float(position.get(key))
            if quantity is not None:
                break
        if symbol and quantity is not None and quantity > 0:
            positions[symbol] = quantity
    cash = None
    for key in ("cash", "available_cash", "buying_power", "現金"):
        cash = as_float(state.get(key))
        if cash is not None:
            break
    return {
        "schema_version": 1,
        "observed_at": observed_at.isoformat(timespec="seconds"),
        "cash": cash,
        "positions": dict(sorted(positions.items())),
    }


def load_snapshot(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, f"Previous snapshot is invalid: {type(error).__name__}: {error}"
    if not isinstance(value, dict):
        return {}, "Previous snapshot root is not an object"
    return value, None


def lifecycle_events(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    old_positions = previous.get("positions", {}) if isinstance(previous.get("positions", {}), dict) else {}
    new_positions = current.get("positions", {}) if isinstance(current.get("positions", {}), dict) else {}
    observed_at = str(current.get("observed_at", ""))
    events: list[dict[str, Any]] = []
    for symbol in sorted(set(old_positions) | set(new_positions)):
        before = float(old_positions.get(symbol, 0) or 0)
        after = float(new_positions.get(symbol, 0) or 0)
        delta = after - before
        if abs(delta) < 1e-9:
            continue
        side = "BUY" if delta > 0 else "SELL"
        raw_id = f"{observed_at}|{symbol}|{before}|{after}"
        events.append({
            "schema_version": 1,
            "event_id": hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:24],
            "observed_at": observed_at,
            "symbol": symbol,
            "side": side,
            "quantity": abs(delta),
            "quantity_before": before,
            "quantity_after": after,
            "source": "broker_position_delta",
        })
    return events


def merge_events(existing: list[dict[str, Any]], new_events: list[dict[str, Any]], retention_events: int) -> list[dict[str, Any]]:
    known = {str(item.get("event_id", "")) for item in existing}
    merged = list(existing)
    for event in new_events:
        if event["event_id"] not in known:
            merged.append(event)
            known.add(event["event_id"])
    return merged[-max(1, retention_events):]


def build_summary(
    events: list[Mapping[str, Any]],
    new_events: list[Mapping[str, Any]],
    baseline_created: bool,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    buy_count = sum(item.get("side") == "BUY" for item in events)
    sell_count = sum(item.get("side") == "SELL" for item in events)
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step15",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "WARNING" if warnings else "READY",
        "baseline_created": baseline_created,
        "new_event_count": len(new_events),
        "total_event_count": len(events),
        "buy_event_count": buy_count,
        "sell_event_count": sell_count,
        "audited_fill_count": buy_count + sell_count,
        "new_events": list(new_events),
        "warnings": list(warnings or []),
    }


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP15 ORDER LIFECYCLE AUDIT", "=" * 86,
        f"Status              : {report.get('status', '')}",
        f"Baseline created    : {report.get('baseline_created', False)}",
        f"New events          : {report.get('new_event_count', 0)}",
        f"Total events        : {report.get('total_event_count', 0)}",
        f"BUY / SELL          : {report.get('buy_event_count', 0)} / {report.get('sell_event_count', 0)}",
        f"Audited fills       : {report.get('audited_fill_count', 0)}", "-" * 86,
    ]
    events = report.get("new_events", [])
    lines.extend([
        f"{item.get('observed_at', '')} {item.get('side', ''):<4} {item.get('symbol', ''):<12} qty={item.get('quantity')} ({item.get('quantity_before')} -> {item.get('quantity_after')})"
        for item in events
    ] or ["No new position-change events"])
    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["-" * 86, "Warnings:"] + [f"  - {value}" for value in warnings])
    return "\n".join(lines + ["=" * 86, ""])


def run_order_lifecycle(root: Path, config: Mapping[str, Any], observed_at: datetime | None = None) -> dict[str, Any]:
    observed_at = observed_at or datetime.now()
    settings = config.get("order_lifecycle", {})
    broker_path = resolve_path(root, str(settings.get("broker_state", "state/v7_paper_broker.json")))
    snapshot_path = resolve_path(root, str(settings.get("snapshot_state", "state/v7_order_lifecycle_snapshot.json")))
    journal_path = resolve_path(root, str(settings.get("event_journal", "state/v7_order_lifecycle_events.jsonl")))
    report_json = resolve_path(root, str(settings.get("report_json", "reports/v7_order_lifecycle.json")))
    report_text = resolve_path(root, str(settings.get("report_text", "reports/v7_order_lifecycle.txt")))
    state, warnings = load_state(broker_path)
    current = broker_snapshot(state, observed_at)
    previous, snapshot_error = load_snapshot(snapshot_path)
    if snapshot_error:
        warnings.append(snapshot_error)
    baseline_created = not bool(previous)
    new_events = [] if baseline_created else lifecycle_events(previous, current)
    try:
        existing = load_history(journal_path)
    except ValueError as error:
        existing = []
        warnings.append(str(error))
    events = merge_events(existing, new_events, int(settings.get("retention_events", 2000)))
    atomic_write(snapshot_path, json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    atomic_write(journal_path, "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in events))
    report = build_summary(events, new_events, baseline_created, warnings)
    atomic_write(report_json, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(report_text, text_report(report))
    report["report_json"] = str(report_json)
    report["report_text"] = str(report_text)
    return report


def print_lifecycle_summary(report: Mapping[str, Any]) -> None:
    print("=" * 80)
    print("PHOENIX v7 STEP15 ORDER LIFECYCLE AUDIT")
    print("=" * 80)
    print(f"Status        : {report.get('status', '')}")
    print(f"Baseline      : {report.get('baseline_created', False)}")
    print(f"New events   : {report.get('new_event_count', 0)}")
    print(f"Audited fills : {report.get('audited_fill_count', 0)}")
    print(f"Report        : {report.get('report_text', '')}")
    print("=" * 80)
