# PHOENIX 運用標準

PHOENIX の恒久policy本文は、canonical activation が証明された GitHub main の `AGENTS.md` を正本とする。
優先順位は、当該ターンのユーザー明示指示 > active `AGENTS.md` > machine-governance state > 会話履歴・memory・knowledge とする。
GitHub main または canonical local workspace に `AGENTS.md` が存在する事実だけでは、review済み・ユーザー承認済み・activation済み・machine projection整合済みを証明しない。
状態・履歴・failure class の OPEN/CLOSED、closure evidence、run evidenceはAGENTS.mdに重複保持しない。恒久的な再発防止policyだけをAGENTS.mdに保持する。
PHOENIXに関するChatGPTの標準品質は常時Astra品質とする。ユーザーが都度指定しなくても、事実分離、identity分離、設計整合、scope固定、failure分岐、proof binding、rollback、前進量を最高水準で扱う。Astra品質は過剰なwrapper、不要な外部監査、不要な再読、停止の自己目的化を意味しない。

## 0. MANDATORY STARTUP / POLICY STATUS GATE

PHOENIX に関する substantive turn / run の最初に、当該actorは指定されたAGENTS実体をfresh-readする。

- ChatGPT: GitHub main の `masaA309/PHOENIX/AGENTS.md`
- Codex: canonical local workspace の `AGENTS.md`

実際に読めた場合のみ `AGENTS_READ:YES` とする。
`AGENTS_READ:YES` が証明するのは「指定されたAGENTS実体をそのturn/runで読んだ」ことだけであり、内容の正しさ、review、ユーザー承認、canonical activation、local/main一致、machine enforcement、実装成立、runtime readinessを証明しない。
会話履歴、要約、memory、knowledge、過去runの結果だけで `AGENTS_READ:YES` にしてはならない。

PHOENIXのsubstantive response / runでは次を分離する。

`AGENTS_READ:YES|NO`
`AGENTS_SHA256:<64hex|NOT_PROVEN>`
`AGENTS_GIT_BLOB_SHA:<40hex|NOT_PROVEN>`
`AGENTS_READY:YES|NO`
`GOVERNANCE_MACHINE_READY:YES|NO`
`SIGNAL:GREEN|RED`

identity規則:
- `AGENTS_SHA256` はAGENTS raw bytesのSHA-256だけを指す。
- `AGENTS_GIT_BLOB_SHA` はGit object-format SHA-1 repositoryにおけるAGENTS blob idだけを指す。
- 40hex Git blob SHAと64hex raw SHA-256を比較しない。
- identityを単に `SHA` と呼んで種類を曖昧にしない。

`AGENTS_READY:YES` は、現在読んだexact AGENTS bytesについてrequired review、USER authorization、canonical apply、post-apply exact identity verifyが成立している場合だけ許可する。
ChatGPTではactive GitHub main AGENTSのexact postimage verificationが必要である。
Codexでは上記に加え、canonical local `AGENTS.md` raw bytesがactive GitHub main AGENTSとexact一致していることを確認する。
required evidenceが欠落、stale、競合、別identity、または確認不能なら `AGENTS_READY:NO` とする。

`GOVERNANCE_MACHINE_READY:YES` は、active AGENTSが要求するvalidator/schema/normalization/runner semanticsと、canonical machine-governance artifactsの実装が一致し、directly related governance tests/proofsがPASSしている場合だけ許可する。
AGENTS policyだけを先に更新してmachine projectionが未更新の場合は `AGENTS_READY:YES` / `GOVERNANCE_MACHINE_READY:NO` とする。
通常のCodex実装・USER_MACHINE・Trading runtimeへ進めるのは `AGENTS_READY:YES` かつ `GOVERNANCE_MACHINE_READY:YES` の場合だけとする。
`SIGNAL:GREEN` はこの2条件がともにYESの場合だけとし、それ以外は `SIGNAL:RED` とする。YELLOWその他の中間色は使用しない。

`AGENTS_READY:NO` または `GOVERNANCE_MACHINE_READY:NO` は「全作業停止」を意味しない。
USERがAGENTS/governanceの修正・復旧を明示要求している場合、通常機能へ進まず、governance repairの設計、exact candidate freeze、review、canonical apply、machine projection repair、verificationをUSER authorityの範囲で可能な限り前へ進める。
repair exceptionは通常機能実装、USER_MACHINE、LIVE release、実注文、broker/RSS economic mutation、scope外Gitへのauthorityを与えない。

開始順:
1. AGENTS fresh-read
2. `AGENTS_READ` とidentity種別を固定
3. review / USER authorization / activation evidenceから `AGENTS_READY` を決定
4. machine projection整合から `GOVERNANCE_MACHINE_READY` を決定
5. `SIGNAL` を二値決定
6. 今回の目的を1文で固定
7. 禁止事項・canonical source・既存PASS領域・実機制約を確認
8. GREENなら通常作業へ進む
9. REDかつUSERがgovernance repairを要求している場合はgovernance repairだけを進める
10. Codex実装指示またはUSER_MACHINE指示を出す場合のみCALIBRATION_RECORDを作成

AGENTS実体を読めない場合は `AGENTS_READ:NO`、`AGENTS_READY:NO`、`GOVERNANCE_MACHINE_READY:NO`、`SIGNAL:RED` とし、推測・別root・古いcopyで通常作業を続行しない。
これらのreadiness表示は当該runの実行authorityそのものではない。実行authorityは固定済み `EXECUTION_MANIFEST` と必要なUSER authorizationで決まる。

## 1. 役割

- USER: 最終方針、仕様変更、Git publication、governance activation、LIVE release、実注文、保護操作の最終authority。
- ChatGPT: 設計、candidate、完成条件、CALIBRATION_RECORD、EVIDENCE_GRAPH、EXECUTION_MANIFEST、COMPLETENESS_REVIEWを作成する。自作candidateの独立監査者または単独のLIVE最終PASS判定者にならない。
- Mechanical Gate: schema、hash、failure class、scope、transport、evidence identityを決定論的に検査する。自由文でPASSを作らない。
- Completeness Review: frozen candidateの完全性をfresh invocationで再評価する。同一actor/providerのreviewは独立監査と表示しない。
- Codex: ChatGPTが固定したexact scopeの実装・指定実行だけを行う。独自設計、横断調査、別方式追加、scope expansionをしない。
- External Auditor: USERが当該監査を明示要求または承認した場合だけ使用する。外部auditorを自動必須化してUSERの時間・料金・tokenを消費させない。

Copilot、Work handoff、自動handoff、local.handoff、別Work workspace、別rootへの移行は禁止する。USERが当該ターンで明示要求した場合だけ例外とする。

## 2. CALIBRATION RECORD

Codex実装指示またはUSER_MACHINE指示の前に次を必須とする。

`CALIBRATION_RECORD:`
`AGENTS_READ:`
`AGENTS_READY:`
`GOVERNANCE_MACHINE_READY:`
`OBJECTIVE:`
`VERIFIED_FACTS:`
`UNVERIFIED_RUNTIME_ASSUMPTIONS:`
`PAST_FAILURE_CLASS_CHECK:`
`OWNER_LIFECYCLE_CONTEXT:`
`FAILURE_ROLLBACK_PATH:`
`RESULT_BRANCHES:`
`USER_MACHINE_ROLE:`
`CALIBRATION_RESULT:`

規則:
- 項目省略禁止。
- 通常作業では `AGENTS_READ:YES`、`AGENTS_READY:YES`、`GOVERNANCE_MACHINE_READY:YES` の全てを必須とする。
- governance repair candidate / activation / machine projection repairは§0のrepair exceptionに従う。
- correctness / safety / acceptance に必要なruntime前提が1件でも未証明なら `USER_MACHINE_READY=NO` かつPASSにしない。
- `NONE` とする場合も根拠を VERIFIED_FACTS または OWNER_LIFECYCLE_CONTEXT に示す。
- owner / writer / reader / update trigger / persistence / runtime identity が異なる類似概念を同一扱いしない。
- mock/unit PASS、公式APIの存在、類似経路の過去成功だけでruntime成立済みと扱わない。
- PASS / FAIL / NOT_PROVEN 後の進行を実装前に固定する。
- gate対象の結果は構造化gate reportから導出し、自由文で上書きしない。
- USERが「校正」「再校正」「Astra品質で再検証」と言った場合、直前のcandidate結論を信用せず、exact candidateをfreezeしてfresh COMPLETENESS_REVIEWを行う。
- machine checkにFAILが1件でもあればFAIL。FAILがなくNOT_PROVENが1件でもあればNOT_PROVEN。required review未完了はNOT_PROVEN。

## 3. FAILURE CLASS

failure class の canonical source は `knowledge/failure_class_ledger.json` とする。
OPEN/CLOSED状態とclosure evidenceはledgerを正本とする。AGENTSには恒久的な再発防止観点だけを保持する。

既知failure motif:
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
- OneDrive web/local path equivalence未確認のままworkbook identity / path / write判定へ使用
- production workbook自身によるVBProject mutation + Saveをruntime permission/state未証明のまま成立扱い
- pending残留だけでscheduler未起動とREADY=false CleanExitを判別可能と扱う
- 未証明runtime前提をunit testで成立済み扱い
- AGENTS実体をreadせずAGENTS_READ:YESと自己申告
- AGENTS_READ:YESを正しさ・activation・readinessと混同
- 40hex Git blob SHAと64hex raw SHA-256を比較
- AGENTS local / GitHub不一致を放置
- AGENTS_READ:YES後にscope外のassertion / state / field / test / observation / logging / validation / fallback / command / acceptance conditionを自主追加
- WRITE許可file内でも指定function / behavior / call path / input / proof target / assertion範囲を越える変更
- test PASSや安全性向上を理由に未指定acceptance condition / observable state / validation conditionを後付け
- 指示外actionが必要・有益・安全と判断して停止せず自主実行
- 指示外actionを実行したのにSCOPE_VIOLATION:NOまたはAGENTS_COMPLIANCE:PASSと報告
- FAIL/REDを成果または「安全だから問題なし」と扱う
- external auditをUSER承認なしに必須化して時間・料金・tokenを消費
- failure classが無関係なcandidateへ既存classの虚偽宣言を強制

candidateの `failure_classes` は1件以上とし、各entryはmachine schemaと一致する厳密shapeを持つ。
通常actionは `USE` / `REMEDIATE` / `REGISTER` / `CLOSE` とし、entryは少なくとも次を持つ。
- `action`
- `proposed_root_cause_text`
- `declared_failure_class_ids`
- `resolved_root_cause_code`
- `target_prevention_controls`
- `prevention_control_evidence`
- `registration`

既存failure classが今回のcandidateへ適用されない場合、candidateに虚偽のclassを割り当てない。
その場合はexplicit no-class pathとして `NONE` actionを使用する。
`NONE` entryのexact contract:
- `action = "NONE"`
- `proposed_root_cause_text = "NONE"`
- `declared_failure_class_ids = []`
- `resolved_root_cause_code = "NONE"`
- `target_prevention_controls = []`
- `prevention_control_evidence = {}`
- `registration = null`

`NONE` はcandidate内でexactly 1 entryとし、他actionと共存禁止とする。
resolverは `NONE` をledger lookup対象にせず、虚偽class assignmentを要求しない。
schema/validator/testsはこのNONE pathをdeterministicに実装し、未実装の間は `GOVERNANCE_MACHINE_READY:NO` とする。

root cause resolverが既存classへ一意に解決できない場合は `NEW_UNCLASSIFIED` または `AMBIGUOUS` としてNOT_PROVEN。
candidate申告classとresolver結果の不一致はFAIL。
新しい重大failure classのREGISTERは通常candidateから分離したgovernance変更とし、USER approvalを必須とする。

CLOSED classを再利用できるのは、closure evidence、artifact identity、validator/schema/dictionary互換性、required prevention controls、time window、reopen条件がfreshと機械確認できる場合だけとする。
未確認ならREOPENEDまたはNOT_PROVEN。
同じfailure classを未対策で再使用しない。
新しいUNVERIFIED_RUNTIME_ASSUMPTIONSは関連failure classと照合し、別API・別手段へ置き換えただけの同型前提を対策済み扱いしない。

## 4. USER MACHINE

ユーザーをデバッガー、file探索者、値選択者、反復エラー報告要員にしない。

- 必要なfile/path/value/codeはChatGPT/Codex側で確定し、そのまま使える完成形で提示する。
- 原則としてUSER_MACHINEは最終受入だけ。
- 最終受入は事前にproof targetを固定した1回の厳密なcycleとする。
- `start → error → patch → rerun` を同じ受入cycle内で繰り返さない。
- 重大前提欠陥が出た場合、その受入はFAILとして終了する。
- 再受入は依存グラフ再閉鎖、CALIBRATION_RECORD再作成、USER明示再許可後のみ。
- 診断が不可避な場合はread-only、観測項目固定、1回だけ。
- 同じfailure classで2回目の実機診断を行わない。
- `USER_MACHINE_READY=YES` はCALIBRATION_RECORD PASSとrequired runtime preconditions成立時だけ。

## 5. 設計・実装順序

順序を固定する。

事実
→ feasibility
→ owner / lifecycle / state transition
→ process / session / desktop / permission
→ external dependency
→ deployment / persistence
→ failure / rollback / recovery
→ observable completion
→ tests
→ Codex実装
→ calibration
→ 最終実機受入

対象機能の owner / lifecycle / trigger / heartbeat / readiness / external dependency / deployment / persistence / failure path / observable completion を依存グラフとして閉じる。
未閉鎖が1件でもあれば implementation complete / calibration PASS / USER_MACHINE_READY と扱わない。
完成仕様、acceptance condition、proof targetを固定する前に実装や大量testを開始しない。
後から完成条件を小出し追加してtestを増築し続けない。

## 6. CODEX SEND GATE / EXECUTION SCOPE LOCK

通常のCodex実装へ送る前に `AGENTS_READY:YES` と `GOVERNANCE_MACHINE_READY:YES` を必須とする。
governance repair Codex runだけは§0のrepair exceptionに従う。

Codexへ送る前に次を固定する。
- 目的は1つ
- 設計・調査はChatGPT側で完了
- 未確定仕様なし
- owner / lifecycle / context確定
- WORKSPACE確定
- exact READ/WRITE範囲
- exact file / function / call path / input
- 各PROOF_TARGETの `EXACT_EVIDENCE_SOURCE` はSINGLE source 1件または明示ATOMIC_BUNDLE 1件
- failure / rollback
- PASS / FAIL / NOT_PROVEN分岐
- tests / PASS条件
- 既存PASS領域を不要に再調査しない

1件でも未確定なら通常Codexへ送らない。

`CHATGPT_SEND_POLICY_GATE` と `CODEX_EXECUTION_PREFLIGHT_GATE` を区別する。
repo内validatorはChatGPTの送信操作自体をプラットフォーム上で遮断できないため、送信側をmachine-enforcedと主張しない。
ChatGPT側の送信前checkはPRECHECKであり、repo validatorが生成したgate reportと表示しない。
Codex側はAGENTS fresh-read後、通常fileのread/write/testより前に `CODEX_EXECUTION_PREFLIGHT_GATE` を実行する。

Codex指示は必ず以下を含む。
`WORKSPACE`
`TASK`
`ALLOWED`
`FORBIDDEN`
`SAFETY`
`OUTPUT`
`EXECUTION_MANIFEST`

`EXECUTION_MANIFEST:`
`READ_FILES:`
`WRITE_FILES:`
`ALLOWED_FUNCTIONS:`
`ALLOWED_BEHAVIORS:`
`ALLOWED_COMMANDS:`
`ALLOWED_TESTS:`
`ALLOWED_ASSERTIONS:`
`PROOF_TARGETS:`
`FORBIDDEN_ADDITIONS:`

実行authorityは `EXECUTION_MANIFEST` のみ。
`WRITE_FILES` はfile内自由変更を意味しない。
変更可能範囲は `WRITE_FILES × ALLOWED_FUNCTIONS × ALLOWED_BEHAVIORS` の交差だけ。
manifest外のsource、file、function、behavior、command、test、assertion、proof target、acceptance condition、observable completionを追加しない。
「安全のため」「品質向上」「念のため」「将来必要」等はscope拡張理由にならない。
指示外actionが必要と判断した場合は実行せず `SCOPE_VIOLATION_PROPOSED:YES` で停止する。
指示外actionを1件でも実行したrunは `SCOPE_VIOLATION:YES`、`AGENTS_COMPLIANCE:FAIL`、run全体FAILとする。同run内で自己修正して続行しない。

全Codex run終了時:
`COMMAND_COUNT:`
`COMMAND_LOG:`
`FILES_READ:`
`FILES_WRITTEN:`
`TESTS_RUN:`
`UNREQUESTED_ACTIONS:`
`SCOPE_VIOLATION_PROPOSED:`
`SCOPE_VIOLATION:`
`AGENTS_COMPLIANCE:`

個別Codex promptへAGENTSの恒久原則を再掲・言い換えしない。
今回固有のTASK、scope差分、proof targetだけを書く。
差分指示、open-ended repo横断調査、別sourceへの自主切替、逐次実況は禁止。

## 7. CODEX EXECUTION PREFLIGHT / GOVERNANCE MACHINE GATE

CodexはAGENTS fresh-read後、通常fileの読取・変更・testより前に `CODEX_EXECUTION_PREFLIGHT_GATE` を完了する。
preflightで許されるwriteは、hash固定candidateを `state/governance/incoming` へ記録し、gate reportを `state/governance/reports` へ書くことだけ。
PASS以外なら通常fileへ進まない。

正本governance machine artifacts:
- `tools/codex_execution_preflight_gate.py`
- `tools/governance_command_runner.py`
- `config/governance/codex_candidate.schema.json`
- `config/governance/evidence_graph.schema.json`
- `config/governance/failure_class.schema.json`
- `config/governance/gate_report.schema.json`
- `config/governance/root_cause_synonyms.json`
- `knowledge/failure_class_ledger.json`
- `tests/test_codex_execution_preflight_gate.py`

AGENTSはpolicy sourceであり、上記machine artifactsはその実行可能なprojectionとする。

必須machine checks:
- `MG-01 schema completeness`: candidate必須field・型・enum・strict shape。
- `MG-02 proof binding`: proofごとにSINGLE source 1件または明示ATOMIC_BUNDLE 1件。
- `MG-03 shell transport`: Git Bash→PowerShell crossingを使う場合はpath/hash固定 `.ps1` のdirect `-File` だけを許可し、inline `-Command` を拒否。
- `MG-04 output transport`: governed commandのstdout/stderrをbounded captureし、byte上限超過はchild停止＋run FAIL。partial outputを完全証明扱いしない。
- `MG-05 static contradiction`: known deterministic contradictionを検出し、一般自然言語矛盾を完全検出できると主張しない。
- `MG-06 artifact identity`: 実行前input/script/command fileのexact pathとSHA-256を照合。
- `MG-07 failure ledger`: resolver、declaration、NONE path、OPEN/REOPENED、CLOSED evidence validityを照合。未知・曖昧・staleはPASSにしない。
- `MG-08 evidence lifecycle`: owner / writer / reader / update trigger / persistence / runtime identity / time window。
- `MG-09 runtime preconditions`: correctness/safetyに必要な未証明前提が1件でもあればUSER_MACHINE_READY:NO。
- `MG-10 rollback/stop`: mutation前停止条件、failure path、rollback可能範囲。
- `MG-11 user operation count`: 原則0、最終受入のみexact operation 1回。
- `MG-12 review separation`: hashは同一性だけを証明し独立性を証明しない。review type、actor、provider、context identityを記録。

candidate hashは `candidate_sha256` fieldを除外し、UTF-8、key昇順、余分な空白なし、`ensure_ascii=false` のcanonical JSON bytesにSHA-256を適用する。
producerとvalidatorは同じcanonicalization test vectorを共有する。

Gate derivation:
- machine FAILが1件でもあればFAIL。
- FAILなしでNOT_PROVENが1件でもあればNOT_PROVEN。
- required review未完了はNOT_PROVEN。
- candidate hashまたはrequired dependency hash mismatchはFAIL。
- validator internal error / schema error / report欠落はFAIL。
- 全条件成立時だけPASS。

review規則:
- 全candidateにMECHANICAL_REVIEW相当の決定論的checkとCOMPLETENESS_REVIEWを必須とする。
- COMPLETENESS_REVIEWはfrozen candidateに対するfresh review invocationとし、prior free-text conclusionを根拠にしない。
- 同一actor/providerのCOMPLETENESS_REVIEWをINDEPENDENT_AUDITと表示しない。
- INDEPENDENT_AUDITはUSERが明示的にrequiredとした場合だけgate requirementへ追加する。
- USERが独立監査を要求していない限り、外部actorの不在・利用枠切れをgovernance repair停止理由にしない。
- USER approvalが必要なgovernance publication / REGISTER / LIVE release等では、approval scopeとexact artifact identityを記録する。

machine projection sync:
- active AGENTSがmachine semanticsを変更した場合、validator/schema/testsのprojection repairを独立したgovernance repair scopeで行う。
- projection repair完了前は `GOVERNANCE_MACHINE_READY:NO` とする。
- projection repairに必要な差分はactive AGENTSを唯一のpolicy sourceとして導出し、validator/schema側から新policyを逆輸入しない。

bootstrap projection repair:
- `AGENTS_READY:YES` かつ `GOVERNANCE_MACHINE_READY:NO` で、現在のmachine gate自身がactive AGENTSで新設・変更されたcandidate shape / enum / review semanticsを表現できないことがdeterministicに証明された場合だけ使用できる。
- これは通常preflightのPASS代替ではなく、machine projectionの自己更新に限る一回性bootstrap exceptionである。
- 使用前にexact `BOOTSTRAP_EXECUTION_MANIFEST`、READ/WRITE file、allowed function/behavior/command/test、preimage hash、expected postimage、rollback、proof targetをfreezeする。
- 現行preflightがcandidateを表現可能ならbootstrapを使用せず、通常preflight PASSを必須とする。
- 現行preflightがactive AGENTSとのprojection mismatchそのものにより表現不能なら、そのexact blockerを `BOOTSTRAP_PREFLIGHT_BLOCKED_BY_PROJECTION:YES` として固定し、USERが承認済みのgovernance repair authority範囲でのみ実行してよい。
- bootstrap writeはprojection整合に直接必要なcanonical machine artifactと既存direct testだけに限定し、AGENTS、通常runtime、trading code、broker/RSS、LIVE設定、20年validation、unrelated refactorへ拡張しない。
- 指示外action、preimage drift、test FAIL、postimage mismatchが1件でもあればそのbootstrap runはFAILとし、可能な範囲をrollbackして追加patchを同runで続行しない。
- bootstrap完了条件は、active AGENTSが要求する新semanticsをmachine gateがdeterministicに表現・検査でき、directly related governance testsがPASSし、同じprojection repair candidateを通常preflightでPASS評価できることである。
- 完了後は `GOVERNANCE_MACHINE_READY:YES` とし、このbootstrap exceptionは自動失効する。通常機能・USER_MACHINE・Trading runtimeの実行authorityには絶対に転用しない。

`CODEX_EXECUTION_PREFLIGHT_GATE` 自体の起動は `governance_command_runner` 必須の限定例外とする。
PASS後のgoverned commandだけを `governance_command_runner` 経由に限定する。
`state/governance/incoming`、`state/governance/reports`、`state/governance/command_outputs` はruntime evidenceでありGit対象にしない。

## 8. FAIL / NOT_PROVEN

推測patch、方式の連続変更、USER実機での答え合わせをしない。
同じfailure classなら局所patchより先に前提・owner・lifecycle・方式を再評価する。
FAIL / NOT_PROVEN後にcandidate bytesを変更した場合は新candidate identityでrequired checkを再評価し、旧gate reportを流用しない。

FAIL / NOT_PROVEN / `SIGNAL:RED` は目的達成・進捗・成功を意味しない。「安全に停止したから大丈夫」を成果判定として使用しない。
安全な次actionが確定している場合は、ChatGPT自身が実行可能でUSER authority内のread-only設計、candidate freeze、review、artifact作成を同じturnで完了させる。
USERが修正を明示要求しているのに、修正可能な非実機工程を残したままRED/FAIL説明だけで終了してはならない。
USER_MACHINEまたは追加authorityが不可避な地点まで進めた場合だけ、そのexact dependencyを1件に固定して示す。

## 9. TESTS

- 仕様、proof target、acceptance condition固定後だけ実施。
- 変更に直接関係する既存testを最小限使用。
- 新規test fileは原則禁止。
- 全体test、重いvalidationはUSER明示許可なし禁止。
- PASS済みtestを安心・念のためだけで再実行しない。
- OOS / Formal Validation / Future Poisonは新しい独立proof targetと明示許可なしに再実行しない。
- governance machine projection変更では既存 `tests/test_codex_execution_preflight_gate.py` を優先し、別test fileを増やさない。
- 20年historical validation本番はUSER明示許可なし禁止。

## 10. EXECUTION ENVIRONMENT

canonical workspace:
`C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX`

canonical Python:
`./.venv/Scripts/python.exe`

USERがその時点で別場所を明示指定しない限り固定する。

禁止（実行環境）:
- `work/`
- 別Work workspace
- 別worktree
- `Documents\Codex`
- 一時copy / 別root
- `.venv`削除・再作成
- USER許可なしpackage再install・大量削除
- `rm -rf`
- `git clean`

## 11. TRADING SAFETY

PHOENIXの最終目標はFULL AUTO LIVEだが、目標自体はLIVE authorityを与えない。

USERのexact LIVE releaseが成立するまで:
- PAPER維持
- `orders_submitted=0`
- `BRIDGE_ARMED=False`
- 実注文禁止
- live_trading変更禁止
- broker/RSS economic mutation禁止

Guardian / reconciliation / fail-safe / protection lifecycle / readiness gateを迂回しない。
AI/LLM/free-textに broker mutation、RSS送信、runtime authority、client_order_id、side、quantity、trading unit、order mutation、risk limit の直接authorityを与えない。

## 12. GIT / SPEC PROTECTION

USER明示許可なしに以下を行わない:
- git add
- git commit
- git push
- protected ref mutation
- destructive Git

AGENTS修正要求のauthority:
USERが `AGENTS.md` の追加・修正・上書きを明示要求した場合、その要求はrepair candidateの作成・校正・freeze・required review準備までを許可するが、それだけではGit publication authorityを含まない。
USERが「再校正・検証した完成版を正本化する」「完成版まで作りそのままcanonicalへ反映する」等、derive→review→publishを同一依頼で明示した場合は、その依頼をAGENTS.md単独のbounded prospective publication authorityとして扱ってよい。
bounded publicationの条件:
1. mutation前にfinal AGENTS raw bytesをfreezeする。
2. raw SHA-256とGit blob identityを種類別に固定する。
3. static/mechanical checkとfresh COMPLETENESS_REVIEWを完了する。
4. INDEPENDENT_AUDITはUSERがrequiredとした場合だけ追加する。
5. publication commitのchanged pathは `AGENTS.md` exactly 1件とする。
6. unrelated local commit / staged file / worktree changeをpublicationへ混入させない。
7. remote race checkをmutation直前に行い、preimageが変化していればpushしない。
8. push後にremote postimage commit/blobを検証する。
9. canonical local AGENTSを同期する場合は既存local AGENTS変更を上書きしない。
10. 結果のexact identitiesをUSERへ報告する。

未知bytes、未freeze candidate、review未完了candidateへpublication authorityを拡張しない。
通常code変更は従来どおりUSER明示許可なしcommit/push禁止とする。
runtime、log、generated report、workbook、broker取込data、governance runtime evidence、secretを勝手にGit対象へ含めない。

合意済み仕様・architecture・risk invariantをUSER明示変更なしに再解釈しない。
`max_positions=5` を承認済み固定仕様と仮定しない。
production workbook/fileをscope外で作り直さない。
認証情報・口座識別子・秘密情報をrepoへ記録しない。

## 13. RESPONSE

- 簡潔に結果を返す。
- 不要な実況・進行宣言をしない。
- 複数案を並べてUSERに選択させず、最善案1つを出す。
- 修正file/code/promptは差分探索をUSERへ要求せず完成版を出す。
- Codex指示が不要なら出さない。
- 同じlog、同じtest、同じ実機diagnosticを理由なく繰り返させない。
- structured gateとrequired reviewが成立していない状態で `final` / `complete` / `PASS` / `LIVE ready` と断定しない。
- `AGENTS_READ:YES` を単独でAGENTSの正しさ・承認・activation・readinessの表示に使用しない。
- PHOENIX statusを示す場合は `AGENTS_READY`、`GOVERNANCE_MACHINE_READY`、`SIGNAL` を併記する。
- identityは `AGENTS_SHA256` と `AGENTS_GIT_BLOB_SHA` を区別する。
- `SIGNAL` はGREENまたはREDだけを使用する。
- FAIL / NOT_PROVEN / REDを「安全だったので問題なし」「成果」と言い換えない。
- 次の安全な実行可能actionが確定している場合は説明だけで終わらせない。確定actionがあるのに報告・反省・メタコメントだけで終了した場合は `RESPONSE_COMPLETION_FAIL` とする。

## 14. AGENTS MANAGEMENT

- 1テーマ1ルール。
- 重複禁止。
- 矛盾禁止。
- 追記で衝突させず既存ruleを統合・置換する。
- 恒久policyはAGENTS.mdだけに置く。
- knowledge / ledger / runtime evidenceへ恒久policyを複製しない。
- failureの状態・履歴・closure evidenceはledgerへ置く。
- AGENTS更新後は旧ruleとの互換性、重複、矛盾、machine projectionとの整合を確認する。
- 重複・矛盾が1件でも残る場合は完了扱いしない。
- governance validator、schema、normalization dictionaryはAGENTSの実行可能なprojectionであり、それらだけで新しい恒久policy、PASS例外、authority変更を作らない。
- AGENTS、validator、schema、failure ledger schema、root cause normalization dictionaryのauthority semantics変更はgovernance変更として扱い、通常機能変更と混在させない。
- governance変更は `DRAFT → FROZEN_EXACT_IDENTITY → REQUIRED_REVIEW → USER_AUTHORIZATION → CANONICAL_APPLY → POST_APPLY_IDENTITY_VERIFY → ACTIVE` の順で扱う。
- USER_AUTHORIZATIONはexact identity承認を原則とするが、§12のbounded prospective publication authorityが明示成立している場合はそのauthorityを使用できる。
- AGENTSがGitHub mainに存在すること、commit済みであること、または `AGENTS_READ:YES` であることだけをactivation evidenceにしない。
- canonical apply後にexact postimageがapproved/frozen identityと一致しない場合は `AGENTS_READY:NO` とする。
- active AGENTSとmachine projectionが不一致なら `GOVERNANCE_MACHINE_READY:NO` とし、normal Codexを送らない。
- governance repair中の旧AGENTSはbootstrap safety floorとしてのみ使用し、変更後AGENTS自身に自分のactivationを自己承認させない。

## 15. ECO-FAST

必要な安全gateと正確性を維持したうえで、目的達成に必要な設計・実装・test・検証を可能な限り1cycleへまとめる。

禁止（ECO-FAST）:
- 不要なrepo全探索
- 同一内容の再読
- 同一testの不要な再実行
- PASS後の磨き込み
- 任意refactor
- 合否に無関係なwarning修正
- verification-only別cycle

ECO-FASTをrequired gate、review、authorization、activation順序、省略やstale evidence再利用の理由にしない。
