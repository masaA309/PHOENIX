from __future__ import annotations

import argparse
import unittest
from pathlib import Path

from phoenix_core.environment_validator import EnvironmentValidator, print_report


ROOT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = ROOT_DIR / "config" / "v7_environment.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--step9-only", action="store_true")
    return parser.parse_args()


def run_tests(step9_only: bool = False) -> bool:
    loader = unittest.TestLoader()
    pattern = "test_v7_step9.py" if step9_only else "test_v7_step*.py"
    suite = loader.discover(
        start_dir=str(ROOT_DIR / "tests"),
        pattern=pattern,
        top_level_dir=str(ROOT_DIR),
    )
    if suite.countTestCases() <= 0:
        print("No Step tests were discovered")
        return False
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def main() -> int:
    args = parse_args()
    print("=" * 100)
    print("PHOENIX v7 STEP9 VERIFY")
    print("=" * 100)
    try:
        validator = EnvironmentValidator.from_file(
            root=ROOT_DIR,
            config_path=CONFIG_FILE,
        )
        report = validator.run_and_save()
    except Exception as error:
        print("STEP9 VERIFY FAILED")
        print(f"{type(error).__name__}: {error}")
        return 1
    print_report(report)
    if not report.ready:
        print("PHOENIX v7 Step9 verification: FAIL")
        return 1
    if not args.skip_tests and not run_tests(args.step9_only):
        print("PHOENIX v7 Step9 verification: FAIL")
        return 1
    print("PHOENIX v7 Step9 verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
