from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from phoenix_core.broker import BrokerAdapter
from phoenix_core.models import (
    AccountSnapshot,
    OrderRequest,
    OrderSide,
    OrderType,
)


@dataclass(frozen=True, slots=True)
class PositionSizingConfig:
    risk_per_trade_pct: float = 0.01
    max_position_pct: float = 0.30
    max_total_invested_pct: float = 0.80
    minimum_cash_reserve_pct: float = 0.10
    fallback_stop_distance_pct: float = 0.03
    lot_size: int = 100
    maximum_quantity_per_ticker: int = 1000
    allow_pyramiding: bool = False
    commission_buffer_pct: float = 0.001

    def validate(self) -> None:
        percentage_fields = {
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_position_pct": self.max_position_pct,
            "max_total_invested_pct": self.max_total_invested_pct,
            "minimum_cash_reserve_pct": self.minimum_cash_reserve_pct,
            "fallback_stop_distance_pct": self.fallback_stop_distance_pct,
            "commission_buffer_pct": self.commission_buffer_pct,
        }

        for name, value in percentage_fields.items():
            if value < 0:
                raise ValueError(f"{name}は0以上にしてください")

        if self.max_position_pct > 1:
            raise ValueError("max_position_pctは1以下にしてください")
        if self.max_total_invested_pct > 1:
            raise ValueError(
                "max_total_invested_pctは1以下にしてください"
            )
        if self.minimum_cash_reserve_pct > 1:
            raise ValueError(
                "minimum_cash_reserve_pctは1以下にしてください"
            )
        if self.lot_size <= 0:
            raise ValueError("lot_sizeは1以上にしてください")
        if self.maximum_quantity_per_ticker <= 0:
            raise ValueError(
                "maximum_quantity_per_tickerは1以上にしてください"
            )


@dataclass(frozen=True, slots=True)
class SizingDecision:
    ticker: str
    name: str
    entry_price: float
    stop_price: float
    held_quantity: int
    risk_quantity: int
    position_limit_quantity: int
    cash_limit_quantity: int
    portfolio_limit_quantity: int
    maximum_quantity_limit: int
    recommended_quantity: int
    estimated_cost_yen: float
    estimated_risk_yen: float
    status: str
    reason: str
    ranking_score: float = 0.0

    @property
    def executable(self) -> bool:
        return (
            self.status == "READY"
            and self.recommended_quantity > 0
        )


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if number == number else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def floor_to_lot(quantity: int, lot_size: int) -> int:
    if quantity <= 0:
        return 0
    return (quantity // lot_size) * lot_size


def held_quantity(
    snapshot: AccountSnapshot,
    ticker: str,
) -> int:
    normalized = ticker.strip().upper()
    for position in snapshot.positions:
        if position.ticker.strip().upper() == normalized:
            return position.quantity
    return 0


def held_market_value(
    snapshot: AccountSnapshot,
    ticker: str,
) -> float:
    normalized = ticker.strip().upper()
    for position in snapshot.positions:
        if position.ticker.strip().upper() == normalized:
            return position.market_value
    return 0.0


def _first_series(
    frame: pd.DataFrame,
    column: str,
    default: Any = 0.0,
) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(
            [default] * len(frame),
            index=frame.index,
        )

    value = frame.loc[:, column]
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]

    return value


def _coalesce_columns(
    frame: pd.DataFrame,
    candidates: list[str],
    default: Any = 0.0,
) -> pd.Series:
    result = pd.Series(
        [default] * len(frame),
        index=frame.index,
        dtype="object",
    )
    filled = pd.Series(
        [False] * len(frame),
        index=frame.index,
    )

    for column in candidates:
        if column not in frame.columns:
            continue

        value = _first_series(
            frame,
            column,
            default=default,
        )

        if pd.api.types.is_numeric_dtype(value):
            usable = value.notna()
        else:
            stripped = (
                value.astype(str)
                .str.strip()
            )
            usable = (
                value.notna()
                & stripped.ne("")
                & stripped.str.lower().ne("nan")
            )

        use_now = usable & ~filled
        result.loc[use_now] = value.loc[use_now]
        filled = filled | usable

    return result


def normalize_candidates(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()

    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

    if frame.empty:
        return pd.DataFrame()

    frame = frame.loc[
        :,
        ~frame.columns.duplicated(keep="first"),
    ].copy()

    ticker_candidates = [
        "ticker",
        "symbol",
        "Symbol",
        "コード",
        "銘柄コード",
    ]
    name_candidates = [
        "銘柄",
        "name",
        "Name",
        "銘柄名",
    ]
    entry_candidates = [
        "エントリー価格",
        "entry_price",
        "EntryPrice",
        "Entry",
        "押し目価格",
        "基準価格",
        "現在価格",
        "現在値",
        "終値",
        "Close",
        "close",
        "価格",
        "Price",
        "price",
        "買値",
    ]
    stop_candidates = [
        "損切価格",
        "stop_price",
        "StopPrice",
        "損切り価格",
        "ストップ価格",
        "stop",
        "Stop",
    ]
    score_candidates = [
        "ランキング点",
        "score",
        "Score",
        "PortfolioScore",
        "AI判断点",
        "PHOENIX_SCORE",
        "PHOENIX SCORE",
    ]

    frame["ticker"] = _coalesce_columns(
        frame,
        ticker_candidates,
        default="",
    )
    frame["銘柄"] = _coalesce_columns(
        frame,
        name_candidates,
        default="",
    )
    frame["エントリー価格"] = _coalesce_columns(
        frame,
        entry_candidates,
        default=0.0,
    )
    frame["損切価格"] = _coalesce_columns(
        frame,
        stop_candidates,
        default=0.0,
    )
    frame["ランキング点"] = _coalesce_columns(
        frame,
        score_candidates,
        default=0.0,
    )

    frame["ticker"] = (
        _first_series(frame, "ticker", "")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    frame["銘柄"] = (
        _first_series(frame, "銘柄", "")
        .astype(str)
        .str.strip()
    )
    blank_name = (
        frame["銘柄"].eq("")
        | frame["銘柄"].str.lower().eq("nan")
    )
    frame.loc[blank_name, "銘柄"] = frame.loc[
        blank_name,
        "ticker",
    ]

    frame["エントリー価格"] = pd.to_numeric(
        _first_series(
            frame,
            "エントリー価格",
            0.0,
        ),
        errors="coerce",
    ).fillna(0.0)

    frame["損切価格"] = pd.to_numeric(
        _first_series(
            frame,
            "損切価格",
            0.0,
        ),
        errors="coerce",
    ).fillna(0.0)

    frame["ランキング点"] = pd.to_numeric(
        _first_series(
            frame,
            "ランキング点",
            0.0,
        ),
        errors="coerce",
    ).fillna(0.0)

    if "Portfolio判定" in frame.columns:
        decision_series = (
            _first_series(
                frame,
                "Portfolio判定",
                "",
            )
            .astype(str)
            .str.strip()
            .str.upper()
        )
        accepted = {
            "採用",
            "READY",
            "BUY",
            "WATCH",
        }
        mask = decision_series.isin(
            {value.upper() for value in accepted}
        )
        if mask.any():
            frame = frame[mask].copy()

    return (
        frame[
            (frame["ticker"] != "")
            & (frame["ticker"].str.lower() != "nan")
            & (frame["エントリー価格"] > 0)
        ]
        .sort_values(
            "ランキング点",
            ascending=False,
        )
        .drop_duplicates(
            subset=["ticker"],
            keep="first",
        )
        .reset_index(drop=True)
    )


def calculate_sizing(
    snapshot: AccountSnapshot,
    ticker: str,
    entry_price: float,
    stop_price: float,
    config: PositionSizingConfig,
    name: str = "",
    ranking_score: float = 0.0,
    reserved_cash_yen: float = 0.0,
    reserved_market_value_yen: float = 0.0,
) -> SizingDecision:
    config.validate()

    normalized_ticker = ticker.strip().upper()
    normalized_name = name.strip() or normalized_ticker
    entry = round(float(entry_price), 2)
    stop = round(float(stop_price), 2)

    if not normalized_ticker:
        raise ValueError("tickerが空です")
    if entry <= 0:
        raise ValueError("entry_priceは0より大きい値にしてください")

    current_held_quantity = held_quantity(
        snapshot,
        normalized_ticker,
    )
    current_held_value = held_market_value(
        snapshot,
        normalized_ticker,
    )

    if current_held_quantity > 0 and not config.allow_pyramiding:
        return SizingDecision(
            ticker=normalized_ticker,
            name=normalized_name,
            entry_price=entry,
            stop_price=stop,
            held_quantity=current_held_quantity,
            risk_quantity=0,
            position_limit_quantity=0,
            cash_limit_quantity=0,
            portfolio_limit_quantity=0,
            maximum_quantity_limit=0,
            recommended_quantity=0,
            estimated_cost_yen=0.0,
            estimated_risk_yen=0.0,
            status="SKIP",
            reason="既に保有中のため追加購入しません",
            ranking_score=ranking_score,
        )

    if stop <= 0 or stop >= entry:
        stop = round(
            entry * (1.0 - config.fallback_stop_distance_pct),
            2,
        )

    risk_per_share = round(entry - stop, 4)
    if risk_per_share <= 0:
        return SizingDecision(
            ticker=normalized_ticker,
            name=normalized_name,
            entry_price=entry,
            stop_price=stop,
            held_quantity=current_held_quantity,
            risk_quantity=0,
            position_limit_quantity=0,
            cash_limit_quantity=0,
            portfolio_limit_quantity=0,
            maximum_quantity_limit=0,
            recommended_quantity=0,
            estimated_cost_yen=0.0,
            estimated_risk_yen=0.0,
            status="SKIP",
            reason="損切価格が不正です",
            ranking_score=ranking_score,
        )

    equity = max(snapshot.equity_yen, 0.0)
    available_cash = max(
        snapshot.cash_yen - reserved_cash_yen,
        0.0,
    )

    risk_budget = equity * config.risk_per_trade_pct
    risk_quantity = floor_to_lot(
        int(risk_budget // risk_per_share),
        config.lot_size,
    )

    maximum_position_value = (
        equity * config.max_position_pct
    )
    additional_position_value = max(
        maximum_position_value - current_held_value,
        0.0,
    )
    position_limit_quantity = floor_to_lot(
        int(additional_position_value // entry),
        config.lot_size,
    )

    minimum_cash_reserve = (
        equity * config.minimum_cash_reserve_pct
    )
    spendable_cash = max(
        available_cash - minimum_cash_reserve,
        0.0,
    )
    buffered_unit_price = (
        entry * (1.0 + config.commission_buffer_pct)
    )
    cash_limit_quantity = floor_to_lot(
        int(spendable_cash // buffered_unit_price),
        config.lot_size,
    )

    maximum_invested_value = (
        equity * config.max_total_invested_pct
    )
    current_invested_value = (
        snapshot.market_value_yen
        + reserved_market_value_yen
    )
    remaining_portfolio_capacity = max(
        maximum_invested_value - current_invested_value,
        0.0,
    )
    portfolio_limit_quantity = floor_to_lot(
        int(remaining_portfolio_capacity // entry),
        config.lot_size,
    )

    maximum_quantity_limit = floor_to_lot(
        max(
            config.maximum_quantity_per_ticker
            - current_held_quantity,
            0,
        ),
        config.lot_size,
    )

    recommended = min(
        risk_quantity,
        position_limit_quantity,
        cash_limit_quantity,
        portfolio_limit_quantity,
        maximum_quantity_limit,
    )
    recommended = floor_to_lot(
        recommended,
        config.lot_size,
    )

    limit_values = {
        "リスク上限": risk_quantity,
        "1銘柄上限": position_limit_quantity,
        "買付余力": cash_limit_quantity,
        "総投資上限": portfolio_limit_quantity,
        "最大株数": maximum_quantity_limit,
    }

    if recommended <= 0:
        zero_reasons = [
            name
            for name, value in limit_values.items()
            if value <= 0
        ]
        reason = (
            "最低売買単位を購入できません"
            if not zero_reasons
            else "・".join(zero_reasons)
            + "により最低売買単位を購入できません"
        )
        status = "SKIP"
    else:
        binding = [
            name
            for name, value in limit_values.items()
            if value == recommended
        ]
        reason = (
            " / ".join(binding)
            + f"を適用して{recommended}株"
        )
        status = "READY"

    return SizingDecision(
        ticker=normalized_ticker,
        name=normalized_name,
        entry_price=entry,
        stop_price=stop,
        held_quantity=current_held_quantity,
        risk_quantity=risk_quantity,
        position_limit_quantity=position_limit_quantity,
        cash_limit_quantity=cash_limit_quantity,
        portfolio_limit_quantity=portfolio_limit_quantity,
        maximum_quantity_limit=maximum_quantity_limit,
        recommended_quantity=recommended,
        estimated_cost_yen=round(
            recommended * entry,
            2,
        ),
        estimated_risk_yen=round(
            recommended * risk_per_share,
            2,
        ),
        status=status,
        reason=reason,
        ranking_score=round(ranking_score, 4),
    )


def size_candidates(
    broker: BrokerAdapter,
    candidates: pd.DataFrame,
    config: PositionSizingConfig,
) -> list[SizingDecision]:
    snapshot = broker.get_account_snapshot()
    decisions: list[SizingDecision] = []
    reserved_cash = 0.0
    reserved_market_value = 0.0

    for _, row in candidates.iterrows():
        decision = calculate_sizing(
            snapshot=snapshot,
            ticker=str(row.get("ticker", "")),
            name=str(row.get("銘柄", "")),
            entry_price=safe_float(
                row.get("エントリー価格")
            ),
            stop_price=safe_float(
                row.get("損切価格")
            ),
            ranking_score=safe_float(
                row.get("ランキング点")
            ),
            config=config,
            reserved_cash_yen=reserved_cash,
            reserved_market_value_yen=(
                reserved_market_value
            ),
        )
        decisions.append(decision)

        if decision.executable:
            reserved_cash += (
                decision.estimated_cost_yen
                * (1.0 + config.commission_buffer_pct)
            )
            reserved_market_value += (
                decision.estimated_cost_yen
            )

    return decisions


def stable_client_order_id(
    decision: SizingDecision,
    run_id: str,
) -> str:
    raw = (
        f"{run_id}|{decision.ticker}|"
        f"{decision.entry_price:.2f}|"
        f"{decision.recommended_quantity}"
    )
    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:18]
    return f"PHX-SIZE-{digest.upper()}"


def build_order_requests(
    decisions: Iterable[SizingDecision],
    run_id: str | None = None,
) -> list[OrderRequest]:
    actual_run_id = (
        run_id
        or datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    orders: list[OrderRequest] = []

    for decision in decisions:
        if not decision.executable:
            continue

        orders.append(
            OrderRequest(
                ticker=decision.ticker,
                side=OrderSide.BUY,
                quantity=decision.recommended_quantity,
                order_type=OrderType.LIMIT,
                limit_price=decision.entry_price,
                client_order_id=stable_client_order_id(
                    decision,
                    actual_run_id,
                ),
                strategy_name="PHOENIX_V7_POSITION_SIZER",
                metadata={
                    "stop_price": decision.stop_price,
                    "estimated_risk_yen": (
                        decision.estimated_risk_yen
                    ),
                    "ranking_score": (
                        decision.ranking_score
                    ),
                },
            )
        )

    return orders


def decisions_frame(
    decisions: Iterable[SizingDecision],
) -> pd.DataFrame:
    rows = []
    for decision in decisions:
        row = asdict(decision)
        row.update(
            {
                "銘柄": row.pop("name"),
                "エントリー価格": row.pop(
                    "entry_price"
                ),
                "損切価格": row.pop("stop_price"),
                "保有株数": row.pop("held_quantity"),
                "リスク上限株数": row.pop(
                    "risk_quantity"
                ),
                "1銘柄上限株数": row.pop(
                    "position_limit_quantity"
                ),
                "余力上限株数": row.pop(
                    "cash_limit_quantity"
                ),
                "総投資上限株数": row.pop(
                    "portfolio_limit_quantity"
                ),
                "最大株数上限": row.pop(
                    "maximum_quantity_limit"
                ),
                "推奨株数": row.pop(
                    "recommended_quantity"
                ),
                "想定購入額": row.pop(
                    "estimated_cost_yen"
                ),
                "想定損失額": row.pop(
                    "estimated_risk_yen"
                ),
                "判定": row.pop("status"),
                "理由": row.pop("reason"),
                "ランキング点": row.pop(
                    "ranking_score"
                ),
            }
        )
        rows.append(row)

    columns = [
        "ticker",
        "銘柄",
        "ランキング点",
        "エントリー価格",
        "損切価格",
        "保有株数",
        "リスク上限株数",
        "1銘柄上限株数",
        "余力上限株数",
        "総投資上限株数",
        "最大株数上限",
        "推奨株数",
        "想定購入額",
        "想定損失額",
        "判定",
        "理由",
    ]
    return pd.DataFrame(rows, columns=columns)


def save_position_sizing_outputs(
    decisions: list[SizingDecision],
    orders: list[OrderRequest],
    plan_path: Path,
    orders_path: Path,
    report_path: Path,
) -> None:
    for path in (
        plan_path,
        orders_path,
        report_path,
    ):
        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    frame = decisions_frame(decisions)
    frame.to_csv(
        plan_path,
        index=False,
        encoding="utf-8-sig",
    )

    order_payload = [
        {
            "ticker": order.ticker,
            "side": order.side.value,
            "quantity": order.quantity,
            "order_type": order.order_type.value,
            "limit_price": order.limit_price,
            "client_order_id": (
                order.client_order_id
            ),
            "strategy_name": order.strategy_name,
            "metadata": order.metadata,
        }
        for order in orders
    ]
    orders_path.write_text(
        json.dumps(
            {
                "version": "PHOENIX v7.0 Step4",
                "generated_at": (
                    datetime.now().isoformat(
                        timespec="seconds"
                    )
                ),
                "order_count": len(order_payload),
                "orders": order_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    ready = sum(
        decision.executable
        for decision in decisions
    )
    skipped = len(decisions) - ready

    lines = [
        "=" * 120,
        "PHOENIX v7 POSITION SIZER",
        "=" * 120,
        f"候補数       : {len(decisions)}件",
        f"発注可能     : {ready}件",
        f"見送り       : {skipped}件",
        "-" * 120,
    ]

    if frame.empty:
        lines.append("候補がありません。")
    else:
        lines.append(frame.to_string(index=False))

    lines.extend(
        [
            "-" * 120,
            "株数はBroker口座の現金・保有状況・"
            "総投資上限・損切リスクから算出しています。",
            "=" * 120,
        ]
    )

    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
