import yfinance as yf

tickers = {
    "トヨタ": "7203.T",
    "ソニー": "6758.T",
    "アップル": "AAPL",
    "マイクロソフト": "MSFT"
}

for name, code in tickers.items():
    stock = yf.Ticker(code)
    info = stock.info

    print("----------------")
    print("会社:", name)
    print("現在価格:", info.get("currentPrice"))
    print("通貨:", info.get("currency"))