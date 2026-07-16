# ranking_ai.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd


REPORT_DIR = Path("reports")

AI_FILE = REPORT_DIR / "ai_judgement.csv"
LEARNING_PROFILE_FILE = REPORT_DIR / "learning_profile.json"
PAPER_SUMMARY_FILE = REPORT_DIR / "paper_trade_summary.csv"

RANKING_FILE = REPORT_DIR / "ranking_ai.csv"
RANKING_TEXT_FILE = REPORT_DIR / "ranking_ai.txt"

MAX_RANKING_COUNT = 20

JUDGEMENT_SCORE = {
    "買い候補": 20,
    "優先監視": 20,
    "押し目待ち": 10,
    "様子見": 0,
    "見送り": -20,
}

RISK_SCORE = {
    "低": 10,
    "中": 0,
    "高": -15,
}

MACD_SCORE = {
    "BUY": 8,
    "NEUTRAL": 0,
    "SELL": -8,
}

MAX_LEARNING_BONUS = 20
MIN_LEARNING_BONUS = -20


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


def load_ai_judgement() -> pd.DataFrame:
    if not AI_FILE.exists():
        raise FileNotFoundError(
            f"AI判断ファイルがありません: "
            f"{AI_FILE}"
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

    data = group.get(
        condition,
        {}
    )

    if isinstance(
        data,
        dict,
    ):
        return data

    return {}


def calculate_profile_bonus(
    group_data: dict[str, Any],
    maximum_absolute_bonus: float,
) -> tuple[float, str]:
    if not group_data:
        return (
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

    evaluation = safe_float(
        group_data.get(
            "evaluation",
            0.0,
        )
    )

    reliability = clamp(
        sample_count / 300.0,
        0.0,
        1.0,
    )

    raw_bonus = (
        (
            win_rate
            - 50.0
        )
        * 0.30
        + average_return
        * 4.0
        + (
            clamp(
                profit_factor,
                0.0,
                3.0,
            )
            - 1.0
        )
        * 4.0
        + evaluation
        * 0.10
    )

    bonus = clamp(
        raw_bonus * reliability,
        -maximum_absolute_bonus,
        maximum_absolute_bonus,
    )

    reason = (
        f"件数{safe_int(sample_count)}"
        f"・勝率{win_rate:.1f}%"
        f"・平均{average_return:+.3f}%"
        f"・PF{profit_factor:.2f}"
    )

    return (
        bonus,
        reason,
    )


def calculate_learning_expectation(
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

    score_data = get_group_data(
        profile,
        "score",
        score_condition,
    )

    rsi_data = get_group_data(
        profile,
        "rsi",
        rsi_condition,
    )

    macd_data = get_group_data(
        profile,
        "macd",
        macd,
    )

    score_bonus, score_reason = (
        calculate_profile_bonus(
            score_data,
            5.0,
        )
    )

    rsi_bonus, rsi_reason = (
        calculate_profile_bonus(
            rsi_data,
            4.0,
        )
    )

    macd_bonus, macd_reason = (
        calculate_profile_bonus(
            macd_data,
            4.0,
        )
    )

    bonuses = [
        score_bonus,
        rsi_bonus,
        macd_bonus,
    ]

    reasons = [
        f"スコア帯{score_condition}: "
        f"{score_reason}",
        f"RSI帯{rsi_condition}: "
        f"{rsi_reason}",
        f"MACD{macd}: "
        f"{macd_reason}",
    ]

    if volume_column is not None:
        volume = safe_float(
            row[volume_column]
        )

        volume_condition = volume_bucket(
            volume
        )

        volume_data = get_group_data(
            profile,
            "volume",
            volume_condition,
        )

        volume_bonus, volume_reason = (
            calculate_profile_bonus(
                volume_data,
                4.0,
            )
        )

        bonuses.append(
            volume_bonus
        )

        reasons.append(
            f"出来高帯{volume_condition}: "
            f"{volume_reason}"
        )

        combination_condition = (
            f"{score_condition} | "
            f"{rsi_condition} | "
            f"{macd} | "
            f"{volume_condition}"
        )

        combination_data = get_group_data(
            profile,
            "combination",
            combination_condition,
        )

        combination_bonus, combination_reason = (
            calculate_profile_bonus(
                combination_data,
                8.0,
            )
        )

        bonuses.append(
            combination_bonus
        )

        reasons.append(
            "複合条件: "
            f"{combination_reason}"
        )

    total_bonus = clamp(
        sum(
            bonuses
        ),
        MIN_LEARNING_BONUS,
        MAX_LEARNING_BONUS,
    )

    valid_group_data = [
        data
        for data in (
            score_data,
            rsi_data,
            macd_data,
        )
        if data
    ]

    expected_return_values = [
        safe_float(
            data.get(
                "average_return",
                0.0,
            )
        )
        for data in valid_group_data
    ]

    expected_win_rate_values = [
        safe_float(
            data.get(
                "win_rate",
                50.0,
            ),
            50.0,
        )
        for data in valid_group_data
    ]

    expected_return = (
        sum(
            expected_return_values
        )
        / len(
            expected_return_values
        )
        if expected_return_values
        else 0.0
    )

    expected_win_rate = (
        sum(
            expected_win_rate_values
        )
        / len(
            expected_win_rate_values
        )
        if expected_win_rate_values
        else 50.0
    )

    return (
        total_bonus,
        expected_return,
        expected_win_rate,
        " / ".join(
            reasons
        ),
    )


def calculate_rsi_score(
    rsi: float,
) -> tuple[float, str]:
    if 40 <= rsi <= 65:
        return (
            10.0,
            "RSI適正",
        )

    if 30 <= rsi < 40:
        return (
            6.0,
            "RSI低め",
        )

    if 65 < rsi <= 75:
        return (
            4.0,
            "RSIやや高め",
        )

    if rsi < 30:
        return (
            2.0,
            "RSI売られ過ぎ",
        )

    return (
        -8.0,
        "RSI過熱",
    )


def calculate_volume_score(
    volume_ratio: float,
) -> tuple[float, str]:
    if volume_ratio >= 3.0:
        return (
            8.0,
            "出来高急増",
        )

    if volume_ratio >= 2.0:
        return (
            7.0,
            "出来高強い",
        )

    if volume_ratio >= 1.5:
        return (
            5.0,
            "出来高増加",
        )

    if volume_ratio >= 1.0:
        return (
            2.0,
            "出来高通常",
        )

    return (
        0.0,
        "出来高低め",
    )


def calculate_price_position_score(
    row: pd.Series,
) -> tuple[float, str]:
    price = safe_float(
        row["価格"]
    )

    target_column = find_column(
        pd.DataFrame(
            [row]
        ),
        [
            "参考目標価格",
            "目標価格",
            "利確価格",
        ],
    )

    stop_column = find_column(
        pd.DataFrame(
            [row]
        ),
        [
            "参考損切価格",
            "損切価格",
        ],
    )

    if (
        target_column is None
        or stop_column is None
    ):
        return (
            0.0,
            "目標価格データなし",
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
            0.0,
            "価格幅判定なし",
        )

    upside = (
        target_price
        - price
    ) / price * 100.0

    downside = (
        price
        - stop_price
    ) / price * 100.0

    if downside <= 0:
        return (
            0.0,
            "損切幅不正",
        )

    reward_risk = (
        upside
        / downside
    )

    if reward_risk >= 3.0:
        return (
            10.0,
            f"RR {reward_risk:.2f}",
        )

    if reward_risk >= 2.0:
        return (
            7.0,
            f"RR {reward_risk:.2f}",
        )

    if reward_risk >= 1.5:
        return (
            4.0,
            f"RR {reward_risk:.2f}",
        )

    if reward_risk >= 1.0:
        return (
            0.0,
            f"RR {reward_risk:.2f}",
        )

    return (
        -8.0,
        f"RR {reward_risk:.2f}",
    )


def calculate_paper_market_adjustment(
    paper_summary: dict[str, Any],
) -> tuple[float, str]:
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

    total_adjustment = 0.0

    if win_rate >= 60:
        total_adjustment += 3.0

    elif win_rate >= 50:
        total_adjustment += 1.0

    elif win_rate < 40:
        total_adjustment -= 4.0

    if profit_factor >= 1.5:
        total_adjustment += 3.0

    elif profit_factor >= 1.1:
        total_adjustment += 1.0

    elif profit_factor < 0.8:
        total_adjustment -= 4.0

    total_adjustment = clamp(
        total_adjustment,
        -8.0,
        6.0,
    )

    return (
        total_adjustment,
        (
            f"ペーパー{closed_count}件"
            f"・勝率{win_rate:.1f}%"
            f"・PF{profit_factor:.2f}"
        ),
    )


def determine_grade(
    ranking_score: float,
) -> str:
    if ranking_score >= 90:
        return "S"

    if ranking_score >= 80:
        return "A"

    if ranking_score >= 70:
        return "B"

    if ranking_score >= 60:
        return "C"

    if ranking_score >= 50:
        return "D"

    return "E"


def determine_stars(
    ranking_score: float,
) -> str:
    if ranking_score >= 90:
        return "★★★★★"

    if ranking_score >= 80:
        return "★★★★☆"

    if ranking_score >= 70:
        return "★★★☆☆"

    if ranking_score >= 60:
        return "★★☆☆☆"

    if ranking_score >= 50:
        return "★☆☆☆☆"

    return "☆☆☆☆☆"


def determine_action(
    ranking_score: float,
    judgement: str,
    risk: str,
) -> str:
    if (
        ranking_score >= 85
        and judgement in {
            "買い候補",
            "優先監視",
        }
        and risk == "低"
    ):
        return "最優先監視"

    if (
        ranking_score >= 75
        and judgement in {
            "買い候補",
            "優先監視",
        }
    ):
        return "買い監視"

    if ranking_score >= 65:
        return "押し目監視"

    if ranking_score >= 50:
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

    paper_adjustment, paper_reason = (
        calculate_paper_market_adjustment(
            paper_summary
        )
    )

    for _, row in ai_df.iterrows():
        ai_score = safe_float(
            row["AI判断点"]
        )

        phoenix_score = safe_float(
            row["PHOENIX_SCORE"]
        )

        judgement = str(
            row["AI判断"]
        ).strip()

        risk = str(
            row["リスク"]
        ).strip()

        rsi = safe_float(
            row["RSI"]
        )

        macd = normalize_macd(
            row["MACD判定"]
        )

        judgement_bonus = (
            JUDGEMENT_SCORE.get(
                judgement,
                0,
            )
        )

        risk_bonus = (
            RISK_SCORE.get(
                risk,
                0,
            )
        )

        macd_bonus = (
            MACD_SCORE.get(
                macd,
                0,
            )
        )

        rsi_bonus, rsi_reason = (
            calculate_rsi_score(
                rsi
            )
        )

        volume_bonus = 0.0
        volume_reason = "出来高データなし"
        volume_ratio = 0.0

        if volume_column is not None:
            volume_ratio = safe_float(
                row[volume_column]
            )

            (
                volume_bonus,
                volume_reason,
            ) = calculate_volume_score(
                volume_ratio
            )

        (
            learning_bonus,
            expected_return,
            expected_win_rate,
            learning_reason,
        ) = calculate_learning_expectation(
            row=row,
            profile=profile,
            volume_column=volume_column,
        )

        (
            price_position_bonus,
            price_position_reason,
        ) = calculate_price_position_score(
            row
        )

        base_score = (
            ai_score * 0.50
            + phoenix_score * 0.25
            + judgement_bonus
            + risk_bonus
            + macd_bonus
            + rsi_bonus
            + volume_bonus
            + learning_bonus
            + price_position_bonus
            + paper_adjustment
        )

        ranking_score = clamp(
            base_score,
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

        reasons = [
            f"AI判断点{safe_int(ai_score)}",
            f"PHOENIX{safe_int(phoenix_score)}",
            f"判断{judgement}",
            f"リスク{risk}",
            f"MACD{macd}",
            rsi_reason,
            volume_reason,
            price_position_reason,
            paper_reason,
        ]

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
                2,
            ),
            "ランク": grade,
            "評価": stars,
            "監視区分": action,
            "AI判断": judgement,
            "AI判断点": safe_int(
                ai_score
            ),
            "PHOENIX_SCORE": safe_int(
                phoenix_score
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
            "ランキング学習補正": round(
                learning_bonus,
                2,
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
                rsi,
                2,
            ),
            "MACD判定": macd,
            "出来高倍率": round(
                volume_ratio,
                3,
            ),
            "判断補正": round(
                judgement_bonus,
                2,
            ),
            "リスク補正": round(
                risk_bonus,
                2,
            ),
            "MACD補正": round(
                macd_bonus,
                2,
            ),
            "RSI補正": round(
                rsi_bonus,
                2,
            ),
            "出来高補正": round(
                volume_bonus,
                2,
            ),
            "価格位置補正": round(
                price_position_bonus,
                2,
            ),
            "ペーパー成績補正": round(
                paper_adjustment,
                2,
            ),
            "ランキング根拠": " / ".join(
                reasons
            ),
            "学習根拠": learning_reason,
            "生成日時": now_text(),
        })

    ranking_df = pd.DataFrame(
        rows
    )

    ranking_df = (
        ranking_df.sort_values(
            by=[
                "ランキング点",
                "AI判断点",
                "PHOENIX_SCORE",
                "期待勝率%",
                "期待騰落率%",
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
                f"{safe_float(row['ランキング点']):.2f}点\n"
            )

            file.write(
                f"監視区分: "
                f"{row['監視区分']}\n"
            )

            file.write(
                f"AI判断: "
                f"{row['AI判断']} "
                f"{safe_int(row['AI判断点'])}点\n"
            )

            file.write(
                f"PHOENIX SCORE: "
                f"{safe_int(row['PHOENIX_SCORE'])}点\n"
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
                f"価格: "
                f"{safe_float(row['価格']):,.2f}円\n"
            )

            file.write(
                f"RSI: "
                f"{safe_float(row['RSI']):.2f} "
                f"MACD: "
                f"{row['MACD判定']}\n"
            )

            file.write(
                f"根拠: "
                f"{row['ランキング根拠']}\n"
            )

            file.write(
                f"学習: "
                f"{row['学習根拠']}\n"
            )

            file.write(
                "-" * 100
                + "\n"
            )


def print_ranking(
    ranking_df: pd.DataFrame,
    profile: dict[str, Any],
    paper_summary: dict[str, Any],
) -> None:
    print()
    print("=" * 110)
    print("PHOENIX RANKING AI")
    print("=" * 110)

    generated_at = profile.get(
        "generated_at",
        "未読込",
    )

    print(
        f"AI判断ファイル       : "
        f"{AI_FILE}"
    )

    print(
        f"自己学習プロフィール : "
        f"{generated_at}"
    )

    paper_closed = safe_int(
        paper_summary.get(
            "決済済み",
            0,
        )
    )

    print(
        f"ペーパー決済件数     : "
        f"{paper_closed}"
    )

    print(
        f"ランキング対象数     : "
        f"{len(ranking_df)}"
    )

    print()
    print("=" * 110)
    print("監視優先ランキング")
    print("=" * 110)

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
        "期待勝率%",
        "期待騰落率%",
        "リスク",
    ]

    print(
        ranking_df[
            display_columns
        ].to_string(
            index=False
        )
    )

    print()
    print("=" * 110)
    print("TOP10 判断詳細")
    print("=" * 110)

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
            f"{safe_float(row['ランキング点']):.2f}点 / "
            f"{row['監視区分']}"
        )

        print(
            f"AI判断: "
            f"{row['AI判断']} "
            f"{safe_int(row['AI判断点'])}点 / "
            f"PHOENIX "
            f"{safe_int(row['PHOENIX_SCORE'])}点"
        )

        print(
            f"期待値: "
            f"勝率 "
            f"{safe_float(row['期待勝率%']):.2f}% / "
            f"騰落率 "
            f"{safe_float(row['期待騰落率%']):+.4f}%"
        )

        print(
            f"根拠: "
            f"{row['ランキング根拠']}"
        )

        print(
            f"学習: "
            f"{row['学習根拠']}"
        )

    print()
    print(
        f"保存完了 : "
        f"{RANKING_FILE}"
    )

    print(
        f"保存完了 : "
        f"{RANKING_TEXT_FILE}"
    )


def main() -> None:
    configure_console()

    print("=" * 110)
    print("PHOENIX RANKING AI ENGINE")
    print("=" * 110)

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