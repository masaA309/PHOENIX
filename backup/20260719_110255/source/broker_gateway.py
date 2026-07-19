from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
from typing import Any

import pandas as pd

from execution_core import ROOT_DIR, REPORT_DIR, EXECUTION_DIR, bootstrap_environment, load_json, read_csv
from realtime_gateway import RealtimeGateway

ORDER_BOOK_FILE = EXECUTION_DIR / "order_book.csv"
SUMMARY_FILE = REPORT_DIR / "broker_gateway_summary.json"
REPORT_FILE = REPORT_DIR / "broker_gateway_report.txt"


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def heartbeat_ok(config: dict[str, Any]) -> bool:
    path = ROOT_DIR / str(config.get("rss_heartbeat_file", "state/rss_bridge_heartbeat.json"))
    data = load_json(path)
    text = str(data.get("timestamp", ""))
    if not text:
        return False
    try:
        timestamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        return age <= float(config.get("rss_heartbeat_max_age_seconds", 90))
    except (ValueError, TypeError):
        return False


def main() -> None:
    EXECUTION_DIR.mkdir(parents=True, exist_ok=True); REPORT_DIR.mkdir(parents=True, exist_ok=True)
    config = bootstrap_environment()["config"]
    orders = read_csv(ORDER_BOOK_FILE)
    mode = str(config.get("mode", "DRY_RUN")).upper()
    queue_path = ROOT_DIR / str(config.get("order_queue_file", "execution/rss_order_queue.csv"))
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    gateway = RealtimeGateway()

    approved = orders[orders.get("status", pd.Series(dtype=str)).astype(str).eq("APPROVED")].copy() if not orders.empty else pd.DataFrame()
    queue_rows: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    for _, row in approved.iterrows():
        ticker = str(row.get("ticker", ""))
        quote = gateway.validate_quote(ticker)
        if not quote.valid:
            blocked_rows.append({"ticker": ticker, "reason": quote.reason})
            continue
        requested_limit = float(row.get("limit_price", 0) or 0)
        limit_price = quote.ask
        tolerance = float(config.get("entry_price_tolerance_percent", 1.0))
        deviation = abs(limit_price - requested_limit) / requested_limit * 100 if requested_limit > 0 else 0
        if requested_limit <= 0 or deviation > tolerance:
            blocked_rows.append({"ticker": ticker, "reason": f"発注直前価格乖離 {deviation:.3f}%"})
            continue
        queue_rows.append({
            "trigger": 0,
            "order_id": str(row.get("order_id", "")),
            "symbol_code": ticker.replace(".T", ""),
            "side": "3" if str(row.get("side", "BUY")).upper() == "BUY" else "1",
            "order_category": "0", "sor": "1",
            "quantity": int(float(row.get("shares", 0))),
            "price_type": "1", "limit_price": round(limit_price, 2),
            "execution_condition": "0", "expiration": "0", "account_type": "0",
            "stop_trigger_price": float(row.get("stop_loss_price", 0)),
            "take_profit_price": float(row.get("take_profit_price", 0)),
            "quote_timestamp_age_seconds": quote.age_seconds,
            "best_bid": quote.bid, "best_ask": quote.ask,
            "phoenix_mode": mode,
        })

    queue = pd.DataFrame(queue_rows)
    queue.to_csv(queue_path, index=False, encoding="utf-8-sig")
    live_requested = mode == "LIVE" and bool(config.get("live_trading", False))
    unlocked = str(config.get("live_unlock_phrase", "")) == "I_ACCEPT_LIVE_TRADING_RISK"
    bridge_ready = heartbeat_ok(config)
    live_permitted = live_requested and unlocked and bridge_ready and len(blocked_rows) == 0 and not queue.empty
    status = "QUEUE_CREATED_DRY_RUN" if mode != "LIVE" else ("LIVE_BRIDGE_READY" if live_permitted else "LIVE_BLOCKED")

    summary = {"version": "PHOENIX v6.6", "generated_at": now_text(), "mode": mode,
               "status": status, "queued_orders": len(queue), "blocked_orders": blocked_rows,
               "live_requested": live_requested, "live_permitted": live_permitted,
               "heartbeat_ok": bridge_ready, "queue_file": str(queue_path)}
    SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_FILE.write_text("\n".join(["PHOENIX v6.6 BROKER GATEWAY", "="*100,
        f"生成時刻: {summary['generated_at']}", f"モード: {mode}", f"状態: {status}",
        f"キュー件数: {len(queue)}", f"ブロック件数: {len(blocked_rows)}", f"LIVE許可: {live_permitted}",
        f"出力: {queue_path}", "", queue.to_string(index=False) if not queue.empty else "発注キューなし", "",
        json.dumps(blocked_rows, ensure_ascii=False, indent=2)]), encoding="utf-8")
    print("="*100); print("PHOENIX v6.6 BROKER GATEWAY"); print("="*100)
    print(f"モード       : {mode}"); print(f"状態         : {status}"); print(f"キュー件数   : {len(queue)}")
    print(f"ブロック件数 : {len(blocked_rows)}"); print(f"LIVE許可     : {live_permitted}")


if __name__ == "__main__": main()
