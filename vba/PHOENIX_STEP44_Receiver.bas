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

Public Sub RunPhoenixStep44LocalReceiver()
    Dim rootPath As String

    On Error GoTo CleanFail
    rootPath = FindRepositoryRoot(ThisWorkbook.Path)
    EnsureBridgeDirectories rootPath
    AcquireStep44Lock rootPath
    ProcessPendingOutboxFiles rootPath
CleanExit:
    ReleaseStep44Lock
    Exit Sub
CleanFail:
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
            Err.Description)
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
    currentPath = startPath
    Do
        If RepositoryLooksValid(currentPath) Then
            FindRepositoryRoot = currentPath
            Exit Function
        End If
        parentPath = fso.GetParentFolderName(currentPath)
        If Len(parentPath) = 0 Or parentPath = currentPath Then Exit Do
        currentPath = parentPath
    Loop

    Err.Raise vbObjectError + 4431, CONTRACT_ID, "Unable to resolve the PHOENIX repository root"
End Function

Private Function RepositoryLooksValid(ByVal rootPath As String) As Boolean
    RepositoryLooksValid = _
        FileExists(RepositoryPath(rootPath, "run_phoenix.py")) And _
        FileExists(RepositoryPath(rootPath, "AGENTS.md")) And _
        FileExists(RepositoryPath(rootPath, "phoenix_core\__init__.py"))
End Function

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
    ByVal note As String) As String

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
        """note"":" & JsonStringText(note) & "}"
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
    Dim fileStem As String

    resultValue = "ACCEPTED"
    reasonCodes = ""

    fileStem = FileStem(sourceFile)
    If NormalizeText(rowValues(OB_INTENT_ID)) <> fileStem Then
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

    currentTime = CurrentJst()
    processingPath = RepositoryPath(rootPath, PROCESSING_DIR) & "\" & FileStem(pendingFilePath) & ".csv"
    finalOutboxPath = processingPath
    MoveFileAtomic pendingFilePath, processingPath

    On Error GoTo ParseFailure
    outboxRow = ReadSingleCsvRecord(processingPath, OutboxColumns())
    normalizedRow = NormalizeOutboxRow(outboxRow)
    On Error GoTo 0

    intentId = NormalizeText(normalizedRow(OB_INTENT_ID))
    idempotencyKey = NormalizeText(normalizedRow(OB_IDEMPOTENCY_KEY))
    sourceChecksum = NormalizeText(normalizedRow(OB_CHECKSUM))
    Set stateRows = LoadStateRows(rootPath)

    latestIntentIndex = FindLatestStateRowIndex(stateRows, ST_INTENT_ID, intentId)
    latestIdemIndex = FindLatestStateRowIndex(stateRows, ST_IDEMPOTENCY_KEY, idempotencyKey)
    resultValue = ""
    reasonCodes = ""

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

    receiptRow = BuildReceiptRow(intentId, idempotencyKey, FormatJstTimestamp(currentTime), resultValue, reasonCodes, sourceChecksum)
    receiptPath = RepositoryPath(rootPath, INBOX_DIR) & "\" & intentId & ".csv"
    WriteCsvRecordAtomic receiptPath, ReceiptColumns(), receiptRow

    stateRow = BuildStateRow( _
        FormatJstTimestamp(currentTime), _
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

    If resultValue = "ACCEPTED" Then
        MoveFileAtomic processingPath, RepositoryPath(rootPath, COMPLETE_DIR) & "\" & FileStem(processingPath) & ".csv"
    Else
        MoveFileAtomic processingPath, RepositoryPath(rootPath, REJECTED_DIR) & "\" & FileStem(processingPath) & ".csv"
    End If

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
        "")
    AppendAuditJsonLine rootPath, auditLine
    Exit Sub

ParseFailure:
    corruptCount = corruptCount + 1
    On Error Resume Next
    AppendAuditJsonLine rootPath, BuildAuditJsonLine( _
        "receipt", _
        FormatJstTimestamp(CurrentJst()), _
        FileStem(pendingFilePath), _
        "", _
        "", _
        "CORRUPT", _
        "CSV_PARSE_FAILED", _
        pendingFilePath, _
        "", _
        processingPath, _
        VBA_INSTANCE_ID, _
        CStr(ORDERS_SUBMITTED), _
        Err.Description)
    MoveFileAtomic processingPath, RepositoryPath(rootPath, REJECTED_DIR) & "\" & FileStem(processingPath) & ".csv"
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
