from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from phoenix_core.performance_tracker import atomic_write, resolve_path


def read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, f"Required report not found: {path}"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, f"Could not read {path}: {type(error).__name__}: {error}"
    if not isinstance(value, dict):
        return {}, f"Report root is not a JSON object: {path}"
    return value, None


def check(name: str, passed: bool, actual: Any, required: Any, message: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "required": required, "message": message}


def build_readiness_report(
    performance: Mapping[str, Any],
    operations: Mapping[str, Any],
    market_data: Mapping[str, Any],
    portfolio: Mapping[str, Any],
    requirements: Mapping[str, Any],
    load_errors: list[str] | None = None,
) -> dict[str, Any]:
    run_count = int(performance.get("run_count", 0) or 0)
    distinct_days = int(performance.get("distinct_run_days", 0) or 0)
    success_rate = performance.get("success_rate")
    success_rate_value = float(success_rate) if success_rate is not None else 0.0
    failed_runs = int(performance.get("status_counts", {}).get("FAILED", 0) or 0)
    filled = int(performance.get("totals", {}).get("filled", 0) or 0)
    risk_halts = int(performance.get("risk_halt_count", 0) or 0)
    minimum_days = max(1, int(requirements.get("minimum_paper_days", 20)))
    minimum_success = float(requirements.get("minimum_success_rate", 0.95))
    minimum_filled = max(0, int(requirements.get("minimum_filled_orders", 3)))
    portfolio_reviews = int(portfolio.get("action_counts", {}).get("REVIEW", 0) or 0)
    checks = [
        check("paper_days", distinct_days >= minimum_days, distinct_days, minimum_days, "Enough distinct paper-trading days have been observed"),
        check("success_rate", success_rate_value >= minimum_success, success_rate_value, minimum_success, "Scheduler success rate meets the threshold"),
        check("failed_runs", failed_runs == 0, failed_runs, 0, "No failed runs exist in the evaluation window"),
        check("filled_orders", filled >= minimum_filled, filled, minimum_filled, "Paper fills are sufficient to exercise execution paths"),
        check("risk_halts", risk_halts == 0, risk_halts, 0, "No risk-controller halts exist in the window"),
        check("latest_operation", operations.get("status") == "SUCCESS", operations.get("status"), "SUCCESS", "Latest scheduled operation succeeded"),
        check("market_data", market_data.get("status") == "READY", market_data.get("status"), "READY", "Market data passed freshness checks"),
        check("portfolio_review", portfolio_reviews == 0, portfolio_reviews, 0, "No portfolio position requires manual data review"),
    ]
    errors = list(load_errors or [])
    ready = all(item["passed"] for item in checks) and not errors
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step14.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "READY" if ready else "NOT_READY",
        "paper_to_live_eligible": ready,
        "live_trading_enabled": False,
        "automatic_promotion": False,
        "passed_checks": sum(item["passed"] for item in checks),
        "total_checks": len(checks),
        "checks": checks,
        "blocking_reasons": errors + [item["message"] for item in checks if not item["passed"]],
        "load_errors": errors,
    }


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP14.1 PAPER-TO-LIVE READINESS GATE", "=" * 92,
        f"Status                 : {report.get('status', '')}",
        f"Eligible               : {report.get('paper_to_live_eligible', False)}",
        f"Live trading enabled   : {report.get('live_trading_enabled', False)}",
        f"Automatic promotion    : {report.get('automatic_promotion', False)}",
        f"Checks passed          : {report.get('passed_checks', 0)}/{report.get('total_checks', 0)}", "-" * 92,
    ]
    for item in report.get("checks", []):
        mark = "PASS" if item.get("passed") else "BLOCK"
        lines.append(f"{mark:<6} {item.get('name', ''):<22} actual={item.get('actual')} required={item.get('required')}")
    blockers = report.get("blocking_reasons", [])
    if blockers:
        lines.extend(["-" * 92, "Blocking reasons:"] + [f"  - {value}" for value in blockers])
    lines.extend(["-" * 92, "This gate never enables live trading automatically.", "=" * 92, ""])
    return "\n".join(lines)


def run_readiness_gate(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    settings = config.get("readiness_gate", {})
    sources = {
        "performance": str(settings.get("performance_report", "reports/v7_performance_summary.json")),
        "operations": str(settings.get("operations_report", "reports/v7_operations_report.json")),
        "market_data": str(settings.get("market_data_report", "reports/v7_market_data_guard.json")),
        "portfolio": str(settings.get("portfolio_report", "reports/v7_portfolio_guard.json")),
        "lifecycle": str(settings.get("lifecycle_report", "reports/v7_order_lifecycle.json")),
    }
    loaded: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, value in sources.items():
        loaded[name], error = read_json(resolve_path(root, value))
        if error:
            errors.append(error)
    performance = dict(loaded.get("performance", {}))
    totals = dict(performance.get("totals", {}))
    totals["filled"] = int(loaded.get("lifecycle", {}).get("audited_fill_count", 0) or 0)
    performance["totals"] = totals
    report = build_readiness_report(
        performance, loaded.get("operations", {}),
        loaded.get("market_data", {}), loaded.get("portfolio", {}), settings, errors,
    )
    json_path = resolve_path(root, str(settings.get("report_json", "reports/v7_readiness_gate.json")))
    text_path = resolve_path(root, str(settings.get("report_text", "reports/v7_readiness_gate.txt")))
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(text_path, text_report(report))
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    return report


def print_readiness_summary(report: Mapping[str, Any]) -> None:
    print("=" * 80)
    print("PHOENIX v7 STEP14.1 READINESS GATE")
    print("=" * 80)
    print(f"Status       : {report.get('status', '')}")
    print(f"Checks       : {report.get('passed_checks', 0)}/{report.get('total_checks', 0)}")
    print(f"Live enabled : {report.get('live_trading_enabled', False)}")
    print(f"Blockers     : {len(report.get('blocking_reasons', []))}")
    print(f"Report       : {report.get('report_text', '')}")
    print("=" * 80)
