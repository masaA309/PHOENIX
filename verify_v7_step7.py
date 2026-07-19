from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile

from phoenix_core.run_guard import RunPolicy, SingleInstanceLock, should_run


def main() -> None:
    checks: list[tuple[str, bool]] = []
    policy = RunPolicy()

    checks.append(("平日実行", should_run(policy, {}, datetime(2026, 7, 20, 8, 30))[0]))
    checks.append(("休日スキップ", not should_run(policy, {}, datetime(2026, 7, 19, 8, 30))[0]))
    checks.append(("1日1回", not should_run(policy, {"last_success_date": "2026-07-20"}, datetime(2026, 7, 20, 9, 0))[0]))

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "verify.lock"
        first = SingleInstanceLock(path)
        second = SingleInstanceLock(path)
        first_ok = first.acquire()
        second_blocked = not second.acquire()
        first.release()
        checks.append(("二重起動防止", first_ok and second_blocked))

    print("=" * 90)
    print("PHOENIX v7 CORE STEP7 VERIFY")
    print("=" * 90)
    for name, passed in checks:
        print(f"{name:<20}: {'PASS' if passed else 'FAIL'}")
    print("=" * 90)
    if not all(passed for _, passed in checks):
        raise SystemExit("PHOENIX v7 Step7検証: FAIL")
    print("PHOENIX v7 Step7検証: PASS")


if __name__ == "__main__":
    main()
