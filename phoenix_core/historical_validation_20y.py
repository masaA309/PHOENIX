from __future__ import annotations

import ast
import argparse
import calendar
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta
import json
import math
import os
import re
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest_engine import (  # type: ignore
    StrategyParameters as BacktestStrategyParameters,
    add_indicators,
    is_entry_signal,
    safe_float,
    signal_score,
)
from phoenix_core.data_freshness import EXPECTED_NIKKEI225_COUNT
from market_data_manager import fetch_history, load_cache, normalize_history as market_normalize_history, normalize_ticker
from phoenix_core.run_guard import SingleInstanceLock
from phoenix_core.virtual_rss_paper import prepare_quote_environment


JST = ZoneInfo("Asia/Tokyo")
MODULE_VERSION = "PHOENIX v7 Historical Validation 20Y"

DEFAULT_CONFIG_PATH = "config/v7_historical_validation_20y.json"
DEFAULT_OUTPUT_DIR = "reports/historical_validation_20y"
DEFAULT_LOCK_PATH = "state/v7_historical_validation_20y.lock"

DEFAULT_INITIAL_CAPITAL_YEN = 500_000.0
DEFAULT_LOT_SIZE = 100
DEFAULT_MAX_POSITIONS = 5
DEFAULT_MAX_POSITION_PCT = 0.30
DEFAULT_MAX_POSITION_HARD_PCT = 0.30
DEFAULT_MAX_TOTAL_INVESTED_PCT = 0.95
DEFAULT_MINIMUM_CASH_RESERVE_PCT = 0.0
DEFAULT_RISK_PER_TRADE_PCT = 0.01
DEFAULT_MAX_PORTFOLIO_RISK_PCT = 1.0
DEFAULT_MAXIMUM_QUANTITY_PER_TICKER = 1_000
DEFAULT_COMMISSION_RATE = 0.0
DEFAULT_SLIPPAGE_RATE = 0.0005
DEFAULT_STOP_ATR_MULTIPLIER = 1.5
DEFAULT_TARGET_R_MULTIPLIER = 2.0
DEFAULT_SIGNAL_SCORE_THRESHOLD = 70.0
DEFAULT_RSI_MIN = 40.0
DEFAULT_RSI_MAX = 72.0
DEFAULT_MA_SHORT = 5
DEFAULT_MA_MID = 25
DEFAULT_MA_LONG = 75
DEFAULT_MAX_HOLD_SESSIONS = 20
DEFAULT_MINIMUM_HISTORY_SESSIONS = 100
DEFAULT_REQUESTED_YEARS = 20
DEFAULT_ALLOW_NETWORK_FETCH = True
DEFAULT_BENCHMARK_TICKER = "^N225"

# Risk v2: point-in-time market breadth filter.
# OFF by default so Risk v1 remains byte-for-byte strategy compatible
# unless explicitly enabled by a validation config.
DEFAULT_MARKET_BREADTH_FILTER_ENABLED = False
DEFAULT_MARKET_BREADTH_BEAR_THRESHOLD = 0.40
DEFAULT_MARKET_BREADTH_BEAR_MAX_TOTAL_INVESTED_PCT = 0.70

TRADING_DAY_TOLERANCE_DAYS = 3
_QUOTE_TRANSPORT_INITIALIZED = False
HISTORY_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


class HistoricalValidationError(RuntimeError):
    pass


def configure_quote_transport() -> dict[str, Any]:
    environment, ca_bundle = prepare_quote_environment()
    if ca_bundle is None or environment.get("status") != "READY":
        raise HistoricalValidationError(
            "Quote transport is unavailable: "
            f"{environment.get('code')} / {environment.get('remediation')}"
        )
    for name in ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE"):
        os.environ[name] = str(ca_bundle)
    return environment


def _ensure_quote_transport() -> dict[str, Any] | None:
    global _QUOTE_TRANSPORT_INITIALIZED
    if _QUOTE_TRANSPORT_INITIALIZED:
        return None
    environment = configure_quote_transport()
    _QUOTE_TRANSPORT_INITIALIZED = True
    return environment


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
            temporary = Path(file.name)
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2 * (attempt + 1))
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class HistoricalValidationConfig:
    initial_capital_yen: float = DEFAULT_INITIAL_CAPITAL_YEN
    lot_size: int = DEFAULT_LOT_SIZE
    max_positions: int = DEFAULT_MAX_POSITIONS
    max_position_pct: float = DEFAULT_MAX_POSITION_PCT
    max_position_hard_pct: float = DEFAULT_MAX_POSITION_HARD_PCT
    max_total_invested_pct: float = DEFAULT_MAX_TOTAL_INVESTED_PCT
    minimum_cash_reserve_pct: float = DEFAULT_MINIMUM_CASH_RESERVE_PCT
    risk_per_trade_pct: float = DEFAULT_RISK_PER_TRADE_PCT
    max_portfolio_risk_pct: float = DEFAULT_MAX_PORTFOLIO_RISK_PCT
    maximum_quantity_per_ticker: int = DEFAULT_MAXIMUM_QUANTITY_PER_TICKER
    commission_rate: float = DEFAULT_COMMISSION_RATE
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE
    stop_atr_multiplier: float = DEFAULT_STOP_ATR_MULTIPLIER
    target_r_multiplier: float = DEFAULT_TARGET_R_MULTIPLIER
    signal_score_threshold: float = DEFAULT_SIGNAL_SCORE_THRESHOLD
    rsi_min: float = DEFAULT_RSI_MIN
    rsi_max: float = DEFAULT_RSI_MAX
    ma_short: int = DEFAULT_MA_SHORT
    ma_mid: int = DEFAULT_MA_MID
    ma_long: int = DEFAULT_MA_LONG
    max_hold_sessions: int = DEFAULT_MAX_HOLD_SESSIONS
    minimum_history_sessions: int = DEFAULT_MINIMUM_HISTORY_SESSIONS
    requested_years: int = DEFAULT_REQUESTED_YEARS
    allow_network_fetch: bool = DEFAULT_ALLOW_NETWORK_FETCH
    universe_csv: str = "data/nikkei225.csv"
    benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER
    market_breadth_filter_enabled: bool = DEFAULT_MARKET_BREADTH_FILTER_ENABLED
    market_breadth_bear_threshold: float = DEFAULT_MARKET_BREADTH_BEAR_THRESHOLD
    market_breadth_bear_max_total_invested_pct: float = DEFAULT_MARKET_BREADTH_BEAR_MAX_TOTAL_INVESTED_PCT
    output_dir: str = DEFAULT_OUTPUT_DIR
    report_json: str = "reports/historical_validation_20y/summary.json"
    report_text: str = "reports/historical_validation_20y/report.txt"
    annual_returns_csv: str = "reports/historical_validation_20y/annual_returns.csv"
    monthly_returns_csv: str = "reports/historical_validation_20y/monthly_returns.csv"
    data_coverage_csv: str = "reports/historical_validation_20y/data_coverage.csv"
    trades_csv: str = "reports/historical_validation_20y/trades.csv"
    equity_curve_csv: str = "reports/historical_validation_20y/equity_curve.csv"
    benchmark_enabled: bool = True
    no_rss: bool = True
    no_real_orders: bool = True
    live_trading_enabled: bool = False
    orders_submitted: int = 0

    def validate(self) -> None:
        numeric_values = {
            "initial_capital_yen": self.initial_capital_yen,
            "max_position_pct": self.max_position_pct,
            "max_total_invested_pct": self.max_total_invested_pct,
            "minimum_cash_reserve_pct": self.minimum_cash_reserve_pct,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "commission_rate": self.commission_rate,
            "slippage_rate": self.slippage_rate,
            "stop_atr_multiplier": self.stop_atr_multiplier,
            "target_r_multiplier": self.target_r_multiplier,
            "signal_score_threshold": self.signal_score_threshold,
            "rsi_min": self.rsi_min,
            "rsi_max": self.rsi_max,
            "market_breadth_bear_threshold": self.market_breadth_bear_threshold,
            "market_breadth_bear_max_total_invested_pct": self.market_breadth_bear_max_total_invested_pct,
        }
        for name, value in numeric_values.items():
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite")
        if self.initial_capital_yen <= 0:
            raise ValueError("initial_capital_yen must be positive")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if self.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if not 0 <= self.max_position_pct <= 1:
            raise ValueError("max_position_pct must be within [0, 1]")
        if not 0 < self.max_position_hard_pct <= 1:
            raise ValueError("max_position_hard_pct must be within (0, 1]")
        if self.max_position_hard_pct < self.max_position_pct:
            raise ValueError("max_position_hard_pct must be >= max_position_pct")
        if not 0 <= self.max_total_invested_pct <= 1:
            raise ValueError("max_total_invested_pct must be within [0, 1]")
        if not 0 <= self.minimum_cash_reserve_pct <= 1:
            raise ValueError("minimum_cash_reserve_pct must be within [0, 1]")
        if self.risk_per_trade_pct <= 0:
            raise ValueError("risk_per_trade_pct must be positive")
        if not 0 < self.max_portfolio_risk_pct <= 1:
            raise ValueError("max_portfolio_risk_pct must be within (0, 1]")
        if self.maximum_quantity_per_ticker <= 0:
            raise ValueError("maximum_quantity_per_ticker must be positive")
        if self.commission_rate < 0:
            raise ValueError("commission_rate must be non-negative")
        if self.slippage_rate < 0:
            raise ValueError("slippage_rate must be non-negative")
        if self.stop_atr_multiplier <= 0 or self.target_r_multiplier <= 0:
            raise ValueError("ATR multipliers must be positive")
        if self.signal_score_threshold < 0:
            raise ValueError("signal_score_threshold must be non-negative")
        if not 0 <= self.rsi_min < self.rsi_max <= 100:
            raise ValueError("rsi_min and rsi_max must satisfy 0 <= min < max <= 100")
        if not 1 <= self.ma_short < self.ma_mid < self.ma_long:
            raise ValueError("MA periods must satisfy ma_short < ma_mid < ma_long")
        if self.max_hold_sessions <= 0:
            raise ValueError("max_hold_sessions must be positive")
        if self.minimum_history_sessions <= 0:
            raise ValueError("minimum_history_sessions must be positive")
        if self.requested_years <= 0:
            raise ValueError("requested_years must be positive")
        if not self.universe_csv:
            raise ValueError("universe_csv must not be empty")
        if not self.benchmark_ticker:
            raise ValueError("benchmark_ticker must not be empty")
        if not 0 <= self.market_breadth_bear_threshold <= 1:
            raise ValueError("market_breadth_bear_threshold must be within [0, 1]")
        if not 0 <= self.market_breadth_bear_max_total_invested_pct <= 1:
            raise ValueError("market_breadth_bear_max_total_invested_pct must be within [0, 1]")
        if self.market_breadth_bear_max_total_invested_pct > self.max_total_invested_pct:
            raise ValueError(
                "market_breadth_bear_max_total_invested_pct must be <= max_total_invested_pct"
            )

    def strategy_parameters(self) -> BacktestStrategyParameters:
        return BacktestStrategyParameters(
            rsi_min=self.rsi_min,
            rsi_max=self.rsi_max,
            stop_atr_multiplier=self.stop_atr_multiplier,
            target_r_multiplier=self.target_r_multiplier,
            ma_short=self.ma_short,
            ma_mid=self.ma_mid,
            ma_long=self.ma_long,
            signal_score_threshold=self.signal_score_threshold,
            max_hold_days=self.max_hold_sessions,
        )


@dataclass(slots=True)
class PositionState:
    ticker: str
    company_name: str
    signal_date: str
    entry_date: str
    entry_session_index: int
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float
    signal_score: float
    entry_cost_yen: float
    actual_stop_price: float = 0.0
    actual_target_price: float = 0.0


@dataclass(slots=True)
class PendingOrder:
    ticker: str
    company_name: str
    signal_date: str
    entry_date: str
    entry_session_index: int
    quantity: int
    stop_price: float
    target_price: float
    signal_score: float
    estimated_cost_yen: float
    estimated_entry_price: float = 0.0


@dataclass(slots=True)
class EntryCandidate:
    ticker: str
    company_name: str
    signal_date: str
    entry_date: str
    entry_session_index: int
    signal_score: float
    estimated_entry_price: float
    stop_price: float
    target_price: float
    next_date: pd.Timestamp


@dataclass(slots=True)
class TradeRecord:
    ticker: str
    company_name: str
    signal_date: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    entry_cost_yen: float
    exit_value_yen: float
    gross_profit_yen: float
    fees_yen: float
    profit_yen: float
    return_pct: float
    holding_sessions: int
    exit_reason: str
    signal_score: float


DIAGNOSTIC_REASONS = (
    "SIGNAL_CANDIDATE",
    "REJECT_RISK_SIZE",
    "REJECT_POSITION_LIMIT",
    "REJECT_CASH",
    "REJECT_TOTAL_EXPOSURE",
    "REJECT_MAX_QUANTITY",
    "PENDING_CREATED",
    "D1_REJECT_RISK_SIZE",
    "D1_REJECT_POSITION_LIMIT",
    "D1_REJECT_CASH",
    "D1_REJECT_TOTAL_EXPOSURE",
    "D1_FILLED",
    "REJECT_PORTFOLIO_RISK",
    "D1_REJECT_PORTFOLIO_RISK",
)


def _empty_diagnostics_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["year", "reason", "count"])


RISK_V2_RESEARCH_COLUMNS = (
    "date",
    "market_regime",
    "market_breadth_above_ma_long_pct",
    "effective_max_total_invested_pct",
)


def _empty_risk_v2_research_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=list(RISK_V2_RESEARCH_COLUMNS))


@dataclass(slots=True)
class HistoricalValidationResult:
    trades: pd.DataFrame
    equity_curve: pd.DataFrame
    annual_returns: pd.DataFrame
    monthly_returns: pd.DataFrame
    rejected_due_to_lot: int = 0
    rejected_due_to_buying_power: int = 0
    diagnostics: pd.DataFrame = field(default_factory=_empty_diagnostics_frame)
    risk_v2_research: pd.DataFrame = field(default_factory=_empty_risk_v2_research_frame)


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def resolve_within(root: Path, value: str) -> Path:
    candidate = Path(value)
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    root_resolved = root.resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"Path escapes repository root: {value}") from error
    return path


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read JSON object: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def read_csv_flexible(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Required CSV file not found: {path}")
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
        except Exception as error:
            last_error = error
    if last_error is not None:
        raise last_error
    return pd.DataFrame()


def normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    return text


def normalize_ticker_code(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    if text.startswith("^"):
        return text.upper()
    return normalize_ticker(text).strip().upper()


def normalize_history_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    work = frame.copy()
    work.index = pd.to_datetime(work.index, errors="coerce")
    work = work[~work.index.isna()]
    if getattr(work.index, "tz", None) is not None:
        work.index = work.index.tz_localize(None)
    work.index = pd.DatetimeIndex(work.index).normalize()
    work = work[~work.index.duplicated(keep="last")]
    return work.sort_index()


def _strip_cache_suffix(value: Any) -> str:
    return re.sub(r"\.\d+$", "", normalize_text(value)).strip()


def _legacy_cache_column_to_field(value: Any) -> str | None:
    column = _strip_cache_suffix(value)
    if not column:
        return None
    normalized = column.lower().replace(" ", "")
    direct_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "adjclose": "Close",
    }
    if normalized in direct_map:
        return direct_map[normalized]
    if column.startswith("(") and column.endswith(")"):
        try:
            parsed = ast.literal_eval(column)
        except (SyntaxError, ValueError):
            parsed = None
        if isinstance(parsed, tuple) and parsed:
            field = str(parsed[0]).strip().lower().replace(" ", "")
            if field in direct_map:
                return direct_map[field]
    return None


def _is_date_like_column(value: Any) -> bool:
    column = _strip_cache_suffix(value).lower()
    return column in {"date", "price"} or column.startswith("unnamed")


def _valid_ohlcv_mask(frame: pd.DataFrame) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=bool)
    required = [column for column in HISTORY_COLUMNS if column in frame.columns]
    if len(required) != len(HISTORY_COLUMNS):
        return pd.Series(False, index=frame.index)

    values = {column: pd.to_numeric(frame[column], errors="coerce") for column in HISTORY_COLUMNS}
    # Allow tiny floating-point drift when checking OHLC consistency.
    row_max = pd.DataFrame({column: values[column] for column in ("Open", "High", "Low", "Close")}).max(axis=1)
    tolerance = row_max * 1e-9
    mask = (
        (values["Open"] > 0)
        & (values["High"] > 0)
        & (values["Low"] > 0)
        & (values["Close"] > 0)
        & (values["High"] + tolerance >= values["Low"])
        & (values["High"] + tolerance >= values["Open"])
        & (values["High"] + tolerance >= values["Close"])
        & (values["Low"] - tolerance <= values["Open"])
        & (values["Low"] - tolerance <= values["Close"])
    )
    if isinstance(frame.index, pd.DatetimeIndex):
        index_dates = frame.index.normalize()
    else:
        index_dates = pd.to_datetime(frame.index, errors="coerce")
        mask &= index_dates.notna()
        index_dates = pd.DatetimeIndex(index_dates).normalize()
    mask &= index_dates != pd.Timestamp("1970-01-01")
    return mask.fillna(False)


def _canonicalize_cached_history(raw: pd.DataFrame, *, ticker: str = "") -> tuple[pd.DataFrame, bool]:
    if raw.empty:
        return pd.DataFrame(), False

    columns = [_strip_cache_suffix(column) for column in raw.columns]
    canonical_columns = ["Date", *HISTORY_COLUMNS]
    is_current_layout = columns == canonical_columns

    working = raw.copy()
    date_positions: list[tuple[int, int]] = []
    for position, column in enumerate(working.columns):
        if not _is_date_like_column(column):
            continue
        raw_series = working.iloc[:, position]
        if pd.api.types.is_numeric_dtype(raw_series):
            continue
        normalized_column = _strip_cache_suffix(column).lower()
        priority = 0 if normalized_column == "date" else 1 if normalized_column == "price" else 2
        date_positions.append((priority, position))

    if not date_positions:
        return pd.DataFrame(), True

    row_count = len(working)
    date_values = np.full(row_count, np.datetime64("NaT"), dtype="datetime64[ns]")
    # Legacy rows may carry the session date in Date, then Price, then Unnamed columns.
    for _, position in sorted(date_positions):
        candidate = pd.to_datetime(working.iloc[:, position].astype("string"), errors="coerce")
        if getattr(candidate.dt, "tz", None) is not None:
            candidate = candidate.dt.tz_localize(None)
        candidate = candidate.dt.normalize()
        candidate = candidate.where(candidate != pd.Timestamp("1970-01-01"))
        candidate_values = candidate.to_numpy()
        fill_mask = pd.isna(date_values) & ~pd.isna(candidate_values)
        date_values[fill_mask] = candidate_values[fill_mask]

    date_index = pd.DatetimeIndex(date_values)
    if getattr(date_index, "tz", None) is not None:
        date_index = date_index.tz_localize(None)
    date_index = date_index.normalize()

    frame_data: dict[str, np.ndarray] = {}
    for field in HISTORY_COLUMNS:
        positions = [position for position, column in enumerate(working.columns) if _legacy_cache_column_to_field(column) == field]
        if not positions:
            return pd.DataFrame(), True
        block = working.iloc[:, positions].apply(pd.to_numeric, errors="coerce")
        frame_data[field] = pd.to_numeric(block.bfill(axis=1).to_numpy()[:, 0], errors="coerce")

    legacy = pd.DataFrame(frame_data, index=date_index)
    legacy = legacy[~legacy.index.isna()]
    if legacy.empty:
        return pd.DataFrame(), True
    legacy = legacy[legacy.index != pd.Timestamp("1970-01-01")]
    if legacy.empty:
        return pd.DataFrame(), True
    legacy = legacy.groupby(level=0).first()
    legacy.index.name = "Date"
    normalized = market_normalize_history(legacy, ticker)
    cleaned = normalized.loc[_valid_ohlcv_mask(normalized)].copy() if not normalized.empty else normalized
    migrated = (not is_current_layout) or len(cleaned) != len(normalized) or not cleaned.equals(normalized)
    return cleaned, migrated


def load_universe(root: Path, config: HistoricalValidationConfig) -> pd.DataFrame:
    universe_path = resolve_within(root, config.universe_csv)
    frame = read_csv_flexible(universe_path)
    return _normalize_universe_for_validation(frame)


def _parse_membership_bound(value: Any) -> pd.Timestamp | None:
    if isinstance(value, (list, tuple, dict, set)):
        raise HistoricalValidationError("Membership boundaries must be scalar values")
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except Exception:
        pass
    text = normalize_text(value)
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    try:
        timestamp = pd.Timestamp(text)
    except Exception as error:
        raise HistoricalValidationError(f"Invalid membership date: {value}") from error
    if pd.isna(timestamp):
        return None
    if getattr(timestamp, "tzinfo", None) is not None:
        timestamp = timestamp.tz_convert(None)
    return timestamp.normalize()


def _coerce_member_periods(value: Any) -> list[tuple[pd.Timestamp | None, pd.Timestamp | None]]:
    if isinstance(value, tuple) and len(value) == 2 and not any(isinstance(item, (list, tuple)) for item in value):
        return [(_parse_membership_bound(value[0]), _parse_membership_bound(value[1]))]
    if isinstance(value, list):
        periods: list[tuple[pd.Timestamp | None, pd.Timestamp | None]] = []
        for item in value:
            if item is None:
                continue
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise HistoricalValidationError("member_periods must contain (member_from, member_until) pairs")
            periods.append((_parse_membership_bound(item[0]), _parse_membership_bound(item[1])))
        return periods or [(None, None)]
    if value is None:
        return [(None, None)]
    try:
        if bool(pd.isna(value)):
            return [(None, None)]
    except Exception:
        pass
    raise HistoricalValidationError("member_periods must contain (member_from, member_until) pairs")


def _merge_membership_periods(
    periods: Iterable[tuple[pd.Timestamp | None, pd.Timestamp | None]]
) -> list[tuple[pd.Timestamp | None, pd.Timestamp | None]]:
    normalized: list[tuple[pd.Timestamp | None, pd.Timestamp | None]] = []
    for member_from, member_until in periods:
        start = _parse_membership_bound(member_from)
        until = _parse_membership_bound(member_until)
        if start is not None and until is not None and until <= start:
            raise HistoricalValidationError("member_until must be after member_from")
        normalized.append((start, until))
    if not normalized:
        return [(None, None)]

    normalized.sort(key=lambda item: item[0] if item[0] is not None else pd.Timestamp.min)
    merged: list[tuple[pd.Timestamp | None, pd.Timestamp | None]] = []
    for start, until in normalized:
        if not merged:
            merged.append((start, until))
            continue
        prev_start, prev_until = merged[-1]
        if prev_until is None:
            continue
        if start is None or start <= prev_until:
            if prev_until is None or until is None:
                merged[-1] = (prev_start, None)
            else:
                merged[-1] = (prev_start, max(prev_until, until))
        else:
            merged.append((start, until))
    return merged


def _normalize_universe_for_validation(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise HistoricalValidationError("Ticker universe is empty")
    ticker_column = next((column for column in ("ticker", "Ticker", "code", "Code") if column in frame.columns), None)
    if ticker_column is None:
        raise HistoricalValidationError("Ticker universe must contain a ticker column")
    name_column = next((column for column in ("name", "Name", "company_name", "CompanyName") if column in frame.columns), None)
    has_member_from = "member_from" in frame.columns
    has_member_until = "member_until" in frame.columns
    has_member_periods = "member_periods" in frame.columns
    has_membership = has_member_from or has_member_until or has_member_periods

    records: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for _, raw in frame.iterrows():
        ticker = normalize_ticker_code(raw[ticker_column])
        if not ticker:
            continue
        company_name = normalize_text(raw.get(name_column), ticker) if name_column is not None else ticker
        if ticker not in records:
            record: dict[str, Any] = {
                "ticker": ticker,
                "company_name": company_name,
            }
            if has_membership:
                record["member_periods"] = []
            records[ticker] = record
            order.append(ticker)
        record = records[ticker]
        if company_name and record.get("company_name", ticker) in ("", ticker):
            record["company_name"] = company_name
        if has_membership:
            if has_member_periods:
                periods = _coerce_member_periods(raw.get("member_periods"))
            else:
                periods = [(
                    _parse_membership_bound(raw.get("member_from")) if has_member_from else None,
                    _parse_membership_bound(raw.get("member_until")) if has_member_until else None,
                )]
            record["member_periods"].extend(periods)

    normalized_rows: list[dict[str, Any]] = []
    for ticker in order:
        record = records[ticker]
        if has_membership:
            record["member_periods"] = _merge_membership_periods(record["member_periods"])
        normalized_rows.append(record)
    normalized = pd.DataFrame(normalized_rows)
    if normalized.empty:
        raise HistoricalValidationError("Ticker universe does not contain usable tickers")
    return normalized.reset_index(drop=True)


def _days_within_periods(
    days: pd.DatetimeIndex,
    periods: Iterable[tuple[pd.Timestamp | None, pd.Timestamp | None]],
) -> pd.DatetimeIndex:
    if days.empty:
        return days
    period_list = list(periods)
    if not period_list:
        return days
    mask = np.zeros(len(days), dtype=bool)
    for member_from, member_until in period_list:
        window = np.ones(len(days), dtype=bool)
        if member_from is not None:
            window &= days >= member_from
        if member_until is not None:
            window &= days < member_until
        mask |= window
    return days[mask]


def _is_member_on_date(
    periods: Iterable[tuple[pd.Timestamp | None, pd.Timestamp | None]],
    current_date: pd.Timestamp,
) -> bool:
    period_list = list(periods)
    if not period_list:
        return True
    current_ts = pd.Timestamp(current_date).normalize()
    for member_from, member_until in period_list:
        if member_from is not None and current_ts < member_from:
            continue
        if member_until is not None and current_ts >= member_until:
            continue
        return True
    return False


def load_history_series(
    ticker: str,
    *,
    allow_network_fetch: bool,
) -> tuple[pd.DataFrame, str]:
    normalized = normalize_ticker_code(ticker)
    if not normalized:
        return pd.DataFrame(), "invalid_ticker"
    if not allow_network_fetch:
        cached = load_cache(normalized)
        return cached, "cache" if not cached.empty else "failed"
    try:
        history, source = fetch_history(
            normalized,
            period="max",
            allow_cache=True,
            force_refresh=True,
        )
        return history, source
    except Exception as error:
        cached = load_cache(normalized)
        if not cached.empty:
            return cached, f"cache_fallback:{type(error).__name__}"
        return pd.DataFrame(), f"failed:{type(error).__name__}"


def acquire_histories(
    universe: pd.DataFrame,
    config: HistoricalValidationConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    histories: dict[str, pd.DataFrame] = {}
    sources: dict[str, str] = {}
    for _, row in universe.iterrows():
        ticker = normalize_ticker_code(row["ticker"])
        try:
            history, source = load_history_series(ticker, allow_network_fetch=config.allow_network_fetch)
        except Exception as error:
            histories[ticker] = pd.DataFrame()
            sources[ticker] = f"failed:{type(error).__name__}"
            continue
        histories[ticker] = history.copy()
        sources[ticker] = source
    return histories, sources


def prepare_histories(
    histories: Mapping[str, pd.DataFrame],
    config: HistoricalValidationConfig,
) -> dict[str, pd.DataFrame]:
    strategy = config.strategy_parameters()
    prepared: dict[str, pd.DataFrame] = {}
    for ticker, frame in histories.items():
        if frame.empty:
            prepared[ticker] = frame.copy()
            continue
        work = normalize_history_frame(frame)
        prepared[ticker] = add_indicators(work, strategy)
    return prepared


def _valid_ohlcv_history(frame: pd.DataFrame) -> pd.DataFrame:
    history = normalize_history_frame(frame)
    if history.empty:
        return history
    return history.loc[_valid_ohlcv_mask(history)].copy()


def _market_days_for_history(frame: pd.DataFrame) -> pd.DatetimeIndex:
    history = _valid_ohlcv_history(frame)
    if history.empty:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(history.index).unique().sort_values()


def _market_day_basis_from_histories(histories: Iterable[pd.DataFrame]) -> pd.DatetimeIndex:
    counts: Counter[pd.Timestamp] = Counter()
    valid_history_count = 0
    for history in histories:
        market_days = _market_days_for_history(history)
        if market_days.empty:
            continue
        valid_history_count += 1
        counts.update(market_days.tolist())
    if valid_history_count == 0:
        return pd.DatetimeIndex([])
    threshold = math.ceil(valid_history_count / 2)
    basis = sorted(day for day, count in counts.items() if count >= threshold)
    return pd.DatetimeIndex(basis)


def floor_to_lot(quantity: int, lot_size: int) -> int:
    if quantity <= 0:
        return 0
    return (quantity // lot_size) * lot_size


def calculate_shares(
    *,
    current_equity: float,
    available_cash: float,
    entry_price: float,
    stop_price: float,
    current_exposure: float,
    config: HistoricalValidationConfig,
    current_portfolio_risk_yen: float = 0.0,
    max_total_invested_pct_override: float | None = None,
) -> int:
    limits = _share_sizing_limits(
        current_equity=current_equity,
        available_cash=available_cash,
        entry_price=entry_price,
        stop_price=stop_price,
        current_exposure=current_exposure,
        current_portfolio_risk_yen=current_portfolio_risk_yen,
        config=config,
        max_total_invested_pct_override=max_total_invested_pct_override,
    )
    quantity = min(
        limits["risk_quantity"],
        limits["portfolio_risk_quantity"],
        limits["position_limit_quantity"],
        limits["cash_limit_quantity"],
        limits["portfolio_limit_quantity"],
    )
    return max(floor_to_lot(quantity, config.lot_size), 0)


def _share_sizing_limits(
    *,
    current_equity: float,
    available_cash: float,
    entry_price: float,
    stop_price: float,
    current_exposure: float,
    config: HistoricalValidationConfig,
    current_portfolio_risk_yen: float = 0.0,
    max_total_invested_pct_override: float | None = None,
) -> dict[str, int]:
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return {
            "risk_quantity": 0,
            "portfolio_risk_quantity": 0,
            "position_limit_quantity": 0,
            "cash_limit_quantity": 0,
            "portfolio_limit_quantity": 0,
            "maximum_quantity_per_ticker": int(config.maximum_quantity_per_ticker),
        }

    risk_per_share = entry_price - stop_price

    # Per-trade risk:
    # each position may lose at most risk_per_trade_pct of current equity
    # when its initial stop is hit.
    risk_budget = current_equity * config.risk_per_trade_pct
    risk_quantity = int(risk_budget // risk_per_share)

    # Portfolio risk:
    # sum of stop-loss risk for open + committed positions is capped.
    remaining_portfolio_risk = max(
        current_equity * config.max_portfolio_risk_pct
        - max(current_portfolio_risk_yen, 0.0),
        0.0,
    )
    portfolio_risk_quantity = int(remaining_portfolio_risk // risk_per_share)

    # Position concentration:
    # max_position_pct is the normal soft cap.
    # If one standard lot alone exceeds the soft cap, one lot may be
    # accepted only when it remains inside max_position_hard_pct.
    soft_position_value = current_equity * config.max_position_pct
    hard_position_value = current_equity * config.max_position_hard_pct

    soft_position_quantity = int(soft_position_value // entry_price)
    one_lot_value = entry_price * config.lot_size

    if (
        soft_position_quantity < config.lot_size
        and one_lot_value <= hard_position_value + 1e-9
    ):
        position_limit_quantity = config.lot_size
    else:
        position_limit_quantity = soft_position_quantity

    # Cash:
    # v1 uses no separate mandatory cash reserve; the portfolio exposure
    # cap is the single capital-utilisation limit.
    spendable_cash = max(
        available_cash - current_equity * config.minimum_cash_reserve_pct,
        0.0,
    )
    buffered_unit_price = entry_price * (1.0 + max(config.commission_rate, 0.0))
    cash_limit_quantity = int(spendable_cash // buffered_unit_price)

    # Total invested capital.
    effective_max_total_invested_pct = config.max_total_invested_pct
    if max_total_invested_pct_override is not None:
        effective_max_total_invested_pct = min(
            config.max_total_invested_pct,
            max(float(max_total_invested_pct_override), 0.0),
        )

    portfolio_capacity = max(
        current_equity * effective_max_total_invested_pct - current_exposure,
        0.0,
    )
    portfolio_limit_quantity = int(portfolio_capacity // entry_price)

    return {
        "risk_quantity": risk_quantity,
        "portfolio_risk_quantity": portfolio_risk_quantity,
        "position_limit_quantity": position_limit_quantity,
        "cash_limit_quantity": cash_limit_quantity,
        "portfolio_limit_quantity": portfolio_limit_quantity,

        # Retained only for backwards-compatible config/report parsing.
        # PHOENIX risk v1 does NOT use a fixed share-count ceiling as a
        # strategy sizing constraint.
        "maximum_quantity_per_ticker": int(config.maximum_quantity_per_ticker),
    }


def _classify_share_rejection_reason(
    *,
    current_equity: float,
    available_cash: float,
    entry_price: float,
    stop_price: float,
    current_exposure: float,
    config: HistoricalValidationConfig,
    d1: bool,
    current_portfolio_risk_yen: float = 0.0,
    max_total_invested_pct_override: float | None = None,
) -> str:
    limits = _share_sizing_limits(
        current_equity=current_equity,
        available_cash=available_cash,
        entry_price=entry_price,
        stop_price=stop_price,
        current_exposure=current_exposure,
        current_portfolio_risk_yen=current_portfolio_risk_yen,
        config=config,
        max_total_invested_pct_override=max_total_invested_pct_override,
    )

    lot_size = config.lot_size

    if limits["risk_quantity"] < lot_size:
        return "D1_REJECT_RISK_SIZE" if d1 else "REJECT_RISK_SIZE"

    if limits["portfolio_risk_quantity"] < lot_size:
        return "D1_REJECT_PORTFOLIO_RISK" if d1 else "REJECT_PORTFOLIO_RISK"

    if limits["position_limit_quantity"] < lot_size:
        return "D1_REJECT_POSITION_LIMIT" if d1 else "REJECT_POSITION_LIMIT"

    if limits["cash_limit_quantity"] < lot_size:
        return "D1_REJECT_CASH" if d1 else "REJECT_CASH"

    if limits["portfolio_limit_quantity"] < lot_size:
        return "D1_REJECT_TOTAL_EXPOSURE" if d1 else "REJECT_TOTAL_EXPOSURE"

    return ""


def _position_risk_yen(position: Any) -> float:
    entry_price = safe_float(getattr(position, "entry_price", 0.0))
    stop_price = safe_float(
        getattr(position, "actual_stop_price", 0.0)
        or getattr(position, "stop_price", 0.0)
    )
    quantity = int(getattr(position, "quantity", 0) or 0)

    return max(entry_price - stop_price, 0.0) * max(quantity, 0)


def _pending_order_risk_yen(order: Any) -> float:
    entry_price = safe_float(getattr(order, "estimated_entry_price", 0.0))
    stop_price = safe_float(getattr(order, "stop_price", 0.0))
    quantity = int(getattr(order, "quantity", 0) or 0)

    return max(entry_price - stop_price, 0.0) * max(quantity, 0)


def _positions_portfolio_risk_yen(
    positions: Mapping[str, Any],
) -> float:
    return float(sum(_position_risk_yen(position) for position in positions.values()))


def _pending_portfolio_risk_yen(
    pending_orders: Mapping[pd.Timestamp, list[Any]],
) -> float:
    return float(
        sum(
            _pending_order_risk_yen(order)
            for orders in pending_orders.values()
            for order in orders
        )
    )


def _build_diagnostics_frame(diagnostics_counts: Counter[tuple[int, str]], start_year: int, end_year: int) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        for reason in DIAGNOSTIC_REASONS:
            rows.append(
                {
                    "year": year,
                    "reason": reason,
                    "count": int(diagnostics_counts.get((year, reason), 0)),
                }
            )
    if not rows:
        return _empty_diagnostics_frame()
    return pd.DataFrame(rows, columns=["year", "reason", "count"])


def _last_available_date(frame: pd.DataFrame) -> pd.Timestamp | None:
    if frame.empty:
        return None
    return pd.Timestamp(frame.index.max()).normalize()


def _is_positive_finite_price(price: float) -> bool:
    return math.isfinite(price) and price > 0


def _last_positive_price(values: Iterable[Any]) -> float:
    for value in reversed(list(values)):
        price = safe_float(value)
        if _is_positive_finite_price(price):
            return price
    return 0.0


def _history_close_at_or_before(frame: pd.DataFrame, date: pd.Timestamp) -> float:
    if frame.empty:
        return 0.0
    available = frame.loc[frame.index <= date, "Close"]
    if available.empty:
        return 0.0
    return _last_positive_price(available.sort_index().tolist())


def _history_open_at_or_before(frame: pd.DataFrame, date: pd.Timestamp) -> float:
    if frame.empty:
        return 0.0
    if date in frame.index:
        open_price = safe_float(frame.loc[date]["Open"])
        if _is_positive_finite_price(open_price):
            return open_price
    available = frame.loc[frame.index < date, "Close"]
    if available.empty:
        return 0.0
    return _last_positive_price(available.sort_index().tolist())


def _close_position(
    *,
    positions: dict[str, PositionState],
    ticker: str,
    exit_date: pd.Timestamp,
    exit_price: float,
    reason: str,
    session_index: int,
    config: HistoricalValidationConfig,
    trades: list[TradeRecord],
) -> float:
    position = positions[ticker]
    holding_sessions = max(session_index - position.entry_session_index + 1, 1)
    entry_value = position.entry_price * position.quantity
    entry_fee = position.entry_cost_yen - entry_value
    exit_value = exit_price * position.quantity
    exit_fee = exit_value * config.commission_rate
    fees_yen = entry_fee + exit_fee
    gross_profit = exit_value - entry_value
    profit = gross_profit - fees_yen
    trades.append(
        TradeRecord(
            ticker=ticker,
            company_name=position.company_name,
            signal_date=position.signal_date,
            entry_date=position.entry_date,
            exit_date=exit_date.date().isoformat(),
            entry_price=round(position.entry_price, 4),
            exit_price=round(exit_price, 4),
            quantity=position.quantity,
            entry_cost_yen=round(position.entry_cost_yen, 2),
            exit_value_yen=round(exit_value, 2),
            gross_profit_yen=round(gross_profit, 2),
            fees_yen=round(fees_yen, 2),
            profit_yen=round(profit, 2),
            return_pct=round(profit / position.entry_cost_yen * 100, 4) if position.entry_cost_yen > 0 else 0.0,
            holding_sessions=holding_sessions,
            exit_reason=reason,
            signal_score=round(position.signal_score, 2),
        )
    )
    del positions[ticker]
    # BUY: cash -= entry_cost_yen (entry fee is already embedded)
    # SELL: cash += exit_value - exit_fee
    return exit_value - exit_fee


def _market_breadth_above_ma_long_ratio(
    *,
    prepared_histories: Mapping[str, pd.DataFrame],
    membership_lookup: Mapping[str, Any],
    current_date: pd.Timestamp,
    uses_membership: bool,
) -> float | None:
    eligible = 0
    above = 0

    for ticker, frame in prepared_histories.items():
        if uses_membership and not _is_member_on_date(
            membership_lookup.get(ticker, []),
            current_date,
        ):
            continue

        work = normalize_history_frame(frame)
        if work.empty or current_date not in work.index:
            continue

        row = work.loc[current_date]
        close_price = safe_float(row.get("Close"))
        ma_long = safe_float(row.get("MA_LONG"))

        if (
            not _is_positive_finite_price(close_price)
            or not _is_positive_finite_price(ma_long)
        ):
            continue

        eligible += 1
        if close_price > ma_long:
            above += 1

    if eligible == 0:
        return None

    return above / eligible


def simulate_validation(
    prepared_histories: Mapping[str, pd.DataFrame],
    universe: pd.DataFrame,
    config: HistoricalValidationConfig,
    requested_start: date | pd.Timestamp,
    requested_end: date | pd.Timestamp,
) -> HistoricalValidationResult:
    requested_start_ts = pd.Timestamp(requested_start).normalize()
    requested_end_ts = pd.Timestamp(requested_end).normalize()
    simulation_dates = sorted(
        {
            pd.Timestamp(date).normalize()
            for frame in prepared_histories.values()
            if not frame.empty
            for date in frame.index
            if requested_start_ts <= pd.Timestamp(date).normalize() <= requested_end_ts
        }
    )
    if not simulation_dates:
        raise HistoricalValidationError("No simulation dates are available in the requested window")

    normalized_universe = _normalize_universe_for_validation(pd.DataFrame(universe))
    uses_membership = "member_periods" in normalized_universe.columns
    name_lookup = {
        normalize_ticker_code(row["ticker"]): normalize_text(row.get("company_name"), normalize_ticker_code(row["ticker"]))
        for _, row in normalized_universe.iterrows()
    }
    membership_lookup = {
        normalize_ticker_code(row["ticker"]): row.get("member_periods", [])
        for _, row in normalized_universe.iterrows()
    }
    last_available_dates = {ticker: _last_available_date(frame) for ticker, frame in prepared_histories.items()}

    positions: dict[str, PositionState] = {}
    pending_orders: dict[pd.Timestamp, list[PendingOrder]] = {}
    trades: list[TradeRecord] = []
    equity_rows: list[dict[str, Any]] = []
    risk_v2_research_rows: list[dict[str, Any]] = []
    rejected_due_to_lot = 0
    rejected_due_to_buying_power = 0
    diagnostics_counts: Counter[tuple[int, str]] = Counter()

    def record_diagnostic(year: int, reason: str, amount: int = 1) -> None:
        diagnostics_counts[(year, reason)] += amount

    cash = float(config.initial_capital_yen)
    reserved_cash = 0.0
    peak_equity = float(config.initial_capital_yen)
    strategy = config.strategy_parameters()

    for session_index, current_date in enumerate(simulation_dates):
        # A. Settle only open-gap exits before today's open fills.
        for ticker in list(positions):
            frame = normalize_history_frame(prepared_histories.get(ticker, pd.DataFrame()))
            if frame.empty or current_date not in frame.index:
                continue
            position = positions[ticker]
            row = frame.loc[current_date]
            open_price = safe_float(row["Open"])
            stop_price = position.actual_stop_price or position.stop_price
            target_price = position.actual_target_price or position.target_price
            exit_price = 0.0
            reason = ""
            if _is_positive_finite_price(open_price) and open_price <= stop_price:
                exit_price = open_price * (1.0 - config.slippage_rate)
                reason = "STOP_GAP"
            elif _is_positive_finite_price(open_price) and open_price >= target_price:
                exit_price = open_price * (1.0 - config.slippage_rate)
                reason = "TARGET_GAP"
            if reason and exit_price > 0:
                cash += _close_position(
                    positions=positions,
                    ticker=ticker,
                    exit_date=current_date,
                    exit_price=exit_price,
                    reason=reason,
                    session_index=session_index,
                    config=config,
                    trades=trades,
                )

        todays_orders = pending_orders.pop(current_date, [])
        reserved_cash = max(
            reserved_cash - sum(order.estimated_cost_yen for order in todays_orders),
            0.0,
        )

        open_market_value = 0.0
        for ticker, position in positions.items():
            frame = normalize_history_frame(prepared_histories.get(ticker, pd.DataFrame()))
            if frame.empty:
                continue
            open_market_value += _history_open_at_or_before(frame, current_date) * position.quantity

        open_equity = cash + open_market_value
        same_day_open_exposure = 0.0
        d1_portfolio_risk_yen = (
            _positions_portfolio_risk_yen(positions)
            + _pending_portfolio_risk_yen(pending_orders)
        )
        for order in sorted(todays_orders, key=lambda item: (-item.signal_score, item.ticker)):
            if order.ticker in positions:
                continue
            if uses_membership and not _is_member_on_date(membership_lookup.get(order.ticker, []), current_date):
                continue
            frame = normalize_history_frame(prepared_histories.get(order.ticker, pd.DataFrame()))
            if frame.empty or current_date not in frame.index:
                continue
            row = frame.loc[current_date]
            open_price = safe_float(row["Open"])
            if open_price <= 0:
                continue
            estimated_entry_price = order.estimated_entry_price
            if estimated_entry_price <= 0:
                continue
            planned_risk_per_share = estimated_entry_price - order.stop_price
            if planned_risk_per_share <= 0:
                continue
            actual_entry_price = open_price * (1.0 + config.slippage_rate)
            actual_stop_price = actual_entry_price - planned_risk_per_share
            actual_target_price = actual_entry_price + planned_risk_per_share * config.target_r_multiplier
            available_cash = cash - reserved_cash
            current_exposure = open_market_value + reserved_cash + same_day_open_exposure
            quantity = calculate_shares(
                current_equity=open_equity,
                available_cash=available_cash,
                entry_price=actual_entry_price,
                stop_price=actual_stop_price,
                current_exposure=current_exposure,
                config=config,
                current_portfolio_risk_yen=d1_portfolio_risk_yen,
            )
            quantity = min(order.quantity, quantity)
            if quantity < config.lot_size:
                # Separate cash/exposure shortages from risk or position-sizing shortages.
                reason = _classify_share_rejection_reason(
                    current_equity=open_equity,
                    available_cash=available_cash,
                    entry_price=actual_entry_price,
                    stop_price=actual_stop_price,
                    current_exposure=current_exposure,
                    config=config,
                    d1=True,
                    current_portfolio_risk_yen=d1_portfolio_risk_yen,
                )
                if reason:
                    record_diagnostic(current_date.year, reason)
                spendable_cash = max(available_cash - open_equity * config.minimum_cash_reserve_pct, 0.0)
                lot_entry_value = actual_entry_price * config.lot_size
                lot_cash_cost = lot_entry_value * (1.0 + config.commission_rate)
                portfolio_capacity = max(open_equity * config.max_total_invested_pct - current_exposure, 0.0)
                if spendable_cash + 1e-9 < lot_cash_cost or portfolio_capacity + 1e-9 < lot_entry_value:
                    rejected_due_to_buying_power += 1
                else:
                    rejected_due_to_lot += 1
                continue
            reserved_cash_yen = actual_entry_price * quantity * (1.0 + config.commission_rate)
            if reserved_cash_yen > available_cash + 1e-9:
                rejected_due_to_buying_power += 1
                continue
            cash -= reserved_cash_yen
            same_day_open_exposure += actual_entry_price * quantity
            d1_portfolio_risk_yen += max(
                actual_entry_price - actual_stop_price,
                0.0,
            ) * quantity
            positions[order.ticker] = PositionState(
                ticker=order.ticker,
                company_name=order.company_name,
                signal_date=order.signal_date,
                entry_date=current_date.date().isoformat(),
                entry_session_index=session_index,
                entry_price=actual_entry_price,
                quantity=quantity,
                stop_price=actual_stop_price,
                target_price=actual_target_price,
                signal_score=order.signal_score,
                entry_cost_yen=reserved_cash_yen,
                actual_stop_price=actual_stop_price,
                actual_target_price=actual_target_price,
            )
            record_diagnostic(current_date.year, "D1_FILLED")

        # D. After all open buys, settle intraday exits for any remaining positions.
        for ticker in list(positions):
            frame = normalize_history_frame(prepared_histories.get(ticker, pd.DataFrame()))
            if frame.empty or current_date not in frame.index:
                continue
            position = positions[ticker]
            row = frame.loc[current_date]
            low_price = safe_float(row["Low"])
            high_price = safe_float(row["High"])
            close_price = safe_float(row["Close"])
            stop_price = position.actual_stop_price or position.stop_price
            target_price = position.actual_target_price or position.target_price
            exit_price = 0.0
            reason = ""
            if _is_positive_finite_price(low_price) and low_price <= stop_price:
                exit_price = stop_price * (1.0 - config.slippage_rate)
                reason = "STOP"
            elif _is_positive_finite_price(high_price) and high_price >= target_price:
                exit_price = target_price * (1.0 - config.slippage_rate)
                reason = "TARGET"
            elif _is_positive_finite_price(close_price) and session_index - position.entry_session_index + 1 >= config.max_hold_sessions:
                exit_price = close_price * (1.0 - config.slippage_rate)
                reason = "TIME_EXIT"
            else:
                last_available = last_available_dates.get(ticker)
                if last_available is not None and current_date >= last_available and _is_positive_finite_price(close_price):
                    exit_price = close_price * (1.0 - config.slippage_rate)
                    reason = "DATA_END"
            if reason and exit_price > 0:
                cash += _close_position(
                    positions=positions,
                    ticker=ticker,
                    exit_date=current_date,
                    exit_price=exit_price,
                    reason=reason,
                    session_index=session_index,
                    config=config,
                    trades=trades,
                )

        market_value = 0.0
        for ticker, position in positions.items():
            frame = normalize_history_frame(prepared_histories.get(ticker, pd.DataFrame()))
            if frame.empty:
                continue
            market_value += _history_close_at_or_before(frame, current_date) * position.quantity

        current_equity = cash + market_value

        effective_max_total_invested_pct = config.max_total_invested_pct
        if config.market_breadth_filter_enabled:
            # Risk v2 market regime is evaluated only when the filter is enabled.
            market_breadth_ratio = _market_breadth_above_ma_long_ratio(
                prepared_histories=prepared_histories,
                membership_lookup=membership_lookup,
                current_date=current_date,
                uses_membership=uses_membership,
            )
            market_regime = "NORMAL"
            if (
                market_breadth_ratio is not None
                and market_breadth_ratio < config.market_breadth_bear_threshold
            ):
                market_regime = "BEAR"
                effective_max_total_invested_pct = min(
                    config.max_total_invested_pct,
                    config.market_breadth_bear_max_total_invested_pct,
                )
            risk_v2_research_rows.append(
                {
                    "date": current_date.date().isoformat(),
                    "market_regime": market_regime,
                    "market_breadth_above_ma_long_pct": (
                        round(market_breadth_ratio * 100.0, 4)
                        if market_breadth_ratio is not None
                        else None
                    ),
                    "effective_max_total_invested_pct": round(
                        effective_max_total_invested_pct,
                        6,
                    ),
                }
            )

        pending_tickers = {order.ticker for orders in pending_orders.values() for order in orders}
        todays_entry_candidates: list[EntryCandidate] = []
        for ticker, frame in prepared_histories.items():
            if ticker in positions or ticker in pending_tickers:
                continue
            if uses_membership and not _is_member_on_date(membership_lookup.get(ticker, []), current_date):
                continue
            work = normalize_history_frame(frame)
            if work.empty or current_date not in work.index:
                continue
            location = work.index.get_loc(current_date)
            if not isinstance(location, (int, np.integer)):
                continue
            location = int(location)
            if location < config.minimum_history_sessions - 1 or location + 1 >= len(work):
                continue
            signal_row = work.iloc[location]
            if not is_entry_signal(signal_row, strategy):
                continue
            next_date = pd.Timestamp(work.index[location + 1]).normalize()
            if uses_membership:
                member_periods = membership_lookup.get(ticker, [])
                if not _is_member_on_date(member_periods, current_date) or not _is_member_on_date(member_periods, next_date):
                    continue
            raw_close = safe_float(signal_row["Close"])
            atr = safe_float(signal_row.get("ATR"))
            if raw_close <= 0 or atr <= 0:
                continue
            estimated_entry_price = raw_close * (1.0 + config.slippage_rate)
            stop_price = estimated_entry_price - atr * config.stop_atr_multiplier
            if stop_price <= 0 or stop_price >= estimated_entry_price:
                continue
            target_price = estimated_entry_price + (estimated_entry_price - stop_price) * config.target_r_multiplier
            if next_date > requested_end_ts:
                continue
            record_diagnostic(current_date.year, "SIGNAL_CANDIDATE")
            todays_entry_candidates.append(
                EntryCandidate(
                    ticker=ticker,
                    company_name=name_lookup.get(ticker, ticker),
                    signal_date=current_date.date().isoformat(),
                    entry_date=next_date.date().isoformat(),
                    entry_session_index=session_index + 1,
                    signal_score=signal_score(signal_row, strategy),
                    estimated_entry_price=estimated_entry_price,
                    stop_price=stop_price,
                    target_price=target_price,
                    next_date=next_date,
                )
            )

        candidate_portfolio_risk_yen = (
            _positions_portfolio_risk_yen(positions)
            + _pending_portfolio_risk_yen(pending_orders)
        )
        for candidate in sorted(todays_entry_candidates, key=lambda item: (-item.signal_score, item.ticker)):
            available_cash = cash - reserved_cash
            current_exposure = market_value + reserved_cash
            quantity = calculate_shares(
                current_equity=current_equity,
                available_cash=available_cash,
                entry_price=candidate.estimated_entry_price,
                stop_price=candidate.stop_price,
                current_exposure=current_exposure,
                config=config,
                current_portfolio_risk_yen=candidate_portfolio_risk_yen,
                max_total_invested_pct_override=effective_max_total_invested_pct,
            )
            if quantity < config.lot_size:
                # Separate cash/exposure shortages from risk or position-sizing shortages.
                reason = _classify_share_rejection_reason(
                    current_equity=current_equity,
                    available_cash=available_cash,
                    entry_price=candidate.estimated_entry_price,
                    stop_price=candidate.stop_price,
                    current_exposure=current_exposure,
                    config=config,
                    d1=False,
                    current_portfolio_risk_yen=candidate_portfolio_risk_yen,
                    max_total_invested_pct_override=effective_max_total_invested_pct,
                )
                if reason:
                    record_diagnostic(current_date.year, reason)
                spendable_cash = max(available_cash - current_equity * config.minimum_cash_reserve_pct, 0.0)
                lot_entry_value = candidate.estimated_entry_price * config.lot_size
                lot_cash_cost = lot_entry_value * (1.0 + config.commission_rate)
                portfolio_capacity = max(
                    current_equity * effective_max_total_invested_pct - current_exposure,
                    0.0,
                )
                if spendable_cash + 1e-9 < lot_cash_cost or portfolio_capacity + 1e-9 < lot_entry_value:
                    rejected_due_to_buying_power += 1
                else:
                    rejected_due_to_lot += 1
                continue
            reserved_cash_yen = candidate.estimated_entry_price * quantity * (1.0 + config.commission_rate)
            if reserved_cash_yen > available_cash + 1e-9:
                rejected_due_to_buying_power += 1
                continue
            pending_orders.setdefault(candidate.next_date, []).append(
                PendingOrder(
                    ticker=candidate.ticker,
                    company_name=candidate.company_name,
                    signal_date=candidate.signal_date,
                    entry_date=candidate.entry_date,
                    entry_session_index=candidate.entry_session_index,
                    quantity=quantity,
                    stop_price=candidate.stop_price,
                    target_price=candidate.target_price,
                    signal_score=candidate.signal_score,
                    estimated_cost_yen=reserved_cash_yen,
                    estimated_entry_price=candidate.estimated_entry_price,
                )
            )
            reserved_cash += reserved_cash_yen
            candidate_portfolio_risk_yen += max(
                candidate.estimated_entry_price - candidate.stop_price,
                0.0,
            ) * quantity
            record_diagnostic(current_date.year, "PENDING_CREATED")

        peak_equity = max(peak_equity, current_equity)
        drawdown_yen = peak_equity - current_equity
        drawdown_pct = drawdown_yen / peak_equity * 100 if peak_equity > 0 else 0.0
        equity_rows.append(
            {
                "date": current_date.date().isoformat(),
                "cash_yen": round(cash, 2),
                "reserved_cash_yen": round(reserved_cash, 2),
                "available_cash_yen": round(cash - reserved_cash, 2),
                "market_value_yen": round(market_value, 2),
                "equity_yen": round(current_equity, 2),
                "peak_equity_yen": round(peak_equity, 2),
                "drawdown_yen": round(drawdown_yen, 2),
                "drawdown_pct": round(drawdown_pct, 6),
                "open_positions": len(positions),
                "pending_orders": sum(len(value) for value in pending_orders.values()),
            }
        )

    final_date = simulation_dates[-1]
    for ticker in list(positions):
        frame = normalize_history_frame(prepared_histories.get(ticker, pd.DataFrame()))
        if frame.empty:
            continue
        final_close = _history_close_at_or_before(frame, final_date)
        if final_close <= 0:
            continue
        exit_price = final_close * (1.0 - config.slippage_rate)
        if exit_price <= 0:
            continue
        cash += _close_position(
            positions=positions,
            ticker=ticker,
            exit_date=final_date,
            exit_price=exit_price,
            reason="END_OF_TEST",
            session_index=len(simulation_dates) - 1,
            config=config,
            trades=trades,
        )

    pending_orders.clear()
    reserved_cash = 0.0

    if equity_rows:
        final_market_value = 0.0
        final_equity = cash + final_market_value
        peak_equity = max(peak_equity, final_equity)
        equity_rows[-1].update(
            {
                "cash_yen": round(cash, 2),
                "reserved_cash_yen": 0.0,
                "available_cash_yen": round(cash, 2),
                "market_value_yen": round(final_market_value, 2),
                "equity_yen": round(final_equity, 2),
                "peak_equity_yen": round(peak_equity, 2),
                "drawdown_yen": round(peak_equity - final_equity, 2),
                "drawdown_pct": round((peak_equity - final_equity) / peak_equity * 100 if peak_equity > 0 else 0.0, 6),
                "open_positions": len(positions),
                "pending_orders": 0,
            }
        )

    trades_df = pd.DataFrame([asdict(trade) for trade in trades])
    equity_df = pd.DataFrame(equity_rows)
    risk_v2_research_df = pd.DataFrame(risk_v2_research_rows, columns=list(RISK_V2_RESEARCH_COLUMNS))
    annual_df = build_period_returns(
        equity_df,
        trades_df,
        "Y",
        config.initial_capital_yen,
    )
    monthly_df = build_period_returns(
        equity_df,
        trades_df,
        "M",
        config.initial_capital_yen,
    )
    return HistoricalValidationResult(
        trades=trades_df,
        equity_curve=equity_df,
        annual_returns=annual_df,
        monthly_returns=monthly_df,
        rejected_due_to_lot=rejected_due_to_lot,
        rejected_due_to_buying_power=rejected_due_to_buying_power,
        diagnostics=_build_diagnostics_frame(diagnostics_counts, requested_start_ts.year, requested_end_ts.year),
        risk_v2_research=risk_v2_research_df,
    )


def build_period_returns(
    equity_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    period: str,
    initial_equity: float,
) -> pd.DataFrame:
    columns = [
        "period",
        "start_date",
        "end_date",
        "start_equity_yen",
        "end_equity_yen",
        "profit_yen",
        "return_pct",
        "trade_count",
        "winning_trades",
        "losing_trades",
        "win_rate_pct",
        "max_drawdown_pct",
    ]
    if equity_df.empty:
        return pd.DataFrame(columns=columns)
    work = equity_df.copy()
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date"])
    if work.empty:
        return pd.DataFrame(columns=columns)
    work["period"] = work["date"].dt.to_period(period)
    trades_work = trades_df.copy()
    if not trades_work.empty:
        trades_work["exit_date"] = pd.to_datetime(trades_work["exit_date"], errors="coerce")
        trades_work = trades_work.dropna(subset=["exit_date"])
        trades_work["period"] = trades_work["exit_date"].dt.to_period(period)
    rows: list[dict[str, Any]] = []
    period_baseline = float(initial_equity)
    for period_value, group in work.groupby("period", sort=True):
        start_equity = period_baseline
        end_equity = safe_float(group["equity_yen"].iloc[-1])
        period_trades = trades_work[trades_work["period"] == period_value] if not trades_work.empty else pd.DataFrame()
        profits = period_trades["profit_yen"].astype(float) if not period_trades.empty else pd.Series(dtype=float)
        winning = int((profits > 0).sum()) if not period_trades.empty else 0
        losing = int((profits < 0).sum()) if not period_trades.empty else 0
        win_rate = winning / len(period_trades) * 100 if len(period_trades) else 0.0
        equity_values = pd.Series([start_equity, *group["equity_yen"].astype(float).tolist()], dtype=float)
        running_max = equity_values.cummax()
        drawdown = (equity_values - running_max) / running_max.replace(0, np.nan) * 100
        rows.append(
            {
                "period": str(period_value),
                "start_date": group["date"].iloc[0].date().isoformat(),
                "end_date": group["date"].iloc[-1].date().isoformat(),
                "start_equity_yen": round(start_equity, 2),
                "end_equity_yen": round(end_equity, 2),
                "profit_yen": round(end_equity - start_equity, 2),
                "return_pct": round(((end_equity / start_equity) - 1) * 100 if start_equity > 0 else 0.0, 6),
                "trade_count": int(len(period_trades)),
                "winning_trades": winning,
                "losing_trades": losing,
                "win_rate_pct": round(win_rate, 6),
                "max_drawdown_pct": round(abs(safe_float(drawdown.min(), 0.0)), 6),
            }
        )
        period_baseline = end_equity
    return pd.DataFrame(rows, columns=columns)


def _streak(values: Iterable[float], positive: bool) -> int:
    best = 0
    current = 0
    for value in values:
        matched = value > 0 if positive else value < 0
        current = current + 1 if matched else 0
        best = max(best, current)
    return best


def _calculate_max_drawdown(equity_df: pd.DataFrame) -> tuple[float, float]:
    if equity_df.empty:
        return 0.0, 0.0
    values = equity_df["equity_yen"].astype(float)
    running_max = values.cummax()
    drawdown_yen = running_max - values
    drawdown_pct = (drawdown_yen / running_max.replace(0, np.nan) * 100).fillna(0.0)
    return round(float(drawdown_yen.max()), 2), round(abs(float(drawdown_pct.max())), 6)


def _performance_metrics(equity_df: pd.DataFrame, initial_equity: float) -> dict[str, Any]:
    if equity_df.empty:
        return {
            "final_equity_yen": round(initial_equity, 2),
            "total_profit_yen": 0.0,
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "cagr_pct": 0.0,
            "max_drawdown_yen": 0.0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
        }
    values = equity_df["equity_yen"].astype(float)
    final_equity = safe_float(values.iloc[-1], initial_equity)
    equity_path = pd.Series([initial_equity, *values.tolist()], dtype=float)
    total_return_pct = ((final_equity / initial_equity) - 1) * 100 if initial_equity > 0 else 0.0
    start_date = pd.to_datetime(equity_df["date"].iloc[0], errors="coerce")
    end_date = pd.to_datetime(equity_df["date"].iloc[-1], errors="coerce")
    years = max((end_date - start_date).days / 365.25, 0.0) if pd.notna(start_date) and pd.notna(end_date) else 0.0
    cagr_pct = ((final_equity / initial_equity) ** (1 / years) - 1) * 100 if initial_equity > 0 and years > 0 else 0.0
    drawdown_yen, drawdown_pct = _calculate_max_drawdown(pd.DataFrame({"equity_yen": equity_path}))
    daily_returns = equity_path.pct_change().dropna()
    sharpe = 0.0
    sortino = 0.0
    if len(daily_returns) > 1:
        std = safe_float(daily_returns.std())
        if std > 0:
            sharpe = safe_float(daily_returns.mean()) / std * math.sqrt(252)
        downside = daily_returns[daily_returns < 0]
        downside_std = safe_float(downside.std())
        if downside_std > 0:
            sortino = safe_float(daily_returns.mean()) / downside_std * math.sqrt(252)
    calmar = cagr_pct / drawdown_pct if drawdown_pct > 0 else 0.0
    return {
        "final_equity_yen": round(final_equity, 2),
        "total_profit_yen": round(final_equity - initial_equity, 2),
        "total_return_pct": round(total_return_pct, 6),
        "annualized_return_pct": round(cagr_pct, 6),
        "cagr_pct": round(cagr_pct, 6),
        "max_drawdown_yen": round(drawdown_yen, 2),
        "max_drawdown_pct": round(drawdown_pct, 6),
        "sharpe_ratio": round(sharpe, 6),
        "sortino_ratio": round(sortino, 6),
        "calmar_ratio": round(calmar, 6),
    }


def _summarize_simulation_result(result: HistoricalValidationResult, initial_equity: float) -> dict[str, Any]:
    performance = _performance_metrics(result.equity_curve, initial_equity)
    trades_df = result.trades

    if trades_df.empty or "profit_yen" not in trades_df.columns:
        winners = pd.DataFrame()
        losers = pd.DataFrame()
        gross_profit = 0.0
        gross_loss = 0.0
        average_profit = 0.0
        average_loss = 0.0
        average_holding_sessions = 0.0
    else:
        profits = trades_df["profit_yen"].astype(float)
        winners = trades_df[profits > 0]
        losers = trades_df[profits < 0]
        gross_profit = safe_float(winners["profit_yen"].astype(float).sum()) if not winners.empty else 0.0
        gross_loss = abs(safe_float(losers["profit_yen"].astype(float).sum())) if not losers.empty else 0.0
        average_profit = safe_float(winners["profit_yen"].astype(float).mean()) if not winners.empty else 0.0
        average_loss = safe_float(losers["profit_yen"].astype(float).mean()) if not losers.empty else 0.0
        average_holding_sessions = safe_float(trades_df["holding_sessions"].astype(float).mean())

    cash_remaining = (
        safe_float(result.equity_curve["cash_yen"].iloc[-1])
        if not result.equity_curve.empty and "cash_yen" in result.equity_curve.columns
        else initial_equity
    )
    market_value = (
        safe_float(result.equity_curve["market_value_yen"].iloc[-1])
        if not result.equity_curve.empty and "market_value_yen" in result.equity_curve.columns
        else 0.0
    )
    trade_count = int(len(trades_df))
    win_rate_pct = len(winners) / trade_count * 100 if trade_count else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    if result.equity_curve.empty:
        cash_ratio = 1.0
    elif "cash_yen" in result.equity_curve.columns and "equity_yen" in result.equity_curve.columns:
        cash_values = pd.to_numeric(result.equity_curve["cash_yen"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        equity_values = pd.to_numeric(result.equity_curve["equity_yen"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        ratio_values = np.divide(
            cash_values,
            equity_values,
            out=np.zeros_like(cash_values, dtype=float),
            where=equity_values > 0,
        )
        cash_ratio = float(np.mean(ratio_values)) if ratio_values.size else 1.0
    else:
        cash_ratio = 0.0

    performance.update(
        {
            "final_equity": performance.get("final_equity_yen", initial_equity),
            "total_return": performance.get("total_return_pct", 0.0),
            "CAGR": performance.get("cagr_pct", 0.0),
            "max_drawdown": performance.get("max_drawdown_pct", 0.0),
            "trade_count": trade_count,
            "winning_trades": int(len(winners)),
            "losing_trades": int(len(losers)),
            "win_rate": round(win_rate_pct, 6),
            "profit_factor": round(profit_factor, 6),
            "average_profit_per_trade_yen": round(average_profit, 2),
            "average_loss_per_trade_yen": round(average_loss, 2),
            "average_holding_sessions": round(average_holding_sessions, 2),
            "avg_holding": round(average_holding_sessions, 2),
            "average_holding_days": round(average_holding_sessions, 2),
            "cash_remaining_yen": round(cash_remaining, 2),
            "cash_ratio": round(cash_ratio, 6),
            "market_value_yen": round(market_value, 2),
            "rejected_due_to_lot": int(result.rejected_due_to_lot),
            "rejected_due_to_buying_power": int(result.rejected_due_to_buying_power),
            "annual_returns_rows": int(len(result.annual_returns)),
            "monthly_returns_rows": int(len(result.monthly_returns)),
        }
    )
    return performance


def _build_historical_validation_config(settings: Mapping[str, Any]) -> HistoricalValidationConfig:
    return HistoricalValidationConfig(
        initial_capital_yen=float(settings.get("initial_capital_yen", DEFAULT_INITIAL_CAPITAL_YEN)),
        lot_size=int(settings.get("lot_size", DEFAULT_LOT_SIZE)),
        max_positions=int(settings.get("max_positions", DEFAULT_MAX_POSITIONS)),
        max_position_pct=float(settings.get("max_position_pct", DEFAULT_MAX_POSITION_PCT)),
        max_position_hard_pct=float(settings.get("max_position_hard_pct", DEFAULT_MAX_POSITION_HARD_PCT)),
        max_total_invested_pct=float(settings.get("max_total_invested_pct", DEFAULT_MAX_TOTAL_INVESTED_PCT)),
        minimum_cash_reserve_pct=float(settings.get("minimum_cash_reserve_pct", DEFAULT_MINIMUM_CASH_RESERVE_PCT)),
        risk_per_trade_pct=float(settings.get("risk_per_trade_pct", DEFAULT_RISK_PER_TRADE_PCT)),
        max_portfolio_risk_pct=float(settings.get("max_portfolio_risk_pct", DEFAULT_MAX_PORTFOLIO_RISK_PCT)),
        maximum_quantity_per_ticker=int(settings.get("maximum_quantity_per_ticker", DEFAULT_MAXIMUM_QUANTITY_PER_TICKER)),
        commission_rate=float(settings.get("commission_rate", DEFAULT_COMMISSION_RATE)),
        slippage_rate=float(settings.get("slippage_rate", DEFAULT_SLIPPAGE_RATE)),
        stop_atr_multiplier=float(settings.get("stop_atr_multiplier", DEFAULT_STOP_ATR_MULTIPLIER)),
        target_r_multiplier=float(settings.get("target_r_multiplier", DEFAULT_TARGET_R_MULTIPLIER)),
        signal_score_threshold=float(settings.get("signal_score_threshold", DEFAULT_SIGNAL_SCORE_THRESHOLD)),
        rsi_min=float(settings.get("rsi_min", DEFAULT_RSI_MIN)),
        rsi_max=float(settings.get("rsi_max", DEFAULT_RSI_MAX)),
        ma_short=int(settings.get("ma_short", DEFAULT_MA_SHORT)),
        ma_mid=int(settings.get("ma_mid", DEFAULT_MA_MID)),
        ma_long=int(settings.get("ma_long", DEFAULT_MA_LONG)),
        max_hold_sessions=int(settings.get("max_hold_sessions", DEFAULT_MAX_HOLD_SESSIONS)),
        minimum_history_sessions=int(settings.get("minimum_history_sessions", DEFAULT_MINIMUM_HISTORY_SESSIONS)),
        requested_years=int(settings.get("requested_years", DEFAULT_REQUESTED_YEARS)),
        allow_network_fetch=bool(settings.get("allow_network_fetch", DEFAULT_ALLOW_NETWORK_FETCH)),
        universe_csv=str(settings.get("universe_csv", "data/nikkei225.csv")),
        benchmark_ticker=str(settings.get("benchmark_ticker", DEFAULT_BENCHMARK_TICKER)),
        market_breadth_filter_enabled=bool(
            settings.get(
                "market_breadth_filter_enabled",
                DEFAULT_MARKET_BREADTH_FILTER_ENABLED,
            )
        ),
        market_breadth_bear_threshold=float(
            settings.get(
                "market_breadth_bear_threshold",
                DEFAULT_MARKET_BREADTH_BEAR_THRESHOLD,
            )
        ),
        market_breadth_bear_max_total_invested_pct=float(
            settings.get(
                "market_breadth_bear_max_total_invested_pct",
                DEFAULT_MARKET_BREADTH_BEAR_MAX_TOTAL_INVESTED_PCT,
            )
        ),
        output_dir=str(settings.get("output_dir", DEFAULT_OUTPUT_DIR)),
        report_json=str(settings.get("report_json", "reports/historical_validation_20y/summary.json")),
        report_text=str(settings.get("report_text", "reports/historical_validation_20y/report.txt")),
        annual_returns_csv=str(settings.get("annual_returns_csv", "reports/historical_validation_20y/annual_returns.csv")),
        monthly_returns_csv=str(settings.get("monthly_returns_csv", "reports/historical_validation_20y/monthly_returns.csv")),
        data_coverage_csv=str(settings.get("data_coverage_csv", "reports/historical_validation_20y/data_coverage.csv")),
        trades_csv=str(settings.get("trades_csv", "reports/historical_validation_20y/trades.csv")),
        equity_curve_csv=str(settings.get("equity_curve_csv", "reports/historical_validation_20y/equity_curve.csv")),
        benchmark_enabled=bool(settings.get("benchmark_enabled", True)),
        no_rss=bool(settings.get("no_rss", True)),
        no_real_orders=bool(settings.get("no_real_orders", True)),
        live_trading_enabled=bool(settings.get("live_trading_enabled", False)),
        orders_submitted=int(settings.get("orders_submitted", 0)),
    )


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_REQUESTED_START = "2006-08"
DEFAULT_REQUESTED_END = "2026-08"
DEFAULT_CACHE_DIR = "data/market_cache"
DEFAULT_COVERAGE_CSV = "reports/historical_validation_20y/data_coverage.csv"
DEFAULT_REPORT_JSON = "reports/historical_validation_20y/summary.json"
DEFAULT_REPORT_TEXT = "reports/historical_validation_20y/report.txt"
DEFAULT_FRACTIONAL_SHARES = False
DEFAULT_ENFORCE_NIKKEI225 = True
DEFAULT_EXPECTED_TICKER_COUNT = EXPECTED_NIKKEI225_COUNT
VALID_COVERAGE_STATUSES = {
    "SUCCESS",
    "PARTIAL",
    "NOT_ELIGIBLE",
    "NO_DATA",
    "DOWNLOAD_FAILED",
    "INSUFFICIENT_HISTORY",
}

DEFAULT_SETTINGS = {
    "enabled": True,
    "initial_capital_yen": DEFAULT_INITIAL_CAPITAL_YEN,
    "lot_size": DEFAULT_LOT_SIZE,
    "fractional_shares": DEFAULT_FRACTIONAL_SHARES,
    "max_positions": DEFAULT_MAX_POSITIONS,
    "max_position_pct": DEFAULT_MAX_POSITION_PCT,
    "max_position_hard_pct": DEFAULT_MAX_POSITION_HARD_PCT,
    "max_total_invested_pct": DEFAULT_MAX_TOTAL_INVESTED_PCT,
    "minimum_cash_reserve_pct": DEFAULT_MINIMUM_CASH_RESERVE_PCT,
    "risk_per_trade_pct": DEFAULT_RISK_PER_TRADE_PCT,
    "max_portfolio_risk_pct": DEFAULT_MAX_PORTFOLIO_RISK_PCT,
    "maximum_quantity_per_ticker": DEFAULT_MAXIMUM_QUANTITY_PER_TICKER,
    "commission_rate": DEFAULT_COMMISSION_RATE,
    "slippage_rate": DEFAULT_SLIPPAGE_RATE,
    "stop_atr_multiplier": DEFAULT_STOP_ATR_MULTIPLIER,
    "target_r_multiplier": DEFAULT_TARGET_R_MULTIPLIER,
    "signal_score_threshold": DEFAULT_SIGNAL_SCORE_THRESHOLD,
    "rsi_min": DEFAULT_RSI_MIN,
    "rsi_max": DEFAULT_RSI_MAX,
    "ma_short": DEFAULT_MA_SHORT,
    "ma_mid": DEFAULT_MA_MID,
    "ma_long": DEFAULT_MA_LONG,
    "max_hold_sessions": DEFAULT_MAX_HOLD_SESSIONS,
    "minimum_history_sessions": DEFAULT_MINIMUM_HISTORY_SESSIONS,
    "requested_years": DEFAULT_REQUESTED_YEARS,
    "requested_start": DEFAULT_REQUESTED_START,
    "requested_end": DEFAULT_REQUESTED_END,
    "allow_network_fetch": DEFAULT_ALLOW_NETWORK_FETCH,
    "universe_csv": "data/nikkei225.csv",
    "benchmark_ticker": DEFAULT_BENCHMARK_TICKER,
    "cache_dir": DEFAULT_CACHE_DIR,
    "coverage_csv": DEFAULT_COVERAGE_CSV,
    "data_coverage_csv": DEFAULT_COVERAGE_CSV,
    "output_dir": DEFAULT_OUTPUT_DIR,
    "report_json": DEFAULT_REPORT_JSON,
    "report_text": DEFAULT_REPORT_TEXT,
    "annual_returns_csv": "reports/historical_validation_20y/annual_returns.csv",
    "monthly_returns_csv": "reports/historical_validation_20y/monthly_returns.csv",
    "trades_csv": "reports/historical_validation_20y/trades.csv",
    "equity_curve_csv": "reports/historical_validation_20y/equity_curve.csv",
    "benchmark_enabled": True,
    "no_rss": True,
    "no_real_orders": True,
    "live_trading_enabled": False,
    "orders_submitted": 0,
    "enforce_nikkei225": DEFAULT_ENFORCE_NIKKEI225,
    "expected_ticker_count": DEFAULT_EXPECTED_TICKER_COUNT,
}


@dataclass(frozen=True, slots=True)
class FetchOutcome:
    history: pd.DataFrame
    cache_used: bool
    download_used: bool
    network_attempts: int
    download_error: str | None = None


def _extract_settings_payload(config: dict[str, Any]) -> dict[str, Any]:
    payload = config.get("historical_validation_20y", config)
    if not isinstance(payload, dict):
        raise HistoricalValidationError("historical_validation_20y config must be an object")
    return payload


def load_settings(root: Path, config_path: Path | str | None = None) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if config_path is None:
        default_path = root / "config" / "v7_historical_validation_20y.json"
        if default_path.is_file():
            settings.update(_extract_settings_payload(load_json_object(default_path)))
        return settings

    resolved = resolve_within(root, str(config_path))
    settings.update(_extract_settings_payload(load_json_object(resolved)))
    return settings


def _as_jst(value: datetime | date | None) -> datetime:
    if value is None:
        return datetime.now(JST)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=JST)
        return value.astimezone(JST)
    return datetime.combine(value, datetime_time(0, 0), tzinfo=JST)


def _parse_boundary_date(value: Any, *, boundary: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        raise HistoricalValidationError(f"{boundary} date is missing")

    if re.fullmatch(r"\d{4}-\d{2}", text):
        year, month = (int(part) for part in text.split("-"))
        if boundary == "start":
            return date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day)

    try:
        return date.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromisoformat(text).date()
        except ValueError as error:
            raise HistoricalValidationError(f"Invalid {boundary} date: {value}") from error


def _normalize_requested_range(
    requested_start: Any | None,
    requested_end: Any | None,
    *,
    as_of: datetime,
) -> tuple[date, date]:
    checked = _as_jst(as_of)
    today = checked.date()

    if requested_end is None:
        end = today
    else:
        end = _parse_boundary_date(requested_end, boundary="end")
        if end > today:
            end = today

    if requested_start is None:
        start = date(end.year - DEFAULT_REQUESTED_YEARS, end.month, 1)
    else:
        start = _parse_boundary_date(requested_start, boundary="start")

    if start > end:
        raise HistoricalValidationError("requested_start must not be after requested_end")
    return start, end


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    safe = normalize_ticker_code(ticker).replace(".", "_")
    return cache_dir / f"{safe}.csv"


def _load_csv_history(path: Path) -> tuple[pd.DataFrame, bool]:
    if not path.is_file():
        return pd.DataFrame(), False
    try:
        raw = read_csv_flexible(path)
    except FileNotFoundError:
        return pd.DataFrame(), False
    if raw.empty:
        return pd.DataFrame(), False
    normalized, migrated = _canonicalize_cached_history(raw)
    return normalized, migrated


def _save_csv_history(path: Path, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_history_frame(frame)
    if normalized.empty:
        return
    normalized.index.name = "Date"
    atomic_write(path, normalized.to_csv(index=True))


def _merge_histories(*frames: pd.DataFrame) -> pd.DataFrame:
    non_empty = [frame for frame in frames if isinstance(frame, pd.DataFrame) and not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    merged = pd.concat(non_empty, axis=0)
    return normalize_history_frame(merged)


def _missing_business_day_spans(
    requested_start: date,
    requested_end: date,
    covered_dates: set[date],
) -> list[tuple[date, date]]:
    requested_sessions = [pd.Timestamp(session).date() for session in pd.bdate_range(requested_start, requested_end)]
    missing_sessions = [session for session in requested_sessions if session not in covered_dates]
    if not missing_sessions:
        return []

    spans: list[tuple[date, date]] = []
    span_start = missing_sessions[0]
    span_end = missing_sessions[0]
    for current in missing_sessions[1:]:
        next_expected = (pd.Timestamp(span_end) + pd.offsets.BDay(1)).date()
        if current == next_expected:
            span_end = current
            continue
        spans.append((span_start, span_end))
        span_start = current
        span_end = current
    spans.append((span_start, span_end))
    return spans


def _trim_history(
    frame: pd.DataFrame,
    requested_start: date,
    requested_end: date,
    *,
    as_of: datetime,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    checked = _as_jst(as_of)
    clipped = normalize_history_frame(frame)
    if clipped.empty:
        return pd.DataFrame()
    clipped = clipped[(clipped.index.date >= requested_start) & (clipped.index.date <= requested_end)]
    if clipped.empty:
        return pd.DataFrame()
    clipped = clipped[clipped.index.date <= checked.date()]
    clipped = clipped[~clipped.index.duplicated(keep="last")]
    clipped = clipped.sort_index()
    clipped.index.name = "Date"
    return clipped


def download_ticker_history(
    ticker: str,
    requested_start: date,
    requested_end: date,
) -> pd.DataFrame:
    _ensure_quote_transport()
    raw = yf.download(
        ticker,
        start=requested_start.isoformat(),
        end=(requested_end + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=True,
        actions=False,
        progress=False,
        threads=False,
        group_by="column",
        timeout=30,
    )
    if not isinstance(raw, pd.DataFrame):
        return pd.DataFrame()
    normalized = market_normalize_history(raw, ticker)
    return normalized.loc[_valid_ohlcv_mask(normalized)].copy() if not normalized.empty else normalized


def fetch_ticker_history(
    root: Path,
    ticker: str,
    requested_start: date,
    requested_end: date,
    *,
    cache_dir: str | Path | None = None,
    as_of: datetime | None = None,
    allow_network_fetch: bool = True,
    download_registry: set[tuple[str, date, date]] | None = None,
) -> FetchOutcome:
    repository = root.resolve()
    cache_root = resolve_within(repository, str(cache_dir or DEFAULT_CACHE_DIR))
    cache_file = _cache_path(cache_root, ticker)

    cached, cache_needs_rewrite = _load_csv_history(cache_file)
    checked = as_of or datetime.now(JST)
    trimmed_cache = _trim_history(cached, requested_start, requested_end, as_of=checked)
    missing_spans: list[tuple[date, date]] = []
    if trimmed_cache.empty:
        missing_spans.append((requested_start, requested_end))
    else:
        first_cached = pd.Timestamp(trimmed_cache.index.min()).date()
        last_cached = pd.Timestamp(trimmed_cache.index.max()).date()
        if first_cached > requested_start:
            missing_spans.append((requested_start, first_cached - timedelta(days=1)))
        if last_cached < requested_end:
            missing_spans.append((last_cached + timedelta(days=1), requested_end))
    if not missing_spans:
        if cache_needs_rewrite and not cached.empty:
            _save_csv_history(cache_file, cached)
        return FetchOutcome(
            history=trimmed_cache,
            cache_used=not cached.empty,
            download_used=False,
            network_attempts=0,
            download_error=None,
        )

    if not allow_network_fetch:
        if cache_needs_rewrite and not cached.empty:
            _save_csv_history(cache_file, cached)
        return FetchOutcome(
            history=trimmed_cache,
            cache_used=not cached.empty,
            download_used=False,
            network_attempts=0,
            download_error=None,
        )

    download_error_messages: list[str] = []
    downloaded_frames: list[pd.DataFrame] = []
    download_used = False
    network_attempts = 0
    registry = download_registry
    for span_start, span_end in missing_spans:
        registry_key = (ticker, span_start, span_end)
        if registry is not None and registry_key in registry:
            continue
        if registry is not None:
            registry.add(registry_key)
        try:
            network_attempts += 1
            downloaded = download_ticker_history(ticker, span_start, span_end)
        except Exception as error:
            download_error_messages.append(
                f"{span_start.isoformat()}..{span_end.isoformat()}: {type(error).__name__}: {error}"
            )
            continue
        if downloaded.empty:
            download_error_messages.append(f"{span_start.isoformat()}..{span_end.isoformat()}: no data returned")
            continue
        downloaded_frames.append(downloaded)
        download_used = True

    merged = _merge_histories(cached, *downloaded_frames)
    usable = _trim_history(merged, requested_start, requested_end, as_of=checked)

    if download_used and not merged.empty:
        _save_csv_history(cache_file, merged)
    elif cache_needs_rewrite and not cached.empty:
        _save_csv_history(cache_file, cached)

    if not usable.empty:
        history = usable
    else:
        history = trimmed_cache

    return FetchOutcome(
        history=history,
        cache_used=not cached.empty,
        download_used=download_used,
        network_attempts=network_attempts,
        download_error="; ".join(download_error_messages) if download_error_messages else None,
    )


def build_coverage_row(
    ticker: str,
    company_name: str,
    requested_start: date,
    requested_end: date,
    outcome: FetchOutcome,
    market_day_basis: Iterable[Any] | None = None,
    member_periods: Iterable[tuple[pd.Timestamp | None, pd.Timestamp | None]] | None = None,
) -> dict[str, Any]:
    history = _valid_ohlcv_history(outcome.history)
    history_days = pd.DatetimeIndex(history.index).unique().sort_values()
    basis = pd.DatetimeIndex(market_day_basis).normalize().unique().sort_values() if market_day_basis is not None else history_days
    if basis.empty:
        basis = history_days
    requested_start_ts = pd.Timestamp(requested_start)
    requested_end_ts = pd.Timestamp(requested_end)
    requested_basis_days = basis[(basis >= requested_start_ts) & (basis <= requested_end_ts)]
    if requested_basis_days.empty:
        requested_basis_days = history_days
    if member_periods is not None:
        eligible_days = _days_within_periods(requested_basis_days, member_periods)
        if eligible_days.empty and not requested_basis_days.empty:
            return {
                "ticker": ticker,
                "company_name": company_name,
                "requested_start": requested_start.isoformat(),
                "requested_end": requested_end.isoformat(),
                "actual_start": "",
                "actual_end": "",
                "trading_days": 0,
                "coverage_status": "NOT_ELIGIBLE",
                "missing_reason": "no constituent days overlap the requested range",
                "network_attempts": outcome.network_attempts,
                "cache_used": bool(outcome.cache_used),
                "download_used": bool(outcome.download_used),
                "coverage_pct": 0.0,
            }
    else:
        eligible_days = requested_basis_days

    if history.empty:
        if outcome.download_error and not outcome.cache_used:
            status = "DOWNLOAD_FAILED"
            reason = outcome.download_error
        elif outcome.download_error:
            status = "NO_DATA"
            reason = f"download failed; cache fallback was empty: {outcome.download_error}"
        else:
            status = "NO_DATA"
            reason = "no usable OHLCV rows were returned"
        return {
            "ticker": ticker,
            "company_name": company_name,
            "requested_start": requested_start.isoformat(),
            "requested_end": requested_end.isoformat(),
            "actual_start": "",
            "actual_end": "",
            "trading_days": 0,
            "coverage_status": status,
            "missing_reason": reason,
            "network_attempts": outcome.network_attempts,
            "cache_used": bool(outcome.cache_used),
            "download_used": bool(outcome.download_used),
            "coverage_pct": 0.0,
        }

    if member_periods is not None:
        present_days = eligible_days.intersection(history_days)
        missing_days = eligible_days.difference(history_days)
        if present_days.empty:
            status = "PARTIAL"
            reason = "no usable OHLCV rows were returned within constituent periods"
            actual_start = ""
            actual_end = ""
            trading_days = 0
        else:
            actual_start = pd.Timestamp(present_days.min()).date().isoformat()
            actual_end = pd.Timestamp(present_days.max()).date().isoformat()
            trading_days = int(len(present_days))
            if missing_days.empty:
                status = "SUCCESS"
                reason = ""
            else:
                status = "PARTIAL"
                reason_parts: list[str] = []
                if missing_days.size > 0 and missing_days[0] == eligible_days[0]:
                    reason_parts.append(f"history starts after constituent_start: first_available={actual_start}")
                if missing_days.size > 0 and missing_days[-1] == eligible_days[-1]:
                    reason_parts.append(f"history ends before constituent_end: last_available={actual_end}")
                reason_parts.append(f"missing_base_days={len(missing_days)}")
                reason_parts.append(f"first_missing={missing_days[0].date().isoformat()}")
                reason_parts.append(f"last_missing={missing_days[-1].date().isoformat()}")
                reason = "; ".join(reason_parts)
        if outcome.download_error and not reason:
            reason = f"download failed; cache fallback used: {outcome.download_error}"
        elif outcome.download_error:
            reason = f"{reason}; download failed: {outcome.download_error}"
        coverage_pct = round((len(present_days) / len(eligible_days)) * 100.0, 2) if len(eligible_days) > 0 else 0.0
        return {
            "ticker": ticker,
            "company_name": company_name,
            "requested_start": requested_start.isoformat(),
            "requested_end": requested_end.isoformat(),
            "actual_start": actual_start,
            "actual_end": actual_end,
            "trading_days": trading_days,
            "coverage_status": status,
            "missing_reason": reason,
            "network_attempts": outcome.network_attempts,
            "cache_used": bool(outcome.cache_used),
            "download_used": bool(outcome.download_used),
            "coverage_pct": coverage_pct,
        }

    present_days = requested_basis_days.intersection(history_days)
    missing_days = requested_basis_days.difference(history_days)
    actual_start = pd.Timestamp(history_days.min()).date()
    actual_end = pd.Timestamp(history_days.max()).date()
    if not missing_days.empty:
        status = "PARTIAL"
        reason_parts: list[str] = []
        if requested_basis_days.size > 0 and missing_days[0] == requested_basis_days[0]:
            reason_parts.append(f"history starts after requested_start: first_available={actual_start.isoformat()}")
        if requested_basis_days.size > 0 and missing_days[-1] == requested_basis_days[-1]:
            reason_parts.append(f"history ends before requested_end: last_available={actual_end.isoformat()}")
        reason_parts.append(f"missing_base_days={len(missing_days)}")
        reason_parts.append(f"first_missing={missing_days[0].date().isoformat()}")
        reason_parts.append(f"last_missing={missing_days[-1].date().isoformat()}")
        reason = "; ".join(reason_parts)
    else:
        status = "SUCCESS"
        reason = ""

    if outcome.download_error and not reason:
        reason = f"download failed; cache fallback used: {outcome.download_error}"
    elif outcome.download_error:
        reason = f"{reason}; download failed: {outcome.download_error}"

    coverage_pct = round((len(present_days) / len(requested_basis_days)) * 100.0, 2) if len(requested_basis_days) > 0 else 0.0
    return {
        "ticker": ticker,
        "company_name": company_name,
        "requested_start": requested_start.isoformat(),
        "requested_end": requested_end.isoformat(),
        "actual_start": actual_start.isoformat(),
        "actual_end": actual_end.isoformat(),
        "trading_days": int(len(history)),
        "coverage_status": status,
        "missing_reason": reason,
        "network_attempts": outcome.network_attempts,
        "cache_used": bool(outcome.cache_used),
        "download_used": bool(outcome.download_used),
        "coverage_pct": coverage_pct,
    }


def _dedupe_entries(entries: Iterable[Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in entries:
        if isinstance(item, dict):
            ticker = normalize_ticker_code(item.get("ticker", ""))
            company_name = normalize_text(item.get("company_name") or item.get("name"), ticker)
        else:
            ticker = normalize_ticker_code(item)
            company_name = ticker
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        result.append({"ticker": ticker, "company_name": company_name})
    if not result:
        raise HistoricalValidationError("Ticker universe is empty")
    return result


def _load_universe_from_csv(
    root: Path,
    universe_csv: str | Path,
    *,
    enforce_nikkei225: bool = True,
    expected_ticker_count: int = EXPECTED_NIKKEI225_COUNT,
) -> pd.DataFrame:
    csv_path = resolve_within(root, str(universe_csv))
    frame = read_csv_flexible(csv_path)
    normalized = _normalize_universe_for_validation(frame)
    has_member_periods = "member_periods" in normalized.columns
    if enforce_nikkei225:
        if not has_member_periods:
            raise HistoricalValidationError(
                "historical member_from/member_until coverage is required for 20-year validation."
            )
        if not normalized["ticker"].str.match(r"^[0-9A-Z]{4}\.T$", na=False).all():
            raise HistoricalValidationError("Ticker universe contains invalid Japanese equity tickers")
    return normalized


def build_data_coverage(
    universe: pd.DataFrame,
    histories: Mapping[str, pd.DataFrame],
    requested_start: pd.Timestamp,
    requested_end: pd.Timestamp,
) -> pd.DataFrame:
    normalized_universe = _normalize_universe_for_validation(pd.DataFrame(universe))
    rows: list[dict[str, Any]] = []
    start_date = pd.Timestamp(requested_start).date()
    end_date = pd.Timestamp(requested_end).date()
    prepared: list[tuple[str, str, pd.DataFrame, bool, Iterable[tuple[pd.Timestamp | None, pd.Timestamp | None]] | None]] = []
    available_histories: list[pd.DataFrame] = []
    for _, row in normalized_universe.iterrows():
        ticker = normalize_ticker_code(row["ticker"])
        company_name = normalize_text(row.get("company_name"), ticker)
        history = _valid_ohlcv_history(histories.get(ticker, pd.DataFrame()))
        cache_used = not history.empty
        available = history.loc[(history.index >= requested_start) & (history.index <= requested_end)] if not history.empty else history.iloc[0:0].copy()
        member_periods = row.get("member_periods") if "member_periods" in normalized_universe.columns else None
        prepared.append((ticker, company_name, available, cache_used, member_periods))
        if not available.empty:
            available_histories.append(available)
    market_day_basis = _market_day_basis_from_histories(available_histories)
    for ticker, company_name, available, cache_used, member_periods in prepared:
        outcome = FetchOutcome(
            history=available,
            cache_used=cache_used,
            download_used=False,
            network_attempts=0,
            download_error=None,
        )
        rows.append(
            build_coverage_row(
                ticker,
                company_name,
                start_date,
                end_date,
                outcome,
                market_day_basis=market_day_basis,
                member_periods=member_periods if "member_periods" in normalized_universe.columns else None,
            )
        )
    return pd.DataFrame(
        rows,
        columns=[
            "ticker",
            "company_name",
            "requested_start",
            "requested_end",
            "actual_start",
            "actual_end",
            "trading_days",
            "coverage_status",
            "missing_reason",
            "network_attempts",
            "cache_used",
            "download_used",
            "coverage_pct",
        ],
    )


def render_report(summary: Mapping[str, Any]) -> str:
    status_counts = summary.get("status_counts", {})
    rows = summary.get("rows", [])
    performance = summary.get("performance", {})
    output_files = summary.get("output_files", {})
    warnings = summary.get("warnings", [])
    cache_rows = sum(1 for row in rows if row.get("cache_used"))
    download_rows = sum(1 for row in rows if row.get("download_used"))
    lines = [
        "PHOENIX v7 HISTORICAL VALIDATION 20Y",
        "=" * 84,
        f"Status           : {summary.get('status', '')}",
        f"Requested start   : {summary.get('requested_start', '')}",
        f"Requested end     : {summary.get('requested_end', '')}",
        f"Actual start      : {summary.get('actual_start_date', '')}",
        f"Actual end        : {summary.get('actual_end_date', '')}",
        f"Trading days      : {summary.get('simulation_trading_days', 0)}",
        f"Tickers           : {summary.get('ticker_count', 0)}",
        f"Initial capital   : {summary.get('initial_capital_yen', 0):,.0f} yen",
        f"Lot size          : {summary.get('lot_size', 0)}",
        f"Fractional shares : {summary.get('fractional_shares', False)}",
        f"Coverage CSV      : {summary.get('coverage_csv', '')}",
        f"Cache dir         : {summary.get('cache_dir', '')}",
        "",
        "Performance",
        "-" * 84,
        f"Final equity      : {performance.get('final_equity_yen', 0):,.0f} yen",
        f"Total return      : {performance.get('total_return', performance.get('total_return_pct', 0)):+.2f}%",
        f"CAGR              : {performance.get('CAGR', performance.get('cagr_pct', 0)):+.2f}%",
        f"Max drawdown      : {performance.get('max_drawdown', performance.get('max_drawdown_pct', 0)):.2f}%",
        f"Profit factor     : {performance.get('profit_factor', 0):.3f}",
        f"Win rate          : {performance.get('win_rate', performance.get('win_rate_pct', 0)):.2f}%",
        f"Trade count       : {performance.get('trade_count', 0)}",
        f"Avg holding       : {performance.get('avg_holding', performance.get('average_holding_sessions', 0)):.2f} sessions",
        f"Cash ratio        : {performance.get('cash_ratio', 0):.2%}",
        f"Cash remaining    : {performance.get('cash_remaining_yen', 0):,.0f} yen",
        f"Market value      : {performance.get('market_value_yen', 0):,.0f} yen",
        f"Rejected lot      : {performance.get('rejected_due_to_lot', 0)}",
        f"Rejected buying   : {performance.get('rejected_due_to_buying_power', 0)}",
        f"Annual returns    : {performance.get('annual_returns_rows', 0)} rows",
        f"Monthly returns   : {performance.get('monthly_returns_rows', 0)} rows",
        "",
        "Coverage split",
        "-" * 84,
        f"SUCCESS            = {status_counts.get('SUCCESS', 0)}",
        f"PARTIAL            = {status_counts.get('PARTIAL', 0)}",
        f"NOT_ELIGIBLE       = {status_counts.get('NOT_ELIGIBLE', 0)}",
        f"NO_DATA            = {status_counts.get('NO_DATA', 0)}",
        f"DOWNLOAD_FAILED    = {status_counts.get('DOWNLOAD_FAILED', 0)}",
        f"INSUFFICIENT_HISTORY = {status_counts.get('INSUFFICIENT_HISTORY', 0)}",
        "",
        "Acquisition",
        "-" * 84,
        f"Cache rows         : {cache_rows}",
        f"Download rows      : {download_rows}",
        f"Network attempts   : {sum(int(row.get('network_attempts', 0)) for row in rows)}",
        "",
        "Warnings",
        "-" * 84,
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "Outputs",
            "-" * 84,
            f"Summary JSON       : {output_files.get('summary_json', '')}",
            f"Report text        : {output_files.get('report_text', '')}",
            f"Annual returns CSV : {output_files.get('annual_returns_csv', '')}",
            f"Monthly returns CSV: {output_files.get('monthly_returns_csv', '')}",
            f"Trades CSV         : {output_files.get('trades_csv', '')}",
            f"Equity curve CSV   : {output_files.get('equity_curve_csv', '')}",
            f"Coverage CSV       : {output_files.get('data_coverage_csv', '')}",
        ]
    )
    if output_files.get("risk_v2_research_csv"):
        lines.append(f"Risk v2 research   : {output_files.get('risk_v2_research_csv', '')}")
    if output_files.get("benchmark_equity_curve_csv"):
        lines.append(f"Benchmark CSV      : {output_files.get('benchmark_equity_curve_csv', '')}")
    lines.extend(
        [
            "",
            "Safety",
            "-" * 84,
            f"No RSS             : {summary.get('safety', {}).get('no_rss', False)}",
            f"No real orders     : {summary.get('safety', {}).get('no_real_orders', False)}",
            f"Orders submitted   : {summary.get('safety', {}).get('orders_submitted', 0)}",
            f"Live trading       : {summary.get('safety', {}).get('live_trading_enabled', False)}",
            "=" * 84,
        ]
    )
    return "\n".join(lines) + "\n"


def save_outputs(root: Path, settings: Mapping[str, Any], report: dict[str, Any], result: HistoricalValidationResult) -> None:
    output_dir = resolve_within(root, str(settings.get("output_dir", DEFAULT_OUTPUT_DIR)))
    summary_path = resolve_within(root, str(settings.get("report_json", DEFAULT_REPORT_JSON)))
    report_text_path = resolve_within(root, str(settings.get("report_text", DEFAULT_REPORT_TEXT)))
    coverage_setting = settings.get("coverage_csv", settings.get("data_coverage_csv", DEFAULT_COVERAGE_CSV))
    coverage_path = resolve_within(root, str(coverage_setting))
    diagnostics_setting = settings.get("diagnostics_csv", str(Path(DEFAULT_OUTPUT_DIR) / "diagnostics.csv"))
    diagnostics_path = resolve_within(root, str(diagnostics_setting))
    annual_path = resolve_within(root, str(settings.get("annual_returns_csv", str(Path(DEFAULT_OUTPUT_DIR) / "annual_returns.csv"))))
    monthly_path = resolve_within(root, str(settings.get("monthly_returns_csv", str(Path(DEFAULT_OUTPUT_DIR) / "monthly_returns.csv"))))
    trades_path = resolve_within(root, str(settings.get("trades_csv", str(Path(DEFAULT_OUTPUT_DIR) / "trades.csv"))))
    equity_path = resolve_within(root, str(settings.get("equity_curve_csv", str(Path(DEFAULT_OUTPUT_DIR) / "equity_curve.csv"))))
    risk_v2_research_enabled = bool(settings.get("market_breadth_filter_enabled", False))
    risk_v2_research_path = output_dir / "risk_v2_research.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in (summary_path, report_text_path, annual_path, monthly_path, coverage_path, diagnostics_path, trades_path, equity_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    report["output_files"] = {
        "summary_json": str(summary_path),
        "report_text": str(report_text_path),
        "annual_returns_csv": str(annual_path),
        "monthly_returns_csv": str(monthly_path),
        "data_coverage_csv": str(coverage_path),
        "diagnostics_csv": str(diagnostics_path),
        "trades_csv": str(trades_path),
        "equity_curve_csv": str(equity_path),
    }
    if risk_v2_research_enabled and not result.risk_v2_research.empty:
        report["output_files"]["risk_v2_research_csv"] = str(risk_v2_research_path)

    coverage_df = pd.DataFrame(report.get("rows", []), columns=[
        "ticker",
        "company_name",
        "requested_start",
        "requested_end",
        "actual_start",
        "actual_end",
        "trading_days",
        "coverage_status",
        "missing_reason",
        "network_attempts",
        "cache_used",
        "download_used",
        "coverage_pct",
    ])
    atomic_write(summary_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(report_text_path, render_report(report))
    result.annual_returns.to_csv(annual_path, index=False, encoding="utf-8-sig")
    result.monthly_returns.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    result.diagnostics.to_csv(diagnostics_path, index=False, encoding="utf-8-sig")
    result.trades.to_csv(trades_path, index=False, encoding="utf-8-sig")
    result.equity_curve.to_csv(equity_path, index=False, encoding="utf-8-sig")
    if risk_v2_research_enabled and not result.risk_v2_research.empty:
        result.risk_v2_research.to_csv(risk_v2_research_path, index=False, encoding="utf-8-sig")
    coverage_df.to_csv(coverage_path, index=False, encoding="utf-8-sig")


def run_historical_validation_20y(
    root: Path | None = None,
    config_path: Path | str | None = None,
    *,
    requested_start: Any | None = None,
    requested_end: Any | None = None,
    tickers: Iterable[Any] | None = None,
    universe_csv: str | Path | None = None,
    cache_dir: str | Path | None = None,
    output_csv: str | Path | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    repository = (root or ROOT).resolve()
    settings = load_settings(repository, config_path)
    if settings.get("enabled", True) is not True:
        raise HistoricalValidationError("Historical validation is disabled")
    config = _build_historical_validation_config(settings)
    checked = _as_jst(as_of)

    start_setting = requested_start if requested_start is not None else settings.get("requested_start")
    end_setting = requested_end if requested_end is not None else settings.get("requested_end")
    start_date, end_date = _normalize_requested_range(start_setting, end_setting, as_of=checked)

    # Compute fetch_start_date for warm-up history used only for indicator calculation.
    # Do NOT change any requested_start usages elsewhere (coverage, membership, simulation, reporting).
    fetch_start_date = (
        pd.Timestamp(start_date) - pd.offsets.BDay(config.minimum_history_sessions + 20)
    ).date()

    if tickers is not None:
        universe_df = pd.DataFrame(_dedupe_entries(tickers))
    else:
        source_csv = universe_csv if universe_csv is not None else settings.get("universe_csv", "data/nikkei225.csv")
        universe_df = _load_universe_from_csv(
            repository,
            source_csv,
            enforce_nikkei225=bool(settings.get("enforce_nikkei225", True)),
            expected_ticker_count=int(settings.get("expected_ticker_count", EXPECTED_NIKKEI225_COUNT) or EXPECTED_NIKKEI225_COUNT),
        )

    cache_setting = cache_dir if cache_dir is not None else settings.get("cache_dir", DEFAULT_CACHE_DIR)
    coverage_setting = output_csv if output_csv is not None else settings.get("coverage_csv", settings.get("data_coverage_csv", DEFAULT_COVERAGE_CSV))
    cache_root = resolve_within(repository, str(cache_setting))
    coverage_path = resolve_within(repository, str(coverage_setting))
    download_registry: set[tuple[str, date, date]] = set()

    fetched: list[tuple[dict[str, Any], FetchOutcome]] = []
    available_histories: list[pd.DataFrame] = []
    for entry in universe_df.to_dict(orient="records"):
        # Pass fetch_start_date as the start argument so histories include warm-up
        # while keeping all coverage/simulation/reporting anchored to start_date.
        outcome = fetch_ticker_history(
            repository,
            entry["ticker"],
            fetch_start_date,
            end_date,
            cache_dir=cache_root,
            as_of=checked,
            allow_network_fetch=bool(settings.get("allow_network_fetch", True)),
            download_registry=download_registry,
        )
        fetched.append((entry, outcome))
        if not outcome.history.empty:
            available_histories.append(outcome.history)

    market_day_basis = _market_day_basis_from_histories(available_histories)
    rows: list[dict[str, Any]] = []
    for entry, outcome in fetched:
        rows.append(
            build_coverage_row(
                entry["ticker"],
                entry["company_name"],
                start_date,
                end_date,
                outcome,
                market_day_basis=market_day_basis,
                member_periods=entry["member_periods"] if "member_periods" in universe_df.columns else None,
            )
        )

    rows = sorted(rows, key=lambda row: row["ticker"])
    status_counts = Counter(str(row["coverage_status"]) for row in rows)
    row_statuses = [str(row["coverage_status"]) for row in rows]
    histories = {entry["ticker"]: outcome.history for entry, outcome in fetched}
    prepared_histories = prepare_histories(histories, config)
    if any(not frame.empty for frame in prepared_histories.values()):
        result = simulate_validation(prepared_histories, universe_df, config, start_date, end_date)
    else:
        trade_columns = [
            "ticker",
            "company_name",
            "signal_date",
            "entry_date",
            "exit_date",
            "entry_price",
            "exit_price",
            "quantity",
            "entry_cost_yen",
            "exit_value_yen",
            "gross_profit_yen",
            "fees_yen",
            "profit_yen",
            "return_pct",
            "holding_sessions",
            "exit_reason",
            "signal_score",
        ]
        equity_columns = [
            "date",
            "cash_yen",
            "reserved_cash_yen",
            "available_cash_yen",
            "market_value_yen",
            "equity_yen",
            "peak_equity_yen",
            "drawdown_yen",
            "drawdown_pct",
            "open_positions",
            "pending_orders",
        ]
        period_columns = [
            "period",
            "start_date",
            "end_date",
            "start_equity_yen",
            "end_equity_yen",
            "profit_yen",
            "return_pct",
            "trade_count",
            "winning_trades",
            "losing_trades",
            "win_rate_pct",
            "max_drawdown_pct",
        ]
        result = HistoricalValidationResult(
            trades=pd.DataFrame(columns=trade_columns),
            equity_curve=pd.DataFrame(columns=equity_columns),
            annual_returns=pd.DataFrame(columns=period_columns),
            monthly_returns=pd.DataFrame(columns=period_columns),
            diagnostics=_build_diagnostics_frame(Counter(), start_date.year, end_date.year),
        )
    performance = _summarize_simulation_result(result, float(settings.get("initial_capital_yen", DEFAULT_INITIAL_CAPITAL_YEN)))
    if not result.equity_curve.empty and "date" in result.equity_curve.columns:
        actual_start_date = str(result.equity_curve["date"].iloc[0])
        actual_end_date = str(result.equity_curve["date"].iloc[-1])
    else:
        actual_start_date = ""
        actual_end_date = ""
    if row_statuses and all(status == "SUCCESS" for status in row_statuses):
        overall_status = "SUCCESS"
    else:
        effective_statuses = [status for status in row_statuses if status != "NOT_ELIGIBLE"]
        if not effective_statuses:
            overall_status = "NOT_ELIGIBLE"
        elif all(status == "SUCCESS" for status in effective_statuses):
            overall_status = "SUCCESS"
        elif any(status == "PARTIAL" for status in effective_statuses):
            overall_status = "PARTIAL"
        elif all(status in {"DOWNLOAD_FAILED", "NO_DATA", "INSUFFICIENT_HISTORY"} for status in effective_statuses):
            overall_status = "FAILED"
        else:
            overall_status = "PARTIAL"

    if "member_periods" in universe_df.columns:
        survivorship_warning = (
            "Historical member_from/member_until periods are respected, but survivorship bias can still remain "
            "if the supplied universe data is incomplete."
        )
    else:
        survivorship_warning = (
            "The supplied universe lacks historical member_from/member_until periods, so survivorship bias remains."
        )

    report = {
        "schema_version": 1,
        "version": "PHOENIX v7 Historical Validation 20Y",
        "generated_at": checked.isoformat(timespec="seconds"),
        "status": overall_status,
        "requested_start": start_date.isoformat(),
        "requested_end": end_date.isoformat(),
        "initial_capital_yen": float(settings.get("initial_capital_yen", DEFAULT_INITIAL_CAPITAL_YEN)),
        "lot_size": int(settings.get("lot_size", DEFAULT_LOT_SIZE)),
        "fractional_shares": bool(settings.get("fractional_shares", False)),
        "ticker_count": len(rows),
        "status_counts": dict(status_counts),
        "coverage_csv": str(coverage_path),
        "cache_dir": str(cache_root),
        "actual_start_date": actual_start_date,
        "actual_end_date": actual_end_date,
        "simulation_trading_days": int(len(result.equity_curve)),
        "rows": rows,
        "performance": performance,
        "warnings": [
            survivorship_warning,
            "No look-ahead bias is used: indicators are causal and entries are executed on the next session.",
        ],
        "safety": {
            "no_rss": bool(settings.get("no_rss", True)),
            "no_real_orders": bool(settings.get("no_real_orders", True)),
            "orders_submitted": int(settings.get("orders_submitted", 0)),
            "live_trading_enabled": bool(settings.get("live_trading_enabled", False)),
        },
        "validation_method": {
            "requested_start": start_date.isoformat(),
            "requested_end": end_date.isoformat(),
            "initial_capital_yen": float(settings.get("initial_capital_yen", DEFAULT_INITIAL_CAPITAL_YEN)),
            "lot_size": int(settings.get("lot_size", DEFAULT_LOT_SIZE)),
            "fractional_shares": bool(settings.get("fractional_shares", False)),
            "enforce_nikkei225": bool(settings.get("enforce_nikkei225", True)),
        },
    }
    save_outputs(repository, settings, report, result)
    return report


def verify_historical_validation_outputs(root: Path, config: Any | None = None) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        if config is None:
            settings = load_settings(root)
        elif isinstance(config, (str, Path)):
            settings = load_settings(root, config)
        elif isinstance(config, Mapping):
            settings = dict(DEFAULT_SETTINGS)
            settings.update(config)
        else:
            settings = dict(DEFAULT_SETTINGS)
            for key in DEFAULT_SETTINGS:
                if hasattr(config, key):
                    settings[key] = getattr(config, key)

        output_dir = resolve_within(root, str(settings.get("output_dir", DEFAULT_OUTPUT_DIR)))
        summary_path = resolve_within(root, str(settings.get("report_json", DEFAULT_REPORT_JSON)))
        report_text_path = resolve_within(root, str(settings.get("report_text", DEFAULT_REPORT_TEXT)))
        coverage_setting = settings.get("coverage_csv", settings.get("data_coverage_csv", DEFAULT_COVERAGE_CSV))
        coverage_path = resolve_within(root, str(coverage_setting))
        diagnostics_path = resolve_within(root, str(settings.get("diagnostics_csv", str(Path(DEFAULT_OUTPUT_DIR) / "diagnostics.csv"))))
        annual_path = resolve_within(root, str(settings.get("annual_returns_csv", str(Path(DEFAULT_OUTPUT_DIR) / "annual_returns.csv"))))
        monthly_path = resolve_within(root, str(settings.get("monthly_returns_csv", str(Path(DEFAULT_OUTPUT_DIR) / "monthly_returns.csv"))))
        trades_path = resolve_within(root, str(settings.get("trades_csv", str(Path(DEFAULT_OUTPUT_DIR) / "trades.csv"))))
        equity_path = resolve_within(root, str(settings.get("equity_curve_csv", str(Path(DEFAULT_OUTPUT_DIR) / "equity_curve.csv"))))
        risk_v2_research_enabled = bool(settings.get("market_breadth_filter_enabled", False))
        risk_v2_research_path = output_dir / "risk_v2_research.csv"

        summary = load_json_object(summary_path)
        coverage = read_csv_flexible(coverage_path)
        diagnostics = read_csv_flexible(diagnostics_path)
        required_columns = [
            "ticker",
            "company_name",
            "requested_start",
            "requested_end",
            "actual_start",
            "actual_end",
            "trading_days",
            "coverage_status",
            "missing_reason",
            "network_attempts",
            "cache_used",
            "download_used",
            "coverage_pct",
        ]

        if summary.get("initial_capital_yen") != DEFAULT_INITIAL_CAPITAL_YEN:
            errors.append("Initial capital does not match 500,000 yen")
        if summary.get("lot_size") != DEFAULT_LOT_SIZE:
            errors.append("Lot size does not match 100")
        if summary.get("fractional_shares") is not False:
            errors.append("Fractional shares must stay disabled")
        if not summary.get("performance"):
            errors.append("Performance summary is missing")
        if not summary.get("warnings") or not any("survivorship bias" in str(warning) for warning in summary.get("warnings", [])):
            errors.append("Survivorship bias warning is missing")
        output_files = summary.get("output_files", {})
        required_output_keys = [
            "summary_json",
            "report_text",
            "data_coverage_csv",
            "diagnostics_csv",
            "annual_returns_csv",
            "monthly_returns_csv",
            "trades_csv",
            "equity_curve_csv",
        ]
        if risk_v2_research_enabled:
            required_output_keys.append("risk_v2_research_csv")
        for key in required_output_keys:
            if key not in output_files:
                errors.append(f"Output file mapping missing: {key}")
        required_performance_keys = [
            "final_equity_yen",
            "total_return",
            "CAGR",
            "max_drawdown",
            "profit_factor",
            "win_rate",
            "trade_count",
            "avg_holding",
            "cash_ratio",
            "rejected_due_to_lot",
            "rejected_due_to_buying_power",
        ]
        performance = summary.get("performance", {})
        for key in required_performance_keys:
            if key not in performance:
                errors.append(f"Performance metric missing: {key}")
        for path in (summary_path, report_text_path, annual_path, monthly_path, coverage_path, diagnostics_path, trades_path, equity_path):
            if not path.is_file():
                errors.append(f"Missing output artifact: {path}")
        if list(coverage.columns[: len(required_columns)]) != required_columns:
            errors.append("data_coverage.csv columns are invalid")
        if not coverage.empty and not set(coverage["coverage_status"]).issubset(VALID_COVERAGE_STATUSES):
            errors.append("Coverage statuses contain unexpected values")
        if not summary.get("rows"):
            errors.append("Summary rows are missing")
        if summary.get("safety", {}).get("orders_submitted") != 0:
            errors.append("Summary must keep orders_submitted at 0")
        if not summary.get("safety", {}).get("no_rss", False):
            errors.append("Summary must keep no_rss true")
        if not summary.get("safety", {}).get("no_real_orders", False):
            errors.append("Summary must keep no_real_orders true")
        if list(diagnostics.columns[:3]) != ["year", "reason", "count"]:
            errors.append("diagnostics.csv columns are invalid")
        if risk_v2_research_enabled:
            if not risk_v2_research_path.is_file():
                errors.append(f"Missing output artifact: {risk_v2_research_path}")
            else:
                risk_v2_research = read_csv_flexible(risk_v2_research_path)
                if list(risk_v2_research.columns[: len(RISK_V2_RESEARCH_COLUMNS)]) != list(RISK_V2_RESEARCH_COLUMNS):
                    errors.append("risk_v2_research.csv columns are invalid")
    except Exception as error:
        errors.append(f"Verification failed: {type(error).__name__}: {error}")
    return not errors, errors


def print_historical_validation_summary(summary: Mapping[str, Any]) -> None:
    status_counts = summary.get("status_counts", {})
    performance = summary.get("performance", {})
    output_files = summary.get("output_files", {})
    warnings = summary.get("warnings", [])
    print("=" * 84)
    print("PHOENIX v7 HISTORICAL VALIDATION 20Y")
    print("=" * 84)
    print(f"Status         : {summary.get('status', '')}")
    print(f"Requested start: {summary.get('requested_start', '')}")
    print(f"Requested end  : {summary.get('requested_end', '')}")
    print(f"Actual start   : {summary.get('actual_start_date', '')}")
    print(f"Actual end     : {summary.get('actual_end_date', '')}")
    print(f"Trading days   : {summary.get('simulation_trading_days', 0)}")
    print(f"Tickers        : {summary.get('ticker_count', 0)}")
    print(f"Initial capital: {summary.get('initial_capital_yen', 0):,.0f} yen")
    print(f"Lot size       : {summary.get('lot_size', 0)}")
    print(f"Fractional     : {summary.get('fractional_shares', False)}")
    print(f"Final equity   : {performance.get('final_equity_yen', 0):,.0f} yen")
    print(f"Total return   : {performance.get('total_return', performance.get('total_return_pct', 0)):+.2f}%")
    print(f"CAGR           : {performance.get('CAGR', performance.get('cagr_pct', 0)):+.2f}%")
    print(f"Max drawdown   : {performance.get('max_drawdown', performance.get('max_drawdown_pct', 0)):.2f}%")
    print(f"Profit factor  : {performance.get('profit_factor', 0):.3f}")
    print(f"Win rate       : {performance.get('win_rate', performance.get('win_rate_pct', 0)):.2f}%")
    print(f"Trade count    : {performance.get('trade_count', 0)}")
    print(f"Avg holding    : {performance.get('avg_holding', performance.get('average_holding_sessions', 0)):.2f} sessions")
    print(f"Cash ratio     : {performance.get('cash_ratio', 0):.2%}")
    print(f"Rejected lot   : {performance.get('rejected_due_to_lot', 0)}")
    print(f"Rejected buy   : {performance.get('rejected_due_to_buying_power', 0)}")
    print(f"Annual returns : {performance.get('annual_returns_rows', 0)} rows")
    print(f"Monthly returns: {performance.get('monthly_returns_rows', 0)} rows")
    print(f"Coverage CSV   : {summary.get('coverage_csv', '')}")
    print(
        "Coverage split : "
        f"SUCCESS={status_counts.get('SUCCESS', 0)} "
        f"PARTIAL={status_counts.get('PARTIAL', 0)} "
        f"NOT_ELIGIBLE={status_counts.get('NOT_ELIGIBLE', 0)} "
        f"NO_DATA={status_counts.get('NO_DATA', 0)} "
        f"DOWNLOAD_FAILED={status_counts.get('DOWNLOAD_FAILED', 0)} "
        f"INSUFFICIENT_HISTORY={status_counts.get('INSUFFICIENT_HISTORY', 0)}"
    )
    if warnings:
        print("Warnings       :")
        for warning in warnings:
            print(f"  - {warning}")
    print("Outputs        :")
    print(f"  Summary JSON : {output_files.get('summary_json', '')}")
    print(f"  Report text  : {output_files.get('report_text', '')}")
    print(f"  Annual CSV   : {output_files.get('annual_returns_csv', '')}")
    print(f"  Monthly CSV  : {output_files.get('monthly_returns_csv', '')}")
    print(f"  Trades CSV   : {output_files.get('trades_csv', '')}")
    print(f"  Equity CSV   : {output_files.get('equity_curve_csv', '')}")
    print("=" * 84)


run_historical_validation = run_historical_validation_20y


def main(argv: list[str] | None = None) -> int:
    configure_console()
    parser = argparse.ArgumentParser(description="PHOENIX Historical Validation 20Y")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH, help="Path to the validation config JSON")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    lock = SingleInstanceLock(root / DEFAULT_LOCK_PATH)
    if not lock.acquire():
        print("Historical validation is already running.")
        return 2
    try:
        summary = run_historical_validation(root, Path(args.config))
        print_historical_validation_summary(summary)
        return 0
    except Exception as error:
        print(f"Historical validation error: {type(error).__name__}: {error}")
        return 1
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
