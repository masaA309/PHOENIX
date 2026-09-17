from __future__ import annotations

import csv
import os
from datetime import datetime
from hashlib import sha256
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


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_meta(path: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    generated_at = _generated_at(rows, path)
    return {
        "name": path.name,
        "path": str(path),
        "exists": path.is_file(),
        "rows": len(rows),
        "generated_at": generated_at,
        "stale": _is_stale(generated_at),
        "sha256": _file_sha256(path),
    }


def _pick_text(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _pick_float(row: dict[str, str], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return _float(value, default)
    return default


def _parse_intraday_candidates(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        ticker = _pick_text(row, "ticker", "Ticker")
        name = _pick_text(row, "銘柄", "銘柄名", "name")
        if not ticker or not name:
            continue
        discovered_at = _pick_text(row, "発見日時", "生成日時", "timestamp", "generated_at")
        discovery_reason = _pick_text(row, "発見理由", "昇格理由", "ランキング根拠", "判定理由", "テクニカル根拠")
        candidates.append({
            "rank": _int(row.get("順位"), index),
            "ticker": ticker,
            "name": name,
            "price": _pick_float(row, "価格", "現在値", "last"),
            "change_pct": _pick_float(row, "前日比%", "当日騰落率%", "change_pct"),
            "score": _pick_float(row, "ランキング点", "PHOENIX_SCORE", "score"),
            "signal": _pick_text(row, "Trade判定", "AI判断", "signal") or "WATCH",
            "phoenix_score": _pick_float(row, "PHOENIX_SCORE", "phoenix_score"),
            "ai_score": _pick_float(row, "AI判断点", "ai_score"),
            "watch_status": _pick_text(row, "監視区分", "候補状態", "status"),
            "risk": _pick_text(row, "リスク", "risk"),
            "rsi": _pick_float(row, "RSI", "RSI14", "rsi"),
            "macd": _pick_text(row, "MACD判定", "MACD", "macd"),
            "volume_ratio": _pick_float(row, "出来高倍率", "volume_ratio"),
            "reason": discovery_reason,
            "technical_reason": _pick_text(row, "テクニカル根拠"),
            "phoenix_reason": _pick_text(row, "PHOENIX理由"),
            "caution_material": _pick_text(row, "注意材料"),
            "monitor_timing": _pick_text(row, "監視タイミング"),
            "base_price": _pick_float(row, "基準価格"),
            "entry_price": _pick_float(row, "押し目価格", "ENTRY", "entry_price"),
            "target_price": _pick_float(row, "利確価格", "TARGET", "target_price"),
            "stop_price": _pick_float(row, "損切価格", "STOP", "stop_price"),
            "trade_decision": _pick_text(row, "Trade判定", "trade_decision"),
            "decision_reason": _pick_text(row, "判定理由", "decision_reason") or discovery_reason,
            "artifact_generated_at": discovered_at,
            "origin": "INTRADAY",
            "discovered_at": discovered_at,
            "discovery_reason": discovery_reason,
            "promotion_status": _pick_text(row, "昇格状態", "候補状態", "status") or "DISCOVERED",
        })
    return candidates


class PhoenixAnalysisReadOnlyAdapter:
    """Read PHOENIX report artifacts only. Never import or invoke PHOENIX runtime."""

    def __init__(
        self,
        ranking_file: str | Path,
        trade_signals_file: str | Path,
        ai_judgement_file: str | Path,
        intraday_file: str | Path,
    ) -> None:
        self.ranking_file = Path(ranking_file).resolve()
        self.trade_signals_file = Path(trade_signals_file).resolve()
        self.ai_judgement_file = Path(ai_judgement_file).resolve()
        self.intraday_file = Path(intraday_file).resolve()

    @classmethod
    def from_environment(cls) -> "PhoenixAnalysisReadOnlyAdapter":
        root = Path(__file__).resolve().parents[2]
        reports = root / "reports"
        return cls(
            os.environ.get("QUADRANT_PHOENIX_RANKING", str(reports / "ranking_ai.csv")),
            os.environ.get("QUADRANT_PHOENIX_SIGNALS", str(reports / "trade_signals.csv")),
            os.environ.get("QUADRANT_PHOENIX_AI", str(reports / "ai_judgement.csv")),
            os.environ.get("QUADRANT_PHOENIX_INTRADAY", str(reports / "intraday_candidates.csv")),
        )

    def snapshot(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        ranking_rows = _read_csv(self.ranking_file)
        signal_rows = _read_csv(self.trade_signals_file)
        ai_rows = _read_csv(self.ai_judgement_file)
        intraday_rows = _read_csv(self.intraday_file)
        intraday = _parse_intraday_candidates(intraday_rows)
        intraday_generated = _generated_at(intraday_rows, self.intraday_file)

        if not ranking_rows:
            return [], intraday, {
                "analysis_available": False,
                "analysis_error": "ranking_ai.csv not found or empty",
                "intraday_available": bool(intraday),
                "intraday_count": len(intraday),
                "intraday_generated_at": intraday_generated,
                "intraday_stale": _is_stale(intraday_generated),
                "intraday_artifact": _artifact_meta(self.intraday_file, intraday_rows),
                "provenance_mode": "READ_ONLY",
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
                "origin": "MORNING",
                "discovered_at": ranking_generated,
                "discovery_reason": _text(row.get("ランキング根拠")) or _text(signal.get("判定理由")),
                "promotion_status": _text(row.get("監視区分")) or _text(signal.get("Trade判定")),
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

        return ranking, intraday, {
            "analysis_available": bool(ranking),
            "analysis_generated_at": newest,
            "analysis_stale": any(_is_stale(value) for value in timestamps) if timestamps else True,
            "analysis_source": "PHOENIX report artifacts (READ ONLY)",
            "analysis_count": len(ranking),
            "analysis_consistency": consistency,
            "analysis_lineage": "MORNING: ranking_ai + trade_signals + ai_judgement",
            "analysis_artifacts": {
                "ranking_ai": _artifact_meta(self.ranking_file, ranking_rows),
                "trade_signals": _artifact_meta(self.trade_signals_file, signal_rows),
                "ai_judgement": _artifact_meta(self.ai_judgement_file, ai_rows),
            },
            "intraday_available": bool(intraday),
            "intraday_generated_at": intraday_generated,
            "intraday_stale": _is_stale(intraday_generated),
            "intraday_count": len(intraday),
            "intraday_source": "PHOENIX intraday candidate artifact (READ ONLY)",
            "intraday_artifact": _artifact_meta(self.intraday_file, intraday_rows),
            "provenance_mode": "READ_ONLY",
        }
