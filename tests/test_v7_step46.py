from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import pandas as pd

from phoenix_core.data_freshness import JST
from phoenix_core.models import AccountSnapshot, BrokerHealth, Position
from phoenix_core import manual_trade_ticket as ticket


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


def _base_trade_rows() -> list[dict[str, object]]:
    return [
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
        {
            "ticker": "CCC.T",
            "name": "Gamma",
            "decision": "BUY",
            "reference_price": 6200.0,
            "entry_price": 6000.0,
            "stop_price": 5950.0,
            "take_profit_price": 7000.0,
            "ai_score": 80,
            "phoenix_score": 80,
            "market_risk_score": 5,
            "market_risk_level": "WATCH",
        },
        {
            "ticker": "DDD.T",
            "name": "Delta",
            "decision": "BUY",
            "reference_price": 7000.0,
            "entry_price": 7000.0,
            "stop_price": 6950.0,
            "take_profit_price": 8000.0,
            "ai_score": 70,
            "phoenix_score": 70,
            "market_risk_score": 5,
            "market_risk_level": "WATCH",
        },
    ]


def _zero_trade_rows() -> list[dict[str, object]]:
    return [
        {
            "ticker": "ZZZ.T",
            "name": "ZeroOne",
            "decision": "BUY",
            "reference_price": 6200.0,
            "entry_price": 6000.0,
            "stop_price": 5950.0,
            "take_profit_price": 7000.0,
            "ai_score": 50,
            "phoenix_score": 50,
            "market_risk_score": 5,
            "market_risk_level": "WATCH",
        },
        {
            "ticker": "YYY.T",
            "name": "ZeroTwo",
            "decision": "BUY",
            "reference_price": 7200.0,
            "entry_price": 7000.0,
            "stop_price": 6950.0,
            "take_profit_price": 8000.0,
            "ai_score": 45,
            "phoenix_score": 45,
            "market_risk_score": 5,
            "market_risk_level": "WATCH",
        },
    ]


def _write_root(root: Path, trade_rows: list[dict[str, object]]) -> None:
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
    _write_json(root / "state" / "v7_paper_broker.json", {"state_version": 2})


def _position_sizer_reason(selection_reason: str) -> str:
    return selection_reason.split("PositionSizer=", 1)[1].split(" / PHOENIX reason: ", 1)[0]


class FakeBroker:
    broker_name = "PAPER"

    def __init__(self, snapshot: AccountSnapshot) -> None:
        self._snapshot = snapshot
        self.submitted_orders = []

    def health_check(self) -> BrokerHealth:
        return BrokerHealth(
            broker_name=self.broker_name,
            healthy=True,
            live_trading_enabled=False,
            message="synthetic health check",
            checked_at=NOW,
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        return self._snapshot

    def submit_order(self, order) -> None:
        self.submitted_orders.append(order)
        raise AssertionError("submit_order should not be called by Step46")


class Step46ManualTradeTicketTest(unittest.TestCase):
    def test_variable_quantity_and_internal_risk_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_root(root, _base_trade_rows())

            snapshot = AccountSnapshot(
                broker_name="PAPER",
                cash_yen=500000.0,
                positions=(),
                realized_pnl_yen=0.0,
                generated_at=NOW,
            )
            fake_broker = FakeBroker(snapshot)

            with mock.patch.object(ticket, "PaperBroker", return_value=fake_broker), mock.patch.object(
                ticket,
                "size_candidates",
                wraps=ticket.size_candidates,
            ) as size_spy, mock.patch.object(
                ticket,
                "evaluate_orders",
                wraps=ticket.evaluate_orders,
            ) as risk_spy:
                report = ticket.build_manual_trade_ticket(root, generated_at=NOW)

            self.assertTrue(size_spy.called)
            self.assertTrue(risk_spy.called)
            self.assertEqual(4, report["candidate_count"])
            self.assertEqual("REVIEW_REQUIRED", report["status"])
            self.assertEqual("2026-08-08", report["signal_date"])
            self.assertNotEqual(report["signal_date"], report["generated_at"][:10])
            self.assertEqual(["MANUAL_ONLY"], report["blockers"])
            self.assertIsNone(report["selected_ticker"])
            self.assertTrue(report["manual_approval_required"])
            self.assertFalse(report["rss_send_allowed"])
            self.assertEqual(0, report["orders_submitted"])
            self.assertEqual(2, report["totals"]["positive_quantity_count"])
            self.assertEqual(2, report["totals"]["zero_quantity_count"])
            self.assertEqual(200000.0, report["totals"]["required_funds_yen"])
            self.assertEqual(300000.0, report["totals"]["cash_remaining_yen"])
            self.assertEqual(300000.0, report["totals"]["capital_basis_remaining_yen"])
            self.assertEqual(100, report["totals"]["lot_size"])
            self.assertEqual([100, 100, 0, 0], [candidate["quantity"] for candidate in report["candidates"]])
            self.assertTrue(any(candidate["quantity"] >= 100 for candidate in report["candidates"]))
            self.assertTrue(any(candidate["quantity"] == 0 for candidate in report["candidates"]))
            self.assertEqual(
                ["READY", "READY", "SKIP", "SKIP"],
                [candidate["sizing_status"] for candidate in report["candidates"]],
            )
            self.assertEqual(
                ["PULLBACK_WAIT", "POST_TOUCH_RECHECK", "RECHECK_REQUIRED", "RECHECK_REQUIRED"],
                [candidate["pullback_state"] for candidate in report["candidates"]],
            )
            self.assertEqual(
                ["PULLBACK_WAIT", "POST_TOUCH_RECHECK", "RECHECK_REQUIRED", "RECHECK_REQUIRED"],
                [candidate["watch_state"] for candidate in report["candidates"]],
            )
            self.assertEqual([False, True, True, True], [candidate["recheck_required"] for candidate in report["candidates"]])
            self.assertTrue(all(isinstance(candidate["recheck_required"], bool) for candidate in report["candidates"]))
            self.assertEqual(
                ["", "", _position_sizer_reason(report["candidates"][2]["selection_reason"]), _position_sizer_reason(report["candidates"][3]["selection_reason"])],
                [candidate["blocked_reasons"] for candidate in report["candidates"]],
            )
            self.assertTrue(all(candidate["quantity"] % 100 == 0 for candidate in report["candidates"]))
            self.assertEqual([], fake_broker.submitted_orders)

            output_root = root / "output"
            ticket.save_manual_trade_ticket_outputs(output_root, report)

            json_path = output_root / "reports" / "v7_manual_trade_ticket.json"
            csv_path = output_root / "reports" / "v7_manual_trade_ticket.csv"
            text_path = output_root / "reports" / "v7_manual_trade_ticket.txt"

            self.assertTrue(json_path.is_file())
            self.assertTrue(csv_path.is_file())
            self.assertTrue(text_path.is_file())

            saved_report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(4, saved_report["candidate_count"])
            self.assertEqual(200000.0, saved_report["totals"]["required_funds_yen"])
            self.assertEqual([100, 100, 0, 0], [candidate["quantity"] for candidate in saved_report["candidates"]])

            frame = pd.read_csv(csv_path, encoding="utf-8-sig", keep_default_na=False)
            self.assertEqual([100, 100, 0, 0], frame["quantity"].astype(int).tolist())
            self.assertEqual([100, 100, 100, 100], frame["lot_size"].astype(int).tolist())
            self.assertEqual(["TRUE"] * 4, frame["manual_approval_required"].astype(str).str.upper().tolist())
            self.assertEqual(["FALSE"] * 4, frame["rss_send_allowed"].astype(str).str.upper().tolist())
            self.assertEqual(
                ["READY", "READY", "SKIP", "SKIP"],
                frame["sizing_status"].astype(str).tolist(),
            )
            self.assertEqual(
                ["PULLBACK_WAIT", "POST_TOUCH_RECHECK", "RECHECK_REQUIRED", "RECHECK_REQUIRED"],
                frame["watch_state"].astype(str).tolist(),
            )
            self.assertEqual(
                [False, True, True, True],
                [value in (True, "True", "TRUE") for value in frame["recheck_required"].tolist()],
            )
            self.assertTrue(all(candidate == "" for candidate in frame.loc[frame["quantity"].astype(int) > 0, "blocked_reasons"].astype(str)))
            self.assertTrue(all(candidate != "" for candidate in frame.loc[frame["quantity"].astype(int) == 0, "blocked_reasons"].astype(str)))
            text = text_path.read_text(encoding="utf-8")
            self.assertIn("PHOENIX v7 STEP46 MANUAL TRADE TICKET", text)
            self.assertIn("Orders submitted     : 0", text)
            self.assertIn("Required funds total : 200,000.00", text)
            self.assertIn("Residual cash        : 300,000.00", text)
            self.assertIn("Qty / lot            : 100 / 100", text)
            self.assertIn("Qty / lot            : 0 / 100", text)
            self.assertIn("Watch state          : PULLBACK_WAIT", text)
            self.assertIn("Watch state          : POST_TOUCH_RECHECK", text)
            self.assertIn("Recheck required     : False", text)
            self.assertIn("Recheck required     : True", text)

    def test_all_zero_quantities_are_normal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _write_root(root, _zero_trade_rows())

            snapshot = AccountSnapshot(
                broker_name="PAPER",
                cash_yen=500000.0,
                positions=(),
                realized_pnl_yen=0.0,
                generated_at=NOW,
            )
            fake_broker = FakeBroker(snapshot)

            with mock.patch.object(ticket, "PaperBroker", return_value=fake_broker):
                report = ticket.build_manual_trade_ticket(root, generated_at=NOW)

            self.assertEqual(2, report["candidate_count"])
            self.assertEqual("2026-08-08", report["signal_date"])
            self.assertNotEqual(report["signal_date"], report["generated_at"][:10])
            self.assertEqual([0, 0], [candidate["quantity"] for candidate in report["candidates"]])
            self.assertEqual(0, report["totals"]["positive_quantity_count"])
            self.assertEqual(2, report["totals"]["zero_quantity_count"])
            self.assertEqual(0.0, report["totals"]["required_funds_yen"])
            self.assertEqual(500000.0, report["totals"]["cash_remaining_yen"])
            self.assertEqual(500000.0, report["totals"]["capital_basis_remaining_yen"])
            self.assertEqual(100, report["totals"]["lot_size"])
            self.assertEqual([100, 100], [candidate["lot_size"] for candidate in report["candidates"]])
            self.assertEqual(["SKIP", "SKIP"], [candidate["sizing_status"] for candidate in report["candidates"]])
            self.assertEqual(["RECHECK_REQUIRED", "RECHECK_REQUIRED"], [candidate["pullback_state"] for candidate in report["candidates"]])
            self.assertEqual(["RECHECK_REQUIRED", "RECHECK_REQUIRED"], [candidate["watch_state"] for candidate in report["candidates"]])
            self.assertEqual([True, True], [candidate["recheck_required"] for candidate in report["candidates"]])
            self.assertEqual(
                [
                    _position_sizer_reason(report["candidates"][0]["selection_reason"]),
                    _position_sizer_reason(report["candidates"][1]["selection_reason"]),
                ],
                [candidate["blocked_reasons"] for candidate in report["candidates"]],
            )
            self.assertEqual("REVIEW_REQUIRED", report["status"])
            self.assertEqual(["MANUAL_ONLY"], report["blockers"])
            self.assertIsNone(report["selected_ticker"])
            self.assertTrue(report["manual_approval_required"])
            self.assertFalse(report["rss_send_allowed"])
            self.assertEqual(0, report["orders_submitted"])
            self.assertEqual([], fake_broker.submitted_orders)


if __name__ == "__main__":
    unittest.main()
