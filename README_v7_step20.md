# PHOENIX v7 Step20

Step20 adds a Rakuten MARKETSPEED II RSS read-only shadow contract. It does not connect to any broker execution path and cannot place, cancel, or modify an order.

## Why this step

The existing realtime CSV reader was not sufficient evidence for a limited pilot: it accepted naive timestamps, did not bind a snapshot to an immutable manifest, did not detect repeated tickers, and was adjacent to a legacy queue writer. Step20 creates an isolated, fail-closed input contract before Excel is connected.

## Evidence flow

1. The audited VBA module exports exactly 20–225 quote rows to an ignored inbox CSV using same-directory atomic replacement.
2. Python validates exact columns, fixed read-only flags, numeric values, `+09:00` timestamps, a 15-second freshness ceiling, JPX trading day/session, unique TSE tickers, and bid/ask consistency.
3. Python requires a separately reviewed workbook attestation, then publishes an immutable content-addressed snapshot and a self-hashed manifest that binds the actual `.xlsm`, its VBA project, tracked VBA source, configuration, JPX calendar, ticker universe, sequence, and source bytes.
4. A shadow session is recorded only after separate manual implementation flags are enabled, at least three immutable captures span four hours or more, morning and post-14:30 samples exist, and every capture covers the complete canonical candidate universe for that date.
5. Shadow sessions credit neither paper days nor audited fills and submit zero external orders.

## Commands

Validate existing evidence without changing inbox, manifest, or shadow state:

```powershell
python -X utf8 rss_shadow_entry_v7.py --dry-run
```

After Excel writes a current snapshot:

```powershell
python -X utf8 rss_shadow_entry_v7.py --publish-current
```

Session capture stays disabled until the real Excel workbook is manually audited. Do not enable it merely to make the staged gate pass.
