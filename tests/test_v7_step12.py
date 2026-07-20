from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from phoenix_core.portfolio_guard import build_portfolio_report, evaluate_position, position_items, run_portfolio_guard


class PortfolioGuardStep12Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "state").mkdir()
        self.config = {"portfolio_guard": {"broker_state": "state/broker.json", "report_json": "reports/guard.json", "report_text": "reports/guard.txt", "default_stop_loss_pct": 0.05, "default_take_profit_pct": 0.10}}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_hold_between_levels(self) -> None:
        item = evaluate_position("1111.T", {"quantity": 100, "average_price": 1000, "current_price": 1030}, 0.05, 0.10)
        self.assertEqual("HOLD", item["action"])
        self.assertEqual(950, item["stop_price"])
        self.assertEqual(1100, item["target_price"])

    def test_stop_level_requests_exit(self) -> None:
        item = evaluate_position("1111.T", {"quantity": 100, "average_price": 1000, "current_price": 940}, 0.05, 0.10)
        self.assertEqual("EXIT", item["action"])

    def test_profit_target_is_detected(self) -> None:
        item = evaluate_position("1111.T", {"quantity": 100, "average_price": 1000, "current_price": 1120}, 0.05, 0.10)
        self.assertEqual("TAKE_PROFIT", item["action"])

    def test_stored_levels_override_defaults(self) -> None:
        item = evaluate_position("1111.T", {"quantity": 100, "average_price": 1000, "current_price": 970, "stop_price": 980, "target_price": 1200}, 0.05, 0.10)
        self.assertEqual("EXIT", item["action"])
        self.assertEqual("stored", item["stop_source"])

    def test_missing_price_requires_review(self) -> None:
        item = evaluate_position("1111.T", {"quantity": 100, "average_price": 1000}, 0.05, 0.10)
        self.assertEqual("REVIEW", item["action"])

    def test_dict_and_list_position_shapes(self) -> None:
        self.assertEqual("1111.T", position_items({"positions": {"1111.T": {"quantity": 100}}})[0][0])
        self.assertEqual("2222.T", position_items({"positions": [{"ticker": "2222.T", "qty": 100}]})[0][0])

    def test_report_never_submits_orders(self) -> None:
        value = build_portfolio_report({"positions": {"1111.T": {"quantity": 100, "average_price": 1000, "current_price": 900}}})
        self.assertEqual("ADVISORY", value["mode"])
        self.assertEqual(0, value["orders_submitted"])
        self.assertEqual(1, value["action_counts"]["EXIT"])

    def test_run_writes_json_and_text(self) -> None:
        (self.root / "state/broker.json").write_text(json.dumps({"positions": {}}), encoding="utf-8")
        value = run_portfolio_guard(self.root, self.config)
        self.assertTrue(Path(value["report_json"]).is_file())
        self.assertTrue(Path(value["report_text"]).is_file())


if __name__ == "__main__":
    unittest.main()
