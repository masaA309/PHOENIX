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


## 追加回収資料

[画像・UI一覧](VISUAL_DESIGN_INDEX.md) / [回収した詳細仕様](RECOVERED_UI_SPEC.md)

四神獣＋金色麒麟はdesign_assets/stage6.jpg。修正版UI添付の表示HTMLとV-LOCKチャートSVGをdesign_referenceへ追加。表示HTMLはブラウザーDOMの保存であり元添付とのbyte一致は未証明。独立Vロゴの原画像は未回収。旧DEMO案と修正版を一覧で区別。

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
- Market BriefとMorning Screeningは別の表示要素として扱う計画。追加回収した画面構成・Market Brief・V表示の詳細は `RECOVERED_UI_SPEC.md` を参照。
- 正式な本線read surfaceからQ adapter → API → UIへ接続し、staging/test stateを本番と推測しない。

## 実装と計画の差を読む注意点

`Position`型にはside、execution、status、current_stop、current_r、v_lock_displayが存在しますが、型があることは全項目の正式runtime接続・画面完成を証明しません。取得時のUIにはSHORT RUNTIME NOT_CONNECTEDの表示経路があります。Q本線についてユーザーは通過済みと述べており、本移管では本線を再判定していません。

過去会話のPositionView計画にはpending_stop等もあります。最新ソースとの差は将来の実装確認事項であり、本移管で追加実装していません。

今後Claudeへ依頼する実装範囲はユーザーが指定してください。この資料自体は新たな実装・発注・LIVE releaseを許可しません。

````

## design_reference/corrected_index_rendered.html

````text
<!doctype html>
<html lang="ja-JP" class="transparentSkybridgeBackground desktopSkybridge light" data-theme="light" style="color-scheme: light; --safe-area-inset-top: 0px; --safe-area-inset-bottom: 0px; --safe-area-inset-left: 0px; --safe-area-inset-right: 0px;"><head><style>@layer sandbox-defaults{html,body,#root{margin:0;padding:0}}</style><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#071019"><title>QUADRANT DEMO-Q</title><style>
:root{--bg:#071019;--card:#111c28;--line:#2b3b4e;--gold:#e8ba50;--txt:#f4f2ec;--mut:#8d9aaa;--green:#67cf92;--red:#ff7275;--blue:#49a7ff}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}body{margin:0;background:var(--bg);color:var(--txt);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-weight:700}button{font:inherit;color:inherit}
.app{max-width:620px;margin:auto;min-height:100vh;padding:env(safe-area-inset-top) 18px calc(105px + env(safe-area-inset-bottom))}
header{height:105px;display:flex;align-items:center;border-bottom:1px solid #233141;margin:0 -18px;padding:0 18px;gap:12px}.logo{width:53px;height:53px;border:2px solid var(--gold);border-radius:10px;display:grid;place-items:center;font-size:29px;color:var(--gold);background:radial-gradient(circle,#5a2634,#111926 65%);box-shadow:inset 0 0 0 3px #172334}.brand{font-size:22px;letter-spacing:.06em}.sub{font-size:11px;color:var(--gold);letter-spacing:.2em;margin-top:3px}.sync{margin-left:auto;text-align:right;font-size:11px}.live{color:var(--green);margin-right:10px}.ro{color:var(--gold)}.time{display:block;color:#8290a0;font-size:9px;margin-top:4px}
.page{display:none;padding-top:24px}.page.on{display:block}h1{font-size:30px;margin:0 0 2px}.eyebrow{color:var(--gold);font-size:12px;letter-spacing:.11em;margin-bottom:17px}.cards4{display:grid;grid-template-columns:1fr 1fr;gap:12px}.metric{background:var(--card);border:1px solid var(--line);border-radius:19px;padding:18px 16px;min-height:112px}.metric span{color:var(--mut);font-size:11px}.metric b{display:block;font-size:25px;margin-top:10px}.green{color:var(--green)!important}.red{color:var(--red)!important}.gold{color:var(--gold)!important}
.box{margin-top:17px;background:var(--card);border:1px solid var(--line);border-radius:19px;padding:16px}.boxtitle{color:var(--gold);font-size:16px;margin-bottom:10px}.rec,.holding{width:100%;border:0;border-top:1px solid #233141;background:none;text-align:left;padding:14px 0;display:grid;align-items:center;gap:8px}.rec:first-of-type,.holding:first-of-type{border-top:0}.rec{grid-template-columns:24px 1fr auto}.rank{color:var(--gold);font-size:19px}.rec small,.holding small{display:block;color:var(--mut);font-size:9px;margin-top:4px}.side{display:inline-block;border:1px solid;border-radius:6px;padding:3px 7px;font-size:9px;margin-right:6px}.LONG{color:var(--blue)}.SHORT{color:var(--red)}.score{text-align:right;font-size:17px}.holding{grid-template-columns:68px 1fr auto}.code{font-size:14px}.name{font-size:14px}.exec{color:var(--gold)!important}.right{text-align:right}.right b{display:block;font-size:14px}.pnl{font-size:14px!important}.status{font-size:9px;border:1px solid #536274;border-radius:5px;padding:3px 6px;display:inline-block;margin-top:5px}.v{color:var(--gold);border-color:#9e7929}.actions{display:flex;gap:7px;justify-content:flex-end;margin-top:7px}.actions span{border:1px solid #8c6a26;border-radius:7px;padding:6px 8px;font-size:9px}
.chartbox{height:420px;border:1px solid #8c6a26;border-radius:18px;margin-top:16px;position:relative;overflow:hidden;background:linear-gradient(#0b151f,#071019)}.chartbox svg{width:100%;height:100%}.legend{position:absolute;top:14px;right:14px;border:1px solid var(--line);border-radius:10px;padding:9px;background:#0d1722dd;font-size:9px;color:#9eabb9}.notice{border:1px solid var(--line);border-radius:14px;padding:13px;color:var(--mut);font-size:11px;margin-top:14px}
.progress{border:1px solid #9d792b;border-radius:18px;text-align:center;color:var(--gold);font-size:21px;padding:22px;margin:18px 0}.guardian{opacity:.38;display:grid;grid-template-columns:55px 1fr auto;gap:12px;align-items:center;border:1px solid var(--line);border-radius:18px;padding:15px;margin-bottom:12px}.guardian.active{opacity:1}.gicon{width:50px;height:50px;border:2px solid #7d642d;border-radius:8px;display:grid;place-items:center;font-size:28px}.guardian b{font-size:17px}.guardian small{display:block;color:var(--mut);margin-top:5px}.lock{text-align:right;color:var(--gold);font-size:12px}
nav{position:fixed;bottom:0;left:0;right:0;max-width:620px;margin:auto;background:#071019f5;border-top:1px solid #273646;padding:8px 5px calc(8px + env(safe-area-inset-bottom));display:grid;grid-template-columns:repeat(5,1fr);z-index:20}nav button{background:none;border:1px solid transparent;border-radius:14px;height:62px;color:#a2acb8;font-size:10px}nav button.on{border-color:#9c7628;color:#fff}nav b{display:block;font-size:17px;margin-bottom:4px}
.sheet{display:none;position:fixed;inset:0;background:#071019fa;z-index:40;overflow:auto;padding:calc(18px + env(safe-area-inset-top)) 18px 30px}.sheet.on{display:block}.sheetin{max-width:620px;margin:auto}.sheethead{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:15px}.close{border:1px solid #8c6a26;background:none;border-radius:50%;width:43px;height:43px}.big{font-size:29px;margin:22px 0 4px}.sect{border-top:1px solid var(--line);margin-top:20px;padding-top:16px}.sect h3{color:var(--gold);font-size:11px;letter-spacing:.12em}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:12px}.grid span{color:var(--mut)}
</style><style>html, body, #root {
      margin-top: 0; margin-bottom: 0; padding-top: 0; padding-bottom: 0;
      
    }
html,body,#root{-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}html,body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Oxygen,Ubuntu,Cantarell,Helvetica Neue,Arial,sans-serif!important}button,input,textarea,select{font-family:inherit}html{background-color:transparent}html.chatgptOled.dark,html.mobileSkybridge.dark{background-color:#000}@supports (font: -apple-system-body){html.mobileSkybridge{font:-apple-system-body}}html.desktopSkybridge.dark{background-color:#1e1e1e}html.transparentSkybridgeBackground,html.transparentSkybridgeBackground.dark{background-color:transparent}html.androidSkybridge,html.androidSkybridge body,html.androidSkybridge *{-webkit-tap-highlight-color:rgba(255,255,255,0)}html.androidSkybridge *::selection,html.androidSkybridge *::-moz-selection{background:#fff0;color:inherit}</style></head><body><div class="app"><header><div class="logo">Q</div><div><div class="brand">QUADRANT</div><div class="sub">FOUR GUARDIANS</div></div><div class="sync"><span class="live">DEMO</span><span class="ro">READ ONLY</span><span class="time">SAMPLE DATA</span></div></header>
<section id="home" class="page on"><div class="notice">DEMO / SAMPLE DATA　実運用・注文機能なし</div><div class="cards4"><div class="metric"><span>推定資産</span><b>¥1,217,185</b></div><div class="metric"><span>本日の損益</span><b class="red">−¥1,060<br><small>(−0.63%)</small></b></div><div class="metric"><span>評価損益</span><b class="green">+¥6,251</b></div><div class="metric"><span>買付可能額</span><b>¥1,050,008</b></div></div><div class="box"><div class="boxtitle">本日のおすすめ上位</div><button class="rec" data-code="7203.T"><b class="rank">1</b><span><b>7203.T　トヨタ自動車</b><small><span class="side LONG">LONG</span> SIGNAL BREAKOUT</small></span><span class="score">92<small>SCORE</small></span></button><button class="rec" data-code="6758.T"><b class="rank">2</b><span><b>6758.T　ソニーグループ</b><small><span class="side SHORT">SHORT</span> SIGNAL MOMENTUM</small></span><span class="score">89<small>SCORE</small></span></button><button class="rec" data-code="8035.T"><b class="rank">3</b><span><b>8035.T　東京エレクトロン</b><small><span class="side SHORT">SHORT</span> SIGNAL TREND</small></span><span class="score">86<small>SCORE</small></span></button></div><div class="box"><div class="boxtitle">保有銘柄</div><button class="holding" data-i="0"><div><b class="code">7203.T</b><small><span class="side LONG">LONG</span></small></div><div><b class="name">トヨタ自動車</b><small class="exec">MARGIN / 100株</small></div><div class="right"><b>¥3,142</b><b class="pnl green">+¥18,420 (+5.86%)</b><span class="status v">V-LOCK</span><div class="actions"><span>詳細</span><span>チャート</span></div></div></button></div></section>
<section id="recommend" class="page"><h1>おすすめ</h1><div class="eyebrow">MORNING SCREENING / SAMPLE</div><div class="box"><button class="rec" data-code="7203.T"><b class="rank">1</b><span><b>7203.T　トヨタ自動車</b><small><span class="side LONG">LONG</span> SIGNAL BREAKOUT</small></span><span class="score">92<small>SCORE</small></span></button><button class="rec" data-code="6758.T"><b class="rank">2</b><span><b>6758.T　ソニーグループ</b><small><span class="side SHORT">SHORT</span> SIGNAL MOMENTUM</small></span><span class="score">89<small>SCORE</small></span></button><button class="rec" data-code="8035.T"><b class="rank">3</b><span><b>8035.T　東京エレクトロン</b><small><span class="side SHORT">SHORT</span> SIGNAL TREND</small></span><span class="score">86<small>SCORE</small></span></button></div></section>
<section id="portfolio" class="page"><h1>保有・成績</h1><div class="eyebrow">LONG / SHORT · CASH / MARGIN · READ ONLY</div><div class="cards4"><div class="metric"><span>LONG</span><b>3</b></div><div class="metric"><span>SHORT</span><b>3</b></div><div class="metric"><span>評価損益</span><b class="green">+¥48,200</b></div><div class="metric"><span>V-LOCK</span><b class="gold">2</b></div></div><div class="box"><button class="holding" data-i="0"><div><b class="code">7203.T</b><small><span class="side LONG">LONG</span></small></div><div><b class="name">トヨタ自動車</b><small class="exec">MARGIN / 100株</small></div><div class="right"><b>¥3,142</b><b class="pnl green">+¥18,420 (+5.86%)</b><span class="status v">V-LOCK</span><div class="actions"><span>詳細</span><span>チャート</span></div></div></button><button class="holding" data-i="1"><div><b class="code">6758.T</b><small><span class="side SHORT">SHORT</span></small></div><div><b class="name">ソニーグループ</b><small class="exec">MARGIN / 100株</small></div><div class="right"><b>¥3,625</b><b class="pnl green">+¥12,800 (+3.66%)</b><span class="status ">TRAILING</span><div class="actions"><span>詳細</span><span>チャート</span></div></div></button><button class="holding" data-i="2"><div><b class="code">8306.T</b><small><span class="side LONG">LONG</span></small></div><div><b class="name">三菱UFJ FG</b><small class="exec">CASH / 100株</small></div><div class="right"><b>¥2,311</b><b class="pnl red">−¥4,260 (−1.81%)</b><span class="status ">HOLDING</span><div class="actions"><span>詳細</span><span>チャート</span></div></div></button><button class="holding" data-i="3"><div><b class="code">8035.T</b><small><span class="side SHORT">SHORT</span></small></div><div><b class="name">東京エレクトロン</b><small class="exec">MARGIN / 20株</small></div><div class="right"><b>¥24,830</b><b class="pnl green">+¥25,600 (+4.32%)</b><span class="status v">V-LOCK</span><div class="actions"><span>詳細</span><span>チャート</span></div></div></button><button class="holding" data-i="4"><div><b class="code">9432.T</b><small><span class="side LONG">LONG</span></small></div><div><b class="name">NTT</b><small class="exec">CASH / 1,000株</small></div><div class="right"><b>¥164.2</b><b class="pnl green">+¥3,120 (+2.03%)</b><span class="status ">TRAILING</span><div class="actions"><span>詳細</span><span>チャート</span></div></div></button><button class="holding" data-i="5"><div><b class="code">9984.T</b><small><span class="side SHORT">SHORT</span></small></div><div><b class="name">ソフトバンクグループ</b><small class="exec">MARGIN / 30株</small></div><div class="right"><b>¥9,821</b><b class="pnl red">−¥7,480 (−2.66%)</b><span class="status ">HOLDING</span><div class="actions"><span>詳細</span><span>チャート</span></div></div></button></div></section>
<section id="chart" class="page"><h1>チャート</h1><div class="eyebrow">7203.T / 60M / SAMPLE</div><div class="notice">Entry / Current / Current Stop　V-LOCKは金色で表示</div><div class="chartbox"><div class="legend">CURRENT　¥3,142<br>ENTRY　¥2,968<br><span class="gold">STOP　¥3,078</span></div><svg viewBox="0 0 500 400" preserveAspectRatio="none"><polyline points="0,330 50,310 100,320 150,270 200,285 250,220 300,235 350,170 400,185 450,110 500,125" fill="none" stroke="#49a7ff" stroke-width="4"></polyline><line x1="0" y1="285" x2="500" y2="285" stroke="#e8ba50" stroke-dasharray="8 7"></line><text x="14" y="278" fill="#e8ba50" font-size="12">CURRENT STOP / V-LOCK</text></svg></div></section>
<section id="progress" class="page"><h1>PROGRESS</h1><div class="progress">STAGE 1 / VERMILION ONLY</div><div class="guardian active"><div class="gicon">🔥</div><div><b>VERMILION</b><small>日本株 / QUADRANT</small></div><div class="lock">UNLOCKED<br><small>INITIAL</small></div></div><div class="guardian"><div class="gicon">🐉</div><div><b>AZURE</b><small>日経225マイクロ</small></div><div class="lock">LOCKED</div></div><div class="guardian"><div class="gicon">🐯</div><div><b>WHITE TIGER</b><small>金ミニ</small></div><div class="lock">LOCKED</div></div><div class="guardian"><div class="gicon">●</div><div><b>BLACK WARRIOR</b><small>日本株信用</small></div><div class="lock">LOCKED</div></div></section></div>
<nav><button class="on" data-p="home"><b>⌂</b>HOME</button><button data-p="recommend"><b>★</b>おすすめ</button><button data-p="portfolio"><b>▦</b>保有</button><button data-p="chart"><b>⌁</b>チャート</button><button data-p="progress"><b>◇</b>PROGRESS</button></nav>
<div id="sheet" class="sheet"><div class="sheetin"><div class="sheethead"><div id="st"></div><button id="close" class="close">×</button></div><div id="sb"></div></div></div><script>
const P=[{"code": "7203.T", "name": "トヨタ自動車", "side": "LONG", "execution": "MARGIN", "current": "¥3,142", "pnl": "+¥18,420", "pct": "+5.86%", "r": "+1.82R", "status": "V-LOCK", "hold": "3日", "entry": "¥2,968", "stop": "¥3,078", "qty": "100株"}, {"code": "6758.T", "name": "ソニーグループ", "side": "SHORT", "execution": "MARGIN", "current": "¥3,625", "pnl": "+¥12,800", "pct": "+3.66%", "r": "+1.41R", "status": "TRAILING", "hold": "5日", "entry": "¥3,761", "stop": "¥3,678", "qty": "100株"}, {"code": "8306.T", "name": "三菱UFJ FG", "side": "LONG", "execution": "CASH", "current": "¥2,311", "pnl": "−¥4,260", "pct": "−1.81%", "r": "−0.42R", "status": "HOLDING", "hold": "2日", "entry": "¥2,354", "stop": "¥2,268", "qty": "100株"}, {"code": "8035.T", "name": "東京エレクトロン", "side": "SHORT", "execution": "MARGIN", "current": "¥24,830", "pnl": "+¥25,600", "pct": "+4.32%", "r": "+2.14R", "status": "V-LOCK", "hold": "7日", "entry": "¥26,110", "stop": "¥25,240", "qty": "20株"}, {"code": "9432.T", "name": "NTT", "side": "LONG", "execution": "CASH", "current": "¥164.2", "pnl": "+¥3,120", "pct": "+2.03%", "r": "+0.88R", "status": "TRAILING", "hold": "4日", "entry": "¥160.9", "stop": "¥162.1", "qty": "1,000株"}, {"code": "9984.T", "name": "ソフトバンクグループ", "side": "SHORT", "execution": "MARGIN", "current": "¥9,821", "pnl": "−¥7,480", "pct": "−2.66%", "r": "−0.73R", "status": "HOLDING", "hold": "1日", "entry": "¥9,555", "stop": "¥10,040", "qty": "30株"}], $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
$$("nav button").forEach(b=>b.onclick=()=>{$$("nav button").forEach(x=>x.classList.toggle("on",x===b));$$(".page").forEach(x=>x.classList.toggle("on",x.id===b.dataset.p));scrollTo(0,0)});
function openP(i){let p=P[i],good=p.pnl.startsWith("+");$("#st").innerHTML=`<span class="side ${p.side}">${p.side}</span> ${p.code} ${p.name}`;$("#sb").innerHTML=`<div class="big ${good?"green":"red"}">${p.pnl} <small>${p.pct}</small></div><div>${p.r} · ${p.status}</div><div class="sect"><h3>CURRENT PROTECTION</h3><div class="grid"><span>Current Stop</span><b>${p.stop}</b><span>Holding</span><b>${p.hold}</b><span>Trailing</span><b>${p.status==="HOLDING"?"OFF":"ACTIVE"}</b><span>Profit Lock</span><b class="${p.status==="V-LOCK"?"gold":""}">${p.status==="V-LOCK"?"SECURED":"—"}</b></div></div><div class="sect"><h3>POSITION</h3><div class="grid"><span>Execution</span><b>${p.execution}</b><span>Entry</span><b>${p.entry}</b><span>Current</span><b>${p.current}</b><span>Quantity</span><b>${p.qty}</b></div></div>`;$("#sheet").classList.add("on")}
$$(".holding").forEach(b=>b.onclick=()=>openP(+b.dataset.i));$$(".rec").forEach(b=>b.onclick=()=>{let i=P.findIndex(p=>p.code===b.dataset.code);if(i>=0)openP(i)});$("#close").onclick=()=>$("#sheet").classList.remove("on");
</script>
<script>globalThis.__codexVisualizationInitialGlobals={"statePersistence":"none","stateModelContext":"none","visualizationStyleVariables":{"--accent":"rgb(232, 243, 254)","--accent-foreground":"rgb(44, 103, 197)","--background":"rgb(252, 252, 252)","--border":"rgba(0, 0, 0, 0.1)","--border-strong":"rgba(0, 0, 0, 0.15)","--card":"color-mix(in oklab, rgb(13, 13, 13) 5%, transparent)","--card-foreground":"rgb(13, 13, 13)","--corner-shape":"round","--control-spacing":"12px","--cursor-interaction":"pointer","--destructive":"rgb(226, 85, 7)","--font-mono":"ui-monospace, SFMono-Regular, \"SF Mono\", menlo, consolas, \"Liberation Mono\", monospace","--font-sans":"-apple-system-body, ui-sans-serif, -apple-system, system-ui, \"Segoe UI\", Helvetica, \"Apple Color Emoji\", Arial, sans-serif, \"Segoe UI Emoji\", \"Segoe UI Symbol\"","--font-size-base":"16px","--font-weight-normal":"400","--foreground":"rgb(13, 13, 13)","--input":"rgba(0, 0, 0, 0.15)","--muted":"color-mix(in srgb, rgb(13, 13, 13) 10%, transparent)","--muted-foreground":"rgb(143, 143, 143)","--popover":"rgb(255, 255, 255)","--popover-foreground":"rgb(13, 13, 13)","--primary":"rgb(44, 103, 197)","--primary-foreground":"rgb(255, 255, 255)","--radius":"8px","--radius-2xl":"16px","--radius-lg":"8px","--radius-md":"6px","--radius-sm":"4px","--ring":"rgb(58, 131, 247)","--secondary":"rgb(243, 243, 243)","--secondary-foreground":"rgb(13, 13, 13)","--blue":"rgb(58, 131, 247)","--orange":"rgb(226, 85, 7)","--green":"rgb(0, 162, 64)","--red":"rgb(224, 46, 42)","--purple":"rgb(146, 79, 247)","--yellow":"rgb(255, 195, 0)","--visualize-paint-gutter":"0px","--viz-series-1":"rgb(44, 103, 197)","--viz-series-2":"#f3c944","--viz-series-3":"#ea77b0","--viz-series-4":"#3db9b0","--viz-series-5":"#5ec978","--viz-series-6":"#f2893c"},"visualizationTheme":"light"};</script>
<style id="codex-visualization-host-theme">:root {}</style>
<script>
(() => {
  // Host colors are defaults; later authored styles can give the same names
  // their own meaning (for example, --muted as a chart's label color).
  const hostStyles = document.getElementById("codex-visualization-host-theme");
  const hostStyle = hostStyles.sheet.cssRules[0].style;
  // Typography, geometry and interaction cursors still follow the host.
  const styleForProperty = (property) =>
    /^--(?:font-|radius|corner-shape$|control-spacing$|cursor-interaction$|icon-size$|visualize-paint-gutter$)/.test(property)
      ? document.documentElement.style
      : hostStyle;
  const initialGlobals =
    globalThis.__codexVisualizationInitialGlobals ?? globalThis.openai;
  delete globalThis.__codexVisualizationInitialGlobals;
  if (initialGlobals?.statePersistence != null) {
    globalThis.openai ??= {};
    globalThis.openai.statePersistence = initialGlobals.statePersistence;
    globalThis.openai.stateModelContext = initialGlobals.stateModelContext ?? "none";
  }
  if (!false) {
    return;
  }
  let appliedProperties = [];
  const applyHostStyleVariables = (styleVariables) => {
    if (styleVariables == null || typeof styleVariables !== "object") {
      return;
    }
    for (const property of appliedProperties) {
      styleForProperty(property).removeProperty(property);
    }
    appliedProperties = [];
    for (const [property, value] of Object.entries(styleVariables)) {
      if (property.startsWith("--") && typeof value === "string") {
        styleForProperty(property).setProperty(property, value);
        appliedProperties.push(property);
      }
    }
  };

  const syncHostStyles = (globals) => {
    applyHostStyleVariables(globals?.visualizationStyleVariables);
    const sandboxDocument = globalThis.frameElement?.ownerDocument;
    if (sandboxDocument != null && globals?.visualizationTheme != null) {
      let colorSchemeMeta = sandboxDocument.querySelector(
        'meta[name="color-scheme"]',
      );
      if (colorSchemeMeta == null) {
        colorSchemeMeta = sandboxDocument.createElement("meta");
        colorSchemeMeta.name = "color-scheme";
        sandboxDocument.head.appendChild(colorSchemeMeta);
      }
      colorSchemeMeta.content = globals.visualizationTheme;
      sandboxDocument.documentElement.style.colorScheme =
        globals.visualizationTheme;
      // Paint the host surface behind transparent saved visualization documents.
      sandboxDocument.documentElement.style.backgroundColor =
        hostStyle.getPropertyValue("--background");
    }
  };

  syncHostStyles(initialGlobals);
  globalThis.addEventListener("openai:set_globals", (event) => {
    syncHostStyles(event.detail?.globals);
  });
})();
</script>
<script>
(() => {
  const reportEnvironmentError = (value) => {
    const error = value instanceof Error ? value : new Error(String(value));
    void globalThis.openai
      .callTool(
        "__codex_inline_visualization_error__",
        {
          message: error.message,
          name: error.name,
          stack: error.stack,
        },
      )
      .catch(() => {});
  };

  globalThis.addEventListener("error", (event) => {
    if (event.target?.localName === "script") {
      // A script's own onerror may render a fallback or load an alternative.
      // Let that handler run; failures it throws still reach the global error path.
      const handlesError = typeof event.target.onerror === "function";
      globalThis.queueMicrotask(() => {
        if (!handlesError && !event.defaultPrevented) {
          reportEnvironmentError("Visualization script could not be loaded");
        }
      });
    } else if (event.target === globalThis) {
      reportEnvironmentError(event.error ?? event.message);
    }
  }, true);
  globalThis.addEventListener("unhandledrejection", (event) => {
    reportEnvironmentError(event.reason);
  });
})();
</script>
<script id="codex-visualization-variants">
(() => {
  let previousSnapshot = "[]";
  let roots = [];
  const report = () => {
    roots = Array.from(
      document.querySelectorAll(".viz-carousel[data-active-variant]"),
    ).slice(0, 32);
    const selectedVariants = roots.flatMap((root, carousel) => {
      const variant = root.dataset.activeVariant;
      const label = root.getAttribute("aria-label")?.slice(0, 256);
      return variant ? [{
        carousel,
        ...(label == null ? {} : { label }),
        variant: variant.slice(0, 256),
      }] : [];
    });
    const snapshot = JSON.stringify(selectedVariants);
    if (snapshot !== previousSnapshot) {
      previousSnapshot = snapshot;
      void globalThis.openai.callTool("__codex_visualization_annotations__", {
        type: "variants",
        selectedVariants,
      }).catch(() => {});
    }
  };
  const observer = new MutationObserver((records) => {
    if (records.some((record) => record.type === "attributes") || roots.some((root) => !root.isConnected)) {
      report();
    }
  });
  observer.observe(document, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["data-active-variant"],
  });
  report();
  globalThis.addEventListener("pagehide", () => observer.disconnect(), { once: true });
})();
</script>
<script>
(() => {
  let isHovering = false;
  let isTouch = false;
  const reportHover = (nextIsHovering, nextIsTouch = false) => {
    if (nextIsHovering === isHovering && nextIsTouch === isTouch) {
      return;
    }
    isHovering = nextIsHovering;
    isTouch = nextIsTouch;
    void globalThis.openai
      .callTool(
        "__codex_inline_visualization_hover__",
        isTouch ? { isHovering, pointerType: "touch" } : { isHovering },
      )
      .catch(() => {});
  };

  globalThis.addEventListener(
    "pointerover",
    (event) =>
      reportHover(event.pointerType !== "touch", event.pointerType === "touch"),
    { capture: true },
  );
  globalThis.addEventListener(
    "pointerout",
    (event) => {
      if (event.pointerType !== "touch" && event.relatedTarget == null) {
        reportHover(false);
      }
    },
    { capture: true },
  );
})();
</script>
<script>
(() => {
  const report = (method) => {
    void globalThis.openai.callTool("__codex_inline_visualization_input__", { method }).catch(() => {});
  };
  globalThis.addEventListener("pointerdown", () => report("pointer"), { capture: true });
  globalThis.addEventListener("keydown", (event) => {
    if (!event.isComposing && event.key !== "Shift" && !event.altKey && !event.ctrlKey && !event.metaKey) {
      report(["Tab","ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key) ? "keyboard-navigation" : "keyboard");
    }
  }, { capture: true });
})();
</script>
<script>
(() => {
  const bubbledClicks = new WeakSet();
  const interactiveSelector = [
    "button", "input", "select", "textarea", "label", "summary", "a[href]",
    "audio[controls]", "video[controls]", "[onclick]", "[data-visualization-interactive]",
    '[contenteditable]:not([contenteditable="false"])',
    ...[
      "button", "checkbox", "combobox", "gridcell", "link", "listbox",
      "menuitem", "menuitemcheckbox", "menuitemradio", "option", "radio",
      "scrollbar", "searchbox", "slider", "spinbutton", "switch", "tab",
      "textbox", "treeitem",
    ].map((role) => '[role~="' + role + '"]'),
  ].join(",");

  globalThis.addEventListener("click", (event) => bubbledClicks.add(event));
  globalThis.addEventListener("click", (event) => {
    // Capture the path before a control can remove itself. Custom delegated
    // controls can opt in with data-visualization-interactive.
    const elements = event.composedPath().filter((target) => target instanceof Element);
    const isInteractiveTarget = elements.some((element) =>
      element.matches(interactiveSelector) ||
      (element.hasAttribute("tabindex") && element.tabIndex >= 0)) ||
      (elements[0] != null && getComputedStyle(elements[0]).cursor === "pointer");
    // Use a task, not a microtask: native dispatch can run microtasks between
    // listeners. Propagation flags are reset when dispatch finishes:
    // https://dom.spec.whatwg.org/#concept-event-dispatch
    globalThis.setTimeout(() => {
      void globalThis.openai.callTool("__codex_inline_visualization_click__", {
        isInteractive: isInteractiveTarget || event.defaultPrevented ||
          (event.bubbles && !bubbledClicks.has(event)),
      }).catch(() => {});
    }, 0);
  }, { capture: true });
})();
</script>
<script>
(() => {
  globalThis.addEventListener("keydown", (event) => {
    if (event.isComposing || event.altKey || event.ctrlKey || event.metaKey ||
      event.shiftKey || !["ArrowLeft", "ArrowRight", "Escape"].includes(event.key)) {
      return;
    }
    const target = event.composedPath().find((element) => element instanceof HTMLElement);
    const editable = target?.closest("[contenteditable]");
    const editing = target && (target.isContentEditable ||
      (editable && editable.getAttribute("contenteditable") !== "false") ||
      target.closest('input, textarea, select, [role="slider"], [role="spinbutton"], [role="combobox"], [role="listbox"], [role="grid"], [role="tree"], [role="tablist"], [role="menu"]'));
    if (event.key !== "Escape" && editing) { return; }
    // Let the widget handle the key before forwarding it across the sandbox.
    globalThis.setTimeout(() => {
      if (!event.defaultPrevented && globalThis.openai?.displayMode === "fullscreen") {
        void globalThis.openai.callTool("__codex_inline_visualization_preview_key__", {
          key: event.key,
        }).catch(() => {});
      }
    }, 0);
  });
})();
</script>




<script>
(() => {
  const contentRange = document.createRange();
  let previousMeasurement = null;
  let heightReportTimer = null;
  const reportHeight = () => {
    const bodyChildren = Array.from(document.body.children).filter(
      (element) =>
        element.tagName !== "SCRIPT" &&
        element.tagName !== "STYLE" &&
        element.getAttribute("role") !== "tooltip",
    );
    const bodyStyle = globalThis.getComputedStyle(document.body);
    const contentWidth = Math.max(
      0,
      Math.round(
        globalThis.innerWidth -
          parseFloat(bodyStyle.paddingLeft) -
          parseFloat(bodyStyle.paddingRight),
      ),
    );
    let contentHeight;
    if (bodyChildren.length === 0) {
      contentRange.selectNodeContents(document.body);
      contentHeight = contentRange.getBoundingClientRect().height;
    } else if (bodyChildren.length === 1) {
      const [bodyChild] = bodyChildren;
      const childRect = bodyChild.getBoundingClientRect();
      // Child margins can collapse above the root without adding to its height.
      // The host adds body padding separately.
      contentHeight =
        Math.max(bodyChild.scrollHeight, childRect.height) +
        Math.max(
          0,
          childRect.top -
            document.body.getBoundingClientRect().top -
            parseFloat(bodyStyle.paddingTop),
        );
    } else {
      const bodyTop = document.body.getBoundingClientRect().top;
      contentHeight = Math.max(
        ...bodyChildren.map(
          (bodyChild) => bodyChild.getBoundingClientRect().bottom - bodyTop,
        ),
      );
    }
    const viewportHeight = globalThis.innerHeight;
    const previous = previousMeasurement;
    previousMeasurement = { contentHeight, contentWidth, viewportHeight };
    if (
      previous != null &&
      contentWidth === previous.contentWidth &&
      contentHeight - previous.contentHeight ===
        viewportHeight - previous.viewportHeight
    ) {
      return;
    }

    void globalThis.openai
      .callTool(
        "__codex_inline_visualization_height__",
        { height: contentHeight, width: contentWidth },
      )
      .catch(() => {});
  };
  const scheduleHeightReport = () => {
    if (heightReportTimer != null) {
      return;
    }
    // Offscreen frames can suspend animation callbacks while their content loads.
    heightReportTimer = globalThis.setTimeout(() => {
      heightReportTimer = null;
      reportHeight();
    }, 0);
  };

  const resizeObserver = new ResizeObserver(scheduleHeightReport);
  const observeBodyChildren = () => {
    for (const element of document.body.children) {
      resizeObserver.observe(element);
    }
  };
  resizeObserver.observe(document.body);
  observeBodyChildren();
  new MutationObserver(() => {
    observeBodyChildren();
    scheduleHeightReport();
  }).observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["style", "class", "height", "width"],
  });
  globalThis.addEventListener("resize", scheduleHeightReport);
  reportHeight();
})();
</script>
<style id="codex-visualization-document-scrollbar">html,body{scrollbar-width:none!important}html::-webkit-scrollbar,body::-webkit-scrollbar{display:none!important}</style>

</body></html>
````

## design_reference/corrected_ui_v_lock_chart.svg

````text
<svg viewBox="0 0 500 400" preserveAspectRatio="none"><polyline points="0,330 50,310 100,320 150,270 200,285 250,220 300,235 350,170 400,185 450,110 500,125" fill="none" stroke="#49a7ff" stroke-width="4"></polyline><line x1="0" y1="285" x2="500" y2="285" stroke="#e8ba50" stroke-dasharray="8 7"></line><text x="14" y="278" fill="#e8ba50" font-size="12">CURRENT STOP / V-LOCK</text></svg>
````

## design_reference/QUADRANT_Q_MOBILE_DEMO.html

````text
<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no"><meta name="theme-color" content="#05070a"><title>QUADRANT</title><style>
:root{--bg:#05070a;--panel:#0c1118;--line:#24303d;--text:#f4f7fb;--muted:#718093;--blue:#168cff;--red:#ff3f57;--green:#22d47b;--gold:#ffb820}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}button{font:inherit;color:inherit}#app{max-width:620px;margin:auto;min-height:100vh;padding:env(safe-area-inset-top) 14px calc(86px + env(safe-area-inset-bottom))}
header{padding:18px 2px 15px;border-bottom:1px solid var(--line)}.brand{font-weight:950;letter-spacing:.18em;font-size:23px}.brand em{font-style:normal;color:#98a6b8;font-size:11px;margin-left:7px}.tag{font-size:9px;color:#6e7b8d;margin-top:5px;letter-spacing:.12em}.live{float:right;margin-top:-29px;border:1px solid #956f18;color:var(--gold);padding:5px 7px;border-radius:6px;font-size:9px;font-weight:900}
.view{display:none;padding-top:18px}.view.active{display:block}.kicker{font-size:9px;letter-spacing:.2em;color:#69778a;font-weight:900}h2{font-size:20px;margin:4px 0 13px}.pcard,.srow{width:100%;background:linear-gradient(145deg,var(--panel),#090d12);border:1px solid var(--line);border-radius:12px;text-align:left;margin-bottom:9px}.pcard{padding:13px}.pcard:active,.srow:active{transform:scale(.99);background:#111923}.crow{display:flex;justify-content:space-between;gap:10px}.side{display:inline-block;border:1px solid;border-radius:4px;padding:3px 7px;font-size:10px;font-weight:950;margin-right:7px}.long{color:var(--blue)}.short{color:var(--red)}.nm{font-size:11px;color:#7c8a9c;margin-top:5px}.vlock{display:inline-grid;place-items:center;width:24px;height:24px;margin-left:7px;border:1px solid #a97912;border-radius:50%;color:var(--gold);font-weight:1000;box-shadow:0 0 10px #ffb82044}.money{font-size:18px;font-weight:950;text-align:right}.money small{display:block;font-size:10px}.pos{color:var(--green)}.neg{color:var(--red)}.gold{color:var(--gold)}.stats{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid #1e2833;border-bottom:1px solid #1e2833;margin-top:12px;padding:9px 0;text-align:center}.stats small{display:block;color:#657487;font-size:8px}.stats b{font-size:11px}.hint{display:flex;justify-content:space-between;color:#657487;font-size:9px;padding-top:9px}.hint span{color:#a6b1bd;font-weight:800}.srow{display:grid;grid-template-columns:28px 1fr auto;gap:8px;align-items:center;padding:11px}.rank{color:#566476;font-size:10px;font-weight:900}.srow small{display:block;color:#718093;font-size:9px;margin-top:4px}.ss{text-align:right}.ss b{font-size:17px}.empty{padding:32px;text-align:center;color:#6e7b8d;border:1px dashed var(--line);border-radius:12px}
nav{position:fixed;z-index:20;bottom:0;left:0;right:0;margin:auto;max-width:620px;background:#080c12ee;backdrop-filter:blur(16px);border-top:1px solid var(--line);padding:7px 7px calc(7px + env(safe-area-inset-bottom));display:grid;grid-template-columns:repeat(4,1fr)}nav button{border:0;background:none;color:#657487;min-height:52px;font-size:9px;font-weight:850}nav button b{display:block;font-size:17px}nav button.on{color:#eaf1f8}
.sheet{display:none;position:fixed;z-index:30;inset:0;background:#05070af2;overflow:auto;padding:calc(12px + env(safe-area-inset-top)) 14px calc(25px + env(safe-area-inset-bottom))}.sheet.open{display:block}.sheetin{max-width:620px;margin:auto}.sheethead{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding:5px 0 14px}.x{width:44px;height:44px;border-radius:50%;border:1px solid #344151;background:#111821;font-size:20px}.bigpl{font-size:29px;font-weight:1000;margin:18px 0 2px}.sect{margin-top:20px;padding-top:14px;border-top:1px solid var(--line)}.sect h3{font-size:9px;letter-spacing:.18em;color:#69778a}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 14px;font-size:12px}.grid span{color:#718093}.chart{position:relative;height:220px;margin-top:8px;border-left:1px solid #293747;border-bottom:1px solid #293747}.chart svg{position:absolute;inset:0;width:100%;height:100%}.level{position:absolute;left:0;right:0;border-top:1px dashed #4c5c70;font-size:9px;color:#8c9bad;padding:4px}.entry{top:35%}.stop{top:68%;border-color:#c18d1c}.legend{display:flex;justify-content:space-between;margin-top:8px;color:#758397;font-size:9px}.demofoot{margin:22px 2px;color:#536173;font-size:9px}
</style></head><body><div id="app"><header><div class="brand">QUADRANT <em>Q</em></div><div class="tag">SEE THE EDGE. TRADE THE FUTURE</div><div class="live">DEMO · READ ONLY</div></header>
<section id="portfolio" class="view active"><div class="kicker">PORTFOLIO</div><h2>POSITIONS</h2><button class="pcard" data-i="0"><div class="crow"><div><span class="side long">LONG</span><b>7203</b><span class="vlock">V</span><div class="nm">トヨタ自動車</div></div><div class="money pos">+¥18,420<small>+5.86%</small></div></div><div class="stats"><div><small>CURRENT</small><b>¥3,142</b></div><div><small>R</small><b class="pos">+1.82R</b></div><div><small>STATUS</small><b class="gold">V-LOCK</b></div></div><div class="hint">3D · MARGIN<span>DETAIL ›</span></div></button><button class="pcard" data-i="1"><div class="crow"><div><span class="side short">SHORT</span><b>6758</b><div class="nm">ソニーグループ</div></div><div class="money pos">+¥12,800<small>+3.66%</small></div></div><div class="stats"><div><small>CURRENT</small><b>¥3,625</b></div><div><small>R</small><b class="pos">+1.41R</b></div><div><small>STATUS</small><b class="">TRAIL</b></div></div><div class="hint">5D · MARGIN<span>DETAIL ›</span></div></button><button class="pcard" data-i="2"><div class="crow"><div><span class="side long">LONG</span><b>8306</b><div class="nm">三菱UFJ FG</div></div><div class="money neg">−¥4,260<small>-1.81%</small></div></div><div class="stats"><div><small>CURRENT</small><b>¥2,311</b></div><div><small>R</small><b class="neg">-0.42R</b></div><div><small>STATUS</small><b class="">HOLD</b></div></div><div class="hint">2D · CASH<span>DETAIL ›</span></div></button><button class="pcard" data-i="3"><div class="crow"><div><span class="side short">SHORT</span><b>8035</b><span class="vlock">V</span><div class="nm">東京エレクトロン</div></div><div class="money pos">+¥25,600<small>+4.32%</small></div></div><div class="stats"><div><small>CURRENT</small><b>¥24,830</b></div><div><small>R</small><b class="pos">+2.14R</b></div><div><small>STATUS</small><b class="gold">V-LOCK</b></div></div><div class="hint">7D · MARGIN<span>DETAIL ›</span></div></button><button class="pcard" data-i="4"><div class="crow"><div><span class="side long">LONG</span><b>9432</b><div class="nm">NTT</div></div><div class="money pos">+¥3,120<small>+2.03%</small></div></div><div class="stats"><div><small>CURRENT</small><b>¥164.2</b></div><div><small>R</small><b class="pos">+0.88R</b></div><div><small>STATUS</small><b class="">TRAIL</b></div></div><div class="hint">4D · CASH<span>DETAIL ›</span></div></button><button class="pcard" data-i="5"><div class="crow"><div><span class="side short">SHORT</span><b>9984</b><div class="nm">ソフトバンクグループ</div></div><div class="money neg">−¥7,480<small>-2.66%</small></div></div><div class="stats"><div><small>CURRENT</small><b>¥9,821</b></div><div><small>R</small><b class="neg">-0.73R</b></div><div><small>STATUS</small><b class="">HOLD</b></div></div><div class="hint">1D · MARGIN<span>DETAIL ›</span></div></button><div class="demofoot">SAMPLE DATA · NO ORDER EXECUTION</div></section>
<section id="orders" class="view"><div class="kicker">08:50</div><h2>MORNING SCREENING</h2><button class="srow" data-code="7203"><span class="rank">01</span><span><span class="side long">LONG</span><b>7203</b><small>トヨタ自動車</small></span><span class="ss"><b>92</b><small>BREAKOUT</small></span></button><button class="srow" data-code="6758"><span class="rank">02</span><span><span class="side short">SHORT</span><b>6758</b><small>ソニーグループ</small></span><span class="ss"><b>89</b><small>MOMENTUM</small></span></button><button class="srow" data-code="8035"><span class="rank">03</span><span><span class="side short">SHORT</span><b>8035</b><small>東京エレクトロン</small></span><span class="ss"><b>86</b><small>TREND</small></span></button><button class="srow" data-code="8306"><span class="rank">04</span><span><span class="side long">LONG</span><b>8306</b><small>三菱UFJ FG</small></span><span class="ss"><b>82</b><small>PULLBACK</small></span></button><button class="srow" data-code="9432"><span class="rank">05</span><span><span class="side long">LONG</span><b>9432</b><small>NTT</small></span><span class="ss"><b>79</b><small>TREND</small></span></button><button class="srow" data-code="9984"><span class="rank">06</span><span><span class="side short">SHORT</span><b>9984</b><small>ソフトバンクグループ</small></span><span class="ss"><b>76</b><small>REVERSAL</small></span></button></section>
<section id="history" class="view"><div class="kicker">TRADE LOG</div><h2>HISTORY</h2><div class="empty">READ ONLY DEMO</div></section>
<section id="analytics" class="view"><div class="kicker">PERFORMANCE</div><h2>ANALYTICS</h2><div class="empty">READ ONLY DEMO</div></section>
<nav><button class="on" data-v="portfolio"><b>▦</b>PORTFOLIO</button><button data-v="orders"><b>⌁</b>SCREEN</button><button data-v="history"><b>↺</b>HISTORY</button><button data-v="analytics"><b>◇</b>ANALYTICS</button></nav></div>
<div id="sheet" class="sheet"><div class="sheetin"><div class="sheethead"><div id="shTitle"></div><button class="x" id="close">×</button></div><div id="shBody"></div></div></div><script>
const P=[{"code": "7203", "name": "トヨタ自動車", "side": "LONG", "current": 3142, "pnl": 18420, "pct": 5.86, "r": 1.82, "status": "V-LOCK", "hold": "3D", "exe": "MARGIN", "entry": 2968, "stop": 3078, "qty": 100}, {"code": "6758", "name": "ソニーグループ", "side": "SHORT", "current": 3625, "pnl": 12800, "pct": 3.66, "r": 1.41, "status": "TRAIL", "hold": "5D", "exe": "MARGIN", "entry": 3761, "stop": 3678, "qty": 100}, {"code": "8306", "name": "三菱UFJ FG", "side": "LONG", "current": 2311, "pnl": -4260, "pct": -1.81, "r": -0.42, "status": "HOLD", "hold": "2D", "exe": "CASH", "entry": 2354, "stop": 2268, "qty": 100}, {"code": "8035", "name": "東京エレクトロン", "side": "SHORT", "current": 24830, "pnl": 25600, "pct": 4.32, "r": 2.14, "status": "V-LOCK", "hold": "7D", "exe": "MARGIN", "entry": 26110, "stop": 25240, "qty": 20}, {"code": "9432", "name": "NTT", "side": "LONG", "current": 164.2, "pnl": 3120, "pct": 2.03, "r": 0.88, "status": "TRAIL", "hold": "4D", "exe": "CASH", "entry": 160.9, "stop": 162.1, "qty": 1000}, {"code": "9984", "name": "ソフトバンクグループ", "side": "SHORT", "current": 9821, "pnl": -7480, "pct": -2.66, "r": -0.73, "status": "HOLD", "hold": "1D", "exe": "MARGIN", "entry": 9555, "stop": 10040, "qty": 30}];const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
$$("nav button").forEach(b=>b.onclick=()=>{$$("nav button").forEach(x=>x.classList.toggle("on",x===b));$$(".view").forEach(v=>v.classList.toggle("active",v.id===b.dataset.v));scrollTo(0,0)});
const f=n=>Number(n).toLocaleString("ja-JP",{maximumFractionDigits:1});
function openP(i){let p=P[i],good=p.pnl>=0,side=p.side.toLowerCase();$("#shTitle").innerHTML=`<span class="side ${side}">${p.side}</span><b>${p.code} ${p.name}</b>${p.status==="V-LOCK"?'<span class="vlock">V</span>':""}`;let pts=p.side==="LONG"?"0,178 55,164 110,170 165,135 220,146 275,104 330,115 385,75 440,88 500,52":"0,45 55,60 110,52 165,88 220,77 275,120 330,108 385,150 440,138 500,175";$("#shBody").innerHTML=`<div class="bigpl ${good?"pos":"neg"}">${good?"+":"−"}¥${Math.abs(p.pnl).toLocaleString()}</div><div class="${good?"pos":"neg"}">${p.pct>=0?"+":""}${p.pct.toFixed(2)}% · ${p.r>=0?"+":""}${p.r.toFixed(2)}R</div><div class="sect"><h3>CURRENT PROTECTION</h3><div class="grid"><span>Current Stop</span><b>¥${f(p.stop)}</b><span>Distance</span><b>¥${f(Math.abs(p.current-p.stop))}</b><span>Trailing</span><b>${p.status==="HOLD"?"OFF":"ACTIVE"}</b><span>Profit Lock</span><b class="${p.status==="V-LOCK"?"gold":""}">${p.status==="V-LOCK"?"SECURED":"—"}</b></div></div><div class="sect"><h3>POSITION</h3><div class="grid"><span>Execution</span><b>${p.exe}</b><span>Entry</span><b>¥${f(p.entry)}</b><span>Current</span><b>¥${f(p.current)}</b><span>Quantity</span><b>${p.qty.toLocaleString()}</b></div></div><div class="sect"><h3>CHART</h3><div class="chart"><div class="level entry">ENTRY ¥${f(p.entry)}</div><div class="level stop">CURRENT STOP ¥${f(p.stop)}</div><svg viewBox="0 0 500 220" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="${p.side==="LONG"?"#168cff":"#ff3f57"}" stroke-width="4" vector-effect="non-scaling-stroke"/></svg></div><div class="legend"><span>ENTRY</span><b>CURRENT ¥${f(p.current)}</b><span>STOP</span></div></div>`;$("#sheet").classList.add("open");document.body.style.overflow="hidden"}
$$(".pcard").forEach(b=>b.onclick=()=>openP(+b.dataset.i));$("#close").onclick=()=>{$("#sheet").classList.remove("open");document.body.style.overflow=""};$$(".srow").forEach(b=>b.onclick=()=>{let i=P.findIndex(p=>p.code===b.dataset.code);if(i>=0)openP(i)});
</script></body></html>
````

## design_reference/quadrant_showcase.html

````text
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'">
<title>QUADRANT / Q — READ ONLY SHOWCASE</title>
<style>
:root{color-scheme:dark;--bg:#0e1219;--panel:#141b26;--line:#293343;--text:#ecf0f6;--muted:#a5afc0;--blue:#80b7ff;--red:#ff8590;--green:#68dba5;--gold:#efcc7c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI","Yu Gothic UI",Meiryo,sans-serif}
button{font:inherit;color:var(--text);background:#202b3c;border:1px solid #3c4c62;border-radius:5px;padding:7px 12px;cursor:pointer}
button:hover{background:#30405a;border-color:#95a8c3}button:focus-visible{outline:2px solid var(--blue);outline-offset:3px}
header{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:15px;padding:19px 32px;background:#101620;border-bottom:1px solid var(--line)}
.brand{font-size:23px;letter-spacing:3px;font-weight:700}.ro{font-size:11px;letter-spacing:2px;color:var(--muted);margin-left:20px}
.safety{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;font-weight:700;letter-spacing:1.5px}.demo{color:var(--gold);border:1px solid #685736;padding:5px 10px}.noorder{padding:5px 0;color:var(--muted)}
main{max-width:1520px;margin:auto;padding:28px 32px 40px}.intro{display:flex;justify-content:space-between;gap:20px;align-items:baseline;margin-bottom:24px}
h1{font-size:25px;font-weight:500;margin:0 0 5px}p{margin:0;color:var(--muted)}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--muted);margin-bottom:7px}
section{margin-bottom:28px}.sectionhead{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px}
h2{font-size:15px;letter-spacing:1.8px;margin:0;font-weight:650}.sub{color:var(--muted);font-size:12px}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
table{width:100%;border-collapse:collapse;white-space:nowrap}th{text-align:left;font-size:10px;color:var(--muted);letter-spacing:1.2px;font-weight:500;background:#18202d;padding:12px 16px}
td{padding:13px 16px;border-top:1px solid var(--line);font-size:13px}tbody tr:hover{background:#1a2433}.num{text-align:right;font-variant-numeric:tabular-nums}.code{font-weight:700;letter-spacing:.6px}
.rank{color:var(--muted);font-size:12px}.side{display:inline-block;min-width:62px;text-align:center;border:1px solid;border-radius:4px;padding:3px 8px;font-size:11px;font-weight:700;letter-spacing:1px}
.long{color:var(--blue);border-color:#598ac2}.short{color:var(--red);border-color:#ba5965}.positive{color:var(--green)}.negative{color:var(--red)}.pnl{font-weight:650}
.status{font-size:11px;letter-spacing:.7px;font-weight:650}.holding{color:#c2cada}.trailing{color:var(--blue)}.v-lock,.gold{color:var(--gold)}.secured{display:block;font-size:8px;letter-spacing:1px;color:var(--gold);margin-top:2px}
.actions{display:flex;gap:7px}.actions button{padding:5px 10px;font-size:12px}.score{font-size:17px;font-weight:650}.signal{font-size:10px;letter-spacing:.5px;color:#c2ccdc}
.legend{display:flex;gap:22px;font-size:11px;color:var(--muted);margin-top:12px;flex-wrap:wrap}footer{border-top:1px solid var(--line);padding-top:16px;font-size:11px;color:var(--muted)}
.overlay{position:fixed;inset:0;background:#05080ec9;z-index:20}.overlay[hidden]{display:none}.drawer{position:absolute;right:0;top:0;bottom:0;width:min(460px,100%);overflow:auto;background:#151d29;border-left:1px solid #415169;padding:25px 28px}
.dialogtop{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}.dialogtop .eyebrow{margin:0}.dialogname{font-size:23px;letter-spacing:1px;margin:0 0 4px}.company{font-size:16px;margin:0 0 15px}
.badges{display:flex;align-items:center;gap:15px;margin-bottom:24px}.metrics{display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:8px;padding:17px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.metrics small{display:block;color:var(--muted);font-size:10px;margin-bottom:5px}.metrics strong{font-size:21px;font-variant-numeric:tabular-nums;white-space:nowrap}
.block{margin-top:24px}.block h3{font-size:11px;letter-spacing:1.6px;color:var(--muted);margin:0 0 12px}.protection{padding:16px;border:1px solid #52677d;border-radius:6px;background:#1b2939}
dl{margin:0}dl>div{display:flex;justify-content:space-between;gap:16px;padding:7px 0}dt{color:var(--muted);font-size:12px}dd{margin:0;text-align:right;font-size:13px}dd.emphasis{font-size:20px;font-weight:650;color:var(--blue)}
.note{font-size:10px;color:var(--muted);margin-top:12px;line-height:1.7}.modal{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:min(960px,94vw);max-height:92vh;overflow:auto;padding:25px;background:#151d29;border:1px solid #43536c;border-radius:10px}
.chartlegend{display:flex;gap:22px;margin:18px 0;font-size:11px;flex-wrap:wrap}.chartlegend span:before{content:"";display:inline-block;width:20px;height:2px;background:currentColor;margin:0 7px 3px 0}.price{color:#dce7f8}.entry{color:#929fb7}.stop{color:var(--blue);font-weight:700}
svg{display:block;width:100%;height:auto;background:#101823;border:1px solid var(--line);border-radius:6px}
.modal .chartfoot{display:flex;justify-content:space-between;margin-top:12px;gap:15px;font-size:11px;color:var(--muted)}
@media(max-width:760px){header{padding:14px 16px;align-items:flex-start;flex-direction:column;gap:8px}.brand{font-size:19px}.ro{margin-left:12px}main{padding:22px 16px}.intro{display:block}.intro .sub{margin-top:8px}td,th{padding:12px}.sectionhead{gap:10px}.metrics strong{font-size:18px}.drawer{padding:20px}.modal{padding:16px}}
</style>
</head>
<body>
<header><div><span class="brand">QUADRANT / Q</span><span class="ro">READ ONLY</span></div><div class="safety"><span class="demo">DEMO / SAMPLE DATA</span><span class="noorder">NO ORDER EXECUTION</span></div></header>
<main id="main">
<div class="intro"><div><div class="eyebrow">QUADRANT READ ONLY SHOWCASE</div><h1>候補とポジションを、一目で。</h1><p>すべて架空のサンプルです。実市場価格・実績を示すものではありません。</p></div><span class="sub">OFFLINE / SAMPLE SESSION</span></div>
<section aria-labelledby="screen-title"><div class="sectionhead"><h2 id="screen-title">MORNING SCREENING</h2><span class="sub">朝の候補 · SAMPLE / 6 CANDIDATES</span></div>
<div class="tablewrap"><table id="screening"><thead><tr><th>RANK</th><th>CODE</th><th>NAME</th><th>SIDE</th><th class="num">SCORE</th><th>SIGNAL</th><th>操作</th></tr></thead><tbody></tbody></table></div></section>
<section aria-labelledby="positions-title"><div class="sectionhead"><h2 id="positions-title">POSITIONS</h2><span class="sub">6 SAMPLE POSITIONS · JPY</span></div>
<div class="tablewrap"><table id="positions"><thead><tr><th>CODE</th><th>NAME</th><th>SIDE</th><th class="num">CURRENT</th><th class="num">P/L</th><th class="num">P/L %</th><th class="num">R</th><th>STATUS</th><th>HOLDING</th><th>操作</th></tr></thead><tbody></tbody></table></div>
<div class="legend"><span>HOLDING · 保有中</span><span>TRAILING · ストップ追随中</span><span class="gold">V-LOCK · PROFIT SECURED</span><span>損益は価格差による架空の評価損益</span></div></section>
<footer>DEMO / SAMPLE DATA · NO ORDER EXECUTION<br>CASH / MARGINはサンプル表示です。正式なLONGの執行方式を確定するものではありません。</footer>
</main>
<div id="detail-overlay" class="overlay" hidden><aside id="drawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="detail-name" tabindex="-1"></aside></div>
<div id="chart-overlay" class="overlay" hidden><div id="chart-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="chart-name" tabindex="-1"></div></div>
<script id="sample-data" type="application/json">[{"code": "7203", "name": "トヨタ自動車", "side": "LONG", "execution": "CASH", "entry": 2800, "current": 2960, "stop": 2890, "quantity": 200, "risk": 100, "status": "V-LOCK", "score": 92, "signal": "TREND CONTINUATION", "holding": "6 sessions", "entry_time": "SAMPLE D−6 / 09:15 JST", "pnl": 32000, "pct": 5.714285714285714, "r": 1.6, "distance": 70, "distance_pct": 2.364864864864865, "strategy": "SAMPLE / TREND CONTINUATION", "trailing": "ACTIVE", "profit_lock": "SECURED", "series": [2800.0, 2807.47, 2809.14, 2809.11, 2825.13, 2834.72, 2821.77, 2826.87, 2855.61, 2853.67, 2832.85, 2853.7, 2883.5, 2864.68, 2850.16, 2885.67, 2902.78, 2874.43, 2876.69, 2914.74, 2914.15, 2890.63, 2908.19, 2935.14, 2924.48, 2915.94, 2936.6, 2947.88, 2941.36, 2945.87, 2956.4, 2960.0]}, {"code": "6758", "name": "ソニーグループ", "side": "SHORT", "execution": "MARGIN", "entry": 3400, "current": 3210, "stop": 3290, "quantity": 100, "risk": 120, "status": "V-LOCK", "score": 89, "signal": "DOWNTREND", "holding": "4 sessions", "entry_time": "SAMPLE D−4 / 09:30 JST", "pnl": 19000, "pct": 5.588235294117648, "r": 1.5833333333333333, "distance": 80, "distance_pct": 2.4922118380062304, "strategy": "SAMPLE / DOWNTREND", "trailing": "ACTIVE", "profit_lock": "SECURED", "series": [3400.0, 3396.64, 3386.32, 3373.96, 3380.86, 3380.05, 3352.19, 3345.98, 3368.15, 3353.5, 3316.19, 3328.89, 3352.33, 3317.42, 3287.68, 3317.96, 3326.17, 3279.83, 3270.22, 3303.56, 3290.53, 3249.98, 3258.73, 3278.75, 3253.63, 3231.07, 3243.54, 3244.75, 3224.6, 3217.69, 3218.0, 3210.0]}, {"code": "8306", "name": "三菱UFJフィナンシャルG", "side": "LONG", "execution": "CASH", "entry": 1800, "current": 1854, "stop": 1785, "quantity": 300, "risk": 60, "status": "TRAILING", "score": 85, "signal": "MOMENTUM", "holding": "3 sessions", "entry_time": "SAMPLE D−3 / 10:00 JST", "pnl": 16200, "pct": 3.0, "r": 0.9, "distance": 69, "distance_pct": 3.7216828478964405, "strategy": "SAMPLE / MOMENTUM", "trailing": "ACTIVE", "profit_lock": "NOT LOCKED", "series": [1800.0, 1803.13, 1802.77, 1801.4, 1809.66, 1814.06, 1804.93, 1806.64, 1822.53, 1820.01, 1806.16, 1817.32, 1833.84, 1821.19, 1811.13, 1831.08, 1839.99, 1821.62, 1821.62, 1843.1, 1841.39, 1825.93, 1835.11, 1849.92, 1842.17, 1835.7, 1846.74, 1852.15, 1846.88, 1848.23, 1853.19, 1854.0]}, {"code": "8035", "name": "東京エレクトロン", "side": "SHORT", "execution": "MARGIN", "entry": 25000, "current": 25400, "stop": 25900, "quantity": 100, "risk": 900, "status": "HOLDING", "score": 81, "signal": "PULLBACK", "holding": "2 sessions", "entry_time": "SAMPLE D−2 / 09:45 JST", "pnl": -40000, "pct": -1.6, "r": -0.4444444444444444, "distance": 500, "distance_pct": 1.968503937007874, "strategy": "SAMPLE / PULLBACK", "trailing": "INACTIVE", "profit_lock": "NOT LOCKED", "series": [25000.0, 25033.67, 25015.16, 24981.34, 25091.95, 25144.73, 24994.66, 25006.98, 25232.13, 25181.07, 24960.14, 25114.24, 25348.91, 25145.97, 24981.8, 25267.78, 25388.23, 25099.53, 25086.3, 25395.28, 25356.39, 25111.17, 25235.64, 25444.65, 25315.16, 25204.79, 25357.18, 25425.16, 25332.89, 25339.93, 25401.13, 25400.0]}, {"code": "9432", "name": "NTT", "side": "LONG", "execution": "CASH", "entry": 160, "current": 156, "stop": 152, "quantity": 1000, "risk": 8, "status": "HOLDING", "score": 78, "signal": "BASE WATCH", "holding": "1 session", "entry_time": "SAMPLE D−1 / 10:15 JST", "pnl": -4000, "pct": -2.5, "r": -0.5, "distance": 4, "distance_pct": 2.564102564102564, "strategy": "SAMPLE / BASE WATCH", "trailing": "INACTIVE", "profit_lock": "NOT LOCKED", "series": [160.0, 160.06, 159.65, 159.1, 159.84, 160.07, 158.49, 158.36, 160.11, 159.42, 157.21, 158.33, 160.18, 158.13, 156.43, 158.72, 159.55, 156.74, 156.38, 158.88, 158.29, 155.87, 156.73, 158.35, 156.95, 155.73, 156.84, 157.2, 156.13, 155.95, 156.25, 156.0]}, {"code": "9984", "name": "ソフトバンクグループ", "side": "SHORT", "execution": "MARGIN", "entry": 9800, "current": 9510, "stop": 9870, "quantity": 100, "risk": 400, "status": "TRAILING", "score": 76, "signal": "WEAKNESS", "holding": "5 sessions", "entry_time": "SAMPLE D−5 / 09:20 JST", "pnl": 29000, "pct": 2.9591836734693877, "r": 0.725, "distance": 360, "distance_pct": 3.7854889589905363, "strategy": "SAMPLE / WEAKNESS", "trailing": "ACTIVE", "profit_lock": "NOT LOCKED", "series": [9800.0, 9799.88, 9776.56, 9746.44, 9780.51, 9788.88, 9707.09, 9697.47, 9782.45, 9744.67, 9631.39, 9684.79, 9774.0, 9668.71, 9580.66, 9692.67, 9731.11, 9587.71, 9566.74, 9688.98, 9656.6, 9532.53, 9572.76, 9650.56, 9577.92, 9513.78, 9566.42, 9581.54, 9525.44, 9513.48, 9525.59, 9510.0]}]</script>
<script>
"use strict";
const samples=JSON.parse(document.getElementById("sample-data").textContent);
const byCode=Object.fromEntries(samples.map(p=>[p.code,p]));
const fmt=n=>Number(n).toLocaleString("en-US",{maximumFractionDigits:2});
const signed=(n,d=0)=>(n<0?"−":"+")+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const tone=p=>p.pnl<0?"negative":"positive";
const side=p=>'<span class="side '+p.side.toLowerCase()+'">'+p.side+'</span>';
const status=p=>'<span class="status '+p.status.toLowerCase()+'">'+p.status+'</span>'+(p.status==="V-LOCK"?'<span class="secured">PROFIT SECURED</span>':'');
const actions=(p,scope)=>'<div class="actions"><button data-action="detail" data-code="'+p.code+'" aria-label="'+scope+' '+p.code+' 詳細">詳細</button><button data-action="chart" data-code="'+p.code+'" aria-label="'+scope+' '+p.code+' チャート">チャート</button></div>';
document.querySelector("#screening tbody").innerHTML=samples.map((p,i)=>'<tr><td class="rank">'+String(i+1).padStart(2,"0")+'</td><td class="code">'+p.code+'</td><td>'+p.name+'</td><td>'+side(p)+'</td><td class="num score">'+p.score+'</td><td class="signal">'+p.signal+'</td><td>'+actions(p,"screening")+'</td></tr>').join("");
document.querySelector("#positions tbody").innerHTML=samples.map(p=>'<tr><td class="code">'+p.code+'</td><td>'+p.name+'</td><td>'+side(p)+'</td><td class="num">'+fmt(p.current)+'</td><td class="num pnl '+tone(p)+'">'+signed(p.pnl)+'</td><td class="num '+tone(p)+'">'+signed(p.pct,2)+'%</td><td class="num '+tone(p)+'">'+signed(p.r,2)+'R</td><td>'+status(p)+'</td><td class="sub">'+p.holding+'</td><td>'+actions(p,"positions")+'</td></tr>').join("");
const detailOverlay=document.getElementById("detail-overlay"),chartOverlay=document.getElementById("chart-overlay");
let activeOverlay=null,returnFocus=null;
function openOverlay(overlay,trigger){returnFocus=trigger;activeOverlay=overlay;overlay.hidden=false;document.getElementById("main").inert=true;document.body.style.overflow="hidden";overlay.querySelector('[data-close]').focus();}
function closeOverlay(){if(!activeOverlay)return;activeOverlay.hidden=true;activeOverlay=null;document.getElementById("main").inert=false;document.body.style.overflow="";if(returnFocus)returnFocus.focus();}
const pair=(a,b,c="")=>'<div><dt>'+a+'</dt><dd class="'+c+'">'+b+'</dd></div>';
function detail(p,trigger){
 document.getElementById("drawer").innerHTML='<div class="dialogtop"><span class="eyebrow">DEMO / SAMPLE DATA</span><button data-close aria-label="Close detail">Close ×</button></div><h2 class="dialogname" id="detail-name">'+p.code+'</h2><p class="company">'+p.name+'</p><div class="badges">'+side(p)+(p.status==="V-LOCK"?'<div>'+status(p)+'</div>':'')+'</div><div class="metrics '+tone(p)+'"><div><small>P/L · JPY</small><strong>'+signed(p.pnl)+'</strong></div><div><small>P/L %</small><strong>'+signed(p.pct,2)+'%</strong></div><div><small>Current R</small><strong>'+signed(p.r,2)+'R</strong></div></div><div class="block protection"><h3>CURRENT PROTECTION</h3><dl>'+pair("Current Stop","¥"+fmt(p.stop),"emphasis")+pair("Distance","¥"+fmt(p.distance)+" / "+p.distance_pct.toFixed(2)+"%")+pair("Trailing",p.trailing)+pair("Profit Lock",p.profit_lock,p.status==="V-LOCK"?"gold":"")+'</dl></div><div class="block"><h3>POSITION</h3><dl>'+pair("Execution",p.execution+" · SAMPLE")+pair("Entry","¥"+fmt(p.entry))+pair("Current","¥"+fmt(p.current))+pair("Quantity",fmt(p.quantity)+" shares")+'</dl><p class="note">Executionは架空例です。正式なLONGの執行方式を確定しません。</p></div><div class="block"><h3>TRADE</h3><dl>'+pair("Entry Time",p.entry_time)+pair("Holding Period",p.holding)+pair("Strategy",p.strategy)+'</dl></div><p class="note">NO ORDER EXECUTION · 架空のサンプルセッション</p>';
 openOverlay(detailOverlay,trigger);
}
function chart(p,trigger){
 const low=Math.min(...p.series,p.entry,p.stop),high=Math.max(...p.series,p.entry,p.stop),pad=(high-low)*.22;
 const min=low-pad,max=high+pad,y=v=>330-(v-min)/(max-min)*285;
 const points=p.series.map((v,i)=>(35+i*650/31).toFixed(2)+','+y(v).toFixed(2)).join(" ");
 const grid=Array.from({length:5},(_,i)=>{const v=min+(max-min)*i/4;return '<line x1="35" x2="685" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#253245"/><text x="35" y="'+(y(v)-7)+'" fill="#8290a6" font-size="10">'+fmt(v)+'</text>';}).join("");
 const line=(value,label,color,dash)=>'<g data-level="'+label+'" data-value="'+value+'"><line x1="35" x2="685" y1="'+y(value)+'" y2="'+y(value)+'" stroke="'+color+'" stroke-width="'+(label==="CURRENT STOP"?2:1)+'" stroke-dasharray="'+dash+'"/><text x="702" y="'+(y(value)-5)+'" fill="'+color+'" font-size="10" font-weight="700">'+label+'</text><text x="702" y="'+(y(value)+13)+'" fill="'+color+'" font-size="14">'+fmt(value)+'</text></g>';
 const svg='<svg viewBox="0 0 840 380" role="img" aria-label="'+p.code+' sample price chart"><title>'+p.name+' — fictional price series</title>'+grid+'<polyline data-series="PRICE" points="'+points+'" fill="none" stroke="#dce7f8" stroke-width="2.5" stroke-linejoin="round"/>'+line(p.entry,"ENTRY","#929fb7","5 5")+line(p.stop,"CURRENT STOP","#80b7ff","7 4")+'<circle cx="685" cy="'+y(p.current)+'" r="4" fill="#dce7f8"/>'+(p.status==="V-LOCK"?'<text data-v-lock="true" x="666" y="'+(y(p.stop)-10)+'" fill="#efcc7c" font-size="23" font-weight="700">V</text>':'')+'<text x="35" y="362" fill="#a5afc0" font-size="10">SAMPLE SERIES / START</text><text x="606" y="362" fill="#a5afc0" font-size="10">SAMPLE / END</text></svg>';
 document.getElementById("chart-modal").innerHTML='<div class="dialogtop"><div><div class="eyebrow">DEMO / SAMPLE DATA · NO ORDER EXECUTION</div><h2 id="chart-name">'+p.code+' / '+p.name+'</h2></div><button data-close aria-label="Close chart">Close ×</button></div>'+side(p)+'<div class="chartlegend"><span class="price">PRICE · '+fmt(p.current)+'</span><span class="entry">ENTRY · '+fmt(p.entry)+'</span><span class="stop">CURRENT STOP · '+fmt(p.stop)+'</span></div>'+svg+'<div class="chartfoot"><span>架空の価格系列 · JPY · 時間軸はサンプル観測順</span><span class="gold">'+(p.status==="V-LOCK"?"V · PROFIT SECURED":"")+'</span></div>';
 openOverlay(chartOverlay,trigger);
}
document.addEventListener("click",e=>{const b=e.target.closest("button");if(b?.hasAttribute("data-close"))return closeOverlay();if(b?.dataset.action){const p=byCode[b.dataset.code];if(b.dataset.action==="detail")detail(p,b);else chart(p,b);}});
[detailOverlay,chartOverlay].forEach(o=>o.addEventListener("click",e=>{if(e.target===o)closeOverlay();}));
document.addEventListener("keydown",e=>{if(!activeOverlay)return;if(e.key==="Escape"){e.preventDefault();closeOverlay();}else if(e.key==="Tab"){const all=activeOverlay.querySelectorAll("button");if(all.length===1){e.preventDefault();all[0].focus();}}});
</script>
</body></html>

````

## design_reference/quadrant_showcase.py

````text
"""QUADRANT / Q: isolated, fictional, offline read-only showcase.
Run with Python standard library only. Writes exactly one sibling HTML file.
"""
import json
import math
from pathlib import Path
from html.parser import HTMLParser

ROWS = [
    dict(code="7203", name="トヨタ自動車", side="LONG", execution="CASH", entry=2800, current=2960, stop=2890, quantity=200, risk=100, status="V-LOCK", score=92, signal="TREND CONTINUATION", holding="6 sessions", entry_time="SAMPLE D−6 / 09:15 JST"),
    dict(code="6758", name="ソニーグループ", side="SHORT", execution="MARGIN", entry=3400, current=3210, stop=3290, quantity=100, risk=120, status="V-LOCK", score=89, signal="DOWNTREND", holding="4 sessions", entry_time="SAMPLE D−4 / 09:30 JST"),
    dict(code="8306", name="三菱UFJフィナンシャルG", side="LONG", execution="CASH", entry=1800, current=1854, stop=1785, quantity=300, risk=60, status="TRAILING", score=85, signal="MOMENTUM", holding="3 sessions", entry_time="SAMPLE D−3 / 10:00 JST"),
    dict(code="8035", name="東京エレクトロン", side="SHORT", execution="MARGIN", entry=25000, current=25400, stop=25900, quantity=100, risk=900, status="HOLDING", score=81, signal="PULLBACK", holding="2 sessions", entry_time="SAMPLE D−2 / 09:45 JST"),
    dict(code="9432", name="NTT", side="LONG", execution="CASH", entry=160, current=156, stop=152, quantity=1000, risk=8, status="HOLDING", score=78, signal="BASE WATCH", holding="1 session", entry_time="SAMPLE D−1 / 10:15 JST"),
    dict(code="9984", name="ソフトバンクグループ", side="SHORT", execution="MARGIN", entry=9800, current=9510, stop=9870, quantity=100, risk=400, status="TRAILING", score=76, signal="WEAKNESS", holding="5 sessions", entry_time="SAMPLE D−5 / 09:20 JST"),
]
for p in ROWS:
    direction = 1 if p["side"] == "LONG" else -1
    change = direction * (p["current"] - p["entry"])
    p.update(pnl=change*p["quantity"], pct=change/p["entry"]*100,
             r=change/p["risk"], distance=abs(p["current"]-p["stop"]),
             distance_pct=abs(p["current"]-p["stop"])/p["current"]*100,
             strategy="SAMPLE / " + p["signal"],
             trailing="ACTIVE" if p["status"] in ("TRAILING", "V-LOCK") else "INACTIVE",
             profit_lock="SECURED" if p["status"] == "V-LOCK" else "NOT LOCKED")
    p["series"] = [round(p["entry"]+(p["current"]-p["entry"])*i/31
                        + math.sin(i*1.7)*p["risk"]*.23*math.sin(math.pi*i/31), 2)
                   for i in range(32)]

def audit_data():
    assert {p["code"] for p in ROWS} == {"7203","6758","8306","8035","9432","9984"}
    assert {p["status"] for p in ROWS} == {"HOLDING","TRAILING","V-LOCK"}
    assert {p["side"] for p in ROWS} == {"LONG","SHORT"}
    assert {p["execution"] for p in ROWS} == {"CASH","MARGIN"}
    assert any(p["pnl"] > 0 for p in ROWS) and any(p["pnl"] < 0 for p in ROWS)
    for p in ROWS:
        d = 1 if p["side"] == "LONG" else -1
        delta = d*(p["current"]-p["entry"])
        assert p["pnl"] == delta*p["quantity"]
        assert math.isclose(p["pct"], delta/p["entry"]*100)
        assert math.isclose(p["r"], delta/p["risk"])
        assert p["pnl"]*p["pct"] > 0 and p["pnl"]*p["r"] > 0
        assert p["distance"] == abs(p["current"]-p["stop"])
        assert math.isclose(p["distance_pct"], p["distance"]/p["current"]*100)
        assert d*(p["current"]-p["stop"]) > 0
        if p["status"] == "V-LOCK":
            assert p["pnl"] > 0 and d*(p["stop"]-p["entry"]) > 0
        assert p["series"][0] == p["entry"] and p["series"][-1] == p["current"]
    print("DATA INVARIANTS: PASS / 6 fictional positions")

TEMPLATE = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; font-src 'none'; media-src 'none'; object-src 'none'; frame-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'">
<title>QUADRANT / Q — READ ONLY SHOWCASE</title>
<style>
:root{color-scheme:dark;--bg:#0e1219;--panel:#141b26;--line:#293343;--text:#ecf0f6;--muted:#a5afc0;--blue:#80b7ff;--red:#ff8590;--green:#68dba5;--gold:#efcc7c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI","Yu Gothic UI",Meiryo,sans-serif}
button{font:inherit;color:var(--text);background:#202b3c;border:1px solid #3c4c62;border-radius:5px;padding:7px 12px;cursor:pointer}
button:hover{background:#30405a;border-color:#95a8c3}button:focus-visible{outline:2px solid var(--blue);outline-offset:3px}
header{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:15px;padding:19px 32px;background:#101620;border-bottom:1px solid var(--line)}
.brand{font-size:23px;letter-spacing:3px;font-weight:700}.ro{font-size:11px;letter-spacing:2px;color:var(--muted);margin-left:20px}
.safety{display:flex;gap:12px;flex-wrap:wrap;font-size:11px;font-weight:700;letter-spacing:1.5px}.demo{color:var(--gold);border:1px solid #685736;padding:5px 10px}.noorder{padding:5px 0;color:var(--muted)}
main{max-width:1520px;margin:auto;padding:28px 32px 40px}.intro{display:flex;justify-content:space-between;gap:20px;align-items:baseline;margin-bottom:24px}
h1{font-size:25px;font-weight:500;margin:0 0 5px}p{margin:0;color:var(--muted)}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--muted);margin-bottom:7px}
section{margin-bottom:28px}.sectionhead{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px}
h2{font-size:15px;letter-spacing:1.8px;margin:0;font-weight:650}.sub{color:var(--muted);font-size:12px}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:8px;background:var(--panel)}
table{width:100%;border-collapse:collapse;white-space:nowrap}th{text-align:left;font-size:10px;color:var(--muted);letter-spacing:1.2px;font-weight:500;background:#18202d;padding:12px 16px}
td{padding:13px 16px;border-top:1px solid var(--line);font-size:13px}tbody tr:hover{background:#1a2433}.num{text-align:right;font-variant-numeric:tabular-nums}.code{font-weight:700;letter-spacing:.6px}
.rank{color:var(--muted);font-size:12px}.side{display:inline-block;min-width:62px;text-align:center;border:1px solid;border-radius:4px;padding:3px 8px;font-size:11px;font-weight:700;letter-spacing:1px}
.long{color:var(--blue);border-color:#598ac2}.short{color:var(--red);border-color:#ba5965}.positive{color:var(--green)}.negative{color:var(--red)}.pnl{font-weight:650}
.status{font-size:11px;letter-spacing:.7px;font-weight:650}.holding{color:#c2cada}.trailing{color:var(--blue)}.v-lock,.gold{color:var(--gold)}.secured{display:block;font-size:8px;letter-spacing:1px;color:var(--gold);margin-top:2px}
.actions{display:flex;gap:7px}.actions button{padding:5px 10px;font-size:12px}.score{font-size:17px;font-weight:650}.signal{font-size:10px;letter-spacing:.5px;color:#c2ccdc}
.legend{display:flex;gap:22px;font-size:11px;color:var(--muted);margin-top:12px;flex-wrap:wrap}footer{border-top:1px solid var(--line);padding-top:16px;font-size:11px;color:var(--muted)}
.overlay{position:fixed;inset:0;background:#05080ec9;z-index:20}.overlay[hidden]{display:none}.drawer{position:absolute;right:0;top:0;bottom:0;width:min(460px,100%);overflow:auto;background:#151d29;border-left:1px solid #415169;padding:25px 28px}
.dialogtop{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}.dialogtop .eyebrow{margin:0}.dialogname{font-size:23px;letter-spacing:1px;margin:0 0 4px}.company{font-size:16px;margin:0 0 15px}
.badges{display:flex;align-items:center;gap:15px;margin-bottom:24px}.metrics{display:grid;grid-template-columns:1.25fr 1fr 1fr;gap:8px;padding:17px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.metrics small{display:block;color:var(--muted);font-size:10px;margin-bottom:5px}.metrics strong{font-size:21px;font-variant-numeric:tabular-nums;white-space:nowrap}
.block{margin-top:24px}.block h3{font-size:11px;letter-spacing:1.6px;color:var(--muted);margin:0 0 12px}.protection{padding:16px;border:1px solid #52677d;border-radius:6px;background:#1b2939}
dl{margin:0}dl>div{display:flex;justify-content:space-between;gap:16px;padding:7px 0}dt{color:var(--muted);font-size:12px}dd{margin:0;text-align:right;font-size:13px}dd.emphasis{font-size:20px;font-weight:650;color:var(--blue)}
.note{font-size:10px;color:var(--muted);margin-top:12px;line-height:1.7}.modal{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:min(960px,94vw);max-height:92vh;overflow:auto;padding:25px;background:#151d29;border:1px solid #43536c;border-radius:10px}
.chartlegend{display:flex;gap:22px;margin:18px 0;font-size:11px;flex-wrap:wrap}.chartlegend span:before{content:"";display:inline-block;width:20px;height:2px;background:currentColor;margin:0 7px 3px 0}.price{color:#dce7f8}.entry{color:#929fb7}.stop{color:var(--blue);font-weight:700}
svg{display:block;width:100%;height:auto;background:#101823;border:1px solid var(--line);border-radius:6px}
.modal .chartfoot{display:flex;justify-content:space-between;margin-top:12px;gap:15px;font-size:11px;color:var(--muted)}
@media(max-width:760px){header{padding:14px 16px;align-items:flex-start;flex-direction:column;gap:8px}.brand{font-size:19px}.ro{margin-left:12px}main{padding:22px 16px}.intro{display:block}.intro .sub{margin-top:8px}td,th{padding:12px}.sectionhead{gap:10px}.metrics strong{font-size:18px}.drawer{padding:20px}.modal{padding:16px}}
</style>
</head>
<body>
<header><div><span class="brand">QUADRANT / Q</span><span class="ro">READ ONLY</span></div><div class="safety"><span class="demo">DEMO / SAMPLE DATA</span><span class="noorder">NO ORDER EXECUTION</span></div></header>
<main id="main">
<div class="intro"><div><div class="eyebrow">QUADRANT READ ONLY SHOWCASE</div><h1>候補とポジションを、一目で。</h1><p>すべて架空のサンプルです。実市場価格・実績を示すものではありません。</p></div><span class="sub">OFFLINE / SAMPLE SESSION</span></div>
<section aria-labelledby="screen-title"><div class="sectionhead"><h2 id="screen-title">MORNING SCREENING</h2><span class="sub">朝の候補 · SAMPLE / 6 CANDIDATES</span></div>
<div class="tablewrap"><table id="screening"><thead><tr><th>RANK</th><th>CODE</th><th>NAME</th><th>SIDE</th><th class="num">SCORE</th><th>SIGNAL</th><th>操作</th></tr></thead><tbody></tbody></table></div></section>
<section aria-labelledby="positions-title"><div class="sectionhead"><h2 id="positions-title">POSITIONS</h2><span class="sub">6 SAMPLE POSITIONS · JPY</span></div>
<div class="tablewrap"><table id="positions"><thead><tr><th>CODE</th><th>NAME</th><th>SIDE</th><th class="num">CURRENT</th><th class="num">P/L</th><th class="num">P/L %</th><th class="num">R</th><th>STATUS</th><th>HOLDING</th><th>操作</th></tr></thead><tbody></tbody></table></div>
<div class="legend"><span>HOLDING · 保有中</span><span>TRAILING · ストップ追随中</span><span class="gold">V-LOCK · PROFIT SECURED</span><span>損益は価格差による架空の評価損益</span></div></section>
<footer>DEMO / SAMPLE DATA · NO ORDER EXECUTION<br>CASH / MARGINはサンプル表示です。正式なLONGの執行方式を確定するものではありません。</footer>
</main>
<div id="detail-overlay" class="overlay" hidden><aside id="drawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="detail-name" tabindex="-1"></aside></div>
<div id="chart-overlay" class="overlay" hidden><div id="chart-modal" class="modal" role="dialog" aria-modal="true" aria-labelledby="chart-name" tabindex="-1"></div></div>
<script id="sample-data" type="application/json">__DATA__</script>
<script>
"use strict";
const samples=JSON.parse(document.getElementById("sample-data").textContent);
const byCode=Object.fromEntries(samples.map(p=>[p.code,p]));
const fmt=n=>Number(n).toLocaleString("en-US",{maximumFractionDigits:2});
const signed=(n,d=0)=>(n<0?"−":"+")+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const tone=p=>p.pnl<0?"negative":"positive";
const side=p=>'<span class="side '+p.side.toLowerCase()+'">'+p.side+'</span>';
const status=p=>'<span class="status '+p.status.toLowerCase()+'">'+p.status+'</span>'+(p.status==="V-LOCK"?'<span class="secured">PROFIT SECURED</span>':'');
const actions=(p,scope)=>'<div class="actions"><button data-action="detail" data-code="'+p.code+'" aria-label="'+scope+' '+p.code+' 詳細">詳細</button><button data-action="chart" data-code="'+p.code+'" aria-label="'+scope+' '+p.code+' チャート">チャート</button></div>';
document.querySelector("#screening tbody").innerHTML=samples.map((p,i)=>'<tr><td class="rank">'+String(i+1).padStart(2,"0")+'</td><td class="code">'+p.code+'</td><td>'+p.name+'</td><td>'+side(p)+'</td><td class="num score">'+p.score+'</td><td class="signal">'+p.signal+'</td><td>'+actions(p,"screening")+'</td></tr>').join("");
document.querySelector("#positions tbody").innerHTML=samples.map(p=>'<tr><td class="code">'+p.code+'</td><td>'+p.name+'</td><td>'+side(p)+'</td><td class="num">'+fmt(p.current)+'</td><td class="num pnl '+tone(p)+'">'+signed(p.pnl)+'</td><td class="num '+tone(p)+'">'+signed(p.pct,2)+'%</td><td class="num '+tone(p)+'">'+signed(p.r,2)+'R</td><td>'+status(p)+'</td><td class="sub">'+p.holding+'</td><td>'+actions(p,"positions")+'</td></tr>').join("");
const detailOverlay=document.getElementById("detail-overlay"),chartOverlay=document.getElementById("chart-overlay");
let activeOverlay=null,returnFocus=null;
function openOverlay(overlay,trigger){returnFocus=trigger;activeOverlay=overlay;overlay.hidden=false;document.getElementById("main").inert=true;document.body.style.overflow="hidden";overlay.querySelector('[data-close]').focus();}
function closeOverlay(){if(!activeOverlay)return;activeOverlay.hidden=true;activeOverlay=null;document.getElementById("main").inert=false;document.body.style.overflow="";if(returnFocus)returnFocus.focus();}
const pair=(a,b,c="")=>'<div><dt>'+a+'</dt><dd class="'+c+'">'+b+'</dd></div>';
function detail(p,trigger){
 document.getElementById("drawer").innerHTML='<div class="dialogtop"><span class="eyebrow">DEMO / SAMPLE DATA</span><button data-close aria-label="Close detail">Close ×</button></div><h2 class="dialogname" id="detail-name">'+p.code+'</h2><p class="company">'+p.name+'</p><div class="badges">'+side(p)+(p.status==="V-LOCK"?'<div>'+status(p)+'</div>':'')+'</div><div class="metrics '+tone(p)+'"><div><small>P/L · JPY</small><strong>'+signed(p.pnl)+'</strong></div><div><small>P/L %</small><strong>'+signed(p.pct,2)+'%</strong></div><div><small>Current R</small><strong>'+signed(p.r,2)+'R</strong></div></div><div class="block protection"><h3>CURRENT PROTECTION</h3><dl>'+pair("Current Stop","¥"+fmt(p.stop),"emphasis")+pair("Distance","¥"+fmt(p.distance)+" / "+p.distance_pct.toFixed(2)+"%")+pair("Trailing",p.trailing)+pair("Profit Lock",p.profit_lock,p.status==="V-LOCK"?"gold":"")+'</dl></div><div class="block"><h3>POSITION</h3><dl>'+pair("Execution",p.execution+" · SAMPLE")+pair("Entry","¥"+fmt(p.entry))+pair("Current","¥"+fmt(p.current))+pair("Quantity",fmt(p.quantity)+" shares")+'</dl><p class="note">Executionは架空例です。正式なLONGの執行方式を確定しません。</p></div><div class="block"><h3>TRADE</h3><dl>'+pair("Entry Time",p.entry_time)+pair("Holding Period",p.holding)+pair("Strategy",p.strategy)+'</dl></div><p class="note">NO ORDER EXECUTION · 架空のサンプルセッション</p>';
 openOverlay(detailOverlay,trigger);
}
function chart(p,trigger){
 const low=Math.min(...p.series,p.entry,p.stop),high=Math.max(...p.series,p.entry,p.stop),pad=(high-low)*.22;
 const min=low-pad,max=high+pad,y=v=>330-(v-min)/(max-min)*285;
 const points=p.series.map((v,i)=>(35+i*650/31).toFixed(2)+','+y(v).toFixed(2)).join(" ");
 const grid=Array.from({length:5},(_,i)=>{const v=min+(max-min)*i/4;return '<line x1="35" x2="685" y1="'+y(v)+'" y2="'+y(v)+'" stroke="#253245"/><text x="35" y="'+(y(v)-7)+'" fill="#8290a6" font-size="10">'+fmt(v)+'</text>';}).join("");
 const line=(value,label,color,dash)=>'<g data-level="'+label+'" data-value="'+value+'"><line x1="35" x2="685" y1="'+y(value)+'" y2="'+y(value)+'" stroke="'+color+'" stroke-width="'+(label==="CURRENT STOP"?2:1)+'" stroke-dasharray="'+dash+'"/><text x="702" y="'+(y(value)-5)+'" fill="'+color+'" font-size="10" font-weight="700">'+label+'</text><text x="702" y="'+(y(value)+13)+'" fill="'+color+'" font-size="14">'+fmt(value)+'</text></g>';
 const svg='<svg viewBox="0 0 840 380" role="img" aria-label="'+p.code+' sample price chart"><title>'+p.name+' — fictional price series</title>'+grid+'<polyline data-series="PRICE" points="'+points+'" fill="none" stroke="#dce7f8" stroke-width="2.5" stroke-linejoin="round"/>'+line(p.entry,"ENTRY","#929fb7","5 5")+line(p.stop,"CURRENT STOP","#80b7ff","7 4")+'<circle cx="685" cy="'+y(p.current)+'" r="4" fill="#dce7f8"/>'+(p.status==="V-LOCK"?'<text data-v-lock="true" x="666" y="'+(y(p.stop)-10)+'" fill="#efcc7c" font-size="23" font-weight="700">V</text>':'')+'<text x="35" y="362" fill="#a5afc0" font-size="10">SAMPLE SERIES / START</text><text x="606" y="362" fill="#a5afc0" font-size="10">SAMPLE / END</text></svg>';
 document.getElementById("chart-modal").innerHTML='<div class="dialogtop"><div><div class="eyebrow">DEMO / SAMPLE DATA · NO ORDER EXECUTION</div><h2 id="chart-name">'+p.code+' / '+p.name+'</h2></div><button data-close aria-label="Close chart">Close ×</button></div>'+side(p)+'<div class="chartlegend"><span class="price">PRICE · '+fmt(p.current)+'</span><span class="entry">ENTRY · '+fmt(p.entry)+'</span><span class="stop">CURRENT STOP · '+fmt(p.stop)+'</span></div>'+svg+'<div class="chartfoot"><span>架空の価格系列 · JPY · 時間軸はサンプル観測順</span><span class="gold">'+(p.status==="V-LOCK"?"V · PROFIT SECURED":"")+'</span></div>';
 openOverlay(chartOverlay,trigger);
}
document.addEventListener("click",e=>{const b=e.target.closest("button");if(b?.hasAttribute("data-close"))return closeOverlay();if(b?.dataset.action){const p=byCode[b.dataset.code];if(b.dataset.action==="detail")detail(p,b);else chart(p,b);}});
[detailOverlay,chartOverlay].forEach(o=>o.addEventListener("click",e=>{if(e.target===o)closeOverlay();}));
document.addEventListener("keydown",e=>{if(!activeOverlay)return;if(e.key==="Escape"){e.preventDefault();closeOverlay();}else if(e.key==="Tab"){const all=activeOverlay.querySelectorAll("button");if(all.length===1){e.preventDefault();all[0].focus();}}});
</script>
</body></html>
'''

class AuditHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.external = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ("src", "href", "action", "srcset"):
            if key in a:
                self.external.append((tag, key, a[key]))
        assert tag not in ("iframe", "form", "object", "embed", "link")

def main():
    audit_data()
    html = TEMPLATE.replace("__DATA__", json.dumps(ROWS, ensure_ascii=False))
    parser = AuditHTML()
    parser.feed(html)
    assert not parser.external
    for forbidden in ("fetch(", "XMLHttpRequest", "WebSocket", "http://", "https://",
                      "Initial Stop", "TODAY", "LIVE", "onclick="):
        assert forbidden not in html, forbidden
    assert "connect-src 'none'" in html
    target = Path(__file__).resolve().with_name("quadrant_showcase.html")
    target.write_text(html, encoding="utf-8")
    assert target.read_text(encoding="utf-8") == html
    print("HTML / ISOLATION STATIC AUDIT: PASS")
    print(target)

if __name__ == "__main__":
    main()


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


## 追加回収資料

[画像・UI一覧](VISUAL_DESIGN_INDEX.md) / [回収した詳細仕様](RECOVERED_UI_SPEC.md)

四神獣＋金色麒麟はdesign_assets/stage6.jpg。修正版UI添付の表示HTMLとV-LOCKチャートSVGをdesign_referenceへ追加。表示HTMLはブラウザーDOMの保存であり元添付とのbyte一致は未証明。独立Vロゴの原画像は未回収。旧DEMO案と修正版を一覧で区別。

````

## recovered_history/browser_1.txt

````text
過去のメッセージを読み込み中…
10月1日(木) 6:53
あなたの発言:
つくって
分析エラー
分析済み
ChatGPT の発言:

そうです。今回は元のQUADRANT画面を基準に、スマホでアプリのようにタップ操作する版として作り直しました。
phoenix_q_p7_integrated_margin_…

今回は、

下部ナビ PORTFOLIO / SCREEN / HISTORY / ANALYTICS
ポジションをタップ → 全画面詳細
LONG青枠 / SHORT赤枠
利益緑 / 損失赤
金V-LOCK
HOLD / TRAIL / V-LOCK
Current Stop / Distance / Execution / Entry / Current
詳細内チャート
Morning Screeningから銘柄タップ → 同じ詳細画面

まで操作できるようにしています。 

QUADRANT_Q_MOBILE_DEMO.html
HTML
あなたの発言:
いや、動かんけど
ChatGPT の発言:

その通り。原因ははっきりしています。

私がまた「HTMLファイルをChatGPTのファイルプレビューで開けば、SafariのWebアプリと同じようにJavaScriptが動く」と扱ってしまった。
見た目は表示できても、そこでタップ用JavaScriptが実行されなければ、PORTFOLIOや詳細画面は動きません。コードを直すだけでは解決しない問題です。

今回必要なのはHTMLファイルではなく、Safariから普通のWebサイトとしてアクセスできるURLです。

つまり完成形は、

iPhone → Safari → https://... → QUADRANT起動 → タブ/銘柄/詳細/チャートをタップ操作

です。

ここから同じHTMLファイルを何度作り直しても意味がないので止めます。次は公開URLを持つWebアプリとして作る経路に切り替えます。Codexは使いません。

あなたの発言:
そ!をやれって
ChatGPT の発言:

そうです。公開URLまで作るという意味です。

ただし、いま確認したところ、このチャットにある実行環境には Webサイトを外部公開して https://... を発行するデプロイ機能がありません。ここでまたHTMLを渡して「できました」とするのは同じ失敗なのでやりません。

現在できているのはQモバイル版のWebアプリ本体まで。次に必要なのは外部ホスティングへのデプロイです。あなたのWindows側を操作できる接続手段があれば、私がそこから公開まで実行できます。

この作業に使えるPC接続（Remote Desktop Commander等）が現在使えない状態なので、このチャット単体から公開URLそのものを発行するところだけは実行不能です。ここは誤魔化しません。

あなたの発言:
PCできるから早く出して
ChatGPT の発言:

PCでやるなら最短で出せます。
ただ、公開先を勝手に決めるとまたズレるので一点だけ。

前にブラウザで開いていたやつと同じ方法で公開するなら、そのサービス名だけ教えて。
例：GitHub Pages / Netlify / Cloudflare Pages など。

サービス名が分からなければ、PC画面のスクショを1枚送ってください。そこから特定して、DEMO-Qを公開URLにする操作だけ出します。

あなたの発言:
ただしこれは現物買い版
ChatGPT の発言:

これで分かりました。前に使っていたのは Tailscale の *.ts.net 経路です。
同じ方式で出せます。公開するなら Tailscale Funnel が該当します。
Tailscale
+1

そして画像の現物買い版をコピーするのではなく、現在確定しているQ仕様（LONG/SHORT・V-LOCK・TRAILING・詳細・チャート）を、この既存QUADRANTのスマホUIに載せるのが今回の正解です。

PCで PowerShell を開いて、まずこれだけ実行してください。

powershell
tailscale funnel status

出てきた結果をそのまま貼ってください。

これだけは必要です。スクショのURLが途中省略されているため、既存Funnelのホスト名・転送先を私が推測して上書きするのは危険です。

既存構成を確認したら、次は私が 既存QUADRANTを壊さず、DEMO-Qを別経路で公開するための確定コマンドだけ出します。
Tailscale公式でもFunnelはWindowsから公開でき、tailscale funnel の出力にそのままiPhoneで開ける https://*.ts.net URLが出ます。
Tailscale
+1

Tailscale Funnel公式ドキュメント

あなたの発言:

ashtc@masaki-gaming MINGW64 /c/dev/PHOENIX (main)
$ tailscale funnel status
https://masaki-gaming.tailb86d1f.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:5177
(.venv)
ashtc@masaki-gaming MINGW64 /c/dev/PHOENIX (main)
$

ChatGPT の発言:

確認できた。既存Qは 5177 番で稼働中なので、そこは触らない。
しかも現在の表示は (tailnet only) なので、これは Funnel ではなくTailscale内限定の既存経路です。Tailscaleは --set-path で別パスを追加できるので、既存 / を壊さず DEMO-Q を分離できます。
Tailscale
+1

ただし今の目的は、まずあなたのiPhoneから確実に開くこと。既存Qと同じTailscale環境を使って、/demo-q だけ追加します。

Git BashでPHOENIXから出て、以下をそのまま実行してください。

Bash
mkdir -p /c/dev/DEMO-Q
cd /c/dev/DEMO-Q

次に、さっき私が作ったファイルをPCに保存して C:\dev\DEMO-Q\index.html に置きます。

保存したら名前を index.html にしてください。

その後、Git Bashでこれだけ実行します。

Bash
cd /c/dev/DEMO-Q
python -m http.server 5188 --bind 127.0.0.1

このターミナルは閉じずにそのまま。別のGit Bashを開いて、

Bash
tailscale serve --set-path=/demo-q --bg http://127.0.0.1:5188
tailscale serve status

公式仕様上、--set-path は既存ルートとは別のURLパスをマウントできます。
Tailscale

最後にiPhone Safariで、

DEMO-Qを開く

です。

5177の既存QUADRANT / は変更しません。PHOENIXも変更しません。OneDriveも使いません。

なお、今見せてもらった旧版は現物LONG前提なので、今回のデモはその画面構造を土台にしつつ、現在のQ仕様である LONG/SHORT、CASH/MARGIN分離、TRAILING、V-LOCK、Current Stop中心の詳細へ置き換える対象です。

QUADRANT_Q_MOBILE_DEMO.html
HTML
あなたの発言:
私が作ったファイルはない
ChatGPT の発言:

そう。言い方が間違っていました。あなたが作ったファイルはありません。DEMO-Q本体は私が作ったファイルです。

PC側にまだ存在しないので、まずこれをPCへ保存します。

PCでリンクを開いて保存するとき、保存先を

プレーンテキスト
C:\dev\DEMO-Q\index.html

にしてください。DEMO-Q フォルダがなければ作成します。

その後だけ、Git Bashで：

Bash
cd /c/dev/DEMO-Q
python -m http.server 5188 --bind 127.0.0.1

これでPC上のDEMO-Qが起動します。まだ5177の既存Qには一切触りません。

ここまでできたら、私が次に既存Qを壊さず https://masaki-gaming.tailb86d1f.ts.net/demo-q/ へ載せるところまで続けます。

QUADRANT_Q_MOBILE_DEMO.html
HTML
ChatGPT は間違えることがあります。重要な情報は確認してください。
最新の応答




思考量
Instant
````

## RECOVERED_UI_SPEC.md

````text
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
from vermilion_readonly import VermilionReadOnlyAdapter

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
VERMILION = VermilionReadOnlyAdapter.from_environment()


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


def attach_vermilion(state: dict[str, Any]) -> dict[str, Any]:
    """制度信用LONG (VERMILION) runner state -> Q display. Read only; RSS cash holdings stay as they are."""
    prices = {p.get("ticker"): p.get("last") for p in state.get("positions", []) if p.get("last")}
    prices.update({w.get("ticker"): w.get("price") for w in state.get("watchlist", []) if w.get("price")})
    try:
        vermilion = VERMILION.snapshot(prices)
    except Exception as exc:  # display must never break the snapshot
        vermilion = {"available": False, "mode": "ERROR", "error": str(exc)[:200], "positions": [], "planned": [], "events": []}
    for row in state.get("positions", []):
        row.setdefault("execution", "CASH" if row.get("account_type") in ("特定", "一般", "NISA") else "NOT_PROVEN")
        row.setdefault("side", "LONG" if row.get("execution") == "CASH" else "NOT_PROVEN")
    if vermilion.get("mode") == "LIVE":
        state["positions"] = list(state.get("positions", [])) + vermilion["positions"]
    state["vermilion"] = vermilion
    state.setdefault("system", {})["vermilion"] = vermilion.get("mode", "NOT_CONNECTED") if vermilion.get("available") else "NOT_CONNECTED"
    return state


async def build_state(step: int = 0) -> dict[str, Any]:
    if DATA_SOURCE == "mock":
        return await asyncio.to_thread(attach_vermilion, build_mock_state(step))
    try:
        state = await asyncio.to_thread(RSS_ADAPTER.snapshot)
    except RssReadOnlyUnavailable as exc:
        state = rss_unavailable_state(str(exc))
    state = await asyncio.to_thread(attach_phoenix_analysis, state)
    return await asyncio.to_thread(attach_vermilion, state)


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


def _margin_value(values: dict[str, Any], names: tuple[str, ...]) -> float | None:
    """First present, numeric value among `names`; '－' (margin account not opened) -> None."""
    for name in names:
        text = _as_text(values.get(name))
        if text and text not in ("－", "-", "ー"):
            try:
                return float(text.replace(",", ""))
            except ValueError:
                return None
    return None


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
            # 信用余力は「自動振替含む」列で判定する（信用口座単体は0になり得る: 2026-10-25 実機確認）
            "margin_power": _margin_value(values, ("自動振替含む_信用新規建余力", "信用口座_信用新規建余力")),
            "margin_ratio": _margin_value(values, ("自動振替含む_保証金率(新規建)", "信用口座_保証金率(新規建)")),
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

## source/QUADRANT_TERMINAL_v0.4.0/backend/vermilion_readonly.py

````text
"""VERMILION (制度信用LONG) read-only adapter for Q.

Reads the margin-LONG runner state written by PHOENIX `run_margin_long.py`
(state/margin_long/live when it exists, otherwise state/margin_long/shadow).
Display only: never writes, never imports order code, never changes gates.
Missing/invalid data is shown as NOT_PROVEN, never guessed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

STALE_SECONDS = 36 * 3600  # state is updated at least every trading day (EOD)
MAX_HOLD_SESSIONS = 40


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _tail_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _gate_flags(phoenix_root: Path) -> dict[str, str]:
    """Static read of the release gates in source (display only)."""
    gates = {"route": "NOT_PROVEN", "broker_live": "NOT_PROVEN", "armed": "NOT_PROVEN"}
    try:
        text = (phoenix_root / "phoenix_core" / "rakuten_rss_long_margin.py").read_text(encoding="utf-8")
        gates["route"] = "CLOSED" if "LONG_MARGIN_ROUTE_RELEASED = False" in text else "OPEN"
    except OSError:
        pass
    try:
        text = (phoenix_root / "run_margin_long.py").read_text(encoding="utf-8")
        gates["broker_live"] = "CLOSED" if "    live = False\n" in text else "OPEN"
        gates["armed"] = "CLOSED" if "armed=False" in text else "OPEN"
    except OSError:
        pass
    return gates


class VermilionReadOnlyAdapter:
    def __init__(self, phoenix_root: Path) -> None:
        self.root = phoenix_root.resolve()
        self.base = self.root / "state" / "margin_long"

    @classmethod
    def from_environment(cls) -> "VermilionReadOnlyAdapter":
        default = Path(__file__).resolve().parents[2]
        return cls(Path(os.environ.get("QUADRANT_PHOENIX_ROOT", str(default))))

    def _source_dir(self) -> tuple[str, Path] | None:
        for mode in ("live", "shadow"):
            directory = self.base / mode
            if (directory / "state.json").exists():
                return mode.upper(), directory
        return None

    def snapshot(self, last_prices: dict[str, float] | None = None) -> dict[str, Any]:
        last_prices = last_prices or {}
        gates = _gate_flags(self.root)
        found = self._source_dir()
        if found is None:
            return {"available": False, "mode": "NOT_CONNECTED", "gates": gates, "positions": [], "planned": [],
                    "events": [], "updated_at": "", "stale": True}
        mode, directory = found
        state = _read_json(directory / "state.json") or {}
        meta = _read_json(directory / "meta.json") or {}
        try:
            mtime = datetime.fromtimestamp((directory / "state.json").stat().st_mtime)
        except OSError:
            mtime = None
        stale = mtime is None or (datetime.now() - mtime).total_seconds() > STALE_SECONDS
        positions = []
        pending = state.get("pending_closes", {}) or {}
        for ticker, p in (state.get("positions", {}) or {}).items():
            try:
                entry = float(p["entry_price"]); r = float(p["initial_r"]); qty = int(p["quantity"])
                eff = float(p["effective_stop"]); pend = float(p.get("pending_stop", eff)); init = float(p["initial_stop"])
            except (KeyError, TypeError, ValueError):
                positions.append({"ticker": ticker, "side": "LONG", "execution": "MARGIN", "status": "NOT_PROVEN",
                                  "qty": 0, "avg_price": 0, "last": 0, "pnl": 0, "pnl_pct": 0, "source": mode})
                continue
            last = last_prices.get(ticker)
            status = ("EXIT_PENDING" if ticker in pending or p.get("time_exit_due")
                      else "TRAILING" if eff > init + 1e-9 else "HOLDING")
            row = {
                "ticker": ticker, "side": "LONG", "execution": "MARGIN", "status": status, "source": mode,
                "engine": "VERMILION", "qty": qty, "avg_price": round(entry, 2),
                "initial_stop": round(init, 2), "current_stop": round(eff, 2),
                "pending_stop": round(max(pend, eff), 2), "initial_r": round(r, 2),
                "held_sessions": int(p.get("held_sessions", 0)), "max_hold_sessions": MAX_HOLD_SESSIONS,
                "time_exit_due": bool(p.get("time_exit_due")), "open_date": str(p.get("open_date", "")),
                "locked_r": round((eff - entry) / r, 2) if r > 0 else None,
            }
            if isinstance(last, (int, float)) and last > 0:
                row.update(last=float(last), pnl=round((last - entry) * qty), pnl_pct=round((last / entry - 1) * 100, 2),
                           current_r=round((last - entry) / r, 2) if r > 0 else None, market_value=round(last * qty))
            else:
                row.update(last=0, pnl=0, pnl_pct=0, current_r=None, price_status="NOT_PROVEN")
            # V-LOCK (display): the stop already protects a profit at or above entry
            row["v_lock_display"] = "ACTIVE" if eff >= entry else "INACTIVE"
            positions.append(row)
        planned = [{"ticker": x.get("ticker"), "quantity": x.get("quantity"), "limit_price": x.get("limit_price"),
                    "signal_date": x.get("signal_date"), "submitted": bool(x.get("client_order_id"))}
                   for x in state.get("planned", []) or []]
        events = []
        for e in _tail_jsonl(directory / "shadow_log.jsonl")[-40:]:
            level = "ERROR" if e.get("result") in ("ERROR",) else "WARN" if e.get("result") == "RSS_UNAVAILABLE" else "INFO"
            text = e.get("result") or ""
            for key in ("paper_open", "paper_close", "entry_skipped_gap"):
                if key in e:
                    text = f"{key} {e[key]} {e.get('price', e.get('open', ''))} {e.get('reason', '')}".strip()
            if e.get("job") == "eod" and "planned" in e:
                text = f"EOD {e.get('session', '')} planned {len(e['planned'])}"
            events.append({"time": str(e.get("at", ""))[11:19], "level": level, "message": f"[{e.get('job', '')}] {text}"[:160]})
        reports = sorted(directory.glob("report_*.html"))
        return {
            "available": True, "mode": mode, "gates": gates, "positions": positions, "planned": planned,
            "events": events, "equity_paper": meta.get("equity"), "last_eod": meta.get("last_eod", ""),
            "updated_at": mtime.isoformat(timespec="seconds") if mtime else "", "stale": stale,
            "latest_report": reports[-1].name if reports else "",
        }

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
import type { ChartPayload, ChartTimeframe, PhoenixSnapshot, Position, RankingItem, VermilionState, WatchItem } from "./types";

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
  const selectedProtection = useMemo(
    () => state.positions.find((item) => item.ticker === selectedItem?.ticker && item.engine === "VERMILION")
      ?? state.vermilion?.positions.find((item) => item.ticker === selectedItem?.ticker),
    [selectedItem?.ticker, state.positions, state.vermilion],
  );
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
                {state.account.margin_power != null
                  ? <MetricCard label="信用新規建余力" value={moneyView(state.account.margin_power)} sub={`現物買付可能額 ${moneyView(state.account.buying_power)}`} />
                  : <MetricCard label="現物買付可能額" value={moneyView(state.account.buying_power)} sub="BUYING POWER · 信用余力 NOT_PROVEN" />}
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
                {state.vermilion?.mode === "SHADOW" && state.vermilion.positions.length ? <>
                  <div className="section-heading vermilion-subheading"><div><small>VERMILION · SHADOW</small><h2>影運用ポジション（紙上・注文なし）</h2></div><div className="heading-actions"><span>{state.vermilion.positions.length}銘柄</span></div></div>
                  <div className="holdings-list">
                    {state.vermilion.positions.map((position) => <HoldingCard key={`shadow-${position.ticker}`} position={position} masked={balancesHidden} onOpen={() => openSummary(position.ticker)} />)}
                  </div>
                </> : null}
              </div>

              <div className="panel section-card side-insight">
                <div className="section-heading"><div><small>AT A GLANCE</small><h2>今日の状況</h2></div></div>
                {analysisAvailable && ranked.length ? <div className="glance-score"><span>VERMILION TOP SCORE</span><strong>{ranked[0]?.score ?? "--"}</strong><small>{ranked[0]?.ticker.replace(".T", "")} · {ranked[0]?.name}</small></div> : <div className="analysis-offline-card"><b>PHOENIX ANALYSIS</b><strong>NOT CONNECTED</strong><p>口座情報はREALでも、ランキング/スコアは偽装せず非表示にします。</p></div>}
                <button type="button" className="primary-link" onClick={() => setTab("ranking")} disabled={!analysisAvailable}>本日の狙い目を見る <span>→</span></button>
                <VermilionCard vermilion={state.vermilion} masked={balancesHidden} />
                <div className="read-only-note"><b>READ ONLY · SHORT {state.meta?.short_runtime ?? "NOT_CONNECTED"}</b><p>このUIには発注・訂正・取消の権限を持たせていません。</p></div>
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
              {selectedProtection ? <div className="detail-strip panel protection-strip">
                <div><span>区分</span><strong>{selectedProtection.side} · {selectedProtection.execution}{selectedProtection.source === "SHADOW" ? " · 紙上" : ""}</strong></div>
                <div><span>現在STOP</span><strong>{selectedProtection.current_stop != null ? `¥${num(selectedProtection.current_stop, 1)}` : "NOT_PROVEN"}</strong></div>
                <div><span>次回STOP（翌営業日から有効）</span><strong>{selectedProtection.pending_stop != null ? `¥${num(selectedProtection.pending_stop, 1)}` : "—"}</strong></div>
                <div><span>状態</span><strong className={selectedProtection.status === "EXIT_PENDING" ? "negative" : ""}>{selectedProtection.status ?? "NOT_PROVEN"}</strong></div>
                <div><span>現在R / 確保R</span><strong>{selectedProtection.current_r != null ? signed(selectedProtection.current_r) : "—"}R / {selectedProtection.locked_r != null ? signed(selectedProtection.locked_r) : "—"}R</strong></div>
                <div><span>保有</span><strong>{selectedProtection.held_sessions ?? 0} / {selectedProtection.max_hold_sessions ?? 40}日</strong></div>
                <div><span>V-LOCK</span><strong>{selectedProtection.v_lock_display ?? "NOT_PROVEN"}</strong></div>
              </div> : null}
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

function VermilionCard({ vermilion, masked }: { vermilion?: VermilionState; masked: boolean }) {
  if (!vermilion || !vermilion.available) {
    return <div className="vermilion-card offline"><b>VERMILION · 制度信用LONG</b><strong>{vermilion?.mode ?? "NOT_CONNECTED"}</strong><p>運用状態ファイルが見つかりません。推測値は表示しません。</p></div>;
  }
  const gates = vermilion.gates ?? { route: "NOT_PROVEN", broker_live: "NOT_PROVEN", armed: "NOT_PROVEN" };
  const allClosed = [gates.route, gates.broker_live, gates.armed].every((g) => g === "CLOSED");
  return (
    <div className={`vermilion-card ${vermilion.mode === "LIVE" ? "live" : "shadow"}`}>
      <div className="vermilion-head"><b>VERMILION · 制度信用LONG</b><em>{vermilion.mode === "SHADOW" ? "影運用（注文なし）" : vermilion.mode}</em></div>
      <div className="vermilion-gates" aria-label="発注ゲート">
        <span className={gates.route === "CLOSED" ? "closed" : "open"}>ROUTE {gates.route}</span>
        <span className={gates.broker_live === "CLOSED" ? "closed" : "open"}>LIVE {gates.broker_live}</span>
        <span className={gates.armed === "CLOSED" ? "closed" : "open"}>ARMED {gates.armed}</span>
      </div>
      <p className="vermilion-note">{allClosed ? "全ゲート閉: 実注文は送信されません。" : "ゲートが開いています。解禁手順どおりか確認してください。"}</p>
      <div className="vermilion-stats">
        <div><span>保有</span><strong>{vermilion.positions.length}</strong></div>
        <div><span>翌営業日候補</span><strong>{vermilion.planned.length}</strong></div>
        <div><span>{vermilion.mode === "SHADOW" ? "紙上資産" : "最終EOD"}</span><strong>{vermilion.mode === "SHADOW" ? (masked || vermilion.equity_paper == null ? "••••" : money(vermilion.equity_paper)) : (vermilion.last_eod || "—")}</strong></div>
      </div>
      {vermilion.planned.length ? <ul className="vermilion-plan">{vermilion.planned.slice(0, 6).map((p) => <li key={p.ticker}><span>{p.ticker.replace(".T", "")}</span><small>{p.quantity}株 · 上限 {num(p.limit_price, 1)}</small><em>{p.submitted ? "寄付指値" : "予定"}</em></li>)}</ul> : null}
      <small className={`vermilion-updated ${vermilion.stale ? "stale" : ""}`}>{vermilion.stale ? "STALE · " : ""}更新 {vermilion.updated_at ? vermilion.updated_at.replace("T", " ") : "—"}{vermilion.last_eod ? ` · EOD ${vermilion.last_eod}` : ""}</small>
    </div>
  );
}

function HoldingCard({ position, item, masked, onOpen }: { position: Position; item?: WatchItem; masked: boolean; onOpen: () => void }) {
  return (
    <button type="button" className="holding-card" onClick={onOpen}>
      <div className="holding-symbol"><span>{position.ticker.replace(".T", "")}</span><small>{position.name ?? item?.name ?? position.ticker}</small>{position.account_type ? <em>{position.account_type}</em> : null}</div>
      <div className="holding-quote"><strong>{num(position.last, 1)}</strong><small>{item ? signed(item.change_pct, "%") : "NOT_PROVEN"}</small></div>
      <div className="holding-position"><span>{position.qty}株</span><small>平均 {masked ? "••••" : `¥${num(position.avg_price, 1)}`}</small></div>
      <div className="holding-pnl"><strong className={tone(position.pnl)}>{masked ? "••••••" : money(position.pnl)}</strong><small className={tone(position.pnl_pct)}>{masked ? "••••" : signed(position.pnl_pct, "%")}</small></div>
      <div className="holding-score">
        <small>{position.execution ?? "NOT_PROVEN"}{position.source === "SHADOW" ? " · PAPER" : ""}</small>
        <strong>{position.side || "NOT_PROVEN"}</strong>
        {position.engine === "VERMILION" ? <small className={`stop-chip ${position.status === "TRAILING" ? "trailing" : position.status === "EXIT_PENDING" ? "exit" : ""}`}>{position.status} · STOP {position.current_stop != null ? num(position.current_stop, 1) : "—"}</small> : null}
      </div>
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

/* VERMILION (制度信用LONG) — read-only status, uses existing tokens */
.vermilion-card { border: 1px solid var(--line); border-radius: 14px; padding: 14px; margin: 12px 0; display: grid; gap: 10px; background: var(--panel-2); }
.vermilion-card.offline strong { color: var(--muted); }
.vermilion-card.live { border-color: var(--accent); }
.vermilion-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 4px 8px; }
.vermilion-head b { white-space: nowrap; }
.vermilion-head b { letter-spacing: .06em; font-size: 12px; color: var(--accent); }
.vermilion-head em { font-style: normal; font-size: 12px; color: var(--muted); }
.vermilion-gates { display: flex; flex-wrap: wrap; gap: 6px; }
.vermilion-gates span { font-size: 11px; padding: 3px 8px; border-radius: 999px; border: 1px solid var(--line); }
.vermilion-gates span.closed { color: var(--positive); border-color: color-mix(in srgb, var(--positive) 45%, transparent); }
.vermilion-gates span.open { color: var(--negative); border-color: var(--negative); font-weight: 700; }
.vermilion-note { margin: 0; font-size: 12px; color: var(--muted); }
.vermilion-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.vermilion-stats div { display: grid; gap: 2px; }
.vermilion-stats span { font-size: 11px; color: var(--muted); }
.vermilion-plan { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
.vermilion-plan li { display: grid; grid-template-columns: 60px 1fr auto; gap: 8px; font-size: 12px; align-items: center; }
.vermilion-plan small { color: var(--muted); }
.vermilion-plan em { font-style: normal; color: var(--accent-2); font-size: 11px; }
.vermilion-updated { font-size: 11px; color: var(--muted-2); }
.vermilion-updated.stale { color: var(--warning); }
.vermilion-subheading { margin-top: 18px; }
.stop-chip { font-size: 10px; color: var(--muted); white-space: nowrap; }
.stop-chip.trailing { color: var(--positive); }
.stop-chip.exit { color: var(--negative); }
.protection-strip { margin-top: 10px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.protection-strip > div { border-bottom: 1px solid var(--line-soft); }

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
  /** 信用新規建余力（自動振替含む）。信用口座未開設/未取得は null */
  margin_power?: number | null;
  /** 保証金率（新規建） */
  margin_ratio?: number | null;
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
  /** VERMILION 制度信用LONG（runner state 由来） */
  engine?: "VERMILION" | string;
  source?: "LIVE" | "SHADOW" | string;
  initial_stop?: number;
  pending_stop?: number;
  initial_r?: number;
  locked_r?: number | null;
  held_sessions?: number;
  max_hold_sessions?: number;
  time_exit_due?: boolean;
  open_date?: string;
  price_status?: "NOT_PROVEN" | string;
}

export type GateState = "CLOSED" | "OPEN" | "NOT_PROVEN" | string;

export interface VermilionPlan {
  ticker: string;
  quantity: number;
  limit_price: number;
  signal_date?: string;
  submitted?: boolean;
}

export interface VermilionState {
  available: boolean;
  mode: "LIVE" | "SHADOW" | "NOT_CONNECTED" | "ERROR" | string;
  gates?: { route: GateState; broker_live: GateState; armed: GateState };
  positions: Position[];
  planned: VermilionPlan[];
  events: EventRow[];
  equity_paper?: number;
  last_eod?: string;
  updated_at?: string;
  stale?: boolean;
  latest_report?: string;
  error?: string;
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
  vermilion?: VermilionState;
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

## VISUAL_DESIGN_INDEX.md

````text
# Q UI ビジュアル成果物

## 核となる4+1：四神獣＋中央の金色麒麟

![四神獣と金色麒麟の最終段階](design_assets/stage6.jpg)

[原画像 stage6.jpg](design_assets/stage6.jpg) — q_assets_exact.zipから回収した既存画像。

## 進行段階6枚

|1|2|3|
|---|---|---|
|![1](design_assets/stage1.jpg)|![2](design_assets/stage2.jpg)|![3](design_assets/stage3.jpg)|
|4：四神獣＋Q|5：中央麒麟の移行段階|6：金色麒麟|
|![4](design_assets/stage4.jpg)|![5](design_assets/stage5.jpg)|![6](design_assets/stage6.jpg)|

## UI・トレールの完成像

[修正版UIの表示HTML](design_reference/corrected_index_rendered.html) — 10月1日07:14添付をブラウザーで開き、表示DOMを回収。元ダウンロードファイルとのbyte一致は未証明。デザイン参照用のサンプル表示であり、本番稼働証明ではない。

![修正版HOME](design_reference/corrected_ui_home.jpg)

![V-LOCKチャート](design_reference/corrected_ui_v_lock_chart.jpg)

[V-LOCKチャートのSVG](design_reference/corrected_ui_v_lock_chart.svg)

[画面構成、金縁カード、トレール、V、Market Briefの詳細仕様](RECOVERED_UI_SPEC.md)

[既存Q保有画面の会話ビューアー記録](design_reference/existing_q_positions_capture.jpg)

## 回収したHTMLの履歴

- [POSITIONS・詳細・CHART・V-LOCKの検討画面](design_reference/quadrant_showcase.html)
- [上記の生成元Python](design_reference/quadrant_showcase.py)
- [モバイル検討案](design_reference/QUADRANT_Q_MOBILE_DEMO.html)

これらの旧DEMO案は最終承認UIではない。モバイル案の英語ナビは拒否され、上の修正版でQの既存日本語UIと金縁カードに戻された。独立したVロゴ原画像は未回収。上のV画像は回収した修正版チャートの表示記録とSVGであり、独立Vロゴの代替原本とは称しない。

````
