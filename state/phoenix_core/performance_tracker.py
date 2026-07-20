from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping


def resolve_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
            temporary = Path(file.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def load_history(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid history JSON at line {line_number}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"History line {line_number} is not a JSON object")
        records.append(value)
    return records


def record_from_operations(report: Mapping[str, Any]) -> dict[str, Any]:
    pipeline = report.get("pipeline", {})
    alerts = report.get("alerts", [])
    generated_at = str(report.get("generated_at", ""))
    log_path = str(report.get("log", {}).get("path", ""))
    return {
        "schema_version": 1,
        "run_id": f"{generated_at}|{log_path}",
        "generated_at": generated_at,
        "status": str(report.get("status", "UNKNOWN")),
        "return_code": int(report.get("return_code", 0) or 0),
        "dry_run": bool(report.get("dry_run", False)),
        "candidate_count": int(pipeline.get("candidate_count", 0) or 0),
        "ready_count": int(pipeline.get("ready_count", 0) or 0),
        "approved_count": int(pipeline.get("approved_count", 0) or 0),
        "filled_count": int(pipeline.get("filled_count", 0) or 0),
        "risk_halted": bool(pipeline.get("halted", False)),
        "alert_codes": [str(item.get("code", "")) for item in alerts],
    }


def summarize(records: Iterable[Mapping[str, Any]], window_runs: int = 30) -> dict[str, Any]:
    items = list(records)[-max(1, window_runs):]
    total = len(items)
    status_counts = {name: sum(item.get("status") == name for item in items) for name in ("SUCCESS", "WARNING", "FAILED")}
    candidates = sum(int(item.get("candidate_count", 0) or 0) for item in items)
    ready = sum(int(item.get("ready_count", 0) or 0) for item in items)
    approved = sum(int(item.get("approved_count", 0) or 0) for item in items)
    filled = sum(int(item.get("filled_count", 0) or 0) for item in items)
    alert_counts: dict[str, int] = {}
    for item in items:
        for code in item.get("alert_codes", []):
            alert_counts[str(code)] = alert_counts.get(str(code), 0) + 1
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step10",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window_runs": max(1, window_runs),
        "run_count": total,
        "status_counts": status_counts,
        "success_rate": round(status_counts["SUCCESS"] / total, 4) if total else None,
        "totals": {"candidates": candidates, "ready": ready, "approved": approved, "filled": filled},
        "conversion_rates": {
            "candidate_to_ready": round(ready / candidates, 4) if candidates else None,
            "approved_to_filled": round(filled / approved, 4) if approved else None,
        },
        "risk_halt_count": sum(bool(item.get("risk_halted", False)) for item in items),
        "alert_counts": dict(sorted(alert_counts.items())),
        "latest_run": items[-1] if items else None,
    }


def text_summary(summary: Mapping[str, Any]) -> str:
    counts = summary.get("status_counts", {})
    totals = summary.get("totals", {})
    rates = summary.get("conversion_rates", {})
    success_rate = summary.get("success_rate")
    percentage = "N/A" if success_rate is None else f"{float(success_rate) * 100:.1f}%"
    lines = [
        "PHOENIX v7 STEP10 PERFORMANCE SUMMARY", "=" * 72,
        f"Runs                 : {summary.get('run_count', 0)} / {summary.get('window_runs', 0)}",
        f"Success rate         : {percentage}",
        f"SUCCESS/WARNING/FAIL : {counts.get('SUCCESS', 0)}/{counts.get('WARNING', 0)}/{counts.get('FAILED', 0)}",
        f"Candidates           : {totals.get('candidates', 0)}",
        f"Ready                : {totals.get('ready', 0)}",
        f"Approved             : {totals.get('approved', 0)}",
        f"Filled               : {totals.get('filled', 0)}",
        f"Candidate -> Ready   : {rates.get('candidate_to_ready')}",
        f"Approved -> Filled   : {rates.get('approved_to_filled')}",
        f"Risk halts           : {summary.get('risk_halt_count', 0)}", "-" * 72,
    ]
    alerts = summary.get("alert_counts", {})
    lines.extend([f"{code}: {count}" for code, count in alerts.items()] or ["No alerts in window"])
    return "\n".join(lines + ["=" * 72, ""])


def update_performance(root: Path, config: Mapping[str, Any], operations_report: Mapping[str, Any]) -> dict[str, Any]:
    settings = config.get("performance", {})
    history_path = resolve_path(root, str(settings.get("history_jsonl", "reports/v7_run_history.jsonl")))
    summary_json = resolve_path(root, str(settings.get("summary_json", "reports/v7_performance_summary.json")))
    summary_text = resolve_path(root, str(settings.get("summary_text", "reports/v7_performance_summary.txt")))
    retention = max(1, int(settings.get("retention_runs", 365)))
    window = max(1, int(settings.get("window_runs", 30)))
    records = load_history(history_path)
    record = record_from_operations(operations_report)
    if not records or records[-1].get("run_id") != record["run_id"]:
        records.append(record)
    records = records[-retention:]
    atomic_write(history_path, "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records))
    summary = summarize(records, window)
    atomic_write(summary_json, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    atomic_write(summary_text, text_summary(summary))
    summary["history_path"] = str(history_path)
    summary["summary_json"] = str(summary_json)
    summary["summary_text"] = str(summary_text)
    return summary


def print_performance_summary(summary: Mapping[str, Any]) -> None:
    totals = summary.get("totals", {})
    print("=" * 80)
    print("PHOENIX v7 STEP10 PERFORMANCE TRACKER")
    print("=" * 80)
    print(f"Runs         : {summary.get('run_count', 0)}")
    print(f"Success rate : {summary.get('success_rate')}")
    print(f"Candidates   : {totals.get('candidates', 0)}")
    print(f"Ready        : {totals.get('ready', 0)}")
    print(f"Approved     : {totals.get('approved', 0)}")
    print(f"Filled       : {totals.get('filled', 0)}")
    print(f"Report       : {summary.get('summary_text', '')}")
    print("=" * 80)
