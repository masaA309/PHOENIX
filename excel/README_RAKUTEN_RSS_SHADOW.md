# 楽天MARKETSPEED II RSS 読み取り専用シャドー接続

Step20は、発注機能を一切持たないExcelブックから相場情報だけを受け取る契約です。Excel 365導入後も、確認が終わるまでは `rss_implementation_ready` と `session_capture_enabled` を `false` のままにします。

## アプリ・Excel・VBAの関係

- MARKETSPEED IIアプリは起動・ログインして、RSSへ相場情報を供給します。アプリ名、実行ファイル、楽天ID、パスワードをVBAへ入力しません。
- Excelには、Officeの32/64bitに合う `MarketSpeed2_RSS_32bit.xll` または `MarketSpeed2_RSS_64bit.xll` と、`MarketSpeed2_RSS_VBA.xlam` を楽天公式手順どおり登録します。
- ExcelセルのMARKETSPEED II RSS関数が価格・気配・出来高・更新日時を受け取り、PHOENIXのVBAはそのセルを読み取り専用CSVへ出力します。
- PHOENIXの初期版には注文、訂正、取消のRSS関数を入れません。認証情報も保存しません。

## Excel導入後チェックリスト

1. Excel 365のデスクトップ版とbit数を確認する。
2. MARKETSPEED IIを最新版にし、ログインとRSS利用可否を確認する。
3. 上記2種類の公式アドインをExcelへ登録し、RSS関数が表示されることを確認する。
4. 1銘柄だけで現在値が更新される読み取り試験を行う。
5. マクロ有効ブックを `runtime\v7_rss_shadow\` に作り、AutoSaveを無効にする。
6. `PHOENIX_RSS_SHADOW_V1.bas` をインポートし、注文関数がないことを目視監査する。
7. 20～225銘柄へ拡張し、時刻・bid/ask・出来高・取引状態を検査する。
8. attestation、3回のshadow capture、Dry Run、レポート確認を順に行う。

## 明日の導入手順

1. MARKETSPEED IIへログインし、RSS機能が有効な状態でExcelを開きます。
2. PHOENIXの `runtime\v7_rss_shadow\PHOENIX_RSS_SHADOW.xlsm` にマクロ有効ブックを保存し、AutoSaveを無効にします。ブックはGit管理しません。
3. `RSS_SHADOW` シートを作り、1行目を `ticker,current_price,bid,ask,volume,trading_status,quote_timestamp,bid_timestamp,ask_timestamp` とします。2行目以降に20～225銘柄を置きます。
4. A列は `1605.T` 形式、B～I列はMARKETSPEED II RSSの市況情報関数またはその参照セルにします。F列は `OPEN`、`TRADING`、`取引中`、`通常` のいずれかに正規化し、G～I列はRSSが返した更新日時をExcel日時として保持します。VBAの現在時刻で代用しません。
5. `PHOENIX_CONTROL` シートを作り、B2へ `0` を入れます。B2～B4は当該Excelセッション内の連番・capture ID・出力時刻表示用で、ブックへ保存する必要はありません。連番の基準は2020年からの経過秒なので、翌日も巻き戻りません。
6. VBAエディターで `PHOENIX_RSS_SHADOW_V1.bas` をインポートします。マクロ一覧から `ExportPhoenixRssShadowSnapshot` を手動実行します。
7. ブックを保存してVBA、全シート、定義名、外部リンク、RSS関数を監査し、Excelを完全に閉じます。その後、次のattestationを1回実行します。2つの確認オプションは、実際に目視確認した場合だけ付けます。

```powershell
python -X utf8 rss_shadow_entry_v7.py --attest-workbook --confirm-vba-source-import --confirm-no-order-functions
```

8. ブックを再度開き、AutoSaveを無効のままにします。CSVを出力した後、同じWindowsセッションで次を実行します。attestation後はブックを上書き保存しません。

```powershell
python -X utf8 rss_shadow_entry_v7.py --publish-current
```

正常なら `reports/v7_rss_shadow_contract.txt` が `READY` になります。保存済みブックが変わった場合はattestationが無効になり、再監査するまで `NOT_READY` になります。

1取引日をshadow sessionとして記録するには、同じ日に少なくとも3回（例: 9:30、11:00、15:00）、各回でVBA出力と `--publish-current` を実行します。最初と最後は4時間以上離し、朝のcaptureと14:30以降のcaptureを含めます。各manifestは上書きせず保存され、3回すべてが候補全銘柄を含む場合だけ1日として認定できます。

## 安全契約

- VBAには市況情報の読取りとCSV出力しかありません。
- 注文、訂正、取消、信用取引、外部送信、Shell、PowerShell呼出しを追加してはいけません。
- `execution/rss_order_queue.csv` およびブローカーstateへ書き込みません。
- CSVは同一フォルダの一時ファイルからatomic replacementし、Python側で列、型、JST時刻、鮮度、銘柄集合、SHA-256、連番を再検証します。
- 11:30～12:30、休日、古い値、未来時刻、重複銘柄、不完全な候補集合、単発snapshotだけの観測は `NOT_READY` です。
- 実ブック (`.xlsm/.xlsx`) と一時ファイルはGit管理対象外です。

## 観測日を記録する前の手動監査

- 実ブックにインポートしたVBAが追跡中の `.bas` と一致する。
- ブック内に発注・訂正・取消のRSS関数、外部送信、認証情報がない。
- 20候補すべてのRSS値と更新日時が変化する。
- `python -X utf8 rss_shadow_entry_v7.py --dry-run` がbroker state、注文キュー、shadow stateを変更しない。

この確認後に限り、別コミットで2つのフラグを有効化します。自動では変更しません。
