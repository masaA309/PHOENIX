from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from phoenix_core.operations_monitor import print_operations_summary, run_operations_monitor
from phoenix_core.performance_tracker import print_performance_summary, update_performance
from phoenix_core.decision_diagnostics import print_diagnostics_summary, run_decision_diagnostics
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


def monitor_and_track(config: dict[str, Any], return_code: int, log_path: Path) -> bool:
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
        return True
    except Exception as error:
        print("PHOENIX Step11 DECISION DIAGNOSTICS ERROR")
        print(f"{type(error).__name__}: {error}")
        return False


def main() -> int:
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
    state = load_state(state_path)
    allowed, reason = should_run(policy, state, now)
    if not args.force and not allowed:
        print(f"PHOENIX Step7 SKIP: {reason}")
        return 0
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"v7_scheduler_{now:%Y%m%d_%H%M%S}.log"
    command = [sys.executable, str(pipeline_script), "--config", str(pipeline_config)]
    dry_run = args.dry_run or bool(scheduler.get("dry_run", False))
    scheduler["dry_run"] = dry_run
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
                save_state(state_path, {**state, **success_state(now, 0, log_path)})
                monitor_ok = monitor_and_track(config, 0, log_path)
                print(f"PHOENIX Step7 SUCCESS: {log_path}")
                return 0 if monitor_ok else 10
            save_state(state_path, {**state, **failure_state(now, completed.returncode, log_path)})
            monitor_and_track(config, completed.returncode, log_path)
            print(f"PHOENIX Step7 FAILED({completed.returncode}): {log_path}")
            return completed.returncode
    except RuntimeError as error:
        print(f"PHOENIX Step7 SKIP: {error}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
