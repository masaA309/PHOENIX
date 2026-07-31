from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from phoenix_core.virtual_rss_paper import (
    JST,
    VirtualRssError,
    check_quote_environment,
    import_eligibility,
    initialize_virtual_ledger,
    print_virtual_rss_summary,
    run_virtual_rss_paper,
)


ROOT = Path(__file__).resolve().parent


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Step21 isolated VIRTUAL_RSS observation/paper simulation."
    )
    parser.add_argument("--config", default="config/v7_scheduler_config.json")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true", help="Observe and report; never mutate the virtual ledger.")
    modes.add_argument("--paper-run", action="store_true", help="Record eligible virtual fills only in the isolated virtual ledger.")
    modes.add_argument("--check-environment", action="store_true", help="Validate quote dependencies and TLS CA bundle without a network request.")
    modes.add_argument("--initialize-from-paper", action="store_true", help="Create the virtual ledger once from the canonical PAPER state.")
    modes.add_argument("--import-kabumini-eligibility", metavar="CSV", help="Import a reviewed Super Screener CSV below runtime/v7_virtual_rss.")
    return parser.parse_args()


def main() -> int:
    try:
        args = _arguments()
        config_path = (ROOT / args.config).resolve()
        with config_path.open("r", encoding="utf-8-sig") as stream:
            config = json.load(stream)
        if not isinstance(config, dict):
            raise VirtualRssError("Scheduler configuration root must be an object")
        if getattr(args, "check_environment", False):
            environment = check_quote_environment()
            print(f"PHOENIX Step21 quote environment: {environment.get('status')}")
            print(f"Code: {environment.get('code')}")
            print(f"TLS verification enabled: {environment.get('tls_verification_enabled')}")
            print(f"CA bundle mode: {environment.get('ca_bundle_mode')}")
            print(f"Remediation: {environment.get('remediation')}")
            print("External orders submitted: 0")
            return 0 if environment.get("status") == "READY" else 10
        if args.initialize_from_paper:
            state = initialize_virtual_ledger(ROOT, config, now=datetime.now(JST))
            print("PHOENIX Step21 virtual ledger initialized from canonical PAPER state")
            print(f"Source PAPER SHA-256: {state['source_paper_state_sha256']}")
            print("External orders submitted: 0")
            return 0
        if args.import_kabumini_eligibility:
            path = (ROOT / args.import_kabumini_eligibility).resolve()
            evidence = import_eligibility(ROOT, config, path, now=datetime.now(JST))
            print(f"Kabu Mini eligibility evidence imported: {len(evidence['tickers'])} tickers")
            print("External orders submitted: 0")
            return 0
        report = run_virtual_rss_paper(ROOT, config, persist=args.paper_run)
        print_virtual_rss_summary(report)
        return 0 if report.get("status") in ("SIMULATION_READY", "MARK_ONLY") else 10
    except VirtualRssError as error:
        print(f"PHOENIX Step21 blocked: {error}", file=sys.stderr)
        print("No order was submitted and no broker state was changed.", file=sys.stderr)
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
