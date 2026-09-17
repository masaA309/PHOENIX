from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd

from phoenix_core.broker import PaperBroker
from phoenix_core.historical_validation_20y import (
    ConfirmedExecutionFill,
    D1EntryDecision,
    PendingOrder,
    StrategyAccountView,
    StrategyRuntimeState,
    _is_member_on_date,
    _pending_portfolio_risk_yen,
    _positions_portfolio_risk_yen,
    apply_confirmed_entry_fill,
    evaluate_d1_entry,
    normalize_ticker_code,
)
from phoenix_core.models import (
    AccountSnapshot,
    BrokerHealth,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
)
from phoenix_core.rakuten_rss_broker import (
    RakutenRssBroker,
    RakutenRssOrderObservation,
)


class StrategyExecutionAdapter(Protocol):
    def account_snapshot(self) -> AccountSnapshot: ...

    def executable_buy_price(self, ticker: str, execution_date: pd.Timestamp) -> float | None: ...

    def submit_entry(self, decision: D1EntryDecision, client_order_id: str) -> OrderResult: ...

    def refresh(self) -> object: ...

    def reconcile(self) -> object: ...


class PaperStrategyExecutionAdapter:
    def __init__(
        self,
        broker: PaperBroker,
        executable_price: Callable[[str, pd.Timestamp], float | None],
    ) -> None:
        self._broker = broker
        self._executable_price = executable_price

    def account_snapshot(self) -> AccountSnapshot:
        return self._broker.get_account_snapshot()

    def executable_buy_price(self, ticker: str, execution_date: pd.Timestamp) -> float | None:
        price = self._executable_price(ticker, execution_date)
        if price is None:
            return None
        value = float(price)
        return value if math.isfinite(value) and value > 0 else None

    def submit_entry(self, decision: D1EntryDecision, client_order_id: str) -> OrderResult:
        return self._broker.submit_order(
            OrderRequest(
                ticker=decision.ticker,
                side=OrderSide.BUY,
                quantity=decision.final_quantity,
                order_type=OrderType.LIMIT,
                limit_price=decision.sizing_price,
                client_order_id=client_order_id,
                strategy_name="PHOENIX",
                metadata={"action": "ENTRY"},
            )
        )

    def refresh(self) -> list[OrderResult]:
        return self._broker.refresh_pending_orders()

    def reconcile(self) -> AccountSnapshot:
        return self._broker.get_account_snapshot()


def deterministic_entry_client_order_id(
    ticker: str,
    signal_date: str | date,
    execution_date: str | date | pd.Timestamp,
) -> str:
    identity = {
        "action": "ENTRY",
        "execution_date": pd.Timestamp(execution_date).date().isoformat(),
        "signal_date": pd.Timestamp(signal_date).date().isoformat(),
        "strategy_name": "PHOENIX",
        "strategy_version": "v7",
        "ticker": normalize_ticker_code(ticker),
    }
    encoded = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"PHOENIX-ENTRY-{hashlib.sha256(encoded).hexdigest()}"


def execute_paper_session_open_entries(
    state: StrategyRuntimeState,
    current_date: str | date | pd.Timestamp,
    adapter: PaperStrategyExecutionAdapter,
) -> tuple[D1EntryDecision, ...]:
    current_ts = pd.Timestamp(current_date).normalize()
    due_orders = state.pending_orders.pop(current_ts, [])
    state.reserved_cash = max(
        state.reserved_cash - sum(order.estimated_cost_yen for order in due_orders),
        0.0,
    )
    decisions = []
    for pending in sorted(due_orders, key=lambda item: (-item.signal_score, item.ticker)):
        ticker = normalize_ticker_code(pending.ticker)
        if ticker in state.positions:
            continue
        if state.uses_membership and not _is_member_on_date(
            state.membership_lookup.get(ticker, []), current_ts
        ):
            continue
        sizing_price = adapter.executable_buy_price(ticker, current_ts)
        if sizing_price is None:
            continue
        snapshot = adapter.account_snapshot()
        state.cash = snapshot.cash_yen
        remaining_pending_risk = _pending_portfolio_risk_yen(state.pending_orders)
        account = StrategyAccountView(
            cash_yen=snapshot.cash_yen - state.reserved_cash,
            market_value_yen=snapshot.market_value_yen,
            equity_yen=snapshot.equity_yen,
            current_exposure_yen=snapshot.market_value_yen + state.reserved_cash,
            current_portfolio_risk_yen=(
                _positions_portfolio_risk_yen(state.positions)
                + remaining_pending_risk
            ),
        )
        decision = evaluate_d1_entry(
            state,
            pending,
            current_date=current_ts,
            sizing_price=sizing_price,
            account=account,
            same_session_committed_exposure_yen=0.0,
            same_session_committed_risk_yen=0.0,
        )
        decisions.append(decision)
        if decision.rejection_reason or decision.final_quantity < state.config.lot_size:
            continue
        client_order_id = deterministic_entry_client_order_id(
            ticker, pending.signal_date, current_ts
        )
        result = adapter.submit_entry(decision, client_order_id)
        if result.status is not OrderStatus.FILLED:
            continue
        fill = ConfirmedExecutionFill(
            client_order_id=result.client_order_id,
            broker_order_id=result.broker_order_id,
            ticker=result.ticker,
            side=result.side.value,
            filled_quantity=result.filled_quantity,
            fill_price=result.filled_price,
            commission_yen=result.commission_yen,
            observed_at=result.created_at.isoformat(),
            final=True,
        )
        apply_confirmed_entry_fill(state, pending, decision, fill)
        state.cash = adapter.account_snapshot().cash_yen
    return tuple(decisions)


@dataclass(frozen=True, slots=True)
class RakutenReconcileSnapshot:
    health: BrokerHealth
    account: AccountSnapshot
    orders: tuple[RakutenRssOrderObservation, ...]
    nonterminal_order_count: int


class RakutenReconcileOnlyStrategyExecutionAdapter:
    def __init__(self, broker: RakutenRssBroker) -> None:
        self._broker = broker

    def account_snapshot(self) -> AccountSnapshot:
        return self._broker.get_account_snapshot()

    def executable_buy_price(self, ticker: str, execution_date: pd.Timestamp) -> float | None:
        raise RuntimeError("LIVE_RECONCILE_ONLY has no entry-price authority")

    def submit_entry(self, decision: D1EntryDecision, client_order_id: str) -> OrderResult:
        raise RuntimeError("LIVE_RECONCILE_ONLY has no order-submit authority")

    def refresh(self) -> RakutenReconcileSnapshot:
        return self.reconcile()

    def reconcile(self) -> RakutenReconcileSnapshot:
        return RakutenReconcileSnapshot(
            health=self._broker.health_check(),
            account=self._broker.get_account_snapshot(),
            orders=self._broker.get_order_observations(),
            nonterminal_order_count=self._broker.nonterminal_order_count(),
        )


class RakutenLiveStrategyExecutionAdapter:
    def __init__(self, broker: RakutenRssBroker) -> None:
        self._broker = broker

    def account_snapshot(self) -> AccountSnapshot:
        return self._broker.get_account_snapshot()

    def executable_buy_price(self, ticker: str, execution_date: pd.Timestamp) -> float | None:
        return self._broker.executable_buy_price(ticker)

    def submit_entry(self, decision: D1EntryDecision, client_order_id: str) -> OrderResult:
        expected_id = deterministic_entry_client_order_id(
            decision.ticker, decision.signal_date, decision.execution_date
        )
        if client_order_id != expected_id:
            raise ValueError("client_order_id does not match the entry decision")
        if not math.isfinite(float(decision.sizing_price)) or decision.sizing_price <= 0:
            raise ValueError("decision sizing_price must be finite and positive")
        return self._broker.submit_order(
            OrderRequest(
                ticker=decision.ticker,
                side=OrderSide.BUY,
                quantity=decision.final_quantity,
                order_type=OrderType.LIMIT,
                limit_price=decision.sizing_price,
                client_order_id=client_order_id,
                strategy_name="PHOENIX",
                metadata={"action": "ENTRY"},
            )
        )

    def submit_order_request(self, order: OrderRequest) -> OrderResult:
        order.validate()
        if order.side is not OrderSide.BUY:
            raise ValueError("LIVE entry adapter accepts BUY orders only")
        return self._broker.submit_order(order)

    def refresh(self) -> list[OrderResult]:
        return self._broker.refresh_pending_orders()

    def reconcile(self) -> RakutenReconcileSnapshot:
        return RakutenReconcileSnapshot(
            health=self._broker.health_check(),
            account=self._broker.get_account_snapshot(),
            orders=self._broker.get_order_observations(),
            nonterminal_order_count=self._broker.nonterminal_order_count(),
        )


def create_rakuten_live_execution_adapter(
    broker: RakutenRssBroker,
) -> RakutenLiveStrategyExecutionAdapter:
    if not isinstance(broker, RakutenRssBroker):
        raise TypeError("LIVE execution adapter requires RakutenRssBroker")
    return RakutenLiveStrategyExecutionAdapter(broker)


def create_rakuten_reconcile_only_execution_adapter(
    config: dict[str, Any],
    root_dir: Path,
) -> RakutenReconcileOnlyStrategyExecutionAdapter:
    operating_mode = str(config.get("operating_mode", "")).strip().upper()
    if operating_mode != "LIVE_RECONCILE_ONLY":
        raise ValueError("operating_mode must be exactly LIVE_RECONCILE_ONLY")
    broker_config = config.get("broker", {})
    if bool(broker_config.get("production_live_fire_armed", False)):
        raise ValueError("LIVE_RECONCILE_ONLY must remain unarmed")
    from phoenix_core.factory import create_broker

    broker = create_broker(config, root_dir)
    if not isinstance(broker, RakutenRssBroker):
        raise TypeError("LIVE_RECONCILE_ONLY factory must return RakutenRssBroker")
    return RakutenReconcileOnlyStrategyExecutionAdapter(broker)


def _runtime_json_safe_value(value: Any) -> Any:
    from dataclasses import asdict, is_dataclass
    from enum import Enum

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if type(value).__module__ == "numpy" and hasattr(value, "item"):
        return _runtime_json_safe_value(value.item())
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Runtime checkpoint contains a non-finite value")
        return value
    if isinstance(value, pd.Timestamp):
        return {"__type__": "pd.Timestamp", "value": value.isoformat()}
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _runtime_json_safe_value(asdict(value))
    if isinstance(value, tuple):
        return {"__type__": "tuple", "items": [_runtime_json_safe_value(item) for item in value]}
    if isinstance(value, list):
        return [_runtime_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {
            "__type__": "dict",
            "items": [
                [_runtime_json_safe_value(key), _runtime_json_safe_value(item)]
                for key, item in sorted(value.items(), key=lambda pair: repr(pair[0]))
            ],
        }
    raise ValueError(f"Runtime checkpoint value is not JSON-safe: {type(value).__name__}")


def _runtime_json_restore_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_runtime_json_restore_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    tag = value.get("__type__")
    if tag == "pd.Timestamp":
        return pd.Timestamp(value["value"])
    if tag == "datetime":
        return datetime.fromisoformat(value["value"])
    if tag == "date":
        return date.fromisoformat(value["value"])
    if tag == "tuple":
        return tuple(_runtime_json_restore_value(item) for item in value["items"])
    if tag == "dict":
        return {
            _runtime_json_restore_value(key): _runtime_json_restore_value(item)
            for key, item in value["items"]
        }
    raise ValueError("Runtime checkpoint contains an unknown tagged value")


def strategy_runtime_state_to_payload(
    state: StrategyRuntimeState, *, last_completed_strategy_session: Any
) -> dict[str, Any]:
    from dataclasses import asdict

    fields = {
        name: getattr(state, name)
        for name in state.__dataclass_fields__
        if name != "strategy"
    }
    fields["last_completed_strategy_session"] = last_completed_strategy_session
    return {"schema_version": 1, "state": _runtime_json_safe_value(fields)}


def strategy_runtime_state_from_payload(payload: dict[str, Any]) -> StrategyRuntimeState:
    from collections import Counter
    from phoenix_core.historical_validation_20y import HistoricalValidationConfig, PositionState, TradeRecord

    if not isinstance(payload, dict) or set(payload) != {"schema_version", "state"} or payload["schema_version"] != 1:
        raise ValueError("Unsupported strategy runtime checkpoint")
    restored = _runtime_json_restore_value(payload["state"])
    if not isinstance(restored, dict):
        raise ValueError("Strategy runtime checkpoint state must be an object")
    config = HistoricalValidationConfig(**restored.pop("config"))
    config.validate()
    restored["positions"] = {key: PositionState(**item) for key, item in restored.get("positions", {}).items()}
    restored["pending_orders"] = {
        pd.Timestamp(key): [PendingOrder(**item) for item in items]
        for key, items in restored.get("pending_orders", {}).items()
    }
    restored["trades"] = [TradeRecord(**item) for item in restored.get("trades", [])]
    restored["diagnostics_counts"] = Counter(restored.get("diagnostics_counts", {}))
    state = StrategyRuntimeState(config=config, strategy=config.strategy_parameters(), **restored)
    return state


def save_strategy_runtime_checkpoint(
    path: Path, state: StrategyRuntimeState, *, last_completed_strategy_session: Any
) -> None:
    from phoenix_core.historical_validation_20y import atomic_write
    payload = strategy_runtime_state_to_payload(
        state, last_completed_strategy_session=last_completed_strategy_session
    )
    atomic_write(path, json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def load_strategy_runtime_checkpoint(path: Path) -> StrategyRuntimeState:
    return strategy_runtime_state_from_payload(json.loads(path.read_text(encoding="utf-8")))


def apply_entry_order_observation(
    state: StrategyRuntimeState,
    pending: PendingOrder,
    decision: D1EntryDecision,
    result: OrderResult,
    account: AccountSnapshot,
    protection_sync: Callable[..., Any] | None = None,
) -> object | None:
    ticker = normalize_ticker_code(decision.ticker)
    expected_client_id = deterministic_entry_client_order_id(ticker, pending.signal_date, decision.execution_date)
    if result.client_order_id != expected_client_id or not result.broker_order_id:
        raise ValueError("Broker order identity does not match the entry decision")
    if normalize_ticker_code(result.ticker) != ticker or result.side is not OrderSide.BUY:
        raise ValueError("Broker order observation does not match the entry decision")
    if (result.quantity != decision.final_quantity or result.filled_quantity < 0
            or result.filled_quantity > result.quantity
            or round(result.requested_price, 2) != round(decision.sizing_price, 2)):
        raise ValueError("Broker order observation quantity is invalid")
    if account.broker_name != result.broker_name or not math.isfinite(float(account.cash_yen)):
        raise ValueError("Broker account identity is invalid")
    broker_position = next((position for position in account.positions if normalize_ticker_code(position.ticker) == ticker), None)
    if result.filled_quantity > 0 and (broker_position is None or broker_position.quantity != result.filled_quantity
                                      or round(broker_position.average_price, 2) != round(result.filled_price, 2)):
        raise ValueError("Broker account snapshot does not confirm the cumulative fill")
    if result.filled_quantity <= 0:
        return None
    fill = ConfirmedExecutionFill(
        client_order_id=result.client_order_id,
        broker_order_id=result.broker_order_id,
        ticker=result.ticker,
        side=result.side.value,
        filled_quantity=result.filled_quantity,
        fill_price=result.filled_price,
        commission_yen=result.commission_yen,
        observed_at=result.created_at.isoformat(),
        final=result.status in {OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED},
    )
    position = apply_confirmed_entry_fill(state, pending, decision, fill)
    state.cash = account.cash_yen
    if protection_sync is not None:
        protection_sync(
            client_order_id=result.client_order_id,
            broker_order_id=result.broker_order_id,
            ticker=ticker,
            quantity=result.filled_quantity,
            entry_price=result.filled_price,
            target_price=position.actual_target_price,
            stop_price=position.actual_stop_price,
            observed_at=result.created_at,
        )
    return position
