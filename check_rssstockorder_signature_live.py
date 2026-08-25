from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

TARGET_WORKBOOK_NAME = "MarketSpeed2_RSS_VBA.xlam"
TARGET_WORKBOOK_PATH = Path(r"C:\Users\ashtc\AppData\Local\MarketSpeed2\Bin\rss\MarketSpeed2_RSS_VBA.xlam")
TARGET_MACRO_NAME = "RssStockOrder_V"

DECL_RE = re.compile(
    rf"^\s*(Public\s+|Private\s+)?(Function|Sub)\s+{re.escape(TARGET_MACRO_NAME)}\b",
    re.IGNORECASE,
)


def _coerce_text(value: object) -> str:
    try:
        return str(value)
    except Exception:
        return repr(value)


def _iter_workbooks(excel: object) -> Iterable[object]:
    try:
        for workbook in excel.Workbooks:
            yield workbook
    except Exception:
        return


def _iter_addins(excel: object) -> Iterable[object]:
    try:
        for addin in excel.AddIns:
            yield addin
    except Exception:
        return


def _is_target_name(name: object) -> bool:
    text = _coerce_text(name).strip().lower()
    return text == TARGET_WORKBOOK_NAME.lower()


def _find_target_workbook(excel: object) -> tuple[str, object] | tuple[None, None]:
    for workbook in _iter_workbooks(excel):
        name = _coerce_text(getattr(workbook, "Name", ""))
        full_name = _coerce_text(getattr(workbook, "FullName", ""))
        if _is_target_name(name) or full_name.lower().endswith("\\" + TARGET_WORKBOOK_NAME.lower()):
            return "Workbook", workbook

    for addin in _iter_addins(excel):
        name = _coerce_text(getattr(addin, "Name", ""))
        full_name = _coerce_text(getattr(addin, "FullName", ""))
        if _is_target_name(name) or full_name.lower().endswith("\\" + TARGET_WORKBOOK_NAME.lower()):
            return "AddIn", addin

    return None, None


def _load_code_lines(component: object) -> list[str]:
    module = component.CodeModule
    count = int(getattr(module, "CountOfLines", 0) or 0)
    if count <= 0:
        return []
    code = _coerce_text(module.Lines(1, count))
    return code.splitlines()


def _merge_declaration(lines: Sequence[str], start_index: int) -> str:
    chunks: list[str] = []
    for idx in range(start_index, len(lines)):
        line = lines[idx].rstrip()
        chunks.append(line.rstrip(" _").strip())
        if not line.rstrip().endswith("_"):
            break
    return " ".join(part for part in chunks if part)


def _find_signature(lines: Sequence[str]) -> tuple[int, str] | tuple[None, None]:
    for idx, line in enumerate(lines):
        if TARGET_MACRO_NAME.lower() not in line.lower():
            continue
        if DECL_RE.search(line):
            return idx, _merge_declaration(lines, idx)
    for idx, line in enumerate(lines):
        if TARGET_MACRO_NAME.lower() in line.lower():
            return idx, _coerce_text(line).strip()
    return None, None


def _print_context(lines: Sequence[str], index: int, component_name: str) -> None:
    start = max(0, index - 4)
    end = min(len(lines), index + 12)
    print(f"COMPONENT={component_name}")
    print(f"LINE={index + 1}")
    for line_no in range(start, end):
        print(f"{line_no + 1}: {lines[line_no].rstrip()}")


def main() -> int:
    try:
        import pythoncom  # type: ignore
        import win32com.client as win32  # type: ignore
    except Exception as exc:
        print(f"BLOCKER: COM libraries unavailable: {type(exc).__name__}: {exc}")
        return 1

    pythoncom.CoInitialize()
    excel = None
    workbook = None
    try:
        try:
            excel = win32.DispatchEx("Excel.Application")
        except Exception as exc:
            print(f"BLOCKER: Excel.Application create failed: {type(exc).__name__}: {exc}")
            return 1

        try:
            excel.Visible = False
            excel.DisplayAlerts = False
        except Exception as exc:
            print(f"BLOCKER: Excel.Application setup failed: {type(exc).__name__}: {exc}")
            return 1

        try:
            excel.AutomationSecurity = 3
        except Exception:
            pass

        try:
            workbook = excel.Workbooks.Open(
                str(TARGET_WORKBOOK_PATH),
                ReadOnly=True,
                UpdateLinks=0,
                AddToMru=False,
                IgnoreReadOnlyRecommended=True,
            )
        except Exception as exc:
            print(f"BLOCKER: workbook open failed: {type(exc).__name__}: {exc}")
            return 1

        print(f"TARGET_WORKBOOK_PATH={TARGET_WORKBOOK_PATH}")
        print(f"TARGET_WORKBOOK={TARGET_WORKBOOK_NAME}")
        print(f"TARGET_MACRO={TARGET_MACRO_NAME}")

        try:
            vbproj = workbook.VBProject
        except Exception as exc:
            print(f"BLOCKER: VBProject access failed: {type(exc).__name__}: {exc}")
            return 1

        try:
            components = list(vbproj.VBComponents)
        except Exception as exc:
            print(f"BLOCKER: VBComponents access failed: {type(exc).__name__}: {exc}")
            return 1

        for component in components:
            try:
                lines = _load_code_lines(component)
            except Exception as exc:
                print(f"SKIP_COMPONENT={_coerce_text(getattr(component, 'Name', ''))} error={type(exc).__name__}: {exc}")
                continue

            if not lines:
                continue
            index, declaration = _find_signature(lines)
            if index is None:
                continue

            print("STATUS=FOUND")
            print(f"DECLARATION={declaration}")
            _print_context(lines, index, _coerce_text(getattr(component, "Name", "")))
            return 0

        print("BLOCKER: RssStockOrder_V signature not found in the loaded workbook")
        return 1
    finally:
        try:
            if workbook is not None:
                workbook.Close(False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
