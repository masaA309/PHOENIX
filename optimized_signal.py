# optimized_signal.py

from pathlib import Path

import pandas as pd

from scanner import scan_all


OUTPUT_FILE = Path(
    "reports/optimized_signals.csv"
)

MIN_SCORE = 55
RSI_MIN = 30
RSI_MAX = 75
MIN_VOLUME_RATIO = 2.0
MACD_CONDITION = "SELL"


def validate_columns(df):
    required_columns = {
        "銘柄",
        "ticker",
        "価格",
        "前日比%",
        "出来高倍率",
        "RSI",
        "MACD判定",
        "PHOENIX_SCORE",
        "理由"
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            f"必要な列がありません: {missing_text}"
        )


def extract_optimized_signals(df):
    target = df[
        (df["PHOENIX_SCORE"] >= MIN_SCORE)
        & (df["RSI"] >= RSI_MIN)
        & (df["RSI"] <= RSI_MAX)
        & (
            df["出来高倍率"]
            >= MIN_VOLUME_RATIO
        )
        & (
            df["MACD判定"]
            == MACD_CONDITION
        )
    ].copy()

    if target.empty:
        return target

    target["最適条件一致"] = True

    target = target.sort_values(
        by=[
            "出来高倍率",
            "PHOENIX_SCORE",
            "前日比%"
        ],
        ascending=[
            False,
            False,
            False
        ]
    ).reset_index(
        drop=True
    )

    return target


def print_signals(target):
    print()
    print("=" * 70)
    print("PHOENIX OPTIMIZED SIGNAL")
    print("=" * 70)

    print(
        f"最低スコア     : {MIN_SCORE}"
    )
    print(
        f"RSI範囲       : "
        f"{RSI_MIN}〜{RSI_MAX}"
    )
    print(
        f"最低出来高倍率 : "
        f"{MIN_VOLUME_RATIO}"
    )
    print(
        f"MACD条件      : "
        f"{MACD_CONDITION}"
    )
    print()

    if target.empty:
        print(
            "本日は最適条件に一致する銘柄はありません。"
        )
        return

    print(
        f"該当銘柄数 : {len(target)}"
    )
    print()

    display_columns = [
        "銘柄",
        "ticker",
        "価格",
        "前日比%",
        "出来高倍率",
        "RSI",
        "MACD判定",
        "PHOENIX_SCORE",
        "理由"
    ]

    print(
        target[
            display_columns
        ].to_string(
            index=False
        )
    )


def save_signals(target):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    target.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print()
    print(
        f"保存完了 : {OUTPUT_FILE}"
    )


def main():
    print("=" * 70)
    print("PHOENIX OPTIMIZED SIGNAL SCANNER")
    print("=" * 70)

    try:
        df = scan_all()

        if df.empty:
            print(
                "銘柄データを取得できませんでした。"
            )
            return

        validate_columns(df)

        target = extract_optimized_signals(
            df
        )

        print_signals(target)
        save_signals(target)

    except Exception as error:
        print(
            f"エラー: {error}"
        )


if __name__ == "__main__":
    main()