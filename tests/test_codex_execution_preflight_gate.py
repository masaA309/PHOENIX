from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from tools.codex_execution_preflight_gate import (
    VALIDATOR_VERSION,
    canonical_json_bytes,
    derive_gate_status,
    main,
    resolve_failure_classes,
    sha256_bytes,
    validate_artifact_identity,
    validate_candidate_schema,
    validate_evidence_lifecycle,
    validate_output_transport,
    validate_proof_binding,
    validate_review_separation,
    validate_rollback_stop,
    validate_runtime_preconditions,
    validate_shell_transport,
    validate_static_contradictions,
    validate_user_operations,
)
from tools.governance_command_runner import run_command


def _candidate() -> dict[str, object]:
    candidate: dict[str, object] = {
        "candidate_id": "candidate-1",
        "candidate_sha256": "",
        "candidate_type": "GOVERNANCE",
        "created_at_utc": "2026-09-02T00:00:00+00:00",
        "expires_at_utc": "2026-09-03T00:00:00+00:00",
        "agents_sha256": "a" * 64,
        "validator_version": VALIDATOR_VERSION,
        "objective": "governance test",
        "workspace": "workspace",
        "task": "test",
        "allowed": [],
        "forbidden": [],
        "safety": {"required_states": []},
        "output": {"complete": True, "truncate": False},
        "execution_manifest": {"commands": [{"via_runner": True}]},
        "proof_targets": ["PT-1"],
        "evidence_graph": [
            {
                "proof_id": "PT-1",
                "claim": "claim",
                "owner": "owner",
                "writer": "writer",
                "reader": "reader",
                "update_trigger": "trigger",
                "persistence_source": "source",
                "runtime_identity": "identity",
                "time_window": "window",
                "evidence_kind": "SINGLE",
                "exact_evidence_source": "source-1",
                "bundle_members": [],
                "exact_command": "command",
                "expected_shape": "shape",
                "pass_predicate": "pass",
                "fail_predicate": "fail",
                "not_proven_predicate": "not-proven",
                "side_effects": "none",
                "failure_path": "stop",
            }
        ],
        "failure_classes": [],
        "runtime_preconditions": [],
        "rollback_stop": {
            "failure_path": "stop",
            "stop_before": "mutation",
            "rollback_scope": "AGENTS.md",
        },
        "result_branches": {},
        "user_machine_operations": [],
        "shell_transport": {"layers": ["PowerShell"], "command": []},
        "output_budget": {"max_stdout_bytes": 1024, "max_stderr_bytes": 1024},
        "artifact_lock": [],
        "review_inputs": [
            {"review_type": "MECHANICAL_REVIEW", "completed": True},
            {"review_type": "COMPLETENESS_REVIEW", "completed": True},
        ],
        "review_requirements": ["MECHANICAL_REVIEW", "COMPLETENESS_REVIEW"],
    }
    payload = dict(candidate)
    payload.pop("candidate_sha256")
    candidate["candidate_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return candidate


class CodexExecutionPreflightGateTest(unittest.TestCase):
    def test_missing_required_section_fails(self) -> None:
        candidate = _candidate()
        candidate.pop("task")
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_proof_source_zero_fails(self) -> None:
        candidate = _candidate()
        candidate["evidence_graph"][0]["exact_evidence_source"] = ""
        self.assertEqual("FAIL", validate_proof_binding(candidate)[0].status)

    def test_proof_source_multiple_candidates_fails(self) -> None:
        candidate = _candidate()
        candidate["evidence_graph"][0]["exact_evidence_source"] = ["a", "b"]
        self.assertEqual("FAIL", validate_proof_binding(candidate)[0].status)

    def test_atomic_bundle_passes(self) -> None:
        candidate = _candidate()
        proof = candidate["evidence_graph"][0]
        proof["evidence_kind"] = "ATOMIC_BUNDLE"
        proof["exact_evidence_source"] = "bundle-1"
        proof["bundle_members"] = ["a", "b"]
        self.assertEqual("PASS", validate_proof_binding(candidate)[0].status)

    def test_git_bash_powershell_inline_command_fails(self) -> None:
        candidate = _candidate()
        candidate["shell_transport"] = {
            "layers": ["Git Bash", "PowerShell"], "command": ["-Command"]
        }
        self.assertEqual("FAIL", validate_shell_transport(candidate)[0].status)

    def test_hash_locked_ps1_file_passes(self) -> None:
        candidate = _candidate()
        candidate["shell_transport"] = {
            "layers": ["Git Bash", "PowerShell"],
            "command": ["-File", "run.ps1"],
            "script_path": "run.ps1",
            "script_sha256": "a" * 64,
        }
        self.assertEqual("PASS", validate_shell_transport(candidate)[0].status)

    def test_output_budget_missing_or_exceeded_fails(self) -> None:
        candidate = _candidate()
        candidate.pop("output_budget")
        self.assertEqual("FAIL", validate_output_transport(candidate)[0].status)
        candidate = _candidate()
        candidate["output_budget"]["declared_stdout_bytes"] = 1025
        self.assertEqual("FAIL", validate_static_contradictions(candidate)[0].status)

    def test_complete_and_truncate_fails(self) -> None:
        candidate = _candidate()
        candidate["output"]["truncate"] = True
        self.assertEqual("FAIL", validate_static_contradictions(candidate)[0].status)

    def test_wrong_artifact_hash_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "input.txt").write_text("input", encoding="utf-8")
            candidate = _candidate()
            candidate["artifact_lock"] = [{"path": "input.txt", "sha256": "0" * 64}]
            payload = dict(candidate)
            payload.pop("candidate_sha256")
            candidate["candidate_sha256"] = sha256_bytes(canonical_json_bytes(payload))
            self.assertEqual("FAIL", validate_artifact_identity(root, candidate)[0].status)

    def test_open_class_fails(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [{"proposed_root_cause_text": "root", "declared_failure_class_ids": ["G-001"], "resolved_root_cause_code": "root"}]
        ledger = {"classes": [{"canonical_id": "FC", "aliases": ["G-001"], "root_cause_code": "root", "status": "OPEN"}]}
        self.assertEqual("FAIL", resolve_failure_classes(candidate, ledger, {"synonyms": {"root": []}})[0].status)

    def test_unknown_root_cause_is_not_proven(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [{"proposed_root_cause_text": "unknown", "declared_failure_class_ids": [], "resolved_root_cause_code": "unknown"}]
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, {"classes": []}, {"synonyms": {}})[0].status)

    def test_ambiguous_root_cause_is_not_proven(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [{"proposed_root_cause_text": "alias", "declared_failure_class_ids": [], "resolved_root_cause_code": "alias"}]
        synonyms = {"synonyms": {"first": ["alias"], "second": ["alias"]}}
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, {"classes": []}, synonyms)[0].status)

    def test_closed_stale_evidence_is_not_proven(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [{"proposed_root_cause_text": "root", "declared_failure_class_ids": ["G-001"], "resolved_root_cause_code": "root"}]
        ledger = {"classes": [{"canonical_id": "FC", "aliases": ["G-001"], "root_cause_code": "root", "status": "CLOSED", "closure_evidence": {}, "reopen_condition": "change"}]}
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, ledger, {"synonyms": {"root": []}})[0].status)

    def test_lifecycle_missing_fails(self) -> None:
        candidate = _candidate()
        candidate["evidence_graph"][0]["owner"] = ""
        self.assertEqual("FAIL", validate_evidence_lifecycle(candidate)[0].status)

    def test_unproven_runtime_prerequisite_is_not_proven(self) -> None:
        candidate = _candidate()
        candidate["runtime_preconditions"] = [{"proven": False}]
        self.assertEqual("NOT_PROVEN", validate_runtime_preconditions(candidate)[0].status)

    def test_rollback_missing_fails(self) -> None:
        candidate = _candidate()
        candidate["rollback_stop"].pop("rollback_scope")
        self.assertEqual("FAIL", validate_rollback_stop(candidate)[0].status)

    def test_user_operation_two_fails(self) -> None:
        candidate = _candidate()
        candidate["user_machine_operations"] = [{}, {}]
        self.assertEqual("FAIL", validate_user_operations(candidate)[0].status)

    def test_prior_conclusion_in_review_input_fails(self) -> None:
        candidate = _candidate()
        candidate["review_inputs"][0]["prior_free_text_conclusion"] = "PASS"
        self.assertEqual("FAIL", validate_review_separation(candidate)[0].status)

    def test_same_actor_independent_audit_fails(self) -> None:
        candidate = _candidate()
        candidate["review_inputs"] = [{"review_type": "INDEPENDENT_AUDIT", "actor": "a", "provider": "p", "context_id": "c", "candidate_actor": "a", "candidate_provider": "p", "candidate_context_id": "c"}]
        self.assertEqual("FAIL", validate_review_separation(candidate)[0].status)

    def test_internal_schema_error_returns_exit_four(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(4, main(["--candidate", str(path), "--agents", str(path), "--ledger", str(path), "--synonyms", str(path), "--report", str(path)]))

    def test_stale_candidate_hash_fails(self) -> None:
        candidate = _candidate()
        candidate["candidate_sha256"] = "0" * 64
        self.assertEqual("FAIL", validate_artifact_identity(Path.cwd(), candidate)[0].status)

    def test_candidate_canonicalization_vector_matches(self) -> None:
        self.assertEqual(b'{"a":"\xe6\x97\xa5\xe6\x9c\xac","b":2}', canonical_json_bytes({"b": 2, "a": "日本"}))

    def test_runner_stdout_limit_stops_child_and_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_command([sys.executable, "-c", "import sys; sys.stdout.write('x' * 100000)"], root, root / "stdout.txt", root / "stderr.txt", 128, 128)
            self.assertTrue(result.output_limit_exceeded)
            self.assertNotEqual(0, result.returncode)

    def test_non_redundant_candidate_passes_all_conditions(self) -> None:
        candidate = _candidate()
        findings = []
        findings.extend(validate_candidate_schema(candidate))
        findings.extend(validate_proof_binding(candidate))
        findings.extend(validate_shell_transport(candidate))
        findings.extend(validate_output_transport(candidate))
        findings.extend(validate_static_contradictions(candidate))
        findings.extend(validate_artifact_identity(Path.cwd(), candidate))
        findings.extend(resolve_failure_classes(candidate, {"classes": []}, {"synonyms": {}}))
        findings.extend(validate_evidence_lifecycle(candidate))
        findings.extend(validate_runtime_preconditions(candidate))
        findings.extend(validate_rollback_stop(candidate))
        findings.extend(validate_user_operations(candidate))
        findings.extend(validate_review_separation(candidate))
        self.assertEqual("PASS", derive_gate_status(findings, candidate))


if __name__ == "__main__":
    unittest.main()
