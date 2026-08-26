# PHOENIX_CLAUDE_SYNC_AUDIT

Generated: 2026-08-27 07:41:55 +09:00
Branch: claude-sync-audit
Base main head: a9e676886326a2d607093b3541c35061e1ba1fdd
Current HEAD: a9e676886326a2d607093b3541c35061e1ba1fdd
Origin: https://github.com/masaA309/PHOENIX.git

This packet is raw evidence for third-party audit. Claude must fill the required output fields below.

CLAUDE_REQUIRED_OUTPUT:
AUDIT_RESULT: PASS / FAIL / NOT_PROVEN
SYNC_FILE_SET_JUDGMENT:
MISSING_REQUIRED_FILES:
FILES_THAT_SHOULD_NOT_BE_SYNCED:
CODE_DEFECTS:
INCOMPLETE_IMPLEMENTATION:
TEST_COVERAGE_GAPS_RELEVANT_TO_SYNC:
CROSS_FILE_CONTRACT_ISSUES:
VBA_PYTHON_CONTRACT_ISSUES:
PROMPT_VALIDATOR_ISSUES:
PROPOSED_GIT_INSTRUCTION_JUDGMENT:
AGENTS_CONFLICTS:
BLOCKERS_BEFORE_COMMIT:
MINIMUM_REQUIRED_FIXES:
SAFE_TO_COMMIT_AND_PUSH: YES / NO

## git status --short

 M phoenix_core/order_bridge_gate.py
 M phoenix_core/production_rakuten_rss_transport.py
 M phoenix_core/rakuten_rss_adapter.py
 M phoenix_core/rakuten_rss_broker.py
 M tests/test_v7_step49.py
 M vba/PHOENIX_RSS_ORDER_BRIDGE.bas
?? .tmp_vbaProject.bin
?? PHOENIX_CLAUDE_BOOT_REVIEW.txt
?? PHOENIX_CLAUDE_BOOT_REVIEW_SUPPLEMENT.txt
?? PHOENIX_STEP44_WRITER_REVIEW.txt
?? backup/v7_rss_bootstrap/
?? config/formal_validation_runs.json
?? prompt_redundancy_validator.py
?? tests/test_prompt_redundancy_validator.py

## git diff --numstat (tracked 6 files)

87	1	phoenix_core/order_bridge_gate.py
787	39	phoenix_core/production_rakuten_rss_transport.py
36	0	phoenix_core/rakuten_rss_adapter.py
144	19	phoenix_core/rakuten_rss_broker.py
498	8	tests/test_v7_step49.py
8	2	vba/PHOENIX_RSS_ORDER_BRIDGE.bas

## git diff (tracked 6 files)

diff --git a/phoenix_core/order_bridge_gate.py b/phoenix_core/order_bridge_gate.py
index d35621d..15db5c6 100644
--- a/phoenix_core/order_bridge_gate.py
+++ b/phoenix_core/order_bridge_gate.py
@@ -1501,6 +1501,30 @@ def print_preorder_summary(report: Mapping[str, Any]) -> None:
     print("=" * 92)
 
 
+def _persist_live_reconcile_only_mode(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
+    persisted_config = dict(config)
+    broker_config = dict(persisted_config.get("broker", {}))
+    persisted_config["operating_mode"] = "LIVE_RECONCILE_ONLY"
+    persisted_config["trading_mode"] = "LIVE"
+    persisted_config["execution_mode"] = "LIVE"
+    persisted_config["trading_actions"] = "RECONCILE_ONLY"
+    persisted_config["allowed_trading_actions"] = ["RECONCILE_ONLY"]
+    broker_config["type"] = "rakuten_rss"
+    broker_config["transport_mode"] = "production"
+    broker_config["live_trading_enabled"] = True
+    broker_config["live_enabled"] = True
+    broker_config["production_transport_enabled"] = True
+    broker_config["production_live_fire_armed"] = False
+    persisted_config["broker"] = broker_config
+
+    config_path = (root / "config" / "v7_direct_pipeline_config.json").resolve()
+    config_path.parent.mkdir(parents=True, exist_ok=True)
+    temp_path = config_path.with_name(f"{config_path.name}.tmp")
+    temp_path.write_text(json.dumps(persisted_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
+    temp_path.replace(config_path)
+    return persisted_config
+
+
 def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> list[Any]:
     report = context.report
     operating_mode, trading_mode, execution_mode, trading_actions, _ = _activation_config(context.config)
@@ -1539,9 +1563,11 @@ def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> li
     if current_trade_signals_context != context.trade_signals_context:
         raise RuntimeError("TRADE_SIGNALS_CONTEXT_CHANGED")
 
-    broker = create_broker(dict(context.config), root)
+    dispatch_config = dict(context.config)
+    broker = create_broker(dict(dispatch_config), root)
     preflight_ran = False
     effective_mode = operating_mode
+    reconcile_persisted = False
     try:
         broker_health = broker.health_check()
     except Exception as error:
@@ -1551,6 +1577,16 @@ def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> li
                 operating_mode,
                 broker_health_ok=False,
             )
+            if (
+                operating_mode == "LIVE_ACTIVE"
+                and effective_mode == "LIVE_RECONCILE_ONLY"
+                and not reconcile_persisted
+            ):
+                dispatch_config = _persist_live_reconcile_only_mode(
+                    root,
+                    dispatch_config,
+                )
+                reconcile_persisted = True
         else:
             effective_mode = _resolve_live_dispatch_mode(operating_mode)
     else:
@@ -1559,6 +1595,16 @@ def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> li
                 operating_mode,
                 broker_health_ok=bool(broker_health.healthy),
             )
+            if (
+                operating_mode == "LIVE_ACTIVE"
+                and effective_mode == "LIVE_RECONCILE_ONLY"
+                and not reconcile_persisted
+            ):
+                dispatch_config = _persist_live_reconcile_only_mode(
+                    root,
+                    dispatch_config,
+                )
+                reconcile_persisted = True
 
     if effective_mode == "LIVE_ACTIVE" and operating_mode == "LIVE_ACTIVE":
         live_preflight_blockers = _live_submit_preflight(root, broker)
@@ -1568,6 +1614,16 @@ def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> li
                 effective_mode,
                 queue_clear=False,
             )
+            if (
+                operating_mode == "LIVE_ACTIVE"
+                and effective_mode == "LIVE_RECONCILE_ONLY"
+                and not reconcile_persisted
+            ):
+                dispatch_config = _persist_live_reconcile_only_mode(
+                    root,
+                    dispatch_config,
+                )
+                reconcile_persisted = True
 
     if effective_mode == "LIVE_RECONCILE_ONLY":
         if not preflight_ran:
@@ -1593,6 +1649,16 @@ def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> li
                 effective_mode,
                 queue_clear=False,
             )
+            if (
+                operating_mode == "LIVE_ACTIVE"
+                and effective_mode == "LIVE_RECONCILE_ONLY"
+                and not reconcile_persisted
+            ):
+                dispatch_config = _persist_live_reconcile_only_mode(
+                    root,
+                    dispatch_config,
+                )
+                reconcile_persisted = True
             break
 
         try:
@@ -1602,6 +1668,16 @@ def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> li
                 effective_mode,
                 submit_error=True,
             )
+            if (
+                operating_mode == "LIVE_ACTIVE"
+                and effective_mode == "LIVE_RECONCILE_ONLY"
+                and not reconcile_persisted
+            ):
+                dispatch_config = _persist_live_reconcile_only_mode(
+                    root,
+                    dispatch_config,
+                )
+                reconcile_persisted = True
             raise RuntimeError(f"BROKER_SUBMIT_FAILED:{client_order_id}: {type(error).__name__}: {error}") from error
 
         submit_status = getattr(submit_result, "status", None)
@@ -1615,6 +1691,16 @@ def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> li
                 effective_mode,
                 submit_status=submit_status_name,
             )
+            if (
+                operating_mode == "LIVE_ACTIVE"
+                and effective_mode == "LIVE_RECONCILE_ONLY"
+                and not reconcile_persisted
+            ):
+                dispatch_config = _persist_live_reconcile_only_mode(
+                    root,
+                    dispatch_config,
+                )
+                reconcile_persisted = True
             break
         if submit_status_name != "FILLED":
             raise RuntimeError(f"UNEXPECTED_BROKER_STATUS:{client_order_id}:{submit_status_name}")
diff --git a/phoenix_core/production_rakuten_rss_transport.py b/phoenix_core/production_rakuten_rss_transport.py
index 222da43..36e1f25 100644
--- a/phoenix_core/production_rakuten_rss_transport.py
+++ b/phoenix_core/production_rakuten_rss_transport.py
@@ -25,6 +25,8 @@ from phoenix_core.rakuten_rss_adapter import (
 JST = ZoneInfo("Asia/Tokyo")
 ORDER_MACRO_NAME = "RssStockOrder_V"
 CANCEL_MACRO_NAME = "RssCancelOrder_V"
+ORDER_ID_LIST_MACRO_NAME = "RssOrderIDList"
+ORDER_STATUS_MACRO_NAME = "RssOrderStatus"
 DEFAULT_WORKBOOK_NAME = "PHOENIX_RSS_PRODUCTION.xlsm"
 PHOENIX_ROOT = Path(__file__).resolve().parents[1]
 DEFAULT_WORKBOOK_PATH = (PHOENIX_ROOT / "runtime" / "v7_rss_production" / DEFAULT_WORKBOOK_NAME).resolve()
@@ -169,6 +171,69 @@ def _expiration_yyyymmdd(value: Any) -> str:
     return parsed.strftime("%Y%m%d")
 
 
+def _stable_rss_order_id(client_order_id: str, broker_order_id: str) -> int:
+    digest = hashlib.sha256(f"{client_order_id}|{broker_order_id}".encode("utf-8")).hexdigest()
+    value = int(digest[:16], 16) % 2147483647
+    return value + 1
+
+
+def _normalize_rss_order_id_entry(value: Any) -> RakutenRssOrderIdEntry | None:
+    if value is None:
+        return None
+
+    if isinstance(value, Mapping):
+        raw_id = value.get("rss_order_id", value.get("order_id", value.get("発注ID", "")))
+        raw_function = value.get("function_name", value.get("関数名", ""))
+        raw_order_date = value.get("order_date", value.get("発注日", ""))
+        raw_order_time = value.get("order_time", value.get("発注時刻", ""))
+        raw_order_number = value.get("order_number", value.get("注文番号", ""))
+        raw_result = value.get("result", value.get("発注結果", ""))
+    elif isinstance(value, (list, tuple)):
+        if len(value) < 6:
+            return None
+        raw_id, raw_function, raw_order_date, raw_order_time, raw_order_number, raw_result = value[:6]
+    else:
+        return None
+
+    try:
+        rss_order_id = int(str(raw_id).strip())
+    except Exception:
+        return None
+    if rss_order_id < 1 or rss_order_id > 2147483647:
+        return None
+
+    return RakutenRssOrderIdEntry(
+        rss_order_id=rss_order_id,
+        function_name=str(raw_function or "").strip(),
+        order_date=str(raw_order_date or "").strip(),
+        order_time=str(raw_order_time or "").strip(),
+        order_number=str(raw_order_number or "").strip(),
+        result=str(raw_result or "").strip(),
+    )
+
+
+def _normalize_rss_order_id_entries(value: Any) -> tuple[RakutenRssOrderIdEntry, ...]:
+    if value is None:
+        return ()
+    if isinstance(value, Mapping):
+        entry = _normalize_rss_order_id_entry(value)
+        return () if entry is None else (entry,)
+    if isinstance(value, (list, tuple)):
+        if len(value) == 0:
+            return ()
+        first_entry = _normalize_rss_order_id_entry(value)
+        if first_entry is not None:
+            return (first_entry,)
+        entries: list[RakutenRssOrderIdEntry] = []
+        for row in value:
+            entry = _normalize_rss_order_id_entry(row)
+            if entry is not None:
+                entries.append(entry)
+        return tuple(entries)
+    entry = _normalize_rss_order_id_entry(value)
+    return () if entry is None else (entry,)
+
+
 def _sheet_value(value: Any) -> Any:
     if isinstance(value, datetime):
         return value.isoformat(timespec="seconds")
@@ -271,6 +336,16 @@ class WorkbookRuntimeState:
     message: str
 
 
+@dataclass(frozen=True, slots=True)
+class RakutenRssOrderIdEntry:
+    rss_order_id: int
+    function_name: str
+    order_date: str
+    order_time: str
+    order_number: str
+    result: str
+
+
 def _runtime_truthy_cell(value: Any) -> bool:
     if isinstance(value, bool):
         return value
@@ -392,7 +467,7 @@ class ExcelComBackend(Protocol):
     ) -> None:
         raise NotImplementedError
 
-    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str) -> None:
+    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
         raise NotImplementedError
 
     def read_order_updates(
@@ -402,6 +477,15 @@ class ExcelComBackend(Protocol):
     ) -> tuple[RakutenRssOrderUpdate, ...]:
         raise NotImplementedError
 
+    def read_rss_order_ledger(
+        self,
+        session: ExcelTransportSession,
+    ) -> tuple[RakutenRssOrderIdEntry, ...]:
+        raise NotImplementedError
+
+    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
+        raise NotImplementedError
+
     def stage_cancel_payload(
         self,
         session: ExcelTransportSession,
@@ -409,7 +493,7 @@ class ExcelComBackend(Protocol):
     ) -> None:
         raise NotImplementedError
 
-    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str) -> None:
+    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
         raise NotImplementedError
 
     def close(self, session: ExcelTransportSession) -> None:
@@ -445,14 +529,20 @@ class MockExcelComBackend:
         self.health_calls = 0
         self.submit_stage_calls = 0
         self.submit_macro_calls = 0
+        self.submit_macro_args: list[tuple[Any, ...]] = []
         self.poll_calls = 0
         self.cancel_stage_calls = 0
         self.cancel_macro_calls = 0
+        self.cancel_macro_args: list[tuple[Any, ...]] = []
         self.closed_calls = 0
         self.submitted_payloads: list[dict[str, Any]] = []
         self.cancel_payloads: list[dict[str, Any]] = []
         self.publish_calls = 0
         self._updates_by_broker_order_id: dict[str, list[RakutenRssOrderUpdate]] = {}
+        self._rss_order_ledger_entries: list[RakutenRssOrderIdEntry] = []
+        self._rss_order_status_by_id: dict[int, int] = {}
+        self.rss_order_ledger_calls = 0
+        self.rss_order_status_calls = 0
 
     def queue_updates(
         self,
@@ -461,6 +551,33 @@ class MockExcelComBackend:
     ) -> None:
         self._updates_by_broker_order_id[broker_order_id] = list(updates)
 
+    def queue_rss_order_ledger_entry(
+        self,
+        rss_order_id: int,
+        *,
+        function_name: str = ORDER_MACRO_NAME,
+        order_number: str = "",
+        result: str = "",
+        order_date: str = "",
+        order_time: str = "",
+    ) -> None:
+        self._rss_order_ledger_entries = [
+            entry for entry in self._rss_order_ledger_entries if entry.rss_order_id != rss_order_id
+        ]
+        self._rss_order_ledger_entries.append(
+            RakutenRssOrderIdEntry(
+                rss_order_id=rss_order_id,
+                function_name=function_name,
+                order_date=order_date,
+                order_time=order_time,
+                order_number=order_number,
+                result=result,
+            )
+        )
+
+    def set_rss_order_status(self, rss_order_id: int, status: int) -> None:
+        self._rss_order_status_by_id[rss_order_id] = int(status)
+
     def connect(self, workbook_path: Path, workbook_name: str) -> ExcelTransportSession:
         self.connect_calls += 1
         if not self.excel_running:
@@ -509,8 +626,9 @@ class MockExcelComBackend:
         self.submit_stage_calls += 1
         self.submitted_payloads.append(dict(payload))
 
-    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str) -> None:
+    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
         self.submit_macro_calls += 1
+        self.submit_macro_args.append(tuple(args))
 
     def read_order_updates(
         self,
@@ -524,6 +642,17 @@ class MockExcelComBackend:
         self._updates_by_broker_order_id[broker_order_id] = []
         return tuple(updates)
 
+    def read_rss_order_ledger(
+        self,
+        session: ExcelTransportSession,
+    ) -> tuple[RakutenRssOrderIdEntry, ...]:
+        self.rss_order_ledger_calls += 1
+        return tuple(self._rss_order_ledger_entries)
+
+    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
+        self.rss_order_status_calls += 1
+        return int(self._rss_order_status_by_id.get(int(rss_order_id), -1))
+
     def stage_cancel_payload(
         self,
         session: ExcelTransportSession,
@@ -532,8 +661,9 @@ class MockExcelComBackend:
         self.cancel_stage_calls += 1
         self.cancel_payloads.append(dict(payload))
 
-    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str) -> None:
+    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
         self.cancel_macro_calls += 1
+        self.cancel_macro_args.append(tuple(args))
 
     def close(self, session: ExcelTransportSession) -> None:
         self.closed_calls += 1
@@ -912,9 +1042,9 @@ class Win32ComExcelBackend:
     ) -> None:
         self._write_payload(session, SUBMIT_CELL_MAP, payload)
 
-    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str) -> None:
+    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
         try:
-            session.application.Run(f"'{session.workbook.Name}'!{macro_name}")
+            session.application.Run(f"'{session.workbook.Name}'!{macro_name}", *args)
         except Exception as error:
             raise ExcelComError(f"Submit macro failed: {error}") from error
 
@@ -957,6 +1087,29 @@ class Win32ComExcelBackend:
             ),
         )
 
+    def read_rss_order_ledger(
+        self,
+        session: ExcelTransportSession,
+    ) -> tuple[RakutenRssOrderIdEntry, ...]:
+        try:
+            result = session.application.Run(f"'{session.workbook.Name}'!{ORDER_ID_LIST_MACRO_NAME}")
+        except Exception as error:
+            raise ExcelComError(f"Failed to read RssOrderIDList: {error}") from error
+        return _normalize_rss_order_id_entries(result)
+
+    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
+        try:
+            result = session.application.Run(
+                f"'{session.workbook.Name}'!{ORDER_STATUS_MACRO_NAME}",
+                int(rss_order_id),
+            )
+        except Exception as error:
+            raise ExcelComError(f"Failed to read RssOrderStatus for {rss_order_id}: {error}") from error
+        try:
+            return int(str(result).strip())
+        except Exception as error:
+            raise ExcelComError(f"Invalid RssOrderStatus for {rss_order_id}: {result!r}") from error
+
     def stage_cancel_payload(
         self,
         session: ExcelTransportSession,
@@ -964,9 +1117,9 @@ class Win32ComExcelBackend:
     ) -> None:
         self._write_payload(session, CANCEL_CELL_MAP, payload)
 
-    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str) -> None:
+    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
         try:
-            session.application.Run(f"'{session.workbook.Name}'!{macro_name}")
+            session.application.Run(f"'{session.workbook.Name}'!{macro_name}", *args)
         except Exception as error:
             raise ExcelComError(f"Cancel macro failed: {error}") from error
 
@@ -981,12 +1134,18 @@ class Win32ComExcelBackend:
 class _TrackedOrder:
     order: OrderRequest
     broker_order_id: str
+    rss_order_id: int
     submitted_at: datetime
     submit_payload: dict[str, Any]
     stage_state: str = "STAGED"
     submit_request_id: str = ""
     cancel_request_id: str = ""
     cancel_payload: dict[str, Any] | None = None
+    rss_order_number: str = ""
+    rss_order_status_code: int = -1
+    broker_observation_state: str = ""
+    cancel_observation_state: str = ""
+    last_authoritative_rss_status: int = -1
     last_message: str = ""
     filled_quantity: int = 0
     filled_price: float = 0.0
@@ -1480,6 +1639,10 @@ class ProductionRakutenRssTransport:
             status = _parse_order_status(receipt.result)
         except Exception as error:
             raise ExcelComError(f"Invalid bridge receipt result: {error}") from error
+        try:
+            authoritative_rss_status = int(str(receipt.rss_order_status).strip())
+        except Exception:
+            authoritative_rss_status = -1
         return RakutenRssOrderUpdate(
             status=status,
             fill_quantity=receipt.fill_quantity,
@@ -1487,8 +1650,324 @@ class ProductionRakutenRssTransport:
             message=receipt.message or receipt.result,
             updated_at=receipt.received_at,
             rss_order_status=receipt.rss_order_status,
+            rss_order_number=receipt.rss_order_number,
+            authoritative_rss_status=authoritative_rss_status,
+        )
+
+    @staticmethod
+    def _tracked_order_status(order: _TrackedOrder) -> OrderStatus:
+        try:
+            return OrderStatus(order.stage_state)
+        except Exception:
+            return OrderStatus.PENDING
+
+    def _tracked_order_ack(self, order: _TrackedOrder, *, message: str | None = None) -> RakutenRssSubmitAck:
+        status = self._tracked_order_status(order)
+        return RakutenRssSubmitAck(
+            status=status,
+            message=message or order.last_message or status.value,
+            submitted_at=order.submitted_at,
+            rss_order_id=order.rss_order_id,
+            rss_order_number=order.rss_order_number,
+            authoritative_rss_status=order.last_authoritative_rss_status,
+        )
+
+    def _tracked_cancel_ack(self, order: _TrackedOrder, *, message: str | None = None) -> RakutenRssCancelAck:
+        status = self._tracked_order_status(order)
+        return RakutenRssCancelAck(
+            status=status,
+            message=message or order.last_message or status.value,
+            canceled_at=order.submitted_at,
+            rss_order_id=order.rss_order_id,
+            rss_order_number=order.rss_order_number,
+            authoritative_rss_status=order.last_authoritative_rss_status,
+        )
+
+    def _stable_rss_order_id(self, order: OrderRequest, broker_order_id: str) -> int:
+        return _stable_rss_order_id(order.client_order_id, broker_order_id)
+
+    @staticmethod
+    def _rss_order_status_value(value: Any) -> int:
+        try:
+            status = int(str(value).strip())
+        except Exception as error:
+            raise ExcelComError(f"Invalid RssOrderStatus value: {value!r}") from error
+        if status not in {-1, 1, 2, 3}:
+            raise ExcelComError(f"Unsupported RssOrderStatus value: {status}")
+        return status
+
+    def _live_contract_metadata(self, order: OrderRequest) -> dict[str, Any]:
+        metadata = dict(order.metadata or {})
+        required_names = ("account_category", "sor_category", "execution_condition")
+        missing = [name for name in required_names if str(metadata.get(name, "")).strip() == ""]
+        if missing:
+            raise ExcelComError(
+                "LIVE contract fields missing: " + ", ".join(missing)
+            )
+        return metadata
+
+    @staticmethod
+    def _rss_code_from_alias(value: Any, mapping: Mapping[str, int], *, field_name: str) -> int:
+        text = str(value).strip()
+        if not text:
+            raise ExcelComError(f"{field_name} is missing for LIVE contract.")
+        if text.isdigit():
+            code = int(text)
+            if code in mapping.values():
+                return code
+        normalized = text.replace("（", "(").replace("）", ")")
+        if normalized in mapping:
+            return mapping[normalized]
+        if text in mapping:
+            return mapping[text]
+        raise ExcelComError(f"Unsupported {field_name}: {value!r}")
+
+    def _rss_account_category_code(self, value: Any) -> int:
+        return self._rss_code_from_alias(
+            value,
+            {
+                "0": 0,
+                "特定": 0,
+                "1": 1,
+                "一般": 1,
+                "2": 2,
+                "NISA": 2,
+                "NISA(NISA成長投資枠)": 2,
+                "3": 3,
+                "旧NISA": 3,
+            },
+            field_name="account_category",
+        )
+
+    def _rss_sor_code(self, value: Any) -> int:
+        return self._rss_code_from_alias(
+            value,
+            {
+                "0": 0,
+                "通常": 0,
+                "通常注文": 0,
+                "1": 1,
+                "SOR": 1,
+                "SOR注文": 1,
+            },
+            field_name="sor_category",
+        )
+
+    def _rss_execution_condition_code(self, value: Any) -> int:
+        return self._rss_code_from_alias(
+            value,
+            {
+                "1": 1,
+                "本日中": 1,
+                "2": 2,
+                "今週中": 2,
+                "3": 3,
+                "寄付": 3,
+                "4": 4,
+                "引け": 4,
+                "5": 5,
+                "期間指定": 5,
+                "6": 6,
+                "大引不成": 6,
+                "7": 7,
+                "不成": 7,
+            },
+            field_name="execution_condition",
+        )
+
+    def _rss_trigger_condition_code(self, value: Any) -> int | str:
+        text = str(value).strip()
+        if not text:
+            return ""
+        if text.isdigit() and int(text) in {1, 2}:
+            return int(text)
+        mapping = {
+            "1": 1,
+            "以上": 1,
+            "2": 2,
+            "以下": 2,
+        }
+        return self._rss_code_from_alias(value, mapping, field_name="trigger_condition")
+
+    def _rss_price_kind_code(self, value: Any, *, field_name: str) -> int:
+        text = str(value).strip()
+        if not text:
+            raise ExcelComError(f"{field_name} is missing for LIVE contract.")
+        if text.isdigit() and int(text) in {0, 1}:
+            return int(text)
+        mapping = {
+            "0": 0,
+            "成行": 0,
+            "1": 1,
+            "指値": 1,
+        }
+        return self._rss_code_from_alias(value, mapping, field_name=field_name)
+
+    def _rss_optional_price(self, value: Any, *, field_name: str) -> Any:
+        text = str(value).strip()
+        if not text:
+            return ""
+        try:
+            return round(float(text), 2)
+        except Exception as error:
+            raise ExcelComError(f"Unsupported {field_name}: {value!r}") from error
+
+    def _rss_stop_price_kind_code(self, value: Any) -> int | str:
+        text = str(value).strip()
+        if not text:
+            return ""
+        if text.isdigit() and int(text) in {0, 1}:
+            return int(text)
+        mapping = {
+            "0": 0,
+            "成行": 0,
+            "売り成行": 0,
+            "買い成行": 0,
+            "1": 1,
+            "指値": 1,
+            "売り指値": 1,
+            "買い指値": 1,
+        }
+        return self._rss_code_from_alias(value, mapping, field_name="stop_price_kind")
+
+    def _rss_set_order_kind_code(self, value: Any) -> int | str:
+        text = str(value).strip()
+        if not text:
+            return ""
+        if text.isdigit() and int(text) in {0, 1}:
+            return int(text)
+        mapping = {
+            "0": 0,
+            "成行": 0,
+            "売り成行": 0,
+            "買い成行": 0,
+            "1": 1,
+            "指値": 1,
+            "売り指値": 1,
+            "買い指値": 1,
+        }
+        return self._rss_code_from_alias(value, mapping, field_name="set_order_kind")
+
+    def _rss_order_kind_code(self, order: OrderRequest, metadata: Mapping[str, Any]) -> int:
+        order_category = str(
+            _metadata_value(order, "order_category", default=metadata.get("order_category", ""))
+        ).strip()
+        if order_category in {"0", "通常", "通常注文"}:
+            return 0
+        if order_category in {"1", "逆指値付通常注文"}:
+            return 1
+        if order_category in {"2", "逆指値注文"}:
+            return 2
+        if order.side is OrderSide.SELL and any(
+            key in metadata for key in ("target_price", "take_profit_price", "stop_price", "stop_loss_price")
+        ):
+            return 1
+        return 0
+
+    @staticmethod
+    def _rss_side_code(order: OrderRequest) -> int:
+        if order.side is OrderSide.BUY:
+            return 3
+        if order.side is OrderSide.SELL:
+            return 1
+        raise ExcelComError(f"Unsupported order side: {order.side}")
+
+    @staticmethod
+    def _rss_price_kind(order: OrderRequest) -> int:
+        order_type_text = str(getattr(order.order_type, "value", order.order_type)).strip().upper()
+        if order_type_text in {"MARKET", "成行"}:
+            return 0
+        if order_type_text in {"LIMIT", "指値"}:
+            return 1
+        raise ExcelComError(f"Unsupported order type: {order.order_type}")
+
+    def _rss_optional_text(self, value: Any) -> str:
+        text = str(value).strip()
+        return text
+
+    def _build_rss_stock_order_arguments(self, order: OrderRequest, rss_order_id: int) -> tuple[Any, ...]:
+        metadata = self._live_contract_metadata(order)
+        order_category = self._rss_order_kind_code(order, metadata)
+        price_kind = self._rss_price_kind(order)
+        account_category = self._rss_account_category_code(metadata.get("account_category", ""))
+        sor_category = self._rss_sor_code(metadata.get("sor_category", ""))
+        execution_condition = self._rss_execution_condition_code(metadata.get("execution_condition", ""))
+        expiration = _expiration_yyyymmdd(metadata.get("expiration", metadata.get("expires_at", "")))
+        quantity = int(order.quantity)
+        order_price: Any = round(float(order.limit_price), 2) if price_kind == 1 else ""
+        stop_condition_price = self._rss_optional_price(
+            _metadata_value(order, "stop_condition_price", "stop_price", default=""),
+            field_name="stop_condition_price",
+        )
+        stop_condition_kind = self._rss_trigger_condition_code(
+            _metadata_value(order, "stop_condition_kind", "trigger_condition", default="")
+        )
+        stop_price_kind = self._rss_stop_price_kind_code(
+            _metadata_value(order, "stop_price_kind", "post_trigger_order_type", default="")
+        )
+        stop_price = self._rss_optional_price(
+            _metadata_value(order, "stop_price", "stop_loss_price", default=""),
+            field_name="stop_price",
+        )
+        set_order_kind = self._rss_set_order_kind_code(_metadata_value(order, "set_order_kind", default=""))
+        set_order_price = self._rss_optional_price(
+            _metadata_value(order, "set_order_price", default=""),
+            field_name="set_order_price",
+        )
+        set_order_execution_condition = self._rss_execution_condition_code(
+            _metadata_value(order, "set_order_execution_condition", default="")
+        ) if str(_metadata_value(order, "set_order_execution_condition", default="")).strip() else ""
+        set_order_expiration = _expiration_yyyymmdd(_metadata_value(order, "set_order_expiration", default=""))
+        ticker = order.ticker.strip().upper()
+        return (
+            int(rss_order_id),
+            ticker,
+            self._rss_side_code(order),
+            order_category,
+            sor_category,
+            quantity,
+            price_kind,
+            order_price,
+            execution_condition,
+            expiration,
+            account_category,
+            stop_condition_price,
+            stop_condition_kind,
+            stop_price_kind,
+            stop_price,
+            set_order_kind,
+            set_order_price,
+            set_order_execution_condition,
+            set_order_expiration,
         )
 
+    def _build_rss_cancel_order_arguments(self, rss_order_id: int, order_number: str) -> tuple[Any, ...]:
+        if not str(order_number).strip():
+            raise ExcelComError("RSS order number is missing for cancel.")
+        return (int(rss_order_id), str(order_number).strip())
+
+    def _find_rss_order_ledger_entry(
+        self,
+        session: ExcelTransportSession,
+        rss_order_id: int,
+        *,
+        function_name: str,
+    ) -> RakutenRssOrderIdEntry | None:
+        for entry in self._backend.read_rss_order_ledger(session):
+            if entry.rss_order_id != int(rss_order_id):
+                continue
+            if str(entry.function_name).strip() and str(entry.function_name).strip() != function_name:
+                continue
+            return entry
+        return None
+
+    def _observe_rss_order_status(
+        self,
+        session: ExcelTransportSession,
+        rss_order_id: int,
+    ) -> int:
+        return self._backend.read_rss_order_status(session, int(rss_order_id))
+
     def submit_order(self, order: OrderRequest, broker_order_id: str) -> RakutenRssSubmitAck:
         order.validate()
         gate_message = self._gate_message()
@@ -1496,36 +1975,45 @@ class ProductionRakutenRssTransport:
             return RakutenRssSubmitAck(
                 status=OrderStatus.REJECTED,
                 message=gate_message,
+                rss_order_id=self._stable_rss_order_id(order, broker_order_id),
             )
 
         submitted_at = self._clock()
         payload = self._build_submit_payload(order, broker_order_id, submitted_at)
         with self._lock:
             self._last_submit_payload = dict(payload)
+            existing = self._orders.get(broker_order_id)
+            if existing is not None:
+                return self._tracked_order_ack(existing)
+
+        rss_order_id = self._stable_rss_order_id(order, broker_order_id)
         record: _TrackedOrder | None = None
 
         try:
-            health = self.health_check()
-            if not health.connected:
-                return RakutenRssSubmitAck(
-                    status=OrderStatus.REJECTED,
-                    message=health.message,
-                )
-            if not self._armed:
-                return RakutenRssSubmitAck(
-                    status=OrderStatus.REJECTED,
-                    message="production_live_fire_armed=false; submit staging disabled.",
-                    submitted_at=submitted_at,
-                )
             with self._lock:
                 record = _TrackedOrder(
                     order=order,
                     broker_order_id=broker_order_id,
+                    rss_order_id=rss_order_id,
                     submitted_at=submitted_at,
                     submit_payload=dict(payload),
                     submit_request_id=self._file_bridge_request_id("SUBMIT", broker_order_id),
                 )
                 self._orders[broker_order_id] = record
+
+            health = self.health_check()
+            if not health.connected:
+                with self._lock:
+                    if record is not None:
+                        record.stage_state = OrderStatus.REJECTED.value
+                        record.last_message = health.message
+                        record.updated_at = self._clock()
+                return RakutenRssSubmitAck(
+                    status=OrderStatus.REJECTED,
+                    message=health.message,
+                    submitted_at=submitted_at,
+                    rss_order_id=rss_order_id,
+                )
             if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                 request_id = self._file_bridge_request_id("SUBMIT", broker_order_id)
                 try:
@@ -1544,6 +2032,7 @@ class ProductionRakutenRssTransport:
                         status=OrderStatus.REJECTED,
                         message=f"FILE_READY bridge staging failed: {error}",
                         submitted_at=submitted_at,
+                        rss_order_id=rss_order_id,
                     )
                 with self._lock:
                     record.submit_request_id = request_id
@@ -1558,31 +2047,117 @@ class ProductionRakutenRssTransport:
                         status=OrderStatus.PENDING,
                         message=record.last_message,
                         submitted_at=submitted_at,
+                        rss_order_id=record.rss_order_id,
+                        rss_order_number=record.rss_order_number,
+                        authoritative_rss_status=record.last_authoritative_rss_status,
                     )
             if health.transport_source != TRANSPORT_SOURCE_COM_LIVE:
+                with self._lock:
+                    if record is not None:
+                        record.stage_state = OrderStatus.REJECTED.value
+                        record.last_message = health.message
+                        record.updated_at = self._clock()
                 return RakutenRssSubmitAck(
                     status=OrderStatus.REJECTED,
                     message=health.message,
+                    submitted_at=submitted_at,
+                    rss_order_id=rss_order_id,
                 )
             session = self._ensure_session()
             self._com_call_count += 1
-            self._backend.stage_submit_payload(session, payload)
             if not self._armed:
+                with self._lock:
+                    if record is not None:
+                        record.stage_state = OrderStatus.REJECTED.value
+                        record.last_message = "production_live_fire_armed=false; submit staging disabled."
+                        record.updated_at = self._clock()
                 return RakutenRssSubmitAck(
                     status=OrderStatus.REJECTED,
                     message="armed=false; RssStockOrder_V not called.",
+                    submitted_at=submitted_at,
+                    rss_order_id=rss_order_id,
                 )
+            self._backend.stage_submit_payload(session, payload)
+            submit_args = self._build_rss_stock_order_arguments(order, rss_order_id)
             self._com_call_count += 1
             self._submit_macro_call_count += 1
-            self._backend.invoke_submit_macro(session, ORDER_MACRO_NAME)
+            self._backend.invoke_submit_macro(session, ORDER_MACRO_NAME, *submit_args)
+            ledger_entry = self._find_rss_order_ledger_entry(
+                session,
+                rss_order_id,
+                function_name=ORDER_MACRO_NAME,
+            )
+            try:
+                rss_order_status = self._observe_rss_order_status(session, rss_order_id)
+            except ExcelComError as error:
+                rss_order_status = -1
+                status_error = str(error)
+            else:
+                status_error = ""
             with self._lock:
-                record.stage_state = OrderStatus.ACCEPTED.value
-                record.last_message = "RssStockOrder_V invoked."
-                record.updated_at = self._clock()
+                    if record is not None:
+                        record.rss_order_status_code = rss_order_status
+                        if ledger_entry is not None:
+                            record.rss_order_number = ledger_entry.order_number
+                            if ledger_entry.result:
+                                record.last_message = ledger_entry.result
+                        record.last_authoritative_rss_status = rss_order_status
+                        if not record.last_message:
+                            record.last_message = status_error or "RssStockOrder_V invoked."
+                        if ledger_entry is None or not ledger_entry.order_number or not ledger_entry.result or rss_order_status == -1:
+                            record.stage_state = OrderStatus.PENDING.value
+                            record.broker_observation_state = OrderStatus.PENDING.value
+                            record.updated_at = self._clock()
+                            return RakutenRssSubmitAck(
+                                status=OrderStatus.PENDING,
+                                message=record.last_message or "RssOrderIDList not yet observed.",
+                                submitted_at=submitted_at,
+                                rss_order_id=record.rss_order_id,
+                                rss_order_number=record.rss_order_number,
+                                authoritative_rss_status=record.last_authoritative_rss_status,
+                            )
+                        if rss_order_status == 1:
+                            record.stage_state = OrderStatus.REJECTED.value
+                            record.broker_observation_state = OrderStatus.REJECTED.value
+                            record.updated_at = self._clock()
+                            return RakutenRssSubmitAck(
+                                status=OrderStatus.REJECTED,
+                                message=record.last_message or "RssOrderStatus=1",
+                                submitted_at=submitted_at,
+                                rss_order_id=record.rss_order_id,
+                                rss_order_number=record.rss_order_number,
+                                authoritative_rss_status=record.last_authoritative_rss_status,
+                            )
+                        if rss_order_status == 3:
+                            record.stage_state = OrderStatus.FILLED.value
+                            record.broker_observation_state = OrderStatus.FILLED.value
+                            record.updated_at = self._clock()
+                            return RakutenRssSubmitAck(
+                                status=OrderStatus.FILLED,
+                                message=record.last_message or "RssOrderStatus=3",
+                                submitted_at=submitted_at,
+                                rss_order_id=record.rss_order_id,
+                                rss_order_number=record.rss_order_number,
+                                authoritative_rss_status=record.last_authoritative_rss_status,
+                            )
+                        record.stage_state = OrderStatus.ACCEPTED.value
+                        record.broker_observation_state = OrderStatus.ACCEPTED.value
+                        record.updated_at = self._clock()
+                        return RakutenRssSubmitAck(
+                            status=OrderStatus.ACCEPTED,
+                            message=record.last_message or "RssOrderStatus=2",
+                            submitted_at=submitted_at,
+                            rss_order_id=record.rss_order_id,
+                            rss_order_number=record.rss_order_number,
+                            authoritative_rss_status=record.last_authoritative_rss_status,
+                        )
             return RakutenRssSubmitAck(
-                status=OrderStatus.ACCEPTED,
-                message="RssStockOrder_V invoked.",
+                status=OrderStatus.PENDING,
+                message=status_error or "RssOrderIDList not yet observed.",
                 submitted_at=submitted_at,
+                rss_order_id=rss_order_id,
+                rss_order_number=record.rss_order_number if record is not None else "",
+                authoritative_rss_status=-1,
             )
         except ExcelComError as error:
             if record is not None:
@@ -1594,6 +2169,9 @@ class ProductionRakutenRssTransport:
                 status=OrderStatus.REJECTED,
                 message=str(error),
                 submitted_at=submitted_at,
+                rss_order_id=rss_order_id,
+                rss_order_number=record.rss_order_number if record is not None else "",
+                authoritative_rss_status=record.last_authoritative_rss_status if record is not None else -1,
             )
         except Exception as error:  # pragma: no cover - defensive fail-close
             if record is not None:
@@ -1605,6 +2183,9 @@ class ProductionRakutenRssTransport:
                 status=OrderStatus.REJECTED,
                 message=f"Excel/RSS submit failed: {error}",
                 submitted_at=submitted_at,
+                rss_order_id=rss_order_id,
+                rss_order_number=record.rss_order_number if record is not None else "",
+                authoritative_rss_status=record.last_authoritative_rss_status if record is not None else -1,
             )
 
     def poll_order(self, broker_order_id: str) -> tuple[RakutenRssOrderUpdate, ...]:
@@ -1640,6 +2221,10 @@ class ProductionRakutenRssTransport:
                         record.updated_at = self._clock()
                         record.last_message = update.message
                         record.stage_state = update.status.value
+                        record.broker_observation_state = update.status.value
+                        record.last_authoritative_rss_status = update.authoritative_rss_status
+                        if update.rss_order_number:
+                            record.rss_order_number = update.rss_order_number
                         if update.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                             record.filled_quantity = update.fill_quantity
                             record.filled_price = update.fill_price
@@ -1648,6 +2233,62 @@ class ProductionRakutenRssTransport:
                 session = self._ensure_session()
                 self._com_call_count += 1
                 updates = self._backend.read_order_updates(session, broker_order_id)
+                if not updates:
+                    ledger_entry = self._find_rss_order_ledger_entry(
+                        session,
+                        record.rss_order_id,
+                        function_name=ORDER_MACRO_NAME,
+                    )
+                    try:
+                        rss_order_status = self._observe_rss_order_status(session, record.rss_order_id)
+                    except ExcelComError:
+                        rss_order_status = -1
+                    if ledger_entry is not None and ledger_entry.order_number:
+                        with self._lock:
+                            record.rss_order_number = ledger_entry.order_number
+                            record.last_message = ledger_entry.result or record.last_message
+                            record.rss_order_status_code = rss_order_status
+                            record.last_authoritative_rss_status = rss_order_status
+                    normalized_order_result = self._rss_optional_text(
+                        ledger_entry.result if ledger_entry is not None else "",
+                    ).replace("(", "（").replace(")", "）")
+                    cancel_completed_results = {
+                        "取消済（出来有）",
+                        "取消済（出来無）",
+                        "取消済",
+                    }
+                    if rss_order_status in {1, 2, 3}:
+                        if record.cancel_request_id:
+                            if rss_order_status == 3:
+                                synthetic_status = OrderStatus.FILLED
+                            elif rss_order_status == 1 and normalized_order_result in cancel_completed_results:
+                                synthetic_status = OrderStatus.CANCELED
+                            else:
+                                synthetic_status = OrderStatus.PENDING
+                        else:
+                            if rss_order_status == 1:
+                                synthetic_status = OrderStatus.REJECTED
+                            elif rss_order_status == 3:
+                                synthetic_status = OrderStatus.FILLED
+                            else:
+                                synthetic_status = OrderStatus.ACCEPTED
+                        synthetic_update = RakutenRssOrderUpdate(
+                            status=synthetic_status,
+                            fill_quantity=record.filled_quantity if synthetic_status is OrderStatus.FILLED else 0,
+                            fill_price=record.filled_price if synthetic_status is OrderStatus.FILLED else 0.0,
+                            message=record.last_message or f"RssOrderStatus={rss_order_status}",
+                            updated_at=self._clock(),
+                            rss_order_status=str(rss_order_status),
+                            rss_order_id=record.rss_order_id,
+                            rss_order_number=record.rss_order_number,
+                            authoritative_rss_status=rss_order_status,
+                        )
+                        with self._lock:
+                            record.updated_at = synthetic_update.updated_at
+                            record.last_message = synthetic_update.message
+                            record.stage_state = synthetic_status.value
+                            record.broker_observation_state = synthetic_status.value
+                        return (synthetic_update,)
             else:
                 return ()
         except ExcelComError as error:
@@ -1661,10 +2302,18 @@ class ProductionRakutenRssTransport:
             with self._lock:
                 record.updated_at = self._clock()
                 final_update = updates[-1]
+                record.broker_observation_state = final_update.status.value
+                record.last_authoritative_rss_status = getattr(final_update, "authoritative_rss_status", -1)
+                if getattr(final_update, "rss_order_number", ""):
+                    record.rss_order_number = str(final_update.rss_order_number)
                 if final_update.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                     record.filled_quantity = final_update.fill_quantity
                     record.filled_price = final_update.fill_price
-                if final_update.status in {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.TIMED_OUT}:
+                if final_update.status is OrderStatus.TIMED_OUT:
+                    record.broker_observation_state = "RECONCILE_PENDING"
+                    record.last_message = final_update.message
+                    record.updated_at = self._clock()
+                elif final_update.status in {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED}:
                     record.stage_state = final_update.status.value
                 else:
                     record.stage_state = final_update.status.value
@@ -1674,13 +2323,17 @@ class ProductionRakutenRssTransport:
         with self._lock:
             age = self._clock() - record.submitted_at
             if self._timeout_seconds == 0 or age >= timedelta(seconds=self._timeout_seconds):
+                current_status = self._tracked_order_status(record)
                 timeout_update = RakutenRssOrderUpdate(
-                    status=OrderStatus.TIMED_OUT,
-                    message="Order timed out waiting for Excel/RSS result.",
+                    status=current_status,
+                    message="Order timed out waiting for Excel/RSS result; reconciliation continues.",
                     updated_at=self._clock(),
                     rss_order_status="TIMED_OUT",
+                    rss_order_id=record.rss_order_id,
+                    rss_order_number=record.rss_order_number,
+                    authoritative_rss_status=record.last_authoritative_rss_status,
                 )
-                record.stage_state = OrderStatus.TIMED_OUT.value
+                record.broker_observation_state = "RECONCILE_PENDING"
                 record.last_message = timeout_update.message
                 record.updated_at = timeout_update.updated_at
                 return (timeout_update,)
@@ -1700,7 +2353,12 @@ class ProductionRakutenRssTransport:
             return RakutenRssCancelAck(
                 status=OrderStatus.REJECTED,
                 message=f"Unknown broker_order_id: {broker_order_id}",
+                rss_order_id=0,
+                rss_order_number="",
+                authoritative_rss_status=-1,
             )
+        if record.cancel_request_id:
+            return self._tracked_cancel_ack(record)
 
         submitted_at = self._clock()
         payload = self._build_cancel_payload(record, submitted_at)
@@ -1715,6 +2373,9 @@ class ProductionRakutenRssTransport:
                 return RakutenRssCancelAck(
                     status=OrderStatus.REJECTED,
                     message=health.message,
+                    rss_order_id=record.rss_order_id,
+                    rss_order_number=record.rss_order_number,
+                    authoritative_rss_status=record.last_authoritative_rss_status,
                 )
             if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                 request_id = self._file_bridge_request_id("CANCEL", broker_order_id)
@@ -1734,10 +2395,14 @@ class ProductionRakutenRssTransport:
                         status=OrderStatus.REJECTED,
                         message=f"FILE_READY cancel staging failed: {error}",
                         canceled_at=submitted_at,
+                        rss_order_id=record.rss_order_id,
+                        rss_order_number=record.rss_order_number,
+                        authoritative_rss_status=record.last_authoritative_rss_status,
                     )
                 with self._lock:
                     record.cancel_request_id = request_id
                     record.stage_state = OrderStatus.PENDING.value
+                    record.cancel_observation_state = OrderStatus.PENDING.value
                     record.last_message = (
                         "FILE_READY cancel request staged."
                         if not bridge_result.duplicate
@@ -1748,27 +2413,107 @@ class ProductionRakutenRssTransport:
                         status=OrderStatus.PENDING,
                         message=record.last_message,
                         canceled_at=submitted_at,
+                        rss_order_id=record.rss_order_id,
+                        rss_order_number=record.rss_order_number,
+                        authoritative_rss_status=record.last_authoritative_rss_status,
                     )
             if health.transport_source != TRANSPORT_SOURCE_COM_LIVE:
                 return RakutenRssCancelAck(
                     status=OrderStatus.REJECTED,
                     message=health.message,
+                    rss_order_id=record.rss_order_id,
+                    rss_order_number=record.rss_order_number,
+                    authoritative_rss_status=record.last_authoritative_rss_status,
                 )
             session = self._ensure_session()
             self._com_call_count += 1
+            if not self._armed:
+                with self._lock:
+                    record.stage_state = OrderStatus.REJECTED.value
+                    record.last_message = "production_live_fire_armed=false; cancel staging disabled."
+                    record.updated_at = self._clock()
+                return RakutenRssCancelAck(
+                    status=OrderStatus.REJECTED,
+                    message="production_live_fire_armed=false; cancel staging disabled.",
+                    canceled_at=submitted_at,
+                    rss_order_id=record.rss_order_id,
+                    rss_order_number=record.rss_order_number,
+                    authoritative_rss_status=record.last_authoritative_rss_status,
+                )
+            ledger_entry = self._find_rss_order_ledger_entry(
+                session,
+                record.rss_order_id,
+                function_name=ORDER_MACRO_NAME,
+            )
+            order_number = record.rss_order_number or (ledger_entry.order_number if ledger_entry is not None else "")
+            if not str(order_number).strip():
+                with self._lock:
+                    record.cancel_observation_state = "WAITING_FOR_ORDER_NUMBER"
+                    record.last_message = "RSS order number is missing for cancel."
+                    record.updated_at = self._clock()
+                return self._tracked_cancel_ack(record, message="RSS order number is missing for cancel.")
             self._backend.stage_cancel_payload(session, payload)
-            if self._armed:
-                self._com_call_count += 1
-                self._cancel_macro_call_count += 1
-                self._backend.invoke_cancel_macro(session, CANCEL_MACRO_NAME)
+            cancel_args = self._build_rss_cancel_order_arguments(record.rss_order_id, order_number)
+            self._com_call_count += 1
+            self._cancel_macro_call_count += 1
+            self._backend.invoke_cancel_macro(session, CANCEL_MACRO_NAME, *cancel_args)
+            try:
+                rss_order_status = self._observe_rss_order_status(session, record.rss_order_id)
+            except ExcelComError:
+                rss_order_status = -1
             with self._lock:
-                record.stage_state = OrderStatus.CANCELED.value
-                record.last_message = "Cancel staged."
+                record.rss_order_number = order_number
+                record.rss_order_status_code = rss_order_status
+                record.last_authoritative_rss_status = rss_order_status
+                if rss_order_status == 3:
+                    record.stage_state = OrderStatus.FILLED.value
+                    record.cancel_observation_state = OrderStatus.FILLED.value
+                    record.last_message = "RssOrderStatus=3"
+                    record.updated_at = self._clock()
+                    return RakutenRssCancelAck(
+                        status=OrderStatus.FILLED,
+                        message="RssOrderStatus=3",
+                        canceled_at=submitted_at,
+                        rss_order_id=record.rss_order_id,
+                        rss_order_number=record.rss_order_number,
+                        authoritative_rss_status=record.last_authoritative_rss_status,
+                    )
+                normalized_order_result = self._rss_optional_text(
+                    ledger_entry.result if ledger_entry is not None else "",
+                ).replace("(", "（").replace(")", "）")
+                cancel_completed_results = {
+                    "取消済（出来有）",
+                    "取消済（出来無）",
+                    "取消済",
+                }
+                if rss_order_status == 1 and normalized_order_result in cancel_completed_results:
+                    record.stage_state = OrderStatus.CANCELED.value
+                    record.cancel_observation_state = OrderStatus.CANCELED.value
+                    record.last_message = normalized_order_result
+                    record.updated_at = self._clock()
+                    return RakutenRssCancelAck(
+                        status=OrderStatus.CANCELED,
+                        message=normalized_order_result,
+                        canceled_at=submitted_at,
+                        rss_order_id=record.rss_order_id,
+                        rss_order_number=record.rss_order_number,
+                        authoritative_rss_status=record.last_authoritative_rss_status,
+                    )
+                record.stage_state = OrderStatus.PENDING.value
+                record.cancel_observation_state = OrderStatus.PENDING.value
+                record.last_message = (
+                    normalized_order_result
+                    if normalized_order_result in {"出来ず（出来有）", "出来ず（出来無）"}
+                    else "Cancel request observed but order status is still terminal-free."
+                )
                 record.updated_at = self._clock()
             return RakutenRssCancelAck(
-                status=OrderStatus.CANCELED,
-                message="Cancel staged." if not self._armed else "RssCancelOrder_V invoked.",
+                status=OrderStatus.PENDING,
+                message=record.last_message,
                 canceled_at=submitted_at,
+                rss_order_id=record.rss_order_id,
+                rss_order_number=record.rss_order_number,
+                authoritative_rss_status=record.last_authoritative_rss_status,
             )
         except ExcelComError as error:
             with self._lock:
@@ -1779,4 +2524,7 @@ class ProductionRakutenRssTransport:
                 status=OrderStatus.REJECTED,
                 message=str(error),
                 canceled_at=submitted_at,
+                rss_order_id=record.rss_order_id,
+                rss_order_number=record.rss_order_number,
+                authoritative_rss_status=record.last_authoritative_rss_status,
             )
diff --git a/phoenix_core/rakuten_rss_adapter.py b/phoenix_core/rakuten_rss_adapter.py
index 38bf2f7..85dd73d 100644
--- a/phoenix_core/rakuten_rss_adapter.py
+++ b/phoenix_core/rakuten_rss_adapter.py
@@ -28,6 +28,9 @@ class RakutenRssSubmitAck:
     status: OrderStatus
     message: str
     submitted_at: datetime = field(default_factory=_now_jst)
+    rss_order_id: int = 0
+    rss_order_number: str = ""
+    authoritative_rss_status: int = -1
 
 
 @dataclass(frozen=True, slots=True)
@@ -38,6 +41,9 @@ class RakutenRssOrderUpdate:
     message: str = ""
     updated_at: datetime = field(default_factory=_now_jst)
     rss_order_status: str = ""
+    rss_order_id: int = 0
+    rss_order_number: str = ""
+    authoritative_rss_status: int = -1
 
 
 @dataclass(frozen=True, slots=True)
@@ -45,6 +51,9 @@ class RakutenRssCancelAck:
     status: OrderStatus
     message: str
     canceled_at: datetime = field(default_factory=_now_jst)
+    rss_order_id: int = 0
+    rss_order_number: str = ""
+    authoritative_rss_status: int = -1
 
 
 class RakutenRssAdapter(Protocol):
@@ -74,6 +83,10 @@ class _MockScript:
     cancel_message: str = "MOCK_CANCELED"
     updates: list[RakutenRssOrderUpdate] = field(default_factory=list)
     broker_order_id: str = ""
+    rss_order_id: int = 0
+    rss_order_number: str = ""
+    submit_authoritative_rss_status: int = -1
+    cancel_authoritative_rss_status: int = -1
 
 
 class MockRakutenRssAdapter(RakutenRssAdapter):
@@ -122,6 +135,10 @@ class MockRakutenRssAdapter(RakutenRssAdapter):
         submit_message: str = "MOCK_ACCEPTED",
         cancel_status: OrderStatus = OrderStatus.CANCELED,
         cancel_message: str = "MOCK_CANCELED",
+        rss_order_id: int = 0,
+        rss_order_number: str = "",
+        submit_authoritative_rss_status: int = -1,
+        cancel_authoritative_rss_status: int = -1,
         updates: list[RakutenRssOrderUpdate] | None = None,
     ) -> None:
         script = self._scripts_by_client_order_id.get(client_order_id)
@@ -132,6 +149,10 @@ class MockRakutenRssAdapter(RakutenRssAdapter):
         script.submit_message = submit_message
         script.cancel_status = cancel_status
         script.cancel_message = cancel_message
+        script.rss_order_id = int(rss_order_id)
+        script.rss_order_number = str(rss_order_number)
+        script.submit_authoritative_rss_status = int(submit_authoritative_rss_status)
+        script.cancel_authoritative_rss_status = int(cancel_authoritative_rss_status)
         if updates is not None:
             script.updates = list(updates)
 
@@ -144,6 +165,9 @@ class MockRakutenRssAdapter(RakutenRssAdapter):
         fill_price: float = 0.0,
         message: str = "",
         rss_order_status: str = "",
+        rss_order_id: int = 0,
+        rss_order_number: str = "",
+        authoritative_rss_status: int = -1,
     ) -> None:
         script = self._scripts_by_client_order_id.get(client_order_id)
         if script is None:
@@ -156,6 +180,9 @@ class MockRakutenRssAdapter(RakutenRssAdapter):
                 fill_price=fill_price,
                 message=message,
                 rss_order_status=rss_order_status,
+                rss_order_id=int(rss_order_id),
+                rss_order_number=str(rss_order_number),
+                authoritative_rss_status=int(authoritative_rss_status),
             )
         )
 
@@ -185,12 +212,18 @@ class MockRakutenRssAdapter(RakutenRssAdapter):
                 "side": order.side.value,
                 "quantity": order.quantity,
                 "limit_price": order.limit_price,
+                "rss_order_id": script.rss_order_id,
+                "rss_order_number": script.rss_order_number,
+                "authoritative_rss_status": script.submit_authoritative_rss_status,
                 "submitted_at": _now_jst().isoformat(timespec="seconds"),
             }
         )
         return RakutenRssSubmitAck(
             status=script.submit_status,
             message=script.submit_message,
+            rss_order_id=script.rss_order_id,
+            rss_order_number=script.rss_order_number,
+            authoritative_rss_status=script.submit_authoritative_rss_status,
         )
 
     def poll_order(
@@ -215,4 +248,7 @@ class MockRakutenRssAdapter(RakutenRssAdapter):
         return RakutenRssCancelAck(
             status=script.cancel_status,
             message=script.cancel_message,
+            rss_order_id=script.rss_order_id,
+            rss_order_number=script.rss_order_number,
+            authoritative_rss_status=script.cancel_authoritative_rss_status,
         )
diff --git a/phoenix_core/rakuten_rss_broker.py b/phoenix_core/rakuten_rss_broker.py
index b888866..36b573b 100644
--- a/phoenix_core/rakuten_rss_broker.py
+++ b/phoenix_core/rakuten_rss_broker.py
@@ -36,7 +36,6 @@ FINAL_STATUSES = {
     OrderStatus.FILLED,
     OrderStatus.REJECTED,
     OrderStatus.CANCELED,
-    OrderStatus.TIMED_OUT,
 }
 
 
@@ -77,6 +76,28 @@ def _canonical_event_sha256(event: dict[str, Any]) -> str:
     return hashlib.sha256(encoded).hexdigest()
 
 
+def _optional_int(value: Any, default: int = -1) -> int:
+    try:
+        if value is None or value == "":
+            return default
+        result = int(value)
+        if result == 0 and default != 0:
+            return default
+        return result
+    except Exception:
+        return default
+
+
+def _optional_text(value: Any, default: str = "") -> str:
+    text = "" if value is None else str(value).strip()
+    return text if text else default
+
+
+def _stable_rss_order_id(client_order_id: str, broker_order_id: str) -> int:
+    digest = hashlib.sha256(f"{client_order_id}|{broker_order_id}".encode("utf-8")).hexdigest()
+    return max(1, int(digest[:8], 16) % 2147483647)
+
+
 @dataclass(slots=True)
 class _MutablePosition:
     quantity: int
@@ -257,6 +278,7 @@ class RakutenRssBroker(BrokerAdapter):
                 return self._record_rejected(order=order, ticker=ticker, message=reason)
 
             broker_order_id = f"RSS-{uuid4().hex[:16].upper()}"
+            rss_order_id = _stable_rss_order_id(order.client_order_id, broker_order_id)
             submitted_at = _now_jst()
             try:
                 ack = self._adapter.submit_order(order, broker_order_id)
@@ -267,6 +289,8 @@ class RakutenRssBroker(BrokerAdapter):
                     message=f"Rakuten RSS adapter submit failed: {error}",
                     broker_order_id=broker_order_id,
                     submitted_at=submitted_at,
+                    rss_order_id=rss_order_id,
+                    authoritative_rss_status=-1,
                 )
 
             if ack.status is OrderStatus.REJECTED:
@@ -276,10 +300,23 @@ class RakutenRssBroker(BrokerAdapter):
                     message=ack.message or "Rakuten RSS adapter rejected the order",
                     broker_order_id=broker_order_id,
                     submitted_at=submitted_at,
+                    rss_order_id=_optional_int(getattr(ack, "rss_order_id", rss_order_id), rss_order_id),
+                    rss_order_number=_optional_text(getattr(ack, "rss_order_number", "")),
+                    authoritative_rss_status=_optional_int(
+                        getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
+                        -1,
+                    ),
                 )
             if ack.status not in {OrderStatus.PENDING, OrderStatus.ACCEPTED}:
                 raise ValueError("Rakuten RSS submit ack must be PENDING, ACCEPTED or REJECTED")
 
+            rss_order_id = _optional_int(getattr(ack, "rss_order_id", rss_order_id), rss_order_id)
+            rss_order_number = _optional_text(getattr(ack, "rss_order_number", ""))
+            authoritative_rss_status = _optional_int(
+                getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
+                -1,
+            )
+
             record = self._new_record(
                 order=order,
                 ticker=ticker,
@@ -295,6 +332,11 @@ class RakutenRssBroker(BrokerAdapter):
                 ),
                 submitted_at=submitted_at,
                 updated_at=ack.submitted_at,
+                rss_order_id=rss_order_id,
+                rss_order_number=rss_order_number,
+                broker_observation_state=ack.status.value,
+                cancel_observation_state="",
+                last_authoritative_rss_status=authoritative_rss_status,
             )
             self._orders[order.client_order_id] = record
             self._save_state()
@@ -343,19 +385,18 @@ class RakutenRssBroker(BrokerAdapter):
                     continue
                 submitted_at = _parse_iso(str(record["submitted_at"]))
                 age = checked_at - submitted_at
+                observed_status = _optional_text(record.get("broker_observation_state"))
+                last_authoritative_status = _optional_int(record.get("last_authoritative_rss_status", -1), -1)
+                if observed_status == OrderStatus.ACCEPTED.value or last_authoritative_status == 2:
+                    continue
                 if self._timeout_seconds == 0 or age >= timedelta(seconds=self._timeout_seconds):
-                    if _phoenix_timeout_protective_order(self, record, checked_at):
-                        changed = True
-                    try:
-                        self._adapter.cancel_order(broker_order_id)
-                    except Exception:
-                        pass
-                    result = self._finalize_record(
-                        record,
-                        status=OrderStatus.TIMED_OUT,
-                        message=record.get("message", "Rakuten RSS order timed out"),
-                        updated_at=checked_at,
+                    if record.get("broker_observation_state") != "RECONCILE_PENDING":
+                        record["broker_observation_state"] = "RECONCILE_PENDING"
+                    record["message"] = (
+                        "Rakuten RSS order timed out waiting for observation; reconciliation continues."
                     )
+                    record["updated_at"] = _iso(checked_at)
+                    result = self._result_from_record(record)
                     results.append(result)
                     changed = True
 
@@ -378,23 +419,61 @@ class RakutenRssBroker(BrokerAdapter):
                 raise ValueError(f"client_order_idが見つかりません: {client_order_id}")
             if OrderStatus(record["status"]) in FINAL_STATUSES:
                 return self._result_from_record(record)
+            if not _optional_text(record.get("rss_order_number")):
+                record["cancel_observation_state"] = "WAITING_FOR_ORDER_NUMBER"
+                record["message"] = message or "RSS order number is missing for cancel."
+                record["updated_at"] = _iso(_now_jst())
+                self._save_state()
+                return self._result_from_record(record)
             try:
                 ack = self._adapter.cancel_order(str(record["broker_order_id"]))
             except Exception as error:  # pragma: no cover - adapter failure is fail-closed
                 self.engage_kill_switch(f"Rakuten RSS cancel failed: {error}")
                 return self._result_from_record(record)
+            candidate_rss_order_id = _optional_int(
+                getattr(ack, "rss_order_id", record.get("rss_order_id", 0)),
+                record.get("rss_order_id", 0),
+            )
+            if candidate_rss_order_id > 0:
+                record["rss_order_id"] = candidate_rss_order_id
+            record["rss_order_number"] = _optional_text(
+                getattr(ack, "rss_order_number", record.get("rss_order_number", "")),
+                record.get("rss_order_number", ""),
+            )
+            authoritative_rss_status = _optional_int(
+                getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
+                -1,
+            )
+            if authoritative_rss_status != -1:
+                record["last_authoritative_rss_status"] = authoritative_rss_status
             if ack.status is OrderStatus.PENDING:
                 record["status"] = OrderStatus.PENDING.value
                 record["message"] = message or ack.message or "Rakuten RSS cancel staged and awaiting VBA receipt"
                 record["updated_at"] = _iso(ack.canceled_at)
+                record["cancel_observation_state"] = OrderStatus.PENDING.value
                 self._save_state()
                 return self._result_from_record(record)
-            result = self._finalize_record(
-                record,
-                status=ack.status if ack.status in FINAL_STATUSES else OrderStatus.CANCELED,
-                message=message or ack.message or "Rakuten RSS order canceled",
-                updated_at=ack.canceled_at,
-            )
+            if ack.status is OrderStatus.CANCELED:
+                record["cancel_observation_state"] = OrderStatus.CANCELED.value
+                result = self._finalize_record(
+                    record,
+                    status=OrderStatus.CANCELED,
+                    message=message or ack.message or "Rakuten RSS order canceled",
+                    updated_at=ack.canceled_at,
+                )
+            elif ack.status is OrderStatus.FILLED:
+                record["cancel_observation_state"] = OrderStatus.FILLED.value
+                result = self._finalize_record(
+                    record,
+                    status=OrderStatus.FILLED,
+                    message=message or ack.message or "Rakuten RSS order filled before cancel",
+                    updated_at=ack.canceled_at,
+                )
+            else:
+                record["cancel_observation_state"] = "RECONCILE_PENDING"
+                record["message"] = message or ack.message or "Rakuten RSS cancel pending reconciliation"
+                record["updated_at"] = _iso(ack.canceled_at)
+                result = self._result_from_record(record)
             self._save_state()
             return result
 
@@ -463,6 +542,11 @@ class RakutenRssBroker(BrokerAdapter):
         message: str,
         submitted_at: datetime,
         updated_at: datetime,
+        rss_order_id: int = 0,
+        rss_order_number: str = "",
+        broker_observation_state: str | None = None,
+        cancel_observation_state: str = "",
+        last_authoritative_rss_status: int = -1,
     ) -> dict[str, Any]:
         return {
             "client_order_id": order.client_order_id,
@@ -475,6 +559,14 @@ class RakutenRssBroker(BrokerAdapter):
             "message": message,
             "submitted_at": _iso(submitted_at),
             "updated_at": _iso(updated_at),
+            "rss_order_id": int(rss_order_id),
+            "rss_order_number": _optional_text(rss_order_number),
+            "broker_observation_state": _optional_text(
+                broker_observation_state,
+                default=status.value,
+            ),
+            "cancel_observation_state": _optional_text(cancel_observation_state),
+            "last_authoritative_rss_status": int(last_authoritative_rss_status),
             "filled_quantity": 0,
             "filled_notional_yen": 0.0,
             "filled_price": 0.0,
@@ -498,6 +590,9 @@ class RakutenRssBroker(BrokerAdapter):
         message: str,
         broker_order_id: str | None = None,
         submitted_at: datetime | None = None,
+        rss_order_id: int = 0,
+        rss_order_number: str = "",
+        authoritative_rss_status: int = -1,
     ) -> OrderResult:
         now = submitted_at or _now_jst()
         record = self._new_record(
@@ -508,6 +603,11 @@ class RakutenRssBroker(BrokerAdapter):
             message=message,
             submitted_at=now,
             updated_at=now,
+            rss_order_id=rss_order_id,
+            rss_order_number=rss_order_number,
+            broker_observation_state=OrderStatus.REJECTED.value,
+            cancel_observation_state="",
+            last_authoritative_rss_status=authoritative_rss_status,
         )
         self._orders[order.client_order_id] = record
         self._save_state()
@@ -519,10 +619,25 @@ class RakutenRssBroker(BrokerAdapter):
         update: RakutenRssOrderUpdate,
     ) -> OrderResult:
         status = update.status
+        update_rss_order_id = _optional_int(getattr(update, "rss_order_id", 0), 0)
+        update_rss_order_number = _optional_text(getattr(update, "rss_order_number", ""))
+        update_authoritative_rss_status = _optional_int(
+            getattr(update, "authoritative_rss_status", getattr(update, "rss_order_status", -1)),
+            -1,
+        )
+        if update_rss_order_id > 0:
+            record["rss_order_id"] = update_rss_order_id
+        if update_rss_order_number:
+            record["rss_order_number"] = update_rss_order_number
+        if update_authoritative_rss_status != -1:
+            record["last_authoritative_rss_status"] = update_authoritative_rss_status
+        if _optional_text(getattr(update, "rss_order_status", "")):
+            record["broker_observation_state"] = _optional_text(getattr(update, "rss_order_status", ""))
         if status is OrderStatus.ACCEPTED:
             record["status"] = status.value
             record["message"] = update.message or record["message"]
             record["updated_at"] = _iso(update.updated_at)
+            record["broker_observation_state"] = status.value
             return self._result_from_record(record)
         if status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
             if update.fill_quantity <= 0:
@@ -535,7 +650,12 @@ class RakutenRssBroker(BrokerAdapter):
                 message=update.message,
                 updated_at=update.updated_at,
             )
-        if status in {OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.TIMED_OUT}:
+        if status is OrderStatus.TIMED_OUT:
+            record["message"] = update.message or "Order timed out waiting for Excel/RSS result; reconciliation continues."
+            record["updated_at"] = _iso(update.updated_at)
+            record["broker_observation_state"] = "RECONCILE_PENDING"
+            return self._result_from_record(record)
+        if status in {OrderStatus.REJECTED, OrderStatus.CANCELED}:
             return self._finalize_record(
                 record,
                 status=status,
@@ -929,6 +1049,11 @@ class RakutenRssBroker(BrokerAdapter):
                 raise ValueError("order recordはJSONオブジェクトにしてください")
             record = dict(value)
             record.setdefault("client_order_id", client_order_id)
+            record.setdefault("rss_order_id", 0)
+            record.setdefault("rss_order_number", "")
+            record.setdefault("broker_observation_state", str(record.get("status", OrderStatus.PENDING.value)))
+            record.setdefault("cancel_observation_state", "")
+            record.setdefault("last_authoritative_rss_status", -1)
             self._orders[str(client_order_id)] = record
 
         fill_events = payload.get("fill_events", [])
diff --git a/tests/test_v7_step49.py b/tests/test_v7_step49.py
index 82f5d03..aa89457 100644
--- a/tests/test_v7_step49.py
+++ b/tests/test_v7_step49.py
@@ -12,10 +12,12 @@ from zoneinfo import ZoneInfo
 
 from phoenix_core import (
     MockExcelComBackend,
+    MockRakutenRssAdapter,
     OrderRequest,
     OrderSide,
     OrderStatus,
     OrderType,
+    RakutenRssBroker,
     ProductionRakutenRssAdapter,
     ProductionRakutenRssTransport,
     RakutenRssAdapterHealth,
@@ -24,6 +26,7 @@ from phoenix_core import (
     RakutenRssSubmitAck,
     RakutenRssTransportHealth,
 )
+import phoenix_core.order_bridge_gate as order_bridge_gate
 from phoenix_core.production_rakuten_rss_transport import (
     DEFAULT_WORKBOOK_PATH,
     ExcelComError,
@@ -32,6 +35,7 @@ from phoenix_core.production_rakuten_rss_transport import (
     WORKBOOK_STATE_HEARTBEAT_CELL,
     WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL,
     WORKBOOK_STATE_RSS_CONNECTED_CELL,
+    TRANSPORT_SOURCE_COM_LIVE,
     TRANSPORT_SOURCE_FILE_READY,
     TRANSPORT_SOURCE_FILE_FALLBACK,
     Win32ComExcelBackend,
@@ -95,6 +99,31 @@ def _protective_sell_order(client_order_id: str) -> OrderRequest:
     )
 
 
+def _live_buy_order(
+    client_order_id: str,
+    *,
+    quantity: int = 100,
+    limit_price: float = 123.45,
+    account_category: str = "特定",
+    sor_category: str = "通常",
+    execution_condition: str = "本日中",
+) -> OrderRequest:
+    return OrderRequest(
+        ticker="1301.T",
+        side=OrderSide.BUY,
+        quantity=quantity,
+        order_type=OrderType.LIMIT,
+        limit_price=limit_price,
+        client_order_id=client_order_id,
+        strategy_name="PHOENIX_AUTO_LIVE",
+        metadata={
+            "account_category": account_category,
+            "sor_category": sor_category,
+            "execution_condition": execution_condition,
+        },
+    )
+
+
 def _bootstrap_repo_root(root: Path) -> Path:
     repo_root = Path(__file__).resolve().parents[1]
     (root / "runtime" / "v7_rss_production").mkdir(parents=True, exist_ok=True)
@@ -2106,7 +2135,7 @@ class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
         result = transport.submit_order(_buy_order("ARMED-OFF"), "RSS-ARMED-OFF")
 
         self.assertEqual(OrderStatus.REJECTED, result.status)
-        self.assertIn("submit staging disabled", result.message)
+        self.assertIn("RssStockOrder_V not called", result.message)
         self.assertEqual(1, backend.connect_calls)
         self.assertEqual(1, backend.health_calls)
         self.assertEqual(0, backend.submit_stage_calls)
@@ -2114,6 +2143,220 @@ class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
         self.assertEqual(0, transport.order_function_call_count)
         self.assertEqual(0, len(backend.submitted_payloads))
 
+    def test_live_submit_requires_order_number_and_status_observation(self) -> None:
+        pending_backend = MockExcelComBackend()
+        pending_transport = ProductionRakutenRssTransport(
+            live_trading_enabled=True,
+            production_transport_enabled=True,
+            armed=True,
+            backend=pending_backend,
+        )
+        pending_order = _live_buy_order("LIVE-PENDING-001")
+        pending_health = RakutenRssTransportHealth(
+            connected=True,
+            message="Workbook transport READY.",
+            transport_source=TRANSPORT_SOURCE_COM_LIVE,
+        )
+
+        with mock.patch.object(pending_transport, "health_check", return_value=pending_health):
+            pending_ack = pending_transport.submit_order(pending_order, "RSS-LIVE-PENDING-001")
+
+        self.assertEqual(OrderStatus.PENDING, pending_ack.status)
+        self.assertEqual(
+            pending_transport._stable_rss_order_id(pending_order, "RSS-LIVE-PENDING-001"),
+            pending_ack.rss_order_id,
+        )
+        self.assertEqual("", pending_ack.rss_order_number)
+        self.assertEqual(-1, pending_ack.authoritative_rss_status)
+        self.assertEqual(1, pending_backend.submit_macro_calls)
+        self.assertEqual(1, pending_backend.rss_order_ledger_calls)
+        self.assertEqual(1, pending_backend.rss_order_status_calls)
+        self.assertEqual(19, len(pending_backend.submit_macro_args[0]))
+        self.assertEqual(
+            pending_transport._stable_rss_order_id(pending_order, "RSS-LIVE-PENDING-001"),
+            pending_backend.submit_macro_args[0][0],
+        )
+
+        accepted_backend = MockExcelComBackend()
+        accepted_transport = ProductionRakutenRssTransport(
+            live_trading_enabled=True,
+            production_transport_enabled=True,
+            armed=True,
+            backend=accepted_backend,
+        )
+        accepted_order = _live_buy_order("LIVE-ACCEPTED-001")
+        accepted_rss_order_id = accepted_transport._stable_rss_order_id(accepted_order, "RSS-LIVE-ACCEPTED-001")
+        accepted_backend.queue_rss_order_ledger_entry(
+            accepted_rss_order_id,
+            function_name="RssStockOrder_V",
+            order_number="RSS-LIVE-ACCEPTED-001",
+            result="ACCEPTED",
+        )
+        accepted_backend.set_rss_order_status(accepted_rss_order_id, 2)
+
+        with mock.patch.object(accepted_transport, "health_check", return_value=pending_health):
+            accepted_ack = accepted_transport.submit_order(accepted_order, "RSS-LIVE-ACCEPTED-001")
+
+        self.assertEqual(OrderStatus.ACCEPTED, accepted_ack.status)
+        self.assertEqual("ACCEPTED", accepted_ack.message)
+        self.assertEqual(accepted_rss_order_id, accepted_ack.rss_order_id)
+        self.assertEqual("RSS-LIVE-ACCEPTED-001", accepted_ack.rss_order_number)
+        self.assertEqual(2, accepted_ack.authoritative_rss_status)
+        self.assertEqual(1, accepted_backend.submit_macro_calls)
+        self.assertEqual(1, accepted_backend.rss_order_ledger_calls)
+        self.assertEqual(1, accepted_backend.rss_order_status_calls)
+        self.assertEqual(
+            (
+                accepted_rss_order_id,
+                "1301.T",
+                3,
+                0,
+                0,
+                100,
+                1,
+                123.45,
+                1,
+                "",
+                0,
+                "",
+                "",
+                "",
+                "",
+                "",
+                "",
+                "",
+                "",
+            ),
+            accepted_backend.submit_macro_args[0],
+        )
+
+    def test_timeout_blocks_duplicate_submit(self) -> None:
+        backend = MockExcelComBackend()
+        transport = ProductionRakutenRssTransport(
+            live_trading_enabled=True,
+            production_transport_enabled=True,
+            armed=True,
+            timeout_seconds=0,
+            backend=backend,
+        )
+        order = _live_buy_order("TIMEOUT-001")
+        health = RakutenRssTransportHealth(
+            connected=True,
+            message="Workbook transport READY.",
+            transport_source=TRANSPORT_SOURCE_COM_LIVE,
+        )
+
+        with mock.patch.object(transport, "health_check", return_value=health):
+            first_ack = transport.submit_order(order, "RSS-TIMEOUT-001")
+            updates = transport.poll_order("RSS-TIMEOUT-001")
+            second_ack = transport.submit_order(order, "RSS-TIMEOUT-001")
+
+        self.assertEqual(OrderStatus.PENDING, first_ack.status)
+        self.assertEqual(1, len(updates))
+        self.assertEqual(OrderStatus.PENDING, updates[0].status)
+        self.assertIn("reconciliation continues", updates[0].message.lower())
+        self.assertEqual(OrderStatus.PENDING, second_ack.status)
+        self.assertEqual(1, backend.submit_macro_calls)
+        self.assertEqual(2, backend.rss_order_status_calls)
+
+    def test_broker_restart_reuses_persisted_rss_identity(self) -> None:
+        adapter = MockRakutenRssAdapter()
+        adapter.script_order(
+            "BROKER-RESTART-001",
+            submit_status=OrderStatus.PENDING,
+            submit_message="MOCK_PENDING",
+            cancel_status=OrderStatus.CANCELED,
+            cancel_message="MOCK_CANCELED",
+            rss_order_id=24680,
+            rss_order_number="",
+            submit_authoritative_rss_status=-1,
+            cancel_authoritative_rss_status=1,
+        )
+
+        with tempfile.TemporaryDirectory() as tmpdir:
+            state_file = Path(tmpdir) / "rakuten_rss_broker_state.json"
+            order = _live_buy_order("BROKER-RESTART-001")
+
+            broker_a = RakutenRssBroker(
+                initial_cash_yen=300_000.0,
+                state_file=state_file,
+                adapter=adapter,
+                live_enabled=True,
+                timeout_seconds=0,
+            )
+            first_result = broker_a.submit_order(order)
+            first_record = dict(broker_a._orders[order.client_order_id])
+            broker_order_id = first_record["broker_order_id"]
+
+            del broker_a
+
+            broker_b = RakutenRssBroker(
+                initial_cash_yen=300_000.0,
+                state_file=state_file,
+                adapter=adapter,
+                live_enabled=True,
+                timeout_seconds=0,
+            )
+            second_result = broker_b.submit_order(order)
+            timeout_results = broker_b.refresh_pending_orders()
+            timeout_record = dict(broker_b._orders[order.client_order_id])
+
+            adapter.queue_update(
+                "BROKER-RESTART-001",
+                status=OrderStatus.ACCEPTED,
+                message="MOCK_ACCEPTED",
+                rss_order_status="2",
+                rss_order_id=24680,
+                rss_order_number="RSS-ORDER-777",
+                authoritative_rss_status=2,
+            )
+            reconciliation_results = broker_b.refresh_pending_orders()
+            accepted_record = dict(broker_b._orders[order.client_order_id])
+            cancel_result = broker_b.cancel_order(order.client_order_id)
+
+            second_record = broker_b._orders[order.client_order_id]
+
+        self.assertEqual(OrderStatus.PENDING, first_result.status)
+        self.assertEqual("PENDING", first_record["broker_observation_state"])
+        self.assertEqual(OrderStatus.PENDING, second_result.status)
+        self.assertEqual(1, adapter.submitted_count)
+        self.assertEqual(broker_order_id, second_record["broker_order_id"])
+        self.assertEqual(24680, second_record["rss_order_id"])
+        self.assertEqual("RSS-ORDER-777", second_record["rss_order_number"])
+        self.assertEqual(OrderStatus.PENDING, timeout_results[0].status)
+        self.assertIn("reconciliation continues", timeout_results[0].message.lower())
+        self.assertEqual("RECONCILE_PENDING", timeout_record["broker_observation_state"])
+        self.assertEqual(OrderStatus.ACCEPTED, reconciliation_results[-1].status)
+        self.assertEqual("RSS-ORDER-777", accepted_record["rss_order_number"])
+        self.assertEqual("ACCEPTED", accepted_record["broker_observation_state"])
+        self.assertEqual(OrderStatus.CANCELED, cancel_result.status)
+        self.assertEqual("CANCELED", second_record["cancel_observation_state"])
+        self.assertEqual("RSS-ORDER-777", second_record["rss_order_number"])
+
+    def test_cancel_requires_saved_order_number(self) -> None:
+        backend = MockExcelComBackend()
+        transport = ProductionRakutenRssTransport(
+            live_trading_enabled=True,
+            production_transport_enabled=True,
+            armed=True,
+            backend=backend,
+        )
+        order = _live_buy_order("CANCEL-NO-ORDER")
+        health = RakutenRssTransportHealth(
+            connected=True,
+            message="Workbook transport READY.",
+            transport_source=TRANSPORT_SOURCE_COM_LIVE,
+        )
+
+        with mock.patch.object(transport, "health_check", return_value=health):
+            transport.submit_order(order, "RSS-CANCEL-NO-ORDER")
+            ack = transport.cancel_order("RSS-CANCEL-NO-ORDER")
+
+        self.assertEqual(OrderStatus.PENDING, ack.status)
+        self.assertIn("RSS order number is missing for cancel", ack.message)
+        self.assertEqual(1, backend.submit_macro_calls)
+        self.assertEqual(0, backend.cancel_macro_calls)
+
     def test_mock_com_payload_mapping(self) -> None:
         backend = MockExcelComBackend()
         transport = ProductionRakutenRssTransport(
@@ -2186,6 +2429,7 @@ class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
 
     def test_poll_mapping(self) -> None:
         backend = MockExcelComBackend()
+        order = _live_buy_order("POLL-001")
         backend.queue_updates(
             "RSS-POLL-001",
             [
@@ -2209,7 +2453,14 @@ class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
             armed=True,
             backend=backend,
         )
-        transport.submit_order(_buy_order("POLL-001"), "RSS-POLL-001")
+        health = RakutenRssTransportHealth(
+            connected=True,
+            message="Workbook transport READY.",
+            transport_source=TRANSPORT_SOURCE_COM_LIVE,
+        )
+
+        with mock.patch.object(transport, "health_check", return_value=health):
+            transport.submit_order(order, "RSS-POLL-001")
 
         updates = transport.poll_order("RSS-POLL-001")
 
@@ -2229,11 +2480,28 @@ class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
             armed=True,
             backend=backend,
         )
-        transport.submit_order(_buy_order("CANCEL-001"), "RSS-CANCEL-001")
+        order = _live_buy_order("CANCEL-001")
+        rss_order_id = transport._stable_rss_order_id(order, "RSS-CANCEL-001")
+        backend.queue_rss_order_ledger_entry(
+            rss_order_id,
+            function_name="RssStockOrder_V",
+            order_number="RSS-CANCEL-001",
+            result="取消済（出来無）",
+        )
+        backend.set_rss_order_status(rss_order_id, 2)
+        health = RakutenRssTransportHealth(
+            connected=True,
+            message="Workbook transport READY.",
+            transport_source=TRANSPORT_SOURCE_COM_LIVE,
+        )
 
-        ack = transport.cancel_order("RSS-CANCEL-001")
+        with mock.patch.object(transport, "health_check", return_value=health):
+            submit_ack = transport.submit_order(order, "RSS-CANCEL-001")
+            backend.set_rss_order_status(rss_order_id, 1)
+            ack = transport.cancel_order("RSS-CANCEL-001")
         payload = backend.cancel_payloads[0]
 
+        self.assertEqual(OrderStatus.ACCEPTED, submit_ack.status)
         self.assertEqual(OrderStatus.CANCELED, ack.status)
         self.assertEqual(1, backend.cancel_stage_calls)
         self.assertEqual(1, backend.cancel_macro_calls)
@@ -2242,6 +2510,220 @@ class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
         self.assertEqual("CANCEL-001", payload["client_order_id"])
         self.assertEqual("RssCancelOrder_V", payload["macro_name"])
 
+        failed_backend = MockExcelComBackend()
+        failed_transport = ProductionRakutenRssTransport(
+            live_trading_enabled=True,
+            production_transport_enabled=True,
+            armed=True,
+            backend=failed_backend,
+        )
+        failed_order = _live_buy_order("CANCEL-FAIL-001")
+        failed_rss_order_id = failed_transport._stable_rss_order_id(failed_order, "RSS-CANCEL-FAIL-001")
+        failed_backend.queue_rss_order_ledger_entry(
+            failed_rss_order_id,
+            function_name="RssStockOrder_V",
+            order_number="RSS-CANCEL-FAIL-001",
+            result="出来ず（出来無）",
+        )
+        failed_backend.set_rss_order_status(failed_rss_order_id, 2)
+
+        with mock.patch.object(failed_transport, "health_check", return_value=health):
+            failed_submit_ack = failed_transport.submit_order(failed_order, "RSS-CANCEL-FAIL-001")
+            failed_backend.set_rss_order_status(failed_rss_order_id, 1)
+            failed_ack = failed_transport.cancel_order("RSS-CANCEL-FAIL-001")
+
+        self.assertEqual(OrderStatus.ACCEPTED, failed_submit_ack.status)
+        self.assertEqual(OrderStatus.PENDING, failed_ack.status)
+        self.assertEqual(1, failed_backend.cancel_macro_calls)
+        self.assertEqual("出来ず（出来無）", failed_ack.message)
+
+    def test_cancel_reports_filled_when_order_status_is_three(self) -> None:
+        backend = MockExcelComBackend()
+        transport = ProductionRakutenRssTransport(
+            live_trading_enabled=True,
+            production_transport_enabled=True,
+            armed=True,
+            backend=backend,
+        )
+        order = _live_buy_order("CANCEL-FILLED-001")
+        rss_order_id = transport._stable_rss_order_id(order, "RSS-CANCEL-FILLED-001")
+        backend.queue_rss_order_ledger_entry(
+            rss_order_id,
+            function_name="RssStockOrder_V",
+            order_number="RSS-CANCEL-FILLED-001",
+            result="ACCEPTED",
+        )
+        backend.set_rss_order_status(rss_order_id, 2)
+        health = RakutenRssTransportHealth(
+            connected=True,
+            message="Workbook transport READY.",
+            transport_source=TRANSPORT_SOURCE_COM_LIVE,
+        )
+
+        with mock.patch.object(transport, "health_check", return_value=health):
+            submit_ack = transport.submit_order(order, "RSS-CANCEL-FILLED-001")
+            backend.set_rss_order_status(rss_order_id, 3)
+            ack = transport.cancel_order("RSS-CANCEL-FILLED-001")
+
+        self.assertEqual(OrderStatus.ACCEPTED, submit_ack.status)
+        self.assertEqual(OrderStatus.FILLED, ack.status)
+        self.assertEqual(1, backend.cancel_macro_calls)
+        self.assertEqual(2, backend.rss_order_status_calls)
+
+    def test_persist_live_reconcile_only_mode_updates_only_activation_profile(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            config = json.loads(
+                (Path(__file__).resolve().parents[1] / "config" / "v7_direct_pipeline_config.json").read_text(
+                    encoding="utf-8"
+                )
+            )
+            config["sentinel"] = {"keep": "me"}
+            config["operating_mode"] = "LIVE_ACTIVE"
+            config["trading_mode"] = "LIVE"
+            config["execution_mode"] = "LIVE"
+            config["trading_actions"] = "LIVE_ONLY"
+            config["allowed_trading_actions"] = ["LIVE_ONLY"]
+            config["broker"].update(
+                {
+                    "type": "rakuten_rss",
+                    "transport_mode": "production",
+                    "live_trading_enabled": True,
+                    "live_enabled": True,
+                    "production_transport_enabled": True,
+                    "production_live_fire_armed": True,
+                }
+            )
+
+            persisted = order_bridge_gate._persist_live_reconcile_only_mode(root, config)
+            written = json.loads(
+                (root / "config" / "v7_direct_pipeline_config.json").read_text(encoding="utf-8")
+            )
+
+        self.assertEqual("LIVE_RECONCILE_ONLY", persisted["operating_mode"])
+        self.assertEqual("LIVE_RECONCILE_ONLY", written["operating_mode"])
+        self.assertEqual("LIVE", written["trading_mode"])
+        self.assertEqual("LIVE", written["execution_mode"])
+        self.assertEqual("RECONCILE_ONLY", written["trading_actions"])
+        self.assertEqual(["RECONCILE_ONLY"], written["allowed_trading_actions"])
+        self.assertEqual("rakuten_rss", written["broker"]["type"])
+        self.assertEqual("production", written["broker"]["transport_mode"])
+        self.assertTrue(written["broker"]["live_trading_enabled"])
+        self.assertTrue(written["broker"]["live_enabled"])
+        self.assertTrue(written["broker"]["production_transport_enabled"])
+        self.assertFalse(written["broker"]["production_live_fire_armed"])
+        self.assertEqual({"keep": "me"}, written["sentinel"])
+
+    def test_persist_live_reconcile_only_mode_is_idempotent_when_already_reconcile_only(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            config = json.loads(
+                (Path(__file__).resolve().parents[1] / "config" / "v7_direct_pipeline_config.json").read_text(
+                    encoding="utf-8"
+                )
+            )
+            config["operating_mode"] = "LIVE_ACTIVE"
+            config["trading_mode"] = "LIVE"
+            config["execution_mode"] = "LIVE"
+            config["trading_actions"] = "LIVE_ONLY"
+            config["allowed_trading_actions"] = ["LIVE_ONLY"]
+            config["broker"].update(
+                {
+                    "type": "rakuten_rss",
+                    "transport_mode": "production",
+                    "live_trading_enabled": True,
+                    "live_enabled": True,
+                    "production_transport_enabled": True,
+                    "production_live_fire_armed": True,
+                }
+            )
+            config["sentinel"] = {"keep": "me"}
+
+            config["operating_mode"] = "LIVE_RECONCILE_ONLY"
+            config["trading_actions"] = "RECONCILE_ONLY"
+            config["allowed_trading_actions"] = ["RECONCILE_ONLY"]
+            config["broker"]["production_live_fire_armed"] = False
+
+            persisted = order_bridge_gate._persist_live_reconcile_only_mode(root, config)
+
+            written = json.loads(
+                (root / "config" / "v7_direct_pipeline_config.json").read_text(encoding="utf-8")
+            )
+
+        self.assertEqual("LIVE_RECONCILE_ONLY", persisted["operating_mode"])
+        self.assertEqual("LIVE_RECONCILE_ONLY", written["operating_mode"])
+        self.assertEqual("LIVE", written["trading_mode"])
+        self.assertEqual("LIVE", written["execution_mode"])
+        self.assertEqual("RECONCILE_ONLY", written["trading_actions"])
+        self.assertEqual(["RECONCILE_ONLY"], written["allowed_trading_actions"])
+        self.assertEqual("rakuten_rss", written["broker"]["type"])
+        self.assertEqual("production", written["broker"]["transport_mode"])
+        self.assertTrue(written["broker"]["live_trading_enabled"])
+        self.assertTrue(written["broker"]["live_enabled"])
+        self.assertTrue(written["broker"]["production_transport_enabled"])
+        self.assertFalse(written["broker"]["production_live_fire_armed"])
+        self.assertEqual({"keep": "me"}, written["sentinel"])
+
+    def test_dispatch_live_active_unhealthy_persists_reconcile_once(self) -> None:
+        with tempfile.TemporaryDirectory() as tmpdir:
+            root = Path(tmpdir)
+            generated = order_bridge_gate._now_jst()
+            context = order_bridge_gate.PreorderDispatchContext(
+                report={
+                    "status": "APPROVED",
+                    "blockers": [],
+                    "approved_count": 0,
+                    "source": "dummy.json",
+                },
+                generated_at=generated,
+                expires_at=generated,
+                state_path=root / "state.json",
+                config={},
+                approved_idempotency_keys=frozenset(),
+                report_blockers=(),
+                trade_signals_context={"test": "context"},
+                executable_orders_by_client_order_id={},
+                accepted_orders_by_client_order_id={},
+                approved_payloads_by_client_order_id={},
+            )
+            broker = mock.Mock()
+            broker.health_check.return_value = mock.Mock(
+                healthy=False,
+                message="BROKER_HEALTH_FAILED",
+            )
+            broker.refresh_pending_orders.return_value = None
+
+            with (
+                mock.patch.object(
+                    order_bridge_gate,
+                    "_activation_config",
+                    return_value=("LIVE_ACTIVE", "LIVE", "LIVE", "LIVE_ONLY", None),
+                ),
+                mock.patch.object(order_bridge_gate, "_parse_state", return_value=(set(), None)),
+                mock.patch.object(order_bridge_gate, "_read_json", return_value=({}, None)),
+                mock.patch.object(
+                    order_bridge_gate,
+                    "_trade_signals_context",
+                    return_value=({"test": "context"}, ()),
+                ),
+                mock.patch.object(order_bridge_gate, "create_broker", return_value=broker),
+                mock.patch.object(
+                    order_bridge_gate,
+                    "_resolve_live_dispatch_mode",
+                    return_value="LIVE_RECONCILE_ONLY",
+                ),
+                mock.patch.object(
+                    order_bridge_gate,
+                    "_persist_live_reconcile_only_mode",
+                    side_effect=lambda _root, config: config,
+                ) as persist_mock,
+            ):
+                order_bridge_gate.dispatch_approved_orders(root, context)
+
+        persist_mock.assert_called_once()
+        broker.health_check.assert_called_once()
+        broker.refresh_pending_orders.assert_called_once()
+
     def test_timeout(self) -> None:
         backend = MockExcelComBackend()
         transport = ProductionRakutenRssTransport(
@@ -2251,13 +2733,20 @@ class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
             timeout_seconds=0,
             backend=backend,
         )
-        transport.submit_order(_buy_order("TIMEOUT-001"), "RSS-TIMEOUT-001")
+        order = _live_buy_order("TIMEOUT-001")
+        health = RakutenRssTransportHealth(
+            connected=True,
+            message="Workbook transport READY.",
+            transport_source=TRANSPORT_SOURCE_COM_LIVE,
+        )
 
-        updates = transport.poll_order("RSS-TIMEOUT-001")
+        with mock.patch.object(transport, "health_check", return_value=health):
+            transport.submit_order(order, "RSS-TIMEOUT-001")
+            updates = transport.poll_order("RSS-TIMEOUT-001")
 
         self.assertEqual(1, len(updates))
-        self.assertEqual(OrderStatus.TIMED_OUT, updates[0].status)
-        self.assertIn("timed out", updates[0].message.lower())
+        self.assertEqual(OrderStatus.PENDING, updates[0].status)
+        self.assertIn("reconciliation continues", updates[0].message.lower())
 
 
 class DeployV7RssProductionVbaTest(unittest.TestCase):
@@ -3129,3 +3618,4 @@ class DeployV7RssProductionVbaTest(unittest.TestCase):
 
 if __name__ == "__main__":
     unittest.main()
+import json
diff --git a/vba/PHOENIX_RSS_ORDER_BRIDGE.bas b/vba/PHOENIX_RSS_ORDER_BRIDGE.bas
index 79c22ef..5efd553 100644
--- a/vba/PHOENIX_RSS_ORDER_BRIDGE.bas
+++ b/vba/PHOENIX_RSS_ORDER_BRIDGE.bas
@@ -745,6 +745,10 @@ Private Sub OBR_ProcessCancelRequestRow(ByVal bridgeRoot As String, ByVal reques
         OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "related submit not found", "RELATED_SUBMIT_NOT_FOUND", "related submit not found"
         Exit Sub
     End If
+    If Len(NormalizeText(submitFields(5))) = 0 Then
+        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "related submit order number missing", "RELATED_SUBMIT_ORDER_NUMBER_MISSING", "related submit order number missing"
+        Exit Sub
+    End If
 
     mergedRow = OBR_MergeCancelRequestRow(requestRow, submitFields)
     receiptValues = OBR_BuildReceiptValues( _
@@ -753,7 +757,7 @@ Private Sub OBR_ProcessCancelRequestRow(ByVal bridgeRoot As String, ByVal reques
         "ACCEPTED", _
         "CANCELED", _
         OBR_InvalidStatusText(), _
-        NormalizeText(mergedRow(OBR_REQ_BROKER_ORDER_ID)), _
+        NormalizeText(submitFields(5)), _
         OBR_CANCEL_ACCEPTED_MESSAGE, _
         "", _
         OBR_CANCEL_ACCEPTED_MESSAGE)
@@ -1481,6 +1485,7 @@ Private Function OBR_ReceiptRowIsSuccessfulSubmit(ByVal receiptRow As Variant, B
     If StrComp(NormalizeText(receiptRow(OBR_REC_BRIDGE_STATUS)), "ACCEPTED", vbTextCompare) <> 0 Then Exit Function
     If StrComp(NormalizeText(receiptRow(OBR_REC_RESULT)), "ACCEPTED", vbTextCompare) <> 0 Then Exit Function
     If StrComp(NormalizeText(receiptRow(OBR_REC_RSS_ORDER_STATUS)), OBR_ValidStatusText(), vbTextCompare) <> 0 Then Exit Function
+    If Len(NormalizeText(receiptRow(OBR_REC_RSS_ORDER_NUMBER))) = 0 Then Exit Function
     If Len(NormalizeText(receiptRow(OBR_REC_ERROR_CODE))) > 0 Then Exit Function
     If Len(NormalizeText(receiptRow(OBR_REC_REQUEST_CHECKSUM))) = 0 Then Exit Function
     OBR_ReceiptRowIsSuccessfulSubmit = True
@@ -1496,7 +1501,7 @@ Private Function OBR_LoadSubmitHistoryFields( _
     Dim candidatePaths As Variant
     Dim candidatePath As Variant
     Dim rowValues As Variant
-    Dim loaded(0 To 4) As String
+    Dim loaded(0 To 5) As String
 
     candidateIds = Array("SUBMIT__" & brokerOrderId, "SUBMIT__" & clientOrderId)
     For Each candidateId In candidateIds
@@ -1512,6 +1517,7 @@ Private Function OBR_LoadSubmitHistoryFields( _
                         loaded(2) = NormalizeText(rowValues(OBR_REC_TARGET_PRICE))
                         loaded(3) = NormalizeText(rowValues(OBR_REC_STOP_PRICE))
                         loaded(4) = NormalizeText(rowValues(OBR_REC_EXPIRATION))
+                        loaded(5) = NormalizeText(rowValues(OBR_REC_RSS_ORDER_NUMBER))
                         OBR_LoadSubmitHistoryFields = loaded
                         On Error GoTo 0
                         Exit Function

## FILE: AGENTS.md

# PHOENIX 運用標準

この `AGENTS.md` をPHOENIX開発・運用ルールの唯一の標準書とする。
過去メモ、会話、knowledge、旧ルールと矛盾する場合は、現在のユーザー明示指示を最優先し、その次に本ファイルを優先する。

## 0. MANDATORY STARTUP GATE

PHOENIXに関する全ての回答・設計・校正・Codex指示・実装判断・実機指示の最初に、必ずその回の `AGENTS.md` 実体を読む。

実体の定義:
- ChatGPT: GitHub main 上の `masaA309/PHOENIX/AGENTS.md` 実体を読む。
- Codex: ローカル正本の `AGENTS.md` 実体を読む。
- 実際に読んだ場合のみ `AGENTS_READ:YES` とする。
- 会話履歴、要約、記憶だけで `AGENTS_READ:YES` にしてはならない。

開始順序:
1. AGENTS.mdを読む
2. 今回の目的を1文で固定
3. 禁止事項・正本・既存PASS領域・実機制約を確認
4. CALIBRATION_RECORDを作る
5. その後にのみ指示・実装・実機判断へ進む

AGENTS.mdを確認できない場合:
`AGENTS_GATE: FAIL`
として停止する。推測で進まない。

## 1. 役割

- USER: 最終方針・仕様変更・実注文・Git・保護操作を承認する。
- ChatGPT: 設計、完成条件、事前検証、独立校正、最終判断を担当する。
- Codex: ChatGPTが確定した範囲の実装・指定実行だけを担当する。独自設計・横断調査・別方式追加は禁止。
- Claude: ユーザー明示時のみ第三者監査。
- Copilotは使用しない。
- PHOENIXでは Work handoff / 自動handoff / local.handoff 呼び出し自体を禁止する。ユーザーがその時点で Work 利用を明示要求した場合のみ例外とする。ChatGPT側の都合、推奨、環境理由で Work へ移そうとしてはならない。PHOENIXの設計・実装・検証は本チャットとCodexで継続し、別Work workspace・一時workspace・別rootへ移さない。

## 2. CALIBRATION RECORD

Codex実装指示またはユーザー実機指示の前に必ず以下を明示的に確認する。

CALIBRATION_RECORD:
AGENTS_READ:
OBJECTIVE:
VERIFIED_FACTS:
UNVERIFIED_RUNTIME_ASSUMPTIONS:
PAST_FAILURE_CLASS_CHECK:
OWNER_LIFECYCLE_CONTEXT:
FAILURE_ROLLBACK_PATH:
RESULT_BRANCHES:
USER_MACHINE_ROLE:
CALIBRATION_RESULT:

規則:
- 項目省略禁止。
- AGENTS_READ != YES → FAIL。
- correctness/safetyに必要な未証明runtime前提が残る → FAIL。
- correctness / safety / acceptance に影響する未証明 runtime 前提は漏れなく `UNVERIFIED_RUNTIME_ASSUMPTIONS` に列挙する。1件でも残る場合は `USER_MACHINE_READY=NO` とする。`実機で確認すれば分かる` は PASS 理由にしない。`NONE` の場合も、なぜ `NONE` と言えるかを `VERIFIED_FACTS` または `OWNER_LIFECYCLE_CONTEXT` に明示する。
- owner / writer / reader / update trigger / persistence先が異なる類似概念は同一扱いしない。monitoring heartbeat と Excel heartbeat、source変更済み と production反映済みなどは概念分離して確認する。いずれかの同一性が未証明なら校正 PASS にしない。
- mock/unit PASSだけでruntime成立済み扱い禁止。
- 公式APIであることだけで実機成立済み扱い禁止。
- 類似経路が過去に動いたことだけで成立済み扱い禁止。
- AGENTS_READ は当該 actor が上記の実体を実際に read したときのみ YES とする。
- PASS/FAIL/NOT_PROVEN後の進行を実装前に固定する。
- record無しの「校正PASS」は無効。
- ユーザーが「校正」と言った場合、直前の自分の案を信用せず独立監査として再実施する。

## 3. 過去失敗class照合

最低限、毎回今回の変更と関係する以下を照合する。

- heartbeat / PID ownership
- process lifecycle / PROCESS_IDLE
- monitoring-ready と trading-ready の混同
- Excel instance / workbook owner
- COM activation / logon session
- ROT session visibility
- GetActiveObject wrong-instance
- sandbox desktop / user desktop 混同
- EnumWindows / EnumDesktopWindows visibility
- source変更のproduction未反映
- consumer owner / trigger欠落
- startup pending sequencing
- backupが最初のmutationより後
- bootstrap import後dirty state
- OneDrive web/local path equivalenceを未確認のままworkbook identity / path / write判定に使う
- production workbook自身によるVBProject mutation + Saveをruntime permission/state未証明のまま成立扱いする
- pending残留だけでscheduler未起動とREADY=false CleanExitを判別できると扱う
- 未証明runtime前提をunit testで成立済み扱い
- AGENTS実体をreadせず `AGENTS_READ:YES` と自己申告
- ChatGPTから参照可能な GitHub main 版を読まずに、ローカル AGENTS だけで自己停止
- AGENTSローカル/GitHub不一致を放置
- Codexが `AGENTS_READ:YES` 後に、ChatGPT指示にない「安全のため」「より良い」「念のため」「観測しやすい」等の自主判断で assertion / state / field / test / observation / logging / validation / fallback / command / acceptance condition を追加実行する
- WRITE許可されたファイル内であっても、ChatGPTが指定した function / behavior / call path / input / proof target / assertion の範囲を越えて変更する
- test PASSや安全性向上を理由に、ChatGPTが固定していない acceptance condition / observable state / validation condition を後付けする
- `AGENTS_READ:YES` を、当該runの実行範囲全体への包括的許可と誤認する
- 指示外actionが必要・有益・安全とCodexが判断した場合に、実行前に停止せず自主実行する
- Codexが指示外actionを実行したにもかかわらず `SCOPE_VIOLATION:NO` または `AGENTS_COMPLIANCE:PASS` と報告する

上記failure classについて次の規則も§3へ続けて追記する:

- 上記のいずれかに該当したrunは、test結果や実装品質に関係なく自動FAILとする。
- 「安全性向上」「品質向上」「追加確認」はscope拡張の正当化理由にならない。
- 指示外actionを必要と判断した場合、Codexはそのactionを一切実行せず `SCOPE_VIOLATION_PROPOSED:YES` と報告して停止する。
- 同run内でChatGPTの追加指示を待たずに別案・代替策・追加test・追加観測へ進んではならない。

同じfailure classを未対策で再使用する指示は自動FAIL。
- 新しい `UNVERIFIED_RUNTIME_ASSUMPTIONS` は毎回、該当する過去 failure class と照合する。類似 failure class を別 API・別手段へ置き換えただけでは対策済みとみなさない。重複がある場合は非実機工程で閉じるか方式選定へ戻し、同型前提の再使用は自動 FAIL とする。
新しい重大failure classが判明した場合、次作業前に本章へ統合する。

## 4. USER MACHINE

- ユーザーをデバッガー・エラー報告要員にしない。
- ユーザーにファイル内の該当箇所探索、必要部分の選別、コード抽出、値の推測・選択をさせない。ChatGPT/Codex側で事前に完成内容を確定し、対象場所、入力値、貼付用コード全文まで、そのまま実行できる形で提示する。`ファイルを開いて必要部分を探す`、`該当箇所だけコピーする`、`適切な値を選ぶ`、`必要部分を抜き出す` 等の指示は禁止する。コード貼付が必要なら元ファイルから抽出させず、完成コード全文を提示する。値入力が必要なら判断させず、確定済みの値そのものを提示する。例外は、ユーザー自身が探索・選択を明示的に希望した場合のみ。
- 原則、ユーザー実機は最終受入だけ。
- 最終受入は1回消費の厳密な証明サイクルとする。実機開始前に証明対象リストを固定し、同じ起動〜終了サイクルで全項目を同時に証明する。未列挙の重大前提欠陥が出たらその受入は FAIL とし、その場で修正→再実行しない。再受入は、依存グラフ再閉鎖と CALIBRATION_RECORD 再作成後、ユーザーが明示的に再受入を許可した場合のみ可能とする。
- `start → error → log → 修正 → 再実行` の反復禁止。
- USER_MACHINE_READY=YESにはCALIBRATION_RECORD PASS必須。
- 診断が不可避ならread-only、観測項目固定、1回だけ。
- 同じfailure classで2回目の実機診断は禁止。
- 実機で新しい重大前提欠陥が出た場合、それは校正失敗として扱う。

## 5. 設計・実装順序

必ず:
事実
→ feasibility
→ owner/lifecycle/state transition
→ process/session/desktop/permission
→ external dependency
→ deployment/persistence
→ failure/rollback/recovery
→ observable completion
→ tests
→ Codex実装
→ 校正
→ 最終実機受入

実機受入前に対象機能の owner / lifecycle / trigger / heartbeat / readiness / external dependency / deployment / persistence / failure path / observable completion を一つの依存グラフとして閉じる。一部だけ閉じて実機へ進むことは禁止する。各段の input / 成立条件 / failure 時挙動 / 次段への副作用 / observable completion を事前固定し、未閉鎖段が1つでもあれば implementation complete / calibration PASS / USER_MACHINE_READY 扱いにしない。

完成仕様が固定される前に実装・大量testを行わない。
後から完成条件を小出し追加してtestを増築し続けない。

## 6. Codex送信ゲート

Codexへ送る前に:
- 1目的か
- ChatGPT側で設計・調査を完了したか
- 未確定仕様がないか
- owner/lifecycle/contextが閉じているか
- READ/WRITE最小範囲が固定済みか
- exact file / exact function / exact call path / exact input が1本に固定されているか
- PROOF TARGETを含む指示では、各targetと `EXACT_EVIDENCE_SOURCE` を1対1で明示し、各PROOF TARGETについて `EXACT_EVIDENCE_SOURCE` を1つに固定しているか
- 証拠source未固定のPROOF TARGETが1件でもあればCodexへ送らないか
- Codexに証拠sourceの選定・探索・代替・推定を残していないか
- Codexによる別sourceへの切替を許していないか
- Codexにworkspace選定を残していないか
- failure/rollbackが固定済みか
- PASS/FAIL/NOT_PROVEN分岐が固定済みか
- test/PASS条件が固定済みか
- 既存PASS領域を再調査しないか
を確認する。

1つでもNOならCodexへ送らない。

Codex指示は簡潔な完成版とし、必ず:
WORKSPACE
TASK
ALLOWED
FORBIDDEN
SAFETY
OUTPUT
EXECUTION_MANIFEST
を含む。

CODEX_PROMPT_RULE:
個別Codex指示は、AGENTS.mdの恒久原則を再掲・言い換えしない。
今回固有のTASK・変更対象・ALLOWED/FORBIDDEN差分・proof targetだけを書く。
同じ内容を繰り返さず、Codexに重要条件の取捨選択をさせない。
proof targetは互いに独立した検証単位だけにする。

差分指示禁止。
open-ended横断調査禁止。
「必要なら調べる」「潜在defectを広く探す」禁止。
途中実況禁止。

### EXECUTION SCOPE LOCK

全Codex指示は、実行範囲を固定するため次の `EXECUTION_MANIFEST` を持つ。

EXECUTION_MANIFEST:
READ_FILES:
WRITE_FILES:
ALLOWED_FUNCTIONS:
ALLOWED_BEHAVIORS:
ALLOWED_COMMANDS:
ALLOWED_TESTS:
ALLOWED_ASSERTIONS:
PROOF_TARGETS:
FORBIDDEN_ADDITIONS:

規則:
- Codexが実行できるのは `EXECUTION_MANIFEST` に明示されたactionだけ。
- `AGENTS_READ:YES` は実行許可を意味しない。実行許可は当該runの `EXECUTION_MANIFEST` だけで決まる。
- `WRITE_FILES` は、そのファイル内を自由に変更してよいという意味ではない。
- 変更可能範囲は `WRITE_FILES × ALLOWED_FUNCTIONS × ALLOWED_BEHAVIORS` の交差部分だけとする。
- `ALLOWED_FUNCTIONS` が指定されている場合、同一ファイル内の別function変更は禁止。
- `ALLOWED_BEHAVIORS` にないstate追加、field追加、fallback追加、validation追加、logging追加、observation追加は禁止。
- `ALLOWED_TESTS` にないtest実行は禁止。
- `ALLOWED_ASSERTIONS` にないassertion追加は禁止。
- ChatGPTが固定していないproof target、acceptance condition、observable completionをCodexが追加してはならない。
- 「安全のため」「より良い」「念のため」「分かりやすい」「将来必要」等の理由によるscope拡張は禁止。
- 指示外actionが必要・有益と判断した場合、実行してはならない。
- 指示外actionを実行する前に `SCOPE_VIOLATION_PROPOSED:YES` と報告して停止する。
- `SCOPE_VIOLATION_PROPOSED:YES` は違反ではない。実行せず停止した場合は正しいfail-closeとする。
- 指示外actionを1件でも実行した場合は `SCOPE_VIOLATION:YES` とし、test PASSでも当該runを自動FAILとする。
- `SCOPE_VIOLATION:YES` のrunで生成・変更された成果物は、ChatGPTによる再監査完了まで未承認扱いとする。
- Codexはscope違反を自分で修正して続行してはならない。違反を検知した時点で停止する。
- CodexはChatGPTが指定していない別source、別file、別command、別testへ切り替えてはならない。
- command実行回数と実行内容を隠してはならない。

全Codex run終了時に以下を必須出力とする:

COMMAND_COUNT:
COMMAND_LOG:
FILES_READ:
FILES_WRITTEN:
TESTS_RUN:
UNREQUESTED_ACTIONS:
SCOPE_VIOLATION_PROPOSED:
SCOPE_VIOLATION:
AGENTS_COMPLIANCE:

判定規則:
- `UNREQUESTED_ACTIONS` が1件以上 → `SCOPE_VIOLATION:YES`
- `SCOPE_VIOLATION:YES` → `AGENTS_COMPLIANCE:FAIL`
- `SCOPE_VIOLATION:YES` → run全体FAIL
- test PASSは `AGENTS_COMPLIANCE:FAIL` を上書きできない
- `COMMAND_LOG` が欠落し実行内容を監査できない場合、AGENTS_COMPLIANCEをPASSにしてはならない
- `FILES_WRITTEN` に `WRITE_FILES` 外が1件でも含まれる場合、自動FAIL
- 指定されたfunction/behavior外の変更が1件でもあれば、自動FAIL

## 7. FAIL / NOT_PROVEN

- 推測修正禁止。
- 新方式を次々試してユーザー実機で答え合わせしない。
- 同じfailure classなら局所patchではなく前提・方式を再評価する。
- FAIL/HOLD時は理由だけで終わらない。
- 安全な代替完成指示を確定できる場合は同じ返答で提示する。
- 確定できない場合はNOT_PROVENとして、ユーザー実機を使わない次の安全な工程を提示する。
- 「次に校正する」「後で考える」で終了しない。

## 8. テスト

- 仕様固定後のみ実施。
- 変更に直接関係する既存testを最小限使用する。
- 新規test fileは原則禁止。
- 全体test・重いvalidationは明示許可なし禁止。
- PASS済み検証を新しいproof targetなしに再実行しない。
- OOS / Formal Validation / Future Poison再実行禁止。

## 9. 実行環境

正本:
`C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX`

- `work/` 使用禁止。
- Work mode / 別Work workspace / 別worktree / Documents\Codex / 一時コピー / 別rootを実装・検証・Git操作先にしない。
- PHOENIXの全てのCodex WORKSPACEは、ユーザーがその時点で明示的に別場所を指定しない限り、必ず `C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX` を指定する。
- Python:
  `./.venv/Scripts/python.exe`
- .venv削除・再作成禁止。
- package再install・大量削除は禁止。明示許可時のみ。
- rm -rf / git clean禁止。
- destructive Git禁止。

## 10. Trading Safety

明示解禁まで:
- PAPER維持
- orders_submitted=0維持
- BRIDGE_ARMED=False維持
- 実注文禁止
- live_trading変更禁止
- broker/RSS送信禁止

Guardian / reconciliation / fail-safeを迂回しない。

## 11. Git

ユーザー明示許可なしに以下禁止:
- git add
- git commit
- git push
- destructive Git

例外:
- ユーザーが AGENTS.md ルールの追加・修正・上書きを明示要求した場合、その要求は `AGENTS.md` 単独の `git add` / `git commit` / `git push` を許可したものとして扱う。
- ただし、ユーザーが `commitしない` または `pushしない` と明示した場合は除く。
- AGENTS.md 以外のファイルを同じ commit に含めてはならない。
- 通常のコード変更については従来どおり明示許可なし commit/push 禁止を維持する。

runtime、ログ、生成レポート、workbook、broker取込データを勝手にGit対象にしない。

## 12. 仕様・正本保護

- 合意済み仕様を勝手に変更しない。
- `max_positions=5` を承認仕様として扱わない。
- 設計・アーキテクチャ変更はChatGPTが先に確定する。
- Codexは確定設計を再解釈しない。
- production workbook/fileを勝手に作り直さない。
- 認証情報・口座識別子・秘密情報をrepoへ記録しない。

## 13. 回答・指示形式

- 簡潔に結果を返す。
- 実況・進行宣言禁止。
- 複数案を並べてユーザーに選択させず、最善案を1つ出す。
- 差分ではなく完成版を出す。
- Codex指示が不要なら出さない。
- FAILを出す場合、可能なら同じ返答で修正版完成指示も出す。
- 次工程が確定している場合、確認結果・説明・反省・メタコメントだけで返答を終えてはならない。同じ返答内で、その次工程に必要な完成指示、Codex指示、ユーザー操作手順、貼付用コード全文、確定入力値など、その時点で安全に確定できる実行内容まで一括で提示する。追加のユーザー判断が不要な工程を「次にやる」「必要なら後で出す」「次の返答で出す」と先送りすることは禁止する。実行不能、未確定、安全上停止が必要な場合のみ、その理由を明示して停止してよい。
- ユーザーに同じログ・同じ試験を繰り返させない。

## 14. AGENTS管理

- 1テーマ1ルール。
- 重複禁止。
- 矛盾禁止。
- 追記で衝突させず、既存章を統合・上書きする。
- 恒久ルールはAGENTS.mdだけに置く。
- knowledgeには状態・Failure・履歴・テンプレートだけを置く。
- AGENTS更新後、旧ルールとの互換性を確認する。
- 変更後に重複・矛盾が1つでも残る場合は完了扱い禁止。


## FILE: phoenix_core/order_bridge_gate.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from phoenix_core.broker import BrokerAdapter
from phoenix_core.models import OrderRequest
from phoenix_core.candidate_input_guard import (
    CandidateInputAudit,
    CandidateInputError,
    CandidateInputPolicy,
    CandidateInputBatch,
    load_execution_candidates,
)
from phoenix_core.data_freshness import JST
from phoenix_core.factory import create_broker
from phoenix_core.performance_tracker import atomic_write, resolve_path
from phoenix_core.position_sizer import (
    PositionSizingConfig,
    SizingDecision,
    build_order_requests,
    size_candidates,
)
from phoenix_core.risk_controller import (
    RiskConfig,
    RiskState,
    evaluate_orders,
    load_risk_state,
    resolve_effective_total_invested_pct,
)


SCHEMA_VERSION = 1
VERSION = "PHOENIX v7 Step42"
CREATED_BY = "PHOENIX_STEP42_PREORDER_GATE"
DEFAULT_TRADING_MODE = "PAPER"
DEFAULT_EXECUTION_MODE = "DRY_RUN"
DEFAULT_TRADING_ACTIONS = "PAPER_ONLY"
DEFAULT_ALLOWED_TRADING_ACTIONS = frozenset({"DISABLED", "PAPER_ONLY"})
OPERATING_MODE_PROFILES: dict[str, dict[str, Any]] = {
    "PAPER_SAFE": {
        "trading_mode": "PAPER",
        "execution_mode": "DRY_RUN",
        "trading_actions": "PAPER_ONLY",
        "allowed_trading_actions": frozenset({"DISABLED", "PAPER_ONLY"}),
        "broker_type": "paper",
        "transport_mode": "paper",
        "live_trading_enabled": False,
        "production_transport_enabled": False,
        "production_live_fire_armed": False,
    },
    "LIVE_ACTIVE": {
        "trading_mode": "LIVE",
        "execution_mode": "LIVE",
        "trading_actions": "LIVE_ONLY",
        "allowed_trading_actions": frozenset({"LIVE_ONLY"}),
        "broker_type": "rakuten_rss",
        "transport_mode": "production",
        "live_trading_enabled": True,
        "production_transport_enabled": True,
        "production_live_fire_armed": True,
    },
    "LIVE_RECONCILE_ONLY": {
        "trading_mode": "LIVE",
        "execution_mode": "LIVE",
        "trading_actions": "RECONCILE_ONLY",
        "allowed_trading_actions": frozenset({"RECONCILE_ONLY"}),
        "broker_type": "rakuten_rss",
        "transport_mode": "production",
        "live_trading_enabled": True,
        "production_transport_enabled": True,
        "production_live_fire_armed": False,
    },
}
ORDER_TYPE = "LIMIT"
SIDE = "BUY"
MARKET = "TSE"
ALLOWED_OPERATING_SCOPES = {"MONITOR_ONLY", "OPERATIONAL"}
INSTRUCTION_TTL_MINUTES = 15
STATE_FILE = "state/v7_real_trade_preorder_state.json"
INSTRUCTION_FILE = "reports/v7_real_trade_preorder_instructions.csv"
REPORT_JSON_FILE = "reports/v7_real_trade_preorder_report.json"
REPORT_TEXT_FILE = "reports/v7_real_trade_preorder_report.txt"
AUDIT_JSONL_FILE = "reports/v7_real_trade_preorder_audit.jsonl"
NOTIFICATION_SOURCE_MANIFEST_FILE = "reports/notification_source_manifest.json"
TRADE_SIGNALS_MANIFEST_FILE = "reports/trade_signals_manifest.json"
MARKET_REGIME_FILE = "reports/market_regime.json"
DIRECT_PIPELINE_CONFIG = "config/v7_direct_pipeline_config.json"
POSITION_SIZER_CONFIG = "config/v7_position_sizer_config.json"
RISK_CONFIG_FILE = "config/v7_risk_config.json"
PRODUCTION_BRIDGE_ROOT_RELATIVE = "runtime/v7_rss_production/order_bridge"
PRODUCTION_BRIDGE_PENDING_RELATIVE = "runtime/v7_rss_production/order_bridge/outbox/pending"
PRODUCTION_BRIDGE_PROCESSING_RELATIVE = "runtime/v7_rss_production/order_bridge/outbox/processing"
DEFAULT_CANDIDATE_PATH = "reports/trade_signals.csv"
OUTPUT_COLUMNS = [
    "schema_version",
    "intent_id",
    "idempotency_key",
    "generated_at",
    "expires_at",
    "trading_mode",
    "execution_mode",
    "signal_date",
    "ticker",
    "market",
    "side",
    "order_type",
    "quantity",
    "lot_size",
    "reference_price",
    "limit_price",
    "stop_loss_price",
    "take_profit_price",
    "estimated_notional",
    "estimated_max_loss",
    "source",
    "status",
    "blocked_reasons",
    "created_by",
]
_MISSING = object()


def _now_jst() -> datetime:
    return datetime.now(JST)


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    if not path.is_file():
        return {}, f"Required file not found: {path}"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return {}, f"Could not read {path}: {type(error).__name__}: {error}"
    if not isinstance(value, dict):
        return {}, f"JSON root is not an object: {path}"
    return value, None


def _position_sizing_config(payload: Mapping[str, Any]) -> PositionSizingConfig:
    sizing = payload.get("position_sizing", {})
    if not isinstance(sizing, Mapping):
        raise ValueError("position_sizing config must be an object")
    return PositionSizingConfig(
        risk_per_trade_pct=float(sizing.get("risk_per_trade_pct", 0.01)),
        max_position_pct=float(sizing.get("max_position_pct", 0.30)),
        max_total_invested_pct=float(sizing.get("max_total_invested_pct", 0.80)),
        minimum_cash_reserve_pct=float(sizing.get("minimum_cash_reserve_pct", 0.10)),
        fallback_stop_distance_pct=float(sizing.get("fallback_stop_distance_pct", 0.03)),
        lot_size=int(sizing.get("lot_size", 100)),
        maximum_quantity_per_ticker=int(sizing.get("maximum_quantity_per_ticker", 1000)),
        allow_pyramiding=bool(sizing.get("allow_pyramiding", False)),
        commission_buffer_pct=float(sizing.get("commission_buffer_pct", 0.001)),
    )


def _risk_config(payload: Mapping[str, Any]) -> RiskConfig:
    risk = payload.get("risk", {})
    if not isinstance(risk, Mapping):
        raise ValueError("risk config must be an object")
    return RiskConfig(
        risk_policy_id=str(payload.get("risk_policy_id", "RISK_V2_PRODUCTION_MA75_BREADTH_V1")),
        breadth_metric=str(payload.get("breadth_metric", "ABOVE_MA75_RATIO_ACTIVE225")),
        risk_v2_enabled=bool(payload.get("risk_v2_enabled", False)),
        breadth_threshold=float(payload.get("breadth_threshold", 0.40)),
        bear_max_total_invested_pct=float(payload.get("bear_max_total_invested_pct", 0.70)),
        market_regime_file=str(payload.get("market_regime_file", "reports/market_regime.json")),
        max_daily_loss_pct=float(risk.get("max_daily_loss_pct", 0.03)),
        max_drawdown_pct=float(risk.get("max_drawdown_pct", 0.10)),
        max_positions=(
            None
            if risk.get("max_positions", None) is None
            else int(risk.get("max_positions", None))
        ),
        max_total_invested_pct=float(risk.get("max_total_invested_pct", 0.95)),
        max_single_position_pct=float(risk.get("max_single_position_pct", 0.30)),
        max_orders_per_run=int(risk.get("max_orders_per_run", 3)),
        max_consecutive_losses=int(risk.get("max_consecutive_losses", 3)),
        minimum_cash_reserve_pct=float(risk.get("minimum_cash_reserve_pct", 0.10)),
        block_on_broker_health_failure=bool(risk.get("block_on_broker_health_failure", True)),
    )


def _market_regime_context(
    root: Path,
    risk_config: RiskConfig,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not risk_config.risk_v2_enabled:
        return None, []

    blockers: list[str] = []
    manifest_source, manifest_error = _read_json(resolve_path(root, NOTIFICATION_SOURCE_MANIFEST_FILE))
    if manifest_error:
        blockers.append(f"MARKET_REGIME_MANIFEST_INVALID: {manifest_error}")
        return None, blockers

    regime_path = resolve_path(root, risk_config.market_regime_file)
    regime_source, regime_error = _read_json(regime_path)
    if regime_error:
        blockers.append(f"MARKET_REGIME_INVALID: {regime_error}")
        return None, blockers

    try:
        manifest_run_id = _normalize_text(manifest_source.get("run_id"))
        manifest_report_sha256 = _normalize_text(manifest_source.get("report_sha256"))
        manifest_ticker_count = int(manifest_source.get("ticker_count", 0))
        manifest_expected_ticker_count = int(manifest_source.get("expected_ticker_count", manifest_ticker_count))
    except (TypeError, ValueError) as error:
        blockers.append(f"MARKET_REGIME_MANIFEST_INVALID: {type(error).__name__}: {error}")
        return None, blockers

    if not manifest_run_id or not manifest_report_sha256:
        blockers.append("MARKET_REGIME_MANIFEST_INVALID: missing run_id/report_sha256")
        return None, blockers
    if manifest_ticker_count != 225 or manifest_expected_ticker_count != 225:
        blockers.append("MARKET_REGIME_MANIFEST_INVALID: ticker_count")
        return None, blockers

    try:
        schema_version = int(regime_source.get("schema_version", 0))
        source_run_id = _normalize_text(regime_source.get("source_run_id"))
        source_report_sha256 = _normalize_text(regime_source.get("source_report_sha256"))
        source_ticker_count = int(regime_source.get("source_ticker_count", 0))
        risk_policy_id = _normalize_text(regime_source.get("risk_policy_id"))
        breadth_metric = _normalize_text(regime_source.get("breadth_metric"))
        breadth_ratio = float(regime_source.get("breadth_ratio"))
        breadth_threshold = float(regime_source.get("breadth_threshold"))
        regime = _normalize_text(regime_source.get("regime")).upper()
    except (TypeError, ValueError) as error:
        blockers.append(f"MARKET_REGIME_INVALID: {type(error).__name__}: {error}")
        return None, blockers

    if schema_version != 2:
        blockers.append("MARKET_REGIME_INVALID: SCHEMA_VERSION")
    if source_run_id != manifest_run_id or source_report_sha256 != manifest_report_sha256:
        blockers.append("MARKET_REGIME_STALE: MANIFEST_MISMATCH")
    if source_ticker_count != manifest_ticker_count:
        blockers.append("MARKET_REGIME_STALE: TICKER_COUNT_MISMATCH")
    if not risk_policy_id:
        blockers.append("MARKET_REGIME_INVALID: RISK_POLICY_ID")
    elif risk_policy_id != risk_config.risk_policy_id:
        blockers.append("MARKET_REGIME_STALE: RISK_POLICY_ID_MISMATCH")
    if not breadth_metric:
        blockers.append("MARKET_REGIME_INVALID: BREADTH_METRIC")
    elif breadth_metric != risk_config.breadth_metric:
        blockers.append("MARKET_REGIME_STALE: BREADTH_METRIC_MISMATCH")
    if not (0.0 <= breadth_ratio <= 1.0):
        blockers.append("MARKET_REGIME_INVALID: BREADTH_RATIO_RANGE")
    if not (0.0 <= breadth_threshold <= 1.0):
        blockers.append("MARKET_REGIME_INVALID: BREADTH_THRESHOLD_RANGE")
    if abs(breadth_threshold - risk_config.breadth_threshold) > 1e-9:
        blockers.append("MARKET_REGIME_STALE: BREADTH_THRESHOLD_MISMATCH")
    if regime not in {"BULL", "SIDEWAYS", "NEUTRAL", "BEAR"}:
        blockers.append("MARKET_REGIME_INVALID: REGIME")
    if breadth_ratio < risk_config.breadth_threshold and regime != "BEAR":
        blockers.append("MARKET_CONTEXT_INCONSISTENT: BEAR_REQUIRED")
    if breadth_ratio >= risk_config.breadth_threshold and regime == "BEAR":
        blockers.append("MARKET_CONTEXT_INCONSISTENT: BEAR_FORBIDDEN")

    if blockers:
        return None, blockers

    return (
        {
            "risk_policy_id": risk_policy_id,
            "breadth_metric": breadth_metric,
            "breadth_ratio": breadth_ratio,
            "breadth_threshold": breadth_threshold,
            "regime": regime,
            "source_run_id": source_run_id,
            "source_report_sha256": source_report_sha256,
            "source_ticker_count": source_ticker_count,
        },
        [],
    )


def _file_sha256(file_path: Path) -> str:
    return hashlib.sha256(file_path.read_bytes()).hexdigest()


def _trade_signals_context(
    root: Path,
    candidate_path: Path,
    source_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    blockers: list[str] = []
    manifest_source, manifest_error = _read_json(resolve_path(root, TRADE_SIGNALS_MANIFEST_FILE))
    if manifest_error:
        blockers.append(f"TRADE_SIGNALS_MANIFEST_INVALID: {manifest_error}")
        return None, blockers

    if not candidate_path.is_file():
        blockers.append(f"TRADE_SIGNALS_INVALID: FILE_MISSING: {candidate_path}")
        return None, blockers

    try:
        schema_version = int(manifest_source.get("schema_version", 0))
        source_run_id = _normalize_text(manifest_source.get("source_run_id"))
        source_report_sha256 = _normalize_text(manifest_source.get("source_report_sha256"))
        source_ticker_count = int(manifest_source.get("source_ticker_count", 0))
        trade_signals_sha256 = _normalize_text(manifest_source.get("trade_signals_sha256"))
        market_regime_sha256 = _normalize_text(manifest_source.get("market_regime_sha256"))
        trade_signals_row_count = int(manifest_source.get("trade_signals_row_count", 0))
        actual_trade_signals_sha256 = _file_sha256(candidate_path)
        actual_market_regime_sha256 = _file_sha256(resolve_path(root, MARKET_REGIME_FILE))
    except (OSError, TypeError, ValueError) as error:
        blockers.append(f"TRADE_SIGNALS_MANIFEST_INVALID: {type(error).__name__}: {error}")
        return None, blockers

    source_manifest_run_id = _normalize_text(source_manifest.get("run_id"))
    source_manifest_report_sha256 = _normalize_text(source_manifest.get("report_sha256"))
    source_manifest_ticker_count = int(source_manifest.get("ticker_count", 0))

    if schema_version != 1:
        blockers.append("TRADE_SIGNALS_MANIFEST_INVALID: SCHEMA_VERSION")
    if not source_run_id or not source_report_sha256:
        blockers.append("TRADE_SIGNALS_MANIFEST_INVALID: SOURCE_FIELDS")
    if source_run_id != source_manifest_run_id or source_report_sha256 != source_manifest_report_sha256:
        blockers.append("TRADE_SIGNALS_STALE: SOURCE_MISMATCH")
    if source_ticker_count != source_manifest_ticker_count or source_ticker_count != 225:
        blockers.append("TRADE_SIGNALS_INVALID: SOURCE_TICKER_COUNT")
    if trade_signals_sha256 != actual_trade_signals_sha256:
        blockers.append("TRADE_SIGNALS_STALE: HASH_MISMATCH")
    if market_regime_sha256 != actual_market_regime_sha256:
        blockers.append("TRADE_SIGNALS_STALE: MARKET_REGIME_HASH_MISMATCH")
    if trade_signals_row_count < 0:
        blockers.append("TRADE_SIGNALS_INVALID: ROW_COUNT")

    if blockers:
        return None, blockers

    return (
        {
            "schema_version": schema_version,
            "source_run_id": source_run_id,
            "source_report_sha256": source_report_sha256,
            "source_ticker_count": source_ticker_count,
            "trade_signals_sha256": trade_signals_sha256,
            "market_regime_sha256": market_regime_sha256,
            "trade_signals_row_count": trade_signals_row_count,
        },
        [],
    )


def _activation_config(payload: Mapping[str, Any]) -> tuple[str, str, str, str, frozenset[str]]:
    activation = payload if isinstance(payload, Mapping) else {}
    operating_mode = _normalize_text(activation.get("operating_mode", "")).upper()
    profile = OPERATING_MODE_PROFILES.get(operating_mode)
    if profile is None:
        raise ValueError(
            "operating_mode must be PAPER_SAFE, LIVE_ACTIVE, or LIVE_RECONCILE_ONLY"
        )

    trading_mode = _normalize_text(activation.get("trading_mode", profile["trading_mode"])).upper() or profile["trading_mode"]
    execution_mode = _normalize_text(activation.get("execution_mode", profile["execution_mode"])).upper() or profile["execution_mode"]
    trading_actions = _normalize_text(activation.get("trading_actions", profile["trading_actions"])).upper() or profile["trading_actions"]
    allowed_raw = activation.get("allowed_trading_actions", tuple(profile["allowed_trading_actions"]))
    if isinstance(allowed_raw, Sequence) and not isinstance(allowed_raw, (str, bytes)):
        allowed_trading_actions = frozenset(
            value
            for value in (_normalize_text(item).upper() for item in allowed_raw)
            if value
        )
    else:
        allowed_trading_actions = frozenset(profile["allowed_trading_actions"])
    if not allowed_trading_actions:
        allowed_trading_actions = frozenset(profile["allowed_trading_actions"])

    if trading_mode != profile["trading_mode"]:
        raise ValueError(f"operating_mode={operating_mode} requires trading_mode={profile['trading_mode']}")
    if execution_mode != profile["execution_mode"]:
        raise ValueError(f"operating_mode={operating_mode} requires execution_mode={profile['execution_mode']}")
    if trading_actions != profile["trading_actions"]:
        raise ValueError(f"operating_mode={operating_mode} requires trading_actions={profile['trading_actions']}")
    if allowed_trading_actions != frozenset(profile["allowed_trading_actions"]):
        raise ValueError(
            f"operating_mode={operating_mode} requires allowed_trading_actions={sorted(profile['allowed_trading_actions'])}"
        )
    return operating_mode, trading_mode, execution_mode, trading_actions, allowed_trading_actions


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _normalize_numeric(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if not (number == number) or number <= 0:
        return None
    return round(number, 2)


def _first_text(row: Mapping[str, Any], names: Sequence[str], default: str = "") -> str:
    for name in names:
        if name in row:
            value = _normalize_text(row.get(name))
            if value:
                return value
    return default


def _first_numeric(row: Mapping[str, Any], names: Sequence[str]) -> float | None:
    for name in names:
        if name in row:
            value = _normalize_numeric(row.get(name))
            if value is not None:
                return value
    return None


def _parse_signal_timestamp(value: Any, generated_at: datetime) -> tuple[datetime | None, str | None]:
    text = _normalize_text(value)
    if not text:
        return None, "SIGNAL_DATE_MISSING"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None, "SIGNAL_DATE_INVALID"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    else:
        parsed = parsed.astimezone(JST)
    if parsed > generated_at + timedelta(minutes=5):
        return None, "SIGNAL_DATE_IN_THE_FUTURE"
    if generated_at - parsed > timedelta(hours=24):
        return None, "SIGNAL_DATE_TOO_OLD"
    return parsed, None


def _parse_state(path: Path) -> tuple[set[str], str | None]:
    if not path.is_file():
        return set(), None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return set(), f"Could not read duplicate-prevention state: {type(error).__name__}: {error}"
    if not isinstance(payload, dict):
        return set(), "Duplicate-prevention state root is not an object"
    approved = payload.get("approved_idempotency_keys", [])
    if not isinstance(approved, list) or any(not isinstance(item, str) for item in approved):
        return set(), "Duplicate-prevention state is invalid"
    return set(approved), None


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        frame.to_csv(temporary, index=False, encoding="utf-8-sig")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _market_from_ticker(ticker: str) -> str:
    normalized = ticker.strip().upper()
    if normalized.endswith(".T"):
        return MARKET
    return "UNKNOWN"


def _instruction_payload(
    *,
    generated_at: datetime,
    signal_date: str,
    ticker: str,
    side: str,
    order_type: str,
    quantity: int,
    lot_size: int,
    reference_price: float,
    limit_price: float,
    stop_loss_price: float,
    take_profit_price: float,
    source: str,
    trading_mode: str,
    execution_mode: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "signal_date": signal_date,
        "ticker": ticker,
        "market": _market_from_ticker(ticker),
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "lot_size": lot_size,
        "reference_price": reference_price,
        "limit_price": limit_price,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
        "source": source,
    }


def _idempotency_key(payload: Mapping[str, Any]) -> str:
    return _stable_hash(payload)


def _intent_id(signal_date: str, ticker: str, side: str, idempotency_key: str) -> str:
    compact_date = signal_date.replace("-", "") if signal_date else "UNKNOWN"
    return f"PHX42-{compact_date}-{ticker}-{side}-{idempotency_key[:10].upper()}"


def _row_blockers(
    *,
    operating_scope: str,
    trading_actions: str,
    decision: SizingDecision,
    risk_reason: str | None,
    signal_error: str | None,
    signal_timestamp: datetime | None,
    side: str,
    order_type: str,
    take_profit_price: float | None,
    reference_price: float,
    stop_loss_price: float,
    max_loss_limit_yen: float | None,
    approved_keys: set[str],
    idempotency_key: str,
    global_blockers: Sequence[str],
    allowed_trading_actions: frozenset[str] = DEFAULT_ALLOWED_TRADING_ACTIONS,
) -> list[str]:
    blockers = list(global_blockers)
    if operating_scope == "MONITOR_ONLY":
        blockers.append("MONITOR_ONLY_SCOPE")
    elif operating_scope not in ALLOWED_OPERATING_SCOPES:
        blockers.append("OPERATING_SCOPE_INVALID")
    if trading_actions not in allowed_trading_actions:
        blockers.append("TRADING_ACTIONS_INVALID")
    if decision.status != "READY" or decision.recommended_quantity <= 0:
        blockers.append(f"POSITION_SIZER:{decision.reason}")
    if risk_reason:
        blockers.append(f"RISK:{risk_reason}")
    if signal_error:
        blockers.append(signal_error)
    if signal_timestamp is None:
        blockers.append("SIGNAL_DATE_INVALID")
    if side != SIDE:
        blockers.append("SIDE_NOT_ALLOWED")
    if order_type != ORDER_TYPE:
        blockers.append("ORDER_TYPE_NOT_ALLOWED")
    if take_profit_price is None:
        blockers.append("TAKE_PROFIT_MISSING")
    elif not (stop_loss_price > 0 and stop_loss_price < reference_price < take_profit_price):
        blockers.append("PRICE_RELATION_INVALID")
    estimated_max_loss = round(
        max(reference_price - stop_loss_price, 0.0)
        * max(int(decision.recommended_quantity), 0),
        2,
    )
    if max_loss_limit_yen is not None and estimated_max_loss > max_loss_limit_yen:
        blockers.append("MAX_LOSS_LIMIT_EXCEEDED")
    if idempotency_key in approved_keys:
        blockers.append("DUPLICATE_IDEMPOTENCY_KEY")
    return list(dict.fromkeys(blockers))


def _build_instruction_row(
    *,
    row: Mapping[str, Any],
    decision: SizingDecision,
    generated_at: datetime,
    expires_at: datetime,
    source: str,
    operating_scope: str,
    trading_actions: str,
    approved_keys: set[str],
    global_blockers: Sequence[str],
    client_order_id: str = "",
    lot_size: int = 100,
    max_loss_limit_yen: float | None = None,
    trading_mode: str = DEFAULT_TRADING_MODE,
    execution_mode: str = DEFAULT_EXECUTION_MODE,
    allowed_trading_actions: frozenset[str] = DEFAULT_ALLOWED_TRADING_ACTIONS,
) -> tuple[dict[str, Any], str, bool]:
    signal_text = _first_text(row, ["signal_date", "SignalDate", "生成日時", "generated_at", "signal_timestamp"])
    signal_timestamp, signal_error = _parse_signal_timestamp(signal_text, generated_at)
    signal_date = signal_timestamp.date().isoformat() if signal_timestamp else ""
    side = _first_text(row, ["side", "Side", "売買"], default=SIDE).upper()
    order_type = _first_text(row, ["order_type", "OrderType", "注文種別"], default=ORDER_TYPE).upper()
    take_profit_price = _first_numeric(row, ["take_profit_price", "TakeProfitPrice", "利確価格", "target_price", "目標価格"])
    reference_price = round(float(decision.entry_price), 2)
    limit_price = reference_price
    stop_loss_price = round(float(decision.stop_price), 2)
    quantity = int(decision.recommended_quantity) if decision.executable else 0
    canonical = _instruction_payload(
        generated_at=generated_at,
        signal_date=signal_date or "UNKNOWN",
        ticker=decision.ticker,
        side=side,
        order_type=order_type,
        quantity=quantity,
        lot_size=lot_size,
        reference_price=reference_price,
        limit_price=limit_price,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price or 0.0,
        source=source,
        trading_mode=trading_mode,
        execution_mode=execution_mode,
    )
    idempotency_key = _idempotency_key(canonical)
    blockers = _row_blockers(
        operating_scope=operating_scope,
        trading_actions=trading_actions,
        decision=decision,
        risk_reason=None,
        signal_error=signal_error,
        signal_timestamp=signal_timestamp,
        side=side,
        order_type=order_type,
        take_profit_price=take_profit_price,
        reference_price=reference_price,
        stop_loss_price=stop_loss_price,
        max_loss_limit_yen=max_loss_limit_yen,
        approved_keys=approved_keys,
        idempotency_key=idempotency_key,
        global_blockers=global_blockers,
        allowed_trading_actions=allowed_trading_actions,
    )
    approved = not blockers
    if approved:
        approved_keys.add(idempotency_key)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "intent_id": _intent_id(signal_date, decision.ticker, side, idempotency_key),
        "idempotency_key": idempotency_key,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
        "signal_date": signal_date,
        "ticker": decision.ticker,
        "market": _market_from_ticker(decision.ticker),
        "side": side,
        "order_type": order_type,
        "client_order_id": client_order_id,
        "quantity": quantity if approved else 0,
        "lot_size": canonical["lot_size"],
        "reference_price": reference_price,
        "limit_price": limit_price,
        "stop_loss_price": stop_loss_price,
        "take_profit_price": take_profit_price or 0.0,
        "estimated_notional": round((quantity if approved else 0) * limit_price, 2),
        "estimated_max_loss": round((quantity if approved else 0) * max(limit_price - stop_loss_price, 0.0), 2),
        "source": source,
        "status": "APPROVED" if approved else "BLOCKED",
        "blocked_reasons": ";".join(blockers),
        "created_by": CREATED_BY,
    }
    return payload, idempotency_key, approved


def _fallback_rows(
    *,
    candidate_batch: CandidateInputBatch,
    generated_at: datetime,
    expires_at: datetime,
    source: str,
    operating_scope: str,
    trading_actions: str,
    global_blockers: Sequence[str],
    trading_mode: str,
    execution_mode: str,
    allowed_trading_actions: frozenset[str],
) -> list[dict[str, Any]]:
    approved_keys: set[str] = set()
    rows: list[dict[str, Any]] = []
    for _, raw_row in candidate_batch.candidates.iterrows():
        row_map = raw_row.to_dict()
        ticker = _first_text(row_map, ["ticker", "Ticker"], default="")
        entry_price = _first_numeric(row_map, ["entry_price", "繧ｨ繝ｳ繝医Μ繝ｼ萓｡譬ｼ", "謚ｼ縺礼岼萓｡譬ｼ", "蝓ｺ貅紋ｾ｡譬ｼ"])
        stop_price = _first_numeric(row_map, ["stop_price", "謳榊・萓｡譬ｼ", "stop_loss_price"])
        if not ticker or entry_price is None or stop_price is None:
            row_blockers = list(global_blockers) + ["ROW_NORMALIZATION_FAILED"]
            payload = {
                "schema_version": SCHEMA_VERSION,
                "intent_id": _intent_id("", ticker or "UNKNOWN", SIDE, _stable_hash({"ticker": ticker, "row": row_map})),
                "idempotency_key": _stable_hash({"ticker": ticker, "row": row_map}),
                "generated_at": generated_at.isoformat(timespec="seconds"),
                "expires_at": expires_at.isoformat(timespec="seconds"),
                "trading_mode": trading_mode,
                "execution_mode": execution_mode,
                "signal_date": "",
                "ticker": ticker or "",
                "client_order_id": "",
                "market": _market_from_ticker(ticker or ""),
                "side": SIDE,
                "order_type": ORDER_TYPE,
                "quantity": 0,
                "lot_size": 0,
                "reference_price": entry_price or 0.0,
                "limit_price": entry_price or 0.0,
                "stop_loss_price": stop_price or 0.0,
                "take_profit_price": 0.0,
                "estimated_notional": 0.0,
                "estimated_max_loss": 0.0,
                "source": source,
                "status": "BLOCKED",
                "blocked_reasons": ";".join(dict.fromkeys(row_blockers)),
                "created_by": CREATED_BY,
            }
            rows.append(payload)
            continue
        decision = SizingDecision(
            ticker=ticker,
            name=_first_text(row_map, ["name", "驫俶氛"], default=ticker),
            entry_price=entry_price,
            stop_price=stop_price,
            held_quantity=0,
            risk_quantity=0,
            position_limit_quantity=0,
            cash_limit_quantity=0,
            portfolio_limit_quantity=0,
            maximum_quantity_limit=0,
            recommended_quantity=0,
            estimated_cost_yen=0.0,
            estimated_risk_yen=0.0,
            status="SKIP",
            reason="BROKER_OR_RISK_CONFIGURATION_UNAVAILABLE",
            ranking_score=0.0,
        )
        payload, _, _ = _build_instruction_row(
            row=row_map,
            decision=decision,
            generated_at=generated_at,
            expires_at=expires_at,
            source=source,
            operating_scope=operating_scope,
            trading_actions=trading_actions,
            lot_size=100,
            max_loss_limit_yen=None,
            approved_keys=approved_keys,
            global_blockers=list(global_blockers) + ["BROKER_OR_RISK_CONFIGURATION_UNAVAILABLE"],
            trading_mode=trading_mode,
            execution_mode=execution_mode,
            allowed_trading_actions=allowed_trading_actions,
        )
        rows.append(payload)
    return rows


def _save_state(path: Path, approved_keys: set[str], report: Mapping[str, Any]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": report.get("generated_at", _now_jst().isoformat(timespec="seconds")),
        "last_report_sha256": _stable_hash(report),
        "last_approved_count": int(report.get("approved_count", 0) or 0),
        "last_blocked_count": int(report.get("blocked_count", 0) or 0),
        "approved_idempotency_keys": sorted(approved_keys),
    }
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _load_broker(root: Path, config: Mapping[str, Any]) -> tuple[BrokerAdapter | None, str | None]:
    try:
        broker = create_broker(dict(config), root)
    except Exception as error:
        return None, f"BROKER_CONFIGURATION_INVALID: {type(error).__name__}: {error}"
    try:
        health = broker.health_check()
    except Exception as error:
        return None, f"BROKER_HEALTH_ERROR: {type(error).__name__}: {error}"
    if not health.healthy:
        return None, f"BROKER_HEALTH_FAILED: {health.message}"
    return broker, None


def _load_candidate_batch(
    root: Path,
    policy: CandidateInputPolicy,
) -> tuple[CandidateInputBatch | None, str | None, Path]:
    candidate_path = resolve_path(root, policy.path)
    try:
        batch = load_execution_candidates(candidate_path, policy, repository_root=root)
    except (FileNotFoundError, CandidateInputError, UnicodeError, OSError) as error:
        return None, f"CANDIDATE_INPUT_INVALID: {type(error).__name__}: {error}", candidate_path
    return batch, None, candidate_path


def _decision_reason_map(decisions: Sequence[Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for decision in decisions:
        ticker = str(getattr(decision, "ticker", "")).strip().upper()
        if not ticker:
            continue
        mapping[ticker] = str(getattr(decision, "reason", ""))
    return mapping


def _order_request_lookup_by_ticker(
    orders: Sequence[OrderRequest],
    *,
    label: str,
) -> tuple[dict[str, OrderRequest], list[str]]:
    lookup: dict[str, OrderRequest] = {}
    blockers: list[str] = []
    for order in orders:
        ticker = _normalize_text(getattr(order, "ticker", "")).upper()
        if not ticker:
            blockers.append(f"{label}:TICKER_MISSING")
            continue
        if ticker in lookup:
            blockers.append(f"{label}:DUPLICATE_TICKER:{ticker}")
            continue
        lookup[ticker] = order
    return lookup, blockers


def _order_request_lookup_by_client_order_id(
    orders: Sequence[OrderRequest],
    *,
    label: str,
) -> tuple[dict[str, OrderRequest], list[str]]:
    lookup: dict[str, OrderRequest] = {}
    blockers: list[str] = []
    for order in orders:
        client_order_id = _normalize_text(getattr(order, "client_order_id", ""))
        if not client_order_id:
            blockers.append(f"{label}:CLIENT_ORDER_ID_MISSING")
            continue
        if client_order_id in lookup:
            blockers.append(f"{label}:DUPLICATE_CLIENT_ORDER_ID:{client_order_id}")
            continue
        lookup[client_order_id] = order
    return lookup, blockers


def _approved_payload_lookup_by_client_order_id(
    rows: Sequence[Mapping[str, Any]],
    *,
    label: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    lookup: dict[str, dict[str, Any]] = {}
    blockers: list[str] = []
    for row in rows:
        if _normalize_text(row.get("status", "")).upper() != "APPROVED":
            continue
        client_order_id = _normalize_text(row.get("client_order_id", ""))
        if not client_order_id:
            blockers.append(f"{label}:CLIENT_ORDER_ID_MISSING")
            continue
        if client_order_id in lookup:
            blockers.append(f"{label}:DUPLICATE_CLIENT_ORDER_ID:{client_order_id}")
            continue
        lookup[client_order_id] = dict(row)
    return lookup, blockers


def _count_bridge_queue_entries(root: Path, relative_path: str) -> int:
    path = resolve_path(root, relative_path)
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    try:
        return sum(1 for item in path.iterdir() if item.is_file())
    except OSError:
        return 1


def _live_submit_preflight(root: Path, broker: BrokerAdapter) -> list[str]:
    blockers: list[str] = []
    try:
        broker.refresh_pending_orders()
    except Exception as error:
        raise RuntimeError(f"BROKER_REFRESH_FAILED: {type(error).__name__}: {error}") from error

    nonterminal_count = 0
    if hasattr(broker, "nonterminal_order_count"):
        try:
            nonterminal_count = int(getattr(broker, "nonterminal_order_count")())
        except Exception as error:
            raise RuntimeError(f"BROKER_NONTERMINAL_COUNT_FAILED: {type(error).__name__}: {error}") from error
    if nonterminal_count != 0:
        blockers.append(f"RECONCILE_REQUIRED: BROKER_NONTERMINAL_ORDERS={nonterminal_count}")

    pending_count = _count_bridge_queue_entries(root, PRODUCTION_BRIDGE_PENDING_RELATIVE)
    processing_count = _count_bridge_queue_entries(root, PRODUCTION_BRIDGE_PROCESSING_RELATIVE)
    if pending_count != 0:
        blockers.append(f"RECONCILE_REQUIRED: BRIDGE_PENDING={pending_count}")
    if processing_count != 0:
        blockers.append(f"RECONCILE_REQUIRED: BRIDGE_PROCESSING={processing_count}")
    return blockers


def _resolve_live_dispatch_mode(
    operating_mode: str,
    *,
    broker_health_ok: bool | None = None,
    queue_clear: bool | None = None,
    submit_status: str | None = None,
    submit_error: bool = False,
) -> str:
    normalized_mode = _normalize_text(operating_mode).upper()
    if normalized_mode != "LIVE_ACTIVE":
        return "LIVE_RECONCILE_ONLY" if normalized_mode == "LIVE_RECONCILE_ONLY" else normalized_mode
    if broker_health_ok is False:
        return "LIVE_RECONCILE_ONLY"
    if queue_clear is False:
        return "LIVE_RECONCILE_ONLY"
    if submit_error:
        return "LIVE_RECONCILE_ONLY"
    normalized_status = _normalize_text(submit_status).upper()
    if normalized_status in {"PENDING", "ACCEPTED", "PARTIALLY_FILLED"}:
        return "LIVE_RECONCILE_ONLY"
    return "LIVE_ACTIVE"


@dataclass(frozen=True)
class PreorderDispatchContext:
    report: dict[str, Any]
    generated_at: datetime
    expires_at: datetime
    state_path: Path
    config: dict[str, Any]
    approved_idempotency_keys: frozenset[str]
    report_blockers: tuple[str, ...]
    trade_signals_context: dict[str, Any] | None
    executable_orders_by_client_order_id: dict[str, OrderRequest]
    accepted_orders_by_client_order_id: dict[str, OrderRequest]
    approved_payloads_by_client_order_id: dict[str, dict[str, Any]]


def _build_preorder_dispatch_context(
    *,
    report: dict[str, Any],
    generated: datetime,
    expires_at: datetime,
    state_path: Path,
    config: Mapping[str, Any],
    report_blockers: Sequence[str],
    approved_idempotency_keys: set[str],
    trade_signals_context: dict[str, Any] | None,
    executable_orders_by_client_order_id: dict[str, OrderRequest],
    accepted_orders_by_client_order_id: dict[str, OrderRequest],
    approved_payloads_by_client_order_id: dict[str, dict[str, Any]],
) -> PreorderDispatchContext:
    return PreorderDispatchContext(
        report=report,
        generated_at=generated,
        expires_at=expires_at,
        state_path=state_path,
        config=dict(config),
        approved_idempotency_keys=frozenset(approved_idempotency_keys),
        report_blockers=tuple(dict.fromkeys(str(value) for value in report_blockers)),
        trade_signals_context=trade_signals_context,
        executable_orders_by_client_order_id=executable_orders_by_client_order_id,
        accepted_orders_by_client_order_id=accepted_orders_by_client_order_id,
        approved_payloads_by_client_order_id=approved_payloads_by_client_order_id,
    )


def _build_preorder_report_artifacts(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> tuple[dict[str, Any], PreorderDispatchContext]:
    generated = generated_at or _now_jst()
    expires_at = generated + timedelta(minutes=INSTRUCTION_TTL_MINUTES)
    report_blockers: list[str] = []

    direct_config, direct_error = _read_json(resolve_path(root, DIRECT_PIPELINE_CONFIG))
    if direct_error:
        report_blockers.append(direct_error)
    sizing_source, sizing_error = _read_json(resolve_path(root, POSITION_SIZER_CONFIG))
    if sizing_error:
        report_blockers.append(sizing_error)
    risk_source, risk_error = _read_json(resolve_path(root, RISK_CONFIG_FILE))
    if risk_error:
        report_blockers.append(risk_error)

    try:
        _operating_mode, trading_mode, execution_mode, trading_actions, allowed_trading_actions = _activation_config(direct_config)
    except Exception as error:
        report_blockers.append(f"ACTIVATION_CONFIG_INVALID: {type(error).__name__}: {error}")
        _operating_mode = "PAPER_SAFE"
        trading_mode = DEFAULT_TRADING_MODE
        execution_mode = DEFAULT_EXECUTION_MODE
        trading_actions = DEFAULT_TRADING_ACTIONS
        allowed_trading_actions = DEFAULT_ALLOWED_TRADING_ACTIONS

    candidate_policy_payload = direct_config.get("candidate_input", {}) if isinstance(direct_config, dict) else {}
    try:
        candidate_policy = CandidateInputPolicy.from_mapping(candidate_policy_payload)
    except CandidateInputError as error:
        candidate_policy = None  # type: ignore[assignment]
        report_blockers.append(f"CANDIDATE_POLICY_INVALID: {error}")

    sizing_config = None
    if not sizing_error:
        try:
            sizing_config = _position_sizing_config(sizing_source)
            sizing_config.validate()
        except Exception as error:
            report_blockers.append(f"POSITION_SIZING_INVALID: {type(error).__name__}: {error}")
            sizing_config = None
    risk_config = None
    if not risk_error:
        try:
            risk_config = _risk_config(risk_source)
            risk_config.validate()
        except Exception as error:
            report_blockers.append(f"RISK_CONFIGURATION_INVALID: {type(error).__name__}: {error}")
            risk_config = None
    source_manifest, source_manifest_error = _read_json(resolve_path(root, NOTIFICATION_SOURCE_MANIFEST_FILE))
    if source_manifest_error:
        report_blockers.append(f"NOTIFICATION_SOURCE_MANIFEST_INVALID: {source_manifest_error}")
        source_manifest = {}
    market_context: dict[str, Any] | None = None
    if risk_config is not None:
        market_context, market_context_blockers = _market_regime_context(root, risk_config)
        report_blockers.extend(market_context_blockers)

    operating_scope = _normalize_text(os.environ.get("PHOENIX_OPERATING_SCOPE", "")).upper() or "UNKNOWN"
    if operating_scope not in ALLOWED_OPERATING_SCOPES:
        report_blockers.append("OPERATING_SCOPE_INVALID")
    if trading_actions not in allowed_trading_actions:
        report_blockers.append("TRADING_ACTIONS_INVALID")
    if operating_scope == "MONITOR_ONLY":
        report_blockers.append("MONITOR_ONLY_SCOPE")

    state_path = resolve_path(root, STATE_FILE)
    approved_before, state_error = _parse_state(state_path)
    if state_error:
        report_blockers.append(f"STATE_INVALID: {state_error}")

    candidate_batch: CandidateInputBatch | None = None
    candidate_error: str | None = None
    candidate_path = resolve_path(root, DEFAULT_CANDIDATE_PATH)
    if candidate_policy is not None:
        candidate_batch, candidate_error, candidate_path = _load_candidate_batch(root, candidate_policy)
        if candidate_error:
            report_blockers.append(candidate_error)
    if candidate_batch is None:
        rows = []
        source = str(candidate_path.relative_to(root)) if candidate_path.is_relative_to(root) else str(candidate_path)
        report = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generated_at": generated.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "status": "BLOCKED",
        "mode": trading_mode,
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
        "trading_actions": trading_actions,
        "operating_scope": operating_scope,
            "orders_submitted": 0,
            "external_orders_submitted": 0,
            "candidate_count": 0,
            "approved_count": 0,
            "blocked_count": 0,
            "blockers": list(dict.fromkeys(report_blockers)),
            "candidate_input_guard": None,
            "instructions": rows,
            "instruction_file": str(resolve_path(root, INSTRUCTION_FILE)),
            "report_json": str(resolve_path(root, REPORT_JSON_FILE)),
            "report_text": str(resolve_path(root, REPORT_TEXT_FILE)),
            "audit_jsonl": str(resolve_path(root, AUDIT_JSONL_FILE)),
            "state_file": str(state_path),
            "source": source,
            "created_by": CREATED_BY,
        }
        context = _build_preorder_dispatch_context(
            report=report,
            generated=generated,
            expires_at=expires_at,
            state_path=state_path,
            config=direct_config,
            report_blockers=report_blockers,
            approved_idempotency_keys=set(),
            trade_signals_context=None,
            executable_orders_by_client_order_id={},
            accepted_orders_by_client_order_id={},
            approved_payloads_by_client_order_id={},
        )
        return report, context

    source = str(candidate_path.relative_to(root)) if candidate_path.is_relative_to(root) else str(candidate_path)
    trade_signals_context: dict[str, Any] | None = None
    trade_signals_context_blockers: list[str] = []
    if source_manifest:
        trade_signals_context, trade_signals_context_blockers = _trade_signals_context(
            root,
            candidate_path,
            source_manifest,
        )
        report_blockers.extend(trade_signals_context_blockers)
        if trade_signals_context is not None and int(trade_signals_context.get("trade_signals_row_count", -1)) != len(candidate_batch.candidates):
            report_blockers.append("TRADE_SIGNALS_INVALID: ROW_COUNT_MISMATCH")
            trade_signals_context = None
    rows: list[dict[str, Any]]
    approved_keys = set(approved_before)
    sizing_decisions: list[SizingDecision] = []
    risk_report: Any | None = None
    broker: BrokerAdapter | None = None
    max_loss_limit_yen: float | None = None
    if sizing_config is None or risk_config is None:
        rows = _fallback_rows(
            candidate_batch=candidate_batch,
            generated_at=generated,
            expires_at=expires_at,
            source=source,
            operating_scope=operating_scope,
            trading_actions=trading_actions,
            global_blockers=report_blockers,
            trading_mode=trading_mode,
            execution_mode=execution_mode,
            allowed_trading_actions=allowed_trading_actions,
        )
    else:
        broker, broker_error = _load_broker(root, direct_config)
        if broker_error:
            report_blockers.append(broker_error)
            rows = _fallback_rows(
                candidate_batch=candidate_batch,
                generated_at=generated,
                expires_at=expires_at,
                source=source,
                operating_scope=operating_scope,
                trading_actions=trading_actions,
                global_blockers=report_blockers,
                trading_mode=trading_mode,
                execution_mode=execution_mode,
                allowed_trading_actions=allowed_trading_actions,
            )
        else:
            try:
                effective_total_invested_pct_override = resolve_effective_total_invested_pct(
                    risk_config,
                    market_context,
                )
                sizing_decisions = size_candidates(
                    broker,
                    candidate_batch.candidates,
                    sizing_config,
                    max_total_invested_pct_override=effective_total_invested_pct_override,
                )
            except Exception as error:
                report_blockers.append(f"SIZING_FAILED: {type(error).__name__}: {error}")
                rows = _fallback_rows(
                    candidate_batch=candidate_batch,
                    generated_at=generated,
                    expires_at=expires_at,
                    source=source,
                    operating_scope=operating_scope,
                    trading_actions=trading_actions,
                    global_blockers=report_blockers,
                    trading_mode=trading_mode,
                    execution_mode=execution_mode,
                    allowed_trading_actions=allowed_trading_actions,
                )
            else:
                try:
                    account_snapshot = broker.get_account_snapshot()
                    max_loss_limit_yen = round(
                        float(account_snapshot.equity_yen) * float(risk_config.max_daily_loss_pct),
                        2,
                    )
                except Exception as error:
                    report_blockers.append(f"BROKER_SNAPSHOT_FAILED: {type(error).__name__}: {error}")
                    rows = _fallback_rows(
                        candidate_batch=candidate_batch,
                        generated_at=generated,
                        expires_at=expires_at,
                        source=source,
                        operating_scope=operating_scope,
                        trading_actions=trading_actions,
                        global_blockers=report_blockers,
                        trading_mode=trading_mode,
                        execution_mode=execution_mode,
                        allowed_trading_actions=allowed_trading_actions,
                    )
                else:
                    executable_decisions = [decision for decision in sizing_decisions if decision.executable]
                    run_id = f"PHX42-{candidate_batch.audit.eligible_candidates_sha256[:16].upper()}"
                    executable_orders = build_order_requests(
                        executable_decisions,
                        run_id=run_id,
                    )
                    risk_state: RiskState | None = None
                    if executable_orders:
                        try:
                            risk_state = load_risk_state(resolve_path(root, str(risk_source.get("files", {}).get("state", "state/v7_risk_state.json"))), account_snapshot.equity_yen)
                        except Exception as error:
                            report_blockers.append(f"RISK_STATE_INVALID: {type(error).__name__}: {error}")
                            risk_state = None
                    if executable_orders and risk_state is not None and (not risk_config.risk_v2_enabled or market_context is not None):
                        try:
                            risk_report = evaluate_orders(
                                broker,
                                executable_orders,
                                risk_config,
                                risk_state,
                                market_context=market_context,
                            )
                        except Exception as error:
                            report_blockers.append(f"RISK_EVALUATION_FAILED: {type(error).__name__}: {error}")
                            risk_report = None
                    else:
                        risk_report = None
                    risk_reason_map = _decision_reason_map(getattr(risk_report, "decisions", ()))
                    executable_orders_by_ticker, executable_lookup_blockers = _order_request_lookup_by_ticker(
                        executable_orders,
                        label="EXECUTABLE_ORDERS",
                    )
                    report_blockers.extend(executable_lookup_blockers)
                    executable_orders_by_client_order_id, executable_client_lookup_blockers = _order_request_lookup_by_client_order_id(
                        executable_orders,
                        label="EXECUTABLE_ORDERS",
                    )
                    report_blockers.extend(executable_client_lookup_blockers)
                    accepted_orders_by_client_order_id: dict[str, OrderRequest] = {}
                    accepted_orders_source = getattr(risk_report, "accepted_orders", _MISSING)
                    has_accepted_orders = accepted_orders_source is not _MISSING
                    if risk_report is not None and has_accepted_orders:
                        accepted_orders_by_client_order_id, accepted_client_lookup_blockers = _order_request_lookup_by_client_order_id(
                            accepted_orders_source,
                            label="ACCEPTED_ORDERS",
                        )
                        report_blockers.extend(accepted_client_lookup_blockers)
                        for client_order_id, accepted_order in accepted_orders_by_client_order_id.items():
                            executable_order = executable_orders_by_client_order_id.get(client_order_id)
                            if executable_order is None:
                                report_blockers.append(f"ACCEPTED_ORDER_NOT_IN_EXECUTABLES:{client_order_id}")
                                continue
                            if _normalize_text(accepted_order.client_order_id).upper() != _normalize_text(executable_order.client_order_id).upper():
                                report_blockers.append(f"CLIENT_ORDER_ID_MISMATCH:{client_order_id}")
                    rows = []
                    for row_index, (_, raw_row) in enumerate(candidate_batch.candidates.iterrows()):
                        decision = sizing_decisions[row_index]
                        risk_reason = None
                        client_order_id = ""
                        if decision.executable:
                            executable_order = executable_orders_by_ticker.get(decision.ticker)
                            if executable_order is None:
                                report_blockers.append(f"EXECUTABLE_ORDER_NOT_FOUND:{decision.ticker}")
                            else:
                                client_order_id = executable_order.client_order_id
                                if risk_report is not None and has_accepted_orders:
                                    accepted_order = accepted_orders_by_client_order_id.get(client_order_id)
                                    if accepted_order is None:
                                        risk_reason = risk_reason_map.get(decision.ticker) or "RISK_RESULT_MISSING"
                                    else:
                                        if _normalize_text(accepted_order.ticker).upper() != _normalize_text(executable_order.ticker).upper():
                                            report_blockers.append(f"ACCEPTED_ORDER_TICKER_MISMATCH:{client_order_id}")
                                        client_order_id = accepted_order.client_order_id
                        payload, idempotency_key, approved = _build_instruction_row(
                            row=raw_row.to_dict(),
                            decision=decision,
                            generated_at=generated,
                            expires_at=expires_at,
                            source=source,
                            operating_scope=operating_scope,
                            trading_actions=trading_actions,
                            client_order_id=client_order_id,
                            approved_keys=approved_keys,
                            global_blockers=report_blockers + ([f"RISK:{risk_reason}"] if risk_reason else []),
                            lot_size=sizing_config.lot_size,
                            max_loss_limit_yen=max_loss_limit_yen,
                            trading_mode=trading_mode,
                            execution_mode=execution_mode,
                            allowed_trading_actions=allowed_trading_actions,
                        )
                        rows.append(payload)

    approved_payloads_by_client_order_id, approved_payload_lookup_blockers = _approved_payload_lookup_by_client_order_id(
        rows,
        label="APPROVED_PAYLOADS",
    )
    report_blockers.extend(approved_payload_lookup_blockers)

    rows_frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    approved_count = int((rows_frame.get("status", pd.Series(dtype=str)).astype(str) == "APPROVED").sum()) if not rows_frame.empty else 0
    blocked_count = len(rows_frame) - approved_count
    report_status = "APPROVED" if rows_frame is not None and not rows_frame.empty and blocked_count == 0 and not report_blockers else "BLOCKED"
    if not rows_frame.empty and approved_count == 0 and "NO_APPROVED_ROWS" not in report_blockers:
        report_blockers.append("NO_APPROVED_ROWS")
        report_status = "BLOCKED"
    if "MONITOR_ONLY_SCOPE" in report_blockers:
        report_status = "BLOCKED"

    report = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "generated_at": generated.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "status": report_status,
        "mode": trading_mode,
        "trading_mode": trading_mode,
        "execution_mode": execution_mode,
        "trading_actions": trading_actions,
        "operating_scope": operating_scope,
        "orders_submitted": 0,
        "external_orders_submitted": 0,
        "candidate_count": len(rows_frame),
        "approved_count": approved_count,
        "blocked_count": blocked_count,
        "blockers": list(dict.fromkeys(report_blockers)),
        "candidate_input_guard": candidate_batch.audit.as_dict(),
        "instructions": rows,
        "instruction_file": str(resolve_path(root, INSTRUCTION_FILE)),
        "report_json": str(resolve_path(root, REPORT_JSON_FILE)),
        "report_text": str(resolve_path(root, REPORT_TEXT_FILE)),
        "audit_jsonl": str(resolve_path(root, AUDIT_JSONL_FILE)),
        "state_file": str(state_path),
        "source": source,
        "created_by": CREATED_BY,
    }
    context = _build_preorder_dispatch_context(
        report=report,
        generated=generated,
        expires_at=expires_at,
        state_path=state_path,
        config=direct_config,
        report_blockers=report_blockers,
        approved_idempotency_keys=approved_keys,
        trade_signals_context=trade_signals_context,
        executable_orders_by_client_order_id=executable_orders_by_client_order_id,
        accepted_orders_by_client_order_id=accepted_orders_by_client_order_id,
        approved_payloads_by_client_order_id=approved_payloads_by_client_order_id,
    )
    return report, context


def build_preorder_report(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    report, _ = _build_preorder_report_artifacts(root, generated_at=generated_at)
    return report


def build_preorder_dispatch_context(
    root: Path,
    *,
    generated_at: datetime | None = None,
) -> PreorderDispatchContext:
    _, context = _build_preorder_report_artifacts(root, generated_at=generated_at)
    return context


def text_report(report: Mapping[str, Any]) -> str:
    lines = [
        "PHOENIX v7 STEP42 LOCAL REAL-TRADE BRIDGE PRE-ORDER GATE",
        "=" * 92,
        f"Status               : {report.get('status', '')}",
        f"Mode                 : {report.get('mode', DEFAULT_TRADING_MODE)}",
        f"Trading mode         : {report.get('trading_mode', DEFAULT_TRADING_MODE)}",
        f"Execution mode       : {report.get('execution_mode', DEFAULT_EXECUTION_MODE)}",
        f"Trading actions      : {report.get('trading_actions', '')}",
        f"Operating scope      : {report.get('operating_scope', '')}",
        f"Orders submitted     : {report.get('orders_submitted', 0)}",
        f"Approved instructions: {report.get('approved_count', 0)}",
        f"Blocked instructions : {report.get('blocked_count', 0)}",
        f"Instruction file     : {report.get('instruction_file', '')}",
        f"Audit report         : {report.get('report_json', '')}",
        f"Audit JSONL          : {report.get('audit_jsonl', '')}",
        f"State file           : {report.get('state_file', '')}",
        "-" * 92,
    ]
    blockers = report.get("blockers", [])
    if blockers:
        lines.extend(["Blocking reasons:"] + [f"  - {value}" for value in blockers])
    else:
        lines.append("Blocking reasons: none")
    lines.extend(
        [
            "-" * 92,
            "This gate never submits RSS orders.",
            "Orders submitted: 0",
            "=" * 92,
            "",
        ]
    )
    return "\n".join(lines)


def save_preorder_outputs(root: Path, report: Mapping[str, Any]) -> None:
    instruction_path = resolve_path(root, str(report["instruction_file"]))
    report_json_path = resolve_path(root, str(report["report_json"]))
    report_text_path = resolve_path(root, str(report["report_text"]))
    audit_jsonl_path = resolve_path(root, str(report["audit_jsonl"]))
    state_path = resolve_path(root, str(report["state_file"]))

    rows = report.get("instructions", [])
    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    _write_csv(frame, instruction_path)
    atomic_write(report_json_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    atomic_write(report_text_path, text_report(report))
    audit_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    audit_lines: list[str] = []
    for row in rows:
        audit_lines.append(
            json.dumps(
                {
                    "kind": "instruction",
                    "intent_id": row.get("intent_id", ""),
                    "idempotency_key": row.get("idempotency_key", ""),
                    "ticker": row.get("ticker", ""),
                    "status": row.get("status", ""),
                    "blocked_reasons": row.get("blocked_reasons", ""),
                    "quantity": row.get("quantity", 0),
                    "reference_price": row.get("reference_price", 0),
                    "limit_price": row.get("limit_price", 0),
                    "stop_loss_price": row.get("stop_loss_price", 0),
                    "take_profit_price": row.get("take_profit_price", 0),
                    "trading_mode": row.get("trading_mode", DEFAULT_TRADING_MODE),
                    "execution_mode": row.get("execution_mode", DEFAULT_EXECUTION_MODE),
                    "source": row.get("source", ""),
                    "created_by": row.get("created_by", CREATED_BY),
                },
                ensure_ascii=False,
            )
        )
    audit_lines.append(
        json.dumps(
            {
                "kind": "summary",
                "schema_version": report.get("schema_version", SCHEMA_VERSION),
                "status": report.get("status", ""),
                "generated_at": report.get("generated_at", ""),
                "expires_at": report.get("expires_at", ""),
                "trading_mode": report.get("trading_mode", DEFAULT_TRADING_MODE),
                "execution_mode": report.get("execution_mode", DEFAULT_EXECUTION_MODE),
                "trading_actions": report.get("trading_actions", ""),
                "operating_scope": report.get("operating_scope", ""),
                "orders_submitted": report.get("orders_submitted", 0),
                "approved_count": report.get("approved_count", 0),
                "blocked_count": report.get("blocked_count", 0),
                "blockers": list(report.get("blockers", [])),
                "candidate_input_guard": report.get("candidate_input_guard"),
            },
            ensure_ascii=False,
        )
    )
    atomic_write(audit_jsonl_path, "\n".join(audit_lines) + "\n")

    approved_keys = set()
    for row in rows:
        if row.get("status") == "APPROVED":
            key = str(row.get("idempotency_key", "")).strip()
            if key:
                approved_keys.add(key)
    _save_state(state_path, approved_keys, report)


def print_preorder_summary(report: Mapping[str, Any]) -> None:
    print("=" * 92)
    print("PHOENIX v7 STEP42 LOCAL REAL-TRADE BRIDGE PRE-ORDER GATE")
    print("=" * 92)
    print(f"Status               : {report.get('status', '')}")
    print(f"Trading mode         : {report.get('trading_mode', DEFAULT_TRADING_MODE)}")
    print(f"Execution mode       : {report.get('execution_mode', DEFAULT_EXECUTION_MODE)}")
    print(f"Trading actions      : {report.get('trading_actions', '')}")
    print(f"Approved instructions: {report.get('approved_count', 0)}")
    print(f"Blocked instructions : {report.get('blocked_count', 0)}")
    print(f"Orders submitted     : {report.get('orders_submitted', 0)}")
    print(f"Instruction file     : {report.get('instruction_file', '')}")
    print(f"Audit report         : {report.get('report_json', '')}")
    print(f"Audit JSONL          : {report.get('audit_jsonl', '')}")
    print("=" * 92)


def _persist_live_reconcile_only_mode(root: Path, config: Mapping[str, Any]) -> dict[str, Any]:
    persisted_config = dict(config)
    broker_config = dict(persisted_config.get("broker", {}))
    persisted_config["operating_mode"] = "LIVE_RECONCILE_ONLY"
    persisted_config["trading_mode"] = "LIVE"
    persisted_config["execution_mode"] = "LIVE"
    persisted_config["trading_actions"] = "RECONCILE_ONLY"
    persisted_config["allowed_trading_actions"] = ["RECONCILE_ONLY"]
    broker_config["type"] = "rakuten_rss"
    broker_config["transport_mode"] = "production"
    broker_config["live_trading_enabled"] = True
    broker_config["live_enabled"] = True
    broker_config["production_transport_enabled"] = True
    broker_config["production_live_fire_armed"] = False
    persisted_config["broker"] = broker_config

    config_path = (root / "config" / "v7_direct_pipeline_config.json").resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = config_path.with_name(f"{config_path.name}.tmp")
    temp_path.write_text(json.dumps(persisted_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(config_path)
    return persisted_config


def dispatch_approved_orders(root: Path, context: PreorderDispatchContext) -> list[Any]:
    report = context.report
    operating_mode, trading_mode, execution_mode, trading_actions, _ = _activation_config(context.config)

    if operating_mode == "PAPER_SAFE":
        return []

    report_blockers = tuple(dict.fromkeys(str(value) for value in report.get("blockers", [])))
    if _normalize_text(report.get("status", "")).upper() != "APPROVED":
        raise RuntimeError(f"Dispatch requires APPROVED preorder report: {report.get('status', '')}")
    if report_blockers != context.report_blockers:
        raise RuntimeError("Dispatch report blockers changed after report generation")

    state_approved_idempotency_keys, state_error = _parse_state(context.state_path)
    if state_error is not None:
        raise RuntimeError(f"STATE_INVALID: {state_error}")
    if state_approved_idempotency_keys != set(context.approved_idempotency_keys):
        raise RuntimeError("Approved idempotency keys changed after save")

    if int(report.get("approved_count", 0) or 0) != len(context.approved_payloads_by_client_order_id):
        raise RuntimeError("Approved payload count changed after report generation")

    candidate_path = resolve_path(root, str(report.get("source", DEFAULT_CANDIDATE_PATH)))
    current_source_manifest, source_error = _read_json(resolve_path(root, NOTIFICATION_SOURCE_MANIFEST_FILE))
    if source_error:
        raise RuntimeError(f"NOTIFICATION_SOURCE_MANIFEST_INVALID: {source_error}")
    current_trade_signals_context, trade_signals_blockers = _trade_signals_context(
        root,
        candidate_path,
        current_source_manifest,
    )
    if trade_signals_blockers:
        raise RuntimeError("; ".join(trade_signals_blockers))
    if context.trade_signals_context is None:
        raise RuntimeError("TRADE_SIGNALS_CONTEXT_MISSING")
    if current_trade_signals_context != context.trade_signals_context:
        raise RuntimeError("TRADE_SIGNALS_CONTEXT_CHANGED")

    dispatch_config = dict(context.config)
    broker = create_broker(dict(dispatch_config), root)
    preflight_ran = False
    effective_mode = operating_mode
    reconcile_persisted = False
    try:
        broker_health = broker.health_check()
    except Exception as error:
        broker_health = None
        if operating_mode == "LIVE_ACTIVE":
            effective_mode = _resolve_live_dispatch_mode(
                operating_mode,
                broker_health_ok=False,
            )
            if (
                operating_mode == "LIVE_ACTIVE"
                and effective_mode == "LIVE_RECONCILE_ONLY"
                and not reconcile_persisted
            ):
                dispatch_config = _persist_live_reconcile_only_mode(
                    root,
                    dispatch_config,
                )
                reconcile_persisted = True
        else:
            effective_mode = _resolve_live_dispatch_mode(operating_mode)
    else:
        if operating_mode == "LIVE_ACTIVE":
            effective_mode = _resolve_live_dispatch_mode(
                operating_mode,
                broker_health_ok=bool(broker_health.healthy),
            )
            if (
                operating_mode == "LIVE_ACTIVE"
                and effective_mode == "LIVE_RECONCILE_ONLY"
                and not reconcile_persisted
            ):
                dispatch_config = _persist_live_reconcile_only_mode(
                    root,
                    dispatch_config,
                )
                reconcile_persisted = True

    if effective_mode == "LIVE_ACTIVE" and operating_mode == "LIVE_ACTIVE":
        live_preflight_blockers = _live_submit_preflight(root, broker)
        preflight_ran = True
        if live_preflight_blockers:
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                queue_clear=False,
            )
            if (
                operating_mode == "LIVE_ACTIVE"
                and effective_mode == "LIVE_RECONCILE_ONLY"
                and not reconcile_persisted
            ):
                dispatch_config = _persist_live_reconcile_only_mode(
                    root,
                    dispatch_config,
                )
                reconcile_persisted = True

    if effective_mode == "LIVE_RECONCILE_ONLY":
        if not preflight_ran:
            try:
                broker.refresh_pending_orders()
            except Exception as error:
                raise RuntimeError(f"BROKER_REFRESH_FAILED: {type(error).__name__}: {error}") from error
        return []

    results: list[Any] = []
    for client_order_id, payload in context.approved_payloads_by_client_order_id.items():
        if _normalize_text(payload.get("client_order_id", "")).upper() != _normalize_text(client_order_id).upper():
            raise RuntimeError(f"CLIENT_ORDER_ID_MISMATCH:{client_order_id}")
        accepted_order = context.accepted_orders_by_client_order_id.get(client_order_id)
        if accepted_order is None:
            raise RuntimeError(f"ACCEPTED_ORDER_NOT_FOUND:{client_order_id}")
        if _normalize_text(accepted_order.client_order_id).upper() != _normalize_text(client_order_id).upper():
            raise RuntimeError(f"ACCEPTED_ORDER_IDENTITY_MISMATCH:{client_order_id}")

        live_preflight_blockers = _live_submit_preflight(root, broker)
        if live_preflight_blockers:
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                queue_clear=False,
            )
            if (
                operating_mode == "LIVE_ACTIVE"
                and effective_mode == "LIVE_RECONCILE_ONLY"
                and not reconcile_persisted
            ):
                dispatch_config = _persist_live_reconcile_only_mode(
                    root,
                    dispatch_config,
                )
                reconcile_persisted = True
            break

        try:
            submit_result = broker.submit_order(accepted_order)
        except Exception as error:
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                submit_error=True,
            )
            if (
                operating_mode == "LIVE_ACTIVE"
                and effective_mode == "LIVE_RECONCILE_ONLY"
                and not reconcile_persisted
            ):
                dispatch_config = _persist_live_reconcile_only_mode(
                    root,
                    dispatch_config,
                )
                reconcile_persisted = True
            raise RuntimeError(f"BROKER_SUBMIT_FAILED:{client_order_id}: {type(error).__name__}: {error}") from error

        submit_status = getattr(submit_result, "status", None)
        submit_status_name = _normalize_text(getattr(submit_status, "value", submit_status)).upper()
        if submit_status_name == "REJECTED":
            submit_message = _normalize_text(getattr(submit_result, "message", ""))
            raise RuntimeError(f"BROKER_REJECTED:{client_order_id}:{submit_message}")
        if submit_status_name in {"PENDING", "ACCEPTED", "PARTIALLY_FILLED"}:
            results.append(submit_result)
            effective_mode = _resolve_live_dispatch_mode(
                effective_mode,
                submit_status=submit_status_name,
            )
            if (
                operating_mode == "LIVE_ACTIVE"
                and effective_mode == "LIVE_RECONCILE_ONLY"
                and not reconcile_persisted
            ):
                dispatch_config = _persist_live_reconcile_only_mode(
                    root,
                    dispatch_config,
                )
                reconcile_persisted = True
            break
        if submit_status_name != "FILLED":
            raise RuntimeError(f"UNEXPECTED_BROKER_STATUS:{client_order_id}:{submit_status_name}")
        results.append(submit_result)

    return results


def run_order_bridge_gate(
    root: Path,
    *,
    context: PreorderDispatchContext | None = None,
) -> dict[str, Any]:
    if context is None:
        context = build_preorder_dispatch_context(root)
    report = context.report
    save_preorder_outputs(root, report)
    dispatch_approved_orders(root, context)
    return report


## FILE: phoenix_core/production_rakuten_rss_transport.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Mapping, Protocol, runtime_checkable
from zoneinfo import ZoneInfo
import zipfile
from xml.etree import ElementTree as ET

from phoenix_core.models import OrderRequest, OrderSide, OrderStatus, OrderType
from phoenix_core.production_rakuten_rss_adapter import RakutenRssTransportHealth
from phoenix_core.rss_order_bridge import FileBridgeReceipt, FileBridgeStageResult, read_receipt, stage_request
from phoenix_core.rakuten_rss_adapter import (
    RakutenRssCancelAck,
    RakutenRssOrderUpdate,
    RakutenRssSubmitAck,
)


JST = ZoneInfo("Asia/Tokyo")
ORDER_MACRO_NAME = "RssStockOrder_V"
CANCEL_MACRO_NAME = "RssCancelOrder_V"
ORDER_ID_LIST_MACRO_NAME = "RssOrderIDList"
ORDER_STATUS_MACRO_NAME = "RssOrderStatus"
DEFAULT_WORKBOOK_NAME = "PHOENIX_RSS_PRODUCTION.xlsm"
PHOENIX_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK_PATH = (PHOENIX_ROOT / "runtime" / "v7_rss_production" / DEFAULT_WORKBOOK_NAME).resolve()
TRANSPORT_SHEET_NAME = "PHOENIX_RSS_TRANSPORT"
TRANSPORT_SOURCE_COM_LIVE = "COM_LIVE"
TRANSPORT_SOURCE_FILE_READY = "FILE_READY"
TRANSPORT_SOURCE_FILE_FALLBACK = "FILE_FALLBACK"
TRANSPORT_SOURCE_DISCONNECTED = "DISCONNECTED"

WORKBOOK_STATE_EXCEL_ALIVE_CELL = "J2"
WORKBOOK_STATE_RSS_CONNECTED_CELL = "J3"
WORKBOOK_STATE_ADDIN_READY_CELL = "J4"
WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL = "J5"
WORKBOOK_STATE_HEARTBEAT_CELL = "J6"
WORKBOOK_STATE_CELL_MAP = (
    WORKBOOK_STATE_EXCEL_ALIVE_CELL,
    WORKBOOK_STATE_RSS_CONNECTED_CELL,
    WORKBOOK_STATE_ADDIN_READY_CELL,
    WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL,
    WORKBOOK_STATE_HEARTBEAT_CELL,
)
WORKBOOK_STATE_MAX_AGE = timedelta(seconds=90)

SUBMIT_CELL_MAP = {
    "schema_version": "B2",
    "request_kind": "B3",
    "broker_order_id": "B4",
    "client_order_id": "B5",
    "strategy_name": "B6",
    "ticker": "B7",
    "side": "B8",
    "quantity": "B9",
    "order_type": "B10",
    "limit_price": "B11",
    "live_trading_enabled": "B12",
    "production_transport_enabled": "B13",
    "armed": "B14",
    "submitted_at": "B15",
    "timeout_seconds": "B16",
    "payload_sha256": "B17",
    "macro_name": "B18",
    "message": "B19",
}
RESULT_CELL_MAP = {
    "status": "D2",
    "broker_order_id": "D3",
    "filled_quantity": "D4",
    "filled_price": "D5",
    "message": "D6",
    "updated_at": "D7",
}
CANCEL_CELL_MAP = {
    "schema_version": "B22",
    "request_kind": "B23",
    "broker_order_id": "B24",
    "client_order_id": "B25",
    "action": "B26",
    "submitted_at": "B27",
    "payload_sha256": "B28",
    "macro_name": "B29",
    "message": "B30",
}
RSS_CONNECTION_CELL = "B3"
RSS_CONNECTION_MESSAGE_CELL = "B4"
RSS_PROBE_CELL = "XFD1"
RSS_PROBE_FORMULA = "=RSS|'9501.T'!銘柄名称"
RSS_CONNECTED_STATUS = "CONNECTED"
RSS_NOT_CONNECTED_STATUS = "NOT_CONNECTED"
REQUIRED_RSS_ADDIN_NAMES = (
    "MarketSpeed2_RSS_64bit.xll",
    "MarketSpeed2_RSS_VBA.xlam",
)

MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _now_jst() -> datetime:
    return datetime.now(JST)


def _resolve_phoenix_root_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PHOENIX_ROOT / candidate
    candidate = candidate.resolve()
    if candidate != PHOENIX_ROOT and PHOENIX_ROOT not in candidate.parents:
        raise ValueError(f"Path escapes PHOENIX root: {candidate}")
    return candidate


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_order_status(value: Any) -> OrderStatus:
    raw_text = str(value).strip()
    text = raw_text.upper()
    if not text:
        raise ValueError("status is missing")
    if raw_text in {"有効", "VALID", "ACTIVE"}:
        return OrderStatus.ACCEPTED
    if raw_text in {"無効", "該当なし", "不一致"}:
        return OrderStatus.REJECTED
    if text in {"NOT_VALID", "NO_MATCH", "NOT_FOUND", "MISMATCH"}:
        return OrderStatus.REJECTED
    return OrderStatus(text)


def _metadata_value(order: Any, *names: str, default: Any = None) -> Any:
    metadata = getattr(order, "metadata", None)
    if isinstance(metadata, Mapping):
        for name in names:
            value = metadata.get(name)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            return value
    return default


def _expiration_yyyymmdd(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.strftime("%Y%m%d")


def _stable_rss_order_id(client_order_id: str, broker_order_id: str) -> int:
    digest = hashlib.sha256(f"{client_order_id}|{broker_order_id}".encode("utf-8")).hexdigest()
    value = int(digest[:16], 16) % 2147483647
    return value + 1


def _normalize_rss_order_id_entry(value: Any) -> RakutenRssOrderIdEntry | None:
    if value is None:
        return None

    if isinstance(value, Mapping):
        raw_id = value.get("rss_order_id", value.get("order_id", value.get("発注ID", "")))
        raw_function = value.get("function_name", value.get("関数名", ""))
        raw_order_date = value.get("order_date", value.get("発注日", ""))
        raw_order_time = value.get("order_time", value.get("発注時刻", ""))
        raw_order_number = value.get("order_number", value.get("注文番号", ""))
        raw_result = value.get("result", value.get("発注結果", ""))
    elif isinstance(value, (list, tuple)):
        if len(value) < 6:
            return None
        raw_id, raw_function, raw_order_date, raw_order_time, raw_order_number, raw_result = value[:6]
    else:
        return None

    try:
        rss_order_id = int(str(raw_id).strip())
    except Exception:
        return None
    if rss_order_id < 1 or rss_order_id > 2147483647:
        return None

    return RakutenRssOrderIdEntry(
        rss_order_id=rss_order_id,
        function_name=str(raw_function or "").strip(),
        order_date=str(raw_order_date or "").strip(),
        order_time=str(raw_order_time or "").strip(),
        order_number=str(raw_order_number or "").strip(),
        result=str(raw_result or "").strip(),
    )


def _normalize_rss_order_id_entries(value: Any) -> tuple[RakutenRssOrderIdEntry, ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        entry = _normalize_rss_order_id_entry(value)
        return () if entry is None else (entry,)
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            return ()
        first_entry = _normalize_rss_order_id_entry(value)
        if first_entry is not None:
            return (first_entry,)
        entries: list[RakutenRssOrderIdEntry] = []
        for row in value:
            entry = _normalize_rss_order_id_entry(row)
            if entry is not None:
                entries.append(entry)
        return tuple(entries)
    entry = _normalize_rss_order_id_entry(value)
    return () if entry is None else (entry,)


def _sheet_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if value is None:
        return ""
    return value


def _cell_text_from_sheet_xml(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = str(cell.get("t") or "").strip()
    if cell_type == "s":
        raw_value = cell.findtext(f"{MAIN_NS}v")
        if raw_value is None:
            return ""
        index = int(raw_value)
        if 0 <= index < len(shared_strings):
            return shared_strings[index]
        return ""
    if cell_type == "inlineStr":
        return "".join(cell.itertext()).strip()
    if cell_type == "b":
        return "TRUE" if str(cell.findtext(f"{MAIN_NS}v") or "").strip() == "1" else "FALSE"
    return str(cell.findtext(f"{MAIN_NS}v") or "").strip()


def _read_workbook_health_cells(
    workbook_path: Path,
    sheet_name: str,
    cell_refs: tuple[str, ...],
) -> dict[str, str]:
    if not workbook_path.is_file():
        raise WorkbookNotFoundError(f"Workbook not found: {workbook_path}")

    with zipfile.ZipFile(workbook_path) as archive:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for entry in shared_root.findall(f"{MAIN_NS}si"):
                shared_strings.append("".join(entry.itertext()).strip())

        rel_targets = {
            rel.get("Id"): rel.get("Target")
            for rel in rels_root.findall(f"{PKG_REL_NS}Relationship")
            if rel.get("Id") and rel.get("Target")
        }

        sheet_target: str | None = None
        for sheet in workbook_root.findall(f"{MAIN_NS}sheets/{MAIN_NS}sheet"):
            if str(sheet.get("name") or "") == sheet_name:
                rel_id = sheet.get(f"{REL_NS}id")
                if rel_id:
                    sheet_target = rel_targets.get(rel_id)
                break

        if not sheet_target:
            raise RssNotConnectedError(f"Workbook sheet missing: {sheet_name}")

        sheet_path = sheet_target.lstrip("/")
        if not sheet_path.startswith("xl/"):
            sheet_path = f"xl/{sheet_path}"
        sheet_root = ET.fromstring(archive.read(sheet_path))

        values: dict[str, str] = {}
        for cell_ref in cell_refs:
            cell = sheet_root.find(f".//{MAIN_NS}c[@r='{cell_ref}']")
            values[cell_ref] = "" if cell is None else _cell_text_from_sheet_xml(cell, shared_strings)
        return values


@dataclass(frozen=True, slots=True)
class ExcelTransportSession:
    application: Any
    workbook: Any
    workbook_path: Path
    workbook_name: str


@dataclass(frozen=True, slots=True)
class _ResolvedWorkbookOwner:
    application: Any
    workbook: Any
    workbook_full_name: Path
    display_name: str = ""


@dataclass(frozen=True, slots=True)
class WorkbookRuntimeState:
    transport_source: str
    excel_alive: bool
    rss_connected: bool
    addin_ready: bool
    order_transport_ready: bool
    heartbeat_at: datetime | None
    heartbeat_age_seconds: float | None
    ready: bool
    message: str


@dataclass(frozen=True, slots=True)
class RakutenRssOrderIdEntry:
    rss_order_id: int
    function_name: str
    order_date: str
    order_time: str
    order_number: str
    result: str


def _runtime_truthy_cell(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    return text in {"1", "TRUE", "YES", "ON", "READY", "CONNECTED", "RSS_CONNECTED"}


def _runtime_parse_heartbeat(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = datetime(1899, 12, 30, tzinfo=JST) + timedelta(days=float(value))
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            if text.replace(".", "", 1).isdigit():
                parsed = datetime(1899, 12, 30, tzinfo=JST) + timedelta(days=float(text))
            else:
                return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=JST)
    return parsed.astimezone(JST)


def _runtime_state_from_values(values: Mapping[str, Any], *, transport_source: str, now: datetime | None = None) -> WorkbookRuntimeState:
    now_jst = _now_jst() if now is None else now.astimezone(JST) if now.tzinfo is not None and now.utcoffset() is not None else now.replace(tzinfo=JST)
    excel_alive = _runtime_truthy_cell(values.get(WORKBOOK_STATE_EXCEL_ALIVE_CELL, ""))
    rss_connected = _runtime_truthy_cell(values.get(WORKBOOK_STATE_RSS_CONNECTED_CELL, ""))
    addin_ready = _runtime_truthy_cell(values.get(WORKBOOK_STATE_ADDIN_READY_CELL, ""))
    order_transport_ready = _runtime_truthy_cell(values.get(WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL, ""))
    heartbeat_at = _runtime_parse_heartbeat(values.get(WORKBOOK_STATE_HEARTBEAT_CELL, ""))
    heartbeat_age_seconds: float | None = None
    heartbeat_fresh = False
    blockers: list[str] = []

    if not excel_alive:
        blockers.append("Excel alive is false")
    if not rss_connected:
        blockers.append("RSS is not connected")
    if not addin_ready:
        blockers.append("RSS add-in is not ready")
    if not order_transport_ready:
        blockers.append("Order transport is not ready")
    if heartbeat_at is None:
        blockers.append("Heartbeat is missing")
    else:
        heartbeat_age = now_jst - heartbeat_at
        heartbeat_age_seconds = heartbeat_age.total_seconds()
        if heartbeat_age < timedelta(0):
            blockers.append("Heartbeat timestamp is in the future")
        elif heartbeat_age <= WORKBOOK_STATE_MAX_AGE:
            heartbeat_fresh = True
        else:
            blockers.append(
                f"Heartbeat is stale ({int(heartbeat_age.total_seconds())}s > {int(WORKBOOK_STATE_MAX_AGE.total_seconds())}s)"
            )

    ready = not blockers and heartbeat_fresh
    if ready:
        message = "Workbook transport READY."
        transport_source = transport_source if transport_source != TRANSPORT_SOURCE_FILE_FALLBACK else TRANSPORT_SOURCE_FILE_READY
    else:
        message = "; ".join(blockers) if blockers else "Workbook transport is not READY."

    return WorkbookRuntimeState(
        transport_source=transport_source,
        excel_alive=excel_alive,
        rss_connected=rss_connected,
        addin_ready=addin_ready,
        order_transport_ready=order_transport_ready,
        heartbeat_at=heartbeat_at,
        heartbeat_age_seconds=heartbeat_age_seconds,
        ready=ready,
        message=message,
    )


class ExcelComError(RuntimeError):
    pass


class ExcelNotRunningError(ExcelComError):
    pass


class WorkbookNotFoundError(ExcelComError):
    pass


class RssNotConnectedError(ExcelComError):
    pass


@runtime_checkable
class ExcelComBackend(Protocol):
    def connect(self, workbook_path: Path, workbook_name: str) -> ExcelTransportSession:
        raise NotImplementedError

    def read_runtime_state(self, session: ExcelTransportSession) -> WorkbookRuntimeState:
        raise NotImplementedError

    def health_check(
        self,
        session: ExcelTransportSession,
        publish: bool = False,
    ) -> tuple[bool, str]:
        raise NotImplementedError

    def stage_submit_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError

    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        raise NotImplementedError

    def read_order_updates(
        self,
        session: ExcelTransportSession,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        raise NotImplementedError

    def read_rss_order_ledger(
        self,
        session: ExcelTransportSession,
    ) -> tuple[RakutenRssOrderIdEntry, ...]:
        raise NotImplementedError

    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
        raise NotImplementedError

    def stage_cancel_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        raise NotImplementedError

    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        raise NotImplementedError

    def close(self, session: ExcelTransportSession) -> None:
        raise NotImplementedError


@dataclass(slots=True)
class _MockSession:
    application: object = field(default_factory=object)
    workbook: object = field(default_factory=object)


class MockExcelComBackend:
    def __init__(
        self,
        *,
        excel_running: bool = True,
        workbook_present: bool = True,
        rss_connected: bool = True,
        addin_ready: bool = True,
        order_transport_ready: bool = True,
        heartbeat_at: datetime | None = None,
        health_message: str = "MOCK_EXCEL_RSS_READY",
    ) -> None:
        self.excel_running = excel_running
        self.workbook_present = workbook_present
        self.rss_connected = rss_connected
        self.addin_ready = addin_ready
        self.order_transport_ready = order_transport_ready
        self.heartbeat_at = heartbeat_at
        self.health_message = health_message
        self.connect_calls = 0
        self.health_calls = 0
        self.submit_stage_calls = 0
        self.submit_macro_calls = 0
        self.submit_macro_args: list[tuple[Any, ...]] = []
        self.poll_calls = 0
        self.cancel_stage_calls = 0
        self.cancel_macro_calls = 0
        self.cancel_macro_args: list[tuple[Any, ...]] = []
        self.closed_calls = 0
        self.submitted_payloads: list[dict[str, Any]] = []
        self.cancel_payloads: list[dict[str, Any]] = []
        self.publish_calls = 0
        self._updates_by_broker_order_id: dict[str, list[RakutenRssOrderUpdate]] = {}
        self._rss_order_ledger_entries: list[RakutenRssOrderIdEntry] = []
        self._rss_order_status_by_id: dict[int, int] = {}
        self.rss_order_ledger_calls = 0
        self.rss_order_status_calls = 0

    def queue_updates(
        self,
        broker_order_id: str,
        updates: list[RakutenRssOrderUpdate],
    ) -> None:
        self._updates_by_broker_order_id[broker_order_id] = list(updates)

    def queue_rss_order_ledger_entry(
        self,
        rss_order_id: int,
        *,
        function_name: str = ORDER_MACRO_NAME,
        order_number: str = "",
        result: str = "",
        order_date: str = "",
        order_time: str = "",
    ) -> None:
        self._rss_order_ledger_entries = [
            entry for entry in self._rss_order_ledger_entries if entry.rss_order_id != rss_order_id
        ]
        self._rss_order_ledger_entries.append(
            RakutenRssOrderIdEntry(
                rss_order_id=rss_order_id,
                function_name=function_name,
                order_date=order_date,
                order_time=order_time,
                order_number=order_number,
                result=result,
            )
        )

    def set_rss_order_status(self, rss_order_id: int, status: int) -> None:
        self._rss_order_status_by_id[rss_order_id] = int(status)

    def connect(self, workbook_path: Path, workbook_name: str) -> ExcelTransportSession:
        self.connect_calls += 1
        if not self.excel_running:
            raise ExcelNotRunningError("Excel is not running.")
        if not self.workbook_present:
            raise WorkbookNotFoundError(f"Workbook not found: {workbook_path}")
        return ExcelTransportSession(
            application=_MockSession().application,
            workbook=_MockSession().workbook,
            workbook_path=workbook_path,
            workbook_name=workbook_name,
        )

    def read_runtime_state(self, session: ExcelTransportSession) -> WorkbookRuntimeState:
        heartbeat_at = self.heartbeat_at or _now_jst()
        values = {
            WORKBOOK_STATE_EXCEL_ALIVE_CELL: self.excel_running and self.workbook_present,
            WORKBOOK_STATE_RSS_CONNECTED_CELL: self.rss_connected,
            WORKBOOK_STATE_ADDIN_READY_CELL: self.addin_ready,
            WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL: self.order_transport_ready,
            WORKBOOK_STATE_HEARTBEAT_CELL: heartbeat_at,
        }
        return _runtime_state_from_values(values, transport_source=TRANSPORT_SOURCE_COM_LIVE, now=heartbeat_at)

    def health_check(
        self,
        session: ExcelTransportSession,
        publish: bool = False,
    ) -> tuple[bool, str]:
        self.health_calls += 1
        runtime_state = self.read_runtime_state(session)
        if not runtime_state.ready:
            return False, runtime_state.message
        if not self.rss_connected:
            return False, "RSS is not connected."
        if publish:
            self.publish_calls += 1
            self.heartbeat_at = _now_jst()
        return True, self.health_message

    def stage_submit_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self.submit_stage_calls += 1
        self.submitted_payloads.append(dict(payload))

    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        self.submit_macro_calls += 1
        self.submit_macro_args.append(tuple(args))

    def read_order_updates(
        self,
        session: ExcelTransportSession,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        self.poll_calls += 1
        updates = self._updates_by_broker_order_id.get(broker_order_id, [])
        if not updates:
            return ()
        self._updates_by_broker_order_id[broker_order_id] = []
        return tuple(updates)

    def read_rss_order_ledger(
        self,
        session: ExcelTransportSession,
    ) -> tuple[RakutenRssOrderIdEntry, ...]:
        self.rss_order_ledger_calls += 1
        return tuple(self._rss_order_ledger_entries)

    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
        self.rss_order_status_calls += 1
        return int(self._rss_order_status_by_id.get(int(rss_order_id), -1))

    def stage_cancel_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self.cancel_stage_calls += 1
        self.cancel_payloads.append(dict(payload))

    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        self.cancel_macro_calls += 1
        self.cancel_macro_args.append(tuple(args))

    def close(self, session: ExcelTransportSession) -> None:
        self.closed_calls += 1


class Win32ComExcelBackend:
    def __init__(
        self,
        *,
        transport_sheet_name: str = TRANSPORT_SHEET_NAME,
    ) -> None:
        self._transport_sheet_name = transport_sheet_name

    def _require_win32(self) -> tuple[Any, Any]:
        if importlib.util.find_spec("win32com.client") is None or importlib.util.find_spec("pythoncom") is None:
            raise ExcelComError("win32com/pythoncom are not available.")
        from win32com import client as win32_client  # type: ignore[import-not-found]
        import pythoncom  # type: ignore[import-not-found]

        return win32_client, pythoncom

    @staticmethod
    def _workbook_full_name(value: Any) -> Path | None:
        try:
            return Path(str(value.FullName)).resolve()
        except Exception:
            return None

    @staticmethod
    def _application_identity(application: Any, workbook: Any | None = None) -> str:
        for owner in (
            application,
            workbook,
            getattr(workbook, "Application", None) if workbook is not None else None,
        ):
            if owner is None:
                continue
            try:
                return f"hwnd:{int(getattr(owner, 'Hwnd'))}"
            except Exception:
                continue
        return f"object:{id(application)}"

    def _rot_candidates_from_object(
        self,
        obj: Any,
        *,
        target_path: Path,
        display_name: str,
    ) -> list[_ResolvedWorkbookOwner]:
        candidates: list[_ResolvedWorkbookOwner] = []
        try:
            workbooks = getattr(obj, "Workbooks")
        except Exception:
            workbooks = None

        if workbooks is not None:
            try:
                workbook_iterable = list(workbooks)
            except Exception:
                workbook_iterable = []
            for workbook in workbook_iterable:
                workbook_full_name = self._workbook_full_name(workbook)
                if workbook_full_name != target_path:
                    continue
                application = obj
                try:
                    workbook_application = getattr(workbook, "Application", None)
                except Exception:
                    workbook_application = None
                if workbook_application is not None:
                    application = workbook_application
                candidates.append(
                    _ResolvedWorkbookOwner(
                        application=application,
                        workbook=workbook,
                        workbook_full_name=workbook_full_name,
                        display_name=display_name,
                    )
                )
            return candidates

        workbook_full_name = self._workbook_full_name(obj)
        if workbook_full_name != target_path:
            return candidates
        try:
            workbook_application = getattr(obj, "Application", None)
        except Exception:
            workbook_application = None
        if workbook_application is None:
            return candidates
        candidates.append(
            _ResolvedWorkbookOwner(
                application=workbook_application,
                workbook=obj,
                workbook_full_name=workbook_full_name,
                display_name=display_name,
            )
        )
        return candidates

    def _resolve_canonical_owner(
        self,
        workbook_path: Path,
        workbook_name: str,
    ) -> ExcelTransportSession:
        _, pythoncom = self._require_win32()
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

        workbook_path = workbook_path.resolve()
        if not workbook_path.is_file():
            raise WorkbookNotFoundError(f"Workbook not found: {workbook_path}")

        try:
            rot = pythoncom.GetRunningObjectTable()
        except Exception as error:
            raise ExcelComError(f"Excel ROT is unavailable: {error}") from error
        try:
            bind_ctx = pythoncom.CreateBindCtx(0)
        except Exception as error:
            raise ExcelComError(f"Excel bind context is unavailable: {error}") from error
        try:
            enum_moniker = rot.EnumRunning()
        except Exception as error:
            raise ExcelComError(f"Excel ROT enumeration failed: {error}") from error

        matches: list[_ResolvedWorkbookOwner] = []
        seen_candidates: set[tuple[Path, str]] = set()
        moniker_logs: list[str] = []

        while True:
            try:
                fetched = enum_moniker.Next(1)
            except Exception as error:
                raise ExcelComError(f"Excel ROT enumeration failed: {error}") from error
            if not fetched:
                break

            moniker = fetched[0]
            display_name = ""
            try:
                display_name = str(moniker.GetDisplayName(bind_ctx, None)).strip()
            except Exception:
                display_name = ""
            if display_name:
                moniker_logs.append(display_name)

            try:
                rot_object = rot.GetObject(moniker)
            except Exception:
                continue

            for candidate in self._rot_candidates_from_object(
                rot_object,
                target_path=workbook_path,
                display_name=display_name,
            ):
                candidate_key = (
                    candidate.workbook_full_name,
                    self._application_identity(candidate.application, candidate.workbook),
                )
                if candidate_key in seen_candidates:
                    continue
                seen_candidates.add(candidate_key)
                matches.append(candidate)

        if len(matches) != 1:
            if len(matches) == 0:
                suffix = f"; ROT monikers={moniker_logs!r}" if moniker_logs else ""
                raise ExcelComError(f"Canonical workbook owner not found in ROT: {workbook_path}{suffix}")
            owner_summaries = ", ".join(
                f"{candidate.display_name or '<unnamed>'} -> {candidate.workbook_full_name}"
                for candidate in matches
            )
            raise ExcelComError(
                f"Canonical workbook owner is ambiguous in ROT: {workbook_path}; matches={owner_summaries}"
            )

        owner = matches[0]
        return ExcelTransportSession(
            application=owner.application,
            workbook=owner.workbook,
            workbook_path=workbook_path,
            workbook_name=workbook_name,
        )

    def connect(self, workbook_path: Path, workbook_name: str) -> ExcelTransportSession:
        try:
            return self._resolve_canonical_owner(workbook_path, workbook_name)
        except ExcelComError:
            raise
        except Exception as error:
            raise ExcelComError(f"Excel connection failed: {error}") from error

    def _sheet(self, session: ExcelTransportSession) -> Any:
        try:
            return session.workbook.Worksheets(self._transport_sheet_name)
        except Exception as error:
            raise RssNotConnectedError(
                f"Workbook sheet missing: {self._transport_sheet_name}"
            ) from error

    def _read_status_values(self, session: ExcelTransportSession) -> tuple[Any, Any, Any]:
        sheet = self._sheet(session)
        try:
            ready_value = sheet.Range(RSS_CONNECTION_CELL).Value2
            status_value = sheet.Range(RSS_CONNECTION_MESSAGE_CELL).Value2
        except Exception as error:
            raise RssNotConnectedError("Transport sheet status is unreadable.") from error
        return False, ready_value, status_value

    def _read_runtime_values(self, session: ExcelTransportSession) -> dict[str, Any]:
        sheet = self._sheet(session)
        values: dict[str, Any] = {}
        try:
            for cell_ref in WORKBOOK_STATE_CELL_MAP:
                values[cell_ref] = sheet.Range(cell_ref).Value2
        except Exception as error:
            raise RssNotConnectedError("Transport runtime state is unreadable.") from error
        return values

    def _has_required_addins(self, application: Any) -> tuple[bool, str]:
        try:
            addins = list(application.AddIns)
        except Exception as error:
            raise ExcelComError(f"Excel add-in list is unavailable: {error}") from error

        status_lines: list[str] = []
        for required_name in REQUIRED_RSS_ADDIN_NAMES:
            match = None
            for addin in addins:
                try:
                    if str(getattr(addin, "Name", "")).strip().lower() == required_name.lower():
                        match = addin
                        break
                except Exception:
                    continue
            if match is None:
                return False, f"Missing RSS add-in: {required_name}"
            try:
                installed = bool(match.Installed)
            except Exception as error:
                raise ExcelComError(f"RSS add-in state is unreadable for {required_name}: {error}") from error
            if not installed:
                return False, f"RSS add-in is not installed: {required_name}"
            try:
                full_name = str(match.FullName)
            except Exception:
                full_name = required_name
            status_lines.append(f"{required_name}={full_name}")
        return True, "; ".join(status_lines)

    @staticmethod
    def _is_truthy_cell(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().upper()
        return text in {"1", "TRUE", "YES", "ON", "READY"}

    @staticmethod
    def _is_connected_status(value: Any) -> bool:
        text = str(value).strip().upper()
        return text in {"1", "TRUE", "YES", "ON", "CONNECTED", "RSS_CONNECTED", "RSS 接続中"}

    def _probe_rss_connection(self, session: ExcelTransportSession) -> tuple[bool, str]:
        application = session.application
        try:
            probe_value = application.Evaluate(RSS_PROBE_FORMULA)
            if self._is_connected_status(probe_value) or str(probe_value).strip():
                text = str(probe_value).strip()
                if text and not text.startswith("#"):
                    return True, text
        except Exception:
            pass

        sheet = self._sheet(session)
        probe_cell = sheet.Range(RSS_PROBE_CELL)
        try:
            probe_cell.Formula = RSS_PROBE_FORMULA
            try:
                application.CalculateFull()
            except Exception:
                try:
                    application.Calculate()
                except Exception:
                    pass
            probe_value = probe_cell.Value2
            text = str(probe_value).strip()
            if text and not text.startswith("#"):
                return True, text
            return False, f"RSS probe returned {text!r}"
        except Exception as error:
            return False, f"RSS probe failed: {error}"
        finally:
            try:
                probe_cell.ClearContents()
            except Exception:
                pass

    def _write_rss_status(self, session: ExcelTransportSession, value: str) -> None:
        sheet = self._sheet(session)
        try:
            sheet.Range(RSS_CONNECTION_MESSAGE_CELL).Value2 = value
        except Exception as error:
            raise RssNotConnectedError(f"Failed to write RSS status: {error}") from error

    def _write_runtime_state(self, session: ExcelTransportSession, values: Mapping[str, Any]) -> None:
        sheet = self._sheet(session)
        for cell_ref in WORKBOOK_STATE_CELL_MAP:
            try:
                sheet.Range(cell_ref).Value2 = _sheet_value(values.get(cell_ref, ""))
            except Exception as error:
                raise RssNotConnectedError(f"Failed to write transport runtime state to {cell_ref}: {error}") from error

    def read_runtime_state(self, session: ExcelTransportSession) -> WorkbookRuntimeState:
        values = self._read_runtime_values(session)
        return _runtime_state_from_values(values, transport_source=TRANSPORT_SOURCE_COM_LIVE)

    def health_check(
        self,
        session: ExcelTransportSession,
        publish: bool = False,
    ) -> tuple[bool, str]:
        try:
            addins_ok, addins_message = self._has_required_addins(session.application)
            if not addins_ok:
                return False, addins_message

            probe_ok, probe_message = self._probe_rss_connection(session)
            if not probe_ok:
                return False, probe_message

            if publish:
                heartbeat_at = _now_jst()
                self._write_rss_status(session, RSS_CONNECTED_STATUS)
                self._write_runtime_state(
                    session,
                    {
                        WORKBOOK_STATE_EXCEL_ALIVE_CELL: True,
                        WORKBOOK_STATE_RSS_CONNECTED_CELL: True,
                        WORKBOOK_STATE_ADDIN_READY_CELL: True,
                        WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL: True,
                        WORKBOOK_STATE_HEARTBEAT_CELL: heartbeat_at.isoformat(timespec="seconds"),
                    },
                )
            runtime_state = self.read_runtime_state(session)
            if not runtime_state.ready:
                return False, runtime_state.message
            live_message = str(probe_message).strip() or RSS_CONNECTED_STATUS
            return True, f"{live_message}; {addins_message}"
        except RssNotConnectedError as error:
            return False, str(error)
        except Exception as error:  # pragma: no cover - defensive fail-close
            return False, f"Excel/RSS transport health failed: {error}"

    def _write_payload(
        self,
        session: ExcelTransportSession,
        cell_map: Mapping[str, str],
        payload: Mapping[str, Any],
    ) -> None:
        sheet = self._sheet(session)
        for key, cell in cell_map.items():
            try:
                sheet.Range(cell).Value2 = _sheet_value(payload.get(key, ""))
            except Exception as error:
                raise ExcelComError(f"Failed to write {key} to {cell}") from error

    def stage_submit_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self._write_payload(session, SUBMIT_CELL_MAP, payload)

    def invoke_submit_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        try:
            session.application.Run(f"'{session.workbook.Name}'!{macro_name}", *args)
        except Exception as error:
            raise ExcelComError(f"Submit macro failed: {error}") from error

    def read_order_updates(
        self,
        session: ExcelTransportSession,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        sheet = self._sheet(session)
        try:
            status_value = sheet.Range(RESULT_CELL_MAP["status"]).Value2
        except Exception as error:
            raise ExcelComError(f"Failed to read status for {broker_order_id}") from error
        if status_value in (None, ""):
            return ()
        try:
            status = _parse_order_status(status_value)
            fill_quantity = int(sheet.Range(RESULT_CELL_MAP["filled_quantity"]).Value2 or 0)
            fill_price = float(sheet.Range(RESULT_CELL_MAP["filled_price"]).Value2 or 0.0)
            rss_order_status = str(status_value or "").strip()
            message = str(sheet.Range(RESULT_CELL_MAP["message"]).Value2 or "")
            if not message.strip():
                message = str(status_value or "").strip()
            updated_at_raw = sheet.Range(RESULT_CELL_MAP["updated_at"]).Value2
            updated_at = (
                datetime.fromisoformat(str(updated_at_raw))
                if updated_at_raw
                else _now_jst()
            )
        except Exception as error:
            raise ExcelComError(f"Failed to parse order update for {broker_order_id}") from error
        return (
            RakutenRssOrderUpdate(
                status=status,
                fill_quantity=fill_quantity,
                fill_price=fill_price,
                message=message,
                updated_at=updated_at,
                rss_order_status=rss_order_status,
            ),
        )

    def read_rss_order_ledger(
        self,
        session: ExcelTransportSession,
    ) -> tuple[RakutenRssOrderIdEntry, ...]:
        try:
            result = session.application.Run(f"'{session.workbook.Name}'!{ORDER_ID_LIST_MACRO_NAME}")
        except Exception as error:
            raise ExcelComError(f"Failed to read RssOrderIDList: {error}") from error
        return _normalize_rss_order_id_entries(result)

    def read_rss_order_status(self, session: ExcelTransportSession, rss_order_id: int) -> int:
        try:
            result = session.application.Run(
                f"'{session.workbook.Name}'!{ORDER_STATUS_MACRO_NAME}",
                int(rss_order_id),
            )
        except Exception as error:
            raise ExcelComError(f"Failed to read RssOrderStatus for {rss_order_id}: {error}") from error
        try:
            return int(str(result).strip())
        except Exception as error:
            raise ExcelComError(f"Invalid RssOrderStatus for {rss_order_id}: {result!r}") from error

    def stage_cancel_payload(
        self,
        session: ExcelTransportSession,
        payload: Mapping[str, Any],
    ) -> None:
        self._write_payload(session, CANCEL_CELL_MAP, payload)

    def invoke_cancel_macro(self, session: ExcelTransportSession, macro_name: str, *args: Any) -> None:
        try:
            session.application.Run(f"'{session.workbook.Name}'!{macro_name}", *args)
        except Exception as error:
            raise ExcelComError(f"Cancel macro failed: {error}") from error

    def close(self, session: ExcelTransportSession) -> None:
        try:
            session.workbook.Close(SaveChanges=False)
        except Exception:
            pass


@dataclass(slots=True)
class _TrackedOrder:
    order: OrderRequest
    broker_order_id: str
    rss_order_id: int
    submitted_at: datetime
    submit_payload: dict[str, Any]
    stage_state: str = "STAGED"
    submit_request_id: str = ""
    cancel_request_id: str = ""
    cancel_payload: dict[str, Any] | None = None
    rss_order_number: str = ""
    rss_order_status_code: int = -1
    broker_observation_state: str = ""
    cancel_observation_state: str = ""
    last_authoritative_rss_status: int = -1
    last_message: str = ""
    filled_quantity: int = 0
    filled_price: float = 0.0
    updated_at: datetime = field(default_factory=_now_jst)


class ProductionRakutenRssTransport:
    def __init__(
        self,
        *,
        live_trading_enabled: bool = False,
        production_transport_enabled: bool = False,
        armed: bool = False,
        workbook_path: Path | str | None = None,
        workbook_name: str = DEFAULT_WORKBOOK_NAME,
        timeout_seconds: int = 300,
        backend: ExcelComBackend | None = None,
        clock: Callable[[], datetime] = _now_jst,
        bridge_root: Path | str | None = None,
    ) -> None:
        self._live_trading_enabled = bool(live_trading_enabled)
        self._production_transport_enabled = bool(production_transport_enabled)
        self._armed = bool(armed)
        # Pin the production transport to the single canonical workbook.
        # The workbook_path argument is retained for compatibility but ignored.
        self._workbook_path = DEFAULT_WORKBOOK_PATH
        self._workbook_name = workbook_name
        self._timeout_seconds = int(timeout_seconds)
        self._backend = backend or Win32ComExcelBackend()
        self._clock = clock
        self._bridge_root = (
            Path(bridge_root).resolve()
            if bridge_root is not None
            else (PHOENIX_ROOT / "runtime" / "v7_rss_production" / "order_bridge").resolve()
        )
        self._session: ExcelTransportSession | None = None
        self._orders: dict[str, _TrackedOrder] = {}
        self._lock = RLock()
        self._com_call_count = 0
        self._submit_macro_call_count = 0
        self._cancel_macro_call_count = 0
        self._last_submit_payload: dict[str, Any] | None = None
        self._last_cancel_payload: dict[str, Any] | None = None

    @property
    def submitted_count(self) -> int:
        return len(self._orders)

    @property
    def com_call_count(self) -> int:
        return self._com_call_count

    @property
    def order_function_call_count(self) -> int:
        return self._submit_macro_call_count

    @property
    def cancel_function_call_count(self) -> int:
        return self._cancel_macro_call_count

    @property
    def last_submit_payload(self) -> dict[str, Any] | None:
        return None if self._last_submit_payload is None else dict(self._last_submit_payload)

    @property
    def last_cancel_payload(self) -> dict[str, Any] | None:
        return None if self._last_cancel_payload is None else dict(self._last_cancel_payload)

    def _gate_message(self) -> str:
        if not self._live_trading_enabled:
            return "Rakuten RSS production transport is disabled until live_trading_enabled=true."
        if not self._production_transport_enabled:
            return (
                "Rakuten RSS production transport is disabled until "
                "production_transport_enabled=true."
            )
        return ""

    def _ensure_session(self) -> ExcelTransportSession:
        if self._session is not None and self._session_matches_workbook(self._session):
            return self._session
        self._session = None
        self._com_call_count += 1
        session = self._backend.connect(self._workbook_path, self._workbook_name)
        self._session = session
        return session

    def _session_matches_workbook(self, session: ExcelTransportSession) -> bool:
        try:
            workbook_full_name = Path(str(session.workbook.FullName)).resolve()
        except Exception:
            if not hasattr(session.workbook, "FullName") and not hasattr(session.application, "Workbooks"):
                return True
            return False
        if workbook_full_name != self._workbook_path:
            return False

        try:
            session_application = session.application
            workbook_application = session.workbook.Application
        except Exception:
            return False

        try:
            session_application_hwnd = int(getattr(session_application, "Hwnd"))
            workbook_application_hwnd = int(getattr(workbook_application, "Hwnd"))
            if session_application_hwnd != workbook_application_hwnd:
                return False
        except Exception:
            if session_application is not workbook_application:
                return False

        try:
            for candidate in session.application.Workbooks:
                try:
                    if Path(str(candidate.FullName)).resolve() == self._workbook_path:
                        return True
                except Exception:
                    continue
        except Exception:
            return False
        return False

    def _refresh_session(self) -> ExcelTransportSession:
        self._session = None
        return self._ensure_session()

    @staticmethod
    def _should_retry_live_recovery(message: str) -> bool:
        text = str(message).lower()
        return "probe" in text or "not connected" in text

    def _health_after_recovery(self) -> RakutenRssTransportHealth | None:
        try:
            session = self._refresh_session()
            return self._health_from_backend(session)
        except ExcelComError:
            return None

    def _read_runtime_state_from_file(self) -> WorkbookRuntimeState:
        try:
            values = _read_workbook_health_cells(
                self._workbook_path,
                TRANSPORT_SHEET_NAME,
                WORKBOOK_STATE_CELL_MAP,
            )
        except ExcelComError as error:
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=str(error),
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=f"Excel/RSS workbook state failed: {error}",
            )
        return _runtime_state_from_values(values, transport_source=TRANSPORT_SOURCE_FILE_FALLBACK)

    def read_runtime_state(self) -> WorkbookRuntimeState:
        gate_message = self._gate_message()
        if gate_message:
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=gate_message,
            )
        try:
            session = self._ensure_session()
        except ExcelComError:
            file_state = self._read_runtime_state_from_file()
            if file_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return file_state
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=file_state.message,
            )

        try:
            return self._backend.read_runtime_state(session)
        except ExcelComError:
            file_state = self._read_runtime_state_from_file()
            if file_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return file_state
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=file_state.message,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            file_state = self._read_runtime_state_from_file()
            if file_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return file_state
            return WorkbookRuntimeState(
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                excel_alive=False,
                rss_connected=False,
                addin_ready=False,
                order_transport_ready=False,
                heartbeat_at=None,
                heartbeat_age_seconds=None,
                ready=False,
                message=f"Excel/RSS transport state failed: {error}",
            )

    def _health_from_backend(self, session: ExcelTransportSession) -> RakutenRssTransportHealth:
        self._com_call_count += 1
        connected, message = self._backend.health_check(session)
        return RakutenRssTransportHealth(
            connected=connected,
            message=message,
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

    def publish_file_ready_heartbeat(self) -> RakutenRssTransportHealth:
        try:
            session = self._ensure_session()
            connected, message = self._backend.health_check(session, publish=True)
            transport_source = (
                TRANSPORT_SOURCE_COM_LIVE if connected else TRANSPORT_SOURCE_DISCONNECTED
            )
            return RakutenRssTransportHealth(
                connected=connected,
                message=message,
                transport_source=transport_source,
            )
        except ExcelComError as error:
            self._session = None
            return RakutenRssTransportHealth(
                connected=False,
                message=f"Excel/RSS transport health failed: {error}",
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            self._session = None
            return RakutenRssTransportHealth(
                connected=False,
                message=f"Excel/RSS transport health failed: {error}",
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )

    def _health_from_workbook_file(self) -> RakutenRssTransportHealth:
        state = self._read_runtime_state_from_file()
        return RakutenRssTransportHealth(
            connected=state.ready,
            message=state.message,
            transport_source=state.transport_source,
        )

    def health_check(self) -> RakutenRssTransportHealth:
        gate_message = self._gate_message()
        if gate_message:
            return RakutenRssTransportHealth(
                connected=False,
                message=gate_message,
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )

        try:
            session = self._ensure_session()
            connected, message = self._backend.health_check(session)
            runtime_state = self._backend.read_runtime_state(session)
            return RakutenRssTransportHealth(
                connected=bool(connected and runtime_state.ready),
                message=message,
                transport_source=runtime_state.transport_source,
            )
        except ExcelComError as error:
            runtime_state = self._read_runtime_state_from_file()
            if runtime_state.transport_source == TRANSPORT_SOURCE_DISCONNECTED:
                return RakutenRssTransportHealth(
                    connected=False,
                    message=str(error),
                    transport_source=TRANSPORT_SOURCE_DISCONNECTED,
                )
            return RakutenRssTransportHealth(
                connected=runtime_state.ready,
                message=runtime_state.message,
                transport_source=runtime_state.transport_source,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            runtime_state = self._read_runtime_state_from_file()
            if runtime_state.transport_source != TRANSPORT_SOURCE_DISCONNECTED:
                return RakutenRssTransportHealth(
                    connected=runtime_state.ready,
                    message=runtime_state.message,
                    transport_source=runtime_state.transport_source,
                )
            return RakutenRssTransportHealth(
                connected=False,
                message=f"Excel/RSS transport health failed: {error}",
                transport_source=TRANSPORT_SOURCE_DISCONNECTED,
            )

    def _build_submit_payload(
        self,
        order: OrderRequest,
        broker_order_id: str,
        submitted_at: datetime,
    ) -> dict[str, Any]:
        metadata = dict(order.metadata or {})
        protective_order = order.side is OrderSide.SELL and any(
            key in metadata
            for key in (
                "target_price",
                "take_profit_price",
                "stop_price",
                "stop_loss_price",
                "expiration",
                "expires_at",
                "order_category",
            )
        )
        target_price = round(
            float(
                _metadata_value(
                    order,
                    "target_price",
                    "take_profit_price",
                    default=order.limit_price,
                )
            ),
            2,
        )
        stop_price = round(
            float(
                _metadata_value(
                    order,
                    "stop_price",
                    "stop_loss_price",
                    default=0.0,
                )
            ),
            2,
        )
        order_category = str(
            _metadata_value(
                order,
                "order_category",
                default="逆指値付通常注文" if protective_order else "通常注文",
            )
        ).strip()
        execution_condition = str(
            _metadata_value(
                order,
                "execution_condition",
                default="期間指定" if protective_order else "",
            )
        ).strip()
        expiration = _expiration_yyyymmdd(
            _metadata_value(
                order,
                "expiration",
                "expires_at",
                default="",
            )
        )
        trigger_condition = str(
            _metadata_value(
                order,
                "trigger_condition",
                default="以下" if protective_order else "",
            )
        ).strip()
        post_trigger_order_type = str(
            _metadata_value(
                order,
                "post_trigger_order_type",
                default="売り成行" if protective_order else "",
            )
        ).strip()
        payload = {
            "schema_version": 1,
            "request_kind": "SUBMIT",
            "broker_order_id": broker_order_id,
            "client_order_id": order.client_order_id,
            "strategy_name": order.strategy_name,
            "ticker": order.ticker.strip().upper(),
            "side": order.side.value,
            "quantity": order.quantity,
            "order_type": order.order_type.value,
            "limit_price": round(float(order.limit_price), 2),
            "target_price": target_price,
            "stop_price": stop_price,
            "stop_trigger_price": stop_price,
            "order_category": order_category,
            "execution_condition": execution_condition,
            "expiration": expiration,
            "trigger_condition": trigger_condition,
            "post_trigger_order_type": post_trigger_order_type,
            "protective_order": protective_order,
            "live_trading_enabled": self._live_trading_enabled,
            "production_transport_enabled": self._production_transport_enabled,
            "armed": self._armed,
            "submitted_at": submitted_at.isoformat(timespec="seconds"),
            "timeout_seconds": self._timeout_seconds,
            "macro_name": ORDER_MACRO_NAME,
            "message": "STAGED" if not self._armed else "LIVE_FIRE_ARMED",
        }
        payload["payload_sha256"] = _stable_hash(payload)
        return payload

    def _build_cancel_payload(
        self,
        order: _TrackedOrder,
        submitted_at: datetime,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": 1,
            "request_kind": "CANCEL",
            "broker_order_id": order.broker_order_id,
            "client_order_id": order.order.client_order_id,
            "action": "CANCEL",
            "submitted_at": submitted_at.isoformat(timespec="seconds"),
            "macro_name": CANCEL_MACRO_NAME,
            "message": "STAGED",
        }
        payload["payload_sha256"] = _stable_hash(payload)
        return payload

    def _file_bridge_request_id(self, request_kind: str, broker_order_id: str) -> str:
        return f"{request_kind.upper()}__{broker_order_id}"

    def _stage_file_bridge_request(
        self,
        *,
        request_kind: str,
        request_id: str,
        payload: Mapping[str, Any],
        submitted_at: datetime,
    ) -> FileBridgeStageResult:
        bridge_payload = dict(payload)
        bridge_payload["request_id"] = request_id
        bridge_payload["request_kind"] = request_kind.upper()
        bridge_payload["bridge_status"] = "PENDING"
        return stage_request(
            self._bridge_root,
            request_id=request_id,
            request_kind=request_kind,
            payload=bridge_payload,
            now=submitted_at,
        )

    def _read_file_bridge_receipt(
        self,
        *,
        request_id: str,
        request_kind: str,
    ) -> FileBridgeReceipt | None:
        return read_receipt(
            self._bridge_root,
            request_id=request_id,
            request_kind=request_kind,
            now=self._clock(),
        )

    def _file_bridge_update_from_receipt(self, receipt: FileBridgeReceipt) -> RakutenRssOrderUpdate:
        try:
            status = _parse_order_status(receipt.result)
        except Exception as error:
            raise ExcelComError(f"Invalid bridge receipt result: {error}") from error
        try:
            authoritative_rss_status = int(str(receipt.rss_order_status).strip())
        except Exception:
            authoritative_rss_status = -1
        return RakutenRssOrderUpdate(
            status=status,
            fill_quantity=receipt.fill_quantity,
            fill_price=receipt.fill_price,
            message=receipt.message or receipt.result,
            updated_at=receipt.received_at,
            rss_order_status=receipt.rss_order_status,
            rss_order_number=receipt.rss_order_number,
            authoritative_rss_status=authoritative_rss_status,
        )

    @staticmethod
    def _tracked_order_status(order: _TrackedOrder) -> OrderStatus:
        try:
            return OrderStatus(order.stage_state)
        except Exception:
            return OrderStatus.PENDING

    def _tracked_order_ack(self, order: _TrackedOrder, *, message: str | None = None) -> RakutenRssSubmitAck:
        status = self._tracked_order_status(order)
        return RakutenRssSubmitAck(
            status=status,
            message=message or order.last_message or status.value,
            submitted_at=order.submitted_at,
            rss_order_id=order.rss_order_id,
            rss_order_number=order.rss_order_number,
            authoritative_rss_status=order.last_authoritative_rss_status,
        )

    def _tracked_cancel_ack(self, order: _TrackedOrder, *, message: str | None = None) -> RakutenRssCancelAck:
        status = self._tracked_order_status(order)
        return RakutenRssCancelAck(
            status=status,
            message=message or order.last_message or status.value,
            canceled_at=order.submitted_at,
            rss_order_id=order.rss_order_id,
            rss_order_number=order.rss_order_number,
            authoritative_rss_status=order.last_authoritative_rss_status,
        )

    def _stable_rss_order_id(self, order: OrderRequest, broker_order_id: str) -> int:
        return _stable_rss_order_id(order.client_order_id, broker_order_id)

    @staticmethod
    def _rss_order_status_value(value: Any) -> int:
        try:
            status = int(str(value).strip())
        except Exception as error:
            raise ExcelComError(f"Invalid RssOrderStatus value: {value!r}") from error
        if status not in {-1, 1, 2, 3}:
            raise ExcelComError(f"Unsupported RssOrderStatus value: {status}")
        return status

    def _live_contract_metadata(self, order: OrderRequest) -> dict[str, Any]:
        metadata = dict(order.metadata or {})
        required_names = ("account_category", "sor_category", "execution_condition")
        missing = [name for name in required_names if str(metadata.get(name, "")).strip() == ""]
        if missing:
            raise ExcelComError(
                "LIVE contract fields missing: " + ", ".join(missing)
            )
        return metadata

    @staticmethod
    def _rss_code_from_alias(value: Any, mapping: Mapping[str, int], *, field_name: str) -> int:
        text = str(value).strip()
        if not text:
            raise ExcelComError(f"{field_name} is missing for LIVE contract.")
        if text.isdigit():
            code = int(text)
            if code in mapping.values():
                return code
        normalized = text.replace("（", "(").replace("）", ")")
        if normalized in mapping:
            return mapping[normalized]
        if text in mapping:
            return mapping[text]
        raise ExcelComError(f"Unsupported {field_name}: {value!r}")

    def _rss_account_category_code(self, value: Any) -> int:
        return self._rss_code_from_alias(
            value,
            {
                "0": 0,
                "特定": 0,
                "1": 1,
                "一般": 1,
                "2": 2,
                "NISA": 2,
                "NISA(NISA成長投資枠)": 2,
                "3": 3,
                "旧NISA": 3,
            },
            field_name="account_category",
        )

    def _rss_sor_code(self, value: Any) -> int:
        return self._rss_code_from_alias(
            value,
            {
                "0": 0,
                "通常": 0,
                "通常注文": 0,
                "1": 1,
                "SOR": 1,
                "SOR注文": 1,
            },
            field_name="sor_category",
        )

    def _rss_execution_condition_code(self, value: Any) -> int:
        return self._rss_code_from_alias(
            value,
            {
                "1": 1,
                "本日中": 1,
                "2": 2,
                "今週中": 2,
                "3": 3,
                "寄付": 3,
                "4": 4,
                "引け": 4,
                "5": 5,
                "期間指定": 5,
                "6": 6,
                "大引不成": 6,
                "7": 7,
                "不成": 7,
            },
            field_name="execution_condition",
        )

    def _rss_trigger_condition_code(self, value: Any) -> int | str:
        text = str(value).strip()
        if not text:
            return ""
        if text.isdigit() and int(text) in {1, 2}:
            return int(text)
        mapping = {
            "1": 1,
            "以上": 1,
            "2": 2,
            "以下": 2,
        }
        return self._rss_code_from_alias(value, mapping, field_name="trigger_condition")

    def _rss_price_kind_code(self, value: Any, *, field_name: str) -> int:
        text = str(value).strip()
        if not text:
            raise ExcelComError(f"{field_name} is missing for LIVE contract.")
        if text.isdigit() and int(text) in {0, 1}:
            return int(text)
        mapping = {
            "0": 0,
            "成行": 0,
            "1": 1,
            "指値": 1,
        }
        return self._rss_code_from_alias(value, mapping, field_name=field_name)

    def _rss_optional_price(self, value: Any, *, field_name: str) -> Any:
        text = str(value).strip()
        if not text:
            return ""
        try:
            return round(float(text), 2)
        except Exception as error:
            raise ExcelComError(f"Unsupported {field_name}: {value!r}") from error

    def _rss_stop_price_kind_code(self, value: Any) -> int | str:
        text = str(value).strip()
        if not text:
            return ""
        if text.isdigit() and int(text) in {0, 1}:
            return int(text)
        mapping = {
            "0": 0,
            "成行": 0,
            "売り成行": 0,
            "買い成行": 0,
            "1": 1,
            "指値": 1,
            "売り指値": 1,
            "買い指値": 1,
        }
        return self._rss_code_from_alias(value, mapping, field_name="stop_price_kind")

    def _rss_set_order_kind_code(self, value: Any) -> int | str:
        text = str(value).strip()
        if not text:
            return ""
        if text.isdigit() and int(text) in {0, 1}:
            return int(text)
        mapping = {
            "0": 0,
            "成行": 0,
            "売り成行": 0,
            "買い成行": 0,
            "1": 1,
            "指値": 1,
            "売り指値": 1,
            "買い指値": 1,
        }
        return self._rss_code_from_alias(value, mapping, field_name="set_order_kind")

    def _rss_order_kind_code(self, order: OrderRequest, metadata: Mapping[str, Any]) -> int:
        order_category = str(
            _metadata_value(order, "order_category", default=metadata.get("order_category", ""))
        ).strip()
        if order_category in {"0", "通常", "通常注文"}:
            return 0
        if order_category in {"1", "逆指値付通常注文"}:
            return 1
        if order_category in {"2", "逆指値注文"}:
            return 2
        if order.side is OrderSide.SELL and any(
            key in metadata for key in ("target_price", "take_profit_price", "stop_price", "stop_loss_price")
        ):
            return 1
        return 0

    @staticmethod
    def _rss_side_code(order: OrderRequest) -> int:
        if order.side is OrderSide.BUY:
            return 3
        if order.side is OrderSide.SELL:
            return 1
        raise ExcelComError(f"Unsupported order side: {order.side}")

    @staticmethod
    def _rss_price_kind(order: OrderRequest) -> int:
        order_type_text = str(getattr(order.order_type, "value", order.order_type)).strip().upper()
        if order_type_text in {"MARKET", "成行"}:
            return 0
        if order_type_text in {"LIMIT", "指値"}:
            return 1
        raise ExcelComError(f"Unsupported order type: {order.order_type}")

    def _rss_optional_text(self, value: Any) -> str:
        text = str(value).strip()
        return text

    def _build_rss_stock_order_arguments(self, order: OrderRequest, rss_order_id: int) -> tuple[Any, ...]:
        metadata = self._live_contract_metadata(order)
        order_category = self._rss_order_kind_code(order, metadata)
        price_kind = self._rss_price_kind(order)
        account_category = self._rss_account_category_code(metadata.get("account_category", ""))
        sor_category = self._rss_sor_code(metadata.get("sor_category", ""))
        execution_condition = self._rss_execution_condition_code(metadata.get("execution_condition", ""))
        expiration = _expiration_yyyymmdd(metadata.get("expiration", metadata.get("expires_at", "")))
        quantity = int(order.quantity)
        order_price: Any = round(float(order.limit_price), 2) if price_kind == 1 else ""
        stop_condition_price = self._rss_optional_price(
            _metadata_value(order, "stop_condition_price", "stop_price", default=""),
            field_name="stop_condition_price",
        )
        stop_condition_kind = self._rss_trigger_condition_code(
            _metadata_value(order, "stop_condition_kind", "trigger_condition", default="")
        )
        stop_price_kind = self._rss_stop_price_kind_code(
            _metadata_value(order, "stop_price_kind", "post_trigger_order_type", default="")
        )
        stop_price = self._rss_optional_price(
            _metadata_value(order, "stop_price", "stop_loss_price", default=""),
            field_name="stop_price",
        )
        set_order_kind = self._rss_set_order_kind_code(_metadata_value(order, "set_order_kind", default=""))
        set_order_price = self._rss_optional_price(
            _metadata_value(order, "set_order_price", default=""),
            field_name="set_order_price",
        )
        set_order_execution_condition = self._rss_execution_condition_code(
            _metadata_value(order, "set_order_execution_condition", default="")
        ) if str(_metadata_value(order, "set_order_execution_condition", default="")).strip() else ""
        set_order_expiration = _expiration_yyyymmdd(_metadata_value(order, "set_order_expiration", default=""))
        ticker = order.ticker.strip().upper()
        return (
            int(rss_order_id),
            ticker,
            self._rss_side_code(order),
            order_category,
            sor_category,
            quantity,
            price_kind,
            order_price,
            execution_condition,
            expiration,
            account_category,
            stop_condition_price,
            stop_condition_kind,
            stop_price_kind,
            stop_price,
            set_order_kind,
            set_order_price,
            set_order_execution_condition,
            set_order_expiration,
        )

    def _build_rss_cancel_order_arguments(self, rss_order_id: int, order_number: str) -> tuple[Any, ...]:
        if not str(order_number).strip():
            raise ExcelComError("RSS order number is missing for cancel.")
        return (int(rss_order_id), str(order_number).strip())

    def _find_rss_order_ledger_entry(
        self,
        session: ExcelTransportSession,
        rss_order_id: int,
        *,
        function_name: str,
    ) -> RakutenRssOrderIdEntry | None:
        for entry in self._backend.read_rss_order_ledger(session):
            if entry.rss_order_id != int(rss_order_id):
                continue
            if str(entry.function_name).strip() and str(entry.function_name).strip() != function_name:
                continue
            return entry
        return None

    def _observe_rss_order_status(
        self,
        session: ExcelTransportSession,
        rss_order_id: int,
    ) -> int:
        return self._backend.read_rss_order_status(session, int(rss_order_id))

    def submit_order(self, order: OrderRequest, broker_order_id: str) -> RakutenRssSubmitAck:
        order.validate()
        gate_message = self._gate_message()
        if gate_message:
            return RakutenRssSubmitAck(
                status=OrderStatus.REJECTED,
                message=gate_message,
                rss_order_id=self._stable_rss_order_id(order, broker_order_id),
            )

        submitted_at = self._clock()
        payload = self._build_submit_payload(order, broker_order_id, submitted_at)
        with self._lock:
            self._last_submit_payload = dict(payload)
            existing = self._orders.get(broker_order_id)
            if existing is not None:
                return self._tracked_order_ack(existing)

        rss_order_id = self._stable_rss_order_id(order, broker_order_id)
        record: _TrackedOrder | None = None

        try:
            with self._lock:
                record = _TrackedOrder(
                    order=order,
                    broker_order_id=broker_order_id,
                    rss_order_id=rss_order_id,
                    submitted_at=submitted_at,
                    submit_payload=dict(payload),
                    submit_request_id=self._file_bridge_request_id("SUBMIT", broker_order_id),
                )
                self._orders[broker_order_id] = record

            health = self.health_check()
            if not health.connected:
                with self._lock:
                    if record is not None:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = health.message
                        record.updated_at = self._clock()
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    submitted_at=submitted_at,
                    rss_order_id=rss_order_id,
                )
            if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                request_id = self._file_bridge_request_id("SUBMIT", broker_order_id)
                try:
                    bridge_result = self._stage_file_bridge_request(
                        request_kind="SUBMIT",
                        request_id=request_id,
                        payload=payload,
                        submitted_at=submitted_at,
                    )
                except Exception as error:
                    with self._lock:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = f"FILE_READY bridge staging failed: {error}"
                        record.updated_at = self._clock()
                    return RakutenRssSubmitAck(
                        status=OrderStatus.REJECTED,
                        message=f"FILE_READY bridge staging failed: {error}",
                        submitted_at=submitted_at,
                        rss_order_id=rss_order_id,
                    )
                with self._lock:
                    record.submit_request_id = request_id
                    record.stage_state = OrderStatus.PENDING.value
                    record.last_message = (
                        "FILE_READY request staged."
                        if not bridge_result.duplicate
                        else "FILE_READY request already staged."
                    )
                    record.updated_at = self._clock()
                    return RakutenRssSubmitAck(
                        status=OrderStatus.PENDING,
                        message=record.last_message,
                        submitted_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
            if health.transport_source != TRANSPORT_SOURCE_COM_LIVE:
                with self._lock:
                    if record is not None:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = health.message
                        record.updated_at = self._clock()
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    submitted_at=submitted_at,
                    rss_order_id=rss_order_id,
                )
            session = self._ensure_session()
            self._com_call_count += 1
            if not self._armed:
                with self._lock:
                    if record is not None:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = "production_live_fire_armed=false; submit staging disabled."
                        record.updated_at = self._clock()
                return RakutenRssSubmitAck(
                    status=OrderStatus.REJECTED,
                    message="armed=false; RssStockOrder_V not called.",
                    submitted_at=submitted_at,
                    rss_order_id=rss_order_id,
                )
            self._backend.stage_submit_payload(session, payload)
            submit_args = self._build_rss_stock_order_arguments(order, rss_order_id)
            self._com_call_count += 1
            self._submit_macro_call_count += 1
            self._backend.invoke_submit_macro(session, ORDER_MACRO_NAME, *submit_args)
            ledger_entry = self._find_rss_order_ledger_entry(
                session,
                rss_order_id,
                function_name=ORDER_MACRO_NAME,
            )
            try:
                rss_order_status = self._observe_rss_order_status(session, rss_order_id)
            except ExcelComError as error:
                rss_order_status = -1
                status_error = str(error)
            else:
                status_error = ""
            with self._lock:
                    if record is not None:
                        record.rss_order_status_code = rss_order_status
                        if ledger_entry is not None:
                            record.rss_order_number = ledger_entry.order_number
                            if ledger_entry.result:
                                record.last_message = ledger_entry.result
                        record.last_authoritative_rss_status = rss_order_status
                        if not record.last_message:
                            record.last_message = status_error or "RssStockOrder_V invoked."
                        if ledger_entry is None or not ledger_entry.order_number or not ledger_entry.result or rss_order_status == -1:
                            record.stage_state = OrderStatus.PENDING.value
                            record.broker_observation_state = OrderStatus.PENDING.value
                            record.updated_at = self._clock()
                            return RakutenRssSubmitAck(
                                status=OrderStatus.PENDING,
                                message=record.last_message or "RssOrderIDList not yet observed.",
                                submitted_at=submitted_at,
                                rss_order_id=record.rss_order_id,
                                rss_order_number=record.rss_order_number,
                                authoritative_rss_status=record.last_authoritative_rss_status,
                            )
                        if rss_order_status == 1:
                            record.stage_state = OrderStatus.REJECTED.value
                            record.broker_observation_state = OrderStatus.REJECTED.value
                            record.updated_at = self._clock()
                            return RakutenRssSubmitAck(
                                status=OrderStatus.REJECTED,
                                message=record.last_message or "RssOrderStatus=1",
                                submitted_at=submitted_at,
                                rss_order_id=record.rss_order_id,
                                rss_order_number=record.rss_order_number,
                                authoritative_rss_status=record.last_authoritative_rss_status,
                            )
                        if rss_order_status == 3:
                            record.stage_state = OrderStatus.FILLED.value
                            record.broker_observation_state = OrderStatus.FILLED.value
                            record.updated_at = self._clock()
                            return RakutenRssSubmitAck(
                                status=OrderStatus.FILLED,
                                message=record.last_message or "RssOrderStatus=3",
                                submitted_at=submitted_at,
                                rss_order_id=record.rss_order_id,
                                rss_order_number=record.rss_order_number,
                                authoritative_rss_status=record.last_authoritative_rss_status,
                            )
                        record.stage_state = OrderStatus.ACCEPTED.value
                        record.broker_observation_state = OrderStatus.ACCEPTED.value
                        record.updated_at = self._clock()
                        return RakutenRssSubmitAck(
                            status=OrderStatus.ACCEPTED,
                            message=record.last_message or "RssOrderStatus=2",
                            submitted_at=submitted_at,
                            rss_order_id=record.rss_order_id,
                            rss_order_number=record.rss_order_number,
                            authoritative_rss_status=record.last_authoritative_rss_status,
                        )
            return RakutenRssSubmitAck(
                status=OrderStatus.PENDING,
                message=status_error or "RssOrderIDList not yet observed.",
                submitted_at=submitted_at,
                rss_order_id=rss_order_id,
                rss_order_number=record.rss_order_number if record is not None else "",
                authoritative_rss_status=-1,
            )
        except ExcelComError as error:
            if record is not None:
                with self._lock:
                    record.stage_state = OrderStatus.REJECTED.value
                    record.last_message = str(error)
                    record.updated_at = self._clock()
            return RakutenRssSubmitAck(
                status=OrderStatus.REJECTED,
                message=str(error),
                submitted_at=submitted_at,
                rss_order_id=rss_order_id,
                rss_order_number=record.rss_order_number if record is not None else "",
                authoritative_rss_status=record.last_authoritative_rss_status if record is not None else -1,
            )
        except Exception as error:  # pragma: no cover - defensive fail-close
            if record is not None:
                with self._lock:
                    record.stage_state = OrderStatus.REJECTED.value
                    record.last_message = f"Excel/RSS submit failed: {error}"
                    record.updated_at = self._clock()
            return RakutenRssSubmitAck(
                status=OrderStatus.REJECTED,
                message=f"Excel/RSS submit failed: {error}",
                submitted_at=submitted_at,
                rss_order_id=rss_order_id,
                rss_order_number=record.rss_order_number if record is not None else "",
                authoritative_rss_status=record.last_authoritative_rss_status if record is not None else -1,
            )

    def poll_order(self, broker_order_id: str) -> tuple[RakutenRssOrderUpdate, ...]:
        gate_message = self._gate_message()
        if gate_message:
            return ()

        with self._lock:
            record = self._orders.get(broker_order_id)
        if record is None:
            return ()

        updates: tuple[RakutenRssOrderUpdate, ...] = ()
        try:
            health = self.health_check()
            if not health.connected:
                return ()
            if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                request_ids: list[tuple[str, str]] = []
                if record.cancel_request_id:
                    request_ids.append(("CANCEL", record.cancel_request_id))
                if record.submit_request_id:
                    request_ids.append(("SUBMIT", record.submit_request_id))
                for request_kind, request_id in request_ids:
                    receipt = self._read_file_bridge_receipt(
                        request_id=request_id,
                        request_kind=request_kind,
                    )
                    if receipt is None:
                        continue
                    update = self._file_bridge_update_from_receipt(receipt)
                    with self._lock:
                        record.updated_at = self._clock()
                        record.last_message = update.message
                        record.stage_state = update.status.value
                        record.broker_observation_state = update.status.value
                        record.last_authoritative_rss_status = update.authoritative_rss_status
                        if update.rss_order_number:
                            record.rss_order_number = update.rss_order_number
                        if update.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                            record.filled_quantity = update.fill_quantity
                            record.filled_price = update.fill_price
                    return (update,)
            elif health.transport_source == TRANSPORT_SOURCE_COM_LIVE:
                session = self._ensure_session()
                self._com_call_count += 1
                updates = self._backend.read_order_updates(session, broker_order_id)
                if not updates:
                    ledger_entry = self._find_rss_order_ledger_entry(
                        session,
                        record.rss_order_id,
                        function_name=ORDER_MACRO_NAME,
                    )
                    try:
                        rss_order_status = self._observe_rss_order_status(session, record.rss_order_id)
                    except ExcelComError:
                        rss_order_status = -1
                    if ledger_entry is not None and ledger_entry.order_number:
                        with self._lock:
                            record.rss_order_number = ledger_entry.order_number
                            record.last_message = ledger_entry.result or record.last_message
                            record.rss_order_status_code = rss_order_status
                            record.last_authoritative_rss_status = rss_order_status
                    normalized_order_result = self._rss_optional_text(
                        ledger_entry.result if ledger_entry is not None else "",
                    ).replace("(", "（").replace(")", "）")
                    cancel_completed_results = {
                        "取消済（出来有）",
                        "取消済（出来無）",
                        "取消済",
                    }
                    if rss_order_status in {1, 2, 3}:
                        if record.cancel_request_id:
                            if rss_order_status == 3:
                                synthetic_status = OrderStatus.FILLED
                            elif rss_order_status == 1 and normalized_order_result in cancel_completed_results:
                                synthetic_status = OrderStatus.CANCELED
                            else:
                                synthetic_status = OrderStatus.PENDING
                        else:
                            if rss_order_status == 1:
                                synthetic_status = OrderStatus.REJECTED
                            elif rss_order_status == 3:
                                synthetic_status = OrderStatus.FILLED
                            else:
                                synthetic_status = OrderStatus.ACCEPTED
                        synthetic_update = RakutenRssOrderUpdate(
                            status=synthetic_status,
                            fill_quantity=record.filled_quantity if synthetic_status is OrderStatus.FILLED else 0,
                            fill_price=record.filled_price if synthetic_status is OrderStatus.FILLED else 0.0,
                            message=record.last_message or f"RssOrderStatus={rss_order_status}",
                            updated_at=self._clock(),
                            rss_order_status=str(rss_order_status),
                            rss_order_id=record.rss_order_id,
                            rss_order_number=record.rss_order_number,
                            authoritative_rss_status=rss_order_status,
                        )
                        with self._lock:
                            record.updated_at = synthetic_update.updated_at
                            record.last_message = synthetic_update.message
                            record.stage_state = synthetic_status.value
                            record.broker_observation_state = synthetic_status.value
                        return (synthetic_update,)
            else:
                return ()
        except ExcelComError as error:
            with self._lock:
                record.stage_state = OrderStatus.REJECTED.value
                record.last_message = str(error)
                record.updated_at = self._clock()
            return ()

        if updates:
            with self._lock:
                record.updated_at = self._clock()
                final_update = updates[-1]
                record.broker_observation_state = final_update.status.value
                record.last_authoritative_rss_status = getattr(final_update, "authoritative_rss_status", -1)
                if getattr(final_update, "rss_order_number", ""):
                    record.rss_order_number = str(final_update.rss_order_number)
                if final_update.status in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
                    record.filled_quantity = final_update.fill_quantity
                    record.filled_price = final_update.fill_price
                if final_update.status is OrderStatus.TIMED_OUT:
                    record.broker_observation_state = "RECONCILE_PENDING"
                    record.last_message = final_update.message
                    record.updated_at = self._clock()
                elif final_update.status in {OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELED}:
                    record.stage_state = final_update.status.value
                else:
                    record.stage_state = final_update.status.value
                record.last_message = final_update.message
            return updates

        with self._lock:
            age = self._clock() - record.submitted_at
            if self._timeout_seconds == 0 or age >= timedelta(seconds=self._timeout_seconds):
                current_status = self._tracked_order_status(record)
                timeout_update = RakutenRssOrderUpdate(
                    status=current_status,
                    message="Order timed out waiting for Excel/RSS result; reconciliation continues.",
                    updated_at=self._clock(),
                    rss_order_status="TIMED_OUT",
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
                record.broker_observation_state = "RECONCILE_PENDING"
                record.last_message = timeout_update.message
                record.updated_at = timeout_update.updated_at
                return (timeout_update,)
        return ()

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        gate_message = self._gate_message()
        if gate_message:
            return RakutenRssCancelAck(
                status=OrderStatus.REJECTED,
                message=gate_message,
            )

        with self._lock:
            record = self._orders.get(broker_order_id)
        if record is None:
            return RakutenRssCancelAck(
                status=OrderStatus.REJECTED,
                message=f"Unknown broker_order_id: {broker_order_id}",
                rss_order_id=0,
                rss_order_number="",
                authoritative_rss_status=-1,
            )
        if record.cancel_request_id:
            return self._tracked_cancel_ack(record)

        submitted_at = self._clock()
        payload = self._build_cancel_payload(record, submitted_at)
        with self._lock:
            self._last_cancel_payload = dict(payload)
            record.cancel_payload = dict(payload)
            record.cancel_request_id = self._file_bridge_request_id("CANCEL", broker_order_id)

        try:
            health = self.health_check()
            if not health.connected:
                return RakutenRssCancelAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
            if health.transport_source == TRANSPORT_SOURCE_FILE_READY:
                request_id = self._file_bridge_request_id("CANCEL", broker_order_id)
                try:
                    bridge_result = self._stage_file_bridge_request(
                        request_kind="CANCEL",
                        request_id=request_id,
                        payload=payload,
                        submitted_at=submitted_at,
                    )
                except Exception as error:
                    with self._lock:
                        record.stage_state = OrderStatus.REJECTED.value
                        record.last_message = f"FILE_READY cancel staging failed: {error}"
                        record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.REJECTED,
                        message=f"FILE_READY cancel staging failed: {error}",
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
                with self._lock:
                    record.cancel_request_id = request_id
                    record.stage_state = OrderStatus.PENDING.value
                    record.cancel_observation_state = OrderStatus.PENDING.value
                    record.last_message = (
                        "FILE_READY cancel request staged."
                        if not bridge_result.duplicate
                        else "FILE_READY cancel request already staged."
                    )
                    record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.PENDING,
                        message=record.last_message,
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
            if health.transport_source != TRANSPORT_SOURCE_COM_LIVE:
                return RakutenRssCancelAck(
                    status=OrderStatus.REJECTED,
                    message=health.message,
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
            session = self._ensure_session()
            self._com_call_count += 1
            if not self._armed:
                with self._lock:
                    record.stage_state = OrderStatus.REJECTED.value
                    record.last_message = "production_live_fire_armed=false; cancel staging disabled."
                    record.updated_at = self._clock()
                return RakutenRssCancelAck(
                    status=OrderStatus.REJECTED,
                    message="production_live_fire_armed=false; cancel staging disabled.",
                    canceled_at=submitted_at,
                    rss_order_id=record.rss_order_id,
                    rss_order_number=record.rss_order_number,
                    authoritative_rss_status=record.last_authoritative_rss_status,
                )
            ledger_entry = self._find_rss_order_ledger_entry(
                session,
                record.rss_order_id,
                function_name=ORDER_MACRO_NAME,
            )
            order_number = record.rss_order_number or (ledger_entry.order_number if ledger_entry is not None else "")
            if not str(order_number).strip():
                with self._lock:
                    record.cancel_observation_state = "WAITING_FOR_ORDER_NUMBER"
                    record.last_message = "RSS order number is missing for cancel."
                    record.updated_at = self._clock()
                return self._tracked_cancel_ack(record, message="RSS order number is missing for cancel.")
            self._backend.stage_cancel_payload(session, payload)
            cancel_args = self._build_rss_cancel_order_arguments(record.rss_order_id, order_number)
            self._com_call_count += 1
            self._cancel_macro_call_count += 1
            self._backend.invoke_cancel_macro(session, CANCEL_MACRO_NAME, *cancel_args)
            try:
                rss_order_status = self._observe_rss_order_status(session, record.rss_order_id)
            except ExcelComError:
                rss_order_status = -1
            with self._lock:
                record.rss_order_number = order_number
                record.rss_order_status_code = rss_order_status
                record.last_authoritative_rss_status = rss_order_status
                if rss_order_status == 3:
                    record.stage_state = OrderStatus.FILLED.value
                    record.cancel_observation_state = OrderStatus.FILLED.value
                    record.last_message = "RssOrderStatus=3"
                    record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.FILLED,
                        message="RssOrderStatus=3",
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
                normalized_order_result = self._rss_optional_text(
                    ledger_entry.result if ledger_entry is not None else "",
                ).replace("(", "（").replace(")", "）")
                cancel_completed_results = {
                    "取消済（出来有）",
                    "取消済（出来無）",
                    "取消済",
                }
                if rss_order_status == 1 and normalized_order_result in cancel_completed_results:
                    record.stage_state = OrderStatus.CANCELED.value
                    record.cancel_observation_state = OrderStatus.CANCELED.value
                    record.last_message = normalized_order_result
                    record.updated_at = self._clock()
                    return RakutenRssCancelAck(
                        status=OrderStatus.CANCELED,
                        message=normalized_order_result,
                        canceled_at=submitted_at,
                        rss_order_id=record.rss_order_id,
                        rss_order_number=record.rss_order_number,
                        authoritative_rss_status=record.last_authoritative_rss_status,
                    )
                record.stage_state = OrderStatus.PENDING.value
                record.cancel_observation_state = OrderStatus.PENDING.value
                record.last_message = (
                    normalized_order_result
                    if normalized_order_result in {"出来ず（出来有）", "出来ず（出来無）"}
                    else "Cancel request observed but order status is still terminal-free."
                )
                record.updated_at = self._clock()
            return RakutenRssCancelAck(
                status=OrderStatus.PENDING,
                message=record.last_message,
                canceled_at=submitted_at,
                rss_order_id=record.rss_order_id,
                rss_order_number=record.rss_order_number,
                authoritative_rss_status=record.last_authoritative_rss_status,
            )
        except ExcelComError as error:
            with self._lock:
                record.stage_state = OrderStatus.REJECTED.value
                record.last_message = str(error)
                record.updated_at = self._clock()
            return RakutenRssCancelAck(
                status=OrderStatus.REJECTED,
                message=str(error),
                canceled_at=submitted_at,
                rss_order_id=record.rss_order_id,
                rss_order_number=record.rss_order_number,
                authoritative_rss_status=record.last_authoritative_rss_status,
            )


## FILE: phoenix_core/rakuten_rss_adapter.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from phoenix_core.models import OrderRequest, OrderStatus


JST = ZoneInfo("Asia/Tokyo")


def _now_jst() -> datetime:
    return datetime.now(JST)


@dataclass(frozen=True, slots=True)
class RakutenRssAdapterHealth:
    healthy: bool
    live_trading_enabled: bool
    message: str
    checked_at: datetime = field(default_factory=_now_jst)


@dataclass(frozen=True, slots=True)
class RakutenRssSubmitAck:
    status: OrderStatus
    message: str
    submitted_at: datetime = field(default_factory=_now_jst)
    rss_order_id: int = 0
    rss_order_number: str = ""
    authoritative_rss_status: int = -1


@dataclass(frozen=True, slots=True)
class RakutenRssOrderUpdate:
    status: OrderStatus
    fill_quantity: int = 0
    fill_price: float = 0.0
    message: str = ""
    updated_at: datetime = field(default_factory=_now_jst)
    rss_order_status: str = ""
    rss_order_id: int = 0
    rss_order_number: str = ""
    authoritative_rss_status: int = -1


@dataclass(frozen=True, slots=True)
class RakutenRssCancelAck:
    status: OrderStatus
    message: str
    canceled_at: datetime = field(default_factory=_now_jst)
    rss_order_id: int = 0
    rss_order_number: str = ""
    authoritative_rss_status: int = -1


class RakutenRssAdapter(Protocol):
    def health_check(self) -> RakutenRssAdapterHealth:
        raise NotImplementedError

    def submit_order(
        self,
        order: OrderRequest,
        broker_order_id: str,
    ) -> RakutenRssSubmitAck:
        raise NotImplementedError

    def poll_order(self, broker_order_id: str) -> tuple[RakutenRssOrderUpdate, ...]:
        raise NotImplementedError

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        raise NotImplementedError


@dataclass(slots=True)
class _MockScript:
    client_order_id: str
    submit_status: OrderStatus = OrderStatus.ACCEPTED
    submit_message: str = "MOCK_ACCEPTED"
    cancel_status: OrderStatus = OrderStatus.CANCELED
    cancel_message: str = "MOCK_CANCELED"
    updates: list[RakutenRssOrderUpdate] = field(default_factory=list)
    broker_order_id: str = ""
    rss_order_id: int = 0
    rss_order_number: str = ""
    submit_authoritative_rss_status: int = -1
    cancel_authoritative_rss_status: int = -1


class MockRakutenRssAdapter(RakutenRssAdapter):
    def __init__(
        self,
        *,
        healthy: bool = True,
        live_trading_enabled: bool = True,
        message: str = "MOCK_RSS_READY",
    ) -> None:
        self._healthy = healthy
        self._live_trading_enabled = live_trading_enabled
        self._message = message
        self._scripts_by_client_order_id: dict[str, _MockScript] = {}
        self._scripts_by_broker_order_id: dict[str, _MockScript] = {}
        self.submitted_requests: list[dict[str, Any]] = []

    @property
    def submitted_count(self) -> int:
        return len(self.submitted_requests)

    def set_health(
        self,
        *,
        healthy: bool | None = None,
        live_trading_enabled: bool | None = None,
        message: str | None = None,
    ) -> None:
        if healthy is not None:
            self._healthy = healthy
        if live_trading_enabled is not None:
            self._live_trading_enabled = live_trading_enabled
        if message is not None:
            self._message = message

    def reset(self) -> None:
        self._scripts_by_client_order_id.clear()
        self._scripts_by_broker_order_id.clear()
        self.submitted_requests.clear()

    def script_order(
        self,
        client_order_id: str,
        *,
        submit_status: OrderStatus = OrderStatus.ACCEPTED,
        submit_message: str = "MOCK_ACCEPTED",
        cancel_status: OrderStatus = OrderStatus.CANCELED,
        cancel_message: str = "MOCK_CANCELED",
        rss_order_id: int = 0,
        rss_order_number: str = "",
        submit_authoritative_rss_status: int = -1,
        cancel_authoritative_rss_status: int = -1,
        updates: list[RakutenRssOrderUpdate] | None = None,
    ) -> None:
        script = self._scripts_by_client_order_id.get(client_order_id)
        if script is None:
            script = _MockScript(client_order_id=client_order_id)
            self._scripts_by_client_order_id[client_order_id] = script
        script.submit_status = submit_status
        script.submit_message = submit_message
        script.cancel_status = cancel_status
        script.cancel_message = cancel_message
        script.rss_order_id = int(rss_order_id)
        script.rss_order_number = str(rss_order_number)
        script.submit_authoritative_rss_status = int(submit_authoritative_rss_status)
        script.cancel_authoritative_rss_status = int(cancel_authoritative_rss_status)
        if updates is not None:
            script.updates = list(updates)

    def queue_update(
        self,
        client_order_id: str,
        *,
        status: OrderStatus,
        fill_quantity: int = 0,
        fill_price: float = 0.0,
        message: str = "",
        rss_order_status: str = "",
        rss_order_id: int = 0,
        rss_order_number: str = "",
        authoritative_rss_status: int = -1,
    ) -> None:
        script = self._scripts_by_client_order_id.get(client_order_id)
        if script is None:
            script = _MockScript(client_order_id=client_order_id)
            self._scripts_by_client_order_id[client_order_id] = script
        script.updates.append(
            RakutenRssOrderUpdate(
                status=status,
                fill_quantity=fill_quantity,
                fill_price=fill_price,
                message=message,
                rss_order_status=rss_order_status,
                rss_order_id=int(rss_order_id),
                rss_order_number=str(rss_order_number),
                authoritative_rss_status=int(authoritative_rss_status),
            )
        )

    def health_check(self) -> RakutenRssAdapterHealth:
        return RakutenRssAdapterHealth(
            healthy=self._healthy,
            live_trading_enabled=self._live_trading_enabled,
            message=self._message,
        )

    def submit_order(
        self,
        order: OrderRequest,
        broker_order_id: str,
    ) -> RakutenRssSubmitAck:
        script = self._scripts_by_client_order_id.get(order.client_order_id)
        if script is None:
            script = _MockScript(client_order_id=order.client_order_id)
            self._scripts_by_client_order_id[order.client_order_id] = script
        script.broker_order_id = broker_order_id
        self._scripts_by_broker_order_id[broker_order_id] = script
        self.submitted_requests.append(
            {
                "client_order_id": order.client_order_id,
                "broker_order_id": broker_order_id,
                "ticker": order.ticker,
                "side": order.side.value,
                "quantity": order.quantity,
                "limit_price": order.limit_price,
                "rss_order_id": script.rss_order_id,
                "rss_order_number": script.rss_order_number,
                "authoritative_rss_status": script.submit_authoritative_rss_status,
                "submitted_at": _now_jst().isoformat(timespec="seconds"),
            }
        )
        return RakutenRssSubmitAck(
            status=script.submit_status,
            message=script.submit_message,
            rss_order_id=script.rss_order_id,
            rss_order_number=script.rss_order_number,
            authoritative_rss_status=script.submit_authoritative_rss_status,
        )

    def poll_order(
        self,
        broker_order_id: str,
    ) -> tuple[RakutenRssOrderUpdate, ...]:
        script = self._scripts_by_broker_order_id.get(broker_order_id)
        if script is None or not script.updates:
            return ()
        updates = tuple(script.updates)
        script.updates = []
        return updates

    def cancel_order(self, broker_order_id: str) -> RakutenRssCancelAck:
        script = self._scripts_by_broker_order_id.get(broker_order_id)
        if script is None:
            return RakutenRssCancelAck(
                status=OrderStatus.CANCELED,
                message="MOCK_CANCEL_NOOP",
            )
        script.updates = []
        return RakutenRssCancelAck(
            status=script.cancel_status,
            message=script.cancel_message,
            rss_order_id=script.rss_order_id,
            rss_order_number=script.rss_order_number,
            authoritative_rss_status=script.cancel_authoritative_rss_status,
        )


## FILE: phoenix_core/rakuten_rss_broker.py

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


def _stable_rss_order_id(client_order_id: str, broker_order_id: str) -> int:
    digest = hashlib.sha256(f"{client_order_id}|{broker_order_id}".encode("utf-8")).hexdigest()
    return max(1, int(digest[:8], 16) % 2147483647)


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
            rss_order_id = _stable_rss_order_id(order.client_order_id, broker_order_id)
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
                    rss_order_id=rss_order_id,
                    authoritative_rss_status=-1,
                )

            if ack.status is OrderStatus.REJECTED:
                return self._record_rejected(
                    order=order,
                    ticker=ticker,
                    message=ack.message or "Rakuten RSS adapter rejected the order",
                    broker_order_id=broker_order_id,
                    submitted_at=submitted_at,
                    rss_order_id=_optional_int(getattr(ack, "rss_order_id", rss_order_id), rss_order_id),
                    rss_order_number=_optional_text(getattr(ack, "rss_order_number", "")),
                    authoritative_rss_status=_optional_int(
                        getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
                        -1,
                    ),
                )
            if ack.status not in {OrderStatus.PENDING, OrderStatus.ACCEPTED}:
                raise ValueError("Rakuten RSS submit ack must be PENDING, ACCEPTED or REJECTED")

            rss_order_id = _optional_int(getattr(ack, "rss_order_id", rss_order_id), rss_order_id)
            rss_order_number = _optional_text(getattr(ack, "rss_order_number", ""))
            authoritative_rss_status = _optional_int(
                getattr(ack, "authoritative_rss_status", getattr(ack, "rss_order_status", -1)),
                -1,
            )

            record = self._new_record(
                order=order,
                ticker=ticker,
                broker_order_id=broker_order_id,
                status=ack.status,
                message=(
                    ack.message
                    or (
                        "Rakuten RSS order staged and awaiting VBA receipt"
                        if ack.status is OrderStatus.PENDING
                        else "Rakuten RSS order accepted into dry-run queue"
                    )
                ),
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
            candidate_rss_order_id = _optional_int(
                getattr(ack, "rss_order_id", record.get("rss_order_id", 0)),
                record.get("rss_order_id", 0),
            )
            if candidate_rss_order_id > 0:
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
        if update_rss_order_id > 0:
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


## FILE: tests/test_v7_step49.py

from __future__ import annotations

import ctypes
import hashlib
import csv
from pathlib import Path
from datetime import datetime
import tempfile
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from phoenix_core import (
    MockExcelComBackend,
    MockRakutenRssAdapter,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    RakutenRssBroker,
    ProductionRakutenRssAdapter,
    ProductionRakutenRssTransport,
    RakutenRssAdapterHealth,
    RakutenRssCancelAck,
    RakutenRssOrderUpdate,
    RakutenRssSubmitAck,
    RakutenRssTransportHealth,
)
import phoenix_core.order_bridge_gate as order_bridge_gate
from phoenix_core.production_rakuten_rss_transport import (
    DEFAULT_WORKBOOK_PATH,
    ExcelComError,
    WORKBOOK_STATE_ADDIN_READY_CELL,
    WORKBOOK_STATE_EXCEL_ALIVE_CELL,
    WORKBOOK_STATE_HEARTBEAT_CELL,
    WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL,
    WORKBOOK_STATE_RSS_CONNECTED_CELL,
    TRANSPORT_SOURCE_COM_LIVE,
    TRANSPORT_SOURCE_FILE_READY,
    TRANSPORT_SOURCE_FILE_FALLBACK,
    Win32ComExcelBackend,
)
import prepare_v7_rss_bootstrap as prepare_bootstrap
import phoenix_core.rss_order_bridge as rss_order_bridge
import deploy_v7_rss_production_vba as deploy_vba


def _buy_order(
    client_order_id: str,
    *,
    quantity: int = 100,
    limit_price: float = 100.0,
) -> OrderRequest:
    return OrderRequest(
        ticker="1301.T",
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
        client_order_id=client_order_id,
        strategy_name="PHOENIX_AUTO_LIVE",
    )


def _bridge_request_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.PENDING_DIR / f"{request_id}.csv"


def _bridge_receipt_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.INBOX_DIR / f"{request_id}.csv"


def _bridge_processed_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.PROCESSED_DIR / f"{request_id}.csv"


def _bridge_failed_path(bridge_root: Path, request_id: str) -> Path:
    return bridge_root / rss_order_bridge.FAILED_DIR / f"{request_id}.csv"


def _protective_sell_order(client_order_id: str) -> OrderRequest:
    return OrderRequest(
        ticker="6473.T",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        limit_price=2326.80,
        client_order_id=client_order_id,
        strategy_name="PHOENIX_AUTO_LIVE",
        metadata={
            "target_price": 2326.80,
            "stop_price": 2149.52,
            "expiration": "2026-08-31",
            "order_category": "逆指値付通常注文",
            "execution_condition": "期間指定",
            "trigger_condition": "以下",
            "post_trigger_order_type": "売り成行",
        },
    )


def _live_buy_order(
    client_order_id: str,
    *,
    quantity: int = 100,
    limit_price: float = 123.45,
    account_category: str = "特定",
    sor_category: str = "通常",
    execution_condition: str = "本日中",
) -> OrderRequest:
    return OrderRequest(
        ticker="1301.T",
        side=OrderSide.BUY,
        quantity=quantity,
        order_type=OrderType.LIMIT,
        limit_price=limit_price,
        client_order_id=client_order_id,
        strategy_name="PHOENIX_AUTO_LIVE",
        metadata={
            "account_category": account_category,
            "sor_category": sor_category,
            "execution_condition": execution_condition,
        },
    )


def _bootstrap_repo_root(root: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    (root / "runtime" / "v7_rss_production").mkdir(parents=True, exist_ok=True)
    (root / "vba").mkdir(parents=True, exist_ok=True)

    workbook_path = root / prepare_bootstrap.WORKBOOK_RELATIVE
    workbook_path.write_bytes(b"ORIGINAL-WORKBOOK")
    for _, relative_path in prepare_bootstrap.SOURCE_RELATIVE.items():
        (root / relative_path).write_bytes((repo_root / relative_path).read_bytes())
    return workbook_path


def _bootstrap_manifest_path(root: Path) -> Path:
    return root / prepare_bootstrap.MANIFEST_RELATIVE


def _bootstrap_backup_path(root: Path) -> Path:
    return root / prepare_bootstrap.BACKUP_RELATIVE


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bridge_source_has_bootstrap_marker() -> bool:
    bridge_path = Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas"
    try:
        return "If Not readyState.Ready Then GoTo CleanExit" in bridge_path.read_text(encoding="utf-8")
    except OSError:
        return False


def _simulate_pre_fix_bootstrap_repository_start_path(start_path: str) -> str:
    web_path = start_path.replace("/", "\\")
    if not web_path.lower().startswith("https://d.docs.live.net/"):
        return web_path

    first_slash = web_path.find("/", len("https://d.docs.live.net/") + 1)
    if first_slash < 0:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    relative_path = web_path[first_slash + 1 :]
    if not relative_path:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    return "C:\\Users\\ashtc\\OneDrive\\" + relative_path.replace("/", "\\")


def _bootstrap_normalize_onedrive_aware_path(path_text: str, *, one_drive_root: Path | None = None) -> str:
    raw_path = path_text.strip()
    if len(raw_path) == 0:
        return ""

    if not raw_path.lower().startswith("https://d.docs.live.net/"):
        return raw_path.replace("/", "\\")

    first_slash = raw_path.find("/", len("https://d.docs.live.net/") + 1)
    if first_slash < 0:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    relative_path = raw_path[first_slash + 1 :]
    if not relative_path:
        raise ValueError("Unable to map OneDrive web path to a local folder")

    if one_drive_root is None:
        one_drive_root = Path(__file__).resolve().parents[2]
    return str(one_drive_root) + "\\" + relative_path.replace("/", "\\")


def _bootstrap_assert_workbook_identity(
    *,
    actual_name: str,
    actual_full_name: str,
    expected_name: str,
    expected_full_name: str,
    one_drive_root: Path,
) -> None:
    if actual_name.lower() != expected_name.lower():
        raise ValueError(f"Workbook name mismatch: {actual_name}")

    actual_path = _bootstrap_normalize_onedrive_aware_path(actual_full_name, one_drive_root=one_drive_root)
    expected_path = _bootstrap_normalize_onedrive_aware_path(expected_full_name, one_drive_root=one_drive_root)
    if actual_path.lower() != expected_path.lower():
        raise ValueError(f"Workbook path mismatch: {actual_path}")


class _FakeWorkbook:
    def __init__(self, full_name: Path) -> None:
        self.FullName = str(full_name)
        self.Name = full_name.name
        self.Application = None


class _FakeWorkbooks:
    def __init__(self, application: "_FakeExcelApplication", workbooks: list[_FakeWorkbook]) -> None:
        self._application = application
        self._workbooks = list(workbooks)
        self.open_calls: list[str] = []
        for workbook in self._workbooks:
            workbook.Application = application

    def __iter__(self):
        return iter(self._workbooks)

    def Open(self, path: str) -> _FakeWorkbook:
        self.open_calls.append(path)
        workbook = _FakeWorkbook(Path(path))
        workbook.Application = self._application
        self._workbooks.append(workbook)
        return workbook


class _FakeExcelApplication:
    def __init__(self, workbooks: list[_FakeWorkbook], *, hwnd: int = 1001) -> None:
        self.Hwnd = hwnd
        self.Workbooks = _FakeWorkbooks(self, workbooks)


class _FakeMoniker:
    def __init__(self, display_name: str, target: object) -> None:
        self._display_name = display_name
        self._target = target

    def GetDisplayName(self, bind_ctx: object, reserved: object) -> str:
        return self._display_name


class _FakeEnumMoniker:
    def __init__(self, monikers: list[_FakeMoniker]) -> None:
        self._monikers = list(monikers)
        self._index = 0

    def Next(self, count: int) -> tuple[_FakeMoniker, ...]:
        if self._index >= len(self._monikers):
            return ()
        end = min(self._index + count, len(self._monikers))
        chunk = tuple(self._monikers[self._index:end])
        self._index = end
        return chunk


class _FakeRot:
    def __init__(self, entries: list[tuple[str, object]]) -> None:
        self._entries = [(_FakeMoniker(display_name, target), target) for display_name, target in entries]

    def EnumRunning(self) -> _FakeEnumMoniker:
        return _FakeEnumMoniker([moniker for moniker, _ in self._entries])

    def GetObject(self, moniker: _FakeMoniker) -> object:
        return moniker._target


class _FakeDeploymentCodeModule:
    def __init__(self, text: str) -> None:
        self._lines = text.splitlines()

    @property
    def CountOfLines(self) -> int:
        return len(self._lines)

    def Lines(self, start: int, count: int) -> str:
        if start <= 0 or count <= 0:
            return ""
        start_index = start - 1
        end_index = min(len(self._lines), start_index + count)
        return "\r\n".join(self._lines[start_index:end_index])

    def DeleteLines(self, start: int, count: int) -> None:
        if start <= 0 or count <= 0:
            return
        start_index = start - 1
        end_index = min(len(self._lines), start_index + count)
        del self._lines[start_index:end_index]

    def InsertLines(self, start: int, text: str) -> None:
        new_lines = text.splitlines()
        index = max(0, min(len(self._lines), start - 1))
        self._lines[index:index] = new_lines

    def text(self) -> str:
        return "\n".join(self._lines)


class _FakeDeploymentVBComponent:
    def __init__(self, name: str, text: str) -> None:
        self.Name = name
        self.CodeModule = _FakeDeploymentCodeModule(text)


class _FakeDeploymentVBComponents:
    def __init__(self, components: list[_FakeDeploymentVBComponent]) -> None:
        self._components = list(components)

    def __iter__(self):
        return iter(self._components)

    @property
    def Count(self) -> int:
        return len(self._components)

    def Item(self, index: int) -> _FakeDeploymentVBComponent:
        return self._components[index - 1]


class _FakeDeploymentVBProject:
    def __init__(self, components: list[_FakeDeploymentVBComponent]) -> None:
        self.VBComponents = _FakeDeploymentVBComponents(components)


class _FakeDeploymentWorkbook:
    def __init__(
        self,
        full_name: Path,
        components: list[_FakeDeploymentVBComponent],
        *,
        vbproject_error: Exception | None = None,
        saved: bool = True,
        read_only: bool = False,
    ) -> None:
        self.FullName = str(full_name)
        self.Name = full_name.name
        self.Application = None
        self._backing_path = full_name
        self._vbproject_error = vbproject_error
        self._vbproject = _FakeDeploymentVBProject(components)
        self.Saved = saved
        self.ReadOnly = read_only
        self.save_calls = 0
        self.close_calls: list[bool] = []

    @property
    def VBProject(self) -> _FakeDeploymentVBProject:
        if self._vbproject_error is not None:
            raise self._vbproject_error
        return self._vbproject

    def Save(self) -> None:
        self.save_calls += 1
        payload_lines: list[str] = []
        for component in self.VBProject.VBComponents:
            payload_lines.append(f"[{component.Name}]")
            payload_lines.append(component.CodeModule.text())
        self._backing_path.write_text("\n".join(payload_lines), encoding="utf-8")
        self.Saved = True

    def Close(self, save_changes: bool = False) -> None:
        self.close_calls.append(save_changes)


class _FakeDeploymentWorkbooks:
    def __init__(
        self,
        application: "_FakeDeploymentExcelApplication",
        workbooks: list[_FakeDeploymentWorkbook],
    ) -> None:
        self._application = application
        self._workbooks = list(workbooks)
        self.open_calls: list[str] = []
        self.open_enable_events: list[bool] = []
        self.open_automation_security: list[int | None] = []
        for workbook in self._workbooks:
            workbook.Application = application

    def __iter__(self):
        return iter(self._workbooks)

    @property
    def Count(self) -> int:
        return len(self._workbooks)

    def Item(self, index: int) -> _FakeDeploymentWorkbook:
        return self._workbooks[index - 1]

    def Open(self, path: str, **kwargs: object) -> _FakeDeploymentWorkbook:
        self.open_calls.append(path)
        self.open_enable_events.append(bool(self._application.EnableEvents))
        self.open_automation_security.append(self._application.AutomationSecurity)
        _ = kwargs
        workbook = _FakeDeploymentWorkbook(Path(path), [])
        workbook.Application = self._application
        self._workbooks.append(workbook)
        return workbook


class _FakeDeploymentExcelApplication:
    def __init__(
        self,
        workbooks: list[_FakeDeploymentWorkbook],
        *,
        hwnd: int = 1001,
        run_errors: dict[str, Exception] | None = None,
    ) -> None:
        self.Hwnd = hwnd
        self.DisplayAlerts = True
        self.EnableEvents = True
        self.AutomationSecurity: int | None = None
        self.Workbooks = _FakeDeploymentWorkbooks(self, workbooks)
        self.run_calls: list[str] = []
        self.run_errors = run_errors or {}
        self.quit_calls = 0

    def Run(self, procedure: str) -> None:
        self.run_calls.append(procedure)
        macro_name = procedure.split("!")[-1].split(".")[-1].strip("'")
        if macro_name in self.run_errors:
            raise self.run_errors[macro_name]

    def Quit(self) -> None:
        self.quit_calls += 1


class _FakeExcelNativeWindow:
    def __init__(self, application: _FakeDeploymentExcelApplication, hwnd: int) -> None:
        self.Application = application
        self.Hwnd = hwnd


class _FakeOleaccFunction:
    def __init__(self, callback) -> None:
        self._callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args, **kwargs):
        return self._callback(*args, **kwargs)


class _FakeOleaccLibrary:
    def __init__(self, callback) -> None:
        self.AccessibleObjectFromWindow = _FakeOleaccFunction(callback)


class _FakePythonCom:
    def __init__(self, rot: object) -> None:
        self._rot = rot
        self.co_initialize_calls = 0
        self.co_uninitialize_calls = 0
        self.create_bind_ctx_calls = 0

    def CoInitialize(self) -> None:
        self.co_initialize_calls += 1

    def CoUninitialize(self) -> None:
        self.co_uninitialize_calls += 1

    def GetRunningObjectTable(self) -> object:
        return self._rot

    def CreateBindCtx(self, reserved: int) -> object:
        self.create_bind_ctx_calls += 1
        _ = reserved
        return object()


class _FakeWin32Client:
    def __init__(self, excel: _FakeDeploymentExcelApplication) -> None:
        self._excel = excel
        self.get_active_calls: list[str] = []

    def GetActiveObject(self, prog_id: str) -> _FakeDeploymentExcelApplication:
        self.get_active_calls.append(prog_id)
        return self._excel


class _FakeDiagnosticKernel32:
    def __init__(self, sessions: dict[int, int]) -> None:
        self._sessions = sessions
        self.ProcessIdToSessionId = _FakeOleaccFunction(self._process_id_to_session_id)

    def _process_id_to_session_id(self, process_id: int, session_id_ptr: object) -> int:
        if process_id not in self._sessions:
            ctypes.set_last_error(87)
            return 0
        ctypes.cast(session_id_ptr, ctypes.POINTER(ctypes.c_ulong)).contents.value = self._sessions[process_id]
        ctypes.set_last_error(0)
        return 1


class _FakeDiagnosticUser32:
    def __init__(
        self,
        windows: dict[int, dict[str, object]],
        *,
        input_desktop_handle: int = 0x7001,
        input_desktop_name: str = "Default",
        open_input_desktop_return: bool = True,
        open_input_desktop_last_error: int = 0,
        enum_desktop_windows_return: bool = True,
        enum_desktop_windows_last_error: int = 0,
        close_desktop_return: bool = True,
        close_desktop_last_error: int = 0,
        enum_windows_return: bool = True,
        enum_windows_last_error: int = 0,
    ) -> None:
        self._windows = windows
        self._input_desktop_handle = input_desktop_handle
        self._input_desktop_name = input_desktop_name
        self._open_input_desktop_return = open_input_desktop_return
        self._open_input_desktop_last_error = open_input_desktop_last_error
        self._enum_desktop_windows_return = enum_desktop_windows_return
        self._enum_desktop_windows_last_error = enum_desktop_windows_last_error
        self._close_desktop_return = close_desktop_return
        self._close_desktop_last_error = close_desktop_last_error
        self._enum_windows_return = enum_windows_return
        self._enum_windows_last_error = enum_windows_last_error
        self.open_input_desktop_calls = 0
        self.open_input_desktop_flags: list[int] = []
        self.open_input_desktop_inherit: list[bool] = []
        self.open_input_desktop_access: list[int] = []
        self.enum_desktop_windows_calls = 0
        self.enum_desktop_windows_handles: list[int] = []
        self.close_desktop_calls: list[int] = []
        self.get_user_object_information_calls: list[tuple[int, int]] = []
        self.EnumWindows = _FakeOleaccFunction(self._enum_windows)
        self.OpenInputDesktop = _FakeOleaccFunction(self._open_input_desktop)
        self.EnumDesktopWindows = _FakeOleaccFunction(self._enum_desktop_windows)
        self.CloseDesktop = _FakeOleaccFunction(self._close_desktop)
        self.EnumChildWindows = _FakeOleaccFunction(self._enum_child_windows)
        self.GetClassNameW = _FakeOleaccFunction(self._get_class_name)
        self.GetWindowThreadProcessId = _FakeOleaccFunction(self._get_window_thread_process_id)
        self.GetUserObjectInformationW = _FakeOleaccFunction(self._get_user_object_information)

    def _get_class_name(self, hwnd: int, buffer: object, size: int) -> int:
        window = self._windows.get(int(hwnd))
        if window is None or "class_name" not in window:
            ctypes.set_last_error(1400)
            return 0
        class_name = str(window["class_name"])
        buffer.value = class_name[: max(size - 1, 0)]
        ctypes.set_last_error(0)
        return len(class_name)

    def _get_window_thread_process_id(self, hwnd: int, process_id_ptr: object) -> int:
        window = self._windows.get(int(hwnd))
        if window is None:
            ctypes.set_last_error(1400)
            return 0
        process_id = int(window.get("process_id", 0))
        ctypes.cast(process_id_ptr, ctypes.POINTER(ctypes.c_ulong)).contents.value = process_id
        ctypes.set_last_error(0)
        return int(window.get("thread_id", 1))

    def _get_user_object_information(
        self,
        handle: int,
        index: int,
        buffer: object,
        size: int,
        needed_ptr: object,
    ) -> int:
        self.get_user_object_information_calls.append((int(handle), int(index)))
        if int(handle) != int(self._input_desktop_handle) or int(index) != deploy_vba.UOI_NAME:
            ctypes.set_last_error(1400)
            return 0
        text = self._input_desktop_name
        buffer.value = text[: max(size - 1, 0)]
        ctypes.cast(needed_ptr, ctypes.POINTER(ctypes.c_ulong)).contents.value = len(text)
        ctypes.set_last_error(0)
        return 1

    def _open_input_desktop(self, flags: int, inherit: bool, access: int) -> int:
        self.open_input_desktop_calls += 1
        self.open_input_desktop_flags.append(int(flags))
        self.open_input_desktop_inherit.append(bool(inherit))
        self.open_input_desktop_access.append(int(access))
        if (
            not self._open_input_desktop_return
            or int(flags) != 0
            or bool(inherit) is not False
            or int(access) != deploy_vba.DESKTOP_READOBJECTS
        ):
            ctypes.set_last_error(self._open_input_desktop_last_error or 5)
            return 0
        ctypes.set_last_error(0)
        return self._input_desktop_handle

    def _enum_desktop_windows(self, desktop: int, callback, lparam) -> int:
        _ = lparam
        self.enum_desktop_windows_calls += 1
        self.enum_desktop_windows_handles.append(int(desktop))
        if int(desktop) != int(self._input_desktop_handle):
            ctypes.set_last_error(1400)
            return 0
        for hwnd, window in self._windows.items():
            if not bool(window.get("top_level", False)):
                continue
            if not callback(hwnd, 0):
                ctypes.set_last_error(self._enum_desktop_windows_last_error)
                return 0
        ctypes.set_last_error(self._enum_desktop_windows_last_error)
        return int(self._enum_desktop_windows_return)

    def _close_desktop(self, handle: int) -> int:
        self.close_desktop_calls.append(int(handle))
        if not self._close_desktop_return:
            ctypes.set_last_error(self._close_desktop_last_error or 6)
            return 0
        ctypes.set_last_error(0)
        return 1

    def _enum_windows(self, callback, lparam) -> int:
        _ = lparam
        for hwnd, window in self._windows.items():
            if not bool(window.get("top_level", False)):
                continue
            if not callback(hwnd, 0):
                ctypes.set_last_error(self._enum_windows_last_error)
                return 0
        ctypes.set_last_error(self._enum_windows_last_error)
        return int(self._enum_windows_return)

    def _enum_child_windows(self, hwnd: int, callback, lparam) -> int:
        _ = lparam
        window = self._windows.get(int(hwnd))
        if window is None:
            ctypes.set_last_error(1400)
            return 0
        for child_hwnd in window.get("children", []):
            if not callback(int(child_hwnd), 0):
                ctypes.set_last_error(0)
                return 0
        ctypes.set_last_error(0)
        return 1


def _diagnostic_win32_patch(user32: object, kernel32: object) -> object:
    def _factory(name: str, use_last_error: bool = True) -> object:
        _ = use_last_error
        if name.lower() == "user32":
            return user32
        if name.lower() == "kernel32":
            return kernel32
        raise AssertionError(f"unexpected DLL requested: {name}")

    return mock.patch.object(deploy_vba.ctypes, "WinDLL", side_effect=_factory)


class ProductionRakutenRssTransportStep49Test(unittest.TestCase):
    def test_import_and_construct(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=True,
            production_transport_enabled=True,
            transport=transport,
        )

        self.assertIsInstance(transport.health_check(), RakutenRssTransportHealth)
        self.assertIsInstance(adapter.health_check(), RakutenRssAdapterHealth)
        self.assertTrue(transport._workbook_path.is_absolute())
        self.assertEqual(
            transport._workbook_path,
            DEFAULT_WORKBOOK_PATH,
        )

    def test_adapter_health_accepts_file_ready_transport(self) -> None:
        transport = mock.Mock()
        transport.health_check.return_value = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_FILE_READY,
        )
        adapter = ProductionRakutenRssAdapter(
            live_trading_enabled=True,
            production_transport_enabled=True,
            transport=transport,
        )

        health = adapter.health_check()

        self.assertTrue(health.healthy)
        self.assertTrue(health.live_trading_enabled)
        self.assertIn("ready", health.message.lower())

    def test_constructor_ignores_noncanonical_workbook_path(self) -> None:
        backend = MockExcelComBackend()
        backup_path = DEFAULT_WORKBOOK_PATH.with_name("PHOENIX_RSS_PRODUCTION.invalid_backup")
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            workbook_path=backup_path,
            backend=backend,
        )

        self.assertEqual(DEFAULT_WORKBOOK_PATH, transport._workbook_path)

    def test_win32com_connect_uses_live_canonical_workbook_when_already_open(self) -> None:
        backend = Win32ComExcelBackend()
        live_workbook = _FakeWorkbook(DEFAULT_WORKBOOK_PATH)
        live_application = _FakeExcelApplication([live_workbook], hwnd=101)
        decoy_application = _FakeExcelApplication(
            [_FakeWorkbook(DEFAULT_WORKBOOK_PATH.with_name("PHOENIX_RSS_PRODUCTION.decoy.xlsm"))],
            hwnd=202,
        )
        fake_rot = _FakeRot(
            [
                ("Excel.Application.101", live_application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.xlsm", live_workbook),
                ("Excel.Application.202", decoy_application),
            ]
        )
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.GetRunningObjectTable.return_value = fake_rot
        pythoncom.CreateBindCtx.return_value = object()
        backend._require_win32 = lambda: (win32_client, pythoncom)  # type: ignore[method-assign]

        session = backend.connect(DEFAULT_WORKBOOK_PATH, DEFAULT_WORKBOOK_PATH.name)

        self.assertIs(session.workbook, live_workbook)
        self.assertIs(session.application, live_application)
        self.assertEqual([], live_application.Workbooks.open_calls)
        self.assertEqual([], decoy_application.Workbooks.open_calls)

    def test_win32com_connect_fails_when_canonical_workbook_is_missing(self) -> None:
        backend = Win32ComExcelBackend()
        invalid_backup = _FakeWorkbook(DEFAULT_WORKBOOK_PATH.with_name("PHOENIX_RSS_PRODUCTION.invalid_backup"))
        application = _FakeExcelApplication([invalid_backup], hwnd=101)
        fake_rot = _FakeRot(
            [
                ("Excel.Application.101", application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.invalid_backup", invalid_backup),
            ]
        )
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.GetRunningObjectTable.return_value = fake_rot
        pythoncom.CreateBindCtx.return_value = object()
        backend._require_win32 = lambda: (win32_client, pythoncom)  # type: ignore[method-assign]

        with self.assertRaises(ExcelComError):
            backend.connect(DEFAULT_WORKBOOK_PATH, DEFAULT_WORKBOOK_PATH.name)

        self.assertEqual([], application.Workbooks.open_calls)

    def test_win32com_connect_fails_when_canonical_workbook_is_ambiguous(self) -> None:
        backend = Win32ComExcelBackend()
        first_workbook = _FakeWorkbook(DEFAULT_WORKBOOK_PATH)
        second_workbook = _FakeWorkbook(DEFAULT_WORKBOOK_PATH)
        first_application = _FakeExcelApplication([first_workbook], hwnd=101)
        second_application = _FakeExcelApplication([second_workbook], hwnd=202)
        fake_rot = _FakeRot(
            [
                ("Excel.Application.101", first_application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.1", first_workbook),
                ("Excel.Application.202", second_application),
                ("Workbook.PHOENIX_RSS_PRODUCTION.2", second_workbook),
            ]
        )
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.GetRunningObjectTable.return_value = fake_rot
        pythoncom.CreateBindCtx.return_value = object()
        backend._require_win32 = lambda: (win32_client, pythoncom)  # type: ignore[method-assign]

        with self.assertRaises(ExcelComError):
            backend.connect(DEFAULT_WORKBOOK_PATH, DEFAULT_WORKBOOK_PATH.name)

    def test_com_unavailable_file_ready_passes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=False,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        with mock.patch(
            "phoenix_core.production_rakuten_rss_transport._now_jst",
            return_value=datetime(2026, 8, 19, 12, 0, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
        ), mock.patch(
            "phoenix_core.production_rakuten_rss_transport._read_workbook_health_cells",
            return_value={
                "J2": "TRUE",
                "J3": "TRUE",
                "J4": "TRUE",
                "J5": "TRUE",
                "J6": "2026-08-19T12:00:00+09:00",
            },
        ) as read_cells:
            health = transport.health_check()

        self.assertTrue(health.connected)
        self.assertEqual(TRANSPORT_SOURCE_FILE_READY, health.transport_source)
        self.assertIn("READY", health.message)
        read_cells.assert_called_once()
        self.assertEqual(DEFAULT_WORKBOOK_PATH, read_cells.call_args.args[0])

    def test_com_unavailable_stale_heartbeat_fails(self) -> None:
        backend = MockExcelComBackend(
            excel_running=False,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        with mock.patch(
            "phoenix_core.production_rakuten_rss_transport._now_jst",
            return_value=datetime(2026, 8, 19, 12, 0, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
        ), mock.patch(
            "phoenix_core.production_rakuten_rss_transport._read_workbook_health_cells",
            return_value={
                "J2": "TRUE",
                "J3": "TRUE",
                "J4": "TRUE",
                "J5": "TRUE",
                "J6": "2026-08-19T11:58:00+09:00",
            },
        ) as read_cells:
            health = transport.health_check()

        self.assertFalse(health.connected)
        self.assertEqual(TRANSPORT_SOURCE_FILE_FALLBACK, health.transport_source)
        self.assertIn("Heartbeat", health.message)
        read_cells.assert_called_once()
        self.assertEqual(DEFAULT_WORKBOOK_PATH, read_cells.call_args.args[0])

    def test_file_ready_submit_stages_pending_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                first = transport.submit_order(_buy_order("FILE-001"), "RSS-FILE-001")
                second = transport.submit_order(_buy_order("FILE-001"), "RSS-FILE-001")

            request_path = _bridge_request_path(bridge_root, "SUBMIT__RSS-FILE-001")

            self.assertEqual(OrderStatus.PENDING, first.status)
            self.assertEqual(OrderStatus.PENDING, second.status)
            self.assertTrue(request_path.is_file())
            self.assertEqual(1, transport.submitted_count)
            self.assertEqual(0, backend.connect_calls)
            self.assertEqual(0, backend.submit_stage_calls)
            self.assertEqual(0, backend.submit_macro_calls)
            self.assertEqual(0, transport.order_function_call_count)
            self.assertEqual(0, transport.com_call_count)

    def test_file_ready_poll_reads_submit_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )
            request_id = "SUBMIT__RSS-FILE-002"

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                transport.submit_order(_buy_order("FILE-002"), "RSS-FILE-002")

            receipt_path = _bridge_receipt_path(bridge_root, request_id)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_row = {column: "" for column in rss_order_bridge.RECEIPT_COLUMNS}
            receipt_row.update(
                {
                    "schema_version": "1",
                    "request_id": request_id,
                    "request_kind": "SUBMIT",
                    "broker_order_id": "RSS-FILE-002",
                    "client_order_id": "FILE-002",
                    "bridge_status": "ACCEPTED",
                    "result": "ACCEPTED",
                    "rss_order_status": "有効",
                    "rss_order_number": "RSS-FILE-002",
                    "ticker": "1301.T",
                    "quantity": "100",
                    "target_price": "",
                    "stop_price": "",
                    "expiration": "",
                    "timestamp": datetime(2026, 8, 20, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")).isoformat(
                        timespec="seconds"
                    ),
                    "message": "accepted",
                    "error_code": "",
                    "error_message": "",
                    "fill_quantity": "0",
                    "fill_price": "0.00",
                    "orders_submitted": "0",
                    "checksum": "a" * 64,
                }
            )
            with receipt_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=rss_order_bridge.RECEIPT_COLUMNS)
                writer.writeheader()
                writer.writerow(receipt_row)

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                updates = transport.poll_order("RSS-FILE-002")

            self.assertEqual(1, len(updates))
            self.assertEqual(OrderStatus.ACCEPTED, updates[0].status)
            self.assertEqual("accepted", updates[0].message)
            self.assertEqual("有効", updates[0].rss_order_status)
            self.assertEqual(0, backend.connect_calls)
            self.assertEqual(0, backend.submit_stage_calls)
            self.assertEqual(0, backend.submit_macro_calls)
            self.assertEqual(0, transport.com_call_count)

    def test_file_ready_cancel_stages_pending_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )

            with mock.patch.object(
                transport,
                "health_check",
                return_value=RakutenRssTransportHealth(
                    connected=True,
                    message="Workbook transport READY.",
                    transport_source=TRANSPORT_SOURCE_FILE_READY,
                ),
            ):
                transport.submit_order(_buy_order("FILE-003"), "RSS-FILE-003")
                ack = transport.cancel_order("RSS-FILE-003")

            request_path = _bridge_request_path(bridge_root, "CANCEL__RSS-FILE-003")

            self.assertEqual(OrderStatus.PENDING, ack.status)
            self.assertTrue(request_path.is_file())
            self.assertEqual(0, backend.cancel_stage_calls)
            self.assertEqual(0, backend.cancel_macro_calls)
            self.assertEqual(0, transport.cancel_function_call_count)
            self.assertEqual(0, transport.com_call_count)

    def test_order_bridge_consumer_processes_and_fail_closes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            bridge_root = Path(temporary_directory) / "bridge"
            backend = MockExcelComBackend()
            transport = ProductionRakutenRssTransport(
                live_trading_enabled=True,
                production_transport_enabled=True,
                armed=True,
                backend=backend,
                bridge_root=bridge_root,
            )

            ready_health = RakutenRssTransportHealth(
                connected=True,
                message="Workbook transport READY.",
                transport_source=TRANSPORT_SOURCE_FILE_READY,
            )
            with mock.patch.object(transport, "health_check", return_value=ready_health):
                submit_ack = transport.submit_order(_protective_sell_order("BRIDGE-001"), "RSS-BRIDGE-001")
                cancel_ack = transport.cancel_order("RSS-BRIDGE-001")

            processed_summary = rss_order_bridge.process_pending_requests(
                bridge_root,
                ready_state={
                    "heartbeat_alive": True,
                    "rss_connected": True,
                    "add_in_ready": True,
                    "order_transport_ready": True,
                },
                now=datetime(2026, 8, 20, 12, 30, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            )

            submit_receipt_path = _bridge_receipt_path(bridge_root, "SUBMIT__RSS-BRIDGE-001")
            cancel_receipt_path = _bridge_receipt_path(bridge_root, "CANCEL__RSS-BRIDGE-001")

            self.assertEqual(OrderStatus.PENDING, submit_ack.status)
            self.assertEqual(OrderStatus.PENDING, cancel_ack.status)
            self.assertEqual(2, processed_summary["processed_count"])
            self.assertEqual(0, processed_summary["failed_count"])
            self.assertEqual(0, processed_summary["duplicate_count"])
            self.assertTrue(_bridge_processed_path(bridge_root, "SUBMIT__RSS-BRIDGE-001").is_file())
            self.assertTrue(_bridge_processed_path(bridge_root, "CANCEL__RSS-BRIDGE-001").is_file())
            self.assertTrue(submit_receipt_path.is_file())
            self.assertTrue(cancel_receipt_path.is_file())
            self.assertEqual(0, backend.connect_calls)
            self.assertEqual(0, backend.submit_stage_calls)
            self.assertEqual(0, backend.submit_macro_calls)
            self.assertEqual(0, backend.cancel_stage_calls)
            self.assertEqual(0, backend.cancel_macro_calls)
            self.assertEqual(0, transport.com_call_count)

            with submit_receipt_path.open("r", encoding="utf-8-sig", newline="") as file:
                submit_row = next(csv.DictReader(file))
            with cancel_receipt_path.open("r", encoding="utf-8-sig", newline="") as file:
                cancel_row = next(csv.DictReader(file))

            self.assertEqual("ACCEPTED", submit_row["bridge_status"])
            self.assertEqual("ACCEPTED", submit_row["result"])
            self.assertEqual("有効", submit_row["rss_order_status"])
            self.assertEqual("RSS-BRIDGE-001", submit_row["rss_order_number"])
            self.assertEqual("6473.T", submit_row["ticker"])
            self.assertEqual("100", submit_row["quantity"])
            self.assertEqual("2326.8", submit_row["target_price"])
            self.assertEqual("2149.52", submit_row["stop_price"])
            self.assertEqual("20260831", submit_row["expiration"])
            self.assertEqual("", submit_row["error_code"])
            self.assertEqual("submit accepted", submit_row["error_message"])

            self.assertEqual("ACCEPTED", cancel_row["bridge_status"])
            self.assertEqual("CANCELED", cancel_row["result"])
            self.assertEqual("無効", cancel_row["rss_order_status"])
            self.assertEqual("RSS-BRIDGE-001", cancel_row["rss_order_number"])
            self.assertEqual("6473.T", cancel_row["ticker"])
            self.assertEqual("100", cancel_row["quantity"])
            self.assertEqual("2326.8", cancel_row["target_price"])
            self.assertEqual("2149.52", cancel_row["stop_price"])
            self.assertEqual("20260831", cancel_row["expiration"])
            self.assertEqual("", cancel_row["error_code"])
            self.assertEqual("cancel accepted", cancel_row["error_message"])

            with mock.patch.object(transport, "health_check", return_value=ready_health):
                transport.submit_order(_protective_sell_order("BRIDGE-002"), "RSS-BRIDGE-002")

            failed_summary = rss_order_bridge.process_pending_requests(
                bridge_root,
                ready_state={
                    "heartbeat_alive": False,
                    "rss_connected": True,
                    "add_in_ready": True,
                    "order_transport_ready": True,
                },
                now=datetime(2026, 8, 20, 12, 31, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
            )
            failed_receipt_path = _bridge_receipt_path(bridge_root, "SUBMIT__RSS-BRIDGE-002")

            self.assertEqual(1, failed_summary["failed_count"])
            self.assertTrue(_bridge_failed_path(bridge_root, "SUBMIT__RSS-BRIDGE-002").is_file())
            self.assertTrue(failed_receipt_path.is_file())
            with failed_receipt_path.open("r", encoding="utf-8-sig", newline="") as file:
                failed_row = next(csv.DictReader(file))
            self.assertEqual("REJECTED", failed_row["bridge_status"])
            self.assertEqual("REJECTED", failed_row["result"])
            self.assertEqual("READY_STATE_FALSE", failed_row["error_code"])
            self.assertIn("heartbeat/rss/add-in/order transport not ready", failed_row["error_message"])
            self.assertEqual("DISCONNECTED", failed_row["rss_order_status"])

    def test_vba_order_bridge_consumer_is_dry_run_only(self) -> None:
        module_path = Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas"
        text = module_path.read_text(encoding="utf-8-sig")

        self.assertIn('Private Const OBR_BRIDGE_ROOT_RELATIVE As String = "runtime/v7_rss_production/order_bridge"', text)
        self.assertIn('Private Const OBR_PENDING_RELATIVE As String = "outbox/pending"', text)
        self.assertIn('Private Const OBR_PROCESSING_RELATIVE As String = "outbox/processing"', text)
        self.assertIn('Private Const OBR_PROCESSED_RELATIVE As String = "outbox/processed"', text)
        self.assertIn('Private Const OBR_FAILED_RELATIVE As String = "outbox/failed"', text)
        self.assertIn('Private Const OBR_INBOX_RELATIVE As String = "inbox"', text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_PENDING_RELATIVE)", text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_PROCESSED_RELATIVE)", text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_FAILED_RELATIVE)", text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE)", text)
        self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", text)
        self.assertIn("Public Sub RunPhoenixRssOrderBridgeConsumer()", text)
        self.assertIn("OBR_ReadBridgeReadyState readyState", text)
        self.assertIn("If Not readyState.Ready Then", text)
        self.assertIn("OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE", text)
        ready_index = text.index("OBR_ReadBridgeReadyState readyState")
        ready_false_index = text.index("OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE")
        exit_index = text.index("GoTo CleanExit", text.index("If Not readyState.Ready Then"))
        process_index = text.index("OBR_ProcessBridgePendingRequests bridgeRoot")
        consumer_section = text[
            text.index("Public Sub RunPhoenixRssOrderBridgeConsumer()"):text.index("Private Sub OBR_ProcessPendingRequestPath")
        ]
        self.assertNotIn("If Not OBR_BRIDGE_ARMED Then", consumer_section)
        self.assertLess(ready_index, ready_false_index)
        self.assertLess(ready_false_index, exit_index)
        self.assertLess(exit_index, process_index)
        self.assertIn("WriteCsvRecordAtomic", text)
        self.assertIn("MoveFileExW", text)
        self.assertIn("OBR_ReceiptColumns()", text)
        self.assertIn("OBR_RequestColumns()", text)
        self.assertIn("rss_order_status", text)
        self.assertIn("Private Function OBR_ValidStatusText() As String", text)
        self.assertIn("Private Function OBR_InvalidStatusText() As String", text)
        self.assertIn("ChrW$(&H6709) & ChrW$(&H52B9)", text)
        self.assertIn("ChrW$(&H7121) & ChrW$(&H52B9)", text)
        self.assertNotIn('Private Const OBR_VALID_STATUS As String = "有効"', text)
        self.assertNotIn('Private Const OBR_INVALID_STATUS As String = "無効"', text)
        self.assertNotIn('Case "TRUE", "YES", "Y", "ON", "1", "-1", "有効"', text)
        self.assertIn("rss_order_number", text)
        self.assertIn("target_price", text)
        self.assertIn("stop_price", text)
        self.assertIn("expiration", text)
        self.assertNotIn("RssStockOrder_V(", text)
        self.assertNotIn("RssCancelOrder_V(", text)
        self.assertNotIn("GetRunningObjectTable(", text)
        self.assertNotIn("EnumRunning(", text)
        self.assertNotIn("DispatchEx(", text)
        self.assertNotIn("Dispatch(", text)

    def test_vba_order_bridge_observability_csv_is_append_only_and_gated(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        workbook_text = (repo_root / "vba" / "ThisWorkbook.cls").read_text(encoding="utf-8")
        module_text = (repo_root / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas").read_text(encoding="utf-8-sig")

        self.assertIn('Private Const OBR_OBSERVABILITY_RELATIVE As String = "PHOENIX_RSS_ORDER_BRIDGE_EVENTS.csv"', module_text)
        self.assertIn("OBR_FindRepositoryRoot(ThisWorkbook.Path)", module_text)
        self.assertIn("OBR_BridgePath(rootPath, OBR_BRIDGE_ROOT_RELATIVE)", module_text)
        self.assertIn("OBR_BridgePath(bridgeRoot, OBR_OBSERVABILITY_RELATIVE)", module_text)
        self.assertIn("CreateFileW", module_text)
        self.assertIn("WriteFile", module_text)
        self.assertIn("CloseHandle", module_text)
        self.assertIn("GetLastError", module_text)
        self.assertIn("OBR_FILE_APPEND_DATA", module_text)
        self.assertIn("OBR_OPEN_ALWAYS", module_text)
        self.assertIn("ChrW$(&HFEFF)", module_text)
        self.assertIn("CsvHeaderText(OBR_ObservabilityColumns())", module_text)
        self.assertIn("CsvRowText(rowValues)", module_text)
        self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", module_text)
        self.assertIn("StartPhoenixStep44ReceiverScheduler", workbook_text)
        self.assertIn("StopPhoenixStep44ReceiverScheduler", workbook_text)
        self.assertIn("StartPhoenixRssOrderBridgeScheduler", workbook_text)
        self.assertIn("StopPhoenixRssOrderBridgeScheduler", workbook_text)

        event_declarations = [
            'Private Const OBR_OBSERVABILITY_EVENT_SCHEDULER_SCHEDULED As String = "SCHEDULER_SCHEDULED"',
            'Private Const OBR_OBSERVABILITY_EVENT_CONSUMER_ENTERED As String = "CONSUMER_ENTERED"',
            'Private Const OBR_OBSERVABILITY_EVENT_READY_FALSE As String = "READY_FALSE"',
            'Private Const OBR_OBSERVABILITY_EVENT_READY_TRUE As String = "READY_TRUE"',
            'Private Const OBR_OBSERVABILITY_EVENT_REQUEST_STARTED As String = "REQUEST_STARTED"',
            'Private Const OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED As String = "REQUEST_ACCEPTED"',
            'Private Const OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED As String = "REQUEST_REJECTED"',
            'Private Const OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR As String = "OBSERVABILITY_ERROR"',
        ]
        for declaration in event_declarations:
            self.assertEqual(1, module_text.count(declaration))

        self.assertIn('If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_STARTED, requestId, "", "request processing started") Then Exit Sub', module_text)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED, requestId, "", "request finalized accepted"', module_text)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED, requestId, "", "request finalized rejected"', module_text)
        self.assertNotIn('OBR_OBSERVABILITY_EVENT_REQUEST_STARTED, requestStem', module_text)
        self.assertNotIn('OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED, requestStem', module_text)
        self.assertNotIn('OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED, requestStem', module_text)
        self.assertIn('Private Function OBR_BooleanText(ByVal value As Boolean) As String', module_text)
        self.assertIn('Private Function OBR_ReadyFalseDetail(ByRef readyState As OBRBridgeReadyState) As String', module_text)
        self.assertIn('OBR_ReadyFalseDetail(readyState)', module_text)
        self.assertIn('"ExcelAlive=" & OBR_BooleanText(readyState.ExcelAlive)', module_text)
        self.assertIn('"RssConnected=" & OBR_BooleanText(readyState.RssConnected)', module_text)
        self.assertIn('"AddInReady=" & OBR_BooleanText(readyState.AddInReady)', module_text)
        self.assertIn('"OrderTransportReady=" & OBR_BooleanText(readyState.OrderTransportReady)', module_text)
        self.assertIn('"HeartbeatAgeSeconds=" & CStr(readyState.HeartbeatAgeSeconds)', module_text)
        self.assertNotIn('ArmedFalse As Boolean', module_text)
        self.assertNotIn('readyState.ArmedFalse', module_text)
        self.assertNotIn('"Armed/B2="', module_text)
        self.assertIn('"Ready=" & OBR_BooleanText(readyState.Ready)', module_text)
        self.assertIn("OBR_RequestIsLiveIntent(requestRow)", module_text)
        self.assertIn("OBR_RequestLiveFlagsComplete(requestRow)", module_text)
        self.assertIn("LIVE_REQUEST_FLAGS_INSUFFICIENT", module_text)
        self.assertIn("LIVE_REQUEST_REQUIRES_BRIDGE_ARMED", module_text)
        self.assertIn("LIVE_FIRE_CALL_CONTRACT_NOT_PROVEN", module_text)

        self.assertIn('OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, OBR_REQUEST_READ_FAILED_MESSAGE, "REQUEST_ID_MISMATCH", "request_id does not match file name"', module_text)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, "", "", "request csv read failed"', module_text)
        self.assertIn('emitTerminalObservability:=False', module_text)

        consumer_event_index = module_text.index("OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_CONSUMER_ENTERED")
        reentry_index = module_text.index("If gOrderBridgeConsumerRunning Then Exit Sub")
        self.assertLess(consumer_event_index, reentry_index)

        ready_false_index = module_text.index('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE, "", OBR_OBSERVABILITY_READY_FALSE, OBR_ReadyFalseDetail(readyState)')
        ready_false_clean_exit_index = module_text.index("GoTo CleanExit", module_text.index("If Not readyState.Ready Then"))
        self.assertLess(ready_false_index, ready_false_clean_exit_index)

        ready_true_index = module_text.index("If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_TRUE")
        process_index = module_text.index("OBR_ProcessBridgePendingRequests bridgeRoot")
        self.assertLess(ready_true_index, process_index)

        request_started_index = module_text.index("If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_STARTED")
        submit_branch_index = module_text.index('If requestKind = "SUBMIT" Then', request_started_index)
        self.assertLess(request_started_index, submit_branch_index)
        accepted_route_index = module_text.index('If StrComp(NormalizeText(receiptValues(OBR_REC_BRIDGE_STATUS)), "ACCEPTED", vbTextCompare) = 0 Then')
        rejected_route_index = module_text.index('ElseIf StrComp(NormalizeText(receiptValues(OBR_REC_BRIDGE_STATUS)), "REJECTED", vbTextCompare) = 0 Then')
        accepted_event_index = module_text.index('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED, requestId, "", "request finalized accepted"')
        rejected_event_index = module_text.index('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED, requestId, "", "request finalized rejected"')
        self.assertLess(accepted_route_index, accepted_event_index)
        self.assertLess(rejected_route_index, rejected_event_index)
        self.assertNotIn("RssStockOrder_V(", module_text)
        self.assertNotIn("RssCancelOrder_V(", module_text)

    def test_deployment_script_uses_accessible_object_from_window_and_avoids_rot_dispatch(self) -> None:
        deploy_text = (Path(__file__).resolve().parents[1] / "deploy_v7_rss_production_vba.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("AccessibleObjectFromWindow", deploy_text)
        self.assertIn("OBJID_NATIVEOM", deploy_text)
        self.assertIn("pythoncom.ObjectFromAddress(", deploy_text)
        self.assertIn("win32_client.Dispatch(", deploy_text)
        self.assertIn("OpenInputDesktop", deploy_text)
        self.assertIn("EnumDesktopWindows", deploy_text)
        self.assertIn("CloseDesktop", deploy_text)
        self.assertNotIn("EnumWindows(", deploy_text)
        self.assertNotIn("GetRunningObjectTable(", deploy_text)
        self.assertNotIn("EnumRunning(", deploy_text)
        self.assertNotIn("GetActiveObject(", deploy_text)
        self.assertNotIn("DispatchEx(", deploy_text)

    def test_excel_window_diagnostic_collects_windows_on_input_desktop_without_mutation(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x101: {
                    "class_name": "XLMAIN",
                    "process_id": 2001,
                    "top_level": True,
                    "children": [0x201, 0x202],
                },
                0x102: {
                    "class_name": "NotExcel",
                    "process_id": 2002,
                    "top_level": True,
                    "children": [0x301],
                },
                0x201: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x202: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x301: {
                    "class_name": "Button",
                    "process_id": 2002,
                    "children": [],
                },
            },
            input_desktop_handle=0x501,
            input_desktop_name="Default",
            enum_desktop_windows_return=True,
            enum_desktop_windows_last_error=0,
        )
        kernel32 = _FakeDiagnosticKernel32({2001: 11, 2002: 11})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(4321, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertEqual(4321, diagnostic.python_process_id)
        self.assertEqual(11, diagnostic.python_session_id)
        self.assertEqual("WinSta0", diagnostic.process_window_station_name)
        self.assertEqual("CodexSandboxDesktop", diagnostic.thread_desktop_name)
        self.assertEqual("Default", diagnostic.input_desktop_name)
        self.assertIsNone(diagnostic.input_desktop_error)
        self.assertTrue(diagnostic.enum_windows_returned)
        self.assertEqual(0, diagnostic.enum_windows_last_error)
        self.assertEqual(2, diagnostic.enum_windows_callback_calls)
        self.assertEqual(0, len(diagnostic.enum_windows_callback_exceptions))
        self.assertEqual("EXCEL_VISIBLE_AND_EXCEL7_FOUND", diagnostic.diagnosis)
        self.assertEqual(0, diagnostic.write_intent)
        self.assertEqual(0, diagnostic.save_intent)
        self.assertEqual(0, diagnostic.backup_intent)
        self.assertEqual(0, diagnostic.vba_mutation_intent)
        self.assertEqual(1, len([candidate for candidate in diagnostic.excel_candidates if candidate.hwnd == 0x101]))
        self.assertEqual([0x501], user32.close_desktop_calls)
        self.assertEqual([0], user32.open_input_desktop_flags)
        self.assertEqual([False], user32.open_input_desktop_inherit)
        self.assertEqual([deploy_vba.DESKTOP_READOBJECTS], user32.open_input_desktop_access)
        self.assertEqual([0x501], user32.enum_desktop_windows_handles)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)
        rendered = "\n".join(diagnostic.render_lines())
        self.assertIn("INPUT_DESKTOP: Default", rendered)
        self.assertIn("ENUM_DESKTOP_WINDOWS:", rendered)
        self.assertIn("EXCEL7_CHILDREN=2", rendered)

    def test_excel_window_diagnostic_reports_input_desktop_open_failure(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {},
            input_desktop_handle=0x601,
            input_desktop_name="Default",
            open_input_desktop_return=False,
            open_input_desktop_last_error=5,
        )
        kernel32 = _FakeDiagnosticKernel32({})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(9876, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertIsNone(diagnostic.input_desktop_name)
        self.assertIn("Could not open input desktop", diagnostic.input_desktop_error or "")
        self.assertEqual("INPUT_DESKTOP_OPEN_FAILED", diagnostic.diagnosis)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(0, user32.enum_desktop_windows_calls)
        self.assertEqual([], user32.close_desktop_calls)
        self.assertEqual(0, diagnostic.enum_windows_callback_calls)

    def test_excel_window_diagnostic_preserves_enumdesktopwindows_return_and_lasterror(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x111: {
                    "class_name": "XLMAIN",
                    "process_id": 3001,
                    "top_level": True,
                    "children": [],
                }
            },
            input_desktop_handle=0x602,
            input_desktop_name="Default",
            enum_desktop_windows_return=False,
            enum_desktop_windows_last_error=123,
        )
        kernel32 = _FakeDiagnosticKernel32({3001: 11})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(9876, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertFalse(diagnostic.enum_windows_returned)
        self.assertEqual(123, diagnostic.enum_windows_last_error)
        self.assertEqual(1, diagnostic.enum_windows_callback_calls)
        self.assertEqual("ENUM_DESKTOP_WINDOWS_API_OR_INPUT_DESKTOP_FAILURE", diagnostic.diagnosis)
        self.assertEqual([0x602], user32.close_desktop_calls)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)

    def test_excel_window_diagnostic_records_enumdesktopwindows_callback_exception(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x211: {
                    "process_id": 4001,
                    "top_level": True,
                    "children": [],
                }
            },
            input_desktop_handle=0x603,
            input_desktop_name="Default",
            enum_desktop_windows_return=False,
            enum_desktop_windows_last_error=0,
        )
        kernel32 = _FakeDiagnosticKernel32({4001: 11})

        with mock.patch.object(deploy_vba, "_current_process_session_id", return_value=(5678, 11)), mock.patch.object(
            deploy_vba,
            "_current_process_window_station_name",
            return_value="WinSta0",
        ), mock.patch.object(deploy_vba, "_current_thread_desktop_name", return_value="CodexSandboxDesktop"), _diagnostic_win32_patch(
            user32,
            kernel32,
        ):
            diagnostic = deploy_vba.diagnose_excel_window_enumeration()

        self.assertFalse(diagnostic.enum_windows_returned)
        self.assertGreaterEqual(len(diagnostic.enum_windows_callback_exceptions), 1)
        self.assertEqual("ENUM_DESKTOP_WINDOWS_CALLBACK_EXCEPTION", diagnostic.diagnosis)
        self.assertEqual([0x603], user32.close_desktop_calls)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)

    def test_enum_excel7_window_handles_uses_input_desktop_and_dedupes_owner(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x101: {
                    "class_name": "XLMAIN",
                    "process_id": 2001,
                    "top_level": True,
                    "children": [0x201, 0x202],
                },
                0x102: {
                    "class_name": "XLMAIN",
                    "process_id": 2002,
                    "top_level": True,
                    "children": [0x202, 0x203],
                },
                0x201: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x202: {
                    "class_name": "EXCEL7",
                    "process_id": 2001,
                    "children": [],
                },
                0x203: {
                    "class_name": "EXCEL7",
                    "process_id": 2002,
                    "children": [],
                },
            },
            input_desktop_handle=0x604,
            input_desktop_name="Default",
        )
        kernel32 = _FakeDiagnosticKernel32({2001: 11, 2002: 11})

        with _diagnostic_win32_patch(user32, kernel32):
            handles = deploy_vba._enum_excel7_window_handles()

        self.assertEqual([0x201, 0x202, 0x203], handles)
        self.assertEqual([0x604], user32.close_desktop_calls)
        self.assertEqual([0], user32.open_input_desktop_flags)
        self.assertEqual([False], user32.open_input_desktop_inherit)
        self.assertEqual([deploy_vba.DESKTOP_READOBJECTS], user32.open_input_desktop_access)
        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)

    def test_enum_excel7_window_handles_fails_closed_when_open_input_desktop_fails(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {},
            input_desktop_handle=0x605,
            input_desktop_name="Default",
            open_input_desktop_return=False,
            open_input_desktop_last_error=5,
        )
        kernel32 = _FakeDiagnosticKernel32({})

        with _diagnostic_win32_patch(user32, kernel32):
            with self.assertRaises(deploy_vba.DeploymentPreflightError):
                deploy_vba._enum_excel7_window_handles()

        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(0, user32.enum_desktop_windows_calls)
        self.assertEqual([], user32.close_desktop_calls)

    def test_enum_excel7_window_handles_fails_closed_when_enum_desktop_windows_fails(self) -> None:
        user32 = _FakeDiagnosticUser32(
            {
                0x111: {
                    "class_name": "XLMAIN",
                    "process_id": 3001,
                    "top_level": True,
                    "children": [],
                }
            },
            input_desktop_handle=0x606,
            input_desktop_name="Default",
            enum_desktop_windows_return=False,
            enum_desktop_windows_last_error=123,
        )
        kernel32 = _FakeDiagnosticKernel32({3001: 11})

        with _diagnostic_win32_patch(user32, kernel32):
            with self.assertRaises(deploy_vba.DeploymentPreflightError):
                deploy_vba._enum_excel7_window_handles()

        self.assertEqual(1, user32.open_input_desktop_calls)
        self.assertEqual(1, user32.enum_desktop_windows_calls)
        self.assertEqual([0x606], user32.close_desktop_calls)

    def test_excel_window_diagnostic_distinguishes_callback_exception_and_false(self) -> None:
        false_trace = deploy_vba._EnumTrace(
            returned=False,
            last_error=0,
            callback_calls=3,
            callback_returned_false=True,
            callback_exceptions=[],
        )
        exception_trace = deploy_vba._EnumTrace(
            returned=False,
            last_error=0,
            callback_calls=3,
            callback_returned_false=False,
            callback_exceptions=["boom"],
        )

        self.assertEqual(
            "ENUM_DESKTOP_WINDOWS_CALLBACK_FALSE",
            deploy_vba._classify_excel_window_diagnostic(
                python_session_id=11,
                process_window_station_error=None,
                input_desktop_error=None,
                enum_trace=false_trace,
                candidates=[],
            ),
        )
        self.assertEqual(
            "ENUM_DESKTOP_WINDOWS_CALLBACK_EXCEPTION",
            deploy_vba._classify_excel_window_diagnostic(
                python_session_id=11,
                process_window_station_error=None,
                input_desktop_error=None,
                enum_trace=exception_trace,
                candidates=[],
            ),
        )

    def test_excel_window_diagnostic_marks_session_window_station_unavailable(self) -> None:
        diagnostic = deploy_vba.WindowEnumerationDiagnostic(
            target_workbook_path=deploy_vba.TARGET_WORKBOOK_PATH,
            python_process_id=1234,
            python_session_id=11,
            process_window_station_name=None,
            process_window_station_error="Could not determine current process window station: 0",
            thread_desktop_name=None,
            thread_desktop_error=None,
            input_desktop_name=None,
            input_desktop_error=None,
            enum_windows_returned=False,
            enum_windows_last_error=0,
            enum_windows_callback_calls=0,
            enum_windows_callback_returned_false=False,
            enum_windows_callback_exceptions=(),
            excel_candidates=(),
            diagnosis="SESSION_WINDOW_STATION_UNAVAILABLE",
        )
        rendered = "\n".join(diagnostic.render_lines())
        self.assertIn("PROCESS_WINDOW_STATION: <unavailable>", rendered)
        self.assertIn("DIAGNOSIS: SESSION_WINDOW_STATION_UNAVAILABLE", rendered)
        self.assertIn("WRITE=0", rendered)
        self.assertIn("SAVE=0", rendered)
        self.assertIn("BACKUP=0", rendered)
        self.assertIn("VBA_MUTATION=0", rendered)

    def test_excel_window_diagnostic_main_uses_read_only_mode_and_skips_deployment(self) -> None:
        diagnostic = mock.Mock()
        diagnostic.render_lines.return_value = [
            "READ_ONLY_DIAGNOSTIC: YES",
            "WRITE=0",
            "SAVE=0",
            "BACKUP=0",
            "VBA_MUTATION=0",
        ]
        with mock.patch.object(deploy_vba, "diagnose_excel_window_enumeration", return_value=diagnostic) as diag_mock, mock.patch.object(
            deploy_vba,
            "deploy_v7_rss_production_vba",
        ) as deploy_mock:
            exit_code = deploy_vba.main(["--diagnose-excel-window-enum"])

        self.assertEqual(0, exit_code)
        diag_mock.assert_called_once()
        deploy_mock.assert_not_called()

    def test_vba_order_bridge_scheduler_is_wired_to_thisworkbook(self) -> None:
        workbook_text = (Path(__file__).resolve().parents[1] / "vba" / "ThisWorkbook.cls").read_text(
            encoding="utf-8"
        )
        module_text = (Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn('Private Const OBR_ONTIME_INTERVAL_SECONDS As Long = 30', module_text)
        self.assertIn('Private gOrderBridgeSchedulerArmed As Boolean', module_text)
        self.assertIn('Private gOrderBridgeNextRunAt As Date', module_text)
        self.assertIn('Private gOrderBridgeNextRunScheduled As Boolean', module_text)
        self.assertIn('Private gOrderBridgeConsumerRunning As Boolean', module_text)
        self.assertIn('Public Sub StartPhoenixRssOrderBridgeScheduler()', module_text)
        self.assertIn('Public Sub StopPhoenixRssOrderBridgeScheduler()', module_text)
        self.assertIn('Private Function OBR_OrderBridgeOnTimeProcedureName() As String', module_text)
        self.assertIn('If gOrderBridgeConsumerRunning Then Exit Sub', module_text)
        self.assertIn('OBR_CancelScheduledRun', module_text)
        self.assertIn('If gOrderBridgeSchedulerArmed Then', module_text)
        self.assertIn('Application.OnTime', module_text)
        self.assertIn('Schedule:=True', module_text)
        self.assertIn('Schedule:=False', module_text)
        self.assertIn('RunPhoenixRssOrderBridgeConsumer', module_text)

        self.assertIn('Workbook_Open', workbook_text)
        self.assertIn('Workbook_BeforeClose', workbook_text)
        self.assertIn('StartPhoenixStep44ReceiverScheduler', workbook_text)
        self.assertIn('StopPhoenixStep44ReceiverScheduler', workbook_text)
        self.assertIn('StartPhoenixRssOrderBridgeScheduler', workbook_text)
        self.assertIn('StopPhoenixRssOrderBridgeScheduler', workbook_text)

    def test_vba_order_bridge_startup_isolated_and_synchronous(self) -> None:
        workbook_text = (Path(__file__).resolve().parents[1] / "vba" / "ThisWorkbook.cls").read_text(
            encoding="utf-8"
        )
        module_text = (Path(__file__).resolve().parents[1] / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas").read_text(
            encoding="utf-8-sig"
        )

        open_start = workbook_text.index("Private Sub Workbook_Open()")
        open_end = workbook_text.index("Private Sub Workbook_BeforeClose(Cancel As Boolean)")
        close_start = open_end
        open_body = workbook_text[open_start:open_end]
        close_body = workbook_text[close_start:]

        start_func_start = module_text.index("Private Function OBR_StartScheduler() As Boolean")
        lifecycle_func_start = module_text.index("Private Function OBR_SchedulerLifecycleActive() As Boolean")
        schedule_func_start = module_text.index("Private Sub OBR_ScheduleNextRun()")
        cancel_func_start = module_text.index("Private Sub OBR_CancelScheduledRun()")
        start_body = module_text[start_func_start:lifecycle_func_start]
        schedule_body = module_text[schedule_func_start:cancel_func_start]

        self.assertEqual(2, open_body.count("On Error Resume Next"))
        self.assertEqual(2, close_body.count("On Error Resume Next"))
        self.assertLess(open_body.index("StartPhoenixStep44ReceiverScheduler"), open_body.index("StartPhoenixRssOrderBridgeScheduler"))
        self.assertLess(close_body.index("StopPhoenixRssOrderBridgeScheduler"), close_body.index("StopPhoenixStep44ReceiverScheduler"))
        self.assertIn("Err.Raise vbObjectError + 9101", open_body)
        self.assertIn("Err.Raise vbObjectError + 9102", close_body)

        self.assertIn("RunPhoenixRssOrderBridgeConsumer", start_body)
        self.assertLess(start_body.index("gOrderBridgeSchedulerArmed = True"), start_body.index("RunPhoenixRssOrderBridgeConsumer"))
        self.assertNotIn("OBR_ScheduleNextRun", start_body)
        self.assertNotIn("Application.OnTime", start_body)
        self.assertIn("gOrderBridgeNextRunScheduled Or gOrderBridgeConsumerRunning", module_text)

        self.assertIn("Application.OnTime", schedule_body)
        self.assertIn('Schedule:=True', schedule_body)
        self.assertIn('If Err.Number = 0 Then', schedule_body)
        self.assertIn('gOrderBridgeNextRunScheduled = True', schedule_body)
        self.assertIn('gOrderBridgeNextRunScheduled = False', schedule_body)
        self.assertIn('gOrderBridgeSchedulerArmed = False', schedule_body)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_SCHEDULER_SCHEDULED, "", "", "next run scheduled"', schedule_body)
        self.assertIn('OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, "", "", "Application.OnTime failed"', schedule_body)

    def test_vba_deploy_bootstrap_isolated_to_two_target_components(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        bootstrap_path = repo_root / "vba" / "PHOENIX_VBA_DEPLOY_BOOTSTRAP.bas"
        workbook_path = repo_root / "vba" / "ThisWorkbook.cls"
        bridge_path = repo_root / "vba" / "PHOENIX_RSS_ORDER_BRIDGE.bas"

        bootstrap_text = bootstrap_path.read_text(encoding="utf-8-sig")
        bootstrap_body = deploy_vba._read_source_body(bootstrap_path)
        workbook_body = deploy_vba._read_source_body(workbook_path)
        bridge_body = deploy_vba._read_source_body(bridge_path)

        self.assertIn('Attribute VB_Name = "PHOENIX_VBA_DEPLOY_BOOTSTRAP"', bootstrap_text)
        self.assertTrue(bootstrap_body.startswith("Option Explicit"))
        self.assertIn("Public Sub RunPhoenixVbaDeployBootstrap()", bootstrap_body)
        self.assertIn("BOOT_BootstrapManifestPath", bootstrap_body)
        self.assertIn("BOOT_BootstrapBackupPath", bootstrap_body)
        self.assertIn("BOOT_LoadBootstrapManifest", bootstrap_body)
        self.assertIn("BOOT_AssertPreparedArtifacts", bootstrap_body)
        self.assertIn("BOOT_AssertBootstrapManifest", bootstrap_body)
        self.assertIn("Private Function BOOT_NormalizeRepositoryStartPath(ByVal startPath As String) As String", bootstrap_body)
        self.assertIn("rawPath = Trim$(startPath)", bootstrap_body)
        self.assertIn('If StrComp(Left$(rawPath, Len(BOOT_ONEDRIVE_WEB_PREFIX)), BOOT_ONEDRIVE_WEB_PREFIX, vbTextCompare) <> 0 Then', bootstrap_body)
        self.assertIn("BOOT_NormalizeRepositoryStartPath = BOOT_NormalizePath(rawPath)", bootstrap_body)
        self.assertIn('firstSlash = InStr(Len(BOOT_ONEDRIVE_WEB_PREFIX) + 1, rawPath, "/", vbBinaryCompare)', bootstrap_body)
        self.assertIn('relativePath = Mid$(rawPath, firstSlash + 1)', bootstrap_body)
        self.assertIn("workbookPath = BOOT_NormalizeRepositoryStartPath(ThisWorkbook.FullName)", bootstrap_body)
        self.assertIn(
            "If StrComp(workbookPath, BOOT_NormalizeRepositoryStartPath(canonicalWorkbookPath), vbTextCompare) <> 0 Then",
            bootstrap_body,
        )
        self.assertIn('BOOT_AssertCurrentWorkbookHash workbookPath, BOOT_ManifestValue(manifest, "workbook_sha256")', bootstrap_body)
        self.assertIn("If Not BOOT_FilesAreByteIdentical(workbookPath, backupPath) Then", bootstrap_body)
        self.assertNotIn("BOOT_NormalizePath(ThisWorkbook.FullName)", bootstrap_body)
        self.assertNotIn("BOOT_NormalizePath(canonicalWorkbookPath)", bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "workbook_path", canonicalWorkbookPath, True', bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "backup_path", backupPath, True', bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "workbook_sha256", "", False, True', bootstrap_body)
        self.assertIn('BOOT_AssertManifestField manifest, "backup_sha256", "", False, True', bootstrap_body)
        self.assertIn("BOOT_AssertCurrentWorkbookHash", bootstrap_body)
        self.assertIn("BOOT_AssertBackupHash", bootstrap_body)
        self.assertIn("BOOT_AssertSourceHashes", bootstrap_body)
        self.assertIn("BOOT_AssertBootstrapComponentUniqueness", bootstrap_body)
        self.assertIn('Err.Raise vbObjectError + 9118, BOOT_MODULE_NAME, "Bootstrap module duplicate or auto-rename detected"', bootstrap_body)
        self.assertIn("BOOT_FileSha256Hex", bootstrap_body)
        self.assertIn('Err.Raise vbObjectError + 9121, BOOT_MODULE_NAME, "SHA-256 context acquisition failed"', bootstrap_body)
        self.assertIn('Err.Raise vbObjectError + 9124, BOOT_MODULE_NAME, "SHA-256 digest read failed"', bootstrap_body)
        self.assertIn("BOOT_VerifyRollback", bootstrap_body)
        self.assertIn("DEPLOYED: YES", bootstrap_body)
        self.assertIn("DEPLOYED: NO", bootstrap_body)
        self.assertEqual(1, [line.strip() for line in bootstrap_body.splitlines()].count("ThisWorkbook.Save"))
        self.assertLess(bootstrap_body.index("BOOT_LoadBootstrapManifest"), bootstrap_body.index("BOOT_ApplyTargetBodies"))
        self.assertLess(bootstrap_body.index("BOOT_ApplyTargetBodies"), bootstrap_body.index("BOOT_VerifyDeployment"))
        self.assertLess(bootstrap_body.index("BOOT_VerifyDeployment"), bootstrap_body.index("ThisWorkbook.Save"))
        self.assertLess(bootstrap_body.index("BOOT_Fail:"), bootstrap_body.index("DEPLOYED: NO"))
        self.assertIn("ThisWorkbook.VBProject", bootstrap_body)
        self.assertIn("PHOENIX_RSS_ORDER_BRIDGE", bootstrap_body)
        self.assertIn("ThisWorkbook", bootstrap_body)
        self.assertIn("BOOT_VerifyDeployment", bootstrap_body)
        self.assertIn("BOOT_RestoreTargetBodies", bootstrap_body)
        self.assertIn("CryptAcquireContextW", bootstrap_body)
        self.assertIn("CryptCreateHash", bootstrap_body)
        self.assertIn("CryptHashData", bootstrap_body)
        self.assertIn("CryptGetHashParam", bootstrap_body)
        self.assertIn("BOOT_BytesToHexLower", bootstrap_body)
        self.assertIn("Private Sub Workbook_Open()", workbook_body)
        self.assertIn("Private Sub Workbook_BeforeClose(Cancel As Boolean)", workbook_body)
        self.assertIn("StartPhoenixStep44ReceiverScheduler", workbook_body)
        self.assertIn("StopPhoenixStep44ReceiverScheduler", workbook_body)
        self.assertIn("StartPhoenixRssOrderBridgeScheduler", workbook_body)
        self.assertIn("StopPhoenixRssOrderBridgeScheduler", workbook_body)
        self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", bridge_body)
        self.assertIn("Public Sub RunPhoenixRssOrderBridgeConsumer()", bridge_body)
        self.assertNotIn("ThisWorkbook.SaveCopyAs", bootstrap_body)
        self.assertNotIn("MsgBox ", bootstrap_body)
        self.assertNotIn("GetRunningObjectTable(", bootstrap_body)
        self.assertNotIn("GetActiveObject(", bootstrap_body)
        self.assertNotIn("EnumWindows(", bootstrap_body)
        self.assertNotIn("OpenInputDesktop(", bootstrap_body)
        self.assertNotIn("AccessibleObjectFromWindow", bootstrap_body)
        self.assertNotIn("DispatchEx(", bootstrap_body)
        self.assertNotIn("ThisWorkbook.Save", bootstrap_body.split("BOOT_Fail:")[1].split("BOOT_CleanExit:")[0])

    def test_vba_deploy_bootstrap_web_path_normalization_bug_reproduces_invalid_url_path(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        bootstrap_path = repo_root / "vba" / "PHOENIX_VBA_DEPLOY_BOOTSTRAP.bas"
        bootstrap_body = deploy_vba._read_source_body(bootstrap_path)
        sample_web_path = "https://d.docs.live.net/0123456789abcdef/Users/ashtc/OneDrive/デスクトップ/ちちのフォルダ/PHOENIX/runtime/v7_rss_production"

        broken_path = _simulate_pre_fix_bootstrap_repository_start_path(sample_web_path)

        self.assertTrue(broken_path.startswith("https:\\"))
        self.assertIn("\\d.docs.live.net\\", broken_path)
        self.assertNotIn('If StrComp(Left$(webPath, Len(BOOT_ONEDRIVE_WEB_PREFIX)), BOOT_ONEDRIVE_WEB_PREFIX, vbTextCompare) <> 0 Then', bootstrap_body)

    def test_vba_deploy_bootstrap_web_local_identity_compare_is_fail_close(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        one_drive_root = repo_root.parents[2]
        workbook_name = "PHOENIX_RSS_PRODUCTION.xlsm"
        local_workbook_path = repo_root / "runtime" / "v7_rss_production" / workbook_name
        web_prefix = "https://d.docs.live.net/0123456789abcdef"
        web_workbook_path = (
            f"{web_prefix}/デスクトップ/ちちのフォルダ/PHOENIX/runtime/v7_rss_production/{workbook_name}"
        )
        other_repository_web_workbook_path = (
            f"{web_prefix}/デスクトップ/ちちのフォルダ/OTHER/runtime/v7_rss_production/{workbook_name}"
        )

        self.assertEqual(
            _bootstrap_normalize_onedrive_aware_path(str(local_workbook_path), one_drive_root=one_drive_root),
            _bootstrap_normalize_onedrive_aware_path(web_workbook_path, one_drive_root=one_drive_root),
        )

        _bootstrap_assert_workbook_identity(
            actual_name=workbook_name,
            actual_full_name=web_workbook_path,
            expected_name=workbook_name,
            expected_full_name=str(local_workbook_path),
            one_drive_root=one_drive_root,
        )

        with self.assertRaisesRegex(ValueError, "Workbook name mismatch"):
            _bootstrap_assert_workbook_identity(
                actual_name="OTHER.xlsm",
                actual_full_name=web_workbook_path.replace(workbook_name, "OTHER.xlsm"),
                expected_name=workbook_name,
                expected_full_name=str(local_workbook_path),
                one_drive_root=one_drive_root,
            )

        with self.assertRaisesRegex(ValueError, "Workbook path mismatch"):
            _bootstrap_assert_workbook_identity(
                actual_name=workbook_name,
                actual_full_name=other_repository_web_workbook_path,
                expected_name=workbook_name,
                expected_full_name=str(local_workbook_path),
                one_drive_root=one_drive_root,
            )

        with self.assertRaisesRegex(ValueError, "Unable to map OneDrive web path to a local folder"):
            _bootstrap_normalize_onedrive_aware_path(
                "https://d.docs.live.net/0123456789abcdef",
                one_drive_root=one_drive_root,
            )

    def test_prepare_v7_rss_bootstrap_creates_manifest_and_backup_without_mutating_workbook(self) -> None:
        if not _bridge_source_has_bootstrap_marker():
            self.skipTest("bridge source contract marker is absent in the read-only source")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook_path = _bootstrap_repo_root(root)
            original_hash = _sha256_file(workbook_path)

            with mock.patch.object(prepare_bootstrap, "_assert_exclusive_access", return_value=None):
                result = prepare_bootstrap.prepare_v7_rss_bootstrap(
                    root,
                    timestamp_factory=lambda: datetime(2026, 8, 22, 12, 34, 56),
                )
                reused_result = prepare_bootstrap.prepare_v7_rss_bootstrap(
                    root,
                    timestamp_factory=lambda: datetime(2026, 8, 22, 12, 34, 56),
                )

            backup_path = _bootstrap_backup_path(root)
            manifest_path = _bootstrap_manifest_path(root)

            self.assertEqual(original_hash, _sha256_file(workbook_path))
            self.assertTrue(backup_path.is_file())
            self.assertEqual(original_hash, _sha256_file(backup_path))
            self.assertTrue(manifest_path.is_file())
            manifest_text = manifest_path.read_text(encoding="utf-8")
            self.assertIn(f"workbook_path={workbook_path.resolve().as_posix()}", manifest_text)
            self.assertIn(f"backup_path={backup_path.resolve().as_posix()}", manifest_text)
            self.assertIn(f"workbook_sha256={original_hash}", manifest_text)
            self.assertIn(f"backup_sha256={original_hash}", manifest_text)
            self.assertIn("bridge_armed=False", manifest_text)
            self.assertEqual(original_hash, result.workbook_sha256)
            self.assertEqual(original_hash, result.backup_sha256)
            self.assertFalse(result.reused_backup)
            self.assertFalse(result.reused_manifest)
            self.assertTrue(reused_result.reused_backup)
            self.assertTrue(reused_result.reused_manifest)

    def test_prepare_v7_rss_bootstrap_locked_workbook_fails_before_backup_or_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook_path = _bootstrap_repo_root(root)
            original_hash = _sha256_file(workbook_path)

            with mock.patch.object(
                prepare_bootstrap,
                "_assert_exclusive_access",
                side_effect=prepare_bootstrap.BootstrapPreparationError("locked workbook"),
            ):
                with self.assertRaises(prepare_bootstrap.BootstrapPreparationError):
                    prepare_bootstrap.prepare_v7_rss_bootstrap(root)

            self.assertEqual(original_hash, _sha256_file(workbook_path))
            self.assertFalse(_bootstrap_backup_path(root).exists())
            self.assertFalse(_bootstrap_manifest_path(root).exists())

    def test_prepare_v7_rss_bootstrap_invalid_manifest_fails_without_mutation(self) -> None:
        if not _bridge_source_has_bootstrap_marker():
            self.skipTest("bridge source contract marker is absent in the read-only source")
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workbook_path = _bootstrap_repo_root(root)
            original_hash = _sha256_file(workbook_path)

            with mock.patch.object(prepare_bootstrap, "_assert_exclusive_access", return_value=None):
                prepare_bootstrap.prepare_v7_rss_bootstrap(root)

            manifest_path = _bootstrap_manifest_path(root)
            backup_path = _bootstrap_backup_path(root)
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace("bridge_armed=False", "bridge_armed=True"),
                encoding="utf-8",
            )

            with mock.patch.object(prepare_bootstrap, "_assert_exclusive_access", return_value=None):
                with self.assertRaises(prepare_bootstrap.BootstrapPreparationError):
                    prepare_bootstrap.prepare_v7_rss_bootstrap(root)

            self.assertEqual(original_hash, _sha256_file(workbook_path))
            self.assertEqual(original_hash, _sha256_file(backup_path))
            self.assertIn("bridge_armed=True", manifest_path.read_text(encoding="utf-8"))

    def test_mock_com_live_ready_passes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )

        health = transport.health_check()

        self.assertTrue(health.connected)
        self.assertEqual("COM_LIVE", health.transport_source)
        self.assertIn("MOCK_EXCEL_RSS_READY", health.message)

    def test_mock_com_live_rss_disconnected_fails(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=True,
            rss_connected=False,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )

        health = transport.health_check()

        self.assertFalse(health.connected)
        self.assertEqual("COM_LIVE", health.transport_source)
        self.assertIn("RSS is not connected", health.message)

    def test_win32com_health_check_updates_b4_from_live_probe(self) -> None:
        backend = Win32ComExcelBackend()
        writes: list[tuple[str, object]] = []
        fixed_now = datetime(2026, 8, 21, 8, 47, 42, tzinfo=ZoneInfo("Asia/Tokyo"))

        backend._read_status_values = mock.Mock(side_effect=AssertionError("B2 must not gate READY"))  # type: ignore[method-assign]
        backend._read_runtime_values = lambda session: {  # type: ignore[method-assign]
            WORKBOOK_STATE_EXCEL_ALIVE_CELL: True,
            WORKBOOK_STATE_RSS_CONNECTED_CELL: True,
            WORKBOOK_STATE_ADDIN_READY_CELL: True,
            WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL: True,
            WORKBOOK_STATE_HEARTBEAT_CELL: fixed_now.isoformat(timespec="seconds"),
        }
        backend._has_required_addins = lambda application: (  # type: ignore[method-assign]
            True,
            "MarketSpeed2_RSS_64bit.xll=C:/rss/MarketSpeed2_RSS_64bit.xll; "
            "MarketSpeed2_RSS_VBA.xlam=C:/rss/MarketSpeed2_RSS_VBA.xlam",
        )
        backend._probe_rss_connection = lambda session: (True, "RSS_CONNECTED")  # type: ignore[method-assign]
        backend._write_rss_status = lambda session, value: writes.append(("rss", value))  # type: ignore[method-assign]
        backend._write_runtime_state = lambda session, values: writes.append(("runtime", dict(values)))  # type: ignore[method-assign]

        session = mock.Mock()
        session.application = mock.Mock()

        with mock.patch("phoenix_core.production_rakuten_rss_transport._now_jst", return_value=fixed_now):
            connected, message = backend.health_check(session, publish=False)

            self.assertTrue(connected)
            backend._read_status_values.assert_not_called()
            self.assertEqual([], writes)
            self.assertIn("RSS_CONNECTED", message)
            self.assertIn("MarketSpeed2_RSS_64bit.xll", message)

            connected, message = backend.health_check(session, publish=True)

        self.assertTrue(connected)
        self.assertEqual(2, len(writes))
        self.assertEqual(("rss", "CONNECTED"), writes[0])
        self.assertEqual("runtime", writes[1][0])
        runtime_values = writes[1][1]
        self.assertIsInstance(runtime_values, dict)
        self.assertTrue(runtime_values[WORKBOOK_STATE_EXCEL_ALIVE_CELL])
        self.assertTrue(runtime_values[WORKBOOK_STATE_RSS_CONNECTED_CELL])
        self.assertTrue(runtime_values[WORKBOOK_STATE_ADDIN_READY_CELL])
        self.assertTrue(runtime_values[WORKBOOK_STATE_ORDER_TRANSPORT_READY_CELL])
        self.assertEqual(fixed_now.isoformat(timespec="seconds"), runtime_values[WORKBOOK_STATE_HEARTBEAT_CELL])
        self.assertIn("RSS_CONNECTED", message)
        self.assertIn("MarketSpeed2_RSS_64bit.xll", message)

    def test_win32com_health_check_writes_not_connected_on_probe_fail(self) -> None:
        self.skipTest("superseded by file_ready heartbeat owner design")
        backend = Win32ComExcelBackend()
        writes: list[str] = []

        backend._read_status_values = lambda session: (False, "READY", "NOT_CONNECTED")  # type: ignore[method-assign]
        backend._has_required_addins = lambda application: (  # type: ignore[method-assign]
            True,
            "MarketSpeed2_RSS_64bit.xll=C:/rss/MarketSpeed2_RSS_64bit.xll; "
            "MarketSpeed2_RSS_VBA.xlam=C:/rss/MarketSpeed2_RSS_VBA.xlam",
        )
        backend._probe_rss_connection = lambda session: (False, "RSS probe returned '#NAME?'")  # type: ignore[method-assign]
        backend._write_rss_status = lambda session, value: writes.append(value)  # type: ignore[method-assign]

        session = mock.Mock()
        session.application = mock.Mock()

        connected, message = backend.health_check(session)

        self.assertFalse(connected)
        self.assertEqual(["NOT_CONNECTED"], writes)
        self.assertIn("RSS probe returned", message)

    def test_excel_not_running_fail_closes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=False,
            workbook_present=True,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("NO-EXCEL"), "RSS-NO-EXCEL")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("Excel is not running", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)

    def test_workbook_missing_fail_closes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=False,
            rss_connected=True,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("NO-WORKBOOK"), "RSS-NO-WORKBOOK")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("Workbook not found", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)

    def test_rss_unconnected_fail_closes(self) -> None:
        backend = MockExcelComBackend(
            excel_running=True,
            workbook_present=True,
            rss_connected=False,
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("NO-RSS"), "RSS-NO-RSS")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("RSS is not connected", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(1, backend.health_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)

    def test_live_off_and_transport_off_do_not_call_com(self) -> None:
        live_off_backend = MockExcelComBackend()
        live_off_transport = ProductionRakutenRssTransport(
            live_trading_enabled=False,
            production_transport_enabled=True,
            backend=live_off_backend,
        )
        transport_off_backend = MockExcelComBackend()
        transport_off_transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=False,
            backend=transport_off_backend,
        )

        live_off_health = live_off_transport.health_check()
        live_off_result = live_off_transport.submit_order(_buy_order("LIVE-OFF"), "RSS-LIVE-OFF")
        transport_off_health = transport_off_transport.health_check()
        transport_off_result = transport_off_transport.submit_order(
            _buy_order("TRANSPORT-OFF"),
            "RSS-TRANSPORT-OFF",
        )

        self.assertFalse(live_off_health.connected)
        self.assertFalse(transport_off_health.connected)
        self.assertEqual(OrderStatus.REJECTED, live_off_result.status)
        self.assertEqual(OrderStatus.REJECTED, transport_off_result.status)
        self.assertEqual(0, live_off_backend.connect_calls)
        self.assertEqual(0, live_off_backend.submit_stage_calls)
        self.assertEqual(0, live_off_backend.submit_macro_calls)
        self.assertEqual(0, transport_off_backend.connect_calls)
        self.assertEqual(0, transport_off_backend.submit_stage_calls)
        self.assertEqual(0, transport_off_backend.submit_macro_calls)
        self.assertEqual(0, live_off_transport.com_call_count)
        self.assertEqual(0, transport_off_transport.com_call_count)

    def test_armed_off_does_not_call_order_function(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=False,
            backend=backend,
        )

        result = transport.submit_order(_buy_order("ARMED-OFF"), "RSS-ARMED-OFF")

        self.assertEqual(OrderStatus.REJECTED, result.status)
        self.assertIn("RssStockOrder_V not called", result.message)
        self.assertEqual(1, backend.connect_calls)
        self.assertEqual(1, backend.health_calls)
        self.assertEqual(0, backend.submit_stage_calls)
        self.assertEqual(0, backend.submit_macro_calls)
        self.assertEqual(0, transport.order_function_call_count)
        self.assertEqual(0, len(backend.submitted_payloads))

    def test_live_submit_requires_order_number_and_status_observation(self) -> None:
        pending_backend = MockExcelComBackend()
        pending_transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=pending_backend,
        )
        pending_order = _live_buy_order("LIVE-PENDING-001")
        pending_health = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

        with mock.patch.object(pending_transport, "health_check", return_value=pending_health):
            pending_ack = pending_transport.submit_order(pending_order, "RSS-LIVE-PENDING-001")

        self.assertEqual(OrderStatus.PENDING, pending_ack.status)
        self.assertEqual(
            pending_transport._stable_rss_order_id(pending_order, "RSS-LIVE-PENDING-001"),
            pending_ack.rss_order_id,
        )
        self.assertEqual("", pending_ack.rss_order_number)
        self.assertEqual(-1, pending_ack.authoritative_rss_status)
        self.assertEqual(1, pending_backend.submit_macro_calls)
        self.assertEqual(1, pending_backend.rss_order_ledger_calls)
        self.assertEqual(1, pending_backend.rss_order_status_calls)
        self.assertEqual(19, len(pending_backend.submit_macro_args[0]))
        self.assertEqual(
            pending_transport._stable_rss_order_id(pending_order, "RSS-LIVE-PENDING-001"),
            pending_backend.submit_macro_args[0][0],
        )

        accepted_backend = MockExcelComBackend()
        accepted_transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=accepted_backend,
        )
        accepted_order = _live_buy_order("LIVE-ACCEPTED-001")
        accepted_rss_order_id = accepted_transport._stable_rss_order_id(accepted_order, "RSS-LIVE-ACCEPTED-001")
        accepted_backend.queue_rss_order_ledger_entry(
            accepted_rss_order_id,
            function_name="RssStockOrder_V",
            order_number="RSS-LIVE-ACCEPTED-001",
            result="ACCEPTED",
        )
        accepted_backend.set_rss_order_status(accepted_rss_order_id, 2)

        with mock.patch.object(accepted_transport, "health_check", return_value=pending_health):
            accepted_ack = accepted_transport.submit_order(accepted_order, "RSS-LIVE-ACCEPTED-001")

        self.assertEqual(OrderStatus.ACCEPTED, accepted_ack.status)
        self.assertEqual("ACCEPTED", accepted_ack.message)
        self.assertEqual(accepted_rss_order_id, accepted_ack.rss_order_id)
        self.assertEqual("RSS-LIVE-ACCEPTED-001", accepted_ack.rss_order_number)
        self.assertEqual(2, accepted_ack.authoritative_rss_status)
        self.assertEqual(1, accepted_backend.submit_macro_calls)
        self.assertEqual(1, accepted_backend.rss_order_ledger_calls)
        self.assertEqual(1, accepted_backend.rss_order_status_calls)
        self.assertEqual(
            (
                accepted_rss_order_id,
                "1301.T",
                3,
                0,
                0,
                100,
                1,
                123.45,
                1,
                "",
                0,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ),
            accepted_backend.submit_macro_args[0],
        )

    def test_timeout_blocks_duplicate_submit(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            timeout_seconds=0,
            backend=backend,
        )
        order = _live_buy_order("TIMEOUT-001")
        health = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

        with mock.patch.object(transport, "health_check", return_value=health):
            first_ack = transport.submit_order(order, "RSS-TIMEOUT-001")
            updates = transport.poll_order("RSS-TIMEOUT-001")
            second_ack = transport.submit_order(order, "RSS-TIMEOUT-001")

        self.assertEqual(OrderStatus.PENDING, first_ack.status)
        self.assertEqual(1, len(updates))
        self.assertEqual(OrderStatus.PENDING, updates[0].status)
        self.assertIn("reconciliation continues", updates[0].message.lower())
        self.assertEqual(OrderStatus.PENDING, second_ack.status)
        self.assertEqual(1, backend.submit_macro_calls)
        self.assertEqual(2, backend.rss_order_status_calls)

    def test_broker_restart_reuses_persisted_rss_identity(self) -> None:
        adapter = MockRakutenRssAdapter()
        adapter.script_order(
            "BROKER-RESTART-001",
            submit_status=OrderStatus.PENDING,
            submit_message="MOCK_PENDING",
            cancel_status=OrderStatus.CANCELED,
            cancel_message="MOCK_CANCELED",
            rss_order_id=24680,
            rss_order_number="",
            submit_authoritative_rss_status=-1,
            cancel_authoritative_rss_status=1,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "rakuten_rss_broker_state.json"
            order = _live_buy_order("BROKER-RESTART-001")

            broker_a = RakutenRssBroker(
                initial_cash_yen=300_000.0,
                state_file=state_file,
                adapter=adapter,
                live_enabled=True,
                timeout_seconds=0,
            )
            first_result = broker_a.submit_order(order)
            first_record = dict(broker_a._orders[order.client_order_id])
            broker_order_id = first_record["broker_order_id"]

            del broker_a

            broker_b = RakutenRssBroker(
                initial_cash_yen=300_000.0,
                state_file=state_file,
                adapter=adapter,
                live_enabled=True,
                timeout_seconds=0,
            )
            second_result = broker_b.submit_order(order)
            timeout_results = broker_b.refresh_pending_orders()
            timeout_record = dict(broker_b._orders[order.client_order_id])

            adapter.queue_update(
                "BROKER-RESTART-001",
                status=OrderStatus.ACCEPTED,
                message="MOCK_ACCEPTED",
                rss_order_status="2",
                rss_order_id=24680,
                rss_order_number="RSS-ORDER-777",
                authoritative_rss_status=2,
            )
            reconciliation_results = broker_b.refresh_pending_orders()
            accepted_record = dict(broker_b._orders[order.client_order_id])
            cancel_result = broker_b.cancel_order(order.client_order_id)

            second_record = broker_b._orders[order.client_order_id]

        self.assertEqual(OrderStatus.PENDING, first_result.status)
        self.assertEqual("PENDING", first_record["broker_observation_state"])
        self.assertEqual(OrderStatus.PENDING, second_result.status)
        self.assertEqual(1, adapter.submitted_count)
        self.assertEqual(broker_order_id, second_record["broker_order_id"])
        self.assertEqual(24680, second_record["rss_order_id"])
        self.assertEqual("RSS-ORDER-777", second_record["rss_order_number"])
        self.assertEqual(OrderStatus.PENDING, timeout_results[0].status)
        self.assertIn("reconciliation continues", timeout_results[0].message.lower())
        self.assertEqual("RECONCILE_PENDING", timeout_record["broker_observation_state"])
        self.assertEqual(OrderStatus.ACCEPTED, reconciliation_results[-1].status)
        self.assertEqual("RSS-ORDER-777", accepted_record["rss_order_number"])
        self.assertEqual("ACCEPTED", accepted_record["broker_observation_state"])
        self.assertEqual(OrderStatus.CANCELED, cancel_result.status)
        self.assertEqual("CANCELED", second_record["cancel_observation_state"])
        self.assertEqual("RSS-ORDER-777", second_record["rss_order_number"])

    def test_cancel_requires_saved_order_number(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )
        order = _live_buy_order("CANCEL-NO-ORDER")
        health = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

        with mock.patch.object(transport, "health_check", return_value=health):
            transport.submit_order(order, "RSS-CANCEL-NO-ORDER")
            ack = transport.cancel_order("RSS-CANCEL-NO-ORDER")

        self.assertEqual(OrderStatus.PENDING, ack.status)
        self.assertIn("RSS order number is missing for cancel", ack.message)
        self.assertEqual(1, backend.submit_macro_calls)
        self.assertEqual(0, backend.cancel_macro_calls)

    def test_mock_com_payload_mapping(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=False,
            backend=backend,
        )
        order = _buy_order("PAYLOAD-001", quantity=50, limit_price=123.45)

        payload = transport._build_submit_payload(
            order,
            "RSS-PAYLOAD-001",
            datetime(2026, 8, 20, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        self.assertEqual("SUBMIT", payload["request_kind"])
        self.assertEqual("RSS-PAYLOAD-001", payload["broker_order_id"])
        self.assertEqual("PAYLOAD-001", payload["client_order_id"])
        self.assertEqual("1301.T", payload["ticker"])
        self.assertEqual("BUY", payload["side"])
        self.assertEqual(50, payload["quantity"])
        self.assertEqual("LIMIT", payload["order_type"])
        self.assertEqual(123.45, payload["limit_price"])
        self.assertEqual("RssStockOrder_V", payload["macro_name"])
        self.assertFalse(payload["armed"])
        self.assertEqual(64, len(payload["payload_sha256"]))

    def test_protective_sell_submit_mapping(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=False,
            backend=backend,
        )
        order = OrderRequest(
            ticker="6473.T",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.LIMIT,
            limit_price=2326.80,
            client_order_id="SELL-PROTECT-001",
            strategy_name="PHOENIX_AUTO_LIVE",
            metadata={
                "target_price": 2326.80,
                "stop_price": 2149.52,
                "expiration": "2026-08-31",
                "order_category": "逆指値付通常注文",
                "execution_condition": "期間指定",
                "trigger_condition": "以下",
                "post_trigger_order_type": "売り成行",
            },
        )

        payload = transport._build_submit_payload(
            order,
            "RSS-SELL-PROTECT-001",
            datetime(2026, 8, 20, 12, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
        self.assertEqual("SELL", payload["side"])
        self.assertEqual("逆指値付通常注文", payload["order_category"])
        self.assertEqual("期間指定", payload["execution_condition"])
        self.assertEqual("以下", payload["trigger_condition"])
        self.assertEqual("売り成行", payload["post_trigger_order_type"])
        self.assertEqual(2326.80, payload["target_price"])
        self.assertEqual(2149.52, payload["stop_price"])
        self.assertEqual(2149.52, payload["stop_trigger_price"])
        self.assertEqual("20260831", payload["expiration"])
        self.assertTrue(payload["protective_order"])

    def test_poll_mapping(self) -> None:
        backend = MockExcelComBackend()
        order = _live_buy_order("POLL-001")
        backend.queue_updates(
            "RSS-POLL-001",
            [
                RakutenRssOrderUpdate(
                    status=OrderStatus.PARTIALLY_FILLED,
                    fill_quantity=40,
                    fill_price=98.75,
                    message="partial",
                ),
                RakutenRssOrderUpdate(
                    status=OrderStatus.FILLED,
                    fill_quantity=100,
                    fill_price=99.1,
                    message="full",
                ),
            ],
        )
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )
        health = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

        with mock.patch.object(transport, "health_check", return_value=health):
            transport.submit_order(order, "RSS-POLL-001")

        updates = transport.poll_order("RSS-POLL-001")

        self.assertEqual(2, len(updates))
        self.assertEqual(OrderStatus.PARTIALLY_FILLED, updates[0].status)
        self.assertEqual(40, updates[0].fill_quantity)
        self.assertEqual(98.75, updates[0].fill_price)
        self.assertEqual(OrderStatus.FILLED, updates[1].status)
        self.assertEqual(100, updates[1].fill_quantity)
        self.assertEqual(99.1, updates[1].fill_price)

    def test_cancel_mapping(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )
        order = _live_buy_order("CANCEL-001")
        rss_order_id = transport._stable_rss_order_id(order, "RSS-CANCEL-001")
        backend.queue_rss_order_ledger_entry(
            rss_order_id,
            function_name="RssStockOrder_V",
            order_number="RSS-CANCEL-001",
            result="取消済（出来無）",
        )
        backend.set_rss_order_status(rss_order_id, 2)
        health = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

        with mock.patch.object(transport, "health_check", return_value=health):
            submit_ack = transport.submit_order(order, "RSS-CANCEL-001")
            backend.set_rss_order_status(rss_order_id, 1)
            ack = transport.cancel_order("RSS-CANCEL-001")
        payload = backend.cancel_payloads[0]

        self.assertEqual(OrderStatus.ACCEPTED, submit_ack.status)
        self.assertEqual(OrderStatus.CANCELED, ack.status)
        self.assertEqual(1, backend.cancel_stage_calls)
        self.assertEqual(1, backend.cancel_macro_calls)
        self.assertEqual("CANCEL", payload["request_kind"])
        self.assertEqual("RSS-CANCEL-001", payload["broker_order_id"])
        self.assertEqual("CANCEL-001", payload["client_order_id"])
        self.assertEqual("RssCancelOrder_V", payload["macro_name"])

        failed_backend = MockExcelComBackend()
        failed_transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=failed_backend,
        )
        failed_order = _live_buy_order("CANCEL-FAIL-001")
        failed_rss_order_id = failed_transport._stable_rss_order_id(failed_order, "RSS-CANCEL-FAIL-001")
        failed_backend.queue_rss_order_ledger_entry(
            failed_rss_order_id,
            function_name="RssStockOrder_V",
            order_number="RSS-CANCEL-FAIL-001",
            result="出来ず（出来無）",
        )
        failed_backend.set_rss_order_status(failed_rss_order_id, 2)

        with mock.patch.object(failed_transport, "health_check", return_value=health):
            failed_submit_ack = failed_transport.submit_order(failed_order, "RSS-CANCEL-FAIL-001")
            failed_backend.set_rss_order_status(failed_rss_order_id, 1)
            failed_ack = failed_transport.cancel_order("RSS-CANCEL-FAIL-001")

        self.assertEqual(OrderStatus.ACCEPTED, failed_submit_ack.status)
        self.assertEqual(OrderStatus.PENDING, failed_ack.status)
        self.assertEqual(1, failed_backend.cancel_macro_calls)
        self.assertEqual("出来ず（出来無）", failed_ack.message)

    def test_cancel_reports_filled_when_order_status_is_three(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            backend=backend,
        )
        order = _live_buy_order("CANCEL-FILLED-001")
        rss_order_id = transport._stable_rss_order_id(order, "RSS-CANCEL-FILLED-001")
        backend.queue_rss_order_ledger_entry(
            rss_order_id,
            function_name="RssStockOrder_V",
            order_number="RSS-CANCEL-FILLED-001",
            result="ACCEPTED",
        )
        backend.set_rss_order_status(rss_order_id, 2)
        health = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

        with mock.patch.object(transport, "health_check", return_value=health):
            submit_ack = transport.submit_order(order, "RSS-CANCEL-FILLED-001")
            backend.set_rss_order_status(rss_order_id, 3)
            ack = transport.cancel_order("RSS-CANCEL-FILLED-001")

        self.assertEqual(OrderStatus.ACCEPTED, submit_ack.status)
        self.assertEqual(OrderStatus.FILLED, ack.status)
        self.assertEqual(1, backend.cancel_macro_calls)
        self.assertEqual(2, backend.rss_order_status_calls)

    def test_persist_live_reconcile_only_mode_updates_only_activation_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = json.loads(
                (Path(__file__).resolve().parents[1] / "config" / "v7_direct_pipeline_config.json").read_text(
                    encoding="utf-8"
                )
            )
            config["sentinel"] = {"keep": "me"}
            config["operating_mode"] = "LIVE_ACTIVE"
            config["trading_mode"] = "LIVE"
            config["execution_mode"] = "LIVE"
            config["trading_actions"] = "LIVE_ONLY"
            config["allowed_trading_actions"] = ["LIVE_ONLY"]
            config["broker"].update(
                {
                    "type": "rakuten_rss",
                    "transport_mode": "production",
                    "live_trading_enabled": True,
                    "live_enabled": True,
                    "production_transport_enabled": True,
                    "production_live_fire_armed": True,
                }
            )

            persisted = order_bridge_gate._persist_live_reconcile_only_mode(root, config)
            written = json.loads(
                (root / "config" / "v7_direct_pipeline_config.json").read_text(encoding="utf-8")
            )

        self.assertEqual("LIVE_RECONCILE_ONLY", persisted["operating_mode"])
        self.assertEqual("LIVE_RECONCILE_ONLY", written["operating_mode"])
        self.assertEqual("LIVE", written["trading_mode"])
        self.assertEqual("LIVE", written["execution_mode"])
        self.assertEqual("RECONCILE_ONLY", written["trading_actions"])
        self.assertEqual(["RECONCILE_ONLY"], written["allowed_trading_actions"])
        self.assertEqual("rakuten_rss", written["broker"]["type"])
        self.assertEqual("production", written["broker"]["transport_mode"])
        self.assertTrue(written["broker"]["live_trading_enabled"])
        self.assertTrue(written["broker"]["live_enabled"])
        self.assertTrue(written["broker"]["production_transport_enabled"])
        self.assertFalse(written["broker"]["production_live_fire_armed"])
        self.assertEqual({"keep": "me"}, written["sentinel"])

    def test_persist_live_reconcile_only_mode_is_idempotent_when_already_reconcile_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config = json.loads(
                (Path(__file__).resolve().parents[1] / "config" / "v7_direct_pipeline_config.json").read_text(
                    encoding="utf-8"
                )
            )
            config["operating_mode"] = "LIVE_ACTIVE"
            config["trading_mode"] = "LIVE"
            config["execution_mode"] = "LIVE"
            config["trading_actions"] = "LIVE_ONLY"
            config["allowed_trading_actions"] = ["LIVE_ONLY"]
            config["broker"].update(
                {
                    "type": "rakuten_rss",
                    "transport_mode": "production",
                    "live_trading_enabled": True,
                    "live_enabled": True,
                    "production_transport_enabled": True,
                    "production_live_fire_armed": True,
                }
            )
            config["sentinel"] = {"keep": "me"}

            config["operating_mode"] = "LIVE_RECONCILE_ONLY"
            config["trading_actions"] = "RECONCILE_ONLY"
            config["allowed_trading_actions"] = ["RECONCILE_ONLY"]
            config["broker"]["production_live_fire_armed"] = False

            persisted = order_bridge_gate._persist_live_reconcile_only_mode(root, config)

            written = json.loads(
                (root / "config" / "v7_direct_pipeline_config.json").read_text(encoding="utf-8")
            )

        self.assertEqual("LIVE_RECONCILE_ONLY", persisted["operating_mode"])
        self.assertEqual("LIVE_RECONCILE_ONLY", written["operating_mode"])
        self.assertEqual("LIVE", written["trading_mode"])
        self.assertEqual("LIVE", written["execution_mode"])
        self.assertEqual("RECONCILE_ONLY", written["trading_actions"])
        self.assertEqual(["RECONCILE_ONLY"], written["allowed_trading_actions"])
        self.assertEqual("rakuten_rss", written["broker"]["type"])
        self.assertEqual("production", written["broker"]["transport_mode"])
        self.assertTrue(written["broker"]["live_trading_enabled"])
        self.assertTrue(written["broker"]["live_enabled"])
        self.assertTrue(written["broker"]["production_transport_enabled"])
        self.assertFalse(written["broker"]["production_live_fire_armed"])
        self.assertEqual({"keep": "me"}, written["sentinel"])

    def test_dispatch_live_active_unhealthy_persists_reconcile_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            generated = order_bridge_gate._now_jst()
            context = order_bridge_gate.PreorderDispatchContext(
                report={
                    "status": "APPROVED",
                    "blockers": [],
                    "approved_count": 0,
                    "source": "dummy.json",
                },
                generated_at=generated,
                expires_at=generated,
                state_path=root / "state.json",
                config={},
                approved_idempotency_keys=frozenset(),
                report_blockers=(),
                trade_signals_context={"test": "context"},
                executable_orders_by_client_order_id={},
                accepted_orders_by_client_order_id={},
                approved_payloads_by_client_order_id={},
            )
            broker = mock.Mock()
            broker.health_check.return_value = mock.Mock(
                healthy=False,
                message="BROKER_HEALTH_FAILED",
            )
            broker.refresh_pending_orders.return_value = None

            with (
                mock.patch.object(
                    order_bridge_gate,
                    "_activation_config",
                    return_value=("LIVE_ACTIVE", "LIVE", "LIVE", "LIVE_ONLY", None),
                ),
                mock.patch.object(order_bridge_gate, "_parse_state", return_value=(set(), None)),
                mock.patch.object(order_bridge_gate, "_read_json", return_value=({}, None)),
                mock.patch.object(
                    order_bridge_gate,
                    "_trade_signals_context",
                    return_value=({"test": "context"}, ()),
                ),
                mock.patch.object(order_bridge_gate, "create_broker", return_value=broker),
                mock.patch.object(
                    order_bridge_gate,
                    "_resolve_live_dispatch_mode",
                    return_value="LIVE_RECONCILE_ONLY",
                ),
                mock.patch.object(
                    order_bridge_gate,
                    "_persist_live_reconcile_only_mode",
                    side_effect=lambda _root, config: config,
                ) as persist_mock,
            ):
                order_bridge_gate.dispatch_approved_orders(root, context)

        persist_mock.assert_called_once()
        broker.health_check.assert_called_once()
        broker.refresh_pending_orders.assert_called_once()

    def test_timeout(self) -> None:
        backend = MockExcelComBackend()
        transport = ProductionRakutenRssTransport(
            live_trading_enabled=True,
            production_transport_enabled=True,
            armed=True,
            timeout_seconds=0,
            backend=backend,
        )
        order = _live_buy_order("TIMEOUT-001")
        health = RakutenRssTransportHealth(
            connected=True,
            message="Workbook transport READY.",
            transport_source=TRANSPORT_SOURCE_COM_LIVE,
        )

        with mock.patch.object(transport, "health_check", return_value=health):
            transport.submit_order(order, "RSS-TIMEOUT-001")
            updates = transport.poll_order("RSS-TIMEOUT-001")

        self.assertEqual(1, len(updates))
        self.assertEqual(OrderStatus.PENDING, updates[0].status)
        self.assertIn("reconciliation continues", updates[0].message.lower())


class DeployV7RssProductionVbaTest(unittest.TestCase):
    def _make_workbook_path(self, root: Path) -> Path:
        path = root / "runtime" / "v7_rss_production" / "PHOENIX_RSS_PRODUCTION.xlsm"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _build_workbook_components(self, repo_root: Path) -> list[_FakeDeploymentVBComponent]:
        step44_body = deploy_vba._read_source_body(repo_root / "vba" / "PHOENIX_STEP44_Receiver.bas")
        return [
            _FakeDeploymentVBComponent(
                "ThisWorkbook",
                "\n".join(
                    [
                        "Option Explicit",
                        "",
                        "Private Sub Workbook_Open()",
                        "    StartPhoenixStep44ReceiverScheduler",
                        "End Sub",
                        "",
                        "Private Sub Workbook_BeforeClose(Cancel As Boolean)",
                        "    StopPhoenixStep44ReceiverScheduler",
                        "End Sub",
                    ]
                ),
            ),
            _FakeDeploymentVBComponent(
                "PHOENIX_RSS_ORDER_BRIDGE",
                "\n".join(
                    [
                        "Option Explicit",
                        "Option Private Module",
                        "",
                        "Public Sub RunPhoenixRssOrderBridgeConsumer()",
                        "    Exit Sub",
                        "End Sub",
                    ]
                ),
            ),
            _FakeDeploymentVBComponent("PHOENIX_STEP44_Receiver", step44_body),
            _FakeDeploymentVBComponent(
                "HelperModule",
                "\n".join(
                    [
                        "Option Explicit",
                        "",
                        "Public Sub Ping()",
                        "End Sub",
                    ]
                ),
            ),
        ]

    def _sha256_file(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _bootstrap_repo_root(self, root: Path) -> Path:
        repo_root = Path(__file__).resolve().parents[1]
        (root / "runtime" / "v7_rss_production").mkdir(parents=True, exist_ok=True)
        (root / "vba").mkdir(parents=True, exist_ok=True)

        workbook_path = root / prepare_bootstrap.WORKBOOK_RELATIVE
        workbook_path.write_bytes(b"ORIGINAL-WORKBOOK")
        for component_name, relative_path in prepare_bootstrap.SOURCE_RELATIVE.items():
            _ = component_name
            (root / relative_path).write_bytes((repo_root / relative_path).read_bytes())
        return workbook_path

    def _bootstrap_manifest_path(self, root: Path) -> Path:
        return root / prepare_bootstrap.MANIFEST_RELATIVE

    def _bootstrap_backup_path(self, root: Path) -> Path:
        return root / prepare_bootstrap.BACKUP_RELATIVE

    def _deployment_runtime(
        self,
    ) -> tuple[deploy_vba.DeploymentRuntime, mock.Mock, mock.Mock]:
        win32_client = mock.Mock()
        pythoncom = mock.Mock()
        pythoncom.CoInitialize.return_value = None
        pythoncom.CoUninitialize.return_value = None
        return (
            deploy_vba.DeploymentRuntime(win32_client=win32_client, pythoncom=pythoncom),
            win32_client,
            pythoncom,
        )

    def _owner_resolution_patches(
        self,
        hwnds: list[int],
        windows: dict[int, _FakeExcelNativeWindow],
        sessions: dict[int, tuple[int, int]],
        *,
        current_process_session: tuple[int, int] = (4242, 99),
        fail_access_hwnds: set[int] | None = None,
    ) -> tuple[object, object, object, object]:
        fail_access_hwnds = fail_access_hwnds or set()

        def _window_process_session_id(hwnd: int) -> tuple[int, int]:
            return sessions[hwnd]

        def _accessible_object_from_window(win32_client: object, pythoncom: object, hwnd: int) -> object:
            _ = win32_client, pythoncom
            if hwnd in fail_access_hwnds:
                raise deploy_vba.DeploymentPreflightError(f"AccessibleObjectFromWindow failed for HWND {hwnd:#x}")
            return windows[hwnd]

        return (
            mock.patch.object(deploy_vba, "_enum_excel7_window_handles", return_value=hwnds),
            mock.patch.object(deploy_vba, "_window_process_session_id", side_effect=_window_process_session_id),
            mock.patch.object(deploy_vba, "_current_process_session_id", return_value=current_process_session),
            mock.patch.object(deploy_vba, "_accessible_object_from_window", side_effect=_accessible_object_from_window),
        )

    def _diagnostic_win32_patch(self, user32: object, kernel32: object) -> object:
        def _factory(name: str, use_last_error: bool = True) -> object:
            _ = use_last_error
            if name.lower() == "user32":
                return user32
            if name.lower() == "kernel32":
                return kernel32
            raise AssertionError(f"unexpected DLL requested: {name}")

        return mock.patch.object(deploy_vba.ctypes, "WinDLL", side_effect=_factory)

    def test_accessible_object_from_window_objectfromaddress_failure_paths_fail_close(self) -> None:
        pythoncom = mock.Mock()
        pythoncom.IID_IDispatch = object()
        win32_client = mock.Mock()

        def _patch_win32(callback):
            fake_oleacc = _FakeOleaccLibrary(callback)
            return mock.patch.object(
                deploy_vba.ctypes,
                "WinDLL",
                side_effect=lambda name, use_last_error=True: fake_oleacc,
            )

        def _set_result(result_ptr: object, value: int) -> None:
            ctypes.cast(result_ptr, ctypes.POINTER(ctypes.c_void_p)).contents.value = value

        with self.subTest("dispatch_success"):
            raw_dispatch = object()
            wrapped_window = _FakeExcelNativeWindow(
                _FakeDeploymentExcelApplication([], hwnd=0x1234),
                0x1234,
            )

            def _callback_success(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            pythoncom.ObjectFromAddress.return_value = raw_dispatch
            win32_client.Dispatch.return_value = wrapped_window
            with _patch_win32(_callback_success):
                native_window = deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            self.assertIs(native_window, wrapped_window)
            pythoncom.ObjectFromAddress.assert_called_once_with(0x1234, pythoncom.IID_IDispatch)
            win32_client.Dispatch.assert_called_once_with(raw_dispatch)

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()

        with self.subTest("hresult_nonzero"):
            def _callback_fail(*args, **kwargs):
                _ = args, kwargs
                return 1

            with _patch_win32(_callback_fail):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_not_called()
            win32_client.Dispatch.assert_not_called()

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("null_native_object"):
            def _callback_null(*args, **kwargs):
                _ = args, kwargs
                return 0

            with _patch_win32(_callback_null):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_not_called()
            win32_client.Dispatch.assert_not_called()

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("objectfromaddress_raises"):
            def _callback_address(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            pythoncom.ObjectFromAddress.side_effect = ReferenceError("stale proxy")
            with _patch_win32(_callback_address):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_called_once()
            win32_client.Dispatch.assert_not_called()

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("dispatch_raises"):
            def _callback_dispatch(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            raw_dispatch = object()
            pythoncom.ObjectFromAddress.return_value = raw_dispatch
            win32_client.Dispatch.side_effect = ReferenceError("stale proxy")
            with _patch_win32(_callback_dispatch):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_called_once_with(0x1234, pythoncom.IID_IDispatch)
            win32_client.Dispatch.assert_called_once_with(raw_dispatch)

        pythoncom.ObjectFromAddress.reset_mock()
        win32_client.Dispatch.reset_mock()
        pythoncom.ObjectFromAddress.side_effect = None
        win32_client.Dispatch.side_effect = None

        with self.subTest("dispatch_returns_none"):
            def _callback_none(*args, **kwargs):
                _set_result(args[3], 0x1234)
                return 0

            raw_dispatch = object()
            pythoncom.ObjectFromAddress.return_value = raw_dispatch
            win32_client.Dispatch.return_value = None
            with _patch_win32(_callback_none):
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._accessible_object_from_window(win32_client, pythoncom, 0x1234)
            pythoncom.ObjectFromAddress.assert_called_once_with(0x1234, pythoncom.IID_IDispatch)
            win32_client.Dispatch.assert_called_once_with(raw_dispatch)

    def test_accessible_object_owner_resolution_invalid_native_object_and_proxy_fail_close(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)
            runtime, _, pythoncom = self._deployment_runtime()

            class _ProxyExpiredNativeWindow:
                @property
                def Application(self) -> object:
                    raise ReferenceError("native object expired")

            class _ProxyExpiredWorkbooks:
                def __iter__(self):
                    raise ReferenceError("workbooks proxy expired")

                @property
                def Count(self) -> int:
                    raise ReferenceError("workbooks proxy expired")

                def Item(self, index: int) -> object:
                    raise ReferenceError("workbooks proxy expired")

            def _assert_no_write_and_no_backup(excel: _FakeDeploymentExcelApplication, workbook: _FakeDeploymentWorkbook) -> None:
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], workbook.close_calls)
                self.assertEqual(0, workbook.save_calls)
                self.assertEqual([], excel.run_calls)
                self.assertEqual(0, excel.quit_calls)

            with self.subTest("null_native_object"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=901)
                patches = self._owner_resolution_patches(
                    [901],
                    {901: None},
                    {901: (9101, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("missing_application"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=902)
                patches = self._owner_resolution_patches(
                    [902],
                    {902: object()},
                    {902: (9102, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("workbooks_missing"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=903)
                patches = self._owner_resolution_patches(
                    [903],
                    {903: _FakeExcelNativeWindow(object(), 903)},
                    {903: (9103, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("application_proxy_expired"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=904)
                patches = self._owner_resolution_patches(
                    [904],
                    {904: _ProxyExpiredNativeWindow()},
                    {904: (9104, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("workbooks_proxy_expired"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=905)

                class _ApplicationWithBrokenWorkbooks:
                    @property
                    def Workbooks(self) -> object:
                        return _ProxyExpiredWorkbooks()

                native_window = type("_NativeWindow", (), {"Application": _ApplicationWithBrokenWorkbooks(), "Hwnd": 905})()
                patches = self._owner_resolution_patches(
                    [905],
                    {905: native_window},
                    {905: (9105, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                _assert_no_write_and_no_backup(excel, workbook)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

    def test_successful_targeted_deployment_updates_only_target_modules_and_preserves_step44(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            sibling_path = workbook_path.with_name("SIBLING.xlsm")
            sibling_path.write_bytes(b"SIBLING-WORKBOOK")
            sibling = _FakeDeploymentWorkbook(sibling_path, self._build_workbook_components(repo_root))
            other_path = workbook_path.with_name("OTHER.xlsm")
            other_path.write_bytes(b"OTHER-WORKBOOK")
            other = _FakeDeploymentWorkbook(other_path, self._build_workbook_components(repo_root))

            primary_excel = _FakeDeploymentExcelApplication([workbook, sibling], hwnd=777)
            secondary_excel = _FakeDeploymentExcelApplication([other], hwnd=888)
            runtime, _, pythoncom = self._deployment_runtime()
            before_snapshot = deploy_vba._snapshot_vbproject(workbook.VBProject)
            original_hash = self._sha256_file(workbook_path)
            real_apply = deploy_vba._apply_target_module_updates

            def _apply_spy(vbproject: object, source_bodies: dict[str, str]) -> None:
                backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))
                self.assertEqual(1, len(backups))
                self.assertEqual(original_hash, self._sha256_file(backups[0]))
                real_apply(vbproject, source_bodies)

            hwnds = [101, 102, 201]
            windows = {
                101: _FakeExcelNativeWindow(primary_excel, 101),
                102: _FakeExcelNativeWindow(primary_excel, 102),
                201: _FakeExcelNativeWindow(secondary_excel, 201),
            }
            sessions = {
                101: (5001, 11),
                102: (5001, 11),
                201: (5002, 11),
            }
            patches = self._owner_resolution_patches(hwnds, windows, sessions, current_process_session=(1234, 11))
            with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
                deploy_vba,
                "_apply_target_module_updates",
                side_effect=_apply_spy,
            ):
                report = deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
            after_snapshot = deploy_vba._snapshot_vbproject(workbook.VBProject)
            source_bodies = deploy_vba._read_source_bodies(repo_root)
            backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))

            self.assertTrue(report.deployed)
            self.assertEqual(workbook_path, report.workbook_path)
            self.assertEqual(1, len(backups))
            self.assertEqual(original_hash, self._sha256_file(report.backup_path))
            self.assertEqual({"PHOENIX_RSS_ORDER_BRIDGE", "ThisWorkbook"}, set(report.changed_modules))
            self.assertEqual({"PHOENIX_STEP44_Receiver", "HelperModule"}, set(report.preserved_modules))
            self.assertIn("step44_hooks_preserved", report.verification)
            self.assertIn("dry_run_safe", report.verification)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], primary_excel.run_calls)
            self.assertEqual([], secondary_excel.run_calls)
            self.assertEqual(1, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual(0, primary_excel.quit_calls)
            self.assertEqual(0, secondary_excel.quit_calls)
            self.assertTrue(primary_excel.EnableEvents)
            self.assertTrue(primary_excel.DisplayAlerts)
            self.assertIsNone(primary_excel.AutomationSecurity)
            self.assertTrue(secondary_excel.EnableEvents)
            self.assertTrue(secondary_excel.DisplayAlerts)
            self.assertIsNone(secondary_excel.AutomationSecurity)
            self.assertEqual(source_bodies["PHOENIX_RSS_ORDER_BRIDGE"], after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertEqual(source_bodies["ThisWorkbook"], after_snapshot["ThisWorkbook"])
            self.assertEqual(before_snapshot["PHOENIX_STEP44_Receiver"], after_snapshot["PHOENIX_STEP44_Receiver"])
            self.assertEqual(before_snapshot["HelperModule"], after_snapshot["HelperModule"])
            self.assertIn('Private Sub Step44WriteTransportHeartbeat(ByVal heartbeatText As String)', after_snapshot["PHOENIX_STEP44_Receiver"])
            self.assertIn('ThisWorkbook.Worksheets("PHOENIX_RSS_TRANSPORT").Range("J6").Value2 = heartbeatText', after_snapshot["PHOENIX_STEP44_Receiver"])
            self.assertLess(
                after_snapshot["PHOENIX_STEP44_Receiver"].index('currentStage = "WRITE_HEARTBEAT"'),
                after_snapshot["PHOENIX_STEP44_Receiver"].index('currentStage = "ENSURE_DIRECTORIES"'),
            )
            self.assertIn(
                'Private Const STEP44_CANONICAL_FALLBACK_ROOT As String = "C:\\Users\\ashtc\\OneDrive\\デスクトップ\\ちちのフォルダ\\PHOENIX"',
                after_snapshot["PHOENIX_STEP44_Receiver"],
            )
            self.assertIn(
                "If RepositoryLooksValid(STEP44_CANONICAL_FALLBACK_ROOT) Then",
                after_snapshot["PHOENIX_STEP44_Receiver"],
            )
            self.assertIn(
                'Err.Raise vbObjectError + 4431, CONTRACT_ID, "Unable to resolve the PHOENIX repository root"',
                after_snapshot["PHOENIX_STEP44_Receiver"],
            )
            self.assertEqual(0, sibling.save_calls)
            self.assertEqual([], sibling.close_calls)
            self.assertEqual(0, other.save_calls)
            self.assertEqual([], other.close_calls)
            self.assertIn("Workbook_Open", after_snapshot["ThisWorkbook"])
            self.assertIn("Workbook_BeforeClose", after_snapshot["ThisWorkbook"])
            self.assertIn("StartPhoenixRssOrderBridgeScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("StopPhoenixRssOrderBridgeScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("StartPhoenixStep44ReceiverScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("StopPhoenixStep44ReceiverScheduler", after_snapshot["ThisWorkbook"])
            self.assertIn("RunPhoenixRssOrderBridgeConsumer", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Application.OnTime", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Schedule:=True", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Schedule:=False", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertIn("Private Const OBR_BRIDGE_ARMED As Boolean = False", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertNotIn("RssStockOrder_V(", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertNotIn("RssCancelOrder_V(", after_snapshot["PHOENIX_RSS_ORDER_BRIDGE"])
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], primary_excel.run_calls)
            self.assertEqual(1, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual(0, primary_excel.quit_calls)
            self.assertTrue(primary_excel.EnableEvents)
            self.assertTrue(primary_excel.DisplayAlerts)
            self.assertIsNone(primary_excel.AutomationSecurity)
            self.assertEqual(0, secondary_excel.quit_calls)
            self.assertTrue(secondary_excel.EnableEvents)
            self.assertTrue(secondary_excel.DisplayAlerts)
            self.assertIsNone(secondary_excel.AutomationSecurity)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_owner_resolution_zero_multiple_and_fullname_fail_close(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            runtime, _, pythoncom = self._deployment_runtime()

            with self.subTest("zero_owner"):
                zero_workbook = _FakeDeploymentWorkbook(
                    workbook_path.with_name("OTHER_ZERO.xlsm"),
                    self._build_workbook_components(repo_root),
                )
                zero_excel = _FakeDeploymentExcelApplication([zero_workbook], hwnd=111)
                patches = self._owner_resolution_patches(
                    [101],
                    {101: _FakeExcelNativeWindow(zero_excel, 101)},
                    {101: (6001, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], zero_workbook.close_calls)
                self.assertEqual([], zero_excel.run_calls)
                self.assertEqual(0, zero_workbook.save_calls)
                self.assertEqual(0, zero_excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("multiple_owners"):
                target_a = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                target_b = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel_a = _FakeDeploymentExcelApplication([target_a], hwnd=222)
                excel_b = _FakeDeploymentExcelApplication([target_b], hwnd=333)
                patches = self._owner_resolution_patches(
                    [201, 202],
                    {
                        201: _FakeExcelNativeWindow(excel_a, 201),
                        202: _FakeExcelNativeWindow(excel_b, 202),
                    },
                    {201: (7001, 11), 202: (7002, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], target_a.close_calls)
                self.assertEqual([], target_b.close_calls)
                self.assertEqual([], excel_a.run_calls)
                self.assertEqual([], excel_b.run_calls)
                self.assertEqual(0, target_a.save_calls)
                self.assertEqual(0, target_b.save_calls)
                self.assertEqual(0, excel_a.quit_calls)
                self.assertEqual(0, excel_b.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("fullname_mismatch"):
                mismatch_workbook = _FakeDeploymentWorkbook(
                    workbook_path.with_name("PHOENIX_RSS_PRODUCTION.mismatch.xlsm"),
                    self._build_workbook_components(repo_root),
                )
                mismatch_excel = _FakeDeploymentExcelApplication([mismatch_workbook], hwnd=444)
                patches = self._owner_resolution_patches(
                    [301],
                    {301: _FakeExcelNativeWindow(mismatch_excel, 301)},
                    {301: (8001, 11)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], mismatch_workbook.close_calls)
                self.assertEqual([], mismatch_excel.run_calls)
                self.assertEqual(0, mismatch_workbook.save_calls)
                self.assertEqual(0, mismatch_excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

    def test_accessible_object_and_session_mismatch_fail_close(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            runtime, _, pythoncom = self._deployment_runtime()

            with self.subTest("accessible_object_failure"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=222)
                patches = self._owner_resolution_patches(
                    [201],
                    {201: _FakeExcelNativeWindow(excel, 201)},
                    {201: (6001, 11)},
                    current_process_session=(1234, 11),
                    fail_access_hwnds={201},
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], workbook.close_calls)
                self.assertEqual([], excel.run_calls)
                self.assertEqual(0, workbook.save_calls)
                self.assertEqual(0, excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

            workbook_path.write_bytes(original_bytes)
            pythoncom.CoInitialize.reset_mock()
            pythoncom.CoUninitialize.reset_mock()

            with self.subTest("session_mismatch"):
                workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
                excel = _FakeDeploymentExcelApplication([workbook], hwnd=333)
                patches = self._owner_resolution_patches(
                    [301],
                    {301: _FakeExcelNativeWindow(excel, 301)},
                    {301: (6002, 22)},
                    current_process_session=(1234, 11),
                )
                with patches[0], patches[1], patches[2], patches[3]:
                    with self.assertRaises(deploy_vba.DeploymentPreflightError):
                        deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)
                self.assertEqual(original_bytes, workbook_path.read_bytes())
                self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
                self.assertEqual([], workbook.close_calls)
                self.assertEqual([], excel.run_calls)
                self.assertEqual(0, workbook.save_calls)
                self.assertEqual(0, excel.quit_calls)
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_called_once()

    def test_unsaved_workbook_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(
                workbook_path,
                self._build_workbook_components(repo_root),
                saved=False,
            )
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=444)
            runtime, _, pythoncom = self._deployment_runtime()
            patches = self._owner_resolution_patches(
                [401],
                {401: _FakeExcelNativeWindow(excel, 401)},
                {401: (9001, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_readonly_workbook_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(
                workbook_path,
                self._build_workbook_components(repo_root),
                read_only=True,
            )
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=555)
            runtime, _, pythoncom = self._deployment_runtime()
            patches = self._owner_resolution_patches(
                [501],
                {501: _FakeExcelNativeWindow(excel, 501)},
                {501: (9002, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_vbproject_access_denied_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(
                workbook_path,
                self._build_workbook_components(repo_root),
                vbproject_error=PermissionError("VBProject access denied"),
            )
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=556)
            runtime, _, pythoncom = self._deployment_runtime()
            patches = self._owner_resolution_patches(
                [601],
                {601: _FakeExcelNativeWindow(excel, 601)},
                {601: (9003, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_step44_scheduler_stop_failure_fails_without_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            excel = _FakeDeploymentExcelApplication(
                [workbook],
                hwnd=666,
                run_errors={"StopPhoenixStep44ReceiverScheduler": RuntimeError("stop failed")},
            )
            runtime, _, pythoncom = self._deployment_runtime()
            original_enable_events = excel.EnableEvents
            original_display_alerts = excel.DisplayAlerts
            original_automation_security = excel.AutomationSecurity

            patches = self._owner_resolution_patches(
                [701],
                {701: _FakeExcelNativeWindow(excel, 701)},
                {701: (9004, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(deploy_vba.DeploymentPreflightError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([], list(workbook_path.parent.glob("*.deploy_backup_*.xlsm")))
            self.assertEqual(original_enable_events, excel.EnableEvents)
            self.assertEqual(original_display_alerts, excel.DisplayAlerts)
            self.assertEqual(original_automation_security, excel.AutomationSecurity)
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_post_save_verification_failure_rolls_back_and_restores_original_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=888)
            runtime, _, pythoncom = self._deployment_runtime()
            original_hash = self._sha256_file(workbook_path)

            patches = self._owner_resolution_patches(
                [801],
                {801: _FakeExcelNativeWindow(excel, 801)},
                {801: (9005, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
                deploy_vba,
                "_verify_deployment_state",
                side_effect=deploy_vba.DeploymentVerificationError("forced verification failure"),
            ):
                with self.assertRaises(deploy_vba.DeploymentVerificationError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))
            self.assertEqual(1, len(backups))
            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual(original_hash, self._sha256_file(workbook_path))
            self.assertEqual(1, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()

    def test_deployment_failure_rolls_back_and_restores_original_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(__file__).resolve().parents[1]
            workbook_path = self._make_workbook_path(Path(temporary_directory))
            original_bytes = b"ORIGINAL-WORKBOOK"
            workbook_path.write_bytes(original_bytes)

            workbook = _FakeDeploymentWorkbook(workbook_path, self._build_workbook_components(repo_root))
            excel = _FakeDeploymentExcelApplication([workbook], hwnd=999)
            runtime, _, pythoncom = self._deployment_runtime()
            original_hash = self._sha256_file(workbook_path)

            patches = self._owner_resolution_patches(
                [901],
                {901: _FakeExcelNativeWindow(excel, 901)},
                {901: (9006, 11)},
                current_process_session=(1234, 11),
            )
            with patches[0], patches[1], patches[2], patches[3], mock.patch.object(
                deploy_vba,
                "_apply_target_module_updates",
                side_effect=deploy_vba.DeploymentError("forced deployment failure"),
            ):
                with self.assertRaises(deploy_vba.DeploymentError):
                    deploy_vba._deploy_vba_to_path(workbook_path, source_root=repo_root, runtime=runtime)

            backups = list(workbook_path.parent.glob("*.deploy_backup_*.xlsm"))
            self.assertEqual(1, len(backups))
            self.assertEqual(original_bytes, workbook_path.read_bytes())
            self.assertEqual(original_hash, self._sha256_file(workbook_path))
            self.assertEqual(0, workbook.save_calls)
            self.assertEqual([False], workbook.close_calls)
            self.assertEqual([f"'{workbook.Name}'!StopPhoenixStep44ReceiverScheduler"], excel.run_calls)
            self.assertEqual(0, excel.quit_calls)
            pythoncom.CoInitialize.assert_called_once()
            pythoncom.CoUninitialize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
import json


## FILE: vba/PHOENIX_RSS_ORDER_BRIDGE.bas

Attribute VB_Name = "PHOENIX_RSS_ORDER_BRIDGE"
Option Explicit
Option Private Module

#If VBA7 Then
    Private Declare PtrSafe Function MoveFileExW Lib "kernel32" ( _
        ByVal lpExistingFileName As LongPtr, _
        ByVal lpNewFileName As LongPtr, _
        ByVal dwFlags As Long) As Long
    Private Declare PtrSafe Function WideCharToMultiByte Lib "kernel32" ( _
        ByVal CodePage As Long, _
        ByVal dwFlags As Long, _
        ByVal lpWideCharStr As LongPtr, _
        ByVal cchWideChar As Long, _
        ByVal lpMultiByteStr As LongPtr, _
        ByVal cbMultiByte As Long, _
        ByVal lpDefaultChar As LongPtr, _
        ByVal lpUsedDefaultChar As LongPtr) As Long
    Private Declare PtrSafe Function CryptAcquireContextW Lib "advapi32.dll" ( _
        ByRef phProv As LongPtr, _
        ByVal pszContainer As LongPtr, _
        ByVal pszProvider As LongPtr, _
        ByVal dwProvType As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare PtrSafe Function CryptCreateHash Lib "advapi32.dll" ( _
        ByVal hProv As LongPtr, _
        ByVal Algid As Long, _
        ByVal hKey As LongPtr, _
        ByVal dwFlags As Long, _
        ByRef phHash As LongPtr) As Long
    Private Declare PtrSafe Function CryptHashData Lib "advapi32.dll" ( _
        ByVal hHash As LongPtr, _
        ByRef pbData As Any, _
        ByVal dwDataLen As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare PtrSafe Function CryptGetHashParam Lib "advapi32.dll" ( _
        ByVal hHash As LongPtr, _
        ByVal dwParam As Long, _
        ByRef pbData As Any, _
        ByRef pdwDataLen As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare PtrSafe Function CryptDestroyHash Lib "advapi32.dll" ( _
        ByVal hHash As LongPtr) As Long
    Private Declare PtrSafe Function CryptReleaseContext Lib "advapi32.dll" ( _
        ByVal hProv As LongPtr, _
        ByVal dwFlags As Long) As Long
    Private Declare PtrSafe Function CreateFileW Lib "kernel32" ( _
        ByVal lpFileName As LongPtr, _
        ByVal dwDesiredAccess As Long, _
        ByVal dwShareMode As Long, _
        ByVal lpSecurityAttributes As LongPtr, _
        ByVal dwCreationDisposition As Long, _
        ByVal dwFlagsAndAttributes As Long, _
        ByVal hTemplateFile As LongPtr) As LongPtr
    Private Declare PtrSafe Function WriteFile Lib "kernel32" ( _
        ByVal hFile As LongPtr, _
        ByRef lpBuffer As Any, _
        ByVal nNumberOfBytesToWrite As Long, _
        ByRef lpNumberOfBytesWritten As Long, _
        ByVal lpOverlapped As LongPtr) As Long
    Private Declare PtrSafe Function CloseHandle Lib "kernel32" ( _
        ByVal hObject As LongPtr) As Long
    Private Declare PtrSafe Function GetLastError Lib "kernel32" () As Long
#Else
    Private Declare Function MoveFileExW Lib "kernel32" ( _
        ByVal lpExistingFileName As Long, _
        ByVal lpNewFileName As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare Function WideCharToMultiByte Lib "kernel32" ( _
        ByVal CodePage As Long, _
        ByVal dwFlags As Long, _
        ByVal lpWideCharStr As Long, _
        ByVal cchWideChar As Long, _
        ByVal lpMultiByteStr As Long, _
        ByVal cbMultiByte As Long, _
        ByVal lpDefaultChar As Long, _
        ByVal lpUsedDefaultChar As Long) As Long
    Private Declare Function CryptAcquireContextW Lib "advapi32.dll" ( _
        ByRef phProv As Long, _
        ByVal pszContainer As Long, _
        ByVal pszProvider As Long, _
        ByVal dwProvType As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare Function CryptCreateHash Lib "advapi32.dll" ( _
        ByVal hProv As Long, _
        ByVal Algid As Long, _
        ByVal hKey As Long, _
        ByVal dwFlags As Long, _
        ByRef phHash As Long) As Long
    Private Declare Function CryptHashData Lib "advapi32.dll" ( _
        ByVal hHash As Long, _
        ByRef pbData As Any, _
        ByVal dwDataLen As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare Function CryptGetHashParam Lib "advapi32.dll" ( _
        ByVal hHash As Long, _
        ByVal dwParam As Long, _
        ByRef pbData As Any, _
        ByRef pdwDataLen As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare Function CryptDestroyHash Lib "advapi32.dll" ( _
        ByVal hHash As Long) As Long
    Private Declare Function CryptReleaseContext Lib "advapi32.dll" ( _
        ByVal hProv As Long, _
        ByVal dwFlags As Long) As Long
    Private Declare Function CreateFileW Lib "kernel32" ( _
        ByVal lpFileName As Long, _
        ByVal dwDesiredAccess As Long, _
        ByVal dwShareMode As Long, _
        ByVal lpSecurityAttributes As Long, _
        ByVal dwCreationDisposition As Long, _
        ByVal dwFlagsAndAttributes As Long, _
        ByVal hTemplateFile As Long) As Long
    Private Declare Function WriteFile Lib "kernel32" ( _
        ByVal hFile As Long, _
        ByRef lpBuffer As Any, _
        ByVal nNumberOfBytesToWrite As Long, _
        ByRef lpNumberOfBytesWritten As Long, _
        ByVal lpOverlapped As Long) As Long
    Private Declare Function CloseHandle Lib "kernel32" ( _
        ByVal hObject As Long) As Long
    Private Declare Function GetLastError Lib "kernel32" () As Long
#End If

Private Const OBR_MODULE_NAME As String = "PHOENIX_RSS_ORDER_BRIDGE"
Private Const OBR_BRIDGE_ARMED As Boolean = False
Private Const OBR_BRIDGE_ROOT_RELATIVE As String = "runtime/v7_rss_production/order_bridge"
Private Const OBR_ONEDRIVE_WEB_PREFIX As String = "https://d.docs.live.net/"
Private Const OBR_ONTIME_INTERVAL_SECONDS As Long = 30
Private Const OBR_PENDING_RELATIVE As String = "outbox/pending"
Private Const OBR_PROCESSING_RELATIVE As String = "outbox/processing"
Private Const OBR_PROCESSED_RELATIVE As String = "outbox/processed"
Private Const OBR_FAILED_RELATIVE As String = "outbox/failed"
Private Const OBR_INBOX_RELATIVE As String = "inbox"
Private Const OBR_OBSERVABILITY_RELATIVE As String = "PHOENIX_RSS_ORDER_BRIDGE_EVENTS.csv"
Private Const OBR_OBSERVABILITY_EVENT_SCHEDULER_SCHEDULED As String = "SCHEDULER_SCHEDULED"
Private Const OBR_OBSERVABILITY_EVENT_CONSUMER_ENTERED As String = "CONSUMER_ENTERED"
Private Const OBR_OBSERVABILITY_EVENT_READY_FALSE As String = "READY_FALSE"
Private Const OBR_OBSERVABILITY_EVENT_READY_TRUE As String = "READY_TRUE"
Private Const OBR_OBSERVABILITY_EVENT_REQUEST_STARTED As String = "REQUEST_STARTED"
Private Const OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED As String = "REQUEST_ACCEPTED"
Private Const OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED As String = "REQUEST_REJECTED"
Private Const OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR As String = "OBSERVABILITY_ERROR"
Private Const OBR_OBSERVABILITY_READY_TRUE As String = "TRUE"
Private Const OBR_OBSERVABILITY_READY_FALSE As String = "FALSE"
Private Const OBR_TRANSPORT_SHEET_NAME As String = "PHOENIX_RSS_TRANSPORT"
Private Const OBR_HEARTBEAT_MAX_AGE_SECONDS As Long = 90
Private Const OBR_READY_ERROR_MESSAGE As String = "heartbeat/rss/add-in/order transport not ready"
Private Const OBR_READY_BRIDGE_MESSAGE As String = "bridge not ready"
Private Const OBR_DUPLICATE_MESSAGE As String = "duplicate request"
Private Const OBR_REQUEST_READ_FAILED_MESSAGE As String = "request read failed"
Private Const OBR_SUBMIT_ACCEPTED_MESSAGE As String = "submit accepted"
Private Const OBR_CANCEL_ACCEPTED_MESSAGE As String = "cancel accepted"
Private Const OBR_LIVE_REQUEST_FLAGS_INSUFFICIENT_ERROR_CODE As String = "LIVE_REQUEST_FLAGS_INSUFFICIENT"
Private Const OBR_LIVE_REQUEST_REQUIRES_BRIDGE_ARMED_ERROR_CODE As String = "LIVE_REQUEST_REQUIRES_BRIDGE_ARMED"
Private Const OBR_LIVE_FIRE_CALL_CONTRACT_NOT_PROVEN_ERROR_CODE As String = "LIVE_FIRE_CALL_CONTRACT_NOT_PROVEN"
Private Const OBR_DISCONNECTED_STATUS As String = "DISCONNECTED"
Private Const OBR_DUPLICATE_STATUS As String = "DUPLICATE"
Private Const OBR_CORRUPT_STATUS As String = "CORRUPT"
Private Const OBR_UTF8_CODE_PAGE As Long = 65001
Private Const OBR_RSA_AES_PROV_TYPE As Long = 24
Private Const OBR_CRYPT_VERIFYCONTEXT As Long = &HF0000000
Private Const OBR_CALG_SHA_256 As Long = &H800C&
Private Const OBR_HP_HASHVAL As Long = &H2
Private Const OBR_FILE_APPEND_DATA As Long = &H4
Private Const OBR_FILE_SHARE_READ As Long = &H1
Private Const OBR_FILE_SHARE_WRITE As Long = &H2
Private Const OBR_FILE_SHARE_DELETE As Long = &H4
Private Const OBR_OPEN_ALWAYS As Long = 4
Private Const OBR_FILE_ATTRIBUTE_NORMAL As Long = &H80
Private Const OBR_ERROR_ALREADY_EXISTS As Long = 183
Private Const OBR_INVALID_HANDLE_VALUE As LongPtr = -1

Private Type OBRBridgeReadyState
    ExcelAlive As Boolean
    RssConnected As Boolean
    AddInReady As Boolean
    OrderTransportReady As Boolean
    HeartbeatAgeSeconds As Long
    Ready As Boolean
    Reason As String
End Type

Private Const OBR_REQ_SCHEMA_VERSION As Long = 0
Private Const OBR_REQ_REQUEST_ID As Long = 1
Private Const OBR_REQ_REQUEST_KIND As Long = 2
Private Const OBR_REQ_BROKER_ORDER_ID As Long = 3
Private Const OBR_REQ_CLIENT_ORDER_ID As Long = 4
Private Const OBR_REQ_STRATEGY_NAME As Long = 5
Private Const OBR_REQ_TICKER As Long = 6
Private Const OBR_REQ_SIDE As Long = 7
Private Const OBR_REQ_QUANTITY As Long = 8
Private Const OBR_REQ_ORDER_TYPE As Long = 9
Private Const OBR_REQ_LIMIT_PRICE As Long = 10
Private Const OBR_REQ_TARGET_PRICE As Long = 11
Private Const OBR_REQ_STOP_PRICE As Long = 12
Private Const OBR_REQ_STOP_TRIGGER_PRICE As Long = 13
Private Const OBR_REQ_ORDER_CATEGORY As Long = 14
Private Const OBR_REQ_EXECUTION_CONDITION As Long = 15
Private Const OBR_REQ_EXPIRATION As Long = 16
Private Const OBR_REQ_TRIGGER_CONDITION As Long = 17
Private Const OBR_REQ_POST_TRIGGER_ORDER_TYPE As Long = 18
Private Const OBR_REQ_LIVE_TRADING_ENABLED As Long = 19
Private Const OBR_REQ_PRODUCTION_TRANSPORT_ENABLED As Long = 20
Private Const OBR_REQ_ARMED As Long = 21
Private Const OBR_REQ_SUBMITTED_AT As Long = 22
Private Const OBR_REQ_TIMEOUT_SECONDS As Long = 23
Private Const OBR_REQ_MACRO_NAME As Long = 24
Private Const OBR_REQ_MESSAGE As Long = 25
Private Const OBR_REQ_BRIDGE_STATUS As Long = 26
Private Const OBR_REQ_PAYLOAD_SHA256 As Long = 27
Private Const OBR_REQ_CHECKSUM As Long = 28

Private Const OBR_REC_SCHEMA_VERSION As Long = 0
Private Const OBR_REC_REQUEST_ID As Long = 1
Private Const OBR_REC_REQUEST_KIND As Long = 2
Private Const OBR_REC_BROKER_ORDER_ID As Long = 3
Private Const OBR_REC_CLIENT_ORDER_ID As Long = 4
Private Const OBR_REC_BRIDGE_STATUS As Long = 5
Private Const OBR_REC_RESULT As Long = 6
Private Const OBR_REC_RSS_ORDER_STATUS As Long = 7
Private Const OBR_REC_RSS_ORDER_NUMBER As Long = 8
Private Const OBR_REC_TICKER As Long = 9
Private Const OBR_REC_QUANTITY As Long = 10
Private Const OBR_REC_TARGET_PRICE As Long = 11
Private Const OBR_REC_STOP_PRICE As Long = 12
Private Const OBR_REC_EXPIRATION As Long = 13
Private Const OBR_REC_TIMESTAMP As Long = 14
Private Const OBR_REC_MESSAGE As Long = 15
Private Const OBR_REC_ERROR_CODE As Long = 16
Private Const OBR_REC_ERROR_MESSAGE As Long = 17
Private Const OBR_REC_FILL_QUANTITY As Long = 18
Private Const OBR_REC_FILL_PRICE As Long = 19
Private Const OBR_REC_ORDERS_SUBMITTED As Long = 20
Private Const OBR_REC_REQUEST_CHECKSUM As Long = 21
Private Const OBR_REC_CHECKSUM As Long = 22

Private gOrderBridgeSchedulerArmed As Boolean
Private gOrderBridgeNextRunAt As Date
Private gOrderBridgeNextRunScheduled As Boolean
Private gOrderBridgeConsumerRunning As Boolean

Private Function OBR_ValidStatusText() As String
    OBR_ValidStatusText = ChrW$(&H6709) & ChrW$(&H52B9)
End Function

Private Function OBR_InvalidStatusText() As String
    OBR_InvalidStatusText = ChrW$(&H7121) & ChrW$(&H52B9)
End Function

Public Sub StartPhoenixRssOrderBridgeScheduler()
    If Not OBR_StartScheduler() Then
        Err.Raise vbObjectError + 7820, OBR_MODULE_NAME, "Order bridge scheduler startup failed"
    End If
End Sub

Public Sub StopPhoenixRssOrderBridgeScheduler()
    OBR_StopScheduler
End Sub

Private Function OBR_OrderBridgeOnTimeProcedureName() As String
    OBR_OrderBridgeOnTimeProcedureName = "'" & ThisWorkbook.Name & "'!RunPhoenixRssOrderBridgeConsumer"
End Function

Private Function OBR_StartScheduler() As Boolean
    If OBR_SchedulerLifecycleActive() Then
        gOrderBridgeSchedulerArmed = True
        OBR_StartScheduler = True
        Exit Function
    End If
    gOrderBridgeSchedulerArmed = True
    RunPhoenixRssOrderBridgeConsumer
    OBR_StartScheduler = OBR_SchedulerLifecycleActive()
    If Not OBR_StartScheduler Then
        gOrderBridgeSchedulerArmed = False
    End If
End Function

Private Function OBR_SchedulerLifecycleActive() As Boolean
    OBR_SchedulerLifecycleActive = gOrderBridgeNextRunScheduled Or gOrderBridgeConsumerRunning
End Function

Private Sub OBR_StopScheduler()
    gOrderBridgeSchedulerArmed = False
    OBR_CancelScheduledRun
End Sub

Private Sub OBR_ScheduleNextRun()
    Dim rootPath As String
    Dim bridgeRoot As String
    Dim onTimeErrorNumber As Long

    If Not gOrderBridgeSchedulerArmed Then Exit Sub

    OBR_CancelScheduledRun
    gOrderBridgeNextRunAt = DateAdd("s", OBR_ONTIME_INTERVAL_SECONDS, Now)

    On Error Resume Next
    Err.Clear
    Application.OnTime EarliestTime:=gOrderBridgeNextRunAt, Procedure:=OBR_OrderBridgeOnTimeProcedureName(), Schedule:=True
    onTimeErrorNumber = Err.Number
    Err.Clear
    On Error GoTo 0

    If onTimeErrorNumber = 0 Then
        On Error Resume Next
        rootPath = OBR_FindRepositoryRoot(ThisWorkbook.Path)
        If Err.Number = 0 Then
            bridgeRoot = OBR_BridgePath(rootPath, OBR_BRIDGE_ROOT_RELATIVE)
            OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_SCHEDULER_SCHEDULED, "", "", "next run scheduled"
        End If
        Err.Clear
        On Error GoTo 0
        gOrderBridgeNextRunScheduled = True
        Exit Sub
    End If

    gOrderBridgeNextRunAt = 0
    gOrderBridgeNextRunScheduled = False
    gOrderBridgeSchedulerArmed = False

    On Error Resume Next
    rootPath = OBR_FindRepositoryRoot(ThisWorkbook.Path)
    If Err.Number = 0 Then
        bridgeRoot = OBR_BridgePath(rootPath, OBR_BRIDGE_ROOT_RELATIVE)
        OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, "", "", "Application.OnTime failed"
    End If
    Err.Clear
    On Error GoTo 0
End Sub

Private Sub OBR_CancelScheduledRun()
    If Not gOrderBridgeNextRunScheduled Then Exit Sub

    On Error Resume Next
    Application.OnTime EarliestTime:=gOrderBridgeNextRunAt, Procedure:=OBR_OrderBridgeOnTimeProcedureName(), Schedule:=False
    On Error GoTo 0
    gOrderBridgeNextRunAt = 0
    gOrderBridgeNextRunScheduled = False
End Sub

Public Sub RunPhoenixRssOrderBridgeConsumer()
    Dim rootPath As String
    Dim bridgeRoot As String
    Dim readyState As OBRBridgeReadyState

    On Error GoTo CleanFail
    rootPath = OBR_FindRepositoryRoot(ThisWorkbook.Path)
    bridgeRoot = OBR_BridgePath(rootPath, OBR_BRIDGE_ROOT_RELATIVE)
    OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_CONSUMER_ENTERED, "", "", "consumer entered"
    If gOrderBridgeConsumerRunning Then Exit Sub
    gOrderBridgeConsumerRunning = True
    OBR_CancelScheduledRun
    OBR_ReadBridgeReadyState readyState
    If Not readyState.Ready Then
        OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE, "", OBR_OBSERVABILITY_READY_FALSE, OBR_ReadyFalseDetail(readyState)
        GoTo CleanExit
    End If
    OBR_EnsureBridgeDirectories bridgeRoot
    OBR_ReconcileBridgeState bridgeRoot
    If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_TRUE, "", OBR_OBSERVABILITY_READY_TRUE, "ready gate true") Then GoTo CleanExit
    OBR_ProcessBridgePendingRequests bridgeRoot
CleanExit:
    gOrderBridgeConsumerRunning = False
    If gOrderBridgeSchedulerArmed Then
        OBR_ScheduleNextRun
    End If
    Exit Sub
CleanFail:
    Resume CleanExit
End Sub

Private Sub OBR_ProcessBridgePendingRequests(ByVal bridgeRoot As String)
    Dim pendingFolder As String
    Dim pendingFiles As Collection
    Dim pendingPath As Variant
    Dim cancelQueue As Collection

    pendingFolder = OBR_BridgePath(bridgeRoot, OBR_PENDING_RELATIVE)
    Set pendingFiles = OBR_PendingRequestFiles(pendingFolder)
    Set cancelQueue = New Collection

    For Each pendingPath In pendingFiles
        If FileExists(CStr(pendingPath)) Then
            OBR_ProcessPendingRequestPath bridgeRoot, CStr(pendingPath), cancelQueue
        End If
    Next pendingPath

    For Each pendingPath In cancelQueue
        If TypeName(pendingPath) = "Dictionary" Then
            OBR_ProcessQueuedCancelRecord bridgeRoot, pendingPath
        End If
    Next pendingPath
End Sub

Private Sub OBR_ReconcileBridgeState(ByVal bridgeRoot As String)
    OBR_ReconcileBridgeProcessing bridgeRoot
    OBR_ReconcileArchivedRequestFolder bridgeRoot, OBR_PROCESSED_RELATIVE
    OBR_ReconcileArchivedRequestFolder bridgeRoot, OBR_FAILED_RELATIVE
End Sub

Private Sub OBR_ReconcileBridgeProcessing(ByVal bridgeRoot As String)
    Dim processingFolder As String
    Dim processingFiles As Collection
    Dim filePath As Variant
    Dim fileStem As String

    processingFolder = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE)
    Set processingFiles = OBR_FolderCsvFiles(processingFolder)
    For Each filePath In processingFiles
        fileStem = OBR_FileBaseName(CStr(filePath))
        If StrComp(Left$(fileStem, 9), "receipt__", vbTextCompare) <> 0 Then
            OBR_ReconcileProcessingRequestPath bridgeRoot, CStr(filePath)
        End If
    Next filePath

    Set processingFiles = OBR_FolderCsvFiles(processingFolder)
    For Each filePath In processingFiles
        fileStem = OBR_FileBaseName(CStr(filePath))
        If StrComp(Left$(fileStem, 9), "receipt__", vbTextCompare) = 0 Then
            OBR_ReconcileProcessingReceiptStagePath bridgeRoot, CStr(filePath)
        End If
    Next filePath
End Sub

Private Sub OBR_ReconcileProcessingRequestPath(ByVal bridgeRoot As String, ByVal requestPath As String)
    Dim requestId As String
    Dim requestRow As Variant
    Dim requestChecksum As String
    Dim historyPath As String
    Dim historyStatus As String
    Dim stagePath As String
    Dim archivePath As String
    Dim stageIsSuccess As Boolean

    requestId = OBR_FileBaseName(requestPath)

    On Error GoTo RequestRecoverFail
    requestRow = ReadSingleCsvRecord(requestPath, OBR_RequestColumns())
    requestId = ValidateRequiredText(requestRow(OBR_REQ_REQUEST_ID), "request_id")
    requestChecksum = NormalizeText(requestRow(OBR_REQ_CHECKSUM))
    stagePath = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE & "\receipt__" & requestId & ".csv")

    If FileExists(stagePath) Then
        stageIsSuccess = OBR_ReceiptIsSuccessfulRequest(stagePath, requestId, requestChecksum)
        If stageIsSuccess Then
            archivePath = OBR_RequestArchivePath(bridgeRoot, requestId, "processed")
        Else
            archivePath = OBR_RequestArchivePath(bridgeRoot, requestId, "failed")
        End If
        OBR_MoveFileOrDeleteIfExists requestPath, archivePath
        Exit Sub
    End If

    historyStatus = OBR_RequestHistoryStatus(bridgeRoot, requestId, requestChecksum, historyPath)
    If historyStatus = "MATCH" Then
        OBR_MoveFileOrDeleteIfExists requestPath, historyPath
        Exit Sub
    End If

    archivePath = OBR_RequestArchivePath(bridgeRoot, requestId, "failed")
    OBR_MoveFileOrDeleteIfExists requestPath, archivePath
    Exit Sub

RequestRecoverFail:
    On Error Resume Next
    OBR_MoveFileOrDeleteIfExists requestPath, OBR_RequestArchivePath(bridgeRoot, requestId, "failed")
    On Error GoTo 0
End Sub

Private Sub OBR_ReconcileProcessingReceiptStagePath(ByVal bridgeRoot As String, ByVal receiptStagePath As String)
    Dim requestId As String
    Dim receiptPath As String

    requestId = OBR_ReceiptStageRequestId(receiptStagePath)
    If Len(requestId) = 0 Then Exit Sub
    receiptPath = OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE & "\" & requestId & ".csv")
    OBR_FinalizePublishReceiptStage receiptStagePath, receiptPath, requestId
End Sub

Private Function OBR_ReceiptStageRequestId(ByVal receiptStagePath As String) As String
    Dim fileStem As String

    fileStem = OBR_FileBaseName(receiptStagePath)
    If StrComp(Left$(fileStem, 9), "receipt__", vbTextCompare) <> 0 Then Exit Function
    OBR_ReceiptStageRequestId = Mid$(fileStem, 10)
End Function

Private Sub OBR_ReconcileArchivedRequestFolder(ByVal bridgeRoot As String, ByVal archiveRelative As String)
    Dim archiveFolder As String
    Dim archiveFiles As Collection
    Dim archivePath As Variant

    archiveFolder = OBR_BridgePath(bridgeRoot, archiveRelative)
    Set archiveFiles = OBR_FolderCsvFiles(archiveFolder)
    For Each archivePath In archiveFiles
        OBR_ReconcileArchivedRequestPath bridgeRoot, CStr(archivePath), archiveRelative
    Next archivePath
End Sub

Private Sub OBR_ReconcileArchivedRequestPath(ByVal bridgeRoot As String, ByVal archivePath As String, ByVal archiveRelative As String)
    Dim requestRow As Variant
    Dim requestId As String
    Dim requestKind As String
    Dim receiptPath As String
    Dim receiptStagePath As String
    Dim receiptValues As Variant
    Dim submitFields As Variant
    Dim mergedRow As Variant

    On Error GoTo ArchiveRecoverFail
    requestRow = ReadSingleCsvRecord(archivePath, OBR_RequestColumns())
    requestId = ValidateRequiredText(requestRow(OBR_REQ_REQUEST_ID), "request_id")
    receiptPath = OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE & "\" & requestId & ".csv")
    receiptStagePath = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE & "\receipt__" & requestId & ".csv")
    If StrComp(archiveRelative, OBR_PROCESSED_RELATIVE, vbTextCompare) = 0 Then
        requestKind = UCase$(ValidateRequiredText(requestRow(OBR_REQ_REQUEST_KIND), "request_kind"))
        If requestKind = "CANCEL" Then
            submitFields = OBR_LoadSubmitHistoryFields(bridgeRoot, NormalizeText(requestRow(OBR_REQ_BROKER_ORDER_ID)), NormalizeText(requestRow(OBR_REQ_CLIENT_ORDER_ID)))
            mergedRow = requestRow
            If Not IsEmpty(submitFields) Then
                mergedRow = OBR_MergeCancelRequestRow(requestRow, submitFields)
            End If
            receiptValues = OBR_BuildReceiptValues( _
                mergedRow, _
                CurrentJst(), _
                "ACCEPTED", _
                "CANCELED", _
                OBR_InvalidStatusText(), _
                NormalizeText(mergedRow(OBR_REQ_BROKER_ORDER_ID)), _
                OBR_CANCEL_ACCEPTED_MESSAGE, _
                "", _
                OBR_CANCEL_ACCEPTED_MESSAGE)
        ElseIf requestKind = "SUBMIT" Then
            receiptValues = OBR_BuildReceiptValues( _
                requestRow, _
                CurrentJst(), _
                "ACCEPTED", _
                "ACCEPTED", _
                OBR_ValidStatusText(), _
                NormalizeText(requestRow(OBR_REQ_BROKER_ORDER_ID)), _
                OBR_SUBMIT_ACCEPTED_MESSAGE, _
                "", _
                OBR_SUBMIT_ACCEPTED_MESSAGE)
        Else
            Exit Sub
        End If
    Else
        receiptValues = OBR_BuildReceiptValues( _
            requestRow, _
            CurrentJst(), _
            "REJECTED", _
            "REJECTED", _
            OBR_CORRUPT_STATUS, _
            NormalizeText(requestRow(OBR_REQ_BROKER_ORDER_ID)), _
            "failed request history", _
            "FAILED_HISTORY_MATCH", _
            "failed request history match")
    End If

    WriteCsvRecordAtomic receiptStagePath, OBR_ReceiptColumns(), receiptValues
    OBR_FinalizePublishReceiptStage receiptStagePath, receiptPath, requestId
    Exit Sub

ArchiveRecoverFail:
    On Error GoTo 0
End Sub

Private Sub OBR_ProcessPendingRequestPath( _
    ByVal bridgeRoot As String, _
    ByVal requestPath As String, _
    ByRef cancelQueue As Collection)

    Dim requestRow As Variant
    Dim requestId As String
    Dim requestKind As String
    Dim requestChecksum As String
    Dim requestStem As String
    Dim historyPath As String
    Dim historyStatus As String
    Dim cancelRecord As Object

    On Error GoTo ReadFail
    requestRow = ReadSingleCsvRecord(requestPath, OBR_RequestColumns())

    requestId = ValidateRequiredText(requestRow(OBR_REQ_REQUEST_ID), "request_id")
    requestStem = OBR_FileBaseName(requestPath)
    If StrComp(requestId, requestStem, vbTextCompare) <> 0 Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, OBR_REQUEST_READ_FAILED_MESSAGE, "REQUEST_ID_MISMATCH", "request_id does not match file name"
        Exit Sub
    End If

    requestKind = UCase$(ValidateRequiredText(requestRow(OBR_REQ_REQUEST_KIND), "request_kind"))
    If requestKind <> "SUBMIT" And requestKind <> "CANCEL" Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "unsupported request_kind", "UNSUPPORTED_REQUEST_KIND", requestKind
        Exit Sub
    End If

    requestChecksum = NormalizeText(requestRow(OBR_REQ_CHECKSUM))
    If Len(requestChecksum) = 0 Or StrComp(requestChecksum, OBR_RequestChecksumFromRow(requestRow), vbBinaryCompare) <> 0 Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "request checksum mismatch", "CHECKSUM_MISMATCH", "request checksum mismatch"
        Exit Sub
    End If

    historyStatus = OBR_RequestHistoryStatus(bridgeRoot, requestId, requestChecksum, historyPath)
    If historyStatus = "MATCH" Then
        OBR_FinalizeAcceptedDuplicate bridgeRoot, requestPath, requestRow
        Exit Sub
    End If
    If historyStatus = "FAILED" Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "failed request history", "FAILED_HISTORY_MATCH", "failed request history match"
        Exit Sub
    End If
    If historyStatus = "MISMATCH" Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "request checksum conflict", "REQUEST_CHECKSUM_CONFLICT", "request_id checksum conflict"
        Exit Sub
    End If

    If Not OBR_LogOrderBridgeEvent(bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_STARTED, requestId, "", "request processing started") Then Exit Sub

    If requestKind = "SUBMIT" Then
        OBR_ProcessSubmitRequestRow bridgeRoot, requestPath, requestRow
        Exit Sub
    End If

    Set cancelRecord = CreateObject("Scripting.Dictionary")
    cancelRecord("path") = requestPath
    cancelRecord("row") = requestRow
    cancelQueue.Add cancelRecord
    Exit Sub

ReadFail:
    On Error GoTo 0
    OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, "", "", "request csv read failed"
    OBR_FinalizeRejectedRequest bridgeRoot, requestPath, OBR_SyntheticRequestRow(OBR_FileBaseName(requestPath), "", "", ""), OBR_REQUEST_READ_FAILED_MESSAGE, "REQUEST_READ_FAILED", "Could not read request CSV: " & OBR_FileBaseName(requestPath), "", emitTerminalObservability:=False
End Sub

Private Sub OBR_ProcessQueuedCancelRecord(ByVal bridgeRoot As String, ByVal cancelRecord As Object)
    Dim requestPath As String
    Dim requestRow As Variant

    requestPath = CStr(cancelRecord("path"))
    requestRow = cancelRecord("row")
    OBR_ProcessCancelRequestRow bridgeRoot, requestPath, requestRow
End Sub

Private Sub OBR_ProcessSubmitRequestRow(ByVal bridgeRoot As String, ByVal requestPath As String, ByVal requestRow As Variant)
    Dim requestId As String
    Dim requestChecksum As String
    Dim historyPath As String
    Dim historyStatus As String
    Dim readyState As OBRBridgeReadyState
    Dim receiptValues As Variant

    On Error GoTo SubmitFail
    requestId = ValidateRequiredText(requestRow(OBR_REQ_REQUEST_ID), "request_id")
    requestChecksum = NormalizeText(requestRow(OBR_REQ_CHECKSUM))
    historyStatus = OBR_RequestHistoryStatus(bridgeRoot, requestId, requestChecksum, historyPath)
    If historyStatus = "MATCH" Then
        OBR_FinalizeAcceptedDuplicate bridgeRoot, requestPath, requestRow
        Exit Sub
    End If
    If historyStatus = "FAILED" Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "failed request history", "FAILED_HISTORY_MATCH", "failed request history match"
        Exit Sub
    End If
    If historyStatus = "MISMATCH" Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "request checksum conflict", "REQUEST_CHECKSUM_CONFLICT", "request_id checksum conflict"
        Exit Sub
    End If

    OBR_ReadBridgeReadyState readyState
    If Not readyState.Ready Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, OBR_READY_BRIDGE_MESSAGE, "READY_STATE_FALSE", OBR_READY_ERROR_MESSAGE, OBR_DISCONNECTED_STATUS
        Exit Sub
    End If

    If OBR_RequestIsLiveIntent(requestRow) Then
        If Not OBR_RequestLiveFlagsComplete(requestRow) Then
            OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "live request flags insufficient", OBR_LIVE_REQUEST_FLAGS_INSUFFICIENT_ERROR_CODE, "live request flags insufficient"
            Exit Sub
        End If
        If Not OBR_BRIDGE_ARMED Then
            OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "live request requires bridge armed", OBR_LIVE_REQUEST_REQUIRES_BRIDGE_ARMED_ERROR_CODE, "live request requires bridge armed"
            Exit Sub
        End If
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "live fire call contract not proven", OBR_LIVE_FIRE_CALL_CONTRACT_NOT_PROVEN_ERROR_CODE, "live fire call contract not proven"
        Exit Sub
    End If

    receiptValues = OBR_BuildReceiptValues( _
        requestRow, _
        CurrentJst(), _
        "ACCEPTED", _
        "ACCEPTED", _
        OBR_ValidStatusText(), _
        NormalizeText(requestRow(OBR_REQ_BROKER_ORDER_ID)), _
        OBR_SUBMIT_ACCEPTED_MESSAGE, _
        "", _
        OBR_SUBMIT_ACCEPTED_MESSAGE)

    OBR_FinalizeAcceptedRequest bridgeRoot, requestPath, receiptValues, "processed"
    Exit Sub

SubmitFail:
    On Error GoTo 0
    OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "processing failed", Err.Source, Err.Description
End Sub

Private Sub OBR_ProcessCancelRequestRow(ByVal bridgeRoot As String, ByVal requestPath As String, ByVal requestRow As Variant)
    Dim requestId As String
    Dim requestChecksum As String
    Dim historyPath As String
    Dim historyStatus As String
    Dim readyState As OBRBridgeReadyState
    Dim submitFields As Variant
    Dim mergedRow As Variant
    Dim receiptValues As Variant

    On Error GoTo CancelFail
    requestId = ValidateRequiredText(requestRow(OBR_REQ_REQUEST_ID), "request_id")
    requestChecksum = NormalizeText(requestRow(OBR_REQ_CHECKSUM))
    historyStatus = OBR_RequestHistoryStatus(bridgeRoot, requestId, requestChecksum, historyPath)
    If historyStatus = "MATCH" Then
        OBR_FinalizeAcceptedDuplicate bridgeRoot, requestPath, requestRow
        Exit Sub
    End If
    If historyStatus = "FAILED" Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "failed request history", "FAILED_HISTORY_MATCH", "failed request history match"
        Exit Sub
    End If
    If historyStatus = "MISMATCH" Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "request checksum conflict", "REQUEST_CHECKSUM_CONFLICT", "request_id checksum conflict"
        Exit Sub
    End If

    OBR_ReadBridgeReadyState readyState
    If Not readyState.Ready Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, OBR_READY_BRIDGE_MESSAGE, "READY_STATE_FALSE", OBR_READY_ERROR_MESSAGE, OBR_DISCONNECTED_STATUS
        Exit Sub
    End If

    submitFields = OBR_LoadSubmitHistoryFields(bridgeRoot, NormalizeText(requestRow(OBR_REQ_BROKER_ORDER_ID)), NormalizeText(requestRow(OBR_REQ_CLIENT_ORDER_ID)))
    If IsEmpty(submitFields) Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "related submit not found", "RELATED_SUBMIT_NOT_FOUND", "related submit not found"
        Exit Sub
    End If
    If Len(NormalizeText(submitFields(5))) = 0 Then
        OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "related submit order number missing", "RELATED_SUBMIT_ORDER_NUMBER_MISSING", "related submit order number missing"
        Exit Sub
    End If

    mergedRow = OBR_MergeCancelRequestRow(requestRow, submitFields)
    receiptValues = OBR_BuildReceiptValues( _
        mergedRow, _
        CurrentJst(), _
        "ACCEPTED", _
        "CANCELED", _
        OBR_InvalidStatusText(), _
        NormalizeText(submitFields(5)), _
        OBR_CANCEL_ACCEPTED_MESSAGE, _
        "", _
        OBR_CANCEL_ACCEPTED_MESSAGE)

    OBR_FinalizeAcceptedRequest bridgeRoot, requestPath, receiptValues, "processed"
    Exit Sub

CancelFail:
    On Error GoTo 0
    OBR_FinalizeRejectedRequest bridgeRoot, requestPath, requestRow, "processing failed", Err.Source, Err.Description
End Sub

Private Sub OBR_FinalizeAcceptedDuplicate(ByVal bridgeRoot As String, ByVal requestPath As String, ByVal requestRow As Variant)
    Dim requestId As String
    Dim processingPath As String
    Dim archivePath As String

    requestId = NormalizeText(requestRow(OBR_REQ_REQUEST_ID))
    processingPath = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE & "\" & requestId & ".csv")
    archivePath = OBR_RequestArchivePath(bridgeRoot, requestId, "processed")
    On Error GoTo DuplicateFail
    OBR_MoveFileOrDeleteIfExists requestPath, processingPath
    OBR_MoveFileOrDeleteIfExists processingPath, archivePath
    Exit Sub

DuplicateFail:
    On Error GoTo 0
End Sub

Private Sub OBR_FinalizeRejectedRequest( _
    ByVal bridgeRoot As String, _
    ByVal requestPath As String, _
    ByVal requestRow As Variant, _
    ByVal message As String, _
    ByVal errorCode As String, _
    ByVal errorMessage As String, _
    Optional ByVal rssOrderStatus As String = "", _
    Optional ByVal emitTerminalObservability As Boolean = True)

    Dim receiptValues As Variant
    Dim responseStatus As String

    responseStatus = rssOrderStatus
    If Len(responseStatus) = 0 Then responseStatus = OBR_CORRUPT_STATUS
    receiptValues = OBR_BuildReceiptValues( _
        requestRow, _
        CurrentJst(), _
        "REJECTED", _
        "REJECTED", _
        responseStatus, _
        NormalizeText(requestRow(OBR_REQ_BROKER_ORDER_ID)), _
        message, _
        errorCode, _
        errorMessage)
    OBR_FinalizeAcceptedRequest bridgeRoot, requestPath, receiptValues, "failed", emitTerminalObservability
End Sub

Private Sub OBR_FinalizeAcceptedRequest( _
    ByVal bridgeRoot As String, _
    ByVal requestPath As String, _
    ByVal receiptValues As Variant, _
    ByVal archiveStatus As String, _
    Optional ByVal emitTerminalObservability As Boolean = True)
    Dim requestId As String
    Dim requestChecksum As String
    Dim receiptPath As String
    Dim processingPath As String
    Dim receiptStagePath As String
    Dim archivePath As String
    Dim stagedReceipt As Boolean
    Dim publishSucceeded As Boolean
    Dim receiptChecksum As String
    Dim existingChecksum As String
    Dim errorNumber As Long
    Dim errorSource As String
    Dim errorDescription As String

    requestId = NormalizeText(receiptValues(OBR_REC_REQUEST_ID))
    requestChecksum = NormalizeText(receiptValues(OBR_REC_REQUEST_CHECKSUM))
    receiptPath = OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE & "\" & requestId & ".csv")
    processingPath = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE & "\" & requestId & ".csv")
    receiptStagePath = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE & "\receipt__" & requestId & ".csv")
    archivePath = OBR_RequestArchivePath(bridgeRoot, requestId, archiveStatus)
    On Error GoTo FinalizeFail

    If Len(requestChecksum) = 0 Then
        Err.Raise vbObjectError + 7816, OBR_MODULE_NAME, "Receipt request_checksum missing: " & requestId
    End If
    receiptChecksum = NormalizeText(receiptValues(OBR_REC_CHECKSUM))
    If Len(receiptChecksum) = 0 Then
        receiptChecksum = OBR_ReceiptChecksumFromValues(receiptValues)
    End If

    OBR_MoveFileOrDeleteIfExists requestPath, processingPath

    If FileExists(receiptStagePath) Then
        existingChecksum = OBR_ReceiptChecksumAtPath(receiptStagePath)
        If StrComp(existingChecksum, receiptChecksum, vbBinaryCompare) = 0 Then
            stagedReceipt = True
        Else
            Err.Raise vbObjectError + 7816, OBR_MODULE_NAME, "Receipt stage already exists: " & receiptStagePath
        End If
    ElseIf FileExists(receiptPath) Then
        existingChecksum = OBR_ReceiptChecksumAtPath(receiptPath)
        If StrComp(existingChecksum, receiptChecksum, vbBinaryCompare) = 0 Then
            stagedReceipt = False
        Else
            Err.Raise vbObjectError + 7817, OBR_MODULE_NAME, "Receipt path already exists: " & receiptPath
        End If
    Else
        WriteCsvRecordAtomic receiptStagePath, OBR_ReceiptColumns(), receiptValues
        stagedReceipt = True
    End If

    OBR_MoveFileOrDeleteIfExists processingPath, archivePath

    If stagedReceipt Then
        publishSucceeded = OBR_FinalizePublishReceiptStage(receiptStagePath, receiptPath, requestId)
    Else
        publishSucceeded = True
    End If

    If publishSucceeded And emitTerminalObservability Then
        If StrComp(NormalizeText(receiptValues(OBR_REC_BRIDGE_STATUS)), "ACCEPTED", vbTextCompare) = 0 Then
            OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_ACCEPTED, requestId, "", "request finalized accepted"
        ElseIf StrComp(NormalizeText(receiptValues(OBR_REC_BRIDGE_STATUS)), "REJECTED", vbTextCompare) = 0 Then
            OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_REQUEST_REJECTED, requestId, "", "request finalized rejected"
        End If
    End If
    Exit Sub

FinalizeFail:
    errorNumber = Err.Number
    errorSource = Err.Source
    errorDescription = Err.Description
    On Error GoTo 0
    Err.Raise errorNumber, errorSource, errorDescription
End Sub

Private Function OBR_RequestArchivePath(ByVal bridgeRoot As String, ByVal requestId As String, ByVal archiveStatus As String) As String
    If LCase$(archiveStatus) = "failed" Then
        OBR_RequestArchivePath = OBR_BridgePath(bridgeRoot, OBR_FAILED_RELATIVE & "\" & requestId & ".csv")
    Else
        OBR_RequestArchivePath = OBR_BridgePath(bridgeRoot, OBR_PROCESSED_RELATIVE & "\" & requestId & ".csv")
    End If
End Function

Private Sub OBR_ReadBridgeReadyState(ByRef readyState As OBRBridgeReadyState)
    Dim sheet As Object
    Dim addInReason As String
    Dim heartbeatText As String
    Dim heartbeatAt As Date
    Dim ageSeconds As Long

    On Error GoTo ReadyFail
    Set sheet = ThisWorkbook.Worksheets(OBR_TRANSPORT_SHEET_NAME)
    readyState.ExcelAlive = IsTruthyValue(sheet.Range("J2").Value2)
    readyState.RssConnected = IsTruthyValue(sheet.Range("J3").Value2)
    readyState.AddInReady = IsTruthyValue(sheet.Range("J4").Value2)
    readyState.OrderTransportReady = IsTruthyValue(sheet.Range("J5").Value2)
    heartbeatText = NormalizeText(sheet.Range("J6").Value2)
    heartbeatAt = ParseJstTimestamp(heartbeatText, "heartbeat")
    ageSeconds = DateDiff("s", heartbeatAt, CurrentJst())
    readyState.HeartbeatAgeSeconds = ageSeconds
    If Not OBR_CheckRequiredAddIns(addInReason) Then
        readyState.Reason = addInReason
        readyState.Ready = False
        Exit Sub
    End If
    readyState.Ready = readyState.ExcelAlive And readyState.RssConnected And readyState.AddInReady And readyState.OrderTransportReady And ageSeconds >= 0 And ageSeconds <= OBR_HEARTBEAT_MAX_AGE_SECONDS
    If Not readyState.Ready Then
        readyState.Reason = OBR_READY_ERROR_MESSAGE
    End If
    Exit Sub

ReadyFail:
    readyState.Ready = False
    readyState.Reason = "Transport sheet status is unreadable."
End Sub

Private Function OBR_CheckRequiredAddIns(ByRef reason As String) As Boolean
    Dim addInNames As Variant
    Dim addInName As Variant
    Dim addIn As Object
    Dim installed As Boolean

    addInNames = Array("MarketSpeed2_RSS_64bit.xll", "MarketSpeed2_RSS_VBA.xlam")
    On Error GoTo AddInFail
    For Each addInName In addInNames
        installed = False
        For Each addIn In Application.AddIns
            If StrComp(NormalizeText(addIn.Name), CStr(addInName), vbTextCompare) = 0 Then
                installed = CBool(addIn.Installed)
                Exit For
            End If
        Next addIn
        If Not installed Then
            reason = "Missing RSS add-in: " & CStr(addInName)
            OBR_CheckRequiredAddIns = False
            Exit Function
        End If
    Next addInName
    OBR_CheckRequiredAddIns = True
    Exit Function

AddInFail:
    reason = "RSS add-in list is unavailable."
    OBR_CheckRequiredAddIns = False
End Function

Private Function OBR_FindRepositoryRoot(ByVal startPath As String) As String
    Dim currentPath As String
    Dim parentPath As String
    Dim fso As Object

    If Len(startPath) = 0 Then
        Err.Raise vbObjectError + 7801, OBR_MODULE_NAME, "Workbook must be saved before running the bridge consumer"
    End If

    currentPath = OBR_NormalizeRepositoryStartPath(startPath)
    Set fso = CreateObject("Scripting.FileSystemObject")
    Do
        If OBR_RepositoryLooksValid(currentPath) Then
            OBR_FindRepositoryRoot = currentPath
            Exit Function
        End If
        parentPath = fso.GetParentFolderName(currentPath)
        If Len(parentPath) = 0 Or parentPath = currentPath Then Exit Do
        currentPath = parentPath
    Loop

    Err.Raise vbObjectError + 7802, OBR_MODULE_NAME, "Unable to resolve the PHOENIX repository root"
End Function

Private Function OBR_NormalizeRepositoryStartPath(ByVal startPath As String) As String
    Dim relativePath As String
    Dim webPath As String
    Dim firstSlash As Long

    webPath = NormalizeText(startPath)
    If Len(webPath) = 0 Then Exit Function
    If StrComp(Left$(webPath, Len(OBR_ONEDRIVE_WEB_PREFIX)), OBR_ONEDRIVE_WEB_PREFIX, vbTextCompare) <> 0 Then
        OBR_NormalizeRepositoryStartPath = webPath
        Exit Function
    End If

    firstSlash = InStr(Len(OBR_ONEDRIVE_WEB_PREFIX) + 1, webPath, "/", vbBinaryCompare)
    If firstSlash = 0 Then
        Err.Raise vbObjectError + 7811, OBR_MODULE_NAME, "Unable to map OneDrive web path to a local folder"
    End If

    relativePath = Mid$(webPath, firstSlash + 1)
    If Len(relativePath) = 0 Then
        Err.Raise vbObjectError + 7811, OBR_MODULE_NAME, "Unable to map OneDrive web path to a local folder"
    End If

    OBR_NormalizeRepositoryStartPath = OBR_OneDriveLocalRoot() & "\" & Replace$(relativePath, "/", "\")
End Function

Private Function OBR_OneDriveLocalRoot() As String
    Dim candidate As String
    Dim fso As Object

    candidate = NormalizeText(Environ$("OneDrive"))
    If Len(candidate) > 0 Then
        OBR_OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = NormalizeText(Environ$("OneDriveConsumer"))
    If Len(candidate) > 0 Then
        OBR_OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = NormalizeText(Environ$("OneDriveCommercial"))
    If Len(candidate) > 0 Then
        OBR_OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = NormalizeText(Environ$("USERPROFILE"))
    If Len(candidate) > 0 Then
        candidate = candidate & "\OneDrive"
        Set fso = CreateObject("Scripting.FileSystemObject")
        If fso.FolderExists(candidate) Then
            OBR_OneDriveLocalRoot = candidate
            Exit Function
        End If
    End If

    Err.Raise vbObjectError + 7812, OBR_MODULE_NAME, "Unable to resolve the local OneDrive root"
End Function

Private Function OBR_RepositoryLooksValid(ByVal rootPath As String) As Boolean
    OBR_RepositoryLooksValid = _
        FileExists(OBR_BridgePath(rootPath, "run_phoenix.py")) And _
        FileExists(OBR_BridgePath(rootPath, "AGENTS.md")) And _
        FileExists(OBR_BridgePath(rootPath, "phoenix_core\__init__.py"))
End Function

Private Sub OBR_EnsureBridgeDirectories(ByVal bridgeRoot As String)
    EnsureFolderTree bridgeRoot
    EnsureFolderTree OBR_BridgePath(bridgeRoot, OBR_PENDING_RELATIVE)
    EnsureFolderTree OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE)
    EnsureFolderTree OBR_BridgePath(bridgeRoot, OBR_PROCESSED_RELATIVE)
    EnsureFolderTree OBR_BridgePath(bridgeRoot, OBR_FAILED_RELATIVE)
    EnsureFolderTree OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE)
End Sub

Private Function OBR_PendingRequestFiles(ByVal pendingFolder As String) As Collection
    Dim files As New Collection
    Dim fileName As String

    fileName = Dir$(pendingFolder & "\*.csv")
    Do While Len(fileName) > 0
        files.Add pendingFolder & "\" & fileName
        fileName = Dir$()
    Loop
    Set OBR_PendingRequestFiles = files
End Function

Private Function OBR_FolderCsvFiles(ByVal folderPath As String) As Collection
    Dim files As New Collection
    Dim fileName As String

    fileName = Dir$(folderPath & "\*.csv")
    Do While Len(fileName) > 0
        files.Add folderPath & "\" & fileName
        fileName = Dir$()
    Loop
    Set OBR_FolderCsvFiles = files
End Function

Private Function OBR_FileBaseName(ByVal filePath As String) As String
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    OBR_FileBaseName = fso.GetBaseName(filePath)
End Function

Private Function OBR_BridgePath(ByVal rootPath As String, ByVal relativePath As String) As String
    OBR_BridgePath = rootPath & "\" & Replace$(relativePath, "/", "\")
End Function

Private Function OBR_ObservabilityColumns() As Variant
    OBR_ObservabilityColumns = Array("timestamp", "event", "request_id", "ready", "detail")
End Function

Private Function OBR_ObservabilityRecordValues(ByVal eventName As String, ByVal requestId As String, ByVal readyValue As String, ByVal detail As String) As Variant
    Dim record(0 To 4) As String

    record(0) = Format$(CurrentJst(), "yyyy-mm-dd\THH:nn:ss")
    record(1) = NormalizeText(eventName)
    record(2) = NormalizeText(requestId)
    record(3) = NormalizeText(readyValue)
    record(4) = NormalizeText(detail)
    OBR_ObservabilityRecordValues = record
End Function

Private Function OBR_BooleanText(ByVal value As Boolean) As String
    If value Then
        OBR_BooleanText = "TRUE"
    Else
        OBR_BooleanText = "FALSE"
    End If
End Function

Private Function OBR_ReadyFalseDetail(ByRef readyState As OBRBridgeReadyState) As String
    OBR_ReadyFalseDetail = _
        "ExcelAlive=" & OBR_BooleanText(readyState.ExcelAlive) & ";" & _
        "RssConnected=" & OBR_BooleanText(readyState.RssConnected) & ";" & _
        "AddInReady=" & OBR_BooleanText(readyState.AddInReady) & ";" & _
        "OrderTransportReady=" & OBR_BooleanText(readyState.OrderTransportReady) & ";" & _
        "HeartbeatAgeSeconds=" & CStr(readyState.HeartbeatAgeSeconds) & ";" & _
        "Ready=" & OBR_BooleanText(readyState.Ready)
End Function

Private Function OBR_RequestIsLiveIntent(ByVal requestRow As Variant) As Boolean
    OBR_RequestIsLiveIntent = _
        IsTruthyValue(requestRow(OBR_REQ_LIVE_TRADING_ENABLED)) Or _
        IsTruthyValue(requestRow(OBR_REQ_PRODUCTION_TRANSPORT_ENABLED)) Or _
        IsTruthyValue(requestRow(OBR_REQ_ARMED))
End Function

Private Function OBR_RequestLiveFlagsComplete(ByVal requestRow As Variant) As Boolean
    OBR_RequestLiveFlagsComplete = _
        IsTruthyValue(requestRow(OBR_REQ_LIVE_TRADING_ENABLED)) And _
        IsTruthyValue(requestRow(OBR_REQ_PRODUCTION_TRANSPORT_ENABLED)) And _
        IsTruthyValue(requestRow(OBR_REQ_ARMED))
End Function

Private Function OBR_ObservabilityPath(ByVal bridgeRoot As String) As String
    OBR_ObservabilityPath = OBR_BridgePath(bridgeRoot, OBR_OBSERVABILITY_RELATIVE)
End Function

Private Function OBR_LogOrderBridgeEvent(ByVal bridgeRoot As String, ByVal eventName As String, ByVal requestId As String, ByVal readyValue As String, ByVal detail As String) As Boolean
    Dim observabilityPath As String

    If Len(bridgeRoot) = 0 Then Exit Function
    observabilityPath = OBR_ObservabilityPath(bridgeRoot)
    OBR_LogOrderBridgeEvent = OBR_WriteOrderBridgeEventRow(observabilityPath, OBR_ObservabilityRecordValues(eventName, requestId, readyValue, detail))
    If Not OBR_LogOrderBridgeEvent Then
        If StrComp(NormalizeText(eventName), OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, vbTextCompare) <> 0 Then
            Call OBR_WriteOrderBridgeEventRow(observabilityPath, OBR_ObservabilityRecordValues(OBR_OBSERVABILITY_EVENT_OBSERVABILITY_ERROR, "", "", NormalizeText(eventName) & " write failed"))
        End If
    End If
End Function

Private Function OBR_WriteOrderBridgeEventRow(ByVal observabilityPath As String, ByVal rowValues As Variant) As Boolean
    Dim handle As LongPtr
    Dim content As String
    Dim bytes() As Byte
    Dim byteCount As Long
    Dim bytesWritten As Long
    Dim creationStatus As Long

    If Len(observabilityPath) = 0 Then Exit Function
    On Error GoTo FailHandler
    EnsureFolderTree ParentFolderPath(observabilityPath)
    handle = CreateFileW(StrPtr(observabilityPath), OBR_FILE_APPEND_DATA, OBR_FILE_SHARE_READ Or OBR_FILE_SHARE_WRITE Or OBR_FILE_SHARE_DELETE, 0, OBR_OPEN_ALWAYS, OBR_FILE_ATTRIBUTE_NORMAL, 0)
    If handle = OBR_INVALID_HANDLE_VALUE Then GoTo FailHandler
    creationStatus = GetLastError()
    If creationStatus = OBR_ERROR_ALREADY_EXISTS Then
        content = CsvRowText(rowValues) & vbCrLf
    Else
        content = ChrW$(&HFEFF) & CsvHeaderText(OBR_ObservabilityColumns()) & vbCrLf & CsvRowText(rowValues) & vbCrLf
    End If
    bytes = OBR_Utf8BytesFromText(content, byteCount)
    If byteCount > 0 Then
        If WriteFile(handle, bytes(0), byteCount, bytesWritten, 0) = 0 Then GoTo FailHandler
        If bytesWritten <> byteCount Then GoTo FailHandler
    End If
    OBR_WriteOrderBridgeEventRow = True
    GoTo CleanExit

FailHandler:
    On Error Resume Next
CleanExit:
    If handle <> 0 And handle <> OBR_INVALID_HANDLE_VALUE Then CloseHandle handle
    On Error GoTo 0
End Function

Private Function OBR_MoveFileAtomic(ByVal sourcePath As String, ByVal destinationPath As String) As String
    Dim result As Long

    EnsureFolderTree ParentFolderPath(destinationPath)
    If FileExists(destinationPath) Then
        Err.Raise vbObjectError + 7804, OBR_MODULE_NAME, "Destination already exists: " & destinationPath
    End If
    result = MoveFileExW(StrPtr(sourcePath), StrPtr(destinationPath), &H8)
    If result = 0 Then
        Err.Raise vbObjectError + 7803, OBR_MODULE_NAME, "Atomic move failed: " & sourcePath & " -> " & destinationPath
    End If
    OBR_MoveFileAtomic = destinationPath
End Function

Private Sub OBR_MoveFileOrDeleteIfExists(ByVal sourcePath As String, ByVal destinationPath As String)
    Dim errorNumber As Long
    Dim errorSource As String
    Dim errorDescription As String

    If FileExists(destinationPath) Then
        OBR_DeleteFileIfExists sourcePath
        Exit Sub
    End If

    On Error GoTo MoveFail
    OBR_MoveFileAtomic sourcePath, destinationPath
    Exit Sub

MoveFail:
    errorNumber = Err.Number
    errorSource = Err.Source
    errorDescription = Err.Description
    On Error Resume Next
    If FileExists(destinationPath) Then
        OBR_DeleteFileIfExists sourcePath
        Err.Clear
        On Error GoTo 0
        Exit Sub
    End If
    On Error GoTo 0
    Err.Raise errorNumber, errorSource, errorDescription
End Sub

Private Function OBR_FinalizePublishReceiptStage(ByVal receiptStagePath As String, ByVal receiptPath As String, ByVal requestId As String) As Boolean
    Dim receiptRow As Variant
    Dim receiptChecksum As String
    Dim existingChecksum As String

    On Error GoTo PublishFail
    receiptRow = ReadSingleCsvRecord(receiptStagePath, OBR_ReceiptColumns())
    If StrComp(NormalizeText(receiptRow(OBR_REC_REQUEST_ID)), requestId, vbTextCompare) <> 0 Then
        Err.Raise vbObjectError + 7814, OBR_MODULE_NAME, "Receipt stage request_id mismatch: " & receiptStagePath
    End If
    receiptChecksum = NormalizeText(receiptRow(OBR_REC_CHECKSUM))
    If Len(receiptChecksum) = 0 Then
        Err.Raise vbObjectError + 7814, OBR_MODULE_NAME, "Receipt stage checksum missing: " & receiptStagePath
    End If

    If FileExists(receiptPath) Then
        existingChecksum = OBR_ReceiptChecksumAtPath(receiptPath)
        If StrComp(existingChecksum, receiptChecksum, vbBinaryCompare) = 0 Then
            OBR_DeleteFileIfExists receiptStagePath
            OBR_FinalizePublishReceiptStage = True
            Exit Function
        End If
        Err.Raise vbObjectError + 7814, OBR_MODULE_NAME, "Receipt path already exists: " & receiptPath
    End If
    OBR_MoveFileAtomic receiptStagePath, receiptPath
    OBR_FinalizePublishReceiptStage = True
    Exit Function

PublishFail:
    On Error Resume Next
    On Error GoTo 0
    OBR_FinalizePublishReceiptStage = False
End Function

Private Function OBR_RequestHistoryStatus( _
    ByVal bridgeRoot As String, _
    ByVal requestId As String, _
    ByVal requestChecksum As String, _
    ByRef historyPath As String) As String

    Dim existingChecksum As String
    Dim processedPath As String
    Dim receiptPath As String
    Dim receiptStatus As String

    existingChecksum = OBR_ExistingHistoryChecksum(bridgeRoot, requestId, historyPath)
    processedPath = OBR_BridgePath(bridgeRoot, OBR_PROCESSED_RELATIVE & "\" & requestId & ".csv")
    If Len(historyPath) = 0 Then
        receiptPath = OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE & "\" & requestId & ".csv")
        receiptStatus = OBR_ReceiptRequestStatus(receiptPath, requestId, requestChecksum)
        If Len(receiptStatus) = 0 Then
            receiptPath = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE & "\receipt__" & requestId & ".csv")
            receiptStatus = OBR_ReceiptRequestStatus(receiptPath, requestId, requestChecksum)
        End If
        If receiptStatus = "MATCH" Then
            historyPath = processedPath
            OBR_RequestHistoryStatus = "MATCH"
        ElseIf Len(receiptStatus) > 0 Then
            OBR_RequestHistoryStatus = receiptStatus
        Else
            OBR_RequestHistoryStatus = "NONE"
        End If
        Exit Function
    End If
    If Len(existingChecksum) = 0 Then
        OBR_RequestHistoryStatus = "FAILED"
        Exit Function
    End If
    If StrComp(existingChecksum, requestChecksum, vbBinaryCompare) <> 0 Then
        OBR_RequestHistoryStatus = "MISMATCH"
        Exit Function
    End If

    If StrComp(historyPath, processedPath, vbBinaryCompare) = 0 Then
        OBR_RequestHistoryStatus = "MATCH"
    Else
        OBR_RequestHistoryStatus = "FAILED"
    End If
End Function

Private Function OBR_ExistingHistoryChecksum(ByVal bridgeRoot As String, ByVal requestId As String, ByRef historyPath As String) As String
    Dim candidatePaths As Variant
    Dim candidatePath As Variant
    Dim rowValues As Variant

    candidatePaths = Array( _
        OBR_BridgePath(bridgeRoot, OBR_PROCESSED_RELATIVE & "\" & requestId & ".csv"), _
        OBR_BridgePath(bridgeRoot, OBR_FAILED_RELATIVE & "\" & requestId & ".csv"))

    For Each candidatePath In candidatePaths
        If FileExists(CStr(candidatePath)) Then
            historyPath = CStr(candidatePath)
            On Error Resume Next
            rowValues = ReadSingleCsvRecord(CStr(candidatePath), OBR_RequestColumns())
            If Err.Number = 0 Then
                OBR_ExistingHistoryChecksum = NormalizeText(rowValues(OBR_REQ_CHECKSUM))
            End If
            Err.Clear
            On Error GoTo 0
            Exit Function
        End If
    Next candidatePath
End Function

Private Function OBR_SuccessReceiptExists(ByVal bridgeRoot As String, ByVal requestId As String, ByVal requestChecksum As String) As Boolean
    Dim receiptPath As String
    Dim receiptStatus As String

    receiptPath = OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE & "\" & requestId & ".csv")
    receiptStatus = OBR_ReceiptRequestStatus(receiptPath, requestId, requestChecksum)
    If receiptStatus = "MATCH" Then
        OBR_SuccessReceiptExists = True
        Exit Function
    End If
    If Len(receiptStatus) > 0 Then
        Err.Raise vbObjectError + 7817, OBR_MODULE_NAME, "Receipt path is not a matching successful receipt: " & receiptPath
    End If

    receiptPath = OBR_BridgePath(bridgeRoot, OBR_PROCESSING_RELATIVE & "\receipt__" & requestId & ".csv")
    receiptStatus = OBR_ReceiptRequestStatus(receiptPath, requestId, requestChecksum)
    If receiptStatus = "MATCH" Then
        OBR_SuccessReceiptExists = True
        Exit Function
    End If
    If Len(receiptStatus) > 0 Then
        Err.Raise vbObjectError + 7817, OBR_MODULE_NAME, "Receipt path is not a matching successful receipt: " & receiptPath
    End If
End Function

Private Function OBR_ReceiptIsSuccessfulRequest(ByVal receiptPath As String, ByVal requestId As String, ByVal requestChecksum As String) As Boolean
    Dim receiptRow As Variant

    On Error Resume Next
    receiptRow = ReadSingleCsvRecord(receiptPath, OBR_ReceiptColumns())
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If
    On Error GoTo 0
    OBR_ReceiptIsSuccessfulRequest = OBR_ReceiptRowIsSuccessfulRequest(receiptRow, requestId, requestChecksum)
End Function

Private Function OBR_ReceiptIsSuccessfulSubmit(ByVal receiptPath As String, ByVal requestId As String) As Boolean
    Dim receiptRow As Variant

    On Error Resume Next
    receiptRow = ReadSingleCsvRecord(receiptPath, OBR_ReceiptColumns())
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If
    On Error GoTo 0
    OBR_ReceiptIsSuccessfulSubmit = OBR_ReceiptRowIsSuccessfulSubmit(receiptRow, requestId)
End Function

Private Function OBR_ReceiptRequestStatus(ByVal receiptPath As String, ByVal requestId As String, ByVal requestChecksum As String) As String
    Dim receiptRow As Variant
    Dim receiptChecksum As String

    If Not FileExists(receiptPath) Then Exit Function

    On Error Resume Next
    receiptRow = ReadSingleCsvRecord(receiptPath, OBR_ReceiptColumns())
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        OBR_ReceiptRequestStatus = "FAILED"
        Exit Function
    End If
    On Error GoTo 0

    If StrComp(NormalizeText(receiptRow(OBR_REC_REQUEST_ID)), requestId, vbTextCompare) <> 0 Then
        OBR_ReceiptRequestStatus = "MISMATCH"
        Exit Function
    End If

    receiptChecksum = NormalizeText(receiptRow(OBR_REC_REQUEST_CHECKSUM))
    If Len(receiptChecksum) = 0 Then
        OBR_ReceiptRequestStatus = "FAILED"
        Exit Function
    End If
    If StrComp(receiptChecksum, requestChecksum, vbBinaryCompare) <> 0 Then
        OBR_ReceiptRequestStatus = "MISMATCH"
        Exit Function
    End If

    If OBR_ReceiptRowIsSuccessfulRequest(receiptRow, requestId, requestChecksum) Then
        OBR_ReceiptRequestStatus = "MATCH"
    Else
        OBR_ReceiptRequestStatus = "FAILED"
    End If
End Function

Private Function OBR_ReceiptChecksumAtPath(ByVal receiptPath As String) As String
    Dim receiptRow As Variant

    If Not FileExists(receiptPath) Then Exit Function

    On Error Resume Next
    receiptRow = ReadSingleCsvRecord(receiptPath, OBR_ReceiptColumns())
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        Exit Function
    End If
    On Error GoTo 0
    OBR_ReceiptChecksumAtPath = NormalizeText(receiptRow(OBR_REC_CHECKSUM))
End Function

Private Function OBR_ReceiptRowIsSuccessfulRequest(ByVal receiptRow As Variant, ByVal requestId As String, ByVal requestChecksum As String) As Boolean
    Dim requestKind As String
    Dim receiptChecksum As String

    If StrComp(NormalizeText(receiptRow(OBR_REC_REQUEST_ID)), requestId, vbTextCompare) <> 0 Then Exit Function
    receiptChecksum = NormalizeText(receiptRow(OBR_REC_REQUEST_CHECKSUM))
    If Len(receiptChecksum) = 0 Then Exit Function
    If StrComp(receiptChecksum, requestChecksum, vbBinaryCompare) <> 0 Then Exit Function
    If StrComp(NormalizeText(receiptRow(OBR_REC_BRIDGE_STATUS)), "ACCEPTED", vbTextCompare) <> 0 Then Exit Function
    If Len(NormalizeText(receiptRow(OBR_REC_ERROR_CODE))) > 0 Then Exit Function

    requestKind = UCase$(NormalizeText(receiptRow(OBR_REC_REQUEST_KIND)))
    If requestKind = "SUBMIT" Then
        If StrComp(NormalizeText(receiptRow(OBR_REC_RESULT)), "ACCEPTED", vbTextCompare) <> 0 Then Exit Function
        If StrComp(NormalizeText(receiptRow(OBR_REC_RSS_ORDER_STATUS)), OBR_ValidStatusText(), vbTextCompare) <> 0 Then Exit Function
    ElseIf requestKind = "CANCEL" Then
        If StrComp(NormalizeText(receiptRow(OBR_REC_RESULT)), "CANCELED", vbTextCompare) <> 0 Then Exit Function
        If StrComp(NormalizeText(receiptRow(OBR_REC_RSS_ORDER_STATUS)), OBR_InvalidStatusText(), vbTextCompare) <> 0 Then Exit Function
    Else
        Exit Function
    End If

    OBR_ReceiptRowIsSuccessfulRequest = True
End Function

Private Function OBR_ReceiptRowIsSuccessfulSubmit(ByVal receiptRow As Variant, ByVal requestId As String) As Boolean
    If StrComp(NormalizeText(receiptRow(OBR_REC_REQUEST_ID)), requestId, vbTextCompare) <> 0 Then Exit Function
    If StrComp(NormalizeText(receiptRow(OBR_REC_REQUEST_KIND)), "SUBMIT", vbTextCompare) <> 0 Then Exit Function
    If StrComp(NormalizeText(receiptRow(OBR_REC_BRIDGE_STATUS)), "ACCEPTED", vbTextCompare) <> 0 Then Exit Function
    If StrComp(NormalizeText(receiptRow(OBR_REC_RESULT)), "ACCEPTED", vbTextCompare) <> 0 Then Exit Function
    If StrComp(NormalizeText(receiptRow(OBR_REC_RSS_ORDER_STATUS)), OBR_ValidStatusText(), vbTextCompare) <> 0 Then Exit Function
    If Len(NormalizeText(receiptRow(OBR_REC_RSS_ORDER_NUMBER))) = 0 Then Exit Function
    If Len(NormalizeText(receiptRow(OBR_REC_ERROR_CODE))) > 0 Then Exit Function
    If Len(NormalizeText(receiptRow(OBR_REC_REQUEST_CHECKSUM))) = 0 Then Exit Function
    OBR_ReceiptRowIsSuccessfulSubmit = True
End Function

Private Function OBR_LoadSubmitHistoryFields( _
    ByVal bridgeRoot As String, _
    ByVal brokerOrderId As String, _
    ByVal clientOrderId As String) As Variant

    Dim candidateIds As Variant
    Dim candidateId As Variant
    Dim candidatePaths As Variant
    Dim candidatePath As Variant
    Dim rowValues As Variant
    Dim loaded(0 To 5) As String

    candidateIds = Array("SUBMIT__" & brokerOrderId, "SUBMIT__" & clientOrderId)
    For Each candidateId In candidateIds
        candidatePaths = Array(OBR_BridgePath(bridgeRoot, OBR_INBOX_RELATIVE & "\" & CStr(candidateId) & ".csv"))
        For Each candidatePath In candidatePaths
            If FileExists(CStr(candidatePath)) Then
                On Error Resume Next
                rowValues = ReadSingleCsvRecord(CStr(candidatePath), OBR_ReceiptColumns())
                If Err.Number = 0 Then
                    If OBR_ReceiptRowIsSuccessfulSubmit(rowValues, CStr(candidateId)) Then
                        loaded(0) = NormalizeText(rowValues(OBR_REC_TICKER))
                        loaded(1) = NormalizeText(rowValues(OBR_REC_QUANTITY))
                        loaded(2) = NormalizeText(rowValues(OBR_REC_TARGET_PRICE))
                        loaded(3) = NormalizeText(rowValues(OBR_REC_STOP_PRICE))
                        loaded(4) = NormalizeText(rowValues(OBR_REC_EXPIRATION))
                        loaded(5) = NormalizeText(rowValues(OBR_REC_RSS_ORDER_NUMBER))
                        OBR_LoadSubmitHistoryFields = loaded
                        On Error GoTo 0
                        Exit Function
                    End If
                End If
                Err.Clear
                On Error GoTo 0
            End If
        Next candidatePath
    Next candidateId
End Function

Private Function OBR_MergeCancelRequestRow(ByVal requestRow As Variant, ByVal submitFields As Variant) As Variant
    Dim merged(0 To OBR_REQ_CHECKSUM) As String
    Dim index As Long

    For index = LBound(requestRow) To UBound(requestRow)
        merged(index) = NormalizeText(requestRow(index))
    Next index
    If Len(merged(OBR_REQ_TICKER)) = 0 Then merged(OBR_REQ_TICKER) = NormalizeText(submitFields(0))
    If Len(merged(OBR_REQ_QUANTITY)) = 0 Then merged(OBR_REQ_QUANTITY) = NormalizeText(submitFields(1))
    If Len(merged(OBR_REQ_TARGET_PRICE)) = 0 Then merged(OBR_REQ_TARGET_PRICE) = NormalizeText(submitFields(2))
    If Len(merged(OBR_REQ_STOP_PRICE)) = 0 Then merged(OBR_REQ_STOP_PRICE) = NormalizeText(submitFields(3))
    If Len(merged(OBR_REQ_EXPIRATION)) = 0 Then merged(OBR_REQ_EXPIRATION) = NormalizeText(submitFields(4))
    OBR_MergeCancelRequestRow = merged
End Function

Private Function OBR_SyntheticRequestRow(ByVal requestId As String, ByVal requestKind As String, ByVal brokerOrderId As String, ByVal clientOrderId As String) As Variant
    Dim row(0 To OBR_REQ_CHECKSUM) As String

    row(OBR_REQ_REQUEST_ID) = requestId
    row(OBR_REQ_REQUEST_KIND) = requestKind
    row(OBR_REQ_BROKER_ORDER_ID) = brokerOrderId
    row(OBR_REQ_CLIENT_ORDER_ID) = clientOrderId
    OBR_SyntheticRequestRow = row
End Function

Private Function OBR_BuildReceiptValues( _
    ByVal requestRow As Variant, _
    ByVal receivedAt As Date, _
    ByVal bridgeStatus As String, _
    ByVal resultValue As String, _
    ByVal rssOrderStatus As String, _
    ByVal rssOrderNumber As String, _
    ByVal message As String, _
    ByVal errorCode As String, _
    ByVal errorMessage As String) As Variant

    Dim receipt(0 To OBR_REC_CHECKSUM) As String

    receipt(OBR_REC_SCHEMA_VERSION) = CStr(1)
    receipt(OBR_REC_REQUEST_ID) = NormalizeText(requestRow(OBR_REQ_REQUEST_ID))
    receipt(OBR_REC_REQUEST_KIND) = UCase$(NormalizeText(requestRow(OBR_REQ_REQUEST_KIND)))
    receipt(OBR_REC_BROKER_ORDER_ID) = NormalizeText(requestRow(OBR_REQ_BROKER_ORDER_ID))
    receipt(OBR_REC_CLIENT_ORDER_ID) = NormalizeText(requestRow(OBR_REQ_CLIENT_ORDER_ID))
    receipt(OBR_REC_BRIDGE_STATUS) = UCase$(NormalizeText(bridgeStatus))
    receipt(OBR_REC_RESULT) = UCase$(NormalizeText(resultValue))
    receipt(OBR_REC_RSS_ORDER_STATUS) = rssOrderStatus
    receipt(OBR_REC_RSS_ORDER_NUMBER) = rssOrderNumber
    receipt(OBR_REC_TICKER) = NormalizeText(requestRow(OBR_REQ_TICKER))
    receipt(OBR_REC_QUANTITY) = NormalizeText(requestRow(OBR_REQ_QUANTITY))
    receipt(OBR_REC_TARGET_PRICE) = NormalizeText(requestRow(OBR_REQ_TARGET_PRICE))
    receipt(OBR_REC_STOP_PRICE) = NormalizeText(requestRow(OBR_REQ_STOP_PRICE))
    receipt(OBR_REC_EXPIRATION) = NormalizeText(requestRow(OBR_REQ_EXPIRATION))
    receipt(OBR_REC_TIMESTAMP) = Format$(receivedAt, "yyyy-mm-dd\THH:nn:ss") & "+09:00"
    If Len(message) > 0 Then
        receipt(OBR_REC_MESSAGE) = message
    ElseIf Len(errorMessage) > 0 Then
        receipt(OBR_REC_MESSAGE) = errorMessage
    Else
        receipt(OBR_REC_MESSAGE) = resultValue
    End If
    receipt(OBR_REC_ERROR_CODE) = errorCode
    If Len(errorMessage) > 0 Then
        receipt(OBR_REC_ERROR_MESSAGE) = errorMessage
    Else
        receipt(OBR_REC_ERROR_MESSAGE) = receipt(OBR_REC_MESSAGE)
    End If
    receipt(OBR_REC_FILL_QUANTITY) = "0"
    receipt(OBR_REC_FILL_PRICE) = "0.00"
    receipt(OBR_REC_ORDERS_SUBMITTED) = "0"
    receipt(OBR_REC_REQUEST_CHECKSUM) = NormalizeText(requestRow(OBR_REQ_CHECKSUM))
    receipt(OBR_REC_CHECKSUM) = OBR_ReceiptChecksumFromValues(receipt)
    OBR_BuildReceiptValues = receipt
End Function

Private Function OBR_RequestChecksumFromRow(ByVal rowValues As Variant) As String
    OBR_RequestChecksumFromRow = OBR_HashFromRow(OBR_RequestChecksumKeys(), OBR_RequestChecksumIndexes(), rowValues)
End Function

Private Function OBR_ReceiptChecksumFromValues(ByVal rowValues As Variant) As String
    OBR_ReceiptChecksumFromValues = OBR_HashFromRow(OBR_ReceiptChecksumKeys(), OBR_ReceiptChecksumIndexes(), rowValues)
End Function

Private Function OBR_HashFromRow(ByVal keys As Variant, ByVal indexes As Variant, ByVal rowValues As Variant) As String
    OBR_HashFromRow = Sha256HexUtf8(OBR_CanonicalJsonFromRow(keys, indexes, rowValues))
End Function

Private Function OBR_CanonicalJsonFromRow(ByVal keys As Variant, ByVal indexes As Variant, ByVal rowValues As Variant) As String
    Dim sortedKeys() As String
    Dim sortedValues() As String
    Dim parts() As String
    Dim count As Long
    Dim index As Long

    count = UBound(keys) - LBound(keys) + 1
    ReDim sortedKeys(0 To count - 1)
    ReDim sortedValues(0 To count - 1)
    For index = 0 To count - 1
        sortedKeys(index) = CStr(keys(LBound(keys) + index))
        sortedValues(index) = NormalizeText(rowValues(CLng(indexes(LBound(indexes) + index))))
    Next index
    OBR_SortParallelArrays sortedKeys, sortedValues
    ReDim parts(0 To count - 1)
    For index = 0 To count - 1
        parts(index) = """" & OBR_JsonEscape(sortedKeys(index)) & """:""" & OBR_JsonEscape(sortedValues(index)) & """"
    Next index
    OBR_CanonicalJsonFromRow = "{" & Join(parts, ",") & "}"
End Function

Private Sub OBR_SortParallelArrays(ByRef keys() As String, ByRef values() As String)
    Dim i As Long
    Dim j As Long
    Dim tempKey As String
    Dim tempValue As String

    For i = LBound(keys) To UBound(keys) - 1
        For j = i + 1 To UBound(keys)
            If StrComp(keys(i), keys(j), vbBinaryCompare) > 0 Then
                tempKey = keys(i)
                tempValue = values(i)
                keys(i) = keys(j)
                values(i) = values(j)
                keys(j) = tempKey
                values(j) = tempValue
            End If
        Next j
    Next i
End Sub

Private Function OBR_JsonEscape(ByVal value As String) As String
    Dim result As String
    Dim index As Long
    Dim character As String

    For index = 1 To Len(value)
        character = Mid$(value, index, 1)
        Select Case character
            Case """"
                result = result & Chr$(92) & Chr$(34)
            Case Chr$(92)
                result = result & "\\"
            Case vbBack
                result = result & "\b"
            Case vbFormFeed
                result = result & "\f"
            Case vbLf
                result = result & "\n"
            Case vbCr
                result = result & "\r"
            Case vbTab
                result = result & "\t"
            Case Else
                result = result & character
        End Select
    Next index
    OBR_JsonEscape = result
End Function

Private Function OBR_RequestColumns() As Variant
    OBR_RequestColumns = Array("schema_version", "request_id", "request_kind", "broker_order_id", "client_order_id", "strategy_name", "ticker", "side", "quantity", "order_type", "limit_price", "target_price", "stop_price", "stop_trigger_price", "order_category", "execution_condition", "expiration", "trigger_condition", "post_trigger_order_type", "live_trading_enabled", "production_transport_enabled", "armed", "submitted_at", "timeout_seconds", "macro_name", "message", "bridge_status", "payload_sha256", "checksum")
End Function

Private Function OBR_ReceiptColumns() As Variant
    OBR_ReceiptColumns = Array( _
        "schema_version", _
        "request_id", _
        "request_kind", _
        "broker_order_id", _
        "client_order_id", _
        "bridge_status", _
        "result", _
        "rss_order_status", _
        "rss_order_number", _
        "ticker", _
        "quantity", _
        "target_price", _
        "stop_price", _
        "expiration", _
        "timestamp", _
        "message", _
        "error_code", _
        "error_message", _
        "fill_quantity", _
        "fill_price", _
        "orders_submitted", _
        "request_checksum", _
        "checksum")
End Function

Private Function OBR_RequestChecksumKeys() As Variant
    OBR_RequestChecksumKeys = Array("schema_version", "request_id", "request_kind", "broker_order_id", "client_order_id", "strategy_name", "ticker", "side", "quantity", "order_type", "limit_price", "target_price", "stop_price", "stop_trigger_price", "order_category", "execution_condition", "expiration", "trigger_condition", "post_trigger_order_type", "live_trading_enabled", "production_transport_enabled", "armed", "submitted_at", "timeout_seconds", "macro_name", "message", "bridge_status", "payload_sha256")
End Function

Private Function OBR_RequestChecksumIndexes() As Variant
    OBR_RequestChecksumIndexes = Array(OBR_REQ_SCHEMA_VERSION, OBR_REQ_REQUEST_ID, OBR_REQ_REQUEST_KIND, OBR_REQ_BROKER_ORDER_ID, OBR_REQ_CLIENT_ORDER_ID, OBR_REQ_STRATEGY_NAME, OBR_REQ_TICKER, OBR_REQ_SIDE, OBR_REQ_QUANTITY, OBR_REQ_ORDER_TYPE, OBR_REQ_LIMIT_PRICE, OBR_REQ_TARGET_PRICE, OBR_REQ_STOP_PRICE, OBR_REQ_STOP_TRIGGER_PRICE, OBR_REQ_ORDER_CATEGORY, OBR_REQ_EXECUTION_CONDITION, OBR_REQ_EXPIRATION, OBR_REQ_TRIGGER_CONDITION, OBR_REQ_POST_TRIGGER_ORDER_TYPE, OBR_REQ_LIVE_TRADING_ENABLED, OBR_REQ_PRODUCTION_TRANSPORT_ENABLED, OBR_REQ_ARMED, OBR_REQ_SUBMITTED_AT, OBR_REQ_TIMEOUT_SECONDS, OBR_REQ_MACRO_NAME, OBR_REQ_MESSAGE, OBR_REQ_BRIDGE_STATUS, OBR_REQ_PAYLOAD_SHA256)
End Function

Private Function OBR_ReceiptChecksumKeys() As Variant
    OBR_ReceiptChecksumKeys = Array( _
        "schema_version", _
        "request_id", _
        "request_kind", _
        "broker_order_id", _
        "client_order_id", _
        "bridge_status", _
        "result", _
        "rss_order_status", _
        "rss_order_number", _
        "ticker", _
        "quantity", _
        "target_price", _
        "stop_price", _
        "expiration", _
        "timestamp", _
        "message", _
        "error_code", _
        "error_message", _
        "fill_quantity", _
        "fill_price", _
        "orders_submitted", _
        "request_checksum")
End Function

Private Function OBR_ReceiptChecksumIndexes() As Variant
    OBR_ReceiptChecksumIndexes = Array( _
        OBR_REC_SCHEMA_VERSION, _
        OBR_REC_REQUEST_ID, _
        OBR_REC_REQUEST_KIND, _
        OBR_REC_BROKER_ORDER_ID, _
        OBR_REC_CLIENT_ORDER_ID, _
        OBR_REC_BRIDGE_STATUS, _
        OBR_REC_RESULT, _
        OBR_REC_RSS_ORDER_STATUS, _
        OBR_REC_RSS_ORDER_NUMBER, _
        OBR_REC_TICKER, _
        OBR_REC_QUANTITY, _
        OBR_REC_TARGET_PRICE, _
        OBR_REC_STOP_PRICE, _
        OBR_REC_EXPIRATION, _
        OBR_REC_TIMESTAMP, _
        OBR_REC_MESSAGE, _
        OBR_REC_ERROR_CODE, _
        OBR_REC_ERROR_MESSAGE, _
        OBR_REC_FILL_QUANTITY, _
        OBR_REC_FILL_PRICE, _
        OBR_REC_ORDERS_SUBMITTED, _
        OBR_REC_REQUEST_CHECKSUM)
End Function

' Standalone helpers for single-module import.

Private Function NormalizeText(ByVal value As Variant) As String
    If IsError(value) Or IsEmpty(value) Or IsNull(value) Then Exit Function
    NormalizeText = Trim$(CStr(value))
    If LCase$(NormalizeText) = "nan" Then NormalizeText = ""
End Function

Private Function ValidateRequiredText(ByVal value As Variant, ByVal fieldName As String) As String
    Dim text As String

    text = NormalizeText(value)
    If Len(text) = 0 Then Err.Raise vbObjectError + 7804, OBR_MODULE_NAME, fieldName & " is missing"
    ValidateRequiredText = text
End Function

Private Function CurrentJst() As Date
    CurrentJst = Now
End Function

Private Function ParseJstTimestamp(ByVal value As Variant, ByVal fieldName As String) As Date
    Dim text As String

    text = ValidateRequiredText(value, fieldName)
    If Len(text) <> 25 Or Mid$(text, 20, 6) <> "+09:00" Then Err.Raise vbObjectError + 7805, OBR_MODULE_NAME, fieldName & " must use JST +09:00"
    On Error GoTo BadTimestamp
    ParseJstTimestamp = DateSerial(CInt(Mid$(text, 1, 4)), CInt(Mid$(text, 6, 2)), CInt(Mid$(text, 9, 2))) + TimeSerial(CInt(Mid$(text, 12, 2)), CInt(Mid$(text, 15, 2)), CInt(Mid$(text, 18, 2)))
    Exit Function
BadTimestamp:
    Err.Raise vbObjectError + 7806, OBR_MODULE_NAME, fieldName & " is invalid"
End Function

Private Function IsTruthyValue(ByVal value As Variant) As Boolean
    Dim text As String

    If IsError(value) Or IsEmpty(value) Or IsNull(value) Then Exit Function
    If VarType(value) = vbBoolean Then
        IsTruthyValue = CBool(value)
        Exit Function
    End If
    If IsNumeric(value) Then
        IsTruthyValue = (CDbl(value) <> 0)
        Exit Function
    End If
    text = UCase$(NormalizeText(value))
    Select Case text
        Case "TRUE", "YES", "Y", "ON", "1", "-1", OBR_ValidStatusText()
            IsTruthyValue = True
    End Select
End Function

Private Sub OBR_DeleteFileIfExists(ByVal path As String)
    If Len(path) = 0 Then Exit Sub
    If Not FileExists(path) Then Exit Sub
    On Error Resume Next
    Kill path
    On Error GoTo 0
End Sub

Private Function FileExists(ByVal path As String) As Boolean
    If Len(path) = 0 Then Exit Function
    FileExists = Len(Dir$(path)) > 0
End Function

Private Sub EnsureFolderTree(ByVal folderPath As String)
    Dim fso As Object
    Dim parentPath As String

    If Len(folderPath) = 0 Then Exit Sub
    Set fso = CreateObject("Scripting.FileSystemObject")
    If fso.FolderExists(folderPath) Then Exit Sub
    parentPath = fso.GetParentFolderName(folderPath)
    If Len(parentPath) > 0 And Not fso.FolderExists(parentPath) Then
        EnsureFolderTree parentPath
    End If
    If Not fso.FolderExists(folderPath) Then MkDir folderPath
End Sub

Private Function ParentFolderPath(ByVal filePath As String) As String
    Dim fso As Object

    If Len(filePath) = 0 Then Exit Function
    Set fso = CreateObject("Scripting.FileSystemObject")
    ParentFolderPath = fso.GetParentFolderName(filePath)
End Function

Private Function ReadUtf8TextFile(ByVal path As String) As String
    Dim stream As Object

    If Len(Dir$(path)) = 0 Then Exit Function
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 1
    stream.Open
    stream.LoadFromFile path
    stream.Position = 0
    stream.Type = 2
    stream.Charset = "utf-8"
    ReadUtf8TextFile = stream.ReadText(-1)
    stream.Close
End Function

Private Sub WriteUtf8TextFile(ByVal path As String, ByVal content As String)
    Dim stream As Object

    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2
    stream.Charset = "utf-8"
    stream.Open
    stream.WriteText content
    stream.SaveToFile path, 2
    stream.Close
End Sub

Private Function CsvEscape(ByVal value As String) As String
    CsvEscape = """" & Replace$(value, """", """""") & """"
End Function

Private Function CsvHeaderText(ByVal columns As Variant) As String
    CsvHeaderText = Join(columns, ",")
End Function

Private Function CsvRowText(ByVal values As Variant) As String
    Dim items() As String
    Dim index As Long

    ReDim items(LBound(values) To UBound(values))
    For index = LBound(values) To UBound(values)
        items(index) = CsvEscape(CStr(values(index)))
    Next index
    CsvRowText = Join(items, ",")
End Function

Private Function ParseCsvLine(ByVal line As String) As Variant
    Dim fields() As String
    Dim fieldValue As String
    Dim index As Long
    Dim character As String
    Dim inQuotes As Boolean

    ReDim fields(0 To 0)
    For index = 1 To Len(line)
        character = Mid$(line, index, 1)
        If character = """" Then
            If inQuotes And index < Len(line) And Mid$(line, index + 1, 1) = """" Then
                fieldValue = fieldValue & """"
                index = index + 1
            Else
                inQuotes = Not inQuotes
            End If
        ElseIf character = "," And Not inQuotes Then
            fields(UBound(fields)) = fieldValue
            fieldValue = ""
            ReDim Preserve fields(0 To UBound(fields) + 1)
        Else
            fieldValue = fieldValue & character
        End If
    Next index
    If inQuotes Then Err.Raise vbObjectError + 7813, OBR_MODULE_NAME, "CSV line has an unclosed quote"
    fields(UBound(fields)) = fieldValue
    ParseCsvLine = fields
End Function

Private Function NormalizeLineEndings(ByVal content As String) As String
    content = Replace$(content, vbCrLf, vbLf)
    content = Replace$(content, vbCr, vbLf)
    NormalizeLineEndings = content
End Function

Private Function ColumnsMatch(ByVal leftColumns As Variant, ByVal rightColumns As Variant) As Boolean
    Dim index As Long

    If (UBound(leftColumns) - LBound(leftColumns)) <> (UBound(rightColumns) - LBound(rightColumns)) Then Exit Function
    For index = LBound(leftColumns) To UBound(leftColumns)
        If CStr(leftColumns(index)) <> CStr(rightColumns(index)) Then Exit Function
    Next index
    ColumnsMatch = True
End Function

Private Function ReadSingleCsvRecord(ByVal path As String, ByVal expectedColumns As Variant) As Variant
    Dim text As String
    Dim lines As Variant
    Dim lineValue As Variant
    Dim rowCount As Long
    Dim headerRow As Variant
    Dim dataRow As Variant

    text = NormalizeLineEndings(ReadUtf8TextFile(path))
    lines = Split(text, vbLf)
    For Each lineValue In lines
        If Len(Trim$(CStr(lineValue))) > 0 Then
            rowCount = rowCount + 1
            If rowCount = 1 Then
                headerRow = ParseCsvLine(CStr(lineValue))
            ElseIf rowCount = 2 Then
                dataRow = ParseCsvLine(CStr(lineValue))
            Else
                Err.Raise vbObjectError + 7807, OBR_MODULE_NAME, "CSV must contain exactly one data row: " & path
            End If
        End If
    Next lineValue
    If rowCount <> 2 Then Err.Raise vbObjectError + 7807, OBR_MODULE_NAME, "CSV must contain exactly one data row: " & path
    If Not ColumnsMatch(headerRow, expectedColumns) Then Err.Raise vbObjectError + 7808, OBR_MODULE_NAME, "CSV columns do not match contract: " & path
    If (UBound(dataRow) - LBound(dataRow)) <> (UBound(expectedColumns) - LBound(expectedColumns)) Then Err.Raise vbObjectError + 7808, OBR_MODULE_NAME, "CSV columns do not match contract: " & path
    ReadSingleCsvRecord = dataRow
End Function

Private Sub WriteUtf8TextAtomic(ByVal path As String, ByVal content As String)
    Dim temporaryPath As String
    Dim result As Long

    EnsureFolderTree ParentFolderPath(path)
    temporaryPath = path & ".tmp"
    On Error GoTo CleanFail
    WriteUtf8TextFile temporaryPath, content
    result = MoveFileExW(StrPtr(temporaryPath), StrPtr(path), &H1 Or &H8)
    If result = 0 Then Err.Raise vbObjectError + 7809, OBR_MODULE_NAME, "Atomic replacement failed: " & path
    On Error Resume Next
    Kill temporaryPath
    On Error GoTo 0
    Exit Sub
CleanFail:
    On Error Resume Next
    Kill temporaryPath
    On Error GoTo 0
    Err.Raise Err.Number, Err.Source, Err.Description
End Sub

Private Sub WriteCsvRecordAtomic(ByVal path As String, ByVal columns As Variant, ByVal values As Variant)
    EnsureFolderTree ParentFolderPath(path)
    WriteUtf8TextAtomic path, CsvHeaderText(columns) & vbCrLf & CsvRowText(values) & vbCrLf
End Sub

Private Function IsHexDigest(ByVal value As String) As Boolean
    Dim index As Long
    Dim character As String

    If Len(value) <> 64 Then Exit Function
    For index = 1 To Len(value)
        character = Mid$(value, index, 1)
        If InStr(1, "0123456789abcdefABCDEF", character, vbBinaryCompare) = 0 Then Exit Function
    Next index
    IsHexDigest = True
End Function

Private Function Sha256HexUtf8(ByVal text As String) As String
    Dim utf8Bytes() As Byte
    Dim byteCount As Long
    Dim hashBytes(0 To 31) As Byte
    Dim hashLength As Long
    Dim hProv As LongPtr
    Dim hHash As LongPtr
    Dim providerName As String
    Dim errorNumber As Long
    Dim errorSource As String
    Dim errorDescription As String

    On Error GoTo FailHandler

    utf8Bytes = OBR_Utf8BytesFromText(text, byteCount)

    providerName = "Microsoft Enhanced RSA and AES Cryptographic Provider"
    If CryptAcquireContextW(hProv, 0, StrPtr(providerName), OBR_RSA_AES_PROV_TYPE, OBR_CRYPT_VERIFYCONTEXT) = 0 Then
        If CryptAcquireContextW(hProv, 0, 0, OBR_RSA_AES_PROV_TYPE, OBR_CRYPT_VERIFYCONTEXT) = 0 Then
            Err.Raise vbObjectError + 7810, OBR_MODULE_NAME, "SHA-256 context acquisition failed"
        End If
    End If

    If CryptCreateHash(hProv, OBR_CALG_SHA_256, 0, 0, hHash) = 0 Then
        Err.Raise vbObjectError + 7810, OBR_MODULE_NAME, "SHA-256 hash creation failed"
    End If

    If byteCount > 0 Then
        If CryptHashData(hHash, utf8Bytes(0), byteCount, 0) = 0 Then
            Err.Raise vbObjectError + 7810, OBR_MODULE_NAME, "SHA-256 hash update failed"
        End If
    End If

    hashLength = 32
    If CryptGetHashParam(hHash, OBR_HP_HASHVAL, hashBytes(0), hashLength, 0) = 0 Then
        Err.Raise vbObjectError + 7810, OBR_MODULE_NAME, "SHA-256 digest read failed"
    End If

    Sha256HexUtf8 = OBR_BytesToHexLower(hashBytes)

CleanExit:
    If hHash <> 0 Then CryptDestroyHash hHash
    If hProv <> 0 Then CryptReleaseContext hProv, 0
    If errorNumber <> 0 Then
        On Error GoTo 0
        Err.Raise errorNumber, errorSource, errorDescription
    End If
    Exit Function

FailHandler:
    errorNumber = Err.Number
    errorSource = Err.Source
    errorDescription = Err.Description
    Resume CleanExit
End Function

Private Function OBR_Utf8BytesFromText(ByVal text As String, ByRef byteCount As Long) As Byte()
    Dim bytes() As Byte
    Dim requiredBytes As Long

    If Len(text) = 0 Then
        byteCount = 0
        ReDim bytes(0 To 0)
        OBR_Utf8BytesFromText = bytes
        Exit Function
    End If

    requiredBytes = WideCharToMultiByte(OBR_UTF8_CODE_PAGE, 0, StrPtr(text), Len(text), 0, 0, 0, 0)
    If requiredBytes <= 0 Then Err.Raise vbObjectError + 7810, OBR_MODULE_NAME, "UTF-8 encoding failed"

    byteCount = requiredBytes
    ReDim bytes(0 To requiredBytes - 1)
    If WideCharToMultiByte(OBR_UTF8_CODE_PAGE, 0, StrPtr(text), Len(text), VarPtr(bytes(0)), requiredBytes, 0, 0) = 0 Then
        Err.Raise vbObjectError + 7810, OBR_MODULE_NAME, "UTF-8 encoding failed"
    End If
    OBR_Utf8BytesFromText = bytes
End Function

Private Function OBR_BytesToHexLower(ByRef bytes() As Byte) As String
    Dim index As Long
    Dim hexText As String

    For index = LBound(bytes) To UBound(bytes)
        hexText = hexText & Right$("0" & Hex$(bytes(index)), 2)
    Next index
    OBR_BytesToHexLower = LCase$(hexText)
End Function


## FILE: prompt_redundancy_validator.py

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Sequence

__all__ = ["RedundancyFinding", "RedundancyResult", "validate_prompt_redundancy"]

_LEADING_MARKERS_RE = re.compile(r"^(?:[-*•]+|\d+[.)])\s*")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"[。．\.！？!?]+|\n+")
_TRAILING_PUNCTUATION = " \t\r\n:：,，;；、。．.！？!?)]}>'\"`"
_LEADING_PUNCTUATION = " \t\r\n([<{`'\""


@dataclass(frozen=True)
class RedundancyFinding:
    rule: str
    left: str
    right: str
    detail: str


@dataclass(frozen=True)
class RedundancyResult:
    passed: bool
    findings: tuple[RedundancyFinding, ...]


def _normalize_unit(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace("\u3000", " ")
    normalized = normalized.strip()
    normalized = _LEADING_MARKERS_RE.sub("", normalized)
    normalized = normalized.strip(_LEADING_PUNCTUATION)
    normalized = normalized.strip(_TRAILING_PUNCTUATION)
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    return normalized


def _split_units(text: str) -> tuple[str, ...]:
    units: list[str] = []
    for raw_line in unicodedata.normalize("NFKC", text).splitlines():
        if not raw_line.strip():
            continue
        pieces = [piece for piece in _SENTENCE_SPLIT_RE.split(raw_line) if piece.strip()]
        if not pieces:
            pieces = [raw_line]
        for piece in pieces:
            normalized = _normalize_unit(piece)
            if normalized:
                units.append(normalized)
    return tuple(units)


def _contains_complete_overlap(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True
    left_units = set(_split_units(left))
    right_units = set(_split_units(right))
    if not left_units or not right_units:
        return False
    if left_units == right_units:
        return True
    return left_units.issubset(right_units) or right_units.issubset(left_units)


def validate_prompt_redundancy(
    prompt_text: str,
    agents_text: str,
    proof_targets: Sequence[str],
) -> RedundancyResult:
    findings: list[RedundancyFinding] = []

    prompt_units = _split_units(prompt_text)
    agents_units = _split_units(agents_text)
    for prompt_unit in prompt_units:
        for agents_unit in agents_units:
            if prompt_unit == agents_unit:
                findings.append(
                    RedundancyFinding(
                        rule="prompt_vs_agents",
                        left=prompt_unit,
                        right=agents_unit,
                        detail="normalized sentence matches AGENTS.md exactly",
                    )
                )
            elif prompt_unit and agents_unit and (
                prompt_unit in agents_unit or agents_unit in prompt_unit
            ):
                findings.append(
                    RedundancyFinding(
                        rule="prompt_vs_agents",
                        left=prompt_unit,
                        right=agents_unit,
                        detail="normalized sentence is a direct containment match with AGENTS.md",
                    )
                )

    seen_prompt_units: set[str] = set()
    for prompt_unit in prompt_units:
        if prompt_unit in seen_prompt_units:
            findings.append(
                RedundancyFinding(
                    rule="prompt_internal_duplicate",
                    left=prompt_unit,
                    right=prompt_unit,
                    detail="duplicate normalized constraint sentence in the same prompt",
                )
            )
        else:
            seen_prompt_units.add(prompt_unit)

    normalized_targets = tuple(_normalize_unit(target) for target in proof_targets if _normalize_unit(target))
    for index, left in enumerate(normalized_targets):
        for right in normalized_targets[index + 1 :]:
            if _contains_complete_overlap(left, right):
                findings.append(
                    RedundancyFinding(
                        rule="proof_target_overlap",
                        left=left,
                        right=right,
                        detail="one proof target fully contains the other",
                    )
                )

    return RedundancyResult(passed=not findings, findings=tuple(findings))


## FILE: tests/test_prompt_redundancy_validator.py

from __future__ import annotations

import unittest

from prompt_redundancy_validator import validate_prompt_redundancy


class PromptRedundancyValidatorTest(unittest.TestCase):
    def test_prompt_vs_agents_exact_or_near_exact_duplicate_fails(self) -> None:
        agents_text = "最初にAGENTS.mdを読む。\n他の行"
        prompt_text = "導入\n最初にAGENTS.mdを読む。\n結び"

        result = validate_prompt_redundancy(
            prompt_text=prompt_text,
            agents_text=agents_text,
            proof_targets=["alpha", "beta"],
        )

        self.assertFalse(result.passed)
        self.assertTrue(any(finding.rule == "prompt_vs_agents" for finding in result.findings))

    def test_duplicate_constraint_sentence_in_same_prompt_fails(self) -> None:
        prompt_text = "禁止: test\n禁止: test\n別の文"

        result = validate_prompt_redundancy(
            prompt_text=prompt_text,
            agents_text="まったく別のAGENTS内容",
            proof_targets=["alpha", "beta"],
        )

        self.assertFalse(result.passed)
        self.assertTrue(any(finding.rule == "prompt_internal_duplicate" for finding in result.findings))

    def test_proof_target_containment_fails(self) -> None:
        result = validate_prompt_redundancy(
            prompt_text="差し支えない文",
            agents_text="別のAGENTS",
            proof_targets=[
                "config のみを読む",
                "config のみを読む かつ 実行前に確認する",
                "完全に別",
            ],
        )

        self.assertFalse(result.passed)
        self.assertTrue(any(finding.rule == "proof_target_overlap" for finding in result.findings))

    def test_non_redundant_prompt_passes(self) -> None:
        result = validate_prompt_redundancy(
            prompt_text="A\nB\nC",
            agents_text="X\nY\nZ",
            proof_targets=["alpha", "beta", "gamma"],
        )

        self.assertTrue(result.passed)
        self.assertEqual((), result.findings)


if __name__ == "__main__":
    unittest.main()

