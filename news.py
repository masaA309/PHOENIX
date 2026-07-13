import feedparser

url = "https://news.google.com/rss/search?q=トヨタ&hl=ja&gl=JP&ceid=JP:ja"

feed = feedparser.parse(url)

print("記事数:", len(feed.entries))

for i, entry in enumerate(feed.entries[:5], start=1):
    print(f"{i}. タイトル:", entry.title)
    print("リンク:", entry.link)
    print("----------------")