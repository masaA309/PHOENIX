from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    suite = unittest.defaultTestLoader.discover(
        start_dir=str(ROOT / "tests"),
        pattern="test_historical_validation_20y.py",
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
