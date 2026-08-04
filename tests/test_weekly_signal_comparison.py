from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import pandas as pd

import weekly_signal_comparison as wsc


REPORT_COLUMNS = [
    "銘柄",
    "ticker",
    "基準日",
    "価格",
    "前日比%",
    "出来高倍率",
    "MA5",
    "MA25",
    "MA75",
    "RSI",
    "MACD判定",
    "PHOENIX_SCORE",
    "理由",
]

JUDGEMENT_COLUMNS = [
    "銘柄",
    "ticker",
    "価格",
    "前日比%",
    "出来高倍率",
    "RSI",
    "MACD判定",
    "PHOENIX_SCORE",
    "AI判断",
    "AI判断点",
]


def _report_row(
    name: str,
    ticker: str,
    basis_date: str,
    price: float,
    change: float,
    volume: float,
    rsi: float,
    macd: str,
    phoenix: float,
) -> dict[str, object]:
    return {
        "銘柄": name,
        "ticker": ticker,
        "基準日": basis_date,
        "価格": price,
        "前日比%": change,
        "出来高倍率": volume,
        "MA5": price,
        "MA25": price - 1,
        "MA75": price - 2,
        "RSI": rsi,
        "MACD判定": macd,
        "PHOENIX_SCORE": phoenix,
        "理由": "test",
    }


def _judgement_row(
    name: str,
    ticker: str,
    price: float,
    change: float,
    volume: float,
    rsi: float,
    macd: str,
    phoenix: float,
    ai_judgement: str,
    ai_points: float,
) -> dict[str, object]:
    return {
        "銘柄": name,
        "ticker": ticker,
        "価格": price,
        "前日比%": change,
        "出来高倍率": volume,
        "RSI": rsi,
        "MACD判定": macd,
        "PHOENIX_SCORE": phoenix,
        "AI判断": ai_judgement,
        "AI判断点": ai_points,
    }


def _snapshot(
    *,
    report_date: str,
    basis_date: str,
    rows: list[dict[str, object]],
    judgement_rows: list[dict[str, object]],
) -> dict[str, object]:
    report_df = pd.DataFrame(rows, columns=REPORT_COLUMNS)
    judgement_df = pd.DataFrame(judgement_rows, columns=JUDGEMENT_COLUMNS)
    counts = Counter(judgement_df["AI判断"].astype(str))
    active_counts = Counter(
        judgement_df.loc[
            judgement_df["AI判断"].isin(wsc.ACTIVE_JUDGEMENTS),
            "AI判断",
        ].astype(str)
    )
    active_tickers = set(
        judgement_df.loc[
            judgement_df["AI判断"].isin(wsc.ACTIVE_JUDGEMENTS),
            "ticker",
        ].astype(str)
    )
    return {
        "report_date": report_date,
        "report_file": f"report_{report_date.replace('-', '')}.csv",
        "basis_date": basis_date,
        "report_df": report_df,
        "judgement_df": judgement_df,
        "all_counts": {label: int(counts.get(label, 0)) for label in wsc.ALL_KNOWN_JUDGEMENTS},
        "active_counts": {label: int(active_counts.get(label, 0)) for label in wsc.ACTIVE_JUDGEMENTS},
        "active_total": int(sum(active_counts.values())),
        "optimized_signal_count": 0,
        "learning_profile_path": "reports/learning_profile.json",
        "learning_profile_generated_at": "2026-07-19 11:11:32",
        "active_tickers": active_tickers,
    }


class WeeklySignalComparisonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd()
        self.temp_root = self.repo_root / "TEMP" / "weekly_signal_comparison_tests"
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def test_signal_classification_and_metric_deltas(self) -> None:
        source_snapshot = _snapshot(
            report_date="2026-07-31",
            basis_date="2026-07-31",
            rows=[
                _report_row("新規株", "1111.T", "2026-07-31", 100.0, 1.0, 1.0, 40.0, "BUY", 60.0),
                _report_row("継続株", "2222.T", "2026-07-31", 110.0, 2.0, 1.2, 41.0, "BUY", 65.0),
                _report_row("格上げ株", "3333.T", "2026-07-31", 120.0, 3.0, 1.4, 42.0, "BUY", 70.0),
                _report_row("格下げ株", "4444.T", "2026-07-31", 130.0, 4.0, 1.6, 43.0, "BUY", 75.0),
                _report_row("除外株", "5555.T", "2026-07-31", 140.0, 5.0, 1.8, 44.0, "BUY", 80.0),
            ],
            judgement_rows=[
                _judgement_row("新規株", "1111.T", 100.0, 1.0, 1.0, 40.0, "BUY", 60.0, "見送り", 20.0),
                _judgement_row("継続株", "2222.T", 110.0, 2.0, 1.2, 41.0, "BUY", 65.0, "買い候補", 70.0),
                _judgement_row("格上げ株", "3333.T", 120.0, 3.0, 1.4, 42.0, "BUY", 70.0, "押し目待ち", 68.0),
                _judgement_row("格下げ株", "4444.T", 130.0, 4.0, 1.6, 43.0, "BUY", 75.0, "買い候補", 72.0),
                _judgement_row("除外株", "5555.T", 140.0, 5.0, 1.8, 44.0, "BUY", 80.0, "買い候補", 74.0),
            ],
        )
        target_snapshot = _snapshot(
            report_date="2026-08-04",
            basis_date="2026-08-03",
            rows=[
                _report_row("新規株", "1111.T", "2026-08-03", 111.5, 2.0, 2.0, 45.0, "SELL", 75.0),
                _report_row("継続株", "2222.T", "2026-08-03", 115.0, 2.5, 1.4, 41.5, "BUY", 66.0),
                _report_row("格上げ株", "3333.T", "2026-08-03", 128.0, 3.5, 1.9, 43.5, "BUY", 78.0),
                _report_row("格下げ株", "4444.T", "2026-08-03", 123.0, 3.0, 1.5, 42.5, "BUY", 69.0),
                _report_row("除外株", "5555.T", "2026-08-03", 141.0, 5.2, 1.7, 44.5, "BUY", 82.0),
            ],
            judgement_rows=[
                _judgement_row("新規株", "1111.T", 111.5, 2.0, 2.0, 45.0, "SELL", 75.0, "買い候補", 80.0),
                _judgement_row("継続株", "2222.T", 115.0, 2.5, 1.4, 41.5, "BUY", 66.0, "買い候補", 71.0),
                _judgement_row("格上げ株", "3333.T", 128.0, 3.5, 1.9, 43.5, "BUY", 78.0, "買い候補", 83.0),
                _judgement_row("格下げ株", "4444.T", 123.0, 3.0, 1.5, 42.5, "BUY", 69.0, "押し目待ち", 66.0),
                _judgement_row("除外株", "5555.T", 141.0, 5.2, 1.7, 44.5, "BUY", 82.0, "見送り", 30.0),
            ],
        )

        result = wsc._compare_signal_snapshots(source_snapshot, target_snapshot)

        self.assertEqual({"new": 1, "continued": 1, "upgraded": 1, "downgraded": 1, "excluded": 1}, result["signal_change_counts"])
        self.assertEqual(["1111.T"], [row["ticker"] for row in result["signal_changes"]["new"]])
        self.assertEqual(["2222.T"], [row["ticker"] for row in result["signal_changes"]["continued"]])
        self.assertEqual(["3333.T"], [row["ticker"] for row in result["signal_changes"]["upgraded"]])
        self.assertEqual(["4444.T"], [row["ticker"] for row in result["signal_changes"]["downgraded"]])
        self.assertEqual(["5555.T"], [row["ticker"] for row in result["signal_changes"]["excluded"]])

        upgraded = next(row for row in result["common_ticker_changes"] if row["ticker"] == "3333.T")
        self.assertEqual("upgraded", upgraded["change_type"])
        self.assertEqual(8.0, upgraded["price_delta"])
        self.assertEqual(15.0, upgraded["ai_points_delta"])
        self.assertEqual(8.0, upgraded["phoenix_score_delta"])
        self.assertEqual(0.5, upgraded["volume_ratio_delta"])
        self.assertEqual(1.5, upgraded["rsi_delta"])
        self.assertEqual("BUY -> BUY", upgraded["macd_change"])

    def test_adaptive_parameter_diff_detects_changed_fields(self) -> None:
        source_snapshot = {
            "path": "source.json",
            "version": "PHOENIX v1",
            "generated_at": "2026-07-01 09:00:00",
            "decision": "PASS",
            "action": "UPDATED",
            "confidence": 98.0,
            "reason": "source",
            "active_parameters": {
                "rsi_min": 45.0,
                "rsi_max": 70.0,
                "stop_atr_multiplier": 1.0,
                "target_r_multiplier": 2.5,
                "ma_short": 5,
                "ma_mid": 20,
                "ma_long": 60,
                "signal_score_threshold": 70.0,
                "max_hold_days": 10,
            },
        }
        target_snapshot = {
            "path": "target.json",
            "version": "PHOENIX v1",
            "generated_at": "2026-08-01 09:00:00",
            "decision": "PASS",
            "action": "UPDATED",
            "confidence": 99.5,
            "reason": "target",
            "active_parameters": {
                "rsi_min": 47.0,
                "rsi_max": 70.0,
                "stop_atr_multiplier": 1.0,
                "target_r_multiplier": 3.0,
                "ma_short": 5,
                "ma_mid": 20,
                "ma_long": 60,
                "signal_score_threshold": 75.0,
                "max_hold_days": 12,
            },
        }

        result = wsc._compare_adaptive_snapshots(source_snapshot, target_snapshot)
        changed_fields = {row["field"] for row in result["changes"]}

        self.assertIn("confidence", changed_fields)
        self.assertIn("reason", changed_fields)
        self.assertIn("rsi_min", changed_fields)
        self.assertIn("target_r_multiplier", changed_fields)
        self.assertIn("signal_score_threshold", changed_fields)
        self.assertIn("max_hold_days", changed_fields)

    def test_compare_weekly_signals_and_save_outputs(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            output_dir = Path(temp_dir) / "output"
            result = wsc.compare_weekly_signals("20260731", "20260804")
            paths = wsc.save_weekly_signal_comparison(result, output_dir=output_dir)

            self.assertEqual("READY", result["status"])
            self.assertEqual("PAPER", result["safety"]["broker_mode"])
            self.assertEqual(0, result["safety"]["orders_submitted"])
            self.assertFalse(result["safety"]["external_connections"])
            self.assertEqual(0, result["safety"]["notification_sent"])
            self.assertTrue(paths["json"].is_file())
            self.assertTrue(paths["txt"].is_file())
            self.assertTrue(paths["csv"].is_file())
            self.assertFalse(list(output_dir.glob("*.tmp")))

            json_data = json.loads(paths["json"].read_text(encoding="utf-8"))
            self.assertEqual("READY", json_data["status"])
            self.assertEqual("report_20260731.csv", json_data["source"]["report_file"])
            self.assertEqual("report_20260804.csv", json_data["target"]["report_file"])
            self.assertIn("common_ticker_changes", json_data)
            self.assertGreater(len(json_data["common_ticker_changes"]), 0)

            text = paths["txt"].read_text(encoding="utf-8")
            self.assertIn("PHOENIX WEEKLY SIGNAL COMPARISON", text)
            self.assertIn("共通銘柄の変化", text)
            self.assertIn("Adaptive Parameterの変化", text)
            self.assertIn("売買推奨ではありません", text)

            csv_df = pd.read_csv(paths["csv"], encoding="utf-8-sig")
            self.assertIn("row_type", csv_df.columns)
            self.assertIn("ticker", csv_df.columns)
            self.assertGreater(len(csv_df), 0)

    def test_find_latest_comparable_report_date_chooses_latest_prior_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            report_dir = Path(temp_dir)
            for filename in (
                "report_20260731.csv",
                "report_20260801.csv",
                "report_20260804.csv",
            ):
                shutil.copy2(self.repo_root / "reports" / filename, report_dir / filename)

            source_date = wsc.find_latest_comparable_report_date("20260804", report_dir=report_dir)

            self.assertIsNotNone(source_date)
            self.assertEqual("2026-08-01", source_date.isoformat())

    def test_run_latest_weekly_signal_comparison_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            report_dir = Path(temp_dir) / "reports"
            output_dir = Path(temp_dir) / "output"
            report_dir.mkdir(parents=True, exist_ok=True)
            for filename in (
                "report_20260731.csv",
                "report_20260804.csv",
            ):
                shutil.copy2(self.repo_root / "reports" / filename, report_dir / filename)

            result = wsc.run_latest_weekly_signal_comparison(
                "20260804",
                report_dir=report_dir,
                output_dir=output_dir,
            )

            self.assertEqual("READY", result["status"])
            self.assertEqual("2026-07-31", result["selection"]["source_report_date"])
            self.assertEqual("2026-08-04", result["selection"]["target_report_date"])
            self.assertEqual("PAPER", result["safety"]["broker_mode"])
            self.assertEqual(0, result["safety"]["orders_submitted"])
            self.assertEqual(0, result["safety"]["notification_sent"])
            self.assertTrue((output_dir / "weekly_signal_comparison_20260731_20260804.json").is_file())
            self.assertTrue((output_dir / "weekly_signal_comparison_20260731_20260804.txt").is_file())
            self.assertTrue((output_dir / "weekly_signal_comparison_20260731_20260804.csv").is_file())
            self.assertFalse(list(output_dir.glob("*.tmp")))

    def test_run_latest_weekly_signal_comparison_skips_without_prior_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            report_dir = Path(temp_dir) / "reports"
            output_dir = Path(temp_dir) / "output"
            report_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(
                self.repo_root / "reports" / "report_20260804.csv",
                report_dir / "report_20260804.csv",
            )

            result = wsc.run_latest_weekly_signal_comparison(
                "20260804",
                report_dir=report_dir,
                output_dir=output_dir,
            )

            self.assertEqual("SKIPPED", result["status"])
            self.assertIsNone(result["selection"]["source_report_date"])
            self.assertEqual("2026-08-04", result["selection"]["target_report_date"])
            self.assertIn("No comparable prior report exists", result["reason"])
            self.assertFalse(output_dir.exists() and any(output_dir.iterdir()))

    def test_same_date_blocks(self) -> None:
        with self.assertRaises(wsc.ComparisonError) as cm:
            wsc.compare_weekly_signals("20260731", "20260731")
        self.assertEqual("BLOCKED", cm.exception.status)

    def test_missing_report_file_blocks(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            report_dir = Path(temp_dir)
            source = pd.read_csv(self.repo_root / "reports" / "report_20260731.csv")
            source.to_csv(report_dir / "report_20260731.csv", index=False, encoding="utf-8-sig")

            with self.assertRaises(wsc.ComparisonError) as cm:
                wsc.compare_weekly_signals(
                    "20260731",
                    "20260804",
                    report_dir=report_dir,
                )

            self.assertEqual("BLOCKED", cm.exception.status)
            self.assertIn("不存在", str(cm.exception))

    def test_required_column_missing_blocks(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            report_dir = Path(temp_dir)
            source = pd.read_csv(self.repo_root / "reports" / "report_20260731.csv")
            source = source.drop(columns=["PHOENIX_SCORE"])
            source.to_csv(report_dir / "report_20260731.csv", index=False, encoding="utf-8-sig")

            target = pd.read_csv(self.repo_root / "reports" / "report_20260804.csv")
            target.to_csv(report_dir / "report_20260804.csv", index=False, encoding="utf-8-sig")

            with self.assertRaises(wsc.ComparisonError) as cm:
                wsc.compare_weekly_signals(
                    "20260731",
                    "20260804",
                    report_dir=report_dir,
                )

            self.assertEqual("BLOCKED", cm.exception.status)
            self.assertIn("必要な列", str(cm.exception))

    def test_duplicate_ticker_blocks(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            report_dir = Path(temp_dir)
            source = pd.read_csv(self.repo_root / "reports" / "report_20260731.csv")
            duplicate_row = source.iloc[[0]].copy()
            source = pd.concat([source, duplicate_row], ignore_index=True)
            source.to_csv(report_dir / "report_20260731.csv", index=False, encoding="utf-8-sig")

            target = pd.read_csv(self.repo_root / "reports" / "report_20260804.csv")
            target.to_csv(report_dir / "report_20260804.csv", index=False, encoding="utf-8-sig")

            with self.assertRaises(wsc.ComparisonError) as cm:
                wsc.compare_weekly_signals(
                    "20260731",
                    "20260804",
                    report_dir=report_dir,
                )

            self.assertEqual("BLOCKED", cm.exception.status)
            self.assertIn("重複ticker", str(cm.exception))

    def test_invalid_numeric_blocks(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.temp_root) as temp_dir:
            report_dir = Path(temp_dir)
            source = pd.read_csv(self.repo_root / "reports" / "report_20260731.csv")
            source["価格"] = source["価格"].astype(object)
            source.loc[0, "価格"] = "not-a-number"
            source.to_csv(report_dir / "report_20260731.csv", index=False, encoding="utf-8-sig")

            target = pd.read_csv(self.repo_root / "reports" / "report_20260804.csv")
            target.to_csv(report_dir / "report_20260804.csv", index=False, encoding="utf-8-sig")

            with self.assertRaises(wsc.ComparisonError) as cm:
                wsc.compare_weekly_signals(
                    "20260731",
                    "20260804",
                    report_dir=report_dir,
                )

            self.assertEqual("BLOCKED", cm.exception.status)
            self.assertIn("不正数値", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
