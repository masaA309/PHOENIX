from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from execution_core import ROOT_DIR, bootstrap_environment, read_csv, safe_float


@dataclass(frozen=True)
class QuoteValidation:
    ticker: str
    valid: bool
    current_price: float
    bid: float
    ask: float
    age_seconds: float | None
    spread_percent: float | None
    trading_status: str
    reason: str


class RealtimeGateway:
    """MarketSpeed II RSS bridge reader.

    Excel/VBA writes execution/rss_realtime_quotes.csv. Python only validates and
    consumes it. It never substitutes Yahoo/cache prices for LIVE execution.
    """

    REQUIRED_ALIASES = {
        "ticker": ("ticker", "symbol", "銘柄コード", "code"),
        "current_price": ("current_price", "last", "現在値", "price"),
        "bid": ("bid", "best_bid", "最良買気配"),
        "ask": ("ask", "best_ask", "最良売気配"),
        "timestamp": ("timestamp", "quote_time", "更新時刻", "datetime"),
        "trading_status": ("trading_status", "status", "売買状態"),
    }

    def __init__(self, quote_file: Path | None = None) -> None:
        config = bootstrap_environment()["config"]
        self.config = config
        self.quote_file = quote_file or ROOT_DIR / str(config["rss_quote_file"])

    @staticmethod
    def _find_column(df: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
        normalized = {str(column).strip().lower(): str(column) for column in df.columns}
        for alias in aliases:
            found = normalized.get(alias.lower())
            if found:
                return found
        return None

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        dt = parsed.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def load_quotes(self) -> pd.DataFrame:
        df = read_csv(self.quote_file)
        if df.empty:
            return df
        rename: dict[str, str] = {}
        for canonical, aliases in self.REQUIRED_ALIASES.items():
            column = self._find_column(df, aliases)
            if column:
                rename[column] = canonical
        return df.rename(columns=rename)

    def validate_quote(self, ticker: str, now: datetime | None = None) -> QuoteValidation:
        now_utc = now or datetime.now(timezone.utc)
        df = self.load_quotes()
        clean_ticker = str(ticker).strip().upper()
        if df.empty or "ticker" not in df.columns:
            return QuoteValidation(clean_ticker, False, 0, 0, 0, None, None, "", "RSSリアルタイム価格ファイルなし")

        symbols = df["ticker"].astype(str).str.strip().str.upper()
        match = df[symbols.eq(clean_ticker)]
        if match.empty and clean_ticker.endswith(".T"):
            match = df[symbols.eq(clean_ticker[:-2])]
        if match.empty:
            return QuoteValidation(clean_ticker, False, 0, 0, 0, None, None, "", "対象銘柄のRSS価格なし")

        row = match.iloc[-1]
        current = safe_float(row.get("current_price"))
        bid = safe_float(row.get("bid"))
        ask = safe_float(row.get("ask"))
        timestamp = self._parse_timestamp(row.get("timestamp"))
        age = max(0.0, (now_utc - timestamp).total_seconds()) if timestamp else None
        status = str(row.get("trading_status", "")).strip().upper()
        midpoint = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
        spread = ((ask - bid) / midpoint * 100) if midpoint > 0 and ask >= bid else None

        reasons: list[str] = []
        if current <= 0:
            reasons.append("現在値が不正")
        max_age = safe_float(self.config.get("rss_quote_max_age_seconds"), 15)
        if age is None or age > max_age:
            reasons.append(f"価格が古い(age={age})")
        if bool(self.config.get("require_bid_ask_for_live", True)) and not (bid > 0 and ask > 0 and ask >= bid):
            reasons.append("最良気配が不正")
        max_spread = safe_float(self.config.get("maximum_spread_percent"), 1.0)
        if spread is not None and spread > max_spread:
            reasons.append(f"スプレッド超過({spread:.3f}%)")
        if bool(self.config.get("require_trading_status_for_live", True)) and status not in {"OPEN", "TRADING", "取引中", "通常"}:
            reasons.append(f"売買状態={status or '不明'}")

        return QuoteValidation(
            clean_ticker, not reasons, current, bid, ask, age,
            round(spread, 6) if spread is not None else None,
            status, "正常" if not reasons else " / ".join(reasons),
        )

    def validate_many(self, tickers: list[str]) -> list[dict[str, Any]]:
        return [asdict(self.validate_quote(ticker)) for ticker in tickers]


if __name__ == "__main__":
    gateway = RealtimeGateway()
    quotes = gateway.load_quotes()
    print("PHOENIX v6.6 REALTIME GATEWAY")
    print(f"quote_file: {gateway.quote_file}")
    print(f"rows: {len(quotes)}")
