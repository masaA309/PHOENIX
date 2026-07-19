# notify.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import sys
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv


# =========================================================
# パス・設定
# =========================================================

REPORT_DIR = Path("reports")

AI_JUDGEMENT_FILE = (
    REPORT_DIR
    / "ai_judgement.csv"
)

ADAPTIVE_PARAMETER_FILE = REPORT_DIR / "adaptive_parameter.json"

NOTIFICATION_LOG_FILE = (
    REPORT_DIR
    / "notification_log.txt"
)

ENV_FILE = Path(".env")

REQUEST_TIMEOUT = 30

DISCORD_MAX_LENGTH = 1900
LINE_MAX_LENGTH = 4500


# =========================================================
# コンソール設定
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


# =========================================================
# 環境変数
# =========================================================

def load_environment() -> None:
    if ENV_FILE.exists():
        load_dotenv(
            dotenv_path=ENV_FILE,
            override=False,
        )
    else:
        load_dotenv(
            override=False,
        )


def get_environment_value(
    name: str,
) -> str:
    return str(
        os.getenv(
            name,
            "",
        )
    ).strip()


# =========================================================
# AI判断CSV読込
# =========================================================

def load_ai_judgement() -> pd.DataFrame:
    if not AI_JUDGEMENT_FILE.exists():
        raise FileNotFoundError(
            "AI判断ファイルがありません: "
            f"{AI_JUDGEMENT_FILE}"
        )

    df = pd.read_csv(
        AI_JUDGEMENT_FILE,
    )

    required_columns = {
        "銘柄",
        "ticker",
        "価格",
        "前日比%",
        "出来高倍率",
        "RSI",
        "MACD判定",
        "PHOENIX_SCORE",
        "AI判断",
        "AI判断点",
        "リスク",
        "監視タイミング",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(
                missing_columns,
            )
        )

        raise ValueError(
            "AI判断ファイルに必要な列がありません: "
            f"{missing_text}"
        )

    numeric_columns = [
        "価格",
        "前日比%",
        "出来高倍率",
        "RSI",
        "PHOENIX_SCORE",
        "AI判断点",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "銘柄",
            "ticker",
            "AI判断",
            "AI判断点",
        ],
    )

    judgement_order = {
        "優先監視": 0,
        "買い候補": 1,
        "押し目待ち": 2,
        "様子見": 3,
        "見送り": 4,
    }

    df["判断順"] = (
        df["AI判断"]
        .map(
            judgement_order,
        )
        .fillna(
            99,
        )
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
        .drop(
            columns=[
                "判断順",
            ]
        )
        .reset_index(
            drop=True,
        )
    )


# =========================================================
# 表示用
# =========================================================

def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if pd.isna(
            value,
        ):
            return default

        return float(
            value,
        )

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
        if pd.isna(
            value,
        ):
            return default

        return int(
            float(
                value,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def format_stock(
    row: pd.Series,
    number: int,
) -> str:
    name = str(
        row["銘柄"]
    )

    ticker = str(
        row["ticker"]
    )

    price = safe_float(
        row["価格"],
    )

    change = safe_float(
        row["前日比%"],
    )

    volume_ratio = safe_float(
        row["出来高倍率"],
    )

    rsi = safe_float(
        row["RSI"],
    )

    phoenix_score = safe_int(
        row["PHOENIX_SCORE"],
    )

    ai_score = safe_int(
        row["AI判断点"],
    )

    risk = str(
        row["リスク"]
    )

    macd = str(
        row["MACD判定"]
    )

    timing = str(
        row["監視タイミング"]
    )

    return (
        f"{number}. {name} ({ticker})\n"
        f"   価格 {price:,.2f}円 "
        f"/ 前日比 {change:+.2f}%\n"
        f"   AI {ai_score}点 "
        f"/ PHOENIX {phoenix_score}点\n"
        f"   出来高 {volume_ratio:.2f}倍 "
        f"/ RSI {rsi:.2f} "
        f"/ MACD {macd}\n"
        f"   リスク {risk}\n"
        f"   {timing}"
    )


def build_group_section(
    title: str,
    target_df: pd.DataFrame,
) -> str:
    lines = [
        f"【{title}】",
    ]

    if target_df.empty:
        lines.append(
            "該当なし"
        )

        return "\n".join(
            lines
        )

    for number, (_, row) in enumerate(
        target_df.iterrows(),
        start=1,
    ):
        lines.append(
            ""
        )

        lines.append(
            format_stock(
                row=row,
                number=number,
            )
        )

    return "\n".join(
        lines
    )


def build_notification_messages(
    df: pd.DataFrame,
) -> list[str]:
    priority_df = df[
        df["AI判断"]
        == "優先監視"
    ]

    buy_df = df[
        df["AI判断"]
        == "買い候補"
    ]

    pullback_df = df[
        df["AI判断"]
        == "押し目待ち"
    ]

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )

    buy_message = "\n".join([
        "🔥 PHOENIX BUY ALERT",
        timestamp,
        "",
        (
            "優先監視 "
            f"{len(priority_df)}銘柄"
            " / 買い候補 "
            f"{len(buy_df)}銘柄"
        ),
        "",
        build_group_section(
            title="優先監視",
            target_df=priority_df,
        ),
        "",
        build_group_section(
            title="買い候補",
            target_df=buy_df,
        ),
        "",
        "※売買推奨ではなく監視候補です。",
        "詳細: reports/ai_judgement.csv",
        "チャート: reports/charts/",
    ])

    pullback_message = "\n".join([
        "📉 PHOENIX PULLBACK ALERT",
        timestamp,
        "",
        (
            "押し目買い候補 "
            f"{len(pullback_df)}銘柄"
        ),
        "",
        build_group_section(
            title="押し目買い候補",
            target_df=pullback_df,
        ),
        "",
        "※現在価格での即時買いではなく、押し目を監視する候補です。",
        "詳細: reports/ai_judgement.csv",
        "チャート: reports/charts/",
    ])

    messages = [buy_message, pullback_message]
    adaptive_message = build_adaptive_message()
    if adaptive_message:
        messages.append(adaptive_message)
    return messages



def build_adaptive_message() -> str:
    if not ADAPTIVE_PARAMETER_FILE.exists():
        return ""
    try:
        import json
        data = json.loads(ADAPTIVE_PARAMETER_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    return "\n".join([
        "🧠 PHOENIX ADAPTIVE PARAMETER",
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        "",
        f"判定: {data.get('decision', 'WAITING')}",
        f"処理: {data.get('action', 'WAITING')}",
        f"信頼度: {safe_float(data.get('confidence', 0)):.2f}%",
        f"理由: {data.get('reason', '')}",
    ])

def split_message(
    message: str,
    maximum_length: int,
) -> list[str]:
    if len(message) <= maximum_length:
        return [message]

    chunks: list[str] = []
    current = ""

    for block in message.split("\n\n"):
        candidate = block if not current else f"{current}\n\n{block}"

        if len(candidate) <= maximum_length:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(block) > maximum_length:
            chunks.append(block[:maximum_length])
            block = block[maximum_length:]

        current = block

    if current:
        chunks.append(current)

    total = len(chunks)

    if total <= 1:
        return chunks

    numbered_chunks: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        prefix = f"({index}/{total})\n"
        numbered_chunks.append(
            prefix + chunk[:maximum_length - len(prefix)]
        )

    return numbered_chunks


# =========================================================
# Discord
# =========================================================

def send_discord(
    message: str,
) -> tuple[bool, str]:
    webhook_url = get_environment_value(
        "DISCORD_WEBHOOK_URL"
    )

    if not webhook_url:
        return (
            False,
            "DISCORD_WEBHOOK_URLが未設定です。",
        )

    discord_message = message[
        :DISCORD_MAX_LENGTH
    ]

    payload = {
        "username": "PHOENIX",
        "content": discord_message,
        "allowed_mentions": {
            "parse": [],
        },
    }

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code in {
            200,
            204,
        }:
            return (
                True,
                "Discord通知成功",
            )

        return (
            False,
            (
                "Discord通知失敗 "
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            ),
        )

    except requests.RequestException as error:
        return (
            False,
            f"Discord通信エラー: {error}",
        )


# =========================================================
# LINE Messaging API
# =========================================================

def build_line_headers(
    access_token: str,
) -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {access_token}"
        ),
        "Content-Type": (
            "application/json"
        ),
    }


def send_line_broadcast(
    message: str,
    access_token: str,
) -> tuple[bool, str]:
    endpoint = (
        "https://api.line.me"
        "/v2/bot/message/broadcast"
    )

    payload = {
        "messages": [
            {
                "type": "text",
                "text": message[
                    :LINE_MAX_LENGTH
                ],
            }
        ],
    }

    try:
        response = requests.post(
            endpoint,
            headers=build_line_headers(
                access_token,
            ),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 200:
            return (
                True,
                "LINE一斉通知成功",
            )

        return (
            False,
            (
                "LINE一斉通知失敗 "
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            ),
        )

    except requests.RequestException as error:
        return (
            False,
            f"LINE通信エラー: {error}",
        )


def send_line_push(
    message: str,
    access_token: str,
    user_id: str,
) -> tuple[bool, str]:
    endpoint = (
        "https://api.line.me"
        "/v2/bot/message/push"
    )

    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message[
                    :LINE_MAX_LENGTH
                ],
            }
        ],
    }

    try:
        response = requests.post(
            endpoint,
            headers=build_line_headers(
                access_token,
            ),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 200:
            return (
                True,
                "LINE個別通知成功",
            )

        return (
            False,
            (
                "LINE個別通知失敗 "
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            ),
        )

    except requests.RequestException as error:
        return (
            False,
            f"LINE通信エラー: {error}",
        )


def send_line(
    message: str,
) -> tuple[bool, str]:
    access_token = get_environment_value(
        "LINE_CHANNEL_ACCESS_TOKEN"
    )

    if not access_token:
        return (
            False,
            "LINE_CHANNEL_ACCESS_TOKENが未設定です。",
        )

    send_mode = (
        get_environment_value(
            "LINE_SEND_MODE"
        )
        .lower()
    )

    if not send_mode:
        send_mode = "broadcast"

    if send_mode == "broadcast":
        return send_line_broadcast(
            message=message,
            access_token=access_token,
        )

    if send_mode == "push":
        user_id = get_environment_value(
            "LINE_USER_ID"
        )

        if not user_id:
            return (
                False,
                (
                    "LINE_SEND_MODE=pushですが、"
                    "LINE_USER_IDが未設定です。"
                ),
            )

        return send_line_push(
            message=message,
            access_token=access_token,
            user_id=user_id,
        )

    return (
        False,
        (
            "LINE_SEND_MODEは"
            "broadcastまたはpushを指定してください。"
        ),
    )


def send_all_discord(
    messages: list[str],
) -> tuple[bool, str]:
    sent_count = 0

    for message in messages:
        for chunk in split_message(
            message=message,
            maximum_length=DISCORD_MAX_LENGTH,
        ):
            success, result = send_discord(
                chunk
            )

            if not success:
                return False, result

            sent_count += 1

    return (
        True,
        f"Discord通知成功: {sent_count}件",
    )


def send_all_line(
    messages: list[str],
) -> tuple[bool, str]:
    sent_count = 0

    for message in messages:
        for chunk in split_message(
            message=message,
            maximum_length=LINE_MAX_LENGTH,
        ):
            success, result = send_line(
                chunk
            )

            if not success:
                return False, result

            sent_count += 1

    return (
        True,
        f"LINE通知成功: {sent_count}件",
    )


# =========================================================
# ログ保存
# =========================================================

def save_notification_log(
    messages: list[str],
    results: list[str],
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        NOTIFICATION_LOG_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as log_file:
        log_file.write(
            "PHOENIX NOTIFICATION LOG\n"
        )

        log_file.write(
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        log_file.write(
            "\n\n"
        )

        for result in results:
            log_file.write(
                result + "\n"
            )

        for number, message in enumerate(
            messages,
            start=1,
        ):
            log_file.write(
                "\n" + "=" * 80 + "\n"
            )
            log_file.write(
                f"NOTIFICATION {number}\n"
            )
            log_file.write(
                "=" * 80 + "\n"
            )
            log_file.write(
                message
            )
            log_file.write(
                "\n"
            )


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()
    load_environment()

    print("=" * 80)
    print("PHOENIX MULTI NOTIFIER")
    print("LINE + Discord")
    print("買い候補通知 / 押し目買い候補通知")
    print("=" * 80)

    try:
        df = load_ai_judgement()

        messages = build_notification_messages(
            df
        )

    except Exception as error:
        print(
            f"通知データ作成エラー: {error}"
        )

        raise SystemExit(
            1
        )

    for number, message in enumerate(
        messages,
        start=1,
    ):
        print()
        print("=" * 80)
        print(f"NOTIFICATION {number}")
        print("=" * 80)
        print(message)

    print()

    discord_success, discord_result = (
        send_all_discord(
            messages
        )
    )

    line_success, line_result = send_all_line(
        messages
    )

    print("=" * 80)
    print("NOTIFICATION RESULT")
    print("=" * 80)

    print(
        discord_result
    )

    print(
        line_result
    )

    results = [
        discord_result,
        line_result,
    ]

    save_notification_log(
        messages=messages,
        results=results,
    )

    print()
    print(
        "通知ログ保存: "
        f"{NOTIFICATION_LOG_FILE}"
    )

    success_count = sum([
        discord_success,
        line_success,
    ])

    print(
        f"通知成功: {success_count}/2"
    )

    if success_count == 0:
        raise SystemExit(
            1
        )

    if success_count == 1:
        print(
            "片方の通知に失敗しました。"
            "成功した通知先への送信は完了しています。"
        )


if __name__ == "__main__":
    main()
