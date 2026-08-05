# PHOENIX Step44 Local VBA Receiver

This directory holds the importable VBA source for the local Step44 receiver.

## Import order

Import these modules into a standard Excel VBA project:

1. `PHOENIX_STEP44_Config.bas`
2. `PHOENIX_STEP44_Csv.bas`
3. `PHOENIX_STEP44_State.bas`
4. `PHOENIX_STEP44_Receiver.bas`

## Entry point

Run this single public macro:

`RunPhoenixStep44LocalReceiver`

## Contracted paths

The VBA receiver reads only the Step43 outbox contract and writes only local receipts and state:

- `runtime/v7_vba_bridge/outbox/pending`
- `runtime/v7_vba_bridge/outbox/processing`
- `runtime/v7_vba_bridge/outbox/complete`
- `runtime/v7_vba_bridge/outbox/rejected`
- `runtime/v7_vba_bridge/inbox`
- `state/v7_vba_bridge_step44_state.csv`
- `reports/v7_vba_bridge_step44_audit.jsonl`

## Safety contract

- Trading actions are disabled.
- No RSS order submission is added.
- Receipts are written as UTF-8 CSV with atomic replacement.
- The receiver fails closed if checksum, schema, time, state, or file writes do not validate.
- The local audit log never stores account credentials or other sensitive secrets.

## Workbook placement

Save the workbook somewhere under the PHOENIX repository tree so `ThisWorkbook.Path` can resolve the repository root.
