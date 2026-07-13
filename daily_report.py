import pandas as pd
import yfinance as yf
from datetime import datetime

# 日経225銘柄読み込み
stocks = pd.read_csv("nikkei225.csv")

results = []

print("=" * 60)
print("PHOENIX DAILY REPORT")
print(datetime.now().strftime("%Y-%m-%d %H:%M"))
print("=" * 60)
print()

print("データ取得中...\n")

for _, row in stocks.iterrows():

    name = row["name"]
    ticker = row["ticker"]

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
            volume_ratio = 0
        else:
            volume_ratio = latest_volume / avg_volume

        results.append({
            "銘柄": name,
            "ticker": ticker,
            "価格": round(latest, 2),
            "前日比%": round(change, 2),
            "出来高倍率": round(volume_ratio, 2)
        })

    except:
        pass

if len(results) == 0:
    print("データ取得失敗")
    exit()

df = pd.DataFrame(results)

# ----------------------------
# 上昇率ランキング
# ----------------------------

print()
print("=" * 60)
print("上昇率ランキング TOP10")
print("=" * 60)

rank_df = df.sort_values(
    by="前日比%",
    ascending=False
)

print(
    rank_df[
        ["銘柄", "価格", "前日比%"]
    ].head(10).to_string(index=False)
)

# ----------------------------
# 出来高ランキング
# ----------------------------

print()
print("=" * 60)
print("出来高急増ランキング TOP10")
print("=" * 60)

volume_df = df.sort_values(
    by="出来高倍率",
    ascending=False
)

print(
    volume_df[
        ["銘柄", "価格", "出来高倍率"]
    ].head(10).to_string(index=False)
)

# ----------------------------
# 注目銘柄
# ----------------------------

print()
print("=" * 60)
print("本日の注目銘柄")
print("=" * 60)

hot = df[
    (df["前日比%"] >= 2)
    &
    (df["出来高倍率"] >= 1.5)
]

if hot.empty:
    print("該当なし")
else:
    print(
        hot[
            ["銘柄", "価格", "前日比%", "出来高倍率"]
        ].sort_values(
            by="前日比%",
            ascending=False
        ).to_string(index=False)
    )

# ----------------------------
# AIコメント
# ----------------------------

print()
print("=" * 60)
print("AIコメント")
print("=" * 60)

if hot.empty:
    print(
        "本日は強いシグナルを示す銘柄はありません。"
    )
else:
    top = hot.sort_values(
        by="前日比%",
        ascending=False
    ).iloc[0]

    print(
        f"{top['銘柄']}は前日比"
        f"{top['前日比%']}%上昇、"
        f"出来高{top['出来高倍率']}倍です。"
    )
    print(
        "短期資金が流入している可能性があります。"
    )

print()
print("=" * 60)
print("PHOENIX REPORT END")
print("=" * 60)