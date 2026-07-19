from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from phoenix_core.broker import BrokerAdapter
from phoenix_core.models import OrderRequest, OrderResult, OrderStatus
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    SizingDecision,
    build_order_requests,
    decisions_frame,
    normalize_candidates,
    size_candidates,
)
from phoenix_core.risk_controller import (
    RiskConfig,
    RiskDecision,
    RiskReport,
    RiskState,
    evaluate_orders,
    load_risk_state,
    save_risk_state,
)


@dataclass(frozen=True, slots=True)
class PipelineResult:
    candidate_count: int
    sizing_decisions: tuple[SizingDecision, ...]
    generated_orders: tuple[OrderRequest, ...]
    risk_report: RiskReport
    execution_results: tuple[OrderResult, ...]

    @property
    def ready_count(self) -> int:
        return len(self.generated_orders)

    @property
    def approved_count(self) -> int:
        return len(self.risk_report.accepted_orders)

    @property
    def filled_count(self) -> int:
        return sum(
            result.status is OrderStatus.FILLED
            for result in self.execution_results
        )


def execute_approved_orders(
    broker: BrokerAdapter,
    orders: Iterable[OrderRequest],
) -> list[OrderResult]:
    results: list[OrderResult] = []
    for order in orders:
        results.append(broker.submit_order(order))
    return results


def run_direct_pipeline(
    broker: BrokerAdapter,
    candidates: pd.DataFrame,
    sizing_config: PositionSizingConfig,
    risk_config: RiskConfig,
    risk_state: RiskState,
    run_id: str | None = None,
    execute_orders: bool = True,
) -> PipelineResult:
    health = broker.health_check()
    if not health.healthy:
        raise RuntimeError(f"Broker Health異常: {health.message}")

    sizing_decisions = size_candidates(
        broker=broker,
        candidates=candidates,
        config=sizing_config,
    )
    generated_orders = build_order_requests(
        sizing_decisions,
        run_id=run_id,
    )
    risk_report = evaluate_orders(
        broker=broker,
        orders=generated_orders,
        config=risk_config,
        state=risk_state,
    )
    execution_results = (
        execute_approved_orders(
            broker,
            risk_report.accepted_orders,
        )
        if execute_orders
        else []
    )

    return PipelineResult(
        candidate_count=len(candidates),
        sizing_decisions=tuple(sizing_decisions),
        generated_orders=tuple(generated_orders),
        risk_report=risk_report,
        execution_results=tuple(execution_results),
    )


def run_direct_pipeline_from_csv(
    broker: BrokerAdapter,
    candidate_path: Path,
    sizing_config: PositionSizingConfig,
    risk_config: RiskConfig,
    risk_state_path: Path,
    run_id: str | None = None,
    execute_orders: bool = True,
) -> PipelineResult:
    candidates = normalize_candidates(candidate_path)
    snapshot = broker.get_account_snapshot()
    state = load_risk_state(
        risk_state_path,
        snapshot.equity_yen,
    )
    result = run_direct_pipeline(
        broker=broker,
        candidates=candidates,
        sizing_config=sizing_config,
        risk_config=risk_config,
        risk_state=state,
        run_id=run_id,
        execute_orders=execute_orders,
    )
    save_risk_state(risk_state_path, state)
    return result


def save_pipeline_logs(
    result: PipelineResult,
    plan_path: Path,
    risk_path: Path,
    execution_path: Path,
    summary_path: Path,
) -> None:
    for path in (plan_path, risk_path, execution_path, summary_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    decisions_frame(result.sizing_decisions).to_csv(
        plan_path,
        index=False,
        encoding="utf-8-sig",
    )

    risk_rows = [asdict(decision) for decision in result.risk_report.decisions]
    pd.DataFrame(risk_rows).to_csv(
        risk_path,
        index=False,
        encoding="utf-8-sig",
    )

    execution_rows = []
    for execution in result.execution_results:
        row = asdict(execution)
        row["side"] = execution.side.value
        row["status"] = execution.status.value
        row["created_at"] = execution.created_at.isoformat(timespec="seconds")
        execution_rows.append(row)
    pd.DataFrame(execution_rows).to_csv(
        execution_path,
        index=False,
        encoding="utf-8-sig",
    )

    payload = {
        "version": "PHOENIX v7 Step6",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": result.candidate_count,
        "ready_count": result.ready_count,
        "approved_count": result.approved_count,
        "filled_count": result.filled_count,
        "halted": result.risk_report.halted,
        "halt_reason": result.risk_report.halt_reason,
        "final_account": None,
    }
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
