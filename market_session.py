# market_session.py

from __future__ import annotations

from datetime import datetime, time as clock_time
from pathlib import Path
import argparse
import os
import subprocess
import sys
import time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


JST = ZoneInfo("Asia/Tokyo")

ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
REPORT_DIR = ROOT_DIR / "reports"

PRICE_MONITOR_FILE = ROOT_DIR / "price_monitor.py"
PAPER_TRADER_FILE = ROOT_DIR / "paper_trader.py"

STATE_FILE = REPORT_DIR / "price_monitor_state.csv"
LOCK_FILE = REPORT_DIR / "market_session.lock"

MORNING_OPEN = clock_time(9, 0)
MORNING_CLOSE = clock_time(11, 30)

AFTERNOON_OPEN = clock_time(12, 30)
AFTERNOON_CLOSE = clock_time(15, 30)

DEFAULT_INTERVAL_SECONDS = 300
MIN_INTERVAL_SECONDS = 60
PROCESS_TIMEOUT_SECONDS = 240


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


def now_jst() -> datetime:
    return datetime.now(
        JST,
    )


def today_text() -> str:
    return now_jst().strftime(
        "%Y-%m-%d",
    )


def timestamp_text() -> str:
    return now_jst().strftime(
        "%Y-%m-%d %H:%M:%S",
    )


def get_log_file() -> Path:
    return LOG_DIR / (
        "market_session_"
        + now_jst().strftime(
            "%Y%m%d",
        )
        + ".log"
    )


def write_log(
    message: Any,
) -> None:
    LOG_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    text = (
        f"[{timestamp_text()}] "
        f"{message}"
    )

    print(
        text,
        flush=True,
    )

    with open(
        get_log_file(),
        "a",
        encoding="utf-8",
        newline="\n",
    ) as file:
        file.write(
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


def process_is_running(
    process_id: int,
) -> bool:
    if process_id <= 0:
        return False

    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"PID eq {process_id}",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )

            output = result.stdout.strip()

            return (
                str(process_id) in output
                and "情報:" not in output
                and "INFO:" not in output
            )

        except Exception:
            return False

    try:
        os.kill(
            process_id,
            0,
        )

        return True

    except (
        ProcessLookupError,
        PermissionError,
        OSError,
    ):
        return False


def acquire_lock() -> None:
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if LOCK_FILE.exists():
        try:
            stored_pid = int(
                LOCK_FILE.read_text(
                    encoding="utf-8",
                ).strip()
            )

        except (
            OSError,
            ValueError,
        ):
            stored_pid = 0

        if process_is_running(
            stored_pid,
        ):
            raise RuntimeError(
                "市場監視はすでに起動しています。"
                f" PID={stored_pid}"
            )

        try:
            LOCK_FILE.unlink()

        except OSError:
            pass

    LOCK_FILE.write_text(
        str(
            os.getpid()
        ),
        encoding="utf-8",
    )


def release_lock() -> None:
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()

    except OSError:
        pass


def is_weekday(
    current: datetime,
) -> bool:
    return current.weekday() < 5


def is_morning_session(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and MORNING_OPEN
        <= current.time()
        <= MORNING_CLOSE
    )


def is_afternoon_session(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and AFTERNOON_OPEN
        <= current.time()
        <= AFTERNOON_CLOSE
    )


def is_trading_session(
    current: datetime,
) -> bool:
    return (
        is_morning_session(current)
        or is_afternoon_session(current)
    )


def is_before_market_open(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and current.time()
        < MORNING_OPEN
    )


def is_lunch_break(
    current: datetime,
) -> bool:
    return (
        is_weekday(current)
        and MORNING_CLOSE
        < current.time()
        < AFTERNOON_OPEN
    )


def market_has_closed(
    current: datetime,
) -> bool:
    return (
        not is_weekday(current)
        or current.time()
        > AFTERNOON_CLOSE
    )


def seconds_until(
    current: datetime,
    target_time: clock_time,
) -> int:
    target = current.replace(
        hour=target_time.hour,
        minute=target_time.minute,
        second=0,
        microsecond=0,
    )

    return max(
        int(
            (
                target
                - current
            ).total_seconds()
        ),
        0,
    )


def seconds_until_next_interval(
    interval_seconds: int,
) -> int:
    current_seconds = int(
        time.time()
    )

    remainder = (
        current_seconds
        % interval_seconds
    )

    wait_seconds = (
        interval_seconds
        - remainder
    )

    return max(
        wait_seconds,
        1,
    )


def state_is_for_today() -> bool:
    if not STATE_FILE.exists():
        return False

    try:
        state = pd.read_csv(
            STATE_FILE,
        )

    except Exception:
        return False

    if (
        state.empty
        or "監視日"
        not in state.columns
    ):
        return False

    dates = (
        state["監視日"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    return today_text() in dates


def run_python_script(
    task_name: str,
    script_file: Path,
    arguments: list[str] | None = None,
) -> bool:
    if arguments is None:
        arguments = []

    if not script_file.exists():
        write_log(
            f"FAILED: {task_name}"
        )

        write_log(
            f"ファイルがありません: "
            f"{script_file}"
        )

        return False

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(
            script_file
        ),
        *arguments,
    ]

    write_log(
        "=" * 80
    )

    write_log(
        f"START: {task_name}"
    )

    write_log(
        "COMMAND: "
        + " ".join(
            command
        )
    )

    started_at = time.time()

    try:
        process = subprocess.run(
            command,
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=(
                PROCESS_TIMEOUT_SECONDS
            ),
            env=build_environment(),
            check=False,
        )

    except subprocess.TimeoutExpired:
        write_log(
            f"FAILED: {task_name}"
        )

        write_log(
            "処理がタイムアウトしました。"
        )

        return False

    except Exception as error:
        write_log(
            f"FAILED: {task_name}"
        )

        write_log(
            f"起動エラー: {error}"
        )

        return False

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

    elapsed = (
        time.time()
        - started_at
    )

    if process.returncode == 0:
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
        f"終了コード: "
        f"{process.returncode}"
    )

    write_log(
        f"処理時間: {elapsed:.1f}秒"
    )

    return False


def run_market_cycle(
    live: bool,
    force_reset: bool,
) -> bool:
    monitor_arguments = [
        "--once",
    ]

    if live:
        monitor_arguments.append(
            "--live"
        )

    reset_required = (
        force_reset
        or not state_is_for_today()
    )

    if reset_required:
        monitor_arguments.append(
            "--reset"
        )

        write_log(
            "本日の初回監視です。"
            "現在価格登録のみ行います。"
        )

    monitor_success = run_python_script(
        task_name="価格監視",
        script_file=PRICE_MONITOR_FILE,
        arguments=monitor_arguments,
    )

    if not monitor_success:
        write_log(
            "価格監視失敗のため、"
            "今回のペーパートレード処理を"
            "スキップします。"
        )

        return False

    trader_success = run_python_script(
        task_name="ペーパートレード更新",
        script_file=PAPER_TRADER_FILE,
    )

    return trader_success


def run_single_cycle(
    live: bool,
    force_reset: bool,
    force: bool,
) -> None:
    current = now_jst()

    if (
        not force
        and not is_trading_session(
            current
        )
    ):
        write_log(
            "市場時間外です。"
            " --force を付けると"
            "テスト実行できます。"
        )

        return

    success = run_market_cycle(
        live=live,
        force_reset=force_reset,
    )

    if success:
        write_log(
            "1回監視が正常終了しました。"
        )

    else:
        raise SystemExit(
            1
        )


def monitor_session(
    interval_seconds: int,
    live: bool,
    force_reset: bool,
) -> None:
    write_log(
        "=" * 80
    )

    write_log(
        "PHOENIX MARKET SESSION START"
    )

    write_log(
        "通知モード: "
        + (
            "LIVE"
            if live
            else "DRY RUN"
        )
    )

    write_log(
        f"監視間隔: "
        f"{interval_seconds}秒"
    )

    first_cycle = True

    while True:
        current = now_jst()

        if not is_weekday(
            current
        ):
            write_log(
                "土日のため終了します。"
            )

            break

        if is_before_market_open(
            current
        ):
            wait_seconds = seconds_until(
                current,
                MORNING_OPEN,
            )

            write_log(
                f"市場開始待機: "
                f"{wait_seconds}秒"
            )

            time.sleep(
                min(
                    wait_seconds,
                    300,
                )
            )

            continue

        if is_lunch_break(
            current
        ):
            wait_seconds = seconds_until(
                current,
                AFTERNOON_OPEN,
            )

            write_log(
                f"昼休み待機: "
                f"{wait_seconds}秒"
            )

            time.sleep(
                min(
                    wait_seconds,
                    300,
                )
            )

            continue

        if market_has_closed(
            current
        ):
            write_log(
                "取引時間終了"
            )

            break

        if not is_trading_session(
            current
        ):
            time.sleep(
                30
            )

            continue

        cycle_success = run_market_cycle(
            live=live,
            force_reset=(
                force_reset
                and first_cycle
            ),
        )

        first_cycle = False

        if not cycle_success:
            write_log(
                "今回の監視処理に失敗しました。"
                "次回周期で再試行します。"
            )

        wait_seconds = (
            seconds_until_next_interval(
                interval_seconds
            )
        )

        write_log(
            f"次回監視まで "
            f"{wait_seconds}秒"
        )

        time.sleep(
            wait_seconds
        )

    run_python_script(
        task_name="終了時ペーパートレード集計",
        script_file=PAPER_TRADER_FILE,
    )

    write_log(
        "PHOENIX MARKET SESSION END"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PHOENIX市場時間自動監視"
        )
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="監視を1回だけ実行",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "LINE・Discordへ"
            "外部通知しない"
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "市場時間外でも"
            "1回実行する"
        ),
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "本日の監視状態を"
            "初期化する"
        ),
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=(
            DEFAULT_INTERVAL_SECONDS
        ),
        help="監視間隔秒数",
    )

    return parser.parse_args()


def main() -> None:
    configure_console()

    arguments = parse_arguments()

    interval_seconds = max(
        arguments.interval,
        MIN_INTERVAL_SECONDS,
    )

    live = not arguments.dry_run

    try:
        acquire_lock()

        if arguments.once:
            run_single_cycle(
                live=live,
                force_reset=arguments.reset,
                force=arguments.force,
            )

            return

        monitor_session(
            interval_seconds=(
                interval_seconds
            ),
            live=live,
            force_reset=arguments.reset,
        )

    except KeyboardInterrupt:
        write_log(
            "手動停止しました。"
        )

    except Exception as error:
        write_log(
            f"エラー: {error}"
        )

        raise SystemExit(
            1
        )

    finally:
        release_lock()


if __name__ == "__main__":
    main()