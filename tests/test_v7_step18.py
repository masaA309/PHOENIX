from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import pandas as pd

from phoenix_core.broker import PaperBroker
from phoenix_core.candidate_input_guard import (
    CandidateInputError,
    CandidateInputPolicy,
    load_execution_candidates,
)
from phoenix_core.pipeline import _run_direct_pipeline_from_csv, save_pipeline_logs
from phoenix_core.position_sizer import PositionSizingConfig
from phoenix_core.risk_controller import RiskConfig


def create_directory_alias(alias: Path, target: Path) -> None:
    try:
        alias.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        if os.name != "nt":
            raise
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(alias), str(target)],
        capture_output=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        message = (completed.stderr or completed.stdout).decode(
            errors="replace"
        )
        raise OSError(message)


def remove_directory_alias(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    else:
        os.rmdir(path)


def strict_policy() -> CandidateInputPolicy:
    return CandidateInputPolicy.from_mapping(
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


def candidate_rows() -> list[dict[str, object]]:
    return [
        {
            "ticker": "1111.T",
            "銘柄": "BUY銘柄",
            "基準価格": 500,
            "押し目価格": 490,
            "損切価格": 480,
            "PHOENIX_SCORE": 90,
            "Trade判定": "BUY",
        },
        {
            "ticker": "2222.T",
            "銘柄": "WATCH銘柄",
            "基準価格": 400,
            "押し目価格": 390,
            "損切価格": 380,
            "PHOENIX_SCORE": 99,
            "Trade判定": "WATCH",
        },
        {
            "ticker": "3333.T",
            "銘柄": "SKIP銘柄",
            "基準価格": 300,
            "押し目価格": 290,
            "損切価格": 280,
            "PHOENIX_SCORE": 100,
            "Trade判定": "SKIP",
        },
    ]


class CandidateExecutionContractStep18Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "reports").mkdir()
        (self.root / "state").mkdir()
        self.path = self.root / "reports/trade_signals.csv"
        self.policy = strict_policy()
        self.write_rows(candidate_rows())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_rows(self, rows: list[dict[str, object]]) -> None:
        pd.DataFrame(rows).to_csv(self.path, index=False, encoding="utf-8-sig")

    def test_only_buy_rows_are_eligible(self) -> None:
        batch = load_execution_candidates(
            self.path, self.policy, repository_root=self.root
        )
        self.assertEqual(["1111.T"], batch.candidates["ticker"].tolist())
        self.assertEqual([490.0], batch.candidates["エントリー価格"].tolist())
        self.assertEqual(3, batch.audit.input_rows)
        self.assertEqual(1, batch.audit.eligible_rows)
        self.assertEqual({"WATCH": 1, "SKIP": 1}, dict(batch.audit.rejection_counts))
        self.assertEqual(64, len(batch.audit.input_sha256))
        self.assertEqual(
            hashlib.sha256(self.path.read_bytes()).hexdigest(),
            batch.audit.input_sha256,
        )
        self.assertEqual(64, len(batch.audit.eligible_candidates_sha256))

    def test_all_skip_rows_produce_zero_orders(self) -> None:
        rows = candidate_rows()
        for row in rows:
            row["Trade判定"] = "SKIP"
        self.write_rows(rows)
        result = _run_direct_pipeline_from_csv(
            broker=PaperBroker(initial_cash_yen=10_000_000),
            candidate_path=self.path,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(),
            risk_state_path=self.root / "state/risk.json",
            candidate_policy=self.policy,
            repository_root=self.root,
            execute_orders=False,
        )
        self.assertEqual(3, result.candidate_count)
        self.assertEqual(0, result.eligible_candidate_count)
        self.assertEqual(0, result.ready_count)
        self.assertEqual(0, result.approved_count)

    def test_high_cash_cannot_promote_watch_or_skip(self) -> None:
        result = _run_direct_pipeline_from_csv(
            broker=PaperBroker(initial_cash_yen=10_000_000),
            candidate_path=self.path,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(),
            risk_state_path=self.root / "state/risk.json",
            candidate_policy=self.policy,
            repository_root=self.root,
            execute_orders=False,
        )
        self.assertEqual({"1111.T"}, {order.ticker for order in result.generated_orders})
        self.assertEqual(1, result.eligible_candidate_count)
        self.assertEqual(3, result.candidate_count)
        self.assertFalse((self.root / "state/risk.json").exists())

    def test_unknown_decision_fails_closed_without_state_change(self) -> None:
        rows = candidate_rows()
        rows[0]["Trade判定"] = "STRONG_BUY"
        self.write_rows(rows)
        broker = PaperBroker(initial_cash_yen=300_000)
        before = broker.get_account_snapshot()
        risk_state = self.root / "state/risk.json"
        with self.assertRaises(CandidateInputError):
            _run_direct_pipeline_from_csv(
                broker=broker,
                candidate_path=self.path,
                sizing_config=PositionSizingConfig(),
                risk_config=RiskConfig(),
                risk_state_path=risk_state,
                candidate_policy=self.policy,
                repository_root=self.root,
                execute_orders=True,
            )
        after = broker.get_account_snapshot()
        self.assertEqual(before.cash_yen, after.cash_yen)
        self.assertEqual(before.positions, after.positions)
        self.assertFalse(risk_state.exists())

    def test_missing_decision_column_fails_closed(self) -> None:
        rows = candidate_rows()
        for row in rows:
            row.pop("Trade判定")
        self.write_rows(rows)
        with self.assertRaisesRegex(CandidateInputError, "Trade判定"):
            load_execution_candidates(
                self.path, self.policy, repository_root=self.root
            )

    def test_duplicate_ticker_fails_closed(self) -> None:
        rows = candidate_rows()
        rows[1]["ticker"] = "1111.t"
        self.write_rows(rows)
        with self.assertRaisesRegex(CandidateInputError, "Duplicate"):
            load_execution_candidates(
                self.path, self.policy, repository_root=self.root
            )

    def test_invalid_price_on_skip_row_still_fails_closed(self) -> None:
        rows = candidate_rows()
        rows[2]["押し目価格"] = -1
        self.write_rows(rows)
        with self.assertRaisesRegex(CandidateInputError, "positive execution price"):
            load_execution_candidates(
                self.path, self.policy, repository_root=self.root
            )

    def test_infinite_price_on_non_buy_row_fails_closed(self) -> None:
        rows = candidate_rows()
        rows[1]["押し目価格"] = float("inf")
        self.write_rows(rows)
        with self.assertRaisesRegex(CandidateInputError, "finite positive"):
            load_execution_candidates(
                self.path, self.policy, repository_root=self.root
            )

    def test_invalid_tse_ticker_fails_closed(self) -> None:
        for ticker in ("EVIL", "1AAA.T", "0ZZZ.T", "1B0A.T"):
            with self.subTest(ticker=ticker):
                rows = candidate_rows()
                rows[0]["ticker"] = ticker
                self.write_rows(rows)
                with self.assertRaisesRegex(CandidateInputError, "TSE code"):
                    load_execution_candidates(
                        self.path, self.policy, repository_root=self.root
                    )

    def test_ragged_csv_row_fails_closed(self) -> None:
        self.path.write_text(
            "ticker,銘柄,押し目価格,損切価格,PHOENIX_SCORE,Trade判定\n"
            "1111.T,銘柄,490,480,90,BUY,EXTRA\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(CandidateInputError, "fields"):
            load_execution_candidates(
                self.path, self.policy, repository_root=self.root
            )

    def test_same_named_file_outside_repository_is_rejected(self) -> None:
        other_root = self.root / "other"
        other_path = other_root / "reports/trade_signals.csv"
        other_path.parent.mkdir(parents=True)
        pd.DataFrame(candidate_rows()).to_csv(other_path, index=False)
        with self.assertRaisesRegex(CandidateInputError, "configured execution source"):
            load_execution_candidates(
                other_path, self.policy, repository_root=self.root
            )

    def test_hard_link_candidate_alias_is_rejected_without_skip(self) -> None:
        target = self.root / "trade_signals_target.csv"
        self.path.replace(target)
        os.link(target, self.path)
        with self.assertRaisesRegex(CandidateInputError, "hard-link alias"):
            load_execution_candidates(
                self.path, self.policy, repository_root=self.root
            )

    def test_directory_reparse_alias_is_rejected_without_skip(self) -> None:
        target = self.root / "reports_target"
        self.path.parent.replace(target)
        create_directory_alias(self.root / "reports", target)
        try:
            with self.assertRaisesRegex(CandidateInputError, "reparse alias"):
                load_execution_candidates(
                    self.root / "reports/trade_signals.csv",
                    self.policy,
                    repository_root=self.root,
                )
        finally:
            remove_directory_alias(self.root / "reports")
            target.replace(self.root / "reports")

    def test_missing_canonical_file_does_not_fallback(self) -> None:
        self.path.unlink()
        pd.DataFrame(candidate_rows()).to_csv(
            self.root / "reports/portfolio_plan.csv", index=False
        )
        with self.assertRaises(FileNotFoundError):
            load_execution_candidates(
                self.path, self.policy, repository_root=self.root
            )

    def test_policy_cannot_be_disabled_or_widened(self) -> None:
        base = {
            "enabled": True,
            "path": "reports/trade_signals.csv",
            "decision_column": "Trade判定",
            "execution_price_column": "押し目価格",
            "executable_values": ["BUY"],
            "known_values": ["BUY", "WATCH", "SKIP"],
            "fallback": False,
        }
        for update in (
            {"enabled": False},
            {"fallback": True},
            {"executable_values": ["BUY", "WATCH"]},
            {"path": "reports/portfolio_plan.csv"},
            {"execution_price_column": "基準価格"},
        ):
            with self.subTest(update=update):
                with self.assertRaises(CandidateInputError):
                    CandidateInputPolicy.from_mapping({**base, **update})

    def test_summary_binds_guard_counts_and_hash(self) -> None:
        result = _run_direct_pipeline_from_csv(
            broker=PaperBroker(initial_cash_yen=10_000_000),
            candidate_path=self.path,
            sizing_config=PositionSizingConfig(),
            risk_config=RiskConfig(),
            risk_state_path=self.root / "state/risk.json",
            candidate_policy=self.policy,
            repository_root=self.root,
            execute_orders=False,
        )
        summary = self.root / "reports/summary.json"
        save_pipeline_logs(
            result,
            self.root / "reports/position.csv",
            self.root / "reports/risk.csv",
            self.root / "reports/execution.csv",
            summary,
        )
        payload = json.loads(summary.read_text(encoding="utf-8"))
        self.assertEqual("READY", payload["candidate_input_guard"]["status"])
        self.assertEqual(3, payload["candidate_count"])
        self.assertEqual(1, payload["eligible_candidate_count"])
        self.assertEqual(64, len(payload["candidate_input_guard"]["input_sha256"]))


if __name__ == "__main__":
    unittest.main()
