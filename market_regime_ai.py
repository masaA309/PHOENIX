from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from phoenix_core.performance_tracker import atomic_write, resolve_path


MANIFEST_FILE = "reports/notification_source_manifest.json"
RISK_CONFIG_FILE = "config/v7_risk_config.json"
OUTPUT_FILE = "reports/market_regime.json"
LEGACY_MARKET_RISK_FILE = "data/market_risk_latest.json"
REQUIRED_COLUMNS = ("ticker", "価格", "MA25", "MA75", "前日比%", "MACD判定", "RSI")
VALID_REGIMES = {"BULL", "NEUTRAL", "BEAR"}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return text


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(root: Path) -> dict[str, Any]:
    manifest = _read_json(resolve_path(root, MANIFEST_FILE))
    required = ("run_id", "report_file", "report_sha256", "ticker_count", "expected_ticker_count")
    missing = [field for field in required if field not in manifest]
    if missing:
        raise ValueError(f"manifest is missing fields: {', '.join(missing)}")
    return manifest


def _load_risk_threshold(root: Path) -> float:
    payload = _read_json(resolve_path(root, RISK_CONFIG_FILE))
    value = payload.get("breadth_threshold")
    if value is None:
        raise ValueError("breadth_threshold is missing from risk config")
    threshold = float(value)
    if not (0.0 <= threshold <= 1.0):
        raise ValueError("breadth_threshold must be between 0 and 1")
    return threshold


def _load_report(root: Path, manifest: Mapping[str, Any]) -> pd.DataFrame:
    report_path = resolve_path(root, str(manifest["report_file"]))
    if not report_path.is_file():
        raise FileNotFoundError(report_path)
    report_sha256 = _sha256(report_path)
    expected_sha256 = _normalize_text(manifest.get("report_sha256"))
    if not expected_sha256:
        raise ValueError("manifest report_sha256 is missing")
    if report_sha256 != expected_sha256:
        raise ValueError("report_sha256 mismatch")

    frame = pd.read_csv(report_path, encoding="utf-8-sig")
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"daily report is missing columns: {', '.join(missing_columns)}")

    expected_ticker_count = int(manifest.get("expected_ticker_count", 0))
    ticker_count = int(manifest.get("ticker_count", 0))
    if ticker_count != 225 or expected_ticker_count != 225:
        raise ValueError("ticker_count must be 225")
    if len(frame) != ticker_count:
        raise ValueError("daily report row count does not match manifest")
    if frame["ticker"].map(_normalize_text).eq("").any():
        raise ValueError("ticker column contains empty values")
    if frame["ticker"].map(_normalize_text).nunique() != ticker_count:
        raise ValueError("ticker column must contain 225 unique symbols")

    for column in ("価格", "MA25", "MA75", "前日比%", "RSI"):
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.isna().any():
            raise ValueError(f"{column} column contains invalid numeric values")
        frame[column] = numeric

    macd = frame["MACD判定"].map(_normalize_text)
    if macd.eq("").any():
        raise ValueError("MACD判定 column contains invalid values")

    return frame


def _legacy_bear_override(root: Path) -> bool:
    legacy_path = resolve_path(root, LEGACY_MARKET_RISK_FILE)
    if not legacy_path.is_file():
        return False
    try:
        payload = _read_json(legacy_path)
    except Exception:
        return False

    keys_to_check = (
        "regime",
        "market_regime",
        "risk",
        "risk_level",
        "state",
        "signal",
        "judgement",
        "classification",
        "score",
    )

    for key in keys_to_check:
        value = payload.get(key)
        if isinstance(value, Mapping):
            for nested_key in keys_to_check:
                nested_value = value.get(nested_key)
                if _normalize_text(nested_value).upper() == "BEAR":
                    return True
        if _normalize_text(value).upper() == "BEAR":
            return True
    return False


def _determine_regime(*, breadth_ratio: float, threshold: float, legacy_bear: bool) -> str:
    if legacy_bear or breadth_ratio < threshold:
        return "BEAR"
    if breadth_ratio >= min(1.0, threshold + 0.10):
        return "BULL"
    return "NEUTRAL"


def build_market_regime(root: Path) -> dict[str, Any]:
    manifest = _load_manifest(root)
    threshold = _load_risk_threshold(root)
    report = _load_report(root, manifest)
    breadth_count = int((report["価格"] > report["MA25"]).sum())
    breadth_ratio = round(breadth_count / len(report), 6)
    legacy_bear = _legacy_bear_override(root)
    regime = _determine_regime(
        breadth_ratio=breadth_ratio,
        threshold=threshold,
        legacy_bear=legacy_bear,
    )

    return {
        "schema_version": 2,
        "generated_at": pd.Timestamp.now(tz="Asia/Tokyo").isoformat(),
        "source_run_id": _normalize_text(manifest.get("run_id")),
        "source_report_sha256": _normalize_text(manifest.get("report_sha256")),
        "source_ticker_count": int(manifest.get("ticker_count", 0)),
        "breadth_ratio": breadth_ratio,
        "breadth_threshold": threshold,
        "regime": regime,
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    payload = build_market_regime(root)
    output_path = resolve_path(root, OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(output_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(
        "Market Regime AI READY",
        f"regime={payload['regime']}",
        f"breadth_ratio={payload['breadth_ratio']:.6f}",
        f"threshold={payload['breadth_threshold']:.2f}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
