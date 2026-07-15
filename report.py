# report.py

from datetime import datetime
from pathlib import Path
import unicodedata

import pandas as pd


REPORT_DIR = Path("reports")

NUMERIC_COLUMNS = {
    "価格",
    "前日比%",
    "出来高倍率",
    "MA5",
    "MA25",
    "MA75",
    "RSI",
    "PHOENIX_SCORE",
}


def text_width(value):
    text = str(value)
    width = 0

    for char in text:
        east_width = unicodedata.east_asian_width(char)

        if east_width in {"F", "W", "A"}:
            width += 2
        else:
            width += 1

    return width


def pad_text(value, width, align="left"):
    text = str(value)
    padding = max(width - text_width(text), 0)

    if align == "right":
        return (" " * padding) + text

    return text + (" " * padding)


def format_value(value, decimals=2):
    if pd.isna(value):
        return "-"

    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def prepare_display_value(column, value):
    decimal_columns = {
        "価格",
        "前日比%",
        "出来高倍率",
        "MA5",
        "MA25",
        "MA75",
        "RSI",
    }

    if column in decimal_columns:
        return format_value(value, 2)

    if column == "PHOENIX_SCORE":
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def print_fixed_table(
    df,
    columns,
    top=None,
    column_gap=4,
    extra_width=2,
):
    if df.empty:
        print("データなし")
        return

    target = df.copy()

    if top is not None:
        target = target.head(top)

    display_rows = []

    for _, row in target.iterrows():
        display_row = {}

        for column in columns:
            display_row[column] = prepare_display_value(
                column,
                row[column],
            )

        display_rows.append(display_row)

    column_widths = {}

    for column in columns:
        widest = text_width(column)

        for row in display_rows:
            widest = max(
                widest,
                text_width(row[column]),
            )

        column_widths[column] = widest + extra_width

    gap = " " * column_gap

    header_parts = []

    for column in columns:
        align = (
            "right"
            if column in NUMERIC_COLUMNS
            else "left"
        )

        header_parts.append(
            pad_text(
                column,
                column_widths[column],
                align=align,
            )
        )

    print(gap.join(header_parts))

    separator_parts = [
        "-" * column_widths[column]
        for column in columns
    ]

    print(gap.join(separator_parts))

    for row in display_rows:
        row_parts = []

        for column in columns:
            align = (
                "right"
                if column in NUMERIC_COLUMNS
                else "left"
            )

            row_parts.append(
                pad_text(
                    row[column],
                    column_widths[column],
                    align=align,
                )
            )

        print(gap.join(row_parts))


def print_header():
    print("=" * 84)
    print("PHOENIX DAILY REPORT")
    print(datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 84)
    print()


def print_rankings(df):
    if df.empty:
        print("データがありません。")
        return

    print()
    print("=" * 84)
    print("上昇率ランキング TOP10")
    print("=" * 84)

    rank_df = df.sort_values(
        by="前日比%",
        ascending=False,
    )

    print_fixed_table(
        rank_df,
        [
            "銘柄",
            "価格",
            "前日比%",
        ],
        top=10,
    )

    print()
    print("=" * 84)
    print("出来高急増ランキング TOP10")
    print("=" * 84)

    volume_df = df.sort_values(
        by="出来高倍率",
        ascending=False,
    )

    print_fixed_table(
        volume_df,
        [
            "銘柄",
            "価格",
            "出来高倍率",
        ],
        top=10,
    )

    print()
    print("=" * 84)
    print("PHOENIX SCORE TOP10")
    print("=" * 84)

    score_df = df.sort_values(
        by=[
            "PHOENIX_SCORE",
            "出来高倍率",
            "前日比%",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )

    print_fixed_table(
        score_df,
        [
            "銘柄",
            "価格",
            "前日比%",
            "出来高倍率",
            "RSI",
            "MACD判定",
            "PHOENIX_SCORE",
        ],
        top=10,
        column_gap=5,
        extra_width=3,
    )


def print_hot_stocks(df):
    print()
    print("=" * 84)
    print("本日の注目銘柄")
    print("=" * 84)

    hot = df[
        df["PHOENIX_SCORE"] >= 70
    ].copy()

    if hot.empty:
        print("該当なし")
        return

    hot = hot.sort_values(
        by=[
            "PHOENIX_SCORE",
            "出来高倍率",
            "前日比%",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )

    print_fixed_table(
        hot,
        [
            "銘柄",
            "価格",
            "前日比%",
            "出来高倍率",
            "RSI",
            "MACD判定",
            "PHOENIX_SCORE",
        ],
        column_gap=5,
        extra_width=3,
    )

    print()
    print("判定理由")

    for _, row in hot.iterrows():
        print(
            f"・{row['銘柄']}: "
            f"{row['理由']}"
        )


def print_ai_comment(df):
    print()
    print("=" * 84)
    print("AIコメント")
    print("=" * 84)

    hot = df[
        df["PHOENIX_SCORE"] >= 70
    ].copy()

    if hot.empty:
        print(
            "本日は強いシグナルを示す銘柄はありません。"
        )
        return

    top = (
        hot.sort_values(
            by=[
                "PHOENIX_SCORE",
                "出来高倍率",
                "前日比%",
            ],
            ascending=[
                False,
                False,
                False,
            ],
        )
        .iloc[0]
    )

    print(
        f"{top['銘柄']}は "
        f"PHOENIX SCORE "
        f"{int(float(top['PHOENIX_SCORE']))}点です。"
    )

    print(
        f"前日比 {format_value(top['前日比%'])}%、"
        f"出来高 {format_value(top['出来高倍率'])}倍、"
        f"RSI {format_value(top['RSI'])}、"
        f"MACD {top['MACD判定']}。"
    )

    print(
        f"判定理由：{top['理由']}"
    )


def save_reports(df):
    REPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    today = datetime.now().strftime(
        "%Y%m%d"
    )

    csv_file = REPORT_DIR / f"report_{today}.csv"
    txt_file = REPORT_DIR / f"report_{today}.txt"

    sorted_df = df.sort_values(
        by=[
            "PHOENIX_SCORE",
            "出来高倍率",
            "前日比%",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    ).reset_index(drop=True)

    sorted_df.to_csv(
        csv_file,
        index=False,
        encoding="utf-8-sig",
    )

    with open(
        txt_file,
        "w",
        encoding="utf-8",
    ) as file:
        file.write("PHOENIX DAILY REPORT\n")
        file.write(
            datetime.now().strftime(
                "%Y-%m-%d %H:%M"
            )
        )
        file.write("\n\n")
        file.write(
            sorted_df.to_string(
                index=False,
            )
        )

    print()
    print("レポート保存完了")
    print(csv_file)
    print(txt_file)


def print_footer():
    print()
    print("=" * 84)
    print("PHOENIX REPORT END")
    print("=" * 84)