# 四神獣 / SHISHIN TERMINAL v0.3.0

PC版とiPhone版を同じReactコードで動かす **read-only prototype** です。

## 四神獣

- 朱雀 / PHOENIX — 日本株
- 青龍 / SEIRYU — FX
- 白虎 / BYAKKO — XAU/USD
- 玄武 / GENBU — US INDEX

売買エンジンは統合しません。SHISHINは共通UI / 切替レイヤーだけです。

## v0.3.0（スマホ版）

- iPhone縦画面を正式レイアウト化
- 上部3タブを常時固定
  - 保有株式一覧
  - 個別サマリー
  - 本日の狙い目
- 右上 `☰` の設定ドロワーをスマホでは全幅シート化
- 四神獣切替を指で押しやすいサイズへ変更
- 保有一覧 / ランキングをスマホ向けカード配置へ最適化
- 銘柄タップ時の押下フィードバックを追加
- 個別サマリーの銘柄切替を横スワイプ可能に変更
- iPhone safe-area / Dynamic Island / ホームインジケータ領域を考慮
- 自動 / ライト / ダークを維持
- PWA manifest / Home Screen icon / service workerを追加
- iPhoneからPCへ接続できるようAPI接続先を `127.0.0.1` 固定から「画面を開いたPCホスト」へ変更
- ViteをLANアクセス可能な `0.0.0.0:1420` で待受
- read-only backendはPrivate LANのオリジンのみ許可

## 重要な境界

この版にもbrokerへの発注・訂正・取消・約定変更ルートはありません。
HTTP routeはGET/HEADのみで、UI authorityは `NONE` のままです。

## PCだけでUI確認

Git Bash:

```bash
cd SHISHIN_TERMINAL_v0.3.0/frontend
npm install
npm run dev
```

PCでは通常 `http://127.0.0.1:1420/` で確認できます。
バックエンドを起動しなければLOCAL MOCK表示です。

## iPhoneで見る（同じWi-Fi）

### 1. 上側Git Bash — read-only backend

```bash
cd SHISHIN_TERMINAL_v0.3.0/backend
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8765
```

### 2. 下側Git Bash — frontend

```bash
cd SHISHIN_TERMINAL_v0.3.0/frontend
npm install
npm run dev
```

Viteの表示に `Network: http://192.168.x.x:1420/` のようなURLが出ます。
PCとiPhoneを同じWi-Fiにつないだ状態で、その **Network URL** をiPhoneのSafariで開きます。

Windows Defender Firewallの確認が出た場合は、家庭内LANで使う場合だけ「プライベート ネットワーク」を許可してください。パブリックネットワークやルーターのポート開放は不要です。

## iPhoneのホーム画面に置く

SafariでSHISHINを開き、

`共有` → `ホーム画面に追加`

でSHISHINアイコンから起動できます。

## 操作確認

1. 上の四神獣スイッチから朱雀 / 青龍 / 白虎 / 玄武を切り替える。
2. 上部の3タブで保有 / 個別 / 狙い目を切り替える。
3. 保有株やランキング行をタップすると個別サマリーへ移動する。
4. 個別サマリーの銘柄ボタンは左右にスワイプできる。
5. `☰` → 外観から自動 / ライト / ダークを変更する。
6. 画面下部にREAD ONLY状態が常時表示されることを確認する。

## 検証済み

- Python syntax: PASS
- FastAPI `/health`: PASS
- FastAPI `/api/v1/snapshot`: PASS
- WebSocket `/ws/v1/state`: PASS
- HTTP methods: GET / HEAD only
- manifest / JSON parse: PASS

この実行環境ではnpm dependency取得がタイムアウトしたため、最終 `npm run build` はWindows側で実施してください。
