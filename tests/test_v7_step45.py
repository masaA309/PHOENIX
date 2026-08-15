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
    def test_manual_ticket_is_review_required_with_variable_share_drafts(self) -> None:
        report = ticket.build_manual_trade_ticket(ROOT, generated_at=GENERATED_AT)

        self.assertEqual("PHOENIX v7 Step46 Manual Ticket Draft", report["version"])
        self.assertEqual("REVIEW_REQUIRED", report["status"])
        self.assertEqual("2026-08-08", report["signal_date"])
        self.assertNotEqual(report["signal_date"], report["generated_at"][:10])
        self.assertTrue(report["manual_approval_required"])
        self.assertFalse(report["rss_send_allowed"])
        self.assertEqual(0, report["orders_submitted"])
        self.assertEqual(5, report["candidate_count"])
        self.assertEqual(0, report["approved_count"])
        self.assertEqual(0, report["blocked_count"])
        self.assertEqual(5, report["review_count"])
        self.assertEqual(["MANUAL_ONLY"], report["blockers"])
        self.assertIsNone(report["selected_ticker"])
        self.assertEqual("BULL", report["market_context"]["regime"])
        self.assertEqual("WATCH", report["market_context"]["market_risk_level"])

        totals = report["totals"]
        self.assertEqual(0.0, totals["required_funds_yen"])
        self.assertEqual(0.0, totals["estimated_max_loss_yen"])
        self.assertEqual(0, totals["positive_quantity_count"])
        self.assertEqual(5, totals["zero_quantity_count"])
        self.assertEqual(500000.0, totals["cash_remaining_yen"])
        self.assertEqual(500000.0, totals["capital_basis_remaining_yen"])
        self.assertEqual(100, totals["lot_size"])

        candidates = report["candidates"]
        self.assertEqual(EXPECTED_TICKERS, [candidate["ticker"] for candidate in candidates])
        self.assertEqual(EXPECTED_QUANTITIES, [candidate["quantity"] for candidate in candidates])
        self.assertEqual([100, 100, 100, 100, 100], [candidate["lot_size"] for candidate in candidates])
        self.assertEqual(EXPECTED_LIMIT_PRICES, [candidate["limit_price"] for candidate in candidates])
        self.assertEqual(EXPECTED_MAX_LOSSES, [candidate["estimated_max_loss"] for candidate in candidates])
        self.assertEqual(EXPECTED_PULLBACK_STATES, [candidate["pullback_state"] for candidate in candidates])
        self.assertEqual(EXPECTED_PULLBACK_STATES, [candidate["watch_state"] for candidate in candidates])
        self.assertEqual(EXPECTED_RECHECK_REQUIRED, [candidate["recheck_required"] for candidate in candidates])
        self.assertTrue(all(isinstance(candidate["recheck_required"], bool) for candidate in candidates))
        self.assertEqual(
            [_position_sizer_reason(candidate["selection_reason"]) for candidate in candidates],
            [candidate["blocked_reasons"] for candidate in candidates],
        )
        self.assertEqual([0, 0, 0, 0, 0], [candidate["orders_submitted"] for candidate in candidates])
        self.assertEqual(["MANUAL_ONLY"] * 5, [candidate["risk_check_result"] for candidate in candidates])
        self.assertEqual(["SKIP"] * 5, [candidate["sizing_status"] for candidate in candidates])
        self.assertTrue(all(candidate["manual_approval_required"] for candidate in candidates))
        self.assertTrue(all(candidate["rss_send_allowed"] is False for candidate in candidates))
        self.assertTrue(all(candidate["quantity"] >= 0 for candidate in candidates))
        self.assertTrue(all(candidate["quantity"] % 100 == 0 for candidate in candidates))

        self.assertIn("Trade判定=BUY", candidates[0]["selection_reason"])
        self.assertIn("PositionSizer=", candidates[2]["selection_reason"])
        self.assertIn("PHOENIX reason:", candidates[2]["selection_reason"])
        self.assertEqual(64, len(candidates[2]["idempotency_key"]))
        self.assertEqual(64, len(candidates[2]["checksum"]))

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
            self.assertEqual(5, saved_report["candidate_count"])
            self.assertEqual(0.0, saved_report["totals"]["required_funds_yen"])
            self.assertEqual(0, saved_report["totals"]["positive_quantity_count"])
            self.assertEqual(100, saved_report["totals"]["lot_size"])
            self.assertEqual(EXPECTED_TICKERS, [candidate["ticker"] for candidate in saved_report["candidates"]])
            self.assertEqual(EXPECTED_QUANTITIES, [candidate["quantity"] for candidate in saved_report["candidates"]])

            frame = pd.read_csv(csv_path, encoding="utf-8-sig")
            self.assertEqual(EXPECTED_TICKERS, frame["ticker"].astype(str).tolist())
            self.assertEqual(EXPECTED_QUANTITIES, frame["quantity"].astype(int).tolist())
            self.assertEqual([100, 100, 100, 100, 100], frame["lot_size"].astype(int).tolist())
            self.assertEqual(["TRUE"] * 5, frame["manual_approval_required"].astype(str).str.upper().tolist())
            self.assertEqual(["FALSE"] * 5, frame["rss_send_allowed"].astype(str).str.upper().tolist())
            self.assertEqual(["MANUAL_ONLY"] * 5, frame["risk_check_result"].astype(str).tolist())
            self.assertEqual(EXPECTED_PULLBACK_STATES, frame["pullback_state"].astype(str).tolist())
            self.assertEqual(EXPECTED_PULLBACK_STATES, frame["watch_state"].astype(str).tolist())
            self.assertEqual(EXPECTED_RECHECK_REQUIRED, [value in (True, "True", "TRUE") for value in frame["recheck_required"].tolist()])
            self.assertTrue(all(candidate == "" for candidate in frame.loc[frame["quantity"].astype(int) > 0, "blocked_reasons"].astype(str)))
            self.assertTrue(all(candidate != "" for candidate in frame.loc[frame["quantity"].astype(int) == 0, "blocked_reasons"].astype(str)))

            text = text_path.read_text(encoding="utf-8")
            self.assertIn("PHOENIX v7 STEP46 MANUAL TRADE TICKET", text)
            self.assertIn("Status               : REVIEW_REQUIRED", text)
            self.assertIn("Manual only reason   : MANUAL_ONLY", text)
            self.assertIn("Orders submitted     : 0", text)
            self.assertIn("Required funds total : 0.00", text)
            self.assertIn("Residual cash        : 500,000.00", text)
            self.assertIn("Residual basis       : 500,000.00", text)
            self.assertIn("Qty / lot            : 0 / 100", text)
            self.assertIn("Watch state          : RECHECK_REQUIRED", text)
            self.assertIn("Recheck required     : True", text)
            self.assertIn("Blocked reasons      :", text)


if __name__ == "__main__":
    unittest.main()
