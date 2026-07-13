import yfinance as yf
import feedparser

ticker = "7203.T"

# 株価取得
stock = yf.Ticker(ticker)
info = stock.info

price = info.get("currentPrice")
name = info.get("longName")

print("===== PHOENIX AI REPORT =====")
print(f"銘柄: {name}")
print(f"現在価格: {price} JPY")
print()

# ニュース取得
url = "https://news.google.com/rss/search?q=トヨタ&hl=ja&gl=JP&ceid=JP:ja"
feed = feedparser.parse(url)

print("【最新ニュース】")
titles = []

for i, entry in enumerate(feed.entries[:5], start=1):
    print(f"{i}. {entry.title}")
    titles.append(entry.title)

print()

# 簡易AIコメント
print("【PHOENIXコメント】")

text = " ".join(titles)

if "EV" in text or "電気自動車" in text:
    print("EV関連ニュースが目立ちます。自動車業界の成長テーマとして注目です。")

elif "決算" in text:
    print("決算関連ニュースが出ています。業績内容の確認が重要です。")

elif "下落" in text or "減益" in text:
    print("ネガティブなニュースが見られます。慎重な判断が必要です。")

else:
    print("本日は大きな材料は少なく、通常のニュースフローとなっています。")