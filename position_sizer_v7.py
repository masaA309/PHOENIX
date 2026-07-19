from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from phoenix_core import create_broker
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    build_order_requests,
    decisions_frame,
    normalize_candidates,
    save_position_sizing_outputs,
    size_candidates,
)


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = (
    ROOT_DIR
    / "config"
    / "v7_position_sizer_config.json"
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


def find_candidate_file(
    files_config: dict[str, Any],
) -> Path:
    configured = str(
        files_config.get("candidates", "")
    ).strip()

    candidates = []
    if configured:
        candidates.append(resolve_path(configured))

    candidates.extend(
        [
            ROOT_DIR
            / "reports"
            / "portfolio_selection.csv",
            ROOT_DIR
            / "reports"
            / "portfolio_plan.csv",
            ROOT_DIR
            / "reports"
            / "trade_signals.csv",
            ROOT_DIR
            / "reports"
            / "price_watchlist.csv",
        ]
    )

    for path in candidates:
        if path.exists():
            return path

    return candidates[0]


def sizing_config_from_json(
    payload: dict[str, Any],
) -> PositionSizingConfig:
    sizing = payload.get("position_sizing", {})

    return PositionSizingConfig(
        risk_per_trade_pct=float(
            sizing.get(
                "risk_per_trade_pct",
                0.01,
            )
        ),
        max_position_pct=float(
            sizing.get(
                "max_position_pct",
                0.30,
            )
        ),
        max_total_invested_pct=float(
            sizing.get(
                "max_total_invested_pct",
                0.80,
            )
        ),
        minimum_cash_reserve_pct=float(
            sizing.get(
                "minimum_cash_reserve_pct",
                0.10,
            )
        ),
        fallback_stop_distance_pct=float(
            sizing.get(
                "fallback_stop_distance_pct",
                0.03,
            )
        ),
        lot_size=int(
            sizing.get("lot_size", 100)
        ),
        maximum_quantity_per_ticker=int(
            sizing.get(
                "maximum_quantity_per_ticker",
                1000,
            )
        ),
        allow_pyramiding=bool(
            sizing.get(
                "allow_pyramiding",
                False,
            )
        ),
        commission_buffer_pct=float(
            sizing.get(
                "commission_buffer_pct",
                0.001,
            )
        ),
    )


def run(config: dict[str, Any]) -> int:
    broker = create_broker(
        config,
        ROOT_DIR,
    )
    health = broker.health_check()

    if not health.healthy:
        raise RuntimeError(
            f"Broker Health異常: {health.message}"
        )

    files_config = config.get("files", {})
    candidate_path = find_candidate_file(
        files_config
    )

    if not candidate_path.exists():
        raise FileNotFoundError(
            "候補CSVが見つかりません。"
            f"確認先: {candidate_path}"
        )

    plan_path = resolve_path(
        str(
            files_config.get(
                "position_plan",
                "reports/v7_position_plan.csv",
            )
        )
    )
    orders_path = resolve_path(
        str(
            files_config.get(
                "orders",
                "reports/v7_order_requests.json",
            )
        )
    )
    report_path = resolve_path(
        str(
            files_config.get(
                "report",
                "reports/v7_position_sizer_report.txt",
            )
        )
    )

    candidates = normalize_candidates(
        candidate_path
    )
    sizing_config = sizing_config_from_json(
        config
    )

    decisions = size_candidates(
        broker=broker,
        candidates=candidates,
        config=sizing_config,
    )
    orders = build_order_requests(
        decisions
    )

    save_position_sizing_outputs(
        decisions=decisions,
        orders=orders,
        plan_path=plan_path,
        orders_path=orders_path,
        report_path=report_path,
    )

    snapshot = broker.get_account_snapshot()
    frame = decisions_frame(decisions)

    print("=" * 120)
    print("PHOENIX v7 BROKER POSITION SIZER")
    print("=" * 120)
    print(f"Broker            : {broker.broker_name}")
    print("Health            : PASS")
    print("実売買            : 無効")
    print(f"候補ファイル      : {candidate_path}")
    print(f"口座資産          : {snapshot.equity_yen:,.0f}円")
    print(f"買付余力          : {snapshot.cash_yen:,.0f}円")
    print(f"現在の保有銘柄数  : {len(snapshot.positions)}件")
    print("-" * 120)

    if frame.empty:
        print("有効な候補はありません。")
    else:
        display_columns = [
            "ticker",
            "銘柄",
            "エントリー価格",
            "損切価格",
            "保有株数",
            "推奨株数",
            "想定購入額",
            "想定損失額",
            "判定",
            "理由",
        ]
        print(
            frame[display_columns].to_string(
                index=False
            )
        )

    ready = sum(
        decision.executable
        for decision in decisions
    )
    skipped = len(decisions) - ready

    print("-" * 120)
    print(f"候補数            : {len(decisions)}件")
    print(f"発注可能          : {ready}件")
    print(f"見送り            : {skipped}件")
    print(f"Position Plan     : {plan_path}")
    print(f"Order Requests    : {orders_path}")
    print(f"Report            : {report_path}")
    print("=" * 120)

    return ready


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PHOENIX v7 Broker Position Sizer"
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
    arguments = parse_args()
    config = load_config(
        Path(arguments.config)
    )
    run(config)


if __name__ == "__main__":
    main()
