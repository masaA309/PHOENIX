# optimization_engine.py
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import itertools
import json
import math
from pathlib import Path
import sys
from typing import Any

import pandas as pd

from backtest_engine import (
    ACCOUNT_CAPITAL,
    NIKKEI225_FILE,
    PORTFOLIO_FILE,
    WATCHLIST_FILE,
    StrategyParameters,
    add_indicators,
    download_history,
    load_universe,
    run_backtest,
)


ROOT_DIR = Path(__file__).resolve().parent
REPORT_DIR = ROOT_DIR / "reports"

RESULTS_FILE = REPORT_DIR / "optimization_results.csv"
BEST_FILE = REPORT_DIR / "optimization_best.json"
REPORT_FILE = REPORT_DIR / "optimization_report.txt"
AI_PARAMETER_FILE = REPORT_DIR / "ai_parameter.json"

DEFAULT_PERIOD = "5y"
DEFAULT_MAX_TICKERS = 20
DEFAULT_MAX_COMBINATIONS = 120
MINIMUM_TRADES = 20

RSI_RANGES = (
    (35.0, 65.0),
    (40.0, 65.0),
    (40.0, 70.0),
    (45.0, 70.0),
    (45.0, 75.0),
)

STOP_ATR_VALUES = (1.0, 1.2, 1.5, 1.8, 2.0)
TARGET_R_VALUES = (1.5, 2.0, 2.5, 3.0)
MA_SETS = (
    (5, 20, 60),
    (5, 25, 75),
    (10, 30, 90),
)
SIGNAL_THRESHOLDS = (60.0, 65.0, 70.0, 75.0)
MAX_HOLD_DAYS_VALUES = (10, 15, 20, 30)


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


def load_raw_histories(
    max_tickers: int,
    period: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    universe = load_universe(max(max_tickers, 1))
    histories: dict[str, pd.DataFrame] = {}
    names: dict[str, str] = {}

    print("=" * 110)
    print("PHOENIX OPTIMIZATION DATA DOWNLOAD")
    print("=" * 110)

    for _, item in universe.iterrows():
        ticker = str(item["ticker"])
        name = str(item["name"])

        print(f"取得中: {ticker} {name}")

        try:
            history = download_history(ticker, period)
        except Exception as error:
            print(f"  SKIP: {error}")
            continue

        if len(history) < 130:
            print(f"  SKIP: データ不足 {len(history)}日")
            continue

        histories[ticker] = history
        names[ticker] = name
        print(f"  OK: {len(history)}日")

    if not histories:
        raise RuntimeError("最適化に使える株価データがありません。")

    return histories, names


def build_parameter_grid() -> list[StrategyParameters]:
    grid: list[StrategyParameters] = []

    for (
        rsi_range,
        stop_atr,
        target_r,
        ma_set,
        threshold,
        max_hold_days,
    ) in itertools.product(
        RSI_RANGES,
        STOP_ATR_VALUES,
        TARGET_R_VALUES,
        MA_SETS,
        SIGNAL_THRESHOLDS,
        MAX_HOLD_DAYS_VALUES,
    ):
        grid.append(
            StrategyParameters(
                rsi_min=rsi_range[0],
                rsi_max=rsi_range[1],
                stop_atr_multiplier=stop_atr,
                target_r_multiplier=target_r,
                ma_short=ma_set[0],
                ma_mid=ma_set[1],
                ma_long=ma_set[2],
                signal_score_threshold=threshold,
                max_hold_days=max_hold_days,
            )
        )

    return grid


def select_parameter_grid(
    all_parameters: list[StrategyParameters],
    max_combinations: int,
) -> list[StrategyParameters]:
    if max_combinations <= 0 or max_combinations >= len(all_parameters):
        return all_parameters

    # 全範囲から均等抽出し、特定領域だけに偏らせない。
    if max_combinations == 1:
        return [all_parameters[0]]

    step = (len(all_parameters) - 1) / (max_combinations - 1)
    indexes = {
        round(index * step)
        for index in range(max_combinations)
    }

    selected = [all_parameters[index] for index in sorted(indexes)]

    # 丸めで件数不足になった場合は先頭から補完。
    if len(selected) < max_combinations:
        selected_keys = {tuple(asdict(item).values()) for item in selected}

        for item in all_parameters:
            key = tuple(asdict(item).values())

            if key in selected_keys:
                continue

            selected.append(item)
            selected_keys.add(key)

            if len(selected) >= max_combinations:
                break

    return selected[:max_combinations]


def calculate_optimization_score(
    performance: dict[str, Any],
) -> tuple[float, str]:
    trade_count = safe_int(performance.get("trade_count"))
    total_return = safe_float(performance.get("total_return_pct"))
    annual_return = safe_float(performance.get("annual_return_pct"))
    max_drawdown = safe_float(performance.get("max_drawdown_pct"))
    sharpe = safe_float(performance.get("sharpe_ratio"))
    profit_factor = safe_float(performance.get("profit_factor"))
    win_rate = safe_float(performance.get("win_rate_pct"))

    capped_pf = min(max(profit_factor, 0), 3.0)
    capped_sharpe = min(max(sharpe, -1.0), 3.0)
    capped_annual = min(max(annual_return, -30.0), 50.0)
    capped_return = min(max(total_return, -50.0), 100.0)
    capped_dd = min(max(max_drawdown, 0), 50.0)

    score = (
        capped_pf * 22.0
        + capped_sharpe * 18.0
        + capped_annual * 1.4
        + capped_return * 0.25
        + win_rate * 0.10
        - capped_dd * 1.8
    )

    if trade_count < MINIMUM_TRADES:
        shortage = MINIMUM_TRADES - trade_count
        score -= shortage * 2.5
        status = "取引不足"
    elif profit_factor < 1.0:
        score -= 15.0
        status = "PF不足"
    elif max_drawdown > 20:
        score -= 15.0
        status = "DD過大"
    else:
        status = "有効"

    return round(score, 6), status


def run_optimization(
    raw_histories: dict[str, pd.DataFrame],
    names: dict[str, str],
    parameter_grid: list[StrategyParameters],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    total = len(parameter_grid)

    print()
    print("=" * 110)
    print("PHOENIX v6.0.1 OPTIMIZATION")
    print("=" * 110)
    print(f"探索組み合わせ: {total}")

    indicator_cache: dict[tuple[int, int, int], dict[str, pd.DataFrame]] = {}

    for number, params in enumerate(parameter_grid, start=1):
        ma_key = (
            params.ma_short,
            params.ma_mid,
            params.ma_long,
        )

        if ma_key not in indicator_cache:
            indicator_cache[ma_key] = {
                ticker: add_indicators(history, params)
                for ticker, history in raw_histories.items()
            }

        histories = indicator_cache[ma_key]

        _, _, summary = run_backtest(
            histories,
            names,
            params,
        )

        performance = summary.get("performance", {})
        optimization_score, status = calculate_optimization_score(
            performance
        )

        row = {
            "rank": 0,
            "optimization_score": optimization_score,
            "status": status,
            **asdict(params),
            "trade_count": safe_int(
                performance.get("trade_count")
            ),
            "win_rate_pct": safe_float(
                performance.get("win_rate_pct")
            ),
            "profit_factor": safe_float(
                performance.get("profit_factor")
            ),
            "total_return_pct": safe_float(
                performance.get("total_return_pct")
            ),
            "annual_return_pct": safe_float(
                performance.get("annual_return_pct")
            ),
            "max_drawdown_pct": safe_float(
                performance.get("max_drawdown_pct")
            ),
            "sharpe_ratio": safe_float(
                performance.get("sharpe_ratio")
            ),
            "average_return_pct": safe_float(
                performance.get("average_return_pct")
            ),
            "average_holding_days": safe_float(
                performance.get("average_holding_days")
            ),
            "final_equity_yen": safe_float(
                performance.get(
                    "final_equity_yen",
                    ACCOUNT_CAPITAL,
                )
            ),
        }
        rows.append(row)

        print(
            f"[{number:>4}/{total}] "
            f"Score={optimization_score:>7.2f} "
            f"PF={row['profit_factor']:.3f} "
            f"Sharpe={row['sharpe_ratio']:.3f} "
            f"DD={row['max_drawdown_pct']:.2f}% "
            f"Trades={row['trade_count']}"
        )

    results = pd.DataFrame(rows)

    if results.empty:
        raise RuntimeError("最適化結果がありません。")

    results = results.sort_values(
        by=[
            "optimization_score",
            "profit_factor",
            "sharpe_ratio",
            "annual_return_pct",
            "trade_count",
        ],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)

    results["rank"] = range(1, len(results) + 1)

    return results


def build_best_payload(
    results: pd.DataFrame,
    period: str,
    max_tickers: int,
    downloaded_tickers: list[str],
) -> dict[str, Any]:
    best = results.iloc[0].to_dict()

    parameters = {
        "rsi_min": safe_float(best["rsi_min"]),
        "rsi_max": safe_float(best["rsi_max"]),
        "stop_atr_multiplier": safe_float(
            best["stop_atr_multiplier"]
        ),
        "target_r_multiplier": safe_float(
            best["target_r_multiplier"]
        ),
        "ma_short": safe_int(best["ma_short"]),
        "ma_mid": safe_int(best["ma_mid"]),
        "ma_long": safe_int(best["ma_long"]),
        "signal_score_threshold": safe_float(
            best["signal_score_threshold"]
        ),
        "max_hold_days": safe_int(best["max_hold_days"]),
    }

    performance = {
        "optimization_score": safe_float(
            best["optimization_score"]
        ),
        "status": str(best["status"]),
        "trade_count": safe_int(best["trade_count"]),
        "win_rate_pct": safe_float(best["win_rate_pct"]),
        "profit_factor": safe_float(best["profit_factor"]),
        "total_return_pct": safe_float(
            best["total_return_pct"]
        ),
        "annual_return_pct": safe_float(
            best["annual_return_pct"]
        ),
        "max_drawdown_pct": safe_float(
            best["max_drawdown_pct"]
        ),
        "sharpe_ratio": safe_float(best["sharpe_ratio"]),
        "average_return_pct": safe_float(
            best["average_return_pct"]
        ),
        "average_holding_days": safe_float(
            best["average_holding_days"]
        ),
        "final_equity_yen": safe_float(
            best["final_equity_yen"]
        ),
    }

    return {
        "version": "PHOENIX v6.0",
        "generated_at": now_text(),
        "period": period,
        "maximum_tickers": max_tickers,
        "downloaded_tickers": downloaded_tickers,
        "tested_combinations": len(results),
        "parameters": parameters,
        "performance": performance,
    }


def update_ai_parameter(best_payload: dict[str, Any]) -> None:
    current: dict[str, Any] = {}

    if AI_PARAMETER_FILE.exists():
        try:
            loaded = json.loads(
                AI_PARAMETER_FILE.read_text(encoding="utf-8")
            )
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, json.JSONDecodeError):
            current = {}

    current["version"] = "PHOENIX v6.0"
    current["updated_at"] = now_text()
    current["source"] = "optimization_engine"
    current["optimization"] = {
        "parameters": best_payload["parameters"],
        "performance": best_payload["performance"],
        "period": best_payload["period"],
        "tested_combinations": best_payload[
            "tested_combinations"
        ],
    }

    # 他エンジンが読みやすいよう、主要値はトップレベルにも保存。
    current.update(best_payload["parameters"])

    save_json(AI_PARAMETER_FILE, current)


def save_outputs(
    results: pd.DataFrame,
    best_payload: dict[str, Any],
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    results.to_csv(
        RESULTS_FILE,
        index=False,
        encoding="utf-8-sig",
    )
    save_json(BEST_FILE, best_payload)
    update_ai_parameter(best_payload)

    params = best_payload["parameters"]
    performance = best_payload["performance"]

    lines = [
        "PHOENIX v6.0.1 OPTIMIZATION REPORT",
        "=" * 110,
        f"生成時刻       : {best_payload['generated_at']}",
        f"検証期間       : {best_payload['period']}",
        f"検証銘柄数     : {len(best_payload['downloaded_tickers'])}",
        f"探索組み合わせ : {best_payload['tested_combinations']}",
        "",
        "BEST PARAMETERS",
        "=" * 110,
        f"RSI            : {params['rsi_min']:.1f} ～ {params['rsi_max']:.1f}",
        f"ATR損切倍率    : {params['stop_atr_multiplier']:.2f}",
        f"利確R倍率      : {params['target_r_multiplier']:.2f}",
        f"MA             : {params['ma_short']} / {params['ma_mid']} / {params['ma_long']}",
        f"シグナル点数   : {params['signal_score_threshold']:.1f}",
        f"最大保有日数   : {params['max_hold_days']}日",
        "",
        "EXPECTED PERFORMANCE",
        "=" * 110,
        f"Optimization   : {performance['optimization_score']:.3f}",
        f"状態           : {performance['status']}",
        f"取引回数       : {performance['trade_count']}回",
        f"勝率           : {performance['win_rate_pct']:.2f}%",
        f"Profit Factor  : {performance['profit_factor']:.3f}",
        f"総リターン     : {performance['total_return_pct']:+.2f}%",
        f"年率リターン   : {performance['annual_return_pct']:+.2f}%",
        f"最大DD         : {performance['max_drawdown_pct']:.2f}%",
        f"Sharpe         : {performance['sharpe_ratio']:.3f}",
        "",
        "注意:",
        "最適化結果は過去データに対する成績であり、将来利益を保証しません。",
        "過学習を避けるため、今後は期間分割検証を追加する必要があります。",
    ]

    REPORT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def print_best(best_payload: dict[str, Any]) -> None:
    params = best_payload["parameters"]
    performance = best_payload["performance"]

    print()
    print("=" * 110)
    print("PHOENIX v6.0.1 OPTIMIZATION BEST")
    print("=" * 110)
    print(f"RSI            : {params['rsi_min']:.1f} ～ {params['rsi_max']:.1f}")
    print(f"ATR損切倍率    : {params['stop_atr_multiplier']:.2f}")
    print(f"利確R倍率      : {params['target_r_multiplier']:.2f}")
    print(
        f"MA             : "
        f"{params['ma_short']} / "
        f"{params['ma_mid']} / "
        f"{params['ma_long']}"
    )
    print(f"シグナル点数   : {params['signal_score_threshold']:.1f}")
    print(f"最大保有日数   : {params['max_hold_days']}日")
    print()
    print(f"Optimization   : {performance['optimization_score']:.3f}")
    print(f"取引回数       : {performance['trade_count']}回")
    print(f"勝率           : {performance['win_rate_pct']:.2f}%")
    print(f"Profit Factor  : {performance['profit_factor']:.3f}")
    print(f"総リターン     : {performance['total_return_pct']:+.2f}%")
    print(f"年率リターン   : {performance['annual_return_pct']:+.2f}%")
    print(f"最大DD         : {performance['max_drawdown_pct']:.2f}%")
    print(f"Sharpe         : {performance['sharpe_ratio']:.3f}")
    print()
    print(f"保存完了: {RESULTS_FILE}")
    print(f"保存完了: {BEST_FILE}")
    print(f"保存完了: {REPORT_FILE}")
    print(f"更新完了: {AI_PARAMETER_FILE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PHOENIX Optimization Engine"
    )
    parser.add_argument(
        "--period",
        choices=("1y", "3y", "5y"),
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
        help="0を指定すると全組み合わせを実行。",
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
        selected_parameters = select_parameter_grid(
            all_parameters,
            args.max_combinations,
        )

        results = run_optimization(
            raw_histories,
            names,
            selected_parameters,
        )

        best_payload = build_best_payload(
            results=results,
            period=args.period,
            max_tickers=max(args.max_tickers, 1),
            downloaded_tickers=list(raw_histories.keys()),
        )

        save_outputs(results, best_payload)
        print_best(best_payload)

    except Exception as error:
        print(f"Optimization Engineエラー: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
