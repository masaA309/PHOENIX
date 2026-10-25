# Q UI 完成像・トレール・V表示の回収仕様

出典: [UI設計継続確認](https://chatgpt.com/c/6ab2b778-c380-83ee-b6a5-08cb6868c99e)、2026-10-01、10-03、10-05の会話。既存会話の回収要約であり、新規設計や本番実装の完了証明ではありません。

## 見た目と完成像

Qロゴ、FOUR GUARDIANS、LIVE / READ ONLY、金縁のカード、日本語中心の画面を維持する。10月1日の修正では HOME・おすすめ・保有・チャート・PROGRESS の既存構成を維持し、LONG/SHORT、CASH/MARGIN、トレールと利益保護、詳細、Current Stop、Morning Screeningを組み込む方針。

`design_reference/QUADRANT_Q_MOBILE_DEMO.html` の PORTFOLIO / SCREEN / HISTORY / ANALYTICS は、その後ユーザーが拒否した案。`quadrant_showcase.html` と生成元Pythonも検討履歴であり、最終承認UIと取り違えない。10月1日07:14の修正版index.htmlは別の添付物。

四神獣の最終段階は `design_assets/stage6.jpg`。上の赤い朱雀、左の青龍、右の白虎、下の紫の玄武に加えて、中央に金色の麒麟を配置した4+1。stage4は四神獣とQ、stage5は中央麒麟が暗い移行段階。旧READMEにあるFX/GOLD/US INDICES等の獣と市場の対応を現行authorityとして流用しない。

## 10月5日時点の画面ごとの役割

|画面|必要な情報|
|---|---|
|HOME|MARKET BRIEF、Morning Screening、重要な状態|
|SCREENING|朝と場中の候補、鮮度、出典|
|POSITIONS|LONG/SHORTとCASH/MARGINを分離、損益、R、HOLDING/TRAILING/EXIT_PENDING、独立したV利益保護バッジ|
|DETAIL / CHART|Entry、Current、Current Stop、保護状態、source authority|
|HISTORY|SIDE、ENTRY、EXIT、RESULT、EXIT REASON|
|SYSTEM|本線・RSS・artifact接続、鮮度、由来。注文操作のauthorityを持たない|

画面役割と10月1日の日本語ナビの関係は会話の時系列として保持し、回収作業で新たな統合デザインを確定しない。ユーザーは10月1日および10月5日にDEMOをやめ、本UIを作ると指定している。

## トレールとV利益保護

TRAILINGという状態と、Vが示す利益保護を混同しない。VはUI側の表示値であり、本線のruntime state、exit trigger、注文命令ではない。

Current Stopで決済された場合に、適用コストを差し引いても利益が残ることが確認できたときに金色のVを表示する。単に含み益がある、トレール中、StopがEntryの利益側へ移っただけでは確定しない。確認不能ならNOT_PROVENまたは非点灯。SHORTのeffective_stopがEntryを下回る場合にもコスト確認が必要。

Vの利益保護表示は実際の決済完了・実現利益と分ける。将来の約定価格やギャップを保証する表示に変えない。原会話の「利益確保」「PROFIT SECURED」「V-LOCK」を、今回の回収で新しい売買ロジックに変換しない。

DETAILは CURRENT PROTECTION（Current Stop、Distance、Trailing、Profit Lock）、POSITION（Execution、Entry、Current、Quantity）、TRADE（Entry日時、Holding Period、Strategy）を整理して見せる。

回収されたPositionView項目: side、execution、entry_price、current_price、quantity、pnl、pnl_pct、current_r、status、current_stop、pending_stop、pending_stop_effective_session、held_sessions、exit_reason、freshness、authority、v_lock_display。v_lock_displayはACTIVE / INACTIVE / NOT_PROVEN。QからPHOENIXへ書き戻さない。

## MARKET BRIEFと継続更新

10月3日の構想は記事全文の羅列ではなく、市場地合い、追い風・材料、リスク、テーマ、イベント、関連スクリーニング候補、出典を整理するもの。公開・更新日時と古い情報の表示を持つ。HOMEの「本日のおすすめ」の上付近に置き、タップで展開する。

本線 → 読取専用Q Data/API層（screening、positions/executions、ニュース収集、正規化・重複除去、Market Brief）→ iPhone / PC UI。スマホを閉じてもサーバー側の収集・保存・更新が継続する構想。ニュースで本線のscoreやsignalを変更しない。

## 現在状態との区別

ユーザーの現在の説明は「Q本線のファイルは通ってる」。過去会話のSHORT未接続等を現在の不具合と再判定しない。今回の作業は成果物の回収・移管であり、本線の再検証や再設計ではない。
