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
