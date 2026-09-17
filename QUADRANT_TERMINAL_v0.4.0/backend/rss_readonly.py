from __future__ import annotations

import os
import platform
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
CHART_TIMEFRAMES = {
    "5m": ("5M", False),
    "15m": ("15M", False),
    "60m": ("60M", False),
    "4h": ("60M", True),
    "1d": ("D", False),
}

READ_ONLY_FUNCTIONS = {
    "RssPositionList",
    "RssOrderList",
    "RssExecutionList",
    "RssCapacityList",
}

FORBIDDEN_ORDER_TOKENS = (
    "RssStockOrder",
    "RssMarginOpenOrder",
    "RssMarginCloseOrder",
    "RssModifyOrder",
    "RssCancelOrder",
    "RssFOPOpenOrder",
    "RssFOPCloseOrder",
    "RssFOPMultiOpenOrder",
    "RssFOPMultiCloseOrder",
    "RssFOPModifyOrder",
    "RssFOPCancelOrder",
)


class RssReadOnlyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RssDiagnostics:
    status: str
    detail: str
    workbook: str


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "-"):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("円", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return default


def _ticker(code: Any) -> str:
    text = _as_text(code)
    if not text or set(text) == {"-"}:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.endswith(".T"):
        return text
    if text.isdigit():
        return f"{text}.T"
    return text


def _normalize_grid(value: Any) -> list[list[Any]]:
    if value is None:
        return []
    if not isinstance(value, tuple):
        return [[value]]
    if value and not isinstance(value[0], tuple):
        return [list(value)]
    return [list(row) for row in value]


def _locate_table(rows: list[list[Any]], required_headers: Iterable[str]) -> tuple[list[str], list[list[Any]]]:
    required = set(required_headers)
    for idx, row in enumerate(rows):
        headers = [_as_text(cell) for cell in row]
        if required.issubset(set(headers)):
            table: list[list[Any]] = []
            for data_row in rows[idx + 1 :]:
                if not any(_as_text(cell) for cell in data_row):
                    if table:
                        break
                    continue
                table.append(data_row)
            return headers, table
    raise RssReadOnlyUnavailable(f"RSS table header not found: {', '.join(required_headers)}")


def _row_dict(headers: list[str], row: list[Any]) -> dict[str, Any]:
    return {header: row[i] if i < len(row) else None for i, header in enumerate(headers) if header}


def _clock_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    text = _as_text(value)
    if " " in text:
        return text.rsplit(" ", 1)[-1]
    return text


def _side(value: Any) -> str:
    text = _as_text(value)
    if "買" in text:
        return "BUY"
    if "売" in text:
        return "SELL"
    return text or "—"


def _order_price(value: Any) -> float | str:
    if isinstance(value, (int, float)):
        return float(value)
    text = _as_text(value)
    if not text:
        return "—"
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return text


def _active_status(*values: Any) -> str:
    texts = [_as_text(value) for value in values if _as_text(value)]
    return " / ".join(texts) if texts else "—"


def _excel_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    text = _as_text(value)
    if not text:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _bar_timestamp(date_value: Any, time_value: Any) -> str:
    date_part = _excel_datetime(date_value)
    time_part = _excel_datetime(time_value)
    if date_part is None:
        return ""
    hour = minute = second = 0
    if time_part is not None:
        hour, minute, second = time_part.hour, time_part.minute, time_part.second
    return datetime(
        date_part.year,
        date_part.month,
        date_part.day,
        hour,
        minute,
        second,
        tzinfo=JST,
    ).isoformat()


def _aggregate_four_hour(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    day_bucket: list[dict[str, Any]] = []
    current_day = ""

    def flush() -> None:
        for start in range(0, len(day_bucket), 4):
            chunk = day_bucket[start : start + 4]
            if not chunk:
                continue
            grouped.append({
                "time": chunk[0]["time"],
                "open": chunk[0]["open"],
                "high": max(item["high"] for item in chunk),
                "low": min(item["low"] for item in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(item["volume"] for item in chunk),
            })

    for bar in bars:
        day = str(bar["time"])[:10]
        if current_day and day != current_day:
            flush()
            day_bucket.clear()
        current_day = day
        day_bucket.append(bar)
    flush()
    return grouped


class ExcelRssReadOnlyAdapter:
    """Read MarketSpeed II RSS output from a dedicated Excel workbook.

    This adapter NEVER invokes an RSS order/mutation function. It only reads cells from
    an already-open workbook whose formulas are limited to approved read-only list/capacity
    functions. The workbook is tied to the MarketSpeed II session currently logged into Excel.
    """

    def __init__(self, workbook_path: str | Path, cache_seconds: float = 1.5) -> None:
        self.workbook_path = Path(workbook_path).resolve()
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cached_at = 0.0
        self._cached_snapshot: dict[str, Any] | None = None
        self._last_error = "not read yet"

    @classmethod
    def from_environment(cls) -> "ExcelRssReadOnlyAdapter":
        default = Path(__file__).resolve().parents[1] / "rss" / "QUADRANT_READONLY_RSS.xlsx"
        path = os.environ.get("QUADRANT_RSS_WORKBOOK", str(default))
        return cls(path)

    def diagnostics(self) -> RssDiagnostics:
        if platform.system() != "Windows":
            return RssDiagnostics("UNAVAILABLE", "Excel RSS bridge requires Windows + Excel", str(self.workbook_path))
        if not self.workbook_path.exists():
            return RssDiagnostics("UNAVAILABLE", "read-only RSS workbook is missing", str(self.workbook_path))
        if self._cached_snapshot is not None:
            return RssDiagnostics("CONNECTED", "read-only workbook data received", str(self.workbook_path))
        return RssDiagnostics("WAITING", self._last_error, str(self.workbook_path))

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            if self._cached_snapshot is not None and now - self._cached_at < self.cache_seconds:
                return self._cached_snapshot
            snapshot = self._read_excel()
            self._cached_snapshot = snapshot
            self._cached_at = now
            self._last_error = "ok"
            return snapshot

    def _read_excel(self) -> dict[str, Any]:
        if platform.system() != "Windows":
            raise RssReadOnlyUnavailable("Excel RSS bridge requires Windows")
        if not self.workbook_path.exists():
            raise RssReadOnlyUnavailable(f"RSS workbook not found: {self.workbook_path}")

        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise RssReadOnlyUnavailable("pywin32 is not installed") from exc

        pythoncom.CoInitialize()
        try:
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except Exception as exc:  # pragma: no cover - Windows/Excel specific
                raise RssReadOnlyUnavailable("Excel is not running. Open the QUADRANT read-only RSS workbook in Excel first.") from exc

            workbook = None
            target_name = self.workbook_path.name.lower()
            target_full = str(self.workbook_path).lower()
            for candidate in excel.Workbooks:
                try:
                    full_name = str(candidate.FullName).lower()
                    name = str(candidate.Name).lower()
                except Exception:
                    continue
                if full_name == target_full or name == target_name:
                    workbook = candidate
                    break

            if workbook is None:
                raise RssReadOnlyUnavailable(
                    f"{self.workbook_path.name} is not open in Excel. Open it in the same Excel instance as MarketSpeed II RSS."
                )

            self._verify_formula_boundary(workbook)
            positions_rows = self._sheet_rows(workbook, "Positions")
            capacity_rows = self._sheet_rows(workbook, "Capacity")
            orders_rows = self._sheet_rows(workbook, "Orders")
            executions_rows = self._sheet_rows(workbook, "Executions")

            positions, watchlist = self._parse_positions(positions_rows)
            account = self._parse_account(capacity_rows, positions)
            orders = self._parse_orders(orders_rows)
            executions = self._parse_executions(executions_rows)

            now_iso = datetime.now(timezone.utc).isoformat()
            return {
                "mode": "READ_ONLY",
                "source": "RAKUTEN_RSS_EXCEL",
                "as_of": now_iso,
                "system": {
                    "phoenix": "NOT_CONNECTED",
                    "market_data": "REAL",
                    "rakuten_rss": "CONNECTED",
                    "live_runtime": "ISOLATED",
                    "watchdog": "UNKNOWN",
                    "analysis": "NOT_CONNECTED",
                },
                "account": account,
                "watchlist": watchlist,
                "positions": positions,
                "orders": orders,
                "executions": executions,
                "events": [
                    {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "level": "PASS",
                        "message": "Rakuten MarketSpeed II RSS account read-only bridge connected",
                    }
                ],
                "meta": {
                    "workbook": self.workbook_path.name,
                    "account_scope": "logged-in MarketSpeed II account",
                    "analysis_available": False,
                    "equity_basis": "現物買付可能額 + 保有銘柄の時価評価額 (推定)",
                },
            }
        except RssReadOnlyUnavailable as exc:
            self._last_error = str(exc)
            raise
        finally:
            pythoncom.CoUninitialize()

    def chart(self, ticker: str, timeframe: str, bars: int = 240) -> dict[str, Any]:
        """Fetch read-only OHLCV through RssChart in a disposable unsaved workbook."""
        normalized_ticker = _ticker(ticker)
        if not normalized_ticker:
            raise RssReadOnlyUnavailable("Invalid ticker")
        key = timeframe.strip().lower()
        if key not in CHART_TIMEFRAMES:
            raise RssReadOnlyUnavailable("Unsupported chart timeframe")
        rss_timeframe, derived_four_hour = CHART_TIMEFRAMES[key]
        requested = max(20, min(int(bars), 1000))
        rss_count = min(3000, requested * 4) if derived_four_hour else requested
        with self._lock:
            return self._read_chart_excel(
                normalized_ticker,
                key,
                rss_timeframe,
                rss_count,
                requested,
                derived_four_hour,
            )

    def _read_chart_excel(
        self,
        ticker: str,
        requested_timeframe: str,
        rss_timeframe: str,
        rss_count: int,
        requested_count: int,
        derived_four_hour: bool,
    ) -> dict[str, Any]:
        if platform.system() != "Windows":
            raise RssReadOnlyUnavailable("Excel RSS chart bridge requires Windows")
        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise RssReadOnlyUnavailable("pywin32 is not installed") from exc

        pythoncom.CoInitialize()
        temp_workbook = None
        try:
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except Exception as exc:
                raise RssReadOnlyUnavailable(
                    "Excel is not running in the QUADRANT backend logon session"
                ) from exc

            target_name = self.workbook_path.name.lower()
            target_full = str(self.workbook_path).lower()
            owner_found = False
            for candidate in excel.Workbooks:
                try:
                    if (
                        str(candidate.FullName).lower() == target_full
                        or str(candidate.Name).lower() == target_name
                    ):
                        owner_found = True
                        break
                except Exception:
                    continue
            if not owner_found:
                raise RssReadOnlyUnavailable(
                    f"{self.workbook_path.name} is not open in the active Excel instance"
                )

            temp_workbook = excel.Workbooks.Add()
            sheet = temp_workbook.Worksheets(1)
            formula = f'=RssChart(,"{ticker}","{rss_timeframe}",{rss_count})'
            sheet.Range("A1").Formula = formula

            rows: list[list[Any]] = []
            last_error = ""
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                try:
                    excel.Calculate()
                    rows = _normalize_grid(sheet.UsedRange.Value)
                    _, data = _locate_table(
                        rows,
                        ("日付", "始値", "高値", "安値", "終値", "出来高"),
                    )
                    if data:
                        break
                except Exception as exc:
                    last_error = str(exc)
                time.sleep(0.15)
            else:
                raise RssReadOnlyUnavailable(
                    "RssChart did not return OHLCV data"
                    + (f": {last_error}" if last_error else "")
                )

            headers, data = _locate_table(
                rows,
                ("日付", "始値", "高値", "安値", "終値", "出来高"),
            )
            parsed: list[dict[str, Any]] = []
            for raw in data:
                item = _row_dict(headers, raw)
                timestamp = _bar_timestamp(item.get("日付"), item.get("時刻"))
                open_price = _as_float(item.get("始値"))
                high = _as_float(item.get("高値"))
                low = _as_float(item.get("安値"))
                close = _as_float(item.get("終値"))
                if not timestamp or min(open_price, high, low, close) <= 0:
                    continue
                parsed.append({
                    "time": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": _as_float(item.get("出来高")),
                })

            parsed.sort(key=lambda row: row["time"])
            if derived_four_hour:
                parsed = _aggregate_four_hour(parsed)
            parsed = parsed[-requested_count:]
            if not parsed:
                raise RssReadOnlyUnavailable("RssChart returned no valid OHLCV rows")

            return {
                "ticker": ticker,
                "timeframe": requested_timeframe,
                "rss_timeframe": rss_timeframe,
                "derived": derived_four_hour,
                "derived_note": (
                    "国内株式は楽天RSSで4H非対応のため、60分足を4本単位でQ表示用に合成"
                    if derived_four_hour
                    else ""
                ),
                "source": "RAKUTEN_RSS_RSSCHART",
                "mode": "READ_ONLY",
                "as_of": datetime.now(timezone.utc).isoformat(),
                "bars": parsed,
            }
        finally:
            if temp_workbook is not None:
                try:
                    temp_workbook.Close(SaveChanges=False)
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def _verify_formula_boundary(self, workbook: Any) -> None:
        found_readonly: set[str] = set()
        for sheet_name in ("Positions", "Capacity", "Orders", "Executions"):
            try:
                sheet = workbook.Worksheets(sheet_name)
                formulas = _normalize_grid(sheet.UsedRange.Formula)
            except Exception as exc:
                raise RssReadOnlyUnavailable(f"Cannot inspect worksheet {sheet_name}") from exc
            for row in formulas:
                for cell in row:
                    text = _as_text(cell)
                    if not text.startswith("="):
                        continue
                    for token in FORBIDDEN_ORDER_TOKENS:
                        if token.lower() in text.lower():
                            raise RssReadOnlyUnavailable(f"Unsafe RSS mutation formula detected: {token}")
                    for token in READ_ONLY_FUNCTIONS:
                        if token.lower() in text.lower():
                            found_readonly.add(token)
        missing = READ_ONLY_FUNCTIONS.difference(found_readonly)
        if missing:
            raise RssReadOnlyUnavailable(f"Required read-only RSS formulas missing: {', '.join(sorted(missing))}")

    @staticmethod
    def _sheet_rows(workbook: Any, name: str) -> list[list[Any]]:
        try:
            sheet = workbook.Worksheets(name)
            return _normalize_grid(sheet.UsedRange.Value2)
        except Exception as exc:
            raise RssReadOnlyUnavailable(f"Cannot read worksheet: {name}") from exc

    @staticmethod
    def _parse_positions(rows: list[list[Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        headers, data = _locate_table(rows, ("銘柄コード", "保有数量", "平均取得価額", "時価"))
        positions: list[dict[str, Any]] = []
        watchlist: list[dict[str, Any]] = []
        for row in data:
            item = _row_dict(headers, row)
            ticker = _ticker(item.get("銘柄コード"))
            if not ticker:
                continue
            qty = _as_float(item.get("保有数量"))
            if qty <= 0:
                continue
            avg = _as_float(item.get("平均取得価額"))
            last = _as_float(item.get("時価"))
            market_value = _as_float(item.get("時価評価額"), qty * last)
            pnl = _as_float(item.get("評価損益額"), (last - avg) * qty)
            pnl_pct = _as_float(item.get("評価損益率"), ((last / avg - 1) * 100 if avg else 0.0))
            change_pct = _as_float(item.get("前日比率"))
            day_change = _as_float(item.get("前日比"))
            name = _as_text(item.get("銘柄名称")) or ticker.replace(".T", "")
            account_type = _as_text(item.get("口座区分")) or "—"
            pending_qty = _as_float(item.get("発注数量"))
            positions.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "side": "LONG",
                    "qty": qty,
                    "avg_price": avg,
                    "last": last,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "market_value": market_value,
                    "account_type": account_type,
                    "pending_qty": pending_qty,
                    "day_change": day_change,
                }
            )
            watchlist.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "price": last,
                    "change_pct": change_pct,
                    "score": None,
                    "signal": "—",
                }
            )
        return positions, watchlist

    @staticmethod
    def _parse_account(rows: list[list[Any]], positions: list[dict[str, Any]]) -> dict[str, Any]:
        headers, data = _locate_table(rows, ("現物買付可能額",))
        values = _row_dict(headers, data[0]) if data else {}
        buying_power = _as_float(values.get("現物買付可能額"))
        market_value = sum(_as_float(item.get("market_value")) for item in positions)
        unrealized = sum(_as_float(item.get("pnl")) for item in positions)
        day_pnl = sum(_as_float(item.get("day_change")) * _as_float(item.get("qty")) for item in positions)
        prior_value = market_value - day_pnl
        day_pct = (day_pnl / prior_value * 100) if prior_value else 0.0
        return {
            "equity": buying_power + market_value,
            "buying_power": buying_power,
            "day_pnl": day_pnl,
            "day_pnl_pct": day_pct,
            "unrealized_pnl": unrealized,
        }

    @staticmethod
    def _parse_orders(rows: list[list[Any]]) -> list[dict[str, Any]]:
        try:
            headers, data = _locate_table(rows, ("銘柄コード", "注文数量", "通常注文状況"))
        except RssReadOnlyUnavailable:
            return []
        result: list[dict[str, Any]] = []
        for row in data:
            item = _row_dict(headers, row)
            ticker = _ticker(item.get("銘柄コード"))
            qty = _as_float(item.get("注文数量"))
            if not ticker or qty <= 0:
                continue
            result.append(
                {
                    "time": _clock_text(item.get("発注/受注日時")),
                    "ticker": ticker,
                    "side": _side(item.get("売買")),
                    "qty": _as_float(item.get("注文数量")),
                    "type": _as_text(item.get("注文区分")) or _as_text(item.get("執行条件")) or "—",
                    "price": _order_price(item.get("注文単価")),
                    "status": _active_status(item.get("通常注文状況"), item.get("逆指値注文状況"), item.get("アルゴ注文状況")),
                }
            )
        return result[:100]

    @staticmethod
    def _parse_executions(rows: list[list[Any]]) -> list[dict[str, Any]]:
        try:
            headers, data = _locate_table(rows, ("銘柄コード", "約定数量", "約定単価", "約定日"))
        except RssReadOnlyUnavailable:
            return []
        result: list[dict[str, Any]] = []
        for row in data:
            item = _row_dict(headers, row)
            ticker = _ticker(item.get("銘柄コード"))
            qty = _as_float(item.get("約定数量"))
            if not ticker or qty <= 0:
                continue
            result.append(
                {
                    "time": _clock_text(item.get("約定日")),
                    "ticker": ticker,
                    "side": _side(item.get("売買")),
                    "qty": _as_float(item.get("約定数量")),
                    "price": _as_float(item.get("約定単価")),
                    "status": "FILLED",
                }
            )
        return result[:100]
