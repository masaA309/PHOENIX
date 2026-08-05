Attribute VB_Name = "PHOENIX_STEP44_State"
Option Explicit
Option Private Module

Private gLockHandle As Integer
Private gLockPath As String

Public Function RepositoryPath(ByVal rootPath As String, ByVal relativePath As String) As String
    If Right$(rootPath, 1) = "\" Then
        RepositoryPath = rootPath & relativePath
    Else
        RepositoryPath = rootPath & "\" & relativePath
    End If
End Function

Public Function StateFilePath(ByVal rootPath As String) As String
    StateFilePath = RepositoryPath(rootPath, STATE_FILE)
End Function

Public Function AuditFilePath(ByVal rootPath As String) As String
    AuditFilePath = RepositoryPath(rootPath, AUDIT_FILE)
End Function

Public Function LockFilePath(ByVal rootPath As String) As String
    LockFilePath = RepositoryPath(rootPath, LOCK_FILE)
End Function

Public Sub EnsureBridgeDirectories(ByVal rootPath As String)
    EnsureFolderTree RepositoryPath(rootPath, PENDING_DIR)
    EnsureFolderTree RepositoryPath(rootPath, PROCESSING_DIR)
    EnsureFolderTree RepositoryPath(rootPath, COMPLETE_DIR)
    EnsureFolderTree RepositoryPath(rootPath, REJECTED_DIR)
    EnsureFolderTree RepositoryPath(rootPath, INBOX_DIR)
    EnsureFolderTree ParentFolderPath(StateFilePath(rootPath))
    EnsureFolderTree ParentFolderPath(AuditFilePath(rootPath))
    EnsureFolderTree ParentFolderPath(LockFilePath(rootPath))
End Sub

Public Sub AcquireStep44Lock(ByVal rootPath As String)
    Dim metadata As String
    Dim lockPath As String

    lockPath = LockFilePath(rootPath)
    EnsureFolderTree ParentFolderPath(lockPath)
    gLockHandle = FreeFile
    On Error GoTo LockFail
    Open lockPath For Binary Access Write Lock Read Write As #gLockHandle
    metadata = "contract_id=" & CONTRACT_ID & vbCrLf & _
        "vba_instance_id=" & VBA_INSTANCE_ID & vbCrLf & _
        "started_at=" & FormatJstTimestamp(CurrentJst()) & vbCrLf
    Put #gLockHandle, , metadata
    gLockPath = lockPath
    Exit Sub
LockFail:
    gLockHandle = 0
    gLockPath = ""
    Err.Raise vbObjectError + 4422, CONTRACT_ID, "Step44 lock is already held or unavailable"
End Sub

Public Sub ReleaseStep44Lock()
    On Error Resume Next
    If gLockHandle <> 0 Then
        Close #gLockHandle
        gLockHandle = 0
    End If
    If Len(gLockPath) > 0 And FileExists(gLockPath) Then
        Kill gLockPath
    End If
    gLockPath = ""
    On Error GoTo 0
End Sub

Public Function LoadStateRows(ByVal rootPath As String) As Collection
    Dim path As String
    Dim rows As Collection
    Dim resultRows As New Collection
    Dim index As Long

    path = StateFilePath(rootPath)
    Set rows = ReadCsvRowsWithHeader(path, StateColumns())
    If rows.Count = 0 Then
        Set LoadStateRows = resultRows
        Exit Function
    End If
    For index = 2 To rows.Count
        resultRows.Add rows.Item(index)
    Next index
    Set LoadStateRows = resultRows
End Function

Public Sub AppendStateRow(ByVal rootPath As String, ByVal values As Variant)
    Dim path As String
    Dim content As String

    path = StateFilePath(rootPath)
    If FileExists(path) Then
        content = ReadUtf8TextFile(path)
        If Len(content) > 0 And Right$(content, 1) <> vbLf Then
            content = content & vbCrLf
        End If
        content = content & CsvRowText(values) & vbCrLf
    Else
        content = CsvHeaderText(StateColumns()) & vbCrLf & CsvRowText(values) & vbCrLf
    End If
    WriteUtf8TextAtomic path, content
End Sub

Public Sub AppendAuditJsonLine(ByVal rootPath As String, ByVal jsonLine As String)
    AppendUtf8TextAtomic AuditFilePath(rootPath), jsonLine & vbCrLf
End Sub
