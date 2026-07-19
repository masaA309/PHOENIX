from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from phoenix_core import (
    create_broker,
    execute_events,
    normalize_events,
    normalize_plan,
    save_snapshot,
)


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "config" / "v7_execution_config.json"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルがありません: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("設定ファイルのルートはJSONオブジェクトにしてください")
    return payload


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def run(config: dict[str, Any]) -> dict[str, Any]:
    broker = create_broker(config, ROOT_DIR)
    health = broker.health_check()

    if not health.healthy:
        raise RuntimeError(health.message)

    files = config.get("files", {})
    execution = config.get("execution", {})

    event_path = resolve_path(
        str(
            files.get(
                "events",
                "reports/price_alert_dry_run.csv",
            )
        )
    )
    plan_path = resolve_path(
        str(
            files.get(
                "position_plan",
                "reports/position_plan.csv",
            )
        )
    )
    log_path = resolve_path(
        str(
            files.get(
                "execution_log",
                "reports/v7_execution_log.csv",
            )
        )
    )
    snapshot_path = resolve_path(
        str(
            files.get(
                "account_snapshot",
                "reports/v7_account_snapshot.json",
            )
        )
    )

    events = normalize_events(event_path)
    plan = normalize_plan(plan_path)

    print("=" * 100)
    print("PHOENIX v7 EXECUTION ENGINE")
    print("=" * 100)
    print(f"Broker        : {broker.broker_name}")
    print(f"Health        : {'PASS' if health.healthy else 'FAIL'}")
    print("実売買        : 無効")
    print(f"イベント件数  : {len(events)}")

    results = execute_events(
        broker=broker,
        events=events,
        plan=plan,
        log_path=log_path,
        default_quantity=max(
            1,
            int(execution.get("default_quantity", 100)),
        ),
        lot_size=max(
            1,
            int(execution.get("lot_size", 100)),
        ),
    )

    for result in results:
        print(
            f"{result.status.value:8} "
            f"{result.side.value:4} "
            f"{result.ticker:10} "
            f"{result.quantity:6}株 "
            f"{result.requested_price:,.2f}円 "
            f"{result.message}"
        )

    snapshot = save_snapshot(broker, snapshot_path)

    filled = sum(
        result.status.value == "FILLED"
        for result in results
    )
    rejected = sum(
        result.status.value == "REJECTED"
        for result in results
    )

    print("-" * 100)
    print(f"約定          : {filled}件")
    print(f"拒否          : {rejected}件")
    print(f"利用可能現金  : {snapshot['cash_yen']:,.0f}円")
    print(f"保有評価額    : {snapshot['market_value_yen']:,.0f}円")
    print(f"現在資産      : {snapshot['equity_yen']:,.0f}円")
    print(f"確定損益      : {snapshot['realized_pnl_yen']:+,.0f}円")
    print(f"実行ログ      : {log_path}")
    print(f"口座状態      : {snapshot_path}")
    print("=" * 100)

    return snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX v7 Execution Engine"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="設定JSON",
    )
    parser.add_argument(
        "--reset-paper",
        action="store_true",
        help="Paper Broker状態を初期化してから実行",
    )
    return parser.parse_args()


def main() -> None:
    configure_console()
    args = parse_args()
    config = load_config(Path(args.config))
    broker = create_broker(config, ROOT_DIR)

    if args.reset_paper and hasattr(broker, "reset"):
        broker.reset()
        print("Paper Broker状態を初期化しました。")

    run(config)


if __name__ == "__main__":
    main()
