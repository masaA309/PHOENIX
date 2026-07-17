# paper_trader.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Any

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"

WATCHLIST_FILE = REPORT_DIR / "price_watchlist.csv"

LIVE_STATE_FILE = REPORT_DIR / "price_monitor_state.csv"
LIVE_EVENT_FILE = REPORT_DIR / "price_alert_history.csv"

DRY_RUN_STATE_FILE = REPORT_DIR / "price_monitor_state_dry_run.csv"
DRY_RUN_EVENT_FILE = REPORT_DIR / "price_alert_dry_run.csv"

# AUTO:
#   DRY RUN用とLIVE用のうち、更新日時が新しい組を自動選択します。
# DRY_RUN:
#   price_monitor_state_dry_run.csv / price_alert_dry_run.csv を使用します。
# LIVE:
#   price_monitor_state.csv / price_alert_history.csv を使用します。
MONITOR_FILE_MODE = "AUTO"


def file_modified_time(
    file_path: Path,
) -> float:
    try:
        return file_path.stat().st_mtime

    except OSError:
        return 0.0


def select_monitor_files() -> tuple[
    Path,
    Path,
    str,
]:
    mode = (
        MONITOR_FILE_MODE
        .strip()
        .upper()
    )

    if mode == "DRY_RUN":
        return (
            DRY_RUN_STATE_FILE,
            DRY_RUN_EVENT_FILE,
            "DRY RUN",
        )

    if mode == "LIVE":
        return (
            LIVE_STATE_FILE,
            LIVE_EVENT_FILE,
            "LIVE",
        )

    dry_run_modified = max(
        file_modified_time(
            DRY_RUN_STATE_FILE
        ),
        file_modified_time(
            DRY_RUN_EVENT_FILE
        ),
    )

    live_modified = max(
        file_modified_time(
            LIVE_STATE_FILE
        ),
        file_modified_time(
            LIVE_EVENT_FILE
        ),
    )

    dry_run_exists = (
        DRY_RUN_STATE_FILE.exists()
        or DRY_RUN_EVENT_FILE.exists()
    )

    live_exists = (
        LIVE_STATE_FILE.exists()
        or LIVE_EVENT_FILE.exists()
    )

    if (
        dry_run_exists
        and (
            not live_exists
            or dry_run_modified
            >= live_modified
        )
    ):
        return (
            DRY_RUN_STATE_FILE,
            DRY_RUN_EVENT_FILE,
            "DRY RUN",
        )

    if live_exists:
        return (
            LIVE_STATE_FILE,
            LIVE_EVENT_FILE,
            "LIVE",
        )

    return (
        DRY_RUN_STATE_FILE,
        DRY_RUN_EVENT_FILE,
        "DRY RUN",
    )


STATE_FILE, EVENT_FILE, ACTIVE_MONITOR_MODE = (
    select_monitor_files()
)

TRADES_FILE = REPORT_DIR / "paper_trades.csv"
SUMMARY_FILE = REPORT_DIR / "paper_trade_summary.csv"
LEARNING_FILE = REPORT_DIR / "paper_learning_data.csv"
TEXT_REPORT_FILE = REPORT_DIR / "paper_trade_report.txt"

INITIAL_CAPITAL = 1_000_000
MAX_POSITION_AMOUNT = 200_000
DEFAULT_LOT_SIZE = 100

COMMISSION_RATE = 0.0
SLIPPAGE_RATE = 0.001

OPEN_STATUS = "保有中"
TARGET_STATUS = "利確"
STOP_STATUS = "損切"
CLOSED_STATUSES = {
    TARGET_STATUS,
    STOP_STATUS,
}


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


def now_text() -> str:
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
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


def load_csv(
    file_path: Path,
) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(
            file_path,
        )

    except Exception as error:
        print(
            f"読込エラー {file_path}: {error}"
        )

        return pd.DataFrame()


def load_watchlist() -> pd.DataFrame:
    df = load_csv(
        WATCHLIST_FILE
    )

    if df.empty:
        raise FileNotFoundError(
            f"監視リストがありません: "
            f"{WATCHLIST_FILE}"
        )

    required_columns = {
        "銘柄",
        "ticker",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
        "MACD判定",
        "基準価格",
        "押し目価格",
        "利確価格",
        "損切価格",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "監視リストに必要な列がありません: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    return df


def load_events() -> pd.DataFrame:
    df = load_csv(
        EVENT_FILE
    )

    if df.empty:
        return pd.DataFrame()

    required_columns = {
        "日時",
        "イベント",
        "銘柄",
        "ticker",
        "現在価格",
    }

    if not required_columns.issubset(
        df.columns
    ):
        return pd.DataFrame()

    df["日時"] = pd.to_datetime(
        df["日時"],
        errors="coerce",
    )

    df["現在価格"] = pd.to_numeric(
        df["現在価格"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "日時",
            "ticker",
            "イベント",
            "現在価格",
        ]
    )

    return (
        df.sort_values(
            by="日時",
        )
        .reset_index(
            drop=True,
        )
    )


def load_state() -> pd.DataFrame:
    df = load_csv(
        STATE_FILE
    )

    if df.empty:
        return pd.DataFrame()

    if "最新価格" in df.columns:
        df["最新価格"] = pd.to_numeric(
            df["最新価格"],
            errors="coerce",
        )

    return df


def load_trades() -> pd.DataFrame:
    df = load_csv(
        TRADES_FILE
    )

    if df.empty:
        return pd.DataFrame(
            columns=[
                "取引ID",
                "銘柄",
                "ticker",
                "AI判断",
                "AI判断点",
                "PHOENIX_SCORE",
                "RSI",
                "MACD判定",
                "基準価格",
                "押し目価格",
                "利確価格",
                "損切価格",
                "エントリー日時",
                "エントリー価格",
                "株数",
                "投資額",
                "決済日時",
                "決済価格",
                "決済理由",
                "状態",
                "損益額",
                "損益率%",
                "保有時間",
                "最高価格",
                "最低価格",
                "最大含み益率%",
                "最大含み損率%",
                "最終更新日時",
            ]
        )

    return df


def calculate_quantity(
    entry_price: float,
) -> int:
    if entry_price <= 0:
        return 0

    affordable_quantity = int(
        MAX_POSITION_AMOUNT
        // entry_price
    )

    lot_quantity = (
        affordable_quantity
        // DEFAULT_LOT_SIZE
        * DEFAULT_LOT_SIZE
    )

    if lot_quantity >= DEFAULT_LOT_SIZE:
        return lot_quantity

    if entry_price <= MAX_POSITION_AMOUNT:
        return 1

    return 0


def calculate_buy_price(
    market_price: float,
) -> float:
    return round(
        market_price
        * (
            1
            + SLIPPAGE_RATE
        ),
        2,
    )


def calculate_sell_price(
    market_price: float,
) -> float:
    return round(
        market_price
        * (
            1
            - SLIPPAGE_RATE
        ),
        2,
    )


def create_trade_id(
    ticker: str,
    entry_datetime: pd.Timestamp,
) -> str:
    return (
        f"{ticker}_"
        + entry_datetime.strftime(
            "%Y%m%d%H%M%S"
        )
    )


def find_watchlist_row(
    watchlist: pd.DataFrame,
    ticker: str,
) -> pd.Series | None:
    matched = watchlist[
        watchlist["ticker"].astype(str)
        == str(ticker)
    ]

    if matched.empty:
        return None

    return matched.iloc[-1]


def trade_is_open(
    trades: pd.DataFrame,
    ticker: str,
) -> bool:
    if trades.empty:
        return False

    matched = trades[
        (
            trades["ticker"].astype(str)
            == str(ticker)
        )
        & (
            trades["状態"]
            == OPEN_STATUS
        )
    ]

    return not matched.empty


def event_already_processed(
    trades: pd.DataFrame,
    ticker: str,
    event_type: str,
    event_datetime: pd.Timestamp,
) -> bool:
    if trades.empty:
        return False

    if event_type == "ENTRY":
        matched = trades[
            (
                trades["ticker"].astype(str)
                == str(ticker)
            )
            & (
                pd.to_datetime(
                    trades["エントリー日時"],
                    errors="coerce",
                )
                == event_datetime
            )
        ]

        return not matched.empty

    matched = trades[
        (
            trades["ticker"].astype(str)
            == str(ticker)
        )
        & (
            pd.to_datetime(
                trades["決済日時"],
                errors="coerce",
            )
            == event_datetime
        )
    ]

    return not matched.empty


def open_trade(
    trades: pd.DataFrame,
    event: pd.Series,
    watch_row: pd.Series,
) -> pd.DataFrame:
    ticker = str(
        event["ticker"]
    )

    if trade_is_open(
        trades,
        ticker,
    ):
        return trades

    event_datetime = pd.Timestamp(
        event["日時"]
    )

    market_price = safe_float(
        event["現在価格"]
    )

    entry_price = calculate_buy_price(
        market_price
    )

    quantity = calculate_quantity(
        entry_price
    )

    if quantity <= 0:
        print(
            f"購入上限超過: "
            f"{ticker} "
            f"{entry_price:.2f}円"
        )

        return trades

    investment_amount = round(
        entry_price
        * quantity,
        2,
    )

    commission = round(
        investment_amount
        * COMMISSION_RATE,
        2,
    )

    investment_amount += commission

    new_trade = {
        "取引ID": create_trade_id(
            ticker,
            event_datetime,
        ),
        "銘柄": str(
            watch_row["銘柄"]
        ),
        "ticker": ticker,
        "AI判断": str(
            watch_row["AI判断"]
        ),
        "AI判断点": safe_int(
            watch_row["AI判断点"]
        ),
        "PHOENIX_SCORE": safe_int(
            watch_row["PHOENIX_SCORE"]
        ),
        "RSI": safe_float(
            watch_row["RSI"]
        ),
        "MACD判定": str(
            watch_row["MACD判定"]
        ),
        "基準価格": safe_float(
            watch_row["基準価格"]
        ),
        "押し目価格": safe_float(
            watch_row["押し目価格"]
        ),
        "利確価格": safe_float(
            watch_row["利確価格"]
        ),
        "損切価格": safe_float(
            watch_row["損切価格"]
        ),
        "エントリー日時": event_datetime.strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "エントリー価格": entry_price,
        "株数": quantity,
        "投資額": investment_amount,
        "決済日時": "",
        "決済価格": pd.NA,
        "決済理由": "",
        "状態": OPEN_STATUS,
        "損益額": 0.0,
        "損益率%": 0.0,
        "保有時間": "",
        "最高価格": entry_price,
        "最低価格": entry_price,
        "最大含み益率%": 0.0,
        "最大含み損率%": 0.0,
        "最終更新日時": now_text(),
    }

    trades = pd.concat(
        [
            trades,
            pd.DataFrame(
                [new_trade]
            ),
        ],
        ignore_index=True,
    )

    print(
        f"仮想買付: "
        f"{watch_row['銘柄']} "
        f"{ticker} "
        f"{quantity}株 "
        f"{entry_price:,.2f}円"
    )

    return trades


def close_trade(
    trades: pd.DataFrame,
    event: pd.Series,
    close_reason: str,
) -> pd.DataFrame:
    ticker = str(
        event["ticker"]
    )

    matched_indexes = trades.index[
        (
            trades["ticker"].astype(str)
            == ticker
        )
        & (
            trades["状態"]
            == OPEN_STATUS
        )
    ].tolist()

    if not matched_indexes:
        return trades

    index = matched_indexes[-1]

    market_price = safe_float(
        event["現在価格"]
    )

    exit_price = calculate_sell_price(
        market_price
    )

    entry_price = safe_float(
        trades.at[
            index,
            "エントリー価格",
        ]
    )

    quantity = safe_int(
        trades.at[
            index,
            "株数",
        ]
    )

    entry_amount = safe_float(
        trades.at[
            index,
            "投資額",
        ]
    )

    exit_amount = round(
        exit_price
        * quantity,
        2,
    )

    commission = round(
        exit_amount
        * COMMISSION_RATE,
        2,
    )

    exit_amount -= commission

    profit_loss = round(
        exit_amount
        - entry_amount,
        2,
    )

    return_rate = (
        profit_loss
        / entry_amount
        * 100
        if entry_amount > 0
        else 0.0
    )

    entry_datetime = pd.to_datetime(
        trades.at[
            index,
            "エントリー日時",
        ],
        errors="coerce",
    )

    exit_datetime = pd.Timestamp(
        event["日時"]
    )

    holding_time = ""

    if pd.notna(entry_datetime):
        holding_delta = (
            exit_datetime
            - entry_datetime
        )

        holding_time = str(
            holding_delta
        )

    trades.at[
        index,
        "決済日時",
    ] = exit_datetime.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    trades.at[
        index,
        "決済価格",
    ] = exit_price

    trades.at[
        index,
        "決済理由",
    ] = close_reason

    trades.at[
        index,
        "状態",
    ] = close_reason

    trades.at[
        index,
        "損益額",
    ] = profit_loss

    trades.at[
        index,
        "損益率%",
    ] = round(
        return_rate,
        4,
    )

    trades.at[
        index,
        "保有時間",
    ] = holding_time

    trades.at[
        index,
        "最終更新日時",
    ] = now_text()

    print(
        f"仮想決済: "
        f"{trades.at[index, '銘柄']} "
        f"{ticker} "
        f"{close_reason} "
        f"{profit_loss:+,.2f}円 "
        f"({return_rate:+.2f}%)"
    )

    return trades


def process_events(
    trades: pd.DataFrame,
    events: pd.DataFrame,
    watchlist: pd.DataFrame,
) -> pd.DataFrame:
    if events.empty:
        return trades

    for _, event in events.iterrows():
        ticker = str(
            event["ticker"]
        )

        event_type = str(
            event["イベント"]
        ).upper()

        event_datetime = pd.Timestamp(
            event["日時"]
        )

        if event_already_processed(
            trades=trades,
            ticker=ticker,
            event_type=event_type,
            event_datetime=event_datetime,
        ):
            continue

        watch_row = find_watchlist_row(
            watchlist=watchlist,
            ticker=ticker,
        )

        if watch_row is None:
            continue

        if event_type == "ENTRY":
            trades = open_trade(
                trades=trades,
                event=event,
                watch_row=watch_row,
            )

        elif event_type == "TARGET":
            trades = close_trade(
                trades=trades,
                event=event,
                close_reason=TARGET_STATUS,
            )

        elif event_type == "STOP":
            trades = close_trade(
                trades=trades,
                event=event,
                close_reason=STOP_STATUS,
            )

    return trades


def update_open_positions(
    trades: pd.DataFrame,
    state: pd.DataFrame,
) -> pd.DataFrame:
    if trades.empty or state.empty:
        return trades

    if "ticker" not in state.columns:
        return trades

    state = (
        state.drop_duplicates(
            subset=["ticker"],
            keep="last",
        )
        .set_index("ticker")
    )

    for index, trade in trades.iterrows():
        if trade["状態"] != OPEN_STATUS:
            continue

        ticker = str(
            trade["ticker"]
        )

        if ticker not in state.index:
            continue

        latest_price = safe_float(
            state.at[
                ticker,
                "最新価格",
            ]
            if "最新価格"
            in state.columns
            else 0
        )

        if latest_price <= 0:
            continue

        entry_price = safe_float(
            trade["エントリー価格"]
        )

        highest_price = max(
            safe_float(
                trade["最高価格"],
                entry_price,
            ),
            latest_price,
        )

        minimum_price = safe_float(
            trade["最低価格"],
            entry_price,
        )

        if minimum_price <= 0:
            minimum_price = entry_price

        lowest_price = min(
            minimum_price,
            latest_price,
        )

        unrealized_profit_rate = (
            (
                latest_price
                - entry_price
            )
            / entry_price
            * 100
            if entry_price > 0
            else 0.0
        )

        max_profit_rate = (
            (
                highest_price
                - entry_price
            )
            / entry_price
            * 100
            if entry_price > 0
            else 0.0
        )

        max_loss_rate = (
            (
                lowest_price
                - entry_price
            )
            / entry_price
            * 100
            if entry_price > 0
            else 0.0
        )

        quantity = safe_int(
            trade["株数"]
        )

        unrealized_profit = round(
            (
                latest_price
                - entry_price
            )
            * quantity,
            2,
        )

        trades.at[
            index,
            "最高価格",
        ] = round(
            highest_price,
            2,
        )

        trades.at[
            index,
            "最低価格",
        ] = round(
            lowest_price,
            2,
        )

        trades.at[
            index,
            "最大含み益率%",
        ] = round(
            max_profit_rate,
            4,
        )

        trades.at[
            index,
            "最大含み損率%",
        ] = round(
            max_loss_rate,
            4,
        )

        trades.at[
            index,
            "損益額",
        ] = unrealized_profit

        trades.at[
            index,
            "損益率%",
        ] = round(
            unrealized_profit_rate,
            4,
        )

        trades.at[
            index,
            "最終更新日時",
        ] = now_text()

    return trades


def save_trades(
    trades: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    trades.to_csv(
        TRADES_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def calculate_max_drawdown(
    closed_trades: pd.DataFrame,
) -> float:
    if closed_trades.empty:
        return 0.0

    profit_series = pd.to_numeric(
        closed_trades["損益額"],
        errors="coerce",
    ).fillna(0.0)

    equity_curve = (
        INITIAL_CAPITAL
        + profit_series.cumsum()
    )

    running_max = equity_curve.cummax()

    drawdown = (
        (
            equity_curve
            - running_max
        )
        / running_max
        * 100
    )

    return safe_float(
        drawdown.min()
    )


def calculate_summary(
    trades: pd.DataFrame,
) -> pd.DataFrame:
    closed = trades[
        trades["状態"].isin(
            CLOSED_STATUSES
        )
    ].copy()

    open_trades = trades[
        trades["状態"]
        == OPEN_STATUS
    ].copy()

    closed["損益額"] = pd.to_numeric(
        closed["損益額"],
        errors="coerce",
    ).fillna(0.0)

    closed["損益率%"] = pd.to_numeric(
        closed["損益率%"],
        errors="coerce",
    ).fillna(0.0)

    wins = closed[
        closed["損益額"] > 0
    ]

    losses = closed[
        closed["損益額"] < 0
    ]

    breakeven = closed[
        closed["損益額"] == 0
    ]

    closed_count = len(
        closed
    )

    win_rate = (
        len(wins)
        / closed_count
        * 100
        if closed_count > 0
        else 0.0
    )

    total_profit = safe_float(
        wins["損益額"].sum()
        if not wins.empty
        else 0.0
    )

    total_loss = abs(
        safe_float(
            losses["損益額"].sum()
            if not losses.empty
            else 0.0
        )
    )

    if total_loss > 0:
        profit_factor = (
            total_profit
            / total_loss
        )

    elif total_profit > 0:
        profit_factor = 99.0

    else:
        profit_factor = 0.0

    realized_profit = safe_float(
        closed["損益額"].sum()
        if not closed.empty
        else 0.0
    )

    unrealized_profit = safe_float(
        open_trades["損益額"].sum()
        if not open_trades.empty
        else 0.0
    )

    current_equity = (
        INITIAL_CAPITAL
        + realized_profit
        + unrealized_profit
    )

    summary = {
        "集計日時": now_text(),
        "初期資金": INITIAL_CAPITAL,
        "全取引数": len(trades),
        "保有中": len(open_trades),
        "決済済み": closed_count,
        "勝ち": len(wins),
        "負け": len(losses),
        "引き分け": len(breakeven),
        "勝率%": round(
            win_rate,
            2,
        ),
        "実現損益": round(
            realized_profit,
            2,
        ),
        "含み損益": round(
            unrealized_profit,
            2,
        ),
        "総損益": round(
            realized_profit
            + unrealized_profit,
            2,
        ),
        "現在資産": round(
            current_equity,
            2,
        ),
        "資産増減率%": round(
            (
                current_equity
                / INITIAL_CAPITAL
                - 1
            )
            * 100,
            4,
        ),
        "平均損益率%": round(
            safe_float(
                closed["損益率%"].mean()
                if not closed.empty
                else 0.0
            ),
            4,
        ),
        "平均利益率%": round(
            safe_float(
                wins["損益率%"].mean()
                if not wins.empty
                else 0.0
            ),
            4,
        ),
        "平均損失率%": round(
            safe_float(
                losses["損益率%"].mean()
                if not losses.empty
                else 0.0
            ),
            4,
        ),
        "最大利益率%": round(
            safe_float(
                closed["損益率%"].max()
                if not closed.empty
                else 0.0
            ),
            4,
        ),
        "最大損失率%": round(
            safe_float(
                closed["損益率%"].min()
                if not closed.empty
                else 0.0
            ),
            4,
        ),
        "プロフィットファクター": round(
            profit_factor,
            3,
        ),
        "最大ドローダウン%": round(
            calculate_max_drawdown(
                closed
            ),
            4,
        ),
    }

    return pd.DataFrame(
        [summary]
    )


def save_summary(
    summary: pd.DataFrame,
) -> None:
    summary.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def create_learning_data(
    trades: pd.DataFrame,
) -> pd.DataFrame:
    closed = trades[
        trades["状態"].isin(
            CLOSED_STATUSES
        )
    ].copy()

    if closed.empty:
        return pd.DataFrame(
            columns=[
                "ticker",
                "銘柄",
                "AI判断",
                "AI判断点",
                "PHOENIX_SCORE",
                "RSI",
                "MACD判定",
                "エントリー価格",
                "決済価格",
                "損益率%",
                "結果",
                "決済理由",
                "エントリー日時",
                "決済日時",
            ]
        )

    closed["結果"] = closed[
        "損益率%"
    ].apply(
        lambda value:
            (
                "WIN"
                if safe_float(value) > 0
                else (
                    "LOSS"
                    if safe_float(value) < 0
                    else "DRAW"
                )
            )
    )

    learning_columns = [
        "ticker",
        "銘柄",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
        "MACD判定",
        "エントリー価格",
        "決済価格",
        "損益率%",
        "結果",
        "決済理由",
        "エントリー日時",
        "決済日時",
    ]

    return closed[
        learning_columns
    ].copy()


def save_learning_data(
    learning_data: pd.DataFrame,
) -> None:
    learning_data.to_csv(
        LEARNING_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def create_text_report(
    trades: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    summary_row = summary.iloc[0]

    with open(
        TEXT_REPORT_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            "PHOENIX PAPER TRADING REPORT\n"
        )

        file.write(
            now_text()
            + "\n"
        )

        file.write(
            "=" * 80
            + "\n"
        )

        file.write(
            f"初期資金: "
            f"{summary_row['初期資金']:,.0f}円\n"
        )

        file.write(
            f"現在資産: "
            f"{summary_row['現在資産']:,.0f}円\n"
        )

        file.write(
            f"総損益: "
            f"{summary_row['総損益']:+,.0f}円\n"
        )

        file.write(
            f"勝率: "
            f"{summary_row['勝率%']:.2f}%\n"
        )

        file.write(
            f"PF: "
            f"{summary_row['プロフィットファクター']:.3f}\n"
        )

        file.write(
            f"最大DD: "
            f"{summary_row['最大ドローダウン%']:.2f}%\n"
        )

        file.write(
            "\n"
        )

        if trades.empty:
            file.write(
                "取引はありません。\n"
            )

            return

        file.write(
            trades.to_string(
                index=False
            )
        )

        file.write(
            "\n"
        )


def print_result(
    trades: pd.DataFrame,
    summary: pd.DataFrame,
) -> None:
    print()
    print("=" * 100)
    print("PHOENIX PAPER TRADER")
    print("=" * 100)

    summary_row = summary.iloc[0]

    print(
        f"初期資金     : "
        f"{summary_row['初期資金']:,.0f}円"
    )

    print(
        f"現在資産     : "
        f"{summary_row['現在資産']:,.0f}円"
    )

    print(
        f"総損益       : "
        f"{summary_row['総損益']:+,.0f}円"
    )

    print(
        f"保有中       : "
        f"{summary_row['保有中']}件"
    )

    print(
        f"決済済み     : "
        f"{summary_row['決済済み']}件"
    )

    print(
        f"勝率         : "
        f"{summary_row['勝率%']:.2f}%"
    )

    print(
        f"平均損益率   : "
        f"{summary_row['平均損益率%']:+.4f}%"
    )

    print(
        f"PF           : "
        f"{summary_row['プロフィットファクター']:.3f}"
    )

    print(
        f"最大DD       : "
        f"{summary_row['最大ドローダウン%']:.4f}%"
    )

    print()
    print("=" * 100)
    print("取引一覧")
    print("=" * 100)

    if trades.empty:
        print(
            "取引はありません。"
        )

    else:
        display_columns = [
            "銘柄",
            "ticker",
            "状態",
            "エントリー価格",
            "決済価格",
            "株数",
            "損益額",
            "損益率%",
            "決済理由",
        ]

        print(
            trades[
                display_columns
            ].to_string(
                index=False
            )
        )

    print()
    print(
        f"保存完了 : {TRADES_FILE}"
    )

    print(
        f"保存完了 : {SUMMARY_FILE}"
    )

    print(
        f"保存完了 : {LEARNING_FILE}"
    )

    print(
        f"保存完了 : {TEXT_REPORT_FILE}"
    )


def main() -> None:
    configure_console()

    print("=" * 100)
    print("PHOENIX PAPER TRADING ENGINE")
    print("=" * 100)

    try:
        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        watchlist = load_watchlist()
        events = load_events()
        state = load_state()
        trades = load_trades()

        print(
            f"監視連携モード : {ACTIVE_MONITOR_MODE}"
        )

        print(
            f"状態ファイル : {STATE_FILE}"
        )

        print(
            f"イベント履歴 : {EVENT_FILE}"
        )

        print(
            f"監視銘柄数 : {len(watchlist)}"
        )

        print(
            f"価格イベント数 : {len(events)}"
        )

        print(
            f"既存仮想取引数 : {len(trades)}"
        )

        trades = process_events(
            trades=trades,
            events=events,
            watchlist=watchlist,
        )

        trades = update_open_positions(
            trades=trades,
            state=state,
        )

        save_trades(
            trades
        )

        summary = calculate_summary(
            trades
        )

        save_summary(
            summary
        )

        learning_data = create_learning_data(
            trades
        )

        save_learning_data(
            learning_data
        )

        create_text_report(
            trades=trades,
            summary=summary,
        )

        print_result(
            trades=trades,
            summary=summary,
        )

    except Exception as error:
        print(
            f"エラー: {error}"
        )

        raise SystemExit(
            1
        )


if __name__ == "__main__":
    main()