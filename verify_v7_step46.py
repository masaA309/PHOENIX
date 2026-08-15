from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _run_pytest() -> int:
    import pytest

    return pytest.main([str(ROOT / "tests" / "test_v7_step46.py")])


def _run_unittest() -> int:
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(ROOT / "tests"),
        pattern="test_v7_step46.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main() -> None:
    try:
        exit_code = _run_pytest()
    except ImportError:
        exit_code = _run_unittest()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
