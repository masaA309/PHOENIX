from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

import repository_guardian
from repository_guardian import (
    DEFAULT_EXPECTED_ORIGIN_URL,
    DEFAULT_EXPECTED_ROOT,
    EXPECTED_ORIGIN_ENV,
    EXPECTED_ROOT_ENV,
    config_from_environment,
    run_repository_guardian,
)


class RepositoryGuardianStep365Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary_directory.name)
        self.expected_root = (
            self.base / "OneDrive" / "desktop" / "family_folder" / "PHOENIX"
        )
        self.expected_root.mkdir(parents=True)
        self.origin = DEFAULT_EXPECTED_ORIGIN_URL

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git_reader(
        self,
        *,
        git_root: Path | None = None,
        origin: str | None = None,
        branch: str | None = "main",
        failures: set[tuple[str, ...]] | None = None,
    ):
        values = {
            ("rev-parse", "--show-toplevel"): str(
                self.expected_root if git_root is None else git_root
            ),
            ("remote", "get-url", "origin"): self.origin if origin is None else origin,
            ("branch", "--show-current"): branch,
        }
        failed_commands = failures or set()

        def read(command, cwd):
            key = tuple(command)
            if key in failed_commands:
                raise RuntimeError(f"simulated failure: {' '.join(key)}")
            value = values[key]
            return "" if value is None else str(value)

        return read

    def run_guardian(self, *, cwd: Path | None = None, reader=None):
        # TEMP may itself be below a Codex directory. The dedicated Codex-copy
        # test exercises the real classifier without this isolation patch.
        with mock.patch("repository_guardian._is_codex_path", return_value=False):
            return run_repository_guardian(
                expected_root=self.expected_root,
                expected_origin_url=self.origin,
                cwd=cwd or self.expected_root,
                report_dir=self.base / "logs",
                git_reader=reader or self.git_reader(),
                environment={},
            )

    def test_correct_canonical_repository_is_ready_and_reports_atomically(self) -> None:
        with mock.patch(
            "repository_guardian.os.replace",
            wraps=os.replace,
        ) as replace:
            result = self.run_guardian()

        self.assertTrue(result.ready)
        self.assertEqual("READY", result.status)
        self.assertEqual((), result.reasons)
        self.assertTrue(result.is_onedrive)
        self.assertFalse(result.is_codex_copy)
        self.assertEqual(2, replace.call_count)

        json_path = Path(result.json_report_path)
        text_path = Path(result.text_report_path)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        text = text_path.read_text(encoding="utf-8")
        self.assertEqual("READY", payload["status"])
        self.assertEqual("main", payload["branch"])
        self.assertEqual("PAPER", payload["mode"])
        self.assertEqual(0, payload["orders_submitted"])
        self.assertIn("Mode: PAPER", text)
        self.assertIn("Orders submitted: 0", text)
        self.assertEqual([], list((self.base / "logs").glob("*.tmp")))

    def test_second_phoenix_root_is_blocked_as_duplicate(self) -> None:
        duplicate = self.base / "backup" / "PHOENIX"
        duplicate.mkdir(parents=True)
        result = self.run_guardian(
            cwd=duplicate,
            reader=self.git_reader(git_root=duplicate),
        )

        self.assertFalse(result.ready)
        self.assertIn("GIT_ROOT_MISMATCH", result.reasons)
        self.assertIn("DUPLICATE_REPOSITORY_SUSPECTED", result.reasons)
        self.assertTrue(result.duplicate_copy_suspected)

    def test_origin_mismatch_is_blocked(self) -> None:
        result = self.run_guardian(
            reader=self.git_reader(origin="https://example.invalid/other/PHOENIX.git")
        )

        self.assertIn("ORIGIN_MISMATCH", result.reasons)
        self.assertEqual("BLOCKED", result.status)

    def test_repository_other_than_phoenix_is_blocked(self) -> None:
        other_root = self.base / "NOT_PHOENIX"
        other_root.mkdir()
        result = run_repository_guardian(
            expected_root=other_root,
            expected_origin_url=self.origin,
            cwd=other_root,
            report_dir=self.base / "other_logs",
            git_reader=self.git_reader(git_root=other_root),
            environment={},
        )

        self.assertIn("REPOSITORY_NAME_MISMATCH", result.reasons)
        self.assertEqual("BLOCKED", result.status)

    def test_codex_work_copy_is_always_blocked(self) -> None:
        codex_root = self.base / "Documents" / "Codex" / "task" / "PHOENIX"
        codex_root.mkdir(parents=True)
        result = run_repository_guardian(
            expected_root=codex_root,
            expected_origin_url=self.origin,
            cwd=codex_root,
            report_dir=self.base / "codex_logs",
            git_reader=self.git_reader(git_root=codex_root),
            environment={},
        )

        self.assertIn("CODEX_WORK_COPY", result.reasons)
        self.assertIn("DUPLICATE_REPOSITORY_SUSPECTED", result.reasons)
        self.assertTrue(result.is_codex_copy)

    def test_missing_git_root_fails_closed(self) -> None:
        command = ("rev-parse", "--show-toplevel")
        result = self.run_guardian(
            reader=self.git_reader(failures={command}),
        )

        self.assertIn("GIT_ROOT_UNAVAILABLE", result.reasons)
        self.assertIn("REPOSITORY_NAME_MISMATCH", result.reasons)
        self.assertIn("git_root", result.git_errors)
        self.assertEqual("BLOCKED", result.status)

    def test_missing_origin_and_branch_fail_closed(self) -> None:
        result = self.run_guardian(
            reader=self.git_reader(origin="", branch=None),
        )

        self.assertIn("ORIGIN_UNAVAILABLE", result.reasons)
        self.assertIn("BRANCH_UNAVAILABLE", result.reasons)
        self.assertEqual("BLOCKED", result.status)

    def test_cwd_outside_reported_git_root_is_blocked(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        result = self.run_guardian(cwd=outside)

        self.assertIn("CWD_OUTSIDE_GIT_ROOT", result.reasons)
        self.assertEqual("BLOCKED", result.status)

    def test_expected_root_and_origin_are_configurable_by_environment(self) -> None:
        configured_root = self.base / "configured" / "PHOENIX"
        environment = {
            EXPECTED_ROOT_ENV: str(configured_root),
            EXPECTED_ORIGIN_ENV: "https://github.com/example/PHOENIX.git",
        }

        config = config_from_environment(environment)

        self.assertEqual(configured_root.resolve(), config.expected_root)
        self.assertEqual(environment[EXPECTED_ORIGIN_ENV], config.expected_origin_url)
        defaults = config_from_environment({})
        self.assertEqual(
            repository_guardian._resolved_path(DEFAULT_EXPECTED_ROOT),
            defaults.expected_root,
        )
        self.assertEqual(DEFAULT_EXPECTED_ORIGIN_URL, defaults.expected_origin_url)

    def test_windows_and_git_bash_paths_compare_equally(self) -> None:
        windows = "C:/Users/ashtc/OneDrive/project/PHOENIX"
        git_bash = "/c/Users/ashtc/OneDrive/project/PHOENIX"
        cygdrive = "/cygdrive/c/Users/ashtc/OneDrive/project/PHOENIX"

        self.assertTrue(repository_guardian._paths_equal(windows, git_bash))
        self.assertTrue(repository_guardian._paths_equal(windows, cygdrive))

    def test_report_write_failure_changes_ready_to_blocked(self) -> None:
        with mock.patch(
            "repository_guardian._atomic_write",
            side_effect=OSError("read only"),
        ):
            result = self.run_guardian()

        self.assertEqual("BLOCKED", result.status)
        self.assertIn("REPORT_WRITE_FAILED", result.reasons)
        self.assertIn("read only", result.report_error or "")

    def test_run_phoenix_stops_before_initialization_when_blocked(self) -> None:
        run_phoenix = importlib.import_module("run_phoenix")
        blocked = SimpleNamespace(
            ready=False,
            reasons=("GIT_ROOT_MISMATCH",),
            report_error=None,
        )
        with (
            mock.patch.object(run_phoenix, "configure_console"),
            mock.patch.object(
                run_phoenix,
                "run_repository_guardian",
                return_value=blocked,
            ) as guard,
            mock.patch.object(run_phoenix, "initialize_directories") as initialize,
            mock.patch.object(sys, "argv", ["run_phoenix.py"]),
        ):
            with self.assertRaises(SystemExit) as stopped:
                run_phoenix.main()

        self.assertEqual(2, stopped.exception.code)
        guard.assert_called_once_with(report_dir=run_phoenix.LOG_DIR)
        initialize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
