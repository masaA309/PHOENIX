from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import time
from typing import Callable, Mapping
from uuid import uuid4


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_RECOVERY_STATE_PATH = ROOT_DIR / "runtime" / "guardian" / "recovery_state.json"
DEFAULT_REPORT_DIR = ROOT_DIR / "logs"

SCHEMA_VERSION = 1
MODE = "PAPER"
ORDERS_SUBMITTED = 0
STATUS_READY = "READY"
STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
STATUS_BLOCKED = "BLOCKED"
EXIT_READY = 0
EXIT_RECOVERY_REQUIRED = 1
EXIT_BLOCKED = 2
DEFAULT_MAX_RECOVERY_ATTEMPTS = 3
MAX_RECOVERY_ATTEMPTS_HARD_LIMIT = 10
ATOMIC_REPLACE_ATTEMPTS = 5
ATOMIC_REPLACE_RETRY_SECONDS = 0.01
JST = timezone(timedelta(hours=9), name="JST")

VALID_RECOVERY_STATUSES = frozenset(
    {STATUS_READY, STATUS_RECOVERY_REQUIRED, STATUS_BLOCKED}
)
VALID_PREVIOUS_STATUSES = frozenset(
    {"COMPLETED", "RUNNING", "FAILED", "INTERRUPTED"}
)
VALID_HEARTBEAT_STATUSES = frozenset(
    {"COMPLETED", "STOPPED", "RUNNING", "FAILED", "LOST"}
)
VALID_FAIL_SAFE_STATUSES = frozenset({"NOT_TRIGGERED", "BLOCKED", "FAIL_SAFE"})
REQUIRED_FIELDS = (
    "schema_version",
    "checked_at",
    "previous_run_id",
    "previous_status",
    "previous_started_at",
    "previous_finished_at",
    "previous_pid",
    "previous_git_commit",
    "previous_repository_root",
    "previous_guardian_status",
    "previous_position_status",
    "previous_heartbeat_status",
    "previous_fail_safe_status",
    "previous_orders_submitted",
    "previous_mode",
    "recovery_status",
    "recovery_reasons",
    "recovery_attempt",
    "recovered_at",
    "exit_code",
)


class RecoveryStateError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class RecoveryRequiredExit(SystemExit):
    def __init__(self, reasons: tuple[str, ...] = ()) -> None:
        self.reasons = reasons
        super().__init__(EXIT_RECOVERY_REQUIRED)


@dataclass
class DisasterRecoveryResult:
    schema_version: int
    checked_at: str
    previous_run_id: object
    previous_status: object
    previous_started_at: object
    previous_finished_at: object
    previous_pid: object
    previous_git_commit: object
    previous_repository_root: object
    previous_guardian_status: object
    previous_position_status: object
    previous_heartbeat_status: object
    previous_fail_safe_status: object
    previous_orders_submitted: object
    previous_mode: object
    recovery_status: str
    recovery_reasons: list[str]
    recovery_attempt: int
    recovered_at: str | None
    exit_code: int
    state_path: str
    json_report_path: str
    text_report_path: str
    report_error: str | None = None

    @property
    def ready(self) -> bool:
        return self.recovery_status == STATUS_READY

    @property
    def recovery_required(self) -> bool:
        return self.recovery_status == STATUS_RECOVERY_REQUIRED

    @property
    def blocked(self) -> bool:
        return self.recovery_status == STATUS_BLOCKED

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("state_path")
        payload.pop("json_report_path")
        payload.pop("text_report_path")
        payload.pop("report_error")
        return payload


@dataclass(frozen=True)
class WatchdogRecoveryGate:
    status: str
    reason: str
    recovery_attempt: int | None

    @property
    def restart_allowed(self) -> bool:
        return self.status in {STATUS_READY, STATUS_RECOVERY_REQUIRED}


def _now_jst() -> datetime:
    return datetime.now(JST)


def _checked_now(value: datetime | None) -> datetime:
    if value is None:
        return _now_jst()
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=JST)
    return value.astimezone(JST)


def _path_identity(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(
        os.path.normpath(str(Path(value).resolve(strict=False)))
    ).casefold()


def _paths_equal(left: object, right: str | os.PathLike[str]) -> bool:
    try:
        return isinstance(left, str) and _path_identity(left) == _path_identity(right)
    except (OSError, ValueError):
        return False


def _parse_jst(value: object, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RecoveryStateError("TIMESTAMP_TYPE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RecoveryStateError("TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RecoveryStateError("TIMESTAMP_TIMEZONE_MISSING")
    if parsed.utcoffset() != timedelta(hours=9):
        raise RecoveryStateError("TIMESTAMP_NOT_JST")
    return parsed.astimezone(JST)


def _strict_non_negative_int(value: object, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RecoveryStateError(reason)
    return value


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


def _read_git_commit(repository_root: Path) -> str:
    git_dir = repository_root / ".git"
    if git_dir.is_file():
        marker, separator, location = git_dir.read_text(
            encoding="utf-8"
        ).strip().partition(":")
        if marker != "gitdir" or not separator:
            raise RecoveryStateError("GIT_DIRECTORY_INVALID")
        candidate = Path(location.strip())
        git_dir = (
            candidate
            if candidate.is_absolute()
            else (repository_root / candidate).resolve(strict=False)
        )
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RecoveryStateError("GIT_COMMIT_UNAVAILABLE") from error
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
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", commit) is None:
        raise RecoveryStateError("GIT_COMMIT_INVALID")
    return commit.lower()


def _load_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RecoveryStateError("RECOVERY_STATE_JSON_MISSING")
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryStateError("RECOVERY_STATE_JSON_INVALID") from error
    if not isinstance(payload, dict):
        raise RecoveryStateError("RECOVERY_STATE_JSON_INVALID")
    missing = [name for name in REQUIRED_FIELDS if name not in payload]
    if missing:
        raise RecoveryStateError("RECOVERY_STATE_REQUIRED_FIELD_MISSING")
    return payload


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


def _text_report(result: DisasterRecoveryResult) -> str:
    reasons = ", ".join(result.recovery_reasons) or "NONE"
    return (
        f"Checked at: {result.checked_at}\n"
        f"Recovery status: {result.recovery_status}\n"
        f"Recovery reasons: {reasons}\n"
        f"Recovery attempt: {result.recovery_attempt}\n"
        f"Previous run ID: {result.previous_run_id}\n"
        f"Previous status: {result.previous_status}\n"
        f"Previous PID: {result.previous_pid}\n"
        f"Previous Git commit: {result.previous_git_commit}\n"
        f"Previous repository root: {result.previous_repository_root}\n"
        f"Previous Guardian status: {result.previous_guardian_status}\n"
        f"Previous Position status: {result.previous_position_status}\n"
        f"Previous Heartbeat status: {result.previous_heartbeat_status}\n"
        f"Previous Fail Safe status: {result.previous_fail_safe_status}\n"
        f"Mode: {result.previous_mode}\n"
        f"Orders submitted: {result.previous_orders_submitted}\n"
        f"Recovered at: {result.recovered_at}\n"
        f"Exit code: {result.exit_code}\n"
    )


def write_recovery_artifacts(result: DisasterRecoveryResult) -> None:
    content = json.dumps(
        result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    _atomic_write(Path(result.state_path), content)
    _atomic_write(Path(result.json_report_path), content)
    _atomic_write(Path(result.text_report_path), _text_report(result))


def recover_stale_lock(
    lock_path: str | os.PathLike[str],
    *,
    previous_pid: int,
    pid_checker: Callable[[int], bool] = _pid_is_alive,
) -> bool:
    path = Path(lock_path)
    if not path.is_file():
        return False
    try:
        original = path.read_bytes()
        payload = json.loads(original.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecoveryStateError("STALE_LOCK_INVALID") from error
    if not isinstance(payload, dict):
        raise RecoveryStateError("STALE_LOCK_INVALID")
    lock_pid = payload.get("pid")
    if (
        isinstance(lock_pid, bool)
        or not isinstance(lock_pid, int)
        or lock_pid <= 0
        or lock_pid != previous_pid
    ):
        raise RecoveryStateError("STALE_LOCK_PID_MISMATCH")
    if pid_checker(lock_pid):
        raise RecoveryStateError("STALE_LOCK_PROCESS_ACTIVE")
    try:
        if path.read_bytes() != original:
            raise RecoveryStateError("STALE_LOCK_CHANGED")
        path.unlink()
    except OSError as error:
        raise RecoveryStateError("STALE_LOCK_REMOVE_FAILED") from error
    return True


def _blank_result(
    *,
    checked: datetime,
    state_path: Path,
    report_dir: Path,
    reason: str,
) -> DisasterRecoveryResult:
    return DisasterRecoveryResult(
        schema_version=SCHEMA_VERSION,
        checked_at=checked.isoformat(timespec="seconds"),
        previous_run_id=None,
        previous_status=None,
        previous_started_at=None,
        previous_finished_at=None,
        previous_pid=None,
        previous_git_commit=None,
        previous_repository_root=None,
        previous_guardian_status=None,
        previous_position_status=None,
        previous_heartbeat_status=None,
        previous_fail_safe_status=None,
        previous_orders_submitted=None,
        previous_mode=None,
        recovery_status=STATUS_BLOCKED,
        recovery_reasons=[reason],
        recovery_attempt=0,
        recovered_at=None,
        exit_code=EXIT_BLOCKED,
        state_path=str(state_path),
        json_report_path=str(report_dir / "disaster_recovery.json"),
        text_report_path=str(report_dir / "disaster_recovery.txt"),
    )


def _result_from_payload(
    payload: Mapping[str, object],
    *,
    checked: datetime,
    state_path: Path,
    report_dir: Path,
    status: str,
    reasons: list[str],
    attempt: int,
    recovered_at: str | None,
) -> DisasterRecoveryResult:
    return DisasterRecoveryResult(
        schema_version=SCHEMA_VERSION,
        checked_at=checked.isoformat(timespec="seconds"),
        previous_run_id=payload.get("previous_run_id"),
        previous_status=payload.get("previous_status"),
        previous_started_at=payload.get("previous_started_at"),
        previous_finished_at=payload.get("previous_finished_at"),
        previous_pid=payload.get("previous_pid"),
        previous_git_commit=payload.get("previous_git_commit"),
        previous_repository_root=payload.get("previous_repository_root"),
        previous_guardian_status=payload.get("previous_guardian_status"),
        previous_position_status=payload.get("previous_position_status"),
        previous_heartbeat_status=payload.get("previous_heartbeat_status"),
        previous_fail_safe_status=payload.get("previous_fail_safe_status"),
        previous_orders_submitted=payload.get("previous_orders_submitted"),
        previous_mode=payload.get("previous_mode"),
        recovery_status=status,
        recovery_reasons=reasons,
        recovery_attempt=attempt,
        recovered_at=recovered_at,
        exit_code=(
            EXIT_READY
            if status == STATUS_READY
            else EXIT_RECOVERY_REQUIRED
            if status == STATUS_RECOVERY_REQUIRED
            else EXIT_BLOCKED
        ),
        state_path=str(state_path),
        json_report_path=str(report_dir / "disaster_recovery.json"),
        text_report_path=str(report_dir / "disaster_recovery.txt"),
    )


def _append_unique(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def run_disaster_recovery(
    *,
    guardian_status: object,
    position_status: object,
    repository_root: str | os.PathLike[str] = ROOT_DIR,
    state_path: str | os.PathLike[str] | None = None,
    report_dir: str | os.PathLike[str] | None = None,
    current_git_commit: str | None = None,
    now: datetime | None = None,
    pid_checker: Callable[[int], bool] = _pid_is_alive,
    watchdog_restart_attempt: int = 0,
    max_recovery_attempts: int = DEFAULT_MAX_RECOVERY_ATTEMPTS,
    stale_lock_path: str | os.PathLike[str] | None = None,
) -> DisasterRecoveryResult:
    checked = _checked_now(now)
    root = Path(repository_root).resolve(strict=False)
    recovery_path = Path(
        state_path or (root / "runtime" / "guardian" / "recovery_state.json")
    )
    logs = Path(report_dir or (root / "logs"))
    if (
        isinstance(max_recovery_attempts, bool)
        or not isinstance(max_recovery_attempts, int)
        or not 1 <= max_recovery_attempts <= MAX_RECOVERY_ATTEMPTS_HARD_LIMIT
    ):
        result = _blank_result(
            checked=checked,
            state_path=recovery_path,
            report_dir=logs,
            reason="RECOVERY_LIMIT_INVALID",
        )
        write_recovery_artifacts(result)
        return result
    try:
        restart_attempt = _strict_non_negative_int(
            watchdog_restart_attempt, "WATCHDOG_RESTART_ATTEMPT_INVALID"
        )
        if restart_attempt > MAX_RECOVERY_ATTEMPTS_HARD_LIMIT:
            raise RecoveryStateError("WATCHDOG_RESTART_LIMIT_EXCEEDED")
        payload = _load_json_object(recovery_path)
    except RecoveryStateError as error:
        result = _blank_result(
            checked=checked,
            state_path=recovery_path,
            report_dir=logs,
            reason=error.reason,
        )
        write_recovery_artifacts(result)
        return result

    blocked: list[str] = []
    recovery: list[str] = []
    parsed_times: list[datetime] = []
    previous_pid: int | None = None
    recovery_attempt = 0

    def block(reason: str) -> None:
        _append_unique(blocked, reason)

    if (
        isinstance(payload["schema_version"], bool)
        or not isinstance(payload["schema_version"], int)
        or payload["schema_version"] != SCHEMA_VERSION
    ):
        block("SCHEMA_VERSION_INVALID")
    for field in ("checked_at", "previous_started_at"):
        try:
            parsed = _parse_jst(payload[field])
            assert parsed is not None
            parsed_times.append(parsed)
        except RecoveryStateError as error:
            block(f"{field.upper()}_{error.reason}")
    for field in ("previous_finished_at", "recovered_at"):
        try:
            parsed = _parse_jst(payload[field], optional=True)
            if parsed is not None:
                parsed_times.append(parsed)
        except RecoveryStateError as error:
            block(f"{field.upper()}_{error.reason}")
    if any(value > checked for value in parsed_times):
        block("TIMESTAMP_FUTURE")
    try:
        started = _parse_jst(payload["previous_started_at"])
        finished = _parse_jst(payload["previous_finished_at"], optional=True)
        recorded_checked = _parse_jst(payload["checked_at"])
        if (
            started is not None
            and recorded_checked is not None
            and started > recorded_checked
        ):
            block("TIMESTAMP_ORDER_INVALID")
        if (
            finished is not None
            and started is not None
            and (finished < started or (recorded_checked and finished > recorded_checked))
        ):
            block("TIMESTAMP_ORDER_INVALID")
    except RecoveryStateError:
        pass

    if not isinstance(payload["previous_run_id"], str) or not str(
        payload["previous_run_id"]
    ).strip():
        block("PREVIOUS_RUN_ID_INVALID")
    previous_status = payload["previous_status"]
    if not isinstance(previous_status, str) or previous_status not in VALID_PREVIOUS_STATUSES:
        block("PREVIOUS_STATUS_INVALID")
    if previous_status == "COMPLETED" and payload["previous_finished_at"] is None:
        block("PREVIOUS_FINISHED_AT_MISSING")
    try:
        previous_pid = _strict_non_negative_int(
            payload["previous_pid"], "PREVIOUS_PID_INVALID"
        )
        if previous_pid <= 0:
            block("PREVIOUS_PID_INVALID")
    except RecoveryStateError as error:
        block(error.reason)
        previous_pid = None

    previous_commit = payload["previous_git_commit"]
    if (
        not isinstance(previous_commit, str)
        or re.fullmatch(r"[0-9a-fA-F]{7,40}", previous_commit) is None
    ):
        block("PREVIOUS_GIT_COMMIT_INVALID")
    try:
        expected_commit = (current_git_commit or _read_git_commit(root)).lower()
        if re.fullmatch(r"[0-9a-fA-F]{7,40}", expected_commit) is None:
            raise RecoveryStateError("GIT_COMMIT_INVALID")
        if isinstance(previous_commit, str) and previous_commit.lower() != expected_commit:
            block("GIT_COMMIT_MISMATCH")
    except RecoveryStateError as error:
        block(error.reason)

    if not _paths_equal(payload["previous_repository_root"], root):
        block("REPOSITORY_ROOT_MISMATCH")
    if guardian_status != STATUS_READY or payload["previous_guardian_status"] != STATUS_READY:
        block("GUARDIAN_NOT_READY")
    if position_status != STATUS_READY or payload["previous_position_status"] != STATUS_READY:
        block("POSITION_NOT_READY")
    heartbeat_status = payload["previous_heartbeat_status"]
    if (
        not isinstance(heartbeat_status, str)
        or heartbeat_status not in VALID_HEARTBEAT_STATUSES
    ):
        block("HEARTBEAT_STATUS_INVALID")
    fail_safe_status = payload["previous_fail_safe_status"]
    if (
        not isinstance(fail_safe_status, str)
        or fail_safe_status not in VALID_FAIL_SAFE_STATUSES
    ):
        block("FAIL_SAFE_STATUS_INVALID")
    elif fail_safe_status != "NOT_TRIGGERED":
        block("FAIL_SAFE_TRIGGERED")
    if payload["previous_mode"] != MODE:
        block("MODE_NOT_PAPER")
    orders = payload["previous_orders_submitted"]
    if isinstance(orders, bool) or not isinstance(orders, int) or orders != 0:
        block("ORDERS_SUBMITTED_NOT_ZERO")
    if (
        not isinstance(payload["recovery_status"], str)
        or payload["recovery_status"] not in VALID_RECOVERY_STATUSES
    ):
        block("RECOVERY_STATUS_INVALID")
    elif payload["recovery_status"] == STATUS_BLOCKED:
        block("PREVIOUS_RECOVERY_BLOCKED")
    stored_reasons = payload["recovery_reasons"]
    if not isinstance(stored_reasons, list) or any(
        not isinstance(reason, str) for reason in stored_reasons
    ):
        block("RECOVERY_REASONS_INVALID")
    if isinstance(payload["exit_code"], bool) or not isinstance(
        payload["exit_code"], int
    ):
        block("EXIT_CODE_INVALID")
    try:
        recovery_attempt = _strict_non_negative_int(
            payload["recovery_attempt"], "RECOVERY_ATTEMPT_INVALID"
        )
        if recovery_attempt > MAX_RECOVERY_ATTEMPTS_HARD_LIMIT:
            block("RECOVERY_HARD_LIMIT_EXCEEDED")
    except RecoveryStateError as error:
        block(error.reason)
        recovery_attempt = 0

    if not blocked:
        if previous_status in {"RUNNING", "FAILED", "INTERRUPTED"}:
            _append_unique(recovery, f"PREVIOUS_STATUS_{previous_status}")
        if previous_status == "RUNNING" and previous_pid is not None:
            if pid_checker(previous_pid):
                block("PREVIOUS_PID_STILL_RUNNING")
            else:
                _append_unique(recovery, "PREVIOUS_PID_NOT_RUNNING")
        if previous_status == "COMPLETED" and heartbeat_status not in {
            "COMPLETED",
            "STOPPED",
        }:
            _append_unique(recovery, "HEARTBEAT_INCOMPLETE")
        if payload["recovery_status"] == STATUS_RECOVERY_REQUIRED:
            _append_unique(recovery, "RECOVERY_CONFIRMATION_PENDING")
        if restart_attempt > 0:
            _append_unique(recovery, "WATCHDOG_RESTARTED")

    recovered_at: str | None = None
    next_attempt = recovery_attempt
    if blocked:
        status = STATUS_BLOCKED
        reasons = blocked
    elif recovery:
        if recovery_attempt >= max_recovery_attempts:
            status = STATUS_BLOCKED
            reasons = ["RECOVERY_ATTEMPT_LIMIT_EXCEEDED"]
        elif (
            payload["recovery_status"] == STATUS_RECOVERY_REQUIRED
            and recovery_attempt > 0
        ):
            try:
                if stale_lock_path is not None and previous_pid is not None:
                    recover_stale_lock(
                        stale_lock_path,
                        previous_pid=previous_pid,
                        pid_checker=pid_checker,
                    )
            except RecoveryStateError as error:
                status = STATUS_BLOCKED
                reasons = [error.reason]
            else:
                status = STATUS_READY
                reasons = []
                recovered_at = checked.isoformat(timespec="seconds")
        else:
            status = STATUS_RECOVERY_REQUIRED
            reasons = recovery
            next_attempt = recovery_attempt + 1
    else:
        status = STATUS_READY
        reasons = []
        next_attempt = 0

    result = _result_from_payload(
        payload,
        checked=checked,
        state_path=recovery_path,
        report_dir=logs,
        status=status,
        reasons=reasons,
        attempt=next_attempt,
        recovered_at=recovered_at,
    )
    try:
        write_recovery_artifacts(result)
    except OSError as error:
        result.recovery_status = STATUS_BLOCKED
        _append_unique(result.recovery_reasons, "REPORT_WRITE_FAILED")
        result.exit_code = EXIT_BLOCKED
        result.report_error = f"{type(error).__name__}: {error}"
    return result


class RecoverySession:
    """Atomically records the current run for the next recovery decision."""

    def __init__(
        self,
        *,
        state_path: str | os.PathLike[str],
        repository_root: str | os.PathLike[str],
        git_commit: str,
        guardian_status: str,
        position_status: str,
        recovery_attempt: int = 0,
        recovered_at: str | None = None,
        now_provider: Callable[[], datetime] = _now_jst,
        pid: int | None = None,
        run_id: str | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        self.repository_root = Path(repository_root).resolve(strict=False)
        self.git_commit = git_commit
        self.guardian_status = guardian_status
        self.position_status = position_status
        self.recovery_attempt = recovery_attempt
        self.recovered_at = recovered_at
        self._now_provider = now_provider
        self.pid = os.getpid() if pid is None else pid
        self.run_id = run_id or uuid4().hex
        self.started_at: datetime | None = None
        self._payload: dict[str, object] | None = None

    def _now(self) -> datetime:
        return _checked_now(self._now_provider())

    def _write(self, payload: Mapping[str, object]) -> None:
        _atomic_write(
            self.state_path,
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        self._payload = dict(payload)

    def start(self) -> None:
        if self._payload is not None:
            raise RuntimeError("Recovery session is already started")
        now = self._now()
        self.started_at = now
        payload = {
            "schema_version": SCHEMA_VERSION,
            "checked_at": now.isoformat(timespec="seconds"),
            "previous_run_id": self.run_id,
            "previous_status": "RUNNING",
            "previous_started_at": now.isoformat(timespec="seconds"),
            "previous_finished_at": None,
            "previous_pid": self.pid,
            "previous_git_commit": self.git_commit,
            "previous_repository_root": str(self.repository_root),
            "previous_guardian_status": self.guardian_status,
            "previous_position_status": self.position_status,
            "previous_heartbeat_status": "RUNNING",
            "previous_fail_safe_status": "NOT_TRIGGERED",
            "previous_orders_submitted": ORDERS_SUBMITTED,
            "previous_mode": MODE,
            "recovery_status": STATUS_READY,
            "recovery_reasons": [],
            "recovery_attempt": self.recovery_attempt,
            "recovered_at": self.recovered_at,
            "exit_code": EXIT_READY,
        }
        self._write(payload)

    def finish(
        self,
        *,
        status: str,
        heartbeat_status: str,
        fail_safe_status: str,
    ) -> None:
        if self._payload is None or self.started_at is None:
            return
        if status not in VALID_PREVIOUS_STATUSES - {"RUNNING"}:
            raise ValueError("terminal recovery session status is invalid")
        if heartbeat_status not in VALID_HEARTBEAT_STATUSES:
            raise ValueError("heartbeat status is invalid")
        if fail_safe_status not in VALID_FAIL_SAFE_STATUSES:
            raise ValueError("Fail Safe status is invalid")
        now = self._now()
        payload = dict(self._payload)
        blocked = fail_safe_status != "NOT_TRIGGERED"
        payload.update(
            {
                "checked_at": now.isoformat(timespec="seconds"),
                "previous_status": status,
                "previous_finished_at": now.isoformat(timespec="seconds"),
                "previous_heartbeat_status": heartbeat_status,
                "previous_fail_safe_status": fail_safe_status,
                "recovery_status": (
                    STATUS_BLOCKED
                    if blocked
                    else STATUS_READY
                    if status == "COMPLETED"
                    else STATUS_RECOVERY_REQUIRED
                ),
                "recovery_reasons": (
                    ["FAIL_SAFE_TRIGGERED"]
                    if blocked
                    else []
                    if status == "COMPLETED"
                    else [f"PREVIOUS_STATUS_{status}"]
                ),
                "recovery_attempt": 0 if status == "COMPLETED" else self.recovery_attempt,
                "exit_code": EXIT_BLOCKED if blocked else EXIT_READY,
            }
        )
        self._write(payload)


def inspect_recovery_state_for_watchdog(
    state_path: str | os.PathLike[str],
    *,
    expected_repository_root: str | os.PathLike[str],
    max_recovery_attempts: int = DEFAULT_MAX_RECOVERY_ATTEMPTS,
) -> WatchdogRecoveryGate:
    try:
        payload = _load_json_object(Path(state_path))
    except RecoveryStateError as error:
        return WatchdogRecoveryGate(STATUS_BLOCKED, error.reason, None)
    attempt = payload.get("recovery_attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        return WatchdogRecoveryGate(STATUS_BLOCKED, "RECOVERY_ATTEMPT_INVALID", None)
    if attempt > MAX_RECOVERY_ATTEMPTS_HARD_LIMIT or attempt >= max_recovery_attempts:
        return WatchdogRecoveryGate(
            STATUS_BLOCKED, "RECOVERY_ATTEMPT_LIMIT_EXCEEDED", attempt
        )
    if payload.get("previous_mode") != MODE:
        return WatchdogRecoveryGate(STATUS_BLOCKED, "MODE_NOT_PAPER", attempt)
    orders = payload.get("previous_orders_submitted")
    if isinstance(orders, bool) or not isinstance(orders, int) or orders != 0:
        return WatchdogRecoveryGate(
            STATUS_BLOCKED, "ORDERS_SUBMITTED_NOT_ZERO", attempt
        )
    if not _paths_equal(payload.get("previous_repository_root"), expected_repository_root):
        return WatchdogRecoveryGate(
            STATUS_BLOCKED, "REPOSITORY_ROOT_MISMATCH", attempt
        )
    if payload.get("previous_guardian_status") != STATUS_READY:
        return WatchdogRecoveryGate(STATUS_BLOCKED, "GUARDIAN_NOT_READY", attempt)
    if payload.get("previous_position_status") != STATUS_READY:
        return WatchdogRecoveryGate(STATUS_BLOCKED, "POSITION_NOT_READY", attempt)
    if payload.get("previous_fail_safe_status") != "NOT_TRIGGERED":
        return WatchdogRecoveryGate(STATUS_BLOCKED, "FAIL_SAFE_TRIGGERED", attempt)
    recovery_status = payload.get("recovery_status")
    if recovery_status == STATUS_BLOCKED or payload.get("exit_code") == EXIT_BLOCKED:
        return WatchdogRecoveryGate(STATUS_BLOCKED, "RECOVERY_BLOCKED", attempt)
    previous_status = payload.get("previous_status")
    if (
        recovery_status == STATUS_RECOVERY_REQUIRED
        or previous_status in {"RUNNING", "FAILED", "INTERRUPTED"}
    ):
        return WatchdogRecoveryGate(
            STATUS_RECOVERY_REQUIRED, "RECOVERY_CONFIRMATION_REQUIRED", attempt
        )
    if recovery_status != STATUS_READY or previous_status != "COMPLETED":
        return WatchdogRecoveryGate(STATUS_BLOCKED, "RECOVERY_STATE_UNDETERMINED", attempt)
    return WatchdogRecoveryGate(STATUS_READY, "RECOVERY_STATE_READY", attempt)

