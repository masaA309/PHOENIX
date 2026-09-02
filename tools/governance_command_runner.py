from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import threading
from typing import BinaryIO, Sequence


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout_path: str
    stderr_path: str
    stdout_bytes: int
    stderr_bytes: int
    output_limit_exceeded: bool


def run_command(
    command: Sequence[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
) -> CommandResult:
    if not isinstance(command, (list, tuple)) or not command:
        raise ValueError("command must be a non-empty JSON array")
    if max_stdout_bytes <= 0 or max_stderr_bytes <= 0:
        raise ValueError("output limits must be positive")
    resolved_cwd = cwd.resolve()
    stdout_path = stdout_path.resolve()
    stderr_path = stderr_path.resolve()
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=resolved_cwd,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    exceeded = threading.Event()
    counts = {"stdout": 0, "stderr": 0}

    def stream(source: BinaryIO, destination: BinaryIO, name: str, limit: int) -> None:
        while True:
            chunk = source.read(8192)
            if not chunk:
                break
            remaining = limit - counts[name]
            if remaining > 0:
                destination.write(chunk[:remaining])
                destination.flush()
                counts[name] += min(len(chunk), remaining)
            if len(chunk) > remaining:
                exceeded.set()
                process.terminate()
                break

    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        stdout_thread = threading.Thread(
            target=stream,
            args=(process.stdout, stdout_file, "stdout", max_stdout_bytes),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=stream,
            args=(process.stderr, stderr_file, "stderr", max_stderr_bytes),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        try:
            returncode = process.wait()
        finally:
            if exceeded.is_set() and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
    if exceeded.is_set():
        returncode = returncode if returncode != 0 else 1
    return CommandResult(
        returncode=returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        stdout_bytes=counts["stdout"],
        stderr_bytes=counts["stderr"],
        output_limit_exceeded=exceeded.is_set(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--stdout", required=True)
    parser.add_argument("--stderr", required=True)
    parser.add_argument("--max-stdout-bytes", required=True, type=int)
    parser.add_argument("--max-stderr-bytes", required=True, type=int)
    args = parser.parse_args(argv)
    command = json.loads(args.command)
    if not isinstance(command, list) or not all(isinstance(item, str) for item in command):
        raise ValueError("command must be a JSON string array")
    result = run_command(
        command,
        Path(args.cwd),
        Path(args.stdout),
        Path(args.stderr),
        args.max_stdout_bytes,
        args.max_stderr_bytes,
    )
    print(f"COMMAND_RESULT:{'FAIL' if result.returncode else 'PASS'}")
    print(f"RETURN_CODE:{result.returncode}")
    print(f"OUTPUT_LIMIT_EXCEEDED:{str(result.output_limit_exceeded).upper()}")
    print(f"STDOUT_BYTES:{result.stdout_bytes}")
    print(f"STDERR_BYTES:{result.stderr_bytes}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
