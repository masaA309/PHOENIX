from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Callable, Mapping
from uuid import uuid4


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_HEARTBEAT_PATH = ROOT_DIR / "runtime" / "guardian" / "heartbeat.json"
DEFAULT_LOG_DIR = ROOT_DIR / "logs"

SCHEMA_VERSION = 1
HEARTBEAT_INTERVAL_SECONDS = 30.0
HEARTBEAT_TIMEOUT_SECONDS = 90.0
ATOMIC_REPLACE_ATTEMPTS = 5
ATOMIC_REPLACE_RETRY_SECONDS = 0.01
MODE = "PAPER"
ORDERS_SUBMITTED = 0
OPERATIONAL_SCOPE = "OPERATIONAL"
MONITOR_ONLY_SCOPE = "MONITOR_ONLY"
TRADING_ACTIONS_PAPER_ONLY = "PAPER_ONLY"
TRADING_ACTIONS_DISABLED = "DISABLED"
POSITIONS_PRESENT_REASON = "POSITIONS_PRESENT"
JST = timezone(timedelta(hours=9), name="JST")

RUNNING_STATUS = "RUNNING"
TERMINAL_STATUSES = frozenset({"COMPLETED", "STOPPED", "FAILED"})
VALID_STATUSES = frozenset({RUNNING_STATUS, *TERMINAL_STATUSES})
REQUIRED_FIELDS = (
    "schema_version",
    "timestamp",
    "started_at",
    "status",
    "mode",
    "pid",
    "process_name",
    "repository_root",
    "git_commit",
    "guardian_status",
    "position_reconciliation_status",
    "current_stage",
    "sequence",
    "orders_submitted",
)


class HeartbeatError(RuntimeError):
    """Raised when a heartbeat cannot be started or safely updated."""


@dataclass(frozen=True)
class HeartbeatValidation:
    status: str
    reason: str
    pid: int | None = None
    sequence: int | None = None
    heartbeat_age_seconds: float | None = None
    mode: object = None
    orders_submitted: object = None
    repository_root: object = None
    timestamp: datetime | None = None
    payload: Mapping[str, Any] | None = None

    @property
    def healthy(self) -> bool:
        return self.status == "HEALTHY"

    @property
    def restart_suppressed(self) -> bool:
        return self.status == "SAFETY_STOP"


def _now_jst() -> datetime:
    return datetime.now(JST)


def _normalize_now(value: datetime | None) -> datetime:
    if value is None:
        return _now_jst()
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=JST)
    return value.astimezone(JST)


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


def _git_commit(repository_root: Path) -> str:
    git_dir = repository_root / ".git"
    if git_dir.is_file():
        marker, separator, location = git_dir.read_text(
            encoding="utf-8"
        ).strip().partition(":")
        if marker != "gitdir" or not separator:
            raise HeartbeatError("Git directory marker is invalid")
        candidate = Path(location.strip())
        git_dir = (
            candidate
            if candidate.is_absolute()
            else (repository_root / candidate).resolve(strict=False)
        )
    head_path = git_dir / "HEAD"
    try:
        head = head_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise HeartbeatError(f"Git HEAD is unavailable: {error}") from error
    if head.startswith("ref: "):
        reference = head[5:].strip()
        reference_path = git_dir / reference
        if reference_path.is_file():
            commit = reference_path.read_text(encoding="utf-8").strip()
        else:
            commit = ""
            packed_refs = git_dir / "packed-refs"
            if packed_refs.is_file():
                for line in packed_refs.read_text(encoding="utf-8").splitlines():
                    if line.startswith(("#", "^")):
                        continue
                    value, separator, name = line.partition(" ")
                    if separator and name == reference:
                        commit = value
                        break
    else:
        commit = head
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", commit):
        raise HeartbeatError("Git commit is invalid")
    return commit


class HeartbeatEventLogger:
    """Best-effort append-only heartbeat audit log."""

    def __init__(self, log_dir: str | os.PathLike[str]) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.json_path = self.log_dir / "heartbeat.jsonl"
        self.text_path = self.log_dir / "heartbeat.txt"
        self._lock = threading.Lock()
        self.write_failures = 0

    def emit(
        self,
        event: str,
        *,
        status: str,
        reason: str,
        pid: int | None,
        sequence: int | None,
        heartbeat_age_seconds: float | None,
        repository_root: object,
        action: str,
        restart_attempt: int | None,
        mode: object = MODE,
        orders_submitted: object = ORDERS_SUBMITTED,
        operating_scope: object = OPERATIONAL_SCOPE,
        trading_actions: object = TRADING_ACTIONS_PAPER_ONLY,
        checked_at: datetime | None = None,
    ) -> bool:
        checked = _normalize_now(checked_at)
        payload = {
            "checked_at": checked.isoformat(timespec="seconds"),
            "event": event,
            "status": status,
            "reason": reason,
            "pid": pid,
            "sequence": sequence,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "mode": mode,
            "orders_submitted": orders_submitted,
            "operating_scope": operating_scope,
            "trading_actions": trading_actions,
            "repository_root": repository_root,
            "action": action,
            "restart_attempt": restart_attempt,
        }
        json_line = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        text_line = (
            f"[{checked:%Y-%m-%d %H:%M:%S%z}] {event} "
            f"status={status} reason={reason} pid={pid} sequence={sequence} "
            f"age={heartbeat_age_seconds} action={action} "
            f"restart_attempt={restart_attempt} | Mode: {mode} "
            f"| Orders submitted: {orders_submitted} "
            f"| Operating scope: {operating_scope} "
            f"| Trading actions: {trading_actions} "
            f"| Repository: {repository_root}"
        )
        try:
            with self._lock:
                with self.json_path.open(
                    "a", encoding="utf-8", newline="\n"
                ) as file:
                    file.write(json_line + "\n")
                with self.text_path.open(
                    "a", encoding="utf-8", newline="\n"
                ) as file:
                    file.write(text_line + "\n")
            return True
        except OSError as error:
            self.write_failures += 1
            print(
                f"Heartbeat audit log write failed: {type(error).__name__}: {error}",
                file=sys.stderr,
                flush=True,
            )
            return False


class PhoenixHeartbeat:
    """Atomic PAPER-only process heartbeat with a bounded daemon thread."""

    def __init__(
        self,
        *,
        repository_root: str | os.PathLike[str],
        guardian_status: str,
        position_reconciliation_status: str,
        heartbeat_path: str | os.PathLike[str] | None = None,
        log_dir: str | os.PathLike[str] | None = None,
        interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS,
        pid: int | None = None,
        process_name: str | None = None,
        git_commit: str | None = None,
        monitor_only: bool = False,
        position_reconciliation_reasons: tuple[str, ...] = (),
        now_provider: Callable[[], datetime] = _now_jst,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if not isinstance(monitor_only, bool):
            raise TypeError("monitor_only must be a boolean")
        if not isinstance(position_reconciliation_reasons, tuple) or any(
            not isinstance(reason, str) for reason in position_reconciliation_reasons
        ):
            raise TypeError("position_reconciliation_reasons must be a tuple of strings")
        self.repository_root = Path(repository_root).resolve(strict=False)
        self.guardian_status = guardian_status
        self.position_reconciliation_status = position_reconciliation_status
        self.position_reconciliation_reasons = position_reconciliation_reasons
        self.monitor_only = monitor_only
        self.operating_scope = (
            MONITOR_ONLY_SCOPE if monitor_only else OPERATIONAL_SCOPE
        )
        self.trading_actions = (
            TRADING_ACTIONS_DISABLED
            if monitor_only
            else TRADING_ACTIONS_PAPER_ONLY
        )
        self.heartbeat_path = Path(
            heartbeat_path
            or (self.repository_root / "runtime" / "guardian" / "heartbeat.json")
        )
        self.interval_seconds = float(interval_seconds)
        self.pid = os.getpid() if pid is None else pid
        self.process_name = process_name or Path(sys.argv[0]).name
        self.git_commit = git_commit or _git_commit(self.repository_root)
        self._now_provider = now_provider
        self._audit = HeartbeatEventLogger(
            log_dir or (self.repository_root / "logs")
        )
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_at: datetime | None = None
        self._current_stage = "NOT_STARTED"
        self._sequence = 0
        self._last_payload: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._terminal_status: str | None = None

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence

    @property
    def last_payload(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._last_payload is None else dict(self._last_payload)

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    @property
    def thread_is_alive(self) -> bool:
        thread = self._thread
        return bool(thread is not None and thread.is_alive())

    def _checked_now(self) -> datetime:
        return _normalize_now(self._now_provider())

    def _write(self, status: str) -> dict[str, Any]:
        checked = self._checked_now()
        with self._lock:
            if self._started_at is None:
                self._started_at = checked
            self._sequence += 1
            payload = {
                "schema_version": SCHEMA_VERSION,
                "timestamp": checked.isoformat(timespec="seconds"),
                "started_at": self._started_at.isoformat(timespec="seconds"),
                "status": status,
                "mode": MODE,
                "pid": self.pid,
                "process_name": self.process_name,
                "repository_root": str(self.repository_root),
                "git_commit": self.git_commit,
                "guardian_status": self.guardian_status,
                "position_reconciliation_status": (
                    self.position_reconciliation_status
                ),
                "position_reconciliation_reasons": list(
                    self.position_reconciliation_reasons
                ),
                "operating_scope": self.operating_scope,
                "trading_actions": self.trading_actions,
                "current_stage": self._current_stage,
                "sequence": self._sequence,
                "orders_submitted": ORDERS_SUBMITTED,
            }
            _atomic_write(
                self.heartbeat_path,
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
            self._last_payload = payload
            return dict(payload)

    def _emit_lifecycle(self, event: str, status: str, reason: str) -> None:
        payload = self.last_payload or {}
        self._audit.emit(
            event,
            status=status,
            reason=reason,
            pid=self.pid,
            sequence=payload.get("sequence"),
            heartbeat_age_seconds=0.0,
            repository_root=str(self.repository_root),
            action="NONE",
            restart_attempt=0,
            operating_scope=self.operating_scope,
            trading_actions=self.trading_actions,
        )

    def start(self, current_stage: str = "OPERATIONAL_READY") -> None:
        if self.guardian_status != "READY":
            raise HeartbeatError("Repository Guardian must be READY")
        if self.monitor_only:
            if (
                self.position_reconciliation_status != "WARNING"
                or self.position_reconciliation_reasons
                != (POSITIONS_PRESENT_REASON,)
            ):
                raise HeartbeatError(
                    "MONITOR_ONLY requires Position Reconciliation "
                    "WARNING / POSITIONS_PRESENT"
                )
        elif self.position_reconciliation_status != "READY":
            raise HeartbeatError("Position Reconciliation must be READY")
        if not isinstance(self.pid, int) or isinstance(self.pid, bool) or self.pid <= 0:
            raise HeartbeatError("pid must be a positive integer")
        if not self.process_name:
            raise HeartbeatError("process_name is required")
        if self._thread is not None:
            raise HeartbeatError("Heartbeat is already started")
        self.set_stage(current_stage)
        self._write(RUNNING_STATUS)
        self._emit_lifecycle("HEARTBEAT_STARTED", RUNNING_STATUS, "STARTED")
        self._thread = threading.Thread(
            target=self._run,
            name="phoenix-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def set_stage(self, current_stage: str) -> None:
        if not isinstance(current_stage, str) or not current_stage.strip():
            raise ValueError("current_stage must be a non-empty string")
        with self._lock:
            self._current_stage = current_stage.strip()

    def publish(self) -> dict[str, Any]:
        if self._thread is None:
            raise HeartbeatError("Heartbeat is not started")
        if self._terminal_status is not None:
            raise HeartbeatError("Heartbeat is already stopped")
        return self._write(RUNNING_STATUS)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.publish()
            except OSError as error:
                message = f"{type(error).__name__}: {error}"
                with self._lock:
                    self._last_error = message
                self._audit.emit(
                    "HEARTBEAT_WRITE_FAILED",
                    status="FAILED",
                    reason=message,
                    pid=self.pid,
                    sequence=self.sequence,
                    heartbeat_age_seconds=None,
                    repository_root=str(self.repository_root),
                    action="WAIT_FOR_WATCHDOG",
                    restart_attempt=0,
                    operating_scope=self.operating_scope,
                    trading_actions=self.trading_actions,
                )
                return

    def stop(
        self,
        status: str = "COMPLETED",
        current_stage: str | None = None,
    ) -> dict[str, Any] | None:
        if status not in TERMINAL_STATUSES:
            raise ValueError("terminal heartbeat status is invalid")
        if self._thread is None:
            return self.last_payload
        if self._terminal_status is not None:
            return self.last_payload
        if current_stage is not None:
            self.set_stage(current_stage)
        self._stop_event.set()
        thread = self._thread
        if thread is not threading.current_thread():
            thread.join(timeout=min(5.0, self.interval_seconds + 1.0))
        self._terminal_status = status
        payload = self._write(status)
        self._emit_lifecycle(
            "HEARTBEAT_TERMINATED",
            status,
            status,
        )
        return payload


def _validation(
    status: str,
    reason: str,
    payload: Mapping[str, Any] | None = None,
    *,
    timestamp: datetime | None = None,
    age: float | None = None,
) -> HeartbeatValidation:
    raw_pid = None if payload is None else payload.get("pid")
    raw_sequence = None if payload is None else payload.get("sequence")
    return HeartbeatValidation(
        status=status,
        reason=reason,
        pid=raw_pid if isinstance(raw_pid, int) and not isinstance(raw_pid, bool) else None,
        sequence=(
            raw_sequence
            if isinstance(raw_sequence, int) and not isinstance(raw_sequence, bool)
            else None
        ),
        heartbeat_age_seconds=age,
        mode=None if payload is None else payload.get("mode"),
        orders_submitted=(
            None if payload is None else payload.get("orders_submitted")
        ),
        repository_root=(
            None if payload is None else payload.get("repository_root")
        ),
        timestamp=timestamp,
        payload=payload,
    )


def _parse_heartbeat_timestamp(value: object) -> tuple[datetime | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, "HEARTBEAT_FIELD_TYPE_INVALID"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, "HEARTBEAT_TIMESTAMP_INVALID"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "HEARTBEAT_TIMESTAMP_TIMEZONE_MISSING"
    if parsed.utcoffset() != timedelta(hours=9):
        return None, "HEARTBEAT_TIMESTAMP_NOT_JST"
    return parsed.astimezone(JST), None


def inspect_heartbeat(
    heartbeat_path: str | os.PathLike[str],
    *,
    expected_pid: int,
    expected_repository_root: str | os.PathLike[str],
    now: datetime | None = None,
    timeout_seconds: float = HEARTBEAT_TIMEOUT_SECONDS,
    previous_sequence: int | None = None,
    previous_timestamp: datetime | None = None,
    expected_operating_scope: str | None = None,
) -> HeartbeatValidation:
    checked = _normalize_now(now)
    path = Path(heartbeat_path)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if not path.is_file():
        return _validation("ABNORMAL", "HEARTBEAT_MISSING")
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _validation("ABNORMAL", "HEARTBEAT_JSON_INVALID")
    if not isinstance(payload, dict):
        return _validation("ABNORMAL", "HEARTBEAT_JSON_INVALID")
    if any(name not in payload for name in REQUIRED_FIELDS):
        return _validation("ABNORMAL", "HEARTBEAT_REQUIRED_FIELD_MISSING", payload)

    raw_mode = payload["mode"]
    if not isinstance(raw_mode, str) or raw_mode != MODE:
        return _validation("SAFETY_STOP", "HEARTBEAT_MODE_MISMATCH", payload)
    raw_orders = payload["orders_submitted"]
    if (
        isinstance(raw_orders, bool)
        or not isinstance(raw_orders, int)
        or raw_orders != ORDERS_SUBMITTED
    ):
        return _validation(
            "SAFETY_STOP", "HEARTBEAT_ORDERS_SUBMITTED_MISMATCH", payload
        )
    raw_root = payload["repository_root"]
    try:
        root_matches = isinstance(raw_root, str) and _path_identity(
            raw_root
        ) == _path_identity(expected_repository_root)
    except (OSError, ValueError):
        root_matches = False
    if not root_matches:
        return _validation(
            "SAFETY_STOP", "HEARTBEAT_REPOSITORY_ROOT_MISMATCH", payload
        )
    if payload["guardian_status"] != "READY":
        return _validation(
            "SAFETY_STOP", "HEARTBEAT_GUARDIAN_STATUS_MISMATCH", payload
        )
    operating_scope = payload.get("operating_scope", OPERATIONAL_SCOPE)
    if operating_scope not in {OPERATIONAL_SCOPE, MONITOR_ONLY_SCOPE}:
        return _validation(
            "SAFETY_STOP", "HEARTBEAT_OPERATING_SCOPE_MISMATCH", payload
        )
    if (
        expected_operating_scope is not None
        and operating_scope != expected_operating_scope
    ):
        return _validation(
            "SAFETY_STOP", "HEARTBEAT_OPERATING_SCOPE_MISMATCH", payload
        )
    position_status = payload["position_reconciliation_status"]
    position_reasons = payload.get("position_reconciliation_reasons", [])
    trading_actions = payload.get(
        "trading_actions",
        TRADING_ACTIONS_PAPER_ONLY,
    )
    if operating_scope == MONITOR_ONLY_SCOPE:
        if trading_actions != TRADING_ACTIONS_DISABLED:
            return _validation(
                "SAFETY_STOP", "HEARTBEAT_TRADING_ACTIONS_MISMATCH", payload
            )
        if (
            position_status != "WARNING"
            or position_reasons != [POSITIONS_PRESENT_REASON]
        ):
            return _validation(
                "SAFETY_STOP",
                "HEARTBEAT_POSITION_RECONCILIATION_STATUS_MISMATCH",
                payload,
            )
    else:
        if trading_actions != TRADING_ACTIONS_PAPER_ONLY:
            return _validation(
                "SAFETY_STOP", "HEARTBEAT_TRADING_ACTIONS_MISMATCH", payload
            )
        if position_status != "READY" or position_reasons != []:
            return _validation(
                "SAFETY_STOP",
                "HEARTBEAT_POSITION_RECONCILIATION_STATUS_MISMATCH",
                payload,
            )

    if (
        isinstance(payload["schema_version"], bool)
        or not isinstance(payload["schema_version"], int)
        or payload["schema_version"] != SCHEMA_VERSION
    ):
        return _validation("ABNORMAL", "HEARTBEAT_SCHEMA_INVALID", payload)
    raw_pid = payload["pid"]
    if isinstance(raw_pid, bool) or not isinstance(raw_pid, int) or raw_pid <= 0:
        return _validation("ABNORMAL", "HEARTBEAT_FIELD_TYPE_INVALID", payload)
    if raw_pid != expected_pid:
        return _validation("ABNORMAL", "HEARTBEAT_PID_MISMATCH", payload)
    raw_status = payload["status"]
    if (
        not isinstance(payload["process_name"], str)
        or not payload["process_name"].strip()
        or not isinstance(payload["git_commit"], str)
        or re.fullmatch(r"[0-9a-fA-F]{7,40}", payload["git_commit"]) is None
        or not isinstance(payload["current_stage"], str)
        or not payload["current_stage"].strip()
        or not isinstance(raw_status, str)
        or raw_status not in VALID_STATUSES
    ):
        return _validation("ABNORMAL", "HEARTBEAT_FIELD_TYPE_INVALID", payload)

    sequence = payload["sequence"]
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence <= 0:
        return _validation("ABNORMAL", "HEARTBEAT_SEQUENCE_INVALID", payload)
    timestamp, timestamp_error = _parse_heartbeat_timestamp(payload["timestamp"])
    if timestamp_error:
        return _validation("ABNORMAL", timestamp_error, payload)
    started_at, started_error = _parse_heartbeat_timestamp(payload["started_at"])
    if started_error:
        return _validation("ABNORMAL", started_error, payload)
    assert timestamp is not None and started_at is not None
    if timestamp > checked or started_at > checked or started_at > timestamp:
        return _validation(
            "ABNORMAL", "HEARTBEAT_TIMESTAMP_FUTURE", payload, timestamp=timestamp
        )
    age = max(0.0, (checked - timestamp).total_seconds())
    if age > timeout_seconds:
        return _validation(
            "ABNORMAL",
            "HEARTBEAT_STALE",
            payload,
            timestamp=timestamp,
            age=age,
        )
    if previous_sequence is not None:
        if sequence < previous_sequence:
            return _validation(
                "ABNORMAL",
                "HEARTBEAT_SEQUENCE_REGRESSION",
                payload,
                timestamp=timestamp,
                age=age,
            )
        if (
            sequence == previous_sequence
            and previous_timestamp is not None
            and timestamp > previous_timestamp
        ):
            return _validation(
                "ABNORMAL",
                "HEARTBEAT_SEQUENCE_NOT_INCREMENTED",
                payload,
                timestamp=timestamp,
                age=age,
            )
        if (
            sequence > previous_sequence
            and previous_timestamp is not None
            and timestamp <= previous_timestamp
        ):
            return _validation(
                "ABNORMAL",
                "HEARTBEAT_TIMESTAMP_NOT_ADVANCED",
                payload,
                timestamp=timestamp,
                age=age,
            )
    if raw_status == "FAILED":
        return _validation(
            "ABNORMAL",
            "HEARTBEAT_REPORTED_FAILED",
            payload,
            timestamp=timestamp,
            age=age,
        )
    return _validation(
        "HEALTHY",
        "HEARTBEAT_OK",
        payload,
        timestamp=timestamp,
        age=age,
    )
