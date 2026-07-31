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
        value = broker_snapshot({"cash_yen": 50000, "positions": {"1111.T": {"quantity": 100}}}, datetime(2026, 7, 21, 9))
        self.assertEqual(50000, value["cash"])
        self.assertEqual({"1111.T": 100}, value["positions"])
        self.assertFalse(value["fill_event_audit_available"])

    def test_v2_fill_event_creates_attribute_crosswalk(self):
        fill = {
            "event_id": "economics-1",
            "broker_order_id": "paper-1",
            "client_order_id": "client-1",
            "ticker": "1111.T",
            "side": "BUY",
            "filled_quantity": 100,
            "created_at": "2026-07-21T09:00:00+09:00",
            "event_sha256": "a" * 64,
        }
        previous = broker_snapshot({"positions": {}, "fill_events": []}, datetime(2026, 7, 21, 8))
        current = broker_snapshot({"positions": {}, "fill_events": [fill]}, datetime(2026, 7, 21, 9))

        events = lifecycle_events(previous, current)

        self.assertTrue(current["fill_event_audit_available"])
        self.assertEqual(1, len(events))
        self.assertEqual("broker_fill_event_crosswalk", events[0]["source"])
        self.assertEqual("economics-1", events[0]["economics_event_id"])
        self.assertEqual("1111.T", events[0]["symbol"])
        self.assertEqual(100, events[0]["quantity"])

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

    def test_dry_run_mode_does_not_persist_snapshot_or_journal(self):
        broker = self.root / "state/broker.json"
        snapshot = self.root / "state/snapshot.json"
        journal = self.root / "state/events.jsonl"
        broker.write_text(json.dumps({"positions": {"1111.T": {"quantity": 100}}}), encoding="utf-8")
        snapshot.write_text(json.dumps({"observed_at": "old", "positions": {}}), encoding="utf-8")
        journal.write_text("", encoding="utf-8")
        before = (snapshot.read_bytes(), journal.read_bytes())
        report = run_order_lifecycle(
            self.root,
            self.config,
            datetime(2026, 7, 21, 9),
            persist_state=False,
        )
        self.assertFalse(report["state_persisted"])
        self.assertEqual(before, (snapshot.read_bytes(), journal.read_bytes()))

    def test_corrupt_snapshot_is_not_overwritten(self):
        (self.root / "state/broker.json").write_text(json.dumps({"positions": {}}), encoding="utf-8")
        snapshot = self.root / "state/snapshot.json"
        snapshot.write_text("broken", encoding="utf-8")
        report = run_order_lifecycle(self.root, self.config, datetime(2026, 7, 21, 9))
        self.assertEqual("WARNING", report["status"])
        self.assertFalse(report["state_persisted"])
        self.assertEqual("broken", snapshot.read_text(encoding="utf-8"))

    def test_summary_never_claims_orders_were_submitted(self):
        report = build_summary([], [], True)
        self.assertNotIn("orders_submitted", report)
        self.assertEqual("READY", report["status"])

if __name__ == "__main__": unittest.main()
