"""VERMILION (制度信用LONG) read-only adapter for Q.

Reads the margin-LONG runner state written by PHOENIX `run_margin_long.py`
(state/margin_long/live when it exists, otherwise state/margin_long/shadow).
Display only: never writes, never imports order code, never changes gates.
Missing/invalid data is shown as NOT_PROVEN, never guessed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

STALE_SECONDS = 36 * 3600  # state is updated at least every trading day (EOD)
MAX_HOLD_SESSIONS = 40


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _tail_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _gate_flags(phoenix_root: Path) -> dict[str, str]:
    """Static read of the release gates in source (display only)."""
    gates = {"route": "NOT_PROVEN", "broker_live": "NOT_PROVEN", "armed": "NOT_PROVEN"}
    try:
        text = (phoenix_root / "phoenix_core" / "rakuten_rss_long_margin.py").read_text(encoding="utf-8")
        gates["route"] = "CLOSED" if "LONG_MARGIN_ROUTE_RELEASED = False" in text else "OPEN"
    except OSError:
        pass
    try:
        text = (phoenix_root / "run_margin_long.py").read_text(encoding="utf-8")
        gates["broker_live"] = "CLOSED" if "    live = False\n" in text else "OPEN"
        gates["armed"] = "CLOSED" if "armed=False" in text else "OPEN"
    except OSError:
        pass
    return gates


class VermilionReadOnlyAdapter:
    def __init__(self, phoenix_root: Path) -> None:
        self.root = phoenix_root.resolve()
        self.base = self.root / "state" / "margin_long"

    @classmethod
    def from_environment(cls) -> "VermilionReadOnlyAdapter":
        default = Path(__file__).resolve().parents[2]
        return cls(Path(os.environ.get("QUADRANT_PHOENIX_ROOT", str(default))))

    def _source_dir(self) -> tuple[str, Path] | None:
        for mode in ("live", "shadow"):
            directory = self.base / mode
            if (directory / "state.json").exists():
                return mode.upper(), directory
        return None

    def snapshot(self, last_prices: dict[str, float] | None = None) -> dict[str, Any]:
        last_prices = last_prices or {}
        gates = _gate_flags(self.root)
        found = self._source_dir()
        if found is None:
            return {"available": False, "mode": "NOT_CONNECTED", "gates": gates, "positions": [], "planned": [],
                    "events": [], "updated_at": "", "stale": True}
        mode, directory = found
        state = _read_json(directory / "state.json") or {}
        meta = _read_json(directory / "meta.json") or {}
        try:
            mtime = datetime.fromtimestamp((directory / "state.json").stat().st_mtime)
        except OSError:
            mtime = None
        stale = mtime is None or (datetime.now() - mtime).total_seconds() > STALE_SECONDS
        positions = []
        pending = state.get("pending_closes", {}) or {}
        for ticker, p in (state.get("positions", {}) or {}).items():
            try:
                entry = float(p["entry_price"]); r = float(p["initial_r"]); qty = int(p["quantity"])
                eff = float(p["effective_stop"]); pend = float(p.get("pending_stop", eff)); init = float(p["initial_stop"])
            except (KeyError, TypeError, ValueError):
                positions.append({"ticker": ticker, "side": "LONG", "execution": "MARGIN", "status": "NOT_PROVEN",
                                  "qty": 0, "avg_price": 0, "last": 0, "pnl": 0, "pnl_pct": 0, "source": mode})
                continue
            last = last_prices.get(ticker)
            status = ("EXIT_PENDING" if ticker in pending or p.get("time_exit_due")
                      else "TRAILING" if eff > init + 1e-9 else "HOLDING")
            row = {
                "ticker": ticker, "side": "LONG", "execution": "MARGIN", "status": status, "source": mode,
                "engine": "VERMILION", "qty": qty, "avg_price": round(entry, 2),
                "initial_stop": round(init, 2), "current_stop": round(eff, 2),
                "pending_stop": round(max(pend, eff), 2), "initial_r": round(r, 2),
                "held_sessions": int(p.get("held_sessions", 0)), "max_hold_sessions": MAX_HOLD_SESSIONS,
                "time_exit_due": bool(p.get("time_exit_due")), "open_date": str(p.get("open_date", "")),
                "locked_r": round((eff - entry) / r, 2) if r > 0 else None,
            }
            if isinstance(last, (int, float)) and last > 0:
                row.update(last=float(last), pnl=round((last - entry) * qty), pnl_pct=round((last / entry - 1) * 100, 2),
                           current_r=round((last - entry) / r, 2) if r > 0 else None, market_value=round(last * qty))
            else:
                row.update(last=0, pnl=0, pnl_pct=0, current_r=None, price_status="NOT_PROVEN")
            # V-LOCK (display): the stop already protects a profit at or above entry
            row["v_lock_display"] = "ACTIVE" if eff >= entry else "INACTIVE"
            positions.append(row)
        planned = [{"ticker": x.get("ticker"), "quantity": x.get("quantity"), "limit_price": x.get("limit_price"),
                    "signal_date": x.get("signal_date"), "submitted": bool(x.get("client_order_id"))}
                   for x in state.get("planned", []) or []]
        events = []
        for e in _tail_jsonl(directory / "shadow_log.jsonl")[-40:]:
            level = "ERROR" if e.get("result") in ("ERROR",) else "WARN" if e.get("result") == "RSS_UNAVAILABLE" else "INFO"
            text = e.get("result") or ""
            for key in ("paper_open", "paper_close", "entry_skipped_gap"):
                if key in e:
                    text = f"{key} {e[key]} {e.get('price', e.get('open', ''))} {e.get('reason', '')}".strip()
            if e.get("job") == "eod" and "planned" in e:
                text = f"EOD {e.get('session', '')} planned {len(e['planned'])}"
            events.append({"time": str(e.get("at", ""))[11:19], "level": level, "message": f"[{e.get('job', '')}] {text}"[:160]})
        reports = sorted(directory.glob("report_*.html"))
        return {
            "available": True, "mode": mode, "gates": gates, "positions": positions, "planned": planned,
            "events": events, "equity_paper": meta.get("equity"), "last_eod": meta.get("last_eod", ""),
            "updated_at": mtime.isoformat(timespec="seconds") if mtime else "", "stale": stale,
            "latest_report": reports[-1].name if reports else "",
        }
