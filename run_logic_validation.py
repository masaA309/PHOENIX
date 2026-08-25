from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    sys.path.insert(0, str(ROOT))
    from phoenix_core.logic_validation_runner import main as runner_main

    raise SystemExit(runner_main())


if __name__ == "__main__":
    main()
