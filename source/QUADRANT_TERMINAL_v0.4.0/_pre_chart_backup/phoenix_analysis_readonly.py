from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


class PhoenixAnalysisReadOnlyAdapter:
    """Read PHOENIX ranking artifacts without importing or invoking PHOENIX runtime."""

    def __init__(self, ranking_file: str | Path) -> None:
        self.ranking_file = Path(ranking_file).resolve()

    @classmethod
    def from_environment(cls) -> "PhoenixAnalysisReadOnlyAdapter":
        root = Path(__file__).resolve().parents[2]
        default = root / "reports" / "ranking_ai.csv"
        return cls(os.environ.get("QUADRANT_PHOENIX_RANKING", str(default)))

    def snapshot(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not self.ranking_file.exists():
            return [], {"analysis_available": False, "analysis_error": "ranking_ai.csv not found"}

        rows: list[dict[str, str]] = []
        for encoding in ("utf-8-sig", "utf-8", "cp932"):
            try:
                with self.ranking_file.open("r", encoding=encoding, newline="") as fh:
                    rows = list(csv.DictReader(fh))
                break
            except UnicodeDecodeError:
                continue

        ranking: list[dict[str, Any]] = []
        generated_at = ""
        for row in rows:
            ticker = str(row.get("ticker", "")).strip()
            name = str(row.get("銘柄", "")).strip()
            if not ticker or not name:
                continue
            generated_at = str(row.get("生成日時", generated_at)).strip() or generated_at
            ranking.append({
                "rank": _int(row.get("順位")),
                "ticker": ticker,
                "name": name,
                "price": _float(row.get("価格")),
                "change_pct": 0.0,
                "score": _float(row.get("ランキング点")),
                "signal": str(row.get("AI判断", "—")).strip() or "—",
                "phoenix_score": _float(row.get("PHOENIX_SCORE")),
                "ai_score": _float(row.get("AI判断点")),
                "rank_label": str(row.get("ランク", "")).strip(),
                "watch_status": str(row.get("監視区分", "")).strip(),
                "risk": str(row.get("リスク", "")).strip(),
                "rsi": _float(row.get("RSI")),
                "macd": str(row.get("MACD判定", "")).strip(),
                "volume_ratio": _float(row.get("出来高倍率")),
                "expected_win_rate": _float(row.get("期待勝率%")),
                "reason": str(row.get("ランキング根拠", "")).strip(),
                "technical_reason": str(row.get("テクニカル根拠", "")).strip(),
            })

        stale = True
        if generated_at:
            try:
                dt = datetime.strptime(generated_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                stale = (datetime.now(timezone.utc) - dt).total_seconds() > 36 * 3600
            except ValueError:
                stale = True

        return ranking, {
            "analysis_available": bool(ranking),
            "analysis_generated_at": generated_at,
            "analysis_stale": stale,
            "analysis_source": str(self.ranking_file),
            "analysis_count": len(ranking),
        }
