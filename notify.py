# notify.py

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import os
import sys
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from phoenix_core.data_freshness import (
    EXPECTED_NIKKEI225_COUNT,
    JST,
    ticker_universe_sha256,
    verify_market_dates,
)


# =========================================================
# パス・設定
# =========================================================

REPORT_DIR = Path("reports")

AI_JUDGEMENT_FILE = (
    REPORT_DIR
    / "ai_judgement.csv"
)
AI_JUDGEMENT_MANIFEST_NAME = "ai_judgement_manifest.json"
OPTIMIZED_SIGNALS_FILE = REPORT_DIR / "optimized_signals.csv"
LEARNING_PROFILE_FILE = REPORT_DIR / "learning_profile.json"

ADAPTIVE_PARAMETER_FILE = REPORT_DIR / "adaptive_parameter.json"

NOTIFICATION_LOG_FILE = (
    REPORT_DIR
    / "notification_log.txt"
)

ENV_FILE = Path(".env")

REQUEST_TIMEOUT = 30
NOTIFICATION_SOURCE_MANIFEST_NAME = "notification_source_manifest.json"
MAX_NOTIFICATION_SOURCE_AGE = timedelta(hours=4)

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

def _load_notification_source_dates(
    *,
    as_of: datetime | None = None,
) -> pd.DataFrame:
    checked_at = as_of or datetime.now(JST)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=JST)
    else:
        checked_at = checked_at.astimezone(JST)
    report_file = REPORT_DIR / f"report_{checked_at:%Y%m%d}.csv"
    if not report_file.is_file():
        raise FileNotFoundError(
            f"Today's source report is missing; stale notification is blocked: {report_file}"
        )

    manifest_file = REPORT_DIR / NOTIFICATION_SOURCE_MANIFEST_NAME
    if not manifest_file.is_file():
        raise FileNotFoundError(
            f"Notification source manifest is missing; notification is blocked: {manifest_file}"
        )
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("Notification source manifest is unreadable") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Notification source manifest schema is invalid")
    if manifest.get("report_file") != report_file.name:
        raise ValueError("Notification source manifest points to a different report")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("Notification source manifest run_id is missing")
    try:
        generated_at = datetime.fromisoformat(str(manifest.get("generated_at", "")))
    except ValueError as error:
        raise ValueError("Notification source manifest generated_at is invalid") from error
    if generated_at.tzinfo is None:
        raise ValueError("Notification source manifest generated_at must include a timezone")
    generated_at = generated_at.astimezone(JST)
    age = checked_at - generated_at
    if age < timedelta(0) or age > MAX_NOTIFICATION_SOURCE_AGE:
        raise ValueError(
            "Notification source manifest is not from the current pipeline run: "
            f"age_seconds={age.total_seconds():.0f}"
        )
    actual_sha256 = sha256(report_file.read_bytes()).hexdigest()
    if manifest.get("report_sha256") != actual_sha256:
        raise ValueError("Notification source report hash does not match the manifest")

    source = pd.read_csv(report_file)
    required = {"ticker", "基準日"}
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Today's source report lacks freshness columns: {sorted(missing)}")
    source = source[["ticker", "基準日"]]
    if source.empty or source.isna().any().any():
        raise ValueError("Today's source report has missing ticker or market date evidence")
    if source["ticker"].duplicated().any():
        raise ValueError("Today's source report has duplicate ticker evidence")
    evidence = verify_market_dates(
        source["基準日"].tolist(),
        as_of=checked_at,
    )
    if evidence["status"] != "READY":
        raise ValueError(
            "Stale market data notification is blocked: "
            + "; ".join(evidence["blocking_reasons"])
        )
    ticker_count = manifest.get("ticker_count")
    if (
        isinstance(ticker_count, bool)
        or not isinstance(ticker_count, int)
        or ticker_count != int(source["ticker"].nunique())
    ):
        raise ValueError("Notification source manifest ticker_count is inconsistent")
    if (
        manifest.get("expected_ticker_count") != EXPECTED_NIKKEI225_COUNT
        or ticker_count != EXPECTED_NIKKEI225_COUNT
    ):
        raise ValueError(
            "Notification source is not a complete Nikkei 225 universe: "
            f"{ticker_count}/{EXPECTED_NIKKEI225_COUNT}"
        )
    universe_sha256 = ticker_universe_sha256(source["ticker"].tolist())
    if manifest.get("ticker_universe_sha256") != universe_sha256:
        raise ValueError("Notification source ticker universe hash is inconsistent")
    recorded_evidence = manifest.get("market_data_evidence")
    if not isinstance(recorded_evidence, dict):
        raise ValueError("Notification source manifest market evidence is missing")
    for field in (
        "status",
        "expected_date",
        "latest_date",
        "oldest_date",
        "calendar_status",
        "calendar_sha256",
    ):
        if recorded_evidence.get(field) != evidence.get(field):
            raise ValueError(
                f"Notification source manifest market evidence differs: {field}"
            )
    source.attrs["source_manifest"] = manifest
    return source


def load_ai_judgement(*, as_of: datetime | None = None) -> pd.DataFrame:
    if not AI_JUDGEMENT_FILE.exists():
        raise FileNotFoundError(
            "AI判断ファイルがありません: "
            f"{AI_JUDGEMENT_FILE}"
        )

    checked_at = as_of or datetime.now(JST)
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=JST)
    else:
        checked_at = checked_at.astimezone(JST)
    source_dates = _load_notification_source_dates(as_of=checked_at)
    source_manifest = source_dates.attrs.get("source_manifest", {})
    ai_manifest_file = REPORT_DIR / AI_JUDGEMENT_MANIFEST_NAME
    if not ai_manifest_file.is_file():
        raise FileNotFoundError(
            f"AI judgement manifest is missing; notification is blocked: {ai_manifest_file}"
        )
    try:
        ai_manifest = json.loads(ai_manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("AI judgement manifest is unreadable") from error
    if not isinstance(ai_manifest, dict) or ai_manifest.get("schema_version") != 1:
        raise ValueError("AI judgement manifest schema is invalid")
    if (
        ai_manifest.get("run_id") != source_manifest.get("run_id")
        or ai_manifest.get("input_report_file") != source_manifest.get("report_file")
        or ai_manifest.get("input_report_sha256") != source_manifest.get("report_sha256")
    ):
        raise ValueError("AI judgement is not derived from the current source run")
    if ai_manifest.get("ai_judgement_file") != AI_JUDGEMENT_FILE.name:
        raise ValueError("AI judgement manifest points to a different output")
    if ai_manifest.get("ai_judgement_sha256") != sha256(
        AI_JUDGEMENT_FILE.read_bytes()
    ).hexdigest():
        raise ValueError("AI judgement file hash does not match its manifest")
    try:
        ai_generated_at = datetime.fromisoformat(str(ai_manifest.get("generated_at", "")))
        source_generated_at = datetime.fromisoformat(
            str(source_manifest.get("generated_at", ""))
        )
    except ValueError as error:
        raise ValueError("AI judgement lineage timestamp is invalid") from error
    if ai_generated_at.tzinfo is None or source_generated_at.tzinfo is None:
        raise ValueError("AI judgement lineage timestamps must include timezones")
    ai_generated_at = ai_generated_at.astimezone(JST)
    source_generated_at = source_generated_at.astimezone(JST)
    if not source_generated_at <= ai_generated_at <= checked_at:
        raise ValueError("AI judgement lineage timestamps are out of order")
    if checked_at - ai_generated_at > MAX_NOTIFICATION_SOURCE_AGE:
        raise ValueError("AI judgement is not from the current pipeline run")
    for path, field in (
        (OPTIMIZED_SIGNALS_FILE, "optimized_signals_sha256"),
        (LEARNING_PROFILE_FILE, "learning_profile_sha256"),
    ):
        actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if ai_manifest.get(field) != actual:
            raise ValueError(f"AI judgement input hash differs: {field}")

    df = pd.read_csv(AI_JUDGEMENT_FILE)
    ticker_count = ai_manifest.get("ticker_count")
    if isinstance(ticker_count, bool) or not isinstance(ticker_count, int):
        raise ValueError("AI judgement manifest ticker_count is invalid")
    if ticker_count != len(df):
        raise ValueError("AI judgement manifest ticker_count is inconsistent")

    df = df.merge(source_dates, on="ticker", how="left", validate="many_to_one")
    if df["基準日"].isna().any():
        missing_tickers = sorted(df.loc[df["基準日"].isna(), "ticker"].astype(str).unique())
        raise ValueError(f"Market data date is missing for notification tickers: {missing_tickers}")

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
