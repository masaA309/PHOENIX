from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any


VALIDATOR_VERSION = "1.1.0"
CANONICAL_WORKSPACE = r"C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX"

GOVERNANCE_ARTIFACTS = (
    "AGENTS.md",
    "tools/codex_execution_preflight_gate.py",
    "tools/governance_command_runner.py",
    "config/governance/codex_candidate.schema.json",
    "config/governance/evidence_graph.schema.json",
    "config/governance/failure_class.schema.json",
    "config/governance/gate_report.schema.json",
    "config/governance/root_cause_synonyms.json",
    "knowledge/failure_class_ledger.json",
    "tests/test_codex_execution_preflight_gate.py",
)

# The ledger cannot contain its own cryptographic digest without creating a self-reference.
# Ledger freshness is instead bound by top-level ledger.version; all other governance
# artifacts are bound by exact SHA-256 in each CLOSED class.
GOVERNANCE_CLOSURE_ARTIFACTS = tuple(
    path for path in GOVERNANCE_ARTIFACTS if path != "knowledge/failure_class_ledger.json"
)
GOVERNANCE_PATHS_BY_CASEFOLD = {path.casefold(): path for path in GOVERNANCE_ARTIFACTS}

INDEPENDENT_AUDIT_WRITE_PATHS = frozenset(GOVERNANCE_ARTIFACTS)

REVIEW_TYPES = frozenset(
    {
        "MECHANICAL_REVIEW",
        "COMPLETENESS_REVIEW",
        "INDEPENDENT_AUDIT",
        "SUBSTITUTE_COMPLETENESS_REVIEW",
        "USER_APPROVAL",
    }
)

FAILURE_ACTIONS = frozenset({"USE", "REMEDIATE", "REGISTER", "CLOSE"})
FAILURE_DECLARATION_KEYS = frozenset(
    {
        "action",
        "proposed_root_cause_text",
        "declared_failure_class_ids",
        "resolved_root_cause_code",
        "target_prevention_controls",
        "prevention_control_evidence",
        "registration",
    }
)
REGISTRATION_KEYS = frozenset(
    {
        "canonical_id",
        "aliases",
        "root_cause_code",
        "root_cause_aliases",
        "root_cause_description",
        "required_prevention_controls",
        "reopen_condition",
    }
)
MANIFEST_KEYS = frozenset(
    {
        "read_files",
        "write_files",
        "allowed_functions",
        "allowed_behaviors",
        "allowed_commands",
        "commands",
        "allowed_tests",
        "allowed_assertions",
        "proof_targets",
        "forbidden_additions",
    }
)

EVIDENCE_KEYS = frozenset(
    {
        "proof_id",
        "claim",
        "owner",
        "writer",
        "reader",
        "update_trigger",
        "persistence_source",
        "runtime_identity",
        "time_window",
        "evidence_kind",
        "exact_evidence_source",
        "bundle_members",
        "exact_command",
        "expected_shape",
        "pass_predicate",
        "fail_predicate",
        "not_proven_predicate",
        "side_effects",
        "failure_path",
    }
)
REVIEW_INPUT_KEYS = frozenset(
    {
        "review_type",
        "completed",
        "actor",
        "provider",
        "context_id",
        "candidate_actor",
        "candidate_provider",
        "candidate_context_id",
        "user_approved",
        "approval_scope",
        "approval_evidence",
        "approved_artifact_hashes",
        "prior_free_text_conclusion",
    }
)
RUNTIME_CANDIDATE_PREFIX = "state/governance/incoming/"
RUNTIME_REPORT_PREFIX = "state/governance/reports/"
RUNTIME_COMMAND_OUTPUT_PREFIX = "state/governance/command_outputs/"
POWERSHELL_INLINE_FLAGS = frozenset({"-command", "-c", "-encodedcommand", "-enc", "-ec"})


@dataclass(frozen=True)
class GateFinding:
    rule_id: str
    status: str
    detail: str


@dataclass(frozen=True)
class GateReport:
    candidate_id: str
    candidate_sha256: str
    status: str
    findings: tuple[GateFinding, ...]
    artifact_hashes: dict[str, str]


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value.lower()
    )


def normalize_repo_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("path must be a non-empty repo-relative POSIX path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise ValueError("path must not be absolute or contain dot segments")
    normalized = parsed.as_posix()
    if normalized != value:
        raise ValueError("path must already be canonical repo-relative POSIX form")
    return normalized


def resolve_repo_path(root: Path, value: object) -> Path:
    relative = normalize_repo_relative_path(value)
    resolved_root = root.resolve()
    resolved = (resolved_root / Path(*PurePosixPath(relative).parts)).resolve()
    resolved.relative_to(resolved_root)
    return resolved


def repo_relative_path(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    relative = resolved.relative_to(resolved_root)
    return PurePosixPath(*relative.parts).as_posix()


def _workspace_key(value: object) -> str:
    if not isinstance(value, (str, os.PathLike)) or not str(value):
        return ""
    return os.path.normcase(os.path.normpath(str(Path(value).resolve())))


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("timestamp must be timezone-aware UTC")
    return parsed


def _strings(value: object, *, nonempty: bool = False, unique: bool = False) -> bool:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return False
    if nonempty and (not value or any(not item for item in value)):
        return False
    if unique and len(value) != len(set(value)):
        return False
    return True


def _proof_ids(candidate: dict[str, Any]) -> set[str]:
    return {
        str(proof.get("proof_id"))
        for proof in candidate.get("evidence_graph", [])
        if isinstance(proof, dict) and proof.get("proof_id")
    }


def _candidate_sensitive_write_paths(candidate: dict[str, Any]) -> set[str]:
    manifest = candidate.get("execution_manifest", {})
    raw = manifest.get("write_files", []) if isinstance(manifest, dict) else []
    paths: set[str] = set()
    if isinstance(raw, list):
        for value in raw:
            try:
                normalized = normalize_repo_relative_path(value)
            except ValueError:
                continue
            paths.add(GOVERNANCE_PATHS_BY_CASEFOLD.get(normalized.casefold(), normalized))
    return paths


def _requires_independent_audit(candidate: dict[str, Any]) -> bool:
    if _candidate_sensitive_write_paths(candidate) & INDEPENDENT_AUDIT_WRITE_PATHS:
        return True
    return any(
        isinstance(declaration, dict) and declaration.get("action") == "REGISTER"
        for declaration in candidate.get("failure_classes", [])
    )


def _valid_user_approval(
    candidate: dict[str, Any],
    scope: str,
    approved_artifact_hashes: dict[str, str] | None = None,
) -> bool:
    for review in candidate.get("review_inputs", []):
        if not isinstance(review, dict):
            continue
        if not (
            review.get("review_type") == "USER_APPROVAL"
            and review.get("completed") is True
            and review.get("actor") == "USER"
            and review.get("user_approved") is True
            and review.get("approval_scope") == scope
            and isinstance(review.get("approval_evidence"), str)
            and bool(review.get("approval_evidence"))
        ):
            continue
        if approved_artifact_hashes is not None:
            raw = review.get("approved_artifact_hashes")
            if not isinstance(raw, dict) or raw != approved_artifact_hashes:
                continue
        return True
    return False


def _governance_lock_hashes(candidate: dict[str, Any]) -> dict[str, str]:
    lock_map = {
        str(lock.get("path")): str(lock.get("sha256"))
        for lock in candidate.get("artifact_lock", [])
        if isinstance(lock, dict) and lock.get("existing") is True
    }
    if any(path not in lock_map for path in GOVERNANCE_ARTIFACTS):
        return {}
    return {path: lock_map[path] for path in GOVERNANCE_ARTIFACTS}


def validate_candidate_schema(candidate: dict[str, Any]) -> list[GateFinding]:
    required = {
        "candidate_id": str,
        "candidate_sha256": str,
        "candidate_type": str,
        "created_at_utc": str,
        "expires_at_utc": str,
        "agents_sha256": str,
        "validator_version": str,
        "objective": str,
        "workspace": str,
        "task": str,
        "allowed": list,
        "forbidden": list,
        "safety": dict,
        "output": dict,
        "execution_manifest": dict,
        "proof_targets": list,
        "evidence_graph": list,
        "failure_classes": list,
        "runtime_preconditions": list,
        "rollback_stop": dict,
        "result_branches": dict,
        "user_machine_operations": list,
        "shell_transport": dict,
        "output_budget": dict,
        "artifact_lock": list,
        "review_inputs": list,
        "review_requirements": list,
    }
    missing = sorted(name for name in required if name not in candidate)
    invalid = sorted(
        name
        for name, expected in required.items()
        if name in candidate and not isinstance(candidate[name], expected)
    )
    extras = sorted(set(candidate) - set(required))
    if missing or invalid or extras:
        return [
            GateFinding(
                "MG-01",
                "FAIL",
                f"missing={missing}; invalid={invalid}; extras={extras}",
            )
        ]
    if candidate["candidate_type"] not in {"IMPLEMENTATION", "GOVERNANCE", "FINAL_ACCEPTANCE"}:
        return [GateFinding("MG-01", "FAIL", "candidate_type enum is invalid")]
    if candidate["validator_version"] != VALIDATOR_VERSION:
        return [GateFinding("MG-01", "FAIL", "validator_version mismatch")]
    if not _is_sha256(candidate["candidate_sha256"]) or not _is_sha256(candidate["agents_sha256"]):
        return [GateFinding("MG-01", "FAIL", "candidate/AGENTS SHA-256 shape is invalid")]
    for name in ("candidate_id", "created_at_utc", "expires_at_utc", "objective", "workspace", "task"):
        if not candidate[name]:
            return [GateFinding("MG-01", "FAIL", f"{name} must be a non-empty string")]
    if (
        not _strings(candidate["allowed"], unique=True)
        or not _strings(candidate["forbidden"], unique=True)
        or any(not item for item in candidate["allowed"])
        or any(not item for item in candidate["forbidden"])
    ):
        return [GateFinding("MG-01", "FAIL", "allowed/forbidden must be unique non-empty string arrays")]
    if not _strings(candidate["proof_targets"], nonempty=True, unique=True):
        return [GateFinding("MG-01", "FAIL", "proof_targets must be non-empty unique strings")]
    if not _strings(candidate["review_requirements"], unique=True):
        return [GateFinding("MG-01", "FAIL", "review_requirements must be unique strings")]
    if any(value not in REVIEW_TYPES for value in candidate["review_requirements"]):
        return [GateFinding("MG-01", "FAIL", "review requirement is invalid")]
    if not candidate["failure_classes"]:
        return [GateFinding("MG-01", "FAIL", "failure_classes must be non-empty")]
    if not all(isinstance(item, dict) for item in candidate["runtime_preconditions"]):
        return [GateFinding("MG-01", "FAIL", "runtime_preconditions must contain objects")]

    manifest = candidate["execution_manifest"]
    if set(manifest) != MANIFEST_KEYS:
        return [GateFinding("MG-01", "FAIL", "execution_manifest shape is not strict")]
    for name in MANIFEST_KEYS - {"commands"}:
        values = manifest.get(name)
        if not _strings(values, unique=True) or any(not item for item in values):
            return [GateFinding("MG-01", "FAIL", f"execution_manifest.{name} must be unique non-empty strings")]
    if manifest["proof_targets"] != candidate["proof_targets"]:
        return [GateFinding("MG-01", "FAIL", "manifest proof_targets differ from candidate proof_targets")]
    for field in ("read_files", "write_files"):
        seen_casefold: set[str] = set()
        for value in manifest[field]:
            try:
                normalized = normalize_repo_relative_path(value)
            except ValueError as error:
                return [GateFinding("MG-01", "FAIL", f"{field} path invalid: {error}")]
            folded = normalized.casefold()
            if folded in seen_casefold:
                return [GateFinding("MG-01", "FAIL", f"{field} contains a case-insensitive duplicate path")]
            seen_casefold.add(folded)
            canonical_governance = GOVERNANCE_PATHS_BY_CASEFOLD.get(folded)
            if canonical_governance is not None and normalized != canonical_governance:
                return [GateFinding("MG-01", "FAIL", f"{field} governance path case alias is forbidden")]

    commands = manifest.get("commands")
    if not isinstance(commands, list):
        return [GateFinding("MG-01", "FAIL", "execution_manifest commands must be a list")]
    command_ids: set[str] = set()
    for command in commands:
        if not isinstance(command, dict) or set(command) != {"command_id", "argv", "via_runner", "preflight"}:
            return [GateFinding("MG-01", "FAIL", "manifest command shape is not strict")]
        command_id = command.get("command_id")
        argv = command.get("argv")
        if not isinstance(command_id, str) or not command_id or command_id in command_ids:
            return [GateFinding("MG-01", "FAIL", "manifest command_id must be non-empty and unique")]
        command_ids.add(command_id)
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) and part for part in argv):
            return [GateFinding("MG-01", "FAIL", "manifest argv must be a non-empty string array")]
        if not isinstance(command.get("via_runner"), bool) or not isinstance(command.get("preflight"), bool):
            return [GateFinding("MG-01", "FAIL", "manifest command flags must be booleans")]
        if command["preflight"] and command["via_runner"]:
            return [GateFinding("MG-01", "FAIL", "preflight is the sole runner exception")]
        if not command["preflight"] and not command["via_runner"]:
            return [GateFinding("MG-01", "FAIL", "non-preflight command must use runner")]

    declared_command_ids = manifest["allowed_commands"]
    actual_command_ids = [command["command_id"] for command in commands]
    if declared_command_ids != actual_command_ids:
        return [GateFinding("MG-01", "FAIL", "allowed_commands differ from commands[] ids")]

    budget = candidate["output_budget"]
    if type(budget.get("max_stdout_bytes")) is not int or type(
        budget.get("max_stderr_bytes")
    ) is not int:
        return [GateFinding("MG-01", "FAIL", "output budget limits must be integers")]
    if budget["max_stdout_bytes"] <= 0 or budget["max_stderr_bytes"] <= 0:
        return [GateFinding("MG-01", "FAIL", "output budget limits must be positive")]

    governance_writes = _candidate_sensitive_write_paths(candidate) & set(GOVERNANCE_ARTIFACTS)
    if governance_writes and candidate["candidate_type"] != "GOVERNANCE":
        return [GateFinding("MG-01", "FAIL", "governance artifacts require GOVERNANCE candidate")]

    proof_ids: set[str] = set()
    string_evidence_fields = EVIDENCE_KEYS - {"bundle_members"}
    for proof in candidate["evidence_graph"]:
        if not isinstance(proof, dict) or set(proof) != EVIDENCE_KEYS:
            return [GateFinding("MG-01", "FAIL", "evidence proof shape is not strict")]
        if any(not isinstance(proof.get(name), str) or not proof[name] for name in string_evidence_fields):
            return [GateFinding("MG-01", "FAIL", "evidence proof string field is missing/invalid")]
        members = proof.get("bundle_members")
        if not _strings(members, unique=True):
            return [GateFinding("MG-01", "FAIL", "bundle_members must be unique strings")]
        if proof["proof_id"] in proof_ids:
            return [GateFinding("MG-01", "FAIL", "proof_id must be unique")]
        proof_ids.add(proof["proof_id"])

    for declaration in candidate["failure_classes"]:
        if not isinstance(declaration, dict) or set(declaration) != FAILURE_DECLARATION_KEYS:
            return [GateFinding("MG-01", "FAIL", "failure class declaration shape is not strict")]
        action = declaration.get("action")
        if action not in FAILURE_ACTIONS:
            return [GateFinding("MG-01", "FAIL", "failure action is invalid")]
        if not isinstance(declaration.get("proposed_root_cause_text"), str) or not declaration[
            "proposed_root_cause_text"
        ]:
            return [GateFinding("MG-01", "FAIL", "proposed_root_cause_text is required")]
        if not isinstance(declaration.get("resolved_root_cause_code"), str) or not declaration[
            "resolved_root_cause_code"
        ]:
            return [GateFinding("MG-01", "FAIL", "resolved_root_cause_code is required")]
        declared_ids = declaration.get("declared_failure_class_ids")
        if not _strings(declared_ids, unique=True) or any(not item for item in declared_ids):
            return [GateFinding("MG-01", "FAIL", "declared_failure_class_ids must be unique non-empty strings")]
        if action != "REGISTER" and not declaration["declared_failure_class_ids"]:
            return [GateFinding("MG-01", "FAIL", "non-REGISTER failure action requires declared_failure_class_ids")]
        targets = declaration.get("target_prevention_controls")
        if not _strings(targets, unique=True) or any(not item for item in targets):
            return [GateFinding("MG-01", "FAIL", "target_prevention_controls must be unique non-empty strings")]
        evidence = declaration.get("prevention_control_evidence")
        if not isinstance(evidence, dict) or not all(
            isinstance(key, str) and key and isinstance(value, str) and value
            for key, value in evidence.items()
        ):
            return [GateFinding("MG-01", "FAIL", "prevention_control_evidence must map strings to proof ids")]
        if any(value not in proof_ids for value in evidence.values()):
            return [GateFinding("MG-01", "FAIL", "prevention_control_evidence references unknown proof_id")]
        registration = declaration.get("registration")
        if action == "REGISTER":
            if candidate["candidate_type"] != "GOVERNANCE":
                return [GateFinding("MG-01", "FAIL", "REGISTER requires GOVERNANCE candidate")]
            if declaration["declared_failure_class_ids"] or declaration["target_prevention_controls"] or evidence:
                return [GateFinding("MG-01", "FAIL", "REGISTER must not declare existing ids/controls/evidence")]
            if not isinstance(registration, dict) or set(registration) != REGISTRATION_KEYS:
                return [GateFinding("MG-01", "FAIL", "REGISTER registration payload shape is not strict")]
            for name in ("canonical_id", "root_cause_code", "root_cause_description", "reopen_condition"):
                if not isinstance(registration.get(name), str) or not registration[name]:
                    return [GateFinding("MG-01", "FAIL", f"registration.{name} is required")]
            aliases = registration.get("aliases")
            if not _strings(aliases, unique=True) or any(not item for item in aliases):
                return [GateFinding("MG-01", "FAIL", "registration.aliases must be unique non-empty strings")]
            root_aliases = registration.get("root_cause_aliases")
            if not _strings(root_aliases, unique=True) or any(not item for item in root_aliases):
                return [GateFinding("MG-01", "FAIL", "registration.root_cause_aliases must be unique non-empty strings")]
            if not _strings(registration.get("required_prevention_controls"), nonempty=True, unique=True):
                return [GateFinding("MG-01", "FAIL", "registration controls must be non-empty unique strings")]
        else:
            if registration is not None:
                return [GateFinding("MG-01", "FAIL", "registration must be null except REGISTER")]
            targets = declaration["target_prevention_controls"]
            if action == "USE" and (targets or evidence):
                return [GateFinding("MG-01", "FAIL", "USE must not carry remediation/closure evidence")]
            if action in {"REMEDIATE", "CLOSE"} and not targets:
                return [GateFinding("MG-01", "FAIL", f"{action} requires target_prevention_controls")]
            if action in {"REMEDIATE", "CLOSE"} and set(evidence) != set(targets):
                return [GateFinding("MG-01", "FAIL", f"{action} evidence keys must exactly match target controls")]

    for review in candidate["review_inputs"]:
        if not isinstance(review, dict) or not set(review).issubset(REVIEW_INPUT_KEYS):
            return [GateFinding("MG-01", "FAIL", "review input shape is not strict")]
        if review.get("review_type") not in REVIEW_TYPES or not isinstance(review.get("completed"), bool):
            return [GateFinding("MG-01", "FAIL", "review input type/completed field is invalid")]
        for name in (
            "actor",
            "provider",
            "context_id",
            "candidate_actor",
            "candidate_provider",
            "candidate_context_id",
            "approval_scope",
            "approval_evidence",
        ):
            if name in review and not isinstance(review.get(name), str):
                return [GateFinding("MG-01", "FAIL", f"review input {name} must be a string")]
        if "user_approved" in review and not isinstance(review.get("user_approved"), bool):
            return [GateFinding("MG-01", "FAIL", "review input user_approved must be boolean")]
        if "prior_free_text_conclusion" in review and not isinstance(
            review.get("prior_free_text_conclusion"), bool
        ):
            return [GateFinding("MG-01", "FAIL", "review input prior_free_text_conclusion must be boolean")]
        if "approved_artifact_hashes" in review:
            hashes = review.get("approved_artifact_hashes")
            if not isinstance(hashes, dict) or not all(
                isinstance(path, str)
                and path
                and _is_sha256(digest)
                for path, digest in hashes.items()
            ):
                return [GateFinding("MG-01", "FAIL", "approved_artifact_hashes is invalid")]
    return [GateFinding("MG-01", "PASS", "candidate contract is structurally valid")]

def validate_time_and_workspace(
    root: Path,
    candidate: dict[str, Any],
    canonical_workspace: str | None = None,
    now_utc: datetime | None = None,
) -> list[GateFinding]:
    try:
        created = _parse_utc(candidate["created_at_utc"])
        expires = _parse_utc(candidate["expires_at_utc"])
    except (KeyError, ValueError) as error:
        return [GateFinding("MG-01", "FAIL", f"created/expires timestamp is invalid: {error}")]
    now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        return [GateFinding("MG-01", "FAIL", "now_utc must be timezone-aware UTC")]
    if not (created <= now < expires) or not created < expires:
        return [GateFinding("MG-01", "FAIL", "candidate is expired, not yet valid, or has invalid ordering")]
    expected = canonical_workspace if canonical_workspace is not None else CANONICAL_WORKSPACE
    if candidate.get("workspace") != expected:
        return [GateFinding("MG-01", "FAIL", "candidate workspace is not exact canonical workspace")]
    if str(root) != expected:
        return [GateFinding("MG-01", "FAIL", "runtime root is not exact canonical workspace")]
    return [GateFinding("MG-01", "PASS", "candidate time window and workspace are valid")]

def validate_proof_binding(candidate: dict[str, Any]) -> list[GateFinding]:
    proofs = candidate.get("evidence_graph", [])
    if not isinstance(proofs, list):
        return [GateFinding("MG-02", "FAIL", "evidence_graph must be a list")]
    proof_ids: list[str] = []
    for proof in proofs:
        if not isinstance(proof, dict) or set(proof) != EVIDENCE_KEYS:
            return [GateFinding("MG-02", "FAIL", "proof shape is not strict")]
        proof_id = proof.get("proof_id")
        if not isinstance(proof_id, str) or not proof_id:
            return [GateFinding("MG-02", "FAIL", "proof_id is missing")]
        proof_ids.append(proof_id)
        kind = proof.get("evidence_kind")
        source = proof.get("exact_evidence_source")
        members = proof.get("bundle_members")
        if kind == "SINGLE":
            if not isinstance(source, str) or not source or members != []:
                return [GateFinding("MG-02", "FAIL", "SINGLE must bind exactly one source and no bundle members")]
        elif kind == "ATOMIC_BUNDLE":
            if not isinstance(source, str) or not source:
                return [GateFinding("MG-02", "FAIL", "ATOMIC_BUNDLE requires one bundle identity")]
            if not _strings(members, nonempty=True, unique=True):
                return [GateFinding("MG-02", "FAIL", "ATOMIC_BUNDLE requires non-empty unique members")]
        else:
            return [GateFinding("MG-02", "FAIL", "evidence_kind is invalid")]
    if len(proof_ids) != len(set(proof_ids)):
        return [GateFinding("MG-02", "FAIL", "proof_id must be unique")]
    if proof_ids != candidate.get("proof_targets", []):
        return [GateFinding("MG-02", "FAIL", "proof_targets and evidence_graph ids/order differ")]
    return [GateFinding("MG-02", "PASS", "proof bindings are exact")]

def validate_shell_transport(candidate: dict[str, Any]) -> list[GateFinding]:
    transport = candidate.get("shell_transport", {})
    if not isinstance(transport, dict) or not set(transport).issubset(
        {"layers", "command", "script_path", "script_sha256"}
    ):
        return [GateFinding("MG-03", "FAIL", "shell_transport shape is not strict")]
    layers = transport.get("layers")
    command = transport.get("command")
    if (
        not _strings(layers, unique=True)
        or not _strings(command)
        or any(not item for item in layers)
        or any(not item for item in command)
    ):
        return [GateFinding("MG-03", "FAIL", "shell transport layers/command are invalid")]
    layer_keys = [layer.casefold() for layer in layers]
    crossing = any("git bash" in layer for layer in layer_keys) and any(
        "powershell" in layer or "pwsh" in layer for layer in layer_keys
    )
    manifest_commands = candidate.get("execution_manifest", {}).get("commands", [])
    ps_commands: list[list[str]] = []
    for item in manifest_commands if isinstance(manifest_commands, list) else []:
        if not isinstance(item, dict):
            continue
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv:
            continue
        argv_text = [str(part) for part in argv]
        exe = argv_text[0].replace("\\", "/").rsplit("/", 1)[-1].casefold()
        nested_ps = any(
            ("powershell" in part.casefold() or "pwsh" in part.casefold())
            for part in argv_text[1:]
        )
        if nested_ps and not ("powershell" in exe or exe in {"pwsh", "pwsh.exe"}):
            return [GateFinding("MG-03", "FAIL", "nested PowerShell invocation is forbidden; direct -File only")]
        if "powershell" in exe or exe in {"pwsh", "pwsh.exe"}:
            ps_commands.append(argv_text)
    if ps_commands and not crossing:
        return [GateFinding("MG-03", "FAIL", "actual PowerShell command is not declared as Git Bash/PowerShell crossing")]
    if not crossing:
        if transport.get("script_path") or transport.get("script_sha256"):
            return [GateFinding("MG-03", "FAIL", "non-crossing transport must not carry PowerShell script lock")]
        return [GateFinding("MG-03", "PASS", "shell transport is fixed")]
    if len(ps_commands) != 1 or command != ps_commands[0]:
        return [GateFinding("MG-03", "FAIL", "declared PowerShell command differs from actual manifest command")]
    lowered = [part.casefold() for part in command]
    if any(part in POWERSHELL_INLINE_FLAGS for part in lowered):
        return [GateFinding("MG-03", "FAIL", "inline/encoded PowerShell command is forbidden")]
    if lowered.count("-file") != 1:
        return [GateFinding("MG-03", "FAIL", "PowerShell crossing requires exactly one -File")]
    file_index = lowered.index("-file")
    if file_index + 1 >= len(command):
        return [GateFinding("MG-03", "FAIL", "PowerShell -File script argument is missing")]
    script_path = transport.get("script_path")
    script_sha = transport.get("script_sha256")
    try:
        normalized_script = normalize_repo_relative_path(script_path)
    except ValueError as error:
        return [GateFinding("MG-03", "FAIL", f"PowerShell script path invalid: {error}")]
    if command[file_index + 1] != normalized_script or not _is_sha256(script_sha):
        return [GateFinding("MG-03", "FAIL", "PowerShell script path/hash binding is invalid")]
    lock_matches = [
        lock
        for lock in candidate.get("artifact_lock", [])
        if isinstance(lock, dict) and lock.get("path") == normalized_script
    ]
    if len(lock_matches) != 1 or lock_matches[0].get("existing") is not True or lock_matches[0].get("sha256") != script_sha:
        return [GateFinding("MG-03", "FAIL", "PowerShell script is not exact artifact-hash locked")]
    return [GateFinding("MG-03", "PASS", "shell transport is fixed")]

def validate_output_transport(candidate: dict[str, Any]) -> list[GateFinding]:
    budget = candidate.get("output_budget")
    if not isinstance(budget, dict):
        return [GateFinding("MG-04", "FAIL", "output budget missing")]
    stdout_limit = budget.get("max_stdout_bytes")
    stderr_limit = budget.get("max_stderr_bytes")
    if type(stdout_limit) is not int or type(stderr_limit) is not int:
        return [GateFinding("MG-04", "FAIL", "output budget types are invalid")]
    if stdout_limit <= 0 or stderr_limit <= 0:
        return [GateFinding("MG-04", "FAIL", "output budget must be positive")]
    for command in candidate.get("execution_manifest", {}).get("commands", []):
        if command.get("preflight"):
            if command.get("via_runner"):
                return [GateFinding("MG-04", "FAIL", "preflight must bypass runner")]
            continue
        if not command.get("via_runner"):
            return [GateFinding("MG-04", "FAIL", "command bypasses governance runner")]
    return [GateFinding("MG-04", "PASS", "output transport is bounded")]


def validate_static_contradictions(candidate: dict[str, Any]) -> list[GateFinding]:
    output = candidate.get("output", {})
    if output.get("complete") and output.get("truncate"):
        return [GateFinding("MG-05", "FAIL", "complete and truncate conflict")]
    budget = candidate.get("output_budget", {})
    if budget.get("declared_stdout_bytes", 0) > budget.get("max_stdout_bytes", 0):
        return [GateFinding("MG-05", "FAIL", "declared stdout exceeds budget")]
    if budget.get("declared_stderr_bytes", 0) > budget.get("max_stderr_bytes", 0):
        return [GateFinding("MG-05", "FAIL", "declared stderr exceeds budget")]
    for proof in candidate.get("evidence_graph", []):
        if proof.get("pass_predicate") == proof.get("fail_predicate"):
            return [GateFinding("MG-05", "FAIL", "PASS and FAIL predicates conflict")]
        if proof.get("requires_manifest_external_action"):
            return [GateFinding("MG-05", "FAIL", "proof requires manifest-external action")]
    states: dict[str, Any] = {}
    for state in candidate.get("safety", {}).get("required_states", []):
        if not isinstance(state, dict):
            return [GateFinding("MG-05", "FAIL", "required state must be an object")]
        name = state.get("name")
        if name in states and states[name] != state.get("value"):
            return [GateFinding("MG-05", "FAIL", "required states conflict")]
        states[name] = state.get("value")
    return [GateFinding("MG-05", "PASS", "known static contradictions absent")]


def validate_artifact_identity(root: Path, candidate: dict[str, Any]) -> list[GateFinding]:
    payload = dict(candidate)
    declared_hash = str(payload.pop("candidate_sha256", ""))
    actual_hash = sha256_bytes(canonical_json_bytes(payload))
    if declared_hash != actual_hash:
        return [GateFinding("MG-06", "FAIL", "candidate SHA-256 mismatch")]

    locks = candidate.get("artifact_lock", [])
    if not isinstance(locks, list):
        return [GateFinding("MG-06", "FAIL", "artifact_lock must be a list")]
    artifact_by_path: dict[str, dict[str, Any]] = {}
    artifact_casefold_paths: set[str] = set()
    for artifact in locks:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256", "existing"}:
            return [GateFinding("MG-06", "FAIL", "artifact lock shape is not strict")]
        try:
            path = normalize_repo_relative_path(artifact.get("path"))
        except ValueError as error:
            return [GateFinding("MG-06", "FAIL", f"artifact path invalid: {error}")]
        folded = path.casefold()
        if path in artifact_by_path or folded in artifact_casefold_paths:
            return [GateFinding("MG-06", "FAIL", "artifact hash locks must be case-insensitively unique")]
        canonical_governance = GOVERNANCE_PATHS_BY_CASEFOLD.get(folded)
        if canonical_governance is not None and path != canonical_governance:
            return [GateFinding("MG-06", "FAIL", "governance artifact path case alias is forbidden")]
        artifact_casefold_paths.add(folded)
        if not _is_sha256(artifact.get("sha256")) or not isinstance(artifact.get("existing"), bool):
            return [GateFinding("MG-06", "FAIL", "artifact lock hash/existing field invalid")]
        artifact_by_path[path] = artifact

    for required_path in GOVERNANCE_ARTIFACTS:
        lock = artifact_by_path.get(required_path)
        if lock is None or lock.get("existing") is not True:
            return [GateFinding("MG-06", "FAIL", "governance artifact hash lock missing or non-existing")]

    for path, artifact in artifact_by_path.items():
        resolved = resolve_repo_path(root, path)
        if artifact["existing"]:
            if not resolved.is_file() or sha256_file(resolved) != artifact["sha256"]:
                return [GateFinding("MG-06", "FAIL", "artifact identity mismatch")]
        elif resolved.exists():
            return [GateFinding("MG-06", "FAIL", "artifact declared non-existing already exists")]

    if candidate.get("agents_sha256") != artifact_by_path["AGENTS.md"]["sha256"]:
        return [GateFinding("MG-06", "FAIL", "agents_sha256 does not match raw AGENTS lock")]
    return [GateFinding("MG-06", "PASS", "candidate and artifacts are hash locked")]


def _normalized_text(value: object) -> str:
    return str(value or "").strip().casefold()


def _normalized_id(value: object) -> str:
    return str(value or "").strip().casefold()


def _existing_class_matches(
    text: str, classes: list[dict[str, Any]], synonym_map: dict[str, Any]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in classes:
        canonical = item.get("root_cause_code")
        terms = [
            canonical,
            *item.get("root_cause_aliases", []),
            *synonym_map.get(canonical, []),
        ]
        if text in {_normalized_text(term) for term in terms}:
            matches.append(item)
    return matches


def _closed_evidence_finding(
    candidate: dict[str, Any], ledger: dict[str, Any], item: dict[str, Any]
) -> GateFinding:
    evidence = item.get("closure_evidence")
    if not isinstance(evidence, dict):
        return GateFinding("MG-07", "NOT_PROVEN", "CLOSED evidence is missing")
    required = {
        "validator_version",
        "artifact_hashes",
        "closed_at_utc",
        "time_window",
        "required_prevention_controls",
    }
    if not required.issubset(evidence):
        return GateFinding("MG-07", "NOT_PROVEN", "CLOSED evidence fields are incomplete")
    if evidence.get("validator_version") != VALIDATOR_VERSION:
        return GateFinding("MG-07", "NOT_PROVEN", "CLOSED validator version is stale")
    if evidence.get("time_window") != "until_governance_artifact_change":
        return GateFinding("MG-07", "NOT_PROVEN", "closure time window is invalid")
    try:
        closed_at = _parse_utc(evidence.get("closed_at_utc"))
    except ValueError:
        return GateFinding("MG-07", "NOT_PROVEN", "closed_at_utc is invalid")
    if closed_at > datetime.now(timezone.utc):
        return GateFinding("MG-07", "NOT_PROVEN", "closure evidence is from the future")
    required_controls = item.get("required_prevention_controls", [])
    if not isinstance(required_controls, list) or not required_controls:
        return GateFinding("MG-07", "NOT_PROVEN", "required prevention controls are missing")
    if set(evidence.get("required_prevention_controls", [])) != set(required_controls):
        return GateFinding("MG-07", "NOT_PROVEN", "closure controls do not cover required controls")
    if "ledger_version" not in evidence:
        return GateFinding("MG-07", "NOT_PROVEN", "legacy CLOSED evidence lacks ledger version binding")
    if evidence.get("ledger_version") != ledger.get("version"):
        return GateFinding("MG-07", "NOT_PROVEN", "ledger version changed since closure")
    if not item.get("reopen_condition"):
        return GateFinding("MG-07", "NOT_PROVEN", "reopen trigger is missing")

    artifact_hashes = evidence.get("artifact_hashes")
    if not isinstance(artifact_hashes, dict) or set(artifact_hashes) != set(
        GOVERNANCE_CLOSURE_ARTIFACTS
    ):
        return GateFinding("MG-07", "NOT_PROVEN", "closure artifact key set is stale")
    lock_map = {
        str(lock.get("path")): str(lock.get("sha256"))
        for lock in candidate.get("artifact_lock", [])
        if isinstance(lock, dict) and lock.get("existing") is True
    }
    for path in GOVERNANCE_CLOSURE_ARTIFACTS:
        if artifact_hashes.get(path) != lock_map.get(path):
            return GateFinding("MG-07", "NOT_PROVEN", f"closure artifact stale: {path}")
    return GateFinding("MG-07", "PASS", "CLOSED evidence is fresh")


def _validate_control_evidence(
    candidate: dict[str, Any], declaration: dict[str, Any], required_controls: list[str], *, close: bool
) -> GateFinding | None:
    targets = declaration.get("target_prevention_controls", [])
    evidence = declaration.get("prevention_control_evidence", {})
    required = set(required_controls)
    target_set = set(targets)
    if close:
        if target_set != required:
            return GateFinding("MG-07", "NOT_PROVEN", "CLOSE requires all prevention controls")
    elif not target_set or not target_set.issubset(required):
        return GateFinding("MG-07", "FAIL", "REMEDIATE controls must be a non-empty required subset")
    if set(evidence) != target_set:
        return GateFinding("MG-07", "NOT_PROVEN" if close else "FAIL", "control evidence keys differ from target controls")
    proof_ids = _proof_ids(candidate)
    if any(value not in proof_ids for value in evidence.values()):
        return GateFinding("MG-07", "NOT_PROVEN", "control evidence references unknown proof id")
    return None


def _validate_registration_collisions(
    candidate: dict[str, Any], ledger: dict[str, Any], synonyms: dict[str, Any], declaration: dict[str, Any]
) -> GateFinding | None:
    if candidate.get("candidate_type") != "GOVERNANCE":
        return GateFinding("MG-07", "FAIL", "REGISTER requires GOVERNANCE candidate")
    registration = declaration.get("registration")
    if not isinstance(registration, dict):
        return GateFinding("MG-07", "FAIL", "REGISTER registration payload missing")
    if declaration.get("declared_failure_class_ids"):
        return GateFinding("MG-07", "FAIL", "REGISTER cannot declare an existing class id")
    if declaration.get("resolved_root_cause_code") != registration.get("root_cause_code"):
        return GateFinding("MG-07", "FAIL", "REGISTER resolved root cause mismatch")
    proposed = _normalized_text(declaration.get("proposed_root_cause_text"))
    registration_terms = {
        _normalized_text(registration.get("root_cause_code")),
        *(_normalized_text(alias) for alias in registration.get("root_cause_aliases", [])),
    }
    if proposed not in registration_terms:
        return GateFinding("MG-07", "FAIL", "REGISTER proposed root cause is not in registration terms")

    existing_ids: set[str] = set()
    existing_text: set[str] = set()
    synonym_map = synonyms.get("synonyms", {})
    for item in ledger.get("classes", []):
        existing_ids.add(_normalized_id(item.get("canonical_id")))
        existing_ids.update(_normalized_id(alias) for alias in item.get("aliases", []))
        code = item.get("root_cause_code")
        existing_text.add(_normalized_text(code))
        existing_text.update(_normalized_text(alias) for alias in item.get("root_cause_aliases", []))
        existing_text.update(_normalized_text(alias) for alias in synonym_map.get(code, []))
    for code, aliases in synonym_map.items():
        existing_text.add(_normalized_text(code))
        existing_text.update(_normalized_text(alias) for alias in aliases)

    new_ids = [registration.get("canonical_id"), *registration.get("aliases", [])]
    new_id_norm = [_normalized_id(value) for value in new_ids]
    if any(not value for value in new_id_norm) or len(new_id_norm) != len(set(new_id_norm)):
        return GateFinding("MG-07", "FAIL", "REGISTER id/aliases are empty or collide internally")
    if set(new_id_norm) & existing_ids:
        return GateFinding("MG-07", "FAIL", "REGISTER class id/alias collision")

    new_text = [registration.get("root_cause_code"), *registration.get("root_cause_aliases", [])]
    new_text_norm = [_normalized_text(value) for value in new_text]
    if any(not value for value in new_text_norm) or len(new_text_norm) != len(set(new_text_norm)):
        return GateFinding("MG-07", "FAIL", "REGISTER root-cause terms are empty or collide internally")
    if set(new_text_norm) & existing_text:
        return GateFinding("MG-07", "FAIL", "REGISTER root-cause/synonym collision")
    if not _valid_user_approval(candidate, f"FAILURE_CLASS_REGISTER:{registration.get('canonical_id')}"):
        return GateFinding("MG-07", "NOT_PROVEN", "REGISTER user approval is not proven")
    return None


def resolve_failure_classes(
    candidate: dict[str, Any], ledger: dict[str, Any], synonyms: dict[str, Any]
) -> list[GateFinding]:
    raw_classes = ledger.get("classes", [])
    if not isinstance(raw_classes, list) or not all(isinstance(item, dict) for item in raw_classes):
        return [GateFinding("MG-07", "FAIL", "failure class ledger shape is invalid")]
    classes: list[dict[str, Any]] = list(raw_classes)
    synonym_map = synonyms.get("synonyms", {})
    if not isinstance(synonym_map, dict):
        return [GateFinding("MG-07", "FAIL", "root cause synonyms shape is invalid")]

    pending_registration_ids: set[str] = set()
    pending_registration_text: set[str] = set()
    for declaration in candidate.get("failure_classes", []):
        action = declaration.get("action")
        if action == "REGISTER":
            finding = _validate_registration_collisions(candidate, ledger, synonyms, declaration)
            if finding:
                return [finding]
            registration = declaration.get("registration", {})
            new_ids = {
                _normalized_id(value)
                for value in [registration.get("canonical_id"), *registration.get("aliases", [])]
            }
            new_text = {
                _normalized_text(value)
                for value in [
                    registration.get("root_cause_code"),
                    *registration.get("root_cause_aliases", []),
                ]
            }
            if new_ids & pending_registration_ids or new_text & pending_registration_text:
                return [GateFinding("MG-07", "FAIL", "REGISTER declarations collide within candidate")]
            pending_registration_ids.update(new_ids)
            pending_registration_text.update(new_text)
            continue

        text = _normalized_text(declaration.get("proposed_root_cause_text"))
        matches = _existing_class_matches(text, classes, synonym_map)
        if not matches:
            return [GateFinding("MG-07", "NOT_PROVEN", "NEW_UNCLASSIFIED root cause")]
        if len(matches) != 1:
            return [GateFinding("MG-07", "NOT_PROVEN", "AMBIGUOUS root cause")]
        item = matches[0]
        root_code = item.get("root_cause_code")
        declared = declaration.get("declared_failure_class_ids", [])
        valid_ids = {str(item.get("canonical_id")), *(str(alias) for alias in item.get("aliases", []))}
        if not declared or any(str(value) not in valid_ids for value in declared):
            return [GateFinding("MG-07", "FAIL", "declared failure class mismatch")]
        if declaration.get("resolved_root_cause_code") != root_code:
            return [GateFinding("MG-07", "FAIL", "resolved root cause mismatch")]

        status = item.get("status")
        required_controls = item.get("required_prevention_controls", [])
        if action == "USE":
            if status != "CLOSED":
                return [GateFinding("MG-07", "FAIL", "USE requires CLOSED class")]
            fresh = _closed_evidence_finding(candidate, ledger, item)
            if fresh.status != "PASS":
                return [fresh]
            continue

        if action == "REMEDIATE":
            if status in {"OPEN", "REOPENED"}:
                pass
            elif status == "CLOSED" and candidate.get("candidate_type") == "GOVERNANCE":
                fresh = _closed_evidence_finding(candidate, ledger, item)
                if fresh.status == "PASS":
                    return [GateFinding("MG-07", "FAIL", "fresh CLOSED class cannot be REMEDIATE target")]
                # A stale CLOSED class is treated as effectively REOPENED only for a
                # governance remediation candidate.
            else:
                return [GateFinding("MG-07", "FAIL", "REMEDIATE requires OPEN/REOPENED or stale CLOSED governance class")]
            control_finding = _validate_control_evidence(
                candidate, declaration, required_controls, close=False
            )
            if control_finding:
                return [control_finding]
            continue

        if action == "CLOSE":
            if candidate.get("candidate_type") != "GOVERNANCE":
                return [GateFinding("MG-07", "FAIL", "CLOSE requires GOVERNANCE candidate")]
            if status not in {"OPEN", "REOPENED"}:
                return [GateFinding("MG-07", "FAIL", "CLOSE requires OPEN or REOPENED class")]
            control_finding = _validate_control_evidence(
                candidate, declaration, required_controls, close=True
            )
            if control_finding:
                return [control_finding]
            continue

        return [GateFinding("MG-07", "FAIL", "failure action is invalid")]
    return [GateFinding("MG-07", "PASS", "failure classes are resolved")]


def validate_evidence_lifecycle(candidate: dict[str, Any]) -> list[GateFinding]:
    required = {
        "owner",
        "writer",
        "reader",
        "update_trigger",
        "persistence_source",
        "runtime_identity",
        "time_window",
    }
    for proof in candidate.get("evidence_graph", []):
        if any(not proof.get(name) for name in required):
            return [GateFinding("MG-08", "FAIL", "evidence lifecycle is incomplete")]
    return [GateFinding("MG-08", "PASS", "evidence lifecycle is complete")]


def validate_runtime_preconditions(candidate: dict[str, Any]) -> list[GateFinding]:
    if any(not item.get("proven", False) for item in candidate.get("runtime_preconditions", [])):
        return [GateFinding("MG-09", "NOT_PROVEN", "USER_MACHINE_READY:NO")]
    return [GateFinding("MG-09", "PASS", "runtime prerequisites are proven")]


def validate_rollback_stop(candidate: dict[str, Any]) -> list[GateFinding]:
    rollback = candidate.get("rollback_stop", {})
    required = ("failure_path", "stop_before", "rollback_scope")
    if any(not rollback.get(name) for name in required):
        return [GateFinding("MG-10", "FAIL", "rollback/stop definition is incomplete")]
    return [GateFinding("MG-10", "PASS", "rollback/stop definition is complete")]


def validate_user_operations(candidate: dict[str, Any]) -> list[GateFinding]:
    operations = candidate.get("user_machine_operations", [])
    allowed_count = 1 if candidate.get("candidate_type") == "FINAL_ACCEPTANCE" else 0
    if len(operations) > allowed_count:
        return [GateFinding("MG-11", "FAIL", "user operation count exceeds policy")]
    return [GateFinding("MG-11", "PASS", "user operation count is permitted")]


def validate_review_separation(candidate: dict[str, Any]) -> list[GateFinding]:
    for review in candidate.get("review_inputs", []):
        if not isinstance(review, dict):
            return [GateFinding("MG-12", "FAIL", "review input is invalid")]
        if review.get("prior_free_text_conclusion"):
            return [GateFinding("MG-12", "FAIL", "prior free-text conclusion is forbidden")]
        if review.get("review_type") == "INDEPENDENT_AUDIT":
            if not all(
                isinstance(review.get(name), str) and review.get(name)
                for name in (
                    "actor",
                    "provider",
                    "context_id",
                    "candidate_actor",
                    "candidate_provider",
                    "candidate_context_id",
                )
            ):
                return [GateFinding("MG-12", "FAIL", "independent audit identity is incomplete")]
            if (
                review.get("actor") == review.get("candidate_actor")
                and review.get("provider") == review.get("candidate_provider")
            ):
                return [GateFinding("MG-12", "FAIL", "same actor/provider cannot become independent by context change")]
        if review.get("review_type") == "SUBSTITUTE_COMPLETENESS_REVIEW":
            if review.get("completed") is True and not _valid_user_approval(
                candidate, "SUBSTITUTE_COMPLETENESS_REVIEW"
            ):
                return [GateFinding("MG-12", "NOT_PROVEN", "substitute review lacks explicit user approval")]
    if candidate.get("candidate_type") == "GOVERNANCE":
        approved = _governance_lock_hashes(candidate)
        if not approved or not _valid_user_approval(
            candidate, "GOVERNANCE_ARTIFACTS", approved
        ):
            return [GateFinding("MG-12", "NOT_PROVEN", "governance artifact approval is not exact-hash bound")]
    return [GateFinding("MG-12", "PASS", "review inputs are separated and approvals are hash bound")]

def derive_gate_status(findings: list[GateFinding], candidate: dict[str, Any]) -> str:
    if any(finding.status == "FAIL" for finding in findings):
        return "FAIL"
    if any(finding.status == "NOT_PROVEN" for finding in findings):
        return "NOT_PROVEN"

    requirements = {"MECHANICAL_REVIEW", "COMPLETENESS_REVIEW"}
    requirements.update(candidate.get("review_requirements", []))
    if _requires_independent_audit(candidate):
        requirements.add("INDEPENDENT_AUDIT")

    completed = {
        review.get("review_type")
        for review in candidate.get("review_inputs", [])
        if isinstance(review, dict) and review.get("completed") is True
    }
    completed.add("MECHANICAL_REVIEW")

    if "INDEPENDENT_AUDIT" in requirements and candidate.get("candidate_type") == "GOVERNANCE":
        if (
            "SUBSTITUTE_COMPLETENESS_REVIEW" in completed
            and _valid_user_approval(candidate, "SUBSTITUTE_COMPLETENESS_REVIEW")
        ):
            requirements.remove("INDEPENDENT_AUDIT")
            requirements.add("SUBSTITUTE_COMPLETENESS_REVIEW")

    if any(requirement not in completed for requirement in requirements):
        return "NOT_PROVEN"
    return "PASS"


def _report_artifact_hashes(
    root: Path, candidate: dict[str, Any], candidate_path: Path | None = None
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for lock in candidate.get("artifact_lock", []):
        if not isinstance(lock, dict) or lock.get("existing") is not True:
            continue
        try:
            relative = normalize_repo_relative_path(lock.get("path"))
            resolved = resolve_repo_path(root, relative)
        except ValueError:
            continue
        if resolved.is_file():
            hashes[relative] = sha256_file(resolved)
    if candidate_path is not None and candidate_path.is_file():
        hashes[repo_relative_path(root, candidate_path)] = sha256_file(candidate_path)
    return hashes


def build_gate_report(
    root: Path,
    candidate: dict[str, Any],
    agents_path: Path,
    ledger_path: Path,
    synonyms_path: Path,
    candidate_path: Path | None = None,
    canonical_workspace: str | None = None,
) -> GateReport:
    resolved_root = root.resolve()
    expected_agents = (resolved_root / "AGENTS.md").resolve()
    expected_ledger = (resolved_root / "knowledge/failure_class_ledger.json").resolve()
    expected_synonyms = (resolved_root / "config/governance/root_cause_synonyms.json").resolve()
    if agents_path.resolve() != expected_agents:
        raise ValueError("agents path is not canonical")
    if ledger_path.resolve() != expected_ledger:
        raise ValueError("ledger path is not canonical")
    if synonyms_path.resolve() != expected_synonyms:
        raise ValueError("synonyms path is not canonical")

    ledger = load_json_object(expected_ledger)
    synonyms = load_json_object(expected_synonyms)
    findings: list[GateFinding] = []
    findings.extend(validate_candidate_schema(candidate))
    findings.extend(validate_time_and_workspace(resolved_root, candidate, canonical_workspace))
    findings.extend(validate_proof_binding(candidate))
    findings.extend(validate_shell_transport(candidate))
    findings.extend(validate_output_transport(candidate))
    findings.extend(validate_static_contradictions(candidate))
    findings.extend(validate_artifact_identity(resolved_root, candidate))
    findings.extend(resolve_failure_classes(candidate, ledger, synonyms))
    findings.extend(validate_evidence_lifecycle(candidate))
    findings.extend(validate_runtime_preconditions(candidate))
    findings.extend(validate_rollback_stop(candidate))
    findings.extend(validate_user_operations(candidate))
    findings.extend(validate_review_separation(candidate))
    return GateReport(
        candidate_id=str(candidate.get("candidate_id", "")),
        candidate_sha256=str(candidate.get("candidate_sha256", "")),
        status=derive_gate_status(findings, candidate),
        findings=tuple(findings),
        artifact_hashes=_report_artifact_hashes(resolved_root, candidate, candidate_path),
    )


def _require_runtime_json_path(relative: str, prefix: str) -> None:
    if not relative.startswith(prefix) or relative == prefix or not relative.endswith(".json"):
        raise ValueError(f"runtime evidence path must be a JSON file under {prefix}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--agents", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--synonyms", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    candidate_id = ""
    candidate_sha256 = ""
    report_display = args.report
    try:
        root = Path.cwd().resolve()
        relative_inputs = {
            "candidate": normalize_repo_relative_path(args.candidate),
            "agents": normalize_repo_relative_path(args.agents),
            "ledger": normalize_repo_relative_path(args.ledger),
            "synonyms": normalize_repo_relative_path(args.synonyms),
            "report": normalize_repo_relative_path(args.report),
        }
        if relative_inputs["agents"] != "AGENTS.md":
            raise ValueError("AGENTS path must be exact canonical path")
        if relative_inputs["ledger"] != "knowledge/failure_class_ledger.json":
            raise ValueError("ledger path must be exact canonical path")
        if relative_inputs["synonyms"] != "config/governance/root_cause_synonyms.json":
            raise ValueError("synonyms path must be exact canonical path")
        _require_runtime_json_path(relative_inputs["candidate"], RUNTIME_CANDIDATE_PREFIX)
        _require_runtime_json_path(relative_inputs["report"], RUNTIME_REPORT_PREFIX)
        paths = {name: resolve_repo_path(root, value) for name, value in relative_inputs.items()}
        if repo_relative_path(root, paths["candidate"]) != relative_inputs["candidate"]:
            raise ValueError("candidate path resolves through alias/symlink")
        if repo_relative_path(root, paths["report"]) != relative_inputs["report"]:
            raise ValueError("report path resolves through alias/symlink")
        if paths["candidate"] == paths["report"]:
            raise ValueError("candidate/report paths must be distinct")
        candidate = load_json_object(paths["candidate"])
        candidate_id = str(candidate.get("candidate_id", ""))
        candidate_sha256 = str(candidate.get("candidate_sha256", ""))
        report = build_gate_report(
            root,
            candidate,
            paths["agents"],
            paths["ledger"],
            paths["synonyms"],
            candidate_path=paths["candidate"],
        )
        payload = asdict(report)
        payload["validator_version"] = VALIDATOR_VERSION
        payload["created_at_utc"] = datetime.now(timezone.utc).isoformat()
        paths["report"].parent.mkdir(parents=True, exist_ok=True)
        with paths["report"].open("xb") as report_file:
            report_file.write(canonical_json_bytes(payload) + b"\n")
        status = report.status
        exit_code = {"PASS": 0, "FAIL": 2, "NOT_PROVEN": 3}[status]
    except Exception:
        status = "FAIL"
        exit_code = 4
    print(f"CODEX_EXECUTION_PREFLIGHT_GATE:{status}")
    print(f"CANDIDATE_ID:{candidate_id}")
    print(f"CANDIDATE_SHA256:{candidate_sha256}")
    print(f"REPORT_PATH:{report_display}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
