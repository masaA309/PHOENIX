from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from typing import Any

from phoenix_core.operations_monitor import print_operations_summary, run_operations_monitor
from phoenix_core.performance_tracker import print_performance_summary, update_performance
from phoenix_core.decision_diagnostics import print_diagnostics_summary, run_decision_diagnostics
from phoenix_core.portfolio_guard import print_portfolio_summary, run_portfolio_guard
from phoenix_core.market_data_guard import print_market_data_summary, run_market_data_guard
from phoenix_core.readiness_gate import print_readiness_summary, run_readiness_gate
from phoenix_core.order_lifecycle import print_lifecycle_summary, run_order_lifecycle
from phoenix_core.trading_economics import (
    print_economics_summary,
    run_trading_economics,
)
from phoenix_core.staged_pilot_gate import (
    print_staged_pilot_summary,
)
from phoenix_core.dry_run_integrity import (
    capture_protected_files,
    print_integrity_summary,
    save_integrity_report,
)
from phoenix_core.run_guard import RunPolicy, SingleInstanceLock, failure_state, load_state, save_state, should_run, success_state

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "config" / "v7_scheduler_config.json"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Scheduler config root must be a JSON object")
    return value


def resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT_DIR / path


def monitor_and_track(
    config: dict[str, Any],
    return_code: int,
    log_path: Path,
    dry_run: bool,
) -> bool:
    operations = config.get("operations", {})
    if not bool(operations.get("enabled", True)):
        print("PHOENIX Step9 MONITOR: disabled")
        return True
    try:
        report = run_operations_monitor(ROOT_DIR, config, return_code, log_path)
        print_operations_summary(report)
    except Exception as error:
        print("PHOENIX Step9 MONITOR ERROR")
        print(f"{type(error).__name__}: {error}")
        return False

    performance = config.get("performance", {})
    if not bool(performance.get("enabled", True)):
        print("PHOENIX Step10 PERFORMANCE TRACKER: disabled")
        return True
    try:
        summary = update_performance(ROOT_DIR, config, report)
        print_performance_summary(summary)
    except Exception as error:
        print("PHOENIX Step10 PERFORMANCE TRACKER ERROR")
        print(f"{type(error).__name__}: {error}")
        return False

    diagnostics = config.get("diagnostics", {})
    if not bool(diagnostics.get("enabled", True)):
        print("PHOENIX Step11 DECISION DIAGNOSTICS: disabled")
        return True
    try:
        diagnostic_report = run_decision_diagnostics(ROOT_DIR, config, report)
        print_diagnostics_summary(diagnostic_report)
    except Exception as error:
        print("PHOENIX Step11 DECISION DIAGNOSTICS ERROR")
        print(f"{type(error).__name__}: {error}")
        return False

    market_safe = True
    market_guard = config.get("market_data_guard", {})
    if bool(market_guard.get("enabled", True)):
        try:
            market_report = run_market_data_guard(
                ROOT_DIR,
                config,
                persist_state=not dry_run,
            )
            print_market_data_summary(market_report)
            market_safe = market_report.get("status") != "FAILED"
        except Exception as error:
            print("PHOENIX Step13 MARKET DATA GUARD ERROR")
            print(f"{type(error).__name__}: {error}")
            market_safe = False
    else:
        print("PHOENIX Step13 MARKET DATA GUARD: disabled")

    guard = config.get("portfolio_guard", {})
    if not bool(guard.get("enabled", True)):
        print("PHOENIX Step12 PORTFOLIO EXIT GUARD: disabled")
        return market_safe
    if not bool(guard.get("advisory_only", True)):
        print("PHOENIX Step12 PORTFOLIO EXIT GUARD ERROR: advisory_only must remain true")
        return False
    try:
        portfolio_report = run_portfolio_guard(ROOT_DIR, config)
        print_portfolio_summary(portfolio_report)
    except Exception as error:
        print("PHOENIX Step12 PORTFOLIO EXIT GUARD ERROR")
        print(f"{type(error).__name__}: {error}")
        return False

    lifecycle_safe = True
    lifecycle = config.get("order_lifecycle", {})
    if bool(lifecycle.get("enabled", True)):
        try:
            lifecycle_report = run_order_lifecycle(
                ROOT_DIR,
                config,
                persist_state=not dry_run,
            )
            print_lifecycle_summary(lifecycle_report)
            lifecycle_safe = lifecycle_report.get("status") == "READY"
        except Exception as error:
            print("PHOENIX Step15 ORDER LIFECYCLE ERROR")
            print(f"{type(error).__name__}: {error}")
            return False
    else:
        print("PHOENIX Step15 ORDER LIFECYCLE: disabled")

    economics = config.get("trading_economics", {})
    if bool(economics.get("enabled", True)):
        try:
            economics_report = run_trading_economics(
                ROOT_DIR,
                config,
                persist_state=not dry_run,
            )
            print_economics_summary(economics_report)
        except Exception as error:
            print("PHOENIX Step19 TRADING ECONOMICS ERROR")
            print(f"{type(error).__name__}: {error}")
            return False
    else:
        print("PHOENIX Step19 TRADING ECONOMICS ERROR: enabled must remain true")
        return False

    readiness = config.get("readiness_gate", {})
    staged = config.get("staged_pilot_gate", {})
    if staged.get("enabled") is not True:
        print("PHOENIX Step19 STAGED PILOT GATE ERROR: enabled must remain true")
        return False
    if bool(readiness.get("enabled", True)):
        try:
            readiness_report = run_readiness_gate(ROOT_DIR, config)
            staged_report = readiness_report.pop("_staged_pilot_report", {})
            print_staged_pilot_summary(staged_report)
            print_readiness_summary(readiness_report)
        except Exception as error:
            print("PHOENIX Step14 READINESS GATE ERROR")
            print(f"{type(error).__name__}: {error}")
            return False
    else:
        print("PHOENIX Step14 READINESS GATE: disabled")

    return market_safe and lifecycle_safe


def verify_dry_run_integrity(
    config: dict[str, Any],
    before: dict[str, dict[str, Any]],
    generated_at: datetime,
) -> bool:
    try:
        report = save_integrity_report(ROOT_DIR, config, before, generated_at)
        print_integrity_summary(report)
        return report.get("status") == "READY"
    except Exception as error:
        print("PHOENIX Step16 DRY RUN INTEGRITY ERROR")
        print(f"{type(error).__name__}: {error}")
        return False


def _run_scheduled_refresh() -> int:
    configure_console()
    parser = argparse.ArgumentParser(description="PHOENIX v7 scheduled one-shot runner")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--force", action="store_true", help="Ignore weekday and once-per-day checks")
    parser.add_argument("--dry-run", action="store_true", help="Run without placing orders")
    args = parser.parse_args()
    config = load_config(Path(args.config))
    scheduler = config.get("scheduler", {})
    files = config.get("files", {})
    policy = RunPolicy(
        enabled=bool(scheduler.get("enabled", True)),
        weekdays=tuple(int(day) for day in scheduler.get("weekdays", [0, 1, 2, 3, 4])),
        once_per_day=bool(scheduler.get("once_per_day", True)),
    )
    state_path = resolve_path(str(files.get("scheduler_state", "state/v7_scheduler_state.json")))
    lock_path = resolve_path(str(files.get("lock", "state/v7_scheduler.lock")))
    log_dir = resolve_path(str(files.get("log_dir", "logs/scheduler")))
    pipeline_config = resolve_path(str(files.get("pipeline_config", "config/v7_direct_pipeline_config.json")))
    pipeline_script = ROOT_DIR / "direct_pipeline_v7.py"
    now = datetime.now()
    dry_run = args.dry_run or bool(scheduler.get("dry_run", False))
    scheduler["dry_run"] = dry_run
    integrity_settings = config.get("dry_run_integrity", {})
    integrity_before: dict[str, dict[str, Any]] = {}
    if dry_run:
        if not bool(integrity_settings.get("enabled", True)):
            print("PHOENIX Step16 ERROR: Dry Run integrity guard must remain enabled")
            return 12
        try:
            integrity_before = capture_protected_files(
                ROOT_DIR,
                [str(value) for value in integrity_settings.get("protected_files", [])],
            )
        except Exception as error:
            print("PHOENIX Step16 DRY RUN INTEGRITY ERROR")
            print(f"{type(error).__name__}: {error}")
            return 12
    try:
        state = load_state(state_path)
    except ValueError as error:
        print("PHOENIX Step7 STATE ERROR")
        print(f"{type(error).__name__}: {error}")
        return 8
    allowed, reason = should_run(policy, state, now)
    if not args.force and not allowed:
        print(f"PHOENIX Step7 SKIP: {reason}")
        return 0
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"v7_scheduler_{now:%Y%m%d_%H%M%S}.log"
    command = [sys.executable, str(pipeline_script), "--config", str(pipeline_config)]
    if dry_run:
        command.append("--dry-run")
    try:
        with SingleInstanceLock(lock_path):
            completed = subprocess.run(
                command, cwd=ROOT_DIR, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False,
            )
            output = completed.stdout
            if completed.stderr:
                output += "\n[STDERR]\n" + completed.stderr
            log_path.write_text(output, encoding="utf-8")
            print(output, end="" if output.endswith("\n") else "\n")
            if completed.returncode == 0:
                if not dry_run:
                    save_state(state_path, {**state, **success_state(now, 0, log_path)})
                monitor_ok = monitor_and_track(config, 0, log_path, dry_run)
                integrity_ok = (
                    verify_dry_run_integrity(config, integrity_before, now)
                    if dry_run else True
                )
                print(f"PHOENIX Step7 SUCCESS: {log_path}")
                if not integrity_ok:
                    return 11
                return 0 if monitor_ok else 10
            if not dry_run:
                save_state(state_path, {**state, **failure_state(now, completed.returncode, log_path)})
            monitor_and_track(config, completed.returncode, log_path, dry_run)
            integrity_ok = (
                verify_dry_run_integrity(config, integrity_before, now)
                if dry_run else True
            )
            print(f"PHOENIX Step7 FAILED({completed.returncode}): {log_path}")
            if not integrity_ok:
                return 11
            return completed.returncode
    except RuntimeError as error:
        print(f"PHOENIX Step7 SKIP: {error}")
        return 0


def main() -> int:
    started_at = perf_counter()
    print(f"[{datetime.now():%H:%M:%S}] Scheduled refresh started")
    try:
        return_code = _run_scheduled_refresh()
    except Exception as error:
        duration_ms = int((perf_counter() - started_at) * 1000)
        print(f"[{datetime.now():%H:%M:%S}] Scheduled refresh failed")
        print(f"Reason: {type(error).__name__}: {error}")
        print(f"Execution time: {duration_ms} ms")
        raise

    duration_ms = int((perf_counter() - started_at) * 1000)
    if return_code == 0:
        print(f"[{datetime.now():%H:%M:%S}] Scheduled refresh completed")
    else:
        print(f"[{datetime.now():%H:%M:%S}] Scheduled refresh failed")
        print(f"Reason: exit code {return_code}")
    print(f"Execution time: {duration_ms} ms")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
