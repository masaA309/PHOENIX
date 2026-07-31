from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import pandas as pd

if "dotenv" not in sys.modules:
    sys.modules["dotenv"] = types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: False)

import notify
import report as daily_report_writer
from phoenix_core.data_freshness import (
    EXPECTED_NIKKEI225_COUNT,
    JPX_CALENDAR_SHA256,
    JST,
    latest_completed_jpx_trading_date,
    ticker_universe_sha256,
    verify_market_dates,
)
from scanner import (
    completed_session_ticker_data,
    load_stock_list,
    ticker_data_is_fresh,
)


class MarketDataFreshnessTest(unittest.TestCase):
    def test_stock_universe_requires_exactly_225_unique_valid_tickers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_file = Path(temp_dir) / "nikkei225.csv"
            valid = pd.DataFrame({
                "name": [f"stock-{index}" for index in range(EXPECTED_NIKKEI225_COUNT)],
                "ticker": [f"{1000 + index}.T" for index in range(EXPECTED_NIKKEI225_COUNT)],
            })
            valid.to_csv(csv_file, index=False)
            self.assertEqual(EXPECTED_NIKKEI225_COUNT, len(load_stock_list(csv_file)))

            valid.iloc[:-1].to_csv(csv_file, index=False)
            with self.assertRaisesRegex(ValueError, "224/225"):
                load_stock_list(csv_file)

            duplicate = valid.copy()
            duplicate.loc[duplicate.index[-1], "ticker"] = duplicate.loc[0, "ticker"]
            duplicate.to_csv(csv_file, index=False)
            with self.assertRaisesRegex(ValueError, "ticker重複"):
                load_stock_list(csv_file)

            invalid = valid.copy()
            invalid.loc[invalid.index[-1], "ticker"] = "INVALID"
            invalid.to_csv(csv_file, index=False)
            with self.assertRaisesRegex(ValueError, "無効なticker"):
                load_stock_list(csv_file)

    def _write_notification_source(
        self,
        report_dir: Path,
        *,
        as_of: datetime,
        market_date: str,
    ) -> Path:
        report_file = report_dir / f"report_{as_of:%Y%m%d}.csv"
        tickers = [f"{1000 + index}.T" for index in range(EXPECTED_NIKKEI225_COUNT)]
        source = pd.DataFrame({
            "ticker": tickers,
            "基準日": [market_date] * EXPECTED_NIKKEI225_COUNT,
        })
        source.to_csv(report_file, index=False)
        evidence = verify_market_dates([market_date], as_of=as_of)
        manifest = {
            "schema_version": 1,
            "run_id": as_of.strftime("%Y%m%dT%H%M%S%f%z"),
            "generated_at": as_of.isoformat(),
            "report_file": report_file.name,
            "report_sha256": sha256(report_file.read_bytes()).hexdigest(),
            "ticker_count": EXPECTED_NIKKEI225_COUNT,
            "expected_ticker_count": EXPECTED_NIKKEI225_COUNT,
            "ticker_universe_sha256": ticker_universe_sha256(tickers),
            "market_data_evidence": evidence,
        }
        (report_dir / notify.NOTIFICATION_SOURCE_MANIFEST_NAME).write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return report_file

    def test_latest_completed_session_honors_close_weekend_and_jpx_holiday(self) -> None:
        self.assertEqual(
            "2026-07-22",
            latest_completed_jpx_trading_date(
                datetime(2026, 7, 23, 8, 0, tzinfo=JST)
            ).isoformat(),
        )
        self.assertEqual(
            "2026-07-17",
            latest_completed_jpx_trading_date(
                datetime(2026, 7, 21, 8, 0, tzinfo=JST)
            ).isoformat(),
        )
        self.assertEqual(
            "2026-07-21",
            latest_completed_jpx_trading_date(
                datetime(2026, 7, 21, 16, 0, tzinfo=JST)
            ).isoformat(),
        )

    def test_only_exact_latest_completed_jpx_session_is_ready(self) -> None:
        as_of = datetime(2026, 7, 23, 8, 0, tzinfo=JST)
        ready = verify_market_dates(["2026-07-22", "2026-07-22"], as_of=as_of)
        self.assertEqual("READY", ready["status"])
        self.assertEqual("2026-07-22", ready["expected_date"])
        self.assertEqual(JPX_CALENDAR_SHA256, ready["calendar_sha256"])

        stale = verify_market_dates(["2026-07-21"], as_of=as_of)
        self.assertEqual("NOT_READY", stale["status"])
        self.assertIn("latest completed JPX session", stale["blocking_reasons"][0])

    def test_missing_invalid_future_and_uncovered_dates_fail_closed(self) -> None:
        as_of = datetime(2026, 7, 23, 8, 0, tzinfo=JST)
        self.assertEqual("NOT_READY", verify_market_dates([], as_of=as_of)["status"])
        with self.assertRaises(ValueError):
            verify_market_dates(["not-a-date"], as_of=as_of)
        self.assertEqual(
            "NOT_READY",
            verify_market_dates(["2026-07-24"], as_of=as_of)["status"],
        )
        uncovered = verify_market_dates(
            ["2099-07-22"],
            as_of=datetime(2099, 7, 23, 8, 0, tzinfo=JST),
        )
        self.assertEqual("NOT_READY", uncovered["status"])
        self.assertIn("does not cover", uncovered["blocking_reasons"][0])

    def test_scanner_checks_exact_market_row_not_cache_save_time(self) -> None:
        as_of = datetime(2026, 7, 23, 8, 0, tzinfo=JST)
        fresh = pd.DataFrame(
            {"Close": [100.0], "Volume": [1000]},
            index=pd.DatetimeIndex(["2026-07-22"]),
        )
        stale = pd.DataFrame(
            {"Close": [100.0], "Volume": [1000]},
            index=pd.DatetimeIndex(["2026-07-21"]),
        )
        self.assertTrue(ticker_data_is_fresh(fresh, as_of=as_of))
        self.assertFalse(ticker_data_is_fresh(stale, as_of=as_of))

    def test_scanner_excludes_intraday_partial_daily_bar(self) -> None:
        as_of = datetime(2026, 7, 23, 9, 31, tzinfo=JST)
        history = pd.DataFrame(
            {"Close": [100.0, 101.0], "Volume": [1000, 100]},
            index=pd.DatetimeIndex(["2026-07-22", "2026-07-23"]),
        )

        completed = completed_session_ticker_data(history, as_of=as_of)

        self.assertEqual([pd.Timestamp("2026-07-22")], list(completed.index))
        self.assertTrue(ticker_data_is_fresh(history, as_of=as_of))

    def test_scanner_keeps_current_daily_bar_only_after_market_close(self) -> None:
        as_of = datetime(2026, 7, 23, 16, 0, tzinfo=JST)
        history = pd.DataFrame(
            {"Close": [100.0, 101.0], "Volume": [1000, 2000]},
            index=pd.DatetimeIndex(["2026-07-22", "2026-07-23"]),
        )

        completed = completed_session_ticker_data(history, as_of=as_of)

        self.assertEqual(pd.Timestamp("2026-07-23"), completed.index.max())

    def test_scanner_rejects_missing_completed_session_and_future_rows(self) -> None:
        as_of = datetime(2026, 7, 23, 9, 31, tzinfo=JST)
        stale = pd.DataFrame(
            {"Close": [100.0], "Volume": [1000]},
            index=pd.DatetimeIndex(["2026-07-21"]),
        )
        future = pd.DataFrame(
            {"Close": [100.0, 101.0], "Volume": [1000, 2000]},
            index=pd.DatetimeIndex(["2026-07-22", "2026-07-24"]),
        )

        self.assertTrue(completed_session_ticker_data(stale, as_of=as_of).empty)
        self.assertTrue(completed_session_ticker_data(future, as_of=as_of).empty)

    def test_daily_report_rejects_partial_nikkei_universe(self) -> None:
        partial = pd.DataFrame({
            "ticker": ["1000.T"],
            "基準日": [latest_completed_jpx_trading_date().isoformat()],
            "PHOENIX_SCORE": [50],
            "出来高倍率": [1.0],
            "前日比%": [0.0],
        })
        with self.assertRaisesRegex(ValueError, "ユニバースが不完全"):
            daily_report_writer.save_reports(partial)

    def test_notifier_rejects_same_day_manifest_with_nonlatest_market_date(self) -> None:
        as_of = datetime(2026, 7, 23, 8, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            self._write_notification_source(
                report_dir,
                as_of=as_of,
                market_date="2026-07-21",
            )
            with patch.object(notify, "REPORT_DIR", report_dir):
                with self.assertRaisesRegex(ValueError, "Stale market data"):
                    notify._load_notification_source_dates(as_of=as_of)

    def test_notifier_rejects_report_tampering_and_old_manifest(self) -> None:
        as_of = datetime(2026, 7, 23, 8, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            report_file = self._write_notification_source(
                report_dir,
                as_of=as_of,
                market_date="2026-07-22",
            )
            report_file.write_text("ticker,基準日\n9999.T,2026-07-22\n", encoding="utf-8")
            with patch.object(notify, "REPORT_DIR", report_dir):
                with self.assertRaisesRegex(ValueError, "hash"):
                    notify._load_notification_source_dates(as_of=as_of)

            self._write_notification_source(
                report_dir,
                as_of=as_of - timedelta(hours=5),
                market_date="2026-07-22",
            )
            old_report = report_dir / f"report_{as_of - timedelta(hours=5):%Y%m%d}.csv"
            current_report = report_dir / f"report_{as_of:%Y%m%d}.csv"
            if old_report != current_report:
                old_report.replace(current_report)
            with patch.object(notify, "REPORT_DIR", report_dir):
                with self.assertRaisesRegex(ValueError, "current pipeline run"):
                    notify._load_notification_source_dates(as_of=as_of)

    def test_notifier_accepts_verified_current_run_deterministically(self) -> None:
        as_of = datetime(2026, 7, 23, 8, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            self._write_notification_source(
                report_dir,
                as_of=as_of,
                market_date="2026-07-22",
            )
            with patch.object(notify, "REPORT_DIR", report_dir):
                first = notify._load_notification_source_dates(as_of=as_of)
                second = notify._load_notification_source_dates(as_of=as_of)
            pd.testing.assert_frame_equal(first, second)

    def test_notifier_rejects_ai_output_from_a_different_source_run(self) -> None:
        as_of = datetime(2026, 7, 23, 8, 0, tzinfo=JST)
        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            self._write_notification_source(
                report_dir,
                as_of=as_of,
                market_date="2026-07-22",
            )
            ai_file = report_dir / "ai_judgement.csv"
            pd.DataFrame({"ticker": ["1000.T"], "価格": [100.0]}).to_csv(
                ai_file, index=False
            )
            ai_manifest = {
                "schema_version": 1,
                "run_id": "OLD-RUN",
                "generated_at": as_of.isoformat(),
                "input_report_file": f"report_{as_of:%Y%m%d}.csv",
                "input_report_sha256": "0" * 64,
                "ai_judgement_file": ai_file.name,
                "ai_judgement_sha256": sha256(ai_file.read_bytes()).hexdigest(),
                "ticker_count": 1,
                "optimized_signals_sha256": None,
                "learning_profile_sha256": None,
            }
            (report_dir / notify.AI_JUDGEMENT_MANIFEST_NAME).write_text(
                json.dumps(ai_manifest), encoding="utf-8"
            )
            with (
                patch.object(notify, "REPORT_DIR", report_dir),
                patch.object(notify, "AI_JUDGEMENT_FILE", ai_file),
                patch.object(notify, "OPTIMIZED_SIGNALS_FILE", report_dir / "optimized.csv"),
                patch.object(notify, "LEARNING_PROFILE_FILE", report_dir / "profile.json"),
            ):
                with self.assertRaisesRegex(ValueError, "current source run"):
                    notify.load_ai_judgement(as_of=as_of)


if __name__ == "__main__":
    unittest.main()
