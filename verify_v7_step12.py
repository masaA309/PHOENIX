from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main() -> int:
    config_path = ROOT / "config/v7_scheduler_config.json"
    required = [ROOT / "phoenix_core/portfolio_guard.py", ROOT / "phoenix_core/decision_diagnostics.py", ROOT / "tests/test_v7_step12.py", config_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("PHOENIX v7 Step12 verification: FAIL")
        for path in missing:
            print(f"Missing: {path}")
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    guard = config.get("portfolio_guard", {})
    if not guard.get("enabled", False) or not guard.get("advisory_only", False):
        print("PHOENIX v7 Step12 verification: FAIL (safe advisory mode is not enabled)")
        return 1
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_v7_step*.py", "-v"], cwd=ROOT, check=False)
    if completed.returncode:
        print("PHOENIX v7 Step12 verification: FAIL")
        return completed.returncode
    print("PHOENIX v7 Step12 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
