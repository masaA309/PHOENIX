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

print("出来高データ取得中...\n")

for name, ticker in stocks.items():
    try:
        hist = yf.Ticker(ticker).history(period="1mo")

        if hist.empty or len(hist) < 6:
            continue

        volume = hist["Volume"].dropna()

        latest = float(volume.iloc[-1])

        avg5 = float(volume.iloc[-6:-1].mean())

        if avg5 == 0:
            continue

        ratio = latest / avg5

        results.append({
            "銘柄": name,
            "本日出来高": int(latest),
            "5日平均比": round(ratio, 2)
        })

    except Exception as e:
        print(f"{name}: {e}")

if not results:
    print("データ取得失敗")
    exit()

df = pd.DataFrame(results)

df = df.sort_values(
    by="5日平均比",
    ascending=False
)

print("\n===== 出来高急増ランキング =====\n")
print(df.to_string(index=False))