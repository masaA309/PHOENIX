# technical.py

import pandas as pd


def calculate_ma(close):

    ma5 = float(close.tail(5).mean())
    ma25 = float(close.tail(25).mean())
    ma75 = float(close.tail(75).mean()) if len(close) >= 75 else None

    return {
        "MA5": round(ma5, 2),
        "MA25": round(ma25, 2),
        "MA75": round(ma75, 2) if ma75 else None
    }


def calculate_rsi(close, period=14):

    delta = close.diff()

    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    if pd.isna(avg_loss.iloc[-1]) or avg_loss.iloc[-1] == 0:
        return 100.0

    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1]
    rsi = 100 - (100 / (1 + rs))

    return round(float(rsi), 2)


def calculate_macd(close):

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    macd_value = round(float(macd.iloc[-1]), 2)
    signal_value = round(float(signal.iloc[-1]), 2)

    trend = (
        "BUY"
        if macd.iloc[-1] > signal.iloc[-1]
        else "SELL"
    )

    return {
        "MACD": macd_value,
        "SIGNAL": signal_value,
        "MACD判定": trend
    }


def check_golden_cross(close):

    ma5 = close.rolling(5).mean()
    ma25 = close.rolling(25).mean()

    if len(ma25.dropna()) < 2:
        return False

    before = (
        ma5.iloc[-2] <= ma25.iloc[-2]
    )

    now = (
        ma5.iloc[-1] > ma25.iloc[-1]
    )

    return before and now


def get_technical_data(close):

    ma = calculate_ma(close)
    rsi = calculate_rsi(close)
    macd = calculate_macd(close)
    golden = check_golden_cross(close)

    latest = float(close.iloc[-1])

    trend = (
        "UP"
        if latest > ma["MA25"]
        else "DOWN"
    )

    return {
        "MA5": ma["MA5"],
        "MA25": ma["MA25"],
        "MA75": ma["MA75"],
        "RSI": rsi,
        "MACD": macd["MACD"],
        "SIGNAL": macd["SIGNAL"],
        "MACD判定": macd["MACD判定"],
        "ゴールデンクロス": golden,
        "トレンド": trend
    }