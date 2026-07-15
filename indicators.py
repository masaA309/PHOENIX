# indicators.py

import pandas as pd


def calc_rsi(close, period=14):

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()

    rs = avg_gain / avg_loss

    rsi = 100 - (100 / (1 + rs))

    return rsi


def calc_macd(close):

    ema12 = close.ewm(
        span=12,
        adjust=False
    ).mean()

    ema26 = close.ewm(
        span=26,
        adjust=False
    ).mean()

    macd = ema12 - ema26

    signal = macd.ewm(
        span=9,
        adjust=False
    ).mean()

    return macd, signal


def calc_score(close, volume):

    if len(close) < 75:
        return None

    price = float(close.iloc[-1])
    prev = float(close.iloc[-2])

    change = (
        (price - prev)
        / prev
        * 100
    )

    avg_volume = volume.iloc[-6:-1].mean()

    if avg_volume == 0:
        volume_ratio = 0
    else:
        volume_ratio = (
            volume.iloc[-1]
            / avg_volume
        )

    ma5 = close.iloc[-5:].mean()
    ma25 = close.iloc[-25:].mean()
    ma75 = close.iloc[-75:].mean()

    rsi_series = calc_rsi(close)
    rsi = float(
        rsi_series.iloc[-1]
    )

    macd, signal = calc_macd(close)

    macd_now = float(
        macd.iloc[-1]
    )

    signal_now = float(
        signal.iloc[-1]
    )

    macd_prev = float(
        macd.iloc[-2]
    )

    signal_prev = float(
        signal.iloc[-2]
    )

    score = 0
    reasons = []

    # ------------------------
    # 前日比
    # ------------------------

    if change >= 5:
        score += 25
        reasons.append(
            "前日比 +5%以上"
        )

    elif change >= 3:
        score += 20
        reasons.append(
            "前日比 +3%以上"
        )

    elif change >= 1:
        score += 10
        reasons.append(
            "前日比 +1%以上"
        )

    # ------------------------
    # 出来高
    # ------------------------

    if volume_ratio >= 5:
        score += 30
        reasons.append(
            "出来高 5倍以上"
        )

    elif volume_ratio >= 3:
        score += 25
        reasons.append(
            "出来高 3倍以上"
        )

    elif volume_ratio >= 2:
        score += 20
        reasons.append(
            "出来高 2倍以上"
        )

    elif volume_ratio >= 1.5:
        score += 10
        reasons.append(
            "出来高 1.5倍以上"
        )

    # ------------------------
    # トレンド
    # ------------------------

    if price > ma25:
        score += 10
        reasons.append(
            "25日線より上"
        )

    if ma5 > ma25:
        score += 5
        reasons.append(
            "MA5 > MA25"
        )

    if ma25 > ma75:
        score += 5
        reasons.append(
            "MA25 > MA75"
        )

    # ------------------------
    # RSI
    # ------------------------

    if 50 <= rsi <= 70:
        score += 15
        reasons.append(
            f"RSI {rsi:.2f}"
        )

    elif 70 < rsi <= 80:
        score += 8
        reasons.append(
            f"RSI {rsi:.2f}"
        )

    elif 30 <= rsi < 50:
        score += 5
        reasons.append(
            f"RSI {rsi:.2f}"
        )

    elif rsi < 30:
        score += 5
        reasons.append(
            f"RSI 売られすぎ {rsi:.2f}"
        )

    elif rsi > 80:
        score -= 10
        reasons.append(
            f"RSI 過熱 {rsi:.2f}"
        )

    # ------------------------
    # MACD
    # ------------------------

    macd_judge = "SELL"

    if macd_now > signal_now:
        score += 10
        macd_judge = "BUY"
        reasons.append(
            "MACD BUY"
        )

    if (
        macd_now > signal_now
        and
        macd_prev <= signal_prev
    ):
        score += 5
        reasons.append(
            "MACD GC"
        )

    # ------------------------
    # スコア補正
    # ------------------------

    score = max(score, 0)
    score = min(score, 100)

    return {
        "score": score,
        "change": round(change, 2),
        "volume_ratio": round(volume_ratio, 2),
        "ma5": round(ma5, 2),
        "ma25": round(ma25, 2),
        "ma75": round(ma75, 2),
        "rsi": round(rsi, 2),
        "macd_judge": macd_judge,
        "reason": " / ".join(reasons)
    }