from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import time
from typing import Iterable

import pandas as pd

from execution_core import CACHE_DIR, STATE_DIR, bootstrap_environment, load_json, save_json

CIRCUIT_FILE = STATE_DIR / "yahoo_circuit.json"


class MarketDataGateway:
    """日足分析専用ゲートウェイ。

    同日・同条件の取得結果を再利用し、失敗が続けばYahooへの再アクセスを
    一定時間停止する。実注文価格には絶対に使用しない。
    """

    def __init__(self) -> None:
        self.config = bootstrap_environment()["config"]
        self.cache_root = CACHE_DIR / "market_daily"
        self.cache_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(tickers: Iterable[str], period: str, interval: str) -> str:
        raw = "|".join(sorted(map(str, tickers))) + f"|{period}|{interval}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def _cache_path(self, tickers: list[str], period: str, interval: str) -> Path:
        date_dir = self.cache_root / datetime.now().strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)
        return date_dir / f"{self._key(tickers, period, interval)}.pkl"

    def _circuit_open(self) -> bool:
        state = load_json(CIRCUIT_FILE)
        until = state.get("open_until")
        if not until:
            return False
        try:
            return datetime.now(timezone.utc) < datetime.fromisoformat(str(until))
        except ValueError:
            return False

    def _record_failure(self, reason: str) -> None:
        state = load_json(CIRCUIT_FILE)
        failures = int(state.get("failures", 0)) + 1
        payload = {"failures": failures, "last_error": reason, "updated_at": datetime.now(timezone.utc).isoformat()}
        if failures >= int(self.config.get("yahoo_max_attempts", 2)):
            payload["open_until"] = (datetime.now(timezone.utc) + timedelta(minutes=float(self.config.get("yahoo_cooldown_minutes", 60)))).isoformat()
        save_json(CIRCUIT_FILE, payload)

    def _record_success(self) -> None:
        save_json(CIRCUIT_FILE, {"failures": 0, "updated_at": datetime.now(timezone.utc).isoformat()})

    def download(self, tickers: list[str], period: str = "1y", interval: str = "1d", force_refresh: bool = False) -> tuple[pd.DataFrame, str]:
        if not tickers:
            return pd.DataFrame(), "EMPTY"
        cache_path = self._cache_path(tickers, period, interval)
        reuse = bool(self.config.get("analysis_reuse_today_cache", True)) and not force_refresh and not bool(self.config.get("analysis_force_refresh", False))
        if reuse and cache_path.exists():
            try:
                return pd.read_pickle(cache_path), "TODAY_CACHE"
            except Exception:
                cache_path.unlink(missing_ok=True)
        if self._circuit_open():
            return pd.DataFrame(), "YAHOO_CIRCUIT_OPEN"

        try:
            import yfinance as yf
            result = yf.download(
                tickers=tickers, period=period, interval=interval,
                group_by="ticker", auto_adjust=False, progress=False,
                threads=bool(self.config.get("yahoo_threads", False)),
                timeout=30,
            )
            if result is None or result.empty:
                raise RuntimeError("Yahoo returned empty data")
            result.to_pickle(cache_path)
            self._record_success()
            time.sleep(max(0.0, float(self.config.get("yahoo_chunk_pause_seconds", 3))))
            return result, "YAHOO_LIVE"
        except Exception as exc:
            self._record_failure(str(exc))
            if cache_path.exists():
                try:
                    return pd.read_pickle(cache_path), "TODAY_CACHE_AFTER_FAILURE"
                except Exception:
                    pass
            return pd.DataFrame(), f"YAHOO_FAILED:{type(exc).__name__}"


if __name__ == "__main__":
    print("PHOENIX v6.6 MARKET DATA GATEWAY READY")
