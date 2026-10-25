# Q UI → Claude 引継ぎ

2026-10-25 時点のローカル成果物を収録した移管用スナップショットです。実装の再設計・変更・本番起動は行っていません。

## 読む順序

1. `CURRENT_AND_PLANNED.md` — 実装済みの現物と予定仕様の区別。
2. `source/QUADRANT_TERMINAL_v0.4.0/` — 未commit変更を含む最新ソース、テスト、画像、設定。
3. `design_assets/` — 既存の確定素材 `q_assets_exact.zip` に入っていた6枚。
4. `HISTORICAL_UI_CONVERSATION.md` — 取得できた過去のUI仕様・実装報告。
5. `previous_handoff_kit/` — 既存Claude引継ぎ資料。収集スクリプトは実行せず原本を保存。
6. `source/` の旧バージョンと `original_distribution/` — デザイン・実装履歴。
7. `ALL_FILES.md` — 全ファイルへのリンク。`MANIFEST.json` にSHA-256と収集元を記録。

`Q_UI_TEXT_BUNDLE.md` は最新コード・仕様・引継ぎ文書を一括で読めるテキスト版です。画像と旧版の全文は個別ファイルを参照してください。`Q_UI_CLAUDE_HANDOFF.zip` は全収録物の一括ダウンロードです。

## 現在の依頼と境界

ユーザーはQ UIの成果物・予定物をClaudeへ移管するための収集、リポジトリへの保存・pushを明示承認しました。candidateなしでこの移管に限定して実行する例外も承認済みです。実装・売買設定を変更する承認とは区別してください。

ユーザーの最新情報は「Q本線のファイルは通ってる」です。2026-10-05の会話にあるSHORT owner/path未接続の記述を現在の本線の失敗判定に流用しないでください。本スナップショットでは本線の実行状態・受入を再検証していません。

QはREAD ONLY表示です。UI表示のために注文・risk・broker authorityを追加しないでください。V-LOCKは表示値です。最新のPHOENIX policyは正本リポジトリのAGENTS.mdを参照してください。この移管ブランチは本番mainの置換ではありません。

## 収録範囲と欠落

- canonical workspaceで見つかったQ/旧TERMINALのソース、画像、設定、既存テストとバックアップを収録。
- v0.4.0の作業中変更5ファイルと未追跡テストを収録。元ファイルは変更していません。
- 稼働中RSSブックは実口座データ混入を避けるため未収録。同梱ZIPから確認した空の初期配布テンプレートを代わりに収録し、manifestで由来を明示。
- node_modules、venv、キャッシュ、ビルド出力、ログ、実口座データ、秘密情報、無関係なPHOENIX/QRC本線コードは収録対象外。
- 会話APIから取得できたUI設計継続確認の5ターンを収録。過去会話全体や未取得の添付物まで完全回収したという意味ではありません。
- テスト・ビルド・実機受入は今回再実行していません。過去のPASS記述は当時の報告です。

正本: https://github.com/masaA309/PHOENIX
