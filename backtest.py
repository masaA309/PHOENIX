# backtest.py

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta


def backtest(
    report_file=None,
    score_threshold=80
):
    """
    PHOENIXスコアの翌日成績を検証する
    """

    if report_file is None:

        today = datetime.now().strftime(
            "%Y%m%d"
        )

        report_file = (
            f"reports/report_{today}.csv"
        )

    print("=" * 60)
    print("PHOENIX BACKTEST")
    print("=" * 60)
    print()

    try:
        df = pd.read_csv(
            report_file
        )

    except Exception as e:

        print(
            f"レポート読込失敗 : {e}"
        )
        return

    targets = df[
        df["PHOENIX_SCORE"]
        >= score_threshold
    ]

    if targets.empty:
        print(
            "対象銘柄なし"
        )
        return

    print(
        f"対象銘柄 : {len(targets)}"
    )
    print()

    results = []

    for _, row in targets.iterrows():

        ticker = row["ticker"]
        name = row["銘柄"]
        score = row["PHOENIX_SCORE"]

        try:
            hist = (
                yf.Ticker(ticker)
                .history(period="7d")
            )

            if len(hist) < 2:
                continue

            buy_price = float(
                hist["Close"].iloc[-2]
            )

            sell_price = float(
                hist["Close"].iloc[-1]
            )

            ret = (
                (
                    sell_price
                    - buy_price
                )
                / buy_price
                * 100
            )

            results.append({
                "銘柄": name,
                "ticker": ticker,
                "PHOENIX_SCORE": score,
                "買値": round(
                    buy_price,
                    2
                ),
                "売値": round(
                    sell_price,
                    2
                ),
                "騰落率%": round(
                    ret,
                    2
                )
            })

            print(
                f"{ticker} "
                f"{ret:.2f}%"
            )

        except Exception as e:

            print(
                f"{ticker} エラー : {e}"
            )

    if len(results) == 0:
        print(
            "検証データなし"
        )
        return

    result_df = pd.DataFrame(
        results
    )

    wins = len(
        result_df[
            result_df["騰落率%"] > 0
        ]
    )

    win_rate = (
        wins
        / len(result_df)
        * 100
    )

    avg_return = (
        result_df[
            "騰落率%"
        ].mean()
    )

    print()
    print("=" * 60)
    print("BACKTEST RESULT")
    print("=" * 60)

    print(
        f"対象銘柄数 : {len(result_df)}"
    )

    print(
        f"勝率 : "
        f"{win_rate:.2f}%"
    )

    print(
        f"平均騰落率 : "
        f"{avg_return:.2f}%"
    )

    print()

    print(
        result_df.sort_values(
            by="騰落率%",
            ascending=False
        ).to_string(
            index=False
        )
    )

    save_file = (
        "reports/"
        "backtest_result.csv"
    )

    result_df.to_csv(
        save_file,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        f"保存完了 : {save_file}"
    )


if __name__ == "__main__":
    backtest()