# GOVERNANCE mode

Use this reference only when the frozen candidate has `candidate_type=GOVERNANCE`.

Governance work changes instruction/governance artifacts only within the candidate's exact scope. It does not reopen CLOSED/FROZEN product design and does not grant runtime, trading, broker/RSS, or LIVE authority.

1. Confirm active AGENTS, current machine-governance identities, candidate identity, and required review state.
2. Run the required preflight before normal repo mutation. Non-PASS ends the run.
3. Apply only the exact governance postimages or bounded transformations authorized by the candidate.
4. Do not infer new policy from schema/validator/ledger implementation details. AGENTS remains the permanent-policy source; machine artifacts enforce exact contracts.
5. If the policy change requires machine projection changes, modify only those projection artifacts explicitly listed by the candidate and run only the authorized direct governance test/proof.
6. If machine projection already enforces the resulting policy and the change only removes duplicated prose/scaffolding, do not create schema, validator, test, gate, or failure-class work just to mirror wording.
7. Do not register or close a failure class unless the candidate explicitly authorizes that action and the machine contract is satisfied.
8. Do not perform Git publication unless USER publication authority is explicitly present in the candidate. Local implementation authority is not publication authority. If USER explicitly authorizes derive→review→publish in one bounded request, keep publication limited to the exact candidate-authorized governance paths and verify remote preimage/postimage identity.
9. If the active AGENTS policy cannot be represented by the current machine gate because of a deterministic projection mismatch, a bootstrap projection repair is allowed only when the frozen candidate explicitly proves that blocker, limits writes to the required governance projection artifacts and existing direct governance test, defines rollback, and requires the repaired gate to pass normal preflight afterward. Do not use bootstrap when current preflight can represent the candidate.
10. Continue through the candidate's Definition of Done without an intermediate review stop.

Stop immediately on preimage drift, candidate/report mismatch, machine-projection contradiction, scope expansion requirement, USER-only authority boundary, or governed command/test failure.

A stopped governance run does not self-repair in the same cycle. Preserve evidence and require a new candidate before retrying.
