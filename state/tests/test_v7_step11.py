from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from phoenix_core.decision_diagnostics import build_diagnostics, infer_reason, read_position_log, run_decision_diagnostics


def operations(candidates: int = 20, ready: int = 0) -> dict:
    return {"pipeline": {"candidate_count": candidates, "ready_count": ready, "approved_count": 0, "filled_count": 0}}


class DecisionDiagnosticsStep11Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "reports").mkdir()
        self.config = {"diagnostics": {"position_log": "reports/positions.csv", "report_json": "reports/diagnostics.json", "report_text": "reports/diagnostics.txt"}}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_explicit_reason_has_priority(self) -> None:
        self.assertEqual("MAX_POSITION", infer_reason({"reason": "MAX_POSITION", "quantity": "0"}))

    def test_japanese_production_columns_are_supported(self) -> None:
        row = {"ticker": "1605.T", "判定": "SKIP", "理由": "最低売買単位を購入できません"}
        value = build_diagnostics([row], operations())
        self.assertEqual({"最低売買単位を購入できません": 1}, value["reason_counts"])
        self.assertEqual("1605.T", value["examples"][0]["symbol"])

    def test_existing_position_is_inferred(self) -> None:
        self.assertEqual("EXISTING_POSITION", infer_reason({"existing_position": "true"}))

    def test_insufficient_cash_for_lot_is_inferred(self) -> None:
        self.assertEqual("INSUFFICIENT_CASH_FOR_LOT", infer_reason({"price": "1000", "cash": "50000", "lot_size": "100"}))

    def test_review_when_candidates_have_no_ready_rows(self) -> None:
        value = build_diagnostics([{"symbol": "1234", "reason": "TOO_EXPENSIVE"}], operations())
        self.assertEqual("REVIEW", value["status"])
        self.assertEqual({"TOO_EXPENSIVE": 1}, value["reason_counts"])
        self.assertEqual("1234", value["examples"][0]["symbol"])

    def test_healthy_when_candidate_is_ready(self) -> None:
        value = build_diagnostics([{"symbol": "1234", "status": "ready"}], operations(20, 1))
        self.assertEqual("HEALTHY", value["status"])
        self.assertEqual(1, value["reason_counts"]["READY"])

    def test_utf8_bom_csv_is_supported(self) -> None:
        path = self.root / "reports/positions.csv"
        path.write_text("symbol,reason\n1234,LOT_TOO_LARGE\n", encoding="utf-8-sig")
        rows, warnings = read_position_log(path)
        self.assertEqual([], warnings)
        self.assertEqual("1234", rows[0]["symbol"])

    def test_missing_log_still_creates_safe_report(self) -> None:
        value = run_decision_diagnostics(self.root, self.config, operations())
        self.assertEqual("REVIEW", value["status"])
        self.assertTrue(value["warnings"])
        saved = json.loads((self.root / "reports/diagnostics.json").read_text(encoding="utf-8"))
        self.assertEqual("PHOENIX v7 Step11.1", saved["version"])
        self.assertTrue((self.root / "reports/diagnostics.txt").is_file())


if __name__ == "__main__":
    unittest.main()
