# modules/trade_engine.py

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import math
import sys
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


# =========================================================
# パス設定
# =========================================================

MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT_DIR),
    )

from notify import (  # noqa: E402
    load_environment,
    send_discord,
    send_line,
)


# =========================================================
# 基本設定
# =========================================================

JST = ZoneInfo("Asia/Tokyo")

REPORT_DIR = ROOT_DIR / "reports"

LIVE_EVENT_FILE = (
    REPORT_DIR
    / "price_alert_history.csv"
)

DRY_EVENT_FILE = (
    REPORT_DIR
    / "price_alert_dry_run.csv"
)

TRADE_ENGINE_LOG_FILE = (
    REPORT_DIR
    / "trade_engine.log"
)

EVENT_ENTRY = "ENTRY"
EVENT_TARGET = "TARGET"
EVENT_STOP = "STOP"

VALID_EVENTS = {
    EVENT_ENTRY,
    EVENT_TARGET,
    EVENT_STOP,
}


# =========================================================
# 売買シグナル
# =========================================================

@dataclass(frozen=True)
class TradeSignal:
    ticker: str
    name: str
    event: str
    price: float

    previous_price: float = 0.0
    quote_time: str = ""

    rank: int = 0
    ranking_score: float = 0.0
    monitor_type: str = ""

    ai_judgement: str = ""
    ai_score: int = 0
    phoenix_score: int = 0

    expected_win_rate: float = 0.0
    expected_return: float = 0.0

    entry_price: float = 0.0
    target_price: float = 0.0
    stop_price: float = 0.0

    risk: str = ""
    rsi: float = 0.0
    macd: str = ""

    source: str = "price_monitor"


@dataclass(frozen=True)
class TradeExecutionResult:
    success: bool
    duplicate: bool
    event_id: str
    event: str
    ticker: str
    notification_success: bool
    notification_result: str
    event_file: str
    message: str


# =========================================================
# 共通処理
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
    return datetime.now(
        JST,
    )


def timestamp_text() -> str:
    return now_jst().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def today_text() -> str:
    return now_jst().strftime(
        "%Y-%m-%d"
    )


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if pd.isna(
            value,
        ):
            return default

        result = float(
            value,
        )

        if not math.isfinite(
            result,
        ):
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
        TRADE_ENGINE_LOG_FILE,
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            text + "\n"
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


def event_file_for_mode(
    live: bool,
) -> Path:
    if live:
        return LIVE_EVENT_FILE

    return DRY_EVENT_FILE


def create_event_id(
    signal: TradeSignal,
) -> str:
    event_time = now_jst().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    ticker_text = (
        signal.ticker
        .replace(
            ".",
            "_",
        )
        .replace(
            "/",
            "_",
        )
        .replace(
            "\\",
            "_",
        )
    )

    return (
        f"{event_time}_"
        f"{ticker_text}_"
        f"{signal.event}"
    )


# =========================================================
# 入力検証
# =========================================================

def normalize_signal(
    signal: TradeSignal,
) -> TradeSignal:
    event = str(
        signal.event,
    ).strip().upper()

    ticker = str(
        signal.ticker,
    ).strip()

    name = str(
        signal.name,
    ).strip()

    quote_time = str(
        signal.quote_time,
    ).strip()

    if not quote_time:
        quote_time = timestamp_text()

    return TradeSignal(
        ticker=ticker,
        name=name,
        event=event,
        price=safe_float(
            signal.price,
        ),
        previous_price=safe_float(
            signal.previous_price,
        ),
        quote_time=quote_time,
        rank=max(
            safe_int(
                signal.rank,
            ),
            0,
        ),
        ranking_score=safe_float(
            signal.ranking_score,
        ),
        monitor_type=str(
            signal.monitor_type,
        ).strip(),
        ai_judgement=str(
            signal.ai_judgement,
        ).strip(),
        ai_score=safe_int(
            signal.ai_score,
        ),
        phoenix_score=safe_int(
            signal.phoenix_score,
        ),
        expected_win_rate=safe_float(
            signal.expected_win_rate,
        ),
        expected_return=safe_float(
            signal.expected_return,
        ),
        entry_price=safe_float(
            signal.entry_price,
        ),
        target_price=safe_float(
            signal.target_price,
        ),
        stop_price=safe_float(
            signal.stop_price,
        ),
        risk=str(
            signal.risk,
        ).strip(),
        rsi=safe_float(
            signal.rsi,
        ),
        macd=str(
            signal.macd,
        ).strip(),
        source=str(
            signal.source,
        ).strip()
        or "price_monitor",
    )


def validate_signal(
    signal: TradeSignal,
) -> None:
    if signal.event not in VALID_EVENTS:
        raise ValueError(
            "不正なイベントです: "
            f"{signal.event}"
        )

    if not signal.ticker:
        raise ValueError(
            "tickerが空です。"
        )

    if not signal.name:
        raise ValueError(
            "銘柄名が空です。"
        )

    if signal.price <= 0:
        raise ValueError(
            "現在価格が不正です: "
            f"{signal.price}"
        )

    if (
        signal.previous_price < 0
        or signal.entry_price < 0
        or signal.target_price < 0
        or signal.stop_price < 0
    ):
        raise ValueError(
            "価格に負の値が含まれています。"
        )

    if signal.event == EVENT_ENTRY:
        if signal.entry_price <= 0:
            raise ValueError(
                "ENTRYには押し目価格が必要です。"
            )

    if signal.event == EVENT_TARGET:
        if signal.target_price <= 0:
            raise ValueError(
                "TARGETには利確価格が必要です。"
            )

    if signal.event == EVENT_STOP:
        if signal.stop_price <= 0:
            raise ValueError(
                "STOPには損切価格が必要です。"
            )


# =========================================================
# 重複防止
# =========================================================

def event_already_exists(
    event_file: Path,
    signal: TradeSignal,
) -> bool:
    if not event_file.exists():
        return False

    try:
        history = read_csv_safe(
            event_file,
        )

    except Exception as error:
        write_log(
            f"イベント履歴読込失敗: {error}"
        )

        return False

    required_columns = {
        "監視日",
        "ticker",
        "イベント",
    }

    if not required_columns.issubset(
        history.columns,
    ):
        return False

    matches = history[
        (
            history["監視日"]
            .astype(str)
            == today_text()
        )
        & (
            history["ticker"]
            .astype(str)
            == signal.ticker
        )
        & (
            history["イベント"]
            .astype(str)
            .str.upper()
            == signal.event
        )
    ]

    return not matches.empty


# =========================================================
# 通知文
# =========================================================

def event_title(
    event: str,
) -> str:
    if event == EVENT_ENTRY:
        return (
            "🟢 PHOENIX PAPER BUY SIGNAL"
        )

    if event == EVENT_TARGET:
        return (
            "🎯 PHOENIX PAPER TARGET SIGNAL"
        )

    return (
        "🔴 PHOENIX PAPER STOP SIGNAL"
    )


def event_description(
    signal: TradeSignal,
) -> str:
    if signal.event == EVENT_ENTRY:
        return (
            f"押し目価格 "
            f"{signal.entry_price:,.2f}円へ到達"
        )

    if signal.event == EVENT_TARGET:
        return (
            f"利確価格 "
            f"{signal.target_price:,.2f}円へ到達"
        )

    return (
        f"損切価格 "
        f"{signal.stop_price:,.2f}円へ到達"
    )


def create_notification_message(
    signal: TradeSignal,
) -> str:
    rank_text = (
        f"{signal.rank}位"
        if signal.rank > 0
        else "順位なし"
    )

    return (
        f"{event_title(signal.event)}\n"
        f"{timestamp_text()}\n"
        f"\n"
        f"ランキング: {rank_text}\n"
        f"{signal.name} ({signal.ticker})\n"
        f"{event_description(signal)}\n"
        f"\n"
        f"前回価格: "
        f"{signal.previous_price:,.2f}円\n"
        f"現在価格: "
        f"{signal.price:,.2f}円\n"
        f"株価時刻: "
        f"{signal.quote_time}\n"
        f"\n"
        f"ランキング点: "
        f"{signal.ranking_score:.4f}点\n"
        f"監視区分: "
        f"{signal.monitor_type}\n"
        f"AI判断: "
        f"{signal.ai_judgement}\n"
        f"AI判断点: "
        f"{signal.ai_score}点\n"
        f"PHOENIX SCORE: "
        f"{signal.phoenix_score}点\n"
        f"期待勝率: "
        f"{signal.expected_win_rate:.2f}%\n"
        f"期待騰落率: "
        f"{signal.expected_return:+.4f}%\n"
        f"リスク: "
        f"{signal.risk}\n"
        f"RSI: "
        f"{signal.rsi:.2f}\n"
        f"MACD: "
        f"{signal.macd}\n"
        f"\n"
        f"押し目価格: "
        f"{signal.entry_price:,.2f}円\n"
        f"利確価格: "
        f"{signal.target_price:,.2f}円\n"
        f"損切価格: "
        f"{signal.stop_price:,.2f}円\n"
        f"\n"
        f"実行モード: PaperTrade\n"
        f"※実口座への注文は行いません。"
    )


# =========================================================
# 外部通知
# =========================================================

def send_notifications(
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

    load_environment()

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
            message,
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
            message,
        )

    except Exception as error:
        line_result = (
            f"LINEエラー: {error}"
        )

    success = (
        discord_success
        or line_success
    )

    result = (
        f"{discord_result} / "
        f"{line_result}"
    )

    return (
        success,
        result,
    )


# =========================================================
# イベント保存
# =========================================================

def signal_to_event_row(
    signal: TradeSignal,
    event_id: str,
    live: bool,
    notification_success: bool,
    notification_result: str,
) -> dict[str, Any]:
    return {
        "イベントID": event_id,
        "監視日": today_text(),
        "日時": timestamp_text(),
        "イベント": signal.event,
        "順位": signal.rank,
        "銘柄": signal.name,
        "ticker": signal.ticker,
        "ランキング点": round(
            signal.ranking_score,
            4,
        ),
        "監視区分": signal.monitor_type,
        "AI判断": signal.ai_judgement,
        "AI判断点": signal.ai_score,
        "PHOENIX_SCORE": (
            signal.phoenix_score
        ),
        "期待勝率%": round(
            signal.expected_win_rate,
            2,
        ),
        "期待騰落率%": round(
            signal.expected_return,
            4,
        ),
        "リスク": signal.risk,
        "RSI": round(
            signal.rsi,
            2,
        ),
        "MACD判定": signal.macd,
        "前回価格": round(
            signal.previous_price,
            2,
        ),
        "現在価格": round(
            signal.price,
            2,
        ),
        "押し目価格": round(
            signal.entry_price,
            2,
        ),
        "利確価格": round(
            signal.target_price,
            2,
        ),
        "損切価格": round(
            signal.stop_price,
            2,
        ),
        "株価時刻": signal.quote_time,
        "実通知": live,
        "通知成功": (
            notification_success
        ),
        "通知結果": (
            notification_result
        ),
        "通知更新日時": timestamp_text(),
        "発生元": signal.source,
        "実行モード": "PAPER",
    }


def append_event(
    event_file: Path,
    event_row: dict[str, Any],
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    row_df = pd.DataFrame([
        event_row
    ])

    file_exists = event_file.exists()

    row_df.to_csv(
        event_file,
        mode="a",
        header=not file_exists,
        index=False,
        encoding="utf-8-sig",
    )


# =========================================================
# 売買エンジン
# =========================================================

def execute_signal(
    signal: TradeSignal,
    live: bool = False,
) -> TradeExecutionResult:
    normalized_signal = normalize_signal(
        signal,
    )

    validate_signal(
        normalized_signal,
    )

    event_file = event_file_for_mode(
        live,
    )

    if event_already_exists(
        event_file,
        normalized_signal,
    ):
        duplicate_message = (
            f"重複イベントを停止: "
            f"{normalized_signal.ticker} "
            f"{normalized_signal.event}"
        )

        write_log(
            duplicate_message,
        )

        return TradeExecutionResult(
            success=True,
            duplicate=True,
            event_id="",
            event=normalized_signal.event,
            ticker=normalized_signal.ticker,
            notification_success=True,
            notification_result=(
                "同一日・同一銘柄・"
                "同一イベント処理済み"
            ),
            event_file=str(
                event_file,
            ),
            message=duplicate_message,
        )

    event_id = create_event_id(
        normalized_signal,
    )

    notification_message = (
        create_notification_message(
            normalized_signal,
        )
    )

    (
        notification_success,
        notification_result,
    ) = send_notifications(
        message=notification_message,
        live=live,
    )

    event_row = signal_to_event_row(
        signal=normalized_signal,
        event_id=event_id,
        live=live,
        notification_success=(
            notification_success
        ),
        notification_result=(
            notification_result
        ),
    )

    append_event(
        event_file=event_file,
        event_row=event_row,
    )

    status_text = (
        "SUCCESS"
        if notification_success
        else "NOTIFICATION FAILED"
    )

    log_message = (
        f"{status_text}: "
        f"{normalized_signal.event} "
        f"{normalized_signal.ticker} "
        f"{normalized_signal.previous_price:.2f}"
        f" -> "
        f"{normalized_signal.price:.2f} "
        f"{notification_result}"
    )

    write_log(
        log_message,
    )

    return TradeExecutionResult(
        success=True,
        duplicate=False,
        event_id=event_id,
        event=normalized_signal.event,
        ticker=normalized_signal.ticker,
        notification_success=(
            notification_success
        ),
        notification_result=(
            notification_result
        ),
        event_file=str(
            event_file,
        ),
        message=notification_message,
    )


def buy_signal(
    signal: TradeSignal,
    live: bool = False,
) -> TradeExecutionResult:
    normalized = normalize_signal(
        signal,
    )

    normalized = TradeSignal(
        **{
            **asdict(
                normalized,
            ),
            "event": EVENT_ENTRY,
        }
    )

    return execute_signal(
        signal=normalized,
        live=live,
    )


def target_signal(
    signal: TradeSignal,
    live: bool = False,
) -> TradeExecutionResult:
    normalized = normalize_signal(
        signal,
    )

    normalized = TradeSignal(
        **{
            **asdict(
                normalized,
            ),
            "event": EVENT_TARGET,
        }
    )

    return execute_signal(
        signal=normalized,
        live=live,
    )


def stop_signal(
    signal: TradeSignal,
    live: bool = False,
) -> TradeExecutionResult:
    normalized = normalize_signal(
        signal,
    )

    normalized = TradeSignal(
        **{
            **asdict(
                normalized,
            ),
            "event": EVENT_STOP,
        }
    )

    return execute_signal(
        signal=normalized,
        live=live,
    )


# =========================================================
# 単体テスト
# =========================================================

def run_self_test() -> None:
    test_signal = TradeSignal(
        ticker="TEST.T",
        name="PHOENIXテスト銘柄",
        event=EVENT_ENTRY,
        price=1000.0,
        previous_price=1010.0,
        quote_time=timestamp_text(),
        rank=1,
        ranking_score=80.0,
        monitor_type="買い監視",
        ai_judgement="買い候補",
        ai_score=80,
        phoenix_score=75,
        expected_win_rate=55.0,
        expected_return=0.5,
        entry_price=1000.0,
        target_price=1050.0,
        stop_price=970.0,
        risk="低",
        rsi=55.0,
        macd="BUY",
        source="trade_engine_self_test",
    )

    result = buy_signal(
        signal=test_signal,
        live=False,
    )

    print("=" * 90)
    print("PHOENIX TRADE ENGINE SELF TEST")
    print("=" * 90)
    print(
        f"success              : "
        f"{result.success}"
    )
    print(
        f"duplicate            : "
        f"{result.duplicate}"
    )
    print(
        f"event_id             : "
        f"{result.event_id}"
    )
    print(
        f"event                : "
        f"{result.event}"
    )
    print(
        f"ticker               : "
        f"{result.ticker}"
    )
    print(
        f"notification_success : "
        f"{result.notification_success}"
    )
    print(
        f"notification_result  : "
        f"{result.notification_result}"
    )
    print(
        f"event_file           : "
        f"{result.event_file}"
    )


def main() -> None:
    configure_console()

    run_self_test()


if __name__ == "__main__":
    main()