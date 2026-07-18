# backtest_engine.py
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data"

PORTFOLIO_FILE = REPORT_DIR / "portfolio_watchlist.csv"
WATCHLIST_FILE = REPORT_DIR / "price_watchlist.csv"
NIKKEI225_FILE = DATA_DIR / "nikkei225.csv"

TRADES_FILE = REPORT_DIR / "backtest_trades.csv"
EQUITY_FILE = REPORT_DIR / "backtest_equity.csv"
SUMMARY_FILE = REPORT_DIR / "backtest_summary.json"
REPORT_FILE = REPORT_DIR / "backtest_report.txt"

ACCOUNT_CAPITAL = 300_000
LOT_SIZE = 100
MAX_POSITIONS = 3
MAX_EXPOSURE_RATIO = 0.80
RISK_PER_TRADE_RATIO = 0.01

DEFAULT_PERIOD = "3y"
DEFAULT_MAX_TICKERS = 20
MAX_HOLD_DAYS = 20
STOP_ATR_MULTIPLIER = 1.5
TARGET_R_MULTIPLIER = 2.0
COMMISSION_RATE = 0.0
SLIPPAGE_RATE = 0.0005

MIN_HISTORY = 100


@dataclass
class Position:
    ticker: str
    name: str
    entry_date: str
    entry_price: float
    shares: int
    stop_price: float
    target_price: float
    signal_score: float
    entry_cost: float
    holding_days: int = 0


@dataclass
class Trade:
    ticker: str
    name: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    entry_cost: float
    exit_value: float
    gross_profit_yen: float
    fees_yen: float
    profit_yen: float
    return_pct: float
    holding_days: int
    exit_reason: str
    signal_score: float


def configure_console() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    last_error: Exception | None = None

    for encoding in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception as error:
            last_error = error

    if last_error:
        raise last_error

    return pd.DataFrame()


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def normalize_ticker(value: Any) -> str:
    ticker = str(value).strip()

    if not ticker or ticker.lower() == "nan":
        return ""

    if ticker.endswith(".T"):
        return ticker

    if ticker.replace(".", "").isalnum():
        return f"{ticker}.T"

    return ticker


def load_universe(max_tickers: int) -> pd.DataFrame:
    """
    Portfolio採用銘柄、監視銘柄、日経225を優先順に統合する。
    """
    max_tickers = max(int(max_tickers), 1)

    source_specs = (
        (PORTFOLIO_FILE, "portfolio"),
        (WATCHLIST_FILE, "watchlist"),
        (NIKKEI225_FILE, "nikkei225"),
    )

    frames: list[pd.DataFrame] = []

    for path, source in source_specs:
        data = read_csv_safe(path)

        if data.empty:
            continue

        ticker_column = next(
            (
                column
                for column in ("ticker", "Ticker", "コード")
                if column in data.columns
            ),
            None,
        )

        if ticker_column is None:
            continue

        name_column = next(
            (
                column
                for column in ("銘柄", "name", "Name", "会社名")
                if column in data.columns
            ),
            None,
        )

        work = data.copy()

        if source == "portfolio" and "Portfolio判定" in work.columns:
            adopted = work[
                work["Portfolio判定"].astype(str).str.strip() == "採用"
            ].copy()

            if not adopted.empty:
                work = adopted

        sort_column = next(
            (
                column
                for column in (
                    "PortfolioScore",
                    "AI判断点",
                    "PHOENIX_SCORE",
                    "score",
                )
                if column in work.columns
            ),
            None,
        )

        if sort_column is not None:
            work[sort_column] = pd.to_numeric(
                work[sort_column],
                errors="coerce",
            )
            work = work.sort_values(
                sort_column,
                ascending=False,
                na_position="last",
            )

        result = pd.DataFrame()
        result["ticker"] = work[ticker_column].map(normalize_ticker)

        if name_column is not None:
            result["name"] = work[name_column].astype(str).str.strip()
        else:
            result["name"] = result["ticker"]

        result["source"] = source

        result = result[
            result["ticker"].astype(str).str.len() > 0
        ].drop_duplicates("ticker")

        if not result.empty:
            frames.append(result)

    if not frames:
        raise FileNotFoundError(
            "バックテスト対象がありません。"
            " reports/portfolio_watchlist.csv、"
            "reports/price_watchlist.csv、"
            "data/nikkei225.csv のいずれかを用意してください。"
        )

    universe = pd.concat(
        frames,
        ignore_index=True,
    )

    universe = universe.drop_duplicates(
        subset=["ticker"],
        keep="first",
    )

    return universe.head(max_tickers).reset_index(drop=True)


def download_history(ticker: str, period: str) -> pd.DataFrame:
    data = yf.download(
        ticker,
        period=period,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )

    if data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        if ticker in data.columns.get_level_values(-1):
            data = data.xs(ticker, axis=1, level=-1)
        else:
            data.columns = data.columns.get_level_values(0)

    required = ["Open", "High", "Low", "Close", "Volume"]

    if not all(column in data.columns for column in required):
        return pd.DataFrame()

    data = data[required].copy()
    data.index = pd.to_datetime(data.index).tz_localize(None)
    data = data[~data.index.duplicated(keep="last")]
    data = data.sort_index()
    data = data.dropna(subset=["Open", "High", "Low", "Close"])

    return data


def add_indicators(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()

    result["MA5"] = result["Close"].rolling(5).mean()
    result["MA25"] = result["Close"].rolling(25).mean()
    result["MA75"] = result["Close"].rolling(75).mean()

    delta = result["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    average_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    average_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()

    rs = average_gain / average_loss.replace(0, np.nan)
    result["RSI"] = 100 - (100 / (1 + rs))
    result["RSI"] = result["RSI"].fillna(50)

    ema12 = result["Close"].ewm(span=12, adjust=False).mean()
    ema26 = result["Close"].ewm(span=26, adjust=False).mean()
    result["MACD"] = ema12 - ema26
    result["MACD_SIGNAL"] = result["MACD"].ewm(span=9, adjust=False).mean()

    previous_close = result["Close"].shift(1)
    true_range = pd.concat(
        [
            result["High"] - result["Low"],
            (result["High"] - previous_close).abs(),
            (result["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    result["ATR"] = true_range.rolling(14).mean()
    result["VOLUME_MA20"] = result["Volume"].rolling(20).mean()
    result["VOLUME_RATIO"] = (
        result["Volume"] / result["VOLUME_MA20"].replace(0, np.nan)
    ).fillna(0)

    result["RETURN_5D"] = result["Close"].pct_change(5) * 100
    result["RETURN_20D"] = result["Close"].pct_change(20) * 100

    return result


def signal_score(row: pd.Series) -> float:
    score = 0.0

    close = safe_float(row.get("Close"))
    ma5 = safe_float(row.get("MA5"))
    ma25 = safe_float(row.get("MA25"))
    ma75 = safe_float(row.get("MA75"))
    rsi = safe_float(row.get("RSI"), 50)
    macd = safe_float(row.get("MACD"))
    macd_signal = safe_float(row.get("MACD_SIGNAL"))
    volume_ratio = safe_float(row.get("VOLUME_RATIO"))
    return_20d = safe_float(row.get("RETURN_20D"))

    if close > ma25 > 0:
        score += 20

    if ma5 > ma25 > 0:
        score += 20

    if ma25 > ma75 > 0:
        score += 20

    if macd > macd_signal:
        score += 15

    if 45 <= rsi <= 68:
        score += 15
    elif 40 <= rsi < 45:
        score += 8

    if volume_ratio >= 1.2:
        score += 5

    if return_20d > 0:
        score += 5

    return round(score, 2)


def is_entry_signal(row: pd.Series) -> bool:
    score = signal_score(row)
    rsi = safe_float(row.get("RSI"), 50)
    atr = safe_float(row.get("ATR"))

    return (
        score >= 70
        and 40 <= rsi <= 72
        and atr > 0
    )


def calculate_shares(
    cash: float,
    entry_price: float,
    stop_price: float,
    current_exposure: float,
) -> int:
    if entry_price <= 0 or stop_price <= 0 or entry_price <= stop_price:
        return 0

    risk_per_share = entry_price - stop_price
    risk_budget = ACCOUNT_CAPITAL * RISK_PER_TRADE_RATIO
    risk_based_shares = int(risk_budget // risk_per_share)

    remaining_exposure = max(
        ACCOUNT_CAPITAL * MAX_EXPOSURE_RATIO - current_exposure,
        0,
    )
    cash_limit = min(cash, remaining_exposure)
    cash_based_shares = int(cash_limit // entry_price)

    shares = min(risk_based_shares, cash_based_shares)
    shares = (shares // LOT_SIZE) * LOT_SIZE

    return max(shares, 0)


def prepare_histories(
    universe: pd.DataFrame,
    period: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    histories: dict[str, pd.DataFrame] = {}
    names: dict[str, str] = {}

    print("=" * 100)
    print("PHOENIX BACKTEST DATA DOWNLOAD")
    print("=" * 100)

    for _, item in universe.iterrows():
        ticker = str(item["ticker"])
        name = str(item["name"])

        print(f"取得中: {ticker} {name}")

        try:
            history = download_history(ticker, period)
        except Exception as error:
            print(f"  SKIP: {error}")
            continue

        if len(history) < MIN_HISTORY:
            print(f"  SKIP: データ不足 {len(history)}日")
            continue

        histories[ticker] = add_indicators(history)
        names[ticker] = name
        print(f"  OK: {len(history)}日")

    if not histories:
        raise RuntimeError("有効な株価データを取得できませんでした。")

    return histories, names


def run_backtest(
    histories: dict[str, pd.DataFrame],
    names: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    all_dates = sorted(
        set().union(*(set(data.index) for data in histories.values()))
    )

    cash = float(ACCOUNT_CAPITAL)
    positions: dict[str, Position] = {}
    trades: list[Trade] = []
    equity_rows: list[dict[str, Any]] = []

    for current_date in all_dates:
        # 決済判定
        for ticker in list(positions):
            position = positions[ticker]
            data = histories[ticker]

            if current_date not in data.index:
                continue

            row = data.loc[current_date]
            position.holding_days += 1

            open_price = safe_float(row["Open"])
            high_price = safe_float(row["High"])
            low_price = safe_float(row["Low"])
            close_price = safe_float(row["Close"])

            exit_price = 0.0
            exit_reason = ""

            if open_price <= position.stop_price:
                exit_price = open_price
                exit_reason = "STOP_GAP"
            elif open_price >= position.target_price:
                exit_price = open_price
                exit_reason = "TARGET_GAP"
            elif low_price <= position.stop_price:
                exit_price = position.stop_price
                exit_reason = "STOP"
            elif high_price >= position.target_price:
                exit_price = position.target_price
                exit_reason = "TARGET"
            elif position.holding_days >= MAX_HOLD_DAYS:
                exit_price = close_price
                exit_reason = "TIME_EXIT"

            if exit_reason:
                slipped_exit = exit_price * (1 - SLIPPAGE_RATE)
                exit_value = slipped_exit * position.shares
                fees = (position.entry_cost + exit_value) * COMMISSION_RATE
                gross_profit = exit_value - position.entry_cost
                profit = gross_profit - fees
                return_pct = (
                    profit / position.entry_cost * 100
                    if position.entry_cost > 0
                    else 0
                )

                cash += exit_value - fees

                trades.append(
                    Trade(
                        ticker=ticker,
                        name=position.name,
                        entry_date=position.entry_date,
                        exit_date=current_date.strftime("%Y-%m-%d"),
                        entry_price=round(position.entry_price, 4),
                        exit_price=round(slipped_exit, 4),
                        shares=position.shares,
                        entry_cost=round(position.entry_cost, 2),
                        exit_value=round(exit_value, 2),
                        gross_profit_yen=round(gross_profit, 2),
                        fees_yen=round(fees, 2),
                        profit_yen=round(profit, 2),
                        return_pct=round(return_pct, 4),
                        holding_days=position.holding_days,
                        exit_reason=exit_reason,
                        signal_score=position.signal_score,
                    )
                )

                del positions[ticker]

        # 当日終値時点でシグナル判定、翌営業日の始値でエントリー
        candidates: list[tuple[float, str, pd.Timestamp]] = []

        for ticker, data in histories.items():
            if ticker in positions or current_date not in data.index:
                continue

            location = data.index.get_loc(current_date)

            if not isinstance(location, (int, np.integer)):
                continue

            if location < MIN_HISTORY - 1 or location + 1 >= len(data):
                continue

            row = data.iloc[location]

            if is_entry_signal(row):
                candidates.append(
                    (
                        signal_score(row),
                        ticker,
                        data.index[location + 1],
                    )
                )

        candidates.sort(reverse=True)

        for score, ticker, entry_date in candidates:
            if len(positions) >= MAX_POSITIONS:
                break

            if ticker in positions:
                continue

            data = histories[ticker]

            if entry_date not in data.index:
                continue

            signal_row = data.loc[current_date]
            entry_row = data.loc[entry_date]

            raw_entry_price = safe_float(entry_row["Open"])
            atr = safe_float(signal_row["ATR"])

            if raw_entry_price <= 0 or atr <= 0:
                continue

            entry_price = raw_entry_price * (1 + SLIPPAGE_RATE)
            stop_price = entry_price - atr * STOP_ATR_MULTIPLIER
            target_price = entry_price + (
                entry_price - stop_price
            ) * TARGET_R_MULTIPLIER

            exposure = sum(
                position.entry_cost for position in positions.values()
            )

            shares = calculate_shares(
                cash=cash,
                entry_price=entry_price,
                stop_price=stop_price,
                current_exposure=exposure,
            )

            if shares < LOT_SIZE:
                continue

            entry_cost = entry_price * shares
            entry_fee = entry_cost * COMMISSION_RATE
            total_debit = entry_cost + entry_fee

            if total_debit > cash:
                continue

            cash -= total_debit

            positions[ticker] = Position(
                ticker=ticker,
                name=names.get(ticker, ticker),
                entry_date=entry_date.strftime("%Y-%m-%d"),
                entry_price=entry_price,
                shares=shares,
                stop_price=stop_price,
                target_price=target_price,
                signal_score=score,
                entry_cost=entry_cost,
            )

        market_value = 0.0

        for ticker, position in positions.items():
            data = histories[ticker]

            if current_date in data.index:
                close_price = safe_float(data.loc[current_date, "Close"])
            else:
                available = data.loc[data.index <= current_date]

                if available.empty:
                    close_price = position.entry_price
                else:
                    close_price = safe_float(available.iloc[-1]["Close"])

            market_value += close_price * position.shares

        equity_rows.append(
            {
                "date": current_date.strftime("%Y-%m-%d"),
                "cash_yen": round(cash, 2),
                "market_value_yen": round(market_value, 2),
                "equity_yen": round(cash + market_value, 2),
                "open_positions": len(positions),
            }
        )

    # 期間末に残ったポジションを終値決済
    if all_dates:
        final_date = all_dates[-1]

        for ticker in list(positions):
            position = positions[ticker]
            data = histories[ticker]
            available = data.loc[data.index <= final_date]

            if available.empty:
                continue

            exit_price = safe_float(available.iloc[-1]["Close"]) * (
                1 - SLIPPAGE_RATE
            )
            exit_value = exit_price * position.shares
            fees = (position.entry_cost + exit_value) * COMMISSION_RATE
            gross_profit = exit_value - position.entry_cost
            profit = gross_profit - fees
            return_pct = (
                profit / position.entry_cost * 100
                if position.entry_cost > 0
                else 0
            )

            cash += exit_value - fees

            trades.append(
                Trade(
                    ticker=ticker,
                    name=position.name,
                    entry_date=position.entry_date,
                    exit_date=final_date.strftime("%Y-%m-%d"),
                    entry_price=round(position.entry_price, 4),
                    exit_price=round(exit_price, 4),
                    shares=position.shares,
                    entry_cost=round(position.entry_cost, 2),
                    exit_value=round(exit_value, 2),
                    gross_profit_yen=round(gross_profit, 2),
                    fees_yen=round(fees, 2),
                    profit_yen=round(profit, 2),
                    return_pct=round(return_pct, 4),
                    holding_days=position.holding_days,
                    exit_reason="END_OF_TEST",
                    signal_score=position.signal_score,
                )
            )

        if equity_rows:
            equity_rows[-1]["cash_yen"] = round(cash, 2)
            equity_rows[-1]["market_value_yen"] = 0.0
            equity_rows[-1]["equity_yen"] = round(cash, 2)
            equity_rows[-1]["open_positions"] = 0

    trades_df = pd.DataFrame([asdict(trade) for trade in trades])
    equity_df = pd.DataFrame(equity_rows)
    summary = calculate_summary(trades_df, equity_df)

    return trades_df, equity_df, summary


def calculate_summary(
    trades: pd.DataFrame,
    equity: pd.DataFrame,
) -> dict[str, Any]:
    if equity.empty:
        final_equity = float(ACCOUNT_CAPITAL)
        total_return = 0.0
        max_drawdown = 0.0
        annual_return = 0.0
        sharpe_ratio = 0.0
        start_date = ""
        end_date = ""
        test_days = 0
    else:
        equity_values = equity["equity_yen"].astype(float)
        final_equity = safe_float(equity_values.iloc[-1], ACCOUNT_CAPITAL)
        total_return = (
            (final_equity / ACCOUNT_CAPITAL - 1) * 100
            if ACCOUNT_CAPITAL > 0
            else 0
        )

        running_max = equity_values.cummax()
        drawdown = (
            (equity_values - running_max)
            / running_max.replace(0, np.nan)
            * 100
        )
        max_drawdown = abs(safe_float(drawdown.min(), 0))

        start = pd.to_datetime(equity["date"].iloc[0])
        end = pd.to_datetime(equity["date"].iloc[-1])
        calendar_days = max((end - start).days, 1)
        years = calendar_days / 365.25

        annual_return = (
            ((final_equity / ACCOUNT_CAPITAL) ** (1 / years) - 1) * 100
            if final_equity > 0 and years > 0
            else 0
        )

        daily_returns = equity_values.pct_change().dropna()

        if len(daily_returns) > 1 and safe_float(daily_returns.std()) > 0:
            sharpe_ratio = (
                safe_float(daily_returns.mean())
                / safe_float(daily_returns.std())
                * math.sqrt(252)
            )
        else:
            sharpe_ratio = 0.0

        start_date = start.strftime("%Y-%m-%d")
        end_date = end.strftime("%Y-%m-%d")
        test_days = len(equity)

    trade_count = len(trades)

    if trade_count > 0:
        profits = trades["profit_yen"].astype(float)
        winners = profits[profits > 0]
        losers = profits[profits < 0]

        win_rate = len(winners) / trade_count * 100
        gross_profit = safe_float(winners.sum())
        gross_loss = abs(safe_float(losers.sum()))

        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (999.0 if gross_profit > 0 else 0.0)
        )

        average_profit = safe_float(winners.mean()) if not winners.empty else 0
        average_loss = safe_float(losers.mean()) if not losers.empty else 0
        average_return = safe_float(trades["return_pct"].mean())
        average_holding = safe_float(trades["holding_days"].mean())
    else:
        win_rate = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        profit_factor = 0.0
        average_profit = 0.0
        average_loss = 0.0
        average_return = 0.0
        average_holding = 0.0

    return {
        "version": "PHOENIX v5.1.1",
        "generated_at": now_text(),
        "strategy": {
            "entry": "MA5>MA25、MA25>MA75、MACD、RSI、出来高を合成した70点以上",
            "execution": "シグナル翌営業日の始値",
            "stop": f"ATR × {STOP_ATR_MULTIPLIER}",
            "target": f"リスク × {TARGET_R_MULTIPLIER}",
            "maximum_holding_days": MAX_HOLD_DAYS,
            "lot_size": LOT_SIZE,
            "account_capital_yen": ACCOUNT_CAPITAL,
            "maximum_positions": MAX_POSITIONS,
            "maximum_exposure_ratio": MAX_EXPOSURE_RATIO,
            "risk_per_trade_ratio": RISK_PER_TRADE_RATIO,
            "slippage_rate": SLIPPAGE_RATE,
            "commission_rate": COMMISSION_RATE,
        },
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "trading_days": test_days,
        },
        "performance": {
            "initial_capital_yen": ACCOUNT_CAPITAL,
            "final_equity_yen": round(final_equity, 2),
            "total_profit_yen": round(final_equity - ACCOUNT_CAPITAL, 2),
            "total_return_pct": round(total_return, 4),
            "annual_return_pct": round(annual_return, 4),
            "max_drawdown_pct": round(max_drawdown, 4),
            "sharpe_ratio": round(sharpe_ratio, 4),
            "trade_count": trade_count,
            "win_rate_pct": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4),
            "gross_profit_yen": round(gross_profit, 2),
            "gross_loss_yen": round(gross_loss, 2),
            "average_profit_yen": round(average_profit, 2),
            "average_loss_yen": round(average_loss, 2),
            "average_return_pct": round(average_return, 4),
            "average_holding_days": round(average_holding, 2),
        },
    }


def save_outputs(
    trades: pd.DataFrame,
    equity: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if trades.empty:
        trades = pd.DataFrame(
            columns=[
                field.name for field in Trade.__dataclass_fields__.values()
            ]
        )

    trades.to_csv(TRADES_FILE, index=False, encoding="utf-8-sig")
    equity.to_csv(EQUITY_FILE, index=False, encoding="utf-8-sig")
    save_json(SUMMARY_FILE, summary)

    performance = summary["performance"]
    period = summary["period"]

    lines = [
        "PHOENIX v5.1.1 BACKTEST REPORT",
        "=" * 100,
        f"生成時刻       : {summary['generated_at']}",
        f"検証期間       : {period['start_date']} ～ {period['end_date']}",
        f"取引日数       : {period['trading_days']}日",
        f"初期資金       : {performance['initial_capital_yen']:,.0f}円",
        f"最終資産       : {performance['final_equity_yen']:,.0f}円",
        f"総損益         : {performance['total_profit_yen']:+,.0f}円",
        f"総リターン     : {performance['total_return_pct']:+.2f}%",
        f"年率リターン   : {performance['annual_return_pct']:+.2f}%",
        f"最大DD         : {performance['max_drawdown_pct']:.2f}%",
        f"シャープレシオ : {performance['sharpe_ratio']:.3f}",
        f"取引回数       : {performance['trade_count']}回",
        f"勝率           : {performance['win_rate_pct']:.2f}%",
        f"Profit Factor  : {performance['profit_factor']:.3f}",
        f"平均損益率     : {performance['average_return_pct']:+.2f}%",
        f"平均保有日数   : {performance['average_holding_days']:.2f}日",
        "",
        "注意:",
        "このバックテストは現在のPHOENIX条件を過去データ用に再現した戦略検証です。",
        "当時のニュース、当時生成されたAI判断点、売買時の実際の約定条件は再現していません。",
    ]

    REPORT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def print_summary(summary: dict[str, Any]) -> None:
    performance = summary["performance"]
    period = summary["period"]

    print()
    print("=" * 100)
    print("PHOENIX v5.1.1 BACKTEST RESULT")
    print("=" * 100)
    print(f"検証期間       : {period['start_date']} ～ {period['end_date']}")
    print(f"取引日数       : {period['trading_days']}日")
    print(f"初期資金       : {performance['initial_capital_yen']:,.0f}円")
    print(f"最終資産       : {performance['final_equity_yen']:,.0f}円")
    print(f"総損益         : {performance['total_profit_yen']:+,.0f}円")
    print(f"総リターン     : {performance['total_return_pct']:+.2f}%")
    print(f"年率リターン   : {performance['annual_return_pct']:+.2f}%")
    print(f"最大DD         : {performance['max_drawdown_pct']:.2f}%")
    print(f"シャープレシオ : {performance['sharpe_ratio']:.3f}")
    print(f"取引回数       : {performance['trade_count']}回")
    print(f"勝率           : {performance['win_rate_pct']:.2f}%")
    print(f"Profit Factor  : {performance['profit_factor']:.3f}")
    print(f"平均損益率     : {performance['average_return_pct']:+.2f}%")
    print(f"平均保有日数   : {performance['average_holding_days']:.2f}日")
    print()
    print(f"保存完了: {TRADES_FILE}")
    print(f"保存完了: {EQUITY_FILE}")
    print(f"保存完了: {SUMMARY_FILE}")
    print(f"保存完了: {REPORT_FILE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX Backtest Engine"
    )
    parser.add_argument(
        "--period",
        choices=("1y", "3y", "5y"),
        default=DEFAULT_PERIOD,
        help="検証期間。既定値は3y。",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=DEFAULT_MAX_TICKERS,
        help="最大検証銘柄数。既定値は20。",
    )
    return parser.parse_args()


def main() -> None:
    configure_console()
    args = parse_args()

    try:
        universe = load_universe(max(args.max_tickers, 1))
        histories, names = prepare_histories(universe, args.period)
        trades, equity, summary = run_backtest(histories, names)
        summary["request"] = {
            "period": args.period,
            "maximum_tickers": max(args.max_tickers, 1),
            "downloaded_tickers": len(histories),
            "tickers": list(histories.keys()),
        }

        save_outputs(trades, equity, summary)
        print_summary(summary)

    except Exception as error:
        print(f"Backtest Engineエラー: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
