from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime
import json
import math
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

from phoenix_core.data_freshness import JST


REPORT_DIR = Path("reports")
DEFAULT_LEARNING_PROFILE_FILE = REPORT_DIR / "learning_profile.json"
DEFAULT_ADAPTIVE_PARAMETER_FILE = REPORT_DIR / "adaptive_parameter.json"

REPORT_REQUIRED_COLUMNS = {
    "銘柄",
    "ticker",
    "基準日",
    "価格",
    "前日比%",
    "出来高倍率",
    "MA5",
    "MA25",
    "MA75",
    "RSI",
    "MACD判定",
    "PHOENIX_SCORE",
    "理由",
}

REPORT_NUMERIC_COLUMNS = (
    "価格",
    "前日比%",
    "出来高倍率",
    "MA5",
    "MA25",
    "MA75",
    "RSI",
    "PHOENIX_SCORE",
)

JUDGEMENT_REQUIRED_COLUMNS = {
    "銘柄",
    "ticker",
    "価格",
    "前日比%",
    "出来高倍率",
    "RSI",
    "MACD判定",
    "PHOENIX_SCORE",
    "AI判断",
    "AI判断点",
}

ACTIVE_JUDGEMENTS = (
    "優先監視",
    "買い候補",
    "押し目待ち",
)

ALL_KNOWN_JUDGEMENTS = (
    "優先監視",
    "買い候補",
    "押し目待ち",
    "様子見",
    "見送り",
)

JUDGEMENT_ORDER = {
    "優先監視": 0,
    "買い候補": 1,
    "押し目待ち": 2,
    "様子見": 3,
    "見送り": 4,
}

SIGNAL_CHANGE_ORDER = {
    "new": 0,
    "upgraded": 1,
    "continued": 2,
    "downgraded": 3,
    "excluded": 4,
}

ADAPTIVE_SCALAR_FIELDS = (
    "decision",
    "action",
    "confidence",
    "reason",
)

ADAPTIVE_PARAMETER_REQUIRED_KEYS = (
    "rsi_min",
    "rsi_max",
    "stop_atr_multiplier",
    "target_r_multiplier",
    "ma_short",
    "ma_mid",
    "ma_long",
    "signal_score_threshold",
    "max_hold_days",
)


class ComparisonError(Exception):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


def _blocked(message: str) -> ComparisonError:
    return ComparisonError("BLOCKED", message)


def _error(message: str) -> ComparisonError:
    return ComparisonError("ERROR", message)


def _native_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            native = value.item()
            if isinstance(native, float) and not math.isfinite(native):
                return None
            return native
        except Exception:
            pass

    return value


def _format_date(value: date | datetime | str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    return str(value)


def _parse_report_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        raise _blocked("不正日付: 空です")

    if text.startswith("report_") and text.endswith(".csv"):
        text = text.removeprefix("report_").removesuffix(".csv")

    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    raise _blocked(f"不正日付: {value}")


def _read_csv_with_fallback(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise _blocked(f"日付ファイル不存在: {path}")

    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except FileNotFoundError as error:
            raise _blocked(f"日付ファイル不存在: {path}") from error
        except pd.errors.EmptyDataError as error:
            raise _blocked(f"空のCSVです: {path}") from error
        except Exception as error:
            last_error = error

    raise _blocked(f"CSVを読めません: {path}: {last_error}")


def _ensure_required_columns(
    df: pd.DataFrame,
    required_columns: set[str],
    *,
    context: str,
) -> None:
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        missing_text = ", ".join(sorted(missing_columns))
        raise _blocked(f"{context}に必要な列がありません: {missing_text}")


def _normalize_report_dataframe(df: pd.DataFrame, *, context: str) -> tuple[pd.DataFrame, date]:
    if df.empty:
        raise _blocked(f"{context}のCSVが空です")

    _ensure_required_columns(df, REPORT_REQUIRED_COLUMNS, context=context)

    normalized = df.copy()
    for column in ("銘柄", "ticker", "基準日", "MACD判定", "理由"):
        normalized[column] = normalized[column].astype(str).str.strip()

    if normalized["銘柄"].eq("").any():
        raise _blocked(f"{context}に空の銘柄名があります")

    if normalized["ticker"].eq("").any():
        raise _blocked(f"{context}に空のtickerがあります")

    normalized["ticker"] = normalized["ticker"].astype(str).str.strip()
    duplicate_mask = normalized["ticker"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicates = ", ".join(sorted(normalized.loc[duplicate_mask, "ticker"].astype(str).unique()))
        raise _blocked(f"{context}に重複tickerがあります: {duplicates}")

    basis_dates = sorted(set(normalized["基準日"].astype(str)))
    if len(basis_dates) != 1:
        raise _blocked(f"{context}の基準日が一意ではありません: {', '.join(basis_dates)}")

    try:
        basis_date = _parse_report_date(basis_dates[0])
    except ComparisonError:
        raise
    except Exception as error:
        raise _blocked(f"{context}の基準日が不正です: {basis_dates[0]}") from error

    for column in REPORT_NUMERIC_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        if normalized[column].isna().any():
            raise _blocked(f"{context}に不正数値があります: {column}")
        if not normalized[column].map(lambda value: math.isfinite(float(value))).all():
            raise _blocked(f"{context}に不正数値があります: {column}")

    normalized["MACD判定"] = normalized["MACD判定"].astype(str).str.strip().str.upper()
    if normalized["MACD判定"].eq("").any():
        raise _blocked(f"{context}に空のMACD判定があります")

    return normalized.reset_index(drop=True), basis_date


def _read_learning_profile(path: Path | None) -> dict[str, Any]:
    if path is None:
        path = DEFAULT_LEARNING_PROFILE_FILE

    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _read_adaptive_snapshot(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise _blocked(f"Adaptive Parameterファイルがありません: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise _blocked(f"Adaptive Parameterファイルを読めません: {path}") from error

    if not isinstance(data, dict):
        raise _blocked(f"Adaptive Parameterファイルの形式が不正です: {path}")

    for field in ("version", "generated_at", "decision", "action", "confidence", "reason", "active_parameters"):
        if field not in data:
            raise _blocked(f"Adaptive Parameterファイルに必要な項目がありません: {field}")

    active_parameters = data.get("active_parameters")
    if not isinstance(active_parameters, dict):
        raise _blocked("Adaptive Parameterのactive_parametersが不正です")

    normalized_parameters: dict[str, Any] = {}
    for key in ADAPTIVE_PARAMETER_REQUIRED_KEYS:
        if key not in active_parameters:
            raise _blocked(f"Adaptive Parameterに必要な項目がありません: {key}")
        normalized_parameters[key] = _native_value(active_parameters[key])
        if normalized_parameters[key] is None:
            raise _blocked(f"Adaptive Parameterに不正数値があります: {key}")
        try:
            numeric_value = float(normalized_parameters[key])
        except (TypeError, ValueError) as error:
            raise _blocked(f"Adaptive Parameterに不正数値があります: {key}") from error
        if not math.isfinite(numeric_value):
            raise _blocked(f"Adaptive Parameterに不正数値があります: {key}")
        if numeric_value.is_integer():
            normalized_parameters[key] = int(numeric_value)
        else:
            normalized_parameters[key] = numeric_value

    return {
        "path": str(path),
        "version": str(data["version"]),
        "generated_at": str(data["generated_at"]),
        "decision": str(data["decision"]),
        "action": str(data["action"]),
        "confidence": float(data["confidence"]),
        "reason": str(data["reason"]),
        "active_parameters": normalized_parameters,
        "candidate_parameters": _native_value(data.get("candidate_parameters")),
    }


def _extract_optimized_tickers(report_df: pd.DataFrame) -> set[str]:
    try:
        from daily_report import extract_optimized_signals as _extract
    except Exception:
        _extract = None

    if _extract is None:
        return _extract_optimized_tickers_fallback(report_df)

    try:
        optimized_df = _extract(report_df.copy())
    except Exception as error:
        raise _blocked(f"最適シグナル抽出に失敗しました: {error}") from error

    if optimized_df.empty or "ticker" not in optimized_df.columns:
        return set()

    return set(optimized_df["ticker"].astype(str).str.strip())


def _extract_optimized_tickers_fallback(report_df: pd.DataFrame) -> set[str]:
    required_columns = {
        "銘柄",
        "ticker",
        "基準日",
        "価格",
        "前日比%",
        "出来高倍率",
        "MA5",
        "MA25",
        "MA75",
        "RSI",
        "MACD判定",
        "PHOENIX_SCORE",
        "理由",
    }
    _ensure_required_columns(report_df, required_columns, context="report")
    filtered = report_df[
        (
            report_df["PHOENIX_SCORE"] >= 55
        )
        & (
            report_df["RSI"] >= 30
        )
        & (
            report_df["RSI"] <= 75
        )
        & (
            report_df["出来高倍率"] >= 2.0
        )
        & (
            report_df["MACD判定"].astype(str).str.upper().str.strip() == "SELL"
        )
    ].copy()
    if filtered.empty:
        return set()
    return set(filtered["ticker"].astype(str).str.strip())


def _create_judgements(
    report_df: pd.DataFrame,
    optimized_tickers: set[str],
    learning_profile: dict[str, Any],
) -> pd.DataFrame:
    try:
        from ai_judgement import create_judgements
    except Exception as error:
        raise _error(f"ai_judgementの読み込みに失敗しました: {error}") from error

    try:
        return create_judgements(
            report_df.copy(),
            optimized_tickers,
            learning_profile,
        )
    except Exception as error:
        raise _blocked(f"AI判断の生成に失敗しました: {error}") from error


def _normalize_judgement_dataframe(df: pd.DataFrame, *, context: str) -> pd.DataFrame:
    if df.empty:
        raise _blocked(f"{context}のAI判断が空です")

    _ensure_required_columns(df, JUDGEMENT_REQUIRED_COLUMNS, context=context)

    normalized = df.copy()
    normalized["ticker"] = normalized["ticker"].astype(str).str.strip()
    normalized["銘柄"] = normalized["銘柄"].astype(str).str.strip()
    normalized["AI判断"] = normalized["AI判断"].astype(str).str.strip()
    normalized["MACD判定"] = normalized["MACD判定"].astype(str).str.strip().str.upper()

    duplicate_mask = normalized["ticker"].duplicated(keep=False)
    if duplicate_mask.any():
        duplicates = ", ".join(sorted(normalized.loc[duplicate_mask, "ticker"].astype(str).unique()))
        raise _blocked(f"{context}に重複tickerがあります: {duplicates}")

    unknown_labels = sorted(
        set(normalized["AI判断"].astype(str)) - set(ALL_KNOWN_JUDGEMENTS)
    )
    if unknown_labels:
        raise _blocked(f"{context}に未知のAI判断があります: {', '.join(unknown_labels)}")

    for column in ("価格", "前日比%", "出来高倍率", "RSI", "PHOENIX_SCORE", "AI判断点"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        if normalized[column].isna().any():
            raise _blocked(f"{context}に不正数値があります: {column}")
        if not normalized[column].map(lambda value: math.isfinite(float(value))).all():
            raise _blocked(f"{context}に不正数値があります: {column}")

    return normalized.reset_index(drop=True)


def _build_snapshot(
    report_date: date,
    *,
    report_dir: Path,
    learning_profile_path: Path | None,
) -> dict[str, Any]:
    report_path = report_dir / f"report_{report_date:%Y%m%d}.csv"
    report_df, basis_date = _normalize_report_dataframe(
        _read_csv_with_fallback(report_path),
        context=f"report_{report_date:%Y%m%d}",
    )
    optimized_tickers = _extract_optimized_tickers(report_df)
    learning_profile = _read_learning_profile(learning_profile_path)
    judgement_df = _normalize_judgement_dataframe(
        _create_judgements(report_df, optimized_tickers, learning_profile),
        context=f"AI判断_{report_date:%Y%m%d}",
    )

    report_tickers = set(report_df["ticker"].astype(str))
    judgement_tickers = set(judgement_df["ticker"].astype(str))
    if report_tickers != judgement_tickers:
        missing_in_judgement = sorted(report_tickers - judgement_tickers)
        missing_in_report = sorted(judgement_tickers - report_tickers)
        details = []
        if missing_in_judgement:
            details.append(f"AI判断に存在しないticker: {', '.join(missing_in_judgement)}")
        if missing_in_report:
            details.append(f"reportに存在しないticker: {', '.join(missing_in_report)}")
        raise _blocked("; ".join(details))

    all_counts = Counter(judgement_df["AI判断"].astype(str))
    active_df = judgement_df[judgement_df["AI判断"].isin(ACTIVE_JUDGEMENTS)].copy()
    active_counts = Counter(active_df["AI判断"].astype(str))
    active_tickers = set(active_df["ticker"].astype(str))

    return {
        "report_date": report_date.isoformat(),
        "report_file": report_path.name,
        "report_path": str(report_path),
        "basis_date": basis_date.isoformat(),
        "report_df": report_df,
        "judgement_df": judgement_df,
        "optimized_tickers": optimized_tickers,
        "optimized_signal_count": int(len(optimized_tickers)),
        "all_counts": {label: int(all_counts.get(label, 0)) for label in ALL_KNOWN_JUDGEMENTS},
        "active_counts": {label: int(active_counts.get(label, 0)) for label in ACTIVE_JUDGEMENTS},
        "active_total": int(sum(active_counts.values())),
        "active_tickers": active_tickers,
        "learning_profile_path": str(learning_profile_path or DEFAULT_LEARNING_PROFILE_FILE),
        "learning_profile_generated_at": _native_value(learning_profile.get("generated_at")) if isinstance(learning_profile, dict) else None,
    }


def _format_signed_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "-"

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)

    sign = "+" if numeric >= 0 else ""
    return f"{sign}{numeric:.{decimals}f}"


def _format_plain_number(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "-"

    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_count_line(label: str, counts: dict[str, int]) -> str:
    return (
        f"{label}: "
        f"優先監視 {counts.get('優先監視', 0)} / "
        f"買い候補 {counts.get('買い候補', 0)} / "
        f"押し目待ち {counts.get('押し目待ち', 0)} / "
        f"様子見 {counts.get('様子見', 0)} / "
        f"見送り {counts.get('見送り', 0)}"
    )


def _build_signal_row(
    ticker: str,
    *,
    source_snapshot: dict[str, Any],
    target_snapshot: dict[str, Any],
) -> dict[str, Any]:
    source_report = source_snapshot["report_df"].set_index("ticker")
    target_report = target_snapshot["report_df"].set_index("ticker")
    source_judgement = source_snapshot["judgement_df"].set_index("ticker")
    target_judgement = target_snapshot["judgement_df"].set_index("ticker")

    source_row = source_report.loc[ticker]
    target_row = target_report.loc[ticker]
    source_judge_row = source_judgement.loc[ticker]
    target_judge_row = target_judgement.loc[ticker]

    source_label = str(source_judge_row["AI判断"])
    target_label = str(target_judge_row["AI判断"])
    source_rank = JUDGEMENT_ORDER.get(source_label, 99)
    target_rank = JUDGEMENT_ORDER.get(target_label, 99)
    source_active = source_label in ACTIVE_JUDGEMENTS
    target_active = target_label in ACTIVE_JUDGEMENTS

    if source_active and target_active:
        if source_rank == target_rank:
            change_type = "continued"
        elif target_rank < source_rank:
            change_type = "upgraded"
        else:
            change_type = "downgraded"
    elif target_active:
        change_type = "new"
    elif source_active:
        change_type = "excluded"
    else:
        change_type = "inactive"

    metric_row = {
        "row_type": "ticker",
        "ticker": ticker,
        "source_name": _native_value(source_row["銘柄"]),
        "target_name": _native_value(target_row["銘柄"]),
        "source_report_date": source_snapshot["report_date"],
        "target_report_date": target_snapshot["report_date"],
        "source_basis_date": source_snapshot["basis_date"],
        "target_basis_date": target_snapshot["basis_date"],
        "source_judgement": source_label,
        "target_judgement": target_label,
        "source_judgement_rank": int(source_rank),
        "target_judgement_rank": int(target_rank),
        "rank_delta": int(target_rank - source_rank),
        "change_type": change_type,
        "source_active": bool(source_active),
        "target_active": bool(target_active),
        "source_price": _native_value(source_row["価格"]),
        "target_price": _native_value(target_row["価格"]),
        "price_delta": _native_value(target_row["価格"] - source_row["価格"]),
        "source_ai_points": _native_value(source_judge_row["AI判断点"]),
        "target_ai_points": _native_value(target_judge_row["AI判断点"]),
        "ai_points_delta": _native_value(target_judge_row["AI判断点"] - source_judge_row["AI判断点"]),
        "source_phoenix_score": _native_value(source_row["PHOENIX_SCORE"]),
        "target_phoenix_score": _native_value(target_row["PHOENIX_SCORE"]),
        "phoenix_score_delta": _native_value(target_row["PHOENIX_SCORE"] - source_row["PHOENIX_SCORE"]),
        "source_volume_ratio": _native_value(source_row["出来高倍率"]),
        "target_volume_ratio": _native_value(target_row["出来高倍率"]),
        "volume_ratio_delta": _native_value(target_row["出来高倍率"] - source_row["出来高倍率"]),
        "source_rsi": _native_value(source_row["RSI"]),
        "target_rsi": _native_value(target_row["RSI"]),
        "rsi_delta": _native_value(target_row["RSI"] - source_row["RSI"]),
        "source_macd": _native_value(source_row["MACD判定"]),
        "target_macd": _native_value(target_row["MACD判定"]),
        "macd_change": f"{_native_value(source_row['MACD判定'])} -> {_native_value(target_row['MACD判定'])}",
    }

    return metric_row


def _compare_signal_snapshots(
    source_snapshot: dict[str, Any],
    target_snapshot: dict[str, Any],
) -> dict[str, Any]:
    source_union = set(source_snapshot["active_tickers"])
    target_union = set(target_snapshot["active_tickers"])
    signal_tickers = sorted(source_union | target_union)

    common_rows: list[dict[str, Any]] = []
    grouped_rows = {
        "new": [],
        "continued": [],
        "upgraded": [],
        "downgraded": [],
        "excluded": [],
    }

    for ticker in signal_tickers:
        row = _build_signal_row(
            ticker,
            source_snapshot=source_snapshot,
            target_snapshot=target_snapshot,
        )
        if row["change_type"] == "inactive":
            continue
        common_rows.append(row)
        grouped_rows[row["change_type"]].append(row)

    def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
        sort_rank = row["target_judgement_rank"]
        if row["change_type"] == "excluded":
            sort_rank = row["source_judgement_rank"]
        return (
            SIGNAL_CHANGE_ORDER.get(row["change_type"], 99),
            sort_rank,
            row["ticker"],
        )

    common_rows.sort(key=sort_key)
    for rows in grouped_rows.values():
        rows.sort(key=sort_key)

    summary = {
        "source": {
            "report_date": source_snapshot["report_date"],
            "basis_date": source_snapshot["basis_date"],
            "report_file": source_snapshot["report_file"],
            "all_counts": source_snapshot["all_counts"],
            "active_counts": source_snapshot["active_counts"],
            "active_total": source_snapshot["active_total"],
            "optimized_signal_count": source_snapshot["optimized_signal_count"],
            "learning_profile_path": source_snapshot["learning_profile_path"],
            "learning_profile_generated_at": source_snapshot["learning_profile_generated_at"],
        },
        "target": {
            "report_date": target_snapshot["report_date"],
            "basis_date": target_snapshot["basis_date"],
            "report_file": target_snapshot["report_file"],
            "all_counts": target_snapshot["all_counts"],
            "active_counts": target_snapshot["active_counts"],
            "active_total": target_snapshot["active_total"],
            "optimized_signal_count": target_snapshot["optimized_signal_count"],
            "learning_profile_path": target_snapshot["learning_profile_path"],
            "learning_profile_generated_at": target_snapshot["learning_profile_generated_at"],
        },
    }

    signal_change_counts = {key: len(value) for key, value in grouped_rows.items()}

    return {
        "summary": summary,
        "signal_change_counts": signal_change_counts,
        "signal_changes": grouped_rows,
        "common_ticker_changes": common_rows,
    }


def _compare_adaptive_snapshots(
    source_snapshot: dict[str, Any],
    target_snapshot: dict[str, Any],
) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []

    def add_change(field: str, source_value: Any, target_value: Any) -> None:
        if source_value == target_value:
            return
        delta: Any = None
        if isinstance(source_value, (int, float)) and isinstance(target_value, (int, float)):
            delta = target_value - source_value
        changes.append(
            {
                "field": field,
                "source_value": _native_value(source_value),
                "target_value": _native_value(target_value),
                "delta": _native_value(delta),
            }
        )

    for field in ADAPTIVE_SCALAR_FIELDS:
        add_change(field, source_snapshot[field], target_snapshot[field])

    source_parameters = source_snapshot["active_parameters"]
    target_parameters = target_snapshot["active_parameters"]
    if set(source_parameters) != set(target_parameters):
        raise _blocked(
            "Adaptive Parameterの項目が一致しません: "
            + ", ".join(sorted(set(source_parameters) ^ set(target_parameters)))
        )

    for key in sorted(source_parameters):
        add_change(
            key,
            source_parameters[key],
            target_parameters[key],
        )

    return {
        "source": {
            "path": source_snapshot["path"],
            "version": source_snapshot["version"],
            "generated_at": source_snapshot["generated_at"],
            "decision": source_snapshot["decision"],
            "action": source_snapshot["action"],
            "confidence": source_snapshot["confidence"],
            "reason": source_snapshot["reason"],
            "active_parameters": source_parameters,
        },
        "target": {
            "path": target_snapshot["path"],
            "version": target_snapshot["version"],
            "generated_at": target_snapshot["generated_at"],
            "decision": target_snapshot["decision"],
            "action": target_snapshot["action"],
            "confidence": target_snapshot["confidence"],
            "reason": target_snapshot["reason"],
            "active_parameters": target_parameters,
        },
        "changes": changes,
    }


def compare_weekly_signals(
    source_date: str | date | datetime,
    target_date: str | date | datetime,
    *,
    report_dir: Path | str = REPORT_DIR,
    learning_profile_path: Path | str | None = None,
    source_adaptive_parameter_path: Path | str | None = None,
    target_adaptive_parameter_path: Path | str | None = None,
) -> dict[str, Any]:
    source_report_date = _parse_report_date(source_date)
    target_report_date = _parse_report_date(target_date)

    if source_report_date == target_report_date:
        raise _blocked("同一日付比較はできません")

    report_dir = Path(report_dir)
    source_snapshot = _build_snapshot(
        source_report_date,
        report_dir=report_dir,
        learning_profile_path=Path(learning_profile_path) if learning_profile_path is not None else None,
    )
    target_snapshot = _build_snapshot(
        target_report_date,
        report_dir=report_dir,
        learning_profile_path=Path(learning_profile_path) if learning_profile_path is not None else None,
    )

    if source_adaptive_parameter_path is None:
        source_adaptive_parameter_path = DEFAULT_ADAPTIVE_PARAMETER_FILE
    if target_adaptive_parameter_path is None:
        target_adaptive_parameter_path = DEFAULT_ADAPTIVE_PARAMETER_FILE

    adaptive_comparison = _compare_adaptive_snapshots(
        _read_adaptive_snapshot(Path(source_adaptive_parameter_path)),
        _read_adaptive_snapshot(Path(target_adaptive_parameter_path)),
    )

    signal_comparison = _compare_signal_snapshots(source_snapshot, target_snapshot)

    return {
        "status": "READY",
        "generated_at": datetime.now(JST).isoformat(),
        "comparison_type": "Weekly Signal Comparison",
        "ticker_key": "ticker",
        "source": signal_comparison["summary"]["source"],
        "target": signal_comparison["summary"]["target"],
        "signal_change_counts": signal_comparison["signal_change_counts"],
        "signal_changes": signal_comparison["signal_changes"],
        "common_ticker_changes": signal_comparison["common_ticker_changes"],
        "adaptive_parameter": adaptive_comparison,
        "safety": {
            "broker_mode": "PAPER",
            "orders_submitted": 0,
            "external_connections": False,
            "broker_state_changed": False,
            "portfolio_state_changed": False,
            "position_state_changed": False,
            "notification_sent": 0,
        },
        "disclaimer": "売買推奨ではありません。",
    }


def _list_report_dates(report_dir: Path | str) -> list[date]:
    report_dir = Path(report_dir)
    if not report_dir.is_dir():
        return []

    report_dates: set[date] = set()
    for report_path in report_dir.glob("report_*.csv"):
        if not report_path.is_file():
            continue
        try:
            report_dates.add(_parse_report_date(report_path.name))
        except ComparisonError:
            continue

    return sorted(report_dates)


def find_latest_comparable_report_date(
    target_date: str | date | datetime,
    *,
    report_dir: Path | str = REPORT_DIR,
) -> date | None:
    target_report_date = _parse_report_date(target_date)
    candidate_dates = [
        report_date
        for report_date in _list_report_dates(report_dir)
        if report_date < target_report_date
    ]
    if not candidate_dates:
        return None
    return max(candidate_dates)


def run_latest_weekly_signal_comparison(
    target_date: str | date | datetime,
    *,
    report_dir: Path | str = REPORT_DIR,
    output_dir: Path | str = REPORT_DIR,
    learning_profile_path: Path | str | None = None,
    source_adaptive_parameter_path: Path | str | None = None,
    target_adaptive_parameter_path: Path | str | None = None,
) -> dict[str, Any]:
    target_report_date = _parse_report_date(target_date)
    source_report_date = find_latest_comparable_report_date(
        target_report_date,
        report_dir=report_dir,
    )

    target_report_file = f"report_{target_report_date:%Y%m%d}.csv"
    if source_report_date is None:
        return {
            "status": "SKIPPED",
            "generated_at": datetime.now(JST).isoformat(),
            "comparison_type": "Weekly Signal Comparison",
            "ticker_key": "ticker",
            "selection": {
                "source_report_date": None,
                "target_report_date": target_report_date.isoformat(),
            },
            "target": {
                "report_date": target_report_date.isoformat(),
                "report_file": target_report_file,
            },
            "reason": (
                "No comparable prior report exists before "
                f"{target_report_date.isoformat()}"
            ),
            "safety": {
                "broker_mode": "PAPER",
                "orders_submitted": 0,
                "external_connections": False,
                "broker_state_changed": False,
                "portfolio_state_changed": False,
                "position_state_changed": False,
                "notification_sent": 0,
            },
        }

    result = compare_weekly_signals(
        source_report_date,
        target_report_date,
        report_dir=report_dir,
        learning_profile_path=learning_profile_path,
        source_adaptive_parameter_path=source_adaptive_parameter_path,
        target_adaptive_parameter_path=target_adaptive_parameter_path,
    )
    paths = save_weekly_signal_comparison(result, output_dir=output_dir)

    return {
        **result,
        "selection": {
            "source_report_date": source_report_date.isoformat(),
            "target_report_date": target_report_date.isoformat(),
        },
        "paths": {name: str(path) for name, path in paths.items()},
    }


def _build_csv_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def append_summary_rows(section: str, counts: dict[str, int]) -> None:
        for name, value in counts.items():
            rows.append(
                {
                    "row_type": "summary",
                    "section": section,
                    "name": name,
                    "ticker": "",
                    "source_value": value,
                    "target_value": "",
                    "delta": "",
                }
            )

    append_summary_rows("source_active_counts", result["source"]["active_counts"])
    append_summary_rows("target_active_counts", result["target"]["active_counts"])
    for name, value in result["signal_change_counts"].items():
        rows.append(
            {
                "row_type": "summary",
                "section": "signal_change_counts",
                "name": name,
                "ticker": "",
                "source_value": value,
                "target_value": "",
                "delta": "",
            }
        )

    for row in result["common_ticker_changes"]:
        csv_row = {
            "row_type": "ticker",
            "section": "common_ticker_changes",
        }
        csv_row.update(row)
        rows.append(csv_row)

    for change in result["adaptive_parameter"]["changes"]:
        rows.append(
            {
                "row_type": "adaptive_parameter",
                "section": "adaptive_parameter",
                "name": change["field"],
                "ticker": "",
                "source_value": change["source_value"],
                "target_value": change["target_value"],
                "delta": change["delta"],
            }
        )

    return rows


def _atomic_temp_path(path: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=path.parent,
        prefix=f"{path.stem}_",
        suffix=f"{path.suffix}.tmp",
    ) as temp_file:
        return Path(temp_file.name)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _atomic_temp_path(path)
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"
    _write_text_atomic(path, content)


def _write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = _atomic_temp_path(path)
    try:
        df = pd.DataFrame(rows)
        df.to_csv(temp_path, index=False, encoding="utf-8-sig")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def build_text_report(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("PHOENIX WEEKLY SIGNAL COMPARISON")
    lines.append(f"生成日時: {result['generated_at']}")
    lines.append("")
    lines.append("比較概要")
    lines.append(
        f"比較元: {result['source']['report_file']} / report日付 {result['source']['report_date']} / 基準日 {result['source']['basis_date']}"
    )
    lines.append(
        f"比較先: {result['target']['report_file']} / report日付 {result['target']['report_date']} / 基準日 {result['target']['basis_date']}"
    )
    lines.append(f"ticker主キー: {result['ticker_key']}")
    lines.append("")
    lines.append("現在通知数")
    lines.append(_format_count_line("比較元", result["source"]["active_counts"]))
    lines.append(_format_count_line("比較先", result["target"]["active_counts"]))
    lines.append("")
    lines.append("新規候補")
    if result["signal_changes"]["new"]:
        for row in result["signal_changes"]["new"]:
            lines.append(
                f"- {row['ticker']} {row['target_name']} | {row['source_judgement']} -> {row['target_judgement']} | "
                f"価格 {_format_plain_number(row['source_price'])} -> {_format_plain_number(row['target_price'])} ({_format_signed_number(row['price_delta'])}) | "
                f"AI {_format_plain_number(row['source_ai_points'], 0)} -> {_format_plain_number(row['target_ai_points'], 0)} ({_format_signed_number(row['ai_points_delta'], 0)})"
            )
    else:
        lines.append("- なし")
    lines.append("")
    lines.append("継続候補")
    if result["signal_changes"]["continued"]:
        for row in result["signal_changes"]["continued"]:
            lines.append(
                f"- {row['ticker']} {row['target_name']} | {row['source_judgement']} -> {row['target_judgement']} | "
                f"価格 {_format_plain_number(row['source_price'])} -> {_format_plain_number(row['target_price'])} ({_format_signed_number(row['price_delta'])}) | "
                f"AI {_format_plain_number(row['source_ai_points'], 0)} -> {_format_plain_number(row['target_ai_points'], 0)} ({_format_signed_number(row['ai_points_delta'], 0)})"
            )
    else:
        lines.append("- なし")
    lines.append("")
    lines.append("格上げ")
    if result["signal_changes"]["upgraded"]:
        for row in result["signal_changes"]["upgraded"]:
            lines.append(
                f"- {row['ticker']} {row['target_name']} | {row['source_judgement']} -> {row['target_judgement']} | "
                f"AI {_format_plain_number(row['source_ai_points'], 0)} -> {_format_plain_number(row['target_ai_points'], 0)} ({_format_signed_number(row['ai_points_delta'], 0)})"
            )
    else:
        lines.append("- なし")
    lines.append("")
    lines.append("格下げ")
    if result["signal_changes"]["downgraded"]:
        for row in result["signal_changes"]["downgraded"]:
            lines.append(
                f"- {row['ticker']} {row['target_name']} | {row['source_judgement']} -> {row['target_judgement']} | "
                f"AI {_format_plain_number(row['source_ai_points'], 0)} -> {_format_plain_number(row['target_ai_points'], 0)} ({_format_signed_number(row['ai_points_delta'], 0)})"
            )
    else:
        lines.append("- なし")
    lines.append("")
    lines.append("除外候補")
    if result["signal_changes"]["excluded"]:
        for row in result["signal_changes"]["excluded"]:
            lines.append(
                f"- {row['ticker']} {row['target_name']} | {row['source_judgement']} -> {row['target_judgement']} | "
                f"AI {_format_plain_number(row['source_ai_points'], 0)} -> {_format_plain_number(row['target_ai_points'], 0)} ({_format_signed_number(row['ai_points_delta'], 0)})"
            )
    else:
        lines.append("- なし")
    lines.append("")
    lines.append("共通銘柄の変化")
    header = "ticker | name | change | price | AI | PHOENIX | volume | RSI | MACD"
    lines.append(header)
    lines.append("-" * len(header))
    for row in result["common_ticker_changes"]:
        lines.append(
            f"{row['ticker']} | {row['target_name']} | {row['change_type']} | "
            f"{_format_plain_number(row['source_price'])} -> {_format_plain_number(row['target_price'])} ({_format_signed_number(row['price_delta'])}) | "
            f"{_format_plain_number(row['source_ai_points'], 0)} -> {_format_plain_number(row['target_ai_points'], 0)} ({_format_signed_number(row['ai_points_delta'], 0)}) | "
            f"{_format_plain_number(row['source_phoenix_score'], 0)} -> {_format_plain_number(row['target_phoenix_score'], 0)} ({_format_signed_number(row['phoenix_score_delta'], 0)}) | "
            f"{_format_plain_number(row['source_volume_ratio'])} -> {_format_plain_number(row['target_volume_ratio'])} ({_format_signed_number(row['volume_ratio_delta'])}) | "
            f"{_format_plain_number(row['source_rsi'])} -> {_format_plain_number(row['target_rsi'])} ({_format_signed_number(row['rsi_delta'])}) | "
            f"{row['macd_change']}"
        )
    lines.append("")
    lines.append("Adaptive Parameterの変化")
    lines.append(
        f"比較元: {result['adaptive_parameter']['source']['generated_at']} / {result['adaptive_parameter']['source']['decision']} / {result['adaptive_parameter']['source']['action']} / {result['adaptive_parameter']['source']['confidence']:.2f}%"
    )
    lines.append(
        f"比較先: {result['adaptive_parameter']['target']['generated_at']} / {result['adaptive_parameter']['target']['decision']} / {result['adaptive_parameter']['target']['action']} / {result['adaptive_parameter']['target']['confidence']:.2f}%"
    )
    if result["adaptive_parameter"]["changes"]:
        for change in result["adaptive_parameter"]["changes"]:
            lines.append(
                f"- {change['field']}: {change['source_value']} -> {change['target_value']} ({_format_signed_number(change['delta'])})"
            )
    else:
        lines.append("- 変更なし")
    lines.append("")
    lines.append("安全条件")
    lines.append(
        "PAPER固定 / Orders submitted: 0 / 実注文なし / broker・portfolio・position state変更なし / 外部接続なし / 通知送信なし"
    )
    lines.append("")
    lines.append(f"注意: {result['disclaimer']}")
    return "\n".join(lines) + "\n"


def save_weekly_signal_comparison(
    result: dict[str, Any],
    *,
    output_dir: Path | str = REPORT_DIR,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        "weekly_signal_comparison_"
        f"{result['source']['report_date'].replace('-', '')}_"
        f"{result['target']['report_date'].replace('-', '')}"
    )

    json_path = output_dir / f"{stem}.json"
    txt_path = output_dir / f"{stem}.txt"
    csv_path = output_dir / f"{stem}.csv"

    _write_json_atomic(json_path, result)
    _write_text_atomic(txt_path, build_text_report(result))
    _write_csv_atomic(csv_path, _build_csv_rows(result))

    return {
        "json": json_path,
        "txt": txt_path,
        "csv": csv_path,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PHOENIX weekly signal comparison")
    parser.add_argument("--source-date", required=True, help="比較元の日付 (YYYY-MM-DD or YYYYMMDD)")
    parser.add_argument("--target-date", required=True, help="比較先の日付 (YYYY-MM-DD or YYYYMMDD)")
    parser.add_argument("--report-dir", default=str(REPORT_DIR), help="report_YYYYMMDD.csv の保存先")
    parser.add_argument("--learning-profile", default=str(DEFAULT_LEARNING_PROFILE_FILE), help="learning_profile.json の保存先")
    parser.add_argument("--source-adaptive-parameter", default=str(DEFAULT_ADAPTIVE_PARAMETER_FILE), help="比較元の adaptive_parameter.json")
    parser.add_argument("--target-adaptive-parameter", default=str(DEFAULT_ADAPTIVE_PARAMETER_FILE), help="比較先の adaptive_parameter.json")
    parser.add_argument("--output-dir", default=str(REPORT_DIR), help="出力先ディレクトリ")

    args = parser.parse_args(argv)

    try:
        result = compare_weekly_signals(
            args.source_date,
            args.target_date,
            report_dir=Path(args.report_dir),
            learning_profile_path=Path(args.learning_profile) if args.learning_profile else None,
            source_adaptive_parameter_path=Path(args.source_adaptive_parameter) if args.source_adaptive_parameter else None,
            target_adaptive_parameter_path=Path(args.target_adaptive_parameter) if args.target_adaptive_parameter else None,
        )
        paths = save_weekly_signal_comparison(result, output_dir=Path(args.output_dir))
        print(build_text_report(result), end="")
        print(f"JSON: {paths['json']}")
        print(f"TXT: {paths['txt']}")
        print(f"CSV: {paths['csv']}")
        return 0
    except ComparisonError as error:
        print(f"{error.status}: {error}")
        return 1
    except Exception as error:
        print(f"ERROR: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
