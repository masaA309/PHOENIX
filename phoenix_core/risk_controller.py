from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from phoenix_core.broker import BrokerAdapter
from phoenix_core.models import OrderRequest, OrderSide
from phoenix_core.performance_tracker import atomic_write


@dataclass(frozen=True, slots=True)
class RiskConfig:
    max_daily_loss_pct: float = 0.03
    max_drawdown_pct: float = 0.10
    max_positions: int | None = None
    max_total_invested_pct: float = 0.95
    max_single_position_pct: float = 0.30
    max_orders_per_run: int = 3
    max_consecutive_losses: int = 3
    minimum_cash_reserve_pct: float = 0.10
    block_on_broker_health_failure: bool = True
    risk_v2_enabled: bool = False
    risk_policy_id: str = "RISK_V2_PRODUCTION_MA25_BREADTH_V1"
    breadth_metric: str = "ABOVE_MA25_RATIO_FULL225"
    breadth_threshold: float = 0.40
    bear_max_total_invested_pct: float = 0.70
    market_regime_file: str = "reports/market_regime.json"

    def validate(self) -> None:
        pct_fields = {
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_total_invested_pct": self.max_total_invested_pct,
            "max_single_position_pct": self.max_single_position_pct,
            "minimum_cash_reserve_pct": self.minimum_cash_reserve_pct,
        }
        for name, value in pct_fields.items():
            if value < 0 or value > 1:
                raise ValueError(f"{name}は0以上1以下にしてください")
        if self.max_positions is not None and self.max_positions <= 0:
            raise ValueError("max_positionsは1以上にしてください")
        if not self.risk_policy_id.strip():
            raise ValueError("risk_policy_idは空にできません")
        if not self.breadth_metric.strip():
            raise ValueError("breadth_metricは空にできません")
        if self.breadth_threshold < 0 or self.breadth_threshold > 1:
            raise ValueError("breadth_thresholdは0以上1以下にしてください")
        if self.bear_max_total_invested_pct < 0 or self.bear_max_total_invested_pct > 1:
            raise ValueError("bear_max_total_invested_pctは0以上1以下にしてください")
        if self.max_orders_per_run <= 0:
            raise ValueError("max_orders_per_runは1以上にしてください")
        if self.max_consecutive_losses < 0:
            raise ValueError("max_consecutive_lossesは0以上にしてください")


@dataclass(slots=True)
class RiskState:
    trading_date: str
    start_of_day_equity_yen: float
    peak_equity_yen: float
    consecutive_losses: int = 0
    halted: bool = False
    halt_reason: str = ""
    updated_at: str = ""

    @classmethod
    def new(cls, equity_yen: float) -> "RiskState":
        now = datetime.now()
        return cls(
            trading_date=date.today().isoformat(),
            start_of_day_equity_yen=round(equity_yen, 2),
            peak_equity_yen=round(equity_yen, 2),
            updated_at=now.isoformat(timespec="seconds"),
        )


@dataclass(frozen=True, slots=True)
class RiskDecision:
    ticker: str
    side: str
    quantity: int
    price: float
    accepted: bool
    reason: str
    estimated_value_yen: float


@dataclass(frozen=True, slots=True)
class RiskReport:
    broker_name: str
    health_pass: bool
    equity_yen: float
    cash_yen: float
    market_value_yen: float
    daily_pnl_yen: float
    daily_loss_pct: float
    drawdown_pct: float
    current_positions: int
    consecutive_losses: int
    halted: bool
    halt_reason: str
    accepted_orders: tuple[OrderRequest, ...]
    decisions: tuple[RiskDecision, ...]


def _normalize_market_context(
    market_context: Mapping[str, Any],
    config: RiskConfig,
) -> dict[str, Any]:
    if not isinstance(market_context, Mapping):
        raise ValueError("market_contextはオブジェクトにしてください")

    required_fields = (
        "breadth_ratio",
        "breadth_threshold",
        "risk_policy_id",
        "breadth_metric",
        "regime",
        "source_run_id",
        "source_report_sha256",
        "source_ticker_count",
    )
    normalized: dict[str, Any] = {}
    missing = [field for field in required_fields if field not in market_context]
    if missing:
        raise ValueError(f"market_contextが不足しています: {', '.join(missing)}")

    try:
        normalized["breadth_ratio"] = float(market_context["breadth_ratio"])
        normalized["breadth_threshold"] = float(market_context["breadth_threshold"])
        normalized["risk_policy_id"] = str(market_context["risk_policy_id"]).strip()
        normalized["breadth_metric"] = str(market_context["breadth_metric"]).strip()
        normalized["regime"] = str(market_context["regime"]).strip().upper()
        normalized["source_run_id"] = str(market_context["source_run_id"]).strip()
        normalized["source_report_sha256"] = str(market_context["source_report_sha256"]).strip()
        normalized["source_ticker_count"] = int(market_context["source_ticker_count"])
    except (TypeError, ValueError) as error:
        raise ValueError(f"market_contextの型が不正です: {error}") from error

    if not (0.0 <= normalized["breadth_ratio"] <= 1.0):
        raise ValueError("market_context.breadth_ratioは0以上1以下にしてください")
    if not (0.0 <= normalized["breadth_threshold"] <= 1.0):
        raise ValueError("market_context.breadth_thresholdは0以上1以下にしてください")
    if normalized["source_ticker_count"] <= 0:
        raise ValueError("market_context.source_ticker_countは1以上にしてください")
    if not normalized["risk_policy_id"]:
        raise ValueError("market_context.risk_policy_idは空にできません")
    if not normalized["breadth_metric"]:
        raise ValueError("market_context.breadth_metricは空にできません")
    if normalized["regime"] not in {"BULL", "SIDEWAYS", "NEUTRAL", "BEAR"}:
        raise ValueError("market_context.regimeが不正です")
    if normalized["breadth_ratio"] < normalized["breadth_threshold"] and normalized["regime"] != "BEAR":
        raise ValueError("market_contextはbreadth_ratio閾値未満ならBEARでなければなりません")
    if config.breadth_threshold != normalized["breadth_threshold"]:
        raise ValueError("market_contextのbreadth_thresholdが設定値と一致しません")
    if normalized["risk_policy_id"] != config.risk_policy_id:
        raise ValueError("market_context.risk_policy_idが設定値と一致しません")
    if normalized["breadth_metric"] != config.breadth_metric:
        raise ValueError("market_context.breadth_metricが設定値と一致しません")
    return normalized


def load_risk_state(path: Path, equity_yen: float) -> RiskState:
    if not path.exists():
        return RiskState.new(equity_yen)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        state = RiskState(**payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError(f"Risk state could not be read: {path}: {error}") from error

    if state.trading_date != date.today().isoformat():
        return RiskState.new(equity_yen)

    state.peak_equity_yen = max(state.peak_equity_yen, equity_yen)
    state.updated_at = datetime.now().isoformat(timespec="seconds")
    return state


def save_risk_state(path: Path, state: RiskState) -> None:
    state.updated_at = datetime.now().isoformat(timespec="seconds")
    atomic_write(
        path,
        json.dumps(asdict(state), ensure_ascii=False, indent=2) + "\n",
    )


def load_order_requests(path: Path) -> list[OrderRequest]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("orders", []) if isinstance(payload, dict) else []
    orders: list[OrderRequest] = []

    from phoenix_core.models import OrderType

    for row in rows:
        side = OrderSide(str(row.get("side", "BUY")).upper())
        orders.append(
            OrderRequest(
                ticker=str(row["ticker"]).strip().upper(),
                side=side,
                quantity=int(row["quantity"]),
                order_type=OrderType(str(row.get("order_type", "LIMIT")).upper()),
                limit_price=float(row["limit_price"]),
                client_order_id=str(row["client_order_id"]),
                strategy_name=str(row.get("strategy_name", "PHOENIX")),
                metadata=dict(row.get("metadata", {})),
            )
        )
    return orders


def _reject(order: OrderRequest, reason: str) -> RiskDecision:
    return RiskDecision(
        ticker=order.ticker,
        side=order.side.value,
        quantity=order.quantity,
        price=order.limit_price,
        accepted=False,
        reason=reason,
        estimated_value_yen=round(order.quantity * order.limit_price, 2),
    )


def _portfolio_capacity_yen(
    equity_yen: float,
    current_exposure_yen: float,
    effective_total_invested_pct: float,
) -> float:
    return max(equity_yen * effective_total_invested_pct - current_exposure_yen, 0.0)


def evaluate_orders(
    broker: BrokerAdapter,
    orders: Iterable[OrderRequest],
    config: RiskConfig,
    state: RiskState,
    market_context: Mapping[str, Any] | None = None,
) -> RiskReport:
    config.validate()
    normalized_market_context = None
    if config.risk_v2_enabled:
        if market_context is None:
            raise ValueError("risk_v2_enabledがtrueのときはmarket_contextが必要です")
        normalized_market_context = _normalize_market_context(market_context, config)
    health = broker.health_check()
    snapshot = broker.get_account_snapshot()
    equity = max(snapshot.equity_yen, 0.0)
    state.peak_equity_yen = max(state.peak_equity_yen, equity)

    daily_pnl = round(equity - state.start_of_day_equity_yen, 2)
    daily_loss_pct = (
        max(-daily_pnl, 0.0) / state.start_of_day_equity_yen
        if state.start_of_day_equity_yen > 0 else 0.0
    )
    drawdown_pct = (
        max(state.peak_equity_yen - equity, 0.0) / state.peak_equity_yen
        if state.peak_equity_yen > 0 else 0.0
    )

    halt_reasons: list[str] = []
    if config.block_on_broker_health_failure and not health.healthy and not config.risk_v2_enabled:
        halt_reasons.append("Broker Health異常")
    if daily_loss_pct >= config.max_daily_loss_pct:
        halt_reasons.append("日次損失上限到達")
    if drawdown_pct >= config.max_drawdown_pct:
        halt_reasons.append("最大ドローダウン上限到達")
    if (
        config.max_consecutive_losses > 0
        and state.consecutive_losses >= config.max_consecutive_losses
    ):
        halt_reasons.append("連敗上限到達")
    if state.halted:
        halt_reasons.append(state.halt_reason or "手動停止中")

    global_halt = bool(halt_reasons)
    if global_halt:
        state.halted = True
        state.halt_reason = " / ".join(dict.fromkeys(halt_reasons))

    accepted: list[OrderRequest] = []
    decisions: list[RiskDecision] = []

    projected_cash = snapshot.cash_yen
    projected_market_value = snapshot.market_value_yen
    projected_positions = {p.ticker: p.market_value for p in snapshot.positions}

    for order in orders:
        try:
            order.validate()
        except ValueError as error:
            decisions.append(_reject(order, f"注文形式異常: {error}"))
            continue

        value = round(order.quantity * order.limit_price, 2)

        if order.side is OrderSide.SELL:
            accepted.append(order)
            projected_cash += value
            projected_market_value = max(projected_market_value - value, 0.0)
            projected_position_value = max(projected_positions.get(order.ticker, 0.0) - value, 0.0)
            if projected_position_value > 0:
                projected_positions[order.ticker] = projected_position_value
            elif order.ticker in projected_positions:
                projected_positions.pop(order.ticker, None)
            decisions.append(
                RiskDecision(
                    ticker=order.ticker,
                    side=order.side.value,
                    quantity=order.quantity,
                    price=order.limit_price,
                    accepted=True,
                    reason="EXIT注文はリスク縮小のため許可",
                    estimated_value_yen=value,
                )
            )
            continue

        if global_halt:
            decisions.append(_reject(order, state.halt_reason))
            continue

        if len(accepted) >= config.max_orders_per_run:
            decisions.append(_reject(order, "1回の最大発注件数を超過"))
            continue

        new_ticker = order.ticker not in projected_positions
        if config.max_positions is not None and new_ticker and len(projected_positions) >= config.max_positions:
            decisions.append(_reject(order, "最大保有銘柄数を超過"))
            continue

        post_cash = projected_cash - value
        post_market = projected_market_value + value

        reserve = equity * config.minimum_cash_reserve_pct
        if post_cash < reserve:
            decisions.append(_reject(order, "最低現金保持率を下回る"))
            continue

        effective_total_invested_pct = config.max_total_invested_pct
        if normalized_market_context is not None and normalized_market_context["regime"] == "BEAR":
            effective_total_invested_pct = min(
                config.max_total_invested_pct,
                config.bear_max_total_invested_pct,
            )
        portfolio_capacity = _portfolio_capacity_yen(
            equity,
            projected_market_value,
            effective_total_invested_pct,
        )
        if portfolio_capacity + 1e-9 < value:
            decisions.append(_reject(order, "総投資率上限を超過"))
            continue

        ticker_value = projected_positions.get(order.ticker, 0.0) + value
        ticker_ratio = ticker_value / equity if equity > 0 else 1.0
        if ticker_ratio > config.max_single_position_pct:
            decisions.append(_reject(order, "1銘柄投資率上限を超過"))
            continue

        accepted.append(order)
        projected_cash = post_cash
        projected_market_value = post_market
        projected_positions[order.ticker] = ticker_value

        decisions.append(
            RiskDecision(
                ticker=order.ticker,
                side=order.side.value,
                quantity=order.quantity,
                price=order.limit_price,
                accepted=True,
                reason="全リスク条件PASS",
                estimated_value_yen=value,
            )
        )

    return RiskReport(
        broker_name=broker.broker_name,
        health_pass=health.healthy,
        equity_yen=equity,
        cash_yen=snapshot.cash_yen,
        market_value_yen=snapshot.market_value_yen,
        daily_pnl_yen=daily_pnl,
        daily_loss_pct=round(daily_loss_pct, 6),
        drawdown_pct=round(drawdown_pct, 6),
        current_positions=len(snapshot.positions),
        consecutive_losses=state.consecutive_losses,
        halted=state.halted,
        halt_reason=state.halt_reason,
        accepted_orders=tuple(accepted),
        decisions=tuple(decisions),
    )


def save_risk_outputs(
    report: RiskReport,
    approved_path: Path,
    report_path: Path,
) -> None:
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    approved = []
    for order in report.accepted_orders:
        approved.append(
            {
                "ticker": order.ticker,
                "side": order.side.value,
                "quantity": order.quantity,
                "order_type": order.order_type.value,
                "limit_price": order.limit_price,
                "client_order_id": order.client_order_id,
                "strategy_name": order.strategy_name,
                "metadata": order.metadata,
            }
        )

    approved_path.write_text(
        json.dumps(
            {
                "version": "PHOENIX v7.0 Step5",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "approved_count": len(approved),
                "orders": approved,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "=" * 110,
        "PHOENIX v7 RISK CONTROLLER",
        "=" * 110,
        f"Broker Health      : {'PASS' if report.health_pass else 'FAIL'}",
        f"現在資産           : {report.equity_yen:,.0f}円",
        f"日次損益           : {report.daily_pnl_yen:+,.0f}円",
        f"日次損失率         : {report.daily_loss_pct:.2%}",
        f"ドローダウン       : {report.drawdown_pct:.2%}",
        f"保有銘柄数         : {report.current_positions}件",
        f"連敗数             : {report.consecutive_losses}回",
        f"システム停止       : {'YES' if report.halted else 'NO'}",
        f"停止理由           : {report.halt_reason or '-'}",
        "-" * 110,
    ]
    for decision in report.decisions:
        status = "APPROVE" if decision.accepted else "REJECT"
        lines.append(
            f"{status:8} {decision.side:4} {decision.ticker:10} "
            f"{decision.quantity:6}株 {decision.price:,.2f}円 "
            f"{decision.reason}"
        )
    lines.extend(
        [
            "-" * 110,
            f"承認注文数         : {len(report.accepted_orders)}件",
            "=" * 110,
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
