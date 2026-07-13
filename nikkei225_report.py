import pandas as pd
import yfinance as yf

stocks = pd.read_csv("nikkei225.csv")

results = []

print("日経225スキャン中...\n")

for _, row in stocks.iterrows():

    name = row["name"]
    ticker = row["ticker"]

    try:
        hist = yf.Ticker(ticker).history(period="5d")

        if hist.empty or len(hist) < 2:
            continue

        close = hist["Close"].dropna()

        latest = float(close.iloc[-1])
        previous = float(close.iloc[-2])

        change = (latest - previous) / previous * 100

        results.append({
            "銘柄": name,
            "価格": round(latest, 2),
            "前日比%": round(change, 2)
        })

    except:
        pass

df = pd.DataFrame(results)

df = df.sort_values(
    by="前日比%",
    ascending=False
)

print(df.head(10).to_string(index=False))