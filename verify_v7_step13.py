from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main() -> int:
    config_path = ROOT / "config/v7_scheduler_config.json"
    required = [ROOT / "phoenix_core/market_data_guard.py", ROOT / "phoenix_core/portfolio_guard.py", ROOT / "tests/test_v7_step13.py", config_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("PHOENIX v7 Step13 verification: FAIL")
        for path in missing:
            print(f"Missing: {path}")
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not config.get("market_data_guard", {}).get("enabled", False):
        print("PHOENIX v7 Step13 verification: FAIL (market data guard disabled)")
        return 1
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_v7_step*.py", "-v"], cwd=ROOT, check=False)
    if completed.returncode:
        print("PHOENIX v7 Step13 verification: FAIL")
        return completed.returncode
    print("PHOENIX v7 Step13 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
