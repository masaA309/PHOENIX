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

<!-- PHOENIX_MEMORY_RULES_START -->
# PHOENIX Codex Rules

## 作業開始前
1. `knowledge/CURRENT_STATE.md` を読む。
2. `knowledge/NEXT_STEP.md` を読む。
3. 設計判断が関係する場合は `knowledge/DECISIONS.md` を読む。
4. `knowledge/FAILURES.md` で同種の失敗を確認する。
5. 現在のユーザー指示を最優先する。

## 作業領域
- 正本は `CURRENT_STATE.md` に記載されたGitリポジトリだけ。
- ブラウザWorkへPHOENIX実装タスクを送らない。
- `Documents\Codex`、別worktree、別コピーを正本にしない。
- 正本パスやアーキテクチャを無断変更しない。
- 現在の事実と将来案を混同しない。

## 実装
- 合意済み仕様を無断変更しない。
- アーキテクチャ変更が必要なら実装せず報告する。
- 無関係な調査、全体テスト、リファクタリングをしない。
- 同じ原因で2回失敗したら停止する。
- 指定された保護対象へ触れない。

## Python
- 通常実行・通知・運用検証は正本の `.venv\Scripts\python.exe` を最優先する。
- `Documents\Codex` 内のテストvenvを通常運用へ使わない。
- 代替Pythonを使う場合は理由、絶対パス、依存関係差を報告する。
- PATH変更やパッケージ導入を無断で行わない。

## 通知
- 通知前に当日レポートとデータ基準日時を確認する。
- 古い結果を現在結果として送信しない。
- Guardian、Position Reconciliation、Fail Safeを迂回しない。
- `PAPER` と `Orders submitted: 0` を維持する。

## 作業終了後
変更ファイル、テスト結果、保護対象、Git操作、外部接続を報告する。
新しい記憶は、ユーザー承認前に確定ルールへ昇格させない。
<!-- PHOENIX_MEMORY_RULES_END -->
