from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from phoenix_core.broker import BrokerAdapter
from phoenix_core.models import (
    AccountSnapshot,
    BrokerHealth,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
)
from phoenix_core.rakuten_rss_adapter import (
    MockRakutenRssAdapter,
    RakutenRssAdapter,
    RakutenRssOrderUpdate,
)


JST = ZoneInfo("Asia/Tokyo")

PENDING_STATUSES = {OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED}
FINAL_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.REJECTED,
    OrderStatus.CANCELED,
}


def _now_jst() -> datetime:
    return datetime.now(JST)


def _normalize_dt(value: datetime | None) -> datetime:
    if value is None:
        return _now_jst()
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=JST)
    return value.astimezone(JST)


def _iso(value: datetime) -> str:
    return _normalize_dt(value).isoformat(timespec="microseconds")


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _normalize_dt(parsed)


def _canonical_event_sha256(event: dict[str, Any]) -> str:
    canonical = {
        key: value
        for key, value in event.items()
        if key != "event_sha256"
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_int(value: Any, default: int = -1) -> int:
    try:
        if value is None or value == "":
            return default
        result = int(value)
        if result == 0 and default != 0:
            return default
        return result
    except Exception:
        return default


def _optional_text(value: Any, default: str = "") -> str:
    text = "" if value is None else str(value).strip()
    return text if text else default


@dataclass(slots=True)
class _MutablePosition:
    quantity: int
    average_price: float
    market_price: float
    economics_tracked_quantity: int = 0
    economics_tracked_cost_basis_yen: float = 0.0


class RakutenRssBroker(BrokerAdapter):
    STATE_VERSION = 1
    FILL_EVENT_VERSION = 1

    def __init__(
        self,
        initial_cash_yen: float = 300_000.0,
        commission_rate: float = 0.0,
        state_file: Path | None = None,
        *,
        adapter: RakutenRssAdapter | None = None,
        live_enabled: bool = False,
        timeout_seconds: int = 300,
    ) -> None:
        if (
            isinstance(initial_cash_yen, bool)
            or not isinstance(initial_cash_yen, Real)
            or not math.isfinite(float(initial_cash_yen))
            or initial_cash_yen < 0
        ):
            raise ValueError("initial_cash_yenは0以上の有限数にしてください")
        if (
            isinstance(commission_rate, bool)
            or not isinstance(commission_rate, Real)
            or not math.isfinite(float(commission_rate))
            or commission_rate < 0
        ):
            raise ValueError("commission_rateは0以上の有限数にしてください")
        if isinstance(timeout_seconds, bool) or timeout_seconds < 0:
            raise ValueError("timeout_secondsは0以上の整数にしてください")

        self._initial_cash_yen = round(float(initial_cash_yen), 2)
        self._cash_yen = self._initial_cash_yen
        self._commission_rate = float(commission_rate)
        self._state_file = state_file
        self._adapter = adapter or MockRakutenRssAdapter()
        self._live_enabled = bool(live_enabled)
        self._timeout_seconds = int(timeout_seconds)
        self._kill_switch_engaged = False
        self._kill_switch_reason = ""
        self._positions: dict[str, _MutablePosition] = {}
        self._realized_pnl_yen = 0.0
        self._orders: dict[str, dict[str, Any]] = {}
        self._fill_events: list[dict[str, Any]] = []
        self._loaded_state_version: int | None = None
        self._lock = RLock()

        self._load_state()

    @property
    def broker_name(self) -> str:
        return "RAKUTEN_RSS"

    def health_check(self) -> BrokerHealth:
        try:
            if self._state_file is not None:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
            adapter_health = self._adapter.health_check()
            live_enabled = self._live_enabled and not self._kill_switch_engaged
            if not self._live_enabled:
                message = "Rakuten RSS broker is disabled until live_trading_enabled=true."
            elif self._kill_switch_engaged:
                message = f"Kill switch engaged: {self._kill_switch_reason or 'UNKNOWN'}"
            elif not adapter_health.healthy:
                message = f"Rakuten RSS adapter unhealthy: {adapter_health.message}"
            else:
                message = "Rakuten RSS dry-run broker ready. Mock adapter only; no real RSS send."
            healthy = live_enabled and adapter_health.healthy
            return BrokerHealth(
                broker_name=self.broker_name,
                healthy=healthy,
                live_trading_enabled=live_enabled,
                message=message,
                checked_at=_now_jst(),
            )
        except OSError as error:
            return BrokerHealth(
                broker_name=self.broker_name,
                healthy=False,
                live_trading_enabled=False,
                message=f"状態保存先異常: {error}",
                checked_at=_now_jst(),
            )

    def initialize_economics_baseline(self) -> bool:
        with self._lock:
            if self._loaded_state_version == self.STATE_VERSION:
                return False
            if self._state_file is None:
                raise ValueError(
                    "economics baselineのatomic保存にはstate_fileが必要です"
                )
            self._save_state()
            return True

    def reset(self) -> None:
        with self._lock:
            self._cash_yen = self._initial_cash_yen
            self._positions.clear()
            self._realized_pnl_yen = 0.0
            self._orders.clear()
            self._fill_events.clear()
            self._kill_switch_engaged = False
            self._kill_switch_reason = ""
            self._save_state()

    def set_market_price(self, ticker: str, market_price: float) -> None:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            raise ValueError("tickerが空です")
        if (
            isinstance(market_price, bool)
            or not isinstance(market_price, Real)
            or not math.isfinite(float(market_price))
            or market_price <= 0
        ):
            raise ValueError("market_priceは0より大きい有限数にしてください")
        with self._lock:
            position = self._positions.get(normalized_ticker)
            if position is not None:
                position.market_price = round(float(market_price), 2)
                self._save_state()

    def get_account_snapshot(self) -> AccountSnapshot:
        with self._lock:
            positions = tuple(
                Position(
                    ticker=ticker,
                    quantity=position.quantity,
                    average_price=position.average_price,
                    market_price=position.market_price,
                )
                for ticker, position in sorted(self._positions.items())
                if position.quantity > 0
            )
            return AccountSnapshot(
                broker_name=self.broker_name,
                cash_yen=round(self._cash_yen, 2),
                positions=positions,
                realized_pnl_yen=round(self._realized_pnl_yen, 2),
                generated_at=_now_jst(),
            )

    def submit_order(self, order: OrderRequest) -> OrderResult:
        order.validate()
        ticker = order.ticker.strip().upper()

        with self._lock:
            existing = self._orders.get(order.client_order_id)
            if existing is not None:
                return self._result_from_record(existing)

            broker_health = self.health_check()
            if not broker_health.healthy:
                return self._record_rejected(
                    order=order,
                    ticker=ticker,
                    message=broker_health.message,
                )

            if order.side is OrderSide.BUY:
                can_submit, reason = self._validate_buy(order, ticker)
            elif order.side is OrderSide.SELL:
                can_submit, reason = self._validate_sell(order, ticker)
            else:
                can_submit, reason = False, "未対応の売買区分です"

            if not can_submit:
                return self._record_rejected(order=order, ticker=ticker, message=reason)

            broker_order_id = f"RSS-{uuid4().hex[:16].upper()}"
            submitted_at = _now_jst()
            try:
                ack = self._adapter.submit_order(order, broker_order_id)
            except Exception as error:  # pragma: no cover - adapter failure is fail-closed
                return self._record_rejected(
                    order=order,
                    ticker=ticker,
                    message=f"Rakuten RSS adapter submit failed: {error}",
                    broker_order_id=broker_order_id,
                    submitted_at=submitted_at,
                    rss_order_id=0,
                    authoritative_rss_status=-1,
                )

            if ack.status is OrderStatus.REJECTED:
                return self._record_rejected(
                    order=order,
                    ticker=ticker,
                    message=ack.message or "Rakuten RSS adapter rejected the order",
                    broker_order_id=broker_order_id,
                    submitted_at=submitted_at,
                    rss_order_id=_optional_int(getattr(ack, "rss_order_id", 0), 0),
                    rss_order_number=_optional_text(getattr(ack, "rss_order_number", "")),
                    authoritative_rss_status=_optional_int(
                        getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
                        -1,
                    ),
                )

            rss_order_id = _optional_int(getattr(ack, "rss_order_id", 0), 0)
            rss_order_number = _optional_text(getattr(ack, "rss_order_number", ""))
            authoritative_rss_status = _optional_int(
                getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
                -1,
            )
            record_status = ack.status if ack.status in {OrderStatus.PENDING, OrderStatus.ACCEPTED} else OrderStatus.PENDING
            if ack.status is OrderStatus.PENDING:
                message = ack.message or "Rakuten RSS order staged and awaiting VBA receipt"
            elif ack.status is OrderStatus.ACCEPTED:
                message = ack.message or "Rakuten RSS order accepted into dry-run queue"
            else:
                message = ack.message or f"Rakuten RSS tracked order requires reconciliation: {ack.status.value}"

            record = self._new_record(
                order=order,
                ticker=ticker,
                broker_order_id=broker_order_id,
                status=record_status,
                message=message,
                submitted_at=submitted_at,
                updated_at=ack.submitted_at,
                rss_order_id=rss_order_id,
                rss_order_number=rss_order_number,
                broker_observation_state=ack.status.value,
                cancel_observation_state="",
                last_authoritative_rss_status=authoritative_rss_status,
            )
            self._orders[order.client_order_id] = record
            self._save_state()
            return self._result_from_record(record)

    def refresh_pending_orders(
        self,
        *,
        now: datetime | None = None,
    ) -> list[OrderResult]:
        with self._lock:
            if not self._live_enabled or self._kill_switch_engaged:
                return []
            if not self._adapter.health_check().healthy:
                return self.engage_kill_switch("Rakuten RSS adapter unhealthy")

            checked_at = _normalize_dt(now)
            results: list[OrderResult] = []
            changed = False

            pending_items = sorted(
                (
                    record
                    for record in self._orders.values()
                    if OrderStatus(record["status"]) in PENDING_STATUSES
                ),
                key=lambda item: item["submitted_at"],
            )

            for record in pending_items:
                broker_order_id = str(record["broker_order_id"])
                try:
                    updates = self._adapter.poll_order(broker_order_id)
                except Exception as error:  # pragma: no cover - adapter failure is fail-closed
                    self.engage_kill_switch(f"Rakuten RSS poll failed: {error}")
                    return results
                for update in updates:
                    result = self._apply_update(record, update)
                    results.append(result)
                    changed = True
                    if _phoenix_sync_protective_order_update(self, record, update):
                        changed = True
                    if OrderStatus(record["status"]) in FINAL_STATUSES:
                        break
                if OrderStatus(record["status"]) in FINAL_STATUSES:
                    continue
                submitted_at = _parse_iso(str(record["submitted_at"]))
                age = checked_at - submitted_at
                observed_status = _optional_text(record.get("broker_observation_state"))
                last_authoritative_status = _optional_int(record.get("last_authoritative_rss_status", -1), -1)
                if observed_status == OrderStatus.ACCEPTED.value or last_authoritative_status == 2:
                    continue
                if self._timeout_seconds == 0 or age >= timedelta(seconds=self._timeout_seconds):
                    if record.get("broker_observation_state") != "RECONCILE_PENDING":
                        record["broker_observation_state"] = "RECONCILE_PENDING"
                    record["message"] = (
                        "Rakuten RSS order timed out waiting for observation; reconciliation continues."
                    )
                    record["updated_at"] = _iso(checked_at)
                    result = self._result_from_record(record)
                    results.append(result)
                    changed = True

            if changed:
                self._save_state()
            return results

    def nonterminal_order_count(self) -> int:
        with self._lock:
            return sum(
                1
                for record in self._orders.values()
                if OrderStatus(record["status"]) in PENDING_STATUSES
            )

    def cancel_order(self, client_order_id: str, message: str | None = None) -> OrderResult:
        with self._lock:
            record = self._orders.get(client_order_id)
            if record is None:
                raise ValueError(f"client_order_idが見つかりません: {client_order_id}")
            if OrderStatus(record["status"]) in FINAL_STATUSES:
                return self._result_from_record(record)
            if not _optional_text(record.get("rss_order_number")):
                record["cancel_observation_state"] = "WAITING_FOR_ORDER_NUMBER"
                record["message"] = message or "RSS order number is missing for cancel."
                record["updated_at"] = _iso(_now_jst())
                self._save_state()
                return self._result_from_record(record)
            try:
                ack = self._adapter.cancel_order(str(record["broker_order_id"]))
            except Exception as error:  # pragma: no cover - adapter failure is fail-closed
                self.engage_kill_switch(f"Rakuten RSS cancel failed: {error}")
                return self._result_from_record(record)
            candidate_rss_order_id = _optional_int(getattr(ack, "rss_order_id", 0), 0)
            record["rss_order_id"] = candidate_rss_order_id
            record["rss_order_number"] = _optional_text(
                getattr(ack, "rss_order_number", record.get("rss_order_number", "")),
                record.get("rss_order_number", ""),
            )
            authoritative_rss_status = _optional_int(
                getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
                -1,
            )
            if authoritative_rss_status != -1:
                record["last_authoritative_rss_status"] = authoritative_rss_status
            if ack.status is OrderStatus.PENDING:
                record["status"] = OrderStatus.PENDING.value
                record["message"] = message or ack.message or "Rakuten RSS cancel staged and awaiting VBA receipt"
                record["updated_at"] = _iso(ack.canceled_at)
                record["cancel_observation_state"] = OrderStatus.PENDING.value
                self._save_state()
                return self._result_from_record(record)
            if ack.status is OrderStatus.CANCELED:
                record["cancel_observation_state"] = OrderStatus.CANCELED.value
                result = self._finalize_record(
                    record,
                    status=OrderStatus.CANCELED,
                    message=message or ack.message or "Rakuten RSS order canceled",
                    updated_at=ack.canceled_at,
                )
            elif ack.status is OrderStatus.FILLED:
                record["cancel_observation_state"] = OrderStatus.FILLED.value
                result = self._finalize_record(
                    record,
                    status=OrderStatus.FILLED,
                    message=message or ack.message or "Rakuten RSS order filled before cancel",
                    updated_at=ack.canceled_at,
                )
            else:
                record["cancel_observation_state"] = "RECONCILE_PENDING"
                record["message"] = message or ack.message or "Rakuten RSS cancel pending reconciliation"
                record["updated_at"] = _iso(ack.canceled_at)
                result = self._result_from_record(record)
            self._save_state()
            return result

    def engage_kill_switch(self, reason: str) -> list[OrderResult]:
        with self._lock:
            self._kill_switch_engaged = True
            self._kill_switch_reason = reason.strip() or "KILL_SWITCH"
            results: list[OrderResult] = []
            for record in self._orders.values():
                if OrderStatus(record["status"]) not in PENDING_STATUSES:
                    continue
                try:
                    cancel_ack = self._adapter.cancel_order(str(record["broker_order_id"]))
                except Exception:
                    cancel_ack = None
                pending_cancel = bool(cancel_ack and cancel_ack.status is OrderStatus.PENDING)
                results.append(
                    self._finalize_record(
                        record,
                        status=OrderStatus.PENDING if pending_cancel else OrderStatus.CANCELED,
                        message=(
                            f"Kill switch: {self._kill_switch_reason} (cancel staged)"
                            if pending_cancel
                            else f"Kill switch: {self._kill_switch_reason}"
                        ),
                        updated_at=_now_jst(),
                    )
                )
            self._save_state()
            return results

    def _validate_buy(self, order: OrderRequest, ticker: str) -> tuple[bool, str]:
        gross = round(order.quantity * order.limit_price, 2)
        commission = round(gross * self._commission_rate, 2)
        total_cost = round(gross + commission, 2)
        if total_cost > self._cash_yen:
            return False, (
                f"買付余力不足: 必要額 {total_cost:,.2f}円 / "
                f"現金 {self._cash_yen:,.2f}円"
            )
        current = self._positions.get(ticker)
        if (
            current is not None
            and current.economics_tracked_quantity < current.quantity
        ):
            return False, "Step19基準前の保有銘柄への買い増しは禁止されています"
        return True, ""

    def _validate_sell(self, order: OrderRequest, ticker: str) -> tuple[bool, str]:
        current = self._positions.get(ticker)
        if current is None or current.quantity < order.quantity:
            held = 0 if current is None else current.quantity
            return False, (
                f"保有株数不足: 売却 {order.quantity}株 / "
                f"保有 {held}株"
            )
        return True, ""

    def _new_record(
        self,
        *,
        order: OrderRequest,
        ticker: str,
        broker_order_id: str,
        status: OrderStatus,
        message: str,
        submitted_at: datetime,
        updated_at: datetime,
        rss_order_id: int = 0,
        rss_order_number: str = "",
        broker_observation_state: str | None = None,
        cancel_observation_state: str = "",
        last_authoritative_rss_status: int = -1,
    ) -> dict[str, Any]:
        return {
            "client_order_id": order.client_order_id,
            "broker_order_id": broker_order_id,
            "ticker": ticker,
            "side": order.side.value,
            "quantity": order.quantity,
            "requested_price": round(order.limit_price, 2),
            "status": status.value,
            "message": message,
            "submitted_at": _iso(submitted_at),
            "updated_at": _iso(updated_at),
            "rss_order_id": int(rss_order_id),
            "rss_order_number": _optional_text(rss_order_number),
            "broker_observation_state": _optional_text(
                broker_observation_state,
                default=status.value,
            ),
            "cancel_observation_state": _optional_text(cancel_observation_state),
            "last_authoritative_rss_status": int(last_authoritative_rss_status),
            "filled_quantity": 0,
            "filled_notional_yen": 0.0,
            "filled_price": 0.0,
            "last_fill_quantity": 0,
            "last_fill_price": 0.0,
            "commission_yen": 0.0,
            "cash_delta_yen": 0.0,
            "cost_basis_released_yen": 0.0,
            "realized_pnl_before_commission_yen": 0.0,
            "economics_eligible_quantity": 0,
            "economics_eligible_commission_yen": 0.0,
            "economics_eligible_realized_pnl_before_commission_yen": 0.0,
            "adverse_slippage_yen": 0.0,
        }

    def _record_rejected(
        self,
        *,
        order: OrderRequest,
        ticker: str,
        message: str,
        broker_order_id: str | None = None,
        submitted_at: datetime | None = None,
        rss_order_id: int = 0,
        rss_order_number: str = "",
        authoritative_rss_status: int = -1,
    ) -> OrderResult:
        now = submitted_at or _now_jst()
        record = self._new_record(
            order=order,
            ticker=ticker,
            broker_order_id=broker_order_id or f"RSS-REJECT-{uuid4().hex[:16].upper()}",
            status=OrderStatus.REJECTED,
            message=message,
            submitted_at=now,
            updated_at=now,
            rss_order_id=rss_order_id,
            rss_order_number=rss_order_number,
            broker_observation_state=OrderStatus.REJECTED.value,
            cancel_observation_state="",
            last_authoritative_rss_status=authoritative_rss_status,
        )
        self._orders[order.client_order_id] = record
        self._save_state()
        return self._result_from_record(record)

    def _apply_update(
        self,
        record: dict[str, Any],
        update: RakutenRssOrderUpdate,
    ) -> OrderResult:
        status = update.status
        update_rss_order_id = _optional_int(getattr(update, "rss_order_id", 0), 0)
        update_rss_order_number = _optional_text(getattr(update, "rss_order_number", ""))
        update_authoritative_rss_status = _optional_int(
            getattr(update, "authoritative_rss_status", getattr(update, "rss_order_status", -1)),
            -1,
        )
        record["rss_order_id"] = update_rss_order_id
        if update_rss_order_number:
            record["rss_order_number"] = update_rss_order_number
        if update_authoritative_rss_status != -1:
            record["last_authoritative_rss_status"] = update_authoritative_rss_status
        if _optional_text(getattr(update, "rss_order_status", "")):
            record["broker_observation_state"] = _optional_text(getattr(update, "rss_order_status", ""))
        if status is OrderStatus.ACCEPTED:
            record["status"] = status.value
            record["message"] = update.message or record["message"]
            record["updated_at"] = _iso(update.updated_at)
            record["broker_observation_state"] = status.value
            return self._result_from_record(record)
        if status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
            if update.fill_quantity <= 0:
                raise ValueError("fill_quantityは1以上にしてください")
            return self._apply_fill(
                record,
                fill_quantity=update.fill_quantity,
                fill_price=update.fill_price,
                status=status,
                message=update.message,
                updated_at=update.updated_at,
            )
        if status is OrderStatus.TIMED_OUT:
            record["message"] = update.message or "Order timed out waiting for Excel/RSS result; reconciliation continues."
            record["updated_at"] = _iso(update.updated_at)
            record["broker_observation_state"] = "RECONCILE_PENDING"
            return self._result_from_record(record)
        if status in {OrderStatus.REJECTED, OrderStatus.CANCELED}:
            return self._finalize_record(
                record,
                status=status,
                message=update.message or status.value,
                updated_at=update.updated_at,
            )
        raise ValueError(f"未対応の更新状態です: {status.value}")

    def _apply_fill(
        self,
        record: dict[str, Any],
        *,
        fill_quantity: int,
        fill_price: float,
        status: OrderStatus,
        message: str,
        updated_at: datetime,
    ) -> OrderResult:
        current_quantity = int(record["filled_quantity"])
        requested_quantity = int(record["quantity"])
        remaining_quantity = requested_quantity - current_quantity
        if fill_quantity > remaining_quantity:
            raise ValueError("fill_quantityが残数量を超えています")
        ticker = str(record["ticker"])
        side = OrderSide(str(record["side"]))
        requested_price = float(record["requested_price"])

        if side is OrderSide.BUY:
            result = self._apply_buy_fill(
                ticker=ticker,
                fill_quantity=fill_quantity,
                fill_price=fill_price,
                requested_price=requested_price,
            )
        else:
            result = self._apply_sell_fill(
                ticker=ticker,
                fill_quantity=fill_quantity,
                fill_price=fill_price,
                requested_price=requested_price,
            )

        cumulative_filled = current_quantity + fill_quantity
        cumulative_notional = round(
            float(record["filled_notional_yen"]) + fill_quantity * fill_price,
            2,
        )
        average_price = round(cumulative_notional / cumulative_filled, 2)

        record["filled_quantity"] = cumulative_filled
        record["filled_notional_yen"] = cumulative_notional
        record["filled_price"] = average_price
        record["last_fill_quantity"] = fill_quantity
        record["last_fill_price"] = round(fill_price, 2)
        record["commission_yen"] = round(
            float(record["commission_yen"]) + result["commission_yen"],
            2,
        )
        record["cash_delta_yen"] = round(
            float(record["cash_delta_yen"]) + result["cash_delta_yen"],
            2,
        )
        record["cost_basis_released_yen"] = round(
            float(record["cost_basis_released_yen"]) + result["cost_basis_released_yen"],
            2,
        )
        record["realized_pnl_before_commission_yen"] = round(
            float(record["realized_pnl_before_commission_yen"])
            + result["realized_pnl_before_commission_yen"],
            2,
        )
        record["economics_eligible_quantity"] = int(record["economics_eligible_quantity"]) + result["economics_eligible_quantity"]
        record["economics_eligible_commission_yen"] = round(
            float(record["economics_eligible_commission_yen"])
            + result["economics_eligible_commission_yen"],
            2,
        )
        record["economics_eligible_realized_pnl_before_commission_yen"] = round(
            float(record["economics_eligible_realized_pnl_before_commission_yen"])
            + result["economics_eligible_realized_pnl_before_commission_yen"],
            2,
        )
        record["adverse_slippage_yen"] = round(
            float(record["adverse_slippage_yen"]) + result["adverse_slippage_yen"],
            2,
        )
        event = {
            "schema_version": self.FILL_EVENT_VERSION,
            "event_id": f"FILL|{record['broker_order_id']}|{len(self._fill_events) + 1}",
            "broker_name": self.broker_name,
            "broker_order_id": record["broker_order_id"],
            "client_order_id": record["client_order_id"],
            "ticker": ticker,
            "side": side.value,
            "status": status.value,
            "filled_quantity": fill_quantity,
            "filled_price": round(fill_price, 2),
            "gross_amount_yen": round(fill_quantity * fill_price, 2),
            "commission_yen": result["commission_yen"],
            "cash_delta_yen": result["cash_delta_yen"],
            "cost_basis_released_yen": result["cost_basis_released_yen"],
            "realized_pnl_before_commission_yen": result["realized_pnl_before_commission_yen"],
            "economics_eligible_quantity": result["economics_eligible_quantity"],
            "economics_eligible_commission_yen": result["economics_eligible_commission_yen"],
            "economics_eligible_realized_pnl_before_commission_yen": result["economics_eligible_realized_pnl_before_commission_yen"],
            "adverse_slippage_yen": result["adverse_slippage_yen"],
            "created_at": _iso(updated_at),
        }
        event["event_sha256"] = _canonical_event_sha256(event)
        self._fill_events.append(event)

        record["status"] = (
            OrderStatus.FILLED.value
            if cumulative_filled >= requested_quantity
            else OrderStatus.PARTIALLY_FILLED.value
        )
        record["message"] = message or record["message"] or status.value
        record["updated_at"] = _iso(updated_at)
        return self._result_from_record(record)

    def _apply_buy_fill(
        self,
        *,
        ticker: str,
        fill_quantity: int,
        fill_price: float,
        requested_price: float,
    ) -> dict[str, float]:
        gross = round(fill_quantity * fill_price, 2)
        commission = round(gross * self._commission_rate, 2)
        total_cost = round(gross + commission, 2)

        current = self._positions.get(ticker)
        if current is None:
            current = _MutablePosition(
                quantity=0,
                average_price=0.0,
                market_price=round(fill_price, 2),
            )
            self._positions[ticker] = current
        elif current.economics_tracked_quantity < current.quantity:
            raise ValueError("Step19基準前の保有銘柄への買い増しは禁止されています")

        old_cost = current.quantity * current.average_price
        new_quantity = current.quantity + fill_quantity
        new_average = (old_cost + fill_quantity * fill_price) / new_quantity
        current.quantity = new_quantity
        current.average_price = round(new_average, 4)
        current.market_price = round(fill_price, 2)
        current.economics_tracked_quantity += fill_quantity
        current.economics_tracked_cost_basis_yen = round(
            current.economics_tracked_cost_basis_yen + gross,
            2,
        )
        self._cash_yen = round(self._cash_yen - total_cost, 2)

        return {
            "commission_yen": commission,
            "cash_delta_yen": -total_cost,
            "cost_basis_released_yen": 0.0,
            "realized_pnl_before_commission_yen": 0.0,
            "economics_eligible_quantity": fill_quantity,
            "economics_eligible_commission_yen": commission,
            "economics_eligible_realized_pnl_before_commission_yen": 0.0,
            "adverse_slippage_yen": round(
                max(0.0, (fill_price - requested_price) * fill_quantity),
                2,
            ),
        }

    def _apply_sell_fill(
        self,
        *,
        ticker: str,
        fill_quantity: int,
        fill_price: float,
        requested_price: float,
    ) -> dict[str, float]:
        current = self._positions.get(ticker)
        if current is None or current.quantity < fill_quantity:
            held = 0 if current is None else current.quantity
            raise ValueError(
                f"保有株数不足: 売却 {fill_quantity}株 / 保有 {held}株"
            )

        gross = round(fill_quantity * fill_price, 2)
        commission = round(gross * self._commission_rate, 2)
        proceeds = round(gross - commission, 2)
        acquisition_cost = round(fill_quantity * current.average_price, 2)
        realized_before_commission = round(gross - acquisition_cost, 2)
        realized_pnl = round(realized_before_commission - commission, 2)

        legacy_quantity = max(0, current.quantity - current.economics_tracked_quantity)
        eligible_quantity = min(
            current.economics_tracked_quantity,
            max(0, fill_quantity - legacy_quantity),
        )
        if eligible_quantity > 0:
            tracked_average = (
                current.economics_tracked_cost_basis_yen
                / current.economics_tracked_quantity
            )
            eligible_cost_basis = round(tracked_average * eligible_quantity, 2)
            eligible_realized_before_commission = round(
                eligible_quantity * fill_price - eligible_cost_basis,
                2,
            )
            eligible_commission = round(
                commission * eligible_quantity / fill_quantity,
                2,
            )
            current.economics_tracked_quantity -= eligible_quantity
            current.economics_tracked_cost_basis_yen = round(
                current.economics_tracked_cost_basis_yen - eligible_cost_basis,
                2,
            )
        else:
            eligible_realized_before_commission = 0.0
            eligible_commission = 0.0

        current.quantity -= fill_quantity
        current.market_price = round(fill_price, 2)
        self._cash_yen = round(self._cash_yen + proceeds, 2)
        self._realized_pnl_yen = round(self._realized_pnl_yen + realized_pnl, 2)
        if current.quantity == 0:
            del self._positions[ticker]

        return {
            "commission_yen": commission,
            "cash_delta_yen": proceeds,
            "cost_basis_released_yen": acquisition_cost,
            "realized_pnl_before_commission_yen": realized_before_commission,
            "economics_eligible_quantity": eligible_quantity,
            "economics_eligible_commission_yen": eligible_commission,
            "economics_eligible_realized_pnl_before_commission_yen": eligible_realized_before_commission,
            "adverse_slippage_yen": round(
                max(0.0, (requested_price - fill_price) * fill_quantity),
                2,
            ),
        }

    def _finalize_record(
        self,
        record: dict[str, Any],
        *,
        status: OrderStatus,
        message: str,
        updated_at: datetime,
    ) -> OrderResult:
        record["status"] = status.value
        record["message"] = message
        record["updated_at"] = _iso(updated_at)
        return self._result_from_record(record)

    def _result_from_record(self, record: Mapping[str, Any]) -> OrderResult:
        status = OrderStatus(str(record["status"]))
        created_at = _parse_iso(str(record["updated_at"]))
        side = OrderSide(str(record["side"]))
        filled_quantity = int(record.get("filled_quantity", 0))
        filled_notional = float(record.get("filled_notional_yen", 0.0))
        filled_price = (
            round(filled_notional / filled_quantity, 2)
            if filled_quantity > 0
            else round(float(record.get("filled_price", 0.0)), 2)
        )
        return OrderResult(
            broker_name=self.broker_name,
            broker_order_id=str(record["broker_order_id"]),
            client_order_id=str(record["client_order_id"]),
            ticker=str(record["ticker"]),
            side=side,
            quantity=int(record["quantity"]),
            requested_price=round(float(record["requested_price"]), 2),
            filled_quantity=filled_quantity,
            filled_price=filled_price,
            status=status,
            message=str(record.get("message", "")),
            created_at=created_at,
            commission_yen=round(float(record.get("commission_yen", 0.0)), 2),
            cash_delta_yen=round(float(record.get("cash_delta_yen", 0.0)), 2),
            cost_basis_released_yen=round(float(record.get("cost_basis_released_yen", 0.0)), 2),
            realized_pnl_before_commission_yen=round(
                float(record.get("realized_pnl_before_commission_yen", 0.0)),
                2,
            ),
            economics_eligible_quantity=int(record.get("economics_eligible_quantity", 0)),
            economics_eligible_commission_yen=round(
                float(record.get("economics_eligible_commission_yen", 0.0)),
                2,
            ),
            economics_eligible_realized_pnl_before_commission_yen=round(
                float(record.get("economics_eligible_realized_pnl_before_commission_yen", 0.0)),
                2,
            ),
            adverse_slippage_yen=round(float(record.get("adverse_slippage_yen", 0.0)), 2),
        )

    def _state_payload(self) -> dict[str, Any]:
        return {
            "state_version": self.STATE_VERSION,
            "broker_name": self.broker_name,
            "adapter_name": type(self._adapter).__name__,
            "account_type": "CASH",
            "live_trading_enabled": self._live_enabled,
            "kill_switch_engaged": self._kill_switch_engaged,
            "kill_switch_reason": self._kill_switch_reason,
            "updated_at": _iso(_now_jst()),
            "initial_cash_yen": self._initial_cash_yen,
            "cash_yen": self._cash_yen,
            "commission_rate": self._commission_rate,
            "realized_pnl_yen": self._realized_pnl_yen,
            "positions": {
                ticker: {
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "market_price": position.market_price,
                    "economics_tracked_quantity": position.economics_tracked_quantity,
                    "economics_tracked_cost_basis_yen": position.economics_tracked_cost_basis_yen,
                }
                for ticker, position in sorted(self._positions.items())
            },
            "orders": self._orders,
            "fill_events": self._fill_events,
        }

    def _save_state(self) -> None:
        if self._state_file is None:
            return
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_file.with_suffix(self._state_file.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                self._state_payload(),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._state_file)
        self._loaded_state_version = self.STATE_VERSION

    def _load_state(self) -> None:
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Rakuten RSS Broker状態ファイルを読み込めません: {self._state_file}"
            ) from error
        if not isinstance(payload, dict):
            raise ValueError("Rakuten RSS Broker状態のルートはJSONオブジェクトにしてください")
        version = payload.get("state_version")
        if type(version) is not int or version != self.STATE_VERSION:
            raise ValueError("未対応のRakuten RSS Broker状態バージョンです")

        self._cash_yen = round(float(payload.get("cash_yen", self._initial_cash_yen)), 2)
        self._realized_pnl_yen = round(float(payload.get("realized_pnl_yen", 0.0)), 2)
        self._commission_rate = float(payload.get("commission_rate", self._commission_rate))
        self._live_enabled = bool(payload.get("live_trading_enabled", self._live_enabled))
        self._kill_switch_engaged = bool(payload.get("kill_switch_engaged", False))
        self._kill_switch_reason = str(payload.get("kill_switch_reason", ""))

        positions = payload.get("positions", {})
        if not isinstance(positions, dict):
            raise ValueError("positionsはJSONオブジェクトにしてください")
        self._positions = {}
        for ticker, value in positions.items():
            if not isinstance(value, dict):
                raise ValueError("positionはJSONオブジェクトにしてください")
            normalized_ticker = str(ticker).strip().upper()
            self._positions[normalized_ticker] = _MutablePosition(
                quantity=int(value.get("quantity", 0)),
                average_price=round(float(value.get("average_price", 0.0)), 4),
                market_price=round(float(value.get("market_price", 0.0)), 2),
                economics_tracked_quantity=int(value.get("economics_tracked_quantity", 0)),
                economics_tracked_cost_basis_yen=round(
                    float(value.get("economics_tracked_cost_basis_yen", 0.0)),
                    2,
                ),
            )

        orders = payload.get("orders", {})
        if not isinstance(orders, dict):
            raise ValueError("ordersはJSONオブジェクトにしてください")
        self._orders = {}
        for client_order_id, value in orders.items():
            if not isinstance(value, dict):
                raise ValueError("order recordはJSONオブジェクトにしてください")
            record = dict(value)
            record.setdefault("client_order_id", client_order_id)
            record.setdefault("rss_order_id", 0)
            record.setdefault("rss_order_number", "")
            record.setdefault("broker_observation_state", str(record.get("status", OrderStatus.PENDING.value)))
            record.setdefault("cancel_observation_state", "")
            record.setdefault("last_authoritative_rss_status", -1)
            self._orders[str(client_order_id)] = record

        fill_events = payload.get("fill_events", [])
        if not isinstance(fill_events, list):
            raise ValueError("fill_eventsはJSON配列にしてください")
        self._fill_events = [dict(event) for event in fill_events if isinstance(event, dict)]
        self._loaded_state_version = self.STATE_VERSION


def read_persisted_nonterminal_order_count(state_file: Path) -> int | None:
    if not state_file.is_file():
        return None

    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    version = payload.get("state_version")
    if type(version) is not int or version != RakutenRssBroker.STATE_VERSION:
        return None

    orders = payload.get("orders")
    if not isinstance(orders, dict):
        return None

    nonterminal_count = 0
    for record in orders.values():
        if not isinstance(record, dict):
            return None
        status = record.get("status")
        if not isinstance(status, str):
            return None
        try:
            order_status = OrderStatus(status)
        except ValueError:
            return None
        if order_status in PENDING_STATUSES:
            nonterminal_count += 1
    return nonterminal_count


try:
    from .protective_orders import (
        INVALID_RSS_ORDER_STATUSES,
        VALID_RSS_ORDER_STATUS,
        ProtectiveOrderLedger,
    )
except Exception:  # pragma: no cover
    ProtectiveOrderLedger = None  # type: ignore[assignment]
    VALID_RSS_ORDER_STATUS = "有効"  # type: ignore[assignment]
    INVALID_RSS_ORDER_STATUSES = {  # type: ignore[assignment]
        "無効",
        "該当なし",
        "不一致",
        "INVALID",
        "REJECTED",
        "CANCELED",
        "TIMED_OUT",
        "NOT_VALID",
        "NO_MATCH",
        "NOT_FOUND",
        "MISMATCH",
    }


def _phoenix_protective_ledger(self):
    ledger = getattr(self, "_phoenix_protective_ledger", None)
    if ledger is None and ProtectiveOrderLedger is not None:
        ledger = ProtectiveOrderLedger()
        setattr(self, "_phoenix_protective_ledger", ledger)
    return ledger


def _phoenix_value(source, *names, default=None):
    if source is None:
        return default
    if isinstance(source, dict):
        for name in names:
            value = source.get(name)
            if value is not None:
                return value
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return value
    return default


def _phoenix_metadata_value(source, *names, default=None):
    metadata = _phoenix_value(source, "metadata")
    if isinstance(metadata, Mapping):
        for name in names:
            value = metadata.get(name)
            if value is not None and str(value).strip():
                return value
    return default


def _phoenix_order_expiration(order):
    return _phoenix_metadata_value(order, "expiration", "expires_at", default=_phoenix_value(order, "expiration", "expires_at"))


def _phoenix_side_name(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.upper()
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name.upper()
    text = str(value).upper()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _phoenix_is_success(result):
    if result is None:
        return False
    candidates = []
    if isinstance(result, dict):
        candidates.extend(
            [
                result.get("status"),
                result.get("state"),
                result.get("result"),
                result.get("order_state"),
                result.get("acceptance_state"),
            ]
        )
    else:
        candidates.extend(
            [
                getattr(result, "status", None),
                getattr(result, "state", None),
                getattr(result, "result", None),
                getattr(result, "order_state", None),
                getattr(result, "acceptance_state", None),
            ]
        )
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, bool):
            if candidate:
                return True
            continue
        text = str(candidate).upper()
        if any(token in text for token in ("FILLED", "ACCEPTED", "SUCCESS", "SUCCEEDED", "DONE", "EXECUTED", "COMPLETED", "CONFIRMED")):
            return True
    return bool(result)


def _phoenix_order_id(result):
    return _phoenix_value(result, "broker_order_id", "order_id", "id", "acceptance_id", "request_id", "orderId")


def _phoenix_ticker(order):
    return _phoenix_value(order, "ticker", "symbol", "code", "stock_code", "security_code")


def _phoenix_quantity(order):
    value = _phoenix_value(order, "quantity", "qty", "shares", "size", "volume")
    return int(value) if value is not None else None


def _phoenix_entry_price(order):
    return _phoenix_value(order, "entry_price", "reference_price", "limit_price", "price", "current_price")


def _phoenix_target_price(order):
    return _phoenix_value(order, "target_price", "take_profit_price", "利確価格", "目標価格")


def _phoenix_stop_price(order):
    return _phoenix_value(order, "stop_price", "stop_loss_price", "損切価格")


def _phoenix_has_protective_prices(order):
    entry_price = _phoenix_entry_price(order)
    target_price = _phoenix_target_price(order)
    stop_price = _phoenix_stop_price(order)
    return entry_price is not None and target_price is not None and stop_price is not None


def _phoenix_rss_order_status_text(source):
    return str(_phoenix_value(source, "rss_order_status", "message", default="")).strip()


def _phoenix_is_valid_rss_order_status(value):
    text = str(value or "").strip()
    if not text:
        return False
    return text in {VALID_RSS_ORDER_STATUS, "有効"} or text.upper() in {"VALID", "ACTIVE"}


def _phoenix_is_invalid_rss_order_status(value):
    text = str(value or "").strip()
    if not text:
        return False
    return text in INVALID_RSS_ORDER_STATUSES or text.upper() in INVALID_RSS_ORDER_STATUSES


def _phoenix_sync_protective_order_update(self, record, update):
    ledger = _phoenix_protective_ledger(self)
    if ledger is None:
        return False
    if _phoenix_side_name(_phoenix_value(record, "side")) != "SELL":
        return False
    ticker = _phoenix_ticker(record)
    if ticker is None:
        return False
    protective_record = ledger.records.get(ticker)
    if protective_record is None or protective_record.protective_order_state not in {"PROTECTING", "PROTECTED", "RECONCILING"}:
        return False
    expected_order_id = str(protective_record.protective_order_id or "").strip()
    record_order_id = str(_phoenix_order_id(record) or "").strip()
    if expected_order_id and record_order_id and expected_order_id != record_order_id:
        return False
    protective_order_id = record_order_id or expected_order_id or str(_phoenix_order_id(update) or "").strip()
    raw_status = _phoenix_rss_order_status_text(update)
    verified_at = _phoenix_value(update, "updated_at")
    if _phoenix_is_valid_rss_order_status(raw_status):
        ledger.register_protective_order_accepted(
            ticker,
            protective_order_id or expected_order_id or "",
            verified_at=verified_at,
            acceptance_state=VALID_RSS_ORDER_STATUS,
        )
        return True
    if _phoenix_is_invalid_rss_order_status(raw_status):
        ledger.confirm_rss_order_status(
            ticker,
            raw_status,
            protective_order_id=protective_order_id or expected_order_id or "",
            verified_at=verified_at,
        )
        return True
    status = _phoenix_value(update, "status")
    if status in {OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.TIMED_OUT}:
        ledger.register_protective_order_rejected(
            ticker,
            reason=f"protective_order_status_{status.value.lower()}",
            verified_at=verified_at,
        )
        return True
    return False


def _phoenix_timeout_protective_order(self, record, verified_at):
    ledger = _phoenix_protective_ledger(self)
    if ledger is None:
        return False
    if _phoenix_side_name(_phoenix_value(record, "side")) != "SELL":
        return False
    ticker = _phoenix_ticker(record)
    if ticker is None:
        return False
    protective_record = ledger.records.get(ticker)
    if protective_record is None or protective_record.protective_order_state not in {"PROTECTING", "PROTECTED", "RECONCILING"}:
        return False
    expected_order_id = str(protective_record.protective_order_id or "").strip()
    record_order_id = str(_phoenix_order_id(record) or "").strip()
    if expected_order_id and record_order_id and expected_order_id != record_order_id:
        return False
    ledger.register_protective_order_rejected(
        ticker,
        reason="protective_order_timed_out",
        verified_at=verified_at,
    )
    return True


def _phoenix_refresh_transport(self):
    ledger = _phoenix_protective_ledger(self)
    if ledger is None:
        return None
    try:
        healthy = bool(_phoenix_original_health_check(self))
    except Exception:
        ledger.mark_transport_disconnected()
        raise
    if healthy:
        if not ledger.transport_connected:
            ledger.mark_transport_reconnected()
        else:
            ledger.transport_connected = True
    else:
        ledger.mark_transport_disconnected()
    return healthy


def _phoenix_submit_order(self, order, *args, **kwargs):
    ledger = _phoenix_protective_ledger(self)
    side_name = _phoenix_side_name(_phoenix_value(order, "side", "order_side", "trade_side"))
    if side_name == "BUY":
        healthy = _phoenix_refresh_transport(self)
        if ledger is not None and not ledger.can_submit_new_buy():
            raise RuntimeError("AUTO_LIVE_PROTECTION_BLOCKED")
        if not bool(healthy):
            raise RuntimeError("AUTO_LIVE_PROTECTION_BLOCKED")
    result = _phoenix_original_submit_order(self, order, *args, **kwargs)
    ledger = _phoenix_protective_ledger(self)
    if ledger is None:
        return result

    ticker = _phoenix_ticker(order)
    if ticker is None:
        return result

    if side_name == "BUY" and _phoenix_is_success(result):
        if _phoenix_has_protective_prices(order):
            quantity = _phoenix_quantity(order)
            entry_price = _phoenix_entry_price(order)
            target_price = _phoenix_target_price(order)
            stop_price = _phoenix_stop_price(order)
        else:
            quantity = None
            entry_price = None
            target_price = None
            stop_price = None
        if quantity is not None and entry_price is not None and target_price is not None and stop_price is not None:
            ledger.register_buy_fill(
                ticker,
                quantity,
                float(entry_price),
                float(target_price),
                float(stop_price),
                buy_order_id=_phoenix_order_id(result) or _phoenix_order_id(order),
            )
    elif side_name == "SELL":
        record = ledger.records.get(ticker)
        if record is not None and record.protective_order_state in {"PROTECTING", "RECONCILING"}:
            if _phoenix_is_success(result):
                ledger.register_protective_order_submitted(
                    ticker,
                    str(_phoenix_order_id(result) or _phoenix_order_id(order) or record.protective_order_id or ""),
                    verified_at=getattr(result, "created_at", None),
                    protective_order_expiration=_phoenix_order_expiration(order),
                )
            else:
                ledger.register_protective_order_rejected(
                    ticker,
                    reason="protective_order_rejected",
                )
    return result


if "RakutenRssBroker" in globals():
    _phoenix_original_health_check = RakutenRssBroker.health_check
    _phoenix_original_submit_order = RakutenRssBroker.submit_order
    RakutenRssBroker.can_submit_new_buy = lambda self: _phoenix_protective_ledger(self).can_submit_new_buy() if _phoenix_protective_ledger(self) is not None else True
    RakutenRssBroker.mark_transport_disconnected = lambda self: _phoenix_protective_ledger(self).mark_transport_disconnected() if _phoenix_protective_ledger(self) is not None else None
    RakutenRssBroker.mark_transport_reconnected = lambda self: _phoenix_protective_ledger(self).mark_transport_reconnected() if _phoenix_protective_ledger(self) is not None else None
    RakutenRssBroker.begin_reconcile = lambda self, ticker: _phoenix_protective_ledger(self).begin_reconcile(ticker) if _phoenix_protective_ledger(self) is not None else None
    RakutenRssBroker.reconcile_protective_position = lambda self, ticker, **kwargs: _phoenix_protective_ledger(self).reconcile(ticker, **kwargs) if _phoenix_protective_ledger(self) is not None else None
    RakutenRssBroker.health_check = _phoenix_original_health_check
    RakutenRssBroker.submit_order = _phoenix_submit_order
    RakutenRssBroker.__phoenix_protective_hooks_installed__ = True
