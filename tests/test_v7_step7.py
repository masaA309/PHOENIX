from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from phoenix_core.run_guard import (
    RunPolicy,
    SingleInstanceLock,
    load_state,
    save_state,
    should_run,
)


class SchedulerStep7Test(unittest.TestCase):
    def test_weekday_allowed(self) -> None:
        policy = RunPolicy()
        allowed, _ = should_run(policy, {}, datetime(2026, 7, 20, 8, 30))
        self.assertTrue(allowed)

    def test_weekend_skipped(self) -> None:
        policy = RunPolicy()
        allowed, _ = should_run(policy, {}, datetime(2026, 7, 19, 8, 30))
        self.assertFalse(allowed)

    def test_once_per_day(self) -> None:
        policy = RunPolicy()
        state = {"last_success_date": "2026-07-20"}
        allowed, _ = should_run(policy, state, datetime(2026, 7, 20, 9, 0))
        self.assertFalse(allowed)

    def test_lock_prevents_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner.lock"
            first = SingleInstanceLock(path)
            second = SingleInstanceLock(path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_atomic_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            save_state(path, {"last_success_date": "2026-07-20"})
            self.assertEqual(load_state(path)["last_success_date"], "2026-07-20")


if __name__ == "__main__":
    unittest.main()
