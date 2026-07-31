from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pandas as pd

from phoenix_core import PaperBroker
from phoenix_core.candidate_input_guard import CandidateInputPolicy
from phoenix_core.pipeline import (
    _run_direct_pipeline_from_csv,
    run_direct_pipeline,
)
from phoenix_core.position_sizer import PositionSizingConfig
from phoenix_core.risk_controller import RiskConfig, RiskState


def main() -> None:
    temp = Path(tempfile.mkdtemp(prefix="phoenix_step6_"))
    try:
        (temp / "reports").mkdir()
        (temp / "state").mkdir()
        candidates = pd.DataFrame(
            [
                {
                    "ticker": "9501.T",
                    "銘柄": "東京電力HD",
                    "押し目価格": 500,
                    "損切価格": 485,
                    "ランキング点": 90,
                    "Trade判定": "BUY",
                },
                {
                    "ticker": "4902.T",
                    "銘柄": "コニカミノルタ",
                    "押し目価格": 600,
                    "損切価格": 582,
                    "ランキング点": 80,
                    "Trade判定": "BUY",
                },
            ]
        )
        candidate_path = temp / "reports/trade_signals.csv"
        candidates.to_csv(candidate_path, index=False, encoding="utf-8-sig")
        policy = CandidateInputPolicy.from_mapping(
            {
                "enabled": True,
                "path": "reports/trade_signals.csv",
                "decision_column": "Trade判定",
                "execution_price_column": "押し目価格",
                "executable_values": ["BUY"],
                "known_values": ["BUY", "WATCH", "SKIP"],
                "fallback": False,
            }
        )
        broker = PaperBroker(
            initial_cash_yen=300000,
            state_file=temp / "state/broker.json",
        )
        result = _run_direct_pipeline_from_csv(
            broker=broker,
            candidate_path=candidate_path,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(max_orders_per_run=2),
            risk_state_path=temp / "state/risk.json",
            candidate_policy=policy,
            repository_root=temp,
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
            candidates=candidates.rename(columns={"押し目価格": "エントリー価格"}),
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(max_orders_per_run=2),
            risk_state=RiskState.new(300000),
            run_id="STEP6-DRY",
            execute_orders=False,
        )
        assert dry.approved_count == 2
        assert dry.filled_count == 0
        assert len(dry_broker.get_account_snapshot().positions) == 0
        try:
            run_direct_pipeline(
                broker=dry_broker,
                candidates=candidates.rename(
                    columns={"押し目価格": "エントリー価格"}
                ),
                sizing_config=PositionSizingConfig(),
                risk_config=RiskConfig(),
                risk_state=RiskState.new(300000),
                execute_orders=True,
            )
        except RuntimeError as error:
            assert "Direct order execution is forbidden" in str(error)
        else:
            raise AssertionError("Public direct execution was not rejected")

        print("=" * 90)
        print("PHOENIX v7 CORE STEP6 VERIFY")
        print("=" * 90)
        print("Canonical CSV guard      : PASS")
        print("Position Sizer直接接続 : PASS")
        print("Risk Controller直接接続: PASS")
        print("Execution Engine直接接続: PASS")
        print("Paper Broker約定        : PASS")
        print("公開Direct API発注不可 : PASS")
        print("Dry Run                  : PASS")
        print(f"約定件数                 : {result.filled_count}件")
        print("=" * 90)
        print("PHOENIX v7 Step6検証: PASS")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    main()
