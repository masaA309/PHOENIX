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
