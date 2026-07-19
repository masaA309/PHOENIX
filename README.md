# PHOENIX v6.9.1 Learning Engine Compatibility Update

Paper Traderの決済履歴を条件別に集計し、統計的な強化候補・抑制候補を作ります。

## 追加ファイル

- `learning_engine.py`
- `config/learning_config.json`
- `tests/verify_learning_engine.py`

## 自動入力

次の順番でCSVを探します。

1. `reports/paper_learning_data.csv`
2. `reports/paper_trades.csv`

明示指定もできます。

```bash
python learning_engine.py --input reports/paper_learning_data.csv
```

## 実行

```bash
python learning_engine.py
```

## 出力

- `reports/learning_summary.csv`
- `reports/learning_statistics.csv`
- `reports/learning_adjustments.json`
- `reports/learning_report.txt`

CSVとTXTはWindowsで文字化けしにくいUTF-8 BOM付きです。

## 検証

```bash
python tests/verify_learning_engine.py
```

## 学習の安全条件

- 最低サンプル数未満は補正ゼロ
- 期待値とProfit Factorの両方を評価
- 補正値には上限あり
- 実売買へ直接接続しない
- v6.9では「学習結果の生成」まで
- AI判定への接続は、Paper Trade検証後の次段階

## phoenix.pyへの登録

現行の`phoenix.py`構造を確認せずに自動上書きすると既存機能を壊す可能性があるため、
このパッケージでは上書きしません。まず単体実行と検証を完了してください。


## v6.9.1追加対応

現在のPHOENIXが出力する次の日本語列名へ正式対応しました。

- 取引ID
- AI判断点
- PHOENIX_SCORE
- RSI
- MACD判定
- 出来高倍率
- 地合い
- 保有日数
- 損益額
- 損益率%
- 勝敗
- エントリー理由
- 決済理由
