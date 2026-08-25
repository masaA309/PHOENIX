from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent


def main() -> None:
    from phoenix_core.order_bridge_gate import (
        build_preorder_dispatch_context,
        print_preorder_summary,
        run_order_bridge_gate,
    )

    context = build_preorder_dispatch_context(ROOT_DIR)
    report = run_order_bridge_gate(ROOT_DIR, context=context)
    print_preorder_summary(report)


if __name__ == "__main__":
    main()
