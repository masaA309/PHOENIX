from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = ROOT_DIR / "state" / "v7_paper_broker.json"
DEFAULT_REPORT_DIR = ROOT_DIR / "logs"

MODE = "PAPER"
ORDERS_SUBMITTED = 0
EXIT_READY = 0
EXIT_BLOCKED = 2
JST = timezone(timedelta(hours=9), name="JST")
MAX_SOURCE_AGE = timedelta(hours=24)

VALID_STATUSES = frozenset({"READY", "WARNING", "BLOCKED"})


class PositionSourceError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class PositionSnapshot:
    mode: object
    positions_count: object
    orders_submitted: object
    source_timestamp: datetime


class PositionProvider(Protocol):
    """Boundary that can later be replaced by a read-only broker adapter."""

    def get_snapshot(self) -> PositionSnapshot:
        raise NotImplementedError


@dataclass(frozen=True)
class PaperJsonPositionProvider:
    state_path: Path

    def get_snapshot(self) -> PositionSnapshot:
        payload = _load_json_object(self.state_path)
        mode = _state_mode(payload)
        positions_count = _state_positions_count(payload)
        orders_submitted = _state_orders_submitted(payload)
        source_timestamp = _state_timestamp(payload)
        _validate_paper_safety_fields(payload)
        return PositionSnapshot(
            mode=mode,
            positions_count=positions_count,
            orders_submitted=orders_submitted,
            source_timestamp=source_timestamp,
        )


@dataclass
class PositionReconciliationResult:
    checked_at: str
    status: str
    reasons: tuple[str, ...]
    mode: object
    positions_count: object
    orders_submitted: object
    guardian_status: object
    previous_run_status: str
    source_timestamp: str | None
    exit_code: int
    json_report_path: str
    text_report_path: str
    report_error: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    @property
    def blocked(self) -> bool:
        return self.status == "BLOCKED"

    def as_dict(self) -> dict[str, object]:
        return {
            "checked_at": self.checked_at,
            "status": self.status,
            "reasons": list(self.reasons),
            "mode": self.mode,
            "positions_count": self.positions_count,
            "orders_submitted": self.orders_submitted,
            "guardian_status": self.guardian_status,
            "previous_run_status": self.previous_run_status,
            "source_timestamp": self.source_timestamp,
            "exit_code": self.exit_code,
            "json_report_path": self.json_report_path,
            "text_report_path": self.text_report_path,
            "report_error": self.report_error,
        }


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PositionSourceError("STATE_JSON_MISSING")
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise PositionSourceError("STATE_JSON_INVALID") from error
    except OSError as error:
        raise PositionSourceError("STATE_JSON_UNREADABLE") from error
    if not isinstance(payload, dict):
        raise PositionSourceError("STATE_JSON_INVALID")
    return payload


def _first_present(payload: Mapping[str, Any], names: Sequence[str]) -> object:
    for name in names:
        if name in payload:
            return payload[name]
    raise PositionSourceError("STATE_REQUIRED_FIELD_MISSING")


def _state_mode(payload: Mapping[str, Any]) -> object:
    mode = _first_present(payload, ("mode", "broker_name"))
    if not isinstance(mode, str) or not mode.strip():
        raise PositionSourceError("STATE_FIELD_TYPE_INVALID")
    if "mode" in payload and "broker_name" in payload:
        broker_name = payload["broker_name"]
        if not isinstance(broker_name, str) or broker_name != mode:
            raise PositionSourceError("STATE_INCONSISTENT")
    return mode


def _strict_count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PositionSourceError("POSITIONS_COUNT_INVALID")
    if value < 0:
        raise PositionSourceError("POSITIONS_COUNT_NEGATIVE")
    return value


def _valid_quantity(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _count_positions(value: object) -> int:
    if isinstance(value, dict):
        for symbol, position in value.items():
            if not isinstance(symbol, str) or not symbol.strip():
                raise PositionSourceError("STATE_INCONSISTENT")
            if not isinstance(position, dict):
                raise PositionSourceError("STATE_INCONSISTENT")
            if "quantity" in position and not _valid_quantity(position["quantity"]):
                raise PositionSourceError("STATE_INCONSISTENT")
        return len(value)
    if isinstance(value, list):
        for position in value:
            if not isinstance(position, dict):
                raise PositionSourceError("STATE_INCONSISTENT")
            if "quantity" in position and not _valid_quantity(position["quantity"]):
                raise PositionSourceError("STATE_INCONSISTENT")
        return len(value)
    raise PositionSourceError("POSITIONS_COUNT_INVALID")


def _state_positions_count(payload: Mapping[str, Any]) -> int:
    declared: int | None = None
    observed: int | None = None
    if "positions_count" in payload:
        declared = _strict_count(payload["positions_count"])
    if "positions" in payload:
        observed = _count_positions(payload["positions"])
    if declared is None and observed is None:
        raise PositionSourceError("STATE_REQUIRED_FIELD_MISSING")
    if declared is not None and observed is not None and declared != observed:
        raise PositionSourceError("STATE_INCONSISTENT")
    return observed if observed is not None else int(declared)


def _state_orders_submitted(payload: Mapping[str, Any]) -> object:
    for name in ("orders_submitted", "external_orders_submitted"):
        if name in payload:
            return payload[name]
    return ORDERS_SUBMITTED


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PositionSourceError("STATE_FIELD_TYPE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise PositionSourceError("STATE_FIELD_TYPE_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PositionSourceError("STATE_FIELD_TYPE_INVALID")
    return parsed.astimezone(JST)


def _state_timestamp(payload: Mapping[str, Any]) -> datetime:
    raw = _first_present(payload, ("source_timestamp", "updated_at"))
    timestamp = _parse_timestamp(raw)
    if "source_timestamp" in payload and "updated_at" in payload:
        if _parse_timestamp(payload["updated_at"]) != timestamp:
            raise PositionSourceError("STATE_INCONSISTENT")
    return timestamp


def _requires_source_freshness(mode: object) -> bool:
    return not isinstance(mode, str) or mode.strip().upper() != MODE


def _validate_paper_safety_fields(payload: Mapping[str, Any]) -> None:
    for name in ("live_trading_enabled", "margin_trading_enabled"):
        if name not in payload:
            continue
        value = payload[name]
        if not isinstance(value, bool):
            raise PositionSourceError("STATE_FIELD_TYPE_INVALID")
        if value:
            raise PositionSourceError("LIVE_TRADING_ENABLED")


def _checked_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(JST)
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=JST)
    return value.astimezone(JST)


def _strict_zero_orders(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return "ORDERS_SUBMITTED_INVALID"
    if value != 0:
        return "ORDERS_SUBMITTED_NOT_ZERO"
    return None


def _previous_status(path: Path) -> tuple[str, str | None]:
    if not path.exists():
        return "NOT_AVAILABLE", None
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "UNKNOWN", "PREVIOUS_REPORT_INVALID"
    if not isinstance(payload, dict) or payload.get("status") not in VALID_STATUSES:
        return "UNKNOWN", "PREVIOUS_REPORT_INVALID"
    return str(payload["status"]), None


def _append_reason(reasons: list[str], reason: str | None) -> None:
    if reason is not None and reason not in reasons:
        reasons.append(reason)


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
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _text_report(result: PositionReconciliationResult) -> str:
    reasons = ", ".join(result.reasons) if result.reasons else "none"
    lines = [
        f"Checked at: {result.checked_at}",
        f"Status: {result.status}",
        f"Reasons: {reasons}",
        f"Mode: {result.mode}",
        f"Positions count: {result.positions_count}",
        f"Orders submitted: {result.orders_submitted}",
        f"Guardian status: {result.guardian_status}",
        f"Previous run status: {result.previous_run_status}",
        f"Source timestamp: {result.source_timestamp}",
        f"Exit code: {result.exit_code}",
    ]
    if result.report_error:
        lines.append(f"Report error: {result.report_error}")
    return "\n".join(lines) + "\n"


def write_reports(result: PositionReconciliationResult) -> None:
    json_content = json.dumps(
        result.as_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    _atomic_write(Path(result.json_report_path), json_content)
    _atomic_write(Path(result.text_report_path), _text_report(result))


def run_position_reconciliation(
    *,
    guardian_status: object,
    state_path: str | os.PathLike[str] = DEFAULT_STATE_PATH,
    report_dir: str | os.PathLike[str] = DEFAULT_REPORT_DIR,
    mode: object = MODE,
    orders_submitted: object = ORDERS_SUBMITTED,
    provider: PositionProvider | None = None,
    now: datetime | None = None,
    max_source_age: timedelta = MAX_SOURCE_AGE,
) -> PositionReconciliationResult:
    checked = _checked_now(now)
    destination = Path(report_dir).resolve(strict=False)
    json_path = destination / "position_reconciliation.json"
    text_path = destination / "position_reconciliation.txt"
    previous_run_status, previous_error = _previous_status(json_path)

    reasons: list[str] = []
    _append_reason(reasons, previous_error)
    reported_mode = mode
    reported_orders = orders_submitted
    positions_count: object = None
    source_timestamp: str | None = None

    guardian_ready = guardian_status == "READY"
    if not guardian_ready:
        _append_reason(reasons, "GUARDIAN_NOT_READY")
    if not isinstance(mode, str) or mode != MODE:
        _append_reason(reasons, "MODE_NOT_PAPER")
    _append_reason(reasons, _strict_zero_orders(orders_submitted))

    if guardian_ready:
        source = provider or PaperJsonPositionProvider(Path(state_path))
        try:
            snapshot = source.get_snapshot()
        except PositionSourceError as error:
            _append_reason(reasons, error.reason)
        else:
            reported_mode = snapshot.mode
            reported_orders = snapshot.orders_submitted
            positions_count = snapshot.positions_count
            source_timestamp = snapshot.source_timestamp.isoformat(timespec="seconds")

            if not isinstance(snapshot.mode, str) or snapshot.mode != MODE:
                _append_reason(reasons, "MODE_NOT_PAPER")
            _append_reason(reasons, _strict_zero_orders(snapshot.orders_submitted))
            if isinstance(snapshot.positions_count, bool) or not isinstance(
                snapshot.positions_count, int
            ):
                _append_reason(reasons, "POSITIONS_COUNT_INVALID")
            elif snapshot.positions_count < 0:
                _append_reason(reasons, "POSITIONS_COUNT_NEGATIVE")
            if snapshot.source_timestamp > checked:
                _append_reason(reasons, "SOURCE_TIMESTAMP_FUTURE")
            elif _requires_source_freshness(snapshot.mode) and checked - snapshot.source_timestamp > max_source_age:
                _append_reason(reasons, "SOURCE_STATE_STALE")

    if reasons:
        status = "BLOCKED"
    elif isinstance(positions_count, int) and positions_count > 0:
        status = "WARNING"
        reasons.append("POSITIONS_PRESENT")
    else:
        status = "READY"
    exit_code = EXIT_BLOCKED if status == "BLOCKED" else EXIT_READY

    result = PositionReconciliationResult(
        checked_at=checked.isoformat(timespec="seconds"),
        status=status,
        reasons=tuple(reasons),
        mode=reported_mode,
        positions_count=positions_count,
        orders_submitted=reported_orders,
        guardian_status=guardian_status,
        previous_run_status=previous_run_status,
        source_timestamp=source_timestamp,
        exit_code=exit_code,
        json_report_path=str(json_path),
        text_report_path=str(text_path),
    )
    try:
        write_reports(result)
    except OSError as error:
        result.status = "BLOCKED"
        result.reasons = tuple((*result.reasons, "REPORT_WRITE_FAILED"))
        result.exit_code = EXIT_BLOCKED
        result.report_error = f"{type(error).__name__}: {error}"
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX Phase3 Step37 Position Reconciliation",
    )
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--guardian-status", default="READY")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_position_reconciliation(
        guardian_status=args.guardian_status,
        state_path=args.state_path,
        report_dir=args.report_dir,
    )
    reasons = ",".join(result.reasons) if result.reasons else "none"
    print(
        f"Position Reconciliation: {result.status} | reasons={reasons} "
        f"| Mode: {result.mode} | Positions: {result.positions_count} "
        f"| Orders submitted: {result.orders_submitted}",
        flush=True,
    )
    if result.report_error:
        print(f"Position Reconciliation report error: {result.report_error}", flush=True)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
