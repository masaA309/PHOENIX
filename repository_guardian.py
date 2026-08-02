from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable, Mapping, Sequence
from uuid import uuid4


DEFAULT_EXPECTED_ROOT = (
    "C:/Users/ashtc/OneDrive/デスクトップ/ちちのフォルダ/PHOENIX"
)
DEFAULT_EXPECTED_ORIGIN_URL = "https://github.com/masaA309/PHOENIX.git"
EXPECTED_REPOSITORY_NAME = "PHOENIX"

EXPECTED_ROOT_ENV = "PHOENIX_EXPECTED_ROOT"
EXPECTED_ORIGIN_ENV = "PHOENIX_EXPECTED_ORIGIN_URL"

MODE = "PAPER"
ORDERS_SUBMITTED = 0
EXIT_READY = 0
EXIT_BLOCKED = 2
JST = timezone(timedelta(hours=9), name="JST")

GitReader = Callable[[Sequence[str], Path], str]


@dataclass(frozen=True)
class GuardianConfig:
    expected_root: Path
    expected_origin_url: str
    expected_repository_name: str = EXPECTED_REPOSITORY_NAME


@dataclass
class GuardianResult:
    status: str
    reasons: tuple[str, ...]
    timestamp: str
    cwd: str
    git_root: str | None
    expected_root: str
    repository_name: str | None
    expected_repository_name: str
    origin_url: str | None
    expected_origin_url: str
    branch: str | None
    is_onedrive: bool
    is_codex_copy: bool
    duplicate_copy_suspected: bool
    git_errors: dict[str, str]
    json_report_path: str
    text_report_path: str
    report_error: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "READY"

    def as_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "status": self.status,
            "reasons": list(self.reasons),
            "cwd": self.cwd,
            "git_root": self.git_root,
            "expected_root": self.expected_root,
            "repository_name": self.repository_name,
            "expected_repository_name": self.expected_repository_name,
            "origin_url": self.origin_url,
            "expected_origin_url": self.expected_origin_url,
            "branch": self.branch,
            "is_onedrive": self.is_onedrive,
            "is_codex_copy": self.is_codex_copy,
            "duplicate_copy_suspected": self.duplicate_copy_suspected,
            "git_errors": dict(self.git_errors),
            "mode": MODE,
            "orders_submitted": ORDERS_SUBMITTED,
            "json_report_path": self.json_report_path,
            "text_report_path": self.text_report_path,
            "report_error": self.report_error,
        }


def _from_git_bash_path(value: str) -> str:
    raw = value.strip()
    cygdrive = re.match(r"^/cygdrive/([A-Za-z])(?:/(.*))?$", raw)
    if cygdrive:
        suffix = cygdrive.group(2) or ""
        return f"{cygdrive.group(1)}:/{suffix}"
    drive_path = re.match(r"^/([A-Za-z])(?:/(.*))?$", raw)
    if drive_path:
        suffix = drive_path.group(2) or ""
        return f"{drive_path.group(1)}:/{suffix}"
    return raw


def _resolved_path(value: str | os.PathLike[str]) -> Path:
    expanded = os.path.expandvars(os.fspath(value))
    return Path(_from_git_bash_path(expanded)).expanduser().resolve(strict=False)


def _path_identity(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.normpath(str(_resolved_path(value)))).casefold()


def _paths_equal(
    left: str | os.PathLike[str],
    right: str | os.PathLike[str],
) -> bool:
    return _path_identity(left) == _path_identity(right)


def _path_is_within(
    candidate: str | os.PathLike[str],
    parent: str | os.PathLike[str],
) -> bool:
    candidate_identity = _path_identity(candidate)
    parent_identity = _path_identity(parent)
    try:
        return os.path.commonpath([candidate_identity, parent_identity]) == parent_identity
    except ValueError:
        return False


def _path_parts(value: str | os.PathLike[str]) -> tuple[str, ...]:
    return tuple(part.casefold() for part in _resolved_path(value).parts)


def _is_onedrive_path(value: str | os.PathLike[str]) -> bool:
    return any(part.startswith("onedrive") for part in _path_parts(value))


def _is_codex_path(value: str | os.PathLike[str]) -> bool:
    return "codex" in _path_parts(value)


def _normalize_origin_url(value: str) -> str:
    normalized = value.strip().replace("\\", "/").rstrip("/")
    if normalized.casefold().endswith(".git"):
        normalized = normalized[:-4]
    return normalized.casefold()


def _default_git_reader(command: Sequence[str], cwd: Path) -> str:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    completed = subprocess.run(
        ["git", *command],
        cwd=str(cwd),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail or f"git exited with {completed.returncode}")
    return completed.stdout.strip()


def config_from_environment(
    environment: Mapping[str, str] | None = None,
    *,
    expected_root: str | os.PathLike[str] | None = None,
    expected_origin_url: str | None = None,
) -> GuardianConfig:
    values = os.environ if environment is None else environment
    root_value = expected_root or values.get(EXPECTED_ROOT_ENV) or DEFAULT_EXPECTED_ROOT
    origin_value = (
        expected_origin_url
        or values.get(EXPECTED_ORIGIN_ENV)
        or DEFAULT_EXPECTED_ORIGIN_URL
    )
    return GuardianConfig(
        expected_root=_resolved_path(root_value),
        expected_origin_url=origin_value.strip(),
    )


def inspect_repository(
    config: GuardianConfig,
    *,
    cwd: str | os.PathLike[str] | None = None,
    report_dir: str | os.PathLike[str] | None = None,
    git_reader: GitReader | None = None,
) -> GuardianResult:
    current_cwd = _resolved_path(cwd or Path.cwd())
    expected_root = _resolved_path(config.expected_root)
    destination = _resolved_path(
        report_dir or (Path(__file__).resolve().parent / "logs")
    )
    reader = git_reader or _default_git_reader

    git_values: dict[str, str | None] = {
        "git_root": None,
        "origin_url": None,
        "branch": None,
    }
    git_errors: dict[str, str] = {}
    commands: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("git_root", ("rev-parse", "--show-toplevel")),
        ("origin_url", ("remote", "get-url", "origin")),
        ("branch", ("branch", "--show-current")),
    )
    for label, command in commands:
        try:
            value = reader(command, current_cwd).strip()
            git_values[label] = value or None
        except Exception as error:  # fail closed for every Git read failure
            git_errors[label] = f"{type(error).__name__}: {error}"

    git_root_raw = git_values["git_root"]
    git_root = _resolved_path(git_root_raw) if git_root_raw else None
    origin_url = git_values["origin_url"]
    branch = git_values["branch"]
    repository_name = git_root.name if git_root is not None else None

    codex_copy = _is_codex_path(current_cwd) or (
        git_root is not None and _is_codex_path(git_root)
    )
    onedrive = _is_onedrive_path(git_root or current_cwd)
    root_mismatch = git_root is not None and not _paths_equal(git_root, expected_root)
    duplicate_suspected = codex_copy or (
        root_mismatch
        and repository_name is not None
        and repository_name.casefold() == config.expected_repository_name.casefold()
    )

    reasons: list[str] = []
    if not expected_root.is_dir():
        reasons.append("EXPECTED_ROOT_NOT_FOUND")
    if git_root is None:
        reasons.append("GIT_ROOT_UNAVAILABLE")
    elif root_mismatch:
        reasons.append("GIT_ROOT_MISMATCH")
    if (
        repository_name is None
        or repository_name.casefold() != config.expected_repository_name.casefold()
    ):
        reasons.append("REPOSITORY_NAME_MISMATCH")
    if origin_url is None:
        reasons.append("ORIGIN_UNAVAILABLE")
    elif _normalize_origin_url(origin_url) != _normalize_origin_url(
        config.expected_origin_url
    ):
        reasons.append("ORIGIN_MISMATCH")
    if branch is None:
        reasons.append("BRANCH_UNAVAILABLE")
    if git_root is not None and not _path_is_within(current_cwd, git_root):
        reasons.append("CWD_OUTSIDE_GIT_ROOT")
    if codex_copy:
        reasons.append("CODEX_WORK_COPY")
    if duplicate_suspected:
        reasons.append("DUPLICATE_REPOSITORY_SUSPECTED")

    json_path = destination / "repository_guardian.json"
    text_path = destination / "repository_guardian.txt"
    return GuardianResult(
        status="BLOCKED" if reasons else "READY",
        reasons=tuple(reasons),
        timestamp=datetime.now(JST).isoformat(timespec="seconds"),
        cwd=str(current_cwd),
        git_root=None if git_root is None else str(git_root),
        expected_root=str(expected_root),
        repository_name=repository_name,
        expected_repository_name=config.expected_repository_name,
        origin_url=origin_url,
        expected_origin_url=config.expected_origin_url,
        branch=branch,
        is_onedrive=onedrive,
        is_codex_copy=codex_copy,
        duplicate_copy_suspected=duplicate_suspected,
        git_errors=git_errors,
        json_report_path=str(json_path),
        text_report_path=str(text_path),
    )


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(
        f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    )
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _text_report(result: GuardianResult) -> str:
    reasons = ", ".join(result.reasons) if result.reasons else "none"
    lines = [
        f"Timestamp: {result.timestamp}",
        f"Status: {result.status}",
        f"Reasons: {reasons}",
        f"Current cwd: {result.cwd}",
        f"Git root: {result.git_root or 'unavailable'}",
        f"Expected root: {result.expected_root}",
        f"Repository name: {result.repository_name or 'unavailable'}",
        f"Expected repository name: {result.expected_repository_name}",
        f"Origin URL: {result.origin_url or 'unavailable'}",
        f"Expected origin URL: {result.expected_origin_url}",
        f"Current branch: {result.branch or 'unavailable'}",
        f"OneDrive path: {result.is_onedrive}",
        f"Codex work copy: {result.is_codex_copy}",
        f"Duplicate copy suspected: {result.duplicate_copy_suspected}",
        f"Mode: {MODE}",
        f"Orders submitted: {ORDERS_SUBMITTED}",
    ]
    if result.git_errors:
        lines.append(
            "Git read errors: "
            + json.dumps(result.git_errors, ensure_ascii=False, sort_keys=True)
        )
    return "\n".join(lines) + "\n"


def write_reports(result: GuardianResult) -> None:
    json_path = Path(result.json_report_path)
    text_path = Path(result.text_report_path)
    json_content = json.dumps(
        result.as_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    _atomic_write(json_path, json_content)
    _atomic_write(text_path, _text_report(result))


def run_repository_guardian(
    *,
    expected_root: str | os.PathLike[str] | None = None,
    expected_origin_url: str | None = None,
    cwd: str | os.PathLike[str] | None = None,
    report_dir: str | os.PathLike[str] | None = None,
    git_reader: GitReader | None = None,
    environment: Mapping[str, str] | None = None,
) -> GuardianResult:
    config = config_from_environment(
        environment,
        expected_root=expected_root,
        expected_origin_url=expected_origin_url,
    )
    result = inspect_repository(
        config,
        cwd=cwd,
        report_dir=report_dir,
        git_reader=git_reader,
    )
    try:
        write_reports(result)
    except OSError as error:
        result.status = "BLOCKED"
        result.reasons = tuple((*result.reasons, "REPORT_WRITE_FAILED"))
        result.report_error = f"{type(error).__name__}: {error}"
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX Phase3 Step36.5 Repository Guardian",
    )
    parser.add_argument("--expected-root")
    parser.add_argument("--expected-origin-url")
    parser.add_argument("--report-dir")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_repository_guardian(
        expected_root=args.expected_root,
        expected_origin_url=args.expected_origin_url,
        report_dir=args.report_dir,
    )
    reasons = ",".join(result.reasons) if result.reasons else "none"
    print(
        f"Repository Guardian: {result.status} | reasons={reasons} "
        f"| Mode: {MODE} | Orders submitted: {ORDERS_SUBMITTED}",
        flush=True,
    )
    if result.report_error:
        print(f"Repository Guardian report error: {result.report_error}", flush=True)
    return EXIT_READY if result.ready else EXIT_BLOCKED


if __name__ == "__main__":
    raise SystemExit(main())
