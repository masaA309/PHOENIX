from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import sys
from typing import Any

import pandas as pd

from execution_core import bootstrap_environment

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
EXECUTION_DIR = ROOT_DIR / "execution"
CONFIG_FILE = ROOT_DIR / "config" / "execution_config.json"
ORDER_BOOK_FILE = EXECUTION_DIR / "order_book.csv"
SUMMARY_FILE = REPORT_DIR / "broker_gateway_summary.json"
REPORT_FILE = REPORT_DIR / "broker_gateway_report.txt"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path) -> dict[str, Any]:
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
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            continue
    return pd.DataFrame()


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
    configure_console()
    EXECUTION_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    config = bootstrap_environment()["config"]
    orders = read_csv(ORDER_BOOK_FILE)
    mode = str(config.get("mode", "DRY_RUN")).upper()
    queue_path = ROOT_DIR / str(config.get("order_queue_file", "execution/rss_order_queue.csv"))
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    approved = orders[orders.get("status", pd.Series(dtype=str)).astype(str).eq("APPROVED")].copy() if not orders.empty else pd.DataFrame()
    queue_rows: list[dict[str, Any]] = []
    for _, row in approved.iterrows():
        queue_rows.append({
            "trigger": 0,
            "order_id": str(row.get("order_id", "")),
            "symbol_code": str(row.get("ticker", "")).replace(".T", ""),
            "side": "3" if str(row.get("side", "BUY")).upper() == "BUY" else "1",
            "order_category": "0",
            "sor": "1",
            "quantity": int(float(row.get("shares", 0))),
            "price_type": "1",
            "limit_price": float(row.get("limit_price", 0)),
            "execution_condition": "0",
            "expiration": "0",
            "account_type": "0",
            "stop_trigger_price": float(row.get("stop_loss_price", 0)),
            "take_profit_price": float(row.get("take_profit_price", 0)),
            "phoenix_mode": mode,
        })

    queue = pd.DataFrame(queue_rows)
    queue.to_csv(queue_path, index=False, encoding="utf-8-sig")

    live_requested = mode == "LIVE" and bool(config.get("live_trading", False))
    unlocked = str(config.get("live_unlock_phrase", "")) == "I_ACCEPT_LIVE_TRADING_RISK"
    bridge_ready = heartbeat_ok(config)
    live_permitted = live_requested and unlocked and bridge_ready

    # Python側から証券会社へ直接発注しない。Excel/VBA側が trigger=1 に変更し、
    # RssStockOrder_V を呼び出す構成を前提とする。
    status = "QUEUE_CREATED"
    if live_requested and not live_permitted:
        status = "LIVE_BLOCKED"
    elif live_permitted:
        status = "LIVE_BRIDGE_READY"

    summary = {
        "version": "PHOENIX v6.5.1",
        "generated_at": now_text(),
        "mode": mode,
        "status": status,
        "queued_orders": len(queue),
        "live_requested": live_requested,
        "live_permitted": live_permitted,
        "heartbeat_ok": bridge_ready,
        "queue_file": str(queue_path),
    }
    SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_FILE.write_text(
        "\n".join([
            "PHOENIX v6.5.1 BROKER GATEWAY",
            "=" * 100,
            f"生成時刻: {summary['generated_at']}",
            f"モード: {mode}",
            f"状態: {status}",
            f"キュー件数: {len(queue)}",
            f"LIVE許可: {live_permitted}",
            f"出力: {queue_path}",
            "",
            queue.to_string(index=False) if not queue.empty else "発注キューなし",
            "",
        ]),
        encoding="utf-8",
    )

    print("=" * 100)
    print("PHOENIX v6.5.1 BROKER GATEWAY")
    print("=" * 100)
    print(f"モード       : {mode}")
    print(f"状態         : {status}")
    print(f"キュー件数   : {len(queue)}")
    print(f"LIVE許可     : {live_permitted}")
    print(f"キューファイル: {queue_path}")


if __name__ == "__main__":
    main()
