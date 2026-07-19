from __future__ import annotations

import argparse
import json
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
import requests
import yfinance as yf


# ============================================================
# PHOENIX Market Risk AI
#
# 海外株式・VIX・為替・ニュースを分析し、
# 日本株市場が始まる前の総合リスクを判定する。
#
# 出力:
#   data/market_risk_latest.json
#   data/market_risk_history.csv
#   reports/market_risk_YYYYMMDD_HHMMSS.txt
# ============================================================


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"

LATEST_JSON_PATH = DATA_DIR / "market_risk_latest.json"
HISTORY_CSV_PATH = DATA_DIR / "market_risk_history.csv"


MARKET_ASSETS: dict[str, dict[str, str]] = {
    "dow": {
        "name": "NYダウ",
        "ticker": "^DJI",
    },
    "sp500": {
        "name": "S&P500",
        "ticker": "^GSPC",
    },
    "nasdaq": {
        "name": "NASDAQ",
        "ticker": "^IXIC",
    },
    "sox": {
        "name": "SOX半導体指数",
        "ticker": "^SOX",
    },
    "vix": {
        "name": "VIX恐怖指数",
        "ticker": "^VIX",
    },
    "usd_jpy": {
        "name": "ドル円",
        "ticker": "JPY=X",
    },
    "nikkei": {
        "name": "日経平均",
        "ticker": "^N225",
    },
}


NEWS_QUERIES = [
    "株式市場 暴落 リスク",
    "米国株 急落 FRB 関税",
    "中東 戦争 地政学リスク 株価",
    "台湾海峡 緊張 株式市場",
    "日銀 金利 円高 株価",
    "半導体 輸出規制 株価",
]


HIGH_RISK_KEYWORDS: dict[str, int] = {
    "戦争": 8,
    "開戦": 10,
    "軍事攻撃": 10,
    "ミサイル": 7,
    "空爆": 9,
    "侵攻": 10,
    "非常事態": 8,
    "金融危機": 10,
    "信用不安": 8,
    "銀行破綻": 10,
    "デフォルト": 10,
    "債務不履行": 10,
    "緊急利上げ": 8,
    "追加関税": 7,
    "輸出規制": 6,
    "制裁強化": 6,
    "取引停止": 9,
    "暴落": 8,
    "急落": 5,
    "大幅安": 5,
    "地政学リスク": 5,
    "台湾海峡": 6,
    "中東情勢": 5,
    "原油急騰": 6,
    "円急騰": 6,
    "急激な円高": 7,
    "景気後退": 5,
    "リセッション": 5,
}


LOW_RISK_KEYWORDS: dict[str, int] = {
    "停戦": -4,
    "和平合意": -5,
    "関税撤回": -4,
    "利下げ期待": -2,
    "緊張緩和": -3,
    "市場安定": -2,
}


@dataclass
class AssetResult:
    key: str
    name: str
    ticker: str
    current: float | None
    previous: float | None
    change_pct: float | None
    score: int
    reason: str
    success: bool


@dataclass
class NewsResult:
    score: int
    matched_keywords: list[str]
    headlines: list[str]
    success: bool
    error: str


@dataclass
class MarketRiskResult:
    generated_at: str
    total_score: int
    risk_level: str
    risk_stars: str
    new_entry_policy: str
    position_policy: str
    cash_policy: str
    summary: str
    reasons: list[str]
    assets: dict[str, dict[str, Any]]
    news: dict[str, Any]


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
    except (AttributeError, OSError):
        pass


def ensure_directories() -> None:
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)

        if pd.isna(number):
            return None

        return number

    except (TypeError, ValueError):
        return None


def fetch_asset_history(
    ticker: str,
    retries: int = 3,
) -> pd.DataFrame:
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            history = yf.Ticker(ticker).history(
                period="10d",
                interval="1d",
                auto_adjust=False,
            )

            if history is None or history.empty:
                raise RuntimeError(
                    f"{ticker} の価格データが空です。"
                )

            if "Close" not in history.columns:
                raise RuntimeError(
                    f"{ticker} にClose列がありません。"
                )

            history = history.dropna(
                subset=["Close"],
            )

            if len(history) < 2:
                raise RuntimeError(
                    f"{ticker} の終値データが2日分ありません。"
                )

            return history

        except Exception as error:
            last_error = error

            if attempt < retries:
                time.sleep(2.0 * attempt)

    raise RuntimeError(
        f"{ticker} の取得に失敗しました: {last_error}"
    )


def calculate_change_pct(
    current: float,
    previous: float,
) -> float:
    if previous == 0:
        return 0.0

    return ((current / previous) - 1.0) * 100.0


def score_stock_index(
    name: str,
    change_pct: float,
) -> tuple[int, str]:
    if change_pct <= -4.0:
        return 25, f"{name}が{change_pct:+.2f}%の歴史的急落"

    if change_pct <= -3.0:
        return 20, f"{name}が{change_pct:+.2f}%の大幅急落"

    if change_pct <= -2.0:
        return 15, f"{name}が{change_pct:+.2f}%の急落"

    if change_pct <= -1.0:
        return 8, f"{name}が{change_pct:+.2f}%下落"

    if change_pct >= 2.0:
        return -4, f"{name}が{change_pct:+.2f}%上昇"

    if change_pct >= 1.0:
        return -2, f"{name}が{change_pct:+.2f}%上昇"

    return 0, f"{name}は{change_pct:+.2f}%で小動き"


def score_sox(
    change_pct: float,
) -> tuple[int, str]:
    if change_pct <= -6.0:
        return 25, f"SOX半導体指数が{change_pct:+.2f}%の歴史的急落"

    if change_pct <= -4.0:
        return 20, f"SOX半導体指数が{change_pct:+.2f}%の大幅急落"

    if change_pct <= -3.0:
        return 15, f"SOX半導体指数が{change_pct:+.2f}%の急落"

    if change_pct <= -2.0:
        return 10, f"SOX半導体指数が{change_pct:+.2f}%下落"

    if change_pct >= 3.0:
        return -4, f"SOX半導体指数が{change_pct:+.2f}%上昇"

    return 0, f"SOX半導体指数は{change_pct:+.2f}%"


def score_vix(
    current: float,
    change_pct: float,
) -> tuple[int, str]:
    score = 0
    details: list[str] = []

    if current >= 50:
        score += 35
        details.append(f"VIXが{current:.2f}のパニック水準")

    elif current >= 40:
        score += 30
        details.append(f"VIXが{current:.2f}の極端な恐怖水準")

    elif current >= 30:
        score += 22
        details.append(f"VIXが{current:.2f}の強い警戒水準")

    elif current >= 25:
        score += 15
        details.append(f"VIXが{current:.2f}の警戒水準")

    elif current >= 20:
        score += 8
        details.append(f"VIXが{current:.2f}まで上昇")

    else:
        details.append(f"VIXは{current:.2f}")

    if change_pct >= 40:
        score += 20
        details.append(f"前日比{change_pct:+.2f}%急騰")

    elif change_pct >= 25:
        score += 15
        details.append(f"前日比{change_pct:+.2f}%急騰")

    elif change_pct >= 15:
        score += 10
        details.append(f"前日比{change_pct:+.2f}%上昇")

    elif change_pct >= 8:
        score += 5
        details.append(f"前日比{change_pct:+.2f}%上昇")

    elif change_pct <= -15:
        score -= 4
        details.append(f"前日比{change_pct:+.2f}%低下")

    return score, "・".join(details)


def score_usd_jpy(
    change_pct: float,
) -> tuple[int, str]:
    # JPY=Xは「1ドル当たりの円」。
    # マイナスは円高方向、プラスは円安方向。
    if change_pct <= -2.5:
        return 18, f"ドル円が{change_pct:+.2f}%変動し急激な円高"

    if change_pct <= -1.5:
        return 12, f"ドル円が{change_pct:+.2f}%変動し強い円高"

    if change_pct <= -0.8:
        return 7, f"ドル円が{change_pct:+.2f}%変動し円高"

    if change_pct >= 2.5:
        return 6, f"ドル円が{change_pct:+.2f}%変動し急激な円安"

    if change_pct >= 1.5:
        return 3, f"ドル円が{change_pct:+.2f}%変動し円安"

    return 0, f"ドル円は{change_pct:+.2f}%の変動"


def score_nikkei(
    change_pct: float,
) -> tuple[int, str]:
    if change_pct <= -4.0:
        return 15, f"日経平均が{change_pct:+.2f}%の大幅急落"

    if change_pct <= -3.0:
        return 12, f"日経平均が{change_pct:+.2f}%の急落"

    if change_pct <= -2.0:
        return 8, f"日経平均が{change_pct:+.2f}%下落"

    return 0, f"日経平均は{change_pct:+.2f}%"


def analyze_asset(
    key: str,
    asset: dict[str, str],
) -> AssetResult:
    name = asset["name"]
    ticker = asset["ticker"]

    try:
        history = fetch_asset_history(ticker)

        previous = safe_float(
            history["Close"].iloc[-2]
        )
        current = safe_float(
            history["Close"].iloc[-1]
        )

        if previous is None or current is None:
            raise RuntimeError(
                "終値を数値として取得できませんでした。"
            )

        change_pct = calculate_change_pct(
            current=current,
            previous=previous,
        )

        if key in {"dow", "sp500", "nasdaq"}:
            score, reason = score_stock_index(
                name=name,
                change_pct=change_pct,
            )

        elif key == "sox":
            score, reason = score_sox(
                change_pct=change_pct,
            )

        elif key == "vix":
            score, reason = score_vix(
                current=current,
                change_pct=change_pct,
            )

        elif key == "usd_jpy":
            score, reason = score_usd_jpy(
                change_pct=change_pct,
            )

        elif key == "nikkei":
            score, reason = score_nikkei(
                change_pct=change_pct,
            )

        else:
            score = 0
            reason = f"{name}は{change_pct:+.2f}%"

        return AssetResult(
            key=key,
            name=name,
            ticker=ticker,
            current=round(current, 4),
            previous=round(previous, 4),
            change_pct=round(change_pct, 4),
            score=score,
            reason=reason,
            success=True,
        )

    except Exception as error:
        return AssetResult(
            key=key,
            name=name,
            ticker=ticker,
            current=None,
            previous=None,
            change_pct=None,
            score=0,
            reason=f"{name}の取得失敗",
            success=False,
        )


def fetch_google_news_rss(
    query: str,
    timeout: int = 10,
) -> list[str]:
    encoded_query = quote_plus(query)

    url = (
        "https://news.google.com/rss/search"
        f"?q={encoded_query}"
        "&hl=ja"
        "&gl=JP"
        "&ceid=JP:ja"
    )

    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/130.0 Safari/537.36"
            )
        },
    )

    response.raise_for_status()

    root = ET.fromstring(response.content)

    headlines: list[str] = []

    for item in root.findall(".//item"):
        title_element = item.find("title")

        if title_element is None:
            continue

        title = str(
            title_element.text or ""
        ).strip()

        if title:
            headlines.append(title)

    return headlines


def analyze_news(
    enabled: bool = True,
    max_headlines: int = 30,
) -> NewsResult:
    if not enabled:
        return NewsResult(
            score=0,
            matched_keywords=[],
            headlines=[],
            success=True,
            error="ニュース分析は無効です。",
        )

    all_headlines: list[str] = []
    errors: list[str] = []

    for query in NEWS_QUERIES:
        try:
            headlines = fetch_google_news_rss(query)
            all_headlines.extend(
                headlines[:8]
            )

        except Exception as error:
            errors.append(
                f"{query}: {error}"
            )

    unique_headlines: list[str] = []
    seen: set[str] = set()

    for headline in all_headlines:
        normalized = headline.strip().lower()

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        unique_headlines.append(
            headline.strip()
        )

        if len(unique_headlines) >= max_headlines:
            break

    matched_keywords: list[str] = []
    raw_score = 0

    combined_text = "\n".join(
        unique_headlines
    )

    for keyword, points in HIGH_RISK_KEYWORDS.items():
        count = combined_text.count(keyword)

        if count > 0:
            contribution = points * min(
                count,
                2,
            )
            raw_score += contribution
            matched_keywords.append(
                f"{keyword}({count})"
            )

    for keyword, points in LOW_RISK_KEYWORDS.items():
        count = combined_text.count(keyword)

        if count > 0:
            contribution = points * min(
                count,
                2,
            )
            raw_score += contribution
            matched_keywords.append(
                f"{keyword}({count})"
            )

    score = max(
        -10,
        min(
            25,
            raw_score,
        ),
    )

    success = len(unique_headlines) > 0

    return NewsResult(
        score=score,
        matched_keywords=matched_keywords,
        headlines=unique_headlines,
        success=success,
        error=" | ".join(errors),
    )


def calculate_correlation_bonus(
    assets: dict[str, AssetResult],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    negative_major_markets = 0

    for key in ["dow", "sp500", "nasdaq", "sox"]:
        result = assets.get(key)

        if (
            result
            and result.success
            and result.change_pct is not None
            and result.change_pct <= -1.5
        ):
            negative_major_markets += 1

    if negative_major_markets >= 4:
        score += 15
        reasons.append(
            "ダウ・S&P500・NASDAQ・SOXが同時下落"
        )

    elif negative_major_markets >= 3:
        score += 10
        reasons.append(
            "米国主要市場3指数以上が同時下落"
        )

    elif negative_major_markets >= 2:
        score += 5
        reasons.append(
            "米国主要市場が複数同時下落"
        )

    vix = assets.get("vix")
    nasdaq = assets.get("nasdaq")
    sox = assets.get("sox")

    if (
        vix
        and vix.success
        and vix.change_pct is not None
        and vix.change_pct >= 15
        and (
            (
                nasdaq
                and nasdaq.success
                and nasdaq.change_pct is not None
                and nasdaq.change_pct <= -2
            )
            or (
                sox
                and sox.success
                and sox.change_pct is not None
                and sox.change_pct <= -3
            )
        )
    ):
        score += 10
        reasons.append(
            "ハイテク株急落とVIX急騰が同時発生"
        )

    usd_jpy = assets.get("usd_jpy")

    if (
        usd_jpy
        and usd_jpy.success
        and usd_jpy.change_pct is not None
        and usd_jpy.change_pct <= -1.0
        and negative_major_markets >= 2
    ):
        score += 7
        reasons.append(
            "米国株下落と円高が同時進行"
        )

    return score, reasons


def determine_risk_level(
    score: int,
) -> tuple[str, str]:
    if score >= 80:
        return "CRITICAL", "★★★★★"

    if score >= 60:
        return "HIGH", "★★★★☆"

    if score >= 35:
        return "CAUTION", "★★★☆☆"

    if score >= 15:
        return "WATCH", "★★☆☆☆"

    return "LOW", "★☆☆☆☆"


def determine_policy(
    risk_level: str,
) -> tuple[str, str, str]:
    if risk_level == "CRITICAL":
        return (
            "原則として新規買い停止",
            "保有ポジション縮小・逆指値確認",
            "現金比率80%以上を検討",
        )

    if risk_level == "HIGH":
        return (
            "新規買いを強く制限",
            "通常ロットの25%から50%",
            "現金比率60%以上を検討",
        )

    if risk_level == "CAUTION":
        return (
            "新規買いは厳選",
            "通常ロットの50%程度",
            "現金比率40%以上を検討",
        )

    if risk_level == "WATCH":
        return (
            "エントリー条件を通常より厳格化",
            "通常ロットの75%程度",
            "現金余力を確保",
        )

    return (
        "通常のエントリー判定",
        "通常ロット",
        "通常の資金管理",
    )


def build_summary(
    risk_level: str,
    total_score: int,
) -> str:
    summaries = {
        "CRITICAL": (
            "市場全体で極めて強い警戒シグナルが出ています。"
            "急落・ギャップダウン・流動性低下に最大限警戒します。"
        ),
        "HIGH": (
            "海外市場や恐怖指数に強い悪化が見られます。"
            "日本株の新規エントリーを大幅に制限します。"
        ),
        "CAUTION": (
            "複数の市場リスクが確認されています。"
            "銘柄選定とポジションサイズを慎重にします。"
        ),
        "WATCH": (
            "軽度の警戒材料があります。"
            "通常より厳しい条件でエントリーを判断します。"
        ),
        "LOW": (
            "現時点で大きな市場警戒シグナルは確認されていません。"
        ),
    }

    return (
        f"{summaries[risk_level]}"
        f" 総合リスクスコアは{total_score}/100です。"
    )


def run_market_risk_analysis(
    enable_news: bool = True,
) -> MarketRiskResult:
    asset_results: dict[str, AssetResult] = {}

    print("=" * 68)
    print("PHOENIX MARKET RISK AI")
    print("=" * 68)
    print("海外市場・VIX・為替を取得しています。")
    print()

    for key, asset in MARKET_ASSETS.items():
        print(
            f"取得中: {asset['name']} "
            f"({asset['ticker']})"
        )

        result = analyze_asset(
            key=key,
            asset=asset,
        )

        asset_results[key] = result

        if result.success:
            print(
                f"  現在値: {result.current:,.2f} "
                f"前日比: {result.change_pct:+.2f}% "
                f"Risk: {result.score:+d}"
            )
        else:
            print(
                f"  WARNING: {result.reason}"
            )

    print()
    print("ニュースリスクを分析しています。")

    news_result = analyze_news(
        enabled=enable_news,
    )

    if news_result.success:
        print(
            f"  ニュースRisk: {news_result.score:+d}"
        )
    else:
        print(
            "  WARNING: ニュースを取得できませんでした。"
        )

    base_score = sum(
        result.score
        for result in asset_results.values()
    )

    correlation_score, correlation_reasons = (
        calculate_correlation_bonus(
            asset_results
        )
    )

    raw_total_score = (
        base_score
        + news_result.score
        + correlation_score
    )

    total_score = max(
        0,
        min(
            100,
            raw_total_score,
        ),
    )

    risk_level, risk_stars = determine_risk_level(
        total_score
    )

    (
        new_entry_policy,
        position_policy,
        cash_policy,
    ) = determine_policy(
        risk_level
    )

    reasons: list[str] = []

    sorted_assets = sorted(
        asset_results.values(),
        key=lambda item: item.score,
        reverse=True,
    )

    for result in sorted_assets:
        if result.score > 0:
            reasons.append(
                f"{result.reason}（+{result.score}）"
            )

    if news_result.score > 0:
        reasons.append(
            f"ニュース・地政学リスク（+{news_result.score}）"
        )

    reasons.extend(
        f"{reason}（相関加点）"
        for reason in correlation_reasons
    )

    if not reasons:
        reasons.append(
            "大きな警戒シグナルは確認されていません。"
        )

    result = MarketRiskResult(
        generated_at=datetime.now().isoformat(
            timespec="seconds"
        ),
        total_score=total_score,
        risk_level=risk_level,
        risk_stars=risk_stars,
        new_entry_policy=new_entry_policy,
        position_policy=position_policy,
        cash_policy=cash_policy,
        summary=build_summary(
            risk_level=risk_level,
            total_score=total_score,
        ),
        reasons=reasons,
        assets={
            key: asdict(asset_result)
            for key, asset_result in asset_results.items()
        },
        news=asdict(news_result),
    )

    return result


def format_asset_line(
    asset: dict[str, Any],
) -> str:
    if not asset.get("success"):
        return (
            f"{asset.get('name', '-'):<15} "
            f"取得失敗"
        )

    current = asset.get("current")
    change_pct = asset.get("change_pct")
    score = int(asset.get("score", 0))

    return (
        f"{asset.get('name', '-'):<15} "
        f"{current:>12,.2f} "
        f"{change_pct:>+8.2f}% "
        f"Risk {score:>+3d}"
    )


def build_text_report(
    result: MarketRiskResult,
) -> str:
    lines: list[str] = []

    lines.append("=" * 68)
    lines.append("PHOENIX MARKET RISK AI")
    lines.append("=" * 68)
    lines.append(f"判定時刻       : {result.generated_at}")
    lines.append(
        f"総合リスク     : {result.risk_stars} "
        f"{result.risk_level}"
    )
    lines.append(
        f"リスクスコア   : {result.total_score}/100"
    )
    lines.append("")

    lines.append("[ 海外市場・為替 ]")
    lines.append(
        f"{'対象':<15} {'現在値':>12} "
        f"{'前日比':>9} {'スコア':>8}"
    )
    lines.append("-" * 68)

    asset_order = [
        "dow",
        "sp500",
        "nasdaq",
        "sox",
        "vix",
        "usd_jpy",
        "nikkei",
    ]

    for key in asset_order:
        asset = result.assets.get(key)

        if asset:
            lines.append(
                format_asset_line(asset)
            )

    lines.append("")
    lines.append("[ 主な警戒理由 ]")

    for reason in result.reasons:
        lines.append(f"・{reason}")

    lines.append("")
    lines.append("[ PHOENIX防御モード ]")
    lines.append(
        f"新規エントリー : {result.new_entry_policy}"
    )
    lines.append(
        f"ポジション     : {result.position_policy}"
    )
    lines.append(
        f"現金比率       : {result.cash_policy}"
    )

    lines.append("")
    lines.append("[ AIコメント ]")
    lines.append(result.summary)

    news_data = result.news
    headlines = news_data.get(
        "headlines",
        [],
    )

    if headlines:
        lines.append("")
        lines.append("[ リスク関連ニュース ]")

        for headline in headlines[:10]:
            lines.append(f"・{headline}")

    lines.append("")
    lines.append("=" * 68)
    lines.append(
        "注意: この判定は市場リスク管理用であり、"
        "将来の株価や損失回避を保証するものではありません。"
    )
    lines.append("=" * 68)

    return "\n".join(lines)


def save_latest_json(
    result: MarketRiskResult,
) -> None:
    with LATEST_JSON_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            asdict(result),
            file,
            ensure_ascii=False,
            indent=2,
        )


def save_history_csv(
    result: MarketRiskResult,
) -> None:
    row: dict[str, Any] = {
        "generated_at": result.generated_at,
        "total_score": result.total_score,
        "risk_level": result.risk_level,
        "risk_stars": result.risk_stars,
        "new_entry_policy": result.new_entry_policy,
        "position_policy": result.position_policy,
        "cash_policy": result.cash_policy,
    }

    for key, asset in result.assets.items():
        row[f"{key}_current"] = asset.get(
            "current"
        )
        row[f"{key}_change_pct"] = asset.get(
            "change_pct"
        )
        row[f"{key}_score"] = asset.get(
            "score"
        )
        row[f"{key}_success"] = asset.get(
            "success"
        )

    row["news_score"] = result.news.get(
        "score",
        0,
    )

    new_df = pd.DataFrame(
        [row]
    )

    if HISTORY_CSV_PATH.exists():
        try:
            old_df = pd.read_csv(
                HISTORY_CSV_PATH,
                encoding="utf-8-sig",
            )

            combined_df = pd.concat(
                [
                    old_df,
                    new_df,
                ],
                ignore_index=True,
            )

        except Exception:
            combined_df = new_df

    else:
        combined_df = new_df

    combined_df.to_csv(
        HISTORY_CSV_PATH,
        index=False,
        encoding="utf-8-sig",
    )


def save_text_report(
    report_text: str,
) -> Path:
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    report_path = (
        REPORT_DIR
        / f"market_risk_{timestamp}.txt"
    )

    report_path.write_text(
        report_text,
        encoding="utf-8",
    )

    return report_path


def load_latest_market_risk() -> dict[str, Any] | None:
    """
    Trade EngineやPrice Monitorから使用する関数。

    戻り値例:
    {
        "total_score": 72,
        "risk_level": "HIGH",
        "new_entry_policy": "新規買いを強く制限",
        ...
    }
    """

    if not LATEST_JSON_PATH.exists():
        return None

    try:
        with LATEST_JSON_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return None

        return data

    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None


def is_new_entry_allowed() -> bool:
    """
    Trade Engineから新規買いを許可するか確認する関数。

    CRITICAL:
        新規買い停止

    HIGH:
        原則停止

    CAUTION以下:
        Trade Engine側の条件付きで許可
    """

    latest = load_latest_market_risk()

    if latest is None:
        # リスク情報がない場合は安全側に倒す。
        return False

    risk_level = str(
        latest.get(
            "risk_level",
            "",
        )
    ).upper()

    return risk_level not in {
        "CRITICAL",
        "HIGH",
    }


def get_position_multiplier() -> float:
    """
    リスクレベルごとの推奨ポジション倍率。

    CRITICAL: 0.00
    HIGH    : 0.25
    CAUTION : 0.50
    WATCH   : 0.75
    LOW     : 1.00
    """

    latest = load_latest_market_risk()

    if latest is None:
        return 0.0

    risk_level = str(
        latest.get(
            "risk_level",
            "",
        )
    ).upper()

    multipliers = {
        "CRITICAL": 0.00,
        "HIGH": 0.25,
        "CAUTION": 0.50,
        "WATCH": 0.75,
        "LOW": 1.00,
    }

    return multipliers.get(
        risk_level,
        0.0,
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "海外市場・VIX・為替・ニュースから"
            "日本株市場の暴落リスクを判定します。"
        )
    )

    parser.add_argument(
        "--no-news",
        action="store_true",
        help="ニュース取得を行わず、市場データのみで判定します。",
    )

    return parser.parse_args()


def main() -> int:
    configure_console()
    ensure_directories()

    args = parse_arguments()

    try:
        result = run_market_risk_analysis(
            enable_news=not args.no_news,
        )

        report_text = build_text_report(
            result
        )

        print()
        print(report_text)

        save_latest_json(
            result
        )

        save_history_csv(
            result
        )

        report_path = save_text_report(
            report_text
        )

        print()
        print(
            f"最新リスク保存: {LATEST_JSON_PATH}"
        )
        print(
            f"履歴保存      : {HISTORY_CSV_PATH}"
        )
        print(
            f"レポート保存  : {report_path}"
        )

        return 0

    except KeyboardInterrupt:
        print()
        print("処理を中断しました。")
        return 130

    except Exception as error:
        print()
        print(
            f"ERROR: Market Risk AI実行失敗: {error}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())