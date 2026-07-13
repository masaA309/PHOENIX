import yfinance as yf
import matplotlib.pyplot as plt

ticker = "7203.T"  # トヨタ

data = yf.download(ticker, period="1y")

plt.figure(figsize=(10, 5))
plt.plot(data.index, data["Close"])
plt.title("Toyota Stock Price")
plt.xlabel("Date")
plt.ylabel("Price (JPY)")
plt.grid(True)

plt.show()