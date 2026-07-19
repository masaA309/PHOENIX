# portfolio_manager.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd


# =========================================================
# PHOENIX v4.1 Portfolio Manager AI
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"

INPUT_FILE = REPORT_DIR / "price_watchlist.csv"
SECTOR_MASTER_FILE = DATA_DIR / "sector_master.csv"

OUTPUT_FILE = REPORT_DIR / "portfolio_watchlist.csv"
SUMMARY_FILE = REPORT_DIR / "portfolio_manager_summary.json"
TEXT_REPORT_FILE = REPORT_DIR / "portfolio_manager_report.txt"
MARKET_REGIME_FILE = REPORT_DIR / "market_regime.json"

ACCOUNT_CAPITAL = 300_000
MAX_SELECTED = 3
MAX_PER_SECTOR = 1
SECOND_PASS_MAX_PER_SECTOR = 2

BUY_BONUS = 10.0
WATCH_BONUS = 4.0

AI_WEIGHT = 0.45
PHOENIX_WEIGHT = 0.35
TRADE_WEIGHT = 0.20

MIN_PORTFOLIO_SCORE = 55.0

DEFAULT_SECTOR = "未分類"


# =========================================================
# セクター辞書
# 必要に応じて data/sector_master.csv で上書き可能
# =========================================================

TICKER_SECTOR_MAP: dict[str, str] = {
    "1605.T": "エネルギー",
    "2413.T": "情報通信・サービス",
    "3401.T": "素材・化学",
    "3405.T": "素材・化学",
    "3436.T": "半導体・電子部品",
    "3697.T": "情報通信・サービス",
    "4005.T": "素材・化学",
    "4188.T": "素材・化学",
    "4661.T": "消費・レジャー",
    "4902.T": "電機・精密",
    "5406.T": "鉄鋼・非鉄",
    "6724.T": "電機・精密",
    "6988.T": "電機・精密",
    "7733.T": "電機・精密",
    "8630.T": "金融・保険",
    "9001.T": "運輸",
    "9101.T": "海運",
    "9107.T": "海運",
    "9501.T": "電力・ガス",
    "9984.T": "情報通信・サービス",
}

NAME_KEYWORD_SECTORS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("銀行", "フィナンシャル", "証券", "保険", "SOMPO", "MS&AD"), "金融・保険"),
    (("電力", "ガス"), "電力・ガス"),
    (("郵船", "汽船", "海運"), "海運"),
    (("鉄道", "電鉄", "旅客鉄道"), "運輸"),
    (("航空", "ANA", "JAL"), "運輸"),
    (("製鋼", "鉄鋼", "金属", "アルミ"), "鉄鋼・非鉄"),
    (("化学", "クラレ", "帝人", "UBE", "トクヤマ"), "素材・化学"),
    (("電工", "電機", "電子", "半導体", "SUMCO"), "電機・精密"),
    (("ソフトバンク", "SHIFT", "エムスリー", "情報", "通信"), "情報通信・サービス"),
    (("INPEX", "石油", "エネルギー"), "エネルギー"),
    (("自動車", "トヨタ", "ホンダ", "日産", "マツダ", "スズキ"), "自動車"),
    (("食品", "飲料", "水産", "ビール"), "食品"),
    (("製薬", "薬品", "ファーマ", "エーザイ"), "医薬品"),
    (("建設", "工業", "重工"), "機械・建設"),
    (("百貨店", "イオン", "セブン", "ファーストリテイリング"), "小売"),
    (("オリエンタルランド", "レジャー"), "消費・レジャー"),
)


# =========================================================
# 共通処理
# =========================================================

def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default

        result = float(value)

        if not math.isfinite(result):
            return default

        return result

    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(safe_float(value, default)))
    except (TypeError, ValueError):
        return default


def read_csv_safe(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame()

    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(file_path, encoding=encoding)
        except Exception as error:
            last_error = error

    if last_error is not None:
        raise last_error

    return pd.DataFrame()


def save_json(file_path: Path, data: dict[str, Any]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)



def load_market_regime() -> dict[str, Any]:
    if not MARKET_REGIME_FILE.exists():
        return {"regime": "SIDEWAYS", "settings": {}}
    try:
        data = json.loads(MARKET_REGIME_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"regime": "SIDEWAYS", "settings": {}}
    except (OSError, json.JSONDecodeError):
        return {"regime": "SIDEWAYS", "settings": {}}


def apply_market_regime() -> dict[str, Any]:
    global MAX_SELECTED, MIN_PORTFOLIO_SCORE
    data = load_market_regime()
    settings = data.get("settings", {})
    if not isinstance(settings, dict):
        settings = {}
    MAX_SELECTED = max(1, safe_int(settings.get("max_positions", MAX_SELECTED), MAX_SELECTED))
    adjustment = safe_float(settings.get("entry_score_adjustment", 0.0), 0.0)
    MIN_PORTFOLIO_SCORE = max(45.0, min(85.0, 55.0 + adjustment * 0.5))
    return data

# =========================================================
# データ読込
# =========================================================

def load_watchlist() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Trade Engine監視リストがありません: {INPUT_FILE}"
        )

    data = read_csv_safe(INPUT_FILE)

    if data.empty:
        raise ValueError("price_watchlist.csv が空です。")

    required_columns = {
        "銘柄",
        "ticker",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "Trade判定",
        "ロット比率",
        "基準価格",
        "押し目価格",
        "利確価格",
        "損切価格",
    }

    missing = required_columns - set(data.columns)

    if missing:
        raise ValueError(
            "price_watchlist.csv に必要な列がありません: "
            + ", ".join(sorted(missing))
        )

    numeric_columns = [
        "AI判断点",
        "PHOENIX_SCORE",
        "ロット比率",
        "基準価格",
        "押し目価格",
        "利確価格",
        "損切価格",
        "MarketRiskScore",
    ]

    for column in numeric_columns:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    data["ticker"] = data["ticker"].astype(str).str.strip()
    data["銘柄"] = data["銘柄"].astype(str).str.strip()
    data["Trade判定"] = (
        data["Trade判定"].astype(str).str.strip().str.upper()
    )

    data = data[
        data["Trade判定"].isin(["BUY", "WATCH"])
    ].copy()

    data = data.dropna(
        subset=[
            "ticker",
            "銘柄",
            "AI判断点",
            "PHOENIX_SCORE",
            "押し目価格",
            "利確価格",
            "損切価格",
        ]
    )

    if data.empty:
        raise ValueError("Portfolio Managerの対象銘柄がありません。")

    return data.reset_index(drop=True)


def load_sector_master() -> dict[str, str]:
    mapping = dict(TICKER_SECTOR_MAP)

    if not SECTOR_MASTER_FILE.exists():
        return mapping

    master = read_csv_safe(SECTOR_MASTER_FILE)

    if master.empty:
        return mapping

    ticker_column = next(
        (
            column
            for column in ("ticker", "Ticker", "コード")
            if column in master.columns
        ),
        None,
    )

    sector_column = next(
        (
            column
            for column in ("セクター", "業種", "sector", "Sector")
            if column in master.columns
        ),
        None,
    )

    if ticker_column is None or sector_column is None:
        return mapping

    for _, row in master.iterrows():
        ticker = str(row[ticker_column]).strip()
        sector = str(row[sector_column]).strip()

        if ticker and sector and sector.lower() != "nan":
            mapping[ticker] = sector

    return mapping


# =========================================================
# セクター・スコア
# =========================================================

def infer_sector(
    ticker: str,
    company_name: str,
    sector_map: dict[str, str],
) -> str:
    if ticker in sector_map:
        return sector_map[ticker]

    normalized_name = str(company_name).strip()

    for keywords, sector in NAME_KEYWORD_SECTORS:
        if any(keyword in normalized_name for keyword in keywords):
            return sector

    return DEFAULT_SECTOR


def trade_score(trade_decision: str) -> float:
    if trade_decision == "BUY":
        return 100.0

    if trade_decision == "WATCH":
        return 70.0

    return 0.0


def market_risk_factor(row: pd.Series) -> float:
    level = str(row.get("MarketRiskLevel", "")).strip().upper()
    score = safe_float(row.get("MarketRiskScore", 50.0), 50.0)

    if level in {"DANGER", "STOP", "CRITICAL"}:
        return 0.20

    if level in {"HIGH", "RISK"}:
        return 0.50

    if level == "WATCH":
        return 0.80

    if level in {"SAFE", "LOW", "NORMAL"}:
        return 1.00

    if score >= 80:
        return 0.40

    if score >= 60:
        return 0.65

    if score >= 40:
        return 0.80

    return 1.00


def calculate_portfolio_score(row: pd.Series) -> float:
    ai_score = safe_float(row["AI判断点"])
    phoenix_score = safe_float(row["PHOENIX_SCORE"])
    decision_score = trade_score(str(row["Trade判定"]))

    raw_score = (
        ai_score * AI_WEIGHT
        + phoenix_score * PHOENIX_WEIGHT
        + decision_score * TRADE_WEIGHT
    )

    adjusted = raw_score * market_risk_factor(row)

    if str(row["Trade判定"]).upper() == "BUY":
        adjusted += BUY_BONUS
    else:
        adjusted += WATCH_BONUS

    return round(min(max(adjusted, 0.0), 100.0), 2)


def risk_reward_ratio(row: pd.Series) -> float:
    entry = safe_float(row["押し目価格"])
    target = safe_float(row["利確価格"])
    stop = safe_float(row["損切価格"])

    risk = entry - stop
    reward = target - entry

    if risk <= 0:
        return 0.0

    return round(reward / risk, 3)


# =========================================================
# 分散選定
# =========================================================

def select_portfolio(data: pd.DataFrame) -> pd.DataFrame:
    work = data.copy()

    sector_map = load_sector_master()

    work["セクター"] = work.apply(
        lambda row: infer_sector(
            str(row["ticker"]),
            str(row["銘柄"]),
            sector_map,
        ),
        axis=1,
    )

    work["リスクリワード"] = work.apply(
        risk_reward_ratio,
        axis=1,
    )

    work["PortfolioScore"] = work.apply(
        calculate_portfolio_score,
        axis=1,
    )

    work["_trade_priority"] = work["Trade判定"].map(
        {"BUY": 0, "WATCH": 1}
    ).fillna(9)

    work = work.sort_values(
        by=[
            "_trade_priority",
            "PortfolioScore",
            "AI判断点",
            "PHOENIX_SCORE",
            "リスクリワード",
        ],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)

    selected_indexes: list[int] = []
    sector_counts: dict[str, int] = {}

    # 1巡目: 原則1セクター1銘柄
    for index, row in work.iterrows():
        if len(selected_indexes) >= MAX_SELECTED:
            break

        if safe_float(row["PortfolioScore"]) < MIN_PORTFOLIO_SCORE:
            continue

        sector = str(row["セクター"])

        if sector_counts.get(sector, 0) >= MAX_PER_SECTOR:
            continue

        selected_indexes.append(index)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    # 2巡目: 候補不足時のみ同一セクター2銘柄まで許可
    if len(selected_indexes) < MAX_SELECTED:
        for index, row in work.iterrows():
            if len(selected_indexes) >= MAX_SELECTED:
                break

            if index in selected_indexes:
                continue

            if safe_float(row["PortfolioScore"]) < MIN_PORTFOLIO_SCORE:
                continue

            sector = str(row["セクター"])

            if sector_counts.get(sector, 0) >= SECOND_PASS_MAX_PER_SECTOR:
                continue

            selected_indexes.append(index)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

    selected_set = set(selected_indexes)

    work["Portfolio判定"] = "補欠"
    work["選定理由"] = "上位候補だが最大保有数・分散条件により補欠"

    for index, row in work.iterrows():
        if safe_float(row["PortfolioScore"]) < MIN_PORTFOLIO_SCORE:
            work.at[index, "Portfolio判定"] = "見送り"
            work.at[index, "選定理由"] = "PortfolioScoreが基準未満"
        elif index in selected_set:
            work.at[index, "Portfolio判定"] = "採用"
            work.at[index, "選定理由"] = (
                f"{row['セクター']}枠で採用 / "
                f"PortfolioScore {safe_float(row['PortfolioScore']):.2f}"
            )

    selected = work[work["Portfolio判定"] == "採用"].copy()

    if selected.empty:
        work["資金配分比率"] = 0.0
        work["想定配分額"] = 0
    else:
        total_score = safe_float(selected["PortfolioScore"].sum())

        work["資金配分比率"] = 0.0
        work["想定配分額"] = 0

        for index in selected.index:
            score = safe_float(work.at[index, "PortfolioScore"])

            allocation = (
                score / total_score
                if total_score > 0
                else 1.0 / len(selected)
            )

            work.at[index, "資金配分比率"] = round(allocation, 4)
            work.at[index, "想定配分額"] = int(
                round(ACCOUNT_CAPITAL * allocation)
            )

    work["Portfolio順位"] = range(1, len(work) + 1)

    columns = [
        "Portfolio順位",
        "銘柄",
        "ticker",
        "セクター",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "Trade判定",
        "PortfolioScore",
        "リスクリワード",
        "資金配分比率",
        "想定配分額",
        "Portfolio判定",
        "選定理由",
    ]

    remaining = [
        column
        for column in work.columns
        if column not in columns and not column.startswith("_")
    ]

    return work[columns + remaining].copy()


# =========================================================
# 保存・表示
# =========================================================

def build_summary(result: pd.DataFrame) -> dict[str, Any]:
    selected = result[result["Portfolio判定"] == "採用"].copy()
    reserve = result[result["Portfolio判定"] == "補欠"].copy()
    rejected = result[result["Portfolio判定"] == "見送り"].copy()

    sector_counts = (
        selected["セクター"].value_counts().to_dict()
        if not selected.empty
        else {}
    )

    return {
        "version": "PHOENIX v4.1",
        "generated_at": now_text(),
        "account_capital_yen": ACCOUNT_CAPITAL,
        "settings": {
            "maximum_selected": MAX_SELECTED,
            "maximum_per_sector_first_pass": MAX_PER_SECTOR,
            "maximum_per_sector_second_pass": SECOND_PASS_MAX_PER_SECTOR,
            "minimum_portfolio_score": MIN_PORTFOLIO_SCORE,
        },
        "result": {
            "input_count": len(result),
            "selected_count": len(selected),
            "reserve_count": len(reserve),
            "rejected_count": len(rejected),
            "selected_sectors": sector_counts,
            "selected_tickers": selected["ticker"].astype(str).tolist(),
        },
    }


def save_outputs(
    result: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    save_json(SUMMARY_FILE, summary)

    selected = result[result["Portfolio判定"] == "採用"].copy()

    with TEXT_REPORT_FILE.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write("PHOENIX PORTFOLIO MANAGER REPORT\n")
        file.write(now_text() + "\n")
        file.write("=" * 120 + "\n")
        file.write(f"口座資金: {ACCOUNT_CAPITAL:,}円\n")
        file.write(f"入力候補: {len(result)}件\n")
        file.write(f"採用候補: {len(selected)}件\n")
        file.write("\n")

        if selected.empty:
            file.write("採用候補はありません。\n")
        else:
            file.write(
                selected[
                    [
                        "Portfolio順位",
                        "銘柄",
                        "ticker",
                        "セクター",
                        "Trade判定",
                        "AI判断点",
                        "PHOENIX_SCORE",
                        "PortfolioScore",
                        "資金配分比率",
                        "想定配分額",
                    ]
                ].to_string(index=False)
            )
            file.write("\n")


def print_result(
    result: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    print("=" * 120)
    print("PHOENIX PORTFOLIO MANAGER AI")
    print("=" * 120)
    print(f"口座資金       : {ACCOUNT_CAPITAL:,}円")
    print(f"入力候補       : {summary['result']['input_count']}件")
    print(f"採用候補       : {summary['result']['selected_count']}件")
    print(f"補欠候補       : {summary['result']['reserve_count']}件")
    print(f"見送り         : {summary['result']['rejected_count']}件")

    print()
    print("=" * 120)
    print("ポートフォリオ選定結果")
    print("=" * 120)

    display_columns = [
        "Portfolio順位",
        "銘柄",
        "ticker",
        "セクター",
        "Trade判定",
        "AI判断点",
        "PHOENIX_SCORE",
        "PortfolioScore",
        "資金配分比率",
        "想定配分額",
        "Portfolio判定",
    ]

    print(result[display_columns].to_string(index=False))

    print()
    print(f"保存完了: {OUTPUT_FILE}")
    print(f"保存完了: {SUMMARY_FILE}")
    print(f"保存完了: {TEXT_REPORT_FILE}")


# =========================================================
# メイン
# =========================================================

def main() -> None:
    configure_console()
    regime_data = apply_market_regime()
    print(f"Market Regime : {regime_data.get('regime', 'SIDEWAYS')}")

    try:
        data = load_watchlist()
        result = select_portfolio(data)
        summary = build_summary(result)

        save_outputs(result, summary)
        print_result(result, summary)

    except Exception as error:
        print(f"エラー: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
