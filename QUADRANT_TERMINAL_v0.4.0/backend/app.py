from __future__ import annotations

import asyncio
import math
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from rss_readonly import ExcelRssReadOnlyAdapter, RssReadOnlyUnavailable
from phoenix_analysis_readonly import PhoenixAnalysisReadOnlyAdapter

VERSION = "0.4.0"
DATA_SOURCE = os.environ.get("QUADRANT_DATA_SOURCE", "mock").strip().lower()
if DATA_SOURCE not in {"mock", "rss"}:
    raise RuntimeError("QUADRANT_DATA_SOURCE must be 'mock' or 'rss'")

app = FastAPI(title="QUADRANT TERMINAL Read-Only API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_origin_regex=r"^http://(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}):1420$",
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_STATE: dict[str, Any] = {
    "mode": "READ_ONLY",
    "source": "MOCK_BACKEND",
    "as_of": "",
    "system": {
        "phoenix": "ONLINE",
        "market_data": "SIMULATED",
        "rakuten_rss": "NOT_CONNECTED",
        "live_runtime": "ISOLATED",
        "watchdog": "OK",
        "analysis": "MOCK",
    },
    "account": {
        "equity": 4_862_430,
        "buying_power": 1_725_000,
        "day_pnl": 28_460,
        "day_pnl_pct": 0.59,
        "unrealized_pnl": 41_700,
    },
    "watchlist": [
        {"ticker": "7203.T", "name": "Toyota", "price": 3018.0, "change_pct": 1.24, "score": 92, "signal": "BUY"},
        {"ticker": "8306.T", "name": "MUFG", "price": 2365.5, "change_pct": 0.82, "score": 87, "signal": "WATCH"},
        {"ticker": "9984.T", "name": "SoftBank G", "price": 17120.0, "change_pct": -0.31, "score": 78, "signal": "HOLD"},
        {"ticker": "6758.T", "name": "Sony G", "price": 3248.0, "change_pct": 0.46, "score": 84, "signal": "BUY"},
        {"ticker": "6501.T", "name": "Hitachi", "price": 4483.0, "change_pct": 1.03, "score": 89, "signal": "WATCH"},
    ],
    "positions": [
        {"ticker": "7203.T", "name": "Toyota", "side": "LONG", "qty": 100, "avg_price": 2945.0, "last": 3018.0, "pnl": 7300, "pnl_pct": 2.48, "market_value": 301800, "account_type": "特定", "pending_qty": 0},
        {"ticker": "8306.T", "name": "MUFG", "side": "LONG", "qty": 200, "avg_price": 2310.0, "last": 2365.5, "pnl": 11100, "pnl_pct": 2.40, "market_value": 473100, "account_type": "NISA", "pending_qty": 0},
    ],
    "orders": [
        {"time": "14:31:52", "ticker": "6758.T", "side": "BUY", "qty": 100, "type": "LIMIT", "price": 3240.0, "status": "SUBMITTED"},
        {"time": "14:29:18", "ticker": "7203.T", "side": "SELL", "qty": 100, "type": "STOP", "price": 2970.0, "status": "WORKING"},
    ],
    "executions": [
        {"time": "13:42:05", "ticker": "8306.T", "side": "BUY", "qty": 200, "price": 2310.0, "status": "FILLED"},
        {"time": "09:14:33", "ticker": "7203.T", "side": "BUY", "qty": 100, "price": 2945.0, "status": "FILLED"},
    ],
    "events": [
        {"time": "14:31:53", "level": "INFO", "message": "6758.T BUY request accepted by mock adapter"},
        {"time": "14:30:21", "level": "INFO", "message": "7203.T quote update received"},
        {"time": "14:29:04", "level": "PASS", "message": "Risk policy observation: PASS (display only)"},
        {"time": "09:00:00", "level": "INFO", "message": "QUADRANT / VERMILION read-only session started (PHOENIX engine)"},
    ],
    "meta": {
        "analysis_available": True,
        "account_scope": "mock",
        "equity_basis": "mock",
    },
}

RSS_ADAPTER = ExcelRssReadOnlyAdapter.from_environment()
PHOENIX_ANALYSIS = PhoenixAnalysisReadOnlyAdapter.from_environment()


def _sma(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            result[index] = running / period
    return result


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def score(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)

    result[period] = score(avg_gain, avg_loss)
    for index in range(period + 1, len(values)):
        delta = values[index] - values[index - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
        result[index] = score(avg_gain, avg_loss)
    return result


def _decorate_chart(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("bars", [])
    closes = [float(row["close"]) for row in rows]
    ma5 = _sma(closes, 5)
    ma25 = _sma(closes, 25)
    ma75 = _sma(closes, 75)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    rsi14 = _rsi(closes, 14)
    macd = [a - b for a, b in zip(ema12, ema26)]
    macd_signal = _ema(macd, 9)

    for index, row in enumerate(rows):
        row["ma5"] = ma5[index]
        row["ma25"] = ma25[index]
        row["ma75"] = ma75[index]
        row["ema12"] = ema12[index] if index < len(ema12) else None
        row["ema26"] = ema26[index] if index < len(ema26) else None
        row["rsi14"] = rsi14[index]
        row["macd"] = macd[index] if index < len(macd) else None
        row["macd_signal"] = macd_signal[index] if index < len(macd_signal) else None

    last = rows[-1] if rows else {}
    payload["indicators"] = {
        "basis": "RSS_VIEW_SELECTED_TIMEFRAME",
        "ma5": last.get("ma5"),
        "ma25": last.get("ma25"),
        "ma75": last.get("ma75"),
        "ema12": last.get("ema12"),
        "ema26": last.get("ema26"),
        "rsi14": last.get("rsi14"),
        "macd": last.get("macd"),
        "macd_signal": last.get("macd_signal"),
    }
    return payload


def build_mock_state(step: int = 0) -> dict[str, Any]:
    state = deepcopy(BASE_STATE)
    wave = math.sin(step / 3.0)
    delta = round(wave * 3.0, 1)
    state["as_of"] = datetime.now(timezone.utc).isoformat()

    for item in state["watchlist"]:
        if item["ticker"] == "7203.T":
            item["price"] = round(item["price"] + delta, 1)
            item["change_pct"] = round(item["change_pct"] + wave * 0.03, 2)

    for position in state["positions"]:
        if position["ticker"] == "7203.T":
            position["last"] = round(3018.0 + delta, 1)
            position["pnl"] = round((position["last"] - position["avg_price"]) * position["qty"])
            position["pnl_pct"] = round((position["last"] / position["avg_price"] - 1) * 100, 2)
            position["market_value"] = round(position["last"] * position["qty"])

    return state


def rss_unavailable_state(detail: str) -> dict[str, Any]:
    return {
        "mode": "READ_ONLY",
        "source": "RAKUTEN_RSS_UNAVAILABLE",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "system": {
            "phoenix": "NOT_CONNECTED",
            "market_data": "UNAVAILABLE",
            "rakuten_rss": "OFFLINE",
            "live_runtime": "ISOLATED",
            "watchdog": "UNKNOWN",
            "analysis": "NOT_CONNECTED",
        },
        "account": {"equity": 0, "buying_power": 0, "day_pnl": 0, "day_pnl_pct": 0, "unrealized_pnl": 0},
        "watchlist": [],
        "positions": [],
        "orders": [],
        "executions": [],
        "events": [{"time": datetime.now().strftime("%H:%M:%S"), "level": "WARN", "message": detail}],
        "meta": {"analysis_available": False, "account_scope": "unavailable", "equity_basis": "n/a", "error": detail},
    }


def attach_phoenix_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ranking, intraday_candidates, analysis_meta = PHOENIX_ANALYSIS.snapshot()
    state["ranking"] = ranking
    state["intraday_candidates"] = intraday_candidates
    state.setdefault("meta", {}).update(analysis_meta)
    if ranking:
        state.setdefault("system", {})["analysis"] = "STALE" if analysis_meta.get("analysis_stale") else "CONNECTED"
    elif intraday_candidates:
        state.setdefault("system", {})["analysis"] = "STALE" if analysis_meta.get("intraday_stale") else "CONNECTED"
    return state


async def build_state(step: int = 0) -> dict[str, Any]:
    if DATA_SOURCE == "mock":
        return build_mock_state(step)
    try:
        state = await asyncio.to_thread(RSS_ADAPTER.snapshot)
    except RssReadOnlyUnavailable as exc:
        state = rss_unavailable_state(str(exc))
    return await asyncio.to_thread(attach_phoenix_analysis, state)


@app.get("/health")
async def health() -> dict[str, Any]:
    diag = RSS_ADAPTER.diagnostics()
    return {
        "status": "ok",
        "mode": "READ_ONLY",
        "version": VERSION,
        "data_source": DATA_SOURCE,
        "rss": {"status": diag.status, "detail": diag.detail},
    }


@app.get("/api/v1/snapshot")
async def snapshot() -> dict[str, Any]:
    return await build_state()


@app.get("/api/v1/chart/{ticker}")
async def chart(ticker: str, timeframe: str = "5m", bars: int = 240) -> dict[str, Any]:
    if DATA_SOURCE != "rss":
        raise HTTPException(status_code=503, detail="Real RSS chart is available only in rss mode")
    try:
        payload = await asyncio.to_thread(RSS_ADAPTER.chart, ticker, timeframe, bars)
    except RssReadOnlyUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _decorate_chart(payload)


@app.get("/api/v1/diagnostics")
async def diagnostics() -> dict[str, Any]:
    diag = RSS_ADAPTER.diagnostics()
    _, intraday_candidates, analysis_meta = await asyncio.to_thread(PHOENIX_ANALYSIS.snapshot)
    return {
        "mode": "READ_ONLY",
        "data_source": DATA_SOURCE,
        "rss": {"status": diag.status, "detail": diag.detail, "workbook": diag.workbook},
        "analysis": analysis_meta,
        "intraday_candidate_count": len(intraday_candidates),
        "mutation_routes": [],
    }


@app.websocket("/ws/v1/state")
async def state_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    step = 0
    try:
        while True:
            await websocket.send_json(await build_state(step))
            step += 1
            await asyncio.sleep(2.0 if DATA_SOURCE == "rss" else 1.0)
    except WebSocketDisconnect:
        return
