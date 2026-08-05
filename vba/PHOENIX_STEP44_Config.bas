Attribute VB_Name = "PHOENIX_STEP44_Config"
Option Explicit
Option Private Module

Public Const CONTRACT_ID As String = "PHOENIX_STEP44_LOCAL_VBA_RECEIVER"
Public Const STEP_NAME As String = "PHOENIX v7 Step44"
Public Const SCHEMA_VERSION As Long = 1
Public Const TRADING_MODE As String = "PAPER"
Public Const EXECUTION_MODE As String = "DRY_RUN"
Public Const TRADING_ACTIONS As String = "DISABLED"
Public Const ORDERS_SUBMITTED As Long = 0
Public Const VBA_INSTANCE_ID As String = "PHOENIX_STEP44_VBA_LOCAL_RECEIVER"

Public Const PENDING_DIR As String = "runtime/v7_vba_bridge/outbox/pending"
Public Const PROCESSING_DIR As String = "runtime/v7_vba_bridge/outbox/processing"
Public Const COMPLETE_DIR As String = "runtime/v7_vba_bridge/outbox/complete"
Public Const REJECTED_DIR As String = "runtime/v7_vba_bridge/outbox/rejected"
Public Const INBOX_DIR As String = "runtime/v7_vba_bridge/inbox"
Public Const STATE_FILE As String = "state/v7_vba_bridge_step44_state.csv"
Public Const LOCK_FILE As String = "state/v7_vba_bridge_step44.lock"
Public Const AUDIT_FILE As String = "reports/v7_vba_bridge_step44_audit.jsonl"

Public Const MAX_FUTURE_SKEW_MINUTES As Long = 5

Public Const OB_SCHEMA_VERSION As Long = 0
Public Const OB_INTENT_ID As Long = 1
Public Const OB_IDEMPOTENCY_KEY As Long = 2
Public Const OB_GENERATED_AT As Long = 3
Public Const OB_EXPIRES_AT As Long = 4
Public Const OB_TICKER As Long = 5
Public Const OB_MARKET As Long = 6
Public Const OB_SIDE As Long = 7
Public Const OB_ORDER_TYPE As Long = 8
Public Const OB_QUANTITY As Long = 9
Public Const OB_REFERENCE_PRICE As Long = 10
Public Const OB_LIMIT_PRICE As Long = 11
Public Const OB_STOP_LOSS_PRICE As Long = 12
Public Const OB_TAKE_PROFIT_PRICE As Long = 13
Public Const OB_ESTIMATED_NOTIONAL As Long = 14
Public Const OB_ESTIMATED_MAX_LOSS As Long = 15
Public Const OB_TRADING_MODE As Long = 16
Public Const OB_EXECUTION_MODE As Long = 17
Public Const OB_BRIDGE_STATUS As Long = 18
Public Const OB_CHECKSUM As Long = 19

Public Const RC_SCHEMA_VERSION As Long = 0
Public Const RC_INTENT_ID As Long = 1
Public Const RC_IDEMPOTENCY_KEY As Long = 2
Public Const RC_RECEIVED_AT As Long = 3
Public Const RC_RESULT As Long = 4
Public Const RC_REASON_CODES As Long = 5
Public Const RC_VBA_INSTANCE_ID As Long = 6
Public Const RC_SOURCE_CHECKSUM As Long = 7
Public Const RC_ORDERS_SUBMITTED As Long = 8
Public Const RC_CHECKSUM As Long = 9

Public Const ST_RECORDED_AT As Long = 0
Public Const ST_INTENT_ID As Long = 1
Public Const ST_IDEMPOTENCY_KEY As Long = 2
Public Const ST_SOURCE_CHECKSUM As Long = 3
Public Const ST_STATUS As Long = 4
Public Const ST_RESULT As Long = 5
Public Const ST_REASON_CODES As Long = 6
Public Const ST_OUTBOX_FILE As Long = 7
Public Const ST_RECEIPT_FILE As Long = 8
Public Const ST_VBA_INSTANCE_ID As Long = 9
Public Const ST_ORDERS_SUBMITTED As Long = 10
Public Const ST_NOTE As Long = 11

Public Function RepositorySentinels() As Variant
    RepositorySentinels = Array("run_phoenix.py", "phoenix_core", "AGENTS.md")
End Function

Public Function OutboxColumns() As Variant
    OutboxColumns = Array( _
        "schema_version", _
        "intent_id", _
        "idempotency_key", _
        "generated_at", _
        "expires_at", _
        "ticker", _
        "market", _
        "side", _
        "order_type", _
        "quantity", _
        "reference_price", _
        "limit_price", _
        "stop_loss_price", _
        "take_profit_price", _
        "estimated_notional", _
        "estimated_max_loss", _
        "trading_mode", _
        "execution_mode", _
        "bridge_status", _
        "checksum" _
    )
End Function

Public Function ReceiptColumns() As Variant
    ReceiptColumns = Array( _
        "schema_version", _
        "intent_id", _
        "idempotency_key", _
        "received_at", _
        "result", _
        "reason_codes", _
        "vba_instance_id", _
        "source_checksum", _
        "orders_submitted", _
        "checksum" _
    )
End Function

Public Function StateColumns() As Variant
    StateColumns = Array( _
        "recorded_at", _
        "intent_id", _
        "idempotency_key", _
        "source_checksum", _
        "status", _
        "result", _
        "reason_codes", _
        "outbox_file", _
        "receipt_file", _
        "vba_instance_id", _
        "orders_submitted", _
        "note" _
    )
End Function

Public Function OutboxChecksumIndexes() As Variant
    OutboxChecksumIndexes = Array( _
        OB_BRIDGE_STATUS, _
        OB_ESTIMATED_MAX_LOSS, _
        OB_ESTIMATED_NOTIONAL, _
        OB_EXECUTION_MODE, _
        OB_EXPIRES_AT, _
        OB_GENERATED_AT, _
        OB_IDEMPOTENCY_KEY, _
        OB_INTENT_ID, _
        OB_LIMIT_PRICE, _
        OB_MARKET, _
        OB_ORDER_TYPE, _
        OB_QUANTITY, _
        OB_REFERENCE_PRICE, _
        OB_SIDE, _
        OB_SCHEMA_VERSION, _
        OB_STOP_LOSS_PRICE, _
        OB_TAKE_PROFIT_PRICE, _
        OB_TICKER, _
        OB_TRADING_MODE _
    )
End Function

Public Function ReceiptChecksumIndexes() As Variant
    ReceiptChecksumIndexes = Array( _
        RC_IDEMPOTENCY_KEY, _
        RC_INTENT_ID, _
        RC_ORDERS_SUBMITTED, _
        RC_REASON_CODES, _
        RC_RECEIVED_AT, _
        RC_RESULT, _
        RC_SCHEMA_VERSION, _
        RC_SOURCE_CHECKSUM, _
        RC_VBA_INSTANCE_ID _
    )
End Function

Public Function StateEventChecksumIndexes() As Variant
    StateEventChecksumIndexes = Array( _
        ST_IDEMPOTENCY_KEY, _
        ST_INTENT_ID, _
        ST_NOTE, _
        ST_ORDERS_SUBMITTED, _
        ST_REASON_CODES, _
        ST_RECORDED_AT, _
        ST_RESULT, _
        ST_SOURCE_CHECKSUM, _
        ST_STATUS, _
        ST_VBA_INSTANCE_ID _
    )
End Function

Public Function FinalStatuses() As Variant
    FinalStatuses = Array("ACCEPTED", "REJECTED", "DUPLICATE", "EXPIRED", "CORRUPT")
End Function
