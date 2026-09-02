from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import math
from numbers import Real
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from phoenix_core.models import (
    AccountSnapshot,
    BrokerHealth,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
)


JST = ZoneInfo("Asia/Tokyo")


def _now_jst() -> datetime:
    return datetime.now(JST)


class BrokerAdapter(ABC):
    @property
    @abstractmethod
    def broker_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> BrokerHealth:
        raise NotImplementedError

    @abstractmethod
    def get_account_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError

    @abstractmethod
    def submit_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    def refresh_pending_orders(self) -> list[OrderResult]:
        raise NotImplementedError

    def nonterminal_order_count(self) -> int:
        raise NotImplementedError


@dataclass(slots=True)
class _MutablePosition:
    quantity: int
    average_price: float
    market_price: float
    economics_tracked_quantity: int = 0
    economics_tracked_cost_basis_yen: float = 0.0


class PaperBroker(BrokerAdapter):
    """
    永続化対応Paper Broker。

    state_fileを指定すると、現金・保有株・確定損益・処理済み注文IDを
    JSONへ保存し、次回実行時に復元する。
    """

    STATE_VERSION = 2
    FILL_EVENT_VERSION = 1

    def __init__(
        self,
        initial_cash_yen: float = 300_000.0,
        commission_rate: float = 0.0,
        state_file: Path | None = None,
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

        self._initial_cash_yen = round(float(initial_cash_yen), 2)
        self._cash_yen = self._initial_cash_yen
        self._commission_rate = float(commission_rate)
        self._state_file = state_file
        self._positions: dict[str, _MutablePosition] = {}
        self._realized_pnl_yen = 0.0
        self._processed_client_order_ids: set[str] = set()
        self._fill_events: list[dict[str, Any]] = []
        self._economics_baseline = self._new_economics_baseline()
        self._loaded_state_version: int | None = None
        self._lock = RLock()

        self._load_state()

    @property
    def broker_name(self) -> str:
        return "PAPER"

    def health_check(self) -> BrokerHealth:
        try:
            if self._state_file is not None:
                self._state_file.parent.mkdir(parents=True, exist_ok=True)
            return BrokerHealth(
                broker_name=self.broker_name,
                healthy=True,
                live_trading_enabled=False,
                message="Paper Broker正常。実売買は無効です。",
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
        """Step19基準を、注文を発生させずにv2状態へ確立する。"""
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
            self._processed_client_order_ids.clear()
            self._fill_events.clear()
            self._economics_baseline = self._new_economics_baseline()
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
            if order.client_order_id in self._processed_client_order_ids:
                return self._rejected_result(
                    order,
                    ticker,
                    "同じclient_order_idの注文は既に処理済みです",
                )

            if order.side is OrderSide.BUY:
                result = self._buy(order, ticker)
            elif order.side is OrderSide.SELL:
                result = self._sell(order, ticker)
            else:
                result = self._rejected_result(
                    order,
                    ticker,
                    "未対応の売買区分です",
                )

            if result.status is OrderStatus.FILLED:
                self._processed_client_order_ids.add(order.client_order_id)
                self._fill_events.append(self._fill_event(result))
                self._save_state()

            return result

    def refresh_pending_orders(self) -> list[OrderResult]:
        return []

    def nonterminal_order_count(self) -> int:
        return 0

    def _buy(self, order: OrderRequest, ticker: str) -> OrderResult:
        gross = round(order.quantity * order.limit_price, 2)
        commission = round(gross * self._commission_rate, 2)
        total_cost = round(gross + commission, 2)

        if total_cost > self._cash_yen:
            return self._rejected_result(
                order,
                ticker,
                (
                    f"買付余力不足: 必要額 {total_cost:,.2f}円 / "
                    f"現金 {self._cash_yen:,.2f}円"
                ),
            )

        current = self._positions.get(ticker)
        if (
            current is not None
            and current.economics_tracked_quantity < current.quantity
        ):
            return self._rejected_result(
                order,
                ticker,
                "Step19基準前の保有銘柄への買い増しは禁止されています",
            )
        if current is None:
            new_quantity = order.quantity
            new_average = order.limit_price
        else:
            old_cost = current.quantity * current.average_price
            new_quantity = current.quantity + order.quantity
            new_average = (
                old_cost + order.quantity * order.limit_price
            ) / new_quantity

        self._positions[ticker] = _MutablePosition(
            quantity=new_quantity,
            average_price=round(new_average, 4),
            market_price=round(order.limit_price, 2),
            economics_tracked_quantity=(
                order.quantity
                if current is None
                else current.economics_tracked_quantity + order.quantity
            ),
            economics_tracked_cost_basis_yen=round(
                gross
                + (
                    0.0
                    if current is None
                    else current.economics_tracked_cost_basis_yen
                ),
                2,
            ),
        )
        self._cash_yen = round(self._cash_yen - total_cost, 2)

        return self._filled_result(
            order,
            ticker,
            (
                f"仮想買付完了: {ticker} {order.quantity}株 "
                f"{order.limit_price:,.2f}円"
            ),
            commission_yen=commission,
            cash_delta_yen=-total_cost,
            economics_eligible_quantity=order.quantity,
            economics_eligible_commission_yen=commission,
        )

    def _sell(self, order: OrderRequest, ticker: str) -> OrderResult:
        current = self._positions.get(ticker)
        if current is None or current.quantity < order.quantity:
            held = 0 if current is None else current.quantity
            return self._rejected_result(
                order,
                ticker,
                (
                    f"保有株数不足: 売却 {order.quantity}株 / "
                    f"保有 {held}株"
                ),
            )

        gross = round(order.quantity * order.limit_price, 2)
        commission = round(gross * self._commission_rate, 2)
        proceeds = round(gross - commission, 2)
        acquisition_cost = round(
            order.quantity * current.average_price,
            2,
        )
        realized_before_commission = round(gross - acquisition_cost, 2)
        realized_pnl = round(realized_before_commission - commission, 2)

        legacy_quantity = max(
            0,
            current.quantity - current.economics_tracked_quantity,
        )
        eligible_quantity = min(
            current.economics_tracked_quantity,
            max(0, order.quantity - legacy_quantity),
        )
        if eligible_quantity > 0:
            tracked_average = (
                current.economics_tracked_cost_basis_yen
                / current.economics_tracked_quantity
            )
            eligible_cost_basis = round(
                tracked_average * eligible_quantity,
                2,
            )
            eligible_realized_before_commission = round(
                eligible_quantity * order.limit_price
                - eligible_cost_basis,
                2,
            )
            eligible_commission = round(
                commission * eligible_quantity / order.quantity,
                2,
            )
            current.economics_tracked_quantity -= eligible_quantity
            if current.economics_tracked_quantity == 0:
                current.economics_tracked_cost_basis_yen = 0.0
            else:
                current.economics_tracked_cost_basis_yen = round(
                    current.economics_tracked_cost_basis_yen
                    - eligible_cost_basis,
                    2,
                )
        else:
            eligible_realized_before_commission = 0.0
            eligible_commission = 0.0

        current.quantity -= order.quantity
        current.market_price = round(order.limit_price, 2)
        self._cash_yen = round(self._cash_yen + proceeds, 2)
        self._realized_pnl_yen = round(
            self._realized_pnl_yen + realized_pnl,
            2,
        )

        if current.quantity == 0:
            del self._positions[ticker]

        return self._filled_result(
            order,
            ticker,
            (
                f"仮想売却完了: {ticker} {order.quantity}株 "
                f"{order.limit_price:,.2f}円 / "
                f"確定損益 {realized_pnl:+,.2f}円"
            ),
            commission_yen=commission,
            cash_delta_yen=proceeds,
            cost_basis_released_yen=acquisition_cost,
            realized_pnl_before_commission_yen=realized_before_commission,
            economics_eligible_quantity=eligible_quantity,
            economics_eligible_commission_yen=eligible_commission,
            economics_eligible_realized_pnl_before_commission_yen=(
                eligible_realized_before_commission
            ),
        )

    def _new_economics_baseline(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "established_at": _now_jst().isoformat(timespec="seconds"),
            "cash_yen": round(self._cash_yen, 2),
            "realized_pnl_yen": round(self._realized_pnl_yen, 2),
            "positions": {
                ticker: {
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                }
                for ticker, position in sorted(self._positions.items())
            },
            "processed_client_order_ids": sorted(
                self._processed_client_order_ids
            ),
        }

    @staticmethod
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

    def _fill_event(self, result: OrderResult) -> dict[str, Any]:
        event = {
            "schema_version": self.FILL_EVENT_VERSION,
            "event_id": f"FILL|{result.broker_order_id}",
            "broker_name": result.broker_name,
            "broker_order_id": result.broker_order_id,
            "client_order_id": result.client_order_id,
            "ticker": result.ticker,
            "side": result.side.value,
            "quantity": result.quantity,
            "requested_price": result.requested_price,
            "filled_quantity": result.filled_quantity,
            "filled_price": result.filled_price,
            "gross_amount_yen": result.gross_amount,
            "commission_yen": result.commission_yen,
            "commission_source": "BROKER_RESULT",
            "cash_delta_yen": result.cash_delta_yen,
            "cost_basis_released_yen": result.cost_basis_released_yen,
            "realized_pnl_before_commission_yen": (
                result.realized_pnl_before_commission_yen
            ),
            "economics_eligible_quantity": (
                result.economics_eligible_quantity
            ),
            "economics_eligible_commission_yen": (
                result.economics_eligible_commission_yen
            ),
            "economics_eligible_realized_pnl_before_commission_yen": (
                result.economics_eligible_realized_pnl_before_commission_yen
            ),
            "adverse_slippage_yen": result.adverse_slippage_yen,
            "created_at": result.created_at.isoformat(timespec="microseconds"),
        }
        event["event_sha256"] = self._canonical_event_sha256(event)
        return event

    def _state_payload(self) -> dict[str, Any]:
        return {
            "state_version": self.STATE_VERSION,
            "broker_name": self.broker_name,
            "account_type": "CASH",
            "live_trading_enabled": False,
            "margin_trading_enabled": False,
            "updated_at": _now_jst().isoformat(timespec="microseconds"),
            "initial_cash_yen": self._initial_cash_yen,
            "cash_yen": self._cash_yen,
            "commission_rate": self._commission_rate,
            "realized_pnl_yen": self._realized_pnl_yen,
            "positions": {
                ticker: {
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                    "market_price": position.market_price,
                    "economics_tracked_quantity": (
                        position.economics_tracked_quantity
                    ),
                    "economics_tracked_cost_basis_yen": (
                        position.economics_tracked_cost_basis_yen
                    ),
                }
                for ticker, position in sorted(self._positions.items())
            },
            "processed_client_order_ids": sorted(
                self._processed_client_order_ids
            ),
            "economics_baseline": self._economics_baseline,
            "fill_events": self._fill_events,
        }

    def _save_state(self) -> None:
        if self._state_file is None:
            return

        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._state_file.with_suffix(
            self._state_file.suffix + ".tmp"
        )
        temporary.write_text(
            json.dumps(
                self._state_payload(),
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(self._state_file)
        self._loaded_state_version = self.STATE_VERSION

    def _load_state(self) -> None:
        if self._state_file is None or not self._state_file.exists():
            return

        try:
            payload = json.loads(
                self._state_file.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Paper Broker状態ファイルを読み込めません: "
                f"{self._state_file}"
            ) from error

        if not isinstance(payload, dict):
            raise ValueError("Paper Broker状態のルートはJSONオブジェクトにしてください")

        version = payload.get("state_version")
        if type(version) is not int or version not in (1, self.STATE_VERSION):
            raise ValueError("未対応のPaper Broker状態バージョンです")

        if version == 1:
            self._load_v1_state(payload)
            self._fill_events = []
            self._economics_baseline = self._new_economics_baseline()
            self._loaded_state_version = 1
            return

        self._load_v2_state(payload)
        self._loaded_state_version = self.STATE_VERSION

    @staticmethod
    def _finite_number(
        value: Any,
        name: str,
        *,
        nonnegative: bool = False,
        positive: bool = False,
    ) -> float:
        if isinstance(value, bool):
            raise ValueError(f"{name}は有限数にしてください")
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name}は有限数にしてください") from error
        if not math.isfinite(number):
            raise ValueError(f"{name}は有限数にしてください")
        if nonnegative and number < 0:
            raise ValueError(f"{name}は0以上にしてください")
        if positive and number <= 0:
            raise ValueError(f"{name}は0より大きくしてください")
        return number

    @staticmethod
    def _required_integer(
        value: Any,
        name: str,
        *,
        minimum: int = 0,
    ) -> int:
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name}は{minimum}以上の整数にしてください")
        return value

    @staticmethod
    def _required_timestamp(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name}がありません")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{name}はISO日時にしてください") from error
        if parsed.utcoffset() != timedelta(hours=9):
            raise ValueError(f"{name}はJSTオフセット付き日時にしてください")
        return value

    @staticmethod
    def _required_id_list(value: Any, name: str) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"{name}はJSON配列にしてください")
        identifiers: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{name}に空のIDがあります")
            identifiers.append(item)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"{name}に重複IDがあります")
        return identifiers

    @staticmethod
    def _money_equal(left: float, right: float) -> bool:
        return abs(round(left, 2) - round(right, 2)) <= 0.011

    def _load_v1_state(self, payload: dict[str, Any]) -> None:
        self._cash_yen = round(
            self._finite_number(
                payload.get("cash_yen", self._initial_cash_yen),
                "cash_yen",
                nonnegative=True,
            ),
            2,
        )
        self._realized_pnl_yen = round(
            self._finite_number(
                payload.get("realized_pnl_yen", 0.0),
                "realized_pnl_yen",
            ),
            2,
        )
        processed = payload.get("processed_client_order_ids", [])
        self._processed_client_order_ids = set(
            self._required_id_list(processed, "processed_client_order_ids")
        )

        positions = payload.get("positions", {})
        if not isinstance(positions, dict):
            raise ValueError("positionsはJSONオブジェクトにしてください")

        self._positions = {}
        for ticker, value in positions.items():
            if not isinstance(value, dict):
                raise ValueError("v1 positionはJSONオブジェクトにしてください")
            required = {"quantity", "average_price", "market_price"}
            missing = sorted(required.difference(value))
            if missing:
                raise ValueError(
                    f"v1 positionに必須項目がありません: {missing}"
                )
            quantity = self._required_integer(
                value["quantity"],
                "v1 position.quantity",
                minimum=1,
            )
            normalized_ticker = str(ticker).strip().upper()
            if not normalized_ticker:
                raise ValueError("position tickerが空です")
            if normalized_ticker in self._positions:
                raise ValueError("v1 positionsに重複tickerがあります")
            self._positions[normalized_ticker] = _MutablePosition(
                quantity=quantity,
                average_price=round(
                    self._finite_number(
                        value["average_price"],
                        f"positions.{normalized_ticker}.average_price",
                        positive=True,
                    ),
                    4,
                ),
                market_price=round(
                    self._finite_number(
                        value["market_price"],
                        f"positions.{normalized_ticker}.market_price",
                        positive=True,
                    ),
                    2,
                ),
                economics_tracked_quantity=0,
                economics_tracked_cost_basis_yen=0.0,
            )

    def _load_v2_state(self, payload: dict[str, Any]) -> None:
        required = {
            "broker_name",
            "account_type",
            "live_trading_enabled",
            "margin_trading_enabled",
            "updated_at",
            "initial_cash_yen",
            "cash_yen",
            "commission_rate",
            "realized_pnl_yen",
            "positions",
            "processed_client_order_ids",
            "economics_baseline",
            "fill_events",
        }
        missing = sorted(required.difference(payload))
        if missing:
            raise ValueError(f"Paper Broker v2状態に必須項目がありません: {missing}")
        if payload["broker_name"] != self.broker_name:
            raise ValueError("broker_nameがPAPERではありません")
        if payload["account_type"] != "CASH":
            raise ValueError("account_typeはCASHでなければなりません")
        if payload["live_trading_enabled"] is not False:
            raise ValueError("live_trading_enabledはfalseでなければなりません")
        if payload["margin_trading_enabled"] is not False:
            raise ValueError("margin_trading_enabledはfalseでなければなりません")
        self._required_timestamp(payload["updated_at"], "updated_at")
        self._finite_number(
            payload["initial_cash_yen"],
            "initial_cash_yen",
            nonnegative=True,
        )
        self._finite_number(
            payload["commission_rate"],
            "commission_rate",
            nonnegative=True,
        )
        self._cash_yen = round(
            self._finite_number(
                payload["cash_yen"],
                "cash_yen",
                nonnegative=True,
            ),
            2,
        )
        self._realized_pnl_yen = round(
            self._finite_number(
                payload["realized_pnl_yen"],
                "realized_pnl_yen",
            ),
            2,
        )
        processed_ids = self._required_id_list(
            payload["processed_client_order_ids"],
            "processed_client_order_ids",
        )
        self._processed_client_order_ids = set(processed_ids)
        self._economics_baseline = self._validate_baseline(
            payload["economics_baseline"]
        )
        self._positions = self._validate_v2_positions(payload["positions"])
        self._fill_events = self._validate_fill_events(payload["fill_events"])
        self._validate_temporal_lineage(payload)
        self._validate_v2_reconciliation()

    def _validate_temporal_lineage(self, payload: dict[str, Any]) -> None:
        baseline_at = datetime.fromisoformat(
            self._economics_baseline["established_at"]
        )
        updated_at = datetime.fromisoformat(payload["updated_at"])
        previous_at = baseline_at
        for event in self._fill_events:
            event_at = datetime.fromisoformat(event["created_at"])
            if event_at < baseline_at:
                raise ValueError("fill eventがStep19 baselineより前です")
            if event_at < previous_at:
                raise ValueError("fill eventの時系列が逆転しています")
            if event_at > updated_at:
                raise ValueError("fill eventがbroker updated_atより未来です")
            previous_at = event_at

    def _validate_baseline(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("economics_baselineはJSONオブジェクトにしてください")
        required = {
            "schema_version",
            "established_at",
            "cash_yen",
            "realized_pnl_yen",
            "positions",
            "processed_client_order_ids",
        }
        missing = sorted(required.difference(value))
        if missing:
            raise ValueError(f"economics_baselineに必須項目がありません: {missing}")
        if value["schema_version"] != 1:
            raise ValueError("economics_baseline.schema_versionが不正です")
        self._required_timestamp(
            value["established_at"],
            "economics_baseline.established_at",
        )
        self._finite_number(
            value["cash_yen"],
            "economics_baseline.cash_yen",
            nonnegative=True,
        )
        self._finite_number(
            value["realized_pnl_yen"],
            "economics_baseline.realized_pnl_yen",
        )
        baseline_ids = self._required_id_list(
            value["processed_client_order_ids"],
            "economics_baseline.processed_client_order_ids",
        )
        positions = value["positions"]
        if not isinstance(positions, dict):
            raise ValueError("economics_baseline.positionsはJSONオブジェクトにしてください")
        normalized_positions: dict[str, dict[str, Any]] = {}
        for ticker, item in positions.items():
            normalized_ticker = str(ticker).strip().upper()
            if not normalized_ticker or not isinstance(item, dict):
                raise ValueError("economics_baseline.positionsが不正です")
            if "quantity" not in item or "average_price" not in item:
                raise ValueError("economics_baseline positionに必須項目がありません")
            quantity = self._required_integer(
                item["quantity"],
                f"economics_baseline.positions.{normalized_ticker}.quantity",
                minimum=1,
            )
            average_price = round(
                self._finite_number(
                    item["average_price"],
                    f"economics_baseline.positions.{normalized_ticker}.average_price",
                    positive=True,
                ),
                4,
            )
            if normalized_ticker in normalized_positions:
                raise ValueError("economics_baseline.positionsに重複tickerがあります")
            normalized_positions[normalized_ticker] = {
                "quantity": quantity,
                "average_price": average_price,
            }
        return {
            "schema_version": 1,
            "established_at": value["established_at"],
            "cash_yen": round(float(value["cash_yen"]), 2),
            "realized_pnl_yen": round(float(value["realized_pnl_yen"]), 2),
            "positions": normalized_positions,
            "processed_client_order_ids": baseline_ids,
        }

    def _validate_v2_positions(
        self,
        value: Any,
    ) -> dict[str, _MutablePosition]:
        if not isinstance(value, dict):
            raise ValueError("positionsはJSONオブジェクトにしてください")
        positions: dict[str, _MutablePosition] = {}
        required = {
            "quantity",
            "average_price",
            "market_price",
            "economics_tracked_quantity",
            "economics_tracked_cost_basis_yen",
        }
        for ticker, item in value.items():
            normalized_ticker = str(ticker).strip().upper()
            if not normalized_ticker or not isinstance(item, dict):
                raise ValueError("positionsが不正です")
            missing = sorted(required.difference(item))
            if missing:
                raise ValueError(
                    f"positions.{normalized_ticker}に必須項目がありません: {missing}"
                )
            quantity = self._required_integer(
                item["quantity"],
                f"positions.{normalized_ticker}.quantity",
                minimum=1,
            )
            tracked_quantity = self._required_integer(
                item["economics_tracked_quantity"],
                f"positions.{normalized_ticker}.economics_tracked_quantity",
            )
            if tracked_quantity > quantity:
                raise ValueError("economics_tracked_quantityが保有数量を超えています")
            tracked_cost = round(
                self._finite_number(
                    item["economics_tracked_cost_basis_yen"],
                    f"positions.{normalized_ticker}.economics_tracked_cost_basis_yen",
                    nonnegative=True,
                ),
                2,
            )
            if (tracked_quantity == 0) != (tracked_cost == 0.0):
                raise ValueError("tracked quantityとtracked cost basisが一致しません")
            if normalized_ticker in positions:
                raise ValueError("positionsに重複tickerがあります")
            positions[normalized_ticker] = _MutablePosition(
                quantity=quantity,
                average_price=round(
                    self._finite_number(
                        item["average_price"],
                        f"positions.{normalized_ticker}.average_price",
                        positive=True,
                    ),
                    4,
                ),
                market_price=round(
                    self._finite_number(
                        item["market_price"],
                        f"positions.{normalized_ticker}.market_price",
                        positive=True,
                    ),
                    2,
                ),
                economics_tracked_quantity=tracked_quantity,
                economics_tracked_cost_basis_yen=tracked_cost,
            )
        return positions

    def _validate_fill_events(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("fill_eventsはJSON配列にしてください")
        events: list[dict[str, Any]] = []
        event_ids: set[str] = set()
        broker_order_ids: set[str] = set()
        client_order_ids: set[str] = set()
        for index, event in enumerate(value):
            validated = self._validate_fill_event(event, index)
            for key, seen in (
                ("event_id", event_ids),
                ("broker_order_id", broker_order_ids),
                ("client_order_id", client_order_ids),
            ):
                identifier = validated[key]
                if identifier in seen:
                    raise ValueError(f"fill_eventsに重複{key}があります")
                seen.add(identifier)
            events.append(validated)
        return events

    def _validate_fill_event(
        self,
        value: Any,
        index: int,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"fill_events[{index}]はJSONオブジェクトにしてください")
        required = {
            "schema_version", "event_id", "event_sha256", "broker_name",
            "broker_order_id", "client_order_id", "ticker", "side",
            "quantity", "requested_price", "filled_quantity", "filled_price",
            "gross_amount_yen", "commission_yen", "commission_source",
            "cash_delta_yen", "cost_basis_released_yen",
            "realized_pnl_before_commission_yen",
            "economics_eligible_quantity", "economics_eligible_commission_yen",
            "economics_eligible_realized_pnl_before_commission_yen",
            "adverse_slippage_yen", "created_at",
        }
        missing = sorted(required.difference(value))
        if missing:
            raise ValueError(f"fill_events[{index}]に必須項目がありません: {missing}")
        if value["schema_version"] != self.FILL_EVENT_VERSION:
            raise ValueError("fill event schema_versionが不正です")
        for name in ("event_id", "broker_order_id", "client_order_id", "ticker"):
            if not isinstance(value[name], str) or not value[name].strip():
                raise ValueError(f"fill event {name}が空です")
        if value["event_id"] != f"FILL|{value['broker_order_id']}":
            raise ValueError("fill event event_idがbroker_order_idと一致しません")
        if value["broker_name"] != self.broker_name:
            raise ValueError("fill event broker_nameがPAPERではありません")
        if value["commission_source"] != "BROKER_RESULT":
            raise ValueError("fill event commission_sourceが不正です")
        if value["side"] not in (OrderSide.BUY.value, OrderSide.SELL.value):
            raise ValueError("fill event sideが不正です")
        quantity = self._required_integer(
            value["quantity"], "fill event quantity", minimum=1
        )
        filled_quantity = self._required_integer(
            value["filled_quantity"], "fill event filled_quantity", minimum=1
        )
        if filled_quantity != quantity:
            raise ValueError("Paper Broker fill eventは全数量約定でなければなりません")
        eligible_quantity = self._required_integer(
            value["economics_eligible_quantity"],
            "fill event economics_eligible_quantity",
        )
        if eligible_quantity > filled_quantity:
            raise ValueError("economics_eligible_quantityが約定数量を超えています")
        requested_price = self._finite_number(
            value["requested_price"], "fill event requested_price", positive=True
        )
        filled_price = self._finite_number(
            value["filled_price"], "fill event filled_price", positive=True
        )
        gross = self._finite_number(
            value["gross_amount_yen"],
            "fill event gross_amount_yen",
            nonnegative=True,
        )
        commission = self._finite_number(
            value["commission_yen"],
            "fill event commission_yen",
            nonnegative=True,
        )
        cash_delta = self._finite_number(
            value["cash_delta_yen"], "fill event cash_delta_yen"
        )
        cost_basis = self._finite_number(
            value["cost_basis_released_yen"],
            "fill event cost_basis_released_yen",
            nonnegative=True,
        )
        realized_before_commission = self._finite_number(
            value["realized_pnl_before_commission_yen"],
            "fill event realized_pnl_before_commission_yen",
        )
        eligible_commission = self._finite_number(
            value["economics_eligible_commission_yen"],
            "fill event economics_eligible_commission_yen",
            nonnegative=True,
        )
        eligible_realized = self._finite_number(
            value["economics_eligible_realized_pnl_before_commission_yen"],
            "fill event economics_eligible_realized_pnl_before_commission_yen",
        )
        adverse_slippage = self._finite_number(
            value["adverse_slippage_yen"],
            "fill event adverse_slippage_yen",
            nonnegative=True,
        )
        self._required_timestamp(value["created_at"], "fill event created_at")
        if not self._money_equal(gross, filled_quantity * filled_price):
            raise ValueError("fill event gross_amount_yenが約定値と一致しません")
        expected_slippage = (
            max(0.0, (filled_price - requested_price) * filled_quantity)
            if value["side"] == OrderSide.BUY.value
            else max(0.0, (requested_price - filled_price) * filled_quantity)
        )
        if not self._money_equal(adverse_slippage, expected_slippage):
            raise ValueError("fill event adverse_slippage_yenが約定値と一致しません")
        if value["side"] == OrderSide.BUY.value:
            if not self._money_equal(cash_delta, -(gross + commission)):
                raise ValueError("BUY fill event cash_delta_yenが不正です")
            if cost_basis != 0.0 or realized_before_commission != 0.0:
                raise ValueError("BUY fill eventに売却損益が設定されています")
            if eligible_quantity != filled_quantity:
                raise ValueError("新規BUYは全数量がeconomics eligibleです")
            if not self._money_equal(eligible_commission, commission):
                raise ValueError("BUY eligible commissionが手数料と一致しません")
            if eligible_realized != 0.0:
                raise ValueError("BUY eligible realized P&Lは0でなければなりません")
        else:
            if not self._money_equal(cash_delta, gross - commission):
                raise ValueError("SELL fill event cash_delta_yenが不正です")
            if not self._money_equal(
                realized_before_commission,
                gross - cost_basis,
            ):
                raise ValueError("SELL fill event realized P&Lが原価と一致しません")
            expected_eligible_commission = round(
                commission * eligible_quantity / filled_quantity,
                2,
            )
            if not self._money_equal(
                eligible_commission,
                expected_eligible_commission,
            ):
                raise ValueError("SELL eligible commissionの按分が不正です")
        digest = value["event_sha256"]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("fill event event_sha256が不正です")
        if digest != self._canonical_event_sha256(value):
            raise ValueError("fill event hashが一致しません")
        return dict(value)

    def _validate_v2_reconciliation(self) -> None:
        baseline_ids = set(
            self._economics_baseline["processed_client_order_ids"]
        )
        event_ids = {event["client_order_id"] for event in self._fill_events}
        if baseline_ids.intersection(event_ids):
            raise ValueError("baselineとfill_eventsのclient_order_idが重複しています")
        if self._processed_client_order_ids != baseline_ids.union(event_ids):
            raise ValueError("processed_client_order_idsが約定証拠と一致しません")

        expected_cash = float(self._economics_baseline["cash_yen"])
        expected_realized = float(
            self._economics_baseline["realized_pnl_yen"]
        )
        expected_quantities = {
            ticker: int(position["quantity"])
            for ticker, position in self._economics_baseline["positions"].items()
        }
        expected_average_prices = {
            ticker: float(position["average_price"])
            for ticker, position in self._economics_baseline["positions"].items()
        }
        expected_tracked_quantities: dict[str, int] = {}
        expected_tracked_costs: dict[str, float] = {}
        for event in self._fill_events:
            ticker = event["ticker"].strip().upper()
            side = event["side"]
            quantity = int(event["filled_quantity"])
            eligible_quantity = int(event["economics_eligible_quantity"])
            expected_cash = round(
                expected_cash + float(event["cash_delta_yen"]),
                2,
            )
            if side == OrderSide.BUY.value:
                old_quantity = expected_quantities.get(ticker, 0)
                old_average = expected_average_prices.get(ticker, 0.0)
                new_quantity = old_quantity + quantity
                expected_average_prices[ticker] = round(
                    (
                        old_quantity * old_average
                        + float(event["gross_amount_yen"])
                    )
                    / new_quantity,
                    4,
                )
                expected_quantities[ticker] = new_quantity
                expected_tracked_quantities[ticker] = (
                    expected_tracked_quantities.get(ticker, 0)
                    + eligible_quantity
                )
                expected_tracked_costs[ticker] = round(
                    expected_tracked_costs.get(ticker, 0.0)
                    + float(event["gross_amount_yen"]),
                    2,
                )
            else:
                current_quantity = expected_quantities.get(ticker, 0)
                if quantity > current_quantity:
                    raise ValueError("fill_eventsのSELL数量が証拠上の保有数量を超えています")
                current_average = expected_average_prices.get(ticker)
                if current_average is None:
                    raise ValueError("SELL対象の再構成平均原価がありません")
                expected_cost_basis = round(quantity * current_average, 2)
                if not self._money_equal(
                    float(event["cost_basis_released_yen"]),
                    expected_cost_basis,
                ):
                    raise ValueError("SELL cost basisが再構成平均原価と一致しません")
                tracked_quantity = expected_tracked_quantities.get(ticker, 0)
                legacy_quantity = current_quantity - tracked_quantity
                expected_eligible_quantity = min(
                    tracked_quantity,
                    max(0, quantity - legacy_quantity),
                )
                if eligible_quantity != expected_eligible_quantity:
                    raise ValueError("SELL eligible数量がlegacy-first規則と一致しません")
                remaining = current_quantity - quantity
                if remaining == 0:
                    expected_quantities.pop(ticker, None)
                    expected_average_prices.pop(ticker, None)
                else:
                    expected_quantities[ticker] = remaining
                if eligible_quantity > tracked_quantity:
                    raise ValueError("SELL eligible数量がtracked数量を超えています")
                expected_tracked_quantities[ticker] = (
                    tracked_quantity - eligible_quantity
                )
                tracked_cost_before = expected_tracked_costs.get(ticker, 0.0)
                eligible_cost_basis = (
                    round(
                        tracked_cost_before
                        / tracked_quantity
                        * eligible_quantity,
                        2,
                    )
                    if tracked_quantity > 0
                    else 0.0
                )
                expected_eligible_realized = round(
                    eligible_quantity * float(event["filled_price"])
                    - eligible_cost_basis,
                    2,
                )
                if not self._money_equal(
                    float(
                        event[
                            "economics_eligible_realized_pnl_before_commission_yen"
                        ]
                    ),
                    expected_eligible_realized,
                ):
                    raise ValueError("SELL eligible realized P&Lがtracked原価と一致しません")
                expected_tracked_costs[ticker] = round(
                    tracked_cost_before - eligible_cost_basis,
                    2,
                )
                if expected_tracked_quantities[ticker] == 0:
                    if not self._money_equal(
                        expected_tracked_costs[ticker],
                        0.0,
                    ):
                        raise ValueError("tracked数量0で原価残高が残っています")
                    expected_tracked_quantities.pop(ticker, None)
                    expected_tracked_costs.pop(ticker, None)
                expected_realized = round(
                    expected_realized
                    + float(event["realized_pnl_before_commission_yen"])
                    - float(event["commission_yen"]),
                    2,
                )

        if not self._money_equal(self._cash_yen, expected_cash):
            raise ValueError("cash_yenがbaselineとfill_eventsに一致しません")
        if not self._money_equal(self._realized_pnl_yen, expected_realized):
            raise ValueError("realized_pnl_yenがbaselineとfill_eventsに一致しません")
        actual_quantities = {
            ticker: position.quantity
            for ticker, position in self._positions.items()
        }
        if actual_quantities != expected_quantities:
            raise ValueError("positions数量がbaselineとfill_eventsに一致しません")
        for ticker, expected_average in expected_average_prices.items():
            if abs(
                round(self._positions[ticker].average_price, 4)
                - round(expected_average, 4)
            ) > 0.00011:
                raise ValueError("position average_priceがfill再生値と一致しません")
        actual_tracked_quantities = {
            ticker: position.economics_tracked_quantity
            for ticker, position in self._positions.items()
            if position.economics_tracked_quantity > 0
        }
        if actual_tracked_quantities != expected_tracked_quantities:
            raise ValueError("tracked数量がfill_eventsに一致しません")
        for ticker, expected_cost in expected_tracked_costs.items():
            if not self._money_equal(
                self._positions[ticker].economics_tracked_cost_basis_yen,
                expected_cost,
            ):
                raise ValueError("tracked cost basisがfill_eventsに一致しません")

    def _filled_result(
        self,
        order: OrderRequest,
        ticker: str,
        message: str,
        *,
        commission_yen: float = 0.0,
        cash_delta_yen: float = 0.0,
        cost_basis_released_yen: float = 0.0,
        realized_pnl_before_commission_yen: float = 0.0,
        economics_eligible_quantity: int = 0,
        economics_eligible_commission_yen: float = 0.0,
        economics_eligible_realized_pnl_before_commission_yen: float = 0.0,
    ) -> OrderResult:
        filled_price = round(order.limit_price, 2)
        requested_price = round(order.limit_price, 2)
        adverse_slippage_yen = round(
            max(
                0.0,
                (
                    filled_price - requested_price
                    if order.side is OrderSide.BUY
                    else requested_price - filled_price
                )
                * order.quantity,
            ),
            2,
        )
        return OrderResult(
            broker_name=self.broker_name,
            broker_order_id=f"PAPER-{uuid4().hex[:16].upper()}",
            client_order_id=order.client_order_id,
            ticker=ticker,
            side=order.side,
            quantity=order.quantity,
            requested_price=requested_price,
            filled_quantity=order.quantity,
            filled_price=filled_price,
            status=OrderStatus.FILLED,
            message=message,
            created_at=_now_jst(),
            commission_yen=round(commission_yen, 2),
            cash_delta_yen=round(cash_delta_yen, 2),
            cost_basis_released_yen=round(cost_basis_released_yen, 2),
            realized_pnl_before_commission_yen=round(
                realized_pnl_before_commission_yen,
                2,
            ),
            economics_eligible_quantity=economics_eligible_quantity,
            economics_eligible_commission_yen=round(
                economics_eligible_commission_yen,
                2,
            ),
            economics_eligible_realized_pnl_before_commission_yen=round(
                economics_eligible_realized_pnl_before_commission_yen,
                2,
            ),
            adverse_slippage_yen=adverse_slippage_yen,
        )

    def _rejected_result(
        self,
        order: OrderRequest,
        ticker: str,
        message: str,
    ) -> OrderResult:
        return OrderResult(
            broker_name=self.broker_name,
            broker_order_id="",
            client_order_id=order.client_order_id,
            ticker=ticker,
            side=order.side,
            quantity=order.quantity,
            requested_price=round(order.limit_price, 2),
            filled_quantity=0,
            filled_price=0.0,
            status=OrderStatus.REJECTED,
            message=message,
            created_at=_now_jst(),
        )
