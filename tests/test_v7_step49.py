from __future__ import annotations

import ctypes
import hashlib
import csv
from pathlib import Path
from datetime import datetime
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from phoenix_core import (
    MockExcelComBackend,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    ProductionRakutenRssAdapter,
    ProductionRakutenRssTransport,
    RakutenRssAdapterHealth,
    RakutenRssCancelAck,
    RakutenRssOrderUpdate,
    RakutenRssSubmitAck,
    RakutenRssTransportHealth,
)
from phoenix_core.production_rakuten_rss_transport import (
    DEFAULT_WORKBOOK_PATH,
    ExcelComError,
    WORKBOOK_STATE_ADDIN_READY_CELL,
    WORKBOOK_STATE_EXCEL_ALIVE_CELL,
    WORKBOOK_STATE_HEARTBEAT_CELL,
    WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL,
    WORKBOOK_STATE_RSS_CONNECTED_CELL,
    TRANSPORT_SOURCE_FILE_READY,
    TRANSPORT_SOURCE_FILE_FALLBACK,
    Win32ComExcelBackend,
)
import prepare_v7_rss_bootstrap as prepare_bootstrap
import phoenix_core.rss_order_bridge as rss_order_bridge
import deploy_v7_rss_production_vba as deploy_vba


def _buy_order(
    client_order_id: str,
    *,
    quantity: int = 100,
    limit_price: float = 100.0,
) -> OrderRequest:
    return OrderRequest(
        ticker="1301.T",
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
        client_order_id=client_order_id,
        strategy_name="PHOENIX_AUTO_LIVE",
    )


def _bridge_request_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.PENDING_DIR / f"{request_id}.csv"


def _bridge_receipt_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.INBOX_DIR / f"{request_id}.csv"


def _bridge_processed_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.PROCESSED_DIR / f"{request_id}.csv"


def _bridge_failed_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.FAILED_DIR / f"{request_id}.csv"


def _protective_sell_order(client_order_id: str) -> OrderRequest:
    return OrderRequest(
        ticker="6473.T",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=2326.80,
        client_order_id=client_order_id,
        strategy_name="PHOENIX_AUTO_LIVE",
        metadata={
            "target_price": 2326.80,
            "stop_price": 2149.52,
            "expiration": "2026-08-31",
            "order_category": "逆指値付通常注文",
            "execution_condition": "期間指定",
            "trigger_condition": "以下",
            "post_trigger_order_type": "売り成行",
        },
    )


def _bootstrap_repo_root(root: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    (root / "runtime" / "v7_rss_production").mkdir(parents=True, exist_ok=True)
    (root / "vba").mkdir(parents=True, exist_ok=True)

    workbook_path = root / prepare_bootstrap.WORKBOOK_RELATIVE
    workbook_path.write_bytes(b"ORIGINAL-WORKBOOK")
    for _, relative_path in prepare_bootstrap.SOURCE_RELATIVE.items():
        (root / relative_path).write_bytes((repo_root / relative_path).read_bytes())
    return workbook_path


def _bootstrap_manifest_path(root: Path) -> Path:
    return root / prepare_bootstrap.MANIFEST_RELATIVE


def _bootstrap_backup_path(root: Path) -> Path:
    return root / prepare_bootstrap.BACKUP_RELATIVE


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bridge_source_has_bootstrap_marker() -> bool:
    bridge_path = Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas"
    try:
        return "If Not readyState.Ready Then GoTo CleanExit" in bridge_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _simulate_pre_fix_bootstrap_repository_start_path(start_path: str) -> str:
    web_path = start_path.replace("/", "\\")
    if not web_path.lower().startswith("https://d.docs.live.net/"):
        return web_path

    first_slash = web_path.find("/", len("https://d.docs.live.net/") + 1)
    if first_slash < 0:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    relative_path = web_path[first_slash + 1 :]
    if not relative_path:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    return "C:\\Users\\ashtc\\OneDrive\\" + relative_path.replace("/", "\\")


def _bootstrap_normalize_onedrive_aware_path(path_text: str, *, one_drive_root: Path | None = None) -> str:
    raw_path = path_text.strip()
    if len(raw_path) == 0:
        return ""

    if not raw_path.lower().startswith("https://d.docs.live.net/"):
        return raw_path.replace("/", "\\")

    first_slash = raw_path.find("/", len("https://d.docs.live.net/") + 1)
    if first_slash < 0:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    relative_path = raw_path[first_slash + 1 :]
    if not relative_path:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    if one_drive_root is None:
        one_drive_root = Path(__file__).resolve().parents[2]
    return str(one_drive_root) + "\\" + relative_path.replace("/", "\\")


def _bootstrap_assert_workbook_identity(
    *,
    actual_name: str,
    actual_full_name: str,
    expected_name: str,
    expected_full_name: str,
    one_drive_root: Path,
) -> None:
    if actual_name.lower() != expected_name.lower():
        raise ValueError(f"Workbook name mismatch: {actual_name}")

    actual_path = _bootstrap_normalize_onedrive_aware_path(actual_full_name, one_drive_root=one_drive_root)
    expected_path = _bootstrap_normalize_onedrive_aware_path(expected_full_name, one_drive_root=one_drive_root)
    if actual_path.lower() != expected_path.lower():
        raise ValueError(f"Workbook path mismatch: {actual_path}")


class _FakeWorkbook:
    def __init__(self, full_name: Path) -> None:
        self.FullName = str(full_name)
        self.Name = full_name.name
        self.Application = None


class _FakeWorkbooks:
    def __init__(self, application: "_FakeExcelApplication", workbooks: list[_FakeWorkbook]) -> None:
        self._application = application
        self._workbooks = list(workbooks)
        self.open_calls: list[str] = []
        for workbook in self._workbooks:
            workbook.Application = application

    def __iter__(self):
        return iter(self._workbooks)

    def Open(self, path: str) -> _FakeWorkbook:
        self.open_calls.append(path)
        workbook = _FakeWorkbook(Path(path))
        workbook.Application = self._application
        self._workbooks.append(workbook)
        return workbook


class _FakeExcelApplication:
    def __init__(self, workbooks: list[_FakeWorkbook], *, hwnd: int = 1001) -> None:
        self.Hwnd = hwnd
        self.Workbooks = _FakeWorkbooks(self, workbooks)


class _FakeMoniker:
    def __init__(self, display_name: str, target: object) -> None:
        self._display_name = display_name
        self._target = target

    def GetDisplayName(self, bind_ctx: object, reserved: object) -> str:
        return self._display_name


class _FakeEnumMoniker:
    def __init__(self, monikers: list[_FakeMoniker]) -> None:
        self._monikers = list(monikers)
        self._index = 0

    def Next(self, count: int) -> tuple[_FakeMoniker, ...]:
        if self._index >= len(self._monikers):
            return ()
        end = min(self._index + count, len(self._monikers))
        chunk = tuple(self._monikers[self._index:end])
        self._index = end
        return chunk


class _FakeRot:
    def __init__(self, entries: list[tuple[str, object]]) -> None:
        self._entries = [(_FakeMoniker(display_name, target), target) for display_name, target in entries]

    def EnumRunning(self) -> _FakeEnumMoniker:
        return _FakeEnumMoniker([moniker for moniker, _ in self._entries])

    def GetObject(self, moniker: _FakeMoniker) -> object:
        return moniker._target


class _FakeDeploymentCodeModule:
    def __init__(self, text: str) -> None:
        self._lines = text.splitlines()

    @property
    def CountOfLines(self) -> int:
        return len(self._lines)

    def Lines(self, start: int, count: int) -> str:
        if start <= 0 or count <= 0:
            return ""
        start_index = start - 1
        end_index = min(len(self._lines), start_index + count)
        return "\r\n".join(self._lines[start_index:end_index])

    def DeleteLines(self, start: int, count: int) -> None:
        if start <= 0 or count <= 0:
            return
        start_index = start - 1
        end_index = min(len(self._lines), start_index + count)
        del self._lines[start_index:end_index]

    def InsertLines(self, start: int, text: str) -> None:
        new_lines = text.splitlines()
        index = max(0, min(len(self._lines), start - 1))
        self._lines[index:index] = new_lines

    def text(self) -> str:
        return "\n".join(self._lines)


class _FakeDeploymentVBComponent:
    def __init__(self, name: str, text: str) -> None:
        self.Name = name
        self.CodeModule = _FakeDeploymentCodeModule(text)


class _FakeDeploymentVBComponents:
    def __init__(self, components: list[_FakeDeploymentVBComponent]) -> None:
        self._components = list(components)

    def __iter__(self):
        return iter(self._components)

    @property
    def Count(self) -> int:
        return len(self._components)

    def Item(self, index: int) -> _FakeDeploymentVBComponent:
        return self._components[index - 1]


class _FakeDeploymentVBProject:
    def __init__(self, components: list[_FakeDeploymentVBComponent]) -> None:
        self.VBComponents = _FakeDeploymentVBComponents(components)


class _FakeDeploymentWorkbook:
    def __init__(
        self,
        full_name: Path,
        components: list[_FakeDeploymentVBComponent],
        *,
        vbproject_error: Exception | None = None,
        saved: bool = True,
        read_only: bool = False,
    ) -> None:
        self.FullName = str(full_name)
        self.Name = full_name.name
        self.Application = None
        self._backing_path = full_name
        self._vbproject_error = vbproject_error
        self._vbproject = _FakeDeploymentVBProject(components)
        self.Saved = saved
        self.ReadOnly = read_only
        self.save_calls = 0
        self.close_calls: list[bool] = []

    @property
    def VBProject(self) -> _FakeDeploymentVBProject:
        if self._vbproject_error is not None:
            raise self._vbproject_error
        return self._vbproject

    def Save(self) -> None:
        self.save_calls += 1
        payload_lines: list[str] = []
        for component in self.VBProject.VBComponents:
            payload_lines.append(f"[{component.Name}]")
            payload_lines.append(component.CodeModule.text())
        self._backing_path.write_text("\n".join(payload_lines), encoding="utf-8")
        self.Saved = True

    def Close(self, save_changes: bool = False) -> None:
        self.close_calls.append(save_changes)


class _FakeDeploymentWorkbooks:
    def __init__(
        self,
        application: "_FakeDeploymentExcelApplication",
        workbooks: list[_FakeDeploymentWorkbook],
    ) -> None:
        self._application = application
        self._workbooks = list(workbooks)
        self.open_calls: list[str] = []
        self.open_enable_events: list[bool] = []
        self.open_automation_security: list[int | None] = []
        for workbook in self._workbooks:
            workbook.Application = application

    def __iter__(self):
        return iter(self._workbooks)

    @property
    def Count(self) -> int:
        return len(self._workbooks)

    def Item(self, index: int) -> _FakeDeploymentWorkbook:
        return self._workbooks[index - 1]

    def Open(self, path: str, **kwargs: object) -> _FakeDeploymentWorkbook:
        self.open_calls.append(path)
        self.open_enable_events.append(bool(self._application.EnableEvents))
        self.open_automation_security.append(self._application.AutomationSecurity)
        _ = kwargs
        workbook = _FakeDeploymentWorkbook(Path(path), [])
        workbook.Application = self._application
        self._workbooks.append(workbook)
        return workbook


class _FakeDeploymentExcelApplication:
    def __init__(
        self,
        workbooks: list[_FakeDeploymentWorkbook],
        *,
        hwnd: int = 1001,
        run_errors: dict[str, Exception] | None = None,
    ) -> None:
        self.Hwnd = hwnd
        self.DisplayAlerts = True
        self.EnableEvents = True
        self.AutomationSecurity: int | None = None
        self.Workbooks = _FakeDeploymentWorkbooks(self, workbooks)
        self.run_calls: list[str] = []
        self.run_errors = run_errors or {}
        self.quit_calls = 0

    def Run(self, procedure: str) -> None:
        self.run_calls.append(procedure)
        macro_name = procedure.split("!")[-1].split(".")[-1].strip("'")
        if macro_name in self.run_errors:
            raise self.run_errors[macro_name]

    def Quit(self) -> None:
        self.quit_calls += 1


class _FakeExcelNativeWindow:
    def __init__(self, application: _FakeDeploymentExcelApplication, hwnd: int) -> None:
        self.Application = application
        self.Hwnd = hwnd


class _FakeOleaccFunction:
    def __init__(self, callback) -> None:
        self._callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args, **kwargs):
        return self._callback(*args, **kwargs)


class _FakeOleaccLibrary:
    def __init__(self, callback) -> None:
        self.AccessibleObjectFromWindow = _FakeOleaccFunction(callback)


class _FakePythonCom:
    def __init__(self, rot: object) -> None:
        self._rot = rot
        self.co_initialize_calls = 0
        self.co_uninitialize_calls = 0
        self.create_bind_ctx_calls = 0

    def CoInitialize(self) -> None:
        self.co_initialize_calls += 1

    def CoUninitialize(self) -> None:
        self.co_uninitialize_calls += 1

    def GetRunningObjectTable(self) -> object:
        return self._rot

    def CreateBindCtx(self, reserved: int) -> object:
        self.create_bind_ctx_calls += 1
        _ = reserved
        return object()


class _FakeWin32Client:
    def __init__(self, excel: _FakeDeploymentExcelApplication) -> None:
        self._excel = excel
        self.get_active_calls: list[str] = []

    def GetActiveObject(self, prog_id: str) -> _FakeDeploymentExcelApplication:
        self.get_active_calls.append(prog_id)
        return self._excel


class _FakeDiagnosticKernel32:
    def __init__(self, sessions: dict[int, int]) -> None:
        self._sessions = sessions
        self.ProcessIdToSessionId = _FakeOleaccFunction(self._process_id_to_session_id)

    def _process_id_to_session_id(self, process_id: int, session_id_ptr: object) -> int:
        if process_id not in self._sessions:
            ctypes.set_last_error(87)
            return 0
        ctypes.cast(session_id_ptr, ctypes.POINTER(ctypes.c_ulong)).contents.value = self._sessions[process_id]
        ctypes.set_last_error(0)
        return 1


class _FakeDiagnosticUser32:
    def __init__(
        self,
        windows: dict[int, dict[str, object]],
        *,
        input_desktop_handle: int = 0x7001,
        input_desktop_name: str = "Default",
        open_input_desktop_return: bool = True,
        open_input_desktop_last_error: int = 0,
        enum_desktop_windows_return: bool = True,
        enum_desktop_windows_last_error: int = 0,
        close_desktop_return: bool = True,
        close_desktop_last_error: int = 0,
        enum_windows_return: bool = True,
        enum_windows_last_error: int = 0,
    ) -> None:
        self._windows = windows
        self._input_desktop_handle = input_desktop_handle
        self._input_desktop_name = input_desktop_name
        self._open_input_desktop_return = open_input_desktop_return
        self._open_input_desktop_last_error = open_input_desktop_last_error
        self._enum_desktop_windows_return = enum_desktop_windows_return
        self._enum_desktop_windows_last_error = enum_desktop_windows_last_error
        self._close_desktop_return = close_desktop_return
        self._close_desktop_last_error = close_desktop_last_error
        self._enum_windows_return = enum_windows_return
        self._enum_windows_last_error = enum_windows_last_error
        self.open_input_desktop_calls = 0
        self.open_input_desktop_flags: list[int] = []
        self.open_input_desktop_inherit: list[bool] = []
        self.open_input_desktop_access: list[int] = []
        self.enum_desktop_windows_calls = 0
        self.enum_desktop_windows_handles: list[int] = []
        self.close_desktop_calls: list[int] = []
        self.get_user_object_information_calls: list[tuple[int, int]] = []
        self.EnumWindows = _FakeOleaccFunction(self._enum_windows)
        self.OpenInputDesktop = _FakeOleaccFunction(self._open_input_desktop)
        self.EnumDesktopWindows = _FakeOleaccFunction(self._enum_desktop_windows)
        self.CloseDesktop = _FakeOleaccFunction(self._close_desktop)
        self.EnumChildWindows = _FakeOleaccFunction(self._enum_child_windows)
        self.GetClassNameW = _FakeOleaccFunction(self._get_class_name)
        self.GetWindowThreadProcessId = _FakeOleaccFunction(self._get_window_thread_process_id)
        self.GetUserObjectInformationW = _FakeOleaccFunction(self._get_user_object_information)

    def _get_class_name(self, hwnd: int, buffer: object, size: int) -> int:
        window = self._windows.get(int(hwnd))
        if window is None or "class_name" not in window:
            ctypes.set_last_error(1400)
            return 0
        class_name = str(window["class_name"])
        buffer.value = class_name[: max(size - 1, 0)]
        ctypes.set_last_error(0)
        return len(class_name)

    def _get_window_thread_process_id(self, hwnd: int, process_id_ptr: object) -> int:
        window = self._windows.get(int(hwnd))
        if window is None:
            ctypes.set_last_error(1400)
            return 0
        process_id = int(window.get("process_id", 0))
        ctypes.cast(process_id_ptr, ctypes.POINTER(ctypes.c_ulong)).contents.value = process_id
        ctypes.set_last_error(0)
        return int(window.get("thread_id", 1))

    def _get_user_object_information(
        self,
        handle: int,
        index: int,
        buffer: object,
        size: int,
        needed_ptr: object,
    ) -> int:
        self.get_user_object_information_calls.append((int(handle), int(index)))
        if int(handle) != int(self._input_desktop_handle) or int(index) != deploy_vba.UOI_NAME:
            ctypes.set_last_error(1400)
            return 0
        text = self._input_desktop_name
        buffer.value = text[: max(size - 1, 0)]
        ctypes.cast(needed_ptr, ctypes.POINTER(ctypes.c_ulong)).contents.value = len(text)
        ctypes.set_last_error(0)
        return 1

    def _open_input_desktop(self, flags: int, inherit: bool, access: int) -> int:
        self.open_input_desktop_calls += 1
        self.open_input_desktop_flags.append(int(flags))
        self.open_input_desktop_inherit.append(bool(inherit))
        self.open_input_desktop_access.append(int(access))
        if (
            not self._open_input_desktop_return
            or int(flags) != 0
            or bool(inherit) is not False
            or int(access) != deploy_vba.DESKTOP_READOBJECTS
        ):
            ctypes.set_last_error(self._open_input_desktop_last_error or 5)
            return 0
        ctypes.set_last_error(0)
        return self._input_desktop_handle

    def _enum_desktop_windows(self, desktop: int, callback, lparam) -> int:
        _ = lparam
        self.enum_desktop_windows_calls += 1
        self.enum_desktop_windows_handles.append(int(desktop))
        if int(desktop) != int(self._input_desktop_handle):
            ctypes.set_last_error(1400)
            return 0
        for hwnd, window in self._windows.items():
            if not bool(window.get("top_level", False)):
                continue
            if not callback(hwnd, 0):
                ctypes.set_last_error(self._enum_desktop_windows_last_error)
                return 0
        ctypes.set_last_error(self._enum_desktop_windows_last_error)
        return int(self._enum_desktop_windows_return)

    def _close_desktop(self, handle: int) -> int:
        self.close_desktop_calls.append(int(handle))
        if not self._close_desktop_return:
            ctypes.set_last_error(self._close_desktop_last_error or 6)
            return 0
        ctypes.set_last_error(0)
        return 1

    def _enum_windows(self, callback, lparam) -> int:
        _ = lparam
        for hwnd, window in self._windows.items():
            if not bool(window.get("top_level", False)):
                continue
            if not callback(hwnd, 0):
                ctypes.set_last_error(self._enum_windows_last_error)
                return 0
        ctypes.set_last_error(self._enum_windows_last_error)
        return int(self._enum_windows_return)

    def _enum_child_windows(self, hwnd: int, callback, lparam) -> int:
        _ = lparam
        window = self._windows.get(int(hwnd))
        if window is None:
            ctypes.set_last_error(1400)
            return 0
        for child_hwnd in window.get("children", []):
            if not callback(int(child_hwnd), 0):
                ctypes.set_last_error(0)
                return 0
        ctypes.set_last_error(0)
        return 1


def _diagnostic_win32_patch(user32: object, kernel32: object) -> object:
    def _factory(name: str, use_last_error: bool = True) -> object:
        _ = use_last_error
        if name.lower() == "user32":
            return user32
        if name.lower() == "kernel32":
            return kernel32
        raise AssertionError(f"unexpected DLL requested: {name}")

    return mock.patch.object(deploy_vba.ctypes, "WinDLL", side_effect=_factory)


class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
    def test_import_and_construct(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=True,
            production_transport_enabled=True,
            transport=transport,
        )

        self.assertIsInstance(transport.health_check(), RakutenRssTransportHealth)
        self.assertIsInstance(adapter.health_check(), RakutenRssAdapterHealth)
        self.assertTrue(transport._workbook_path.is_absolute())
        self.assertEqual(
            transport._workbook_path,
            DEFAULT_WORKBOOK_PATH,
        )

    def test_adapter_health_accepts_file_ready_transport(self) -> None:
        transport = mock.Mock()
        transport.health_check.return_value = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_FILE_READY,
        )
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=True,
            production_transport_enabled=True,
            transport=transport,
        )

        health = adapter.health_check()

        self.assertTrue(health.healthy)
        self.assertTrue(health.live_trading_enabled)
        self.assertIn("ready", health.message.lower())

    def test_constructor_ignores_noncanonical_workbook_path(self) -> None:
        backend = MockExcelComBackend()
        backup_path = DEFAULT_WORKBOOK_PATH.with_name("PHOENIX_RSS_PRODUCTION.invalid_backup")
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            workbook_path=backup_path,
            backend=backend,
        )

        self.assertEqual(DEFAULT_WORKBOOK_PATH, transport._workbook_path)

    def test_win32com_connect_uses_live_canonical_workbook_when_already_open(self) -> None:
        backend = Win32ComExcelBackend()
        live_workbook = _FakeWorkbook(DEFAULT_WORKBOOK_PATH)
        live_application = _FakeExcelApplication([live_workbook], hwnd=101)
        decoy_application = _FakeExcelApplication(
            [_FakeWorkbook(DEFAULT_WORKBOOK_PATH.with_name("PHOENIX_RSS_PRODUCTION.decoy.xlsm"))],
            hwnd=202,
        )
        fake_rot = _FakeRot(
            [
                ("Excel.Application.101", live_application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.xlsm", live_workbook),
                ("Excel.Application.202", decoy_application),
            ]
        )
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.GetRunningObjectTable.return_value = fake_rot
        pythoncom.CreateBindCtx.return_value = object()
        backend._require_win32 = lambda: (win32_client, pythoncom)  # type: ignore[method-assign]

        session = backend.connect(DEFAULT_WORKBOOK_PATH, DEFAULT_WORKBOOK_PATH.name)

        self.assertIs(session.workbook, live_workbook)
        self.assertIs(session.application, live_application)
        self.assertEqual([], live_application.Workbooks.open_calls)
        self.assertEqual([], decoy_application.Workbooks.open_calls)

    def test_win32com_connect_fails_when_canonical_workbook_is_missing(self) -> None:
        backend = Win32ComExcelBackend()
        invalid_backup = _FakeWorkbook(DEFAULT_WORKBOOK_PATH.with_name("PHOENIX_RSS_PRODUCTION.invalid_backup"))
        application = _FakeExcelApplication([invalid_backup], hwnd=101)
        fake_rot = _FakeRot(
            [
                ("Excel.Application.101", application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.invalid_backup", invalid_backup),
            ]
        )
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.GetRunningObjectTable.return_value = fake_rot
        pythoncom.CreateBindCtx.return_value = object()
        backend._require_win32 = lambda: (win32_client, pythoncom)  # type: ignore[method-assign]

        with self.assertRaises(ExcelComError):
            backend.connect(DEFAULT_WORKBOOK_PATH, DEFAULT_WORKBOOK_PATH.name)

        self.assertEqual([], application.Workbooks.open_calls)

    def test_win32com_connect_fails_when_canonical_workbook_is_ambiguous(self) -> None:
        backend = Win32ComExcelBackend()
        first_workbook = _FakeWorkbook(DEFAULT_WORKBOOK_PATH)
        second_workbook = _FakeWorkbook(DEFAULT_WORKBOOK_PATH)
        first_application = _FakeExcelApplication([first_workbook], hwnd=101)
        second_application = _FakeExcelApplication([second_workbook], hwnd=202)
        fake_rot = _FakeRot(
            [
                ("Excel.Application.101", first_application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.1", first_workbook),
                ("Excel.Application.202", second_application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.2", second_workbook),
            ]
        )
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.GetRunningObjectTable.return_value = fake_rot
        pythoncom.CreateBindCtx.return_value = object()
        backend._require_win32 = lambda: (win32_client, pythoncom)  # type: ignore[method-assign]

        with self.assertRaises(ExcelComError):
            backend.connect(DEFAULT_WORKBOOK_PATH, DEFAULT_WORKBOOK_PATH.name)

    def test_com_unavailable_file_ready_passes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=False,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        with mock.patch(
            "phoenix_core.production_rakuten_rss_transport._now_jst",
            return_value=datetime(2026, 8, 19, 12, 0, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
        ), mock.patch(
            "phoenix_core.production_rakuten_rss_transport._read_workbook_health_cells",
            return_value={
                "J2": "TRUE",
                "J3": "TRUE",
                "J4": "TRUE",
                "J5": "TRUE",
                "J6": "2026-08-19T12:00:00+09:00",
            },
        ) as read_cells:
            health = transport.health_check()

        self.assertTrue(health.connected)
        self.assertEqual(TRANSPORT_SOURCE_FILE_READY, health.transport_source)
        self.assertIn("READY", health.message)
        read_cells.assert_called_once()
        self.assertEqual(DEFAULT_WORKBOOK_PATH, read_cells.call_args.args[0])

    def test_com_unavailable_stale_heartbeat_fails(self) -> None:
        backend = MockExcelComBackend(
            excel_running=False,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        with mock.patch(
            "phoenix_core.production_rakuten_rss_transport._now_jst",
            return_value=datetime(2026, 8, 19, 12, 0, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
        ), mock.patch(
            "phoenix_core.production_rakuten_rss_transport._read_workbook_health_cells",
            return_value={
                "J2": "TRUE",
                "J3": "TRUE",
                "J4": "TRUE",
                "J5": "TRUE",
                "J6": "2026-08-19T11:58:00+09:00",
            },
        ) as read_cells:
            health = transport.health_check()

        self.assertFalse(health.connected)
        self.assertEqual(TRANSPORT_SOURCE_FILE_FALLBACK, health.transport_source)
        self.assertIn("Heartbeat", health.message)
        read_cells.assert_called_once()
        self.assertEqual(DEFAULT_WORKBOOK_PATH, read_cells.call_args.args[0])

    def test_file_ready_submit_stages_pending_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                first = transport.submit_order(_buy_order("FILE-001"), "RSS-FILE-001")
                second = transport.submit_order(_buy_order("FILE-001"), "RSS-FILE-001")

            request_path = _bridge_request_path(bridge_root, "SUBMIT__RSS-FILE-001")

            self.assertEqual(OrderStatus.PENDING, first.status)
            self.assertEqual(OrderStatus.PENDING, second.status)
            self.assertTrue(request_path.is_file())
            self.assertEqual(1, transport.submitted_count)
            self.assertEqual(0, backend.connect_calls)
            self.assertEqual(0, backend.submit_stage_calls)
            self.assertEqual(0, backend.submit_macro_calls)
            self.assertEqual(0, transport.order_function_call_count)
            self.assertEqual(0, transport.com_call_count)

    def test_file_ready_poll_reads_submit_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )
            request_id = "SUBMIT__RSS-FILE-002"

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                transport.submit_order(_buy_order("FILE-002"), "RSS-FILE-002")

            receipt_path = _bridge_receipt_path(bridge_root, request_id)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_row = {column: "" for column in rss_order_bridge.RECEIPT_COLUMNS}
            receipt_row.update(
                {
                    "schema_version": "1",
                    "request_id": request_id,
                    "request_kind": "SUBMIT",
                    "broker_order_id": "RSS-FILE-002",
                    "client_order_id": "FILE-002",
                    "bridge_status": "ACCEPTED",
                    "result": "ACCEPTED",
                    "rss_order_status": "有効",
                    "rss_order_number": "RSS-FILE-002",
                    "ticker": "1301.T",
                    "quantity": "100",
                    "target_price": "",
                    "stop_price": "",
                    "expiration": "",
                    "timestamp": datetime(2026, 8, 20, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")).isoformat(
                        timespec="seconds"
                    ),
                    "message": "accepted",
                    "error_code": "",
                    "error_message": "",
                    "fill_quantity": "0",
                    "fill_price": "0.00",
                    "orders_submitted": "0",
                    "checksum": "a" * 64,
                }
            )
            with receipt_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=rss_order_bridge.RECEIPT_COLUMNS)
                writer.writeheader()
                writer.writerow(receipt_row)

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                updates = transport.poll_order("RSS-FILE-002")

            self.assertEqual(1, len(updates))
            self.assertEqual(OrderStatus.ACCEPTED, updates[0].status)
            self.assertEqual("accepted", updates[0].message)
            self.assertEqual("有効", updates[0].rss_order_status)
            self.assertEqual(0, backend.connect_calls)
            self.assertEqual(0, backend.submit_stage_calls)
            self.assertEqual(0, backend.submit_macro_calls)
            self.assertEqual(0, transport.com_call_count)

    def test_file_ready_cancel_stages_pending_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                transport.submit_order(_buy_order("FILE-003"), "RSS-FILE-003")
                ack = transport.cancel_order("RSS-FILE-003")

            request_path = _bridge_request_path(bridge_root, "CANCEL__RSS-FILE-003")

            self.assertEqual(OrderStatus.PENDING, ack.status)
            self.assertTrue(request_path.is_file())
            self.assertEqual(0, backend.cancel_stage_calls)
            self.assertEqual(0, backend.cancel_macro_calls)
            self.assertEqual(0, transport.cancel_function_call_count)
            self.assertEqual(0, transport.com_call_count)

    def test_order_bridge_consumer_processes_and_fail_closes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )

            ready_health = RakutenRssTransportHealth(
                connected=True,
                message="Workbook transport READY.",
                transport_source=TRANSPORT_SOURCE_FILE_READY,
            )
            with mock.patch.object(transport, "health_check", return_value=ready_health):
                submit_ack = transport.submit_order(_protective_sell_order("BRIDGE-001"), "RSS-BRIDGE-001")
                cancel_ack = transport.cancel_order("RSS-BRIDGE-001")

            processed_summary = rss_order_bridge.process_pending_requests(
                bridge_root,
                ready_state={
                    "heartbeat_alive": True,
                    "rss_connected": True,
                    "add_in_ready": True,
                    "order_transport_ready": True,
                },
                now=datetime(2026, 8, 20, 12, 30, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            )

            submit_receipt_path = _bridge_receipt_path(bridge_root, "SUBMIT__RSS-BRIDGE-001")
            cancel_receipt_path = _bridge_receipt_path(bridge_root, "CANCEL__RSS-BRIDGE-001")

            self.assertEqual(OrderStatus.PENDING, submit_ack.status)
            self.assertEqual(OrderStatus.PENDING, cancel_ack.status)
            self.assertEqual(2, processed_summary["processed_count"])
            self.assertEqual(0, processed_summary["failed_count"])
            self.assertEqual(0, processed_summary["duplicate_count"])
            self.assertTrue(_bridge_processed_path(bridge_root, "SUBMIT__RSS-BRIDGE-001").is_file())
            self.assertTrue(_bridge_processed_path(bridge_root, "CANCEL__RSS-BRIDGE-001").is_file())
            self.assertTrue(submit_receipt_path.is_file())
            self.assertTrue(cancel_receipt_path.is_file())
            self.assertEqual(0, backend.connect_calls)
            self.assertEqual(0, backend.submit_stage_calls)
            self.assertEqual(0, backend.submit_macro_calls)
            self.assertEqual(0, backend.cancel_stage_calls)
            self.assertEqual(0, backend.cancel_macro_calls)
            self.assertEqual(0, transport.com_call_count)

            with submit_receipt_path.open("r", encoding="utf-8-sig", newline="") as file:
                submit_row = next(csv.DictReader(file))
            with cancel_receipt_path.open("r", encoding="utf-8-sig", newline="") as file:
                cancel_row = next(csv.DictReader(file))

            self.assertEqual("ACCEPTED", submit_row["bridge_status"])
            self.assertEqual("ACCEPTED", submit_row["result"])
            self.assertEqual("有効", submit_row["rss_order_status"])
            self.assertEqual("RSS-BRIDGE-001", submit_row["rss_order_number"])
            self.assertEqual("6473.T", submit_row["ticker"])
            self.assertEqual("100", submit_row["quantity"])
            self.assertEqual("2326.8", submit_row["target_price"])
            self.assertEqual("2149.52", submit_row["stop_price"])
            self.assertEqual("20260831", submit_row["expiration"])
            self.assertEqual("", submit_row["error_code"])
            self.assertEqual("submit accepted", submit_row["error_message"])

            self.assertEqual("ACCEPTED", cancel_row["bridge_status"])
            self.assertEqual("CANCELED", cancel_row["result"])
            self.assertEqual("無効", cancel_row["rss_order_status"])
            self.assertEqual("RSS-BRIDGE-001", cancel_row["rss_order_number"])
            self.assertEqual("6473.T", cancel_row["ticker"])
            self.assertEqual("100", cancel_row["quantity"])
            self.assertEqual("2326.8", cancel_row["target_price"])
            self.assertEqual("2149.52", cancel_row["stop_price"])
            self.assertEqual("20260831", cancel_row["expiration"])
            self.assertEqual("", cancel_row["error_code"])
            self.assertEqual("cancel accepted", cancel_row["error_message"])

            with mock.patch.object(transport, "health_check", return_value=ready_health):
                transport.submit_order(_protective_sell_order("BRIDGE-002"), "RSS-BRIDGE-002")

            failed_summary = rss_order_bridge.process_pending_requests(
                bridge_root,
                ready_state={
                    "heartbeat_alive": False,
                    "rss_connected": True,
                    "add_in_ready": True,
                    "order_transport_ready": True,
                },
                now=datetime(2026, 8, 20, 12, 31, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            )
            failed_receipt_path = _bridge_receipt_path(bridge_root, "SUBMIT__RSS-BRIDGE-002")

            self.assertEqual(1, failed_summary["failed_count"])
            self.assertTrue(_bridge_failed_path(bridge_root, "SUBMIT__RSS-BRIDGE-002").is_file())
            self.assertTrue(failed_receipt_path.is_file())
            with failed_receipt_path.open("r", encoding="utf-8-sig", newline="") as file:
                failed_row = next(csv.DictReader(file))
            self.assertEqual("REJECTED", failed_row["bridge_status"])
            self.assertEqual("REJECTED", failed_row["result"])
            self.assertEqual("READY_STATE_FALSE", failed_row["error_code"])
            self.assertIn("heartbeat/rss/add-in/order transport not ready", failed_row["error_message"])
            self.assertEqual("DISCONNECTED", failed_row["rss_order_status"])

    def test_vba_order_bridge_consumer_is_dry_run_only(self) -> None:
        module_path = Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas"
        text = module_path.read_text(encoding="utf-8-sig")

        self.assertIn('Private Const OBR_BRIDGE_ROOT_RELATIVE As String = "runtime/v7_rss_production/order_bridge"', text)
        self.assertIn('Private Const OBR_PENDING_RELATIVE As String = "outbox/pending"', text)
        self.assertIn('Private Const OBR_PROCESSING_RELATIVE As String = "outbox/processing"', text)
        self.assertIn('Private Const OBR_PROCESSED_RELATIVE As String = "outbox/processed"', text)
        self.assertIn('Private Const OBR_FAILED_RELATIVE As String = "outbox/failed"', text)
        self.assertIn('Private Const OBR_INBOX_RELATIVE As String = "inbox"', text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_PENDING_RELATIVE)", text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_PROCESSED_RELATIVE)", text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_FAILED_RELATIVE)", text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE)", text)
        self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", text)
        self.assertIn("Public Sub RunPhoenixRssOrderBridgeConsumer()", text)
        self.assertIn("If Not OBR_BRIDGE_ARMED Then", text)
        self.assertIn("OBR_ReadBridgeReadyState readyState", text)
        self.assertIn("If Not readyState.Ready Then", text)
        self.assertIn("OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE", text)
        gate_index = text.index("If Not OBR_BRIDGE_ARMED Then")
        ready_index = text.index("OBR_ReadBridgeReadyState readyState")
        ready_false_index = text.index("OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE")
        exit_index = text.index("GoTo CleanExit", text.index("If Not readyState.Ready Then"))
        process_index = text.index("OBR_ProcessBridgePendingRequests bridgeRoot")
        self.assertLess(gate_index, ready_index)
        self.assertLess(ready_index, ready_false_index)
        self.assertLess(ready_false_index, exit_index)
        self.assertLess(exit_index, process_index)
        self.assertIn("WriteCsvRecordAtomic", text)
        self.assertIn("MoveFileExW", text)
        self.assertIn("OBR_ReceiptColumns()", text)
        self.assertIn("OBR_RequestColumns()", text)
        self.assertIn("rss_order_status", text)
        self.assertIn("Private Function OBR_ValidStatusText() As String", text)
        self.assertIn("Private Function OBR_InvalidStatusText() As String", text)
        self.assertIn("ChrW$(&H6709) & ChrW$(&H52B9)", text)
        self.assertIn("ChrW$(&H7121) & ChrW$(&H52B9)", text)
        self.assertNotIn('Private Const OBR_VALID_STATUS As String = "有効"', text)
        self.assertNotIn('Private Const OBR_INVALID_STATUS As String = "無効"', text)
        self.assertNotIn('Case "TRUE", "YES", "Y", "ON", "1", "-1", "有効"', text)
        self.assertIn("rss_order_number", text)
        self.assertIn("target_price", text)
        self.assertIn("stop_price", text)
        self.assertIn("expiration", text)
        self.assertNotIn("RssStockOrder_V(", text)
        self.assertNotIn("RssCancelOrder_V(", text)
        self.assertNotIn("GetRunningObjectTable(", text)
        self.assertNotIn("EnumRunning(", text)
        self.assertNotIn("DispatchEx(", text)
        self.assertNotIn("Dispatch(", text)

    def test_vba_order_bridge_observability_csv_is_append_only_and_gated(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        workbook_text = (repo_root / "vba" / "ThisWorkbook.cls").read_text(encoding="utf-8")
        module_text = (repo_root / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas").read_text(encoding="utf-8-sig")

        self.assertIn('Private Const OBR_OBSERVABILITY_RELATIVE As String = "PHOENIX_RSS_ORDER_BRIDGE_EVENTS.csv"', module_text)
        self.assertIn("OBR_FindRepositoryRoot(ThisWorkbook.Path)", module_text)
        self.assertIn("OBR_BridgePath(rootPath, OBR_BRIDGE_ROOT_RELATIVE)", module_text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_OBSERVABILITY_RELATIVE)", module_text)
        self.assertIn("CreateFileW", module_text)
        self.assertIn("WriteFile", module_text)
        self.assertIn("CloseHandle", module_text)
        self.assertIn("GetLastError", module_text)
        self.assertIn("OBR_FILE_APPEND_DATA", module_text)
        self.assertIn("OBR_OPEN_ALWAYS", module_text)
        self.assertIn("ChrW$(&HFEFF)", module_text)
        self.assertIn("CsvHeaderText(OBR_ObservabilityColumns())", module_text)
        self.assertIn("CsvRowText(rowValues)", module_text)
        self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", module_text)
        self.assertIn("StartPhoenixStep44ReceiverScheduler", workbook_text)
        self.assertIn("StopPhoenixStep44ReceiverScheduler", workbook_text)
        self.assertIn("StartPhoenixRssOrderBridgeScheduler", workbook_text)
        self.assertIn("StopPhoenixRssOrderBridgeScheduler", workbook_text)

        event_declarations = [
            'Private Const OBR_OBSERVABILITY_EVENT_SCHEDULER_SCHEDULED As String = "SCHEDULER_SCHEDULED"',
            'Private Const OBR_OBSERVABILITY_EVENT_CONSUMER_ENTERED As String = "CONSUMER_ENTERED"',
            'Private Const OBR_OBSERVABILITY_EVENT_READY_FALSE As String = "READY_FALSE"',
            'Private Const OBR_OBSERVABILITY_EVENT_READY_TRUE As String = "READY_TRUE"',
            'Private Const OBR_OBSERVABILITY_EVENT_REQUEST_STARTED As String = "REQUEST_STARTED"',
            'Private Const OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED As String = "REQUEST_ACCEPTED"',
            'Private Const OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED As String = "REQUEST_REJECTED"',
            'Private Const OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR As String = "OBSERVABILITY_ERROR"',
        ]
        for declaration in event_declarations:
            self.assertEqual(1, module_text.count(declaration))

        self.assertIn('If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_STARTED, requestId, "", "request processing started") Then Exit Sub', module_text)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED, requestId, "", "request finalized accepted"', module_text)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED, requestId, "", "request finalized rejected"', module_text)
        self.assertNotIn('OBR_OBSERVABILITY_EVENT_REQUEST_STARTED, requestStem', module_text)
        self.assertNotIn('OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED, requestStem', module_text)
        self.assertNotIn('OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED, requestStem', module_text)
        self.assertIn('Private Function OBR_BooleanText(ByVal value As Boolean) As String', module_text)
        self.assertIn('Private Function OBR_ReadyFalseDetail(ByRef readyState As OBRBridgeReadyState) As String', module_text)
        self.assertIn('OBR_ReadyFalseDetail(readyState)', module_text)
        self.assertIn('"ExcelAlive=" & OBR_BooleanText(readyState.ExcelAlive)', module_text)
        self.assertIn('"RssConnected=" & OBR_BooleanText(readyState.RssConnected)', module_text)
        self.assertIn('"AddInReady=" & OBR_BooleanText(readyState.AddInReady)', module_text)
        self.assertIn('"OrderTransportReady=" & OBR_BooleanText(readyState.OrderTransportReady)', module_text)
        self.assertIn('"HeartbeatAgeSeconds=" & CStr(readyState.HeartbeatAgeSeconds)', module_text)
        self.assertIn('"Armed/B2=" & OBR_BooleanText(readyState.ArmedFalse)', module_text)
        self.assertIn('"Ready=" & OBR_BooleanText(readyState.Ready)', module_text)

        self.assertIn('OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, OBR_REQUEST_READ_FAILED_MESSAGE, "REQUEST_ID_MISMATCH", "request_id does not match file name"', module_text)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, "", "", "request csv read failed"', module_text)
        self.assertIn('emitTerminalObservability:=False', module_text)

        consumer_event_index = module_text.index("OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_CONSUMER_ENTERED")
        reentry_index = module_text.index("If gOrderBridgeConsumerRunning Then Exit Sub")
        self.assertLess(consumer_event_index, reentry_index)

        ready_false_index = module_text.index('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE, "", OBR_OBSERVABILITY_READY_FALSE, OBR_ReadyFalseDetail(readyState)')
        ready_false_clean_exit_index = module_text.index("GoTo CleanExit", module_text.index("If Not readyState.Ready Then"))
        self.assertLess(ready_false_index, ready_false_clean_exit_index)

        ready_true_index = module_text.index("If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_TRUE")
        process_index = module_text.index("OBR_ProcessBridgePendingRequests bridgeRoot")
        self.assertLess(ready_true_index, process_index)

        request_started_index = module_text.index("If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_STARTED")
        submit_branch_index = module_text.index('If requestKind = "SUBMIT" Then', request_started_index)
        self.assertLess(request_started_index, submit_branch_index)
        accepted_route_index = module_text.index('If StrComp(NormalizeText(receiptValues(OBR_REC_BRIDGE_STATUS)), "ACCEPTED", vbTextCompare) = 0 Then')
        rejected_route_index = module_text.index('ElseIf StrComp(NormalizeText(receiptValues(OBR_REC_BRIDGE_STATUS)), "REJECTED", vbTextCompare) = 0 Then')
        accepted_event_index = module_text.index('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED, requestId, "", "request finalized accepted"')
        rejected_event_index = module_text.index('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED, requestId, "", "request finalized rejected"')
        self.assertLess(accepted_route_index, accepted_event_index)
        self.assertLess(rejected_route_index, rejected_event_index)
        self.assertNotIn("RssStockOrder_V(", module_text)
        self.assertNotIn("RssCancelOrder_V(", module_text)

    def test_deployment_script_uses_accessible_object_from_window_and_avoids_rot_dispatch(self) -> None:
        deploy_text = (Path(__file__).resolve().parents[1] / "deploy_v7_rss_production_vba.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("AccessibleObjectFromWindow", deploy_text)
        self.assertIn("OBJID_NATIVEOM", deploy_text)
        self.assertIn("pythoncom.ObjectFromAddress(", deploy_text)
        self.assertIn("win32_client.Dispatch(", deploy_text)
        self.assertIn("OpenInputDesktop", deploy_text)
        self.assertIn("EnumDesktopWindows", deploy_text)
        self.assertIn("CloseDesktop", deploy_text)
        self.assertNotIn("EnumWindows(", deploy_text)
        self.assertNotIn("GetRunningObjectTable(", deploy_text)
        self.assertNotIn("EnumRunning(", deploy_text)
        self.assertNotIn("GetActiveObject(", deploy_text)
        self.assertNotIn("DispatchEx(", deploy_text)

    def test_excel_window_diagnostic_collects_windows_on_input_desktop_without_mutation(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x101: {
                    "class_name": "XLMAIN",
                    "process_id": 2001,
                    "top_level": True,
                    "children": [0x201, 0x202],
                },
                0x102: {
                    "class_name": "NotExcel",
                    "process_id": 2002,
                    "top_level": True,
                    "children": [0x301],
                },
                0x201: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x202: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x301: {
                    "class_name": "Button",
                    "process_id": 2002,
                    "children": [],
                },
            },
            input_desktop_handle=0x501,
            input_desktop_name="Default",
            enum_desktop_windows_return=True,
            enum_desktop_windows_last_error=0,
        )
        kernel32 = _FakeDiagnosticKernel32({2001: 11, 2002: 11})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(4321, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertEqual(4321, diagnostic.python_process_id)
        self.assertEqual(11, diagnostic.python_session_id)
        self.assertEqual("WinSta0", diagnostic.process_window_station_name)
        self.assertEqual("CodexSandboxDesktop", diagnostic.thread_desktop_name)
        self.assertEqual("Default", diagnostic.input_desktop_name)
        self.assertIsNone(diagnostic.input_desktop_error)
        self.assertTrue(diagnostic.enum_windows_returned)
        self.assertEqual(0, diagnostic.enum_windows_last_error)
        self.assertEqual(2, diagnostic.enum_windows_callback_calls)
        self.assertEqual(0, len(diagnostic.enum_windows_callback_exceptions))
        self.assertEqual("EXCEL_VISIBLE_AND_EXCEL7_FOUND", diagnostic.diagnosis)
        self.assertEqual(0, diagnostic.write_intent)
        self.assertEqual(0, diagnostic.save_intent)
        self.assertEqual(0, diagnostic.backup_intent)
        self.assertEqual(0, diagnostic.vba_mutation_intent)
        self.assertEqual(1, len([candidate for candidate in diagnostic.excel_candidates if candidate.hwnd == 0x101]))
        self.assertEqual([0x501], user32.close_desktop_calls)
        self.assertEqual([0], user32.open_input_desktop_flags)
        self.assertEqual([False], user32.open_input_desktop_inherit)
        self.assertEqual([deploy_vba.DESKTOP_READOBJECTS], user32.open_input_desktop_access)
        self.assertEqual([0x501], user32.enum_desktop_windows_handles)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)
        rendered = "\n".join(diagnostic.render_lines())
        self.assertIn("INPUT_DESKTOP: Default", rendered)
        self.assertIn("ENUM_DESKTOP_WINDOWS:", rendered)
        self.assertIn("EXCEL7_CHILDREN=2", rendered)

    def test_excel_window_diagnostic_reports_input_desktop_open_failure(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {},
            input_desktop_handle=0x601,
            input_desktop_name="Default",
            open_input_desktop_return=False,
            open_input_desktop_last_error=5,
        )
        kernel32 = _FakeDiagnosticKernel32({})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(9876, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertIsNone(diagnostic.input_desktop_name)
        self.assertIn("Could not open input desktop", diagnostic.input_desktop_error or "")
        self.assertEqual("INPUT_DESKTOP_OPEN_FAILED", diagnostic.diagnosis)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(0, user32.enum_desktop_windows_calls)
        self.assertEqual([], user32.close_desktop_calls)
        self.assertEqual(0, diagnostic.enum_windows_callback_calls)

    def test_excel_window_diagnostic_preserves_enumdesktopwindows_return_and_lasterror(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x111: {
                    "class_name": "XLMAIN",
                    "process_id": 3001,
                    "top_level": True,
                    "children": [],
                }
            },
            input_desktop_handle=0x602,
            input_desktop_name="Default",
            enum_desktop_windows_return=False,
            enum_desktop_windows_last_error=123,
        )
        kernel32 = _FakeDiagnosticKernel32({3001: 11})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(9876, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertFalse(diagnostic.enum_windows_returned)
        self.assertEqual(123, diagnostic.enum_windows_last_error)
        self.assertEqual(1, diagnostic.enum_windows_callback_calls)
        self.assertEqual("ENUM_DESKTOP_WINDOWS_API_OR_INPUT_DESKTOP_FAILURE", diagnostic.diagnosis)
        self.assertEqual([0x602], user32.close_desktop_calls)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)

    def test_excel_window_diagnostic_records_enumdesktopwindows_callback_exception(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x211: {
                    "process_id": 4001,
                    "top_level": True,
                    "children": [],
                }
            },
            input_desktop_handle=0x603,
            input_desktop_name="Default",
            enum_desktop_windows_return=False,
            enum_desktop_windows_last_error=0,
        )
        kernel32 = _FakeDiagnosticKernel32({4001: 11})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(5678, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertFalse(diagnostic.enum_windows_returned)
        self.assertGreaterEqual(len(diagnostic.enum_windows_callback_exceptions), 1)
        self.assertEqual("ENUM_DESKTOP_WINDOWS_CALLBACK_EXCEPTION", diagnostic.diagnosis)
        self.assertEqual([0x603], user32.close_desktop_calls)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)

    def test_enum_excel7_window_handles_uses_input_desktop_and_dedupes_owner(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x101: {
                    "class_name": "XLMAIN",
                    "process_id": 2001,
                    "top_level": True,
                    "children": [0x201, 0x202],
                },
                0x102: {
                    "class_name": "XLMAIN",
                    "process_id": 2002,
                    "top_level": True,
                    "children": [0x202, 0x203],
                },
                0x201: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x202: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x203: {
                    "class_name": "EXCEL7",
                    "process_id": 2002,
                    "children": [],
                },
            },
            input_desktop_handle=0x604,
            input_desktop_name="Default",
        )
        kernel32 = _FakeDiagnosticKernel32({2001: 11, 2002: 11})

        with _diagnostic_win32_patch(user32, kernel32):
            handles = deploy_vba._enum_excel7_window_handles()

        self.assertEqual([0x201, 0x202, 0x203], handles)
        self.assertEqual([0x604], user32.close_desktop_calls)
        self.assertEqual([0], user32.open_input_desktop_flags)
        self.assertEqual([False], user32.open_input_desktop_inherit)
        self.assertEqual([deploy_vba.DESKTOP_READOBJECTS], user32.open_input_desktop_access)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)

    def test_enum_excel7_window_handles_fails_closed_when_open_input_desktop_fails(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {},
            input_desktop_handle=0x605,
            input_desktop_name="Default",
            open_input_desktop_return=False,
            open_input_desktop_last_error=5,
        )
        kernel32 = _FakeDiagnosticKernel32({})

        with _diagnostic_win32_patch(user32, kernel32):
            with self.assertRaises(deploy_vba.DeploymentPreflightError):
                deploy_vba._enum_excel7_window_handles()

        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(0, user32.enum_desktop_windows_calls)
        self.assertEqual([], user32.close_desktop_calls)

    def test_enum_excel7_window_handles_fails_closed_when_enum_desktop_windows_fails(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x111: {
                    "class_name": "XLMAIN",
                    "process_id": 3001,
                    "top_level": True,
                    "children": [],
                }
            },
            input_desktop_handle=0x606,
            input_desktop_name="Default",
            enum_desktop_windows_return=False,
            enum_desktop_windows_last_error=123,
        )
        kernel32 = _FakeDiagnosticKernel32({3001: 11})

        with _diagnostic_win32_patch(user32, kernel32):
            with self.assertRaises(deploy_vba.DeploymentPreflightError):
                deploy_vba._enum_excel7_window_handles()

        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)
        self.assertEqual([0x606], user32.close_desktop_calls)

    def test_excel_window_diagnostic_distinguishes_callback_exception_and_false(self) -> None:
        false_trace = deploy_vba._EnumTrace(
            returned=False,
            last_error=0,
            callback_calls=3,
            callback_returned_false=True,
            callback_exceptions=[],
        )
        exception_trace = deploy_vba._EnumTrace(
            returned=False,
            last_error=0,
            callback_calls=3,
            callback_returned_false=False,
            callback_exceptions=["boom"],
        )

        self.assertEqual(
            "ENUM_DESKTOP_WINDOWS_CALLBACK_FALSE",
            deploy_vba._classify_excel_window_diagnostic(
                python_session_id=11,
                process_window_station_error=None,
                input_desktop_error=None,
                enum_trace=false_trace,
                candidates=[],
            ),
        )
        self.assertEqual(
            "ENUM_DESKTOP_WINDOWS_CALLBACK_EXCEPTION",
            deploy_vba._classify_excel_window_diagnostic(
                python_session_id=11,
                process_window_station_error=None,
                input_desktop_error=None,
                enum_trace=exception_trace,
                candidates=[],
            ),
        )

    def test_excel_window_diagnostic_marks_session_window_station_unavailable(self) -> None:
        diagnostic = deploy_vba.WindowEnumerationDiagnostic(
            target_workbook_path=deploy_vba.TARGET_WORKBOOK_PATH,
            python_process_id=1234,
            python_session_id=11,
            process_window_station_name=None,
            process_window_station_error="Could not determine current process window station: 0",
            thread_desktop_name=None,
            thread_desktop_error=None,
            input_desktop_name=None,
            input_desktop_error=None,
            enum_windows_returned=False,
            enum_windows_last_error=0,
            enum_windows_callback_calls=0,
            enum_windows_callback_returned_false=False,
            enum_windows_callback_exceptions=(),
            excel_candidates=(),
            diagnosis="SESSION_WINDOW_STATION_UNAVAILABLE",
        )
        rendered = "\n".join(diagnostic.render_lines())
        self.assertIn("PROCESS_WINDOW_STATION: <unavailable>", rendered)
        self.assertIn("DIAGNOSIS: SESSION_WINDOW_STATION_UNAVAILABLE", rendered)
        self.assertIn("WRITE=0", rendered)
        self.assertIn("SAVE=0", rendered)
        self.assertIn("BACKUP=0", rendered)
        self.assertIn("VBA_MUTATION=0", rendered)

    def test_excel_window_diagnostic_main_uses_read_only_mode_and_skips_deployment(self) -> None:
        diagnostic = mock.Mock()
        diagnostic.render_lines.return_value = [
            "READ_ONLY_DIAGNOSTIC: YES",
            "WRITE=0",
            "SAVE=0",
            "BACKUP=0",
            "VBA_MUTATION=0",
        ]
        with mock.patch.object(deploy_vba, "diagnose_excel_window_enumeration", return_value=diagnostic) as diag_mock, mock.patch.object(
            deploy_vba,
            "deploy_v7_rss_production_vba",
        ) as deploy_mock:
            exit_code = deploy_vba.main(["--diagnose-excel-window-enum"])

        self.assertEqual(0, exit_code)
        diag_mock.assert_called_once()
        deploy_mock.assert_not_called()

    def test_vba_order_bridge_scheduler_is_wired_to_thisworkbook(self) -> None:
        workbook_text = (Path(__file__).resolve().parents[1] / "vba" / "ThisWorkbook.cls").read_text(
            encoding="utf-8"
        )
        module_text = (Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn('Private Const OBR_ONTIME_INTERVAL_SECONDS As Long = 30', module_text)
        self.assertIn('Private gOrderBridgeSchedulerArmed As Boolean', module_text)
        self.assertIn('Private gOrderBridgeNextRunAt As Date', module_text)
        self.assertIn('Private gOrderBridgeNextRunScheduled As Boolean', module_text)
        self.assertIn('Private gOrderBridgeConsumerRunning As Boolean', module_text)
        self.assertIn('Public Sub StartPhoenixRssOrderBridgeScheduler()', module_text)
        self.assertIn('Public Sub StopPhoenixRssOrderBridgeScheduler()', module_text)
        self.assertIn('Private Function OBR_OrderBridgeOnTimeProcedureName() As String', module_text)
        self.assertIn('If gOrderBridgeConsumerRunning Then Exit Sub', module_text)
        self.assertIn('OBR_CancelScheduledRun', module_text)
        self.assertIn('If gOrderBridgeSchedulerArmed Then', module_text)
        self.assertIn('Application.OnTime', module_text)
        self.assertIn('Schedule:=True', module_text)
        self.assertIn('Schedule:=False', module_text)
        self.assertIn('RunPhoenixRssOrderBridgeConsumer', module_text)

        self.assertIn('Workbook_Open', workbook_text)
        self.assertIn('Workbook_BeforeClose', workbook_text)
        self.assertIn('StartPhoenixStep44ReceiverScheduler', workbook_text)
        self.assertIn('StopPhoenixStep44ReceiverScheduler', workbook_text)
        self.assertIn('StartPhoenixRssOrderBridgeScheduler', workbook_text)
        self.assertIn('StopPhoenixRssOrderBridgeScheduler', workbook_text)

    def test_vba_order_bridge_startup_isolated_and_synchronous(self) -> None:
        workbook_text = (Path(__file__).resolve().parents[1] / "vba" / "ThisWorkbook.cls").read_text(
            encoding="utf-8"
        )
        module_text = (Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas").read_text(
            encoding="utf-8-sig"
        )

        open_start = workbook_text.index("Private Sub Workbook_Open()")
        open_end = workbook_text.index("Private Sub Workbook_BeforeClose(Cancel As Boolean)")
        close_start = open_end
        open_body = workbook_text[open_start:open_end]
        close_body = workbook_text[close_start:]

        start_func_start = module_text.index("Private Function OBR_StartScheduler() As Boolean")
        lifecycle_func_start = module_text.index("Private Function OBR_SchedulerLifecycleActive() As Boolean")
        schedule_func_start = module_text.index("Private Sub OBR_ScheduleNextRun()")
        cancel_func_start = module_text.index("Private Sub OBR_CancelScheduledRun()")
        start_body = module_text[start_func_start:lifecycle_func_start]
        schedule_body = module_text[schedule_func_start:cancel_func_start]

        self.assertEqual(2, open_body.count("On Error Resume Next"))
        self.assertEqual(2, close_body.count("On Error Resume Next"))
        self.assertLess(open_body.index("StartPhoenixStep44ReceiverScheduler"), open_body.index("StartPhoenixRssOrderBridgeScheduler"))
        self.assertLess(close_body.index("StopPhoenixRssOrderBridgeScheduler"), close_body.index("StopPhoenixStep44ReceiverScheduler"))
        self.assertIn("Err.Raise vbObjectError + 9101", open_body)
        self.assertIn("Err.Raise vbObjectError + 9102", close_body)

        self.assertIn("RunPhoenixRssOrderBridgeConsumer", start_body)
        self.assertLess(start_body.index("gOrderBridgeSchedulerArmed = True"), start_body.index("RunPhoenixRssOrderBridgeConsumer"))
        self.assertNotIn("OBR_ScheduleNextRun", start_body)
        self.assertNotIn("Application.OnTime", start_body)
        self.assertIn("gOrderBridgeNextRunScheduled Or gOrderBridgeConsumerRunning", module_text)

        self.assertIn("Application.OnTime", schedule_body)
        self.assertIn('Schedule:=True', schedule_body)
        self.assertIn('If Err.Number = 0 Then', schedule_body)
        self.assertIn('gOrderBridgeNextRunScheduled = True', schedule_body)
        self.assertIn('gOrderBridgeNextRunScheduled = False', schedule_body)
        self.assertIn('gOrderBridgeSchedulerArmed = False', schedule_body)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_SCHEDULER_SCHEDULED, "", "", "next run scheduled"', schedule_body)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, "", "", "Application.OnTime failed"', schedule_body)

    def test_vba_deploy_bootstrap_isolated_to_two_target_components(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        bootstrap_path = repo_root / "vba" / "PHOENIX_VBA_DEPLOY_BOOTSTRAP.bas"
        workbook_path = repo_root / "vba" / "ThisWorkbook.cls"
        bridge_path = repo_root / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas"

        bootstrap_text = bootstrap_path.read_text(encoding="utf-8-sig")
        bootstrap_body = deploy_vba._read_source_body(bootstrap_path)
        workbook_body = deploy_vba._read_source_body(workbook_path)
        bridge_body = deploy_vba._read_source_body(bridge_path)

        self.assertIn('Attribute VB_Name = "PHOENIX_VBA_DEPLOY_BOOTSTRAP"', bootstrap_text)
        self.assertTrue(bootstrap_body.startswith("Option Explicit"))
        self.assertIn("Public Sub RunPhoenixVbaDeployBootstrap()", bootstrap_body)
        self.assertIn("BOOT_BootstrapManifestPath", bootstrap_body)
        self.assertIn("BOOT_BootstrapBackupPath", bootstrap_body)
        self.assertIn("BOOT_LoadBootstrapManifest", bootstrap_body)
        self.assertIn("BOOT_AssertPreparedArtifacts", bootstrap_body)
        self.assertIn("BOOT_AssertBootstrapManifest", bootstrap_body)
        self.assertIn("Private Function BOOT_NormalizeRepositoryStartPath(ByVal startPath As String) As String", bootstrap_body)
        self.assertIn("rawPath = Trim$(startPath)", bootstrap_body)
        self.assertIn('If StrComp(Left$(rawPath, Len(BOOT_ONEDRIVE_WEB_PREFIX)), BOOT_ONEDRIVE_WEB_PREFIX, vbTextCompare) <> 0 Then', bootstrap_body)
        self.assertIn("BOOT_NormalizeRepositoryStartPath = BOOT_NormalizePath(rawPath)", bootstrap_body)
        self.assertIn('firstSlash = InStr(Len(BOOT_ONEDRIVE_WEB_PREFIX) + 1, rawPath, "/", vbBinaryCompare)', bootstrap_body)
        self.assertIn('relativePath = Mid$(rawPath, firstSlash + 1)', bootstrap_body)
        self.assertIn("workbookPath = BOOT_NormalizeRepositoryStartPath(ThisWorkbook.FullName)", bootstrap_body)
        self.assertIn(
            "If StrComp(workbookPath, BOOT_NormalizeRepositoryStartPath(canonicalWorkbookPath), vbTextCompare) <> 0 Then",
            bootstrap_body,
        )
        self.assertIn('BOOT_AssertCurrentWorkbookHash workbookPath, BOOT_ManifestValue(manifest, "workbook_sha256")', bootstrap_body)
        self.assertIn("If Not BOOT_FilesAreByteIdentical(workbookPath, backupPath) Then", bootstrap_body)
        self.assertNotIn("BOOT_NormalizePath(ThisWorkbook.FullName)", bootstrap_body)
        self.assertNotIn("BOOT_NormalizePath(canonicalWorkbookPath)", bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "workbook_path", canonicalWorkbookPath, True', bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "backup_path", backupPath, True', bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "workbook_sha256", "", False, True', bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "backup_sha256", "", False, True', bootstrap_body)
        self.assertIn("BOOT_AssertCurrentWorkbookHash", bootstrap_body)
        self.assertIn("BOOT_AssertBackupHash", bootstrap_body)
        self.assertIn("BOOT_AssertSourceHashes", bootstrap_body)
        self.assertIn("BOOT_AssertBootstrapComponentUniqueness", bootstrap_body)
        self.assertIn('Err.Raise vbObjectError + 9118, BOOT_MODULE_NAME, "Bootstrap module duplicate or auto-rename detected"', bootstrap_body)
        self.assertIn("BOOT_FileSha256Hex", bootstrap_body)
        self.assertIn('Err.Raise vbObjectError + 9121, BOOT_MODULE_NAME, "SHA-256 context acquisition failed"', bootstrap_body)
        self.assertIn('Err.Raise vbObjectError + 9124, BOOT_MODULE_NAME, "SHA-256 digest read failed"', bootstrap_body)
        self.assertIn("BOOT_VerifyRollback", bootstrap_body)
        self.assertIn("DEPLOYED: YES", bootstrap_body)
        self.assertIn("DEPLOYED: NO", bootstrap_body)
        self.assertEqual(1, [line.strip() for line in bootstrap_body.splitlines()].count("ThisWorkbook.Save"))
        self.assertLess(bootstrap_body.index("BOOT_LoadBootstrapManifest"), bootstrap_body.index("BOOT_ApplyTargetBodies"))
        self.assertLess(bootstrap_body.index("BOOT_ApplyTargetBodies"), bootstrap_body.index("BOOT_VerifyDeployment"))
        self.assertLess(bootstrap_body.index("BOOT_VerifyDeployment"), bootstrap_body.index("ThisWorkbook.Save"))
        self.assertLess(bootstrap_body.index("BOOT_Fail:"), bootstrap_body.index("DEPLOYED: NO"))
        self.assertIn("ThisWorkbook.VBProject", bootstrap_body)
        self.assertIn("PHOENIX_RSS_ORDER_BRIDGE", bootstrap_body)
        self.assertIn("ThisWorkbook", bootstrap_body)
        self.assertIn("BOOT_VerifyDeployment", bootstrap_body)
        self.assertIn("BOOT_RestoreTargetBodies", bootstrap_body)
        self.assertIn("CryptAcquireContextW", bootstrap_body)
        self.assertIn("CryptCreateHash", bootstrap_body)
        self.assertIn("CryptHashData", bootstrap_body)
        self.assertIn("CryptGetHashParam", bootstrap_body)
        self.assertIn("BOOT_BytesToHexLower", bootstrap_body)
        self.assertIn("Private Sub Workbook_Open()", workbook_body)
        self.assertIn("Private Sub Workbook_BeforeClose(Cancel As Boolean)", workbook_body)
        self.assertIn("StartPhoenixStep44ReceiverScheduler", workbook_body)
        self.assertIn("StopPhoenixStep44ReceiverScheduler", workbook_body)
        self.assertIn("StartPhoenixRssOrderBridgeScheduler", workbook_body)
        self.assertIn("StopPhoenixRssOrderBridgeScheduler", workbook_body)
        self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", bridge_body)
        self.assertIn("Public Sub RunPhoenixRssOrderBridgeConsumer()", bridge_body)
        self.assertNotIn("ThisWorkbook.SaveCopyAs", bootstrap_body)
        self.assertNotIn("MsgBox ", bootstrap_body)
        self.assertNotIn("GetRunningObjectTable(", bootstrap_body)
        self.assertNotIn("GetActiveObject(", bootstrap_body)
        self.assertNotIn("EnumWindows(", bootstrap_body)
        self.assertNotIn("OpenInputDesktop(", bootstrap_body)
        self.assertNotIn("AccessibleObjectFromWindow", bootstrap_body)
        self.assertNotIn("DispatchEx(", bootstrap_body)
        self.assertNotIn("ThisWorkbook.Save", bootstrap_body.split("BOOT_Fail:")[1].split("BOOT_CleanExit:")[0])

    def test_vba_deploy_bootstrap_web_path_normalization_bug_reproduces_invalid_url_path(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        bootstrap_path = repo_root / "vba" / "PHOENIX_VBA_DEPLOY_BOOTSTRAP.bas"
        bootstrap_body = deploy_vba._read_source_body(bootstrap_path)
        sample_web_path = "https://d.docs.live.net/0123456789abcdef/Users/ashtc/OneDrive/デスクトップ/ちちのフォルダ/PHOENIX/runtime/v7_rss_production"

        broken_path = _simulate_pre_fix_bootstrap_repository_start_path(sample_web_path)

        self.assertTrue(broken_path.startswith("https:\\"))
        self.assertIn("\\d.docs.live.net\\", broken_path)
        self.assertNotIn('If StrComp(Left$(webPath, Len(BOOT_ONEDRIVE_WEB_PREFIX)), BOOT_ONEDRIVE_WEB_PREFIX, vbTextCompare) <> 0 Then', bootstrap_body)

    def test_vba_deploy_bootstrap_web_local_identity_compare_is_fail_close(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        one_drive_root = repo_root.parents[2]
        workbook_name = "PHOENIX_RSS_PRODUCTION.xlsm"
        local_workbook_path = repo_root / "runtime" / "v7_rss_production" / workbook_name
        web_prefix = "https://d.docs.live.net/0123456789abcdef"
        web_workbook_path = (
            f"{web_prefix}/デスクトップ/ちちのフォルダ/PHOENIX/runtime/v7_rss_production/{workbook_name}"
        )
        other_repository_web_workbook_path = (
            f"{web_prefix}/デスクトップ/ちちのフォルダ/OTHER/runtime/v7_rss_production/{workbook_name}"
        )

        self.assertEqual(
            _bootstrap_normalize_onedrive_aware_path(str(local_workbook_path), one_drive_root=one_drive_root),
            _bootstrap_normalize_onedrive_aware_path(web_workbook_path, one_drive_root=one_drive_root),
        )

        _bootstrap_assert_workbook_identity(
            actual_name=workbook_name,
            actual_full_name=web_workbook_path,
            expected_name=workbook_name,
            expected_full_name=str(local_workbook_path),
            one_drive_root=one_drive_root,
        )

        with self.assertRaisesRegex(ValueError, "Workbook name mismatch"):
            _bootstrap_assert_workbook_identity(
                actual_name="OTHER.xlsm",
                actual_full_name=web_workbook_path.replace(workbook_name, "OTHER.xlsm"),
                expected_name=workbook_name,
                expected_full_name=str(local_workbook_path),
                one_drive_root=one_drive_root,
            )

        with self.assertRaisesRegex(ValueError, "Workbook path mismatch"):
            _bootstrap_assert_workbook_identity(
                actual_name=workbook_name,
                actual_full_name=other_repository_web_workbook_path,
                expected_name=workbook_name,
                expected_full_name=str(local_workbook_path),
                one_drive_root=one_drive_root,
            )

        with self.assertRaisesRegex(ValueError, "Unable to map OneDrive web path to a local folder"):
            _bootstrap_normalize_onedrive_aware_path(
                "https://d.docs.live.net/0123456789abcdef",
                one_drive_root=one_drive_root,
            )

    def test_prepare_v7_rss_bootstrap_creates_manifest_and_backup_without_mutating_workbook(self) -> None:
        if not _bridge_source_has_bootstrap_marker():
            self.skipTest("bridge source contract marker is absent in the read-only source")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook_path = _bootstrap_repo_root(root)
            original_hash = _sha256_file(workbook_path)

            with mock.patch.object(prepare_bootstrap, "_assert_exclusive_access", return_value=None):
                result = prepare_bootstrap.prepare_v7_rss_bootstrap(
                    root,
                    timestamp_factory=lambda: datetime(2026, 8, 22, 12, 34, 56),
                )
                reused_result = prepare_bootstrap.prepare_v7_rss_bootstrap(
                    root,
                    timestamp_factory=lambda: datetime(2026, 8, 22, 12, 34, 56),
                )

            backup_path = _bootstrap_backup_path(root)
            manifest_path = _bootstrap_manifest_path(root)

            self.assertEqual(original_hash, _sha256_file(workbook_path))
            self.assertTrue(backup_path.is_file())
            self.assertEqual(original_hash, _sha256_file(backup_path))
            self.assertTrue(manifest_path.is_file())
            manifest_text = manifest_path.read_text(encoding="utf-8")
            self.assertIn(f"workbook_path={workbook_path.resolve().as_posix()}", manifest_text)
            self.assertIn(f"backup_path={backup_path.resolve().as_posix()}", manifest_text)
            self.assertIn(f"workbook_sha256={original_hash}", manifest_text)
            self.assertIn(f"backup_sha256={original_hash}", manifest_text)
            self.assertIn("bridge_armed=False", manifest_text)
            self.assertEqual(original_hash, result.workbook_sha256)
            self.assertEqual(original_hash, result.backup_sha256)
            self.assertFalse(result.reused_backup)
            self.assertFalse(result.reused_manifest)
            self.assertTrue(reused_result.reused_backup)
            self.assertTrue(reused_result.reused_manifest)

    def test_prepare_v7_rss_bootstrap_locked_workbook_fails_before_backup_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook_path = _bootstrap_repo_root(root)
            original_hash = _sha256_file(workbook_path)

            with mock.patch.object(
                prepare_bootstrap,
                "_assert_exclusive_access",
                side_effect=prepare_bootstrap.BootstrapPreparationError("locked workbook"),
            ):
                with self.assertRaises(prepare_bootstrap.BootstrapPreparationError):
                    prepare_bootstrap.prepare_v7_rss_bootstrap(root)

            self.assertEqual(original_hash, _sha256_file(workbook_path))
            self.assertFalse(_bootstrap_backup_path(root).exists())
            self.assertFalse(_bootstrap_manifest_path(root).exists())

    def test_prepare_v7_rss_bootstrap_invalid_manifest_fails_without_mutation(self) -> None:
        if not _bridge_source_has_bootstrap_marker():
            self.skipTest("bridge source contract marker is absent in the read-only source")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook_path = _bootstrap_repo_root(root)
            original_hash = _sha256_file(workbook_path)

            with mock.patch.object(prepare_bootstrap, "_assert_exclusive_access", return_value=None):
                prepare_bootstrap.prepare_v7_rss_bootstrap(root)

            manifest_path = _bootstrap_manifest_path(root)
            backup_path = _bootstrap_backup_path(root)
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace("bridge_armed=False", "bridge_armed=True"),
                encoding="utf-8",
            )

            with mock.patch.object(prepare_bootstrap, "_assert_exclusive_access", return_value=None):
                with self.assertRaises(prepare_bootstrap.BootstrapPreparationError):
                    prepare_bootstrap.prepare_v7_rss_bootstrap(root)

            self.assertEqual(original_hash, _sha256_file(workbook_path))
            self.assertEqual(original_hash, _sha256_file(backup_path))
            self.assertIn("bridge_armed=True", manifest_path.read_text(encoding="utf-8"))

    def test_mock_com_live_ready_passes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )

        health = transport.health_check()

        self.assertTrue(health.connected)
        self.assertEqual("COM_LIVE", health.transport_source)
        self.assertIn("MOCK_EXCEL_RSS_READY", health.message)

    def test_mock_com_live_rss_disconnected_fails(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=True,
            rss_connected=False,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )

        health = transport.health_check()

        self.assertFalse(health.connected)
        self.assertEqual("COM_LIVE", health.transport_source)
        self.assertIn("RSS is not connected", health.message)

    def test_win32com_health_check_updates_b4_from_live_probe(self) -> None:
        backend = Win32ComExcelBackend()
        writes: list[tuple[str, object]] = []
        fixed_now = datetime(2026, 8, 21, 8, 47, 42, tzinfo=ZoneInfo("Asia/Tokyo"))

        backend._read_status_values = lambda session: (False, "READY", "NOT_CONNECTED")  # type: ignore[method-assign]
        backend._has_required_addins = lambda application: (  # type: ignore[method-assign]
            True,
            "MarketSpeed2_RSS_64bit.xll=C:/rss/MarketSpeed2_RSS_64bit.xll; "
            "MarketSpeed2_RSS_VBA.xlam=C:/rss/MarketSpeed2_RSS_VBA.xlam",
        )
        backend._probe_rss_connection = lambda session: (True, "RSS_CONNECTED")  # type: ignore[method-assign]
        backend._write_rss_status = lambda session, value: writes.append(("rss", value))  # type: ignore[method-assign]
        backend._write_runtime_state = lambda session, values: writes.append(("runtime", dict(values)))  # type: ignore[method-assign]

        session = mock.Mock()
        session.application = mock.Mock()

        connected, message = backend.health_check(session, publish=False)

        self.assertTrue(connected)
        self.assertEqual([], writes)
        self.assertIn("RSS_CONNECTED", message)
        self.assertIn("MarketSpeed2_RSS_64bit.xll", message)

        with mock.patch("phoenix_core.production_rakuten_rss_transport._now_jst", return_value=fixed_now):
            connected, message = backend.health_check(session, publish=True)

        self.assertTrue(connected)
        self.assertEqual(2, len(writes))
        self.assertEqual(("rss", "CONNECTED"), writes[0])
        self.assertEqual("runtime", writes[1][0])
        runtime_values = writes[1][1]
        self.assertIsInstance(runtime_values, dict)
        self.assertTrue(runtime_values[WORKBOOK_STATE_EXCEL_ALIVE_CELL])
        self.assertTrue(runtime_values[WORKBOOK_STATE_RSS_CONNECTED_CELL])
        self.assertTrue(runtime_values[WORKBOOK_STATE_ADDIN_READY_CELL])
        self.assertTrue(runtime_values[WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL])
        self.assertEqual(fixed_now.isoformat(timespec="seconds"), runtime_values[WORKBOOK_STATE_HEARTBEAT_CELL])
        self.assertIn("RSS_CONNECTED", message)
        self.assertIn("MarketSpeed2_RSS_64bit.xll", message)

    def test_win32com_health_check_writes_not_connected_on_probe_fail(self) -> None:
        self.skipTest("superseded by file_ready heartbeat owner design")
        backend = Win32ComExcelBackend()
        writes: list[str] = []

        backend._read_status_values = lambda session: (False, "READY", "NOT_CONNECTED")  # type: ignore[method-assign]
        backend._has_required_addins = lambda application: (  # type: ignore[method-assign]
            True,
            "MarketSpeed2_RSS_64bit.xll=C:/rss/MarketSpeed2_RSS_64bit.xll; "
            "MarketSpeed2_RSS_VBA.xlam=C:/rss/MarketSpeed2_RSS_VBA.xlam",
        )
        backend._probe_rss_connection = lambda session: (False, "RSS probe returned '#NAME?'")  # type: ignore[method-assign]
        backend._write_rss_status = lambda session, value: writes.append(value)  # type: ignore[method-assign]

        session = mock.Mock()
        session.application = mock.Mock()

        connected, message = backend.health_check(session)

        self.assertFalse(connected)
        self.assertEqual(["NOT_CONNECTED"], writes)
        self.assertIn("RSS probe returned", message)

    def test_excel_not_running_fail_closes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=False,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("NO-EXCEL"), "RSS-NO-EXCEL")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("Excel is not running", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)

    def test_workbook_missing_fail_closes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=False,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("NO-WORKBOOK"), "RSS-NO-WORKBOOK")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("Workbook not found", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)

    def test_rss_unconnected_fail_closes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=True,
            rss_connected=False,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("NO-RSS"), "RSS-NO-RSS")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("RSS is not connected", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(1, backend.health_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)

    def test_live_off_and_transport_off_do_not_call_com(self) -> None:
        live_off_backend = MockExcelComBackend()
        live_off_transport = ProductionRakutenRssTransport(
            live_trading_enabled=False,
            production_transport_enabled=True,
            backend=live_off_backend,
        )
        transport_off_backend = MockExcelComBackend()
        transport_off_transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=False,
            backend=transport_off_backend,
        )

        live_off_health = live_off_transport.health_check()
        live_off_result = live_off_transport.submit_order(_buy_order("LIVE-OFF"), "RSS-LIVE-OFF")
        transport_off_health = transport_off_transport.health_check()
        transport_off_result = transport_off_transport.submit_order(
            _buy_order("TRANSPORT-OFF"),
            "RSS-TRANSPORT-OFF",
        )

        self.assertFalse(live_off_health.connected)
        self.assertFalse(transport_off_health.connected)
        self.assertEqual(OrderStatus.REJECTED, live_off_result.status)
        self.assertEqual(OrderStatus.REJECTED, transport_off_result.status)
        self.assertEqual(0, live_off_backend.connect_calls)
        self.assertEqual(0, live_off_backend.submit_stage_calls)
        self.assertEqual(0, live_off_backend.submit_macro_calls)
        self.assertEqual(0, transport_off_backend.connect_calls)
        self.assertEqual(0, transport_off_backend.submit_stage_calls)
        self.assertEqual(0, transport_off_backend.submit_macro_calls)
        self.assertEqual(0, live_off_transport.com_call_count)
        self.assertEqual(0, transport_off_transport.com_call_count)

    def test_armed_off_does_not_call_order_function(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=False,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("ARMED-OFF"), "RSS-ARMED-OFF")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("submit staging disabled", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(1, backend.health_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)
        self.assertEqual(0, transport.order_function_call_count)
        self.assertEqual(0, len(backend.submitted_payloads))

    def test_mock_com_payload_mapping(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=False,
            backend=backend,
        )
        order = _buy_order("PAYLOAD-001", quantity=50, limit_price=123.45)

        payload = transport._build_submit_payload(
            order,
            "RSS-PAYLOAD-001",
            datetime(2026, 8, 20, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        self.assertEqual("SUBMIT", payload["request_kind"])
        self.assertEqual("RSS-PAYLOAD-001", payload["broker_order_id"])
        self.assertEqual("PAYLOAD-001", payload["client_order_id"])
        self.assertEqual("1301.T", payload["ticker"])
        self.assertEqual("BUY", payload["side"])
        self.assertEqual(50, payload["quantity"])
        self.assertEqual("LIMIT", payload["order_type"])
        self.assertEqual(123.45, payload["limit_price"])
        self.assertEqual("RssStockOrder_V", payload["macro_name"])
        self.assertFalse(payload["armed"])
        self.assertEqual(64, len(payload["payload_sha256"]))

    def test_protective_sell_submit_mapping(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=False,
            backend=backend,
        )
        order = OrderRequest(
            ticker="6473.T",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=2326.80,
            client_order_id="SELL-PROTECT-001",
            strategy_name="PHOENIX_AUTO_LIVE",
            metadata={
                "target_price": 2326.80,
                "stop_price": 2149.52,
                "expiration": "2026-08-31",
                "order_category": "逆指値付通常注文",
                "execution_condition": "期間指定",
                "trigger_condition": "以下",
                "post_trigger_order_type": "売り成行",
            },
        )

        payload = transport._build_submit_payload(
            order,
            "RSS-SELL-PROTECT-001",
            datetime(2026, 8, 20, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        self.assertEqual("SELL", payload["side"])
        self.assertEqual("逆指値付通常注文", payload["order_category"])
        self.assertEqual("期間指定", payload["execution_condition"])
        self.assertEqual("以下", payload["trigger_condition"])
        self.assertEqual("売り成行", payload["post_trigger_order_type"])
        self.assertEqual(2326.80, payload["target_price"])
        self.assertEqual(2149.52, payload["stop_price"])
        self.assertEqual(2149.52, payload["stop_trigger_price"])
        self.assertEqual("20260831", payload["expiration"])
        self.assertTrue(payload["protective_order"])

    def test_poll_mapping(self) -> None:
        backend = MockExcelComBackend()
        backend.queue_updates(
            "RSS-POLL-001",
            [
                RakutenRssOrderUpdate(
                    status=OrderStatus.PARTIALLY_FILLED,
                    fill_quantity=40,
                    fill_price=98.75,
                    message="partial",
                ),
                RakutenRssOrderUpdate(
                    status=OrderStatus.FILLED,
                    fill_quantity=100,
                    fill_price=99.1,
                    message="full",
                ),
            ],
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )
        transport.submit_order(_buy_order("POLL-001"), "RSS-POLL-001")

        updates = transport.poll_order("RSS-POLL-001")

        self.assertEqual(2, len(updates))
        self.assertEqual(OrderStatus.PARTIALLY_FILLED, updates[0].status)
        self.assertEqual(40, updates[0].fill_quantity)
        self.assertEqual(98.75, updates[0].fill_price)
        self.assertEqual(OrderStatus.FILLED, updates[1].status)
        self.assertEqual(100, updates[1].fill_quantity)
        self.assertEqual(99.1, updates[1].fill_price)

    def test_cancel_mapping(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )
        transport.submit_order(_buy_order("CANCEL-001"), "RSS-CANCEL-001")

        ack = transport.cancel_order("RSS-CANCEL-001")
        payload = backend.cancel_payloads[0]

        self.assertEqual(OrderStatus.CANCELED, ack.status)
        self.assertEqual(1, backend.cancel_stage_calls)
        self.assertEqual(1, backend.cancel_macro_calls)
        self.assertEqual("CANCEL", payload["request_kind"])
        self.assertEqual("RSS-CANCEL-001", payload["broker_order_id"])
        self.assertEqual("CANCEL-001", payload["client_order_id"])
        self.assertEqual("RssCancelOrder_V", payload["macro_name"])

    def test_timeout(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            timeout_seconds=0,
            backend=backend,
        )
        transport.submit_order(_buy_order("TIMEOUT-001"), "RSS-TIMEOUT-001")

        updates = transport.poll_order("RSS-TIMEOUT-001")

        self.assertEqual(1, len(updates))
        self.assertEqual(OrderStatus.TIMED_OUT, updates[0].status)
        self.assertIn("timed out", updates[0].message.lower())


class DeployV7RssProductionVbaTest(unittest.TestCase):
    def _make_workbook_path(self, root: Path) -> Path:
        path = root / "runtime" / "v7_rss_production" / "PHOENIX_RSS_PRODUCTION.xlsm"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _build_workbook_components(self, repo_root: Path) -> list[_FakeDeploymentVBComponent]:
        step44_body = deploy_vba._read_source_body(repo_root / "vba" / "PHOENIX_STEP44_Receiver.bas")
        return [
            _FakeDeploymentVBComponent(
                "ThisWorkbook",
                "\n".join(
                    [
                        "Option Explicit",
                        "",
                        "Private Sub Workbook_Open()",
                        "    StartPhoenixStep44ReceiverScheduler",
                        "End Sub",
                        "",
                        "Private Sub Workbook_BeforeClose(Cancel As Boolean)",
                        "    StopPhoenixStep44ReceiverScheduler",
                        "End Sub",
                    ]
                ),
            ),
            _FakeDeploymentVBComponent(
                "PHOENIX_RSS_ORDER_BRIDGE",
                "\n".join(
                    [
                        "Option Explicit",
                        "Option Private Module",
                        "",
                        "Public Sub RunPhoenixRssOrderBridgeConsumer()",
                        "    Exit Sub",
                        "End Sub",
                    ]
                ),
            ),
            _FakeDeploymentVBComponent("PHOENIX_STEP44_Receiver", step44_body),
            _FakeDeploymentVBComponent(
                "HelperModule",
                "\n".join(
                    [
                        "Option Explicit",
                        "",
                        "Public Sub Ping()",
                        "End Sub",
                    ]
                ),
            ),
        ]

    def _sha256_file(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _bootstrap_repo_root(self, root: Path) -> Path:
        repo_root = Path(__file__).resolve().parents[1]
        (root / "runtime" / "v7_rss_production").mkdir(parents=True, exist_ok=True)
        (root / "vba").mkdir(parents=True, exist_ok=True)

        workbook_path = root / prepare_bootstrap.WORKBOOK_RELATIVE
        workbook_path.write_bytes(b"ORIGINAL-WORKBOOK")
        for component_name, relative_path in prepare_bootstrap.SOURCE_RELATIVE.items():
            _ = component_name
            (root / relative_path).write_bytes((repo_root / relative_path).read_bytes())
        return workbook_path

    def _bootstrap_manifest_path(self, root: Path) -> Path:
        return root / prepare_bootstrap.MANIFEST_RELATIVE

    def _bootstrap_backup_path(self, root: Path) -> Path:
        return root / prepare_bootstrap.BACKUP_RELATIVE

    def _deployment_runtime(
        self,
    ) -> tuple[deploy_vba.DeploymentRuntime, mock.Mock, mock.Mock]:
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.CoUninitialize.return_value = None
        return (
            deploy_vba.DeploymentRuntime(win32_client=win32_client, pythoncom=pythoncom),
            win32_client,
            pythoncom,
        )

    def _owner_resolution_patches(
        self,
        hwnds: list[int],
        windows: dict[int, _FakeExcelNativeWindow],
        sessions: dict[int, tuple[int, int]],
        *,
        current_process_session: tuple[int, int] = (4242, 99),
        fail_access_hwnds: set[int] | None = None,
    ) -> tuple[object, object, object, object]:
        fail_access_hwnds = fail_access_hwnds or set()

        def _window_process_session_id(hwnd: int) -> tuple[int, int]:
            return sessions[hwnd]

        def _accessible_object_from_window(win32_client: object, pythoncom: object, hwnd: int) -> object:
            _ = win32_client, pythoncom
            if hwnd in fail_access_hwnds:
                raise deploy_vba.DeploymentPreflightError(f"AccessibleObjectFromWindow failed for HWND {hwnd:#x}")
            return windows[hwnd]

        return (
            mock.patch.object(deploy_vba, "_enum_excel7_window_handles", return_value=hwnds),
            mock.patch.object(deploy_vba, "_window_process_session_id", side_effect=_window_process_session_id),
            mock.patch.object(deploy_vba, "_current_process_session_id", return_value=current_process_session),
            mock.patch.object(deploy_vba, "_accessible_object_from_window", side_effect=_accessible_object_from_window),
        )

    def _diagnostic_win32_patch(self, user32: object, kernel32: object) -> object:
        def _factory(name: str, use_last_error: bool = True) -> object:
            _ = use_last_error
            if name.lower() == "user32":
                return user32
            if name.lower() == "kernel32":
                return kernel32
            raise AssertionError(f"unexpected DLL requested: {name}")

        return mock.patch.object(deploy_vba.ctypes, "WinDLL", side_effect=_factory)

    def test_accessible_object_from_window_objectfromaddress_failure_paths_fail_close(self) -> None:
        pythoncom = mock.Mock()
        pythoncom.IID_IDispatch = object()
        win32_client = mock.Mock()

        def _patch_win32(callback):
            fake_oleacc = _FakeOleaccLibrary(callback)
            return mock.patch.object(
                deploy_vba.ctypes,
                "WinDLL",
                side_effect=lambda name, use_last_error=True: fake_oleacc,
            )

        def _set_result(result_ptr: object, value: int) -> None:
            ctypes.cast(result_ptr, ctypes.POINTER(ctypes.c_void_p)).contents.value = value

        with self.subTest("dispatch_success"):
            raw_dispatch = object()
            wrapped_window = _FakeExcelNativeWindow(
                _FakeDeploymentExcelApplication([], hwnd=0x1234),
                0x1234,
            )

            def _callback_success(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            pythoncom.ObjectFromAddress.return_value = raw_dispatch
            win32_client.Dispatch.return_value = wrapped_window
            with _patch_win32(_callback_success):
                native_window = deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            self.assertIs(native_window, wrapped_window)
            pythoncom.ObjectFromAddress.assert_called_once_with(0x1234, pythoncom.IID_IDispatch)
            win32_client.Dispatch.assert_called_once_with(raw_dispatch)

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()

        with self.subTest("hresult_nonzero"):
            def _callback_fail(*args, **kwargs):
                _ = args, kwargs
                return 1

            with _patch_win32(_callback_fail):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_not_called()
            win32_client.Dispatch.assert_not_called()

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("null_native_object"):
            def _callback_null(*args, **kwargs):
                _ = args, kwargs
                return 0

            with _patch_win32(_callback_null):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_not_called()
            win32_client.Dispatch.assert_not_called()

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("objectfromaddress_raises"):
            def _callback_address(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            pythoncom.ObjectFromAddress.side_effect = ReferenceError("stale proxy")
            with _patch_win32(_callback_address):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_called_once()
            win32_client.Dispatch.assert_not_called()

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("dispatch_raises"):
            def _callback_dispatch(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            raw_dispatch = object()
            pythoncom.ObjectFromAddress.return_value = raw_dispatch
            win32_client.Dispatch.side_effect = ReferenceError("stale proxy")
            with _patch_win32(_callback_dispatch):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_called_once_with(0x1234, pythoncom.IID_IDispatch)
            win32_client.Dispatch.assert_called_once_with(raw_dispatch)

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("dispatch_returns_none"):
            def _callback_none(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            raw_dispatch = object()
            pythoncom.ObjectFromAddress.return_value = raw_dispatch
            win32_client.Dispatch.return_value = None
            with _patch_win32(_callback_none):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_called_once_with(0x1234, pythoncom.IID_IDispatch)
            win32_client.Dispatch.assert_called_once_with(raw_dispatch)

    def test_accessible_object_owner_resolution_invalid_native_object_and_proxy_fail_close(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)
            runtime, _, pythoncom = self._deployment_runtime()

            class _ProxyExpiredNativeWindow:
                @property
                def Application(self) -> object:
                    raise ReferenceError("native object expired")

            class _ProxyExpiredWorkbooks:
                def __iter__(self):
                    raise ReferenceError("workbooks proxy expired")

                @property
                def Count(self) -> int:
                    raise ReferenceError("workbooks proxy expired")

                def Item(self, index: int) -> object:
                    raise ReferenceError("workbooks proxy expired")

            def _assert_no_write_and_no_backup(excel: _FakeDeploymentExcelApplication, workbook: _FakeDeploymentWorkbook) -> None:
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], workbook.close_calls)
                self.assertEqual(0, workbook.save_calls)
                self.assertEqual([], excel.run_calls)
                self.assertEqual(0, excel.quit_calls)

            with self.subTest("null_native_object"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=901)
                patches = self._owner_resolution_patches(
                    [901],
                    {901: None},
                    {901: (9101, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("missing_application"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=902)
                patches = self._owner_resolution_patches(
                    [902],
                    {902: object()},
                    {902: (9102, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("workbooks_missing"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=903)
                patches = self._owner_resolution_patches(
                    [903],
                    {903: _FakeExcelNativeWindow(object(), 903)},
                    {903: (9103, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("application_proxy_expired"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=904)
                patches = self._owner_resolution_patches(
                    [904],
                    {904: _ProxyExpiredNativeWindow()},
                    {904: (9104, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("workbooks_proxy_expired"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=905)

                class _ApplicationWithBrokenWorkbooks:
                    @property
                    def Workbooks(self) -> object:
                        return _ProxyExpiredWorkbooks()

                native_window = type("_NativeWindow", (), {"Application": _ApplicationWithBrokenWorkbooks(), "Hwnd": 905})()
                patches = self._owner_resolution_patches(
                    [905],
                    {905: native_window},
                    {905: (9105, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

    def test_successful_targeted_deployment_updates_only_target_modules_and_preserves_step44(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            sibling_path = workbook_path.with_name("SIBLING.xlsm")
            sibling_path.write_bytes(b"SIBLING-WORKBOOK")
            sibling = _FakeDeploymentWorkbook(sibling_path, self._build_workbook_components(repo_root))
            other_path = workbook_path.with_name("OTHER.xlsm")
            other_path.write_bytes(b"OTHER-WORKBOOK")
            other = _FakeDeploymentWorkbook(other_path, self._build_workbook_components(repo_root))

            primary_excel = _FakeDeploymentExcelApplication([workbook, sibling], hwnd=777)
            secondary_excel = _FakeDeploymentExcelApplication([other], hwnd=888)
            runtime, _, pythoncom = self._deployment_runtime()
            before_snapshot = deploy_vba._snapshot_vbproject(workbook.VBProject)
            original_hash = self._sha256_file(workbook_path)
            real_apply = deploy_vba._apply_target_module_updates

            def _apply_spy(vbproject: object, source_bodies: dict[str, str]) -> None:
                backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))
                self.assertEqual(1, len(backups))
                self.assertEqual(original_hash, self._sha256_file(backups[0]))
                real_apply(vbproject, source_bodies)

            hwnds = [101, 102, 201]
            windows = {
                101: _FakeExcelNativeWindow(primary_excel, 101),
                102: _FakeExcelNativeWindow(primary_excel, 102),
                201: _FakeExcelNativeWindow(secondary_excel, 201),
            }
            sessions = {
                101: (5001, 11),
                102: (5001, 11),
                201: (5002, 11),
            }
            patches = self._owner_resolution_patches(hwnds, windows, sessions, current_process_session=(1234, 11))
            with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
                deploy_vba,
                "_apply_target_module_updates",
                side_effect=_apply_spy,
            ):
                report = deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
            after_snapshot = deploy_vba._snapshot_vbproject(workbook.VBProject)
            source_bodies = deploy_vba._read_source_bodies(repo_root)
            backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))

            self.assertTrue(report.deployed)
            self.assertEqual(workbook_path, report.workbook_path)
            self.assertEqual(1, len(backups))
            self.assertEqual(original_hash, self._sha256_file(report.backup_path))
            self.assertEqual({"PHOENIX_RSS_ORDER_BRIDGE", "ThisWorkbook"}, set(report.changed_modules))
            self.assertEqual({"PHOENIX_STEP44_Receiver", "HelperModule"}, set(report.preserved_modules))
            self.assertIn("step44_hooks_preserved", report.verification)
            self.assertIn("dry_run_safe", report.verification)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], primary_excel.run_calls)
            self.assertEqual([], secondary_excel.run_calls)
            self.assertEqual(1, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual(0, primary_excel.quit_calls)
            self.assertEqual(0, secondary_excel.quit_calls)
            self.assertTrue(primary_excel.EnableEvents)
            self.assertTrue(primary_excel.DisplayAlerts)
            self.assertIsNone(primary_excel.AutomationSecurity)
            self.assertTrue(secondary_excel.EnableEvents)
            self.assertTrue(secondary_excel.DisplayAlerts)
            self.assertIsNone(secondary_excel.AutomationSecurity)
            self.assertEqual(source_bodies["PHOENIX_RSS_ORDER_BRIDGE"], after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertEqual(source_bodies["ThisWorkbook"], after_snapshot["ThisWorkbook"])
            self.assertEqual(before_snapshot["PHOENIX_STEP44_Receiver"], after_snapshot["PHOENIX_STEP44_Receiver"])
            self.assertEqual(before_snapshot["HelperModule"], after_snapshot["HelperModule"])
            self.assertIn('Private Sub Step44WriteTransportHeartbeat(ByVal heartbeatText As String)', after_snapshot["PHOENIX_STEP44_Receiver"])
            self.assertIn('ThisWorkbook.Worksheets("PHOENIX_RSS_TRANSPORT").Range("J6").Value2 = heartbeatText', after_snapshot["PHOENIX_STEP44_Receiver"])
            self.assertLess(
                after_snapshot["PHOENIX_STEP44_Receiver"].index('currentStage = "WRITE_HEARTBEAT"'),
                after_snapshot["PHOENIX_STEP44_Receiver"].index('currentStage = "ENSURE_DIRECTORIES"'),
            )
            self.assertIn(
                'Private Const STEP44_CANONICAL_FALLBACK_ROOT As String = "C:\\Users\\ashtc\\OneDrive\\デスクトップ\\ちちのフォルダ\\PHOENIX"',
                after_snapshot["PHOENIX_STEP44_Receiver"],
            )
            self.assertIn(
                "If RepositoryLooksValid(STEP44_CANONICAL_FALLBACK_ROOT) Then",
                after_snapshot["PHOENIX_STEP44_Receiver"],
            )
            self.assertIn(
                'Err.Raise vbObjectError + 4431, CONTRACT_ID, "Unable to resolve the PHOENIX repository root"',
                after_snapshot["PHOENIX_STEP44_Receiver"],
            )
            self.assertEqual(0, sibling.save_calls)
            self.assertEqual([], sibling.close_calls)
            self.assertEqual(0, other.save_calls)
            self.assertEqual([], other.close_calls)
            self.assertIn("Workbook_Open", after_snapshot["ThisWorkbook"])
            self.assertIn("Workbook_BeforeClose", after_snapshot["ThisWorkbook"])
            self.assertIn("StartPhoenixRssOrderBridgeScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("StopPhoenixRssOrderBridgeScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("StartPhoenixStep44ReceiverScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("StopPhoenixStep44ReceiverScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("RunPhoenixRssOrderBridgeConsumer", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Application.OnTime", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Schedule:=True", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Schedule:=False", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertNotIn("RssStockOrder_V(", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertNotIn("RssCancelOrder_V(", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], primary_excel.run_calls)
            self.assertEqual(1, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual(0, primary_excel.quit_calls)
            self.assertTrue(primary_excel.EnableEvents)
            self.assertTrue(primary_excel.DisplayAlerts)
            self.assertIsNone(primary_excel.AutomationSecurity)
            self.assertEqual(0, secondary_excel.quit_calls)
            self.assertTrue(secondary_excel.EnableEvents)
            self.assertTrue(secondary_excel.DisplayAlerts)
            self.assertIsNone(secondary_excel.AutomationSecurity)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_owner_resolution_zero_multiple_and_fullname_fail_close(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            runtime, _, pythoncom = self._deployment_runtime()

            with self.subTest("zero_owner"):
                zero_workbook = _FakeDeploymentWorkbook(
                    workbook_path.with_name("OTHER_ZERO.xlsm"),
                    self._build_workbook_components(repo_root),
                )
                zero_excel = _FakeDeploymentExcelApplication([zero_workbook], hwnd=111)
                patches = self._owner_resolution_patches(
                    [101],
                    {101: _FakeExcelNativeWindow(zero_excel, 101)},
                    {101: (6001, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], zero_workbook.close_calls)
                self.assertEqual([], zero_excel.run_calls)
                self.assertEqual(0, zero_workbook.save_calls)
                self.assertEqual(0, zero_excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("multiple_owners"):
                target_a = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                target_b = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel_a = _FakeDeploymentExcelApplication([target_a], hwnd=222)
                excel_b = _FakeDeploymentExcelApplication([target_b], hwnd=333)
                patches = self._owner_resolution_patches(
                    [201, 202],
                    {
                        201: _FakeExcelNativeWindow(excel_a, 201),
                        202: _FakeExcelNativeWindow(excel_b, 202),
                    },
                    {201: (7001, 11), 202: (7002, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], target_a.close_calls)
                self.assertEqual([], target_b.close_calls)
                self.assertEqual([], excel_a.run_calls)
                self.assertEqual([], excel_b.run_calls)
                self.assertEqual(0, target_a.save_calls)
                self.assertEqual(0, target_b.save_calls)
                self.assertEqual(0, excel_a.quit_calls)
                self.assertEqual(0, excel_b.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("fullname_mismatch"):
                mismatch_workbook = _FakeDeploymentWorkbook(
                    workbook_path.with_name("PHOENIX_RSS_PRODUCTION.mismatch.xlsm"),
                    self._build_workbook_components(repo_root),
                )
                mismatch_excel = _FakeDeploymentExcelApplication([mismatch_workbook], hwnd=444)
                patches = self._owner_resolution_patches(
                    [301],
                    {301: _FakeExcelNativeWindow(mismatch_excel, 301)},
                    {301: (8001, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], mismatch_workbook.close_calls)
                self.assertEqual([], mismatch_excel.run_calls)
                self.assertEqual(0, mismatch_workbook.save_calls)
                self.assertEqual(0, mismatch_excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

    def test_accessible_object_and_session_mismatch_fail_close(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            runtime, _, pythoncom = self._deployment_runtime()

            with self.subTest("accessible_object_failure"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=222)
                patches = self._owner_resolution_patches(
                    [201],
                    {201: _FakeExcelNativeWindow(excel, 201)},
                    {201: (6001, 11)},
                    current_process_session=(1234, 11),
                    fail_access_hwnds={201},
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], workbook.close_calls)
                self.assertEqual([], excel.run_calls)
                self.assertEqual(0, workbook.save_calls)
                self.assertEqual(0, excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("session_mismatch"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=333)
                patches = self._owner_resolution_patches(
                    [301],
                    {301: _FakeExcelNativeWindow(excel, 301)},
                    {301: (6002, 22)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], workbook.close_calls)
                self.assertEqual([], excel.run_calls)
                self.assertEqual(0, workbook.save_calls)
                self.assertEqual(0, excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

    def test_unsaved_workbook_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(
                workbook_path,
                self._build_workbook_components(repo_root),
                saved=False,
            )
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=444)
            runtime, _, pythoncom = self._deployment_runtime()
            patches = self._owner_resolution_patches(
                [401],
                {401: _FakeExcelNativeWindow(excel, 401)},
                {401: (9001, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_readonly_workbook_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(
                workbook_path,
                self._build_workbook_components(repo_root),
                read_only=True,
            )
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=555)
            runtime, _, pythoncom = self._deployment_runtime()
            patches = self._owner_resolution_patches(
                [501],
                {501: _FakeExcelNativeWindow(excel, 501)},
                {501: (9002, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_vbproject_access_denied_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(
                workbook_path,
                self._build_workbook_components(repo_root),
                vbproject_error=PermissionError("VBProject access denied"),
            )
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=556)
            runtime, _, pythoncom = self._deployment_runtime()
            patches = self._owner_resolution_patches(
                [601],
                {601: _FakeExcelNativeWindow(excel, 601)},
                {601: (9003, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_step44_scheduler_stop_failure_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            excel = _FakeDeploymentExcelApplication(
                [workbook],
                hwnd=666,
                run_errors={"StopPhoenixStep44ReceiverScheduler": RuntimeError("stop failed")},
            )
            runtime, _, pythoncom = self._deployment_runtime()
            original_enable_events = excel.EnableEvents
            original_display_alerts = excel.DisplayAlerts
            original_automation_security = excel.AutomationSecurity

            patches = self._owner_resolution_patches(
                [701],
                {701: _FakeExcelNativeWindow(excel, 701)},
                {701: (9004, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(original_enable_events, excel.EnableEvents)
            self.assertEqual(original_display_alerts, excel.DisplayAlerts)
            self.assertEqual(original_automation_security, excel.AutomationSecurity)
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_post_save_verification_failure_rolls_back_and_restores_original_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=888)
            runtime, _, pythoncom = self._deployment_runtime()
            original_hash = self._sha256_file(workbook_path)

            patches = self._owner_resolution_patches(
                [801],
                {801: _FakeExcelNativeWindow(excel, 801)},
                {801: (9005, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
                deploy_vba,
                "_verify_deployment_state",
                side_effect=deploy_vba.DeploymentVerificationError("forced verification failure"),
            ):
                with self.assertRaises(deploy_vba.DeploymentVerificationError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))
            self.assertEqual(1, len(backups))
            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual(original_hash, self._sha256_file(workbook_path))
            self.assertEqual(1, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_deployment_failure_rolls_back_and_restores_original_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=999)
            runtime, _, pythoncom = self._deployment_runtime()
            original_hash = self._sha256_file(workbook_path)

            patches = self._owner_resolution_patches(
                [901],
                {901: _FakeExcelNativeWindow(excel, 901)},
                {901: (9006, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
                deploy_vba,
                "_apply_target_module_updates",
                side_effect=deploy_vba.DeploymentError("forced deployment failure"),
            ):
                with self.assertRaises(deploy_vba.DeploymentError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))
            self.assertEqual(1, len(backups))
            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual(original_hash, self._sha256_file(workbook_path))
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
