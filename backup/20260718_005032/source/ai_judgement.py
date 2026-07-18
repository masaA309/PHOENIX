# ai_judgement.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd


# =========================================================
# 設定
# =========================================================

REPORT_DIR = Path("reports")

OUTPUT_FILE = (
    REPORT_DIR
    / "ai_judgement.csv"
)

TEXT_OUTPUT_FILE = (
    REPORT_DIR
    / "ai_judgement.txt"
)

LEARNING_PROFILE_FILE = (
    REPORT_DIR
    / "learning_profile.json"
)

OPTIMIZED_FILE = (
    REPORT_DIR
    / "optimized_signals.csv"
)

TOP_STOCKS = 20
MIN_LEARNING_SAMPLES = 30


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
        if pd.isna(value):
            return default

        return int(
            float(value)
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def score_bucket(
    value: Any,
) -> str:
    score = safe_float(value)

    lower = int(
        math.floor(score / 5) * 5
    )

    return f"{lower}-{lower + 4}"


def rsi_bucket(
    value: Any,
) -> str:
    rsi = safe_float(value)

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
    volume = safe_float(value)

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


# =========================================================
# レポート読込
# =========================================================

def get_latest_report_file() -> Path:
    report_files = sorted(
        REPORT_DIR.glob(
            "report_*.csv"
        ),
        key=lambda path:
            path.stat().st_mtime,
        reverse=True,
    )

    if not report_files:
        raise FileNotFoundError(
            "reportsフォルダに"
            "report_*.csvがありません。"
        )

    return report_files[0]


def load_report() -> tuple[
    pd.DataFrame,
    Path,
]:
    report_file = (
        get_latest_report_file()
    )

    df = pd.read_csv(
        report_file
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
        "理由",
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
        "前日比%",
        "出来高倍率",
        "RSI",
        "PHOENIX_SCORE",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["MACD判定"] = (
        df["MACD判定"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df = (
        df.dropna(
            subset=numeric_columns
        )
        .sort_values(
            by=[
                "PHOENIX_SCORE",
                "出来高倍率",
                "前日比%",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .head(TOP_STOCKS)
        .reset_index(drop=True)
    )

    return df, report_file


def load_optimized_tickers() -> set[str]:
    if not OPTIMIZED_FILE.exists():
        return set()

    try:
        df = pd.read_csv(
            OPTIMIZED_FILE
        )

        if "ticker" not in df.columns:
            return set()

        return set(
            df["ticker"]
            .dropna()
            .astype(str)
            .str.strip()
        )

    except Exception:
        return set()


def load_learning_profile() -> dict[str, Any]:
    if not LEARNING_PROFILE_FILE.exists():
        return {
            "generated_at": "",
            "groups": {},
        }

    try:
        with open(
            LEARNING_PROFILE_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            profile = json.load(
                file
            )

        if not isinstance(
            profile,
            dict,
        ):
            return {
                "generated_at": "",
                "groups": {},
            }

        return profile

    except Exception as error:
        print(
            f"学習プロフィール読込エラー: "
            f"{error}"
        )

        return {
            "generated_at": "",
            "groups": {},
        }


# =========================================================
# 自己学習ボーナス
# =========================================================

def calculate_group_bonus(
    group_data: dict[str, Any] | None,
) -> tuple[int, str]:
    if not group_data:
        return 0, ""

    sample_count = safe_int(
        group_data.get(
            "sample_count",
            0,
        )
    )

    if sample_count < MIN_LEARNING_SAMPLES:
        return 0, ""

    win_rate = safe_float(
        group_data.get(
            "win_rate",
            50,
        )
    )

    average_return = safe_float(
        group_data.get(
            "average_return",
            0,
        )
    )

    profit_factor = safe_float(
        group_data.get(
            "profit_factor",
            1,
        )
    )

    evaluation = safe_float(
        group_data.get(
            "evaluation",
            0,
        )
    )

    bonus = int(
        round(
            max(
                min(
                    evaluation,
                    12,
                ),
                -12,
            )
        )
    )

    description = (
        f"過去{sample_count}件"
        f"・勝率{win_rate:.1f}%"
        f"・平均{average_return:+.3f}%"
        f"・PF{profit_factor:.2f}"
    )

    return bonus, description


def calculate_learning_adjustment(
    row: pd.Series,
    profile: dict[str, Any],
) -> tuple[
    int,
    list[str],
]:
    groups = profile.get(
        "groups",
        {}
    )

    if not isinstance(
        groups,
        dict,
    ):
        return 0, []

    phoenix_score = safe_float(
        row["PHOENIX_SCORE"]
    )

    rsi = safe_float(
        row["RSI"]
    )

    volume_ratio = safe_float(
        row["出来高倍率"]
    )

    macd = str(
        row["MACD判定"]
    ).upper()

    conditions = [
        (
            "score",
            score_bucket(
                phoenix_score
            ),
            "スコア帯",
        ),
        (
            "rsi",
            rsi_bucket(
                rsi
            ),
            "RSI帯",
        ),
        (
            "macd",
            macd,
            "MACD",
        ),
        (
            "volume",
            volume_bucket(
                volume_ratio
            ),
            "出来高帯",
        ),
    ]

    total_bonus = 0
    explanations = []

    for (
        group_type,
        condition,
        label,
    ) in conditions:
        group_type_data = groups.get(
            group_type,
            {}
        )

        if not isinstance(
            group_type_data,
            dict,
        ):
            continue

        group_data = group_type_data.get(
            condition
        )

        bonus, description = (
            calculate_group_bonus(
                group_data
            )
        )

        if bonus == 0:
            continue

        total_bonus += bonus

        sign = (
            "+"
            if bonus > 0
            else ""
        )

        explanations.append(
            f"{label}{condition}: "
            f"{sign}{bonus}点 "
            f"({description})"
        )

    combination_parts = [
        score_bucket(
            phoenix_score
        ),
        rsi_bucket(
            rsi
        ),
        macd,
        volume_bucket(
            volume_ratio
        ),
    ]

    combination_key = (
        " | ".join(
            combination_parts
        )
    )

    combination_groups = groups.get(
        "combination",
        {}
    )

    if isinstance(
        combination_groups,
        dict,
    ):
        combination_data = (
            combination_groups.get(
                combination_key
            )
        )

        bonus, description = (
            calculate_group_bonus(
                combination_data
            )
        )

        if bonus != 0:
            combination_bonus = int(
                round(
                    bonus * 1.5
                )
            )

            total_bonus += (
                combination_bonus
            )

            sign = (
                "+"
                if combination_bonus > 0
                else ""
            )

            explanations.append(
                "複合条件: "
                f"{sign}{combination_bonus}点 "
                f"({description})"
            )

    total_bonus = max(
        min(
            total_bonus,
            20,
        ),
        -20,
    )

    return (
        total_bonus,
        explanations,
    )


# =========================================================
# リスク
# =========================================================

def calculate_risk(
    change: float,
    volume_ratio: float,
    rsi: float,
) -> tuple[
    str,
    int,
    list[str],
]:
    score = 0
    reasons = []

    if rsi >= 85:
        score += 35
        reasons.append(
            f"RSI {rsi:.2f}で極端な過熱"
        )

    elif rsi >= 75:
        score += 20
        reasons.append(
            f"RSI {rsi:.2f}で過熱"
        )

    elif rsi <= 25:
        score += 25
        reasons.append(
            f"RSI {rsi:.2f}で極端な売られすぎ"
        )

    if change >= 8:
        score += 30
        reasons.append(
            f"前日比 {change:+.2f}%の急騰"
        )

    elif change >= 5:
        score += 20
        reasons.append(
            f"前日比 {change:+.2f}%の大幅上昇"
        )

    elif change <= -5:
        score += 20
        reasons.append(
            f"前日比 {change:+.2f}%の大幅下落"
        )

    if volume_ratio >= 5:
        score += 20
        reasons.append(
            f"出来高 {volume_ratio:.2f}倍"
        )

    elif volume_ratio >= 3:
        score += 10
        reasons.append(
            f"出来高 {volume_ratio:.2f}倍"
        )

    score = min(
        score,
        100,
    )

    if score >= 60:
        level = "高"

    elif score >= 30:
        level = "中"

    else:
        level = "低"

    return (
        level,
        score,
        reasons,
    )


# =========================================================
# AI判断
# =========================================================

def make_judgement(
    row: pd.Series,
    optimized_tickers: set[str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    name = str(
        row["銘柄"]
    )

    ticker = str(
        row["ticker"]
    )

    price = safe_float(
        row["価格"]
    )

    change = safe_float(
        row["前日比%"]
    )

    volume_ratio = safe_float(
        row["出来高倍率"]
    )

    rsi = safe_float(
        row["RSI"]
    )

    phoenix_score = safe_int(
        row["PHOENIX_SCORE"]
    )

    macd = str(
        row["MACD判定"]
    ).upper()

    optimized_match = (
        ticker
        in optimized_tickers
    )

    base_score = 0
    positives = []
    cautions = []

    if phoenix_score >= 80:
        base_score += 35

    elif phoenix_score >= 70:
        base_score += 25

    elif phoenix_score >= 60:
        base_score += 15

    elif phoenix_score >= 55:
        base_score += 8

    positives.append(
        f"PHOENIX SCORE "
        f"{phoenix_score}点"
    )

    if 45 <= rsi <= 65:
        base_score += 15
        positives.append(
            f"RSI {rsi:.2f}は適正範囲"
        )

    elif 35 <= rsi < 45:
        base_score += 7
        positives.append(
            f"RSI {rsi:.2f}は反発余地"
        )

    elif 65 < rsi <= 75:
        base_score += 5
        cautions.append(
            f"RSI {rsi:.2f}はやや過熱"
        )

    elif rsi > 75:
        base_score -= 20
        cautions.append(
            f"RSI {rsi:.2f}は過熱"
        )

    if macd == "BUY":
        base_score += 15
        positives.append(
            "MACD BUY"
        )

    else:
        base_score -= 5
        cautions.append(
            "MACD SELL"
        )

    if 1.2 <= volume_ratio < 2:
        base_score += 8
        positives.append(
            f"出来高 {volume_ratio:.2f}倍"
        )

    elif 2 <= volume_ratio < 4:
        base_score += 12
        positives.append(
            f"出来高 {volume_ratio:.2f}倍"
        )

    elif volume_ratio >= 4:
        base_score += 5
        cautions.append(
            f"出来高 {volume_ratio:.2f}倍"
        )

    if 0 < change <= 4:
        base_score += 10
        positives.append(
            f"前日比 {change:+.2f}%"
        )

    elif 4 < change <= 7:
        base_score += 5
        cautions.append(
            f"前日比 {change:+.2f}%"
            "で高値追い注意"
        )

    elif change > 7:
        base_score -= 15
        cautions.append(
            f"前日比 {change:+.2f}%"
            "で急騰後"
        )

    elif change < -5:
        base_score -= 20
        cautions.append(
            f"前日比 {change:+.2f}%"
            "で急落中"
        )

    if optimized_match:
        base_score += 20
        positives.append(
            "最適シグナル条件に一致"
        )

    (
        risk_level,
        risk_score,
        risk_reasons,
    ) = calculate_risk(
        change=change,
        volume_ratio=volume_ratio,
        rsi=rsi,
    )

    base_score -= int(
        risk_score * 0.25
    )

    (
        learning_bonus,
        learning_reasons,
    ) = calculate_learning_adjustment(
        row=row,
        profile=profile,
    )

    final_score = (
        base_score
        + learning_bonus
    )

    final_score = max(
        min(
            final_score,
            100,
        ),
        0,
    )

    if (
        optimized_match
        and final_score >= 55
    ):
        judgement = "優先監視"

    elif (
        final_score >= 70
        and risk_level != "高"
    ):
        judgement = "買い候補"

    elif final_score >= 50:
        judgement = "押し目待ち"

    elif final_score >= 30:
        judgement = "様子見"

    else:
        judgement = "見送り"

    if rsi >= 80 or change >= 8:
        timing = (
            "急騰直後のため追いかけず、"
            "押し目を待つ"
        )

    elif (
        macd == "BUY"
        and 45 <= rsi <= 70
        and change > 0
    ):
        timing = (
            "翌営業日の寄り付き後、"
            "値動きを確認"
        )

    elif optimized_match:
        timing = (
            "翌営業日の反発確認後に監視"
        )

    elif change < 0:
        timing = (
            "下げ止まり確認まで待機"
        )

    else:
        timing = (
            "出来高と株価の継続を確認"
        )

    if judgement in {
        "買い候補",
        "優先監視",
    }:
        target_price = round(
            price * 1.05,
            2,
        )

        stop_price = round(
            price * 0.97,
            2,
        )

    elif judgement == "押し目待ち":
        target_price = round(
            price * 1.04,
            2,
        )

        stop_price = round(
            price * 0.96,
            2,
        )

    else:
        target_price = None
        stop_price = None

    return {
        "銘柄": name,
        "ticker": ticker,
        "価格": round(
            price,
            2,
        ),
        "前日比%": round(
            change,
            2,
        ),
        "出来高倍率": round(
            volume_ratio,
            2,
        ),
        "RSI": round(
            rsi,
            2,
        ),
        "MACD判定": macd,
        "PHOENIX_SCORE": phoenix_score,
        "最適条件一致": optimized_match,
        "基本判断点": base_score,
        "学習補正点": learning_bonus,
        "AI判断点": final_score,
        "AI判断": judgement,
        "リスク": risk_level,
        "リスク点": risk_score,
        "監視タイミング": timing,
        "参考目標価格": target_price,
        "参考損切価格": stop_price,
        "プラス材料": " / ".join(
            positives
        ),
        "注意材料": " / ".join(
            cautions
            + risk_reasons
        ),
        "自己学習根拠": " / ".join(
            learning_reasons
        ),
        "PHOENIX理由": str(
            row["理由"]
        ),
    }


# =========================================================
# 作成・保存
# =========================================================

def create_judgements(
    report_df: pd.DataFrame,
    optimized_tickers: set[str],
    profile: dict[str, Any],
) -> pd.DataFrame:
    results = []

    for _, row in report_df.iterrows():
        results.append(
            make_judgement(
                row=row,
                optimized_tickers=(
                    optimized_tickers
                ),
                profile=profile,
            )
        )

    df = pd.DataFrame(
        results
    )

    order = {
        "優先監視": 0,
        "買い候補": 1,
        "押し目待ち": 2,
        "様子見": 3,
        "見送り": 4,
    }

    df["判断順"] = (
        df["AI判断"]
        .map(order)
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
        .drop(
            columns=[
                "判断順",
            ]
        )
        .reset_index(drop=True)
    )


def print_results(
    df: pd.DataFrame,
) -> None:
    print()
    print("=" * 110)
    print("PHOENIX SELF LEARNING AI JUDGEMENT")
    print("=" * 110)

    display_columns = [
        "銘柄",
        "ticker",
        "価格",
        "PHOENIX_SCORE",
        "基本判断点",
        "学習補正点",
        "AI判断点",
        "AI判断",
        "リスク",
    ]

    print(
        df[
            display_columns
        ].to_string(
            index=False
        )
    )

    print()
    print("=" * 110)
    print("自己学習判断詳細 TOP10")
    print("=" * 110)

    for number, row in df.head(
        10
    ).iterrows():
        print()
        print(
            f"[{number + 1}] "
            f"{row['銘柄']} "
            f"({row['ticker']})"
        )

        print(
            f"判断: {row['AI判断']} "
            f"/ 基本 {row['基本判断点']}点 "
            f"/ 学習補正 "
            f"{row['学習補正点']:+d}点 "
            f"/ 最終 {row['AI判断点']}点"
        )

        if row["自己学習根拠"]:
            print(
                "自己学習根拠: "
                f"{row['自己学習根拠']}"
            )

        print(
            "監視タイミング: "
            f"{row['監視タイミング']}"
        )


def save_results(
    df: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    with open(
        TEXT_OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(
            "PHOENIX SELF LEARNING "
            "AI JUDGEMENT\n"
        )

        file.write(
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        file.write(
            "\n\n"
        )

        for number, row in df.iterrows():
            file.write(
                f"[{number + 1}] "
                f"{row['銘柄']} "
                f"({row['ticker']})\n"
            )

            file.write(
                f"AI判断: "
                f"{row['AI判断']}\n"
            )

            file.write(
                f"基本判断点: "
                f"{row['基本判断点']}\n"
            )

            file.write(
                f"学習補正点: "
                f"{row['学習補正点']:+d}\n"
            )

            file.write(
                f"最終判断点: "
                f"{row['AI判断点']}\n"
            )

            file.write(
                f"自己学習根拠: "
                f"{row['自己学習根拠']}\n"
            )

            file.write(
                f"監視タイミング: "
                f"{row['監視タイミング']}\n"
            )

            file.write(
                "-" * 80
                + "\n"
            )

    print()
    print(
        f"保存完了 : {OUTPUT_FILE}"
    )

    print(
        f"保存完了 : "
        f"{TEXT_OUTPUT_FILE}"
    )


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()

    print("=" * 110)
    print("PHOENIX SELF LEARNING AI")
    print("=" * 110)

    try:
        report_df, report_file = (
            load_report()
        )

        optimized_tickers = (
            load_optimized_tickers()
        )

        profile = (
            load_learning_profile()
        )

        print(
            f"使用レポート : "
            f"{report_file}"
        )

        print(
            f"判断対象銘柄数 : "
            f"{len(report_df)}"
        )

        generated_at = profile.get(
            "generated_at",
            ""
        )

        if generated_at:
            print(
                "自己学習プロフィール : "
                f"{generated_at}"
            )

        else:
            print(
                "自己学習プロフィールなし "
                "（基本判断のみ使用）"
            )

        result_df = create_judgements(
            report_df=report_df,
            optimized_tickers=(
                optimized_tickers
            ),
            profile=profile,
        )

        print_results(
            result_df
        )

        save_results(
            result_df
        )

    except Exception as error:
        print(
            f"エラー: {error}"
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()