# price_monitor.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as clock_time
from pathlib import Path
import argparse
import math
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from notify import load_environment, send_discord, send_line


# =========================================================
# 基本設定
# =========================================================

JST = ZoneInfo("Asia/Tokyo")

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"

WATCHLIST_FILE = REPORT_DIR / "price_watchlist.csv"

LIVE_STATE_FILE = REPORT_DIR / "price_monitor_state.csv"
DRY_STATE_FILE = REPORT_DIR / "price_monitor_state_dry_run.csv"

LIVE_EVENT_FILE = REPORT_DIR / "price_alert_history.csv"
DRY_EVENT_FILE = REPORT_DIR / "price_alert_dry_run.csv"

LOG_FILE = REPORT_DIR / "price_monitor.log"

DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 60
DEFAULT_MAX_TARGETS = 20
DEFAULT_MAX_QUOTE_AGE_MINUTES = 20

MORNING_OPEN = clock_time(9, 0)
MORNING_CLOSE = clock_time(11, 30)

AFTERNOON_OPEN = clock_time(12, 30)
AFTERNOON_CLOSE = clock_time(15, 30)

ACTIVE_MONITOR_TYPES = {
    "最優先監視",
    "買い監視",
    "押し目監視",
}

ENTRY_RATIO_BY_MONITOR_TYPE = {
    "最優先監視": 0.990,
    "買い監視": 0.985,
    "押し目監視": 0.970,
    "継続観察": 0.960,
}

DEFAULT_ENTRY_RATIO = 0.970
DEFAULT_TARGET_RATIO = 1.050
DEFAULT_STOP_RATIO = 0.970

EVENT_ENTRY = "ENTRY"
EVENT_TARGET = "TARGET"
EVENT_STOP = "STOP"

FINAL_STATUSES = {
    "利確到達",
    "損切到達",
}


# =========================================================
# 株価データ
# =========================================================

@dataclass
class Quote:
    ticker: str
    price: float
    timestamp: pd.Timestamp


# =========================================================
# 共通
# =========================================================

def configure_console() -> None:
    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    except (
        AttributeError,
        OSError,
    ):
        pass


def now_jst() -> datetime:
    return datetime.now(JST)


def timestamp_text() -> str:
    return now_jst().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def today_text() -> str:
    return now_jst().strftime(
        "%Y-%m-%d"
    )


def write_log(
    message: Any,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = (
        f"[{timestamp_text()}] "
        f"{message}"
    )

    print(
        text,
        flush=True,
    )

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            text + "\n"
        )


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if pd.isna(value):
            return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        return int(
            round(
                safe_float(
                    value,
                    default,
                )
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def bool_value(
    value: Any,
) -> bool:
    if isinstance(value, bool):
        return value

    return (
        str(value)
        .strip()
        .lower()
        in {
            "true",
            "1",
            "yes",
        }
    )


def read_csv_safe(
    file_path: Path,
) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame()

    last_error: Exception | None = None

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "cp932",
    ):
        try:
            return pd.read_csv(
                file_path,
                encoding=encoding,
            )

        except Exception as error:
            last_error = error

    if last_error is not None:
        raise last_error

    return pd.DataFrame()


def first_positive_value(
    row: pd.Series,
    candidates: list[str],
) -> float:
    for column in candidates:
        if column not in row.index:
            continue

        value = safe_float(
            row[column]
        )

        if value > 0:
            return value

    return 0.0


def state_file_for_mode(
    live: bool,
) -> Path:
    return (
        LIVE_STATE_FILE
        if live
        else DRY_STATE_FILE
    )


def event_file_for_mode(
    live: bool,
) -> Path:
    return (
        LIVE_EVENT_FILE
        if live
        else DRY_EVENT_FILE
    )


# =========================================================
# 市場時間
# =========================================================

def is_weekday(
    current: datetime,
) -> bool:
    return current.weekday() < 5


def is_morning_session(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and MORNING_OPEN
        <= current.time()
        <= MORNING_CLOSE
    )


def is_afternoon_session(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and AFTERNOON_OPEN
        <= current.time()
        <= AFTERNOON_CLOSE
    )


def is_market_open(
    current: datetime,
) -> bool:
    return (
        is_morning_session(current)
        or is_afternoon_session(current)
    )


def is_before_market_open(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and current.time()
        < MORNING_OPEN
    )


def is_lunch_break(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and MORNING_CLOSE
        < current.time()
        < AFTERNOON_OPEN
    )


def market_has_closed(
    current: datetime,
) -> bool:
    return (
        not is_weekday(current)
        or current.time()
        > AFTERNOON_CLOSE
    )


def seconds_until(
    current: datetime,
    target_time: clock_time,
) -> int:
    target = current.replace(
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )

    return max(
        int(
            (
                target
                - current
            ).total_seconds()
        ),
        0,
    )


# =========================================================
# Trade Engine監視リスト読込
# =========================================================

def load_trade_watchlist(
    max_targets: int,
) -> pd.DataFrame:
    if not WATCHLIST_FILE.exists():
        raise FileNotFoundError(
            "Trade Engine監視リストがありません: "
            f"{WATCHLIST_FILE}"
        )

    watchlist = read_csv_safe(
        WATCHLIST_FILE
    )

    if watchlist.empty:
        raise ValueError(
            "Trade Engine監視リストが空です。"
        )

    required_columns = {
        "銘柄",
        "ticker",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "基準価格",
        "押し目価格",
        "利確価格",
        "損切価格",
        "Trade判定",
        "ロット比率",
        "MarketRiskScore",
        "MarketRiskLevel",
    }

    missing_columns = (
        required_columns
        - set(watchlist.columns)
    )

    if missing_columns:
        raise ValueError(
            "price_watchlist.csv に必要な列がありません: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    numeric_columns = [
        "AI判断点",
        "PHOENIX_SCORE",
        "基準価格",
        "押し目価格",
        "利確価格",
        "損切価格",
        "ロット比率",
        "MarketRiskScore",
    ]

    optional_numeric_columns = [
        "RSI",
        "ランキング点",
        "順位",
        "期待勝率%",
        "期待騰落率%",
    ]

    for column in numeric_columns:
        watchlist[column] = pd.to_numeric(
            watchlist[column],
            errors="coerce",
        )

    for column in optional_numeric_columns:
        if column in watchlist.columns:
            watchlist[column] = pd.to_numeric(
                watchlist[column],
                errors="coerce",
            )

    watchlist["ticker"] = (
        watchlist["ticker"]
        .astype(str)
        .str.strip()
    )

    watchlist["Trade判定"] = (
        watchlist["Trade判定"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    watchlist = watchlist[
        watchlist["Trade判定"].isin(
            [
                "BUY",
                "WATCH",
            ]
        )
    ].copy()

    watchlist = watchlist.dropna(
        subset=[
            "銘柄",
            "ticker",
            "基準価格",
            "押し目価格",
            "利確価格",
            "損切価格",
        ]
    )

    watchlist = watchlist[
        (
            watchlist["基準価格"] > 0
        )
        & (
            watchlist["押し目価格"] > 0
        )
        & (
            watchlist["利確価格"] > 0
        )
        & (
            watchlist["損切価格"] > 0
        )
    ].copy()

    watchlist = watchlist[
        (
            watchlist["利確価格"]
            > watchlist["押し目価格"]
        )
        & (
            watchlist["損切価格"]
            < watchlist["押し目価格"]
        )
    ].copy()

    if watchlist.empty:
        raise ValueError(
            "有効な監視対象がありません。"
        )

    if "順位" not in watchlist.columns:
        watchlist["順位"] = range(
            1,
            len(watchlist) + 1,
        )

    if "ランキング点" not in watchlist.columns:
        watchlist["ランキング点"] = (
            watchlist["AI判断点"]
            .fillna(0)
            * 0.60
            + watchlist["PHOENIX_SCORE"]
            .fillna(0)
            * 0.40
        )

    watchlist["監視区分"] = (
        watchlist["Trade判定"]
        .map({
            "BUY": "買い監視",
            "WATCH": "押し目監視",
        })
        .fillna("継続観察")
    )

    if "RSI" not in watchlist.columns:
        watchlist["RSI"] = 0.0

    if "MACD判定" not in watchlist.columns:
        watchlist["MACD判定"] = ""

    if "期待勝率%" not in watchlist.columns:
        watchlist["期待勝率%"] = 0.0

    if "期待騰落率%" not in watchlist.columns:
        watchlist["期待騰落率%"] = 0.0

    if "リスク" not in watchlist.columns:
        watchlist["リスク"] = ""

    if "ランク" not in watchlist.columns:
        watchlist["ランク"] = ""

    if "評価" not in watchlist.columns:
        watchlist["評価"] = ""

    if "判定理由" not in watchlist.columns:
        watchlist["判定理由"] = ""

    if "生成日時" not in watchlist.columns:
        watchlist["生成日時"] = ""

    priority_map = {
        "BUY": 0,
        "WATCH": 1,
    }

    watchlist["監視優先順位"] = (
        watchlist["Trade判定"]
        .map(priority_map)
        .fillna(9)
    )

    watchlist = (
        watchlist.sort_values(
            by=[
                "監視優先順位",
                "AI判断点",
                "PHOENIX_SCORE",
                "ランキング点",
            ],
            ascending=[
                True,
                False,
                False,
                False,
            ],
        )
        .head(
            max(
                max_targets,
                1,
            )
        )
        .reset_index(
            drop=True,
        )
    )

    watchlist["順位"] = range(
        1,
        len(watchlist) + 1,
    )

    watchlist = watchlist.drop(
        columns=[
            "監視優先順位",
        ]
    )

    return watchlist


# =========================================================
# 監視価格作成
# =========================================================

def calculate_entry_price(
    row: pd.Series,
) -> float:
    explicit_price = first_positive_value(
        row,
        [
            "押し目価格",
            "買い価格",
            "押し目価格_ai",
            "買い価格_ai",
        ],
    )

    if explicit_price > 0:
        return round(
            explicit_price,
            2,
        )

    base_price = safe_float(
        row["価格"]
    )

    monitor_type = str(
        row["監視区分"]
    ).strip()

    ratio = (
        ENTRY_RATIO_BY_MONITOR_TYPE.get(
            monitor_type,
            DEFAULT_ENTRY_RATIO,
        )
    )

    return round(
        base_price
        * ratio,
        2,
    )


def calculate_target_price(
    row: pd.Series,
    entry_price: float,
) -> float:
    explicit_price = first_positive_value(
        row,
        [
            "参考目標価格",
            "目標価格",
            "参考目標価格_ai",
            "目標価格_ai",
        ],
    )

    if explicit_price > entry_price:
        return round(
            explicit_price,
            2,
        )

    return round(
        entry_price
        * DEFAULT_TARGET_RATIO,
        2,
    )


def calculate_stop_price(
    row: pd.Series,
    entry_price: float,
) -> float:
    explicit_price = first_positive_value(
        row,
        [
            "参考損切価格",
            "損切価格",
            "参考損切価格_ai",
            "損切価格_ai",
        ],
    )

    if (
        explicit_price > 0
        and explicit_price < entry_price
    ):
        return round(
            explicit_price,
            2,
        )

    return round(
        entry_price
        * DEFAULT_STOP_RATIO,
        2,
    )


def create_watchlist(
    targets: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    created_at = timestamp_text()
    monitor_date = today_text()

    for _, row in targets.iterrows():
        rows.append({
            "監視日": monitor_date,
            "作成日時": created_at,
            "順位": safe_int(
                row["順位"]
            ),
            "銘柄": str(
                row["銘柄"]
            ),
            "ticker": str(
                row["ticker"]
            ).strip(),
            "ランキング点": round(
                safe_float(
                    row.get(
                        "ランキング点",
                        0.0,
                    )
                ),
                4,
            ),
            "ランク": str(
                row.get(
                    "ランク",
                    "",
                )
            ),
            "評価": str(
                row.get(
                    "評価",
                    "",
                )
            ),
            "監視区分": str(
                row["監視区分"]
            ),
            "AI判断": str(
                row["AI判断"]
            ),
            "AI判断点": safe_int(
                row["AI判断点"]
            ),
            "PHOENIX_SCORE": safe_int(
                row["PHOENIX_SCORE"]
            ),
            "期待勝率%": round(
                safe_float(
                    row.get(
                        "期待勝率%",
                        0.0,
                    )
                ),
                2,
            ),
            "期待騰落率%": round(
                safe_float(
                    row.get(
                        "期待騰落率%",
                        0.0,
                    )
                ),
                4,
            ),
            "リスク": str(
                row.get(
                    "リスク",
                    "",
                )
            ),
            "RSI": round(
                safe_float(
                    row.get(
                        "RSI",
                        0.0,
                    )
                ),
                2,
            ),
            "MACD判定": str(
                row.get(
                    "MACD判定",
                    "",
                )
            ),
            "基準価格": round(
                safe_float(
                    row["基準価格"]
                ),
                2,
            ),
            "押し目価格": round(
                safe_float(
                    row["押し目価格"]
                ),
                2,
            ),
            "利確価格": round(
                safe_float(
                    row["利確価格"]
                ),
                2,
            ),
            "損切価格": round(
                safe_float(
                    row["損切価格"]
                ),
                2,
            ),
            "Trade判定": str(
                row["Trade判定"]
            ),
            "ロット比率": round(
                safe_float(
                    row["ロット比率"]
                ),
                2,
            ),
            "MarketRiskScore": round(
                safe_float(
                    row["MarketRiskScore"]
                ),
                2,
            ),
            "MarketRiskLevel": str(
                row["MarketRiskLevel"]
            ),
            "判定理由": str(
                row.get(
                    "判定理由",
                    "",
                )
            ),
            "生成日時": str(
                row.get(
                    "生成日時",
                    "",
                )
            ),
        })

    return pd.DataFrame(
        rows
    )


# =========================================================
# 状態管理
# =========================================================

def create_initial_state(
    watchlist: pd.DataFrame,
) -> pd.DataFrame:
    state = watchlist.copy()

    state["前回価格"] = pd.NA
    state["最新価格"] = pd.NA
    state["株価時刻"] = ""
    state["最新確認日時"] = ""

    state["初回価格登録済み"] = False

    state["エントリー到達"] = False
    state["エントリー到達日時"] = ""

    state["利確到達"] = False
    state["利確到達日時"] = ""

    state["損切到達"] = False
    state["損切到達日時"] = ""

    state["監視状態"] = "初回価格待ち"

    state["保留通知イベントID"] = ""
    state["保留通知イベント"] = ""
    state["保留通知前回価格"] = pd.NA
    state["保留通知現在価格"] = pd.NA
    state["保留通知発生日時"] = ""
    state["保留通知試行回数"] = 0
    state["保留通知最終結果"] = ""

    return state


def load_previous_state(
    state_file: Path,
) -> pd.DataFrame:
    if not state_file.exists():
        return pd.DataFrame()

    try:
        previous = read_csv_safe(
            state_file
        )

    except Exception as error:
        write_log(
            f"状態読込エラー: {error}"
        )

        return pd.DataFrame()

    if (
        previous.empty
        or "監視日" not in previous.columns
    ):
        return pd.DataFrame()

    previous = previous[
        previous["監視日"].astype(str)
        == today_text()
    ].copy()

    return previous


def trigger_prices_match(
    new_row: pd.Series,
    old_row: pd.Series,
) -> bool:
    columns = [
        "押し目価格",
        "利確価格",
        "損切価格",
    ]

    for column in columns:
        new_value = safe_float(
            new_row[column]
        )

        old_value = safe_float(
            old_row.get(
                column,
                0.0,
            )
        )

        if abs(
            new_value
            - old_value
        ) > 0.01:
            return False

    return True


def merge_previous_state(
    state: pd.DataFrame,
    previous: pd.DataFrame,
) -> pd.DataFrame:
    if previous.empty:
        return state

    previous = (
        previous.drop_duplicates(
            subset=["ticker"],
            keep="last",
        )
        .set_index("ticker")
    )

    preserve_columns = [
        "前回価格",
        "最新価格",
        "株価時刻",
        "最新確認日時",
        "初回価格登録済み",
        "エントリー到達",
        "エントリー到達日時",
        "利確到達",
        "利確到達日時",
        "損切到達",
        "損切到達日時",
        "監視状態",
        "保留通知イベントID",
        "保留通知イベント",
        "保留通知前回価格",
        "保留通知現在価格",
        "保留通知発生日時",
        "保留通知試行回数",
        "保留通知最終結果",
    ]

    for index, row in state.iterrows():
        ticker = str(
            row["ticker"]
        )

        if ticker not in previous.index:
            continue

        old_row = previous.loc[
            ticker
        ]

        if isinstance(
            old_row,
            pd.DataFrame,
        ):
            old_row = old_row.iloc[-1]

        if not trigger_prices_match(
            row,
            old_row,
        ):
            continue

        for column in preserve_columns:
            if column in old_row.index:
                state.at[
                    index,
                    column,
                ] = old_row[column]

    return state


def save_state(
    state: pd.DataFrame,
    state_file: Path,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    state.to_csv(
        state_file,
        index=False,
        encoding="utf-8-sig",
    )


def prepare_state(
    live: bool,
    reset: bool,
    max_targets: int,
) -> pd.DataFrame:
    targets = load_trade_watchlist(
        max_targets=max_targets,
    )

    watchlist = create_watchlist(
        targets
    )

    state = create_initial_state(
        watchlist
    )

    state_file = state_file_for_mode(
        live
    )

    if not reset:
        previous = load_previous_state(
            state_file
        )

        state = merge_previous_state(
            state,
            previous,
        )

    save_state(
        state,
        state_file,
    )

    return state


# =========================================================
# 株価取得
# =========================================================

def normalize_timestamp(
    value: Any,
) -> pd.Timestamp:
    timestamp = pd.Timestamp(
        value
    )

    if timestamp.tzinfo is None:
        return timestamp.tz_localize(
            JST
        )

    return timestamp.tz_convert(
        JST
    )


def extract_close_series(
    data: pd.DataFrame,
    ticker: str,
    ticker_count: int,
) -> pd.Series:
    if data.empty:
        return pd.Series(
            dtype=float
        )

    if isinstance(
        data.columns,
        pd.MultiIndex,
    ):
        level_zero = (
            data.columns
            .get_level_values(0)
        )

        level_one = (
            data.columns
            .get_level_values(1)
        )

        ticker_data = pd.DataFrame()

        if ticker in level_zero:
            ticker_data = data[
                ticker
            ].copy()

        elif ticker in level_one:
            ticker_data = data.xs(
                ticker,
                axis=1,
                level=1,
            ).copy()

        if ticker_data.empty:
            return pd.Series(
                dtype=float
            )

        for candidate in (
            "Close",
            "Adj Close",
        ):
            if candidate in ticker_data.columns:
                return pd.to_numeric(
                    ticker_data[candidate],
                    errors="coerce",
                ).dropna()

        return pd.Series(
            dtype=float
        )

    if ticker_count == 1:
        for candidate in (
            "Close",
            "Adj Close",
        ):
            if candidate in data.columns:
                return pd.to_numeric(
                    data[candidate],
                    errors="coerce",
                ).dropna()

    return pd.Series(
        dtype=float
    )


def fetch_current_quotes(
    tickers: list[str],
) -> dict[str, Quote]:
    if not tickers:
        return {}

    try:
        data = yf.download(
            tickers=tickers,
            period="1d",
            interval="5m",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=False,
            timeout=30,
        )

    except Exception as error:
        write_log(
            f"株価取得エラー: {error}"
        )

        return {}

    quotes: dict[str, Quote] = {}

    for ticker in tickers:
        close = extract_close_series(
            data=data,
            ticker=ticker,
            ticker_count=len(tickers),
        )

        if close.empty:
            continue

        price = safe_float(
            close.iloc[-1]
        )

        if price <= 0:
            continue

        try:
            quote_timestamp = normalize_timestamp(
                close.index[-1]
            )

        except Exception:
            quote_timestamp = pd.Timestamp(
                now_jst()
            )

        quotes[ticker] = Quote(
            ticker=ticker,
            price=price,
            timestamp=quote_timestamp,
        )

    return quotes


def quote_age_minutes(
    quote: Quote,
) -> float:
    current = pd.Timestamp(
        now_jst()
    )

    difference = (
        current
        - quote.timestamp
    )

    age = (
        difference.total_seconds()
        / 60.0
    )

    return max(
        age,
        0.0,
    )


def quote_is_fresh(
    quote: Quote,
    maximum_age_minutes: int,
) -> bool:
    age = quote_age_minutes(
        quote
    )

    return age <= maximum_age_minutes


# =========================================================
# 価格クロス
# =========================================================

def crossed_down(
    previous_price: float,
    current_price: float,
    trigger_price: float,
) -> bool:
    return (
        previous_price > trigger_price
        and current_price <= trigger_price
    )


def crossed_up(
    previous_price: float,
    current_price: float,
    trigger_price: float,
) -> bool:
    return (
        previous_price < trigger_price
        and current_price >= trigger_price
    )


# =========================================================
# イベント履歴
# =========================================================

def load_event_keys(
    event_file: Path,
) -> set[tuple[str, str, str]]:
    if not event_file.exists():
        return set()

    try:
        history = read_csv_safe(
            event_file
        )

    except Exception:
        return set()

    required_columns = {
        "監視日",
        "ticker",
        "イベント",
    }

    if not required_columns.issubset(
        history.columns
    ):
        return set()

    history = history[
        history["監視日"].astype(str)
        == today_text()
    ]

    keys: set[
        tuple[str, str, str]
    ] = set()

    for _, row in history.iterrows():
        keys.add(
            (
                str(row["監視日"]),
                str(row["ticker"]),
                str(row["イベント"]),
            )
        )

    return keys


def create_event_id(
    ticker: str,
    event_type: str,
) -> str:
    return (
        f"{today_text()}_"
        f"{ticker}_"
        f"{event_type}_"
        f"{now_jst().strftime('%H%M%S%f')}"
    )


def append_event(
    event_file: Path,
    event_id: str,
    event_type: str,
    row: pd.Series,
    previous_price: float,
    current_price: float,
    quote_timestamp: pd.Timestamp,
    live: bool,
    notification_success: bool,
    notification_result: str,
) -> None:
    event_row = pd.DataFrame([
        {
            "イベントID": event_id,
            "監視日": today_text(),
            "日時": timestamp_text(),
            "イベント": event_type,
            "順位": row["順位"],
            "銘柄": row["銘柄"],
            "ticker": row["ticker"],
            "ランキング点": row["ランキング点"],
            "監視区分": row["監視区分"],
            "AI判断": row["AI判断"],
            "AI判断点": row["AI判断点"],
            "PHOENIX_SCORE": row["PHOENIX_SCORE"],
            "期待勝率%": row.get(
                "期待勝率%",
                0.0,
            ),
            "期待騰落率%": row.get(
                "期待騰落率%",
                0.0,
            ),
            "前回価格": round(
                previous_price,
                2,
            ),
            "現在価格": round(
                current_price,
                2,
            ),
            "押し目価格": row["押し目価格"],
            "利確価格": row["利確価格"],
            "損切価格": row["損切価格"],
            "株価時刻": quote_timestamp.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "実通知": live,
            "通知成功": notification_success,
            "通知結果": notification_result,
            "通知更新日時": timestamp_text(),
        }
    ])

    file_exists = event_file.exists()

    event_row.to_csv(
        event_file,
        mode="a",
        header=not file_exists,
        index=False,
        encoding="utf-8-sig",
    )


def update_event_notification(
    event_file: Path,
    event_id: str,
    notification_success: bool,
    notification_result: str,
) -> None:
    if not event_file.exists():
        return

    try:
        history = read_csv_safe(
            event_file
        )

    except Exception as error:
        write_log(
            f"イベント履歴更新エラー: {error}"
        )

        return

    if (
        history.empty
        or "イベントID" not in history.columns
    ):
        return

    matched = (
        history["イベントID"].astype(str)
        == str(event_id)
    )

    if not matched.any():
        return

    history.loc[
        matched,
        "通知成功",
    ] = notification_success

    history.loc[
        matched,
        "通知結果",
    ] = notification_result

    history.loc[
        matched,
        "通知更新日時",
    ] = timestamp_text()

    history.to_csv(
        event_file,
        index=False,
        encoding="utf-8-sig",
    )


# =========================================================
# 通知
# =========================================================

def create_alert_message(
    event_type: str,
    row: pd.Series,
    previous_price: float,
    current_price: float,
    quote_timestamp: pd.Timestamp,
) -> str:
    entry_price = safe_float(
        row["押し目価格"]
    )

    target_price = safe_float(
        row["利確価格"]
    )

    stop_price = safe_float(
        row["損切価格"]
    )

    if event_type == EVENT_ENTRY:
        title = (
            "🟢 PHOENIX BUY PRICE ALERT"
        )

        event_text = (
            f"押し目価格 "
            f"{entry_price:,.2f}円へ到達"
        )

    elif event_type == EVENT_TARGET:
        title = (
            "🎯 PHOENIX TARGET ALERT"
        )

        event_text = (
            f"利確価格 "
            f"{target_price:,.2f}円へ到達"
        )

    else:
        title = (
            "🔴 PHOENIX STOP ALERT"
        )

        event_text = (
            f"損切価格 "
            f"{stop_price:,.2f}円へ到達"
        )

    return (
        f"{title}\n"
        f"{timestamp_text()}\n"
        f"\n"
        f"ランキング {safe_int(row['順位'])}位\n"
        f"{row['銘柄']} ({row['ticker']})\n"
        f"{event_text}\n"
        f"\n"
        f"前回価格: {previous_price:,.2f}円\n"
        f"現在価格: {current_price:,.2f}円\n"
        f"株価時刻: "
        f"{quote_timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"\n"
        f"ランキング点: "
        f"{safe_float(row['ランキング点']):.4f}点\n"
        f"監視区分: {row['監視区分']}\n"
        f"AI判断: {row['AI判断']}\n"
        f"AI判断点: {safe_int(row['AI判断点'])}点\n"
        f"PHOENIX SCORE: "
        f"{safe_int(row['PHOENIX_SCORE'])}点\n"
        f"期待勝率: "
        f"{safe_float(row.get('期待勝率%', 0.0)):.2f}%\n"
        f"期待騰落率: "
        f"{safe_float(row.get('期待騰落率%', 0.0)):+.4f}%\n"
        f"\n"
        f"押し目価格: {entry_price:,.2f}円\n"
        f"利確価格: {target_price:,.2f}円\n"
        f"損切価格: {stop_price:,.2f}円\n"
        f"\n"
        f"※売買推奨ではなく価格監視通知です。"
    )


def send_alert(
    message: str,
    live: bool,
) -> tuple[bool, str]:
    if not live:
        return (
            True,
            "DRY RUN：外部通知なし",
        )

    discord_success = False
    discord_result = (
        "Discord未実行"
    )

    line_success = False
    line_result = (
        "LINE未実行"
    )

    try:
        (
            discord_success,
            discord_result,
        ) = send_discord(
            message
        )

    except Exception as error:
        discord_result = (
            f"Discordエラー: {error}"
        )

    try:
        (
            line_success,
            line_result,
        ) = send_line(
            message
        )

    except Exception as error:
        line_result = (
            f"LINEエラー: {error}"
        )

    return (
        (
            discord_success
            or line_success
        ),
        (
            f"{discord_result} / "
            f"{line_result}"
        ),
    )


# =========================================================
# 保留通知
# =========================================================

def clear_pending_notification(
    state: pd.DataFrame,
    index: int,
) -> None:
    state.at[
        index,
        "保留通知イベントID",
    ] = ""

    state.at[
        index,
        "保留通知イベント",
    ] = ""

    state.at[
        index,
        "保留通知前回価格",
    ] = pd.NA

    state.at[
        index,
        "保留通知現在価格",
    ] = pd.NA

    state.at[
        index,
        "保留通知発生日時",
    ] = ""

    state.at[
        index,
        "保留通知試行回数",
    ] = 0

    state.at[
        index,
        "保留通知最終結果",
    ] = ""


def set_pending_notification(
    state: pd.DataFrame,
    index: int,
    event_id: str,
    event_type: str,
    previous_price: float,
    current_price: float,
    result: str,
) -> None:
    state.at[
        index,
        "保留通知イベントID",
    ] = event_id

    state.at[
        index,
        "保留通知イベント",
    ] = event_type

    state.at[
        index,
        "保留通知前回価格",
    ] = previous_price

    state.at[
        index,
        "保留通知現在価格",
    ] = current_price

    state.at[
        index,
        "保留通知発生日時",
    ] = timestamp_text()

    state.at[
        index,
        "保留通知試行回数",
    ] = 1

    state.at[
        index,
        "保留通知最終結果",
    ] = result


def retry_pending_notifications(
    state: pd.DataFrame,
    live: bool,
    event_file: Path,
) -> set[str]:
    retried_tickers: set[str] = set()

    if not live:
        return retried_tickers

    for index, row in state.iterrows():
        event_id = str(
            row.get(
                "保留通知イベントID",
                "",
            )
        ).strip()

        event_type = str(
            row.get(
                "保留通知イベント",
                "",
            )
        ).strip()

        if (
            not event_id
            or not event_type
            or event_id.lower() == "nan"
            or event_type.lower() == "nan"
        ):
            continue

        ticker = str(
            row["ticker"]
        )

        previous_price = safe_float(
            row.get(
                "保留通知前回価格",
                0.0,
            )
        )

        current_price = safe_float(
            row.get(
                "保留通知現在価格",
                0.0,
            )
        )

        quote_timestamp_text = str(
            row.get(
                "株価時刻",
                "",
            )
        )

        try:
            quote_timestamp = normalize_timestamp(
                quote_timestamp_text
            )

        except Exception:
            quote_timestamp = pd.Timestamp(
                now_jst()
            )

        message = create_alert_message(
            event_type=event_type,
            row=row,
            previous_price=previous_price,
            current_price=current_price,
            quote_timestamp=quote_timestamp,
        )

        success, result = send_alert(
            message=message,
            live=True,
        )

        attempts = (
            safe_int(
                row.get(
                    "保留通知試行回数",
                    0,
                )
            )
            + 1
        )

        state.at[
            index,
            "保留通知試行回数",
        ] = attempts

        state.at[
            index,
            "保留通知最終結果",
        ] = result

        update_event_notification(
            event_file=event_file,
            event_id=event_id,
            notification_success=success,
            notification_result=result,
        )

        write_log(
            f"通知再試行 "
            f"{ticker} "
            f"{event_type} "
            f"試行{attempts}回 "
            f"{result}"
        )

        retried_tickers.add(
            ticker
        )

        if success:
            clear_pending_notification(
                state,
                index,
            )

    return retried_tickers


# =========================================================
# イベント処理
# =========================================================

def apply_event_state(
    state: pd.DataFrame,
    index: int,
    event_type: str,
    notification_success: bool,
) -> None:
    current_time = timestamp_text()

    if event_type == EVENT_ENTRY:
        state.at[
            index,
            "エントリー到達",
        ] = True

        state.at[
            index,
            "エントリー到達日時",
        ] = current_time

        state.at[
            index,
            "監視状態",
        ] = (
            "保有監視中"
            if notification_success
            else "保有監視中・通知保留"
        )

    elif event_type == EVENT_TARGET:
        state.at[
            index,
            "利確到達",
        ] = True

        state.at[
            index,
            "利確到達日時",
        ] = current_time

        state.at[
            index,
            "監視状態",
        ] = (
            "利確到達"
            if notification_success
            else "利確到達・通知保留"
        )

    elif event_type == EVENT_STOP:
        state.at[
            index,
            "損切到達",
        ] = True

        state.at[
            index,
            "損切到達日時",
        ] = current_time

        state.at[
            index,
            "監視状態",
        ] = (
            "損切到達"
            if notification_success
            else "損切到達・通知保留"
        )


def process_event(
    state: pd.DataFrame,
    index: int,
    row: pd.Series,
    event_type: str,
    previous_price: float,
    current_price: float,
    quote_timestamp: pd.Timestamp,
    live: bool,
    event_file: Path,
    event_keys: set[
        tuple[str, str, str]
    ],
) -> None:
    ticker = str(
        row["ticker"]
    )

    event_key = (
        today_text(),
        ticker,
        event_type,
    )

    if event_key in event_keys:
        return

    event_id = create_event_id(
        ticker=ticker,
        event_type=event_type,
    )

    message = create_alert_message(
        event_type=event_type,
        row=row,
        previous_price=previous_price,
        current_price=current_price,
        quote_timestamp=quote_timestamp,
    )

    success, result = send_alert(
        message=message,
        live=live,
    )

    append_event(
        event_file=event_file,
        event_id=event_id,
        event_type=event_type,
        row=row,
        previous_price=previous_price,
        current_price=current_price,
        quote_timestamp=quote_timestamp,
        live=live,
        notification_success=success,
        notification_result=result,
    )

    event_keys.add(
        event_key
    )

    apply_event_state(
        state=state,
        index=index,
        event_type=event_type,
        notification_success=success,
    )

    if (
        live
        and not success
    ):
        set_pending_notification(
            state=state,
            index=index,
            event_id=event_id,
            event_type=event_type,
            previous_price=previous_price,
            current_price=current_price,
            result=result,
        )

    write_log(
        f"{event_type} "
        f"{ticker} "
        f"{previous_price:.2f}"
        f" -> "
        f"{current_price:.2f} "
        f"{result}"
    )


# =========================================================
# 株価判定
# =========================================================

def process_quotes(
    state: pd.DataFrame,
    quotes: dict[str, Quote],
    live: bool,
    event_file: Path,
    maximum_quote_age_minutes: int,
    skip_tickers: set[str],
) -> pd.DataFrame:
    event_keys = load_event_keys(
        event_file
    )

    check_time = timestamp_text()

    for index, row in state.iterrows():
        ticker = str(
            row["ticker"]
        )

        if ticker in skip_tickers:
            continue

        if ticker not in quotes:
            continue

        quote = quotes[
            ticker
        ]

        if (
            live
            and not quote_is_fresh(
                quote,
                maximum_quote_age_minutes,
            )
        ):
            write_log(
                f"古い株価のため判定停止 "
                f"{ticker}: "
                f"{quote.timestamp.strftime('%Y-%m-%d %H:%M:%S')} "
                f"経過{quote_age_minutes(quote):.1f}分"
            )

            continue

        current_price = quote.price

        initialized = bool_value(
            row["初回価格登録済み"]
        )

        previous_price = safe_float(
            row["最新価格"]
        )

        state.at[
            index,
            "前回価格",
        ] = (
            previous_price
            if previous_price > 0
            else pd.NA
        )

        state.at[
            index,
            "最新価格",
        ] = round(
            current_price,
            2,
        )

        state.at[
            index,
            "株価時刻",
        ] = quote.timestamp.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        state.at[
            index,
            "最新確認日時",
        ] = check_time

        entry_reached = bool_value(
            row["エントリー到達"]
        )

        target_reached = bool_value(
            row["利確到達"]
        )

        stop_reached = bool_value(
            row["損切到達"]
        )

        entry_price = safe_float(
            row["押し目価格"]
        )

        if (
            not initialized
            or previous_price <= 0
        ):
            state.at[
                index,
                "初回価格登録済み",
            ] = True

            state.at[
                index,
                "監視状態",
            ] = "監視中"

            write_log(
                f"初回価格登録 "
                f"順位{safe_int(row['順位'])} "
                f"{ticker}: "
                f"{current_price:.2f}円"
            )

            # 起動時点ですでに押し目価格以下なら、
            # クロス待ちにせずENTRYイベントを記録する。
            if (
                not entry_reached
                and entry_price > 0
                and current_price <= entry_price
            ):
                process_event(
                    state=state,
                    index=index,
                    row=row,
                    event_type=EVENT_ENTRY,
                    previous_price=current_price,
                    current_price=current_price,
                    quote_timestamp=quote.timestamp,
                    live=live,
                    event_file=event_file,
                    event_keys=event_keys,
                )

            continue

        target_price = safe_float(
            row["利確価格"]
        )

        stop_price = safe_float(
            row["損切価格"]
        )

        # 1銘柄・1周期で最大1イベント
        if not entry_reached:
            if crossed_down(
                previous_price=previous_price,
                current_price=current_price,
                trigger_price=entry_price,
            ):
                process_event(
                    state=state,
                    index=index,
                    row=row,
                    event_type=EVENT_ENTRY,
                    previous_price=previous_price,
                    current_price=current_price,
                    quote_timestamp=quote.timestamp,
                    live=live,
                    event_file=event_file,
                    event_keys=event_keys,
                )

            continue

        if (
            target_reached
            or stop_reached
        ):
            continue

        if crossed_up(
            previous_price=previous_price,
            current_price=current_price,
            trigger_price=target_price,
        ):
            process_event(
                state=state,
                index=index,
                row=row,
                event_type=EVENT_TARGET,
                previous_price=previous_price,
                current_price=current_price,
                quote_timestamp=quote.timestamp,
                live=live,
                event_file=event_file,
                event_keys=event_keys,
            )

            continue

        if crossed_down(
            previous_price=previous_price,
            current_price=current_price,
            trigger_price=stop_price,
        ):
            process_event(
                state=state,
                index=index,
                row=row,
                event_type=EVENT_STOP,
                previous_price=previous_price,
                current_price=current_price,
                quote_timestamp=quote.timestamp,
                live=live,
                event_file=event_file,
                event_keys=event_keys,
            )

    return state


# =========================================================
# 監視実行
# =========================================================

def run_one_cycle(
    state: pd.DataFrame,
    live: bool,
    maximum_quote_age_minutes: int,
) -> pd.DataFrame:
    state_file = state_file_for_mode(
        live
    )

    event_file = event_file_for_mode(
        live
    )

    retried_tickers = (
        retry_pending_notifications(
            state=state,
            live=live,
            event_file=event_file,
        )
    )

    active = state[
        ~state["監視状態"].astype(str).isin(
            FINAL_STATUSES
        )
    ].copy()

    tickers = (
        active["ticker"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    if not tickers:
        write_log(
            "有効な監視対象がありません。"
        )

        save_state(
            state,
            state_file,
        )

        return state

    write_log(
        f"株価取得開始: "
        f"{len(tickers)}銘柄"
    )

    quotes = fetch_current_quotes(
        tickers
    )

    write_log(
        f"株価取得成功: "
        f"{len(quotes)}/"
        f"{len(tickers)}銘柄"
    )

    if quotes:
        state = process_quotes(
            state=state,
            quotes=quotes,
            live=live,
            event_file=event_file,
            maximum_quote_age_minutes=(
                maximum_quote_age_minutes
            ),
            skip_tickers=retried_tickers,
        )

    save_state(
        state,
        state_file,
    )

    return state


def monitor_loop(
    state: pd.DataFrame,
    interval_seconds: int,
    live: bool,
    force: bool,
    maximum_quote_age_minutes: int,
) -> None:
    write_log(
        "PHOENIX TRADE PRICE MONITOR START"
    )

    write_log(
        "通知モード: "
        + (
            "LIVE"
            if live
            else "DRY RUN"
        )
    )

    write_log(
        f"監視間隔: "
        f"{interval_seconds}秒"
    )

    while True:
        current = now_jst()

        if not force:
            if not is_weekday(
                current
            ):
                write_log(
                    "土日のため監視終了"
                )

                break

            if is_before_market_open(
                current
            ):
                wait_seconds = seconds_until(
                    current,
                    MORNING_OPEN,
                )

                write_log(
                    f"市場開始待機: "
                    f"{wait_seconds}秒"
                )

                time.sleep(
                    min(
                        wait_seconds,
                        300,
                    )
                )

                continue

            if is_lunch_break(
                current
            ):
                wait_seconds = seconds_until(
                    current,
                    AFTERNOON_OPEN,
                )

                write_log(
                    f"昼休み待機: "
                    f"{wait_seconds}秒"
                )

                time.sleep(
                    min(
                        wait_seconds,
                        300,
                    )
                )

                continue

            if market_has_closed(
                current
            ):
                write_log(
                    "市場終了時刻を過ぎました。"
                )

                break

            if not is_market_open(
                current
            ):
                time.sleep(30)
                continue

        state = run_one_cycle(
            state=state,
            live=live,
            maximum_quote_age_minutes=(
                maximum_quote_age_minutes
            ),
        )

        time.sleep(
            interval_seconds
        )

    save_state(
        state,
        state_file_for_mode(
            live
        ),
    )

    write_log(
        "PHOENIX TRADE PRICE MONITOR END"
    )


# =========================================================
# 引数
# =========================================================

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PHOENIX Trade Engine連動価格監視"
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="価格確認を1回だけ実行",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="市場時間外でも実行",
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "LINE・Discordへ実通知する。"
            "未指定時はDRY RUN"
        ),
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="当日の監視状態を初期化",
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="監視間隔秒数",
    )

    parser.add_argument(
        "--max-targets",
        type=int,
        default=DEFAULT_MAX_TARGETS,
        help="Trade Engine監視リストから使う最大銘柄数",
    )

    parser.add_argument(
        "--max-quote-age",
        type=int,
        default=(
            DEFAULT_MAX_QUOTE_AGE_MINUTES
        ),
        help=(
            "実通知で許可する"
            "株価データの最大経過分数"
        ),
    )

    return parser.parse_args()


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()
    load_environment()

    arguments = parse_arguments()

    live = arguments.live

    print("=" * 115)
    print("PHOENIX TRADE ENGINE PRICE MONITOR")
    print("=" * 115)

    try:
        state = prepare_state(
            live=live,
            reset=arguments.reset,
            max_targets=max(
                arguments.max_targets,
                1,
            ),
        )

        display_columns = [
            "順位",
            "銘柄",
            "ticker",
            "ランキング点",
            "監視区分",
            "基準価格",
            "押し目価格",
            "利確価格",
            "損切価格",
            "監視状態",
        ]

        print(
            state[
                display_columns
            ].to_string(
                index=False
            )
        )

        print()

        print(
            "通知モード: "
            + (
                "LIVE"
                if live
                else "DRY RUN"
            )
        )

        print(
            "監視元: Trade Engine"
        )

        print(
            f"監視リスト: "
            f"{WATCHLIST_FILE}"
        )

        print(
            f"状態ファイル: "
            f"{state_file_for_mode(live)}"
        )

        print(
            f"イベント履歴: "
            f"{event_file_for_mode(live)}"
        )

        if arguments.once:
            state = run_one_cycle(
                state=state,
                live=live,
                maximum_quote_age_minutes=max(
                    arguments.max_quote_age,
                    1,
                ),
            )

            save_state(
                state,
                state_file_for_mode(
                    live
                ),
            )

            write_log(
                "1回監視完了"
            )

            return

        monitor_loop(
            state=state,
            interval_seconds=max(
                arguments.interval,
                MIN_INTERVAL_SECONDS,
            ),
            live=live,
            force=arguments.force,
            maximum_quote_age_minutes=max(
                arguments.max_quote_age,
                1,
            ),
        )

    except KeyboardInterrupt:
        write_log(
            "手動停止しました。"
        )

    except Exception as error:
        write_log(
            f"エラー: {error}"
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()