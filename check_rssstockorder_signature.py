from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Iterable

XLAM_PATH = Path(r"C:\Users\ashtc\AppData\Local\MarketSpeed2\Bin\rss\MarketSpeed2_RSS_VBA.xlam")
XLL_PATH = Path(r"C:\Users\ashtc\AppData\Local\MarketSpeed2\Bin\rss\MarketSpeed2_RSS_64bit.xll")
TARGET_NAME = "RssStockOrder_V"

DECL_RE = re.compile(rf"^\s*(Public\s+|Private\s+)?(Function|Sub)\s+{re.escape(TARGET_NAME)}\b", re.IGNORECASE)


def _print_context(lines: list[str], line_index: int, module_name: str, source_name: str) -> None:
    start = max(0, line_index - 5)
    end = min(len(lines), line_index + 15)
    print(f"SOURCE={source_name}")
    print(f"MODULE={module_name}")
    print(f"LINE={line_index + 1}")
    for idx in range(start, end):
        print(f"{idx + 1}: {lines[idx].rstrip()}")


def _find_in_lines(lines: list[str]) -> int | None:
    for idx, line in enumerate(lines):
        if TARGET_NAME.lower() not in line.lower():
            continue
        if DECL_RE.search(line):
            return idx
    for idx, line in enumerate(lines):
        if TARGET_NAME.lower() in line.lower():
            return idx
    return None


def _scan_oletools(path: Path) -> bool:
    try:
        from oletools.olevba import VBA_Parser  # type: ignore
    except Exception as exc:
        print(f"OLETOOLS_UNAVAILABLE: {exc}")
        return False

    parser = VBA_Parser(str(path))
    found = False
    try:
        for item in parser.extract_macros():
            if len(item) == 4:
                _, source_name, module_name, vba_code = item
            elif len(item) == 3:
                source_name, module_name, vba_code = item
            else:
                continue

            if TARGET_NAME.lower() not in str(vba_code).lower():
                continue

            lines = str(vba_code).splitlines()
            idx = _find_in_lines(lines)
            if idx is None:
                continue
            _print_context(lines, idx, str(module_name), str(source_name))
            found = True
            break
    finally:
        try:
            parser.close()
        except Exception:
            pass

    return found


def _scan_excel_com(path: Path) -> bool:
    try:
        import win32com.client as win32  # type: ignore
    except Exception as exc:
        print(f"COM_UNAVAILABLE: {exc}")
        return False

    excel = None
    wb = None
    try:
        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        try:
            excel.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        except Exception:
            pass

        wb = excel.Workbooks.Open(
            str(path),
            ReadOnly=True,
            UpdateLinks=0,
            AddToMru=False,
            IgnoreReadOnlyRecommended=True,
        )

        vbproj = wb.VBProject
        for comp in vbproj.VBComponents:
            code = comp.CodeModule.Lines(1, comp.CodeModule.CountOfLines)
            if TARGET_NAME.lower() not in code.lower():
                continue
            lines = code.splitlines()
            idx = _find_in_lines(lines)
            if idx is None:
                continue
            _print_context(lines, idx, comp.Name, path.name)
            return True
        print("NO_SIGNATURE_FOUND_IN_COM")
        return False
    except Exception as exc:
        print(f"COM_FAIL: {type(exc).__name__}: {exc}")
        return False
    finally:
        try:
            if wb is not None:
                wb.Close(False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass


def main() -> int:
    print(f"XLAM={XLAM_PATH}")
    print(f"XLL={XLL_PATH}")

    if not XLAM_PATH.exists():
        print("BLOCKER: xlam path does not exist")
        return 1
    if not XLL_PATH.exists():
        print("BLOCKER: xll path does not exist")
        return 1

    print("METHOD=OLETOOLS")
    if _scan_oletools(XLAM_PATH):
        print("STATUS=OK")
        return 0

    print("METHOD=EXCEL_COM")
    if _scan_excel_com(XLAM_PATH):
        print("STATUS=OK")
        return 0

    print("BLOCKER: RssStockOrder_V signature not confirmed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
