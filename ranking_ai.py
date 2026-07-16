# ranking_ai.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd


# =========================================================
# ファイル設定
# =========================================================

REPORT_DIR = Path("reports")

AI_FILE = REPORT_DIR / "ai_judgement.csv"
LEARNING_PROFILE_FILE = REPORT_DIR / "learning_profile.json"
PAPER_SUMMARY_FILE = REPORT_DIR / "paper_trade_summary.csv"

RANKING_FILE = REPORT_DIR / "ranking_ai.csv"
RANKING_TEXT_FILE = REPORT_DIR / "ranking_ai.txt"

MAX_RANKING_COUNT = 20


# =========================================================
# ランキング配点
#
# 各項目を0～100へ正規化し、加重平均する。
# 単純加算による100点張り付きを防ぐ。
#
# 銘柄同士を意図的にずらす処理や、
# 順位に応じた加点・減点は一切行わない。
# =========================================================

WEIGHT_AI_SCORE = 0.34
WEIGHT_PHOENIX_SCORE = 0.19
WEIGHT_JUDGEMENT = 0.10
WEIGHT_RISK = 0.08
WEIGHT_TECHNICAL = 0.10
WEIGHT_LEARNING = 0.14
WEIGHT_REWARD_RISK = 0.05

TOTAL_WEIGHT = (
    WEIGHT_AI_SCORE
    + WEIGHT_PHOENIX_SCORE
    + WEIGHT_JUDGEMENT
    + WEIGHT_RISK
    + WEIGHT_TECHNICAL
    + WEIGHT_LEARNING
    + WEIGHT_REWARD_RISK
)

JUDGEMENT_COMPONENT = {
    "優先監視": 95.0,
    "買い候補": 90.0,
    "押し目待ち": 70.0,
    "様子見": 45.0,
    "見送り": 20.0,
}

RISK_COMPONENT = {
    "低": 90.0,
    "中": 60.0,
    "高": 25.0,
}

MACD_COMPONENT = {
    "BUY": 88.0,
    "NEUTRAL": 55.0,
    "SELL": 25.0,
}


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
    return int(
        round(
            safe_float(
                value,
                default,
            )
        )
    )


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column

    return None


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


# =========================================================
# データ読込
# =========================================================

def load_ai_judgement() -> pd.DataFrame:
    if not AI_FILE.exists():
        raise FileNotFoundError(
            f"AI判断ファイルがありません: {AI_FILE}"
        )

    df = read_csv_safe(
        AI_FILE
    )

    if df.empty:
        raise ValueError(
            "AI判断ファイルが空です。"
        )

    required_columns = {
        "銘柄",
        "ticker",
        "価格",
        "PHOENIX_SCORE",
        "AI判断点",
        "AI判断",
        "リスク",
        "RSI",
        "MACD判定",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            "AI判断ファイルに必要な列がありません: "
            + ", ".join(
                sorted(
                    missing_columns
                )
            )
        )

    numeric_columns = [
        "価格",
        "PHOENIX_SCORE",
        "AI判断点",
        "RSI",
    ]

    optional_numeric_columns = [
        "基本判断点",
        "学習補正点",
        "出来高倍率",
        "前日比%",
        "参考目標価格",
        "参考損切価格",
        "目標価格",
        "損切価格",
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

    df = df.dropna(
        subset=[
            "銘柄",
            "ticker",
            "価格",
            "PHOENIX_SCORE",
            "AI判断点",
        ]
    ).copy()

    df["ticker"] = (
        df["ticker"]
        .astype(str)
        .str.strip()
    )

    return df.reset_index(
        drop=True
    )


def load_learning_profile() -> dict[str, Any]:
    if not LEARNING_PROFILE_FILE.exists():
        return {}

    try:
        with open(
            LEARNING_PROFILE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(
                file
            )

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception:
        pass

    return {}


def load_paper_summary() -> dict[str, Any]:
    if not PAPER_SUMMARY_FILE.exists():
        return {}

    try:
        df = read_csv_safe(
            PAPER_SUMMARY_FILE
        )

        if df.empty:
            return {}

        return df.iloc[-1].to_dict()

    except Exception:
        return {}


# =========================================================
# 学習バケット
# =========================================================

def normalize_macd(
    value: Any,
) -> str:
    text = str(
        value
    ).strip().upper()

    if (
        "BUY" in text
        or "買" in text
    ):
        return "BUY"

    if (
        "SELL" in text
        or "売" in text
    ):
        return "SELL"

    return "NEUTRAL"


def score_bucket(
    value: Any,
) -> str:
    score = safe_float(
        value
    )

    lower = int(
        math.floor(
            score / 5
        )
        * 5
    )

    return (
        f"{lower}-"
        f"{lower + 4}"
    )


def rsi_bucket(
    value: Any,
) -> str:
    rsi = safe_float(
        value
    )

    if rsi < 30:
        return "0-29"

    if rsi < 40:
        return "30-39"

    if rsi < 50:
        return "40-49"

    if rsi < 60:
        return "50-59"

    if rsi < 70:
        return "60-69"

    if rsi < 80:
        return "70-79"

    return "80-100"


def volume_bucket(
    value: Any,
) -> str:
    volume = safe_float(
        value
    )

    if volume < 0.8:
        return "0.0-0.79"

    if volume < 1.0:
        return "0.8-0.99"

    if volume < 1.2:
        return "1.0-1.19"

    if volume < 1.5:
        return "1.2-1.49"

    if volume < 2.0:
        return "1.5-1.99"

    if volume < 3.0:
        return "2.0-2.99"

    return "3.0以上"


def get_group_data(
    profile: dict[str, Any],
    group_type: str,
    condition: str,
) -> dict[str, Any]:
    groups = profile.get(
        "groups",
        {}
    )

    if not isinstance(
        groups,
        dict,
    ):
        return {}

    group = groups.get(
        group_type,
        {}
    )

    if not isinstance(
        group,
        dict,
    ):
        return {}

    result = group.get(
        condition,
        {}
    )

    if isinstance(
        result,
        dict,
    ):
        return result

    return {}


# =========================================================
# 各構成点
# =========================================================

def normalize_input_score(
    value: Any,
) -> float:
    return clamp(
        safe_float(value),
        0.0,
        100.0,
    )


def calculate_rsi_component(
    rsi: float,
) -> tuple[float, str]:
    if 45 <= rsi <= 60:
        return (
            92.0,
            "RSI良好",
        )

    if 40 <= rsi < 45:
        return (
            84.0,
            "RSIやや低め",
        )

    if 60 < rsi <= 68:
        return (
            82.0,
            "RSIやや高め",
        )

    if 35 <= rsi < 40:
        return (
            72.0,
            "RSI低め",
        )

    if 68 < rsi <= 75:
        return (
            68.0,
            "RSI高め",
        )

    if 30 <= rsi < 35:
        return (
            58.0,
            "RSI反発待ち",
        )

    if rsi < 30:
        return (
            48.0,
            "RSI売られ過ぎ",
        )

    if rsi <= 80:
        return (
            42.0,
            "RSI過熱気味",
        )

    return (
        20.0,
        "RSI過熱",
    )


def calculate_volume_component(
    volume_ratio: float,
) -> tuple[float, str]:
    if volume_ratio >= 3.0:
        return (
            90.0,
            "出来高急増",
        )

    if volume_ratio >= 2.0:
        return (
            94.0,
            "出来高強い",
        )

    if volume_ratio >= 1.5:
        return (
            88.0,
            "出来高増加",
        )

    if volume_ratio >= 1.2:
        return (
            80.0,
            "出来高やや増加",
        )

    if volume_ratio >= 1.0:
        return (
            72.0,
            "出来高通常",
        )

    if volume_ratio >= 0.8:
        return (
            62.0,
            "出来高低め",
        )

    return (
        48.0,
        "出来高不足",
    )


def calculate_technical_component(
    row: pd.Series,
    volume_column: str | None,
) -> tuple[
    float,
    float,
    str,
]:
    rsi = safe_float(
        row["RSI"]
    )

    macd = normalize_macd(
        row["MACD判定"]
    )

    rsi_score, rsi_reason = (
        calculate_rsi_component(
            rsi
        )
    )

    macd_score = MACD_COMPONENT.get(
        macd,
        55.0,
    )

    volume_ratio = 0.0
    volume_score = 60.0
    volume_reason = "出来高データなし"

    if volume_column is not None:
        volume_ratio = safe_float(
            row[volume_column]
        )

        (
            volume_score,
            volume_reason,
        ) = calculate_volume_component(
            volume_ratio
        )

    technical_score = (
        rsi_score * 0.40
        + macd_score * 0.40
        + volume_score * 0.20
    )

    reason = (
        f"{rsi_reason}"
        f"・MACD{macd}"
        f"・{volume_reason}"
    )

    return (
        clamp(
            technical_score,
            0.0,
            100.0,
        ),
        volume_ratio,
        reason,
    )


def calculate_reward_risk_component(
    row: pd.Series,
) -> tuple[
    float,
    float,
    str,
]:
    price = safe_float(
        row["価格"]
    )

    target_column = None

    for candidate in (
        "参考目標価格",
        "目標価格",
        "利確価格",
    ):
        if candidate in row.index:
            target_column = candidate
            break

    stop_column = None

    for candidate in (
        "参考損切価格",
        "損切価格",
    ):
        if candidate in row.index:
            stop_column = candidate
            break

    if (
        target_column is None
        or stop_column is None
    ):
        return (
            55.0,
            0.0,
            "RRデータなし",
        )

    target_price = safe_float(
        row[target_column]
    )

    stop_price = safe_float(
        row[stop_column]
    )

    if (
        price <= 0
        or target_price <= price
        or stop_price <= 0
        or stop_price >= price
    ):
        return (
            50.0,
            0.0,
            "RR判定不能",
        )

    upside = (
        target_price
        - price
    ) / price

    downside = (
        price
        - stop_price
    ) / price

    if downside <= 0:
        return (
            50.0,
            0.0,
            "RR判定不能",
        )

    reward_risk = (
        upside
        / downside
    )

    if reward_risk >= 3.0:
        score = 95.0

    elif reward_risk >= 2.5:
        score = 90.0

    elif reward_risk >= 2.0:
        score = 84.0

    elif reward_risk >= 1.5:
        score = 74.0

    elif reward_risk >= 1.2:
        score = 64.0

    elif reward_risk >= 1.0:
        score = 54.0

    else:
        score = 35.0

    return (
        score,
        reward_risk,
        f"RR {reward_risk:.2f}",
    )


# =========================================================
# 学習評価
# =========================================================

def group_learning_quality(
    group_data: dict[str, Any],
) -> tuple[
    float,
    float,
    float,
    str,
]:
    if not group_data:
        return (
            50.0,
            50.0,
            0.0,
            "学習データなし",
        )

    sample_count = safe_float(
        group_data.get(
            "effective_sample_count",
            group_data.get(
                "sample_count",
                0,
            ),
        )
    )

    win_rate = safe_float(
        group_data.get(
            "win_rate",
            50.0,
        ),
        50.0,
    )

    average_return = safe_float(
        group_data.get(
            "average_return",
            0.0,
        )
    )

    profit_factor = safe_float(
        group_data.get(
            "profit_factor",
            1.0,
        ),
        1.0,
    )

    reliability = clamp(
        sample_count / 300.0,
        0.0,
        1.0,
    )

    win_score = clamp(
        50.0
        + (
            win_rate
            - 50.0
        )
        * 3.0,
        0.0,
        100.0,
    )

    return_score = clamp(
        50.0
        + average_return
        * 55.0,
        0.0,
        100.0,
    )

    pf_score = clamp(
        50.0
        + (
            profit_factor
            - 1.0
        )
        * 45.0,
        0.0,
        100.0,
    )

    measured_quality = (
        win_score * 0.40
        + return_score * 0.35
        + pf_score * 0.25
    )

    quality = (
        50.0
        + (
            measured_quality
            - 50.0
        )
        * reliability
    )

    reason = (
        f"件数{safe_int(sample_count)}"
        f"・勝率{win_rate:.1f}%"
        f"・平均{average_return:+.3f}%"
        f"・PF{profit_factor:.2f}"
    )

    return (
        clamp(
            quality,
            0.0,
            100.0,
        ),
        win_rate,
        average_return,
        reason,
    )


def calculate_learning_component(
    row: pd.Series,
    profile: dict[str, Any],
    volume_column: str | None,
) -> tuple[
    float,
    float,
    float,
    str,
]:
    phoenix_score = safe_float(
        row["PHOENIX_SCORE"]
    )

    rsi = safe_float(
        row["RSI"]
    )

    macd = normalize_macd(
        row["MACD判定"]
    )

    score_condition = score_bucket(
        phoenix_score
    )

    rsi_condition = rsi_bucket(
        rsi
    )

    group_specs: list[
        tuple[
            str,
            str,
            float,
        ]
    ] = [
        (
            "score",
            score_condition,
            0.25,
        ),
        (
            "rsi",
            rsi_condition,
            0.20,
        ),
        (
            "macd",
            macd,
            0.20,
        ),
    ]

    volume_condition = ""

    if volume_column is not None:
        volume_ratio = safe_float(
            row[volume_column]
        )

        volume_condition = volume_bucket(
            volume_ratio
        )

        group_specs.append(
            (
                "volume",
                volume_condition,
                0.15,
            )
        )

        combination_condition = (
            f"{score_condition} | "
            f"{rsi_condition} | "
            f"{macd} | "
            f"{volume_condition}"
        )

        group_specs.append(
            (
                "combination",
                combination_condition,
                0.20,
            )
        )

    else:
        group_specs = [
            (
                "score",
                score_condition,
                0.35,
            ),
            (
                "rsi",
                rsi_condition,
                0.30,
            ),
            (
                "macd",
                macd,
                0.35,
            ),
        ]

    total_quality = 0.0
    total_weight = 0.0

    expected_win_rate = 0.0
    expected_return = 0.0

    reasons: list[str] = []

    for (
        group_type,
        condition,
        weight,
    ) in group_specs:
        group_data = get_group_data(
            profile=profile,
            group_type=group_type,
            condition=condition,
        )

        (
            quality,
            win_rate,
            average_return,
            reason,
        ) = group_learning_quality(
            group_data
        )

        total_quality += (
            quality
            * weight
        )

        expected_win_rate += (
            win_rate
            * weight
        )

        expected_return += (
            average_return
            * weight
        )

        total_weight += weight

        label = {
            "score": "スコア帯",
            "rsi": "RSI帯",
            "macd": "MACD",
            "volume": "出来高帯",
            "combination": "複合条件",
        }.get(
            group_type,
            group_type,
        )

        reasons.append(
            f"{label}{condition}: {reason}"
        )

    if total_weight <= 0:
        return (
            50.0,
            50.0,
            0.0,
            "学習データなし",
        )

    return (
        clamp(
            total_quality
            / total_weight,
            0.0,
            100.0,
        ),
        expected_win_rate
        / total_weight,
        expected_return
        / total_weight,
        " / ".join(
            reasons
        ),
    )


# =========================================================
# ペーパー成績
# =========================================================

def calculate_paper_adjustment(
    paper_summary: dict[str, Any],
) -> tuple[
    float,
    str,
]:
    closed_count = safe_int(
        paper_summary.get(
            "決済済み",
            0,
        )
    )

    if closed_count < 10:
        return (
            0.0,
            f"ペーパー決済{closed_count}件",
        )

    win_rate = safe_float(
        paper_summary.get(
            "勝率%",
            0.0,
        )
    )

    profit_factor = safe_float(
        paper_summary.get(
            "プロフィットファクター",
            0.0,
        )
    )

    reliability = clamp(
        closed_count / 100.0,
        0.0,
        1.0,
    )

    adjustment = (
        (
            win_rate
            - 50.0
        )
        * 0.08
        + (
            profit_factor
            - 1.0
        )
        * 3.0
    ) * reliability

    adjustment = clamp(
        adjustment,
        -3.0,
        3.0,
    )

    return (
        adjustment,
        (
            f"ペーパー{closed_count}件"
            f"・勝率{win_rate:.1f}%"
            f"・PF{profit_factor:.2f}"
        ),
    )


# =========================================================
# 最終評価
# =========================================================

def determine_grade(
    ranking_score: float,
) -> str:
    if ranking_score >= 85:
        return "S"

    if ranking_score >= 78:
        return "A"

    if ranking_score >= 70:
        return "B"

    if ranking_score >= 62:
        return "C"

    if ranking_score >= 52:
        return "D"

    return "E"


def determine_stars(
    ranking_score: float,
) -> str:
    if ranking_score >= 85:
        return "★★★★★"

    if ranking_score >= 78:
        return "★★★★☆"

    if ranking_score >= 70:
        return "★★★☆☆"

    if ranking_score >= 62:
        return "★★☆☆☆"

    if ranking_score >= 52:
        return "★☆☆☆☆"

    return "☆☆☆☆☆"


def determine_action(
    ranking_score: float,
    judgement: str,
    risk: str,
) -> str:
    if (
        ranking_score >= 82
        and judgement in {
            "買い候補",
            "優先監視",
        }
        and risk == "低"
    ):
        return "最優先監視"

    if (
        ranking_score >= 74
        and judgement in {
            "買い候補",
            "優先監視",
        }
    ):
        return "買い監視"

    if ranking_score >= 66:
        return "押し目監視"

    if ranking_score >= 55:
        return "継続観察"

    return "見送り"


def create_ranking(
    ai_df: pd.DataFrame,
    profile: dict[str, Any],
    paper_summary: dict[str, Any],
) -> pd.DataFrame:
    rows: list[
        dict[str, Any]
    ] = []

    volume_column = find_column(
        ai_df,
        [
            "出来高倍率",
            "volume_ratio",
        ],
    )

    (
        paper_adjustment,
        paper_reason,
    ) = calculate_paper_adjustment(
        paper_summary
    )

    for _, row in ai_df.iterrows():
        ai_score = normalize_input_score(
            row["AI判断点"]
        )

        phoenix_score = normalize_input_score(
            row["PHOENIX_SCORE"]
        )

        judgement = str(
            row["AI判断"]
        ).strip()

        risk = str(
            row["リスク"]
        ).strip()

        judgement_component = (
            JUDGEMENT_COMPONENT.get(
                judgement,
                45.0,
            )
        )

        risk_component = (
            RISK_COMPONENT.get(
                risk,
                55.0,
            )
        )

        (
            technical_component,
            volume_ratio,
            technical_reason,
        ) = calculate_technical_component(
            row=row,
            volume_column=volume_column,
        )

        (
            learning_component,
            expected_win_rate,
            expected_return,
            learning_reason,
        ) = calculate_learning_component(
            row=row,
            profile=profile,
            volume_column=volume_column,
        )

        (
            reward_risk_component,
            reward_risk,
            reward_risk_reason,
        ) = calculate_reward_risk_component(
            row
        )

        weighted_score = (
            ai_score
            * WEIGHT_AI_SCORE
            + phoenix_score
            * WEIGHT_PHOENIX_SCORE
            + judgement_component
            * WEIGHT_JUDGEMENT
            + risk_component
            * WEIGHT_RISK
            + technical_component
            * WEIGHT_TECHNICAL
            + learning_component
            * WEIGHT_LEARNING
            + reward_risk_component
            * WEIGHT_REWARD_RISK
        ) / TOTAL_WEIGHT

        ranking_score = clamp(
            weighted_score
            + paper_adjustment,
            0.0,
            100.0,
        )

        grade = determine_grade(
            ranking_score
        )

        stars = determine_stars(
            ranking_score
        )

        action = determine_action(
            ranking_score=ranking_score,
            judgement=judgement,
            risk=risk,
        )

        ranking_reason = (
            f"AI {ai_score:.1f}"
            f"×{WEIGHT_AI_SCORE:.0%}"
            f" / PHOENIX {phoenix_score:.1f}"
            f"×{WEIGHT_PHOENIX_SCORE:.0%}"
            f" / 判断 {judgement_component:.1f}"
            f"×{WEIGHT_JUDGEMENT:.0%}"
            f" / リスク {risk_component:.1f}"
            f"×{WEIGHT_RISK:.0%}"
            f" / テクニカル {technical_component:.1f}"
            f"×{WEIGHT_TECHNICAL:.0%}"
            f" / 学習 {learning_component:.1f}"
            f"×{WEIGHT_LEARNING:.0%}"
            f" / RR {reward_risk_component:.1f}"
            f"×{WEIGHT_REWARD_RISK:.0%}"
            f" / {paper_reason}"
        )

        rows.append({
            "順位": 0,
            "銘柄": str(
                row["銘柄"]
            ),
            "ticker": str(
                row["ticker"]
            ),
            "価格": round(
                safe_float(
                    row["価格"]
                ),
                2,
            ),
            "ランキング点": round(
                ranking_score,
                4,
            ),
            "ランク": grade,
            "評価": stars,
            "監視区分": action,
            "AI判断": judgement,
            "AI判断点": round(
                ai_score,
                2,
            ),
            "PHOENIX_SCORE": round(
                phoenix_score,
                2,
            ),
            "基本判断点": safe_int(
                row.get(
                    "基本判断点",
                    0,
                )
            ),
            "既存学習補正点": safe_int(
                row.get(
                    "学習補正点",
                    0,
                )
            ),
            "判断構成点": round(
                judgement_component,
                2,
            ),
            "リスク構成点": round(
                risk_component,
                2,
            ),
            "テクニカル構成点": round(
                technical_component,
                2,
            ),
            "学習構成点": round(
                learning_component,
                2,
            ),
            "RR構成点": round(
                reward_risk_component,
                2,
            ),
            "ペーパー成績補正": round(
                paper_adjustment,
                4,
            ),
            "期待勝率%": round(
                expected_win_rate,
                2,
            ),
            "期待騰落率%": round(
                expected_return,
                4,
            ),
            "リスク": risk,
            "RSI": round(
                safe_float(
                    row["RSI"]
                ),
                2,
            ),
            "MACD判定": normalize_macd(
                row["MACD判定"]
            ),
            "出来高倍率": round(
                volume_ratio,
                3,
            ),
            "リスクリワード": round(
                reward_risk,
                3,
            ),
            "テクニカル根拠": (
                technical_reason
            ),
            "RR根拠": (
                reward_risk_reason
            ),
            "ランキング根拠": (
                ranking_reason
            ),
            "学習根拠": (
                learning_reason
            ),
            "生成日時": now_text(),
        })

    ranking_df = pd.DataFrame(
        rows
    )

    ranking_df = (
        ranking_df.sort_values(
            by=[
                "ランキング点",
                "期待騰落率%",
                "期待勝率%",
                "AI判断点",
                "PHOENIX_SCORE",
            ],
            ascending=[
                False,
                False,
                False,
                False,
                False,
            ],
        )
        .head(
            MAX_RANKING_COUNT
        )
        .reset_index(
            drop=True
        )
    )

    ranking_df["順位"] = (
        ranking_df.index
        + 1
    )

    ranking_df["順位"] = ranking_df[
        "順位"
    ].astype(int)

    return ranking_df


# =========================================================
# 保存
# =========================================================

def save_ranking(
    ranking_df: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    ranking_df.to_csv(
        RANKING_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    with open(
        RANKING_TEXT_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            "PHOENIX RANKING AI\n"
        )

        file.write(
            now_text()
            + "\n"
        )

        file.write(
            "=" * 100
            + "\n\n"
        )

        if ranking_df.empty:
            file.write(
                "ランキング対象はありません。\n"
            )

            return

        for _, row in ranking_df.iterrows():
            file.write(
                f"{safe_int(row['順位'])}位 "
                f"{row['銘柄']} "
                f"({row['ticker']})\n"
            )

            file.write(
                f"{row['評価']} "
                f"ランク{row['ランク']} "
                f"{safe_float(row['ランキング点']):.4f}点\n"
            )

            file.write(
                f"監視区分: "
                f"{row['監視区分']}\n"
            )

            file.write(
                f"AI判断: "
                f"{row['AI判断']} "
                f"{safe_float(row['AI判断点']):.2f}点\n"
            )

            file.write(
                f"PHOENIX SCORE: "
                f"{safe_float(row['PHOENIX_SCORE']):.2f}点\n"
            )

            file.write(
                f"期待勝率: "
                f"{safe_float(row['期待勝率%']):.2f}%\n"
            )

            file.write(
                f"期待騰落率: "
                f"{safe_float(row['期待騰落率%']):+.4f}%\n"
            )

            file.write(
                f"テクニカル: "
                f"{row['テクニカル構成点']:.2f}点 "
                f"({row['テクニカル根拠']})\n"
            )

            file.write(
                f"学習評価: "
                f"{row['学習構成点']:.2f}点\n"
            )

            file.write(
                f"リスクリワード: "
                f"{row['RR根拠']}\n"
            )

            file.write(
                f"計算根拠: "
                f"{row['ランキング根拠']}\n"
            )

            file.write(
                f"学習根拠: "
                f"{row['学習根拠']}\n"
            )

            file.write(
                "-" * 100
                + "\n"
            )


# =========================================================
# 表示
# =========================================================

def print_ranking(
    ranking_df: pd.DataFrame,
    profile: dict[str, Any],
    paper_summary: dict[str, Any],
) -> None:
    print()
    print("=" * 115)
    print("PHOENIX RANKING AI v2")
    print("=" * 115)

    print(
        f"AI判断ファイル       : {AI_FILE}"
    )

    print(
        "自己学習プロフィール : "
        + str(
            profile.get(
                "generated_at",
                "未読込",
            )
        )
    )

    print(
        "ペーパー決済件数     : "
        + str(
            safe_int(
                paper_summary.get(
                    "決済済み",
                    0,
                )
            )
        )
    )

    print(
        f"ランキング対象数     : {len(ranking_df)}"
    )

    print()
    print("=" * 115)
    print("監視優先ランキング")
    print("=" * 115)

    if ranking_df.empty:
        print(
            "ランキング対象はありません。"
        )

        return

    display_columns = [
        "順位",
        "銘柄",
        "ticker",
        "ランキング点",
        "ランク",
        "評価",
        "監視区分",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "学習構成点",
        "期待勝率%",
        "期待騰落率%",
        "リスク",
    ]

    display_df = ranking_df[
        display_columns
    ].copy()

    display_df[
        "ランキング点"
    ] = display_df[
        "ランキング点"
    ].map(
        lambda value: f"{safe_float(value):.4f}"
    )

    print(
        display_df.to_string(
            index=False
        )
    )

    print()
    print("=" * 115)
    print("TOP10 判断詳細")
    print("=" * 115)

    for _, row in (
        ranking_df
        .head(10)
        .iterrows()
    ):
        print()

        print(
            f"[{safe_int(row['順位'])}] "
            f"{row['銘柄']} "
            f"({row['ticker']})"
        )

        print(
            f"{row['評価']} "
            f"ランク{row['ランク']} / "
            f"{safe_float(row['ランキング点']):.4f}点 / "
            f"{row['監視区分']}"
        )

        print(
            f"AI判断: "
            f"{row['AI判断']} "
            f"{safe_float(row['AI判断点']):.2f}点 / "
            f"PHOENIX "
            f"{safe_float(row['PHOENIX_SCORE']):.2f}点"
        )

        print(
            f"構成点: "
            f"判断 {safe_float(row['判断構成点']):.2f} / "
            f"リスク {safe_float(row['リスク構成点']):.2f} / "
            f"テクニカル {safe_float(row['テクニカル構成点']):.2f} / "
            f"学習 {safe_float(row['学習構成点']):.2f} / "
            f"RR {safe_float(row['RR構成点']):.2f}"
        )

        print(
            f"期待値: "
            f"勝率 "
            f"{safe_float(row['期待勝率%']):.2f}% / "
            f"騰落率 "
            f"{safe_float(row['期待騰落率%']):+.4f}%"
        )

        print(
            f"計算根拠: "
            f"{row['ランキング根拠']}"
        )

        print(
            f"学習根拠: "
            f"{row['学習根拠']}"
        )

    print()
    print(
        f"保存完了 : {RANKING_FILE}"
    )

    print(
        f"保存完了 : {RANKING_TEXT_FILE}"
    )


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()

    print("=" * 115)
    print("PHOENIX NON-SATURATING RANKING AI")
    print("=" * 115)

    try:
        ai_df = load_ai_judgement()

        profile = load_learning_profile()

        paper_summary = (
            load_paper_summary()
        )

        ranking_df = create_ranking(
            ai_df=ai_df,
            profile=profile,
            paper_summary=paper_summary,
        )

        save_ranking(
            ranking_df
        )

        print_ranking(
            ranking_df=ranking_df,
            profile=profile,
            paper_summary=paper_summary,
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