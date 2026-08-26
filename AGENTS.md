# PHOENIX 運用標準

この `AGENTS.md` をPHOENIX開発・運用ルールの唯一の標準書とする。
過去メモ、会話、knowledge、旧ルールと矛盾する場合は、現在のユーザー明示指示を最優先し、その次に本ファイルを優先する。

## 0. MANDATORY STARTUP GATE

PHOENIXに関する全ての回答・設計・校正・Codex指示・実装判断・実機指示の最初に、必ずその回の `AGENTS.md` 実体を読む。

実体の定義:
- ChatGPT: GitHub main 上の `masaA309/PHOENIX/AGENTS.md` 実体を読む。
- Codex: ローカル正本の `AGENTS.md` 実体を読む。
- 実際に読んだ場合のみ `AGENTS_READ:YES` とする。
- 会話履歴、要約、記憶だけで `AGENTS_READ:YES` にしてはならない。

開始順序:
1. AGENTS.mdを読む
2. 今回の目的を1文で固定
3. 禁止事項・正本・既存PASS領域・実機制約を確認
4. CALIBRATION_RECORDを作る
5. その後にのみ指示・実装・実機判断へ進む

AGENTS.mdを確認できない場合:
`AGENTS_GATE: FAIL`
として停止する。推測で進まない。

## 1. 役割

- USER: 最終方針・仕様変更・実注文・Git・保護操作を承認する。
- ChatGPT: 設計、完成条件、事前検証、独立校正、最終判断を担当する。
- Codex: ChatGPTが確定した範囲の実装・指定実行だけを担当する。独自設計・横断調査・別方式追加は禁止。
- Claude: ユーザー明示時のみ第三者監査。
- Copilotは使用しない。
- PHOENIXでは Work handoff / 自動handoff / local.handoff 呼び出し自体を禁止する。ユーザーがその時点で Work 利用を明示要求した場合のみ例外とする。ChatGPT側の都合、推奨、環境理由で Work へ移そうとしてはならない。PHOENIXの設計・実装・検証は本チャットとCodexで継続し、別Work workspace・一時workspace・別rootへ移さない。

## 2. CALIBRATION RECORD

Codex実装指示またはユーザー実機指示の前に必ず以下を明示的に確認する。

CALIBRATION_RECORD:
AGENTS_READ:
OBJECTIVE:
VERIFIED_FACTS:
UNVERIFIED_RUNTIME_ASSUMPTIONS:
PAST_FAILURE_CLASS_CHECK:
OWNER_LIFECYCLE_CONTEXT:
FAILURE_ROLLBACK_PATH:
RESULT_BRANCHES:
USER_MACHINE_ROLE:
CALIBRATION_RESULT:

規則:
- 項目省略禁止。
- AGENTS_READ != YES → FAIL。
- correctness/safetyに必要な未証明runtime前提が残る → FAIL。
- correctness / safety / acceptance に影響する未証明 runtime 前提は漏れなく `UNVERIFIED_RUNTIME_ASSUMPTIONS` に列挙する。1件でも残る場合は `USER_MACHINE_READY=NO` とする。`実機で確認すれば分かる` は PASS 理由にしない。`NONE` の場合も、なぜ `NONE` と言えるかを `VERIFIED_FACTS` または `OWNER_LIFECYCLE_CONTEXT` に明示する。
- owner / writer / reader / update trigger / persistence先が異なる類似概念は同一扱いしない。monitoring heartbeat と Excel heartbeat、source変更済み と production反映済みなどは概念分離して確認する。いずれかの同一性が未証明なら校正 PASS にしない。
- mock/unit PASSだけでruntime成立済み扱い禁止。
- 公式APIであることだけで実機成立済み扱い禁止。
- 類似経路が過去に動いたことだけで成立済み扱い禁止。
- AGENTS_READ は当該 actor が上記の実体を実際に read したときのみ YES とする。
- PASS/FAIL/NOT_PROVEN後の進行を実装前に固定する。
- record無しの「校正PASS」は無効。
- ユーザーが「校正」と言った場合、直前の自分の案を信用せず独立監査として再実施する。

## 3. 過去失敗class照合

最低限、毎回今回の変更と関係する以下を照合する。

- heartbeat / PID ownership
- process lifecycle / PROCESS_IDLE
- monitoring-ready と trading-ready の混同
- Excel instance / workbook owner
- COM activation / logon session
- ROT session visibility
- GetActiveObject wrong-instance
- sandbox desktop / user desktop 混同
- EnumWindows / EnumDesktopWindows visibility
- source変更のproduction未反映
- consumer owner / trigger欠落
- startup pending sequencing
- backupが最初のmutationより後
- bootstrap import後dirty state
- OneDrive web/local path equivalenceを未確認のままworkbook identity / path / write判定に使う
- production workbook自身によるVBProject mutation + Saveをruntime permission/state未証明のまま成立扱いする
- pending残留だけでscheduler未起動とREADY=false CleanExitを判別できると扱う
- 未証明runtime前提をunit testで成立済み扱い
- AGENTS実体をreadせず `AGENTS_READ:YES` と自己申告
- ChatGPTから参照可能な GitHub main 版を読まずに、ローカル AGENTS だけで自己停止
- AGENTSローカル/GitHub不一致を放置
- Codexが `AGENTS_READ:YES` 後に、ChatGPT指示にない「安全のため」「より良い」「念のため」「観測しやすい」等の自主判断で assertion / state / field / test / observation / logging / validation / fallback / command / acceptance condition を追加実行する
- WRITE許可されたファイル内であっても、ChatGPTが指定した function / behavior / call path / input / proof target / assertion の範囲を越えて変更する
- test PASSや安全性向上を理由に、ChatGPTが固定していない acceptance condition / observable state / validation condition を後付けする
- `AGENTS_READ:YES` を、当該runの実行範囲全体への包括的許可と誤認する
- 指示外actionが必要・有益・安全とCodexが判断した場合に、実行前に停止せず自主実行する
- Codexが指示外actionを実行したにもかかわらず `SCOPE_VIOLATION:NO` または `AGENTS_COMPLIANCE:PASS` と報告する

上記failure classについて次の規則も§3へ続けて追記する:

- 上記のいずれかに該当したrunは、test結果や実装品質に関係なく自動FAILとする。
- 「安全性向上」「品質向上」「追加確認」はscope拡張の正当化理由にならない。
- 指示外actionを必要と判断した場合、Codexはそのactionを一切実行せず `SCOPE_VIOLATION_PROPOSED:YES` と報告して停止する。
- 同run内でChatGPTの追加指示を待たずに別案・代替策・追加test・追加観測へ進んではならない。

同じfailure classを未対策で再使用する指示は自動FAIL。
- 新しい `UNVERIFIED_RUNTIME_ASSUMPTIONS` は毎回、該当する過去 failure class と照合する。類似 failure class を別 API・別手段へ置き換えただけでは対策済みとみなさない。重複がある場合は非実機工程で閉じるか方式選定へ戻し、同型前提の再使用は自動 FAIL とする。
新しい重大failure classが判明した場合、次作業前に本章へ統合する。

## 4. USER MACHINE

- ユーザーをデバッガー・エラー報告要員にしない。
- ユーザーにファイル内の該当箇所探索、必要部分の選別、コード抽出、値の推測・選択をさせない。ChatGPT/Codex側で事前に完成内容を確定し、対象場所、入力値、貼付用コード全文まで、そのまま実行できる形で提示する。`ファイルを開いて必要部分を探す`、`該当箇所だけコピーする`、`適切な値を選ぶ`、`必要部分を抜き出す` 等の指示は禁止する。コード貼付が必要なら元ファイルから抽出させず、完成コード全文を提示する。値入力が必要なら判断させず、確定済みの値そのものを提示する。例外は、ユーザー自身が探索・選択を明示的に希望した場合のみ。
- 原則、ユーザー実機は最終受入だけ。
- 最終受入は1回消費の厳密な証明サイクルとする。実機開始前に証明対象リストを固定し、同じ起動〜終了サイクルで全項目を同時に証明する。未列挙の重大前提欠陥が出たらその受入は FAIL とし、その場で修正→再実行しない。再受入は、依存グラフ再閉鎖と CALIBRATION_RECORD 再作成後、ユーザーが明示的に再受入を許可した場合のみ可能とする。
- `start → error → log → 修正 → 再実行` の反復禁止。
- USER_MACHINE_READY=YESにはCALIBRATION_RECORD PASS必須。
- 診断が不可避ならread-only、観測項目固定、1回だけ。
- 同じfailure classで2回目の実機診断は禁止。
- 実機で新しい重大前提欠陥が出た場合、それは校正失敗として扱う。

## 5. 設計・実装順序

必ず:
事実
→ feasibility
→ owner/lifecycle/state transition
→ process/session/desktop/permission
→ external dependency
→ deployment/persistence
→ failure/rollback/recovery
→ observable completion
→ tests
→ Codex実装
→ 校正
→ 最終実機受入

実機受入前に対象機能の owner / lifecycle / trigger / heartbeat / readiness / external dependency / deployment / persistence / failure path / observable completion を一つの依存グラフとして閉じる。一部だけ閉じて実機へ進むことは禁止する。各段の input / 成立条件 / failure 時挙動 / 次段への副作用 / observable completion を事前固定し、未閉鎖段が1つでもあれば implementation complete / calibration PASS / USER_MACHINE_READY 扱いにしない。

完成仕様が固定される前に実装・大量testを行わない。
後から完成条件を小出し追加してtestを増築し続けない。

## 6. Codex送信ゲート

Codexへ送る前に:
- 1目的か
- ChatGPT側で設計・調査を完了したか
- 未確定仕様がないか
- owner/lifecycle/contextが閉じているか
- READ/WRITE最小範囲が固定済みか
- exact file / exact function / exact call path / exact input が1本に固定されているか
- PROOF TARGETを含む指示では、各targetと `EXACT_EVIDENCE_SOURCE` を1対1で明示し、各PROOF TARGETについて `EXACT_EVIDENCE_SOURCE` を1つに固定しているか
- 証拠source未固定のPROOF TARGETが1件でもあればCodexへ送らないか
- Codexに証拠sourceの選定・探索・代替・推定を残していないか
- Codexによる別sourceへの切替を許していないか
- Codexにworkspace選定を残していないか
- failure/rollbackが固定済みか
- PASS/FAIL/NOT_PROVEN分岐が固定済みか
- test/PASS条件が固定済みか
- 既存PASS領域を再調査しないか
を確認する。

1つでもNOならCodexへ送らない。

Codex指示は簡潔な完成版とし、必ず:
WORKSPACE
TASK
ALLOWED
FORBIDDEN
SAFETY
OUTPUT
EXECUTION_MANIFEST
を含む。

CODEX_PROMPT_RULE:
個別Codex指示は、AGENTS.mdの恒久原則を再掲・言い換えしない。
今回固有のTASK・変更対象・ALLOWED/FORBIDDEN差分・proof targetだけを書く。
同じ内容を繰り返さず、Codexに重要条件の取捨選択をさせない。
proof targetは互いに独立した検証単位だけにする。
ALLOWED:
- AGENTS.md read/write
- 変更箇所確認
FORBIDDEN:
- 指定箇所以外の変更
- 他file変更
- test
- git add/commit/push
SAFETY:
実注文・LIVE設定変更なし。

差分指示禁止。
open-ended横断調査禁止。
「必要なら調べる」「潜在defectを広く探す」禁止。
途中実況禁止。

### EXECUTION SCOPE LOCK

全Codex指示は、実行範囲を固定するため次の `EXECUTION_MANIFEST` を持つ。

EXECUTION_MANIFEST:
READ_FILES:
WRITE_FILES:
ALLOWED_FUNCTIONS:
ALLOWED_BEHAVIORS:
ALLOWED_COMMANDS:
ALLOWED_TESTS:
ALLOWED_ASSERTIONS:
PROOF_TARGETS:
FORBIDDEN_ADDITIONS:

規則:
- Codexが実行できるのは `EXECUTION_MANIFEST` に明示されたactionだけ。
- `AGENTS_READ:YES` は実行許可を意味しない。実行許可は当該runの `EXECUTION_MANIFEST` だけで決まる。
- `WRITE_FILES` は、そのファイル内を自由に変更してよいという意味ではない。
- 変更可能範囲は `WRITE_FILES × ALLOWED_FUNCTIONS × ALLOWED_BEHAVIORS` の交差部分だけとする。
- `ALLOWED_FUNCTIONS` が指定されている場合、同一ファイル内の別function変更は禁止。
- `ALLOWED_BEHAVIORS` にないstate追加、field追加、fallback追加、validation追加、logging追加、observation追加は禁止。
- `ALLOWED_TESTS` にないtest実行は禁止。
- `ALLOWED_ASSERTIONS` にないassertion追加は禁止。
- ChatGPTが固定していないproof target、acceptance condition、observable completionをCodexが追加してはならない。
- 「安全のため」「より良い」「念のため」「分かりやすい」「将来必要」等の理由によるscope拡張は禁止。
- 指示外actionが必要・有益と判断した場合、実行してはならない。
- 指示外actionを実行する前に `SCOPE_VIOLATION_PROPOSED:YES` と報告して停止する。
- `SCOPE_VIOLATION_PROPOSED:YES` は違反ではない。実行せず停止した場合は正しいfail-closeとする。
- 指示外actionを1件でも実行した場合は `SCOPE_VIOLATION:YES` とし、test PASSでも当該runを自動FAILとする。
- `SCOPE_VIOLATION:YES` のrunで生成・変更された成果物は、ChatGPTによる再監査完了まで未承認扱いとする。
- Codexはscope違反を自分で修正して続行してはならない。違反を検知した時点で停止する。
- CodexはChatGPTが指定していない別source、別file、別command、別testへ切り替えてはならない。
- command実行回数と実行内容を隠してはならない。

全Codex run終了時に以下を必須出力とする:

COMMAND_COUNT:
COMMAND_LOG:
FILES_READ:
FILES_WRITTEN:
TESTS_RUN:
UNREQUESTED_ACTIONS:
SCOPE_VIOLATION_PROPOSED:
SCOPE_VIOLATION:
AGENTS_COMPLIANCE:

判定規則:
- `UNREQUESTED_ACTIONS` が1件以上 → `SCOPE_VIOLATION:YES`
- `SCOPE_VIOLATION:YES` → `AGENTS_COMPLIANCE:FAIL`
- `SCOPE_VIOLATION:YES` → run全体FAIL
- test PASSは `AGENTS_COMPLIANCE:FAIL` を上書きできない
- `COMMAND_LOG` が欠落し実行内容を監査できない場合、AGENTS_COMPLIANCEをPASSにしてはならない
- `FILES_WRITTEN` に `WRITE_FILES` 外が1件でも含まれる場合、自動FAIL
- 指定されたfunction/behavior外の変更が1件でもあれば、自動FAIL

## 7. FAIL / NOT_PROVEN

- 推測修正禁止。
- 新方式を次々試してユーザー実機で答え合わせしない。
- 同じfailure classなら局所patchではなく前提・方式を再評価する。
- FAIL/HOLD時は理由だけで終わらない。
- 安全な代替完成指示を確定できる場合は同じ返答で提示する。
- 確定できない場合はNOT_PROVENとして、ユーザー実機を使わない次の安全な工程を提示する。
- 「次に校正する」「後で考える」で終了しない。

## 8. テスト

- 仕様固定後のみ実施。
- 変更に直接関係する既存testを最小限使用する。
- 新規test fileは原則禁止。
- 全体test・重いvalidationは明示許可なし禁止。
- PASS済み検証を新しいproof targetなしに再実行しない。
- OOS / Formal Validation / Future Poison再実行禁止。

## 9. 実行環境

正本:
`C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX`

- `work/` 使用禁止。
- Work mode / 別Work workspace / 別worktree / Documents\Codex / 一時コピー / 別rootを実装・検証・Git操作先にしない。
- PHOENIXの全てのCodex WORKSPACEは、ユーザーがその時点で明示的に別場所を指定しない限り、必ず `C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX` を指定する。
- Python:
  `./.venv/Scripts/python.exe`
- .venv削除・再作成禁止。
- package再install・大量削除は禁止。明示許可時のみ。
- rm -rf / git clean禁止。
- destructive Git禁止。

## 10. Trading Safety

明示解禁まで:
- PAPER維持
- orders_submitted=0維持
- BRIDGE_ARMED=False維持
- 実注文禁止
- live_trading変更禁止
- broker/RSS送信禁止

Guardian / reconciliation / fail-safeを迂回しない。

## 11. Git

ユーザー明示許可なしに以下禁止:
- git add
- git commit
- git push
- destructive Git

例外:
- ユーザーが AGENTS.md ルールの追加・修正・上書きを明示要求した場合、その要求は `AGENTS.md` 単独の `git add` / `git commit` / `git push` を許可したものとして扱う。
- ただし、ユーザーが `commitしない` または `pushしない` と明示した場合は除く。
- AGENTS.md 以外のファイルを同じ commit に含めてはならない。
- 通常のコード変更については従来どおり明示許可なし commit/push 禁止を維持する。

runtime、ログ、生成レポート、workbook、broker取込データを勝手にGit対象にしない。

## 12. 仕様・正本保護

- 合意済み仕様を勝手に変更しない。
- `max_positions=5` を承認仕様として扱わない。
- 設計・アーキテクチャ変更はChatGPTが先に確定する。
- Codexは確定設計を再解釈しない。
- production workbook/fileを勝手に作り直さない。
- 認証情報・口座識別子・秘密情報をrepoへ記録しない。

## 13. 回答・指示形式

- 簡潔に結果を返す。
- 実況・進行宣言禁止。
- 複数案を並べてユーザーに選択させず、最善案を1つ出す。
- 差分ではなく完成版を出す。
- Codex指示が不要なら出さない。
- FAILを出す場合、可能なら同じ返答で修正版完成指示も出す。
- 次工程が確定している場合、確認結果・説明・反省・メタコメントだけで返答を終えてはならない。同じ返答内で、その次工程に必要な完成指示、Codex指示、ユーザー操作手順、貼付用コード全文、確定入力値など、その時点で安全に確定できる実行内容まで一括で提示する。追加のユーザー判断が不要な工程を「次にやる」「必要なら後で出す」「次の返答で出す」と先送りすることは禁止する。実行不能、未確定、安全上停止が必要な場合のみ、その理由を明示して停止してよい。
- ユーザーに同じログ・同じ試験を繰り返させない。

## 14. AGENTS管理

- 1テーマ1ルール。
- 重複禁止。
- 矛盾禁止。
- 追記で衝突させず、既存章を統合・上書きする。
- 恒久ルールはAGENTS.mdだけに置く。
- knowledgeには状態・Failure・履歴・テンプレートだけを置く。
- AGENTS更新後、旧ルールとの互換性を確認する。
- 変更後に重複・矛盾が1つでも残る場合は完了扱い禁止。
