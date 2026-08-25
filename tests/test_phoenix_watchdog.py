from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import threading
import time
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from phoenix_watchdog import (
    AlreadyRunningError,
    EventLogger,
    EXIT_OK,
    EXIT_CONFIGURATION_ERROR,
    EXIT_HEARTBEAT_FAILURE,
    EXIT_RESTART_LIMIT,
    MonitorConfig,
    PhoenixWatchdog,
    ProcessLock,
)
from phoenix_core import RakutenRssTransportHealth


class _FakeFileReadyTransport:
    def __init__(self, *, connected: bool = True, message: str = "FILE_READY_OK") -> None:
        self.connected = connected
        self.message = message
        self.calls = 0

    def publish_file_ready_heartbeat(self) -> RakutenRssTransportHealth:
        self.calls += 1
        return RakutenRssTransportHealth(
            connected=self.connected,
            message=self.message,
            transport_source="COM_LIVE" if self.connected else "DISCONNECTED",
        )


class _FakeChildProcess:
    def __init__(self, pid: int, returncode: int | None = None) -> None:
        self.pid = pid
        self._returncode = returncode

    def poll(self) -> int | None:
        return self._returncode


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

    def write_step44_summary(
        self,
        recorded_at: str,
        *,
        result: str = "READY",
    ) -> Path:
        path = self.root / "reports" / "v7_vba_bridge_step44_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": "summary",
            "recorded_at": recorded_at,
            "intent_id": "",
            "idempotency_key": "",
            "source_checksum": "",
            "result": result,
            "reason_codes": "",
            "source_file": "",
            "receipt_file": "",
            "outbox_file": "",
            "reader_id": "PHOENIX_STEP44_VBA_LOCAL_RECEIVER",
            "orders_submitted": "0",
            "note": "accepted=0;rejected=0;duplicate=0;expired=0;corrupt=0",
            "current_stage": "",
            "current_file": "",
            "error_number": "",
            "error_source": "",
            "error_description": "",
            "error_line": "",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def make_watchdog(
        self,
        target: Path,
        *,
        max_restarts: int = 0,
        startup_grace_seconds: float = 0.01,
        enable_file_ready_heartbeat: bool = False,
        file_ready_transport: object | None = None,
        file_ready_heartbeat_seconds: float = 0.01,
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
            enable_file_ready_heartbeat=enable_file_ready_heartbeat,
            file_ready_transport=file_ready_transport,
            file_ready_heartbeat_seconds=file_ready_heartbeat_seconds,
        )

    def read_events(self) -> list[dict[str, object]]:
        files = list(self.log_dir.glob("phoenix_watchdog_*.jsonl"))
        self.assertEqual(1, len(files))
        return [
            json.loads(line)
            for line in files[0].read_text(encoding="utf-8").splitlines()
        ]

    def wait_for_event(
        self,
        event_name: str,
        *,
        timeout: float = 3.0,
    ) -> list[dict[str, object]]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            files = list(self.log_dir.glob("phoenix_watchdog_*.jsonl"))
            if files:
                events = self.read_events()
                if any(event["event"] == event_name for event in events):
                    return events
            time.sleep(0.01)
        self.fail(f"timed out waiting for {event_name}")

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
        results: list[int] = []
        thread = threading.Thread(target=lambda: results.append(watchdog.run()))
        thread.start()

        events = self.wait_for_event("PROCESS_IDLE")
        self.assertIsNone(watchdog.child_pid)
        self.assertTrue(thread.is_alive())

        watchdog.request_stop("unit_test")
        thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual([EXIT_OK], results)

        names = [event["event"] for event in events]
        self.assertIn("PROCESS_LAUNCHED", names)
        self.assertIn("PROCESS_STARTED", names)
        self.assertIn("PROCESS_EXITED", names)
        self.assertIn("PROCESS_IDLE", names)
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

    def test_stale_run_phoenix_heartbeat_is_cleared_before_launch(self) -> None:
        heartbeat_path = self.root / "runtime" / "guardian" / "heartbeat.json"
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        stale_payload = {
            "schema_version": 1,
            "timestamp": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
            "started_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
            "status": "RUNNING",
            "mode": "PAPER",
            "pid": 999_999_999,
            "process_name": "run_phoenix.py",
            "repository_root": str(self.root.resolve()),
            "git_commit": "b1e5a4c",
            "guardian_status": "READY",
            "position_reconciliation_status": "READY",
            "current_stage": "TEST",
            "sequence": 1,
            "orders_submitted": 0,
        }
        heartbeat_path.write_text(json.dumps(stale_payload), encoding="utf-8")

        target = self.write_script(
            "run_phoenix.py",
            """
from pathlib import Path
import sys

heartbeat = Path("runtime/guardian/heartbeat.json")
sys.exit(0 if not heartbeat.exists() else 11)
""".strip()
            + "\n",
        )
        watchdog = self.make_watchdog(target)
        results: list[int] = []
        thread = threading.Thread(target=lambda: results.append(watchdog.run()))
        thread.start()

        events = self.wait_for_event("PROCESS_IDLE")
        self.assertIsNone(watchdog.child_pid)
        self.assertTrue(thread.is_alive())

        watchdog.request_stop("unit_test")
        thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual([EXIT_OK], results)
        self.assertFalse(heartbeat_path.exists())

        names = [event["event"] for event in events]
        self.assertIn("HEARTBEAT_STALE_CLEARED", names)
        self.assertIn("PROCESS_EXITED", names)
        self.assertIn("PROCESS_IDLE", names)

    def test_existing_run_phoenix_heartbeat_owner_blocks_new_launch(self) -> None:
        heartbeat_path = self.root / "runtime" / "guardian" / "heartbeat.json"
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        heartbeat_payload = {
            "schema_version": 1,
            "timestamp": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
            "started_at": datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds"),
            "status": "RUNNING",
            "mode": "PAPER",
            "pid": os.getpid(),
            "process_name": "run_phoenix.py",
            "repository_root": str(self.root.resolve()),
            "git_commit": "b1e5a4c",
            "guardian_status": "READY",
            "position_reconciliation_status": "READY",
            "current_stage": "TEST",
            "sequence": 1,
            "orders_submitted": 0,
        }
        heartbeat_path.write_text(json.dumps(heartbeat_payload), encoding="utf-8")

        target = self.write_script("run_phoenix.py", "pass\n")
        watchdog = self.make_watchdog(target)

        with mock.patch("phoenix_watchdog.subprocess.Popen") as popen:
            self.assertEqual(EXIT_HEARTBEAT_FAILURE, watchdog.run())

        popen.assert_not_called()
        self.assertTrue(heartbeat_path.exists())
        names = [event["event"] for event in self.read_events()]
        self.assertIn("HEARTBEAT_OWNER_ACTIVE", names)
        self.assertNotIn("PROCESS_LAUNCHED", names)

    def test_file_ready_heartbeat_publishes_only_for_fresh_step44_ready(self) -> None:
        target = self.write_script("heartbeat_owner.py", "pass\n")
        transport = _FakeFileReadyTransport()
        watchdog = self.make_watchdog(
            target,
            enable_file_ready_heartbeat=True,
            file_ready_transport=transport,
            file_ready_heartbeat_seconds=0.01,
        )
        now = datetime.now(ZoneInfo("Asia/Tokyo"))
        watchdog._process = None
        watchdog._file_ready_publish_ready.clear()

        self.write_step44_summary(now.isoformat(timespec="seconds"))
        self.assertTrue(watchdog._publish_file_ready_heartbeat_once())
        self.assertEqual(1, transport.calls)

        watchdog._process = _FakeChildProcess(pid=1234, returncode=7)
        self.write_step44_summary(now.isoformat(timespec="seconds"))
        self.assertTrue(watchdog._publish_file_ready_heartbeat_once())
        self.assertEqual(2, transport.calls)

        future = now + timedelta(seconds=120)
        self.write_step44_summary(future.isoformat(timespec="seconds"))
        self.assertFalse(watchdog._publish_file_ready_heartbeat_once())
        self.assertEqual(2, transport.calls)

        stale = now - timedelta(seconds=120)
        self.write_step44_summary(stale.isoformat(timespec="seconds"))
        self.assertFalse(watchdog._publish_file_ready_heartbeat_once())
        self.assertEqual(2, transport.calls)

        transport.connected = False
        self.write_step44_summary(now.isoformat(timespec="seconds"))
        self.assertFalse(watchdog._publish_file_ready_heartbeat_once())
        self.assertEqual(3, transport.calls)

    def test_file_ready_heartbeat_continues_while_child_is_idle_and_stops_after_watchdog_stop(self) -> None:
        target = self.write_script(
            "heartbeat_idle_child.py",
            "import time\ntime.sleep(0.08)\n",
        )
        transport = _FakeFileReadyTransport()
        now = datetime.now(ZoneInfo("Asia/Tokyo"))
        self.write_step44_summary(now.isoformat(timespec="seconds"))
        watchdog = self.make_watchdog(
            target,
            enable_file_ready_heartbeat=True,
            file_ready_transport=transport,
            file_ready_heartbeat_seconds=0.01,
        )
        results: list[int] = []
        healthy_heartbeat = mock.Mock()
        healthy_heartbeat.healthy = True
        healthy_heartbeat.sequence = 1
        healthy_heartbeat.timestamp = now
        healthy_heartbeat.reason = "UNIT_TEST"
        healthy_heartbeat.pid = 1234
        healthy_heartbeat.heartbeat_age_seconds = 0.0
        healthy_heartbeat.mode = "PAPER"
        healthy_heartbeat.orders_submitted = 0
        healthy_heartbeat.repository_root = str(self.root)

        with mock.patch(
            "phoenix_watchdog.inspect_heartbeat",
            return_value=healthy_heartbeat,
        ):
            thread = threading.Thread(target=lambda: results.append(watchdog.run()))
            thread.start()

            events = self.wait_for_event("PROCESS_IDLE")
            self.assertIsNone(watchdog.child_pid)
            self.assertTrue(thread.is_alive())

            calls_at_idle = transport.calls
            deadline = time.monotonic() + 3.0
            while transport.calls == calls_at_idle and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertGreater(transport.calls, calls_at_idle)

            watchdog.request_stop("unit_test")
            thread.join(timeout=5.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual([EXIT_OK], results)
        count_after_stop = transport.calls
        time.sleep(0.05)
        self.assertEqual(count_after_stop, transport.calls)
        self.assertIn("PROCESS_IDLE", [event["event"] for event in events])

    def test_repository_guardian_block_fails_closed_while_file_ready_monitoring_continues(self) -> None:
        counter_file = self.root / "launch_count.txt"
        target = self.write_script(
            "guardian_blocked_child.py",
            f"""
import time
from pathlib import Path
import sys

counter = Path({str(counter_file)!r})
count = int(counter.read_text(encoding="utf-8")) if counter.exists() else 0
counter.write_text(str(count + 1), encoding="utf-8")
time.sleep(0.05)
sys.exit(2)
""".strip()
            + "\n",
        )
        transport = _FakeFileReadyTransport()
        now = datetime.now(ZoneInfo("Asia/Tokyo"))
        self.write_step44_summary(now.isoformat(timespec="seconds"))
        watchdog = self.make_watchdog(
            target,
            max_restarts=3,
            startup_grace_seconds=0.0,
            enable_file_ready_heartbeat=True,
            file_ready_transport=transport,
            file_ready_heartbeat_seconds=0.01,
        )

        self.assertEqual(EXIT_CONFIGURATION_ERROR, watchdog.run())
        self.assertTrue(counter_file.exists())
        self.assertEqual(1, int(counter_file.read_text(encoding="utf-8")))
        self.assertGreaterEqual(transport.calls, 1)

        events = self.read_events()
        names = [event["event"] for event in events]
        blocked_events = [
            event for event in events if event["event"] == "REPOSITORY_GUARDIAN_BLOCKED"
        ]
        self.assertEqual(1, len(blocked_events))
        self.assertIn("REPOSITORY_GUARDIAN_BLOCKED", names)
        self.assertIn("FILE_READY_HEARTBEAT_PUBLISHED", names)
        self.assertNotIn("PROCESS_IDLE", names)
        self.assertNotIn("RESTART_SCHEDULED", names)
        self.assertNotIn("RESTART_LIMIT_REACHED", names)
        self.assertTrue(all(event["restart_suppressed"] is True for event in blocked_events))
        self.assertTrue(all(event["backoff_seconds"] == 0.0 for event in blocked_events))
        calls_after_run = transport.calls
        time.sleep(0.05)
        self.assertEqual(calls_after_run, transport.calls)


if __name__ == "__main__":
    unittest.main()
