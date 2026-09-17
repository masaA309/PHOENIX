# IMPLEMENTATION mode

Use this reference only when the frozen candidate has `candidate_type=IMPLEMENTATION`.

1. Confirm active AGENTS and candidate identity, then run the required preflight before normal repo work.
2. If preflight is not PASS, stop. Do not patch, retry, or redesign in the same run.
3. Read only candidate-authorized files needed for the execution.
4. Modify only the intersection of authorized files, functions, behaviors, commands, assertions, tests, and proof targets.
5. Do not add logging, fallback, validation, observability, tests, refactors, or acceptance conditions that are absent from the frozen scope.
6. Use current source to resolve routine implementation details only when the candidate intentionally leaves multiple equivalent in-scope choices; never use that freedom to alter architecture or authority ownership.
7. Run only candidate-authorized affected tests. Do not widen the suite after PASS unless a new failure or unresolved concern within scope requires it.
8. Continue through the candidate's Definition of Done without pausing for intermediate review.

Stop immediately when any of these occurs:

- artifact/preimage drift
- a required action is outside the frozen scope
- a required safety/runtime precondition is not proven
- a USER-only authority boundary is reached
- a governed command/test returns FAIL or NOT_PROVEN where the candidate requires PASS

On stop, report the exact failed condition and leave unrelated files/state untouched.
