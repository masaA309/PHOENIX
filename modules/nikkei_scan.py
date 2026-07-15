# ======================================
# PHOENIX Market Scanner
# 日経225スキャン
# ======================================

import yfinance as yf
import pandas as pd


# 日経225銘柄リスト
# 後で自動取得化可能
NIKKEI225 = [
    "7203.T",  # トヨタ
    "6758.T",  # ソニー
    "9984.T",  # ソフトバンクG
    "8306.T",  # 三菱UFJ
    "6861.T",  # キーエンス
    "8035.T",  # 東京エレクトロン
]


def get_stock_data(code):

    try:

        stock = yf.Ticker(code)

        data = stock.history(
            period="5d"
        )

        if len(data) < 2:
            return None


        today = data.iloc[-1]
        yesterday = data.iloc[-2]


        price = today["Close"]

        change = (
            (price - yesterday["Close"])
            /
            yesterday["Close"]
            *
            100
        )


        volume = today["Volume"]


        return {

            "code": code,

            "price": round(price,2),

            "change": round(change,2),

            "volume": int(volume)

        }


    except Exception as e:

        print(
            code,
            "ERROR",
            e
        )

        return None



def scan_market():

    results=[]


    for code in NIKKEI225:

        data=get_stock_data(code)

        if data:
            results.append(data)


    df=pd.DataFrame(results)


    if df.empty:
        return {}


    market={

        "stocks":results,

        "average_change":
            round(
                df["change"].mean(),
                2
            ),

        "volume_total":
            int(
                df["volume"].sum()
            )

    }


    return market