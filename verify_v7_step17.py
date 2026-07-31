from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = [
        ROOT / "phoenix_core" / "historical_replay.py",
        ROOT / "historical_replay_v7.py",
        ROOT / "config" / "v7_historical_replay_config.json",
        ROOT / "data" / "historical_replay_manifest.json",
        ROOT / "tests" / "test_v7_step17.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("PHOENIX v7 Step17.1 verification: FAIL")
        for path in missing:
            print(f"Missing: {path}")
        return 1
    config = json.loads(required[2].read_text(encoding="utf-8-sig"))
    settings = config.get("historical_replay", {})
    if settings.get("enabled") is not True:
        print("PHOENIX v7 Step17.1 verification: FAIL (gate disabled)")
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
            "test_v7*.py",
            "-v",
        ],
        cwd=ROOT,
        check=False,
    )
    if completed.returncode:
        print("PHOENIX v7 Step17.1 verification: FAIL")
        return completed.returncode
    print("PHOENIX v7 Step17.1 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
