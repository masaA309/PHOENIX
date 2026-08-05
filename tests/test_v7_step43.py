from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from phoenix_core.data_freshness import JST
import phoenix_core.order_bridge_gate as step42
import phoenix_core.vba_bridge_contract as bridge


NOW = datetime(2026, 8, 5, 9, 0, 0, tzinfo=JST)


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


class Step43VbaBridgeContractTest(unittest.TestCase):
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

    def _write_receipt(
        self,
        root: Path,
        *,
        intent_id: str,
        idempotency_key: str,
        source_checksum: str,
        result: str = "ACCEPTED",
        reason_codes: list[str] | None = None,
        vba_instance_id: str = "VBA-LOCAL-01",
        orders_submitted: int = 0,
        file_name: str | None = None,
    ) -> Path:
        path = root / bridge.INBOX_DIR / (file_name or f"{intent_id}.csv")
        row = {
            "schema_version": "1",
            "intent_id": intent_id,
            "idempotency_key": idempotency_key,
            "received_at": NOW.isoformat(timespec="seconds"),
            "result": result,
            "reason_codes": ";".join(reason_codes or []),
            "vba_instance_id": vba_instance_id,
            "source_checksum": source_checksum,
            "orders_submitted": str(orders_submitted),
        }
        row["checksum"] = bridge._checksum_fields(row, bridge.RECEIPT_COLUMNS)
        _write_csv(path, bridge.RECEIPT_COLUMNS, [row])
        return path

    def _pending_csv(self, root: Path, intent_id: str) -> Path:
        return root / bridge.PENDING_DIR / f"{intent_id}.csv"

    def _read_csv_row(self, path: Path) -> dict[str, str]:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(io.StringIO(file.read(), newline=""), strict=True)
            return next(reader)

    def test_outbox_generation_writes_utf8_csv_with_fixed_columns_checksum_and_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report, step42_row = self._write_step42_source(root)
            with mock.patch.dict(
                bridge.os.environ,
                {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"},
                clear=False,
            ):
                summary = bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])

            self.assertEqual("READY", summary["status"])
            self.assertEqual("DISABLED", summary["trading_actions"])
            self.assertEqual(1, summary["pending_created_count"])
            self.assertEqual(0, summary["orders_submitted"])

            pending_file = self._pending_csv(root, step42_row["intent_id"])
            self.assertTrue(pending_file.exists())
            self.assertTrue(pending_file.read_bytes().startswith(b"\xef\xbb\xbf"))

            row = self._read_csv_row(pending_file)
            self.assertEqual(tuple(bridge.OUTBOX_COLUMNS), tuple(row.keys()))
            self.assertEqual("PENDING", row["bridge_status"])
            self.assertEqual(
                bridge._checksum_fields(row, bridge.OUTBOX_COLUMNS),
                row["checksum"],
            )
            self.assertEqual("PAPER", row["trading_mode"])
            self.assertEqual("DRY_RUN", row["execution_mode"])

            state = json.loads((root / bridge.STATE_FILE).read_text(encoding="utf-8"))
            record = state["records"][step42_row["intent_id"]]
            self.assertEqual("PENDING", record["status"])
            self.assertEqual(row["checksum"], record["checksum"])
            self.assertEqual(64, len(record["outbox_sha256"]))

    def test_duplicate_restart_does_not_create_second_pending_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report, step42_row = self._write_step42_source(root)
            with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                first = bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])
                second = bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])

            self.assertEqual(1, first["pending_created_count"])
            self.assertEqual(1, second["pending_skipped_count"])
            self.assertEqual(1, len(list((root / bridge.PENDING_DIR).glob("*.csv"))))

    def test_expired_step42_report_blocks_new_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report, step42_row = self._write_step42_source(
                root,
                expires_at=NOW - timedelta(minutes=1),
            )
            with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                summary = bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])

            self.assertEqual("BLOCKED", summary["status"])
            self.assertIn("STEP42_EXPIRED", summary["blockers"])
            self.assertFalse(list((root / bridge.PENDING_DIR).glob("*.csv")))

    def test_receipt_acceptance_moves_pending_to_complete_and_updates_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report, step42_row = self._write_step42_source(root)
            with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])
            pending_row = self._read_csv_row(self._pending_csv(root, step42_row["intent_id"]))
            receipt = self._write_receipt(
                root,
                intent_id=step42_row["intent_id"],
                idempotency_key=step42_row["idempotency_key"],
                source_checksum=pending_row["checksum"],
                result="ACCEPTED",
            )

            summary = bridge.ingest_bridge_receipts(root, now=NOW)

            self.assertEqual("READY", summary["status"])
            self.assertEqual(1, summary["accepted_count"])
            self.assertEqual(1, summary["receipt_processed_count"])
            self.assertFalse(receipt.exists())
            self.assertFalse(self._pending_csv(root, step42_row["intent_id"]).exists())
            self.assertTrue((root / bridge.COMPLETE_DIR / f"{step42_row['intent_id']}.csv").exists())

            state = json.loads((root / bridge.STATE_FILE).read_text(encoding="utf-8"))
            record = state["records"][step42_row["intent_id"]]
            self.assertEqual("ACCEPTED", record["status"])
            self.assertEqual("ACCEPTED", record["result"])

    def test_duplicate_receipt_is_dropped_after_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report, step42_row = self._write_step42_source(root)
            with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])
            pending_row = self._read_csv_row(self._pending_csv(root, step42_row["intent_id"]))
            self._write_receipt(
                root,
                intent_id=step42_row["intent_id"],
                idempotency_key=step42_row["idempotency_key"],
                source_checksum=pending_row["checksum"],
                result="ACCEPTED",
            )
            bridge.ingest_bridge_receipts(root, now=NOW)
            duplicate = self._write_receipt(
                root,
                intent_id=step42_row["intent_id"],
                idempotency_key=step42_row["idempotency_key"],
                source_checksum=pending_row["checksum"],
                result="ACCEPTED",
            )

            summary = bridge.ingest_bridge_receipts(root, now=NOW)

            self.assertEqual(1, summary["duplicate_count"])
            self.assertFalse(duplicate.exists())
            state = json.loads((root / bridge.STATE_FILE).read_text(encoding="utf-8"))
            self.assertEqual("ACCEPTED", state["records"][step42_row["intent_id"]]["status"])

    def test_receipt_validation_fail_closed_for_id_mismatch_unknown_status_and_nonzero_orders(self) -> None:
        cases = [
            (
                "id mismatch",
                {
                    "file_name": f"{'PHX42-20260805-1301T-BUY-STEP43TEST'}.csv",
                    "intent_id": "WRONG-INTENT",
                    "result": "ACCEPTED",
                },
            ),
            ("unknown status", {"result": "MAYBE"}),
            ("nonzero orders", {"result": "ACCEPTED", "orders_submitted": 1}),
            ("source checksum mismatch", {"result": "ACCEPTED", "source_checksum": "f" * 64}),
        ]
        for name, overrides in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                report, step42_row = self._write_step42_source(root)
                with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                    bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])
                pending_row = self._read_csv_row(self._pending_csv(root, step42_row["intent_id"]))
                intent_id = overrides.get("intent_id", step42_row["intent_id"])
                self._write_receipt(
                    root,
                    intent_id=intent_id,
                    idempotency_key=step42_row["idempotency_key"],
                    source_checksum=overrides.get("source_checksum", pending_row["checksum"]),
                    result=overrides.get("result", "ACCEPTED"),
                    orders_submitted=overrides.get("orders_submitted", 0),
                    file_name=overrides.get("file_name"),
                )

                summary = bridge.ingest_bridge_receipts(root, now=NOW)

                self.assertEqual(1, summary["corrupt_count"])
                state = json.loads((root / bridge.STATE_FILE).read_text(encoding="utf-8"))
                self.assertEqual("CORRUPT", state["records"][step42_row["intent_id"]]["status"])

    def test_broken_receipt_input_is_corrupt_for_csv_and_json(self) -> None:
        for name, file_name, content in [
            ("csv", "broken.csv", "schema_version,intent_id\n1\n"),
            ("json", "broken.json", "{"),
        ]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                report, step42_row = self._write_step42_source(root)
                with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                    bridge.stage_bridge_outbox(root, now=NOW, report=report, rows=[step42_row])
                inbox = root / bridge.INBOX_DIR
                inbox.mkdir(parents=True, exist_ok=True)
                (inbox / file_name).write_text(content, encoding="utf-8")

                summary = bridge.ingest_bridge_receipts(root, now=NOW)

                self.assertEqual(1, summary["corrupt_count"])
                self.assertFalse((inbox / file_name).exists())

    def test_monitor_only_fail_safe_and_blocked_step42_do_not_create_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report, step42_row = self._write_step42_source(root)
            with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "MONITOR_ONLY"}, clear=False):
                monitor_summary = bridge.run_vba_bridge_contract(root, now=NOW)

            self.assertEqual("BLOCKED", monitor_summary["status"])
            self.assertFalse(list((root / bridge.PENDING_DIR).glob("*.csv")))

            fail_safe_log = root / "logs" / "fail_safe.json"
            fail_safe_log.parent.mkdir(parents=True, exist_ok=True)
            fail_safe_log.write_text(
                json.dumps({"status": "FAIL_SAFE"}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                fail_safe_summary = bridge.run_vba_bridge_contract(root, now=NOW)

            self.assertEqual("BLOCKED", fail_safe_summary["status"])
            self.assertIn("FAIL_SAFE_ACTIVE", fail_safe_summary["blockers"])
            self.assertFalse(list((root / bridge.PENDING_DIR).glob("*.csv")))

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report, step42_row = self._write_step42_source(root, report_status="BLOCKED")
            with mock.patch.dict(bridge.os.environ, {"PHOENIX_OPERATING_SCOPE": "OPERATIONAL"}, clear=False):
                blocked_summary = bridge.run_vba_bridge_contract(root, now=NOW)

            self.assertEqual("BLOCKED", blocked_summary["status"])
            self.assertFalse(list((root / bridge.PENDING_DIR).glob("*.csv")))


if __name__ == "__main__":
    unittest.main()
