# walk_forward_engine.py
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd

from backtest_engine import (
    StrategyParameters,
    add_indicators,
    run_backtest,
)
from optimization_engine import (
    build_parameter_grid,
    calculate_optimization_score,
    load_raw_histories,
    select_parameter_grid,
)


ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"

RESULTS_FILE = REPORT_DIR / "walk_forward_results.csv"
SUMMARY_FILE = REPORT_DIR / "walk_forward_summary.json"
REPORT_FILE = REPORT_DIR / "walk_forward_report.txt"

DEFAULT_PERIOD = "5y"
DEFAULT_MAX_TICKERS = 20
DEFAULT_MAX_COMBINATIONS = 20
DEFAULT_TRAIN_YEARS = 3
DEFAULT_TEST_MONTHS = 12
DEFAULT_STEP_MONTHS = 12
MIN_TRAIN_DAYS = 500
MIN_TEST_DAYS = 120
MIN_TEST_TRADES = 3

PASS_MIN_AVERAGE_PF = 1.20
PASS_MIN_AVERAGE_SHARPE = 0.50
PASS_MAX_AVERAGE_DD = 15.0
PASS_MIN_SUCCESS_RATE = 60.0


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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def normalize_histories(
    histories: dict[str, pd.DataFrame],
) -> dict[str, pd.DataFrame]:
    normalized: dict[str, pd.DataFrame] = {}

    for ticker, history in histories.items():
        if history.empty:
            continue

        data = history.copy()
        data.index = pd.to_datetime(data.index)

        if getattr(data.index, "tz", None) is not None:
            data.index = data.index.tz_localize(None)

        data = data[~data.index.duplicated(keep="last")]
        data = data.sort_index()
        normalized[ticker] = data

    if not normalized:
        raise RuntimeError("Walk-Forwardに使える株価データがありません。")

    return normalized


def build_windows(
    histories: dict[str, pd.DataFrame],
    train_years: int,
    test_months: int,
    step_months: int,
) -> list[dict[str, pd.Timestamp]]:
    if train_years <= 0:
        raise ValueError("学習年数は1年以上にしてください。")
    if test_months <= 0:
        raise ValueError("検証月数は1か月以上にしてください。")
    if step_months <= 0:
        raise ValueError("移動月数は1か月以上にしてください。")

    minimum_date = min(data.index.min() for data in histories.values())
    maximum_date = max(data.index.max() for data in histories.values())

    train_start = pd.Timestamp(minimum_date).normalize()
    train_end = train_start + pd.DateOffset(years=train_years)
    windows: list[dict[str, pd.Timestamp]] = []

    while True:
        test_start = train_end
        test_end = test_start + pd.DateOffset(months=test_months)

        if test_start >= maximum_date:
            break

        actual_test_end = min(test_end, maximum_date + pd.Timedelta(days=1))

        windows.append(
            {
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": actual_test_end,
            }
        )

        train_start = train_start + pd.DateOffset(months=step_months)
        train_end = train_start + pd.DateOffset(years=train_years)

        if train_end >= maximum_date:
            break

    return windows


def slice_histories(
    histories: dict[str, pd.DataFrame],
    start: pd.Timestamp,
    end: pd.Timestamp,
    minimum_days: int,
) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}

    for ticker, history in histories.items():
        selected = history.loc[
            (history.index >= start) & (history.index < end)
        ].copy()

        if len(selected) >= minimum_days:
            result[ticker] = selected

    return result


def prepare_indicators(
    raw_histories: dict[str, pd.DataFrame],
    parameters: StrategyParameters,
) -> dict[str, pd.DataFrame]:
    return {
        ticker: add_indicators(history, parameters)
        for ticker, history in raw_histories.items()
    }


def find_best_parameters(
    train_histories: dict[str, pd.DataFrame],
    names: dict[str, str],
    parameters: list[StrategyParameters],
) -> tuple[StrategyParameters, dict[str, Any]]:
    if not parameters:
        raise RuntimeError("探索パラメータがありません。")

    best_parameters: StrategyParameters | None = None
    best_summary: dict[str, Any] = {}
    best_score = float("-inf")

    indicator_cache: dict[
        tuple[int, int, int],
        dict[str, pd.DataFrame],
    ] = {}

    for candidate in parameters:
        ma_key = (
            candidate.ma_short,
            candidate.ma_mid,
            candidate.ma_long,
        )

        if ma_key not in indicator_cache:
            indicator_cache[ma_key] = prepare_indicators(
                train_histories,
                candidate,
            )

        _, _, summary = run_backtest(
            indicator_cache[ma_key],
            names,
            candidate,
        )
        performance = summary.get("performance", {})
        score, status = calculate_optimization_score(performance)

        ranking_key = (
            score,
            safe_float(performance.get("profit_factor")),
            safe_float(performance.get("sharpe_ratio")),
            safe_float(performance.get("annual_return_pct")),
            safe_int(performance.get("trade_count")),
        )

        current_best_key = (
            best_score,
            safe_float(
                best_summary.get("performance", {}).get(
                    "profit_factor"
                )
            ),
            safe_float(
                best_summary.get("performance", {}).get(
                    "sharpe_ratio"
                )
            ),
            safe_float(
                best_summary.get("performance", {}).get(
                    "annual_return_pct"
                )
            ),
            safe_int(
                best_summary.get("performance", {}).get(
                    "trade_count"
                )
            ),
        )

        if best_parameters is None or ranking_key > current_best_key:
            best_parameters = candidate
            best_score = score
            best_summary = summary
            best_summary["optimization_score"] = score
            best_summary["optimization_status"] = status

    if best_parameters is None:
        raise RuntimeError("ベストパラメータを決定できませんでした。")

    return best_parameters, best_summary


def evaluate_test_window(
    test_histories: dict[str, pd.DataFrame],
    names: dict[str, str],
    parameters: StrategyParameters,
) -> dict[str, Any]:
    prepared = prepare_indicators(test_histories, parameters)
    _, _, summary = run_backtest(prepared, names, parameters)
    return summary


def window_success(performance: dict[str, Any]) -> bool:
    trades = safe_int(performance.get("trade_count"))
    profit_factor = safe_float(performance.get("profit_factor"))
    total_return = safe_float(performance.get("total_return_pct"))
    max_drawdown = safe_float(performance.get("max_drawdown_pct"))

    return (
        trades >= MIN_TEST_TRADES
        and profit_factor > 1.0
        and total_return > 0
        and max_drawdown <= 20.0
    )


def run_walk_forward(
    raw_histories: dict[str, pd.DataFrame],
    names: dict[str, str],
    parameter_grid: list[StrategyParameters],
    train_years: int,
    test_months: int,
    step_months: int,
) -> pd.DataFrame:
    histories = normalize_histories(raw_histories)
    windows = build_windows(
        histories,
        train_years=train_years,
        test_months=test_months,
        step_months=step_months,
    )

    if not windows:
        raise RuntimeError(
            "Walk-Forward期間を作成できません。"
            "より長いperiodを指定してください。"
        )

    rows: list[dict[str, Any]] = []

    print()
    print("=" * 120)
    print("PHOENIX v6.2 WALK-FORWARD TEST")
    print("=" * 120)
    print(f"候補パラメータ : {len(parameter_grid)}")
    print(f"作成期間数     : {len(windows)}")

    for fold_number, window in enumerate(windows, start=1):
        train_histories = slice_histories(
            histories,
            window["train_start"],
            window["train_end"],
            MIN_TRAIN_DAYS,
        )
        test_histories = slice_histories(
            histories,
            window["test_start"],
            window["test_end"],
            MIN_TEST_DAYS,
        )

        common_tickers = sorted(
            set(train_histories) & set(test_histories)
        )
        train_histories = {
            ticker: train_histories[ticker]
            for ticker in common_tickers
        }
        test_histories = {
            ticker: test_histories[ticker]
            for ticker in common_tickers
        }
        fold_names = {
            ticker: names.get(ticker, ticker)
            for ticker in common_tickers
        }

        if not common_tickers:
            print(
                f"[{fold_number}/{len(windows)}] SKIP "
                "学習・検証の共通銘柄なし"
            )
            continue

        best_parameters, train_summary = find_best_parameters(
            train_histories,
            fold_names,
            parameter_grid,
        )
        test_summary = evaluate_test_window(
            test_histories,
            fold_names,
            best_parameters,
        )

        train_performance = train_summary.get("performance", {})
        test_performance = test_summary.get("performance", {})
        success = window_success(test_performance)

        row = {
            "fold": fold_number,
            "train_start": window["train_start"].strftime("%Y-%m-%d"),
            "train_end": (
                window["train_end"] - pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "test_start": window["test_start"].strftime("%Y-%m-%d"),
            "test_end": (
                window["test_end"] - pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "ticker_count": len(common_tickers),
            **asdict(best_parameters),
            "train_optimization_score": safe_float(
                train_summary.get("optimization_score")
            ),
            "train_trade_count": safe_int(
                train_performance.get("trade_count")
            ),
            "train_profit_factor": safe_float(
                train_performance.get("profit_factor")
            ),
            "train_total_return_pct": safe_float(
                train_performance.get("total_return_pct")
            ),
            "train_sharpe_ratio": safe_float(
                train_performance.get("sharpe_ratio")
            ),
            "test_trade_count": safe_int(
                test_performance.get("trade_count")
            ),
            "test_win_rate_pct": safe_float(
                test_performance.get("win_rate_pct")
            ),
            "test_profit_factor": safe_float(
                test_performance.get("profit_factor")
            ),
            "test_total_return_pct": safe_float(
                test_performance.get("total_return_pct")
            ),
            "test_annual_return_pct": safe_float(
                test_performance.get("annual_return_pct")
            ),
            "test_max_drawdown_pct": safe_float(
                test_performance.get("max_drawdown_pct")
            ),
            "test_sharpe_ratio": safe_float(
                test_performance.get("sharpe_ratio")
            ),
            "success": success,
        }
        rows.append(row)

        print(
            f"[{fold_number:>2}/{len(windows)}] "
            f"Train {row['train_start']}～{row['train_end']} | "
            f"Test {row['test_start']}～{row['test_end']} | "
            f"PF={row['test_profit_factor']:.3f} "
            f"Sharpe={row['test_sharpe_ratio']:.3f} "
            f"DD={row['test_max_drawdown_pct']:.2f}% "
            f"Return={row['test_total_return_pct']:+.2f}% "
            f"{'PASS' if success else 'FAIL'}"
        )

    results = pd.DataFrame(rows)

    if results.empty:
        raise RuntimeError(
            "有効なWalk-Forward検証期間がありませんでした。"
        )

    return results


def most_common_parameters(
    results: pd.DataFrame,
) -> dict[str, Any]:
    parameter_columns = [
        "rsi_min",
        "rsi_max",
        "stop_atr_multiplier",
        "target_r_multiplier",
        "ma_short",
        "ma_mid",
        "ma_long",
        "signal_score_threshold",
        "max_hold_days",
    ]

    grouped = (
        results.groupby(parameter_columns, dropna=False)
        .size()
        .reset_index(name="selected_count")
        .sort_values(
            ["selected_count", "signal_score_threshold"],
            ascending=[False, False],
        )
    )

    selected = grouped.iloc[0].to_dict()

    return {
        "rsi_min": safe_float(selected["rsi_min"]),
        "rsi_max": safe_float(selected["rsi_max"]),
        "stop_atr_multiplier": safe_float(
            selected["stop_atr_multiplier"]
        ),
        "target_r_multiplier": safe_float(
            selected["target_r_multiplier"]
        ),
        "ma_short": safe_int(selected["ma_short"]),
        "ma_mid": safe_int(selected["ma_mid"]),
        "ma_long": safe_int(selected["ma_long"]),
        "signal_score_threshold": safe_float(
            selected["signal_score_threshold"]
        ),
        "max_hold_days": safe_int(selected["max_hold_days"]),
        "selected_count": safe_int(selected["selected_count"]),
    }


def build_summary(
    results: pd.DataFrame,
    period: str,
    max_tickers: int,
    tested_combinations: int,
    train_years: int,
    test_months: int,
    step_months: int,
) -> dict[str, Any]:
    valid = results.copy()
    fold_count = len(valid)
    success_count = int(valid["success"].astype(bool).sum())
    success_rate = (
        success_count / fold_count * 100
        if fold_count > 0
        else 0.0
    )

    total_test_trades = int(valid["test_trade_count"].sum())
    average_pf = safe_float(valid["test_profit_factor"].mean())
    average_sharpe = safe_float(valid["test_sharpe_ratio"].mean())
    average_dd = safe_float(valid["test_max_drawdown_pct"].mean())
    average_annual_return = safe_float(
        valid["test_annual_return_pct"].mean()
    )
    average_total_return = safe_float(
        valid["test_total_return_pct"].mean()
    )
    median_pf = safe_float(valid["test_profit_factor"].median())
    median_sharpe = safe_float(valid["test_sharpe_ratio"].median())

    status = (
        "PASS"
        if (
            average_pf >= PASS_MIN_AVERAGE_PF
            and average_sharpe >= PASS_MIN_AVERAGE_SHARPE
            and average_dd <= PASS_MAX_AVERAGE_DD
            and success_rate >= PASS_MIN_SUCCESS_RATE
        )
        else "FAIL"
    )

    return {
        "version": "PHOENIX v6.2",
        "generated_at": now_text(),
        "status": status,
        "period": period,
        "maximum_tickers": max_tickers,
        "tested_combinations_per_fold": tested_combinations,
        "train_years": train_years,
        "test_months": test_months,
        "step_months": step_months,
        "fold_count": fold_count,
        "success_count": success_count,
        "success_rate_pct": round(success_rate, 4),
        "total_test_trades": total_test_trades,
        "average_profit_factor": round(average_pf, 6),
        "median_profit_factor": round(median_pf, 6),
        "average_sharpe_ratio": round(average_sharpe, 6),
        "median_sharpe_ratio": round(median_sharpe, 6),
        "average_max_drawdown_pct": round(average_dd, 6),
        "average_annual_return_pct": round(
            average_annual_return,
            6,
        ),
        "average_total_return_pct": round(
            average_total_return,
            6,
        ),
        "adopted_parameters": most_common_parameters(valid),
        "pass_thresholds": {
            "minimum_average_profit_factor": PASS_MIN_AVERAGE_PF,
            "minimum_average_sharpe_ratio": PASS_MIN_AVERAGE_SHARPE,
            "maximum_average_drawdown_pct": PASS_MAX_AVERAGE_DD,
            "minimum_success_rate_pct": PASS_MIN_SUCCESS_RATE,
        },
    }


def save_outputs(
    results: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    results.to_csv(
        RESULTS_FILE,
        index=False,
        encoding="utf-8-sig",
    )
    save_json(SUMMARY_FILE, summary)

    adopted = summary["adopted_parameters"]

    lines = [
        "PHOENIX v6.2 WALK-FORWARD REPORT",
        "=" * 120,
        f"生成時刻       : {summary['generated_at']}",
        f"判定           : {summary['status']}",
        f"検証期間数     : {summary['fold_count']}",
        f"成功期間数     : {summary['success_count']}",
        f"成功率         : {summary['success_rate_pct']:.2f}%",
        f"検証取引数     : {summary['total_test_trades']}回",
        "",
        "OUT-OF-SAMPLE PERFORMANCE",
        "=" * 120,
        f"平均PF         : {summary['average_profit_factor']:.3f}",
        f"中央値PF       : {summary['median_profit_factor']:.3f}",
        f"平均Sharpe     : {summary['average_sharpe_ratio']:.3f}",
        f"中央値Sharpe   : {summary['median_sharpe_ratio']:.3f}",
        f"平均最大DD     : {summary['average_max_drawdown_pct']:.2f}%",
        f"平均年率       : {summary['average_annual_return_pct']:+.2f}%",
        f"平均期間収益   : {summary['average_total_return_pct']:+.2f}%",
        "",
        "MOST SELECTED PARAMETERS",
        "=" * 120,
        f"RSI            : {adopted['rsi_min']:.1f} ～ {adopted['rsi_max']:.1f}",
        f"ATR損切倍率    : {adopted['stop_atr_multiplier']:.2f}",
        f"利確R倍率      : {adopted['target_r_multiplier']:.2f}",
        (
            f"MA             : "
            f"{adopted['ma_short']} / "
            f"{adopted['ma_mid']} / "
            f"{adopted['ma_long']}"
        ),
        f"シグナル点数   : {adopted['signal_score_threshold']:.1f}",
        f"最大保有日数   : {adopted['max_hold_days']}日",
        f"選択回数       : {adopted['selected_count']}回",
        "",
        "注意:",
        "Walk-Forward結果も将来利益を保証しません。",
        "期間数や取引数が少ない場合は判定を過信しないでください。",
    ]

    REPORT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def print_summary(summary: dict[str, Any]) -> None:
    adopted = summary["adopted_parameters"]

    print()
    print("=" * 120)
    print("PHOENIX v6.2 WALK-FORWARD SUMMARY")
    print("=" * 120)
    print(f"判定           : {summary['status']}")
    print(f"検証期間数     : {summary['fold_count']}")
    print(f"成功率         : {summary['success_rate_pct']:.2f}%")
    print(f"検証取引数     : {summary['total_test_trades']}回")
    print(f"平均PF         : {summary['average_profit_factor']:.3f}")
    print(f"平均Sharpe     : {summary['average_sharpe_ratio']:.3f}")
    print(f"平均最大DD     : {summary['average_max_drawdown_pct']:.2f}%")
    print(f"平均年率       : {summary['average_annual_return_pct']:+.2f}%")
    print()
    print(
        f"採用候補       : RSI "
        f"{adopted['rsi_min']:.0f}-{adopted['rsi_max']:.0f}, "
        f"ATR {adopted['stop_atr_multiplier']:.2f}, "
        f"R {adopted['target_r_multiplier']:.2f}, "
        f"MA {adopted['ma_short']}/"
        f"{adopted['ma_mid']}/"
        f"{adopted['ma_long']}, "
        f"Signal {adopted['signal_score_threshold']:.0f}"
    )
    print()
    print(f"保存完了: {RESULTS_FILE}")
    print(f"保存完了: {SUMMARY_FILE}")
    print(f"保存完了: {REPORT_FILE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX Walk-Forward Test Engine"
    )
    parser.add_argument(
        "--period",
        choices=("3y", "5y", "10y"),
        default=DEFAULT_PERIOD,
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=DEFAULT_MAX_TICKERS,
    )
    parser.add_argument(
        "--max-combinations",
        type=int,
        default=DEFAULT_MAX_COMBINATIONS,
        help="各期間で探索する組み合わせ数。0で全件。",
    )
    parser.add_argument(
        "--train-years",
        type=int,
        default=DEFAULT_TRAIN_YEARS,
    )
    parser.add_argument(
        "--test-months",
        type=int,
        default=DEFAULT_TEST_MONTHS,
    )
    parser.add_argument(
        "--step-months",
        type=int,
        default=DEFAULT_STEP_MONTHS,
    )
    return parser.parse_args()


def main() -> None:
    configure_console()
    args = parse_args()

    try:
        raw_histories, names = load_raw_histories(
            max_tickers=max(args.max_tickers, 1),
            period=args.period,
        )

        all_parameters = build_parameter_grid()
        parameter_grid = select_parameter_grid(
            all_parameters,
            args.max_combinations,
        )

        results = run_walk_forward(
            raw_histories=raw_histories,
            names=names,
            parameter_grid=parameter_grid,
            train_years=args.train_years,
            test_months=args.test_months,
            step_months=args.step_months,
        )

        summary = build_summary(
            results=results,
            period=args.period,
            max_tickers=max(args.max_tickers, 1),
            tested_combinations=len(parameter_grid),
            train_years=args.train_years,
            test_months=args.test_months,
            step_months=args.step_months,
        )

        save_outputs(results, summary)
        print_summary(summary)

    except Exception as error:
        print(f"Walk-Forward Engineエラー: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
