# learning_engine.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import numpy as np
import pandas as pd


REPORT_DIR = Path("reports")

BACKTEST_FILE = REPORT_DIR / "backtest_all.csv"
PAPER_FILE = REPORT_DIR / "paper_learning_data.csv"

PROFILE_JSON_FILE = REPORT_DIR / "learning_profile.json"
PROFILE_CSV_FILE = REPORT_DIR / "learning_profile.csv"
EVIDENCE_CSV_FILE = REPORT_DIR / "learning_evidence.csv"

MIN_SAMPLE_COUNT = 30

BACKTEST_WEIGHT = 1.0
PAPER_WEIGHT = 5.0

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

PAPER_RETURN_COLUMN_CANDIDATES = [
    "損益率%",
    "return",
    "return_pct",
]

PAPER_SCORE_COLUMN_CANDIDATES = [
    "PHOENIX_SCORE",
    "AI判断点",
    "score",
]

RETURN_COL = "学習リターン%"
SCORE_COL = "学習スコア"
RSI_COL = "学習RSI"
MACD_COL = "学習MACD"
VOLUME_COL = "学習出来高倍率"
SOURCE_COL = "学習ソース"
WEIGHT_COL = "学習重み"


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

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_round(
    value: Any,
    digits: int = 4,
) -> float:
    return round(
        safe_float(value),
        digits,
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


def normalize_macd(
    value: Any,
) -> str:
    text = str(value).upper().strip()

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

    if text:
        return text

    return "NEUTRAL"


def normalize_return_percent(
    values: pd.Series,
    column_name: str,
) -> pd.Series:
    result = pd.to_numeric(
        values,
        errors="coerce",
    )

    valid = result.dropna()

    if valid.empty:
        return result

    is_percent_column = (
        "%" in column_name
        or "率" in column_name
    )

    if not is_percent_column:
        percentile_95 = safe_float(
            valid.abs().quantile(0.95)
        )

        if percentile_95 <= 1.5:
            result = result * 100.0

    return result.clip(
        lower=-50.0,
        upper=50.0,
    )


def load_backtest() -> tuple[
    pd.DataFrame,
    dict[str, str | None],
]:
    if not BACKTEST_FILE.exists():
        raise FileNotFoundError(
            f"バックテスト結果がありません: "
            f"{BACKTEST_FILE}"
        )

    df = read_csv_safe(
        BACKTEST_FILE
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
            "バックテストに騰落率列がありません。"
        )

    if score_column is None:
        raise ValueError(
            "バックテストにスコア列がありません。"
        )

    result = pd.DataFrame(
        index=df.index
    )

    result[RETURN_COL] = (
        normalize_return_percent(
            df[return_column],
            return_column,
        )
    )

    result[SCORE_COL] = pd.to_numeric(
        df[score_column],
        errors="coerce",
    )

    if rsi_column is not None:
        result[RSI_COL] = pd.to_numeric(
            df[rsi_column],
            errors="coerce",
        )

    else:
        result[RSI_COL] = np.nan

    if macd_column is not None:
        result[MACD_COL] = df[
            macd_column
        ].map(
            normalize_macd
        )

    else:
        result[MACD_COL] = pd.NA

    if volume_column is not None:
        result[VOLUME_COL] = pd.to_numeric(
            df[volume_column],
            errors="coerce",
        )

    else:
        result[VOLUME_COL] = np.nan

    result[SOURCE_COL] = "backtest"
    result[WEIGHT_COL] = BACKTEST_WEIGHT

    ticker_column = find_column(
        df,
        [
            "ticker",
            "Ticker",
            "コード",
        ],
    )

    name_column = find_column(
        df,
        [
            "銘柄",
            "name",
            "銘柄名",
        ],
    )

    if ticker_column is not None:
        result["ticker"] = df[
            ticker_column
        ].astype(str)

    else:
        result["ticker"] = ""

    if name_column is not None:
        result["銘柄"] = df[
            name_column
        ].astype(str)

    else:
        result["銘柄"] = ""

    result = result.dropna(
        subset=[
            RETURN_COL,
            SCORE_COL,
        ]
    ).reset_index(
        drop=True
    )

    columns = {
        "return": return_column,
        "score": score_column,
        "rsi": rsi_column,
        "macd": macd_column,
        "volume": volume_column,
    }

    return (
        result,
        columns,
    )


def load_paper_learning() -> pd.DataFrame:
    if not PAPER_FILE.exists():
        return pd.DataFrame()

    df = read_csv_safe(
        PAPER_FILE
    )

    if df.empty:
        return pd.DataFrame()

    return_column = find_column(
        df,
        PAPER_RETURN_COLUMN_CANDIDATES,
    )

    score_column = find_column(
        df,
        PAPER_SCORE_COLUMN_CANDIDATES,
    )

    rsi_column = find_column(
        df,
        RSI_COLUMN_CANDIDATES,
    )

    macd_column = find_column(
        df,
        MACD_COLUMN_CANDIDATES,
    )

    if (
        return_column is None
        or score_column is None
    ):
        print(
            "ペーパー学習データに必要な列がないため、"
            "今回はバックテストのみ使用します。"
        )

        return pd.DataFrame()

    if "結果" in df.columns:
        df = df[
            df["結果"]
            .astype(str)
            .isin(
                [
                    "WIN",
                    "LOSS",
                    "DRAW",
                ]
            )
        ].copy()

    result = pd.DataFrame(
        index=df.index
    )

    result[RETURN_COL] = (
        normalize_return_percent(
            df[return_column],
            return_column,
        )
    )

    result[SCORE_COL] = pd.to_numeric(
        df[score_column],
        errors="coerce",
    )

    if rsi_column is not None:
        result[RSI_COL] = pd.to_numeric(
            df[rsi_column],
            errors="coerce",
        )

    else:
        result[RSI_COL] = np.nan

    if macd_column is not None:
        result[MACD_COL] = df[
            macd_column
        ].map(
            normalize_macd
        )

    else:
        result[MACD_COL] = pd.NA

    result[VOLUME_COL] = np.nan
    result[SOURCE_COL] = "paper"
    result[WEIGHT_COL] = PAPER_WEIGHT

    if "ticker" in df.columns:
        result["ticker"] = df[
            "ticker"
        ].astype(str)

    else:
        result["ticker"] = ""

    if "銘柄" in df.columns:
        result["銘柄"] = df[
            "銘柄"
        ].astype(str)

    else:
        result["銘柄"] = ""

    return (
        result.dropna(
            subset=[
                RETURN_COL,
                SCORE_COL,
            ]
        )
        .reset_index(
            drop=True
        )
    )


def score_bucket(
    value: Any,
) -> str:
    score = safe_float(value)

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


def weighted_average(
    values: pd.Series,
    weights: pd.Series,
) -> float:
    numeric_values = pd.to_numeric(
        values,
        errors="coerce",
    )

    numeric_weights = pd.to_numeric(
        weights,
        errors="coerce",
    )

    valid = (
        numeric_values.notna()
        & numeric_weights.notna()
        & (
            numeric_weights > 0
        )
    )

    if not valid.any():
        return 0.0

    return float(
        np.average(
            numeric_values[valid],
            weights=numeric_weights[
                valid
            ],
        )
    )


def calculate_evaluation_score(
    effective_sample_count: float,
    win_rate: float,
    average_return: float,
    profit_factor: float,
) -> float:
    sample_reliability = min(
        effective_sample_count / 300.0,
        1.0,
    )

    win_component = (
        win_rate - 50.0
    ) * 0.8

    return_component = (
        average_return * 15.0
    )

    capped_pf = min(
        max(
            profit_factor,
            0.0,
        ),
        5.0,
    )

    pf_component = (
        capped_pf - 1.0
    ) * 12.0

    return (
        win_component
        + return_component
        + pf_component
    ) * sample_reliability


def empty_statistics() -> dict[str, Any]:
    return {
        "対象数": 0,
        "有効サンプル数": 0.0,
        "バックテスト件数": 0,
        "ペーパー件数": 0,
        "勝率%": 0.0,
        "平均騰落率%": 0.0,
        "中央値%": 0.0,
        "平均利益%": 0.0,
        "平均損失%": 0.0,
        "PF": 0.0,
        "期待値評価": 0.0,
        "ペーパー勝率%": 0.0,
        "ペーパー平均損益率%": 0.0,
    }


def calculate_statistics(
    group_df: pd.DataFrame,
) -> dict[str, Any]:
    if group_df.empty:
        return empty_statistics()

    work = group_df.copy()

    work[RETURN_COL] = pd.to_numeric(
        work[RETURN_COL],
        errors="coerce",
    )

    work[WEIGHT_COL] = pd.to_numeric(
        work[WEIGHT_COL],
        errors="coerce",
    )

    work = work.dropna(
        subset=[
            RETURN_COL,
            WEIGHT_COL,
        ]
    )

    work = work[
        work[WEIGHT_COL] > 0
    ].copy()

    if work.empty:
        return empty_statistics()

    values = work[
        RETURN_COL
    ]

    weights = work[
        WEIGHT_COL
    ]

    sample_count = len(work)

    effective_sample_count = safe_float(
        weights.sum()
    )

    win_rate = (
        weighted_average(
            (
                values > 0
            ).astype(float),
            weights,
        )
        * 100.0
    )

    average_return = weighted_average(
        values,
        weights,
    )

    median_return = safe_float(
        values.median()
    )

    wins = work[
        work[RETURN_COL] > 0
    ]

    losses = work[
        work[RETURN_COL] < 0
    ]

    if not wins.empty:
        average_profit = (
            weighted_average(
                wins[RETURN_COL],
                wins[WEIGHT_COL],
            )
        )

    else:
        average_profit = 0.0

    if not losses.empty:
        average_loss = (
            weighted_average(
                losses[RETURN_COL],
                losses[WEIGHT_COL],
            )
        )

    else:
        average_loss = 0.0

    if not wins.empty:
        total_profit = safe_float(
            (
                wins[RETURN_COL]
                * wins[WEIGHT_COL]
            ).sum()
        )

    else:
        total_profit = 0.0

    if not losses.empty:
        total_loss = abs(
            safe_float(
                (
                    losses[RETURN_COL]
                    * losses[WEIGHT_COL]
                ).sum()
            )
        )

    else:
        total_loss = 0.0

    if total_loss > 0:
        profit_factor = (
            total_profit
            / total_loss
        )

    elif total_profit > 0:
        profit_factor = 99.0

    else:
        profit_factor = 0.0

    evaluation = (
        calculate_evaluation_score(
            effective_sample_count=(
                effective_sample_count
            ),
            win_rate=win_rate,
            average_return=average_return,
            profit_factor=profit_factor,
        )
    )

    backtest_df = work[
        work[SOURCE_COL]
        == "backtest"
    ]

    paper_df = work[
        work[SOURCE_COL]
        == "paper"
    ]

    paper_win_rate = 0.0
    paper_average_return = 0.0

    if not paper_df.empty:
        paper_values = paper_df[
            RETURN_COL
        ]

        paper_win_rate = safe_float(
            (
                paper_values > 0
            ).mean()
            * 100.0
        )

        paper_average_return = safe_float(
            paper_values.mean()
        )

    return {
        "対象数": int(
            sample_count
        ),
        "有効サンプル数": safe_round(
            effective_sample_count,
            2,
        ),
        "バックテスト件数": int(
            len(backtest_df)
        ),
        "ペーパー件数": int(
            len(paper_df)
        ),
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
        "ペーパー勝率%": safe_round(
            paper_win_rate,
            2,
        ),
        "ペーパー平均損益率%": safe_round(
            paper_average_return,
            4,
        ),
    }


def build_group_statistics(
    df: pd.DataFrame,
    group_column: str,
    group_type: str,
) -> list[dict[str, Any]]:
    results: list[
        dict[str, Any]
    ] = []

    grouped = df.groupby(
        group_column,
        dropna=False,
    )

    for group_name, group_df in grouped:
        results.append({
            "分類": group_type,
            "条件": str(
                group_name
            ),
            **calculate_statistics(
                group_df
            ),
        })

    return results


def build_learning_profile(
    evidence_df: pd.DataFrame,
    backtest_columns: dict[
        str,
        str | None,
    ],
) -> tuple[
    dict[str, Any],
    pd.DataFrame,
]:
    work = evidence_df.copy()

    work["スコア帯"] = work[
        SCORE_COL
    ].apply(
        score_bucket
    )

    profile_rows: list[
        dict[str, Any]
    ] = []

    profile_rows.extend(
        build_group_statistics(
            df=work,
            group_column="スコア帯",
            group_type="score",
        )
    )

    rsi_work = work.dropna(
        subset=[
            RSI_COL,
        ]
    ).copy()

    if not rsi_work.empty:
        rsi_work["RSI帯"] = rsi_work[
            RSI_COL
        ].apply(
            rsi_bucket
        )

        profile_rows.extend(
            build_group_statistics(
                df=rsi_work,
                group_column="RSI帯",
                group_type="rsi",
            )
        )

    macd_work = work.dropna(
        subset=[
            MACD_COL,
        ]
    ).copy()

    if not macd_work.empty:
        profile_rows.extend(
            build_group_statistics(
                df=macd_work,
                group_column=MACD_COL,
                group_type="macd",
            )
        )

    volume_work = work.dropna(
        subset=[
            VOLUME_COL,
        ]
    ).copy()

    if not volume_work.empty:
        volume_work["出来高帯"] = (
            volume_work[
                VOLUME_COL
            ].apply(
                volume_bucket
            )
        )

        profile_rows.extend(
            build_group_statistics(
                df=volume_work,
                group_column="出来高帯",
                group_type="volume",
            )
        )

    combination_work = work.dropna(
        subset=[
            RSI_COL,
            MACD_COL,
            VOLUME_COL,
        ]
    ).copy()

    if not combination_work.empty:
        combination_work[
            "スコア帯"
        ] = combination_work[
            SCORE_COL
        ].apply(
            score_bucket
        )

        combination_work[
            "RSI帯"
        ] = combination_work[
            RSI_COL
        ].apply(
            rsi_bucket
        )

        combination_work[
            "出来高帯"
        ] = combination_work[
            VOLUME_COL
        ].apply(
            volume_bucket
        )

        combination_work[
            "複合条件"
        ] = (
            combination_work[
                [
                    "スコア帯",
                    "RSI帯",
                    MACD_COL,
                    "出来高帯",
                ]
            ]
            .astype(str)
            .agg(
                " | ".join,
                axis=1,
            )
        )

        combination_rows = (
            build_group_statistics(
                df=combination_work,
                group_column="複合条件",
                group_type="combination",
            )
        )

        profile_rows.extend(
            row
            for row
            in combination_rows
            if int(
                row["対象数"]
            )
            >= MIN_SAMPLE_COUNT
        )

    profile_df = pd.DataFrame(
        profile_rows
    )

    profile_df = (
        profile_df.sort_values(
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
        )
        .reset_index(
            drop=True
        )
    )

    overall_stats = (
        calculate_statistics(
            work
        )
    )

    profile: dict[str, Any] = {
        "generated_at": (
            datetime.now().isoformat(
                timespec="seconds"
            )
        ),
        "source_file": str(
            BACKTEST_FILE
        ),
        "source_files": {
            "backtest": str(
                BACKTEST_FILE
            ),
            "paper": str(
                PAPER_FILE
            ),
        },
        "source_counts": {
            "backtest": int(
                (
                    work[SOURCE_COL]
                    == "backtest"
                ).sum()
            ),
            "paper": int(
                (
                    work[SOURCE_COL]
                    == "paper"
                ).sum()
            ),
        },
        "weights": {
            "backtest": (
                BACKTEST_WEIGHT
            ),
            "paper": (
                PAPER_WEIGHT
            ),
        },
        "minimum_sample_count": (
            MIN_SAMPLE_COUNT
        ),
        "overall": overall_stats,
        "columns": (
            backtest_columns
        ),
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

        profile["groups"][
            group_type
        ][condition] = {
            "sample_count": int(
                row["対象数"]
            ),
            "effective_sample_count": (
                safe_float(
                    row[
                        "有効サンプル数"
                    ]
                )
            ),
            "backtest_count": int(
                row[
                    "バックテスト件数"
                ]
            ),
            "paper_count": int(
                row[
                    "ペーパー件数"
                ]
            ),
            "win_rate": safe_float(
                row["勝率%"]
            ),
            "average_return": (
                safe_float(
                    row[
                        "平均騰落率%"
                    ]
                )
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
            "paper_win_rate": (
                safe_float(
                    row[
                        "ペーパー勝率%"
                    ]
                )
            ),
            "paper_average_return": (
                safe_float(
                    row[
                        "ペーパー平均損益率%"
                    ]
                )
            ),
        }

    return (
        profile,
        profile_df,
    )


def save_profile(
    profile: dict[str, Any],
    profile_df: pd.DataFrame,
    evidence_df: pd.DataFrame,
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        PROFILE_JSON_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
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

    evidence_columns = [
        SOURCE_COL,
        WEIGHT_COL,
        "ticker",
        "銘柄",
        SCORE_COL,
        RSI_COL,
        MACD_COL,
        VOLUME_COL,
        RETURN_COL,
    ]

    evidence_df[
        evidence_columns
    ].to_csv(
        EVIDENCE_CSV_FILE,
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

    counts = profile[
        "source_counts"
    ]

    print()
    print("=" * 90)
    print("PHOENIX LEARNING RESULT")
    print("=" * 90)

    print(
        f"バックテスト件数 : "
        f"{counts['backtest']:,}"
    )

    print(
        f"ペーパー取引件数 : "
        f"{counts['paper']:,}"
    )

    print(
        f"統合学習対象数   : "
        f"{overall['対象数']:,}"
    )

    print(
        f"統合勝率         : "
        f"{overall['勝率%']:.2f}%"
    )

    print(
        f"統合平均騰落率   : "
        f"{overall['平均騰落率%']:+.4f}%"
    )

    print(
        f"統合PF           : "
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
                    "ペーパー件数",
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
        f"保存完了 : "
        f"{PROFILE_JSON_FILE}"
    )

    print(
        f"保存完了 : "
        f"{PROFILE_CSV_FILE}"
    )

    print(
        f"保存完了 : "
        f"{EVIDENCE_CSV_FILE}"
    )


def main() -> None:
    configure_console()

    print("=" * 90)
    print("PHOENIX SELF LEARNING ENGINE v2.1")
    print("=" * 90)

    try:
        backtest_df, columns = (
            load_backtest()
        )

        paper_df = (
            load_paper_learning()
        )

        evidence_frames = [
            backtest_df
        ]

        if not paper_df.empty:
            evidence_frames.append(
                paper_df
            )

        evidence_df = pd.concat(
            evidence_frames,
            ignore_index=True,
        )

        print(
            f"使用ファイル : "
            f"{BACKTEST_FILE}"
        )

        print(
            f"バックテスト件数 : "
            f"{len(backtest_df):,}"
        )

        print(
            f"ペーパー取引件数 : "
            f"{len(paper_df):,}"
        )

        profile, profile_df = (
            build_learning_profile(
                evidence_df=evidence_df,
                backtest_columns=columns,
            )
        )

        save_profile(
            profile=profile,
            profile_df=profile_df,
            evidence_df=evidence_df,
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