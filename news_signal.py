# news_signal.py

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote
import re
import time

import feedparser
import pandas as pd


REPORT_DIR = Path("reports")
OUTPUT_FILE = REPORT_DIR / "news_signals.csv"

MAX_STOCKS = 20
MAX_NEWS_PER_STOCK = 10
MAX_ARTICLE_AGE_DAYS = 14
REQUEST_INTERVAL = 0.3


POSITIVE_KEYWORDS = [
    ("業績予想を上方修正", 25),
    ("上方修正", 20),
    ("自己株式取得", 20),
    ("自社株買い", 20),
    ("過去最高益", 18),
    ("最高益", 15),
    ("黒字転換", 15),
    ("増配", 15),
    ("復配", 15),
    ("大型受注", 15),
    ("資本提携", 15),
    ("業務提携", 12),
    ("受注獲得", 12),
    ("承認取得", 15),
    ("目標株価引き上げ", 10),
    ("格上げ", 10),
    ("上振れ", 10),
    ("営業増益", 12),
    ("最終増益", 12),
    ("増益", 10),
    ("共同開発", 10),
    ("新製品", 8),
]


NEGATIVE_KEYWORDS = [
    ("業績予想を下方修正", -25),
    ("下方修正", -20),
    ("赤字転落", -20),
    ("粉飾", -25),
    ("不正", -20),
    ("不祥事", -20),
    ("行政処分", -20),
    ("無配", -20),
    ("減配", -15),
    ("リコール", -15),
    ("営業減益", -12),
    ("最終減益", -12),
    ("業績悪化", -12),
    ("目標株価引き下げ", -10),
    ("格下げ", -10),
    ("下振れ", -10),
    ("減益", -10),
    ("赤字", -15),
    ("訴訟", -10),
]


BLOCKED_SOURCES = [
    "biggo",
    "moomoo",
    "mshale",
    "株つぶやき",
    "掲示板",
]


TRUSTED_SOURCES = [
    "ロイター",
    "reuters",
    "日本経済新聞",
    "日経",
    "時事通信",
    "共同通信",
    "ブルームバーグ",
    "bloomberg",
    "株探",
    "会社四季報",
    "東洋経済",
    "日刊工業新聞",
    "アイフィス株予報",
    "pr times",
]


IRRELEVANT_PATTERNS = [
    r"株つぶやき",
    r"掲示板",
    r"チャート",
    r"現物信用売買内訳",
    r"信用残",
    r"貸借取引",
    r"夜間pts",
    r"寄り前",
    r"成り行き注文",
    r"売買代金",
    r"値上がり率",
    r"値下がり率",
    r"動いた日本株",
    r"株価は今後どうなる",
    r"今の株価の理由",
    r"aiが解説",
    r"株価・株式情報",
    r"リアルタイム株価",
    r"株価速報",
    r"ライブ",
    r"生配信",
    r"youtube",
    r"動画",
    r"バレーボール",
    r"サッカー",
    r"野球",
    r"競馬",
    r"寄り付き",
    r"前場",
    r"後場",
    r"大引け",
]


COMPANY_SUFFIXES = [
    "ホールディングス",
    "フィナンシャルグループ",
    "グループ",
    "株式会社",
    "ＨＤ",
    "HD",
]


def normalize_text(value):
    text = str(value).strip()

    return re.sub(
        r"\s+",
        " ",
        text,
    )


def normalize_for_match(value):
    text = normalize_text(
        value
    ).lower()

    return re.sub(
        r"[\s　・･\-－―ー_（）()\[\]【】]",
        "",
        text,
    )


def simplify_company_name(company_name):
    simplified = normalize_text(
        company_name
    )

    for suffix in COMPANY_SUFFIXES:
        if simplified.endswith(suffix):
            simplified = simplified[
                :-len(suffix)
            ]

    return simplified.strip()


def get_latest_report_file():
    report_files = sorted(
        REPORT_DIR.glob("report_*.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not report_files:
        raise FileNotFoundError(
            "reportsフォルダにreport_*.csvがありません。"
        )

    return report_files[0]


def load_report():
    report_file = get_latest_report_file()

    df = pd.read_csv(
        report_file
    )

    required_columns = {
        "銘柄",
        "ticker",
        "PHOENIX_SCORE",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            f"必要な列がありません: {missing_text}"
        )

    df["PHOENIX_SCORE"] = pd.to_numeric(
        df["PHOENIX_SCORE"],
        errors="coerce",
    )

    df = (
        df.dropna(
            subset=[
                "銘柄",
                "ticker",
                "PHOENIX_SCORE",
            ]
        )
        .sort_values(
            by="PHOENIX_SCORE",
            ascending=False,
        )
        .head(MAX_STOCKS)
        .reset_index(drop=True)
    )

    return df, report_file


def build_google_news_url(company_name):
    query = quote(
        f'"{company_name}" '
        f'(決算 OR 業績 OR 上方修正 OR 下方修正 '
        f'OR 自社株買い OR 増配 OR 減配 '
        f'OR 受注 OR 提携 OR 承認 '
        f'OR 格上げ OR 格下げ)'
    )

    return (
        "https://news.google.com/rss/search"
        f"?q={query}"
        "&hl=ja"
        "&gl=JP"
        "&ceid=JP:ja"
    )


def parse_published_date(entry):
    published_text = entry.get(
        "published",
        "",
    )

    if not published_text:
        return None

    try:
        published = parsedate_to_datetime(
            published_text
        )

        if published.tzinfo is None:
            published = published.replace(
                tzinfo=timezone.utc
            )

        return published.astimezone(
            timezone.utc
        )

    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return None


def is_recent_article(published):
    if published is None:
        return False

    age_seconds = (
        datetime.now(timezone.utc)
        - published
    ).total_seconds()

    maximum_seconds = (
        MAX_ARTICLE_AGE_DAYS
        * 24
        * 60
        * 60
    )

    return (
        0
        <= age_seconds
        <= maximum_seconds
    )


def calculate_recency_score(published):
    age_hours = (
        datetime.now(timezone.utc)
        - published
    ).total_seconds() / 3600

    if age_hours <= 24:
        return 4

    if age_hours <= 72:
        return 2

    if age_hours <= 168:
        return 1

    return 0


def extract_source_name(title):
    parts = re.split(
        r"\s[-–—]\s",
        title,
    )

    if len(parts) < 2:
        return ""

    return parts[-1].strip()


def is_blocked_source(source_name):
    normalized = source_name.lower()

    return any(
        blocked in normalized
        for blocked in BLOCKED_SOURCES
    )


def calculate_source_score(
    title,
    source_name,
):
    combined = (
        f"{title} {source_name}"
    ).lower()

    if any(
        trusted.lower() in combined
        for trusted in TRUSTED_SOURCES
    ):
        return 3

    return 0


def is_irrelevant_title(title):
    return any(
        re.search(
            pattern,
            title,
            flags=re.IGNORECASE,
        )
        for pattern in IRRELEVANT_PATTERNS
    )


def company_name_matches(
    title,
    company_name,
):
    normalized_title = normalize_for_match(
        title
    )

    full_name = normalize_for_match(
        company_name
    )

    simplified_name = normalize_for_match(
        simplify_company_name(
            company_name
        )
    )

    if (
        full_name
        and full_name in normalized_title
    ):
        return True

    if (
        simplified_name
        and len(simplified_name) >= 3
        and simplified_name in normalized_title
    ):
        return True

    return False


def title_signature(title):
    normalized = normalize_for_match(
        title
    )

    normalized = re.sub(
        r"[^0-9a-z一-龥ぁ-んァ-ヶ]",
        "",
        normalized,
    )

    return normalized[:100]


def find_keyword_matches(
    title,
    keyword_definitions,
):
    matches = []

    for keyword, points in keyword_definitions:
        if keyword in title:
            matches.append(
                (
                    keyword,
                    points,
                )
            )

    matches.sort(
        key=lambda item: len(item[0]),
        reverse=True,
    )

    selected = []

    for keyword, points in matches:
        if any(
            keyword in selected_keyword
            for selected_keyword, _ in selected
        ):
            continue

        selected.append(
            (
                keyword,
                points,
            )
        )

    return selected


def analyze_title(title):
    positive_matches = find_keyword_matches(
        title,
        POSITIVE_KEYWORDS,
    )

    negative_matches = find_keyword_matches(
        title,
        NEGATIVE_KEYWORDS,
    )

    positive_score = sum(
        points
        for _, points in positive_matches
    )

    negative_score = sum(
        points
        for _, points in negative_matches
    )

    keywords = []

    for keyword, points in positive_matches:
        keywords.append(
            f"{keyword}(+{points})"
        )

    for keyword, points in negative_matches:
        keywords.append(
            f"{keyword}({points})"
        )

    if negative_score < 0:
        final_score = negative_score

        if positive_score > 0:
            final_score += min(
                positive_score,
                abs(negative_score) // 3,
            )

    else:
        final_score = positive_score

    return (
        final_score,
        keywords,
    )


def fetch_company_news(company_name):
    url = build_google_news_url(
        company_name
    )

    feed = feedparser.parse(
        url
    )

    news_items = []
    seen_signatures = set()

    for entry in feed.entries:
        if len(news_items) >= MAX_NEWS_PER_STOCK:
            break

        title = normalize_text(
            entry.get(
                "title",
                "",
            )
        )

        if not title:
            continue

        source_name = extract_source_name(
            title
        )

        if is_blocked_source(
            source_name
        ):
            continue

        if is_irrelevant_title(
            title
        ):
            continue

        if not company_name_matches(
            title,
            company_name,
        ):
            continue

        published = parse_published_date(
            entry
        )

        if not is_recent_article(
            published
        ):
            continue

        signature = title_signature(
            title
        )

        if (
            not signature
            or signature in seen_signatures
        ):
            continue

        keyword_score, keywords = analyze_title(
            title
        )

        if keyword_score == 0:
            continue

        seen_signatures.add(
            signature
        )

        recency_score = calculate_recency_score(
            published
        )

        source_score = calculate_source_score(
            title,
            source_name,
        )

        if keyword_score < 0:
            news_score = keyword_score
        else:
            news_score = (
                keyword_score
                + recency_score
                + source_score
            )

        news_items.append({
            "title": title,
            "source": source_name,
            "link": entry.get(
                "link",
                "",
            ),
            "published": published.strftime(
                "%Y-%m-%d %H:%M"
            ),
            "news_score": news_score,
            "keywords": " / ".join(
                keywords
            ),
        })

    return news_items


def summarize_company_news(news_items):
    if not news_items:
        return {
            "ニュース件数": 0,
            "ニューススコア": 0,
            "ニュース判定": "ニュースなし",
            "主要ニュース": "",
            "ニュース媒体": "",
            "材料キーワード": "",
            "ニュースURL": "",
        }

    sorted_news = sorted(
        news_items,
        key=lambda item: (
            item["news_score"],
            item["published"],
        ),
        reverse=True,
    )

    positive_news = [
        item
        for item in sorted_news
        if item["news_score"] > 0
    ]

    negative_news = [
        item
        for item in sorted_news
        if item["news_score"] < 0
    ]

    positive_total = sum(
        item["news_score"]
        for item in positive_news[:2]
    )

    negative_total = sum(
        item["news_score"]
        for item in negative_news[:2]
    )

    total_score = max(
        min(
            positive_total + negative_total,
            30,
        ),
        -30,
    )

    if total_score >= 15:
        judgement = "強い好材料"

    elif total_score >= 5:
        judgement = "好材料"

    elif total_score <= -15:
        judgement = "強い悪材料"

    elif total_score <= -5:
        judgement = "悪材料"

    else:
        judgement = "中立"

    if total_score < 0 and negative_news:
        top_news = min(
            negative_news,
            key=lambda item:
                item["news_score"],
        )

    elif positive_news:
        top_news = max(
            positive_news,
            key=lambda item:
                item["news_score"],
        )

    else:
        top_news = sorted_news[0]

    keyword_groups = [
        item["keywords"]
        for item in sorted_news[:4]
        if item["keywords"]
    ]

    return {
        "ニュース件数": len(
            news_items
        ),
        "ニューススコア": total_score,
        "ニュース判定": judgement,
        "主要ニュース": top_news[
            "title"
        ],
        "ニュース媒体": top_news[
            "source"
        ],
        "材料キーワード": " / ".join(
            keyword_groups
        ),
        "ニュースURL": top_news[
            "link"
        ],
    }


def calculate_combined_score(
    phoenix_score,
    news_score,
):
    combined = (
        float(phoenix_score)
        + float(news_score)
    )

    return int(
        max(
            min(
                round(combined),
                100,
            ),
            0,
        )
    )


def create_news_signals(report_df):
    results = []
    total = len(report_df)

    for number, row in enumerate(
        report_df.itertuples(index=False),
        start=1,
    ):
        company_name = str(
            getattr(
                row,
                "銘柄",
            )
        )

        ticker = str(
            getattr(
                row,
                "ticker",
            )
        )

        phoenix_score = float(
            getattr(
                row,
                "PHOENIX_SCORE",
            )
        )

        print(
            f"[{number}/{total}] "
            f"{ticker} {company_name}"
        )

        try:
            news_items = fetch_company_news(
                company_name
            )

            summary = summarize_company_news(
                news_items
            )

        except Exception as error:
            print(
                f"NEWS ERROR {ticker}: {error}"
            )

            summary = {
                "ニュース件数": 0,
                "ニューススコア": 0,
                "ニュース判定": "取得失敗",
                "主要ニュース": "",
                "ニュース媒体": "",
                "材料キーワード": "",
                "ニュースURL": "",
            }

        results.append({
            "銘柄": company_name,
            "ticker": ticker,
            "PHOENIX_SCORE": int(
                phoenix_score
            ),
            "ニュース件数": summary[
                "ニュース件数"
            ],
            "ニューススコア": summary[
                "ニューススコア"
            ],
            "総合スコア":
                calculate_combined_score(
                    phoenix_score,
                    summary[
                        "ニューススコア"
                    ],
                ),
            "ニュース判定": summary[
                "ニュース判定"
            ],
            "ニュース媒体": summary[
                "ニュース媒体"
            ],
            "主要ニュース": summary[
                "主要ニュース"
            ],
            "材料キーワード": summary[
                "材料キーワード"
            ],
            "ニュースURL": summary[
                "ニュースURL"
            ],
        })

        time.sleep(
            REQUEST_INTERVAL
        )

    result_df = pd.DataFrame(
        results
    )

    return result_df.sort_values(
        by=[
            "総合スコア",
            "ニューススコア",
            "PHOENIX_SCORE",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )


def print_results(df):
    print()
    print("=" * 110)
    print("PHOENIX NEWS SIGNAL TOP20")
    print("=" * 110)

    display_columns = [
        "銘柄",
        "ticker",
        "PHOENIX_SCORE",
        "ニュース件数",
        "ニューススコア",
        "総合スコア",
        "ニュース判定",
        "ニュース媒体",
        "主要ニュース",
    ]

    print(
        df[
            display_columns
        ]
        .head(20)
        .to_string(
            index=False
        )
    )


def save_results(df):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        f"保存完了 : {OUTPUT_FILE}"
    )


def main():
    print("=" * 110)
    print("PHOENIX NEWS SIGNAL ANALYZER")
    print("=" * 110)
    print()

    try:
        report_df, report_file = load_report()

        print(
            f"使用レポート : {report_file}"
        )

        print(
            f"ニュース分析銘柄数 : "
            f"{len(report_df)}"
        )

        print(
            f"対象期間 : 過去"
            f"{MAX_ARTICLE_AGE_DAYS}日"
        )

        print(
            "企業一致・材料記事・"
            "低品質媒体除外"
        )

        print()

        result_df = create_news_signals(
            report_df
        )

        print_results(
            result_df
        )

        save_results(
            result_df
        )

    except Exception as error:
        print(
            f"エラー: {error}"
        )


if __name__ == "__main__":
    main()