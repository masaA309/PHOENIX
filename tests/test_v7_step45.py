from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd

from phoenix_core.data_freshness import JST
from phoenix_core import manual_trade_ticket as ticket


ROOT = Path(__file__).resolve().parent.parent
GENERATED_AT = datetime(2026, 8, 9, 10, 16, 28, tzinfo=JST)
EXPECTED_TICKERS = ["6103.T", "5233.T", "6724.T", "4704.T", "2269.T"]
EXPECTED_QUANTITIES = [0, 0, 0, 0, 0]
EXPECTED_LIMIT_PRICES = [5409.6, 4246.34, 3070.34, 6585.6, 3931.76]
EXPECTED_MAX_LOSSES = [0.0, 0.0, 0.0, 0.0, 0.0]
EXPECTED_PULLBACK_STATES = ["RECHECK_REQUIRED"] * 5
EXPECTED_RECHECK_REQUIRED = [True] * 5


def _position_sizer_reason(selection_reason: str) -> str:
    return selection_reason.split("PositionSizer=", 1)[1].split(" / PHOENIX reason: ", 1)[0]


class Step45ManualTradeTicketTest(unittest.TestCase):
    def test_manual_ticket_is_review_required_with_final_rows_only(self) -> None:
        report = ticket.build_manual_trade_ticket(ROOT, generated_at=GENERATED_AT)

        self.assertEqual("PHOENIX v7 Step46 Manual Ticket", report["version"])
        self.assertEqual("REVIEW_REQUIRED", report["status"])
        self.assertEqual("2026-08-08", report["signal_date"])
        self.assertNotEqual(report["signal_date"], report["generated_at"][:10])
        self.assertTrue(report["manual_approval_required"])
        self.assertFalse(report["rss_send_allowed"])
        self.assertEqual(0, report["orders_submitted"])
        self.assertEqual(report["candidate_count"], len(report["candidates"]))
        self.assertEqual(0, report["approved_count"])
        self.assertEqual(0, report["blocked_count"])
        self.assertEqual(report["candidate_count"], report["review_count"])
        self.assertEqual(["MANUAL_ONLY"], report["blockers"])
        self.assertIsNone(report["selected_ticker"])
        self.assertEqual("BULL", report["market_context"]["regime"])

        totals = report["totals"]
        self.assertEqual(totals["required_funds_yen"], sum(candidate["estimated_notional"] for candidate in report["candidates"]))
        self.assertEqual(totals["estimated_max_loss_yen"], sum(candidate["estimated_max_loss"] for candidate in report["candidates"]))
        self.assertEqual(len(report["candidates"]), totals["positive_quantity_count"])
        self.assertEqual(0, totals["zero_quantity_count"])
        self.assertEqual(100, totals["lot_size"])

        candidates = report["candidates"]
        self.assertTrue(all(candidate["quantity"] > 0 for candidate in candidates))
        self.assertTrue(all(candidate["quantity"] % 100 == 0 for candidate in candidates))
        self.assertTrue(all(candidate["manual_approval_required"] for candidate in candidates))
        self.assertTrue(all(candidate["rss_send_allowed"] is False for candidate in candidates))
        self.assertTrue(all(candidate["client_order_id"].startswith("PHX-MANUAL-") for candidate in candidates))
        self.assertEqual(len(candidates), len({candidate["client_order_id"] for candidate in candidates}))
        self.assertEqual(len(candidates), len({candidate["idempotency_key"] for candidate in candidates}))
        self.assertTrue(all(len(candidate["idempotency_key"]) == 64 for candidate in candidates))
        self.assertTrue(all(len(candidate["checksum"]) == 64 for candidate in candidates))
        self.assertTrue(all(candidate["selection_reason"] for candidate in candidates))

    def test_save_outputs_writes_review_required_artifacts(self) -> None:
        report = ticket.build_manual_trade_ticket(ROOT, generated_at=GENERATED_AT)

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_root = Path(temporary_directory)
            ticket.save_manual_trade_ticket_outputs(output_root, report)

            json_path = output_root / "reports" / "v7_manual_trade_ticket.json"
            csv_path = output_root / "reports" / "v7_manual_trade_ticket.csv"
            text_path = output_root / "reports" / "v7_manual_trade_ticket.txt"

            self.assertTrue(json_path.is_file())
            self.assertTrue(csv_path.is_file())
            self.assertTrue(text_path.is_file())

            saved_report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual("REVIEW_REQUIRED", saved_report["status"])
            self.assertEqual(saved_report["candidate_count"], len(saved_report["candidates"]))
            self.assertEqual(saved_report["candidate_count"], saved_report["totals"]["positive_quantity_count"])
            self.assertEqual(100, saved_report["totals"]["lot_size"])
            self.assertTrue(all(candidate["client_order_id"] for candidate in saved_report["candidates"]))

            frame = pd.read_csv(csv_path, encoding="utf-8-sig")
            self.assertIn("client_order_id", frame.columns)
            self.assertEqual(saved_report["candidate_count"], len(frame))
            self.assertTrue(all(frame["client_order_id"].astype(str).str.startswith("PHX-MANUAL-")))
            self.assertTrue(all(frame["quantity"].astype(int) > 0))

            text = text_path.read_text(encoding="utf-8")
            self.assertIn("PHOENIX v7 STEP46 MANUAL TRADE TICKET", text)
            self.assertIn("Status               : REVIEW_REQUIRED", text)
            self.assertIn("Manual only reason   : MANUAL_ONLY", text)
            self.assertIn("Orders submitted     : 0", text)


if __name__ == "__main__":
    unittest.main()
