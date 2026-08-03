# PHOENIX Current State

Last updated: 2026-08-03

## Repository
- Root: `C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX`
- Origin: `https://github.com/masaA309/PHOENIX.git`
- Branch: `main`
- 正確なHEADは各作業開始時にGitで確認する
- 現在、正本移行は行わない

## Runtime
- Mode: `PAPER`
- Orders submitted: `0`
- 通常Python: `.venv\Scripts\python.exe`
- `Documents\Codex` 内のテストvenvは通常運用用ではない

## Guardian
- Step36 WatchDog: completed
- Step36.5 Repository Guardian: completed
- Step37 Position Reconciliation: completed
- Step38 Heartbeat: completed
- Step39 Fail Safe: implemented、関連18件PASS
- Step40 Disaster Recovery: implemented、関連35件PASS
- Step39/40のGit保存状態は作業開始時に確認する

## Current operational issue
- 2026-08-03 08:00ジョブは開始済み
- Repository Guardian: `READY`
- Position Reconciliation: `BLOCKED`
- Reason: `SOURCE_STATE_STALE`
- positions_count: `4`
- source_timestamp: `2026-07-24T08:30:04+09:00`
- Fail Safe: `POSITION_BLOCKED`
- Heartbeat: `NOT_STARTED`
- 当日通知は未実行

## Historical Replay
- Folds: `7`
- OOS sessions: `1764`
- Trades: `445`
- Profit Factor: `1.221187`
- Max fold drawdown: `12.390433%`
- 目標最大DD: `10.0%以下`

## Existing operational differences
次はコード変更コミットへ混ぜない。
- `data/market_risk_history.csv`
- `data/market_risk_latest.json`
