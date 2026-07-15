# news.py

import feedparser
from urllib.parse import quote


def get_stock_news(company_name, max_items=5):
    """
    銘柄名からGoogleニュースを取得する

    Returns:
        [
            {
                "title": "...",
                "link": "...",
                "published": "..."
            }
        ]
    """

    query = quote(company_name)

    url = (
        f"https://news.google.com/rss/search?"
        f"q={query}+株&hl=ja&gl=JP&ceid=JP:ja"
    )

    feed = feedparser.parse(url)

    news_list = []

    for entry in feed.entries[:max_items]:

        news = {
            "title": entry.get(
                "title",
                ""
            ),
            "link": entry.get(
                "link",
                ""
            ),
            "published": entry.get(
                "published",
                ""
            )
        }

        news_list.append(news)

    return news_list


def print_stock_news(company_name, max_items=5):

    news = get_stock_news(
        company_name,
        max_items
    )

    print("=" * 60)
    print(f"{company_name} ニュース")
    print("=" * 60)

    if len(news) == 0:
        print("ニュースなし")
        return

    for i, item in enumerate(news, start=1):

        print(f"[{i}] {item['title']}")
        print(item["published"])
        print(item["link"])
        print()


if __name__ == "__main__":

    company = input(
        "銘柄名："
    )

    print_stock_news(company)