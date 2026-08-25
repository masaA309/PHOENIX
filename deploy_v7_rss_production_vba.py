from __future__ import annotations

import ctypes
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
import uuid
from typing import Any, Callable, Mapping, Sequence
from ctypes import wintypes


ROOT_DIR = Path(__file__).resolve().parent
VBA_DIR = ROOT_DIR / "vba"
TARGET_WORKBOOK_PATH = (ROOT_DIR / "runtime" / "v7_rss_production" / "PHOENIX_RSS_PRODUCTION.xlsm").resolve()
TARGET_SOURCE_PATHS = {
    "PHOENIX_RSS_ORDER_BRIDGE": VBA_DIR / "PHOENIX_RSS_ORDER_BRIDGE.bas",
    "ThisWorkbook": VBA_DIR / "ThisWorkbook.cls",
}
TARGET_COMPONENT_NAMES = tuple(TARGET_SOURCE_PATHS.keys())
EXCEL_APPLICATION_PROG_ID = "Excel.Application"
FORCE_DISABLE_AUTOMATION_SECURITY = 3
OBJID_NATIVEOM = -16
IID_IDISPATCH_TEXT = "00020400-0000-0000-C000-000000000046"
DESKTOP_READOBJECTS = 0x0001
UOI_NAME = 2
TH32CS_SNAPPROCESS = 0x00000002
MAX_PATH = 260
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
ERROR_NO_MORE_FILES = 18


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * MAX_PATH),
    ]


class DeploymentError(RuntimeError):
    pass


class DeploymentPreflightError(DeploymentError):
    pass


class DeploymentVerificationError(DeploymentError):
    pass


class DeploymentRollbackError(DeploymentError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentRuntime:
    win32_client: Any
    pythoncom: Any


@dataclass(frozen=True, slots=True)
class DeploymentReport:
    deployed: bool
    workbook_path: Path
    backup_path: Path | None
    changed_modules: tuple[str, ...]
    preserved_modules: tuple[str, ...]
    verification: dict[str, bool] = field(default_factory=dict)
    message: str = ""


@dataclass(frozen=True, slots=True)
class WorkbookOwner:
    application: Any
    workbook: Any
    workbook_fullname: str
    application_identity: str
    hwnd: int | None = None
    process_id: int | None = None
    session_id: int | None = None
    display_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowCandidateDiagnostic:
    hwnd: int
    class_name: str
    process_id: int
    session_id: int
    excel7_child_count: int


@dataclass(frozen=True, slots=True)
class WindowEnumerationDiagnostic:
    target_workbook_path: Path
    python_process_id: int
    python_session_id: int
    process_window_station_name: str | None
    process_window_station_error: str | None
    thread_desktop_name: str | None
    thread_desktop_error: str | None
    input_desktop_name: str | None
    input_desktop_error: str | None
    enum_windows_returned: bool
    enum_windows_last_error: int
    enum_windows_callback_calls: int
    enum_windows_callback_returned_false: bool
    enum_windows_callback_exceptions: tuple[str, ...]
    excel_candidates: tuple[WindowCandidateDiagnostic, ...]
    diagnosis: str
    write_intent: int = 0
    save_intent: int = 0
    backup_intent: int = 0
    vba_mutation_intent: int = 0

    def render_lines(self) -> list[str]:
        lines = [
            "READ_ONLY_DIAGNOSTIC: YES",
            f"TARGET_WORKBOOK: {self.target_workbook_path}",
            f"PYTHON_PID: {self.python_process_id}",
            f"PYTHON_SESSION_ID: {self.python_session_id}",
        ]
        if self.process_window_station_error is None:
            lines.append(f"PROCESS_WINDOW_STATION: {self.process_window_station_name}")
        else:
            lines.append(
                "PROCESS_WINDOW_STATION: <unavailable> "
                f"({self.process_window_station_error})"
            )
        if self.thread_desktop_error is None:
            lines.append(f"THREAD_DESKTOP: {self.thread_desktop_name}")
        else:
            lines.append(f"THREAD_DESKTOP: <unavailable> ({self.thread_desktop_error})")
        if self.input_desktop_error is None:
            lines.append(f"INPUT_DESKTOP: {self.input_desktop_name}")
        else:
            lines.append(f"INPUT_DESKTOP: <unavailable> ({self.input_desktop_error})")
        lines.append(
            "ENUM_DESKTOP_WINDOWS: "
            f"return={int(self.enum_windows_returned)} "
            f"last_error={self.enum_windows_last_error} "
            f"callback_calls={self.enum_windows_callback_calls} "
            f"callback_returned_false={int(self.enum_windows_callback_returned_false)} "
            f"callback_exceptions={len(self.enum_windows_callback_exceptions)}"
        )
        for exception_text in self.enum_windows_callback_exceptions:
            lines.append(f"  CALLBACK_EXCEPTION: {exception_text}")
        lines.append(f"EXCEL_TOP_LEVEL_CANDIDATES: {len(self.excel_candidates)}")
        for candidate in self.excel_candidates:
            lines.append(
                "  - "
                f"HWND={candidate.hwnd:#x} "
                f"CLASS={candidate.class_name} "
                f"PID={candidate.process_id} "
                f"SESSION={candidate.session_id} "
                f"EXCEL7_CHILDREN={candidate.excel7_child_count}"
            )
        lines.append(f"DIAGNOSIS: {self.diagnosis}")
        lines.append(f"WRITE={self.write_intent}")
        lines.append(f"SAVE={self.save_intent}")
        lines.append(f"BACKUP={self.backup_intent}")
        lines.append(f"VBA_MUTATION={self.vba_mutation_intent}")
        return lines


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def _require_runtime() -> DeploymentRuntime:
    try:
        from win32com import client as win32_client  # type: ignore[import-not-found]
        import pythoncom  # type: ignore[import-not-found]
    except Exception as exc:
        raise DeploymentPreflightError(f"COM libraries unavailable: {type(exc).__name__}: {exc}") from exc
    return DeploymentRuntime(win32_client=win32_client, pythoncom=pythoncom)


def _normalize_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _extract_vba_code_body(text: str) -> str:
    lines = [line.rstrip() for line in _normalize_lines(text)]
    start_index: int | None = None

    for idx, line in enumerate(lines):
        if line.strip().startswith("Option "):
            start_index = idx
            break

    if start_index is None:
        for idx, line in enumerate(lines):
            token = line.strip()
            if not token:
                continue
            if token.startswith("Attribute "):
                continue
            if token.startswith("VERSION ") or token in {"BEGIN", "END"}:
                continue
            start_index = idx
            break

    if start_index is None:
        return ""

    body_lines: list[str] = []
    for line in lines[start_index:]:
        token = line.strip()
        if token.startswith("Attribute "):
            continue
        if token.startswith("VERSION ") or token in {"BEGIN", "END"}:
            continue
        body_lines.append(line)
    return "\n".join(body_lines).strip()


def _read_source_body(path: Path) -> str:
    return _extract_vba_code_body(path.read_text(encoding="utf-8-sig"))


def _source_paths(source_root: Path) -> dict[str, Path]:
    vba_root = source_root / "vba"
    return {
        "PHOENIX_RSS_ORDER_BRIDGE": vba_root / "PHOENIX_RSS_ORDER_BRIDGE.bas",
        "ThisWorkbook": vba_root / "ThisWorkbook.cls",
    }


def _canonical_path_text(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _component_name(component: Any) -> str:
    return str(getattr(component, "Name", "")).strip()


def _iter_vbcomponents(vbproject: Any) -> list[Any]:
    components = getattr(vbproject, "VBComponents", None)
    if components is None:
        raise DeploymentPreflightError("VBComponents collection is unavailable")
    try:
        return list(components)
    except Exception:
        items: list[Any] = []
        count = int(getattr(components, "Count", 0) or 0)
        for index in range(1, count + 1):
            try:
                items.append(components.Item(index))
            except Exception:
                break
        return items


def _component_code_body(component: Any) -> str:
    module = getattr(component, "CodeModule", None)
    if module is None:
        raise DeploymentPreflightError(f"CodeModule is unavailable for component {_component_name(component)!r}")
    count = int(getattr(module, "CountOfLines", 0) or 0)
    if count <= 0:
        return ""
    try:
        text = str(module.Lines(1, count))
    except Exception as exc:
        raise DeploymentPreflightError(f"Could not read VBA code for component {_component_name(component)!r}") from exc
    return _extract_vba_code_body(text)


def _set_component_code_body(component: Any, body: str) -> None:
    module = getattr(component, "CodeModule", None)
    if module is None:
        raise DeploymentPreflightError(f"CodeModule is unavailable for component {_component_name(component)!r}")
    count = int(getattr(module, "CountOfLines", 0) or 0)
    if count > 0:
        module.DeleteLines(1, count)
    normalized = body.strip()
    if normalized:
        module.InsertLines(1, normalized.replace("\n", "\r\n"))


def _snapshot_vbproject(vbproject: Any) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for component in _iter_vbcomponents(vbproject):
        snapshot[_component_name(component)] = _component_code_body(component)
    return snapshot


def _find_component(vbproject: Any, component_name: str) -> Any:
    for component in _iter_vbcomponents(vbproject):
        if _component_name(component).lower() == component_name.lower():
            return component
    raise DeploymentPreflightError(f"VBComponent not found: {component_name}")


def _read_source_bodies(source_root: Path) -> dict[str, str]:
    source_bodies: dict[str, str] = {}
    source_paths = _source_paths(source_root)
    missing = [path for path in source_paths.values() if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise DeploymentPreflightError(f"Required VBA source file(s) missing: {missing_text}")

    for component_name, source_path in source_paths.items():
        source_bodies[component_name] = _read_source_body(source_path)
    return source_bodies


def _iter_collection_items(collection: Any) -> list[Any]:
    if collection is None:
        return []
    try:
        return list(collection)
    except Exception:
        items: list[Any] = []
        count = int(getattr(collection, "Count", 0) or 0)
        for index in range(1, count + 1):
            try:
                items.append(collection.Item(index))
            except Exception as exc:
                raise DeploymentPreflightError("COM collection could not be enumerated") from exc
        return items


def _com_identity(com_object: Any) -> str:
    try:
        hwnd = getattr(com_object, "Hwnd")
    except Exception:
        hwnd = None
    if hwnd is not None:
        return f"Hwnd:{hwnd}"
    return f"PyId:{id(com_object)}"


def _count_excel_processes() -> int:
    if os.name != "nt":
        raise DeploymentPreflightError("Excel process enumeration is only supported on Windows")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, 0, INVALID_HANDLE_VALUE, -1):
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Excel process enumeration failed: {error}")

    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            error = ctypes.get_last_error()
            if error == ERROR_NO_MORE_FILES:
                return 0
            raise DeploymentPreflightError(f"Excel process enumeration failed: {error}")

        count = 0
        while True:
            if str(entry.szExeFile).upper() == "EXCEL.EXE":
                count += 1
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                error = ctypes.get_last_error()
                if error == ERROR_NO_MORE_FILES:
                    break
                raise DeploymentPreflightError(f"Excel process enumeration failed: {error}")
        return count
    finally:
        try:
            kernel32.CloseHandle(snapshot)
        except Exception:
            pass


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guid_from_text(guid_text: str) -> _GUID:
    normalized = guid_text.strip("{}")
    parsed = uuid.UUID(normalized)
    data = parsed.bytes_le
    return _GUID(
        int.from_bytes(data[0:4], "little"),
        int.from_bytes(data[4:6], "little"),
        int.from_bytes(data[6:8], "little"),
        (ctypes.c_ubyte * 8)(*data[8:16]),
    )


def _current_process_session_id() -> tuple[int, int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcessId.restype = wintypes.DWORD
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL

    process_id = int(kernel32.GetCurrentProcessId())
    session_id = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(process_id, ctypes.byref(session_id)):
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not determine current process session id: {error}")
    return process_id, int(session_id.value)


def _window_process_session_id(hwnd: int) -> tuple[int, int]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL

    process_id = wintypes.DWORD()
    thread_id = int(user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id)))
    if thread_id == 0 or process_id.value == 0:
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not determine process id for HWND {hwnd:#x}: {error}")

    session_id = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(process_id.value, ctypes.byref(session_id)):
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(
            f"Could not determine session id for HWND {hwnd:#x} (pid={process_id.value}): {error}"
        )
    return int(process_id.value), int(session_id.value)


def _user_object_name(user32: Any, handle: int, *, context: str) -> str:
    get_user_object_information = user32.GetUserObjectInformationW
    get_user_object_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPWSTR,
        ctypes.c_ulong,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    get_user_object_information.restype = wintypes.BOOL

    buffer = ctypes.create_unicode_buffer(512)
    needed = ctypes.c_ulong()
    if not get_user_object_information(handle, UOI_NAME, buffer, len(buffer), ctypes.byref(needed)):
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not determine {context} name: {error}")
    return buffer.value


def _current_process_window_station_name() -> str:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetProcessWindowStation.restype = wintypes.HANDLE
    window_station = user32.GetProcessWindowStation()
    if not window_station:
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not determine current process window station: {error}")
    return _user_object_name(user32, int(window_station), context="process window station")


def _current_thread_desktop_name() -> str:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
    user32.GetThreadDesktop.restype = wintypes.HANDLE

    thread_id = int(kernel32.GetCurrentThreadId())
    desktop = user32.GetThreadDesktop(thread_id)
    if not desktop:
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not determine current thread desktop: {error}")
    return _user_object_name(user32, int(desktop), context="thread desktop")


@dataclass(slots=True)
class _EnumTrace:
    returned: bool = False
    last_error: int = 0
    callback_calls: int = 0
    callback_returned_false: bool = False
    callback_exceptions: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _InputDesktopScan:
    input_desktop_name: str | None
    input_desktop_error: str | None
    enum_trace: _EnumTrace
    candidates: tuple[WindowCandidateDiagnostic, ...]
    excel7_window_handles: tuple[int, ...]


def _open_input_desktop_handle(user32: Any) -> int:
    open_input_desktop = user32.OpenInputDesktop
    open_input_desktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_input_desktop.restype = wintypes.HANDLE

    desktop_handle = open_input_desktop(0, False, DESKTOP_READOBJECTS)
    desktop_handle_value = int(desktop_handle or 0)
    if desktop_handle_value == 0:
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not open input desktop: {error}")
    return desktop_handle_value


def _close_desktop_handle(user32: Any, desktop_handle: int) -> None:
    close_desktop = user32.CloseDesktop
    close_desktop.argtypes = [wintypes.HANDLE]
    close_desktop.restype = wintypes.BOOL

    if not close_desktop(desktop_handle):
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not close input desktop: {error}")


def _class_name_for_window(user32: Any, hwnd: int) -> str:
    get_class_name = user32.GetClassNameW
    get_class_name.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    get_class_name.restype = ctypes.c_int
    buffer = ctypes.create_unicode_buffer(256)
    if get_class_name(hwnd, buffer, len(buffer)) == 0:
        error = ctypes.get_last_error()
        raise DeploymentPreflightError(f"Could not determine class name for HWND {hwnd:#x}: {error}")
    return buffer.value


def _excel7_child_count_for_window(user32: Any, hwnd: int) -> int:
    return len(_excel7_child_handles_for_window(user32, hwnd))


def _excel7_child_handles_for_window(user32: Any, hwnd: int) -> list[int]:
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    enum_child_windows = user32.EnumChildWindows
    enum_child_windows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
    enum_child_windows.restype = wintypes.BOOL

    trace = _EnumTrace()
    excel7_handles: list[int] = []
    seen_handles: set[int] = set()

    @WNDENUMPROC
    def _collect(child_hwnd: int, _lparam: int) -> bool:
        trace.callback_calls += 1
        try:
            child_hwnd_int = int(child_hwnd)
            if _class_name_for_window(user32, child_hwnd_int).upper() == "EXCEL7" and child_hwnd_int not in seen_handles:
                seen_handles.add(child_hwnd_int)
                excel7_handles.append(child_hwnd_int)
        except Exception as exc:
            trace.callback_exceptions.append(str(exc))
            return False
        return True

    ctypes.set_last_error(0)
    trace.returned = bool(enum_child_windows(hwnd, _collect, 0))
    trace.last_error = int(ctypes.get_last_error())
    return excel7_handles


def _collect_excel_window_diagnostics() -> _InputDesktopScan:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    enum_desktop_windows = user32.EnumDesktopWindows
    enum_desktop_windows.argtypes = [wintypes.HANDLE, WNDENUMPROC, wintypes.LPARAM]
    enum_desktop_windows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL

    desktop_handle: int | None = None
    input_desktop_name: str | None = None
    input_desktop_error: str | None = None
    trace = _EnumTrace()
    candidates: list[WindowCandidateDiagnostic] = []
    excel7_window_handles: list[int] = []
    seen_excel7_window_handles: set[int] = set()

    def _candidate_body(hwnd_value: int) -> WindowCandidateDiagnostic | None:
        class_name = _class_name_for_window(user32, hwnd_value)
        process_id = wintypes.DWORD()
        thread_id = int(user32.GetWindowThreadProcessId(hwnd_value, ctypes.byref(process_id)))
        if thread_id == 0 or process_id.value == 0:
            error = ctypes.get_last_error()
            raise DeploymentPreflightError(f"Could not determine process id for HWND {hwnd_value:#x}: {error}")
        session_id = wintypes.DWORD()
        if not kernel32.ProcessIdToSessionId(process_id.value, ctypes.byref(session_id)):
            error = ctypes.get_last_error()
            raise DeploymentPreflightError(
                f"Could not determine session id for HWND {hwnd_value:#x} (pid={process_id.value}): {error}"
            )
        excel7_child_handles = _excel7_child_handles_for_window(user32, hwnd_value)
        excel7_child_count = len(excel7_child_handles)
        if class_name.upper() == "XLMAIN" or excel7_child_count > 0:
            for excel7_child_handle in excel7_child_handles:
                if excel7_child_handle in seen_excel7_window_handles:
                    continue
                seen_excel7_window_handles.add(excel7_child_handle)
                excel7_window_handles.append(excel7_child_handle)
            return WindowCandidateDiagnostic(
                hwnd=hwnd_value,
                class_name=class_name,
                process_id=int(process_id.value),
                session_id=int(session_id.value),
                excel7_child_count=excel7_child_count,
            )
        return None

    @WNDENUMPROC
    def _collect(hwnd: int, _lparam: int) -> bool:
        trace.callback_calls += 1
        try:
            candidate = _candidate_body(int(hwnd))
        except Exception as exc:
            trace.callback_exceptions.append(str(exc))
            return False
        if candidate is None:
            return True
        candidates.append(candidate)
        return True

    try:
        desktop_handle = _open_input_desktop_handle(user32)
        input_desktop_name = _user_object_name(user32, desktop_handle, context="input desktop")
        ctypes.set_last_error(0)
        trace.returned = bool(enum_desktop_windows(desktop_handle, _collect, 0))
        trace.last_error = int(ctypes.get_last_error())
    except Exception as exc:
        input_desktop_error = str(exc)
    finally:
        if desktop_handle not in (None, 0):
            try:
                _close_desktop_handle(user32, int(desktop_handle))
            except Exception as exc:
                if input_desktop_error is None:
                    input_desktop_error = str(exc)
                else:
                    input_desktop_error = f"{input_desktop_error}; {exc}"

    return _InputDesktopScan(
        input_desktop_name=input_desktop_name,
        input_desktop_error=input_desktop_error,
        enum_trace=trace,
        candidates=tuple(candidates),
        excel7_window_handles=tuple(excel7_window_handles),
    )


def _classify_excel_window_diagnostic(
    *,
    python_session_id: int,
    process_window_station_error: str | None,
    input_desktop_error: str | None,
    enum_trace: _EnumTrace,
    candidates: list[WindowCandidateDiagnostic],
) -> str:
    if process_window_station_error is not None:
        return "SESSION_WINDOW_STATION_UNAVAILABLE"
    if input_desktop_error is not None:
        if "Could not open input desktop" in input_desktop_error:
            return "INPUT_DESKTOP_OPEN_FAILED"
        if "Could not close input desktop" in input_desktop_error:
            return "INPUT_DESKTOP_CLOSE_FAILED"
        if "Could not determine input desktop name" in input_desktop_error:
            return "INPUT_DESKTOP_NAME_UNAVAILABLE"
        return "INPUT_DESKTOP_UNAVAILABLE"
    if not enum_trace.returned:
        if enum_trace.callback_exceptions:
            return "ENUM_DESKTOP_WINDOWS_CALLBACK_EXCEPTION"
        if enum_trace.callback_returned_false:
            return "ENUM_DESKTOP_WINDOWS_CALLBACK_FALSE"
        if enum_trace.callback_calls == 0:
            return "ENUM_DESKTOP_WINDOWS_NO_CALLBACKS_OR_INPUT_DESKTOP_INVISIBLE"
        return "ENUM_DESKTOP_WINDOWS_API_OR_INPUT_DESKTOP_FAILURE"
    if not candidates:
        return "EXCEL_WINDOW_NOT_VISIBLE_ON_INPUT_DESKTOP"
    if any(candidate.session_id != python_session_id for candidate in candidates):
        return "EXCEL_SESSION_MISMATCH"
    if any(candidate.excel7_child_count > 0 for candidate in candidates):
        return "EXCEL_VISIBLE_AND_EXCEL7_FOUND"
    return "EXCEL_VISIBLE_BUT_EXCEL7_SEARCH_FAILED"


def diagnose_excel_window_enumeration() -> WindowEnumerationDiagnostic:
    python_process_id, python_session_id = _current_process_session_id()

    process_window_station_name: str | None
    process_window_station_error: str | None
    try:
        process_window_station_name = _current_process_window_station_name()
        process_window_station_error = None
    except Exception as exc:
        process_window_station_name = None
        process_window_station_error = str(exc)

    thread_desktop_name: str | None
    thread_desktop_error: str | None
    try:
        thread_desktop_name = _current_thread_desktop_name()
        thread_desktop_error = None
    except Exception as exc:
        thread_desktop_name = None
        thread_desktop_error = str(exc)

    scan = _collect_excel_window_diagnostics()
    enum_trace = scan.enum_trace
    candidates = list(scan.candidates)
    diagnosis = _classify_excel_window_diagnostic(
        python_session_id=python_session_id,
        process_window_station_error=process_window_station_error,
        input_desktop_error=scan.input_desktop_error,
        enum_trace=enum_trace,
        candidates=candidates,
    )
    return WindowEnumerationDiagnostic(
        target_workbook_path=TARGET_WORKBOOK_PATH,
        python_process_id=python_process_id,
        python_session_id=python_session_id,
        process_window_station_name=process_window_station_name,
        process_window_station_error=process_window_station_error,
        thread_desktop_name=thread_desktop_name,
        thread_desktop_error=thread_desktop_error,
        input_desktop_name=scan.input_desktop_name,
        input_desktop_error=scan.input_desktop_error,
        enum_windows_returned=enum_trace.returned,
        enum_windows_last_error=enum_trace.last_error,
        enum_windows_callback_calls=enum_trace.callback_calls,
        enum_windows_callback_returned_false=enum_trace.callback_returned_false,
        enum_windows_callback_exceptions=tuple(enum_trace.callback_exceptions),
        excel_candidates=tuple(candidates),
        diagnosis=diagnosis,
    )


def _enum_excel7_window_handles() -> list[int]:
    if os.name != "nt":
        raise DeploymentPreflightError("Excel window enumeration is only supported on Windows")

    scan = _collect_excel_window_diagnostics()
    if scan.input_desktop_error is not None:
        raise DeploymentPreflightError(f"Excel input desktop enumeration failed: {scan.input_desktop_error}")
    if not scan.enum_trace.returned:
        error_suffix = f": {scan.enum_trace.last_error}" if scan.enum_trace.last_error else ""
        raise DeploymentPreflightError(f"Excel desktop window enumeration failed{error_suffix}")
    if not scan.excel7_window_handles:
        suffix = f"; EXCEL7 HWNDs={[candidate.hwnd for candidate in scan.candidates]!r}" if scan.candidates else ""
        raise DeploymentPreflightError(f"Canonical workbook owner not found on input desktop: {TARGET_WORKBOOK_PATH}{suffix}")
    return list(scan.excel7_window_handles)


def _accessible_object_from_window(win32_client: Any, pythoncom: Any, hwnd: int) -> Any:
    oleacc = ctypes.WinDLL("oleacc", use_last_error=True)
    accessible_object_from_window = oleacc.AccessibleObjectFromWindow
    accessible_object_from_window.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    accessible_object_from_window.restype = wintypes.HRESULT if hasattr(wintypes, "HRESULT") else ctypes.c_long

    result = ctypes.c_void_p()
    riid = _guid_from_text(IID_IDISPATCH_TEXT)
    hr = int(accessible_object_from_window(hwnd, OBJID_NATIVEOM, ctypes.byref(riid), ctypes.byref(result)))
    if hr != 0:
        raise DeploymentPreflightError(f"AccessibleObjectFromWindow failed for HWND {hwnd:#x}: {hr}")
    if not result.value:
        raise DeploymentPreflightError(f"AccessibleObjectFromWindow returned no object for HWND {hwnd:#x}")
    try:
        native_dispatch = pythoncom.ObjectFromAddress(int(result.value), pythoncom.IID_IDispatch)
    except Exception as exc:
        raise DeploymentPreflightError(f"AccessibleObjectFromWindow wrapping failed for HWND {hwnd:#x}: {exc}") from exc
    if native_dispatch is None:
        raise DeploymentPreflightError(f"AccessibleObjectFromWindow returned a null dispatch proxy for HWND {hwnd:#x}")
    try:
        wrapped_window = win32_client.Dispatch(native_dispatch)
    except Exception as exc:
        raise DeploymentPreflightError(f"AccessibleObjectFromWindow dispatch wrapping failed for HWND {hwnd:#x}: {exc}") from exc
    if wrapped_window is None:
        raise DeploymentPreflightError(f"AccessibleObjectFromWindow dispatch wrapping returned no object for HWND {hwnd:#x}")
    return wrapped_window


def _workbooks_matching_fullname(application: Any, workbook_path: Path) -> list[Any]:
    canonical_path = _canonical_path_text(workbook_path)
    try:
        workbooks = getattr(application, "Workbooks")
    except Exception as exc:
        raise DeploymentPreflightError(f"Excel Workbooks collection is unavailable: {exc}") from exc

    matches: list[Any] = []
    for candidate in _iter_collection_items(workbooks):
        try:
            candidate_fullname = _canonical_path_text(Path(str(getattr(candidate, "FullName"))))
        except Exception as exc:
            raise DeploymentPreflightError(f"Workbook FullName is unavailable: {exc}") from exc
        if candidate_fullname == canonical_path:
            matches.append(candidate)
    return matches


def _validate_resolved_owner(
    owner: WorkbookOwner,
    workbook_path: Path,
    *,
    runtime: DeploymentRuntime,
) -> WorkbookOwner:
    _current_process_id, current_session_id = _current_process_session_id()
    refreshed_owner = _resolve_canonical_workbook_owner(runtime.win32_client, workbook_path, runtime.pythoncom)
    if owner.process_id is not None and refreshed_owner.process_id != owner.process_id:
        raise DeploymentPreflightError(
            "Canonical workbook owner process changed before mutation: "
            f"expected {owner.process_id}, got {refreshed_owner.process_id}"
        )
    if refreshed_owner.application_identity != owner.application_identity:
        raise DeploymentPreflightError(
            "Canonical workbook owner changed before mutation: "
            f"expected {owner.application_identity}, got {refreshed_owner.application_identity}"
        )
    if refreshed_owner.workbook_fullname != owner.workbook_fullname:
        raise DeploymentPreflightError(
            "Canonical workbook FullName changed before mutation: "
            f"expected {owner.workbook_fullname}, got {refreshed_owner.workbook_fullname}"
        )
    if refreshed_owner.session_id != current_session_id:
        raise DeploymentPreflightError(
            f"Canonical workbook owner session mismatch: current={current_session_id}, owner={refreshed_owner.session_id}"
        )
    try:
        if bool(getattr(refreshed_owner.workbook, "ReadOnly", False)):
            raise DeploymentPreflightError("Production workbook is read-only")
    except AttributeError as exc:
        raise DeploymentPreflightError(f"Workbook ReadOnly state is unavailable: {exc}") from exc
    try:
        if not bool(getattr(refreshed_owner.workbook, "Saved")):
            raise DeploymentPreflightError("Production workbook has unsaved changes")
    except AttributeError as exc:
        raise DeploymentPreflightError(f"Workbook Saved state is unavailable: {exc}") from exc
    return refreshed_owner


def _resolve_canonical_workbook_owner(
    win32_client: Any,
    workbook_path: Path,
    pythoncom: Any,
) -> WorkbookOwner:
    current_process_id, current_session_id = _current_process_session_id()
    window_handles = _enum_excel7_window_handles()
    if not window_handles:
        raise DeploymentPreflightError(f"Canonical workbook owner not found on current desktop: {workbook_path}")

    matches: list[WorkbookOwner] = []
    seen_candidates: set[tuple[str, str]] = set()
    window_logs: list[str] = []

    for hwnd in window_handles:
        process_id, window_session_id = _window_process_session_id(hwnd)
        if window_session_id != current_session_id:
            raise DeploymentPreflightError(
                f"Excel window session mismatch for HWND {hwnd:#x}: "
                f"current session={current_session_id}, window session={window_session_id}, pid={process_id}"
            )
        window_logs.append(f"HWND:{hwnd:#x}/PID:{process_id}/SESSION:{window_session_id}")
        try:
            native_window = _accessible_object_from_window(win32_client, pythoncom, hwnd)
        except DeploymentError:
            raise
        except Exception as exc:
            raise DeploymentPreflightError(f"AccessibleObjectFromWindow failed for HWND {hwnd:#x}: {exc}") from exc

        try:
            application = getattr(native_window, "Application", None)
        except Exception as exc:
            raise DeploymentPreflightError(f"Excel native object Application is unavailable for HWND {hwnd:#x}: {exc}") from exc
        if application is None:
            raise DeploymentPreflightError(f"Excel native object has no Application for HWND {hwnd:#x}")

        try:
            application_identity = _com_identity(application)
        except Exception as exc:
            raise DeploymentPreflightError(f"Could not identify Excel application for HWND {hwnd:#x}: {exc}") from exc

        for workbook in _workbooks_matching_fullname(application, workbook_path):
            try:
                workbook_fullname = _canonical_path_text(Path(str(getattr(workbook, "FullName"))))
            except Exception as exc:
                raise DeploymentPreflightError(f"Workbook FullName is unavailable: {exc}") from exc
            candidate_key = (application_identity, workbook_fullname)
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            matches.append(
                WorkbookOwner(
                    application=application,
                    workbook=workbook,
                    workbook_fullname=workbook_fullname,
                    application_identity=application_identity,
                    hwnd=hwnd,
                    process_id=process_id,
                    session_id=window_session_id,
                    display_names=(f"HWND:{hwnd:#x}",),
                )
            )

    if len(matches) != 1:
        if len(matches) == 0:
            suffix = f"; EXCEL7 HWNDs={window_logs!r}" if window_logs else ""
            raise DeploymentPreflightError(f"Canonical workbook owner not found: {workbook_path}{suffix}")
        owner_summaries = ", ".join(
            f"{candidate.display_names[0] if candidate.display_names else '<unnamed>'} -> {candidate.workbook_fullname}"
            for candidate in matches
        )
        raise DeploymentPreflightError(
            f"Canonical workbook owner is ambiguous: {workbook_path}; matches={owner_summaries}"
        )

    owner = matches[0]
    if owner.session_id != current_session_id:
        raise DeploymentPreflightError(
            f"Canonical workbook owner session mismatch: current={current_session_id}, owner={owner.session_id}"
        )
    return owner


def _capture_excel_state(application: Any) -> dict[str, Any]:
    try:
        return {
            "EnableEvents": bool(application.EnableEvents),
            "DisplayAlerts": bool(application.DisplayAlerts),
            "AutomationSecurity": getattr(application, "AutomationSecurity"),
        }
    except Exception as exc:
        raise DeploymentPreflightError(f"Could not capture Excel application state: {exc}") from exc


def _restore_excel_state(application: Any, state: Mapping[str, Any]) -> None:
    try:
        application.EnableEvents = state["EnableEvents"]
    except Exception:
        pass
    try:
        application.DisplayAlerts = state["DisplayAlerts"]
    except Exception:
        pass
    try:
        application.AutomationSecurity = state["AutomationSecurity"]
    except Exception:
        pass


def _prepare_excel_instance(application: Any) -> dict[str, Any]:
    original_state = _capture_excel_state(application)
    try:
        application.EnableEvents = False
        application.DisplayAlerts = False
        application.AutomationSecurity = FORCE_DISABLE_AUTOMATION_SECURITY
    except Exception as exc:
        _restore_excel_state(application, original_state)
        raise DeploymentPreflightError(f"Could not disable Excel automation: {exc}") from exc
    return original_state


def _macro_reference(workbook_name: str, procedure_name: str) -> str:
    escaped_name = workbook_name.replace("'", "''")
    return f"'{escaped_name}'!{procedure_name}"


def _run_workbook_macro(application: Any, workbook_name: str, procedure_name: str) -> None:
    try:
        application.Run(_macro_reference(workbook_name, procedure_name))
    except Exception as exc:
        raise DeploymentPreflightError(f"Could not run macro {procedure_name}: {exc}") from exc


def _stop_step44_scheduler(owner: WorkbookOwner) -> None:
    _run_workbook_macro(owner.application, owner.workbook.Name, "StopPhoenixStep44ReceiverScheduler")


def _create_backup(
    workbook_path: Path,
    *,
    timestamp_factory: Callable[[], datetime] | None = None,
) -> tuple[Path, str]:
    now = timestamp_factory() if timestamp_factory is not None else datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S_%f")
    backup_path = workbook_path.with_name(
        f"{workbook_path.stem}.deploy_backup_{timestamp}{workbook_path.suffix}"
    )
    if backup_path.exists():
        suffix = 1
        while True:
            candidate = workbook_path.with_name(
                f"{workbook_path.stem}.deploy_backup_{timestamp}_{suffix}{workbook_path.suffix}"
            )
            if not candidate.exists():
                backup_path = candidate
                break
            suffix += 1

    original_hash = _file_sha256(workbook_path)
    shutil.copy2(workbook_path, backup_path)
    backup_hash = _file_sha256(backup_path)
    if backup_hash != original_hash:
        raise DeploymentPreflightError(
            f"Backup hash mismatch for {backup_path}: expected {original_hash}, got {backup_hash}"
        )
    return backup_path, original_hash


def _close_workbook_best_effort(workbook: Any) -> None:
    try:
        workbook.Close(False)
    except Exception:
        pass


def _close_workbook_or_fail(workbook: Any) -> None:
    try:
        workbook.Close(False)
    except Exception as exc:
        raise DeploymentError(f"Workbook close failed: {exc}") from exc


def _apply_target_module_updates(vbproject: Any, source_bodies: Mapping[str, str]) -> None:
    for component_name in TARGET_COMPONENT_NAMES:
        component = _find_component(vbproject, component_name)
        _set_component_code_body(component, source_bodies[component_name])


def _verify_deployment_state(
    *,
    before_snapshot: Mapping[str, str],
    after_snapshot: Mapping[str, str],
    source_bodies: Mapping[str, str],
) -> dict[str, bool]:
    verification: dict[str, bool] = {}

    for component_name in TARGET_COMPONENT_NAMES:
        expected = source_bodies[component_name].strip()
        actual = after_snapshot.get(component_name, "").strip()
        if actual != expected:
            raise DeploymentVerificationError(
                f"Target module mismatch after save: {component_name}"
            )
        verification[f"{component_name}_updated"] = True

    before_non_target = {name for name in before_snapshot if name not in TARGET_COMPONENT_NAMES}
    after_non_target = {name for name in after_snapshot if name not in TARGET_COMPONENT_NAMES}
    if before_non_target != after_non_target:
        raise DeploymentVerificationError(
            "Non-target VBComponent set changed unexpectedly"
        )

    for component_name, before_body in before_snapshot.items():
        if component_name in TARGET_COMPONENT_NAMES:
            continue
        after_body = after_snapshot.get(component_name)
        if after_body != before_body:
            raise DeploymentVerificationError(
                f"Non-target VBComponent changed unexpectedly: {component_name}"
            )
        verification[f"{component_name}_preserved"] = True

    thisworkbook_body = after_snapshot.get("ThisWorkbook", "")
    bridge_body = after_snapshot.get("PHOENIX_RSS_ORDER_BRIDGE", "")

    required_hooks = {
        "ThisWorkbook": (
            "Workbook_Open",
            "Workbook_BeforeClose",
            "StartPhoenixStep44ReceiverScheduler",
            "StopPhoenixStep44ReceiverScheduler",
            "StartPhoenixRssOrderBridgeScheduler",
            "StopPhoenixRssOrderBridgeScheduler",
        ),
        "PHOENIX_RSS_ORDER_BRIDGE": (
            "RunPhoenixRssOrderBridgeConsumer",
            "Public Sub StartPhoenixRssOrderBridgeScheduler()",
            "Public Sub StopPhoenixRssOrderBridgeScheduler()",
            "OBR_BRIDGE_ARMED As Boolean = False",
            "Application.OnTime",
            "Schedule:=True",
            "Schedule:=False",
        ),
    }
    for needle in required_hooks["ThisWorkbook"]:
        if needle not in thisworkbook_body:
            raise DeploymentVerificationError(f"ThisWorkbook hook missing after save: {needle}")
        verification[f"ThisWorkbook_has_{needle}"] = True

    for needle in required_hooks["PHOENIX_RSS_ORDER_BRIDGE"]:
        if needle not in bridge_body:
            raise DeploymentVerificationError(f"Order bridge module missing after save: {needle}")
        verification[f"PHOENIX_RSS_ORDER_BRIDGE_has_{needle}"] = True

    if "RssStockOrder_V(" in bridge_body:
        raise DeploymentVerificationError("Order bridge module still contains RssStockOrder_V(")
    if "RssCancelOrder_V(" in bridge_body:
        raise DeploymentVerificationError("Order bridge module still contains RssCancelOrder_V(")
    verification["dry_run_safe"] = True

    if "StartPhoenixStep44ReceiverScheduler" not in thisworkbook_body:
        raise DeploymentVerificationError("Step44 start hook missing after save")
    if "StopPhoenixStep44ReceiverScheduler" not in thisworkbook_body:
        raise DeploymentVerificationError("Step44 stop hook missing after save")
    verification["step44_hooks_preserved"] = True

    return verification


def _restore_backup(
    workbook_path: Path,
    backup_path: Path,
    *,
    expected_hash: str | None = None,
) -> None:
    try:
        shutil.copy2(backup_path, workbook_path)
    except Exception as exc:
        raise DeploymentRollbackError(
            f"Rollback failed while restoring production workbook from {backup_path}: {exc}"
        ) from exc
    if expected_hash is not None:
        restored_hash = _file_sha256(workbook_path)
        if restored_hash != expected_hash:
            raise DeploymentRollbackError(
                f"Rollback hash mismatch for {workbook_path}: expected {expected_hash}, got {restored_hash}"
            )


def _deploy_vba_to_path(
    workbook_path: Path,
    *,
    source_root: Path = ROOT_DIR,
    runtime: DeploymentRuntime | None = None,
    timestamp_factory: Callable[[], datetime] | None = None,
) -> DeploymentReport:
    runtime = runtime or _require_runtime()
    workbook_path = workbook_path.resolve()
    source_root = source_root.resolve()

    if workbook_path != TARGET_WORKBOOK_PATH and workbook_path.name != TARGET_WORKBOOK_PATH.name:
        raise DeploymentPreflightError(
            f"Deployment is restricted to the canonical workbook path: {TARGET_WORKBOOK_PATH}"
        )
    if not workbook_path.is_file():
        raise DeploymentPreflightError(f"Production workbook not found: {workbook_path}")
    if not source_root.is_dir():
        raise DeploymentPreflightError(f"Source root not found: {source_root}")

    source_bodies = _read_source_bodies(source_root)
    workbook: Any | None = None
    owner: WorkbookOwner | None = None
    backup_path: Path | None = None
    original_hash: str | None = None
    before_snapshot: dict[str, str] | None = None
    excel_state: dict[str, Any] | None = None
    try:
        try:
            runtime.pythoncom.CoInitialize()
        except Exception as exc:
            raise DeploymentPreflightError(f"COM initialization failed: {exc}") from exc

        owner = _resolve_canonical_workbook_owner(runtime.win32_client, workbook_path, runtime.pythoncom)
        workbook = owner.workbook
        application = owner.application
        workbook_fullname = _canonical_path_text(Path(str(getattr(workbook, "FullName"))))
        if workbook_fullname != _canonical_path_text(workbook_path):
            raise DeploymentPreflightError(
                f"Resolved workbook owner does not match canonical path: {workbook_fullname}"
            )

        try:
            if bool(getattr(workbook, "ReadOnly", False)):
                raise DeploymentPreflightError("Production workbook is read-only")
        except AttributeError as exc:
            raise DeploymentPreflightError(f"Workbook ReadOnly state is unavailable: {exc}") from exc

        try:
            if not bool(getattr(workbook, "Saved")):
                raise DeploymentPreflightError("Production workbook has unsaved changes")
        except AttributeError as exc:
            raise DeploymentPreflightError(f"Workbook Saved state is unavailable: {exc}") from exc

        excel_state = _prepare_excel_instance(application)
        _stop_step44_scheduler(owner)

        owner = _validate_resolved_owner(owner, workbook_path, runtime=runtime)
        workbook = owner.workbook
        application = owner.application

        try:
            vbproject = workbook.VBProject
        except Exception as exc:
            raise DeploymentPreflightError(f"VBProject access denied: {exc}") from exc

        before_snapshot = _snapshot_vbproject(vbproject)
        for component_name in TARGET_COMPONENT_NAMES:
            if component_name not in before_snapshot:
                raise DeploymentPreflightError(f"Required VBComponent missing before deployment: {component_name}")

        backup_path, original_hash = _create_backup(
            workbook_path,
            timestamp_factory=timestamp_factory,
        )
        owner = _validate_resolved_owner(owner, workbook_path, runtime=runtime)
        workbook = owner.workbook
        application = owner.application
        try:
            vbproject = workbook.VBProject
        except Exception as exc:
            raise DeploymentPreflightError(f"VBProject access denied: {exc}") from exc

        _apply_target_module_updates(vbproject, source_bodies)
        try:
            workbook.Save()
        except Exception as exc:
            raise DeploymentError(f"Workbook save failed: {exc}") from exc

        after_snapshot = _snapshot_vbproject(vbproject)
        verification = _verify_deployment_state(
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            source_bodies=source_bodies,
        )

        _close_workbook_or_fail(workbook)
        workbook = None
        report = DeploymentReport(
            deployed=True,
            workbook_path=workbook_path,
            backup_path=backup_path,
            changed_modules=TARGET_COMPONENT_NAMES,
            preserved_modules=tuple(
                name for name in before_snapshot if name not in TARGET_COMPONENT_NAMES
            ),
            verification=verification,
            message="production VBA deployed successfully",
        )
        return report
    except Exception as exc:
        if workbook is not None:
            _close_workbook_best_effort(workbook)
            workbook = None
        if backup_path is not None and original_hash is not None:
            _restore_backup(workbook_path, backup_path, expected_hash=original_hash)
        if isinstance(exc, DeploymentError):
            raise
        raise DeploymentError(str(exc)) from exc
    finally:
        if owner is not None and excel_state is not None:
            _restore_excel_state(owner.application, excel_state)
        try:
            runtime.pythoncom.CoUninitialize()
        except Exception:
            pass


def deploy_v7_rss_production_vba() -> DeploymentReport:
    return _deploy_vba_to_path(TARGET_WORKBOOK_PATH)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--diagnose-excel-window-enum" in args:
        diagnostic = diagnose_excel_window_enumeration()
        for line in diagnostic.render_lines():
            print(line)
        return 0
    try:
        report = deploy_v7_rss_production_vba()
    except DeploymentError as exc:
        print("DEPLOYED: NO")
        print(f"ERROR: {exc}")
        return 1

    print("DEPLOYED: YES")
    print(f"WORKBOOK: {report.workbook_path}")
    print(f"BACKUP: {report.backup_path}")
    print(f"UPDATED: {', '.join(report.changed_modules)}")
    print("VERIFIED: " + ", ".join(sorted(report.verification.keys())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
