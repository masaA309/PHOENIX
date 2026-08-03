# PHOENIX Failure Registry

## F-001 Browser Work misuse
- Status: approved
- 失敗: ブラウザWorkへローカル編集タスクを送った
- 再発防止: PHOENIX実装は現在Codexで開いている正本だけで行う

## F-002 Current fact and future plan mixed
- Status: approved
- 失敗: 未移行の `C:\PHOENIX` を現在の正本として指示した
- 再発防止: `CURRENT_STATE.md` と実際のGitルートを先に確認する

## F-003 Architecture changed without approval
- Status: approved
- 失敗: 合意済みの正本方針を無断変更した
- 再発防止: 理由・利点・欠点・影響を提示し、承認前は変更しない

## F-004 Repeated ineffective commands
- Status: approved
- 失敗: 新情報を得られない確認を繰り返した
- 再発防止: コマンド提示前に得られる新情報を確認する

## F-005 Wrong Python environment
- Status: approved
- 失敗: 通知検証へ古いCodexテストvenvを使い、`python-dotenv` 不足で失敗した
- 再発防止: 通常実行は正本 `.venv\Scripts\python.exe` を最優先する

## F-006 Notification without current report
- Status: approved
- 失敗: 当日レポート未生成で古い結果の通知を試みた
- 再発防止: 当日レポートとデータ基準日時を先に確認する

## F-007 Retry after permission denial
- Status: approved
- 失敗: 同じ書込み不可セッションへ再開指示を出した
- 再発防止: 失敗条件が変わるまで同一セッションへ再送しない

## F-008 Automatic Work handoff
- Status: approved
- 失敗: 禁止後もブラウザWorkへ自動送信した
- 再発防止: PHOENIXでは自動handoffを使用しない

## F-009 Repeated retries and excessive credit use
- Status: approved
- 失敗: 同じ失敗条件のまま再試行を重ね、過剰にクレジットを消費した
- 再発防止: 実行前に新しく分かることを確認し、失敗条件が変わらない限り再試行しない

## F-010 Missing next instruction in completion report
- Status: approved
- 失敗: 完了報告時に保存コマンドまたは次の指示書を同じ返答へ含めなかった
- 再発防止: 完了報告、許可された保存コマンド、次の指示書を1つの返答にまとめる

## F-011 Duplicated long prompt
- Status: approved
- 失敗: 保存済みの共通前提を外部Codex用プロンプトへ重複記載し、長文化した
- 再発防止: `PROMPT_LIBRARY.md` の承認済み短縮テンプレートを使い、保存済み前提を繰り返さない

## F-012 Unverified Work, Codex, or permission claim
- Status: approved
- 失敗: Work、Codex、ツール、権限、ワークスペースの状態を未確認で断定した
- 再発防止: 利用可能なツール、実際の権限、正本ワークスペースを確認してから報告する
