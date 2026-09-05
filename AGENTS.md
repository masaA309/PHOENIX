# PHOENIX 運用標準

この AGENTS.md をPHOENIX開発・運用ルールの唯一の標準書とする。 過去メモ、会話、knowledge、旧ルールと矛盾する場合は、現在のユーザー明示指示を最優先し、その次に本ファイルを優先する。

## 0. MANDATORY STARTUP GATE

PHOENIXに関する全ての回答・設計・校正・Codex指示・実装判断・実機指示の最初に、必ずその回の AGENTS.md 実体を読む。

実体の定義:

ChatGPT: GitHub main 上の masaA309/PHOENIX/AGENTS.md 実体を読む。
Codex: ローカル正本の AGENTS.md 実体を読む。
実際に読んだ場合のみ AGENTS_READ:YES とする。
会話履歴、要約、記憶だけで AGENTS_READ:YES にしてはならない。

開始順序:

AGENTS.mdを読む
今回の目的を1文で固定
禁止事項・正本・既存PASS領域・実機制約を確認
CALIBRATION_RECORDを作る
その後にのみ指示・実装・実機判断へ進む

AGENTS.mdを確認できない場合: AGENTS_GATE: FAIL として停止する。推測で進まない。

## 1. 役割
USER: 最終方針・仕様変更・実注文・Git・保護操作を承認する。
ChatGPT: candidate設計、完成条件、事前検証、CALIBRATION_RECORD、EVIDENCE_GRAPH、EXECUTION_MANIFESTの作成を担当する。自分が作成したcandidateの独立監査者または単独の最終PASS判定者を兼ねない。PASS/FAIL/NOT_PROVENは構造化gate reportから導出する。
Mechanical Gate: schema・hash・failure class・scope・shell transport・output transportを決定論的に検査する。自由文の結論を出さない。
Completeness Review: candidateの完全性を再評価するが、同一モデル・同一provider・同一contextの場合は独立監査と表示しない。
Codex: ChatGPTが確定した範囲の実装・指定実行だけを担当する。独自設計・横断調査・別方式追加は禁止。
Claude: ユーザー明示時のみ第三者監査。
Copilotは使用しない。
PHOENIXでは Work handoff / 自動handoff / local.handoff 呼び出し自体を禁止する。ユーザーがその時点で Work 利用を明示要求した場合のみ例外とする。ChatGPT側の都合、推奨、環境理由で Work へ移そうとしてはならない。PHOENIXの設計・実装・検証は本チャットとCodexで継続し、別Work workspace・一時workspace・別rootへ移さない。
## 2. CALIBRATION RECORD

Codex実装指示またはユーザー実機指示の前に必ず以下を明示的に確認する。

CALIBRATION_RECORD: AGENTS_READ: OBJECTIVE: VERIFIED_FACTS: UNVERIFIED_RUNTIME_ASSUMPTIONS: PAST_FAILURE_CLASS_CHECK: OWNER_LIFECYCLE_CONTEXT: FAILURE_ROLLBACK_PATH: RESULT_BRANCHES: USER_MACHINE_ROLE: CALIBRATION_RESULT:

規則:

項目省略禁止。
AGENTS_READ != YES → FAIL。
correctness/safetyに必要な未証明runtime前提が残る → FAIL。
correctness / safety / acceptance に影響する未証明 runtime 前提は漏れなく UNVERIFIED_RUNTIME_ASSUMPTIONS に列挙する。1件でも残る場合は USER_MACHINE_READY=NO とする。実機で確認すれば分かる は PASS 理由にしない。NONE の場合も、なぜ NONE と言えるかを VERIFIED_FACTS または OWNER_LIFECYCLE_CONTEXT に明示する。
owner / writer / reader / update trigger / persistence先が異なる類似概念は同一扱いしない。monitoring heartbeat と Excel heartbeat、source変更済み と production反映済みなどは概念分離して確認する。いずれかの同一性が未証明なら校正 PASS にしない。
mock/unit PASSだけでruntime成立済み扱い禁止。
公式APIであることだけで実機成立済み扱い禁止。
類似経路が過去に動いたことだけで成立済み扱い禁止。
AGENTS_READ は当該 actor が上記の実体を実際に read したときのみ YES とする。
PASS/FAIL/NOT_PROVEN後の進行を実装前に固定する。
record無しの「校正PASS」は無効。
ユーザーが「校正」と言った場合、直前の自分の案を信用せずcandidateを凍結し、新しいreview invocationで再評価する。同一モデル・同一provider・同一contextによる再評価はCOMPLETENESS_REVIEWとし、独立監査と表示しない。ユーザーが明示した別providerまたは外部actorによる監査だけをINDEPENDENT_AUDITと表示する。
外部actorが利用不能でユーザーが代行reviewを明示承認した場合、review typeと独立性欠如を記録し、ユーザーがその限定を受容した場合に限りgovernance設計・governance実装へ進める。代行reviewだけで通常PHOENIX runtime、Disaster Recovery、ユーザー実機、Trading Safety、実注文をPASSにしてはならない。
CALIBRATION_RESULTを自由文で自己承認しない。gate対象では、candidate hashと一致する構造化gate reportからのみ導出する。machine checkにFAILが1件でもあればFAIL、NOT_PROVENが1件でもあればNOT_PROVENとする。ChatGPT、Mechanical Gate、Completeness Review、CodexはFAIL/NOT_PROVENをPASSへ上書きしない。
## 3. 過去失敗class照合

最低限、毎回今回の変更と関係する以下を照合する。

heartbeat / PID ownership
process lifecycle / PROCESS_IDLE
monitoring-ready と trading-ready の混同
Excel instance / workbook owner
COM activation / logon session
ROT session visibility
GetActiveObject wrong-instance
sandbox desktop / user desktop 混同
EnumWindows / EnumDesktopWindows visibility
source変更のproduction未反映
consumer owner / trigger欠落
startup pending sequencing
backupが最初のmutationより後
bootstrap import後dirty state
OneDrive web/local path equivalenceを未確認のままworkbook identity / path / write判定に使う
production workbook自身によるVBProject mutation + Saveをruntime permission/state未証明のまま成立扱いする
pending残留だけでscheduler未起動とREADY=false CleanExitを判別できると扱う
未証明runtime前提をunit testで成立済み扱い
AGENTS実体をreadせず AGENTS_READ:YES と自己申告
ChatGPTから参照可能な GitHub main 版を読まずに、ローカル AGENTS だけで自己停止
AGENTSローカル/GitHub不一致を放置
Codexが AGENTS_READ:YES 後に、ChatGPT指示にない「安全のため」「より良い」「念のため」「観測しやすい」等の自主判断で assertion / state / field / test / observation / logging / validation / fallback / command / acceptance condition を追加実行する
WRITE許可されたファイル内であっても、ChatGPTが指定した function / behavior / call path / input / proof target / assertion の範囲を越えて変更する
test PASSや安全性向上を理由に、ChatGPTが固定していない acceptance condition / observable state / validation condition を後付けする
AGENTS_READ:YES を、当該runの実行範囲全体への包括的許可と誤認する
指示外actionが必要・有益・安全とCodexが判断した場合に、実行前に停止せず自主実行する
Codexが指示外actionを実行したにもかかわらず SCOPE_VIOLATION:NO または AGENTS_COMPLIANCE:PASS と報告する

上記failure classについて次の規則も§3へ続けて追記する:

上記のいずれかに該当したrunは、test結果や実装品質に関係なく自動FAILとする。
「安全性向上」「品質向上」「追加確認」はscope拡張の正当化理由にならない。
指示外actionを必要と判断した場合、Codexはそのactionを一切実行せず SCOPE_VIOLATION_PROPOSED:YES と報告して停止する。
同run内でChatGPTの追加指示を待たずに別案・代替策・追加test・追加観測へ進んではならない。

同じfailure classを未対策で再使用する指示は自動FAIL。

新しい UNVERIFIED_RUNTIME_ASSUMPTIONS は毎回、該当する過去 failure class と照合する。類似 failure class を別 API・別手段へ置き換えただけでは対策済みとみなさない。重複がある場合は非実機工程で閉じるか方式選定へ戻し、同型前提の再使用は自動 FAIL とする。 新しい重大failure classが判明した場合、次作業前に本章へ統合する。

failure classの状態・履歴・closure evidenceの正本はknowledge/failure_class_ledger.jsonとする。candidateはdeclared_failure_class_ids、proposed_root_cause_text、resolved_root_cause_codeを必須とする。root cause resolverが既存classへ一意に解決できない場合はNEW_UNCLASSIFIEDまたはAMBIGUOUSとしてNOT_PROVENとし、新規classとして自動PASSしない。candidate申告classとresolver結果の不一致はFAILとする。新規class登録は通常candidateから分離したgovernance変更とし、ユーザー承認を必須とする。
CLOSEDは永久の再監査禁止を意味しない。CLOSED classを再利用可能とするには、closure evidenceのexact sourceとhashが一致し、validator/schema/dictionary versionが適用対象と互換で、required prevention controlsを全て覆い、time windowが有効で、新規evidence・identity変更・closure predicate欠陥・validator新規FAIL・ユーザー再監査要求がないことを機械確認する。1件でも未確認ならREOPENEDまたはNOT_PROVENとする。
## 4. USER MACHINE
ユーザーをデバッガー・エラー報告要員にしない。
ユーザーにファイル内の該当箇所探索、必要部分の選別、コード抽出、値の推測・選択をさせない。ChatGPT/Codex側で事前に完成内容を確定し、対象場所、入力値、貼付用コード全文まで、そのまま実行できる形で提示する。ファイルを開いて必要部分を探す、該当箇所だけコピーする、適切な値を選ぶ、必要部分を抜き出す 等の指示は禁止する。コード貼付が必要なら元ファイルから抽出させず、完成コード全文を提示する。値入力が必要なら判断させず、確定済みの値そのものを提示する。例外は、ユーザー自身が探索・選択を明示的に希望した場合のみ。
原則、ユーザー実機は最終受入だけ。
最終受入は1回消費の厳密な証明サイクルとする。実機開始前に証明対象リストを固定し、同じ起動〜終了サイクルで全項目を同時に証明する。未列挙の重大前提欠陥が出たらその受入は FAIL とし、その場で修正→再実行しない。再受入は、依存グラフ再閉鎖と CALIBRATION_RECORD 再作成後、ユーザーが明示的に再受入を許可した場合のみ可能とする。
start → error → log → 修正 → 再実行 の反復禁止。
USER_MACHINE_READY=YESにはCALIBRATION_RECORD PASS必須。
診断が不可避ならread-only、観測項目固定、1回だけ。
同じfailure classで2回目の実機診断は禁止。
実機で新しい重大前提欠陥が出た場合、それは校正失敗として扱う。
## 5. 設計・実装順序

必ず: 事実 → feasibility → owner/lifecycle/state transition → process/session/desktop/permission → external dependency → deployment/persistence → failure/rollback/recovery → observable completion → tests → Codex実装 → 校正 → 最終実機受入

実機受入前に対象機能の owner / lifecycle / trigger / heartbeat / readiness / external dependency / deployment / persistence / failure path / observable completion を一つの依存グラフとして閉じる。一部だけ閉じて実機へ進むことは禁止する。各段の input / 成立条件 / failure 時挙動 / 次段への副作用 / observable completion を事前固定し、未閉鎖段が1つでもあれば implementation complete / calibration PASS / USER_MACHINE_READY 扱いにしない。

完成仕様が固定される前に実装・大量testを行わない。 後から完成条件を小出し追加してtestを増築し続けない。

## 6. Codex送信ゲート

Codexへ送る前に:

1目的か
ChatGPT側で設計・調査を完了したか
未確定仕様がないか
owner/lifecycle/contextが閉じているか
READ/WRITE最小範囲が固定済みか
exact file / exact function / exact call path / exact input が1本に固定されているか
PROOF TARGETを含む指示では、各targetと EXACT_EVIDENCE_SOURCE を1対1で明示し、各PROOF TARGETについて EXACT_EVIDENCE_SOURCE を1つに固定しているか
証拠source未固定のPROOF TARGETが1件でもあればCodexへ送らないか
Codexに証拠sourceの選定・探索・代替・推定を残していないか
Codexによる別sourceへの切替を許していないか
Codexにworkspace選定を残していないか
failure/rollbackが固定済みか
PASS/FAIL/NOT_PROVEN分岐が固定済みか
test/PASS条件が固定済みか
既存PASS領域を再調査しないか を確認する。

1つでもNOならCodexへ送らない。

CHATGPT_SEND_POLICY_GATEとCODEX_EXECUTION_PREFLIGHT_GATEを区別する。repo内validatorはChatGPTの送信操作自体をプラットフォーム上で遮断できないため、送信側を機械的に強制したと主張してはならない。ChatGPT側は構造化candidateが完成していなければ送信しないpolicy gateとする。送信前にChatGPTが作ったcheck結果はPRECHECKであり、repo validatorが生成したgate reportと表示しない。
Codex側はAGENTS.md読取後、通常fileの読取・変更・testより前にCODEX_EXECUTION_PREFLIGHT_GATEを実行する。preflightで許されるのは、hash固定されたcandidateをstate/governance/incomingへ記録し、AGENTS.md・validator・schema・辞書・ledgerだけを読み、gate reportをstate/governance/reportsへ書くことだけとする。PASS以外なら通常fileへ進まず停止する。
candidate、AGENTS.md、validator、schema、辞書、ledger、実行scriptのhashをreportへ固定する。report後にいずれかが変わればstale reportとしてFAILとする。

Codex指示は簡潔な完成版とし、必ず: WORKSPACE TASK ALLOWED FORBIDDEN SAFETY OUTPUT EXECUTION_MANIFEST を含む。

CODEX_PROMPT_RULE: 個別Codex指示は、AGENTS.mdの恒久原則を再掲・言い換えしない。 今回固有のTASK・変更対象・ALLOWED/FORBIDDEN差分・proof targetだけを書く。 同じ内容を繰り返さず、Codexに重要条件の取捨選択をさせない。 proof targetは互いに独立した検証単位だけにする。

差分指示禁止。 open-ended横断調査禁止。 「必要なら調べる」「潜在defectを広く探す」禁止。 途中実況禁止。

### EXECUTION SCOPE LOCK

全Codex指示は、実行範囲を固定するため次の EXECUTION_MANIFEST を持つ。

EXECUTION_MANIFEST: READ_FILES: WRITE_FILES: ALLOWED_FUNCTIONS: ALLOWED_BEHAVIORS: ALLOWED_COMMANDS: ALLOWED_TESTS: ALLOWED_ASSERTIONS: PROOF_TARGETS: FORBIDDEN_ADDITIONS:

規則:

Codexが実行できるのは EXECUTION_MANIFEST に明示されたactionだけ。
AGENTS_READ:YES は実行許可を意味しない。実行許可は当該runの EXECUTION_MANIFEST だけで決まる。
WRITE_FILES は、そのファイル内を自由に変更してよいという意味ではない。
変更可能範囲は WRITE_FILES × ALLOWED_FUNCTIONS × ALLOWED_BEHAVIORS の交差部分だけとする。
ALLOWED_FUNCTIONS が指定されている場合、同一ファイル内の別function変更は禁止。
ALLOWED_BEHAVIORS にないstate追加、field追加、fallback追加、validation追加、logging追加、observation追加は禁止。
ALLOWED_TESTS にないtest実行は禁止。
ALLOWED_ASSERTIONS にないassertion追加は禁止。
ChatGPTが固定していないproof target、acceptance condition、observable completionをCodexが追加してはならない。
「安全のため」「より良い」「念のため」「分かりやすい」「将来必要」等の理由によるscope拡張は禁止。
指示外actionが必要・有益と判断した場合、実行してはならない。
指示外actionを実行する前に SCOPE_VIOLATION_PROPOSED:YES と報告して停止する。
SCOPE_VIOLATION_PROPOSED:YES は違反ではない。実行せず停止した場合は正しいfail-closeとする。
指示外actionを1件でも実行した場合は SCOPE_VIOLATION:YES とし、test PASSでも当該runを自動FAILとする。
SCOPE_VIOLATION:YES のrunで生成・変更された成果物は、ChatGPTによる再監査完了まで未承認扱いとする。
Codexはscope違反を自分で修正して続行してはならない。違反を検知した時点で停止する。
CodexはChatGPTが指定していない別source、別file、別command、別testへ切り替えてはならない。
command実行回数と実行内容を隠してはならない。

全Codex run終了時に以下を必須出力とする:

COMMAND_COUNT: COMMAND_LOG: FILES_READ: FILES_WRITTEN: TESTS_RUN: UNREQUESTED_ACTIONS: SCOPE_VIOLATION_PROPOSED: SCOPE_VIOLATION: AGENTS_COMPLIANCE:

判定規則:

UNREQUESTED_ACTIONS が1件以上 → SCOPE_VIOLATION:YES
SCOPE_VIOLATION:YES → AGENTS_COMPLIANCE:FAIL
SCOPE_VIOLATION:YES → run全体FAIL
test PASSは AGENTS_COMPLIANCE:FAIL を上書きできない
COMMAND_LOG が欠落し実行内容を監査できない場合、AGENTS_COMPLIANCEをPASSにしてはならない
FILES_WRITTEN に WRITE_FILES 外が1件でも含まれる場合、自動FAIL
指定されたfunction/behavior外の変更が1件でもあれば、自動FAIL
## 7. FAIL / NOT_PROVEN
推測修正禁止。
新方式を次々試してユーザー実機で答え合わせしない。
同じfailure classなら局所patchではなく前提・方式を再評価する。
FAIL/HOLD時は理由だけで終わらない。
安全な代替完成指示を確定できる場合は同じ返答で提示する。
確定できない場合はNOT_PROVENとして、ユーザー実機を使わない次の安全な工程を提示する。
「次に校正する」「後で考える」で終了しない。

machine validatorのFAIL/NOT_PROVENは停止状態として扱う。candidate修正時は同じreportを流用せず、新candidate IDで全checkを再評価する。
## 8. テスト
仕様固定後のみ実施。
変更に直接関係する既存testを最小限使用する。
新規test fileは原則禁止。
全体test・重いvalidationは明示許可なし禁止。
PASS済み検証を新しいproof targetなしに再実行しない。
OOS / Formal Validation / Future Poison再実行禁止。

governance validatorの新規test fileは、ユーザーが承認したgovernance専用runに限り例外として許可する。通常機能test、runtime、Excel、broker、OOS、Formal Validation、Future Poisonと同一runで実行しない。
## 9. 実行環境

正本: C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX

work/ 使用禁止。
Work mode / 別Work workspace / 別worktree / Documents\Codex / 一時コピー / 別rootを実装・検証・Git操作先にしない。
PHOENIXの全てのCodex WORKSPACEは、ユーザーがその時点で明示的に別場所を指定しない限り、必ず C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX を指定する。
Python: ./.venv/Scripts/python.exe
.venv削除・再作成禁止。
package再install・大量削除は禁止。明示許可時のみ。
rm -rf / git clean禁止。
destructive Git禁止。
## 10. Trading Safety

明示解禁まで:

PAPER維持
orders_submitted=0維持
BRIDGE_ARMED=False維持
実注文禁止
live_trading変更禁止
broker/RSS送信禁止

Guardian / reconciliation / fail-safeを迂回しない。

## 11. Git

ユーザー明示許可なしに以下禁止:

git add
git commit
git push
destructive Git

例外:

ユーザーが AGENTS.md ルールの追加・修正・上書きを明示要求した場合、その要求は AGENTS.md 単独の git add / git commit / git push を許可したものとして扱う。
ただし、ユーザーが commitしない または pushしない と明示した場合は除く。
AGENTS.md 以外のファイルを同じ commit に含めてはならない。
通常のコード変更については従来どおり明示許可なし commit/push 禁止を維持する。

runtime、ログ、生成レポート、workbook、broker取込データを勝手にGit対象にしない。

## 12. 仕様・正本保護
合意済み仕様を勝手に変更しない。
max_positions=5 を承認仕様として扱わない。
設計・アーキテクチャ変更はChatGPTが先に確定する。
Codexは確定設計を再解釈しない。
production workbook/fileを勝手に作り直さない。
認証情報・口座識別子・秘密情報をrepoへ記録しない。
## 13. 回答・指示形式
簡潔に結果を返す。
実況・進行宣言禁止。
複数案を並べてユーザーに選択させず、最善案を1つ出す。
差分ではなく完成版を出す。
Codex指示が不要なら出さない。
FAILを出す場合、可能なら同じ返答で修正版完成指示も出す。
次工程が確定している場合、確認結果・説明・反省・メタコメントだけで返答を終えてはならない。同じ返答内で、その次工程に必要な完成指示、Codex指示、ユーザー操作手順、貼付用コード全文、確定入力値など、その時点で安全に確定できる実行内容まで一括で提示する。追加のユーザー判断が不要な工程を「次にやる」「必要なら後で出す」「次の返答で出す」と先送りすることは禁止する。実行不能、未確定、安全上停止が必要な場合のみ、その理由を明示して停止してよい。この条件を満たさず、次の安全な実行可能アクションが確定しているのに報告・判定・反省だけで回答を終了した場合は RESPONSE_COMPLETION_FAIL とする。
ユーザーに同じログ・同じ試験を繰り返させない。

同一モデル・同一provider・同一contextで行ったreviewを独立監査、第三者監査、外部監査と表示しない。該当reviewはMECHANICAL_REVIEWまたはCOMPLETENESS_REVIEWと明示する。
## 14. AGENTS管理
1テーマ1ルール。
重複禁止。
矛盾禁止。
追記で衝突させず、既存章を統合・上書きする。
恒久ルールはAGENTS.mdだけに置く。
knowledgeには状態・Failure・履歴・テンプレートだけを置く。
AGENTS更新後、旧ルールとの互換性を確認する。
変更後に重複・矛盾が1つでも残る場合は完了扱い禁止。

恒久原則の唯一の正本はAGENTS.mdとする。governance validator、schema、正規化辞書はAGENTS.mdに明記された原則の実行可能な投影であり、それらだけで新しい恒久原則、PASS例外、権限変更を作らない。ledgerはfailureの状態・履歴・closure evidenceを保持するが、恒久原則を定義しない。外部fileがAGENTS.mdと不一致ならAGENTS_GATE:FAILとし、外部file側でAGENTS.mdを上書きしない。
AGENTS.md、governance validator、schema、failure ledger schema、root cause正規化辞書の変更はgovernance変更とする。通常機能変更と同一run・同一commitに含めない。変更後validatorで自己承認せず、変更artifactのhashを固定したreviewとユーザー承認を完了するまで有効化しない。

## 15. GOVERNANCE MACHINE GATE

正本artifact:

AGENTS.md
tools/codex_execution_preflight_gate.py
tools/governance_command_runner.py
config/governance/codex_candidate.schema.json
config/governance/evidence_graph.schema.json
config/governance/failure_class.schema.json
config/governance/gate_report.schema.json
config/governance/root_cause_synonyms.json
knowledge/failure_class_ledger.json
tests/test_codex_execution_preflight_gate.py

必須check:

MG-01 schema completeness: candidateの必須field・型・enumを検証する。
MG-02 proof binding: proofごとにSINGLE source 1件または明示ATOMIC_BUNDLE 1件を要求する。
MG-03 shell transport: Git BashからPowerShellへのinline -Commandを拒否し、path/hash固定.ps1を-Fileで実行する形式だけを許可する。
MG-04 output transport: 全commandをgovernance_command_runner経由に固定し、詳細stdout/stderrをfileへcaptureする。chatへ返すのは固定schema要約だけとし、実測byte上限をrunnerが強制する。上限到達時はchild processを停止し、OUTPUT_LIMIT_EXCEEDEDとしてrun FAILにする。途中までの詳細証拠を完全証明扱いしない。
MG-05 static contradiction: complete要求とtruncate、相反state必須値、PASS/FAIL同一predicate、evidence欠落、manifest外action必須、transport上限超過の既知矛盾を検出する。一般自然言語矛盾を完全検出できると主張しない。対象外で監査が必要ならNOT_PROVENとする。
MG-06 artifact identity: 実行前input、script、command fileのexact pathとSHA-256を照合する。実装対象sourceの変更後hashを事前既知と偽らない。
MG-07 failure ledger: root cause resolver、declared class、OPEN/REOPENED、CLOSED evidence validityを照合する。未知・曖昧・staleはPASSにしない。
MG-08 evidence lifecycle: owner、writer、reader、update trigger、persistence、runtime identity、time windowを必須とする。
MG-09 runtime preconditions: correctness/safetyに必要な未証明前提が1件でもあればUSER_MACHINE_READY:NOとする。
MG-10 rollback/stop: mutation前停止、failure path、rollback可能範囲を必須とする。
MG-11 user operation count: 原則0、最終受入のみexact operation 1回を許可する。
MG-12 review separation: hashは同一性だけを証明し独立性を証明しない。前段の自由文結論をreview inputへ含めず、review typeとactor invocation IDを記録する。

candidate hashはcandidate_sha256 fieldを除外し、UTF-8、key昇順、余分な空白なし、ensure_ascii=falseのcanonical JSON bytesにSHA-256を適用して算出する。validatorとcandidate producerは同じcanonicalization test vectorで一致を証明する。

Gate derivation:

machine checkにFAILが1件でもあればFAIL。
FAILがなくNOT_PROVENが1件でもあればNOT_PROVEN。
required reviewが未完了ならNOT_PROVEN。
candidate hashまたは依存artifact hashが不一致ならFAIL。
全条件が成立した場合だけPASS。

required reviewはcandidate作成者が任意に減らさない。全candidateにMECHANICAL_REVIEWとCOMPLETENESS_REVIEWを必須とする。ユーザーが外部監査を明示した場合、governance原則・validator・schema・正規化辞書を変更する場合、新しい重大failure classを登録する場合はINDEPENDENT_AUDITも必須とする。ただし外部actor利用不能時にユーザーが独立性欠如を理解して代行reviewを明示承認したgovernance変更だけは、SUBSTITUTE_COMPLETENESS_REVIEWとして記録して実装へ進める。この例外で通常runtime・実機・Trading SafetyをPASSにしない。
CODEX_EXECUTION_PREFLIGHT_GATE自体の起動はgovernance_command_runner必須の例外とする。preflightのstdoutは固定schema・固定byte上限とし、PASS後のcommandだけをgovernance_command_runner経由に限定する。state/governance/incomingとstate/governance/reportsはruntime evidenceでありGit対象にしない。
validator internal error、schema error、report欠落はFAILとして停止する。人間の自由文PASSで上書きしない。

## 16. ECO-FAST

ECO-FASTはPHOENIXの省トークン・省計算運用原則とする。目的達成に必要な実装、必要テスト、検証、終了を可能な限り1サイクルで完結する。実況、低価値なverification-only別サイクル、PASS後の磨き込み、任意リファクタ、合否に無関係なwarning修正、同一testの不要な再実行は禁止する。

repo全探索、同一内容の再読、既知仕様の再調査は必要時のみ行い、通常は必要ファイルだけを読む。routine作業は最小推論・最小操作で処理し、architecture / safety / owner / lifecycle / rollback などの難所は十分に推論してから進める。

ECO-FASTは安全gate、正確性、必要検証を省略する理由にしてはならない。commit/push許可があるサイクルでは、scope確認、commit、push、最終確認までを可能な限り一括化し、目的達成時点で即終了する。

ECO-FASTは既存の必須gate、review、承認、activation順序を変更せず、staleなgovernance evidenceを再利用する根拠にもならない。
