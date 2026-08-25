from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import csv
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from phoenix_core.data_freshness import JST
from phoenix_core.performance_tracker import atomic_write


SCHEMA_VERSION = 1
BRIDGE_ROOT_DIR = "runtime/v7_rss_production/order_bridge"
PENDING_DIR = f"{BRIDGE_ROOT_DIR}/outbox/pending"
PROCESSING_DIR = f"{BRIDGE_ROOT_DIR}/outbox/processing"
PROCESSED_DIR = f"{BRIDGE_ROOT_DIR}/outbox/processed"
FAILED_DIR = f"{BRIDGE_ROOT_DIR}/outbox/failed"
COMPLETE_DIR = PROCESSED_DIR
REJECTED_DIR = FAILED_DIR
INBOX_DIR = f"{BRIDGE_ROOT_DIR}/inbox"
STATE_FILE = "state/v7_rss_production_order_bridge_state.json"

REQUEST_COLUMNS = [
    "schema_version",
    "request_id",
    "request_kind",
    "broker_order_id",
    "client_order_id",
    "strategy_name",
    "ticker",
    "side",
    "quantity",
    "order_type",
    "limit_price",
    "target_price",
    "stop_price",
    "stop_trigger_price",
    "order_category",
    "execution_condition",
    "expiration",
    "trigger_condition",
    "post_trigger_order_type",
    "live_trading_enabled",
    "production_transport_enabled",
    "armed",
    "submitted_at",
    "timeout_seconds",
    "macro_name",
    "message",
    "bridge_status",
    "payload_sha256",
    "checksum",
]

RECEIPT_COLUMNS = [
    "schema_version",
    "request_id",
    "request_kind",
    "broker_order_id",
    "client_order_id",
    "bridge_status",
    "result",
    "rss_order_status",
    "rss_order_number",
    "ticker",
    "quantity",
    "target_price",
    "stop_price",
    "expiration",
    "timestamp",
    "message",
    "error_code",
    "error_message",
    "fill_quantity",
    "fill_price",
    "orders_submitted",
    "request_checksum",
    "checksum",
]

FINAL_RESULTS = {"ACCEPTED", "REJECTED", "CANCELED", "TIMED_OUT", "DUPLICATE", "EXPIRED", "CORRUPT"}


def _now_jst() -> datetime:
    return datetime.now(JST)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    import hashlib

    return hashlib.sha256(encoded).hexdigest()


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
            import os

            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _read_csv_row(path: Path, *, columns: Sequence[str]) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw, newline=""), strict=True)
    header = tuple(reader.fieldnames or ())
    if header != tuple(columns):
        raise ValueError(f"CSV columns do not match bridge contract: {path}")
    rows = list(reader)
    if len(rows) != 1:
        raise ValueError(f"CSV must contain exactly one row: {path}")
    row = rows[0]
    return {column: _normalize_text(row.get(column)) for column in columns}


def _state_path(root: Path) -> Path:
    return Path(root) / STATE_FILE


def _load_state(root: Path) -> dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": _now_jst().isoformat(timespec="seconds"),
            "requests": {},
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read order bridge state: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Order bridge state root is not an object: {path}")
    requests = payload.get("requests", {})
    if not isinstance(requests, dict):
        raise ValueError(f"Order bridge state requests are invalid: {path}")
    payload["requests"] = requests
    return payload


def _save_state(root: Path, state: Mapping[str, Any]) -> None:
    path = _state_path(root)
    payload = dict(state)
    payload["schema_version"] = SCHEMA_VERSION
    payload["updated_at"] = _now_jst().isoformat(timespec="seconds")
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _request_path(root: Path, request_id: str, request_kind: str) -> Path:
    folder = Path(root) / PENDING_DIR
    folder.mkdir(parents=True, exist_ok=True)
    _ = request_kind
    return folder / f"{request_id}.csv"


def _receipt_path(root: Path, request_id: str, request_kind: str) -> Path:
    folder = Path(root) / INBOX_DIR
    folder.mkdir(parents=True, exist_ok=True)
    _ = request_kind
    return folder / f"{request_id}.csv"


def _write_request_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    row = {column: payload.get(column, "") for column in REQUEST_COLUMNS}
    row["schema_version"] = SCHEMA_VERSION
    row["bridge_status"] = _normalize_text(row.get("bridge_status")) or "PENDING"
    row["payload_sha256"] = _normalize_text(row.get("payload_sha256"))
    row["checksum"] = _stable_hash(
        {column: _normalize_text(row.get(column, "")) for column in REQUEST_COLUMNS if column != "checksum"}
    )
    return row


def _request_state_from_row(
    *,
    request_id: str,
    request_kind: str,
    request_file: Path,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "request_kind": request_kind,
        "request_file": str(request_file),
        "request_hash": _normalize_text(row.get("checksum")),
        "bridge_status": _normalize_text(row.get("bridge_status")) or "PENDING",
        "broker_order_id": _normalize_text(row.get("broker_order_id")),
        "client_order_id": _normalize_text(row.get("client_order_id")),
        "submitted_at": _normalize_text(row.get("submitted_at")),
        "received_at": "",
        "receipt_file": "",
        "receipt_hash": "",
        "result": "",
        "message": _normalize_text(row.get("message")),
        "rss_order_status": "",
        "request_row": {column: _normalize_text(row.get(column)) for column in REQUEST_COLUMNS},
    }


@dataclass(frozen=True, slots=True)
class FileBridgeStageResult:
    request_id: str
    request_kind: str
    request_file: Path
    request_hash: str
    bridge_status: str
    staged_at: datetime
    duplicate: bool = False


@dataclass(frozen=True, slots=True)
class FileBridgeReceipt:
    request_id: str
    request_kind: str
    broker_order_id: str
    client_order_id: str
    bridge_status: str
    result: str
    rss_order_status: str
    rss_order_number: str
    ticker: str
    quantity: int
    target_price: float
    stop_price: float
    expiration: str
    received_at: datetime
    message: str
    error_code: str
    error_message: str
    fill_quantity: int
    fill_price: float
    orders_submitted: int
    request_checksum: str
    receipt_file: Path
    checksum: str


def stage_request(
    root: Path,
    *,
    request_id: str,
    request_kind: str,
    payload: Mapping[str, Any],
    now: datetime | None = None,
) -> FileBridgeStageResult:
    current = now or _now_jst()
    request_kind = request_kind.upper().strip()
    if request_kind not in {"SUBMIT", "CANCEL"}:
        raise ValueError(f"Unsupported request_kind: {request_kind}")

    request_file = _request_path(root, request_id, request_kind)
    row = _write_request_row(
        {
            **payload,
            "request_id": request_id,
            "request_kind": request_kind,
            "bridge_status": "PENDING",
        }
    )

    state = _load_state(root)
    requests = state.setdefault("requests", {})
    existing = requests.get(request_id)
    if isinstance(existing, dict):
        existing_hash = _normalize_text(existing.get("request_hash"))
        if existing_hash and existing_hash != row["checksum"]:
            raise ValueError(f"Conflicting request payload for request_id: {request_id}")
        if not request_file.is_file():
            _csv_write_atomic(request_file, [row], REQUEST_COLUMNS)
        return FileBridgeStageResult(
            request_id=request_id,
            request_kind=request_kind,
            request_file=request_file,
            request_hash=row["checksum"],
            bridge_status="PENDING",
            staged_at=current,
            duplicate=True,
        )

    _csv_write_atomic(request_file, [row], REQUEST_COLUMNS)
    requests[request_id] = _request_state_from_row(
        request_id=request_id,
        request_kind=request_kind,
        request_file=request_file,
        row=row,
    )
    _save_state(root, state)
    return FileBridgeStageResult(
        request_id=request_id,
        request_kind=request_kind,
        request_file=request_file,
        request_hash=row["checksum"],
        bridge_status="PENDING",
        staged_at=current,
        duplicate=False,
    )


def read_receipt(
    root: Path,
    *,
    request_id: str,
    request_kind: str,
    now: datetime | None = None,
) -> FileBridgeReceipt | None:
    _ = now or _now_jst()
    request_kind = request_kind.upper().strip()
    if request_kind not in {"SUBMIT", "CANCEL"}:
        raise ValueError(f"Unsupported request_kind: {request_kind}")
    receipt_file = _receipt_path(root, request_id, request_kind)
    if not receipt_file.is_file():
        return None

    row = _read_csv_row(receipt_file, columns=RECEIPT_COLUMNS)
    if row["request_id"] != request_id:
        raise ValueError(f"Receipt request_id mismatch: {receipt_file}")
    if row["request_kind"].upper() != request_kind:
        raise ValueError(f"Receipt request_kind mismatch: {receipt_file}")

    received_at = datetime.fromisoformat(row["timestamp"]).astimezone(JST)
    receipt = FileBridgeReceipt(
        request_id=request_id,
        request_kind=request_kind,
        broker_order_id=row["broker_order_id"],
        client_order_id=row["client_order_id"],
        bridge_status=row["bridge_status"].upper(),
        result=row["result"].upper(),
        rss_order_status=row["rss_order_status"],
        rss_order_number=row["rss_order_number"],
        ticker=row["ticker"],
        quantity=int(row["quantity"] or 0),
        target_price=float(row["target_price"] or 0.0),
        stop_price=float(row["stop_price"] or 0.0),
        expiration=row["expiration"],
        received_at=received_at,
        message=row["message"],
        error_code=row["error_code"],
        error_message=row["error_message"] or row["message"],
        fill_quantity=int(row["fill_quantity"] or 0),
        fill_price=float(row["fill_price"] or 0.0),
        orders_submitted=int(row["orders_submitted"] or 0),
        request_checksum=row["request_checksum"],
        receipt_file=receipt_file,
        checksum=row["checksum"],
    )

    state = _load_state(root)
    requests = state.setdefault("requests", {})
    record = requests.get(request_id)
    if isinstance(record, dict):
        record["timestamp"] = row["timestamp"]
        record["received_at"] = row["timestamp"]
        record["receipt_file"] = str(receipt_file)
        record["receipt_hash"] = row["checksum"]
        record["result"] = receipt.result
        record["message"] = receipt.message
        record["rss_order_status"] = receipt.rss_order_status
        record["bridge_status"] = receipt.bridge_status
        _save_state(root, state)
    return receipt


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _normalize_text(value).upper()
    return text in {"1", "TRUE", "YES", "Y", "ON", "READY", "CONNECTED", "PASS"}


def _request_checksum(row: Mapping[str, Any]) -> str:
    return _stable_hash({column: _normalize_text(row.get(column, "")) for column in REQUEST_COLUMNS if column != "checksum"})


def _request_is_duplicate(state: Mapping[str, Any], request_id: str, request_hash: str) -> bool:
    requests = state.get("requests", {})
    if not isinstance(requests, Mapping):
        return False
    existing = requests.get(request_id)
    if not isinstance(existing, Mapping):
        return False
    existing_hash = _normalize_text(existing.get("request_hash"))
    if not existing_hash:
        return False
    existing_result = _normalize_text(existing.get("result")).upper()
    return existing_hash == request_hash and existing_result in FINAL_RESULTS


def _request_row_for_receipt(row: Mapping[str, Any]) -> dict[str, Any]:
    return {column: _normalize_text(row.get(column)) for column in REQUEST_COLUMNS}


def _find_submit_context(
    state: Mapping[str, Any],
    *,
    broker_order_id: str,
    client_order_id: str,
) -> Mapping[str, Any] | None:
    requests = state.get("requests", {})
    if not isinstance(requests, Mapping):
        return None
    for record in requests.values():
        if not isinstance(record, Mapping):
            continue
        if _normalize_text(record.get("request_kind")).upper() != "SUBMIT":
            continue
        if _normalize_text(record.get("broker_order_id")) == broker_order_id:
            return record
        if _normalize_text(record.get("client_order_id")) == client_order_id:
            return record
    return None


def _receipt_row_from_request(
    *,
    row: Mapping[str, Any],
    received_at: datetime,
    bridge_status: str,
    result: str,
    rss_order_status: str,
    rss_order_number: str,
    error_code: str = "",
    error_message: str = "",
    message: str = "",
    fill_quantity: int = 0,
    fill_price: float = 0.0,
    orders_submitted: int = 0,
) -> dict[str, Any]:
    receipt_row: dict[str, Any] = {column: "" for column in RECEIPT_COLUMNS}
    receipt_row.update(
        {
            "schema_version": SCHEMA_VERSION,
            "request_id": _normalize_text(row.get("request_id")),
            "request_kind": _normalize_text(row.get("request_kind")).upper(),
            "broker_order_id": _normalize_text(row.get("broker_order_id")),
            "client_order_id": _normalize_text(row.get("client_order_id")),
            "bridge_status": bridge_status.upper(),
            "result": result.upper(),
            "rss_order_status": rss_order_status,
            "rss_order_number": rss_order_number,
            "ticker": _normalize_text(row.get("ticker")),
            "quantity": _normalize_text(row.get("quantity")),
            "target_price": _normalize_text(row.get("target_price")),
            "stop_price": _normalize_text(row.get("stop_price")),
            "expiration": _normalize_text(row.get("expiration")),
            "timestamp": received_at.isoformat(timespec="seconds"),
            "message": message or error_message or result,
            "error_code": error_code,
            "error_message": error_message or message,
            "fill_quantity": fill_quantity,
            "fill_price": f"{fill_price:.2f}",
            "orders_submitted": orders_submitted,
            "request_checksum": _normalize_text(row.get("checksum")),
        }
    )
    receipt_row["checksum"] = _stable_hash({column: receipt_row.get(column, "") for column in RECEIPT_COLUMNS if column != "checksum"})
    return receipt_row


def _move_request_file(request_file: Path, *, status: str) -> Path:
    archive_dir = PROCESSED_DIR if status == "processed" else FAILED_DIR
    destination = request_file.parent.parent / Path(archive_dir).name / request_file.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    request_file.replace(destination)
    return destination


def _receipt_path_from_request(root: Path, request_id: str) -> Path:
    folder = Path(root) / INBOX_DIR
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{request_id}.csv"


def process_pending_requests(
    root: Path,
    *,
    ready_state: Mapping[str, Any],
    now: datetime | None = None,
) -> dict[str, int]:
    current = now or _now_jst()
    root = Path(root)
    pending_dir = root / PENDING_DIR
    pending_dir.mkdir(parents=True, exist_ok=True)
    state = _load_state(root)
    requests = state.setdefault("requests", {})
    summary = {
        "pending_count": 0,
        "processed_count": 0,
        "failed_count": 0,
        "duplicate_count": 0,
    }

    pending_files: list[tuple[datetime, Path, dict[str, str]]] = []
    for request_file in sorted(pending_dir.glob("*.csv")):
        try:
            row = _read_csv_row(request_file, columns=REQUEST_COLUMNS)
            request_time = datetime.fromisoformat(row["submitted_at"]).astimezone(JST)
        except Exception:
            row = {}
            request_time = current
        pending_files.append((request_time, request_file, row))

    def _request_sort_key(item: tuple[datetime, Path, dict[str, str]]) -> tuple[datetime, int, str]:
        request_time, request_file, request_row = item
        request_kind = _normalize_text(request_row.get("request_kind")).upper()
        kind_priority = 0 if request_kind == "SUBMIT" else 1
        return (request_time, kind_priority, request_file.name)

    pending_files.sort(key=_request_sort_key)
    bridge_ready = all(
        _truthy(ready_state.get(key))
        for key in ("heartbeat_alive", "rss_connected", "add_in_ready", "order_transport_ready")
    )

    for _, request_file, row in pending_files:
        request_id = _normalize_text(row.get("request_id")) or request_file.stem
        request_kind = _normalize_text(row.get("request_kind")).upper()
        request_hash = _request_checksum(row) if row else ""
        receipt_path = _receipt_path_from_request(root, request_id)

        if not row:
            summary["failed_count"] += 1
            receipt_row = _receipt_row_from_request(
                row={"request_id": request_id, "request_kind": request_kind, "broker_order_id": "", "client_order_id": ""},
                received_at=current,
                bridge_status="REJECTED",
                result="REJECTED",
                rss_order_status="CORRUPT",
                rss_order_number="",
                error_code="REQUEST_READ_FAILED",
                error_message=f"Could not read request CSV: {request_file.name}",
                message="request read failed",
            )
            _csv_write_atomic(receipt_path, [receipt_row], RECEIPT_COLUMNS)
            moved_path = _move_request_file(request_file, status="failed")
            record = requests.get(request_id)
            if isinstance(record, dict):
                record["bridge_status"] = "REJECTED"
                record["result"] = "REJECTED"
                record["error_code"] = "REQUEST_READ_FAILED"
                record["error_message"] = receipt_row["error_message"]
                record["receipt_file"] = str(receipt_path)
                record["request_file"] = str(moved_path)
            else:
                requests[request_id] = {
                    "request_id": request_id,
                    "request_kind": request_kind,
                    "request_hash": request_hash,
                    "bridge_status": "REJECTED",
                    "result": "REJECTED",
                    "error_code": "REQUEST_READ_FAILED",
                    "error_message": receipt_row["error_message"],
                    "request_file": str(moved_path),
                    "receipt_file": str(receipt_path),
                }
            continue

        try:
            if row["checksum"] != request_hash:
                raise ValueError("Request checksum mismatch")
            if request_kind not in {"SUBMIT", "CANCEL"}:
                raise ValueError(f"Unsupported request_kind: {request_kind}")

            if _request_is_duplicate(state, request_id, request_hash):
                summary["duplicate_count"] += 1
                receipt_row = _receipt_row_from_request(
                    row=row,
                    received_at=current,
                    bridge_status="REJECTED",
                    result="REJECTED",
                    rss_order_status="DUPLICATE",
                    rss_order_number=_normalize_text(row.get("broker_order_id")),
                    error_code="DUPLICATE_REQUEST_ID",
                    error_message="Duplicate request_id with matching checksum",
                    message="duplicate request",
                )
                _csv_write_atomic(receipt_path, [receipt_row], RECEIPT_COLUMNS)
                moved_path = _move_request_file(request_file, status="processed")
                request_row = _request_row_for_receipt(row)
                record = requests.get(request_id)
                if isinstance(record, dict):
                    record["duplicate_receipt_file"] = str(receipt_path)
                    record["duplicate_seen_at"] = receipt_row["timestamp"]
                    record["duplicate_error_code"] = "DUPLICATE_REQUEST_ID"
                    record["duplicate_error_message"] = receipt_row["error_message"]
                    record["request_file"] = str(moved_path)
                else:
                    requests[request_id] = {
                        "request_id": request_id,
                        "request_kind": request_kind,
                        "request_hash": request_hash,
                        "bridge_status": "REJECTED",
                        "result": "REJECTED",
                        "error_code": "DUPLICATE_REQUEST_ID",
                        "error_message": receipt_row["error_message"],
                        "request_row": request_row,
                        "request_file": str(moved_path),
                        "receipt_file": str(receipt_path),
                        "broker_order_id": request_row.get("broker_order_id", ""),
                        "client_order_id": request_row.get("client_order_id", ""),
                        "submitted_at": request_row.get("submitted_at", ""),
                        "received_at": receipt_row["timestamp"],
                        "timestamp": receipt_row["timestamp"],
                        "rss_order_status": receipt_row["rss_order_status"],
                    }
                continue

            if not bridge_ready:
                summary["failed_count"] += 1
                receipt_row = _receipt_row_from_request(
                    row=row,
                    received_at=current,
                    bridge_status="REJECTED",
                    result="REJECTED",
                    rss_order_status="DISCONNECTED",
                    rss_order_number=_normalize_text(row.get("broker_order_id")),
                    error_code="READY_STATE_FALSE",
                    error_message="heartbeat/rss/add-in/order transport not ready",
                    message="bridge not ready",
                )
                _csv_write_atomic(receipt_path, [receipt_row], RECEIPT_COLUMNS)
                moved_path = _move_request_file(request_file, status="failed")
                request_row = _request_row_for_receipt(row)
                requests[request_id] = {
                    "request_id": request_id,
                    "request_kind": request_kind,
                    "request_hash": request_hash,
                    "bridge_status": "REJECTED",
                    "result": "REJECTED",
                    "error_code": "READY_STATE_FALSE",
                    "error_message": receipt_row["error_message"],
                    "request_row": request_row,
                    "request_file": str(moved_path),
                    "receipt_file": str(receipt_path),
                    "broker_order_id": request_row.get("broker_order_id", ""),
                    "client_order_id": request_row.get("client_order_id", ""),
                    "submitted_at": request_row.get("submitted_at", ""),
                    "received_at": receipt_row["timestamp"],
                    "timestamp": receipt_row["timestamp"],
                    "rss_order_status": receipt_row["rss_order_status"],
                }
                continue

            if request_kind == "SUBMIT":
                summary["processed_count"] += 1
                receipt_row = _receipt_row_from_request(
                    row=row,
                    received_at=current,
                    bridge_status="ACCEPTED",
                    result="ACCEPTED",
                    rss_order_status="有効",
                    rss_order_number=_normalize_text(row.get("broker_order_id")),
                    message="submit accepted",
                    orders_submitted=0,
                )
                archive_status = "processed"
            else:
                submit_context = _find_submit_context(
                    state,
                    broker_order_id=_normalize_text(row.get("broker_order_id")),
                    client_order_id=_normalize_text(row.get("client_order_id")),
                )
                if submit_context is None:
                    raise ValueError("RELATED_SUBMIT_NOT_FOUND")
                related_row = submit_context.get("request_row", {})
                if not isinstance(related_row, Mapping):
                    related_row = {}
                merged_row = dict(row)
                for field in ("ticker", "quantity", "target_price", "stop_price", "expiration"):
                    if not _normalize_text(merged_row.get(field)):
                        merged_row[field] = _normalize_text(related_row.get(field))
                summary["processed_count"] += 1
                receipt_row = _receipt_row_from_request(
                    row=merged_row,
                    received_at=current,
                    bridge_status="ACCEPTED",
                    result="CANCELED",
                    rss_order_status="無効",
                    rss_order_number=_normalize_text(row.get("broker_order_id")),
                    message="cancel accepted",
                    orders_submitted=0,
                )
                archive_status = "processed"

            _csv_write_atomic(receipt_path, [receipt_row], RECEIPT_COLUMNS)
            moved_path = _move_request_file(request_file, status=archive_status)
            request_row = _request_row_for_receipt(row)
            requests[request_id] = {
                "request_id": request_id,
                "request_kind": request_kind,
                "request_hash": request_hash,
                "bridge_status": receipt_row["bridge_status"],
                "result": receipt_row["result"],
                "error_code": receipt_row["error_code"],
                "error_message": receipt_row["error_message"],
                "request_row": request_row,
                "request_file": str(moved_path),
                "receipt_file": str(receipt_path),
                "broker_order_id": request_row.get("broker_order_id", ""),
                "client_order_id": request_row.get("client_order_id", ""),
                "submitted_at": request_row.get("submitted_at", ""),
                "received_at": receipt_row["timestamp"],
                "timestamp": receipt_row["timestamp"],
                "rss_order_status": receipt_row["rss_order_status"],
                "rss_order_number": receipt_row["rss_order_number"],
            }
        except Exception as error:
            summary["failed_count"] += 1
            error_message = str(error)
            receipt_row = _receipt_row_from_request(
                row=row or {"request_id": request_id, "request_kind": request_kind, "broker_order_id": "", "client_order_id": ""},
                received_at=current,
                bridge_status="REJECTED",
                result="REJECTED",
                rss_order_status="CORRUPT",
                rss_order_number=_normalize_text((row or {}).get("broker_order_id")),
                error_code=type(error).__name__.upper(),
                error_message=error_message,
                message="processing failed",
            )
            _csv_write_atomic(receipt_path, [receipt_row], RECEIPT_COLUMNS)
            moved_path = _move_request_file(request_file, status="failed")
            request_row = _request_row_for_receipt(row or {"request_id": request_id, "request_kind": request_kind, "broker_order_id": "", "client_order_id": ""})
            requests[request_id] = {
                "request_id": request_id,
                "request_kind": request_kind,
                "request_hash": request_hash,
                "bridge_status": "REJECTED",
                "result": "REJECTED",
                "error_code": receipt_row["error_code"],
                "error_message": error_message,
                "request_row": request_row,
                "request_file": str(moved_path),
                "receipt_file": str(receipt_path),
                "broker_order_id": request_row.get("broker_order_id", ""),
                "client_order_id": request_row.get("client_order_id", ""),
                "submitted_at": request_row.get("submitted_at", ""),
                "received_at": receipt_row["timestamp"],
                "timestamp": receipt_row["timestamp"],
                "rss_order_status": receipt_row["rss_order_status"],
                "rss_order_number": receipt_row["rss_order_number"],
            }

    _save_state(root, state)
    summary["pending_count"] = len(pending_files)
    return summary


def ensure_request_columns() -> tuple[str, ...]:
    return tuple(REQUEST_COLUMNS)


def ensure_receipt_columns() -> tuple[str, ...]:
    return tuple(RECEIPT_COLUMNS)
