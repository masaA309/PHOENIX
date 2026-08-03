# PHOENIX Next Step

Last updated: 2026-08-03

## Codex execution guardrails
- 現在の依頼を過去の記憶より常に優先し、1タスク1目的で進める。
- 実行前に何が新しく分かるかを確認し、同じ失敗条件のまま再試行しない。
- ブラウザWork、自動handoff、別worktree、別コピーへ作業を送らない。
- 保存済み共通前提を長文で重複せず、外部Codexには `PROMPT_LIBRARY.md` の承認済み短縮テンプレートを使う。
- ツール、権限、正本ワークスペースを確認してから事実を報告する。
- 完了報告、許可された保存コマンド、次の指示書を同じ返答にまとめる。
- 新しい記憶はユーザー承認前に `approved` にしない。

## Priority 1
Step39とStep40のGit保存状態を確認し、未保存なら対象ファイルだけを保存する。

## Priority 2
`SOURCE_STATE_STALE` を正規経路で解消する。

- 古い `positions_count=4` を勝手に0へ変更しない
- 現在のPAPERポジション状態を再生成する
- Position Reconciliationを `READY` へ戻す
- GuardianやFail Safeを迂回しない

## Priority 3
当日データを正規経路で更新する。

- 当日 `report_YYYYMMDD.csv` を生成
- データ基準日時を確認
- 正本 `.venv\Scripts\python.exe` で通知を1回検証
- 古い結果を現在結果として送信しない

## Parallel work
Historical Replayの最大DD改善分析。

- PF: `1.221187`
- 最大DD: `12.390433%`
- Trades: `445`
- 目標DD: `10.0%以下`
