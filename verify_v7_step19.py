from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = [
        ROOT / "phoenix_core" / "trading_economics.py",
        ROOT / "phoenix_core" / "staged_pilot_gate.py",
        ROOT / "tests" / "test_v7_step19.py",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("PHOENIX v7 Step19 verification: FAIL")
        for path in missing:
            print(f"Missing: {path}")
        return 1
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), pattern="test_v7*.py"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        print("PHOENIX v7 Step19 verification: FAIL")
        if result.skipped:
            print(f"Skipped tests are forbidden: {len(result.skipped)}")
        return 1
    print("PHOENIX v7 Step19 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
