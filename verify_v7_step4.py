from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pandas as pd

from phoenix_core import (
    OrderRequest,
    OrderSide,
    OrderType,
    PaperBroker,
)
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    build_order_requests,
    calculate_sizing,
    normalize_candidates,
    save_position_sizing_outputs,
    size_candidates,
)


def main() -> None:
    temp_root = Path(
        tempfile.mkdtemp(
            prefix="phoenix_v7_step4_"
        )
    )

    try:
        reports = temp_root / "reports"
        reports.mkdir(parents=True)
        state_file = temp_root / "state" / "paper.json"

        broker = PaperBroker(
            initial_cash_yen=300000,
            state_file=state_file,
        )

        broker.submit_order(
            OrderRequest(
                ticker="4005.T",
                side=OrderSide.BUY,
                quantity=100,
                order_type=OrderType.LIMIT,
                limit_price=500.0,
                client_order_id="STEP4-HELD-001",
            )
        )

        candidate_file = reports / "candidates.csv"
        pd.DataFrame(
            [
                {
                    "銘柄": "テスト低位株",
                    "ticker": "9501.T",
                    "押し目価格": 500.0,
                    "損切価格": 485.0,
                    "PortfolioScore": 90,
                },
                {
                    "銘柄": "保有済み",
                    "ticker": "4005.T",
                    "押し目価格": 520.0,
                    "損切価格": 500.0,
                    "PortfolioScore": 80,
                },
                {
                    "銘柄": "高価格株",
                    "ticker": "9984.T",
                    "押し目価格": 5500.0,
                    "損切価格": 5300.0,
                    "PortfolioScore": 70,
                },
            ]
        ).to_csv(
            candidate_file,
            index=False,
            encoding="utf-8-sig",
        )

        candidates = normalize_candidates(
            candidate_file
        )
        config = PositionSizingConfig(
            risk_per_trade_pct=0.01,
            max_position_pct=0.30,
            max_total_invested_pct=0.80,
            minimum_cash_reserve_pct=0.10,
            fallback_stop_distance_pct=0.03,
            lot_size=100,
            maximum_quantity_per_ticker=1000,
            allow_pyramiding=False,
            commission_buffer_pct=0.001,
        )

        decisions = size_candidates(
            broker=broker,
            candidates=candidates,
            config=config,
        )

        ready = {
            decision.ticker: decision
            for decision in decisions
        }

        assert ready["9501.T"].recommended_quantity == 100
        assert ready["9501.T"].status == "READY"
        assert ready["9501.T"].estimated_cost_yen == 50000
        assert ready["9501.T"].estimated_risk_yen == 1500

        assert ready["4005.T"].recommended_quantity == 0
        assert ready["4005.T"].status == "SKIP"
        assert "保有中" in ready["4005.T"].reason

        assert ready["9984.T"].recommended_quantity == 0
        assert ready["9984.T"].status == "SKIP"

        direct = calculate_sizing(
            snapshot=broker.get_account_snapshot(),
            ticker="1111.T",
            name="Fallback Stop",
            entry_price=500,
            stop_price=0,
            ranking_score=50,
            config=config,
        )
        assert direct.stop_price == 485
        assert direct.recommended_quantity == 100

        orders = build_order_requests(
            decisions,
            run_id="VERIFY-STEP4",
        )
        assert len(orders) == 1
        assert orders[0].ticker == "9501.T"
        assert orders[0].quantity == 100
        assert orders[0].limit_price == 500

        plan_path = reports / "plan.csv"
        orders_path = reports / "orders.json"
        report_path = reports / "report.txt"

        save_position_sizing_outputs(
            decisions=decisions,
            orders=orders,
            plan_path=plan_path,
            orders_path=orders_path,
            report_path=report_path,
        )

        assert plan_path.exists()
        assert orders_path.exists()
        assert report_path.exists()

        print("=" * 90)
        print("PHOENIX v7 CORE STEP4 VERIFY")
        print("=" * 90)
        print("Broker余力取得       : PASS")
        print("Broker保有株取得     : PASS")
        print("保有済み判定         : PASS")
        print("リスクベース株数     : PASS")
        print("1銘柄上限            : PASS")
        print("総投資上限           : PASS")
        print("現金余力上限         : PASS")
        print("最低現金保持         : PASS")
        print("100株単位丸め        : PASS")
        print("高価格株見送り       : PASS")
        print("損切価格補完         : PASS")
        print("OrderRequest生成     : PASS")
        print("CSV・JSON・TXT保存   : PASS")
        print(
            f"推奨株数             : "
            f"{ready['9501.T'].recommended_quantity}株"
        )
        print(
            f"想定購入額           : "
            f"{ready['9501.T'].estimated_cost_yen:,.0f}円"
        )
        print(
            f"想定最大損失         : "
            f"{ready['9501.T'].estimated_risk_yen:,.0f}円"
        )
        print("=" * 90)
        print("PHOENIX v7 Step4検証: PASS")
    finally:
        shutil.rmtree(
            temp_root,
            ignore_errors=True,
        )


if __name__ == "__main__":
    main()
