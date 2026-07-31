# PHOENIX Repository Instructions

## Start here

1. Read `knowledge/00_INDEX.md` first.
2. Follow only the links needed for the current task; do not load every report or log.
3. Confirm the current Git status before editing.

## Safety

- PAPER and read-only RSS work are allowed. Real orders and automatic live enablement are prohibited.
- Never weaken risk limits, freshness checks, readiness gates, or cost assumptions to create favorable results.
- Dry Run must not change broker, order, fill, risk, readiness, or evidence state.
- Never record credentials, account identifiers, cookies, webhooks, or other secrets in repository files.
- Runtime state, logs, generated reports, workbooks, and imported broker data must not be added to Git.

## Memory workflow

- Stable goals and constraints belong in `knowledge/NARRATIVE.md`.
- Approved or superseded architectural decisions belong in `knowledge/DECISIONS.md`; never silently rewrite their history.
- Reusable failure analysis belongs in `knowledge/LESSONS.md`.
- Current priorities and blockers belong in `knowledge/BACKLOG.md`.
- Link to code, commits, and evidence instead of copying large logs into knowledge files.
- The AI may prepare evidence and proposals. Capital deployment and live-trading approval remain human decisions.

## Efficiency

- Run focused tests while editing and one full suite only at a meaningful release boundary.
- Do not repeat successful network downloads or full test runs without a new reason.
- Prefer the existing local cache and repository tools before adding a paid service or dependency.
