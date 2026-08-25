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
    ArmedFalse As Boolean
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
    If Not OBR_BRIDGE_ARMED Then
        OBR_ReadBridgeReadyState readyState
        If Not readyState.Ready Then
            OBR_LogOrderBridgeEvent bridgeRoot, OBR_OBSERVABILITY_EVENT_READY_FALSE, "", OBR_OBSERVABILITY_READY_FALSE, OBR_ReadyFalseDetail(readyState)
            GoTo CleanExit
        End If
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

    mergedRow = OBR_MergeCancelRequestRow(requestRow, submitFields)
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
    readyState.ArmedFalse = Not IsTruthyValue(sheet.Range("B2").Value2)
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
    readyState.Ready = readyState.ExcelAlive And readyState.RssConnected And readyState.AddInReady And readyState.OrderTransportReady And readyState.ArmedFalse And (Not OBR_BRIDGE_ARMED) And ageSeconds >= 0 And ageSeconds <= OBR_HEARTBEAT_MAX_AGE_SECONDS
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
        "Armed/B2=" & OBR_BooleanText(readyState.ArmedFalse) & ";" & _
        "Ready=" & OBR_BooleanText(readyState.Ready)
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
    Dim loaded(0 To 4) As String

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
