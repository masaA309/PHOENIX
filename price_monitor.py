# price_monitor.py

from __future__ import annotations

from datetime import datetime, time as clock_time
from pathlib import Path
import argparse
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from notify import load_environment, send_discord, send_line


# =========================================================
# 設定
# =========================================================

JST = ZoneInfo("Asia/Tokyo")

REPORT_DIR = Path("reports")

AI_FILE = REPORT_DIR / "ai_judgement.csv"
WATCHLIST_FILE = REPORT_DIR / "price_watchlist.csv"
STATE_FILE = REPORT_DIR / "price_monitor_state.csv"
EVENT_FILE = REPORT_DIR / "price_alert_history.csv"
LOG_FILE = REPORT_DIR / "price_monitor.log"

MARKET_OPEN = clock_time(9, 0)
MARKET_CLOSE = clock_time(15, 30)

DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 60
MAX_TARGETS = 20

# 同一銘柄・同一イベントの再通知を禁止
EVENT_TYPES = {
    "ENTRY",
    "TARGET",
    "STOP",
}

ENTRY_RATIO_BY_JUDGEMENT = {
    "優先監視": 0.990,
    "買い候補": 0.985,
    "押し目待ち": 0.970,
}

DEFAULT_TARGET_RATIO = 1.050
DEFAULT_STOP_RATIO = 0.970


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

        return float(value)

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
        if pd.isna(value):
            return default

        return int(float(value))

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


def is_market_open(
    current: datetime,
) -> bool:
    if current.weekday() >= 5:
        return False

    return (
        MARKET_OPEN
        <= current.time()
        <= MARKET_CLOSE
    )


# =========================================================
# AI判断読込
# =========================================================

def load_ai_targets() -> pd.DataFrame:
    if not AI_FILE.exists():
        raise FileNotFoundError(
            f"AI判断ファイルがありません: "
            f"{AI_FILE}"
        )

    df = pd.read_csv(
        AI_FILE,
    )

    required_columns = {
        "銘柄",
        "ticker",
        "価格",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
        "MACD判定",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "必要な列がありません: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    numeric_columns = [
        "価格",
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
    ]

    optional_numeric_columns = [
        "参考目標価格",
        "参考損切価格",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    for column in optional_numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    target_judgements = {
        "優先監視",
        "買い候補",
        "押し目待ち",
    }

    df = df[
        df["AI判断"].isin(
            target_judgements
        )
    ].copy()

    df = df.dropna(
        subset=[
            "銘柄",
            "ticker",
            "価格",
            "AI判断",
            "AI判断点",
        ]
    )

    judgement_order = {
        "優先監視": 0,
        "買い候補": 1,
        "押し目待ち": 2,
    }

    df["判断順"] = (
        df["AI判断"]
        .map(judgement_order)
        .fillna(99)
    )

    return (
        df.sort_values(
            by=[
                "判断順",
                "AI判断点",
                "PHOENIX_SCORE",
            ],
            ascending=[
                True,
                False,
                False,
            ],
        )
        .head(MAX_TARGETS)
        .drop(
            columns=["判断順"]
        )
        .reset_index(drop=True)
    )


# =========================================================
# 監視リスト
# =========================================================

def create_watchlist(
    ai_df: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    for _, row in ai_df.iterrows():
        judgement = str(
            row["AI判断"]
        )

        base_price = safe_float(
            row["価格"]
        )

        entry_ratio = (
            ENTRY_RATIO_BY_JUDGEMENT.get(
                judgement,
                0.970,
            )
        )

        entry_price = round(
            base_price * entry_ratio,
            2,
        )

        target_price = 0.0

        if (
            "参考目標価格"
            in row.index
            and pd.notna(
                row["参考目標価格"]
            )
        ):
            target_price = safe_float(
                row["参考目標価格"]
            )

        if target_price <= entry_price:
            target_price = round(
                entry_price
                * DEFAULT_TARGET_RATIO,
                2,
            )

        stop_price = 0.0

        if (
            "参考損切価格"
            in row.index
            and pd.notna(
                row["参考損切価格"]
            )
        ):
            stop_price = safe_float(
                row["参考損切価格"]
            )

        if (
            stop_price <= 0
            or stop_price >= entry_price
        ):
            stop_price = round(
                entry_price
                * DEFAULT_STOP_RATIO,
                2,
            )

        rows.append({
            "監視日": today_text(),
            "作成日時": timestamp_text(),
            "銘柄": str(
                row["銘柄"]
            ),
            "ticker": str(
                row["ticker"]
            ).strip(),
            "AI判断": judgement,
            "AI判断点": safe_int(
                row["AI判断点"]
            ),
            "PHOENIX_SCORE": safe_int(
                row["PHOENIX_SCORE"]
            ),
            "RSI": round(
                safe_float(
                    row["RSI"]
                ),
                2,
            ),
            "MACD判定": str(
                row["MACD判定"]
            ),
            "基準価格": round(
                base_price,
                2,
            ),
            "押し目価格": entry_price,
            "利確価格": target_price,
            "損切価格": stop_price,
        })

    watchlist = pd.DataFrame(
        rows
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    watchlist.to_csv(
        WATCHLIST_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    return watchlist


# =========================================================
# 状態管理
# =========================================================

def create_initial_state(
    watchlist: pd.DataFrame,
) -> pd.DataFrame:
    state = watchlist.copy()

    state["前回価格"] = pd.NA
    state["最新価格"] = pd.NA
    state["最新確認日時"] = ""

    # 最初の価格取得は基準登録だけで通知しない
    state["初回価格登録済み"] = False

    state["エントリー到達"] = False
    state["エントリー到達日時"] = ""

    state["利確到達"] = False
    state["利確到達日時"] = ""

    state["損切到達"] = False
    state["損切到達日時"] = ""

    state["監視状態"] = "初回価格待ち"

    return state


def load_previous_state() -> pd.DataFrame:
    if not STATE_FILE.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(
            STATE_FILE
        )

        if "監視日" not in df.columns:
            return pd.DataFrame()

        return df[
            df["監視日"].astype(str)
            == today_text()
        ].copy()

    except Exception as error:
        write_log(
            f"状態読込エラー: {error}"
        )

        return pd.DataFrame()


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
        "最新確認日時",
        "初回価格登録済み",
        "エントリー到達",
        "エントリー到達日時",
        "利確到達",
        "利確到達日時",
        "損切到達",
        "損切到達日時",
        "監視状態",
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

        for column in preserve_columns:
            if column in old_row.index:
                state.at[
                    index,
                    column,
                ] = old_row[column]

    return state


def save_state(
    state: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    state.to_csv(
        STATE_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def prepare_state(
    reset: bool,
) -> pd.DataFrame:
    ai_df = load_ai_targets()

    if ai_df.empty:
        raise ValueError(
            "監視対象銘柄がありません。"
        )

    watchlist = create_watchlist(
        ai_df
    )

    state = create_initial_state(
        watchlist
    )

    if not reset:
        previous = load_previous_state()

        state = merge_previous_state(
            state=state,
            previous=previous,
        )

    save_state(
        state
    )

    return state


# =========================================================
# 株価取得
# =========================================================

def normalize_prices(
    data: pd.DataFrame,
    tickers: list[str],
) -> dict[str, float]:
    prices: dict[str, float] = {}

    if data.empty:
        return prices

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

        for ticker in tickers:
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
                continue

            if "Close" not in ticker_data.columns:
                continue

            close = pd.to_numeric(
                ticker_data["Close"],
                errors="coerce",
            ).dropna()

            if close.empty:
                continue

            prices[ticker] = float(
                close.iloc[-1]
            )

        return prices

    if len(tickers) == 1:
        ticker = tickers[0]

        if "Close" not in data.columns:
            return prices

        close = pd.to_numeric(
            data["Close"],
            errors="coerce",
        ).dropna()

        if not close.empty:
            prices[ticker] = float(
                close.iloc[-1]
            )

    return prices


def fetch_current_prices(
    tickers: list[str],
) -> dict[str, float]:
    if not tickers:
        return {}

    try:
        data = yf.download(
            tickers=tickers,
            period="1d",
            interval="5m",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=False,
            timeout=30,
        )

    except Exception as error:
        write_log(
            f"株価取得エラー: {error}"
        )

        return {}

    return normalize_prices(
        data=data,
        tickers=tickers,
    )


# =========================================================
# クロス判定
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
# 通知
# =========================================================

def create_alert_message(
    event_type: str,
    row: pd.Series,
    previous_price: float,
    current_price: float,
) -> str:
    name = str(
        row["銘柄"]
    )

    ticker = str(
        row["ticker"]
    )

    entry_price = safe_float(
        row["押し目価格"]
    )

    target_price = safe_float(
        row["利確価格"]
    )

    stop_price = safe_float(
        row["損切価格"]
    )

    if event_type == "ENTRY":
        title = "🟢 PHOENIX ENTRY ALERT"

        event_text = (
            f"押し目価格 "
            f"{entry_price:,.2f}円を下抜け"
        )

    elif event_type == "TARGET":
        title = "🎯 PHOENIX TARGET ALERT"

        event_text = (
            f"利確価格 "
            f"{target_price:,.2f}円を上抜け"
        )

    else:
        title = "🔴 PHOENIX STOP ALERT"

        event_text = (
            f"損切価格 "
            f"{stop_price:,.2f}円を下抜け"
        )

    return (
        f"{title}\n"
        f"{timestamp_text()}\n"
        f"\n"
        f"{name} ({ticker})\n"
        f"{event_text}\n"
        f"\n"
        f"前回価格: {previous_price:,.2f}円\n"
        f"現在価格: {current_price:,.2f}円\n"
        f"\n"
        f"AI判断: {row['AI判断']}\n"
        f"AI判断点: "
        f"{safe_int(row['AI判断点'])}点\n"
        f"PHOENIX SCORE: "
        f"{safe_int(row['PHOENIX_SCORE'])}点\n"
        f"RSI: {safe_float(row['RSI']):.2f}\n"
        f"MACD: {row['MACD判定']}\n"
        f"\n"
        f"押し目価格: {entry_price:,.2f}円\n"
        f"利確価格: {target_price:,.2f}円\n"
        f"損切価格: {stop_price:,.2f}円\n"
        f"\n"
        f"※売買推奨ではなく監視通知です。"
    )


def send_alert(
    message: str,
    live: bool,
) -> tuple[
    bool,
    str,
]:
    if not live:
        return (
            True,
            "DRY RUN：外部通知なし",
        )

    discord_success, discord_result = (
        send_discord(
            message
        )
    )

    line_success, line_result = send_line(
        message
    )

    return (
        discord_success
        or line_success,
        (
            f"{discord_result} / "
            f"{line_result}"
        ),
    )


# =========================================================
# 履歴
# =========================================================

def event_exists(
    ticker: str,
    event_type: str,
) -> bool:
    if not EVENT_FILE.exists():
        return False

    try:
        history = pd.read_csv(
            EVENT_FILE
        )

    except Exception:
        return False

    required = {
        "監視日",
        "ticker",
        "イベント",
    }

    if not required.issubset(
        history.columns
    ):
        return False

    matches = history[
        (
            history["監視日"].astype(str)
            == today_text()
        )
        & (
            history["ticker"].astype(str)
            == ticker
        )
        & (
            history["イベント"].astype(str)
            == event_type
        )
    ]

    return not matches.empty


def append_event(
    event_type: str,
    row: pd.Series,
    previous_price: float,
    current_price: float,
    notification_result: str,
    live: bool,
) -> None:
    new_row = pd.DataFrame([
        {
            "監視日": today_text(),
            "日時": timestamp_text(),
            "イベント": event_type,
            "銘柄": row["銘柄"],
            "ticker": row["ticker"],
            "AI判断": row["AI判断"],
            "AI判断点": row["AI判断点"],
            "PHOENIX_SCORE": (
                row["PHOENIX_SCORE"]
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
            "実通知": live,
            "通知結果": notification_result,
        }
    ])

    if EVENT_FILE.exists():
        try:
            history = pd.read_csv(
                EVENT_FILE
            )

            new_row = pd.concat(
                [
                    history,
                    new_row,
                ],
                ignore_index=True,
            )

        except Exception:
            pass

    new_row.to_csv(
        EVENT_FILE,
        index=False,
        encoding="utf-8-sig",
    )


# =========================================================
# 判定
# =========================================================

def process_one_event(
    state: pd.DataFrame,
    index: int,
    row: pd.Series,
    event_type: str,
    previous_price: float,
    current_price: float,
    live: bool,
) -> None:
    ticker = str(
        row["ticker"]
    )

    if event_exists(
        ticker=ticker,
        event_type=event_type,
    ):
        return

    message = create_alert_message(
        event_type=event_type,
        row=row,
        previous_price=previous_price,
        current_price=current_price,
    )

    success, result = send_alert(
        message=message,
        live=live,
    )

    write_log(
        f"{event_type} "
        f"{ticker} "
        f"{previous_price:.2f}"
        f" -> "
        f"{current_price:.2f} "
        f"{result}"
    )

    append_event(
        event_type=event_type,
        row=row,
        previous_price=previous_price,
        current_price=current_price,
        notification_result=result,
        live=live,
    )

    check_time = timestamp_text()

    if event_type == "ENTRY":
        state.at[
            index,
            "エントリー到達",
        ] = True

        state.at[
            index,
            "エントリー到達日時",
        ] = check_time

        state.at[
            index,
            "監視状態",
        ] = (
            "保有監視中"
            if success
            else "エントリー通知失敗"
        )

    elif event_type == "TARGET":
        state.at[
            index,
            "利確到達",
        ] = True

        state.at[
            index,
            "利確到達日時",
        ] = check_time

        state.at[
            index,
            "監視状態",
        ] = (
            "利確到達"
            if success
            else "利確通知失敗"
        )

    elif event_type == "STOP":
        state.at[
            index,
            "損切到達",
        ] = True

        state.at[
            index,
            "損切到達日時",
        ] = check_time

        state.at[
            index,
            "監視状態",
        ] = (
            "損切到達"
            if success
            else "損切通知失敗"
        )


def process_prices(
    state: pd.DataFrame,
    prices: dict[str, float],
    live: bool,
) -> pd.DataFrame:
    check_time = timestamp_text()

    for index, row in state.iterrows():
        ticker = str(
            row["ticker"]
        )

        if ticker not in prices:
            continue

        current_price = float(
            prices[ticker]
        )

        initialized = bool_value(
            row["初回価格登録済み"]
        )

        previous_price = safe_float(
            row["最新価格"]
        )

        state.at[
            index,
            "前回価格",
        ] = previous_price or pd.NA

        state.at[
            index,
            "最新価格",
        ] = round(
            current_price,
            2,
        )

        state.at[
            index,
            "最新確認日時",
        ] = check_time

        # 初回は通知せず基準価格を登録
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
                f"{ticker}: "
                f"{current_price:.2f}円"
            )

            continue

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

        target_price = safe_float(
            row["利確価格"]
        )

        stop_price = safe_float(
            row["損切価格"]
        )

        # 1回の価格確認で最大1通知
        if not entry_reached:
            if crossed_down(
                previous_price=previous_price,
                current_price=current_price,
                trigger_price=entry_price,
            ):
                process_one_event(
                    state=state,
                    index=index,
                    row=row,
                    event_type="ENTRY",
                    previous_price=previous_price,
                    current_price=current_price,
                    live=live,
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
            process_one_event(
                state=state,
                index=index,
                row=row,
                event_type="TARGET",
                previous_price=previous_price,
                current_price=current_price,
                live=live,
            )

            continue

        if crossed_down(
            previous_price=previous_price,
            current_price=current_price,
            trigger_price=stop_price,
        ):
            process_one_event(
                state=state,
                index=index,
                row=row,
                event_type="STOP",
                previous_price=previous_price,
                current_price=current_price,
                live=live,
            )

    return state


# =========================================================
# 監視実行
# =========================================================

def run_one_cycle(
    state: pd.DataFrame,
    live: bool,
) -> pd.DataFrame:
    active = state[
        ~state["監視状態"].isin(
            [
                "利確到達",
                "損切到達",
            ]
        )
    ]

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

        return state

    write_log(
        f"株価取得開始: "
        f"{len(tickers)}銘柄"
    )

    prices = fetch_current_prices(
        tickers
    )

    write_log(
        f"株価取得成功: "
        f"{len(prices)}/"
        f"{len(tickers)}銘柄"
    )

    if not prices:
        return state

    state = process_prices(
        state=state,
        prices=prices,
        live=live,
    )

    save_state(
        state
    )

    return state


def monitor_loop(
    state: pd.DataFrame,
    interval_seconds: int,
    force: bool,
    live: bool,
) -> None:
    write_log(
        "PHOENIX PRICE MONITOR START"
    )

    write_log(
        "通知モード: "
        + (
            "LIVE"
            if live
            else "DRY RUN"
        )
    )

    while True:
        current = now_jst()

        if (
            not force
            and not is_market_open(current)
        ):
            if (
                current.weekday() >= 5
                or current.time()
                > MARKET_CLOSE
            ):
                write_log(
                    "市場時間外のため終了します。"
                )

                break

            write_log(
                "市場開始待機中"
            )

            time.sleep(300)
            continue

        state = run_one_cycle(
            state=state,
            live=live,
        )

        time.sleep(
            interval_seconds
        )


# =========================================================
# 引数
# =========================================================

def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PHOENIX安全価格監視"
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
            "指定しなければ通知しない"
        ),
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "当日の監視状態を初期化する"
        ),
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=(
            DEFAULT_INTERVAL_SECONDS
        ),
        help="監視間隔秒数",
    )

    return parser.parse_args()


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()
    load_environment()

    args = parse_arguments()

    print("=" * 90)
    print("PHOENIX SAFE PRICE MONITOR")
    print("=" * 90)

    try:
        state = prepare_state(
            reset=args.reset
        )

        print(
            state[
                [
                    "銘柄",
                    "ticker",
                    "AI判断",
                    "基準価格",
                    "押し目価格",
                    "利確価格",
                    "損切価格",
                    "監視状態",
                ]
            ].to_string(
                index=False
            )
        )

        print()
        print(
            "通知モード: "
            + (
                "LIVE"
                if args.live
                else "DRY RUN"
            )
        )

        print(
            f"監視リスト: "
            f"{WATCHLIST_FILE}"
        )

        print(
            f"状態ファイル: "
            f"{STATE_FILE}"
        )

        if args.once:
            run_one_cycle(
                state=state,
                live=args.live,
            )

            write_log(
                "1回監視完了"
            )

            return

        monitor_loop(
            state=state,
            interval_seconds=max(
                args.interval,
                MIN_INTERVAL_SECONDS,
            ),
            force=args.force,
            live=args.live,
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