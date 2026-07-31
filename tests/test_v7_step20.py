from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timedelta
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from phoenix_core.data_freshness import JST
from phoenix_core.candidate_input_guard import (
    CandidateInputPolicy,
    load_execution_candidates,
)
from phoenix_core.rss_shadow_contract import (
    SNAPSHOT_COLUMNS,
    create_workbook_attestation,
    publish_inbox_snapshot,
    run_rss_shadow_contract,
    verify_rss_shadow_report,
    verify_shadow_evidence_state,
)


NOW = datetime(2026, 7, 23, 15, 0, 0, tzinfo=JST)


def settings() -> dict[str, object]:
    return {
        "enabled": True,
        "advisory_only": True,
        "read_only": True,
        "orders_allowed": False,
        "live_trading_enabled": False,
        "contract_id": "PHOENIX_RSS_SHADOW_V1",
        "source": "RAKUTEN_MARKETSPEED_II_RSS",
        "exporter": "PHOENIX_EXCEL_VBA_SHADOW",
        "workbook_contract_version": "1",
        "workbook_attestation_required": True,
        "runtime_root": "runtime/v7_rss_shadow",
        "inbox_directory": "runtime/v7_rss_shadow/inbox",
        "inbox_snapshot_file": "runtime/v7_rss_shadow/inbox/current_snapshot.csv",
        "snapshot_directory": "runtime/v7_rss_shadow/snapshots",
        "manifest_directory": "runtime/v7_rss_shadow/manifests",
        "manifest_file": "runtime/v7_rss_shadow/current_manifest.json",
        "producer_file": "excel/PHOENIX_RSS_SHADOW_V1.bas",
        "workbook_file": "runtime/v7_rss_shadow/PHOENIX_RSS_SHADOW.xlsm",
        "workbook_attestation_file": "state/rakuten_rss_workbook_attestation.json",
        "maximum_quote_age_seconds": 15,
        "maximum_manifest_age_seconds": 90,
        "maximum_future_skew_seconds": 2,
        "minimum_quote_rows": 20,
        "maximum_quote_rows": 225,
        "maximum_snapshot_bytes": 1_048_576,
        "minimum_session_captures": 3,
        "minimum_session_span_seconds": 14_400,
        "maximum_session_manifests": 64,
        "session_capture_enabled": False,
        "candidate_guard_report": "reports/v7_direct_pipeline_summary.json",
        "shadow_evidence_state": "state/v7_realtime_shadow_evidence.json",
        "report_json": "reports/v7_rss_shadow_contract.json",
        "report_text": "reports/v7_rss_shadow_contract.txt",
    }


def config() -> dict[str, object]:
    return {
        "rss_shadow_contract": settings(),
        "staged_pilot_gate": {"rss_implementation_ready": False},
        "files": {"pipeline_config": "config/v7_direct_pipeline_config.json"},
    }


def snapshot_bytes(
    *,
    capture_id: str = "RSS_20260723_100000_1",
    sequence: int = 1,
    exported_at: datetime = NOW,
    quote_at: datetime | None = None,
    rows: int = 20,
    header: tuple[str, ...] = SNAPSHOT_COLUMNS,
    mutate: callable | None = None,
) -> bytes:
    quote_at = quote_at or (exported_at - timedelta(seconds=5))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    for index in range(rows):
        ticker = f"{1605 + index:04d}.T"
        row: dict[str, object] = {
            "schema_version": "1",
            "contract_id": "PHOENIX_RSS_SHADOW_V1",
            "source": "RAKUTEN_MARKETSPEED_II_RSS",
            "exporter": "PHOENIX_EXCEL_VBA_SHADOW",
            "workbook_contract_version": "1",
            "read_only": "true",
            "orders_allowed": "false",
            "external_orders_submitted": "0",
            "capture_id": capture_id,
            "sequence": str(sequence),
            "exported_at": exported_at.isoformat(timespec="seconds"),
            "ticker": ticker,
            "current_price": str(1000 + index),
            "bid": str(999 + index),
            "ask": str(1001 + index),
            "volume": str(index * 100),
            "trading_status": "TRADING",
            "quote_timestamp": quote_at.isoformat(timespec="seconds"),
            "bid_timestamp": quote_at.isoformat(timespec="seconds"),
            "ask_timestamp": quote_at.isoformat(timespec="seconds"),
        }
        if mutate is not None:
            mutate(row, index)
        writer.writerow({name: row.get(name, "") for name in header})
    return output.getvalue().encode("utf-8")


class RssShadowWorkspace:
    def __init__(self, directory: str):
        self.root = Path(directory)
        (self.root / "excel").mkdir(parents=True)
        (self.root / "reports").mkdir()
        (self.root / "state").mkdir()
        (self.root / "config").mkdir()
        (self.root / "excel/PHOENIX_RSS_SHADOW_V1.bas").write_text(
            "Option Explicit\n' read-only test producer\n", encoding="utf-8"
        )
        self.config = config()
        candidate_policy = {
            "enabled": True,
            "path": "reports/trade_signals.csv",
            "decision_column": "Trade判定",
            "execution_price_column": "押し目価格",
            "executable_values": ["BUY"],
            "known_values": ["BUY", "WATCH", "SKIP"],
            "fallback": False,
        }
        (self.root / "config/v7_direct_pipeline_config.json").write_text(
            json.dumps({"candidate_input": candidate_policy}, ensure_ascii=False),
            encoding="utf-8",
        )
        workbook = self.root / "runtime/v7_rss_shadow/PHOENIX_RSS_SHADOW.xlsm"
        workbook.parent.mkdir(parents=True)
        with zipfile.ZipFile(workbook, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
            archive.writestr("xl/workbook.xml", "<workbook />")
            archive.writestr("xl/vbaProject.bin", b"safe-read-only-vba-project")
        create_workbook_attestation(
            self.root,
            self.config,
            source_import_confirmed=True,
            no_order_functions_confirmed=True,
            as_of=datetime(2026, 7, 23, 8, 30, tzinfo=JST),
        )

    @property
    def inbox(self) -> Path:
        return self.root / "runtime/v7_rss_shadow/inbox/current_snapshot.csv"

    @property
    def manifest(self) -> Path:
        return self.root / "runtime/v7_rss_shadow/current_manifest.json"

    @property
    def report(self) -> Path:
        return self.root / "reports/v7_rss_shadow_contract.json"

    def write_snapshot(self, value: bytes | None = None) -> None:
        self.inbox.parent.mkdir(parents=True, exist_ok=True)
        self.inbox.write_bytes(value or snapshot_bytes())

    def publish(self, value: bytes | None = None) -> dict[str, object]:
        self.write_snapshot(value)
        return publish_inbox_snapshot(self.root, self.config, as_of=NOW)

    def publish_session_captures(self) -> None:
        captures = (
            (1, datetime(2026, 7, 23, 9, 30, tzinfo=JST)),
            (2, datetime(2026, 7, 23, 11, 0, tzinfo=JST)),
            (3, NOW),
        )
        for sequence, captured_at in captures:
            self.write_snapshot(
                snapshot_bytes(
                    capture_id=f"RSS_20260723_{captured_at:%H%M%S}_{sequence}",
                    sequence=sequence,
                    exported_at=captured_at,
                )
            )
            publish_inbox_snapshot(
                self.root, self.config, as_of=captured_at
            )

    def write_candidate_guard(self, *, omitted_ticker: bool = False) -> None:
        tickers = [f"{1605 + index:04d}.T" for index in range(20)]
        if omitted_ticker:
            tickers[-1] = "9999.T"
        source = io.StringIO(newline="")
        writer = csv.DictWriter(
            source,
            fieldnames=(
                "ticker", "銘柄", "基準価格", "押し目価格",
                "損切価格", "PHOENIX_SCORE", "Trade判定",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for index, ticker in enumerate(tickers):
            writer.writerow(
                {
                    "ticker": ticker,
                    "銘柄": f"TEST-{index}",
                    "基準価格": 1000 + index,
                    "押し目価格": 990 + index,
                    "損切価格": 950 + index,
                    "PHOENIX_SCORE": 50,
                    "Trade判定": "WATCH",
                }
            )
        raw = source.getvalue().encode("utf-8")
        source_path = self.root / "reports/trade_signals.csv"
        source_path.write_bytes(raw)
        policy = CandidateInputPolicy.from_mapping(
            json.loads(
                (self.root / "config/v7_direct_pipeline_config.json").read_text(
                    encoding="utf-8"
                )
            )["candidate_input"]
        )
        batch = load_execution_candidates(
            source_path, policy, repository_root=self.root
        )
        guard = {
            "generated_at": NOW.isoformat(timespec="seconds"),
            "candidate_input_guard": batch.audit.as_dict(),
        }
        (self.root / "reports/v7_direct_pipeline_summary.json").write_text(
            json.dumps(guard), encoding="utf-8"
        )


class RssShadowContractStep20Test(unittest.TestCase):
    def test_valid_publish_and_report_verify_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.write_snapshot()
            result = run_rss_shadow_contract(
                workspace.root, workspace.config, as_of=NOW, publish_inbox=True
            )
            self.assertEqual("READY", result["status"])
            self.assertEqual(20, result["source_evidence"]["ticker_count"])
            valid, errors = verify_rss_shadow_report(
                workspace.root, workspace.config, result, as_of=NOW
            )
            self.assertTrue(valid, errors)
            stored = json.loads(workspace.report.read_text(encoding="utf-8"))
            valid, errors = verify_rss_shadow_report(
                workspace.root, workspace.config, stored, as_of=NOW
            )
            self.assertTrue(valid, errors)
            self.assertEqual(0, stored["safety"]["orders_submitted"])

    def test_missing_manifest_is_not_ready_without_state_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            protected = workspace.root / "state/v7_paper_broker.json"
            queue = workspace.root / "execution/rss_order_queue.csv"
            queue.parent.mkdir()
            protected.write_bytes(b"broker-state")
            queue.write_bytes(b"queue")
            before = (protected.read_bytes(), queue.read_bytes())
            result = run_rss_shadow_contract(workspace.root, workspace.config, as_of=NOW)
            self.assertEqual("NOT_READY", result["status"])
            self.assertEqual(before, (protected.read_bytes(), queue.read_bytes()))
            self.assertFalse((workspace.root / "state/v7_realtime_shadow_evidence.json").exists())

    def test_exact_columns_and_order_like_columns_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            header = SNAPSHOT_COLUMNS + ("order_id",)
            workspace.write_snapshot(snapshot_bytes(header=header))
            with self.assertRaisesRegex(ValueError, "order columns"):
                publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)

    def test_duplicate_ticker_nonfinite_and_crossed_market_are_rejected(self) -> None:
        cases = {
            "duplicate": lambda row, index: row.update(ticker="1605.T") if index == 1 else None,
            "nonfinite": lambda row, index: row.update(current_price="NaN") if index == 0 else None,
            "crossed": lambda row, index: row.update(bid="2000", ask="1000") if index == 0 else None,
        }
        for label, mutate in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                workspace = RssShadowWorkspace(directory)
                workspace.write_snapshot(snapshot_bytes(mutate=mutate))
                with self.assertRaises(ValueError):
                    publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)

    def test_naive_stale_future_and_lunch_timestamps_are_rejected(self) -> None:
        values = (
            snapshot_bytes(quote_at=(NOW - timedelta(seconds=16))),
            snapshot_bytes(quote_at=(NOW + timedelta(seconds=3))),
            snapshot_bytes(exported_at=datetime(2026, 7, 23, 12, 0, tzinfo=JST)),
        )
        for value in values:
            with tempfile.TemporaryDirectory() as directory:
                workspace = RssShadowWorkspace(directory)
                workspace.write_snapshot(value)
                with self.assertRaises(ValueError):
                    publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.write_snapshot()
            with self.assertRaisesRegex(ValueError, "timezone-aware"):
                publish_inbox_snapshot(
                    workspace.root, workspace.config, as_of=datetime(2026, 7, 23, 10, 0)
                )

    def test_snapshot_and_manifest_tampering_are_detected(self) -> None:
        for target in ("snapshot", "manifest"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                workspace = RssShadowWorkspace(directory)
                manifest = workspace.publish()
                if target == "snapshot":
                    path = workspace.root / str(manifest["snapshot_file"])
                    path.write_bytes(path.read_bytes() + b"x")
                else:
                    payload = json.loads(workspace.manifest.read_text(encoding="utf-8"))
                    payload["ticker_count"] = 21
                    workspace.manifest.write_text(json.dumps(payload), encoding="utf-8")
                result = run_rss_shadow_contract(workspace.root, workspace.config, as_of=NOW)
                self.assertEqual("NOT_READY", result["status"])

    def test_workbook_change_invalidates_attestation_and_publication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workbook = workspace.root / "runtime/v7_rss_shadow/PHOENIX_RSS_SHADOW.xlsm"
            workbook.write_bytes(workbook.read_bytes() + b"changed")
            workspace.write_snapshot()
            with self.assertRaisesRegex(ValueError, "Workbook attestation no longer matches"):
                publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)

    def test_sequence_is_monotonic_idempotent_and_capture_id_is_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            first = workspace.publish()
            second = publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)
            self.assertEqual(first, second)
            workspace.write_snapshot(snapshot_bytes(capture_id="RSS_20260723_100001_2", sequence=1))
            with self.assertRaisesRegex(ValueError, "increase"):
                publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)
            workspace.write_snapshot(snapshot_bytes(mutate=lambda row, index: row.update(ask="1002") if index == 0 else None))
            with self.assertRaisesRegex(ValueError, "same capture_id"):
                publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)

    def test_preexisting_operation_lock_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.write_snapshot()
            lock = workspace.root / "runtime/v7_rss_shadow/operation.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("owner", encoding="ascii")
            with self.assertRaises(RuntimeError):
                publish_inbox_snapshot(workspace.root, workspace.config, as_of=NOW)
            self.assertEqual("owner", lock.read_text(encoding="ascii"))

    def test_config_cannot_escape_repository_or_spoof_boolean_with_integer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.write_snapshot()
            escaped = deepcopy(workspace.config)
            escaped["rss_shadow_contract"]["runtime_root"] = str(Path(directory).parent)  # type: ignore[index]
            with self.assertRaisesRegex(ValueError, "child of the repository"):
                publish_inbox_snapshot(workspace.root, escaped, as_of=NOW)
            spoofed = deepcopy(workspace.config)
            spoofed["rss_shadow_contract"]["read_only"] = 1  # type: ignore[index]
            with self.assertRaises(ValueError):
                publish_inbox_snapshot(workspace.root, spoofed, as_of=NOW)
            lowered = deepcopy(workspace.config)
            lowered["rss_shadow_contract"]["minimum_quote_rows"] = 1  # type: ignore[index]
            with self.assertRaisesRegex(ValueError, "row limits"):
                publish_inbox_snapshot(workspace.root, lowered, as_of=NOW)

    def test_session_capture_requires_complete_candidate_universe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.config["rss_shadow_contract"]["session_capture_enabled"] = True  # type: ignore[index]
            workspace.config["staged_pilot_gate"]["rss_implementation_ready"] = True  # type: ignore[index]
            workspace.write_candidate_guard(omitted_ticker=True)
            workspace.publish_session_captures()
            result = run_rss_shadow_contract(
                workspace.root,
                workspace.config,
                as_of=NOW,
                capture_session=True,
            )
            self.assertEqual("NOT_READY", result["status"])
            self.assertFalse((workspace.root / "state/v7_realtime_shadow_evidence.json").exists())

    def test_single_snapshot_never_counts_as_a_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.config["rss_shadow_contract"]["session_capture_enabled"] = True  # type: ignore[index]
            workspace.config["staged_pilot_gate"]["rss_implementation_ready"] = True  # type: ignore[index]
            workspace.write_candidate_guard()
            workspace.publish()
            result = run_rss_shadow_contract(
                workspace.root, workspace.config, as_of=NOW, capture_session=True
            )
            self.assertEqual("NOT_READY", result["status"])
            self.assertFalse((workspace.root / "state/v7_realtime_shadow_evidence.json").exists())

    def test_session_capture_is_same_day_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.config["rss_shadow_contract"]["session_capture_enabled"] = True  # type: ignore[index]
            workspace.config["staged_pilot_gate"]["rss_implementation_ready"] = True  # type: ignore[index]
            workspace.write_candidate_guard()
            workspace.publish_session_captures()
            first = run_rss_shadow_contract(
                workspace.root, workspace.config, as_of=NOW,
                capture_session=True,
            )
            self.assertTrue(first["session_recorded"])
            state_path = workspace.root / "state/v7_realtime_shadow_evidence.json"
            first_bytes = state_path.read_bytes()
            second = run_rss_shadow_contract(
                workspace.root, workspace.config, as_of=NOW, capture_session=True
            )
            self.assertFalse(second["session_recorded"])
            self.assertEqual(first_bytes, state_path.read_bytes())

    def test_corrupt_existing_state_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.config["rss_shadow_contract"]["session_capture_enabled"] = True  # type: ignore[index]
            workspace.config["staged_pilot_gate"]["rss_implementation_ready"] = True  # type: ignore[index]
            workspace.write_candidate_guard()
            state_path = workspace.root / "state/v7_realtime_shadow_evidence.json"
            state_path.write_text('{"external_orders_submitted":1}', encoding="utf-8")
            before = state_path.read_bytes()
            workspace.publish_session_captures()
            result = run_rss_shadow_contract(
                workspace.root, workspace.config, as_of=NOW,
                capture_session=True,
            )
            self.assertEqual("NOT_READY", result["status"])
            self.assertEqual(before, state_path.read_bytes())

    def test_archived_snapshot_tampering_invalidates_shadow_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.config["rss_shadow_contract"]["session_capture_enabled"] = True  # type: ignore[index]
            workspace.config["staged_pilot_gate"]["rss_implementation_ready"] = True  # type: ignore[index]
            workspace.write_candidate_guard()
            workspace.publish_session_captures()
            result = run_rss_shadow_contract(
                workspace.root, workspace.config, as_of=NOW, capture_session=True
            )
            self.assertEqual("READY", result["status"])
            state_path = workspace.root / "state/v7_realtime_shadow_evidence.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            manifest_path = workspace.root / state["sessions"][0]["rss_manifest_files"][0]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            snapshot_path = workspace.root / manifest["snapshot_file"]
            snapshot_path.write_bytes(snapshot_path.read_bytes() + b"tampered")
            valid, errors = verify_shadow_evidence_state(
                workspace.root, workspace.config, state
            )
            self.assertFalse(valid)
            self.assertTrue(errors)

    def test_report_tampering_and_false_as_zero_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workspace.publish()
            run_rss_shadow_contract(workspace.root, workspace.config, as_of=NOW)
            report = json.loads(workspace.report.read_text(encoding="utf-8"))
            report["safety"]["orders_submitted"] = False
            report["evidence_sha256"] = hashlib.sha256(
                json.dumps(
                    {key: value for key, value in report.items() if key != "evidence_sha256"},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
            valid, errors = verify_rss_shadow_report(
                workspace.root, workspace.config, report, as_of=NOW
            )
            self.assertFalse(valid)
            self.assertTrue(errors)

    def test_step20_sources_do_not_import_or_call_legacy_execution_paths(self) -> None:
        root = Path(__file__).resolve().parents[1]
        module = (root / "phoenix_core/rss_shadow_contract.py").read_text(encoding="utf-8")
        vba = (root / "excel/PHOENIX_RSS_SHADOW_V1.bas").read_text(encoding="utf-8")
        for forbidden in (
            "broker_gateway", "realtime_gateway", "execution_core",
            "RssStockOrder", "Application.Run", "rss_order_queue.csv", "Shell(",
        ):
            self.assertNotIn(forbidden, module + vba)
        csv_escape_line = next(line for line in vba.splitlines() if "CsvCell =" in line)
        self.assertEqual(18, csv_escape_line.count('"'))

    def test_workbook_forbidden_execution_token_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = RssShadowWorkspace(directory)
            workbook = workspace.root / "runtime/v7_rss_shadow/PHOENIX_RSS_SHADOW.xlsm"
            with zipfile.ZipFile(workbook, "w") as archive:
                archive.writestr("[Content_Types].xml", "<Types />")
                archive.writestr("xl/workbook.xml", "<workbook />")
                archive.writestr("xl/vbaProject.bin", b"RssStockOrder")
            with self.assertRaisesRegex(ValueError, "forbidden execution token"):
                create_workbook_attestation(
                    workspace.root,
                    workspace.config,
                    source_import_confirmed=True,
                    no_order_functions_confirmed=True,
                    as_of=NOW,
                )


if __name__ == "__main__":
    unittest.main()
