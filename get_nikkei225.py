import pandas as pd
import requests
from io import StringIO
from pathlib import Path

URL = "https://ja.wikipedia.org/wiki/日経平均株価"

print("日経225構成銘柄を取得中...")

try:
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        URL,
        headers=headers,
        timeout=30
    )
    response.raise_for_status()

    tables = pd.read_html(
        StringIO(response.text)
    )

    dfs = []

    for table in tables:
        cols = [str(c) for c in table.columns]

        if (
            "証券コード" in cols
            and "銘柄" in cols
        ):
            df = table[
                ["証券コード", "銘柄"]
            ].copy()
            dfs.append(df)

    if len(dfs) == 0:
        raise Exception(
            "銘柄テーブルが見つかりませんでした。"
        )

    nikkei = pd.concat(
        dfs,
        ignore_index=True
    )

    nikkei["証券コード"] = (
        nikkei["証券コード"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    nikkei = nikkei[
        nikkei["証券コード"].str.match(
            r"^[0-9A-Z]{4}$",
            na=False
        )
    ]

    result = pd.DataFrame()

    result["name"] = nikkei["銘柄"]
    result["ticker"] = (
        nikkei["証券コード"] + ".T"
    )

    result = (
        result
        .drop_duplicates()
        .sort_values(
            by="ticker"
        )
        .reset_index(drop=True)
    )

    # dataフォルダ作成
    Path("data").mkdir(
        exist_ok=True
    )

    # PHOENIX本番CSVへ保存
    result.to_csv(
        "data/nikkei225.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print("=" * 60)
    print(
        f"保存完了！ {len(result)}銘柄"
    )
    print(
        "保存先: data/nikkei225.csv"
    )
    print("=" * 60)
    print()

    print(result.head())

except Exception as e:
    print("エラー:", e)