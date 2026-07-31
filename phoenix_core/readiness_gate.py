from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from phoenix_core.performance_tracker import atomic_write, resolve_path
from phoenix_core.historical_replay import verify_historical_report
from phoenix_core.trading_economics import verify_economics_report
from phoenix_core.staged_pilot_gate import run_staged_pilot_gate


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
    lifecycle: Mapping[str, Any] | None = None,
    historical: Mapping[str, Any] | None = None,
    economics: Mapping[str, Any] | None = None,
    staged: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_evidence = performance.get("paper_evidence", {})
    evidence = raw_evidence if isinstance(raw_evidence, Mapping) else {}
    evidence_verified = (
        evidence.get("integrity_status") == "VERIFIED"
        and evidence.get("eligibility_rule") == "dry_run == false"
    )
    distinct_days = int(evidence.get("distinct_run_days", 0) or 0)
    success_rate = evidence.get("success_rate")
    success_rate_value = float(success_rate) if success_rate is not None else 0.0
    failed_runs = int(evidence.get("status_counts", {}).get("FAILED", 0) or 0)
    evidence_filled = int(evidence.get("totals", {}).get("filled", 0) or 0)
    filled = int(lifecycle.get("audited_fill_count", 0) or 0) if lifecycle is not None else evidence_filled
    risk_halts = int(evidence.get("risk_halt_count", 0) or 0)
    minimum_days = max(1, int(requirements.get("minimum_paper_days", 20)))
    minimum_success = float(requirements.get("minimum_success_rate", 0.95))
    minimum_filled = max(0, int(requirements.get("minimum_filled_orders", 3)))
    portfolio_reviews = int(portfolio.get("action_counts", {}).get("REVIEW", 0) or 0)
    checks = [
        check("paper_evidence", evidence_verified, evidence.get("integrity_status", "MISSING"), "VERIFIED", "Paper evidence is unverified or includes ineligible Dry Run evidence"),
        check("paper_days", distinct_days >= minimum_days, distinct_days, minimum_days, "Distinct paper-trading days are below the required minimum"),
        check("success_rate", success_rate_value >= minimum_success, success_rate_value, minimum_success, "Scheduler success rate is below the required threshold"),
        check("failed_runs", failed_runs == 0, failed_runs, 0, "Failed paper runs exist in the evaluation window"),
        check("filled_orders", filled >= minimum_filled, filled, minimum_filled, "Audited paper fills are below the required minimum"),
        check("risk_halts", risk_halts == 0, risk_halts, 0, "Risk-controller halts exist in the evaluation window"),
        check(
            "latest_paper_operation",
            operations.get("status") == "SUCCESS" and operations.get("dry_run") is False,
            {"status": operations.get("status"), "dry_run": operations.get("dry_run")},
            {"status": "SUCCESS", "dry_run": False},
            "Latest scheduled operation is not a successful non-Dry-Run paper execution",
        ),
        check("market_data", market_data.get("status") == "READY", market_data.get("status"), "READY", "Market data freshness checks are not READY"),
        check("portfolio_review", portfolio_reviews == 0, portfolio_reviews, 0, "One or more portfolio positions require manual data review"),
    ]
    if lifecycle is not None:
        lifecycle_persisted = lifecycle.get("state_persisted") is True
        expected_persisted = operations.get("dry_run") is False
        lifecycle_ready = (
            lifecycle.get("status") == "READY"
            and lifecycle_persisted is expected_persisted
        )
        checks.append(
            check(
                "lifecycle_audit",
                lifecycle_ready,
                {
                    "status": lifecycle.get("status"),
                    "state_persisted": lifecycle.get("state_persisted"),
                },
                {"status": "READY", "state_persisted": expected_persisted},
                "Order lifecycle audit is not READY or has an invalid persistence state",
            )
        )
    economics_required = requirements.get("step19_economics_required") is True
    if economics is not None or economics_required:
        economics = economics or {}
        economics_ready = (
            economics.get("economics_evidence_verified") is True
            and
            economics.get("status") == "READY"
            and economics.get("ledger_integrity_status") == "READY"
            and economics.get("cost_input_status") == "READY"
            and economics.get("account_reconciliation_status") == "READY"
            and economics.get("accounting_scope") == "POST_STEP19_BASELINE_ONLY"
            and economics.get("past_fills_reconstructed") is False
            and economics.get("capital_plan", {}).get("contribution_credited_as_profit_yen") == 0
            and economics.get("capital_plan", {}).get("automatic_risk_scaling") is False
            and economics.get("distribution", {}).get("distribution_executed") is False
            and economics.get("distribution", {}).get("external_transfer_executed") is False
            and economics.get("safety", {}).get("orders_submitted") == 0
            and economics.get("safety", {}).get("live_trading_enabled") is False
            and economics.get("safety", {}).get("automatic_promotion") is False
        )
        checks.append(
            check(
                "trading_economics",
                economics_ready,
                {
                    "status": economics.get("status", "MISSING"),
                    "evidence_verified": economics.get("economics_evidence_verified", False),
                    "ledger": economics.get("ledger_integrity_status", "MISSING"),
                    "cost_inputs": economics.get("cost_input_status", "MISSING"),
                    "reconciliation": economics.get("account_reconciliation_status", "MISSING"),
                },
                {
                    "status": "READY",
                    "evidence_verified": True,
                    "ledger": "READY",
                    "cost_inputs": "READY",
                    "reconciliation": "READY",
                },
                "Trading economics, costs, or account reconciliation are not READY",
            )
        )
    staged_required = requirements.get("step19_staged_pilot_required") is True
    if staged is not None or staged_required:
        staged = staged or {}
        component = staged.get("component_status", {})
        safety = staged.get("safety", {})
        staged_ready = (
            staged.get("status") == "READY"
            and staged.get("pilot_candidate_eligible") is True
            and component.get("manual_approval_status") == "READY"
            and component.get("rss_status") == "READY"
            and component.get("accounting_status") == "READY"
            and component.get("shadow_status") == "READY"
            and component.get("sell_safety_status") == "READY"
            and safety.get("orders_submitted") == 0
            and safety.get("live_trading_enabled") is False
            and safety.get("automatic_promotion") is False
            and safety.get("automatic_funding") is False
        )
        checks.append(
            check(
                "staged_pilot_integration",
                staged_ready,
                {
                    "status": staged.get("status", "MISSING"),
                    "pilot_candidate": staged.get("pilot_candidate_eligible", False),
                    "manual": component.get("manual_approval_status", "MISSING"),
                    "rss": component.get("rss_status", "MISSING"),
                    "safe_sell": component.get("sell_safety_status", "MISSING"),
                },
                {
                    "status": "READY",
                    "pilot_candidate": True,
                    "manual": "READY",
                    "rss": "READY",
                    "safe_sell": "READY",
                },
                "RSS, manual approval, accounting, shadow, or safe-SELL pilot integration is not READY",
            )
        )
    if historical is None:
        historical = {}
    if historical is not None:
        evidence_digest = str(historical.get("evidence_sha256", ""))
        digest_valid = (
            len(evidence_digest) == 64
            and all(value in "0123456789abcdefABCDEF" for value in evidence_digest)
        )
        historical_ready = (
            historical.get("gate_status") == "READY"
            and historical.get("execution_status") == "COMPLETED"
            and historical.get("evidence_kind") == "HISTORICAL_WALK_FORWARD_REPLAY"
            and digest_valid
            and historical.get("data_contract_status") == "READY"
            and historical.get("risk_limits_unchanged") is True
            and historical.get("input_files_unchanged") is True
            and historical.get("state_integrity_status") == "READY"
            and historical.get("post_save_integrity_status") == "READY"
            and historical.get("historical_evidence_verified") is True
            and historical.get("replay_scope") == "PRODUCTION_DECISION_PIPELINE"
            and historical.get("sealed_holdout_status") == "READY"
            and historical.get("execution_model_status") == "READY"
            and int(historical.get("paper_days_credited", -1) or 0) == 0
            and int(historical.get("audited_fills_credited", -1) or 0) == 0
            and int(historical.get("external_orders_submitted", -1) or 0) == 0
            and historical.get("live_trading_enabled") is False
            and historical.get("automatic_promotion") is False
        )
        checks.append(
            check(
                "historical_replay_gate",
                historical_ready,
                {
                    "gate_status": historical.get("gate_status", "MISSING"),
                    "evidence_kind": historical.get("evidence_kind", "MISSING"),
                    "data_contract_status": historical.get("data_contract_status", "MISSING"),
                    "state_integrity_status": historical.get("state_integrity_status", "MISSING"),
                    "post_save_integrity_status": historical.get("post_save_integrity_status", "MISSING"),
                    "replay_scope": historical.get("replay_scope", "MISSING"),
                    "sealed_holdout_status": historical.get("sealed_holdout_status", "MISSING"),
                    "execution_model_status": historical.get("execution_model_status", "MISSING"),
                },
                {
                    "gate_status": "READY",
                    "evidence_kind": "HISTORICAL_WALK_FORWARD_REPLAY",
                    "data_contract_status": "READY",
                    "state_integrity_status": "READY",
                    "post_save_integrity_status": "READY",
                    "replay_scope": "PRODUCTION_DECISION_PIPELINE",
                    "sealed_holdout_status": "READY",
                    "execution_model_status": "READY",
                },
                "Historical walk-forward evidence is not READY under the production data contract",
            )
        )
    errors = list(load_errors or [])
    ready = all(item["passed"] for item in checks) and not errors
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step19",
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
        "PHOENIX v7 STEP17.1 PAPER-TO-LIVE READINESS GATE", "=" * 92,
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
    historical_report_value = str(settings.get("historical_replay_report", "")).strip()
    historical_config_value = str(settings.get("historical_replay_config", "")).strip()
    economics_report_value = str(settings.get("economics_report", "")).strip()
    historical_configured = bool(historical_report_value and historical_config_value)
    if historical_report_value:
        sources["historical"] = historical_report_value
    if economics_report_value:
        sources["economics"] = economics_report_value
    loaded: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if not historical_report_value:
        errors.append("Historical replay report is required and cannot be disabled")
    if not historical_config_value:
        errors.append("Historical replay config is required and cannot be disabled")
    if settings.get("step19_economics_required") is not True:
        errors.append("Step19 economics requirement must remain enabled")
    if not economics_report_value:
        errors.append("Trading economics report is required and cannot be disabled")
    if settings.get("step19_staged_pilot_required") is not True:
        errors.append("Step19 staged pilot integration requirement must remain enabled")
    staged_settings = config.get("staged_pilot_gate", {})
    if not isinstance(staged_settings, Mapping) or staged_settings.get("enabled") is not True:
        errors.append("Step19 staged pilot gate must remain enabled")
    for name, value in sources.items():
        loaded[name], error = read_json(resolve_path(root, value))
        if error:
            errors.append(error)
    if historical_configured:
        replay_config = resolve_path(root, historical_config_value)
        evidence_valid, evidence_errors = verify_historical_report(
            root,
            loaded.get("historical", {}),
            replay_config,
        )
        loaded.setdefault("historical", {})["historical_evidence_verified"] = evidence_valid
        errors.extend(evidence_errors)
    else:
        loaded.setdefault("historical", {})["historical_evidence_verified"] = False
    if economics_report_value:
        economics_valid, economics_errors = verify_economics_report(
            root,
            config,
            loaded.get("economics", {}),
        )
        loaded.setdefault("economics", {})["economics_evidence_verified"] = economics_valid
        errors.extend(economics_errors)
    try:
        staged_report = run_staged_pilot_gate(root, config)
    except Exception as error:
        staged_report = {}
        errors.append(f"Could not rebuild staged pilot integration: {type(error).__name__}: {error}")
    report = build_readiness_report(
        loaded.get("performance", {}), loaded.get("operations", {}),
        loaded.get("market_data", {}), loaded.get("portfolio", {}), settings, errors,
        loaded.get("lifecycle", {}),
        loaded.get("historical", {}),
        loaded.get("economics", {}),
        staged_report,
    )
    json_path = resolve_path(root, str(settings.get("report_json", "reports/v7_readiness_gate.json")))
    text_path = resolve_path(root, str(settings.get("report_text", "reports/v7_readiness_gate.txt")))
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(text_path, text_report(report))
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    report["_staged_pilot_report"] = staged_report
    return report


def print_readiness_summary(report: Mapping[str, Any]) -> None:
    print("=" * 80)
    print("PHOENIX v7 STEP17.1 READINESS GATE")
    print("=" * 80)
    print(f"Status       : {report.get('status', '')}")
    print(f"Checks       : {report.get('passed_checks', 0)}/{report.get('total_checks', 0)}")
    print(f"Live enabled : {report.get('live_trading_enabled', False)}")
    print(f"Blockers     : {len(report.get('blocking_reasons', []))}")
    print(f"Report       : {report.get('report_text', '')}")
    print("=" * 80)
