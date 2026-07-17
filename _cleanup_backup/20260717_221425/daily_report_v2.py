import pandas as pd
import yfinance as yf
from datetime import datetime
from pathlib import Path

# ============================
# 日経225銘柄読み込み
# ============================
stocks = pd.read_csv("data/nikkei225.csv")

results = []

print("=" * 60)
print("PHOENIX DAILY REPORT")
print(datetime.now().strftime("%Y-%m-%d %H:%M"))
print("=" * 60)
print()
print("データ取得中...\n")

# ============================
# データ取得
# ============================
for _, row in stocks.iterrows():

    name = row["name"]
    ticker = row["ticker"]

    try:
        hist = yf.Ticker(ticker).history(period="3mo")

        if hist.empty or len(hist) < 30:
            continue

        close = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        if len(close) < 25 or len(volume) < 6:
            continue

        latest = float(close.iloc[-1])
        previous = float(close.iloc[-2])

        change = (latest - previous) / previous * 100

        latest_volume = float(volume.iloc[-1])
        avg_volume = float(volume.iloc[-6:-1].mean())

        volume_ratio = (
            latest_volume / avg_volume
            if avg_volume != 0
            else 0
        )

        # ============================
        # 移動平均
        # ============================
        ma5 = float(close.tail(5).mean())
        ma25 = float(close.tail(25).mean())

        trend = "UP" if latest > ma25 else "DOWN"

        # ============================
        # RSI(14)
        # ============================
        delta = close.diff()

        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        if avg_loss.iloc[-1] == 0:
            rsi = 100
        else:
            rs = avg_gain.iloc[-1] / avg_loss.iloc[-1]
            rsi = 100 - (100 / (1 + rs))

        rsi = round(float(rsi), 2)

        # ============================
        # PHOENIX SCORE
        # ============================
        score = 0

        # 上昇率
        if change >= 3:
            score += 30
        elif change >= 1:
            score += 15

        # 出来高
        if volume_ratio >= 3:
            score += 30
        elif volume_ratio >= 2:
            score += 20
        elif volume_ratio >= 1.5:
            score += 10

        # トレンド
        if trend == "UP":
            score += 20

        # MA5 > MA25
        if ma5 > ma25:
            score += 20

        # RSI
        if 40 <= rsi <= 70:
            score += 10
        elif rsi < 30:
            score += 5

        results.append({
            "銘柄": name,
            "ticker": ticker,
            "価格": round(latest, 2),
            "前日比%": round(change, 2),
            "出来高倍率": round(volume_ratio, 2),
            "MA5": round(ma5, 2),
            "MA25": round(ma25, 2),
            "RSI": rsi,
            "トレンド": trend,
            "PHOENIX_SCORE": score
        })

    except Exception as e:
        print(f"{ticker} エラー: {e}")

# ============================
# データ確認
# ============================
if len(results) == 0:
    print("データ取得失敗")
    raise SystemExit

df = pd.DataFrame(results)

# ============================
# 上昇率ランキング
# ============================
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

# ============================
# 出来高ランキング
# ============================
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

# ============================
# PHOENIX SCORE TOP10
# ============================
print()
print("=" * 60)
print("PHOENIX SCORE TOP10")
print("=" * 60)

score_df = df.sort_values(
    by="PHOENIX_SCORE",
    ascending=False
)

print(
    score_df[
        [
            "銘柄",
            "価格",
            "前日比%",
            "出来高倍率",
            "RSI",
            "PHOENIX_SCORE"
        ]
    ].head(10).to_string(index=False)
)

# ============================
# 注目銘柄
# ============================
print()
print("=" * 60)
print("本日の注目銘柄")
print("=" * 60)

hot = df[
    df["PHOENIX_SCORE"] >= 50
]

if hot.empty:
    print("該当なし")
else:
    print(
        hot[
            [
                "銘柄",
                "価格",
                "前日比%",
                "出来高倍率",
                "RSI",
                "PHOENIX_SCORE"
            ]
        ]
        .sort_values(
            by="PHOENIX_SCORE",
            ascending=False
        )
        .to_string(index=False)
    )

# ============================
# AIコメント
# ============================
print()
print("=" * 60)
print("AIコメント")
print("=" * 60)

if hot.empty:
    print("本日は強いシグナルを示す銘柄はありません。")
else:
    top = hot.sort_values(
        by="PHOENIX_SCORE",
        ascending=False
    ).iloc[0]

    print(
        f"{top['銘柄']}は "
        f"PHOENIX SCORE {top['PHOENIX_SCORE']}点、"
        f"前日比 {top['前日比%']}%、"
        f"出来高 {top['出来高倍率']}倍、"
        f"RSI {top['RSI']} です。"
    )
    print("短期資金の流入が確認されています。")

# ============================
# レポート保存
# ============================
today = datetime.now().strftime("%Y%m%d")

report_dir = Path("reports")
report_dir.mkdir(exist_ok=True)

csv_file = report_dir / f"report_{today}.csv"
txt_file = report_dir / f"report_{today}.txt"

df.to_csv(
    csv_file,
    index=False,
    encoding="utf-8-sig"
)

with open(
    txt_file,
    "w",
    encoding="utf-8"
) as f:
    f.write(
        score_df.head(20).to_string(index=False)
    )

print()
print("レポート保存完了")
print(csv_file)
print(txt_file)

print()
print("=" * 60)
print("PHOENIX REPORT END")
print("=" * 60)