# Q UI — current source and handoff documents

Snapshot: 2026-10-25. Historical claims are not current verification. Binary assets and legacy source are linked in ALL_FILES.md.

## CLAUDE_START_HERE.md

````text
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

````

## CURRENT_AND_PLANNED.md

````text
# 現物と予定仕様

## 現物で確認できる成果物

- `source/QUADRANT_TERMINAL_v0.4.0/frontend/src/App.tsx`: Q画面、保有・分析・来歴・接続状態・privacy表示。React/TypeScript。
- `frontend/src/components/MarketChart.tsx`: チャート。`styles.css`: デザイン。`types.ts`: API表示型。
- `frontend/public/`: guardian画像、Qアイコン、PWA manifest/service worker。
- `frontend/src-tauri/`: Tauriデスクトップ構成。
- `backend/app.py`: FastAPIのsnapshot/chart/diagnostics/healthとWebSocket。既定データソースはrss。
- `backend/rss_readonly.py`: Excel/RSSの読取adapter、注文関数境界確認、チャート取得、信用情報読取処理。
- `backend/phoenix_analysis_readonly.py`: Morning Screening/Intraday成果物の読取と来歴。日付基準のSTALE。
- `backend/tests/test_rss_readonly.py` と `tests/test_margin_readonly.py`: 既存の対象テスト。今回の実行結果はありません。
- `rss/`: 読取ブリッジ説明と、口座データのない初期配布ブック。
- v0.3.2、SHISHIN v0.3.0、PHOENIX TERMINAL v0.1/v0.1.1、v0.4.0内バックアップ: 履歴参照用。

## 過去の合意・予定（新しい設計ではない）

出典は `HISTORICAL_UI_CONVERSATION.md` の2026-10-05の記録。細部がその記録にない項目は推測で補完していません。

- QUADRANT family: VERMILION / AZURE / WHITE TIGER / BLACK WARRIOR。内部engine名と売買authorityを表示ブランドから分離。
- LONG/SHORTとCASH/MARGINを別々に表示。unknownをLONGへ決め打ちしない。
- POSITIONS / DETAIL / CHARTに、正式stateに基づくProtection情報を表示する。
- 現在stop、current R、TRAILING、EXIT_PENDING、pending stop、発効session、保有session、exit reason、freshness、authorityを扱う計画。
- V-LOCKは費用込み利益保護を示すQ表示。ACTIVE / INACTIVE / NOT_PROVENを区別し、売買ロジックへ書き戻さない。
- Market BriefとMorning Screeningは別の表示要素として扱う計画。取得記録にMarket Briefの詳細仕様全文は存在しない。
- 正式な本線read surfaceからQ adapter → API → UIへ接続し、staging/test stateを本番と推測しない。

## 実装と計画の差を読む注意点

`Position`型にはside、execution、status、current_stop、current_r、v_lock_displayが存在しますが、型があることは全項目の正式runtime接続・画面完成を証明しません。取得時のUIにはSHORT RUNTIME NOT_CONNECTEDの表示経路があります。Q本線についてユーザーは通過済みと述べており、本移管では本線を再判定していません。

過去会話のPositionView計画にはpending_stop等もあります。最新ソースとの差は将来の実装確認事項であり、本移管で追加実装していません。

今後Claudeへ依頼する実装範囲はユーザーが指定してください。この資料自体は新たな実装・発注・LIVE releaseを許可しません。

````

## HISTORICAL_UI_CONVERSATION.md

````text
# Q UI conversation evidence

Retrieved 2026-10-25 from UI設計継続確認. These are historical statements, not current runtime verification. The history API exposed only the turns below; older designs may be absent. Current user states Q mainline files have passed. Do not treat the 2026-10-05 blockers as current facts.

## 2026-10-05T14:36:46.985Z (db8894cd-f636-4694-b551-38c4891ca290)

### userMessage

進めて

### agentMessage

進めました。残っていた一点は**推測せずに結論まで確定**できました。

### SHORT runtimeのcanonical read source/path

結論は、**現時点では固定canonical pathは存在しません。**

現物 `strategy_execution_runtime.py` を追うと、production SHORT session owner は、

`run_short_gen1_production_runtime_session(checkpoint_path: Path, ...)`

という構造です。

そして実行条件は明確で、

- 呼び出し側から `checkpoint_path` を渡す
- そのファイルが既に存在していなければFAIL
- そこからruntime stateをload
- sessionをadvance
- **同じ `checkpoint_path` へstateを保存**

となっています。

つまり本線runtimeには正式なcheckpoint **schema / serializer / lifecycle** はありますが、

`C:\dev\PHOENIX\state\xxx.json`

のような**唯一のproduction checkpoint locationをruntime自身がcanonical固定しているわけではありません。**

検索で見つかった `state/governance/incoming/...` 群は実装candidate・承認・監査成果物です。**LIVE runtime stateそのものとしてQが読んではいけません。**

---

## ここでUI境界を確定

したがってQ側から、

「たぶんこのJSONだろう」

と探し回る実装は禁止します。

本番QのSHORT接続は、

**PHOENIX runtime  
→ 明示的に指定されたREAD ONLY checkpoint  
→ Q adapter  
→ Q API  
→ UI**

だけを許可します。

checkpoint sourceがまだ本線側で正式に指定されていない状態では、Qは正直に

**`SHORT RUNTIME — NOT CONNECTED`**

と表示します。

これはFAILではなく、authorityを捏造しないための正常状態です。

### Q側のデータ契約

これで本番UI側は、本線変更なしで次の形まで固定できます。

```text
PositionView
  side                 LONG | SHORT | NOT_PROVEN
  execution            CASH | MARGIN | NOT_PROVEN
  entry_price
  current_price
  quantity
  pnl
  pnl_pct
  current_r
  status               HOLDING | TRAILING | EXIT_PENDING | NOT_PROVEN
  current_stop
  pending_stop
  pending_stop_effective_session
  held_sessions
  exit_reason
  freshness
  authority
  v_lock_display       ACTIVE | INACTIVE | NOT_PROVEN
```

ここで `v_lock_display` は**Qだけの表示値**。PHOENIXへ書き戻しません。

また、SHORTで `effective_stop` がEntryより利益側へ移っていても、コスト控除後利益が証明できなければ `V-LOCK = NOT_PROVEN` のままです。

---

## ゼロ視点・第三者・最深部監査結果

ここで一つ重要な修正があります。

前段で「canonical checkpoint pathを特定すれば接続実装へ進める」としていましたが、現物確認の結果、**探せば見つかる固定pathではなく、呼び出し側から注入されるpath**でした。

したがって存在しないcanonical pathをさらに探索するのは中止します。これは無駄な探索になります。

本線2号でそのowner/pathが正式確定した時点で、Qへ設定値として渡せばよく、**そのためにPHOENIX本線設計へUI側から要求を出す必要もありません。**

これで本番Qは、本線2号の設計進行を待たずに作れる部分と、authority成立まで `NOT CONNECTED / NOT PROVEN` にすべき部分を完全に分離できました。

**PHOENIX変更 0 / governance追加 0 / LIVE変更 0 / Codex使用 0 / DEMO依存 0。**

次の未完了境界はもう探索ではありません。**この契約を既存v0.4.0へ適用する本UI実装境界**です。

## 2026-10-05T14:40:50.694Z (af5a4b54-2ac7-4e56-9784-ebdf2c71a8ed)

### userMessage

進めて

### agentMessage

進めました。**実装直前のpreflightまで完了**です。

fresh-readした `AGENTS.md` のSHA-256は  
`3612B039F37B7BED23266A1884404C8A4DD015DB4FE2D2DF234698CF89C2AD6D`。

さらに `QUADRANT_TERMINAL_v0.4.0` をGitで限定確認した結果、

- tracked済み
- `git status --short -- QUADRANT_TERMINAL_v0.4.0` → **変更なし**
- `git diff --name-only -- QUADRANT_TERMINAL_v0.4.0` → **差分なし**
- PHOENIX本線側に存在する大量の進行中変更とは、変更対象をパス単位で分離可能

まで確認しました。

ここで、前に「PHOENIX repo内だからQを触るのは危険」と広く止めた判断を修正します。**repo全体を触るのは危険ですが、現在cleanな `QUADRANT_TERMINAL_v0.4.0` の限定変更なら、本線ロジックを変更せずに実装境界を切れます。**

実装対象も絞れています。第一実装単位は、①mock silent fallback排除、②Morning Screeningの36時間STALEをJST当日基準へ修正、③RSSの`side="LONG"`固定を廃止して不明時は`NOT_PROVEN`、④UI型を `SIDE` と `EXECUTION` の独立authorityに変更、⑤SHORT runtime未接続時は`SHORT RUNTIME — NOT CONNECTED`、⑥V-LOCKは売買stateにせず `ACTIVE / INACTIVE / NOT_PROVEN` のQ表示値だけ、です。

**SHORT trigger・trailing・exit・broker・runtime・checkpoint ownerには一切変更を加えません。** MARKET BRIEFや大規模画面再構築もこの変更へ混ぜません。

ゼロ視点・第三者多角・最深部監査後も、この第一実装単位で本線への逆流はありません。現在は **canonical変更 0 / LIVE変更 0 / Codex使用 0** のまま、**Q UI限定実装の人間承認境界**まで到達しました。

次に実際のtrackedファイルを書き換えるため、ここだけは承認が必要です。  
**`IMPLEMENTATION:quadrant_terminal_v040_readonly_ui_alignment_20261005`** の実装承認をください。

## 2026-10-05T14:43:13.209Z (7933925e-0ff5-4841-adf7-2330c614ff6c)

### userMessage

IMPLEMENTATION:quadrant_terminal_v040_readonly_ui_alignment_20261005 の実装承認

### agentMessage

実装承認分を完了しました。

`IMPLEMENTATION:quadrant_terminal_v040_readonly_ui_alignment_20261005` の変更は **`QUADRANT_TERMINAL_v0.4.0` 内の5ファイルだけ**です。

- production既定データソースを `rss` に変更。起動直後や接続失敗時のmock silent fallbackを排除。
- Morning Screeningの36時間STALE判定を廃止し、**JST当日生成のみTODAY／日付が変わればSTALE**へ修正。
- RSS positionの強制 `LONG` を廃止。authorityがないため `side=NOT_PROVEN / execution=NOT_PROVEN`。
- Position型を `SIDE / EXECUTION / STATUS / Current Stop / Current R / V-LOCK display` に対応。
- `V-LOCK` は `ACTIVE / INACTIVE / NOT_PROVEN` の**Q表示値のみ**。売買authorityにはしていません。
- SHORT runtime未接続を明示的に `SHORT RUNTIME · NOT_CONNECTED` と表示。
- watchlistに存在しない実保有positionも消えずに表示可能へ修正。
- rankingが存在しない場合にwatchlistから候補を捏造するfallbackを削除。
- LONG式 `(last/avg-1)` でposition P/L%を再計算していた処理を削除。SHORTをLONG式で誤計算しないよう修正。
- stream切断時もmock表示へ落とさず `DISCONNECTED`。

監査・検証結果は、**Python compile PASS、既存RSS focused tests 3/3 PASS、TypeScript + Vite production build PASS、`git diff --check` PASS**です。pytest自体は両venvに未導入だったため、追加installはせず、既存3テスト関数を同じPython環境から直接実行して全PASSを確認しました。

途中、最初の編集試行でPowerShellの文字コード問題により `rss_readonly.py` が文字化けしましたが、**即座にHEADのexact preimageへ復元してdiff=0を確認してからUTF-8方式で再実装**しています。最終監査にはその破損は残っていません。

現在の変更対象はこの5ファイルのみです。既存のPHOENIX本線側の作業中差分には触れていません。Git add/commit/pushもしていません。LIVE注文・broker mutationも0です。

この承認scopeの実装はここで完了です。次の本UI未完了境界は、**POSITIONSの正式なProtection/Detail/Chart表示へ、証明済みauthorityだけを接続する段階**です。

## 2026-10-05T14:48:42.395Z (33a64f15-698d-46b4-8c84-2adc565c3604)

### userMessage

進めて

### agentMessage

進めました。次の未完了境界について、実装前の現物監査まで完了しています。

結論は、**現在のQ UIからSHORT production runtimeのProtection情報を直接接続してはいけません**。現物ではSHORT production側に `entry_price / initial_r / effective_stop / held_sessions / highest_reached_r_level / pending_stop / pending_closes` まで正式な状態構造が存在します。一方、そのcheckpointを実運用で所有・更新してQがREAD ONLYで参照できる**production owner/path がまだ成立していません**。`run_short_gen1_production_runtime_session()` も現状は本体から呼ばれておらず、tests/staging以外に実呼出しがありません。

したがって、ここでUI側が `effective_stop` 等を勝手に探索して拾う実装をすると、過去の候補・staging・test stateをproduction stateと誤認する危険があります。これは禁止です。

さらに確認できた重要点は、SHORT runtime自体には正式に以下が存在します。

- SIDE = SHORTを確定できるposition identity
- EXECUTION = margin SHORT lifecycle
- ENTRY = `entry_price`
- CURRENT STOP = `effective_stop`
- INITIAL R = `initial_r`
- TRAILING進行 = `highest_reached_r_level`
- 次session stop = `pending_stop`
- EXIT_PENDING = `pending_closes`
- holding期間 = `held_sessions`

一方、**V-LOCKはruntime authorityに存在しません**。従来どおりQ表示専用です。また現在のSHORT cost authorityにはNOT_PROVEN要素が残るため、利益確保を費用控除後まで証明できない場合はVを点灯させません。

よって次の一本道は確定しました。

**「SHORT production runtime checkpointの正式owner/pathを本線で成立させる」→ その確定したREAD ONLY surfaceだけをQのPOSITIONS / DETAIL / CHARTへ接続する。**

ここを飛ばしてUIだけ作り込むことはしません。また、今回の確認では既存Q UI差分以外を変更しておらず、Codexも使用していません。既存の大量のPHOENIX本線差分にも触れていません。

なお、これは新しいUI gateを作ったのではなく、現在のPOSITIONS正式接続に必要な**未成立依存を現物から特定した結果**です。次はこのowner/path境界を、本線の現在状態と衝突させず閉じるところから進めます。

## 2026-10-05T14:50:49.434Z (2f017aeb-484c-4f45-b603-5f109a71d18f)

### userMessage

やはり注文ロジックは先に閉じて本線に結合しないとダメか

### agentMessage

はい。**現状の現物を確認した限り、その順序が正しいです。**

ただし「Q UIを全部止める」という意味ではありません。境界を分ける必要があります。

**本線で先に閉じる必要があるもの**は、実際の売買状態を決める部分です。特にSHORTについては、発注トリガー → 建玉成立 → 保有 → `effective_stop` / trailing step-up → EXIT trigger → EXIT_PENDING → 発注・約定・reconciliation → 状態永続化までを、本線のproduction lifecycleとして一本につなぐ必要があります。今は各構成要素はかなり存在していますが、先ほど確認したようにproduction runtime sessionの正式owner/pathがまだ実運用本線につながっていません。

そのため、今Q UIを先行して本接続すると、UI側が「どの状態が現在の正式状態なのか」を独自判断することになります。これは避けるべきです。特に **TRAILING、Current Stop、R、EXIT_PENDING、V表示** が危険です。

一方で、UIの確定済み仕様はそのまま保持できます。LONG/SHORT表示、CASH/MARGIN分離、POSITIONS/DETAIL/CHARTのレイアウト、Vアイコンのデザイン、Market Brief、Morning Screeningとの分離などをやり直す必要はありません。

したがって一本道は、

**① SHORT注文・決済lifecycleを閉じる  
→ ② production runtimeの正式owner/stateを本線へ結合  
→ ③ その確定stateをREAD ONLY境界としてQへ公開  
→ ④ Q本番UIを接続  
→ ⑤ FULL AUTO LIVE側の次の未完了境界へ**

です。

特に重要なのは、**V-LOCKを注文ロジックへ戻さないこと**です。TRAIL/stopは本線の売買ロジック、Vは確定した本線stateをQが読んで「費用込みで利益保護済み」と表示するUI機能、という分離は維持します。

なので、今はUIを無理に完成させるより、**本線2号で進めているSHORT発注トリガーを含む注文・決済ロジックを先に閉じて本線結合する**のが最短です。その後ならQ UIは推測なしで正式stateへ接続できます。



````

## previous_handoff_kit/CLAUDE_HANDOFF_PROMPT.md

````text
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

````

## previous_handoff_kit/collect_q_handoff.ps1

````text
﻿#requires -Version 5.1
param(
 [string]$OutputDir = (Join-Path $env:USERPROFILE 'Desktop\Q_Claude_Handoff'),
 [switch]$IncludeSource
)
$ErrorActionPreference='Stop'
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$work=Join-Path $OutputDir "Q_HANDOFF_$stamp"
$files=Join-Path $work 'FILES'
New-Item -ItemType Directory -Path $files -Force | Out-Null
$records=New-Object 'System.Collections.Generic.List[object]'
$notes=New-Object 'System.Collections.Generic.List[string]'
$homeRoot=Join-Path $env:USERPROFILE 'Documents\Codex'
$roots=@(
 (Join-Path $homeRoot '2026-10-18\referenced-chatgpt-conversation-this-is-an\work\QRC_DIRECT_GATEWAY_V2'),
 'C:\QRC_149_RC6_Product_Development_Candidate'
)
# No broad disk crawl. Existing known roots only.
$patterns=@('AGENTS.md','*MANIFEST*.sha256','*QRC*SPEC*.md','*QRC*REQUIREMENT*.md','*QRC*ACCEPTANCE*.md',
 '*GATEWAY*.md','*VERMILION*.md','*PHOENIX*.md','*AZURE*.md','*SHORT*.md',
 '*LONG*.md','*QRC*HANDOFF*.md','*QRC*PROTOCOL*.md')
$deny='(?i)(secret|credential|token|password|private.?key|hmac.?key|\.env|id_rsa|\.pem$|\.pfx$|\.db$|\.sqlite|\.git\\)'
$limit=3MB
$maxTotal=35MB
$total=0L
foreach($base in $roots) {
 if(!(Test-Path -LiteralPath $base)){ $notes.Add("NOT_FOUND root: $base");continue }
 $notes.Add("FOUND root: $base")
 foreach($pattern in $patterns){
  Get-ChildItem -LiteralPath $base -File -Recurse -Filter $pattern -ErrorAction SilentlyContinue |
   ForEach-Object {
    $f=$_
    if($f.FullName -match $deny -or $f.Length -gt $limit -or $total+$f.Length -gt $maxTotal){return}
    $relative=$f.FullName.Substring($base.Length).TrimStart('\')
    $label=if($base -like 'C:\QRC*'){'QRC_PRODUCT'}else{'GATEWAY_V2'}
    $dest=Join-Path (Join-Path $files $label) $relative
    if(Test-Path -LiteralPath $dest){return}
    $parent=Split-Path $dest -Parent
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    try {
     Copy-Item -LiteralPath $f.FullName -Destination $dest -ErrorAction Stop
     $hash=(Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
     $records.Add([pscustomobject]@{Origin=$f.FullName;Collected=$dest.Substring($work.Length+1);SHA256=$hash;Bytes=$f.Length;ModifiedUTC=$f.LastWriteTimeUtc.ToString('o')})
     $total+=$f.Length
    }catch{$notes.Add("SKIP: $($f.FullName)")}
   }
 }
}
# Optional code: only source files from known QRC Gateway root, never .env/keys.
if($IncludeSource -and (Test-Path $roots[0])) {
 Get-ChildItem -LiteralPath $roots[0] -File -Filter '*.py' -ErrorAction SilentlyContinue |
  ForEach-Object {
   $f=$_; if($f.FullName -match $deny -or $f.Length -gt $limit -or $total+$f.Length -gt $maxTotal){return}
   $dest=Join-Path (Join-Path $files 'GATEWAY_V2\SOURCE') $f.Name
   New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
   Copy-Item -LiteralPath $f.FullName -Destination $dest
   $records.Add([pscustomobject]@{Origin=$f.FullName;Collected=$dest.Substring($work.Length+1);SHA256=(Get-FileHash $dest -Algorithm SHA256).Hash;Bytes=$f.Length;ModifiedUTC=$f.LastWriteTimeUtc.ToString('o')})
   $total+=$f.Length
  }
}
# Record process metadata, no command invocation into QRC and no secrets.
try {
 $proc=Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
 Where-Object {$_.CommandLine -match '(?i)QRC|gateway|startup_limited'} |
 Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CreationDate
 $proc | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath (Join-Path $work 'QRC_PROCESS_METADATA.json') -Encoding UTF8
}catch{$notes.Add('NOT_PROVEN: process metadata')}
$records | Export-Csv -LiteralPath (Join-Path $work 'MANIFEST.csv') -NoTypeInformation -Encoding UTF8
$report=[pscustomobject]@{
 CreatedUTC=(Get-Date).ToUniversalTime().ToString('o')
 Mode='READ_ONLY_COLLECTION'
 FilesCollected=$records.Count
 BytesCollected=$total
 Sources=$roots
 Notes=@($notes)
 Warnings=@('No runtime execution, no QRC authorization, no Claude connection test','Source files only when -IncludeSource specified','Inspect contents before sharing; secret scanning is name-based and not a guarantee')
}
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $work 'COLLECTION_REPORT.json') -Encoding UTF8
$zip=Join-Path $OutputDir "Q_HANDOFF_EVIDENCE_$stamp.zip"
Get-ChildItem -LiteralPath $work | Compress-Archive -DestinationPath $zip -Force
Write-Output "COLLECTED_ZIP=$zip"
Write-Output "FILES=$($records.Count)"

````

## previous_handoff_kit/README.md

````text
# Q → Claude 引継ぎキット

**これは正式なQRC書込・実行接続を実装したものではありません。** Claudeに渡す引継ぎ指示と、既知のWindowsディレクトリから証拠を読み取り回収するスクリプトです。

## 最短手順
1. ZIPをWindowsへ展開。
2. PowerShellで展開先に移動し、次を実行:
   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\collect_q_handoff.ps1 -IncludeSource`
3. デスクトップの `Q_Claude_Handoff\Q_HANDOFF_EVIDENCE_*.zip` をClaude Desktopに添付。
4. `CLAUDE_HANDOFF_PROMPT.md` の全文をClaudeへ送信。

## 実行範囲
- 既知の2つのQRC/Gatewayフォルダのみ読取。実注文、ファイル改変、QRC停止、認証変更はしない。
- ファイル名で秘密情報を除外するが、**中身に秘密がない保証はない**。外部アップロード前に内容を確認すること。
- Q本体の全ファイルは収集しない。ClaudeにはGitHub正本への接続も別途必要。
- 現物の存在・接続・Claude動作は未検証。`NOT_PROVEN`はそのまま維持する。

````

## README.md

````text
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

````

## source/QUADRANT_TERMINAL_v0.4.0/backend/app.py

````text
from __future__ import annotations

import asyncio
import math
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from rss_readonly import ExcelRssReadOnlyAdapter, RssReadOnlyUnavailable
from phoenix_analysis_readonly import PhoenixAnalysisReadOnlyAdapter

VERSION = "0.4.0"
DATA_SOURCE = os.environ.get("QUADRANT_DATA_SOURCE", "rss").strip().lower()
if DATA_SOURCE not in {"mock", "rss"}:
    raise RuntimeError("QUADRANT_DATA_SOURCE must be 'mock' or 'rss'")

app = FastAPI(title="QUADRANT TERMINAL Read-Only API", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_origin_regex=r"^http://(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}):1420$",
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

BASE_STATE: dict[str, Any] = {
    "mode": "READ_ONLY",
    "source": "MOCK_BACKEND",
    "as_of": "",
    "system": {
        "phoenix": "ONLINE",
        "market_data": "SIMULATED",
        "rakuten_rss": "NOT_CONNECTED",
        "live_runtime": "ISOLATED",
        "watchdog": "OK",
        "analysis": "MOCK",
    },
    "account": {
        "equity": 4_862_430,
        "buying_power": 1_725_000,
        "day_pnl": 28_460,
        "day_pnl_pct": 0.59,
        "unrealized_pnl": 41_700,
    },
    "watchlist": [
        {"ticker": "7203.T", "name": "Toyota", "price": 3018.0, "change_pct": 1.24, "score": 92, "signal": "BUY"},
        {"ticker": "8306.T", "name": "MUFG", "price": 2365.5, "change_pct": 0.82, "score": 87, "signal": "WATCH"},
        {"ticker": "9984.T", "name": "SoftBank G", "price": 17120.0, "change_pct": -0.31, "score": 78, "signal": "HOLD"},
        {"ticker": "6758.T", "name": "Sony G", "price": 3248.0, "change_pct": 0.46, "score": 84, "signal": "BUY"},
        {"ticker": "6501.T", "name": "Hitachi", "price": 4483.0, "change_pct": 1.03, "score": 89, "signal": "WATCH"},
    ],
    "positions": [
        {"ticker": "7203.T", "name": "Toyota", "side": "LONG", "qty": 100, "avg_price": 2945.0, "last": 3018.0, "pnl": 7300, "pnl_pct": 2.48, "market_value": 301800, "account_type": "特定", "pending_qty": 0},
        {"ticker": "8306.T", "name": "MUFG", "side": "LONG", "qty": 200, "avg_price": 2310.0, "last": 2365.5, "pnl": 11100, "pnl_pct": 2.40, "market_value": 473100, "account_type": "NISA", "pending_qty": 0},
    ],
    "orders": [
        {"time": "14:31:52", "ticker": "6758.T", "side": "BUY", "qty": 100, "type": "LIMIT", "price": 3240.0, "status": "SUBMITTED"},
        {"time": "14:29:18", "ticker": "7203.T", "side": "SELL", "qty": 100, "type": "STOP", "price": 2970.0, "status": "WORKING"},
    ],
    "executions": [
        {"time": "13:42:05", "ticker": "8306.T", "side": "BUY", "qty": 200, "price": 2310.0, "status": "FILLED"},
        {"time": "09:14:33", "ticker": "7203.T", "side": "BUY", "qty": 100, "price": 2945.0, "status": "FILLED"},
    ],
    "events": [
        {"time": "14:31:53", "level": "INFO", "message": "6758.T BUY request accepted by mock adapter"},
        {"time": "14:30:21", "level": "INFO", "message": "7203.T quote update received"},
        {"time": "14:29:04", "level": "PASS", "message": "Risk policy observation: PASS (display only)"},
        {"time": "09:00:00", "level": "INFO", "message": "QUADRANT / VERMILION read-only session started (PHOENIX engine)"},
    ],
    "meta": {
        "analysis_available": True,
        "account_scope": "mock",
        "equity_basis": "mock",
    },
}

RSS_ADAPTER = ExcelRssReadOnlyAdapter.from_environment()
PHOENIX_ANALYSIS = PhoenixAnalysisReadOnlyAdapter.from_environment()


def _sma(values: list[float], period: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        if index >= period - 1:
            result[index] = running / period
    return result


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return result
    gains: list[float] = []
    losses: list[float] = []
    for index in range(1, period + 1):
        delta = values[index] - values[index - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def score(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)

    result[period] = score(avg_gain, avg_loss)
    for index in range(period + 1, len(values)):
        delta = values[index] - values[index - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
        result[index] = score(avg_gain, avg_loss)
    return result


def _decorate_chart(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("bars", [])
    closes = [float(row["close"]) for row in rows]
    ma5 = _sma(closes, 5)
    ma25 = _sma(closes, 25)
    ma75 = _sma(closes, 75)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    rsi14 = _rsi(closes, 14)
    macd = [a - b for a, b in zip(ema12, ema26)]
    macd_signal = _ema(macd, 9)

    for index, row in enumerate(rows):
        row["ma5"] = ma5[index]
        row["ma25"] = ma25[index]
        row["ma75"] = ma75[index]
        row["ema12"] = ema12[index] if index < len(ema12) else None
        row["ema26"] = ema26[index] if index < len(ema26) else None
        row["rsi14"] = rsi14[index]
        row["macd"] = macd[index] if index < len(macd) else None
        row["macd_signal"] = macd_signal[index] if index < len(macd_signal) else None

    last = rows[-1] if rows else {}
    payload["indicators"] = {
        "basis": "RSS_VIEW_SELECTED_TIMEFRAME",
        "ma5": last.get("ma5"),
        "ma25": last.get("ma25"),
        "ma75": last.get("ma75"),
        "ema12": last.get("ema12"),
        "ema26": last.get("ema26"),
        "rsi14": last.get("rsi14"),
        "macd": last.get("macd"),
        "macd_signal": last.get("macd_signal"),
    }
    return payload


def build_mock_state(step: int = 0) -> dict[str, Any]:
    state = deepcopy(BASE_STATE)
    wave = math.sin(step / 3.0)
    delta = round(wave * 3.0, 1)
    state["as_of"] = datetime.now(timezone.utc).isoformat()

    for item in state["watchlist"]:
        if item["ticker"] == "7203.T":
            item["price"] = round(item["price"] + delta, 1)
            item["change_pct"] = round(item["change_pct"] + wave * 0.03, 2)

    for position in state["positions"]:
        if position["ticker"] == "7203.T":
            position["last"] = round(3018.0 + delta, 1)
            position["pnl"] = round((position["last"] - position["avg_price"]) * position["qty"])
            position["pnl_pct"] = round((position["last"] / position["avg_price"] - 1) * 100, 2)
            position["market_value"] = round(position["last"] * position["qty"])

    return state


def rss_unavailable_state(detail: str) -> dict[str, Any]:
    return {
        "mode": "READ_ONLY",
        "source": "RAKUTEN_RSS_UNAVAILABLE",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "system": {
            "phoenix": "NOT_CONNECTED",
            "market_data": "UNAVAILABLE",
            "rakuten_rss": "OFFLINE",
            "live_runtime": "ISOLATED",
            "watchdog": "UNKNOWN",
            "analysis": "NOT_CONNECTED",
        },
        "account": {"equity": 0, "buying_power": 0, "day_pnl": 0, "day_pnl_pct": 0, "unrealized_pnl": 0},
        "watchlist": [],
        "positions": [],
        "orders": [],
        "executions": [],
        "events": [{"time": datetime.now().strftime("%H:%M:%S"), "level": "WARN", "message": detail}],
        "meta": {"analysis_available": False, "account_scope": "unavailable", "equity_basis": "n/a", "short_runtime": "NOT_CONNECTED", "error": detail},
    }


def attach_phoenix_analysis(state: dict[str, Any]) -> dict[str, Any]:
    ranking, intraday_candidates, analysis_meta = PHOENIX_ANALYSIS.snapshot()
    state["ranking"] = ranking
    state["intraday_candidates"] = intraday_candidates
    state.setdefault("meta", {}).update(analysis_meta)
    if ranking:
        state.setdefault("system", {})["analysis"] = "STALE" if analysis_meta.get("analysis_stale") else "CONNECTED"
    elif intraday_candidates:
        state.setdefault("system", {})["analysis"] = "STALE" if analysis_meta.get("intraday_stale") else "CONNECTED"
    return state


async def build_state(step: int = 0) -> dict[str, Any]:
    if DATA_SOURCE == "mock":
        return build_mock_state(step)
    try:
        state = await asyncio.to_thread(RSS_ADAPTER.snapshot)
    except RssReadOnlyUnavailable as exc:
        state = rss_unavailable_state(str(exc))
    return await asyncio.to_thread(attach_phoenix_analysis, state)


@app.get("/health")
async def health() -> dict[str, Any]:
    diag = RSS_ADAPTER.diagnostics()
    return {
        "status": "ok",
        "mode": "READ_ONLY",
        "version": VERSION,
        "data_source": DATA_SOURCE,
        "rss": {"status": diag.status, "detail": diag.detail},
    }


@app.get("/api/v1/snapshot")
async def snapshot() -> dict[str, Any]:
    return await build_state()


@app.get("/api/v1/chart/{ticker}")
async def chart(ticker: str, timeframe: str = "5m", bars: int = 240) -> dict[str, Any]:
    if DATA_SOURCE != "rss":
        raise HTTPException(status_code=503, detail="Real RSS chart is available only in rss mode")
    try:
        payload = await asyncio.to_thread(RSS_ADAPTER.chart, ticker, timeframe, bars)
    except RssReadOnlyUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _decorate_chart(payload)


@app.get("/api/v1/diagnostics")
async def diagnostics() -> dict[str, Any]:
    diag = RSS_ADAPTER.diagnostics()
    _, intraday_candidates, analysis_meta = await asyncio.to_thread(PHOENIX_ANALYSIS.snapshot)
    return {
        "mode": "READ_ONLY",
        "data_source": DATA_SOURCE,
        "rss": {"status": diag.status, "detail": diag.detail, "workbook": diag.workbook},
        "analysis": analysis_meta,
        "intraday_candidate_count": len(intraday_candidates),
        "mutation_routes": [],
    }


@app.websocket("/ws/v1/state")
async def state_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    step = 0
    try:
        while True:
            await websocket.send_json(await build_state(step))
            step += 1
            await asyncio.sleep(2.0 if DATA_SOURCE == "rss" else 1.0)
    except WebSocketDisconnect:
        return

````

## source/QUADRANT_TERMINAL_v0.4.0/backend/phoenix_analysis_readonly.py

````text
from __future__ import annotations

import csv
import os
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(round(_float(value, default)))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            with path.open("r", encoding=encoding, newline="") as fh:
                return list(csv.DictReader(fh))
        except UnicodeDecodeError:
            continue
    return []


def _generated_at(rows: list[dict[str, str]], path: Path) -> str:
    for row in rows:
        value = _text(row.get("生成日時"))
        if value:
            return value
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime, tz=JST).strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _is_stale(value: str) -> bool:
    if not value:
        return True
    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
    except ValueError:
        return True
    return dt.date() != datetime.now(JST).date()


def _by_ticker(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = _text(row.get("ticker"))
        if ticker:
            result[ticker] = row
    return result


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_meta(path: Path, rows: list[dict[str, str]]) -> dict[str, Any]:
    generated_at = _generated_at(rows, path)
    return {
        "name": path.name,
        "path": str(path),
        "exists": path.is_file(),
        "rows": len(rows),
        "generated_at": generated_at,
        "stale": _is_stale(generated_at),
        "sha256": _file_sha256(path),
    }


def _pick_text(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _pick_float(row: dict[str, str], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        value = _text(row.get(key))
        if value:
            return _float(value, default)
    return default


def _parse_intraday_candidates(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        ticker = _pick_text(row, "ticker", "Ticker")
        name = _pick_text(row, "銘柄", "銘柄名", "name")
        if not ticker or not name:
            continue
        discovered_at = _pick_text(row, "発見日時", "生成日時", "timestamp", "generated_at")
        discovery_reason = _pick_text(row, "発見理由", "昇格理由", "ランキング根拠", "判定理由", "テクニカル根拠")
        candidates.append({
            "rank": _int(row.get("順位"), index),
            "ticker": ticker,
            "name": name,
            "price": _pick_float(row, "価格", "現在値", "last"),
            "change_pct": _pick_float(row, "前日比%", "当日騰落率%", "change_pct"),
            "score": _pick_float(row, "ランキング点", "PHOENIX_SCORE", "score"),
            "signal": _pick_text(row, "Trade判定", "AI判断", "signal") or "WATCH",
            "phoenix_score": _pick_float(row, "PHOENIX_SCORE", "phoenix_score"),
            "ai_score": _pick_float(row, "AI判断点", "ai_score"),
            "watch_status": _pick_text(row, "監視区分", "候補状態", "status"),
            "risk": _pick_text(row, "リスク", "risk"),
            "rsi": _pick_float(row, "RSI", "RSI14", "rsi"),
            "macd": _pick_text(row, "MACD判定", "MACD", "macd"),
            "volume_ratio": _pick_float(row, "出来高倍率", "volume_ratio"),
            "reason": discovery_reason,
            "technical_reason": _pick_text(row, "テクニカル根拠"),
            "phoenix_reason": _pick_text(row, "PHOENIX理由"),
            "caution_material": _pick_text(row, "注意材料"),
            "monitor_timing": _pick_text(row, "監視タイミング"),
            "base_price": _pick_float(row, "基準価格"),
            "entry_price": _pick_float(row, "押し目価格", "ENTRY", "entry_price"),
            "target_price": _pick_float(row, "利確価格", "TARGET", "target_price"),
            "stop_price": _pick_float(row, "損切価格", "STOP", "stop_price"),
            "trade_decision": _pick_text(row, "Trade判定", "trade_decision"),
            "decision_reason": _pick_text(row, "判定理由", "decision_reason") or discovery_reason,
            "artifact_generated_at": discovered_at,
            "origin": "INTRADAY",
            "discovered_at": discovered_at,
            "discovery_reason": discovery_reason,
            "promotion_status": _pick_text(row, "昇格状態", "候補状態", "status") or "DISCOVERED",
        })
    return candidates


class PhoenixAnalysisReadOnlyAdapter:
    """Read PHOENIX report artifacts only. Never import or invoke PHOENIX runtime."""

    def __init__(
        self,
        ranking_file: str | Path,
        trade_signals_file: str | Path,
        ai_judgement_file: str | Path,
        intraday_file: str | Path,
    ) -> None:
        self.ranking_file = Path(ranking_file).resolve()
        self.trade_signals_file = Path(trade_signals_file).resolve()
        self.ai_judgement_file = Path(ai_judgement_file).resolve()
        self.intraday_file = Path(intraday_file).resolve()

    @classmethod
    def from_environment(cls) -> "PhoenixAnalysisReadOnlyAdapter":
        root = Path(__file__).resolve().parents[2]
        reports = root / "reports"
        return cls(
            os.environ.get("QUADRANT_PHOENIX_RANKING", str(reports / "ranking_ai.csv")),
            os.environ.get("QUADRANT_PHOENIX_SIGNALS", str(reports / "trade_signals.csv")),
            os.environ.get("QUADRANT_PHOENIX_AI", str(reports / "ai_judgement.csv")),
            os.environ.get("QUADRANT_PHOENIX_INTRADAY", str(reports / "intraday_candidates.csv")),
        )

    def snapshot(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        ranking_rows = _read_csv(self.ranking_file)
        signal_rows = _read_csv(self.trade_signals_file)
        ai_rows = _read_csv(self.ai_judgement_file)
        intraday_rows = _read_csv(self.intraday_file)
        intraday = _parse_intraday_candidates(intraday_rows)
        intraday_generated = _generated_at(intraday_rows, self.intraday_file)

        if not ranking_rows:
            return [], intraday, {
                "analysis_available": False,
                "analysis_error": "ranking_ai.csv not found or empty",
                "intraday_available": bool(intraday),
                "intraday_count": len(intraday),
                "intraday_generated_at": intraday_generated,
                "intraday_stale": _is_stale(intraday_generated),
                "intraday_artifact": _artifact_meta(self.intraday_file, intraday_rows),
                "provenance_mode": "READ_ONLY",
            }

        signals = _by_ticker(signal_rows)
        ai = _by_ticker(ai_rows)

        ranking_generated = _generated_at(ranking_rows, self.ranking_file)
        signal_generated = _generated_at(signal_rows, self.trade_signals_file)
        ai_generated = _generated_at(ai_rows, self.ai_judgement_file)

        ranking: list[dict[str, Any]] = []
        for row in ranking_rows:
            ticker = _text(row.get("ticker"))
            name = _text(row.get("銘柄"))
            if not ticker or not name:
                continue

            signal = signals.get(ticker, {})
            judgement = ai.get(ticker, {})

            ranking.append({
                "rank": _int(row.get("順位")),
                "ticker": ticker,
                "name": name,
                "price": _float(row.get("価格")),
                "change_pct": _float(signal.get("前日比%"), _float(judgement.get("前日比%"))),
                "score": _float(row.get("ランキング点")),
                "signal": _text(signal.get("Trade判定")) or _text(row.get("AI判断")) or "—",
                "phoenix_score": _float(row.get("PHOENIX_SCORE")),
                "ai_score": _float(row.get("AI判断点")),
                "rank_label": _text(row.get("ランク")),
                "watch_status": _text(row.get("監視区分")),
                "risk": _text(row.get("リスク")),
                "rsi": _float(row.get("RSI")),
                "macd": _text(row.get("MACD判定")),
                "volume_ratio": _float(row.get("出来高倍率")),
                "expected_win_rate": _float(row.get("期待勝率%")),
                "reason": _text(row.get("ランキング根拠")),
                "technical_reason": _text(row.get("テクニカル根拠")),
                "learning_reason": _text(row.get("学習根拠")) or _text(judgement.get("自己学習根拠")),
                "phoenix_reason": _text(judgement.get("PHOENIX理由")),
                "plus_material": _text(judgement.get("プラス材料")),
                "caution_material": _text(judgement.get("注意材料")),
                "monitor_timing": _text(judgement.get("監視タイミング")),
                "base_price": _float(signal.get("基準価格")),
                "entry_price": _float(signal.get("押し目価格")),
                "target_price": _float(signal.get("利確価格"), _float(judgement.get("参考目標価格"))),
                "stop_price": _float(signal.get("損切価格"), _float(judgement.get("参考損切価格"))),
                "trade_decision": _text(signal.get("Trade判定")),
                "decision_reason": _text(signal.get("判定理由")),
                "market_risk_score": _float(signal.get("MarketRiskScore")),
                "market_risk_level": _text(signal.get("MarketRiskLevel")),
                "artifact_generated_at": ranking_generated,
                "origin": "MORNING",
                "discovered_at": ranking_generated,
                "discovery_reason": _text(row.get("ランキング根拠")) or _text(signal.get("判定理由")),
                "promotion_status": _text(row.get("監視区分")) or _text(signal.get("Trade判定")),
            })

        timestamps = [x for x in (ranking_generated, signal_generated, ai_generated) if x]
        parsed_times: list[datetime] = []
        for value in timestamps:
            try:
                parsed_times.append(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST))
            except ValueError:
                pass
        if len(parsed_times) == len(timestamps) and parsed_times:
            spread_seconds = (max(parsed_times) - min(parsed_times)).total_seconds()
            consistency = "CONSISTENT_RUN" if spread_seconds <= 300 else "MIXED_TIMESTAMPS"
        else:
            consistency = "NOT_PROVEN"
        newest = max(timestamps) if timestamps else ""

        return ranking, intraday, {
            "analysis_available": bool(ranking),
            "analysis_generated_at": newest,
            "analysis_stale": any(_is_stale(value) for value in timestamps) if timestamps else True,
            "analysis_source": "PHOENIX report artifacts (READ ONLY)",
            "analysis_count": len(ranking),
            "analysis_consistency": consistency,
            "analysis_lineage": "MORNING: ranking_ai + trade_signals + ai_judgement",
            "analysis_artifacts": {
                "ranking_ai": _artifact_meta(self.ranking_file, ranking_rows),
                "trade_signals": _artifact_meta(self.trade_signals_file, signal_rows),
                "ai_judgement": _artifact_meta(self.ai_judgement_file, ai_rows),
            },
            "intraday_available": bool(intraday),
            "intraday_generated_at": intraday_generated,
            "intraday_stale": _is_stale(intraday_generated),
            "intraday_count": len(intraday),
            "intraday_source": "PHOENIX intraday candidate artifact (READ ONLY)",
            "intraday_artifact": _artifact_meta(self.intraday_file, intraday_rows),
            "provenance_mode": "READ_ONLY",
        }

````

## source/QUADRANT_TERMINAL_v0.4.0/backend/requirements.txt

````text
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
pywin32>=306; platform_system == "Windows"
tzdata>=2025.2; platform_system == "Windows"

````

## source/QUADRANT_TERMINAL_v0.4.0/backend/rss_readonly.py

````text
from __future__ import annotations

import os
import platform
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
CHART_TIMEFRAMES = {
    "5m": ("5M", False),
    "15m": ("15M", False),
    "60m": ("60M", False),
    "4h": ("60M", True),
    "1d": ("D", False),
}

READ_ONLY_FUNCTIONS = {
    "RssPositionList",
    "RssOrderList",
    "RssExecutionList",
    "RssCapacityList",
}

# Optional margin read-only sheets (candidate 08, FROZEN). Missing sheet => NOT_PROVEN, never guessed.
MARGIN_READ_SHEETS = {
    "MarginPower": "RssMarginPower",
    "MarginPositions": "RssMarginPositionList",
    "MarginInfo": "RssMarginInfo",
}

FORBIDDEN_ORDER_TOKENS = (
    "RssStockOrder",
    "RssMarginOpenOrder",
    "RssMarginCloseOrder",
    "RssModifyOrder",
    "RssCancelOrder",
    "RssFOPOpenOrder",
    "RssFOPCloseOrder",
    "RssFOPMultiOpenOrder",
    "RssFOPMultiCloseOrder",
    "RssFOPModifyOrder",
    "RssFOPCancelOrder",
)


class RssReadOnlyUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RssDiagnostics:
    status: str
    detail: str
    workbook: str


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", "-"):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("円", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return default


def _ticker(code: Any) -> str:
    text = _as_text(code)
    if not text or set(text) == {"-"}:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.endswith(".T"):
        return text
    if text.isdigit():
        return f"{text}.T"
    return text


def _normalize_grid(value: Any) -> list[list[Any]]:
    if value is None:
        return []
    if not isinstance(value, tuple):
        return [[value]]
    if value and not isinstance(value[0], tuple):
        return [list(value)]
    return [list(row) for row in value]


def _locate_table(rows: list[list[Any]], required_headers: Iterable[str]) -> tuple[list[str], list[list[Any]]]:
    required = set(required_headers)
    for idx, row in enumerate(rows):
        headers = [_as_text(cell) for cell in row]
        if required.issubset(set(headers)):
            table: list[list[Any]] = []
            for data_row in rows[idx + 1 :]:
                if not any(_as_text(cell) for cell in data_row):
                    if table:
                        break
                    continue
                table.append(data_row)
            return headers, table
    raise RssReadOnlyUnavailable(f"RSS table header not found: {', '.join(required_headers)}")


def _row_dict(headers: list[str], row: list[Any]) -> dict[str, Any]:
    return {header: row[i] if i < len(row) else None for i, header in enumerate(headers) if header}


def _clock_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    text = _as_text(value)
    if " " in text:
        return text.rsplit(" ", 1)[-1]
    return text


def _side(value: Any) -> str:
    text = _as_text(value)
    if "買" in text:
        return "BUY"
    if "売" in text:
        return "SELL"
    return text or "—"


def _order_price(value: Any) -> float | str:
    if isinstance(value, (int, float)):
        return float(value)
    text = _as_text(value)
    if not text:
        return "—"
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return text


def _active_status(*values: Any) -> str:
    texts = [_as_text(value) for value in values if _as_text(value)]
    return " / ".join(texts) if texts else "—"


def _excel_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime(1899, 12, 30) + timedelta(days=float(value))
    text = _as_text(value)
    if not text:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _bar_timestamp(date_value: Any, time_value: Any) -> str:
    date_part = _excel_datetime(date_value)
    time_part = _excel_datetime(time_value)
    if date_part is None:
        return ""
    hour = minute = second = 0
    if time_part is not None:
        hour, minute, second = time_part.hour, time_part.minute, time_part.second
    return datetime(
        date_part.year,
        date_part.month,
        date_part.day,
        hour,
        minute,
        second,
        tzinfo=JST,
    ).isoformat()


def _aggregate_four_hour(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    day_bucket: list[dict[str, Any]] = []
    current_day = ""

    def flush() -> None:
        for start in range(0, len(day_bucket), 4):
            chunk = day_bucket[start : start + 4]
            if not chunk:
                continue
            grouped.append({
                "time": chunk[0]["time"],
                "open": chunk[0]["open"],
                "high": max(item["high"] for item in chunk),
                "low": min(item["low"] for item in chunk),
                "close": chunk[-1]["close"],
                "volume": sum(item["volume"] for item in chunk),
            })

    for bar in bars:
        day = str(bar["time"])[:10]
        if current_day and day != current_day:
            flush()
            day_bucket.clear()
        current_day = day
        day_bucket.append(bar)
    flush()
    return grouped


class ExcelRssReadOnlyAdapter:
    """Read MarketSpeed II RSS output from a dedicated Excel workbook.

    This adapter NEVER invokes an RSS order/mutation function. It only reads cells from
    an already-open workbook whose formulas are limited to approved read-only list/capacity
    functions. The workbook is tied to the MarketSpeed II session currently logged into Excel.
    """

    def __init__(self, workbook_path: str | Path, cache_seconds: float = 1.5) -> None:
        self.workbook_path = Path(workbook_path).resolve()
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cached_at = 0.0
        self._cached_snapshot: dict[str, Any] | None = None
        self._last_error = "not read yet"

    @classmethod
    def from_environment(cls) -> "ExcelRssReadOnlyAdapter":
        default = Path(__file__).resolve().parents[1] / "rss" / "QUADRANT_READONLY_RSS.xlsx"
        path = os.environ.get("QUADRANT_RSS_WORKBOOK", str(default))
        return cls(path)

    def diagnostics(self) -> RssDiagnostics:
        if platform.system() != "Windows":
            return RssDiagnostics("UNAVAILABLE", "Excel RSS bridge requires Windows + Excel", str(self.workbook_path))
        if not self.workbook_path.exists():
            return RssDiagnostics("UNAVAILABLE", "read-only RSS workbook is missing", str(self.workbook_path))
        if self._cached_snapshot is not None:
            return RssDiagnostics("CONNECTED", "read-only workbook data received", str(self.workbook_path))
        return RssDiagnostics("WAITING", self._last_error, str(self.workbook_path))

    def snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            if self._cached_snapshot is not None and now - self._cached_at < self.cache_seconds:
                return self._cached_snapshot
            snapshot = self._read_excel()
            self._cached_snapshot = snapshot
            self._cached_at = now
            self._last_error = "ok"
            return snapshot

    def _read_excel(self) -> dict[str, Any]:
        if platform.system() != "Windows":
            raise RssReadOnlyUnavailable("Excel RSS bridge requires Windows")
        if not self.workbook_path.exists():
            raise RssReadOnlyUnavailable(f"RSS workbook not found: {self.workbook_path}")

        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise RssReadOnlyUnavailable("pywin32 is not installed") from exc

        pythoncom.CoInitialize()
        try:
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except Exception as exc:  # pragma: no cover - Windows/Excel specific
                raise RssReadOnlyUnavailable("Excel is not running. Open the QUADRANT read-only RSS workbook in Excel first.") from exc

            workbook = None
            target_name = self.workbook_path.name.lower()
            target_full = str(self.workbook_path).lower()
            for candidate in excel.Workbooks:
                try:
                    full_name = str(candidate.FullName).lower()
                    name = str(candidate.Name).lower()
                except Exception:
                    continue
                if full_name == target_full or name == target_name:
                    workbook = candidate
                    break

            if workbook is None:
                raise RssReadOnlyUnavailable(
                    f"{self.workbook_path.name} is not open in Excel. Open it in the same Excel instance as MarketSpeed II RSS."
                )

            self._verify_formula_boundary(workbook)
            positions_rows = self._sheet_rows(workbook, "Positions")
            capacity_rows = self._sheet_rows(workbook, "Capacity")
            orders_rows = self._sheet_rows(workbook, "Orders")
            executions_rows = self._sheet_rows(workbook, "Executions")

            positions, watchlist = self._parse_positions(positions_rows)
            account = self._parse_account(capacity_rows, positions)
            orders = self._parse_orders(orders_rows)
            executions = self._parse_executions(executions_rows)
            margin = self._read_margin(workbook)

            now_iso = datetime.now(timezone.utc).isoformat()
            return {
                "mode": "READ_ONLY",
                "source": "RAKUTEN_RSS_EXCEL",
                "as_of": now_iso,
                "system": {
                    "phoenix": "NOT_CONNECTED",
                    "market_data": "REAL",
                    "rakuten_rss": "CONNECTED",
                    "live_runtime": "ISOLATED",
                    "watchdog": "UNKNOWN",
                    "analysis": "NOT_CONNECTED",
                },
                "account": account,
                "watchlist": watchlist,
                "positions": positions,
                "orders": orders,
                "executions": executions,
                "margin": margin,
                "events": [
                    {
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "level": "PASS",
                        "message": "Rakuten MarketSpeed II RSS account read-only bridge connected",
                    }
                ],
                "meta": {
                    "workbook": self.workbook_path.name,
                    "account_scope": "logged-in MarketSpeed II account",
                    "analysis_available": False,
                    "short_runtime": "NOT_CONNECTED",
                    "equity_basis": "現物買付可能額 + 保有銘柄の時価評価額 (推定)",
                },
            }
        except RssReadOnlyUnavailable as exc:
            self._last_error = str(exc)
            raise
        finally:
            pythoncom.CoUninitialize()

    def chart(self, ticker: str, timeframe: str, bars: int = 240) -> dict[str, Any]:
        """Fetch read-only OHLCV through RssChart in a disposable unsaved workbook."""
        normalized_ticker = _ticker(ticker)
        if not normalized_ticker:
            raise RssReadOnlyUnavailable("Invalid ticker")
        key = timeframe.strip().lower()
        if key not in CHART_TIMEFRAMES:
            raise RssReadOnlyUnavailable("Unsupported chart timeframe")
        rss_timeframe, derived_four_hour = CHART_TIMEFRAMES[key]
        requested = max(20, min(int(bars), 1000))
        rss_count = min(3000, requested * 4) if derived_four_hour else requested
        with self._lock:
            return self._read_chart_excel(
                normalized_ticker,
                key,
                rss_timeframe,
                rss_count,
                requested,
                derived_four_hour,
            )

    def _read_chart_excel(
        self,
        ticker: str,
        requested_timeframe: str,
        rss_timeframe: str,
        rss_count: int,
        requested_count: int,
        derived_four_hour: bool,
    ) -> dict[str, Any]:
        if platform.system() != "Windows":
            raise RssReadOnlyUnavailable("Excel RSS chart bridge requires Windows")
        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore
        except ImportError as exc:
            raise RssReadOnlyUnavailable("pywin32 is not installed") from exc

        pythoncom.CoInitialize()
        temp_workbook = None
        try:
            try:
                excel = win32com.client.GetActiveObject("Excel.Application")
            except Exception as exc:
                raise RssReadOnlyUnavailable(
                    "Excel is not running in the QUADRANT backend logon session"
                ) from exc

            target_name = self.workbook_path.name.lower()
            target_full = str(self.workbook_path).lower()
            owner_found = False
            for candidate in excel.Workbooks:
                try:
                    if (
                        str(candidate.FullName).lower() == target_full
                        or str(candidate.Name).lower() == target_name
                    ):
                        owner_found = True
                        break
                except Exception:
                    continue
            if not owner_found:
                raise RssReadOnlyUnavailable(
                    f"{self.workbook_path.name} is not open in the active Excel instance"
                )

            temp_workbook = excel.Workbooks.Add()
            sheet = temp_workbook.Worksheets(1)
            formula = f'=RssChart(,"{ticker}","{rss_timeframe}",{rss_count})'
            sheet.Range("A1").Formula = formula

            rows: list[list[Any]] = []
            last_error = ""
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                try:
                    excel.Calculate()
                    rows = _normalize_grid(sheet.UsedRange.Value)
                    _, data = _locate_table(
                        rows,
                        ("日付", "始値", "高値", "安値", "終値", "出来高"),
                    )
                    if data:
                        break
                except Exception as exc:
                    last_error = str(exc)
                time.sleep(0.15)
            else:
                raise RssReadOnlyUnavailable(
                    "RssChart did not return OHLCV data"
                    + (f": {last_error}" if last_error else "")
                )

            headers, data = _locate_table(
                rows,
                ("日付", "始値", "高値", "安値", "終値", "出来高"),
            )
            parsed: list[dict[str, Any]] = []
            for raw in data:
                item = _row_dict(headers, raw)
                timestamp = _bar_timestamp(item.get("日付"), item.get("時刻"))
                open_price = _as_float(item.get("始値"))
                high = _as_float(item.get("高値"))
                low = _as_float(item.get("安値"))
                close = _as_float(item.get("終値"))
                if not timestamp or min(open_price, high, low, close) <= 0:
                    continue
                parsed.append({
                    "time": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": _as_float(item.get("出来高")),
                })

            parsed.sort(key=lambda row: row["time"])
            if derived_four_hour:
                parsed = _aggregate_four_hour(parsed)
            parsed = parsed[-requested_count:]
            if not parsed:
                raise RssReadOnlyUnavailable("RssChart returned no valid OHLCV rows")

            return {
                "ticker": ticker,
                "timeframe": requested_timeframe,
                "rss_timeframe": rss_timeframe,
                "derived": derived_four_hour,
                "derived_note": (
                    "国内株式は楽天RSSで4H非対応のため、60分足を4本単位でQ表示用に合成"
                    if derived_four_hour
                    else ""
                ),
                "source": "RAKUTEN_RSS_RSSCHART",
                "mode": "READ_ONLY",
                "as_of": datetime.now(timezone.utc).isoformat(),
                "bars": parsed,
            }
        finally:
            if temp_workbook is not None:
                try:
                    temp_workbook.Close(SaveChanges=False)
                except Exception:
                    pass
            pythoncom.CoUninitialize()

    def _verify_formula_boundary(self, workbook: Any) -> None:
        found_readonly: set[str] = set()
        sheets = ["Positions", "Capacity", "Orders", "Executions"]
        for name in MARGIN_READ_SHEETS:
            try:
                workbook.Worksheets(name)
                sheets.append(name)
            except Exception:
                pass
        for sheet_name in sheets:
            try:
                sheet = workbook.Worksheets(sheet_name)
                formulas = _normalize_grid(sheet.UsedRange.Formula)
            except Exception as exc:
                raise RssReadOnlyUnavailable(f"Cannot inspect worksheet {sheet_name}") from exc
            for row in formulas:
                for cell in row:
                    text = _as_text(cell)
                    if not text.startswith("="):
                        continue
                    for token in FORBIDDEN_ORDER_TOKENS:
                        if token.lower() in text.lower():
                            raise RssReadOnlyUnavailable(f"Unsafe RSS mutation formula detected: {token}")
                    for token in READ_ONLY_FUNCTIONS:
                        if token.lower() in text.lower():
                            found_readonly.add(token)
        missing = READ_ONLY_FUNCTIONS.difference(found_readonly)
        if missing:
            raise RssReadOnlyUnavailable(f"Required read-only RSS formulas missing: {', '.join(sorted(missing))}")

    def _read_margin(self, workbook: Any) -> dict[str, Any]:
        """Raw margin read. No column semantics are assumed; absent/unopened => NOT_PROVEN."""
        result: dict[str, Any] = {}
        for sheet_name, func in MARGIN_READ_SHEETS.items():
            try:
                rows = self._sheet_rows(workbook, sheet_name)
            except RssReadOnlyUnavailable:
                result[sheet_name] = {"function": func, "status": "NOT_PROVEN", "reason": "sheet absent"}
                continue
            cells = [_as_text(c) for r in rows for c in r if _as_text(c)]
            unopened = bool(cells) and all(c in ("－", "-", "ー") for c in cells)
            result[sheet_name] = {
                "function": func,
                "status": "UNOPENED_OR_EMPTY" if (not cells or unopened) else "READ",
                "rows": [[_as_text(c) for c in r] for r in rows] if cells and not unopened else [],
            }
        return result

    @staticmethod
    def _sheet_rows(workbook: Any, name: str) -> list[list[Any]]:
        try:
            sheet = workbook.Worksheets(name)
            return _normalize_grid(sheet.UsedRange.Value2)
        except Exception as exc:
            raise RssReadOnlyUnavailable(f"Cannot read worksheet: {name}") from exc

    @staticmethod
    def _parse_positions(rows: list[list[Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        headers, data = _locate_table(rows, ("銘柄コード", "保有数量", "平均取得価額", "時価"))
        positions: list[dict[str, Any]] = []
        watchlist: list[dict[str, Any]] = []
        for row in data:
            item = _row_dict(headers, row)
            ticker = _ticker(item.get("銘柄コード"))
            if not ticker:
                continue
            qty = _as_float(item.get("保有数量"))
            if qty <= 0:
                continue
            avg = _as_float(item.get("平均取得価額"))
            last = _as_float(item.get("時価"))
            market_value = _as_float(item.get("時価評価額"), qty * last)
            pnl = _as_float(item.get("評価損益額"), (last - avg) * qty)
            pnl_pct = _as_float(item.get("評価損益率"), ((last / avg - 1) * 100 if avg else 0.0))
            change_pct = _as_float(item.get("前日比率"))
            day_change = _as_float(item.get("前日比"))
            name = _as_text(item.get("銘柄名称")) or ticker.replace(".T", "")
            account_type = _as_text(item.get("口座区分")) or "—"
            pending_qty = _as_float(item.get("発注数量"))
            positions.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "side": "NOT_PROVEN",
                    "execution": "NOT_PROVEN",
                    "status": "NOT_PROVEN",
                    "v_lock_display": "NOT_PROVEN",
                    "qty": qty,
                    "avg_price": avg,
                    "last": last,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "market_value": market_value,
                    "account_type": account_type,
                    "pending_qty": pending_qty,
                    "day_change": day_change,
                }
            )
            watchlist.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "price": last,
                    "change_pct": change_pct,
                    "score": None,
                    "signal": "—",
                }
            )
        return positions, watchlist

    @staticmethod
    def _parse_account(rows: list[list[Any]], positions: list[dict[str, Any]]) -> dict[str, Any]:
        headers, data = _locate_table(rows, ("現物買付可能額",))
        values = _row_dict(headers, data[0]) if data else {}
        buying_power = _as_float(values.get("現物買付可能額"))
        market_value = sum(_as_float(item.get("market_value")) for item in positions)
        unrealized = sum(_as_float(item.get("pnl")) for item in positions)
        day_pnl = sum(_as_float(item.get("day_change")) * _as_float(item.get("qty")) for item in positions)
        prior_value = market_value - day_pnl
        day_pct = (day_pnl / prior_value * 100) if prior_value else 0.0
        return {
            "equity": buying_power + market_value,
            "buying_power": buying_power,
            "day_pnl": day_pnl,
            "day_pnl_pct": day_pct,
            "unrealized_pnl": unrealized,
        }

    @staticmethod
    def _parse_orders(rows: list[list[Any]]) -> list[dict[str, Any]]:
        try:
            headers, data = _locate_table(rows, ("銘柄コード", "注文数量", "通常注文状況"))
        except RssReadOnlyUnavailable:
            return []
        result: list[dict[str, Any]] = []
        for row in data:
            item = _row_dict(headers, row)
            ticker = _ticker(item.get("銘柄コード"))
            qty = _as_float(item.get("注文数量"))
            if not ticker or qty <= 0:
                continue
            result.append(
                {
                    "time": _clock_text(item.get("発注/受注日時")),
                    "ticker": ticker,
                    "side": _side(item.get("売買")),
                    "qty": _as_float(item.get("注文数量")),
                    "type": _as_text(item.get("注文区分")) or _as_text(item.get("執行条件")) or "—",
                    "price": _order_price(item.get("注文単価")),
                    "status": _active_status(item.get("通常注文状況"), item.get("逆指値注文状況"), item.get("アルゴ注文状況")),
                }
            )
        return result[:100]

    @staticmethod
    def _parse_executions(rows: list[list[Any]]) -> list[dict[str, Any]]:
        try:
            headers, data = _locate_table(rows, ("銘柄コード", "約定数量", "約定単価", "約定日"))
        except RssReadOnlyUnavailable:
            return []
        result: list[dict[str, Any]] = []
        for row in data:
            item = _row_dict(headers, row)
            ticker = _ticker(item.get("銘柄コード"))
            qty = _as_float(item.get("約定数量"))
            if not ticker or qty <= 0:
                continue
            result.append(
                {
                    "time": _clock_text(item.get("約定日")),
                    "ticker": ticker,
                    "side": _side(item.get("売買")),
                    "qty": _as_float(item.get("約定数量")),
                    "price": _as_float(item.get("約定単価")),
                    "status": "FILLED",
                }
            )
        return result[:100]

````

## source/QUADRANT_TERMINAL_v0.4.0/backend/tests/test_rss_readonly.py

````text
from rss_readonly import ExcelRssReadOnlyAdapter, FORBIDDEN_ORDER_TOKENS, READ_ONLY_FUNCTIONS


def test_position_parser_maps_official_headers():
    rows = [
        ["=RssPositionList()"],
        ["銘柄コード", "銘柄名称", "口座区分", "保有数量", "発注数量", "平均取得価額", "時価", "前日比", "前日比率", "時価評価額", "評価損益額", "評価損益率"],
        ["7203", "トヨタ自動車", "特定", 100, 0, 2900, 3000, 25, 0.84, 300000, 10000, 3.45],
    ]
    positions, watchlist = ExcelRssReadOnlyAdapter._parse_positions(rows)
    assert positions[0]["ticker"] == "7203.T"
    assert positions[0]["account_type"] == "特定"
    assert positions[0]["pnl"] == 10000
    assert watchlist[0]["score"] is None


def test_account_is_estimated_from_read_only_fields():
    rows = [
        ["=RssCapacityList()"],
        ["現物買付可能額", "信用口座_保証金余裕額"],
        [500000, 0],
    ]
    positions = [{"market_value": 300000, "pnl": 10000, "day_change": 25, "qty": 100}]
    account = ExcelRssReadOnlyAdapter._parse_account(rows, positions)
    assert account["equity"] == 800000
    assert account["buying_power"] == 500000
    assert account["unrealized_pnl"] == 10000
    assert account["day_pnl"] == 2500


def test_readonly_function_allowlist_and_mutation_denylist_are_disjoint():
    assert READ_ONLY_FUNCTIONS
    for allowed in READ_ONLY_FUNCTIONS:
        assert all(token.lower() not in allowed.lower() for token in FORBIDDEN_ORDER_TOKENS)

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/index.html

````text
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#0a0d11" />
    <meta name="color-scheme" content="dark light" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="QUADRANT" />
    <link rel="apple-touch-icon" href="/icon-180.png" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <title>QUADRANT TERMINAL</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/package.json

````text
{
  "name": "quadrant-terminal",
  "private": true,
  "version": "0.4.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "tauri": "tauri"
  },
  "dependencies": {
    "@tauri-apps/api": "2.11.1",
    "lightweight-charts": "5.2.1",
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@tauri-apps/cli": "2.11.4",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "6.1.1",
    "typescript": "7.0.2",
    "vite": "8.3.0",
    "@types/node": "^22.14.0"
  }
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/public/manifest.webmanifest

````text
{
  "id": "/",
  "name": "QUADRANT TERMINAL",
  "short_name": "QUADRANT",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "display_override": [
    "standalone",
    "minimal-ui"
  ],
  "orientation": "any",
  "background_color": "#0a0d11",
  "theme_color": "#0a0d11",
  "lang": "ja",
  "categories": [
    "finance",
    "business"
  ],
  "icons": [
    {
      "src": "/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ],
  "description": "QUADRANT unified read-only trading terminal. VERMILION / AZURE / WHITE TIGER / BLACK WARRIOR share one observation UI while their underlying engines remain isolated."
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/public/sw.js

````text
const CACHE = "quadrant-shell-v0.4.0";
const SHELL = ["/", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match("/")))
  );
});

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src/App.tsx

````text
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { MarketChart } from "./components/MarketChart";
import type { ChartPayload, ChartTimeframe, PhoenixSnapshot, Position, RankingItem, WatchItem } from "./types";

const PAGE_HOST = window.location.hostname;
const IS_TAURI = PAGE_HOST === "tauri.localhost";
const API_HOST = import.meta.env.VITE_SHISHIN_API_HOST || (IS_TAURI ? "127.0.0.1" : PAGE_HOST) || "127.0.0.1";
const API_PROTOCOL = IS_TAURI ? "http:" : window.location.protocol === "https:" ? "https:" : "http:";
const WS_PROTOCOL = IS_TAURI ? "ws:" : window.location.protocol === "https:" ? "wss:" : "ws:";
const API = `${API_PROTOCOL}//${API_HOST}:8765`;
const WS = `${WS_PROTOCOL}//${API_HOST}:8765/ws/v1/state`;

type BeastId = "phoenix" | "seiryu" | "byakko" | "genbu";
type MainTab = "holdings" | "summary" | "ranking";
type ThemeChoice = "system" | "light" | "dark";
type HoldingsSort = "pnl" | "value" | "ticker";

type Beast = {
  id: BeastId;
  icon: string;
  uiName: string;
  internalEngine: string;
  market: string;
  accent: string;
  accent2: string;
  status: "ACTIVE" | "PLANNED";
};

// UI branding is intentionally separated from the existing engine/project names.
// engine ids, API schema, runtime names and order authority are NOT renamed here.
const beasts: Beast[] = [
  { id: "phoenix", icon: "/assets/guardians/vermilion.png", uiName: "VERMILION", internalEngine: "PHOENIX", market: "JAPAN EQUITIES", accent: "#ff5a36", accent2: "#ffb34d", status: "ACTIVE" },
  { id: "seiryu", icon: "/assets/guardians/azure.png", uiName: "AZURE", internalEngine: "SEIRYU", market: "FX", accent: "#22c7c7", accent2: "#4f8cff", status: "PLANNED" },
  { id: "byakko", icon: "/assets/guardians/white-tiger.png", uiName: "WHITE TIGER", internalEngine: "BYAKKO", market: "GOLD", accent: "#d8b86a", accent2: "#f2f3f5", status: "PLANNED" },
  { id: "genbu", icon: "/assets/guardians/black-warrior.png", uiName: "BLACK WARRIOR", internalEngine: "GENBU", market: "US INDICES", accent: "#7c5ce6", accent2: "#33235f", status: "PLANNED" },
];

const unavailableSnapshot: PhoenixSnapshot = {
  mode: "READ_ONLY", source: "UNAVAILABLE", as_of: "",
  system: { phoenix: "NOT_CONNECTED", market_data: "UNAVAILABLE", rakuten_rss: "NOT_CONNECTED", live_runtime: "ISOLATED", watchdog: "UNKNOWN", analysis: "NOT_CONNECTED" },
  account: { equity: 0, buying_power: 0, day_pnl: 0, day_pnl_pct: 0, unrealized_pnl: 0 },
  watchlist: [], ranking: [], intraday_candidates: [], positions: [], orders: [], executions: [], events: [],
  meta: { analysis_available: false, account_scope: "unavailable", equity_basis: "NOT_PROVEN", short_runtime: "NOT_CONNECTED" },
};

const insightByTicker: Record<string, { trend: string; rsi: number; macd: string; volume: string; thesis: string[]; risk: string[] }> = {
  "7203.T": { trend: "STRONG UP", rsi: 61.4, macd: "BUY", volume: "1.42×", thesis: ["中期上昇トレンドを維持", "MA5 > MA25 > MA75", "出来高が平常時より増加"], risk: ["短期過熱が強まれば追随を抑制", "MA25割れを再評価ポイントにする"] },
  "8306.T": { trend: "UP", rsi: 57.8, macd: "POSITIVE", volume: "1.18×", thesis: ["上昇基調を維持", "モメンタムは中立より上", "押し目監視候補"], risk: ["金利材料による急変", "直近安値割れで優先度低下"] },
  "9984.T": { trend: "RANGE", rsi: 48.9, macd: "NEUTRAL", volume: "0.91×", thesis: ["方向感待ち", "スコアは監視圏", "ブレイク確認を優先"], risk: ["ボラティリティ急拡大", "レンジ下限割れ"] },
  "6758.T": { trend: "UP", rsi: 59.2, macd: "BUY", volume: "1.25×", thesis: ["価格と短期MAが上向き", "出来高増加", "モメンタム改善"], risk: ["直近高値での失速", "短期MAデッドクロス"] },
  "6501.T": { trend: "STRONG UP", rsi: 63.1, macd: "BUY", volume: "1.36×", thesis: ["高値圏を維持", "トレンド強度良好", "出来高が追随"], risk: ["過熱圏への接近", "ギャップダウン発生時は再判定"] },
};

function money(value: number) {
  return new Intl.NumberFormat("ja-JP", { style: "currency", currency: "JPY", maximumFractionDigits: 0 }).format(value);
}

function num(value: number, digits = 1) {
  return new Intl.NumberFormat("ja-JP", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

function signed(value: number, suffix = "") {
  return `${value > 0 ? "+" : ""}${num(value, 2)}${suffix}`;
}

function tone(value: number) {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function useResolvedTheme(choice: ThemeChoice) {
  const [systemDark, setSystemDark] = useState(() => window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!query) return;
    const listener = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    query.addEventListener("change", listener);
    return () => query.removeEventListener("change", listener);
  }, []);
  return choice === "system" ? (systemDark ? "dark" : "light") : choice;
}

function StatusDot({ value }: { value: string }) {
  const ok = ["ONLINE", "OK", "CONNECTED", "REAL"].includes(value);
  const muted = ["ISOLATED", "SIMULATED", "NOT_CONNECTED"].includes(value);
  return <span className={`status-dot ${ok ? "ok" : muted ? "muted" : "warn"}`} />;
}

function MetricCard({ label, value, sub, valueClass = "" }: { label: string; value: string; sub?: string; valueClass?: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong className={valueClass}>{value}</strong>
      {sub ? <small>{sub}</small> : null}
    </div>
  );
}

function EmptySystem({ beast }: { beast: Beast }) {
  return (
    <section className="coming-card panel">
      <div className="coming-glyph"><img src={beast.icon} alt="" /></div>
      <span>QUADRANT MODULE</span>
      <h2>{beast.uiName}</h2>
      <p>{beast.market}</p>
      <div className="coming-state">INTERFACE SHELL READY · ENGINE NOT CONNECTED</div>
      <p className="coming-copy">QUADRANTの共通UIだけ先に確認できます。実データ・実注文経路は接続していません。</p>
    </section>
  );
}

function App() {
  const [state, setState] = useState<PhoenixSnapshot>(unavailableSnapshot);
  const [stream, setStream] = useState<"CONNECTED" | "DISCONNECTED">("DISCONNECTED");
  const [clock, setClock] = useState(new Date());
  const [activeBeast, setActiveBeast] = useState<BeastId>("phoenix");
  const [tab, setTab] = useState<MainTab>("holdings");
  const [selectedTicker, setSelectedTicker] = useState("7203.T");
  const [beastMenuOpen, setBeastMenuOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [chartFullscreen, setChartFullscreen] = useState(false);
  const [chartTimeframe, setChartTimeframe] = useState<ChartTimeframe>("5m");
  const [chartData, setChartData] = useState<ChartPayload | null>(null);
  const [chartError, setChartError] = useState("");
  const [chartLoading, setChartLoading] = useState(false);
  const [holdingsQuery, setHoldingsQuery] = useState("");
  const [holdingsSort, setHoldingsSort] = useState<HoldingsSort>("pnl");
  const [balancesHidden, setBalancesHidden] = useState(() => localStorage.getItem("quadrant-hide-balances") === "1");
  const [themeChoice, setThemeChoice] = useState<ThemeChoice>(() => (localStorage.getItem("shishin-theme") as ThemeChoice) || "dark"); // keep legacy key so existing preference survives branding change
  const resolvedTheme = useResolvedTheme(themeChoice);
  const beast = beasts.find((item) => item.id === activeBeast) ?? beasts[0];

  useEffect(() => {
    localStorage.setItem("shishin-theme", themeChoice);
  }, [themeChoice]);

  useEffect(() => {
    localStorage.setItem("quadrant-hide-balances", balancesHidden ? "1" : "0");
  }, [balancesHidden]);

  useEffect(() => {
    document.body.classList.toggle("chart-fullscreen-open", chartFullscreen);
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setChartFullscreen(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.classList.remove("chart-fullscreen-open");
      window.removeEventListener("keydown", onKey);
    };
  }, [chartFullscreen]);

  useEffect(() => {
    const t = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    let socket: WebSocket | undefined;
    let closed = false;
    fetch(`${API}/api/v1/snapshot`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<PhoenixSnapshot>;
      })
      .then((snapshot) => !closed && setState(snapshot))
      .catch(() => undefined);

    try {
      socket = new WebSocket(WS);
      socket.onopen = () => !closed && setStream("CONNECTED");
      socket.onmessage = (event) => {
        if (closed) return;
        try {
          setState(JSON.parse(event.data) as PhoenixSnapshot);
        } catch {
          setStream("DISCONNECTED");
        }
      };
      socket.onerror = () => !closed && setStream("DISCONNECTED");
      socket.onclose = () => !closed && setStream("DISCONNECTED");
    } catch {
      setStream("DISCONNECTED");
    }
    return () => {
      closed = true;
      socket?.close();
    };
  }, []);

  const selectedItem = useMemo(() => {
    const position = state.positions.find((item) => item.ticker === selectedTicker);
    return state.watchlist.find((item) => item.ticker === selectedTicker)
      ?? state.ranking?.find((item) => item.ticker === selectedTicker)
      ?? state.intraday_candidates?.find((item) => item.ticker === selectedTicker)
      ?? (position ? { ticker: position.ticker, name: position.name ?? position.ticker, price: position.last, change_pct: 0, score: null, signal: "NOT_PROVEN" } : undefined)
      ?? state.watchlist[0] ?? state.ranking?.[0] ?? state.intraday_candidates?.[0]
      ?? (state.positions[0] ? { ticker: state.positions[0].ticker, name: state.positions[0].name ?? state.positions[0].ticker, price: state.positions[0].last, change_pct: 0, score: null, signal: "NOT_PROVEN" } : undefined);
  }, [selectedTicker, state.intraday_candidates, state.positions, state.watchlist, state.ranking]);
  const selectedPosition = useMemo(
    () => state.positions.find((item) => item.ticker === selectedItem?.ticker),
    [selectedItem?.ticker, state.positions],
  );
  const ranked = useMemo<RankingItem[]>(
    () => [...(state.ranking ?? [])].sort((a, b) => a.rank - b.rank),
    [state.ranking],
  );
  const intradayCandidates = useMemo(
    () => [...(state.intraday_candidates ?? [])].sort((a, b) => a.rank - b.rank),
    [state.intraday_candidates],
  );
  const selectedAnalysis = useMemo<RankingItem | undefined>(
    () => [...(state.ranking ?? []), ...(state.intraday_candidates ?? [])].find((item) => item.ticker === selectedItem?.ticker),
    [selectedItem?.ticker, state.intraday_candidates, state.ranking],
  );
  const selectableItems = useMemo(() => {
    const byTicker = new Map<string, WatchItem>();
    for (const item of state.ranking ?? []) byTicker.set(item.ticker, item);
    for (const item of state.intraday_candidates ?? []) byTicker.set(item.ticker, item);
    for (const item of state.watchlist) byTicker.set(item.ticker, { ...byTicker.get(item.ticker), ...item, score: byTicker.get(item.ticker)?.score ?? item.score });
    for (const position of state.positions) if (!byTicker.has(position.ticker)) byTicker.set(position.ticker, { ticker: position.ticker, name: position.name ?? position.ticker, price: position.last, change_pct: 0, score: null, signal: "NOT_PROVEN" });
    return [...byTicker.values()];
  }, [state.intraday_candidates, state.positions, state.ranking, state.watchlist]);
  const insight = selectedItem ? insightByTicker[selectedItem.ticker] : undefined;
  const isMock = state.source.includes("MOCK") || state.system.market_data === "SIMULATED";
  const isRealRss = state.source === "RAKUTEN_RSS_EXCEL";
  const rssUnavailable = state.source === "RAKUTEN_RSS_UNAVAILABLE";
  const analysisAvailable = state.meta?.analysis_available ?? false;
  const analysisStale = state.meta?.analysis_stale ?? false;
  const analysisGeneratedAt = state.meta?.analysis_generated_at ?? "";
  const intradayAvailable = state.meta?.intraday_available ?? intradayCandidates.length > 0;
  const intradayStale = state.meta?.intraday_stale ?? false;
  const intradayGeneratedAt = state.meta?.intraday_generated_at ?? "";
  const analysisArtifacts = Object.entries(state.meta?.analysis_artifacts ?? {});
  const intradayArtifact = state.meta?.intraday_artifact;
  const updatedAt = state.as_of ? new Date(state.as_of) : clock;
  const stale = isRealRss && clock.getTime() - updatedAt.getTime() > 10_000;

  useEffect(() => {
    let cancelled = false;
    if (!isRealRss || tab !== "summary" || !selectedItem?.ticker) {
      setChartData(null);
      setChartError("");
      return () => { cancelled = true; };
    }
    setChartLoading(true);
    setChartError("");
    fetch(`${API}/api/v1/chart/${encodeURIComponent(selectedItem.ticker)}?timeframe=${chartTimeframe}&bars=240`)
      .then(async (response) => {
        if (!response.ok) {
          const detail = await response.json().catch(() => ({})) as { detail?: string };
          throw new Error(detail.detail || `HTTP ${response.status}`);
        }
        return response.json() as Promise<ChartPayload>;
      })
      .then((payload) => { if (!cancelled) setChartData(payload); })
      .catch((error: Error) => { if (!cancelled) { setChartData(null); setChartError(error.message); } })
      .finally(() => { if (!cancelled) setChartLoading(false); });
    return () => { cancelled = true; };
  }, [chartTimeframe, isRealRss, selectedItem?.ticker, tab]);

  const moneyView = (value: number) => balancesHidden ? "••••••" : money(value);
  const filteredPositions = useMemo(() => {
    const query = holdingsQuery.trim().toLowerCase();
    const rows = state.positions.filter((position) => {
      const item = state.watchlist.find((candidate) => candidate.ticker === position.ticker);
      const haystack = `${position.ticker} ${position.name ?? ""} ${item?.name ?? ""} ${position.account_type ?? ""}`.toLowerCase();
      return !query || haystack.includes(query);
    });
    return rows.sort((a, b) => {
      if (holdingsSort === "value") return (b.market_value ?? b.last * b.qty) - (a.market_value ?? a.last * a.qty);
      if (holdingsSort === "ticker") return a.ticker.localeCompare(b.ticker, "ja");
      return b.pnl - a.pnl;
    });
  }, [holdingsQuery, holdingsSort, state.positions, state.watchlist]);

  const openSummary = (ticker: string) => {
    setSelectedTicker(ticker);
    setTab("summary");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <main
      className="app-shell"
      data-theme={resolvedTheme}
      data-beast={beast.id}
      style={{ "--accent": beast.accent, "--accent-2": beast.accent2 } as CSSProperties}
    >
      <header className="app-header">
        <div className="brand-lockup">
          <div className="shishin-mark quadrant-mark"><img src="/quadrant-home-1024.png" alt="QUADRANT" /></div>
          <div className="brand-copy">
            <strong>QUADRANT</strong>
            <small>UNIFIED MULTI-MARKET TRADING TERMINAL · READ ONLY</small>
          </div>
        </div>

        <div className="header-actions">
          <div className="beast-switcher-wrap">
            <button className="beast-switcher" type="button" onClick={() => setBeastMenuOpen((v) => !v)} aria-expanded={beastMenuOpen}>
              <span className="beast-mini"><img src={beast.icon} alt="" /></span>
              <span className="beast-switch-text"><b>{beast.uiName}</b><small>{beast.market}</small></span>
              <span className="chevron">⌄</span>
            </button>
            {beastMenuOpen ? (
              <div className="beast-menu panel">
                {beasts.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={item.id === activeBeast ? "selected" : ""}
                    onClick={() => { setActiveBeast(item.id); setBeastMenuOpen(false); }}
                    style={{ "--item-accent": item.accent } as CSSProperties}
                  >
                    <span className="menu-glyph"><img src={item.icon} alt="" /></span>
                    <span><b>{item.uiName}</b><small>{item.market}</small></span>
                    <em>{item.status}</em>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <div className="clock-block"><span>{stream === "CONNECTED" ? "STREAM" : "DISCONNECTED"}</span><time>{clock.toLocaleTimeString("ja-JP", { hour12: false })}</time></div>
          <button className="menu-button" type="button" onClick={() => setDrawerOpen(true)} aria-label="設定メニュー">☰</button>
        </div>
      </header>

      <nav className="main-tabs" aria-label="メインナビゲーション">
        <button type="button" className={tab === "holdings" ? "active" : ""} onClick={() => setTab("holdings")}><span>保有株式一覧</span><small>POSITIONS</small></button>
        <button type="button" className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}><span>個別サマリー</span><small>SUMMARY</small></button>
        <button type="button" className={tab === "ranking" ? "active" : ""} onClick={() => setTab("ranking")}><span>本日の狙い目</span><small>RANKING</small></button>
      </nav>

      {activeBeast !== "phoenix" ? (
        <div className="content-wrap"><EmptySystem beast={beast} /></div>
      ) : (
        <div className="content-wrap">
          {tab === "holdings" ? (
            <>
              <section className={`source-banner ${isRealRss ? "real" : rssUnavailable ? "error" : "mock"}`}>
                <div><StatusDot value={isRealRss ? "CONNECTED" : rssUnavailable ? "OFFLINE" : "SIMULATED"} /><b>{isRealRss ? "RAKUTEN RSS · LIVE ACCOUNT" : rssUnavailable ? "RAKUTEN RSS · NOT AVAILABLE" : "MOCK DATA"}</b></div>
                <span>{isRealRss ? `${state.positions.length} holdings · ${state.orders.length} orders today · ${state.executions.length} fills today` : rssUnavailable ? (state.meta?.error ?? "Excel RSS bridge is not ready") : "UI preview data"}</span>
                <em className={stale ? "stale" : ""}>{stale ? "STALE" : `更新 ${updatedAt.toLocaleTimeString("ja-JP", { hour12: false })}`}</em>
              </section>
              <section className="overview-strip">
                <MetricCard label="推定資産" value={moneyView(state.account.equity)} sub="ESTIMATED EQUITY" />
                <MetricCard label="現物買付可能額" value={moneyView(state.account.buying_power)} sub="BUYING POWER" />
                <MetricCard label="保有株本日差" value={moneyView(state.account.day_pnl)} sub={balancesHidden ? "••••" : signed(state.account.day_pnl_pct, "%")} valueClass={tone(state.account.day_pnl)} />
                <MetricCard label="含み損益" value={moneyView(state.account.unrealized_pnl)} sub="UNREALIZED" valueClass={tone(state.account.unrealized_pnl)} />
              </section>
            </>
          ) : null}

          {tab === "holdings" ? (
            <section className="page-grid holdings-page">
              <div className="panel section-card holdings-list-card">
                <div className="section-heading holdings-heading"><div><small>PORTFOLIO</small><h2>保有株式一覧</h2></div><div className="heading-actions"><span>{state.positions.length}銘柄</span><button type="button" className="privacy-toggle" onClick={() => setBalancesHidden((value) => !value)} aria-label={balancesHidden ? "金額を表示" : "金額を隠す"}>{balancesHidden ? "◉" : "◎"}</button></div></div>
                <div className="portfolio-tools">
                  <input value={holdingsQuery} onChange={(event) => setHoldingsQuery(event.target.value)} placeholder="銘柄コード・名称・口座区分で検索" aria-label="保有銘柄を検索" />
                  <div className="sort-chips" aria-label="並び順">
                    <button type="button" className={holdingsSort === "pnl" ? "active" : ""} onClick={() => setHoldingsSort("pnl")}>損益</button>
                    <button type="button" className={holdingsSort === "value" ? "active" : ""} onClick={() => setHoldingsSort("value")}>評価額</button>
                    <button type="button" className={holdingsSort === "ticker" ? "active" : ""} onClick={() => setHoldingsSort("ticker")}>コード</button>
                  </div>
                </div>
                <div className="holdings-list">
                  {filteredPositions.length ? filteredPositions.map((position) => {
                    const item = state.watchlist.find((candidate) => candidate.ticker === position.ticker);
                    return <HoldingCard key={`${position.ticker}-${position.account_type ?? "all"}`} position={position} item={item} masked={balancesHidden} onOpen={() => openSummary(position.ticker)} />;
                  }) : <div className="empty-list">{rssUnavailable ? "RSS接続後に保有銘柄を表示します。" : "条件に一致する保有銘柄はありません。"}</div>}
                </div>
              </div>

              <div className="panel section-card side-insight">
                <div className="section-heading"><div><small>AT A GLANCE</small><h2>今日の状況</h2></div></div>
                {analysisAvailable && ranked.length ? <div className="glance-score"><span>VERMILION TOP SCORE</span><strong>{ranked[0]?.score ?? "--"}</strong><small>{ranked[0]?.ticker.replace(".T", "")} · {ranked[0]?.name}</small></div> : <div className="analysis-offline-card"><b>PHOENIX ANALYSIS</b><strong>NOT CONNECTED</strong><p>口座情報はREALでも、ランキング/スコアは偽装せず非表示にします。</p></div>}
                <button type="button" className="primary-link" onClick={() => setTab("ranking")} disabled={!analysisAvailable}>本日の狙い目を見る <span>→</span></button>
                <div className="read-only-note"><b>SHORT RUNTIME ? {state.meta?.short_runtime ?? "NOT_CONNECTED"}</b><p>このUIには発注・訂正・取消の権限を持たせていません。</p></div>
              </div>
            </section>
          ) : null}

          {tab === "summary" && selectedItem ? (
            <section className="summary-page">
              <div className="instrument-hero panel">
                <div className="instrument-main">
                  <div className="symbol-block"><small>SELECTED SYMBOL</small><div><strong>{selectedItem.ticker.replace(".T", "")}</strong><span>{selectedItem.name}</span></div></div>
                  <div className="quote-block"><strong>{num(selectedItem.price, 1)}</strong><span className={tone(selectedItem.change_pct)}>{signed(selectedItem.change_pct, "%")}</span></div>
                  <div className="score-ring"><small>PHOENIX</small><strong>{selectedAnalysis?.score ?? selectedItem.score ?? "—"}</strong><span>{selectedAnalysis?.trade_decision || selectedAnalysis?.signal || selectedItem.signal || "—"}</span></div>
                </div>
                <div className="symbol-picker" aria-label="銘柄切替">
                  {selectableItems.map((item) => <button key={item.ticker} type="button" className={item.ticker === selectedItem.ticker ? "active" : ""} onClick={() => setSelectedTicker(item.ticker)}>{item.ticker.replace(".T", "")}</button>)}
                </div>
              </div>

              <div className="summary-grid">
                <section className={`panel chart-card ${chartFullscreen ? "fullscreen-chart" : ""}`}>
                  <div className="section-heading compact chart-heading">
                    <div><small>RAKUTEN RSS · REAL OHLCV</small><h2>チャート</h2></div>
                    <div className="chart-heading-actions"><span>{chartLoading ? "LOADING" : chartData ? `${chartTimeframe.toUpperCase()} · REAL` : "WAITING"}</span><button type="button" className="chart-fullscreen-toggle" onClick={() => setChartFullscreen((v) => !v)}>{chartFullscreen ? "× 閉じる" : "⤢ 全画面"}</button></div>
                  </div>
                  <div className="timeframe-chips">
                    {(["5m", "15m", "60m", "4h", "1d"] as ChartTimeframe[]).map((value) => <button key={value} type="button" className={chartTimeframe === value ? "active" : ""} onClick={() => setChartTimeframe(value)}>{value === "1d" ? "日足" : value === "4h" ? "4時間*" : value.replace("m", "分")}</button>)}
                  </div>
                  {chartData?.derived ? <div className="derived-chart-note">* {chartData.derived_note}</div> : null}
                  {chartData?.bars.length ? <MarketChart bars={chartData.bars} theme={resolvedTheme} accent={beast.accent} scenario={{ entry: selectedAnalysis?.entry_price, target: selectedAnalysis?.target_price, stop: selectedAnalysis?.stop_price }} /> : <div className="chart-waiting">{chartError || (isMock ? "REAL RSSモードで実チャートを表示します。" : "RssChartデータ待機中")}</div>}
                  {chartData ? <div className="rss-indicator-strip"><span>RSS VIEW</span><b>MA5 {typeof chartData.indicators.ma5 === "number" ? num(chartData.indicators.ma5, 2) : "—"}</b><b>MA25 {typeof chartData.indicators.ma25 === "number" ? num(chartData.indicators.ma25, 2) : "—"}</b><b>MA75 {typeof chartData.indicators.ma75 === "number" ? num(chartData.indicators.ma75, 2) : "—"}</b><b>EMA12 {typeof chartData.indicators.ema12 === "number" ? num(chartData.indicators.ema12, 2) : "—"}</b><b>EMA26 {typeof chartData.indicators.ema26 === "number" ? num(chartData.indicators.ema26, 2) : "—"}</b><b>RSI14 {typeof chartData.indicators.rsi14 === "number" ? num(chartData.indicators.rsi14, 1) : "—"}</b><b>MACD {typeof chartData.indicators.macd === "number" ? num(chartData.indicators.macd, 3) : "—"}</b><b>SIG {typeof chartData.indicators.macd_signal === "number" ? num(chartData.indicators.macd_signal, 3) : "—"}</b></div> : null}
                </section>

                <aside className="panel analysis-card">
                  <div className="section-heading compact"><div><small>PHOENIX LOGIC · DAILY ARTIFACT</small><h2>判断と条件付きシナリオ</h2></div>{analysisStale ? <span className="stale-badge">STALE</span> : null}</div>
                  {analysisAvailable && selectedAnalysis ? <>
                    <div className="analysis-grid">
                      <MetricCard label="PHOENIX SCORE" value={num(selectedAnalysis.phoenix_score ?? 0, 0)} />
                      <MetricCard label="RSI14" value={num(selectedAnalysis.rsi ?? 0, 1)} />
                      <MetricCard label="MACD" value={selectedAnalysis.macd || "—"} />
                      <MetricCard label="VOLUME" value={`${num(selectedAnalysis.volume_ratio ?? 0, 2)}×`} />
                    </div>
                    <div className="scenario-ladder">
                      <div><span>現在判断</span><strong>{selectedAnalysis.trade_decision || selectedAnalysis.signal || "—"}</strong></div>
                      <div><span>基準</span><strong>{selectedAnalysis.base_price ? `¥${num(selectedAnalysis.base_price, 1)}` : "—"}</strong></div>
                      <div className="entry"><span>押し目 / ENTRY</span><strong>{selectedAnalysis.entry_price ? `¥${num(selectedAnalysis.entry_price, 1)}` : "—"}</strong></div>
                      <div className="target"><span>TARGET</span><strong>{selectedAnalysis.target_price ? `¥${num(selectedAnalysis.target_price, 1)}` : "—"}</strong></div>
                      <div className="stop"><span>STOP / INVALIDATION</span><strong>{selectedAnalysis.stop_price ? `¥${num(selectedAnalysis.stop_price, 1)}` : "—"}</strong></div>
                    </div>
                    <div className="scenario-path" aria-label="PHOENIX条件付きシナリオ線図">
                      <div className="scenario-node now"><span>NOW</span><b>¥{num(selectedItem.price, 1)}</b></div>
                      <span className="scenario-arrow down">↘</span>
                      <div className="scenario-node entry"><span>押し目待ち</span><b>{selectedAnalysis.entry_price ? `¥${num(selectedAnalysis.entry_price, 1)}` : "—"}</b><small>条件維持ならENTRY候補</small></div>
                      <span className="scenario-arrow up">↗</span>
                      <div className="scenario-node target"><span>TARGET</span><b>{selectedAnalysis.target_price ? `¥${num(selectedAnalysis.target_price, 1)}` : "—"}</b></div>
                      <div className="scenario-stop-line"><span>STOP / INVALIDATION</span><b>{selectedAnalysis.stop_price ? `¥${num(selectedAnalysis.stop_price, 1)}` : "—"}</b></div>
                    </div>
                    <div className="decision-blocks">
                      <div className="decision-block thesis-block"><span>PHOENIXが見ている条件</span><p>{selectedAnalysis.phoenix_reason || selectedAnalysis.technical_reason || "判断条件の記録なし"}</p></div>
                      <div className="decision-block reevaluate-block"><span>条件付きシナリオ</span><p>{selectedAnalysis.monitor_timing || "押し目・モメンタム・出来高条件を再確認"}。ENTRY付近で条件維持なら候補、STOP割れで無効化。</p></div>
                      <div className="decision-block caution-block"><span>注意材料</span><p>{selectedAnalysis.caution_material || `市場リスク: ${selectedAnalysis.market_risk_level || "—"}`}</p></div>
                      <div className="decision-block invalidation-block"><span>判定理由</span><p>{selectedAnalysis.decision_reason || selectedAnalysis.reason || "—"}</p></div>
                    </div>
                    <div className="artifact-note">GENERATED {analysisGeneratedAt || selectedAnalysis.artifact_generated_at || "—"} · {analysisStale ? "STALE / 過去分析" : "CURRENT"} · Qは表示のみ</div>
                  </> : isMock && insight ? <div className="analysis-placeholder"><b>MOCK ANALYSIS</b><p>{insight.thesis.join(" / ")}</p></div> : <div className="analysis-placeholder"><b>THIS TICKER IS NOT IN CURRENT PHOENIX ARTIFACT</b><p>保有口座には存在しますが、現在読み込んでいるPHOENIXランキング/シグナルには含まれていません。推測値は表示しません。</p></div>}
                </aside>
              </div>

              <div className="detail-strip panel">
                <div><span>保有</span><strong>{selectedPosition ? `${selectedPosition.qty}株` : "なし"}</strong></div>
                <div><span>平均取得</span><strong>{selectedPosition ? (balancesHidden ? "••••" : `¥${num(selectedPosition.avg_price, 1)}`) : "—"}</strong></div>
                <div><span>評価損益</span><strong className={selectedPosition ? tone(selectedPosition.pnl) : ""}>{selectedPosition ? moneyView(selectedPosition.pnl) : "—"}</strong></div>
                <div><span>シグナル</span><strong>{selectedAnalysis?.trade_decision || selectedAnalysis?.signal || selectedItem.signal}</strong></div>
              </div>
            </section>
          ) : null}

          {tab === "ranking" ? (
            <div className="opportunity-page">
              <section className="panel section-card ranking-card">
                <div className="section-heading"><div><small>MORNING SELECTION</small><h2>朝のPHOENIX選定</h2></div><span className={analysisStale ? "stale-badge" : "current-badge"}>{analysisStale ? "STALE" : "TODAY"}</span></div>
                <div className="opportunity-runline"><b>生成 {analysisGeneratedAt || "—"}</b><span>{state.meta?.analysis_consistency || "NOT_PROVEN"}</span><span>{state.meta?.analysis_count ?? ranked.length} candidates</span></div>
                {analysisAvailable ? <>
                  <div className="ranking-list">
                    {ranked.map((item, index) => (
                      <button type="button" className="ranking-row opportunity-row" key={`morning-${item.ticker}`} onClick={() => openSummary(item.ticker)}>
                        <span className="rank-no">{String(index + 1).padStart(2, "0")}</span>
                        <span className="rank-symbol"><b>{item.ticker.replace(".T", "")}</b><small>{item.name}</small><em className="rank-reason">{item.discovery_reason || item.reason || item.technical_reason || item.phoenix_reason || item.decision_reason || "PHOENIXスコア上位候補"}</em><span className="candidate-metrics">RSI {typeof item.rsi === "number" ? num(item.rsi, 1) : "—"} · MACD {item.macd || "—"} · VOL {typeof item.volume_ratio === "number" ? `${num(item.volume_ratio, 2)}x` : "—"}</span></span>
                        <span className="rank-price"><b>{num(item.price, 1)}</b><small className={tone(item.change_pct)}>{signed(item.change_pct, "%")}</small></span>
                        <span className="rank-score"><small>PHX</small><b>{item.phoenix_score ?? item.score ?? "—"}</b></span>
                        <span className={`signal-chip ${(item.trade_decision || item.signal).toLowerCase()}`}>{item.trade_decision || item.signal}</span>
                        <span className="open-arrow">›</span>
                      </button>
                    ))}
                  </div>
                  <div className="ranking-footnote">LINE / Discordの代わりに、PHOENIX生成済み成果物をQがREAD ONLYで表示します。銘柄を選ぶとENTRY / TARGET / STOPと判断根拠を確認できます。</div>
                </> : <div className="ranking-unavailable"><b>PHOENIX MORNING ANALYSIS NOT CONNECTED</b><p>朝スクリーニング成果物がありません。Qは口座情報から候補を推測生成しません。</p></div>}
              </section>

              <section className="panel section-card ranking-card intraday-card">
                <div className="section-heading"><div><small>INTRADAY DISCOVERY</small><h2>場中に浮上した候補</h2></div><span className={intradayStale ? "stale-badge" : intradayAvailable ? "current-badge" : "muted-badge"}>{intradayAvailable ? (intradayStale ? "STALE" : "LIVE FEED") : "NOT CONNECTED"}</span></div>
                <div className="opportunity-runline"><b>更新 {intradayGeneratedAt || "—"}</b><span>{state.meta?.intraday_count ?? intradayCandidates.length} candidates</span><span>Q READ ONLY</span></div>
                {intradayAvailable && intradayCandidates.length ? <div className="ranking-list">
                  {intradayCandidates.map((item, index) => (
                    <button type="button" className="ranking-row opportunity-row intraday-row" key={`intraday-${item.ticker}-${item.discovered_at || index}`} onClick={() => openSummary(item.ticker)}>
                      <span className="rank-no new-rank">NEW</span>
                      <span className="rank-symbol"><b>{item.ticker.replace(".T", "")}</b><small>{item.name} · {item.discovered_at || "時刻未記録"}</small><em className="rank-reason">{item.discovery_reason || item.reason || item.decision_reason || "場中条件改善で候補昇格"}</em><span className="candidate-metrics">{item.promotion_status || "DISCOVERED"} · RSI {typeof item.rsi === "number" ? num(item.rsi, 1) : "—"} · MACD {item.macd || "—"} · VOL {typeof item.volume_ratio === "number" ? `${num(item.volume_ratio, 2)}x` : "—"}</span></span>
                      <span className="rank-price"><b>{num(item.price, 1)}</b><small className={tone(item.change_pct)}>{signed(item.change_pct, "%")}</small></span>
                      <span className="rank-score"><small>PHX</small><b>{item.phoenix_score ?? item.score ?? "—"}</b></span>
                      <span className={`signal-chip ${(item.trade_decision || item.signal).toLowerCase()}`}>{item.trade_decision || item.signal}</span>
                      <span className="open-arrow">›</span>
                    </button>
                  ))}
                </div> : <div className="ranking-unavailable intraday-unavailable"><b>INTRADAY DISCOVERY NOT CONNECTED</b><p>PHOENIX側の「朝選定外から場中に新規発掘する成果物」はまだ未接続です。Q側は先に表示口を実装し、実データが出るまでは候補を捏造しません。</p></div>}
              </section>

              <section className="panel section-card provenance-card">
                <div className="section-heading"><div><small>ANALYSIS PROVENANCE</small><h2>分析の出所・鮮度</h2></div><span>{state.meta?.provenance_mode || "READ ONLY"}</span></div>
                <div className="provenance-summary"><b>{state.meta?.analysis_lineage || "PHOENIX artifacts"}</b><span>整合性 {state.meta?.analysis_consistency || "NOT_PROVEN"}</span></div>
                <div className="provenance-grid">
                  {analysisArtifacts.map(([key, artifact]) => <div className="provenance-item" key={key}><span>{key}</span><b>{artifact.name || artifact.path.split(/[\\/]/).pop()}</b><small>{artifact.generated_at || "生成日時不明"} · {artifact.rows ?? 0} rows</small><em className={artifact.exists === false ? "missing" : artifact.stale ? "stale" : "current"}>{artifact.exists === false ? "MISSING" : artifact.stale ? "STALE" : "CURRENT"}</em><code>{artifact.sha256 ? artifact.sha256.slice(0, 12) : "NO HASH"}</code></div>)}
                  {intradayArtifact ? <div className="provenance-item intraday-provenance"><span>intraday</span><b>{intradayArtifact.name || "intraday_candidates.csv"}</b><small>{intradayArtifact.generated_at || "未生成"} · {intradayArtifact.rows ?? 0} rows</small><em className={intradayArtifact.exists === false ? "missing" : intradayArtifact.stale ? "stale" : "current"}>{intradayArtifact.exists === false ? "NOT CONNECTED" : intradayArtifact.stale ? "STALE" : "CURRENT"}</em><code>{intradayArtifact.sha256 ? intradayArtifact.sha256.slice(0, 12) : "NO HASH"}</code></div> : null}
                </div>
                <div className="ranking-footnote">QはPHOENIXを実行せず、成果物を読み取るだけです。生成時刻・行数・SHA-256短縮表示で「何を見ているか」を追跡できます。</div>
              </section>
            </div>
          ) : null}
        </div>
      )}

      <footer className="status-footer">
        <div className="footer-status-main"><StatusDot value={activeBeast === "phoenix" ? state.system.phoenix : "ISOLATED"} /><span>{beast.uiName}</span><b>{activeBeast === "phoenix" ? state.system.phoenix : "SHELL"}</b><span className={`status-pill ${isMock ? "mock" : isRealRss ? "real" : "warn"}`}>{isMock ? "MOCK" : isRealRss ? "REAL RSS" : "RSS OFFLINE"}</span><span className="status-pill readonly">READ ONLY</span><span className="status-updated">更新 {updatedAt.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</span></div>
        <div className="footer-desktop"><span>UI AUTHORITY</span><b>NONE</b><span>·</span><span>v0.4.0</span></div>
      </footer>

      {drawerOpen ? <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} /> : null}
      <aside className={`settings-drawer ${drawerOpen ? "open" : ""}`} aria-hidden={!drawerOpen}>
        <div className="drawer-head"><div><small>QUADRANT TERMINAL</small><h2>設定</h2></div><button type="button" onClick={() => setDrawerOpen(false)} aria-label="閉じる">×</button></div>

        <section className="drawer-section">
          <span className="drawer-label">外観</span>
          <div className="segmented">
            {(["system", "light", "dark"] as ThemeChoice[]).map((choice) => (
              <button type="button" key={choice} className={themeChoice === choice ? "active" : ""} onClick={() => setThemeChoice(choice)}>{choice === "system" ? "自動" : choice === "light" ? "ライト" : "ダーク"}</button>
            ))}
          </div>
          <p className="drawer-help">「自動」はiPhone / Windowsの外観設定に追従します。</p>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">モジュール</span>
          <div className="module-map-card">
            <span><b>{beast.uiName}</b><small>{beast.market}</small></span>
            <span className="module-map-arrow">→</span>
            <span><b>{beast.internalEngine}</b><small>INTERNAL ENGINE</small></span>
          </div>
          <p className="drawer-help">表示名だけをQUADRANT側で切り替えます。内部エンジン名・runtime・state・order authorityは変更しません。</p>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">システム状態</span>
          <div className="system-list">
            {[
              ["VERMILION / PHOENIX ENGINE", state.system.phoenix],
              ["MARKET", state.system.market_data],
              ["RAKUTEN RSS", state.system.rakuten_rss],
              ["LIVE RUNTIME", state.system.live_runtime],
              ["WATCHDOG", state.system.watchdog],
              ["PHOENIX ANALYSIS", state.system.analysis ?? "UNKNOWN"],
            ].map(([label, value]) => <div key={label}><span><StatusDot value={value} />{label}</span><b>{value}</b></div>)}
          </div>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">PHOENIXロジック表示</span>
          <div className="logic-card">
            <b>MORNING</b>
            <p>日足ベースのPHOENIX成果物から、PHOENIX SCORE・MA系トレンド・RSI14・MACD・出来高倍率・市場リスクを読み、BUY / WATCH / SKIP、押し目、TARGET、STOPを表示します。</p>
            <b>INTRADAY</b>
            <p>場中の新規発掘はPHOENIX側の成果物が出た場合だけ表示します。Q自身は候補を作らず、未接続時はNOT CONNECTEDのままにします。</p>
            <b>SCENARIO</b>
            <p>未来予測ではなく「ENTRY付近で条件維持なら候補、STOP割れで無効化」という条件付きシナリオとして表示します。</p>
          </div>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">分析プロヴェナンス</span>
          <div className="drawer-provenance">
            <div><span>MORNING</span><b>{analysisGeneratedAt || "—"}</b><em className={analysisStale ? "stale" : "current"}>{analysisStale ? "STALE" : "CURRENT"}</em></div>
            <div><span>INTRADAY</span><b>{intradayGeneratedAt || "—"}</b><em className={intradayAvailable ? intradayStale ? "stale" : "current" : "missing"}>{intradayAvailable ? intradayStale ? "STALE" : "CURRENT" : "NOT CONNECTED"}</em></div>
            <div><span>LINEAGE</span><b>{state.meta?.analysis_consistency || "NOT_PROVEN"}</b><em>{state.meta?.provenance_mode || "READ ONLY"}</em></div>
          </div>
          <p className="drawer-help">詳細な生成時刻・行数・SHA-256は「本日の狙い目」最下部のANALYSIS PROVENANCEで確認できます。</p>
        </section>

        <section className="drawer-section">
          <span className="drawer-label">操作ガイド</span>
          <ol className="quick-guide">
            <li><b>マーケット切替</b><span>上部の「VERMILION」をタップ</span></li>
            <li><b>画面切替</b><span>上の3タブから選択</span></li>
            <li><b>銘柄詳細</b><span>保有一覧・ランキングの銘柄をタップ</span></li>
            <li><b>iPhoneホーム画面</b><span>Safariの共有 →「ホーム画面に追加」でアプリ風に起動</span></li>
          </ol>
        </section>

        <section className="drawer-section mobile-connection-help">
          <span className="drawer-label">スマホ接続</span>
          <div className="connection-card">
            <b>API HOST</b>
            <code>{API_HOST}:8765</code>
            <p>PCのread-only APIへ接続します。現在の楽天RSS連携はExcelブリッジ経由で、注文関数は使用しません。外部アクセスは将来VPN経由にします。</p>
          </div>
        </section>

        <div className="drawer-safety"><b>READ ONLY / EXECUTION AUTHORITY NONE</b><p>QUADRANT UIからbroker mutationへ直接到達する経路は作りません。</p></div>
      </aside>
    </main>
  );
}

function HoldingCard({ position, item, masked, onOpen }: { position: Position; item?: WatchItem; masked: boolean; onOpen: () => void }) {
  return (
    <button type="button" className="holding-card" onClick={onOpen}>
      <div className="holding-symbol"><span>{position.ticker.replace(".T", "")}</span><small>{position.name ?? item?.name ?? position.ticker}</small>{position.account_type ? <em>{position.account_type}</em> : null}</div>
      <div className="holding-quote"><strong>{num(position.last, 1)}</strong><small>{item ? signed(item.change_pct, "%") : "NOT_PROVEN"}</small></div>
      <div className="holding-position"><span>{position.qty}株</span><small>平均 {masked ? "••••" : `¥${num(position.avg_price, 1)}`}</small></div>
      <div className="holding-pnl"><strong className={tone(position.pnl)}>{masked ? "••••••" : money(position.pnl)}</strong><small className={tone(position.pnl_pct)}>{masked ? "••••" : signed(position.pnl_pct, "%")}</small></div>
      <div className="holding-score"><small>{position.execution ?? "NOT_PROVEN"}</small><strong>{position.side || "NOT_PROVEN"}</strong></div>
      <span className="open-arrow">›</span>
    </button>
  );
}

export default App;

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src/components/MarketChart.tsx

````text
import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";
import type { ChartBar } from "../types";

function t(value: string): UTCTimestamp {
  return Math.floor(new Date(value).getTime() / 1000) as UTCTimestamp;
}

function lineData(bars: ChartBar[], key: "ma5" | "ma25" | "ma75" | "ema12" | "ema26"): LineData<UTCTimestamp>[] {
  return bars.flatMap((bar) => {
    const value = bar[key];
    return typeof value === "number" ? [{ time: t(bar.time), value }] : [];
  });
}

export function MarketChart({
  bars,
  theme,
  accent,
  scenario,
}: {
  bars: ChartBar[];
  theme: "light" | "dark";
  accent: string;
  scenario?: { entry?: number; target?: number; stop?: number };
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ma5Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma25Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ma75Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema12Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema26Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      width: Math.max(container.clientWidth, 1),
      height: Math.max(container.clientHeight, 240),
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: theme === "dark" ? "#8b98a5" : "#5f6a75", attributionLogo: false },
      grid: {
        vertLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
        horzLines: { color: theme === "dark" ? "rgba(255,255,255,.045)" : "rgba(20,36,50,.075)" },
      },
      rightPriceScale: { borderColor: theme === "dark" ? "rgba(255,255,255,.10)" : "rgba(20,36,50,.12)" },
      timeScale: { borderColor: theme === "dark" ? "rgba(255,255,255,.10)" : "rgba(20,36,50,.12)", timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: accent }, horzLine: { color: accent } },
    });
    chartRef.current = chart;
    candleRef.current = chart.addSeries(CandlestickSeries, { upColor: "#22c58b", downColor: "#ef5b70", borderUpColor: "#22c58b", borderDownColor: "#ef5b70", wickUpColor: "#22c58b", wickDownColor: "#ef5b70" });
    volumeRef.current = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
    volumeRef.current.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    ma5Ref.current = chart.addSeries(LineSeries, { color: "#f5c542", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    ma25Ref.current = chart.addSeries(LineSeries, { color: "#4f8cff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    ma75Ref.current = chart.addSeries(LineSeries, { color: "#b16cff", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    ema12Ref.current = chart.addSeries(LineSeries, { color: "#23c8a5", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    ema26Ref.current = chart.addSeries(LineSeries, { color: "#f58b57", lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      chart.applyOptions({ width: Math.max(1, Math.floor(entry.contentRect.width)), height: Math.max(240, Math.floor(entry.contentRect.height)) });
    });
    observer.observe(container);
    return () => { observer.disconnect(); chart.remove(); chartRef.current = null; };
  }, []);

  useEffect(() => {
    const candles: CandlestickData<UTCTimestamp>[] = bars.map((b) => ({ time: t(b.time), open: b.open, high: b.high, low: b.low, close: b.close }));
    const volumes: HistogramData<UTCTimestamp>[] = bars.map((b) => ({ time: t(b.time), value: b.volume, color: b.close >= b.open ? "rgba(34,197,139,.30)" : "rgba(239,91,112,.30)" }));
    candleRef.current?.setData(candles);
    volumeRef.current?.setData(volumes);
    ma5Ref.current?.setData(lineData(bars, "ma5"));
    ma25Ref.current?.setData(lineData(bars, "ma25"));
    ma75Ref.current?.setData(lineData(bars, "ma75"));
    ema12Ref.current?.setData(lineData(bars, "ema12"));
    ema26Ref.current?.setData(lineData(bars, "ema26"));
    chartRef.current?.timeScale().fitContent();
  }, [bars]);

  useEffect(() => {
    const candle = candleRef.current;
    if (!candle) return;
    for (const line of priceLinesRef.current) candle.removePriceLine(line);
    priceLinesRef.current = [];
    const add = (price: number | undefined, title: string, color: string) => {
      if (!price || price <= 0) return;
      priceLinesRef.current.push(candle.createPriceLine({ price, title, color, lineWidth: 1, axisLabelVisible: true }));
    };
    add(scenario?.entry, "ENTRY", accent);
    add(scenario?.target, "TARGET", "#22c58b");
    add(scenario?.stop, "STOP", "#ef5b70");
  }, [scenario?.entry, scenario?.target, scenario?.stop, accent]);

  useEffect(() => {
    chartRef.current?.applyOptions({
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: theme === "dark" ? "#8b98a5" : "#5f6a75", attributionLogo: false },
      crosshair: { vertLine: { color: accent }, horzLine: { color: accent } },
    });
  }, [accent, theme]);

  return <div className="market-chart" ref={containerRef} aria-label="楽天RSS実OHLCVチャート" />;
}
````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src/data/mock.ts

````text
import type { PhoenixSnapshot } from "../types";

export const mockSnapshot: PhoenixSnapshot = {
  mode: "READ_ONLY",
  source: "BUNDLED_MOCK",
  as_of: new Date().toISOString(),
  system: {
    phoenix: "ONLINE",
    market_data: "SIMULATED",
    rakuten_rss: "NOT_CONNECTED",
    live_runtime: "ISOLATED",
    watchdog: "OK",
    analysis: "MOCK",
  },
  account: {
    equity: 4_862_430,
    buying_power: 1_725_000,
    day_pnl: 28_460,
    day_pnl_pct: 0.59,
    unrealized_pnl: 41_700,
  },
  watchlist: [
    { ticker: "7203.T", name: "Toyota", price: 3018.0, change_pct: 1.24, score: 92, signal: "BUY" },
    { ticker: "8306.T", name: "MUFG", price: 2365.5, change_pct: 0.82, score: 87, signal: "WATCH" },
    { ticker: "9984.T", name: "SoftBank G", price: 17120.0, change_pct: -0.31, score: 78, signal: "HOLD" },
    { ticker: "6758.T", name: "Sony G", price: 3248.0, change_pct: 0.46, score: 84, signal: "BUY" },
    { ticker: "6501.T", name: "Hitachi", price: 4483.0, change_pct: 1.03, score: 89, signal: "WATCH" },
  ],
  positions: [
    { ticker: "7203.T", name: "Toyota", side: "LONG", qty: 100, avg_price: 2945.0, last: 3018.0, pnl: 7300, pnl_pct: 2.48, market_value: 301800, account_type: "特定", pending_qty: 0 },
    { ticker: "8306.T", name: "MUFG", side: "LONG", qty: 200, avg_price: 2310.0, last: 2365.5, pnl: 11100, pnl_pct: 2.4, market_value: 473100, account_type: "NISA", pending_qty: 0 },
  ],
  orders: [
    { time: "14:31:52", ticker: "6758.T", side: "BUY", qty: 100, type: "LIMIT", price: 3240.0, status: "SUBMITTED" },
    { time: "14:29:18", ticker: "7203.T", side: "SELL", qty: 100, type: "STOP", price: 2970.0, status: "WORKING" },
  ],
  executions: [
    { time: "13:42:05", ticker: "8306.T", side: "BUY", qty: 200, price: 2310.0, status: "FILLED" },
    { time: "09:14:33", ticker: "7203.T", side: "BUY", qty: 100, price: 2945.0, status: "FILLED" },
  ],
  meta: { analysis_available: true, account_scope: "mock", equity_basis: "mock" },
  events: [
    { time: "14:31:53", level: "INFO", message: "6758.T BUY request accepted by mock adapter" },
    { time: "14:30:21", level: "INFO", message: "7203.T quote update received" },
    { time: "14:29:04", level: "PASS", message: "Risk policy observation: PASS (display only)" },
    { time: "09:00:00", level: "INFO", message: "QUADRANT / VERMILION read-only session started (PHOENIX engine)" },
  ],
};

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src/main.tsx

````text
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);


if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src/styles.css

````text
:root {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-synthesis: none;
  text-rendering: geometricPrecision;
}
* { box-sizing: border-box; }
html, body, #root { margin: 0; min-width: 320px; min-height: 100%; }
body { margin: 0; }
button { font: inherit; }
button, a { -webkit-tap-highlight-color: transparent; }

.app-shell {
  --accent: #ff5a36;
  --accent-2: #ffb34d;
  --bg: #080a0d;
  --bg-elevated: #0d1116;
  --panel: rgba(15, 19, 24, .94);
  --panel-2: #121820;
  --line: rgba(255,255,255,.09);
  --line-soft: rgba(255,255,255,.055);
  --text: #edf1f4;
  --muted: #8995a0;
  --muted-2: #596672;
  --shadow: 0 18px 50px rgba(0,0,0,.28);
  --positive: #22c58b;
  --negative: #ef5b70;
  --warning: #d8a94b;
  min-height: 100vh;
  color: var(--text);
  background:
    radial-gradient(circle at 50% -10%, color-mix(in srgb, var(--accent) 12%, transparent), transparent 34rem),
    linear-gradient(180deg, var(--bg-elevated), var(--bg));
  transition: background .25s ease, color .25s ease;
}
.app-shell[data-theme="light"] {
  --bg: #eef1f4;
  --bg-elevated: #f7f8fa;
  --panel: rgba(255,255,255,.94);
  --panel-2: #f7f8fa;
  --line: rgba(28,39,49,.13);
  --line-soft: rgba(28,39,49,.075);
  --text: #18212a;
  --muted: #66727e;
  --muted-2: #8b96a1;
  --shadow: 0 14px 42px rgba(36,47,58,.10);
}
.panel { background: var(--panel); border: 1px solid var(--line); box-shadow: var(--shadow); }
.positive { color: var(--positive) !important; }
.negative { color: var(--negative) !important; }
.neutral { color: var(--muted) !important; }

.app-header {
  position: sticky; top: 0; z-index: 40;
  min-height: 70px; display: flex; align-items: center; justify-content: space-between; gap: 18px;
  padding: 10px max(18px, env(safe-area-inset-right)) 10px max(18px, env(safe-area-inset-left));
  background: color-mix(in srgb, var(--bg-elevated) 92%, transparent);
  border-bottom: 1px solid var(--line); backdrop-filter: blur(18px);
}
.brand-lockup { display: flex; align-items: center; gap: 11px; min-width: 0; }
.shishin-mark { width: 40px; height: 40px; border: 1px solid color-mix(in srgb, var(--accent) 72%, var(--line)); display: grid; place-items: center; color: var(--accent); font: 800 19px/1 ui-serif, Georgia, serif; box-shadow: inset 0 0 20px color-mix(in srgb, var(--accent) 7%, transparent); }
.brand-copy { min-width: 0; }
.brand-copy strong { display: block; letter-spacing: .08em; font-size: 15px; white-space: nowrap; }
.brand-copy strong span { color: var(--muted); font-size: 11px; font-weight: 650; }
.brand-copy small { display: block; color: var(--muted-2); letter-spacing: .13em; font-size: 8px; margin-top: 3px; white-space: nowrap; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.beast-switcher-wrap { position: relative; }
.beast-switcher { min-width: 225px; height: 48px; display: grid; grid-template-columns: 34px 1fr 18px; align-items: center; gap: 8px; padding: 6px 10px; color: var(--text); background: var(--panel); border: 1px solid var(--line); cursor: pointer; text-align: left; }
.beast-switcher:hover { border-color: color-mix(in srgb, var(--accent) 48%, var(--line)); }
.beast-mini { width: 30px; height: 30px; display: grid; place-items: center; color: var(--accent); border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--line)); font-weight: 800; }
.beast-switch-text { display: grid; gap: 2px; }
.beast-switch-text b { font-size: 12px; letter-spacing: .06em; }
.beast-switch-text small { color: var(--muted); font-size: 8px; letter-spacing: .06em; }
.chevron { color: var(--muted); font-size: 18px; }
.beast-menu { position: absolute; top: calc(100% + 8px); right: 0; width: 330px; padding: 6px; z-index: 80; }
.beast-menu button { width: 100%; min-height: 62px; display: grid; grid-template-columns: 38px 1fr auto; align-items: center; gap: 10px; padding: 8px; background: transparent; border: 1px solid transparent; color: var(--text); text-align: left; cursor: pointer; }
.beast-menu button:hover, .beast-menu button.selected { background: color-mix(in srgb, var(--item-accent) 7%, transparent); border-color: color-mix(in srgb, var(--item-accent) 32%, var(--line)); }
.menu-glyph { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid color-mix(in srgb, var(--item-accent) 46%, var(--line)); color: var(--item-accent); font-weight: 800; }
.beast-menu button > span:nth-child(2) { display: grid; gap: 3px; }
.beast-menu b { font-size: 11px; }
.beast-menu small { color: var(--muted); font-size: 9px; }
.beast-menu em { color: var(--muted-2); font-size: 8px; font-style: normal; letter-spacing: .08em; }
.clock-block { display: grid; justify-items: end; gap: 2px; min-width: 84px; }
.clock-block span { color: var(--muted); font-size: 8px; letter-spacing: .08em; }
.clock-block time { font: 700 15px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
.menu-button { width: 44px; height: 44px; display: grid; place-items: center; color: var(--text); background: var(--panel); border: 1px solid var(--line); cursor: pointer; font-size: 20px; }
.menu-button:hover { border-color: color-mix(in srgb, var(--accent) 48%, var(--line)); }

.main-tabs { position: sticky; top: 70px; z-index: 30; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); max-width: 920px; margin: 0 auto; background: color-mix(in srgb, var(--bg) 94%, transparent); border: 1px solid var(--line); border-top: 0; backdrop-filter: blur(16px); }
.main-tabs button { position: relative; min-height: 57px; border: 0; border-right: 1px solid var(--line); background: transparent; color: var(--muted); cursor: pointer; display: grid; place-items: center; align-content: center; gap: 3px; }
.main-tabs button:last-child { border-right: 0; }
.main-tabs button span { font-size: 12px; font-weight: 750; }
.main-tabs button small { font-size: 7px; letter-spacing: .14em; color: var(--muted-2); }
.main-tabs button.active { color: var(--text); background: color-mix(in srgb, var(--accent) 5%, transparent); }
.main-tabs button.active::after { content: ""; position: absolute; left: 18%; right: 18%; bottom: 0; height: 2px; background: linear-gradient(90deg, var(--accent), var(--accent-2)); box-shadow: 0 0 12px color-mix(in srgb, var(--accent) 55%, transparent); }

.content-wrap { width: min(1240px, calc(100% - 28px)); margin: 18px auto 64px; }
.overview-strip { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 10px; }
.metric-card { min-height: 78px; padding: 13px 14px; background: var(--panel); border: 1px solid var(--line); display: grid; align-content: center; gap: 4px; }
.metric-card > span { color: var(--muted); font-size: 9px; letter-spacing: .08em; }
.metric-card strong { font: 750 18px/1.15 ui-monospace, SFMono-Regular, Menlo, monospace; }
.metric-card small { color: var(--muted-2); font-size: 8px; letter-spacing: .06em; }
.page-grid { display: grid; grid-template-columns: minmax(0, 1fr) 310px; gap: 10px; }
.section-card { overflow: hidden; }
.section-heading { min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px 16px; border-bottom: 1px solid var(--line-soft); }
.section-heading.compact { min-height: 56px; }
.section-heading small { color: var(--muted-2); font-size: 8px; letter-spacing: .12em; }
.section-heading h2 { margin: 3px 0 0; font-size: 15px; letter-spacing: .03em; }
.section-heading > span { color: var(--muted); font-size: 9px; }
.holdings-list { padding: 4px 0; }
.holding-card { width: 100%; display: grid; grid-template-columns: 1.2fr .9fr .9fr 1fr 70px 20px; align-items: center; gap: 10px; min-height: 78px; padding: 10px 16px; color: var(--text); background: transparent; border: 0; border-bottom: 1px solid var(--line-soft); cursor: pointer; text-align: left; }
.holding-card:last-child { border-bottom: 0; }
.holding-card:hover { background: color-mix(in srgb, var(--accent) 5%, transparent); }
.holding-symbol, .holding-quote, .holding-position, .holding-pnl, .holding-score { display: grid; gap: 3px; }
.holding-symbol span { font: 800 16px ui-monospace, SFMono-Regular, Menlo, monospace; }
.holding-symbol small, .holding-position small, .holding-pnl small, .holding-score small { color: var(--muted); font-size: 8px; }
.holding-quote strong, .holding-pnl strong { font: 750 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
.holding-quote small { font-size: 9px; }
.holding-position span { font-weight: 700; font-size: 11px; }
.holding-score { justify-items: center; }
.holding-score strong { font: 800 22px/1 ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--accent); }
.open-arrow { color: var(--muted-2); font-size: 24px; justify-self: end; }
.side-insight { min-height: 300px; }
.glance-score { display: grid; justify-items: center; padding: 28px 16px 20px; }
.glance-score span { color: var(--muted); font-size: 8px; letter-spacing: .12em; }
.glance-score strong { color: var(--accent); font: 850 58px/1 ui-monospace, SFMono-Regular, Menlo, monospace; margin: 7px 0; text-shadow: 0 0 24px color-mix(in srgb, var(--accent) 24%, transparent); }
.glance-score small { color: var(--muted); font-size: 10px; }
.primary-link { width: calc(100% - 28px); margin: 0 14px; min-height: 44px; display: flex; align-items: center; justify-content: space-between; padding: 0 13px; border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--line)); color: var(--text); background: color-mix(in srgb, var(--accent) 7%, transparent); cursor: pointer; }
.read-only-note { margin: 14px; padding: 12px; border: 1px solid var(--line); background: var(--panel-2); }
.read-only-note b { color: var(--warning); font-size: 9px; letter-spacing: .12em; }
.read-only-note p { color: var(--muted); font-size: 9px; line-height: 1.6; margin: 5px 0 0; }

.summary-page { display: grid; gap: 10px; }
.instrument-hero { overflow: hidden; }
.instrument-main { min-height: 94px; display: grid; grid-template-columns: 1fr auto 104px; align-items: center; gap: 18px; padding: 12px 16px; }
.symbol-block { display: grid; gap: 6px; }
.symbol-block > small { color: var(--muted-2); font-size: 8px; letter-spacing: .12em; }
.symbol-block > div { display: flex; align-items: baseline; gap: 10px; }
.symbol-block strong { font: 850 27px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
.symbol-block span { color: var(--muted); font-size: 11px; }
.quote-block { display: grid; justify-items: end; gap: 4px; }
.quote-block strong { font: 800 27px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
.quote-block span { font-size: 10px; }
.score-ring { min-height: 72px; border-left: 1px solid var(--line); display: grid; justify-items: center; align-content: center; }
.score-ring small { color: var(--muted-2); font-size: 7px; letter-spacing: .12em; }
.score-ring strong { color: var(--accent); font: 850 30px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
.score-ring span { color: var(--muted); font-size: 8px; margin-top: 3px; }
.symbol-picker { display: flex; gap: 5px; padding: 8px 12px; border-top: 1px solid var(--line-soft); overflow-x: auto; scrollbar-width: none; }
.symbol-picker::-webkit-scrollbar { display: none; }
.symbol-picker button { flex: 0 0 auto; min-width: 58px; height: 30px; border: 1px solid var(--line); background: transparent; color: var(--muted); cursor: pointer; font: 700 10px ui-monospace, SFMono-Regular, Menlo, monospace; }
.symbol-picker button.active { color: var(--text); border-color: color-mix(in srgb, var(--accent) 58%, var(--line)); background: color-mix(in srgb, var(--accent) 7%, transparent); }
.summary-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(300px, .85fr); gap: 10px; }
.chart-card, .analysis-card { min-width: 0; overflow: hidden; }
.market-chart { width: 100%; height: 340px; min-height: 340px; overflow: hidden; contain: layout paint; }
.analysis-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; padding: 10px; }
.analysis-grid .metric-card { min-height: 70px; box-shadow: none; }
.thesis-block, .risk-block { padding: 11px 14px; border-top: 1px solid var(--line-soft); }
.thesis-block > span, .risk-block > span { color: var(--muted); font-size: 8px; letter-spacing: .1em; }
.thesis-block p, .risk-block p { margin: 6px 0 0; color: var(--text); font-size: 10px; line-height: 1.5; }
.risk-block p { color: var(--muted); }
.detail-strip { display: grid; grid-template-columns: repeat(4, 1fr); overflow: hidden; }
.detail-strip > div { min-height: 68px; padding: 12px 14px; border-right: 1px solid var(--line-soft); display: grid; align-content: center; gap: 5px; }
.detail-strip > div:last-child { border-right: 0; }
.detail-strip span { color: var(--muted); font-size: 8px; }
.detail-strip strong { font: 750 13px ui-monospace, SFMono-Regular, Menlo, monospace; }

.ranking-card { overflow: hidden; }
.ranking-list { padding: 4px 0; }
.ranking-row { width: 100%; min-height: 72px; display: grid; grid-template-columns: 46px 1.35fr .9fr 80px 74px 18px; align-items: center; gap: 10px; padding: 8px 14px; color: var(--text); background: transparent; border: 0; border-bottom: 1px solid var(--line-soft); cursor: pointer; text-align: left; }
.ranking-row:hover { background: color-mix(in srgb, var(--accent) 5%, transparent); }
.rank-no { color: var(--muted-2); font: 700 18px ui-monospace, SFMono-Regular, Menlo, monospace; }
.ranking-row:first-child .rank-no { color: var(--accent); }
.rank-symbol, .rank-price, .rank-score { display: grid; gap: 3px; }
.rank-symbol b, .rank-price b { font: 750 13px ui-monospace, SFMono-Regular, Menlo, monospace; }
.rank-symbol small, .rank-price small, .rank-score small { color: var(--muted); font-size: 8px; }
.rank-score { justify-items: center; }
.rank-score b { color: var(--accent); font: 850 24px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }
.signal-chip { justify-self: start; min-width: 54px; padding: 5px 7px; border: 1px solid var(--line); font-size: 8px; font-weight: 800; text-align: center; }
.signal-chip.buy { color: var(--positive); border-color: color-mix(in srgb, var(--positive) 42%, var(--line)); }
.signal-chip.watch { color: var(--warning); border-color: color-mix(in srgb, var(--warning) 42%, var(--line)); }
.signal-chip.hold { color: var(--muted); }
.ranking-footnote { padding: 11px 14px; color: var(--muted-2); font-size: 8px; border-top: 1px solid var(--line-soft); }

.coming-card { min-height: 480px; display: grid; place-items: center; align-content: center; text-align: center; padding: 30px; }
.coming-glyph { width: 112px; height: 112px; display: grid; place-items: center; color: var(--accent); border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--line)); font: 850 48px/1 ui-serif, Georgia, serif; box-shadow: inset 0 0 40px color-mix(in srgb, var(--accent) 7%, transparent), 0 0 48px color-mix(in srgb, var(--accent) 9%, transparent); }
.coming-card > span { margin-top: 20px; color: var(--muted); font-size: 10px; letter-spacing: .12em; }
.coming-card h2 { margin: 8px 0 0; font-size: 30px; letter-spacing: .16em; }
.coming-card > p { margin: 8px 0; color: var(--muted); }
.coming-state { margin-top: 22px; padding: 8px 12px; border: 1px solid var(--line); color: var(--accent); font-size: 8px; letter-spacing: .1em; }
.coming-card .coming-copy { max-width: 520px; margin-top: 14px; font-size: 10px; line-height: 1.7; }

.status-footer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 25; min-height: 34px; padding: 0 16px max(0px, env(safe-area-inset-bottom)); display: flex; align-items: center; justify-content: space-between; gap: 16px; color: var(--muted); background: color-mix(in srgb, var(--bg-elevated) 92%, transparent); border-top: 1px solid var(--line); backdrop-filter: blur(18px); font-size: 8px; letter-spacing: .07em; }
.status-footer > div { display: flex; align-items: center; gap: 7px; }
.status-footer b { color: var(--text); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--warning); box-shadow: 0 0 8px color-mix(in srgb, var(--warning) 55%, transparent); flex: 0 0 auto; }
.status-dot.ok { background: var(--positive); box-shadow: 0 0 8px color-mix(in srgb, var(--positive) 55%, transparent); }
.status-dot.muted { background: var(--muted-2); box-shadow: none; }

.drawer-backdrop { position: fixed; inset: 0; z-index: 89; background: rgba(0,0,0,.46); backdrop-filter: blur(2px); }
.settings-drawer { position: fixed; z-index: 90; top: 0; right: 0; bottom: 0; width: min(390px, 92vw); padding-bottom: env(safe-area-inset-bottom); transform: translateX(102%); transition: transform .22s ease; background: var(--bg-elevated); border-left: 1px solid var(--line); box-shadow: -24px 0 60px rgba(0,0,0,.28); overflow-y: auto; }
.settings-drawer.open { transform: translateX(0); }
.drawer-head { min-height: 74px; display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--line); }
.drawer-head small { color: var(--muted-2); font-size: 8px; letter-spacing: .12em; }
.drawer-head h2 { margin: 4px 0 0; font-size: 18px; }
.drawer-head button { width: 38px; height: 38px; border: 1px solid var(--line); background: transparent; color: var(--text); font-size: 22px; cursor: pointer; }
.drawer-section { padding: 18px 16px; border-bottom: 1px solid var(--line-soft); }
.drawer-label { display: block; margin-bottom: 10px; color: var(--muted); font-size: 9px; letter-spacing: .1em; }
.segmented { display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid var(--line); }
.segmented button { height: 38px; border: 0; border-right: 1px solid var(--line); background: transparent; color: var(--muted); cursor: pointer; }
.segmented button:last-child { border-right: 0; }
.segmented button.active { color: var(--text); background: color-mix(in srgb, var(--accent) 10%, transparent); box-shadow: inset 0 -2px var(--accent); }
.drawer-help { color: var(--muted-2); font-size: 9px; line-height: 1.6; margin: 8px 0 0; }
.system-list { display: grid; gap: 1px; background: var(--line-soft); border: 1px solid var(--line-soft); }
.system-list > div { min-height: 42px; padding: 0 10px; background: var(--panel); display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.system-list span { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 9px; }
.system-list b { font-size: 8px; letter-spacing: .08em; }
.quick-guide { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.quick-guide li { padding: 10px; border: 1px solid var(--line); display: grid; gap: 4px; }
.quick-guide b { font-size: 10px; }
.quick-guide span { color: var(--muted); font-size: 9px; }
.drawer-safety { margin: 16px; padding: 12px; border: 1px solid color-mix(in srgb, var(--warning) 30%, var(--line)); background: color-mix(in srgb, var(--warning) 5%, transparent); }
.drawer-safety b { color: var(--warning); font-size: 8px; letter-spacing: .1em; }
.drawer-safety p { color: var(--muted); font-size: 9px; line-height: 1.6; margin: 5px 0 0; }

@media (max-width: 900px) {
  .brand-copy small, .clock-block { display: none; }
  .beast-switcher { min-width: 188px; }
  .content-wrap { width: min(100% - 20px, 760px); margin-top: 12px; }
  .overview-strip { grid-template-columns: 1fr 1fr; }
  .page-grid, .summary-grid { grid-template-columns: 1fr; }
  .holding-card { grid-template-columns: 1fr .75fr .8fr 70px 18px; }
  .holding-position { display: none; }
  .market-chart { height: 300px; min-height: 300px; }
}

@media (max-width: 640px) {
  .app-header { min-height: 62px; padding-top: calc(8px + env(safe-area-inset-top)); padding-left: 10px; padding-right: 10px; }
  .shishin-mark { width: 34px; height: 34px; font-size: 16px; }
  .brand-copy strong { font-size: 12px; }
  .brand-copy strong span { display: none; }
  .header-actions { gap: 6px; }
  .beast-switcher { min-width: 0; width: 135px; height: 40px; grid-template-columns: 27px 1fr 12px; padding: 4px 6px; gap: 5px; }
  .beast-mini { width: 25px; height: 25px; font-size: 12px; }
  .beast-switch-text b { font-size: 10px; }
  .beast-switch-text small { font-size: 7px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 76px; }
  .menu-button { width: 40px; height: 40px; font-size: 18px; }
  .beast-menu { position: fixed; top: calc(62px + env(safe-area-inset-top)); left: 8px; right: 8px; width: auto; }
  .main-tabs { top: calc(62px + env(safe-area-inset-top)); width: 100%; max-width: none; border-left: 0; border-right: 0; }
  .main-tabs button { min-height: 52px; }
  .main-tabs button span { font-size: 10px; }
  .main-tabs button small { font-size: 6px; }
  .content-wrap { width: calc(100% - 14px); margin: 9px 7px 58px; }
  .overview-strip { gap: 6px; margin-bottom: 7px; }
  .metric-card { min-height: 68px; padding: 10px; }
  .metric-card > span { font-size: 8px; }
  .metric-card strong { font-size: 14px; }
  .section-heading { min-height: 54px; padding: 9px 12px; }
  .section-heading h2 { font-size: 13px; }
  .holdings-page { gap: 7px; }
  .holding-card { min-height: 72px; grid-template-columns: 1.2fr .9fr .9fr 53px 14px; gap: 6px; padding: 9px 11px; }
  .holding-symbol span { font-size: 14px; }
  .holding-quote strong, .holding-pnl strong { font-size: 11px; }
  .holding-score strong { font-size: 19px; }
  .side-insight { min-height: 0; }
  .glance-score { padding: 18px 12px 14px; }
  .glance-score strong { font-size: 44px; }
  .instrument-main { min-height: 84px; grid-template-columns: 1fr auto 70px; gap: 8px; padding: 10px 11px; }
  .symbol-block strong { font-size: 21px; }
  .symbol-block span { display: block; font-size: 9px; }
  .quote-block strong { font-size: 20px; }
  .score-ring { min-height: 60px; }
  .score-ring strong { font-size: 25px; }
  .summary-grid { gap: 7px; }
  .market-chart { height: 250px; min-height: 250px; }
  .analysis-grid { gap: 5px; padding: 7px; }
  .analysis-grid .metric-card { min-height: 62px; }
  .detail-strip { grid-template-columns: 1fr 1fr; }
  .detail-strip > div { border-bottom: 1px solid var(--line-soft); }
  .detail-strip > div:nth-child(2) { border-right: 0; }
  .detail-strip > div:nth-last-child(-n+2) { border-bottom: 0; }
  .ranking-row { min-height: 68px; grid-template-columns: 34px 1fr 58px 50px 14px; gap: 7px; padding: 8px 10px; }
  .rank-price { display: none; }
  .rank-no { font-size: 15px; }
  .rank-symbol b { font-size: 12px; }
  .rank-score b { font-size: 20px; }
  .signal-chip { min-width: 47px; padding: 4px 5px; font-size: 7px; }
  .status-footer { min-height: 32px; padding-left: 10px; padding-right: 10px; }
  .footer-desktop { display: none !important; }
  .coming-card { min-height: 390px; }
  .coming-glyph { width: 90px; height: 90px; font-size: 39px; }
}

/* v0.3.0 — mobile-first refinement */
html { background: #080a0d; }
body { min-height: 100dvh; overscroll-behavior-y: contain; }
.app-shell { min-height: 100dvh; }
button { touch-action: manipulation; }
.holding-card, .ranking-row, .main-tabs button, .beast-switcher, .menu-button, .symbol-picker button, .primary-link {
  transition: background-color .14s ease, border-color .14s ease, transform .08s ease, opacity .14s ease;
}
.holding-card:active, .ranking-row:active, .main-tabs button:active, .beast-switcher:active, .menu-button:active, .symbol-picker button:active, .primary-link:active {
  transform: scale(.992);
}
.connection-card { border: 1px solid var(--line); background: var(--panel); padding: 12px; display: grid; gap: 7px; }
.connection-card b { color: var(--muted); font-size: 8px; letter-spacing: .1em; }
.connection-card code { color: var(--accent); font: 700 12px ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }
.connection-card p { margin: 0; color: var(--muted); font-size: 9px; line-height: 1.6; }

@media (max-width: 640px) {
  html, body, #root { min-height: 100dvh; }
  body { overflow-x: hidden; -webkit-text-size-adjust: 100%; }

  .app-header {
    min-height: calc(58px + env(safe-area-inset-top));
    padding: calc(7px + env(safe-area-inset-top)) max(8px, env(safe-area-inset-right)) 7px max(8px, env(safe-area-inset-left));
    gap: 6px;
  }
  .brand-lockup { gap: 6px; flex: 0 0 auto; }
  .shishin-mark { width: 36px; height: 36px; border-radius: 9px; }
  .brand-copy { display: none; }
  .header-actions { flex: 1; min-width: 0; justify-content: flex-end; }
  .beast-switcher-wrap { flex: 1; max-width: 210px; }
  .beast-switcher { width: 100%; min-width: 0; height: 42px; border-radius: 10px; grid-template-columns: 28px minmax(0, 1fr) 14px; }
  .beast-mini { border-radius: 7px; }
  .beast-switch-text small { max-width: none; }
  .menu-button { width: 42px; height: 42px; border-radius: 10px; flex: 0 0 auto; }
  .beast-menu {
    top: calc(58px + env(safe-area-inset-top));
    left: 8px; right: 8px;
    border-radius: 14px;
    max-height: calc(100dvh - 82px - env(safe-area-inset-top));
    overflow-y: auto;
  }
  .beast-menu button { min-height: 68px; border-radius: 10px; }

  .main-tabs {
    top: calc(58px + env(safe-area-inset-top));
    height: 54px;
    border: 0;
    border-bottom: 1px solid var(--line);
    box-shadow: 0 10px 24px color-mix(in srgb, var(--bg) 86%, transparent);
  }
  .main-tabs button { min-height: 54px; padding: 4px 3px; }
  .main-tabs button span { font-size: 10.5px; white-space: nowrap; }
  .main-tabs button small { display: none; }
  .main-tabs button.active::after { left: 12%; right: 12%; height: 3px; border-radius: 999px 999px 0 0; }

  .content-wrap { width: 100%; margin: 0 0 calc(48px + env(safe-area-inset-bottom)); padding: 8px 7px 10px; }
  .overview-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-bottom: 7px; }
  .metric-card { min-width: 0; min-height: 70px; border-radius: 12px; padding: 10px 11px; }
  .metric-card strong { font-size: clamp(13px, 4vw, 16px); overflow-wrap: anywhere; }
  .panel { border-radius: 13px; }
  .section-card, .instrument-hero, .chart-card, .analysis-card, .detail-strip { overflow: hidden; }
  .section-heading { min-height: 52px; padding: 9px 11px; }
  .section-heading h2 { font-size: 13px; }
  .section-heading > span { font-size: 8px; }

  .page-grid, .summary-grid { gap: 7px; }
  .holdings-list { padding: 3px 0; }
  .holding-card {
    min-height: 88px;
    grid-template-columns: minmax(0, 1.2fr) minmax(70px, .8fr) 58px 16px;
    grid-template-areas:
      "symbol quote score arrow"
      "symbol pnl score arrow";
    gap: 4px 8px;
    padding: 11px 10px 11px 12px;
  }
  .holding-symbol { grid-area: symbol; align-self: center; min-width: 0; }
  .holding-symbol span { font-size: 16px; }
  .holding-symbol small { font-size: 9px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .holding-quote { grid-area: quote; justify-items: end; align-self: end; }
  .holding-quote::before { content: "現在値"; color: var(--muted-2); font-size: 7px; }
  .holding-quote strong { font-size: 12px; }
  .holding-quote small { font-size: 8px; }
  .holding-position { display: none; }
  .holding-pnl { grid-area: pnl; justify-items: end; align-self: start; }
  .holding-pnl::before { content: "評価損益"; color: var(--muted-2); font-size: 7px; }
  .holding-pnl strong { font-size: 11px; }
  .holding-pnl small { font-size: 8px; }
  .holding-score { grid-area: score; align-self: center; justify-items: center; border-left: 1px solid var(--line-soft); }
  .holding-score strong { font-size: 24px; }
  .open-arrow { grid-area: arrow; align-self: center; font-size: 25px; }
  .holding-card:active, .ranking-row:active { background: color-mix(in srgb, var(--accent) 10%, transparent); }

  .side-insight { min-height: 0; }
  .glance-score { padding: 17px 12px 14px; }
  .glance-score strong { font-size: 46px; }
  .primary-link { min-height: 48px; border-radius: 10px; }
  .read-only-note { border-radius: 10px; }

  .instrument-main {
    min-height: 92px;
    grid-template-columns: minmax(0, 1fr) auto 72px;
    gap: 7px;
    padding: 11px;
  }
  .symbol-block { min-width: 0; }
  .symbol-block strong { font-size: 22px; }
  .symbol-block span { max-width: 120px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .quote-block { justify-items: end; }
  .quote-block strong { font-size: 19px; }
  .score-ring { min-height: 64px; border-radius: 10px; }
  .score-ring strong { font-size: 25px; }
  .symbol-picker { -webkit-overflow-scrolling: touch; scrollbar-width: none; padding: 8px 9px; gap: 6px; }
  .symbol-picker::-webkit-scrollbar { display: none; }
  .symbol-picker button { min-width: 64px; height: 36px; border-radius: 9px; }

  .market-chart { height: 272px; min-height: 272px; }
  .analysis-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .analysis-grid .metric-card { min-height: 64px; }
  .thesis-block, .risk-block { padding: 12px; }
  .thesis-block p, .risk-block p { font-size: 10px; line-height: 1.55; }
  .detail-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .detail-strip > div { min-height: 66px; }

  .ranking-row {
    min-height: 82px;
    grid-template-columns: 32px minmax(0, 1fr) 52px 54px 14px;
    grid-template-areas: "rank symbol score chip arrow";
    gap: 7px;
    padding: 10px 9px;
  }
  .rank-no { grid-area: rank; font-size: 15px; }
  .rank-symbol { grid-area: symbol; min-width: 0; }
  .rank-symbol b { font-size: 13px; }
  .rank-symbol small { font-size: 9px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .rank-price { display: none; }
  .rank-score { grid-area: score; }
  .rank-score b { font-size: 21px; }
  .signal-chip { grid-area: chip; min-width: 50px; padding: 5px 4px; border-radius: 8px; }
  .ranking-row .open-arrow { grid-area: arrow; }
  .ranking-footnote { font-size: 8px; line-height: 1.5; }

  .coming-card { min-height: calc(100dvh - 178px - env(safe-area-inset-top)); margin: 0; border-radius: 14px; }
  .coming-glyph { border-radius: 22px; }

  .status-footer {
    min-height: calc(38px + env(safe-area-inset-bottom));
    padding: 0 max(10px, env(safe-area-inset-right)) env(safe-area-inset-bottom) max(10px, env(safe-area-inset-left));
    font-size: 8px;
  }
  .status-footer > div:first-child { width: 100%; justify-content: center; }
  .footer-desktop { display: none !important; }

  .settings-drawer {
    width: 100%;
    top: max(10px, env(safe-area-inset-top));
    border-left: 0;
    border-top: 1px solid var(--line);
    border-radius: 18px 18px 0 0;
    box-shadow: 0 -20px 50px rgba(0,0,0,.32);
  }
  .drawer-head { min-height: 66px; padding-top: 10px; }
  .drawer-head button { border-radius: 10px; }
  .segmented { border-radius: 10px; overflow: hidden; }
  .segmented button { min-height: 44px; }
  .quick-guide li, .connection-card, .drawer-safety { border-radius: 10px; }
}

@media (max-width: 380px) {
  .beast-switcher-wrap { max-width: 176px; }
  .beast-switch-text small { max-width: 94px; }
  .holding-card { grid-template-columns: minmax(0, 1fr) minmax(62px, .72fr) 50px 12px; }
  .holding-score strong { font-size: 21px; }
  .ranking-row { grid-template-columns: 28px minmax(0, 1fr) 45px 48px 12px; }
  .signal-chip { min-width: 44px; font-size: 6.8px; }
}

/* v0.3.1 — focused navigation, mobile chart fullscreen, status clarity */
.chart-heading-actions { display: flex; align-items: center; gap: 10px; }
.chart-fullscreen-toggle { display: none; height: 32px; padding: 0 10px; border: 1px solid color-mix(in srgb, var(--accent) 38%, var(--line)); border-radius: 8px; background: color-mix(in srgb, var(--accent) 7%, var(--panel)); color: var(--text); font-size: 9px; font-weight: 750; cursor: pointer; }
.chart-fullscreen-toggle:active { transform: scale(.97); }
.decision-blocks { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; padding: 7px; }
.decision-block { min-height: 92px; padding: 12px; border: 1px solid var(--line-soft); background: color-mix(in srgb, var(--panel-2) 88%, transparent); }
.decision-block > span { display: block; margin-bottom: 7px; color: var(--accent); font-size: 8px; font-weight: 800; letter-spacing: .1em; }
.decision-block p { margin: 4px 0 0; color: var(--muted); font-size: 9px; line-height: 1.55; }
.caution-block > span { color: var(--warning); }
.invalidation-block > span { color: var(--negative); }
.rank-symbol em.rank-reason { display: block; margin-top: 4px; color: var(--muted-2); font-size: 8px; font-style: normal; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.status-pill { padding: 3px 6px; border: 1px solid var(--line); border-radius: 999px; font-size: 7px; font-weight: 850; letter-spacing: .08em; }
.status-pill.mock { color: var(--warning); border-color: color-mix(in srgb, var(--warning) 38%, var(--line)); }
.status-pill.real { color: var(--positive); border-color: color-mix(in srgb, var(--positive) 38%, var(--line)); }
.status-pill.readonly { color: var(--accent); border-color: color-mix(in srgb, var(--accent) 38%, var(--line)); }
.status-updated { color: var(--muted-2); font-variant-numeric: tabular-nums; }

@media (max-width: 640px) {
  .app-header { min-height: calc(54px + env(safe-area-inset-top)); padding-top: calc(5px + env(safe-area-inset-top)); padding-bottom: 5px; }
  .shishin-mark { width: 34px; height: 34px; }
  .beast-switcher { height: 38px; }
  .menu-button { width: 38px; height: 38px; }
  .main-tabs { top: calc(54px + env(safe-area-inset-top)); }
  .beast-menu { top: calc(54px + env(safe-area-inset-top)); }
  .chart-fullscreen-toggle { display: inline-flex; align-items: center; justify-content: center; }
  .chart-heading-actions { gap: 6px; }
  .chart-heading-actions > span { display: none; }
  .decision-blocks { grid-template-columns: 1fr; padding: 7px; }
  .decision-block { min-height: 0; border-radius: 10px; }
  .rank-symbol em.rank-reason { max-width: 170px; font-size: 7.6px; }
  .ranking-row { min-height: 94px; }
  .status-footer { overflow-x: auto; scrollbar-width: none; justify-content: flex-start; }
  .status-footer::-webkit-scrollbar { display: none; }
  .footer-status-main { min-width: max-content; width: auto !important; justify-content: flex-start !important; }
  .status-updated { display: inline; }
  body.chart-fullscreen-open { overflow: hidden; }
  .chart-card.fullscreen-chart { position: fixed; inset: 0; z-index: 140; display: grid; grid-template-rows: auto minmax(0, 1fr); border: 0; border-radius: 0; background: var(--bg); box-shadow: none; }
  .chart-card.fullscreen-chart .section-heading { min-height: calc(50px + env(safe-area-inset-top)); padding-top: calc(8px + env(safe-area-inset-top)); background: color-mix(in srgb, var(--bg-elevated) 96%, transparent); }
  .chart-card.fullscreen-chart .chart-heading-actions > span { display: inline; }
  .chart-card.fullscreen-chart .market-chart { height: 100% !important; min-height: 0 !important; }
}

@media (max-width: 900px) and (orientation: landscape) {
  .chart-card.fullscreen-chart .section-heading { min-height: 44px; padding-top: max(6px, env(safe-area-inset-top)); }
  .chart-card.fullscreen-chart .market-chart { height: calc(100dvh - 44px - env(safe-area-inset-top)) !important; }
}

/* Smartphone/touch full-screen must remain active after rotating to landscape. */
@media (hover: none) and (pointer: coarse) {
  .chart-fullscreen-toggle { display: inline-flex; align-items: center; justify-content: center; }
  body.chart-fullscreen-open { overflow: hidden; }
  .chart-card.fullscreen-chart { position: fixed; inset: 0; z-index: 140; display: grid; grid-template-rows: auto minmax(0, 1fr); border: 0; border-radius: 0; background: var(--bg); box-shadow: none; }
  .chart-card.fullscreen-chart .section-heading { min-height: calc(50px + env(safe-area-inset-top)); padding-top: calc(8px + env(safe-area-inset-top)); background: color-mix(in srgb, var(--bg-elevated) 96%, transparent); }
  .chart-card.fullscreen-chart .chart-heading-actions > span { display: inline; }
  .chart-card.fullscreen-chart .market-chart { height: 100% !important; min-height: 0 !important; }
}

/* v0.3.2 — QUADRANT branding layer. Engine ids remain unchanged intentionally. */
.quadrant-mark {
  border-radius: 10px;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 18px;
  font-weight: 900;
  letter-spacing: -.06em;
  background:
    linear-gradient(var(--panel), var(--panel)) padding-box,
    linear-gradient(145deg, var(--accent), color-mix(in srgb, var(--accent-2) 80%, white)) border-box;
  border: 1px solid transparent;
  box-shadow: inset 0 0 24px color-mix(in srgb, var(--accent) 8%, transparent), 0 0 24px color-mix(in srgb, var(--accent) 7%, transparent);
}
.brand-copy strong { letter-spacing: .14em; font-weight: 850; }
.beast-mini, .menu-glyph { font-size: 10px; letter-spacing: -.03em; }
.beast-switch-text b { text-transform: uppercase; letter-spacing: .09em; }
.beast-menu b { letter-spacing: .07em; }
.coming-card h2 { letter-spacing: .1em; }

@media (max-width: 640px) {
  .quadrant-mark { font-size: 16px; }
  .beast-switch-text b { font-size: 10px; }
  .beast-switch-text small { font-size: 7px; letter-spacing: .08em; }
}
.module-map-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: color-mix(in srgb, var(--accent) 4%, var(--panel));
}
.module-map-card > span:not(.module-map-arrow) { display: grid; gap: 3px; min-width: 0; }
.module-map-card b { color: var(--text); font-size: 10px; letter-spacing: .08em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.module-map-card small { color: var(--muted-2); font-size: 7px; letter-spacing: .09em; }
.module-map-arrow { color: var(--accent); font-weight: 900; }

/* v0.3.3 — QUADRANT guardian artwork integration */
.quadrant-mark,
.beast-mini,
.menu-glyph,
.coming-glyph {
  overflow: hidden;
  padding: 0;
  background: #07090c;
}
.quadrant-mark img,
.beast-mini img,
.menu-glyph img,
.coming-glyph img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.quadrant-mark {
  border-color: color-mix(in srgb, #d6aa47 58%, var(--line));
  box-shadow: 0 0 18px rgba(217, 169, 66, .12);
}
.quadrant-mark img { transform: scale(1.03); }
.beast-mini {
  border-color: color-mix(in srgb, var(--accent) 48%, #d2ad57 22%, var(--line));
  box-shadow: 0 0 12px color-mix(in srgb, var(--accent) 10%, transparent);
}
.menu-glyph {
  border-color: color-mix(in srgb, var(--item-accent) 42%, #d6aa47 28%, var(--line));
  border-radius: 7px;
  box-shadow: 0 0 12px color-mix(in srgb, var(--item-accent) 9%, transparent);
}
.beast-menu button.selected .menu-glyph {
  box-shadow: 0 0 18px color-mix(in srgb, var(--item-accent) 22%, transparent);
}
.coming-glyph {
  border-radius: 22px;
  border-color: color-mix(in srgb, var(--accent) 38%, #d6aa47 34%, var(--line));
  box-shadow: 0 0 42px color-mix(in srgb, var(--accent) 15%, transparent);
}
.coming-glyph img { transform: scale(1.015); }

@media (max-width: 640px) {
  .quadrant-mark { border-radius: 9px; }
  .beast-mini { border-radius: 7px; }
  .menu-glyph { width: 44px; height: 44px; }
  .beast-menu button { grid-template-columns: 44px 1fr auto; }
}

/* v0.4.0 — live account read-only bridge + portfolio usability */
.source-banner {
  min-height: 44px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: color-mix(in srgb, var(--panel) 94%, var(--accent) 6%);
  color: var(--muted);
}
.source-banner > div { display: flex; align-items: center; gap: 7px; min-width: 0; }
.source-banner b { color: var(--text); font-size: 9px; letter-spacing: .08em; white-space: nowrap; }
.source-banner span { min-width: 0; font-size: 9px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.source-banner em { font-style: normal; font-size: 8px; color: var(--muted-2); white-space: nowrap; }
.source-banner.real { border-color: color-mix(in srgb, #22c58b 42%, var(--line)); background: color-mix(in srgb, var(--panel) 93%, #22c58b 7%); }
.source-banner.error { border-color: color-mix(in srgb, #ef5b70 48%, var(--line)); background: color-mix(in srgb, var(--panel) 92%, #ef5b70 8%); }
.source-banner em.stale { color: #ffb34d; font-weight: 800; }

.holdings-heading .heading-actions { display: flex; align-items: center; gap: 8px; }
.privacy-toggle {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.privacy-toggle:hover { border-color: var(--accent); color: var(--accent); }

.portfolio-tools {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto;
  gap: 8px;
  padding: 9px 10px;
  border-top: 1px solid var(--line-soft);
  border-bottom: 1px solid var(--line-soft);
  background: color-mix(in srgb, var(--panel) 94%, var(--bg) 6%);
}
.portfolio-tools input {
  width: 100%;
  min-width: 0;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--bg-soft);
  color: var(--text);
  padding: 0 10px;
  font: inherit;
  font-size: 10px;
  outline: none;
}
.portfolio-tools input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent); }
.sort-chips { display: flex; align-items: center; gap: 5px; }
.sort-chips button {
  min-width: 48px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  font: inherit;
  font-size: 9px;
  cursor: pointer;
}
.sort-chips button.active { color: var(--text); border-color: var(--accent); background: color-mix(in srgb, var(--accent) 13%, transparent); }

.holding-symbol em {
  display: inline-flex;
  width: fit-content;
  margin-top: 5px;
  padding: 2px 6px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted-2);
  font-style: normal;
  font-size: 7px;
  line-height: 1.2;
}
.empty-list {
  min-height: 180px;
  display: grid;
  place-items: center;
  padding: 24px;
  color: var(--muted);
  font-size: 11px;
  text-align: center;
}

.analysis-offline-card,
.analysis-placeholder,
.ranking-unavailable {
  display: grid;
  align-content: center;
  gap: 8px;
  min-height: 170px;
  padding: 22px;
  text-align: center;
  background: color-mix(in srgb, var(--panel) 94%, var(--accent) 6%);
}
.analysis-offline-card b,
.analysis-placeholder b,
.ranking-unavailable b { color: var(--muted-2); font-size: 8px; letter-spacing: .12em; }
.analysis-offline-card strong { color: var(--text); font-size: 18px; letter-spacing: .04em; }
.analysis-offline-card p,
.analysis-placeholder p,
.ranking-unavailable p { margin: 0 auto; max-width: 560px; color: var(--muted); font-size: 10px; line-height: 1.7; }
.analysis-placeholder { min-height: 320px; }
.ranking-unavailable { min-height: 360px; }
.primary-link:disabled { opacity: .38; cursor: not-allowed; transform: none !important; }

.status-pill.warn { color: #ffb34d; border-color: color-mix(in srgb, #ffb34d 45%, var(--line)); background: color-mix(in srgb, #ffb34d 9%, transparent); }

@media (max-width: 640px) {
  .source-banner {
    min-height: 54px;
    grid-template-columns: 1fr auto;
    gap: 3px 8px;
    padding: 8px 10px;
    border-radius: 10px;
  }
  .source-banner > div { grid-column: 1 / 2; }
  .source-banner > span { grid-column: 1 / -1; grid-row: 2; font-size: 7.5px; }
  .source-banner > em { grid-column: 2; grid-row: 1; }
  .source-banner b { font-size: 8px; }

  .portfolio-tools {
    grid-template-columns: 1fr;
    gap: 7px;
    padding: 8px;
  }
  .portfolio-tools input { height: 38px; font-size: 11px; }
  .sort-chips { display: grid; grid-template-columns: repeat(3, 1fr); }
  .sort-chips button { height: 36px; min-width: 0; }
  .privacy-toggle { width: 32px; height: 32px; }
  .holding-symbol em { margin-top: 4px; }
  .analysis-placeholder { min-height: 230px; }
  .ranking-unavailable { min-height: 300px; padding: 18px; }
}

/* v0.4.0 — PHOENIX opportunity cockpit + provenance */
.opportunity-page { display: grid; gap: 12px; }
.opportunity-runline { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; padding: 8px 12px; border-top: 1px solid var(--line-soft); border-bottom: 1px solid var(--line-soft); color: var(--muted-2); font-size: 8px; }
.opportunity-runline b { color: var(--text); font-size: 9px; }
.current-badge, .muted-badge, .stale-badge { display: inline-flex; align-items: center; min-height: 24px; padding: 0 8px; border: 1px solid var(--line); border-radius: 999px; font-size: 7px; font-weight: 850; letter-spacing: .08em; }
.current-badge { color: var(--positive); border-color: color-mix(in srgb, var(--positive) 42%, var(--line)); }
.muted-badge { color: var(--muted-2); }
.candidate-metrics { display: block; margin-top: 5px; color: var(--accent); font-size: 7.5px; font-weight: 750; letter-spacing: .03em; }
.new-rank { color: var(--accent); font-size: 8px !important; font-weight: 900; letter-spacing: .06em; }
.intraday-row { background: color-mix(in srgb, var(--accent) 3%, var(--panel)); }
.intraday-unavailable { min-height: 180px; }
.provenance-card { overflow: hidden; }
.provenance-summary { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; padding: 10px 12px; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 8px; }
.provenance-summary b { color: var(--text); font-size: 9px; }
.provenance-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; padding: 10px; }
.provenance-item { display: grid; gap: 5px; min-width: 0; padding: 10px; border: 1px solid var(--line-soft); border-radius: 10px; background: color-mix(in srgb, var(--panel-2) 88%, transparent); }
.provenance-item > span { color: var(--accent); font-size: 7px; font-weight: 850; letter-spacing: .08em; text-transform: uppercase; }
.provenance-item b { overflow: hidden; color: var(--text); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.provenance-item small { color: var(--muted); font-size: 7.5px; line-height: 1.45; }
.provenance-item em { width: fit-content; font-size: 7px; font-style: normal; font-weight: 850; letter-spacing: .06em; }
.provenance-item em.current { color: var(--positive); }
.provenance-item em.stale { color: var(--warning); }
.provenance-item em.missing { color: var(--negative); }
.provenance-item code { overflow: hidden; color: var(--muted-2); font-size: 7px; text-overflow: ellipsis; white-space: nowrap; }
.logic-card { display: grid; gap: 6px; padding: 11px; border: 1px solid var(--line); border-radius: 10px; background: color-mix(in srgb, var(--panel) 94%, var(--accent) 6%); }
.logic-card b { color: var(--accent); font-size: 8px; letter-spacing: .09em; }
.logic-card p { margin: 0 0 5px; color: var(--muted); font-size: 8.5px; line-height: 1.55; }
.drawer-provenance { display: grid; gap: 7px; }
.drawer-provenance > div { display: grid; grid-template-columns: 72px minmax(0, 1fr) auto; align-items: center; gap: 7px; padding: 8px 9px; border: 1px solid var(--line-soft); border-radius: 9px; }
.drawer-provenance span { color: var(--muted-2); font-size: 7px; font-weight: 800; letter-spacing: .08em; }
.drawer-provenance b { overflow: hidden; color: var(--text); font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.drawer-provenance em { font-size: 7px; font-style: normal; font-weight: 850; }
.drawer-provenance em.current { color: var(--positive); }
.drawer-provenance em.stale { color: var(--warning); }
.drawer-provenance em.missing { color: var(--negative); }

@media (max-width: 900px) {
  .provenance-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 640px) {
  .opportunity-page { gap: 9px; }
  .opportunity-runline { gap: 4px 8px; padding: 7px 9px; font-size: 7px; }
  .candidate-metrics { font-size: 7px; line-height: 1.35; white-space: normal; }
  .provenance-grid { grid-template-columns: 1fr; gap: 6px; padding: 8px; }
  .provenance-summary { padding: 8px 9px; }
  .intraday-unavailable { min-height: 150px; }
  .drawer-provenance > div { grid-template-columns: 64px minmax(0, 1fr) auto; }
}
.scenario-path { position: relative; display: grid; grid-template-columns: minmax(82px, 1fr) 24px minmax(110px, 1.25fr) 24px minmax(82px, 1fr); align-items: center; gap: 5px; margin: 8px; padding: 13px 10px 36px; border: 1px solid var(--line-soft); border-radius: 11px; background: color-mix(in srgb, var(--panel-2) 90%, transparent); }
.scenario-node { display: grid; gap: 3px; min-height: 56px; align-content: center; padding: 8px; border: 1px solid var(--line); border-radius: 9px; text-align: center; }
.scenario-node span { color: var(--muted-2); font-size: 7px; font-weight: 850; letter-spacing: .08em; }
.scenario-node b { color: var(--text); font-size: 11px; }
.scenario-node small { color: var(--muted); font-size: 6.8px; line-height: 1.3; }
.scenario-node.entry { border-color: color-mix(in srgb, var(--accent) 55%, var(--line)); background: color-mix(in srgb, var(--accent) 8%, transparent); }
.scenario-node.target { border-color: color-mix(in srgb, var(--positive) 48%, var(--line)); }
.scenario-arrow { color: var(--accent); font-size: 22px; font-weight: 900; text-align: center; }
.scenario-arrow.up { color: var(--positive); }
.scenario-stop-line { position: absolute; left: 10px; right: 10px; bottom: 9px; display: flex; justify-content: space-between; gap: 10px; padding-top: 6px; border-top: 1px dashed color-mix(in srgb, var(--negative) 68%, var(--line)); color: var(--negative); font-size: 7px; }
.scenario-stop-line span { font-weight: 850; letter-spacing: .08em; }
.scenario-stop-line b { font-size: 8px; }
@media (max-width: 640px) {
  .scenario-path { grid-template-columns: 1fr 18px 1.15fr 18px 1fr; gap: 3px; margin: 7px; padding: 10px 6px 34px; }
  .scenario-node { min-height: 52px; padding: 6px 4px; }
  .scenario-node b { font-size: 9px; }
  .scenario-arrow { font-size: 17px; }
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src/types.ts

````text
export type ConnectionStatus = "ONLINE" | "OFFLINE" | "OK" | "SIMULATED" | "NOT_CONNECTED" | "ISOLATED" | "CONNECTED" | "REAL" | "UNAVAILABLE" | "UNKNOWN" | string;

export interface SystemState {
  phoenix: ConnectionStatus;
  market_data: ConnectionStatus;
  rakuten_rss: ConnectionStatus;
  live_runtime: ConnectionStatus;
  watchdog: ConnectionStatus;
  analysis?: ConnectionStatus;
}

export interface AccountState {
  equity: number;
  buying_power: number;
  day_pnl: number;
  day_pnl_pct: number;
  unrealized_pnl: number;
}

export interface WatchItem {
  ticker: string;
  name: string;
  price: number;
  change_pct: number;
  score: number | null;
  signal: string;
}

export interface RankingItem extends WatchItem {
  rank: number;
  origin?: "MORNING" | "INTRADAY";
  discovered_at?: string;
  discovery_reason?: string;
  promotion_status?: string;
  phoenix_score?: number;
  ai_score?: number;
  rank_label?: string;
  watch_status?: string;
  risk?: string;
  rsi?: number;
  macd?: string;
  volume_ratio?: number;
  expected_win_rate?: number;
  reason?: string;
  technical_reason?: string;
  learning_reason?: string;
  phoenix_reason?: string;
  plus_material?: string;
  caution_material?: string;
  monitor_timing?: string;
  base_price?: number;
  entry_price?: number;
  target_price?: number;
  stop_price?: number;
  trade_decision?: string;
  decision_reason?: string;
  market_risk_score?: number;
  market_risk_level?: string;
  artifact_generated_at?: string;
}

export type ChartTimeframe = "5m" | "15m" | "60m" | "4h" | "1d";

export interface ChartBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5?: number | null;
  ma25?: number | null;
  ma75?: number | null;
  ema12?: number | null;
  ema26?: number | null;
  rsi14?: number | null;
  macd?: number | null;
  macd_signal?: number | null;
}

export interface ChartPayload {
  ticker: string;
  timeframe: ChartTimeframe;
  rss_timeframe: string;
  derived: boolean;
  derived_note: string;
  source: string;
  mode: string;
  as_of: string;
  bars: ChartBar[];
  indicators: {
    basis: string;
    ma5?: number | null;
    ma25?: number | null;
    ma75?: number | null;
    ema12?: number | null;
    ema26?: number | null;
    rsi14?: number | null;
    macd?: number | null;
    macd_signal?: number | null;
  };
}

export interface Position {
  ticker: string;
  name?: string;
  side: "LONG" | "SHORT" | "NOT_PROVEN" | string;
  execution?: "CASH" | "MARGIN" | "NOT_PROVEN" | string;
  status?: "HOLDING" | "TRAILING" | "EXIT_PENDING" | "NOT_PROVEN" | string;
  current_stop?: number;
  current_r?: number;
  v_lock_display?: "ACTIVE" | "INACTIVE" | "NOT_PROVEN" | string;
  qty: number;
  avg_price: number;
  last: number;
  pnl: number;
  pnl_pct: number;
  market_value?: number;
  account_type?: string;
  pending_qty?: number;
  day_change?: number;
}

export interface OrderRow {
  time: string;
  ticker: string;
  side: string;
  qty: number;
  type: string;
  price: number | string;
  status: string;
}

export interface ExecutionRow {
  time: string;
  ticker: string;
  side: string;
  qty: number;
  price: number;
  status: string;
}

export interface EventRow {
  time: string;
  level: string;
  message: string;
}

export interface ArtifactProvenance {
  name?: string;
  path: string;
  exists?: boolean;
  rows?: number;
  generated_at: string;
  stale?: boolean;
  sha256?: string;
}

export interface SnapshotMeta {
  workbook?: string;
  account_scope?: string;
  analysis_available?: boolean;
  analysis_generated_at?: string;
  analysis_stale?: boolean;
  analysis_source?: string;
  analysis_count?: number;
  analysis_error?: string;
  analysis_consistency?: string;
  analysis_lineage?: string;
  analysis_artifacts?: Record<string, ArtifactProvenance>;
  intraday_available?: boolean;
  intraday_generated_at?: string;
  intraday_stale?: boolean;
  intraday_count?: number;
  intraday_source?: string;
  intraday_artifact?: ArtifactProvenance;
  provenance_mode?: string;
  equity_basis?: string;
  short_runtime?: "CONNECTED" | "NOT_CONNECTED" | string;
  error?: string;
}

export interface PhoenixSnapshot {
  mode: string;
  source: string;
  as_of: string;
  system: SystemState;
  account: AccountState;
  watchlist: WatchItem[];
  ranking?: RankingItem[];
  intraday_candidates?: RankingItem[];
  positions: Position[];
  orders: OrderRow[];
  executions: ExecutionRow[];
  events: EventRow[];
  meta?: SnapshotMeta;
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src/vite-env.d.ts

````text
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SHISHIN_API_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src-tauri/build.rs

````text
fn main() {
    tauri_build::build()
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src-tauri/capabilities/default.json

````text
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "Default capability for PHOENIX TERMINAL read-only shell",
  "windows": ["main"],
  "permissions": ["core:default"]
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src-tauri/Cargo.toml

````text
[package]
name = "shishin-terminal"
version = "0.4.0"
description = "QUADRANT unified read-only trading terminal"
authors = ["QUADRANT"]
edition = "2021"

[lib]
name = "shishin_terminal_lib"
crate-type = ["staticlib", "cdylib", "rlib"]

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src-tauri/src/lib.rs

````text
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running QUADRANT TERMINAL");
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src-tauri/src/main.rs

````text
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    shishin_terminal_lib::run();
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/src-tauri/tauri.conf.json

````text
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "QUADRANT TERMINAL",
  "version": "0.4.0",
  "identifier": "com.shishin.terminal",
  "build": {
    "beforeDevCommand": "npm run dev",
    "devUrl": "http://localhost:1420",
    "beforeBuildCommand": "npm run build",
    "frontendDist": "../dist"
  },
  "app": {
    "windows": [
      {
        "label": "main",
        "title": "QUADRANT TERMINAL",
        "width": 1440,
        "height": 940,
        "minWidth": 1180,
        "minHeight": 760,
        "resizable": true,
        "fullscreen": false,
        "center": true
      }
    ],
    "security": {
      "csp": "default-src 'self'; connect-src 'self' http://127.0.0.1:8765 ws://127.0.0.1:8765; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"
    }
  },
  "bundle": {
    "active": true,
    "targets": "all"
  }
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/tsconfig.app.json

````text
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"]
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/tsconfig.json

````text
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ]
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/tsconfig.node.json

````text
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}

````

## source/QUADRANT_TERMINAL_v0.4.0/frontend/vite.config.ts

````text
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
    host: host || "0.0.0.0",
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
});

````

## source/QUADRANT_TERMINAL_v0.4.0/README.md

````text
# QUADRANT TERMINAL v0.4.0

Unified read-only observation UI for the QUADRANT family.

- VERMILION — JAPAN EQUITIES — internal engine: PHOENIX
- AZURE — FX — internal engine: SEIRYU
- WHITE TIGER — GOLD — internal engine: BYAKKO
- BLACK WARRIOR — US INDICES — internal engine: GENBU

Internal engine names and execution authority are unchanged. QUADRANT remains READ ONLY.

## v0.4.0

### Rakuten account READ ONLY bridge

A dedicated Excel workbook is included at:

`rss/QUADRANT_READONLY_RSS.xlsx`

It uses only `RssPositionList`, `RssCapacityList`, `RssOrderList`, and `RssExecutionList`. The backend attaches to the workbook already open in Excel and reads the current MarketSpeed II RSS session's domestic-stock account data.

In explicit RSS mode, failure to connect returns an empty unavailable state. It never silently replaces a failed REAL account connection with mock holdings.

See `rss/README_RSS.md` for the short setup.

### UI refinement

- REAL RSS / MOCK / RSS OFFLINE is always visible.
- Holdings search by code/name/account type.
- Sort holdings by P/L, market value, or ticker.
- Privacy toggle masks balances and P/L on screen.
- Account type badges (e.g. 特定 / NISA).
- Current RSS buying power is surfaced in the holdings metrics.
- Stale-data warning after 10 seconds without a REAL snapshot update.
- When only account RSS is connected, PHOENIX SCORE/ranking is intentionally hidden rather than fabricated.
- Existing mobile fullscreen chart, responsive layout, dark-first theme, guardian icons, and system switcher remain.

## Start frontend

```bash
cd QUADRANT_TERMINAL_v0.4.0/frontend
npm install
npm run dev -- --host 0.0.0.0
```

## Start backend — mock UI

```bash
cd QUADRANT_TERMINAL_v0.4.0/backend
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

## Start backend — REAL Rakuten RSS READ ONLY

Open `rss/QUADRANT_READONLY_RSS.xlsx` in Excel first, then:

```bash
cd QUADRANT_TERMINAL_v0.4.0/backend
source .venv/Scripts/activate
QUADRANT_DATA_SOURCE=rss python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

The backend exposes only GET endpoints plus the state WebSocket. There are no POST/PUT/PATCH/DELETE order routes.

````

## source/QUADRANT_TERMINAL_v0.4.0/rss/README_RSS.md

````text
# QUADRANT — Rakuten RSS READ ONLY bridge

This bridge is observation-only. The workbook contains only these MarketSpeed II RSS functions:

- `RssPositionList()` — domestic cash equity holdings
- `RssCapacityList()` — cash buying power / capacity
- `RssOrderList()` — today's domestic stock order list
- `RssExecutionList()` — today's domestic stock executions

No order, modify, cancel, margin-open/close, or futures-order function is present.

## Windows use

1. Start MarketSpeed II and make MarketSpeed II RSS available.
2. Open `QUADRANT_READONLY_RSS.xlsx` in **Excel** and leave it open.
3. Confirm the Positions/Capacity sheets are populated by RSS.
4. Start the QUADRANT backend in explicit RSS mode:

```bash
cd QUADRANT_TERMINAL_v0.4.0/backend
source .venv/Scripts/activate
QUADRANT_DATA_SOURCE=rss python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

5. Start the frontend as usual and open QUADRANT.

If Excel/RSS/the workbook is unavailable, RSS mode returns an empty `RAKUTEN_RSS_UNAVAILABLE` state. It deliberately does **not** substitute fake portfolio data.

## Boundary

QUADRANT reads cells only. It does not press an order trigger, call a VBA order function, submit/cancel/modify an order, or hold broker mutation authority.

````

## source/QUADRANT_TERMINAL_v0.4.0/START_QUADRANT_READONLY.cmd

````text
@echo off
setlocal
set ROOT=%~dp0

echo [QUADRANT] Starting READ ONLY RSS backend...
start "QUADRANT BACKEND - RSS READ ONLY" cmd /k "pushd ""%ROOT%backend"" && set QUADRANT_DATA_SOURCE=rss && call .venv\Scripts\activate.bat && python -m uvicorn app:app --host 0.0.0.0 --port 8765"

timeout /t 2 /nobreak >nul

echo [QUADRANT] Starting frontend...
start "QUADRANT FRONTEND" cmd /k "cd /d "%ROOT%frontend" && npm run dev -- --host 0.0.0.0"

echo.
echo QUADRANT started in READ ONLY mode.
echo Local: http://localhost:1420/
echo LAN/Tailscale: use this PC's IP with port 1420.
echo.
pause

````

## source/QUADRANT_TERMINAL_v0.4.0/tests/test_margin_readonly.py

````text
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
import rss_readonly as r

class Sheet:
    def __init__(s, v): s.UsedRange = type("U", (), {"Value2": v, "Formula": v})()
class WB:
    def __init__(s, d): s.d = d
    def Worksheets(s, n):
        if n not in s.d: raise KeyError(n)
        return Sheet(s.d[n])

def adapter(): return r.ExcelRssReadOnlyAdapter.__new__(r.ExcelRssReadOnlyAdapter)

def test_margin_functions_not_order_tokens():
    for f in r.MARGIN_READ_SHEETS.values():
        assert not any(t.lower() in f.lower() for t in r.FORBIDDEN_ORDER_TOKENS)

def test_absent_sheet_not_proven():
    out = adapter()._read_margin(WB({}))
    assert all(v["status"] == "NOT_PROVEN" for v in out.values())

def test_unopened_dash():
    out = adapter()._read_margin(WB({"MarginPower": (("－",),)}))
    assert out["MarginPower"]["status"] == "UNOPENED_OR_EMPTY"

def test_read_and_boundary_rejects_order_formula():
    out = adapter()._read_margin(WB({"MarginPositions": (("a", "b"), ("1", "2"))}))
    assert out["MarginPositions"]["status"] == "READ"
    wb = WB({n: (("=RssMarginOpenOrder(1)",),) for n in ["Positions","Capacity","Orders","Executions"]})
    try: adapter()._verify_formula_boundary(wb)
    except r.RssReadOnlyUnavailable as e: assert "mutation" in str(e)
    else: raise AssertionError

````
