from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import unittest

from phoenix_core.market_data_guard import build_report, file_health, next_guard_state, position_prices, run_market_data_guard


class MarketDataGuardStep13Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "reports").mkdir()
        (self.root / "state").mkdir()
        self.now = datetime(2026, 7, 20, 9, 0, 0)
        self.config = {"market_data_guard": {"signals_file": "reports/signals.csv", "broker_state": "state/broker.json", "guard_state": "state/guard.json", "report_json": "reports/guard.json", "report_text": "reports/guard.txt", "max_age_hours": 96, "unchanged_warning_days": 2}}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def touch_at_now(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")
        stamp = self.now.timestamp()
        os.utime(path, (stamp, stamp))

    def test_recent_file_is_ready(self) -> None:
        path = self.root / "reports/signals.csv"
        self.touch_at_now(path, "ticker,price\n1111.T,1000\n")
        self.assertEqual("READY", file_health(path, self.now, 96)["status"])

    def test_missing_file_fails(self) -> None:
        self.assertEqual("FAILED", file_health(self.root / "missing.csv", self.now, 96)["status"])

    def test_stale_file_warns(self) -> None:
        path = self.root / "reports/signals.csv"
        path.write_text("data", encoding="utf-8")
        old = datetime(2026, 7, 10).timestamp()
        os.utime(path, (old, old))
        self.assertEqual("WARNING", file_health(path, self.now, 96)["status"])

    def test_position_prices_support_market_price(self) -> None:
        prices, warnings = position_prices({"positions": {"1111.T": {"market_price": 123.4}}})
        self.assertEqual({"1111.T": 123.4}, prices)
        self.assertEqual([], warnings)

    def test_missing_position_price_fails_report(self) -> None:
        report = build_report({}, {}, ["Missing current price: 1111.T"], 0, 2, self.now)
        self.assertEqual("FAILED", report["status"])
        self.assertEqual(0, report["orders_submitted"])

    def test_unchanged_counter_only_advances_on_new_date(self) -> None:
        previous = {"last_observed_date": "2026-07-19", "fingerprint": "abc", "unchanged_days": 0}
        value = next_guard_state(previous, "abc", self.now)
        self.assertEqual(1, value["unchanged_days"])
        same_day = next_guard_state(value, "abc", self.now)
        self.assertEqual(1, same_day["unchanged_days"])

    def test_unchanged_threshold_warns(self) -> None:
        report = build_report({}, {"1111.T": 100}, [], 2, 2, self.now)
        self.assertEqual("WARNING", report["status"])

    def test_run_writes_reports_and_state(self) -> None:
        self.touch_at_now(self.root / "reports/signals.csv", "ticker,price\n1111.T,1000\n")
        self.touch_at_now(self.root / "state/broker.json", json.dumps({"positions": {"1111.T": {"market_price": 1000}}}))
        report = run_market_data_guard(self.root, self.config, self.now)
        self.assertEqual("READY", report["status"])
        self.assertTrue((self.root / "state/guard.json").is_file())
        self.assertTrue((self.root / "reports/guard.txt").is_file())


if __name__ == "__main__":
    unittest.main()
