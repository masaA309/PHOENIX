# PHOENIX RSS Order Bridge Setup

This directory is the workbook-side import location for the RSS order bridge contract.

## Contracted paths

- `runtime/v7_rss_production/order_bridge/outbox/pending`
- `runtime/v7_rss_production/order_bridge/outbox/processing`
- `runtime/v7_rss_production/order_bridge/outbox/processed`
- `runtime/v7_rss_production/order_bridge/outbox/failed`
- `runtime/v7_rss_production/order_bridge/inbox`
- `state/v7_rss_production_order_bridge_state.json`

## Dry-run consumer contract

The repository-side dry-run consumer/writer contract is implemented in:

- [`phoenix_core/rss_order_bridge.py`](../phoenix_core/rss_order_bridge.py)

That contract is what the Python transport and tests use for FILE_READY staging, receipt polling, duplicate suppression, and fail-close behavior.

## Workbook placement

Import the order bridge consumer into the workbook under the PHOENIX repository tree so `ThisWorkbook.Path` can resolve the repository root.

