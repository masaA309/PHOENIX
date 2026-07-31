from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from phoenix_core.broker import PaperBroker
from phoenix_core.performance_tracker import atomic_write, resolve_path


YEN = Decimal("0.01")
STEP19_BASE_CAPITAL_YEN = Decimal("300000")
STEP19_CONDITIONAL_CONTRIBUTION_YEN = Decimal("200000")
STEP19_MAX_FUNDED_CAPITAL_YEN = Decimal("500000")
STEP19_FIXED_MONTHLY_COST_YEN = Decimal("7000")
STEP19_CONSERVATIVE_TAX_RATE = Decimal("0.20315")
STEP19_LIVING_FUNDS_RATE = Decimal("0.20")
STEP19_MAX_DISTRIBUTION_RATE = Decimal("0.30")
JST = ZoneInfo("Asia/Tokyo")
VALID_COMMISSION_PLANS = {"SUPER_DISCOUNT", "ZERO_COURSE"}


def _money(value: Any, name: str, *, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not result.is_finite():
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result.quantize(YEN, rounding=ROUND_HALF_UP)


def _rate(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite rate")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"{name} must be a finite rate") from error
    if not result.is_finite():
        raise ValueError(f"{name} must be a finite rate")
    return result


def _as_float(value: Decimal) -> float:
    return float(value.quantize(YEN, rounding=ROUND_HALF_UP))


def _strict_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    value = {key: item for key, item in payload.items() if key != "event_sha256"}
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(encoded).hexdigest()


def _parse_datetime(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an ISO datetime")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO datetime") from error
    if result.tzinfo is None or result.utcoffset() != timedelta(hours=9):
        raise ValueError(f"{name} must include the JST +09:00 offset")
    return result


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _rakuten_super_discount_fee(gross_yen: Decimal) -> Decimal:
    tiers = (
        (Decimal("50000"), Decimal("55")),
        (Decimal("100000"), Decimal("99")),
        (Decimal("200000"), Decimal("115")),
        (Decimal("500000"), Decimal("275")),
        (Decimal("1000000"), Decimal("535")),
        (Decimal("1500000"), Decimal("640")),
        (Decimal("30000000"), Decimal("1013")),
    )
    for limit, fee in tiers:
        if gross_yen <= limit:
            return fee
    return Decimal("1070")


def _evidence_file_matches(
    root: Path | None,
    relative_value: Any,
    expected_sha256: Any,
) -> bool:
    if root is None or not _is_sha256(expected_sha256):
        return False
    if not isinstance(relative_value, str) or not relative_value.strip():
        return False
    root_resolved = root.resolve()
    candidate = (root_resolved / relative_value).resolve()
    if not candidate.is_relative_to(root_resolved) or not candidate.is_file():
        return False
    try:
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError:
        return False
    return actual == str(expected_sha256).lower()


def _validate_step19_settings(
    settings: Mapping[str, Any],
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(settings, Mapping):
        raise ValueError("trading_economics config must be an object")
    if settings.get("enabled") is not True:
        raise ValueError("Step19 trading_economics.enabled must remain true")
    if settings.get("advisory_only") is not True:
        raise ValueError("Step19 advisory_only must remain true")
    if settings.get("live_trading_enabled") is not False:
        raise ValueError("Step19 live_trading_enabled must remain false")
    if settings.get("automatic_promotion") is not False:
        raise ValueError("Step19 automatic_promotion must remain false")

    capital = settings.get("capital_plan", {})
    if not isinstance(capital, Mapping):
        raise ValueError("capital_plan must be an object")
    base = _money(capital.get("base_capital_yen"), "base_capital_yen", minimum=Decimal(0))
    addition = _money(
        capital.get("conditional_contribution_yen"),
        "conditional_contribution_yen",
        minimum=Decimal(0),
    )
    maximum = _money(
        capital.get("maximum_funded_capital_yen"),
        "maximum_funded_capital_yen",
        minimum=Decimal(0),
    )
    risk_basis = _money(
        capital.get("risk_capital_basis_yen"),
        "risk_capital_basis_yen",
        minimum=Decimal(0),
    )
    if (
        base != STEP19_BASE_CAPITAL_YEN
        or addition != STEP19_CONDITIONAL_CONTRIBUTION_YEN
        or maximum != STEP19_MAX_FUNDED_CAPITAL_YEN
        or base + addition != maximum
    ):
        raise ValueError("Step19 capital plan must remain 300,000 + 200,000 = 500,000 yen")
    if risk_basis != base or capital.get("automatic_risk_scaling") is not False:
        raise ValueError("Capital contribution must not automatically increase the risk basis")

    fixed = _money(
        settings.get("fixed_monthly_operating_cost_yen"),
        "fixed_monthly_operating_cost_yen",
        minimum=Decimal(0),
    )
    if fixed != STEP19_FIXED_MONTHLY_COST_YEN:
        raise ValueError("Step19 fixed monthly operating cost must remain 7,000 yen")

    distribution = settings.get("distribution", {})
    if not isinstance(distribution, Mapping):
        raise ValueError("distribution must be an object")
    living_rate = _rate(distribution.get("living_funds_rate"), "living_funds_rate")
    maximum_rate = _rate(distribution.get("maximum_living_funds_rate"), "maximum_living_funds_rate")
    if living_rate != STEP19_LIVING_FUNDS_RATE or maximum_rate != STEP19_MAX_DISTRIBUTION_RATE:
        raise ValueError("Step19 living-funds rate must remain 20% with a 30% safety ceiling")
    if distribution.get("manual_approval_required") is not True:
        raise ValueError("Living-funds distribution must require manual approval")
    if distribution.get("unrealized_profit_eligible") is not False:
        raise ValueError("Unrealized profit must not be distributable")

    tax = settings.get("tax_reserve", {})
    if not isinstance(tax, Mapping):
        raise ValueError("tax_reserve must be an object")
    tax_rate = _rate(tax.get("conservative_rate"), "conservative_rate")
    if tax_rate != STEP19_CONSERVATIVE_TAX_RATE:
        raise ValueError("Conservative listed-stock tax reserve must remain 20.315%")

    commission = settings.get("commission", {})
    if not isinstance(commission, Mapping):
        raise ValueError("commission must be an object")
    fallback_fee = _money(
        commission.get("unverified_plan_fee_reserve_per_filled_order_yen"),
        "unverified_plan_fee_reserve_per_filled_order_yen",
        minimum=Decimal(0),
    )
    if fallback_fee < Decimal("1070"):
        raise ValueError("Unverified Rakuten fee plan reserve must be at least 1,070 yen per fill")
    account_plan = commission.get("account_plan")
    plan_claimed_verified = commission.get("account_plan_verified") is True
    schedule_hash_valid = _evidence_file_matches(
        evidence_root,
        commission.get("published_fee_schedule_file"),
        commission.get("published_fee_schedule_sha256"),
    )
    account_evidence_valid = _evidence_file_matches(
        evidence_root,
        commission.get("account_plan_evidence_file"),
        commission.get("account_plan_evidence_sha256"),
    )
    sor_verified = commission.get("sor_r_cross_agreement_verified") is True
    plan_evidence_verified = (
        plan_claimed_verified
        and account_plan in VALID_COMMISSION_PLANS
        and schedule_hash_valid
        and account_evidence_valid
        and (account_plan != "ZERO_COURSE" or sor_verified)
    )

    slippage = settings.get("slippage", {})
    if not isinstance(slippage, Mapping):
        raise ValueError("slippage must be an object")
    slippage_bps = _rate(slippage.get("reserve_bps_per_side"), "reserve_bps_per_side")
    if slippage_bps < 0:
        raise ValueError("reserve_bps_per_side must not be negative")

    return {
        "base": base,
        "addition": addition,
        "maximum": maximum,
        "risk_basis": risk_basis,
        "fixed": fixed,
        "living_rate": living_rate,
        "maximum_rate": maximum_rate,
        "tax_rate": tax_rate,
        "fallback_fee": fallback_fee,
        "slippage_bps": slippage_bps,
        "account_plan": account_plan,
        "commission_verified": plan_evidence_verified,
        "commission_claimed_verified": plan_claimed_verified,
        "commission_evidence_valid": schedule_hash_valid and account_evidence_valid,
        "tax_verified": tax.get("account_tax_treatment_verified") is True,
    }


def verify_broker_economics_state(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        return {"status": "NOT_READY", "errors": ["Broker state root is not an object"]}
    version = payload.get("state_version")
    if version == 1:
        return {
            "status": "BASELINE_PENDING",
            "errors": ["Step19 accounting baseline has not been atomically established yet"],
        }
    if version != 2:
        return {"status": "NOT_READY", "errors": ["Unsupported Paper Broker state version"]}
    if payload.get("broker_name") != "PAPER":
        errors.append("Accounting evidence must come from PAPER broker")
    if payload.get("account_type") != "CASH":
        errors.append("Broker account type is not confirmed CASH")
    if payload.get("live_trading_enabled") is not False:
        errors.append("Broker state unexpectedly enables live trading")
    if payload.get("margin_trading_enabled") is not False:
        errors.append("Broker state unexpectedly enables margin trading")

    baseline_at: datetime | None = None
    updated_at: datetime | None = None
    try:
        updated_at = _parse_datetime(payload.get("updated_at"), "updated_at")
        if now is not None:
            checked_now = now if now.tzinfo is not None else now.replace(tzinfo=JST)
            if updated_at > checked_now.astimezone(JST):
                raise ValueError("Broker state updated_at is in the future")
    except ValueError as error:
        errors.append(str(error))

    baseline = payload.get("economics_baseline")
    if not isinstance(baseline, Mapping):
        errors.append("economics_baseline is missing")
        baseline = {}
    else:
        try:
            if baseline.get("schema_version") != 1:
                raise ValueError("economics_baseline schema_version must be 1")
            baseline_at = _parse_datetime(
                baseline.get("established_at"), "economics_baseline.established_at"
            )
            if updated_at is not None and baseline_at > updated_at:
                raise ValueError("Accounting baseline is later than broker updated_at")
            _money(baseline.get("cash_yen"), "economics_baseline.cash_yen", minimum=Decimal(0))
            _money(baseline.get("realized_pnl_yen"), "economics_baseline.realized_pnl_yen")
            ids = baseline.get("processed_client_order_ids")
            if not isinstance(ids, list) or any(not isinstance(value, str) or not value for value in ids):
                raise ValueError("economics_baseline.processed_client_order_ids must be strings")
            if len(ids) != len(set(ids)):
                raise ValueError("economics_baseline contains duplicate processed order ids")
            positions = baseline.get("positions")
            if not isinstance(positions, Mapping):
                raise ValueError("economics_baseline.positions must be an object")
            for ticker, position in positions.items():
                if not isinstance(ticker, str) or not ticker or not isinstance(position, Mapping):
                    raise ValueError("economics_baseline position is invalid")
                _strict_int(position.get("quantity"), f"baseline position {ticker}.quantity", minimum=1)
                _money(position.get("average_price"), f"baseline position {ticker}.average_price", minimum=YEN)
        except ValueError as error:
            errors.append(str(error))

    events = payload.get("fill_events")
    if not isinstance(events, list):
        errors.append("fill_events is missing or not a list")
        events = []
    event_ids: set[str] = set()
    client_ids: set[str] = set()
    previous_event_at: datetime | None = None
    for index, event in enumerate(events):
        prefix = f"fill_events[{index}]"
        if not isinstance(event, Mapping):
            errors.append(f"{prefix} is not an object")
            continue
        try:
            if event.get("schema_version") != 1:
                raise ValueError(f"{prefix}.schema_version must be 1")
            event_id = event.get("event_id")
            client_id = event.get("client_order_id")
            if not isinstance(event_id, str) or not event_id:
                raise ValueError(f"{prefix}.event_id is missing")
            if event_id in event_ids:
                raise ValueError(f"duplicate fill event id: {event_id}")
            event_ids.add(event_id)
            if not isinstance(client_id, str) or not client_id:
                raise ValueError(f"{prefix}.client_order_id is missing")
            if client_id in client_ids:
                raise ValueError(f"duplicate fill client order id: {client_id}")
            client_ids.add(client_id)
            if event.get("broker_name") != "PAPER" or event.get("commission_source") != "BROKER_RESULT":
                raise ValueError(f"{prefix} has an untrusted broker/cost source")
            if event.get("side") not in {"BUY", "SELL"}:
                raise ValueError(f"{prefix}.side is invalid")
            quantity = _strict_int(event.get("filled_quantity"), f"{prefix}.filled_quantity", minimum=1)
            eligible_quantity = _strict_int(
                event.get("economics_eligible_quantity"),
                f"{prefix}.economics_eligible_quantity",
                minimum=0,
            )
            if eligible_quantity > quantity:
                raise ValueError(f"{prefix}.economics_eligible_quantity exceeds fill quantity")
            for name in (
                "requested_price", "filled_price", "gross_amount_yen",
                "commission_yen", "cost_basis_released_yen",
                "economics_eligible_commission_yen", "adverse_slippage_yen",
            ):
                _money(event.get(name), f"{prefix}.{name}", minimum=Decimal(0))
            for name in (
                "cash_delta_yen", "realized_pnl_before_commission_yen",
                "economics_eligible_realized_pnl_before_commission_yen",
            ):
                _money(event.get(name), f"{prefix}.{name}")
            created_at = _parse_datetime(event.get("created_at"), f"{prefix}.created_at")
            if baseline_at is not None and created_at < baseline_at:
                raise ValueError(f"{prefix}.created_at predates the Step19 baseline")
            if previous_event_at is not None and created_at < previous_event_at:
                raise ValueError(f"{prefix}.created_at is not chronological")
            if updated_at is not None and created_at > updated_at:
                raise ValueError(f"{prefix}.created_at is later than broker updated_at")
            if now is not None:
                checked_now = now if now.tzinfo is not None else now.replace(tzinfo=JST)
                if created_at > checked_now.astimezone(JST):
                    raise ValueError(f"{prefix}.created_at is in the future")
            previous_event_at = created_at
            digest = event.get("event_sha256")
            if not isinstance(digest, str) or digest != _canonical_sha256(event):
                raise ValueError(f"{prefix}.event_sha256 does not match content")
        except (ValueError, TypeError) as error:
            errors.append(str(error))

    try:
        processed = payload.get("processed_client_order_ids")
        if not isinstance(processed, list) or any(not isinstance(value, str) for value in processed):
            raise ValueError("processed_client_order_ids must be a list of strings")
        baseline_ids = baseline.get("processed_client_order_ids", []) if isinstance(baseline, Mapping) else []
        expected = set(baseline_ids) | client_ids
        if set(processed) != expected or len(processed) != len(expected):
            raise ValueError("processed order ids do not reconcile with baseline plus fill events")
        baseline_cash = _money(baseline.get("cash_yen"), "baseline cash")
        current_cash = _money(payload.get("cash_yen"), "current cash")
        expected_cash = baseline_cash + sum(
            (_money(event.get("cash_delta_yen"), "event cash delta") for event in events if isinstance(event, Mapping)),
            Decimal(0),
        )
        if current_cash != expected_cash.quantize(YEN, rounding=ROUND_HALF_UP):
            raise ValueError("cash does not reconcile with baseline plus fill events")
        baseline_realized = _money(baseline.get("realized_pnl_yen"), "baseline realized pnl")
        expected_realized = baseline_realized
        for event in events:
            if isinstance(event, Mapping) and event.get("side") == "SELL":
                expected_realized += _money(event.get("realized_pnl_before_commission_yen"), "event realized pnl")
                expected_realized -= _money(event.get("commission_yen"), "event commission")
        current_realized = _money(payload.get("realized_pnl_yen"), "current realized pnl")
        if current_realized != expected_realized.quantize(YEN, rounding=ROUND_HALF_UP):
            raise ValueError("realized P&L does not reconcile with baseline plus fill events")
    except (ValueError, TypeError) as error:
        errors.append(str(error))

    return {"status": "READY" if not errors else "NOT_READY", "errors": errors}


def _months_inclusive(start: datetime, end: datetime) -> int:
    if end < start:
        raise ValueError("Accounting baseline is in the future")
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _percentile(values: list[Decimal], percentile: Decimal) -> Decimal:
    if not values:
        return Decimal(0)
    ordered = sorted(values)
    rank = int(math.ceil(float(percentile * len(ordered)))) - 1
    return ordered[max(0, min(rank, len(ordered) - 1))]


def build_economics_report(
    broker_state: Mapping[str, Any],
    settings: Mapping[str, Any],
    now: datetime | None = None,
    *,
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(JST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    else:
        now = now.astimezone(JST)
    values = _validate_step19_settings(settings, evidence_root=evidence_root)
    verification = verify_broker_economics_state(broker_state, now=now)
    events = broker_state.get("fill_events", []) if isinstance(broker_state, Mapping) else []
    if not isinstance(events, list):
        events = []

    eligible_realized = Decimal(0)
    eligible_commission = Decimal(0)
    adverse_values: list[Decimal] = []
    modeled_slippage_reserve = Decimal(0)
    modeled_commission = Decimal(0)
    taxable_realized_by_year: dict[str, Decimal] = {}
    tracked_fill_event_ids: list[str] = []
    tracked_fill_evidence: list[dict[str, Any]] = []
    tracked_buy_fills = 0
    tracked_sell_fills = 0
    for event in events:
        if not isinstance(event, Mapping):
            continue
        try:
            eligible_quantity = _strict_int(event.get("economics_eligible_quantity"), "eligible quantity")
            if eligible_quantity <= 0:
                continue
            eligible_commission += _money(event.get("economics_eligible_commission_yen"), "eligible commission")
            adverse = _money(event.get("adverse_slippage_yen"), "adverse slippage", minimum=Decimal(0))
            adverse_values.append(adverse)
            quantity = _strict_int(event.get("filled_quantity"), "filled quantity", minimum=1)
            eligible_gross = (
                _money(event.get("gross_amount_yen"), "gross amount", minimum=Decimal(0))
                * Decimal(eligible_quantity)
                / Decimal(quantity)
            )
            modeled_slippage_reserve += (
                eligible_gross * values["slippage_bps"] / Decimal("10000")
            )
            if values["account_plan"] == "SUPER_DISCOUNT":
                modeled_commission += _rakuten_super_discount_fee(eligible_gross)
            elif values["account_plan"] == "ZERO_COURSE" and values["commission_verified"]:
                modeled_commission += Decimal(0)
            event_id = event.get("event_id")
            if isinstance(event_id, str) and event_id:
                tracked_fill_event_ids.append(event_id)
                tracked_fill_evidence.append({
                    "economics_fill_id": event_id,
                    "broker_order_id": event.get("broker_order_id"),
                    "client_order_id": event.get("client_order_id"),
                    "ticker": event.get("ticker"),
                    "side": event.get("side"),
                    "quantity": event.get("filled_quantity"),
                    "created_at": event.get("created_at"),
                    "broker_fill_event_sha256": event.get("event_sha256"),
                })
            if event.get("side") == "BUY":
                tracked_buy_fills += 1
            elif event.get("side") == "SELL":
                tracked_sell_fills += 1
                realized = _money(
                    event.get("economics_eligible_realized_pnl_before_commission_yen"),
                    "eligible realized pnl",
                )
                eligible_realized += realized
                created_at = _parse_datetime(event.get("created_at"), "eligible fill created_at")
                year = str(created_at.year)
                taxable_realized_by_year[year] = taxable_realized_by_year.get(year, Decimal(0)) + realized
        except ValueError:
            continue

    adverse_total = sum(adverse_values, Decimal(0)).quantize(YEN, rounding=ROUND_HALF_UP)
    modeled_slippage_reserve = modeled_slippage_reserve.quantize(YEN, rounding=ROUND_HALF_UP)
    eligible_commission = eligible_commission.quantize(YEN, rounding=ROUND_HALF_UP)
    eligible_realized = eligible_realized.quantize(YEN, rounding=ROUND_HALF_UP)
    modeled_commission = modeled_commission.quantize(YEN, rounding=ROUND_HALF_UP)
    eligible_fill_count = tracked_buy_fills + tracked_sell_fills
    unverified_fee_reserve = (
        values["fallback_fee"] * eligible_fill_count
    ).quantize(YEN, rounding=ROUND_HALF_UP)
    commission_cost_used = (
        max(eligible_commission, modeled_commission)
        if values["commission_verified"]
        else max(eligible_commission, unverified_fee_reserve)
    )
    # Realized P&L already uses the actual fill price, so actual/model slippage is
    # retained as execution-quality evidence and must not be charged a second time.
    slippage_cost_used = Decimal(0)
    strategy_net = (eligible_realized - commission_cost_used).quantize(
        YEN, rounding=ROUND_HALF_UP
    )

    baseline = broker_state.get("economics_baseline", {}) if isinstance(broker_state, Mapping) else {}
    months = 1
    month_error: str | None = None
    if isinstance(baseline, Mapping) and baseline.get("established_at"):
        try:
            months = _months_inclusive(_parse_datetime(baseline.get("established_at"), "baseline"), now)
        except ValueError as error:
            month_error = str(error)
    fixed_cost = (values["fixed"] * months).quantize(YEN, rounding=ROUND_HALF_UP)
    positive_taxable_by_year = {
        year: max(Decimal(0), amount).quantize(YEN, rounding=ROUND_HALF_UP)
        for year, amount in sorted(taxable_realized_by_year.items())
    }
    taxable_profit = sum(positive_taxable_by_year.values(), Decimal(0))
    tax_reserve = sum(
        (
            (amount * values["tax_rate"]).quantize(YEN, rounding=ROUND_HALF_UP)
            for amount in positive_taxable_by_year.values()
        ),
        Decimal(0),
    ).quantize(YEN, rounding=ROUND_HALF_UP)
    business_net = (strategy_net - fixed_cost - tax_reserve).quantize(YEN, rounding=ROUND_HALF_UP)
    preliminary_distributable = max(Decimal(0), business_net)
    preliminary_living = (
        preliminary_distributable * values["living_rate"]
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    preliminary_reinvestment = (
        preliminary_distributable - preliminary_living
    ).quantize(YEN, rounding=ROUND_HALF_UP)

    blockers = list(verification.get("errors", []))
    lineage = {
        "config_sha256": _object_sha256(settings),
        "broker_snapshot_sha256": _object_sha256(broker_state),
        "fill_ledger_sha256": _object_sha256(events),
    }
    if not all(len(value) == 64 for value in lineage.values()):
        blockers.append("Step19 accounting lineage could not be hashed canonically")
    if month_error:
        blockers.append(month_error)
    if not values["commission_verified"]:
        blockers.append("Rakuten cash-equity commission course has not been verified for the account")
    if not values["tax_verified"]:
        blockers.append("Account type and actual tax-withholding treatment have not been verified")
    distribution_blockers = [
        "Month-end broker reconciliation and high-water mark are not finalized",
        "Living-funds transfer remains advisory and requires explicit manual approval",
    ]
    cost_inputs_ready = values["commission_verified"] and values["tax_verified"]
    ledger_ready = (
        verification.get("status") == "READY"
        and month_error is None
        and all(len(value) == 64 for value in lineage.values())
    )
    status = "READY" if ledger_ready and cost_inputs_ready else "NOT_READY"
    distribution_ready = status == "READY" and not distribution_blockers

    return {
        "schema_version": 1,
        "version": "PHOENIX v7 Step19",
        "generated_at": now.isoformat(timespec="seconds"),
        "status": status,
        "distribution_status": "READY" if distribution_ready else "NOT_READY",
        "ledger_integrity_status": verification.get("status", "NOT_READY"),
        "cost_input_status": "READY" if cost_inputs_ready else "NOT_READY",
        "account_reconciliation_status": "READY" if ledger_ready else "NOT_READY",
        "accounting_scope": "POST_STEP19_BASELINE_ONLY",
        "past_fills_reconstructed": False,
        "lineage": lineage,
        "capital_plan": {
            "base_capital_yen": _as_float(values["base"]),
            "conditional_contribution_yen": _as_float(values["addition"]),
            "maximum_funded_capital_yen": _as_float(values["maximum"]),
            "risk_capital_basis_yen": _as_float(values["risk_basis"]),
            "contribution_credited_as_profit_yen": 0.0,
            "automatic_risk_scaling": False,
            "capital_contribution_executed": False,
        },
        "costs": {
            "accounting_months": months,
            "fixed_monthly_operating_cost_yen": _as_float(values["fixed"]),
            "fixed_operating_cost_total_yen": _as_float(fixed_cost),
            "broker_commission_actual_yen": _as_float(eligible_commission),
            "broker_commission_modeled_plan_yen": _as_float(modeled_commission),
            "broker_commission_yen": _as_float(commission_cost_used),
            "unverified_commission_reserve_yen": _as_float(unverified_fee_reserve),
            "commission_cost_used_yen": _as_float(commission_cost_used),
            "adverse_slippage_actual_yen": _as_float(adverse_total),
            "adverse_slippage_yen": _as_float(slippage_cost_used),
            "modeled_slippage_reserve_yen": _as_float(modeled_slippage_reserve),
            "slippage_cost_used_yen": _as_float(slippage_cost_used),
            "slippage_already_reflected_in_fill_pnl": True,
            "adverse_slippage_p95_yen": _as_float(_percentile(adverse_values, Decimal("0.95"))),
            "adverse_slippage_max_yen": _as_float(max(adverse_values, default=Decimal(0))),
            "conservative_tax_reserve_rate": float(values["tax_rate"]),
            "tax_reserve_yen": _as_float(tax_reserve),
            "taxable_profit_by_year_yen": {
                year: _as_float(amount) for year, amount in positive_taxable_by_year.items()
            },
            "unverified_plan_fee_reserve_per_filled_order_yen": _as_float(values["fallback_fee"]),
            "slippage_reserve_bps_per_side": float(values["slippage_bps"]),
            "fixed_cost_hurdle_pct_on_300k": 2.3333,
            "fixed_cost_hurdle_pct_on_500k": 1.4,
        },
        "performance": {
            "tracked_buy_fills": tracked_buy_fills,
            "tracked_sell_fills": tracked_sell_fills,
            "tracked_fill_event_ids": tracked_fill_event_ids,
            "tracked_fill_evidence": tracked_fill_evidence,
            "eligible_realized_pnl_before_costs_yen": _as_float(eligible_realized),
            "strategy_net_realized_pnl_yen": _as_float(strategy_net),
            "business_net_after_all_reserved_costs_yen": _as_float(business_net),
            "unrealized_profit_credited_yen": 0.0,
            "cost_coverage": strategy_net >= fixed_cost,
            "unrecovered_loss_yen": _as_float(max(Decimal(0), -business_net)),
        },
        "distribution": {
            "living_funds_rate": float(values["living_rate"]),
            "maximum_living_funds_rate": float(values["maximum_rate"]),
            "preliminary_distributable_profit_yen": _as_float(preliminary_distributable),
            "preliminary_living_funds_yen": _as_float(preliminary_living),
            "preliminary_reinvestment_yen": _as_float(preliminary_reinvestment),
            "approved_distribution_yen": 0.0,
            "month_end_finalized": False,
            "high_water_mark_reconciled": False,
            "manual_approval_required": True,
            "distribution_executed": False,
            "external_transfer_executed": False,
        },
        "safety": {
            "advisory_only": True,
            "orders_submitted": 0,
            "live_trading_enabled": False,
            "automatic_promotion": False,
            "state_persisted": False,
        },
        "blocking_reasons": blockers,
        "distribution_blocking_reasons": distribution_blockers,
    }


def verify_economics_report(
    root: Path,
    config: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, list[str]]:
    """Rebuild the advisory report from current config and broker evidence."""
    errors: list[str] = []
    settings = config.get("trading_economics", {})
    if not isinstance(settings, Mapping):
        return False, ["trading_economics config is not an object"]
    if not isinstance(report, Mapping):
        return False, ["Trading economics report root is not an object"]
    try:
        generated_at = _parse_datetime(report.get("generated_at"), "economics.generated_at")
        checked_now = now or datetime.now(JST)
        if checked_now.tzinfo is None:
            checked_now = checked_now.replace(tzinfo=JST)
        checked_now = checked_now.astimezone(JST)
        if generated_at > checked_now:
            raise ValueError("Trading economics report was generated in the future")
        if checked_now - generated_at > timedelta(hours=24):
            raise ValueError("Trading economics report is older than 24 hours")
    except ValueError as error:
        return False, [str(error)]

    broker_path = resolve_path(
        root, str(settings.get("broker_state", "state/v7_paper_broker.json"))
    )
    try:
        broker_state = json.loads(broker_path.read_text(encoding="utf-8-sig"))
        if not isinstance(broker_state, dict):
            raise ValueError("Broker state root is not an object")
        if broker_state.get("state_version") == PaperBroker.STATE_VERSION:
            PaperBroker(
                initial_cash_yen=float(broker_state.get("initial_cash_yen", 0)),
                commission_rate=float(broker_state.get("commission_rate", 0)),
                state_file=broker_path,
            )
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        return False, [f"Could not verify economics broker evidence: {type(error).__name__}: {error}"]

    try:
        expected = build_economics_report(
            broker_state,
            settings,
            now=generated_at,
            evidence_root=root,
        )
        if _object_sha256(report) != _object_sha256(expected):
            errors.append("Trading economics report does not match current broker/config evidence")
    except (TypeError, ValueError) as error:
        errors.append(f"Could not rebuild trading economics report: {error}")
    return not errors, errors


def text_report(report: Mapping[str, Any]) -> str:
    capital = report.get("capital_plan", {})
    costs = report.get("costs", {})
    performance = report.get("performance", {})
    distribution = report.get("distribution", {})
    lines = [
        "PHOENIX v7 STEP19 TRADING ECONOMICS AND COST GATE",
        "=" * 94,
        f"Status                         : {report.get('status', '')}",
        f"Distribution status            : {report.get('distribution_status', '')}",
        f"Ledger integrity               : {report.get('ledger_integrity_status', '')}",
        f"Cost inputs                    : {report.get('cost_input_status', '')}",
        f"Accounting scope               : {report.get('accounting_scope', '')}",
        "-" * 94,
        f"Capital plan                   : {capital.get('base_capital_yen', 0):,.0f} + {capital.get('conditional_contribution_yen', 0):,.0f} = {capital.get('maximum_funded_capital_yen', 0):,.0f} JPY",
        f"Risk capital basis             : {capital.get('risk_capital_basis_yen', 0):,.0f} JPY (no automatic scaling)",
        f"Fixed operating cost           : {costs.get('fixed_monthly_operating_cost_yen', 0):,.0f} JPY/month",
        f"Commission actual / used       : {costs.get('broker_commission_actual_yen', 0):,.2f} / {costs.get('commission_cost_used_yen', 0):,.2f} JPY",
        f"Slippage actual / extra charge : {costs.get('adverse_slippage_actual_yen', 0):,.2f} / {costs.get('slippage_cost_used_yen', 0):,.2f} JPY",
        f"Conservative tax reserve       : {costs.get('tax_reserve_yen', 0):,.2f} JPY ({float(costs.get('conservative_tax_reserve_rate', 0)) * 100:.3f}%)",
        "-" * 94,
        f"Realized P&L before costs      : {performance.get('eligible_realized_pnl_before_costs_yen', 0):+,.2f} JPY",
        f"Strategy net realized P&L      : {performance.get('strategy_net_realized_pnl_yen', 0):+,.2f} JPY",
        f"Business net after all reserve : {performance.get('business_net_after_all_reserved_costs_yen', 0):+,.2f} JPY",
        f"Preliminary living funds       : {distribution.get('preliminary_living_funds_yen', 0):,.2f} JPY",
        f"Approved / transferred         : {distribution.get('approved_distribution_yen', 0):,.2f} / 0 JPY",
        "-" * 94,
        "Blocking reasons:",
    ]
    lines.extend([f"  - {value}" for value in report.get("blocking_reasons", [])] or ["  - None"])
    lines.extend(["Distribution blockers:"])
    lines.extend(
        [f"  - {value}" for value in report.get("distribution_blocking_reasons", [])]
        or ["  - None"]
    )
    lines.extend([
        "-" * 94,
        "No live order, capital transfer, risk scaling, or living-funds transfer is performed.",
        "=" * 94,
        "",
    ])
    return "\n".join(lines)


def run_trading_economics(
    root: Path,
    config: Mapping[str, Any],
    *,
    now: datetime | None = None,
    persist_state: bool = False,
) -> dict[str, Any]:
    settings = config.get("trading_economics", {})
    if not isinstance(settings, Mapping):
        raise ValueError("trading_economics config must be an object")
    broker_path = resolve_path(root, str(settings.get("broker_state", "state/v7_paper_broker.json")))
    load_errors: list[str] = []
    broker_state: dict[str, Any] = {}
    if not broker_path.is_file():
        load_errors.append(f"Required broker state not found: {broker_path}")
    else:
        try:
            value = json.loads(broker_path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("Broker state root is not an object")
            broker_state = value
            if broker_state.get("state_version") == PaperBroker.STATE_VERSION:
                PaperBroker(
                    initial_cash_yen=float(broker_state.get("initial_cash_yen", 0)),
                    commission_rate=float(broker_state.get("commission_rate", 0)),
                    state_file=broker_path,
                )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            load_errors.append(f"Could not read broker state: {type(error).__name__}: {error}")
    report = build_economics_report(
        broker_state,
        settings,
        now=now,
        evidence_root=root,
    )
    if load_errors:
        report["status"] = "NOT_READY"
        report["ledger_integrity_status"] = "NOT_READY"
        report["account_reconciliation_status"] = "NOT_READY"
        report["blocking_reasons"] = load_errors + list(report.get("blocking_reasons", []))
    report["safety"]["state_persisted"] = False
    report["requested_state_persistence"] = bool(persist_state)
    json_path = resolve_path(root, str(settings.get("report_json", "reports/v7_trading_economics.json")))
    text_path = resolve_path(root, str(settings.get("report_text", "reports/v7_trading_economics.txt")))
    atomic_write(json_path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    atomic_write(text_path, text_report(report))
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    return report


def print_economics_summary(report: Mapping[str, Any]) -> None:
    costs = report.get("costs", {})
    performance = report.get("performance", {})
    print("=" * 80)
    print("PHOENIX v7 STEP19 TRADING ECONOMICS")
    print("=" * 80)
    print(f"Status       : {report.get('status', '')}")
    print(f"Ledger       : {report.get('ledger_integrity_status', '')}")
    print(f"Fixed/month  : {costs.get('fixed_monthly_operating_cost_yen', 0):,.0f} JPY")
    print(f"Net business : {performance.get('business_net_after_all_reserved_costs_yen', 0):+,.2f} JPY")
    print(f"Live enabled : {report.get('safety', {}).get('live_trading_enabled', False)}")
    print(f"Report       : {report.get('report_text', '')}")
    print("=" * 80)
