# run_phoenix.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import subprocess
import sys
import time
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
REPORT_DIR = ROOT_DIR / "reports"

LOG_FILE = LOG_DIR / (
    "phoenix_"
    + datetime.now().strftime("%Y%m%d")
    + ".log"
)

PROCESS_TIMEOUT_SECONDS = 1800


TASKS = [
    {
        "name": "日経225構成銘柄更新",
        "script": "get_nikkei225.py",
        "required": True,
    },
    {
        "name": "日次スキャン・レポート",
        "script": "daily_report.py",
        "required": True,
    },
    {
        "name": "自己学習エンジン",
        "script": "learning_engine.py",
        "required": False,
    },
    {
        "name": "AI売買判断",
        "script": "ai_judgement.py",
        "required": True,
    },
    {
        "name": "監視優先ランキングAI",
        "script": "ranking_ai.py",
        "required": True,
    },
    {
        "name": "チャート自動生成",
        "script": "chart_generator.py",
        "required": True,
    },
    {
        "name": "LINE・Discord通知",
        "script": "notify.py",
        "required": True,
    },
]


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
    ) as file:
        file.write(
            text + "\n"
        )


def build_environment() -> dict[str, str]:
    environment = os.environ.copy()

    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"

    return environment


def run_script(
    task_name: str,
    script_name: str,
) -> tuple[
    bool,
    float,
    int,
]:
    script_path = ROOT_DIR / script_name

    write_log("=" * 90)
    write_log(f"START: {task_name}")
    write_log(f"SCRIPT: {script_name}")

    if not script_path.exists():
        write_log(
            f"FAILED: ファイルがありません: "
            f"{script_path}"
        )

        return (
            False,
            0.0,
            -1,
        )

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(script_path),
    ]

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

        write_log(
            f"FAILED: {task_name}"
        )

        write_log(
            f"タイムアウト: "
            f"{PROCESS_TIMEOUT_SECONDS}秒"
        )

        return (
            False,
            elapsed,
            -2,
        )

    except Exception as error:
        elapsed = (
            time.time()
            - started_at
        )

        write_log(
            f"FAILED: {task_name}"
        )

        write_log(
            f"起動エラー: {error}"
        )

        return (
            False,
            elapsed,
            -3,
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
            write_log(line)

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
        )

    write_log(
        f"FAILED: {task_name}"
    )

    write_log(
        f"終了コード: "
        f"{process.returncode}"
    )

    write_log(
        f"処理時間: {elapsed:.1f}秒"
    )

    return (
        False,
        elapsed,
        process.returncode,
    )


def verify_output_files() -> dict[str, bool]:
    today = datetime.now().strftime(
        "%Y%m%d"
    )

    expected_files = {
        "日次CSV": (
            REPORT_DIR
            / f"report_{today}.csv"
        ),
        "AI判断CSV": (
            REPORT_DIR
            / "ai_judgement.csv"
        ),
        "ランキングCSV": (
            REPORT_DIR
            / "ranking_ai.csv"
        ),
        "ランキングTXT": (
            REPORT_DIR
            / "ranking_ai.txt"
        ),
    }

    results: dict[str, bool] = {}

    write_log("=" * 90)
    write_log("出力ファイル確認")

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

    success_count = sum(
        1
        for result in task_results
        if result["success"]
    )

    failure_count = (
        len(task_results)
        - success_count
    )

    required_failures = [
        result
        for result in task_results
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
    write_log("PHOENIX DAILY RESULT")
    write_log("=" * 90)

    for result in task_results:
        status = (
            "SUCCESS"
            if result["success"]
            else "FAILED"
        )

        required_text = (
            "必須"
            if result["required"]
            else "任意"
        )

        write_log(
            f"{status:<7} "
            f"{result['name']} "
            f"({required_text}) "
            f"{result['elapsed']:.1f}秒"
        )

    write_log("-" * 90)

    write_log(
        f"成功: {success_count}件"
    )

    write_log(
        f"失敗: {failure_count}件"
    )

    write_log(
        f"総処理時間: "
        f"{elapsed_total:.1f}秒"
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


def main() -> None:
    configure_console()

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    started_at = time.time()

    write_log("=" * 90)
    write_log("PHOENIX DAILY AUTOMATION START")
    write_log("=" * 90)

    write_log(
        f"Python: {sys.executable}"
    )

    write_log(
        f"作業フォルダ: {ROOT_DIR}"
    )

    task_results: list[
        dict[str, Any]
    ] = []

    required_task_failed = False

    for task in TASKS:
        if required_task_failed:
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
            })

            continue

        success, elapsed, returncode = (
            run_script(
                task_name=task["name"],
                script_name=task["script"],
            )
        )

        task_results.append({
            "name": task["name"],
            "script": task["script"],
            "required": task["required"],
            "success": success,
            "elapsed": elapsed,
            "returncode": returncode,
            "skipped": False,
        })

        if (
            task["required"]
            and not success
        ):
            required_task_failed = True

    output_results = (
        verify_output_files()
    )

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
        )
    ]

    missing_outputs = [
        name
        for name, exists
        in output_results.items()
        if not exists
    ]

    if (
        required_failures
        or missing_outputs
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()