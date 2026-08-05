Attribute VB_Name = "PHOENIX_STEP44_Csv"
Option Explicit
Option Private Module

#If VBA7 Then
    Private Declare PtrSafe Function MoveFileExW Lib "kernel32" ( _
        ByVal lpExistingFileName As LongPtr, _
        ByVal lpNewFileName As LongPtr, _
        ByVal dwFlags As Long) As Long

    Private Declare PtrSafe Sub GetSystemTime Lib "kernel32" ( _
        ByRef lpSystemTime As SYSTEMTIME)
#Else
    Private Declare Function MoveFileExW Lib "kernel32" ( _
        ByVal lpExistingFileName As Long, _
        ByVal lpNewFileName As Long, _
        ByVal dwFlags As Long) As Long

    Private Declare Sub GetSystemTime Lib "kernel32" ( _
        ByRef lpSystemTime As SYSTEMTIME)
#End If

Private Type SYSTEMTIME
    wYear As Integer
    wMonth As Integer
    wDayOfWeek As Integer
    wDay As Integer
    wHour As Integer
    wMinute As Integer
    wSecond As Integer
    wMilliseconds As Integer
End Type

Private Const MOVEFILE_REPLACE_EXISTING As Long = &H1
Private Const MOVEFILE_WRITE_THROUGH As Long = &H8

Public Function NormalizeText(ByVal value As Variant) As String
    If IsError(value) Or IsEmpty(value) Or IsNull(value) Then
        NormalizeText = ""
        Exit Function
    End If
    NormalizeText = Trim$(CStr(value))
    If LCase$(NormalizeText) = "nan" Then
        NormalizeText = ""
    End If
End Function

Public Function NormalizeUpperText(ByVal value As Variant) As String
    NormalizeUpperText = UCase$(NormalizeText(value))
End Function

Public Function ValidateRequiredText(ByVal value As Variant, ByVal fieldName As String) As String
    Dim text As String
    text = NormalizeText(value)
    If Len(text) = 0 Then
        Err.Raise vbObjectError + 4401, CONTRACT_ID, fieldName & " is missing"
    End If
    ValidateRequiredText = text
End Function

Public Function ValidatePositiveIntegerText(ByVal value As Variant, ByVal fieldName As String) As String
    Dim text As String
    Dim number As Double
    text = NormalizeText(value)
    If Len(text) = 0 Then Err.Raise vbObjectError + 4402, CONTRACT_ID, fieldName & " is missing"
    If LCase$(text) = "nan" Or LCase$(text) = "infinity" Or LCase$(text) = "+infinity" Or LCase$(text) = "-infinity" Then
        Err.Raise vbObjectError + 4403, CONTRACT_ID, fieldName & " is invalid"
    End If
    On Error GoTo BadNumber
    number = CDbl(Replace$(text, ",", ""))
    On Error GoTo 0
    If number <= 0 Or number <> Fix(number) Then
        Err.Raise vbObjectError + 4404, CONTRACT_ID, fieldName & " must be a positive integer"
    End If
    ValidatePositiveIntegerText = Format$(number, "0")
    Exit Function
BadNumber:
    Err.Raise vbObjectError + 4405, CONTRACT_ID, fieldName & " must be a positive integer"
End Function

Public Function ValidatePositiveMoneyText(ByVal value As Variant, ByVal fieldName As String) As String
    Dim text As String
    Dim number As Double
    text = NormalizeText(value)
    If Len(text) = 0 Then Err.Raise vbObjectError + 4406, CONTRACT_ID, fieldName & " is missing"
    text = Replace$(text, ",", "")
    If LCase$(text) = "nan" Or LCase$(text) = "infinity" Or LCase$(text) = "+infinity" Or LCase$(text) = "-infinity" Then
        Err.Raise vbObjectError + 4407, CONTRACT_ID, fieldName & " is invalid"
    End If
    On Error GoTo BadMoney
    number = CDbl(text)
    On Error GoTo 0
    If Not (number > 0#) Or number <> number Then
        Err.Raise vbObjectError + 4408, CONTRACT_ID, fieldName & " must be a positive number"
    End If
    ValidatePositiveMoneyText = Replace$(Format$(number, "0.00"), ",", ".")
    Exit Function
BadMoney:
    Err.Raise vbObjectError + 4409, CONTRACT_ID, fieldName & " must be a positive number"
End Function

Public Function ValidateNonNegativeIntegerText(ByVal value As Variant, ByVal fieldName As String) As String
    Dim text As String
    Dim number As Double
    text = NormalizeText(value)
    If Len(text) = 0 Then Err.Raise vbObjectError + 4410, CONTRACT_ID, fieldName & " is missing"
    On Error GoTo BadNumber
    number = CDbl(Replace$(text, ",", ""))
    On Error GoTo 0
    If number < 0 Or number <> Fix(number) Then
        Err.Raise vbObjectError + 4411, CONTRACT_ID, fieldName & " must be a non-negative integer"
    End If
    ValidateNonNegativeIntegerText = Format$(number, "0")
    Exit Function
BadNumber:
    Err.Raise vbObjectError + 4412, CONTRACT_ID, fieldName & " must be a non-negative integer"
End Function

Public Function CurrentUtc() As Date
    Dim systemTime As SYSTEMTIME
    GetSystemTime systemTime
    CurrentUtc = DateSerial(systemTime.wYear, systemTime.wMonth, systemTime.wDay) + _
        TimeSerial(systemTime.wHour, systemTime.wMinute, systemTime.wSecond)
End Function

Public Function CurrentJst() As Date
    CurrentJst = DateAdd("h", 9, CurrentUtc())
End Function

Public Function FormatJstTimestamp(ByVal value As Date) As String
    FormatJstTimestamp = Format$(value, "yyyy-mm-dd\THH:nn:ss") & "+09:00"
End Function

Public Function ParseJstTimestamp(ByVal value As Variant, ByVal fieldName As String) As Date
    Dim text As String
    text = ValidateRequiredText(value, fieldName)
    If Len(text) <> 25 Or Mid$(text, 20, 6) <> "+09:00" Then
        Err.Raise vbObjectError + 4413, CONTRACT_ID, fieldName & " must use JST +09:00"
    End If
    On Error GoTo BadTimestamp
    ParseJstTimestamp = DateSerial(CInt(Mid$(text, 1, 4)), CInt(Mid$(text, 6, 2)), CInt(Mid$(text, 9, 2))) + _
        TimeSerial(CInt(Mid$(text, 12, 2)), CInt(Mid$(text, 15, 2)), CInt(Mid$(text, 18, 2)))
    Exit Function
BadTimestamp:
    Err.Raise vbObjectError + 4414, CONTRACT_ID, fieldName & " is invalid"
End Function

Public Function ValidateJstTimestampText(ByVal value As Variant, ByVal fieldName As String) As String
    ValidateJstTimestampText = FormatJstTimestamp(ParseJstTimestamp(value, fieldName))
End Function

Public Function CsvEscape(ByVal value As String) As String
    CsvEscape = """" & Replace$(value, """", """""") & """"
End Function

Public Function CsvHeaderText(ByVal columns As Variant) As String
    CsvHeaderText = Join(columns, ",")
End Function

Public Function CsvRowText(ByVal values As Variant) As String
    Dim items() As String
    Dim index As Long
    ReDim items(LBound(values) To UBound(values))
    For index = LBound(values) To UBound(values)
        items(index) = CsvEscape(CStr(values(index)))
    Next index
    CsvRowText = Join(items, ",")
End Function

Public Function ParseCsvLine(ByVal line As String) As Variant
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

    fields(UBound(fields)) = fieldValue
    ParseCsvLine = fields
End Function

Private Function NormalizeLineEndings(ByVal content As String) As String
    content = Replace$(content, vbCrLf, vbLf)
    content = Replace$(content, vbCr, vbLf)
    NormalizeLineEndings = content
End Function

Public Function ReadUtf8TextFile(ByVal path As String) As String
    Dim stream As Object
    If Len(Dir$(path)) = 0 Then
        ReadUtf8TextFile = ""
        Exit Function
    End If
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

Public Sub EnsureFolderTree(ByVal folderPath As String)
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

Public Function ParentFolderPath(ByVal filePath As String) As String
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    ParentFolderPath = fso.GetParentFolderName(filePath)
End Function

Public Function FileExists(ByVal path As String) As Boolean
    FileExists = Len(Dir$(path)) > 0
End Function

Private Function ColumnsMatch(ByVal leftColumns As Variant, ByVal rightColumns As Variant) As Boolean
    Dim index As Long
    If (UBound(leftColumns) - LBound(leftColumns)) <> (UBound(rightColumns) - LBound(rightColumns)) Then Exit Function
    For index = LBound(leftColumns) To UBound(leftColumns)
        If CStr(leftColumns(index)) <> CStr(rightColumns(index)) Then Exit Function
    Next index
    ColumnsMatch = True
End Function

Public Function ReadCsvRows(ByVal path As String) As Collection
    Dim rows As Collection
    Dim content As String
    Dim normalized As String
    Dim lines As Variant
    Dim lineValue As Variant

    Set rows = New Collection
    content = ReadUtf8TextFile(path)
    If Len(content) = 0 Then
        Set ReadCsvRows = rows
        Exit Function
    End If

    normalized = NormalizeLineEndings(content)
    lines = Split(normalized, vbLf)
    For Each lineValue In lines
        If Len(Trim$(CStr(lineValue))) > 0 Then
            rows.Add ParseCsvLine(CStr(lineValue))
        End If
    Next lineValue
    Set ReadCsvRows = rows
End Function

Public Function ReadCsvRowsWithHeader(ByVal path As String, ByVal expectedColumns As Variant) As Collection
    Dim rows As Collection
    Dim header As Variant
    Set rows = ReadCsvRows(path)
    If rows.Count = 0 Then
        Set ReadCsvRowsWithHeader = rows
        Exit Function
    End If
    header = rows.Item(1)
    If Not ColumnsMatch(header, expectedColumns) Then
        Err.Raise vbObjectError + 4415, CONTRACT_ID, "CSV columns do not match contract: " & path
    End If
    Set ReadCsvRowsWithHeader = rows
End Function

Public Function ReadSingleCsvRecord(ByVal path As String, ByVal expectedColumns As Variant) As Variant
    Dim rows As Collection
    Set rows = ReadCsvRows(path)
    If rows.Count <> 2 Then
        Err.Raise vbObjectError + 4416, CONTRACT_ID, "CSV must contain exactly one data row: " & path
    End If
    If Not ColumnsMatch(rows.Item(1), expectedColumns) Then
        Err.Raise vbObjectError + 4417, CONTRACT_ID, "CSV columns do not match contract: " & path
    End If
    ReadSingleCsvRecord = rows.Item(2)
End Function

Public Sub WriteCsvRecordAtomic(ByVal path As String, ByVal columns As Variant, ByVal values As Variant)
    EnsureFolderTree ParentFolderPath(path)
    WriteUtf8TextAtomic path, CsvHeaderText(columns) & vbCrLf & CsvRowText(values) & vbCrLf
End Sub

Public Sub AppendUtf8TextAtomic(ByVal path As String, ByVal content As String)
    Dim existingText As String
    Dim combinedText As String

    EnsureFolderTree ParentFolderPath(path)
    existingText = ReadUtf8TextFile(path)
    If Len(existingText) > 0 Then
        combinedText = existingText
        If Right$(combinedText, 1) <> vbLf Then
            combinedText = combinedText & vbCrLf
        End If
        combinedText = combinedText & content
    Else
        combinedText = content
    End If
    WriteUtf8TextAtomic path, combinedText
End Sub

Public Sub WriteUtf8TextAtomic(ByVal path As String, ByVal content As String)
    Dim temporaryPath As String
    Dim result As Long

    EnsureFolderTree ParentFolderPath(path)
    temporaryPath = path & ".tmp"
    On Error GoTo CleanFail
    WriteUtf8TextFile temporaryPath, content
    result = MoveFileExW(StrPtr(temporaryPath), StrPtr(path), MOVEFILE_REPLACE_EXISTING Or MOVEFILE_WRITE_THROUGH)
    If result = 0 Then
        Err.Raise vbObjectError + 4418, CONTRACT_ID, "Atomic replacement failed: " & path
    End If
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

Public Function RowItem(ByVal rowValues As Variant, ByVal index As Long) As String
    RowItem = NormalizeText(rowValues(index))
End Function

Private Function JsonEscape(ByVal value As String) As String
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
    JsonEscape = result
End Function

Private Function JsonString(ByVal value As String) As String
    JsonString = """" & JsonEscape(value) & """"
End Function

Public Function CanonicalJsonFromOutboxRow(ByVal rowValues As Variant) As String
    Dim parts() As String
    Dim keys As Variant
    Dim index As Long

    keys = OutboxChecksumIndexes()
    ReDim parts(LBound(keys) To UBound(keys))
    For index = LBound(keys) To UBound(keys)
        parts(index) = JsonString(RowItem(rowValues, CLng(keys(index))))
    Next index
    CanonicalJsonFromOutboxRow = "{" & Join(parts, ",") & "}"
End Function

Public Function CanonicalJsonFromReceiptRow(ByVal rowValues As Variant) As String
    Dim parts() As String
    Dim keys As Variant
    Dim index As Long

    keys = ReceiptChecksumIndexes()
    ReDim parts(LBound(keys) To UBound(keys))
    For index = LBound(keys) To UBound(keys)
        parts(index) = JsonString(RowItem(rowValues, CLng(keys(index))))
    Next index
    CanonicalJsonFromReceiptRow = "{" & Join(parts, ",") & "}"
End Function

Public Function Sha256HexUtf8(ByVal text As String) As String
    Dim temporaryPath As String
    Dim scriptPath As String
    Dim scriptText As String
    Dim shell As Object
    Dim execObject As Object
    Dim command As String
    Dim stdoutText As String
    Dim lines As Variant
    Dim lineValue As Variant
    Dim index As Long

    temporaryPath = Environ$("TEMP") & "\phoenix_step44_hash_" & Format$(CurrentUtc(), "yyyymmdd_hhnnss") & "_" & CStr(CLng(Timer * 1000)) & ".txt"
    scriptPath = temporaryPath & ".ps1"
    WriteUtf8TextAtomic temporaryPath, text

    scriptText = ""
    scriptText = scriptText & "param([string]$Path)" & vbCrLf
    scriptText = scriptText & "$Text = Get-Content -Raw -Encoding UTF8 -LiteralPath $Path" & vbCrLf
    scriptText = scriptText & "$Sha = [System.Security.Cryptography.SHA256]::Create()" & vbCrLf
    scriptText = scriptText & "try {" & vbCrLf
    scriptText = scriptText & "  $Bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)" & vbCrLf
    scriptText = scriptText & "  $Hash = $Sha.ComputeHash($Bytes)" & vbCrLf
    scriptText = scriptText & "  ($Hash | ForEach-Object { $_.ToString('x2') }) -join ''" & vbCrLf
    scriptText = scriptText & "} finally {" & vbCrLf
    scriptText = scriptText & "  $Sha.Dispose()" & vbCrLf
    scriptText = scriptText & "}" & vbCrLf
    WriteUtf8TextAtomic scriptPath, scriptText

    command = "powershell.exe -NoProfile -NonInteractive -File """ & scriptPath & """ """ & temporaryPath & """"
    Set shell = CreateObject("WScript.Shell")
    Set execObject = shell.Exec(command)
    stdoutText = execObject.StdOut.ReadAll

    On Error Resume Next
    Kill temporaryPath
    Kill scriptPath
    On Error GoTo 0

    lines = Split(NormalizeLineEndings(stdoutText), vbLf)
    For index = UBound(lines) To LBound(lines) Step -1
        lineValue = Trim$(CStr(lines(index)))
        If Len(lineValue) = 64 Then
            If IsHexDigest(lineValue) Then
                Sha256HexUtf8 = LCase$(lineValue)
                Exit Function
            End If
        End If
    Next index
    Err.Raise vbObjectError + 4419, CONTRACT_ID, "SHA-256 calculation failed"
End Function

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
