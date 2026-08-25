from __future__ import annotations

"""RSS実機health_check専用 launcher.

This script performs exactly one ProductionRakutenRssTransport health_check
call and prints the live Excel / workbook / RSS status fields needed for a
manual one-shot verification run.
"""

import json
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from phoenix_core.production_rakuten_rss_transport import (  # noqa: E402
    DEFAULT_WORKBOOK_PATH,
    ProductionRakutenRssTransport,
    TRANSPORT_SOURCE_COM_LIVE,
)


REQUIRED_ADDIN_NAMES = (
    "MarketSpeed2_RSS_64bit.xll",
    "MarketSpeed2_RSS_VBA.xlam",
)


def _resolve_text(value: Any) -> str:
    try:
        return str(Path(str(value)).resolve())
    except Exception:
        return str(value)


def _read_required_addins(session: Any) -> dict[str, dict[str, Any]]:
    try:
        addins = list(session.application.AddIns)
    except Exception as error:
        return {
            name: {"installed": False, "full_name": f"unavailable: {error}"}
            for name in REQUIRED_ADDIN_NAMES
        }

    results: dict[str, dict[str, Any]] = {}
    for required_name in REQUIRED_ADDIN_NAMES:
        matched = None
        for addin in addins:
            try:
                addin_name = str(getattr(addin, "Name", "")).strip()
            except Exception:
                continue
            if addin_name.casefold() == required_name.casefold():
                matched = addin
                break

        if matched is None:
            results[required_name] = {
                "installed": False,
                "full_name": "missing",
            }
            continue

        try:
            installed = bool(getattr(matched, "Installed"))
        except Exception:
            installed = False
        try:
            full_name = str(getattr(matched, "FullName", required_name))
        except Exception:
            full_name = required_name

        results[required_name] = {
            "installed": installed,
            "full_name": full_name,
        }

    return results


def main() -> int:
    transport = ProductionRakutenRssTransport(
        live_trading_enabled=True,
        production_transport_enabled=True,
        armed=False,
        workbook_path=DEFAULT_WORKBOOK_PATH,
    )
    runtime_state = transport.read_runtime_state()
    health = None
    try:
        if runtime_state.transport_source == TRANSPORT_SOURCE_COM_LIVE:
            health = transport.health_check()
    except Exception as error:
        health = {
            "connected": False,
            "transport_source": runtime_state.transport_source,
            "message": f"health_check failed: {error}",
        }
    session = getattr(transport, "_session", None)

    target_workbook = "FAIL"
    addins = {
        name: {"installed": False, "full_name": "N/A"}
        for name in REQUIRED_ADDIN_NAMES
    }
    b4 = "NOT_CONNECTED"

    if session is not None:
        try:
            target_workbook = (
                "PASS"
                if _resolve_text(session.workbook.FullName) == str(DEFAULT_WORKBOOK_PATH)
                else "FAIL"
            )
        except Exception:
            target_workbook = "FAIL"

        addins = _read_required_addins(session)

        try:
            _, _, b4_value = transport._backend._read_status_values(session)
            b4 = str(b4_value)
        except Exception as error:
            b4 = f"ERR:{error}"
    else:
        target_workbook = "PASS" if DEFAULT_WORKBOOK_PATH.is_file() else "FAIL"
        addins = {
            name: {
                "installed": runtime_state.addin_ready,
                "full_name": "FILE_STATE",
            }
            for name in REQUIRED_ADDIN_NAMES
        }
        b4 = "CONNECTED" if runtime_state.rss_connected else "NOT_CONNECTED"

    if health is None:
        health_connected = runtime_state.ready
        transport_source = runtime_state.transport_source
        health_message = runtime_state.message
    else:
        health_connected = bool(health["connected"]) if isinstance(health, dict) else health.connected
        transport_source = health["transport_source"] if isinstance(health, dict) else health.transport_source
        health_message = health["message"] if isinstance(health, dict) else health.message
    if transport_source == TRANSPORT_SOURCE_COM_LIVE:
        try:
            runtime_state = transport.read_runtime_state()
        except Exception:
            pass
    live_com = health_connected and transport_source == TRANSPORT_SOURCE_COM_LIVE
    report = {
        "selected_workbook_path": str(DEFAULT_WORKBOOK_PATH),
        "Excel COM_LIVE": "PASS" if live_com else "FAIL",
        "target workbook": target_workbook,
        "RSS add-ins": addins,
        "RSS live probe": "PASS" if runtime_state.rss_connected else "FAIL",
        "B4": b4,
        "transport_source": transport_source,
        "health_check": "PASS" if health_connected else "FAIL",
        "health_message": health_message,
        "runtime_ready": runtime_state.ready,
        "armed": False,
        "RssStockOrder_V calls": transport.order_function_call_count,
        "real orders": transport.submitted_count,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if health_connected else 1


if __name__ == "__main__":
    raise SystemExit(main())
