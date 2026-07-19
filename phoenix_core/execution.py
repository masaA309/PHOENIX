from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from phoenix_core.broker import BrokerAdapter
from phoenix_core.models import (
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)


ENTRY_EVENTS = {"ENTRY", "BUY"}
EXIT_EVENTS = {
    "TAKE_PROFIT",
    "TARGET",
    "STOP_LOSS",
    "STOP",
    "EXIT",
    "CLOSE",
    "SELL",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if result == result else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def normalize_events(path: Path) -> pd.DataFrame:
    frame = load_csv(path)
    if frame.empty:
        return pd.DataFrame(
            columns=["日時", "イベント", "ticker", "現在価格"]
        )

    aliases = {
        "datetime": "日時",
        "event": "イベント",
        "symbol": "ticker",
        "price": "現在価格",
    }
    frame = frame.rename(
        columns={
            source: target
            for source, target in aliases.items()
            if source in frame.columns and target not in frame.columns
        }
    )

    required = {"日時", "イベント", "ticker", "現在価格"}
    if not required.issubset(frame.columns):
        missing = required - set(frame.columns)
        raise ValueError(
            "イベントCSVに必要な列がありません: "
            + ", ".join(sorted(missing))
        )

    frame["日時"] = pd.to_datetime(frame["日時"], errors="coerce")
    frame["現在価格"] = pd.to_numeric(
        frame["現在価格"],
        errors="coerce",
    )
    return (
        frame.dropna(
            subset=["日時", "イベント", "ticker", "現在価格"]
        )
        .sort_values("日時")
        .reset_index(drop=True)
    )


def normalize_plan(path: Path) -> pd.DataFrame:
    frame = load_csv(path)
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "株数"])

    aliases = {
        "symbol": "ticker",
        "quantity": "株数",
        "shares": "株数",
        "recommended_shares": "株数",
        "推奨株数": "株数",
    }
    frame = frame.rename(
        columns={
            source: target
            for source, target in aliases.items()
            if source in frame.columns and target not in frame.columns
        }
    )

    if "ticker" not in frame.columns:
        return pd.DataFrame(columns=["ticker", "株数"])

    if "株数" not in frame.columns:
        frame["株数"] = 0

    frame["株数"] = pd.to_numeric(
        frame["株数"],
        errors="coerce",
    ).fillna(0)

    return frame


def stable_order_id(
    event_time: pd.Timestamp,
    event_type: str,
    ticker: str,
) -> str:
    raw = (
        f"{event_time.isoformat()}|"
        f"{event_type.upper()}|"
        f"{ticker.upper()}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"PHX-{digest.upper()}"


def held_quantity(
    broker: BrokerAdapter,
    ticker: str,
) -> int:
    snapshot = broker.get_account_snapshot()
    for position in snapshot.positions:
        if position.ticker.upper() == ticker.upper():
            return position.quantity
    return 0


def plan_quantity(
    plan: pd.DataFrame,
    ticker: str,
    default_quantity: int,
) -> int:
    matched = plan[
        plan["ticker"].astype(str).str.upper() == ticker.upper()
    ]
    if matched.empty:
        return default_quantity

    quantity = safe_int(matched.iloc[-1].get("株数"), 0)
    return quantity if quantity > 0 else default_quantity


def order_from_event(
    event: pd.Series,
    plan: pd.DataFrame,
    broker: BrokerAdapter,
    default_quantity: int,
    lot_size: int,
) -> OrderRequest | None:
    ticker = str(event["ticker"]).strip().upper()
    event_type = str(event["イベント"]).strip().upper()
    event_time = pd.Timestamp(event["日時"])
    price = round(safe_float(event["現在価格"]), 2)

    if price <= 0:
        return None

    if event_type in ENTRY_EVENTS:
        quantity = plan_quantity(
            plan,
            ticker,
            default_quantity,
        )
        side = OrderSide.BUY
    elif event_type in EXIT_EVENTS:
        quantity = held_quantity(broker, ticker)
        side = OrderSide.SELL
    else:
        return None

    if quantity <= 0:
        return None

    lot = max(1, lot_size)
    quantity = (quantity // lot) * lot
    if quantity <= 0:
        return None

    return OrderRequest(
        ticker=ticker,
        side=side,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=price,
        client_order_id=stable_order_id(
            event_time,
            event_type,
            ticker,
        ),
        strategy_name="PHOENIX_V7",
        metadata={
            "source_event": event_type,
            "source_time": event_time.isoformat(),
        },
    )


def append_execution_log(
    path: Path,
    event: pd.Series,
    result: OrderResult | None,
    message: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "記録日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "イベント日時": pd.Timestamp(event["日時"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "イベント": str(event["イベント"]),
        "ticker": str(event["ticker"]),
        "現在価格": safe_float(event["現在価格"]),
        "broker": "" if result is None else result.broker_name,
        "client_order_id": (
            "" if result is None else result.client_order_id
        ),
        "broker_order_id": (
            "" if result is None else result.broker_order_id
        ),
        "売買": "" if result is None else result.side.value,
        "注文株数": 0 if result is None else result.quantity,
        "約定株数": 0 if result is None else result.filled_quantity,
        "注文価格": (
            0.0 if result is None else result.requested_price
        ),
        "約定価格": 0.0 if result is None else result.filled_price,
        "状態": "SKIPPED" if result is None else result.status.value,
        "メッセージ": message,
    }

    frame = pd.DataFrame([record])
    frame.to_csv(
        path,
        mode="a",
        header=not path.exists() or path.stat().st_size == 0,
        index=False,
        encoding="utf-8-sig",
    )


def execute_events(
    broker: BrokerAdapter,
    events: pd.DataFrame,
    plan: pd.DataFrame,
    log_path: Path,
    default_quantity: int,
    lot_size: int,
) -> list[OrderResult]:
    results: list[OrderResult] = []

    exit_mask = (
        events["イベント"]
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(EXIT_EVENTS)
    )
    ordered = pd.concat(
        [
            events[exit_mask].sort_values("日時"),
            events[~exit_mask].sort_values("日時"),
        ],
        ignore_index=True,
    )

    for _, event in ordered.iterrows():
        order = order_from_event(
            event=event,
            plan=plan,
            broker=broker,
            default_quantity=default_quantity,
            lot_size=lot_size,
        )

        if order is None:
            append_execution_log(
                log_path,
                event,
                None,
                "注文対象外または売却可能株数なし",
            )
            continue

        result = broker.submit_order(order)
        append_execution_log(
            log_path,
            event,
            result,
            result.message,
        )
        results.append(result)

    return results


def snapshot_to_dict(broker: BrokerAdapter) -> dict[str, Any]:
    snapshot = broker.get_account_snapshot()
    return {
        "broker_name": snapshot.broker_name,
        "generated_at": snapshot.generated_at.isoformat(
            timespec="seconds"
        ),
        "cash_yen": snapshot.cash_yen,
        "market_value_yen": snapshot.market_value_yen,
        "unrealized_pnl_yen": snapshot.unrealized_pnl_yen,
        "realized_pnl_yen": snapshot.realized_pnl_yen,
        "equity_yen": snapshot.equity_yen,
        "positions": [
            asdict(position)
            for position in snapshot.positions
        ],
    }


def save_snapshot(
    broker: BrokerAdapter,
    path: Path,
) -> dict[str, Any]:
    payload = snapshot_to_dict(broker)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload
