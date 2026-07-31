from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from phoenix_core.broker import PaperBroker
from phoenix_core.virtual_rss_paper import (
    CONTRACT_ID,
    JST,
    QUOTE_SOURCE,
    VirtualQuote,
    VirtualRssError,
    build_eligibility_evidence,
    build_notification_preview,
    check_quote_environment,
    import_eligibility,
    initialize_virtual_ledger,
    load_eligibility,
    load_state,
    fetch_yfinance_quotes,
    modeled_fill,
    quote_readiness,
    run_virtual_rss_paper,
    _event_hash,
    _preview_text,
    _sha256,
    _state_hash,
)
from phoenix_core.rss_shadow_contract import verify_rss_shadow_report
import virtual_rss_entry_v7
import run_phoenix


REPOSITORY = Path(__file__).resolve().parents[1]
POLICY_BYTES = (REPOSITORY / "config/v7_virtual_rss_policy.json").read_bytes()
POLICY = json.loads(POLICY_BYTES.decode("utf-8"))
POLICY_HASH = hashlib.sha256(POLICY_BYTES).hexdigest()


def quote(
    ticker: str = "9501.T",
    price: float = 500.0,
    event_at: datetime | None = None,
    received_at: datetime | None = None,
    *,
    bid: float | None = None,
    ask: float | None = None,
) -> VirtualQuote:
    event = event_at or datetime(2026, 7, 23, 10, 5, tzinfo=JST)
    return VirtualQuote(
        ticker=ticker,
        price=price,
        event_at=event,
        received_at=received_at or event,
        bid=bid,
        ask=ask,
    )


class Step21Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for name in ("config", "reports", "state", "runtime/v7_virtual_rss", "execution"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / "config/v7_virtual_rss_policy.json").write_bytes(POLICY_BYTES)
        self.now = datetime(2026, 7, 23, 10, 6, tzinfo=JST)
        self._write_paper()
        self._write_candidates(generated_at="2026-07-23T09:00:00+09:00")
        direct = {
            "candidate_input": {
                "enabled": True,
                "path": "reports/trade_signals.csv",
                "decision_column": "Trade判定",
                "execution_price_column": "押し目価格",
                "executable_values": ["BUY"],
                "known_values": ["BUY", "WATCH", "SKIP"],
                "fallback": False,
            },
            "position_sizing": {
                "risk_per_trade_pct": 0.01,
                "max_position_pct": 0.3,
                "max_total_invested_pct": 0.8,
                "minimum_cash_reserve_pct": 0.1,
                "fallback_stop_distance_pct": 0.03,
                "lot_size": 100,
                "maximum_quantity_per_ticker": 1000,
                "allow_pyramiding": False,
                "commission_buffer_pct": 0.001,
            },
        }
        (self.root / "config/v7_direct_pipeline_config.json").write_text(
            json.dumps(direct, ensure_ascii=False), encoding="utf-8"
        )
        self.config = {
            "virtual_rss_paper": {
                "enabled": True,
                "advisory_only": True,
                "virtual_only": True,
                "orders_allowed": False,
                "external_notifications_allowed": False,
                "automatic_funding": False,
                "policy_file": "config/v7_virtual_rss_policy.json",
                "policy_sha256": POLICY_HASH,
                "direct_pipeline_config": "config/v7_direct_pipeline_config.json",
                "runtime_root": "runtime/v7_virtual_rss",
                "source_paper_state": "state/v7_paper_broker.json",
                "state_file": "state/v7_virtual_rss_paper.json",
                "lock_file": "state/v7_virtual_rss_paper.lock",
                "kabumini_eligibility_file": "state/rakuten_kabumini_eligibility.json",
                "maximum_candidate_age_hours": 96,
                "maximum_price_deviation_from_signal_pct": 0.20,
                "report_json": "reports/v7_virtual_rss_paper.json",
                "report_text": "reports/v7_virtual_rss_paper.txt",
                "notification_preview_json": "reports/v7_virtual_trade_notification_preview.json",
                "notification_preview_text": "reports/v7_virtual_trade_notification_preview.txt",
            }
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_paper(self, positions: dict | None = None) -> None:
        payload = {
            "state_version": 1,
            "broker_name": "PAPER",
            "updated_at": "2026-07-23T08:00:00.000000",
            "initial_cash_yen": 300000.0,
            "cash_yen": 300000.0,
            "commission_rate": 0.0,
            "realized_pnl_yen": 0.0,
            "positions": positions or {},
            "processed_client_order_ids": [],
        }
        (self.root / "state/v7_paper_broker.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def _write_candidates(
        self,
        *,
        ticker: str = "9501.T",
        price: float = 600.0,
        stop: float = 490.0,
        target: float = 650.0,
        generated_at: str,
    ) -> None:
        text = (
            "銘柄,ticker,Trade判定,押し目価格,損切価格,利確価格,AI判断点,生成日時\n"
            f"テスト銘柄,{ticker},BUY,{price},{stop},{target},90,{generated_at}\n"
        )
        (self.root / "reports/trade_signals.csv").write_text(text, encoding="utf-8")

    def _write_eligibility(self, ticker: str = "9501.T") -> None:
        csv_path = self.root / "runtime/v7_virtual_rss/kabumini.csv"
        csv_path.write_text(
            "ticker,opening_buy_enabled,realtime_buy_enabled\n"
            f"{ticker},1,1\n",
            encoding="utf-8",
        )
        import_eligibility(self.root, self.config, csv_path, now=self.now)


class VirtualCostStep21Test(unittest.TestCase):
    def test_kabumini_buy_uses_spread_slippage_round_up_and_zero_fee(self) -> None:
        result = modeled_fill(
            quote(price=5600, bid=5400, ask=5600),
            "BUY",
            "RAKUTEN_KABU_MINI_SIM",
            POLICY,
        )
        self.assertEqual(5616.0, result["filled_price_yen"])
        self.assertEqual(0.0, result["commission_yen"])
        self.assertEqual(22.0, result["product_spread_bps"])
        self.assertEqual(5.0, result["slippage_reserve_bps"])
        self.assertTrue(result["book_price_measured"])

    def test_kabumini_sell_rounds_down(self) -> None:
        result = modeled_fill(
            quote(price=5500, bid=5400, ask=5600),
            "SELL",
            "RAKUTEN_KABU_MINI_SIM",
            POLICY,
        )
        self.assertEqual(5385.0, result["filled_price_yen"])
        self.assertEqual(0.0, result["commission_yen"])

    def test_standard_unit_uses_unverified_fee_reserve(self) -> None:
        result = modeled_fill(quote(), "BUY", "TSE_STANDARD_UNIT_SIM", POLICY)
        self.assertEqual(1070.0, result["commission_yen"])
        self.assertEqual(0.0, result["product_spread_bps"])
        self.assertFalse(result["book_price_measured"])

    def test_invalid_quote_numbers_and_crossed_book_fail_closed(self) -> None:
        for value in (True, 0, -1, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(VirtualRssError):
                    quote(price=value).validate()
        with self.assertRaises(VirtualRssError):
            quote(bid=501, ask=500).validate()
        with self.assertRaises(VirtualRssError):
            quote(price=499, bid=500, ask=501).validate()
        with self.assertRaises(VirtualRssError):
            quote(price=502, bid=500, ask=501).validate()


class QuoteReadinessStep21Test(unittest.TestCase):
    def test_quote_environment_materializes_verified_local_ca_bundle(self) -> None:
        environment = check_quote_environment()
        self.assertEqual("READY", environment["status"])
        self.assertEqual("READY", environment["code"])
        self.assertTrue(environment["tls_verification_enabled"])
        self.assertEqual("LOCAL_MATERIALIZED_COPY", environment["ca_bundle_mode"])
        self.assertEqual(64, len(environment["ca_bundle_sha256"]))

    def test_missing_ca_bundle_blocks_before_yfinance_download(self) -> None:
        import yfinance as yf

        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.pem"
            with (
                patch.dict(
                    os.environ,
                    {
                        "SSL_CERT_FILE": "",
                        "CURL_CA_BUNDLE": "",
                        "REQUESTS_CA_BUNDLE": "",
                    },
                ),
                patch("certifi.where", return_value=str(missing)),
                patch.object(yf, "download") as download,
            ):
                quotes, errors, lineage = fetch_yfinance_quotes(
                    ["9501.T"],
                    received_at=datetime(2026, 7, 23, 10, 6, tzinfo=JST),
                )
        self.assertEqual({}, quotes)
        self.assertEqual(["TLS_CA_BUNDLE_MISSING"], errors)
        self.assertEqual("FAILED", lineage["environment"]["status"])
        self.assertEqual("REINSTALL_CERTIFI_ACTIVE_VENV", lineage["environment"]["remediation"])
        download.assert_not_called()

    def test_provider_failure_returns_complete_fail_closed_lineage(self) -> None:
        import yfinance as yf

        with patch.object(yf, "download", side_effect=RuntimeError("offline")):
            quotes, errors, lineage = fetch_yfinance_quotes(
                ["9501.T"],
                received_at=datetime(2026, 7, 23, 10, 6, tzinfo=JST),
            )
        self.assertEqual({}, quotes)
        self.assertEqual(["YFINANCE_REQUEST_FAILED:RuntimeError"], errors)
        self.assertEqual("FAILED", lineage["status"])
        self.assertEqual(64, len(lineage["snapshot_sha256"]))
        self.assertFalse(lineage["fallback_used"])
        self.assertEqual(0, lineage["post_requests"])
        self.assertEqual("READY", lineage["environment"]["status"])

    def test_curl_77_is_classified_without_leaking_raw_error(self) -> None:
        import yfinance as yf

        secret = "https://example.invalid/?token=never-report-this"
        with patch.object(
            yf,
            "download",
            side_effect=RuntimeError(f"curl: (77) certificate verify locations {secret}"),
        ):
            quotes, errors, lineage = fetch_yfinance_quotes(
                ["9501.T"],
                received_at=datetime(2026, 7, 23, 10, 6, tzinfo=JST),
            )
        self.assertEqual({}, quotes)
        self.assertEqual(["TLS_CA_BUNDLE_UNREADABLE"], errors)
        self.assertEqual("TLS_CA_BUNDLE_UNREADABLE", lineage["environment"]["code"])
        self.assertNotIn(secret, json.dumps(lineage))

    def test_current_intraday_quote_is_fill_ready(self) -> None:
        current = datetime(2026, 7, 23, 10, 6, tzinfo=JST)
        status, reasons = quote_readiness(quote(), current, POLICY, mini=False)
        self.assertEqual("FILL_READY", status)
        self.assertEqual([], reasons)

    def test_stale_future_outside_and_naive_quotes_are_blocked(self) -> None:
        current = datetime(2026, 7, 23, 16, 0, tzinfo=JST)
        status, reasons = quote_readiness(
            quote(event_at=current - timedelta(hours=1), received_at=current),
            current,
            POLICY,
            mini=True,
        )
        self.assertEqual("MARK_ONLY", status)
        self.assertIn("STALE_QUOTE", reasons)
        self.assertIn("OUTSIDE_FILL_SESSION", reasons)
        with self.assertRaises(VirtualRssError):
            quote(event_at=datetime(2026, 7, 23, 10, 0)).validate()

    def test_future_receipt_and_excessive_measured_spread_are_mark_only(self) -> None:
        current = datetime(2026, 7, 23, 10, 6, tzinfo=JST)
        future_receipt = quote(received_at=current + timedelta(minutes=1))
        status, reasons = quote_readiness(future_receipt, current, POLICY, mini=False)
        self.assertEqual("MARK_ONLY", status)
        self.assertIn("FUTURE_RECEIPT_TIME", reasons)
        wide = quote(price=500, bid=480, ask=520)
        status, reasons = quote_readiness(wide, current, POLICY, mini=False)
        self.assertEqual("MARK_ONLY", status)
        self.assertIn("MEASURED_SPREAD_TOO_WIDE", reasons)

    def test_preopen_and_lunch_quote_events_cannot_fill_after_session_resumes(self) -> None:
        morning = datetime(2026, 7, 23, 9, 5, tzinfo=JST)
        preopen = quote(
            event_at=datetime(2026, 7, 23, 8, 59, 30, tzinfo=JST),
            received_at=morning,
        )
        status, reasons = quote_readiness(preopen, morning, POLICY, mini=False)
        self.assertEqual("MARK_ONLY", status)
        self.assertIn("QUOTE_EVENT_OUTSIDE_FILL_SESSION", reasons)
        afternoon = datetime(2026, 7, 23, 12, 31, tzinfo=JST)
        lunch = quote(
            event_at=datetime(2026, 7, 23, 12, 29, 30, tzinfo=JST),
            received_at=afternoon,
        )
        status, reasons = quote_readiness(lunch, afternoon, POLICY, mini=True)
        self.assertEqual("MARK_ONLY", status)
        self.assertIn("QUOTE_EVENT_OUTSIDE_FILL_SESSION", reasons)


class EligibilityStep21Test(Step21Fixture):
    def test_import_and_load_reviewed_eligibility(self) -> None:
        self._write_eligibility()
        loaded, status = load_eligibility(
            self.root / "state/rakuten_kabumini_eligibility.json", self.now, POLICY
        )
        self.assertEqual("VERIFIED", status)
        self.assertTrue(loaded["9501.T"]["realtime_buy_enabled"])

    def test_missing_and_stale_evidence_fail_closed(self) -> None:
        loaded, status = load_eligibility(
            self.root / "state/missing.json", self.now, POLICY
        )
        self.assertEqual({}, loaded)
        self.assertEqual("MISSING", status)
        csv_path = self.root / "runtime/v7_virtual_rss/old.csv"
        csv_path.write_text(
            "ticker,opening_buy_enabled,realtime_buy_enabled\n9501.T,1,1\n",
            encoding="utf-8",
        )
        evidence = build_eligibility_evidence(
            csv_path, self.now - timedelta(days=8),
            source_url="RAKUTEN_SUPER_SCREENER_MANUAL_EXPORT",
        )
        path = self.root / "state/rakuten_kabumini_eligibility.json"
        path.write_text(json.dumps(evidence), encoding="utf-8")
        loaded, status = load_eligibility(path, self.now, POLICY)
        self.assertEqual({}, loaded)
        self.assertEqual("STALE", status)

    def test_tampered_evidence_is_rejected(self) -> None:
        self._write_eligibility()
        path = self.root / "state/rakuten_kabumini_eligibility.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["tickers"]["9501.T"]["realtime_buy_enabled"] = False
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_eligibility(path, self.now, POLICY)

    def test_new_import_cannot_overwrite_corrupt_existing_evidence(self) -> None:
        self._write_eligibility()
        destination = self.root / "state/rakuten_kabumini_eligibility.json"
        original = json.loads(destination.read_text(encoding="utf-8"))
        original["tickers"]["9501.T"]["realtime_buy_enabled"] = False
        destination.write_text(json.dumps(original), encoding="utf-8")
        csv_path = self.root / "runtime/v7_virtual_rss/replacement.csv"
        csv_path.write_text(
            "ticker,opening_buy_enabled,realtime_buy_enabled\n1605.T,1,1\n",
            encoding="utf-8",
        )
        before = destination.read_bytes()
        with self.assertRaises(VirtualRssError):
            import_eligibility(
                self.root, self.config, csv_path, now=self.now + timedelta(minutes=1)
            )
        self.assertEqual(before, destination.read_bytes())


class VirtualLedgerStep21Test(Step21Fixture):
    def test_policy_hash_path_escape_and_risk_relaxation_fail_closed(self) -> None:
        bad_hash = json.loads(json.dumps(self.config))
        bad_hash["virtual_rss_paper"]["policy_sha256"] = "0" * 64
        with self.assertRaises(VirtualRssError):
            initialize_virtual_ledger(self.root, bad_hash, now=self.now)

        escaped = json.loads(json.dumps(self.config))
        escaped["virtual_rss_paper"]["state_file"] = "../outside.json"
        with self.assertRaises(VirtualRssError):
            initialize_virtual_ledger(self.root, escaped, now=self.now)

        real_rss_alias = json.loads(json.dumps(self.config))
        real_rss_alias["virtual_rss_paper"]["report_json"] = (
            "reports/v7_rss_shadow.json"
        )
        with self.assertRaises(VirtualRssError):
            initialize_virtual_ledger(self.root, real_rss_alias, now=self.now)

        relaxed_policy = json.loads(POLICY_BYTES.decode("utf-8"))
        relaxed_policy["quote_feed"]["maximum_quote_age_seconds"] = 3600
        relaxed_bytes = json.dumps(relaxed_policy).encode("utf-8")
        (self.root / "config/v7_virtual_rss_policy.json").write_bytes(relaxed_bytes)
        relaxed_config = json.loads(json.dumps(self.config))
        relaxed_config["virtual_rss_paper"]["policy_sha256"] = hashlib.sha256(
            relaxed_bytes
        ).hexdigest()
        with self.assertRaises(VirtualRssError):
            initialize_virtual_ledger(self.root, relaxed_config, now=self.now)
        (self.root / "config/v7_virtual_rss_policy.json").write_bytes(POLICY_BYTES)

        initialize_virtual_ledger(self.root, self.config, now=self.now)
        direct_path = self.root / "config/v7_direct_pipeline_config.json"
        direct = json.loads(direct_path.read_text(encoding="utf-8"))
        direct["position_sizing"]["risk_per_trade_pct"] = 0.02
        direct_path.write_text(json.dumps(direct, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            run_virtual_rss_paper(
                self.root, self.config, persist=False,
                quotes={"9501.T": quote()}, now=self.now,
            )

    def test_lock_contention_fails_without_deleting_foreign_lock(self) -> None:
        lock = self.root / "state/v7_virtual_rss_paper.lock"
        lock.write_text("foreign", encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            initialize_virtual_ledger(self.root, self.config, now=self.now)
        self.assertEqual("foreign", lock.read_text(encoding="utf-8"))

    def test_initialization_clones_cash_positions_and_source_hash(self) -> None:
        self._write_paper({
            "1605.T": {"quantity": 100, "average_price": 1000.0, "market_price": 1100.0}
        })
        state = initialize_virtual_ledger(self.root, self.config, now=self.now)
        self.assertEqual(300000.0, state["cash_yen"])
        self.assertIn("1605.T|BASELINE_CANONICAL_PAPER", state["positions"])
        self.assertEqual(0, state["paper_days_credited"])
        self.assertFalse(state["eligible_for_real_rss_gate"])
        with self.assertRaises(VirtualRssError):
            initialize_virtual_ledger(self.root, self.config, now=self.now)

    def test_initialization_rejects_source_change_during_read(self) -> None:
        from phoenix_core import virtual_rss_paper as module

        with patch.object(
            module,
            "_file_sha256",
            side_effect=["1" * 64, "2" * 64],
        ):
            with self.assertRaises(VirtualRssError):
                initialize_virtual_ledger(self.root, self.config, now=self.now)
        self.assertFalse((self.root / "state/v7_virtual_rss_paper.json").exists())

    def test_valid_v2_source_is_accepted_and_inconsistent_v2_is_rejected(self) -> None:
        paper_path = self.root / "state/v7_paper_broker.json"
        broker = PaperBroker(
            initial_cash_yen=300000,
            commission_rate=0.0,
            state_file=paper_path,
        )
        self.assertTrue(broker.initialize_economics_baseline())
        checked = datetime.now(JST) + timedelta(seconds=3)
        state = initialize_virtual_ledger(self.root, self.config, now=checked)
        self.assertEqual(2, state["source_paper_state_version"])

        (self.root / "state/v7_virtual_rss_paper.json").unlink()
        corrupt = json.loads(paper_path.read_text(encoding="utf-8"))
        corrupt["cash_yen"] -= 1
        paper_path.write_text(json.dumps(corrupt), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            initialize_virtual_ledger(
                self.root, self.config, now=checked + timedelta(seconds=1)
            )

    def test_uninitialized_paper_run_is_not_ready_and_never_creates_ledger(self) -> None:
        report = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        self.assertEqual("NOT_READY", report["status"])
        self.assertEqual("NOT_INITIALIZED_NO_STATE_WRITE", report["run_effect"])
        self.assertIn("INITIALIZE_BEFORE_PAPER_RUN", report["blockers"])
        self.assertFalse((self.root / "state/v7_virtual_rss_paper.json").exists())

    def test_legacy_v1_paper_is_baseline_only_and_gets_no_fill_credit(self) -> None:
        path = self.root / "state/v7_paper_broker.json"
        paper = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(paper), encoding="utf-8")
        state = initialize_virtual_ledger(self.root, self.config, now=self.now)
        self.assertEqual(1, state["source_paper_state_version"])
        self.assertEqual(
            "LEGACY_NAIVE_ASSUMED_JST_BASELINE_ONLY",
            state["source_paper_timestamp_status"],
        )
        self.assertEqual([], state["fills"])
        self.assertEqual(0, state["paper_days_credited"])

    def test_state_tamper_is_rejected_not_repaired(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        path = self.root / "state/v7_virtual_rss_paper.json"
        before = path.read_bytes()
        value = json.loads(before)
        value["external_orders_submitted"] = 1
        path.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_state(path)
        self.assertEqual(1, json.loads(path.read_text())["external_orders_submitted"])

    def test_dry_run_never_changes_virtual_or_canonical_state(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        virtual = self.root / "state/v7_virtual_rss_paper.json"
        paper = self.root / "state/v7_paper_broker.json"
        before = (virtual.read_bytes(), paper.read_bytes())
        report = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=False,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        self.assertIn(report["status"], ("SIMULATION_READY", "MARK_ONLY"))
        self.assertEqual(before, (virtual.read_bytes(), paper.read_bytes()))
        self.assertEqual(0, report["external_orders_submitted"])
        self.assertEqual(0, report["external_notifications_sent"])
        notification_path = self.root / "reports/v7_virtual_trade_notification_preview.txt"
        self.assertTrue(notification_path.is_file())
        notification_bytes = notification_path.read_bytes()
        self.assertEqual(
            report["notification_preview"]["body_sha256"],
            hashlib.sha256(notification_bytes).hexdigest(),
        )

    def test_report_write_failure_cannot_advance_ledger(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        state_path = self.root / "state/v7_virtual_rss_paper.json"
        before = state_path.read_bytes()
        from phoenix_core import virtual_rss_paper as module

        real_atomic_write = module.atomic_write

        def fail_text_report(path: Path, content: str) -> None:
            if path.name == "v7_virtual_rss_paper.txt":
                raise OSError("simulated report failure")
            real_atomic_write(path, content)

        with patch.object(module, "atomic_write", side_effect=fail_text_report):
            with self.assertRaises(OSError):
                run_virtual_rss_paper(
                    self.root,
                    self.config,
                    persist=True,
                    quotes={"9501.T": quote()},
                    now=self.now,
                )
        self.assertEqual(before, state_path.read_bytes())

    def test_failed_quote_universe_never_advances_paper_ledger(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        state_path = self.root / "state/v7_virtual_rss_paper.json"
        before = state_path.read_bytes()
        report = run_virtual_rss_paper(
            self.root, self.config, persist=True, quotes={}, now=self.now
        )
        self.assertEqual("NOT_READY", report["status"])
        self.assertIn("QUOTE_FAILURE_NO_LEDGER_ADVANCE", report["blockers"])
        self.assertEqual(before, state_path.read_bytes())

    def test_ca_preflight_failure_never_advances_paper_ledger(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        state_path = self.root / "state/v7_virtual_rss_paper.json"
        before = state_path.read_bytes()
        from phoenix_core import virtual_rss_paper as module

        environment = {
            "status": "FAILED",
            "code": "TLS_CA_BUNDLE_MISSING",
            "tls_verification_enabled": True,
            "ca_bundle_mode": "UNAVAILABLE",
            "ca_bundle_sha256": "",
            "remediation": "REINSTALL_CERTIFI_ACTIVE_VENV",
        }
        with patch.object(module, "prepare_quote_environment", return_value=(environment, None)):
            report = run_virtual_rss_paper(
                self.root, self.config, persist=True, now=self.now
            )
        self.assertEqual("NOT_READY", report["status"])
        self.assertEqual("QUOTE_FAILURE_NO_STATE_WRITE", report["run_effect"])
        self.assertIn("TLS_CA_BUNDLE_MISSING", report["blockers"])
        self.assertEqual(before, state_path.read_bytes())
        self.assertEqual(0, report["external_orders_submitted"])
        self.assertEqual(0, report["external_notifications_sent"])

    def test_partial_quote_universe_never_advances_paper_ledger(self) -> None:
        self._write_paper({
            "1605.T": {
                "quantity": 100,
                "average_price": 1000.0,
                "market_price": 1100.0,
            }
        })
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        state_path = self.root / "state/v7_virtual_rss_paper.json"
        before = state_path.read_bytes()
        report = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        self.assertEqual("NOT_READY", report["status"])
        self.assertIn("INCOMPLETE_QUOTE_UNIVERSE", report["blockers"])
        self.assertEqual(before, state_path.read_bytes())

    def test_paper_run_records_one_isolated_standard_unit_fill(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        report = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        self.assertEqual(1, len(report["fills"]))
        fill = report["fills"][0]
        self.assertEqual("TSE_STANDARD_UNIT_SIM", fill["route"])
        self.assertEqual(100, fill["quantity"])
        self.assertEqual(1070.0, fill["commission_yen"])
        state = load_state(self.root / "state/v7_virtual_rss_paper.json")
        self.assertEqual(1, len(state["fills"]))
        self.assertEqual(0, state["paper_days_credited"])
        self.assertEqual(0, state["external_orders_submitted"])
        self.assertEqual(
            state["state_sha256"], report["ledger_commit"]["expected_state_sha256"]
        )

    def test_paper_run_records_replayable_kabumini_fill_with_zero_fee(self) -> None:
        self._write_candidates(
            ticker="1605.T",
            price=4000,
            stop=3400,
            target=4200,
            generated_at="2026-07-23T09:00:00+09:00",
        )
        self._write_eligibility("1605.T")
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        report = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"1605.T": quote(ticker="1605.T", price=3500)},
            now=self.now,
        )
        self.assertEqual(1, len(report["fills"]))
        fill = report["fills"][0]
        self.assertEqual("RAKUTEN_KABU_MINI_SIM", fill["route"])
        self.assertTrue(1 <= fill["quantity"] <= 99)
        self.assertEqual(0.0, fill["commission_yen"])
        state = load_state(self.root / "state/v7_virtual_rss_paper.json")
        self.assertEqual(fill["event_id"], state["fills"][0]["event_id"])

    def test_rehashed_event_with_invalid_quote_lineage_is_rejected(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        path = self.root / "state/v7_virtual_rss_paper.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        event = state["fills"][0]
        event["quote"]["event_at"] = "2026-07-23T08:59:30+09:00"
        event["quote"]["received_at"] = "2026-07-23T10:06:00+09:00"
        event["quote_snapshot_sha256"] = _sha256(event["quote"])
        event["event_id"] = _sha256({
            "run_id": event["run_id"],
            "ticker": event["ticker"],
            "route": event["route"],
            "side": event["side"],
            "quantity": event["quantity"],
            "quote_snapshot_sha256": event["quote_snapshot_sha256"],
            "policy_sha256": event["policy_sha256"],
            "candidate_limit_yen": event["candidate_limit_yen"],
        })
        event["event_sha256"] = _event_hash(event)
        state["last_event_sha256"] = event["event_sha256"]
        state["state_sha256"] = _state_hash(state)
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_state(path)

    def test_rehashed_event_with_unreproducible_sizing_is_rejected(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        path = self.root / "state/v7_virtual_rss_paper.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        event = state["fills"][0]
        event["decision_lineage"]["sizing_policy_snapshot"][
            "max_position_pct"
        ] = 0.10
        event["event_sha256"] = _event_hash(event)
        state["last_event_sha256"] = event["event_sha256"]
        state["state_sha256"] = _state_hash(state)
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_state(path)

    def test_rehashed_target_change_cannot_escape_raw_candidate_snapshot(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        path = self.root / "state/v7_virtual_rss_paper.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        event = state["fills"][0]
        event["decision_lineage"]["eligible_candidate_rows"][0]["利確価格"] = 9999
        event["target_price_yen"] = 9999.0
        position = state["positions"]["9501.T|TSE_STANDARD_UNIT_SIM"]
        position["target_price_yen"] = 9999.0
        event["event_sha256"] = _event_hash(event)
        state["last_event_sha256"] = event["event_sha256"]
        state["state_sha256"] = _state_hash(state)
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_state(path)

    def test_rehashed_lower_rank_selection_is_rejected(self) -> None:
        (self.root / "reports/trade_signals.csv").write_text(
            "銘柄,ticker,Trade判定,押し目価格,損切価格,利確価格,AI判断点,生成日時\n"
            "テストA,9501.T,BUY,600,490,650,90,2026-07-23T09:00:00+09:00\n"
            "テストB,5406.T,BUY,600,490,650,80,2026-07-23T09:00:00+09:00\n",
            encoding="utf-8",
        )
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={
                "9501.T": quote(),
                "5406.T": quote(ticker="5406.T"),
            },
            now=self.now,
        )
        path = self.root / "state/v7_virtual_rss_paper.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        event = state["fills"][0]
        decision = event["decision_lineage"]
        old_run_id = event["run_id"]
        raw_text = bytes.fromhex(decision["candidate_input_hex"]).decode("utf-8-sig")
        raw_text = raw_text.replace(
            "テストB,5406.T,BUY,600,490,650,80,",
            "テストB,5406.T,BUY,600,490,650,99,",
        )
        input_bytes = raw_text.encode("utf-8")
        decision["candidate_input_hex"] = input_bytes.hex()
        decision["candidate_input_sha256"] = hashlib.sha256(input_bytes).hexdigest()
        from phoenix_core import virtual_rss_paper as module

        candidate_frame, candidate_rows = module._candidate_rows_from_input_snapshot(
            decision["candidate_input_hex"], decision["candidate_input_sha256"]
        )
        decision["eligible_candidate_rows"] = candidate_rows
        decision["eligible_candidates_sha256"] = module.candidate_execution_sha256(
            candidate_frame
        )
        quote_hash = _sha256(decision["run_quote_universe"])
        new_run_id = _sha256({
            "contract": CONTRACT_ID,
            "trading_date": "2026-07-23",
            "candidate_sha256": decision["eligible_candidates_sha256"],
            "quote_snapshot_sha256": quote_hash,
            "policy_sha256": event["policy_sha256"],
        })
        event["run_id"] = new_run_id
        event["event_id"] = _sha256({
            "run_id": new_run_id,
            "ticker": event["ticker"],
            "route": event["route"],
            "side": event["side"],
            "quantity": event["quantity"],
            "quote_snapshot_sha256": event["quote_snapshot_sha256"],
            "policy_sha256": event["policy_sha256"],
            "candidate_limit_yen": event["candidate_limit_yen"],
        })
        event["event_sha256"] = _event_hash(event)
        state["processed_run_ids"] = [
            new_run_id if value == old_run_id else value
            for value in state["processed_run_ids"]
        ]
        state["last_event_sha256"] = event["event_sha256"]
        state["state_sha256"] = _state_hash(state)
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_state(path)

    def test_rehashed_kabumini_fill_cannot_forge_eligibility_hash(self) -> None:
        self._write_candidates(
            ticker="1605.T",
            price=4000,
            stop=3400,
            target=4200,
            generated_at="2026-07-23T09:00:00+09:00",
        )
        self._write_eligibility("1605.T")
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"1605.T": quote(ticker="1605.T", price=3500)},
            now=self.now,
        )
        path = self.root / "state/v7_virtual_rss_paper.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        event = state["fills"][0]
        event["decision_lineage"]["eligibility_evidence_sha256"] = "f" * 64
        event["event_sha256"] = _event_hash(event)
        state["last_event_sha256"] = event["event_sha256"]
        state["state_sha256"] = _state_hash(state)
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_state(path)

    def test_same_day_second_run_cannot_add_another_buy(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        first = run_virtual_rss_paper(
            self.root, self.config, persist=True,
            quotes={"9501.T": quote()}, now=self.now,
        )
        self.assertEqual(1, len(first["fills"]))
        self._write_candidates(
            ticker="5406.T", price=600, stop=490,
            generated_at="2026-07-23T09:00:00+09:00",
        )
        second_quote = quote(
            ticker="5406.T",
            price=499.0,
            event_at=self.now + timedelta(minutes=5),
            received_at=self.now + timedelta(minutes=5),
        )
        second = run_virtual_rss_paper(
            self.root, self.config, persist=True,
            quotes={
                "5406.T": second_quote,
                "9501.T": quote(
                    price=500.0,
                    event_at=self.now + timedelta(minutes=5),
                    received_at=self.now + timedelta(minutes=5),
                ),
            },
            now=self.now + timedelta(minutes=5),
        )
        self.assertEqual([], second["fills"])
        self.assertIn("DAILY_NEW_BUY_LIMIT_REACHED", second["blockers"])
        self.assertEqual(1, len(load_state(self.root / "state/v7_virtual_rss_paper.json")["fills"]))

    def test_rehashed_ledger_cannot_claim_two_buys_on_one_day(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        day_two = datetime(2026, 7, 24, 10, 6, tzinfo=JST)
        self._write_candidates(
            ticker="5406.T",
            price=600,
            stop=490,
            generated_at="2026-07-24T09:00:00+09:00",
        )
        run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={
                "9501.T": quote(
                    price=500,
                    event_at=day_two - timedelta(minutes=1),
                    received_at=day_two - timedelta(minutes=1),
                ),
                "5406.T": quote(
                    ticker="5406.T",
                    price=500,
                    event_at=day_two - timedelta(minutes=1),
                    received_at=day_two - timedelta(minutes=1),
                ),
            },
            now=day_two,
        )
        path = self.root / "state/v7_virtual_rss_paper.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        event = state["fills"][1]
        old_run_id = event["run_id"]
        same_day_created = datetime(2026, 7, 23, 10, 7, tzinfo=JST)
        same_day_quote = datetime(2026, 7, 23, 10, 6, 30, tzinfo=JST)
        event["created_at"] = same_day_created.isoformat(timespec="microseconds")
        decision = event["decision_lineage"]
        decision["candidate_generated_at"] = "2026-07-23T09:00:00+09:00"
        input_bytes = bytes.fromhex(decision["candidate_input_hex"])
        input_bytes = input_bytes.replace(
            b"2026-07-24T09:00:00+09:00",
            b"2026-07-23T09:00:00+09:00",
        )
        decision["candidate_input_hex"] = input_bytes.hex()
        decision["candidate_input_sha256"] = hashlib.sha256(input_bytes).hexdigest()
        for row in decision["eligible_candidate_rows"]:
            if row["ticker"] == "5406.T":
                row["生成日時"] = "2026-07-23T09:00:00+09:00"
        for row in decision["run_quote_universe"]:
            row["event_at"] = same_day_quote.isoformat(timespec="seconds")
            row["received_at"] = same_day_quote.isoformat(timespec="seconds")
        own_quote = next(
            row for row in decision["run_quote_universe"]
            if row["ticker"] == "5406.T"
        )
        event["quote"] = json.loads(json.dumps(own_quote))
        event["quote_snapshot_sha256"] = _sha256(event["quote"])
        run_quote_hash = _sha256(decision["run_quote_universe"])
        new_run_id = _sha256({
            "contract": CONTRACT_ID,
            "trading_date": "2026-07-23",
            "candidate_sha256": decision["eligible_candidates_sha256"],
            "quote_snapshot_sha256": run_quote_hash,
            "policy_sha256": event["policy_sha256"],
        })
        event["run_id"] = new_run_id
        event["event_id"] = _sha256({
            "run_id": new_run_id,
            "ticker": event["ticker"],
            "route": event["route"],
            "side": event["side"],
            "quantity": event["quantity"],
            "quote_snapshot_sha256": event["quote_snapshot_sha256"],
            "policy_sha256": event["policy_sha256"],
            "candidate_limit_yen": event["candidate_limit_yen"],
        })
        event["event_sha256"] = _event_hash(event)
        state["processed_run_ids"] = [
            new_run_id if value == old_run_id else value
            for value in state["processed_run_ids"]
        ]
        state["observation_days"] = ["2026-07-23"]
        state["updated_at"] = same_day_created.isoformat(timespec="microseconds")
        state["last_event_sha256"] = event["event_sha256"]
        state["state_sha256"] = _state_hash(state)
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(VirtualRssError):
            load_state(path)

    def test_take_profit_exit_is_recorded_with_costs_and_realized_pnl(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        first = run_virtual_rss_paper(
            self.root, self.config, persist=True,
            quotes={"9501.T": quote()}, now=self.now,
        )
        self.assertEqual("BUY", first["fills"][0]["side"])
        next_day = datetime(2026, 7, 24, 10, 6, tzinfo=JST)
        exit_quote = quote(
            price=660.0,
            event_at=datetime(2026, 7, 24, 10, 5, tzinfo=JST),
            received_at=datetime(2026, 7, 24, 10, 5, tzinfo=JST),
        )
        second = run_virtual_rss_paper(
            self.root, self.config, persist=True,
            quotes={"9501.T": exit_quote}, now=next_day,
        )
        self.assertEqual(1, len(second["fills"]))
        fill = second["fills"][0]
        self.assertEqual("SELL", fill["side"])
        self.assertEqual(1070.0, fill["commission_yen"])
        self.assertGreater(fill["realized_pnl_yen"], 0)
        state = load_state(self.root / "state/v7_virtual_rss_paper.json")
        self.assertNotIn("9501.T|TSE_STANDARD_UNIT_SIM", state["positions"])

    def test_multiple_exits_plus_one_buy_are_atomic_and_retry_is_idempotent(self) -> None:
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        first = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={"9501.T": quote()},
            now=self.now,
        )
        self.assertEqual(["BUY"], [item["side"] for item in first["fills"]])

        day_two = datetime(2026, 7, 24, 10, 6, tzinfo=JST)
        self._write_candidates(
            ticker="5406.T",
            price=600,
            stop=490,
            generated_at="2026-07-24T09:00:00+09:00",
        )
        second = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes={
                "9501.T": quote(
                    price=500,
                    event_at=day_two - timedelta(minutes=1),
                    received_at=day_two - timedelta(minutes=1),
                ),
                "5406.T": quote(
                    ticker="5406.T",
                    price=500,
                    event_at=day_two - timedelta(minutes=1),
                    received_at=day_two - timedelta(minutes=1),
                ),
            },
            now=day_two,
        )
        self.assertEqual(["BUY"], [item["side"] for item in second["fills"]])

        day_three = datetime(2026, 7, 27, 10, 6, tzinfo=JST)
        self._write_candidates(
            ticker="1605.T",
            price=600,
            stop=490,
            generated_at="2026-07-27T09:00:00+09:00",
        )
        third_quotes = {
            "9501.T": quote(
                price=660,
                event_at=day_three - timedelta(minutes=1),
                received_at=day_three - timedelta(minutes=1),
            ),
            "5406.T": quote(
                ticker="5406.T",
                price=660,
                event_at=day_three - timedelta(minutes=1),
                received_at=day_three - timedelta(minutes=1),
            ),
            "1605.T": quote(
                ticker="1605.T",
                price=500,
                event_at=day_three - timedelta(minutes=1),
                received_at=day_three - timedelta(minutes=1),
            ),
        }
        third = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes=third_quotes,
            now=day_three,
        )
        self.assertEqual(3, len(third["fills"]))
        self.assertEqual(["SELL", "SELL", "BUY"], [item["side"] for item in third["fills"]])
        state_path = self.root / "state/v7_virtual_rss_paper.json"
        committed = state_path.read_bytes()
        state = load_state(state_path)
        self.assertEqual(list(range(1, 6)), [item["sequence"] for item in state["fills"]])
        self.assertEqual("1605.T", next(
            item["ticker"]
            for item in state["positions"].values()
            if item["route"] == "TSE_STANDARD_UNIT_SIM"
        ))

        retry = run_virtual_rss_paper(
            self.root,
            self.config,
            persist=True,
            quotes=third_quotes,
            now=day_three,
        )
        self.assertEqual([], retry["fills"])
        self.assertEqual("IDEMPOTENT_NOOP", retry["run_effect"])
        self.assertEqual(committed, state_path.read_bytes())

    def test_stale_candidate_and_missing_mini_eligibility_do_not_fill(self) -> None:
        self._write_candidates(
            ticker="1605.T", price=4000, stop=3400,
            generated_at="2026-07-18T09:00:00+09:00",
        )
        initialize_virtual_ledger(self.root, self.config, now=self.now)
        report = run_virtual_rss_paper(
            self.root, self.config, persist=True,
            quotes={"1605.T": quote(ticker="1605.T", price=3500)}, now=self.now,
        )
        self.assertEqual([], report["fills"])
        self.assertIn("STALE_CANDIDATE", report["blockers"])
        self.assertIn("KABUMINI_ELIGIBILITY_MISSING", report["blockers"])


class NotificationAndIsolationStep21Test(unittest.TestCase):
    def test_notification_chunks_are_lossless_and_preview_only(self) -> None:
        report = {
            "status": "SIMULATION_READY",
            "trading_date": "2026-07-23",
            "fills": [
                {
                    "side": "BUY", "ticker": f"{1000 + index}.T", "quantity": 1,
                    "route": "RAKUTEN_KABU_MINI_SIM", "reference_last_price_yen": 1000.0,
                    "filled_price_yen": 1004.0, "commission_yen": 0.0,
                    "realized_pnl_yen": 0.0, "cash_after_yen": 299000.0 - index,
                }
                for index in range(30)
            ],
            "performance": {"cash_yen": 270000, "net_pnl_after_reserves_yen": -350},
        }
        preview = build_notification_preview(report, maximum_chunk_chars=300)
        reconstructed = "".join(item["payload"] for item in preview["chunks"])
        self.assertEqual(preview["body_sha256"], hashlib.sha256(reconstructed.encode("utf-8")).hexdigest())
        self.assertEqual(preview["body"], reconstructed)
        self.assertEqual(preview["body"], _preview_text(preview))
        self.assertEqual(
            preview["body_sha256"], hashlib.sha256(_preview_text(preview).encode("utf-8")).hexdigest()
        )
        self.assertTrue(all(
            item["text"].startswith("VIRTUAL_RSS仮想取引・注文未送信")
            for item in preview["chunks"]
        ))
        self.assertTrue(all(
            item["payload_sha256"] == hashlib.sha256(item["payload"].encode("utf-8")).hexdigest()
            for item in preview["chunks"]
        ))
        self.assertFalse(preview["send_attempted"])
        self.assertFalse(preview["sent"])
        self.assertFalse(preview["external_notifications_allowed"])

    def test_step21_has_no_legacy_execution_or_notification_imports(self) -> None:
        source = (REPOSITORY / "phoenix_core/virtual_rss_paper.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        forbidden = {"broker_gateway", "execution_core", "realtime_gateway", "notify", "phoenix"}
        self.assertTrue(imports.isdisjoint(forbidden))
        self.assertNotIn("RAKUTEN_MARKETSPEED_II_RSS", source)

    def test_virtual_contract_cannot_masquerade_as_step20(self) -> None:
        self.assertEqual("PHOENIX_VIRTUAL_RSS_PAPER_V1", CONTRACT_ID)
        self.assertNotEqual("RAKUTEN_MARKETSPEED_II_RSS", QUOTE_SOURCE)
        self.assertFalse(POLICY["eligible_for_real_rss_gate"])

    def test_virtual_report_is_rejected_by_real_rss_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            valid, errors = verify_rss_shadow_report(
                Path(directory),
                {},
                {
                    "schema_version": 1,
                    "step": 21,
                    "contract_id": CONTRACT_ID,
                    "evidence_kind": "VIRTUAL_MARKET_FEED_SIMULATION",
                    "status": "SIMULATION_READY",
                    "eligible_for_real_rss_gate": False,
                },
                as_of=datetime(2026, 7, 23, 10, 6, tzinfo=JST),
            )
        self.assertFalse(valid)
        self.assertTrue(any("invalid" in value.lower() for value in errors))


class VirtualRssCliStep21Test(Step21Fixture):
    def test_environment_check_is_network_free_and_reports_ready(self) -> None:
        (self.root / "config/v7_scheduler_config.json").write_text(
            json.dumps(self.config), encoding="utf-8"
        )
        args = SimpleNamespace(
            config="config/v7_scheduler_config.json",
            check_environment=True,
            initialize_from_paper=False,
            import_kabumini_eligibility=None,
            paper_run=False,
            dry_run=False,
        )
        environment = {
            "status": "READY",
            "code": "READY",
            "tls_verification_enabled": True,
            "ca_bundle_mode": "LOCAL_MATERIALIZED_COPY",
            "remediation": "NONE",
        }
        output = io.StringIO()
        with (
            patch.object(virtual_rss_entry_v7, "ROOT", self.root),
            patch.object(virtual_rss_entry_v7, "_arguments", return_value=args),
            patch.object(
                virtual_rss_entry_v7,
                "check_quote_environment",
                return_value=environment,
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(0, virtual_rss_entry_v7.main())
        self.assertIn("quote environment: READY", output.getvalue())
        self.assertIn("External orders submitted: 0", output.getvalue())

    def test_missing_kabumini_csv_returns_actionable_error_without_traceback(self) -> None:
        (self.root / "config/v7_scheduler_config.json").write_text(
            json.dumps(self.config), encoding="utf-8"
        )
        args = SimpleNamespace(
            config="config/v7_scheduler_config.json",
            check_environment=False,
            initialize_from_paper=False,
            import_kabumini_eligibility="runtime/v7_virtual_rss/missing.csv",
            paper_run=False,
            dry_run=False,
        )
        errors = io.StringIO()
        with (
            patch.object(virtual_rss_entry_v7, "ROOT", self.root),
            patch.object(virtual_rss_entry_v7, "_arguments", return_value=args),
            redirect_stderr(errors),
        ):
            self.assertEqual(10, virtual_rss_entry_v7.main())
        self.assertIn("Super Screener", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())
        self.assertFalse((self.root / "state/v7_virtual_rss_paper.json").exists())

    def test_not_ready_online_result_returns_nonzero(self) -> None:
        (self.root / "config/v7_scheduler_config.json").write_text(
            json.dumps(self.config), encoding="utf-8"
        )
        args = SimpleNamespace(
            config="config/v7_scheduler_config.json",
            initialize_from_paper=False,
            import_kabumini_eligibility=None,
            paper_run=True,
            dry_run=False,
        )
        failed_report = {
            "status": "NOT_READY",
            "mode": "VIRTUAL_PAPER_RUN",
            "quotes": {"observed_count": 0, "requested_count": 1},
            "fills": [],
        }
        with (
            patch.object(virtual_rss_entry_v7, "ROOT", self.root),
            patch.object(virtual_rss_entry_v7, "_arguments", return_value=args),
            patch.object(
                virtual_rss_entry_v7,
                "run_virtual_rss_paper",
                return_value=failed_report,
            ),
            patch.object(virtual_rss_entry_v7, "print_virtual_rss_summary"),
        ):
            self.assertEqual(10, virtual_rss_entry_v7.main())


class DailyCandidateRefreshStep21Test(unittest.TestCase):
    def test_daily_task_builds_trade_candidates_before_ranking_and_notification(self) -> None:
        scripts = [str(task["script"]) for task in run_phoenix.TASKS]
        self.assertLess(scripts.index("ai_judgement.py"), scripts.index("trade_engine.py"))
        self.assertLess(scripts.index("trade_engine.py"), scripts.index("ranking_ai.py"))
        self.assertLess(scripts.index("trade_engine.py"), scripts.index("notify.py"))

    def test_refresh_only_excludes_notification_and_chart_tasks(self) -> None:
        self.assertIn("trade_engine.py", run_phoenix.REFRESH_ONLY_SCRIPTS)
        self.assertIn("daily_report.py", run_phoenix.REFRESH_ONLY_SCRIPTS)
        self.assertNotIn("notify.py", run_phoenix.REFRESH_ONLY_SCRIPTS)
        self.assertNotIn("chart_generator.py", run_phoenix.REFRESH_ONLY_SCRIPTS)

    def test_quote_transport_exports_verified_ca_to_every_child(self) -> None:
        environment = {
            "status": "READY",
            "code": "READY",
            "ca_bundle_mode": "LOCAL_MATERIALIZED_COPY",
            "tls_verification_enabled": True,
        }
        ca_bundle = Path(tempfile.gettempdir()) / "phoenix-test-ca.pem"
        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(
                run_phoenix,
                "prepare_quote_environment",
                return_value=(environment, ca_bundle),
            ),
        ):
            self.assertEqual(environment, run_phoenix.configure_quote_transport())
            child = run_phoenix.build_environment()
            for name in ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE"):
                self.assertEqual(str(ca_bundle), child[name])

    def test_quote_transport_failure_is_fail_closed(self) -> None:
        failed = {
            "status": "FAILED",
            "code": "TLS_CA_BUNDLE_MISSING",
            "remediation": "REINSTALL_CERTIFI_ACTIVE_VENV",
        }
        with patch.object(
            run_phoenix,
            "prepare_quote_environment",
            return_value=(failed, None),
        ):
            with self.assertRaises(RuntimeError):
                run_phoenix.configure_quote_transport()


if __name__ == "__main__":
    unittest.main()
