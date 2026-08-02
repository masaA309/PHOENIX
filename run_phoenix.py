# run_phoenix.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time
from typing import Any

from phoenix_heartbeat import PhoenixHeartbeat
from phoenix_core.virtual_rss_paper import prepare_quote_environment
from position_reconciliation import run_position_reconciliation
from repository_guardian import run_repository_guardian


# =========================================================
# 基本設定
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"

LOG_FILE = LOG_DIR / (
    "phoenix_"
    + datetime.now().strftime("%Y%m%d")
    + ".log"
)

PROCESS_TIMEOUT_SECONDS = 1800

STOP_ON_REQUIRED_FAILURE = True

_ACTIVE_HEARTBEAT: PhoenixHeartbeat | None = None


# =========================================================
# 実行タスク
# =========================================================
#
# required=True
#   失敗した場合、後続処理を停止します。
#
# required=False
#   ファイルが存在しない場合や処理が失敗した場合も、
#   後続処理を続行します。
#
# enabled=False
#   一時的に実行対象から外せます。
#
# PHOENIX v2.8 実行順
#
# 1. Market Risk AI
# 2. Price Monitor
# 3. 日経225構成銘柄更新
# 4. 日次スキャン・レポート
# 5. Learning Engine
# 6. AI売買判断
# 7. ランキングAI
# 8. チャート生成
# 9. LINE・Discord通知
#

TASKS: list[dict[str, Any]] = [
    {
        "name": "Market Risk AI",
        "script": "market_risk_ai.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "Price Monitor",
        "script": "price_monitor.py",
        "args": ["--once"],
        "required": False,
        "enabled": True,
    },
    {
        "name": "日経225構成銘柄更新",
        "script": "get_nikkei225.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "日次スキャン・レポート",
        "script": "daily_report.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "自己学習エンジン",
        "script": "learning_engine.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "AI売買判断",
        "script": "ai_judgement.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "取引候補生成",
        "script": "trade_engine.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "監視優先ランキングAI",
        "script": "ranking_ai.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "チャート自動生成",
        "script": "chart_generator.py",
        "required": True,
        "enabled": True,
    },
    {
        "name": "LINE・Discord通知",
        "script": "notify.py",
        "required": True,
        "enabled": True,
    },
]

REFRESH_ONLY_SCRIPTS = {
    "market_risk_ai.py",
    "get_nikkei225.py",
    "daily_report.py",
    "learning_engine.py",
    "ai_judgement.py",
    "trade_engine.py",
}


# =========================================================
# コンソール設定
# =========================================================

def configure_console() -> None:
    try:
        sys.stdout.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

        sys.stderr.reconfigure(
            encoding="utf-8",
            errors="replace",
        )

    except (
        AttributeError,
        OSError,
    ):
        pass


# =========================================================
# 共通処理
# =========================================================

def now_text() -> str:
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def write_log(
    message: Any,
) -> None:
    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = (
        f"[{now_text()}] "
        f"{message}"
    )

    print(
        text,
        flush=True,
    )

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8",
        newline="\n",
    ) as log_file:
        log_file.write(
            text + "\n"
        )


def build_environment() -> dict[str, str]:
    environment = os.environ.copy()

    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"

    return environment


def configure_quote_transport() -> dict[str, Any]:
    environment, ca_bundle = prepare_quote_environment()
    if ca_bundle is None or environment.get("status") != "READY":
        raise RuntimeError(
            "Quote transport is unavailable: "
            f"{environment.get('code')} / {environment.get('remediation')}"
        )
    for name in ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE"):
        os.environ[name] = str(ca_bundle)
    return environment


def initialize_directories() -> None:
    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def reset_log_file() -> None:
    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        LOG_FILE,
        "w",
        encoding="utf-8",
        newline="\n",
    ) as log_file:
        log_file.write(
            ""
        )


# =========================================================
# Pythonスクリプト実行
# =========================================================

def run_script(
    task_name: str,
    script_name: str,
    required: bool,
    args: list[str] | None = None,
) -> tuple[
    bool,
    float,
    int,
    str,
]:
    script_path = ROOT_DIR / script_name

    write_log("=" * 90)
    write_log(
        f"START: {task_name}"
    )
    write_log(
        f"SCRIPT: {script_name}"
    )
    write_log(
        "TYPE: "
        + (
            "必須"
            if required
            else "任意"
        )
    )

    if not script_path.exists():
        message = (
            "ファイルがありません: "
            f"{script_path}"
        )

        if required:
            write_log(
                f"FAILED: {message}"
            )

            return (
                False,
                0.0,
                -1,
                message,
            )

        write_log(
            f"SKIPPED: {message}"
        )

        return (
            True,
            0.0,
            0,
            message,
        )

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(script_path),
    ]
    command.extend(args or [])

    started_at = time.time()

    try:
        process = subprocess.run(
            command,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROCESS_TIMEOUT_SECONDS,
            env=build_environment(),
            check=False,
        )

    except subprocess.TimeoutExpired:
        elapsed = (
            time.time()
            - started_at
        )

        message = (
            "タイムアウト: "
            f"{PROCESS_TIMEOUT_SECONDS}秒"
        )

        write_log(
            f"FAILED: {task_name}"
        )
        write_log(
            message
        )

        return (
            False,
            elapsed,
            -2,
            message,
        )

    except Exception as error:
        elapsed = (
            time.time()
            - started_at
        )

        message = (
            f"起動エラー: {error}"
        )

        write_log(
            f"FAILED: {task_name}"
        )
        write_log(
            message
        )

        return (
            False,
            elapsed,
            -3,
            message,
        )

    elapsed = (
        time.time()
        - started_at
    )

    if process.stdout:
        for line in (
            process.stdout
            .rstrip()
            .splitlines()
        ):
            write_log(
                line
            )

    if process.stderr:
        for line in (
            process.stderr
            .rstrip()
            .splitlines()
        ):
            write_log(
                f"STDERR: {line}"
            )

    if process.returncode == 0:
        write_log(
            f"SUCCESS: {task_name}"
        )
        write_log(
            f"処理時間: {elapsed:.1f}秒"
        )

        return (
            True,
            elapsed,
            process.returncode,
            "正常終了",
        )

    message = (
        "終了コード: "
        f"{process.returncode}"
    )

    write_log(
        f"FAILED: {task_name}"
    )
    write_log(
        message
    )
    write_log(
        f"処理時間: {elapsed:.1f}秒"
    )

    return (
        False,
        elapsed,
        process.returncode,
        message,
    )


# =========================================================
# 出力ファイル確認
# =========================================================

def verify_output_files(*, refresh_only: bool = False) -> dict[str, bool]:
    today = datetime.now().strftime(
        "%Y%m%d"
    )

    expected_files = {
        "Market Risk最新JSON": (
            DATA_DIR
            / "market_risk_latest.json"
        ),
        "Market Risk履歴CSV": (
            DATA_DIR
            / "market_risk_history.csv"
        ),
        "日次レポートCSV": (
            REPORT_DIR
            / f"report_{today}.csv"
        ),
        "AI判断CSV": (
            REPORT_DIR
            / "ai_judgement.csv"
        ),
        "取引候補CSV": (
            REPORT_DIR
            / "trade_signals.csv"
        ),
        "ランキングCSV": (
            REPORT_DIR
            / "ranking_ai.csv"
        ),
        "ランキングTXT": (
            REPORT_DIR
            / "ranking_ai.txt"
        ),
        "通知ログ": (
            REPORT_DIR
            / "notification_log.txt"
        ),
    }
    if refresh_only:
        expected_files = {
            name: path
            for name, path in expected_files.items()
            if name not in {"ランキングCSV", "ランキングTXT", "通知ログ"}
        }

    results: dict[str, bool] = {}

    write_log("=" * 90)
    write_log(
        "出力ファイル確認"
    )

    for name, file_path in expected_files.items():
        exists = file_path.exists()

        results[name] = exists

        status = (
            "OK"
            if exists
            else "MISSING"
        )

        write_log(
            f"{status}: "
            f"{name} "
            f"{file_path}"
        )

    return results


# =========================================================
# 最終結果
# =========================================================

def print_final_summary(
    task_results: list[
        dict[str, Any]
    ],
    output_results: dict[
        str,
        bool
    ],
    started_at: float,
) -> None:
    elapsed_total = (
        time.time()
        - started_at
    )

    executed_results = [
        result
        for result in task_results
        if not result.get(
            "disabled",
            False,
        )
    ]

    success_count = sum(
        1
        for result in executed_results
        if result["success"]
    )

    failure_count = sum(
        1
        for result in executed_results
        if not result["success"]
    )

    required_failures = [
        result
        for result in executed_results
        if (
            result["required"]
            and not result["success"]
        )
    ]

    missing_outputs = [
        name
        for name, exists
        in output_results.items()
        if not exists
    ]

    write_log("=" * 90)
    write_log(
        "PHOENIX DAILY RESULT"
    )
    write_log("=" * 90)

    for result in task_results:
        if result.get(
            "disabled",
            False,
        ):
            write_log(
                f"DISABLED "
                f"{result['name']}"
            )
            continue

        status = (
            "SUCCESS"
            if result["success"]
            else "FAILED"
        )

        if result.get(
            "skipped",
            False,
        ):
            status = "SKIPPED"

        required_text = (
            "必須"
            if result["required"]
            else "任意"
        )

        write_log(
            f"{status:<8} "
            f"{result['name']} "
            f"({required_text}) "
            f"{result['elapsed']:.1f}秒"
        )

        if result.get(
            "message"
        ):
            write_log(
                f"         {result['message']}"
            )

    write_log("-" * 90)

    write_log(
        f"成功: {success_count}件"
    )
    write_log(
        f"失敗: {failure_count}件"
    )
    write_log(
        f"総処理時間: {elapsed_total:.1f}秒"
    )

    if required_failures:
        write_log(
            "必須処理失敗: "
            + ", ".join(
                result["name"]
                for result
                in required_failures
            )
        )

    if missing_outputs:
        write_log(
            "未生成ファイル: "
            + ", ".join(
                missing_outputs
            )
        )

    if (
        not required_failures
        and not missing_outputs
    ):
        write_log(
            "PHOENIX DAILY RUN SUCCESS"
        )
    else:
        write_log(
            "PHOENIX DAILY RUN FAILED"
        )

    write_log(
        f"ログ保存: {LOG_FILE}"
    )


# =========================================================
# メイン
# =========================================================

def print_morning_run_summary(
    task_results: list[dict[str, Any]],
    output_results: dict[str, bool],
    started_at: float,
) -> None:
    def phase_status(
        scripts: set[str],
        success_status: str,
    ) -> str:
        phase_results = [
            result
            for result in task_results
            if (
                result["script"] in scripts
                and not result.get("disabled", False)
            )
        ]
        executed = [
            result
            for result in phase_results
            if not result.get("skipped", False)
        ]
        if not executed:
            return "NOT_RUN"
        if any(not result["success"] for result in executed):
            return "FAILED"
        if any(
            result.get("skipped", False)
            and not result["success"]
            for result in phase_results
        ):
            return "FAILED"
        return success_status

    def git_commit() -> str | None:
        try:
            git_dir = ROOT_DIR / ".git"
            if git_dir.is_file():
                marker, location = git_dir.read_text(
                    encoding="utf-8"
                ).strip().split(":", 1)
                if marker != "gitdir":
                    return None
                candidate = Path(location.strip())
                git_dir = (
                    candidate
                    if candidate.is_absolute()
                    else (ROOT_DIR / candidate).resolve()
                )

            head = (git_dir / "HEAD").read_text(
                encoding="utf-8"
            ).strip()
            if head.startswith("ref: "):
                reference = head[5:].strip()
                reference_path = git_dir / reference
                if reference_path.is_file():
                    commit = reference_path.read_text(
                        encoding="utf-8"
                    ).strip()
                else:
                    commit = ""
                    packed_refs = git_dir / "packed-refs"
                    if packed_refs.is_file():
                        for line in packed_refs.read_text(
                            encoding="utf-8"
                        ).splitlines():
                            if line.startswith(("#", "^")):
                                continue
                            value, separator, name = line.partition(" ")
                            if separator and name == reference:
                                commit = value
                                break
            else:
                commit = head

            if len(commit) >= 7 and all(
                character in "0123456789abcdefABCDEF"
                for character in commit
            ):
                return commit[:7]
        except (OSError, ValueError):
            pass
        return None

    required_failures = [
        result
        for result in task_results
        if (
            result["required"]
            and not result["success"]
            and not result.get("disabled", False)
        )
    ]
    missing_outputs = [
        name
        for name, exists in output_results.items()
        if not exists
    ]
    elapsed_total = time.time() - started_at
    exit_code = 1 if required_failures or missing_outputs else 0
    commit = git_commit()

    write_log("=" * 90)
    write_log("PHOENIX OPERATIONAL SUMMARY")
    write_log("=" * 90)
    write_log("Mode         : PAPER")
    write_log(
        "Refresh      : "
        + phase_status(
            {"get_nikkei225.py", "daily_report.py"},
            "OK",
        )
    )
    write_log(
        "Market Guard : "
        + phase_status(
            {"market_risk_ai.py"},
            "READY",
        )
    )
    write_log(
        "AI           : "
        + phase_status(
            {
                "learning_engine.py",
                "ai_judgement.py",
                "trade_engine.py",
                "ranking_ai.py",
            },
            "OK",
        )
    )
    write_log(
        "Notify       : "
        + phase_status(
            {"notify.py"},
            "SUCCESS",
        )
    )
    write_log("Scheduler    : READY")
    if commit is not None:
        write_log(f"Git Commit   : {commit}")
    write_log(f"Elapsed      : {elapsed_total:.1f} s")
    write_log(f"Exit Code    : {exit_code}")
    write_log("=" * 90)


def _run_main() -> None:
    global _ACTIVE_HEARTBEAT
    configure_console()
    guardian_result = run_repository_guardian(report_dir=LOG_DIR)
    if not guardian_result.ready:
        reasons = ", ".join(guardian_result.reasons) or "unknown"
        print(
            "PHOENIX START BLOCKED BY REPOSITORY GUARDIAN: " + reasons,
            file=sys.stderr,
            flush=True,
        )
        if guardian_result.report_error:
            print(
                "Repository Guardian report error: "
                + guardian_result.report_error,
                file=sys.stderr,
                flush=True,
            )
        raise SystemExit(2)
    reconciliation_result = run_position_reconciliation(
        guardian_status=guardian_result.status,
        report_dir=LOG_DIR,
    )
    if reconciliation_result.status != "READY":
        reasons = ", ".join(reconciliation_result.reasons) or "unknown"
        print(
            "PHOENIX START BLOCKED BY POSITION RECONCILIATION: " + reasons,
            file=sys.stderr,
            flush=True,
        )
        if reconciliation_result.report_error:
            print(
                "Position Reconciliation report error: "
                + reconciliation_result.report_error,
                file=sys.stderr,
                flush=True,
            )
        raise SystemExit(2)
    heartbeat = PhoenixHeartbeat(
        repository_root=ROOT_DIR,
        guardian_status=guardian_result.status,
        position_reconciliation_status=reconciliation_result.status,
    )
    heartbeat.start(current_stage="OPERATIONAL_READY")
    _ACTIVE_HEARTBEAT = heartbeat
    print(
        "POSITION RECONCILIATION: " + reconciliation_result.status,
        flush=True,
    )
    print("PHOENIX OPERATIONAL READY", flush=True)
    heartbeat.set_stage("INITIALIZE_DIRECTORIES")
    initialize_directories()
    reset_log_file()

    parser = argparse.ArgumentParser(description="PHOENIX daily automation")
    parser.add_argument(
        "--refresh-only",
        action="store_true",
        help="Refresh verified market data and trade candidates without charts or notifications.",
    )
    args = parser.parse_args()

    heartbeat.set_stage("QUOTE_TRANSPORT")
    try:
        quote_environment = configure_quote_transport()
    except RuntimeError as error:
        write_log("PHOENIX QUOTE TRANSPORT FAILED")
        write_log(str(error))
        raise SystemExit(1) from error
    write_log(
        "Quote transport: "
        f"{quote_environment.get('status')} / {quote_environment.get('ca_bundle_mode')} / TLS=True"
    )

    started_at = time.time()

    write_log("=" * 90)
    write_log(
        "PHOENIX v2.8 DAILY AUTOMATION START"
    )
    write_log("=" * 90)

    write_log(
        f"Python: {sys.executable}"
    )
    write_log(
        f"作業フォルダ: {ROOT_DIR}"
    )
    write_log(
        f"ログファイル: {LOG_FILE}"
    )

    task_results: list[
        dict[str, Any]
    ] = []

    required_task_failed = False

    selected_tasks = [
        task
        for task in TASKS
        if not args.refresh_only or task["script"] in REFRESH_ONLY_SCRIPTS
    ]
    for task in selected_tasks:
        heartbeat.set_stage(str(task["name"]))
        enabled = bool(
            task.get(
                "enabled",
                True,
            )
        )

        if not enabled:
            write_log("=" * 90)
            write_log(
                f"DISABLED: {task['name']}"
            )

            task_results.append({
                "name": task["name"],
                "script": task["script"],
                "required": task["required"],
                "success": True,
                "elapsed": 0.0,
                "returncode": 0,
                "skipped": True,
                "disabled": True,
                "message": "設定により無効",
            })

            continue

        if (
            required_task_failed
            and STOP_ON_REQUIRED_FAILURE
        ):
            write_log("=" * 90)
            write_log(
                f"SKIPPED: {task['name']}"
            )
            write_log(
                "前の必須処理が失敗したため、"
                "後続処理を停止しました。"
            )

            task_results.append({
                "name": task["name"],
                "script": task["script"],
                "required": task["required"],
                "success": False,
                "elapsed": 0.0,
                "returncode": -10,
                "skipped": True,
                "disabled": False,
                "message": (
                    "前の必須処理失敗により停止"
                ),
            })

            continue

        success, elapsed, returncode, message = (
            run_script(
                task_name=task["name"],
                script_name=task["script"],
                required=task["required"],
                args=task.get("args"),
            )
        )

        script_exists = (
            ROOT_DIR
            / task["script"]
        ).exists()

        skipped = (
            not task["required"]
            and not script_exists
        )

        task_results.append({
            "name": task["name"],
            "script": task["script"],
            "required": task["required"],
            "success": success,
            "elapsed": elapsed,
            "returncode": returncode,
            "skipped": skipped,
            "disabled": False,
            "message": message,
        })

        if (
            task["required"]
            and not success
        ):
            required_task_failed = True

    heartbeat.set_stage("VERIFY_OUTPUTS")
    output_results = verify_output_files(refresh_only=args.refresh_only)

    heartbeat.set_stage("FINAL_SUMMARY")
    print_final_summary(
        task_results=task_results,
        output_results=output_results,
        started_at=started_at,
    )

    required_failures = [
        result
        for result in task_results
        if (
            result["required"]
            and not result["success"]
            and not result.get(
                "disabled",
                False,
            )
        )
    ]

    missing_outputs = [
        name
        for name, exists
        in output_results.items()
        if not exists
    ]

    print_morning_run_summary(
        task_results=task_results,
        output_results=output_results,
        started_at=started_at,
    )

    if (
        required_failures
        or missing_outputs
    ):
        raise SystemExit(
            1
        )


def _stop_active_heartbeat(
    status: str,
    current_stage: str,
    *,
    preserve_active_exception: bool,
) -> None:
    heartbeat = _ACTIVE_HEARTBEAT
    if heartbeat is None:
        return
    try:
        heartbeat.stop(status=status, current_stage=current_stage)
    except Exception as error:
        if not preserve_active_exception:
            raise
        print(
            "Heartbeat shutdown failed while preserving the active exception: "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
            flush=True,
        )


def main() -> None:
    global _ACTIVE_HEARTBEAT
    _ACTIVE_HEARTBEAT = None
    try:
        _run_main()
    except KeyboardInterrupt:
        _stop_active_heartbeat(
            "STOPPED",
            "INTERRUPTED",
            preserve_active_exception=True,
        )
        raise
    except BaseException:
        _stop_active_heartbeat(
            "FAILED",
            "FAILED",
            preserve_active_exception=True,
        )
        raise
    else:
        _stop_active_heartbeat(
            "COMPLETED",
            "COMPLETED",
            preserve_active_exception=False,
        )
    finally:
        _ACTIVE_HEARTBEAT = None


if __name__ == "__main__":
    main()
