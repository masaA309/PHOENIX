from __future__ import annotations

import argparse
import json
from pathlib import Path

from phoenix_core.rss_shadow_contract import (
    create_workbook_attestation,
    print_rss_shadow_summary,
    run_rss_shadow_contract,
)


ROOT = Path(__file__).resolve().parent


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the Step20 read-only Rakuten RSS shadow contract."
    )
    parser.add_argument(
        "--config",
        default="config/v7_scheduler_config.json",
        help="Scheduler configuration path relative to the repository root.",
    )
    parser.add_argument(
        "--attest-workbook",
        action="store_true",
        help="Hash the reviewed .xlsm workbook and create its local attestation.",
    )
    parser.add_argument(
        "--confirm-vba-source-import",
        action="store_true",
        help="Confirm that the tracked .bas was imported into the reviewed workbook.",
    )
    parser.add_argument(
        "--confirm-no-order-functions",
        action="store_true",
        help="Confirm that the reviewed workbook has no order, amend, or cancel function.",
    )
    parser.add_argument(
        "--publish-current",
        action="store_true",
        help="Validate the Excel inbox CSV and publish an immutable snapshot manifest.",
    )
    parser.add_argument(
        "--capture-session",
        action="store_true",
        help="Record one verified RSS shadow session when all explicit gates are enabled.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; no inbox publication or session-state update is allowed.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    if args.attest_workbook:
        if args.dry_run or args.publish_current or args.capture_session:
            raise SystemExit("--attest-workbook must be run as a separate operation")
    elif args.confirm_vba_source_import or args.confirm_no_order_functions:
        raise SystemExit("Workbook review confirmations require --attest-workbook")
    if args.dry_run and (args.publish_current or args.capture_session):
        raise SystemExit(
            "--dry-run cannot be combined with --publish-current or --capture-session"
        )
    config_path = (ROOT / args.config).resolve()
    with config_path.open("r", encoding="utf-8-sig") as stream:
        config = json.load(stream)
    if not isinstance(config, dict):
        raise ValueError("Scheduler configuration root must be an object")
    if args.attest_workbook:
        evidence = create_workbook_attestation(
            ROOT,
            config,
            source_import_confirmed=args.confirm_vba_source_import,
            no_order_functions_confirmed=args.confirm_no_order_functions,
        )
        print("PHOENIX Step20 workbook attestation created")
        print(f"Workbook SHA-256: {evidence['workbook_sha256']}")
        print("Orders submitted: 0")
        return 0
    report = run_rss_shadow_contract(
        ROOT,
        config,
        publish_inbox=args.publish_current and not args.dry_run,
        capture_session=args.capture_session and not args.dry_run,
    )
    print_rss_shadow_summary(report)
    return 0 if report.get("status") == "READY" else 10


if __name__ == "__main__":
    raise SystemExit(main())
