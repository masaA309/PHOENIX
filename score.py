# score.py

def calculate_score(data):

    score = 0
    reasons = []

    # ============================
    # 上昇率
    # ============================
    change = data["前日比%"]

    if change >= 5:
        score += 35
        reasons.append("前日比 +5%以上")

    elif change >= 3:
        score += 30
        reasons.append("前日比 +3%以上")

    elif change >= 1:
        score += 15
        reasons.append("前日比 +1%以上")

    # ============================
    # 出来高
    # ============================
    volume_ratio = data["出来高倍率"]

    if volume_ratio >= 5:
        score += 35
        reasons.append("出来高 5倍以上")

    elif volume_ratio >= 3:
        score += 30
        reasons.append("出来高 3倍以上")

    elif volume_ratio >= 2:
        score += 20
        reasons.append("出来高 2倍以上")

    elif volume_ratio >= 1.5:
        score += 10
        reasons.append("出来高 1.5倍以上")

    # ============================
    # トレンド
    # ============================
    if data["トレンド"] == "UP":
        score += 20
        reasons.append("25日線より上")

    # ============================
    # 移動平均
    # ============================
    ma5 = data["MA5"]
    ma25 = data["MA25"]

    if ma5 > ma25:
        score += 15
        reasons.append("MA5 > MA25")

    ma75 = data.get("MA75")

    if (
        ma75 is not None
        and ma25 > ma75
    ):
        score += 10
        reasons.append("MA25 > MA75")

    # ============================
    # RSI
    # ============================
    rsi = data["RSI"]

    if 40 <= rsi <= 70:
        score += 10
        reasons.append(f"RSI {rsi}")

    elif rsi < 30:
        score += 5
        reasons.append(f"RSI 売られすぎ ({rsi})")

    # ============================
    # MACD
    # ============================
    if data["MACD判定"] == "BUY":
        score += 10
        reasons.append("MACD BUY")

    # ============================
    # ゴールデンクロス
    # ============================
    if data["ゴールデンクロス"]:
        score += 15
        reasons.append("ゴールデンクロス")

    # ============================
    # 上限
    # ============================
    score = min(score, 100)

    return {
        "PHOENIX_SCORE": score,
        "理由": " / ".join(reasons)
    }