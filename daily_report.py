# daily_report.py

from pathlib import Path

import pandas as pd

from scanner import scan_all
from report import (
    print_header,
    print_rankings,
    print_hot_stocks,
    print_ai_comment,
    save_reports,
    print_footer,
)


OPTIMIZED_OUTPUT_FILE = Path(
    "reports/optimized_signals.csv"
)

MIN_SCORE = 55
RSI_MIN = 30
RSI_MAX = 75
MIN_VOLUME_RATIO = 2.0
MACD_CONDITION = "SELL"


def extract_optimized_signals(df):
    required_columns = {
        "銘柄",
        "ticker",
        "価格",
        "前日比%",
        "出来高倍率",
        "RSI",
        "MACD判定",
        "PHOENIX_SCORE",
        "理由",
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
            f"最適シグナル抽出に必要な列がありません: "
            f"{missing_text}"
        )

    target = df[
        (
            df["PHOENIX_SCORE"]
            >= MIN_SCORE
        )
        & (
            df["RSI"]
            >= RSI_MIN
        )
        & (
            df["RSI"]
            <= RSI_MAX
        )
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
            "前日比%",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    return target


def print_optimized_signals(target):
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
            "本日は最適条件に一致する"
            "銘柄はありません。"
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
        "理由",
    ]

    print(
        target[
            display_columns
        ].to_string(
            index=False
        )
    )


def print_optimized_comment(target):
    print()
    print("=" * 70)
    print("PHOENIX OPTIMIZED COMMENT")
    print("=" * 70)

    if target.empty:
        print(
            "本日はバックテスト上の"
            "最適条件に一致する銘柄はありません。"
        )
        return

    top = target.iloc[0]

    print(
        f"最優先監視銘柄は"
        f" {top['銘柄']} です。"
    )

    print(
        f"PHOENIX SCORE "
        f"{top['PHOENIX_SCORE']}点、"
        f"前日比 {top['前日比%']}%、"
        f"出来高 {top['出来高倍率']}倍、"
        f"RSI {top['RSI']}、"
        f"MACD {top['MACD判定']}。"
    )

    print(
        "過去検証では、"
        "スコア55以上・RSI30〜75・"
        "出来高2倍以上・MACD SELLの"
        "組み合わせが比較的良好でした。"
    )

    print(
        f"判定理由：{top['理由']}"
    )

    print(
        "これは売買推奨ではなく、"
        "翌営業日の監視候補です。"
    )


def save_optimized_signals(target):
    OPTIMIZED_OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.to_csv(
        OPTIMIZED_OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print()
    print(
        f"最適シグナル保存完了 : "
        f"{OPTIMIZED_OUTPUT_FILE}"
    )


def main():
    print_header()

    try:
        df = scan_all()

        if df.empty:
            print(
                "データ取得失敗"
            )
            print_footer()
            return

        print_rankings(
            df
        )

        print_hot_stocks(
            df
        )

        print_ai_comment(
            df
        )

        optimized = (
            extract_optimized_signals(
                df
            )
        )

        print_optimized_signals(
            optimized
        )

        print_optimized_comment(
            optimized
        )

        save_reports(
            df
        )

        save_optimized_signals(
            optimized
        )

    except Exception as error:
        print()
        print(
            f"PHOENIXエラー: {error}"
        )

    print_footer()


if __name__ == "__main__":
    main()