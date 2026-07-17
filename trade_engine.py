# trade_engine.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import sys
from typing import Any

import pandas as pd


# =========================================================
# 基本設定
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"

AI_JUDGEMENT_FILE = REPORT_DIR / "ai_judgement.csv"
MARKET_RISK_FILE = DATA_DIR / "market_risk_latest.json"

WATCHLIST_FILE = REPORT_DIR / "price_watchlist.csv"
TRADE_SIGNAL_FILE = REPORT_DIR / "trade_signals.csv"
TEXT_REPORT_FILE = REPORT_DIR / "trade_engine_report.txt"

MAX_WATCHLIST_COUNT = 30

BUY_MIN_AI_SCORE = 80
WATCH_MIN_AI_SCORE = 65
MIN_PHOENIX_SCORE = 60

DEFAULT_TARGET_RATE = 0.05
DEFAULT_STOP_RATE = 0.03
DEFAULT_PULLBACK_RATE = 0.02

RISK_POSITION_RATIOS = [
    (29, 1.00),
    (49, 0.75),
    (69, 0.50),
    (89, 0.25),
    (100, 0.00),
]

BUY_LABELS = {
    "BUY",
    "買い",
    "買い候補",
    "強い買い",
    "優先監視",
    "エントリー候補",
}

WATCH_LABELS = {
    "WATCH",
    "監視",
    "押し目待ち",
    "様子見",
    "注目",
}

SKIP_LABELS = {
    "SELL",
    "売り",
    "見送り",
    "除外",
    "危険",
}

OUTPUT_COLUMNS = [
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
    "Trade判定",
    "ロット比率",
    "MarketRiskScore",
    "MarketRiskLevel",
    "判定理由",
    "生成日時",
]


# =========================================================
# コンソール
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
# 共通関数
# =========================================================

def now_text() -> str:
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def normalize_text(
    value: Any,
) -> str:
    if pd.isna(value):
        return ""

    return str(value).strip()


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if pd.isna(value):
            return default

        text = (
            str(value)
            .replace(",", "")
            .replace("%", "")
            .strip()
        )

        return float(text)

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


def ensure_directories() -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def load_csv(
    file_path: Path,
) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(
            f"ファイルがありません: {file_path}"
        )

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp932",
    ]

    last_error: Exception | None = None

    for encoding in encodings:
        try:
            return pd.read_csv(
                file_path,
                encoding=encoding,
            )

        except Exception as error:
            last_error = error

    raise RuntimeError(
        f"CSVを読み込めません: {file_path} / {last_error}"
    )


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
    required: bool = False,
) -> str | None:
    normalized_map = {
        str(column).strip().lower(): column
        for column in df.columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()

        if key in normalized_map:
            return normalized_map[key]

    if required:
        raise ValueError(
            "必要な列がありません: "
            + " / ".join(candidates)
        )

    return None


# =========================================================
# Market Risk
# =========================================================

def load_market_risk() -> dict[str, Any]:
    if not MARKET_RISK_FILE.exists():
        print(
            f"Market Riskファイルなし: {MARKET_RISK_FILE}"
        )

        return {
            "score": 50,
            "level": "UNKNOWN",
            "message": "Market Riskファイル未生成",
        }

    try:
        with open(
            MARKET_RISK_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

    except Exception as error:
        print(
            f"Market Risk読込エラー: {error}"
        )

        return {
            "score": 50,
            "level": "UNKNOWN",
            "message": "Market Risk読込失敗",
        }

    score_candidates = [
        "market_risk_score",
        "risk_score",
        "score",
        "MarketRiskScore",
        "市場リスクスコア",
    ]

    level_candidates = [
        "market_risk_level",
        "risk_level",
        "level",
        "MarketRiskLevel",
        "市場リスク",
    ]

    score = 50.0
    level = "UNKNOWN"

    for key in score_candidates:
        if key in data:
            score = safe_float(
                data[key],
                50.0,
            )
            break

    for key in level_candidates:
        if key in data:
            level = normalize_text(
                data[key]
            ).upper()
            break

    score = max(
        0.0,
        min(
            score,
            100.0,
        ),
    )

    if level in {
        "",
        "UNKNOWN",
    }:
        level = risk_level_from_score(
            score
        )

    return {
        "score": score,
        "level": level,
        "message": normalize_text(
            data.get(
                "message",
                "",
            )
        ),
    }


def risk_level_from_score(
    score: float,
) -> str:
    if score <= 29:
        return "LOW"

    if score <= 49:
        return "NORMAL"

    if score <= 69:
        return "HIGH"

    if score <= 89:
        return "VERY_HIGH"

    return "EXTREME"


def position_ratio_from_risk(
    score: float,
) -> float:
    for upper_limit, ratio in RISK_POSITION_RATIOS:
        if score <= upper_limit:
            return ratio

    return 0.0


# =========================================================
# AI判断CSVの標準化
# =========================================================

def standardize_ai_dataframe(
    source_df: pd.DataFrame,
) -> pd.DataFrame:
    if source_df.empty:
        raise ValueError(
            "AI判断CSVが空です。"
        )

    name_col = find_column(
        source_df,
        [
            "銘柄",
            "name",
            "会社名",
            "銘柄名",
        ],
        required=True,
    )

    ticker_col = find_column(
        source_df,
        [
            "ticker",
            "ティッカー",
            "コード",
            "証券コード",
        ],
        required=True,
    )

    ai_label_col = find_column(
        source_df,
        [
            "AI判断",
            "AI判定",
            "判定",
            "signal",
            "action",
        ],
        required=True,
    )

    ai_score_col = find_column(
        source_df,
        [
            "AI判断点",
            "AI_SCORE",
            "AIスコア",
            "ai_score",
            "score",
        ],
    )

    phoenix_score_col = find_column(
        source_df,
        [
            "PHOENIX_SCORE",
            "PHOENIX SCORE",
            "phoenix_score",
            "総合スコア",
        ],
    )

    rsi_col = find_column(
        source_df,
        [
            "RSI",
            "rsi",
            "RSI14",
        ],
    )

    macd_col = find_column(
        source_df,
        [
            "MACD判定",
            "MACD",
            "macd_signal",
        ],
    )

    price_col = find_column(
        source_df,
        [
            "現在価格",
            "価格",
            "終値",
            "close",
            "基準価格",
        ],
        required=True,
    )

    pullback_col = find_column(
        source_df,
        [
            "押し目価格",
            "押し目候補価格",
            "pullback_price",
        ],
    )

    target_col = find_column(
        source_df,
        [
            "利確価格",
            "目標価格",
            "target_price",
        ],
    )

    stop_col = find_column(
        source_df,
        [
            "損切価格",
            "損切り価格",
            "stop_price",
        ],
    )

    change_col = find_column(
        source_df,
        [
            "前日比%",
            "騰落率%",
            "change_pct",
            "上昇率",
        ],
    )

    volume_ratio_col = find_column(
        source_df,
        [
            "出来高倍率",
            "volume_ratio",
            "出来高比",
        ],
    )

    standardized_rows: list[
        dict[str, Any]
    ] = []

    for _, row in source_df.iterrows():
        base_price = safe_float(
            row[price_col]
        )

        if base_price <= 0:
            continue

        pullback_price = (
            safe_float(
                row[pullback_col]
            )
            if pullback_col
            else round(
                base_price
                * (
                    1
                    - DEFAULT_PULLBACK_RATE
                ),
                2,
            )
        )

        target_price = (
            safe_float(
                row[target_col]
            )
            if target_col
            else round(
                base_price
                * (
                    1
                    + DEFAULT_TARGET_RATE
                ),
                2,
            )
        )

        stop_price = (
            safe_float(
                row[stop_col]
            )
            if stop_col
            else round(
                base_price
                * (
                    1
                    - DEFAULT_STOP_RATE
                ),
                2,
            )
        )

        if pullback_price <= 0:
            pullback_price = round(
                base_price
                * (
                    1
                    - DEFAULT_PULLBACK_RATE
                ),
                2,
            )

        if target_price <= base_price:
            target_price = round(
                base_price
                * (
                    1
                    + DEFAULT_TARGET_RATE
                ),
                2,
            )

        if (
            stop_price <= 0
            or stop_price >= base_price
        ):
            stop_price = round(
                base_price
                * (
                    1
                    - DEFAULT_STOP_RATE
                ),
                2,
            )

        standardized_rows.append({
            "銘柄": normalize_text(
                row[name_col]
            ),
            "ticker": normalize_text(
                row[ticker_col]
            ),
            "AI判断": normalize_text(
                row[ai_label_col]
            ),
            "AI判断点": (
                safe_int(
                    row[ai_score_col]
                )
                if ai_score_col
                else 0
            ),
            "PHOENIX_SCORE": (
                safe_int(
                    row[phoenix_score_col]
                )
                if phoenix_score_col
                else 0
            ),
            "RSI": (
                safe_float(
                    row[rsi_col]
                )
                if rsi_col
                else 0.0
            ),
            "MACD判定": (
                normalize_text(
                    row[macd_col]
                )
                if macd_col
                else ""
            ),
            "基準価格": round(
                base_price,
                2,
            ),
            "押し目価格": round(
                pullback_price,
                2,
            ),
            "利確価格": round(
                target_price,
                2,
            ),
            "損切価格": round(
                stop_price,
                2,
            ),
            "前日比%": (
                safe_float(
                    row[change_col]
                )
                if change_col
                else 0.0
            ),
            "出来高倍率": (
                safe_float(
                    row[volume_ratio_col]
                )
                if volume_ratio_col
                else 0.0
            ),
        })

    result = pd.DataFrame(
        standardized_rows
    )

    if result.empty:
        raise ValueError(
            "有効なAI判断データがありません。"
        )

    result = result[
        result["ticker"] != ""
    ].copy()

    return result


# =========================================================
# Trade判定
# =========================================================

def normalize_ai_label(
    label: str,
) -> str:
    return (
        label
        .strip()
        .upper()
        .replace("　", "")
        .replace(" ", "")
    )


def classify_ai_label(
    label: str,
) -> str:
    normalized = normalize_ai_label(
        label
    )

    for item in BUY_LABELS:
        if normalize_ai_label(
            item
        ) in normalized:
            return "BUY"

    for item in WATCH_LABELS:
        if normalize_ai_label(
            item
        ) in normalized:
            return "WATCH"

    for item in SKIP_LABELS:
        if normalize_ai_label(
            item
        ) in normalized:
            return "SKIP"

    return "UNKNOWN"


def calculate_trade_decision(
    row: pd.Series,
    market_risk_score: float,
    market_risk_level: str,
) -> tuple[
    str,
    float,
    str,
]:
    ai_label = normalize_text(
        row["AI判断"]
    )

    ai_category = classify_ai_label(
        ai_label
    )

    ai_score = safe_int(
        row["AI判断点"]
    )

    phoenix_score = safe_int(
        row["PHOENIX_SCORE"]
    )

    rsi = safe_float(
        row["RSI"]
    )

    macd = normalize_text(
        row["MACD判定"]
    ).upper()

    position_ratio = position_ratio_from_risk(
        market_risk_score
    )

    reasons: list[str] = []

    if position_ratio <= 0:
        return (
            "SKIP",
            0.0,
            (
                f"市場リスクが高すぎるため見送り "
                f"({market_risk_level} "
                f"{market_risk_score:.0f})"
            ),
        )

    if ai_category == "SKIP":
        return (
            "SKIP",
            0.0,
            f"AI判断が見送り系: {ai_label}",
        )

    if phoenix_score > 0 and phoenix_score < MIN_PHOENIX_SCORE:
        return (
            "SKIP",
            0.0,
            (
                "PHOENIX_SCORE不足: "
                f"{phoenix_score}"
            ),
        )

    if rsi >= 80:
        return (
            "SKIP",
            0.0,
            (
                "RSI過熱のため見送り: "
                f"{rsi:.1f}"
            ),
        )

    if ai_category == "BUY":
        reasons.append(
            f"AI判断={ai_label}"
        )

        if ai_score >= BUY_MIN_AI_SCORE:
            reasons.append(
                f"AI判断点={ai_score}"
            )

            if "SELL" in macd or "売" in macd:
                return (
                    "WATCH",
                    position_ratio,
                    (
                        "AI判断は買いだが"
                        f"MACDが弱い: {macd}"
                    ),
                )

            return (
                "BUY",
                position_ratio,
                " / ".join(
                    reasons
                ),
            )

        if ai_score >= WATCH_MIN_AI_SCORE:
            return (
                "WATCH",
                position_ratio,
                (
                    "買い系判断だがAI判断点が"
                    f"基準未満: {ai_score}"
                ),
            )

        return (
            "SKIP",
            0.0,
            (
                "AI判断点不足: "
                f"{ai_score}"
            ),
        )

    if ai_category == "WATCH":
        if ai_score >= BUY_MIN_AI_SCORE:
            return (
                "WATCH",
                position_ratio,
                (
                    f"監視系判断: {ai_label} / "
                    f"AI判断点={ai_score}"
                ),
            )

        if ai_score >= WATCH_MIN_AI_SCORE:
            return (
                "WATCH",
                position_ratio,
                (
                    f"押し目監視: {ai_label} / "
                    f"AI判断点={ai_score}"
                ),
            )

        return (
            "SKIP",
            0.0,
            (
                "監視基準未満: "
                f"{ai_score}"
            ),
        )

    if ai_score >= BUY_MIN_AI_SCORE:
        return (
            "BUY",
            position_ratio,
            (
                "AIラベル未分類だが"
                f"AI判断点が高い: {ai_score}"
            ),
        )

    if ai_score >= WATCH_MIN_AI_SCORE:
        return (
            "WATCH",
            position_ratio,
            (
                "AIラベル未分類のため監視: "
                f"{ai_score}"
            ),
        )

    return (
        "SKIP",
        0.0,
        (
            "売買条件を満たさない: "
            f"{ai_label}"
        ),
    )


def build_trade_signals(
    ai_df: pd.DataFrame,
    market_risk: dict[str, Any],
) -> pd.DataFrame:
    rows: list[
        dict[str, Any]
    ] = []

    market_risk_score = safe_float(
        market_risk["score"],
        50.0,
    )

    market_risk_level = normalize_text(
        market_risk["level"]
    )

    for _, row in ai_df.iterrows():
        decision, ratio, reason = (
            calculate_trade_decision(
                row=row,
                market_risk_score=market_risk_score,
                market_risk_level=market_risk_level,
            )
        )

        result = row.to_dict()

        result.update({
            "Trade判定": decision,
            "ロット比率": round(
                ratio,
                2,
            ),
            "MarketRiskScore": round(
                market_risk_score,
                2,
            ),
            "MarketRiskLevel": market_risk_level,
            "判定理由": reason,
            "生成日時": now_text(),
        })

        rows.append(
            result
        )

    result_df = pd.DataFrame(
        rows
    )

    result_df["優先順位"] = (
        result_df["Trade判定"]
        .map({
            "BUY": 0,
            "WATCH": 1,
            "SKIP": 2,
        })
        .fillna(9)
    )

    result_df = (
        result_df.sort_values(
            by=[
                "優先順位",
                "AI判断点",
                "PHOENIX_SCORE",
                "出来高倍率",
                "前日比%",
            ],
            ascending=[
                True,
                False,
                False,
                False,
                False,
            ],
        )
        .drop(
            columns=[
                "優先順位",
            ]
        )
        .reset_index(
            drop=True,
        )
    )

    return result_df


# =========================================================
# Watchlist生成
# =========================================================

def build_watchlist(
    signals: pd.DataFrame,
) -> pd.DataFrame:
    watchlist = signals[
        signals["Trade判定"].isin(
            [
                "BUY",
                "WATCH",
            ]
        )
    ].copy()

    if watchlist.empty:
        return pd.DataFrame(
            columns=OUTPUT_COLUMNS
        )

    watchlist = (
        watchlist.head(
            MAX_WATCHLIST_COUNT
        )
        .copy()
    )

    for column in OUTPUT_COLUMNS:
        if column not in watchlist.columns:
            watchlist[column] = ""

    return watchlist[
        OUTPUT_COLUMNS
    ]


# =========================================================
# 保存
# =========================================================

def save_outputs(
    signals: pd.DataFrame,
    watchlist: pd.DataFrame,
    market_risk: dict[str, Any],
) -> None:
    signals.to_csv(
        TRADE_SIGNAL_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    watchlist.to_csv(
        WATCHLIST_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    buy_count = int(
        (
            signals["Trade判定"]
            == "BUY"
        ).sum()
    )

    watch_count = int(
        (
            signals["Trade判定"]
            == "WATCH"
        ).sum()
    )

    skip_count = int(
        (
            signals["Trade判定"]
            == "SKIP"
        ).sum()
    )

    with open(
        TEXT_REPORT_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            "PHOENIX TRADE ENGINE REPORT\n"
        )
        file.write(
            now_text()
            + "\n"
        )
        file.write(
            "=" * 100
            + "\n"
        )
        file.write(
            "Market Risk Score : "
            f"{safe_float(market_risk['score']):.2f}\n"
        )
        file.write(
            "Market Risk Level : "
            f"{market_risk['level']}\n"
        )
        file.write(
            f"BUY               : {buy_count}\n"
        )
        file.write(
            f"WATCH             : {watch_count}\n"
        )
        file.write(
            f"SKIP              : {skip_count}\n"
        )
        file.write(
            f"Watchlist         : {len(watchlist)}\n"
        )
        file.write(
            "\n"
        )

        if watchlist.empty:
            file.write(
                "監視対象はありません。\n"
            )
        else:
            display_columns = [
                "銘柄",
                "ticker",
                "AI判断",
                "AI判断点",
                "PHOENIX_SCORE",
                "Trade判定",
                "ロット比率",
                "基準価格",
                "押し目価格",
                "利確価格",
                "損切価格",
                "判定理由",
            ]

            file.write(
                watchlist[
                    display_columns
                ].to_string(
                    index=False
                )
            )
            file.write(
                "\n"
            )


# =========================================================
# 表示
# =========================================================

def print_result(
    signals: pd.DataFrame,
    watchlist: pd.DataFrame,
    market_risk: dict[str, Any],
) -> None:
    buy_count = int(
        (
            signals["Trade判定"]
            == "BUY"
        ).sum()
    )

    watch_count = int(
        (
            signals["Trade判定"]
            == "WATCH"
        ).sum()
    )

    skip_count = int(
        (
            signals["Trade判定"]
            == "SKIP"
        ).sum()
    )

    print()
    print("=" * 100)
    print("PHOENIX TRADE ENGINE")
    print("=" * 100)

    print(
        "Market Risk : "
        f"{safe_float(market_risk['score']):.0f} "
        f"({market_risk['level']})"
    )

    print(
        "ロット比率   : "
        f"{position_ratio_from_risk(safe_float(market_risk['score'])) * 100:.0f}%"
    )

    print(
        f"BUY          : {buy_count}件"
    )

    print(
        f"WATCH        : {watch_count}件"
    )

    print(
        f"SKIP         : {skip_count}件"
    )

    print(
        f"監視対象     : {len(watchlist)}件"
    )

    print()
    print("=" * 100)
    print("監視対象一覧")
    print("=" * 100)

    if watchlist.empty:
        print(
            "監視対象はありません。"
        )

    else:
        display_columns = [
            "銘柄",
            "ticker",
            "AI判断",
            "AI判断点",
            "PHOENIX_SCORE",
            "Trade判定",
            "ロット比率",
            "基準価格",
            "押し目価格",
            "利確価格",
            "損切価格",
        ]

        print(
            watchlist[
                display_columns
            ].to_string(
                index=False
            )
        )

    print()
    print(
        f"保存完了: {TRADE_SIGNAL_FILE}"
    )
    print(
        f"保存完了: {WATCHLIST_FILE}"
    )
    print(
        f"保存完了: {TEXT_REPORT_FILE}"
    )


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()
    ensure_directories()

    print("=" * 100)
    print("PHOENIX TRADE ENGINE START")
    print("=" * 100)

    try:
        source_df = load_csv(
            AI_JUDGEMENT_FILE
        )

        print(
            f"AI判断データ: {len(source_df)}件"
        )

        ai_df = standardize_ai_dataframe(
            source_df
        )

        market_risk = load_market_risk()

        print(
            "Market Risk: "
            f"{safe_float(market_risk['score']):.0f} "
            f"({market_risk['level']})"
        )

        signals = build_trade_signals(
            ai_df=ai_df,
            market_risk=market_risk,
        )

        watchlist = build_watchlist(
            signals
        )

        save_outputs(
            signals=signals,
            watchlist=watchlist,
            market_risk=market_risk,
        )

        print_result(
            signals=signals,
            watchlist=watchlist,
            market_risk=market_risk,
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
