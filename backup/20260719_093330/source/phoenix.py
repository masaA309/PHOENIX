# phoenix.py
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
LOG_DIR = ROOT_DIR / "logs"
BACKUP_DIR = ROOT_DIR / "backup"
STATE_DIR = ROOT_DIR / "state"

RUN_STATE_FILE = STATE_DIR / "phoenix_run_state.json"
LATEST_SUMMARY_FILE = REPORT_DIR / "phoenix_latest_summary.json"
LATEST_REPORT_FILE = REPORT_DIR / "phoenix_latest_report.txt"

BACKUP_KEEP_COUNT = 14
DEFAULT_TIMEOUT = 3600
PRICE_MONITOR_TIMEOUT = 600

REQUIRED_PACKAGES = ["pandas", "yfinance", "requests"]


@dataclass(frozen=True)
class Stage:
    key: str
    title: str
    script: str
    args: tuple[str, ...] = ()
    required: bool = True
    timeout: int = DEFAULT_TIMEOUT


STAGES = (
    Stage("market_risk", "Market Risk AI", "market_risk_ai.py"),
    Stage("daily_report", "Daily Report", "daily_report.py"),
    Stage("ai_judgement", "AI Judgement", "ai_judgement.py"),
    Stage("market_regime", "Market Regime AI", "market_regime_ai.py"),
    Stage("trade_engine", "Trade Engine", "trade_engine.py"),
    Stage("portfolio_optimizer", "Portfolio Optimizer", "portfolio_optimizer.py"),
    Stage("portfolio_manager", "Portfolio Manager", "portfolio_manager.py"),
    Stage("position_sizer", "Position Sizer", "position_sizer.py"),
    Stage(
        "price_monitor",
        "Price Monitor",
        "price_monitor.py",
        ("--once",),
        True,
        PRICE_MONITOR_TIMEOUT,
    ),
    Stage("paper_trader", "Paper Trader", "paper_trader.py"),
    Stage("learning_engine", "Learning Engine", "learning_engine.py"),
    Stage("backtest", "Backtest Engine", "backtest_engine.py"),
    Stage("optimization", "Optimization Engine", "optimization_engine.py"),
    Stage("walk_forward", "Walk Forward Engine", "walk_forward_engine.py"),
    Stage("adaptive_parameter", "Adaptive Parameter", "adaptive_parameter_engine.py"),
    Stage("dashboard", "Dashboard", "dashboard.py"),
    Stage("notify", "Notify", "notify.py", (), False),
)


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run_id_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def separator() -> str:
    return "=" * 120


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(text)
        if not text.endswith("\n"):
            file.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX v6.4 統合オートパイロット"
    )
    parser.add_argument("--from", dest="from_stage")
    parser.add_argument("--only", dest="only_stage")
    parser.add_argument("--force-market", action="store_true")
    parser.add_argument("--skip-backup", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--list", action="store_true")
    return parser.parse_args()


def get_stage(key: str) -> Stage | None:
    return next((stage for stage in STAGES if stage.key == key), None)


def show_stage_list() -> None:
    print(separator())
    print("PHOENIX STAGE LIST")
    print(separator())
    for number, stage in enumerate(STAGES, 1):
        kind = "必須" if stage.required else "任意"
        print(
            f"{number:>2}. {stage.key:<18} "
            f"{stage.title:<22} {stage.script:<24} {kind}"
        )


def diagnostics() -> dict[str, Any]:
    python_ok = sys.version_info >= (3, 10)

    packages = []
    for package in REQUIRED_PACKAGES:
        ok = importlib.util.find_spec(package) is not None
        packages.append({"name": package, "ok": ok})

    files = []
    for stage in STAGES:
        if not stage.required:
            continue
        exists = (ROOT_DIR / stage.script).exists()
        files.append({"name": stage.script, "ok": exists})

    ready = (
        python_ok
        and all(item["ok"] for item in packages)
        and all(item["ok"] for item in files)
    )

    return {
        "python_ok": python_ok,
        "python_version": sys.version.split()[0],
        "packages": packages,
        "files": files,
        "ready": ready,
    }


def print_diagnostics(data: dict[str, Any]) -> None:
    print(separator())
    print("PHOENIX SYSTEM DIAGNOSTICS")
    print(separator())
    print(
        f"{'Python':<30}"
        f"{'OK' if data['python_ok'] else 'ERROR':<10}"
        f"{data['python_version']}"
    )

    for item in data["packages"]:
        print(
            f"{item['name']:<30}"
            f"{'OK' if item['ok'] else 'ERROR':<10}"
        )

    print("-" * 120)

    for item in data["files"]:
        print(
            f"{item['name']:<30}"
            f"{'OK' if item['ok'] else 'ERROR':<10}"
        )

    print("-" * 120)
    print("SYSTEM STATUS:", "READY" if data["ready"] else "CHECK REQUIRED")


def copy_if_exists(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    elif source.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def cleanup_backups() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    folders = sorted(
        [path for path in BACKUP_DIR.iterdir() if path.is_dir()],
        reverse=True,
    )
    for old in folders[BACKUP_KEEP_COUNT:]:
        shutil.rmtree(old, ignore_errors=True)


def create_backup(run_id: str) -> Path:
    target = BACKUP_DIR / run_id
    target.mkdir(parents=True, exist_ok=True)

    copy_if_exists(REPORT_DIR, target / "reports")
    copy_if_exists(ROOT_DIR / "data", target / "data")

    source_dir = target / "source"
    for file_name in [
        "market_data_manager.py",
        "market_risk_ai.py",
        "daily_report.py",
        "ai_judgement.py",
        "trade_engine.py",
        "portfolio_optimizer.py",
        "portfolio_manager.py",
        "position_sizer.py",
        "price_monitor.py",
        "paper_trader.py",
        "learning_engine.py",
        "backtest_engine.py",
        "optimization_engine.py",
        "walk_forward_engine.py",
        "adaptive_parameter_engine.py",
        "dashboard.py",
        "notify.py",
        "phoenix.py",
    ]:
        source = ROOT_DIR / file_name
        if source.exists():
            copy_if_exists(source, source_dir / file_name)

    cleanup_backups()
    return target


def resolve_stages(args: argparse.Namespace) -> list[Stage]:
    if args.only_stage:
        stage = get_stage(args.only_stage)
        if stage is None:
            raise ValueError(f"不明なステージです: {args.only_stage}")
        return [stage]

    if args.from_stage:
        stage = get_stage(args.from_stage)
        if stage is None:
            raise ValueError(f"不明なステージです: {args.from_stage}")
        index = list(STAGES).index(stage)
        return list(STAGES[index:])

    if args.no_resume:
        return list(STAGES)

    previous = load_json(RUN_STATE_FILE)
    if previous.get("status") == "RUNNING":
        last_key = str(previous.get("last_completed_stage", ""))
        last_stage = get_stage(last_key)

        if last_stage is not None:
            next_index = list(STAGES).index(last_stage) + 1
            if next_index < len(STAGES):
                print(f"前回中断を検出: {last_key} の次から再開")
                return list(STAGES[next_index:])

    return list(STAGES)


def stage_command(stage: Stage, force_market: bool) -> list[str]:
    command = [sys.executable, str(ROOT_DIR / stage.script), *stage.args]
    if stage.key == "price_monitor" and force_market:
        command.append("--force")
    return command


def run_process(
    command: list[str],
    timeout: int,
    log_path: Path,
) -> tuple[int, str, bool]:
    process = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env={**os.environ, "PYTHONUTF8": "1"},
    )

    output: list[str] = []
    started = time.monotonic()
    timed_out = False
    assert process.stdout is not None

    while True:
        text = process.stdout.readline()

        if text:
            print(text, end="")
            append_log(log_path, text)
            output.append(text)

        if process.poll() is not None:
            rest = process.stdout.read()
            if rest:
                print(rest, end="")
                append_log(log_path, rest)
                output.append(rest)
            break

        if time.monotonic() - started > timeout:
            timed_out = True
            process.kill()
            message = f"\nTIMEOUT: {timeout}秒を超えたため終了\n"
            print(message)
            append_log(log_path, message)
            output.append(message)
            break

        time.sleep(0.05)

    return_code = process.wait()
    return return_code, "".join(output), timed_out


def run_stage(
    stage: Stage,
    force_market: bool,
    log_path: Path,
) -> dict[str, Any]:
    script_path = ROOT_DIR / stage.script
    started_at = now_text()

    if not script_path.exists():
        status = "ERROR" if stage.required else "SKIPPED"
        message = (
            "必須ファイルがありません"
            if stage.required
            else "任意ファイルがないため省略"
        )
        return {
            "key": stage.key,
            "title": stage.title,
            "script": stage.script,
            "required": stage.required,
            "status": status,
            "return_code": None,
            "seconds": 0.0,
            "started_at": started_at,
            "finished_at": now_text(),
            "message": message,
            "command": [],
            "output_tail": "",
        }

    command = stage_command(stage, force_market)
    started = time.monotonic()

    print()
    print(separator())
    print(f"START: {stage.title}")
    print("COMMAND:", " ".join(command))
    print(separator())

    append_log(
        log_path,
        f"\n{separator()}\nSTART: {stage.title}\n"
        f"COMMAND: {' '.join(command)}\n{separator()}\n",
    )

    try:
        return_code, output, timed_out = run_process(
            command, stage.timeout, log_path
        )
        seconds = time.monotonic() - started

        if timed_out:
            status = "TIMEOUT"
            message = "実行時間上限超過"
        elif return_code == 0:
            status = "OK"
            message = "正常終了"
        else:
            status = "ERROR"
            message = f"終了コード {return_code}"

        print(separator())
        print(f"END: {stage.title} {status} {seconds:.2f} sec")
        print(separator())

        return {
            "key": stage.key,
            "title": stage.title,
            "script": stage.script,
            "required": stage.required,
            "status": status,
            "return_code": return_code,
            "seconds": round(seconds, 3),
            "started_at": started_at,
            "finished_at": now_text(),
            "message": message,
            "command": command,
            "output_tail": output[-4000:],
        }

    except Exception as error:
        seconds = time.monotonic() - started
        error_text = traceback.format_exc()
        print(error_text)
        append_log(log_path, error_text)

        return {
            "key": stage.key,
            "title": stage.title,
            "script": stage.script,
            "required": stage.required,
            "status": "ERROR",
            "return_code": None,
            "seconds": round(seconds, 3),
            "started_at": started_at,
            "finished_at": now_text(),
            "message": str(error),
            "command": command,
            "output_tail": error_text[-4000:],
        }


def build_summary(
    run_id: str,
    started_at: str,
    results: list[dict[str, Any]],
    diagnostic_data: dict[str, Any],
    backup_path: Path | None,
) -> dict[str, Any]:
    success = sum(item["status"] == "OK" for item in results)
    skipped = sum(item["status"] == "SKIPPED" for item in results)
    failed = sum(
        item["status"] in {"ERROR", "TIMEOUT"}
        for item in results
    )
    required_failed = any(
        item["required"] and item["status"] in {"ERROR", "TIMEOUT"}
        for item in results
    )

    return {
        "version": "PHOENIX v6.3",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": now_text(),
        "status": "PARTIAL_FAILURE" if required_failed else "SUCCESS",
        "success_count": success,
        "failed_count": failed,
        "skipped_count": skipped,
        "total_seconds": round(
            sum(float(item["seconds"]) for item in results),
            3,
        ),
        "diagnostics_ok": diagnostic_data["ready"],
        "backup_path": str(backup_path) if backup_path else "",
        "results": results,
    }


def save_report(summary: dict[str, Any]) -> None:
    save_json(LATEST_SUMMARY_FILE, summary)

    lines = [
        "PHOENIX v6.3 EXECUTION REPORT",
        separator(),
        f"RUN ID        : {summary['run_id']}",
        f"START         : {summary['started_at']}",
        f"FINISH        : {summary['finished_at']}",
        f"STATUS        : {summary['status']}",
        f"SUCCESS       : {summary['success_count']}",
        f"FAILED        : {summary['failed_count']}",
        f"SKIPPED       : {summary['skipped_count']}",
        f"TOTAL SECONDS : {summary['total_seconds']:.3f}",
        f"BACKUP        : {summary['backup_path']}",
        separator(),
        "",
    ]

    for item in summary["results"]:
        lines.append(
            f"{item['title']:<24} "
            f"{item['status']:<10} "
            f"{item['seconds']:>10.2f} sec "
            f"{item['message']}"
        )

    LATEST_REPORT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def print_summary(summary: dict[str, Any], log_path: Path) -> None:
    print()
    print(separator())
    print("PHOENIX COMPLETE")
    print(separator())

    for item in summary["results"]:
        print(
            f"{item['title']:<24} "
            f"{item['status']:<10} "
            f"{item['seconds']:>10.2f} sec "
            f"{item['message']}"
        )

    print("-" * 120)
    print(f"成功           : {summary['success_count']}件")
    print(f"失敗           : {summary['failed_count']}件")
    print(f"省略           : {summary['skipped_count']}件")
    print(f"合計時間       : {summary['total_seconds']:.2f}秒")
    print(f"最終状態       : {summary['status']}")
    print(f"ログ           : {log_path}")
    print(f"結果JSON       : {LATEST_SUMMARY_FILE}")
    print(f"結果レポート   : {LATEST_REPORT_FILE}")
    print(separator())


def main() -> None:
    configure_console()
    args = parse_args()

    if args.list:
        show_stage_list()
        return

    for directory in [
        REPORT_DIR,
        LOG_DIR,
        BACKUP_DIR,
        STATE_DIR,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    run_id = run_id_text()
    started_at = now_text()
    log_path = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"

    print(separator())
    print("PHOENIX v6.3 AUTOPILOT START")
    print(separator())
    print(f"ROOT DIR : {ROOT_DIR}")
    print(f"RUN ID   : {run_id}")
    print(f"START    : {started_at}")

    append_log(
        log_path,
        f"\n{separator()}\nPHOENIX v6.3 AUTOPILOT START\n"
        f"RUN ID: {run_id}\nSTART : {started_at}\n{separator()}\n",
    )

    diagnostic_data = diagnostics()
    print_diagnostics(diagnostic_data)

    backup_path = None
    if args.skip_backup:
        print("バックアップ: 省略")
    else:
        print("バックアップ作成中...")
        backup_path = create_backup(run_id)
        print(f"バックアップ完了: {backup_path}")

    stages = resolve_stages(args)

    state = {
        "version": "PHOENIX v6.3",
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": "",
        "status": "RUNNING",
        "last_completed_stage": "",
        "stages": {},
    }
    save_json(RUN_STATE_FILE, state)

    results = []

    for stage in stages:
        result = run_stage(
            stage=stage,
            force_market=args.force_market,
            log_path=log_path,
        )
        results.append(result)
        state["stages"][stage.key] = result

        if result["status"] in {"OK", "SKIPPED"}:
            state["last_completed_stage"] = stage.key

        save_json(RUN_STATE_FILE, state)

        if (
            args.stop_on_error
            and result["status"] in {"ERROR", "TIMEOUT"}
        ):
            break

    summary = build_summary(
        run_id,
        started_at,
        results,
        diagnostic_data,
        backup_path,
    )
    save_report(summary)

    state["finished_at"] = summary["finished_at"]
    state["status"] = summary["status"]
    state["summary_file"] = str(LATEST_SUMMARY_FILE)
    save_json(RUN_STATE_FILE, state)

    print_summary(summary, log_path)

    append_log(
        log_path,
        f"PHOENIX FINISH: {summary['status']} "
        f"{summary['total_seconds']:.2f} sec\n",
    )

    if summary["status"] != "SUCCESS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
