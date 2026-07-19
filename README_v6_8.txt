PHOENIX v6.8 Paper Trader Pro

導入:
1. ZIPを展開
2. paper_trader.py と config フォルダをPHOENIXルートへ上書き
3. 次を実行

python compile_all.py
python phoenix.py --only paper_trader
python phoenix.py --only performance_analyzer

主な追加機能:
- 初期資金30万円に対応
- 最大保有数と1銘柄上限を設定ファイル化
- AI判断点・PHOENIX SCOREによる新規条件
- 利確・損切り・最大保有日数による自動決済
- スリッページ・手数料を損益へ反映
- 利用可能現金を考慮した株数計算
- RSI、MACD、出来高倍率、地合い、理由を学習データへ保存
- Performance Analyzerが読む reports/paper_trades.csv と互換

注意:
既存 reports/paper_trades.csv は削除せず、そのまま引き継ぎます。
最初の実行前にGitの状態を確認してください。
