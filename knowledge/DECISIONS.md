# PHOENIX Decision Log

Decisions are append-only. A newer entry may supersede an older one, but the older rationale remains visible.

## D-001 — Keep real trading disabled

- Date: 2026-07-24
- Status: ACTIVE
- Decision: PHOENIX remains PAPER/read-only. No code path may automatically enable live trading or submit a real order.
- Rationale: Operational evidence and the broker integration contract are not yet complete.
- Evidence: Step14–Step21 readiness and isolation tests.

## D-002 — Use historical replay as supplementary evidence

- Date: 2026-07-24
- Status: ACTIVE
- Decision: Historical walk-forward replay is used to accelerate strategy validation without crediting replay sessions as real paper-trading days or real fills.
- Rationale: It improves development speed while preventing hindsight evidence from replacing live observation.
- Evidence: Step17 and Step17.1 implementation and tests.

## D-003 — Include all material trading costs

- Date: 2026-07-24
- Status: ACTIVE
- Decision: Results must include commission evidence or a conservative reserve, spread/slippage, tax reserve, and 7,000 yen monthly fixed cost before distribution decisions.
- Rationale: Gross profit is not spendable profit.
- Evidence: Step19 economics policy and tests.

## D-004 — Use an isolated read-only RSS bridge first

- Date: 2026-07-24
- Status: ACTIVE
- Decision: MarketSpeed II RSS will first provide market and historical data through desktop Excel. PHOENIX consumes a validated, atomic export; RSS order functions remain excluded.
- Rationale: The official Excel interface can remove public-quote dependence without exposing capital during integration.
- Evidence: Step20 RSS shadow contract and Step21 virtual RSS ledger.

## D-005 — Develop locally and synchronize source safely

- Date: 2026-07-24
- Status: SUPERSEDED by D-007
- Decision: Git development occurs in the local Codex workspace. A hash-checked allow-list script copies committed source files to the OneDrive runtime workspace without Git metadata or runtime artifacts.
- Rationale: OneDrive reparse behavior intermittently denied normal Git lock and commit-message files.
- Evidence: `sync_step21_to_onedrive.ps1` and its preflight verification.

## D-006 — Use completed JPX sessions for daily indicators

- Date: 2026-07-24
- Status: ACTIVE
- Decision: Before the JPX cash close, an in-progress same-day daily bar is excluded and indicators end at the exact latest completed JPX session. Missing, stale, or future data still fails closed.
- Rationale: A public provider may expose a partial daily row during trading hours; it must neither enter signals nor make the previous completed session appear stale.
- Evidence: commit `fa3cf24b7c65f6c1651b85c56ba4d164cd85399c`; 225/225 live refresh and 290 passing tests.

## D-007 — Use the OneDrive PHOENIX repository as the sole canonical workspace

- Date: 2026-08-02
- Status: ACTIVE
- Decision: `C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX` is the only canonical PHOENIX development and runtime repository. Copies under `Documents\Codex`, worktrees, and other duplicate folders must not be used as the development source of truth.
- Rationale: A single guarded repository prevents source divergence and accidental execution or editing of stale copies.
- Evidence: Phase3 Step36.5 Repository Guardian and its focused tests.
