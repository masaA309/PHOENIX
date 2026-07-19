from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentReport:
    root: str
    started_at: str
    finished_at: str
    duration_ms: int
    results: tuple[CheckResult, ...]

    @property
    def ready(self) -> bool:
        return not any(result.status == "FAIL" for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "ready": self.ready,
            "root": self.root,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "summary": {
                "pass": sum(result.status == "PASS" for result in self.results),
                "warn": sum(result.status == "WARN" for result in self.results),
                "fail": sum(result.status == "FAIL" for result in self.results),
            },
            "results": [result.to_dict() for result in self.results],
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_version(value: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for part in value.split(".")[:3]:
        digits = "".join(character for character in part if character.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        value = json.load(file)
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


class EnvironmentValidator:
    def __init__(self, root: Path | str, config: dict[str, Any]) -> None:
        self.root = Path(root).resolve()
        self.config = config
        if config.get("schema_version") != 1:
            raise ValueError("Unsupported environment schema_version")

    @classmethod
    def from_file(
        cls,
        root: Path | str,
        config_path: Path | str,
    ) -> "EnvironmentValidator":
        root_path = Path(root).resolve()
        path = Path(config_path)
        if not path.is_absolute():
            path = root_path / path
        path = path.resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Environment config not found: {path}")
        return cls(root=root_path, config=read_json(path))

    def resolve_path(self, relative_path: str) -> Path:
        raw_path = Path(relative_path)
        path = (raw_path if raw_path.is_absolute() else self.root / raw_path).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ValueError(
                f"Configured path escapes project root: {relative_path}"
            ) from error
        return path

    @staticmethod
    def passed(name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status="PASS", message=message)

    @staticmethod
    def warned(name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status="WARN", message=message)

    @staticmethod
    def failed(name: str, message: str) -> CheckResult:
        return CheckResult(name=name, status="FAIL", message=message)

    def check_python(self) -> list[CheckResult]:
        minimum = parse_version(str(self.config.get("minimum_python", "3.11.0")))
        current = tuple(sys.version_info[:3])
        if current < minimum:
            return [self.failed("python_version", f"{current} is below {minimum}")]
        return [self.passed("python_version", sys.version.split()[0])]

    def check_virtual_environment(self) -> list[CheckResult]:
        required = bool(self.config.get("require_virtual_environment", True))
        active = sys.prefix != sys.base_prefix or bool(os.environ.get("VIRTUAL_ENV"))
        if active:
            return [self.passed("virtual_environment", sys.prefix)]
        if required:
            return [self.failed("virtual_environment", "Virtual environment is not active")]
        return [self.warned("virtual_environment", "Virtual environment is not required")]

    def check_modules(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        for module_name in self.config.get("required_modules", []):
            name = str(module_name)
            if importlib.util.find_spec(name) is None:
                results.append(self.failed(f"module:{name}", "Module not found"))
            else:
                results.append(self.passed(f"module:{name}", "Module available"))
        return results

    def check_directories(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        for directory_name in self.config.get("required_directories", []):
            path = self.resolve_path(str(directory_name))
            if path.is_dir():
                results.append(self.passed(f"directory:{directory_name}", str(path)))
            else:
                results.append(self.failed(f"directory:{directory_name}", "Directory not found"))

        for directory_name in self.config.get("create_directories", []):
            path = self.resolve_path(str(directory_name))
            path.mkdir(parents=True, exist_ok=True)
            if path.is_dir():
                results.append(self.passed(f"directory:{directory_name}", "Directory ready"))
            else:
                results.append(self.failed(f"directory:{directory_name}", "Directory creation failed"))
        return results

    def check_files(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        for file_name in self.config.get("required_files", []):
            path = self.resolve_path(str(file_name))
            if not path.is_file():
                results.append(self.failed(f"file:{file_name}", "Required file not found"))
            elif path.stat().st_size <= 0:
                results.append(self.failed(f"file:{file_name}", "File is empty"))
            else:
                results.append(self.passed(f"file:{file_name}", "File ready"))
        return results

    def check_json_files(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        for file_name in self.config.get("required_json_files", []):
            path = self.resolve_path(str(file_name))
            if not path.is_file():
                results.append(self.failed(f"json:{file_name}", "JSON file not found"))
                continue
            try:
                with path.open("r", encoding="utf-8-sig") as file:
                    json.load(file)
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                results.append(
                    self.failed(f"json:{file_name}", f"{type(error).__name__}: {error}")
                )
            else:
                results.append(self.passed(f"json:{file_name}", "Valid JSON"))
        return results

    def check_sources(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        for file_name in self.config.get("source_files", []):
            path = self.resolve_path(str(file_name))
            if not path.is_file():
                results.append(self.failed(f"source:{file_name}", "Source file not found"))
                continue
            try:
                source = path.read_text(encoding="utf-8-sig")
            except UnicodeError as error:
                results.append(self.failed(f"source:{file_name}", f"UTF-8 error: {error}"))
                continue
            if "\ufffd" in source:
                results.append(
                    self.failed(f"source:{file_name}", "Replacement character detected")
                )
                continue
            if "\x00" in source:
                results.append(self.failed(f"source:{file_name}", "NUL character detected"))
                continue
            try:
                if path.suffix.lower() == ".py":
                    compile(source, str(path), "exec")
                elif path.suffix.lower() == ".json":
                    json.loads(source)
            except (SyntaxError, json.JSONDecodeError) as error:
                results.append(
                    self.failed(f"source:{file_name}", f"{type(error).__name__}: {error}")
                )
            else:
                results.append(self.passed(f"source:{file_name}", "UTF-8 and syntax passed"))
        return results

    def check_writable_directories(self) -> list[CheckResult]:
        results: list[CheckResult] = []
        for directory_name in self.config.get("writable_directories", []):
            path = self.resolve_path(str(directory_name))
            path.mkdir(parents=True, exist_ok=True)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    dir=path,
                    prefix=".phoenix_",
                    suffix=".tmp",
                    delete=False,
                ) as file:
                    file.write(b"PHOENIX")
                    file.flush()
                    os.fsync(file.fileno())
                    temporary_path = Path(file.name)
                temporary_path.unlink()
                results.append(self.passed(f"writable:{directory_name}", "Write test passed"))
            except OSError as error:
                if temporary_path is not None and temporary_path.exists():
                    try:
                        temporary_path.unlink()
                    except OSError:
                        pass
                results.append(
                    self.failed(f"writable:{directory_name}", f"{type(error).__name__}: {error}")
                )
        return results

    def check_disk_space(self) -> list[CheckResult]:
        minimum_mb = int(self.config.get("minimum_free_disk_mb", 512))
        free_mb = int(shutil.disk_usage(self.root).free / 1024 / 1024)
        if free_mb < minimum_mb:
            return [self.failed("disk_space", f"{free_mb} MB free")]
        return [self.passed("disk_space", f"{free_mb} MB free")]

    def check_powershell(self) -> list[CheckResult]:
        scripts = self.config.get("powershell_scripts", [])
        if not scripts:
            return []
        if os.name != "nt":
            return [self.warned("powershell_parser", "Skipped on non-Windows system")]

        executable = (
            shutil.which("powershell.exe")
            or shutil.which("pwsh.exe")
            or shutil.which("pwsh")
        )
        if executable is None:
            return [self.failed("powershell_parser", "PowerShell executable not found")]

        results: list[CheckResult] = []
        for file_name in scripts:
            path = self.resolve_path(str(file_name))
            if not path.is_file():
                results.append(
                    self.failed(f"powershell:{file_name}", "PowerShell file not found")
                )
                continue

            escaped_path = str(path).replace("'", "''")
            command = (
                "$tokens=$null;"
                "$errors=$null;"
                "[System.Management.Automation.Language.Parser]::ParseFile("
                f"'{escaped_path}',[ref]$tokens,[ref]$errors) | Out-Null;"
                "if($errors.Count -gt 0){"
                "$errors | ForEach-Object { Write-Error $_.Message }; exit 1}"
            )
            encoded_command = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
            try:
                process = subprocess.run(
                    [
                        executable,
                        "-NoProfile",
                        "-NonInteractive",
                        "-EncodedCommand",
                        encoded_command,
                    ],
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                results.append(
                    self.failed(f"powershell:{file_name}", f"{type(error).__name__}: {error}")
                )
                continue
            if process.returncode != 0:
                message = process.stderr.strip() or process.stdout.strip() or "PowerShell parser error"
                results.append(self.failed(f"powershell:{file_name}", message))
            else:
                results.append(
                    self.passed(f"powershell:{file_name}", "PowerShell syntax passed")
                )
        return results

    def run_group(
        self,
        group_name: str,
        callback: Callable[[], list[CheckResult]],
    ) -> list[CheckResult]:
        try:
            return callback()
        except Exception as error:
            return [self.failed(group_name, f"{type(error).__name__}: {error}")]

    def run(self) -> EnvironmentReport:
        started_at = utc_now()
        started_time = time.monotonic()
        checks = (
            ("python", self.check_python),
            ("virtual_environment", self.check_virtual_environment),
            ("modules", self.check_modules),
            ("directories", self.check_directories),
            ("files", self.check_files),
            ("json", self.check_json_files),
            ("sources", self.check_sources),
            ("writable", self.check_writable_directories),
            ("disk", self.check_disk_space),
            ("powershell", self.check_powershell),
        )
        results: list[CheckResult] = []
        for group_name, callback in checks:
            results.extend(self.run_group(group_name, callback))
        duration_ms = int((time.monotonic() - started_time) * 1000)
        return EnvironmentReport(
            root=str(self.root),
            started_at=started_at,
            finished_at=utc_now(),
            duration_ms=duration_ms,
            results=tuple(results),
        )

    def report_path(self) -> Path:
        return self.resolve_path(
            str(self.config.get("report_file", "reports/v7_environment_report.json"))
        )

    def save_report(self, report: EnvironmentReport) -> Path:
        target = self.report_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                json.dump(report.to_dict(), file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
                temporary_path = Path(file.name)
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
        return target

    def run_and_save(self) -> EnvironmentReport:
        report = self.run()
        self.save_report(report)
        return report


def print_report(report: EnvironmentReport) -> None:
    separator = "=" * 100
    print(separator)
    print("PHOENIX v7 ENVIRONMENT VALIDATOR")
    print(separator)
    for result in report.results:
        print(f"{result.status:<5} {result.name:<45} {result.message}")
    print(separator)
    if report.ready:
        print("ENVIRONMENT READY")
    else:
        print("ENVIRONMENT NOT READY - TRADING DISABLED")
    print(separator)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--config", default="config/v7_environment.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validator = EnvironmentValidator.from_file(
            root=args.root,
            config_path=args.config,
        )
        report = validator.run_and_save()
    except Exception as error:
        print("ENVIRONMENT VALIDATOR ERROR")
        print(f"{type(error).__name__}: {error}")
        return 2
    print_report(report)
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
