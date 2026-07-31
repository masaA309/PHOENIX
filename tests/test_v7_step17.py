from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

from phoenix_core.historical_replay import (
    EVIDENCE_KIND,
    HISTORICAL_REPLAY_LOCK,
    HistoricalReplayError,
    HistoricalReplayLockError,
    REQUIRED_OUTPUT_PATHS,
    REQUIRED_PROTECTED_FILES,
    StrategyConfig,
    add_causal_indicators,
    assess_manifest,
    build_walk_forward_folds,
    load_price_file,
    records_available_as_of,
    risk_state_for_session,
    run_historical_replay,
    signal_at,
    verify_historical_report,
)
import historical_replay_v7 as historical_cli
import phoenix_core.historical_replay as historical_module
from phoenix_core.readiness_gate import build_readiness_report
from phoenix_core.run_guard import SingleInstanceLock


def create_file_alias(alias: Path, target: Path) -> None:
    try:
        alias.symlink_to(target)
    except OSError:
        os.link(target, alias)


def verified_manifest() -> dict:
    datasets = {}
    for name in (
        "price_history",
        "historical_universe",
        "corporate_actions",
        "fundamentals",
        "shikiho",
    ):
        datasets[name] = {
            "required": True,
            "available": True,
            "used_by_replay": True,
            "source": "TEST",
            "path": f"data/{name}.csv",
            "available_at_field": None if name == "price_history" else "available_at",
            "point_in_time_verified": True,
        }
    datasets["shikiho"]["license_confirmed"] = True
    return {
        "schema_version": 1,
        "timezone": "Asia/Tokyo",
        "datasets": datasets,
    }


def synthetic_prices(rows: int = 400) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-04", periods=rows)
    close = [100 + index * 0.08 + 2.5 * math.sin(index / 3.0) for index in range(rows)]
    return pd.DataFrame(
        {
            "Date": dates.strftime("%Y-%m-%d"),
            "Open": close,
            "High": [value * 1.015 for value in close],
            "Low": [value * 0.985 for value in close],
            "Close": close,
            "Volume": [1000 + (index % 7) * 100 for index in range(rows)],
        }
    )


def readiness_inputs() -> tuple[dict, dict, dict, dict]:
    performance = {
        "paper_evidence": {
            "integrity_status": "VERIFIED",
            "eligibility_rule": "dry_run == false",
            "distinct_run_days": 20,
            "success_rate": 1.0,
            "status_counts": {"FAILED": 0},
            "totals": {"filled": 3},
            "risk_halt_count": 0,
        }
    }
    return (
        performance,
        {"status": "SUCCESS", "dry_run": False},
        {"status": "READY"},
        {"action_counts": {"REVIEW": 0}},
    )


class PointInTimeContractStep17Test(unittest.TestCase):
    def test_publication_after_decision_is_excluded(self) -> None:
        records = [
            {"id": "old", "available_at": "2025-01-10T10:00:00+09:00"},
            {"id": "future", "available_at": "2025-01-10T16:00:00+09:00"},
        ]
        selected = records_available_as_of(
            records,
            datetime.fromisoformat("2025-01-10T15:30:00+09:00"),
        )
        self.assertEqual(["old"], [item["id"] for item in selected])

    def test_naive_publication_time_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            records_available_as_of(
                [{"available_at": "2025-01-10T10:00:00"}],
                datetime.fromisoformat("2025-01-10T15:30:00+09:00"),
            )

    def test_incomplete_manifest_is_not_ready(self) -> None:
        manifest = verified_manifest()
        manifest["datasets"]["fundamentals"]["available"] = False
        blockers = assess_manifest(manifest)
        self.assertTrue(any("fundamentals" in value for value in blockers))

    def test_verified_manifest_has_no_contract_blocker(self) -> None:
        self.assertEqual(
            [],
            assess_manifest(
                verified_manifest(),
                implemented_datasets=(
                    "price_history",
                    "historical_universe",
                    "corporate_actions",
                    "fundamentals",
                    "shikiho",
                ),
            ),
        )


class HistoricalPriceValidationStep17Test(unittest.TestCase):
    def test_duplicate_session_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prices.csv"
            frame = synthetic_prices(20)
            frame.loc[1, "Date"] = frame.loc[0, "Date"]
            frame.to_csv(path, index=False)
            with self.assertRaises(HistoricalReplayError):
                load_price_file(path)

    def test_ohlc_contradiction_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "prices.csv"
            frame = synthetic_prices(20)
            frame.loc[5, "High"] = frame.loc[5, "Low"] - 1
            frame.to_csv(path, index=False)
            with self.assertRaises(HistoricalReplayError):
                load_price_file(path)

    def test_future_rows_do_not_change_current_signal(self) -> None:
        raw = synthetic_prices(150).set_index(pd.to_datetime(synthetic_prices(150)["Date"]))
        raw = raw[["Open", "High", "Low", "Close", "Volume"]]
        strategy = StrategyConfig(signal_score_threshold=0)
        first = add_causal_indicators(raw, strategy)
        decision_date = first.index[120]
        first_signal = signal_at("1111.T", first, decision_date, strategy, 100)
        poisoned = raw.copy()
        poisoned.loc[poisoned.index > decision_date, ["Open", "High", "Low", "Close"]] *= 100
        second = add_causal_indicators(poisoned, strategy)
        second_signal = signal_at("1111.T", second, decision_date, strategy, 100)
        self.assertEqual(first_signal, second_signal)


class WalkForwardBoundaryStep17Test(unittest.TestCase):
    def test_folds_are_non_overlapping_and_train_precedes_test(self) -> None:
        dates = pd.bdate_range("2020-01-01", periods=160)
        folds = build_walk_forward_folds(dates, 100, 20, 20)
        self.assertEqual(3, len(folds))
        previous_end = None
        for fold in folds:
            self.assertLess(fold["train_end"], fold["test_start"])
            if previous_end is not None:
                self.assertLess(previous_end, fold["test_start"])
            previous_end = fold["test_end"]

    def test_overlapping_oos_windows_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_walk_forward_folds(pd.bdate_range("2020-01-01", periods=160), 100, 20, 10)


class HistoricalEvidenceIsolationStep17Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "config").mkdir()
        (self.root / "data").mkdir()
        (self.root / "state").mkdir()
        (self.root / "reports").mkdir()
        synthetic_prices().to_csv(self.root / "data/1111_T.csv", index=False)
        (self.root / "data/manifest.json").write_text(
            json.dumps(verified_manifest()), encoding="utf-8"
        )
        self.risk_values = {
            "max_daily_loss_pct": 0.03,
            "max_drawdown_pct": 0.10,
            "max_positions": 5,
            "max_total_invested_pct": 0.80,
            "max_single_position_pct": 0.30,
            "max_orders_per_run": 3,
            "max_consecutive_losses": 3,
            "minimum_cash_reserve_pct": 0.10,
            "block_on_broker_health_failure": True,
        }
        pipeline = {
            "broker": {"initial_cash_yen": 300000, "commission_rate": 0.0},
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
            },
            "risk": self.risk_values,
        }
        (self.root / "config/pipeline.json").write_text(json.dumps(pipeline), encoding="utf-8")
        self.protected = self.root / "state/v7_paper_broker.json"
        self.protected.write_text('{"unchanged":true}\n', encoding="utf-8")
        config = {
            "historical_replay": {
                "enabled": True,
                "manifest": "data/manifest.json",
                "price_glob": "data/*_T.csv",
                "active_pipeline_config": "config/pipeline.json",
                "train_sessions": 100,
                "test_sessions": 50,
                "step_sessions": 50,
                "minimum_history_sessions": 80,
                "validation_protocol": {
                    "replay_scope": "SURROGATE_TECHNICAL_BASELINE",
                    "parameter_policy": "FROZEN_TRACKED_CONFIG",
                    "sealed_holdout_status": "NOT_ESTABLISHED",
                },
                "strategy": {
                    "rsi_min": 0,
                    "rsi_max": 100,
                    "signal_score_threshold": 0,
                    "max_hold_sessions": 5,
                },
                "execution_assumptions": {
                    "entry_slippage_rate": 0.0005,
                    "exit_slippage_rate": 0.0005,
                    "maximum_volume_participation_rate": 0.01,
                    "daily_price_limit_model": "NOT_IMPLEMENTED",
                },
                "gate": {
                    "minimum_folds": 5,
                    "minimum_oos_sessions": 250,
                    "minimum_simulated_trades": 30,
                    "minimum_profit_factor": 1.2,
                    "minimum_successful_fold_rate": 0.6,
                    "maximum_drawdown_pct": 10,
                    "maximum_risk_halt_days": 0,
                    "maximum_risk_limit_violations": 0,
                },
                "protected_files": list(REQUIRED_PROTECTED_FILES),
                **REQUIRED_OUTPUT_PATHS,
            }
        }
        self.config_path = self.root / "config/replay.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_replay_is_deterministic_and_does_not_credit_paper_evidence(self) -> None:
        before = self.protected.read_bytes()
        first = run_historical_replay(self.root, self.config_path)
        second = run_historical_replay(self.root, self.config_path)
        self.assertEqual(first["evidence_sha256"], second["evidence_sha256"])
        self.assertEqual(0, first["paper_days_credited"])
        self.assertEqual(0, first["audited_fills_credited"])
        self.assertEqual(0, first["external_orders_submitted"])
        self.assertFalse(first["live_trading_enabled"])
        self.assertEqual("NOT_READY", first["gate_status"])
        self.assertEqual("SURROGATE_TECHNICAL_BASELINE", first["replay_scope"])
        self.assertEqual("NOT_ESTABLISHED", first["sealed_holdout_status"])
        self.assertEqual("READY", first["state_integrity_status"])
        self.assertEqual("READY", first["post_save_integrity_status"])
        self.assertEqual(before, self.protected.read_bytes())
        trades = pd.read_csv(
            self.root / REQUIRED_OUTPUT_PATHS["trades_csv"], encoding="utf-8-sig"
        )
        for _, trade in trades.iterrows():
            self.assertLess(trade["signal_date"], trade["entry_date"])

    def test_report_and_detail_artifacts_are_reverified(self) -> None:
        report = run_historical_replay(self.root, self.config_path)
        valid, errors = verify_historical_report(self.root, report, self.config_path)
        self.assertTrue(valid, errors)
        report["gate_status"] = "READY"
        valid, errors = verify_historical_report(self.root, report, self.config_path)
        self.assertFalse(valid)
        self.assertTrue(any("NOT_READY" in value for value in errors))

    def test_modified_trade_artifact_is_rejected(self) -> None:
        report = run_historical_replay(self.root, self.config_path)
        with (self.root / REQUIRED_OUTPUT_PATHS["trades_csv"]).open(
            "a", encoding="utf-8"
        ) as handle:
            handle.write("tampered\n")
        valid, errors = verify_historical_report(self.root, report, self.config_path)
        self.assertFalse(valid)
        self.assertTrue(any("artifact" in value for value in errors))

    def test_modified_replay_config_makes_report_stale(self) -> None:
        report = run_historical_replay(self.root, self.config_path)
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["historical_replay"]["strategy"]["signal_score_threshold"] = 1
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        valid, errors = verify_historical_report(self.root, report, self.config_path)
        self.assertFalse(valid)
        self.assertTrue(any("config_sha256" in value or "control inputs" in value for value in errors))

    def test_risk_state_resets_on_each_historical_session(self) -> None:
        first = risk_state_for_session(pd.Timestamp("2025-01-06"), 300000)
        first.halted = True
        first.halt_reason = "test"
        second = risk_state_for_session(pd.Timestamp("2025-01-07"), 290000)
        self.assertFalse(second.halted)
        self.assertEqual("", second.halt_reason)
        self.assertEqual(290000, second.peak_equity_yen)

    def test_active_risk_limits_are_used_without_override(self) -> None:
        report = run_historical_replay(self.root, self.config_path)
        self.assertEqual(self.risk_values, report["active_risk_limits"])
        self.assertTrue(report["risk_limits_unchanged"])

    def test_historical_risk_override_is_rejected(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["historical_replay"]["risk_overrides"] = {"max_drawdown_pct": 1.0}
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_historical_replay(self.root, self.config_path)

    def test_gate_safety_floor_cannot_be_lowered(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["historical_replay"]["gate"]["minimum_profit_factor"] = 1.0
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_historical_replay(self.root, self.config_path)

    def test_output_path_cannot_target_operational_state(self) -> None:
        before = self.protected.read_bytes()
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["historical_replay"]["report_json"] = "state/v7_paper_broker.json"
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_historical_replay(self.root, self.config_path)
        self.assertEqual(before, self.protected.read_bytes())

    def test_required_protected_file_cannot_be_removed(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["historical_replay"]["protected_files"].remove(
            "state/v7_risk_state.json"
        )
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_historical_replay(self.root, self.config_path)

    def test_duplicate_protected_path_is_rejected(self) -> None:
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        config["historical_replay"]["protected_files"].append(
            "state/v7_paper_broker.json"
        )
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_historical_replay(self.root, self.config_path)

    def test_missing_price_session_fails_closed(self) -> None:
        second = synthetic_prices()
        second = second.drop(index=120)
        second.to_csv(self.root / "data/2222_T.csv", index=False)
        with self.assertRaisesRegex(HistoricalReplayError, "missing price sessions"):
            run_historical_replay(self.root, self.config_path)

    def test_missing_training_session_fails_closed(self) -> None:
        second = synthetic_prices()
        second = second.drop(index=50)
        second.to_csv(self.root / "data/2222_T.csv", index=False)
        with self.assertRaisesRegex(HistoricalReplayError, "missing training price"):
            run_historical_replay(self.root, self.config_path)

    def test_concurrent_replay_is_rejected(self) -> None:
        lock = SingleInstanceLock(self.root / HISTORICAL_REPLAY_LOCK)
        self.assertTrue(lock.acquire())
        try:
            with self.assertRaisesRegex(HistoricalReplayError, "already running"):
                run_historical_replay(self.root, self.config_path)
        finally:
            lock.release()

    def test_lock_is_released_after_replay_error(self) -> None:
        original = self.config_path.read_text(encoding="utf-8")
        config = json.loads(original)
        config["historical_replay"]["risk_overrides"] = {"max_drawdown_pct": 1.0}
        self.config_path.write_text(json.dumps(config), encoding="utf-8")
        with self.assertRaises(ValueError):
            run_historical_replay(self.root, self.config_path)
        self.assertFalse((self.root / HISTORICAL_REPLAY_LOCK).exists())
        self.config_path.write_text(original, encoding="utf-8")
        report = run_historical_replay(self.root, self.config_path)
        self.assertEqual("READY", report["post_save_integrity_status"])

    def test_lock_contention_does_not_overwrite_cli_report(self) -> None:
        failure_report = self.root / REQUIRED_OUTPUT_PATHS["report_json"]
        failure_report.write_text("sentinel\n", encoding="utf-8")
        with (
            mock.patch.object(historical_cli, "ROOT_DIR", self.root),
            mock.patch.object(historical_cli, "DEFAULT_CONFIG", self.config_path),
            mock.patch.object(historical_cli, "FAILURE_REPORT", failure_report),
            mock.patch.object(historical_cli, "configure_console"),
            mock.patch.object(
                historical_cli,
                "run_historical_replay",
                side_effect=HistoricalReplayLockError("busy"),
            ),
            mock.patch.object(sys, "argv", ["historical_replay_v7.py"]),
        ):
            self.assertEqual(2, historical_cli.main())
        self.assertEqual("sentinel\n", failure_report.read_text(encoding="utf-8"))

    def test_post_save_status_is_bound_to_artifact_commit(self) -> None:
        report = run_historical_replay(self.root, self.config_path)
        report["post_save_integrity_status"] = "PENDING"
        valid, errors = verify_historical_report(self.root, report, self.config_path)
        self.assertFalse(valid)
        self.assertTrue(any("artifact commit" in value for value in errors))

    def test_readiness_fields_are_bound_to_artifact_commit(self) -> None:
        report = run_historical_replay(self.root, self.config_path)
        report["execution_status"] = "FAILED"
        valid, errors = verify_historical_report(self.root, report, self.config_path)
        self.assertFalse(valid)
        self.assertTrue(any("artifact commit" in value for value in errors))

    def test_final_integrity_failure_commits_invalid_marker(self) -> None:
        original_capture = historical_module.capture_files
        calls = 0

        def capture_with_final_change(root: Path, paths: list[str]):
            nonlocal calls
            calls += 1
            result = original_capture(root, paths)
            if calls == 9 and result:
                first = next(iter(result))
                result[first] = dict(result[first])
                result[first]["sha256"] = "changed"
            return result

        with mock.patch.object(
            historical_module, "capture_files", side_effect=capture_with_final_change
        ):
            with self.assertRaisesRegex(HistoricalReplayError, "Post-save integrity"):
                run_historical_replay(self.root, self.config_path)
        marker = json.loads(
            (self.root / REQUIRED_OUTPUT_PATHS["report_json"]).read_text(encoding="utf-8")
        )
        self.assertEqual("FAILED", marker["gate_status"])
        self.assertEqual("FAILED", marker["post_save_integrity_status"])

    def test_output_file_alias_is_rejected_without_skip(self) -> None:
        target = self.root / "reports/v7_operations_report.json"
        target.write_text("sentinel\n", encoding="utf-8")
        output = self.root / REQUIRED_OUTPUT_PATHS["report_json"]
        create_file_alias(output, target)
        with self.assertRaises(ValueError):
            run_historical_replay(self.root, self.config_path)
        self.assertEqual("sentinel\n", target.read_text(encoding="utf-8"))

    def test_price_file_alias_is_rejected_without_skip(self) -> None:
        target = self.root / "data/1111_T.csv"
        alias = self.root / "data/2222_T.csv"
        create_file_alias(alias, target)
        with self.assertRaisesRegex(HistoricalReplayError, "aliases are forbidden"):
            run_historical_replay(self.root, self.config_path)


class ReadinessHistoricalGateStep17Test(unittest.TestCase):
    def test_forged_historical_evidence_does_not_pass(self) -> None:
        historical = {
            "gate_status": "READY",
            "execution_status": "COMPLETED",
            "evidence_kind": EVIDENCE_KIND,
            "data_contract_status": "READY",
            "state_integrity_status": "READY",
            "post_save_integrity_status": "READY",
            "historical_evidence_verified": False,
            "replay_scope": "PRODUCTION_DECISION_PIPELINE",
            "sealed_holdout_status": "READY",
            "execution_model_status": "READY",
            "risk_limits_unchanged": True,
            "input_files_unchanged": True,
            "paper_days_credited": 20,
            "audited_fills_credited": 3,
            "external_orders_submitted": 0,
            "live_trading_enabled": False,
            "automatic_promotion": False,
            "evidence_sha256": "a" * 64,
        }
        report = build_readiness_report(
            *readiness_inputs(),
            {"minimum_paper_days": 20, "minimum_filled_orders": 3},
            lifecycle={"status": "READY", "state_persisted": True, "audited_fill_count": 3},
            historical=historical,
        )
        item = next(value for value in report["checks"] if value["name"] == "historical_replay_gate")
        self.assertFalse(item["passed"])

    def test_separate_valid_historical_evidence_adds_one_passed_check(self) -> None:
        historical = {
            "gate_status": "READY",
            "execution_status": "COMPLETED",
            "evidence_kind": EVIDENCE_KIND,
            "evidence_sha256": "a" * 64,
            "data_contract_status": "READY",
            "risk_limits_unchanged": True,
            "input_files_unchanged": True,
            "state_integrity_status": "READY",
            "post_save_integrity_status": "READY",
            "historical_evidence_verified": True,
            "replay_scope": "PRODUCTION_DECISION_PIPELINE",
            "sealed_holdout_status": "READY",
            "execution_model_status": "READY",
            "paper_days_credited": 0,
            "audited_fills_credited": 0,
            "external_orders_submitted": 0,
            "live_trading_enabled": False,
            "automatic_promotion": False,
        }
        report = build_readiness_report(
            *readiness_inputs(),
            {"minimum_paper_days": 20, "minimum_filled_orders": 3},
            lifecycle={"status": "READY", "state_persisted": True, "audited_fill_count": 3},
            historical=historical,
        )
        self.assertEqual("READY", report["status"])


if __name__ == "__main__":
    unittest.main()
