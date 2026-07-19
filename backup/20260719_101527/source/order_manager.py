from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import json
import sys
from typing import Any

import pandas as pd

from execution_core import bootstrap_environment

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
EXECUTION_DIR = ROOT_DIR / "execution"
CONFIG_FILE = ROOT_DIR / "config" / "execution_config.json"
CANDIDATES_FILE = REPORT_DIR / "execution_candidates.csv"
ORDER_BOOK_FILE = EXECUTION_DIR / "order_book.csv"
SUMMARY_FILE = REPORT_DIR / "order_manager_summary.json"
REPORT_FILE = REPORT_DIR / "order_manager_report.txt"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            continue
    return pd.DataFrame()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def order_id(ticker: str, side: str, shares: int, price: float) -> str:
    trading_day = datetime.now().strftime("%Y%m%d")
    key = f"{trading_day}|{ticker}|{side}|{shares}|{price:.2f}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12].upper()
    return f"PX-{trading_day}-{digest}"


def main() -> None:
    configure_console()
    EXECUTION_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    config = bootstrap_environment()["config"]
    candidates = read_csv(CANDIDATES_FILE)
    existing = read_csv(ORDER_BOOK_FILE)

    rows: list[dict[str, Any]] = []
    if not candidates.empty:
        for _, row in candidates[candidates["execution_decision"].astype(str).eq("READY")].iterrows():
            ticker = str(row.get("ticker", ""))
            side = str(row.get("side", "BUY"))
            shares = int(float(row.get("shares_rss", 0)))
            entry = float(row.get("entry_price", 0))
            oid = order_id(ticker, side, shares, entry)
            if not existing.empty and "order_id" in existing.columns and existing["order_id"].astype(str).eq(oid).any():
                continue
            rows.append({
                "order_id": oid,
                "created_at": now_text(),
                "updated_at": now_text(),
                "mode": str(config.get("mode", "DRY_RUN")).upper(),
                "broker": str(config.get("broker", "楽天証券")),
                "ticker": ticker,
                "name": str(row.get("銘柄", "")),
                "side": side,
                "shares": shares,
                "order_type": "LIMIT",
                "limit_price": entry,
                "take_profit_price": float(row.get("take_profit_price", 0)),
                "stop_loss_price": float(row.get("stop_loss_price", 0)),
                "status": "APPROVED",
                "broker_order_number": "",
                "filled_shares": 0,
                "average_fill_price": 0.0,
                "last_error": "",
            })

    created = pd.DataFrame(rows)
    if existing.empty:
        order_book = created
    elif created.empty:
        order_book = existing
    else:
        order_book = pd.concat([existing, created], ignore_index=True)
    order_book.to_csv(ORDER_BOOK_FILE, index=False, encoding="utf-8-sig")

    active = order_book[~order_book.get("status", pd.Series(dtype=str)).astype(str).isin(["CLOSED", "CANCELLED", "REJECTED"])] if not order_book.empty else pd.DataFrame()
    summary = {
        "version": "PHOENIX v6.5.1",
        "generated_at": now_text(),
        "created_orders": len(created),
        "total_orders": len(order_book),
        "active_orders": len(active),
    }
    SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_FILE.write_text(
        "\n".join([
            "PHOENIX v6.5.1 ORDER MANAGER",
            "=" * 100,
            f"新規作成: {len(created)}件",
            f"注文台帳: {len(order_book)}件",
            f"有効注文: {len(active)}件",
            "",
            order_book.tail(20).to_string(index=False) if not order_book.empty else "注文なし",
            "",
        ]),
        encoding="utf-8",
    )
    print("=" * 100)
    print("PHOENIX v6.5.1 ORDER MANAGER")
    print("=" * 100)
    print(f"新規作成 : {len(created)}件")
    print(f"注文台帳 : {len(order_book)}件")


if __name__ == "__main__":
    main()
