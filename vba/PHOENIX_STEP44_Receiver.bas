Attribute VB_Name = "PHOENIX_STEP44_Receiver"
Option Explicit

' ADODB.Stream is used in the companion CSV module for local UTF-8 file I/O.

#If VBA7 Then
    Private Declare PtrSafe Function MoveFileExW Lib "kernel32" ( _
        ByVal lpExistingFileName As LongPtr, _
        ByVal lpNewFileName As LongPtr, _
        ByVal dwFlags As Long) As Long
#Else
    Private Declare Function MoveFileExW Lib "kernel32" ( _
        ByVal lpExistingFileName As Long, _
        ByVal lpNewFileName As Long, _
        ByVal dwFlags As Long) As Long
#End If

Private Const MOVEFILE_REPLACE_EXISTING As Long = &H1
Private Const MOVEFILE_WRITE_THROUGH As Long = &H8
Private Const STEP44_ONEDRIVE_WEB_PREFIX As String = "https://d.docs.live.net/"
Private Const STEP44_ONTIME_INTERVAL_SECONDS As Long = 30
Private Const STEP44_CANONICAL_FALLBACK_ROOT As String = "C:\Users\ashtc\OneDrive\デスクトップ\ちちのフォルダ\PHOENIX"

Private gStep44SchedulerArmed As Boolean
Private gStep44NextRunAt As Date
Private gStep44NextRunScheduled As Boolean
Private gStep44ConsumerRunning As Boolean

Public Sub StartPhoenixStep44ReceiverScheduler()
    PhoenixStep44StartScheduler
End Sub

Public Sub StopPhoenixStep44ReceiverScheduler()
    PhoenixStep44StopScheduler
End Sub

Private Function Step44OnTimeProcedureName() As String
    Step44OnTimeProcedureName = "'" & ThisWorkbook.Name & "'!RunPhoenixStep44LocalReceiver"
End Function

Private Sub PhoenixStep44StartScheduler()
    If gStep44SchedulerArmed Then Exit Sub
    gStep44SchedulerArmed = True
    PhoenixStep44ScheduleNextRun
End Sub

Private Sub PhoenixStep44StopScheduler()
    gStep44SchedulerArmed = False
    PhoenixStep44CancelScheduledRun
End Sub

Private Sub PhoenixStep44ScheduleNextRun()
    If Not gStep44SchedulerArmed Then Exit Sub
    PhoenixStep44CancelScheduledRun
    gStep44NextRunAt = DateAdd("s", STEP44_ONTIME_INTERVAL_SECONDS, Now)
    Application.OnTime EarliestTime:=gStep44NextRunAt, Procedure:=Step44OnTimeProcedureName(), Schedule:=True
    gStep44NextRunScheduled = True
End Sub

Private Sub PhoenixStep44CancelScheduledRun()
    If Not gStep44NextRunScheduled Then Exit Sub
    On Error Resume Next
    Application.OnTime EarliestTime:=gStep44NextRunAt, Procedure:=Step44OnTimeProcedureName(), Schedule:=False
    On Error GoTo 0
    gStep44NextRunAt = 0
    gStep44NextRunScheduled = False
End Sub

Private Sub Step44WriteTransportHeartbeat(ByVal heartbeatText As String)
    ThisWorkbook.Worksheets("PHOENIX_RSS_TRANSPORT").Range("J6").Value2 = heartbeatText
End Sub

Public Sub RunPhoenixStep44LocalReceiver()
    Dim rootPath As String
    Dim heartbeatText As String
    Dim currentStage As String
    Dim errorNumber As Long
    Dim errorSource As String
    Dim errorDescription As String
    Dim errorLine As Long
    Dim shouldReraise As Boolean

    On Error GoTo CleanFail
    If gStep44ConsumerRunning Then Exit Sub
    gStep44ConsumerRunning = True
    PhoenixStep44CancelScheduledRun
    currentStage = "RESOLVE_ROOT"
    rootPath = NormalizeRepositoryStartPath(ThisWorkbook.Path)
    rootPath = FindRepositoryRoot(rootPath)
    currentStage = "WRITE_HEARTBEAT"
    heartbeatText = FormatJstTimestamp(CurrentJst())
    Step44WriteTransportHeartbeat heartbeatText
    currentStage = "ENSURE_DIRECTORIES"
    EnsureBridgeDirectories rootPath
    currentStage = "ACQUIRE_LOCK"
    AcquireStep44Lock rootPath
    currentStage = "RECONCILE_FINAL"
    ReconcileFinalOutboxFiles rootPath
    currentStage = "RECONCILE_PROCESSING"
    ReconcileProcessingOutboxFiles rootPath
    currentStage = "PROCESS_PENDING"
    ProcessPendingOutboxFiles rootPath
CleanExit:
    ReleaseStep44Lock
    gStep44ConsumerRunning = False
    If gStep44SchedulerArmed Then
        PhoenixStep44ScheduleNextRun
    End If
    If shouldReraise Then
        Err.Raise errorNumber, errorSource, errorDescription
    End If
    Exit Sub
CleanFail:
    errorNumber = Err.Number
    errorSource = Err.Source
    errorDescription = Err.Description
    errorLine = Erl
    On Error Resume Next
    If Len(rootPath) > 0 Then
        AppendAuditJsonLine rootPath, BuildAuditJsonLine( _
            "fatal", _
            FormatJstTimestamp(CurrentJst()), _
            "", _
            "", _
            "", _
            "CORRUPT", _
            "RUN_FAILED", _
            "", _
            "", _
            "", _
            VBA_INSTANCE_ID, _
            "0", _
            "top_level_failure", _
            currentStage, _
            "", _
            CStr(errorNumber), _
            errorSource, _
            errorDescription, _
            CStr(errorLine))
    End If
    If Len(rootPath) = 0 Then
        shouldReraise = True
    End If
    On Error GoTo 0
    Resume CleanExit
End Sub

Private Function FindRepositoryRoot(ByVal startPath As String) As String
    Dim currentPath As String
    Dim parentPath As String
    Dim fso As Object

    If Len(startPath) = 0 Then
        Err.Raise vbObjectError + 4430, CONTRACT_ID, "This workbook must be saved before running Step44"
    End If

    Set fso = CreateObject("Scripting.FileSystemObject")
    currentPath = NormalizeRepositoryStartPath(startPath)
    Do
        If RepositoryLooksValid(currentPath) Then
            FindRepositoryRoot = currentPath
            Exit Function
        End If
        parentPath = fso.GetParentFolderName(currentPath)
        If Len(parentPath) = 0 Or parentPath = currentPath Then Exit Do
        currentPath = parentPath
    Loop

    If RepositoryLooksValid(STEP44_CANONICAL_FALLBACK_ROOT) Then
        FindRepositoryRoot = STEP44_CANONICAL_FALLBACK_ROOT
        Exit Function
    End If

    Err.Raise vbObjectError + 4431, CONTRACT_ID, "Unable to resolve the PHOENIX repository root"
End Function

Private Function NormalizeRepositoryStartPath(ByVal startPath As String) As String
    Dim relativePath As String
    Dim webPath As String
    Dim firstSlash As Long

    webPath = NormalizeText(startPath)
    If Len(webPath) = 0 Then Exit Function
    If StrComp(Left$(webPath, Len(STEP44_ONEDRIVE_WEB_PREFIX)), STEP44_ONEDRIVE_WEB_PREFIX, vbTextCompare) <> 0 Then
        NormalizeRepositoryStartPath = webPath
        Exit Function
    End If

    firstSlash = InStr(Len(STEP44_ONEDRIVE_WEB_PREFIX) + 1, webPath, "/", vbBinaryCompare)
    If firstSlash = 0 Then
        Err.Raise vbObjectError + 4432, CONTRACT_ID, "Unable to map OneDrive web path to a local folder"
    End If

    relativePath = Mid$(webPath, firstSlash + 1)
    If Len(relativePath) = 0 Then
        Err.Raise vbObjectError + 4432, CONTRACT_ID, "Unable to map OneDrive web path to a local folder"
    End If

    NormalizeRepositoryStartPath = OneDriveLocalRoot() & "\" & Replace$(relativePath, "/", "\")
End Function

Private Function OneDriveLocalRoot() As String
    Dim candidate As String
    Dim fso As Object

    candidate = NormalizeText(Environ$("OneDrive"))
    If Len(candidate) > 0 Then
        OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = NormalizeText(Environ$("OneDriveConsumer"))
    If Len(candidate) > 0 Then
        OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = NormalizeText(Environ$("OneDriveCommercial"))
    If Len(candidate) > 0 Then
        OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = NormalizeText(Environ$("USERPROFILE"))
    If Len(candidate) > 0 Then
        candidate = candidate & "\OneDrive"
        Set fso = CreateObject("Scripting.FileSystemObject")
        If fso.FolderExists(candidate) Then
            OneDriveLocalRoot = candidate
            Exit Function
        End If
    End If

    Err.Raise vbObjectError + 4433, CONTRACT_ID, "Unable to resolve the local OneDrive root"
End Function

Private Function RepositoryLooksValid(ByVal rootPath As String) As Boolean
    RepositoryLooksValid = _
        FileExists(RepositoryPath(rootPath, "run_phoenix.py")) And _
        FileExists(RepositoryPath(rootPath, "AGENTS.md")) And _
        FileExists(RepositoryPath(rootPath, "phoenix_core\__init__.py"))
End Function

Private Sub ReconcileFinalOutboxFiles(ByVal rootPath As String)
    Dim stateRows As Collection
    Dim completeFiles As Collection
    Dim rejectedFiles As Collection
    Dim filePath As Variant

    Set stateRows = LoadStateRows(rootPath)

    Set completeFiles = PendingCsvFiles(RepositoryPath(rootPath, COMPLETE_DIR))
    For Each filePath In completeFiles
        ReconcileFinalOutboxFile rootPath, stateRows, CStr(filePath), "ACCEPTED", "complete"
        Set stateRows = LoadStateRows(rootPath)
    Next filePath

    Set rejectedFiles = PendingCsvFiles(RepositoryPath(rootPath, REJECTED_DIR))
    For Each filePath In rejectedFiles
        ReconcileFinalOutboxFile rootPath, stateRows, CStr(filePath), "REJECTED", "rejected"
        Set stateRows = LoadStateRows(rootPath)
    Next filePath
End Sub

Private Sub ReconcileFinalOutboxFile( _
    ByVal rootPath As String, _
    ByVal stateRows As Collection, _
    ByVal finalFilePath As String, _
    ByVal fallbackResult As String, _
    ByVal finalFolderName As String)

    Dim intentId As String
    Dim requestRow As Variant
    Dim receiptPath As String
    Dim receiptRow As Variant
    Dim finalStateIndex As Long
    Dim sourceChecksum As String
    Dim idempotencyKey As String
    Dim resultValue As String
    Dim reasonCodes As String
    Dim note As String

    intentId = FileStem(finalFilePath)
    If Len(intentId) = 0 Then Exit Sub

    finalStateIndex = FindLatestFinalStateRowIndex(stateRows, ST_INTENT_ID, intentId)
    If finalStateIndex > 0 Then Exit Sub

    requestRow = ReadSingleCsvRecord(finalFilePath, OutboxColumns())
    idempotencyKey = NormalizeText(requestRow(OB_IDEMPOTENCY_KEY))
    sourceChecksum = NormalizeText(requestRow(OB_CHECKSUM))
    receiptPath = RepositoryPath(rootPath, INBOX_DIR) & "\" & intentId & ".csv"

    resultValue = fallbackResult
    reasonCodes = "RECOVERED_FROM_FINAL_FOLDER"
    note = "recovered_from_final_folder=" & finalFolderName

    If FileExists(receiptPath) Then
        receiptRow = ReadSingleCsvRecord(receiptPath, ReceiptColumns())
        If StrComp(NormalizeText(receiptRow(RC_INTENT_ID)), intentId, vbTextCompare) = 0 Then
            resultValue = UCase$(NormalizeText(receiptRow(RC_RESULT)))
            If Len(resultValue) = 0 Then resultValue = fallbackResult
            reasonCodes = NormalizeText(receiptRow(RC_REASON_CODES))
            sourceChecksum = NormalizeText(receiptRow(RC_SOURCE_CHECKSUM))
            If Len(sourceChecksum) = 0 Then sourceChecksum = NormalizeText(requestRow(OB_CHECKSUM))
            note = note & ";receipt_recovered=TRUE"
        Else
            Err.Raise vbObjectError + 4434, CONTRACT_ID, "Receipt intent mismatch during Step44 recovery: " & receiptPath
        End If
    Else
        note = note & ";receipt_missing=TRUE"
    End If

    AppendStateRow rootPath, BuildStateRow( _
        FormatJstTimestamp(CurrentJst()), _
        intentId, _
        idempotencyKey, _
        sourceChecksum, _
        resultValue, _
        resultValue, _
        reasonCodes, _
        finalFilePath, _
        receiptPath, _
        note)
End Sub

Private Sub ReconcileProcessingOutboxFiles(ByVal rootPath As String)
    Dim processingFolder As String
    Dim processingFiles As Collection
    Dim filePath As Variant
    Dim pendingPath As String

    processingFolder = RepositoryPath(rootPath, PROCESSING_DIR)
    Set processingFiles = PendingCsvFiles(processingFolder)
    For Each filePath In processingFiles
        pendingPath = RepositoryPath(rootPath, PENDING_DIR) & "\" & FileStem(CStr(filePath)) & ".csv"
        MoveFileAtomic CStr(filePath), pendingPath
    Next filePath
End Sub

Private Function PendingCsvFiles(ByVal folderPath As String) As Collection
    Dim fso As Object
    Dim folder As Object
    Dim fileItem As Object
    Dim values() As String
    Dim result As New Collection
    Dim count As Long
    Dim index As Long

    Set fso = CreateObject("Scripting.FileSystemObject")
    If Not fso.FolderExists(folderPath) Then
        Set PendingCsvFiles = result
        Exit Function
    End If

    Set folder = fso.GetFolder(folderPath)
    For Each fileItem In folder.Files
        If LCase$(fso.GetExtensionName(fileItem.Name)) = "csv" Then
            ReDim Preserve values(0 To count)
            values(count) = CStr(fileItem.Path)
            count = count + 1
        End If
    Next fileItem

    If count = 0 Then
        Set PendingCsvFiles = result
        Exit Function
    End If

    SortStringArray values
    For index = LBound(values) To UBound(values)
        result.Add values(index)
    Next index
    Set PendingCsvFiles = result
End Function

Private Sub SortStringArray(ByRef values() As String)
    Dim i As Long
    Dim j As Long
    Dim temp As String

    For i = LBound(values) To UBound(values) - 1
        For j = i + 1 To UBound(values)
            If StrComp(values(i), values(j), vbBinaryCompare) > 0 Then
                temp = values(i)
                values(i) = values(j)
                values(j) = temp
            End If
        Next j
    Next i
End Sub

Private Function FileStem(ByVal filePath As String) As String
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    FileStem = fso.GetBaseName(filePath)
End Function

Private Function MoveFileAtomic(ByVal sourcePath As String, ByVal destinationPath As String) As String
    Dim result As Long

    EnsureFolderTree ParentFolderPath(destinationPath)
    If FileExists(destinationPath) Then
        On Error Resume Next
        Kill destinationPath
        On Error GoTo 0
    End If
    result = MoveFileExW(StrPtr(sourcePath), StrPtr(destinationPath), MOVEFILE_REPLACE_EXISTING Or MOVEFILE_WRITE_THROUGH)
    If result = 0 Then
        Err.Raise vbObjectError + 4432, CONTRACT_ID, "Atomic move failed: " & sourcePath & " -> " & destinationPath
    End If
    MoveFileAtomic = destinationPath
End Function

Private Sub AddReason(ByRef reasonCodes As String, ByVal code As String)
    If Len(code) = 0 Then Exit Sub
    If Len(reasonCodes) = 0 Then
        reasonCodes = code
        Exit Sub
    End If
    If InStr(1, ";" & reasonCodes & ";", ";" & code & ";", vbTextCompare) = 0 Then
        reasonCodes = reasonCodes & ";" & code
    End If
End Sub

Private Function IsFinalStatus(ByVal status As String) As Boolean
    Select Case UCase$(NormalizeText(status))
        Case "ACCEPTED", "REJECTED", "DUPLICATE", "EXPIRED", "CORRUPT"
            IsFinalStatus = True
    End Select
End Function

Private Function FindLatestStateRowIndex(ByVal rows As Collection, ByVal columnIndex As Long, ByVal targetValue As String) As Long
    Dim index As Long
    Dim rowValues As Variant

    For index = rows.Count To 1 Step -1
        rowValues = rows.Item(index)
        If NormalizeText(rowValues(columnIndex)) = targetValue Then
            FindLatestStateRowIndex = index
            Exit Function
        End If
    Next index
End Function

Private Function BuildStateRow( _
    ByVal recordedAt As String, _
    ByVal intentId As String, _
    ByVal idempotencyKey As String, _
    ByVal sourceChecksum As String, _
    ByVal status As String, _
    ByVal resultValue As String, _
    ByVal reasonCodes As String, _
    ByVal outboxFile As String, _
    ByVal receiptFile As String, _
    ByVal note As String) As Variant

    Dim row(0 To 11) As String
    row(ST_RECORDED_AT) = recordedAt
    row(ST_INTENT_ID) = intentId
    row(ST_IDEMPOTENCY_KEY) = idempotencyKey
    row(ST_SOURCE_CHECKSUM) = sourceChecksum
    row(ST_STATUS) = status
    row(ST_RESULT) = resultValue
    row(ST_REASON_CODES) = reasonCodes
    row(ST_OUTBOX_FILE) = outboxFile
    row(ST_RECEIPT_FILE) = receiptFile
    row(ST_VBA_INSTANCE_ID) = VBA_INSTANCE_ID
    row(ST_ORDERS_SUBMITTED) = CStr(ORDERS_SUBMITTED)
    row(ST_NOTE) = note
    BuildStateRow = row
End Function

Private Function JsonEscapeText(ByVal value As String) As String
    Dim result As String
    Dim index As Long
    Dim character As String

    For index = 1 To Len(value)
        character = Mid$(value, index, 1)
        Select Case character
            Case """"
                result = result & """"
            Case "\"
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
    JsonEscapeText = result
End Function

Private Function JsonStringText(ByVal value As String) As String
    JsonStringText = """" & JsonEscapeText(value) & """"
End Function

Private Function BuildAuditJsonLine( _
    ByVal kind As String, _
    ByVal recordedAt As String, _
    ByVal intentId As String, _
    ByVal idempotencyKey As String, _
    ByVal sourceChecksum As String, _
    ByVal resultValue As String, _
    ByVal reasonCodes As String, _
    ByVal sourceFile As String, _
    ByVal receiptFile As String, _
    ByVal outboxFile As String, _
    ByVal readerId As String, _
    ByVal ordersSubmitted As String, _
    ByVal note As String, _
    Optional ByVal currentStage As String = "", _
    Optional ByVal currentFile As String = "", _
    Optional ByVal errorNumber As String = "", _
    Optional ByVal errorSource As String = "", _
    Optional ByVal errorDescription As String = "", _
    Optional ByVal errorLine As String = "") As String

    BuildAuditJsonLine = "{" & _
        """kind"":" & JsonStringText(kind) & "," & _
        """recorded_at"":" & JsonStringText(recordedAt) & "," & _
        """intent_id"":" & JsonStringText(intentId) & "," & _
        """idempotency_key"":" & JsonStringText(idempotencyKey) & "," & _
        """source_checksum"":" & JsonStringText(sourceChecksum) & "," & _
        """result"":" & JsonStringText(resultValue) & "," & _
        """reason_codes"":" & JsonStringText(reasonCodes) & "," & _
        """source_file"":" & JsonStringText(sourceFile) & "," & _
        """receipt_file"":" & JsonStringText(receiptFile) & "," & _
        """outbox_file"":" & JsonStringText(outboxFile) & "," & _
        """reader_id"":" & JsonStringText(readerId) & "," & _
        """orders_submitted"":" & JsonStringText(ordersSubmitted) & "," & _
        """note"":" & JsonStringText(note) & "," & _
        """current_stage"":" & JsonStringText(currentStage) & "," & _
        """current_file"":" & JsonStringText(currentFile) & "," & _
        """error_number"":" & JsonStringText(errorNumber) & "," & _
        """error_source"":" & JsonStringText(errorSource) & "," & _
        """error_description"":" & JsonStringText(errorDescription) & "," & _
        """error_line"":" & JsonStringText(errorLine) & "}"
End Function

Private Function JsonPropertyText(ByVal key As String, ByVal value As String) As String
    JsonPropertyText = JsonStringText(key) & ":" & JsonStringText(value)
End Function

Private Function FindLatestFinalStateRowIndex(ByVal rows As Collection, ByVal columnIndex As Long, ByVal targetValue As String) As Long
    Dim index As Long
    Dim rowValues As Variant

    For index = rows.Count To 1 Step -1
        rowValues = rows.Item(index)
        If NormalizeText(rowValues(columnIndex)) = targetValue Then
            If IsFinalStatus(rowValues(ST_STATUS)) Then
                FindLatestFinalStateRowIndex = index
                Exit Function
            End If
        End If
    Next index
End Function

Private Function CanonicalJsonFromOutboxRow(ByVal rowValues As Variant) As String
    Dim parts(0 To 18) As String

    parts(0) = JsonPropertyText("bridge_status", NormalizeText(rowValues(OB_BRIDGE_STATUS)))
    parts(1) = JsonPropertyText("estimated_max_loss", NormalizeText(rowValues(OB_ESTIMATED_MAX_LOSS)))
    parts(2) = JsonPropertyText("estimated_notional", NormalizeText(rowValues(OB_ESTIMATED_NOTIONAL)))
    parts(3) = JsonPropertyText("execution_mode", NormalizeText(rowValues(OB_EXECUTION_MODE)))
    parts(4) = JsonPropertyText("expires_at", NormalizeText(rowValues(OB_EXPIRES_AT)))
    parts(5) = JsonPropertyText("generated_at", NormalizeText(rowValues(OB_GENERATED_AT)))
    parts(6) = JsonPropertyText("idempotency_key", NormalizeText(rowValues(OB_IDEMPOTENCY_KEY)))
    parts(7) = JsonPropertyText("intent_id", NormalizeText(rowValues(OB_INTENT_ID)))
    parts(8) = JsonPropertyText("limit_price", NormalizeText(rowValues(OB_LIMIT_PRICE)))
    parts(9) = JsonPropertyText("market", NormalizeText(rowValues(OB_MARKET)))
    parts(10) = JsonPropertyText("order_type", NormalizeText(rowValues(OB_ORDER_TYPE)))
    parts(11) = JsonPropertyText("quantity", NormalizeText(rowValues(OB_QUANTITY)))
    parts(12) = JsonPropertyText("reference_price", NormalizeText(rowValues(OB_REFERENCE_PRICE)))
    parts(13) = JsonPropertyText("schema_version", NormalizeText(rowValues(OB_SCHEMA_VERSION)))
    parts(14) = JsonPropertyText("side", NormalizeText(rowValues(OB_SIDE)))
    parts(15) = JsonPropertyText("stop_loss_price", NormalizeText(rowValues(OB_STOP_LOSS_PRICE)))
    parts(16) = JsonPropertyText("take_profit_price", NormalizeText(rowValues(OB_TAKE_PROFIT_PRICE)))
    parts(17) = JsonPropertyText("ticker", NormalizeText(rowValues(OB_TICKER)))
    parts(18) = JsonPropertyText("trading_mode", NormalizeText(rowValues(OB_TRADING_MODE)))
    CanonicalJsonFromOutboxRow = "{" & Join(parts, ",") & "}"
End Function

Private Function CanonicalJsonFromReceiptRow(ByVal rowValues As Variant) As String
    Dim parts(0 To 8) As String

    parts(0) = JsonPropertyText("idempotency_key", NormalizeText(rowValues(RC_IDEMPOTENCY_KEY)))
    parts(1) = JsonPropertyText("intent_id", NormalizeText(rowValues(RC_INTENT_ID)))
    parts(2) = JsonPropertyText("orders_submitted", NormalizeText(rowValues(RC_ORDERS_SUBMITTED)))
    parts(3) = JsonPropertyText("reason_codes", NormalizeText(rowValues(RC_REASON_CODES)))
    parts(4) = JsonPropertyText("received_at", NormalizeText(rowValues(RC_RECEIVED_AT)))
    parts(5) = JsonPropertyText("result", NormalizeText(rowValues(RC_RESULT)))
    parts(6) = JsonPropertyText("schema_version", NormalizeText(rowValues(RC_SCHEMA_VERSION)))
    parts(7) = JsonPropertyText("source_checksum", NormalizeText(rowValues(RC_SOURCE_CHECKSUM)))
    parts(8) = JsonPropertyText("vba_instance_id", NormalizeText(rowValues(RC_VBA_INSTANCE_ID)))
    CanonicalJsonFromReceiptRow = "{" & Join(parts, ",") & "}"
End Function

Private Function IsHexDigestText(ByVal value As String) As Boolean
    Dim index As Long
    Dim character As String

    If Len(value) <> 64 Then Exit Function
    For index = 1 To Len(value)
        character = Mid$(value, index, 1)
        If InStr(1, "0123456789abcdefABCDEF", character, vbBinaryCompare) = 0 Then Exit Function
    Next index
    IsHexDigestText = True
End Function

Private Function Sha256HexUtf8(ByVal text As String) As String
    Dim shell As Object
    Dim environmentValues As Object
    Dim execObject As Object
    Dim command As String
    Dim stdoutText As String
    Dim lines As Variant
    Dim lineValue As Variant
    Dim index As Long

    Set shell = CreateObject("WScript.Shell")
    Set environmentValues = shell.Environment("Process")
    environmentValues("PHOENIX_STEP44_HASH_INPUT") = text

    ' Inline PowerShell avoids temporary script execution-policy failures and keeps hashing self-contained.
    command = "powershell.exe -NoProfile -NonInteractive -Command ""$sha=[System.Security.Cryptography.SHA256]::Create(); try { $bytes=[System.Text.Encoding]::UTF8.GetBytes($env:PHOENIX_STEP44_HASH_INPUT); ($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join '' } finally { $sha.Dispose() }"""
    Set execObject = shell.Exec(command)
    stdoutText = execObject.StdOut.ReadAll

    On Error Resume Next
    environmentValues("PHOENIX_STEP44_HASH_INPUT") = ""
    On Error GoTo 0

    stdoutText = Replace$(Replace$(stdoutText, vbCrLf, vbLf), vbCr, vbLf)
    lines = Split(stdoutText, vbLf)
    For index = UBound(lines) To LBound(lines) Step -1
        lineValue = Trim$(CStr(lines(index)))
        If Len(lineValue) = 64 Then
            If IsHexDigestText(lineValue) Then
                Sha256HexUtf8 = LCase$(lineValue)
                Exit Function
            End If
        End If
    Next index

    Err.Raise vbObjectError + 4419, CONTRACT_ID, "SHA-256 calculation failed"
End Function

Private Function NormalizeOutboxRow(ByVal rowValues As Variant) As Variant
    Dim row(0 To 19) As String

    row(OB_SCHEMA_VERSION) = ValidateRequiredText(rowValues(OB_SCHEMA_VERSION), "schema_version")
    row(OB_INTENT_ID) = ValidateRequiredText(rowValues(OB_INTENT_ID), "intent_id")
    row(OB_IDEMPOTENCY_KEY) = ValidateRequiredText(rowValues(OB_IDEMPOTENCY_KEY), "idempotency_key")
    row(OB_GENERATED_AT) = ValidateJstTimestampText(rowValues(OB_GENERATED_AT), "generated_at")
    row(OB_EXPIRES_AT) = ValidateJstTimestampText(rowValues(OB_EXPIRES_AT), "expires_at")
    row(OB_TICKER) = ValidateRequiredText(rowValues(OB_TICKER), "ticker")
    row(OB_MARKET) = ValidateRequiredText(rowValues(OB_MARKET), "market")
    row(OB_SIDE) = NormalizeUpperText(ValidateRequiredText(rowValues(OB_SIDE), "side"))
    row(OB_ORDER_TYPE) = NormalizeUpperText(ValidateRequiredText(rowValues(OB_ORDER_TYPE), "order_type"))
    row(OB_QUANTITY) = ValidatePositiveIntegerText(rowValues(OB_QUANTITY), "quantity")
    row(OB_REFERENCE_PRICE) = ValidatePositiveMoneyText(rowValues(OB_REFERENCE_PRICE), "reference_price")
    row(OB_LIMIT_PRICE) = ValidatePositiveMoneyText(rowValues(OB_LIMIT_PRICE), "limit_price")
    row(OB_STOP_LOSS_PRICE) = ValidatePositiveMoneyText(rowValues(OB_STOP_LOSS_PRICE), "stop_loss_price")
    row(OB_TAKE_PROFIT_PRICE) = ValidatePositiveMoneyText(rowValues(OB_TAKE_PROFIT_PRICE), "take_profit_price")
    row(OB_ESTIMATED_NOTIONAL) = ValidatePositiveMoneyText(rowValues(OB_ESTIMATED_NOTIONAL), "estimated_notional")
    row(OB_ESTIMATED_MAX_LOSS) = ValidatePositiveMoneyText(rowValues(OB_ESTIMATED_MAX_LOSS), "estimated_max_loss")
    row(OB_TRADING_MODE) = NormalizeUpperText(ValidateRequiredText(rowValues(OB_TRADING_MODE), "trading_mode"))
    row(OB_EXECUTION_MODE) = NormalizeUpperText(ValidateRequiredText(rowValues(OB_EXECUTION_MODE), "execution_mode"))
    row(OB_BRIDGE_STATUS) = NormalizeUpperText(ValidateRequiredText(rowValues(OB_BRIDGE_STATUS), "bridge_status"))
    row(OB_CHECKSUM) = LCase$(ValidateRequiredText(rowValues(OB_CHECKSUM), "checksum"))
    NormalizeOutboxRow = row
End Function

Private Sub EvaluateContractResult( _
    ByVal rowValues As Variant, _
    ByVal sourceFile As String, _
    ByVal currentTime As Date, _
    ByRef resultValue As String, _
    ByRef reasonCodes As String)

    Dim generatedAt As Date
    Dim expiresAt As Date
    Dim computedChecksum As String
    Dim sourceFileStem As String

    resultValue = "ACCEPTED"
    reasonCodes = ""

    sourceFileStem = FileStem(sourceFile)
    If NormalizeText(rowValues(OB_INTENT_ID)) <> sourceFileStem Then
        resultValue = "CORRUPT"
        AddReason reasonCodes, "INTENT_FILENAME_MISMATCH"
    End If

    If NormalizeText(rowValues(OB_SCHEMA_VERSION)) <> CStr(SCHEMA_VERSION) Then
        resultValue = "REJECTED"
        AddReason reasonCodes, "SCHEMA_VERSION_INVALID"
    End If
    If NormalizeText(rowValues(OB_TRADING_MODE)) <> TRADING_MODE Then
        resultValue = "REJECTED"
        AddReason reasonCodes, "TRADING_MODE_INVALID"
    End If
    If NormalizeText(rowValues(OB_EXECUTION_MODE)) <> EXECUTION_MODE Then
        resultValue = "REJECTED"
        AddReason reasonCodes, "EXECUTION_MODE_INVALID"
    End If
    If NormalizeText(rowValues(OB_BRIDGE_STATUS)) <> "PENDING" Then
        resultValue = "REJECTED"
        AddReason reasonCodes, "BRIDGE_STATUS_INVALID"
    End If

    On Error GoTo TimestampFailure
    generatedAt = ParseJstTimestamp(rowValues(OB_GENERATED_AT), "generated_at")
    expiresAt = ParseJstTimestamp(rowValues(OB_EXPIRES_AT), "expires_at")
    On Error GoTo 0

    If expiresAt <= generatedAt Then
        resultValue = "CORRUPT"
        AddReason reasonCodes, "EXPIRES_AT_INVALID"
    End If
    If generatedAt > DateAdd("n", MAX_FUTURE_SKEW_MINUTES, currentTime) Then
        resultValue = "CORRUPT"
        AddReason reasonCodes, "GENERATED_AT_FUTURE"
    End If
    If currentTime > expiresAt Then
        If resultValue <> "CORRUPT" Then resultValue = "EXPIRED"
        AddReason reasonCodes, "EXPIRED"
    End If

    computedChecksum = LCase$(Sha256HexUtf8(CanonicalJsonFromOutboxRow(rowValues)))
    If NormalizeText(rowValues(OB_CHECKSUM)) <> computedChecksum Then
        resultValue = "CORRUPT"
        AddReason reasonCodes, "CHECKSUM_MISMATCH"
    End If
    Exit Sub
TimestampFailure:
    resultValue = "CORRUPT"
    AddReason reasonCodes, "TIMESTAMP_INVALID"
    On Error GoTo 0
End Sub

Private Function BuildReceiptRow( _
    ByVal intentId As String, _
    ByVal idempotencyKey As String, _
    ByVal receivedAt As String, _
    ByVal resultValue As String, _
    ByVal reasonCodes As String, _
    ByVal sourceChecksum As String) As Variant

    Dim row(0 To 9) As String
    row(RC_SCHEMA_VERSION) = CStr(SCHEMA_VERSION)
    row(RC_INTENT_ID) = intentId
    row(RC_IDEMPOTENCY_KEY) = idempotencyKey
    row(RC_RECEIVED_AT) = receivedAt
    row(RC_RESULT) = UCase$(resultValue)
    row(RC_REASON_CODES) = reasonCodes
    row(RC_VBA_INSTANCE_ID) = VBA_INSTANCE_ID
    row(RC_SOURCE_CHECKSUM) = LCase$(sourceChecksum)
    row(RC_ORDERS_SUBMITTED) = CStr(ORDERS_SUBMITTED)
    row(RC_CHECKSUM) = LCase$(Sha256HexUtf8(CanonicalJsonFromReceiptRow(row)))
    BuildReceiptRow = row
End Function

Private Sub ProcessSingleOutboxFile( _
    ByVal rootPath As String, _
    ByVal pendingFilePath As String, _
    ByRef acceptedCount As Long, _
    ByRef rejectedCount As Long, _
    ByRef duplicateCount As Long, _
    ByRef expiredCount As Long, _
    ByRef corruptCount As Long)

    Dim processingPath As String
    Dim finalOutboxPath As String
    Dim outboxRow As Variant
    Dim normalizedRow As Variant
    Dim stateRows As Collection
    Dim currentTime As Date
    Dim intentId As String
    Dim idempotencyKey As String
    Dim sourceChecksum As String
    Dim resultValue As String
    Dim reasonCodes As String
    Dim latestIntentIndex As Long
    Dim latestIdemIndex As Long
    Dim latestRow As Variant
    Dim receiptRow As Variant
    Dim receiptPath As String
    Dim stateRow As Variant
    Dim auditLine As String
    Dim currentStage As String
    Dim currentFile As String
    Dim finalStateNote As String
    Dim fatalNote As String
    Dim cleanupNote As String
    Dim cleanupSourcePath As String
    Dim cleanupDestinationPath As String
    Dim fatalRecordedAt As String
    Dim fatalIntentId As String
    Dim fatalIdempotencyKey As String
    Dim fatalSourceChecksum As String
    Dim errorNumber As Long
    Dim errorSource As String
    Dim errorDescription As String
    Dim errorLine As Long
    Dim hasPriorFinalState As Boolean
    Dim hasPriorFinalStateChecked As Boolean
    Dim receiptWritten As Boolean

    On Error GoTo FatalFail
    currentStage = "MOVE_TO_PROCESSING"
    currentFile = pendingFilePath
    currentTime = CurrentJst()
    processingPath = RepositoryPath(rootPath, PROCESSING_DIR) & "\" & FileStem(pendingFilePath) & ".csv"
    finalOutboxPath = processingPath
    MoveFileAtomic pendingFilePath, processingPath
    currentFile = processingPath

    currentStage = "READ_CSV"
    outboxRow = ReadSingleCsvRecord(processingPath, OutboxColumns())

    currentStage = "NORMALIZE"
    normalizedRow = NormalizeOutboxRow(outboxRow)

    intentId = NormalizeText(normalizedRow(OB_INTENT_ID))
    idempotencyKey = NormalizeText(normalizedRow(OB_IDEMPOTENCY_KEY))
    sourceChecksum = NormalizeText(normalizedRow(OB_CHECKSUM))

    currentStage = "LOAD_STATE"
    Set stateRows = LoadStateRows(rootPath)

    currentStage = "WRITE_PROCESSING_STATE"
    AppendStateRow rootPath, BuildStateRow( _
        FormatJstTimestamp(currentTime), _
        intentId, _
        idempotencyKey, _
        sourceChecksum, _
        "PROCESSING", _
        "PROCESSING", _
        "ENTERED_PROCESSING", _
        processingPath, _
        "", _
        "working")

    currentStage = "VALIDATE_CONTRACT"
    resultValue = ""
    reasonCodes = ""
    latestIntentIndex = FindLatestFinalStateRowIndex(stateRows, ST_INTENT_ID, intentId)
    latestIdemIndex = FindLatestFinalStateRowIndex(stateRows, ST_IDEMPOTENCY_KEY, idempotencyKey)
    hasPriorFinalState = (latestIntentIndex > 0) Or (latestIdemIndex > 0)
    hasPriorFinalStateChecked = True

    If latestIntentIndex > 0 Then
        latestRow = stateRows.Item(latestIntentIndex)
        If Len(NormalizeText(latestRow(ST_SOURCE_CHECKSUM))) > 0 And NormalizeText(latestRow(ST_SOURCE_CHECKSUM)) <> sourceChecksum Then
            resultValue = "CORRUPT"
            AddReason reasonCodes, "STATE_INTENT_CHECKSUM_CONFLICT"
        ElseIf NormalizeText(latestRow(ST_IDEMPOTENCY_KEY)) <> idempotencyKey Then
            resultValue = "CORRUPT"
            AddReason reasonCodes, "STATE_INTENT_IDEMPOTENCY_CONFLICT"
        Else
            resultValue = "DUPLICATE"
            AddReason reasonCodes, "ALREADY_PROCESSED"
        End If
    End If

    If resultValue = "" And latestIdemIndex > 0 Then
        latestRow = stateRows.Item(latestIdemIndex)
        If NormalizeText(latestRow(ST_INTENT_ID)) <> intentId Then
            resultValue = "CORRUPT"
            AddReason reasonCodes, "STATE_IDEMPOTENCY_INTENT_CONFLICT"
        End If
    End If

    If resultValue = "" Then
        EvaluateContractResult normalizedRow, processingPath, currentTime, resultValue, reasonCodes
    End If

    If resultValue = "ACCEPTED" Then
        acceptedCount = acceptedCount + 1
    ElseIf resultValue = "REJECTED" Then
        rejectedCount = rejectedCount + 1
    ElseIf resultValue = "DUPLICATE" Then
        duplicateCount = duplicateCount + 1
    ElseIf resultValue = "EXPIRED" Then
        expiredCount = expiredCount + 1
    Else
        corruptCount = corruptCount + 1
    End If

    currentStage = "BUILD_RECEIPT"
    receiptRow = BuildReceiptRow(intentId, idempotencyKey, FormatJstTimestamp(currentTime), resultValue, reasonCodes, sourceChecksum)

    currentStage = "WRITE_RECEIPT"
    receiptPath = RepositoryPath(rootPath, INBOX_DIR) & "\" & intentId & ".csv"
    WriteCsvRecordAtomic receiptPath, ReceiptColumns(), receiptRow
    receiptWritten = True

    If resultValue = "ACCEPTED" Then
        finalOutboxPath = RepositoryPath(rootPath, COMPLETE_DIR) & "\" & FileStem(processingPath) & ".csv"
    Else
        finalOutboxPath = RepositoryPath(rootPath, REJECTED_DIR) & "\" & FileStem(processingPath) & ".csv"
    End If

    currentStage = "MOVE_TO_FINAL"
    MoveFileAtomic processingPath, finalOutboxPath
    currentFile = finalOutboxPath

    finalStateNote = ""
    If hasPriorFinalState Then
        finalStateNote = "prior_final_exists=TRUE"
    End If

    currentStage = "WRITE_FINAL_STATE"
    stateRow = BuildStateRow( _
        FormatJstTimestamp(CurrentJst()), _
        intentId, _
        idempotencyKey, _
        sourceChecksum, _
        UCase$(resultValue), _
        UCase$(resultValue), _
        reasonCodes, _
        finalOutboxPath, _
        receiptPath, _
        "finalized")
    AppendStateRow rootPath, stateRow

    currentStage = "WRITE_AUDIT"
    auditLine = BuildAuditJsonLine( _
        "receipt", _
        FormatJstTimestamp(currentTime), _
        intentId, _
        idempotencyKey, _
        sourceChecksum, _
        UCase$(resultValue), _
        reasonCodes, _
        pendingFilePath, _
        receiptPath, _
        finalOutboxPath, _
        VBA_INSTANCE_ID, _
        CStr(ORDERS_SUBMITTED), _
        finalStateNote, _
        currentStage, _
        currentFile, _
        "", _
        "", _
        "", _
        "")
    AppendAuditJsonLine rootPath, auditLine
    Exit Sub

FatalFail:
    errorNumber = Err.Number
    errorSource = Err.Source
    errorDescription = Err.Description
    errorLine = Erl
    fatalRecordedAt = FormatJstTimestamp(CurrentJst())
    fatalIntentId = intentId
    If Len(fatalIntentId) = 0 Then
        fatalIntentId = FileStem(pendingFilePath)
    End If
    fatalIdempotencyKey = idempotencyKey
    fatalSourceChecksum = sourceChecksum

    Err.Clear
    cleanupNote = ""
    On Error Resume Next
    If receiptWritten And UCase$(NormalizeText(resultValue)) = "ACCEPTED" Then
        If Len(receiptPath) > 0 And FileExists(receiptPath) Then
            Kill receiptPath
            If Err.Number <> 0 Then
                cleanupNote = cleanupNote & "receipt_cleanup_failed=" & CStr(Err.Number) & ";"
                Err.Clear
            Else
                cleanupNote = cleanupNote & "receipt_cleanup=DELETED;"
                Err.Clear
            End If
        End If
    End If

    cleanupSourcePath = currentFile
    If Len(cleanupSourcePath) = 0 Or Not FileExists(cleanupSourcePath) Then
        If Len(finalOutboxPath) > 0 And FileExists(finalOutboxPath) Then
            cleanupSourcePath = finalOutboxPath
        ElseIf Len(processingPath) > 0 And FileExists(processingPath) Then
            cleanupSourcePath = processingPath
        ElseIf Len(pendingFilePath) > 0 And FileExists(pendingFilePath) Then
            cleanupSourcePath = pendingFilePath
        End If
    End If

    If Len(cleanupSourcePath) > 0 Then
        cleanupDestinationPath = RepositoryPath(rootPath, REJECTED_DIR) & "\" & FileStem(cleanupSourcePath) & ".csv"
        If StrComp(NormalizeText(cleanupSourcePath), NormalizeText(cleanupDestinationPath), vbTextCompare) <> 0 Then
            MoveFileAtomic cleanupSourcePath, cleanupDestinationPath
            If Err.Number <> 0 Then
                cleanupNote = cleanupNote & "cleanup_move_failed=" & CStr(Err.Number) & ";"
                Err.Clear
            Else
                cleanupNote = cleanupNote & "cleanup_move=REJECTED;"
                Err.Clear
            End If
        Else
            cleanupNote = cleanupNote & "cleanup_move=SKIPPED_ALREADY_REJECTED;"
        End If
    Else
        cleanupNote = cleanupNote & "cleanup_move=SKIPPED_NO_SOURCE;"
    End If
    On Error GoTo 0

    Do While Len(cleanupNote) > 0 And Right$(cleanupNote, 1) = ";"
        cleanupNote = Left$(cleanupNote, Len(cleanupNote) - 1)
    Loop

    fatalNote = "stage=" & currentStage
    If Len(cleanupNote) > 0 Then
        fatalNote = fatalNote & ";" & cleanupNote
    End If
    If hasPriorFinalStateChecked And hasPriorFinalState Then
        fatalNote = fatalNote & ";prior_final_exists=TRUE"
    End If

    On Error Resume Next
    stateRow = BuildStateRow( _
        fatalRecordedAt, _
        fatalIntentId, _
        fatalIdempotencyKey, _
        fatalSourceChecksum, _
        "CORRUPT", _
        "RUN_FAILED", _
        "RUN_FAILED", _
        currentFile, _
        receiptPath, _
        fatalNote)
    AppendStateRow rootPath, stateRow
    If Err.Number <> 0 Then
        If Len(fatalNote) > 0 Then fatalNote = fatalNote & ";"
        fatalNote = fatalNote & "state_write_failed=" & CStr(Err.Number)
        Err.Clear
    End If
    On Error GoTo 0

    On Error Resume Next
    auditLine = BuildAuditJsonLine( _
        "fatal", _
        fatalRecordedAt, _
        fatalIntentId, _
        fatalIdempotencyKey, _
        fatalSourceChecksum, _
        "RUN_FAILED", _
        "RUN_FAILED", _
        pendingFilePath, _
        receiptPath, _
        currentFile, _
        VBA_INSTANCE_ID, _
        CStr(ORDERS_SUBMITTED), _
        fatalNote, _
        currentStage, _
        currentFile, _
        CStr(errorNumber), _
        errorSource, _
        errorDescription, _
        CStr(errorLine))
    AppendAuditJsonLine rootPath, auditLine
    On Error GoTo 0
End Sub

Private Sub ProcessPendingOutboxFiles(ByVal rootPath As String)
    Dim files As Collection
    Dim filePath As Variant
    Dim acceptedCount As Long
    Dim rejectedCount As Long
    Dim duplicateCount As Long
    Dim expiredCount As Long
    Dim corruptCount As Long

    Set files = PendingCsvFiles(RepositoryPath(rootPath, PENDING_DIR))
    For Each filePath In files
        ProcessSingleOutboxFile rootPath, CStr(filePath), acceptedCount, rejectedCount, duplicateCount, expiredCount, corruptCount
    Next filePath

    AppendAuditJsonLine rootPath, BuildAuditJsonLine( _
        "summary", _
        FormatJstTimestamp(CurrentJst()), _
        "", _
        "", _
        "", _
        "READY", _
        "", _
        "", _
        "", _
        "", _
        VBA_INSTANCE_ID, _
        CStr(ORDERS_SUBMITTED), _
        "accepted=" & CStr(acceptedCount) & ";rejected=" & CStr(rejectedCount) & ";duplicate=" & CStr(duplicateCount) & ";expired=" & CStr(expiredCount) & ";corrupt=" & CStr(corruptCount))
End Sub
