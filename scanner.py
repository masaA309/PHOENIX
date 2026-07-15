# scanner.py

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import os
import time
from typing import Any

import pandas as pd
import yfinance as yf

from indicators import calc_score


# =========================================================
# 設定
# =========================================================

STOCK_LIST_FILE = Path("data/nikkei225.csv")
CACHE_FILE = Path("data/market_data_cache.pkl")

HISTORY_PERIOD = "1y"

# Yahoo Financeへの1回当たりの銘柄数
BATCH_SIZE = 20

# バッチ間の待機時間
BATCH_WAIT_SECONDS = 3

# 75日移動平均などに必要な最低データ数
MIN_HISTORY_DAYS = 75

# 環境変数 PHOENIX_FORCE_REFRESH=1 で強制再取得
FORCE_REFRESH = (
    os.environ.get(
        "PHOENIX_FORCE_REFRESH",
        "0",
    )
    == "1"
)


# =========================================================
# 銘柄CSV
# =========================================================

def load_stock_list(
    csv_file: Path = STOCK_LIST_FILE,
) -> pd.DataFrame:
    if not csv_file.exists():
        raise FileNotFoundError(
            f"銘柄CSVがありません: {csv_file}"
        )

    stocks = pd.read_csv(
        csv_file,
    )

    required_columns = {
        "name",
        "ticker",
    }

    missing_columns = (
        required_columns
        - set(stocks.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            "銘柄CSVに必要な列がありません: "
            f"{missing_text}"
        )

    stocks["name"] = (
        stocks["name"]
        .astype(str)
        .str.strip()
    )

    stocks["ticker"] = (
        stocks["ticker"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    stocks = stocks[
        stocks["ticker"].str.match(
            r"^[0-9A-Z]{4}\.T$",
            na=False,
        )
    ]

    stocks = (
        stocks.drop_duplicates(
            subset=["ticker"],
        )
        .reset_index(
            drop=True,
        )
    )

    if stocks.empty:
        raise ValueError(
            "有効な銘柄がありません。"
        )

    return stocks


# =========================================================
# キャッシュ
# =========================================================

def empty_cache() -> dict[str, Any]:
    return {
        "saved_at": "",
        "stocks": {},
    }


def load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return empty_cache()

    try:
        cache = pd.read_pickle(
            CACHE_FILE,
        )

        if not isinstance(
            cache,
            dict,
        ):
            return empty_cache()

        if "stocks" not in cache:
            return empty_cache()

        if not isinstance(
            cache["stocks"],
            dict,
        ):
            return empty_cache()

        return cache

    except Exception as error:
        print(
            f"キャッシュ読込エラー: {error}"
        )

        return empty_cache()


def save_cache(
    stock_data: dict[str, pd.DataFrame],
) -> None:
    CACHE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    cache = {
        "saved_at": datetime.now().isoformat(
            timespec="seconds",
        ),
        "stocks": stock_data,
    }

    pd.to_pickle(
        cache,
        CACHE_FILE,
    )


def cache_is_today(
    cache: dict[str, Any],
) -> bool:
    saved_at = str(
        cache.get(
            "saved_at",
            "",
        )
    )

    if not saved_at:
        return False

    try:
        saved_datetime = (
            datetime.fromisoformat(
                saved_at,
            )
        )

    except ValueError:
        return False

    return (
        saved_datetime.date()
        == datetime.now().date()
    )


def cache_has_enough_stocks(
    cache: dict[str, Any],
    tickers: list[str],
) -> bool:
    cached_stocks = cache.get(
        "stocks",
        {},
    )

    valid_count = 0

    for ticker in tickers:
        ticker_data = cached_stocks.get(
            ticker,
        )

        if not isinstance(
            ticker_data,
            pd.DataFrame,
        ):
            continue

        if len(ticker_data) >= MIN_HISTORY_DAYS:
            valid_count += 1

    # 225銘柄中、ほぼ全件あれば当日キャッシュを使用
    required_count = max(
        len(tickers) - 5,
        1,
    )

    return (
        valid_count
        >= required_count
    )


# =========================================================
# データ整形
# =========================================================

def clean_ticker_data(
    ticker_data: pd.DataFrame,
) -> pd.DataFrame:
    if ticker_data.empty:
        return pd.DataFrame()

    required_columns = {
        "Close",
        "Volume",
    }

    if not required_columns.issubset(
        ticker_data.columns,
    ):
        return pd.DataFrame()

    cleaned = ticker_data[
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

    # 株価未確定行などを除外
    cleaned = cleaned.dropna(
        subset=[
            "Close",
            "Volume",
        ]
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

    return cleaned


def extract_ticker_data(
    downloaded: pd.DataFrame,
    ticker: str,
    batch_size: int,
) -> pd.DataFrame:
    if downloaded.empty:
        return pd.DataFrame()

    # 複数銘柄取得時
    if isinstance(
        downloaded.columns,
        pd.MultiIndex,
    ):
        level_zero = (
            downloaded.columns
            .get_level_values(0)
        )

        level_one = (
            downloaded.columns
            .get_level_values(1)
        )

        if ticker in level_zero:
            ticker_data = downloaded[
                ticker
            ].copy()

        elif ticker in level_one:
            ticker_data = downloaded.xs(
                ticker,
                axis=1,
                level=1,
            ).copy()

        else:
            return pd.DataFrame()

    # 1銘柄取得時
    else:
        if batch_size != 1:
            return pd.DataFrame()

        ticker_data = downloaded.copy()

    return clean_ticker_data(
        ticker_data,
    )


def split_batches(
    tickers: list[str],
    batch_size: int,
):
    for start in range(
        0,
        len(tickers),
        batch_size,
    ):
        yield tickers[
            start:start + batch_size
        ]


# =========================================================
# Yahoo Finance取得
# =========================================================

def download_one_batch(
    tickers: list[str],
) -> pd.DataFrame:
    try:
        return yf.download(
            tickers=tickers,
            period=HISTORY_PERIOD,
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,

            # アクセス集中を抑える
            threads=False,

            timeout=30,
        )

    except Exception as error:
        print(
            f"バッチ取得エラー: {error}"
        )

        return pd.DataFrame()


def download_market_data(
    tickers: list[str],
    cached_stocks: dict[str, pd.DataFrame],
) -> tuple[
    dict[str, pd.DataFrame],
    list[str],
]:
    merged_stocks = dict(
        cached_stocks,
    )

    live_success = []

    batches = list(
        split_batches(
            tickers,
            BATCH_SIZE,
        )
    )

    total_batches = len(
        batches,
    )

    print(
        f"日経225一括取得開始: "
        f"{len(tickers)}銘柄"
    )
    print()

    for batch_number, batch in enumerate(
        batches,
        start=1,
    ):
        print(
            f"市場データ取得 "
            f"[{batch_number}/{total_batches}] "
            f"{len(batch)}銘柄"
        )

        # 制限中に何度も再試行しない
        downloaded = download_one_batch(
            batch,
        )

        if downloaded.empty:
            print(
                "  取得失敗。"
                "保存済みキャッシュを使用します。"
            )

        else:
            batch_success_count = 0

            for ticker in batch:
                ticker_data = extract_ticker_data(
                    downloaded=downloaded,
                    ticker=ticker,
                    batch_size=len(batch),
                )

                if (
                    ticker_data.empty
                    or len(ticker_data)
                    < MIN_HISTORY_DAYS
                ):
                    continue

                merged_stocks[
                    ticker
                ] = ticker_data

                live_success.append(
                    ticker
                )

                batch_success_count += 1

            print(
                f"  ライブ取得成功: "
                f"{batch_success_count}/"
                f"{len(batch)}銘柄"
            )

        # 最後のバッチ後は待たない
        if batch_number < total_batches:
            time.sleep(
                BATCH_WAIT_SECONDS,
            )

    return (
        merged_stocks,
        live_success,
    )


# =========================================================
# 分析
# =========================================================

def analyze_stock(
    name: str,
    ticker: str,
    ticker_data: pd.DataFrame,
) -> dict[str, Any] | None:
    ticker_data = clean_ticker_data(
        ticker_data,
    )

    if len(ticker_data) < MIN_HISTORY_DAYS:
        return None

    close = ticker_data[
        "Close"
    ]

    volume = ticker_data[
        "Volume"
    ]

    score_data = calc_score(
        close,
        volume,
    )

    if score_data is None:
        return None

    latest_price = float(
        close.iloc[-1]
    )

    latest_date = pd.Timestamp(
        close.index[-1]
    ).strftime(
        "%Y-%m-%d",
    )

    return {
        "銘柄": name,
        "ticker": ticker,
        "基準日": latest_date,
        "価格": round(
            latest_price,
            2,
        ),
        "前日比%": score_data[
            "change"
        ],
        "出来高倍率": score_data[
            "volume_ratio"
        ],
        "MA5": score_data[
            "ma5"
        ],
        "MA25": score_data[
            "ma25"
        ],
        "MA75": score_data[
            "ma75"
        ],
        "RSI": score_data[
            "rsi"
        ],
        "MACD判定": score_data[
            "macd_judge"
        ],
        "PHOENIX_SCORE": score_data[
            "score"
        ],
        "理由": score_data[
            "reason"
        ],
    }


# =========================================================
# 全銘柄スキャン
# =========================================================

def scan_all(
    csv_file: Path | str = STOCK_LIST_FILE,
) -> pd.DataFrame:
    stocks = load_stock_list(
        Path(csv_file),
    )

    tickers = stocks[
        "ticker"
    ].tolist()

    cache = load_cache()

    cached_stocks = cache.get(
        "stocks",
        {},
    )

    use_today_cache = (
        not FORCE_REFRESH
        and cache_is_today(
            cache,
        )
        and cache_has_enough_stocks(
            cache,
            tickers,
        )
    )

    if use_today_cache:
        print(
            "本日はすでに市場データを取得済みです。"
        )
        print(
            f"当日キャッシュを使用: "
            f"{CACHE_FILE}"
        )
        print()

        market_stocks = cached_stocks
        live_success = []

    else:
        market_stocks, live_success = (
            download_market_data(
                tickers=tickers,
                cached_stocks=cached_stocks,
            )
        )

        # 1銘柄以上取得できた場合だけ保存日時を更新
        if live_success:
            save_cache(
                market_stocks,
            )

            print()
            print(
                f"市場データキャッシュ保存: "
                f"{CACHE_FILE}"
            )

        elif cached_stocks:
            print()
            print(
                "ライブ取得は失敗しましたが、"
                "前回キャッシュを使用します。"
            )

        else:
            print()
            print(
                "ライブ取得・キャッシュの両方が"
                "利用できません。"
            )

            return pd.DataFrame()

    results = []
    failed_tickers = []
    cache_used_count = 0

    total = len(
        stocks,
    )

    live_success_set = set(
        live_success,
    )

    for number, row in enumerate(
        stocks.itertuples(
            index=False,
        ),
        start=1,
    ):
        name = str(
            row.name,
        )

        ticker = str(
            row.ticker,
        )

        print(
            f"ANALYZE "
            f"[{number}/{total}] "
            f"{ticker}"
        )

        ticker_data = market_stocks.get(
            ticker,
        )

        if not isinstance(
            ticker_data,
            pd.DataFrame,
        ):
            failed_tickers.append(
                ticker,
            )
            continue

        try:
            result = analyze_stock(
                name=name,
                ticker=ticker,
                ticker_data=ticker_data,
            )

            if result is None:
                failed_tickers.append(
                    ticker,
                )
                continue

            if (
                not use_today_cache
                and ticker
                not in live_success_set
            ):
                cache_used_count += 1

            results.append(
                result,
            )

        except Exception as error:
            failed_tickers.append(
                ticker,
            )

            print(
                f"分析エラー "
                f"{ticker}: {error}"
            )

    print()
    print(
        f"分析成功: {len(results)}銘柄"
    )
    print(
        f"分析失敗: {len(failed_tickers)}銘柄"
    )

    if not use_today_cache:
        print(
            f"今回ライブ取得: "
            f"{len(live_success_set)}銘柄"
        )
        print(
            f"前回キャッシュ補完: "
            f"{cache_used_count}銘柄"
        )

    if failed_tickers:
        preview = ", ".join(
            failed_tickers[:10]
        )

        print(
            f"失敗銘柄例: {preview}"
        )

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(
        results,
    )

    return (
        result_df.sort_values(
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
        .reset_index(
            drop=True,
        )
    )


# =========================================================
# 単体実行
# =========================================================

def main() -> None:
    df = scan_all()

    if df.empty:
        raise SystemExit(
            "データ取得失敗"
        )

    print()
    print(
        df.head(
            20,
        ).to_string(
            index=False,
        )
    )


if __name__ == "__main__":
    main()