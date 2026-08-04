from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import run_phoenix


class Step42RunPhoenixIntegrationTest(unittest.TestCase):
    def test_order_manager_is_registered_and_launchable_in_monitor_only(self) -> None:
        scripts = [str(task["script"]) for task in run_phoenix.TASKS]
        self.assertLess(scripts.index("trade_engine.py"), scripts.index("order_manager.py"))
        self.assertLess(scripts.index("order_manager.py"), scripts.index("ranking_ai.py"))
        self.assertIn("order_manager.py", run_phoenix.REFRESH_ONLY_SCRIPTS)
        self.assertIn("order_manager.py", run_phoenix.MONITOR_ONLY_ALLOWED_SCRIPTS)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                mock.patch.object(run_phoenix, "LOG_DIR", root / "logs"),
                mock.patch.object(run_phoenix, "LOG_FILE", root / "logs" / "run.log"),
                mock.patch.object(
                    run_phoenix.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""),
                ) as subprocess_run,
            ):
                result = run_phoenix.run_script(
                    "Step42 Pre-Order Gate",
                    "order_manager.py",
                    True,
                    monitor_only=True,
                )

        self.assertTrue(result[0])
        self.assertEqual(0, result[2])
        subprocess_run.assert_called_once()

        command = subprocess_run.call_args.args[0]
        kwargs = subprocess_run.call_args.kwargs
        self.assertTrue(any(str(part).endswith("order_manager.py") for part in command))
        self.assertEqual("MONITOR_ONLY", kwargs["env"]["PHOENIX_OPERATING_SCOPE"])
        self.assertEqual("DISABLED", kwargs["env"]["PHOENIX_TRADING_ACTIONS"])


if __name__ == "__main__":
    unittest.main()
