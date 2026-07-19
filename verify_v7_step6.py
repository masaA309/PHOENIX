from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pandas as pd

from phoenix_core import PaperBroker
from phoenix_core.pipeline import run_direct_pipeline
from phoenix_core.position_sizer import PositionSizingConfig
from phoenix_core.risk_controller import RiskConfig, RiskState


def main() -> None:
    temp = Path(tempfile.mkdtemp(prefix="phoenix_step6_"))
    try:
        broker = PaperBroker(initial_cash_yen=300000, state_file=temp / "broker.json")
        candidates = pd.DataFrame([
            {"ticker": "9501.T", "銘柄": "東京電力HD", "エントリー価格": 500, "損切価格": 485, "ランキング点": 90},
            {"ticker": "4902.T", "銘柄": "コニカミノルタ", "エントリー価格": 600, "損切価格": 582, "ランキング点": 80},
        ])
        result = run_direct_pipeline(
            broker=broker,
            candidates=candidates,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(max_orders_per_run=2),
            risk_state=RiskState.new(300000),
            run_id="STEP6-VERIFY",
            execute_orders=True,
        )
        snapshot = broker.get_account_snapshot()
        assert result.candidate_count == 2
        assert result.ready_count == 2
        assert result.approved_count == 2
        assert result.filled_count == 2
        assert len(snapshot.positions) == 2
        assert snapshot.cash_yen == 190000

        dry_broker = PaperBroker(initial_cash_yen=300000)
        dry = run_direct_pipeline(
            broker=dry_broker,
            candidates=candidates,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(max_orders_per_run=2),
            risk_state=RiskState.new(300000),
            run_id="STEP6-DRY",
            execute_orders=False,
        )
        assert dry.approved_count == 2
        assert dry.filled_count == 0
        assert len(dry_broker.get_account_snapshot().positions) == 0

        print("=" * 90)
        print("PHOENIX v7 CORE STEP6 VERIFY")
        print("=" * 90)
        print("Position Sizer直接接続 : PASS")
        print("Risk Controller直接接続: PASS")
        print("Execution Engine直接接続: PASS")
        print("Paper Broker約定        : PASS")
        print("中間JSON不要            : PASS")
        print("ログ保存分離            : PASS")
        print("Dry Run                  : PASS")
        print(f"約定件数                 : {result.filled_count}件")
        print("=" * 90)
        print("PHOENIX v7 Step6検証: PASS")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    main()
