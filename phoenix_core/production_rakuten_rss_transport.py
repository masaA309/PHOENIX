from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Protocol, runtime_checkable
from zoneinfo import ZoneInfo
import zipfile
from xml.etree import ElementTree as ET

from phoenix_core.models import OrderRequest, OrderSide, OrderStatus, OrderType
from phoenix_core.production_rakuten_rss_adapter import RakutenRssTransportHealth
from phoenix_core.rss_order_bridge import FileBridgeReceipt, FileBridgeStageResult, read_receipt, stage_request
from phoenix_core.rakuten_rss_adapter import (
    RakutenRssCancelAck,
    RakutenRssOrderUpdate,
    RakutenRssSubmitAck,
)


JST = ZoneInfo("Asia/Tokyo")
ORDER_MACRO_NAME = "RssStockOrder_V"
CANCEL_MACRO_NAME = "RssCancelOrder_V"
ORDER_ID_LIST_MACRO_NAME = "RssOrderIDList"
ORDER_STATUS_MACRO_NAME = "RssOrderStatus"
DEFAULT_WORKBOOK_NAME = "PHOENIX_RSS_PRODUCTION.xlsm"
PHOENIX_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK_PATH = (PHOENIX_ROOT / "runtime" / "v7_rss_production" / DEFAULT_WORKBOOK_NAME).resolve()
TRANSPORT_SHEET_NAME = "PHOENIX_RSS_TRANSPORT"
TRANSPORT_SOURCE_COM_LIVE = "COM_LIVE"
TRANSPORT_SOURCE_FILE_READY = "FILE_READY"
TRANSPORT_SOURCE_FILE_FALLBACK = "FILE_FALLBACK"
TRANSPORT_SOURCE_DISCONNECTED = "DISCONNECTED"

WORKBOOK_STATE_EXCEL_ALIVE_CELL = "J2"
WORKBOOK_STATE_RSS_CONNECTED_CELL = "J3"
WORKBOOK_STATE_ADDIN_READY_CELL = "J4"
WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL = "J5"
WORKBOOK_STATE_HEARTBEAT_CELL = "J6"
WORKBOOK_STATE_CELL_MAP = (
    WORKBOOK_STATE_EXCEL_ALIVE_CELL,
    WORKBOOK_STATE_RSS_CONNECTED_CELL,
    WORKBOOK_STATE_ADDIN_READY_CELL,
    WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL,
    WORKBOOK_STATE_HEARTBEAT_CELL,
)
WORKBOOK_STATE_MAX_AGE = timedelta(seconds=90)

SUBMIT_CELL_MAP = {
    "schema_version": "B2",
    "request_kind": "B3",
    "broker_order_id": "B4",
    "client_order_id": "B5",
    "strategy_name": "B6",
    "ticker": "B7",
    "side": "B8",
    "quantity": "B9",
    "order_type": "B10",
    "limit_price": "B11",
    "live_trading_enabled": "B12",
    "production_transport_enabled": "B13",
    "armed": "B14",
    "submitted_at": "B15",
    "timeout_seconds": "B16",
    "payload_sha256": "B17",
    "macro_name": "B18",
    "message": "B19",
}
RESULT_CELL_MAP = {
    "status": "D2",
    "broker_order_id": "D3",
    "filled_quantity": "D4",
    "filled_price": "D5",
    "message": "D6",
    "updated_at": "D7",
}
CANCEL_CELL_MAP = {
    "schema_version": "B22",
    "request_kind": "B23",
    "broker_order_id": "B24",
    "client_order_id": "B25",
    "action": "B26",
    "submitted_at": "B27",
    "payload_sha256": "B28",
    "macro_name": "B29",
    "message": "B30",
}
RSS_CONNECTION_CELL = "B3"
RSS_CONNECTION_MESSAGE_CELL = "B4"
RSS_PROBE_CELL = "XFD1"
RSS_PROBE_FORMULA = "=RSS|'9501.T'!銘柄名称"
RSS_CONNECTED_STATUS = "CONNECTED"
RSS_NOT_CONNECTED_STATUS = "NOT_CONNECTED"
REQUIRED_RSS_ADDIN_NAMES = (
    "MarketSpeed2_RSS_64bit.xll",
    "MarketSpeed2_RSS_VBA.xlam",
)

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _now_jst() -> datetime:
    return datetime.now(JST)


def _resolve_phoenix_root_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PHOENIX_ROOT / candidate
    candidate = candidate.resolve()
    if candidate != PHOENIX_ROOT and PHOENIX_ROOT not in candidate.parents:
        raise ValueError(f"Path escapes PHOENIX root: {candidate}")
    return candidate


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_order_status(value: Any) -> OrderStatus:
    raw_text = str(value).strip()
    text = raw_text.upper()
    if not text:
        raise ValueError("status is missing")
    if raw_text in {"有効", "VALID", "ACTIVE"}:
        return OrderStatus.ACCEPTED
    if raw_text in {"無効", "該当なし", "不一致"}:
        return OrderStatus.REJECTED
    if text in {"NOT_VALID", "NO_MATCH", "NOT_FOUND", "MISMATCH"}:
        return OrderStatus.REJECTED
    return OrderStatus(text)


def _metadata_value(order: Any, *names: str, default: Any = None) -> Any:
    metadata = getattr(order, "metadata", None)
    if isinstance(metadata, Mapping):
        for name in names:
            value = metadata.get(name)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            return value
    return default


def _expiration_yyyymmdd(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.strftime("%Y%m%d")


def _stable_rss_order_id(client_order_id: str, broker_order_id: str) -> int:
    digest = hashlib.sha256(f"{client_order_id}|{broker_order_id}".encode("utf-8")).hexdigest()
    value = int(digest[:16], 16) % 2147483647
    return value + 1


def _normalize_rss_order_id_entry(value: Any) -> RakutenRssOrderIdEntry | None:
    if value is None:
        return None

    if isinstance(value, Mapping):
        raw_id = value.get("rss_order_id", value.get("order_id", value.get("発注ID", "")))
        raw_function = value.get("function_name", value.get("関数名", ""))
        raw_order_date = value.get("order_date", value.get("発注日", ""))
        raw_order_time = value.get("order_time", value.get("発注時刻", ""))
        raw_order_number = value.get("order_number", value.get("注文番号", ""))
        raw_result = value.get("result", value.get("発注結果", ""))
    elif isinstance(value, (list, tuple)):
        if len(value) < 6:
            return None
        raw_id, raw_function, raw_order_date, raw_order_time, raw_order_number, raw_result = value[:6]
    else:
        return None

    try:
        rss_order_id = int(str(raw_id).strip())
    except Exception:
        return None
    if rss_order_id < 1 or rss_order_id > 2147483647:
        return None

    return RakutenRssOrderIdEntry(
        rss_order_id=rss_order_id,
        function_name=str(raw_function or "").strip(),
        order_date=str(raw_order_date or "").strip(),
        order_time=str(raw_order_time or "").strip(),
        order_number=str(raw_order_number or "").strip(),
        result=str(raw_result or "").strip(),
    )


def _normalize_rss_order_id_entries(value: Any) -> tuple[RakutenRssOrderIdEntry, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        entry = _normalize_rss_order_id_entry(value)
        return () if entry is None else (entry,)
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return ()
        first_entry = _normalize_rss_order_id_entry(value)
        if first_entry is not None:
            return (first_entry,)
        entries: list[RakutenRssOrderIdEntry] = []
        for row in value:
            entry = _normalize_rss_order_id_entry(row)
            if entry is not None:
                entries.append(entry)
        return tuple(entries)
    entry = _normalize_rss_order_id_entry(value)
    return () if entry is None else (entry,)


def _sheet_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return ""
    return value


def _cell_text_from_sheet_xml(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = str(cell.get("t") or "").strip()
    if cell_type == "s":
        raw_value = cell.findtext(f"{MAIN_NS}v")
        if raw_value is None:
            return ""
        index = int(raw_value)
        if 0 <= index < len(shared_strings):
            return shared_strings[index]
        return ""
    if cell_type == "inlineStr":
        return "".join(cell.itertext()).strip()
    if cell_type == "b":
        return "TRUE" if str(cell.findtext(f"{MAIN_NS}v") or "").strip() == "1" else "FALSE"
    return str(cell.findtext(f"{MAIN_NS}v") or "").strip()


def _read_workbook_health_cells(
    workbook_path: Path,
    sheet_name: str,
    cell_refs: tuple[str, ...],
) -> dict[str, str]:
    if not workbook_path.is_file():
        raise WorkbookNotFoundError(f"Workbook not found: {workbook_path}")

    with zipfile.ZipFile(workbook_path) as archive:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for entry in shared_root.findall(f"{MAIN_NS}si"):
                shared_strings.append("".join(entry.itertext()).strip())

        rel_targets = {
            rel.get("Id"): rel.get("Target")
            for rel in rels_root.findall(f"{PKG_REL_NS}Relationship")
            if rel.get("Id") and rel.get("Target")
        }

        sheet_target: str | None = None
        for sheet in workbook_root.findall(f"{MAIN_NS}sheets/{MAIN_NS}sheet"):
            if str(sheet.get("name") or "") == sheet_name:
                rel_id = sheet.get(f"{REL_NS}id")
                if rel_id:
                    sheet_target = rel_targets.get(rel_id)
                break

        if not sheet_target:
            raise RssNotConnectedError(f"Workbook sheet missing: {sheet_name}")

        sheet_path = sheet_target.lstrip("/")
        if not sheet_path.startswith("xl/"):
            sheet_path = f"xl/{sheet_path}"
        sheet_root = ET.fromstring(archive.read(sheet_path))

        values: dict[str, str] = {}
        for cell_ref in cell_refs:
            cell = sheet_root.find(f".//{MAIN_NS}c[@r='{cell_ref}']")
            values[cell_ref] = "" if cell is None else _cell_text_from_sheet_xml(cell, shared_strings)
        return values


@dataclass(frozen=True, slots=True)
class ExcelTransportSession:
    application: Any
    workbook: Any
    workbook_path: Path
    workbook_name: str


@dataclass(frozen=True, slots=True)
class _ResolvedWorkbookOwner:
    application: Any
    workbook: Any
    workbook_full_name: Path
    display_name: str = ""


@dataclass(frozen=True, slots=True)
class WorkbookRuntimeState:
    transport_source: str
    excel_alive: bool
    rss_connected: bool
    addin_ready: bool
    order_transport_ready: bool
    heartbeat_at: datetime | None
    heartbeat_age_seconds: float | None
    ready: bool
    message: str


@dataclass(frozen=True, slots=True)
class RakutenRssOrderIdEntry:
    rss_order_id: int
    function_name: str
    order_date: str
    order_time: str
    order_number: str
    result: str


def _runtime_truthy_cell(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    return text in {"1", "TRUE", "YES", "ON", "READY", "CONNECTED", "RSS_CONNECTED"}


def _runtime_parse_heartbeat(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime(1899, 12, 30, tzinfo=JST) + timedelta(days=float(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            if text.replace(".", "", 1).isdigit():
                parsed = datetime(1899, 12, 30, tzinfo=JST) + timedelta(days=float(text))
            else:
                return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _runtime_state_from_values(values: Mapping[str, Any], *, transport_source: str, now: datetime | None = None) -> WorkbookRuntimeState:
    now_jst = _now_jst() if now is None else now.astimezone(JST) if now.tzinfo is not None and now.utcoffset() is not None else now.replace(tzinfo=JST)
    excel_alive = _runtime_truthy_cell(values.get(WORKBOOK_STATE_EXCEL_ALIVE_CELL, ""))
    rss_connected = _runtime_truthy_cell(values.get(WORKBOOK_STATE_RSS_CONNECTED_CELL, ""))
    addin_ready = _runtime_truthy_cell(values.get(WORKBOOK_STATE_ADDIN_READY_CELL, ""))
    order_transport_ready = _runtime_truthy_cell(values.get(WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL, ""))
    heartbeat_at = _runtime_parse_heartbeat(values.get(WORKBOOK_STATE_HEARTBEAT_CELL, ""))
    heartbeat_age_seconds: float | None = None
    heartbeat_fresh = False
    blockers: list[str] = []

    if not excel_alive:
        blockers.append("Excel alive is false")
    if not rss_connected:
        blockers.append("RSS is not connected")
    if not addin_ready:
        blockers.append("RSS add-in is not ready")
    if not order_transport_ready:
        blockers.append("Order transport is not ready")
    if heartbeat_at is None:
        blockers.append("Heartbeat is missing")
    else:
        heartbeat_age = now_jst - heartbeat_at
        heartbeat_age_seconds = heartbeat_age.total_seconds()
        if heartbeat_age < timedelta(0):
            blockers.append("Heartbeat timestamp is in the future")
        elif heartbeat_age <= WORKBOOK_STATE_MAX_AGE:
            heartbeat_fresh = True
        else:
            blockers.append(
                f"Heartbeat is stale ({int(heartbeat_age.total_seconds())}s > {int(WORKBOOK_STATE_MAX_AGE.total_seconds())}s)"
            )

    ready = not blockers and heartbeat_fresh
    if ready:
        message = "Workbook transport READY."
        transport_source = transport_source if transport_source != TRANSPORT_SOURCE_FILE_FALLBACK else TRANSPORT_SOURCE_FILE_READY
    else:
        message = "; ".join(blockers) if blockers else "Workbook transport is not READY."

    return WorkbookRuntimeState(
        transport_source=transport_source,
        excel_alive=excel_alive,
        rss_connected=rss_connected,
        addin_ready=addin_ready,
        order_transport_ready=order_transport_ready,
        heartbeat_at=heartbeat_at,
        heartbeat_age_seconds=heartbeat_age_seconds,
        ready=ready,
        message=message,
    )


class ExcelComError(RuntimeError):
    pass


class ExcelNotRunningError(ExcelComError):
    pass


class WorkbookNotFoundError(ExcelComError):
    pass


class RssNotConnectedError(ExcelComError):
    pass


@runtime_checkable
class ExcelComBackend(Protocol):
    def connect(self, workbook_path: Path, workbook_name: str) -> ExcelTransportSession:
        raise NotImplementedError

    def read_runtime_state(self, session: ExcelTransportSession) -> WorkbookRuntimeState:
        raise NotImplementedError

    def health_check(
        self,
        session: ExcelTransportSession,
        publish: bool = False,
    ) -> tuple[bool, str]:
        raise NotImplementedError

    def stage_submit_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError

    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        raise NotImplementedError

    def read_order_updates(
        self,
        session: ExcelTransportSession,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        raise NotImplementedError

    def read_rss_order_ledger(
        self,
        session: ExcelTransportSession,
    ) -> tuple[RakutenRssOrderIdEntry, ...]:
        raise NotImplementedError

    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
        raise NotImplementedError

    def stage_cancel_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError

    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        raise NotImplementedError

    def close(self, session: ExcelTransportSession) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class _MockSession:
    application: object = field(default_factory=object)
    workbook: object = field(default_factory=object)


class MockExcelComBackend:
    def __init__(
        self,
        *,
        excel_running: bool = True,
        workbook_present: bool = True,
        rss_connected: bool = True,
        addin_ready: bool = True,
        order_transport_ready: bool = True,
        heartbeat_at: datetime | None = None,
        health_message: str = "MOCK_EXCEL_RSS_READY",
    ) -> None:
        self.excel_running = excel_running
        self.workbook_present = workbook_present
        self.rss_connected = rss_connected
        self.addin_ready = addin_ready
        self.order_transport_ready = order_transport_ready
        self.heartbeat_at = heartbeat_at
        self.health_message = health_message
        self.connect_calls = 0
        self.health_calls = 0
        self.submit_stage_calls = 0
        self.submit_macro_calls = 0
        self.submit_macro_args: list[tuple[Any, ...]] = []
        self.poll_calls = 0
        self.cancel_stage_calls = 0
        self.cancel_macro_calls = 0
        self.cancel_macro_args: list[tuple[Any, ...]] = []
        self.closed_calls = 0
        self.submitted_payloads: list[dict[str, Any]] = []
        self.cancel_payloads: list[dict[str, Any]] = []
        self.publish_calls = 0
        self._updates_by_broker_order_id: dict[str, list[RakutenRssOrderUpdate]] = {}
        self._rss_order_ledger_entries: list[RakutenRssOrderIdEntry] = []
        self._rss_order_status_by_id: dict[int, int] = {}
        self.rss_order_ledger_calls = 0
        self.rss_order_status_calls = 0

    def queue_updates(
        self,
        broker_order_id: str,
        updates: list[RakutenRssOrderUpdate],
    ) -> None:
        self._updates_by_broker_order_id[broker_order_id] = list(updates)

    def queue_rss_order_ledger_entry(
        self,
        rss_order_id: int,
        *,
        function_name: str = ORDER_MACRO_NAME,
        order_number: str = "",
        result: str = "",
        order_date: str = "",
        order_time: str = "",
    ) -> None:
        self._rss_order_ledger_entries = [
            entry for entry in self._rss_order_ledger_entries if entry.rss_order_id != rss_order_id
        ]
        self._rss_order_ledger_entries.append(
            RakutenRssOrderIdEntry(
                rss_order_id=rss_order_id,
                function_name=function_name,
                order_date=order_date,
                order_time=order_time,
                order_number=order_number,
                result=result,
            )
        )

    def set_rss_order_status(self, rss_order_id: int, status: int) -> None:
        self._rss_order_status_by_id[rss_order_id] = int(status)

    def connect(self, workbook_path: Path, workbook_name: str) -> ExcelTransportSession:
        self.connect_calls += 1
        if not self.excel_running:
            raise ExcelNotRunningError("Excel is not running.")
        if not self.workbook_present:
            raise WorkbookNotFoundError(f"Workbook not found: {workbook_path}")
        return ExcelTransportSession(
            application=_MockSession().application,
            workbook=_MockSession().workbook,
            workbook_path=workbook_path,
            workbook_name=workbook_name,
        )

    def read_runtime_state(self, session: ExcelTransportSession) -> WorkbookRuntimeState:
        heartbeat_at = self.heartbeat_at or _now_jst()
        values = {
            WORKBOOK_STATE_EXCEL_ALIVE_CELL: self.excel_running and self.workbook_present,
            WORKBOOK_STATE_RSS_CONNECTED_CELL: self.rss_connected,
            WORKBOOK_STATE_ADDIN_READY_CELL: self.addin_ready,
            WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL: self.order_transport_ready,
            WORKBOOK_STATE_HEARTBEAT_CELL: heartbeat_at,
        }
        return _runtime_state_from_values(values, transport_source=TRANSPORT_SOURCE_COM_LIVE, now=heartbeat_at)

    def health_check(
        self,
        session: ExcelTransportSession,
        publish: bool = False,
    ) -> tuple[bool, str]:
        self.health_calls += 1
        runtime_state = self.read_runtime_state(session)
        if not runtime_state.ready:
            return False, runtime_state.message
        if not self.rss_connected:
            return False, "RSS is not connected."
        if publish:
            self.publish_calls += 1
            self.heartbeat_at = _now_jst()
        return True, self.health_message

    def stage_submit_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self.submit_stage_calls += 1
        self.submitted_payloads.append(dict(payload))

    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        self.submit_macro_calls += 1
        self.submit_macro_args.append(tuple(args))

    def read_order_updates(
        self,
        session: ExcelTransportSession,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        self.poll_calls += 1
        updates = self._updates_by_broker_order_id.get(broker_order_id, [])
        if not updates:
            return ()
        self._updates_by_broker_order_id[broker_order_id] = []
        return tuple(updates)

    def read_rss_order_ledger(
        self,
        session: ExcelTransportSession,
    ) -> tuple[RakutenRssOrderIdEntry, ...]:
        self.rss_order_ledger_calls += 1
        return tuple(self._rss_order_ledger_entries)

    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
        self.rss_order_status_calls += 1
        return int(self._rss_order_status_by_id.get(int(rss_order_id), -1))

    def stage_cancel_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self.cancel_stage_calls += 1
        self.cancel_payloads.append(dict(payload))

    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        self.cancel_macro_calls += 1
        self.cancel_macro_args.append(tuple(args))

    def close(self, session: ExcelTransportSession) -> None:
        self.closed_calls += 1


class Win32ComExcelBackend:
    def __init__(
        self,
        *,
        transport_sheet_name: str = TRANSPORT_SHEET_NAME,
    ) -> None:
        self._transport_sheet_name = transport_sheet_name

    def _require_win32(self) -> tuple[Any, Any]:
        if importlib.util.find_spec("win32com.client") is None or importlib.util.find_spec("pythoncom") is None:
            raise ExcelComError("win32com/pythoncom are not available.")
        from win32com import client as win32_client  # type: ignore[import-not-found]
        import pythoncom  # type: ignore[import-not-found]

        return win32_client, pythoncom

    @staticmethod
    def _workbook_full_name(value: Any) -> Path | None:
        try:
            return Path(str(value.FullName)).resolve()
        except Exception:
            return None

    @staticmethod
    def _application_identity(application: Any, workbook: Any | None = None) -> str:
        for owner in (
            application,
            workbook,
            getattr(workbook, "Application", None) if workbook is not None else None,
        ):
            if owner is None:
                continue
            try:
                return f"hwnd:{int(getattr(owner, 'Hwnd'))}"
            except Exception:
                continue
        return f"object:{id(application)}"

    def _rot_candidates_from_object(
        self,
        obj: Any,
        *,
        target_path: Path,
        display_name: str,
    ) -> list[_ResolvedWorkbookOwner]:
        candidates: list[_ResolvedWorkbookOwner] = []
        try:
            workbooks = getattr(obj, "Workbooks")
        except Exception:
            workbooks = None

        if workbooks is not None:
            try:
                workbook_iterable = list(workbooks)
            except Exception:
                workbook_iterable = []
            for workbook in workbook_iterable:
                workbook_full_name = self._workbook_full_name(workbook)
                if workbook_full_name != target_path:
                    continue
                application = obj
                try:
                    workbook_application = getattr(workbook, "Application", None)
                except Exception:
                    workbook_application = None
                if workbook_application is not None:
                    application = workbook_application
                candidates.append(
                    _ResolvedWorkbookOwner(
                        application=application,
                        workbook=workbook,
                        workbook_full_name=workbook_full_name,
                        display_name=display_name,
                    )
                )
            return candidates

        workbook_full_name = self._workbook_full_name(obj)
        if workbook_full_name != target_path:
            return candidates
        try:
            workbook_application = getattr(obj, "Application", None)
        except Exception:
            workbook_application = None
        if workbook_application is None:
            return candidates
        candidates.append(
            _ResolvedWorkbookOwner(
                application=workbook_application,
                workbook=obj,
                workbook_full_name=workbook_full_name,
                display_name=display_name,
            )
        )
        return candidates

    def _resolve_canonical_owner(
        self,
        workbook_path: Path,
        workbook_name: str,
    ) -> ExcelTransportSession:
        _, pythoncom = self._require_win32()
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

        workbook_path = workbook_path.resolve()
        if not workbook_path.is_file():
            raise WorkbookNotFoundError(f"Workbook not found: {workbook_path}")

        try:
            rot = pythoncom.GetRunningObjectTable()
        except Exception as error:
            raise ExcelComError(f"Excel ROT is unavailable: {error}") from error
        try:
            bind_ctx = pythoncom.CreateBindCtx(0)
        except Exception as error:
            raise ExcelComError(f"Excel bind context is unavailable: {error}") from error
        try:
            enum_moniker = rot.EnumRunning()
        except Exception as error:
            raise ExcelComError(f"Excel ROT enumeration failed: {error}") from error

        matches: list[_ResolvedWorkbookOwner] = []
        seen_candidates: set[tuple[Path, str]] = set()
        moniker_logs: list[str] = []

        while True:
            try:
                fetched = enum_moniker.Next(1)
            except Exception as error:
                raise ExcelComError(f"Excel ROT enumeration failed: {error}") from error
            if not fetched:
                break

            moniker = fetched[0]
            display_name = ""
            try:
                display_name = str(moniker.GetDisplayName(bind_ctx, None)).strip()
            except Exception:
                display_name = ""
            if display_name:
                moniker_logs.append(display_name)

            try:
                rot_object = rot.GetObject(moniker)
            except Exception:
                continue

            for candidate in self._rot_candidates_from_object(
                rot_object,
                target_path=workbook_path,
                display_name=display_name,
            ):
                candidate_key = (
                    candidate.workbook_full_name,
                    self._application_identity(candidate.application, candidate.workbook),
                )
                if candidate_key in seen_candidates:
                    continue
                seen_candidates.add(candidate_key)
                matches.append(candidate)

        if len(matches) != 1:
            if len(matches) == 0:
                suffix = f"; ROT monikers={moniker_logs!r}" if moniker_logs else ""
                raise ExcelComError(f"Canonical workbook owner not found in ROT: {workbook_path}{suffix}")
            owner_summaries = ", ".join(
                f"{candidate.display_name or '<unnamed>'} -> {candidate.workbook_full_name}"
                for candidate in matches
            )
            raise ExcelComError(
                f"Canonical workbook owner is ambiguous in ROT: {workbook_path}; matches={owner_summaries}"
            )

        owner = matches[0]
        return ExcelTransportSession(
            application=owner.application,
            workbook=owner.workbook,
            workbook_path=workbook_path,
            workbook_name=workbook_name,
        )

    def connect(self, workbook_path: Path, workbook_name: str) -> ExcelTransportSession:
        try:
            return self._resolve_canonical_owner(workbook_path, workbook_name)
        except ExcelComError:
            raise
        except Exception as error:
            raise ExcelComError(f"Excel connection failed: {error}") from error

    def _sheet(self, session: ExcelTransportSession) -> Any:
        try:
            return session.workbook.Worksheets(self._transport_sheet_name)
        except Exception as error:
            raise RssNotConnectedError(
                f"Workbook sheet missing: {self._transport_sheet_name}"
            ) from error

    def _read_status_values(self, session: ExcelTransportSession) -> tuple[Any, Any, Any]:
        sheet = self._sheet(session)
        try:
            ready_value = sheet.Range(RSS_CONNECTION_CELL).Value2
            status_value = sheet.Range(RSS_CONNECTION_MESSAGE_CELL).Value2
        except Exception as error:
            raise RssNotConnectedError("Transport sheet status is unreadable.") from error
        return False, ready_value, status_value

    def _read_runtime_values(self, session: ExcelTransportSession) -> dict[str, Any]:
        sheet = self._sheet(session)
        values: dict[str, Any] = {}
        try:
            for cell_ref in WORKBOOK_STATE_CELL_MAP:
                values[cell_ref] = sheet.Range(cell_ref).Value2
        except Exception as error:
            raise RssNotConnectedError("Transport runtime state is unreadable.") from error
        return values

    def _has_required_addins(self, application: Any) -> tuple[bool, str]:
        try:
            addins = list(application.AddIns)
        except Exception as error:
            raise ExcelComError(f"Excel add-in list is unavailable: {error}") from error

        status_lines: list[str] = []
        for required_name in REQUIRED_RSS_ADDIN_NAMES:
            match = None
            for addin in addins:
                try:
                    if str(getattr(addin, "Name", "")).strip().lower() == required_name.lower():
                        match = addin
                        break
                except Exception:
                    continue
            if match is None:
                return False, f"Missing RSS add-in: {required_name}"
            try:
                installed = bool(match.Installed)
            except Exception as error:
                raise ExcelComError(f"RSS add-in state is unreadable for {required_name}: {error}") from error
            if not installed:
                return False, f"RSS add-in is not installed: {required_name}"
            try:
                full_name = str(match.FullName)
            except Exception:
                full_name = required_name
            status_lines.append(f"{required_name}={full_name}")
        return True, "; ".join(status_lines)

    @staticmethod
    def _is_truthy_cell(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().upper()
        return text in {"1", "TRUE", "YES", "ON", "READY"}

    @staticmethod
    def _is_connected_status(value: Any) -> bool:
        text = str(value).strip().upper()
        return text in {"1", "TRUE", "YES", "ON", "CONNECTED", "RSS_CONNECTED", "RSS 接続中"}

    def _probe_rss_connection(self, session: ExcelTransportSession) -> tuple[bool, str]:
        application = session.application
        try:
            probe_value = application.Evaluate(RSS_PROBE_FORMULA)
            if self._is_connected_status(probe_value) or str(probe_value).strip():
                text = str(probe_value).strip()
                if text and not text.startswith("#"):
                    return True, text
        except Exception:
            pass

        sheet = self._sheet(session)
        probe_cell = sheet.Range(RSS_PROBE_CELL)
        try:
            probe_cell.Formula = RSS_PROBE_FORMULA
            try:
                application.CalculateFull()
            except Exception:
                try:
                    application.Calculate()
                except Exception:
                    pass
            probe_value = probe_cell.Value2
            text = str(probe_value).strip()
            if text and not text.startswith("#"):
                return True, text
            return False, f"RSS probe returned {text!r}"
        except Exception as error:
            return False, f"RSS probe failed: {error}"
        finally:
            try:
                probe_cell.ClearContents()
            except Exception:
                pass

    def _write_rss_status(self, session: ExcelTransportSession, value: str) -> None:
        sheet = self._sheet(session)
        try:
            sheet.Range(RSS_CONNECTION_MESSAGE_CELL).Value2 = value
        except Exception as error:
            raise RssNotConnectedError(f"Failed to write RSS status: {error}") from error

    def _write_runtime_state(self, session: ExcelTransportSession, values: Mapping[str, Any]) -> None:
        sheet = self._sheet(session)
        for cell_ref in WORKBOOK_STATE_CELL_MAP:
            try:
                sheet.Range(cell_ref).Value2 = _sheet_value(values.get(cell_ref, ""))
            except Exception as error:
                raise RssNotConnectedError(f"Failed to write transport runtime state to {cell_ref}: {error}") from error

    def read_runtime_state(self, session: ExcelTransportSession) -> WorkbookRuntimeState:
        values = self._read_runtime_values(session)
        return _runtime_state_from_values(values, transport_source=TRANSPORT_SOURCE_COM_LIVE)

    def health_check(
        self,
        session: ExcelTransportSession,
        publish: bool = False,
    ) -> tuple[bool, str]:
        try:
            addins_ok, addins_message = self._has_required_addins(session.application)
            if not addins_ok:
                return False, addins_message

            probe_ok, probe_message = self._probe_rss_connection(session)
            if not probe_ok:
                return False, probe_message

            if publish:
                heartbeat_at = _now_jst()
                self._write_rss_status(session, RSS_CONNECTED_STATUS)
                self._write_runtime_state(
                    session,
                    {
                        WORKBOOK_STATE_EXCEL_ALIVE_CELL: True,
                        WORKBOOK_STATE_RSS_CONNECTED_CELL: True,
                        WORKBOOK_STATE_ADDIN_READY_CELL: True,
                        WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL: True,
                        WORKBOOK_STATE_HEARTBEAT_CELL: heartbeat_at.isoformat(timespec="seconds"),
                    },
                )
            runtime_state = self.read_runtime_state(session)
            if not runtime_state.ready:
                return False, runtime_state.message
            live_message = str(probe_message).strip() or RSS_CONNECTED_STATUS
            return True, f"{live_message}; {addins_message}"
        except RssNotConnectedError as error:
            return False, str(error)
        except Exception as error:  # pragma: no cover - defensive fail-close
            return False, f"Excel/RSS transport health failed: {error}"

    def _write_payload(
        self,
        session: ExcelTransportSession,
        cell_map: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> None:
        sheet = self._sheet(session)
        for key, cell in cell_map.items():
            try:
                sheet.Range(cell).Value2 = _sheet_value(payload.get(key, ""))
            except Exception as error:
                raise ExcelComError(f"Failed to write {key} to {cell}") from error

    def stage_submit_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self._write_payload(session, SUBMIT_CELL_MAP, payload)

    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        try:
            session.application.Run(f"'{session.workbook.Name}'!{macro_name}", *args)
        except Exception as error:
            raise ExcelComError(f"Submit macro failed: {error}") from error

    def read_order_updates(
        self,
        session: ExcelTransportSession,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        sheet = self._sheet(session)
        try:
            status_value = sheet.Range(RESULT_CELL_MAP["status"]).Value2
        except Exception as error:
            raise ExcelComError(f"Failed to read status for {broker_order_id}") from error
        if status_value in (None, ""):
            return ()
        try:
            status = _parse_order_status(status_value)
            fill_quantity = int(sheet.Range(RESULT_CELL_MAP["filled_quantity"]).Value2 or 0)
            fill_price = float(sheet.Range(RESULT_CELL_MAP["filled_price"]).Value2 or 0.0)
            rss_order_status = str(status_value or "").strip()
            message = str(sheet.Range(RESULT_CELL_MAP["message"]).Value2 or "")
            if not message.strip():
                message = str(status_value or "").strip()
            updated_at_raw = sheet.Range(RESULT_CELL_MAP["updated_at"]).Value2
            updated_at = (
                datetime.fromisoformat(str(updated_at_raw))
                if updated_at_raw
                else _now_jst()
            )
        except Exception as error:
            raise ExcelComError(f"Failed to parse order update for {broker_order_id}") from error
        return (
            RakutenRssOrderUpdate(
                status=status,
                fill_quantity=fill_quantity,
                fill_price=fill_price,
                message=message,
                updated_at=updated_at,
                rss_order_status=rss_order_status,
            ),
        )

    def read_rss_order_ledger(
        self,
        session: ExcelTransportSession,
    ) -> tuple[RakutenRssOrderIdEntry, ...]:
        try:
            result = session.application.Run(f"'{session.workbook.Name}'!{ORDER_ID_LIST_MACRO_NAME}")
        except Exception as error:
            raise ExcelComError(f"Failed to read RssOrderIDList: {error}") from error
        return _normalize_rss_order_id_entries(result)

    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
        try:
            result = session.application.Run(
                f"'{session.workbook.Name}'!{ORDER_STATUS_MACRO_NAME}",
                int(rss_order_id),
            )
        except Exception as error:
            raise ExcelComError(f"Failed to read RssOrderStatus for {rss_order_id}: {error}") from error
        try:
            return int(str(result).strip())
        except Exception as error:
            raise ExcelComError(f"Invalid RssOrderStatus for {rss_order_id}: {result!r}") from error

    def stage_cancel_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self._write_payload(session, CANCEL_CELL_MAP, payload)

    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        try:
            session.application.Run(f"'{session.workbook.Name}'!{macro_name}", *args)
        except Exception as error:
            raise ExcelComError(f"Cancel macro failed: {error}") from error

    def close(self, session: ExcelTransportSession) -> None:
        try:
            session.workbook.Close(SaveChanges=False)
        except Exception:
            pass


@dataclass(slots=True)
class _TrackedOrder:
    order: OrderRequest
    broker_order_id: str
    rss_order_id: int
    submitted_at: datetime
    submit_payload: dict[str, Any]
    stage_state: str = "STAGED"
    submit_request_id: str = ""
    cancel_request_id: str = ""
    cancel_payload: dict[str, Any] | None = None
    rss_order_number: str = ""
    rss_order_status_code: int = -1
    broker_observation_state: str = ""
    cancel_observation_state: str = ""
    last_authoritative_rss_status: int = -1
    last_message: str = ""
    filled_quantity: int = 0
    filled_price: float = 0.0
    updated_at: datetime = field(default_factory=_now_jst)


class ProductionRakutenRssTransport:
    def __init__(
        self,
        *,
        live_trading_enabled: bool = False,
        production_transport_enabled: bool = False,
        armed: bool = False,
        workbook_path: Path | str | None = None,
        workbook_name: str = DEFAULT_WORKBOOK_NAME,
        timeout_seconds: int = 300,
        backend: ExcelComBackend | None = None,
        clock: Callable[[], datetime] = _now_jst,
        bridge_root: Path | str | None = None,
    ) -> None:
        self._live_trading_enabled = bool(live_trading_enabled)
        self._production_transport_enabled = bool(production_transport_enabled)
        self._armed = bool(armed)
        # Pin the production transport to the single canonical workbook.
        # The workbook_path argument is retained for compatibility but ignored.
        self._workbook_path = DEFAULT_WORKBOOK_PATH
        self._workbook_name = workbook_name
        self._timeout_seconds = int(timeout_seconds)
        self._backend = backend or Win32ComExcelBackend()
        self._clock = clock
        self._bridge_root = (
            Path(bridge_root).resolve()
            if bridge_root is not None
            else (PHOENIX_ROOT / "runtime" / "v7_rss_production" / "order_bridge").resolve()
        )
        self._session: ExcelTransportSession | None = None
        self._orders: dict[str, _TrackedOrder] = {}
        self._lock = RLock()
        self._com_call_count = 0
        self._submit_macro_call_count = 0
        self._cancel_macro_call_count = 0
        self._last_submit_payload: dict[str, Any] | None = None
        self._last_cancel_payload: dict[str, Any] | None = None

    @property
    def submitted_count(self) -> int:
        return len(self._orders)

    @property
    def com_call_count(self) -> int:
        return self._com_call_count

    @property
    def order_function_call_count(self) -> int:
        return self._submit_macro_call_count

    @property
    def cancel_function_call_count(self) -> int:
        return self._cancel_macro_call_count

    @property
    def last_submit_payload(self) -> dict[str, Any] | None:
        return None if self._last_submit_payload is None else dict(self._last_submit_payload)

    @property
    def last_cancel_payload(self) -> dict[str, Any] | None:
        return None if self._last_cancel_payload is None else dict(self._last_cancel_payload)

    def _gate_message(self) -> str:
        if not self._live_trading_enabled:
            return "Rakuten RSS production transport is disabled until live_trading_enabled=true."
        if not self._production_transport_enabled:
            return (
                "Rakuten RSS production transport is disabled until "
                "production_transport_enabled=true."
            )
        return ""

    def _ensure_session(self) -> ExcelTransportSession:
        if self._session is not None and self._session_matches_workbook(self._session):
            return self._session
        self._session = None
        self._com_call_count += 1
        session = self._backend.connect(self._workbook_path, self._workbook_name)
        self._session = session
        return session

    def _session_matches_workbook(self, session: ExcelTransportSession) -> bool:
        try:
            workbook_full_name = Path(str(session.workbook.FullName)).resolve()
        except Exception:
            if not hasattr(session.workbook, "FullName") and not hasattr(session.application, "Workbooks"):
                return True
            return False
        if workbook_full_name != self._workbook_path:
            return False

        try:
            session_application = session.application
            workbook_application = session.workbook.Application
        except Exception:
            return False

        try:
            session_application_hwnd = int(getattr(session_application, "Hwnd"))
            workbook_application_hwnd = int(getattr(workbook_application, "Hwnd"))
            if session_application_hwnd != workbook_application_hwnd:
                return False
        except Exception:
            if session_application is not workbook_application:
                return False

        try:
            for candidate in session.application.Workbooks:
                try:
                    if Path(str(candidate.FullName)).resolve() == self._workbook_path:
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _refresh_session(self) -> ExcelTransportSession:
        self._session = None
        return self._ensure_session()

    @staticmethod
    def _should_retry_live_recovery(message: str) -> bool:
        text = str(message).lower()
        return "probe" in text or "not connected" in text

    def _health_after_recovery(self) -> RakutenRssTransportHealth | None:
        try:
            session = self._refresh_session()
            return self._health_from_backend(session)
        except ExcelComError:
            return None

    def _read_runtime_state_from_file(self) -> WorkbookRuntimeState:
        try:
            values = _read_workbook_health_cells(
                self._workbook_path,
                TRANSPORT_SHEET_NAME,
                WORKBOOK_STATE_CELL_MAP,
            )
        except ExcelComError as error:
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=str(error),
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=f"Excel/RSS workbook state failed: {error}",
            )
        return _runtime_state_from_values(values, transport_source=TRANSPORT_SOURCE_FILE_FALLBACK)

    def read_runtime_state(self) -> WorkbookRuntimeState:
        gate_message = self._gate_message()
        if gate_message:
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=gate_message,
            )
        try:
            session = self._ensure_session()
        except ExcelComError:
            file_state = self._read_runtime_state_from_file()
            if file_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return file_state
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=file_state.message,
            )

        try:
            return self._backend.read_runtime_state(session)
        except ExcelComError:
            file_state = self._read_runtime_state_from_file()
            if file_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return file_state
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=file_state.message,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            file_state = self._read_runtime_state_from_file()
            if file_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return file_state
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=f"Excel/RSS transport state failed: {error}",
            )

    def _health_from_backend(self, session: ExcelTransportSession) -> RakutenRssTransportHealth:
        self._com_call_count += 1
        connected, message = self._backend.health_check(session)
        return RakutenRssTransportHealth(
            connected=connected,
            message=message,
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

    def publish_file_ready_heartbeat(self) -> RakutenRssTransportHealth:
        try:
            session = self._ensure_session()
            connected, message = self._backend.health_check(session, publish=True)
            transport_source = (
                TRANSPORT_SOURCE_COM_LIVE if connected else TRANSPORT_SOURCE_DISCONNECTED
            )
            return RakutenRssTransportHealth(
                connected=connected,
                message=message,
                transport_source=transport_source,
            )
        except ExcelComError as error:
            self._session = None
            return RakutenRssTransportHealth(
                connected=False,
                message=f"Excel/RSS transport health failed: {error}",
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            self._session = None
            return RakutenRssTransportHealth(
                connected=False,
                message=f"Excel/RSS transport health failed: {error}",
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )

    def _health_from_workbook_file(self) -> RakutenRssTransportHealth:
        state = self._read_runtime_state_from_file()
        return RakutenRssTransportHealth(
            connected=state.ready,
            message=state.message,
            transport_source=state.transport_source,
        )

    def health_check(self) -> RakutenRssTransportHealth:
        gate_message = self._gate_message()
        if gate_message:
            return RakutenRssTransportHealth(
                connected=False,
                message=gate_message,
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )

        try:
            session = self._ensure_session()
            connected, message = self._backend.health_check(session)
            runtime_state = self._backend.read_runtime_state(session)
            return RakutenRssTransportHealth(
                connected=bool(connected and runtime_state.ready),
                message=message,
                transport_source=runtime_state.transport_source,
            )
        except ExcelComError as error:
            runtime_state = self._read_runtime_state_from_file()
            if runtime_state.transport_source == TRANSPORT_SOURCE_DISCONNECTED:
                return RakutenRssTransportHealth(
                    connected=False,
                    message=str(error),
                    transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                )
            return RakutenRssTransportHealth(
                connected=runtime_state.ready,
                message=runtime_state.message,
                transport_source=runtime_state.transport_source,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            runtime_state = self._read_runtime_state_from_file()
            if runtime_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return RakutenRssTransportHealth(
                    connected=runtime_state.ready,
                    message=runtime_state.message,
                    transport_source=runtime_state.transport_source,
                )
            return RakutenRssTransportHealth(
                connected=False,
                message=f"Excel/RSS transport health failed: {error}",
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )

    def _build_submit_payload(
        self,
        order: OrderRequest,
        broker_order_id: str,
        submitted_at: datetime,
    ) -> dict[str, Any]:
        metadata = dict(order.metadata or {})
        protective_order = order.side is OrderSide.SELL and any(
            key in metadata
            for key in (
                "target_price",
                "take_profit_price",
                "stop_price",
                "stop_loss_price",
                "expiration",
                "expires_at",
                "order_category",
            )
        )
        target_price = round(
            float(
                _metadata_value(
                    order,
                    "target_price",
                    "take_profit_price",
                    default=order.limit_price,
                )
            ),
            2,
        )
        stop_price = round(
            float(
                _metadata_value(
                    order,
                    "stop_price",
                    "stop_loss_price",
                    default=0.0,
                )
            ),
            2,
        )
        order_category = str(
            _metadata_value(
                order,
                "order_category",
                default="逆指値付通常注文" if protective_order else "通常注文",
            )
        ).strip()
        execution_condition = str(
            _metadata_value(
                order,
                "execution_condition",
                default="期間指定" if protective_order else "",
            )
        ).strip()
        expiration = _expiration_yyyymmdd(
            _metadata_value(
                order,
                "expiration",
                "expires_at",
                default="",
            )
        )
        trigger_condition = str(
            _metadata_value(
                order,
                "trigger_condition",
                default="以下" if protective_order else "",
            )
        ).strip()
        post_trigger_order_type = str(
            _metadata_value(
                order,
                "post_trigger_order_type",
                default="売り成行" if protective_order else "",
            )
        ).strip()
        payload = {
            "schema_version": 1,
            "request_kind": "SUBMIT",
            "broker_order_id": broker_order_id,
            "client_order_id": order.client_order_id,
            "strategy_name": order.strategy_name,
            "ticker": order.ticker.strip().upper(),
            "side": order.side.value,
            "quantity": order.quantity,
            "order_type": order.order_type.value,
            "limit_price": round(float(order.limit_price), 2),
            "target_price": target_price,
            "stop_price": stop_price,
            "stop_trigger_price": stop_price,
            "order_category": order_category,
            "execution_condition": execution_condition,
            "expiration": expiration,
            "trigger_condition": trigger_condition,
            "post_trigger_order_type": post_trigger_order_type,
            "protective_order": protective_order,
            "live_trading_enabled": self._live_trading_enabled,
            "production_transport_enabled": self._production_transport_enabled,
            "armed": self._armed,
            "submitted_at": submitted_at.isoformat(timespec="seconds"),
            "timeout_seconds": self._timeout_seconds,
            "macro_name": ORDER_MACRO_NAME,
            "message": "STAGED" if not self._armed else "LIVE_FIRE_ARMED",
        }
        payload["payload_sha256"] = _stable_hash(payload)
        return payload

    def _build_cancel_payload(
        self,
        order: _TrackedOrder,
        submitted_at: datetime,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": 1,
            "request_kind": "CANCEL",
            "broker_order_id": order.broker_order_id,
            "client_order_id": order.order.client_order_id,
            "action": "CANCEL",
            "submitted_at": submitted_at.isoformat(timespec="seconds"),
            "macro_name": CANCEL_MACRO_NAME,
            "message": "STAGED",
        }
        payload["payload_sha256"] = _stable_hash(payload)
        return payload

    def _file_bridge_request_id(self, request_kind: str, broker_order_id: str) -> str:
        return f"{request_kind.upper()}__{broker_order_id}"

    def _stage_file_bridge_request(
        self,
        *,
        request_kind: str,
        request_id: str,
        payload: Mapping[str, Any],
        submitted_at: datetime,
    ) -> FileBridgeStageResult:
        bridge_payload = dict(payload)
        bridge_payload["request_id"] = request_id
        bridge_payload["request_kind"] = request_kind.upper()
        bridge_payload["bridge_status"] = "PENDING"
        return stage_request(
            self._bridge_root,
            request_id=request_id,
            request_kind=request_kind,
            payload=bridge_payload,
            now=submitted_at,
        )

    def _read_file_bridge_receipt(
        self,
        *,
        request_id: str,
        request_kind: str,
    ) -> FileBridgeReceipt | None:
        return read_receipt(
            self._bridge_root,
            request_id=request_id,
            request_kind=request_kind,
            now=self._clock(),
        )

    def _file_bridge_update_from_receipt(self, receipt: FileBridgeReceipt) -> RakutenRssOrderUpdate:
        try:
            status = _parse_order_status(receipt.result)
        except Exception as error:
            raise ExcelComError(f"Invalid bridge receipt result: {error}") from error
        try:
            authoritative_rss_status = int(str(receipt.rss_order_status).strip())
        except Exception:
            authoritative_rss_status = -1
        return RakutenRssOrderUpdate(
            status=status,
            fill_quantity=receipt.fill_quantity,
            fill_price=receipt.fill_price,
            message=receipt.message or receipt.result,
            updated_at=receipt.received_at,
            rss_order_status=receipt.rss_order_status,
            rss_order_number=receipt.rss_order_number,
            authoritative_rss_status=authoritative_rss_status,
        )

    @staticmethod
    def _tracked_order_status(order: _TrackedOrder) -> OrderStatus:
        try:
            return OrderStatus(order.stage_state)
        except Exception:
            return OrderStatus.PENDING

    def _tracked_order_ack(self, order: _TrackedOrder, *, message: str | None = None) -> RakutenRssSubmitAck:
        status = self._tracked_order_status(order)
        return RakutenRssSubmitAck(
            status=status,
            message=message or order.last_message or status.value,
            submitted_at=order.submitted_at,
            rss_order_id=order.rss_order_id,
            rss_order_number=order.rss_order_number,
            authoritative_rss_status=order.last_authoritative_rss_status,
        )

    def _tracked_cancel_ack(self, order: _TrackedOrder, *, message: str | None = None) -> RakutenRssCancelAck:
        status = self._tracked_order_status(order)
        return RakutenRssCancelAck(
            status=status,
            message=message or order.last_message or status.value,
            canceled_at=order.submitted_at,
            rss_order_id=order.rss_order_id,
            rss_order_number=order.rss_order_number,
            authoritative_rss_status=order.last_authoritative_rss_status,
        )

    def _stable_rss_order_id(self, order: OrderRequest, broker_order_id: str) -> int:
        return _stable_rss_order_id(order.client_order_id, broker_order_id)

    @staticmethod
    def _rss_order_status_value(value: Any) -> int:
        try:
            status = int(str(value).strip())
        except Exception as error:
            raise ExcelComError(f"Invalid RssOrderStatus value: {value!r}") from error
        if status not in {-1, 1, 2, 3}:
            raise ExcelComError(f"Unsupported RssOrderStatus value: {status}")
        return status

    def _live_contract_metadata(self, order: OrderRequest) -> dict[str, Any]:
        metadata = dict(order.metadata or {})
        required_names = ("account_category", "sor_category", "execution_condition")
        missing = [name for name in required_names if str(metadata.get(name, "")).strip() == ""]
        if missing:
            raise ExcelComError(
                "LIVE contract fields missing: " + ", ".join(missing)
            )
        return metadata

    @staticmethod
    def _rss_code_from_alias(value: Any, mapping: Mapping[str, int], *, field_name: str) -> int:
        text = str(value).strip()
        if not text:
            raise ExcelComError(f"{field_name} is missing for LIVE contract.")
        if text.isdigit():
            code = int(text)
            if code in mapping.values():
                return code
        normalized = text.replace("（", "(").replace("）", ")")
        if normalized in mapping:
            return mapping[normalized]
        if text in mapping:
            return mapping[text]
        raise ExcelComError(f"Unsupported {field_name}: {value!r}")

    def _rss_account_category_code(self, value: Any) -> int:
        return self._rss_code_from_alias(
            value,
            {
                "0": 0,
                "特定": 0,
                "1": 1,
                "一般": 1,
                "2": 2,
                "NISA": 2,
                "NISA(NISA成長投資枠)": 2,
                "3": 3,
                "旧NISA": 3,
            },
            field_name="account_category",
        )

    def _rss_sor_code(self, value: Any) -> int:
        return self._rss_code_from_alias(
            value,
            {
                "0": 0,
                "通常": 0,
                "通常注文": 0,
                "1": 1,
                "SOR": 1,
                "SOR注文": 1,
            },
            field_name="sor_category",
        )

    def _rss_execution_condition_code(self, value: Any) -> int:
        return self._rss_code_from_alias(
            value,
            {
                "1": 1,
                "本日中": 1,
                "2": 2,
                "今週中": 2,
                "3": 3,
                "寄付": 3,
                "4": 4,
                "引け": 4,
                "5": 5,
                "期間指定": 5,
                "6": 6,
                "大引不成": 6,
                "7": 7,
                "不成": 7,
            },
            field_name="execution_condition",
        )

    def _rss_trigger_condition_code(self, value: Any) -> int | str:
        text = str(value).strip()
        if not text:
            return ""
        if text.isdigit() and int(text) in {1, 2}:
            return int(text)
        mapping = {
            "1": 1,
            "以上": 1,
            "2": 2,
            "以下": 2,
        }
        return self._rss_code_from_alias(value, mapping, field_name="trigger_condition")

    def _rss_price_kind_code(self, value: Any, *, field_name: str) -> int:
        text = str(value).strip()
        if not text:
            raise ExcelComError(f"{field_name} is missing for LIVE contract.")
        if text.isdigit() and int(text) in {0, 1}:
            return int(text)
        mapping = {
            "0": 0,
            "成行": 0,
            "1": 1,
            "指値": 1,
        }
        return self._rss_code_from_alias(value, mapping, field_name=field_name)

    def _rss_optional_price(self, value: Any, *, field_name: str) -> Any:
        text = str(value).strip()
        if not text:
            return ""
        try:
            return round(float(text), 2)
        except Exception as error:
            raise ExcelComError(f"Unsupported {field_name}: {value!r}") from error

    def _rss_stop_price_kind_code(self, value: Any) -> int | str:
        text = str(value).strip()
        if not text:
            return ""
        if text.isdigit() and int(text) in {0, 1}:
            return int(text)
        mapping = {
            "0": 0,
            "成行": 0,
            "売り成行": 0,
            "買い成行": 0,
            "1": 1,
            "指値": 1,
            "売り指値": 1,
            "買い指値": 1,
        }
        return self._rss_code_from_alias(value, mapping, field_name="stop_price_kind")

    def _rss_set_order_kind_code(self, value: Any) -> int | str:
        text = str(value).strip()
        if not text:
            return ""
        if text.isdigit() and int(text) in {0, 1}:
            return int(text)
        mapping = {
            "0": 0,
            "成行": 0,
            "売り成行": 0,
            "買い成行": 0,
            "1": 1,
            "指値": 1,
            "売り指値": 1,
            "買い指値": 1,
        }
        return self._rss_code_from_alias(value, mapping, field_name="set_order_kind")

    def _rss_order_kind_code(self, order: OrderRequest, metadata: Mapping[str, Any]) -> int:
        order_category = str(
            _metadata_value(order, "order_category", default=metadata.get("order_category", ""))
        ).strip()
        if order_category in {"0", "通常", "通常注文"}:
            return 0
        if order_category in {"1", "逆指値付通常注文"}:
            return 1
        if order_category in {"2", "逆指値注文"}:
            return 2
        if order.side is OrderSide.SELL and any(
            key in metadata for key in ("target_price", "take_profit_price", "stop_price", "stop_loss_price")
        ):
            return 1
        return 0

    @staticmethod
    def _rss_side_code(order: OrderRequest) -> int:
        if order.side is OrderSide.BUY:
            return 3
        if order.side is OrderSide.SELL:
            return 1
        raise ExcelComError(f"Unsupported order side: {order.side}")

    @staticmethod
    def _rss_price_kind(order: OrderRequest) -> int:
        order_type_text = str(getattr(order.order_type, "value", order.order_type)).strip().upper()
        if order_type_text in {"MARKET", "成行"}:
            return 0
        if order_type_text in {"LIMIT", "指値"}:
            return 1
        raise ExcelComError(f"Unsupported order type: {order.order_type}")

    def _rss_optional_text(self, value: Any) -> str:
        text = str(value).strip()
        return text

    def _build_rss_stock_order_arguments(self, order: OrderRequest, rss_order_id: int) -> tuple[Any, ...]:
        metadata = self._live_contract_metadata(order)
        order_category = self._rss_order_kind_code(order, metadata)
        price_kind = self._rss_price_kind(order)
        account_category = self._rss_account_category_code(metadata.get("account_category", ""))
        sor_category = self._rss_sor_code(metadata.get("sor_category", ""))
        execution_condition = self._rss_execution_condition_code(metadata.get("execution_condition", ""))
        expiration = _expiration_yyyymmdd(metadata.get("expiration", metadata.get("expires_at", "")))
        quantity = int(order.quantity)
        order_price: Any = round(float(order.limit_price), 2) if price_kind == 1 else ""
        stop_condition_price = self._rss_optional_price(
            _metadata_value(order, "stop_condition_price", "stop_price", default=""),
            field_name="stop_condition_price",
        )
        stop_condition_kind = self._rss_trigger_condition_code(
            _metadata_value(order, "stop_condition_kind", "trigger_condition", default="")
        )
        stop_price_kind = self._rss_stop_price_kind_code(
            _metadata_value(order, "stop_price_kind", "post_trigger_order_type", default="")
        )
        stop_price = self._rss_optional_price(
            _metadata_value(order, "stop_price", "stop_loss_price", default=""),
            field_name="stop_price",
        )
        set_order_kind = self._rss_set_order_kind_code(_metadata_value(order, "set_order_kind", default=""))
        set_order_price = self._rss_optional_price(
            _metadata_value(order, "set_order_price", default=""),
            field_name="set_order_price",
        )
        set_order_execution_condition = self._rss_execution_condition_code(
            _metadata_value(order, "set_order_execution_condition", default="")
        ) if str(_metadata_value(order, "set_order_execution_condition", default="")).strip() else ""
        set_order_expiration = _expiration_yyyymmdd(_metadata_value(order, "set_order_expiration", default=""))
        ticker = order.ticker.strip().upper()
        return (
            int(rss_order_id),
            ticker,
            self._rss_side_code(order),
            order_category,
            sor_category,
            quantity,
            price_kind,
            order_price,
            execution_condition,
            expiration,
            account_category,
            stop_condition_price,
            stop_condition_kind,
            stop_price_kind,
            stop_price,
            set_order_kind,
            set_order_price,
            set_order_execution_condition,
            set_order_expiration,
        )

    def _build_rss_cancel_order_arguments(self, rss_order_id: int, order_number: str) -> tuple[Any, ...]:
        if not str(order_number).strip():
            raise ExcelComError("RSS order number is missing for cancel.")
        return (int(rss_order_id), str(order_number).strip())

    def _find_rss_order_ledger_entry(
        self,
        session: ExcelTransportSession,
        rss_order_id: int,
        *,
        function_name: str,
    ) -> RakutenRssOrderIdEntry | None:
        for entry in self._backend.read_rss_order_ledger(session):
            if entry.rss_order_id != int(rss_order_id):
                continue
            if str(entry.function_name).strip() and str(entry.function_name).strip() != function_name:
                continue
            return entry
        return None

    def _observe_rss_order_status(
        self,
        session: ExcelTransportSession,
        rss_order_id: int,
    ) -> int:
        return self._backend.read_rss_order_status(session, int(rss_order_id))

    def submit_order(self, order: OrderRequest, broker_order_id: str) -> RakutenRssSubmitAck:
        order.validate()
        gate_message = self._gate_message()
        if gate_message:
            return RakutenRssSubmitAck(
                status=OrderStatus.REJECTED,
                message=gate_message,
                rss_order_id=self._stable_rss_order_id(order, broker_order_id),
            )

        submitted_at = self._clock()
        payload = self._build_submit_payload(order, broker_order_id, submitted_at)
        with self._lock:
            self._last_submit_payload = dict(payload)
            existing = self._orders.get(broker_order_id)
            if existing is not None:
                return self._tracked_order_ack(existing)

        rss_order_id = self._stable_rss_order_id(order, broker_order_id)
        record: _TrackedOrder | None = None

        try:
            with self._lock:
                record = _TrackedOrder(
                    order=order,
                    broker_order_id=broker_order_id,
                    rss_order_id=rss_order_id,
                    submitted_at=submitted_at,
                    submit_payload=dict(payload),
                    submit_request_id=self._file_bridge_request_id("SUBMIT", broker_order_id),
                )
                self._orders[broker_order_id] = record

            health = self.health_check()
            if not health.connected:
                with self._lock:
                    if record is not None:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = health.message
                        record.updated_at = self._clock()
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    submitted_at=submitted_at,
                    rss_order_id=rss_order_id,
                )
            if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                request_id = self._file_bridge_request_id("SUBMIT", broker_order_id)
                try:
                    bridge_result = self._stage_file_bridge_request(
                        request_kind="SUBMIT",
                        request_id=request_id,
                        payload=payload,
                        submitted_at=submitted_at,
                    )
                except Exception as error:
                    with self._lock:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = f"FILE_READY bridge staging failed: {error}"
                        record.updated_at = self._clock()
                    return RakutenRssSubmitAck(
                        status=OrderStatus.REJECTED,
                        message=f"FILE_READY bridge staging failed: {error}",
                        submitted_at=submitted_at,
                        rss_order_id=rss_order_id,
                    )
                with self._lock:
                    record.submit_request_id = request_id
                    record.stage_state = OrderStatus.PENDING.value
                    record.last_message = (
                        "FILE_READY request staged."
                        if not bridge_result.duplicate
                        else "FILE_READY request already staged."
                    )
                    record.updated_at = self._clock()
                    return RakutenRssSubmitAck(
                        status=OrderStatus.PENDING,
                        message=record.last_message,
                        submitted_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
            if health.transport_source != TRANSPORT_SOURCE_COM_LIVE:
                with self._lock:
                    if record is not None:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = health.message
                        record.updated_at = self._clock()
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    submitted_at=submitted_at,
                    rss_order_id=rss_order_id,
                )
            session = self._ensure_session()
            self._com_call_count += 1
            if not self._armed:
                with self._lock:
                    if record is not None:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = "production_live_fire_armed=false; submit staging disabled."
                        record.updated_at = self._clock()
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message="armed=false; RssStockOrder_V not called.",
                    submitted_at=submitted_at,
                    rss_order_id=rss_order_id,
                )
            self._backend.stage_submit_payload(session, payload)
            submit_args = self._build_rss_stock_order_arguments(order, rss_order_id)
            self._com_call_count += 1
            self._submit_macro_call_count += 1
            self._backend.invoke_submit_macro(session, ORDER_MACRO_NAME, *submit_args)
            ledger_entry = self._find_rss_order_ledger_entry(
                session,
                rss_order_id,
                function_name=ORDER_MACRO_NAME,
            )
            try:
                rss_order_status = self._observe_rss_order_status(session, rss_order_id)
            except ExcelComError as error:
                rss_order_status = -1
                status_error = str(error)
            else:
                status_error = ""
            with self._lock:
                    if record is not None:
                        record.rss_order_status_code = rss_order_status
                        if ledger_entry is not None:
                            record.rss_order_number = ledger_entry.order_number
                            if ledger_entry.result:
                                record.last_message = ledger_entry.result
                        record.last_authoritative_rss_status = rss_order_status
                        if not record.last_message:
                            record.last_message = status_error or "RssStockOrder_V invoked."
                        if ledger_entry is None or not ledger_entry.order_number or not ledger_entry.result or rss_order_status == -1:
                            record.stage_state = OrderStatus.PENDING.value
                            record.broker_observation_state = OrderStatus.PENDING.value
                            record.updated_at = self._clock()
                            return RakutenRssSubmitAck(
                                status=OrderStatus.PENDING,
                                message=record.last_message or "RssOrderIDList not yet observed.",
                                submitted_at=submitted_at,
                                rss_order_id=record.rss_order_id,
                                rss_order_number=record.rss_order_number,
                                authoritative_rss_status=record.last_authoritative_rss_status,
                            )
                        if rss_order_status == 1:
                            record.stage_state = OrderStatus.REJECTED.value
                            record.broker_observation_state = OrderStatus.REJECTED.value
                            record.updated_at = self._clock()
                            return RakutenRssSubmitAck(
                                status=OrderStatus.REJECTED,
                                message=record.last_message or "RssOrderStatus=1",
                                submitted_at=submitted_at,
                                rss_order_id=record.rss_order_id,
                                rss_order_number=record.rss_order_number,
                                authoritative_rss_status=record.last_authoritative_rss_status,
                            )
                        if rss_order_status == 3:
                            record.stage_state = OrderStatus.PENDING.value
                            record.broker_observation_state = OrderStatus.PENDING.value
                            record.last_message = record.last_message or "RssOrderStatus=3"
                            record.updated_at = self._clock()
                            return RakutenRssSubmitAck(
                                status=OrderStatus.PENDING,
                                message=record.last_message or "RssOrderStatus=3",
                                submitted_at=submitted_at,
                                rss_order_id=record.rss_order_id,
                                rss_order_number=record.rss_order_number,
                                authoritative_rss_status=record.last_authoritative_rss_status,
                            )
                        record.stage_state = OrderStatus.ACCEPTED.value
                        record.broker_observation_state = OrderStatus.ACCEPTED.value
                        record.updated_at = self._clock()
                        return RakutenRssSubmitAck(
                            status=OrderStatus.ACCEPTED,
                            message=record.last_message or "RssOrderStatus=2",
                            submitted_at=submitted_at,
                            rss_order_id=record.rss_order_id,
                            rss_order_number=record.rss_order_number,
                            authoritative_rss_status=record.last_authoritative_rss_status,
                        )
            return RakutenRssSubmitAck(
                status=OrderStatus.PENDING,
                message=status_error or "RssOrderIDList not yet observed.",
                submitted_at=submitted_at,
                rss_order_id=rss_order_id,
                rss_order_number=record.rss_order_number if record is not None else "",
                authoritative_rss_status=-1,
            )
        except ExcelComError as error:
            if record is not None:
                with self._lock:
                    record.stage_state = OrderStatus.REJECTED.value
                    record.last_message = str(error)
                    record.updated_at = self._clock()
            return RakutenRssSubmitAck(
                status=OrderStatus.REJECTED,
                message=str(error),
                submitted_at=submitted_at,
                rss_order_id=rss_order_id,
                rss_order_number=record.rss_order_number if record is not None else "",
                authoritative_rss_status=record.last_authoritative_rss_status if record is not None else -1,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            if record is not None:
                with self._lock:
                    record.stage_state = OrderStatus.REJECTED.value
                    record.last_message = f"Excel/RSS submit failed: {error}"
                    record.updated_at = self._clock()
            return RakutenRssSubmitAck(
                status=OrderStatus.REJECTED,
                message=f"Excel/RSS submit failed: {error}",
                submitted_at=submitted_at,
                rss_order_id=rss_order_id,
                rss_order_number=record.rss_order_number if record is not None else "",
                authoritative_rss_status=record.last_authoritative_rss_status if record is not None else -1,
            )

    def poll_order(self, broker_order_id: str) -> tuple[RakutenRssOrderUpdate, ...]:
        gate_message = self._gate_message()
        if gate_message:
            return ()

        with self._lock:
            record = self._orders.get(broker_order_id)
        if record is None:
            return ()

        updates: tuple[RakutenRssOrderUpdate, ...] = ()
        try:
            health = self.health_check()
            if not health.connected:
                return ()
            if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                request_ids: list[tuple[str, str]] = []
                if record.cancel_request_id:
                    request_ids.append(("CANCEL", record.cancel_request_id))
                if record.submit_request_id:
                    request_ids.append(("SUBMIT", record.submit_request_id))
                for request_kind, request_id in request_ids:
                    receipt = self._read_file_bridge_receipt(
                        request_id=request_id,
                        request_kind=request_kind,
                    )
                    if receipt is None:
                        continue
                    update = self._file_bridge_update_from_receipt(receipt)
                    with self._lock:
                        record.updated_at = self._clock()
                        record.last_message = update.message
                        record.stage_state = update.status.value
                        record.broker_observation_state = update.status.value
                        record.last_authoritative_rss_status = update.authoritative_rss_status
                        if update.rss_order_number:
                            record.rss_order_number = update.rss_order_number
                        if update.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                            record.filled_quantity = update.fill_quantity
                            record.filled_price = update.fill_price
                    return (update,)
            elif health.transport_source == TRANSPORT_SOURCE_COM_LIVE:
                session = self._ensure_session()
                self._com_call_count += 1
                updates = self._backend.read_order_updates(session, broker_order_id)
                if not updates:
                    ledger_entry = self._find_rss_order_ledger_entry(
                        session,
                        record.rss_order_id,
                        function_name=ORDER_MACRO_NAME,
                    )
                    try:
                        rss_order_status = self._observe_rss_order_status(session, record.rss_order_id)
                    except ExcelComError:
                        rss_order_status = -1
                    if ledger_entry is not None and ledger_entry.order_number:
                        with self._lock:
                            record.rss_order_number = ledger_entry.order_number
                            record.last_message = ledger_entry.result or record.last_message
                            record.rss_order_status_code = rss_order_status
                            record.last_authoritative_rss_status = rss_order_status
                    normalized_order_result = self._rss_optional_text(
                        ledger_entry.result if ledger_entry is not None else "",
                    ).replace("(", "（").replace(")", "）")
                    cancel_completed_results = {
                        "取消済（出来有）",
                        "取消済（出来無）",
                        "取消済",
                    }
                    if rss_order_status in {1, 2, 3}:
                        if record.cancel_request_id:
                            if rss_order_status == 3:
                                synthetic_status = OrderStatus.PENDING
                            elif rss_order_status == 1 and normalized_order_result in cancel_completed_results:
                                synthetic_status = OrderStatus.CANCELED
                            else:
                                synthetic_status = OrderStatus.PENDING
                        else:
                            if rss_order_status == 1:
                                synthetic_status = OrderStatus.REJECTED
                            elif rss_order_status == 3:
                                synthetic_status = OrderStatus.PENDING
                            else:
                                synthetic_status = OrderStatus.ACCEPTED
                        synthetic_update = RakutenRssOrderUpdate(
                            status=synthetic_status,
                            fill_quantity=record.filled_quantity if synthetic_status is OrderStatus.FILLED else 0,
                            fill_price=record.filled_price if synthetic_status is OrderStatus.FILLED else 0.0,
                            message=record.last_message or f"RssOrderStatus={rss_order_status}",
                            updated_at=self._clock(),
                            rss_order_status=str(rss_order_status),
                            rss_order_id=record.rss_order_id,
                            rss_order_number=record.rss_order_number,
                            authoritative_rss_status=rss_order_status,
                        )
                        with self._lock:
                            record.updated_at = synthetic_update.updated_at
                            record.last_message = synthetic_update.message
                            record.stage_state = synthetic_status.value
                            record.broker_observation_state = synthetic_status.value
                        return (synthetic_update,)
            else:
                return ()
        except ExcelComError as error:
            with self._lock:
                record.stage_state = OrderStatus.REJECTED.value
                record.last_message = str(error)
                record.updated_at = self._clock()
            return ()

        if updates:
            with self._lock:
                record.updated_at = self._clock()
                final_update = updates[-1]
                record.broker_observation_state = final_update.status.value
                record.last_authoritative_rss_status = getattr(final_update, "authoritative_rss_status", -1)
                if getattr(final_update, "rss_order_number", ""):
                    record.rss_order_number = str(final_update.rss_order_number)
                if final_update.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                    record.filled_quantity = final_update.fill_quantity
                    record.filled_price = final_update.fill_price
                if final_update.status is OrderStatus.TIMED_OUT:
                    record.broker_observation_state = "RECONCILE_PENDING"
                    record.last_message = final_update.message
                    record.updated_at = self._clock()
                elif final_update.status in {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED}:
                    record.stage_state = final_update.status.value
                else:
                    record.stage_state = final_update.status.value
                record.last_message = final_update.message
            return updates

        with self._lock:
            age = self._clock() - record.submitted_at
            if self._timeout_seconds == 0 or age >= timedelta(seconds=self._timeout_seconds):
                current_status = self._tracked_order_status(record)
                timeout_update = RakutenRssOrderUpdate(
                    status=current_status,
                    message="Order timed out waiting for Excel/RSS result; reconciliation continues.",
                    updated_at=self._clock(),
                    rss_order_status="TIMED_OUT",
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
                record.broker_observation_state = "RECONCILE_PENDING"
                record.last_message = timeout_update.message
                record.updated_at = timeout_update.updated_at
                return (timeout_update,)
        return ()

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        gate_message = self._gate_message()
        if gate_message:
            return RakutenRssCancelAck(
                status=OrderStatus.REJECTED,
                message=gate_message,
            )

        with self._lock:
            record = self._orders.get(broker_order_id)
        if record is None:
            return RakutenRssCancelAck(
                status=OrderStatus.REJECTED,
                message=f"Unknown broker_order_id: {broker_order_id}",
                rss_order_id=0,
                rss_order_number="",
                authoritative_rss_status=-1,
            )
        if record.cancel_request_id:
            return self._tracked_cancel_ack(record)

        submitted_at = self._clock()
        payload = self._build_cancel_payload(record, submitted_at)
        with self._lock:
            self._last_cancel_payload = dict(payload)
            record.cancel_payload = dict(payload)
            record.cancel_request_id = self._file_bridge_request_id("CANCEL", broker_order_id)

        try:
            health = self.health_check()
            if not health.connected:
                return RakutenRssCancelAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
            if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                request_id = self._file_bridge_request_id("CANCEL", broker_order_id)
                try:
                    bridge_result = self._stage_file_bridge_request(
                        request_kind="CANCEL",
                        request_id=request_id,
                        payload=payload,
                        submitted_at=submitted_at,
                    )
                except Exception as error:
                    with self._lock:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = f"FILE_READY cancel staging failed: {error}"
                        record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.REJECTED,
                        message=f"FILE_READY cancel staging failed: {error}",
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
                with self._lock:
                    record.cancel_request_id = request_id
                    record.stage_state = OrderStatus.PENDING.value
                    record.cancel_observation_state = OrderStatus.PENDING.value
                    record.last_message = (
                        "FILE_READY cancel request staged."
                        if not bridge_result.duplicate
                        else "FILE_READY cancel request already staged."
                    )
                    record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.PENDING,
                        message=record.last_message,
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
            if health.transport_source != TRANSPORT_SOURCE_COM_LIVE:
                return RakutenRssCancelAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
            session = self._ensure_session()
            self._com_call_count += 1
            if not self._armed:
                with self._lock:
                    record.stage_state = OrderStatus.REJECTED.value
                    record.last_message = "production_live_fire_armed=false; cancel staging disabled."
                    record.updated_at = self._clock()
                return RakutenRssCancelAck(
                    status=OrderStatus.REJECTED,
                    message="production_live_fire_armed=false; cancel staging disabled.",
                    canceled_at=submitted_at,
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
            ledger_entry = self._find_rss_order_ledger_entry(
                session,
                record.rss_order_id,
                function_name=ORDER_MACRO_NAME,
            )
            order_number = record.rss_order_number or (ledger_entry.order_number if ledger_entry is not None else "")
            if not str(order_number).strip():
                with self._lock:
                    record.cancel_observation_state = "WAITING_FOR_ORDER_NUMBER"
                    record.last_message = "RSS order number is missing for cancel."
                    record.updated_at = self._clock()
                return self._tracked_cancel_ack(record, message="RSS order number is missing for cancel.")
            self._backend.stage_cancel_payload(session, payload)
            cancel_args = self._build_rss_cancel_order_arguments(record.rss_order_id, order_number)
            self._com_call_count += 1
            self._cancel_macro_call_count += 1
            self._backend.invoke_cancel_macro(session, CANCEL_MACRO_NAME, *cancel_args)
            try:
                rss_order_status = self._observe_rss_order_status(session, record.rss_order_id)
            except ExcelComError:
                rss_order_status = -1
            with self._lock:
                record.rss_order_number = order_number
                record.rss_order_status_code = rss_order_status
                record.last_authoritative_rss_status = rss_order_status
                if rss_order_status == 3:
                    record.stage_state = OrderStatus.PENDING.value
                    record.cancel_observation_state = OrderStatus.PENDING.value
                    record.last_message = "RssOrderStatus=3"
                    record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.PENDING,
                        message="RssOrderStatus=3",
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
                normalized_order_result = self._rss_optional_text(
                    ledger_entry.result if ledger_entry is not None else "",
                ).replace("(", "（").replace(")", "）")
                cancel_completed_results = {
                    "取消済（出来有）",
                    "取消済（出来無）",
                    "取消済",
                }
                if rss_order_status == 1 and normalized_order_result in cancel_completed_results:
                    record.stage_state = OrderStatus.CANCELED.value
                    record.cancel_observation_state = OrderStatus.CANCELED.value
                    record.last_message = normalized_order_result
                    record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.CANCELED,
                        message=normalized_order_result,
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
                record.stage_state = OrderStatus.PENDING.value
                record.cancel_observation_state = OrderStatus.PENDING.value
                record.last_message = (
                    normalized_order_result
                    if normalized_order_result in {"出来ず（出来有）", "出来ず（出来無）"}
                    else "Cancel request observed but order status is still terminal-free."
                )
                record.updated_at = self._clock()
            return RakutenRssCancelAck(
                status=OrderStatus.PENDING,
                message=record.last_message,
                canceled_at=submitted_at,
                rss_order_id=record.rss_order_id,
                rss_order_number=record.rss_order_number,
                authoritative_rss_status=record.last_authoritative_rss_status,
            )
        except ExcelComError as error:
            with self._lock:
                record.stage_state = OrderStatus.REJECTED.value
                record.last_message = str(error)
                record.updated_at = self._clock()
            return RakutenRssCancelAck(
                status=OrderStatus.REJECTED,
                message=str(error),
                canceled_at=submitted_at,
                rss_order_id=record.rss_order_id,
                rss_order_number=record.rss_order_number,
                authoritative_rss_status=record.last_authoritative_rss_status,
            )
