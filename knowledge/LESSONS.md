# PHOENIX Reusable Lessons

## OneDrive and Git metadata

- Symptom: creation of `.git/index.lock` or `.git/COMMIT_EDITMSG` is denied although ordinary source files are writable.
- Cause class: OneDrive/reparse-directory behavior around Git metadata, not a source-code defect.
- Response: keep the canonical Git worktree local and synchronize only a committed source allow-list with blob/hash verification.
- Do not: use destructive Git recovery commands or copy `.git` into OneDrive.

## TLS CA bundle under the runtime path

- Symptom: `curl (77) error setting certificate verify locations` from yfinance/curl_cffi.
- Cause class: provider transport could not reliably use the CA bundle at the original runtime path.
- Response: validate the certifi bundle, materialize a verified local ASCII-path copy, and export it to child processes while keeping TLS verification enabled.
- Do not: disable certificate verification.

## Apparent 224/225 market-data failure during trading hours

- Symptom: batch downloads returned frames, but only one ticker passed freshness validation.
- Cause: most frames included an incomplete same-day daily bar while the freshness gate correctly expected the previous completed JPX session.
- Response: remove only the incomplete current-session row before analysis and require the exact completed session to remain present.
- Do not: treat this symptom as delisting, lower the 225/225 requirement, or accept a partial daily bar.

## Morning notification used unchanged data

- Symptom: the scheduled morning path reported existing candidates without refreshing their source data.
- Cause: `scheduled_entry_v7.py` invoked the direct pipeline path, which consumed an existing `reports/trade_signals.csv`; it did not invoke the daily scanner.
- Response: integrate the verified refresh stage before the scheduled pipeline and stop downstream processing when refresh lineage or completeness fails.
- Status: implementation pending; manual `run_phoenix.py --refresh-only` is verified.

## Verification cost

- Symptom: repeated full suites or market downloads consume time, energy, and model context without increasing evidence.
- Response: use focused tests during editing, one full suite at a release boundary, cache market data, and never ask the user to rerun a successful full verification without a new reason.
