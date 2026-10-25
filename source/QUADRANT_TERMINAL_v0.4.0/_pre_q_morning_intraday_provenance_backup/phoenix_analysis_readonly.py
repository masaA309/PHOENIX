from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
STALE_AFTER_HOURS = 36


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(round(_float(value, default)))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                return list(csv.DictReader(fh))
        except UnicodeDecodeError:
            continue
    return []


def _generated_at(rows: list[dict[str, str]], path: Path) -> str:
    for row in rows:
        value = _text(row.get("生成日時"))
        if value:
            return value
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime, tz=JST).strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _is_stale(value: str) -> bool:
    if not value:
        return True
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
    except ValueError:
        return True
    return (datetime.now(JST) - dt).total_seconds() > STALE_AFTER_HOURS * 3600


def _by_ticker(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = _text(row.get("ticker"))
        if ticker:
            result[ticker] = row
    return result


class PhoenixAnalysisReadOnlyAdapter:
    """Read PHOENIX report artifacts only. Never import or invoke PHOENIX runtime."""

    def __init__(
        self,
        ranking_file: str | Path,
        trade_signals_file: str | Path,
        ai_judgement_file: str | Path,
    ) -> None:
        self.ranking_file = Path(ranking_file).resolve()
        self.trade_signals_file = Path(trade_signals_file).resolve()
        self.ai_judgement_file = Path(ai_judgement_file).resolve()

    @classmethod
    def from_environment(cls) -> "PhoenixAnalysisReadOnlyAdapter":
        root = Path(__file__).resolve().parents[2]
        reports = root / "reports"
        return cls(
            os.environ.get("QUADRANT_PHOENIX_RANKING", str(reports / "ranking_ai.csv")),
            os.environ.get("QUADRANT_PHOENIX_SIGNALS", str(reports / "trade_signals.csv")),
            os.environ.get("QUADRANT_PHOENIX_AI", str(reports / "ai_judgement.csv")),
        )

    def snapshot(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        ranking_rows = _read_csv(self.ranking_file)
        signal_rows = _read_csv(self.trade_signals_file)
        ai_rows = _read_csv(self.ai_judgement_file)

        if not ranking_rows:
            return [], {
                "analysis_available": False,
                "analysis_error": "ranking_ai.csv not found or empty",
            }

        signals = _by_ticker(signal_rows)
        ai = _by_ticker(ai_rows)

        ranking_generated = _generated_at(ranking_rows, self.ranking_file)
        signal_generated = _generated_at(signal_rows, self.trade_signals_file)
        ai_generated = _generated_at(ai_rows, self.ai_judgement_file)

        ranking: list[dict[str, Any]] = []
        for row in ranking_rows:
            ticker = _text(row.get("ticker"))
            name = _text(row.get("銘柄"))
            if not ticker or not name:
                continue

            signal = signals.get(ticker, {})
            judgement = ai.get(ticker, {})

            ranking.append({
                "rank": _int(row.get("順位")),
                "ticker": ticker,
                "name": name,
                "price": _float(row.get("価格")),
                "change_pct": _float(signal.get("前日比%"), _float(judgement.get("前日比%"))),
                "score": _float(row.get("ランキング点")),
                "signal": _text(signal.get("Trade判定")) or _text(row.get("AI判断")) or "—",
                "phoenix_score": _float(row.get("PHOENIX_SCORE")),
                "ai_score": _float(row.get("AI判断点")),
                "rank_label": _text(row.get("ランク")),
                "watch_status": _text(row.get("監視区分")),
                "risk": _text(row.get("リスク")),
                "rsi": _float(row.get("RSI")),
                "macd": _text(row.get("MACD判定")),
                "volume_ratio": _float(row.get("出来高倍率")),
                "expected_win_rate": _float(row.get("期待勝率%")),
                "reason": _text(row.get("ランキング根拠")),
                "technical_reason": _text(row.get("テクニカル根拠")),
                "learning_reason": _text(row.get("学習根拠")) or _text(judgement.get("自己学習根拠")),
                "phoenix_reason": _text(judgement.get("PHOENIX理由")),
                "plus_material": _text(judgement.get("プラス材料")),
                "caution_material": _text(judgement.get("注意材料")),
                "monitor_timing": _text(judgement.get("監視タイミング")),
                "base_price": _float(signal.get("基準価格")),
                "entry_price": _float(signal.get("押し目価格")),
                "target_price": _float(signal.get("利確価格"), _float(judgement.get("参考目標価格"))),
                "stop_price": _float(signal.get("損切価格"), _float(judgement.get("参考損切価格"))),
                "trade_decision": _text(signal.get("Trade判定")),
                "decision_reason": _text(signal.get("判定理由")),
                "market_risk_score": _float(signal.get("MarketRiskScore")),
                "market_risk_level": _text(signal.get("MarketRiskLevel")),
                "artifact_generated_at": ranking_generated,
            })

        timestamps = [x for x in (ranking_generated, signal_generated, ai_generated) if x]
        parsed_times: list[datetime] = []
        for value in timestamps:
            try:
                parsed_times.append(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST))
            except ValueError:
                pass
        if len(parsed_times) == len(timestamps) and parsed_times:
            spread_seconds = (max(parsed_times) - min(parsed_times)).total_seconds()
            consistency = "CONSISTENT_RUN" if spread_seconds <= 300 else "MIXED_TIMESTAMPS"
        else:
            consistency = "NOT_PROVEN"
        newest = max(timestamps) if timestamps else ""

        return ranking, {
            "analysis_available": bool(ranking),
            "analysis_generated_at": newest,
            "analysis_stale": any(_is_stale(value) for value in timestamps) if timestamps else True,
            "analysis_source": "PHOENIX report artifacts (READ ONLY)",
            "analysis_count": len(ranking),
            "analysis_consistency": consistency,
            "analysis_artifacts": {
                "ranking_ai": {"path": str(self.ranking_file), "generated_at": ranking_generated, "stale": _is_stale(ranking_generated)},
                "trade_signals": {"path": str(self.trade_signals_file), "generated_at": signal_generated, "stale": _is_stale(signal_generated)},
                "ai_judgement": {"path": str(self.ai_judgement_file), "generated_at": ai_generated, "stale": _is_stale(ai_generated)},
            },
        }
