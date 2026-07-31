from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from phoenix_core import PaperBroker
from phoenix_core.candidate_input_guard import (
    CandidateInputAudit,
    CandidateInputPolicy,
    candidate_execution_sha256,
)
from phoenix_core.pipeline import (
    _run_direct_pipeline,
    _run_direct_pipeline_from_csv,
    run_direct_pipeline,
)
from phoenix_core.position_sizer import PositionSizingConfig
from phoenix_core.risk_controller import (
    RiskConfig,
    RiskState,
    save_risk_state,
)


class DirectPipelineV7Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "reports").mkdir()
        (self.root / "state").mkdir()
        self.candidate_path = self.root / "reports/trade_signals.csv"
        self.candidates().to_csv(
            self.candidate_path,
            index=False,
            encoding="utf-8-sig",
        )
        self.policy = CandidateInputPolicy.from_mapping(
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

    def tearDown(self) -> None:
        self.temp.cleanup()

    def candidates(self) -> pd.DataFrame:
        return pd.DataFrame(
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

    def test_canonical_csv_execution(self) -> None:
        broker = PaperBroker(
            initial_cash_yen=300000,
            state_file=self.root / "state/paper.json",
        )
        result = _run_direct_pipeline_from_csv(
            broker=broker,
            candidate_path=self.candidate_path,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(max_orders_per_run=2),
            risk_state_path=self.root / "state/risk.json",
            candidate_policy=self.policy,
            repository_root=self.root,
            run_id="UNIT-CANONICAL",
            execute_orders=True,
        )
        self.assertEqual(2, result.filled_count)
        self.assertEqual(2, len(broker.get_account_snapshot().positions))

    def test_dry_run_does_not_trade(self) -> None:
        broker = PaperBroker(
            initial_cash_yen=300000,
            state_file=self.root / "state/paper_halt.json",
        )
        result = run_direct_pipeline(
            broker,
            self.candidates().rename(columns={"押し目価格": "エントリー価格"}),
            PositionSizingConfig(),
            RiskConfig(max_orders_per_run=2),
            RiskState.new(300000),
            run_id="UNIT-DRY",
            execute_orders=False,
        )
        self.assertEqual(2, result.approved_count)
        self.assertEqual(0, result.filled_count)
        self.assertEqual(0, len(broker.get_account_snapshot().positions))

    def test_risk_rejection_prevents_canonical_execution(self) -> None:
        broker = PaperBroker(
            initial_cash_yen=300000,
            state_file=self.root / "state/paper_risk_halt.json",
        )
        state_path = self.root / "state/risk.json"
        state = RiskState.new(300000)
        state.start_of_day_equity_yen = 310000
        save_risk_state(state_path, state)
        result = _run_direct_pipeline_from_csv(
            broker=broker,
            candidate_path=self.candidate_path,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(max_daily_loss_pct=0.03),
            risk_state_path=state_path,
            candidate_policy=self.policy,
            repository_root=self.root,
            run_id="UNIT-HALT",
            execute_orders=True,
        )
        self.assertTrue(result.risk_report.halted)
        self.assertEqual(0, result.filled_count)
        self.assertEqual(0, len(broker.get_account_snapshot().positions))

    def test_public_direct_api_cannot_execute_forged_audit(self) -> None:
        broker = PaperBroker(initial_cash_yen=300000)
        forged = pd.DataFrame(
            [
                {
                    "ticker": "EVIL",
                    "銘柄": "forged",
                    "エントリー価格": 500,
                    "損切価格": 480,
                    "ランキング点": 90,
                    "Trade判定": "BUY",
                }
            ]
        )
        audit = CandidateInputAudit(
            status="READY",
            source_path="C:/substituted/reports/trade_signals.csv",
            input_sha256="a" * 64,
            eligible_candidates_sha256=candidate_execution_sha256(forged),
            input_rows=1,
            eligible_rows=1,
            rejected_rows=0,
            decision_counts=(("BUY", 1), ("WATCH", 0), ("SKIP", 0)),
            rejection_counts=(),
        )
        with self.assertRaisesRegex(RuntimeError, "Direct order execution is forbidden"):
            run_direct_pipeline(
                broker,
                forged,
                PositionSizingConfig(),
                RiskConfig(),
                RiskState.new(300000),
                execute_orders=True,
                candidate_input_audit=audit,
            )
        self.assertEqual(0, len(broker.get_account_snapshot().positions))

    def test_internal_execution_rejects_candidate_tamper(self) -> None:
        candidates = self.candidates().rename(
            columns={"押し目価格": "エントリー価格"}
        )
        audit = CandidateInputAudit(
            status="READY",
            source_path="reports/trade_signals.csv",
            input_sha256="a" * 64,
            eligible_candidates_sha256=candidate_execution_sha256(candidates),
            input_rows=2,
            eligible_rows=2,
            rejected_rows=0,
            decision_counts=(("BUY", 2), ("WATCH", 0), ("SKIP", 0)),
            rejection_counts=(),
        )
        candidates.loc[0, "エントリー価格"] = 501
        broker = PaperBroker(initial_cash_yen=300000)
        with self.assertRaisesRegex(RuntimeError, "does not match"):
            _run_direct_pipeline(
                broker,
                candidates,
                PositionSizingConfig(),
                RiskConfig(),
                RiskState.new(300000),
                execute_orders=True,
                candidate_input_audit=audit,
            )
        self.assertEqual(0, len(broker.get_account_snapshot().positions))


if __name__ == "__main__":
    unittest.main()
