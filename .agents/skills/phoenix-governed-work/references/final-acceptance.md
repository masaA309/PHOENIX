# FINAL_ACCEPTANCE mode

Use this reference only when the frozen candidate has `candidate_type=FINAL_ACCEPTANCE`.

Final acceptance is a pre-calibrated single cycle, not an interactive debugging session.

1. Confirm active AGENTS, exact candidate/report identities, all required runtime preconditions, rollback path, and USER authority before the first mutation.
2. Run the required preflight. Non-PASS ends the cycle before acceptance mutation.
3. Execute only the candidate-authorized USER_MACHINE operation count and governed commands.
4. Capture only the proof targets named by the candidate. Do not add exploratory diagnostics during acceptance.
5. If a required proof fails, an assumption is disproven, artifact/state drifts, or rollback is required, mark the cycle FAIL and stop.
6. Do not patch, repair, change method, or rerun acceptance in the same cycle.
7. Do not ask USER to search files, choose implementation values, or relay iterative error output that can be collected mechanically.
8. Final acceptance does not itself grant LIVE, arming, broker/RSS economic mutation, Git publication, or other protected authority. Those require their own exact USER authorization in the candidate.
9. If rollback is candidate-authorized and required, perform only that rollback and then stop.

Report the resulting proof identities and PASS/FAIL/NOT_PROVEN branch exactly. Do not turn a safe stop into a PASS.
