from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from phoenix_core.environment_validator import EnvironmentValidator, print_report


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = ROOT_DIR / "config" / "v7_environment.json"
SCHEDULER_FILE = ROOT_DIR / "scheduled_runner_v7.py"


def main() -> int:
    environment_only = "--environment-only" in sys.argv[1:]
    forwarded_arguments = [
        argument for argument in sys.argv[1:] if argument != "--environment-only"
    ]

    try:
        validator = EnvironmentValidator.from_file(
            root=ROOT_DIR,
            config_path=CONFIG_FILE,
        )
        report = validator.run_and_save()
    except Exception as error:
        print("ENVIRONMENT GATE ERROR")
        print(f"{type(error).__name__}: {error}")
        print("TRADING DISABLED")
        return 2

    print_report(report)
    if not report.ready:
        print("TRADING DISABLED")
        return 2
    if environment_only:
        return 0
    if not SCHEDULER_FILE.is_file():
        print("scheduled_runner_v7.py was not found")
        return 3

    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(SCHEDULER_FILE),
        *forwarded_arguments,
    ]
    try:
        process = subprocess.run(
            command,
            cwd=ROOT_DIR,
            env=environment,
            check=False,
        )
    except OSError as error:
        print("SCHEDULER START FAILED")
        print(f"{type(error).__name__}: {error}")
        return 4
    return int(process.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
