from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import traceback
import math
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market_data_manager import normalize_ticker
from phoenix_core.historical_validation_20y import (
    EXPECTED_NIKKEI225_COUNT,
    JST,
    HistoricalValidationError,
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


DEFAULT_SPEC_PATH = Path("config/formal_validation_runs.json")
DEFAULT_ACCEPTANCE_CRITERIA_PATH = Path("config/formal_validation_acceptance_criteria.json")
DEFAULT_OUTPUT_DIR = Path("reports/formal_validation")
DEFAULT_INPUT_MANIFEST_FILE = "input_manifest.json"
DEFAULT_SUMMARY_JSON_FILE = "summary.json"
DEFAULT_SUMMARY_CSV_FILE = "summary.csv"
DEFAULT_REPORT_TEXT_FILE = "report.txt"
DEFAULT_DRY_RUN_JSON_FILE = "dry_run.json"
DEFAULT_RUNS_DIR = "runs"
DEFAULT_WINDOW_PAD = 20
MANIFEST_SCHEMA_VERSION = 1
RUN_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class FormalValidationRunSpec:
    name: str
    requested_start: str
    requested_end: str
    market_breadth_filter_enabled: bool

    def to_manifest_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def window_key(self) -> tuple[str, str]:
        return self.requested_start, self.requested_end


@dataclass(frozen=True, slots=True)
class FormalValidationSpec:
    path: Path
    raw: dict[str, Any]
    base_config_path: Path
    output_dir: Path
    cache_dir: Path
    universe_csv: Path
    runs: tuple[FormalValidationRunSpec, ...]
    allow_network_fetch: bool
    stop_on_fail: bool


class FormalValidationError(RuntimeError):
    pass


def _now_text() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _list_cache_files(cache_dir: Path) -> list[Path]:
    if not cache_dir.is_dir():
        raise FileNotFoundError(f"Market cache directory is missing: {cache_dir}")
    return sorted(path for path in cache_dir.rglob("*") if path.is_file())


def _cache_ticker_from_file(path: Path) -> str:
    if path.suffix.lower() != ".csv":
        return ""
    stem = path.stem.replace("_", ".")
    ticker = normalize_ticker(stem).strip().upper()
    return ticker


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _json_safe_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append({key: _json_safe_value(value) for key, value in row.items()})
    return records


def _build_market_cache_inventory(root: Path, cache_dir: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for path in _list_cache_files(cache_dir):
        inventory.append(
            {
                "path": _rel(root, path),
                "size": int(path.stat().st_size),
                "sha256": _sha256_file(path),
            }
        )
    return inventory


def _load_run_specs(raw_runs: Any) -> tuple[FormalValidationRunSpec, ...]:
    if not isinstance(raw_runs, list) or not raw_runs:
        raise ValueError("formal_validation_runs.json must contain a non-empty runs list")

    expected_names = ("P1_OFF", "P1_ON", "P2_OFF", "P2_ON")
    if len(raw_runs) != len(expected_names):
        raise ValueError("formal_validation_runs.json must define exactly four runs")

    parsed: list[FormalValidationRunSpec] = []
    for expected_name, raw in zip(expected_names, raw_runs, strict=True):
        if not isinstance(raw, dict):
            raise ValueError("Each run specification must be an object")
        name = str(raw.get("name", "")).strip()
        if name != expected_name:
            raise ValueError(f"Unexpected run name: {name!r}; expected {expected_name!r}")
        requested_start = str(raw.get("requested_start", "")).strip()
        requested_end = str(raw.get("requested_end", "")).strip()
        if not requested_start or not requested_end:
            raise ValueError(f"Run {name} must define requested_start and requested_end")
        market_breadth_filter_enabled = bool(raw.get("market_breadth_filter_enabled", False))
        start_ts = pd.Timestamp(requested_start)
        end_ts = pd.Timestamp(requested_end)
        if end_ts < start_ts:
            raise ValueError(f"Run {name} requested_end must be on or after requested_start")
        parsed.append(
            FormalValidationRunSpec(
                name=name,
                requested_start=start_ts.date().isoformat(),
                requested_end=end_ts.date().isoformat(),
                market_breadth_filter_enabled=market_breadth_filter_enabled,
            )
        )
    return tuple(parsed)


def load_formal_validation_spec(root: Path, spec_path: Path | str = DEFAULT_SPEC_PATH) -> FormalValidationSpec:
    repository = root.resolve()
    spec_file = resolve_within(repository, str(spec_path))
    raw = _load_json_file(spec_file)
    if int(raw.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
        raise ValueError("formal_validation_runs.json schema_version must be 1")

    base_config_path = resolve_within(repository, str(raw.get("base_config_path", "config/v7_historical_validation_20y.json")))
    output_dir = resolve_within(repository, str(raw.get("output_dir", DEFAULT_OUTPUT_DIR)))
    cache_dir = resolve_within(repository, str(raw.get("cache_dir", "data/market_cache")))
    universe_csv = resolve_within(repository, str(raw.get("universe_csv", "data/nikkei225_membership_20y.csv")))
    allow_network_fetch = bool(raw.get("allow_network_fetch", False))
    stop_on_fail = bool(raw.get("stop_on_fail", True))
    if allow_network_fetch:
        raise ValueError("formal validation runner must keep network fetch disabled")

    runs = _load_run_specs(raw.get("runs"))
    return FormalValidationSpec(
        path=spec_file,
        raw=raw,
        base_config_path=base_config_path,
        output_dir=output_dir,
        cache_dir=cache_dir,
        universe_csv=universe_csv,
        runs=runs,
        allow_network_fetch=allow_network_fetch,
        stop_on_fail=stop_on_fail,
    )


def _build_input_manifest_payload(root: Path, spec: FormalValidationSpec, worker_path: Path, launcher_path: Path) -> dict[str, Any]:
    cache_inventory = _build_market_cache_inventory(root, spec.cache_dir)
    cache_csv_files = [entry for entry in cache_inventory if entry["path"].lower().endswith(".csv")]
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "root": root.resolve().as_posix(),
        "spec_file": _rel(root, spec.path),
        "spec_sha256": _sha256_file(spec.path),
        "historical_validation_file": _rel(root, root / "phoenix_core" / "historical_validation_20y.py"),
        "historical_validation_sha256": _sha256_file(root / "phoenix_core" / "historical_validation_20y.py"),
        "base_config_file": _rel(root, spec.base_config_path),
        "base_config_sha256": _sha256_file(spec.base_config_path),
        "membership_file": _rel(root, spec.universe_csv),
        "membership_sha256": _sha256_file(spec.universe_csv),
        "cache_dir": _rel(root, spec.cache_dir),
        "market_cache_file_count": len(cache_inventory),
        "market_cache_csv_count": len(cache_csv_files),
        "market_cache_files": cache_inventory,
        "worker_file": _rel(root, worker_path),
        "worker_sha256": _sha256_file(worker_path),
        "launcher_file": _rel(root, launcher_path),
        "launcher_sha256": _sha256_file(launcher_path),
        "python_version": platform.python_version(),
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "output_dir": _rel(root, spec.output_dir),
        "allow_network_fetch": spec.allow_network_fetch,
        "run_specs": [run.to_manifest_dict() for run in spec.runs],
    }
    return payload


def _finalize_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    stable_payload = dict(payload)
    manifest_sha256 = _sha256_text(_canonical_json(stable_payload))
    finalized = dict(stable_payload)
    finalized["generated_at"] = _now_text()
    finalized["input_manifest_sha256"] = manifest_sha256
    return finalized


def _read_manifest_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    manifest = _load_json_file(path)
    if int(manifest.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported input manifest schema: {path}")
    return manifest


def _run_spec_sha256(run_spec: FormalValidationRunSpec) -> str:
    return _sha256_text(_canonical_json(run_spec.to_manifest_dict()))


def _run_identity_sha256(run_spec_sha256: str, input_manifest_sha256: str) -> str:
    payload = {
        "run_spec_sha256": run_spec_sha256,
        "input_manifest_sha256": input_manifest_sha256,
    }
    return _sha256_text(_canonical_json(payload))


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


def _build_run_settings(
    base_settings: dict[str, Any],
    run_spec: FormalValidationRunSpec,
    run_dir: Path,
) -> dict[str, Any]:
    settings = dict(base_settings)
    settings.update(
        {
            "requested_start": run_spec.requested_start,
            "requested_end": run_spec.requested_end,
            "allow_network_fetch": False,
            "market_breadth_filter_enabled": run_spec.market_breadth_filter_enabled,
            "output_dir": str(run_dir),
            "report_json": str(run_dir / "summary.json"),
            "report_text": str(run_dir / "report.txt"),
            "coverage_csv": str(run_dir / "data_coverage.csv"),
            "data_coverage_csv": str(run_dir / "data_coverage.csv"),
            "diagnostics_csv": str(run_dir / "diagnostics.csv"),
            "annual_returns_csv": str(run_dir / "annual_returns.csv"),
            "monthly_returns_csv": str(run_dir / "monthly_returns.csv"),
            "trades_csv": str(run_dir / "trades.csv"),
            "equity_curve_csv": str(run_dir / "equity_curve.csv"),
            "no_rss": True,
            "no_real_orders": True,
            "live_trading_enabled": False,
            "orders_submitted": 0,
        }
    )
    return settings


def _cache_ticker_set_from_manifest(input_manifest: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for entry in input_manifest.get("market_cache_files", []):
        if not isinstance(entry, dict):
            continue
        relative_path = str(entry.get("path", ""))
        if not relative_path.lower().endswith(".csv"):
            continue
        result.add(_cache_ticker_from_file(Path(relative_path)))
    return {ticker for ticker in result if ticker}


def _build_formal_report_text(report: dict[str, Any]) -> str:
    performance = report.get("performance", {})
    formal = report.get("formal_validation", {})
    output_files = report.get("output_files", {})
    lines = [
        "PHOENIX FORMAL VALIDATION 20Y",
        "=" * 84,
        f"Run name           : {report.get('run_name', '')}",
        f"Status             : {report.get('status', '')}",
        f"Requested start    : {report.get('requested_start', '')}",
        f"Requested end      : {report.get('requested_end', '')}",
        f"Risk v2 enabled    : {report.get('market_breadth_filter_enabled', False)}",
        f"Input manifest SHA : {report.get('input_manifest_sha256', '')}",
        f"Run spec SHA       : {report.get('run_spec_sha256', '')}",
        f"Run identity SHA   : {report.get('run_identity_sha256', '')}",
        "",
        "Coverage / prep",
        "-" * 84,
        f"Membership tickers : {formal.get('membership_ticker_count', 0)}",
        f"Cache tickers      : {formal.get('cache_csv_ticker_count', 0)}",
        f"Prepared tickers   : {formal.get('simulation_ticker_count', 0)}",
        f"Excluded cache     : {formal.get('excluded_cache_ticker_count', 0)}",
        f"Fetch disabled     : {report.get('safety', {}).get('no_rss', False)}",
        "",
        "Performance",
        "-" * 84,
        f"Final equity       : {performance.get('final_equity_yen', 0):,.0f} yen",
        f"Total return       : {performance.get('total_return', performance.get('total_return_pct', 0)):+.2f}%",
        f"CAGR               : {performance.get('CAGR', performance.get('cagr_pct', 0)):+.2f}%",
        f"Profit factor      : {performance.get('profit_factor', 0):.3f}",
        f"Expectancy / trade  : {performance.get('expectancy_per_trade_yen', 0):,.2f} yen",
        f"Max drawdown       : {performance.get('max_drawdown', performance.get('max_drawdown_pct', 0)):.2f}%",
        f"Win rate            : {performance.get('win_rate', performance.get('win_rate_pct', 0)):.2f}%",
        f"Trades              : {performance.get('trade_count', 0)}",
        f"Avg holding         : {performance.get('avg_holding', performance.get('average_holding_sessions', 0)):.2f} sessions",
        f"Avg cash            : {performance.get('avg_cash_yen', 0):,.2f} yen",
        f"Max consecutive loss: {performance.get('max_consecutive_losses', 0)}",
        f"Longest underwater  : {performance.get('longest_underwater_sessions', 0)} sessions",
        f"Recovery factor     : {performance.get('recovery_factor', 0):.6f}",
        f"Rejected lot        : {performance.get('rejected_due_to_lot', 0)}",
        f"Rejected buying     : {performance.get('rejected_due_to_buying_power', 0)}",
        "",
        "Outputs",
        "-" * 84,
        f"Summary JSON        : {output_files.get('summary_json', '')}",
        f"Report text         : {output_files.get('report_text', '')}",
        f"Coverage CSV        : {output_files.get('data_coverage_csv', '')}",
        f"Diagnostics CSV     : {output_files.get('diagnostics_csv', '')}",
        f"Annual CSV          : {output_files.get('annual_returns_csv', '')}",
        f"Monthly CSV         : {output_files.get('monthly_returns_csv', '')}",
        f"Trades CSV          : {output_files.get('trades_csv', '')}",
        f"Equity CSV          : {output_files.get('equity_curve_csv', '')}",
    ]
    if output_files.get("risk_v2_research_csv"):
        lines.append(f"Risk v2 research    : {output_files.get('risk_v2_research_csv', '')}")
    if report.get("error"):
        lines.extend(["", "Error", "-" * 84, str(report.get("error", ""))])
    lines.append("=" * 84)
    return "\n".join(lines) + "\n"


def _build_aggregate_report_text(summary: dict[str, Any]) -> str:
    lines = [
        "PHOENIX FORMAL VALIDATION SUMMARY",
        "=" * 84,
        f"Status             : {summary.get('status', '')}",
        f"Input manifest SHA  : {summary.get('input_manifest_sha256', '')}",
        f"Output dir         : {summary.get('output_dir', '')}",
        "",
        "Runs",
        "-" * 84,
    ]
    for run in summary.get("runs", []):
        final_equity_yen = _run_metric(run, "final_equity_yen", 0)
        total_return_pct = _run_metric(run, "total_return_pct", 0)
        cagr_pct = _run_metric(run, "cagr_pct", 0)
        profit_factor = _run_metric(run, "profit_factor", 0)
        max_drawdown_pct = _run_metric(run, "max_drawdown_pct", 0)
        trade_count = _run_metric(run, "trade_count", 0)
        lines.extend(
            [
                f"{run.get('run_name', '')} | {run.get('status', '')} | resume_skipped={run.get('resume_skipped', False)}",
                f"  Final equity    : {final_equity_yen:,.0f} yen",
                f"  Total return    : {total_return_pct:+.2f}%",
                f"  CAGR            : {cagr_pct:+.2f}%",
                f"  Profit factor   : {profit_factor:.3f}",
                f"  Max drawdown    : {max_drawdown_pct:.2f}%",
                f"  Trades          : {trade_count}",
            ]
        )
    comparisons = summary.get("comparisons", [])
    if comparisons:
        lines.extend(["", "ON / OFF Deltas", "-" * 84])
        for comparison in comparisons:
            lines.extend(
                [
                    f"{comparison.get('pair_name', '')}",
                    f"  Final equity Δ  : {comparison.get('final_equity_delta_yen', 0):,.0f} yen",
                    f"  CAGR Δ          : {comparison.get('cagr_delta_pct', 0):+.2f}%",
                    f"  PF Δ            : {comparison.get('profit_factor_delta', 0):+.3f}",
                    f"  MaxDD Δ         : {comparison.get('max_drawdown_delta_pct', 0):+.2f}%",
                    f"  Trades Δ        : {comparison.get('trade_count_delta', 0):+d}",
                ]
            )
    lines.append("=" * 84)
    return "\n".join(lines) + "\n"


def _flatten_run_for_csv(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_name": run.get("run_name", ""),
        "status": run.get("status", ""),
        "resume_skipped": bool(run.get("resume_skipped", False)),
        "requested_start": run.get("requested_start", ""),
        "requested_end": run.get("requested_end", ""),
        "risk_v2_enabled": bool(run.get("market_breadth_filter_enabled", False)),
        "input_manifest_sha256": run.get("input_manifest_sha256", ""),
        "run_spec_sha256": run.get("run_spec_sha256", ""),
        "run_identity_sha256": run.get("run_identity_sha256", ""),
        "final_equity_yen": _run_metric(run, "final_equity_yen", ""),
        "total_return_pct": _run_metric(run, "total_return_pct", ""),
        "cagr_pct": _run_metric(run, "cagr_pct", ""),
        "profit_factor": _run_metric(run, "profit_factor", ""),
        "expectancy_per_trade_yen": _run_metric(run, "expectancy_per_trade_yen", ""),
        "max_drawdown_pct": _run_metric(run, "max_drawdown_pct", ""),
        "win_rate_pct": _run_metric(run, "win_rate_pct", ""),
        "trade_count": _run_metric(run, "trade_count", ""),
        "avg_holding_sessions": _run_metric(run, "avg_holding_sessions", ""),
        "avg_cash_yen": _run_metric(run, "avg_cash_yen", ""),
        "max_consecutive_losses": _run_metric(run, "max_consecutive_losses", ""),
        "longest_underwater_sessions": _run_metric(run, "longest_underwater_sessions", ""),
        "recovery_factor": _run_metric(run, "recovery_factor", ""),
        "rejected_due_to_lot": _run_metric(run, "rejected_due_to_lot", ""),
        "rejected_due_to_buying_power": _run_metric(run, "rejected_due_to_buying_power", ""),
        "membership_ticker_count": run.get("membership_ticker_count", ""),
        "cache_csv_ticker_count": run.get("cache_csv_ticker_count", ""),
        "simulation_ticker_count": run.get("simulation_ticker_count", ""),
        "excluded_cache_ticker_count": run.get("excluded_cache_ticker_count", ""),
        "summary_json": run.get("summary_json", ""),
        "report_text": run.get("report_text", ""),
        "run_log": run.get("run_log", ""),
    }


def _run_performance(run: dict[str, Any]) -> dict[str, Any]:
    performance = run.get("performance")
    return performance if isinstance(performance, dict) else {}


def _run_metric(run: dict[str, Any], key: str, default: Any = 0.0) -> Any:
    performance = _run_performance(run)
    if key in performance:
        return performance.get(key, default)
    return run.get(key, default)


def _gate_row(name: str, status: str, reason: str) -> dict[str, str]:
    return {"name": name, "status": status, "reason": reason}


def _all_pass(rows: list[dict[str, Any]]) -> bool:
    return all(row.get("status") == "PASS" for row in rows)


def _safe_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise FormalValidationError(f"{field} is missing or not numeric") from error
    if not math.isfinite(number):
        raise FormalValidationError(f"{field} is not finite")
    return number


def _contains_non_finite_json(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_non_finite_json(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_non_finite_json(item) for item in value)
    return False


def _load_acceptance_criteria(root: Path, criteria_path: Path | str) -> dict[str, Any]:
    criteria_file = resolve_within(root, str(criteria_path))
    criteria = _load_json_file(criteria_file)
    if int(criteria.get("schema_version", 0)) != MANIFEST_SCHEMA_VERSION:
        raise FormalValidationError("formal validation acceptance criteria schema_version must be 1")
    for key in ("hard_gates", "safety_gates", "performance_policy", "closure_policy"):
        if not isinstance(criteria.get(key), dict):
            raise FormalValidationError(f"formal validation acceptance criteria missing {key}")
    metrics = criteria["performance_policy"].get("metrics")
    if not isinstance(metrics, dict):
        raise FormalValidationError("formal validation acceptance criteria missing performance_policy.metrics")
    required_metrics = (
        "cagr_delta_pct",
        "final_equity_delta_yen",
        "profit_factor_delta",
        "max_drawdown_delta_pct",
        "trade_count_delta",
    )
    for metric in required_metrics:
        if metric not in metrics:
            raise FormalValidationError(f"formal validation acceptance criteria missing metric {metric}")
    pairs = criteria["performance_policy"].get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise FormalValidationError("formal validation acceptance criteria missing performance_policy.pairs")
    return criteria


def _evaluate_threshold(metric: str, value: float, rule: dict[str, Any]) -> tuple[str, str]:
    if bool(rule.get("informational_only", False)):
        return "PASS", f"{metric}={value} is informational only"
    operator = str(rule.get("operator", "")).strip()
    threshold = _safe_number(rule.get("threshold"), f"criteria.{metric}.threshold")
    if operator == ">":
        passed = value > threshold
    elif operator == ">=":
        passed = value >= threshold
    elif operator == "<":
        passed = value < threshold
    elif operator == "<=":
        passed = value <= threshold
    else:
        raise FormalValidationError(f"Unsupported acceptance operator for {metric}: {operator!r}")
    status = "PASS" if passed else "FAIL"
    return status, f"{metric}={value} {operator} {threshold}"


def _read_text_if_present(path: Path) -> str:
    if not path.is_file():
        raise FormalValidationError(f"Required formal validation artifact is missing: {path}")
    return path.read_text(encoding="utf-8-sig")


def _comparison_rows_from_run_rows(run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {row["run_name"]: row for row in run_rows if row.get("status") == "DONE"}
    pairs = [("P1_OFF", "P1_ON"), ("P2_OFF", "P2_ON")]
    comparisons: list[dict[str, Any]] = []
    for off_name, on_name in pairs:
        off = lookup.get(off_name)
        on = lookup.get(on_name)
        if not off or not on:
            continue
        comparisons.append(
            {
                "pair_name": f"{on_name} - {off_name}",
                "left_run": off_name,
                "right_run": on_name,
                "final_equity_delta_yen": round(float(_run_metric(on, "final_equity_yen", 0.0)) - float(_run_metric(off, "final_equity_yen", 0.0)), 2),
                "cagr_delta_pct": round(float(_run_metric(on, "cagr_pct", 0.0)) - float(_run_metric(off, "cagr_pct", 0.0)), 6),
                "profit_factor_delta": round(float(_run_metric(on, "profit_factor", 0.0)) - float(_run_metric(off, "profit_factor", 0.0)), 6),
                "max_drawdown_delta_pct": round(float(_run_metric(on, "max_drawdown_pct", 0.0)) - float(_run_metric(off, "max_drawdown_pct", 0.0)), 6),
                "trade_count_delta": int(float(_run_metric(on, "trade_count", 0)) - float(_run_metric(off, "trade_count", 0))),
            }
        )
    return comparisons


def evaluate_formal_validation_acceptance(
    root: Path | str | None = None,
    *,
    spec_path: Path | str = DEFAULT_SPEC_PATH,
    criteria_path: Path | str = DEFAULT_ACCEPTANCE_CRITERIA_PATH,
) -> dict[str, Any]:
    repository = (Path(root) if root is not None else Path(__file__).resolve().parent.parent).resolve()
    output_dir = Path(str(spec_path)).parent

    hard_gates: list[dict[str, str]] = []
    safety_gates: list[dict[str, str]] = []
    outcome_rows: list[dict[str, Any]] = []
    report_text = ""

    try:
        criteria = _load_acceptance_criteria(repository, criteria_path)
        spec = load_formal_validation_spec(repository, spec_path)
        output_dir = spec.output_dir
        summary_path = output_dir / DEFAULT_SUMMARY_JSON_FILE
        summary_csv_path = output_dir / DEFAULT_SUMMARY_CSV_FILE
        report_text_path = output_dir / DEFAULT_REPORT_TEXT_FILE
        input_manifest_path = output_dir / DEFAULT_INPUT_MANIFEST_FILE
        dry_run_path = output_dir / DEFAULT_DRY_RUN_JSON_FILE
        summary = _load_json_file(summary_path)
        input_manifest = _load_json_file(input_manifest_path)
        dry_run = _load_json_file(dry_run_path)
        report_text = _read_text_if_present(report_text_path)
        summary_csv = pd.read_csv(summary_csv_path, encoding="utf-8-sig")
        all_files = sorted(path for path in output_dir.rglob("*") if path.is_file())

        required_names = list(criteria["hard_gates"].get("required_run_names", []))
        runs = summary.get("runs", [])
        run_lookup = {str(run.get("run_name", "")): run for run in runs if isinstance(run, dict)}
        present_names = [str(run.get("run_name", "")) for run in runs if isinstance(run, dict)]
        hard_gates.append(
            _gate_row(
                "required_run_names",
                "PASS" if present_names == required_names else "FAIL",
                f"present={present_names}",
            )
        )
        aggregate_status = str(criteria["hard_gates"].get("aggregate_status", ""))
        hard_gates.append(
            _gate_row(
                "aggregate_status",
                "PASS" if summary.get("status") == aggregate_status else "FAIL",
                f"summary.status={summary.get('status')}",
            )
        )
        expected_run_status = str(criteria["hard_gates"].get("run_status", ""))
        hard_gates.append(
            _gate_row(
                "all_runs_done",
                "PASS" if all(str(run.get("status", "")) == expected_run_status for run in runs) else "FAIL",
                f"expected={expected_run_status}",
            )
        )

        expected_input_sha = str(summary.get("input_manifest_sha256", ""))
        manifest_ok = bool(expected_input_sha)
        manifest_ok = manifest_ok and input_manifest.get("input_manifest_sha256") == expected_input_sha
        manifest_ok = manifest_ok and dry_run.get("input_manifest_sha256") == expected_input_sha
        expected_run_summary_status = str(criteria["hard_gates"].get("run_summary_status", ""))
        missing_output_files: list[str] = []
        for run_name in required_names:
            run = run_lookup.get(run_name, {})
            run_dir = output_dir / DEFAULT_RUNS_DIR / run_name
            run_manifest = _load_json_file(run_dir / "manifest.json")
            run_summary = _load_json_file(run_dir / "summary.json")
            manifest_ok = manifest_ok and run_manifest.get("input_manifest_sha256") == expected_input_sha
            manifest_ok = manifest_ok and run_summary.get("input_manifest_sha256") == expected_input_sha
            manifest_ok = manifest_ok and run_manifest.get("run_spec_sha256") == run.get("run_spec_sha256")
            manifest_ok = manifest_ok and run_manifest.get("run_identity_sha256") == run.get("run_identity_sha256")
            manifest_ok = manifest_ok and run_manifest.get("status") == expected_run_status
            manifest_ok = manifest_ok and run_summary.get("status") == expected_run_summary_status
            output_files = run_summary.get("output_files", {})
            if not isinstance(output_files, dict) or not output_files:
                missing_output_files.append(f"{run_name}:output_files")
            else:
                for output_name, output_path in output_files.items():
                    candidate = Path(str(output_path))
                    artifact_path = candidate if candidate.is_absolute() else repository / candidate
                    if not artifact_path.is_file():
                        missing_output_files.append(f"{run_name}:{output_name}")
        hard_gates.append(
            _gate_row(
                "manifest_binding",
                "PASS" if manifest_ok else "FAIL",
                f"input_manifest_sha256={expected_input_sha}",
            )
        )
        hard_gates.append(
            _gate_row(
                "output_completeness",
                "PASS" if not missing_output_files else "FAIL",
                f"missing={missing_output_files}",
            )
        )

        csv_ok = len(summary_csv.index) == len(required_names)
        for run_name in required_names:
            run = run_lookup.get(run_name, {})
            matching_rows = summary_csv[summary_csv["run_name"] == run_name]
            if len(matching_rows.index) != 1:
                csv_ok = False
                continue
            row = matching_rows.iloc[0]
            csv_ok = csv_ok and str(row.get("status", "")) == str(run.get("status", ""))
            csv_ok = csv_ok and str(row.get("input_manifest_sha256", "")) == str(run.get("input_manifest_sha256", ""))
            for metric in ("cagr_pct", "final_equity_yen", "profit_factor", "max_drawdown_pct", "trade_count"):
                csv_ok = csv_ok and _safe_number(row.get(metric), f"summary.csv.{run_name}.{metric}") == _safe_number(
                    _run_metric(run, metric),
                    f"summary.json.{run_name}.{metric}",
                )
        report_ok = bool(re.search(r"Status\s+:\s+SUCCESS", report_text))
        report_ok = report_ok and expected_input_sha in report_text
        report_ok = report_ok and str(summary.get("output_dir", "")) in report_text
        report_ok = report_ok and all(f"{run_name} | DONE | resume_skipped=False" in report_text for run_name in required_names)
        for comparison in summary.get("comparisons", []):
            report_ok = report_ok and str(comparison.get("pair_name", "")) in report_text
        hard_gates.append(
            _gate_row(
                "report_consistency",
                "PASS" if csv_ok and report_ok else "FAIL",
                f"summary_csv={csv_ok}; report_text={report_ok}",
            )
        )

        zero_byte_files = [_rel(repository, path) for path in all_files if path.stat().st_size == 0]
        hard_gates.append(
            _gate_row(
                "zero_byte_outputs",
                "PASS" if not zero_byte_files else "FAIL",
                f"zero_byte_files={zero_byte_files}",
            )
        )

        non_finite = _contains_non_finite_json(summary) or _contains_non_finite_json(input_manifest) or _contains_non_finite_json(dry_run)
        non_finite_pattern = re.compile(r"\b(?:nan|inf|infinity)\b", re.IGNORECASE)
        old_namespace_pattern = re.compile(r"reports[\\/]+formal_validation(?:[\\/]|$)")
        old_namespace_hits: list[str] = []
        for path in all_files:
            if path.suffix.lower() not in {".json", ".csv", ".txt", ".log"}:
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if non_finite_pattern.search(text):
                non_finite = True
            if old_namespace_pattern.search(text):
                old_namespace_hits.append(_rel(repository, path))
        hard_gates.append(
            _gate_row(
                "non_finite_values",
                "PASS" if not non_finite else "FAIL",
                "no NaN/Infinity tokens or numeric non-finite values found" if not non_finite else "non-finite value found",
            )
        )
        hard_gates.append(
            _gate_row(
                "old_namespace_contamination",
                "PASS" if not old_namespace_hits else "FAIL",
                f"hits={old_namespace_hits}",
            )
        )

        expected_safety = criteria["safety_gates"]
        safety_gates.append(
            _gate_row(
                "allow_network_fetch",
                "PASS" if spec.allow_network_fetch is bool(expected_safety.get("allow_network_fetch")) else "FAIL",
                f"spec.allow_network_fetch={spec.allow_network_fetch}",
            )
        )
        for run_name in required_names:
            run_summary = _load_json_file(output_dir / DEFAULT_RUNS_DIR / run_name / "summary.json")
            safety = run_summary.get("safety", {})
            for field in ("no_rss", "no_real_orders", "orders_submitted", "live_trading_enabled"):
                expected = expected_safety.get(field)
                actual = safety.get(field)
                safety_gates.append(
                    _gate_row(
                        f"{run_name}.{field}",
                        "PASS" if actual == expected else "FAIL",
                        f"actual={actual}; expected={expected}",
                    )
                )
        paper_ok = all(
            row.get("status") == "PASS"
            for row in safety_gates
            if row["name"].endswith(".no_real_orders")
            or row["name"].endswith(".orders_submitted")
            or row["name"].endswith(".live_trading_enabled")
        )
        safety_gates.append(
            _gate_row(
                "paper_maintained",
                "PASS" if paper_ok and bool(expected_safety.get("paper_maintained", False)) else "FAIL",
                "derived from no_real_orders=true, orders_submitted=0, live_trading_enabled=false",
            )
        )
        safety_gates.append(
            _gate_row(
                "bridge_armed",
                "PASS" if expected_safety.get("bridge_armed") is False else "FAIL",
                "formal validation does not arm bridge; criteria requires false",
            )
        )

        recalculated_comparisons = _comparison_rows_from_run_rows(runs)
        if recalculated_comparisons != summary.get("comparisons", []):
            hard_gates.append(_gate_row("comparison_binding", "FAIL", "summary comparisons do not match recalculated deltas"))
        else:
            hard_gates.append(_gate_row("comparison_binding", "PASS", "summary comparisons match recalculated deltas"))
        comparison_lookup = {row["pair_name"]: row for row in recalculated_comparisons}
        metric_rules = criteria["performance_policy"]["metrics"]
        for pair in criteria["performance_policy"].get("pairs", []):
            outcome_name = str(pair.get("name", ""))
            off_name = str(pair.get("off_run", ""))
            on_name = str(pair.get("on_run", ""))
            pair_name = f"{on_name} - {off_name}"
            comparison = comparison_lookup.get(pair_name)
            metric_results: dict[str, Any] = {}
            outcome_status = "PASS"
            if comparison is None:
                outcome_status = "FAIL"
                metric_results["pair"] = {"status": "FAIL", "reason": f"missing comparison {pair_name}"}
            else:
                for metric, rule in metric_rules.items():
                    if not isinstance(rule, dict):
                        raise FormalValidationError(f"criteria for {metric} must be an object")
                    value = _safe_number(comparison.get(metric), f"{pair_name}.{metric}")
                    metric_status, reason = _evaluate_threshold(metric, value, rule)
                    metric_results[metric] = {
                        "status": metric_status,
                        "delta": value,
                        "reason": reason,
                    }
                    if metric_status != "PASS":
                        outcome_status = "FAIL"
            outcome_rows.append(
                {
                    "name": outcome_name,
                    "status": outcome_status,
                    "off_run": off_name,
                    "on_run": on_name,
                    "metric_results": metric_results,
                }
            )

        execution_success = summary.get("status") == criteria["hard_gates"].get("aggregate_status")
        artifact_acceptance = _all_pass(hard_gates)
        safety_acceptance = _all_pass(safety_gates)
        performance_acceptance = all(row.get("status") == "PASS" for row in outcome_rows)
        closure = (
            bool(criteria["closure_policy"].get("requires_execution_success", True)) and execution_success
            and bool(criteria["closure_policy"].get("requires_artifact_acceptance", True)) and artifact_acceptance
            and bool(criteria["closure_policy"].get("requires_safety_acceptance", True)) and safety_acceptance
            and bool(criteria["closure_policy"].get("requires_all_performance_outcomes_pass", True)) and performance_acceptance
        )
        status = "PASS" if closure else "FAIL"
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "version": "PHOENIX Formal Validation Acceptance Report",
            "generated_at": _now_text(),
            "status": status,
            "formal_validation_closed": closure,
            "criteria_file": _rel(repository, resolve_within(repository, str(criteria_path))),
            "spec_file": _rel(repository, spec.path),
            "output_dir": _rel(repository, output_dir),
            "execution_success": execution_success,
            "artifact_acceptance": artifact_acceptance,
            "safety_acceptance": safety_acceptance,
            "performance_acceptance": performance_acceptance,
            "hard_gates": hard_gates,
            "safety_gates": safety_gates,
            "outcomes": outcome_rows,
        }
    except Exception as error:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "version": "PHOENIX Formal Validation Acceptance Report",
            "generated_at": _now_text(),
            "status": "FAIL",
            "formal_validation_closed": False,
            "criteria_file": str(criteria_path),
            "spec_file": str(spec_path),
            "output_dir": str(output_dir),
            "execution_success": False,
            "artifact_acceptance": False,
            "safety_acceptance": False,
            "performance_acceptance": False,
            "hard_gates": hard_gates,
            "safety_gates": safety_gates,
            "outcomes": outcome_rows,
            "error": f"{type(error).__name__}: {error}",
        }


class FormalValidationRunner:
    def __init__(
        self,
        root: Path | str | None = None,
        spec_path: Path | str = DEFAULT_SPEC_PATH,
    ) -> None:
        self.root = (Path(root) if root is not None else Path(__file__).resolve().parent.parent).resolve()
        self.spec = load_formal_validation_spec(self.root, spec_path)
        self.base_settings = load_settings(self.root, self.spec.base_config_path)
        self.base_config = _build_historical_validation_config(self.base_settings)
        self.base_config.validate()
        self.output_dir = self.spec.output_dir
        self.runs_dir = self.output_dir / DEFAULT_RUNS_DIR
        self.input_manifest_path = self.output_dir / DEFAULT_INPUT_MANIFEST_FILE
        self.summary_json_path = self.output_dir / DEFAULT_SUMMARY_JSON_FILE
        self.summary_csv_path = self.output_dir / DEFAULT_SUMMARY_CSV_FILE
        self.report_text_path = self.output_dir / DEFAULT_REPORT_TEXT_FILE
        self.dry_run_path = self.output_dir / DEFAULT_DRY_RUN_JSON_FILE
        self.worker_path = Path(__file__).resolve()
        self.launcher_path = self.root / "run_formal_validation.py"
        self._window_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._cache_tickers: set[str] | None = None
        self._input_manifest_sha256: str | None = None
        self._input_manifest: dict[str, Any] | None = None

    def _compute_input_manifest(self) -> tuple[dict[str, Any], str]:
        payload = _build_input_manifest_payload(self.root, self.spec, self.worker_path, self.launcher_path)
        finalized = _finalize_manifest(payload)
        return finalized, str(finalized["input_manifest_sha256"])

    def _ensure_input_manifest(self) -> tuple[dict[str, Any], str]:
        current_manifest, current_sha = self._compute_input_manifest()
        existing = _read_manifest_file(self.input_manifest_path)
        if existing is not None:
            existing_sha = str(existing.get("input_manifest_sha256", ""))
            if existing_sha and existing_sha != current_sha:
                # Refresh the baseline for a new validation session; run-state resume
                # still remains blocked by the per-run manifest checks below.
                self.output_dir.mkdir(parents=True, exist_ok=True)
                atomic_write(
                    self.input_manifest_path,
                    _canonical_json(current_manifest) + "\n",
                )
                self._input_manifest = current_manifest
                self._input_manifest_sha256 = current_sha
                return current_manifest, current_sha
            self._input_manifest = existing
            self._input_manifest_sha256 = existing_sha or current_sha
            return existing, self._input_manifest_sha256

        self.output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write(
            self.input_manifest_path,
            _canonical_json(current_manifest) + "\n",
        )
        self._input_manifest = current_manifest
        self._input_manifest_sha256 = current_sha
        return current_manifest, current_sha

    def _refresh_input_manifest_sha256(self) -> str:
        _, current_sha = self._compute_input_manifest()
        if self._input_manifest_sha256 is not None and current_sha != self._input_manifest_sha256:
            raise FormalValidationError(
                "Input manifest changed during the formal validation run; stop and restart from the beginning"
            )
        return current_sha

    def _run_spec_sha256(self, run_spec: FormalValidationRunSpec) -> str:
        return _run_spec_sha256(run_spec)

    def _run_identity_sha256(self, run_spec: FormalValidationRunSpec, input_manifest_sha256: str) -> str:
        return _run_identity_sha256(self._run_spec_sha256(run_spec), input_manifest_sha256)

    def _run_dir(self, run_spec: FormalValidationRunSpec) -> Path:
        return self.runs_dir / run_spec.name

    def _state_path(self, run_spec: FormalValidationRunSpec) -> Path:
        return self._run_dir(run_spec) / "manifest.json"

    def _run_log_path(self, run_spec: FormalValidationRunSpec) -> Path:
        return self._run_dir(run_spec) / "run.log"

    def _resolved_cache_tickers(self) -> set[str]:
        if self._cache_tickers is not None:
            return set(self._cache_tickers)
        input_manifest, _ = self._ensure_input_manifest()
        cache_tickers = _cache_ticker_set_from_manifest(input_manifest)
        self._cache_tickers = cache_tickers
        return set(cache_tickers)

    def _load_window_data(
        self,
        run_spec: FormalValidationRunSpec,
        input_manifest_sha256: str,
    ) -> dict[str, Any]:
        window_key = run_spec.window_key
        cached = self._window_cache.get(window_key)
        if cached is not None:
            return cached

        requested_start = pd.Timestamp(run_spec.requested_start).date()
        requested_end = pd.Timestamp(run_spec.requested_end).date()
        fetch_start_date = (
            pd.Timestamp(requested_start) - pd.offsets.BDay(self.base_config.minimum_history_sessions + DEFAULT_WINDOW_PAD)
        ).date()
        checked = datetime.now(JST)
        universe_df = _load_universe_from_csv(
            self.root,
            self.spec.universe_csv,
            enforce_nikkei225=bool(self.base_settings.get("enforce_nikkei225", True)),
            expected_ticker_count=int(
                self.base_settings.get("expected_ticker_count", EXPECTED_NIKKEI225_COUNT) or EXPECTED_NIKKEI225_COUNT
            ),
        )
        download_registry: set[tuple[str, date, date]] = set()
        fetched: list[tuple[dict[str, Any], Any]] = []
        for entry in universe_df.to_dict(orient="records"):
            outcome = fetch_ticker_history(
                self.root,
                entry["ticker"],
                fetch_start_date,
                requested_end,
                cache_dir=self.spec.cache_dir,
                as_of=checked,
                allow_network_fetch=False,
                download_registry=download_registry,
            )
            fetched.append((entry, outcome))

        histories = {entry["ticker"]: outcome.history for entry, outcome in fetched}
        prepared_histories = prepare_histories(histories, self.base_config)
        prepared_histories = {ticker: frame for ticker, frame in prepared_histories.items() if not frame.empty}
        if not prepared_histories:
            raise FormalValidationError(
                f"No cached histories are available for the requested window {run_spec.name}"
            )

        coverage_df = build_data_coverage(
            universe_df,
            histories,
            pd.Timestamp(requested_start),
            pd.Timestamp(requested_end),
        )
        membership_tickers = {str(ticker).strip().upper() for ticker in universe_df["ticker"].tolist()}
        cache_tickers = self._resolved_cache_tickers()
        membership_ticker_count = int(len(universe_df))
        cache_ticker_count = len(cache_tickers)
        simulation_ticker_count = int(len(prepared_histories))
        excluded_cache_ticker_count = int(len(cache_tickers - membership_tickers))
        window_data = {
            "requested_start": requested_start,
            "requested_end": requested_end,
            "fetch_start_date": fetch_start_date,
            "checked": checked.isoformat(timespec="seconds"),
            "universe_df": universe_df,
            "histories": histories,
            "prepared_histories": prepared_histories,
            "coverage_rows": _json_safe_records(coverage_df),
            "membership_ticker_count": membership_ticker_count,
            "cache_csv_ticker_count": cache_ticker_count,
            "simulation_ticker_count": simulation_ticker_count,
            "excluded_cache_ticker_count": excluded_cache_ticker_count,
        }
        self._window_cache[window_key] = window_data
        return window_data

    def _build_run_record(
        self,
        run_spec: FormalValidationRunSpec,
        input_manifest_sha256: str,
        *,
        status: str,
        resume_skipped: bool,
        performance: dict[str, Any] | None = None,
        formal_validation: dict[str, Any] | None = None,
        output_files: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        run_spec_sha256 = self._run_spec_sha256(run_spec)
        run_identity_sha256 = self._run_identity_sha256(run_spec, input_manifest_sha256)
        run_record = {
            "schema_version": RUN_SCHEMA_VERSION,
            "version": "PHOENIX Formal Validation 20Y",
            "generated_at": _now_text(),
            "run_name": run_spec.name,
            "requested_start": run_spec.requested_start,
            "requested_end": run_spec.requested_end,
            "market_breadth_filter_enabled": run_spec.market_breadth_filter_enabled,
            "status": status,
            "resume_skipped": bool(resume_skipped),
            "input_manifest_sha256": input_manifest_sha256,
            "run_spec_sha256": run_spec_sha256,
            "run_identity_sha256": run_identity_sha256,
            "performance": performance or {},
            "formal_validation": formal_validation or {},
            "output_files": output_files or {},
            "error": error,
        }
        return run_record

    def _run_output_paths(self, run_spec: FormalValidationRunSpec) -> dict[str, Path]:
        run_dir = self._run_dir(run_spec)
        return {
            "run_dir": run_dir,
            "summary_json": run_dir / "summary.json",
            "report_text": run_dir / "report.txt",
            "diagnostics_csv": run_dir / "diagnostics.csv",
            "annual_returns_csv": run_dir / "annual_returns.csv",
            "monthly_returns_csv": run_dir / "monthly_returns.csv",
            "data_coverage_csv": run_dir / "data_coverage.csv",
            "trades_csv": run_dir / "trades.csv",
            "equity_curve_csv": run_dir / "equity_curve.csv",
            "run_log": run_dir / "run.log",
            "state": run_dir / "manifest.json",
        }

    def _load_existing_run_record(
        self,
        run_spec: FormalValidationRunSpec,
        input_manifest_sha256: str,
    ) -> dict[str, Any] | None:
        state_path = self._state_path(run_spec)
        if not state_path.is_file():
            return None
        state = _load_json_file(state_path)
        if state.get("input_manifest_sha256") != input_manifest_sha256:
            raise FormalValidationError(
                f"Run {run_spec.name} cannot resume because the input manifest sha does not match"
            )
        if state.get("run_spec_sha256") != self._run_spec_sha256(run_spec):
            raise FormalValidationError(
                f"Run {run_spec.name} cannot resume because the run spec sha does not match"
            )
        if state.get("status") != "DONE":
            return None

        output_paths = self._run_output_paths(run_spec)
        summary_path = output_paths["summary_json"]
        if not summary_path.is_file():
            raise FormalValidationError(
                f"Run {run_spec.name} is marked DONE but its summary output is missing: {summary_path}"
            )
        summary = _load_json_file(summary_path)
        formal = summary.get("formal_validation", {})
        performance = summary.get("performance", {})
        return self._build_run_record(
            run_spec,
            input_manifest_sha256,
            status="DONE",
            resume_skipped=True,
            performance=performance,
            formal_validation=formal,
            output_files=summary.get("output_files", {}),
            error=None,
        )

    def _write_run_state(self, run_spec: FormalValidationRunSpec, state: dict[str, Any]) -> None:
        output_paths = self._run_output_paths(run_spec)
        output_paths["run_dir"].mkdir(parents=True, exist_ok=True)
        atomic_write(output_paths["state"], _canonical_json(state) + "\n")

    def _execute_run(
        self,
        run_spec: FormalValidationRunSpec,
        input_manifest_sha256: str,
        window_data: dict[str, Any],
    ) -> dict[str, Any]:
        output_paths = self._run_output_paths(run_spec)
        output_paths["run_dir"].mkdir(parents=True, exist_ok=True)
        state_path = output_paths["state"]
        existing = self._load_existing_run_record(run_spec, input_manifest_sha256)
        if existing is not None:
            return existing

        run_spec_sha256 = self._run_spec_sha256(run_spec)
        run_identity_sha256 = self._run_identity_sha256(run_spec, input_manifest_sha256)
        run_state = {
            "schema_version": RUN_SCHEMA_VERSION,
            "run_name": run_spec.name,
            "run_spec_sha256": run_spec_sha256,
            "input_manifest_sha256": input_manifest_sha256,
            "run_identity_sha256": run_identity_sha256,
            "status": "RUNNING",
            "started_at": _now_text(),
            "output_dir": _rel(self.root, output_paths["run_dir"]),
        }
        atomic_write(state_path, _canonical_json(run_state) + "\n")

        try:
            settings = _build_run_settings(self.base_settings, run_spec, output_paths["run_dir"])
            config = _build_historical_validation_config(settings)
            config.validate()

            prepared_histories = window_data["prepared_histories"]
            universe_df = window_data["universe_df"]
            requested_start = window_data["requested_start"]
            requested_end = window_data["requested_end"]

            result = simulate_validation(
                prepared_histories,
                universe_df,
                config,
                requested_start,
                requested_end,
            )
            performance = _summarize_simulation_result(result, float(config.initial_capital_yen))
            performance.update(_summarize_extra_metrics(result, float(config.initial_capital_yen)))
            formal_validation = {
                "membership_ticker_count": window_data["membership_ticker_count"],
                "cache_csv_ticker_count": window_data["cache_csv_ticker_count"],
                "simulation_ticker_count": window_data["simulation_ticker_count"],
                "excluded_cache_ticker_count": window_data["excluded_cache_ticker_count"],
            }
            report = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "version": "PHOENIX Formal Validation 20Y",
                "generated_at": _now_text(),
                "run_name": run_spec.name,
                "requested_start": run_spec.requested_start,
                "requested_end": run_spec.requested_end,
                "market_breadth_filter_enabled": run_spec.market_breadth_filter_enabled,
                "input_manifest_sha256": input_manifest_sha256,
                "run_spec_sha256": run_spec_sha256,
                "run_identity_sha256": run_identity_sha256,
                "initial_capital_yen": float(config.initial_capital_yen),
                "lot_size": int(config.lot_size),
                "fractional_shares": False,
                "ticker_count": int(len(universe_df)),
                "status": "SUCCESS",
                "actual_start_date": str(result.equity_curve["date"].iloc[0]) if not result.equity_curve.empty and "date" in result.equity_curve.columns else "",
                "actual_end_date": str(result.equity_curve["date"].iloc[-1]) if not result.equity_curve.empty and "date" in result.equity_curve.columns else "",
                "simulation_trading_days": int(len(result.equity_curve)),
                "rows": window_data["coverage_rows"],
                "performance": performance,
                "warnings": [
                    "No look-ahead bias is used: indicators are causal and entries are executed on the next session.",
                    "Network fetch is disabled; only cached history is eligible for the formal validation runner.",
                ],
                "safety": {
                    "no_rss": True,
                    "no_real_orders": True,
                    "orders_submitted": 0,
                    "live_trading_enabled": False,
                },
                "formal_validation": formal_validation,
            }
            save_outputs(self.root, settings, report, result)
            report_text = _build_formal_report_text(report)
            atomic_write(output_paths["report_text"], report_text)
            atomic_write(output_paths["run_log"], report_text)
            run_state.update(
                {
                    "status": "DONE",
                    "completed_at": _now_text(),
                    "summary_json": _rel(self.root, output_paths["summary_json"]),
                    "report_text": _rel(self.root, output_paths["report_text"]),
                    "run_log": _rel(self.root, output_paths["run_log"]),
                    "output_files": report.get("output_files", {}),
                }
            )
            atomic_write(state_path, _canonical_json(run_state) + "\n")
            return self._build_run_record(
                run_spec,
                input_manifest_sha256,
                status="DONE",
                resume_skipped=False,
                performance=performance,
                formal_validation=formal_validation,
                output_files=report.get("output_files", {}),
            )
        except Exception as error:
            error_text = f"{type(error).__name__}: {error}"
            trace = traceback.format_exc()
            failure_log = "\n".join(
                [
                    f"Run {run_spec.name} FAILED",
                    f"Started at: {run_state['started_at']}",
                    f"Error: {error_text}",
                    "",
                    trace,
                ]
            )
            atomic_write(output_paths["run_log"], failure_log)
            run_state.update(
                {
                    "status": "FAILED",
                    "completed_at": _now_text(),
                    "error": error_text,
                    "traceback": trace,
                    "run_log": _rel(self.root, output_paths["run_log"]),
                }
            )
            atomic_write(state_path, _canonical_json(run_state) + "\n")
            return self._build_run_record(
                run_spec,
                input_manifest_sha256,
                status="FAILED",
                resume_skipped=False,
                performance={},
                formal_validation={
                    "membership_ticker_count": window_data.get("membership_ticker_count", 0),
                    "cache_csv_ticker_count": window_data.get("cache_csv_ticker_count", 0),
                    "simulation_ticker_count": window_data.get("simulation_ticker_count", 0),
                    "excluded_cache_ticker_count": window_data.get("excluded_cache_ticker_count", 0),
                },
                output_files={"run_log": _rel(self.root, output_paths["run_log"])},
                error=error_text,
            )

    def _not_run_record(
        self,
        run_spec: FormalValidationRunSpec,
        input_manifest_sha256: str,
        reason: str,
    ) -> dict[str, Any]:
        return self._build_run_record(
            run_spec,
            input_manifest_sha256,
            status="NOT_RUN",
            resume_skipped=False,
            performance={},
            formal_validation={},
            output_files={},
            error=reason,
        )

    def _comparison_rows(self, run_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _comparison_rows_from_run_rows(run_rows)

    def _summary_from_run_rows(self, input_manifest_sha256: str, run_rows: list[dict[str, Any]]) -> dict[str, Any]:
        status = "SUCCESS"
        if any(row.get("status") == "FAILED" for row in run_rows):
            status = "FAILED"
        elif any(row.get("status") == "NOT_RUN" for row in run_rows):
            status = "PARTIAL"
        summary = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "version": "PHOENIX Formal Validation 20Y",
            "generated_at": _now_text(),
            "status": status,
            "input_manifest_sha256": input_manifest_sha256,
            "output_dir": _rel(self.root, self.output_dir),
            "run_count": len(run_rows),
            "runs": run_rows,
            "comparisons": self._comparison_rows(run_rows),
            "warnings": [
                "Network fetch is disabled for the formal validation runner.",
                "Resume is only allowed when both the run spec and the input manifest sha match.",
            ],
        }
        return summary

    def _write_summary_artifacts(self, summary: dict[str, Any]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        summary_json = _canonical_json(summary) + "\n"
        atomic_write(self.summary_json_path, summary_json)
        atomic_write(self.report_text_path, _build_aggregate_report_text(summary))
        csv_rows = [_flatten_run_for_csv(run) for run in summary.get("runs", [])]
        pd.DataFrame(csv_rows).to_csv(self.summary_csv_path, index=False, encoding="utf-8-sig")

    def dry_run(self) -> dict[str, Any]:
        input_manifest, input_manifest_sha256 = self._ensure_input_manifest()
        first_run = self.spec.runs[0]
        window_data = self._load_window_data(first_run, input_manifest_sha256)
        dry_run = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "version": "PHOENIX Formal Validation 20Y",
            "generated_at": _now_text(),
            "status": "DRY_RUN",
            "input_manifest_file": _rel(self.root, self.input_manifest_path),
            "input_manifest_sha256": input_manifest_sha256,
            "spec_file": _rel(self.root, self.spec.path),
            "spec_sha256": _sha256_file(self.spec.path),
            "prepared_run": first_run.to_manifest_dict(),
            "prepared_window": {
                "requested_start": first_run.requested_start,
                "requested_end": first_run.requested_end,
                "membership_ticker_count": window_data["membership_ticker_count"],
                "cache_csv_ticker_count": window_data["cache_csv_ticker_count"],
                "simulation_ticker_count": window_data["simulation_ticker_count"],
                "excluded_cache_ticker_count": window_data["excluded_cache_ticker_count"],
            },
            "planned_runs": [run.to_manifest_dict() for run in self.spec.runs],
            "notes": [
                "Dry-run stops after input-manifest validation and a single window preparation pass.",
                "No simulation is executed in dry-run mode.",
            ],
        }
        atomic_write(self.dry_run_path, _canonical_json(dry_run) + "\n")
        return dry_run

    def run(self) -> dict[str, Any]:
        _, input_manifest_sha256 = self._ensure_input_manifest()
        run_rows: list[dict[str, Any]] = []
        failed_run_name: str | None = None

        for run_spec in self.spec.runs:
            current_sha = self._refresh_input_manifest_sha256()
            if current_sha != input_manifest_sha256:
                raise FormalValidationError(
                    "Input manifest changed while the formal validation runner was executing"
                )
            if failed_run_name is not None:
                run_rows.append(
                    self._not_run_record(
                        run_spec,
                        input_manifest_sha256,
                        f"Stopped after failure in {failed_run_name}",
                    )
                )
                continue

            window_data = self._load_window_data(run_spec, input_manifest_sha256)
            record = self._execute_run(run_spec, input_manifest_sha256, window_data)
            run_rows.append(record)
            if record.get("status") == "FAILED":
                failed_run_name = run_spec.name if self.spec.stop_on_fail else None
                if self.spec.stop_on_fail:
                    continue

        summary = self._summary_from_run_rows(input_manifest_sha256, run_rows)
        self._write_summary_artifacts(summary)
        return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PHOENIX formal validation pipeline.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_SPEC_PATH),
        help="Path to config/formal_validation_runs.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the formal validation inputs and prepare one window without running simulations.",
    )
    parser.add_argument(
        "--acceptance-only",
        action="store_true",
        help="Evaluate existing formal validation artifacts without running simulations.",
    )
    parser.add_argument(
        "--acceptance-criteria",
        default=str(DEFAULT_ACCEPTANCE_CRITERIA_PATH),
        help="Path to config/formal_validation_acceptance_criteria.json",
    )
    args = parser.parse_args(argv)

    try:
        if args.acceptance_only:
            result = evaluate_formal_validation_acceptance(
                spec_path=args.config,
                criteria_path=args.acceptance_criteria,
            )
            print(_canonical_json(result))
            return 0 if result.get("status") == "PASS" else 1
        runner = FormalValidationRunner(spec_path=args.config)
        if args.dry_run:
            result = runner.dry_run()
            print(_canonical_json(result))
        else:
            result = runner.run()
            print(_canonical_json(result))
        return 0
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
