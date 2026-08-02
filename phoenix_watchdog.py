from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from types import FrameType
from typing import Any
from uuid import uuid4


ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
TARGET_SCRIPT = ROOT_DIR / "run_phoenix.py"
LOCK_FILE = LOG_DIR / "phoenix_watchdog.lock"

MODE = "PAPER"
ORDERS_SUBMITTED = 0
MAX_RESTARTS_HARD_LIMIT = 10

EXIT_OK = 0
EXIT_RESTART_LIMIT = 1
EXIT_CONFIGURATION_ERROR = 2
EXIT_ALREADY_RUNNING = 3


class WatchdogError(RuntimeError):
    """Base error for fail-safe WatchDog shutdowns."""


class AlreadyRunningError(WatchdogError):
    """Raised when another WatchDog owns the lock."""


class UnsafeLockError(WatchdogError):
    """Raised when a lock cannot safely be classified as stale."""


@dataclass(frozen=True)
class MonitorConfig:
    max_restarts: int = 3
    backoff_base_seconds: float = 5.0
    backoff_max_seconds: float = 60.0
    startup_grace_seconds: float = 2.0
    poll_seconds: float = 1.0
    termination_grace_seconds: float = 10.0
    stale_lock_seconds: float = 6 * 60 * 60

    def __post_init__(self) -> None:
        if not 0 <= self.max_restarts <= MAX_RESTARTS_HARD_LIMIT:
            raise ValueError(
                "max_restarts must be between 0 and "
                f"{MAX_RESTARTS_HARD_LIMIT}"
            )
        if self.backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds must be non-negative")
        if self.backoff_max_seconds < self.backoff_base_seconds:
            raise ValueError(
                "backoff_max_seconds must be greater than or equal to "
                "backoff_base_seconds"
            )
        if self.startup_grace_seconds < 0:
            raise ValueError("startup_grace_seconds must be non-negative")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if self.termination_grace_seconds <= 0:
            raise ValueError("termination_grace_seconds must be positive")
        if self.stale_lock_seconds <= 0:
            raise ValueError("stale_lock_seconds must be positive")

    def backoff_seconds(self, restart_number: int) -> float:
        if restart_number < 1:
            raise ValueError("restart_number must be at least 1")
        return min(
            self.backoff_max_seconds,
            self.backoff_base_seconds * (2 ** (restart_number - 1)),
        )


class EventLogger:
    """Append-only JSON Lines and text logging under PHOENIX/logs."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()

    @property
    def text_path(self) -> Path:
        return self.log_dir / f"phoenix_watchdog_{datetime.now():%Y%m%d}.txt"

    @property
    def json_path(self) -> Path:
        return self.log_dir / f"phoenix_watchdog_{datetime.now():%Y%m%d}.jsonl"

    def emit(self, event: str, **details: Any) -> None:
        now = datetime.now().astimezone()
        payload: dict[str, Any] = {
            "timestamp": now.isoformat(timespec="seconds"),
            "event": event,
            "mode": MODE,
            "orders_submitted": ORDERS_SUBMITTED,
        }
        payload.update(details)
        json_line = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        detail_text = " ".join(
            f"{key}={value}"
            for key, value in sorted(details.items())
        )
        text_line = (
            f"[{now:%Y-%m-%d %H:%M:%S}] {event}"
            + (f" {detail_text}" if detail_text else "")
            + f" | Mode: {MODE} | Orders submitted: {ORDERS_SUBMITTED}"
        )

        with self._write_lock:
            with self.json_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(json_line + "\n")
            with self.text_path.open("a", encoding="utf-8", newline="\n") as file:
                file.write(text_line + "\n")
            print(text_line, flush=True)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False
    return True


class ProcessLock:
    """Atomic PID lock with conservative stale-lock recovery."""

    def __init__(
        self,
        path: Path,
        logger: EventLogger,
        stale_after_seconds: float,
    ) -> None:
        self.path = Path(path)
        self.logger = logger
        self.stale_after_seconds = stale_after_seconds
        self.token = uuid4().hex
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            try:
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
            except FileExistsError:
                if self._remove_if_stale():
                    continue
                raise AlreadyRunningError(
                    f"active WatchDog lock exists: {self.path}"
                )

            try:
                payload = {
                    "pid": os.getpid(),
                    "token": self.token,
                    "created_at": datetime.now().astimezone().isoformat(
                        timespec="seconds"
                    ),
                    "mode": MODE,
                }
                with os.fdopen(
                    descriptor,
                    "w",
                    encoding="utf-8",
                    newline="\n",
                ) as file:
                    json.dump(payload, file, ensure_ascii=False, sort_keys=True)
                    file.write("\n")
                    file.flush()
                    os.fsync(file.fileno())
            except Exception:
                try:
                    self.path.unlink()
                except OSError:
                    pass
                raise

            self.acquired = True
            self.logger.emit("LOCK_ACQUIRED", lock_file=str(self.path))
            return

        raise UnsafeLockError(
            f"lock changed repeatedly; refusing to start: {self.path}"
        )

    def _remove_if_stale(self) -> bool:
        try:
            stat = self.path.stat()
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return True
        except OSError as error:
            raise UnsafeLockError(
                f"cannot inspect existing lock safely: {error}"
            ) from error

        age_seconds = max(0.0, time.time() - stat.st_mtime)
        try:
            payload = json.loads(raw)
            pid = int(payload["pid"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            if age_seconds < self.stale_after_seconds:
                raise UnsafeLockError(
                    "recent lock is unreadable; refusing unsafe removal"
                )
            pid = -1

        if _pid_is_alive(pid):
            self.logger.emit(
                "ACTIVE_LOCK_DETECTED",
                lock_file=str(self.path),
                owner_pid=pid,
            )
            return False

        try:
            self.path.unlink()
        except FileNotFoundError:
            return True
        except OSError as error:
            raise UnsafeLockError(
                f"stale lock cannot be removed safely: {error}"
            ) from error

        self.logger.emit(
            "STALE_LOCK_REMOVED",
            age_seconds=round(age_seconds, 3),
            lock_file=str(self.path),
            owner_pid=pid,
        )
        return True

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            self.acquired = False
            return

        if payload.get("token") != self.token:
            self.logger.emit(
                "LOCK_RELEASE_SKIPPED",
                reason="ownership_changed",
                lock_file=str(self.path),
            )
            self.acquired = False
            return

        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        self.acquired = False
        self.logger.emit("LOCK_RELEASED", lock_file=str(self.path))


class PhoenixWatchdog:
    def __init__(
        self,
        target_script: Path,
        root_dir: Path,
        log_dir: Path,
        lock_file: Path,
        config: MonitorConfig | None = None,
    ) -> None:
        self.target_script = Path(target_script).resolve()
        self.root_dir = Path(root_dir).resolve()
        self.config = config or MonitorConfig()
        self.logger = EventLogger(Path(log_dir))
        self.lock = ProcessLock(
            Path(lock_file),
            self.logger,
            self.config.stale_lock_seconds,
        )
        self.stop_event = threading.Event()
        self.stop_reason = "requested"
        self._process: subprocess.Popen[Any] | None = None
        self._process_lock = threading.Lock()

    @property
    def child_pid(self) -> int | None:
        with self._process_lock:
            return None if self._process is None else self._process.pid

    def request_stop(self, reason: str = "requested") -> None:
        self.stop_reason = reason
        self.stop_event.set()

    def run(self) -> int:
        if not self.target_script.is_file():
            self.logger.emit(
                "CONFIGURATION_ERROR",
                reason="target_not_found",
                target=str(self.target_script),
            )
            return EXIT_CONFIGURATION_ERROR

        self.logger.emit(
            "WATCHDOG_STARTING",
            max_restarts=self.config.max_restarts,
            target=str(self.target_script),
        )
        self.logger.emit(
            "PAPER_MODE_FIXED",
            live_trading=False,
            order_capability=False,
        )

        try:
            self.lock.acquire()
        except (AlreadyRunningError, UnsafeLockError) as error:
            self.logger.emit("WATCHDOG_START_BLOCKED", reason=str(error))
            return EXIT_ALREADY_RUNNING

        exit_code = EXIT_OK
        try:
            exit_code = self._monitor()
            return exit_code
        finally:
            self._safe_stop_child()
            self.lock.release()
            self.logger.emit(
                "WATCHDOG_STOPPED",
                exit_code=exit_code,
                reason=self.stop_reason if self.stop_event.is_set() else "completed",
                restarts_are_bounded=True,
            )

    def _monitor(self) -> int:
        restart_count = 0
        while not self.stop_event.is_set():
            exit_code = self._launch_and_monitor()
            if self.stop_event.is_set():
                self.logger.emit("SAFE_STOP", reason=self.stop_reason)
                return EXIT_OK
            if exit_code == 0:
                self.logger.emit("PROCESS_EXITED", exit_code=0)
                return EXIT_OK
            if exit_code == EXIT_CONFIGURATION_ERROR:
                self.logger.emit(
                    "REPOSITORY_GUARDIAN_BLOCKED",
                    exit_code=exit_code,
                    restart_suppressed=True,
                )
                return EXIT_CONFIGURATION_ERROR

            self.logger.emit(
                "ABNORMAL_EXIT",
                exit_code=exit_code,
                restarts_used=restart_count,
            )
            if restart_count >= self.config.max_restarts:
                self.logger.emit(
                    "RESTART_LIMIT_REACHED",
                    max_restarts=self.config.max_restarts,
                )
                return EXIT_RESTART_LIMIT

            restart_number = restart_count + 1
            delay = self.config.backoff_seconds(restart_number)
            self.logger.emit(
                "RESTART_SCHEDULED",
                backoff_seconds=delay,
                restart_number=restart_number,
            )
            if self.stop_event.wait(delay):
                self.logger.emit("SAFE_STOP", reason=self.stop_reason)
                return EXIT_OK
            restart_count = restart_number

        self.logger.emit("SAFE_STOP", reason=self.stop_reason)
        return EXIT_OK

    def _launch_and_monitor(self) -> int:
        command = [
            sys.executable,
            "-X",
            "utf8",
            str(self.target_script),
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "PHOENIX_MODE": MODE,
                "PHOENIX_EXECUTION_MODE": MODE,
                "PHOENIX_LIVE_TRADING": "0",
                "PHOENIX_ALLOW_LIVE_TRADING": "0",
            }
        )
        popen_options: dict[str, Any] = {
            "cwd": self.root_dir,
            "env": environment,
        }
        if os.name == "nt":
            popen_options["creationflags"] = getattr(
                subprocess,
                "CREATE_NEW_PROCESS_GROUP",
                0,
            )
        else:
            popen_options["start_new_session"] = True

        try:
            process = subprocess.Popen(command, **popen_options)
        except OSError as error:
            self.logger.emit("PROCESS_START_FAILED", reason=str(error))
            return 127

        with self._process_lock:
            self._process = process
        self.logger.emit("PROCESS_LAUNCHED", pid=process.pid)

        startup_deadline = time.monotonic() + self.config.startup_grace_seconds
        while time.monotonic() < startup_deadline:
            exit_code = process.poll()
            if exit_code is not None:
                self._clear_process(process)
                return int(exit_code)
            remaining = max(0.0, startup_deadline - time.monotonic())
            if self.stop_event.wait(min(self.config.poll_seconds, remaining)):
                self._safe_stop_child()
                return 0

        exit_code = process.poll()
        if exit_code is not None:
            self._clear_process(process)
            return int(exit_code)

        self.logger.emit(
            "PROCESS_STARTED",
            pid=process.pid,
            startup_grace_seconds=self.config.startup_grace_seconds,
        )
        while not self.stop_event.wait(self.config.poll_seconds):
            exit_code = process.poll()
            if exit_code is not None:
                self._clear_process(process)
                return int(exit_code)

        self._safe_stop_child()
        return 0

    def _clear_process(self, process: subprocess.Popen[Any]) -> None:
        with self._process_lock:
            if self._process is process:
                self._process = None

    def _safe_stop_child(self) -> None:
        with self._process_lock:
            process = self._process
        if process is None:
            return
        if process.poll() is not None:
            self._clear_process(process)
            return

        self.logger.emit(
            "PROCESS_TERMINATING",
            pid=process.pid,
            reason=self.stop_reason,
        )
        process.terminate()
        try:
            process.wait(timeout=self.config.termination_grace_seconds)
        except subprocess.TimeoutExpired:
            self.logger.emit("PROCESS_KILLING", pid=process.pid)
            process.kill()
            process.wait(timeout=self.config.termination_grace_seconds)
        finally:
            self._clear_process(process)
        self.logger.emit(
            "PROCESS_STOPPED",
            exit_code=process.returncode,
            pid=process.pid,
        )


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _restart_count(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= MAX_RESTARTS_HARD_LIMIT:
        raise argparse.ArgumentTypeError(
            f"value must be between 0 and {MAX_RESTARTS_HARD_LIMIT}"
        )
    return parsed


def _install_signal_handlers(
    watchdog: PhoenixWatchdog,
) -> dict[signal.Signals, Any]:
    previous: dict[signal.Signals, Any] = {}

    def handle(signum: int, _frame: FrameType | None) -> None:
        watchdog.request_stop(f"signal_{signum}")

    for name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, name, None)
        if signum is None:
            continue
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, handle)
    return previous


def _restore_signal_handlers(previous: dict[signal.Signals, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX Step36 WatchDog (PAPER only)",
    )
    parser.add_argument(
        "--max-restarts",
        type=_restart_count,
        default=3,
        help=f"restart limit, 0-{MAX_RESTARTS_HARD_LIMIT} (default: 3)",
    )
    parser.add_argument(
        "--backoff-base-seconds",
        type=_non_negative_float,
        default=5.0,
    )
    parser.add_argument(
        "--backoff-max-seconds",
        type=_non_negative_float,
        default=60.0,
    )
    parser.add_argument(
        "--startup-grace-seconds",
        type=_non_negative_float,
        default=2.0,
    )
    parser.add_argument(
        "--poll-seconds",
        type=_positive_float,
        default=1.0,
    )
    parser.add_argument(
        "--termination-grace-seconds",
        type=_positive_float,
        default=10.0,
    )
    parser.add_argument(
        "--stale-lock-seconds",
        type=_positive_float,
        default=6 * 60 * 60,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = MonitorConfig(
            max_restarts=args.max_restarts,
            backoff_base_seconds=args.backoff_base_seconds,
            backoff_max_seconds=args.backoff_max_seconds,
            startup_grace_seconds=args.startup_grace_seconds,
            poll_seconds=args.poll_seconds,
            termination_grace_seconds=args.termination_grace_seconds,
            stale_lock_seconds=args.stale_lock_seconds,
        )
    except ValueError as error:
        print(f"WatchDog configuration error: {error}", file=sys.stderr)
        return EXIT_CONFIGURATION_ERROR

    watchdog = PhoenixWatchdog(
        target_script=TARGET_SCRIPT,
        root_dir=ROOT_DIR,
        log_dir=LOG_DIR,
        lock_file=LOCK_FILE,
        config=config,
    )
    previous = _install_signal_handlers(watchdog)
    try:
        return watchdog.run()
    except KeyboardInterrupt:
        watchdog.request_stop("keyboard_interrupt")
        return EXIT_OK
    finally:
        _restore_signal_handlers(previous)


if __name__ == "__main__":
    raise SystemExit(main())
