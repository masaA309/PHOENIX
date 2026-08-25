# PHOENIX Failure Registry

## F-001 Browser Work misuse
- Status: approved
- 失敗: ブラウザWorkへローカル編集タスクを送った
- 再発防止: PHOENIX実装は現在Codexで開いている正本だけで行う

## F-002 Current fact and future plan mixed
- Status: approved
- 失敗: 未移行の `C:\PHOENIX` を現在の正本として指示した
- 再発防止: `CURRENT_STATE.md` と実際の正本を先に確認する

## F-003 Architecture changed without approval
- Status: approved
- 失敗: 合意済みの正本方針を無断変更した
- 再発防止: 理由・利点・欠点・影響を提示し、承認前は変更しない

## F-004 Repeated ineffective commands
- Status: approved
- 失敗: 新情報を得られない確認コマンドを繰り返した
- 再発防止: 初回実行前に得られる新情報を確認し、YESでない操作は行わない

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
- 再発防止: 権限または実行環境が変わるまで同一セッションへ再送しない

## F-008 Automatic Work handoff
- Status: approved
- 失敗: 禁止後もブラウザWorkへ自動送信した
- 再発防止: PHOENIXでは自動handoffを使用しない

## F-009 Two-failure stop and credit control not applied
- Status: approved
- 失敗: 失敗条件を変えない再実行と2回失敗後の続行により、クレジット、時間、ユーザー操作を浪費した
- 原因分析: 再実行前の新情報・失敗条件確認と停止基準が実行手順へ組み込まれていなかった
- 最小修正: 初回は新情報が得られる場合だけ実行し、再実行は失敗条件も変わった場合だけ許可し、2回失敗で停止する
- 検証: 再実行時に新情報と変更された失敗条件を説明でき、2回目の失敗後に追加実行がないことを確認する
- 標準化: `AGENTS.md` の「最優先目標」「実行判断」と `PROMPT_LIBRARY.md` の「再試行」「クレジット節約」へ統合する
- 次回確認: 実行履歴に同条件の3回目がなく、再開条件が明記されているか確認する

## F-010 Completion response missing required parts
- Status: approved
- 失敗: 完了時に、完了確認、保存コマンド、次のCodex指示書の一部を同じ返答へ含めなかった
- 原因分析: 作業完了と回答完了を分け、固定の回答形式で確認していなかった
- 最小修正: 毎回、3項目を同じ返答へ順番どおり記載し、禁止された保存操作は「保存コマンドなし」と明記する
- 検証: 返答に①完了確認、②保存コマンド、③次のCodex指示書がすべて存在することを確認する
- 標準化: `AGENTS.md` の「回答形式」と `PROMPT_LIBRARY.md` の「完了報告」「保存」へ統合する
- 次回確認: 完了返答を送る前に3項目の欠落がないか確認する

## F-011 Prompt duplication and scope expansion
- Status: approved
- 失敗: 保存済みの共通前提や複数目的をプロンプトへ重複記載し、長文化と作業範囲拡大を招いた
- 原因分析: 用途別テンプレートの役割が重なり、必要なテンプレートだけを選ぶ基準がなかった
- 最小修正: テンプレートを8用途へ限定し、共通ルールは `AGENTS.md` を参照して、目的・対象・保護対象だけを差し込む
- 検証: 使用プロンプトが1目的で、保存済みルールの長文複製と無関係な指示を含まないことを確認する
- 標準化: `AGENTS.md` の「タスク管理」「AGENTS管理」と整理済み `PROMPT_LIBRARY.md` へ統合する
- 次回確認: 新規プロンプトを追加せず、既存8テンプレートのいずれかを統合更新しているか確認する

## F-012 Unverified environment or capability claim
- Status: approved
- 失敗: Codex、ツール、権限、正本ワークスペース、実行状態を未確認のまま断定した
- 原因分析: 予定・推測・実測結果の区別をせず、作業開始時の確認が不足していた
- 最小修正: 必要な事実だけを読み取りで確認し、確認できない事項は未確認と明記する
- 検証: 各状態報告に確認結果があり、将来案を現在の事実として扱っていないことを確認する
- 標準化: `AGENTS.md` の「基本原則」「作業開始」と `PROMPT_LIBRARY.md` の「新規タスク開始」へ統合する
- 次回確認: 最初の実行前に正本、ツール、権限、変更対象、保護対象を確認したか確認する

## F-013 Improvement was not standardized
- Status: approved
- 失敗: 改善が標準化されなかったため、最小修正と検証後もルール、テンプレート、Failure、次回確認へ反映されず再発した
- 原因分析: 修正と検証を改善完了とみなし、PDCA/SDCAの標準化工程を省略し、類似ルールを追記で分散させた
- 最小修正: 原因分析、最小修正、検証、標準化、AGENTS統合、PROMPT_LIBRARY更新、FAILURES更新、次回確認までを一続きで完了する
- 検証: `AGENTS.md` に1テーマ1ルールで統合され、対応テンプレートとFailureが更新され、次回確認項目が存在することを確認する
- 標準化: `AGENTS.md` の「標準化（PDCA/SDCA）」「AGENTS管理」を唯一の標準とし、追記ではなく既存内容を統合更新する
- 次回確認: 同種ミスの次回作業で標準が実際に参照され、8工程の欠落と重複ルールがないか確認する

## F-014 Production RSS workbook path drift
- Status: approved
- 失敗: ProductionRakutenRssTransport が `.invalid_backup` を含む非正規Workbook候補を選択し、Excel が誤ったファイルを開こうとした
- 原因分析: 生成入口が外部の `workbook_path` に従っており、正規Workbookの固定値より候補探索やバックアップ名の混入を許していた
- 最小修正: `runtime/v7_rss_production/PHOENIX_RSS_PRODUCTION.xlsm` に固定し、live Workbook が既に開かれている場合のみ再利用し、それ以外は正規 `.xlsm` のみを開く
- 検証: step48/49 は PASS、canonical workbook path は PASS、`.invalid_backup` selected は NO、実機 health_check は Excel 不在で FAIL
- 標準化: `AGENTS.md` の workbook固定方針と `PROMPT_LIBRARY.md` の RSS workbook固定テンプレートへ統合する
- 次回確認: `backup/old/tmp/.invalid_backup` を Workbook 候補にしていないか、変更前に確認する
