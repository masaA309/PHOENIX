from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from phoenix_core.performance_tracker import atomic_write, resolve_path
from phoenix_core.portfolio_guard import as_float, load_state, position_items


def file_health(path: Path, now: datetime, max_age_hours: float) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "status": "FAILED", "age_hours": None, "message": "File not found"}
    stat = path.stat()
    modified = datetime.fromtimestamp(stat.st_mtime)
    age_hours = (now - modified).total_seconds() / 3600
    if stat.st_size <= 0:
        status, message = "FAILED", "File is empty"
    elif age_hours < -0.1:
        status, message = "FAILED", "File timestamp is in the future"
    elif age_hours > max_age_hours:
        status, message = "WARNING", f"File is older than {max_age_hours:g} hours"
    else:
        status, message = "READY", "File is recent"
    return {
        "path": str(path), "exists": True, "status": status,
        "size_bytes": stat.st_size, "modified_at": modified.isoformat(timespec="seconds"),
        "age_hours": round(age_hours, 3), "message": message,
    }


def position_prices(state: Mapping[str, Any]) -> tuple[dict[str, float], list[str]]:
    prices: dict[str, float] = {}
    warnings: list[str] = []
    for symbol, position in position_items(state):
        price = None
        for key in ("market_price", "current_price", "last_price", "price", "現在価格"):
            price = as_float(position.get(key))
            if price is not None:
                break
        if price is None or price <= 0:
            warnings.append(f"Missing current price: {symbol or '(unknown symbol)'}")
        else:
            prices[symbol] = price
    return prices, warnings


def price_fingerprint(prices: Mapping[str, float]) -> str:
    payload = json.dumps(dict(sorted(prices.items())), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_guard_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def next_guard_state(previous: Mapping[str, Any], fingerprint: str, observed_at: datetime) -> dict[str, Any]:
    today = observed_at.date().isoformat()
    previous_date = str(previous.get("last_observed_date", ""))
    previous_fingerprint = str(previous.get("fingerprint", ""))
    unchanged_days = int(previous.get("unchanged_days", 0) or 0)
    if previous_date == today:
        pass
    elif fingerprint and fingerprint == previous_fingerprint:
        unchanged_days += 1
    else:
        unchanged_days = 0
    return {
        "schema_version": 1,
        "last_observed_at": observed_at.isoformat(timespec="seconds"),
        "last_observed_date": today,
        "fingerprint": fingerprint,
        "unchanged_days": unchanged_days,
    }


def build_report(
    files: Mapping[str, Mapping[str, Any]],
    prices: Mapping[str, float],
    price_warnings: list[str],
    unchanged_days: int,
    unchanged_warning_days: int,
    generated_at: datetime,
) -> dict[str, Any]:
    alerts: list[dict[str, str]] = []
    for name, item in files.items():
        if item.get("status") in {"FAILED", "WARNING"}:
            alerts.append({"level": str(item["status"]), "code": f"{name.upper()}_{item['status']}", "message": str(item.get("message", ""))})
    for message in price_warnings:
        alerts.append({"level": "FAILED", "code": "POSITION_PRICE_MISSING", "message": message})
    if prices and unchanged_days >= unchanged_warning_days:
        alerts.append({"level": "WARNING", "code": "PRICES_UNCHANGED", "message": f"Position prices have not changed across {unchanged_days} observed days"})
    levels = {item["level"] for item in alerts}
    status = "FAILED" if "FAILED" in levels else "WARNING" if "WARNING" in levels else "READY"
    return {
        "schema_version": 1, "version": "PHOENIX v7 Step13",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "status": status, "advisory_only": True, "orders_submitted": 0,
        "files": dict(files), "position_price_count": len(prices),
        "position_prices": dict(sorted(prices.items())),
        "unchanged_days": unchanged_days,
        "unchanged_warning_days": unchanged_warning_days,
        "alerts": alerts,
    }


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP13 MARKET DATA GUARD", "=" * 82,
        f"Status              : {report.get('status', '')}",
        f"Advisory only       : {report.get('advisory_only', True)}",
        f"Position prices     : {report.get('position_price_count', 0)}",
        f"Unchanged days      : {report.get('unchanged_days', 0)}", "-" * 82,
    ]
    for name, item in report.get("files", {}).items():
        lines.append(f"{name:<18} {item.get('status', ''):<8} age={item.get('age_hours')}h  {item.get('message', '')}")
    lines.append("-" * 82)
    alerts = report.get("alerts", [])
    lines.extend([f"{item.get('level', ''):<8} {item.get('code', ''):<28} {item.get('message', '')}" for item in alerts] or ["No market-data alerts"])
    return "\n".join(lines + ["=" * 82, ""])


def run_market_data_guard(root: Path, config: Mapping[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now()
    settings = config.get("market_data_guard", {})
    signals = resolve_path(root, str(settings.get("signals_file", "reports/trade_signals.csv")))
    broker = resolve_path(root, str(settings.get("broker_state", "state/v7_paper_broker.json")))
    state_path = resolve_path(root, str(settings.get("guard_state", "state/v7_market_data_guard.json")))
    report_json = resolve_path(root, str(settings.get("report_json", "reports/v7_market_data_guard.json")))
    report_text = resolve_path(root, str(settings.get("report_text", "reports/v7_market_data_guard.txt")))
    max_age = max(1.0, float(settings.get("max_age_hours", 96)))
    file_results = {"signals": file_health(signals, now, max_age), "broker_state": file_health(broker, now, max_age)}
    broker_state, state_warnings = load_state(broker)
    prices, price_warnings = position_prices(broker_state)
    price_warnings = state_warnings + price_warnings
    fingerprint = price_fingerprint(prices) if prices else ""
    previous = load_guard_state(state_path)
    current = next_guard_state(previous, fingerprint, now)
    atomic_write(state_path, json.dumps(current, ensure_ascii=False, indent=2) + "\n")
    threshold = max(1, int(settings.get("unchanged_warning_days", 2)))
    report = build_report(file_results, prices, price_warnings, int(current["unchanged_days"]), threshold, now)
    atomic_write(report_json, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(report_text, text_report(report))
    report["report_json"] = str(report_json)
    report["report_text"] = str(report_text)
    return report


def print_market_data_summary(report: Mapping[str, Any]) -> None:
    print("=" * 80)
    print("PHOENIX v7 STEP13 MARKET DATA GUARD")
    print("=" * 80)
    print(f"Status          : {report.get('status', '')}")
    print(f"Position prices : {report.get('position_price_count', 0)}")
    print(f"Unchanged days  : {report.get('unchanged_days', 0)}")
    print(f"Alerts          : {len(report.get('alerts', []))}")
    print(f"Report          : {report.get('report_text', '')}")
    print("=" * 80)
