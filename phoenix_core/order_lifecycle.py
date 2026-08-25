from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from phoenix_core.broker import PaperBroker
from phoenix_core.models import OrderRequest, OrderSide, OrderType
from phoenix_core.performance_tracker import atomic_write, load_history, resolve_path
from phoenix_core.portfolio_guard import as_float, load_state, position_items


MANUAL_TRADE_TICKET_REPORT = "reports/v7_manual_trade_ticket.json"
MANUAL_FILL_INBOX = "state/v7_manual_fill_inbox.csv"
MANUAL_FILL_INGEST_REPORT_JSON = "reports/v7_manual_fill_ingest.json"
MANUAL_FILL_INGEST_REPORT_TEXT = "reports/v7_manual_fill_ingest.txt"


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
    for key in ("cash_yen", "cash", "available_cash", "buying_power", "現金"):
        cash = as_float(state.get(key))
        if cash is not None:
            break
    fill_event_audit_available = "fill_events" in state
    fill_events: list[dict[str, Any]] = []
    raw_fill_events = state.get("fill_events", [])
    if raw_fill_events is not None:
        if not isinstance(raw_fill_events, list):
            raise ValueError("Broker fill_events is not a list")
        required = (
            "event_id", "broker_order_id", "client_order_id", "ticker",
            "side", "filled_quantity", "created_at", "event_sha256",
        )
        for index, event in enumerate(raw_fill_events):
            if not isinstance(event, Mapping):
                raise ValueError(f"Broker fill_events[{index}] is not an object")
            if any(name not in event for name in required):
                raise ValueError(f"Broker fill_events[{index}] lacks crosswalk fields")
            fill_events.append({name: event[name] for name in required})
    return {
        "schema_version": 1,
        "observed_at": observed_at.isoformat(timespec="seconds"),
        "cash": cash,
        "positions": dict(sorted(positions.items())),
        "fill_event_audit_available": fill_event_audit_available,
        "fill_events": fill_events,
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


def _load_manual_trade_ticket(root: Path) -> dict[str, dict[str, Any]]:
    report_path = resolve_path(root, MANUAL_TRADE_TICKET_REPORT)
    if not report_path.is_file():
        raise ValueError(f"manual trade ticket is missing: {report_path}")
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manual trade ticket report is invalid")
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("manual trade ticket candidates is invalid")
    lookup: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"manual trade ticket candidate[{index}] is invalid")
        client_order_id = str(candidate.get("client_order_id", "")).strip()
        if not client_order_id:
            raise ValueError(f"manual trade ticket candidate[{index}] lacks client_order_id")
        lookup[client_order_id] = dict(candidate)
    return lookup


def _load_manual_fill_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows = []
        for index, row in enumerate(reader):
            if row is None:
                raise ValueError(f"manual fill inbox row[{index}] is invalid")
            rows.append({str(key): str(value).strip() for key, value in row.items() if key is not None})
    return rows


def _manual_fill_text(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP15 MANUAL FILL INGEST",
        "=" * 86,
        f"Status              : {report.get('status', '')}",
        f"Ingested count      : {report.get('ingested_count', 0)}",
        f"Duplicate count     : {report.get('duplicate_count', 0)}",
        f"Rejected count      : {report.get('rejected_count', 0)}",
        f"Applied count       : {report.get('applied_count', 0)}",
        f"Inbox path          : {report.get('inbox_path', '')}",
        f"Broker state path   : {report.get('broker_state_path', '')}",
        "-" * 86,
    ]
    for item in report.get("fills", []):
        lines.extend([
            f"{item.get('filled_at', '')} {item.get('client_order_id', ''):<24} {item.get('ticker', ''):<12} "
            f"{item.get('side', ''):<4} qty={item.get('actual_fill_quantity')} price={item.get('actual_fill_price')}",
        ])
    return "\n".join(lines + ["=" * 86, ""])


def ingest_manual_fills(
    root: Path,
    config: Mapping[str, Any],
    observed_at: datetime | None = None,
) -> dict[str, Any] | None:
    settings = config.get("order_lifecycle", {})
    broker_path = resolve_path(root, str(settings.get("broker_state", "state/v7_paper_broker.json")))
    inbox_path = resolve_path(root, MANUAL_FILL_INBOX)
    if not inbox_path.is_file():
        return None

    rows = _load_manual_fill_rows(inbox_path)
    if not rows:
        return None

    state, warnings = load_state(broker_path)
    if warnings:
        raise ValueError("; ".join(warnings))
    broker = PaperBroker(
        initial_cash_yen=float(state.get("cash_yen", 0.0) or 0.0),
        state_file=broker_path,
    )
    ticket_lookup = _load_manual_trade_ticket(root)
    duplicate_count = 0
    rejected_count = 0
    applied_rows: list[dict[str, Any]] = []
    processed_ids = set(str(item) for item in state.get("processed_client_order_ids", []))

    for index, row in enumerate(rows):
        client_order_id = str(row.get("client_order_id", "")).strip()
        if not client_order_id:
            raise ValueError(f"manual fill inbox row[{index}] lacks client_order_id")
        if client_order_id in processed_ids:
            duplicate_count += 1
            continue
        ticket_row = ticket_lookup.get(client_order_id)
        if ticket_row is None:
            raise ValueError(f"manual fill inbox row[{index}] has unknown client_order_id: {client_order_id}")
        ticker = str(ticket_row.get("ticker", "")).strip().upper()
        side = str(ticket_row.get("side", "BUY")).strip().upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"manual fill inbox row[{index}] has invalid side: {side}")
        try:
            actual_fill_price = round(float(row.get("actual_fill_price", "")), 2)
            actual_fill_quantity = int(float(row.get("actual_fill_quantity", "")))
        except ValueError as error:
            raise ValueError(f"manual fill inbox row[{index}] has invalid fill values") from error
        if actual_fill_price <= 0 or actual_fill_quantity <= 0:
            raise ValueError(f"manual fill inbox row[{index}] has non-positive fill values")
        filled_at = str(row.get("filled_at", "")).strip()
        if not filled_at:
            raise ValueError(f"manual fill inbox row[{index}] lacks filled_at")

        order = OrderRequest(
            ticker=ticker,
            side=OrderSide(side),
            quantity=actual_fill_quantity,
            order_type=OrderType.LIMIT,
            limit_price=actual_fill_price,
            client_order_id=client_order_id,
            strategy_name="PHOENIX_MANUAL_FILL",
            metadata={
                "source": "manual_fill_inbox",
                "filled_at": filled_at,
            },
        )
        result = broker.submit_order(order)
        status_text = str(getattr(result, "status", "")).upper()
        if "FILLED" not in status_text:
            raise ValueError(f"manual fill submit failed for {client_order_id}")
        broker_order_id = str(
            getattr(
                result,
                "broker_order_id",
                getattr(result, "order_id", f"MANUAL|{client_order_id}"),
            )
        ).strip() or f"MANUAL|{client_order_id}"
        post_state = json.loads(broker_path.read_text(encoding="utf-8"))
        if not isinstance(post_state, dict):
            raise ValueError("manual fill broker state is invalid")
        fill_events = post_state.get("fill_events", [])
        if fill_events is None:
            fill_events = []
        if not isinstance(fill_events, list):
            raise ValueError("manual fill broker fill_events is invalid")
        fill_event = {
            "event_id": f"FILL|{broker_order_id}",
            "broker_order_id": broker_order_id,
            "client_order_id": client_order_id,
            "ticker": ticker,
            "side": side,
            "filled_quantity": actual_fill_quantity,
            "created_at": filled_at,
        }
        digest_source = json.dumps(
            fill_event,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        fill_event["event_sha256"] = hashlib.sha256(digest_source).hexdigest()
        if not any(
            isinstance(existing, Mapping)
            and str(existing.get("event_id", "")) == fill_event["event_id"]
            for existing in fill_events
        ):
            fill_events.append(fill_event)
        post_state["fill_events"] = fill_events
        atomic_write(broker_path, json.dumps(post_state, ensure_ascii=False, indent=2) + "\n")
        applied_rows.append(
            {
                "client_order_id": client_order_id,
                "ticker": ticker,
                "side": side,
                "actual_fill_price": actual_fill_price,
                "actual_fill_quantity": actual_fill_quantity,
                "filled_at": filled_at,
                "broker_status": str(getattr(result, "status", "")),
            }
        )
        processed_ids.add(client_order_id)

    if not applied_rows and duplicate_count == len(rows):
        inbox_path.unlink(missing_ok=True)
        return {
            "schema_version": 1,
            "version": "PHOENIX v7 Step15 Manual Fill Ingest",
            "generated_at": (observed_at or datetime.now()).isoformat(timespec="seconds"),
            "status": "READY",
            "ingested_count": 0,
            "duplicate_count": duplicate_count,
            "rejected_count": rejected_count,
            "applied_count": 0,
            "inbox_path": str(inbox_path),
            "broker_state_path": str(broker_path),
            "fills": [],
        }

    report = {
        "schema_version": 1,
        "version": "PHOENIX v7 Step15 Manual Fill Ingest",
        "generated_at": (observed_at or datetime.now()).isoformat(timespec="seconds"),
        "status": "READY",
        "ingested_count": len(applied_rows),
        "duplicate_count": duplicate_count,
        "rejected_count": rejected_count,
        "applied_count": len(applied_rows),
        "inbox_path": str(inbox_path),
        "broker_state_path": str(broker_path),
        "fills": applied_rows,
    }
    inbox_path.unlink(missing_ok=True)
    json_path = resolve_path(root, MANUAL_FILL_INGEST_REPORT_JSON)
    text_path = resolve_path(root, MANUAL_FILL_INGEST_REPORT_TEXT)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(text_path, _manual_fill_text(report))
    return report


def lifecycle_events(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (
        previous.get("fill_event_audit_available") is True
        and current.get("fill_event_audit_available") is True
        and isinstance(previous.get("fill_events"), list)
        and isinstance(current.get("fill_events"), list)
    ):
        previous_ids = {
            str(item.get("event_id", ""))
            for item in previous.get("fill_events", [])
            if isinstance(item, Mapping)
        }
        events: list[dict[str, Any]] = []
        for fill in current.get("fill_events", []):
            if not isinstance(fill, Mapping) or str(fill.get("event_id", "")) in previous_ids:
                continue
            raw_id = f"LIFECYCLE|{fill.get('event_id')}|{fill.get('event_sha256')}"
            events.append({
                "schema_version": 2,
                "event_id": hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:24],
                "observed_at": str(current.get("observed_at", "")),
                "symbol": str(fill.get("ticker", "")),
                "side": str(fill.get("side", "")),
                "quantity": fill.get("filled_quantity"),
                "source": "broker_fill_event_crosswalk",
                "economics_event_id": str(fill.get("event_id", "")),
                "broker_order_id": str(fill.get("broker_order_id", "")),
                "client_order_id": str(fill.get("client_order_id", "")),
                "fill_created_at": str(fill.get("created_at", "")),
                "broker_fill_event_sha256": str(fill.get("event_sha256", "")),
            })
        return events

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
        "audited_fill_ids": [
            str(item.get("event_id", ""))
            for item in events
            if str(item.get("event_id", ""))
        ],
        "audited_fill_crosswalk": [
            {
                "lifecycle_fill_id": str(item.get("event_id", "")),
                "economics_fill_id": str(item.get("economics_event_id", "")),
                "broker_order_id": str(item.get("broker_order_id", "")),
                "client_order_id": str(item.get("client_order_id", "")),
                "ticker": str(item.get("symbol", "")),
                "side": str(item.get("side", "")),
                "quantity": item.get("quantity"),
                "created_at": str(item.get("fill_created_at", "")),
                "broker_fill_event_sha256": str(item.get("broker_fill_event_sha256", "")),
            }
            for item in events
            if item.get("source") == "broker_fill_event_crosswalk"
        ],
        "new_events": list(new_events),
        "warnings": list(warnings or []),
    }


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP15 ORDER LIFECYCLE AUDIT", "=" * 86,
        f"Status              : {report.get('status', '')}",
        f"State persisted     : {report.get('state_persisted', False)}",
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


def run_order_lifecycle(
    root: Path,
    config: Mapping[str, Any],
    observed_at: datetime | None = None,
    persist_state: bool = True,
) -> dict[str, Any]:
    observed_at = observed_at or datetime.now()
    settings = config.get("order_lifecycle", {})
    broker_path = resolve_path(root, str(settings.get("broker_state", "state/v7_paper_broker.json")))
    snapshot_path = resolve_path(root, str(settings.get("snapshot_state", "state/v7_order_lifecycle_snapshot.json")))
    journal_path = resolve_path(root, str(settings.get("event_journal", "state/v7_order_lifecycle_events.jsonl")))
    report_json = resolve_path(root, str(settings.get("report_json", "reports/v7_order_lifecycle.json")))
    report_text = resolve_path(root, str(settings.get("report_text", "reports/v7_order_lifecycle.txt")))
    ingest_manual_fills(root, config, observed_at=observed_at)
    state, warnings = load_state(broker_path)
    try:
        raw_state = json.loads(broker_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raw_state = state
    if isinstance(raw_state, dict):
        state = raw_state
    current = broker_snapshot(state, observed_at)
    previous, snapshot_error = load_snapshot(snapshot_path)
    if snapshot_error:
        warnings.append(snapshot_error)
    baseline_created = not bool(previous)
    new_events = [] if baseline_created else lifecycle_events(previous, current)
    history_valid = True
    try:
        existing = load_history(journal_path)
    except ValueError as error:
        existing = []
        warnings.append(str(error))
        history_valid = False
    events = merge_events(existing, new_events, int(settings.get("retention_events", 2000)))
    state_valid = not warnings and history_valid
    state_persisted = bool(persist_state and state_valid)
    if state_persisted:
        atomic_write(snapshot_path, json.dumps(current, ensure_ascii=False, indent=2) + "\n")
        atomic_write(journal_path, "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in events))
    report = build_summary(events, new_events, baseline_created, warnings)
    report["state_persisted"] = state_persisted
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
    print(f"State saved   : {report.get('state_persisted', False)}")
    print(f"Baseline      : {report.get('baseline_created', False)}")
    print(f"New events   : {report.get('new_event_count', 0)}")
    print(f"Audited fills : {report.get('audited_fill_count', 0)}")
    print(f"Report        : {report.get('report_text', '')}")
    print("=" * 80)
