from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from phoenix_core.broker import PaperBroker
from phoenix_core.candidate_input_guard import CandidateInputPolicy
from phoenix_core.dry_run_integrity import (
    build_integrity_report,
    capture_protected_files,
    save_integrity_report,
)
from phoenix_core.pipeline import _run_direct_pipeline_from_csv
from phoenix_core.position_sizer import PositionSizingConfig
from phoenix_core.risk_controller import RiskConfig, load_risk_state


class DryRunIntegrityStep16Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "state").mkdir()
        self.config = {
            "dry_run_integrity": {
                "protected_files": ["state/a.json", "state/missing.json"],
                "report_json": "reports/integrity.json",
                "report_text": "reports/integrity.txt",
            }
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_unchanged_and_missing_files_pass(self) -> None:
        (self.root / "state/a.json").write_text("{}\n", encoding="utf-8")
        before = capture_protected_files(
            self.root,
            self.config["dry_run_integrity"]["protected_files"],
        )
        report = save_integrity_report(self.root, self.config, before)
        self.assertEqual("READY", report["status"])
        self.assertEqual(2, report["unchanged_file_count"])
        self.assertTrue((self.root / "reports/integrity.txt").is_file())

    def test_changed_file_fails(self) -> None:
        path = self.root / "state/a.json"
        path.write_text("before", encoding="utf-8")
        before = capture_protected_files(self.root, ["state/a.json"])
        path.write_text("after", encoding="utf-8")
        after = capture_protected_files(self.root, ["state/a.json"])
        report = build_integrity_report(before, after)
        self.assertEqual("FAILED", report["status"])
        self.assertEqual(1, report["changed_file_count"])

    def test_path_escape_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            capture_protected_files(self.root, ["../outside.json"])

    def test_config_change_during_run_fails_closed(self) -> None:
        before = capture_protected_files(self.root, ["state/a.json"])
        with self.assertRaises(ValueError):
            save_integrity_report(self.root, self.config, before)


class DryRunRiskStateStep16Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "reports").mkdir()
        self.candidates = self.root / "reports/trade_signals.csv"
        pd.DataFrame([
            {
                "ticker": "9501.T",
                "銘柄": "東京電力HD",
                "エントリー価格": 500,
                "押し目価格": 500,
                "損切価格": 485,
                "ランキング点": 90,
                "Trade判定": "BUY",
            }
        ]).to_csv(self.candidates, index=False, encoding="utf-8-sig")
        self.state = self.root / "risk.json"
        self.broker_state = self.root / "broker.json"
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

    def run_pipeline(self, execute_orders: bool) -> None:
        _run_direct_pipeline_from_csv(
            broker=PaperBroker(
                initial_cash_yen=300_000,
                state_file=self.broker_state,
            ),
            candidate_path=self.candidates,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(),
            risk_state_path=self.state,
            candidate_policy=self.policy,
            repository_root=self.root,
            run_id="STEP16-TEST",
            execute_orders=execute_orders,
        )

    def test_dry_run_does_not_create_risk_state(self) -> None:
        self.run_pipeline(False)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.broker_state.exists())

    def test_paper_execution_persists_risk_state_atomically(self) -> None:
        self.run_pipeline(True)
        self.assertTrue(self.state.is_file())
        self.assertIsInstance(json.loads(self.state.read_text(encoding="utf-8")), dict)
        self.assertFalse(self.state.with_suffix(".json.tmp").exists())

    def test_corrupt_risk_state_fails_closed(self) -> None:
        self.state.write_text("broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_risk_state(self.state, 300_000)


if __name__ == "__main__":
    unittest.main()
