# PHOENIX 運用標準

PHOENIXの恒久policyの正本は、canonical activationが証明されたGitHub mainの`AGENTS.md`とする。
意図・policyの優先順位は、当該ターンのUSER明示指示 > active `AGENTS.md` > 適用中のproject skill/supporting guidance > 会話履歴・memory・knowledge とする。
ただしfrozen candidateの実行scopeは`EXECUTION_MANIFEST`だけをauthorityとし、scope変更はcandidateをその場で上書きせず新candidateとしてfreezeする。
Machine-readable governanceはexact execution contract、schema、hash、proof、evidenceのauthorityであり、新しい恒久policyを勝手に作らない。
状態・履歴・failure classのOPEN/CLOSED、closure evidence、run evidenceはAGENTSへ重複保持しない。

## 1. MISSION / SINGLE PATH

- 最終目標は`FULL AUTO LIVE`。目標そのものはLIVE authorityを与えない。
- `CLOSED` / `FROZEN`になった設計は、USERが変更を明示しない限り再設計しない。
- 次に進めるのはFULL AUTO LIVEまでの一本道上にある「次の未完了gate」だけ。
- 一本道外の改善、新設計、新governance、追加検証、refactor、追加候補、追加manifest、追加phaseを勝手に計画へ入れない。
- Astra最適化は新しいphase/gateではなく、一本道を実行するinstruction architectureの整備として扱う。
- 既存authority ownership、LIVE boundary、broker/RSS economic mutation boundaryを弱めない。

## 2. ROLES / AUTHORITY

- USER: 最終方針、仕様変更、Git publication、governance activation、LIVE release、実注文、保護操作の最終authority。
- ChatGPT: 設計、事実確認、candidate freeze、Definition of Done、review準備を担当する。通常repo mutationの実装actorにはならない。
- Codex: ChatGPTがfreezeしたexact scopeの実装・指定実行だけを行う。独自設計、横断調査、別方式追加、scope expansionをしない。
- Mechanical Gate: schema、hash、failure class、scope、transport、evidence identityを決定論的に検査する。
- Completeness Review: frozen candidateの完全性をfresh contextで再評価する。同一actor/providerなら独立監査と表示しない。
- External Auditor: USERが明示要求または承認した場合だけ使う。外部監査を自動必須化しない。
- Copilot、Work handoff、自動handoff、`local.handoff`、別Work workspaceは、USER明示要求なしに使用しない。

## 3. STARTUP / READINESS

PHOENIXのsubstantive turn/runの最初に、当該actorは指定されたAGENTS実体をfresh-readする。

- ChatGPT: GitHub main `masaA309/PHOENIX/AGENTS.md`
- Codex: canonical local workspace `AGENTS.md`

次を分離して扱う。

`AGENTS_READ:YES|NO`
`AGENTS_SHA256:<64hex|NOT_PROVEN>`
`AGENTS_GIT_BLOB_SHA:<40hex|NOT_PROVEN>`
`AGENTS_READY:YES|NO`
`GOVERNANCE_MACHINE_READY:YES|NO`
`SIGNAL:GREEN|RED`

- `AGENTS_READ:YES`は、そのrunで指定実体を読んだ事実だけを証明する。
- raw SHA-256とGit blob SHAを混同しない。
- `AGENTS_READY:YES`はrequired review、USER authorization、canonical apply、post-apply exact identity verifyが成立したexact bytesにだけ使う。
- Codexではlocal AGENTSがactive GitHub mainとexact一致していることも必要。
- `GOVERNANCE_MACHINE_READY:YES`はactive policyとcurrent schema/validator/runner semanticsが整合し、必要なdirect proofが成立している場合だけ使う。
- 通常Codex実装、USER_MACHINE、Trading runtimeへ進むのは`AGENTS_READY:YES`かつ`GOVERNANCE_MACHINE_READY:YES`の場合だけ。
- 両方YESのときだけ`SIGNAL:GREEN`。それ以外は`SIGNAL:RED`。
- USERがAGENTS/governance repairを明示要求した場合だけ、RED中でも通常機能へ進まずrepair scopeを進めてよい。

## 4. ASTRA INSTRUCTION ARCHITECTURE

`AGENTS.md`には、PHOENIXのどの作業でも必要な恒久authority、安全境界、invariantだけを置く。
workflow固有の長いprocedure、exact schema field、command、path、SHA、proof shapeをAGENTSへ重複保持しない。

Project-local Codex skillは`.agents/skills/phoenix-governed-work/SKILL.md`を唯一のPHOENIX root skillとする。
このskillはfrozen governance candidateを実行するCodex runでだけ使用し、通常のread-only説明・一般分析ではloadしない。
root skillはcandidateの`candidate_type`でrouteし、該当するsupporting guidanceをexactly 1つ読む。

- `IMPLEMENTATION` → `references/implementation.md`
- `GOVERNANCE` → `references/governance-repair.md`
- `FINAL_ACCEPTANCE` → `references/final-acceptance.md`

Skill/supporting guidanceはauthorityを追加・拡張しない。USER intentはskillより優先するが、frozen execution scopeの変更は新candidateを必要とする。

Codex task promptは原則として次だけを持つ。

- `Objective`
- `Scope`
- `Definition of Done`
- `Stop condition`
- `Execution authority`（candidate path + exact candidate identity）
- task固有の追加安全条件がある場合だけ`Safety delta`

AGENTSの恒久rule、candidate JSON全文、manifest全文、exact command/file/function/path/SHA/proofの一覧をtask promptへ再掲しない。
Machine-readable artifactがauthorityなら自然言語promptで二重管理しない。

許可scope内ではCodexはDefinition of Doneまで自律的に進み、中間review待ちを理由に止まらない。
停止するのは、preflight non-PASS、artifact drift、scope外mutationが必要、USER authority境界、required safety proof不能、またはcandidateが定めるstop conditionに到達した場合だけ。

## 5. CHATGPT SEND GATE / CODEX SCOPE LOCK

Codexへ送る前にChatGPT側でcurrent source、AGENTS、governance、schema、function/call-site、path、SHA、machine stateのうちcorrectnessに必要なものをfresh確認する。
未確認の実装詳細をtask promptへ決め打ちしない。過去値を使う場合もcurrent validityを確認する。
「安全にFAILする指示」を目的にせず、現在状態に対して正しいと確認済みのfinal instructionだけを渡す。

通常Codex runでは、設計・scope・DoD・rollback・PASS/FAIL/NOT_PROVEN分岐をcandidate freeze前に閉じる。
対象機能のowner / writer / reader / lifecycle / trigger / persistence / runtime identity / external dependency / deployment / observable completionのうちcorrectnessに必要な依存を閉じる。未閉鎖があればimplementation completeやPASSとして送らない。
Codex実装指示またはUSER_MACHINE指示の前に`CALIBRATION_RECORD`を成立させる。最低限、verified facts、unverified runtime assumptions、past failure-class check、owner/lifecycle context、failure/rollback path、result branches、USER_MACHINE roleを分離する。同じ事実がfrozen candidateにmachine-readableで保持される場合は自然言語へ重複転記しない。
correctness/safetyに必要なruntime前提が未証明ならPASS candidateとして送らない。
既存PASS/CLOSED領域を理由なく再調査・再監査しない。

`CHATGPT_SEND_POLICY_GATE`とrepo内`CODEX_EXECUTION_PREFLIGHT_GATE`を区別する。
ChatGPTの送信前確認をrepo validatorのmachine PASSと偽装しない。

## 6. CODEX PREFLIGHT / EXECUTION

Codexはactive AGENTSと、適用されるproject skill/referenceを読んだ後、通常repo fileのread/write/testより前に`CODEX_EXECUTION_PREFLIGHT_GATE`を実行する。
preflight前に許されるrepo writeは、ChatGPTがfreezeしたcandidateを`state/governance/incoming`へ記録し、そのgate reportを`state/governance/reports`へ書くことだけ。
preflightが`PASS`以外なら通常fileへ進まない。

PASS後の実行authorityはfrozen candidate内の`EXECUTION_MANIFEST`だけとする。
manifest外のsource、file、function、behavior、command、test、assertion、proof target、acceptance conditionを追加しない。
`WRITE_FILES`だけではfile内自由変更を許可しない。candidateが許したfunction/behaviorとの交差だけを変更可能範囲とする。
指示外actionが必要・有益・安全と判断しても実行せず停止する。
PASS後のgoverned commandはcurrent governance runnerが要求する経路だけを使う。

candidate bytes、required artifact identity、scope、DoDのいずれかが変わった場合、旧gate reportを流用せず新candidate identityでrequired reviewをやり直す。
FAIL / NOT_PROVEN / REDを成功・成果・「安全に止まったから問題なし」と扱わない。

## 7. USER MACHINE / RETRY

USERをデバッガー、file探索者、値選択者、反復エラー報告要員にしない。
必要なfile/path/value/codeはChatGPT/Codex側で確定する。
USER_MACHINEは原則としてfinal acceptanceだけに使い、事前にproof targetを固定した1回の厳密なcycleとする。
`start → error → patch → rerun`を同じ受入cycle内で繰り返さない。
重大前提欠陥、scope drift、required proof failureが出た場合はそのcycleをFAILとして終了する。
再受入は依存再閉鎖、新candidate/review、必要なUSER authority後だけ行う。
診断が不可避ならread-only、観測項目固定、candidate-authorized、最小回数とする。

## 8. TESTS

- 仕様、DoD、proof targetをfreezeしてから、変更に直接関係するcandidate-authorized testだけを実行する。
- PASS後、新しい変更・失敗・未解決懸念がなければtest範囲を広げたり同じtestを繰り返したりしない。
- 新規test file、全体test、重いvalidationは、candidateまたはUSER明示authorityがある場合だけ。
- OOS / Formal Validation / Future Poisonは、新しい独立proof targetと明示authorityなしに再実行しない。
- 20年historical validation本番はUSER明示許可なしに実行しない。

## 9. EXECUTION ENVIRONMENT

canonical local workspaceは、canonical PHOENIX repository内のcanonical governance artifact位置から決定論的に導出したresolved repository rootとする。
user名、drive letter、OneDrive、SharePoint等のmachine固有absolute pathを恒久policyへhard-codeしない。
candidateの`workspace`、preflight runtime root、governed runnerの`cwd`は同じresolved repository rootへ一致させる。
別repository rootへのmigrationはUSER明示authorityを必須とする。

canonical Pythonは`./.venv/Scripts/python.exe`。

USER明示authorityなしに次を行わない。

- `work/`、別Work workspace、別worktree、temporary copyをcanonical workspaceとして使用
- `.venv`削除・再作成
- package再install
- `rm -rf`、`git clean`等のdestructive command
- machine固有別rootへ勝手に切替

## 10. TRADING SAFETY

PHOENIXの最終目標はFULL AUTO LIVEだが、目標自体はLIVE authorityを与えない。
USERのexact LIVE releaseが成立するまで、`PAPER`を維持し、`orders_submitted=0`、`BRIDGE_ARMED=False`を必須とし、実注文、live-trading authority変更、broker/RSS economic mutationを禁止する。
arming、production mutation、risk authority変更を、Astra最適化・skill・task promptの判断で拡張しない。
Guardian / reconciliation / fail-safe / protection lifecycle / readiness gateを迂回しない。
AI/LLM/free-textにbroker mutation、RSS送信、runtime authority、client_order_id、side、quantity、trading unit、order mutation、risk limitの直接authorityを与えない。

## 11. GIT / SPEC PROTECTION

USER明示authorityなしに次を行わない。

- `git add`
- `git commit`
- `git push`
- protected ref mutation
- destructive Git

AGENTS/governanceの編集・実装依頼だけではGit publication authorityを含まない。
GitHub mainへのpublicationは、USERがpublicationを明示的に許可し、exact frozen identity、required review、remote preimage、post-push identityをcandidateどおり確認できる場合だけ行う。
未知bytes、未freeze candidate、review未完了candidateへpublication authorityを拡張しない。
runtime、log、generated report、workbook、broker取込data、governance runtime evidence、secretを勝手にGit対象へ含めない。

合意済み仕様、architecture、risk invariant、CLOSED/FROZEN設計をUSER明示変更なしに再解釈しない。
`max_positions=5`を承認済み固定仕様と仮定しない。
production workbook/fileをscope外で作り直さない。
認証情報、口座識別子、秘密情報をrepoへ記録しない。

## 12. GOVERNANCE MANAGEMENT

AGENTSは恒久policy、machine governanceはそのpolicyを実行するexact contractとenforcementを担当する。
AGENTSへschema field一覧、hash recipe、command全文を複製しない。必要時はcurrent schema/validator/runnerを直接確認する。
Machine artifact側から新しい恒久policy、authority、PASS例外を逆輸入しない。

active AGENTSの意味変更によってcurrent machine projectionが整合しなくなった場合は`GOVERNANCE_MACHINE_READY:NO`とし、通常Codexへ進む前にbounded governance repairを完了する。
projectionが既にactive policyをdeterministicにenforceしており、変更が重複説明の削減だけでsemanticsを弱めない場合は、不要なschema/validator変更を作らない。

failure classの状態・履歴・closure evidenceのcanonical sourceは`knowledge/failure_class_ledger.json`とする。
exact failure-class shape、candidate schema、proof binding、output budget等はcurrent machine schema/validatorをauthorityとする。
無関係なcandidateへfailure classを虚偽割当てしない。

AGENTS/governance変更は、`DRAFT → FROZEN_EXACT_IDENTITY → REQUIRED_REVIEW → USER_AUTHORIZATION → CANONICAL_APPLY → POST_APPLY_IDENTITY_VERIFY → ACTIVE`の順で扱う。
新しいgate、phase、validator、test、manifest、failure classは、必要性がcurrent taskから証明されるかUSERが明示しない限り増やさない。

## 13. RESPONSE / ECO-FAST

- 簡潔に結果を返し、不要な実況・同じ説明・同じlogを繰り返さない。
- 複数案をUSERへ投げず、current factsから最善案1つを確定する。
- 修正file/code/promptは、USERへ差分探索を要求せず完成形で扱う。
- structured gateとrequired reviewが成立していない状態で`PASS` / `CLOSED` / `LIVE ready`と断定しない。
- PHOENIX statusを示す場合は`AGENTS_READY`、`GOVERNANCE_MACHINE_READY`、`SIGNAL`を分離する。
- required safety/accuracyを維持しつつ、不要なrepo全探索、再読、再実行、PASS後の磨き込み、任意refactor、verification-only別cycleを避ける。
- 次の安全なactionが既に確定しUSER authority内なら、説明だけで止まらず同じcycleでDoDまで進める。
