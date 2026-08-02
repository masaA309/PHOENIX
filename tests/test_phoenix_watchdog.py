from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from phoenix_watchdog import (
    AlreadyRunningError,
    EventLogger,
    EXIT_OK,
    EXIT_RESTART_LIMIT,
    MonitorConfig,
    PhoenixWatchdog,
    ProcessLock,
)


class PhoenixWatchdogStep36Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.log_dir = self.root / "logs"
        self.lock_file = self.log_dir / "phoenix_watchdog.lock"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_script(self, name: str, source: str) -> Path:
        path = self.root / name
        path.write_text(source, encoding="utf-8")
        return path

    def make_watchdog(
        self,
        target: Path,
        *,
        max_restarts: int = 0,
        startup_grace_seconds: float = 0.01,
    ) -> PhoenixWatchdog:
        config = MonitorConfig(
            max_restarts=max_restarts,
            backoff_base_seconds=0.01,
            backoff_max_seconds=0.02,
            startup_grace_seconds=startup_grace_seconds,
            poll_seconds=0.005,
            termination_grace_seconds=2.0,
            stale_lock_seconds=1.0,
        )
        return PhoenixWatchdog(
            target_script=target,
            root_dir=self.root,
            log_dir=self.log_dir,
            lock_file=self.lock_file,
            config=config,
        )

    def read_events(self) -> list[dict[str, object]]:
        files = list(self.log_dir.glob("phoenix_watchdog_*.jsonl"))
        self.assertEqual(1, len(files))
        return [
            json.loads(line)
            for line in files[0].read_text(encoding="utf-8").splitlines()
        ]

    def test_process_start_confirmation_and_paper_logs(self) -> None:
        target = self.write_script(
            "successful_child.py",
            """
import os
import sys
import time

paper = (
    os.environ.get("PHOENIX_MODE") == "PAPER"
    and os.environ.get("PHOENIX_EXECUTION_MODE") == "PAPER"
    and os.environ.get("PHOENIX_LIVE_TRADING") == "0"
    and os.environ.get("PHOENIX_ALLOW_LIVE_TRADING") == "0"
)
time.sleep(0.08)
sys.exit(0 if paper else 9)
""".strip()
            + "\n",
        )
        watchdog = self.make_watchdog(target)

        self.assertEqual(EXIT_OK, watchdog.run())

        events = self.read_events()
        names = [event["event"] for event in events]
        self.assertIn("PROCESS_LAUNCHED", names)
        self.assertIn("PROCESS_STARTED", names)
        self.assertIn("PROCESS_EXITED", names)
        self.assertTrue(all(event["mode"] == "PAPER" for event in events))
        self.assertTrue(all(event["orders_submitted"] == 0 for event in events))
        text_file = next(self.log_dir.glob("phoenix_watchdog_*.txt"))
        text = text_file.read_text(encoding="utf-8")
        self.assertIn("Mode: PAPER", text)
        self.assertIn("Orders submitted: 0", text)

    def test_abnormal_exit_uses_bounded_exponential_backoff(self) -> None:
        counter_file = self.root / "launch_count.txt"
        target = self.write_script(
            "failing_child.py",
            f"""
from pathlib import Path
import sys

counter = Path({str(counter_file)!r})
count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
counter.write_text(str(count + 1), encoding="utf-8")
sys.exit(7)
""".strip()
            + "\n",
        )
        watchdog = self.make_watchdog(
            target,
            max_restarts=2,
            startup_grace_seconds=0.0,
        )

        self.assertEqual(EXIT_RESTART_LIMIT, watchdog.run())

        self.assertEqual("3", counter_file.read_text(encoding="utf-8"))
        events = self.read_events()
        abnormal = [event for event in events if event["event"] == "ABNORMAL_EXIT"]
        restarts = [
            event for event in events if event["event"] == "RESTART_SCHEDULED"
        ]
        self.assertEqual(3, len(abnormal))
        self.assertEqual([1, 2], [event["restart_number"] for event in restarts])
        self.assertEqual([0.01, 0.02], [event["backoff_seconds"] for event in restarts])
        self.assertEqual("RESTART_LIMIT_REACHED", events[-3]["event"])

    def test_lock_blocks_duplicate_and_recovers_dead_pid(self) -> None:
        logger = EventLogger(self.log_dir)
        first = ProcessLock(self.lock_file, logger, stale_after_seconds=1.0)
        second = ProcessLock(self.lock_file, logger, stale_after_seconds=1.0)
        first.acquire()
        try:
            with self.assertRaises(AlreadyRunningError):
                second.acquire()
        finally:
            first.release()

        self.lock_file.write_text(
            json.dumps({"pid": 999_999_999, "token": "stale"}) + "\n",
            encoding="utf-8",
        )
        recovered = ProcessLock(self.lock_file, logger, stale_after_seconds=1.0)
        recovered.acquire()
        recovered.release()

        names = [event["event"] for event in self.read_events()]
        self.assertIn("ACTIVE_LOCK_DETECTED", names)
        self.assertIn("STALE_LOCK_REMOVED", names)

    def test_stop_request_terminates_child_safely(self) -> None:
        target = self.write_script(
            "long_child.py",
            "import time\ntime.sleep(30)\n",
        )
        watchdog = self.make_watchdog(target)
        results: list[int] = []
        thread = threading.Thread(target=lambda: results.append(watchdog.run()))
        thread.start()
        deadline = time.monotonic() + 3.0
        while watchdog.child_pid is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIsNotNone(watchdog.child_pid)

        watchdog.request_stop("unit_test")
        thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual([EXIT_OK], results)
        self.assertIsNone(watchdog.child_pid)
        names = [event["event"] for event in self.read_events()]
        self.assertIn("PROCESS_TERMINATING", names)
        self.assertIn("PROCESS_STOPPED", names)
        self.assertIn("SAFE_STOP", names)


if __name__ == "__main__":
    unittest.main()
