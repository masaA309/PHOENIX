from __future__ import annotations

import csv
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
from contextlib import contextmanager
from typing import Any, Mapping

from phoenix_core.data_freshness import (
    JPX_CALENDAR_SHA256,
    JST,
    is_jpx_equities_trading_day,
    ticker_universe_sha256,
)
from phoenix_core.candidate_input_guard import (
    CandidateInputPolicy,
    load_execution_candidates,
)
from phoenix_core.performance_tracker import atomic_write, resolve_path


CONTRACT_ID = "PHOENIX_RSS_SHADOW_V1"
SOURCE_ID = "RAKUTEN_MARKETSPEED_II_RSS"
EXPORTER_ID = "PHOENIX_EXCEL_VBA_SHADOW"
WORKBOOK_CONTRACT_VERSION = "1"
REPORT_VERSION = "PHOENIX v7 Step20"
TICKER_PATTERN = re.compile(r"^[1-9][0-9ACDFGHJKLMNPRSTUWXY][0-9][0-9ACDFGHJKLMNPRSTUWXY]\.T$")
CAPTURE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
SESSION_START = time(9, 0)
MORNING_END = time(11, 30)
AFTERNOON_START = time(12, 30)
SESSION_END = time(15, 30)
FINAL_SAMPLE_START = time(14, 30)
HARD_MAXIMUM_SNAPSHOT_BYTES = 2_000_000
DEFAULT_MAXIMUM_EVIDENCE_BYTES = 4_000_000
HARD_MAXIMUM_WORKBOOK_BYTES = 50_000_000
HARD_MAXIMUM_VBA_PROJECT_BYTES = 10_000_000
HARD_MAXIMUM_WORKBOOK_XML_BYTES = 10_000_000
FORBIDDEN_WORKBOOK_TOKENS = (
    "rssstockorder",
    "rssmargin",
    "rsscancel",
    "rssmodify",
    "application.run",
    "auto_open",
    "workbook_open",
    "shell(",
    "rss_order_queue",
    "execution/order_book",
    "powershell",
    "winhttp",
    "xmlhttp",
)
SNAPSHOT_COLUMNS = (
    "schema_version",
    "contract_id",
    "source",
    "exporter",
    "workbook_contract_version",
    "read_only",
    "orders_allowed",
    "external_orders_submitted",
    "capture_id",
    "sequence",
    "exported_at",
    "ticker",
    "current_price",
    "bid",
    "ask",
    "volume",
    "trading_status",
    "quote_timestamp",
    "bid_timestamp",
    "ask_timestamp",
)
ORDER_LIKE_COLUMNS = {
    "trigger",
    "order_id",
    "client_order_id",
    "side",
    "quantity",
    "shares",
    "order_type",
    "price_type",
    "account",
    "account_type",
    "execution_condition",
    "expiration",
    "sor",
}
READY_TRADING_STATUSES = {"OPEN", "TRADING", "取引中", "通常"}


def _canonical_sha256(value: Mapping[str, Any], hash_field: str) -> str:
    payload = {key: item for key, item in value.items() if key != hash_field}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdefABCDEF" for character in value)
    )


def _exact(value: Any, expected: Any) -> bool:
    return type(value) is type(expected) and value == expected


def _strict_int(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if isinstance(value, str):
        if not value.isdigit():
            raise ValueError(f"{name} must be an integer")
        parsed = int(value)
    elif isinstance(value, int):
        parsed = value
    else:
        raise ValueError(f"{name} must be an integer")
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


def _strict_decimal(value: Any, name: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a finite decimal")
    text = str(value).strip()
    if not text or "," in text:
        raise ValueError(f"{name} must be an unformatted finite decimal")
    try:
        parsed = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a finite decimal") from error
    if not parsed.is_finite() or (positive and parsed <= 0):
        qualifier = "positive " if positive else ""
        raise ValueError(f"{name} must be a {qualifier}finite decimal")
    return parsed


def _strict_jst_datetime(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be an ISO-8601 JST timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 JST timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=9):
        raise ValueError(f"{name} must include the +09:00 JST offset")
    return parsed.astimezone(JST)


def _as_jst(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(JST)


def _stable_read_bytes(
    path: Path, *, maximum_bytes: int = DEFAULT_MAXIMUM_EVIDENCE_BYTES
) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")
    before = path.stat()
    if before.st_size > maximum_bytes:
        raise ValueError(f"Required file exceeds the byte limit: {path}")
    first = path.read_bytes()
    middle = path.stat()
    if middle.st_size > maximum_bytes or len(first) > maximum_bytes:
        raise ValueError(f"Required file exceeds the byte limit: {path}")
    second = path.read_bytes()
    after = path.stat()
    if after.st_size > maximum_bytes or len(second) > maximum_bytes:
        raise ValueError(f"Required file exceeds the byte limit: {path}")
    if not first:
        raise ValueError(f"Required file is empty: {path}")
    if (
        first != second
        or before.st_size != middle.st_size
        or middle.st_size != after.st_size
        or before.st_mtime_ns != middle.st_mtime_ns
        or middle.st_mtime_ns != after.st_mtime_ns
    ):
        raise ValueError(f"File changed while it was being verified: {path}")
    return first


@contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    acquired = False
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        acquired = True
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        yield
    except FileExistsError as error:
        raise RuntimeError(f"RSS shadow operation lock already exists: {path}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if acquired and path.exists():
            path.unlink()


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _path_under(root: Path, value: str, allowed_root: Path, name: str) -> Path:
    path = resolve_path(root, value).resolve()
    allowed = allowed_root.resolve()
    if path != allowed and allowed not in path.parents:
        raise ValueError(f"{name} escapes its allowed directory")
    return path


def _settings(config: Mapping[str, Any]) -> Mapping[str, Any]:
    settings = config.get("rss_shadow_contract", {})
    if not isinstance(settings, Mapping):
        raise ValueError("rss_shadow_contract config must be an object")
    fixed = {
        "enabled": True,
        "advisory_only": True,
        "read_only": True,
        "orders_allowed": False,
        "live_trading_enabled": False,
        "contract_id": CONTRACT_ID,
        "source": SOURCE_ID,
        "exporter": EXPORTER_ID,
        "workbook_contract_version": WORKBOOK_CONTRACT_VERSION,
        "workbook_attestation_required": True,
    }
    for name, expected in fixed.items():
        if not _exact(settings.get(name), expected):
            raise ValueError(f"rss_shadow_contract.{name} must remain {expected!r}")
    quote_age = _strict_int(
        settings.get("maximum_quote_age_seconds"),
        "rss_shadow_contract.maximum_quote_age_seconds",
        1,
    )
    manifest_age = _strict_int(
        settings.get("maximum_manifest_age_seconds"),
        "rss_shadow_contract.maximum_manifest_age_seconds",
        1,
    )
    future_skew = _strict_int(
        settings.get("maximum_future_skew_seconds"),
        "rss_shadow_contract.maximum_future_skew_seconds",
        0,
    )
    minimum_rows = _strict_int(
        settings.get("minimum_quote_rows"),
        "rss_shadow_contract.minimum_quote_rows",
        1,
    )
    maximum_rows = _strict_int(
        settings.get("maximum_quote_rows"),
        "rss_shadow_contract.maximum_quote_rows",
        1,
    )
    maximum_bytes = _strict_int(
        settings.get("maximum_snapshot_bytes"),
        "rss_shadow_contract.maximum_snapshot_bytes",
        1,
    )
    minimum_captures = _strict_int(
        settings.get("minimum_session_captures"),
        "rss_shadow_contract.minimum_session_captures",
        1,
    )
    minimum_span = _strict_int(
        settings.get("minimum_session_span_seconds"),
        "rss_shadow_contract.minimum_session_span_seconds",
        1,
    )
    maximum_manifests = _strict_int(
        settings.get("maximum_session_manifests"),
        "rss_shadow_contract.maximum_session_manifests",
        1,
    )
    if quote_age > 15:
        raise ValueError("maximum_quote_age_seconds cannot exceed 15")
    if manifest_age > 90:
        raise ValueError("maximum_manifest_age_seconds cannot exceed 90")
    if future_skew > 2:
        raise ValueError("maximum_future_skew_seconds cannot exceed 2")
    if minimum_rows < 20 or maximum_rows > 225 or minimum_rows > maximum_rows:
        raise ValueError("RSS quote row limits are invalid")
    if maximum_bytes > HARD_MAXIMUM_SNAPSHOT_BYTES:
        raise ValueError("maximum_snapshot_bytes exceeds the hard safety ceiling")
    if minimum_captures < 3 or minimum_span < 14_400:
        raise ValueError("RSS session sampling safety floors cannot be lowered")
    if maximum_manifests > 64 or minimum_captures > maximum_manifests:
        raise ValueError("RSS session manifest limits are invalid")
    return settings


def _settings_sha256(settings: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        dict(settings),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _producer_evidence(root: Path, settings: Mapping[str, Any]) -> tuple[str, str]:
    relative = str(settings.get("producer_file", "excel/PHOENIX_RSS_SHADOW_V1.bas"))
    path = resolve_path(root, relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in path.parents:
        raise ValueError("producer_file must stay inside the repository")
    data = _stable_read_bytes(path)
    try:
        source = data.decode("utf-8-sig").lower()
    except UnicodeDecodeError as error:
        raise ValueError("RSS VBA producer must be UTF-8") from error
    for token in FORBIDDEN_WORKBOOK_TOKENS:
        if token in source:
            raise ValueError(f"RSS VBA producer contains a forbidden token: {token}")
    for line in source.splitlines():
        if "createobject(" in line and not any(
            allowed in line
            for allowed in ("adodb.stream", "scripting.filesystemobject")
        ):
            raise ValueError("RSS VBA producer contains an unapproved COM object")
    return path.relative_to(root_resolved).as_posix(), _sha256_bytes(data)


def _workbook_paths(
    root: Path, settings: Mapping[str, Any]
) -> tuple[Path, Path]:
    workbook_path = _path_under(
        root,
        str(settings.get("workbook_file", "runtime/v7_rss_shadow/PHOENIX_RSS_SHADOW.xlsm")),
        _runtime_root(root, settings),
        "workbook_file",
    )
    if workbook_path.suffix.lower() != ".xlsm":
        raise ValueError("workbook_file must be an .xlsm file")
    attestation_path = _path_under(
        root,
        str(
            settings.get(
                "workbook_attestation_file",
                "state/rakuten_rss_workbook_attestation.json",
            )
        ),
        (root / "state").resolve(),
        "workbook_attestation_file",
    )
    return workbook_path, attestation_path


def _workbook_binary_evidence(path: Path) -> tuple[bytes, bytes]:
    workbook_bytes = _stable_read_bytes(
        path, maximum_bytes=HARD_MAXIMUM_WORKBOOK_BYTES
    )
    try:
        with zipfile.ZipFile(io.BytesIO(workbook_bytes), "r") as archive:
            archive_names = archive.namelist()
            names_lower = {name.lower() for name in archive_names}
            if "xl/workbook.xml" not in names_lower:
                raise ValueError("Workbook has no xl/workbook.xml")
            forbidden_prefixes = (
                "xl/externallinks/",
                "xl/embeddings/",
                "xl/activex/",
                "xl/macrosheets/",
                "xl/dialogsheets/",
            )
            if any(
                name.lower().startswith(forbidden_prefixes)
                or name.lower() == "xl/connections.xml"
                for name in archive_names
            ):
                raise ValueError("Workbook contains a forbidden external or legacy component")
            names = [name for name in archive_names if name.lower() == "xl/vbaproject.bin"]
            if len(names) != 1:
                raise ValueError("Workbook must contain exactly one xl/vbaProject.bin")
            vba_info = archive.getinfo(names[0])
            if vba_info.file_size > HARD_MAXIMUM_VBA_PROJECT_BYTES:
                raise ValueError("Workbook VBA project exceeds the byte limit")
            vba_project = archive.read(names[0])
            xml_parts: list[bytes] = []
            xml_size = 0
            for name in archive_names:
                if not name.lower().endswith((".xml", ".rels")):
                    continue
                info = archive.getinfo(name)
                xml_size += info.file_size
                if xml_size > HARD_MAXIMUM_WORKBOOK_XML_BYTES:
                    raise ValueError("Workbook XML exceeds the byte limit")
                xml_parts.append(archive.read(name).lower())
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError("Workbook is not a valid macro-enabled Excel container") from error
    scan_targets = (workbook_bytes.lower(), vba_project.lower(), *xml_parts)
    for token in FORBIDDEN_WORKBOOK_TOKENS:
        encoded = token.encode("ascii")
        encoded_wide = token.encode("utf-16le")
        if any(encoded in value or encoded_wide in value for value in scan_targets):
            raise ValueError(f"Workbook contains a forbidden execution token: {token}")
    if any(
        b'targetmode="external"' in value
        or b'state="hidden"' in value
        or b'state="veryhidden"' in value
        for value in xml_parts
    ):
        raise ValueError("Workbook contains an external relationship or hidden sheet")
    return workbook_bytes, vba_project


def create_workbook_attestation(
    root: Path,
    config: Mapping[str, Any],
    *,
    source_import_confirmed: bool,
    no_order_functions_confirmed: bool,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    if source_import_confirmed is not True or no_order_functions_confirmed is not True:
        raise ValueError("Both independent workbook review confirmations are required")
    settings = _settings(config)
    audited_at = _as_jst(as_of or datetime.now(JST), "as_of")
    workbook_path, attestation_path = _workbook_paths(root, settings)
    workbook_bytes, vba_project = _workbook_binary_evidence(workbook_path)
    producer_file, producer_sha256 = _producer_evidence(root, settings)
    attestation: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "workbook_contract_version": WORKBOOK_CONTRACT_VERSION,
        "workbook_file": workbook_path.resolve().relative_to(root.resolve()).as_posix(),
        "workbook_sha256": _sha256_bytes(workbook_bytes),
        "vba_project_sha256": _sha256_bytes(vba_project),
        "producer_file": producer_file,
        "producer_sha256": producer_sha256,
        "source_import_confirmed": True,
        "no_order_functions_confirmed": True,
        "static_scan_scope": "XLSM_CONTAINER_AND_RAW_VBA_PROJECT",
        "audited_at": audited_at.isoformat(timespec="seconds"),
    }
    attestation["attestation_sha256"] = _canonical_sha256(
        attestation, "attestation_sha256"
    )
    atomic_write(
        attestation_path,
        json.dumps(attestation, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    return attestation


def _workbook_evidence(
    root: Path, settings: Mapping[str, Any], *, as_of: datetime
) -> dict[str, Any]:
    workbook_path, attestation_path = _workbook_paths(root, settings)
    attestation = _read_json_strict(attestation_path)
    if attestation.get("attestation_sha256") != _canonical_sha256(
        attestation, "attestation_sha256"
    ):
        raise ValueError("Workbook attestation hash is invalid")
    fixed = {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "workbook_contract_version": WORKBOOK_CONTRACT_VERSION,
        "source_import_confirmed": True,
        "no_order_functions_confirmed": True,
        "static_scan_scope": "XLSM_CONTAINER_AND_RAW_VBA_PROJECT",
    }
    for name, expected in fixed.items():
        if not _exact(attestation.get(name), expected):
            raise ValueError(f"Workbook attestation has invalid {name}")
    workbook_bytes, vba_project = _workbook_binary_evidence(workbook_path)
    producer_file, producer_sha256 = _producer_evidence(root, settings)
    comparisons = {
        "workbook_file": workbook_path.resolve().relative_to(root.resolve()).as_posix(),
        "workbook_sha256": _sha256_bytes(workbook_bytes),
        "vba_project_sha256": _sha256_bytes(vba_project),
        "producer_file": producer_file,
        "producer_sha256": producer_sha256,
    }
    for name, expected in comparisons.items():
        if attestation.get(name) != expected:
            raise ValueError(f"Workbook attestation no longer matches {name}")
    audited_at = _strict_jst_datetime(attestation.get("audited_at"), "attestation.audited_at")
    as_of_jst = _as_jst(as_of, "as_of")
    age = (as_of_jst - audited_at).total_seconds()
    if age < -2 or age > 30 * 24 * 60 * 60:
        raise ValueError("Workbook attestation is stale or future")
    return {
        **comparisons,
        "workbook_attestation_sha256": attestation["attestation_sha256"],
        "workbook_audited_at": audited_at.isoformat(timespec="seconds"),
    }


def _parse_snapshot(
    data: bytes,
    settings: Mapping[str, Any],
    *,
    as_of: datetime,
) -> dict[str, Any]:
    if len(data) > int(settings["maximum_snapshot_bytes"]):
        raise ValueError("RSS snapshot exceeds the configured byte limit")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("RSS snapshot must be UTF-8 CSV") from error
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    header = tuple(reader.fieldnames or ())
    order_columns = sorted({name.strip().lower() for name in header} & ORDER_LIKE_COLUMNS)
    if order_columns:
        raise ValueError(f"RSS shadow snapshot contains order columns: {', '.join(order_columns)}")
    if header != SNAPSHOT_COLUMNS:
        raise ValueError("RSS shadow snapshot columns do not match the exact contract")
    rows = list(reader)
    minimum_rows = int(settings["minimum_quote_rows"])
    maximum_rows = int(settings["maximum_quote_rows"])
    if not minimum_rows <= len(rows) <= maximum_rows:
        raise ValueError(
            f"RSS snapshot row count is outside {minimum_rows}..{maximum_rows}: {len(rows)}"
        )

    as_of_jst = _as_jst(as_of, "as_of")
    quote_age_limit = int(settings["maximum_quote_age_seconds"])
    manifest_age_limit = int(settings["maximum_manifest_age_seconds"])
    future_limit = timedelta(seconds=int(settings["maximum_future_skew_seconds"]))
    common: dict[str, Any] | None = None
    tickers: list[str] = []
    quote_ages: list[float] = []
    normalized_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"RSS snapshot row {index} is ragged")
        expected_common = {
            "schema_version": "1",
            "contract_id": CONTRACT_ID,
            "source": SOURCE_ID,
            "exporter": EXPORTER_ID,
            "workbook_contract_version": WORKBOOK_CONTRACT_VERSION,
            "read_only": "true",
            "orders_allowed": "false",
            "external_orders_submitted": "0",
        }
        for name, expected in expected_common.items():
            if str(row.get(name, "")).strip() != expected:
                raise ValueError(f"RSS snapshot row {index} has invalid {name}")
        capture_id = str(row["capture_id"]).strip()
        if not CAPTURE_ID_PATTERN.fullmatch(capture_id):
            raise ValueError(f"RSS snapshot row {index} has invalid capture_id")
        sequence = _strict_int(str(row["sequence"]).strip(), f"row {index}.sequence", 1)
        exported_at = _strict_jst_datetime(row["exported_at"], f"row {index}.exported_at")
        shared = {
            "capture_id": capture_id,
            "sequence": sequence,
            "exported_at": exported_at.isoformat(timespec="seconds"),
        }
        if common is None:
            common = shared
        elif shared != common:
            raise ValueError("RSS snapshot rows do not share one capture identity")

        ticker = str(row["ticker"]).strip().upper()
        if not TICKER_PATTERN.fullmatch(ticker):
            raise ValueError(f"RSS snapshot row {index} has invalid ticker")
        if ticker in tickers:
            raise ValueError(f"RSS snapshot contains duplicate ticker: {ticker}")
        tickers.append(ticker)
        current_price = _strict_decimal(row["current_price"], f"row {index}.current_price", positive=True)
        bid = _strict_decimal(row["bid"], f"row {index}.bid", positive=True)
        ask = _strict_decimal(row["ask"], f"row {index}.ask", positive=True)
        if ask < bid:
            raise ValueError(f"RSS snapshot row {index} has ask below bid")
        volume = _strict_int(str(row["volume"]).strip(), f"row {index}.volume", 0)
        status = str(row["trading_status"]).strip()
        if status not in READY_TRADING_STATUSES:
            raise ValueError(f"RSS snapshot row {index} trading status is not READY: {status}")
        times: dict[str, datetime] = {}
        for field in ("quote_timestamp", "bid_timestamp", "ask_timestamp"):
            parsed = _strict_jst_datetime(row[field], f"row {index}.{field}")
            if parsed > as_of_jst + future_limit:
                raise ValueError(f"RSS snapshot row {index} {field} is in the future")
            if parsed > exported_at + future_limit:
                raise ValueError(f"RSS snapshot row {index} {field} is later than export")
            if parsed.date() != exported_at.date():
                raise ValueError(f"RSS snapshot row {index} {field} is from another date")
            age = (as_of_jst - parsed).total_seconds()
            if age < -future_limit.total_seconds() or age > quote_age_limit:
                raise ValueError(f"RSS snapshot row {index} {field} is stale or future")
            quote_ages.append(max(0.0, age))
            times[field] = parsed
        normalized_rows.append(
            {
                "ticker": ticker,
                "current_price": str(current_price),
                "bid": str(bid),
                "ask": str(ask),
                "volume": volume,
                "trading_status": status,
                **{name: value.isoformat(timespec="seconds") for name, value in times.items()},
            }
        )

    if common is None:
        raise ValueError("RSS snapshot has no rows")
    exported_at = _strict_jst_datetime(common["exported_at"], "exported_at")
    export_age = (as_of_jst - exported_at).total_seconds()
    if exported_at > as_of_jst + future_limit or export_age > manifest_age_limit:
        raise ValueError("RSS snapshot export time is stale or future")
    if exported_at.date() != as_of_jst.date():
        raise ValueError("RSS snapshot is not from the current JST date")
    if not is_jpx_equities_trading_day(exported_at.date()):
        raise ValueError("RSS snapshot is not from a verified JPX trading day")
    export_time = exported_at.time().replace(tzinfo=None)
    in_session = (
        SESSION_START <= export_time <= MORNING_END
        or AFTERNOON_START <= export_time <= SESSION_END
    )
    if not in_session:
        raise ValueError("RSS snapshot is outside the JPX cash-equity session window")
    return {
        **common,
        "trading_date": exported_at.date().isoformat(),
        "ticker_count": len(tickers),
        "ticker_universe_sha256": ticker_universe_sha256(tickers),
        "oldest_quote_age_seconds": round(max(quote_ages), 6),
        "newest_quote_age_seconds": round(min(quote_ages), 6),
        "tickers": sorted(tickers),
        "rows": normalized_rows,
    }


def _runtime_root(root: Path, settings: Mapping[str, Any]) -> Path:
    runtime_root = resolve_path(root, str(settings["runtime_root"])).resolve()
    repository = root.resolve()
    if runtime_root == repository or repository not in runtime_root.parents:
        raise ValueError("runtime_root must be a child of the repository")
    return runtime_root


def _manifest_path(root: Path, settings: Mapping[str, Any]) -> Path:
    runtime_root = _runtime_root(root, settings)
    return _path_under(
        root,
        str(settings["manifest_file"]),
        runtime_root,
        "manifest_file",
    )


def _snapshot_directory(root: Path, settings: Mapping[str, Any]) -> Path:
    runtime_root = _runtime_root(root, settings)
    return _path_under(
        root,
        str(settings["snapshot_directory"]),
        runtime_root,
        "snapshot_directory",
    )


def _manifest_directory(root: Path, settings: Mapping[str, Any]) -> Path:
    runtime_root = _runtime_root(root, settings)
    return _path_under(
        root,
        str(settings["manifest_directory"]),
        runtime_root,
        "manifest_directory",
    )


def _inbox_path(root: Path, settings: Mapping[str, Any]) -> Path:
    runtime_root = _runtime_root(root, settings)
    inbox_root = _path_under(
        root,
        str(settings["inbox_directory"]),
        runtime_root,
        "inbox_directory",
    )
    return _path_under(
        root,
        str(settings["inbox_snapshot_file"]),
        inbox_root,
        "inbox_snapshot_file",
    )


def _read_json_strict(path: Path) -> dict[str, Any]:
    data = _stable_read_bytes(path)
    try:
        value = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def _publish_inbox_snapshot_unlocked(
    root: Path,
    config: Mapping[str, Any],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    settings = _settings(config)
    as_of = as_of or datetime.now(JST)
    inbox_path = _inbox_path(root, settings)
    source_bytes = _stable_read_bytes(
        inbox_path, maximum_bytes=int(settings["maximum_snapshot_bytes"])
    )
    snapshot = _parse_snapshot(source_bytes, settings, as_of=as_of)
    snapshot_sha256 = _sha256_bytes(source_bytes)
    producer_file, producer_sha256 = _producer_evidence(root, settings)
    workbook = _workbook_evidence(root, settings, as_of=as_of)
    settings_sha256 = _settings_sha256(settings)
    manifest_path = _manifest_path(root, settings)
    previous: dict[str, Any] | None = None
    if manifest_path.exists():
        previous = _read_json_strict(manifest_path)
        if previous.get("manifest_sha256") != _canonical_sha256(previous, "manifest_sha256"):
            raise ValueError("Existing RSS shadow manifest hash is invalid")
        previous_capture = str(previous.get("capture_id", ""))
        previous_snapshot = str(previous.get("snapshot_sha256", ""))
        previous_sequence = _strict_int(previous.get("sequence"), "previous.sequence", 1)
        if previous_capture == snapshot["capture_id"]:
            if previous_snapshot != snapshot_sha256:
                raise ValueError("The same capture_id was reused with different snapshot bytes")
            current_lineage = {
                "producer_file": producer_file,
                "producer_sha256": producer_sha256,
                "settings_sha256": settings_sha256,
                **workbook,
            }
            if any(previous.get(name) != value for name, value in current_lineage.items()):
                raise ValueError("The same capture_id cannot reuse changed producer lineage")
            return previous
        if int(snapshot["sequence"]) <= previous_sequence:
            raise ValueError("RSS snapshot sequence must increase monotonically")

    snapshot_directory = _snapshot_directory(root, settings)
    snapshot_name = f"{snapshot['capture_id']}_{snapshot_sha256[:16]}.csv"
    snapshot_path = snapshot_directory / snapshot_name
    if snapshot_path.exists():
        if _stable_read_bytes(snapshot_path) != source_bytes:
            raise ValueError("Immutable RSS snapshot path already has different bytes")
    else:
        _atomic_write_bytes(snapshot_path, source_bytes)
    relative_snapshot = snapshot_path.resolve().relative_to(root.resolve()).as_posix()
    as_of_jst = _as_jst(as_of, "as_of")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "source": SOURCE_ID,
        "exporter": EXPORTER_ID,
        "workbook_contract_version": WORKBOOK_CONTRACT_VERSION,
        "workbook_attestation_required": True,
        "read_only": True,
        "orders_allowed": False,
        "external_orders_submitted": 0,
        "capture_id": snapshot["capture_id"],
        "sequence": snapshot["sequence"],
        "trading_date": snapshot["trading_date"],
        "exported_at": snapshot["exported_at"],
        "published_at": as_of_jst.isoformat(timespec="seconds"),
        "snapshot_file": relative_snapshot,
        "snapshot_sha256": snapshot_sha256,
        "snapshot_size_bytes": len(source_bytes),
        "ticker_count": snapshot["ticker_count"],
        "ticker_universe_sha256": snapshot["ticker_universe_sha256"],
        "producer_file": producer_file,
        "producer_sha256": producer_sha256,
        **workbook,
        "settings_sha256": settings_sha256,
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest, "manifest_sha256")
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    archive_name = f"{snapshot['capture_id']}_{manifest['manifest_sha256'][:16]}.json"
    archive_path = _manifest_directory(root, settings) / archive_name
    if archive_path.exists():
        if _stable_read_bytes(archive_path) != manifest_bytes:
            raise ValueError("Immutable RSS manifest path already has different bytes")
    else:
        _atomic_write_bytes(archive_path, manifest_bytes)
    _atomic_write_bytes(manifest_path, manifest_bytes)
    return manifest


def publish_inbox_snapshot(
    root: Path,
    config: Mapping[str, Any],
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    settings = _settings(config)
    operation_time = as_of or datetime.now(JST)
    lock_path = _runtime_root(root, settings) / "operation.lock"
    with _exclusive_lock(lock_path):
        return _publish_inbox_snapshot_unlocked(
            root, config, as_of=operation_time
        )


def _evaluate_manifest(
    root: Path,
    config: Mapping[str, Any],
    *,
    as_of: datetime,
    manifest_path_override: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    settings = _settings(config)
    errors: list[str] = []
    manifest: dict[str, Any] = {}
    snapshot: dict[str, Any] = {}
    manifest_path = (
        _path_under(
            root,
            str(manifest_path_override),
            _manifest_directory(root, settings),
            "archived_manifest",
        )
        if manifest_path_override is not None
        else _manifest_path(root, settings)
    )
    try:
        manifest = _read_json_strict(manifest_path)
        if manifest.get("manifest_sha256") != _canonical_sha256(manifest, "manifest_sha256"):
            raise ValueError("RSS shadow manifest hash is invalid")
        fixed = {
            "schema_version": 1,
            "contract_id": CONTRACT_ID,
            "source": SOURCE_ID,
            "exporter": EXPORTER_ID,
            "workbook_contract_version": WORKBOOK_CONTRACT_VERSION,
            "workbook_attestation_required": True,
            "read_only": True,
            "orders_allowed": False,
            "external_orders_submitted": 0,
            "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
        }
        for name, expected in fixed.items():
            if not _exact(manifest.get(name), expected):
                raise ValueError(f"RSS shadow manifest has invalid {name}")
        if not _is_sha256(manifest.get("snapshot_sha256")):
            raise ValueError("RSS shadow snapshot hash is invalid")
        if manifest.get("settings_sha256") != _settings_sha256(settings):
            raise ValueError("RSS shadow settings changed after publication")
        producer_file, producer_sha256 = _producer_evidence(root, settings)
        if manifest.get("producer_file") != producer_file or manifest.get("producer_sha256") != producer_sha256:
            raise ValueError("RSS shadow VBA producer evidence changed")
        workbook = _workbook_evidence(root, settings, as_of=as_of)
        for name, expected in workbook.items():
            if manifest.get(name) != expected:
                raise ValueError(f"RSS shadow workbook evidence changed: {name}")
        snapshot_directory = _snapshot_directory(root, settings)
        snapshot_path = _path_under(
            root,
            str(manifest.get("snapshot_file", "")),
            snapshot_directory,
            "manifest.snapshot_file",
        )
        snapshot_bytes = _stable_read_bytes(
            snapshot_path, maximum_bytes=int(settings["maximum_snapshot_bytes"])
        )
        if len(snapshot_bytes) != _strict_int(
            manifest.get("snapshot_size_bytes"), "manifest.snapshot_size_bytes", 1
        ):
            raise ValueError("RSS shadow snapshot size does not match manifest")
        if _sha256_bytes(snapshot_bytes) != manifest.get("snapshot_sha256"):
            raise ValueError("RSS shadow snapshot hash does not match manifest")
        snapshot = _parse_snapshot(snapshot_bytes, settings, as_of=as_of)
        comparisons = {
            "capture_id": snapshot["capture_id"],
            "sequence": snapshot["sequence"],
            "trading_date": snapshot["trading_date"],
            "exported_at": snapshot["exported_at"],
            "ticker_count": snapshot["ticker_count"],
            "ticker_universe_sha256": snapshot["ticker_universe_sha256"],
        }
        for name, expected in comparisons.items():
            if manifest.get(name) != expected:
                raise ValueError(f"RSS shadow manifest does not match snapshot {name}")
        published_at = _strict_jst_datetime(manifest.get("published_at"), "manifest.published_at")
        as_of_jst = _as_jst(as_of, "as_of")
        future_limit = timedelta(seconds=int(settings["maximum_future_skew_seconds"]))
        published_age = (as_of_jst - published_at).total_seconds()
        if published_at > as_of_jst + future_limit or published_age > int(settings["maximum_manifest_age_seconds"]):
            raise ValueError("RSS shadow manifest publication time is stale or future")
    except (FileNotFoundError, OSError, UnicodeError, ValueError, csv.Error) as error:
        errors.append(f"{type(error).__name__}: {error}")
    evidence = {
        "manifest_file": str(manifest_path),
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "snapshot_file": manifest.get("snapshot_file", ""),
        "snapshot_sha256": manifest.get("snapshot_sha256", ""),
        "capture_id": manifest.get("capture_id", ""),
        "sequence": manifest.get("sequence", 0),
        "trading_date": manifest.get("trading_date", ""),
        "exported_at": manifest.get("exported_at", ""),
        "published_at": manifest.get("published_at", ""),
        "ticker_count": snapshot.get("ticker_count", manifest.get("ticker_count", 0)),
        "ticker_universe_sha256": snapshot.get(
            "ticker_universe_sha256", manifest.get("ticker_universe_sha256", "")
        ),
        "oldest_quote_age_seconds": snapshot.get("oldest_quote_age_seconds"),
        "newest_quote_age_seconds": snapshot.get("newest_quote_age_seconds"),
        "tickers": snapshot.get("tickers", []),
        "producer_sha256": manifest.get("producer_sha256", ""),
        "workbook_sha256": manifest.get("workbook_sha256", ""),
        "vba_project_sha256": manifest.get("vba_project_sha256", ""),
        "workbook_attestation_sha256": manifest.get(
            "workbook_attestation_sha256", ""
        ),
        "settings_sha256": manifest.get("settings_sha256", ""),
    }
    return evidence, errors


def _base_shadow_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "schema_version": 1,
        "evidence_kind": "REALTIME_RSS_SHADOW",
        "integrity_status": "VERIFIED",
        "jpx_calendar_status": "VERIFIED",
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
        "sessions": [],
        "external_orders_submitted": 0,
        "paper_days_credited": 0,
        "audited_live_fills_credited": 0,
    }
    state["evidence_sha256"] = _canonical_sha256(state, "evidence_sha256")
    return state


def _validate_archived_manifest_and_snapshot(
    root: Path,
    settings: Mapping[str, Any],
    manifest_path: Path,
    *,
    expected_trading_date: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _read_json_strict(manifest_path)
    if manifest.get("manifest_sha256") != _canonical_sha256(
        manifest, "manifest_sha256"
    ):
        raise ValueError("Archived RSS manifest hash is invalid")
    fixed = {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "source": SOURCE_ID,
        "exporter": EXPORTER_ID,
        "workbook_contract_version": WORKBOOK_CONTRACT_VERSION,
        "workbook_attestation_required": True,
        "read_only": True,
        "orders_allowed": False,
        "external_orders_submitted": 0,
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
    }
    for name, expected in fixed.items():
        if not _exact(manifest.get(name), expected):
            raise ValueError(f"Archived RSS manifest has invalid {name}")
    if manifest.get("trading_date") != expected_trading_date:
        raise ValueError("Archived RSS manifest trading date is unbound")
    for name in (
        "manifest_sha256",
        "snapshot_sha256",
        "ticker_universe_sha256",
        "producer_sha256",
        "workbook_sha256",
        "vba_project_sha256",
        "workbook_attestation_sha256",
        "settings_sha256",
    ):
        if not _is_sha256(manifest.get(name)):
            raise ValueError(f"Archived RSS manifest has invalid {name}")
    if manifest.get("settings_sha256") != _settings_sha256(settings):
        raise ValueError("Archived RSS manifest settings lineage changed")
    published_at = _strict_jst_datetime(
        manifest.get("published_at"), "archived_manifest.published_at"
    )
    snapshot_path = _path_under(
        root,
        str(manifest.get("snapshot_file", "")),
        _snapshot_directory(root, settings),
        "archived_manifest.snapshot_file",
    )
    snapshot_bytes = _stable_read_bytes(
        snapshot_path, maximum_bytes=int(settings["maximum_snapshot_bytes"])
    )
    if len(snapshot_bytes) != _strict_int(
        manifest.get("snapshot_size_bytes"), "snapshot_size_bytes", 1
    ):
        raise ValueError("Archived RSS snapshot size does not match manifest")
    if _sha256_bytes(snapshot_bytes) != manifest.get("snapshot_sha256"):
        raise ValueError("Archived RSS snapshot hash does not match manifest")
    snapshot = _parse_snapshot(snapshot_bytes, settings, as_of=published_at)
    comparisons = {
        "capture_id": snapshot["capture_id"],
        "sequence": snapshot["sequence"],
        "trading_date": snapshot["trading_date"],
        "exported_at": snapshot["exported_at"],
        "ticker_count": snapshot["ticker_count"],
        "ticker_universe_sha256": snapshot["ticker_universe_sha256"],
    }
    for name, expected in comparisons.items():
        if manifest.get(name) != expected:
            raise ValueError(f"Archived RSS manifest does not match snapshot {name}")
    return manifest, snapshot


def _load_shadow_state(
    root: Path, path: Path, settings: Mapping[str, Any]
) -> dict[str, Any]:
    if not path.exists():
        return _base_shadow_state()
    state = _read_json_strict(path)
    if state.get("evidence_sha256") != _canonical_sha256(state, "evidence_sha256"):
        raise ValueError("Existing RSS shadow evidence hash is invalid")
    if state.get("evidence_kind") != "REALTIME_RSS_SHADOW":
        raise ValueError("Existing RSS shadow evidence kind is invalid")
    fixed = {
        "schema_version": 1,
        "integrity_status": "VERIFIED",
        "jpx_calendar_status": "VERIFIED",
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
        "external_orders_submitted": 0,
        "paper_days_credited": 0,
        "audited_live_fills_credited": 0,
    }
    for name, expected in fixed.items():
        if not _exact(state.get(name), expected):
            raise ValueError(f"Existing RSS shadow evidence has invalid {name}")
    sessions = state.get("sessions")
    if not isinstance(sessions, list):
        raise ValueError("Existing RSS shadow sessions are invalid")
    trading_dates: set[str] = set()
    all_lifecycle_ids: set[str] = set()
    all_economics_ids: set[str] = set()
    minimum_rows = int(settings["minimum_quote_rows"])
    for index, session in enumerate(sessions):
        if not isinstance(session, Mapping):
            raise ValueError(f"Existing RSS shadow session {index} is not an object")
        if session.get("session_sha256") != _canonical_sha256(
            session, "session_sha256"
        ):
            raise ValueError(f"Existing RSS shadow session {index} hash is invalid")
        trading_date = str(session.get("trading_date", ""))
        try:
            parsed_date = datetime.strptime(trading_date, "%Y-%m-%d").date()
        except ValueError as error:
            raise ValueError(
                f"Existing RSS shadow session {index} date is invalid"
            ) from error
        if session.get("session_id") != trading_date or trading_date in trading_dates:
            raise ValueError("Existing RSS shadow session date identity is invalid")
        if not is_jpx_equities_trading_day(parsed_date):
            raise ValueError("Existing RSS shadow session is not a JPX trading day")
        trading_dates.add(trading_date)
        session_fixed = {
            "source": SOURCE_ID,
            "contract_id": CONTRACT_ID,
            "rss_only": True,
            "fallback_used": False,
            "integrity_status": "READY",
            "candidate_guard_status": "READY",
            "coverage_method": "THREE_POINT_SESSION_SAMPLING",
            "continuous_connection_claimed": False,
            "invalid_quote_count": 0,
            "risk_halt_count": 0,
            "risk_override_count": 0,
            "external_orders_submitted": 0,
        }
        for name, expected in session_fixed.items():
            if not _exact(session.get(name), expected):
                raise ValueError(
                    f"Existing RSS shadow session {trading_date} has invalid {name}"
                )
        if _strict_int(session.get("rss_ticker_count"), "rss_ticker_count", 1) < minimum_rows:
            raise ValueError("Existing RSS shadow session has incomplete quote coverage")
        capture_count = _strict_int(
            session.get("capture_count"), "capture_count", 3
        )
        if capture_count < int(settings["minimum_session_captures"]):
            raise ValueError("Existing RSS shadow session has too few captures")
        capture_fields = (
            "capture_ids",
            "rss_manifest_files",
            "rss_manifest_sha256s",
            "rss_snapshot_sha256s",
        )
        for name in capture_fields:
            values = session.get(name)
            if (
                not isinstance(values, list)
                or len(values) != capture_count
                or len(values) != len(set(values))
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise ValueError(
                    f"Existing RSS shadow session {trading_date} has invalid {name}"
                )
        for value in session["rss_manifest_sha256s"] + session["rss_snapshot_sha256s"]:
            if not _is_sha256(value):
                raise ValueError("Existing RSS shadow capture hash is invalid")
        for manifest_file, manifest_sha256 in zip(
            session["rss_manifest_files"], session["rss_manifest_sha256s"]
        ):
            manifest_path = _path_under(
                root,
                manifest_file,
                _manifest_directory(root, settings),
                "session.rss_manifest_file",
            )
            capture_index = session["rss_manifest_files"].index(manifest_file)
            archived, archived_snapshot = _validate_archived_manifest_and_snapshot(
                root,
                settings,
                manifest_path,
                expected_trading_date=trading_date,
            )
            if archived.get("manifest_sha256") != manifest_sha256:
                raise ValueError("Existing RSS shadow archived manifest is invalid")
            if (
                archived.get("capture_id") != session["capture_ids"][capture_index]
                or archived.get("snapshot_sha256")
                != session["rss_snapshot_sha256s"][capture_index]
                or archived_snapshot.get("capture_id")
                != session["capture_ids"][capture_index]
            ):
                raise ValueError("Existing RSS shadow archived capture is unbound")
            lineage = {
                "producer_sha256": "rss_producer_sha256",
                "workbook_sha256": "rss_workbook_sha256",
                "vba_project_sha256": "rss_vba_project_sha256",
                "workbook_attestation_sha256": "rss_workbook_attestation_sha256",
                "settings_sha256": "rss_settings_sha256",
            }
            for manifest_name, session_name in lineage.items():
                if archived.get(manifest_name) != session.get(session_name):
                    raise ValueError("Existing RSS shadow archived lineage is inconsistent")
        if (
            session.get("capture_id") not in session["capture_ids"]
            or session.get("rss_manifest_sha256")
            not in session["rss_manifest_sha256s"]
            or session.get("rss_snapshot_sha256")
            not in session["rss_snapshot_sha256s"]
        ):
            raise ValueError("Existing RSS shadow current capture lineage is invalid")
        first_capture = _strict_jst_datetime(
            session.get("first_capture_at"), "first_capture_at"
        )
        last_capture = _strict_jst_datetime(
            session.get("last_capture_at"), "last_capture_at"
        )
        if (
            first_capture.date().isoformat() != trading_date
            or last_capture.date().isoformat() != trading_date
            or (last_capture - first_capture).total_seconds()
            < int(settings["minimum_session_span_seconds"])
            or first_capture.time() > MORNING_END
            or last_capture.time() < FINAL_SAMPLE_START
        ):
            raise ValueError("Existing RSS shadow session capture span is invalid")
        for name in (
            "rss_snapshot_sha256",
            "rss_manifest_sha256",
            "rss_producer_sha256",
            "rss_workbook_sha256",
            "rss_vba_project_sha256",
            "rss_workbook_attestation_sha256",
            "rss_settings_sha256",
            "rss_universe_sha256",
            "candidate_report_sha256",
            "candidate_input_sha256",
            "candidate_universe_sha256",
            "eligible_candidates_sha256",
        ):
            if not _is_sha256(session.get(name)):
                raise ValueError(
                    f"Existing RSS shadow session {trading_date} has invalid {name}"
                )
        for name in ("lifecycle_fill_ids", "economics_fill_ids", "fill_links"):
            if not isinstance(session.get(name), list):
                raise ValueError(
                    f"Existing RSS shadow session {trading_date} has invalid {name}"
                )
        lifecycle_ids = session["lifecycle_fill_ids"]
        economics_ids = session["economics_fill_ids"]
        if (
            any(not isinstance(value, str) or not value for value in lifecycle_ids)
            or any(not isinstance(value, str) or not value for value in economics_ids)
            or len(lifecycle_ids) != len(set(lifecycle_ids))
            or len(economics_ids) != len(set(economics_ids))
            or len(lifecycle_ids) != len(economics_ids)
            or all_lifecycle_ids.intersection(lifecycle_ids)
            or all_economics_ids.intersection(economics_ids)
        ):
            raise ValueError("Existing RSS shadow fill identifiers are invalid")
        expected_links: set[tuple[str, str]] = set()
        for link in session["fill_links"]:
            if not isinstance(link, Mapping) or set(link) != {
                "lifecycle_fill_id", "economics_fill_id"
            }:
                raise ValueError("Existing RSS shadow fill crosswalk is invalid")
            pair = (link["lifecycle_fill_id"], link["economics_fill_id"])
            if pair in expected_links:
                raise ValueError("Existing RSS shadow fill crosswalk is duplicated")
            expected_links.add(pair)
        if (
            {pair[0] for pair in expected_links} != set(lifecycle_ids)
            or {pair[1] for pair in expected_links} != set(economics_ids)
        ):
            raise ValueError("Existing RSS shadow fill crosswalk is incomplete")
        all_lifecycle_ids.update(lifecycle_ids)
        all_economics_ids.update(economics_ids)
    return state


def verify_shadow_evidence_state(
    root: Path,
    config: Mapping[str, Any],
    state: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    try:
        settings = _settings(config)
        state_path = _path_under(
            root,
            str(
                settings.get(
                    "shadow_evidence_state",
                    "state/v7_realtime_shadow_evidence.json",
                )
            ),
            (root / "state").resolve(),
            "shadow_evidence_state",
        )
        verified = _load_shadow_state(root, state_path, settings)
        if dict(state) != verified:
            raise ValueError("Loaded shadow evidence does not match verified state")
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError, csv.Error) as error:
        return False, [f"RSS shadow state verification failed: {type(error).__name__}: {error}"]
    return True, []


def _candidate_guard_evidence(
    root: Path,
    config: Mapping[str, Any],
    settings: Mapping[str, Any],
    trading_date: str,
) -> dict[str, Any]:
    reports_root = (root / "reports").resolve()
    path = _path_under(
        root,
        str(settings.get("candidate_guard_report", "reports/v7_direct_pipeline_summary.json")),
        reports_root,
        "candidate_guard_report",
    )
    raw = _stable_read_bytes(path)
    try:
        report = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Candidate guard report is invalid") from error
    if not isinstance(report, dict):
        raise ValueError("Candidate guard report root is invalid")
    guard = report.get("candidate_input_guard", {})
    if not isinstance(guard, Mapping) or guard.get("status") != "READY":
        raise ValueError("Candidate input guard is not READY")
    generated_at = str(report.get("generated_at", ""))
    try:
        generated_date = datetime.fromisoformat(generated_at).date().isoformat()
    except ValueError as error:
        raise ValueError("Candidate guard generated_at is invalid") from error
    if generated_date != trading_date:
        raise ValueError("Candidate guard report is not from the RSS trading date")
    for name in ("input_sha256", "eligible_candidates_sha256"):
        if not _is_sha256(guard.get(name)):
            raise ValueError(f"Candidate guard {name} is invalid")
    source_path = _path_under(
        root,
        str(guard.get("source_path", "")),
        reports_root,
        "candidate_guard.source_path",
    )
    source_bytes = _stable_read_bytes(
        source_path, maximum_bytes=int(settings["maximum_snapshot_bytes"])
    )
    if _sha256_bytes(source_bytes) != guard["input_sha256"]:
        raise ValueError("Candidate source no longer matches candidate guard")
    try:
        candidate_reader = csv.DictReader(
            io.StringIO(source_bytes.decode("utf-8-sig"), newline=""), strict=True
        )
        candidate_rows = list(candidate_reader)
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("Candidate source CSV is invalid") from error
    if "ticker" not in tuple(candidate_reader.fieldnames or ()):
        raise ValueError("Candidate source CSV has no ticker column")
    candidate_tickers = [str(row.get("ticker", "")).strip().upper() for row in candidate_rows]
    if (
        len(candidate_tickers) != _strict_int(guard.get("input_rows"), "input_rows", 1)
        or len(candidate_tickers) != len(set(candidate_tickers))
        or any(not TICKER_PATTERN.fullmatch(ticker) for ticker in candidate_tickers)
    ):
        raise ValueError("Candidate source ticker universe is invalid")
    files = config.get("files", {})
    if not isinstance(files, Mapping):
        raise ValueError("Scheduler files config is invalid")
    pipeline_config_path = _path_under(
        root,
        str(files.get("pipeline_config", "config/v7_direct_pipeline_config.json")),
        (root / "config").resolve(),
        "pipeline_config",
    )
    pipeline_config = _read_json_strict(pipeline_config_path)
    policy = CandidateInputPolicy.from_mapping(
        pipeline_config.get("candidate_input", {})
    )
    batch = load_execution_candidates(
        source_path,
        policy,
        repository_root=root,
    )
    recomputed = batch.audit.as_dict()
    for name in (
        "status",
        "input_sha256",
        "eligible_candidates_sha256",
        "input_rows",
        "eligible_rows",
        "rejected_rows",
        "decision_counts",
        "rejection_counts",
    ):
        if guard.get(name) != recomputed.get(name):
            raise ValueError(f"Candidate guard no longer matches source field: {name}")
    return {
        "report_sha256": _sha256_bytes(raw),
        "input_sha256": guard["input_sha256"],
        "eligible_candidates_sha256": guard["eligible_candidates_sha256"],
        "eligible_rows": _strict_int(guard.get("eligible_rows"), "eligible_rows", 0),
        "tickers": sorted(candidate_tickers),
        "candidate_universe_sha256": ticker_universe_sha256(candidate_tickers),
    }


def _session_capture_lineage(
    root: Path,
    config: Mapping[str, Any],
    settings: Mapping[str, Any],
    trading_date: str,
    candidate_tickers: list[str],
) -> dict[str, Any]:
    manifest_paths = sorted(_manifest_directory(root, settings).glob("*.json"))
    if len(manifest_paths) > 4096:
        raise ValueError("RSS manifest archive exceeds the hard inspection limit")
    captures: list[dict[str, Any]] = []
    for path in manifest_paths:
        raw = _read_json_strict(path)
        if raw.get("manifest_sha256") != _canonical_sha256(raw, "manifest_sha256"):
            raise ValueError(f"Archived RSS manifest hash is invalid: {path.name}")
        if raw.get("trading_date") != trading_date:
            continue
        published_at = _strict_jst_datetime(
            raw.get("published_at"), f"{path.name}.published_at"
        )
        evidence, errors = _evaluate_manifest(
            root,
            config,
            as_of=published_at,
            manifest_path_override=path,
        )
        if errors:
            raise ValueError(
                f"Archived RSS manifest is not independently valid: {path.name}: "
                + "; ".join(errors)
            )
        if not set(candidate_tickers).issubset(set(evidence.get("tickers", []))):
            raise ValueError(
                f"Archived RSS capture does not cover the candidate universe: {path.name}"
            )
        captures.append(evidence)
    minimum_captures = int(settings["minimum_session_captures"])
    if not minimum_captures <= len(captures) <= int(settings["maximum_session_manifests"]):
        raise ValueError(
            f"RSS session requires {minimum_captures}..{settings['maximum_session_manifests']} verified captures"
        )
    captures.sort(key=lambda value: str(value["published_at"]))
    capture_ids = [str(value["capture_id"]) for value in captures]
    sequences = [_strict_int(value["sequence"], "capture.sequence", 1) for value in captures]
    if len(capture_ids) != len(set(capture_ids)) or len(sequences) != len(set(sequences)):
        raise ValueError("RSS session capture identities are duplicated")
    if sequences != sorted(sequences):
        raise ValueError("RSS session capture sequence is not monotonic")
    capture_times = [
        _strict_jst_datetime(value["exported_at"], "capture.exported_at")
        for value in captures
    ]
    first_capture = min(capture_times)
    last_capture = max(capture_times)
    if (last_capture - first_capture).total_seconds() < int(
        settings["minimum_session_span_seconds"]
    ):
        raise ValueError("RSS session capture time span is insufficient")
    if not any(value.time() <= MORNING_END for value in capture_times):
        raise ValueError("RSS session has no verified morning capture")
    if not any(value.time() >= FINAL_SAMPLE_START for value in capture_times):
        raise ValueError("RSS session has no verified late-afternoon capture")
    return {
        "capture_count": len(captures),
        "capture_ids": capture_ids,
        "rss_manifest_files": [
            Path(str(value["manifest_file"])).resolve().relative_to(root.resolve()).as_posix()
            for value in captures
        ],
        "rss_manifest_sha256s": [str(value["manifest_sha256"]) for value in captures],
        "rss_snapshot_sha256s": [str(value["snapshot_sha256"]) for value in captures],
        "first_capture_at": first_capture.isoformat(timespec="seconds"),
        "last_capture_at": last_capture.isoformat(timespec="seconds"),
    }


def _capture_session_unlocked(
    root: Path,
    config: Mapping[str, Any],
    report: Mapping[str, Any],
) -> tuple[bool, str]:
    settings = _settings(config)
    staged = config.get("staged_pilot_gate", {})
    if not isinstance(staged, Mapping):
        raise ValueError("staged_pilot_gate config must be an object")
    if settings.get("session_capture_enabled") is not True:
        raise ValueError("RSS shadow session capture is not enabled")
    if staged.get("rss_implementation_ready") is not True:
        raise ValueError("Excel/RSS implementation has not been manually verified")
    report_time = _strict_jst_datetime(report.get("generated_at"), "report.generated_at")
    report_verified, report_errors = verify_rss_shadow_report(
        root, config, report, as_of=report_time
    )
    if not report_verified:
        raise ValueError(
            "RSS shadow report changed before session capture: "
            + "; ".join(report_errors)
        )
    if report.get("status") != "READY" or report.get("evidence_verified") is not True:
        raise ValueError("RSS shadow contract report is not READY")
    evidence = report.get("source_evidence", {})
    if not isinstance(evidence, Mapping):
        raise ValueError("RSS shadow source evidence is missing")
    trading_date = str(evidence.get("trading_date", ""))
    candidate = _candidate_guard_evidence(root, config, settings, trading_date)
    rss_tickers = evidence.get("tickers", [])
    if not isinstance(rss_tickers, list) or not set(candidate["tickers"]).issubset(
        set(rss_tickers)
    ):
        raise ValueError("RSS snapshot does not cover the complete candidate universe")
    capture_lineage = _session_capture_lineage(
        root, config, settings, trading_date, candidate["tickers"]
    )
    state_path = _path_under(
        root,
        str(settings.get("shadow_evidence_state", "state/v7_realtime_shadow_evidence.json")),
        (root / "state").resolve(),
        "shadow_evidence_state",
    )
    state = _load_shadow_state(root, state_path, settings)
    sessions = list(state.get("sessions", []))
    for session in sessions:
        if isinstance(session, Mapping) and session.get("trading_date") == trading_date:
            return False, "A verified RSS shadow session already exists for this trading date"
    session: dict[str, Any] = {
        "session_id": trading_date,
        "trading_date": trading_date,
        "source": SOURCE_ID,
        "contract_id": CONTRACT_ID,
        "capture_id": evidence.get("capture_id", ""),
        "rss_only": True,
        "fallback_used": False,
        "rss_snapshot_sha256": evidence.get("snapshot_sha256", ""),
        "rss_manifest_sha256": evidence.get("manifest_sha256", ""),
        "rss_producer_sha256": evidence.get("producer_sha256", ""),
        "rss_workbook_sha256": evidence.get("workbook_sha256", ""),
        "rss_vba_project_sha256": evidence.get("vba_project_sha256", ""),
        "rss_workbook_attestation_sha256": evidence.get(
            "workbook_attestation_sha256", ""
        ),
        "rss_settings_sha256": evidence.get("settings_sha256", ""),
        "rss_ticker_count": evidence.get("ticker_count", 0),
        "rss_universe_sha256": evidence.get("ticker_universe_sha256", ""),
        "candidate_report_sha256": candidate["report_sha256"],
        "candidate_input_sha256": candidate["input_sha256"],
        "candidate_universe_sha256": candidate["candidate_universe_sha256"],
        "eligible_candidates_sha256": candidate["eligible_candidates_sha256"],
        "eligible_candidate_count": candidate["eligible_rows"],
        "integrity_status": "READY",
        "candidate_guard_status": "READY",
        "coverage_method": "THREE_POINT_SESSION_SAMPLING",
        "continuous_connection_claimed": False,
        **capture_lineage,
        "invalid_quote_count": 0,
        "risk_halt_count": 0,
        "risk_override_count": 0,
        "external_orders_submitted": 0,
        "lifecycle_fill_ids": [],
        "economics_fill_ids": [],
        "fill_links": [],
    }
    session["session_sha256"] = _canonical_sha256(session, "session_sha256")
    sessions.append(session)
    state = {
        **state,
        "sessions": sessions,
        "integrity_status": "VERIFIED",
        "jpx_calendar_status": "VERIFIED",
        "jpx_calendar_sha256": JPX_CALENDAR_SHA256,
        "external_orders_submitted": 0,
        "paper_days_credited": 0,
        "audited_live_fills_credited": 0,
    }
    state["evidence_sha256"] = _canonical_sha256(state, "evidence_sha256")
    atomic_write(
        state_path,
        json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    persisted = _load_shadow_state(root, state_path, settings)
    if persisted != state:
        raise ValueError("Persisted RSS shadow state failed post-save verification")
    return True, "Verified RSS shadow session recorded"


def _capture_session(
    root: Path,
    config: Mapping[str, Any],
    report: Mapping[str, Any],
) -> tuple[bool, str]:
    settings = _settings(config)
    lock_path = _runtime_root(root, settings) / "operation.lock"
    with _exclusive_lock(lock_path):
        return _capture_session_unlocked(root, config, report)


def build_rss_shadow_report(
    source_evidence: Mapping[str, Any],
    errors: list[str],
    *,
    generated_at: datetime,
    session_recorded: bool = False,
    session_message: str = "",
) -> dict[str, Any]:
    ready = not errors
    report: dict[str, Any] = {
        "schema_version": 1,
        "version": REPORT_VERSION,
        "generated_at": _as_jst(generated_at, "generated_at").isoformat(timespec="seconds"),
        "status": "READY" if ready else "NOT_READY",
        "contract_status": "READY" if ready else "NOT_READY",
        "evidence_verified": ready,
        "source_evidence": dict(source_evidence),
        "session_recorded": bool(session_recorded),
        "session_message": session_message,
        "blocking_reasons": list(errors),
        "safety": {
            "advisory_only": True,
            "read_only": True,
            "orders_allowed": False,
            "orders_submitted": 0,
            "external_orders_submitted": 0,
            "broker_state_changed": False,
            "order_queue_touched": False,
            "live_trading_enabled": False,
        },
    }
    report["evidence_sha256"] = _canonical_sha256(report, "evidence_sha256")
    return report


def verify_rss_shadow_report(
    root: Path,
    config: Mapping[str, Any],
    report: Mapping[str, Any],
    *,
    as_of: datetime | None = None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        report_hash_valid = report.get("evidence_sha256") == _canonical_sha256(
            report, "evidence_sha256"
        )
    except (TypeError, ValueError):
        report_hash_valid = False
    if not report_hash_valid:
        errors.append("RSS shadow report hash is invalid")
    fixed = {
        "schema_version": 1,
        "version": REPORT_VERSION,
        "status": "READY",
        "contract_status": "READY",
        "evidence_verified": True,
    }
    for name, expected in fixed.items():
        if not _exact(report.get(name), expected):
            errors.append(f"RSS shadow report has invalid {name}")
    safety = report.get("safety", {})
    if not isinstance(safety, Mapping) or not (
        safety.get("advisory_only") is True
        and safety.get("read_only") is True
        and safety.get("orders_allowed") is False
        and _exact(safety.get("orders_submitted"), 0)
        and _exact(safety.get("external_orders_submitted"), 0)
        and safety.get("broker_state_changed") is False
        and safety.get("order_queue_touched") is False
        and safety.get("live_trading_enabled") is False
    ):
        errors.append("RSS shadow report safety contract is invalid")
    as_of = as_of or datetime.now(JST)
    try:
        current_evidence, current_errors = _evaluate_manifest(root, config, as_of=as_of)
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError) as error:
        current_evidence = {}
        current_errors = [f"RSS shadow verification failed: {type(error).__name__}: {error}"]
    errors.extend(current_errors)
    reported_evidence = report.get("source_evidence", {})
    if not isinstance(reported_evidence, Mapping) or dict(reported_evidence) != current_evidence:
        errors.append("RSS shadow report does not match current source evidence")
    return not errors, errors


def text_report(report: Mapping[str, Any]) -> str:
    evidence = report.get("source_evidence", {})
    safety = report.get("safety", {})
    lines = [
        "PHOENIX v7 STEP20 RAKUTEN RSS READ-ONLY SHADOW CONTRACT",
        "=" * 94,
        f"Status                 : {report.get('status', '')}",
        f"Evidence verified      : {report.get('evidence_verified', False)}",
        f"Trading date           : {evidence.get('trading_date', '')}",
        f"Capture / sequence      : {evidence.get('capture_id', '')} / {evidence.get('sequence', 0)}",
        f"Ticker count            : {evidence.get('ticker_count', 0)}",
        f"Workbook evidence       : {evidence.get('workbook_sha256', '')[:16]}",
        f"Oldest quote age        : {evidence.get('oldest_quote_age_seconds')} sec",
        f"Session recorded        : {report.get('session_recorded', False)}",
        f"Read only / orders      : {safety.get('read_only', False)} / {safety.get('orders_submitted', 0)}",
        f"Live trading enabled    : {safety.get('live_trading_enabled', False)}",
        "-" * 94,
    ]
    blockers = report.get("blocking_reasons", [])
    lines.extend([f"BLOCK  {value}" for value in blockers] or ["READY  Immutable RSS snapshot contract verified"])
    lines.extend(
        [
            "-" * 94,
            "This component never imports the legacy broker gateway or creates an order queue.",
            "=" * 94,
            "",
        ]
    )
    return "\n".join(lines)


def run_rss_shadow_contract(
    root: Path,
    config: Mapping[str, Any],
    *,
    as_of: datetime | None = None,
    publish_inbox: bool = False,
    capture_session: bool = False,
) -> dict[str, Any]:
    settings = _settings(config)
    as_of = as_of or datetime.now(JST)
    _as_jst(as_of, "as_of")
    errors: list[str] = []
    if publish_inbox:
        try:
            publish_inbox_snapshot(root, config, as_of=as_of)
        except (FileNotFoundError, OSError, RuntimeError, UnicodeError, ValueError, csv.Error) as error:
            errors.append(f"Publish failed: {type(error).__name__}: {error}")
    evidence, evaluate_errors = _evaluate_manifest(root, config, as_of=as_of)
    errors.extend(evaluate_errors)
    report = build_rss_shadow_report(evidence, errors, generated_at=as_of)
    if capture_session and not errors:
        try:
            recorded, message = _capture_session(root, config, report)
            report = build_rss_shadow_report(
                evidence,
                [],
                generated_at=as_of,
                session_recorded=recorded,
                session_message=message,
            )
        except (FileNotFoundError, OSError, RuntimeError, UnicodeError, ValueError) as error:
            errors.append(f"Session capture failed: {type(error).__name__}: {error}")
            report = build_rss_shadow_report(evidence, errors, generated_at=as_of)
    reports_root = (root / "reports").resolve()
    json_path = _path_under(
        root,
        str(settings.get("report_json", "reports/v7_rss_shadow_contract.json")),
        reports_root,
        "report_json",
    )
    text_path = _path_under(
        root,
        str(settings.get("report_text", "reports/v7_rss_shadow_contract.txt")),
        reports_root,
        "report_text",
    )
    report["report_json"] = str(json_path)
    report["report_text"] = str(text_path)
    report["evidence_sha256"] = _canonical_sha256(report, "evidence_sha256")
    atomic_write(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
    atomic_write(text_path, text_report(report))
    return report


def print_rss_shadow_summary(report: Mapping[str, Any]) -> None:
    evidence = report.get("source_evidence", {})
    print("=" * 80)
    print("PHOENIX v7 STEP20 RAKUTEN RSS READ-ONLY SHADOW CONTRACT")
    print("=" * 80)
    print(f"Status       : {report.get('status', '')}")
    print(f"Capture      : {evidence.get('capture_id', '')}")
    print(f"Quotes       : {evidence.get('ticker_count', 0)}")
    print(f"Session saved: {report.get('session_recorded', False)}")
    print(f"Orders       : {report.get('safety', {}).get('orders_submitted', 0)}")
    print(f"Live enabled : {report.get('safety', {}).get('live_trading_enabled', False)}")
    print(f"Report       : {report.get('report_text', '')}")
    print("=" * 80)
