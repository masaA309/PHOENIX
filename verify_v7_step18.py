from __future__ import annotations

import json
from pathlib import Path
import unittest

from phoenix_core.candidate_input_guard import CandidateInputPolicy


ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = [
        ROOT / "phoenix_core" / "candidate_input_guard.py",
        ROOT / "phoenix_core" / "pipeline.py",
        ROOT / "direct_pipeline_v7.py",
        ROOT / "config" / "v7_direct_pipeline_config.json",
        ROOT / "tests" / "test_v7_step18.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("PHOENIX v7 Step18 verification: FAIL")
        for path in missing:
            print(f"Missing: {path}")
        return 1
    try:
        config = json.loads(required[3].read_text(encoding="utf-8-sig"))
        CandidateInputPolicy.from_mapping(config.get("candidate_input", {}))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print("PHOENIX v7 Step18 verification: FAIL")
        print(f"{type(error).__name__}: {error}")
        return 1
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"),
        pattern="test_v7*.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        print("PHOENIX v7 Step18 verification: FAIL")
        if result.skipped:
            print(f"Skipped tests are forbidden: {len(result.skipped)}")
        return 1
    print("PHOENIX v7 Step18 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
