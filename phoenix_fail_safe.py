from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Callable, NoReturn
from uuid import uuid4

from phoenix_heartbeat import (
    HEARTBEAT_TIMEOUT_SECONDS,
    HeartbeatValidation,
    MONITOR_ONLY_SCOPE,
    OPERATIONAL_SCOPE,
    TRADING_ACTIONS_DISABLED,
    TRADING_ACTIONS_PAPER_ONLY,
    inspect_heartbeat,
)


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = ROOT_DIR / "logs"
DEFAULT_HEARTBEAT_PATH = ROOT_DIR / "runtime" / "guardian" / "heartbeat.json"

MODE = "PAPER"
ORDERS_SUBMITTED = 0
EXIT_FAIL_SAFE = 2
FAIL_SAFE_STATUS = "FAIL_SAFE"
JST = timezone(timedelta(hours=9), name="JST")

WATCHDOG_HEALTHY_STATUSES = frozenset({"READY", "MONITORING"})
ATOMIC_REPLACE_ATTEMPTS = 5
ATOMIC_REPLACE_RETRY_SECONDS = 0.01


class FailSafeExit(SystemExit):
    """The process must terminate with the non-retryable safety exit code."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(EXIT_FAIL_SAFE)


@dataclass(frozen=True)
class FailSafeResult:
    timestamp: str
    reason: str
    status: str
    mode: str
    orders_submitted: int
    repository_root: str
    guardian_status: str
    position_status: str
    heartbeat_status: str
    watchdog_status: str
    operating_scope: str
    trading_actions: str
    exit_code: int

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _now_jst() -> datetime:
    return datetime.now(JST)


def _path_identity(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(
        os.path.normpath(str(Path(value).resolve(strict=False)))
    ).casefold()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        for attempt in range(ATOMIC_REPLACE_ATTEMPTS):
            try:
                os.replace(temporary_path, path)
                break
            except PermissionError:
                if attempt + 1 >= ATOMIC_REPLACE_ATTEMPTS:
                    raise
                time.sleep(ATOMIC_REPLACE_RETRY_SECONDS)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _text_report(result: FailSafeResult) -> str:
    return (
        f"Timestamp: {result.timestamp}\n"
        f"Status: {result.status}\n"
        f"Reason: {result.reason}\n"
        f"Mode: {result.mode}\n"
        f"Orders submitted: {result.orders_submitted}\n"
        f"Repository root: {result.repository_root}\n"
        f"Guardian status: {result.guardian_status}\n"
        f"Position status: {result.position_status}\n"
        f"Heartbeat status: {result.heartbeat_status}\n"
        f"WatchDog status: {result.watchdog_status}\n"
        f"Operating scope: {result.operating_scope}\n"
        f"Trading actions: {result.trading_actions}\n"
        f"Exit code: {result.exit_code}\n"
    )


def _normalized_heartbeat_reason(validation: HeartbeatValidation) -> str:
    if validation.reason == "HEARTBEAT_JSON_INVALID":
        return "JSON_CORRUPT"
    if validation.reason == "HEARTBEAT_PID_MISMATCH":
        return "PID_MISMATCH"
    if validation.reason == "HEARTBEAT_REPOSITORY_ROOT_MISMATCH":
        return "REPOSITORY_MISMATCH"
    if validation.reason == "HEARTBEAT_MODE_MISMATCH":
        return "MODE_NOT_PAPER"
    if validation.reason == "HEARTBEAT_ORDERS_SUBMITTED_MISMATCH":
        return "ORDERS_SUBMITTED_NONZERO"
    if validation.reason == "HEARTBEAT_GUARDIAN_STATUS_MISMATCH":
        return "GUARDIAN_BLOCKED"
    if validation.reason == "HEARTBEAT_POSITION_RECONCILIATION_STATUS_MISMATCH":
        return "POSITION_BLOCKED"
    if validation.reason == "HEARTBEAT_OPERATING_SCOPE_MISMATCH":
        return "OPERATING_SCOPE_MISMATCH"
    if validation.reason == "HEARTBEAT_TRADING_ACTIONS_MISMATCH":
        return "TRADING_ACTIONS_NOT_DISABLED"
    if validation.reason in {
        "HEARTBEAT_MISSING",
        "HEARTBEAT_STALE",
        "HEARTBEAT_REPORTED_FAILED",
    }:
        return "HEARTBEAT_LOST"
    return validation.reason


class FailSafeController:
    """Monitors PAPER safety invariants and performs one idempotent safe stop."""

    def __init__(
        self,
        *,
        repository_root: str | os.PathLike[str],
        log_dir: str | os.PathLike[str] | None = None,
        expected_repository_root: str | os.PathLike[str] | None = None,
        mode: str = MODE,
        orders_submitted: int = ORDERS_SUBMITTED,
        watchdog_status_provider: Callable[[], str] | None = None,
        monitor_interval_seconds: float = 1.0,
        heartbeat_timeout_seconds: float = HEARTBEAT_TIMEOUT_SECONDS,
        now_provider: Callable[[], datetime] = _now_jst,
    ) -> None:
        if monitor_interval_seconds <= 0:
            raise ValueError("monitor_interval_seconds must be positive")
        if heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds must be positive")
        self.repository_root = Path(repository_root).resolve(strict=False)
        self.expected_repository_root = Path(
            expected_repository_root or repository_root
        ).resolve(strict=False)
        self.log_dir = Path(log_dir or (self.repository_root / "logs"))
        self.mode = mode
        self.orders_submitted = orders_submitted
        self.monitor_interval_seconds = float(monitor_interval_seconds)
        self.heartbeat_timeout_seconds = float(heartbeat_timeout_seconds)
        self._now_provider = now_provider
        self._watchdog_status_provider = watchdog_status_provider

        self.guardian_status = "NOT_CHECKED"
        self.position_status = "NOT_CHECKED"
        self.heartbeat_status = "NOT_STARTED"
        self.watchdog_status = "MONITORING"
        self.monitor_only = False

        self._heartbeat_path: Path | None = None
        self._expected_pid: int | None = None
        self._previous_sequence: int | None = None
        self._previous_timestamp: datetime | None = None
        self._background_stoppers: list[tuple[str, Callable[[], object]]] = []
        self._stop_event = threading.Event()
        self._triggered_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._result: FailSafeResult | None = None
        self._report_error: str | None = None

    @property
    def result(self) -> FailSafeResult | None:
        with self._lock:
            return self._result

    @property
    def triggered(self) -> bool:
        return self._triggered_event.is_set()

    @property
    def monitor_is_alive(self) -> bool:
        thread = self._monitor_thread
        return bool(thread is not None and thread.is_alive())

    @property
    def report_error(self) -> str | None:
        with self._lock:
            return self._report_error

    def update_statuses(
        self,
        *,
        guardian_status: str | None = None,
        position_status: str | None = None,
        heartbeat_status: str | None = None,
        watchdog_status: str | None = None,
    ) -> None:
        with self._lock:
            if guardian_status is not None:
                self.guardian_status = guardian_status
            if position_status is not None:
                self.position_status = position_status
            if heartbeat_status is not None:
                self.heartbeat_status = heartbeat_status
            if watchdog_status is not None:
                self.watchdog_status = watchdog_status

    def register_background_stopper(
        self,
        name: str,
        stopper: Callable[[], object],
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("background name is required")
        if not callable(stopper):
            raise TypeError("background stopper must be callable")
        with self._lock:
            if self._result is not None:
                raise RuntimeError("Fail Safe has already been triggered")
            self._background_stoppers.append((name.strip(), stopper))

    @property
    def operating_scope(self) -> str:
        return MONITOR_ONLY_SCOPE if self.monitor_only else OPERATIONAL_SCOPE

    @property
    def trading_actions(self) -> str:
        return (
            TRADING_ACTIONS_DISABLED
            if self.monitor_only
            else TRADING_ACTIONS_PAPER_ONLY
        )

    def enable_monitor_only(self) -> None:
        with self._lock:
            if self._result is not None or self._monitor_thread is not None:
                raise RuntimeError("Fail Safe operating scope is already active")
            self.monitor_only = True

    def _write_reports(self, result: FailSafeResult) -> None:
        json_path = self.log_dir / "fail_safe.json"
        text_path = self.log_dir / "fail_safe.txt"
        json_content = json.dumps(
            result.as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        try:
            _atomic_write(json_path, json_content)
            _atomic_write(text_path, _text_report(result))
        except OSError as error:
            message = f"{type(error).__name__}: {error}"
            with self._lock:
                self._report_error = message
            print(
                "Fail Safe report write failed: " + message,
                file=sys.stderr,
                flush=True,
            )

    def transition(
        self,
        reason: str,
        *,
        guardian_status: str | None = None,
        position_status: str | None = None,
        heartbeat_status: str | None = None,
        watchdog_status: str | None = None,
    ) -> FailSafeResult:
        if not isinstance(reason, str) or not reason.strip():
            reason = "UNDETERMINED"
        with self._lock:
            if self._result is not None:
                return self._result
            self.update_statuses(
                guardian_status=guardian_status,
                position_status=position_status,
                heartbeat_status=heartbeat_status,
                watchdog_status=watchdog_status,
            )
            result = FailSafeResult(
                timestamp=self._now_provider().astimezone(JST).isoformat(
                    timespec="seconds"
                ),
                reason=reason.strip(),
                status=FAIL_SAFE_STATUS,
                mode=self.mode,
                orders_submitted=self.orders_submitted,
                repository_root=str(self.repository_root),
                guardian_status=self.guardian_status,
                position_status=self.position_status,
                heartbeat_status=self.heartbeat_status,
                watchdog_status=self.watchdog_status,
                operating_scope=self.operating_scope,
                trading_actions=self.trading_actions,
                exit_code=EXIT_FAIL_SAFE,
            )
            self._result = result
            stoppers = tuple(reversed(self._background_stoppers))
            self._stop_event.set()
            self._triggered_event.set()

        for name, stopper in stoppers:
            try:
                stopper()
            except Exception as error:
                print(
                    "Fail Safe background stop failed for "
                    f"{name}: {type(error).__name__}: {error}",
                    file=sys.stderr,
                    flush=True,
                )
        self._write_reports(result)
        return result

    def fail_and_exit(self, reason: str, **statuses: str) -> NoReturn:
        self.transition(reason, **statuses)
        raise FailSafeExit(reason)

    def _static_reason(self) -> str | None:
        if self.mode != MODE:
            return "MODE_NOT_PAPER"
        if (
            isinstance(self.orders_submitted, bool)
            or not isinstance(self.orders_submitted, int)
            or self.orders_submitted != ORDERS_SUBMITTED
        ):
            return "ORDERS_SUBMITTED_NONZERO"
        try:
            root_matches = _path_identity(self.repository_root) == _path_identity(
                self.expected_repository_root
            )
        except (OSError, ValueError):
            root_matches = False
        if not root_matches:
            return "REPOSITORY_MISMATCH"
        if self.guardian_status != "READY":
            return "GUARDIAN_BLOCKED"
        expected_position_status = "WARNING" if self.monitor_only else "READY"
        if self.position_status != expected_position_status:
            return "POSITION_BLOCKED"
        if self.watchdog_status not in WATCHDOG_HEALTHY_STATUSES:
            return "WATCHDOG_ABNORMAL"
        return None

    def check_once(self) -> bool:
        if self.triggered:
            return False
        if self._watchdog_status_provider is not None:
            try:
                watchdog_status = self._watchdog_status_provider()
            except Exception:
                watchdog_status = "ABNORMAL"
            self.update_statuses(watchdog_status=watchdog_status)

        reason = self._static_reason()
        if reason is not None:
            self.transition(reason)
            return False

        heartbeat_path = self._heartbeat_path
        expected_pid = self._expected_pid
        if heartbeat_path is None or expected_pid is None:
            self.transition("HEARTBEAT_LOST", heartbeat_status="LOST")
            return False
        validation = inspect_heartbeat(
            heartbeat_path,
            expected_pid=expected_pid,
            expected_repository_root=self.expected_repository_root,
            now=self._now_provider(),
            timeout_seconds=self.heartbeat_timeout_seconds,
            previous_sequence=self._previous_sequence,
            previous_timestamp=self._previous_timestamp,
            expected_operating_scope=self.operating_scope,
        )
        if not validation.healthy:
            reason = _normalized_heartbeat_reason(validation)
            self.transition(reason, heartbeat_status="LOST")
            return False

        self.update_statuses(heartbeat_status="HEALTHY")
        self._previous_sequence = validation.sequence
        self._previous_timestamp = validation.timestamp
        return True

    def _monitor(self) -> None:
        while not self._stop_event.wait(self.monitor_interval_seconds):
            try:
                if not self.check_once():
                    return
            except Exception:
                self.transition(
                    "FAIL_SAFE_MONITOR_EXCEPTION",
                    heartbeat_status="LOST",
                )
                return

    def start_monitoring(
        self,
        *,
        heartbeat_path: str | os.PathLike[str],
        expected_pid: int,
    ) -> None:
        if isinstance(expected_pid, bool) or not isinstance(expected_pid, int):
            raise TypeError("expected_pid must be an integer")
        if expected_pid <= 0:
            raise ValueError("expected_pid must be positive")
        with self._lock:
            if self._monitor_thread is not None:
                raise RuntimeError("Fail Safe monitoring is already started")
            self._heartbeat_path = Path(heartbeat_path)
            self._expected_pid = expected_pid
        if not self.check_once():
            self.raise_if_triggered()
        self._monitor_thread = threading.Thread(
            target=self._monitor,
            name="phoenix-fail-safe",
            daemon=True,
        )
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        self._stop_event.set()
        thread = self._monitor_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=min(5.0, self.monitor_interval_seconds + 1.0))

    def raise_if_triggered(self) -> None:
        result = self.result
        if result is not None:
            raise FailSafeExit(result.reason)
