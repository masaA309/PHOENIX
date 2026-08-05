from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from phoenix_core.data_freshness import JST
import phoenix_core.order_bridge_gate as step42
import phoenix_core.vba_bridge_contract as bridge
import run_phoenix


NOW = datetime(2026, 8, 5, 9, 0, 0, tzinfo=JST)


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


class Step43RunPhoenixIntegrationTest(unittest.TestCase):
    def _step42_row(self, *, generated_at: datetime, expires_at: datetime) -> dict[str, str]:
        intent_id = "PHX42-20260805-1301T-BUY-STEP43TEST"
        idempotency_key = "step43-test-idempotency-key"
        quantity = 100
        reference_price = 1000.0
        limit_price = 1000.0
        stop_loss_price = 950.0
        take_profit_price = 1100.0
        estimated_notional = quantity * limit_price
        estimated_max_loss = quantity * (limit_price - stop_loss_price)
        return {
            "schema_version": "1",
            "intent_id": intent_id,
            "idempotency_key": idempotency_key,
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "expires_at": expires_at.isoformat(timespec="seconds"),
            "trading_mode": "PAPER",
            "execution_mode": "DRY_RUN",
            "signal_date": generated_at.date().isoformat(),
            "ticker": "1301.T",
            "market": "TSE",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": str(quantity),
            "lot_size": "100",
            "reference_price": f"{reference_price:.2f}",
            "limit_price": f"{limit_price:.2f}",
            "stop_loss_price": f"{stop_loss_price:.2f}",
            "take_profit_price": f"{take_profit_price:.2f}",
            "estimated_notional": f"{estimated_notional:.2f}",
            "estimated_max_loss": f"{estimated_max_loss:.2f}",
            "source": "reports/trade_signals.csv",
            "status": "APPROVED",
            "blocked_reasons": "",
            "created_by": "PHOENIX_STEP42_PREORDER_GATE",
        }

    def _write_step42_source(
        self,
        root: Path,
        *,
        report_status: str = "APPROVED",
        generated_at: datetime = NOW,
        expires_at: datetime = NOW + timedelta(minutes=15),
        operating_scope: str = "OPERATIONAL",
    ) -> tuple[dict[str, object], dict[str, str]]:
        row = self._step42_row(generated_at=generated_at, expires_at=expires_at)
        instruction_path = root / step42.INSTRUCTION_FILE
        report_path = root / step42.REPORT_JSON_FILE
        _write_csv(instruction_path, step42.OUTPUT_COLUMNS, [row])
        report = {
            "schema_version": step42.SCHEMA_VERSION,
            "version": step42.VERSION,
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "expires_at": expires_at.isoformat(timespec="seconds"),
            "status": report_status,
            "mode": step42.TRADING_MODE,
            "trading_mode": step42.TRADING_MODE,
            "execution_mode": step42.EXECUTION_MODE,
            "trading_actions": "PAPER_ONLY",
            "operating_scope": operating_scope,
            "orders_submitted": 0,
            "external_orders_submitted": 0,
            "candidate_count": 1,
            "approved_count": 1,
            "blocked_count": 0 if report_status == "APPROVED" else 1,
            "blockers": [] if report_status == "APPROVED" else ["TEST_BLOCKED"],
            "candidate_input_guard": None,
            "instructions": [row],
            "instruction_file": str(instruction_path),
            "report_json": str(report_path),
            "report_text": str(root / "reports" / "step42_report.txt"),
            "audit_jsonl": str(root / "reports" / "step42_audit.jsonl"),
            "state_file": str(root / "state" / "step42_state.json"),
            "source": "reports/trade_signals.csv",
            "created_by": "PHOENIX_STEP42_PREORDER_GATE",
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report, row

    def _subprocess_side_effect(
        self,
        root: Path,
        command: list[str],
        *,
        env: dict[str, str],
        returncode: int = 0,
        stdout: str = "ok\n",
        stderr: str = "",
        raise_error: Exception | None = None,
    ) -> SimpleNamespace:
        if raise_error is not None:
            raise raise_error
        with mock.patch.dict(bridge.os.environ, env, clear=True):
            bridge.run_vba_bridge_contract(root, now=NOW)
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_vba_bridge_is_registered_after_order_manager_and_allowed_in_monitor_only(self) -> None:
        scripts = [str(task["script"]) for task in run_phoenix.TASKS]
        self.assertLess(scripts.index("trade_engine.py"), scripts.index("order_manager.py"))
        self.assertLess(scripts.index("order_manager.py"), scripts.index("vba_bridge.py"))
        self.assertLess(scripts.index("vba_bridge.py"), scripts.index("ranking_ai.py"))
        self.assertIn("vba_bridge.py", run_phoenix.REFRESH_ONLY_SCRIPTS)
        self.assertIn("vba_bridge.py", run_phoenix.MONITOR_ONLY_ALLOWED_SCRIPTS)

    def test_run_script_creates_pending_in_operational_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_step42_source(root, report_status="APPROVED")
            with (
                mock.patch.object(run_phoenix, "LOG_DIR", root / "logs"),
                mock.patch.object(run_phoenix, "LOG_FILE", root / "logs" / "run.log"),
                mock.patch.object(run_phoenix.subprocess, "run") as subprocess_run,
            ):
                subprocess_run.side_effect = lambda *args, **kwargs: self._subprocess_side_effect(
                    root,
                    args[0],
                    env=kwargs["env"],
                )
                result = run_phoenix.run_script(
                    "Step43 VBA Bridge Contract",
                    "vba_bridge.py",
                    True,
                    monitor_only=False,
                )

            self.assertTrue(result[0])
            self.assertEqual(0, result[2])
            subprocess_run.assert_called_once()
            kwargs = subprocess_run.call_args.kwargs
            self.assertEqual("OPERATIONAL", kwargs["env"]["PHOENIX_OPERATING_SCOPE"])
            self.assertEqual("PAPER_ONLY", kwargs["env"]["PHOENIX_TRADING_ACTIONS"])
            self.assertEqual(1, len(list((root / bridge.PENDING_DIR).glob("*.csv"))))

    def test_run_script_blocks_pending_in_monitor_only_and_when_step42_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_step42_source(root, report_status="APPROVED")
            with (
                mock.patch.object(run_phoenix, "LOG_DIR", root / "logs"),
                mock.patch.object(run_phoenix, "LOG_FILE", root / "logs" / "run.log"),
                mock.patch.object(run_phoenix.subprocess, "run") as subprocess_run,
            ):
                subprocess_run.side_effect = lambda *args, **kwargs: self._subprocess_side_effect(
                    root,
                    args[0],
                    env=kwargs["env"],
                )
                result = run_phoenix.run_script(
                    "Step43 VBA Bridge Contract",
                    "vba_bridge.py",
                    True,
                    monitor_only=True,
                )

            self.assertTrue(result[0])
            self.assertEqual(0, result[2])
            self.assertEqual(0, len(list((root / bridge.PENDING_DIR).glob("*.csv"))))
            kwargs = subprocess_run.call_args.kwargs
            self.assertEqual("MONITOR_ONLY", kwargs["env"]["PHOENIX_OPERATING_SCOPE"])
            self.assertEqual("DISABLED", kwargs["env"]["PHOENIX_TRADING_ACTIONS"])

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_step42_source(root, report_status="BLOCKED")
            with (
                mock.patch.object(run_phoenix, "LOG_DIR", root / "logs"),
                mock.patch.object(run_phoenix, "LOG_FILE", root / "logs" / "run.log"),
                mock.patch.object(run_phoenix.subprocess, "run") as subprocess_run,
            ):
                subprocess_run.side_effect = lambda *args, **kwargs: self._subprocess_side_effect(
                    root,
                    args[0],
                    env=kwargs["env"],
                )
                result = run_phoenix.run_script(
                    "Step43 VBA Bridge Contract",
                    "vba_bridge.py",
                    True,
                    monitor_only=False,
                )

            self.assertTrue(result[0])
            self.assertEqual(0, result[2])
            self.assertEqual(0, len(list((root / bridge.PENDING_DIR).glob("*.csv"))))

    def test_run_script_fails_closed_when_subprocess_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self._write_step42_source(root, report_status="APPROVED")
            with (
                mock.patch.object(run_phoenix, "LOG_DIR", root / "logs"),
                mock.patch.object(run_phoenix, "LOG_FILE", root / "logs" / "run.log"),
                mock.patch.object(run_phoenix.subprocess, "run") as subprocess_run,
            ):
                subprocess_run.side_effect = RuntimeError("boom")
                result = run_phoenix.run_script(
                    "Step43 VBA Bridge Contract",
                    "vba_bridge.py",
                    True,
                    monitor_only=False,
                )

            self.assertFalse(result[0])
            self.assertEqual(-3, result[2])
            self.assertEqual(0, len(list((root / bridge.PENDING_DIR).glob("*.csv"))))


if __name__ == "__main__":
    unittest.main()
