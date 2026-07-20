from __future__ import annotations

import csv
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from phoenix_core.performance_tracker import atomic_write, resolve_path


REASON_KEYS = ("reason", "skip_reason", "reject_reason", "rejection_reason", "status_reason", "message", "理由")
STATUS_KEYS = ("status", "decision", "result", "sizing_status", "判定")
SYMBOL_KEYS = ("symbol", "ticker", "code", "銘柄コード")
READY_VALUES = {"ready", "approved", "pass", "passed", "ok", "true", "1"}


def normalized_row(row: Mapping[str, Any]) -> dict[str, str]:
    return {str(key).strip().lower(): str(value or "").strip() for key, value in row.items() if key is not None}


def first_value(row: Mapping[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        if row.get(key):
            return row[key]
    return ""


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def number(row: Mapping[str, str], *keys: str) -> float | None:
    for key in keys:
        raw = row.get(key, "").replace(",", "").replace("円", "").strip()
        if not raw:
            continue
        try:
            return float(raw)
        except ValueError:
            continue
    return None


def infer_reason(row: Mapping[str, str]) -> str:
    explicit = first_value(row, REASON_KEYS)
    if explicit:
        return explicit
    status = first_value(row, STATUS_KEYS).lower()
    if status in READY_VALUES:
        return "READY"
    if truthy(row.get("existing_position", "")) or truthy(row.get("already_held", "")):
        return "EXISTING_POSITION"
    quantity = number(row, "quantity", "qty", "shares", "order_quantity")
    if quantity is not None and quantity <= 0:
        return "ZERO_QUANTITY"
    price = number(row, "price", "last_price", "close", "entry_price")
    cash = number(row, "available_cash", "cash", "buying_power")
    lot = number(row, "lot_size", "unit", "trading_unit") or 100
    if price is not None and cash is not None and price * lot > cash:
        return "INSUFFICIENT_CASH_FOR_LOT"
    stop = number(row, "stop_price", "stop_loss", "stop")
    if price is not None and stop is not None and stop >= price:
        return "INVALID_STOP_DISTANCE"
    return status.upper() if status else "UNSPECIFIED"


def read_position_log(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.is_file():
        return [], [f"Position sizing log not found: {path}"]
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames:
                return [], ["Position sizing log has no header"]
            return [normalized_row(row) for row in reader], []
    except (OSError, UnicodeError, csv.Error) as error:
        return [], [f"Could not read position sizing log: {type(error).__name__}: {error}"]


def build_diagnostics(
    position_rows: list[Mapping[str, str]],
    operations_report: Mapping[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    pipeline = operations_report.get("pipeline", {})
    reason_counts: dict[str, int] = {}
    examples: list[dict[str, str]] = []
    for row in position_rows:
        reason = infer_reason(row)
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if reason != "READY" and len(examples) < 10:
            examples.append({"symbol": first_value(row, SYMBOL_KEYS), "reason": reason})
    candidates = int(pipeline.get("candidate_count", 0) or 0)
    ready = int(pipeline.get("ready_count", 0) or 0)
    if candidates > 0 and ready == 0:
        status = "REVIEW"
        headline = "Candidates were found, but none passed position sizing."
    elif ready > 0:
        status = "HEALTHY"
        headline = "At least one candidate passed position sizing."
    else:
        status = "NO_DATA"
        headline = "No candidates were available for sizing."
    recommendations: list[str] = []
    if candidates > 0 and ready == 0:
        recommendations.append("Review the most frequent exclusion reason before changing any risk limit.")
    if reason_counts.get("UNSPECIFIED", 0):
        recommendations.append("Add an explicit reason column to the position sizing log for complete attribution.")
    if not position_rows:
        recommendations.append("Confirm that the position sizing stage writes its CSV diagnostic log.")
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step11.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "headline": headline,
        "pipeline": {
            "candidates": candidates,
            "ready": ready,
            "approved": int(pipeline.get("approved_count", 0) or 0),
            "filled": int(pipeline.get("filled_count", 0) or 0),
        },
        "position_log_rows": len(position_rows),
        "reason_counts": dict(sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))),
        "examples": examples,
        "warnings": list(warnings or []),
        "recommendations": recommendations,
    }


def text_report(report: Mapping[str, Any]) -> str:
    pipeline = report.get("pipeline", {})
    lines = [
        "PHOENIX v7 STEP11.1 DECISION DIAGNOSTICS", "=" * 76,
        f"Status       : {report.get('status', '')}",
        f"Summary      : {report.get('headline', '')}",
        f"Candidates   : {pipeline.get('candidates', 0)}",
        f"Ready        : {pipeline.get('ready', 0)}",
        f"Approved     : {pipeline.get('approved', 0)}",
        f"Filled       : {pipeline.get('filled', 0)}",
        f"Log rows     : {report.get('position_log_rows', 0)}", "-" * 76,
        "Exclusion reasons:",
    ]
    reasons = report.get("reason_counts", {})
    lines.extend([f"  {reason}: {count}" for reason, count in reasons.items()] or ["  No row-level reasons available"])
    warnings = report.get("warnings", [])
    if warnings:
        lines.extend(["-" * 76, "Warnings:"] + [f"  - {item}" for item in warnings])
    recommendations = report.get("recommendations", [])
    if recommendations:
        lines.extend(["-" * 76, "Next checks:"] + [f"  - {item}" for item in recommendations])
    return "\n".join(lines + ["=" * 76, ""])


def run_decision_diagnostics(root: Path, config: Mapping[str, Any], operations_report: Mapping[str, Any]) -> dict[str, Any]:
    settings = config.get("diagnostics", {})
    log_path = resolve_path(root, str(settings.get("position_log", "reports/v7_direct_position_log.csv")))
    json_path = resolve_path(root, str(settings.get("report_json", "reports/v7_decision_diagnostics.json")))
    text_path = resolve_path(root, str(settings.get("report_text", "reports/v7_decision_diagnostics.txt")))
    rows, warnings = read_position_log(log_path)
    report = build_diagnostics(rows, operations_report, warnings)
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(text_path, text_report(report))
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    return report


def print_diagnostics_summary(report: Mapping[str, Any]) -> None:
    print("=" * 80)
    print("PHOENIX v7 STEP11.1 DECISION DIAGNOSTICS")
    print("=" * 80)
    print(f"Status  : {report.get('status', '')}")
    print(f"Summary : {report.get('headline', '')}")
    print(f"Reasons : {report.get('reason_counts', {})}")
    print(f"Report  : {report.get('report_text', '')}")
    print("=" * 80)
