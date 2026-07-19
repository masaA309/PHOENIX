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
# 基本設定
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"

LEARNING_SOURCE_FILE = REPORT_DIR / "paper_learning_data.csv"
LEARNING_REPORT_FILE = REPORT_DIR / "learning_report.csv"
PARAMETER_FILE = REPORT_DIR / "ai_parameter.json"
TEXT_REPORT_FILE = REPORT_DIR / "learning_engine_report.txt"

ACCOUNT_CAPITAL = 300_000

MIN_SAMPLE_FOR_ADJUSTMENT = 10
STRONG_SAMPLE_COUNT = 30
MAX_SCORE_ADJUSTMENT = 20
BASELINE_SCORE = 0

RSI_BINS = [
    (-math.inf, 29.9999, "RSI 30未満"),
    (30.0, 39.9999, "RSI 30-39"),
    (40.0, 49.9999, "RSI 40-49"),
    (50.0, 59.9999, "RSI 50-59"),
    (60.0, 69.9999, "RSI 60-69"),
    (70.0, math.inf, "RSI 70以上"),
]

AI_SCORE_BINS = [
    (-math.inf, 59.9999, "AI判断点 60未満"),
    (60.0, 69.9999, "AI判断点 60-69"),
    (70.0, 79.9999, "AI判断点 70-79"),
    (80.0, math.inf, "AI判断点 80以上"),
]

PHOENIX_SCORE_BINS = [
    (-math.inf, 59.9999, "PHOENIX_SCORE 60未満"),
    (60.0, 69.9999, "PHOENIX_SCORE 60-69"),
    (70.0, 79.9999, "PHOENIX_SCORE 70-79"),
    (80.0, math.inf, "PHOENIX_SCORE 80以上"),
]


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


def write_json(
    file_path: Path,
    data: dict[str, Any],
) -> None:
    with open(
        file_path,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 学習データ読込
# =========================================================

def create_empty_learning_source() -> pd.DataFrame:
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


def load_learning_source() -> pd.DataFrame:
    if not LEARNING_SOURCE_FILE.exists():
        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        empty = create_empty_learning_source()

        empty.to_csv(
            LEARNING_SOURCE_FILE,
            index=False,
            encoding="utf-8-sig",
        )

        return empty

    data = read_csv_safe(
        LEARNING_SOURCE_FILE
    )

    if data.empty:
        return create_empty_learning_source()

    required_columns = {
        "ticker",
        "銘柄",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
        "MACD判定",
        "損益率%",
        "結果",
        "決済理由",
    }

    missing_columns = (
        required_columns
        - set(data.columns)
    )

    if missing_columns:
        raise ValueError(
            "paper_learning_data.csv に必要な列がありません: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    numeric_columns = [
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
        "損益率%",
    ]

    for column in numeric_columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    data["ticker"] = (
        data["ticker"]
        .astype(str)
        .str.strip()
    )

    data["AI判断"] = (
        data["AI判断"]
        .astype(str)
        .str.strip()
    )

    data["MACD判定"] = (
        data["MACD判定"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    data["結果"] = (
        data["結果"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    data["決済理由"] = (
        data["決済理由"]
        .astype(str)
        .str.strip()
    )

    data = data.dropna(
        subset=[
            "ticker",
            "損益率%",
        ]
    )

    data = data[
        data["結果"].isin(
            [
                "WIN",
                "LOSS",
                "DRAW",
            ]
        )
    ].copy()

    data = data.drop_duplicates(
        subset=[
            "ticker",
            "エントリー日時",
            "決済日時",
        ],
        keep="last",
    )

    return data.reset_index(
        drop=True
    )


# =========================================================
# 統計
# =========================================================

def wilson_shrunk_win_rate(
    wins: int,
    total: int,
    prior_rate: float,
    prior_weight: int = 10,
) -> float:
    if total <= 0:
        return prior_rate

    return (
        wins
        + prior_rate * prior_weight
    ) / (
        total
        + prior_weight
    )


def sample_confidence(
    sample_count: int,
) -> float:
    if sample_count <= 0:
        return 0.0

    return min(
        sample_count
        / STRONG_SAMPLE_COUNT,
        1.0,
    )


def calculate_adjustment(
    win_rate: float,
    average_return: float,
    profit_factor: float,
    sample_count: int,
    baseline_win_rate: float,
) -> int:
    if sample_count < MIN_SAMPLE_FOR_ADJUSTMENT:
        return BASELINE_SCORE

    confidence = sample_confidence(
        sample_count
    )

    win_component = (
        win_rate
        - baseline_win_rate
    ) * 40.0

    return_component = max(
        min(
            average_return * 1.5,
            8.0,
        ),
        -8.0,
    )

    if profit_factor >= 2.0:
        pf_component = 4.0
    elif profit_factor >= 1.3:
        pf_component = 2.0
    elif profit_factor >= 1.0:
        pf_component = 0.0
    elif profit_factor > 0:
        pf_component = -3.0
    else:
        pf_component = -5.0

    raw_adjustment = (
        win_component
        + return_component
        + pf_component
    ) * confidence

    return int(
        max(
            min(
                round(raw_adjustment),
                MAX_SCORE_ADJUSTMENT,
            ),
            -MAX_SCORE_ADJUSTMENT,
        )
    )


def create_group_row(
    data: pd.DataFrame,
    category: str,
    condition: str,
    baseline_win_rate: float,
) -> dict[str, Any]:
    total = len(data)

    if total <= 0:
        return {
            "カテゴリ": category,
            "条件": condition,
            "取引数": 0,
            "勝ち": 0,
            "負け": 0,
            "引分": 0,
            "勝率%": 0.0,
            "補正勝率%": round(
                baseline_win_rate * 100,
                2,
            ),
            "平均損益率%": 0.0,
            "中央値損益率%": 0.0,
            "総損益率%": 0.0,
            "PF": 0.0,
            "信頼度%": 0.0,
            "AI点補正": 0,
            "判定": "データ不足",
        }

    returns = pd.to_numeric(
        data["損益率%"],
        errors="coerce",
    ).fillna(0.0)

    wins = int(
        (
            returns > 0
        ).sum()
    )

    losses = int(
        (
            returns < 0
        ).sum()
    )

    draws = total - wins - losses

    gross_profit = safe_float(
        returns[
            returns > 0
        ].sum()
    )

    gross_loss = abs(
        safe_float(
            returns[
                returns < 0
            ].sum()
        )
    )

    if gross_loss > 0:
        profit_factor = (
            gross_profit
            / gross_loss
        )
    elif gross_profit > 0:
        profit_factor = 99.0
    else:
        profit_factor = 0.0

    raw_win_rate = (
        wins
        / total
    )

    adjusted_win_rate = (
        wilson_shrunk_win_rate(
            wins=wins,
            total=total,
            prior_rate=baseline_win_rate,
        )
    )

    average_return = safe_float(
        returns.mean()
    )

    adjustment = calculate_adjustment(
        win_rate=adjusted_win_rate,
        average_return=average_return,
        profit_factor=profit_factor,
        sample_count=total,
        baseline_win_rate=baseline_win_rate,
    )

    if total < MIN_SAMPLE_FOR_ADJUSTMENT:
        judgement = "データ不足"
    elif adjustment >= 8:
        judgement = "強化"
    elif adjustment >= 3:
        judgement = "やや強化"
    elif adjustment <= -8:
        judgement = "大幅抑制"
    elif adjustment <= -3:
        judgement = "やや抑制"
    else:
        judgement = "維持"

    return {
        "カテゴリ": category,
        "条件": condition,
        "取引数": total,
        "勝ち": wins,
        "負け": losses,
        "引分": draws,
        "勝率%": round(
            raw_win_rate * 100,
            2,
        ),
        "補正勝率%": round(
            adjusted_win_rate * 100,
            2,
        ),
        "平均損益率%": round(
            average_return,
            4,
        ),
        "中央値損益率%": round(
            safe_float(
                returns.median()
            ),
            4,
        ),
        "総損益率%": round(
            safe_float(
                returns.sum()
            ),
            4,
        ),
        "PF": round(
            profit_factor,
            3,
        ),
        "信頼度%": round(
            sample_confidence(total)
            * 100,
            2,
        ),
        "AI点補正": adjustment,
        "判定": judgement,
    }


def bin_label(
    value: float,
    bins: list[
        tuple[
            float,
            float,
            str,
        ]
    ],
) -> str:
    for minimum, maximum, label in bins:
        if minimum <= value <= maximum:
            return label

    return "不明"


def build_learning_report(
    data: pd.DataFrame,
) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(
            columns=[
                "カテゴリ",
                "条件",
                "取引数",
                "勝ち",
                "負け",
                "引分",
                "勝率%",
                "補正勝率%",
                "平均損益率%",
                "中央値損益率%",
                "総損益率%",
                "PF",
                "信頼度%",
                "AI点補正",
                "判定",
            ]
        )

    baseline_wins = int(
        (
            data["損益率%"] > 0
        ).sum()
    )

    baseline_win_rate = (
        baseline_wins
        / len(data)
        if len(data) > 0
        else 0.5
    )

    rows: list[
        dict[str, Any]
    ] = []

    rows.append(
        create_group_row(
            data=data,
            category="全体",
            condition="全取引",
            baseline_win_rate=baseline_win_rate,
        )
    )

    data = data.copy()

    data["RSI条件"] = data["RSI"].apply(
        lambda value:
            bin_label(
                safe_float(value),
                RSI_BINS,
            )
    )

    data["AI点条件"] = data[
        "AI判断点"
    ].apply(
        lambda value:
            bin_label(
                safe_float(value),
                AI_SCORE_BINS,
            )
    )

    data["PHOENIX条件"] = data[
        "PHOENIX_SCORE"
    ].apply(
        lambda value:
            bin_label(
                safe_float(value),
                PHOENIX_SCORE_BINS,
            )
    )

    grouping_definitions = [
        (
            "RSI",
            "RSI条件",
        ),
        (
            "MACD",
            "MACD判定",
        ),
        (
            "AI判断",
            "AI判断",
        ),
        (
            "AI判断点",
            "AI点条件",
        ),
        (
            "PHOENIX_SCORE",
            "PHOENIX条件",
        ),
        (
            "決済理由",
            "決済理由",
        ),
    ]

    for category, column in grouping_definitions:
        for condition, group in data.groupby(
            column,
            dropna=False,
        ):
            condition_text = str(
                condition
            ).strip()

            if (
                not condition_text
                or condition_text.lower()
                == "nan"
            ):
                condition_text = "不明"

            rows.append(
                create_group_row(
                    data=group,
                    category=category,
                    condition=condition_text,
                    baseline_win_rate=baseline_win_rate,
                )
            )

    report = pd.DataFrame(
        rows
    )

    report = report.sort_values(
        by=[
            "カテゴリ",
            "取引数",
            "AI点補正",
        ],
        ascending=[
            True,
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    return report


# =========================================================
# AIパラメータ作成
# =========================================================

def report_adjustments(
    report: pd.DataFrame,
    category: str,
) -> dict[str, int]:
    if report.empty:
        return {}

    matched = report[
        (
            report["カテゴリ"]
            == category
        )
        & (
            report["取引数"]
            >= MIN_SAMPLE_FOR_ADJUSTMENT
        )
    ]

    return {
        str(row["条件"]): safe_int(
            row["AI点補正"]
        )
        for _, row in matched.iterrows()
    }


def overall_statistics(
    data: pd.DataFrame,
) -> dict[str, Any]:
    if data.empty:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "win_rate_percent": 0.0,
            "average_return_percent": 0.0,
            "total_return_percent": 0.0,
            "profit_factor": 0.0,
        }

    returns = pd.to_numeric(
        data["損益率%"],
        errors="coerce",
    ).fillna(0.0)

    wins = int(
        (
            returns > 0
        ).sum()
    )

    losses = int(
        (
            returns < 0
        ).sum()
    )

    draws = len(data) - wins - losses

    gross_profit = safe_float(
        returns[
            returns > 0
        ].sum()
    )

    gross_loss = abs(
        safe_float(
            returns[
                returns < 0
            ].sum()
        )
    )

    if gross_loss > 0:
        profit_factor = (
            gross_profit
            / gross_loss
        )
    elif gross_profit > 0:
        profit_factor = 99.0
    else:
        profit_factor = 0.0

    return {
        "trades": len(data),
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate_percent": round(
            wins
            / len(data)
            * 100,
            2,
        ),
        "average_return_percent": round(
            safe_float(
                returns.mean()
            ),
            4,
        ),
        "total_return_percent": round(
            safe_float(
                returns.sum()
            ),
            4,
        ),
        "profit_factor": round(
            profit_factor,
            3,
        ),
    }


def build_parameter_data(
    data: pd.DataFrame,
    report: pd.DataFrame,
) -> dict[str, Any]:
    total_trades = len(data)

    learning_active = (
        total_trades
        >= MIN_SAMPLE_FOR_ADJUSTMENT
    )

    return {
        "version": "PHOENIX v3.4",
        "generated_at": now_text(),
        "account_capital_yen": ACCOUNT_CAPITAL,
        "learning": {
            "active": learning_active,
            "minimum_sample_for_adjustment": (
                MIN_SAMPLE_FOR_ADJUSTMENT
            ),
            "strong_sample_count": STRONG_SAMPLE_COUNT,
            "maximum_score_adjustment": (
                MAX_SCORE_ADJUSTMENT
            ),
            "message": (
                "学習補正を有効化"
                if learning_active
                else (
                    f"決済済み取引が"
                    f"{MIN_SAMPLE_FOR_ADJUSTMENT}件未満のため"
                    "AI点補正は0"
                )
            ),
        },
        "overall": overall_statistics(
            data
        ),
        "score_adjustments": {
            "rsi": report_adjustments(
                report,
                "RSI",
            ),
            "macd": report_adjustments(
                report,
                "MACD",
            ),
            "ai_judgement": report_adjustments(
                report,
                "AI判断",
            ),
            "ai_score": report_adjustments(
                report,
                "AI判断点",
            ),
            "phoenix_score": report_adjustments(
                report,
                "PHOENIX_SCORE",
            ),
        },
        "risk_management": {
            "account_capital_yen": ACCOUNT_CAPITAL,
            "default_risk_per_trade_percent": 1.0,
            "default_max_loss_yen": int(
                ACCOUNT_CAPITAL
                * 0.01
            ),
            "maximum_total_exposure_percent": 80.0,
            "maximum_single_position_percent": 30.0,
            "maximum_open_positions": 3,
        },
    }


# =========================================================
# 保存・表示
# =========================================================

def save_outputs(
    report: pd.DataFrame,
    parameters: dict[str, Any],
) -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    report.to_csv(
        LEARNING_REPORT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    write_json(
        PARAMETER_FILE,
        parameters,
    )

    overall = parameters["overall"]
    learning = parameters["learning"]

    with open(
        TEXT_REPORT_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
            "PHOENIX LEARNING ENGINE REPORT\n"
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
            f"口座資金: "
            f"{ACCOUNT_CAPITAL:,}円\n"
        )
        file.write(
            f"学習対象: "
            f"{overall['trades']}件\n"
        )
        file.write(
            f"勝率: "
            f"{overall['win_rate_percent']:.2f}%\n"
        )
        file.write(
            f"平均損益率: "
            f"{overall['average_return_percent']:+.4f}%\n"
        )
        file.write(
            f"PF: "
            f"{overall['profit_factor']:.3f}\n"
        )
        file.write(
            f"学習状態: "
            f"{learning['message']}\n"
        )
        file.write(
            "\n"
        )

        if report.empty:
            file.write(
                "決済済みの学習データはありません。\n"
            )
        else:
            file.write(
                report.to_string(
                    index=False
                )
            )
            file.write(
                "\n"
            )


def print_result(
    data: pd.DataFrame,
    report: pd.DataFrame,
    parameters: dict[str, Any],
) -> None:
    overall = parameters["overall"]
    learning = parameters["learning"]

    print("=" * 100)
    print("PHOENIX LEARNING ENGINE")
    print("=" * 100)
    print(
        f"口座資金       : "
        f"{ACCOUNT_CAPITAL:,}円"
    )
    print(
        f"学習対象取引   : "
        f"{len(data)}件"
    )
    print(
        f"勝ち           : "
        f"{overall['wins']}件"
    )
    print(
        f"負け           : "
        f"{overall['losses']}件"
    )
    print(
        f"勝率           : "
        f"{overall['win_rate_percent']:.2f}%"
    )
    print(
        f"平均損益率     : "
        f"{overall['average_return_percent']:+.4f}%"
    )
    print(
        f"PF             : "
        f"{overall['profit_factor']:.3f}"
    )
    print(
        f"学習状態       : "
        f"{learning['message']}"
    )

    print()
    print("=" * 100)
    print("学習結果")
    print("=" * 100)

    if report.empty:
        print(
            "決済済み取引がないため、"
            "初期パラメータを保存しました。"
        )
    else:
        display_columns = [
            "カテゴリ",
            "条件",
            "取引数",
            "勝率%",
            "平均損益率%",
            "PF",
            "信頼度%",
            "AI点補正",
            "判定",
        ]

        print(
            report[
                display_columns
            ].to_string(
                index=False
            )
        )

    print()
    print(
        f"保存完了: {LEARNING_REPORT_FILE}"
    )
    print(
        f"保存完了: {PARAMETER_FILE}"
    )
    print(
        f"保存完了: {TEXT_REPORT_FILE}"
    )


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()

    try:
        REPORT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        data = load_learning_source()

        report = build_learning_report(
            data
        )

        parameters = build_parameter_data(
            data=data,
            report=report,
        )

        save_outputs(
            report=report,
            parameters=parameters,
        )

        print_result(
            data=data,
            report=report,
            parameters=parameters,
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
