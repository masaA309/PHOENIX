from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def main() -> None:
    from phoenix_core.vba_bridge_contract import print_bridge_summary, run_vba_bridge_contract

    report = run_vba_bridge_contract(ROOT_DIR)
    print_bridge_summary(report)


if __name__ == "__main__":
    main()
