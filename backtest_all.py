import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from indicators import calc_score


CSV_FILE = "data/nikkei225.csv"
REPORT_DIR = Path("reports")
OUTPUT_FILE = REPORT_DIR / "backtest_all.csv"

SCORE_THRESHOLD = 40
HISTORY_PERIOD = "2y"
MIN_HISTORY_DAYS = 80
REQUEST_INTERVAL = 0.1


def validate_stock_list(stocks):
    required_columns = {"name", "ticker"}
    missing_columns = required_columns - set(stocks.columns)

    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise ValueError(
            f"銘柄CSVに必要な列がありません: {missing_text}"
        )


def calculate_next_day_return(close, index):
    buy_price = float(close.iloc[index])
    sell_price = float(close.iloc[index + 1])

    if buy_price <= 0:
        return None

    return (
        (sell_price - buy_price)
        / buy_price
        * 100
    )


def backtest_stock(name, ticker):
    hist = yf.Ticker(ticker).history(
        period=HISTORY_PERIOD,
        auto_adjust=True
    )

    if hist.empty:
        return []

    if "Close" not in hist.columns or "Volume" not in hist.columns:
        return []

    data = hist[
        ["Close", "Volume"]
    ].dropna()

    if len(data) < MIN_HISTORY_DAYS:
        return []

    close = data["Close"]
    volume = data["Volume"]

    results = []

    for index in range(
        75,
        len(data) - 1
    ):
        historical_close = close.iloc[
            : index + 1
        ]

        historical_volume = volume.iloc[
            : index + 1
        ]

        score_data = calc_score(
            historical_close,
            historical_volume
        )

        if score_data is None:
            continue

        score = int(
            score_data["score"]
        )

        if score < SCORE_THRESHOLD:
            continue

        next_day_return = calculate_next_day_return(
            close,
            index
        )

        if next_day_return is None:
            continue

        signal_date = pd.Timestamp(
            data.index[index]
        ).strftime("%Y-%m-%d")

        next_date = pd.Timestamp(
            data.index[index + 1]
        ).strftime("%Y-%m-%d")

        results.append({
            "銘柄": name,
            "ticker": ticker,
            "シグナル日": signal_date,
            "判定日": next_date,
            "score": score,
            "翌日騰落率%": round(
                next_day_return,
                4
            ),
            "前日比%": score_data["change"],
            "出来高倍率": score_data[
                "volume_ratio"
            ],
            "MA5": score_data["ma5"],
            "MA25": score_data["ma25"],
            "MA75": score_data["ma75"],
            "RSI": score_data["rsi"],
            "MACD判定": score_data[
                "macd_judge"
            ],
            "理由": score_data["reason"]
        })

    return results


def print_summary(result_df):
    returns = result_df[
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

    total = len(result_df)

    win_rate = (
        wins / total * 100
        if total > 0
        else 0
    )

    average_return = float(
        returns.mean()
    )

    median_return = float(
        returns.median()
    )

    max_return = float(
        returns.max()
    )

    min_return = float(
        returns.min()
    )

    print()
    print("=" * 60)
    print("PHOENIX BACKTEST RESULT")
    print("=" * 60)
    print(f"最低スコア     : {SCORE_THRESHOLD}")
    print(f"対象数         : {total}")
    print(f"勝ち           : {wins}")
    print(f"負け           : {losses}")
    print(f"引き分け       : {draws}")
    print(f"勝率           : {win_rate:.2f}%")
    print(f"平均騰落率     : {average_return:.4f}%")
    print(f"中央値         : {median_return:.4f}%")
    print(f"最大上昇       : {max_return:.2f}%")
    print(f"最大下落       : {min_return:.2f}%")
    print("=" * 60)

    top_results = result_df.sort_values(
        by="翌日騰落率%",
        ascending=False
    ).head(20)

    print()
    print("翌日上昇率 TOP20")
    print()
    print(
        top_results[
            [
                "銘柄",
                "ticker",
                "シグナル日",
                "score",
                "RSI",
                "MACD判定",
                "翌日騰落率%"
            ]
        ].to_string(index=False)
    )


def main():
    print("=" * 60)
    print("PHOENIX ALL BACKTEST")
    print("RSI・MACD対応 共通スコア版")
    print("=" * 60)
    print()

    try:
        stocks = pd.read_csv(
            CSV_FILE
        )

        validate_stock_list(
            stocks
        )

    except Exception as error:
        print(
            f"銘柄CSV読込エラー: {error}"
        )
        return

    all_results = []
    total_stocks = len(stocks)
    success_count = 0
    error_count = 0

    for number, row in enumerate(
        stocks.itertuples(index=False),
        start=1
    ):
        name = str(row.name)
        ticker = str(row.ticker)

        print(
            f"[{number}/{total_stocks}] "
            f"{ticker} {name}"
        )

        try:
            stock_results = backtest_stock(
                name,
                ticker
            )

            all_results.extend(
                stock_results
            )

            success_count += 1

        except Exception as error:
            error_count += 1
            print(
                f"ERROR {ticker}: {error}"
            )

        time.sleep(
            REQUEST_INTERVAL
        )

    if not all_results:
        print()
        print("バックテスト対象データがありません。")
        return

    result_df = pd.DataFrame(
        all_results
    )

    result_df = result_df.sort_values(
        by=[
            "シグナル日",
            "score",
            "ticker"
        ],
        ascending=[
            True,
            False,
            True
        ]
    ).reset_index(
        drop=True
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print_summary(
        result_df
    )

    print()
    print(f"正常取得銘柄数 : {success_count}")
    print(f"エラー銘柄数   : {error_count}")
    print(f"保存完了       : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()