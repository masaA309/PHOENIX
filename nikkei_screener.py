import yfinance as yf
import pandas as pd

stocks = {
    "トヨタ": "7203.T",
    "ソニー": "6758.T",
    "任天堂": "7974.T",
    "NTT": "9432.T",
    "キーエンス": "6861.T",
    "ファーストリテイリング": "9983.T",
    "三菱UFJ": "8306.T",
    "ソフトバンクG": "9984.T",
    "東京エレクトロン": "8035.T",
    "リクルート": "6098.T"
}

results = []

print("データ取得中...\n")

for name, ticker in stocks.items():
    try:
        # history() の方が安定
        hist = yf.Ticker(ticker).history(period="5d")

        if hist.empty or len(hist) < 2:
            print(f"{name}: データ不足")
            continue

        close = hist["Close"].dropna()

        if len(close) < 2:
            print(f"{name}: 終値不足")
            continue

        latest = float(close.iloc[-1])
        previous = float(close.iloc[-2])

        if previous == 0:
            continue

        change = ((latest - previous) / previous) * 100

        results.append({
            "銘柄": name,
            "価格": round(latest, 2),
            "前日比%": round(change, 2)
        })

    except Exception as e:
        print(f"{name}: エラー -> {e}")

if len(results) == 0:
    print("取得できたデータがありません。")
else:
    df = pd.DataFrame(results)

    df = df.sort_values(
        by="前日比%",
        ascending=False
    )

    print("\n===== PHOENIXランキング =====\n")
    print(df.to_string(index=False))