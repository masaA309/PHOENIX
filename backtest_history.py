# backtest_history.py

import pandas as pd
import yfinance as yf
from datetime import datetime


def backtest_history(
    ticker,
    score_threshold=80,
    days=100
):
    """
    過去データでPHOENIX SCOREの有効性を検証
    """

    print("=" * 60)
    print(f"BACKTEST : {ticker}")
    print("=" * 60)

    hist = (
        yf.Ticker(ticker)
        .history(period="2y")
    )

    if len(hist) < days + 80:
        print("データ不足")
        return

    results = []

    close = hist["Close"]
    volume = hist["Volume"]

    for i in range(75, len(hist) - 1):

        today = hist.index[i]

        price = float(close.iloc[i])
        prev = float(close.iloc[i - 1])

        change = (
            (price - prev)
            / prev
            * 100
        )

        avg_volume = (
            volume.iloc[i - 5:i]
            .mean()
        )

        if avg_volume == 0:
            volume_ratio = 0
        else:
            volume_ratio = (
                volume.iloc[i]
                / avg_volume
            )

        ma5 = (
            close.iloc[i - 4:i + 1]
            .mean()
        )

        ma25 = (
            close.iloc[i - 24:i + 1]
            .mean()
        )

        ma75 = (
            close.iloc[i - 74:i + 1]
            .mean()
        )

        score = 0

        # 前日比
        if change >= 5:
            score += 35
        elif change >= 3:
            score += 30
        elif change >= 1:
            score += 15

        # 出来高
        if volume_ratio >= 5:
            score += 35
        elif volume_ratio >= 3:
            score += 30
        elif volume_ratio >= 2:
            score += 20
        elif volume_ratio >= 1.5:
            score += 10

        # トレンド
        if price > ma25:
            score += 20

        if ma5 > ma25:
            score += 15

        if ma25 > ma75:
            score += 10

        score = min(score, 100)

        # 翌日の成績
        next_price = float(
            close.iloc[i + 1]
        )

        ret = (
            (next_price - price)
            / price
            * 100
        )

        results.append({
            "date": today.date(),
            "score": score,
            "return": ret
        })

    df = pd.DataFrame(results)

    target = df[
        df["score"]
        >= score_threshold
    ]

    if target.empty:
        print("対象なし")
        return

    wins = len(
        target[
            target["return"] > 0
        ]
    )

    win_rate = (
        wins
        / len(target)
        * 100
    )

    avg_return = (
        target["return"]
        .mean()
    )

    print()
    print(
        f"対象数 : {len(target)}"
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
        target.sort_values(
            by="return",
            ascending=False
        ).head(20)
    )

    save_file = (
        f"reports/"
        f"backtest_{ticker}.csv"
    )

    target.to_csv(
        save_file,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        f"保存完了 : {save_file}"
    )


if __name__ == "__main__":

    ticker = input(
        "ticker : "
    ).strip()

    if ticker == "":
        ticker = "7203.T"

    backtest_history(
        ticker=ticker,
        score_threshold=80
    )