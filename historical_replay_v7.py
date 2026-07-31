from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from phoenix_core.historical_replay import (
    HistoricalReplayLockError,
    REQUIRED_PROTECTED_FILES,
    capture_files,
    files_unchanged,
    print_historical_replay_summary,
    run_historical_replay,
)
from phoenix_core.performance_tracker import atomic_write


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT_DIR / "config" / "v7_historical_replay_config.json"
FAILURE_REPORT = ROOT_DIR / "reports" / "v7_historical_replay.json"


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def main() -> int:
    configure_console()
    parser = argparse.ArgumentParser(
        description="PHOENIX v7 Step17.1 offline historical walk-forward replay gate"
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    protected_before = capture_files(ROOT_DIR, list(REQUIRED_PROTECTED_FILES))
    try:
        report = run_historical_replay(ROOT_DIR, Path(args.config))
    except HistoricalReplayLockError as error:
        print("PHOENIX v7 Step17.1 historical replay: BUSY")
        print(f"{type(error).__name__}: {error}")
        return 2
    except Exception as error:
        protected_after = capture_files(ROOT_DIR, list(REQUIRED_PROTECTED_FILES))
        state_unchanged = files_unchanged(protected_before, protected_after)
        failure = {
            "schema_version": 1,
            "version": "PHOENIX v7 Step17.1",
            "gate_status": "FAILED",
            "execution_status": "FAILED",
            "evidence_kind": "HISTORICAL_WALK_FORWARD_REPLAY",
            "blocking_reasons": [f"{type(error).__name__}: {error}"],
            "state_integrity_status": "READY" if state_unchanged else "FAILED",
            "post_save_integrity_status": "FAILED",
            "protected_files_before": protected_before,
            "protected_files_after": protected_after,
            "paper_days_credited": 0,
            "audited_fills_credited": 0,
            "external_orders_submitted": 0,
            "live_trading_enabled": False,
            "automatic_promotion": False,
        }
        atomic_write(FAILURE_REPORT, json.dumps(failure, ensure_ascii=False, indent=2) + "\n")
        print("PHOENIX v7 Step17.1 historical replay: FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1
    print_historical_replay_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
