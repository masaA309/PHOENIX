from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from phoenix_core.data_freshness import JST
import phoenix_core.vba_bridge_contract as bridge


ROOT = Path(__file__).resolve().parent.parent
VBA_DIR = ROOT / "vba"


class Step44LocalVbaReceiverTest(unittest.TestCase):
    def test_vba_sources_are_present_and_restricted_to_local_bridge_contract(self) -> None:
        expected_files = [
            "PHOENIX_STEP44_Config.bas",
            "PHOENIX_STEP44_Csv.bas",
            "PHOENIX_STEP44_State.bas",
            "PHOENIX_STEP44_Receiver.bas",
            "ThisWorkbook.cls",
            "STEP44_SETUP.md",
        ]
        for file_name in expected_files:
            self.assertTrue((VBA_DIR / file_name).is_file(), file_name)

        config_text = (VBA_DIR / "PHOENIX_STEP44_Config.bas").read_text(encoding="utf-8")
        csv_text = (VBA_DIR / "PHOENIX_STEP44_Csv.bas").read_text(encoding="utf-8")
        state_text = (VBA_DIR / "PHOENIX_STEP44_State.bas").read_text(encoding="utf-8")
        receiver_text = (VBA_DIR / "PHOENIX_STEP44_Receiver.bas").read_text(encoding="utf-8")
        workbook_text = (VBA_DIR / "ThisWorkbook.cls").read_text(encoding="utf-8")
        setup_text = (VBA_DIR / "STEP44_SETUP.md").read_text(encoding="utf-8")

        for text in (config_text, csv_text, state_text, receiver_text):
            self.assertIn("Attribute VB_Name", text)
            self.assertIn("Option Explicit", text)

        self.assertIn('RunPhoenixStep44LocalReceiver', receiver_text)
        self.assertIn('StartPhoenixStep44ReceiverScheduler', receiver_text)
        self.assertIn('StopPhoenixStep44ReceiverScheduler', receiver_text)
        self.assertIn('Application.OnTime', receiver_text)
        self.assertIn('Schedule:=True', receiver_text)
        self.assertIn('Schedule:=False', receiver_text)
        self.assertIn('rootPath = NormalizeRepositoryStartPath(ThisWorkbook.Path)', receiver_text)
        self.assertIn('rootPath = FindRepositoryRoot(rootPath)', receiver_text)
        self.assertIn('currentStage = "RECONCILE_FINAL"', receiver_text)
        self.assertIn('ReconcileFinalOutboxFiles', receiver_text)
        self.assertIn('ReconcileFinalOutboxFile', receiver_text)
        self.assertIn('currentStage = "RECONCILE_PROCESSING"', receiver_text)
        self.assertIn('ReconcileProcessingOutboxFiles', receiver_text)
        self.assertIn('If Len(rootPath) = 0 Then', receiver_text)
        self.assertIn('shouldReraise = True', receiver_text)
        self.assertIn('Err.Raise errorNumber, errorSource, errorDescription', receiver_text)
        self.assertIn('STEP44_ONEDRIVE_WEB_PREFIX', receiver_text)
        self.assertIn('NormalizeRepositoryStartPath', receiver_text)
        self.assertIn('OneDriveLocalRoot', receiver_text)
        self.assertIn('https://d.docs.live.net/', receiver_text)
        self.assertIn('Unable to map OneDrive web path to a local folder', receiver_text)
        self.assertIn('gStep44SchedulerArmed', receiver_text)
        self.assertIn('gStep44NextRunAt', receiver_text)
        self.assertIn('gStep44NextRunScheduled', receiver_text)
        self.assertIn('gStep44ConsumerRunning', receiver_text)
        self.assertIn('Workbook_Open', workbook_text)
        self.assertIn('Workbook_BeforeClose', workbook_text)
        self.assertIn('StartPhoenixStep44ReceiverScheduler', workbook_text)
        self.assertIn('StopPhoenixStep44ReceiverScheduler', workbook_text)
        self.assertIn('runtime/v7_vba_bridge/outbox/pending', config_text)
        self.assertIn('runtime/v7_vba_bridge/outbox/complete', config_text)
        self.assertIn('runtime/v7_vba_bridge/outbox/rejected', config_text)
        self.assertIn('runtime/v7_vba_bridge/inbox', config_text)
        self.assertIn('state/v7_vba_bridge_step44_state.csv', config_text)
        self.assertIn('reports/v7_vba_bridge_step44_audit.jsonl', config_text)
        self.assertIn('PHOENIX_STEP44_VBA_LOCAL_RECEIVER', config_text)

        self.assertIn('Sha256HexUtf8', csv_text)
        self.assertIn('ParseCsvLine', csv_text)
        self.assertIn('WriteUtf8TextAtomic', csv_text)
        self.assertIn('AppendUtf8TextAtomic', state_text)
        self.assertIn('AcquireStep44Lock', state_text)
        self.assertIn('ReleaseStep44Lock', state_text)
        self.assertIn('MoveFileExW', receiver_text)
        self.assertIn('ADODB.Stream', receiver_text)
        self.assertIn('PROCESSING', receiver_text)
        self.assertIn('DUPLICATE', receiver_text)
        self.assertIn('EXPIRED', receiver_text)
        self.assertIn('CORRUPT', receiver_text)
        self.assertIn('REJECTED', receiver_text)

        forbidden = [
            "OrderSend",
            "SendOrder",
            "BuyMarket",
            "SellMarket",
            "WinHttp",
            "XMLHTTP",
        ]
        for word in forbidden:
            self.assertNotIn(word, config_text + csv_text + state_text + receiver_text)

        self.assertIn("RunPhoenixStep44LocalReceiver", setup_text)
        self.assertIn("state/v7_vba_bridge_step44_state.csv", setup_text)

    def test_step44_receipt_fixture_is_step43_compatible(self) -> None:
        receipt = {
            "schema_version": "1",
            "intent_id": "PHX42-20260805-1301T-BUY-STEP44TEST",
            "idempotency_key": "step44-test-idempotency-key",
            "received_at": datetime(2026, 8, 5, 9, 0, 0, tzinfo=JST).isoformat(timespec="seconds"),
            "result": "ACCEPTED",
            "reason_codes": "",
            "vba_instance_id": "PHOENIX_STEP44_VBA_LOCAL_RECEIVER",
            "source_checksum": "a" * 64,
            "orders_submitted": "0",
        }
        receipt["checksum"] = bridge._checksum_fields(receipt, bridge.RECEIPT_COLUMNS)

        bridge._validate_receipt_row(receipt)

        self.assertEqual("ACCEPTED", receipt["result"])
        self.assertEqual("0", receipt["orders_submitted"])
        self.assertEqual(64, len(receipt["checksum"]))


if __name__ == "__main__":
    unittest.main()
