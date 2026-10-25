# QUADRANT / Q — Claude Desktop 正式引継ぎ指示

目的：既存QUADRANT/Q（内部名称PHOENIX）を現物ベースで引き継ぎ、VERMILIONからFULL AUTO LIVEまでの既存一本道を継続する。新規プロジェクト、再設計、追加gate、manifest、governanceは作らない。

## 最初の操作
1. 添付の `Q_HANDOFF_EVIDENCE.zip` があれば展開して `MANIFEST.csv`、`COLLECTION_REPORT.json`、`FILES/` を読む。なければ、このPCの既存Windowsファイル・GitHub接続を使用し、`collect_q_handoff.ps1` の読取収集を実行する。収集済みの実物と現行GitHub mainの差異を区別する。
2. `masaA309/PHOENIX` の `AGENTS.md` をfresh-readし、SHA・適用状態・権限境界を確認する。正本は https://github.com/masaA309/PHOENIX 。QRC中継は非公開 `masaA309/qrc-relay-2678fd21`。
3. Windows上の既存QRC Gateway/worker、MCPサーバー、起動設定、ログ、source-access仕様、承認記録を現物で確認する。`qrc_codex_mcp.py` の `qrc_signed_ping` と `qrc_signed_health` は診断用であり、書込・実行権限を持つとみなさない。
4. QRCが既に提供する署名付き操作だけを、その正規プロトコルと既存の承認条件で使用する。GitHubの要求ファイルを作成しただけでWindows実行済みと扱わない。新規認証バイパス・秘密鍵の表示・自動実注文は禁止。
5. 以下の成果物を作成する。証拠のない事項は `NOT_PROVEN` と明記し、推測で埋めない。

## 成果物（同じフォルダへ）
- `01_Q_ARCHITECTURE.md`：Q全体、VERMILION/AZURE/WHITE TIGER/BLACK WARRIOR、PHOENIXとの関係、保護設計
- `02_PROGRESS_EVIDENCE.md`：実装済み・実測済み・未実測の区別、根拠ファイル・SHA
- `03_REMAINING_TASKS.md`：既存一本道の次の未完了事項を優先順で整理（新規gateは禁止）
- `04_QRC_CURRENT_SPEC.md`：Gateway/worker/actor/relay/MCP、署名、要求・応答、承認、常駐、制約
- `04A_QRC_ORIGINAL_REQUIREMENTS.md`：初期要求と現状差分。履歴に根拠がなければNOT_FOUND
- `05_FULL_AUTO_LIVE_PATH.md`：VERMILION優先、broker/RSS実口座照合→信用建玉→注文・約定→費用→検証→LIVE承認境界。AZUREは後続。ユーザーの実注文承認は代行しない。
- `06_SOURCE_INDEX.csv`：出典、パス、ハッシュ、更新時刻、収集結果
- `07_ACCESS_AND_BLOCKERS.md`：Claudeの実際の読取/書込/実行能力、接続テスト、未接続理由と修正可能範囲

## 運用条件
- CLOSED/FROZEN/PROTECTEDを維持し、AGENTS.mdとmachine governanceを優先。
- 追加有料サービス/APIを導入しない。既存QRCを再構築しない。
- 1件のFAILで根拠のない再実行や別ID再送をしない。副作用が不確定ならUNCERTAIN保持。
- 調査・修正は既存の許可済みscope内でのみ実行。新しい権限が必要ならその境界だけ明示。
- 進捗実況ではなく、完成したファイルと監査結果を提示する。
