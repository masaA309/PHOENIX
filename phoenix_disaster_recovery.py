from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
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
OPERATIONAL_SCOPE = "OPERATIONAL"
MONITOR_ONLY_SCOPE = "MONITOR_ONLY"
POSITIONS_PRESENT_REASON = "POSITIONS_PRESENT"
TRADING_ACTIONS_PAPER_ONLY = "PAPER_ONLY"
TRADING_ACTIONS_DISABLED = "DISABLED"
STATUS_READY = "READY"
STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
STATUS_BLOCKED = "BLOCKED"
STATE_KIND_RECOVERY_DECISION = "DISASTER_RECOVERY_DECISION"
STATE_KIND_PHOENIX_RUN = "PHOENIX_RUN"
RECOVERY_PHASE_EVALUATION = "EVALUATION"
RECOVERY_PHASE_BOOTSTRAP = "BOOTSTRAP"
EXIT_READY = 0
EXIT_RECOVERY_REQUIRED = 1
EXIT_BLOCKED = 2
DEFAULT_MAX_RECOVERY_ATTEMPTS = 3
MAX_RECOVERY_ATTEMPTS_HARD_LIMIT = 10
ATOMIC_REPLACE_ATTEMPTS = 5
ATOMIC_REPLACE_RETRY_SECONDS = 0.01
JST = timezone(timedelta(hours=9), name="JST")
CURRENT_SAFETY_CONTEXT_MISSING_REASON = "CURRENT_SAFETY_CONTEXT_MISSING"
LEGACY_ATTEMPT_LIMIT_MIGRATION_REASON = "LEGACY_ATTEMPT_LIMIT_MIGRATION"
LEGACY_ATTEMPT_LIMIT_MIGRATION_CONSUMED_REASON = (
    "LEGACY_ATTEMPT_LIMIT_MIGRATION_CONSUMED"
)
CURRENT_SAFETY_CONTEXT_KEYS = (
    "current_git_commit",
    "current_repository_root",
    "current_guardian_status",
    "current_position_status",
    "current_position_reasons",
    "current_operating_scope",
    "current_trading_actions",
    "current_mode",
    "current_orders_submitted",
)
MIGRATION_IDENTITY_FIELDS = (
    "previous_run_id",
    "previous_status",
    "previous_started_at",
    "previous_finished_at",
    "previous_pid",
    "previous_git_commit",
    "previous_repository_root",
    "previous_guardian_status",
    "previous_position_status",
    "previous_position_reasons",
    "previous_operating_scope",
    "previous_trading_actions",
    "previous_heartbeat_status",
    "previous_fail_safe_status",
    "previous_orders_submitted",
    "previous_mode",
)

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
PREVIOUS_RECORD_FIELDS = (
    "previous_run_id",
    "previous_status",
    "previous_started_at",
    "previous_finished_at",
    "previous_pid",
    "previous_git_commit",
    "previous_repository_root",
    "previous_guardian_status",
    "previous_position_status",
    "previous_position_reasons",
    "previous_operating_scope",
    "previous_trading_actions",
    "previous_heartbeat_status",
    "previous_fail_safe_status",
    "previous_orders_submitted",
    "previous_mode",
)
LEGACY_MISSING_STATE_REASONS = frozenset(
    {
        "PREVIOUS_STARTED_AT_TIMESTAMP_TYPE_INVALID",
        "PREVIOUS_RUN_ID_INVALID",
        "PREVIOUS_STATUS_INVALID",
        "PREVIOUS_PID_INVALID",
        "PREVIOUS_GIT_COMMIT_INVALID",
        "REPOSITORY_ROOT_MISMATCH",
        "GUARDIAN_NOT_READY",
        "PREVIOUS_OPERATING_SCOPE_INVALID",
        "POSITION_NOT_READY",
        "HEARTBEAT_STATUS_INVALID",
        "FAIL_SAFE_STATUS_INVALID",
        "MODE_NOT_PAPER",
        "ORDERS_SUBMITTED_NOT_ZERO",
        "PREVIOUS_RECOVERY_BLOCKED",
    }
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
    state_kind: str
    recovery_phase: str
    current_git_commit: str | None
    current_repository_root: object
    current_guardian_status: object
    current_position_status: object
    current_position_reasons: object
    current_operating_scope: object
    current_trading_actions: object
    current_mode: object
    current_orders_submitted: object
    previous_run_id: object
    previous_status: object
    previous_started_at: object
    previous_finished_at: object
    previous_pid: object
    previous_git_commit: object
    previous_repository_root: object
    previous_guardian_status: object
    previous_position_status: object
    previous_position_reasons: object
    previous_operating_scope: object
    previous_trading_actions: object
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
    migration_consumed_identity: str | None = None

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
        if payload["migration_consumed_identity"] is None:
            payload.pop("migration_consumed_identity")
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
        f"State kind: {result.state_kind}\n"
        f"Recovery phase: {result.recovery_phase}\n"
        f"Recovery status: {result.recovery_status}\n"
        f"Recovery reasons: {reasons}\n"
        f"Recovery attempt: {result.recovery_attempt}\n"
        f"Current Git commit: {result.current_git_commit}\n"
        f"Current repository root: {result.current_repository_root}\n"
        f"Current Guardian status: {result.current_guardian_status}\n"
        f"Current Position status: {result.current_position_status}\n"
        f"Current Position reasons: {result.current_position_reasons}\n"
        f"Current operating scope: {result.current_operating_scope}\n"
        f"Current trading actions: {result.current_trading_actions}\n"
        f"Current mode: {result.current_mode}\n"
        f"Current orders submitted: {result.current_orders_submitted}\n"
        f"Previous run ID: {result.previous_run_id}\n"
        f"Previous status: {result.previous_status}\n"
        f"Previous PID: {result.previous_pid}\n"
        f"Previous Git commit: {result.previous_git_commit}\n"
        f"Previous repository root: {result.previous_repository_root}\n"
        f"Previous Guardian status: {result.previous_guardian_status}\n"
        f"Previous Position status: {result.previous_position_status}\n"
        f"Previous Position reasons: {result.previous_position_reasons}\n"
        f"Previous operating scope: {result.previous_operating_scope}\n"
        f"Previous trading actions: {result.previous_trading_actions}\n"
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
        state_kind=STATE_KIND_RECOVERY_DECISION,
        recovery_phase=RECOVERY_PHASE_EVALUATION,
        current_git_commit=None,
        current_repository_root=None,
        current_guardian_status=None,
        current_position_status=None,
        current_position_reasons=None,
        current_operating_scope=None,
        current_trading_actions=None,
        current_mode=None,
        current_orders_submitted=None,
        previous_run_id=None,
        previous_status=None,
        previous_started_at=None,
        previous_finished_at=None,
        previous_pid=None,
        previous_git_commit=None,
        previous_repository_root=None,
        previous_guardian_status=None,
        previous_position_status=None,
        previous_position_reasons=None,
        previous_operating_scope=None,
        previous_trading_actions=None,
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
        migration_consumed_identity=None,
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
    current: Mapping[str, object],
) -> DisasterRecoveryResult:
    return DisasterRecoveryResult(
        schema_version=SCHEMA_VERSION,
        checked_at=checked.isoformat(timespec="seconds"),
        state_kind=STATE_KIND_RECOVERY_DECISION,
        recovery_phase=RECOVERY_PHASE_EVALUATION,
        current_git_commit=current.get("git_commit"),
        current_repository_root=current.get("repository_root"),
        current_guardian_status=current.get("guardian_status"),
        current_position_status=current.get("position_status"),
        current_position_reasons=current.get("position_reasons"),
        current_operating_scope=current.get("operating_scope"),
        current_trading_actions=current.get("trading_actions"),
        current_mode=current.get("mode"),
        current_orders_submitted=current.get("orders_submitted"),
        previous_run_id=payload.get("previous_run_id"),
        previous_status=payload.get("previous_status"),
        previous_started_at=payload.get("previous_started_at"),
        previous_finished_at=payload.get("previous_finished_at"),
        previous_pid=payload.get("previous_pid"),
        previous_git_commit=payload.get("previous_git_commit"),
        previous_repository_root=payload.get("previous_repository_root"),
        previous_guardian_status=payload.get("previous_guardian_status"),
        previous_position_status=payload.get("previous_position_status"),
        previous_position_reasons=payload.get("previous_position_reasons", []),
        previous_operating_scope=payload.get(
            "previous_operating_scope", OPERATIONAL_SCOPE
        ),
        previous_trading_actions=payload.get(
            "previous_trading_actions", TRADING_ACTIONS_PAPER_ONLY
        ),
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
        migration_consumed_identity=payload.get("migration_consumed_identity")
        if isinstance(payload.get("migration_consumed_identity"), str)
        else None,
    )


def _append_unique(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _has_current_safety_context(payload: Mapping[str, object]) -> bool:
    return any(key in payload for key in CURRENT_SAFETY_CONTEXT_KEYS)


def _normalized_previous_position_reasons(payload: Mapping[str, object]) -> list[str]:
    raw_reasons = payload.get("previous_position_reasons", [])
    if not isinstance(raw_reasons, list):
        raw_reasons = [raw_reasons]
    return sorted({str(reason) for reason in raw_reasons})


def _legacy_attempt_limit_identity(
    payload: Mapping[str, object],
    expected_repository_root: str | os.PathLike[str],
) -> str:
    identity_payload: dict[str, object] = {}
    for field in MIGRATION_IDENTITY_FIELDS:
        if field == "previous_repository_root":
            value = payload.get(field)
            identity_payload[field] = (
                _path_identity(value)
                if isinstance(value, str)
                else _path_identity(expected_repository_root)
            )
        elif field == "previous_position_reasons":
            identity_payload[field] = _normalized_previous_position_reasons(payload)
        else:
            identity_payload[field] = payload.get(field)
    encoded = json.dumps(
        identity_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _current_context_missing_only(reasons: list[str]) -> bool:
    return reasons == [CURRENT_SAFETY_CONTEXT_MISSING_REASON]


def _current_safety_context_from_payload(
    payload: Mapping[str, object],
    *,
    expected_repository_root: str | os.PathLike[str],
) -> tuple[dict[str, object], list[str]]:
    if not _has_current_safety_context(payload):
        return {
            "git_commit": None,
            "repository_root": expected_repository_root,
            "guardian_status": None,
            "position_status": None,
            "position_reasons": [],
            "operating_scope": None,
            "trading_actions": None,
            "mode": None,
            "orders_submitted": None,
        }, [CURRENT_SAFETY_CONTEXT_MISSING_REASON]

    blocked: list[str] = []

    current_operating_scope = payload.get("current_operating_scope")
    current_trading_actions = payload.get("current_trading_actions")
    if current_operating_scope not in {OPERATIONAL_SCOPE, MONITOR_ONLY_SCOPE}:
        _append_unique(blocked, "OPERATING_SCOPE_INVALID")
    elif current_operating_scope == MONITOR_ONLY_SCOPE:
        if current_trading_actions != TRADING_ACTIONS_DISABLED:
            _append_unique(blocked, "OPERATING_SCOPE_INVALID")
    elif current_trading_actions != TRADING_ACTIONS_PAPER_ONLY:
        _append_unique(blocked, "OPERATING_SCOPE_INVALID")

    current_position_reasons = payload.get("current_position_reasons", [])
    if not isinstance(current_position_reasons, list) or any(
        not isinstance(reason, str) for reason in current_position_reasons
    ):
        _append_unique(blocked, "POSITION_REASONS_INVALID")
        normalized_position_reasons: tuple[str, ...] = ()
    else:
        normalized_position_reasons = tuple(current_position_reasons)

    current_root_value = payload.get("current_repository_root", expected_repository_root)
    current, current_blocks = _current_safety_context(
        root=Path(str(current_root_value)).resolve(strict=False),
        expected_repository_root=expected_repository_root,
        guardian_status=payload.get("current_guardian_status"),
        position_status=payload.get("current_position_status"),
        monitor_only=current_operating_scope == MONITOR_ONLY_SCOPE,
        position_reasons=normalized_position_reasons,
        current_mode=payload.get("current_mode"),
        current_orders_submitted=payload.get("current_orders_submitted"),
        current_git_commit=payload.get("current_git_commit"),
    )
    return current, blocked + current_blocks


def _is_legacy_attempt_limit_state(
    *,
    payload: Mapping[str, object],
    expected_repository_root: str | os.PathLike[str],
    previous_pid: int | None,
    pid_checker: Callable[[int], bool],
    recovery_attempt: int,
    max_recovery_attempts: int,
) -> bool:
    if payload.get("recovery_status") != STATUS_BLOCKED:
        return False
    if payload.get("recovery_reasons") != ["RECOVERY_ATTEMPT_LIMIT_EXCEEDED"]:
        return False
    if payload.get("exit_code") != EXIT_BLOCKED:
        return False
    if recovery_attempt < max_recovery_attempts:
        return False
    if recovery_attempt > MAX_RECOVERY_ATTEMPTS_HARD_LIMIT:
        return False
    if _has_current_safety_context(payload):
        return False
    legacy_identity = _legacy_attempt_limit_identity(payload, expected_repository_root)
    if payload.get("migration_consumed_identity") == legacy_identity:
        return False
    if previous_pid is None or pid_checker(previous_pid):
        return False
    if payload.get("previous_fail_safe_status") != "NOT_TRIGGERED":
        return False
    if payload.get("previous_orders_submitted") != ORDERS_SUBMITTED:
        return False
    if payload.get("previous_guardian_status") != STATUS_READY:
        return False
    previous_status = payload.get("previous_status")
    if previous_status not in VALID_PREVIOUS_STATUSES:
        return False
    if not _paths_equal(payload.get("previous_repository_root"), expected_repository_root):
        return False
    previous_position_status = payload.get("previous_position_status")
    previous_operating_scope = payload.get("previous_operating_scope")
    previous_position_reasons = _normalized_previous_position_reasons(payload)
    previous_trading_actions = payload.get("previous_trading_actions")
    if previous_position_status == "WARNING":
        if (
            previous_operating_scope != MONITOR_ONLY_SCOPE
            or previous_position_reasons != [POSITIONS_PRESENT_REASON]
            or previous_trading_actions != TRADING_ACTIONS_DISABLED
        ):
            return False
    elif previous_position_status != STATUS_READY:
        return False
    elif (
        previous_operating_scope != OPERATIONAL_SCOPE
        or previous_position_reasons != []
        or previous_trading_actions != TRADING_ACTIONS_PAPER_ONLY
    ):
        return False
    if payload.get("previous_mode") != MODE:
        return False
    previous_commit = payload.get("previous_git_commit")
    if (
        not isinstance(previous_commit, str)
        or re.fullmatch(r"[0-9a-fA-F]{7,40}", previous_commit) is None
    ):
        return False
    try:
        actual_current_commit = _read_git_commit(Path(expected_repository_root))
    except RecoveryStateError:
        return False
    if previous_status != "COMPLETED" and (
        not isinstance(previous_commit, str)
        or previous_commit.lower() != actual_current_commit.lower()
    ):
        return False
    return True


def _is_uninitialized_recovery_decision(
    payload: Mapping[str, object],
    *,
    checked: datetime,
) -> bool:
    if not all(
        field in payload and payload[field] is None
        for field in PREVIOUS_RECORD_FIELDS
    ):
        return False
    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        return False
    try:
        recorded_checked = _parse_jst(payload.get("checked_at"))
    except RecoveryStateError:
        return False
    if recorded_checked is None or recorded_checked > checked:
        return False
    recovery_attempt = payload.get("recovery_attempt")
    if (
        isinstance(recovery_attempt, bool)
        or not isinstance(recovery_attempt, int)
        or recovery_attempt != 0
        or payload.get("recovered_at") is not None
    ):
        return False
    reasons = payload.get("recovery_reasons")
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) for reason in reasons
    ):
        return False

    state_kind = payload.get("state_kind")
    recovery_phase = payload.get("recovery_phase")
    if (
        state_kind == STATE_KIND_RECOVERY_DECISION
        and recovery_phase == RECOVERY_PHASE_BOOTSTRAP
    ):
        status = payload.get("recovery_status")
        exit_code = payload.get("exit_code")
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            return False
        return (status, exit_code) in {
            (STATUS_READY, EXIT_READY),
            (STATUS_BLOCKED, EXIT_BLOCKED),
        }

    if state_kind is not None or recovery_phase is not None:
        return False
    if (
        payload.get("recovery_status") != STATUS_BLOCKED
        or isinstance(payload.get("exit_code"), bool)
        or payload.get("exit_code") != EXIT_BLOCKED
    ):
        return False
    reason_set = frozenset(reasons)
    return reasons == ["RECOVERY_STATE_JSON_MISSING"] or (
        len(reasons) == len(LEGACY_MISSING_STATE_REASONS)
        and reason_set == LEGACY_MISSING_STATE_REASONS
    )


def _current_safety_context(
    *,
    root: Path,
    expected_repository_root: str | os.PathLike[str],
    guardian_status: object,
    position_status: object,
    monitor_only: object,
    position_reasons: object,
    current_mode: object,
    current_orders_submitted: object,
    current_git_commit: str | None,
) -> tuple[dict[str, object], list[str]]:
    blocked: list[str] = []

    def block(reason: str) -> None:
        _append_unique(blocked, reason)

    if not _paths_equal(str(root), expected_repository_root):
        block("REPOSITORY_ROOT_MISMATCH")
    if guardian_status != STATUS_READY:
        block("GUARDIAN_NOT_READY")
    if not isinstance(monitor_only, bool):
        block("MONITOR_ONLY_INVALID")
    if not isinstance(position_reasons, tuple) or any(
        not isinstance(reason, str) for reason in position_reasons
    ):
        block("POSITION_REASONS_INVALID")
        normalized_position_reasons: object = None
    else:
        normalized_position_reasons = list(position_reasons)
        if monitor_only:
            if (
                position_status != "WARNING"
                or position_reasons != (POSITIONS_PRESENT_REASON,)
            ):
                block("POSITION_NOT_MONITOR_ONLY")
        elif position_status != STATUS_READY or position_reasons:
            block("POSITION_NOT_READY")
    if current_mode != MODE:
        block("MODE_NOT_PAPER")
    if (
        isinstance(current_orders_submitted, bool)
        or not isinstance(current_orders_submitted, int)
        or current_orders_submitted != ORDERS_SUBMITTED
    ):
        block("ORDERS_SUBMITTED_NOT_ZERO")

    validated_commit: str | None = None
    try:
        commit_value = (
            _read_git_commit(root)
            if current_git_commit is None
            else current_git_commit
        )
        validated_commit = commit_value.lower()
        if re.fullmatch(r"[0-9a-fA-F]{7,40}", validated_commit) is None:
            raise RecoveryStateError("GIT_COMMIT_INVALID")
    except (AttributeError, RecoveryStateError) as error:
        block(
            error.reason
            if isinstance(error, RecoveryStateError)
            else "GIT_COMMIT_INVALID"
        )
        validated_commit = None

    valid_monitor_only = isinstance(monitor_only, bool) and monitor_only
    current = {
        "git_commit": validated_commit,
        "repository_root": str(root),
        "guardian_status": guardian_status,
        "position_status": position_status,
        "position_reasons": normalized_position_reasons,
        "operating_scope": (
            MONITOR_ONLY_SCOPE if valid_monitor_only else OPERATIONAL_SCOPE
        ),
        "trading_actions": (
            TRADING_ACTIONS_DISABLED
            if valid_monitor_only
            else TRADING_ACTIONS_PAPER_ONLY
        ),
        "mode": current_mode,
        "orders_submitted": current_orders_submitted,
    }
    return current, blocked


def _bootstrap_result(
    *,
    checked: datetime,
    state_path: Path,
    report_dir: Path,
    current: Mapping[str, object],
    reasons: list[str],
) -> DisasterRecoveryResult:
    status = STATUS_BLOCKED if reasons else STATUS_READY
    result = DisasterRecoveryResult(
        schema_version=SCHEMA_VERSION,
        checked_at=checked.isoformat(timespec="seconds"),
        state_kind=STATE_KIND_RECOVERY_DECISION,
        recovery_phase=RECOVERY_PHASE_BOOTSTRAP,
        current_git_commit=current.get("git_commit"),
        current_repository_root=current.get("repository_root"),
        current_guardian_status=current.get("guardian_status"),
        current_position_status=current.get("position_status"),
        current_position_reasons=current.get("position_reasons"),
        current_operating_scope=current.get("operating_scope"),
        current_trading_actions=current.get("trading_actions"),
        current_mode=current.get("mode"),
        current_orders_submitted=current.get("orders_submitted"),
        previous_run_id=None,
        previous_status=None,
        previous_started_at=None,
        previous_finished_at=None,
        previous_pid=None,
        previous_git_commit=None,
        previous_repository_root=None,
        previous_guardian_status=None,
        previous_position_status=None,
        previous_position_reasons=None,
        previous_operating_scope=None,
        previous_trading_actions=None,
        previous_heartbeat_status=None,
        previous_fail_safe_status=None,
        previous_orders_submitted=None,
        previous_mode=None,
        recovery_status=status,
        recovery_reasons=list(reasons),
        recovery_attempt=0,
        recovered_at=None,
        exit_code=EXIT_BLOCKED if reasons else EXIT_READY,
        state_path=str(state_path),
        json_report_path=str(report_dir / "disaster_recovery.json"),
        text_report_path=str(report_dir / "disaster_recovery.txt"),
    )
    try:
        write_recovery_artifacts(result)
    except OSError as error:
        result.recovery_status = STATUS_BLOCKED
        _append_unique(result.recovery_reasons, "REPORT_WRITE_FAILED")
        result.exit_code = EXIT_BLOCKED
        result.report_error = f"{type(error).__name__}: {error}"
    return result


def run_disaster_recovery(
    *,
    guardian_status: object,
    position_status: object,
    repository_root: str | os.PathLike[str] = ROOT_DIR,
    expected_repository_root: str | os.PathLike[str] | None = None,
    state_path: str | os.PathLike[str] | None = None,
    report_dir: str | os.PathLike[str] | None = None,
    current_git_commit: str | None = None,
    current_mode: object = MODE,
    current_orders_submitted: object = ORDERS_SUBMITTED,
    now: datetime | None = None,
    pid_checker: Callable[[int], bool] = _pid_is_alive,
    watchdog_restart_attempt: int = 0,
    max_recovery_attempts: int = DEFAULT_MAX_RECOVERY_ATTEMPTS,
    stale_lock_path: str | os.PathLike[str] | None = None,
    monitor_only: bool = False,
    position_reasons: tuple[str, ...] = (),
) -> DisasterRecoveryResult:
    checked = _checked_now(now)
    root = Path(repository_root).resolve(strict=False)
    recovery_path = Path(
        state_path or (root / "runtime" / "guardian" / "recovery_state.json")
    )
    logs = Path(report_dir or (root / "logs"))
    expected_root = (
        root if expected_repository_root is None else expected_repository_root
    )
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
    except RecoveryStateError as error:
        result = _blank_result(
            checked=checked,
            state_path=recovery_path,
            report_dir=logs,
            reason=error.reason,
        )
        write_recovery_artifacts(result)
        return result

    payload: dict[str, object] | None
    try:
        payload = _load_json_object(recovery_path)
    except RecoveryStateError as error:
        if error.reason == "RECOVERY_STATE_JSON_MISSING":
            payload = None
        else:
            result = _blank_result(
                checked=checked,
                state_path=recovery_path,
                report_dir=logs,
                reason=error.reason,
            )
            write_recovery_artifacts(result)
            return result

    current, current_blocks = _current_safety_context(
        root=root,
        expected_repository_root=expected_root,
        guardian_status=guardian_status,
        position_status=position_status,
        monitor_only=monitor_only,
        position_reasons=position_reasons,
        current_mode=current_mode,
        current_orders_submitted=current_orders_submitted,
        current_git_commit=current_git_commit,
    )
    if payload is None or _is_uninitialized_recovery_decision(
        payload, checked=checked
    ):
        return _bootstrap_result(
            checked=checked,
            state_path=recovery_path,
            report_dir=logs,
            current=current,
            reasons=current_blocks,
        )

    blocked: list[str] = list(current_blocks)
    recovery: list[str] = []
    parsed_times: list[datetime] = []
    previous_pid: int | None = None
    recovery_attempt = 0
    payload_current, payload_current_blocks = _current_safety_context_from_payload(
        payload,
        expected_repository_root=expected_root,
    )
    if not _current_context_missing_only(payload_current_blocks):
        for reason in payload_current_blocks:
            _append_unique(blocked, reason)

    def block(reason: str) -> None:
        _append_unique(blocked, reason)

    if (
        isinstance(payload["schema_version"], bool)
        or not isinstance(payload["schema_version"], int)
        or payload["schema_version"] != SCHEMA_VERSION
    ):
        block("SCHEMA_VERSION_INVALID")
    state_kind = payload.get("state_kind")
    recovery_phase = payload.get("recovery_phase")
    if state_kind is not None and state_kind not in {
        STATE_KIND_RECOVERY_DECISION,
        STATE_KIND_PHOENIX_RUN,
    }:
        block("STATE_KIND_INVALID")
    if recovery_phase is not None and recovery_phase not in {
        RECOVERY_PHASE_EVALUATION,
        RECOVERY_PHASE_BOOTSTRAP,
    }:
        block("RECOVERY_PHASE_INVALID")
    if (
        state_kind == STATE_KIND_PHOENIX_RUN
        and recovery_phase == RECOVERY_PHASE_BOOTSTRAP
    ):
        block("RECOVERY_STATE_KIND_INCONSISTENT")
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
    current_commit = current.get("git_commit")
    if (
        previous_status != "COMPLETED"
        and isinstance(previous_commit, str)
        and isinstance(current_commit, str)
        and previous_commit.lower() != current_commit.lower()
    ):
        block("GIT_COMMIT_MISMATCH")

    if not _paths_equal(payload["previous_repository_root"], root):
        block("REPOSITORY_ROOT_MISMATCH")
    if payload["previous_guardian_status"] != STATUS_READY:
        block("GUARDIAN_NOT_READY")
    previous_position_status = payload["previous_position_status"]
    previous_position_reasons = payload.get("previous_position_reasons", [])
    previous_operating_scope = payload.get(
        "previous_operating_scope", OPERATIONAL_SCOPE
    )
    previous_trading_actions = payload.get(
        "previous_trading_actions", TRADING_ACTIONS_PAPER_ONLY
    )
    if previous_operating_scope not in {OPERATIONAL_SCOPE, MONITOR_ONLY_SCOPE}:
        block("PREVIOUS_OPERATING_SCOPE_INVALID")
    if previous_position_status == "WARNING":
        if (
            previous_operating_scope != MONITOR_ONLY_SCOPE
            or previous_position_reasons != [POSITIONS_PRESENT_REASON]
            or previous_trading_actions != TRADING_ACTIONS_DISABLED
        ):
            block("PREVIOUS_POSITION_NOT_MONITOR_ONLY")
    elif previous_position_status != STATUS_READY:
        block("POSITION_NOT_READY")
    elif (
        previous_operating_scope != OPERATIONAL_SCOPE
        or previous_position_reasons != []
        or previous_trading_actions != TRADING_ACTIONS_PAPER_ONLY
    ):
        block("PREVIOUS_POSITION_STATE_INCONSISTENT")
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

    legacy_identity = _legacy_attempt_limit_identity(payload, expected_root)
    consumed_identity_matches = payload.get("migration_consumed_identity") == legacy_identity
    legacy_attempt_state = _is_legacy_attempt_limit_state(
        payload=payload,
        expected_repository_root=expected_root,
        previous_pid=previous_pid,
        pid_checker=pid_checker,
        recovery_attempt=recovery_attempt,
        max_recovery_attempts=max_recovery_attempts,
    )

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
    if fail_safe_status != "NOT_TRIGGERED" and fail_safe_status in VALID_FAIL_SAFE_STATUSES:
        status = STATUS_BLOCKED
        reasons = ["FAIL_SAFE_TRIGGERED"]
    elif blocked:
        status = STATUS_BLOCKED
        reasons = blocked
    elif _current_context_missing_only(payload_current_blocks) and consumed_identity_matches:
        status = STATUS_BLOCKED
        reasons = [LEGACY_ATTEMPT_LIMIT_MIGRATION_CONSUMED_REASON]
    elif _current_context_missing_only(payload_current_blocks) and legacy_attempt_state:
        status = STATUS_RECOVERY_REQUIRED
        reasons = [LEGACY_ATTEMPT_LIMIT_MIGRATION_REASON]
        next_attempt = 0
        payload["migration_consumed_identity"] = legacy_identity
    elif payload_current_blocks:
        status = STATUS_BLOCKED
        reasons = payload_current_blocks
    elif recovery:
        if recovery_attempt >= max_recovery_attempts and not legacy_attempt_state:
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
        current=current,
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
        position_reasons: tuple[str, ...] = (),
        monitor_only: bool = False,
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
        self.position_reasons = position_reasons
        self.monitor_only = monitor_only
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
        if not isinstance(self.monitor_only, bool):
            raise TypeError("monitor_only must be a boolean")
        if not isinstance(self.position_reasons, tuple) or any(
            not isinstance(reason, str) for reason in self.position_reasons
        ):
            raise TypeError("position_reasons must be a tuple of strings")
        if self.monitor_only:
            if (
                self.position_status != "WARNING"
                or self.position_reasons != (POSITIONS_PRESENT_REASON,)
            ):
                raise ValueError(
                    "MONITOR_ONLY requires Position Reconciliation "
                    "WARNING / POSITIONS_PRESENT"
                )
        elif self.position_status != STATUS_READY:
            raise ValueError("Position Reconciliation must be READY")
        now = self._now()
        self.started_at = now
        payload = {
            "schema_version": SCHEMA_VERSION,
            "checked_at": now.isoformat(timespec="seconds"),
            "state_kind": STATE_KIND_PHOENIX_RUN,
            "recovery_phase": RECOVERY_PHASE_EVALUATION,
            "current_git_commit": self.git_commit,
            "current_repository_root": str(self.repository_root),
            "current_guardian_status": self.guardian_status,
            "current_position_status": self.position_status,
            "current_position_reasons": list(self.position_reasons),
            "current_operating_scope": (
                MONITOR_ONLY_SCOPE if self.monitor_only else OPERATIONAL_SCOPE
            ),
            "current_trading_actions": (
                TRADING_ACTIONS_DISABLED
                if self.monitor_only
                else TRADING_ACTIONS_PAPER_ONLY
            ),
            "current_mode": MODE,
            "current_orders_submitted": ORDERS_SUBMITTED,
            "previous_run_id": self.run_id,
            "previous_status": "RUNNING",
            "previous_started_at": now.isoformat(timespec="seconds"),
            "previous_finished_at": None,
            "previous_pid": self.pid,
            "previous_git_commit": self.git_commit,
            "previous_repository_root": str(self.repository_root),
            "previous_guardian_status": self.guardian_status,
            "previous_position_status": self.position_status,
            "previous_position_reasons": list(self.position_reasons),
            "previous_operating_scope": (
                MONITOR_ONLY_SCOPE if self.monitor_only else OPERATIONAL_SCOPE
            ),
            "previous_trading_actions": (
                TRADING_ACTIONS_DISABLED
                if self.monitor_only
                else TRADING_ACTIONS_PAPER_ONLY
            ),
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
    pid_checker: Callable[[int], bool] = _pid_is_alive,
) -> WatchdogRecoveryGate:
    try:
        payload = _load_json_object(Path(state_path))
    except RecoveryStateError as error:
        return WatchdogRecoveryGate(STATUS_BLOCKED, error.reason, None)
    attempt = payload.get("recovery_attempt")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        return WatchdogRecoveryGate(STATUS_BLOCKED, "RECOVERY_ATTEMPT_INVALID", None)
    bootstrap_state = _is_uninitialized_recovery_decision(
        payload, checked=_now_jst()
    )
    previous_fail_safe_status = payload.get("previous_fail_safe_status")
    previous_status = payload.get("previous_status")
    if (
        isinstance(previous_fail_safe_status, str)
        and previous_fail_safe_status in VALID_FAIL_SAFE_STATUSES
        and previous_fail_safe_status != "NOT_TRIGGERED"
    ):
        return WatchdogRecoveryGate(STATUS_BLOCKED, "FAIL_SAFE_TRIGGERED", attempt)
    if not bootstrap_state:
        if previous_status not in VALID_PREVIOUS_STATUSES:
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "PREVIOUS_STATUS_INVALID", attempt
            )
        previous_commit = payload.get("previous_git_commit")
        if (
            not isinstance(previous_commit, str)
            or re.fullmatch(r"[0-9a-fA-F]{7,40}", previous_commit) is None
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "PREVIOUS_GIT_COMMIT_INVALID", attempt
            )
        previous_heartbeat_status = payload.get("previous_heartbeat_status")
        if (
            not isinstance(previous_heartbeat_status, str)
            or previous_heartbeat_status not in VALID_HEARTBEAT_STATUSES
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "HEARTBEAT_STATUS_INVALID", attempt
            )
        if (
            not isinstance(previous_fail_safe_status, str)
            or previous_fail_safe_status not in VALID_FAIL_SAFE_STATUSES
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "FAIL_SAFE_STATUS_INVALID", attempt
            )
        try:
            actual_current_commit = _read_git_commit(Path(expected_repository_root))
        except RecoveryStateError as error:
            return WatchdogRecoveryGate(STATUS_BLOCKED, error.reason, attempt)
        if previous_status != "COMPLETED" and (
            previous_commit.lower() != actual_current_commit.lower()
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "GIT_COMMIT_MISMATCH", attempt
            )
    else:
        previous_commit = payload.get("previous_git_commit")
        previous_heartbeat_status = payload.get("previous_heartbeat_status")
    previous_pid: int | None = None
    try:
        previous_pid = _strict_non_negative_int(
            payload.get("previous_pid"), "PREVIOUS_PID_INVALID"
        )
        if previous_pid <= 0:
            previous_pid = None
    except RecoveryStateError:
        previous_pid = None
    legacy_identity = _legacy_attempt_limit_identity(payload, expected_repository_root)
    consumed_identity_matches = payload.get("migration_consumed_identity") == legacy_identity
    legacy_attempt_state = _is_legacy_attempt_limit_state(
        payload=payload,
        expected_repository_root=expected_repository_root,
        previous_pid=previous_pid,
        pid_checker=pid_checker,
        recovery_attempt=attempt,
        max_recovery_attempts=max_recovery_attempts,
    )
    current, current_blocks = _current_safety_context_from_payload(
        payload,
        expected_repository_root=expected_repository_root,
    )
    current_context_missing = _current_context_missing_only(current_blocks)
    if current_blocks and not current_context_missing:
        return WatchdogRecoveryGate(STATUS_BLOCKED, current_blocks[0], attempt)
    if attempt > MAX_RECOVERY_ATTEMPTS_HARD_LIMIT:
        return WatchdogRecoveryGate(
            STATUS_BLOCKED, "RECOVERY_HARD_LIMIT_EXCEEDED", attempt
        )
    if (
        attempt >= max_recovery_attempts
        and not legacy_attempt_state
        and not current_context_missing
    ):
        return WatchdogRecoveryGate(
            STATUS_BLOCKED, "RECOVERY_ATTEMPT_LIMIT_EXCEEDED", attempt
        )
    if _is_uninitialized_recovery_decision(
        payload, checked=_now_jst()
    ):
        if (
            payload.get("state_kind") != STATE_KIND_RECOVERY_DECISION
            or payload.get("recovery_phase") != RECOVERY_PHASE_BOOTSTRAP
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "BOOTSTRAP_DIRECT_START_REQUIRED", attempt
            )
        if payload.get("recovery_status") != STATUS_READY:
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "RECOVERY_BLOCKED", attempt
            )
        if payload.get("current_mode") != MODE:
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "MODE_NOT_PAPER", attempt
            )
        current_orders = payload.get("current_orders_submitted")
        if (
            isinstance(current_orders, bool)
            or not isinstance(current_orders, int)
            or current_orders != ORDERS_SUBMITTED
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "ORDERS_SUBMITTED_NOT_ZERO", attempt
            )
        if not _paths_equal(
            payload.get("current_repository_root"), expected_repository_root
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "REPOSITORY_ROOT_MISMATCH", attempt
            )
        if payload.get("current_guardian_status") != STATUS_READY:
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "GUARDIAN_NOT_READY", attempt
            )
        current_commit = payload.get("current_git_commit")
        if (
            not isinstance(current_commit, str)
            or re.fullmatch(r"[0-9a-fA-F]{7,40}", current_commit) is None
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "GIT_COMMIT_INVALID", attempt
            )
        current_position_status = payload.get("current_position_status")
        current_scope = payload.get("current_operating_scope")
        current_reasons = payload.get("current_position_reasons")
        current_trading_actions = payload.get("current_trading_actions")
        if current_position_status == "WARNING":
            if (
                current_scope != MONITOR_ONLY_SCOPE
                or current_reasons != [POSITIONS_PRESENT_REASON]
                or current_trading_actions != TRADING_ACTIONS_DISABLED
            ):
                return WatchdogRecoveryGate(
                    STATUS_BLOCKED, "POSITION_NOT_MONITOR_ONLY", attempt
                )
        elif current_position_status != STATUS_READY:
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "POSITION_NOT_READY", attempt
            )
        elif (
            current_scope != OPERATIONAL_SCOPE
            or current_reasons != []
            or current_trading_actions != TRADING_ACTIONS_PAPER_ONLY
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "POSITION_STATE_INCONSISTENT", attempt
            )
        return WatchdogRecoveryGate(
            STATUS_RECOVERY_REQUIRED,
            "BOOTSTRAP_CONFIRMATION_REQUIRED",
            attempt,
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
    previous_position_status = payload.get("previous_position_status")
    previous_operating_scope = payload.get(
        "previous_operating_scope", OPERATIONAL_SCOPE
    )
    previous_position_reasons = payload.get("previous_position_reasons", [])
    previous_trading_actions = payload.get(
        "previous_trading_actions", TRADING_ACTIONS_PAPER_ONLY
    )
    if previous_operating_scope not in {OPERATIONAL_SCOPE, MONITOR_ONLY_SCOPE}:
        return WatchdogRecoveryGate(
            STATUS_BLOCKED, "OPERATING_SCOPE_INVALID", attempt
        )
    if previous_position_status == "WARNING":
        if (
            previous_operating_scope != MONITOR_ONLY_SCOPE
            or previous_position_reasons != [POSITIONS_PRESENT_REASON]
            or previous_trading_actions != TRADING_ACTIONS_DISABLED
        ):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "POSITION_NOT_MONITOR_ONLY", attempt
            )
    elif previous_position_status != STATUS_READY:
        return WatchdogRecoveryGate(STATUS_BLOCKED, "POSITION_NOT_READY", attempt)
    elif (
        previous_operating_scope != OPERATIONAL_SCOPE
        or previous_position_reasons != []
        or previous_trading_actions != TRADING_ACTIONS_PAPER_ONLY
    ):
        return WatchdogRecoveryGate(
            STATUS_BLOCKED, "POSITION_STATE_INCONSISTENT", attempt
        )
    if previous_status == "RUNNING" and previous_pid is not None:
        if pid_checker(previous_pid):
            return WatchdogRecoveryGate(
                STATUS_BLOCKED, "PREVIOUS_PID_STILL_RUNNING", attempt
            )
    if current_context_missing and consumed_identity_matches:
        return WatchdogRecoveryGate(
            STATUS_BLOCKED,
            LEGACY_ATTEMPT_LIMIT_MIGRATION_CONSUMED_REASON,
            attempt,
        )
    if current_context_missing and legacy_attempt_state:
        return WatchdogRecoveryGate(
            STATUS_RECOVERY_REQUIRED,
            LEGACY_ATTEMPT_LIMIT_MIGRATION_REASON,
            0,
        )
    if current_context_missing:
        return WatchdogRecoveryGate(
            STATUS_BLOCKED,
            CURRENT_SAFETY_CONTEXT_MISSING_REASON,
            attempt,
        )
    recovery_status = payload.get("recovery_status")
    if (
        (recovery_status == STATUS_BLOCKED or payload.get("exit_code") == EXIT_BLOCKED)
        and not legacy_attempt_state
    ):
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
