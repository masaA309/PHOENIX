from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = [
        ROOT / "phoenix_core/virtual_rss_paper.py",
        ROOT / "virtual_rss_entry_v7.py",
        ROOT / "config/v7_virtual_rss_policy.json",
        ROOT / "tests/test_v7_step21.py",
        ROOT / "README_v7_step21.md",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        print("PHOENIX v7 Step21 verification: FAIL")
        for path in missing:
            print(f"Missing: {path}")
        return 1
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"), pattern="test_v7*.py"
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful() or result.skipped:
        print("PHOENIX v7 Step21 verification: FAIL")
        if result.skipped:
            print(f"Skipped tests are forbidden: {len(result.skipped)}")
        return 1
    print("PHOENIX v7 Step21 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
