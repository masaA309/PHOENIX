# score_analysis.py

from pathlib import Path

import pandas as pd


BACKTEST_FILE = Path("reports/backtest_all.csv")
OUTPUT_FILE = Path("reports/score_analysis.csv")


def load_backtest_data(file_path):
    if not file_path.exists():
        raise FileNotFoundError(
            f"ファイルが見つかりません: {file_path}"
        )

    df = pd.read_csv(file_path)

    required_columns = {
        "score",
        "翌日騰落率%"
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

    df["score"] = pd.to_numeric(
        df["score"],
        errors="coerce"
    )

    df["翌日騰落率%"] = pd.to_numeric(
        df["翌日騰落率%"],
        errors="coerce"
    )

    df = df.dropna(
        subset=[
            "score",
            "翌日騰落率%"
        ]
    )

    return df


def calculate_statistics(
    df,
    score_threshold
):
    target = df[
        df["score"]
        >= score_threshold
    ].copy()

    count = len(target)

    if count == 0:
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
        / count
        * 100
    )

    positive_average = (
        returns[
            returns > 0
        ].mean()
    )

    negative_average = (
        returns[
            returns < 0
        ].mean()
    )

    profit_factor = None

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

    if total_loss > 0:
        profit_factor = (
            total_profit
            / total_loss
        )

    return {
        "score以上": score_threshold,
        "対象数": count,
        "勝ち": wins,
        "負け": losses,
        "引き分け": draws,
        "勝率%": round(
            win_rate,
            2
        ),
        "平均騰落率%": round(
            float(
                returns.mean()
            ),
            4
        ),
        "中央値%": round(
            float(
                returns.median()
            ),
            4
        ),
        "平均利益%": (
            round(
                float(
                    positive_average
                ),
                4
            )
            if pd.notna(
                positive_average
            )
            else 0.0
        ),
        "平均損失%": (
            round(
                float(
                    negative_average
                ),
                4
            )
            if pd.notna(
                negative_average
            )
            else 0.0
        ),
        "最大上昇%": round(
            float(
                returns.max()
            ),
            2
        ),
        "最大下落%": round(
            float(
                returns.min()
            ),
            2
        ),
        "プロフィットファクター": (
            round(
                profit_factor,
                3
            )
            if profit_factor
            is not None
            else 0.0
        )
    }


def analyze_exact_scores(df):
    exact_results = []

    score_values = sorted(
        df["score"]
        .dropna()
        .astype(int)
        .unique()
    )

    for score_value in score_values:
        target = df[
            df["score"]
            == score_value
        ]

        if target.empty:
            continue

        returns = target[
            "翌日騰落率%"
        ]

        exact_results.append({
            "score": score_value,
            "対象数": len(target),
            "勝率%": round(
                (
                    returns > 0
                ).mean()
                * 100,
                2
            ),
            "平均騰落率%": round(
                float(
                    returns.mean()
                ),
                4
            ),
            "中央値%": round(
                float(
                    returns.median()
                ),
                4
            )
        })

    return pd.DataFrame(
        exact_results
    )


def main():
    print("=" * 60)
    print("PHOENIX SCORE ANALYSIS")
    print("=" * 60)
    print()

    try:
        df = load_backtest_data(
            BACKTEST_FILE
        )

    except Exception as error:
        print(error)
        return

    thresholds = [
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
        90,
        95,
        100
    ]

    results = []

    for threshold in thresholds:
        stats = calculate_statistics(
            df,
            threshold
        )

        if stats is not None:
            results.append(
                stats
            )

    result_df = pd.DataFrame(
        results
    )

    if result_df.empty:
        print("分析対象データがありません。")
        return

    print("スコア以上の累積成績")
    print()

    print(
        result_df.to_string(
            index=False
        )
    )

    exact_df = analyze_exact_scores(
        df
    )

    print()
    print("=" * 60)
    print("スコア単体の成績")
    print("=" * 60)
    print()

    if exact_df.empty:
        print("単体スコア分析データなし")
    else:
        print(
            exact_df.to_string(
                index=False
            )
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

    exact_output_file = Path(
        "reports/"
        "score_analysis_exact.csv"
    )

    exact_df.to_csv(
        exact_output_file,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        f"保存完了 : {OUTPUT_FILE}"
    )
    print(
        f"保存完了 : {exact_output_file}"
    )


if __name__ == "__main__":
    main()