from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Dict, Optional

UNPROTECTED = "UNPROTECTED"
PROTECTING = "PROTECTING"
PROTECTED = "PROTECTED"
CRITICAL = "CRITICAL"
RECONCILING = "RECONCILING"
VALID_RSS_ORDER_STATUS = "有効"
INVALID_RSS_ORDER_STATUSES = {
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

_ACTIVE_STATES = {PROTECTING, PROTECTED, CRITICAL, RECONCILING}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_timestamp(value: Optional[datetime]) -> datetime:
    return value if value is not None else _utcnow()


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_expiration_yyyymmdd(value: object) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.strftime("%Y%m%d")


def _price_matches(expected: float, actual: object) -> bool:
    try:
        return round(float(expected), 2) == round(float(actual), 2)
    except (TypeError, ValueError):
        return False


def _status_is_acceptable(value: object) -> bool:
    text = _normalize_text(value)
    if not text:
        return False
    upper = text.upper()
    return text not in INVALID_RSS_ORDER_STATUSES and upper not in INVALID_RSS_ORDER_STATUSES


def _require_price_relation(stop_price: float, entry_price: float, target_price: float) -> None:
    if not (stop_price > 0 and stop_price < entry_price < target_price):
        raise ValueError("invalid protective price relation")


def _normalize_rss_order_status(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    upper = text.upper()
    if text in {VALID_RSS_ORDER_STATUS, "有効"} or upper in {"VALID", "ACTIVE"}:
        return VALID_RSS_ORDER_STATUS
    if text in {"無効", "該当なし", "不一致"}:
        return text
    if upper in INVALID_RSS_ORDER_STATUSES:
        return "無効"
    return text


@dataclass(slots=True)
class ProtectiveOrderRecord:
    ticker: str
    quantity: int
    entry_price: float
    target_price: float
    stop_price: float
    protective_order_id: Optional[str] = None
    protective_order_expiration: Optional[str] = None
    protective_order_state: str = UNPROTECTED
    protected_at: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None
    regular_order_status: Optional[str] = None
    stop_order_status: Optional[str] = None
    buy_order_id: Optional[str] = None
    broker_position_id: Optional[str] = None
    protective_order_acceptance_state: Optional[str] = None
    transport_connected: bool = True
    reconcile_required: bool = False
    last_error: Optional[str] = None

    def active(self) -> bool:
        return self.protective_order_state in _ACTIVE_STATES

    def is_ready(self) -> bool:
        return self.protective_order_state == PROTECTED and self.protective_order_id is not None


@dataclass
class ProtectiveOrderLedger:
    records: Dict[str, ProtectiveOrderRecord] = field(default_factory=dict)
    transport_connected: bool = True
    reconcile_required: bool = False

    def _get(self, ticker: str) -> ProtectiveOrderRecord:
        try:
            return self.records[ticker]
        except KeyError as exc:
            raise KeyError(f"unknown protective record: {ticker}") from exc

    def register_buy_fill(
        self,
        ticker: str,
        quantity: int,
        entry_price: float,
        target_price: float,
        stop_price: float,
        *,
        buy_order_id: Optional[str] = None,
        verified_at: Optional[datetime] = None,
        broker_position_id: Optional[str] = None,
    ) -> ProtectiveOrderRecord:
        _require_price_relation(stop_price, entry_price, target_price)
        record = ProtectiveOrderRecord(
            ticker=ticker,
            quantity=quantity,
            entry_price=entry_price,
            target_price=target_price,
            stop_price=stop_price,
            buy_order_id=buy_order_id,
            broker_position_id=broker_position_id,
            protective_order_state=PROTECTING,
            last_verified_at=_coerce_timestamp(verified_at),
            transport_connected=self.transport_connected,
            reconcile_required=False,
        )
        self.records[ticker] = record
        return record

    def register_protective_order_submitted(
        self,
        ticker: str,
        protective_order_id: Optional[str] = None,
        *,
        verified_at: Optional[datetime] = None,
        protective_order_expiration: Optional[object] = None,
        regular_order_status: Optional[object] = None,
        stop_order_status: Optional[object] = None,
    ) -> ProtectiveOrderRecord:
        record = self._get(ticker)
        updated = replace(
            record,
            protective_order_id=protective_order_id or record.protective_order_id,
            protective_order_expiration=(
                _normalize_expiration_yyyymmdd(protective_order_expiration)
                if protective_order_expiration is not None
                else record.protective_order_expiration
            ),
            protective_order_state=PROTECTING,
            protective_order_acceptance_state="PENDING",
            regular_order_status=_normalize_text(regular_order_status) or None,
            stop_order_status=_normalize_text(stop_order_status) or None,
            last_verified_at=_coerce_timestamp(verified_at),
            transport_connected=self.transport_connected,
            reconcile_required=False,
            last_error=None,
        )
        self.records[ticker] = updated
        return updated

    def register_protective_order_accepted(
        self,
        ticker: str,
        protective_order_id: str,
        *,
        verified_at: Optional[datetime] = None,
        acceptance_state: str = VALID_RSS_ORDER_STATUS,
    ) -> ProtectiveOrderRecord:
        record = self._get(ticker)
        updated = replace(
            record,
            protective_order_id=protective_order_id,
            protective_order_state=PROTECTED,
            protected_at=_coerce_timestamp(verified_at),
            last_verified_at=_coerce_timestamp(verified_at),
            protective_order_acceptance_state=acceptance_state,
            transport_connected=True,
            reconcile_required=False,
            last_error=None,
        )
        self.records[ticker] = updated
        self.reconcile_required = any(item.protective_order_state == RECONCILING for item in self.records.values())
        return updated

    def confirm_rss_order_status(
        self,
        ticker: str,
        rss_order_status: object,
        *,
        protective_order_id: Optional[str] = None,
        verified_at: Optional[datetime] = None,
    ) -> ProtectiveOrderRecord:
        normalized_status = _normalize_rss_order_status(rss_order_status)
        if normalized_status == VALID_RSS_ORDER_STATUS:
            return self.register_protective_order_accepted(
                ticker,
                protective_order_id or self._get(ticker).protective_order_id or "",
                verified_at=verified_at,
                acceptance_state=normalized_status,
            )
        reason = normalized_status or "rss_order_status_missing"
        return self.register_protective_order_rejected(
            ticker,
            reason=f"protective_order_status_{reason}",
            verified_at=verified_at,
        )

    def register_protective_order_rejected(
        self,
        ticker: str,
        *,
        reason: Optional[str] = None,
        verified_at: Optional[datetime] = None,
    ) -> ProtectiveOrderRecord:
        record = self._get(ticker)
        updated = replace(
            record,
            protective_order_state=CRITICAL,
            last_verified_at=_coerce_timestamp(verified_at),
            last_error=reason or "protective_order_rejected",
            reconcile_required=False,
        )
        self.records[ticker] = updated
        self.reconcile_required = True
        return updated

    def mark_transport_disconnected(self, *, verified_at: Optional[datetime] = None) -> None:
        self.transport_connected = False
        for ticker, record in list(self.records.items()):
            if record.protective_order_state == PROTECTING:
                self.records[ticker] = replace(
                    record,
                    protective_order_state=CRITICAL,
                    transport_connected=False,
                    reconcile_required=False,
                    last_verified_at=_coerce_timestamp(verified_at),
                    last_error="transport_disconnected_before_protective_order",
                )
            elif record.protective_order_state == RECONCILING:
                self.records[ticker] = replace(
                    record,
                    protective_order_state=CRITICAL,
                    transport_connected=False,
                    reconcile_required=False,
                    last_verified_at=_coerce_timestamp(verified_at),
                    last_error="transport_disconnected_during_reconcile",
                )
            else:
                self.records[ticker] = replace(
                    record,
                    transport_connected=False,
                    last_verified_at=_coerce_timestamp(verified_at),
                )
        self.reconcile_required = any(item.protective_order_state == RECONCILING for item in self.records.values())

    def mark_transport_reconnected(self, *, verified_at: Optional[datetime] = None) -> None:
        self.transport_connected = True
        for ticker, record in list(self.records.items()):
            if record.protective_order_state == PROTECTED:
                self.records[ticker] = replace(
                    record,
                    protective_order_state=RECONCILING,
                    transport_connected=True,
                    reconcile_required=True,
                    last_verified_at=_coerce_timestamp(verified_at),
                )
            else:
                self.records[ticker] = replace(
                    record,
                    transport_connected=True,
                    last_verified_at=_coerce_timestamp(verified_at),
                )
        self.reconcile_required = any(item.protective_order_state == RECONCILING for item in self.records.values())

    def begin_reconcile(self, ticker: str, *, verified_at: Optional[datetime] = None) -> ProtectiveOrderRecord:
        record = self._get(ticker)
        updated = replace(
            record,
            protective_order_state=RECONCILING,
            reconcile_required=True,
            transport_connected=True,
            last_verified_at=_coerce_timestamp(verified_at),
        )
        self.records[ticker] = updated
        self.reconcile_required = True
        return updated

    def reconcile(
        self,
        ticker: str,
        *,
        position_matches: bool,
        open_order_matches: bool,
        protective_order_matches: bool,
        verified_at: Optional[datetime] = None,
        protective_order_id: Optional[str] = None,
        order_number: Optional[str] = None,
        reported_ticker: Optional[str] = None,
        quantity: Optional[int] = None,
        target_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        expiration: Optional[object] = None,
        regular_order_status: Optional[object] = None,
        stop_order_status: Optional[object] = None,
    ) -> ProtectiveOrderRecord:
        record = self._get(ticker)
        mismatches: list[str] = []
        if not (position_matches and open_order_matches and protective_order_matches):
            mismatches.append("reconcile_mismatch")

        if reported_ticker is not None and _normalize_text(reported_ticker).upper() != _normalize_text(ticker).upper():
            mismatches.append("ticker_mismatch")

        expected_order_number = _normalize_text(order_number or protective_order_id or record.protective_order_id)
        if order_number is not None or protective_order_id is not None:
            if not expected_order_number:
                mismatches.append("order_number_missing")
            elif record.protective_order_id and record.protective_order_id != expected_order_number:
                mismatches.append("order_number_mismatch")

        if quantity is not None and int(quantity) != record.quantity:
            mismatches.append("quantity_mismatch")

        if target_price is not None and not _price_matches(record.target_price, target_price):
            mismatches.append("target_price_mismatch")

        if stop_price is not None and not _price_matches(record.stop_price, stop_price):
            mismatches.append("stop_price_mismatch")

        stored_expiration = _normalize_expiration_yyyymmdd(record.protective_order_expiration)
        live_expiration = _normalize_expiration_yyyymmdd(expiration) if expiration is not None else ""
        effective_expiration = live_expiration or stored_expiration
        if stored_expiration or live_expiration:
            if not stored_expiration:
                mismatches.append("expiration_missing_in_record")
            elif not live_expiration:
                mismatches.append("expiration_missing")
            elif stored_expiration != live_expiration:
                mismatches.append("expiration_mismatch")
            else:
                verified_moment = _coerce_timestamp(verified_at)
                try:
                    if verified_moment.date() > datetime.strptime(effective_expiration, "%Y%m%d").date():
                        mismatches.append("expiration_expired")
                except ValueError:
                    mismatches.append("expiration_invalid")

        normalized_regular_status = _normalize_text(regular_order_status)
        if regular_order_status is not None:
            if not _status_is_acceptable(normalized_regular_status):
                mismatches.append("regular_order_status_invalid")

        normalized_stop_status = _normalize_text(stop_order_status)
        if stop_order_status is not None:
            if not _status_is_acceptable(normalized_stop_status):
                mismatches.append("stop_order_status_invalid")

        if not mismatches:
            updated = replace(
                record,
                protective_order_state=PROTECTED,
                protective_order_id=expected_order_number or record.protective_order_id,
                protective_order_expiration=effective_expiration or record.protective_order_expiration,
                protected_at=record.protected_at or _coerce_timestamp(verified_at),
                last_verified_at=_coerce_timestamp(verified_at),
                transport_connected=True,
                reconcile_required=False,
                regular_order_status=normalized_regular_status or record.regular_order_status,
                stop_order_status=normalized_stop_status or record.stop_order_status,
                last_error=None,
            )
        else:
            updated = replace(
                record,
                protective_order_state=CRITICAL,
                last_verified_at=_coerce_timestamp(verified_at),
                reconcile_required=False,
                last_error="reconcile_mismatch:" + ",".join(mismatches),
            )
        self.records[ticker] = updated
        self.reconcile_required = any(item.protective_order_state == RECONCILING for item in self.records.values())
        return updated

    def system_state(self) -> str:
        states = {record.protective_order_state for record in self.records.values()}
        if CRITICAL in states:
            return CRITICAL
        if PROTECTING in states:
            return PROTECTING
        if RECONCILING in states or self.reconcile_required:
            return RECONCILING
        if PROTECTED in states:
            return PROTECTED
        return UNPROTECTED

    def can_submit_new_buy(self) -> bool:
        if not self.transport_connected or self.reconcile_required:
            return False
        return all(record.protective_order_state == PROTECTED for record in self.records.values())

    def snapshot(self, ticker: str) -> ProtectiveOrderRecord:
        return self._get(ticker)
