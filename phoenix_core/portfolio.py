from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pandas as pd

from phoenix_core.broker import BrokerAdapter
from phoenix_core.models import AccountSnapshot, Position


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


def position_rows(snapshot: AccountSnapshot) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for position in snapshot.positions:
        rows.append(
            {
                "ticker": position.ticker,
                "株数": position.quantity,
                "平均取得価格": round(position.average_price, 2),
                "現在価格": round(position.market_price, 2),
                "取得額": round(
                    position.quantity * position.average_price,
                    2,
                ),
                "評価額": position.market_value,
                "含み損益": position.unrealized_pnl,
                "含み損益率%": round(
                    (
                        position.market_price
                        / position.average_price
                        - 1.0
                    )
                    * 100,
                    4,
                )
                if position.average_price > 0
                else 0.0,
            }
        )

    return rows


def position_frame(snapshot: AccountSnapshot) -> pd.DataFrame:
    columns = [
        "ticker",
        "株数",
        "平均取得価格",
        "現在価格",
        "取得額",
        "評価額",
        "含み損益",
        "含み損益率%",
    ]
    return pd.DataFrame(
        position_rows(snapshot),
        columns=columns,
    )


def concentration_metrics(
    snapshot: AccountSnapshot,
) -> dict[str, float]:
    equity = snapshot.equity_yen

    if equity <= 0 or not snapshot.positions:
        return {
            "largest_position_ratio": 0.0,
            "cash_ratio": 1.0 if snapshot.cash_yen > 0 else 0.0,
            "invested_ratio": 0.0,
        }

    values = [
        position.market_value
        for position in snapshot.positions
    ]

    return {
        "largest_position_ratio": round(
            max(values) / equity,
            6,
        ),
        "cash_ratio": round(
            snapshot.cash_yen / equity,
            6,
        ),
        "invested_ratio": round(
            snapshot.market_value_yen / equity,
            6,
        ),
    }


def build_portfolio_summary(
    broker: BrokerAdapter,
) -> dict[str, Any]:
    health = broker.health_check()
    snapshot = broker.get_account_snapshot()
    concentration = concentration_metrics(snapshot)

    return {
        "version": "PHOENIX v7.0 Step3",
        "generated_at": datetime.now().isoformat(
            timespec="seconds"
        ),
        "broker": {
            "name": broker.broker_name,
            "healthy": health.healthy,
            "live_trading_enabled": health.live_trading_enabled,
            "message": health.message,
        },
        "account": {
            "cash_yen": snapshot.cash_yen,
            "market_value_yen": snapshot.market_value_yen,
            "equity_yen": snapshot.equity_yen,
            "realized_pnl_yen": snapshot.realized_pnl_yen,
            "unrealized_pnl_yen": snapshot.unrealized_pnl_yen,
            "total_pnl_yen": round(
                snapshot.realized_pnl_yen
                + snapshot.unrealized_pnl_yen,
                2,
            ),
            "position_count": len(snapshot.positions),
            "buying_power_yen": snapshot.cash_yen,
        },
        "risk": {
            "largest_position_ratio": concentration[
                "largest_position_ratio"
            ],
            "cash_ratio": concentration["cash_ratio"],
            "invested_ratio": concentration["invested_ratio"],
        },
        "positions": position_rows(snapshot),
    }


def save_portfolio_outputs(
    broker: BrokerAdapter,
    summary_path: Path,
    positions_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    payload = build_portfolio_summary(broker)

    for path in (
        summary_path,
        positions_path,
        report_path,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)

    summary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    snapshot = broker.get_account_snapshot()
    frame = position_frame(snapshot)
    frame.to_csv(
        positions_path,
        index=False,
        encoding="utf-8-sig",
    )

    account = payload["account"]
    risk = payload["risk"]

    lines = [
        "=" * 100,
        "PHOENIX v7 BROKER PORTFOLIO MANAGER",
        "=" * 100,
        f"作成日時             : {payload['generated_at']}",
        f"Broker               : {payload['broker']['name']}",
        f"Broker Health        : "
        f"{'PASS' if payload['broker']['healthy'] else 'FAIL'}",
        f"実売買               : "
        f"{'有効' if payload['broker']['live_trading_enabled'] else '無効'}",
        "-" * 100,
        f"利用可能現金         : {account['cash_yen']:,.0f}円",
        f"買付余力             : {account['buying_power_yen']:,.0f}円",
        f"保有評価額           : {account['market_value_yen']:,.0f}円",
        f"口座資産             : {account['equity_yen']:,.0f}円",
        f"確定損益             : {account['realized_pnl_yen']:+,.0f}円",
        f"含み損益             : {account['unrealized_pnl_yen']:+,.0f}円",
        f"総損益               : {account['total_pnl_yen']:+,.0f}円",
        f"保有銘柄数           : {account['position_count']}件",
        "-" * 100,
        f"現金比率             : {risk['cash_ratio']:.2%}",
        f"投資比率             : {risk['invested_ratio']:.2%}",
        f"最大銘柄比率         : {risk['largest_position_ratio']:.2%}",
        "-" * 100,
    ]

    if frame.empty:
        lines.append("保有銘柄はありません。")
    else:
        lines.append(frame.to_string(index=False))

    lines.extend(
        [
            "=" * 100,
            "口座情報はBroker Adapterから取得しています。",
            "=" * 100,
        ]
    )

    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return payload


def update_market_prices(
    broker: BrokerAdapter,
    quote_file: Path,
) -> int:
    """
    Paper Broker専用の価格更新補助。

    quote_fileは以下のいずれかの列名を受け付ける。
    ticker/symbol
    現在価格/最新価格/price/close
    """
    if not quote_file.exists():
        return 0

    try:
        frame = pd.read_csv(quote_file)
    except pd.errors.EmptyDataError:
        return 0

    aliases = {
        "symbol": "ticker",
        "現在価格": "価格",
        "最新価格": "価格",
        "price": "価格",
        "close": "価格",
    }

    frame = frame.rename(
        columns={
            source: target
            for source, target in aliases.items()
            if source in frame.columns
            and target not in frame.columns
        }
    )

    if "ticker" not in frame.columns or "価格" not in frame.columns:
        return 0

    setter = getattr(broker, "set_market_price", None)
    if not callable(setter):
        return 0

    held = {
        position.ticker.upper()
        for position in broker.get_account_snapshot().positions
    }

    updated = 0

    for _, row in frame.iterrows():
        ticker = str(row.get("ticker", "")).strip().upper()
        price = safe_float(row.get("価格"))

        if ticker not in held or price <= 0:
            continue

        setter(ticker, price)
        updated += 1

    return updated
