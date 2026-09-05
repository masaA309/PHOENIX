from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import tools.codex_execution_preflight_gate as gate
import tools.governance_command_runner as runner
from tools.codex_execution_preflight_gate import (
    GOVERNANCE_ARTIFACTS,
    GOVERNANCE_CLOSURE_ARTIFACTS,
    VALIDATOR_VERSION,
    build_gate_report,
    canonical_json_bytes,
    derive_gate_status,
    main,
    resolve_failure_classes,
    sha256_bytes,
    sha256_file,
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
    validate_time_and_workspace,
    validate_user_operations,
)
from tools.governance_command_runner import run_command, run_governed_command


def _rehash(candidate: dict[str, object]) -> dict[str, object]:
    payload = dict(candidate)
    payload.pop("candidate_sha256", None)
    candidate["candidate_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return candidate


def _candidate(root: Path | None = None) -> dict[str, object]:
    root = (root or Path.cwd()).resolve()
    now = datetime.now(timezone.utc)
    candidate: dict[str, object] = {
        "candidate_id": "candidate-1",
        "candidate_sha256": "0" * 64,
        "candidate_type": "IMPLEMENTATION",
        "created_at_utc": (now - timedelta(minutes=1)).isoformat(),
        "expires_at_utc": (now + timedelta(hours=1)).isoformat(),
        "agents_sha256": sha256_file(root / "AGENTS.md"),
        "validator_version": VALIDATOR_VERSION,
        "objective": "governance test",
        "workspace": str(root),
        "task": "test",
        "allowed": [],
        "forbidden": [],
        "safety": {"required_states": []},
        "output": {"complete": True, "truncate": False},
        "execution_manifest": {
            "read_files": [],
            "write_files": [
                "state/governance/command_outputs/echo.stdout",
                "state/governance/command_outputs/echo.stderr",
            ],
            "allowed_functions": [],
            "allowed_behaviors": [],
            "allowed_commands": ["echo"],
            "commands": [
                {
                    "command_id": "echo",
                    "argv": [sys.executable, "-c", "print('ok')"],
                    "via_runner": True,
                    "preflight": False,
                }
            ],
            "allowed_tests": [],
            "allowed_assertions": [],
            "proof_targets": ["PT-1"],
            "forbidden_additions": [],
        },
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
        "artifact_lock": [
            {"path": path, "sha256": sha256_file(root / path), "existing": True}
            for path in GOVERNANCE_ARTIFACTS
        ],
        "review_inputs": [
            {"review_type": "COMPLETENESS_REVIEW", "completed": True},
        ],
        "review_requirements": [],
    }
    return _rehash(candidate)


def _proof_declaration(action: str, **extra: object) -> dict[str, object]:
    declaration: dict[str, object] = {
        "action": action,
        "proposed_root_cause_text": "root",
        "declared_failure_class_ids": ["G-001"],
        "resolved_root_cause_code": "root",
        "target_prevention_controls": [],
        "prevention_control_evidence": {},
        "registration": None,
    }
    declaration.update(extra)
    return declaration


def _fresh_closed_ledger(candidate: dict[str, object], status: str = "CLOSED") -> dict[str, object]:
    lock_map = {
        item["path"]: item["sha256"]
        for item in candidate["artifact_lock"]
        if item["existing"]
    }
    closure = {}
    if status == "CLOSED":
        closure = {
            "validator_version": VALIDATOR_VERSION,
            "artifact_hashes": {
                path: lock_map[path] for path in GOVERNANCE_CLOSURE_ARTIFACTS
            },
            "closed_at_utc": datetime.now(timezone.utc).isoformat(),
            "time_window": "until_governance_artifact_change",
            "required_prevention_controls": ["control"],
            "test_run_id": "run",
            "ledger_version": 1,
        }
    return {
        "version": 1,
        "classes": [
            {
                "canonical_id": "FC",
                "aliases": ["G-001"],
                "root_cause_code": "root",
                "root_cause_aliases": ["root alias"],
                "root_cause_description": "root",
                "required_prevention_controls": ["control"],
                "status": status,
                "closure_evidence": closure,
                "reopen_condition": "change",
            }
        ],
    }


def _add_substitute_approval(candidate: dict[str, object]) -> None:
    candidate["review_inputs"].extend(
        [
            {
                "review_type": "SUBSTITUTE_COMPLETENESS_REVIEW",
                "completed": True,
            },
            {
                "review_type": "USER_APPROVAL",
                "completed": True,
                "actor": "USER",
                "user_approved": True,
                "approval_scope": "SUBSTITUTE_COMPLETENESS_REVIEW",
                "approval_evidence": "user-approved-governance-substitute",
            },
        ]
    )


def _add_governance_artifact_approval(candidate: dict[str, object]) -> None:
    approved = {
        item["path"]: item["sha256"]
        for item in candidate["artifact_lock"]
        if item["path"] in GOVERNANCE_ARTIFACTS and item["existing"]
    }
    candidate["review_inputs"].append(
        {
            "review_type": "USER_APPROVAL",
            "completed": True,
            "actor": "USER",
            "user_approved": True,
            "approval_scope": "GOVERNANCE_ARTIFACTS",
            "approval_evidence": "exact-governance-artifact-hashes-approved",
            "approved_artifact_hashes": approved,
        }
    )


def _gate_candidate(root: Path | None = None) -> dict[str, object]:
    candidate = _candidate(root)
    candidate["candidate_type"] = "GOVERNANCE"
    candidate["failure_classes"] = [
        _proof_declaration(
            "REGISTER",
            proposed_root_cause_text="test root",
            declared_failure_class_ids=[],
            resolved_root_cause_code="test root",
            registration={
                "canonical_id": "FC-TEST-ONLY",
                "aliases": ["G-TEST-ONLY"],
                "root_cause_code": "test root",
                "root_cause_aliases": ["test alias"],
                "root_cause_description": "test root",
                "required_prevention_controls": ["test control"],
                "reopen_condition": "test change",
            },
        )
    ]
    candidate["review_inputs"].append(
        {
            "review_type": "USER_APPROVAL",
            "completed": True,
            "actor": "USER",
            "user_approved": True,
            "approval_scope": "FAILURE_CLASS_REGISTER:FC-TEST-ONLY",
            "approval_evidence": "test-approved",
        }
    )
    _add_substitute_approval(candidate)
    _add_governance_artifact_approval(candidate)
    return _rehash(candidate)


def _copy_governance_tree(root: Path) -> None:
    for relative in GOVERNANCE_ARTIFACTS:
        source = Path.cwd() / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _write_candidate_and_report(root: Path, candidate: dict[str, object]) -> tuple[Path, Path]:
    candidate_path = root / "state/governance/incoming/candidate.json"
    report_path = root / "state/governance/reports/candidate.json"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_bytes(canonical_json_bytes(candidate) + b"\n")
    report = asdict(
        build_gate_report(
            root,
            candidate,
            root / "AGENTS.md",
            root / "knowledge/failure_class_ledger.json",
            root / "config/governance/root_cause_synonyms.json",
            candidate_path=candidate_path,
        )
    )
    report["validator_version"] = VALIDATOR_VERSION
    report["created_at_utc"] = datetime.now(timezone.utc).isoformat()
    report_path.write_bytes(canonical_json_bytes(report) + b"\n")
    return candidate_path, report_path


class CodexExecutionPreflightGateTest(unittest.TestCase):
    def test_missing_required_section_fails(self) -> None:
        candidate = _candidate()
        candidate.pop("task")
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_failure_classes_must_not_be_empty(self) -> None:
        candidate = _candidate()
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_non_register_declared_failure_ids_must_not_be_empty(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [
            _proof_declaration("USE", declared_failure_class_ids=[])
        ]
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_candidate_schema_requires_failure_declaration(self) -> None:
        schema = json.loads((Path.cwd() / "config/governance/codex_candidate.schema.json").read_text(encoding="utf-8"))
        declaration_array = schema["properties"]["failure_classes"]
        self.assertEqual(1, declaration_array["minItems"])
        conditions = declaration_array["items"]["allOf"]
        mins = {
            item["if"]["properties"]["action"]["const"]: item["then"]["properties"].get("declared_failure_class_ids", {}).get("minItems")
            for item in conditions
        }
        self.assertEqual(1, mins["USE"])
        self.assertEqual(1, mins["REMEDIATE"])
        self.assertEqual(1, mins["CLOSE"])

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
            "layers": ["Git Bash", "PowerShell"],
            "command": ["-Command"],
        }
        self.assertEqual("FAIL", validate_shell_transport(candidate)[0].status)

    def test_hash_locked_ps1_file_passes(self) -> None:
        candidate = _candidate()
        argv = ["powershell.exe", "-File", "run.ps1"]
        candidate["execution_manifest"]["commands"] = [
            {"command_id": "ps", "argv": argv, "via_runner": True, "preflight": False}
        ]
        candidate["execution_manifest"]["allowed_commands"] = ["ps"]
        candidate["shell_transport"] = {
            "layers": ["Git Bash", "PowerShell"],
            "command": argv,
            "script_path": "run.ps1",
            "script_sha256": "a" * 64,
        }
        candidate["artifact_lock"].append(
            {"path": "run.ps1", "sha256": "a" * 64, "existing": True}
        )
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
        candidate = _candidate()
        candidate["artifact_lock"][0]["sha256"] = "0" * 64
        _rehash(candidate)
        self.assertEqual("FAIL", validate_artifact_identity(Path.cwd(), candidate)[0].status)

    def test_open_class_use_fails(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [_proof_declaration("USE")]
        ledger = _fresh_closed_ledger(candidate, status="OPEN")
        self.assertEqual("FAIL", resolve_failure_classes(candidate, ledger, {"synonyms": {}})[0].status)

    def test_unknown_root_cause_is_not_proven(self) -> None:
        candidate = _candidate()
        declaration = _proof_declaration("USE", proposed_root_cause_text="unknown", resolved_root_cause_code="unknown")
        candidate["failure_classes"] = [declaration]
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, {"version": 1, "classes": []}, {"synonyms": {}})[0].status)

    def test_ambiguous_root_cause_is_not_proven(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [_proof_declaration("USE", proposed_root_cause_text="alias", resolved_root_cause_code="first")]
        ledger = {
            "version": 1,
            "classes": [
                {"canonical_id": "A", "aliases": [], "root_cause_code": "first", "root_cause_aliases": ["alias"], "status": "OPEN"},
                {"canonical_id": "B", "aliases": [], "root_cause_code": "second", "root_cause_aliases": ["alias"], "status": "OPEN"},
            ],
        }
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, ledger, {"synonyms": {}})[0].status)

    def test_closed_stale_evidence_is_not_proven(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [_proof_declaration("USE")]
        ledger = _fresh_closed_ledger(candidate)
        ledger["classes"][0]["closure_evidence"]["artifact_hashes"][GOVERNANCE_CLOSURE_ARTIFACTS[0]] = "0" * 64
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, ledger, {"synonyms": {}})[0].status)

    def test_closed_fresh_use_passes(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [_proof_declaration("USE")]
        self.assertEqual("PASS", resolve_failure_classes(candidate, _fresh_closed_ledger(candidate), {"synonyms": {}})[0].status)

    def test_open_class_remediation_subset_passes(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [
            _proof_declaration(
                "REMEDIATE",
                target_prevention_controls=["control"],
                prevention_control_evidence={"control": "PT-1"},
            )
        ]
        self.assertEqual("PASS", resolve_failure_classes(candidate, _fresh_closed_ledger(candidate, "OPEN"), {"synonyms": {}})[0].status)

    def test_remediation_invalid_controls_fail(self) -> None:
        for targets, evidence, expected in [
            ([], {}, "FAIL"),
            (["unknown"], {"unknown": "PT-1"}, "FAIL"),
            (["control"], {}, "FAIL"),
            (["control"], {"control": "UNKNOWN"}, "NOT_PROVEN"),
        ]:
            with self.subTest(targets=targets, evidence=evidence):
                candidate = _candidate()
                candidate["failure_classes"] = [
                    _proof_declaration(
                        "REMEDIATE",
                        target_prevention_controls=targets,
                        prevention_control_evidence=evidence,
                    )
                ]
                self.assertEqual(expected, resolve_failure_classes(candidate, _fresh_closed_ledger(candidate, "OPEN"), {"synonyms": {}})[0].status)

    def test_stale_closed_governance_remediation_passes_but_fresh_closed_fails(self) -> None:
        candidate = _candidate()
        candidate["candidate_type"] = "GOVERNANCE"
        candidate["failure_classes"] = [
            _proof_declaration(
                "REMEDIATE",
                target_prevention_controls=["control"],
                prevention_control_evidence={"control": "PT-1"},
            )
        ]
        stale = _fresh_closed_ledger(candidate)
        stale["classes"][0]["closure_evidence"]["ledger_version"] = 0
        self.assertEqual("PASS", resolve_failure_classes(candidate, stale, {"synonyms": {}})[0].status)
        self.assertEqual("FAIL", resolve_failure_classes(candidate, _fresh_closed_ledger(candidate), {"synonyms": {}})[0].status)

    def test_register_requires_governance_candidate_and_user_approval(self) -> None:
        candidate = _candidate()
        registration = {
            "canonical_id": "FC-NEW",
            "aliases": ["G-NEW"],
            "root_cause_code": "new root",
            "root_cause_aliases": ["new alias"],
            "root_cause_description": "new root",
            "required_prevention_controls": ["control"],
            "reopen_condition": "change",
        }
        candidate["failure_classes"] = [
            _proof_declaration(
                "REGISTER",
                proposed_root_cause_text="new root",
                declared_failure_class_ids=[],
                resolved_root_cause_code="new root",
                registration=registration,
            )
        ]
        self.assertEqual("FAIL", resolve_failure_classes(candidate, {"version": 1, "classes": []}, {"synonyms": {}})[0].status)
        candidate["candidate_type"] = "GOVERNANCE"
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, {"version": 1, "classes": []}, {"synonyms": {}})[0].status)
        candidate["review_inputs"].append(
            {
                "review_type": "USER_APPROVAL",
                "completed": True,
                "actor": "USER",
                "user_approved": True,
                "approval_scope": "FAILURE_CLASS_REGISTER:FC-NEW",
                "approval_evidence": "approved",
            }
        )
        self.assertEqual("PASS", resolve_failure_classes(candidate, {"version": 1, "classes": []}, {"synonyms": {}})[0].status)

    def test_register_collisions_fail(self) -> None:
        base_candidate = _candidate()
        base_candidate["candidate_type"] = "GOVERNANCE"
        base_candidate["review_inputs"].append(
            {
                "review_type": "USER_APPROVAL",
                "completed": True,
                "actor": "USER",
                "user_approved": True,
                "approval_scope": "FAILURE_CLASS_REGISTER:FC-NEW",
                "approval_evidence": "approved",
            }
        )
        ledger = _fresh_closed_ledger(base_candidate)
        synonyms = {"synonyms": {"root": ["legacy synonym"]}}
        cases = [
            {"canonical_id": "FC", "aliases": ["G-NEW"], "root_cause_code": "new root", "root_cause_aliases": []},
            {"canonical_id": "FC-NEW", "aliases": ["G-001"], "root_cause_code": "new root", "root_cause_aliases": []},
            {"canonical_id": "FC-NEW", "aliases": ["G-NEW"], "root_cause_code": "root", "root_cause_aliases": []},
            {"canonical_id": "FC-NEW", "aliases": ["G-NEW"], "root_cause_code": "new root", "root_cause_aliases": ["root alias"]},
            {"canonical_id": "FC-NEW", "aliases": ["G-NEW"], "root_cause_code": "new root", "root_cause_aliases": ["legacy synonym"]},
        ]
        for collision in cases:
            with self.subTest(collision=collision):
                candidate = json.loads(json.dumps(base_candidate))
                registration = {
                    **collision,
                    "root_cause_description": "new root",
                    "required_prevention_controls": ["control"],
                    "reopen_condition": "change",
                }
                candidate["failure_classes"] = [
                    _proof_declaration(
                        "REGISTER",
                        proposed_root_cause_text=registration["root_cause_code"],
                        declared_failure_class_ids=[],
                        resolved_root_cause_code=registration["root_cause_code"],
                        registration=registration,
                    )
                ]
                self.assertEqual("FAIL", resolve_failure_classes(candidate, ledger, synonyms)[0].status)

    def test_close_requires_governance_candidate(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [
            _proof_declaration(
                "CLOSE",
                target_prevention_controls=["control"],
                prevention_control_evidence={"control": "PT-1"},
            )
        ]
        self.assertEqual("FAIL", resolve_failure_classes(candidate, _fresh_closed_ledger(candidate, "OPEN"), {"synonyms": {}})[0].status)

    def test_close_requires_all_prevention_controls_and_proof(self) -> None:
        candidate = _candidate()
        candidate["candidate_type"] = "GOVERNANCE"
        ledger = _fresh_closed_ledger(candidate, "OPEN")
        ledger["classes"][0]["required_prevention_controls"] = ["control", "control2"]
        for targets, evidence, expected in [
            (["control"], {"control": "PT-1"}, "NOT_PROVEN"),
            (["control", "control2"], {"control": "PT-1"}, "NOT_PROVEN"),
            (["control", "control2"], {"control": "PT-1", "control2": "UNKNOWN"}, "NOT_PROVEN"),
            (["control", "control2"], {"control": "PT-1", "control2": "PT-1"}, "PASS"),
        ]:
            with self.subTest(targets=targets, evidence=evidence):
                candidate["failure_classes"] = [
                    _proof_declaration(
                        "CLOSE",
                        target_prevention_controls=targets,
                        prevention_control_evidence=evidence,
                    )
                ]
                self.assertEqual(expected, resolve_failure_classes(candidate, ledger, {"synonyms": {}})[0].status)

    def test_closed_ledger_version_change_is_not_proven(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [_proof_declaration("USE")]
        ledger = _fresh_closed_ledger(candidate)
        ledger["version"] = 2
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, ledger, {"synonyms": {}})[0].status)

    def test_mandatory_reviews_are_system_derived(self) -> None:
        candidate = _candidate()
        candidate["review_requirements"] = []
        self.assertEqual("PASS", derive_gate_status([], candidate))
        candidate["review_inputs"] = []
        self.assertEqual("NOT_PROVEN", derive_gate_status([], candidate))

    def test_governance_sensitive_change_requires_independent_or_approved_substitute(self) -> None:
        candidate = _candidate()
        candidate["candidate_type"] = "GOVERNANCE"
        candidate["execution_manifest"]["write_files"] = ["tools/codex_execution_preflight_gate.py"]
        self.assertEqual("NOT_PROVEN", derive_gate_status([], candidate))
        candidate["review_inputs"].append(
            {
                "review_type": "SUBSTITUTE_COMPLETENESS_REVIEW",
                "completed": True,
            }
        )
        self.assertEqual("NOT_PROVEN", derive_gate_status([], candidate))
        candidate["review_inputs"].append(
            {
                "review_type": "USER_APPROVAL",
                "completed": True,
                "actor": "USER",
                "user_approved": True,
                "approval_scope": "SUBSTITUTE_COMPLETENESS_REVIEW",
                "approval_evidence": "approved",
            }
        )
        self.assertEqual("PASS", derive_gate_status([], candidate))

    def test_substitute_cannot_satisfy_normal_implementation_independent_requirement(self) -> None:
        candidate = _candidate()
        candidate["review_requirements"] = ["INDEPENDENT_AUDIT"]
        _add_substitute_approval(candidate)
        self.assertEqual("NOT_PROVEN", derive_gate_status([], candidate))

    def test_candidate_expiry_and_workspace_are_strict(self) -> None:
        candidate = _candidate()
        root = Path.cwd().resolve()
        self.assertEqual("PASS", validate_time_and_workspace(root, candidate, str(root))[0].status)
        candidate["expires_at_utc"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.assertEqual("FAIL", validate_time_and_workspace(root, candidate, str(root))[0].status)
        candidate = _candidate()
        candidate["workspace"] = "other"
        self.assertEqual("FAIL", validate_time_and_workspace(root, candidate, str(root))[0].status)

    def test_governance_artifact_locks_are_exact_unique_and_agents_raw(self) -> None:
        candidate = _candidate()
        self.assertEqual("PASS", validate_artifact_identity(Path.cwd(), candidate)[0].status)
        candidate["artifact_lock"].append(dict(candidate["artifact_lock"][0]))
        _rehash(candidate)
        self.assertEqual("FAIL", validate_artifact_identity(Path.cwd(), candidate)[0].status)
        candidate = _candidate()
        candidate["artifact_lock"] = candidate["artifact_lock"][1:]
        _rehash(candidate)
        self.assertEqual("FAIL", validate_artifact_identity(Path.cwd(), candidate)[0].status)

    def test_agents_hash_must_match_raw_agents_artifact_lock(self) -> None:
        candidate = _candidate()
        candidate["agents_sha256"] = "0" * 64
        _rehash(candidate)
        self.assertEqual("FAIL", validate_artifact_identity(Path.cwd(), candidate)[0].status)

    def test_failure_class_schema_declares_separate_alias_fields(self) -> None:
        schema = json.loads(Path("config/governance/failure_class.schema.json").read_text(encoding="utf-8"))
        self.assertIn("aliases", schema["properties"])
        self.assertIn("root_cause_aliases", schema["properties"])
        self.assertIn("aliases", schema["required"])
        self.assertIn("root_cause_aliases", schema["required"])
        closure_text = json.dumps(schema, ensure_ascii=False)
        self.assertIn("ledger_version", closure_text)
        self.assertNotIn("ledger_sha256", closure_text)

    def test_candidate_schema_declares_failure_action_contract(self) -> None:
        schema = json.loads(Path("config/governance/codex_candidate.schema.json").read_text(encoding="utf-8"))
        declaration = schema["properties"]["failure_classes"]["items"]
        self.assertEqual(
            {"action", "proposed_root_cause_text", "declared_failure_class_ids", "resolved_root_cause_code", "target_prevention_controls", "prevention_control_evidence", "registration"},
            set(declaration["required"]),
        )
        command = schema["properties"]["execution_manifest"]["properties"]["commands"]["items"]
        self.assertEqual({"command_id", "argv", "via_runner", "preflight"}, set(command["required"]))

    def test_manifest_scope_and_command_shape_are_strict(self) -> None:
        candidate = _candidate()
        candidate["execution_manifest"]["commands"] = [{"via_runner": True}]
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)
        candidate = _candidate()
        candidate["execution_manifest"].pop("allowed_functions")
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_manifest_allowed_commands_and_proof_target_order_are_exact(self) -> None:
        candidate = _candidate()
        candidate["execution_manifest"]["allowed_commands"] = ["other"]
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)
        candidate = _candidate()
        candidate["proof_targets"] = ["PT-1", "PT-2"]
        candidate["execution_manifest"]["proof_targets"] = ["PT-2", "PT-1"]
        candidate["evidence_graph"].append(dict(candidate["evidence_graph"][0], proof_id="PT-2"))
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_all_canonical_governance_writes_require_independent_or_substitute(self) -> None:
        for path in GOVERNANCE_ARTIFACTS:
            with self.subTest(path=path):
                candidate = _candidate()
                candidate["candidate_type"] = "GOVERNANCE"
                candidate["execution_manifest"]["write_files"] = [path]
                self.assertEqual("NOT_PROVEN", derive_gate_status([], candidate))

    def test_time_validation_accepts_injected_utc_now_only(self) -> None:
        root = Path.cwd().resolve()
        candidate = _candidate()
        created = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)
        candidate["created_at_utc"] = created.isoformat()
        candidate["expires_at_utc"] = (created + timedelta(hours=1)).isoformat()
        self.assertEqual(
            "PASS",
            validate_time_and_workspace(
                root, candidate, str(root), created + timedelta(minutes=1)
            )[0].status,
        )
        self.assertEqual(
            "FAIL",
            validate_time_and_workspace(
                root, candidate, str(root), datetime(2026, 9, 4, 0, 1)
            )[0].status,
        )

    def test_governed_runner_rejects_output_paths_outside_root_or_same(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                outside = root.parent / "outside-governed.txt"
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command(
                        "echo", candidate_path, report_path, root, outside, root / "stderr.txt"
                    )
                self.assertFalse(result.spawned)
                popen.assert_not_called()
                same = root / "same.txt"
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command(
                        "echo", candidate_path, report_path, root, same, same
                    )
                self.assertFalse(result.spawned)
                popen.assert_not_called()

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
        candidate["review_inputs"] = [
            {
                "review_type": "INDEPENDENT_AUDIT",
                "completed": True,
                "actor": "a",
                "provider": "p",
                "context_id": "c",
                "candidate_actor": "a",
                "candidate_provider": "p",
                "candidate_context_id": "c",
            }
        ]
        self.assertEqual("FAIL", validate_review_separation(candidate)[0].status)

    def test_internal_schema_error_returns_exit_four(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(
                4,
                main(
                    [
                        "--candidate",
                        "state/governance/incoming/invalid.json",
                        "--agents",
                        "AGENTS.md",
                        "--ledger",
                        "knowledge/failure_class_ledger.json",
                        "--synonyms",
                        "config/governance/root_cause_synonyms.json",
                        "--report",
                        "state/governance/reports/x.json",
                    ]
                ),
            )

    def test_stale_candidate_hash_fails(self) -> None:
        candidate = _candidate()
        candidate["candidate_sha256"] = "0" * 64
        self.assertEqual("FAIL", validate_artifact_identity(Path.cwd(), candidate)[0].status)

    def test_candidate_canonicalization_vector_matches(self) -> None:
        self.assertEqual(
            b'{"a":"\xe6\x97\xa5\xe6\x9c\xac","b":2}',
            canonical_json_bytes({"b": 2, "a": "日本"}),
        )

    def test_runner_stdout_limit_stops_child_and_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_command(
                [sys.executable, "-c", "import sys; sys.stdout.write('x' * 100000)"],
                root,
                root / "stdout.txt",
                root / "stderr.txt",
                128,
                128,
            )
            self.assertTrue(result.output_limit_exceeded)
            self.assertNotEqual(0, result.returncode)

    def test_runner_spawns_before_output_sinks_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stdout = root / "stdout.txt"
            stderr = root / "stderr.txt"
            real_popen = subprocess.Popen

            def checked_popen(*args, **kwargs):
                self.assertFalse(stdout.exists())
                self.assertFalse(stderr.exists())
                return real_popen(*args, **kwargs)

            with patch("tools.governance_command_runner.subprocess.Popen", side_effect=checked_popen):
                result = run_command(
                    [sys.executable, "-c", "print('ok')"],
                    root,
                    stdout,
                    stderr,
                    128,
                    128,
                )
            self.assertEqual(0, result.returncode)

    def _valid_runner_fixture(self, root: Path) -> tuple[dict[str, object], Path, Path]:
        _copy_governance_tree(root)
        candidate = _gate_candidate(root)
        candidate_path, report_path = _write_candidate_and_report(root, candidate)
        return candidate, candidate_path, report_path

    def test_runner_rechecks_candidate_hash_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                candidate, candidate_path, report_path = self._valid_runner_fixture(root)
                candidate["task"] = "changed"
                _rehash(candidate)
                candidate_path.write_bytes(canonical_json_bytes(candidate) + b"\n")
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command("echo", candidate_path, report_path, root, root / "state/governance/command_outputs/echo.stdout", root / "state/governance/command_outputs/echo.stderr")
                self.assertFalse(result.spawned)
                popen.assert_not_called()

    def test_runner_rechecks_agents_hash_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                with (root / "AGENTS.md").open("ab") as handle:
                    handle.write(b"\nchanged")
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command("echo", candidate_path, report_path, root, root / "state/governance/command_outputs/echo.stdout", root / "state/governance/command_outputs/echo.stderr")
                self.assertFalse(result.spawned)
                popen.assert_not_called()

    def test_runner_rechecks_governance_artifact_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                with (root / "config/governance/codex_candidate.schema.json").open("ab") as handle:
                    handle.write(b"\n")
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command("echo", candidate_path, report_path, root, root / "state/governance/command_outputs/echo.stdout", root / "state/governance/command_outputs/echo.stderr")
                self.assertFalse(result.spawned)
                popen.assert_not_called()

    def test_runner_rechecks_gate_status_before_spawn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                report = json.loads(report_path.read_text(encoding="utf-8"))
                report["status"] = "FAIL"
                report_path.write_bytes(canonical_json_bytes(report) + b"\n")
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command("echo", candidate_path, report_path, root, root / "state/governance/command_outputs/echo.stdout", root / "state/governance/command_outputs/echo.stderr")
                self.assertFalse(result.spawned)
                popen.assert_not_called()

    def test_runner_rejects_unknown_command_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command("missing", candidate_path, report_path, root, root / "state/governance/command_outputs/echo.stdout", root / "state/governance/command_outputs/echo.stderr")
                self.assertFalse(result.spawned)
                popen.assert_not_called()

    def test_runner_fresh_pass_spawns_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                real_popen = subprocess.Popen
                with patch("tools.governance_command_runner.subprocess.Popen", wraps=real_popen) as popen:
                    result = run_governed_command("echo", candidate_path, report_path, root, root / "state/governance/command_outputs/echo.stdout", root / "state/governance/command_outputs/echo.stderr")
                self.assertTrue(result.spawned)
                self.assertEqual(0, result.returncode)
                self.assertEqual(1, popen.call_count)


    def test_evidence_missing_non_lifecycle_required_field_fails(self) -> None:
        candidate = _gate_candidate()
        candidate["evidence_graph"][0].pop("claim")
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_proof_target_order_mismatch_fails(self) -> None:
        candidate = _gate_candidate()
        proof = dict(candidate["evidence_graph"][0])
        proof["proof_id"] = "PT-2"
        candidate["evidence_graph"].append(proof)
        candidate["proof_targets"] = ["PT-2", "PT-1"]
        candidate["execution_manifest"]["proof_targets"] = ["PT-2", "PT-1"]
        self.assertEqual("FAIL", validate_proof_binding(candidate)[0].status)

    def test_workspace_textual_alias_is_rejected(self) -> None:
        candidate = _gate_candidate()
        root = Path.cwd().resolve()
        candidate["workspace"] = str(root) + "/."
        finding = validate_time_and_workspace(root, candidate, str(root))[0]
        self.assertEqual("FAIL", finding.status)

    def test_powershell_transport_cannot_disagree_with_manifest_command(self) -> None:
        candidate = _gate_candidate()
        script = "tools/safe.ps1"
        candidate["execution_manifest"]["commands"] = [{
            "command_id": "ps",
            "argv": ["powershell.exe", "-Command", "Write-Host ok"],
            "via_runner": True,
            "preflight": False,
        }]
        candidate["execution_manifest"]["allowed_commands"] = ["ps"]
        candidate["shell_transport"] = {
            "layers": ["Git Bash", "PowerShell"],
            "command": ["powershell.exe", "-File", script],
            "script_path": script,
            "script_sha256": "0" * 64,
        }
        candidate["artifact_lock"].append({"path": script, "sha256": "0" * 64, "existing": True})
        self.assertEqual("FAIL", validate_shell_transport(candidate)[0].status)

    def test_powershell_encoded_command_is_rejected(self) -> None:
        candidate = _gate_candidate()
        argv = ["pwsh", "-EncodedCommand", "AAAA"]
        candidate["execution_manifest"]["commands"] = [{
            "command_id": "ps", "argv": argv, "via_runner": True, "preflight": False
        }]
        candidate["execution_manifest"]["allowed_commands"] = ["ps"]
        candidate["shell_transport"] = {"layers": ["Git Bash", "PowerShell"], "command": argv}
        self.assertEqual("FAIL", validate_shell_transport(candidate)[0].status)

    def test_powershell_script_hash_must_match_artifact_lock(self) -> None:
        candidate = _gate_candidate()
        script = "tools/safe.ps1"
        argv = ["pwsh", "-File", script]
        candidate["execution_manifest"]["commands"] = [{
            "command_id": "ps", "argv": argv, "via_runner": True, "preflight": False
        }]
        candidate["execution_manifest"]["allowed_commands"] = ["ps"]
        candidate["shell_transport"] = {
            "layers": ["Git Bash", "PowerShell"], "command": argv,
            "script_path": script, "script_sha256": "1" * 64,
        }
        candidate["artifact_lock"].append({"path": script, "sha256": "2" * 64, "existing": True})
        self.assertEqual("FAIL", validate_shell_transport(candidate)[0].status)

    def test_preflight_report_cannot_target_governance_artifact(self) -> None:
        before = sha256_file(Path("AGENTS.md"))
        self.assertEqual(
            4,
            main([
                "--candidate", "state/governance/incoming/x.json",
                "--agents", "AGENTS.md",
                "--ledger", "knowledge/failure_class_ledger.json",
                "--synonyms", "config/governance/root_cause_synonyms.json",
                "--report", "AGENTS.md",
            ]),
        )
        self.assertEqual(before, sha256_file(Path("AGENTS.md")))

    def test_preflight_candidate_must_be_under_incoming(self) -> None:
        self.assertEqual(
            4,
            main([
                "--candidate", "candidate.json",
                "--agents", "AGENTS.md",
                "--ledger", "knowledge/failure_class_ledger.json",
                "--synonyms", "config/governance/root_cause_synonyms.json",
                "--report", "state/governance/reports/x.json",
            ]),
        )

    def test_governed_runner_rejects_unauthorized_output_without_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                stdout = root / "state/governance/command_outputs/not-authorized.stdout"
                stderr = root / "state/governance/command_outputs/not-authorized.stderr"
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command("echo", candidate_path, report_path, root, stdout, stderr)
                self.assertFalse(result.spawned)
                self.assertFalse(stdout.exists())
                self.assertFalse(stderr.exists())
                popen.assert_not_called()

    def test_governed_runner_auth_failure_does_not_write_authorized_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                stdout = root / "state/governance/command_outputs/echo.stdout"
                stderr = root / "state/governance/command_outputs/echo.stderr"
                report = json.loads(report_path.read_text(encoding="utf-8"))
                report["status"] = "FAIL"
                report_path.write_bytes(canonical_json_bytes(report) + b"\n")
                result = run_governed_command("echo", candidate_path, report_path, root, stdout, stderr)
                self.assertFalse(result.spawned)
                self.assertFalse(stdout.exists())
                self.assertFalse(stderr.exists())

    def test_same_actor_provider_different_context_is_not_independent(self) -> None:
        candidate = _gate_candidate()
        candidate["review_inputs"] = [{
            "review_type": "INDEPENDENT_AUDIT",
            "completed": True,
            "actor": "same",
            "provider": "same-provider",
            "context_id": "review-context",
            "candidate_actor": "same",
            "candidate_provider": "same-provider",
            "candidate_context_id": "candidate-context",
        }]
        self.assertEqual("FAIL", validate_review_separation(candidate)[0].status)

    def test_governance_approval_without_exact_hashes_is_not_proven(self) -> None:
        candidate = _gate_candidate()
        for review in candidate["review_inputs"]:
            if review.get("approval_scope") == "GOVERNANCE_ARTIFACTS":
                review.pop("approved_artifact_hashes")
        self.assertEqual("NOT_PROVEN", validate_review_separation(candidate)[0].status)

    def test_governance_approval_wrong_hashes_is_not_proven(self) -> None:
        candidate = _gate_candidate()
        for review in candidate["review_inputs"]:
            if review.get("approval_scope") == "GOVERNANCE_ARTIFACTS":
                review["approved_artifact_hashes"]["AGENTS.md"] = "0" * 64
        self.assertEqual("NOT_PROVEN", validate_review_separation(candidate)[0].status)

    def test_legacy_closed_use_is_not_proven_but_governance_remediation_can_proceed(self) -> None:
        candidate = _gate_candidate()
        ledger = _fresh_closed_ledger(candidate)
        ledger["classes"][0]["closure_evidence"].pop("ledger_version")
        use = _proof_declaration("USE")
        candidate["failure_classes"] = [use]
        self.assertEqual("NOT_PROVEN", resolve_failure_classes(candidate, ledger, {"synonyms": {}})[0].status)
        candidate["failure_classes"] = [
            _proof_declaration(
                "REMEDIATE",
                target_prevention_controls=["control"],
                prevention_control_evidence={"control": "PT-1"},
            )
        ]
        self.assertEqual("PASS", resolve_failure_classes(candidate, ledger, {"synonyms": {}})[0].status)

    def test_failure_schema_loads_legacy_closed_without_ledger_version_requirement(self) -> None:
        schema = json.loads(Path("config/governance/failure_class.schema.json").read_text(encoding="utf-8"))
        closed_requirements = []
        for clause in schema["allOf"]:
            required = clause.get("then", {}).get("properties", {}).get("closure_evidence", {}).get("required", [])
            if required:
                closed_requirements.extend(required)
        self.assertNotIn("ledger_version", closed_requirements)


    def test_nested_powershell_invocation_is_rejected(self) -> None:
        candidate = _gate_candidate()
        argv = ["bash", "-lc", "powershell.exe -Command Write-Host ok"]
        candidate["execution_manifest"]["commands"] = [
            {"command_id": "nested", "argv": argv, "via_runner": True, "preflight": False}
        ]
        candidate["execution_manifest"]["allowed_commands"] = ["nested"]
        candidate["shell_transport"] = {"layers": ["Git Bash"], "command": argv}
        self.assertEqual("FAIL", validate_shell_transport(candidate)[0].status)

    def test_preflight_report_symlink_alias_is_rejected_without_source_write(self) -> None:
        if not hasattr(Path, "symlink_to"):
            self.skipTest("symlink unsupported")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_governance_tree(root)
            incoming = root / "state/governance/incoming"
            reports = root / "state/governance/reports"
            incoming.mkdir(parents=True)
            reports.mkdir(parents=True)
            (incoming / "x.json").write_text("{}", encoding="utf-8")
            alias = reports / "x.json"
            try:
                alias.symlink_to(root / "AGENTS.md")
            except OSError:
                self.skipTest("symlink creation unavailable")
            before = sha256_file(root / "AGENTS.md")
            old = Path.cwd()
            try:
                os.chdir(root)
                rc = main([
                    "--candidate", "state/governance/incoming/x.json",
                    "--agents", "AGENTS.md",
                    "--ledger", "knowledge/failure_class_ledger.json",
                    "--synonyms", "config/governance/root_cause_synonyms.json",
                    "--report", "state/governance/reports/x.json",
                ])
            finally:
                os.chdir(old)
            self.assertEqual(4, rc)
            self.assertEqual(before, sha256_file(root / "AGENTS.md"))

    def test_runner_candidate_and_report_paths_must_be_canonical_runtime_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                candidate, candidate_path, report_path = self._valid_runner_fixture(root)
                outside_candidate = root / "candidate.json"
                outside_candidate.write_bytes(candidate_path.read_bytes())
                stdout = root / "state/governance/command_outputs/echo.stdout"
                stderr = root / "state/governance/command_outputs/echo.stderr"
                result = run_governed_command("echo", outside_candidate, report_path, root, stdout, stderr)
                self.assertFalse(result.spawned)
                self.assertFalse(stdout.exists())
                self.assertFalse(stderr.exists())

    def test_preflight_governance_input_alias_path_is_rejected(self) -> None:
        self.assertEqual(
            4,
            main([
                "--candidate", "state/governance/incoming/x.json",
                "--agents", "./AGENTS.md",
                "--ledger", "knowledge/failure_class_ledger.json",
                "--synonyms", "config/governance/root_cause_synonyms.json",
                "--report", "state/governance/reports/x.json",
            ]),
        )

    def test_manual_candidate_validation_rejects_schema_invalid_empty_strings(self) -> None:
        cases = []
        for field in ("candidate_id", "objective", "task"):
            candidate = _gate_candidate()
            candidate[field] = ""
            cases.append(candidate)
        for field in ("allowed", "forbidden"):
            candidate = _gate_candidate()
            candidate[field] = [""]
            cases.append(candidate)
        for field in (
            "allowed_functions",
            "allowed_behaviors",
            "allowed_tests",
            "allowed_assertions",
            "forbidden_additions",
        ):
            candidate = _gate_candidate()
            candidate["execution_manifest"][field] = [""]
            cases.append(candidate)
        for candidate in cases:
            self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_output_budget_boolean_is_not_an_integer(self) -> None:
        candidate = _gate_candidate()
        candidate["output_budget"]["max_stdout_bytes"] = True
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)
        self.assertEqual("FAIL", validate_output_transport(candidate)[0].status)

    def test_governance_path_case_alias_is_rejected_and_still_sensitive(self) -> None:
        candidate = _candidate()
        candidate["failure_classes"] = [_proof_declaration("USE")]
        candidate["execution_manifest"]["write_files"].append("agents.md")
        self.assertTrue(gate._requires_independent_audit(candidate))
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_artifact_lock_case_alias_duplicate_fails(self) -> None:
        candidate = _gate_candidate()
        candidate["artifact_lock"].append(
            {"path": "agents.md", "sha256": sha256_file(Path("AGENTS.md")), "existing": True}
        )
        _rehash(candidate)
        self.assertEqual("FAIL", validate_artifact_identity(Path.cwd(), candidate)[0].status)

    def test_review_prior_free_text_conclusion_schema_uses_boolean(self) -> None:
        schema = json.loads(
            Path("config/governance/codex_candidate.schema.json").read_text(encoding="utf-8")
        )
        review_item = schema["properties"]["review_inputs"]["items"]
        self.assertEqual("boolean", review_item["properties"]["prior_free_text_conclusion"]["type"])
        candidate = _gate_candidate()
        candidate["review_inputs"][0]["prior_free_text_conclusion"] = "false"
        self.assertEqual("FAIL", validate_candidate_schema(candidate)[0].status)

    def test_register_declarations_colliding_with_each_other_fail(self) -> None:
        candidate = _gate_candidate()
        second = _proof_declaration(
            "REGISTER",
            proposed_root_cause_text="second root",
            declared_failure_class_ids=[],
            resolved_root_cause_code="second root",
            registration={
                "canonical_id": "FC-SECOND",
                "aliases": ["G-TEST-ONLY"],
                "root_cause_code": "second root",
                "root_cause_aliases": ["second alias"],
                "root_cause_description": "second root",
                "required_prevention_controls": ["second control"],
                "reopen_condition": "second change",
            },
        )
        candidate["failure_classes"].append(second)
        candidate["review_inputs"].append(
            {
                "review_type": "USER_APPROVAL",
                "completed": True,
                "actor": "USER",
                "user_approved": True,
                "approval_scope": "FAILURE_CLASS_REGISTER:FC-SECOND",
                "approval_evidence": "test-approved-second",
            }
        )
        self.assertEqual(
            "FAIL",
            resolve_failure_classes(candidate, {"version": 1, "classes": []}, {"synonyms": {}})[0].status,
        )

    def test_preflight_report_hardlink_cannot_overwrite_governance_artifact(self) -> None:
        if not hasattr(os, "link"):
            self.skipTest("hardlink unsupported")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_governance_tree(root)
            candidate = _gate_candidate(root)
            candidate_path = root / "state/governance/incoming/x.json"
            report_path = root / "state/governance/reports/x.json"
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_bytes(canonical_json_bytes(candidate) + b"\n")
            try:
                os.link(root / "AGENTS.md", report_path)
            except OSError:
                self.skipTest("hardlink creation unavailable")
            before = sha256_file(root / "AGENTS.md")
            old = Path.cwd()
            try:
                os.chdir(root)
                with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                    rc = main(
                        [
                            "--candidate",
                            "state/governance/incoming/x.json",
                            "--agents",
                            "AGENTS.md",
                            "--ledger",
                            "knowledge/failure_class_ledger.json",
                            "--synonyms",
                            "config/governance/root_cause_synonyms.json",
                            "--report",
                            "state/governance/reports/x.json",
                        ]
                    )
            finally:
                os.chdir(old)
            self.assertEqual(4, rc)
            self.assertEqual(before, sha256_file(root / "AGENTS.md"))

    def test_governed_runner_hardlink_output_does_not_spawn_or_overwrite(self) -> None:
        if not hasattr(os, "link"):
            self.skipTest("hardlink unsupported")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                stdout = root / "state/governance/command_outputs/echo.stdout"
                stderr = root / "state/governance/command_outputs/echo.stderr"
                stdout.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(root / "AGENTS.md", stdout)
                except OSError:
                    self.skipTest("hardlink creation unavailable")
                before = sha256_file(root / "AGENTS.md")
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command(
                        "echo", candidate_path, report_path, root, stdout, stderr
                    )
                self.assertFalse(result.spawned)
                self.assertEqual(before, sha256_file(root / "AGENTS.md"))
                self.assertFalse(stderr.exists())
                popen.assert_not_called()

    def test_runner_low_level_cli_is_rejected_in_canonical_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            stdout = root / "stdout.txt"
            stderr = root / "stderr.txt"
            with patch.object(runner, "CANONICAL_WORKSPACE", str(root)), patch(
                "tools.governance_command_runner.subprocess.Popen"
            ) as popen:
                with self.assertRaises(ValueError):
                    runner.main(
                        [
                            "--command",
                            json.dumps([sys.executable, "-c", "print('no')"]),
                            "--cwd",
                            str(root),
                            "--stdout",
                            str(stdout),
                            "--stderr",
                            str(stderr),
                            "--max-stdout-bytes",
                            "128",
                            "--max-stderr-bytes",
                            "128",
                        ]
                    )
            popen.assert_not_called()
            self.assertFalse(stdout.exists())
            self.assertFalse(stderr.exists())

    def test_runner_candidate_and_report_require_json_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(gate, "CANONICAL_WORKSPACE", str(root.resolve())):
                _, candidate_path, report_path = self._valid_runner_fixture(root)
                candidate_no_suffix = candidate_path.with_suffix("")
                candidate_no_suffix.write_bytes(candidate_path.read_bytes())
                stdout = root / "state/governance/command_outputs/echo.stdout"
                stderr = root / "state/governance/command_outputs/echo.stderr"
                with patch("tools.governance_command_runner.subprocess.Popen") as popen:
                    result = run_governed_command(
                        "echo", candidate_no_suffix, report_path, root, stdout, stderr
                    )
                self.assertFalse(result.spawned)
                popen.assert_not_called()

    def test_non_redundant_candidate_passes_all_conditions(self) -> None:
        candidate = _gate_candidate()
        root = Path.cwd().resolve()
        findings = []
        findings.extend(validate_candidate_schema(candidate))
        findings.extend(validate_time_and_workspace(root, candidate, str(root)))
        findings.extend(validate_proof_binding(candidate))
        findings.extend(validate_shell_transport(candidate))
        findings.extend(validate_output_transport(candidate))
        findings.extend(validate_static_contradictions(candidate))
        findings.extend(validate_artifact_identity(root, candidate))
        findings.extend(resolve_failure_classes(candidate, {"version": 1, "classes": []}, {"synonyms": {}}))
        findings.extend(validate_evidence_lifecycle(candidate))
        findings.extend(validate_runtime_preconditions(candidate))
        findings.extend(validate_rollback_stop(candidate))
        findings.extend(validate_user_operations(candidate))
        findings.extend(validate_review_separation(candidate))
        self.assertEqual("PASS", derive_gate_status(findings, candidate))


if __name__ == "__main__":
    unittest.main()
