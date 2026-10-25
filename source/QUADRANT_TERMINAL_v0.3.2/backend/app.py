from __future__ import annotations

import asyncio
import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="QUADRANT TERMINAL Read-Only API", version="0.3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_origin_regex=r"^http://(?:(?:192\.168|10\.|172\.(?:1[6-9]|2\d|3[01]))[0-9.]*):1420$",
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
        {"ticker": "7203.T", "side": "LONG", "qty": 100, "avg_price": 2945.0, "last": 3018.0, "pnl": 7300, "pnl_pct": 2.48},
        {"ticker": "8306.T", "side": "LONG", "qty": 200, "avg_price": 2310.0, "last": 2365.5, "pnl": 11100, "pnl_pct": 2.40},
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
}


def build_state(step: int = 0) -> dict[str, Any]:
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

    return state


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "READ_ONLY", "version": "0.3.2"}


@app.get("/api/v1/snapshot")
async def snapshot() -> dict[str, Any]:
    return build_state()


@app.websocket("/ws/v1/state")
async def state_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    step = 0
    try:
        while True:
            await websocket.send_json(build_state(step))
            step += 1
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
