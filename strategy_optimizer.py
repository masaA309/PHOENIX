# strategy_optimizer.py

from itertools import product
from pathlib import Path

import pandas as pd


INPUT_FILE = Path("reports/backtest_all.csv")
OUTPUT_FILE = Path("reports/strategy_optimizer.csv")

MIN_SAMPLE_SIZE = 100

SCORE_THRESHOLDS = [
    40,
    45,
    50,
    55,
    60,
    65,
    70,
    75,
    80,
    85,
    90
]

RSI_MIN_VALUES = [
    0,
    30,
    40,
    45,
    50
]

RSI_MAX_VALUES = [
    60,
    65,
    70,
    75,
    80,
    100
]

VOLUME_THRESHOLDS = [
    0,
    1.0,
    1.2,
    1.5,
    2.0
]

MACD_FILTERS = [
    "ALL",
    "BUY",
    "SELL"
]


def load_data():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"ファイルが見つかりません: {INPUT_FILE}"
        )

    df = pd.read_csv(INPUT_FILE)

    required_columns = {
        "score",
        "翌日騰落率%",
        "RSI",
        "出来高倍率",
        "MACD判定"
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            f"必要な列がありません: {missing_text}"
        )

    numeric_columns = [
        "score",
        "翌日騰落率%",
        "RSI",
        "出来高倍率"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df["MACD判定"] = (
        df["MACD判定"]
        .astype(str)
        .str.upper()
        .str.strip()
    )

    df = df.dropna(
        subset=numeric_columns
    )

    return df


def calculate_profit_factor(returns):
    total_profit = float(
        returns[
            returns > 0
        ].sum()
    )

    total_loss = abs(
        float(
            returns[
                returns < 0
            ].sum()
        )
    )

    if total_loss == 0:
        return 999.0 if total_profit > 0 else 0.0

    return total_profit / total_loss


def calculate_max_drawdown(returns):
    equity_curve = (
        1
        + returns / 100
    ).cumprod()

    running_max = equity_curve.cummax()

    drawdown = (
        equity_curve
        / running_max
        - 1
    ) * 100

    return float(
        drawdown.min()
    )


def analyze_strategy(
    df,
    score_threshold,
    rsi_min,
    rsi_max,
    volume_threshold,
    macd_filter
):
    target = df[
        (df["score"] >= score_threshold)
        & (df["RSI"] >= rsi_min)
        & (df["RSI"] <= rsi_max)
        & (df["出来高倍率"] >= volume_threshold)
    ].copy()

    if macd_filter != "ALL":
        target = target[
            target["MACD判定"]
            == macd_filter
        ]

    sample_count = len(target)

    if sample_count < MIN_SAMPLE_SIZE:
        return None

    returns = target[
        "翌日騰落率%"
    ]

    wins = int(
        (returns > 0).sum()
    )

    losses = int(
        (returns < 0).sum()
    )

    draws = int(
        (returns == 0).sum()
    )

    win_rate = (
        wins
        / sample_count
        * 100
    )

    average_return = float(
        returns.mean()
    )

    median_return = float(
        returns.median()
    )

    average_win = returns[
        returns > 0
    ].mean()

    average_loss = returns[
        returns < 0
    ].mean()

    profit_factor = calculate_profit_factor(
        returns
    )

    max_drawdown = calculate_max_drawdown(
        returns
    )

    positive_months = None

    if "シグナル日" in target.columns:
        target["シグナル日"] = pd.to_datetime(
            target["シグナル日"],
            errors="coerce"
        )

        monthly_returns = (
            target
            .dropna(
                subset=["シグナル日"]
            )
            .assign(
                月=lambda x:
                    x["シグナル日"]
                    .dt.to_period("M")
            )
            .groupby("月")[
                "翌日騰落率%"
            ]
            .mean()
        )

        if len(monthly_returns) > 0:
            positive_months = (
                monthly_returns > 0
            ).mean() * 100

    strategy_score = (
        average_return * 100
        + (profit_factor - 1) * 20
        + (win_rate - 50) * 0.5
        + min(sample_count / 1000, 5)
        + max(max_drawdown, -50) * 0.05
    )

    return {
        "最低スコア": score_threshold,
        "RSI下限": rsi_min,
        "RSI上限": rsi_max,
        "最低出来高倍率": volume_threshold,
        "MACD条件": macd_filter,
        "対象数": sample_count,
        "勝ち": wins,
        "負け": losses,
        "引き分け": draws,
        "勝率%": round(
            win_rate,
            2
        ),
        "平均騰落率%": round(
            average_return,
            4
        ),
        "中央値%": round(
            median_return,
            4
        ),
        "平均利益%": (
            round(
                float(average_win),
                4
            )
            if pd.notna(average_win)
            else 0.0
        ),
        "平均損失%": (
            round(
                float(average_loss),
                4
            )
            if pd.notna(average_loss)
            else 0.0
        ),
        "最大上昇%": round(
            float(returns.max()),
            2
        ),
        "最大下落%": round(
            float(returns.min()),
            2
        ),
        "最大DD%": round(
            max_drawdown,
            2
        ),
        "プロフィットファクター": round(
            profit_factor,
            3
        ),
        "プラス月率%": (
            round(
                positive_months,
                2
            )
            if positive_months is not None
            else 0.0
        ),
        "戦略評価点": round(
            strategy_score,
            3
        )
    }


def main():
    print("=" * 60)
    print("PHOENIX STRATEGY OPTIMIZER")
    print("=" * 60)
    print()

    try:
        df = load_data()

    except Exception as error:
        print(error)
        return

    combinations = list(
        product(
            SCORE_THRESHOLDS,
            RSI_MIN_VALUES,
            RSI_MAX_VALUES,
            VOLUME_THRESHOLDS,
            MACD_FILTERS
        )
    )

    total_combinations = len(
        combinations
    )

    print(
        f"検証条件数: {total_combinations}"
    )
    print()

    results = []

    for number, combination in enumerate(
        combinations,
        start=1
    ):
        (
            score_threshold,
            rsi_min,
            rsi_max,
            volume_threshold,
            macd_filter
        ) = combination

        if rsi_min >= rsi_max:
            continue

        result = analyze_strategy(
            df=df,
            score_threshold=score_threshold,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            volume_threshold=volume_threshold,
            macd_filter=macd_filter
        )

        if result is not None:
            results.append(result)

        if (
            number % 500 == 0
            or number == total_combinations
        ):
            print(
                f"[{number}/{total_combinations}]"
            )

    if not results:
        print(
            "条件を満たす分析結果がありません。"
        )
        return

    result_df = pd.DataFrame(
        results
    )

    result_df = result_df.sort_values(
        by=[
            "戦略評価点",
            "平均騰落率%",
            "プロフィットファクター",
            "対象数"
        ],
        ascending=[
            False,
            False,
            False,
            False
        ]
    ).reset_index(
        drop=True
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("=" * 60)
    print("最良条件 TOP20")
    print("=" * 60)
    print()

    display_columns = [
        "最低スコア",
        "RSI下限",
        "RSI上限",
        "最低出来高倍率",
        "MACD条件",
        "対象数",
        "勝率%",
        "平均騰落率%",
        "中央値%",
        "最大DD%",
        "プロフィットファクター",
        "戦略評価点"
    ]

    print(
        result_df[
            display_columns
        ]
        .head(20)
        .to_string(index=False)
    )

    print()
    print(
        f"保存完了: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()