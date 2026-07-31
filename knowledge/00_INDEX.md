# PHOENIX Operations Memory

This directory is PHOENIX's durable operational memory. It keeps important context in local, plain-text files so that it survives chat, model, editor, and application changes. Obsidian is optional; these files work with any editor.

## Minimal reading route

1. [NARRATIVE.md](NARRATIVE.md) — stable purpose, capital policy, safety, and cost constraints.
2. [BACKLOG.md](BACKLOG.md) — current priorities and blockers.
3. Read [DECISIONS.md](DECISIONS.md) only when changing architecture or policy.
4. Read [LESSONS.md](LESSONS.md) only when diagnosing a known failure class.

## Canonical sources

- Repository rules: [../AGENTS.md](../AGENTS.md)
- Project operating brief: [../PHOENIX_PM_BRIEF.md](../PHOENIX_PM_BRIEF.md)
- Current implementation: [../README_v7_step21.md](../README_v7_step21.md)
- Active policies: [../config](../config)
- Tests: [../tests](../tests)

Generated reports, logs, state, imported market data, and workbooks are evidence artifacts, not durable knowledge. Keep them in their existing ignored runtime locations and link to them only when needed.

## Update rule

- Preserve the user's original intent in `NARRATIVE.md`.
- Append decisions with a date, status, rationale, and evidence.
- Record a lesson only when it is reusable.
- Remove completed backlog items by moving their outcome into `DECISIONS.md` or `LESSONS.md`.
- Do not store secrets or detailed account information here.
