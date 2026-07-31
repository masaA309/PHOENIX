from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from phoenix_core.broker import PaperBroker
from phoenix_core.models import OrderRequest, OrderSide, OrderStatus, OrderType
from phoenix_core.performance_tracker import atomic_write
from phoenix_core.position_sizer import PositionSizingConfig, calculate_sizing
from phoenix_core.risk_controller import RiskConfig, RiskState, evaluate_orders
from phoenix_core.run_guard import SingleInstanceLock


EVIDENCE_KIND = "HISTORICAL_WALK_FORWARD_REPLAY"
REPLAY_SCOPE = "SURROGATE_TECHNICAL_BASELINE"
SEALED_HOLDOUT_STATUS = "NOT_ESTABLISHED"
EXECUTION_MODEL_STATUS = "PROVISIONAL_NO_DAILY_PRICE_LIMITS"
REQUIRED_PRICE_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")
REQUIRED_DATASETS = (
    "price_history",
    "historical_universe",
    "corporate_actions",
    "fundamentals",
    "shikiho",
)
IMPLEMENTED_DATASETS = frozenset({"price_history"})
JST = ZoneInfo("Asia/Tokyo")
MINIMUM_GATE_FLOORS = {
    "minimum_folds": 5,
    "minimum_oos_sessions": 250,
    "minimum_simulated_trades": 30,
    "minimum_profit_factor": 1.2,
    "minimum_successful_fold_rate": 0.6,
}
HISTORICAL_REPLAY_LOCK = "state/v7_historical_replay.lock"
REQUIRED_PROTECTED_FILES = (
    "state/v7_paper_broker.json",
    "state/v7_risk_state.json",
    "state/v7_scheduler_state.json",
    "state/v7_market_data_guard.json",
    "state/v7_order_lifecycle_snapshot.json",
    "state/v7_order_lifecycle_events.jsonl",
    "reports/v7_run_history.jsonl",
)
REQUIRED_OUTPUT_PATHS = {
    "report_json": "reports/v7_historical_replay.json",
    "report_text": "reports/v7_historical_replay.txt",
    "folds_csv": "reports/v7_historical_replay_folds.csv",
    "trades_csv": "reports/v7_historical_replay_trades.csv",
}


class HistoricalReplayError(RuntimeError):
    pass


class HistoricalReplayLockError(HistoricalReplayError):
    pass


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    rsi_min: float = 40.0
    rsi_max: float = 72.0
    ma_short: int = 5
    ma_mid: int = 25
    ma_long: int = 75
    signal_score_threshold: float = 70.0
    stop_atr_multiplier: float = 1.5
    target_r_multiplier: float = 2.0
    max_hold_sessions: int = 20

    def validate(self) -> None:
        numeric = asdict(self)
        if any(not math.isfinite(float(value)) for value in numeric.values()):
            raise ValueError("Strategy settings must be finite")
        if not 1 <= self.ma_short < self.ma_mid < self.ma_long:
            raise ValueError("Moving-average periods must satisfy short < mid < long")
        if not 0 <= self.rsi_min < self.rsi_max <= 100:
            raise ValueError("RSI range is invalid")
        if self.signal_score_threshold < 0:
            raise ValueError("Signal threshold must be non-negative")
        if self.stop_atr_multiplier <= 0 or self.target_r_multiplier <= 0:
            raise ValueError("ATR stop and target multipliers must be positive")
        if self.max_hold_sessions <= 0:
            raise ValueError("max_hold_sessions must be positive")


@dataclass(slots=True)
class ReplayPosition:
    ticker: str
    signal_date: str
    entry_date: str
    entry_price: float
    quantity: int
    stop_price: float
    target_price: float
    signal_score: float
    holding_sessions: int = 0


def resolve_within(root: Path, value: str) -> Path:
    candidate = Path(value)
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    root_resolved = root.resolve()
    try:
        path.relative_to(root_resolved)
    except ValueError as error:
        raise ValueError(f"Path escapes repository root: {value}") from error
    return path


def read_json_object(path: Path) -> dict[str, Any]:
    value, _ = read_json_object_with_hash(path)
    return value


def read_json_object_with_hash(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    try:
        content = path.read_bytes()
        value = json.loads(content.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read JSON object: {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value, hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def capture_files(root: Path, values: Iterable[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in values:
        path = resolve_within(root, str(raw))
        relative = path.relative_to(root.resolve()).as_posix()
        if path.is_file():
            result[relative] = {
                "exists": True,
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        else:
            result[relative] = {"exists": False, "size": 0, "sha256": None}
    return dict(sorted(result.items()))


def files_unchanged(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
) -> bool:
    return dict(before) == dict(after)


def _parse_aware_timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"Invalid {field}: {value}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone: {value}")
    return parsed.astimezone(JST)


def records_available_as_of(
    records: Iterable[Mapping[str, Any]],
    decision_at: datetime,
    available_field: str = "available_at",
) -> list[dict[str, Any]]:
    decision = _parse_aware_timestamp(decision_at, "decision_at")
    available: list[dict[str, Any]] = []
    for record in records:
        if available_field not in record:
            raise ValueError(f"Missing {available_field} in point-in-time record")
        published = _parse_aware_timestamp(record[available_field], available_field)
        if published <= decision:
            available.append(dict(record))
    return available


def assess_manifest(
    manifest: Mapping[str, Any],
    implemented_datasets: Iterable[str] = IMPLEMENTED_DATASETS,
) -> list[str]:
    blockers: list[str] = []
    implemented = frozenset(str(value) for value in implemented_datasets)
    if int(manifest.get("schema_version", 0) or 0) != 1:
        blockers.append("Point-in-time manifest schema_version must be 1")
    if manifest.get("timezone") != "Asia/Tokyo":
        blockers.append("Point-in-time manifest timezone must be Asia/Tokyo")
    datasets = manifest.get("datasets", {})
    if not isinstance(datasets, Mapping):
        return blockers + ["Point-in-time manifest datasets must be an object"]
    for name in REQUIRED_DATASETS:
        raw = datasets.get(name)
        if not isinstance(raw, Mapping):
            blockers.append(f"Required dataset definition is missing: {name}")
            continue
        if raw.get("required") is not True:
            blockers.append(f"Required dataset cannot be disabled: {name}")
        if raw.get("available") is not True:
            blockers.append(f"Required dataset is unavailable: {name}")
        if raw.get("point_in_time_verified") is not True:
            blockers.append(f"Point-in-time provenance is not verified: {name}")
        if raw.get("used_by_replay") is not True:
            blockers.append(f"Required dataset is not consumed by replay: {name}")
        if name not in implemented:
            blockers.append(f"Point-in-time dataset ingestion is not implemented: {name}")
        if not str(raw.get("source") or "").strip():
            blockers.append(f"Dataset source is missing: {name}")
        if not str(raw.get("path") or "").strip():
            blockers.append(f"Dataset path is missing: {name}")
        if name != "price_history" and not str(raw.get("available_at_field") or "").strip():
            blockers.append(f"Publication/availability field is missing: {name}")
    shikiho = datasets.get("shikiho", {})
    if isinstance(shikiho, Mapping) and shikiho.get("license_confirmed") is not True:
        blockers.append("Licensed use of historical Shikiho data is not confirmed")
    return list(dict.fromkeys(blockers))


def _price_paths(root: Path, pattern: str) -> list[Path]:
    raw = Path(pattern)
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("price_glob must be a repository-relative safe pattern")
    matches = sorted(root.glob(pattern))
    if not matches:
        raise HistoricalReplayError(f"No historical price files matched: {pattern}")
    paths: list[Path] = []
    seen: set[str] = set()
    seen_file_ids: set[tuple[int, int]] = set()
    for lexical_path in matches:
        if not lexical_path.is_file():
            raise HistoricalReplayError(
                f"Historical price match is not a regular file: {lexical_path}"
            )
        resolved_path = resolve_within(root, str(lexical_path))
        lexical_absolute = lexical_path.absolute()
        if str(resolved_path).casefold() != str(lexical_absolute).casefold():
            raise HistoricalReplayError(
                f"Symbolic/reparse aliases are forbidden for price inputs: {lexical_path}"
            )
        stat_result = lexical_path.stat()
        file_id = (int(stat_result.st_dev), int(stat_result.st_ino))
        if stat_result.st_nlink > 1 or file_id in seen_file_ids:
            raise HistoricalReplayError(
                f"Hard-link aliases are forbidden for price inputs: {lexical_path}"
            )
        seen_file_ids.add(file_id)
        key = resolved_path.as_posix().casefold()
        if key in seen:
            raise HistoricalReplayError(
                f"Duplicate canonical historical price input: {lexical_path}"
            )
        seen.add(key)
        paths.append(resolved_path)
    if not paths:
        raise HistoricalReplayError(f"No historical price files matched: {pattern}")
    return paths


def _ticker_from_path(path: Path) -> str:
    stem = path.stem.upper()
    if stem.endswith("_T"):
        return f"{stem[:-2]}.T"
    return stem.replace("_", ".")


def load_price_file(path: Path, content: bytes | None = None) -> pd.DataFrame:
    try:
        actual_content = path.read_bytes() if content is None else content
        frame = pd.read_csv(io.BytesIO(actual_content))
    except (OSError, UnicodeError, pd.errors.ParserError) as error:
        raise HistoricalReplayError(f"Could not parse price file {path}: {error}") from error
    if frame.empty:
        raise HistoricalReplayError(f"Price file is empty: {path}")
    if frame.columns.duplicated().any():
        raise HistoricalReplayError(f"Duplicate columns in price file: {path}")
    missing = [name for name in REQUIRED_PRICE_COLUMNS if name not in frame.columns]
    if missing:
        raise HistoricalReplayError(f"Missing columns in {path}: {missing}")
    if len(frame.columns) != len(REQUIRED_PRICE_COLUMNS):
        unexpected = [name for name in frame.columns if name not in REQUIRED_PRICE_COLUMNS]
        raise HistoricalReplayError(f"Unexpected columns in {path}: {unexpected}")
    dates = pd.to_datetime(frame["Date"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise HistoricalReplayError(f"Invalid date in price file: {path}")
    if dates.duplicated().any():
        raise HistoricalReplayError(f"Duplicate session date in price file: {path}")
    if not dates.is_monotonic_increasing:
        raise HistoricalReplayError(f"Session dates are not strictly increasing: {path}")
    numeric = frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]].apply(
        pd.to_numeric,
        errors="coerce",
    )
    values = numeric.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise HistoricalReplayError(f"Non-finite price value in: {path}")
    if (numeric[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise HistoricalReplayError(f"Non-positive OHLC value in: {path}")
    if (numeric["Volume"] < 0).any():
        raise HistoricalReplayError(f"Negative volume in: {path}")
    tolerance = numeric[["Open", "High", "Low", "Close"]].abs().max(axis=1) * 1e-10 + 1e-8
    if (numeric["High"] + tolerance < numeric[["Open", "Low", "Close"]].max(axis=1)).any():
        raise HistoricalReplayError(f"High is below another OHLC value in: {path}")
    if (numeric["Low"] - tolerance > numeric[["Open", "High", "Close"]].min(axis=1)).any():
        raise HistoricalReplayError(f"Low is above another OHLC value in: {path}")
    result = numeric.copy()
    result.index = pd.DatetimeIndex(dates).normalize()
    result.index.name = "Date"
    return result


def load_price_history(root: Path, pattern: str) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    histories: dict[str, pd.DataFrame] = {}
    hashes: dict[str, str] = {}
    for path in _price_paths(root, pattern):
        ticker = _ticker_from_path(path)
        if ticker in histories:
            raise HistoricalReplayError(f"Duplicate ticker price history: {ticker}")
        content = path.read_bytes()
        histories[ticker] = load_price_file(path, content)
        hashes[path.relative_to(root).as_posix()] = hashlib.sha256(content).hexdigest()
    return dict(sorted(histories.items())), dict(sorted(hashes.items()))


def add_causal_indicators(frame: pd.DataFrame, strategy: StrategyConfig) -> pd.DataFrame:
    strategy.validate()
    result = frame.copy()
    result["MA_SHORT"] = result["Close"].rolling(strategy.ma_short).mean()
    result["MA_MID"] = result["Close"].rolling(strategy.ma_mid).mean()
    result["MA_LONG"] = result["Close"].rolling(strategy.ma_long).mean()
    delta = result["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    average_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = average_gain / average_loss.replace(0, np.nan)
    result["RSI"] = (100 - (100 / (1 + rs))).fillna(50)
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
    result["RETURN_20D"] = result["Close"].pct_change(20) * 100
    return result


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def score_signal(row: Mapping[str, Any], strategy: StrategyConfig) -> float:
    score = 0.0
    close = _finite(row.get("Close"))
    ma_short = _finite(row.get("MA_SHORT"))
    ma_mid = _finite(row.get("MA_MID"))
    ma_long = _finite(row.get("MA_LONG"))
    rsi = _finite(row.get("RSI"), 50.0)
    if close > ma_mid > 0:
        score += 20
    if ma_short > ma_mid > 0:
        score += 20
    if ma_mid > ma_long > 0:
        score += 20
    if _finite(row.get("MACD")) > _finite(row.get("MACD_SIGNAL")):
        score += 15
    rsi_center = (strategy.rsi_min + strategy.rsi_max) / 2
    rsi_half_range = max((strategy.rsi_max - strategy.rsi_min) / 2, 1)
    if strategy.rsi_min <= rsi <= strategy.rsi_max:
        distance_ratio = abs(rsi - rsi_center) / rsi_half_range
        score += max(5.0, 15.0 * (1.0 - 0.35 * distance_ratio))
    elif strategy.rsi_min - 5 <= rsi < strategy.rsi_min:
        score += 6
    if _finite(row.get("VOLUME_RATIO")) >= 1.2:
        score += 5
    if _finite(row.get("RETURN_20D")) > 0:
        score += 5
    return round(score, 2)


def signal_at(
    ticker: str,
    frame: pd.DataFrame,
    decision_date: pd.Timestamp,
    strategy: StrategyConfig,
    minimum_history_sessions: int,
) -> dict[str, Any] | None:
    if decision_date not in frame.index:
        return None
    location = frame.index.get_loc(decision_date)
    if not isinstance(location, (int, np.integer)) or location < minimum_history_sessions - 1:
        return None
    row = frame.iloc[int(location)]
    score = score_signal(row, strategy)
    rsi = _finite(row.get("RSI"), 50.0)
    atr = _finite(row.get("ATR"))
    if (
        score < strategy.signal_score_threshold
        or not strategy.rsi_min <= rsi <= strategy.rsi_max
        or atr <= 0
    ):
        return None
    decision_at = datetime.combine(
        decision_date.date(),
        datetime.min.time().replace(hour=15, minute=30),
        tzinfo=JST,
    )
    return {
        "ticker": ticker,
        "decision_date": decision_date.strftime("%Y-%m-%d"),
        "decision_at": decision_at.isoformat(),
        "score": score,
        "atr": round(atr, 8),
        "average_volume_20d": round(_finite(row.get("VOLUME_MA20")), 8),
    }


def build_walk_forward_folds(
    sessions: Iterable[pd.Timestamp],
    train_sessions: int,
    test_sessions: int,
    step_sessions: int,
) -> list[dict[str, Any]]:
    dates = sorted({pd.Timestamp(value).normalize() for value in sessions})
    if train_sessions <= 0 or test_sessions <= 0 or step_sessions <= 0:
        raise ValueError("Walk-forward session counts must be positive")
    if step_sessions < test_sessions:
        raise ValueError("Overlapping out-of-sample windows are forbidden")
    folds: list[dict[str, Any]] = []
    test_start = train_sessions
    number = 1
    while test_start + test_sessions <= len(dates):
        train_values = dates[test_start - train_sessions : test_start]
        test_values = dates[test_start : test_start + test_sessions]
        folds.append(
            {
                "fold": number,
                "train_start": train_values[0],
                "train_end": train_values[-1],
                "train_dates": tuple(train_values),
                "test_start": test_values[0],
                "test_end": test_values[-1],
                "test_dates": tuple(test_values),
            }
        )
        number += 1
        test_start += step_sessions
    return folds


def _submit_exit(
    broker: PaperBroker,
    position: ReplayPosition,
    exit_date: pd.Timestamp,
    exit_price: float,
    reason: str,
    fold_number: int,
    commission_rate: float,
) -> dict[str, Any]:
    order = OrderRequest(
        ticker=position.ticker,
        side=OrderSide.SELL,
        quantity=position.quantity,
        order_type=OrderType.LIMIT,
        limit_price=round(exit_price, 2),
        client_order_id=f"HIST-F{fold_number:02d}-{exit_date:%Y%m%d}-{position.ticker}-SELL",
        strategy_name="PHOENIX_V7_HISTORICAL_REPLAY",
        metadata={"reason": reason},
    )
    result = broker.submit_order(order)
    if result.status is not OrderStatus.FILLED:
        raise HistoricalReplayError(f"Simulated exit was rejected: {position.ticker}: {result.message}")
    fees = (position.entry_price + result.filled_price) * position.quantity * commission_rate
    profit = (result.filled_price - position.entry_price) * position.quantity - fees
    event = {
        "fold": fold_number,
        "ticker": position.ticker,
        "signal_date": position.signal_date,
        "entry_date": position.entry_date,
        "exit_date": exit_date.strftime("%Y-%m-%d"),
        "entry_price": round(position.entry_price, 2),
        "exit_price": round(result.filled_price, 2),
        "quantity": position.quantity,
        "profit_yen": round(profit, 2),
        "return_pct": round(
            profit / (position.entry_price * position.quantity) * 100,
            6,
        ),
        "holding_sessions": position.holding_sessions,
        "exit_reason": reason,
        "signal_score": position.signal_score,
    }
    event["event_id"] = canonical_sha256(event)[:24]
    return event


def _audit_entry_limits(snapshot: Any, risk: RiskConfig) -> list[str]:
    equity = max(float(snapshot.equity_yen), 0.0)
    if equity <= 0:
        return ["non_positive_equity"]
    violations: list[str] = []
    tolerance = 1e-8
    if snapshot.market_value_yen / equity > risk.max_total_invested_pct + tolerance:
        violations.append("max_total_invested_pct")
    if snapshot.cash_yen + tolerance < equity * risk.minimum_cash_reserve_pct:
        violations.append("minimum_cash_reserve_pct")
    if len(snapshot.positions) > risk.max_positions:
        violations.append("max_positions")
    for position in snapshot.positions:
        if position.market_value / equity > risk.max_single_position_pct + tolerance:
            violations.append(f"max_single_position_pct:{position.ticker}")
    return violations


def _metrics(trades: list[dict[str, Any]], equity: list[float], initial_cash: float) -> dict[str, Any]:
    profits = [float(item["profit_yen"]) for item in trades]
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = -sum(value for value in profits if value < 0)
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = 99.0
    else:
        profit_factor = 0.0
    peak = initial_cash
    maximum_drawdown = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            maximum_drawdown = max(maximum_drawdown, (peak - value) / peak * 100)
    final_equity = equity[-1] if equity else initial_cash
    return {
        "trade_count": len(trades),
        "win_count": sum(value > 0 for value in profits),
        "loss_count": sum(value < 0 for value in profits),
        "gross_profit_yen": round(gross_profit, 2),
        "gross_loss_yen": round(gross_loss, 2),
        "net_profit_yen": round(sum(profits), 2),
        "profit_factor": round(profit_factor, 6),
        "total_return_pct": round((final_equity / initial_cash - 1) * 100, 6),
        "maximum_drawdown_pct": round(maximum_drawdown, 6),
        "final_equity_yen": round(final_equity, 2),
    }


def replay_fold(
    histories: Mapping[str, pd.DataFrame],
    fold: Mapping[str, Any],
    strategy: StrategyConfig,
    sizing: PositionSizingConfig,
    risk: RiskConfig,
    initial_cash_yen: float,
    commission_rate: float,
    entry_slippage_rate: float,
    exit_slippage_rate: float,
    maximum_volume_participation_rate: float,
    minimum_history_sessions: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    fold_number = int(fold["fold"])
    test_dates = tuple(pd.Timestamp(value) for value in fold["test_dates"])
    broker = PaperBroker(
        initial_cash_yen=initial_cash_yen,
        commission_rate=commission_rate,
        state_file=None,
    )
    positions: dict[str, ReplayPosition] = {}
    pending: dict[str, dict[str, Any]] = {}
    trades: list[dict[str, Any]] = []
    equity_values: list[float] = []
    risk_halt_dates: set[str] = set()
    risk_limit_violations: list[str] = []
    previous_date = pd.Timestamp(fold["train_end"])
    train_dates = tuple(pd.Timestamp(value) for value in fold["train_dates"])
    fold_histories: dict[str, pd.DataFrame] = dict(histories)
    for ticker, frame in histories.items():
        missing_train = [value for value in train_dates if value not in frame.index]
        if missing_train:
            raise HistoricalReplayError(
                f"Fold {fold_number} has {len(missing_train)} missing training price "
                f"sessions for {ticker}"
            )
        location = frame.index.get_loc(previous_date)
        if not isinstance(location, (int, np.integer)) or location < minimum_history_sessions - 1:
            raise HistoricalReplayError(
                f"Fold {fold_number} has insufficient training history for {ticker}"
            )
        signal = signal_at(ticker, frame, previous_date, strategy, minimum_history_sessions)
        if signal is not None:
            pending[ticker] = signal
    if not fold_histories:
        raise HistoricalReplayError(
            f"Fold {fold_number} has no point-in-time eligible price histories"
        )

    for current_date in test_dates:
        date_text = current_date.strftime("%Y-%m-%d")
        missing_tickers = sorted(
            ticker
            for ticker, frame in fold_histories.items()
            if current_date not in frame.index
        )
        if missing_tickers:
            raise HistoricalReplayError(
                f"Fold {fold_number} has missing price sessions on {date_text}: "
                + ", ".join(missing_tickers)
            )
        for ticker, position in list(positions.items()):
            frame = histories[ticker]
            if current_date in frame.index:
                broker.set_market_price(ticker, float(frame.loc[current_date, "Open"]))
        opening = broker.get_account_snapshot()
        state = risk_state_for_session(current_date, opening.equity_yen)

        for ticker, position in list(positions.items()):
            frame = histories[ticker]
            if current_date not in frame.index:
                continue
            row = frame.loc[current_date]
            open_price = float(row["Open"])
            exit_price = 0.0
            reason = ""
            if open_price <= position.stop_price:
                exit_price = open_price * (1 - exit_slippage_rate)
                reason = "STOP_GAP"
            elif open_price >= position.target_price:
                exit_price = open_price * (1 - exit_slippage_rate)
                reason = "TARGET_GAP"
            if reason:
                trade = _submit_exit(
                    broker, position, current_date, exit_price, reason,
                    fold_number, commission_rate,
                )
                trades.append(trade)
                state.consecutive_losses = state.consecutive_losses + 1 if trade["profit_yen"] < 0 else 0
                del positions[ticker]

        entry_candidates: list[tuple[float, str, float, float, str, float]] = []
        for ticker, signal in list(pending.items()):
            frame = histories[ticker]
            if current_date not in frame.index:
                continue
            del pending[ticker]
            if ticker in positions:
                continue
            open_price = float(frame.loc[current_date, "Open"])
            entry_price = open_price * (1 + entry_slippage_rate)
            stop_price = entry_price - float(signal["atr"]) * strategy.stop_atr_multiplier
            entry_candidates.append(
                (
                    float(signal["score"]), ticker, entry_price, stop_price,
                    str(signal["decision_date"]), float(signal["average_volume_20d"]),
                )
            )
        entry_candidates.sort(key=lambda item: (-item[0], item[1]))

        orders: list[OrderRequest] = []
        reserved_cash = 0.0
        reserved_market = 0.0
        signal_dates: dict[str, str] = {}
        for score, ticker, entry_price, stop_price, signal_date, known_average_volume in entry_candidates:
            decision = calculate_sizing(
                snapshot=broker.get_account_snapshot(),
                ticker=ticker,
                name=ticker,
                entry_price=entry_price,
                stop_price=stop_price,
                config=sizing,
                ranking_score=score,
                reserved_cash_yen=reserved_cash,
                reserved_market_value_yen=reserved_market,
            )
            if not decision.executable:
                continue
            liquidity_quantity = int(
                (known_average_volume * maximum_volume_participation_rate) // sizing.lot_size
            ) * sizing.lot_size
            order_quantity = min(decision.recommended_quantity, liquidity_quantity)
            if order_quantity < sizing.lot_size:
                continue
            order = OrderRequest(
                ticker=ticker,
                side=OrderSide.BUY,
                quantity=order_quantity,
                order_type=OrderType.LIMIT,
                limit_price=decision.entry_price,
                client_order_id=f"HIST-F{fold_number:02d}-{current_date:%Y%m%d}-{ticker}-BUY",
                strategy_name="PHOENIX_V7_HISTORICAL_REPLAY",
                metadata={
                    "stop_price": decision.stop_price,
                    "ranking_score": score,
                },
            )
            orders.append(order)
            signal_dates[ticker] = signal_date
            reserved_cost = order_quantity * decision.entry_price
            reserved_cash += reserved_cost * (1 + sizing.commission_buffer_pct)
            reserved_market += reserved_cost

        risk_report = evaluate_orders(broker, orders, risk, state)
        if risk_report.halted:
            risk_halt_dates.add(date_text)
        for order in risk_report.accepted_orders:
            violations_before = set(_audit_entry_limits(broker.get_account_snapshot(), risk))
            result = broker.submit_order(order)
            if result.status is not OrderStatus.FILLED:
                raise HistoricalReplayError(f"Simulated entry was rejected: {order.ticker}: {result.message}")
            stop_price = float(order.metadata["stop_price"])
            risk_distance = result.filled_price - stop_price
            positions[order.ticker] = ReplayPosition(
                ticker=order.ticker,
                signal_date=signal_dates[order.ticker],
                entry_date=date_text,
                entry_price=result.filled_price,
                quantity=result.filled_quantity,
                stop_price=round(stop_price, 2),
                target_price=round(
                    result.filled_price + risk_distance * strategy.target_r_multiplier,
                    2,
                ),
                signal_score=float(order.metadata["ranking_score"]),
            )
            violations_after = set(_audit_entry_limits(broker.get_account_snapshot(), risk))
            risk_limit_violations.extend(sorted(violations_after - violations_before))

        for ticker, position in list(positions.items()):
            frame = histories[ticker]
            if current_date not in frame.index:
                continue
            row = frame.loc[current_date]
            position.holding_sessions += 1
            exit_price = 0.0
            reason = ""
            if float(row["Low"]) <= position.stop_price:
                exit_price = position.stop_price * (1 - exit_slippage_rate)
                reason = "STOP"
            elif float(row["High"]) >= position.target_price:
                exit_price = position.target_price * (1 - exit_slippage_rate)
                reason = "TARGET"
            elif position.holding_sessions >= strategy.max_hold_sessions:
                exit_price = float(row["Close"]) * (1 - exit_slippage_rate)
                reason = "TIME_EXIT"
            if reason:
                trade = _submit_exit(
                    broker, position, current_date, exit_price, reason,
                    fold_number, commission_rate,
                )
                trades.append(trade)
                state.consecutive_losses = state.consecutive_losses + 1 if trade["profit_yen"] < 0 else 0
                del positions[ticker]

        for ticker in list(positions):
            frame = histories[ticker]
            if current_date in frame.index:
                broker.set_market_price(ticker, float(frame.loc[current_date, "Close"]))
        closing = broker.get_account_snapshot()
        equity_values.append(closing.equity_yen)
        for ticker, frame in fold_histories.items():
            if ticker in positions:
                continue
            signal = signal_at(ticker, frame, current_date, strategy, minimum_history_sessions)
            if signal is not None:
                pending[ticker] = signal

    final_date = test_dates[-1]
    for ticker, position in list(positions.items()):
        frame = histories[ticker]
        available = frame.loc[frame.index <= final_date]
        if available.empty:
            raise HistoricalReplayError(f"No final valuation for open position: {ticker}")
        exit_price = float(available.iloc[-1]["Close"]) * (1 - exit_slippage_rate)
        trade = _submit_exit(
            broker, position, final_date, exit_price, "END_OF_FOLD",
            fold_number, commission_rate,
        )
        trades.append(trade)
        del positions[ticker]
    final_snapshot = broker.get_account_snapshot()
    if equity_values:
        equity_values[-1] = final_snapshot.equity_yen
    metrics = _metrics(trades, equity_values, initial_cash_yen)
    fold_result = {
        "fold": fold_number,
        "train_start": pd.Timestamp(fold["train_start"]).strftime("%Y-%m-%d"),
        "train_end": pd.Timestamp(fold["train_end"]).strftime("%Y-%m-%d"),
        "test_start": pd.Timestamp(fold["test_start"]).strftime("%Y-%m-%d"),
        "test_end": pd.Timestamp(fold["test_end"]).strftime("%Y-%m-%d"),
        "oos_sessions": len(test_dates),
        **metrics,
        "risk_halt_days": len(risk_halt_dates),
        "risk_limit_violations": len(risk_limit_violations),
    }
    fold_result["successful"] = bool(
        metrics["trade_count"] >= 3
        and metrics["profit_factor"] > 1.0
        and metrics["total_return_pct"] > 0
        and metrics["maximum_drawdown_pct"] <= risk.max_drawdown_pct * 100
        and not risk_limit_violations
    )
    return fold_result, trades


def risk_state_for_session(session: pd.Timestamp, equity_yen: float) -> RiskState:
    date_text = pd.Timestamp(session).strftime("%Y-%m-%d")
    return RiskState(
        trading_date=date_text,
        start_of_day_equity_yen=round(float(equity_yen), 2),
        peak_equity_yen=round(float(equity_yen), 2),
        consecutive_losses=0,
        halted=False,
        halt_reason="",
        updated_at=f"{date_text}T09:00:00+09:00",
    )


def _relative_key(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix().casefold()


def _validate_run_settings(
    root: Path,
    config_path: Path,
    settings: Mapping[str, Any],
) -> None:
    forbidden = {"risk", "risk_overrides", "position_sizing", "position_sizing_overrides"}
    present = sorted(forbidden & set(settings))
    if present:
        raise ValueError(f"Historical replay cannot override active risk settings: {present}")
    for name in ("train_sessions", "test_sessions", "step_sessions", "minimum_history_sessions"):
        if int(settings.get(name, 0) or 0) <= 0:
            raise ValueError(f"{name} must be positive")
    if int(settings["step_sessions"]) < int(settings["test_sessions"]):
        raise ValueError("Overlapping out-of-sample folds are forbidden")
    assumptions = settings.get("execution_assumptions", {})
    for name in ("entry_slippage_rate", "exit_slippage_rate"):
        value = float(assumptions.get(name, -1))
        if not math.isfinite(value) or value < 0.0005:
            raise ValueError(f"{name} must be finite and at least 0.0005")
    participation = float(assumptions.get("maximum_volume_participation_rate", 0))
    if not math.isfinite(participation) or not 0 < participation <= 0.05:
        raise ValueError("maximum_volume_participation_rate must be within (0, 0.05]")
    if assumptions.get("daily_price_limit_model") != "NOT_IMPLEMENTED":
        raise ValueError("This implementation cannot claim a completed daily price-limit model")
    protocol = settings.get("validation_protocol", {})
    if not isinstance(protocol, Mapping):
        raise ValueError("validation_protocol must be an object")
    if protocol.get("replay_scope") != REPLAY_SCOPE:
        raise ValueError("This implementation cannot claim production decision-pipeline parity")
    if protocol.get("parameter_policy") != "FROZEN_TRACKED_CONFIG":
        raise ValueError("Historical strategy parameters must use the tracked frozen config")
    if protocol.get("sealed_holdout_status") != SEALED_HOLDOUT_STATUS:
        raise ValueError("This implementation cannot claim an established sealed holdout")
    gate = settings.get("gate", {})
    positive = (
        "minimum_folds",
        "minimum_oos_sessions",
        "minimum_simulated_trades",
        "minimum_profit_factor",
        "minimum_successful_fold_rate",
        "maximum_drawdown_pct",
    )
    for name in positive:
        value = float(gate.get(name, 0))
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Gate threshold must be positive: {name}")
    if not 0 < float(gate["minimum_successful_fold_rate"]) <= 1:
        raise ValueError("minimum_successful_fold_rate must be within (0, 1]")
    for name, floor in MINIMUM_GATE_FLOORS.items():
        if float(gate.get(name, 0)) < floor:
            raise ValueError(f"Historical gate threshold is below the safety floor: {name}")
    if int(gate.get("maximum_risk_limit_violations", -1)) < 0:
        raise ValueError("maximum_risk_limit_violations must be non-negative")
    if int(gate.get("maximum_risk_halt_days", -1)) < 0:
        raise ValueError("maximum_risk_halt_days must be non-negative")

    protected_values = settings.get("protected_files")
    if not isinstance(protected_values, list) or not protected_values:
        raise ValueError("protected_files must be a non-empty list")
    protected_paths: list[Path] = []
    for value in protected_values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("protected_files entries must be non-empty strings")
        path = resolve_within(root, value)
        if path.exists() and not path.is_file():
            raise ValueError(f"Protected path is not a regular file: {value}")
        protected_paths.append(path)
    protected_keys = [_relative_key(root, path) for path in protected_paths]
    if len(protected_keys) != len(set(protected_keys)):
        raise ValueError("protected_files must not contain duplicate paths")
    required_protected = {value.casefold() for value in REQUIRED_PROTECTED_FILES}
    missing_protected = sorted(required_protected - set(protected_keys))
    if missing_protected:
        raise ValueError(
            "protected_files is missing required operational evidence: "
            + ", ".join(missing_protected)
        )

    output_paths: dict[str, Path] = {}
    for name, expected in REQUIRED_OUTPUT_PATHS.items():
        value = settings.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Historical output path is required: {name}")
        raw_path = Path(value)
        if (
            raw_path.is_absolute()
            or ".." in raw_path.parts
            or raw_path.as_posix().casefold() != expected.casefold()
        ):
            raise ValueError(f"Historical output path must be {expected}: {name}")
        actual_path = resolve_within(root, value)
        if _relative_key(root, actual_path) != expected.casefold():
            raise ValueError(f"Historical output path must be {expected}: {name}")
        if actual_path.exists() and not actual_path.is_file():
            raise ValueError(f"Historical output path is not a regular file: {name}")
        if actual_path.exists() and actual_path.stat().st_nlink > 1:
            raise ValueError(f"Historical output path cannot be a hard-link alias: {name}")
        output_paths[name] = actual_path
    output_keys = {_relative_key(root, path) for path in output_paths.values()}
    if len(output_keys) != len(output_paths):
        raise ValueError("Historical output paths must be distinct")
    if output_keys & set(protected_keys):
        raise ValueError("Historical outputs must not overlap protected operational evidence")

    control_paths = [
        config_path,
        resolve_within(root, str(settings.get("manifest", ""))),
        resolve_within(root, str(settings.get("active_pipeline_config", ""))),
        resolve_within(root, "phoenix_core/historical_replay.py"),
        resolve_within(root, "phoenix_core/position_sizer.py"),
        resolve_within(root, "phoenix_core/risk_controller.py"),
        resolve_within(root, "phoenix_core/broker.py"),
        *_price_paths(root, str(settings.get("price_glob", ""))),
    ]
    control_keys = {_relative_key(root, path) for path in control_paths}
    if output_keys & control_keys:
        raise ValueError("Historical outputs must not overlap replay inputs or code")


def _aggregate(
    folds: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    initial_cash: float,
) -> dict[str, Any]:
    profits = [float(item["profit_yen"]) for item in trades]
    gross_profit = sum(value for value in profits if value > 0)
    gross_loss = -sum(value for value in profits if value < 0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    return {
        "fold_count": len(folds),
        "oos_session_count": sum(int(item["oos_sessions"]) for item in folds),
        "simulated_trade_count": len(trades),
        "simulated_fill_count": len(trades) * 2,
        "win_count": sum(value > 0 for value in profits),
        "profit_factor": round(profit_factor, 6),
        "successful_fold_count": sum(bool(item["successful"]) for item in folds),
        "successful_fold_rate": round(
            sum(bool(item["successful"]) for item in folds) / len(folds) if folds else 0.0,
            6,
        ),
        "maximum_fold_drawdown_pct": round(
            max((float(item["maximum_drawdown_pct"]) for item in folds), default=0.0),
            6,
        ),
        "risk_halt_days": sum(int(item["risk_halt_days"]) for item in folds),
        "risk_limit_violations": sum(int(item["risk_limit_violations"]) for item in folds),
        "initial_cash_per_fold_yen": round(initial_cash, 2),
    }


def _performance_checks(
    aggregate: Mapping[str, Any],
    gate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = [
        ("fold_count", aggregate["fold_count"], int(gate["minimum_folds"]), ">="),
        ("oos_sessions", aggregate["oos_session_count"], int(gate["minimum_oos_sessions"]), ">="),
        ("simulated_trades", aggregate["simulated_trade_count"], int(gate["minimum_simulated_trades"]), ">="),
        ("profit_factor", aggregate["profit_factor"], float(gate["minimum_profit_factor"]), ">="),
        ("successful_fold_rate", aggregate["successful_fold_rate"], float(gate["minimum_successful_fold_rate"]), ">="),
        ("maximum_drawdown_pct", aggregate["maximum_fold_drawdown_pct"], float(gate["maximum_drawdown_pct"]), "<="),
        ("risk_halt_days", aggregate["risk_halt_days"], int(gate["maximum_risk_halt_days"]), "<="),
        ("risk_limit_violations", aggregate["risk_limit_violations"], int(gate["maximum_risk_limit_violations"]), "<="),
    ]
    return [
        {
            "name": name,
            "passed": actual >= required if operator == ">=" else actual <= required,
            "actual": actual,
            "required": required,
            "operator": operator,
        }
        for name, actual, required, operator in rows
    ]


def _csv_text(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name, "") for name in fieldnames})
    return buffer.getvalue()


def render_detail_csv(
    folds: list[dict[str, Any]],
    trades: list[dict[str, Any]],
) -> tuple[str, str]:
    fold_fields = list(folds[0]) if folds else ["fold"]
    trade_fields = list(trades[0]) if trades else [
        "fold", "ticker", "signal_date", "entry_date", "exit_date", "entry_price",
        "exit_price", "quantity", "profit_yen", "return_pct", "holding_sessions",
        "exit_reason", "signal_score", "event_id",
    ]
    return (
        "\ufeff" + _csv_text(folds, fold_fields),
        "\ufeff" + _csv_text(trades, trade_fields),
    )


def text_report(report: Mapping[str, Any]) -> str:
    aggregate = report.get("aggregate", {})
    lines = [
        "PHOENIX v7 STEP17.1 HISTORICAL WALK-FORWARD REPLAY GATE",
        "=" * 100,
        f"Gate status              : {report.get('gate_status')}",
        f"Execution status         : {report.get('execution_status')}",
        f"Evidence kind            : {report.get('evidence_kind')}",
        f"Evidence SHA-256         : {report.get('evidence_sha256')}",
        f"Point-in-time data       : {report.get('data_contract_status')}",
        f"Replay scope             : {report.get('replay_scope')}",
        f"Sealed holdout           : {report.get('sealed_holdout_status')}",
        f"Execution model          : {report.get('execution_model_status')}",
        f"Risk limits unchanged    : {report.get('risk_limits_unchanged')}",
        f"Operational state intact : {report.get('state_integrity_status')}",
        f"Post-save integrity       : {report.get('post_save_integrity_status')}",
        f"Folds / OOS sessions     : {aggregate.get('fold_count', 0)} / {aggregate.get('oos_session_count', 0)}",
        f"Simulated trades/fills   : {aggregate.get('simulated_trade_count', 0)} / {aggregate.get('simulated_fill_count', 0)}",
        f"Profit factor            : {aggregate.get('profit_factor', 0)}",
        f"Successful fold rate     : {aggregate.get('successful_fold_rate', 0)}",
        f"Max fold drawdown        : {aggregate.get('maximum_fold_drawdown_pct', 0)}%",
        f"Paper days credited      : {report.get('paper_days_credited', 0)}",
        f"Audited fills credited   : {report.get('audited_fills_credited', 0)}",
        f"External orders          : {report.get('external_orders_submitted', 0)}",
        "-" * 100,
        "Performance checks:",
    ]
    for item in report.get("performance_checks", []):
        mark = "PASS" if item.get("passed") else "BLOCK"
        lines.append(
            f"{mark:<6} {item.get('name', ''):<28} actual={item.get('actual')} "
            f"{item.get('operator')} {item.get('required')}"
        )
    blockers = report.get("blocking_reasons", [])
    if blockers:
        lines.extend(["-" * 100, "Blocking reasons:"])
        lines.extend(f"  - {value}" for value in blockers)
    lines.extend(
        [
            "-" * 100,
            "Historical evidence never counts as paper-trading days or audited broker fills.",
            "This gate never enables live trading automatically.",
            "=" * 100,
            "",
        ]
    )
    return "\n".join(lines)


def save_report(
    root: Path,
    settings: Mapping[str, Any],
    report: dict[str, Any],
    folds: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    *,
    commit_json: bool = True,
) -> None:
    report_json = resolve_within(root, str(settings["report_json"]))
    report_text = resolve_within(root, str(settings["report_text"]))
    folds_csv = resolve_within(root, str(settings["folds_csv"]))
    trades_csv = resolve_within(root, str(settings["trades_csv"]))
    folds_text, trades_text = render_detail_csv(folds, trades)
    report_text_value = text_report(report)
    report["artifact_hashes"] = {
        "folds_csv_sha256": sha256_text(folds_text),
        "trades_csv_sha256": sha256_text(trades_text),
        "report_text_sha256": sha256_text(report_text_value),
    }
    atomic_write(folds_csv, folds_text)
    atomic_write(trades_csv, trades_text)
    atomic_write(report_text, report_text_value)
    if commit_json:
        # JSON is the commit marker and is written only after all detail artifacts.
        atomic_write(report_json, json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def artifact_commit_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "gate_status": report.get("gate_status"),
        "execution_status": report.get("execution_status"),
        "evidence_kind": report.get("evidence_kind"),
        "data_contract_status": report.get("data_contract_status"),
        "replay_scope": report.get("replay_scope"),
        "sealed_holdout_status": report.get("sealed_holdout_status"),
        "execution_model_status": report.get("execution_model_status"),
        "blocking_reasons": list(report.get("blocking_reasons", [])),
        "evidence_sha256": report.get("evidence_sha256"),
        "artifact_hashes": dict(report.get("artifact_hashes", {})),
        "post_save_integrity_status": report.get("post_save_integrity_status"),
        "state_integrity_status": report.get("state_integrity_status"),
        "input_files_unchanged": report.get("input_files_unchanged"),
        "risk_limits_unchanged": report.get("risk_limits_unchanged"),
        "paper_days_credited": report.get("paper_days_credited"),
        "audited_fills_credited": report.get("audited_fills_credited"),
        "external_orders_submitted": report.get("external_orders_submitted"),
        "live_trading_enabled": report.get("live_trading_enabled"),
        "automatic_promotion": report.get("automatic_promotion"),
    }


def commit_report_json(
    root: Path,
    settings: Mapping[str, Any],
    report: Mapping[str, Any],
) -> None:
    report_json = resolve_within(root, str(settings["report_json"]))
    atomic_write(report_json, json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def invalidate_report_commit(
    root: Path,
    settings: Mapping[str, Any],
    message: str,
) -> None:
    failure = {
        "schema_version": 1,
        "version": "PHOENIX v7 Step17.1",
        "gate_status": "FAILED",
        "execution_status": "FAILED",
        "evidence_kind": EVIDENCE_KIND,
        "state_integrity_status": "FAILED",
        "post_save_integrity_status": "FAILED",
        "blocking_reasons": [message],
        "paper_days_credited": 0,
        "audited_fills_credited": 0,
        "external_orders_submitted": 0,
        "live_trading_enabled": False,
        "automatic_promotion": False,
    }
    commit_report_json(root, settings, failure)


def verify_historical_report(
    root: Path,
    report: Mapping[str, Any],
    config_path: Path,
) -> tuple[bool, list[str]]:
    errors: list[str] = []
    try:
        root = root.resolve()
        resolved_config = resolve_within(root, str(config_path))
        config = read_json_object(resolved_config)
        settings = config.get("historical_replay", {})
        if not isinstance(settings, Mapping):
            raise ValueError("historical_replay config must be an object")
        if settings.get("enabled") is not True:
            raise ValueError("Historical replay gate cannot be disabled")
        _validate_run_settings(root, resolved_config, settings)
        payload = report.get("evidence_payload")
        if not isinstance(payload, Mapping):
            raise ValueError("Historical report evidence_payload is missing")
        if canonical_sha256(payload) != report.get("evidence_sha256"):
            errors.append("Historical evidence digest does not match its payload")
        manifest_path = resolve_within(root, str(settings["manifest"]))
        pipeline_path = resolve_within(root, str(settings["active_pipeline_config"]))
        manifest = read_json_object(manifest_path)
        pipeline = read_json_object(pipeline_path)
        current_manifest_blockers = assess_manifest(manifest)
        if list(payload.get("manifest_blockers", [])) != current_manifest_blockers:
            errors.append("Historical manifest assessment is stale or modified")
        expected_data_contract = "READY" if not current_manifest_blockers else "NOT_READY"
        if report.get("data_contract_status") != expected_data_contract:
            errors.append("Historical data-contract status is inconsistent with its manifest")
        protocol_expected = [
            "Replay is a surrogate technical baseline, not the production decision pipeline",
            "A strategy lock and sealed final holdout have not been established",
            "The daily Japanese price-limit execution model is not implemented",
        ]
        if list(payload.get("protocol_blockers", [])) != protocol_expected:
            errors.append("Historical validation protocol evidence is invalid")
        if (
            payload.get("replay_scope") != REPLAY_SCOPE
            or payload.get("sealed_holdout_status") != SEALED_HOLDOUT_STATUS
            or payload.get("execution_model_status") != EXECUTION_MODEL_STATUS
        ):
            errors.append("Historical replay scope/protocol claims are invalid")
        code_files = [
            "phoenix_core/historical_replay.py",
            "phoenix_core/position_sizer.py",
            "phoenix_core/risk_controller.py",
            "phoenix_core/broker.py",
        ]
        control_files = [
            resolved_config.relative_to(root).as_posix(),
            manifest_path.relative_to(root).as_posix(),
            pipeline_path.relative_to(root).as_posix(),
            *code_files,
        ]
        current_controls = capture_files(root, control_files)
        if dict(report.get("control_files_before", {})) != current_controls:
            errors.append("Historical control inputs changed after replay")
        if dict(report.get("control_files_after", {})) != current_controls:
            errors.append("Historical replay did not finish with the current control inputs")
        for field, path in (
            ("config_sha256", resolved_config),
            ("manifest_sha256", manifest_path),
            ("active_pipeline_sha256", pipeline_path),
        ):
            current_hash = sha256_file(path)
            if payload.get(field) != current_hash or report.get(field) != current_hash:
                errors.append(f"Historical report {field} is stale")
        current_prices = {
            path.relative_to(root).as_posix(): sha256_file(path)
            for path in _price_paths(root, str(settings["price_glob"]))
        }
        if dict(payload.get("price_hashes", {})) != current_prices:
            errors.append("Historical price inputs changed after replay")
        if dict(report.get("price_file_hashes", {})) != current_prices:
            errors.append("Historical report price hashes are invalid")
        current_code = {name: current_controls[name] for name in code_files}
        if dict(payload.get("code_hashes", {})) != current_code:
            errors.append("Historical replay code hashes are stale")
        sizing_values = dict(pipeline.get("position_sizing", {}))
        risk_values = dict(pipeline.get("risk", {}))
        broker_values = dict(pipeline.get("broker", {}))
        current_risk_fingerprint = canonical_sha256(
            {"position_sizing": sizing_values, "risk": risk_values, "broker": broker_values}
        )
        if payload.get("risk_fingerprint") != current_risk_fingerprint:
            errors.append("Historical risk fingerprint does not match active v7 settings")
        if report.get("risk_fingerprint") != current_risk_fingerprint:
            errors.append("Historical report risk fingerprint is invalid")
        if payload.get("aggregate") != report.get("aggregate"):
            errors.append("Historical aggregate does not match evidence payload")
        if payload.get("folds") != report.get("folds"):
            errors.append("Historical folds do not match evidence payload")
        current_checks = _performance_checks(
            dict(report.get("aggregate", {})),
            settings["gate"],
        )
        if current_checks != report.get("performance_checks"):
            errors.append("Historical performance checks are stale or modified")
        folds_path = resolve_within(root, str(settings["folds_csv"]))
        trades_path = resolve_within(root, str(settings["trades_csv"]))
        text_path = resolve_within(root, str(settings["report_text"]))
        artifacts = report.get("artifact_hashes", {})
        for name, path in (
            ("folds_csv_sha256", folds_path),
            ("trades_csv_sha256", trades_path),
            ("report_text_sha256", text_path),
        ):
            if not path.is_file() or artifacts.get(name) != sha256_file(path):
                errors.append(f"Historical detail artifact is missing or stale: {name}")
        expected_artifact_commit = canonical_sha256(artifact_commit_payload(report))
        if report.get("artifact_commit_sha256") != expected_artifact_commit:
            errors.append("Historical artifact commit digest is missing or invalid")
        payload_csv = dict(payload.get("output_csv_hashes", {}))
        if payload_csv.get("folds_csv_sha256") != artifacts.get("folds_csv_sha256"):
            errors.append("Historical folds artifact is not bound to evidence")
        if payload_csv.get("trades_csv_sha256") != artifacts.get("trades_csv_sha256"):
            errors.append("Historical trades artifact is not bound to evidence")
        payload_before = dict(payload.get("protected_files_before", {}))
        payload_after = dict(payload.get("protected_files_after", {}))
        if payload_before != dict(report.get("protected_files_before", {})):
            errors.append("Historical pre-replay state evidence was modified")
        if payload_after != dict(report.get("protected_files_after", {})):
            errors.append("Historical post-replay state evidence was modified")
        if payload.get("state_unchanged") is not True or payload_before != payload_after:
            errors.append("Historical replay changed protected operational state")
        if report.get("replay_scope") != REPLAY_SCOPE:
            errors.append("Historical report cannot claim production decision-pipeline parity")
        if report.get("sealed_holdout_status") != SEALED_HOLDOUT_STATUS:
            errors.append("Historical report cannot claim a sealed holdout")
        if report.get("execution_model_status") != EXECUTION_MODEL_STATUS:
            errors.append("Historical execution-model status is invalid")
        if report.get("post_save_integrity_status") != "READY":
            errors.append("Historical post-save integrity check is not READY")
        if report.get("gate_status") != "NOT_READY":
            errors.append("Current surrogate protocol must remain NOT_READY")
        if not protocol_expected or not all(
            value in report.get("blocking_reasons", []) for value in protocol_expected
        ):
            errors.append("Historical protocol blockers are missing")
    except (KeyError, TypeError, ValueError, OSError, HistoricalReplayError) as error:
        errors.append(f"Historical evidence verification failed: {type(error).__name__}: {error}")
    return not errors, errors


def run_historical_replay(root: Path, config_path: Path) -> dict[str, Any]:
    root = root.resolve()
    lock = SingleInstanceLock(resolve_within(root, HISTORICAL_REPLAY_LOCK))
    if not lock.acquire():
        raise HistoricalReplayLockError(
            f"Another historical replay is already running: {lock.path}"
        )
    try:
        return _run_historical_replay_locked(root, config_path)
    finally:
        lock.release()


def _run_historical_replay_locked(root: Path, config_path: Path) -> dict[str, Any]:
    root = root.resolve()
    config_path = resolve_within(root, str(config_path)) if not config_path.is_absolute() else resolve_within(root, str(config_path))
    config, loaded_config_hash = read_json_object_with_hash(config_path)
    settings = config.get("historical_replay", {})
    if not isinstance(settings, Mapping):
        raise ValueError("historical_replay config must be an object")
    if settings.get("enabled") is not True:
        raise ValueError("Historical replay gate cannot be disabled")
    _validate_run_settings(root, config_path, settings)
    manifest_path = resolve_within(root, str(settings["manifest"]))
    manifest, loaded_manifest_hash = read_json_object_with_hash(manifest_path)
    manifest_blockers = assess_manifest(manifest)
    protected_before = capture_files(root, [str(value) for value in settings["protected_files"]])
    histories, price_hashes_before = load_price_history(root, str(settings["price_glob"]))
    strategy = StrategyConfig(**dict(settings.get("strategy", {})))
    strategy.validate()
    pipeline_path = resolve_within(root, str(settings["active_pipeline_config"]))
    pipeline, loaded_pipeline_hash = read_json_object_with_hash(pipeline_path)
    code_files = [
        "phoenix_core/historical_replay.py",
        "phoenix_core/position_sizer.py",
        "phoenix_core/risk_controller.py",
        "phoenix_core/broker.py",
    ]
    control_files = [
        config_path.relative_to(root).as_posix(),
        manifest_path.relative_to(root).as_posix(),
        pipeline_path.relative_to(root).as_posix(),
        *code_files,
    ]
    control_hashes_before = capture_files(root, control_files)
    loaded_control_hashes = {
        config_path.relative_to(root).as_posix(): loaded_config_hash,
        manifest_path.relative_to(root).as_posix(): loaded_manifest_hash,
        pipeline_path.relative_to(root).as_posix(): loaded_pipeline_hash,
    }
    if any(
        control_hashes_before[name].get("sha256") != digest
        for name, digest in loaded_control_hashes.items()
    ):
        raise HistoricalReplayError("A JSON control input changed while it was being loaded")
    sizing_values = dict(pipeline.get("position_sizing", {}))
    risk_values = dict(pipeline.get("risk", {}))
    broker_values = dict(pipeline.get("broker", {}))
    sizing = PositionSizingConfig(**sizing_values)
    risk = RiskConfig(**risk_values)
    sizing.validate()
    risk.validate()
    gate_maximum_drawdown = float(settings["gate"]["maximum_drawdown_pct"])
    if gate_maximum_drawdown > risk.max_drawdown_pct * 100:
        raise ValueError("Historical gate cannot exceed the active v7 drawdown limit")
    if int(settings["gate"]["maximum_risk_halt_days"]) != 0:
        raise ValueError("Historical gate must reject every risk-halt day")
    if int(settings["gate"]["maximum_risk_limit_violations"]) != 0:
        raise ValueError("Historical gate must reject every risk-limit violation")
    initial_cash = float(broker_values.get("initial_cash_yen", 300_000))
    commission_rate = float(broker_values.get("commission_rate", 0.0))
    if initial_cash <= 0 or commission_rate < 0:
        raise ValueError("Active broker simulation settings are invalid")
    prepared = {
        ticker: add_causal_indicators(frame, strategy)
        for ticker, frame in histories.items()
    }
    sessions = sorted(set().union(*(set(frame.index) for frame in prepared.values())))
    folds = build_walk_forward_folds(
        sessions,
        int(settings["train_sessions"]),
        int(settings["test_sessions"]),
        int(settings["step_sessions"]),
    )
    if not folds:
        raise HistoricalReplayError("No complete non-overlapping walk-forward folds are available")
    fold_results: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    assumptions = settings["execution_assumptions"]
    for fold in folds:
        fold_result, fold_trades = replay_fold(
            prepared,
            fold,
            strategy,
            sizing,
            risk,
            initial_cash,
            commission_rate,
            float(assumptions["entry_slippage_rate"]),
            float(assumptions["exit_slippage_rate"]),
            float(assumptions["maximum_volume_participation_rate"]),
            int(settings["minimum_history_sessions"]),
        )
        fold_results.append(fold_result)
        trades.extend(fold_trades)
    aggregate = _aggregate(fold_results, trades, initial_cash)
    performance_checks = _performance_checks(aggregate, settings["gate"])
    price_hashes_after = {
        path: sha256_file(resolve_within(root, path))
        for path in price_hashes_before
    }
    control_hashes_after = capture_files(root, control_files)
    input_files_unchanged = (
        price_hashes_before == price_hashes_after
        and files_unchanged(control_hashes_before, control_hashes_after)
    )
    protected_after = capture_files(root, [str(value) for value in settings["protected_files"]])
    state_unchanged = files_unchanged(protected_before, protected_after)
    risk_fingerprint = canonical_sha256(
        {"position_sizing": sizing_values, "risk": risk_values, "broker": broker_values}
    )
    code_hashes = {
        name: control_hashes_before[name]
        for name in code_files
    }
    folds_text, trades_text = render_detail_csv(fold_results, trades)
    output_csv_hashes = {
        "folds_csv_sha256": sha256_text(folds_text),
        "trades_csv_sha256": sha256_text(trades_text),
    }
    protocol_blockers = [
        "Replay is a surrogate technical baseline, not the production decision pipeline",
        "A strategy lock and sealed final holdout have not been established",
        "The daily Japanese price-limit execution model is not implemented",
    ]
    evidence_payload = {
        "evidence_kind": EVIDENCE_KIND,
        "replay_scope": REPLAY_SCOPE,
        "sealed_holdout_status": SEALED_HOLDOUT_STATUS,
        "execution_model_status": EXECUTION_MODEL_STATUS,
        "config_sha256": loaded_config_hash,
        "manifest_sha256": loaded_manifest_hash,
        "active_pipeline_sha256": loaded_pipeline_hash,
        "risk_fingerprint": risk_fingerprint,
        "price_hashes": price_hashes_before,
        "code_hashes": code_hashes,
        "output_csv_hashes": output_csv_hashes,
        "protected_files_before": protected_before,
        "protected_files_after": protected_after,
        "state_unchanged": state_unchanged,
        "strategy": asdict(strategy),
        "folds": fold_results,
        "trade_event_ids": [item["event_id"] for item in trades],
        "aggregate": aggregate,
        "manifest_blockers": manifest_blockers,
        "protocol_blockers": protocol_blockers,
    }
    blockers = list(manifest_blockers) + protocol_blockers
    blockers.extend(
        f"Performance gate failed: {item['name']}"
        for item in performance_checks
        if not item["passed"]
    )
    if not input_files_unchanged:
        blockers.append("Historical input files changed during replay")
    if not state_unchanged:
        blockers.append("Operational state changed during historical replay")
    generated_at = datetime.now(JST).isoformat(timespec="seconds")
    ready = not blockers
    report: dict[str, Any] = {
        "schema_version": 1,
        "version": "PHOENIX v7 Step17.1",
        "generated_at": generated_at,
        "gate_status": "READY" if ready else "NOT_READY",
        "execution_status": "COMPLETED",
        "evidence_kind": EVIDENCE_KIND,
        "evidence_sha256": canonical_sha256(evidence_payload),
        "evidence_payload": evidence_payload,
        "data_contract_status": "READY" if not manifest_blockers else "NOT_READY",
        "replay_scope": REPLAY_SCOPE,
        "strategy_protocol_status": "NOT_READY",
        "sealed_holdout_status": SEALED_HOLDOUT_STATUS,
        "execution_model_status": EXECUTION_MODEL_STATUS,
        "risk_limits_unchanged": True,
        "risk_limits_source": pipeline_path.relative_to(root).as_posix(),
        "config_sha256": evidence_payload["config_sha256"],
        "manifest_sha256": evidence_payload["manifest_sha256"],
        "active_pipeline_sha256": evidence_payload["active_pipeline_sha256"],
        "risk_fingerprint": risk_fingerprint,
        "active_position_sizing": sizing_values,
        "active_risk_limits": risk_values,
        "active_broker_simulation": broker_values,
        "strategy": asdict(strategy),
        "execution_assumptions": dict(assumptions),
        "input_files_unchanged": input_files_unchanged,
        "state_integrity_status": "READY" if state_unchanged else "FAILED",
        "protected_files_before": protected_before,
        "protected_files_after": protected_after,
        "price_file_hashes": price_hashes_before,
        "code_file_hashes": code_hashes,
        "control_files_before": control_hashes_before,
        "control_files_after": control_hashes_after,
        "output_csv_hashes": output_csv_hashes,
        "manifest_blockers": manifest_blockers,
        "protocol_blockers": protocol_blockers,
        "aggregate": aggregate,
        "performance_checks": performance_checks,
        "folds": fold_results,
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "paper_days_credited": 0,
        "audited_fills_credited": 0,
        "external_orders_submitted": 0,
        "live_trading_enabled": False,
        "automatic_promotion": False,
        "post_save_integrity_status": "PENDING",
    }
    save_report(root, settings, report, fold_results, trades, commit_json=False)
    protected_post_save = capture_files(
        root, [str(value) for value in settings["protected_files"]]
    )
    controls_post_save = capture_files(root, control_files)
    prices_post_save = {
        path: sha256_file(resolve_within(root, path))
        for path in price_hashes_before
    }
    if (
        not files_unchanged(protected_before, protected_post_save)
        or not files_unchanged(control_hashes_before, controls_post_save)
        or price_hashes_before != prices_post_save
    ):
        message = "Protected state or replay inputs changed while historical outputs were saved"
        invalidate_report_commit(root, settings, message)
        raise HistoricalReplayError(message)
    report["post_save_integrity_status"] = "READY"
    save_report(root, settings, report, fold_results, trades, commit_json=False)
    protected_precommit = capture_files(
        root, [str(value) for value in settings["protected_files"]]
    )
    controls_precommit = capture_files(root, control_files)
    prices_precommit = {
        path: sha256_file(resolve_within(root, path))
        for path in price_hashes_before
    }
    if (
        not files_unchanged(protected_before, protected_precommit)
        or not files_unchanged(control_hashes_before, controls_precommit)
        or price_hashes_before != prices_precommit
    ):
        message = "Pre-commit integrity verification failed for historical report artifacts"
        invalidate_report_commit(root, settings, message)
        raise HistoricalReplayError(message)
    report["artifact_commit_sha256"] = canonical_sha256(
        artifact_commit_payload(report)
    )
    commit_report_json(root, settings, report)
    protected_final = capture_files(
        root, [str(value) for value in settings["protected_files"]]
    )
    controls_final = capture_files(root, control_files)
    prices_final = {
        path: sha256_file(resolve_within(root, path))
        for path in price_hashes_before
    }
    if (
        not files_unchanged(protected_before, protected_final)
        or not files_unchanged(control_hashes_before, controls_final)
        or price_hashes_before != prices_final
    ):
        message = "Post-save integrity verification failed after final historical report commit"
        invalidate_report_commit(root, settings, message)
        raise HistoricalReplayError(message)
    report["report_json"] = str(resolve_within(root, str(settings["report_json"])))
    report["report_text"] = str(resolve_within(root, str(settings["report_text"])))
    return report


def print_historical_replay_summary(report: Mapping[str, Any]) -> None:
    aggregate = report.get("aggregate", {})
    print("=" * 88)
    print("PHOENIX v7 STEP17.1 HISTORICAL WALK-FORWARD REPLAY GATE")
    print("=" * 88)
    print(f"Gate status    : {report.get('gate_status')}")
    print(f"Data contract  : {report.get('data_contract_status')}")
    print(f"Folds          : {aggregate.get('fold_count', 0)}")
    print(f"OOS sessions   : {aggregate.get('oos_session_count', 0)}")
    print(f"Trades         : {aggregate.get('simulated_trade_count', 0)}")
    print(f"Profit factor  : {aggregate.get('profit_factor', 0)}")
    print(f"State integrity: {report.get('state_integrity_status')}")
    print(f"Paper days     : {report.get('paper_days_credited', 0)}")
    print(f"Live enabled   : {report.get('live_trading_enabled', False)}")
    print(f"Report         : {report.get('report_text', '')}")
    print("=" * 88)
