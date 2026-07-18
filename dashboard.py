# dashboard.py
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"

PHOENIX_SUMMARY_FILE = REPORT_DIR / "phoenix_latest_summary.json"
PORTFOLIO_FILE = REPORT_DIR / "portfolio_watchlist.csv"
PRICE_WATCHLIST_FILE = REPORT_DIR / "price_watchlist.csv"
POSITION_PLAN_FILE = REPORT_DIR / "position_plan.csv"
POSITION_SUMMARY_FILE = REPORT_DIR / "position_sizer_summary.json"
PAPER_SUMMARY_FILE = REPORT_DIR / "paper_trade_summary.csv"
PAPER_TRADES_FILE = REPORT_DIR / "paper_trades.csv"
LEARNING_REPORT_FILE = REPORT_DIR / "learning_report.csv"
AI_PARAMETER_FILE = REPORT_DIR / "ai_parameter.json"
BACKTEST_SUMMARY_FILE = REPORT_DIR / "backtest_summary.json"

MARKET_RISK_FILES = (
    DATA_DIR / "market_risk_latest.json",
    REPORT_DIR / "market_risk_latest.json",
    REPORT_DIR / "market_risk.json",
)

OUTPUT_JSON = REPORT_DIR / "dashboard_summary.json"
OUTPUT_TEXT = REPORT_DIR / "dashboard_report.txt"
OUTPUT_HTML = REPORT_DIR / "dashboard.html"

ACCOUNT_CAPITAL_DEFAULT = 300_000
DISPLAY_TOP_COUNT = 10


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
    return int(round(safe_float(value, default)))


def money(value: Any) -> str:
    number = safe_float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,.0f}円"


def percent(value: Any, digits: int = 2) -> str:
    number = safe_float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.{digits}f}%"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def read_csv_safe(path: Path) -> pd.DataFrame:
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


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def find_key(data: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    for value in data.values():
        if isinstance(value, dict):
            found = find_key(value, keys, None)
            if found is not None:
                return found
    return default


def first_csv_value(data: pd.DataFrame, columns: tuple[str, ...], default: Any = None) -> Any:
    if data.empty:
        return default
    for column in columns:
        if column in data.columns:
            series = data[column].dropna()
            if not series.empty:
                return series.iloc[-1]
    return default


def load_market_risk() -> dict[str, Any]:
    source = ""
    data: dict[str, Any] = {}
    for path in MARKET_RISK_FILES:
        if path.exists():
            source = str(path)
            data = load_json(path)
            break

    score = safe_float(
        find_key(data, ("market_risk_score", "risk_score", "score", "MarketRiskScore"), 50),
        50,
    )
    level = str(
        find_key(data, ("market_risk_level", "risk_level", "level", "status", "MarketRiskLevel"), "WATCH")
    ).strip().upper()

    valid = {"SAFE", "LOW", "NORMAL", "WATCH", "HIGH", "RISK", "DANGER", "STOP", "CRITICAL"}
    if level not in valid:
        level = "STOP" if score >= 80 else "HIGH" if score >= 60 else "WATCH" if score >= 40 else "SAFE"

    return {"score": round(score, 2), "level": level, "source": source}


def load_portfolio() -> dict[str, Any]:
    data = read_csv_safe(PORTFOLIO_FILE)
    if data.empty:
        data = read_csv_safe(PRICE_WATCHLIST_FILE)
    if data.empty:
        return {"input_count": 0, "selected_count": 0, "reserve_count": 0, "selected": [], "sector_counts": {}}

    if "Portfolio判定" in data.columns:
        status = data["Portfolio判定"].astype(str).str.strip()
        selected = data[status == "採用"].copy()
        reserve_count = int((status == "補欠").sum())
    else:
        selected = data.head(3).copy()
        reserve_count = max(len(data) - len(selected), 0)

    if "Portfolio順位" in selected.columns:
        selected = selected.sort_values("Portfolio順位")
    elif "PortfolioScore" in selected.columns:
        selected = selected.sort_values("PortfolioScore", ascending=False)

    rows: list[dict[str, Any]] = []
    for number, (_, row) in enumerate(selected.head(DISPLAY_TOP_COUNT).iterrows(), 1):
        rows.append({
            "rank": safe_int(row.get("Portfolio順位", number), number),
            "name": str(row.get("銘柄", "")),
            "ticker": str(row.get("ticker", "")),
            "sector": str(row.get("セクター", "未分類")),
            "trade_decision": str(row.get("Trade判定", "")),
            "ai_score": safe_float(row.get("AI判断点", 0)),
            "phoenix_score": safe_float(row.get("PHOENIX_SCORE", 0)),
            "portfolio_score": safe_float(row.get("PortfolioScore", 0)),
            "allocation_ratio": safe_float(row.get("資金配分比率", 0)),
            "allocation_yen": safe_float(row.get("想定配分額", 0)),
        })

    sectors = (
        selected["セクター"].fillna("未分類").astype(str).value_counts().to_dict()
        if "セクター" in selected.columns else {}
    )

    return {
        "input_count": len(data),
        "selected_count": len(selected),
        "reserve_count": reserve_count,
        "selected": rows,
        "sector_counts": sectors,
    }


def load_positions() -> dict[str, Any]:
    summary = load_json(POSITION_SUMMARY_FILE)
    plan = read_csv_safe(POSITION_PLAN_FILE)

    capital = safe_float(
        find_key(summary, ("account_capital_yen", "account_capital", "initial_capital", "口座資金"), ACCOUNT_CAPITAL_DEFAULT),
        ACCOUNT_CAPITAL_DEFAULT,
    )

    adopted = pd.DataFrame()
    if not plan.empty:
        if "Position判定" in plan.columns:
            adopted = plan[plan["Position判定"].astype(str).str.strip() == "採用"].copy()
        else:
            adopted = plan.copy()

    invested = safe_float(find_key(summary, ("total_investment_yen", "total_investment", "総投資額"), 0))
    expected_profit = safe_float(find_key(summary, ("total_expected_profit_yen", "expected_profit_yen", "総想定利益"), 0))
    expected_loss = safe_float(find_key(summary, ("total_expected_loss_yen", "expected_loss_yen", "総想定損失"), 0))

    if not adopted.empty:
        if invested == 0 and "投資金額円" in adopted.columns:
            invested = safe_float(adopted["投資金額円"].sum())
        if expected_profit == 0 and "想定利益円" in adopted.columns:
            expected_profit = safe_float(adopted["想定利益円"].sum())
        if expected_loss == 0 and "想定損失円" in adopted.columns:
            expected_loss = safe_float(adopted["想定損失円"].sum())

    rr = expected_profit / abs(expected_loss) if expected_loss else 0.0

    return {
        "account_capital_yen": capital,
        "invested_yen": invested,
        "available_cash_yen": max(capital - invested, 0),
        "expected_profit_yen": expected_profit,
        "expected_loss_yen": expected_loss,
        "risk_reward": round(rr, 3),
        "adopted_count": len(adopted),
    }


def load_paper_trader() -> dict[str, Any]:
    summary = read_csv_safe(PAPER_SUMMARY_FILE)
    trades = read_csv_safe(PAPER_TRADES_FILE)

    current_assets = safe_float(
        first_csv_value(summary, ("現在資産", "current_assets", "current_equity"), ACCOUNT_CAPITAL_DEFAULT),
        ACCOUNT_CAPITAL_DEFAULT,
    )
    total_profit = safe_float(first_csv_value(summary, ("総損益", "total_profit", "total_pnl"), current_assets - ACCOUNT_CAPITAL_DEFAULT))
    win_rate = safe_float(first_csv_value(summary, ("勝率", "win_rate"), 0))
    pf = safe_float(first_csv_value(summary, ("PF", "profit_factor"), 0))
    max_dd = safe_float(first_csv_value(summary, ("最大DD", "max_drawdown"), 0))

    open_count = 0
    closed_count = 0
    if not trades.empty:
        status_col = next((c for c in ("状態", "status", "取引状態") if c in trades.columns), None)
        if status_col:
            values = trades[status_col].astype(str)
            open_count = int(values.str.contains("保有|OPEN|open", regex=True, na=False).sum())
            closed_count = int(values.str.contains("決済|CLOSED|closed", regex=True, na=False).sum())
        else:
            closed_count = len(trades)

    return {
        "current_assets_yen": current_assets,
        "total_profit_yen": total_profit,
        "win_rate": win_rate,
        "profit_factor": pf,
        "max_drawdown": max_dd,
        "open_count": open_count,
        "closed_count": closed_count,
    }


def load_learning() -> dict[str, Any]:
    parameters = load_json(AI_PARAMETER_FILE)
    report = read_csv_safe(LEARNING_REPORT_FILE)

    closed = safe_int(find_key(parameters, ("closed_trades", "trade_count", "sample_count", "決済済み取引数"), first_csv_value(report, ("取引数", "件数", "sample_count"), 0)))
    win_rate = safe_float(find_key(parameters, ("win_rate", "adjusted_win_rate", "勝率"), first_csv_value(report, ("勝率", "win_rate"), 0)))
    average_return = safe_float(find_key(parameters, ("average_return", "avg_return", "平均損益率"), first_csv_value(report, ("平均損益率", "平均リターン", "avg_return"), 0)))
    pf = safe_float(find_key(parameters, ("profit_factor", "PF"), first_csv_value(report, ("PF", "profit_factor"), 0)))
    confidence = safe_float(find_key(parameters, ("confidence", "learning_confidence", "信頼度"), 0))
    adjustment = safe_float(find_key(parameters, ("ai_score_adjustment", "score_adjustment", "AI点補正"), 0))

    return {
        "state": "学習中" if closed >= 10 else "初期学習",
        "closed_trades": closed,
        "win_rate": win_rate,
        "average_return": average_return,
        "profit_factor": pf,
        "confidence": confidence,
        "ai_score_adjustment": adjustment,
    }


def load_system() -> dict[str, Any]:
    data = load_json(PHOENIX_SUMMARY_FILE)
    stages: list[dict[str, Any]] = []
    results = data.get("results", [])
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                stages.append({
                    "title": str(item.get("title", item.get("key", ""))),
                    "status": str(item.get("status", "UNKNOWN")),
                    "seconds": safe_float(item.get("seconds", 0)),
                    "message": str(item.get("message", "")),
                })

    return {
        "status": str(data.get("status", "UNKNOWN")),
        "success_count": safe_int(data.get("success_count", 0)),
        "failed_count": safe_int(data.get("failed_count", 0)),
        "total_seconds": safe_float(data.get("total_seconds", 0)),
        "run_id": str(data.get("run_id", "")),
        "started_at": str(data.get("started_at", "")),
        "finished_at": str(data.get("finished_at", "")),
        "stages": stages,
    }



def load_backtest() -> dict[str, Any]:
    data = load_json(BACKTEST_SUMMARY_FILE)
    performance = data.get("performance", {})
    period = data.get("period", {})

    if not isinstance(performance, dict):
        performance = {}

    if not isinstance(period, dict):
        period = {}

    return {
        "available": bool(data),
        "start_date": str(period.get("start_date", "")),
        "end_date": str(period.get("end_date", "")),
        "trading_days": safe_int(period.get("trading_days", 0)),
        "final_equity_yen": safe_float(
            performance.get("final_equity_yen", ACCOUNT_CAPITAL_DEFAULT),
            ACCOUNT_CAPITAL_DEFAULT,
        ),
        "total_profit_yen": safe_float(
            performance.get("total_profit_yen", 0)
        ),
        "total_return_pct": safe_float(
            performance.get("total_return_pct", 0)
        ),
        "annual_return_pct": safe_float(
            performance.get("annual_return_pct", 0)
        ),
        "max_drawdown_pct": safe_float(
            performance.get("max_drawdown_pct", 0)
        ),
        "sharpe_ratio": safe_float(
            performance.get("sharpe_ratio", 0)
        ),
        "trade_count": safe_int(
            performance.get("trade_count", 0)
        ),
        "win_rate_pct": safe_float(
            performance.get("win_rate_pct", 0)
        ),
        "profit_factor": safe_float(
            performance.get("profit_factor", 0)
        ),
        "average_return_pct": safe_float(
            performance.get("average_return_pct", 0)
        ),
        "average_holding_days": safe_float(
            performance.get("average_holding_days", 0)
        ),
    }


def build_dashboard() -> dict[str, Any]:
    market = load_market_risk()
    portfolio = load_portfolio()
    positions = load_positions()
    paper = load_paper_trader()
    learning = load_learning()
    backtest = load_backtest()
    system = load_system()

    if system["failed_count"] > 0:
        overall = "ERROR"
    elif market["level"] in {"STOP", "CRITICAL", "DANGER"}:
        overall = "MARKET STOP"
    elif portfolio["selected_count"] == 0:
        overall = "NO POSITION"
    else:
        overall = "READY"

    return {
        "version": "PHOENIX v5.1.1",
        "generated_at": now_text(),
        "overall_status": overall,
        "market_risk": market,
        "portfolio": portfolio,
        "positions": positions,
        "paper_trader": paper,
        "learning": learning,
        "backtest": backtest,
        "system": system,
    }


def print_dashboard(data: dict[str, Any]) -> None:
    risk = data["market_risk"]
    portfolio = data["portfolio"]
    positions = data["positions"]
    paper = data["paper_trader"]
    learning = data["learning"]
    backtest = data["backtest"]
    system = data["system"]

    print("=" * 120)
    print("PHOENIX v5.1.1 DASHBOARD")
    print("=" * 120)
    print(f"生成時刻       : {data['generated_at']}")
    print(f"システム状態   : {data['overall_status']}")
    print(f"Market Risk    : {risk['level']} ({risk['score']:.0f})")
    print(f"実行状態       : {system['status']}")
    print(f"成功 / 失敗    : {system['success_count']} / {system['failed_count']}")
    print(f"実行時間       : {system['total_seconds']:.2f}秒")

    print("\n" + "=" * 120)
    print("資産・ポジション")
    print("=" * 120)
    print(f"口座資金       : {money(positions['account_capital_yen'])}")
    print(f"投資予定額     : {money(positions['invested_yen'])}")
    print(f"余力           : {money(positions['available_cash_yen'])}")
    print(f"想定利益       : {money(positions['expected_profit_yen'])}")
    print(f"想定損失       : {money(positions['expected_loss_yen'])}")
    print(f"Risk Reward    : {positions['risk_reward']:.3f}")
    print(f"採用ポジション : {positions['adopted_count']}件")

    print("\n" + "=" * 120)
    print("今日の採用銘柄")
    print("=" * 120)
    if not portfolio["selected"]:
        print("採用銘柄はありません。")
    else:
        print(f"{'順位':>4} {'銘柄':<24} {'ticker':<10} {'セクター':<18} {'判定':<8} {'AI':>6} {'PHX':>6} {'Portfolio':>10} {'配分額':>14}")
        print("-" * 120)
        for row in portfolio["selected"]:
            print(
                f"{row['rank']:>4} {row['name']:<24.24} {row['ticker']:<10.10} "
                f"{row['sector']:<18.18} {row['trade_decision']:<8.8} "
                f"{row['ai_score']:>6.1f} {row['phoenix_score']:>6.1f} "
                f"{row['portfolio_score']:>10.2f} {row['allocation_yen']:>13,.0f}円"
            )

    print("\n" + "=" * 120)
    print("Paper Trader / Learning")
    print("=" * 120)
    print(f"現在資産       : {money(paper['current_assets_yen'])}")
    print(f"総損益         : {money(paper['total_profit_yen'])}")
    print(f"保有 / 決済    : {paper['open_count']} / {paper['closed_count']}")
    print(f"Paper勝率      : {percent(paper['win_rate'])}")
    print(f"Paper PF       : {paper['profit_factor']:.3f}")
    print(f"最大DD         : {percent(paper['max_drawdown'], 4)}")
    print(f"学習状態       : {learning['state']}")
    print(f"学習対象       : {learning['closed_trades']}件")
    print(f"学習勝率       : {percent(learning['win_rate'])}")
    print(f"平均損益率     : {percent(learning['average_return'], 4)}")
    print(f"学習PF         : {learning['profit_factor']:.3f}")
    print(f"信頼度         : {learning['confidence']:.3f}")
    print(f"AI点補正       : {learning['ai_score_adjustment']:+.2f}")

    print()
    print("=" * 120)
    print("Backtest")
    print("=" * 120)

    if backtest["available"]:
        print(f"検証期間       : {backtest['start_date']} ～ {backtest['end_date']}")
        print(f"取引回数       : {backtest['trade_count']}回")
        print(f"勝率           : {backtest['win_rate_pct']:.2f}%")
        print(f"Profit Factor  : {backtest['profit_factor']:.3f}")
        print(f"総リターン     : {backtest['total_return_pct']:+.2f}%")
        print(f"年率リターン   : {backtest['annual_return_pct']:+.2f}%")
        print(f"最大DD         : {backtest['max_drawdown_pct']:.2f}%")
        print(f"シャープレシオ : {backtest['sharpe_ratio']:.3f}")
        print(f"平均保有日数   : {backtest['average_holding_days']:.2f}日")
    else:
        print("バックテスト結果はまだありません。")

    print("\n" + "=" * 120)
    print("ステージ実行時間")
    print("=" * 120)
    if not system["stages"]:
        print("phoenix_latest_summary.json がありません。")
    else:
        for stage in system["stages"]:
            print(f"{stage['title']:<28} {stage['status']:<12} {stage['seconds']:>10.2f} sec {stage['message']}")

    print(f"\nJSON保存 : {OUTPUT_JSON}")
    print(f"TXT保存  : {OUTPUT_TEXT}")
    print(f"HTML保存 : {OUTPUT_HTML}")
    print("=" * 120)


def save_text(data: dict[str, Any]) -> None:
    risk = data["market_risk"]
    portfolio = data["portfolio"]
    positions = data["positions"]
    paper = data["paper_trader"]
    learning = data["learning"]
    backtest = data["backtest"]
    system = data["system"]

    lines = [
        "PHOENIX v5.1.1 DASHBOARD",
        "=" * 120,
        f"生成時刻       : {data['generated_at']}",
        f"システム状態   : {data['overall_status']}",
        f"Market Risk    : {risk['level']} ({risk['score']:.0f})",
        f"実行状態       : {system['status']}",
        f"実行時間       : {system['total_seconds']:.2f}秒",
        "",
        "資産・ポジション",
        "=" * 120,
        f"口座資金       : {money(positions['account_capital_yen'])}",
        f"投資予定額     : {money(positions['invested_yen'])}",
        f"余力           : {money(positions['available_cash_yen'])}",
        f"想定利益       : {money(positions['expected_profit_yen'])}",
        f"想定損失       : {money(positions['expected_loss_yen'])}",
        f"Risk Reward    : {positions['risk_reward']:.3f}",
        "",
        "今日の採用銘柄",
        "=" * 120,
    ]

    if portfolio["selected"]:
        for row in portfolio["selected"]:
            lines.append(
                f"{row['rank']}. {row['name']} ({row['ticker']}) / {row['sector']} / "
                f"{row['trade_decision']} / AI {row['ai_score']:.1f} / "
                f"PHOENIX {row['phoenix_score']:.1f} / Portfolio {row['portfolio_score']:.2f} / "
                f"配分 {row['allocation_yen']:,.0f}円"
            )
    else:
        lines.append("採用銘柄はありません。")

    lines.extend([
        "",
        "Paper Trader / Learning",
        "=" * 120,
        f"現在資産       : {money(paper['current_assets_yen'])}",
        f"総損益         : {money(paper['total_profit_yen'])}",
        f"Paper勝率      : {percent(paper['win_rate'])}",
        f"Paper PF       : {paper['profit_factor']:.3f}",
        f"学習状態       : {learning['state']}",
        f"学習対象       : {learning['closed_trades']}件",
        f"学習勝率       : {percent(learning['win_rate'])}",
        f"平均損益率     : {percent(learning['average_return'], 4)}",
        f"学習PF         : {learning['profit_factor']:.3f}",
        f"AI点補正       : {learning['ai_score_adjustment']:+.2f}",
        "",
        "Backtest",
        "=" * 120,
        f"検証期間       : {backtest['start_date']} ～ {backtest['end_date']}",
        f"取引回数       : {backtest['trade_count']}回",
        f"勝率           : {backtest['win_rate_pct']:.2f}%",
        f"Profit Factor  : {backtest['profit_factor']:.3f}",
        f"総リターン     : {backtest['total_return_pct']:+.2f}%",
        f"年率リターン   : {backtest['annual_return_pct']:+.2f}%",
        f"最大DD         : {backtest['max_drawdown_pct']:.2f}%",
        f"シャープレシオ : {backtest['sharpe_ratio']:.3f}",
        "",
        "ステージ実行時間",
        "=" * 120,
    ])

    for stage in system["stages"]:
        lines.append(f"{stage['title']:<28} {stage['status']:<12} {stage['seconds']:>10.2f} sec {stage['message']}")

    OUTPUT_TEXT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def status_class(status: str) -> str:
    value = status.upper()
    if value in {"READY", "SUCCESS", "OK", "SAFE", "LOW", "NORMAL"}:
        return "good"
    if value in {"WATCH", "NO POSITION", "UNKNOWN"}:
        return "warn"
    return "danger"


def save_html(data: dict[str, Any]) -> None:
    risk = data["market_risk"]
    portfolio = data["portfolio"]
    positions = data["positions"]
    paper = data["paper_trader"]
    learning = data["learning"]
    backtest = data["backtest"]
    system = data["system"]

    portfolio_rows = "".join(
        f"<tr><td>{r['rank']}</td><td>{escape(r['name'])}</td><td>{escape(r['ticker'])}</td>"
        f"<td>{escape(r['sector'])}</td><td>{escape(r['trade_decision'])}</td>"
        f"<td>{r['ai_score']:.1f}</td><td>{r['phoenix_score']:.1f}</td>"
        f"<td>{r['portfolio_score']:.2f}</td><td>{r['allocation_yen']:,.0f}円</td></tr>"
        for r in portfolio["selected"]
    ) or '<tr><td colspan="9">採用銘柄はありません。</td></tr>'

    sector_cards = "".join(
        f'<div class="mini"><span>{escape(str(sector))}</span><strong>{int(count)}</strong></div>'
        for sector, count in portfolio["sector_counts"].items()
    ) or '<div class="mini"><span>セクター</span><strong>0</strong></div>'

    stage_rows = "".join(
        f"<tr><td>{escape(s['title'])}</td><td><span class='badge {status_class(s['status'])}'>{escape(s['status'])}</span></td>"
        f"<td>{s['seconds']:.2f} sec</td><td>{escape(s['message'])}</td></tr>"
        for s in system["stages"]
    ) or '<tr><td colspan="4">実行結果はまだありません。</td></tr>'

    html = f'''<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PHOENIX Dashboard</title>
<style>
:root{{--bg:#0b1020;--panel:#121a2e;--panel2:#18233d;--text:#f5f7ff;--muted:#a9b2c9;--line:#2a395f;--good:#43d17a;--warn:#f0bd4f;--danger:#ff6577}}
*{{box-sizing:border-box}}body{{margin:0;font-family:"Segoe UI","Yu Gothic UI",sans-serif;background:radial-gradient(circle at top right,#17284d 0,transparent 32%),var(--bg);color:var(--text)}}
.wrap{{max-width:1500px;margin:auto;padding:28px}}header{{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:22px}}h1{{margin:0;font-size:34px}}.muted{{color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}}.card{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:18px}}.title{{color:var(--muted);font-size:13px}}.value{{font-size:28px;font-weight:750;margin-top:8px}}.note{{color:var(--muted);font-size:12px;margin-top:8px}}
section{{margin-top:20px}}h2{{font-size:18px}}.table{{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:16px}}table{{width:100%;border-collapse:collapse;min-width:900px}}th,td{{padding:13px 14px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}}th{{color:var(--muted);font-size:12px}}tr:last-child td{{border-bottom:0}}
.badge{{display:inline-block;padding:5px 10px;border-radius:999px;font-weight:700;font-size:12px}}.good{{color:var(--good);background:#43d17a20}}.warn{{color:var(--warn);background:#f0bd4f20}}.danger{{color:var(--danger);background:#ff657720}}
.mini-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}.mini{{background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:14px;display:flex;justify-content:space-between}}.mini span{{color:var(--muted)}}.mini strong{{font-size:22px}}
footer{{text-align:right;color:var(--muted);font-size:12px;margin-top:22px}}@media(max-width:1000px){{.grid{{grid-template-columns:repeat(2,1fr)}}}}@media(max-width:640px){{.grid{{grid-template-columns:1fr}}header{{flex-direction:column;align-items:start}}.wrap{{padding:16px}}}}
</style></head><body><div class="wrap">
<header><div><h1>PHOENIX v5.1.1</h1><div class="muted">AI Trading Operations Dashboard</div></div><div><span class="badge {status_class(data['overall_status'])}">{escape(data['overall_status'])}</span><div class="muted">{escape(data['generated_at'])}</div></div></header>
<div class="grid">
<div class="card"><div class="title">MARKET RISK</div><div class="value">{escape(risk['level'])}</div><div class="note">Risk Score {risk['score']:.0f}</div></div>
<div class="card"><div class="title">口座資金</div><div class="value">{positions['account_capital_yen']:,.0f}円</div><div class="note">投資予定 {positions['invested_yen']:,.0f}円</div></div>
<div class="card"><div class="title">余力</div><div class="value">{positions['available_cash_yen']:,.0f}円</div><div class="note">採用 {positions['adopted_count']}ポジション</div></div>
<div class="card"><div class="title">RISK REWARD</div><div class="value">{positions['risk_reward']:.2f}</div><div class="note">利益 {positions['expected_profit_yen']:,.0f}円 / 損失 {positions['expected_loss_yen']:,.0f}円</div></div>
<div class="card"><div class="title">現在資産</div><div class="value">{paper['current_assets_yen']:,.0f}円</div><div class="note">総損益 {paper['total_profit_yen']:+,.0f}円</div></div>
<div class="card"><div class="title">PAPER WIN RATE</div><div class="value">{paper['win_rate']:.2f}%</div><div class="note">PF {paper['profit_factor']:.3f}</div></div>
<div class="card"><div class="title">LEARNING</div><div class="value">{learning['closed_trades']}件</div><div class="note">勝率 {learning['win_rate']:.2f}% / PF {learning['profit_factor']:.3f}</div></div>
<div class="card"><div class="title">BACKTEST RETURN</div><div class="value">{backtest['total_return_pct']:+.2f}%</div><div class="note">年率 {backtest['annual_return_pct']:+.2f}% / DD {backtest['max_drawdown_pct']:.2f}%</div></div>
<div class="card"><div class="title">BACKTEST QUALITY</div><div class="value">{backtest['win_rate_pct']:.2f}%</div><div class="note">PF {backtest['profit_factor']:.3f} / Sharpe {backtest['sharpe_ratio']:.3f}</div></div>
<div class="card"><div class="title">SYSTEM</div><div class="value">{escape(system['status'])}</div><div class="note">成功 {system['success_count']} / 失敗 {system['failed_count']} / {system['total_seconds']:.2f} sec</div></div>
</div>
<section><h2>今日の採用銘柄</h2><div class="table"><table><thead><tr><th>順位</th><th>銘柄</th><th>Ticker</th><th>セクター</th><th>判定</th><th>AI</th><th>PHOENIX</th><th>Portfolio</th><th>配分額</th></tr></thead><tbody>{portfolio_rows}</tbody></table></div></section>
<section><h2>セクター構成</h2><div class="mini-grid">{sector_cards}</div></section>
<section><h2>Backtest</h2><div class="mini-grid">
<div class="mini"><span>取引回数</span><strong>{backtest['trade_count']}</strong></div>
<div class="mini"><span>勝率</span><strong>{backtest['win_rate_pct']:.2f}%</strong></div>
<div class="mini"><span>Profit Factor</span><strong>{backtest['profit_factor']:.3f}</strong></div>
<div class="mini"><span>総リターン</span><strong>{backtest['total_return_pct']:+.2f}%</strong></div>
<div class="mini"><span>年率</span><strong>{backtest['annual_return_pct']:+.2f}%</strong></div>
<div class="mini"><span>最大DD</span><strong>{backtest['max_drawdown_pct']:.2f}%</strong></div>
<div class="mini"><span>Sharpe</span><strong>{backtest['sharpe_ratio']:.3f}</strong></div>
<div class="mini"><span>平均保有</span><strong>{backtest['average_holding_days']:.1f}日</strong></div>
</div></section>
<section><h2>ステージ実行結果</h2><div class="table"><table><thead><tr><th>ステージ</th><th>状態</th><th>実行時間</th><th>メッセージ</th></tr></thead><tbody>{stage_rows}</tbody></table></div></section>
<footer>Generated at {escape(data['generated_at'])}</footer></div></body></html>'''

    OUTPUT_HTML.write_text(html, encoding="utf-8", newline="\n")


def main() -> None:
    configure_console()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        dashboard = build_dashboard()
        save_json(OUTPUT_JSON, dashboard)
        save_text(dashboard)
        save_html(dashboard)
        print_dashboard(dashboard)
    except Exception as error:
        print(f"Dashboardエラー: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
