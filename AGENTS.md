# PHOENIX 運用標準

この `AGENTS.md` を PHOENIX の恒久運用ルールの唯一の正本とする。
優先順位は、当該ターンのユーザー明示指示 > 現在の `AGENTS.md` > machine-governance state > 会話履歴・memory・knowledge とする。
状態・履歴・failure class の OPEN/CLOSED とclosure evidence、run evidenceはAGENTS.mdに重複保持しない。恒久的な再発防止観点はAGENTS.mdに保持してよい。

## 0. MANDATORY STARTUP GATE

PHOENIX に関する substantive turn の最初に必ず当該 actor が AGENTS.md 実体を fresh-read する。

- ChatGPT: GitHub main の `masaA309/PHOENIX/AGENTS.md`
- Codex: canonical local workspace の `AGENTS.md`

実際に読めた場合のみ `AGENTS_READ:YES` とする。
会話履歴、要約、memory、knowledge、過去 run の結果だけで `AGENTS_READ:YES` にしてはならない。
読めない場合は `AGENTS_GATE:FAIL` として停止し、推測・別root・古いcopyで続行しない。

開始順:
1. AGENTS.md fresh-read
2. 今回の目的を1文で固定
3. 禁止事項・canonical source・既存PASS領域・実機制約を確認
4. Codex実装指示またはUSER_MACHINE指示を出す場合のみ CALIBRATION_RECORD を作成
5. その後に設計・指示・実装・実機判断へ進む

`AGENTS_READ:YES` は実行許可ではない。実行許可は当該 run の `EXECUTION_MANIFEST` とユーザー承認で決まる。

## 1. 役割

- USER: 最終方針、仕様変更、Git公開、governance activation、LIVE release、実注文、保護操作の最終authority。
- ChatGPT: 設計、candidate、完成条件、CALIBRATION_RECORD、EVIDENCE_GRAPH、EXECUTION_MANIFESTを作成する。自作candidateの独立監査者または単独の最終PASS判定者にならない。
- Mechanical Gate: schema、hash、failure class、scope、transport、evidence identityを決定論的に検査する。自由文でPASSを作らない。
- Completeness Review: candidateの完全性を再評価する。同一モデル・同一provider・同一contextのreviewを独立監査と表示しない。
- Codex: ChatGPTが固定したexact scopeの実装・指定実行だけを行う。独自設計、横断調査、別方式追加、scope expansionをしない。
- Claude等の外部auditor: ユーザーがその監査を明示要求または承認した場合だけ使用する。

Copilot、Work handoff、自動handoff、local.handoff、別Work workspace、別rootへの移行は禁止する。ユーザーが当該ターンで明示要求した場合だけ例外とする。

## 2. CALIBRATION RECORD

Codex実装指示またはUSER_MACHINE指示の前に次を必須とする。

`CALIBRATION_RECORD:`
`AGENTS_READ:`
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
- `AGENTS_READ != YES` はFAIL。
- correctness / safety / acceptance に必要なruntime前提が1件でも未証明なら `USER_MACHINE_READY=NO` かつ PASSにしない。
- `NONE` とする場合も根拠を VERIFIED_FACTS または OWNER_LIFECYCLE_CONTEXT に示す。
- owner / writer / reader / update trigger / persistence / runtime identity が異なる類似概念を同一扱いしない。
- mock/unit PASS、公式APIの存在、類似経路の過去成功だけでruntime成立済みと扱わない。
- PASS / FAIL / NOT_PROVEN 後の進行を実装前に固定する。
- gate対象の結果は構造化gate reportから導出し、自由文で上書きしない。
- ユーザーが「校正」と言った場合、直前の自分の案を信用せずcandidateを凍結し、新しいreview invocationで再評価する。同一モデル・同一provider・同一contextの再評価はCOMPLETENESS_REVIEWとし、独立監査と表示しない。
- machine checkにFAILが1件でもあればFAIL。FAILがなくNOT_PROVENが1件でもあればNOT_PROVEN。required review未完了はNOT_PROVEN。

## 3. FAILURE CLASS

failure class の canonical source は `knowledge/failure_class_ledger.json` とする。
OPEN/CLOSED状態とclosure evidenceはledgerを正本とするが、次の既知failure motifは再発防止の恒久照合観点としてAGENTS.mdに保持する。

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
- ChatGPTから参照可能なGitHub main版を読まず、local AGENTSだけで自己停止
- AGENTS local / GitHub不一致を放置
- AGENTS_READ:YES後にscope外のassertion / state / field / test / observation / logging / validation / fallback / command / acceptance conditionを自主追加
- WRITE許可file内でも指定function / behavior / call path / input / proof target / assertion範囲を越える変更
- test PASSや安全性向上を理由に未指定acceptance condition / observable state / validation conditionを後付け
- AGENTS_READ:YESをrun全体への包括実行許可と誤認
- 指示外actionが必要・有益・安全と判断して停止せず自主実行
- 指示外actionを実行したのにSCOPE_VIOLATION:NOまたはAGENTS_COMPLIANCE:PASSと報告

candidateは次を持つ:
- `declared_failure_class_ids`
- `proposed_root_cause_text`
- `resolved_root_cause_code`

root cause resolverが既存classへ一意に解決できない場合は `NEW_UNCLASSIFIED` または `AMBIGUOUS` としてNOT_PROVEN。
candidate申告classとresolver結果の不一致はFAIL。
新しい重大failure classの登録は通常candidateから分離したgovernance変更とし、ユーザー承認を必須とする。

CLOSED classを再利用できるのは、関連するclosure evidence・artifact identity・validator/schema/dictionary互換性・required prevention controls・time window・reopen条件がfreshと機械確認できる場合だけとする。
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
- 再受入は依存グラフ再閉鎖、CALIBRATION_RECORD再作成、ユーザー明示再許可後のみ。
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

Codexへ送る前に次を固定する。

- 目的は1つ
- 設計・調査はChatGPT側で完了
- 未確定仕様なし
- owner / lifecycle / context確定
- WORKSPACE確定
- exact READ/WRITE範囲
- exact file / function / call path / input
- 各PROOF_TARGETの `EXACT_EVIDENCE_SOURCE` は SINGLE source 1件または明示ATOMIC_BUNDLE 1件
- failure / rollback
- PASS / FAIL / NOT_PROVEN分岐
- tests / PASS条件
- 既存PASS領域を不要に再調査しない

1件でも未確定ならCodexへ送らない。

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

正本governance artifacts:
- `AGENTS.md`
- `tools/codex_execution_preflight_gate.py`
- `tools/governance_command_runner.py`
- `config/governance/codex_candidate.schema.json`
- `config/governance/evidence_graph.schema.json`
- `config/governance/failure_class.schema.json`
- `config/governance/gate_report.schema.json`
- `config/governance/root_cause_synonyms.json`
- `knowledge/failure_class_ledger.json`
- `tests/test_codex_execution_preflight_gate.py`

必須machine checks:
- `MG-01 schema completeness`: candidate必須field・型・enum。
- `MG-02 proof binding`: proofごとにSINGLE source 1件または明示ATOMIC_BUNDLE 1件。
- `MG-03 shell transport`: Git Bash→PowerShell inline `-Command` を拒否し、path/hash固定 `.ps1` の `-File` だけを許可。
- `MG-04 output transport`: governed commandのstdout/stderrをbounded captureし、byte上限超過はchild停止＋run FAIL。partial outputを完全証明扱いしない。
- `MG-05 static contradiction`: `complete要求とtruncate`、相反state必須値、同一predicateのPASS/FAIL併存、evidence欠落、manifest外action必須、transport上限超過の既知矛盾をdeterministic検出する。一般自然言語矛盾を完全検出できると主張せず、対象外はNOT_PROVENとする。
- `MG-06 artifact identity`: 実行前input/script/command fileのexact pathとSHA-256を照合。
- `MG-07 failure ledger`: resolver、declared class、OPEN/REOPENED、CLOSED evidence validityを照合。未知・曖昧・staleはPASSにしない。
- `MG-08 evidence lifecycle`: owner / writer / reader / update trigger / persistence / runtime identity / time window。
- `MG-09 runtime preconditions`: correctness/safetyに必要な未証明前提が1件でもあればUSER_MACHINE_READY:NO。
- `MG-10 rollback/stop`: mutation前停止条件、failure path、rollback可能範囲。
- `MG-11 user operation count`: 原則0、最終受入のみexact operation 1回。
- `MG-12 review separation`: hashは同一性だけを証明し独立性を証明しない。review typeとactor invocation IDを記録。

candidate hashは `candidate_sha256` fieldを除外し、UTF-8、key昇順、余分な空白なし、`ensure_ascii=false` のcanonical JSON bytesにSHA-256を適用する。
producerとvalidatorは同じcanonicalization test vectorを共有する。

Gate derivation:
- machine FAILが1件でもあればFAIL。
- FAILなしでNOT_PROVENが1件でもあればNOT_PROVEN。
- required review未完了はNOT_PROVEN。
- candidate hashまたはrequired dependency hash mismatchはFAIL。
- 全条件成立時だけPASS。
- validator internal error / schema error / report欠落はFAIL。

全candidateにMECHANICAL_REVIEWとCOMPLETENESS_REVIEWを必須とする。
ユーザーが外部監査を明示した場合、governance原則・validator・schema・normalization dictionary変更、新重大failure class登録にはINDEPENDENT_AUDITも必須とする。
review independenceの定義は§1に従う。
外部actorが利用不能で、ユーザーが独立性欠如を理解して代行reviewを明示承認したgovernance変更だけは `SUBSTITUTE_COMPLETENESS_REVIEW` として設計・実装へ進めてよい。ただし通常runtime、USER_MACHINE、Trading Safety、LIVE、実注文のPASS根拠にはしない。

`CODEX_EXECUTION_PREFLIGHT_GATE` 自体の起動は `governance_command_runner` 必須の限定例外とする。preflight出力は固定schema・固定byte上限とし、PASS後のcommandだけを `governance_command_runner` 経由に限定する。
`state/governance/incoming` と `state/governance/reports` はruntime evidenceでありGit対象にしない。

## 8. FAIL / NOT_PROVEN

推測patch、方式の連続変更、ユーザー実機での答え合わせをしない。
同じfailure classなら局所patchより先に前提・owner・lifecycle・方式を再評価する。

FAIL / NOT_PROVEN後にcandidate bytesを変更した場合は新candidate identityでrequired checkを再評価し、旧gate reportを流用しない。

安全な次actionが確定している場合は同じ返答で提示する。
未確定または安全停止が必要な場合はその理由を明示し、USER_MACHINEを使わない次の安全工程を示す。

## 9. TESTS

- 仕様、proof target、acceptance condition固定後だけ実施。
- 変更に直接関係する既存testを最小限使用。
- 新規test fileは原則禁止。
- 全体test、重いvalidationはユーザー明示許可なし禁止。
- PASS済みtestを安心・念のためだけで再実行しない。
- OOS / Formal Validation / Future Poisonは新しい独立proof targetと明示許可なしに再実行しない。
- governance validatorの新規test fileはユーザー承認済みgovernance専用runだけの例外とし、通常runtime / Excel / broker / Trading / heavy validationと混在させない。

## 10. EXECUTION ENVIRONMENT

canonical workspace:
`C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX`

canonical Python:
`./.venv/Scripts/python.exe`

ユーザーがその時点で別場所を明示指定しない限り固定する。

禁止:
- `work/`
- 別Work workspace
- 別worktree
- `Documents\Codex`
- 一時copy / 別root
- `.venv`削除・再作成
- ユーザー許可なしpackage再install・大量削除
- `rm -rf`
- `git clean`

## 11. TRADING SAFETY

PHOENIXの最終目標はFULL AUTO LIVEだが、目標自体はLIVE authorityを与えない。

ユーザーのexact LIVE releaseが成立するまで:
- PAPER維持
- `orders_submitted=0`
- `BRIDGE_ARMED=False`
- 実注文禁止
- live_trading変更禁止
- broker/RSS economic mutation禁止

Guardian / reconciliation / fail-safe / protection lifecycle / readiness gateを迂回しない。
AI/LLM/free-textに broker mutation、RSS送信、runtime authority、client_order_id、side、quantity、trading unit、order mutation、risk limit の直接authorityを与えない。

## 12. GIT / SPEC PROTECTION

ユーザー明示許可なしに以下を行わない:
- git add
- git commit
- git push
- protected ref mutation
- destructive Git

例外:
ユーザーが `AGENTS.md` ルールの追加・修正・上書きを明示要求した場合、その要求は `AGENTS.md` 単独の git add / git commit / git push を許可したものとして扱う。
ただし、ユーザーが commitしない / pushしない と明示した場合は除く。
この例外で `AGENTS.md` 以外のfileを同じcommitへ含めない。
通常code変更は従来どおり明示許可なしcommit/push禁止とする。

runtime、log、generated report、workbook、broker取込data、governance runtime evidence、secretを勝手にGit対象へ含めない。

合意済み仕様・architecture・risk invariantをユーザー明示変更なしに再解釈しない。
`max_positions=5` を承認済み固定仕様と仮定しない。
production workbook/fileをscope外で作り直さない。
認証情報・口座識別子・秘密情報をrepoへ記録しない。

## 13. RESPONSE

- 簡潔に結果を返す。
- 不要な実況・進行宣言をしない。
- 複数案を並べてユーザーに選択させず、最善案1つを出す。
- 修正file/code/promptは差分探索をユーザーへ要求せず完成版を出す。
- Codex指示が不要なら出さない。
- 同じlog、同じtest、同じ実機diagnosticを理由なく繰り返させない。
- structured gateとrequired reviewが成立していない状態で `final` / `complete` / `PASS` / `LIVE ready` と断定しない。
- 次の安全な実行可能actionが確定している場合は説明だけで終わらせない。確定actionがあるのに報告・反省・メタコメントだけで終了した場合は `RESPONSE_COMPLETION_FAIL` とする。

## 14. AGENTS MANAGEMENT

- 1テーマ1ルール。
- 重複禁止。
- 矛盾禁止。
- 追記で衝突させず既存ruleを統合・置換する。
- 恒久policyはAGENTS.mdだけに置く。
- knowledge / ledger / runtime evidenceへ恒久policyを複製しない。
- failureの状態・履歴・closure evidenceはledgerへ置く。
- AGENTS更新後は旧ruleとの互換性、重複、矛盾、machine gateとの整合を確認する。
- 重複・矛盾が1件でも残る場合は完了扱いしない。
- governance validator、schema、normalization dictionaryはAGENTSの実行可能な投影であり、それらだけで新しい恒久policy、PASS例外、authority変更を作らない。
- AGENTS、governance validator、schema、failure ledger schema、root cause normalization dictionaryのauthority semantics変更はgovernance変更として扱い、通常機能変更と混在させない。
- governance変更は変更artifactを固定してrequired reviewを行い、ユーザー承認前にcanonical activationしない。

## 15. ECO-FAST

必要な安全gateと正確性を維持したうえで、目的達成に必要な設計・実装・test・検証を可能な限り1cycleへまとめる。

禁止:
- 不要なrepo全探索
- 同一内容の再読
- 同一testの不要な再実行
- PASS後の磨き込み
- 任意refactor
- 合否に無関係なwarning修正
- verification-only別cycle

ECO-FASTをrequired gate、review、authorization、activation順序、省略やstale evidence再利用の理由にしない。
