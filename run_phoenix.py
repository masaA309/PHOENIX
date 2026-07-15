# run_phoenix.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import subprocess
import sys
import time
from typing import Any


LOG_DIR = Path("logs")

LOG_FILE = LOG_DIR / (
    "phoenix_"
    + datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    + ".log"
)


TASKS: list[dict[str, Any]] = [
    {
        "name": "日経225構成銘柄更新",
        "file": "get_nikkei225.py",
        "required": True,
    },
    {
        "name": "PHOENIX日次レポート",
        "file": "daily_report.py",
        "required": True,
    },
    {
        "name": "自己学習プロフィール更新",
        "file": "learning_engine.py",
        "required": False,
    },
    {
        "name": "自己学習AI売買判断",
        "file": "ai_judgement.py",
        "required": True,
    },
    {
        "name": "チャート生成",
        "file": "chart_generator.py",
        "required": True,
    },
    {
        "name": "LINE・Discord通知",
        "file": "notify.py",
        "required": True,
    },
]


def safe_text(
    value: Any,
) -> str:
    return (
        str(value)
        .replace(
            "\u2013",
            "-",
        )
        .replace(
            "\u2014",
            "-",
        )
        .replace(
            "\u2212",
            "-",
        )
    )


def write_log(
    message: Any,
) -> None:
    text = safe_text(
        message
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

    environment[
        "PYTHONIOENCODING"
    ] = "utf-8"

    environment[
        "PYTHONUTF8"
    ] = "1"

    return environment


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


def run_script(
    task: dict[str, Any],
) -> bool:
    task_name = str(
        task["name"]
    )

    script_file = Path(
        str(
            task["file"]
        )
    )

    required = bool(
        task.get(
            "required",
            False,
        )
    )

    if not script_file.exists():
        if required:
            write_log(
                f"FAILED: {task_name}"
            )

            write_log(
                f"{script_file} がありません。"
            )

            return False

        write_log(
            f"SKIP: {task_name}"
        )

        write_log(
            f"{script_file} がありません。"
        )

        return True

    write_log("")
    write_log("=" * 80)

    write_log(
        f"START: {task_name}"
    )

    write_log(
        f"FILE : {script_file}"
    )

    write_log("=" * 80)

    started_at = time.time()

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                str(script_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=build_environment(),
        )

    except Exception as error:
        write_log(
            f"起動エラー: {error}"
        )

        return False

    if process.stdout is not None:
        for line in process.stdout:
            write_log(
                line.rstrip()
            )

    return_code = process.wait()

    elapsed = (
        time.time()
        - started_at
    )

    if return_code == 0:
        write_log(
            f"SUCCESS: {task_name}"
        )

        write_log(
            f"処理時間: {elapsed:.1f}秒"
        )

        return True

    write_log(
        f"FAILED: {task_name}"
    )

    write_log(
        f"終了コード: {return_code}"
    )

    write_log(
        f"処理時間: {elapsed:.1f}秒"
    )

    return False


def main() -> None:
    configure_console()

    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_log("=" * 80)
    write_log("PHOENIX MASTER RUN")

    write_log(
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    write_log("=" * 80)

    success_count = 0
    failed_tasks: list[str] = []

    for task in TASKS:
        success = run_script(
            task
        )

        if success:
            success_count += 1
            continue

        task_name = str(
            task["name"]
        )

        failed_tasks.append(
            task_name
        )

        if bool(
            task.get(
                "required",
                False,
            )
        ):
            write_log("")
            write_log(
                "必須処理が失敗したため、"
                "後続処理を中止します。"
            )

            break

    write_log("")
    write_log("=" * 80)
    write_log("PHOENIX MASTER RESULT")
    write_log("=" * 80)

    write_log(
        f"成功: {success_count}"
    )

    write_log(
        f"失敗: {len(failed_tasks)}"
    )

    if failed_tasks:
        for task_name in failed_tasks:
            write_log(
                f"- {task_name}"
            )

    else:
        write_log(
            "すべての処理が完了しました。"
        )

    write_log(
        f"ログ保存先: {LOG_FILE}"
    )

    write_log("=" * 80)

    if failed_tasks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()