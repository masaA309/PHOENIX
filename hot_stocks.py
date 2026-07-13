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

print("スクリーニング中...\n")

for name, ticker in stocks.items():
    try:
        hist = yf.Ticker(ticker).history(period="1mo")

        if hist.empty or len(hist) < 6:
            continue

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        if len(close) < 2 or len(volume) < 6:
            continue

        latest = float(close.iloc[-1])
        previous = float(close.iloc[-2])

        change = (latest - previous) / previous * 100

        latest_volume = float(volume.iloc[-1])
        avg_volume = float(volume.iloc[-6:-1].mean())

        if avg_volume == 0:
            continue

        volume_ratio = latest_volume / avg_volume

        if change >= 2 and volume_ratio >= 1.5:
            results.append({
                "銘柄": name,
                "価格": round(latest, 2),
                "前日比%": round(change, 2),
                "出来高倍率": round(volume_ratio, 2)
            })

    except Exception as e:
        print(f"{name}: {e}")

if results:
    df = pd.DataFrame(results)
    df = df.sort_values(
        by="前日比%",
        ascending=False
    )

    print("===== 注目銘柄 =====\n")
    print(df.to_string(index=False))
else:
    print("本日の注目銘柄はありません。")