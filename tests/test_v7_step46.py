from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from phoenix_core import manual_trade_ticket as ticket
from phoenix_core import order_lifecycle
from phoenix_core.data_freshness import JST


NOW = datetime(2026, 8, 9, 10, 16, 28, tzinfo=JST)


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_root(
    root: Path,
    trade_rows: list[dict[str, object]],
    *,
    processed_client_order_ids: list[str] | None = None,
) -> None:
    _write_csv(
        root / "reports" / "trade_signals.csv",
        [
            "ticker",
            "name",
            "decision",
            "reference_price",
            "entry_price",
            "stop_price",
            "take_profit_price",
            "ai_score",
            "phoenix_score",
            "market_risk_score",
            "market_risk_level",
        ],
        trade_rows,
    )
    _write_csv(
        root / "reports" / "ai_judgement.csv",
        [
            "ticker",
            "ai_decision",
            "ai_score",
            "phoenix_score",
            "phoenix_reason",
        ],
        [
            {
                "ticker": row["ticker"],
                "ai_decision": "買い候補",
                "ai_score": row["ai_score"],
                "phoenix_score": row["phoenix_score"],
                "phoenix_reason": f"{row['ticker']} synthetic reason",
            }
            for row in trade_rows
        ],
    )
    _write_csv(
        root / "reports" / "report_20260807.csv",
        ["signal_date"],
        [{"signal_date": "2026-08-08"}],
    )
    _write_json(
        root / "reports" / "ai_judgement_manifest.json",
        {"schema_version": 1, "generated_at": "2026-08-08T09:00:00+09:00"},
    )
    _write_json(
        root / "reports" / "market_regime.json",
        {
            "regime": "BULL",
            "confidence": 99.0,
            "score": 73.8,
            "strategy": "AGGRESSIVE",
            "settings": {
                "capital_usage_percent": 100.0,
                "max_positions": 5,
                "risk_per_trade_multiplier": 1.1,
                "stop_multiplier": 1.1,
                "target_multiplier": 1.2,
            },
        },
    )
    _write_json(
        root / "data" / "market_risk_latest.json",
        {"total_score": 17, "risk_level": "WATCH"},
    )
    _write_json(
        root / "config" / "v7_position_sizer_config.json",
        {
            "position_sizing": {
                "risk_per_trade_pct": 0.01,
                "max_position_pct": 0.30,
                "max_total_invested_pct": 0.80,
                "minimum_cash_reserve_pct": 0.10,
                "fallback_stop_distance_pct": 0.03,
                "lot_size": 100,
                "maximum_quantity_per_ticker": 1000,
                "allow_pyramiding": False,
                "commission_buffer_pct": 0.001,
            }
        },
    )
    _write_json(
        root / "state" / "v7_paper_broker.json",
        {
            "state_version": 1,
            "cash_yen": 500000.0,
            "realized_pnl_yen": 0.0,
            "positions": {},
            "processed_client_order_ids": processed_client_order_ids or [],
            "fill_events": [],
        },
    )


def _lifecycle_config() -> dict[str, object]:
    return {
        "order_lifecycle": {
            "broker_state": "state/v7_paper_broker.json",
            "snapshot_state": "state/v7_order_lifecycle_snapshot.json",
            "event_journal": "state/v7_order_lifecycle_events.jsonl",
            "report_json": "reports/v7_order_lifecycle.json",
            "report_text": "reports/v7_order_lifecycle.txt",
            "retention_events": 100,
        }
    }


class Step46ManualTradeTicketTest(unittest.TestCase):
    def test_final_ticket_filters_bad_rows_and_keeps_client_order_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_root(
                root,
                [
                    {
                        "ticker": "AAA.T",
                        "name": "Alpha",
                        "decision": "BUY",
                        "reference_price": 1020.0,
                        "entry_price": 1000.0,
                        "stop_price": 950.0,
                        "take_profit_price": 1120.0,
                        "ai_score": 99,
                        "phoenix_score": 99,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    },
                    {
                        "ticker": "ZERO.T",
                        "name": "Zero",
                        "decision": "BUY",
                        "reference_price": 1020.0,
                        "entry_price": 0.0,
                        "stop_price": 950.0,
                        "take_profit_price": 1120.0,
                        "ai_score": 50,
                        "phoenix_score": 50,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    },
                    {
                        "ticker": "BAD.T",
                        "name": "Bad",
                        "decision": "BUY",
                        "reference_price": 1020.0,
                        "entry_price": 1000.0,
                        "stop_price": 1005.0,
                        "take_profit_price": 1120.0,
                        "ai_score": 60,
                        "phoenix_score": 60,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    },
                    {
                        "ticker": "RISK.T",
                        "name": "Risk",
                        "decision": "BUY",
                        "reference_price": 610000.0,
                        "entry_price": 600000.0,
                        "stop_price": 590000.0,
                        "take_profit_price": 700000.0,
                        "ai_score": 70,
                        "phoenix_score": 70,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    },
                ],
            )

            report = ticket.build_manual_trade_ticket(root, generated_at=NOW)

            self.assertEqual("REVIEW_REQUIRED", report["status"])
            self.assertEqual(1, report["candidate_count"])
            self.assertEqual(1, report["review_count"])
            self.assertEqual(1, report["totals"]["positive_quantity_count"])
            self.assertEqual(0, report["totals"]["zero_quantity_count"])
            self.assertEqual("2026-08-08", report["signal_date"])
            self.assertNotEqual(report["signal_date"], report["generated_at"][:10])
            self.assertEqual(["MANUAL_ONLY"], report["blockers"])
            self.assertIsNone(report["selected_ticker"])
            self.assertTrue(report["manual_approval_required"])
            self.assertFalse(report["rss_send_allowed"])
            self.assertEqual(0, report["orders_submitted"])

            candidate = report["candidates"][0]
            self.assertEqual("AAA.T", candidate["ticker"])
            self.assertTrue(candidate["quantity"] > 0)
            self.assertEqual(
                ticket._manual_ticket_client_order_id("2026-08-08", "AAA.T", "BUY"),
                candidate["client_order_id"],
            )
            self.assertEqual(64, len(candidate["idempotency_key"]))
            self.assertEqual(64, len(candidate["checksum"]))
            self.assertTrue(candidate["manual_approval_required"])
            self.assertFalse(candidate["rss_send_allowed"])
            self.assertTrue(candidate["client_order_id"].startswith("PHX-MANUAL-"))

    def test_stale_signal_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_root(
                root,
                [
                    {
                        "ticker": "AAA.T",
                        "name": "Alpha",
                        "decision": "BUY",
                        "reference_price": 1020.0,
                        "entry_price": 1000.0,
                        "stop_price": 950.0,
                        "take_profit_price": 1120.0,
                        "ai_score": 99,
                        "phoenix_score": 99,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    }
                ],
            )
            report = ticket.build_manual_trade_ticket(
                root,
                generated_at=datetime(2026, 8, 12, 10, 16, 28, tzinfo=JST),
            )

            self.assertEqual(0, report["candidate_count"])
            self.assertEqual([], report["candidates"])
            self.assertEqual(0, report["totals"]["positive_quantity_count"])
            self.assertEqual(0, report["totals"]["required_funds_yen"])
            self.assertEqual(0, report["totals"]["zero_quantity_count"])
            self.assertEqual("2026-08-08", report["signal_date"])

    def test_manual_ticket_rebuild_is_suppressed_by_saved_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            processed_id = ticket._manual_ticket_client_order_id("2026-08-08", "AAA.T", "BUY")
            _write_root(
                root,
                [
                    {
                        "ticker": "AAA.T",
                        "name": "Alpha",
                        "decision": "BUY",
                        "reference_price": 1020.0,
                        "entry_price": 1000.0,
                        "stop_price": 950.0,
                        "take_profit_price": 1120.0,
                        "ai_score": 99,
                        "phoenix_score": 99,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    },
                    {
                        "ticker": "BBB.T",
                        "name": "Beta",
                        "decision": "BUY",
                        "reference_price": 980.0,
                        "entry_price": 1000.0,
                        "stop_price": 950.0,
                        "take_profit_price": 1120.0,
                        "ai_score": 98,
                        "phoenix_score": 98,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    },
                ],
                processed_client_order_ids=[processed_id],
            )
            report = ticket.build_manual_trade_ticket(root, generated_at=NOW)
            self.assertEqual(1, report["candidate_count"])
            self.assertEqual(["BBB.T"], [candidate["ticker"] for candidate in report["candidates"]])
            ticket.save_manual_trade_ticket_outputs(root, report)
            rebuilt = ticket.build_manual_trade_ticket(root, generated_at=NOW)
            self.assertEqual(0, rebuilt["candidate_count"])
            self.assertEqual([], rebuilt["candidates"])

    def test_manual_fill_ingest_updates_lifecycle_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_root(
                root,
                [
                    {
                        "ticker": "AAA.T",
                        "name": "Alpha",
                        "decision": "BUY",
                        "reference_price": 1020.0,
                        "entry_price": 1000.0,
                        "stop_price": 950.0,
                        "take_profit_price": 1120.0,
                        "ai_score": 99,
                        "phoenix_score": 99,
                        "market_risk_score": 5,
                        "market_risk_level": "WATCH",
                    }
                ],
            )
            report = ticket.build_manual_trade_ticket(root, generated_at=NOW)
            ticket.save_manual_trade_ticket_outputs(root, report)
            candidate = report["candidates"][0]
            baseline = order_lifecycle.run_order_lifecycle(root, _lifecycle_config(), NOW)
            self.assertTrue(baseline["baseline_created"])

            _write_csv(
                root / "state" / "v7_manual_fill_inbox.csv",
                ["client_order_id", "actual_fill_price", "actual_fill_quantity", "filled_at"],
                [
                    {
                        "client_order_id": candidate["client_order_id"],
                        "actual_fill_price": candidate["limit_price"],
                        "actual_fill_quantity": candidate["quantity"],
                        "filled_at": "2026-08-09T11:00:00+09:00",
                    }
                ],
            )
            ingest_report = order_lifecycle.ingest_manual_fills(root, _lifecycle_config(), NOW)
            self.assertIsNotNone(ingest_report)
            self.assertEqual(1, ingest_report["ingested_count"])
            self.assertEqual("2026-08-09T11:00:00+09:00", ingest_report["fills"][0]["filled_at"])
            self.assertFalse((root / "state" / "v7_manual_fill_inbox.csv").exists())

            lifecycle_report = order_lifecycle.run_order_lifecycle(root, _lifecycle_config(), NOW)
            self.assertEqual(1, lifecycle_report["new_event_count"])
            self.assertEqual(1, lifecycle_report["audited_fill_count"])
            self.assertEqual(candidate["client_order_id"], lifecycle_report["audited_fill_crosswalk"][0]["client_order_id"])


if __name__ == "__main__":
    unittest.main()
