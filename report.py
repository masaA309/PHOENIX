import yfinance as yf
import feedparser

# 株価
ticker = "7203.T"
stock = yf.Ticker(ticker)
info = stock.info

print("===== PHOENIX Daily Report =====")
print(f"銘柄: {info.get('longName')}")
print(f"現在価格: {info.get('currentPrice')} {info.get('currency')}")
print()

# ニュース
url = "https://news.google.com/rss/search?q=トヨタ&hl=ja&gl=JP&ceid=JP:ja"
feed = feedparser.parse(url)

print("【最新ニュース】")
for i, entry in enumerate(feed.entries[:5], start=1):
    print(f"{i}. {entry.title}")