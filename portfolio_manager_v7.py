from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from phoenix_core import create_broker
from phoenix_core.portfolio import (
    save_portfolio_outputs,
    update_market_prices,
)


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = (
    ROOT_DIR
    / "config"
    / "v7_portfolio_config.json"
)


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )
    except (AttributeError, OSError):
        pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(
            f"設定ファイルがありません: {path}"
        )

    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(payload, dict):
        raise ValueError(
            "設定ファイルのルートは"
            "JSONオブジェクトにしてください"
        )

    return payload


def resolve_path(value: str) -> Path:
    path = Path(value)
    return (
        path
        if path.is_absolute()
        else ROOT_DIR / path
    )


def run(config: dict[str, Any]) -> dict[str, Any]:
    broker = create_broker(
        config,
        ROOT_DIR,
    )

    health = broker.health_check()

    if not health.healthy:
        raise RuntimeError(
            f"Broker Health異常: {health.message}"
        )

    files = config.get("files", {})

    quote_path = resolve_path(
        str(
            files.get(
                "quotes",
                "reports/price_monitor_state.csv",
            )
        )
    )

    summary_path = resolve_path(
        str(
            files.get(
                "summary",
                "reports/v7_portfolio_summary.json",
            )
        )
    )

    positions_path = resolve_path(
        str(
            files.get(
                "positions",
                "reports/v7_portfolio_positions.csv",
            )
        )
    )

    report_path = resolve_path(
        str(
            files.get(
                "report",
                "reports/v7_portfolio_report.txt",
            )
        )
    )

    updated = update_market_prices(
        broker,
        quote_path,
    )

    payload = save_portfolio_outputs(
        broker=broker,
        summary_path=summary_path,
        positions_path=positions_path,
        report_path=report_path,
    )

    account = payload["account"]
    risk = payload["risk"]

    print("=" * 100)
    print("PHOENIX v7 BROKER PORTFOLIO MANAGER")
    print("=" * 100)
    print(f"Broker        : {payload['broker']['name']}")
    print(
        "Health        : "
        + (
            "PASS"
            if payload["broker"]["healthy"]
            else "FAIL"
        )
    )
    print("実売買        : 無効")
    print(f"価格更新      : {updated}件")
    print("-" * 100)
    print(
        f"利用可能現金  : "
        f"{account['cash_yen']:,.0f}円"
    )
    print(
        f"買付余力      : "
        f"{account['buying_power_yen']:,.0f}円"
    )
    print(
        f"保有評価額    : "
        f"{account['market_value_yen']:,.0f}円"
    )
    print(
        f"現在資産      : "
        f"{account['equity_yen']:,.0f}円"
    )
    print(
        f"確定損益      : "
        f"{account['realized_pnl_yen']:+,.0f}円"
    )
    print(
        f"含み損益      : "
        f"{account['unrealized_pnl_yen']:+,.0f}円"
    )
    print(
        f"総損益        : "
        f"{account['total_pnl_yen']:+,.0f}円"
    )
    print(
        f"保有銘柄数    : "
        f"{account['position_count']}件"
    )
    print("-" * 100)
    print(
        f"現金比率      : "
        f"{risk['cash_ratio']:.2%}"
    )
    print(
        f"投資比率      : "
        f"{risk['invested_ratio']:.2%}"
    )
    print(
        f"最大銘柄比率  : "
        f"{risk['largest_position_ratio']:.2%}"
    )
    print("-" * 100)
    print(f"Summary       : {summary_path}")
    print(f"Positions     : {positions_path}")
    print(f"Report        : {report_path}")
    print("=" * 100)

    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PHOENIX v7 Broker Portfolio Manager"
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="設定JSON",
    )
    return parser.parse_args()


def main() -> None:
    configure_console()
    args = parse_args()
    config = load_config(
        Path(args.config)
    )
    run(config)


if __name__ == "__main__":
    main()
