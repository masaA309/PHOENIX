from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"

WATCHLIST_FILE = REPORT_DIR / "portfolio_watchlist.csv"
AI_PARAMETER_FILE = REPORT_DIR / "ai_parameter.json"
MARKET_REGIME_FILE = REPORT_DIR / "market_regime.json"
KABUMINI_SYMBOLS_FILE = DATA_DIR / "rakuten_kabumini_symbols.csv"

POSITION_PLAN_FILE = REPORT_DIR / "position_plan.csv"
POSITION_REPORT_FILE = REPORT_DIR / "position_sizer_report.txt"
POSITION_SUMMARY_FILE = REPORT_DIR / "position_sizer_summary.json"

DEFAULT_ACCOUNT_CAPITAL = 300_000
DEFAULT_RISK_PER_TRADE_PERCENT = 1.0
DEFAULT_MAX_TOTAL_EXPOSURE_PERCENT = 80.0
DEFAULT_MAX_SINGLE_POSITION_PERCENT = 30.0
DEFAULT_MAX_OPEN_POSITIONS = 5

BROKER_NAME = "楽天証券"
TRADING_SERVICE = "かぶミニ"
MIN_TRADE_UNIT = 1
ASSUME_ELIGIBLE_WHEN_LIST_MISSING = True
REALTIME_SPREAD_PERCENT = 0.22


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
        if value is None or pd.isna(value):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    return int(math.floor(safe_float(value, default)))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception as error:
            last_error = error
    if last_error:
        raise last_error
    return pd.DataFrame()


def load_settings() -> dict[str, Any]:
    parameters = read_json(AI_PARAMETER_FILE)
    risk = parameters.get("risk_management", {})
    if not isinstance(risk, dict):
        risk = {}

    settings = {
        "account_capital_yen": max(1, safe_int(risk.get("account_capital_yen", parameters.get("account_capital_yen", DEFAULT_ACCOUNT_CAPITAL)), DEFAULT_ACCOUNT_CAPITAL)),
        "risk_per_trade_percent": max(0.1, safe_float(risk.get("default_risk_per_trade_percent", DEFAULT_RISK_PER_TRADE_PERCENT), DEFAULT_RISK_PER_TRADE_PERCENT)),
        "maximum_total_exposure_percent": min(100.0, max(1.0, safe_float(risk.get("maximum_total_exposure_percent", DEFAULT_MAX_TOTAL_EXPOSURE_PERCENT), DEFAULT_MAX_TOTAL_EXPOSURE_PERCENT))),
        "maximum_single_position_percent": min(100.0, max(1.0, safe_float(risk.get("maximum_single_position_percent", DEFAULT_MAX_SINGLE_POSITION_PERCENT), DEFAULT_MAX_SINGLE_POSITION_PERCENT))),
        "maximum_open_positions": max(1, safe_int(risk.get("maximum_open_positions", DEFAULT_MAX_OPEN_POSITIONS), DEFAULT_MAX_OPEN_POSITIONS)),
        "source": str(AI_PARAMETER_FILE) if AI_PARAMETER_FILE.exists() else "初期設定",
    }

    regime = read_json(MARKET_REGIME_FILE)
    regime_settings = regime.get("settings", {})
    if not isinstance(regime_settings, dict):
        regime_settings = {}

    capital_usage = safe_float(regime_settings.get("capital_usage_percent", 70.0), 70.0)
    risk_multiplier = safe_float(regime_settings.get("risk_per_trade_multiplier", 1.0), 1.0)
    settings["maximum_total_exposure_percent"] = min(settings["maximum_total_exposure_percent"], capital_usage)
    settings["risk_per_trade_percent"] = max(0.1, settings["risk_per_trade_percent"] * risk_multiplier)
    settings["maximum_open_positions"] = max(1, safe_int(regime_settings.get("max_positions", settings["maximum_open_positions"]), settings["maximum_open_positions"]))
    settings["market_regime"] = str(regime.get("regime", "SIDEWAYS"))
    settings["regime_confidence"] = safe_float(regime.get("confidence", 0.0))
    settings["broker"] = BROKER_NAME
    settings["trading_service"] = TRADING_SERVICE
    settings["minimum_trade_unit"] = MIN_TRADE_UNIT
    settings["realtime_spread_percent"] = REALTIME_SPREAD_PERCENT
    return settings


def load_kabumini_symbols() -> set[str] | None:
    data = read_csv(KABUMINI_SYMBOLS_FILE)
    if data.empty:
        return None
    for column in ("ticker", "銘柄コード", "code"):
        if column in data.columns:
            values = data[column].astype(str).str.strip().str.replace(".T", "", regex=False)
            return set(values)
    return None


def normalize_code(ticker: str) -> str:
    return str(ticker).strip().replace(".T", "")


def load_watchlist() -> pd.DataFrame:
    data = read_csv(WATCHLIST_FILE)
    if data.empty:
        raise FileNotFoundError(f"監視リストがありません、または空です: {WATCHLIST_FILE}")

    required = {"銘柄", "ticker", "AI判断点", "PHOENIX_SCORE", "Trade判定", "押し目価格", "利確価格", "損切価格"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError("price_watchlist.csv に必要な列がありません: " + ", ".join(sorted(missing)))

    for column in ("AI判断点", "PHOENIX_SCORE", "押し目価格", "利確価格", "損切価格", "MarketRiskScore"):
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    data["Trade判定"] = data["Trade判定"].astype(str).str.strip().str.upper()
    if "Portfolio判定" in data.columns:
        data = data[data["Portfolio判定"].astype(str).eq("採用")].copy()
    data = data[data["Trade判定"].isin(["BUY", "WATCH"])].copy()
    data = data.dropna(subset=["押し目価格", "利確価格", "損切価格"])
    data = data[(data["押し目価格"] > 0) & (data["利確価格"] > data["押し目価格"]) & (data["損切価格"] < data["押し目価格"])].copy()
    if data.empty:
        raise ValueError("有効なポジション計算対象がありません。")
    return data.reset_index(drop=True)


def calculate_plan(watchlist: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    capital = safe_float(settings["account_capital_yen"])
    max_total = capital * safe_float(settings["maximum_total_exposure_percent"]) / 100.0
    max_single = capital * safe_float(settings["maximum_single_position_percent"]) / 100.0
    risk_budget = capital * safe_float(settings["risk_per_trade_percent"]) / 100.0
    max_positions = safe_int(settings["maximum_open_positions"])
    kabumini_symbols = load_kabumini_symbols()

    data = watchlist.copy()
    data["__priority"] = data["Trade判定"].map({"BUY": 0, "WATCH": 1}).fillna(2)
    sort_col = "OptimizerScore" if "OptimizerScore" in data.columns else ("PortfolioScore" if "PortfolioScore" in data.columns else "AI判断点")
    data = data.sort_values(["__priority", sort_col, "AI判断点"], ascending=[True, False, False]).reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    used = 0.0
    adopted = 0

    for index, row in data.iterrows():
        entry = safe_float(row.get("押し目価格"))
        target = safe_float(row.get("利確価格"))
        stop = safe_float(row.get("損切価格"))
        loss_per_share = entry - stop
        profit_per_share = target - entry
        code = normalize_code(row.get("ticker", ""))

        if kabumini_symbols is None:
            eligible = ASSUME_ELIGIBLE_WHEN_LIST_MISSING
            eligibility = "未確認（対象リスト未配置）"
        else:
            eligible = code in kabumini_symbols
            eligibility = "対象" if eligible else "対象外"

        max_by_risk = safe_int(risk_budget / loss_per_share) if loss_per_share > 0 else 0
        max_by_single = safe_int(max_single / entry) if entry > 0 else 0
        remaining = max(0.0, max_total - used)
        max_by_remaining = safe_int(remaining / entry) if entry > 0 else 0
        allocation_ratio = safe_float(row.get("資金配分比率", row.get("推奨配分比率", 0.0)), 0.0)
        allocation_cap = max_total * allocation_ratio if allocation_ratio > 0 else max_single
        max_by_allocation = safe_int(allocation_cap / entry) if entry > 0 else 0
        shares = min(max_by_risk, max_by_single, max_by_remaining, max_by_allocation if max_by_allocation > 0 else max_by_single)

        decision = "採用"
        reason = "1株単位・資金管理条件クリア"
        if not eligible:
            shares = 0
            decision = "見送り"
            reason = "楽天かぶミニ対象外"
        elif adopted >= max_positions:
            shares = 0
            decision = "見送り"
            reason = "最大保有数超過"
        elif shares < MIN_TRADE_UNIT:
            shares = 0
            decision = "見送り"
            reason = "計算株数が1株未満"

        investment = round(shares * entry, 2)
        expected_profit = round(shares * profit_per_share, 2)
        expected_loss = round(shares * loss_per_share, 2)

        if decision == "採用":
            used += investment
            adopted += 1

        rows.append({
            "優先順位": index + 1,
            "作成日時": now_text(),
            "銘柄": str(row.get("銘柄", "")),
            "ticker": str(row.get("ticker", "")),
            "AI判断": str(row.get("AI判断", "")),
            "AI判断点": safe_float(row.get("AI判断点")),
            "PHOENIX_SCORE": safe_float(row.get("PHOENIX_SCORE")),
            "Trade判定": str(row.get("Trade判定", "")),
            "MarketRiskScore": safe_float(row.get("MarketRiskScore", 0)),
            "MarketRiskLevel": str(row.get("MarketRiskLevel", "")),
            "基準価格": safe_float(row.get("基準価格", entry)),
            "エントリー価格": entry,
            "利確価格": target,
            "損切価格": stop,
            "損切幅円": round(loss_per_share, 2),
            "損切幅%": round(loss_per_share / entry * 100.0, 3) if entry else 0.0,
            "リスクリワード": round(profit_per_share / loss_per_share, 3) if loss_per_share else 0.0,
            "売買単位": MIN_TRADE_UNIT,
            "取引サービス": TRADING_SERVICE,
            "かぶミニ判定": eligibility,
            "株数": shares,
            "投資金額円": investment,
            "口座比率%": round(investment / capital * 100.0, 3) if capital else 0.0,
            "想定利益円": expected_profit,
            "想定損失円": expected_loss,
            "実損失率%": round(expected_loss / capital * 100.0, 4) if capital else 0.0,
            "Position判定": decision,
            "判定理由": reason,
        })

    return pd.DataFrame(rows)


def build_summary(plan: pd.DataFrame, settings: dict[str, Any]) -> dict[str, Any]:
    adopted = plan[plan["Position判定"] == "採用"].copy()
    capital = safe_float(settings["account_capital_yen"])
    investment = safe_float(adopted["投資金額円"].sum()) if not adopted.empty else 0.0
    profit = safe_float(adopted["想定利益円"].sum()) if not adopted.empty else 0.0
    loss = safe_float(adopted["想定損失円"].sum()) if not adopted.empty else 0.0
    return {
        "version": "PHOENIX v6.4",
        "generated_at": now_text(),
        "settings": settings,
        "result": {
            "targets": len(plan),
            "adopted_positions": len(adopted),
            "rejected_positions": len(plan) - len(adopted),
            "total_investment_yen": round(investment, 0),
            "available_cash_yen": round(capital - investment, 0),
            "total_exposure_percent": round(investment / capital * 100.0, 2) if capital else 0.0,
            "total_expected_profit_yen": round(profit, 0),
            "total_expected_loss_yen": round(loss, 0),
            "total_expected_loss_percent": round(loss / capital * 100.0, 4) if capital else 0.0,
            "minimum_trade_unit": MIN_TRADE_UNIT,
            "broker": BROKER_NAME,
            "trading_service": TRADING_SERVICE,
        },
    }


def save_outputs(plan: pd.DataFrame, summary: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    plan.to_csv(POSITION_PLAN_FILE, index=False, encoding="utf-8-sig")
    POSITION_SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    result = summary["result"]
    settings = summary["settings"]
    lines = [
        "PHOENIX v6.4 POSITION SIZER REPORT",
        now_text(),
        "=" * 120,
        f"証券会社: {BROKER_NAME}",
        f"取引サービス: {TRADING_SERVICE}",
        f"最低売買単位: {MIN_TRADE_UNIT}株",
        f"口座資金: {safe_int(settings['account_capital_yen']):,}円",
        f"最大総投資比率: {safe_float(settings['maximum_total_exposure_percent']):.2f}%",
        f"採用数: {safe_int(result['adopted_positions'])}件",
        f"総投資額: {safe_int(result['total_investment_yen']):,}円",
        "",
        plan.to_string(index=False),
        "",
    ]
    POSITION_REPORT_FILE.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def print_result(plan: pd.DataFrame, summary: dict[str, Any]) -> None:
    settings = summary["settings"]
    result = summary["result"]
    print("=" * 120)
    print("PHOENIX v6.4 POSITION SIZER - 楽天かぶミニ対応")
    print("=" * 120)
    print(f"証券会社       : {BROKER_NAME}")
    print(f"取引サービス   : {TRADING_SERVICE}")
    print(f"最低売買単位   : {MIN_TRADE_UNIT}株")
    print(f"口座資金       : {safe_int(settings['account_capital_yen']):,}円")
    print(f"1取引リスク   : {safe_float(settings['risk_per_trade_percent']):.2f}%")
    print(f"最大総投資比率 : {safe_float(settings['maximum_total_exposure_percent']):.2f}%")
    print(f"最大1銘柄比率 : {safe_float(settings['maximum_single_position_percent']):.2f}%")
    print(f"最大保有数     : {safe_int(settings['maximum_open_positions'])}件")
    print(f"対象銘柄リスト : {KABUMINI_SYMBOLS_FILE if KABUMINI_SYMBOLS_FILE.exists() else '未配置（対象と仮定）'}")
    print()
    columns = ["優先順位", "銘柄", "ticker", "Trade判定", "AI判断点", "PHOENIX_SCORE", "エントリー価格", "損切価格", "株数", "投資金額円", "想定利益円", "想定損失円", "かぶミニ判定", "Position判定", "判定理由"]
    print(plan[columns].to_string(index=False))
    print()
    print("=" * 120)
    print("集計")
    print("=" * 120)
    print(f"計算対象       : {safe_int(result['targets'])}件")
    print(f"採用           : {safe_int(result['adopted_positions'])}件")
    print(f"見送り         : {safe_int(result['rejected_positions'])}件")
    print(f"総投資額       : {safe_int(result['total_investment_yen']):,}円")
    print(f"総投資比率     : {safe_float(result['total_exposure_percent']):.2f}%")
    print(f"余力           : {safe_int(result['available_cash_yen']):,}円")
    print(f"総想定利益     : {safe_int(result['total_expected_profit_yen']):,}円")
    print(f"総想定損失     : {safe_int(result['total_expected_loss_yen']):,}円")
    print(f"総想定損失率   : {safe_float(result['total_expected_loss_percent']):.4f}%")
    print()
    print(f"保存完了: {POSITION_PLAN_FILE}")
    print(f"保存完了: {POSITION_SUMMARY_FILE}")
    print(f"保存完了: {POSITION_REPORT_FILE}")


def main() -> None:
    configure_console()
    try:
        settings = load_settings()
        watchlist = load_watchlist()
        plan = calculate_plan(watchlist, settings)
        summary = build_summary(plan, settings)
        save_outputs(plan, summary)
        print_result(plan, summary)
    except Exception as error:
        print(f"エラー: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
