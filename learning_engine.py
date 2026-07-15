# learning_engine.py

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

BACKTEST_FILE = (
    REPORT_DIR
    / "backtest_all.csv"
)

PROFILE_JSON_FILE = (
    REPORT_DIR
    / "learning_profile.json"
)

PROFILE_CSV_FILE = (
    REPORT_DIR
    / "learning_profile.csv"
)

MIN_SAMPLE_COUNT = 30

RETURN_COLUMN_CANDIDATES = [
    "翌日騰落率%",
    "return",
    "騰落率%",
    "翌日リターン%",
]

SCORE_COLUMN_CANDIDATES = [
    "score",
    "PHOENIX_SCORE",
]

RSI_COLUMN_CANDIDATES = [
    "RSI",
    "rsi",
]

MACD_COLUMN_CANDIDATES = [
    "MACD判定",
    "macd_judge",
    "MACD",
]

VOLUME_COLUMN_CANDIDATES = [
    "出来高倍率",
    "volume_ratio",
]


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


def find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    for column in candidates:
        if column in df.columns:
            return column

    return None


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


def safe_round(
    value: Any,
    digits: int = 4,
) -> float:
    number = safe_float(value)

    if not math.isfinite(number):
        return 0.0

    return round(
        number,
        digits,
    )


# =========================================================
# データ読込
# =========================================================

def load_backtest() -> tuple[
    pd.DataFrame,
    dict[str, str | None],
]:
    if not BACKTEST_FILE.exists():
        raise FileNotFoundError(
            f"バックテスト結果がありません: "
            f"{BACKTEST_FILE}"
        )

    df = pd.read_csv(
        BACKTEST_FILE,
    )

    return_column = find_column(
        df,
        RETURN_COLUMN_CANDIDATES,
    )

    score_column = find_column(
        df,
        SCORE_COLUMN_CANDIDATES,
    )

    rsi_column = find_column(
        df,
        RSI_COLUMN_CANDIDATES,
    )

    macd_column = find_column(
        df,
        MACD_COLUMN_CANDIDATES,
    )

    volume_column = find_column(
        df,
        VOLUME_COLUMN_CANDIDATES,
    )

    if return_column is None:
        raise ValueError(
            "騰落率列がありません。"
        )

    if score_column is None:
        raise ValueError(
            "スコア列がありません。"
        )

    df[return_column] = pd.to_numeric(
        df[return_column],
        errors="coerce",
    )

    df[score_column] = pd.to_numeric(
        df[score_column],
        errors="coerce",
    )

    if rsi_column is not None:
        df[rsi_column] = pd.to_numeric(
            df[rsi_column],
            errors="coerce",
        )

    if volume_column is not None:
        df[volume_column] = pd.to_numeric(
            df[volume_column],
            errors="coerce",
        )

    if macd_column is not None:
        df[macd_column] = (
            df[macd_column]
            .astype(str)
            .str.upper()
            .str.strip()
        )

    df = df.dropna(
        subset=[
            return_column,
            score_column,
        ],
    ).copy()

    if df.empty:
        raise ValueError(
            "有効なバックテスト結果がありません。"
        )

    columns = {
        "return": return_column,
        "score": score_column,
        "rsi": rsi_column,
        "macd": macd_column,
        "volume": volume_column,
    }

    return df, columns


# =========================================================
# 区分
# =========================================================

def score_bucket(
    value: Any,
) -> str:
    score = safe_float(value)

    lower = int(
        math.floor(score / 5) * 5
    )

    upper = lower + 4

    return f"{lower}-{upper}"


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
# 成績計算
# =========================================================

def calculate_statistics(
    returns: pd.Series,
) -> dict[str, Any]:
    values = pd.to_numeric(
        returns,
        errors="coerce",
    ).dropna()

    sample_count = len(values)

    if sample_count == 0:
        return {
            "対象数": 0,
            "勝率%": 0.0,
            "平均騰落率%": 0.0,
            "中央値%": 0.0,
            "平均利益%": 0.0,
            "平均損失%": 0.0,
            "PF": 0.0,
            "期待値評価": 0.0,
        }

    wins = values[
        values > 0
    ]

    losses = values[
        values < 0
    ]

    win_rate = (
        len(wins)
        / sample_count
        * 100
    )

    average_return = values.mean()
    median_return = values.median()

    average_profit = (
        wins.mean()
        if not wins.empty
        else 0.0
    )

    average_loss = (
        losses.mean()
        if not losses.empty
        else 0.0
    )

    total_profit = wins.sum()
    total_loss = abs(
        losses.sum()
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

    evaluation = calculate_evaluation_score(
        sample_count=sample_count,
        win_rate=win_rate,
        average_return=average_return,
        profit_factor=profit_factor,
    )

    return {
        "対象数": int(sample_count),
        "勝率%": safe_round(
            win_rate,
            2,
        ),
        "平均騰落率%": safe_round(
            average_return,
            4,
        ),
        "中央値%": safe_round(
            median_return,
            4,
        ),
        "平均利益%": safe_round(
            average_profit,
            4,
        ),
        "平均損失%": safe_round(
            average_loss,
            4,
        ),
        "PF": safe_round(
            profit_factor,
            3,
        ),
        "期待値評価": safe_round(
            evaluation,
            2,
        ),
    }


def calculate_evaluation_score(
    sample_count: int,
    win_rate: float,
    average_return: float,
    profit_factor: float,
) -> float:
    sample_reliability = min(
        sample_count / 300,
        1.0,
    )

    win_component = (
        win_rate - 50
    ) * 0.8

    return_component = (
        average_return
        * 15
    )

    pf_component = (
        profit_factor - 1
    ) * 12

    raw_score = (
        win_component
        + return_component
        + pf_component
    )

    return (
        raw_score
        * sample_reliability
    )


def build_group_statistics(
    df: pd.DataFrame,
    group_column: str,
    return_column: str,
    group_type: str,
) -> list[dict[str, Any]]:
    results = []

    grouped = df.groupby(
        group_column,
        dropna=False,
    )

    for group_name, group_df in grouped:
        stats = calculate_statistics(
            group_df[
                return_column
            ]
        )

        row = {
            "分類": group_type,
            "条件": str(group_name),
            **stats,
        }

        results.append(
            row
        )

    return results


# =========================================================
# 学習プロフィール
# =========================================================

def build_learning_profile(
    df: pd.DataFrame,
    columns: dict[str, str | None],
) -> tuple[
    dict[str, Any],
    pd.DataFrame,
]:
    return_column = str(
        columns["return"]
    )

    score_column = str(
        columns["score"]
    )

    work = df.copy()

    work["スコア帯"] = work[
        score_column
    ].apply(
        score_bucket
    )

    profile_rows = []

    profile_rows.extend(
        build_group_statistics(
            df=work,
            group_column="スコア帯",
            return_column=return_column,
            group_type="score",
        )
    )

    rsi_column = columns.get(
        "rsi"
    )

    if rsi_column is not None:
        work["RSI帯"] = work[
            rsi_column
        ].apply(
            rsi_bucket
        )

        profile_rows.extend(
            build_group_statistics(
                df=work,
                group_column="RSI帯",
                return_column=return_column,
                group_type="rsi",
            )
        )

    macd_column = columns.get(
        "macd"
    )

    if macd_column is not None:
        profile_rows.extend(
            build_group_statistics(
                df=work,
                group_column=macd_column,
                return_column=return_column,
                group_type="macd",
            )
        )

    volume_column = columns.get(
        "volume"
    )

    if volume_column is not None:
        work["出来高帯"] = work[
            volume_column
        ].apply(
            volume_bucket
        )

        profile_rows.extend(
            build_group_statistics(
                df=work,
                group_column="出来高帯",
                return_column=return_column,
                group_type="volume",
            )
        )

    exact_columns = [
        "スコア帯",
    ]

    if "RSI帯" in work.columns:
        exact_columns.append(
            "RSI帯"
        )

    if macd_column is not None:
        exact_columns.append(
            macd_column
        )

    if "出来高帯" in work.columns:
        exact_columns.append(
            "出来高帯"
        )

    if len(exact_columns) >= 3:
        work["複合条件"] = (
            work[
                exact_columns
            ]
            .astype(str)
            .agg(
                " | ".join,
                axis=1,
            )
        )

        combination_rows = (
            build_group_statistics(
                df=work,
                group_column="複合条件",
                return_column=return_column,
                group_type="combination",
            )
        )

        combination_rows = [
            row
            for row in combination_rows
            if int(
                row["対象数"]
            ) >= MIN_SAMPLE_COUNT
        ]

        profile_rows.extend(
            combination_rows
        )

    profile_df = pd.DataFrame(
        profile_rows
    )

    profile_df = profile_df.sort_values(
        by=[
            "分類",
            "期待値評価",
            "対象数",
        ],
        ascending=[
            True,
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    overall_stats = (
        calculate_statistics(
            work[
                return_column
            ]
        )
    )

    profile = {
        "generated_at": (
            datetime.now().isoformat(
                timespec="seconds",
            )
        ),
        "source_file": str(
            BACKTEST_FILE
        ),
        "minimum_sample_count": (
            MIN_SAMPLE_COUNT
        ),
        "overall": overall_stats,
        "columns": columns,
        "groups": {
            "score": {},
            "rsi": {},
            "macd": {},
            "volume": {},
            "combination": {},
        },
    }

    for row in profile_rows:
        group_type = str(
            row["分類"]
        )

        condition = str(
            row["条件"]
        )

        if group_type not in profile[
            "groups"
        ]:
            continue

        profile[
            "groups"
        ][group_type][condition] = {
            "sample_count": int(
                row["対象数"]
            ),
            "win_rate": safe_float(
                row["勝率%"]
            ),
            "average_return": safe_float(
                row["平均騰落率%"]
            ),
            "median_return": safe_float(
                row["中央値%"]
            ),
            "profit_factor": safe_float(
                row["PF"]
            ),
            "evaluation": safe_float(
                row["期待値評価"]
            ),
        }

    return (
        profile,
        profile_df,
    )


# =========================================================
# 保存・表示
# =========================================================

def save_profile(
    profile: dict[str, Any],
    profile_df: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        PROFILE_JSON_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            profile,
            file,
            ensure_ascii=False,
            indent=2,
        )

    profile_df.to_csv(
        PROFILE_CSV_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def print_summary(
    profile: dict[str, Any],
    profile_df: pd.DataFrame,
) -> None:
    overall = profile[
        "overall"
    ]

    print()
    print("=" * 90)
    print("PHOENIX LEARNING RESULT")
    print("=" * 90)

    print(
        f"学習対象数     : "
        f"{overall['対象数']}"
    )

    print(
        f"全体勝率       : "
        f"{overall['勝率%']:.2f}%"
    )

    print(
        f"全体平均騰落率 : "
        f"{overall['平均騰落率%']:.4f}%"
    )

    print(
        f"全体PF         : "
        f"{overall['PF']:.3f}"
    )

    print()
    print("=" * 90)
    print("期待値が高い条件 TOP20")
    print("=" * 90)

    display_df = (
        profile_df[
            profile_df["対象数"]
            >= MIN_SAMPLE_COUNT
        ]
        .sort_values(
            by=[
                "期待値評価",
                "対象数",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .head(20)
    )

    if display_df.empty:
        print(
            "十分なサンプル数を持つ条件がありません。"
        )

    else:
        print(
            display_df[
                [
                    "分類",
                    "条件",
                    "対象数",
                    "勝率%",
                    "平均騰落率%",
                    "PF",
                    "期待値評価",
                ]
            ].to_string(
                index=False
            )
        )

    print()
    print(
        f"保存完了 : {PROFILE_JSON_FILE}"
    )

    print(
        f"保存完了 : {PROFILE_CSV_FILE}"
    )


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()

    print("=" * 90)
    print("PHOENIX SELF LEARNING ENGINE")
    print("=" * 90)

    try:
        df, columns = load_backtest()

        print(
            f"使用ファイル : {BACKTEST_FILE}"
        )

        print(
            f"バックテスト件数 : {len(df)}"
        )

        profile, profile_df = (
            build_learning_profile(
                df=df,
                columns=columns,
            )
        )

        save_profile(
            profile=profile,
            profile_df=profile_df,
        )

        print_summary(
            profile=profile,
            profile_df=profile_df,
        )

    except Exception as error:
        print(
            f"エラー: {error}"
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()