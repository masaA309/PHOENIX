from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import threading
from typing import BinaryIO, Sequence

from tools.codex_execution_preflight_gate import (
    CANONICAL_WORKSPACE,
    GOVERNANCE_ARTIFACTS,
    RUNTIME_COMMAND_OUTPUT_PREFIX,
    VALIDATOR_VERSION,
    build_gate_report,
    canonical_json_bytes,
    load_json_object,
    normalize_repo_relative_path,
    repo_relative_path,
    resolve_repo_path,
    sha256_bytes,
    sha256_file,
)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout_path: str
    stderr_path: str
    stdout_bytes: int
    stderr_bytes: int
    output_limit_exceeded: bool
    spawned: bool = True


@dataclass(frozen=True)
class GovernedAuthorization:
    command_id: str
    argv: tuple[str, ...]
    max_stdout_bytes: int
    max_stderr_bytes: int
    fingerprint: str


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
    if stdout_path == stderr_path:
        raise ValueError("stdout/stderr paths must be distinct")
    if stdout_path.exists() or stderr_path.exists():
        raise ValueError("output sinks must be fresh")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    exceeded = threading.Event()
    counts = {"stdout": 0, "stderr": 0}

    # Preserve the established low-level ordering: spawn the child with bounded PIPEs
    # before opening file sinks. If sink creation fails, the child is terminated.
    process = subprocess.Popen(
        [str(part) for part in command],
        cwd=resolved_cwd,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    created_sinks: list[Path] = []
    try:
        stdout_file = stdout_path.open("xb")
        created_sinks.append(stdout_path)
        stderr_file = stderr_path.open("xb")
        created_sinks.append(stderr_path)
    except Exception:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        for created in created_sinks:
            try:
                created.unlink()
            except FileNotFoundError:
                pass
        raise

    with stdout_file, stderr_file:
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
            if process.stdout is not None:
                process.stdout.close()
            if process.stderr is not None:
                process.stderr.close()
    if exceeded.is_set():
        returncode = returncode if returncode != 0 else 1
    return CommandResult(
        returncode=returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        stdout_bytes=counts["stdout"],
        stderr_bytes=counts["stderr"],
        output_limit_exceeded=exceeded.is_set(),
        spawned=True,
    )


def _canonical_candidate_hash(candidate: dict[str, object]) -> str:
    payload = dict(candidate)
    declared = str(payload.pop("candidate_sha256", ""))
    actual = sha256_bytes(canonical_json_bytes(payload))
    if declared != actual:
        raise ValueError("candidate hash mismatch")
    return actual


def _lexical_repo_relative(root: Path, path: Path) -> str:
    absolute = path if path.is_absolute() else root / path
    relative = absolute.relative_to(root)
    value = PurePosixPath(*relative.parts).as_posix()
    return normalize_repo_relative_path(value)


def _require_canonical_governance_paths(
    root: Path, agents_path: Path, ledger_path: Path, synonyms_path: Path
) -> None:
    expected_relative = {
        "agents": "AGENTS.md",
        "ledger": "knowledge/failure_class_ledger.json",
        "synonyms": "config/governance/root_cause_synonyms.json",
    }
    actual_paths = {
        "agents": agents_path,
        "ledger": ledger_path,
        "synonyms": synonyms_path,
    }
    for name, path in actual_paths.items():
        lexical = _lexical_repo_relative(root, path)
        if lexical != expected_relative[name]:
            raise ValueError("governance path is not exact canonical path")
        if repo_relative_path(root, path) != lexical:
            raise ValueError("governance path resolves through alias/symlink")
def _report_payload_for_fingerprint(report: dict[str, object]) -> dict[str, object]:
    return {
        "candidate_id": report.get("candidate_id"),
        "candidate_sha256": report.get("candidate_sha256"),
        "status": report.get("status"),
        "validator_version": report.get("validator_version"),
        "artifact_hashes": report.get("artifact_hashes"),
    }


def _authorize_governed_command(
    command_id: str,
    candidate_path: Path,
    report_path: Path,
    root: Path,
    agents_path: Path,
    ledger_path: Path,
    synonyms_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> GovernedAuthorization:
    root = root.resolve()
    candidate_lexical = _lexical_repo_relative(root, candidate_path)
    report_lexical = _lexical_repo_relative(root, report_path)
    if not candidate_lexical.startswith("state/governance/incoming/") or not candidate_lexical.endswith(".json"):
        raise ValueError("candidate path is outside canonical incoming JSON directory")
    if not report_lexical.startswith("state/governance/reports/") or not report_lexical.endswith(".json"):
        raise ValueError("report path is outside canonical reports JSON directory")
    candidate_path = candidate_path.resolve()
    report_path = report_path.resolve()
    candidate_path.relative_to(root)
    report_path.relative_to(root)
    if repo_relative_path(root, candidate_path) != candidate_lexical:
        raise ValueError("candidate path resolves through alias/symlink")
    if repo_relative_path(root, report_path) != report_lexical:
        raise ValueError("report path resolves through alias/symlink")
    _require_canonical_governance_paths(root, agents_path, ledger_path, synonyms_path)

    candidate = load_json_object(candidate_path)
    stored_report = load_json_object(report_path)
    _canonical_candidate_hash(candidate)

    manifest = candidate.get("execution_manifest", {})
    write_files = manifest.get("write_files", []) if isinstance(manifest, dict) else []
    if not isinstance(write_files, list):
        raise ValueError("manifest write_files invalid")
    stdout_relative = repo_relative_path(root, stdout_path)
    stderr_relative = repo_relative_path(root, stderr_path)
    for relative in (stdout_relative, stderr_relative):
        if not relative.startswith(RUNTIME_COMMAND_OUTPUT_PREFIX):
            raise ValueError("governed output must be under canonical command output directory")
        if relative not in write_files:
            raise ValueError("governed output path is not candidate-authorized")
        if relative in GOVERNANCE_ARTIFACTS:
            raise ValueError("governed output cannot target governance artifact")
    if stdout_path in {candidate_path, report_path} or stderr_path in {candidate_path, report_path}:
        raise ValueError("governed output cannot overwrite candidate/report")

    commands = candidate.get("execution_manifest", {}).get("commands", [])
    if not isinstance(commands, list):
        raise ValueError("manifest commands invalid")
    matches = [
        command
        for command in commands
        if isinstance(command, dict) and command.get("command_id") == command_id
    ]
    if len(matches) != 1:
        raise ValueError("unknown or duplicate governed command")
    command = matches[0]
    if command.get("preflight") is not False or command.get("via_runner") is not True:
        raise ValueError("command is not runner-authorized")
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(part, str) and part for part in argv
    ):
        raise ValueError("command argv invalid")

    fresh_report = build_gate_report(
        root,
        candidate,
        agents_path,
        ledger_path,
        synonyms_path,
        candidate_path=candidate_path,
    )
    if fresh_report.status != "PASS":
        raise ValueError("fresh governance gate is not PASS")

    if stored_report.get("status") != "PASS":
        raise ValueError("stored governance gate is not PASS")
    if stored_report.get("validator_version") != VALIDATOR_VERSION:
        raise ValueError("stored validator version mismatch")
    if stored_report.get("candidate_id") != fresh_report.candidate_id:
        raise ValueError("stored candidate id mismatch")
    if stored_report.get("candidate_sha256") != fresh_report.candidate_sha256:
        raise ValueError("stored candidate hash mismatch")
    stored_hashes = stored_report.get("artifact_hashes")
    if not isinstance(stored_hashes, dict) or stored_hashes != fresh_report.artifact_hashes:
        raise ValueError("stored governance artifact hashes are stale")

    candidate_relative = repo_relative_path(root, candidate_path)
    if stored_hashes.get(candidate_relative) != sha256_file(candidate_path):
        raise ValueError("raw candidate file hash is stale")

    budget = candidate.get("output_budget")
    if not isinstance(budget, dict):
        raise ValueError("output budget invalid")
    max_stdout_bytes = budget.get("max_stdout_bytes")
    max_stderr_bytes = budget.get("max_stderr_bytes")
    if (
        not isinstance(max_stdout_bytes, int)
        or not isinstance(max_stderr_bytes, int)
        or max_stdout_bytes <= 0
        or max_stderr_bytes <= 0
    ):
        raise ValueError("output budget invalid")

    fingerprint_payload = {
        "command_id": command_id,
        "argv": argv,
        "budget": [max_stdout_bytes, max_stderr_bytes],
        "candidate_file_sha256": sha256_file(candidate_path),
        "report_file_sha256": sha256_file(report_path),
        "report": _report_payload_for_fingerprint(stored_report),
        "stdout_path": stdout_relative,
        "stderr_path": stderr_relative,
    }
    return GovernedAuthorization(
        command_id=command_id,
        argv=tuple(argv),
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=max_stderr_bytes,
        fingerprint=sha256_bytes(canonical_json_bytes(fingerprint_payload)),
    )


def _resolve_governed_output_paths(
    root: Path, stdout_path: Path, stderr_path: Path
) -> tuple[Path, Path]:
    def resolve_one(path: Path) -> Path:
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        resolved.relative_to(root)
        return resolved

    stdout_resolved = resolve_one(stdout_path)
    stderr_resolved = resolve_one(stderr_path)
    if stdout_resolved == stderr_resolved:
        raise ValueError("governed stdout/stderr paths must be distinct")
    if stdout_resolved.exists() or stderr_resolved.exists():
        raise ValueError("governed output sinks must be fresh")
    return stdout_resolved, stderr_resolved


def _blocked_result_without_io(stdout_path: Path, stderr_path: Path) -> CommandResult:
    return CommandResult(
        returncode=1,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        stdout_bytes=0,
        stderr_bytes=0,
        output_limit_exceeded=False,
        spawned=False,
    )


def run_governed_command(
    command_id: str,
    candidate_path: Path,
    gate_report_path: Path,
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    agents_path: Path = Path("AGENTS.md"),
    ledger_path: Path = Path("knowledge/failure_class_ledger.json"),
    synonyms_path: Path = Path("config/governance/root_cause_synonyms.json"),
) -> CommandResult:
    root = cwd.resolve()
    try:
        governed_stdout, governed_stderr = _resolve_governed_output_paths(
            root, stdout_path, stderr_path
        )
    except Exception:
        return _blocked_result_without_io(stdout_path, stderr_path)
    try:
        first = _authorize_governed_command(
            command_id,
            (root / candidate_path) if not candidate_path.is_absolute() else candidate_path,
            (root / gate_report_path) if not gate_report_path.is_absolute() else gate_report_path,
            root,
            (root / agents_path) if not agents_path.is_absolute() else agents_path,
            (root / ledger_path) if not ledger_path.is_absolute() else ledger_path,
            (root / synonyms_path) if not synonyms_path.is_absolute() else synonyms_path,
            governed_stdout,
            governed_stderr,
        )
        # Re-read candidate, report, AGENTS, ledger, synonyms and all artifact locks immediately
        # before opening output sinks / spawning a child. Any change since first authorization
        # produces a different fingerprint or a failed fresh gate.
        second = _authorize_governed_command(
            command_id,
            (root / candidate_path) if not candidate_path.is_absolute() else candidate_path,
            (root / gate_report_path) if not gate_report_path.is_absolute() else gate_report_path,
            root,
            (root / agents_path) if not agents_path.is_absolute() else agents_path,
            (root / ledger_path) if not ledger_path.is_absolute() else ledger_path,
            (root / synonyms_path) if not synonyms_path.is_absolute() else synonyms_path,
            governed_stdout,
            governed_stderr,
        )
        if first.fingerprint != second.fingerprint:
            raise ValueError("governed authorization changed before spawn")
    except Exception:
        return _blocked_result_without_io(governed_stdout, governed_stderr)

    return run_command(
        second.argv,
        root,
        governed_stdout,
        governed_stderr,
        second.max_stdout_bytes,
        second.max_stderr_bytes,
    )



def _same_workspace(path: Path, canonical_workspace: str) -> bool:
    left = os.path.normcase(os.path.normpath(str(path.resolve())))
    right = os.path.normcase(os.path.normpath(canonical_workspace))
    return left == right

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--command")
    mode.add_argument("--command-id")
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--stdout", required=True)
    parser.add_argument("--stderr", required=True)
    parser.add_argument("--max-stdout-bytes", type=int)
    parser.add_argument("--max-stderr-bytes", type=int)
    parser.add_argument("--candidate")
    parser.add_argument("--gate-report")
    parser.add_argument("--agents")
    parser.add_argument("--ledger")
    parser.add_argument("--synonyms")
    args = parser.parse_args(argv)

    if args.command_id:
        required = {
            "candidate": args.candidate,
            "gate_report": args.gate_report,
            "agents": args.agents,
            "ledger": args.ledger,
            "synonyms": args.synonyms,
        }
        if any(not value for value in required.values()):
            raise ValueError("governed mode requires candidate/gate-report/agents/ledger/synonyms")
        result = run_governed_command(
            args.command_id,
            Path(args.candidate),
            Path(args.gate_report),
            Path(args.cwd),
            Path(args.stdout),
            Path(args.stderr),
            Path(args.agents),
            Path(args.ledger),
            Path(args.synonyms),
        )
    else:
        if _same_workspace(Path(args.cwd), CANONICAL_WORKSPACE):
            raise ValueError("low-level --command is forbidden in the canonical PHOENIX workspace; use --command-id")
        if args.max_stdout_bytes is None or args.max_stderr_bytes is None:
            raise ValueError("low-level mode requires explicit output limits")
        command = json.loads(args.command)
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) and item for item in command
        ):
            raise ValueError("command must be a non-empty JSON string array")
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
    print(f"SPAWNED:{str(result.spawned).upper()}")
    print(f"STDOUT_BYTES:{result.stdout_bytes}")
    print(f"STDERR_BYTES:{result.stderr_bytes}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
