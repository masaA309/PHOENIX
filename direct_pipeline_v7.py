from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from phoenix_core import create_broker
from phoenix_core.pipeline import (
    run_direct_pipeline_from_csv,
    save_pipeline_logs,
)
from phoenix_core.position_sizer import PositionSizingConfig
from phoenix_core.risk_controller import RiskConfig

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "config" / "v7_direct_pipeline_config.json"


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


def find_candidate_file(files: dict[str, Any]) -> Path:
    configured = str(files.get("candidates", "")).strip()
    paths = []
    if configured:
        paths.append(resolve_path(configured))
    paths.extend([
        ROOT_DIR / "reports" / "portfolio_selection.csv",
        ROOT_DIR / "reports" / "portfolio_plan.csv",
        ROOT_DIR / "reports" / "trade_signals.csv",
        ROOT_DIR / "reports" / "price_watchlist.csv",
    ])
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def sizing_config(payload: dict[str, Any]) -> PositionSizingConfig:
    c = payload.get("position_sizing", {})
    return PositionSizingConfig(
        risk_per_trade_pct=float(c.get("risk_per_trade_pct", 0.01)),
        max_position_pct=float(c.get("max_position_pct", 0.30)),
        max_total_invested_pct=float(c.get("max_total_invested_pct", 0.80)),
        minimum_cash_reserve_pct=float(c.get("minimum_cash_reserve_pct", 0.10)),
        fallback_stop_distance_pct=float(c.get("fallback_stop_distance_pct", 0.03)),
        lot_size=int(c.get("lot_size", 100)),
        maximum_quantity_per_ticker=int(c.get("maximum_quantity_per_ticker", 1000)),
        allow_pyramiding=bool(c.get("allow_pyramiding", False)),
        commission_buffer_pct=float(c.get("commission_buffer_pct", 0.001)),
    )


def risk_config(payload: dict[str, Any]) -> RiskConfig:
    c = payload.get("risk", {})
    return RiskConfig(
        max_daily_loss_pct=float(c.get("max_daily_loss_pct", 0.03)),
        max_drawdown_pct=float(c.get("max_drawdown_pct", 0.10)),
        max_positions=int(c.get("max_positions", 5)),
        max_total_invested_pct=float(c.get("max_total_invested_pct", 0.80)),
        max_single_position_pct=float(c.get("max_single_position_pct", 0.30)),
        max_orders_per_run=int(c.get("max_orders_per_run", 3)),
        max_consecutive_losses=int(c.get("max_consecutive_losses", 3)),
        minimum_cash_reserve_pct=float(c.get("minimum_cash_reserve_pct", 0.10)),
        block_on_broker_health_failure=bool(c.get("block_on_broker_health_failure", True)),
    )


def main() -> None:
    configure_console()
    parser = argparse.ArgumentParser(description="PHOENIX v7 Direct Trading Pipeline")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="発注せず、Position SizerとRisk Controllerだけ実行します",
    )
    args = parser.parse_args()

    config = load_config(Path(args.config))
    broker = create_broker(config, ROOT_DIR)
    files = config.get("files", {})
    candidate_path = find_candidate_file(files)
    if not candidate_path.exists():
        raise FileNotFoundError(f"候補CSVが見つかりません: {candidate_path}")

    result = run_direct_pipeline_from_csv(
        broker=broker,
        candidate_path=candidate_path,
        sizing_config=sizing_config(config),
        risk_config=risk_config(config),
        risk_state_path=resolve_path(str(files.get("risk_state", "state/v7_risk_state.json"))),
        execute_orders=not args.dry_run,
    )

    save_pipeline_logs(
        result=result,
        plan_path=resolve_path(str(files.get("position_log", "reports/v7_direct_position_log.csv"))),
        risk_path=resolve_path(str(files.get("risk_log", "reports/v7_direct_risk_log.csv"))),
        execution_path=resolve_path(str(files.get("execution_log", "reports/v7_direct_execution_log.csv"))),
        summary_path=resolve_path(str(files.get("summary", "reports/v7_direct_pipeline_summary.json"))),
    )

    final_snapshot = broker.get_account_snapshot()
    print("=" * 118)
    print("PHOENIX v7 DIRECT TRADING PIPELINE")
    print("=" * 118)
    print(f"Broker             : {broker.broker_name}")
    print(f"Mode               : {'DRY RUN' if args.dry_run else 'PAPER EXECUTION'}")
    print(f"候補ファイル       : {candidate_path}")
    print(f"候補数             : {result.candidate_count}件")
    print(f"Position Sizer通過 : {result.ready_count}件")
    print(f"Risk承認           : {result.approved_count}件")
    print(f"約定               : {result.filled_count}件")
    print(f"システム停止       : {'YES' if result.risk_report.halted else 'NO'}")
    print("-" * 118)
    for decision in result.risk_report.decisions:
        status = "APPROVE" if decision.accepted else "REJECT"
        print(f"{status:8} {decision.side:4} {decision.ticker:10} {decision.quantity:6}株 {decision.price:,.2f}円 {decision.reason}")
    if result.execution_results:
        print("-" * 118)
        for execution in result.execution_results:
            print(f"{execution.status.value:8} {execution.side.value:4} {execution.ticker:10} {execution.filled_quantity:6}株 {execution.filled_price:,.2f}円 {execution.message}")
    print("-" * 118)
    print(f"現金               : {final_snapshot.cash_yen:,.0f}円")
    print(f"評価額             : {final_snapshot.market_value_yen:,.0f}円")
    print(f"口座資産           : {final_snapshot.equity_yen:,.0f}円")
    print(f"保有銘柄数         : {len(final_snapshot.positions)}件")
    print("=" * 118)


if __name__ == "__main__":
    main()
