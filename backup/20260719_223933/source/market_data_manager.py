# market_data_manager.py
from __future__ import annotations

from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import random
import time
from typing import Any

import pandas as pd
import yfinance as yf


ROOT_DIR = Path(__file__).resolve().parent
CACHE_DIR = ROOT_DIR / "data" / "market_cache"
STATUS_FILE = CACHE_DIR / "cache_status.json"

DEFAULT_RETRIES = 3
DEFAULT_RETRY_WAIT = 2.0
REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")

PERIOD_DAYS = {
    "5d": 10,
    "1mo": 45,
    "3mo": 120,
    "6mo": 240,
    "1y": 420,
    "2y": 800,
    "3y": 1_200,
    "5y": 2_000,
    "10y": 4_000,
    "max": 15_000,
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def normalize_ticker(value: Any) -> str:
    ticker = str(value).strip().upper()

    if not ticker or ticker == "NAN":
        return ""

    if ticker.endswith(".T"):
        return ticker

    if ticker.replace(".", "").isalnum():
        return f"{ticker}.T"

    return ticker


def cache_path(ticker: str) -> Path:
    safe_name = normalize_ticker(ticker).replace(".", "_")
    return CACHE_DIR / f"{safe_name}.csv"


def normalize_history(data: pd.DataFrame, ticker: str = "") -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    result = data.copy()

    if isinstance(result.columns, pd.MultiIndex):
        ticker = normalize_ticker(ticker)
        levels = [
            set(str(value) for value in result.columns.get_level_values(i))
            for i in range(result.columns.nlevels)
        ]

        selected = False
        for level_number, values in enumerate(levels):
            if ticker and ticker in values:
                try:
                    result = result.xs(ticker, axis=1, level=level_number)
                    selected = True
                    break
                except (KeyError, ValueError):
                    pass

        if not selected and isinstance(result.columns, pd.MultiIndex):
            result.columns = result.columns.get_level_values(0)

    rename_map = {}
    for column in result.columns:
        normalized = str(column).strip().lower().replace(" ", "")
        aliases = {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "adjclose": "Adj Close",
            "volume": "Volume",
        }
        if normalized in aliases:
            rename_map[column] = aliases[normalized]

    result = result.rename(columns=rename_map)

    if "Close" not in result.columns and "Adj Close" in result.columns:
        result["Close"] = result["Adj Close"]

    if not all(column in result.columns for column in REQUIRED_COLUMNS):
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    result = result[list(REQUIRED_COLUMNS)].copy()

    for column in REQUIRED_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result.index = pd.to_datetime(result.index, errors="coerce")
    result = result[~result.index.isna()]

    if getattr(result.index, "tz", None) is not None:
        result.index = result.index.tz_localize(None)

    result = result[~result.index.duplicated(keep="last")]
    result = result.sort_index()
    result = result.dropna(subset=["Open", "High", "Low", "Close"])
    result = result[result["Close"] > 0]
    result["Volume"] = result["Volume"].fillna(0)

    return result


def load_cache(ticker: str) -> pd.DataFrame:
    path = cache_path(ticker)

    if not path.exists():
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))

    try:
        data = pd.read_csv(path, index_col=0, parse_dates=True)
        return normalize_history(data, ticker)
    except Exception:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS))


def save_cache(ticker: str, data: pd.DataFrame) -> None:
    normalized = normalize_history(data, ticker)

    if normalized.empty:
        return

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_cache(ticker)

    if not existing.empty:
        normalized = pd.concat([existing, normalized])
        normalized = normalized[~normalized.index.duplicated(keep="last")]
        normalized = normalized.sort_index()

    normalized.to_csv(cache_path(ticker), encoding="utf-8-sig")


def period_start_date(period: str) -> datetime:
    days = PERIOD_DAYS.get(period, 2_000)
    return datetime.now() - timedelta(days=days)


def filter_period(data: pd.DataFrame, period: str) -> pd.DataFrame:
    if data.empty or period == "max":
        return data.copy()

    start = pd.Timestamp(period_start_date(period).date())
    filtered = data.loc[data.index >= start].copy()
    return filtered if not filtered.empty else data.copy()


def _download_with_yf_download(ticker: str, period: str) -> pd.DataFrame:
    return yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        actions=False,
        progress=False,
        threads=False,
        group_by="column",
        timeout=20,
    )


def _download_with_ticker_history(ticker: str, period: str) -> pd.DataFrame:
    return yf.Ticker(ticker).history(
        period=period,
        interval="1d",
        auto_adjust=True,
        actions=False,
        timeout=20,
        raise_errors=False,
    )


def _download_with_dates(ticker: str, period: str) -> pd.DataFrame:
    start = period_start_date(period).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    return yf.download(
        ticker,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        actions=False,
        progress=False,
        threads=False,
        group_by="column",
        timeout=20,
    )


def update_status(
    ticker: str,
    source: str,
    rows: int,
    error: str = "",
) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    status: dict[str, Any] = {}

    if STATUS_FILE.exists():
        try:
            status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            status = {}

    status[normalize_ticker(ticker)] = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "rows": int(rows),
        "error": error,
    }

    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_history(
    ticker: str,
    period: str = "3y",
    retries: int = DEFAULT_RETRIES,
    retry_wait: float = DEFAULT_RETRY_WAIT,
    allow_cache: bool = True,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    ticker = normalize_ticker(ticker)

    if not ticker:
        return pd.DataFrame(columns=list(REQUIRED_COLUMNS)), "invalid_ticker"

    cached = load_cache(ticker) if allow_cache else pd.DataFrame()

    if force_refresh is False and not cached.empty:
        filtered = filter_period(cached, period)
        minimum_expected = {
            "5d": 3,
            "1mo": 15,
            "3mo": 45,
            "6mo": 90,
            "1y": 180,
            "2y": 360,
            "3y": 550,
            "5y": 900,
            "10y": 1_800,
            "max": 1_800,
        }.get(period, 100)

        latest_age = (pd.Timestamp.now().normalize() - filtered.index.max()).days

        if len(filtered) >= minimum_expected and latest_age <= 10:
            update_status(ticker, "cache", len(filtered))
            return filtered, "cache"

    methods = (
        ("yf.download(period)", _download_with_yf_download),
        ("Ticker.history", _download_with_ticker_history),
        ("yf.download(date)", _download_with_dates),
    )
    errors: list[str] = []

    for attempt in range(1, max(retries, 1) + 1):
        for source, method in methods:
            try:
                raw = method(ticker, period)
                normalized = normalize_history(raw, ticker)

                if not normalized.empty:
                    save_cache(ticker, normalized)
                    result = filter_period(load_cache(ticker), period)
                    update_status(ticker, source, len(result))
                    return result, source

                errors.append(f"{source}: empty")
            except Exception as error:
                errors.append(f"{source}: {type(error).__name__}: {error}")

        if attempt < max(retries, 1):
            delay = max(retry_wait, 0.0) * attempt + random.uniform(0.2, 0.8)
            time.sleep(delay)

    if allow_cache and not cached.empty:
        filtered = filter_period(cached, period)
        update_status(
            ticker,
            "stale_cache",
            len(filtered),
            " | ".join(errors[-6:]),
        )
        return filtered, "stale_cache"

    error_text = " | ".join(errors[-6:])
    update_status(ticker, "failed", 0, error_text)
    return pd.DataFrame(columns=list(REQUIRED_COLUMNS)), "failed"
