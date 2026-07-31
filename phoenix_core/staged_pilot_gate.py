from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from phoenix_core.data_freshness import (
    JPX_CALENDAR_SHA256,
    is_jpx_equities_trading_day,
)
from phoenix_core.historical_replay import verify_historical_report
from phoenix_core.performance_tracker import atomic_write, resolve_path
from phoenix_core.rss_shadow_contract import (
    CONTRACT_ID as RSS_CONTRACT_ID,
    SOURCE_ID as RSS_SOURCE_ID,
    verify_rss_shadow_report,
    verify_shadow_evidence_state,
)
from phoenix_core.trading_economics import verify_economics_report


def _strict_int(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _canonical_sha256(value: Mapping[str, Any], hash_field: str) -> str:
    payload = {key: item for key, item in value.items() if key != hash_field}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verified_hash(value: Mapping[str, Any], hash_field: str) -> bool:
    digest = value.get(hash_field)
    return _is_sha256(digest) and digest == _canonical_sha256(value, hash_field)


def _strict_trading_date(value: Any, name: str, *, not_after: date) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError(f"{name} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be YYYY-MM-DD") from error
    if parsed.isoformat() != value:
        raise ValueError(f"{name} must be YYYY-MM-DD")
    try:
        trading_day = is_jpx_equities_trading_day(parsed)
    except ValueError as error:
        raise ValueError(f"{name} is outside the verified JPX calendar") from error
    if not trading_day:
        raise ValueError(f"{name} must be a verified JPX equities session date")
    if parsed > not_after:
        raise ValueError(f"{name} cannot be in the future")
    return parsed


def _strict_string_ids(value: Any, name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{name} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} contains duplicate ids")
    return value


def _strict_fill_links(
    value: Any,
    lifecycle_ids: list[str],
    economics_ids: list[str],
    name: str,
) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    pairs: list[tuple[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"{name}[{index}] must be an object")
        lifecycle_id = item.get("lifecycle_fill_id")
        economics_id = item.get("economics_fill_id")
        if not isinstance(lifecycle_id, str) or not lifecycle_id:
            raise ValueError(f"{name}[{index}].lifecycle_fill_id is invalid")
        if not isinstance(economics_id, str) or not economics_id:
            raise ValueError(f"{name}[{index}].economics_fill_id is invalid")
        pairs.append((lifecycle_id, economics_id))
    if len(pairs) != len(set(pairs)):
        raise ValueError(f"{name} contains duplicate links")
    if {item[0] for item in pairs} != set(lifecycle_ids):
        raise ValueError(f"{name} does not cover the lifecycle fill ids exactly")
    if {item[1] for item in pairs} != set(economics_ids):
        raise ValueError(f"{name} does not cover the economics fill ids exactly")
    if len(pairs) != len(lifecycle_ids) or len(pairs) != len(economics_ids):
        raise ValueError(f"{name} must provide a one-to-one fill mapping")
    return set(pairs)


def _authoritative_fill_links_match(
    pairs: set[tuple[str, str]],
    lifecycle: Mapping[str, Any],
    economics: Mapping[str, Any],
) -> bool:
    lifecycle_values = lifecycle.get("audited_fill_crosswalk", [])
    economics_values = economics.get("performance", {}).get("tracked_fill_evidence", [])
    if not isinstance(lifecycle_values, list) or not isinstance(economics_values, list):
        return False
    lifecycle_map: dict[str, Mapping[str, Any]] = {}
    economics_map: dict[str, Mapping[str, Any]] = {}
    for item in lifecycle_values:
        if not isinstance(item, Mapping):
            return False
        key = item.get("lifecycle_fill_id")
        if not isinstance(key, str) or not key or key in lifecycle_map:
            return False
        lifecycle_map[key] = item
    for item in economics_values:
        if not isinstance(item, Mapping):
            return False
        key = item.get("economics_fill_id")
        if not isinstance(key, str) or not key or key in economics_map:
            return False
        economics_map[key] = item
    fields = (
        "broker_order_id", "client_order_id", "ticker", "side", "quantity",
        "created_at", "broker_fill_event_sha256",
    )
    for lifecycle_id, economics_id in pairs:
        life = lifecycle_map.get(lifecycle_id)
        econ = economics_map.get(economics_id)
        if life is None or econ is None:
            return False
        if life.get("economics_fill_id") != economics_id:
            return False
        if any(life.get(field) != econ.get(field) for field in fields):
            return False
    return True


def _finite_number(value: Any, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{name} must be a finite number >= {minimum}")
    return result


def _check(code: str, passed: bool, actual: Any, required: Any, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "passed": bool(passed),
        "actual": actual,
        "required": required,
        "message": message,
    }


def _validate_settings(settings: Mapping[str, Any]) -> None:
    if not isinstance(settings, Mapping):
        raise ValueError("staged_pilot_gate config must be an object")
    required_flags = {
        "enabled": True,
        "advisory_only": True,
        "cash_only": True,
        "margin_allowed": False,
        "short_selling_allowed": False,
        "manual_approval_required": True,
        "rss_required": True,
        "live_trading_enabled": False,
        "automatic_promotion": False,
        "automatic_funding": False,
        "automatic_risk_scaling": False,
    }
    for name, required in required_flags.items():
        if settings.get(name) is not required:
            raise ValueError(f"Step19 {name} must remain {str(required).lower()}")
    exact_integers = {
        "base_capital_yen": 300_000,
        "conditional_contribution_yen": 200_000,
        "maximum_funded_capital_yen": 500_000,
        "risk_capital_basis_yen": 300_000,
        "minimum_shadow_sessions": 5,
        "minimum_shadow_fills": 3,
        "minimum_pilot_sessions_for_capital_increase": 5,
        "minimum_pilot_fills_for_capital_increase": 3,
        "max_new_buy_submissions_per_session": 1,
    }
    for name, required in exact_integers.items():
        actual = _strict_int(settings.get(name), name)
        if actual != required:
            raise ValueError(f"Step19 {name} must remain {required}")
    if settings.get("risk_reducing_sell_separate_path") is not True:
        raise ValueError("Risk-reducing SELL must remain a separate path from the BUY cap")
    if settings.get("single_verified_trading_unit") is not True:
        raise ValueError("The pilot must remain limited to one verified trading unit")


def _historical_ready(historical: Mapping[str, Any]) -> bool:
    try:
        zero_credits = all(
            _strict_int(historical.get(name), f"historical.{name}") == 0
            for name in (
                "external_orders_submitted", "paper_days_credited", "audited_fills_credited"
            )
        )
    except ValueError:
        return False
    return (
        historical.get("gate_status") == "READY"
        and historical.get("execution_status") == "COMPLETED"
        and historical.get("evidence_kind") == "HISTORICAL_WALK_FORWARD_REPLAY"
        and historical.get("data_contract_status") == "READY"
        and historical.get("state_integrity_status") == "READY"
        and historical.get("post_save_integrity_status") == "READY"
        and historical.get("historical_evidence_verified") is True
        and historical.get("risk_limits_unchanged") is True
        and historical.get("input_files_unchanged") is True
        and historical.get("replay_scope") == "PRODUCTION_DECISION_PIPELINE"
        and historical.get("sealed_holdout_status") == "READY"
        and historical.get("execution_model_status") == "READY"
        and historical.get("live_trading_enabled") is False
        and historical.get("automatic_promotion") is False
        and zero_credits
    )


def _shadow_metrics(
    shadow: Mapping[str, Any],
    *,
    not_after: date,
) -> tuple[int, int, set[str], set[str], set[tuple[str, str]], bool, list[str]]:
    errors: list[str] = []
    sessions = shadow.get("sessions", [])
    if not isinstance(sessions, list):
        return 0, 0, set(), set(), set(), False, ["Shadow sessions are not a list"]
    trading_dates: set[str] = set()
    lifecycle_fill_ids: set[str] = set()
    economics_fill_ids: set[str] = set()
    fill_links: set[tuple[str, str]] = set()
    for index, session in enumerate(sessions):
        if not isinstance(session, Mapping):
            errors.append(f"Shadow session {index} is not an object")
            continue
        try:
            trading_date = _strict_trading_date(
                session.get("trading_date"),
                f"shadow session {index}.trading_date",
                not_after=not_after,
            ).isoformat()
        except ValueError as error:
            errors.append(str(error))
            continue
        if trading_date in trading_dates:
            errors.append(f"Duplicate shadow trading date: {trading_date}")
        trading_dates.add(trading_date)
        session_id = session.get("session_id")
        if session_id != trading_date:
            errors.append(f"Shadow session_id must equal trading_date: {trading_date}")
        if not _verified_hash(session, "session_sha256"):
            errors.append(f"Shadow session {trading_date} hash is invalid")
        if session.get("integrity_status") != "READY":
            errors.append(f"Shadow session {session_id} integrity is not READY")
        if session.get("candidate_guard_status") != "READY":
            errors.append(f"Shadow session {session_id} candidate guard is not READY")
        if session.get("source") != RSS_SOURCE_ID or session.get("contract_id") != RSS_CONTRACT_ID:
            errors.append(f"Shadow session {session_id} is not bound to the Step20 RSS contract")
        if (
            session.get("coverage_method") != "THREE_POINT_SESSION_SAMPLING"
            or session.get("continuous_connection_claimed") is not False
        ):
            errors.append(f"Shadow session {session_id} sampling evidence is invalid")
        try:
            capture_count = _strict_int(
                session.get("capture_count"), f"shadow {trading_date}.capture_count"
            )
            capture_fields = (
                "capture_ids",
                "rss_manifest_files",
                "rss_manifest_sha256s",
                "rss_snapshot_sha256s",
            )
            for name in capture_fields:
                values = session.get(name)
                if (
                    not isinstance(values, list)
                    or len(values) != capture_count
                    or len(values) != len(set(values))
                ):
                    raise ValueError(f"shadow {trading_date}.{name} is invalid")
            if capture_count < 3:
                raise ValueError(f"shadow {trading_date} has fewer than three captures")
            first_capture = datetime.fromisoformat(str(session.get("first_capture_at", "")))
            last_capture = datetime.fromisoformat(str(session.get("last_capture_at", "")))
            if (
                first_capture.utcoffset() != timedelta(hours=9)
                or last_capture.utcoffset() != timedelta(hours=9)
                or first_capture.date().isoformat() != trading_date
                or last_capture.date().isoformat() != trading_date
                or (last_capture - first_capture).total_seconds() < 14_400
                or first_capture.time() > datetime.strptime("11:30", "%H:%M").time()
                or last_capture.time() < datetime.strptime("14:30", "%H:%M").time()
            ):
                raise ValueError(f"shadow {trading_date} capture span is invalid")
            for name in (
                "rss_snapshot_sha256",
                "rss_manifest_sha256",
                "rss_producer_sha256",
                "rss_workbook_sha256",
                "rss_vba_project_sha256",
                "rss_workbook_attestation_sha256",
                "rss_settings_sha256",
                "rss_universe_sha256",
            ):
                if not _is_sha256(session.get(name)):
                    raise ValueError(f"shadow {trading_date}.{name} is invalid")
            if (
                session.get("capture_id") not in session["capture_ids"]
                or session.get("rss_manifest_sha256") not in session["rss_manifest_sha256s"]
                or session.get("rss_snapshot_sha256") not in session["rss_snapshot_sha256s"]
            ):
                raise ValueError(f"shadow {trading_date} current capture is unbound")
        except (TypeError, ValueError) as error:
            errors.append(str(error))
        try:
            for name in ("risk_halt_count", "risk_override_count", "external_orders_submitted"):
                if _strict_int(session.get(name), f"shadow {trading_date}.{name}") != 0:
                    errors.append(f"Shadow session {trading_date} has nonzero {name}")
            lifecycle_values = _strict_string_ids(
                session.get("lifecycle_fill_ids"), f"shadow {trading_date}.lifecycle_fill_ids"
            )
            economics_values = _strict_string_ids(
                session.get("economics_fill_ids"), f"shadow {trading_date}.economics_fill_ids"
            )
            if len(lifecycle_values) != len(economics_values):
                errors.append(f"Shadow session {trading_date} fill evidence counts differ")
            session_links = _strict_fill_links(
                session.get("fill_links"),
                lifecycle_values,
                economics_values,
                f"shadow {trading_date}.fill_links",
            )
        except ValueError as error:
            errors.append(str(error))
            continue
        for fill_id in lifecycle_values:
            if fill_id in lifecycle_fill_ids:
                errors.append(f"Duplicate shadow lifecycle fill: {fill_id}")
            lifecycle_fill_ids.add(fill_id)
        for fill_id in economics_values:
            if fill_id in economics_fill_ids:
                errors.append(f"Duplicate shadow economics fill: {fill_id}")
            economics_fill_ids.add(fill_id)
        for link in session_links:
            if link in fill_links:
                errors.append(f"Duplicate shadow fill link: {link}")
            fill_links.add(link)
    try:
        root_zero = all(
            _strict_int(shadow.get(name), f"shadow.{name}") == 0
            for name in (
                "external_orders_submitted", "paper_days_credited", "audited_live_fills_credited"
            )
        )
    except ValueError as error:
        errors.append(str(error))
        root_zero = False
    evidence_valid = (
        shadow.get("evidence_kind") == "REALTIME_RSS_SHADOW"
        and shadow.get("integrity_status") == "VERIFIED"
        and shadow.get("jpx_calendar_status") == "VERIFIED"
        and shadow.get("jpx_calendar_sha256") == JPX_CALENDAR_SHA256
        and _verified_hash(shadow, "evidence_sha256")
        and root_zero
        and not errors
    )
    return (
        len(trading_dates), len(lifecycle_fill_ids), lifecycle_fill_ids,
        economics_fill_ids, fill_links, evidence_valid, errors,
    )


def _pilot_metrics(
    pilot: Mapping[str, Any],
    *,
    not_after: date,
) -> tuple[int, int, set[str], set[str], set[tuple[str, str]], bool, list[str]]:
    sessions = pilot.get("sessions", [])
    if not isinstance(sessions, list):
        return 0, 0, set(), set(), set(), False, ["Pilot sessions are not a list"]
    dates: set[str] = set()
    lifecycle_ids: set[str] = set()
    economics_ids: set[str] = set()
    fill_links: set[tuple[str, str]] = set()
    errors: list[str] = []
    valid = (
        pilot.get("integrity_status") == "VERIFIED"
        and pilot.get("jpx_calendar_status") == "VERIFIED"
        and pilot.get("jpx_calendar_sha256") == JPX_CALENDAR_SHA256
        and _verified_hash(pilot, "evidence_sha256")
    )
    for index, item in enumerate(sessions):
        if not isinstance(item, Mapping):
            errors.append(f"Pilot session {index} is not an object")
            continue
        try:
            trading_date = _strict_trading_date(
                item.get("trading_date"),
                f"pilot session {index}.trading_date",
                not_after=not_after,
            ).isoformat()
        except ValueError as error:
            errors.append(str(error))
            continue
        if trading_date in dates:
            errors.append(f"Duplicate pilot trading date: {trading_date}")
        dates.add(trading_date)
        if item.get("session_id") != trading_date:
            errors.append(f"Pilot session_id must equal trading_date: {trading_date}")
        if not _verified_hash(item, "session_sha256"):
            errors.append(f"Pilot session {trading_date} hash is invalid")
        if item.get("all_guards_status") != "READY":
            errors.append(f"Pilot session {trading_date} guards are not READY")
        try:
            attempts = _strict_int(
                item.get("new_buy_submission_attempts"),
                f"pilot {trading_date}.new_buy_submission_attempts",
            )
            if attempts > 1:
                errors.append(f"Pilot session {trading_date} exceeds the daily BUY cap")
            for name in ("unreconciled_fill_count", "risk_halt_count"):
                if _strict_int(item.get(name), f"pilot {trading_date}.{name}") != 0:
                    errors.append(f"Pilot session {trading_date} has nonzero {name}")
            life_values = _strict_string_ids(
                item.get("lifecycle_fill_ids"), f"pilot {trading_date}.lifecycle_fill_ids"
            )
            econ_values = _strict_string_ids(
                item.get("economics_fill_ids"), f"pilot {trading_date}.economics_fill_ids"
            )
            if len(life_values) != len(econ_values):
                errors.append(f"Pilot session {trading_date} fill evidence counts differ")
            session_links = _strict_fill_links(
                item.get("fill_links"),
                life_values,
                econ_values,
                f"pilot {trading_date}.fill_links",
            )
        except ValueError as error:
            errors.append(str(error))
            continue
        for fill_id in life_values:
            if fill_id in lifecycle_ids:
                errors.append(f"Duplicate pilot lifecycle fill: {fill_id}")
            lifecycle_ids.add(fill_id)
        for fill_id in econ_values:
            if fill_id in economics_ids:
                errors.append(f"Duplicate pilot economics fill: {fill_id}")
            economics_ids.add(fill_id)
        for link in session_links:
            if link in fill_links:
                errors.append(f"Duplicate pilot fill link: {link}")
            fill_links.add(link)
    valid = valid and not errors
    return (
        len(dates), len(lifecycle_ids), lifecycle_ids, economics_ids,
        fill_links, valid, errors,
    )


def build_staged_pilot_report(
    performance: Mapping[str, Any],
    operations: Mapping[str, Any],
    market_data: Mapping[str, Any],
    portfolio: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
    historical: Mapping[str, Any],
    economics: Mapping[str, Any],
    shadow: Mapping[str, Any],
    pilot: Mapping[str, Any],
    settings: Mapping[str, Any],
    *,
    rss_contract: Mapping[str, Any] | None = None,
    shadow_evidence_verified: bool = False,
    load_errors: list[str] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    _validate_settings(settings)
    generated_at = generated_at or datetime.now()
    paper = performance.get("paper_evidence", {})
    if not isinstance(paper, Mapping):
        paper = {}
    pipeline = operations.get("pipeline", {})
    if not isinstance(pipeline, Mapping):
        pipeline = {}
    candidate_guard_status = str(pipeline.get("candidate_input_status", "MISSING"))
    (
        shadow_sessions,
        shadow_fills,
        shadow_lifecycle_fill_ids,
        shadow_economics_fill_ids,
        shadow_fill_links,
        shadow_valid,
        shadow_errors,
    ) = _shadow_metrics(shadow, not_after=generated_at.date())
    shadow_valid = shadow_valid and shadow_evidence_verified is True
    (
        pilot_sessions,
        pilot_fills,
        pilot_lifecycle_fill_ids,
        pilot_economics_fill_ids,
        pilot_fill_links,
        pilot_valid,
        pilot_errors,
    ) = _pilot_metrics(pilot, not_after=generated_at.date())
    portfolio_reviews = int(portfolio.get("action_counts", {}).get("REVIEW", 0) or 0)
    failed_runs = int(paper.get("status_counts", {}).get("FAILED", 0) or 0)
    risk_halts = int(paper.get("risk_halt_count", 0) or 0)
    historical_ready = _historical_ready(historical)
    economics_ready = (
        economics.get("economics_evidence_verified") is True
        and economics.get("status") == "READY"
        and economics.get("ledger_integrity_status") == "READY"
        and economics.get("cost_input_status") == "READY"
        and economics.get("account_reconciliation_status") == "READY"
        and economics.get("safety", {}).get("live_trading_enabled") is False
        and economics.get("safety", {}).get("automatic_promotion") is False
    )
    rss_contract_ready = (
        isinstance(rss_contract, Mapping)
        and rss_contract.get("rss_evidence_verified") is True
        and rss_contract.get("status") == "READY"
        and rss_contract.get("evidence_verified") is True
        and rss_contract.get("safety", {}).get("read_only") is True
        and rss_contract.get("safety", {}).get("orders_allowed") is False
        and type(rss_contract.get("safety", {}).get("orders_submitted")) is int
        and rss_contract.get("safety", {}).get("orders_submitted") == 0
        and rss_contract.get("safety", {}).get("live_trading_enabled") is False
    )
    lifecycle_fill_values = lifecycle.get("audited_fill_ids", [])
    lifecycle_fill_ids = (
        set(lifecycle_fill_values)
        if isinstance(lifecycle_fill_values, list)
        and all(isinstance(value, str) and value for value in lifecycle_fill_values)
        and len(lifecycle_fill_values) == len(set(lifecycle_fill_values))
        else set()
    )
    economics_fill_values = economics.get("performance", {}).get("tracked_fill_event_ids", [])
    economics_fill_ids = (
        set(economics_fill_values)
        if isinstance(economics_fill_values, list)
        and all(isinstance(value, str) and value for value in economics_fill_values)
        and len(economics_fill_values) == len(set(economics_fill_values))
        else set()
    )
    shadow_fills_reconciled = (
        bool(shadow_lifecycle_fill_ids)
        and shadow_lifecycle_fill_ids.issubset(lifecycle_fill_ids)
        and shadow_economics_fill_ids.issubset(economics_fill_ids)
        and int(lifecycle.get("audited_fill_count", -1) or 0) == len(lifecycle_fill_ids)
        and _authoritative_fill_links_match(shadow_fill_links, lifecycle, economics)
    )
    pilot_fills_reconciled = (
        bool(pilot_lifecycle_fill_ids)
        and pilot_lifecycle_fill_ids.issubset(lifecycle_fill_ids)
        and pilot_economics_fill_ids.issubset(economics_fill_ids)
        and _authoritative_fill_links_match(pilot_fill_links, lifecycle, economics)
    )
    metric_errors: list[str] = []
    if shadow_lifecycle_fill_ids.intersection(pilot_lifecycle_fill_ids):
        metric_errors.append("Shadow and pilot lifecycle fills must not overlap")
    if shadow_economics_fill_ids.intersection(pilot_economics_fill_ids):
        metric_errors.append("Shadow and pilot economics fills must not overlap")
    try:
        business_net = _finite_number(
            economics.get("performance", {}).get("business_net_after_all_reserved_costs_yen"),
            "economics.business_net_after_all_reserved_costs_yen",
        )
        unrecovered_loss = _finite_number(
            economics.get("performance", {}).get("unrecovered_loss_yen"),
            "economics.unrecovered_loss_yen",
            0,
        )
        maximum_drawdown = _finite_number(
            pilot.get("maximum_drawdown_pct"), "pilot.maximum_drawdown_pct", 0
        )
    except ValueError as error:
        metric_errors.append(str(error))
        business_net = -1.0
        unrecovered_loss = 1.0
        maximum_drawdown = 1.0
    checks = [
        _check("HISTORICAL_REPLAY_NOT_READY", historical_ready, historical.get("gate_status", "MISSING"), "READY", "Historical replay and data-quality gates must pass"),
        _check("CANDIDATE_GUARD_NOT_READY", candidate_guard_status == "READY", candidate_guard_status, "READY", "Canonical Step18 candidate evidence must be READY"),
        _check("MARKET_DATA_NOT_READY", market_data.get("status") == "READY", market_data.get("status", "MISSING"), "READY", "Market data freshness must be READY"),
        _check("PORTFOLIO_REVIEW_REQUIRED", portfolio_reviews == 0, portfolio_reviews, 0, "No position may require manual data review"),
        _check(
            "LIFECYCLE_NOT_READY",
            lifecycle.get("status") == "READY" and lifecycle.get("state_persisted") is True,
            {"status": lifecycle.get("status", "MISSING"), "state_persisted": lifecycle.get("state_persisted")},
            {"status": "READY", "state_persisted": True},
            "Order lifecycle must be reconciled and persisted",
        ),
        _check("FAILED_PAPER_RUNS_EXIST", failed_runs == 0, failed_runs, 0, "No failed paper run may exist in the evaluation window"),
        _check("RISK_HALTS_EXIST", risk_halts == 0, risk_halts, 0, "No risk halt may exist in the evaluation window"),
        _check("ECONOMICS_NOT_READY", economics_ready, economics.get("status", "MISSING"), "READY", "Step19 costs and accounting must be fully reconciled"),
        _check("SHADOW_EVIDENCE_INVALID", shadow_valid, shadow.get("integrity_status", "MISSING"), "VERIFIED", "Realtime RSS shadow evidence must be verified"),
        _check("SHADOW_SESSIONS_INSUFFICIENT", shadow_sessions >= 5, shadow_sessions, 5, "Five distinct JPX realtime shadow sessions are required"),
        _check("SHADOW_FILLS_INSUFFICIENT", shadow_fills >= 3, shadow_fills, 3, "Three unique audited shadow fills are required"),
        _check(
            "SHADOW_FILLS_UNRECONCILED",
            shadow_fills_reconciled,
            {
                "shadow_lifecycle": len(shadow_lifecycle_fill_ids),
                "shadow_economics": len(shadow_economics_fill_ids),
                "lifecycle": len(lifecycle_fill_ids),
                "economics": len(economics_fill_ids),
            },
            "Every shadow fill exists in lifecycle and economics evidence",
            "Realtime shadow fills must reconcile to lifecycle and broker economics evidence",
        ),
        _check("MANUAL_APPROVAL_NOT_IMPLEMENTED", settings.get("manual_approval_implementation_ready") is True, settings.get("manual_approval_implementation_ready", False), True, "Single-use hash-bound manual approval is not implemented"),
        _check("RSS_NOT_IMPLEMENTED", settings.get("rss_implementation_ready") is True, settings.get("rss_implementation_ready", False), True, "Rakuten RSS and Excel evidence connection is not implemented"),
        _check("RSS_CONTRACT_NOT_READY", rss_contract_ready, rss_contract.get("status", "MISSING") if isinstance(rss_contract, Mapping) else "MISSING", "READY and independently verified", "The read-only Rakuten RSS snapshot contract is not objectively verified"),
        _check("RAKUTEN_FEE_PLAN_UNVERIFIED", settings.get("rakuten_fee_plan_verified") is True, settings.get("rakuten_fee_plan_verified", False), True, "The actual Rakuten commission course is unverified"),
        _check("TAX_TREATMENT_UNVERIFIED", settings.get("tax_treatment_verified") is True, settings.get("tax_treatment_verified", False), True, "The account tax treatment is unverified"),
        _check("CASH_ACCOUNT_UNVERIFIED", settings.get("cash_account_verified") is True, settings.get("cash_account_verified", False), True, "A live cash-only account has not been verified"),
        _check("TRADING_UNIT_UNVERIFIED", settings.get("security_master_unit_verified") is True, settings.get("security_master_unit_verified", False), True, "A broker security-master trading unit has not been verified"),
        _check("DAILY_BUY_CAP_NOT_ENFORCED", settings.get("daily_buy_cap_enforcement_ready") is True, settings.get("daily_buy_cap_enforcement_ready", False), True, "One new BUY submission attempt per JPX session is not enforced"),
        _check("SAFE_SELL_PATH_NOT_IMPLEMENTED", settings.get("risk_reducing_sell_path_ready") is True, settings.get("risk_reducing_sell_path_ready", False), True, "A separate risk-reducing SELL path is not implemented"),
    ]
    errors = list(load_errors or []) + shadow_errors + pilot_errors + metric_errors
    pilot_candidate = all(item["passed"] for item in checks) and not errors

    capital_checks = [
        _check("PILOT_NOT_ACTIVE", settings.get("limited_live_pilot_active") is True, settings.get("limited_live_pilot_active", False), True, "The limited live pilot has not been explicitly activated"),
        _check("PILOT_SESSIONS_INSUFFICIENT", pilot_sessions >= 5, pilot_sessions, 5, "Five distinct guarded pilot sessions are required before a contribution candidate"),
        _check("PILOT_FILLS_INSUFFICIENT", pilot_fills >= 3, pilot_fills, 3, "Three independently reconciled pilot fills are required before a contribution candidate"),
        _check("PILOT_EVIDENCE_INVALID", pilot_valid, pilot.get("integrity_status", "MISSING"), "VERIFIED", "Pilot evidence must show all guards READY with no unresolved fill"),
        _check("PILOT_FILLS_UNRECONCILED", pilot_fills_reconciled, {"lifecycle": len(pilot_lifecycle_fill_ids), "economics": len(pilot_economics_fill_ids)}, "Every pilot fill exists in lifecycle and economics evidence", "Pilot fills must reconcile to independent evidence"),
        _check("BUSINESS_NET_NOT_POSITIVE", business_net > 0, business_net, "> 0", "All costs, tax reserve, and fixed operating costs must be covered"),
        _check("COST_COVERAGE_INSUFFICIENT", economics.get("performance", {}).get("cost_coverage") is True, economics.get("performance", {}).get("cost_coverage", False), True, "Strategy profit must cover fixed operating costs"),
        _check("HIGH_WATER_MARK_NOT_RECONCILED", economics.get("distribution", {}).get("high_water_mark_reconciled") is True, economics.get("distribution", {}).get("high_water_mark_reconciled", False), True, "High-water mark must be reconciled before adding capital"),
        _check("UNRECOVERED_LOSS_EXISTS", unrecovered_loss == 0, unrecovered_loss, 0, "No unrecovered loss may remain before adding capital"),
        _check("PILOT_DRAWDOWN_EXCEEDED", maximum_drawdown <= 0.10, maximum_drawdown, "<= 0.10", "Pilot maximum drawdown must remain within 10%"),
        _check("FUNDING_APPROVAL_MISSING", settings.get("conditional_funding_approved") is True, settings.get("conditional_funding_approved", False), True, "The conditional 200,000-yen contribution requires separate approval"),
    ]
    capital_increase_candidate = pilot_candidate and all(item["passed"] for item in capital_checks)

    blocking_checks = [item for item in checks + capital_checks if not item["passed"]]
    blocking_codes = ["LOAD_ERROR"] * len(errors) + [item["code"] for item in blocking_checks]
    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step19",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "status": "READY" if pilot_candidate else "NOT_READY",
        "phase": "PAPER_AND_REALTIME_SHADOW_VALIDATION",
        "pilot_candidate_eligible": pilot_candidate,
        "capital_increase_candidate_eligible": capital_increase_candidate,
        "capital": {
            "current_authorized_capital_yen": 300_000,
            "conditional_contribution_yen": 200_000,
            "maximum_funded_capital_yen": 500_000,
            "risk_capital_basis_yen": 300_000,
            "funding_approved": False,
            "risk_cap_approved": False,
            "capital_contribution_executed": False,
            "contribution_credited_as_profit_yen": 0,
        },
        "pilot_contract": {
            "minimum_shadow_sessions": 5,
            "minimum_shadow_fills": 3,
            "max_new_buy_submissions_per_session": 1,
            "single_verified_trading_unit": True,
            "cash_only": True,
            "manual_approval_required": True,
            "rss_required": True,
            "risk_reducing_sell_separate_path": True,
        },
        "evidence": {
            "shadow_sessions": shadow_sessions,
            "shadow_fills": shadow_fills,
            "pilot_sessions": pilot_sessions,
            "pilot_fills": pilot_fills,
            "paper_days_credited_from_historical": 0,
            "audited_live_fills_credited_from_shadow": 0,
            "external_orders_submitted": 0,
        },
        "component_status": {
            "manual_approval_status": "READY" if settings.get("manual_approval_implementation_ready") is True else "NOT_IMPLEMENTED",
            "rss_status": (
                "READY"
                if settings.get("rss_implementation_ready") is True and rss_contract_ready
                else "NOT_IMPLEMENTED"
                if settings.get("rss_implementation_ready") is not True
                else "NOT_READY"
            ),
            "rakuten_fee_plan_status": "READY" if settings.get("rakuten_fee_plan_verified") is True else "UNVERIFIED",
            "accounting_status": "READY" if economics_ready else "NOT_READY",
            "shadow_status": "READY" if shadow_valid and shadow_sessions >= 5 and shadow_fills >= 3 else "NOT_READY",
            "sell_safety_status": "READY" if settings.get("risk_reducing_sell_path_ready") is True else "NOT_IMPLEMENTED",
        },
        "checks": checks,
        "capital_increase_checks": capital_checks,
        "blocking_codes": blocking_codes,
        "blocking_reasons": errors + [item["message"] for item in blocking_checks],
        "load_errors": list(load_errors or []),
        "safety": {
            "advisory_only": True,
            "orders_submitted": 0,
            "live_trading_enabled": False,
            "automatic_promotion": False,
            "automatic_funding": False,
            "automatic_risk_scaling": False,
            "external_transfer_executed": False,
            "distribution_executed": False,
        },
    }


def text_report(report: Mapping[str, Any]) -> str:
    capital = report.get("capital", {})
    evidence = report.get("evidence", {})
    components = report.get("component_status", {})
    lines = [
        "PHOENIX v7 STEP19 STAGED CAPITAL AND LIMITED PILOT CANDIDATE GATE",
        "=" * 98,
        f"Status                    : {report.get('status', '')}",
        f"Pilot candidate           : {report.get('pilot_candidate_eligible', False)}",
        f"Capital increase candidate: {report.get('capital_increase_candidate_eligible', False)}",
        f"Capital                   : {capital.get('current_authorized_capital_yen', 0):,.0f} + {capital.get('conditional_contribution_yen', 0):,.0f} / max {capital.get('maximum_funded_capital_yen', 0):,.0f} JPY",
        f"Risk basis                : {capital.get('risk_capital_basis_yen', 0):,.0f} JPY (separate approval)",
        "-" * 98,
        f"Shadow sessions / fills   : {evidence.get('shadow_sessions', 0)} / {evidence.get('shadow_fills', 0)}",
        f"Manual approval           : {components.get('manual_approval_status', '')}",
        f"Rakuten RSS / Excel       : {components.get('rss_status', '')}",
        f"Rakuten commission plan   : {components.get('rakuten_fee_plan_status', '')}",
        f"Trading economics         : {components.get('accounting_status', '')}",
        f"Risk-reducing SELL path   : {components.get('sell_safety_status', '')}",
        "-" * 98,
    ]
    for item in report.get("checks", []):
        mark = "PASS" if item.get("passed") else "BLOCK"
        lines.append(f"{mark:<6} {item.get('code', ''):<38} actual={item.get('actual')} required={item.get('required')}")
    lines.extend([
        "-" * 98,
        "This is an advisory candidate gate. It never enables orders, live trading, funding, risk scaling, or transfers.",
        "=" * 98,
        "",
    ])
    return "\n".join(lines)


def _read_json(path: Path, label: str, required: bool = True) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, f"Required {label} report not found: {path}" if required else None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, f"Could not read {label}: {type(error).__name__}: {error}"
    if not isinstance(value, dict):
        return {}, f"{label} root is not an object"
    return value, None


def run_staged_pilot_gate(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    settings = config.get("staged_pilot_gate", {})
    if not isinstance(settings, Mapping):
        raise ValueError("staged_pilot_gate config must be an object")
    _validate_settings(settings)
    source_names = (
        "performance", "operations", "market_data", "portfolio", "lifecycle",
        "historical", "economics", "shadow", "pilot", "rss_contract",
    )
    defaults = {
        "performance": "reports/v7_performance_summary.json",
        "operations": "reports/v7_operations_report.json",
        "market_data": "reports/v7_market_data_guard.json",
        "portfolio": "reports/v7_portfolio_guard.json",
        "lifecycle": "reports/v7_order_lifecycle.json",
        "historical": "reports/v7_historical_replay.json",
        "economics": "reports/v7_trading_economics.json",
        "shadow": "state/v7_realtime_shadow_evidence.json",
        "pilot": "state/v7_limited_pilot_evidence.json",
        "rss_contract": "reports/v7_rss_shadow_contract.json",
    }
    loaded: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name in source_names:
        path = resolve_path(root, str(settings.get(f"{name}_report", defaults[name])))
        loaded[name], error = _read_json(path, name, required=True)
        if error:
            errors.append(error)
    historical_config_value = str(settings.get("historical_replay_config", "")).strip()
    if not historical_config_value:
        errors.append("Historical replay config is required")
        loaded.setdefault("historical", {})["historical_evidence_verified"] = False
    else:
        config_path = resolve_path(root, historical_config_value)
        verified, verify_errors = verify_historical_report(root, loaded.get("historical", {}), config_path)
        loaded.setdefault("historical", {})["historical_evidence_verified"] = verified
        errors.extend(verify_errors)
    economics_verified, economics_errors = verify_economics_report(
        root, config, loaded.get("economics", {})
    )
    loaded.setdefault("economics", {})["economics_evidence_verified"] = economics_verified
    errors.extend(economics_errors)
    rss_verified, rss_errors = verify_rss_shadow_report(
        root, config, loaded.get("rss_contract", {})
    )
    loaded.setdefault("rss_contract", {})["rss_evidence_verified"] = rss_verified
    errors.extend(rss_errors)
    shadow_verified, shadow_verify_errors = verify_shadow_evidence_state(
        root, config, loaded.get("shadow", {})
    )
    errors.extend(shadow_verify_errors)
    report = build_staged_pilot_report(
        loaded.get("performance", {}),
        loaded.get("operations", {}),
        loaded.get("market_data", {}),
        loaded.get("portfolio", {}),
        loaded.get("lifecycle", {}),
        loaded.get("historical", {}),
        loaded.get("economics", {}),
        loaded.get("shadow", {}),
        loaded.get("pilot", {}),
        settings,
        rss_contract=loaded.get("rss_contract", {}),
        shadow_evidence_verified=shadow_verified,
        load_errors=errors,
    )
    json_path = resolve_path(root, str(settings.get("report_json", "reports/v7_staged_pilot_gate.json")))
    text_path = resolve_path(root, str(settings.get("report_text", "reports/v7_staged_pilot_gate.txt")))
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    atomic_write(text_path, text_report(report))
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    return report


def print_staged_pilot_summary(report: Mapping[str, Any]) -> None:
    capital = report.get("capital", {})
    evidence = report.get("evidence", {})
    print("=" * 80)
    print("PHOENIX v7 STEP19 STAGED PILOT CANDIDATE GATE")
    print("=" * 80)
    print(f"Status       : {report.get('status', '')}")
    print(f"Pilot        : {report.get('pilot_candidate_eligible', False)}")
    print(f"Capital +20  : {report.get('capital_increase_candidate_eligible', False)}")
    print(f"Shadow days  : {evidence.get('shadow_sessions', 0)}/5")
    print(f"Shadow fills : {evidence.get('shadow_fills', 0)}/3")
    print(f"Risk basis   : {capital.get('risk_capital_basis_yen', 0):,.0f} JPY")
    print(f"Live enabled : {report.get('safety', {}).get('live_trading_enabled', False)}")
    print(f"Report       : {report.get('report_text', '')}")
    print("=" * 80)
