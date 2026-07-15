# chart_generator.py

from __future__ import annotations

from pathlib import Path
import re
import unicodedata
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


REPORT_DIR = Path("reports")
CHART_DIR = REPORT_DIR / "charts"

AI_FILE = REPORT_DIR / "ai_judgement.csv"
CACHE_FILE = Path("data/market_data_cache.pkl")

MAX_CHARTS = 10
DISPLAY_DAYS = 130


def safe_filename(
    value: str,
) -> str:
    text = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    text = re.sub(
        r'[\\/:*?"<>|]',
        "_",
        text,
    )

    text = re.sub(
        r"\s+",
        "_",
        text,
    )

    return text.strip(
        "._",
    )


def load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        raise FileNotFoundError(
            f"市場データキャッシュがありません: "
            f"{CACHE_FILE}"
        )

    cache = pd.read_pickle(
        CACHE_FILE,
    )

    if not isinstance(
        cache,
        dict,
    ):
        raise ValueError(
            "市場データキャッシュの形式が不正です。"
        )

    stock_data = cache.get(
        "stocks",
    )

    if not isinstance(
        stock_data,
        dict,
    ):
        raise ValueError(
            "キャッシュ内にstocksデータがありません。"
        )

    return cache


def load_targets() -> pd.DataFrame:
    if not AI_FILE.exists():
        raise FileNotFoundError(
            f"AI判断ファイルがありません: "
            f"{AI_FILE}"
        )

    df = pd.read_csv(
        AI_FILE,
    )

    required_columns = {
        "銘柄",
        "ticker",
        "AI判断",
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
        "MACD判定",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(
                missing_columns,
            )
        )

        raise ValueError(
            f"AI判断ファイルに必要な列がありません: "
            f"{missing_text}"
        )

    numeric_columns = [
        "AI判断点",
        "PHOENIX_SCORE",
        "RSI",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    judgement_order = {
        "優先監視": 0,
        "買い候補": 1,
        "押し目待ち": 2,
        "様子見": 3,
        "見送り": 4,
    }

    df["判断順"] = (
        df["AI判断"]
        .map(
            judgement_order,
        )
        .fillna(
            99,
        )
    )

    df = (
        df.dropna(
            subset=[
                "銘柄",
                "ticker",
                "AI判断点",
            ],
        )
        .sort_values(
            by=[
                "判断順",
                "AI判断点",
                "PHOENIX_SCORE",
            ],
            ascending=[
                True,
                False,
                False,
            ],
        )
        .head(
            MAX_CHARTS,
        )
        .reset_index(
            drop=True,
        )
    )

    return df


def clean_price_data(
    data: pd.DataFrame,
) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()

    required_columns = {
        "Close",
        "Volume",
    }

    if not required_columns.issubset(
        data.columns,
    ):
        return pd.DataFrame()

    cleaned = data[
        [
            "Close",
            "Volume",
        ]
    ].copy()

    cleaned["Close"] = pd.to_numeric(
        cleaned["Close"],
        errors="coerce",
    )

    cleaned["Volume"] = pd.to_numeric(
        cleaned["Volume"],
        errors="coerce",
    )

    cleaned = cleaned.dropna(
        subset=[
            "Close",
            "Volume",
        ],
    )

    cleaned = cleaned[
        cleaned["Close"] > 0
    ]

    cleaned = cleaned[
        ~cleaned.index.duplicated(
            keep="last",
        )
    ]

    cleaned = cleaned.sort_index()

    cleaned["MA5"] = (
        cleaned["Close"]
        .rolling(
            5,
        )
        .mean()
    )

    cleaned["MA25"] = (
        cleaned["Close"]
        .rolling(
            25,
        )
        .mean()
    )

    cleaned["MA75"] = (
        cleaned["Close"]
        .rolling(
            75,
        )
        .mean()
    )

    return cleaned.tail(
        DISPLAY_DAYS,
    )


def get_ticker_data(
    cache: dict[str, Any],
    ticker: str,
) -> pd.DataFrame:
    stocks = cache[
        "stocks"
    ]

    data = stocks.get(
        ticker,
    )

    if not isinstance(
        data,
        pd.DataFrame,
    ):
        return pd.DataFrame()

    return clean_price_data(
        data,
    )


def get_optional_float(
    row: pd.Series,
    column: str,
) -> float | None:
    if column not in row:
        return None

    value = row[
        column
    ]

    if pd.isna(
        value,
    ):
        return None

    try:
        return float(
            value,
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def create_chart(
    row: pd.Series,
    data: pd.DataFrame,
) -> Path:
    name = str(
        row["銘柄"]
    )

    ticker = str(
        row["ticker"]
    )

    judgement = str(
        row["AI判断"]
    )

    judgement_score = get_optional_float(
        row,
        "AI判断点",
    )

    phoenix_score = get_optional_float(
        row,
        "PHOENIX_SCORE",
    )

    rsi = get_optional_float(
        row,
        "RSI",
    )

    target_price = get_optional_float(
        row,
        "参考目標価格",
    )

    loss_cut_price = get_optional_float(
        row,
        "参考損切価格",
    )

    macd_judgement = str(
        row.get(
            "MACD判定",
            "",
        )
    )

    CHART_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    figure = plt.figure(
        figsize=(
            14,
            9,
        ),
    )

    price_axis = figure.add_axes(
        [
            0.08,
            0.36,
            0.86,
            0.55,
        ],
    )

    volume_axis = figure.add_axes(
        [
            0.08,
            0.10,
            0.86,
            0.18,
        ],
        sharex=price_axis,
    )

    price_axis.plot(
        data.index,
        data["Close"],
        label="Close",
        linewidth=1.8,
    )

    price_axis.plot(
        data.index,
        data["MA5"],
        label="MA5",
        linewidth=1.2,
    )

    price_axis.plot(
        data.index,
        data["MA25"],
        label="MA25",
        linewidth=1.2,
    )

    price_axis.plot(
        data.index,
        data["MA75"],
        label="MA75",
        linewidth=1.2,
    )

    latest_price = float(
        data["Close"].iloc[-1]
    )

    if target_price is not None:
        price_axis.axhline(
            y=target_price,
            linestyle="--",
            linewidth=1.0,
            label=(
                f"Target "
                f"{target_price:.2f}"
            ),
        )

    if loss_cut_price is not None:
        price_axis.axhline(
            y=loss_cut_price,
            linestyle="--",
            linewidth=1.0,
            label=(
                f"Stop "
                f"{loss_cut_price:.2f}"
            ),
        )

    title_parts = [
        f"{name} ({ticker})",
        f"Close {latest_price:.2f}",
        f"AI {judgement}",
    ]

    if judgement_score is not None:
        title_parts.append(
            f"AI Score "
            f"{judgement_score:.0f}"
        )

    if phoenix_score is not None:
        title_parts.append(
            f"PHOENIX "
            f"{phoenix_score:.0f}"
        )

    if rsi is not None:
        title_parts.append(
            f"RSI "
            f"{rsi:.2f}"
        )

    if macd_judgement:
        title_parts.append(
            f"MACD "
            f"{macd_judgement}"
        )

    price_axis.set_title(
        " | ".join(
            title_parts,
        ),
    )

    price_axis.set_ylabel(
        "Price",
    )

    price_axis.grid(
        True,
        alpha=0.3,
    )

    price_axis.legend(
        loc="upper left",
    )

    volume_axis.bar(
        data.index,
        data["Volume"],
        width=1.0,
    )

    volume_axis.set_ylabel(
        "Volume",
    )

    volume_axis.grid(
        True,
        alpha=0.2,
    )

    figure.autofmt_xdate()

    filename = (
        f"{safe_filename(name)}_"
        f"{safe_filename(ticker)}.png"
    )

    output_file = (
        CHART_DIR
        / filename
    )

    figure.savefig(
        output_file,
        dpi=150,
        bbox_inches="tight",
    )

    plt.close(
        figure,
    )

    return output_file


def save_index(
    results: list[dict[str, Any]],
) -> Path:
    index_file = (
        CHART_DIR
        / "chart_index.csv"
    )

    result_df = pd.DataFrame(
        results,
    )

    result_df.to_csv(
        index_file,
        index=False,
        encoding="utf-8-sig",
    )

    return index_file


def main() -> None:
    print("=" * 80)
    print("PHOENIX CHART GENERATOR")
    print("市場データキャッシュ使用版")
    print("=" * 80)

    try:
        targets = load_targets()
        cache = load_cache()

    except Exception as error:
        print(
            f"エラー: {error}"
        )

        raise SystemExit(
            1,
        )

    saved_at = str(
        cache.get(
            "saved_at",
            "",
        )
    )

    print(
        f"使用キャッシュ: {CACHE_FILE}"
    )

    print(
        f"キャッシュ保存日時: {saved_at}"
    )

    print(
        f"対象銘柄数: {len(targets)}"
    )

    print(
        "Yahoo Financeへのアクセスは行いません。"
    )

    success_count = 0
    failed_tickers = []
    chart_results = []

    for number, row in targets.iterrows():
        name = str(
            row["銘柄"]
        )

        ticker = str(
            row["ticker"]
        )

        print()
        print(
            f"[{number + 1}/{len(targets)}] "
            f"{ticker} {name}"
        )

        try:
            data = get_ticker_data(
                cache=cache,
                ticker=ticker,
            )

            if data.empty:
                failed_tickers.append(
                    ticker,
                )

                print(
                    "  キャッシュに株価データがありません。"
                )

                continue

            output_file = create_chart(
                row=row,
                data=data,
            )

            success_count += 1

            chart_results.append({
                "銘柄": name,
                "ticker": ticker,
                "AI判断": row[
                    "AI判断"
                ],
                "AI判断点": row[
                    "AI判断点"
                ],
                "PHOENIX_SCORE": row[
                    "PHOENIX_SCORE"
                ],
                "チャート": str(
                    output_file,
                ),
            })

            print(
                f"  保存: {output_file}"
            )

        except Exception as error:
            failed_tickers.append(
                ticker,
            )

            print(
                f"  エラー: {error}"
            )

    CHART_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    index_file = save_index(
        chart_results,
    )

    print()
    print("=" * 80)
    print("CHART RESULT")
    print("=" * 80)
    print(
        f"成功: {success_count}"
    )
    print(
        f"失敗: {len(failed_tickers)}"
    )
    print(
        f"チャート保存先: {CHART_DIR}"
    )
    print(
        f"一覧保存先: {index_file}"
    )

    if failed_tickers:
        print(
            "失敗銘柄: "
            + ", ".join(
                failed_tickers,
            )
        )

    if success_count == 0:
        raise SystemExit(
            1,
        )


if __name__ == "__main__":
    main()