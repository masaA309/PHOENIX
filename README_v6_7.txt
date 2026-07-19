PHOENIX v6.7 Performance Analyzer 完全差し替えパッケージ

追加/差し替え:
- performance_analyzer.py（新規）
- config/performance_config.json（新規）
- phoenix.py（完全差し替え）
- compile_all.py（PowerShell対応の一括構文検査）

重要:
- 初期資金 300,000円
- ChatGPT Plus 3,000円/月
- Excel 3,000円/月
- 固定費合計 6,000円/月を最初から評価
- 特定口座（源泉徴収あり）税率20.315%を概算表示
- 税金は利益がプラスの月だけ概算
- 50取引以上、PF 1.5以上、勝率55%以上、最大DD10%以下、コスト後プラス月3回で増資判定PASS

使い方:
1. PHOENIXルートへ中身を上書き
2. python compile_all.py
3. python performance_analyzer.py
4. python phoenix.py --list
5. python phoenix.py --only performance_analyzer

既存 reports/paper_trades.csv が無くても安全に初期レポートを作成します。
