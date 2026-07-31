from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main() -> int:
    config_path = ROOT / "config/v7_scheduler_config.json"
    required = [
        ROOT / "phoenix_core/dry_run_integrity.py",
        ROOT / "phoenix_core/performance_tracker.py",
        ROOT / "phoenix_core/readiness_gate.py",
        ROOT / "tests/test_v7_step16.py",
        config_path,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("PHOENIX v7 Step16 verification: FAIL")
        for path in missing:
            print(f"Missing: {path}")
        return 1
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    settings = config.get("dry_run_integrity", {})
    if not settings.get("enabled", False) or not settings.get("protected_files"):
        print("PHOENIX v7 Step16 verification: FAIL (integrity guard disabled)")
        return 1
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_v7_step*.py",
            "-v",
        ],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode:
        print("PHOENIX v7 Step16 verification: FAIL")
        return completed.returncode
    print("PHOENIX v7 Step16 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
