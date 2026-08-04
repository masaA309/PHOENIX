from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def main() -> None:
    from phoenix_core.order_bridge_gate import print_preorder_summary, run_order_bridge_gate

    report = run_order_bridge_gate(ROOT_DIR)
    print_preorder_summary(report)


if __name__ == "__main__":
    main()
