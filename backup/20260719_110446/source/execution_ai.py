from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import math
import sys
from typing import Any

import pandas as pd

from execution_core import bootstrap_environment
from realtime_gateway import RealtimeGateway

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
POSITION_PLAN_FILE = REPORT_DIR / "position_plan.csv"
RISK_SUMMARY_FILE = REPORT_DIR / "risk_controller_summary.json"
OUTPUT_FILE = REPORT_DIR / "execution_candidates.csv"
SUMMARY_FILE = REPORT_DIR / "execution_ai_summary.json"
REPORT_FILE = REPORT_DIR / "execution_ai_report.txt"


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists(): return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError): return {}


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists(): return pd.DataFrame()
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try: return pd.read_csv(path, encoding=encoding)
        except Exception: continue
    return pd.DataFrame()


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    configure_console(); REPORT_DIR.mkdir(parents=True, exist_ok=True)
    config = bootstrap_environment()["config"]
    mode = str(config.get("mode", "DRY_RUN")).upper()
    risk = load_json(RISK_SUMMARY_FILE)
    plan = read_csv(POSITION_PLAN_FILE)
    if plan.empty:
        raise FileNotFoundError(f"ポジション計画がありません: {POSITION_PLAN_FILE}")

    gateway = RealtimeGateway()
    adopted = plan[plan["Position判定"].astype(str).eq("採用")].copy() if "Position判定" in plan.columns else plan.copy()
    minimum_unit = int(safe_float(config.get("minimum_rss_trade_unit", 100), 100))
    max_position = safe_float(config.get("maximum_position_value_yen", 100000), 100000)
    max_trades = int(safe_float(config.get("maximum_daily_trades", 1), 1))
    tolerance = safe_float(config.get("entry_price_tolerance_percent", 1.0), 1.0)
    risk_allowed = bool(risk.get("allowed", False))
    allow_kabumini = bool(config.get("allow_kabumini_auto_execution", False))

    rows: list[dict[str, Any]] = []
    for _, row in adopted.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        shares = int(safe_float(row.get("株数", 0)))
        planned_entry = safe_float(row.get("エントリー価格", 0))
        target = safe_float(row.get("利確価格", 0))
        stop = safe_float(row.get("損切価格", 0))
        service = str(row.get("取引サービス", ""))
        score = safe_float(row.get("OptimizerScore", row.get("PortfolioScore", row.get("AI判断点", 0))))
        rss_shares = shares if shares >= minimum_unit and shares % minimum_unit == 0 else 0
        quote = gateway.validate_quote(ticker)
        execution_price = quote.ask if quote.valid and quote.ask > 0 else 0.0
        deviation = abs(execution_price - planned_entry) / planned_entry * 100 if planned_entry > 0 and execution_price > 0 else None
        order_value = rss_shares * execution_price if execution_price > 0 else 0

        decision = "READY" if mode == "LIVE" else "DRY_RUN_READY"
        reason = "RSSリアルタイム価格・最良気配・鮮度条件クリア"
        if not risk_allowed:
            decision, reason = "BLOCK", "Risk ControllerがBLOCK"
        elif service == "かぶミニ" and not allow_kabumini:
            decision, reason = "MANUAL_ONLY", "かぶミニはRSS自動執行対象外"
        elif rss_shares == 0:
            decision, reason = "MANUAL_ONLY", f"RSS単元{minimum_unit}株を満たさない"
        elif not quote.valid:
            decision, reason = "BLOCK", f"RSS価格不正: {quote.reason}"
        elif deviation is None or deviation > tolerance:
            decision, reason = "BLOCK", f"予定価格乖離 {deviation}％ / 上限 {tolerance}％"
        elif order_value > max_position:
            decision, reason = "BLOCK", "リアルタイム価格換算で1銘柄上限超過"
        elif not (execution_price > 0 and target > execution_price and 0 < stop < execution_price):
            decision, reason = "BLOCK", "現在価格に対する利確・損切条件が不正"

        rows.append({
            "generated_at": now_text(), "銘柄": str(row.get("銘柄", "")), "ticker": ticker,
            "side": "BUY", "order_type": "LIMIT", "shares_original": shares, "shares_rss": rss_shares,
            "planned_entry_price": round(planned_entry, 2), "realtime_price": round(quote.current_price, 2),
            "best_bid": round(quote.bid, 2), "best_ask": round(quote.ask, 2),
            "quote_age_seconds": quote.age_seconds, "spread_percent": quote.spread_percent,
            "limit_price": round(execution_price, 2), "take_profit_price": round(target, 2),
            "stop_loss_price": round(stop, 2), "order_value_yen": round(order_value, 2),
            "entry_deviation_percent": round(deviation, 4) if deviation is not None else None,
            "execution_score": round(score, 3), "execution_decision": decision, "reason": reason,
        })

    output = pd.DataFrame(rows)
    if not output.empty:
        ready_mask = output["execution_decision"].isin(["READY", "DRY_RUN_READY"])
        ready_indices = output.index[ready_mask].tolist()
        for index in ready_indices[max_trades:]:
            output.at[index, "execution_decision"] = "BLOCK"
            output.at[index, "reason"] = "1日最大注文数超過"
    output.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    counts = output["execution_decision"].value_counts().to_dict() if not output.empty else {}
    summary = {"version": "PHOENIX v6.6", "generated_at": now_text(), "mode": mode,
               "targets": len(output), "ready": int(counts.get("READY", 0)),
               "dry_run_ready": int(counts.get("DRY_RUN_READY", 0)),
               "manual_only": int(counts.get("MANUAL_ONLY", 0)), "blocked": int(counts.get("BLOCK", 0))}
    save_json(SUMMARY_FILE, summary)
    REPORT_FILE.write_text("\n".join(["PHOENIX v6.6 EXECUTION AI", "="*100,
        f"生成時刻: {summary['generated_at']}", f"モード: {mode}",
        f"LIVE発注可能: {summary['ready']}件", f"DRY RUN確認: {summary['dry_run_ready']}件",
        f"手動のみ: {summary['manual_only']}件", f"停止: {summary['blocked']}件", "",
        output.to_string(index=False), ""]), encoding="utf-8")
    print("="*100); print("PHOENIX v6.6 EXECUTION AI"); print("="*100)
    print(f"LIVE発注可能 : {summary['ready']}件"); print(f"DRY RUN確認  : {summary['dry_run_ready']}件"); print(f"停止         : {summary['blocked']}件")


if __name__ == "__main__": main()
