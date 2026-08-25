# run_phoenix.py

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time
from typing import Any

from phoenix_disaster_recovery import (
    MAX_RECOVERY_ATTEMPTS_HARD_LIMIT,
    RecoveryRequiredExit,
    RecoverySession,
    run_disaster_recovery,
)
from phoenix_fail_safe import FailSafeController, FailSafeExit
from phoenix_heartbeat import PhoenixHeartbeat
from phoenix_core.virtual_rss_paper import prepare_quote_environment
from position_reconciliation import run_position_reconciliation
from repository_guardian import run_repository_guardian
from weekly_signal_comparison import run_latest_weekly_signal_comparison


# =========================================================
# 基本設定
# =========================================================

ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"
DIRECT_PIPELINE_CONFIG_FILE = ROOT_DIR / "config" / "v7_direct_pipeline_config.json"

LOG_FILE = LOG_DIR / (
    "phoenix_"
    + datetime.now().strftime("%Y%m%d")
    + ".log"
)

PROCESS_TIMEOUT_SECONDS = 1800
MAX_POSITION_STATE_AGE_SECONDS = 24 * 60 * 60

STOP_ON_REQUIRED_FAILURE = True

_ACTIVE_HEARTBEAT: PhoenixHeartbeat | None = None
_ACTIVE_FAIL_SAFE: FailSafeController | None = None
_ACTIVE_RECOVERY_SESSION: RecoverySession | None = None
_ACTIVE_OPERATING_MODE = "PAPER_SAFE"

OPERATING_MODE_TRADING_ACTIONS = {
    "PAPER_SAFE": "PAPER_ONLY",
    "LIVE_ACTIVE": "LIVE_ONLY",
    "LIVE_RECONCILE_ONLY": "RECONCILE_ONLY",
}


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
# 5. Market Regime AI
# 6. Learning Engine
# 7. AI売買判断
# 8. ランキングAI
# 9. チャート生成
# 10. LINE・Discord通知
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
        "name": "Market Regime AI",
        "script": "market_regime_ai.py",
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
        "name": "Step42 Pre-Order Gate",
        "script": "order_manager.py",
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
    "market_regime_ai.py",
    "learning_engine.py",
    "ai_judgement.py",
    "trade_engine.py",
    "order_manager.py",
}

MONITOR_ONLY_ALLOWED_SCRIPTS = frozenset(
    {
        "market_risk_ai.py",
        "price_monitor.py",
        "get_nikkei225.py",
        "daily_report.py",
        "market_regime_ai.py",
        "learning_engine.py",
        "ai_judgement.py",
        "trade_engine.py",
        "order_manager.py",
        "ranking_ai.py",
        "chart_generator.py",
        "notify.py",
    }
)


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


def build_environment(*, monitor_only: bool = False) -> dict[str, str]:
    environment = os.environ.copy()

    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    environment["PHOENIX_OPERATING_SCOPE"] = (
        "MONITOR_ONLY" if monitor_only else "OPERATIONAL"
    )
    environment["PHOENIX_TRADING_ACTIONS"] = (
        "DISABLED"
        if monitor_only
        else OPERATING_MODE_TRADING_ACTIONS[_ACTIVE_OPERATING_MODE]
    )
    environment["PHOENIX_OPERATING_MODE"] = _ACTIVE_OPERATING_MODE

    return environment


def load_operating_mode() -> str:
    if not DIRECT_PIPELINE_CONFIG_FILE.is_file():
        raise RuntimeError(
            "Operating mode config is missing: "
            f"{DIRECT_PIPELINE_CONFIG_FILE}"
        )

    try:
        payload = json.loads(DIRECT_PIPELINE_CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Operating mode config could not be read: "
            f"{type(error).__name__}: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError("Operating mode config root must be an object")

    operating_mode = str(payload.get("operating_mode", "")).strip().upper()
    if operating_mode not in OPERATING_MODE_TRADING_ACTIONS:
        raise RuntimeError(
            "operating_mode must be one of PAPER_SAFE, LIVE_ACTIVE, LIVE_RECONCILE_ONLY"
        )
    return operating_mode


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
    monitor_only: bool = False,
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

    if monitor_only and script_name not in MONITOR_ONLY_ALLOWED_SCRIPTS:
        message = f"MONITOR_ONLYで許可されていない処理です: {script_name}"
        write_log(f"BLOCKED: {message}")
        return (
            False,
            0.0,
            -20,
            message,
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
            env=build_environment(monitor_only=monitor_only),
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
        "Market Regime JSON": (
            REPORT_DIR
            / "market_regime.json"
        ),
        "AI判断CSV": (
            REPORT_DIR
            / "ai_judgement.csv"
        ),
        "取引候補CSV": (
            REPORT_DIR
            / "trade_signals.csv"
        ),
        "取引候補manifest": (
            REPORT_DIR
            / "trade_signals_manifest.json"
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
    *,
    monitor_only: bool = False,
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
    write_log(
        "PHOENIX MONITOR ONLY SUMMARY"
        if monitor_only
        else "PHOENIX OPERATIONAL SUMMARY"
    )
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
            {
                "market_risk_ai.py",
                "market_regime_ai.py",
            },
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
    write_log(
        "Scheduler    : MONITORING"
        if monitor_only
        else "Scheduler    : READY"
    )
    if commit is not None:
        write_log(f"Git Commit   : {commit}")
    write_log(f"Elapsed      : {elapsed_total:.1f} s")
    write_log(f"Exit Code    : {exit_code}")
    write_log("=" * 90)


def _parse_reconciliation_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _is_monitor_only_reconciliation(
    reconciliation_result: object,
    *,
    guardian_status: object,
) -> bool:
    if guardian_status != "READY":
        return False
    if getattr(reconciliation_result, "status", None) != "WARNING":
        return False
    if getattr(reconciliation_result, "reasons", None) != (
        "POSITIONS_PRESENT",
    ):
        return False
    if getattr(reconciliation_result, "mode", None) != "PAPER":
        return False
    orders_submitted = getattr(
        reconciliation_result,
        "orders_submitted",
        None,
    )
    if (
        isinstance(orders_submitted, bool)
        or not isinstance(orders_submitted, int)
        or orders_submitted != 0
    ):
        return False
    positions_count = getattr(reconciliation_result, "positions_count", None)
    if (
        isinstance(positions_count, bool)
        or not isinstance(positions_count, int)
        or positions_count <= 0
    ):
        return False
    if getattr(reconciliation_result, "guardian_status", None) != "READY":
        return False
    if getattr(reconciliation_result, "report_error", None) is not None:
        return False
    if getattr(reconciliation_result, "exit_code", None) != 0:
        return False
    checked_at = _parse_reconciliation_timestamp(
        getattr(reconciliation_result, "checked_at", None)
    )
    source_timestamp = _parse_reconciliation_timestamp(
        getattr(reconciliation_result, "source_timestamp", None)
    )
    if checked_at is None or source_timestamp is None:
        return False
    age_seconds = (checked_at - source_timestamp).total_seconds()
    if age_seconds < 0:
        return False
    if getattr(reconciliation_result, "mode", None) == "PAPER":
        return True
    return age_seconds <= MAX_POSITION_STATE_AGE_SECONDS


def _format_weekly_signal_comparison_counts(counts: dict[str, int]) -> str:
    ordered_keys = ("new", "continued", "upgraded", "downgraded", "excluded")
    return ", ".join(
        f"{key}={counts.get(key, 0)}"
        for key in ordered_keys
    )


def _log_weekly_signal_comparison_result(result: dict[str, Any]) -> None:
    write_log("=" * 90)
    write_log("WEEKLY SIGNAL COMPARISON")
    status = str(result.get("status", "READY"))
    write_log(f"Status       : {status}")

    if status == "SKIPPED":
        selection = result.get("selection")
        if isinstance(selection, dict):
            write_log(
                "Source date  : "
                f"{selection.get('source_report_date') or '-'}"
            )
            write_log(
                "Target date  : "
                f"{selection.get('target_report_date') or '-'}"
            )
        reason = result.get("reason")
        if reason is not None:
            write_log(f"Reason       : {reason}")
        return

    source = result["source"]
    target = result["target"]
    write_log(
        "Source date  : "
        f"{source['report_date']} ({source['report_file']})"
    )
    write_log(
        "Target date  : "
        f"{target['report_date']} ({target['report_file']})"
    )
    write_log(
        "Signal counts: "
        + _format_weekly_signal_comparison_counts(
            result.get("signal_change_counts", {})
        )
    )
    safety = result["safety"]
    write_log(
        "Safety       : "
        f"broker_mode={safety['broker_mode']}, "
        f"orders_submitted={safety['orders_submitted']}, "
        f"trading_actions=DISABLED, "
        f"external_connections={safety['external_connections']}, "
        f"notification_sent={safety['notification_sent']}"
    )
    paths = result.get("paths")
    if isinstance(paths, dict) and paths:
        write_log(
            "Saved to     : "
            + ", ".join(f"{name.upper()}={path}" for name, path in paths.items())
        )


def _run_weekly_signal_comparison() -> dict[str, Any] | None:
    target_date = datetime.now().date()
    try:
        result = run_latest_weekly_signal_comparison(
            target_date,
            report_dir=REPORT_DIR,
            output_dir=REPORT_DIR,
        )
    except Exception as error:
        write_log("=" * 90)
        write_log("WEEKLY SIGNAL COMPARISON OPTIONAL FAILURE")
        write_log(f"Target date  : {target_date.isoformat()}")
        write_log(f"{type(error).__name__}: {error}")
        return None

    _log_weekly_signal_comparison_result(result)
    return result


def _run_main() -> None:
    global _ACTIVE_FAIL_SAFE, _ACTIVE_HEARTBEAT, _ACTIVE_RECOVERY_SESSION
    fail_safe = FailSafeController(
        repository_root=ROOT_DIR,
        log_dir=LOG_DIR,
    )
    _ACTIVE_FAIL_SAFE = fail_safe
    configure_console()
    guardian_result = run_repository_guardian(report_dir=LOG_DIR)
    guardian_status = getattr(
        guardian_result,
        "status",
        "READY" if guardian_result.ready else "BLOCKED",
    )
    fail_safe.update_statuses(guardian_status=guardian_status)
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
        fail_safe.fail_and_exit(
            "GUARDIAN_BLOCKED",
            guardian_status=guardian_status,
        )
    reconciliation_result = run_position_reconciliation(
        guardian_status=guardian_status,
        report_dir=LOG_DIR,
    )
    fail_safe.update_statuses(position_status=reconciliation_result.status)
    monitor_only = _is_monitor_only_reconciliation(
        reconciliation_result,
        guardian_status=guardian_status,
    )
    if reconciliation_result.status != "READY" and not monitor_only:
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
        fail_safe.fail_and_exit(
            "POSITION_BLOCKED",
            position_status=reconciliation_result.status,
        )
    if monitor_only:
        fail_safe.enable_monitor_only()
    raw_restart_attempt = os.environ.get("PHOENIX_WATCHDOG_RESTART_ATTEMPT", "0")
    try:
        watchdog_restart_attempt = int(raw_restart_attempt)
    except ValueError as error:
        raise RuntimeError("WatchDog restart attempt is invalid") from error
    if not 0 <= watchdog_restart_attempt <= MAX_RECOVERY_ATTEMPTS_HARD_LIMIT:
        raise RuntimeError("WatchDog restart attempt is outside the safety limit")
    recovery_result = run_disaster_recovery(
        guardian_status=guardian_status,
        position_status=reconciliation_result.status,
        repository_root=ROOT_DIR,
        expected_repository_root=getattr(
            guardian_result, "expected_root", ROOT_DIR
        ),
        state_path=ROOT_DIR / "runtime" / "guardian" / "recovery_state.json",
        report_dir=LOG_DIR,
        current_mode=reconciliation_result.mode,
        current_orders_submitted=reconciliation_result.orders_submitted,
        watchdog_restart_attempt=watchdog_restart_attempt,
        monitor_only=monitor_only,
        position_reasons=tuple(reconciliation_result.reasons),
    )
    if recovery_result.blocked:
        reasons = ", ".join(recovery_result.recovery_reasons) or "unknown"
        print(
            "PHOENIX START BLOCKED BY DISASTER RECOVERY: " + reasons,
            file=sys.stderr,
            flush=True,
        )
        fail_safe.fail_and_exit("DISASTER_RECOVERY_BLOCKED")
    if recovery_result.recovery_required:
        reasons = ", ".join(recovery_result.recovery_reasons) or "unknown"
        print(
            "PHOENIX RECOVERY CONFIRMATION REQUIRED: " + reasons,
            file=sys.stderr,
            flush=True,
        )
        raise RecoveryRequiredExit(tuple(recovery_result.recovery_reasons))
    recovery_session = RecoverySession(
        state_path=recovery_result.state_path,
        repository_root=ROOT_DIR,
        git_commit=str(recovery_result.current_git_commit),
        guardian_status=guardian_status,
        position_status=reconciliation_result.status,
        position_reasons=tuple(reconciliation_result.reasons),
        monitor_only=monitor_only,
        recovery_attempt=recovery_result.recovery_attempt,
        recovered_at=recovery_result.recovered_at,
    )
    recovery_session.start()
    _ACTIVE_RECOVERY_SESSION = recovery_session
    heartbeat = PhoenixHeartbeat(
        repository_root=ROOT_DIR,
        guardian_status=guardian_status,
        position_reconciliation_status=reconciliation_result.status,
        position_reconciliation_reasons=tuple(reconciliation_result.reasons),
        monitor_only=monitor_only,
    )
    _ACTIVE_HEARTBEAT = heartbeat
    fail_safe.register_background_stopper(
        "heartbeat",
        lambda: heartbeat.stop(status="FAILED", current_stage="FAIL_SAFE"),
    )
    heartbeat.start(
        current_stage="MONITOR_ONLY" if monitor_only else "OPERATIONAL_READY"
    )
    fail_safe.start_monitoring(
        heartbeat_path=heartbeat.heartbeat_path,
        expected_pid=heartbeat.pid,
    )
    print(
        "POSITION RECONCILIATION: " + reconciliation_result.status,
        flush=True,
    )
    print("DISASTER RECOVERY: " + recovery_result.recovery_status, flush=True)
    if monitor_only:
        print("PHOENIX MONITOR ONLY", flush=True)
        print("Mode: PAPER", flush=True)
        print("Orders submitted: 0", flush=True)
        print("Trading actions: DISABLED", flush=True)
    else:
        print("PHOENIX OPERATIONAL READY", flush=True)
    heartbeat.set_stage("INITIALIZE_DIRECTORIES")
    fail_safe.raise_if_triggered()
    initialize_directories()
    fail_safe.raise_if_triggered()
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
    global _ACTIVE_OPERATING_MODE
    try:
        _ACTIVE_OPERATING_MODE = load_operating_mode()
    except RuntimeError as error:
        write_log("PHOENIX OPERATING MODE CONFIG FAILED")
        write_log(str(error))
        raise SystemExit(1) from error
    write_log(f"Operating mode: {_ACTIVE_OPERATING_MODE}")

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
        if not monitor_only or task["script"] in MONITOR_ONLY_ALLOWED_SCRIPTS
    ]
    for task in selected_tasks:
        fail_safe.raise_if_triggered()
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
                monitor_only=monitor_only,
            )
        )
        fail_safe.raise_if_triggered()

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

    fail_safe.raise_if_triggered()
    heartbeat.set_stage("VERIFY_OUTPUTS")
    output_results = verify_output_files(refresh_only=args.refresh_only)

    fail_safe.raise_if_triggered()
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

    if not required_failures and not missing_outputs:
        _run_weekly_signal_comparison()

    heartbeat.set_stage("FINAL_SUMMARY")
    print_final_summary(
        task_results=task_results,
        output_results=output_results,
        started_at=started_at,
    )

    print_morning_run_summary(
        task_results=task_results,
        output_results=output_results,
        started_at=started_at,
        monitor_only=monitor_only,
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


def _finish_active_recovery(
    status: str,
    heartbeat_status: str,
    fail_safe_status: str,
    *,
    preserve_active_exception: bool,
) -> None:
    session = _ACTIVE_RECOVERY_SESSION
    if session is None:
        return
    try:
        session.finish(
            status=status,
            heartbeat_status=heartbeat_status,
            fail_safe_status=fail_safe_status,
        )
    except Exception as error:
        if not preserve_active_exception:
            raise
        print(
            "Disaster Recovery finalization failed while preserving the active "
            f"exception: {type(error).__name__}: {error}",
            file=sys.stderr,
            flush=True,
        )


def main() -> None:
    global _ACTIVE_FAIL_SAFE, _ACTIVE_HEARTBEAT, _ACTIVE_RECOVERY_SESSION
    _ACTIVE_FAIL_SAFE = None
    _ACTIVE_HEARTBEAT = None
    _ACTIVE_RECOVERY_SESSION = None
    try:
        _run_main()
    except KeyboardInterrupt:
        if _ACTIVE_FAIL_SAFE is not None:
            _ACTIVE_FAIL_SAFE.stop_monitoring()
        _stop_active_heartbeat(
            "STOPPED",
            "INTERRUPTED",
            preserve_active_exception=True,
        )
        _finish_active_recovery(
            "INTERRUPTED",
            "STOPPED",
            "NOT_TRIGGERED",
            preserve_active_exception=True,
        )
        raise
    except SystemExit:
        raise
    except BaseException as error:
        fail_safe = _ACTIVE_FAIL_SAFE
        if isinstance(error, RecoveryRequiredExit):
            if fail_safe is not None:
                fail_safe.stop_monitoring()
            raise
        if fail_safe is None:
            _stop_active_heartbeat(
                "FAILED",
                "FAILED",
                preserve_active_exception=True,
            )
            _finish_active_recovery(
                "FAILED",
                "FAILED",
                "NOT_TRIGGERED",
                preserve_active_exception=True,
            )
            raise
        if isinstance(error, FailSafeExit):
            fail_safe.stop_monitoring()
            _finish_active_recovery(
                "FAILED",
                "FAILED",
                "BLOCKED",
                preserve_active_exception=True,
            )
            raise
        fail_safe.transition(
            "UNCAUGHT_EXCEPTION",
            heartbeat_status="FAILED",
        )
        fail_safe.stop_monitoring()
        _finish_active_recovery(
            "FAILED",
            "FAILED",
            "BLOCKED",
            preserve_active_exception=True,
        )
        raise FailSafeExit("UNCAUGHT_EXCEPTION") from error
    else:
        if _ACTIVE_FAIL_SAFE is not None:
            if _ACTIVE_FAIL_SAFE.triggered:
                _finish_active_recovery(
                    "FAILED",
                    "FAILED",
                    "BLOCKED",
                    preserve_active_exception=True,
                )
                _ACTIVE_FAIL_SAFE.raise_if_triggered()
            _ACTIVE_FAIL_SAFE.stop_monitoring()
        _stop_active_heartbeat(
            "COMPLETED",
            "COMPLETED",
            preserve_active_exception=False,
        )
        _finish_active_recovery(
            "COMPLETED",
            "COMPLETED",
            "NOT_TRIGGERED",
            preserve_active_exception=False,
        )
    finally:
        if _ACTIVE_FAIL_SAFE is not None:
            _ACTIVE_FAIL_SAFE.stop_monitoring()
        _ACTIVE_RECOVERY_SESSION = None
        _ACTIVE_FAIL_SAFE = None
        _ACTIVE_HEARTBEAT = None


if __name__ == "__main__":
    main()
