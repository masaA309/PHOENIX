# performance_analyzer.py
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_FILE = ROOT_DIR / "config" / "performance_config.json"


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
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルがありません: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("設定ファイルのルートはJSONオブジェクトにしてください")
    return value


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def monthly_cost(config: dict[str, Any]) -> float:
    costs = config.get("monthly_costs", {})
    total = safe_float(costs.get("other_yen"))
    if bool(costs.get("include_chatgpt_plus", True)):
        total += safe_float(costs.get("chatgpt_plus_yen"))
    if bool(costs.get("include_excel", True)):
        total += safe_float(costs.get("excel_yen"))
    return total


def normalize_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["取引ID", "決済日時", "損益額", "損益率%", "状態", "決済日時_dt", "決済済み"])
    try:
        df = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=["取引ID", "決済日時", "損益額", "損益率%", "状態", "決済日時_dt", "決済済み"])

    aliases = {
        "trade_id": "取引ID", "exit_datetime": "決済日時", "realized_pnl": "損益額",
        "pnl": "損益額", "pnl_percent": "損益率%", "status": "状態"
    }
    df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns and v not in df.columns})
    for column, default in [("取引ID", ""), ("決済日時", ""), ("損益額", 0.0), ("損益率%", 0.0), ("状態", "")]:
        if column not in df.columns:
            df[column] = default

    df["損益額"] = pd.to_numeric(df["損益額"], errors="coerce").fillna(0.0)
    df["損益率%"] = pd.to_numeric(df["損益率%"], errors="coerce").fillna(0.0)
    df["決済日時_dt"] = pd.to_datetime(df["決済日時"], errors="coerce")
    closed_words = {"利確", "損切", "決済", "closed", "CLOSED", "WIN", "LOSS"}
    df["決済済み"] = df["決済日時_dt"].notna() | df["状態"].astype(str).isin(closed_words)
    return df


def maximum_streak(values: list[float], positive: bool) -> int:
    best = current = 0
    for value in values:
        matched = value > 0 if positive else value < 0
        current = current + 1 if matched else 0
        best = max(best, current)
    return best


def build_equity_curve(closed: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    columns = ["sequence", "決済日時", "取引ID", "損益額", "累積損益", "資産", "資産ピーク", "ドローダウン額", "ドローダウン%"]
    if closed.empty:
        return pd.DataFrame([{
            "sequence": 0, "決済日時": "", "取引ID": "INITIAL", "損益額": 0.0,
            "累積損益": 0.0, "資産": initial_capital, "資産ピーク": initial_capital,
            "ドローダウン額": 0.0, "ドローダウン%": 0.0,
        }], columns=columns)

    work = closed.sort_values(["決済日時_dt", "取引ID"], na_position="last").copy()
    work["累積損益"] = work["損益額"].cumsum()
    work["資産"] = initial_capital + work["累積損益"]
    work["資産ピーク"] = work["資産"].cummax().clip(lower=initial_capital)
    work["ドローダウン額"] = work["資産"] - work["資産ピーク"]
    work["ドローダウン%"] = (work["ドローダウン額"] / work["資産ピーク"] * 100).fillna(0.0)
    work.insert(0, "sequence", range(1, len(work) + 1))
    work["決済日時"] = work["決済日時_dt"].dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
    return work[columns]


def tax_estimate(profit: float, config: dict[str, Any]) -> float:
    tax = config.get("tax", {})
    if not bool(tax.get("apply_tax_estimate", True)):
        return 0.0
    if str(tax.get("account_type", "")).lower() == "nisa":
        return 0.0
    return max(0.0, profit) * safe_float(tax.get("estimated_rate", 0.20315))


def build_monthly(closed: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    columns = ["month", "trades", "wins", "losses", "win_rate_percent", "gross_profit", "gross_loss", "trading_pnl", "fixed_cost", "tax_estimate", "net_profit", "profitable_after_cost"]
    if closed.empty:
        return pd.DataFrame(columns=columns)
    work = closed.dropna(subset=["決済日時_dt"]).copy()
    if work.empty:
        return pd.DataFrame(columns=columns)
    work["month"] = work["決済日時_dt"].dt.to_period("M").astype(str)
    rows = []
    cost = monthly_cost(config)
    for month, group in work.groupby("month", sort=True):
        pnl = group["損益額"]
        trading_pnl = float(pnl.sum())
        estimated_tax = tax_estimate(trading_pnl, config)
        net = trading_pnl - cost - estimated_tax
        wins = int((pnl > 0).sum())
        losses = int((pnl < 0).sum())
        rows.append({
            "month": month, "trades": len(group), "wins": wins, "losses": losses,
            "win_rate_percent": round(wins / len(group) * 100, 4) if len(group) else 0.0,
            "gross_profit": round(float(pnl[pnl > 0].sum()), 2),
            "gross_loss": round(float(pnl[pnl < 0].sum()), 2),
            "trading_pnl": round(trading_pnl, 2), "fixed_cost": round(cost, 2),
            "tax_estimate": round(estimated_tax, 2), "net_profit": round(net, 2),
            "profitable_after_cost": bool(net > 0),
        })
    return pd.DataFrame(rows, columns=columns)


def analyze(config: dict[str, Any]) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    initial = safe_float(config.get("initial_capital_yen"), 300000.0)
    trade_path = resolve_path(config.get("input_files", {}).get("paper_trades", "reports/paper_trades.csv"))
    trades = normalize_trades(trade_path)
    closed = trades[trades["決済済み"]].copy()
    pnl = closed["損益額"] if not closed.empty else pd.Series(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gross_profit = float(wins.sum())
    gross_loss_abs = abs(float(losses.sum()))
    total_pnl = float(pnl.sum())
    profit_factor = gross_profit / gross_loss_abs if gross_loss_abs > 0 else (float("inf") if gross_profit > 0 else 0.0)
    equity = build_equity_curve(closed, initial)
    max_dd_yen = abs(float(equity["ドローダウン額"].min())) if not equity.empty else 0.0
    max_dd_pct = abs(float(equity["ドローダウン%"].min())) if not equity.empty else 0.0
    monthly = build_monthly(closed, config)
    current_month = datetime.now().strftime("%Y-%m")
    current = monthly[monthly["month"] == current_month]
    current_trading = safe_float(current.iloc[0]["trading_pnl"]) if not current.empty else 0.0
    cost = monthly_cost(config)
    current_tax = tax_estimate(current_trading, config)
    current_net = current_trading - cost - current_tax
    qualification = config.get("qualification", {})
    positive_months = int(monthly["profitable_after_cost"].sum()) if not monthly.empty else 0
    checks = {
        "closed_trades": len(closed) >= int(qualification.get("minimum_closed_trades", 50)),
        "profit_factor": profit_factor >= safe_float(qualification.get("minimum_profit_factor"), 1.5),
        "win_rate": ((len(wins) / len(closed) * 100) if len(closed) else 0.0) >= safe_float(qualification.get("minimum_win_rate_percent"), 55.0),
        "maximum_drawdown": max_dd_pct <= safe_float(qualification.get("maximum_drawdown_percent"), 10.0),
        "positive_months_after_cost": positive_months >= int(qualification.get("required_positive_months", 3)),
    }
    values = pnl.tolist()
    summary = {
        "version": "6.7", "generated_at": now_text(), "input_file": str(trade_path),
        "initial_capital_yen": round(initial, 2), "closed_trades": int(len(closed)),
        "open_trades": int((~trades["決済済み"]).sum()) if not trades.empty else 0,
        "wins": int(len(wins)), "losses": int(len(losses)), "break_even": int((pnl == 0).sum()),
        "win_rate_percent": round((len(wins) / len(closed) * 100) if len(closed) else 0.0, 4),
        "gross_profit_yen": round(gross_profit, 2), "gross_loss_yen": round(-gross_loss_abs, 2),
        "total_trading_pnl_yen": round(total_pnl, 2),
        "profit_factor": None if math.isinf(profit_factor) else round(profit_factor, 4),
        "profit_factor_display": "INF" if math.isinf(profit_factor) else f"{profit_factor:.4f}",
        "average_profit_yen": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "average_loss_yen": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "expectancy_yen_per_trade": round(float(pnl.mean()), 2) if len(pnl) else 0.0,
        "max_consecutive_wins": maximum_streak(values, True), "max_consecutive_losses": maximum_streak(values, False),
        "maximum_drawdown_yen": round(max_dd_yen, 2), "maximum_drawdown_percent": round(max_dd_pct, 4),
        "ending_equity_before_fixed_cost_yen": round(initial + total_pnl, 2),
        "monthly_fixed_cost_yen": round(cost, 2), "current_month": current_month,
        "current_month_trading_pnl_yen": round(current_trading, 2),
        "current_month_tax_estimate_yen": round(current_tax, 2),
        "current_month_net_profit_yen": round(current_net, 2),
        "current_month_cost_recovered": bool(current_net > 0),
        "positive_months_after_cost": positive_months,
        "qualification_checks": checks, "qualified_for_capital_increase": all(checks.values()),
        "warning": "Paper Tradeの結果であり、将来の利益を保証しません。税額は概算です。",
    }
    return summary, monthly, equity


def save_outputs(config: dict[str, Any], summary: dict[str, Any], monthly: pd.DataFrame, equity: pd.DataFrame) -> None:
    outputs = config.get("output_files", {})
    paths = {key: resolve_path(outputs.get(key, default)) for key, default in {
        "summary_json": "reports/performance_summary.json", "summary_csv": "reports/performance_summary.csv",
        "monthly_csv": "reports/performance_monthly.csv", "equity_curve_csv": "reports/equity_curve.csv",
        "text_report": "reports/performance_report.txt"}.items()}
    for path in paths.values(): path.parent.mkdir(parents=True, exist_ok=True)
    paths["summary_json"].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([summary]).to_csv(paths["summary_csv"], index=False, encoding="utf-8-sig")
    monthly.to_csv(paths["monthly_csv"], index=False, encoding="utf-8-sig")
    equity.to_csv(paths["equity_curve_csv"], index=False, encoding="utf-8-sig")
    report = ["=" * 100, "PHOENIX v6.7 PERFORMANCE ANALYZER", "=" * 100,
              f"作成日時             : {summary['generated_at']}", f"初期資金             : {summary['initial_capital_yen']:,.0f}円",
              f"決済済み取引         : {summary['closed_trades']}件", f"勝率                 : {summary['win_rate_percent']:.2f}%",
              f"PF                   : {summary['profit_factor_display']}", f"売買損益             : {summary['total_trading_pnl_yen']:+,.0f}円",
              f"最大ドローダウン     : {summary['maximum_drawdown_yen']:,.0f}円 ({summary['maximum_drawdown_percent']:.2f}%)",
              "-" * 100, f"今月売買損益         : {summary['current_month_trading_pnl_yen']:+,.0f}円",
              f"今月固定費           : -{summary['monthly_fixed_cost_yen']:,.0f}円  (ChatGPT Plus + Excel)",
              f"今月税額概算         : -{summary['current_month_tax_estimate_yen']:,.0f}円",
              f"今月コスト・税引後   : {summary['current_month_net_profit_yen']:+,.0f}円",
              f"固定費回収           : {'YES' if summary['current_month_cost_recovered'] else 'NO'}",
              "-" * 100, f"増資合格判定         : {'PASS' if summary['qualified_for_capital_increase'] else 'NOT YET'}"]
    for key, ok in summary["qualification_checks"].items(): report.append(f"  {'OK' if ok else 'NG'} {key}")
    report += ["-" * 100, summary["warning"], "=" * 100]
    paths["text_report"].write_text("\n".join(report) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PHOENIX v6.7 Paper Trade成績・固定費・税概算分析")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_FILE))
    return parser.parse_args()


def main() -> int:
    configure_console()
    args = parse_args()
    try:
        config = load_json(Path(args.config))
        summary, monthly, equity = analyze(config)
        save_outputs(config, summary, monthly, equity)
        print((resolve_path(config.get("output_files", {}).get("text_report", "reports/performance_report.txt"))).read_text(encoding="utf-8"))
        return 0
    except Exception as error:
        print(f"Performance Analyzer エラー: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
