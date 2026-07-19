from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from phoenix_core.environment_validator import EnvironmentValidator


class EnvironmentValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name).resolve()
        (self.root / "config").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "phoenix_core").mkdir()
        (self.root / "app.py").write_text(
            "def main():\n    return 0\n",
            encoding="utf-8",
        )
        (self.root / "config" / "sample.json").write_text(
            json.dumps({"enabled": True}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def config(self) -> dict:
        return {
            "schema_version": 1,
            "minimum_python": "3.8.0",
            "require_virtual_environment": False,
            "required_modules": ["json"],
            "required_directories": ["config", "tests", "phoenix_core"],
            "create_directories": ["logs", "reports"],
            "required_files": ["app.py", "config/sample.json"],
            "required_json_files": ["config/sample.json"],
            "source_files": ["app.py", "config/sample.json"],
            "writable_directories": ["logs", "reports"],
            "minimum_free_disk_mb": 1,
            "powershell_scripts": [],
            "report_file": "reports/environment_report.json",
        }

    def test_valid_environment_passes(self) -> None:
        report = EnvironmentValidator(root=self.root, config=self.config()).run()
        self.assertTrue(report.ready)

    def test_missing_file_fails(self) -> None:
        config = self.config()
        config["required_files"].append("missing.py")
        report = EnvironmentValidator(root=self.root, config=config).run()
        self.assertFalse(report.ready)

    def test_invalid_json_fails(self) -> None:
        (self.root / "config" / "sample.json").write_text(
            '{"enabled": ',
            encoding="utf-8",
        )
        report = EnvironmentValidator(root=self.root, config=self.config()).run()
        self.assertFalse(report.ready)

    def test_python_syntax_error_fails(self) -> None:
        (self.root / "app.py").write_text("def broken(:\n", encoding="utf-8")
        report = EnvironmentValidator(root=self.root, config=self.config()).run()
        self.assertFalse(report.ready)

    def test_report_saved(self) -> None:
        report = EnvironmentValidator(
            root=self.root,
            config=self.config(),
        ).run_and_save()
        report_file = self.root / "reports" / "environment_report.json"
        self.assertTrue(report.ready)
        self.assertTrue(report_file.is_file())
        saved = json.loads(report_file.read_text(encoding="utf-8"))
        self.assertTrue(saved["ready"])

    def test_path_traversal_fails_closed(self) -> None:
        config = self.config()
        config["required_files"].append("../outside.py")
        report = EnvironmentValidator(root=self.root, config=config).run()
        self.assertFalse(report.ready)


if __name__ == "__main__":
    unittest.main()
