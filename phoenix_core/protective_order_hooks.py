from __future__ import annotations

from typing import Mapping

from .protective_orders import ProtectiveOrderLedger, ProtectiveOrderRecord


def _value(source, *names, default=None):
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


def _side_name(value):
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


def _is_success(result):
    if result is None:
        return False
    if isinstance(result, dict):
        candidates = [result.get("status"), result.get("state"), result.get("result"), result.get("order_state"), result.get("acceptance_state")]
    else:
        candidates = [getattr(result, "status", None), getattr(result, "state", None), getattr(result, "result", None), getattr(result, "order_state", None), getattr(result, "acceptance_state", None)]
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


def _metadata_value(source, *names, default=None):
    metadata = _value(source, "metadata")
    if isinstance(metadata, Mapping):
        for name in names:
            value = metadata.get(name)
            if value is not None and str(value).strip():
                return value
    return default


def _order_expiration(order):
    return _metadata_value(order, "expiration", "expires_at", default=_value(order, "expiration", "expires_at"))


def _order_id(result):
    return _value(result, "order_id", "id", "acceptance_id", "request_id", "orderId")


def _ticker(order):
    return _value(order, "ticker", "symbol", "code", "stock_code", "security_code")


def _quantity(order):
    value = _value(order, "quantity", "qty", "shares", "size", "volume")
    return int(value) if value is not None else None


def _entry_price(order):
    return _value(order, "entry_price", "reference_price", "limit_price", "price", "current_price")


def _target_price(order):
    return _value(order, "target_price", "take_profit_price", "利確価格", "目標価格")


def _stop_price(order):
    return _value(order, "stop_price", "stop_loss_price", "損切価格")


def _has_protective_prices(order):
    return _entry_price(order) is not None and _target_price(order) is not None and _stop_price(order) is not None


def install() -> None:
    from .rakuten_rss_broker import RakutenRssBroker

    if getattr(RakutenRssBroker, "__phoenix_protective_hooks_installed__", False):
        return

    original_health_check = RakutenRssBroker.health_check
    original_submit_order = RakutenRssBroker.submit_order

    def _ledger(self):
        ledger = getattr(self, "_phoenix_protective_ledger", None)
        if ledger is None:
            ledger = ProtectiveOrderLedger()
            setattr(self, "_phoenix_protective_ledger", ledger)
        return ledger

    def can_submit_new_buy(self):
        return _ledger(self).can_submit_new_buy()

    def mark_transport_disconnected(self):
        return _ledger(self).mark_transport_disconnected()

    def mark_transport_reconnected(self):
        return _ledger(self).mark_transport_reconnected()

    def begin_reconcile(self, ticker):
        return _ledger(self).begin_reconcile(ticker)

    def reconcile_protective_position(self, ticker, **kwargs):
        return _ledger(self).reconcile(ticker, **kwargs)

    def health_check(self, *args, **kwargs):
        ledger = _ledger(self)
        try:
            result = original_health_check(self, *args, **kwargs)
        except Exception:
            ledger.mark_transport_disconnected()
            raise
        if result.healthy:
            if not ledger.transport_connected:
                ledger.mark_transport_reconnected()
            else:
                ledger.transport_connected = True
        else:
            ledger.mark_transport_disconnected()
        return result

    def submit_order(self, order, *args, **kwargs):
        ledger = _ledger(self)
        side_name = _side_name(_value(order, "side", "order_side", "trade_side"))
        if side_name == "BUY":
            health = health_check(self)
            if not ledger.can_submit_new_buy() or not health.healthy:
                raise RuntimeError("AUTO_LIVE_PROTECTION_BLOCKED")
        result = original_submit_order(self, order, *args, **kwargs)

        ticker = _ticker(order)
        if ticker is None:
            return result

        if side_name == "BUY" and _is_success(result):
            if not _has_protective_prices(order):
                ledger.records[ticker] = ledger.records.get(
                    ticker,
                    ProtectiveOrderRecord(
                        ticker=ticker,
                        quantity=_quantity(order) or 0,
                        entry_price=float(_entry_price(order) or 0.0),
                        target_price=0.0,
                        stop_price=0.0,
                        protective_order_state="CRITICAL",
                        last_error="protective_prices_missing",
                    ),
                )
                raise RuntimeError("AUTO_LIVE_PROTECTION_BLOCKED")
            quantity = _quantity(order)
            entry_price = _entry_price(order)
            target_price = _target_price(order)
            stop_price = _stop_price(order)
            if quantity is not None and entry_price is not None and target_price is not None and stop_price is not None:
                ledger.register_buy_fill(
                    ticker,
                    quantity,
                    float(entry_price),
                    float(target_price),
                    float(stop_price),
                    buy_order_id=_order_id(result) or _order_id(order),
                )
        elif side_name == "SELL":
            record = ledger.records.get(ticker)
            if record is not None and record.protective_order_state in {"PROTECTING", "RECONCILING"}:
                if _is_success(result):
                    ledger.register_protective_order_submitted(
                        ticker,
                        str(_order_id(result) or _order_id(order) or record.protective_order_id or ""),
                        verified_at=getattr(result, "created_at", None),
                        protective_order_expiration=_order_expiration(order),
                    )
                else:
                    ledger.register_protective_order_rejected(ticker, reason="protective_order_rejected")
        return result

    RakutenRssBroker.can_submit_new_buy = can_submit_new_buy
    RakutenRssBroker.mark_transport_disconnected = mark_transport_disconnected
    RakutenRssBroker.mark_transport_reconnected = mark_transport_reconnected
    RakutenRssBroker.begin_reconcile = begin_reconcile
    RakutenRssBroker.reconcile_protective_position = reconcile_protective_position
    RakutenRssBroker.health_check = health_check
    RakutenRssBroker.submit_order = submit_order
    RakutenRssBroker.__phoenix_protective_hooks_installed__ = True


install()
