from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import ssl
import tempfile
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from phoenix_core.broker import PaperBroker
from phoenix_core.candidate_input_guard import (
    CandidateInputPolicy,
    DECISION_COLUMN,
    EXECUTABLE_DECISIONS,
    EXECUTION_PRICE_COLUMN,
    KNOWN_DECISIONS,
    TSE_TICKER_PATTERN,
    candidate_execution_sha256,
    load_execution_candidates,
)
from phoenix_core.data_freshness import JPX_CALENDAR_SHA256, is_jpx_equities_trading_day
from phoenix_core.models import AccountSnapshot, Position
from phoenix_core.performance_tracker import atomic_write, resolve_path
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    calculate_sizing,
    normalize_candidate_frame,
)


JST = ZoneInfo("Asia/Tokyo")
YEN = Decimal("0.01")
WHOLE_YEN = Decimal("1")
STATE_VERSION = 1
STATE_KIND = "VIRTUAL_RSS_PAPER_LEDGER"
EVIDENCE_KIND = "VIRTUAL_MARKET_FEED_SIMULATION"
CONTRACT_ID = "PHOENIX_VIRTUAL_RSS_PAPER_V1"
QUOTE_SOURCE = "YFINANCE_PUBLIC_5M_UNADJUSTED"
ELIGIBILITY_KIND = "RAKUTEN_KABU_MINI_ELIGIBILITY_MANUAL_EXPORT"
ZERO_HASH = "0" * 64


class VirtualRssError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VirtualQuote:
    ticker: str
    price: float
    event_at: datetime
    received_at: datetime
    source: str = QUOTE_SOURCE
    currency: str = "JPY"
    bid: float | None = None
    ask: float | None = None
    adjusted: bool = False

    def validate(self) -> None:
        if not TSE_TICKER_PATTERN.fullmatch(self.ticker.strip().upper()):
            raise VirtualRssError(f"Invalid TSE ticker: {self.ticker}")
        if self.source != QUOTE_SOURCE or self.currency != "JPY":
            raise VirtualRssError("Virtual quote source/currency is not allowed")
        if self.adjusted is not False:
            raise VirtualRssError("Adjusted prices cannot be used for virtual fills")
        for name, value in (("price", self.price), ("bid", self.bid), ("ask", self.ask)):
            if value is None and name != "price":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise VirtualRssError(f"Quote {name} must be a finite positive number")
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise VirtualRssError(f"Quote {name} must be a finite positive number")
        if (self.bid is None) != (self.ask is None):
            raise VirtualRssError("Virtual quote bid and ask must be supplied together")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise VirtualRssError("Virtual quote bid cannot exceed ask")
        if (
            self.bid is not None
            and self.ask is not None
            and not float(self.bid) <= float(self.price) <= float(self.ask)
        ):
            raise VirtualRssError("Virtual quote last price must remain inside bid/ask")
        for name, value in (("event_at", self.event_at), ("received_at", self.received_at)):
            if value.utcoffset() != timedelta(hours=9):
                raise VirtualRssError(f"{name} must have an explicit +09:00 offset")

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "ticker": self.ticker.strip().upper(),
            "price": round(float(self.price), 4),
            "bid": None if self.bid is None else round(float(self.bid), 4),
            "ask": None if self.ask is None else round(float(self.ask), 4),
            "event_at": self.event_at.isoformat(timespec="seconds"),
            "received_at": self.received_at.isoformat(timespec="seconds"),
            "source": self.source,
            "currency": self.currency,
            "adjusted": False,
            "quote_kind": "MEASURED_LAST_WITH_OPTIONAL_BID_ASK",
        }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strict_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise VirtualRssError(f"{name} must be an integer >= {minimum}")
    return value


def _decimal(value: Any, name: str, *, minimum: Decimal | None = None) -> Decimal:
    if isinstance(value, bool):
        raise VirtualRssError(f"{name} must be numeric")
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise VirtualRssError(f"{name} must be numeric") from error
    if not result.is_finite() or (minimum is not None and result < minimum):
        raise VirtualRssError(f"{name} is outside the allowed range")
    return result


def _jst_datetime(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise VirtualRssError(f"{name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise VirtualRssError(f"{name} must be an ISO timestamp") from error
    if parsed.utcoffset() != timedelta(hours=9):
        raise VirtualRssError(f"{name} must have an explicit +09:00 offset")
    return parsed


def _safe_repo_path(root: Path, value: str, allowed_parent: str) -> Path:
    repository = root.resolve()
    expected_parent = (repository / allowed_parent).resolve()
    path = resolve_path(repository, value)
    absolute = path.absolute()
    resolved = path.resolve(strict=False)
    if os.path.normcase(str(absolute)) != os.path.normcase(str(resolved)):
        raise VirtualRssError(f"Path aliases are forbidden: {path}")
    try:
        resolved.relative_to(expected_parent)
    except ValueError as error:
        raise VirtualRssError(f"Path must remain below {allowed_parent}: {path}") from error
    return path


def _load_json_object(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise VirtualRssError(f"Could not read {name}: {path}") from error
    if not isinstance(value, dict):
        raise VirtualRssError(f"{name} root must be an object")
    return value


def _validate_settings_contract(settings: Mapping[str, Any]) -> None:
    fixed_paths = {
        "policy_file": "config/v7_virtual_rss_policy.json",
        "direct_pipeline_config": "config/v7_direct_pipeline_config.json",
        "runtime_root": "runtime/v7_virtual_rss",
        "source_paper_state": "state/v7_paper_broker.json",
        "state_file": "state/v7_virtual_rss_paper.json",
        "lock_file": "state/v7_virtual_rss_paper.lock",
        "kabumini_eligibility_file": "state/rakuten_kabumini_eligibility.json",
        "report_json": "reports/v7_virtual_rss_paper.json",
        "report_text": "reports/v7_virtual_rss_paper.txt",
        "notification_preview_json": "reports/v7_virtual_trade_notification_preview.json",
        "notification_preview_text": "reports/v7_virtual_trade_notification_preview.txt",
    }
    for name, expected in fixed_paths.items():
        if type(settings.get(name)) is not str or settings.get(name) != expected:
            raise VirtualRssError(f"virtual_rss_paper.{name} must be {expected}")
    if len(set(fixed_paths.values())) != len(fixed_paths):
        raise VirtualRssError("Virtual RSS dedicated paths must be distinct")


def _validate_policy_payload(policy: Mapping[str, Any]) -> None:
    fixed = {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "evidence_kind": EVIDENCE_KIND,
        "virtual_only": True,
        "eligible_for_real_rss_gate": False,
        "orders_allowed": False,
        "external_notifications_allowed": False,
    }
    for key, wanted in fixed.items():
        if type(wanted) is bool:
            valid = policy.get(key) is wanted
        else:
            valid = type(policy.get(key)) is type(wanted) and policy.get(key) == wanted
        if not valid:
            raise VirtualRssError(f"Virtual RSS policy has invalid {key}")
    quote = policy.get("quote_feed")
    unit = policy.get("standard_unit")
    mini = policy.get("kabumini")
    economics = policy.get("economics")
    if not all(isinstance(value, dict) for value in (quote, unit, mini, economics)):
        raise VirtualRssError("Virtual RSS policy sections are incomplete")
    exact_values = (
        (quote, "source", QUOTE_SOURCE),
        (quote, "currency", "JPY"),
        (quote, "period", "1d"),
        (quote, "interval", "5m"),
        (quote, "maximum_quote_age_seconds", 900),
        (quote, "maximum_future_skew_seconds", 2),
        (quote, "maximum_measured_bid_ask_spread_bps", 100),
        (quote, "synthetic_quote_half_spread_bps", 10),
        (quote, "synthetic_bid_ask_is_measured", False),
        (unit, "route", "TSE_STANDARD_UNIT_SIM"),
        (unit, "lot_size", 100),
        (unit, "commission_plan", "UNVERIFIED_CONSERVATIVE_RESERVE"),
        (unit, "commission_reserve_per_fill_yen", 1070),
        (unit, "adverse_slippage_bps_per_side", 5),
        (mini, "route", "RAKUTEN_KABU_MINI_SIM"),
        (mini, "minimum_quantity", 1),
        (mini, "maximum_quantity", 99),
        (mini, "buy_commission_yen", 0),
        (mini, "sell_commission_yen", 0),
        (mini, "realtime_spread_bps_per_side", 22),
        (mini, "adverse_slippage_bps_per_side", 5),
        (mini, "buy_rounding", "CEILING_TO_WHOLE_YEN"),
        (mini, "sell_rounding", "FLOOR_TO_WHOLE_YEN"),
        (mini, "morning_session", "09:00-11:30"),
        (mini, "afternoon_session", "12:30-15:25"),
        (mini, "current_eligibility_evidence_required", True),
        (mini, "maximum_eligibility_age_days", 7),
        (economics, "initial_risk_capital_yen", 300000),
        (economics, "conditional_contribution_yen", 200000),
        (economics, "automatic_contribution", False),
        (economics, "fixed_monthly_operating_cost_yen", 7000),
        (economics, "assumed_trading_days_per_month", 20),
        (economics, "tax_reserve_rate", 0.20315),
        (economics, "living_funds_rate", 0.20),
        (economics, "maximum_living_funds_rate", 0.30),
        (economics, "living_funds_manual_approval_required", True),
    )
    for section, key, wanted in exact_values:
        value = section.get(key)
        if type(wanted) is bool:
            valid = value is wanted
        else:
            valid = type(value) is type(wanted) and value == wanted
        if not valid:
            raise VirtualRssError(f"Virtual RSS policy value is invalid: {key}")


def load_policy(root: Path, settings: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    expected = {
        "enabled": True,
        "advisory_only": True,
        "virtual_only": True,
        "orders_allowed": False,
        "external_notifications_allowed": False,
        "automatic_funding": False,
    }
    for key, wanted in expected.items():
        if settings.get(key) is not wanted:
            raise VirtualRssError(f"virtual_rss_paper.{key} must be {wanted!r}")
    _validate_settings_contract(settings)
    policy_path = _safe_repo_path(
        root, str(settings.get("policy_file", "")), "config"
    )
    if not policy_path.is_file():
        raise VirtualRssError("Virtual RSS reviewed policy is missing")
    digest = _file_sha256(policy_path)
    expected_digest = str(settings.get("policy_sha256", "")).lower()
    if digest != expected_digest:
        raise VirtualRssError("Virtual RSS reviewed policy hash does not match config")
    policy = _load_json_object(policy_path, "virtual RSS policy")
    _validate_policy_payload(policy)
    return policy, digest


def _policy_section(policy: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = policy.get(name)
    if not isinstance(value, Mapping):
        raise VirtualRssError(f"Policy section is missing: {name}")
    return value


def modeled_fill(
    quote: VirtualQuote,
    side: str,
    route: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    quote.validate()
    normalized_side = side.strip().upper()
    if normalized_side not in ("BUY", "SELL"):
        raise VirtualRssError("Virtual fill side must be BUY or SELL")
    if route not in ("TSE_STANDARD_UNIT_SIM", "RAKUTEN_KABU_MINI_SIM"):
        raise VirtualRssError("Unknown virtual route")
    measured_book = quote.bid is not None and quote.ask is not None
    feed = _policy_section(policy, "quote_feed")
    half_spread = Decimal(str(feed["synthetic_quote_half_spread_bps"])) / Decimal(10000)
    last = _decimal(quote.price, "quote price", minimum=Decimal("0.0001"))
    if normalized_side == "BUY":
        book_reference = _decimal(quote.ask, "quote ask") if measured_book else last * (1 + half_spread)
    else:
        book_reference = _decimal(quote.bid, "quote bid") if measured_book else last * (1 - half_spread)
    section_name = "standard_unit" if route == "TSE_STANDARD_UNIT_SIM" else "kabumini"
    route_policy = _policy_section(policy, section_name)
    slippage = Decimal(str(route_policy["adverse_slippage_bps_per_side"])) / Decimal(10000)
    product_spread = (
        Decimal(str(route_policy["realtime_spread_bps_per_side"])) / Decimal(10000)
        if route == "RAKUTEN_KABU_MINI_SIM"
        else Decimal(0)
    )
    total_rate = slippage + product_spread
    if normalized_side == "BUY":
        unrounded = book_reference * (1 + total_rate)
    else:
        unrounded = book_reference * (1 - total_rate)
    if route == "RAKUTEN_KABU_MINI_SIM":
        rounding = ROUND_CEILING if normalized_side == "BUY" else ROUND_FLOOR
        filled = unrounded.quantize(WHOLE_YEN, rounding=rounding)
        commission = Decimal(str(route_policy[
            "buy_commission_yen" if normalized_side == "BUY" else "sell_commission_yen"
        ]))
    else:
        filled = unrounded.quantize(YEN, rounding=ROUND_HALF_UP)
        commission = Decimal(str(route_policy["commission_reserve_per_fill_yen"]))
    adverse = abs(filled - last).quantize(YEN, rounding=ROUND_HALF_UP)
    return {
        "side": normalized_side,
        "route": route,
        "last_price_yen": float(last),
        "book_reference_yen": float(book_reference.quantize(YEN, rounding=ROUND_HALF_UP)),
        "filled_price_yen": float(filled),
        "commission_yen": float(commission),
        "product_spread_bps": float(product_spread * Decimal(10000)),
        "slippage_reserve_bps": float(slippage * Decimal(10000)),
        "synthetic_quote_half_spread_bps": 0.0 if measured_book else float(half_spread * Decimal(10000)),
        "book_price_measured": measured_book,
        "adverse_price_difference_per_share_yen": float(adverse),
        "costs_embedded_in_fill_price": True,
    }


def _quote_frame_for_ticker(data: pd.DataFrame, ticker: str, count: int) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        level0 = {str(value) for value in data.columns.get_level_values(0)}
        level1 = {str(value) for value in data.columns.get_level_values(1)}
        if ticker in level0:
            return data[ticker]
        if ticker in level1:
            return data.xs(ticker, axis=1, level=1)
        return pd.DataFrame()
    return data if count == 1 else pd.DataFrame()


def _quote_environment_failure(code: str, remediation: str) -> dict[str, Any]:
    return {
        "status": "FAILED",
        "code": code,
        "tls_verification_enabled": True,
        "ca_bundle_mode": "UNAVAILABLE",
        "ca_bundle_sha256": "",
        "remediation": remediation,
    }


def prepare_quote_environment() -> tuple[dict[str, Any], Path | None]:
    try:
        import certifi
    except (ImportError, OSError):
        return _quote_environment_failure(
            "QUOTE_DEPENDENCY_MISSING",
            "INSTALL_PINNED_STEP21_DEPENDENCIES",
        ), None
    for module_name in ("curl_cffi", "yfinance"):
        if importlib.util.find_spec(module_name) is None:
            return _quote_environment_failure(
                "QUOTE_DEPENDENCY_MISSING",
                "INSTALL_PINNED_STEP21_DEPENDENCIES",
            ), None

    source_kind = "CERTIFI"
    source_value = ""
    for environment_name in ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE"):
        configured = os.environ.get(environment_name, "").strip()
        if configured:
            source_kind = environment_name
            source_value = configured
            break
    if not source_value:
        try:
            source_value = certifi.where()
        except (AttributeError, OSError):
            return _quote_environment_failure(
                "TLS_CA_BUNDLE_MISSING",
                "REINSTALL_CERTIFI_ACTIVE_VENV",
            ), None
    source = Path(source_value).expanduser()
    if not source.is_file():
        remediation = (
            "FIX_OR_UNSET_CA_BUNDLE_ENV"
            if source_kind != "CERTIFI"
            else "REINSTALL_CERTIFI_ACTIVE_VENV"
        )
        return _quote_environment_failure("TLS_CA_BUNDLE_MISSING", remediation), None
    try:
        content = source.read_bytes()
    except OSError:
        return _quote_environment_failure(
            "TLS_CA_BUNDLE_UNREADABLE",
            "MOVE_VENV_OUTSIDE_ONEDRIVE_OR_REINSTALL_CERTIFI",
        ), None
    if len(content) < 1024 or b"-----BEGIN CERTIFICATE-----" not in content:
        return _quote_environment_failure(
            "TLS_CA_BUNDLE_INVALID",
            "REINSTALL_CERTIFI_ACTIVE_VENV",
        ), None

    digest = hashlib.sha256(content).hexdigest()
    local_root = Path(tempfile.gettempdir()) / "phoenix_v7_virtual_rss_ca"
    local_bundle = local_root / f"cacert-{digest}.pem"
    try:
        if not local_bundle.is_file() or hashlib.sha256(local_bundle.read_bytes()).hexdigest() != digest:
            atomic_write(local_bundle, content.decode("ascii"))
        if hashlib.sha256(local_bundle.read_bytes()).hexdigest() != digest:
            raise OSError("materialized CA bundle hash mismatch")
        ssl.create_default_context(cafile=str(local_bundle))
    except (OSError, UnicodeDecodeError, ssl.SSLError):
        return _quote_environment_failure(
            "TLS_CA_BUNDLE_MATERIALIZATION_FAILED",
            "MOVE_VENV_OUTSIDE_ONEDRIVE_OR_REINSTALL_CERTIFI",
        ), None
    return {
        "status": "READY",
        "code": "READY",
        "tls_verification_enabled": True,
        "ca_bundle_mode": "LOCAL_MATERIALIZED_COPY",
        "ca_bundle_source": source_kind,
        "ca_bundle_sha256": digest,
        "remediation": "NONE",
    }, local_bundle


def check_quote_environment() -> dict[str, Any]:
    environment, _ = prepare_quote_environment()
    return environment


@contextmanager
def _temporary_ca_environment(ca_bundle: Path):
    names = ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE")
    previous = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ[name] = str(ca_bundle)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def fetch_yfinance_quotes(
    tickers: Iterable[str], *, received_at: datetime | None = None,
    cache_directory: Path | None = None,
) -> tuple[dict[str, VirtualQuote], list[str], dict[str, Any]]:
    normalized = sorted({str(value).strip().upper() for value in tickers})
    if not normalized:
        return {}, [], {"status": "EMPTY", "source": QUOTE_SOURCE}
    for ticker in normalized:
        if not TSE_TICKER_PATTERN.fullmatch(ticker):
            raise VirtualRssError(f"Invalid quote ticker: {ticker}")
    checked_at = received_at or datetime.now(JST)
    if checked_at.utcoffset() != timedelta(hours=9):
        raise VirtualRssError("received_at must have an explicit +09:00 offset")
    environment, ca_bundle = prepare_quote_environment()
    if ca_bundle is None:
        return {}, [str(environment["code"])], {
            "status": "FAILED",
            "source": QUOTE_SOURCE,
            "currency": "JPY",
            "adjusted": False,
            "received_at": checked_at.isoformat(timespec="seconds"),
            "requested_tickers": normalized,
            "observed_tickers": [],
            "snapshot_sha256": _sha256([]),
            "fallback_used": False,
            "post_requests": 0,
            "environment": environment,
        }
    try:
        with _temporary_ca_environment(ca_bundle):
            import yfinance as yf

            if cache_directory is not None:
                cache_directory.mkdir(parents=True, exist_ok=True)
                yf.set_tz_cache_location(str(cache_directory))

            data = yf.download(
                tickers=normalized,
                period="1d",
                interval="5m",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=30,
            )
    except Exception as error:
        error_code = f"YFINANCE_REQUEST_FAILED:{type(error).__name__}"
        lowered = str(error).lower()
        if "curl: (77)" in lowered or "certificate verify locations" in lowered:
            error_code = "TLS_CA_BUNDLE_UNREADABLE"
            environment = {
                **environment,
                "status": "FAILED",
                "code": error_code,
                "remediation": "MOVE_VENV_OUTSIDE_ONEDRIVE_OR_REINSTALL_CERTIFI",
            }
        return {}, [error_code], {
            "status": "FAILED",
            "source": QUOTE_SOURCE,
            "currency": "JPY",
            "adjusted": False,
            "received_at": checked_at.isoformat(timespec="seconds"),
            "requested_tickers": normalized,
            "observed_tickers": [],
            "snapshot_sha256": _sha256([]),
            "fallback_used": False,
            "post_requests": 0,
            "environment": environment,
        }
    if data is None or data.empty:
        return {}, ["YFINANCE_EMPTY_RESPONSE"], {
            "status": "FAILED",
            "source": QUOTE_SOURCE,
            "currency": "JPY",
            "adjusted": False,
            "received_at": checked_at.isoformat(timespec="seconds"),
            "requested_tickers": normalized,
            "observed_tickers": [],
            "snapshot_sha256": _sha256([]),
            "fallback_used": False,
            "post_requests": 0,
            "environment": environment,
        }
    quotes: dict[str, VirtualQuote] = {}
    errors: list[str] = []
    for ticker in normalized:
        frame = _quote_frame_for_ticker(data, ticker, len(normalized))
        if frame.empty or "Close" not in frame:
            errors.append(f"QUOTE_MISSING:{ticker}")
            continue
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        if close.empty:
            errors.append(f"QUOTE_MISSING:{ticker}")
            continue
        timestamp = pd.Timestamp(close.index[-1])
        if timestamp.tzinfo is None:
            errors.append(f"QUOTE_TIMEZONE_MISSING:{ticker}")
            continue
        event_at = timestamp.tz_convert(JST).to_pydatetime()
        quote = VirtualQuote(
            ticker=ticker,
            price=float(close.iloc[-1]),
            event_at=event_at,
            received_at=checked_at,
        )
        try:
            quote.validate()
        except VirtualRssError as error:
            errors.append(f"QUOTE_INVALID:{ticker}:{error}")
            continue
        quotes[ticker] = quote
    snapshot_rows = [quotes[ticker].as_dict() for ticker in sorted(quotes)]
    return quotes, errors, {
        "status": "OBSERVED" if quotes else "FAILED",
        "source": QUOTE_SOURCE,
        "currency": "JPY",
        "adjusted": False,
        "received_at": checked_at.isoformat(timespec="seconds"),
        "requested_tickers": normalized,
        "observed_tickers": sorted(quotes),
        "snapshot_sha256": _sha256(snapshot_rows),
        "fallback_used": False,
        "post_requests": 0,
        "environment": environment,
    }


def quote_readiness(
    quote: VirtualQuote, now: datetime, policy: Mapping[str, Any], *, mini: bool
) -> tuple[str, list[str]]:
    quote.validate()
    if now.utcoffset() != timedelta(hours=9):
        raise VirtualRssError("now must have an explicit +09:00 offset")
    feed = _policy_section(policy, "quote_feed")
    reasons: list[str] = []
    age = (now - quote.event_at).total_seconds()
    if age < -float(feed["maximum_future_skew_seconds"]):
        reasons.append("FUTURE_QUOTE")
    if age > float(feed["maximum_quote_age_seconds"]):
        reasons.append("STALE_QUOTE")
    try:
        trading_day = is_jpx_equities_trading_day(now.date())
    except ValueError:
        trading_day = False
        reasons.append("JPX_CALENDAR_UNSUPPORTED")
    if not trading_day:
        reasons.append("NOT_JPX_TRADING_DAY")
    current = now.timetz().replace(tzinfo=None)
    event_time = quote.event_at.timetz().replace(tzinfo=None)
    close = time(15, 25) if mini else time(15, 30)
    in_session = time(9, 0) <= current <= time(11, 30) or time(12, 30) <= current <= close
    event_in_session = (
        time(9, 0) <= event_time <= time(11, 30)
        or time(12, 30) <= event_time <= close
    )
    if not in_session:
        reasons.append("OUTSIDE_FILL_SESSION")
    if not event_in_session:
        reasons.append("QUOTE_EVENT_OUTSIDE_FILL_SESSION")
    if quote.event_at.date() != now.date():
        reasons.append("QUOTE_NOT_TODAY")
    if quote.event_at > quote.received_at + timedelta(seconds=float(feed["maximum_future_skew_seconds"])):
        reasons.append("QUOTE_AFTER_RECEIPT")
    if quote.received_at > now + timedelta(seconds=float(feed["maximum_future_skew_seconds"])):
        reasons.append("FUTURE_RECEIPT_TIME")
    if quote.bid is not None and quote.ask is not None:
        midpoint = (Decimal(str(quote.ask)) + Decimal(str(quote.bid))) / Decimal(2)
        measured_spread_bps = (
            (Decimal(str(quote.ask)) - Decimal(str(quote.bid)))
            / midpoint
            * Decimal(10000)
        )
        if measured_spread_bps > Decimal(str(feed["maximum_measured_bid_ask_spread_bps"])):
            reasons.append("MEASURED_SPREAD_TOO_WIDE")
    return ("FILL_READY" if not reasons else "MARK_ONLY"), sorted(set(reasons))


def _quote_from_mapping(value: Any) -> VirtualQuote:
    if not isinstance(value, Mapping):
        raise VirtualRssError("Virtual fill quote lineage must be an object")
    required = {
        "ticker", "price", "bid", "ask", "event_at", "received_at",
        "source", "currency", "adjusted", "quote_kind",
    }
    if set(value) != required or value.get("quote_kind") != "MEASURED_LAST_WITH_OPTIONAL_BID_ASK":
        raise VirtualRssError("Virtual fill quote lineage schema is invalid")
    quote = VirtualQuote(
        ticker=str(value["ticker"]),
        price=float(_decimal(value["price"], "lineage quote price")),
        bid=None if value["bid"] is None else float(_decimal(value["bid"], "lineage quote bid")),
        ask=None if value["ask"] is None else float(_decimal(value["ask"], "lineage quote ask")),
        event_at=_jst_datetime(value["event_at"], "lineage quote event_at"),
        received_at=_jst_datetime(value["received_at"], "lineage quote received_at"),
        source=str(value["source"]),
        currency=str(value["currency"]),
        adjusted=value["adjusted"],
    )
    quote.validate()
    return quote


def build_eligibility_evidence(
    csv_path: Path, checked_at: datetime, *, source_url: str
) -> dict[str, Any]:
    if checked_at.utcoffset() != timedelta(hours=9):
        raise VirtualRssError("Eligibility checked_at must have an explicit +09:00 offset")
    if source_url != "RAKUTEN_SUPER_SCREENER_MANUAL_EXPORT":
        raise VirtualRssError("Eligibility source must be a reviewed Rakuten Super Screener export")
    try:
        content = csv_path.read_bytes()
        decoded = content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(decoded), strict=True))
    except (OSError, UnicodeError, csv.Error) as error:
        raise VirtualRssError("Could not read Kabu Mini eligibility CSV") from error
    if not rows or set(rows[0]) != {"ticker", "opening_buy_enabled", "realtime_buy_enabled"}:
        raise VirtualRssError("Eligibility CSV columns are invalid")
    tickers: dict[str, dict[str, bool]] = {}
    for row in rows:
        ticker = str(row["ticker"]).strip().upper()
        if not TSE_TICKER_PATTERN.fullmatch(ticker) or ticker in tickers or ticker == "4755.T":
            raise VirtualRssError(f"Invalid/duplicate Kabu Mini ticker: {ticker}")
        flags: dict[str, bool] = {}
        for field in ("opening_buy_enabled", "realtime_buy_enabled"):
            raw = str(row[field]).strip()
            if raw not in ("0", "1"):
                raise VirtualRssError(f"Eligibility flag must be 0 or 1: {field}")
            flags[field] = raw == "1"
        tickers[ticker] = flags
    payload: dict[str, Any] = {
        "schema_version": 1,
        "evidence_kind": ELIGIBILITY_KIND,
        "broker": "RAKUTEN_SECURITIES",
        "source": source_url,
        "checked_at": checked_at.isoformat(timespec="seconds"),
        "input_sha256": hashlib.sha256(content).hexdigest(),
        "tickers": {key: tickers[key] for key in sorted(tickers)},
    }
    payload["evidence_sha256"] = _sha256(payload)
    return payload


def _validate_eligibility_evidence_value(
    raw_value: Mapping[str, Any], now: datetime, policy: Mapping[str, Any]
) -> tuple[dict[str, dict[str, bool]], str]:
    if not isinstance(raw_value, Mapping):
        raise VirtualRssError("Kabu Mini eligibility evidence must be an object")
    value = json.loads(json.dumps(raw_value))
    expected_hash = value.pop("evidence_sha256", None)
    actual_hash = _sha256(value)
    value["evidence_sha256"] = expected_hash
    if expected_hash != actual_hash:
        raise VirtualRssError("Kabu Mini eligibility evidence hash is invalid")
    fixed = {
        "schema_version": 1,
        "evidence_kind": ELIGIBILITY_KIND,
        "broker": "RAKUTEN_SECURITIES",
        "source": "RAKUTEN_SUPER_SCREENER_MANUAL_EXPORT",
    }
    for key, wanted in fixed.items():
        if type(value.get(key)) is not type(wanted) or value.get(key) != wanted:
            raise VirtualRssError(f"Kabu Mini eligibility evidence has invalid {key}")
    checked = _jst_datetime(value.get("checked_at"), "eligibility.checked_at")
    input_hash = value.get("input_sha256")
    if (
        not isinstance(input_hash, str)
        or len(input_hash) != 64
        or any(character not in "0123456789abcdef" for character in input_hash)
    ):
        raise VirtualRssError("Kabu Mini eligibility input hash is invalid")
    maximum_age = _strict_int(
        _policy_section(policy, "kabumini").get("maximum_eligibility_age_days"),
        "maximum_eligibility_age_days", minimum=1,
    )
    tickers = value.get("tickers")
    if not isinstance(tickers, dict) or not tickers:
        raise VirtualRssError("Kabu Mini eligibility ticker map is empty")
    normalized: dict[str, dict[str, bool]] = {}
    for ticker, flags in tickers.items():
        if not TSE_TICKER_PATTERN.fullmatch(str(ticker)) or not isinstance(flags, dict):
            raise VirtualRssError("Kabu Mini eligibility ticker entry is invalid")
        if set(flags) != {"opening_buy_enabled", "realtime_buy_enabled"}:
            raise VirtualRssError("Kabu Mini eligibility flags are invalid")
        if any(flags[key] not in (True, False) or type(flags[key]) is not bool for key in flags):
            raise VirtualRssError("Kabu Mini eligibility flags must be booleans")
        normalized[str(ticker)] = dict(flags)
    if checked > now + timedelta(seconds=2) or now - checked > timedelta(days=maximum_age):
        return {}, "STALE"
    return normalized, "VERIFIED"


def load_eligibility(
    path: Path, now: datetime, policy: Mapping[str, Any]
) -> tuple[dict[str, dict[str, bool]], str]:
    if not path.is_file():
        return {}, "MISSING"
    value = _load_json_object(path, "Kabu Mini eligibility evidence")
    return _validate_eligibility_evidence_value(value, now, policy)


def _state_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("state_sha256", None)
    return _sha256(payload)


def _event_hash(value: Mapping[str, Any]) -> str:
    payload = dict(value)
    payload.pop("event_sha256", None)
    return _sha256(payload)


def _position_key(ticker: str, route: str) -> str:
    return f"{ticker}|{route}"


def new_state_from_paper(
    paper_path: Path, *, now: datetime, policy_sha256: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    if len(policy_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in policy_sha256
    ):
        raise VirtualRssError("Virtual policy SHA-256 is invalid")
    _validate_policy_payload(policy)
    source_hash_before = _file_sha256(paper_path)
    paper = _load_json_object(paper_path, "canonical paper broker state")
    if _file_sha256(paper_path) != source_hash_before:
        raise VirtualRssError("Canonical PAPER state changed while it was being read")
    version = paper.get("state_version")
    if type(version) is not int or version not in (1, 2) or paper.get("broker_name") != "PAPER":
        raise VirtualRssError("Canonical paper broker state is not PAPER/live-disabled")
    if version == 2:
        if (
            paper.get("account_type") != "CASH"
            or paper.get("live_trading_enabled") is not False
            or paper.get("margin_trading_enabled") is not False
        ):
            raise VirtualRssError("Canonical paper broker v2 safety fields are invalid")
        source_updated = _jst_datetime(paper.get("updated_at"), "paper updated_at")
        timestamp_status = "EXPLICIT_JST"
    else:
        forbidden_v1_fields = {
            "account_type", "live_trading_enabled", "margin_trading_enabled", "fill_events"
        }.intersection(paper)
        if forbidden_v1_fields:
            raise VirtualRssError("Legacy PAPER v1 contains unexpected safety/event fields")
        if _decimal(paper.get("commission_rate"), "paper commission rate") != 0:
            raise VirtualRssError("Legacy PAPER v1 commission rate must be zero")
        raw_updated = paper.get("updated_at")
        if not isinstance(raw_updated, str):
            raise VirtualRssError("Legacy PAPER v1 updated_at is invalid")
        try:
            source_updated = datetime.fromisoformat(raw_updated)
        except ValueError as error:
            raise VirtualRssError("Legacy PAPER v1 updated_at is invalid") from error
        if source_updated.tzinfo is not None:
            raise VirtualRssError("Legacy PAPER v1 timestamp contract unexpectedly changed")
        source_updated = source_updated.replace(tzinfo=JST)
        timestamp_status = "LEGACY_NAIVE_ASSUMED_JST_BASELINE_ONLY"
    if source_updated > now + timedelta(seconds=2):
        raise VirtualRssError("Canonical paper broker state is from the future")
    initial = _decimal(paper.get("initial_cash_yen"), "paper initial cash", minimum=Decimal(0))
    commission_rate = _decimal(
        paper.get("commission_rate"), "paper commission rate", minimum=Decimal(0)
    )
    if _file_sha256(paper_path) != source_hash_before:
        raise VirtualRssError("Canonical PAPER state changed before validation")
    try:
        validated_broker = PaperBroker(
            initial_cash_yen=float(initial),
            commission_rate=float(commission_rate),
            state_file=paper_path,
        )
        validated_snapshot = validated_broker.get_account_snapshot()
    except (OSError, TypeError, ValueError) as error:
        raise VirtualRssError("Canonical PAPER state failed full broker validation") from error
    if _file_sha256(paper_path) != source_hash_before:
        raise VirtualRssError("Canonical PAPER validation unexpectedly changed its source")
    cash = _decimal(validated_snapshot.cash_yen, "paper cash", minimum=Decimal(0))
    baseline: dict[str, Any] = {}
    for item in validated_snapshot.positions:
        normalized = item.ticker.strip().upper()
        if not TSE_TICKER_PATTERN.fullmatch(normalized):
            raise VirtualRssError("Canonical paper broker position ticker is invalid")
        quantity = _strict_int(item.quantity, "paper position quantity", minimum=1)
        average = _decimal(item.average_price, "paper average price", minimum=Decimal("0.01"))
        market = _decimal(item.market_price, "paper market price", minimum=Decimal("0.01"))
        key = _position_key(normalized, "BASELINE_CANONICAL_PAPER")
        baseline[key] = {
            "ticker": normalized,
            "route": "BASELINE_CANONICAL_PAPER",
            "quantity": quantity,
            "cost_basis_yen": float((average * quantity).quantize(YEN, rounding=ROUND_HALF_UP)),
            "average_price_yen": float(average),
            "market_price_yen": float(market),
            "stop_price_yen": 0.0,
            "target_price_yen": 0.0,
        }
    state: dict[str, Any] = {
        "state_version": STATE_VERSION,
        "evidence_kind": STATE_KIND,
        "contract_id": CONTRACT_ID,
        "virtual_only": True,
        "eligible_for_real_rss_gate": False,
        "live_trading_enabled": False,
        "external_orders_submitted": 0,
        "external_notifications_sent": 0,
        "real_rss_sessions_credited": 0,
        "paper_days_credited": 0,
        "audited_live_fills_credited": 0,
        "initialization": "CLONED_CANONICAL_PAPER",
        "source_paper_state_sha256": source_hash_before,
        "policy_sha256": policy_sha256,
        "policy_canonical_sha256": _sha256(policy),
        "policy_snapshot": json.loads(json.dumps(policy)),
        "source_paper_state_version": version,
        "source_paper_state_updated_at": source_updated.isoformat(timespec="microseconds"),
        "source_paper_timestamp_status": timestamp_status,
        "initial_cash_yen": float(initial),
        "baseline_cash_yen": float(cash),
        "baseline_positions": baseline,
        "cash_yen": float(cash),
        "positions": json.loads(json.dumps(baseline)),
        "realized_pnl_yen": 0.0,
        "fills": [],
        "processed_run_ids": [],
        "observation_days": [],
        "last_event_sha256": ZERO_HASH,
        "updated_at": now.isoformat(timespec="microseconds"),
    }
    state["state_sha256"] = _state_hash(state)
    validate_state(state)
    return state


def _replay_state(state: Mapping[str, Any]) -> tuple[Decimal, dict[str, Any], Decimal, str]:
    cash = _decimal(state.get("baseline_cash_yen"), "baseline cash", minimum=Decimal(0))
    policy = state.get("policy_snapshot")
    if not isinstance(policy, Mapping):
        raise VirtualRssError("Virtual replay policy snapshot is missing")
    _validate_policy_payload(policy)
    baseline = state.get("baseline_positions")
    if not isinstance(baseline, dict):
        raise VirtualRssError("Virtual baseline_positions must be an object")
    positions: dict[str, Any] = json.loads(json.dumps(baseline))
    for key, item in positions.items():
        if not isinstance(item, dict):
            raise VirtualRssError("Virtual baseline position must be an object")
        ticker = str(item.get("ticker", ""))
        if key != _position_key(ticker, "BASELINE_CANONICAL_PAPER"):
            raise VirtualRssError("Virtual baseline position key/route is invalid")
        if item.get("route") != "BASELINE_CANONICAL_PAPER":
            raise VirtualRssError("Virtual baseline position route is invalid")
        quantity = _strict_int(item.get("quantity"), "baseline quantity", minimum=1)
        basis = _decimal(item.get("cost_basis_yen"), "baseline cost basis", minimum=Decimal("0.01"))
        average = _decimal(item.get("average_price_yen"), "baseline average", minimum=Decimal("0.01"))
        market = _decimal(item.get("market_price_yen"), "baseline market", minimum=Decimal("0.01"))
        if basis != (average * quantity).quantize(YEN, rounding=ROUND_HALF_UP):
            raise VirtualRssError("Virtual baseline cost basis is inconsistent")
        if market <= 0:
            raise VirtualRssError("Virtual baseline market price is invalid")
    realized = Decimal(0)
    previous = ZERO_HASH
    fills = state.get("fills")
    if not isinstance(fills, list):
        raise VirtualRssError("Virtual fills must be a list")
    event_ids: set[str] = set()
    last_time: datetime | None = None
    active_run_id = ""
    seen_run_ids: set[str] = set()
    run_start_values: dict[str, tuple[Decimal, dict[str, Any], Decimal]] = {}
    buy_count_by_day: dict[str, int] = {}
    buy_count_by_run: dict[str, int] = {}
    for sequence, event in enumerate(fills, start=1):
        if not isinstance(event, dict):
            raise VirtualRssError("Virtual fill must be an object")
        if _strict_int(event.get("sequence"), "fill sequence", minimum=1) != sequence:
            raise VirtualRssError("Virtual fill sequence is not contiguous")
        if event.get("previous_event_sha256") != previous or event.get("event_sha256") != _event_hash(event):
            raise VirtualRssError("Virtual fill hash chain is invalid")
        event_id = str(event.get("event_id", ""))
        if not event_id or event_id in event_ids:
            raise VirtualRssError("Virtual fill event_id is missing or duplicated")
        event_ids.add(event_id)
        created = _jst_datetime(event.get("created_at"), "fill created_at")
        if last_time is not None and created < last_time:
            raise VirtualRssError("Virtual fill timestamps moved backwards")
        last_time = created
        side = event.get("side")
        ticker = str(event.get("ticker", ""))
        route = str(event.get("route", ""))
        run_id = str(event.get("run_id", ""))
        if (
            len(run_id) != 64
            or any(character not in "0123456789abcdef" for character in run_id)
        ):
            raise VirtualRssError("Virtual fill run ID is invalid")
        if run_id != active_run_id:
            if run_id in seen_run_ids:
                raise VirtualRssError("Virtual fill run events are not contiguous")
            active_run_id = run_id
            seen_run_ids.add(run_id)
            run_start_values[run_id] = (
                cash,
                json.loads(json.dumps(positions)),
                realized,
            )
        if side not in ("BUY", "SELL") or not TSE_TICKER_PATTERN.fullmatch(ticker):
            raise VirtualRssError("Virtual fill identity is invalid")
        if route not in ("TSE_STANDARD_UNIT_SIM", "RAKUTEN_KABU_MINI_SIM"):
            raise VirtualRssError("Virtual fill route is invalid")
        if event.get("external_order_submitted") is not False:
            raise VirtualRssError("Virtual fill external_order_submitted must be false")
        if type(event.get("readiness_credit")) is not int or event.get("readiness_credit") != 0:
            raise VirtualRssError("Virtual fill readiness_credit must be integer zero")
        if event.get("costs_embedded_in_fill_price") is not True:
            raise VirtualRssError("Virtual fill must embed spread/slippage in its price")
        if event.get("policy_sha256") != state.get("policy_sha256"):
            raise VirtualRssError("Virtual fill policy hash does not match the ledger")
        expected_event_id = _sha256({
            "run_id": event.get("run_id"),
            "ticker": ticker,
            "route": route,
            "side": side,
            "quantity": event.get("quantity"),
            "quote_snapshot_sha256": event.get("quote_snapshot_sha256"),
            "policy_sha256": event.get("policy_sha256"),
            "candidate_limit_yen": event.get("candidate_limit_yen"),
        })
        if event_id != expected_event_id:
            raise VirtualRssError("Virtual fill event ID is not deterministic")
        quantity = _strict_int(event.get("quantity"), "fill quantity", minimum=1)
        if route == "TSE_STANDARD_UNIT_SIM" and quantity % 100:
            raise VirtualRssError("Standard-unit fill quantity is not a 100-share multiple")
        if route == "RAKUTEN_KABU_MINI_SIM" and not 1 <= quantity <= 99:
            raise VirtualRssError("Kabu Mini fill quantity must be 1..99")
        quote = _quote_from_mapping(event.get("quote"))
        if quote.ticker != ticker:
            raise VirtualRssError("Virtual fill quote ticker does not match the event")
        if event.get("quote_snapshot_sha256") != _sha256(event.get("quote")):
            raise VirtualRssError("Virtual fill quote lineage hash is invalid")
        readiness, readiness_reasons = quote_readiness(
            quote,
            created,
            policy,
            mini=route == "RAKUTEN_KABU_MINI_SIM",
        )
        if readiness != "FILL_READY" or readiness_reasons:
            raise VirtualRssError("Virtual fill quote was not fill-ready at event time")
        modeled = modeled_fill(quote, str(side), route, policy)
        price = _decimal(event.get("filled_price_yen"), "fill price", minimum=Decimal("0.01"))
        commission = _decimal(event.get("commission_yen"), "fill commission", minimum=Decimal(0))
        if price != _decimal(modeled["filled_price_yen"], "modeled fill price"):
            raise VirtualRssError("Virtual fill price cannot be reproduced from quote lineage")
        if commission != _decimal(modeled["commission_yen"], "modeled commission"):
            raise VirtualRssError("Virtual fill commission cannot be reproduced")
        if _decimal(event.get("reference_last_price_yen"), "fill reference last") != _decimal(quote.price, "quote last"):
            raise VirtualRssError("Virtual fill reference last price is inconsistent")
        for event_name, modeled_name in (
            ("product_spread_bps", "product_spread_bps"),
            ("slippage_reserve_bps", "slippage_reserve_bps"),
            ("synthetic_quote_half_spread_bps", "synthetic_quote_half_spread_bps"),
        ):
            if _decimal(event.get(event_name), event_name) != _decimal(modeled[modeled_name], modeled_name):
                raise VirtualRssError(f"Virtual fill modeled cost is inconsistent: {event_name}")
        if event.get("book_price_measured") is not modeled["book_price_measured"]:
            raise VirtualRssError("Virtual fill book-price classification is inconsistent")
        decision = event.get("decision_lineage")
        if not isinstance(decision, Mapping):
            raise VirtualRssError("Virtual fill decision lineage is missing")
        if side == "BUY":
            expected_decision_keys = {
                "kind", "candidate_input_sha256", "eligible_candidates_sha256",
                "candidate_input_hex",
                "candidate_generated_at", "signal_limit_yen",
                "candidate_name", "candidate_ranking_score",
                "eligible_candidate_rows", "run_quote_universe",
                "sizing_policy_snapshot", "candidate_controls",
                "eligibility_status", "eligibility_evidence_snapshot",
                "eligibility_evidence_sha256", "eligibility_entry",
            }
            if set(decision) != expected_decision_keys or decision.get("kind") != "CANDIDATE_BUY":
                raise VirtualRssError("Virtual BUY decision lineage schema is invalid")
            for hash_name in ("candidate_input_sha256", "eligible_candidates_sha256"):
                digest = str(decision.get(hash_name, ""))
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    raise VirtualRssError(f"Virtual BUY {hash_name} is invalid")
            eligible_rows = decision.get("eligible_candidate_rows")
            if (
                not isinstance(eligible_rows, list)
                or not eligible_rows
                or any(not isinstance(item, dict) for item in eligible_rows)
            ):
                raise VirtualRssError("Virtual BUY eligible candidate evidence is invalid")
            candidate_frame, input_derived_rows = _candidate_rows_from_input_snapshot(
                decision.get("candidate_input_hex"),
                str(decision.get("candidate_input_sha256", "")),
            )
            if input_derived_rows != eligible_rows:
                raise VirtualRssError(
                    "Virtual BUY candidate rows do not match the sealed input snapshot"
                )
            try:
                recomputed_candidates_hash = candidate_execution_sha256(candidate_frame)
            except (TypeError, ValueError, OverflowError) as error:
                raise VirtualRssError(
                    "Virtual BUY eligible candidate evidence cannot be normalized"
                ) from error
            if recomputed_candidates_hash != decision.get("eligible_candidates_sha256"):
                raise VirtualRssError("Virtual BUY eligible candidate evidence hash is invalid")
            matching_rows = [
                item for item in eligible_rows
                if str(item.get("ticker", "")).strip().upper() == ticker
            ]
            if len(matching_rows) != 1:
                raise VirtualRssError("Virtual BUY candidate row is missing or duplicated")
            candidate_row = matching_rows[0]
            quote_rows = decision.get("run_quote_universe")
            if (
                not isinstance(quote_rows, list)
                or not quote_rows
                or any(not isinstance(item, dict) for item in quote_rows)
            ):
                raise VirtualRssError("Virtual BUY run quote universe is invalid")
            run_quotes: dict[str, VirtualQuote] = {}
            for quote_row in quote_rows:
                run_quote = _quote_from_mapping(quote_row)
                if run_quote.ticker in run_quotes:
                    raise VirtualRssError("Virtual BUY run quote universe has duplicates")
                run_quotes[run_quote.ticker] = run_quote
            if list(run_quotes) != sorted(run_quotes):
                raise VirtualRssError("Virtual BUY run quote universe is not canonical")
            if ticker not in run_quotes or run_quotes[ticker].as_dict() != quote.as_dict():
                raise VirtualRssError("Virtual BUY own quote is not bound to its run universe")
            run_quote_hash = _sha256(quote_rows)
            expected_run_id = _sha256({
                "contract": CONTRACT_ID,
                "trading_date": created.date().isoformat(),
                "candidate_sha256": recomputed_candidates_hash,
                "quote_snapshot_sha256": run_quote_hash,
                "policy_sha256": state.get("policy_sha256"),
            })
            if run_id != expected_run_id:
                raise VirtualRssError("Virtual BUY run ID cannot be reproduced")
            generated = _jst_datetime(
                decision.get("candidate_generated_at"), "candidate generated_at"
            )
            if quote.event_at <= generated:
                raise VirtualRssError("Virtual BUY does not use a post-decision quote")
            signal_limit = _decimal(
                decision.get("signal_limit_yen"), "candidate signal limit",
                minimum=Decimal("0.01"),
            )
            if signal_limit != _decimal(event.get("candidate_limit_yen"), "event candidate limit"):
                raise VirtualRssError("Virtual BUY candidate limit lineage is inconsistent")
            row_limit = _decimal(
                candidate_row.get("エントリー価格"),
                "candidate row entry price",
                minimum=Decimal("0.01"),
            )
            row_stop = _decimal(
                candidate_row.get("損切価格"),
                "candidate row stop price",
                minimum=Decimal(0),
            )
            row_target = _decimal(
                candidate_row.get("利確価格", 0),
                "candidate row target price",
                minimum=Decimal(0),
            )
            row_ranking = _decimal(
                candidate_row.get("ランキング点"),
                "candidate row ranking score",
            )
            row_generated = _signal_time(candidate_row.get("生成日時"))
            if (
                row_limit != signal_limit
                or row_stop != _decimal(event.get("stop_price_yen"), "event stop price")
                or row_target != _decimal(event.get("target_price_yen"), "event target price")
                or row_ranking != _decimal(
                    decision.get("candidate_ranking_score"), "candidate ranking score"
                )
                or row_generated != generated
                or str(candidate_row.get("銘柄", ticker))
                != str(decision.get("candidate_name", ""))
            ):
                raise VirtualRssError("Virtual BUY selected candidate lineage is inconsistent")
            controls = decision.get("candidate_controls")
            if not isinstance(controls, Mapping) or set(controls) != {
                "maximum_candidate_age_hours",
                "maximum_price_deviation_from_signal_pct",
            }:
                raise VirtualRssError("Virtual BUY candidate controls are invalid")
            maximum_age = _decimal(
                controls.get("maximum_candidate_age_hours"),
                "candidate maximum age",
            )
            maximum_deviation = _decimal(
                controls.get("maximum_price_deviation_from_signal_pct"),
                "candidate maximum price deviation",
            )
            if maximum_age <= 0 or maximum_age > 96:
                raise VirtualRssError("Virtual BUY candidate age control is unsafe")
            if maximum_deviation <= 0 or maximum_deviation > Decimal("0.20"):
                raise VirtualRssError("Virtual BUY price deviation control is unsafe")
            if created - generated > timedelta(hours=float(maximum_age)):
                raise VirtualRssError("Virtual BUY candidate was stale at fill time")
            deviation = abs(_decimal(quote.price, "quote price") - signal_limit) / signal_limit
            if deviation > maximum_deviation:
                raise VirtualRssError("Virtual BUY exceeded its price deviation control")
            if price > signal_limit:
                raise VirtualRssError("Virtual BUY fill exceeds the candidate limit")
            eligibility_status = str(decision.get("eligibility_status", ""))
            eligibility_snapshot = decision.get("eligibility_evidence_snapshot")
            if eligibility_status == "MISSING":
                if eligibility_snapshot != {}:
                    raise VirtualRssError(
                        "Missing Kabu Mini eligibility cannot carry a snapshot"
                    )
                replay_eligibility: dict[str, dict[str, bool]] = {}
            elif eligibility_status in {"VERIFIED", "STALE"}:
                if not isinstance(eligibility_snapshot, Mapping):
                    raise VirtualRssError("Kabu Mini eligibility snapshot is invalid")
                replay_eligibility, replay_eligibility_status = (
                    _validate_eligibility_evidence_value(
                        eligibility_snapshot, created, policy
                    )
                )
                if replay_eligibility_status != eligibility_status:
                    raise VirtualRssError(
                        "Kabu Mini eligibility status cannot be reproduced"
                    )
            else:
                raise VirtualRssError("Virtual BUY eligibility status is invalid")
            sizing_values = decision.get("sizing_policy_snapshot")
            if not isinstance(sizing_values, Mapping):
                raise VirtualRssError("Virtual BUY sizing policy snapshot is missing")
            _validate_sizing_policy(sizing_values)
            pre_cash, pre_positions, pre_realized = run_start_values[run_id]
            position_tickers = {
                str(item.get("ticker", ""))
                for item in pre_positions.values()
                if isinstance(item, Mapping)
            }
            if not position_tickers.issubset(run_quotes):
                raise VirtualRssError("Virtual BUY sizing quote universe is incomplete")
            sizing_snapshot = _account_snapshot(
                {
                    "cash_yen": float(pre_cash),
                    "positions": pre_positions,
                    "realized_pnl_yen": float(pre_realized),
                },
                run_quotes,
                created,
            )
            replayed_plans = _candidate_plan(
                {
                    "cash_yen": float(pre_cash),
                    "positions": pre_positions,
                    "realized_pnl_yen": float(pre_realized),
                },
                candidate_frame,
                run_quotes,
                replay_eligibility,
                eligibility_status,
                policy,
                sizing_values,
                created,
                float(maximum_age),
                float(maximum_deviation),
            )
            replayed_ready = [
                item for item in replayed_plans if item.get("status") == "FILL_READY"
            ]
            if not replayed_ready:
                raise VirtualRssError("Virtual BUY has no reproducible fill-ready candidate")
            selected_plan = replayed_ready[0]
            if (
                selected_plan.get("ticker") != ticker
                or selected_plan.get("route") != route
                or selected_plan.get("quantity") != quantity
            ):
                raise VirtualRssError(
                    "Virtual BUY is not the highest-ranked fill-ready candidate"
                )
            candidate_name = str(decision.get("candidate_name", ""))
            ranking_score = float(row_ranking)
            unit_fill = modeled_fill(quote, "BUY", "TSE_STANDARD_UNIT_SIM", policy)
            unit_sizing = calculate_sizing(
                sizing_snapshot,
                ticker,
                unit_fill["filled_price_yen"],
                float(row_stop),
                _sizing_config(
                    sizing_values,
                    lot_size=100,
                    maximum_quantity=_strict_int(
                        sizing_values.get("maximum_quantity_per_ticker"),
                        "maximum_quantity_per_ticker",
                        minimum=100,
                    ),
                ),
                name=candidate_name,
                ranking_score=ranking_score,
            )
            mini_fill = modeled_fill(quote, "BUY", "RAKUTEN_KABU_MINI_SIM", policy)
            mini_sizing = calculate_sizing(
                sizing_snapshot,
                ticker,
                mini_fill["filled_price_yen"],
                float(row_stop),
                _sizing_config(sizing_values, lot_size=1, maximum_quantity=99),
                name=candidate_name,
                ranking_score=ranking_score,
            )
            unit_quantity = unit_sizing.recommended_quantity if unit_sizing.executable else 0
            mini_quantity = min(
                mini_sizing.recommended_quantity if mini_sizing.executable else 0,
                99,
            )
            expected_route = (
                "TSE_STANDARD_UNIT_SIM"
                if unit_quantity >= 100
                else "RAKUTEN_KABU_MINI_SIM"
            )
            expected_quantity = unit_quantity if unit_quantity >= 100 else mini_quantity
            if route != expected_route or quantity != expected_quantity or quantity <= 0:
                raise VirtualRssError("Virtual BUY route/quantity cannot be reproduced")
            total_cost = price * quantity + commission
            cash_reserve = _decimal(
                sizing_snapshot.equity_yen, "sizing equity"
            ) * _decimal(
                sizing_values.get("minimum_cash_reserve_pct"),
                "minimum cash reserve pct",
            )
            if _decimal(sizing_snapshot.cash_yen, "sizing cash") - total_cost < cash_reserve:
                raise VirtualRssError("Virtual BUY violated its cash reserve")
            eligibility_entry = decision.get("eligibility_entry")
            eligibility_hash = str(decision.get("eligibility_evidence_sha256", ""))
            if route == "RAKUTEN_KABU_MINI_SIM":
                if (
                    eligibility_status != "VERIFIED"
                    or len(eligibility_hash) != 64
                    or any(c not in "0123456789abcdef" for c in eligibility_hash)
                    or not isinstance(eligibility_entry, Mapping)
                    or eligibility_entry != replay_eligibility.get(ticker)
                    or eligibility_entry.get("realtime_buy_enabled") is not True
                    or not isinstance(eligibility_snapshot, Mapping)
                    or eligibility_hash
                    != eligibility_snapshot.get("evidence_sha256")
                ):
                    raise VirtualRssError("Virtual Kabu Mini BUY eligibility lineage is invalid")
            elif eligibility_hash or eligibility_entry != {}:
                raise VirtualRssError("Standard-unit BUY cannot carry Kabu Mini eligibility")
            buy_day = created.date().isoformat()
            buy_count_by_day[buy_day] = buy_count_by_day.get(buy_day, 0) + 1
            buy_count_by_run[run_id] = buy_count_by_run.get(run_id, 0) + 1
            if buy_count_by_day[buy_day] > 1 or buy_count_by_run[run_id] > 1:
                raise VirtualRssError("Virtual ledger exceeds the one-BUY safety cap")
        else:
            if (
                set(decision) != {"kind", "trigger", "position_key"}
                or decision.get("kind") != "POSITION_EXIT"
                or decision.get("trigger") not in ("STOP_LOSS", "TAKE_PROFIT")
            ):
                raise VirtualRssError("Virtual SELL decision lineage is invalid")
        expected_commission = Decimal(1070) if route == "TSE_STANDARD_UNIT_SIM" else Decimal(0)
        expected_product_spread = Decimal(0) if route == "TSE_STANDARD_UNIT_SIM" else Decimal(22)
        if commission != expected_commission:
            raise VirtualRssError("Virtual fill commission does not match its route")
        if _decimal(event.get("product_spread_bps"), "fill product spread") != expected_product_spread:
            raise VirtualRssError("Virtual fill product spread does not match its route")
        if _decimal(event.get("slippage_reserve_bps"), "fill slippage") != Decimal(5):
            raise VirtualRssError("Virtual fill slippage reserve is invalid")
        synthetic = _decimal(event.get("synthetic_quote_half_spread_bps"), "fill synthetic spread")
        measured = event.get("book_price_measured")
        if type(measured) is not bool or synthetic not in (Decimal(0), Decimal(10)):
            raise VirtualRssError("Virtual fill book-source classification is invalid")
        if (measured and synthetic != 0) or (not measured and synthetic != 10):
            raise VirtualRssError("Virtual fill measured/modeled spread flags disagree")
        gross = (price * quantity).quantize(YEN, rounding=ROUND_HALF_UP)
        if gross != _decimal(event.get("gross_yen"), "fill gross"):
            raise VirtualRssError("Virtual fill gross is inconsistent")
        key = _position_key(ticker, route)
        if side == "BUY":
            expected_delta = -(gross + commission)
            if cash + expected_delta < 0:
                raise VirtualRssError("Virtual fill would make cash negative")
            existing = positions.get(key)
            old_quantity = 0 if existing is None else _strict_int(existing["quantity"], "position quantity", minimum=1)
            old_basis = Decimal(0) if existing is None else _decimal(existing["cost_basis_yen"], "position basis")
            new_quantity = old_quantity + quantity
            new_basis = old_basis + gross + commission
            positions[key] = {
                "ticker": ticker,
                "route": route,
                "quantity": new_quantity,
                "cost_basis_yen": float(new_basis.quantize(YEN, rounding=ROUND_HALF_UP)),
                "average_price_yen": float((new_basis / new_quantity).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                "market_price_yen": float(price),
                "stop_price_yen": float(_decimal(event.get("stop_price_yen"), "fill stop", minimum=Decimal(0))),
                "target_price_yen": float(_decimal(event.get("target_price_yen"), "fill target", minimum=Decimal(0))),
            }
            event_realized = Decimal(0)
        else:
            existing = positions.get(key)
            if not isinstance(existing, dict):
                raise VirtualRssError("Virtual SELL has no matching position")
            if decision.get("position_key") != key:
                raise VirtualRssError("Virtual SELL position lineage is invalid")
            stop_price = _decimal(event.get("stop_price_yen"), "SELL stop price", minimum=Decimal(0))
            target_price = _decimal(event.get("target_price_yen"), "SELL target price", minimum=Decimal(0))
            if decision.get("trigger") == "STOP_LOSS" and not (stop_price > 0 and quote.price <= float(stop_price)):
                raise VirtualRssError("Virtual STOP_LOSS trigger cannot be reproduced")
            if decision.get("trigger") == "TAKE_PROFIT" and not (target_price > 0 and quote.price >= float(target_price)):
                raise VirtualRssError("Virtual TAKE_PROFIT trigger cannot be reproduced")
            old_quantity = _strict_int(existing.get("quantity"), "position quantity", minimum=1)
            if quantity > old_quantity:
                raise VirtualRssError("Virtual SELL exceeds position quantity")
            old_basis = _decimal(existing.get("cost_basis_yen"), "position basis")
            released = (old_basis * quantity / old_quantity).quantize(YEN, rounding=ROUND_HALF_UP)
            proceeds = gross - commission
            expected_delta = proceeds
            event_realized = proceeds - released
            remaining = old_quantity - quantity
            if remaining:
                remaining_basis = old_basis - released
                existing["quantity"] = remaining
                existing["cost_basis_yen"] = float(remaining_basis)
                existing["average_price_yen"] = float((remaining_basis / remaining).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))
                existing["market_price_yen"] = float(price)
            else:
                positions.pop(key)
        if expected_delta != _decimal(event.get("cash_delta_yen"), "fill cash delta"):
            raise VirtualRssError("Virtual fill cash delta is inconsistent")
        if event_realized.quantize(YEN, rounding=ROUND_HALF_UP) != _decimal(event.get("realized_pnl_yen"), "fill realized pnl"):
            raise VirtualRssError("Virtual fill realized P&L is inconsistent")
        cash += expected_delta
        realized += event_realized
        if cash.quantize(YEN) != _decimal(event.get("cash_after_yen"), "fill cash after"):
            raise VirtualRssError("Virtual fill cash-after value is inconsistent")
        position_after = positions.get(key)
        expected_after = 0 if position_after is None else int(position_after["quantity"])
        if expected_after != _strict_int(event.get("position_quantity_after"), "fill position after"):
            raise VirtualRssError("Virtual fill position-after value is inconsistent")
        previous = str(event["event_sha256"])
    return cash.quantize(YEN), positions, realized.quantize(YEN), previous


def validate_state(state: Mapping[str, Any]) -> None:
    fixed = {
        "state_version": STATE_VERSION,
        "evidence_kind": STATE_KIND,
        "contract_id": CONTRACT_ID,
        "virtual_only": True,
        "eligible_for_real_rss_gate": False,
        "live_trading_enabled": False,
        "external_orders_submitted": 0,
        "external_notifications_sent": 0,
        "real_rss_sessions_credited": 0,
        "paper_days_credited": 0,
        "audited_live_fills_credited": 0,
        "initialization": "CLONED_CANONICAL_PAPER",
    }
    for key, wanted in fixed.items():
        value = state.get(key)
        if type(value) is not type(wanted) or value != wanted:
            raise VirtualRssError(f"Virtual state has invalid {key}")
    if state.get("state_sha256") != _state_hash(state):
        raise VirtualRssError("Virtual state root hash is invalid")
    _jst_datetime(state.get("updated_at"), "state updated_at")
    source_hash = str(state.get("source_paper_state_sha256", ""))
    if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
        raise VirtualRssError("Virtual source paper state hash is invalid")
    policy_hash = str(state.get("policy_sha256", ""))
    if len(policy_hash) != 64 or any(c not in "0123456789abcdef" for c in policy_hash):
        raise VirtualRssError("Virtual policy hash is invalid")
    policy_snapshot = state.get("policy_snapshot")
    if not isinstance(policy_snapshot, Mapping):
        raise VirtualRssError("Virtual policy snapshot is missing")
    _validate_policy_payload(policy_snapshot)
    if state.get("policy_canonical_sha256") != _sha256(policy_snapshot):
        raise VirtualRssError("Virtual policy snapshot hash is invalid")
    source_version = state.get("source_paper_state_version")
    timestamp_status = state.get("source_paper_timestamp_status")
    expected_timestamp_status = (
        "LEGACY_NAIVE_ASSUMED_JST_BASELINE_ONLY"
        if source_version == 1
        else "EXPLICIT_JST"
    )
    if type(source_version) is not int or source_version not in (1, 2):
        raise VirtualRssError("Virtual source PAPER version is invalid")
    if timestamp_status != expected_timestamp_status:
        raise VirtualRssError("Virtual source PAPER timestamp status is invalid")
    _jst_datetime(state.get("source_paper_state_updated_at"), "source paper updated_at")
    run_ids = state.get("processed_run_ids")
    days = state.get("observation_days")
    if not isinstance(run_ids, list) or len(run_ids) != len(set(run_ids)):
        raise VirtualRssError("Virtual processed run IDs are invalid")
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in run_ids
    ):
        raise VirtualRssError("Virtual processed run ID is invalid")
    if not isinstance(days, list) or days != sorted(set(days)):
        raise VirtualRssError("Virtual observation days are invalid")
    for value in days:
        try:
            parsed = datetime.fromisoformat(str(value)).date()
            if parsed.isoformat() != value or not is_jpx_equities_trading_day(parsed):
                raise ValueError
        except ValueError as error:
            raise VirtualRssError("Virtual observation day is invalid") from error
    cash, positions, realized, previous = _replay_state(state)
    event_run_ids = {str(item.get("run_id", "")) for item in state.get("fills", [])}
    if not event_run_ids.issubset(set(run_ids)):
        raise VirtualRssError("Virtual fill references an unprocessed run")
    updated = _jst_datetime(state.get("updated_at"), "state updated_at")
    if any(
        _jst_datetime(item.get("created_at"), "fill created_at") > updated
        for item in state.get("fills", [])
    ):
        raise VirtualRssError("Virtual fill is later than the ledger update time")
    if cash != _decimal(state.get("cash_yen"), "state cash"):
        raise VirtualRssError("Virtual state cash does not reconcile")
    if positions != state.get("positions"):
        raise VirtualRssError("Virtual state positions do not reconcile")
    if realized != _decimal(state.get("realized_pnl_yen"), "state realized pnl"):
        raise VirtualRssError("Virtual state realized P&L does not reconcile")
    if previous != state.get("last_event_sha256"):
        raise VirtualRssError("Virtual state last event hash does not reconcile")


def load_state(path: Path) -> dict[str, Any]:
    state = _load_json_object(path, "virtual RSS paper state")
    validate_state(state)
    return state


def _save_state(path: Path, state: dict[str, Any]) -> None:
    state["state_sha256"] = _state_hash(state)
    validate_state(state)
    atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    reloaded = load_state(path)
    if reloaded["state_sha256"] != state["state_sha256"]:
        raise VirtualRssError("Virtual state post-save verification failed")


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    except FileExistsError as error:
        raise VirtualRssError("Virtual RSS operation is already running") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
            path.unlink(missing_ok=True)


def _account_snapshot(state: Mapping[str, Any], quotes: Mapping[str, VirtualQuote], now: datetime) -> AccountSnapshot:
    combined: dict[str, tuple[int, Decimal, Decimal]] = {}
    positions = state.get("positions", {})
    if not isinstance(positions, Mapping):
        raise VirtualRssError("Virtual positions are invalid")
    for item in positions.values():
        ticker = str(item["ticker"])
        quantity = _strict_int(item["quantity"], "position quantity", minimum=1)
        basis = _decimal(item["cost_basis_yen"], "position basis")
        mark = Decimal(str(quotes[ticker].price)) if ticker in quotes else _decimal(item["market_price_yen"], "market price")
        old = combined.get(ticker, (0, Decimal(0), Decimal(0)))
        combined[ticker] = (old[0] + quantity, old[1] + basis, old[2] + mark * quantity)
    rows = tuple(
        Position(
            ticker=ticker,
            quantity=value[0],
            average_price=float((value[1] / value[0]).quantize(Decimal("0.0001"))),
            market_price=float((value[2] / value[0]).quantize(Decimal("0.0001"))),
        )
        for ticker, value in sorted(combined.items())
    )
    return AccountSnapshot(
        broker_name="VIRTUAL_RSS_PAPER",
        cash_yen=float(state["cash_yen"]),
        positions=rows,
        realized_pnl_yen=float(state["realized_pnl_yen"]),
        generated_at=now,
    )


def _sizing_config(values: Mapping[str, Any], *, lot_size: int, maximum_quantity: int) -> PositionSizingConfig:
    return PositionSizingConfig(
        risk_per_trade_pct=float(values.get("risk_per_trade_pct", 0.01)),
        max_position_pct=float(values.get("max_position_pct", 0.3)),
        max_total_invested_pct=float(values.get("max_total_invested_pct", 0.8)),
        minimum_cash_reserve_pct=float(values.get("minimum_cash_reserve_pct", 0.1)),
        fallback_stop_distance_pct=float(values.get("fallback_stop_distance_pct", 0.03)),
        lot_size=lot_size,
        maximum_quantity_per_ticker=maximum_quantity,
        allow_pyramiding=False,
        commission_buffer_pct=float(values.get("commission_buffer_pct", 0.001)),
    )


def _validate_sizing_policy(values: Mapping[str, Any]) -> None:
    numeric_bounds = {
        "risk_per_trade_pct": (Decimal("0.000001"), Decimal("0.01")),
        "max_position_pct": (Decimal("0.000001"), Decimal("0.30")),
        "max_total_invested_pct": (Decimal("0.000001"), Decimal("0.80")),
        "minimum_cash_reserve_pct": (Decimal("0.10"), Decimal("1.00")),
    }
    for name, (minimum, maximum) in numeric_bounds.items():
        value = _decimal(values.get(name), f"position_sizing.{name}")
        if value < minimum or value > maximum:
            raise VirtualRssError(f"position_sizing.{name} would relax the Step21 risk contract")
    if type(values.get("lot_size")) is not int or values.get("lot_size") != 100:
        raise VirtualRssError("Canonical position_sizing.lot_size must remain 100")
    maximum_quantity = values.get("maximum_quantity_per_ticker")
    if type(maximum_quantity) is not int or not 100 <= maximum_quantity <= 1000:
        raise VirtualRssError("Canonical maximum_quantity_per_ticker is invalid")
    if values.get("allow_pyramiding") is not False:
        raise VirtualRssError("Pyramiding must remain disabled")
    commission_buffer = _decimal(
        values.get("commission_buffer_pct"), "position_sizing.commission_buffer_pct"
    )
    if commission_buffer < Decimal("0.001"):
        raise VirtualRssError("The canonical commission buffer cannot be reduced")


def _signal_time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise VirtualRssError("Candidate generation time is missing")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise VirtualRssError("Candidate generation time is invalid") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    if parsed.utcoffset() != timedelta(hours=9):
        parsed = parsed.astimezone(JST)
    return parsed


def _candidate_rows_from_input_snapshot(
    input_hex: Any, expected_sha256: str
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    if (
        not isinstance(input_hex, str)
        or not input_hex
        or len(input_hex) > 10_000_000
        or len(input_hex) % 2
    ):
        raise VirtualRssError("Virtual BUY candidate input snapshot is invalid")
    try:
        content = bytes.fromhex(input_hex)
        decoded = content.decode("utf-8-sig")
    except (ValueError, UnicodeError) as error:
        raise VirtualRssError("Virtual BUY candidate input snapshot cannot be decoded") from error
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise VirtualRssError("Virtual BUY candidate input snapshot hash is invalid")
    try:
        csv_rows = list(csv.reader(io.StringIO(decoded), strict=True))
    except csv.Error as error:
        raise VirtualRssError("Virtual BUY candidate input CSV is invalid") from error
    if not csv_rows:
        raise VirtualRssError("Virtual BUY candidate input CSV is empty")
    header = csv_rows[0]
    normalized_header = [str(value).strip().casefold() for value in header]
    if (
        any(not value for value in normalized_header)
        or len(normalized_header) != len(set(normalized_header))
        or any(len(row) != len(header) for row in csv_rows[1:])
    ):
        raise VirtualRssError("Virtual BUY candidate input CSV shape is invalid")
    try:
        raw = pd.read_csv(io.StringIO(decoded))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeError) as error:
        raise VirtualRssError("Virtual BUY candidate input CSV cannot be parsed") from error
    for required in (DECISION_COLUMN, EXECUTION_PRICE_COLUMN, "ticker"):
        if required not in raw.columns:
            raise VirtualRssError("Virtual BUY candidate input column is missing")
    decisions = raw[DECISION_COLUMN].map(
        lambda value: "" if pd.isna(value) else str(value).strip().upper()
    )
    if set(decisions) - set(KNOWN_DECISIONS):
        raise VirtualRssError("Virtual BUY candidate input has an unknown decision")
    tickers = raw["ticker"].map(
        lambda value: "" if pd.isna(value) else str(value).strip().upper()
    )
    if (
        tickers.eq("").any()
        or tickers.duplicated(keep=False).any()
        or any(not TSE_TICKER_PATTERN.fullmatch(value) for value in tickers)
    ):
        raise VirtualRssError("Virtual BUY candidate input tickers are invalid")
    prices = pd.to_numeric(raw[EXECUTION_PRICE_COLUMN], errors="coerce")
    if not bool(prices.map(lambda value: pd.notna(value) and math.isfinite(float(value)) and float(value) > 0).all()):
        raise VirtualRssError("Virtual BUY candidate input prices are invalid")
    normalized = raw.copy()
    normalized["ticker"] = tickers
    normalized["エントリー価格"] = prices.astype(float)
    normalized = normalize_candidate_frame(normalized, apply_portfolio_filter=False)
    if len(normalized) != len(raw):
        raise VirtualRssError("Virtual BUY candidate input normalization lost rows")
    eligible_tickers = set(tickers[decisions.isin(set(EXECUTABLE_DECISIONS))])
    candidates = normalized[normalized["ticker"].isin(eligible_tickers)].copy()
    candidates = candidates.reset_index(drop=True)
    if candidates.empty:
        raise VirtualRssError("Virtual BUY candidate input has no eligible row")
    rows = json.loads(
        candidates.to_json(orient="records", force_ascii=False, date_format="iso")
    )
    return candidates, rows


def _candidate_plan(
    state: Mapping[str, Any], candidates: pd.DataFrame, quotes: Mapping[str, VirtualQuote],
    eligibility: Mapping[str, Mapping[str, bool]], eligibility_status: str,
    policy: Mapping[str, Any], sizing_values: Mapping[str, Any], now: datetime,
    maximum_candidate_age_hours: float,
    maximum_price_deviation_from_signal_pct: float,
) -> list[dict[str, Any]]:
    snapshot = _account_snapshot(state, quotes, now)
    plans: list[dict[str, Any]] = []
    ordered = candidates.sort_values("ランキング点", ascending=False, kind="stable")
    for _, row in ordered.iterrows():
        ticker = str(row["ticker"])
        quote = quotes.get(ticker)
        plan: dict[str, Any] = {"ticker": ticker, "name": str(row.get("銘柄", ticker)), "status": "BLOCKED", "reasons": []}
        if quote is None:
            plan["reasons"].append("QUOTE_MISSING")
            plans.append(plan)
            continue
        generated = _signal_time(row.get("生成日時"))
        if now - generated > timedelta(hours=maximum_candidate_age_hours):
            plan["reasons"].append("STALE_CANDIDATE")
        if quote.event_at <= generated:
            plan["reasons"].append("NO_POST_DECISION_QUOTE")
        signal_limit = float(row["エントリー価格"])
        stop = float(row["損切価格"])
        target = float(row.get("利確価格", 0.0))
        if quote.price > signal_limit:
            plan["reasons"].append("LIMIT_NOT_REACHED")
        if abs(quote.price - signal_limit) / signal_limit > maximum_price_deviation_from_signal_pct:
            plan["reasons"].append("PRICE_DEVIATION_REVIEW")
        unit_ready, unit_reasons = quote_readiness(quote, now, policy, mini=False)
        mini_ready, mini_reasons = quote_readiness(quote, now, policy, mini=True)
        unit_fill = modeled_fill(quote, "BUY", "TSE_STANDARD_UNIT_SIM", policy)
        unit_sizing = calculate_sizing(
            snapshot, ticker, unit_fill["filled_price_yen"], stop,
            _sizing_config(sizing_values, lot_size=100, maximum_quantity=int(sizing_values.get("maximum_quantity_per_ticker", 1000))),
            name=plan["name"], ranking_score=float(row["ランキング点"]),
        )
        mini_fill = modeled_fill(quote, "BUY", "RAKUTEN_KABU_MINI_SIM", policy)
        mini_sizing = calculate_sizing(
            snapshot, ticker, mini_fill["filled_price_yen"], stop,
            _sizing_config(sizing_values, lot_size=1, maximum_quantity=99),
            name=plan["name"], ranking_score=float(row["ランキング点"]),
        )
        unit_quantity = unit_sizing.recommended_quantity if unit_sizing.executable else 0
        mini_quantity = min(mini_sizing.recommended_quantity if mini_sizing.executable else 0, 99)
        route = "TSE_STANDARD_UNIT_SIM" if unit_quantity >= 100 else "RAKUTEN_KABU_MINI_SIM"
        selected_fill = unit_fill if route == "TSE_STANDARD_UNIT_SIM" else mini_fill
        selected_quantity = unit_quantity if route == "TSE_STANDARD_UNIT_SIM" else mini_quantity
        if route == "TSE_STANDARD_UNIT_SIM":
            plan["reasons"].extend(unit_reasons)
        else:
            plan["reasons"].extend(mini_reasons)
            if eligibility_status != "VERIFIED":
                plan["reasons"].append(f"KABUMINI_ELIGIBILITY_{eligibility_status}")
            elif not eligibility.get(ticker, {}).get("realtime_buy_enabled", False):
                plan["reasons"].append("KABUMINI_REALTIME_BUY_NOT_ELIGIBLE")
        if selected_quantity <= 0:
            plan["reasons"].append("POSITION_SIZER_BLOCKED")
        if selected_fill["filled_price_yen"] > signal_limit:
            plan["reasons"].append("MODELED_FILL_EXCEEDS_LIMIT")
        gross = Decimal(str(selected_fill["filled_price_yen"])) * selected_quantity
        total = gross + Decimal(str(selected_fill["commission_yen"]))
        reserve = Decimal(str(snapshot.equity_yen)) * Decimal(str(sizing_values.get("minimum_cash_reserve_pct", 0.1)))
        if Decimal(str(snapshot.cash_yen)) - total < reserve:
            plan["reasons"].append("CASH_RESERVE_BLOCKED")
        plan.update({
            "action": "ENTRY",
            "route": route,
            "quantity": selected_quantity,
            "signal_limit_yen": signal_limit,
            "stop_price_yen": stop,
            "target_price_yen": target,
            "quote": quote.as_dict(),
            "modeled_fill": selected_fill,
            "unit_sizing_status": unit_sizing.status,
            "unit_quantity": unit_quantity,
            "mini_sizing_status": mini_sizing.status,
            "mini_quantity": mini_quantity,
            "quote_readiness": unit_ready if route == "TSE_STANDARD_UNIT_SIM" else mini_ready,
            "candidate_generated_at": generated.isoformat(timespec="seconds"),
            "ranking_score": float(row["ランキング点"]),
        })
        plan["reasons"] = sorted(set(plan["reasons"]))
        if not plan["reasons"]:
            plan["status"] = "FILL_READY"
        plans.append(plan)
    return plans


def _exit_plans(
    state: Mapping[str, Any],
    quotes: Mapping[str, VirtualQuote],
    policy: Mapping[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    positions = state.get("positions")
    if not isinstance(positions, Mapping):
        raise VirtualRssError("Virtual positions are invalid")
    for key, position in sorted(positions.items()):
        if not isinstance(position, Mapping):
            raise VirtualRssError("Virtual position is invalid")
        route = str(position.get("route", ""))
        if route == "BASELINE_CANONICAL_PAPER":
            continue
        ticker = str(position.get("ticker", ""))
        quote = quotes.get(ticker)
        if quote is None:
            continue
        stop = float(position.get("stop_price_yen", 0.0))
        target = float(position.get("target_price_yen", 0.0))
        trigger = ""
        if stop > 0 and quote.price <= stop:
            trigger = "STOP_LOSS"
        elif target > 0 and quote.price >= target:
            trigger = "TAKE_PROFIT"
        if not trigger:
            continue
        is_mini = route == "RAKUTEN_KABU_MINI_SIM"
        readiness, reasons = quote_readiness(quote, now, policy, mini=is_mini)
        fill = modeled_fill(quote, "SELL", route, policy)
        plan = {
            "ticker": ticker,
            "name": ticker,
            "action": "EXIT",
            "exit_trigger": trigger,
            "route": route,
            "quantity": int(position["quantity"]),
            "signal_limit_yen": 0.0,
            "stop_price_yen": stop,
            "target_price_yen": target,
            "quote": quote.as_dict(),
            "modeled_fill": fill,
            "quote_readiness": readiness,
            "status": "FILL_READY" if not reasons else "BLOCKED",
            "reasons": reasons,
            "position_key": key,
        }
        plans.append(plan)
    return plans


def _append_fill(
    state: dict[str, Any], plan: Mapping[str, Any], *, side: str,
    quantity: int, run_id: str, policy_hash: str, now: datetime,
) -> dict[str, Any]:
    fill = plan["modeled_fill"]
    price = Decimal(str(fill["filled_price_yen"]))
    commission = Decimal(str(fill["commission_yen"]))
    gross = (price * quantity).quantize(YEN, rounding=ROUND_HALF_UP)
    route = str(plan["route"])
    ticker = str(plan["ticker"])
    if side == "BUY":
        cash_delta = -(gross + commission)
        realized = Decimal(0)
        position_before = state["positions"].get(_position_key(ticker, route))
        quantity_before = 0 if position_before is None else int(position_before["quantity"])
    else:
        key = _position_key(ticker, route)
        position = state["positions"][key]
        basis = Decimal(str(position["cost_basis_yen"]))
        released = (basis * quantity / int(position["quantity"])).quantize(YEN, rounding=ROUND_HALF_UP)
        cash_delta = gross - commission
        realized = cash_delta - released
        quantity_before = int(position["quantity"])
    cash_after = Decimal(str(state["cash_yen"])) + cash_delta
    quantity_after = quantity_before + quantity if side == "BUY" else quantity_before - quantity
    event_core = {
        "run_id": run_id,
        "ticker": ticker,
        "route": route,
        "side": side,
        "quantity": quantity,
        "quote_snapshot_sha256": _sha256(plan["quote"]),
        "policy_sha256": policy_hash,
        "candidate_limit_yen": float(plan.get("signal_limit_yen", 0.0)),
    }
    event_id = _sha256(event_core)
    if side == "BUY":
        decision_lineage = {
            "kind": "CANDIDATE_BUY",
            "candidate_input_sha256": str(plan.get("candidate_input_sha256", "")),
            "candidate_input_hex": str(plan.get("candidate_input_hex", "")),
            "eligible_candidates_sha256": str(plan.get("eligible_candidates_sha256", "")),
            "candidate_generated_at": str(plan.get("candidate_generated_at", "")),
            "signal_limit_yen": float(plan.get("signal_limit_yen", 0.0)),
            "candidate_name": str(plan.get("name", "")),
            "candidate_ranking_score": float(plan.get("ranking_score", 0.0)),
            "eligible_candidate_rows": json.loads(
                json.dumps(plan.get("eligible_candidate_rows", []))
            ),
            "run_quote_universe": json.loads(
                json.dumps(plan.get("run_quote_universe", []))
            ),
            "sizing_policy_snapshot": json.loads(
                json.dumps(plan.get("sizing_policy_snapshot", {}))
            ),
            "candidate_controls": dict(plan.get("candidate_controls", {})),
            "eligibility_status": str(plan.get("eligibility_status", "")),
            "eligibility_evidence_snapshot": json.loads(
                json.dumps(plan.get("eligibility_evidence_snapshot", {}))
            ),
            "eligibility_evidence_sha256": str(plan.get("eligibility_evidence_sha256", "")),
            "eligibility_entry": dict(plan.get("eligibility_entry", {})),
        }
    else:
        decision_lineage = {
            "kind": "POSITION_EXIT",
            "trigger": str(plan.get("exit_trigger", "")),
            "position_key": str(plan.get("position_key", "")),
        }
    event: dict[str, Any] = {
        "sequence": len(state["fills"]) + 1,
        "event_id": event_id,
        **event_core,
        "reference_last_price_yen": float(plan["quote"]["price"]),
        "quote": dict(plan["quote"]),
        "decision_lineage": decision_lineage,
        "filled_price_yen": float(price),
        "gross_yen": float(gross),
        "commission_yen": float(commission),
        "cash_delta_yen": float(cash_delta),
        "cash_after_yen": float(cash_after.quantize(YEN)),
        "position_quantity_after": quantity_after,
        "realized_pnl_yen": float(realized.quantize(YEN, rounding=ROUND_HALF_UP)),
        "product_spread_bps": float(fill["product_spread_bps"]),
        "slippage_reserve_bps": float(fill["slippage_reserve_bps"]),
        "synthetic_quote_half_spread_bps": float(fill["synthetic_quote_half_spread_bps"]),
        "book_price_measured": fill["book_price_measured"] is True,
        "costs_embedded_in_fill_price": True,
        "stop_price_yen": float(plan.get("stop_price_yen", 0.0)),
        "target_price_yen": float(plan.get("target_price_yen", 0.0)),
        "created_at": now.isoformat(timespec="microseconds"),
        "previous_event_sha256": state["last_event_sha256"],
        "external_order_submitted": False,
        "readiness_credit": 0,
    }
    event["event_sha256"] = _event_hash(event)
    existing = {item["event_id"]: item for item in state["fills"]}
    if event_id in existing:
        if existing[event_id] != event:
            raise VirtualRssError("Duplicate virtual event ID has different content")
        return existing[event_id]
    state["fills"].append(event)
    cash, positions, realized_total, previous = _replay_state(state)
    state["cash_yen"] = float(cash)
    state["positions"] = positions
    state["realized_pnl_yen"] = float(realized_total)
    state["last_event_sha256"] = previous
    return event


def _performance(state: Mapping[str, Any], quotes: Mapping[str, VirtualQuote], policy: Mapping[str, Any]) -> dict[str, Any]:
    market_value = Decimal(0)
    for item in state.get("positions", {}).values():
        ticker = str(item["ticker"])
        mark = Decimal(str(quotes[ticker].price)) if ticker in quotes else Decimal(str(item["market_price_yen"]))
        market_value += mark * int(item["quantity"])
    cash = Decimal(str(state["cash_yen"]))
    gross_equity = cash + market_value
    economics = _policy_section(policy, "economics")
    fixed_per_day = Decimal(str(economics["fixed_monthly_operating_cost_yen"])) / Decimal(str(economics["assumed_trading_days_per_month"]))
    fixed_reserve = fixed_per_day * len(state.get("observation_days", []))
    realized = Decimal(str(state["realized_pnl_yen"]))
    tax_reserve = max(realized, Decimal(0)) * Decimal(str(economics["tax_reserve_rate"]))
    net_equity = gross_equity - fixed_reserve - tax_reserve
    initial = Decimal(str(state["initial_cash_yen"]))
    distributable = max(net_equity - initial, Decimal(0))
    living_candidate = distributable * Decimal(str(economics["living_funds_rate"]))
    return {
        "cash_yen": float(cash.quantize(YEN)),
        "market_value_yen": float(market_value.quantize(YEN)),
        "gross_equity_yen": float(gross_equity.quantize(YEN)),
        "realized_pnl_yen": float(realized.quantize(YEN)),
        "fixed_operating_cost_reserve_yen": float(fixed_reserve.quantize(YEN)),
        "tax_reserve_yen": float(tax_reserve.quantize(YEN, rounding=ROUND_HALF_UP)),
        "net_equity_after_reserves_yen": float(net_equity.quantize(YEN, rounding=ROUND_HALF_UP)),
        "net_pnl_after_reserves_yen": float((net_equity - initial).quantize(YEN, rounding=ROUND_HALF_UP)),
        "living_funds_candidate_yen": float(living_candidate.quantize(YEN, rounding=ROUND_FLOOR)),
        "living_funds_distributed_yen": 0.0,
        "living_funds_manual_approval_required": True,
        "conditional_contribution_applied_yen": 0.0,
    }


def build_notification_preview(report: Mapping[str, Any], *, maximum_chunk_chars: int = 1600) -> dict[str, Any]:
    if type(maximum_chunk_chars) is not int or maximum_chunk_chars < 300:
        raise VirtualRssError("maximum_chunk_chars must be an integer >= 300")
    fills = report.get("fills", [])
    if not isinstance(fills, list):
        raise VirtualRssError("Report fills must be a list")
    lines = [
        "VIRTUAL_RSS仮想取引・注文未送信",
        f"状態: {report.get('status', 'UNKNOWN')} / 価格源: {QUOTE_SOURCE}",
        f"取引日: {report.get('trading_date', '')} / 仮想約定: {len(fills)}件",
    ]
    for index, item in enumerate(fills, start=1):
        event_reference = str(item.get("event_id", ""))[:12] or "PREVIEW"
        lines.append(
            f"履歴#{item.get('sequence', index)} {item['side']} {item['ticker']} "
            f"{item['quantity']}株 証跡:{event_reference} "
            f"[{item['route']}] 基準{item['reference_last_price_yen']:,.2f}円 → "
            f"仮想{item['filled_price_yen']:,.2f}円 / 手数料{item['commission_yen']:,.0f}円 / "
            f"商品spread{float(item.get('product_spread_bps', 0)):g}bps / "
            f"slippage引当{float(item.get('slippage_reserve_bps', 0)):g}bps / "
            f"実現損益{item['realized_pnl_yen']:,.2f}円 / 取引後現金{item['cash_after_yen']:,.2f}円"
        )
    perf = report.get("performance", {})
    lines.extend([
        f"現金: {float(perf.get('cash_yen', 0)):,.2f}円",
        f"固定費・税引当後損益: {float(perf.get('net_pnl_after_reserves_yen', 0)):,.2f}円",
        "外部通知: 無効 / 実RSS・本番移行実績への加算: 0",
    ])
    body = "\n".join(lines)
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    chunks: list[str] = []
    remaining = body
    payload_limit = maximum_chunk_chars - 80
    while remaining:
        chunks.append(remaining[:payload_limit])
        remaining = remaining[payload_limit:]
    rendered_chunks = []
    for index, chunk in enumerate(chunks, start=1):
        header = f"VIRTUAL_RSS仮想取引・注文未送信 [{index}/{len(chunks)}]\n"
        rendered_chunks.append({
            "number": index,
            "total": len(chunks),
            "payload": chunk,
            "payload_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
            "text": header + chunk,
        })
    return {
        "schema_version": 1,
        "preview_only": True,
        "external_notifications_allowed": False,
        "send_attempted": False,
        "sent": False,
        "body": body,
        "body_sha256": body_hash,
        "chunk_count": len(chunks),
        "chunks": rendered_chunks,
    }


def _text_report(report: Mapping[str, Any]) -> str:
    perf = report.get("performance", {})
    return "\n".join([
        "PHOENIX v7 Step21 - VIRTUAL RSS PAPER",
        "=" * 58,
        f"Status                 : {report.get('status', '')}",
        f"Mode                   : {report.get('mode', '')}",
        f"Quote source           : {QUOTE_SOURCE}",
        f"Observed / requested   : {report.get('quotes', {}).get('observed_count', 0)} / {report.get('quotes', {}).get('requested_count', 0)}",
        f"Plans / virtual fills  : {len(report.get('plans', []))} / {len(report.get('fills', []))}",
        f"Cash / gross equity    : {perf.get('cash_yen', 0):,.2f} / {perf.get('gross_equity_yen', 0):,.2f} JPY",
        f"Net P&L after reserves : {perf.get('net_pnl_after_reserves_yen', 0):,.2f} JPY",
        "External orders        : 0",
        "External notifications : 0 (preview only)",
        "Real RSS/paper/live credit: 0 / 0 / 0",
        "",
        "Blockers:",
        *[f"- {value}" for value in report.get("blockers", [])],
        "",
    ])


def _preview_text(preview: Mapping[str, Any]) -> str:
    body = preview.get("body")
    if not isinstance(body, str):
        raise VirtualRssError("Notification preview body is missing")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != preview.get("body_sha256"):
        raise VirtualRssError("Notification preview body hash is invalid")
    return body


def run_virtual_rss_paper(
    root: Path,
    config: Mapping[str, Any],
    *,
    persist: bool,
    quotes: Mapping[str, VirtualQuote] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    repository = root.resolve()
    settings = config.get("virtual_rss_paper")
    if not isinstance(settings, Mapping):
        raise VirtualRssError("virtual_rss_paper config is missing")
    policy, policy_hash = load_policy(repository, settings)
    checked = now or datetime.now(JST)
    if checked.utcoffset() != timedelta(hours=9):
        raise VirtualRssError("now must have an explicit +09:00 offset")
    state_path = _safe_repo_path(repository, str(settings.get("state_file", "")), "state")
    paper_path = _safe_repo_path(repository, str(settings.get("source_paper_state", "")), "state")
    eligibility_path = _safe_repo_path(repository, str(settings.get("kabumini_eligibility_file", "")), "state")
    report_json = _safe_repo_path(repository, str(settings.get("report_json", "")), "reports")
    report_text = _safe_repo_path(repository, str(settings.get("report_text", "")), "reports")
    notification_json = _safe_repo_path(repository, str(settings.get("notification_preview_json", "")), "reports")
    notification_text = _safe_repo_path(repository, str(settings.get("notification_preview_text", "")), "reports")
    lock_path = _safe_repo_path(repository, str(settings.get("lock_file", "")), "state")
    runtime_root = _safe_repo_path(repository, str(settings.get("runtime_root", "")), "runtime")
    direct = config.get("_direct_pipeline_config")
    if not isinstance(direct, Mapping):
        direct_path = _safe_repo_path(repository, str(settings.get("direct_pipeline_config", "")), "config")
        direct = _load_json_object(direct_path, "direct pipeline config")
    candidate_policy = CandidateInputPolicy.from_mapping(direct.get("candidate_input", {}))
    candidate_input_path = repository / candidate_policy.path
    candidate_batch = load_execution_candidates(
        candidate_input_path, candidate_policy, repository_root=repository
    )
    try:
        candidate_input_bytes = candidate_input_path.read_bytes()
    except OSError as error:
        raise VirtualRssError("Candidate input changed after validation") from error
    if hashlib.sha256(candidate_input_bytes).hexdigest() != candidate_batch.audit.input_sha256:
        raise VirtualRssError("Candidate input changed after validation")
    candidate_input_hex = candidate_input_bytes.hex()
    candidate_tickers = list(candidate_batch.candidates["ticker"])
    state: dict[str, Any]
    blockers: list[str] = []
    ledger_initialized = state_path.is_file()
    if ledger_initialized:
        state = load_state(state_path)
        if state.get("policy_sha256") != policy_hash:
            raise VirtualRssError(
                "Existing virtual ledger is bound to a different reviewed policy"
            )
    elif paper_path.is_file():
        state = new_state_from_paper(
            paper_path, now=checked, policy_sha256=policy_hash, policy=policy
        )
        blockers.append("VIRTUAL_LEDGER_NOT_INITIALIZED")
    else:
        raise VirtualRssError("Canonical paper broker state is missing")
    original_state_hash = state["state_sha256"]
    position_tickers = [
        str(item.get("ticker", ""))
        for item in state.get("positions", {}).values()
        if isinstance(item, Mapping)
    ]
    tickers = sorted(set(candidate_tickers + position_tickers))
    if quotes is None:
        observed, quote_errors, lineage = fetch_yfinance_quotes(
            tickers,
            received_at=checked,
            cache_directory=runtime_root / "yfinance_cache",
        )
    else:
        observed = {ticker: value for ticker, value in quotes.items()}
        for ticker, quote in observed.items():
            quote.validate()
            if ticker != quote.ticker:
                raise VirtualRssError("Injected quote key/ticker mismatch")
        quote_errors = []
        rows = [observed[ticker].as_dict() for ticker in sorted(observed)]
        lineage = {
            "status": "OBSERVED" if observed else "FAILED",
            "source": QUOTE_SOURCE,
            "currency": "JPY",
            "adjusted": False,
            "received_at": checked.isoformat(timespec="seconds"),
            "requested_tickers": sorted(tickers),
            "observed_tickers": sorted(observed),
            "snapshot_sha256": _sha256(rows),
            "fallback_used": False,
            "post_requests": 0,
        }
    eligibility, eligibility_status = load_eligibility(eligibility_path, checked, policy)
    eligibility_evidence: dict[str, Any] = {}
    eligibility_evidence_sha256 = ""
    if eligibility_path.is_file():
        eligibility_evidence = _load_json_object(
            eligibility_path, "Kabu Mini eligibility evidence"
        )
        snapshot_eligibility, snapshot_status = _validate_eligibility_evidence_value(
            eligibility_evidence, checked, policy
        )
        if snapshot_status != eligibility_status or snapshot_eligibility != eligibility:
            raise VirtualRssError("Kabu Mini eligibility evidence changed after validation")
    if eligibility_status == "VERIFIED":
        eligibility_evidence_sha256 = str(
            eligibility_evidence.get("evidence_sha256", "")
        )
    if quote_errors:
        blockers.extend(quote_errors)
    if set(observed) != set(tickers):
        blockers.append("INCOMPLETE_QUOTE_UNIVERSE")
    sizing_values = direct.get("position_sizing")
    if not isinstance(sizing_values, Mapping):
        raise VirtualRssError("position_sizing config is missing")
    _validate_sizing_policy(sizing_values)
    candidate_age = _decimal(
        settings.get("maximum_candidate_age_hours"),
        "maximum_candidate_age_hours",
    )
    if candidate_age <= 0 or candidate_age > 96:
        raise VirtualRssError("maximum_candidate_age_hours must be within (0, 96]")
    maximum_deviation = _decimal(
        settings.get("maximum_price_deviation_from_signal_pct"),
        "maximum_price_deviation_from_signal_pct",
    )
    if maximum_deviation <= 0 or maximum_deviation > Decimal("0.20"):
        raise VirtualRssError(
            "maximum_price_deviation_from_signal_pct must be within (0, 0.20]"
        )
    buy_plans = _candidate_plan(
        state, candidate_batch.candidates, observed, eligibility, eligibility_status,
        policy, sizing_values, checked,
        float(candidate_age),
        float(maximum_deviation),
    )
    eligible_candidate_rows = json.loads(
        candidate_batch.candidates.to_json(
            orient="records", force_ascii=False, date_format="iso"
        )
    )
    quote_universe = [observed[ticker].as_dict() for ticker in sorted(observed)]
    sizing_policy_snapshot = json.loads(json.dumps(sizing_values))
    candidate_controls = {
        "maximum_candidate_age_hours": float(candidate_age),
        "maximum_price_deviation_from_signal_pct": float(maximum_deviation),
    }
    for plan in buy_plans:
        plan["candidate_input_sha256"] = candidate_batch.audit.input_sha256
        plan["eligible_candidates_sha256"] = (
            candidate_batch.audit.eligible_candidates_sha256
        )
        plan["eligibility_evidence_sha256"] = (
            eligibility_evidence_sha256
            if plan.get("route") == "RAKUTEN_KABU_MINI_SIM"
            else ""
        )
        plan["eligibility_entry"] = (
            dict(eligibility.get(str(plan.get("ticker", "")), {}))
            if plan.get("route") == "RAKUTEN_KABU_MINI_SIM"
            else {}
        )
        if plan.get("status") == "FILL_READY":
            plan["candidate_input_hex"] = candidate_input_hex
            plan["eligible_candidate_rows"] = eligible_candidate_rows
            plan["run_quote_universe"] = quote_universe
            plan["sizing_policy_snapshot"] = sizing_policy_snapshot
            plan["candidate_controls"] = candidate_controls
            plan["eligibility_status"] = eligibility_status
            plan["eligibility_evidence_snapshot"] = json.loads(
                json.dumps(eligibility_evidence)
            )
    exit_plans = _exit_plans(state, observed, policy, checked)
    plans = exit_plans + buy_plans
    run_id = _sha256({
        "contract": CONTRACT_ID,
        "trading_date": checked.date().isoformat(),
        "candidate_sha256": candidate_batch.audit.eligible_candidates_sha256,
        "quote_snapshot_sha256": lineage["snapshot_sha256"],
        "policy_sha256": policy_hash,
    })
    new_fills: list[dict[str, Any]] = []
    already_processed = run_id in state["processed_run_ids"]
    complete_quotes = not quote_errors and set(observed) == set(tickers)
    trading_day = False
    try:
        trading_day = is_jpx_equities_trading_day(checked.date())
    except ValueError:
        blockers.append("JPX_CALENDAR_UNSUPPORTED")
    if persist and not ledger_initialized:
        blockers.append("INITIALIZE_BEFORE_PAPER_RUN")
    should_commit = persist and ledger_initialized and not already_processed and complete_quotes
    if should_commit:
        ready_exits = [
            plan for plan in exit_plans if plan["status"] == "FILL_READY"
        ]
        for plan in ready_exits:
            new_fills.append(_append_fill(
                state, plan, side="SELL", quantity=int(plan["quantity"]),
                run_id=run_id, policy_hash=policy_hash, now=checked,
            ))
        fill_ready = [plan for plan in buy_plans if plan["status"] == "FILL_READY"]
        buys_today = sum(
            item.get("side") == "BUY"
            and _jst_datetime(item.get("created_at"), "fill created_at").date() == checked.date()
            for item in state["fills"]
        )
        if fill_ready and buys_today == 0:
            new_fills.append(_append_fill(
                state, fill_ready[0], side="BUY", quantity=int(fill_ready[0]["quantity"]),
                run_id=run_id, policy_hash=policy_hash, now=checked,
            ))
        elif fill_ready:
            blockers.append("DAILY_NEW_BUY_LIMIT_REACHED")
        if trading_day:
            state["observation_days"] = sorted(set(state["observation_days"] + [checked.date().isoformat()]))
        state["processed_run_ids"].append(run_id)
        state["updated_at"] = checked.isoformat(timespec="microseconds")
    elif persist and already_processed:
        blockers.append("IDEMPOTENT_RUN_ALREADY_PROCESSED")
    elif persist and not complete_quotes:
        blockers.append("QUOTE_FAILURE_NO_LEDGER_ADVANCE")
    if not persist:
        blockers.append("DRY_RUN_NO_LEDGER_WRITE")
    performance = _performance(state, observed, policy)
    any_fill_ready = any(plan.get("status") == "FILL_READY" for plan in plans)
    if persist and not ledger_initialized:
        report_status = "NOT_READY"
    elif not complete_quotes:
        report_status = "NOT_READY"
    elif ledger_initialized and any_fill_ready:
        report_status = "SIMULATION_READY"
    else:
        report_status = "MARK_ONLY"
    if not persist:
        run_effect = "DRY_RUN_NO_STATE_WRITE"
    elif not ledger_initialized:
        run_effect = "NOT_INITIALIZED_NO_STATE_WRITE"
    elif already_processed:
        run_effect = "IDEMPOTENT_NOOP"
    elif not complete_quotes:
        run_effect = "QUOTE_FAILURE_NO_STATE_WRITE"
    else:
        run_effect = "STATE_COMMIT_EXPECTED"
    expected_state_hash = _state_hash(state) if should_commit else (
        original_state_hash if ledger_initialized else ""
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "step": 21,
        "contract_id": CONTRACT_ID,
        "evidence_kind": EVIDENCE_KIND,
        "status": report_status,
        "mode": "VIRTUAL_PAPER_RUN" if persist else "DRY_RUN",
        "virtual_only": True,
        "eligible_for_real_rss_gate": False,
        "live_trading_enabled": False,
        "orders_allowed": False,
        "external_notifications_allowed": False,
        "external_orders_submitted": 0,
        "external_notifications_sent": 0,
        "real_rss_sessions_credited": 0,
        "paper_days_credited": 0,
        "audited_live_fills_credited": 0,
        "generated_at": checked.isoformat(timespec="seconds"),
        "trading_date": checked.date().isoformat(),
        "run_id": run_id,
        "run_effect": run_effect,
        "policy_sha256": policy_hash,
        "ledger_commit": {
            "binding_kind": "EXPECTED_STATE_SHA256",
            "state_update_planned": should_commit,
            "pre_state_sha256": original_state_hash if ledger_initialized else "",
            "expected_state_sha256": expected_state_hash,
        },
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
        "candidate_input": candidate_batch.audit.as_dict(),
        "quotes": {
            **lineage,
            "requested_count": len(tickers),
            "observed_count": len(observed),
            "fill_ready_count": sum(
                quote_readiness(quote, checked, policy, mini=False)[0] == "FILL_READY"
                for quote in observed.values()
            ),
            "model_only_bid_ask": any(q.bid is None for q in observed.values()),
        },
        "kabumini_eligibility_status": eligibility_status,
        "plans": plans,
        "fills": new_fills,
        "ledger_fill_count": len(state["fills"]),
        "performance": performance,
        "blockers": sorted(set(blockers + [reason for plan in plans for reason in plan.get("reasons", [])])),
    }
    preview = build_notification_preview(report)
    report["notification_preview"] = {
        key: value for key, value in preview.items() if key not in {"body", "chunks"}
    }
    with _exclusive_lock(lock_path):
        if should_commit:
            current = load_state(state_path)
            if current["state_sha256"] != original_state_hash:
                raise VirtualRssError("Virtual ledger changed during operation")
        atomic_write(report_json, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        atomic_write(report_text, _text_report(report))
        atomic_write(notification_json, json.dumps(preview, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        atomic_write(notification_text, _preview_text(preview))
        if should_commit:
            _save_state(state_path, state)
    return report


def initialize_virtual_ledger(root: Path, config: Mapping[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    repository = root.resolve()
    settings = config.get("virtual_rss_paper")
    if not isinstance(settings, Mapping):
        raise VirtualRssError("virtual_rss_paper config is missing")
    policy, policy_hash = load_policy(repository, settings)
    checked = now or datetime.now(JST)
    state_path = _safe_repo_path(repository, str(settings.get("state_file", "")), "state")
    paper_path = _safe_repo_path(repository, str(settings.get("source_paper_state", "")), "state")
    lock_path = _safe_repo_path(repository, str(settings.get("lock_file", "")), "state")
    with _exclusive_lock(lock_path):
        if state_path.exists():
            raise VirtualRssError("Virtual ledger already exists; reset is forbidden")
        state = new_state_from_paper(
            paper_path, now=checked, policy_sha256=policy_hash, policy=policy
        )
        _save_state(state_path, state)
    return state


def import_eligibility(
    root: Path, config: Mapping[str, Any], csv_path: Path, *, now: datetime | None = None
) -> dict[str, Any]:
    repository = root.resolve()
    settings = config.get("virtual_rss_paper")
    if not isinstance(settings, Mapping):
        raise VirtualRssError("virtual_rss_paper config is missing")
    policy, _ = load_policy(repository, settings)
    checked = now or datetime.now(JST)
    import_path = csv_path.resolve()
    runtime = (repository / "runtime/v7_virtual_rss").resolve()
    try:
        import_path.relative_to(runtime)
    except ValueError as error:
        raise VirtualRssError("Eligibility import CSV must be below runtime/v7_virtual_rss") from error
    if not import_path.is_file():
        raise VirtualRssError(
            "Kabu Mini eligibility CSV is missing; export and review the latest "
            "Rakuten Super Screener list before importing it"
        )
    evidence = build_eligibility_evidence(
        import_path, checked, source_url="RAKUTEN_SUPER_SCREENER_MANUAL_EXPORT"
    )
    destination = _safe_repo_path(repository, str(settings.get("kabumini_eligibility_file", "")), "state")
    lock_path = _safe_repo_path(repository, str(settings.get("lock_file", "")), "state")
    with _exclusive_lock(lock_path):
        if destination.is_file():
            load_eligibility(destination, checked, policy)
            existing = _load_json_object(destination, "Kabu Mini eligibility evidence")
            existing_time = _jst_datetime(existing.get("checked_at"), "existing eligibility.checked_at")
            if existing_time >= checked:
                raise VirtualRssError("Eligibility evidence cannot move backwards or overwrite the same time")
        atomic_write(destination, json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        loaded, status = load_eligibility(destination, checked, policy)
        if status != "VERIFIED" or len(loaded) != len(evidence["tickers"]):
            raise VirtualRssError("Eligibility evidence post-save verification failed")
    return evidence


def print_virtual_rss_summary(report: Mapping[str, Any]) -> None:
    quotes = report.get("quotes", {})
    environment = quotes.get("environment", {}) if isinstance(quotes, Mapping) else {}
    print(f"PHOENIX Step21 status: {report.get('status')}")
    print(f"Mode: {report.get('mode')}")
    print(f"Quotes: {quotes.get('observed_count', 0)}/{quotes.get('requested_count', 0)}")
    if isinstance(environment, Mapping) and environment:
        print(
            "Quote environment: "
            f"{environment.get('status')} / {environment.get('code')} / "
            f"TLS verification={environment.get('tls_verification_enabled')}"
        )
        if environment.get("remediation") not in (None, "", "NONE"):
            print(f"Quote remediation: {environment.get('remediation')}")
    print(f"Kabu Mini eligibility: {report.get('kabumini_eligibility_status', 'UNKNOWN')}")
    blockers = report.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        print(f"Blockers: {', '.join(str(value) for value in blockers)}")
    print(f"Virtual fills: {len(report.get('fills', []))}")
    print("External orders submitted: 0")
    print("External notifications sent: 0")
    print("Real RSS / paper-day / live-fill credit: 0 / 0 / 0")
