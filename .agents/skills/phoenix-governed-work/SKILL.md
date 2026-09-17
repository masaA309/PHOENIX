---
name: phoenix-governed-work
description: Use only for PHOENIX Codex runs that execute a frozen governance candidate of type IMPLEMENTATION, GOVERNANCE, or FINAL_ACCEPTANCE. Do not use for ordinary read-only explanation or analysis without a frozen candidate.
---

# PHOENIX Governed Work

Read the active repository `AGENTS.md` first. This skill never expands authority granted by USER, AGENTS, or the frozen candidate.

USER instructions take precedence for intent and authorization. A frozen candidate is not edited in place: any execution-scope change requires a new candidate and required review.

## Route by candidate type

Inspect the frozen candidate's `candidate_type` and read exactly one reference:

- `IMPLEMENTATION` → [references/implementation.md](references/implementation.md)
- `GOVERNANCE` → [references/governance-repair.md](references/governance-repair.md)
- `FINAL_ACCEPTANCE` → [references/final-acceptance.md](references/final-acceptance.md)

Do not load unrelated references "for completeness".

## Shared rules

- Treat `EXECUTION_MANIFEST` as the exact execution-scope authority.
- Do not reconstruct or broaden commands, paths, hashes, tests, proof targets, or safety state from prose.
- Use the task prompt for Objective, Scope, Definition of Done, Stop condition, candidate identity, and any task-specific safety delta only.
- Within the authorized scope, continue to Definition of Done without pausing for intermediate review.
- Stop only on a candidate/AGENTS stop condition, preflight non-PASS, artifact drift, required scope expansion, USER authority boundary, or required safety proof failure.
- If this skill appears to conflict with USER intent or active AGENTS, follow the higher authority and report the exact conflict rather than improvising.
