# PHOENIX Backlog

Last reviewed: 2026-07-24

## P0 — Scheduled fresh-data chain

- Run the verified daily refresh before the 08:00 scheduled direct pipeline.
- Require the current run's report, manifest/hash lineage, exact JPX completed session, and complete 225-ticker universe.
- Stop before candidate execution when refresh fails; never fall back silently to yesterday's `trade_signals.csv`.
- Keep Dry Run broker/order/risk/evidence state unchanged.

## P1 — Read-only MarketSpeed II RSS onboarding

- Install desktop Excel 365.
- Register the matching 32/64-bit MarketSpeed II RSS XLL and the VBA XLAM.
- Complete the official RSS consent/connect procedure while MarketSpeed II is logged in.
- Validate market-data functions and chart history in a read-only workbook.
- Export atomically into the existing Step20 shadow contract; do not add order functions.

## P1 — Kabu Mini eligibility evidence

- Export and manually review the current eligible-symbol CSV.
- Import it through the Step21 eligibility command and retain its hash/source evidence.
- Missing or stale eligibility continues to block mini-share virtual fills.

## P1 — Evidence collection

- Continue distinct paper-day and audited-fill collection without counting Dry Runs, replays, baselines, or repeated same-day runs.
- Review cost-adjusted performance before any additional 200,000-yen contribution or staged-pilot proposal.

## P2 — Data-provider reduction

- After RSS validation, prefer RSS for live Japanese-equity quotes and supported chart history.
- Retain provider isolation and cache-based recovery; do not make one external public endpoint a single point of failure.

## Deferred research

- US-dollar asset allocation.
- Dividend-income portfolio design.
- These begin only after the Japanese-equity evidence and operating-cost model are stable.
