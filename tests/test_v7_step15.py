from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from phoenix_core.order_lifecycle import broker_snapshot, build_summary, lifecycle_events, merge_events, run_order_lifecycle


class OrderLifecycleStep15Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "state").mkdir()
        self.config = {"order_lifecycle": {"broker_state": "state/broker.json", "snapshot_state": "state/snapshot.json", "event_journal": "state/events.jsonl", "report_json": "reports/lifecycle.json", "report_text": "reports/lifecycle.txt", "retention_events": 100}}

    def tearDown(self): self.temp.cleanup()

    def test_snapshot_extracts_positions_and_cash(self):
        value = broker_snapshot({"cash": 50000, "positions": {"1111.T": {"quantity": 100}}}, datetime(2026, 7, 21, 9))
        self.assertEqual(50000, value["cash"])
        self.assertEqual({"1111.T": 100}, value["positions"])

    def test_buy_delta_creates_event(self):
        events = lifecycle_events({"positions": {}}, {"observed_at": "x", "positions": {"1111.T": 100}})
        self.assertEqual("BUY", events[0]["side"])
        self.assertEqual(100, events[0]["quantity"])

    def test_sell_delta_creates_event(self):
        events = lifecycle_events({"positions": {"1111.T": 100}}, {"observed_at": "x", "positions": {"1111.T": 40}})
        self.assertEqual("SELL", events[0]["side"])
        self.assertEqual(60, events[0]["quantity"])

    def test_unchanged_position_creates_no_event(self):
        self.assertEqual([], lifecycle_events({"positions": {"1111.T": 100}}, {"observed_at": "x", "positions": {"1111.T": 100}}))

    def test_duplicate_event_is_not_merged_twice(self):
        event = lifecycle_events({"positions": {}}, {"observed_at": "x", "positions": {"1111.T": 100}})[0]
        self.assertEqual(1, len(merge_events([event], [event], 100)))

    def test_baseline_does_not_count_existing_positions(self):
        (self.root / "state/broker.json").write_text(json.dumps({"positions": {"1111.T": {"quantity": 100}}}), encoding="utf-8")
        report = run_order_lifecycle(self.root, self.config, datetime(2026, 7, 21, 9))
        self.assertTrue(report["baseline_created"])
        self.assertEqual(0, report["audited_fill_count"])

    def test_second_run_detects_new_position(self):
        broker = self.root / "state/broker.json"
        broker.write_text(json.dumps({"positions": {"1111.T": {"quantity": 100}}}), encoding="utf-8")
        run_order_lifecycle(self.root, self.config, datetime(2026, 7, 21, 9))
        broker.write_text(json.dumps({"positions": {"1111.T": {"quantity": 100}, "2222.T": {"quantity": 100}}}), encoding="utf-8")
        report = run_order_lifecycle(self.root, self.config, datetime(2026, 7, 22, 9))
        self.assertEqual(1, report["new_event_count"])
        self.assertEqual(1, report["audited_fill_count"])

    def test_summary_never_claims_orders_were_submitted(self):
        report = build_summary([], [], True)
        self.assertNotIn("orders_submitted", report)
        self.assertEqual("READY", report["status"])

if __name__ == "__main__": unittest.main()
