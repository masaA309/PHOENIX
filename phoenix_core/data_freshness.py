from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from typing import Any, Iterable


JST = timezone(timedelta(hours=9))
JPX_EQUITIES_CLOSE = time(15, 30)
JPX_CALENDAR_SOURCE_URL = "https://www.jpx.co.jp/english/corporate/about-jpx/calendar/"
EXPECTED_NIKKEI225_COUNT = 225

# JPX publishes the cash-equities market holidays.  Keep the calendar finite and
# fail closed outside the reviewed range instead of guessing future holidays.
_JPX_MARKET_HOLIDAYS: dict[int, tuple[str, ...]] = {
    2025: (
        "2025-01-01", "2025-01-02", "2025-01-03", "2025-01-13",
        "2025-02-11", "2025-02-23", "2025-02-24", "2025-03-20",
        "2025-04-29", "2025-05-03", "2025-05-04", "2025-05-05",
        "2025-05-06", "2025-07-21", "2025-08-11", "2025-09-15",
        "2025-09-23", "2025-10-13", "2025-11-03", "2025-11-23",
        "2025-11-24", "2025-12-31",
    ),
    2026: (
        "2026-01-01", "2026-01-02", "2026-01-03", "2026-01-12",
        "2026-02-11", "2026-02-23", "2026-03-20", "2026-04-29",
        "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06",
        "2026-07-20", "2026-08-11", "2026-09-21", "2026-09-22",
        "2026-09-23", "2026-10-12", "2026-11-03", "2026-11-23",
        "2026-12-31",
    ),
    2027: (
        "2027-01-01", "2027-01-02", "2027-01-03", "2027-01-11",
        "2027-02-11", "2027-02-23", "2027-03-21", "2027-03-22",
        "2027-04-29", "2027-05-03", "2027-05-04", "2027-05-05",
        "2027-07-19", "2027-08-11", "2027-09-20", "2027-09-23",
        "2027-10-11", "2027-11-03", "2027-11-23", "2027-12-31",
    ),
}


def _calendar_sha256() -> str:
    canonical = json.dumps(
        {str(year): list(values) for year, values in sorted(_JPX_MARKET_HOLIDAYS.items())},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return sha256(canonical).hexdigest()


JPX_CALENDAR_SHA256 = _calendar_sha256()


def ticker_universe_sha256(values: Iterable[Any]) -> str:
    tickers = [str(value).strip() for value in values]
    if any(not value for value in tickers):
        raise ValueError("ticker universe contains an empty ticker")
    if len(tickers) != len(set(tickers)):
        raise ValueError("ticker universe contains duplicates")
    canonical = json.dumps(
        sorted(tickers), ensure_ascii=True, separators=(",", ":")
    ).encode("ascii")
    return sha256(canonical).hexdigest()


def parse_market_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        raise ValueError("market data date is missing")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError as error:
        raise ValueError(f"invalid market data date: {text}") from error


def _as_jst(value: datetime | date | None) -> datetime:
    if value is None:
        return datetime.now(JST)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=JST)
        return value.astimezone(JST)
    return datetime.combine(value, time(8, 0), tzinfo=JST)


def is_jpx_equities_trading_day(value: date) -> bool:
    holidays = _JPX_MARKET_HOLIDAYS.get(value.year)
    if holidays is None:
        supported = f"{min(_JPX_MARKET_HOLIDAYS)}-{max(_JPX_MARKET_HOLIDAYS)}"
        raise ValueError(
            f"JPX calendar does not cover {value.year}; reviewed range is {supported}"
        )
    return value.weekday() < 5 and value.isoformat() not in holidays


def latest_completed_jpx_trading_date(
    as_of: datetime | date | None = None,
) -> date:
    checked = _as_jst(as_of)
    candidate = checked.date()
    if checked.timetz().replace(tzinfo=None) < JPX_EQUITIES_CLOSE:
        candidate -= timedelta(days=1)
    for _ in range(14):
        if is_jpx_equities_trading_day(candidate):
            return candidate
        candidate -= timedelta(days=1)
    raise ValueError("a completed JPX equities session was not found within 14 days")


def verify_market_dates(
    values: Iterable[Any],
    *,
    as_of: datetime | date | None = None,
    expected_date: date | None = None,
) -> dict[str, Any]:
    checked = _as_jst(as_of)
    dates = [parse_market_date(value) for value in values]
    if not dates:
        return {
            "status": "NOT_READY",
            "expected_date": None,
            "latest_date": None,
            "oldest_date": None,
            "maximum_age_days": None,
            "calendar_status": "VERIFIED",
            "calendar_source_url": JPX_CALENDAR_SOURCE_URL,
            "calendar_sha256": JPX_CALENDAR_SHA256,
            "blocking_reasons": ["market data dates are missing"],
        }

    blockers: list[str] = []
    try:
        expected = expected_date or latest_completed_jpx_trading_date(checked)
        if expected_date is not None and not is_jpx_equities_trading_day(expected_date):
            blockers.append(
                f"expected market date is not a JPX equities trading day: {expected_date}"
            )
    except ValueError as error:
        expected = None
        blockers.append(str(error))

    future = sorted(value for value in dates if value > checked.date())
    oldest = min(dates)
    latest = max(dates)
    if future:
        blockers.append("market data contains a future date")
    if expected is not None:
        mismatches = sorted({value for value in dates if value != expected})
        if mismatches:
            blockers.append(
                "market data does not match the latest completed JPX session: "
                f"expected={expected.isoformat()} actual="
                + ",".join(item.isoformat() for item in mismatches)
            )

    return {
        "status": "READY" if not blockers else "NOT_READY",
        "expected_date": expected.isoformat() if expected is not None else None,
        "latest_date": latest.isoformat(),
        "oldest_date": oldest.isoformat(),
        "maximum_age_days": (checked.date() - oldest).days,
        "calendar_status": "VERIFIED",
        "calendar_source_url": JPX_CALENDAR_SOURCE_URL,
        "calendar_sha256": JPX_CALENDAR_SHA256,
        "blocking_reasons": blockers,
    }
