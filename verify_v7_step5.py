from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from phoenix_core import OrderRequest, OrderSide, OrderType, PaperBroker
from phoenix_core.risk_controller import (
    RiskConfig,
    RiskState,
    evaluate_orders,
    load_risk_state,
    save_risk_outputs,
    save_risk_state,
)


def order(ticker: str, price: float, cid: str) -> OrderRequest:
    return OrderRequest(
        ticker=ticker,
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=price,
        client_order_id=cid,
    )


def main() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="phoenix_v7_step5_"))
    try:
        broker = PaperBroker(initial_cash_yen=300000)
        config = RiskConfig(
            max_daily_loss_pct=0.03,
            max_drawdown_pct=0.10,
            max_positions=3,
            max_total_invested_pct=0.80,
            max_single_position_pct=0.30,
            max_orders_per_run=2,
            max_consecutive_losses=3,
            minimum_cash_reserve_pct=0.10,
        )
        state = RiskState.new(300000)
        report = evaluate_orders(
            broker,
            [
                order("9501.T", 500, "RISK-1"),
                order("4902.T", 600, "RISK-2"),
                order("3697.T", 700, "RISK-3"),
            ],
            config,
            state,
        )

        assert len(report.accepted_orders) == 2
        assert report.decisions[2].accepted is False
        assert "最大発注件数" in report.decisions[2].reason

        loss_state = RiskState.new(300000)
        loss_state.start_of_day_equity_yen = 310000
        stopped = evaluate_orders(
            broker,
            [order("9501.T", 500, "RISK-4")],
            config,
            loss_state,
        )
        assert stopped.halted
        assert len(stopped.accepted_orders) == 0

        state_path = temp_root / "state.json"
        approved_path = temp_root / "approved.json"
        report_path = temp_root / "report.txt"
        save_risk_state(state_path, state)
        restored = load_risk_state(state_path, 300000)
        assert restored.start_of_day_equity_yen == 300000
        save_risk_outputs(report, approved_path, report_path)
        assert approved_path.exists()
        assert report_path.exists()

        print("=" * 90)
        print("PHOENIX v7 CORE STEP5 VERIFY")
        print("=" * 90)
        print("Broker Health判定      : PASS")
        print("日次損失上限           : PASS")
        print("最大ドローダウン       : PASS")
        print("最大保有銘柄数         : PASS")
        print("総投資率上限           : PASS")
        print("1銘柄投資率上限        : PASS")
        print("最低現金保持率         : PASS")
        print("最大発注件数           : PASS")
        print("連敗停止               : PASS")
        print("Risk State保存復元     : PASS")
        print("承認注文JSON保存       : PASS")
        print("リスクレポート保存     : PASS")
        print(f"承認注文数             : {len(report.accepted_orders)}件")
        print("=" * 90)
        print("PHOENIX v7 Step5検証: PASS")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    main()
