from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from phoenix_core import create_broker
from phoenix_core.risk_controller import (
    RiskConfig,
    evaluate_orders,
    load_order_requests,
    load_risk_state,
    save_risk_outputs,
    save_risk_state,
)

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "config" / "v7_risk_config.json"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("設定ファイルのルートはJSONオブジェクトにしてください")
    return payload


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def config_from_json(payload: dict[str, Any]) -> RiskConfig:
    risk = payload.get("risk", {})
    return RiskConfig(
        max_daily_loss_pct=float(risk.get("max_daily_loss_pct", 0.03)),
        max_drawdown_pct=float(risk.get("max_drawdown_pct", 0.10)),
        max_positions=int(risk.get("max_positions", 5)),
        max_total_invested_pct=float(risk.get("max_total_invested_pct", 0.80)),
        max_single_position_pct=float(risk.get("max_single_position_pct", 0.30)),
        max_orders_per_run=int(risk.get("max_orders_per_run", 3)),
        max_consecutive_losses=int(risk.get("max_consecutive_losses", 3)),
        minimum_cash_reserve_pct=float(risk.get("minimum_cash_reserve_pct", 0.10)),
        block_on_broker_health_failure=bool(
            risk.get("block_on_broker_health_failure", True)
        ),
    )


def run(config: dict[str, Any]) -> int:
    broker = create_broker(config, ROOT_DIR)
    files = config.get("files", {})

    orders_path = resolve_path(
        str(files.get("orders", "reports/v7_order_requests.json"))
    )
    approved_path = resolve_path(
        str(files.get("approved_orders", "reports/v7_risk_approved_orders.json"))
    )
    report_path = resolve_path(
        str(files.get("report", "reports/v7_risk_report.txt"))
    )
    state_path = resolve_path(
        str(files.get("state", "state/v7_risk_state.json"))
    )

    snapshot = broker.get_account_snapshot()
    state = load_risk_state(state_path, snapshot.equity_yen)
    orders = load_order_requests(orders_path)
    report = evaluate_orders(
        broker=broker,
        orders=orders,
        config=config_from_json(config),
        state=state,
    )

    save_risk_state(state_path, state)
    save_risk_outputs(report, approved_path, report_path)

    print("=" * 110)
    print("PHOENIX v7 BROKER RISK CONTROLLER")
    print("=" * 110)
    print(f"Broker            : {report.broker_name}")
    print(f"Health            : {'PASS' if report.health_pass else 'FAIL'}")
    print(f"現在資産          : {report.equity_yen:,.0f}円")
    print(f"日次損益          : {report.daily_pnl_yen:+,.0f}円")
    print(f"日次損失率        : {report.daily_loss_pct:.2%}")
    print(f"ドローダウン      : {report.drawdown_pct:.2%}")
    print(f"保有銘柄数        : {report.current_positions}件")
    print(f"連敗数            : {report.consecutive_losses}回")
    print(f"システム停止      : {'YES' if report.halted else 'NO'}")
    print("-" * 110)

    for decision in report.decisions:
        status = "APPROVE" if decision.accepted else "REJECT"
        print(
            f"{status:8} {decision.side:4} {decision.ticker:10} "
            f"{decision.quantity:6}株 {decision.price:,.2f}円 "
            f"{decision.reason}"
        )

    print("-" * 110)
    print(f"入力注文数        : {len(report.decisions)}件")
    print(f"承認注文数        : {len(report.accepted_orders)}件")
    print(f"Approved Orders   : {approved_path}")
    print(f"Risk Report       : {report_path}")
    print(f"Risk State        : {state_path}")
    print("=" * 110)
    return len(report.accepted_orders)


def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(description="PHOENIX v7 Risk Controller")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    run(load_config(Path(args.config)))


if __name__ == "__main__":
    main()
