from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import phoenix_core.historical_validation_20y as hv

ROOT = Path(__file__).resolve().parents[2]
START = "2016-08"
END = "2026-08"
OUT = ROOT / "state" / "validation_runtime"
OUT.mkdir(parents=True, exist_ok=True)

settings = hv.load_settings(ROOT, "config/v7_historical_validation_20y.json")
config = hv._build_historical_validation_config(settings)
checked = hv._as_jst(None)
start_date, end_date = hv._normalize_requested_range(START, END, as_of=checked)
fetch_start = (pd.Timestamp(start_date) - pd.offsets.BDay(config.minimum_history_sessions + 20)).date()
cache_root = hv.resolve_within(ROOT, settings["cache_dir"])
universe = hv._load_universe_from_csv(
    ROOT, settings["universe_csv"], enforce_nikkei225=True, expected_ticker_count=225
)
registry: set[tuple[str, object, object]] = set()
fetched = []
for entry in universe.to_dict(orient="records"):
    outcome = hv.fetch_ticker_history(
        ROOT,
        entry["ticker"],
        fetch_start,
        end_date,
        cache_dir=cache_root,
        as_of=checked,
        allow_network_fetch=False,
        download_registry=registry,
    )
    fetched.append((entry, outcome))

histories = {entry["ticker"]: outcome.history for entry, outcome in fetched}
prepared = hv.prepare_histories(histories, config)

for ticker, frame in prepared.items():
    if frame.empty:
        continue
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise RuntimeError(f"{ticker}: index is not DatetimeIndex")
    if frame.index.tz is not None or not frame.index.is_monotonic_increasing:
        raise RuntimeError(f"{ticker}: index not normalized/sorted")
    if frame.index.has_duplicates or not frame.index.equals(frame.index.normalize()):
        raise RuntimeError(f"{ticker}: duplicate/non-normalized index")
benchmark = hv.fetch_ticker_history(
    ROOT,
    settings.get("benchmark_ticker", "^N225"),
    fetch_start,
    end_date,
    cache_dir=cache_root,
    as_of=checked,
    allow_network_fetch=True,
    download_registry=registry,
)
if benchmark.history.empty:
    raise RuntimeError("Benchmark history unavailable")
bench_ret20 = benchmark.history["Close"].pct_change(20) * 100.0

augmented: dict[str, pd.DataFrame] = {}
for ticker, frame in prepared.items():
    work = frame.copy()
    if not work.empty:
        work["PRIOR_HIGH_20"] = work["High"].rolling(20, min_periods=20).max().shift(1)
        work["ATR_PCT"] = work["ATR"] / work["Close"].replace(0, np.nan) * 100.0
        work["ATR_PCT_MED60"] = work["ATR_PCT"].rolling(60, min_periods=40).median().shift(1)
        work["VOL_EXP_RATIO"] = work["ATR_PCT"] / work["ATR_PCT_MED60"].replace(0, np.nan)
        work["BENCH_RETURN_20D"] = bench_ret20.reindex(work.index)
        work["RELATIVE_20D"] = work["RETURN_20D"] - work["BENCH_RETURN_20D"]
    augmented[ticker] = work

sf = hv.safe_float
original_entry = hv.is_entry_signal
original_score = hv.signal_score
original_normalize = hv.normalize_history_frame
def atr_ok(row: pd.Series) -> bool:
    return sf(row.get("ATR")) > 0


def trend_entry(row: pd.Series, params) -> bool:
    close = sf(row.get("Close"))
    ma_s = sf(row.get("MA_SHORT"))
    ma_m = sf(row.get("MA_MID"))
    ma_l = sf(row.get("MA_LONG"))
    rsi = sf(row.get("RSI"), 50)
    macd = sf(row.get("MACD"))
    macd_sig = sf(row.get("MACD_SIGNAL"))
    ret20 = sf(row.get("RETURN_20D"))
    return close > ma_m > ma_l > 0 and ma_s > ma_m and macd > macd_sig and ret20 > 0 and 45 <= rsi <= 70 and atr_ok(row)


def trend_score(row: pd.Series, params) -> float:
    close = sf(row.get("Close")); ma_s = sf(row.get("MA_SHORT")); ma_m = sf(row.get("MA_MID")); ma_l = sf(row.get("MA_LONG"))
    macd = sf(row.get("MACD")); macd_sig = sf(row.get("MACD_SIGNAL")); ret20 = max(sf(row.get("RETURN_20D")), 0)
    return round(min(100.0, 40 * (close > ma_m > ma_l > 0) + 20 * (ma_s > ma_m) + 20 * (macd > macd_sig) + min(ret20, 20)), 2)


def relative_entry(row: pd.Series, params) -> bool:
    close = sf(row.get("Close")); ma_m = sf(row.get("MA_MID")); ma_l = sf(row.get("MA_LONG"))
    rsi = sf(row.get("RSI"), 50); rel = sf(row.get("RELATIVE_20D"))
    return rel > 0 and close > ma_m > ma_l > 0 and 45 <= rsi <= 72 and atr_ok(row)


def relative_score(row: pd.Series, params) -> float:
    rel = max(sf(row.get("RELATIVE_20D")), 0.0)
    ret20 = max(sf(row.get("RETURN_20D")), 0.0)
    vr = max(sf(row.get("VOLUME_RATIO")), 0.0)
    return round(min(100.0, 55.0 + min(rel * 3.0, 25.0) + min(ret20, 10.0) + min(vr * 4.0, 10.0)), 2)


def volume_entry(row: pd.Series, params) -> bool:
    vr = sf(row.get("VOLUME_RATIO"))
    close = sf(row.get("Close")); ma_m = sf(row.get("MA_MID"))
    ret5 = sf(row.get("RETURN_5D")); rsi = sf(row.get("RSI"), 50)
    return vr >= 1.5 and close > ma_m > 0 and ret5 > 0 and 40 <= rsi <= 75 and atr_ok(row)


def volume_score(row: pd.Series, params) -> float:
    vr = max(sf(row.get("VOLUME_RATIO")), 0.0)
    ret5 = max(sf(row.get("RETURN_5D")), 0.0)
    return round(min(100.0, 50.0 + min(vr * 15.0, 35.0) + min(ret5 * 2.0, 15.0)), 2)


def pullback_entry(row: pd.Series, params) -> bool:
    close = sf(row.get("Close")); ma_s = sf(row.get("MA_SHORT")); ma_m = sf(row.get("MA_MID")); ma_l = sf(row.get("MA_LONG"))
    rsi = sf(row.get("RSI"), 50); ret20 = sf(row.get("RETURN_20D"))
    return ma_m > ma_l > 0 and close > ma_l and close <= ma_s * 1.01 and close >= ma_m * 0.97 and ret20 > 0 and 35 <= rsi <= 52 and atr_ok(row)


def pullback_score(row: pd.Series, params) -> float:
    rsi = sf(row.get("RSI"), 50); close = sf(row.get("Close")); ma_m = sf(row.get("MA_MID"))
    dist = abs(close / ma_m - 1.0) * 100.0 if ma_m > 0 else 99.0
    return round(max(0.0, min(100.0, 85.0 - abs(rsi - 44.0) * 2.0 - dist * 3.0)), 2)


def breakout_entry(row: pd.Series, params) -> bool:
    close = sf(row.get("Close")); prior_high = sf(row.get("PRIOR_HIGH_20"))
    vr = sf(row.get("VOLUME_RATIO")); rsi = sf(row.get("RSI"), 50)
    return prior_high > 0 and close > prior_high and vr >= 1.2 and 45 <= rsi <= 78 and atr_ok(row)


def breakout_score(row: pd.Series, params) -> float:
    close = sf(row.get("Close")); prior_high = sf(row.get("PRIOR_HIGH_20")); vr = max(sf(row.get("VOLUME_RATIO")), 0.0)
    breakout_pct = max((close / prior_high - 1.0) * 100.0, 0.0) if prior_high > 0 else 0.0
    return round(min(100.0, 60.0 + min(breakout_pct * 5.0, 20.0) + min(vr * 8.0, 20.0)), 2)


def vol_entry(row: pd.Series, params) -> bool:
    ratio = sf(row.get("VOL_EXP_RATIO")); close = sf(row.get("Close")); ma_m = sf(row.get("MA_MID"))
    ret5 = sf(row.get("RETURN_5D")); rsi = sf(row.get("RSI"), 50)
    return ratio >= 1.25 and close > ma_m > 0 and ret5 > 0 and 42 <= rsi <= 75 and atr_ok(row)


def vol_score(row: pd.Series, params) -> float:
    ratio = max(sf(row.get("VOL_EXP_RATIO")), 0.0); ret5 = max(sf(row.get("RETURN_5D")), 0.0)
    return round(min(100.0, 50.0 + min((ratio - 1.0) * 60.0, 35.0) + min(ret5 * 2.0, 15.0)), 2)


STRATEGIES = {
    "CONTROL": (original_entry, original_score),
    "TREND_MOMENTUM": (trend_entry, trend_score),
    "RELATIVE_STRENGTH": (relative_entry, relative_score),
    "VOLUME_ANOMALY": (volume_entry, volume_score),
    "PULLBACK_MEAN_REVERSION": (pullback_entry, pullback_score),
    "BREAKOUT_20D": (breakout_entry, breakout_score),
    "VOLATILITY_EXPANSION": (vol_entry, vol_score),
}


def expectation_metrics(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {"expectancy_yen": 0.0, "gross_turnover_yen": 0.0, "total_fees_yen": 0.0}
    profits = pd.to_numeric(trades["profit_yen"], errors="coerce").fillna(0.0)
    turnover = pd.to_numeric(trades["entry_cost_yen"], errors="coerce").fillna(0.0).sum()
    turnover += pd.to_numeric(trades["exit_value_yen"], errors="coerce").fillna(0.0).sum()
    fees = pd.to_numeric(trades["fees_yen"], errors="coerce").fillna(0.0).sum()
    return {
        "expectancy_yen": round(float(profits.mean()), 2),
        "gross_turnover_yen": round(float(turnover), 2),
        "total_fees_yen": round(float(fees), 2),
    }


def run_one(name: str, entry_fn, score_fn) -> tuple[dict[str, object], hv.HistoricalValidationResult]:
    hv.is_entry_signal = entry_fn
    hv.signal_score = score_fn
    hv.normalize_history_frame = lambda frame: frame
    result = hv.simulate_validation(augmented, universe, config, start_date, end_date)
    perf = hv._summarize_simulation_result(result, config.initial_capital_yen)
    perf.update(expectation_metrics(result.trades))
    perf["strategy"] = name
    if not result.equity_curve.empty:
        avg_equity = pd.to_numeric(result.equity_curve["equity_yen"], errors="coerce").mean()
        perf["turnover_multiple"] = round(perf["gross_turnover_yen"] / avg_equity, 4) if avg_equity > 0 else 0.0
    else:
        perf["turnover_multiple"] = 0.0
    return perf, result


rows = []
for name, (entry_fn, score_fn) in STRATEGIES.items():
    print(f"RUN {name}", flush=True)
    perf, result = run_one(name, entry_fn, score_fn)
    rows.append(perf)
    result.trades.to_csv(OUT / f"10y_{name.lower()}_trades.csv", index=False, encoding="utf-8-sig")
    print(name, perf["CAGR"], perf["max_drawdown"], perf["trade_count"], perf["profit_factor"], flush=True)

hv.is_entry_signal = original_entry
hv.signal_score = original_score
hv.normalize_history_frame = original_normalize


comparison = pd.DataFrame(rows)
columns = [
    "strategy", "final_equity", "total_return", "CAGR", "max_drawdown",
    "trade_count", "win_rate", "profit_factor", "expectancy_yen",
    "avg_holding", "gross_turnover_yen", "turnover_multiple", "total_fees_yen",
    "sharpe_ratio", "sortino_ratio", "calmar_ratio",
]
comparison = comparison[[column for column in columns if column in comparison.columns]]
comparison = comparison.sort_values(["CAGR", "max_drawdown"], ascending=[False, True])
comparison.to_csv(OUT / "strategy_tournament_10y_comparison.csv", index=False, encoding="utf-8-sig")
summary = {
    "requested_start": str(start_date),
    "requested_end": str(end_date),
    "initial_capital_yen": config.initial_capital_yen,
    "available_tickers": int(sum(not frame.empty for frame in prepared.values())),
    "universe_rows": int(len(universe)),
    "missing_eligible_data": 12,
    "strategies": comparison.to_dict(orient="records"),
}
(OUT / "strategy_tournament_10y_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
print(comparison.to_string(index=False), flush=True)
