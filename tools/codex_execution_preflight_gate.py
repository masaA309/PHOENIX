from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


VALIDATOR_VERSION = "1.0.0"


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
    allowed_types = {"IMPLEMENTATION", "GOVERNANCE", "FINAL_ACCEPTANCE"}
    if missing or invalid:
        return [GateFinding("MG-01", "FAIL", f"missing={missing}; invalid={invalid}")]
    if candidate["candidate_type"] not in allowed_types:
        return [GateFinding("MG-01", "FAIL", "candidate_type enum is invalid")]
    if candidate["validator_version"] != VALIDATOR_VERSION:
        return [GateFinding("MG-01", "FAIL", "validator_version mismatch")]
    return [GateFinding("MG-01", "PASS", "required fields and types are present")]


def validate_proof_binding(candidate: dict[str, Any]) -> list[GateFinding]:
    for proof in candidate.get("evidence_graph", []):
        kind = proof.get("evidence_kind")
        source = proof.get("exact_evidence_source")
        members = proof.get("bundle_members")
        if kind == "SINGLE":
            if not isinstance(source, str) or not source or members:
                return [GateFinding("MG-02", "FAIL", "SINGLE must bind exactly one source")]
        elif kind == "ATOMIC_BUNDLE":
            if not isinstance(source, str) or not source:
                return [GateFinding("MG-02", "FAIL", "ATOMIC_BUNDLE requires one bundle identity")]
            if not isinstance(members, list) or not members:
                return [GateFinding("MG-02", "FAIL", "ATOMIC_BUNDLE requires members")]
        else:
            return [GateFinding("MG-02", "FAIL", "evidence_kind is invalid")]
    if len(candidate.get("proof_targets", [])) != len(candidate.get("evidence_graph", [])):
        return [GateFinding("MG-02", "FAIL", "proof target binding count mismatch")]
    return [GateFinding("MG-02", "PASS", "proof bindings are exact")]


def validate_shell_transport(candidate: dict[str, Any]) -> list[GateFinding]:
    transport = candidate.get("shell_transport", {})
    layers = [str(layer).lower() for layer in transport.get("layers", [])]
    command = transport.get("command", [])
    command_parts = command if isinstance(command, list) else [str(command)]
    crossing = any("git bash" in layer for layer in layers) and any(
        "powershell" in layer for layer in layers
    )
    if crossing:
        if any(str(part).lower() == "-command" for part in command_parts):
            return [GateFinding("MG-03", "FAIL", "inline PowerShell -Command is forbidden")]
        if not any(str(part).lower() == "-file" for part in command_parts):
            return [GateFinding("MG-03", "FAIL", "PowerShell crossing requires -File")]
        if not transport.get("script_path") or not transport.get("script_sha256"):
            return [GateFinding("MG-03", "FAIL", "PowerShell script path/hash lock missing")]
    return [GateFinding("MG-03", "PASS", "shell transport is fixed")]


def validate_output_transport(candidate: dict[str, Any]) -> list[GateFinding]:
    budget = candidate.get("output_budget")
    if not isinstance(budget, dict):
        return [GateFinding("MG-04", "FAIL", "output budget missing")]
    stdout_limit = budget.get("max_stdout_bytes")
    stderr_limit = budget.get("max_stderr_bytes")
    if not isinstance(stdout_limit, int) or not isinstance(stderr_limit, int):
        return [GateFinding("MG-04", "FAIL", "output budget types are invalid")]
    if stdout_limit <= 0 or stderr_limit <= 0:
        return [GateFinding("MG-04", "FAIL", "output budget must be positive")]
    for command in candidate.get("execution_manifest", {}).get("commands", []):
        if command.get("preflight"):
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
    resolved_root = root.resolve()
    for artifact in candidate.get("artifact_lock", []):
        if not artifact.get("existing", True):
            continue
        path = (resolved_root / artifact.get("path", "")).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError:
            return [GateFinding("MG-06", "FAIL", "artifact path escapes workspace")]
        if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
            return [GateFinding("MG-06", "FAIL", "artifact identity mismatch")]
    return [GateFinding("MG-06", "PASS", "candidate and artifacts are hash locked")]


def resolve_failure_classes(
    candidate: dict[str, Any], ledger: dict[str, Any], synonyms: dict[str, Any]
) -> list[GateFinding]:
    classes = ledger.get("classes", [])
    synonym_map = synonyms.get("synonyms", {})
    for declaration in candidate.get("failure_classes", []):
        text = str(declaration.get("proposed_root_cause_text", "")).strip().lower()
        canonical_matches = []
        for canonical, aliases in synonym_map.items():
            terms = [canonical, *aliases]
            if text in {str(term).strip().lower() for term in terms}:
                canonical_matches.append(canonical)
        if not canonical_matches:
            return [GateFinding("MG-07", "NOT_PROVEN", "NEW_UNCLASSIFIED root cause")]
        if len(canonical_matches) != 1:
            return [GateFinding("MG-07", "NOT_PROVEN", "AMBIGUOUS root cause")]
        root_code = canonical_matches[0]
        matches = [item for item in classes if item.get("root_cause_code") == root_code]
        if len(matches) != 1:
            return [GateFinding("MG-07", "NOT_PROVEN", "ledger resolution is not unique")]
        item = matches[0]
        declared = declaration.get("declared_failure_class_ids", [])
        valid_ids = {item.get("canonical_id"), *item.get("aliases", [])}
        if not declared or any(value not in valid_ids for value in declared):
            return [GateFinding("MG-07", "FAIL", "declared failure class mismatch")]
        if declaration.get("resolved_root_cause_code") != root_code:
            return [GateFinding("MG-07", "FAIL", "resolved root cause mismatch")]
        if item.get("status") in {"OPEN", "REOPENED"}:
            return [GateFinding("MG-07", "FAIL", "failure class is not closed")]
        evidence = item.get("closure_evidence", {})
        required = {
            "validator_version",
            "artifact_hashes",
            "closed_at_utc",
            "time_window",
            "required_prevention_controls",
        }
        if not required.issubset(evidence) or evidence.get("validator_version") != VALIDATOR_VERSION:
            return [GateFinding("MG-07", "NOT_PROVEN", "CLOSED evidence is stale")]
        if evidence.get("time_window") != "until_governance_artifact_change":
            return [GateFinding("MG-07", "NOT_PROVEN", "closure time window is stale")]
        if not item.get("reopen_condition"):
            return [GateFinding("MG-07", "NOT_PROVEN", "reopen trigger is missing")]
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
        if review.get("prior_free_text_conclusion"):
            return [GateFinding("MG-12", "FAIL", "prior free-text conclusion is forbidden")]
        if review.get("review_type") == "INDEPENDENT_AUDIT":
            if review.get("actor") == review.get("candidate_actor") and review.get(
                "provider"
            ) == review.get("candidate_provider") and review.get("context_id") == review.get(
                "candidate_context_id"
            ):
                return [GateFinding("MG-12", "FAIL", "independent review is not separated")]
    return [GateFinding("MG-12", "PASS", "review inputs are separated")]


def derive_gate_status(findings: list[GateFinding], candidate: dict[str, Any]) -> str:
    if any(finding.status == "FAIL" for finding in findings):
        return "FAIL"
    if any(finding.status == "NOT_PROVEN" for finding in findings):
        return "NOT_PROVEN"
    requirements = candidate.get("review_requirements", [])
    completed = {
        review.get("review_type")
        for review in candidate.get("review_inputs", [])
        if review.get("completed")
    }
    if any(requirement not in completed for requirement in requirements):
        return "NOT_PROVEN"
    return "PASS"


def build_gate_report(
    root: Path,
    candidate: dict[str, Any],
    agents_path: Path,
    ledger_path: Path,
    synonyms_path: Path,
) -> GateReport:
    ledger = load_json_object(ledger_path)
    synonyms = load_json_object(synonyms_path)
    findings: list[GateFinding] = []
    findings.extend(validate_candidate_schema(candidate))
    findings.extend(validate_proof_binding(candidate))
    findings.extend(validate_shell_transport(candidate))
    findings.extend(validate_output_transport(candidate))
    findings.extend(validate_static_contradictions(candidate))
    findings.extend(validate_artifact_identity(root, candidate))
    findings.extend(resolve_failure_classes(candidate, ledger, synonyms))
    findings.extend(validate_evidence_lifecycle(candidate))
    findings.extend(validate_runtime_preconditions(candidate))
    findings.extend(validate_rollback_stop(candidate))
    findings.extend(validate_user_operations(candidate))
    findings.extend(validate_review_separation(candidate))
    artifact_hashes = {
        "AGENTS.md": sha256_file(agents_path),
        str(ledger_path): sha256_file(ledger_path),
        str(synonyms_path): sha256_file(synonyms_path),
    }
    return GateReport(
        candidate_id=str(candidate.get("candidate_id", "")),
        candidate_sha256=str(candidate.get("candidate_sha256", "")),
        status=derive_gate_status(findings, candidate),
        findings=tuple(findings),
        artifact_hashes=artifact_hashes,
    )


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
        paths = {
            name: (root / value).resolve()
            for name, value in {
                "candidate": args.candidate,
                "agents": args.agents,
                "ledger": args.ledger,
                "synonyms": args.synonyms,
                "report": args.report,
            }.items()
        }
        for path in paths.values():
            path.relative_to(root)
        candidate = load_json_object(paths["candidate"])
        candidate_id = str(candidate.get("candidate_id", ""))
        candidate_sha256 = str(candidate.get("candidate_sha256", ""))
        report = build_gate_report(
            root, candidate, paths["agents"], paths["ledger"], paths["synonyms"]
        )
        payload = asdict(report)
        payload["validator_version"] = VALIDATOR_VERSION
        payload["created_at_utc"] = datetime.now(timezone.utc).isoformat()
        paths["report"].parent.mkdir(parents=True, exist_ok=True)
        paths["report"].write_bytes(canonical_json_bytes(payload) + b"\n")
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
