from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest import mock

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

    def test_lock_file_is_removed_when_pid_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner.lock"
            lock = SingleInstanceLock(path)
            with mock.patch("phoenix_core.run_guard.os.write", side_effect=OSError("fail")):
                with self.assertRaises(OSError):
                    lock.acquire()
            self.assertFalse(path.exists())
            self.assertIsNone(lock._fd)

    def test_atomic_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            save_state(path, {"last_success_date": "2026-07-20"})
            self.assertEqual(load_state(path)["last_success_date"], "2026-07-20")

    def test_corrupt_scheduler_state_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            path.write_text("broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_state(path)


if __name__ == "__main__":
    unittest.main()
