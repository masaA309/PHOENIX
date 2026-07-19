from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from execution_core import (
    ROOT_DIR, REPORT_DIR, bootstrap_environment, configure_console,
    load_json, now_text, read_csv, safe_float, save_json, validate_execution_config,
)

POSITION_PLAN_FILE = REPORT_DIR / "position_plan.csv"
PAPER_TRADES_FILE = REPORT_DIR / "paper_trades.csv"
RISK_SUMMARY_FILE = REPORT_DIR / "risk_controller_summary.json"
RISK_REPORT_FILE = REPORT_DIR / "risk_controller_report.txt"
DATA_HEALTH_FILE = REPORT_DIR / "data_health_summary.json"


def heartbeat_age_seconds(path: Path) -> float | None:
    data = load_json(path)
    text = str(data.get("timestamp", "")).strip()
    if not text:
        return None
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds())
    except ValueError:
        return None


def today_realized_pnl() -> float:
    trades = read_csv(PAPER_TRADES_FILE)
    if trades.empty:
        return 0.0
    date_column = next((c for c in ("決済日時", "exit_time", "date", "日付") if c in trades.columns), None)
    pnl_column = next((c for c in ("損益円", "realized_pnl_yen", "利益円", "pnl") if c in trades.columns), None)
    if not date_column or not pnl_column:
        return 0.0
    dates = pd.to_datetime(trades[date_column], errors="coerce")
    pnl = pd.to_numeric(trades[pnl_column], errors="coerce").fillna(0.0)
    return safe_float(pnl[dates.dt.date == datetime.now().date()].sum())


def main() -> None:
    configure_console()
    boot = bootstrap_environment()
    config = boot["config"]
    position_plan = read_csv(POSITION_PLAN_FILE)
    adopted = position_plan[position_plan["Position判定"].astype(str).eq("採用")].copy() if not position_plan.empty and "Position判定" in position_plan.columns else pd.DataFrame()
    investment = safe_float(pd.to_numeric(adopted.get("投資金額円", pd.Series(dtype=float)), errors="coerce").sum())
    capital = safe_float(config.get("account_capital_yen", 300000), 300000)
    exposure = investment / capital * 100.0 if capital else 0.0
    realized_pnl = today_realized_pnl()

    stop_file = ROOT_DIR / str(config.get("emergency_stop_file", "EMERGENCY_STOP"))
    heartbeat_file = ROOT_DIR / str(config.get("rss_heartbeat_file", "state/rss_bridge_heartbeat.json"))
    heartbeat_age = heartbeat_age_seconds(heartbeat_file)
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    config_errors = validate_execution_config(config)
    add("設定検証", not config_errors, "正常" if not config_errors else " / ".join(config_errors))
    add("緊急停止", not stop_file.exists(), "停止ファイルなし" if not stop_file.exists() else str(stop_file))
    add("信用取引禁止", not bool(config.get("allow_margin", False)), "現物のみ")
    add("成行注文禁止", not bool(config.get("allow_market_order", False)), "指値のみ")
    add("日次損失上限", realized_pnl > -safe_float(config.get("maximum_daily_loss_yen", 1500), 1500), f"本日確定損益 {realized_pnl:,.0f}円")
    add("総エクスポージャー", exposure <= safe_float(config.get("maximum_total_exposure_percent", 30.0), 30.0), f"予定 {exposure:.2f}%")

    mode = str(config.get("mode", "DRY_RUN")).upper()
    if mode == "LIVE":
        max_age = safe_float(config.get("rss_heartbeat_max_age_seconds", 90), 90)
        data_health = load_json(DATA_HEALTH_FILE)
        add("RSSブリッジ接続", heartbeat_age is not None and heartbeat_age <= max_age, f"Heartbeat age={heartbeat_age}")
        add("RSSリアルタイム価格", bool(data_health.get("live_data_ready", False)), "現在値・気配ファイル必須")
        add("LIVE解除文言", str(config.get("live_unlock_phrase", "")) == "I_ACCEPT_LIVE_TRADING_RISK", "解除文言確認")
        add("LIVEフラグ", bool(config.get("live_trading", False)), "live_trading=true 必須")
    else:
        add("実売買禁止", not bool(config.get("live_trading", False)), f"mode={mode}")

    allowed = all(item["ok"] for item in checks)
    summary = {
        "version": "PHOENIX v6.6", "generated_at": now_text(), "mode": mode,
        "allowed": allowed, "decision": "ALLOW" if allowed else "BLOCK",
        "realized_pnl_yen": round(realized_pnl, 2), "planned_exposure_percent": round(exposure, 3),
        "checks": checks,
    }
    save_json(RISK_SUMMARY_FILE, summary)
    lines = ["PHOENIX v6.6 RISK CONTROLLER", "=" * 100, f"生成時刻: {summary['generated_at']}", f"モード: {mode}", f"判定: {summary['decision']}", ""]
    lines.extend(f"{'OK' if i['ok'] else 'BLOCK':<6} {i['name']}: {i['detail']}" for i in checks)
    RISK_REPORT_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("=" * 100); print("PHOENIX v6.6 RISK CONTROLLER"); print("=" * 100)
    print(f"モード : {mode}"); print(f"判定   : {summary['decision']}")
    for item in checks: print(f"{'OK' if item['ok'] else 'BLOCK':<6} {item['name']}: {item['detail']}")


if __name__ == "__main__":
    main()
