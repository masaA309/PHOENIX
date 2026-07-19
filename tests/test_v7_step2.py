from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from phoenix_core import (
    PaperBroker,
    execute_events,
    normalize_events,
    normalize_plan,
)


class V7ExecutionTest(unittest.TestCase):
    def test_paper_state_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_file = root / "paper.json"

            broker = PaperBroker(
                initial_cash_yen=300000,
                state_file=state_file,
            )

            events = pd.DataFrame(
                [
                    {
                        "日時": pd.Timestamp("2026-07-20 09:00:00"),
                        "イベント": "ENTRY",
                        "ticker": "9501.T",
                        "現在価格": 500.0,
                    }
                ]
            )
            plan = pd.DataFrame(
                [{"ticker": "9501.T", "株数": 100}]
            )

            results = execute_events(
                broker=broker,
                events=events,
                plan=plan,
                log_path=root / "log.csv",
                default_quantity=100,
                lot_size=100,
            )
            self.assertEqual("FILLED", results[0].status.value)

            restored = PaperBroker(
                initial_cash_yen=300000,
                state_file=state_file,
            )
            snapshot = restored.get_account_snapshot()

            self.assertEqual(250000, snapshot.cash_yen)
            self.assertEqual(1, len(snapshot.positions))
            self.assertEqual(100, snapshot.positions[0].quantity)

    def test_normalizers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events_file = root / "events.csv"
            plan_file = root / "plan.csv"

            pd.DataFrame(
                [
                    {
                        "datetime": "2026-07-20 09:00:00",
                        "event": "ENTRY",
                        "symbol": "9501.T",
                        "price": 500.0,
                    }
                ]
            ).to_csv(events_file, index=False)

            pd.DataFrame(
                [{"symbol": "9501.T", "quantity": 100}]
            ).to_csv(plan_file, index=False)

            events = normalize_events(events_file)
            plan = normalize_plan(plan_file)

            self.assertEqual("9501.T", events.iloc[0]["ticker"])
            self.assertEqual(500.0, events.iloc[0]["現在価格"])
            self.assertEqual(100, plan.iloc[0]["株数"])


if __name__ == "__main__":
    unittest.main()
