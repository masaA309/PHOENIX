from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import csv
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from phoenix_core.data_freshness import JST
from phoenix_core.order_bridge_gate import (
    EXECUTION_MODE as STEP42_EXECUTION_MODE,
    INSTRUCTION_FILE as STEP42_INSTRUCTION_FILE,
    OUTPUT_COLUMNS as STEP42_OUTPUT_COLUMNS,
    REPORT_JSON_FILE as STEP42_REPORT_JSON_FILE,
    SCHEMA_VERSION as STEP42_SCHEMA_VERSION,
    TRADING_MODE as STEP42_TRADING_MODE,
)
from phoenix_core.performance_tracker import atomic_write, resolve_path


SCHEMA_VERSION = 1
VERSION = "PHOENIX v7 Step43"
CONTRACT_ID = "PHOENIX_STEP43_VBA_BRIDGE"
TRADING_MODE = "PAPER"
EXECUTION_MODE = "DRY_RUN"
TRADING_ACTIONS = "DISABLED"
ORDERS_SUBMITTED = 0
BRIDGE_STATUS_PENDING = "PENDING"
BRIDGE_STATUS_PROCESSING = "PROCESSING"
BRIDGE_STATUS_ACCEPTED = "ACCEPTED"
BRIDGE_STATUS_REJECTED = "REJECTED"
BRIDGE_STATUS_DUPLICATE = "DUPLICATE"
BRIDGE_STATUS_EXPIRED = "EXPIRED"
BRIDGE_STATUS_CORRUPT = "CORRUPT"
BRIDGE_FINAL_STATUSES = {
    BRIDGE_STATUS_ACCEPTED,
    BRIDGE_STATUS_REJECTED,
    BRIDGE_STATUS_DUPLICATE,
    BRIDGE_STATUS_EXPIRED,
    BRIDGE_STATUS_CORRUPT,
}
BRIDGE_STATUSES = {
    BRIDGE_STATUS_PENDING,
    BRIDGE_STATUS_PROCESSING,
    *BRIDGE_FINAL_STATUSES,
}
ALLOWED_OPERATING_SCOPES = {"OPERATIONAL", "MONITOR_ONLY"}
ALLOWED_RESULTS = {
    BRIDGE_STATUS_ACCEPTED,
    BRIDGE_STATUS_REJECTED,
    BRIDGE_STATUS_DUPLICATE,
    BRIDGE_STATUS_EXPIRED,
    BRIDGE_STATUS_CORRUPT,
}
PENDING_DIR = "runtime/v7_vba_bridge/outbox/pending"
PROCESSING_DIR = "runtime/v7_vba_bridge/outbox/processing"
COMPLETE_DIR = "runtime/v7_vba_bridge/outbox/complete"
REJECTED_DIR = "runtime/v7_vba_bridge/outbox/rejected"
INBOX_DIR = "runtime/v7_vba_bridge/inbox"
STATE_FILE = "state/v7_vba_bridge_state.json"
AUDIT_JSONL_FILE = "reports/v7_vba_bridge_audit.jsonl"
REPORT_JSON_FILE = "reports/v7_vba_bridge_report.json"
REPORT_TEXT_FILE = "reports/v7_vba_bridge_report.txt"
OUTBOX_COLUMNS = [
    "schema_version",
    "intent_id",
    "idempotency_key",
    "generated_at",
    "expires_at",
    "ticker",
    "market",
    "side",
    "order_type",
    "quantity",
    "reference_price",
    "limit_price",
    "stop_loss_price",
    "take_profit_price",
    "estimated_notional",
    "estimated_max_loss",
    "trading_mode",
    "execution_mode",
    "bridge_status",
    "checksum",
]
RECEIPT_COLUMNS = [
    "schema_version",
    "intent_id",
    "idempotency_key",
    "received_at",
    "result",
    "reason_codes",
    "vba_instance_id",
    "source_checksum",
    "orders_submitted",
    "checksum",
]


def _now_jst() -> datetime:
    return datetime.now(JST)


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value).strip().lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _normalize_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    return result


def _normalize_money(value: Any, *, field: str) -> str:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be numeric") from error
    if not (number == number):
        raise ValueError(f"{field} must be numeric")
    return f"{number:.2f}"


def _money_value(value: Any, *, field: str) -> float:
    return float(_normalize_money(value, field=field))


def _parse_jst_datetime(value: Any, *, field: str) -> datetime:
    text = _normalize_text(value)
    if not text:
        raise ValueError(f"{field} is missing")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field} is invalid") from error
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _field_payload(payload: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field: payload[field] for field in fields}


def _checksum_fields(payload: Mapping[str, Any], columns: Sequence[str]) -> str:
    canonical = _field_payload(payload, [column for column in columns if column != "checksum"])
    return _stable_hash(canonical)


def _csv_write_atomic(path: Path, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=list(columns),
                extrasaction="raise",
                lineterminator="\n",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in columns})
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _read_json_strict(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8-sig")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _read_csv_rows(path: Path, *, columns: Sequence[str]) -> list[dict[str, str]]:
    raw = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw, newline=""), strict=True)
    header = tuple(reader.fieldnames or ())
    if header != tuple(columns):
        raise ValueError(f"CSV columns do not match contract: {path}")
    rows: list[dict[str, str]] = []
    for raw_row in reader:
        values = ["" if raw_row.get(column) is None else str(raw_row.get(column)).strip() for column in columns]
        if not any(values):
            continue
        rows.append({column: value for column, value in zip(columns, values, strict=True)})
    return rows


def _read_single_row_csv(path: Path, *, columns: Sequence[str]) -> dict[str, str]:
    rows = _read_csv_rows(path, columns=columns)
    if len(rows) != 1:
        raise ValueError(f"CSV must contain exactly one row: {path}")
    return rows[0]


def _is_final_status(status: str) -> bool:
    return status in BRIDGE_FINAL_STATUSES


def _status_precedence(status: str) -> int:
    if status == BRIDGE_STATUS_PENDING:
        return 1
    if status == BRIDGE_STATUS_PROCESSING:
        return 2
    if status in BRIDGE_FINAL_STATUSES:
        return 3
    return 0


def _empty_state(now: datetime | None = None) -> dict[str, Any]:
    timestamp = (now or _now_jst()).isoformat(timespec="seconds")
    return {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "contract_id": CONTRACT_ID,
        "updated_at": timestamp,
        "records": {},
    }


def _state_path(root: Path) -> Path:
    return resolve_path(root, STATE_FILE)


def _outbox_directories(root: Path) -> dict[str, Path]:
    return {
        BRIDGE_STATUS_PENDING: resolve_path(root, PENDING_DIR),
        BRIDGE_STATUS_PROCESSING: resolve_path(root, PROCESSING_DIR),
        BRIDGE_STATUS_ACCEPTED: resolve_path(root, COMPLETE_DIR),
        BRIDGE_STATUS_REJECTED: resolve_path(root, REJECTED_DIR),
    }


def _state_record_from_outbox_file(path: Path, *, status: str) -> dict[str, Any]:
    row = _read_single_row_csv(path, columns=OUTBOX_COLUMNS)
    if row["schema_version"] != str(SCHEMA_VERSION):
        raise ValueError(f"Outbox schema version mismatch: {path}")
    if row["bridge_status"] != BRIDGE_STATUS_PENDING:
        raise ValueError(f"Outbox bridge_status must remain PENDING: {path}")
    if row["intent_id"] != path.stem:
        raise ValueError(f"Outbox filename does not match intent_id: {path}")
    if row["checksum"] != _checksum_fields(row, OUTBOX_COLUMNS):
        raise ValueError(f"Outbox checksum mismatch: {path}")
    return {
        "intent_id": row["intent_id"],
        "idempotency_key": row["idempotency_key"],
        "status": status,
        "generated_at": row["generated_at"],
        "expires_at": row["expires_at"],
        "ticker": row["ticker"],
        "market": row["market"],
        "side": row["side"],
        "order_type": row["order_type"],
        "quantity": row["quantity"],
        "reference_price": row["reference_price"],
        "limit_price": row["limit_price"],
        "stop_loss_price": row["stop_loss_price"],
        "take_profit_price": row["take_profit_price"],
        "estimated_notional": row["estimated_notional"],
        "estimated_max_loss": row["estimated_max_loss"],
        "trading_mode": row["trading_mode"],
        "execution_mode": row["execution_mode"],
        "bridge_status": row["bridge_status"],
        "checksum": row["checksum"],
        "outbox_file": str(path),
        "outbox_sha256": _file_sha256(path),
        "source_report_file": "",
        "source_report_sha256": "",
        "source_instruction_file": "",
        "source_instruction_sha256": "",
        "result": "",
        "reason_codes": [],
        "received_at": "",
        "vba_instance_id": "",
        "source_checksum": "",
        "receipt_file": "",
        "receipt_sha256": "",
        "updated_at": _now_jst().isoformat(timespec="seconds"),
    }


def _discover_state_from_files(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for status, directory in _outbox_directories(root).items():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.csv")):
            record = _state_record_from_outbox_file(path, status=status)
            intent_id = record["intent_id"]
            existing = records.get(intent_id)
            if existing is None:
                records[intent_id] = record
                continue
            if existing["checksum"] != record["checksum"]:
                raise ValueError(f"Conflicting outbox records discovered for {intent_id}")
            if _status_precedence(record["status"]) > _status_precedence(existing["status"]):
                records[intent_id] = record
    return records


def _save_bridge_state(root: Path, state: Mapping[str, Any]) -> None:
    path = _state_path(root)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "contract_id": CONTRACT_ID,
        "updated_at": state.get("updated_at", _now_jst().isoformat(timespec="seconds")),
        "records": state.get("records", {}),
    }
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_bridge_state(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    state_file = _state_path(root)
    if state_file.is_file():
        state = _read_json_strict(state_file)
        if int(state.get("schema_version", 0) or 0) != SCHEMA_VERSION:
            raise ValueError("Bridge state schema version is invalid")
        if str(state.get("contract_id", "")).strip() != CONTRACT_ID:
            raise ValueError("Bridge state contract id is invalid")
        records = state.get("records", {})
        if not isinstance(records, dict):
            raise ValueError("Bridge state records must be an object")
    else:
        state = _empty_state(now)
        records = state["records"]

    discovered = _discover_state_from_files(root)
    changed = False
    for intent_id, record in discovered.items():
        existing = records.get(intent_id)
        if existing is None:
            records[intent_id] = record
            changed = True
            continue
        if not isinstance(existing, dict):
            raise ValueError(f"Bridge state record is invalid for {intent_id}")
        existing_status = str(existing.get("status", "")).strip()
        discovered_status = str(record.get("status", "")).strip()
        if existing.get("checksum") and record.get("checksum") and existing.get("checksum") != record.get("checksum"):
            if _is_final_status(existing_status) and discovered_status == BRIDGE_STATUS_PENDING:
                raise ValueError(f"Bridge state conflicts with an existing final file: {intent_id}")
            if _is_final_status(discovered_status) and existing_status == BRIDGE_STATUS_PENDING:
                records[intent_id] = record
                changed = True
                continue
            raise ValueError(f"Bridge state checksum conflict for {intent_id}")
        if _status_precedence(discovered_status) > _status_precedence(existing_status):
            records[intent_id] = record
            changed = True
        elif discovered_status != existing_status and _status_precedence(discovered_status) == _status_precedence(existing_status):
            raise ValueError(f"Bridge state conflict for {intent_id}")
    state["records"] = records
    state["updated_at"] = (now or _now_jst()).isoformat(timespec="seconds")
    if changed or not state_file.is_file():
        _save_bridge_state(root, state)
    return state


def _fail_safe_blocker(root: Path) -> str | None:
    fail_safe_path = root / "logs" / "fail_safe.json"
    if not fail_safe_path.is_file():
        return None
    try:
        payload = _read_json_strict(fail_safe_path)
    except ValueError as error:
        return f"FAIL_SAFE_REPORT_INVALID: {error}"
    status = str(payload.get("status", "")).strip()
    if status == "FAIL_SAFE":
        return "FAIL_SAFE_ACTIVE"
    return None


def _parse_step42_source(root: Path, *, now: datetime) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    blockers: list[str] = []
    report_path = resolve_path(root, STEP42_REPORT_JSON_FILE)
    try:
        report = _read_json_strict(report_path)
    except (OSError, ValueError) as error:
        return {}, [], [f"STEP42_REPORT_INVALID: {type(error).__name__}: {error}"]
    report_blockers = report.get("blockers", [])
    if not isinstance(report_blockers, list):
        blockers.append("STEP42_BLOCKERS_INVALID")
    elif report_blockers:
        blockers.extend(f"STEP42:{_normalize_text(value)}" for value in report_blockers if _normalize_text(value))

    if int(report.get("schema_version", 0) or 0) != STEP42_SCHEMA_VERSION:
        blockers.append("STEP42_SCHEMA_VERSION_INVALID")
    if _normalize_text(report.get("status")).upper() != "APPROVED":
        blockers.append("STEP42_STATUS_NOT_APPROVED")
    if _normalize_text(report.get("mode")).upper() != STEP42_TRADING_MODE:
        blockers.append("STEP42_MODE_INVALID")
    if _normalize_text(report.get("trading_mode")).upper() != STEP42_TRADING_MODE:
        blockers.append("STEP42_TRADING_MODE_INVALID")
    if _normalize_text(report.get("execution_mode")).upper() != STEP42_EXECUTION_MODE:
        blockers.append("STEP42_EXECUTION_MODE_INVALID")
    if _normalize_text(report.get("trading_actions")).upper() not in {"PAPER_ONLY", "DISABLED"}:
        blockers.append("STEP42_TRADING_ACTIONS_INVALID")
    if _normalize_int(report.get("orders_submitted", 0), field="orders_submitted") != 0:
        blockers.append("STEP42_ORDERS_SUBMITTED_NONZERO")

    generated_at = _parse_jst_datetime(report.get("generated_at"), field="generated_at")
    expires_at = _parse_jst_datetime(report.get("expires_at"), field="expires_at")
    if now > expires_at:
        blockers.append("STEP42_EXPIRED")

    instruction_path = resolve_path(root, str(report.get("instruction_file", STEP42_INSTRUCTION_FILE)))
    if not instruction_path.is_file():
        blockers.append(f"STEP42_INSTRUCTION_FILE_MISSING: {instruction_path}")
        return report, [], blockers
    try:
        rows = _read_csv_rows(instruction_path, columns=STEP42_OUTPUT_COLUMNS)
    except (OSError, ValueError, csv.Error) as error:
        blockers.append(f"STEP42_INSTRUCTION_INVALID: {type(error).__name__}: {error}")
        return report, [], blockers

    if len(rows) != _normalize_int(report.get("approved_count", 0), field="approved_count"):
        blockers.append("STEP42_APPROVED_COUNT_MISMATCH")
    if _normalize_int(report.get("blocked_count", 0), field="blocked_count") != 0:
        blockers.append("STEP42_BLOCKED_ROWS_PRESENT")
    if any(_normalize_text(row.get("status")).upper() != "APPROVED" for row in rows):
        blockers.append("STEP42_ROW_STATUS_NOT_APPROVED")
    if any(not _normalize_text(row.get("intent_id")) or not _normalize_text(row.get("idempotency_key")) for row in rows):
        blockers.append("STEP42_ROW_IDENTITY_MISSING")
    if any(_normalize_text(row.get("bridge_status")).upper() == BRIDGE_STATUS_PENDING for row in rows):
        blockers.append("STEP42_ROW_CONTRACT_LEAKED")
    report["generated_at"] = generated_at.isoformat(timespec="seconds")
    report["expires_at"] = expires_at.isoformat(timespec="seconds")
    return report, rows, blockers


def _bridge_row_from_step42_row(
    row: Mapping[str, str],
    *,
    generated_at: str,
    expires_at: str,
) -> dict[str, str]:
    quantity = _normalize_int(row.get("quantity", 0), field="quantity")
    reference_price = _money_value(row.get("reference_price", 0), field="reference_price")
    limit_price = _money_value(row.get("limit_price", reference_price), field="limit_price")
    stop_loss_price = _money_value(row.get("stop_loss_price", 0), field="stop_loss_price")
    take_profit_price = _money_value(row.get("take_profit_price", 0), field="take_profit_price")
    estimated_notional = _money_value(
        row.get("estimated_notional", quantity * limit_price),
        field="estimated_notional",
    )
    estimated_max_loss = _money_value(
        row.get("estimated_max_loss", max(limit_price - stop_loss_price, 0.0) * quantity),
        field="estimated_max_loss",
    )
    payload = {
        "schema_version": str(SCHEMA_VERSION),
        "intent_id": _normalize_text(row.get("intent_id")),
        "idempotency_key": _normalize_text(row.get("idempotency_key")),
        "generated_at": generated_at,
        "expires_at": expires_at,
        "ticker": _normalize_text(row.get("ticker")),
        "market": _normalize_text(row.get("market")),
        "side": _normalize_text(row.get("side")).upper(),
        "order_type": _normalize_text(row.get("order_type")).upper(),
        "quantity": str(quantity),
        "reference_price": f"{reference_price:.2f}",
        "limit_price": f"{limit_price:.2f}",
        "stop_loss_price": f"{stop_loss_price:.2f}",
        "take_profit_price": f"{take_profit_price:.2f}",
        "estimated_notional": f"{estimated_notional:.2f}",
        "estimated_max_loss": f"{estimated_max_loss:.2f}",
        "trading_mode": TRADING_MODE,
        "execution_mode": EXECUTION_MODE,
        "bridge_status": BRIDGE_STATUS_PENDING,
    }
    payload["checksum"] = _checksum_fields(payload, OUTBOX_COLUMNS)
    return payload


def _receipt_payload_from_mapping(mapping: Mapping[str, Any]) -> dict[str, str]:
    payload = {
        "schema_version": str(SCHEMA_VERSION),
        "intent_id": _normalize_text(mapping.get("intent_id")),
        "idempotency_key": _normalize_text(mapping.get("idempotency_key")),
        "received_at": _normalize_text(mapping.get("received_at")),
        "result": _normalize_text(mapping.get("result")).upper(),
        "reason_codes": _normalize_text(mapping.get("reason_codes")),
        "vba_instance_id": _normalize_text(mapping.get("vba_instance_id")),
        "source_checksum": _normalize_text(mapping.get("source_checksum")).lower(),
        "orders_submitted": str(_normalize_int(mapping.get("orders_submitted", 0), field="orders_submitted")),
    }
    payload["checksum"] = _checksum_fields(payload, RECEIPT_COLUMNS)
    return payload


def _archive_outbox_file(path: Path, *, status: str) -> Path:
    if status == BRIDGE_STATUS_ACCEPTED:
        directory = path.parent.parent / "complete"
    else:
        directory = path.parent.parent / "rejected"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / path.name
    if destination != path:
        path.replace(destination)
    return destination


def _record_to_state(
    row: Mapping[str, str],
    *,
    status: str,
    outbox_path: Path,
    source_report_file: Path,
    source_report_sha256: str,
    source_instruction_file: Path,
    source_instruction_sha256: str,
    outbox_sha256: str,
    now: datetime,
) -> dict[str, Any]:
    return {
        "intent_id": row["intent_id"],
        "idempotency_key": row["idempotency_key"],
        "status": status,
        "generated_at": row["generated_at"],
        "expires_at": row["expires_at"],
        "ticker": row["ticker"],
        "market": row["market"],
        "side": row["side"],
        "order_type": row["order_type"],
        "quantity": row["quantity"],
        "reference_price": row["reference_price"],
        "limit_price": row["limit_price"],
        "stop_loss_price": row["stop_loss_price"],
        "take_profit_price": row["take_profit_price"],
        "estimated_notional": row["estimated_notional"],
        "estimated_max_loss": row["estimated_max_loss"],
        "trading_mode": row["trading_mode"],
        "execution_mode": row["execution_mode"],
        "bridge_status": row["bridge_status"],
        "checksum": row["checksum"],
        "outbox_file": str(outbox_path),
        "outbox_sha256": outbox_sha256,
        "source_report_file": str(source_report_file),
        "source_report_sha256": source_report_sha256,
        "source_instruction_file": str(source_instruction_file),
        "source_instruction_sha256": source_instruction_sha256,
        "result": "",
        "reason_codes": [],
        "received_at": "",
        "vba_instance_id": "",
        "source_checksum": "",
        "receipt_file": "",
        "receipt_sha256": "",
        "updated_at": now.isoformat(timespec="seconds"),
    }


def _write_audit(root: Path, entries: Sequence[Mapping[str, Any]]) -> None:
    audit_path = resolve_path(root, AUDIT_JSONL_FILE)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(audit_path, "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n")


def stage_bridge_outbox(
    root: Path,
    *,
    now: datetime | None = None,
    report: Mapping[str, Any] | None = None,
    rows: Sequence[Mapping[str, str]] | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = now or _now_jst()
    loaded_state = state if state is not None else _load_bridge_state(root, now=current)
    source_report = dict(report or {})
    source_rows = list(rows or [])
    blockers: list[str] = []
    if not source_report or not source_rows:
        source_report, source_rows, blockers = _parse_step42_source(root, now=current)
    report_path = resolve_path(root, STEP42_REPORT_JSON_FILE)
    instruction_path = resolve_path(root, str(source_report.get("instruction_file", STEP42_INSTRUCTION_FILE)))
    report_sha256 = _file_sha256(report_path) if report_path.is_file() else ""
    instruction_sha256 = _file_sha256(instruction_path) if instruction_path.is_file() else ""

    pending_dir = resolve_path(root, PENDING_DIR)
    processing_dir = resolve_path(root, PROCESSING_DIR)
    complete_dir = resolve_path(root, COMPLETE_DIR)
    rejected_dir = resolve_path(root, REJECTED_DIR)
    for directory in (pending_dir, processing_dir, complete_dir, rejected_dir):
        directory.mkdir(parents=True, exist_ok=True)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generated_at": current.isoformat(timespec="seconds"),
        "status": "READY" if not blockers else "BLOCKED",
        "mode": TRADING_MODE,
        "trading_mode": TRADING_MODE,
        "execution_mode": EXECUTION_MODE,
        "trading_actions": TRADING_ACTIONS,
        "orders_submitted": ORDERS_SUBMITTED,
        "pending_created_count": 0,
        "pending_skipped_count": 0,
        "blockers": list(dict.fromkeys(blockers)),
        "outbox_pending_dir": str(pending_dir),
        "outbox_processing_dir": str(processing_dir),
        "outbox_complete_dir": str(complete_dir),
        "outbox_rejected_dir": str(rejected_dir),
        "state_file": str(_state_path(root)),
        "source_report_file": str(report_path),
        "source_report_sha256": report_sha256,
        "source_instruction_file": str(instruction_path),
        "source_instruction_sha256": instruction_sha256,
        "created_by": CONTRACT_ID,
    }
    if blockers:
        _save_bridge_state(root, loaded_state)
        return summary

    try:
        _parse_jst_datetime(source_report.get("generated_at"), field="generated_at")
        expires_at = _parse_jst_datetime(source_report.get("expires_at"), field="expires_at")
    except ValueError as error:
        summary["blockers"].append(f"STEP42_REPORT_TIME_INVALID: {type(error).__name__}: {error}")
        summary["status"] = "BLOCKED"
        _save_bridge_state(root, loaded_state)
        return summary
    if current > expires_at:
        summary["blockers"].append("STEP42_EXPIRED")
        summary["status"] = "BLOCKED"
        _save_bridge_state(root, loaded_state)
        return summary

    if _normalize_text(source_report.get("status")).upper() != "APPROVED":
        summary["blockers"].append("STEP42_STATUS_NOT_APPROVED")
        summary["status"] = "BLOCKED"
        _save_bridge_state(root, loaded_state)
        return summary

    approved_rows = [row for row in source_rows if _normalize_text(row.get("status")).upper() == "APPROVED"]
    if not approved_rows:
        summary["blockers"].append("STEP42_NO_APPROVED_ROWS")
        summary["status"] = "BLOCKED"
        _save_bridge_state(root, loaded_state)
        return summary

    records: dict[str, Any] = loaded_state.setdefault("records", {})
    audit_entries: list[dict[str, Any]] = []
    for row in approved_rows:
        bridge_row = _bridge_row_from_step42_row(
            row,
            generated_at=source_report["generated_at"],
            expires_at=source_report["expires_at"],
        )
        intent_id = bridge_row["intent_id"]
        record = records.get(intent_id)
        if record is not None:
            existing_status = _normalize_text(record.get("status")).upper()
            existing_report_sha256 = _normalize_text(record.get("source_report_sha256"))
            existing_instruction_sha256 = _normalize_text(record.get("source_instruction_sha256"))
            if (
                existing_report_sha256
                and report_sha256
                and existing_report_sha256 != report_sha256
            ) or (
                existing_instruction_sha256
                and instruction_sha256
                and existing_instruction_sha256 != instruction_sha256
            ):
                summary["blockers"].append(f"STATE_LINEAGE_CONFLICT:{intent_id}")
                summary["status"] = "BLOCKED"
                continue
            if record.get("checksum") != bridge_row["checksum"]:
                summary["blockers"].append(f"STATE_CONFLICT:{intent_id}")
                summary["status"] = "BLOCKED"
                continue
            summary["pending_skipped_count"] += 1
            audit_entries.append(
                {
                    "kind": "outbox",
                    "intent_id": intent_id,
                    "idempotency_key": bridge_row["idempotency_key"],
                    "status": existing_status or BRIDGE_STATUS_PENDING,
                    "result": "DUPLICATE",
                    "reason_codes": ["STATE_ALREADY_EXISTS"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "checksum": bridge_row["checksum"],
                    "source_report_sha256": report_sha256,
                    "source_instruction_sha256": instruction_sha256,
                }
            )
            continue
        outbox_path = pending_dir / f"{intent_id}.csv"
        if outbox_path.exists():
            summary["pending_skipped_count"] += 1
            records[intent_id] = _record_to_state(
                bridge_row,
                status=BRIDGE_STATUS_PENDING,
                outbox_path=outbox_path,
                source_report_file=report_path,
                source_report_sha256=report_sha256,
                source_instruction_file=instruction_path,
                source_instruction_sha256=instruction_sha256,
                outbox_sha256=_file_sha256(outbox_path),
                now=current,
            )
            audit_entries.append(
                {
                    "kind": "outbox",
                    "intent_id": intent_id,
                    "idempotency_key": bridge_row["idempotency_key"],
                    "status": BRIDGE_STATUS_PENDING,
                    "result": "DUPLICATE",
                    "reason_codes": ["OUTBOX_FILE_ALREADY_EXISTS"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "checksum": bridge_row["checksum"],
                    "source_report_sha256": report_sha256,
                    "source_instruction_sha256": instruction_sha256,
                }
            )
            continue
        _csv_write_atomic(outbox_path, [bridge_row], OUTBOX_COLUMNS)
        outbox_sha256 = _file_sha256(outbox_path)
        records[intent_id] = _record_to_state(
            bridge_row,
            status=BRIDGE_STATUS_PENDING,
            outbox_path=outbox_path,
            source_report_file=report_path,
            source_report_sha256=report_sha256,
            source_instruction_file=instruction_path,
            source_instruction_sha256=instruction_sha256,
            outbox_sha256=outbox_sha256,
            now=current,
        )
        summary["pending_created_count"] += 1
        audit_entries.append(
            {
                "kind": "outbox",
                "intent_id": intent_id,
                "idempotency_key": bridge_row["idempotency_key"],
                "status": BRIDGE_STATUS_PENDING,
                "result": "CREATED",
                "reason_codes": [],
                "orders_submitted": ORDERS_SUBMITTED,
                "checksum": bridge_row["checksum"],
                "outbox_sha256": outbox_sha256,
                "source_report_sha256": report_sha256,
                "source_instruction_sha256": instruction_sha256,
            }
        )

    loaded_state["updated_at"] = current.isoformat(timespec="seconds")
    _save_bridge_state(root, loaded_state)
    if audit_entries:
        audit_entries.append(
            {
                "kind": "summary",
                "schema_version": SCHEMA_VERSION,
                "status": summary["status"],
                "generated_at": summary["generated_at"],
                "pending_created_count": summary["pending_created_count"],
                "pending_skipped_count": summary["pending_skipped_count"],
                "orders_submitted": ORDERS_SUBMITTED,
                "blockers": list(summary["blockers"]),
            }
        )
        _write_audit(root, audit_entries)
    return summary


def _parse_receipt_file(path: Path) -> dict[str, str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        row = _read_single_row_csv(path, columns=RECEIPT_COLUMNS)
        return row
    if suffix == ".json":
        payload = _read_json_strict(path)
        row = _receipt_payload_from_mapping(payload)
        return row
    raise ValueError(f"Unsupported receipt file type: {path}")


def _validate_receipt_row(row: Mapping[str, str]) -> None:
    if row["schema_version"] != str(SCHEMA_VERSION):
        raise ValueError("Receipt schema version is invalid")
    if not _normalize_text(row.get("intent_id")):
        raise ValueError("Receipt intent_id is missing")
    if not _normalize_text(row.get("idempotency_key")):
        raise ValueError("Receipt idempotency_key is missing")
    if not _normalize_text(row.get("vba_instance_id")):
        raise ValueError("Receipt vba_instance_id is missing")
    if _normalize_int(row.get("orders_submitted", 0), field="orders_submitted") != 0:
        raise ValueError("Receipt orders_submitted must be zero")
    if _normalize_text(row.get("result")).upper() not in ALLOWED_RESULTS:
        raise ValueError("Receipt result is invalid")
    if not _is_sha256(row.get("source_checksum")):
        raise ValueError("Receipt source_checksum is invalid")
    if not _is_sha256(row.get("checksum")):
        raise ValueError("Receipt checksum is invalid")
    if row["checksum"] != _checksum_fields(row, RECEIPT_COLUMNS):
        raise ValueError("Receipt checksum mismatch")
    _parse_jst_datetime(row.get("received_at"), field="received_at")


def _move_receipt_file(path: Path) -> None:
    if path.exists():
        path.unlink(missing_ok=True)


def ingest_bridge_receipts(
    root: Path,
    *,
    now: datetime | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = now or _now_jst()
    loaded_state = state if state is not None else _load_bridge_state(root, now=current)
    inbox_dir = resolve_path(root, INBOX_DIR)
    inbox_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generated_at": current.isoformat(timespec="seconds"),
        "status": "READY",
        "mode": TRADING_MODE,
        "trading_mode": TRADING_MODE,
        "execution_mode": EXECUTION_MODE,
        "trading_actions": TRADING_ACTIONS,
        "orders_submitted": ORDERS_SUBMITTED,
        "receipt_processed_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "duplicate_count": 0,
        "expired_count": 0,
        "corrupt_count": 0,
        "inbox_dir": str(inbox_dir),
        "state_file": str(_state_path(root)),
    }
    records: dict[str, Any] = loaded_state.setdefault("records", {})
    audit_entries: list[dict[str, Any]] = []
    receipt_paths = list(sorted(inbox_dir.glob("*.csv"))) + list(sorted(inbox_dir.glob("*.json")))
    for receipt_path in receipt_paths:
        tentative_intent_id = receipt_path.stem
        try:
            receipt_row = _parse_receipt_file(receipt_path)
            _validate_receipt_row(receipt_row)
        except Exception as error:
            summary["corrupt_count"] += 1
            record = records.get(tentative_intent_id)
            if record is not None:
                record["status"] = BRIDGE_STATUS_CORRUPT
                record["result"] = BRIDGE_STATUS_CORRUPT
                record["received_at"] = _now_jst().isoformat(timespec="seconds")
                record["receipt_file"] = str(receipt_path)
                record["receipt_sha256"] = _file_sha256(receipt_path) if receipt_path.is_file() else ""
                record["updated_at"] = current.isoformat(timespec="seconds")
            audit_entries.append(
                {
                    "kind": "receipt",
                    "intent_id": tentative_intent_id,
                    "status": BRIDGE_STATUS_CORRUPT,
                    "result": BRIDGE_STATUS_CORRUPT,
                    "reason_codes": ["RECEIPT_INVALID"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "source_file": str(receipt_path),
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            _move_receipt_file(receipt_path)
            continue

        intent_id = receipt_row["intent_id"]
        if intent_id != tentative_intent_id:
            summary["corrupt_count"] += 1
            record = records.get(intent_id) or records.get(tentative_intent_id)
            if record is not None:
                record["status"] = BRIDGE_STATUS_CORRUPT
                record["result"] = BRIDGE_STATUS_CORRUPT
                record["received_at"] = receipt_row["received_at"]
                record["reason_codes"] = ["INTENT_ID_MISMATCH"]
                record["receipt_file"] = str(receipt_path)
                record["receipt_sha256"] = _file_sha256(receipt_path)
                record["updated_at"] = current.isoformat(timespec="seconds")
            audit_entries.append(
                {
                    "kind": "receipt",
                    "intent_id": intent_id,
                    "status": BRIDGE_STATUS_CORRUPT,
                    "result": BRIDGE_STATUS_CORRUPT,
                    "reason_codes": ["INTENT_ID_MISMATCH"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "source_file": str(receipt_path),
                }
            )
            _move_receipt_file(receipt_path)
            continue

        record = records.get(intent_id)
        if record is None:
            summary["corrupt_count"] += 1
            audit_entries.append(
                {
                    "kind": "receipt",
                    "intent_id": intent_id,
                    "status": BRIDGE_STATUS_CORRUPT,
                    "result": BRIDGE_STATUS_CORRUPT,
                    "reason_codes": ["UNKNOWN_INTENT"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "source_file": str(receipt_path),
                }
            )
            _move_receipt_file(receipt_path)
            continue

        if _normalize_text(record.get("idempotency_key")) != receipt_row["idempotency_key"]:
            summary["corrupt_count"] += 1
            record["status"] = BRIDGE_STATUS_CORRUPT
            record["result"] = BRIDGE_STATUS_CORRUPT
            record["received_at"] = receipt_row["received_at"]
            record["reason_codes"] = ["IDEMPOTENCY_KEY_MISMATCH"]
            record["receipt_file"] = str(receipt_path)
            record["receipt_sha256"] = _file_sha256(receipt_path)
            record["updated_at"] = current.isoformat(timespec="seconds")
            _save_bridge_state(root, loaded_state)
            audit_entries.append(
                {
                    "kind": "receipt",
                    "intent_id": intent_id,
                    "status": BRIDGE_STATUS_CORRUPT,
                    "result": BRIDGE_STATUS_CORRUPT,
                    "reason_codes": ["IDEMPOTENCY_KEY_MISMATCH"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "source_file": str(receipt_path),
                }
            )
            _move_receipt_file(receipt_path)
            continue

        if receipt_row["source_checksum"] != _normalize_text(record.get("checksum")):
            summary["corrupt_count"] += 1
            record["status"] = BRIDGE_STATUS_CORRUPT
            record["result"] = BRIDGE_STATUS_CORRUPT
            record["received_at"] = receipt_row["received_at"]
            record["reason_codes"] = ["SOURCE_CHECKSUM_MISMATCH"]
            record["receipt_file"] = str(receipt_path)
            record["receipt_sha256"] = _file_sha256(receipt_path)
            record["updated_at"] = current.isoformat(timespec="seconds")
            _save_bridge_state(root, loaded_state)
            audit_entries.append(
                {
                    "kind": "receipt",
                    "intent_id": intent_id,
                    "status": BRIDGE_STATUS_CORRUPT,
                    "result": BRIDGE_STATUS_CORRUPT,
                    "reason_codes": ["SOURCE_CHECKSUM_MISMATCH"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "source_file": str(receipt_path),
                }
            )
            _move_receipt_file(receipt_path)
            continue

        if _normalize_text(record.get("status")).upper() in BRIDGE_FINAL_STATUSES:
            summary["duplicate_count"] += 1
            audit_entries.append(
                {
                    "kind": "receipt",
                    "intent_id": intent_id,
                    "status": BRIDGE_STATUS_DUPLICATE,
                    "result": BRIDGE_STATUS_DUPLICATE,
                    "reason_codes": ["ALREADY_FINAL"],
                    "orders_submitted": ORDERS_SUBMITTED,
                    "source_file": str(receipt_path),
                }
            )
            _move_receipt_file(receipt_path)
            continue

        record["status"] = BRIDGE_STATUS_PROCESSING
        record["updated_at"] = current.isoformat(timespec="seconds")
        _save_bridge_state(root, loaded_state)

        expected_source_checksum = _normalize_text(record.get("checksum"))
        if receipt_row["source_checksum"] != expected_source_checksum:
            final_status = BRIDGE_STATUS_CORRUPT
            reason_codes = ["SOURCE_CHECKSUM_MISMATCH"]
        else:
            try:
                expires_at = _parse_jst_datetime(record.get("expires_at"), field="expires_at")
                received_at = _parse_jst_datetime(receipt_row.get("received_at"), field="received_at")
            except ValueError as error:
                final_status = BRIDGE_STATUS_CORRUPT
                reason_codes = [f"RECEIPT_TIME_INVALID:{error}"]
            else:
                if received_at > expires_at or current > expires_at:
                    final_status = BRIDGE_STATUS_EXPIRED
                    reason_codes = ["EXPIRED"]
                else:
                    final_status = _normalize_text(receipt_row.get("result")).upper()
                    reason_codes = [code for code in _normalize_text(receipt_row.get("reason_codes")).split(";") if code]
                    if final_status not in ALLOWED_RESULTS:
                        final_status = BRIDGE_STATUS_CORRUPT
                        reason_codes = ["RESULT_INVALID"]

        if final_status == BRIDGE_STATUS_ACCEPTED:
            summary["accepted_count"] += 1
        elif final_status == BRIDGE_STATUS_REJECTED:
            summary["rejected_count"] += 1
        elif final_status == BRIDGE_STATUS_DUPLICATE:
            summary["duplicate_count"] += 1
        elif final_status == BRIDGE_STATUS_EXPIRED:
            summary["expired_count"] += 1
        else:
            summary["corrupt_count"] += 1

        record["status"] = final_status
        record["result"] = final_status
        record["reason_codes"] = list(dict.fromkeys(reason_codes))
        record["received_at"] = receipt_row["received_at"]
        record["vba_instance_id"] = receipt_row["vba_instance_id"]
        record["source_checksum"] = receipt_row["source_checksum"]
        record["receipt_file"] = str(receipt_path)
        record["receipt_sha256"] = _file_sha256(receipt_path)
        record["updated_at"] = current.isoformat(timespec="seconds")

        source_outbox = Path(record["outbox_file"])
        if source_outbox.exists():
            if source_outbox.parent.name == "pending":
                processing_path = source_outbox.parent.parent / "processing" / source_outbox.name
                processing_path.parent.mkdir(parents=True, exist_ok=True)
                source_outbox.replace(processing_path)
                record["outbox_file"] = str(processing_path)
                source_outbox = processing_path
            final_path = _archive_outbox_file(source_outbox, status=final_status)
            record["outbox_file"] = str(final_path)
            record["outbox_sha256"] = _file_sha256(final_path)
        _save_bridge_state(root, loaded_state)
        audit_entries.append(
            {
                "kind": "receipt",
                "intent_id": intent_id,
                "status": final_status,
                "result": final_status,
                "reason_codes": list(dict.fromkeys(reason_codes)),
                "orders_submitted": ORDERS_SUBMITTED,
                "source_checksum": receipt_row["source_checksum"],
                "vba_instance_id": receipt_row["vba_instance_id"],
                "source_file": str(receipt_path),
            }
        )
        summary["receipt_processed_count"] += 1
        _move_receipt_file(receipt_path)

    loaded_state["updated_at"] = current.isoformat(timespec="seconds")
    _save_bridge_state(root, loaded_state)
    if audit_entries:
        audit_entries.append(
            {
                "kind": "summary",
                "schema_version": SCHEMA_VERSION,
                "status": summary["status"],
                "generated_at": summary["generated_at"],
                "receipt_processed_count": summary["receipt_processed_count"],
                "accepted_count": summary["accepted_count"],
                "rejected_count": summary["rejected_count"],
                "duplicate_count": summary["duplicate_count"],
                "expired_count": summary["expired_count"],
                "corrupt_count": summary["corrupt_count"],
                "orders_submitted": ORDERS_SUBMITTED,
            }
        )
        _write_audit(root, audit_entries)
    return summary


def _merge_summary(base: dict[str, Any], extra: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if key.endswith("_count") and isinstance(value, int):
            merged[key] = int(merged.get(key, 0)) + value
        elif key == "blockers" and value:
            merged.setdefault(key, [])
            merged[key] = list(dict.fromkeys([*merged.get(key, []), *list(value)]))
        else:
            merged[key] = value
    return merged


def _status_from_summary(summary: Mapping[str, Any]) -> str:
    blockers = list(summary.get("blockers", []))
    return "BLOCKED" if blockers else "READY"


def run_vba_bridge_contract(
    root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or _now_jst()
    scope = _normalize_text(os.environ.get("PHOENIX_OPERATING_SCOPE", "")).upper()
    summary = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generated_at": current.isoformat(timespec="seconds"),
        "status": "READY",
        "mode": TRADING_MODE,
        "trading_mode": TRADING_MODE,
        "execution_mode": EXECUTION_MODE,
        "trading_actions": TRADING_ACTIONS,
        "orders_submitted": ORDERS_SUBMITTED,
        "blockers": [],
        "pending_created_count": 0,
        "pending_skipped_count": 0,
        "receipt_processed_count": 0,
        "accepted_count": 0,
        "rejected_count": 0,
        "duplicate_count": 0,
        "expired_count": 0,
        "corrupt_count": 0,
    }

    if scope not in ALLOWED_OPERATING_SCOPES:
        summary["blockers"].append("OPERATING_SCOPE_INVALID")
    elif scope == "MONITOR_ONLY":
        summary["blockers"].append("MONITOR_ONLY_SCOPE")

    fail_safe_reason = _fail_safe_blocker(root)
    if fail_safe_reason is not None:
        summary["blockers"].append(fail_safe_reason)

    try:
        report, rows, report_blockers = _parse_step42_source(root, now=current)
    except Exception as error:
        report, rows, report_blockers = {}, [], [f"STEP42_SOURCE_ERROR: {type(error).__name__}: {error}"]
    summary["blockers"].extend(report_blockers)

    state: dict[str, Any] | None = None
    if not summary["blockers"]:
        state = _load_bridge_state(root, now=current)
        stage_summary = stage_bridge_outbox(root, now=current, report=report, rows=rows, state=state)
        summary = _merge_summary(summary, stage_summary)
        if _status_from_summary(stage_summary) == "READY":
            receipt_summary = ingest_bridge_receipts(root, now=current, state=state)
            summary = _merge_summary(summary, receipt_summary)

    summary["status"] = _status_from_summary(summary)
    summary["outbox_pending_dir"] = str(resolve_path(root, PENDING_DIR))
    summary["outbox_processing_dir"] = str(resolve_path(root, PROCESSING_DIR))
    summary["outbox_complete_dir"] = str(resolve_path(root, COMPLETE_DIR))
    summary["outbox_rejected_dir"] = str(resolve_path(root, REJECTED_DIR))
    summary["inbox_dir"] = str(resolve_path(root, INBOX_DIR))
    summary["state_file"] = str(_state_path(root))
    summary["audit_jsonl"] = str(resolve_path(root, AUDIT_JSONL_FILE))
    summary["report_json"] = str(resolve_path(root, REPORT_JSON_FILE))
    summary["report_text"] = str(resolve_path(root, REPORT_TEXT_FILE))
    summary["step42_report_json"] = str(resolve_path(root, STEP42_REPORT_JSON_FILE))
    summary["step42_instruction_file"] = str(resolve_path(root, STEP42_INSTRUCTION_FILE))
    summary["source_report_sha256"] = _file_sha256(resolve_path(root, STEP42_REPORT_JSON_FILE)) if resolve_path(root, STEP42_REPORT_JSON_FILE).is_file() else ""
    summary["source_instruction_sha256"] = _file_sha256(resolve_path(root, STEP42_INSTRUCTION_FILE)) if resolve_path(root, STEP42_INSTRUCTION_FILE).is_file() else ""
    summary["created_by"] = CONTRACT_ID
    report_json_path = resolve_path(root, REPORT_JSON_FILE)
    report_text_path = resolve_path(root, REPORT_TEXT_FILE)
    atomic_write(report_json_path, json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    atomic_write(report_text_path, text_report(summary))
    return summary


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP43 VBA/RSS LOCAL BRIDGE CONTRACT",
        "=" * 92,
        f"Status               : {report.get('status', '')}",
        f"Mode                 : {report.get('mode', TRADING_MODE)}",
        f"Trading mode         : {report.get('trading_mode', TRADING_MODE)}",
        f"Execution mode       : {report.get('execution_mode', EXECUTION_MODE)}",
        f"Trading actions      : {report.get('trading_actions', TRADING_ACTIONS)}",
        f"Orders submitted     : {report.get('orders_submitted', 0)}",
        f"Pending created      : {report.get('pending_created_count', 0)}",
        f"Pending skipped      : {report.get('pending_skipped_count', 0)}",
        f"Receipts processed   : {report.get('receipt_processed_count', 0)}",
        f"Accepted / rejected  : {report.get('accepted_count', 0)} / {report.get('rejected_count', 0)}",
        f"Duplicate / expired   : {report.get('duplicate_count', 0)} / {report.get('expired_count', 0)}",
        f"Corrupt              : {report.get('corrupt_count', 0)}",
        f"Outbox pending       : {report.get('outbox_pending_dir', '')}",
        f"Outbox processing    : {report.get('outbox_processing_dir', '')}",
        f"Outbox complete      : {report.get('outbox_complete_dir', '')}",
        f"Outbox rejected      : {report.get('outbox_rejected_dir', '')}",
        f"Inbox                : {report.get('inbox_dir', '')}",
        f"State file           : {report.get('state_file', '')}",
        "-" * 92,
    ]
    blockers = list(report.get("blockers", []))
    if blockers:
        lines.extend(["Blocking reasons:"] + [f"  - {value}" for value in blockers])
    else:
        lines.append("Blocking reasons: none")
    lines.extend(
        [
            "-" * 92,
            "ACCEPTED means VBA validated the handoff only; it never submits orders.",
            "Orders submitted: 0",
            "=" * 92,
            "",
        ]
    )
    return "\n".join(lines)


def print_bridge_summary(report: Mapping[str, Any]) -> None:
    print("=" * 92)
    print("PHOENIX v7 STEP43 VBA/RSS LOCAL BRIDGE CONTRACT")
    print("=" * 92)
    print(f"Status               : {report.get('status', '')}")
    print(f"Trading mode         : {report.get('trading_mode', TRADING_MODE)}")
    print(f"Execution mode       : {report.get('execution_mode', EXECUTION_MODE)}")
    print(f"Trading actions      : {report.get('trading_actions', TRADING_ACTIONS)}")
    print(f"Pending created      : {report.get('pending_created_count', 0)}")
    print(f"Receipts processed   : {report.get('receipt_processed_count', 0)}")
    print(f"Orders submitted     : {report.get('orders_submitted', 0)}")
    print(f"Outbox pending       : {report.get('outbox_pending_dir', '')}")
    print(f"State file           : {report.get('state_file', '')}")
    print("=" * 92)
