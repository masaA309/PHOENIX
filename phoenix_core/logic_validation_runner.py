from __future__ import annotations

import argparse
import hashlib
import json
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phoenix_core.historical_validation_20y import (  # type: ignore
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


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_CONFIG_PATH = Path("config/v7_historical_validation_risk_v2_quick.json")
DEFAULT_OUTPUT_DIR = Path("reports/logic_validation")
DEFAULT_REQUESTED_START = "2022-02-01"
DEFAULT_REQUESTED_END = "2026-08-14"
DEFAULT_AS_OF = datetime(2026, 8, 14, 16, 0, tzinfo=JST)
DEFAULT_CONCENTRATION_INPUTS = (
    Path("reports/formal_validation/runs/P1_ON/trades.csv"),
    Path("reports/formal_validation/runs/P2_ON/trades.csv"),
)
DEFAULT_RUNS_DIR = "runs"
DEFAULT_PLAN_FILE = "dry_run.json"
DEFAULT_SUMMARY_FILE = "summary.json"
DEFAULT_REPORT_FILE = "report.txt"
DEFAULT_SUMMARY_CSV_FILE = "summary.csv"
DEFAULT_DRY_RUN_TEXT_FILE = "dry_run.txt"
DEFAULT_CONFIG_FILE = "config.json"
DEFAULT_MANIFEST_FILE = "manifest.json"
DEFAULT_TICKER_PROFIT_FILE = "ticker_profit.csv"
MANIFEST_SCHEMA_VERSION = 1
RUNNER_VERSION = "PHOENIX Logic Validation Risk v2"


class LogicValidationError(RuntimeError):
    pass


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


@dataclass(frozen=True, slots=True)
class LogicValidationCase:
    group: str
    name: str
    slug: str
    kind: str
    breadth_threshold: float | None = None
    bear_cap: float | None = None
    slippage_multiplier: float | None = None

    def to_manifest_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_case_specs() -> tuple[LogicValidationCase, ...]:
    cases: list[LogicValidationCase] = []

    breadth_values = (0.35, 0.40, 0.45)
    bear_caps = (0.65, 0.70, 0.75)
    for breadth in breadth_values:
        for cap in bear_caps:
            slug = f"A_b{int(round(breadth * 100)):02d}_c{int(round(cap * 100)):02d}"
            cases.append(
                LogicValidationCase(
                    group="A",
                    name=f"breadth_{breadth:.2f}_cap_{cap:.2f}",
                    slug=slug,
                    kind="simulation",
                    breadth_threshold=breadth,
                    bear_cap=cap,
                )
            )

    for multiplier in (1.0, 2.0, 3.0):
        slug = f"B_slip_{int(multiplier)}x"
        cases.append(
            LogicValidationCase(
                group="B",
                name=f"slippage_{int(multiplier)}x",
                slug=slug,
                kind="simulation",
                slippage_multiplier=multiplier,
            )
        )

    cases.append(
        LogicValidationCase(
            group="C",
            name="concentration",
            slug="C_concentration",
            kind="concentration",
        )
    )
    return tuple(cases)


def _base_settings(root: Path, base_config_path: Path) -> tuple[dict[str, Any], str]:
    settings = load_settings(root, base_config_path)
    if settings.get("allow_network_fetch", True):
        settings["allow_network_fetch"] = False
    config = _build_historical_validation_config(settings)
    config.validate()
    base_config_sha256 = _sha256_file(resolve_within(root, str(base_config_path)))
    return settings, base_config_sha256


def _case_dir(output_root: Path, case: LogicValidationCase) -> Path:
    return output_root / DEFAULT_RUNS_DIR / case.slug


def _case_config_path(output_root: Path, case: LogicValidationCase) -> Path:
    return _case_dir(output_root, case) / DEFAULT_CONFIG_FILE


def _case_summary_path(output_root: Path, case: LogicValidationCase) -> Path:
    return _case_dir(output_root, case) / DEFAULT_SUMMARY_FILE


def _case_report_path(output_root: Path, case: LogicValidationCase) -> Path:
    return _case_dir(output_root, case) / DEFAULT_REPORT_FILE


def _case_manifest_path(output_root: Path, case: LogicValidationCase) -> Path:
    return _case_dir(output_root, case) / DEFAULT_MANIFEST_FILE


def _case_ticker_profit_path(output_root: Path) -> Path:
    return output_root / DEFAULT_TICKER_PROFIT_FILE


def _prepare_universe_and_histories(
    root: Path,
    base_settings: dict[str, Any],
    requested_start: str,
    requested_end: str,
    as_of: datetime,
) -> dict[str, Any]:
    config = _build_historical_validation_config(base_settings)
    requested_start_ts = pd.Timestamp(requested_start).normalize()
    requested_end_ts = pd.Timestamp(requested_end).normalize()
    fetch_start_date = (
        requested_start_ts - pd.offsets.BDay(config.minimum_history_sessions + 20)
    ).date()

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
    available_histories: list[pd.DataFrame] = []
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
        if not outcome.history.empty:
            available_histories.append(outcome.history)

    histories = {entry["ticker"]: outcome.history for entry, outcome in fetched}
    prepared_histories = prepare_histories(histories, config)
    coverage_df = build_data_coverage(
        universe_df,
        histories,
        requested_start_ts,
        requested_end_ts,
    )
    coverage_rows = coverage_df.to_dict(orient="records")
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
        "coverage_rows": coverage_rows,
        "membership_ticker_count": int(len(universe_df)),
        "cache_csv_ticker_count": int(len(cache_tickers)),
        "simulation_ticker_count": int(sum(1 for frame in prepared_histories.values() if not frame.empty)),
        "excluded_cache_ticker_count": int(len(cache_tickers - membership_tickers)),
    }


def _case_settings(
    base_settings: dict[str, Any],
    case: LogicValidationCase,
    case_dir: Path,
    requested_start: str,
    requested_end: str,
    base_slippage_rate: float,
) -> dict[str, Any]:
    settings = dict(base_settings)
    settings.update(
        {
            "requested_start": requested_start,
            "requested_end": requested_end,
            "allow_network_fetch": False,
            "market_breadth_filter_enabled": case.group in {"A", "B"},
            "market_breadth_bear_threshold": (
                case.breadth_threshold
                if case.breadth_threshold is not None
                else settings.get("market_breadth_bear_threshold", 0.40)
            ),
            "market_breadth_bear_max_total_invested_pct": (
                case.bear_cap
                if case.bear_cap is not None
                else settings.get("market_breadth_bear_max_total_invested_pct", 0.70)
            ),
            "slippage_rate": (
                round(base_slippage_rate * case.slippage_multiplier, 10)
                if case.slippage_multiplier is not None
                else float(settings.get("slippage_rate", 0.0005))
            ),
            "output_dir": str(case_dir),
            "report_json": str(case_dir / DEFAULT_SUMMARY_FILE),
            "report_text": str(case_dir / DEFAULT_REPORT_FILE),
            "annual_returns_csv": str(case_dir / "annual_returns.csv"),
            "monthly_returns_csv": str(case_dir / "monthly_returns.csv"),
            "coverage_csv": str(case_dir / "data_coverage.csv"),
            "data_coverage_csv": str(case_dir / "data_coverage.csv"),
            "diagnostics_csv": str(case_dir / "diagnostics.csv"),
            "trades_csv": str(case_dir / "trades.csv"),
            "equity_curve_csv": str(case_dir / "equity_curve.csv"),
            "benchmark_enabled": bool(settings.get("benchmark_enabled", True)),
            "no_rss": True,
            "no_real_orders": True,
            "live_trading_enabled": False,
            "orders_submitted": 0,
        }
    )
    return settings


def _case_identity(
    root: Path,
    base_config_sha256: str,
    case: LogicValidationCase,
    settings: dict[str, Any],
) -> tuple[str, str]:
    payload = {
        "base_config_sha256": base_config_sha256,
        "case": case.to_manifest_dict(),
        "settings": {
            "requested_start": settings.get("requested_start"),
            "requested_end": settings.get("requested_end"),
            "allow_network_fetch": settings.get("allow_network_fetch"),
            "market_breadth_filter_enabled": settings.get("market_breadth_filter_enabled"),
            "market_breadth_bear_threshold": settings.get("market_breadth_bear_threshold"),
            "market_breadth_bear_max_total_invested_pct": settings.get("market_breadth_bear_max_total_invested_pct"),
            "slippage_rate": settings.get("slippage_rate"),
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


def _can_resume_case(
    case: LogicValidationCase,
    manifest_path: Path,
    summary_path: Path,
    expected_identity_sha256: str,
) -> bool:
    manifest = _load_manifest(manifest_path)
    if manifest is None:
        return False
    if manifest.get("case_name") != case.name:
        return False
    if manifest.get("case_identity_sha256") != expected_identity_sha256:
        return False
    if manifest.get("status") != "DONE":
        return False
    if not summary_path.is_file():
        return False
    return True


def _write_case_manifest(
    manifest_path: Path,
    *,
    case: LogicValidationCase,
    base_config_path: Path,
    base_config_sha256: str,
    case_identity_sha256: str,
    status: str,
    resume_skipped: bool,
    output_files: dict[str, Any],
    error: str | None = None,
) -> None:
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "case_group": case.group,
        "case_name": case.name,
        "case_slug": case.slug,
        "case_kind": case.kind,
        "case": case.to_manifest_dict(),
        "base_config_file": _rel(ROOT, base_config_path),
        "base_config_sha256": base_config_sha256,
        "case_identity_sha256": case_identity_sha256,
        "status": status,
        "resume_skipped": resume_skipped,
        "output_files": output_files,
        "error": error,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(manifest_path, manifest)


def _build_simulation_report(
    *,
    case: LogicValidationCase,
    base_config_path: Path,
    base_config_sha256: str,
    case_identity_sha256: str,
    case_settings: dict[str, Any],
    universe_df: pd.DataFrame,
    coverage_rows: list[dict[str, Any]],
    result: Any,
    performance: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    output_files = {
        "summary_json": case_settings["report_json"],
        "report_text": case_settings["report_text"],
        "annual_returns_csv": case_settings["annual_returns_csv"],
        "monthly_returns_csv": case_settings["monthly_returns_csv"],
        "data_coverage_csv": case_settings["data_coverage_csv"],
        "diagnostics_csv": case_settings["diagnostics_csv"],
        "trades_csv": case_settings["trades_csv"],
        "equity_curve_csv": case_settings["equity_curve_csv"],
    }
    if case_settings.get("market_breadth_filter_enabled", False) and not result.risk_v2_research.empty:
        output_files["risk_v2_research_csv"] = str(Path(case_settings["output_dir"]) / "risk_v2_research.csv")

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "case_group": case.group,
        "case_name": case.name,
        "case_slug": case.slug,
        "case_kind": case.kind,
        "requested_start": str(case_settings["requested_start"]),
        "requested_end": str(case_settings["requested_end"]),
        "input_manifest_sha256": case_identity_sha256,
        "base_config_file": _rel(ROOT, base_config_path),
        "base_config_sha256": base_config_sha256,
        "initial_capital_yen": float(case_settings["initial_capital_yen"]),
        "lot_size": int(case_settings["lot_size"]),
        "fractional_shares": False,
        "ticker_count": int(len(universe_df)),
        "status": "SUCCESS",
        "actual_start_date": str(result.equity_curve["date"].iloc[0]) if not result.equity_curve.empty else "",
        "actual_end_date": str(result.equity_curve["date"].iloc[-1]) if not result.equity_curve.empty else "",
        "simulation_trading_days": int(len(result.equity_curve)),
        "rows": coverage_rows,
        "performance": performance,
        "warnings": [
            "Network fetch is disabled for logic validation.",
            "Risk v2 parameters are varied only through the runner; the underlying historical validation engine is unchanged.",
        ],
        "safety": {
            "no_rss": True,
            "no_real_orders": True,
            "orders_submitted": 0,
            "live_trading_enabled": False,
        },
        "formal_validation": {
            "membership_ticker_count": context["membership_ticker_count"],
            "cache_csv_ticker_count": context["cache_csv_ticker_count"],
            "simulation_ticker_count": context["simulation_ticker_count"],
            "excluded_cache_ticker_count": context["excluded_cache_ticker_count"],
        },
        "validation": {
            "market_breadth_filter_enabled": bool(case_settings.get("market_breadth_filter_enabled", False)),
            "market_breadth_bear_threshold": case_settings.get("market_breadth_bear_threshold"),
            "market_breadth_bear_max_total_invested_pct": case_settings.get("market_breadth_bear_max_total_invested_pct"),
            "slippage_rate": case_settings.get("slippage_rate"),
        },
        "output_files": output_files,
    }


def _render_case_report(report: dict[str, Any]) -> str:
    performance = report.get("performance", {})
    validation = report.get("validation", {})
    lines = [
        "=" * 88,
        f"{report.get('version', RUNNER_VERSION)}",
        "=" * 88,
        f"Case             : {report.get('case_name', '')}",
        f"Group            : {report.get('case_group', '')}",
        f"Requested period : {report.get('requested_start', '')} -> {report.get('requested_end', '')}",
        f"Base config      : {report.get('base_config_file', '')}",
        f"Market breadth   : {validation.get('market_breadth_filter_enabled', False)}",
        f"Breadth threshold: {validation.get('market_breadth_bear_threshold', '')}",
        f"BEAR cap         : {validation.get('market_breadth_bear_max_total_invested_pct', '')}",
        f"Slippage rate    : {validation.get('slippage_rate', '')}",
        "",
        "Performance",
        "-" * 88,
        f"Final equity     : {performance.get('final_equity_yen', 0):,.0f} yen",
        f"CAGR             : {performance.get('CAGR', performance.get('cagr_pct', 0)):+.2f}%",
        f"Profit factor    : {performance.get('profit_factor', 0):.3f}",
        f"Max drawdown     : {performance.get('max_drawdown', performance.get('max_drawdown_pct', 0)):.2f}%",
        f"Trade count      : {performance.get('trade_count', 0)}",
        f"Win rate         : {performance.get('win_rate', performance.get('win_rate_pct', 0)):.2f}%",
        "",
        "Safety",
        "-" * 88,
        f"Mode             : PAPER",
        f"Orders submitted : 0",
        f"Network fetch    : disabled",
        "",
        "Output files",
        "-" * 88,
    ]
    for key, label in (
        ("summary_json", "Summary JSON"),
        ("report_text", "Report text"),
        ("annual_returns_csv", "Annual CSV"),
        ("monthly_returns_csv", "Monthly CSV"),
        ("data_coverage_csv", "Coverage CSV"),
        ("diagnostics_csv", "Diagnostics CSV"),
        ("trades_csv", "Trades CSV"),
        ("equity_curve_csv", "Equity CSV"),
        ("risk_v2_research_csv", "Risk v2 research"),
    ):
        path = report.get("output_files", {}).get(key)
        if path:
            lines.append(f"{label:<16}: {path}")
    return "\n".join(lines) + "\n"


def _execute_simulation_case(
    *,
    root: Path,
    base_settings: dict[str, Any],
    base_config_path: Path,
    base_config_sha256: str,
    context: dict[str, Any],
    case: LogicValidationCase,
    resume: bool,
) -> dict[str, Any]:
    case_dir = _case_dir(root / DEFAULT_OUTPUT_DIR, case)
    case_dir.mkdir(parents=True, exist_ok=True)
    case_settings = _case_settings(
        base_settings,
        case,
        case_dir,
        DEFAULT_REQUESTED_START,
        DEFAULT_REQUESTED_END,
        _safe_float(base_settings.get("slippage_rate", 0.0005), 0.0005),
    )
    case_config = _build_historical_validation_config(case_settings)
    case_config.validate()
    case_identity_sha256, canonical = _case_identity(root, base_config_sha256, case, case_settings)
    config_path = _case_config_path(root / DEFAULT_OUTPUT_DIR, case)
    summary_path = _case_summary_path(root / DEFAULT_OUTPUT_DIR, case)
    report_path = _case_report_path(root / DEFAULT_OUTPUT_DIR, case)
    manifest_path = _case_manifest_path(root / DEFAULT_OUTPUT_DIR, case)

    if resume and _can_resume_case(case, manifest_path, summary_path, case_identity_sha256):
        summary = _read_json(summary_path)
        performance = summary.get("performance", {})
        return {
            "case_group": case.group,
            "case_name": case.name,
            "case_slug": case.slug,
            "case_kind": case.kind,
            "status": "DONE",
            "resume_skipped": True,
            "output_dir": _rel(root, case_dir),
            "performance": performance,
            "validation": summary.get("validation", {}),
            "output_files": summary.get("output_files", {}),
            "summary_json": _rel(root, summary_path),
        }

    _write_json(config_path, {"historical_validation_20y": case_settings})
    result = simulate_validation(
        context["prepared_histories"],
        context["universe_df"],
        case_config,
        context["requested_start"],
        context["requested_end"],
    )
    performance = _summarize_simulation_result(result, float(case_settings["initial_capital_yen"]))
    report = _build_simulation_report(
        case=case,
        base_config_path=base_config_path,
        base_config_sha256=base_config_sha256,
        case_identity_sha256=case_identity_sha256,
        case_settings=case_settings,
        universe_df=context["universe_df"],
        coverage_rows=context["coverage_rows"],
        result=result,
        performance=performance,
        context=context,
    )
    save_outputs(root, case_settings, report, result)
    report_text = _render_case_report(report)
    atomic_write(report_path, report_text)
    _write_case_manifest(
        manifest_path,
        case=case,
        base_config_path=base_config_path,
        base_config_sha256=base_config_sha256,
        case_identity_sha256=case_identity_sha256,
        status="DONE",
        resume_skipped=False,
        output_files=report["output_files"],
    )
    return {
        "case_group": case.group,
        "case_name": case.name,
        "case_slug": case.slug,
        "case_kind": case.kind,
        "status": "DONE",
        "resume_skipped": False,
        "output_dir": _rel(root, case_dir),
        "performance": performance,
        "validation": report["validation"],
        "output_files": report["output_files"],
        "summary_json": _rel(root, summary_path),
    }


def _load_trade_frames(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for rel_path in DEFAULT_CONCENTRATION_INPUTS:
        path = resolve_within(root, str(rel_path))
        if not path.is_file():
            raise FileNotFoundError(f"Concentration input not found: {path}")
        frame = pd.read_csv(path)
        required = {"ticker", "profit_yen"}
        if not required.issubset(frame.columns):
            raise ValueError(f"Concentration input missing required columns: {path}")
        if "company_name" not in frame.columns:
            frame["company_name"] = frame["ticker"]
        frames.append(frame)
    if not frames:
        raise LogicValidationError("No concentration inputs were found")
    combined = pd.concat(frames, ignore_index=True)
    combined["ticker"] = combined["ticker"].astype(str)
    combined["company_name"] = combined["company_name"].fillna(combined["ticker"]).astype(str)
    combined["profit_yen"] = combined["profit_yen"].astype(float)
    return combined


def _concentration_summary(root: Path, output_dir: Path) -> dict[str, Any]:
    combined = _load_trade_frames(root)
    ticker_profit = (
        combined.groupby("ticker", as_index=False)
        .agg(
            company_name=("company_name", "first"),
            total_profit_yen=("profit_yen", "sum"),
            trade_count=("profit_yen", "size"),
        )
        .sort_values(["total_profit_yen", "ticker"], ascending=[False, True])
        .reset_index(drop=True)
    )
    total_profit = _safe_float(ticker_profit["total_profit_yen"].sum(), 0.0)
    metrics: dict[str, Any] = {
        "total_profit_yen": round(total_profit, 2),
        "profitable_ticker_count": int((ticker_profit["total_profit_yen"] > 0).sum()),
        "losing_ticker_count": int((ticker_profit["total_profit_yen"] < 0).sum()),
        "flat_ticker_count": int((ticker_profit["total_profit_yen"] == 0).sum()),
    }

    for n in (1, 5, 10):
        top_profit = _safe_float(ticker_profit.head(n)["total_profit_yen"].sum(), 0.0)
        metrics[f"top{n}_profit_yen"] = round(top_profit, 2)
        metrics[f"top{n}_contribution_pct"] = (
            round(top_profit / total_profit * 100.0, 6) if total_profit != 0 else None
        )
        metrics[f"top{n}_profit_excluding_yen"] = round(total_profit - top_profit, 2)

    ticker_profit_path = _case_ticker_profit_path(output_dir)
    ticker_profit_path.parent.mkdir(parents=True, exist_ok=True)
    ticker_profit.to_csv(ticker_profit_path, index=False, encoding="utf-8-sig")

    report = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "case_group": "C",
        "case_name": "concentration",
        "case_slug": "C_concentration",
        "case_kind": "concentration",
        "status": "SUCCESS",
        "inputs": [
            _rel(root, resolve_within(root, str(path)))
            for path in DEFAULT_CONCENTRATION_INPUTS
        ],
        "metrics": metrics,
        "ticker_profit_csv": _rel(root, ticker_profit_path),
        "ticker_profit_rows": ticker_profit.to_dict(orient="records"),
    }

    report_path = output_dir / "concentration_report.txt"
    lines = [
        "=" * 88,
        f"{RUNNER_VERSION} - concentration",
        "=" * 88,
        f"Inputs           : {', '.join(report['inputs'])}",
        f"Total profit     : {metrics['total_profit_yen']:,.2f} yen",
        f"Top1 contribution: {metrics['top1_contribution_pct'] if metrics['top1_contribution_pct'] is not None else 'n/a'}%",
        f"Top5 contribution: {metrics['top5_contribution_pct'] if metrics['top5_contribution_pct'] is not None else 'n/a'}%",
        f"Top10 contribution: {metrics['top10_contribution_pct'] if metrics['top10_contribution_pct'] is not None else 'n/a'}%",
        f"Profitable tickers: {metrics['profitable_ticker_count']}",
        f"Losing tickers    : {metrics['losing_ticker_count']}",
        "",
        "Top 10 tickers by total profit",
        "-" * 88,
    ]
    for row in ticker_profit.head(10).to_dict(orient="records"):
        lines.append(
            f"{row['ticker']:<8} {row['company_name']:<24} {row['total_profit_yen']:>12,.2f} yen"
        )
    atomic_write(report_path, "\n".join(lines) + "\n")
    summary_path = output_dir / "concentration_summary.json"
    _write_json(summary_path, report)
    manifest_path = output_dir / DEFAULT_MANIFEST_FILE
    _write_json(
        manifest_path,
        {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "runner_version": RUNNER_VERSION,
            "generated_at": _now_text(),
            "case_group": "C",
            "case_name": "concentration",
            "case_slug": "C_concentration",
            "case_kind": "concentration",
            "status": "DONE",
            "resume_skipped": False,
            "output_files": {
                "summary_json": _rel(root, summary_path),
                "report_text": _rel(root, report_path),
                "ticker_profit_csv": _rel(root, ticker_profit_path),
            },
            "error": None,
        },
    )
    return {
        "case_group": "C",
        "case_name": "concentration",
        "case_slug": "C_concentration",
        "case_kind": "concentration",
        "status": "DONE",
        "resume_skipped": False,
        "output_dir": _rel(root, output_dir),
        "metrics": metrics,
        "output_files": {
            "summary_json": _rel(root, summary_path),
            "report_text": _rel(root, report_path),
            "ticker_profit_csv": _rel(root, ticker_profit_path),
        },
        "summary_json": _rel(root, summary_path),
    }


def _build_summary_csv_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        performance = case.get("performance", {})
        metrics = case.get("metrics", {})
        row = {
            "case_group": case.get("case_group", ""),
            "case_name": case.get("case_name", ""),
            "case_slug": case.get("case_slug", ""),
            "case_kind": case.get("case_kind", ""),
            "status": case.get("status", ""),
            "resume_skipped": bool(case.get("resume_skipped", False)),
            "output_dir": case.get("output_dir", ""),
        }
        row.update(
            {
                "final_equity_yen": performance.get("final_equity_yen"),
                "CAGR": performance.get("CAGR", performance.get("cagr_pct")),
                "profit_factor": performance.get("profit_factor"),
                "max_drawdown": performance.get("max_drawdown", performance.get("max_drawdown_pct")),
                "trade_count": performance.get("trade_count"),
                "win_rate": performance.get("win_rate", performance.get("win_rate_pct")),
                "total_profit_yen": metrics.get("total_profit_yen"),
                "top1_contribution_pct": metrics.get("top1_contribution_pct"),
                "top5_contribution_pct": metrics.get("top5_contribution_pct"),
                "top10_contribution_pct": metrics.get("top10_contribution_pct"),
                "profitable_ticker_count": metrics.get("profitable_ticker_count"),
                "losing_ticker_count": metrics.get("losing_ticker_count"),
            }
        )
        rows.append(row)
    return rows


def _build_top_level_report(base_config_path: Path, requested_start: str, requested_end: str, cases: list[dict[str, Any]]) -> str:
    lines = [
        "=" * 96,
        RUNNER_VERSION,
        "=" * 96,
        f"Base config      : {base_config_path.as_posix()}",
        f"Requested period : {requested_start} -> {requested_end}",
        "",
        "A. Parameter robustness",
        "-" * 96,
    ]
    for case in cases:
        if case.get("case_group") != "A":
            continue
        perf = case.get("performance", {})
        lines.append(
            f"{case.get('case_name', ''):<22} "
            f"EQ={perf.get('final_equity_yen', 0):,.0f} "
            f"CAGR={perf.get('CAGR', perf.get('cagr_pct', 0)):+.2f}% "
            f"PF={perf.get('profit_factor', 0):.3f} "
            f"MaxDD={perf.get('max_drawdown', perf.get('max_drawdown_pct', 0)):.2f}% "
            f"Trades={perf.get('trade_count', 0)} "
            f"WinRate={perf.get('win_rate', perf.get('win_rate_pct', 0)):.2f}%"
        )
    lines.extend(
        [
            "",
            "B. Slippage stress",
            "-" * 96,
        ]
    )
    for case in cases:
        if case.get("case_group") != "B":
            continue
        perf = case.get("performance", {})
        lines.append(
            f"{case.get('case_name', ''):<22} "
            f"EQ={perf.get('final_equity_yen', 0):,.0f} "
            f"CAGR={perf.get('CAGR', perf.get('cagr_pct', 0)):+.2f}% "
            f"PF={perf.get('profit_factor', 0):.3f} "
            f"MaxDD={perf.get('max_drawdown', perf.get('max_drawdown_pct', 0)):.2f}% "
            f"Trades={perf.get('trade_count', 0)}"
        )
    lines.extend(
        [
            "",
            "C. Concentration",
            "-" * 96,
        ]
    )
    concentration = next((case for case in cases if case.get("case_group") == "C"), {})
    metrics = concentration.get("metrics", {})
    lines.extend(
        [
            f"Total profit       : {metrics.get('total_profit_yen', 0):,.2f} yen",
            f"Top1 contribution  : {metrics.get('top1_contribution_pct') if metrics.get('top1_contribution_pct') is not None else 'n/a'}%",
            f"Top5 contribution  : {metrics.get('top5_contribution_pct') if metrics.get('top5_contribution_pct') is not None else 'n/a'}%",
            f"Top10 contribution : {metrics.get('top10_contribution_pct') if metrics.get('top10_contribution_pct') is not None else 'n/a'}%",
            f"Profitable tickers : {metrics.get('profitable_ticker_count', 0)}",
            f"Losing tickers     : {metrics.get('losing_ticker_count', 0)}",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_dry_run_payload(
    *,
    root: Path,
    base_config_path: Path,
    base_config_sha256: str,
    base_settings: dict[str, Any],
    requested_start: str,
    requested_end: str,
    cases: Iterable[LogicValidationCase],
) -> dict[str, Any]:
    checks = {
        "base_config_exists": resolve_within(root, str(base_config_path)).is_file(),
        "market_cache_dir_exists": resolve_within(root, str(base_settings.get("cache_dir", "data/market_cache"))).is_dir(),
        "universe_csv_exists": resolve_within(root, str(base_settings.get("universe_csv", "data/nikkei225_membership_20y.csv"))).is_file(),
        "concentration_input_p1_exists": resolve_within(root, str(DEFAULT_CONCENTRATION_INPUTS[0])).is_file(),
        "concentration_input_p2_exists": resolve_within(root, str(DEFAULT_CONCENTRATION_INPUTS[1])).is_file(),
    }
    case_plans: list[dict[str, Any]] = []
    for case in cases:
        if case.kind == "simulation":
            case_dir = _case_dir(root / DEFAULT_OUTPUT_DIR, case)
            settings = _case_settings(
                base_settings,
                case,
                case_dir,
                requested_start,
                requested_end,
                _safe_float(base_settings.get("slippage_rate", 0.0005), 0.0005),
            )
            case_config = _build_historical_validation_config(settings)
            case_config.validate()
            case_identity_sha256, _ = _case_identity(root, base_config_sha256, case, settings)
            case_plans.append(
                {
                    "case_group": case.group,
                    "case_name": case.name,
                    "case_slug": case.slug,
                    "case_kind": case.kind,
                    "output_dir": _rel(root, case_dir),
                    "config_file": _rel(root, _case_config_path(root / DEFAULT_OUTPUT_DIR, case)),
                    "manifest_file": _rel(root, _case_manifest_path(root / DEFAULT_OUTPUT_DIR, case)),
                    "summary_file": _rel(root, _case_summary_path(root / DEFAULT_OUTPUT_DIR, case)),
                    "case_identity_sha256": case_identity_sha256,
                    "settings": {
                        "market_breadth_filter_enabled": settings.get("market_breadth_filter_enabled"),
                        "market_breadth_bear_threshold": settings.get("market_breadth_bear_threshold"),
                        "market_breadth_bear_max_total_invested_pct": settings.get("market_breadth_bear_max_total_invested_pct"),
                        "slippage_rate": settings.get("slippage_rate"),
                    },
                }
            )
        else:
            case_dir = root / DEFAULT_OUTPUT_DIR
            case_plans.append(
                {
                    "case_group": case.group,
                    "case_name": case.name,
                    "case_slug": case.slug,
                    "case_kind": case.kind,
                    "output_dir": _rel(root, case_dir),
                    "summary_file": _rel(root, case_dir / "concentration_summary.json"),
                    "report_file": _rel(root, case_dir / "concentration_report.txt"),
                    "ticker_profit_file": _rel(root, _case_ticker_profit_path(case_dir)),
                    "inputs": [_rel(root, resolve_within(root, str(path))) for path in DEFAULT_CONCENTRATION_INPUTS],
                }
            )

    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "status": "DRY_RUN",
        "base_config_file": _rel(root, resolve_within(root, str(base_config_path))),
        "base_config_sha256": base_config_sha256,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "checks": checks,
        "planned_cases": case_plans,
        "notes": [
            "No simulation is executed in dry-run mode.",
            "No network access is attempted in dry-run mode.",
            "Resume behavior is validated structurally only; existing case artifacts are not overwritten during dry-run.",
        ],
    }


def run_logic_validation(
    *,
    root: Path | None = None,
    base_config_path: Path | str = DEFAULT_BASE_CONFIG_PATH,
    requested_start: str = DEFAULT_REQUESTED_START,
    requested_end: str = DEFAULT_REQUESTED_END,
    resume: bool = True,
    dry_run: bool = False,
    as_of: datetime = DEFAULT_AS_OF,
) -> dict[str, Any]:
    repository = (root or ROOT).resolve()
    base_config_path = Path(base_config_path)
    output_root = repository / DEFAULT_OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)
    base_settings, base_config_sha256 = _base_settings(repository, base_config_path)
    cases = build_case_specs()

    if dry_run:
        dry_run_payload = _build_dry_run_payload(
            root=repository,
            base_config_path=base_config_path,
            base_config_sha256=base_config_sha256,
            base_settings=base_settings,
            requested_start=requested_start,
            requested_end=requested_end,
            cases=cases,
        )
        _write_json(output_root / DEFAULT_PLAN_FILE, dry_run_payload)
        atomic_write(output_root / DEFAULT_DRY_RUN_TEXT_FILE, _build_top_level_report(base_config_path, requested_start, requested_end, []))
        return dry_run_payload

    context = _prepare_universe_and_histories(
        repository,
        base_settings,
        requested_start,
        requested_end,
        as_of,
    )

    case_records: list[dict[str, Any]] = []
    for case in cases:
        if case.kind == "simulation":
            record = _execute_simulation_case(
                root=repository,
                base_settings=base_settings,
                base_config_path=base_config_path,
                base_config_sha256=base_config_sha256,
                context=context,
                case=case,
                resume=resume,
            )
        else:
            record = _concentration_summary(repository, output_root)
        case_records.append(record)

    summary = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "version": RUNNER_VERSION,
        "generated_at": _now_text(),
        "status": "FAILED" if any(case.get("status") == "FAILED" for case in case_records) else "SUCCESS",
        "base_config_file": _rel(repository, resolve_within(repository, str(base_config_path))),
        "base_config_sha256": base_config_sha256,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "run_count": len(case_records),
        "runs": case_records,
    }
    summary_path = output_root / DEFAULT_SUMMARY_FILE
    report_path = output_root / DEFAULT_REPORT_FILE
    summary_csv_path = output_root / DEFAULT_SUMMARY_CSV_FILE
    _write_json(summary_path, summary)
    atomic_write(report_path, _build_top_level_report(base_config_path, requested_start, requested_end, case_records))
    pd.DataFrame(_build_summary_csv_rows(case_records)).to_csv(summary_csv_path, index=False, encoding="utf-8-sig")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PHOENIX Logic Validation Risk v2")
    parser.add_argument(
        "--base-config",
        default=str(DEFAULT_BASE_CONFIG_PATH),
        help="Base config to clone for logic validation cases",
    )
    parser.add_argument(
        "--requested-start",
        default=DEFAULT_REQUESTED_START,
        help="Validation start date",
    )
    parser.add_argument(
        "--requested-end",
        default=DEFAULT_REQUESTED_END,
        help="Validation end date",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the plan without running simulations",
    )
    parser.add_argument(
        "--resume",
        dest="resume",
        action="store_true",
        default=True,
        help="Skip finished cases when case artifacts already exist",
    )
    parser.add_argument(
        "--no-resume",
        dest="resume",
        action="store_false",
        help="Recompute all cases even if artifacts already exist",
    )
    args = parser.parse_args(argv)

    try:
        run_logic_validation(
            root=ROOT,
            base_config_path=Path(args.base_config),
            requested_start=args.requested_start,
            requested_end=args.requested_end,
            resume=bool(args.resume),
            dry_run=bool(args.dry_run),
        )
        return 0
    except Exception as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        if isinstance(error, LogicValidationError):
            return 2
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
