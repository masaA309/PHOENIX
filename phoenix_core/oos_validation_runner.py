from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phoenix_core.historical_validation_20y import (  # type: ignore
    JST,
    _build_historical_validation_config,
    _load_universe_from_csv,
    _summarize_simulation_result,
    atomic_write,
    build_data_coverage,
    fetch_ticker_history,
    load_settings,
    prepare_histories,
    resolve_within,
    save_outputs,
    simulate_validation,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_CONFIG_PATH = Path("config/v7_historical_validation_risk_v2_quick.json")
DEFAULT_OUTPUT_DIR = Path("reports/oos_validation")
DEFAULT_REQUESTED_START = "2017-08-01"
DEFAULT_REQUESTED_END = "2026-08-14"
DEFAULT_AS_OF = datetime(2026, 8, 14, 16, 0, tzinfo=JST)
DEFAULT_INITIAL_CAPITAL_YEN = 500000
DEFAULT_FIXED_BREADTH_THRESHOLD = 0.40
DEFAULT_FIXED_BEAR_CAP = 0.70
DEFAULT_RUNS_DIR = "runs"
DEFAULT_PLAN_FILE = "dry_run.json"
DEFAULT_SUMMARY_FILE = "summary.json"
DEFAULT_REPORT_FILE = "report.txt"
DEFAULT_SUMMARY_CSV_FILE = "summary.csv"
DEFAULT_DRY_RUN_TEXT_FILE = "dry_run.txt"
DEFAULT_CONFIG_FILE = "config.json"
DEFAULT_MANIFEST_FILE = "manifest.json"
MANIFEST_SCHEMA_VERSION = 1
RUNNER_VERSION = "PHOENIX OOS Validation Risk v2"


class OOSValidationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OOSValidationRunSpec:
    name: str
    slug: str
    requested_start: str
    requested_end: str

    def to_manifest_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_text() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return float(default)
    if pd.isna(number):
        return float(default)
    return number


def _summarize_extra_metrics(result: Any, initial_equity: float) -> dict[str, Any]:
    trades = result.trades if isinstance(result.trades, pd.DataFrame) else pd.DataFrame()
    equity = result.equity_curve if isinstance(result.equity_curve, pd.DataFrame) else pd.DataFrame()

    if trades.empty or "profit_yen" not in trades.columns:
        expectancy_yen = 0.0
        expectancy_pct = 0.0
        max_consecutive_losses = 0
    else:
        profits = pd.to_numeric(trades["profit_yen"], errors="coerce").fillna(0.0).astype(float)
        returns = pd.to_numeric(trades.get("return_pct", pd.Series(dtype=float)), errors="coerce").fillna(0.0).astype(float)
        expectancy_yen = float(profits.mean()) if not profits.empty else 0.0
        expectancy_pct = float(returns.mean()) if not returns.empty else 0.0
        max_consecutive_losses = 0
        consecutive_losses = 0
        for profit in profits.tolist():
            if profit < 0:
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_losses = 0

    if equity.empty or "cash_yen" not in equity.columns:
        avg_cash_yen = float(initial_equity)
        avg_cash_pct = 1.0
        longest_underwater_sessions = 0
    else:
        cash_values = pd.to_numeric(equity["cash_yen"], errors="coerce").fillna(0.0).astype(float)
        equity_values = pd.to_numeric(equity.get("equity_yen", pd.Series(dtype=float)), errors="coerce").fillna(0.0).astype(float)
        avg_cash_yen = float(cash_values.mean()) if not cash_values.empty else float(initial_equity)
        if not equity_values.empty:
            safe_equity = equity_values.replace(0.0, np.nan)
            avg_cash_pct = float((cash_values / safe_equity).fillna(0.0).mean())
            running_max = equity_values.cummax()
            underwater = equity_values < (running_max - 1e-9)
            longest_underwater_sessions = 0
            current = 0
            for flag in underwater.tolist():
                if flag:
                    current += 1
                    longest_underwater_sessions = max(longest_underwater_sessions, current)
                else:
                    current = 0
        else:
            avg_cash_pct = 1.0
            longest_underwater_sessions = 0

    performance = _summarize_simulation_result(result, float(initial_equity))
    max_drawdown_yen = float(performance.get("max_drawdown_yen", 0.0))
    total_profit_yen = float(performance.get("total_profit_yen", 0.0))
    recovery_factor = total_profit_yen / max_drawdown_yen if max_drawdown_yen > 0 else 0.0

    return {
        "expectancy_per_trade_yen": round(expectancy_yen, 2),
        "expectancy_per_trade_pct": round(expectancy_pct, 6),
        "avg_cash_yen": round(avg_cash_yen, 2),
        "avg_cash_pct": round(avg_cash_pct, 6),
        "max_consecutive_losses": int(max_consecutive_losses),
        "longest_underwater_sessions": int(longest_underwater_sessions),
        "recovery_factor": round(recovery_factor, 6),
    }


def build_run_specs() -> tuple[OOSValidationRunSpec, ...]:
    return (
        OOSValidationRunSpec("OOS-1", "OOS_1", "2017-08-01", "2020-12-31"),
        OOSValidationRunSpec("OOS-2", "OOS_2", "2021-01-01", "2023-12-31"),
        OOSValidationRunSpec("OOS-3", "OOS_3", "2024-01-01", "2026-08-14"),
    )


def _base_settings(root: Path, base_config_path: Path) -> tuple[dict[str, Any], str]:
    settings = load_settings(root, base_config_path)
    if settings.get("allow_network_fetch", True):
        settings["allow_network_fetch"] = False
    config = _build_historical_validation_config(settings)
    config.validate()
    base_config_sha256 = _sha256_file(resolve_within(root, str(base_config_path)))
    return settings, base_config_sha256


def _run_dir(output_root: Path, run: OOSValidationRunSpec) -> Path:
    return output_root / DEFAULT_RUNS_DIR / run.slug


def _run_config_path(output_root: Path, run: OOSValidationRunSpec) -> Path:
    return _run_dir(output_root, run) / DEFAULT_CONFIG_FILE


def _run_summary_path(output_root: Path, run: OOSValidationRunSpec) -> Path:
    return _run_dir(output_root, run) / DEFAULT_SUMMARY_FILE


def _run_report_path(output_root: Path, run: OOSValidationRunSpec) -> Path:
    return _run_dir(output_root, run) / DEFAULT_REPORT_FILE


def _run_manifest_path(output_root: Path, run: OOSValidationRunSpec) -> Path:
    return _run_dir(output_root, run) / DEFAULT_MANIFEST_FILE


def _run_identity(
    base_config_sha256: str,
    run: OOSValidationRunSpec,
    settings: dict[str, Any],
) -> tuple[str, str]:
    payload = {
        "base_config_sha256": base_config_sha256,
        "run": run.to_manifest_dict(),
        "settings": {
            "requested_start": settings.get("requested_start"),
            "requested_end": settings.get("requested_end"),
            "allow_network_fetch": settings.get("allow_network_fetch"),
            "market_breadth_filter_enabled": settings.get("market_breadth_filter_enabled"),
            "market_breadth_bear_threshold": settings.get("market_breadth_bear_threshold"),
            "market_breadth_bear_max_total_invested_pct": settings.get("market_breadth_bear_max_total_invested_pct"),
            "slippage_rate": settings.get("slippage_rate"),
            "initial_capital_yen": settings.get("initial_capital_yen"),
            "output_dir": settings.get("output_dir"),
            "report_json": settings.get("report_json"),
            "report_text": settings.get("report_text"),
            "annual_returns_csv": settings.get("annual_returns_csv"),
            "monthly_returns_csv": settings.get("monthly_returns_csv"),
            "coverage_csv": settings.get("coverage_csv"),
            "data_coverage_csv": settings.get("data_coverage_csv"),
            "diagnostics_csv": settings.get("diagnostics_csv"),
            "trades_csv": settings.get("trades_csv"),
            "equity_curve_csv": settings.get("equity_curve_csv"),
        },
    }
    canonical = _canonical_json(payload)
    return _sha256_text(canonical), canonical


def _load_manifest(manifest_path: Path) -> dict[str, Any] | None:
    if not manifest_path.is_file():
        return None
    return _read_json(manifest_path)


def _can_resume_run(run: OOSValidationRunSpec, manifest_path: Path, summary_path: Path, expected_identity_sha256: str) -> bool:
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        return False
    if manifest.get("run_name") != run.name:
        return False
    if manifest.get("run_identity_sha256") != expected_identity_sha256:
        return False
    if manifest.get("status") != "DONE":
        return False
    return summary_path.is_file()


def _write_run_manifest(
    manifest_path: Path,
    *,
    run: OOSValidationRunSpec,
    base_config_path: Path,
    base_config_sha256: str,
    run_identity_sha256: str,
    status: str,
    resume_skipped: bool,
    output_files: dict[str, Any],
    error: str | None = None,
) -> None:
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "run_name": run.name,
        "run_slug": run.slug,
        "run": run.to_manifest_dict(),
        "base_config_file": _rel(ROOT, base_config_path),
        "base_config_sha256": base_config_sha256,
        "run_identity_sha256": run_identity_sha256,
        "status": status,
        "resume_skipped": resume_skipped,
        "output_files": output_files,
        "error": error,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, manifest)


def _prepare_context(
    root: Path,
    base_settings: dict[str, Any],
    runs: Iterable[OOSValidationRunSpec],
    as_of: datetime,
) -> dict[str, Any]:
    config = _build_historical_validation_config(base_settings)
    run_specs = tuple(runs)
    requested_start_ts = min(pd.Timestamp(run.requested_start).normalize() for run in run_specs)
    requested_end_ts = max(pd.Timestamp(run.requested_end).normalize() for run in run_specs)
    fetch_start_date = (requested_start_ts - pd.offsets.BDay(config.minimum_history_sessions + 20)).date()

    universe_csv = resolve_within(root, str(base_settings.get("universe_csv", "data/nikkei225_membership_20y.csv")))
    universe_df = _load_universe_from_csv(
        root,
        universe_csv,
        enforce_nikkei225=bool(base_settings.get("enforce_nikkei225", True)),
        expected_ticker_count=int(base_settings.get("expected_ticker_count", 225) or 225),
    )

    cache_dir = resolve_within(root, str(base_settings.get("cache_dir", "data/market_cache")))
    download_registry: set[tuple[str, Any, Any]] = set()
    fetched: list[tuple[dict[str, Any], Any]] = []
    for entry in universe_df.to_dict(orient="records"):
        outcome = fetch_ticker_history(
            root,
            entry["ticker"],
            fetch_start_date,
            requested_end_ts.date(),
            cache_dir=cache_dir,
            as_of=as_of,
            allow_network_fetch=False,
            download_registry=download_registry,
        )
        fetched.append((entry, outcome))

    histories = {entry["ticker"]: outcome.history for entry, outcome in fetched}
    prepared_histories = prepare_histories(histories, config)
    cache_tickers = {
        str(path.stem).replace("_", ".").strip().upper()
        for path in resolve_within(root, str(cache_dir)).rglob("*.csv")
    }
    membership_tickers = {str(ticker).strip().upper() for ticker in universe_df["ticker"].tolist()}
    return {
        "requested_start": requested_start_ts,
        "requested_end": requested_end_ts,
        "fetch_start_date": fetch_start_date,
        "universe_df": universe_df,
        "histories": histories,
        "prepared_histories": prepared_histories,
        "membership_ticker_count": int(len(universe_df)),
        "cache_csv_ticker_count": int(len(cache_tickers)),
        "simulation_ticker_count": int(sum(1 for frame in prepared_histories.values() if not frame.empty)),
        "excluded_cache_ticker_count": int(len(cache_tickers - membership_tickers)),
    }


def _fixed_run_settings(
    base_settings: dict[str, Any],
    run: OOSValidationRunSpec,
    run_dir: Path,
    base_slippage_rate: float,
) -> dict[str, Any]:
    settings = dict(base_settings)
    settings.update(
        {
            "requested_start": run.requested_start,
            "requested_end": run.requested_end,
            "allow_network_fetch": False,
            "initial_capital_yen": DEFAULT_INITIAL_CAPITAL_YEN,
            "market_breadth_filter_enabled": True,
            "market_breadth_bear_threshold": DEFAULT_FIXED_BREADTH_THRESHOLD,
            "market_breadth_bear_max_total_invested_pct": DEFAULT_FIXED_BEAR_CAP,
            "slippage_rate": base_slippage_rate,
            "output_dir": str(run_dir),
            "report_json": str(run_dir / DEFAULT_SUMMARY_FILE),
            "report_text": str(run_dir / DEFAULT_REPORT_FILE),
            "annual_returns_csv": str(run_dir / "annual_returns.csv"),
            "monthly_returns_csv": str(run_dir / "monthly_returns.csv"),
            "coverage_csv": str(run_dir / "data_coverage.csv"),
            "data_coverage_csv": str(run_dir / "data_coverage.csv"),
            "diagnostics_csv": str(run_dir / "diagnostics.csv"),
            "trades_csv": str(run_dir / "trades.csv"),
            "equity_curve_csv": str(run_dir / "equity_curve.csv"),
            "benchmark_enabled": bool(settings.get("benchmark_enabled", True)),
            "no_rss": True,
            "no_real_orders": True,
            "live_trading_enabled": False,
            "orders_submitted": 0,
        }
    )
    return settings


def _summarize_oos_performance(result: Any, initial_equity: float) -> dict[str, Any]:
    performance = _summarize_simulation_result(result, initial_equity)
    performance.update(_summarize_extra_metrics(result, initial_equity))
    performance["total_return"] = performance.get("total_return_pct", 0.0)
    performance["CAGR"] = performance.get("cagr_pct", 0.0)
    performance["max_drawdown"] = performance.get("max_drawdown_pct", 0.0)
    performance["expectancy_per_trade"] = performance.get("expectancy_per_trade_yen", 0.0)
    performance["longest_underwater"] = performance.get("longest_underwater_sessions", 0)
    return performance


def _build_run_report(
    *,
    run: OOSValidationRunSpec,
    base_config_path: Path,
    base_config_sha256: str,
    run_identity_sha256: str,
    run_settings: dict[str, Any],
    universe_df: pd.DataFrame,
    coverage_rows: list[dict[str, Any]],
    result: Any,
    performance: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    output_files = {
        "summary_json": run_settings["report_json"],
        "report_text": run_settings["report_text"],
        "annual_returns_csv": run_settings["annual_returns_csv"],
        "monthly_returns_csv": run_settings["monthly_returns_csv"],
        "data_coverage_csv": run_settings["data_coverage_csv"],
        "diagnostics_csv": run_settings["diagnostics_csv"],
        "trades_csv": run_settings["trades_csv"],
        "equity_curve_csv": run_settings["equity_curve_csv"],
    }
    if run_settings.get("market_breadth_filter_enabled", False) and not result.risk_v2_research.empty:
        output_files["risk_v2_research_csv"] = str(Path(run_settings["output_dir"]) / "risk_v2_research.csv")

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "run_name": run.name,
        "run_slug": run.slug,
        "run_kind": "simulation",
        "requested_start": str(run_settings["requested_start"]),
        "requested_end": str(run_settings["requested_end"]),
        "input_manifest_sha256": run_identity_sha256,
        "base_config_file": _rel(ROOT, base_config_path),
        "base_config_sha256": base_config_sha256,
        "initial_capital_yen": float(run_settings["initial_capital_yen"]),
        "lot_size": int(run_settings["lot_size"]),
        "fractional_shares": False,
        "ticker_count": int(len(universe_df)),
        "status": "SUCCESS",
        "actual_start_date": str(result.equity_curve["date"].iloc[0]) if not result.equity_curve.empty else "",
        "actual_end_date": str(result.equity_curve["date"].iloc[-1]) if not result.equity_curve.empty else "",
        "simulation_trading_days": int(len(result.equity_curve)),
        "rows": coverage_rows,
        "performance": performance,
        "warnings": [
            "Network fetch is disabled for OOS validation.",
            "Risk v2 parameters are fixed in the runner; the historical validation engine is unchanged.",
        ],
        "safety": {
            "no_rss": True,
            "no_real_orders": True,
            "orders_submitted": 0,
            "live_trading_enabled": False,
        },
        "prep": {
            "membership_ticker_count": context["membership_ticker_count"],
            "cache_csv_ticker_count": context["cache_csv_ticker_count"],
            "simulation_ticker_count": context["simulation_ticker_count"],
            "excluded_cache_ticker_count": context["excluded_cache_ticker_count"],
        },
        "validation": {
            "market_breadth_filter_enabled": bool(run_settings.get("market_breadth_filter_enabled", False)),
            "market_breadth_bear_threshold": run_settings.get("market_breadth_bear_threshold"),
            "market_breadth_bear_max_total_invested_pct": run_settings.get("market_breadth_bear_max_total_invested_pct"),
            "slippage_rate": run_settings.get("slippage_rate"),
        },
        "output_files": output_files,
    }


def _render_run_report(report: dict[str, Any]) -> str:
    performance = report.get("performance", {})
    validation = report.get("validation", {})
    prep = report.get("prep", {})
    output_files = report.get("output_files", {})
    lines = [
        "=" * 88,
        f"{report.get('version', RUNNER_VERSION)}",
        "=" * 88,
        f"Run              : {report.get('run_name', '')}",
        f"Run kind         : {report.get('run_kind', '')}",
        f"Requested period : {report.get('requested_start', '')} -> {report.get('requested_end', '')}",
        f"Base config      : {report.get('base_config_file', '')}",
        f"Market breadth   : {validation.get('market_breadth_filter_enabled', False)}",
        f"Breadth threshold: {validation.get('market_breadth_bear_threshold', '')}",
        f"BEAR cap         : {validation.get('market_breadth_bear_max_total_invested_pct', '')}",
        f"Slippage rate    : {validation.get('slippage_rate', '')}",
        f"Initial capital  : {report.get('initial_capital_yen', 0):,.0f} yen",
        "",
        "Performance",
        "-" * 88,
        f"Final equity     : {performance.get('final_equity_yen', 0):,.0f} yen",
        f"Total return     : {performance.get('total_return', performance.get('total_return_pct', 0)):+.2f}%",
        f"CAGR             : {performance.get('CAGR', performance.get('cagr_pct', 0)):+.2f}%",
        f"Profit factor    : {performance.get('profit_factor', 0):.3f}",
        f"Max drawdown     : {performance.get('max_drawdown', performance.get('max_drawdown_pct', 0)):.2f}%",
        f"Trades           : {performance.get('trade_count', 0)}",
        f"Win rate         : {performance.get('win_rate', performance.get('win_rate_pct', 0)):.2f}%",
        f"Expectancy/trade : {performance.get('expectancy_per_trade_yen', 0):,.2f} yen",
        f"Max consecutive losses: {performance.get('max_consecutive_losses', 0)}",
        f"Longest underwater     : {performance.get('longest_underwater_sessions', 0)} sessions",
        f"Recovery factor        : {performance.get('recovery_factor', 0):.6f}",
        f"Rejected lot     : {performance.get('rejected_due_to_lot', 0)}",
        f"Rejected buying  : {performance.get('rejected_due_to_buying_power', 0)}",
        "",
        "Preparation",
        "-" * 88,
        f"Membership tickers: {prep.get('membership_ticker_count', 0)}",
        f"Cache tickers     : {prep.get('cache_csv_ticker_count', 0)}",
        f"Prepared tickers   : {prep.get('simulation_ticker_count', 0)}",
        f"Excluded cache     : {prep.get('excluded_cache_ticker_count', 0)}",
        "",
        "Outputs",
        "-" * 88,
        f"Summary JSON      : {output_files.get('summary_json', '')}",
        f"Report text       : {output_files.get('report_text', '')}",
        f"Annual CSV        : {output_files.get('annual_returns_csv', '')}",
        f"Monthly CSV       : {output_files.get('monthly_returns_csv', '')}",
        f"Trades CSV        : {output_files.get('trades_csv', '')}",
        f"Equity CSV        : {output_files.get('equity_curve_csv', '')}",
        f"Coverage CSV      : {output_files.get('data_coverage_csv', '')}",
    ]
    if output_files.get("risk_v2_research_csv"):
        lines.append(f"Risk v2 research  : {output_files.get('risk_v2_research_csv', '')}")
    if report.get("error"):
        lines.extend(["", "Error", "-" * 88, str(report.get("error", ""))])
    lines.append("=" * 88)
    return "\n".join(lines) + "\n"


def _execute_run(
    *,
    root: Path,
    base_settings: dict[str, Any],
    base_config_path: Path,
    base_config_sha256: str,
    context: dict[str, Any],
    run: OOSValidationRunSpec,
    resume: bool,
) -> dict[str, Any]:
    run_dir = _run_dir(root / DEFAULT_OUTPUT_DIR, run)
    run_dir.mkdir(parents=True, exist_ok=True)
    run_settings = _fixed_run_settings(
        base_settings,
        run,
        run_dir,
        _safe_float(base_settings.get("slippage_rate", 0.0005), 0.0005),
    )
    run_config = _build_historical_validation_config(run_settings)
    run_config.validate()
    run_identity_sha256, _ = _run_identity(base_config_sha256, run, run_settings)
    config_path = _run_config_path(root / DEFAULT_OUTPUT_DIR, run)
    summary_path = _run_summary_path(root / DEFAULT_OUTPUT_DIR, run)
    report_path = _run_report_path(root / DEFAULT_OUTPUT_DIR, run)
    manifest_path = _run_manifest_path(root / DEFAULT_OUTPUT_DIR, run)

    if resume and _can_resume_run(run, manifest_path, summary_path, run_identity_sha256):
        summary = _read_json(summary_path)
        return {
            "run_name": run.name,
            "run_slug": run.slug,
            "run_kind": "simulation",
            "requested_start": run.requested_start,
            "requested_end": run.requested_end,
            "status": "DONE",
            "resume_skipped": True,
            "output_dir": _rel(root, run_dir),
            "performance": summary.get("performance", {}),
            "validation": summary.get("validation", {}),
            "output_files": summary.get("output_files", {}),
            "summary_json": _rel(root, summary_path),
            "report_text": _rel(root, report_path),
        }

    _write_json(config_path, {"historical_validation_20y": run_settings})
    coverage_df = build_data_coverage(
        context["universe_df"],
        context["histories"],
        pd.Timestamp(run.requested_start).normalize(),
        pd.Timestamp(run.requested_end).normalize(),
    )
    coverage_rows = coverage_df.to_dict(orient="records")
    result = simulate_validation(
        context["prepared_histories"],
        context["universe_df"],
        run_config,
        pd.Timestamp(run.requested_start).normalize(),
        pd.Timestamp(run.requested_end).normalize(),
    )
    performance = _summarize_oos_performance(result, float(run_settings["initial_capital_yen"]))
    report = _build_run_report(
        run=run,
        base_config_path=base_config_path,
        base_config_sha256=base_config_sha256,
        run_identity_sha256=run_identity_sha256,
        run_settings=run_settings,
        universe_df=context["universe_df"],
        coverage_rows=coverage_rows,
        result=result,
        performance=performance,
        context=context,
    )
    save_outputs(root, run_settings, report, result)
    atomic_write(report_path, _render_run_report(report))
    _write_run_manifest(
        manifest_path,
        run=run,
        base_config_path=base_config_path,
        base_config_sha256=base_config_sha256,
        run_identity_sha256=run_identity_sha256,
        status="DONE",
        resume_skipped=False,
        output_files=report["output_files"],
    )
    return {
        "run_name": run.name,
        "run_slug": run.slug,
        "run_kind": "simulation",
        "requested_start": run.requested_start,
        "requested_end": run.requested_end,
        "status": "DONE",
        "resume_skipped": False,
        "output_dir": _rel(root, run_dir),
        "performance": performance,
        "validation": report["validation"],
        "output_files": report["output_files"],
        "summary_json": _rel(root, summary_path),
        "report_text": _rel(root, report_path),
    }


def _build_summary_csv_rows(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in runs:
        performance = run.get("performance", {})
        validation = run.get("validation", {})
        rows.append(
            {
                "run_name": run.get("run_name", ""),
                "run_slug": run.get("run_slug", ""),
                "status": run.get("status", ""),
                "resume_skipped": bool(run.get("resume_skipped", False)),
                "output_dir": run.get("output_dir", ""),
                "requested_start": run.get("requested_start", ""),
                "requested_end": run.get("requested_end", ""),
                "breadth_threshold": validation.get("market_breadth_bear_threshold"),
                "bear_cap": validation.get("market_breadth_bear_max_total_invested_pct"),
                "slippage_rate": validation.get("slippage_rate"),
                "final_equity_yen": performance.get("final_equity_yen"),
                "total_return_pct": performance.get("total_return_pct"),
                "cagr_pct": performance.get("cagr_pct"),
                "profit_factor": performance.get("profit_factor"),
                "max_drawdown_pct": performance.get("max_drawdown_pct"),
                "trade_count": performance.get("trade_count"),
                "win_rate": performance.get("win_rate"),
                "expectancy_per_trade_yen": performance.get("expectancy_per_trade_yen"),
                "max_consecutive_losses": performance.get("max_consecutive_losses"),
                "longest_underwater_sessions": performance.get("longest_underwater_sessions"),
                "recovery_factor": performance.get("recovery_factor"),
                "rejected_due_to_lot": performance.get("rejected_due_to_lot"),
                "rejected_due_to_buying_power": performance.get("rejected_due_to_buying_power"),
            }
        )
    return rows


def _build_aggregate_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [run for run in runs if run.get("status") == "DONE"]
    profitable_run_count = sum(float(run.get("performance", {}).get("total_profit_yen", 0.0)) > 0 for run in successful)
    pf_gt_1_count = sum(float(run.get("performance", {}).get("profit_factor", 0.0)) > 1.0 for run in successful)
    cagr_gt_0_count = sum(float(run.get("performance", {}).get("cagr_pct", 0.0)) > 0.0 for run in successful)
    max_drawdown_values = [float(run.get("performance", {}).get("max_drawdown_pct", 0.0)) for run in successful]
    pf_values = [float(run.get("performance", {}).get("profit_factor", 0.0)) for run in successful]
    cagr_values = [float(run.get("performance", {}).get("cagr_pct", 0.0)) for run in successful]
    return {
        "successful_run_count": len(successful),
        "profitable_run_count": int(profitable_run_count),
        "pf_gt_1_run_count": int(pf_gt_1_count),
        "cagr_gt_0_run_count": int(cagr_gt_0_count),
        "max_max_drawdown_pct": round(max(max_drawdown_values), 6) if max_drawdown_values else None,
        "min_profit_factor": round(min(pf_values), 6) if pf_values else None,
        "min_cagr_pct": round(min(cagr_values), 6) if cagr_values else None,
    }


def _build_top_level_report(base_config_path: Path, fixed_summary: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    lines = [
        "=" * 96,
        RUNNER_VERSION,
        "=" * 96,
        f"Base config      : {base_config_path.as_posix()}",
        f"Requested window : {DEFAULT_REQUESTED_START} -> {DEFAULT_REQUESTED_END}",
        f"Fixed breadth    : {DEFAULT_FIXED_BREADTH_THRESHOLD:.2f}",
        f"Fixed BEAR cap   : {DEFAULT_FIXED_BEAR_CAP:.2f}",
        f"Fixed slippage   : baseline from base config",
        f"Initial capital  : {DEFAULT_INITIAL_CAPITAL_YEN:,.0f} yen",
        "",
        "Summary",
        "-" * 96,
        f"Successful runs   : {fixed_summary.get('successful_run_count', 0)} / {len(runs)}",
        f"Profitable runs   : {fixed_summary.get('profitable_run_count', 0)}",
        f"PF > 1 runs       : {fixed_summary.get('pf_gt_1_run_count', 0)}",
        f"CAGR > 0 runs     : {fixed_summary.get('cagr_gt_0_run_count', 0)}",
        f"Max MaxDD         : {fixed_summary.get('max_max_drawdown_pct', '')}",
        f"Min PF            : {fixed_summary.get('min_profit_factor', '')}",
        f"Min CAGR          : {fixed_summary.get('min_cagr_pct', '')}",
        "",
        "Runs",
        "-" * 96,
    ]
    for run in runs:
        perf = run.get("performance", {})
        val = run.get("validation", {})
        lines.append(
            f"{run.get('run_name', ''):<8} "
            f"{run.get('requested_start', '')} -> {run.get('requested_end', '')} "
            f"breadth={val.get('market_breadth_bear_threshold', '')} "
            f"cap={val.get('market_breadth_bear_max_total_invested_pct', '')} "
            f"EQ={perf.get('final_equity_yen', 0):,.0f} "
            f"CAGR={perf.get('cagr_pct', 0):+.2f}% "
            f"PF={perf.get('profit_factor', 0):.3f} "
            f"MaxDD={perf.get('max_drawdown_pct', 0):.2f}% "
            f"trades={perf.get('trade_count', 0)} "
            f"win={perf.get('win_rate', 0):.2f}%"
        )
    return "\n".join(lines) + "\n"


def _build_dry_run_payload(
    *,
    root: Path,
    base_config_path: Path,
    base_config_sha256: str,
    base_settings: dict[str, Any],
    runs: Iterable[OOSValidationRunSpec],
) -> dict[str, Any]:
    checks = {
        "base_config_exists": resolve_within(root, str(base_config_path)).is_file(),
        "market_cache_dir_exists": resolve_within(root, str(base_settings.get("cache_dir", "data/market_cache"))).is_dir(),
        "universe_csv_exists": resolve_within(root, str(base_settings.get("universe_csv", "data/nikkei225_membership_20y.csv"))).is_file(),
    }
    planned_runs: list[dict[str, Any]] = []
    run_list = tuple(runs)
    for run in run_list:
        run_dir = _run_dir(root / DEFAULT_OUTPUT_DIR, run)
        settings = _fixed_run_settings(
            base_settings,
            run,
            run_dir,
            _safe_float(base_settings.get("slippage_rate", 0.0005), 0.0005),
        )
        _build_historical_validation_config(settings).validate()
        run_identity_sha256, _ = _run_identity(base_config_sha256, run, settings)
        planned_runs.append(
            {
                "run_name": run.name,
                "run_slug": run.slug,
                "run_kind": "simulation",
                "requested_start": run.requested_start,
                "requested_end": run.requested_end,
                "output_dir": _rel(root, run_dir),
                "config_file": _rel(root, _run_config_path(root / DEFAULT_OUTPUT_DIR, run)),
                "manifest_file": _rel(root, _run_manifest_path(root / DEFAULT_OUTPUT_DIR, run)),
                "summary_file": _rel(root, _run_summary_path(root / DEFAULT_OUTPUT_DIR, run)),
                "run_identity_sha256": run_identity_sha256,
                "settings": {
                    "market_breadth_filter_enabled": settings.get("market_breadth_filter_enabled"),
                    "market_breadth_bear_threshold": settings.get("market_breadth_bear_threshold"),
                    "market_breadth_bear_max_total_invested_pct": settings.get("market_breadth_bear_max_total_invested_pct"),
                    "slippage_rate": settings.get("slippage_rate"),
                    "initial_capital_yen": settings.get("initial_capital_yen"),
                },
            }
        )

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "status": "DRY_RUN",
        "base_config_file": _rel(root, resolve_within(root, str(base_config_path))),
        "base_config_sha256": base_config_sha256,
        "requested_window": {
            "start": DEFAULT_REQUESTED_START,
            "end": DEFAULT_REQUESTED_END,
        },
        "fixed_validation": {
            "market_breadth_filter_enabled": True,
            "market_breadth_bear_threshold": DEFAULT_FIXED_BREADTH_THRESHOLD,
            "market_breadth_bear_max_total_invested_pct": DEFAULT_FIXED_BEAR_CAP,
            "slippage_rate": "baseline from base config",
            "initial_capital_yen": DEFAULT_INITIAL_CAPITAL_YEN,
        },
        "checks": checks,
        "planned_runs": planned_runs,
        "notes": [
            "No simulation is executed in dry-run mode.",
            "No network access is attempted in dry-run mode.",
            "All runs are fixed to breadth=0.40, BEAR cap=0.70, and baseline slippage.",
        ],
    }


def run_oos_validation(
    *,
    root: Path | None = None,
    base_config_path: Path | str = DEFAULT_BASE_CONFIG_PATH,
    resume: bool = True,
    dry_run: bool = False,
    as_of: datetime = DEFAULT_AS_OF,
) -> dict[str, Any]:
    repository = (root or ROOT).resolve()
    base_config_path = Path(base_config_path)
    output_root = repository / DEFAULT_OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    base_settings, base_config_sha256 = _base_settings(repository, base_config_path)
    runs = build_run_specs()

    if dry_run:
        dry_run_payload = _build_dry_run_payload(
            root=repository,
            base_config_path=base_config_path,
            base_config_sha256=base_config_sha256,
            base_settings=base_settings,
            runs=runs,
        )
        _write_json(output_root / DEFAULT_PLAN_FILE, dry_run_payload)
        atomic_write(
            output_root / DEFAULT_DRY_RUN_TEXT_FILE,
            _build_top_level_report(base_config_path, _build_aggregate_summary([]), []),
        )
        return dry_run_payload

    context = _prepare_context(repository, base_settings, runs, as_of)
    run_records: list[dict[str, Any]] = []
    for run in runs:
        try:
            record = _execute_run(
                root=repository,
                base_settings=base_settings,
                base_config_path=base_config_path,
                base_config_sha256=base_config_sha256,
                context=context,
                run=run,
                resume=resume,
            )
        except Exception as error:
            run_dir = _run_dir(output_root, run)
            run_dir.mkdir(parents=True, exist_ok=True)
            record = {
                "run_name": run.name,
                "run_slug": run.slug,
                "run_kind": "simulation",
                "requested_start": run.requested_start,
                "requested_end": run.requested_end,
                "status": "FAILED",
                "resume_skipped": False,
                "output_dir": _rel(repository, run_dir),
                "performance": {},
                "validation": {
                    "market_breadth_filter_enabled": True,
                    "market_breadth_bear_threshold": DEFAULT_FIXED_BREADTH_THRESHOLD,
                    "market_breadth_bear_max_total_invested_pct": DEFAULT_FIXED_BEAR_CAP,
                    "slippage_rate": _safe_float(base_settings.get("slippage_rate", 0.0005), 0.0005),
                },
                "output_files": {},
                "summary_json": "",
                "report_text": "",
                "error": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
            }
            manifest_path = _run_manifest_path(output_root, run)
            _write_run_manifest(
                manifest_path,
                run=run,
                base_config_path=base_config_path,
                base_config_sha256=base_config_sha256,
                run_identity_sha256="",
                status="FAILED",
                resume_skipped=False,
                output_files={},
                error=record["error"],
            )
            atomic_write(run_dir / DEFAULT_REPORT_FILE, record["error"])
        run_records.append(record)

    aggregate = _build_aggregate_summary(run_records)
    summary = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "status": "FAILED" if any(run.get("status") == "FAILED" for run in run_records) else "SUCCESS",
        "base_config_file": _rel(repository, resolve_within(repository, str(base_config_path))),
        "base_config_sha256": base_config_sha256,
        "run_count": len(run_records),
        "fixed_validation": {
            "market_breadth_filter_enabled": True,
            "market_breadth_bear_threshold": DEFAULT_FIXED_BREADTH_THRESHOLD,
            "market_breadth_bear_max_total_invested_pct": DEFAULT_FIXED_BEAR_CAP,
            "slippage_rate": _safe_float(base_settings.get("slippage_rate", 0.0005), 0.0005),
            "initial_capital_yen": DEFAULT_INITIAL_CAPITAL_YEN,
        },
        "aggregate": aggregate,
        "runs": run_records,
    }
    summary_path = output_root / DEFAULT_SUMMARY_FILE
    report_path = output_root / DEFAULT_REPORT_FILE
    summary_csv_path = output_root / DEFAULT_SUMMARY_CSV_FILE
    _write_json(summary_path, summary)
    atomic_write(report_path, _build_top_level_report(base_config_path, aggregate, run_records))
    pd.DataFrame(_build_summary_csv_rows(run_records)).to_csv(summary_csv_path, index=False, encoding="utf-8-sig")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PHOENIX OOS Validation Risk v2")
    parser.add_argument(
        "--base-config",
        default=str(DEFAULT_BASE_CONFIG_PATH),
        help="Base config to clone for OOS validation runs",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the OOS plan without running simulations",
    )
    parser.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="Skip finished runs when run artifacts already exist",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Recompute all runs even if artifacts already exist",
    )
    args = parser.parse_args(argv)

    try:
        run_oos_validation(
            root=ROOT,
            base_config_path=Path(args.base_config),
            resume=bool(args.resume),
            dry_run=bool(args.dry_run),
        )
        return 0
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        if isinstance(error, OOSValidationError):
            return 2
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
