from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from phoenix_core import historical_validation_20y as hv


ROOT = Path(__file__).resolve().parent.parent
JST = hv.JST


def make_history_frame(dates: list[str]) -> pd.DataFrame:
    index = pd.to_datetime(dates)
    rows = []
    for position, _ in enumerate(index):
        price = 100.0 + position
        rows.append(
            {
                "Open": price,
                "High": price + 1.0,
                "Low": price - 1.0,
                "Close": price + 0.5,
                "Volume": 1000 + position,
            }
        )
    frame = pd.DataFrame(rows, index=index)
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    return frame


def make_two_day_entry_frame(day1_close: float, day2_open: float) -> pd.DataFrame:
    index = pd.to_datetime(["2006-08-01", "2006-08-02"])
    return pd.DataFrame(
        [
            {
                "Open": day1_close,
                "High": day1_close + 1.0,
                "Low": day1_close - 1.0,
                "Close": day1_close,
                "Volume": 1000,
                "ATR": 1.0,
            },
            {
                "Open": day2_open,
                "High": day2_open + 1.0,
                "Low": day2_open - 1.0,
                "Close": day2_open,
                "Volume": 1001,
                "ATR": 1.0,
            },
        ],
        index=index,
    )


def make_atr_history_frame(dates: list[str], *, base_price: float = 100.0, atr: float = 1.0) -> pd.DataFrame:
    index = pd.to_datetime(dates)
    rows = []
    for position, _ in enumerate(index):
        price = base_price + position
        rows.append(
            {
                "Open": price,
                "High": price + 1.0,
                "Low": price - 1.0,
                "Close": price,
                "Volume": 1000 + position,
                "ATR": atr,
            }
        )
    frame = pd.DataFrame(rows, index=index)
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    return frame


def make_pending_order_config(initial_capital_yen: float, risk_per_trade_pct: float = 1.0) -> hv.HistoricalValidationConfig:
    return hv.HistoricalValidationConfig(
        initial_capital_yen=initial_capital_yen,
        lot_size=100,
        max_positions=1,
        max_position_pct=1.0,
        max_total_invested_pct=1.0,
        minimum_cash_reserve_pct=0.0,
        risk_per_trade_pct=risk_per_trade_pct,
        maximum_quantity_per_ticker=1000,
        commission_rate=0.0,
        slippage_rate=0.0,
        stop_atr_multiplier=1.5,
        target_r_multiplier=2.0,
        signal_score_threshold=70.0,
        rsi_min=40.0,
        rsi_max=72.0,
        ma_short=5,
        ma_mid=25,
        ma_long=75,
        max_hold_sessions=10,
        minimum_history_sessions=1,
        requested_years=20,
        allow_network_fetch=False,
        universe_csv="data/nikkei225.csv",
        benchmark_ticker="^N225",
        output_dir="reports/historical_validation_20y",
        report_json="reports/historical_validation_20y/summary.json",
        report_text="reports/historical_validation_20y/report.txt",
        annual_returns_csv="reports/historical_validation_20y/annual_returns.csv",
        monthly_returns_csv="reports/historical_validation_20y/monthly_returns.csv",
        data_coverage_csv="reports/historical_validation_20y/data_coverage.csv",
        trades_csv="reports/historical_validation_20y/trades.csv",
        equity_curve_csv="reports/historical_validation_20y/equity_curve.csv",
        benchmark_enabled=True,
        no_rss=True,
        no_real_orders=True,
        live_trading_enabled=False,
        orders_submitted=0,
    )


def make_config(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "enabled": True,
        "initial_capital_yen": 500000,
        "lot_size": 100,
        "fractional_shares": False,
        "max_positions": 1,
        "max_position_pct": 1.0,
        "max_total_invested_pct": 1.0,
        "minimum_cash_reserve_pct": 0.0,
        "risk_per_trade_pct": 0.01,
        "maximum_quantity_per_ticker": 1000,
        "commission_rate": 0.0,
        "slippage_rate": 0.0,
        "stop_atr_multiplier": 1.5,
        "target_r_multiplier": 2.0,
        "signal_score_threshold": 70.0,
        "rsi_min": 40.0,
        "rsi_max": 72.0,
        "ma_short": 5,
        "ma_mid": 25,
        "ma_long": 75,
        "max_hold_sessions": 10,
        "minimum_history_sessions": 1,
        "requested_years": 20,
        "requested_start": "2006-08-01",
        "requested_end": "2006-08-03",
        "allow_network_fetch": True,
        "universe_csv": "data/nikkei225.csv",
        "benchmark_ticker": "^N225",
        "cache_dir": "data/market_cache",
        "coverage_csv": "reports/historical_validation_20y/data_coverage.csv",
        "data_coverage_csv": "reports/historical_validation_20y/data_coverage.csv",
        "output_dir": "reports/historical_validation_20y",
        "report_json": "reports/historical_validation_20y/summary.json",
        "report_text": "reports/historical_validation_20y/report.txt",
        "annual_returns_csv": "reports/historical_validation_20y/annual_returns.csv",
        "monthly_returns_csv": "reports/historical_validation_20y/monthly_returns.csv",
        "trades_csv": "reports/historical_validation_20y/trades.csv",
        "equity_curve_csv": "reports/historical_validation_20y/equity_curve.csv",
        "benchmark_enabled": True,
        "no_rss": True,
        "no_real_orders": True,
        "live_trading_enabled": False,
        "orders_submitted": 0,
        "enforce_nikkei225": False,
        "expected_ticker_count": 1,
    }
    values.update(overrides)
    return values


def diagnostics_lookup(frame: pd.DataFrame) -> dict[tuple[int, str], int]:
    return {
        (int(row.year), str(row.reason)): int(row.count)
        for row in frame.itertuples(index=False)
    }


def legacy_cache_columns(ticker: str) -> list[str]:
    return [
        "Date",
        "Price",
        "Close",
        "High",
        "Low",
        "Open",
        "Volume",
        f"('Close', '{ticker}')",
        f"('High', '{ticker}')",
        f"('Low', '{ticker}')",
        f"('Open', '{ticker}')",
        f"('Volume', '{ticker}')",
        f"('Close', '{ticker}').1",
        f"('High', '{ticker}').1",
        f"('Low', '{ticker}').1",
        f"('Open', '{ticker}').1",
        f"('Volume', '{ticker}').1",
        f"('Close', '{ticker}').2",
        f"('High', '{ticker}').2",
        f"('Low', '{ticker}').2",
        f"('Open', '{ticker}').2",
        f"('Volume', '{ticker}').2",
        f"('Close', '{ticker}').3",
        f"('High', '{ticker}').3",
        f"('Low', '{ticker}').3",
        f"('Open', '{ticker}').3",
        f"('Volume', '{ticker}').3",
    ]


class HistoricalValidation20yTest(unittest.TestCase):
    def test_config_file_preserves_window_capital_and_lot_size(self) -> None:
        settings = hv.load_settings(ROOT)
        self.assertEqual(500000.0, float(settings["initial_capital_yen"]))
        self.assertEqual(100, int(settings["lot_size"]))
        self.assertFalse(bool(settings["fractional_shares"]))
        self.assertEqual("2006-08", settings["requested_start"])
        self.assertEqual("2026-08", settings["requested_end"])
        self.assertEqual("data/market_cache", settings["cache_dir"])
        self.assertEqual("reports/historical_validation_20y/data_coverage.csv", settings["coverage_csv"])
        self.assertTrue(bool(settings["no_rss"]))
        self.assertTrue(bool(settings["no_real_orders"]))
        self.assertEqual(0, int(settings["orders_submitted"]))
        self.assertTrue(bool(settings["enforce_nikkei225"]))
        self.assertEqual(225, int(settings["expected_ticker_count"]))

    def test_performance_metrics_use_initial_equity_baseline(self) -> None:
        equity_df = pd.DataFrame(
            {
                "date": pd.to_datetime(["2023-01-01", "2024-01-01"]),
                "equity_yen": [90.0, 121.0],
            }
        )

        performance = hv._performance_metrics(equity_df, 100.0)

        self.assertEqual(121.0, performance["final_equity_yen"])
        self.assertEqual(21.0, performance["total_profit_yen"])
        self.assertEqual(21.0, performance["total_return_pct"])
        self.assertEqual(10.0, performance["max_drawdown_pct"])
        self.assertEqual(10.0, performance["max_drawdown_yen"])
        expected_cagr = ((121.0 / 100.0) ** (1 / ((pd.Timestamp("2024-01-01") - pd.Timestamp("2023-01-01")).days / 365.25)) - 1) * 100
        self.assertAlmostEqual(expected_cagr, performance["cagr_pct"], places=6)
        self.assertNotEqual(0.0, performance["sharpe_ratio"])

        empty_performance = hv._performance_metrics(pd.DataFrame(columns=["date", "equity_yen"]), 100.0)
        self.assertEqual(100.0, empty_performance["final_equity_yen"])
        self.assertEqual(0.0, empty_performance["total_profit_yen"])
        self.assertEqual(0.0, empty_performance["total_return_pct"])
        self.assertEqual(0.0, empty_performance["max_drawdown_pct"])

    def test_summarize_simulation_result_uses_period_average_cash_ratio(self) -> None:
        equity_curve = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
                "cash_yen": [100.0, 50.0, 0.0],
                "market_value_yen": [0.0, 50.0, 100.0],
                "equity_yen": [100.0, 100.0, 100.0],
            }
        )
        result = hv.HistoricalValidationResult(
            trades=pd.DataFrame(),
            equity_curve=equity_curve,
            annual_returns=pd.DataFrame(),
            monthly_returns=pd.DataFrame(),
        )

        performance = hv._summarize_simulation_result(result, 100.0)

        self.assertAlmostEqual(0.5, performance["cash_ratio"], places=6)
        self.assertEqual(0.0, performance["cash_remaining_yen"])
        self.assertEqual(100.0, performance["market_value_yen"])

        empty_result = hv.HistoricalValidationResult(
            trades=pd.DataFrame(),
            equity_curve=pd.DataFrame(columns=["date", "cash_yen", "market_value_yen", "equity_yen"]),
            annual_returns=pd.DataFrame(),
            monthly_returns=pd.DataFrame(),
        )
        empty_performance = hv._summarize_simulation_result(empty_result, 100.0)

        self.assertEqual(1.0, empty_performance["cash_ratio"])
        self.assertEqual(100.0, empty_performance["cash_remaining_yen"])
        self.assertEqual(0.0, empty_performance["market_value_yen"])

    def test_close_position_accounts_for_entry_and_exit_fees_separately(self) -> None:
        config = hv.HistoricalValidationConfig(commission_rate=0.01)
        positions = {
            "7203.T": hv.PositionState(
                ticker="7203.T",
                company_name="Toyota",
                signal_date="2024-01-01",
                entry_date="2024-01-02",
                entry_session_index=1,
                entry_price=100.0,
                quantity=100,
                stop_price=95.0,
                target_price=120.0,
                signal_score=80.0,
                entry_cost_yen=10100.0,
                actual_stop_price=95.0,
                actual_target_price=120.0,
            )
        }
        trades: list[hv.TradeRecord] = []

        returned_cash = hv._close_position(
            positions=positions,
            ticker="7203.T",
            exit_date=pd.Timestamp("2024-01-03"),
            exit_price=110.0,
            reason="TARGET",
            session_index=2,
            config=config,
            trades=trades,
        )

        self.assertEqual(10890.0, returned_cash)
        self.assertNotIn("7203.T", positions)
        self.assertEqual(1, len(trades))

        trade = trades[0]
        self.assertEqual(10100.0, trade.entry_cost_yen)
        self.assertEqual(11000.0, trade.exit_value_yen)
        self.assertEqual(1000.0, trade.gross_profit_yen)
        self.assertEqual(210.0, trade.fees_yen)
        self.assertEqual(790.0, trade.profit_yen)
        self.assertEqual(round(790.0 / 10100.0 * 100.0, 4), trade.return_pct)

    def test_download_ticker_history_applies_quote_transport(self) -> None:
        original_flag = hv._QUOTE_TRANSPORT_INITIALIZED
        hv._QUOTE_TRANSPORT_INITIALIZED = False
        try:
            with tempfile.TemporaryDirectory() as directory:
                calls: list[dict[str, object]] = []

                def fake_download(ticker: str, **kwargs):
                    calls.append({"ticker": ticker, **kwargs})
                    frame = make_history_frame(
                        [
                            "2006-08-01",
                            "2006-08-02",
                            "2006-08-03",
                        ]
                    )
                    frame.columns = pd.MultiIndex.from_product([[ticker], frame.columns])
                    return frame

                with patch.dict(os.environ, {}, clear=False), patch.object(
                    hv,
                    "prepare_quote_environment",
                    return_value=({"status": "READY", "code": "READY", "remediation": ""}, Path("C:/certs/phoenix-ca.pem")),
                ) as prepare, patch.object(hv.yf, "download", side_effect=fake_download):
                    outcome = hv.download_ticker_history(
                        "7203.T",
                        date(2006, 8, 1),
                        date(2006, 8, 3),
                    )
                    self.assertEqual(1, prepare.call_count)
                    self.assertEqual(1, len(calls))
                    self.assertEqual("2006-08-01", calls[0]["start"])
                    self.assertEqual("2006-08-04", calls[0]["end"])
                    self.assertEqual(Path("C:/certs/phoenix-ca.pem"), Path(os.environ["SSL_CERT_FILE"]))
                    self.assertEqual(Path("C:/certs/phoenix-ca.pem"), Path(os.environ["CURL_CA_BUNDLE"]))
                    self.assertEqual(Path("C:/certs/phoenix-ca.pem"), Path(os.environ["REQUESTS_CA_BUNDLE"]))
                    self.assertEqual(
                        [
                            "2006-08-01",
                            "2006-08-02",
                            "2006-08-03",
                        ],
                        outcome.index.strftime("%Y-%m-%d").tolist(),
                    )
                    self.assertEqual(["Open", "High", "Low", "Close", "Volume"], outcome.columns.tolist())
        finally:
            hv._QUOTE_TRANSPORT_INITIALIZED = original_flag

    def test_atomic_write_retries_permission_error_and_preserves_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "result.txt"
            original_replace = os.replace
            sleep_calls: list[float] = []
            replace_calls = {"count": 0}

            def flaky_replace(src: Path, dst: Path) -> None:
                replace_calls["count"] += 1
                if replace_calls["count"] <= 2:
                    raise PermissionError("WinError 5")
                original_replace(src, dst)

            with patch.object(hv.os, "replace", side_effect=flaky_replace) as replace, patch.object(
                hv.time,
                "sleep",
                side_effect=lambda seconds: sleep_calls.append(seconds),
            ):
                hv.atomic_write(target, "payload\n")

            self.assertEqual(3, replace.call_count)
            self.assertEqual([0.2, 0.4], sleep_calls)
            self.assertEqual("payload\n", target.read_text(encoding="utf-8"))
            self.assertEqual([], list(root.glob("*.tmp")))

    def test_build_data_coverage_emits_requested_schema(self) -> None:
        requested_start = pd.Timestamp("2024-01-02")
        requested_end = pd.Timestamp("2024-01-12")
        full_dates = pd.bdate_range("2024-01-02", "2024-01-12").strftime("%Y-%m-%d").tolist()
        partial_dates = pd.bdate_range("2024-01-08", "2024-01-12").strftime("%Y-%m-%d").tolist()
        universe = pd.DataFrame(
            [
                {"ticker": "1332.T", "company_name": "Full"},
                {"ticker": "1605.T", "company_name": "Partial"},
                {"ticker": "9999.T", "company_name": "Missing"},
            ]
        )
        histories = {
            "1332.T": make_history_frame(full_dates),
            "1605.T": make_history_frame(partial_dates),
            "9999.T": pd.DataFrame(),
        }

        coverage = hv.build_data_coverage(universe, histories, requested_start, requested_end)

        self.assertEqual(
            [
                "ticker",
                "company_name",
                "requested_start",
                "requested_end",
                "actual_start",
                "actual_end",
                "trading_days",
                "coverage_status",
                "missing_reason",
                "network_attempts",
                "cache_used",
                "download_used",
                "coverage_pct",
            ],
            coverage.columns.tolist(),
        )
        self.assertEqual(["SUCCESS", "PARTIAL", "NO_DATA"], coverage["coverage_status"].tolist())
        self.assertEqual("2024-01-02", coverage.loc[0, "requested_start"])
        self.assertEqual("2024-01-12", coverage.loc[0, "requested_end"])
        self.assertEqual("2024-01-02", coverage.loc[0, "actual_start"])
        self.assertEqual("2024-01-12", coverage.loc[0, "actual_end"])
        self.assertEqual(9, int(coverage.loc[0, "trading_days"]))
        self.assertEqual(100.0, float(coverage.loc[0, "coverage_pct"]))
        self.assertEqual("", coverage.loc[0, "missing_reason"])
        self.assertEqual(55.56, float(coverage.loc[1, "coverage_pct"]))
        self.assertIn("history starts after requested_start", coverage.loc[1, "missing_reason"])
        self.assertIn("missing_base_days=4", coverage.loc[1, "missing_reason"])
        self.assertEqual(0.0, float(coverage.loc[2, "coverage_pct"]))
        self.assertEqual("no usable OHLCV rows were returned", coverage.loc[2, "missing_reason"])

    def test_build_period_returns_uses_initial_equity_then_previous_period_close(self) -> None:
        equity_df = pd.DataFrame(
            {
                "date": [
                    "2024-01-02",
                    "2024-01-31",
                    "2024-02-01",
                    "2024-02-28",
                ],
                "equity_yen": [110.0, 121.0, 108.9, 108.9],
            }
        )

        result = hv.build_period_returns(equity_df, pd.DataFrame(), "M", 100.0)

        self.assertEqual(["2024-01", "2024-02"], result["period"].tolist())
        january = result.iloc[0]
        february = result.iloc[1]

        self.assertEqual(100.0, float(january["start_equity_yen"]))
        self.assertEqual(121.0, float(january["end_equity_yen"]))
        self.assertEqual(21.0, float(january["profit_yen"]))
        self.assertEqual(21.0, float(january["return_pct"]))
        self.assertEqual(0.0, float(january["max_drawdown_pct"]))

        self.assertEqual(121.0, float(february["start_equity_yen"]))
        self.assertEqual(108.9, float(february["end_equity_yen"]))
        self.assertEqual(-12.1, float(february["profit_yen"]))
        self.assertEqual(-10.0, float(february["return_pct"]))
        self.assertEqual(10.0, float(february["max_drawdown_pct"]))

    def test_requested_range_uses_global_last_market_date_for_end_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[dict[str, object]] = []

            def make_dates(start: str, end: str, gap_start: str | None = None, gap_end: str | None = None) -> list[str]:
                gap_start_ts = pd.Timestamp(gap_start) if gap_start is not None else None
                gap_end_ts = pd.Timestamp(gap_end) if gap_end is not None else None
                dates: list[str] = []
                for timestamp in pd.bdate_range(start, end):
                    if gap_start_ts is not None and gap_end_ts is not None and gap_start_ts <= timestamp <= gap_end_ts:
                        continue
                    dates.append(timestamp.strftime("%Y-%m-%d"))
                return dates

            def fake_download(ticker: str, **kwargs):
                calls.append({"ticker": ticker, **kwargs})
                if ticker == "7203.T":
                    return make_history_frame(
                        make_dates("2006-08-01", "2026-08-07", "2012-07-02", "2012-07-13")
                    )
                return make_history_frame(make_dates("2006-08-01", "2026-07-20"))

            with patch.object(hv.yf, "download", side_effect=fake_download):
                report = hv.run_historical_validation_20y(
                    root=root,
                    tickers=["7203.T", "6758.T"],
                    requested_start="2006-08-01",
                    requested_end="2026-08-09",
                    cache_dir=root / "data" / "market_cache",
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2026, 8, 9, 16, 0, tzinfo=JST),
                )

            self.assertEqual(2, len(calls))
            self.assertEqual(["7203.T", "6758.T"], [call["ticker"] for call in calls])
            self.assertEqual("2006-08-01", calls[0]["start"])
            self.assertEqual("2026-08-10", calls[0]["end"])
            self.assertEqual("2006-08-01", calls[1]["start"])
            self.assertEqual("2026-08-10", calls[1]["end"])
            self.assertEqual(2, report["ticker_count"])
            rows = {row["ticker"]: row for row in report["rows"]}
            self.assertEqual("2026-08-09", rows["7203.T"]["requested_end"])
            self.assertEqual("2026-08-07", rows["7203.T"]["actual_end"])
            self.assertEqual("PARTIAL", rows["7203.T"]["coverage_status"])
            self.assertIn("missing_base_days=", rows["7203.T"]["missing_reason"])
            self.assertIn("first_missing=2012-07-02", rows["7203.T"]["missing_reason"])
            self.assertIn("last_missing=2012-07-13", rows["7203.T"]["missing_reason"])
            self.assertEqual("2026-07-20", rows["6758.T"]["actual_end"])
            self.assertEqual("PARTIAL", rows["6758.T"]["coverage_status"])
            self.assertIn("history ends before requested_end", rows["6758.T"]["missing_reason"])

    def test_same_ticker_range_is_not_downloaded_repeatedly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []

            def fake_download(ticker: str, **kwargs):
                calls.append(ticker)
                return make_history_frame(
                    [
                        "2006-08-01",
                        "2006-08-02",
                        "2006-08-03",
                    ]
                )

            with patch.object(hv.yf, "download", side_effect=fake_download):
                report = hv.run_historical_validation_20y(
                    root=root,
                    tickers=["7203.T", "7203.T"],
                    requested_start="2006-08-01",
                    requested_end="2006-08-03",
                    cache_dir=root / "data" / "market_cache",
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                )

            self.assertEqual(["7203.T"], calls)
            self.assertEqual(1, report["ticker_count"])
            self.assertEqual("SUCCESS", report["rows"][0]["coverage_status"])

    def test_cache_hit_fetches_only_missing_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_dir = root / "data" / "market_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached = make_history_frame(
                [
                    "2006-08-01",
                    "2006-08-02",
                ]
            )
            cached.index.name = "Date"
            cached.to_csv(cache_dir / "7203_T.csv", encoding="utf-8")
            calls: list[dict[str, object]] = []

            def fake_download(ticker: str, **kwargs):
                calls.append({"ticker": ticker, **kwargs})
                return make_history_frame(
                    [
                        "2006-08-03",
                        "2006-08-04",
                    ]
                )

            with patch.object(hv.yf, "download", side_effect=fake_download):
                outcome = hv.fetch_ticker_history(
                    root,
                    "7203.T",
                    date(2006, 8, 1),
                    date(2006, 8, 4),
                    cache_dir=cache_dir,
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                    allow_network_fetch=True,
                )

            self.assertEqual(1, len(calls))
            self.assertEqual("2006-08-03", calls[0]["start"])
            self.assertEqual("2006-08-05", calls[0]["end"])
            self.assertTrue(outcome.cache_used)
            self.assertTrue(outcome.download_used)
            self.assertEqual(1, outcome.network_attempts)
            self.assertIsNone(outcome.download_error)
            self.assertEqual(
                [
                    "2006-08-01",
                    "2006-08-02",
                    "2006-08-03",
                    "2006-08-04",
                ],
                outcome.history.index.strftime("%Y-%m-%d").tolist(),
            )

    def test_legacy_tuple_cache_is_migrated_to_five_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_dir = root / "data" / "market_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "7203_T.csv"
            columns = legacy_cache_columns("7203.T")
            rows = [
                {
                    "Date": "2006-08-01",
                    "Price": "2006-08-02",
                    "('High', '7203.T')": 110.0,
                    "('Open', '7203.T')": 100.0,
                },
                {
                    "Price": "2006-08-01",
                    "('Low', '7203.T')": 90.0,
                    "('Close', '7203.T')": 105.0,
                    "('Volume', '7203.T')": 1000.0,
                },
                {
                    "Date": "1970-01-01",
                    "('Open', '7203.T')": 0.0,
                    "('High', '7203.T')": 0.0,
                    "('Low', '7203.T')": 0.0,
                    "('Close', '7203.T')": 0.0,
                    "('Volume', '7203.T')": 0.0,
                },
            ]
            pd.DataFrame(rows, columns=columns).to_csv(cache_file, index=False, encoding="utf-8")

            outcome = hv.fetch_ticker_history(
                root,
                "7203.T",
                date(2006, 8, 1),
                date(2006, 8, 1),
                cache_dir=cache_dir,
                as_of=datetime(2006, 8, 2, 16, 0, tzinfo=JST),
                allow_network_fetch=False,
            )

            self.assertEqual(["2006-08-01"], outcome.history.index.strftime("%Y-%m-%d").tolist())
            self.assertEqual(["Open", "High", "Low", "Close", "Volume"], outcome.history.columns.tolist())
            self.assertEqual(100.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Open"]))
            self.assertEqual(110.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "High"]))
            self.assertEqual(90.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Low"]))
            self.assertEqual(105.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Close"]))
            self.assertEqual(1000.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Volume"]))

            rewritten = pd.read_csv(cache_file)
            self.assertEqual(["Date", "Open", "High", "Low", "Close", "Volume"], rewritten.columns.tolist())
            self.assertEqual(["2006-08-01"], rewritten["Date"].tolist())

    def test_legacy_price_date_cache_is_restored_and_fake_row_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_dir = root / "data" / "market_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "7203_T.csv"
            columns = legacy_cache_columns("7203.T") + ["Unnamed: 0"]
            rows = [
                {
                    "Price": "2006-08-01",
                    "Unnamed: 0": "2006-08-02",
                    "('Open', '7203.T')": 200.0,
                    "('High', '7203.T')": 210.0,
                    "('Low', '7203.T')": 190.0,
                    "('Close', '7203.T')": 205.0,
                },
                {
                    "Unnamed: 0": "2006-08-01",
                    "('Volume', '7203.T')": 2000.0,
                },
                {
                    "Date": "1970-01-01",
                    "Price": "1970-01-01",
                    "Unnamed: 0": "1970-01-01",
                    "('Open', '7203.T')": 0.0,
                    "('High', '7203.T')": 0.0,
                    "('Low', '7203.T')": 0.0,
                    "('Close', '7203.T')": 0.0,
                    "('Volume', '7203.T')": 0.0,
                },
            ]
            pd.DataFrame(rows, columns=columns).to_csv(cache_file, index=False, encoding="utf-8")

            outcome = hv.fetch_ticker_history(
                root,
                "7203.T",
                date(2006, 8, 1),
                date(2006, 8, 1),
                cache_dir=cache_dir,
                as_of=datetime(2006, 8, 2, 16, 0, tzinfo=JST),
                allow_network_fetch=False,
            )

            self.assertEqual(["2006-08-01"], outcome.history.index.strftime("%Y-%m-%d").tolist())
            self.assertEqual(["Open", "High", "Low", "Close", "Volume"], outcome.history.columns.tolist())
            self.assertEqual(200.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Open"]))
            self.assertEqual(210.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "High"]))
            self.assertEqual(190.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Low"]))
            self.assertEqual(205.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Close"]))
            self.assertEqual(2000.0, float(outcome.history.loc[pd.Timestamp("2006-08-01"), "Volume"]))

            rewritten = pd.read_csv(cache_file)
            self.assertEqual(["Date", "Open", "High", "Low", "Close", "Volume"], rewritten.columns.tolist())
            self.assertEqual(["2006-08-01"], rewritten["Date"].tolist())

    def test_build_data_coverage_uses_only_valid_ohlcv_rows(self) -> None:
        universe = pd.DataFrame({"ticker": ["7203.T"], "company_name": ["Toyota"]})
        histories = {
            "7203.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 110.0, "Low": 90.0, "Close": 105.0, "Volume": 1000},
                    {"Open": 0.0, "High": 0.0, "Low": 0.0, "Close": 0.0, "Volume": 1001},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            )
        }

        coverage = hv.build_data_coverage(
            universe,
            histories,
            pd.Timestamp("2006-08-01"),
            pd.Timestamp("2006-08-02"),
        )

        self.assertEqual(1, int(coverage.loc[0, "trading_days"]))
        self.assertEqual("2006-08-01", coverage.loc[0, "actual_start"])
        self.assertEqual("2006-08-01", coverage.loc[0, "actual_end"])
        self.assertEqual("SUCCESS", coverage.loc[0, "coverage_status"])
        self.assertEqual("", coverage.loc[0, "missing_reason"])

    def test_build_data_coverage_ignores_days_outside_membership_periods(self) -> None:
        universe = pd.DataFrame(
            [
                {
                    "ticker": "1111.T",
                    "company_name": "LateJoin",
                    "member_from": "2024-01-04",
                    "member_until": "",
                },
                {
                    "ticker": "2222.T",
                    "company_name": "EarlyExit",
                    "member_from": "2024-01-02",
                    "member_until": "2024-01-05",
                },
            ]
        )
        histories = {
            "1111.T": make_history_frame(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "2222.T": make_history_frame(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        }

        coverage = hv.build_data_coverage(
            universe,
            histories,
            pd.Timestamp("2024-01-02"),
            pd.Timestamp("2024-01-05"),
        )
        rows = {row["ticker"]: row for row in coverage.to_dict(orient="records")}

        self.assertEqual("SUCCESS", rows["1111.T"]["coverage_status"])
        self.assertEqual("2024-01-04", rows["1111.T"]["actual_start"])
        self.assertEqual("2024-01-05", rows["1111.T"]["actual_end"])
        self.assertEqual(100.0, float(rows["1111.T"]["coverage_pct"]))
        self.assertEqual("SUCCESS", rows["2222.T"]["coverage_status"])
        self.assertEqual("2024-01-02", rows["2222.T"]["actual_start"])
        self.assertEqual("2024-01-04", rows["2222.T"]["actual_end"])
        self.assertEqual(100.0, float(rows["2222.T"]["coverage_pct"]))

    def test_build_data_coverage_marks_gap_within_membership_as_partial(self) -> None:
        universe = pd.DataFrame(
            [
                {
                    "ticker": "3333.T",
                    "company_name": "Gap",
                    "member_from": "2024-01-02",
                    "member_until": "2024-01-10",
                },
                {
                    "ticker": "4444.T",
                    "company_name": "Support",
                    "member_from": "2024-01-02",
                    "member_until": "",
                }
            ]
        )
        histories = {
            "3333.T": make_history_frame(["2024-01-02", "2024-01-03", "2024-01-05"]),
            "4444.T": make_history_frame(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        }

        coverage = hv.build_data_coverage(
            universe,
            histories,
            pd.Timestamp("2024-01-02"),
            pd.Timestamp("2024-01-05"),
        )

        self.assertEqual("PARTIAL", coverage.loc[0, "coverage_status"])
        self.assertEqual(75.0, float(coverage.loc[0, "coverage_pct"]))
        self.assertIn("missing_base_days=1", coverage.loc[0, "missing_reason"])
        self.assertIn("first_missing=2024-01-04", coverage.loc[0, "missing_reason"])
        self.assertIn("last_missing=2024-01-04", coverage.loc[0, "missing_reason"])

    def test_build_data_coverage_marks_out_of_window_membership_as_not_eligible(self) -> None:
        universe = pd.DataFrame(
            [
                {
                    "ticker": "4444.T",
                    "company_name": "Dormant",
                    "member_from": "2024-01-10",
                    "member_until": "2024-01-15",
                }
            ]
        )
        histories = {
            "4444.T": make_history_frame(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
        }

        coverage = hv.build_data_coverage(
            universe,
            histories,
            pd.Timestamp("2024-01-02"),
            pd.Timestamp("2024-01-05"),
        )

        self.assertEqual("NOT_ELIGIBLE", coverage.loc[0, "coverage_status"])
        self.assertEqual("", coverage.loc[0, "actual_start"])
        self.assertEqual("", coverage.loc[0, "actual_end"])
        self.assertEqual(0.0, float(coverage.loc[0, "coverage_pct"]))
        self.assertIn("no constituent days overlap the requested range", coverage.loc[0, "missing_reason"])

    def test_same_ticker_range_is_downloaded_only_once_per_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[dict[str, object]] = []
            registry: set[tuple[str, date, date]] = set()

            def fake_download(ticker: str, **kwargs):
                calls.append({"ticker": ticker, **kwargs})
                return make_history_frame(
                    [
                        "2006-08-01",
                        "2006-08-02",
                        "2006-08-03",
                    ]
                )

            with patch.object(hv, "_save_csv_history", side_effect=lambda *args, **kwargs: None), patch.object(
                hv.yf,
                "download",
                side_effect=fake_download,
            ):
                first = hv.fetch_ticker_history(
                    root,
                    "7203.T",
                    date(2006, 8, 1),
                    date(2006, 8, 3),
                    cache_dir=root / "data" / "market_cache",
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                    allow_network_fetch=True,
                    download_registry=registry,
                )
                second = hv.fetch_ticker_history(
                    root,
                    "7203.T",
                    date(2006, 8, 1),
                    date(2006, 8, 3),
                    cache_dir=root / "data" / "market_cache",
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                    allow_network_fetch=True,
                    download_registry=registry,
                )

            self.assertEqual(1, len(calls))
            self.assertTrue(first.download_used)
            self.assertEqual(3, len(first.history))
            self.assertFalse(second.download_used)
            self.assertEqual(0, second.network_attempts)
            self.assertTrue(second.history.empty)

    def test_download_failure_is_recorded_and_validation_continues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []

            def fake_download(ticker: str, **kwargs):
                calls.append(ticker)
                if ticker == "7203.T":
                    raise RuntimeError("boom")
                return make_history_frame(
                    [
                        "2006-08-01",
                        "2006-08-02",
                        "2006-08-03",
                    ]
                )

            with patch.object(hv.yf, "download", side_effect=fake_download):
                report = hv.run_historical_validation_20y(
                    root=root,
                    tickers=["7203.T", "6758.T"],
                    requested_start="2006-08-01",
                    requested_end="2006-08-03",
                    cache_dir=root / "data" / "market_cache",
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                )

            self.assertEqual(["7203.T", "6758.T"], calls)
            rows = {row["ticker"]: row for row in report["rows"]}
            self.assertEqual("DOWNLOAD_FAILED", rows["7203.T"]["coverage_status"])
            self.assertEqual("SUCCESS", rows["6758.T"]["coverage_status"])
            self.assertEqual(2, report["ticker_count"])

    def test_later_listing_is_partial_not_fake_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls: list[str] = []

            def make_dates(start: str, end: str) -> list[str]:
                return [timestamp.strftime("%Y-%m-%d") for timestamp in pd.bdate_range(start, end)]

            def fake_download(ticker: str, **kwargs):
                calls.append(ticker)
                if ticker == "7203.T":
                    return make_history_frame(
                        [
                            "2018-01-04",
                            "2018-01-05",
                            "2018-01-08",
                            "2018-01-09",
                            "2018-01-10",
                        ]
                    )
                return make_history_frame(make_dates("2006-08-01", "2018-01-10"))

            with patch.object(hv.yf, "download", side_effect=fake_download):
                report = hv.run_historical_validation_20y(
                    root=root,
                    tickers=["7203.T", "6758.T"],
                    requested_start="2006-08-01",
                    requested_end="2018-01-10",
                    cache_dir=root / "data" / "market_cache",
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2018, 1, 11, 16, 0, tzinfo=JST),
                )

            self.assertEqual(["7203.T", "6758.T"], calls)
            rows = {row["ticker"]: row for row in report["rows"]}
            row = rows["7203.T"]
            self.assertEqual("2018-01-04", row["actual_start"])
            self.assertEqual("PARTIAL", row["coverage_status"])
            self.assertIn("history starts after requested_start", row["missing_reason"])
            self.assertIn("missing_base_days=", row["missing_reason"])
            self.assertEqual("SUCCESS", rows["6758.T"]["coverage_status"])

    def test_fixed_max_positions_does_not_cap_universe(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-03")
        universe = pd.DataFrame(
            [
                {"ticker": "7203.T", "company_name": "Toyota"},
                {"ticker": "6758.T", "company_name": "Sony"},
            ]
        )
        base_frame = pd.DataFrame(
            {
                "Open": [100.0, 101.0, 102.0],
                "High": [101.0, 102.0, 103.0],
                "Low": [99.0, 100.0, 101.0],
                "Close": [100.5, 101.5, 102.5],
                "Volume": [1000, 1001, 1002],
                "ATR": [1.0, 1.0, 1.0],
            },
            index=pd.to_datetime(["2006-08-01", "2006-08-02", "2006-08-03"]),
        )
        prepared_histories = {
            "7203.T": base_frame.copy(),
            "6758.T": base_frame.copy(),
        }
        config = hv.HistoricalValidationConfig(
            initial_capital_yen=500000,
            lot_size=100,
            max_positions=1,
            max_position_pct=0.5,
            max_total_invested_pct=1.0,
            minimum_cash_reserve_pct=0.0,
            risk_per_trade_pct=0.01,
            maximum_quantity_per_ticker=1000,
            commission_rate=0.0,
            slippage_rate=0.0,
            stop_atr_multiplier=1.5,
            target_r_multiplier=2.0,
            signal_score_threshold=70.0,
            rsi_min=40.0,
            rsi_max=72.0,
            ma_short=5,
            ma_mid=25,
            ma_long=75,
            max_hold_sessions=10,
            minimum_history_sessions=1,
            requested_years=20,
            allow_network_fetch=False,
            universe_csv="data/nikkei225.csv",
            benchmark_ticker="^N225",
            output_dir="reports/historical_validation_20y",
            report_json="reports/historical_validation_20y/summary.json",
            report_text="reports/historical_validation_20y/report.txt",
            annual_returns_csv="reports/historical_validation_20y/annual_returns.csv",
            monthly_returns_csv="reports/historical_validation_20y/monthly_returns.csv",
            data_coverage_csv="reports/historical_validation_20y/data_coverage.csv",
            trades_csv="reports/historical_validation_20y/trades.csv",
            equity_curve_csv="reports/historical_validation_20y/equity_curve.csv",
            benchmark_enabled=True,
            no_rss=True,
            no_real_orders=True,
            live_trading_enabled=False,
            orders_submitted=0,
        )

        with patch.object(hv, "is_entry_signal", return_value=True), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(2, len(result.trades))
        self.assertEqual(2, int(result.equity_curve["open_positions"].max()))

    def test_pending_order_priority_prefers_high_score_independent_of_input_order(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories_forward = {
            "1000.T": make_two_day_entry_frame(90.0, 90.0),
            "2000.T": make_two_day_entry_frame(100.0, 100.0),
        }
        prepared_histories_reverse = {
            "2000.T": make_two_day_entry_frame(100.0, 100.0),
            "1000.T": make_two_day_entry_frame(90.0, 90.0),
        }
        universe = pd.DataFrame(
            [
                {"ticker": "1000.T", "company_name": "LOW"},
                {"ticker": "2000.T", "company_name": "HIGH"},
            ]
        )
        config = make_pending_order_config(10000.0)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            side_effect=lambda row, strategy: float(row["Close"]),
        ):
            forward = hv.simulate_validation(prepared_histories_forward, universe, config, requested_start, requested_end)
            reverse = hv.simulate_validation(prepared_histories_reverse, universe, config, requested_start, requested_end)

        self.assertEqual(["HIGH"], forward.trades["company_name"].tolist())
        self.assertEqual(["HIGH"], reverse.trades["company_name"].tolist())
        self.assertEqual(0, forward.rejected_due_to_lot)
        self.assertEqual(0, reverse.rejected_due_to_lot)
        self.assertEqual(1, forward.rejected_due_to_buying_power)
        self.assertEqual(1, reverse.rejected_due_to_buying_power)

    def test_pending_order_rejects_lot_when_cash_and_exposure_allow_one_lot_but_risk_limits_quantity(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "1000.T": make_two_day_entry_frame(100.0, 100.0),
        }
        universe = pd.DataFrame(
            [
                {"ticker": "1000.T", "company_name": "RISK"},
            ]
        )
        config = make_pending_order_config(10000.0, risk_per_trade_pct=0.01)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            side_effect=lambda row, strategy: float(row["Close"]),
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertTrue(result.trades.empty)
        self.assertEqual(1, result.rejected_due_to_lot)
        self.assertEqual(0, result.rejected_due_to_buying_power)

    def test_pending_orders_release_all_reserved_cash_before_gap_up_fills(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "1000.T": make_two_day_entry_frame(90.0, 140.0),
            "2000.T": make_two_day_entry_frame(100.0, 150.0),
        }
        universe = pd.DataFrame(
            [
                {"ticker": "1000.T", "company_name": "LOW"},
                {"ticker": "2000.T", "company_name": "HIGH"},
            ]
        )
        config = make_pending_order_config(19000.0)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            side_effect=lambda row, strategy: float(row["Close"]),
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(["HIGH"], result.trades["company_name"].tolist())
        self.assertEqual(0, result.rejected_due_to_lot)
        self.assertEqual(1, result.rejected_due_to_buying_power)

    def test_diagnostics_record_signal_candidates_and_risk_shortfalls_without_pending(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "1000.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 111.0, "Low": 90.0, "Close": 100.0, "Volume": 1000, "ATR": 10.0},
                    {"Open": 100.0, "High": 111.0, "Low": 90.0, "Close": 100.0, "Volume": 1001, "ATR": 10.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "1000.T", "company_name": "RISK"},
            ]
        )
        config = make_pending_order_config(10000.0, risk_per_trade_pct=0.005)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        counts = diagnostics_lookup(result.diagnostics)
        self.assertEqual(1, counts[(2006, "SIGNAL_CANDIDATE")])
        self.assertEqual(1, counts[(2006, "REJECT_RISK_SIZE")])
        self.assertEqual(0, counts[(2006, "PENDING_CREATED")])
        self.assertEqual(0, counts[(2006, "D1_FILLED")])
        self.assertTrue(result.trades.empty)
        self.assertEqual(1, result.rejected_due_to_lot)
        self.assertEqual(0, result.rejected_due_to_buying_power)

    def test_diagnostics_record_pending_created_and_d1_cash_shortfall_after_gap_up(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "1000.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 111.0, "Low": 90.0, "Close": 100.0, "Volume": 1000, "ATR": 10.0},
                    {"Open": 150.0, "High": 161.0, "Low": 140.0, "Close": 150.0, "Volume": 1001, "ATR": 10.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "1000.T", "company_name": "CASH"},
            ]
        )
        config = replace(
            make_pending_order_config(15_000.0),
            minimum_cash_reserve_pct=0.10,
        )

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        counts = diagnostics_lookup(result.diagnostics)
        self.assertEqual(1, counts[(2006, "SIGNAL_CANDIDATE")])
        self.assertEqual(1, counts[(2006, "PENDING_CREATED")])
        self.assertEqual(1, counts[(2006, "D1_REJECT_CASH")])
        self.assertEqual(0, counts[(2006, "D1_FILLED")])
        self.assertTrue(result.trades.empty)
        self.assertEqual(0, result.rejected_due_to_lot)
        self.assertEqual(1, result.rejected_due_to_buying_power)

    def test_diagnostics_record_pending_created_and_d1_position_limit_shortfall_after_gap_up(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "1000.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 111.0, "Low": 90.0, "Close": 100.0, "Volume": 1000, "ATR": 10.0},
                    {"Open": 150.0, "High": 161.0, "Low": 140.0, "Close": 150.0, "Volume": 1001, "ATR": 10.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "1000.T", "company_name": "LIMIT"},
            ]
        )
        config = replace(
            make_pending_order_config(1_000_000.0, risk_per_trade_pct=0.01),
            max_position_pct=0.01,
        )

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        counts = diagnostics_lookup(result.diagnostics)
        self.assertEqual(1, counts[(2006, "SIGNAL_CANDIDATE")])
        self.assertEqual(1, counts[(2006, "PENDING_CREATED")])
        self.assertEqual(1, counts[(2006, "D1_REJECT_POSITION_LIMIT")])
        self.assertEqual(0, counts[(2006, "D1_REJECT_CASH")])
        self.assertEqual(0, counts[(2006, "D1_REJECT_TOTAL_EXPOSURE")])
        self.assertEqual(0, counts[(2006, "D1_FILLED")])
        self.assertTrue(result.trades.empty)

    def test_diagnostics_record_d1_position_limit_preempts_cash_shortfall_after_gap_up(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "1000.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 111.0, "Low": 90.0, "Close": 100.0, "Volume": 1000, "ATR": 10.0},
                    {"Open": 150.0, "High": 161.0, "Low": 140.0, "Close": 150.0, "Volume": 1001, "ATR": 10.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "1000.T", "company_name": "PREEMPT"},
            ]
        )
        config = replace(
            make_pending_order_config(15_000.0, risk_per_trade_pct=0.10),
            max_position_pct=0.90,
            minimum_cash_reserve_pct=0.10,
        )

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        counts = diagnostics_lookup(result.diagnostics)
        self.assertEqual(1, counts[(2006, "SIGNAL_CANDIDATE")])
        self.assertEqual(1, counts[(2006, "PENDING_CREATED")])
        self.assertEqual(1, counts[(2006, "D1_REJECT_POSITION_LIMIT")])
        self.assertEqual(0, counts[(2006, "D1_REJECT_CASH")])
        self.assertEqual(0, counts[(2006, "D1_REJECT_TOTAL_EXPOSURE")])
        self.assertEqual(0, counts[(2006, "D1_FILLED")])
        self.assertTrue(result.trades.empty)

    def test_entry_day_stop_executes_after_open_fill(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "7203.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000, "ATR": 1.0},
                    {"Open": 100.0, "High": 101.0, "Low": 98.0, "Close": 100.0, "Volume": 1001, "ATR": 1.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "7203.T", "company_name": "Toyota"},
            ]
        )
        config = make_pending_order_config(20000.0)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(1, len(result.trades))
        trade = result.trades.iloc[0]
        self.assertEqual("2006-08-02", trade["entry_date"])
        self.assertEqual("2006-08-02", trade["exit_date"])
        self.assertEqual("STOP", trade["exit_reason"])
        self.assertEqual(1, int(trade["holding_sessions"]))

    def test_gap_up_reanchors_stop_and_target_before_intraday_exit(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-03")
        prepared_histories = {
            "7203.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000, "ATR": 1.0},
                    {"Open": 150.0, "High": 151.0, "Low": 149.0, "Close": 150.0, "Volume": 1001, "ATR": 1.0},
                    {"Open": 150.0, "High": 154.0, "Low": 149.0, "Close": 153.5, "Volume": 1002, "ATR": 1.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02", "2006-08-03"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "7203.T", "company_name": "Toyota"},
            ]
        )
        config = make_pending_order_config(30000.0)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(1, len(result.trades))
        trade = result.trades.iloc[0]
        self.assertEqual("2006-08-02", trade["entry_date"])
        self.assertEqual("2006-08-03", trade["exit_date"])
        self.assertEqual("TARGET", trade["exit_reason"])
        self.assertEqual(150.0, float(trade["entry_price"]))
        self.assertEqual(153.0, float(trade["exit_price"]))

    def test_intraday_exit_proceeds_do_not_fund_same_day_open_fills(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "A.T": pd.DataFrame(
                [
                    {"Open": 90.0, "High": 91.0, "Low": 89.0, "Close": 90.0, "Volume": 1000, "ATR": 1.0},
                    {"Open": 150.0, "High": 155.0, "Low": 149.0, "Close": 154.0, "Volume": 1001, "ATR": 1.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            ),
            "B.T": pd.DataFrame(
                [
                    {"Open": 80.0, "High": 81.0, "Low": 79.0, "Close": 80.0, "Volume": 1000, "ATR": 1.0},
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1001, "ATR": 1.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02"]),
            ),
        }
        universe = pd.DataFrame(
            [
                {"ticker": "A.T", "company_name": "A"},
                {"ticker": "B.T", "company_name": "B"},
            ]
        )
        config = replace(make_pending_order_config(20000.0), maximum_quantity_per_ticker=100)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            side_effect=lambda row, strategy: float(row["Close"]),
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(["A"], result.trades["company_name"].tolist())
        self.assertEqual(1, len(result.trades))
        trade = result.trades.iloc[0]
        self.assertEqual("2006-08-02", trade["entry_date"])
        self.assertEqual("2006-08-02", trade["exit_date"])
        self.assertEqual("TARGET", trade["exit_reason"])
        self.assertEqual(150.0, float(trade["entry_price"]))
        self.assertEqual(153.0, float(trade["exit_price"]))
        self.assertEqual(1, int(trade["holding_sessions"]))
        self.assertEqual(0, result.rejected_due_to_lot)
        self.assertEqual(1, result.rejected_due_to_buying_power)

    def test_zero_open_gap_does_not_force_exit_before_normal_time_exit(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-04")
        prepared_histories = {
            "7203.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000, "ATR": 1.0},
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1001, "ATR": 1.0},
                    {"Open": 0.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1002, "ATR": 1.0},
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1003, "ATR": 1.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02", "2006-08-03", "2006-08-04"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "7203.T", "company_name": "Toyota"},
            ]
        )
        config = replace(make_pending_order_config(30000.0), max_hold_sessions=3)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(1, len(result.trades))
        trade = result.trades.iloc[0]
        self.assertEqual("2006-08-04", trade["exit_date"])
        self.assertEqual("TIME_EXIT", trade["exit_reason"])
        self.assertGreater(float(trade["exit_price"]), 0.0)

    def test_zero_low_and_high_do_not_trigger_intraday_stop_or_target(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-03")
        prepared_histories = {
            "7203.T": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000, "ATR": 1.0},
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1001, "ATR": 1.0},
                    {"Open": 100.0, "High": 0.0, "Low": 0.0, "Close": 100.5, "Volume": 1002, "ATR": 1.0},
                ],
                index=pd.to_datetime(["2006-08-01", "2006-08-02", "2006-08-03"]),
            )
        }
        universe = pd.DataFrame(
            [
                {"ticker": "7203.T", "company_name": "Toyota"},
            ]
        )
        config = replace(make_pending_order_config(30000.0), max_hold_sessions=2)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(1, len(result.trades))
        trade = result.trades.iloc[0]
        self.assertEqual("2006-08-03", trade["exit_date"])
        self.assertEqual("TIME_EXIT", trade["exit_reason"])
        self.assertGreater(float(trade["exit_price"]), 0.0)

    def test_pending_order_does_not_fill_when_next_session_is_outside_membership(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-02")
        prepared_histories = {
            "A.T": make_atr_history_frame(["2006-08-01", "2006-08-02"]),
            "B.T": make_atr_history_frame(["2006-08-01", "2006-08-02"]),
        }
        universe = pd.DataFrame(
            [
                {
                    "ticker": "A.T",
                    "company_name": "Skip",
                    "member_from": "2006-08-01",
                    "member_until": "2006-08-02",
                },
                {
                    "ticker": "B.T",
                    "company_name": "Keep",
                    "member_from": "2006-08-01",
                    "member_until": "",
                },
            ]
        )
        config = make_pending_order_config(20000.0)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name == pd.Timestamp("2006-08-01"),
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(["B.T"], result.trades["ticker"].tolist())
        self.assertEqual(["Keep"], result.trades["company_name"].tolist())

    def test_rejoined_membership_allows_same_ticker_to_trade_in_separate_periods(self) -> None:
        requested_start = pd.Timestamp("2006-08-01")
        requested_end = pd.Timestamp("2006-08-06")
        prepared_histories = {
            "R.T": make_atr_history_frame(
                [
                    "2006-08-01",
                    "2006-08-02",
                    "2006-08-03",
                    "2006-08-04",
                    "2006-08-05",
                    "2006-08-06",
                ]
            )
        }
        universe = pd.DataFrame(
            [
                {
                    "ticker": "R.T",
                    "company_name": "Rejoin",
                    "member_from": "2006-08-01",
                    "member_until": "2006-08-03",
                },
                {
                    "ticker": "R.T",
                    "company_name": "Rejoin",
                    "member_from": "2006-08-05",
                    "member_until": "",
                },
            ]
        )
        config = replace(make_pending_order_config(30000.0), max_hold_sessions=1)

        with patch.object(
            hv,
            "is_entry_signal",
            side_effect=lambda row, strategy: row.name in {pd.Timestamp("2006-08-01"), pd.Timestamp("2006-08-05")},
        ), patch.object(
            hv,
            "signal_score",
            return_value=80.0,
        ):
            result = hv.simulate_validation(prepared_histories, universe, config, requested_start, requested_end)

        self.assertEqual(2, len(result.trades))
        self.assertEqual(["2006-08-02", "2006-08-06"], result.trades["entry_date"].tolist())
        self.assertEqual(["2006-08-02", "2006-08-06"], result.trades["exit_date"].tolist())
        self.assertEqual(["R.T", "R.T"], result.trades["ticker"].tolist())

    def test_history_price_helpers_skip_non_positive_prices(self) -> None:
        frame = pd.DataFrame(
            [
                {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000},
                {"Open": 0.0, "High": 102.0, "Low": 98.0, "Close": 101.0, "Volume": 1001},
                {"Open": -5.0, "High": 103.0, "Low": 97.0, "Close": 0.0, "Volume": 1002},
            ],
            index=pd.to_datetime(["2006-08-01", "2006-08-02", "2006-08-03"]),
        )
        frame.index = pd.DatetimeIndex(frame.index).normalize()

        self.assertEqual(101.0, hv._history_close_at_or_before(frame, pd.Timestamp("2006-08-03")))
        self.assertEqual(101.0, hv._history_open_at_or_before(frame, pd.Timestamp("2006-08-03")))
        self.assertEqual(100.0, hv._history_open_at_or_before(frame, pd.Timestamp("2006-08-01")))

    def test_cached_range_skips_network_when_covered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache_dir = root / "data" / "market_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached = make_history_frame(
                [
                    "2006-08-01",
                    "2006-08-02",
                    "2006-08-03",
                ]
            )
            cached.index.name = "Date"
            cached.to_csv(cache_dir / "7203_T.csv", encoding="utf-8")

            with patch.object(hv.yf, "download", side_effect=AssertionError("network should not be used")):
                report = hv.run_historical_validation_20y(
                    root=root,
                    tickers=["7203.T"],
                    requested_start="2006-08-01",
                    requested_end="2006-08-03",
                    cache_dir=cache_dir,
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                )

            row = report["rows"][0]
            self.assertTrue(row["cache_used"])
            self.assertFalse(row["download_used"])
            self.assertEqual(0, row["network_attempts"])
            self.assertEqual("SUCCESS", row["coverage_status"])

    def test_not_eligible_rows_do_not_make_overall_status_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "data").mkdir(parents=True, exist_ok=True)
            universe_csv = root / "data" / "membership_universe.csv"
            universe_csv.write_text(
                "\n".join(
                    [
                        "name,ticker,member_from,member_until",
                        "Inactive,1111.T,2006-08-10,",
                        "Active,2222.T,2006-08-01,",
                    ]
                ),
                encoding="utf-8",
            )
            config_path = root / "config" / "v7_historical_validation_20y.json"
            config_path.write_text(
                json.dumps(
                    {
                        "historical_validation_20y": make_config(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            frame = make_history_frame(
                [
                    "2006-08-01",
                    "2006-08-02",
                    "2006-08-03",
                    "2006-08-04",
                    "2006-08-05",
                ]
            )

            with patch.object(hv.yf, "download", return_value=frame):
                report = hv.run_historical_validation_20y(
                    root=root,
                    config_path=Path("config/v7_historical_validation_20y.json"),
                    requested_start="2006-08-01",
                    requested_end="2006-08-05",
                    universe_csv=universe_csv,
                    cache_dir=root / "data" / "market_cache",
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2006, 8, 6, 16, 0, tzinfo=JST),
                )

            rows = {row["ticker"]: row for row in report["rows"]}
            self.assertEqual("NOT_ELIGIBLE", rows["1111.T"]["coverage_status"])
            self.assertEqual("SUCCESS", rows["2222.T"]["coverage_status"])
            self.assertEqual("SUCCESS", report["status"])

    def test_static_snapshot_without_membership_columns_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            config_path = root / "v7_historical_validation_20y.json"
            config_path.write_text(
                json.dumps(
                    {
                        "historical_validation_20y": make_config(
                            universe_csv="data/nikkei225.csv",
                            benchmark_enabled=False,
                            enforce_nikkei225=True,
                            expected_ticker_count=225,
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            with patch.object(hv.yf, "download", side_effect=AssertionError("network should not be used")):
                with self.assertRaisesRegex(hv.HistoricalValidationError, "historical member_from/member_until"):
                    hv.run_historical_validation_20y(
                        root=ROOT,
                        config_path=config_path,
                        as_of=datetime(2026, 8, 11, 16, 0, tzinfo=JST),
                    )

    def test_historical_membership_csv_can_exceed_expected_ticker_count(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "data").mkdir(parents=True, exist_ok=True)
            universe_csv = root / "data" / "historical_membership.csv"
            rows = ["name,ticker,member_from,member_until"]
            for index in range(226):
                ticker = f"{1000 + index:04d}.T"
                member_from = "2006-08-10" if index == 0 else "2006-08-01"
                rows.append(f"Company{index},{ticker},{member_from},")
            universe_csv.write_text("\n".join(rows), encoding="utf-8")
            config_path = root / "config" / "v7_historical_validation_20y.json"
            config_path.write_text(
                json.dumps(
                    {
                        "historical_validation_20y": make_config(
                            enforce_nikkei225=True,
                            expected_ticker_count=225,
                            benchmark_enabled=False,
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            frame = make_history_frame(["2006-08-01", "2006-08-02", "2006-08-03"])

            def fake_fetch_ticker_history(*args, **kwargs):
                return hv.FetchOutcome(
                    history=frame.copy(),
                    cache_used=False,
                    download_used=False,
                    network_attempts=0,
                    download_error=None,
                )

            with patch.object(hv, "fetch_ticker_history", side_effect=fake_fetch_ticker_history), patch.object(
                hv,
                "is_entry_signal",
                return_value=False,
            ):
                report = hv.run_historical_validation_20y(
                    root=root,
                    config_path=Path("config/v7_historical_validation_20y.json"),
                    requested_start="2006-08-01",
                    requested_end="2006-08-03",
                    universe_csv=universe_csv,
                    cache_dir=root / "data" / "market_cache",
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                )

            self.assertEqual(226, report["ticker_count"])
            rows = {row["ticker"]: row for row in report["rows"]}
            self.assertEqual("NOT_ELIGIBLE", rows["1000.T"]["coverage_status"])
            self.assertEqual("SUCCESS", rows["1001.T"]["coverage_status"])

    def test_run_writes_outputs_and_verify_passes(self) -> None:
        frame = make_history_frame(
            [
                "2006-08-01",
                "2006-08-02",
                "2006-08-03",
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "reports").mkdir(parents=True, exist_ok=True)
            config_path = root / "config" / "v7_historical_validation_20y.json"
            config_path.write_text(
                json.dumps(
                    {
                        "historical_validation_20y": make_config(),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with patch.object(hv.yf, "download", return_value=frame):
                report = hv.run_historical_validation_20y(
                    root=root,
                    config_path=Path("config/v7_historical_validation_20y.json"),
                    tickers=["1332.T"],
                    cache_dir=root / "data" / "market_cache",
                    output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                    as_of=datetime(2006, 8, 4, 16, 0, tzinfo=JST),
                )

            self.assertEqual(500000.0, float(report["initial_capital_yen"]))
            self.assertEqual(100, int(report["lot_size"]))
            self.assertFalse(bool(report["fractional_shares"]))
            self.assertTrue(report["safety"]["no_rss"])
            self.assertEqual(0, int(report["safety"]["orders_submitted"]))
            self.assertIn("performance", report)
            self.assertIn("output_files", report)
            self.assertTrue(any("survivorship bias" in warning for warning in report.get("warnings", [])))

            output_dir = root / "reports" / "historical_validation_20y"
            summary_path = output_dir / "summary.json"
            report_path = output_dir / "report.txt"
            coverage_path = output_dir / "data_coverage.csv"
            diagnostics_path = output_dir / "diagnostics.csv"
            annual_path = output_dir / "annual_returns.csv"
            monthly_path = output_dir / "monthly_returns.csv"
            trades_path = output_dir / "trades.csv"
            equity_path = output_dir / "equity_curve.csv"

            self.assertTrue(summary_path.is_file())
            self.assertTrue(report_path.is_file())
            self.assertTrue(coverage_path.is_file())
            self.assertTrue(diagnostics_path.is_file())
            self.assertTrue(annual_path.is_file())
            self.assertTrue(monthly_path.is_file())
            self.assertTrue(trades_path.is_file())
            self.assertTrue(equity_path.is_file())

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertIn("performance", summary)
            performance = summary["performance"]
            for key in (
                "final_equity_yen",
                "total_return",
                "CAGR",
                "max_drawdown",
                "profit_factor",
                "win_rate",
                "trade_count",
                "avg_holding",
                "cash_ratio",
                "rejected_due_to_lot",
                "rejected_due_to_buying_power",
            ):
                self.assertIn(key, performance)
            for key, expected_path in (
                ("summary_json", summary_path),
                ("report_text", report_path),
                ("data_coverage_csv", coverage_path),
                ("diagnostics_csv", diagnostics_path),
                ("annual_returns_csv", annual_path),
                ("monthly_returns_csv", monthly_path),
                ("trades_csv", trades_path),
                ("equity_curve_csv", equity_path),
            ):
                self.assertEqual(str(expected_path), summary["output_files"][key])

            report_text = report_path.read_text(encoding="utf-8")
            self.assertIn("Final equity", report_text)
            self.assertIn("Cash ratio", report_text)
            self.assertIn("Annual returns CSV", report_text)
            self.assertIn("Monthly returns CSV", report_text)
            self.assertIn("Trades CSV", report_text)
            self.assertIn("Equity curve CSV", report_text)
            self.assertIn("survivorship bias", report_text)

            ok, errors = hv.verify_historical_validation_outputs(root, Path("config/v7_historical_validation_20y.json"))
            self.assertTrue(ok, msg="; ".join(errors))
            self.assertEqual([], errors)

    def test_fetch_start_date_warmup_and_requested_start_preserved(self) -> None:
        """
        Ensure fetch_ticker_history is called with an earlier fetch_start_date
        including warm-up, while coverage and simulation requested_start remain unchanged.
        """
        requested_start = "2020-01-06"
        requested_end = "2020-02-28"
        expected_fetch = (pd.Timestamp(requested_start) - pd.offsets.BDay(hv.DEFAULT_MINIMUM_HISTORY_SESSIONS + 20)).date()

        captured: dict[str, object] = {}

        def fake_fetch(root, ticker, start_date, end_date, cache_dir=None, as_of=None, allow_network_fetch=True, download_registry=None):
            captured["fetch_start_arg"] = start_date
            dates = pd.bdate_range(start=start_date, end=requested_end).strftime("%Y-%m-%d").tolist()
            frame = make_history_frame(dates)
            return hv.FetchOutcome(history=frame, cache_used=True, download_used=False, network_attempts=0, download_error=None)

        def fake_prepare(histories, config):
            any_df = next(iter(histories.values()))
            captured["prepared_min_index"] = any_df.index.min()
            return histories

        def fake_simulate(prepared, universe, config, requested_start=None, requested_end=None):
            captured["simulate_requested_start"] = requested_start
            return hv.HistoricalValidationResult(trades=pd.DataFrame(), equity_curve=pd.DataFrame(), annual_returns=pd.DataFrame(), monthly_returns=pd.DataFrame())

        with tempfile.TemporaryDirectory() as directory, patch.object(hv, "fetch_ticker_history", side_effect=fake_fetch), patch.object(hv, "prepare_histories", side_effect=fake_prepare), patch.object(hv, "simulate_validation", side_effect=fake_simulate):
            root = Path(directory)
            report = hv.run_historical_validation_20y(
                root=root,
                tickers=["FAKE.T"],
                requested_start=requested_start,
                requested_end=requested_end,
                cache_dir=root / "data" / "market_cache",
                output_csv=root / "reports" / "historical_validation_20y" / "data_coverage.csv",
                as_of=datetime(2020, 2, 28, 16, 0, tzinfo=JST),
            )

        self.assertEqual(expected_fetch, captured.get("fetch_start_arg"))
        self.assertLess(pd.Timestamp(captured.get("prepared_min_index")), pd.Timestamp(requested_start))
        days = len(pd.bdate_range(start=pd.Timestamp(expected_fetch), end=pd.Timestamp(requested_start)))
        self.assertGreaterEqual(days, hv.DEFAULT_MINIMUM_HISTORY_SESSIONS)
        self.assertEqual(requested_start, report.get("requested_start"))
        self.assertEqual(pd.Timestamp(requested_start).date(), captured.get("simulate_requested_start"))


if __name__ == "__main__":
    unittest.main()



# PHOENIX RISK V1 REGRESSION TESTS

def test_risk_v1_default_capital_rules():
    import phoenix_core.historical_validation_20y as hv

    config = hv.HistoricalValidationConfig()

    assert config.risk_per_trade_pct == 0.01
    assert config.max_portfolio_risk_pct == 1.0
    assert config.max_position_pct == 0.30
    assert config.max_position_hard_pct == 0.30
    assert config.max_total_invested_pct == 0.95
    assert config.minimum_cash_reserve_pct == 0.0


def test_risk_v1_optional_soft_position_cap_can_allow_one_standard_lot():
    import phoenix_core.historical_validation_20y as hv

    config = hv.HistoricalValidationConfig(
        max_position_pct=0.30,
        max_position_hard_pct=0.50,
    )

    quantity = hv.calculate_shares(
        current_equity=500_000.0,
        available_cash=500_000.0,
        entry_price=1_800.0,
        stop_price=1_750.0,
        current_exposure=0.0,
        current_portfolio_risk_yen=0.0,
        config=config,
    )

    # 100 shares cost 180,000 yen = 36% of equity.
    # This exceeds the normal 30% soft cap but remains below the 50% hard cap.
    assert quantity == 100


def test_risk_v1_hard_position_cap_rejects_one_lot_above_thirty_percent():
    import phoenix_core.historical_validation_20y as hv

    config = hv.HistoricalValidationConfig()

    quantity = hv.calculate_shares(
        current_equity=500_000.0,
        available_cash=500_000.0,
        entry_price=1_800.0,
        stop_price=1_750.0,
        current_exposure=0.0,
        current_portfolio_risk_yen=0.0,
        config=config,
    )

    # 100 shares cost 180,000 yen = 36% of equity, above the canonical 30% hard cap.
    assert quantity == 0


def test_risk_v1_portfolio_risk_cap_blocks_new_position():
    import phoenix_core.historical_validation_20y as hv

    config = hv.HistoricalValidationConfig(
        max_portfolio_risk_pct=0.04,
    )

    quantity = hv.calculate_shares(
        current_equity=500_000.0,
        available_cash=500_000.0,
        entry_price=1_000.0,
        stop_price=950.0,
        current_exposure=0.0,
        current_portfolio_risk_yen=18_000.0,
        config=config,
    )

    reason = hv._classify_share_rejection_reason(
        current_equity=500_000.0,
        available_cash=500_000.0,
        entry_price=1_000.0,
        stop_price=950.0,
        current_exposure=0.0,
        current_portfolio_risk_yen=18_000.0,
        config=config,
        d1=False,
    )

    # 4% of 500,000 = 20,000 yen.
    # Only 2,000 yen of risk capacity remains; one 100-share lot needs 5,000.
    assert quantity == 0
    assert reason == "REJECT_PORTFOLIO_RISK"


def test_risk_v1_fixed_share_ceiling_is_not_a_strategy_constraint():
    import phoenix_core.historical_validation_20y as hv

    config = hv.HistoricalValidationConfig(
        maximum_quantity_per_ticker=1,
    )

    quantity = hv.calculate_shares(
        current_equity=500_000.0,
        available_cash=500_000.0,
        entry_price=1_000.0,
        stop_price=975.0,
        current_exposure=0.0,
        current_portfolio_risk_yen=0.0,
        config=config,
    )

    # maximum_quantity_per_ticker remains parseable for backwards
    # compatibility but does not constrain PHOENIX risk-v1 sizing.
    assert quantity >= 100
