Attribute VB_Name = "PHOENIX_RSS_SHADOW_V1"
Option Explicit

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

Private Const CONTRACT_ID As String = "PHOENIX_RSS_SHADOW_V1"
Private Const SOURCE_ID As String = "RAKUTEN_MARKETSPEED_II_RSS"
Private Const EXPORTER_ID As String = "PHOENIX_EXCEL_VBA_SHADOW"
Private Const WORKBOOK_CONTRACT_VERSION As String = "1"
Private Const MOVEFILE_REPLACE_EXISTING As Long = &H1
Private Const MOVEFILE_WRITE_THROUGH As Long = &H8
Private Const MAX_ROWS As Long = 225

Public Sub ExportPhoenixRssShadowSnapshot()
    Dim sourceSheet As Worksheet
    Dim controlSheet As Worksheet
    Dim lastRow As Long
    Dim rowNumber As Long
    Dim sequence As Long
    Dim captureId As String
    Dim exportedAt As String
    Dim csvText As String
    Dim rootPath As String
    Dim inboxPath As String
    Dim targetPath As String
    Dim temporaryPath As String
    Dim fileSystem As Object
    Dim captureTime As Date

    If Len(ThisWorkbook.Path) = 0 Then
        Err.Raise vbObjectError + 2000, CONTRACT_ID, _
            "Save the workbook in the PHOENIX repository before exporting."
    End If
    Set sourceSheet = ThisWorkbook.Worksheets("RSS_SHADOW")
    Set controlSheet = ThisWorkbook.Worksheets("PHOENIX_CONTROL")
    lastRow = sourceSheet.Cells(sourceSheet.Rows.Count, "A").End(xlUp).Row
    If lastRow < 21 Or lastRow > MAX_ROWS + 1 Then
        Err.Raise vbObjectError + 2001, CONTRACT_ID, _
            "RSS_SHADOW must contain between 20 and 225 quote rows."
    End If
    captureTime = Now
    sequence = CLng(DateDiff("s", #1/1/2020#, captureTime))
    If IsNumeric(controlSheet.Range("B2").Value2) Then
        If CLng(controlSheet.Range("B2").Value2) >= sequence Then
            sequence = CLng(controlSheet.Range("B2").Value2) + 1
        End If
    End If
    If sequence < 1 Then
        Err.Raise vbObjectError + 2003, CONTRACT_ID, "Invalid sequence."
    End If

    exportedAt = FormatJstTimestamp(captureTime)
    captureId = "RSS_" & Format$(captureTime, "yyyymmdd_HHnnss") & "_" & CStr(sequence)
    csvText = SnapshotHeader() & vbCrLf
    For rowNumber = 2 To lastRow
        csvText = csvText & SnapshotRow( _
            sourceSheet, rowNumber, captureId, sequence, exportedAt) & vbCrLf
    Next rowNumber

    Set fileSystem = CreateObject("Scripting.FileSystemObject")
    rootPath = fileSystem.GetParentFolderName( _
        fileSystem.GetParentFolderName(ThisWorkbook.Path))
    If Len(Dir$(rootPath & "\config\v7_scheduler_config.json")) = 0 Then
        Err.Raise vbObjectError + 2005, CONTRACT_ID, _
            "Workbook must be saved under PHOENIX\runtime\v7_rss_shadow."
    End If
    inboxPath = rootPath & "\runtime\v7_rss_shadow\inbox"
    EnsureFolder rootPath & "\runtime"
    EnsureFolder rootPath & "\runtime\v7_rss_shadow"
    EnsureFolder inboxPath
    targetPath = inboxPath & "\current_snapshot.csv"
    temporaryPath = inboxPath & "\.current_snapshot." & captureId & ".tmp"
    WriteUtf8File temporaryPath, csvText
    If MoveFileExW(StrPtr(temporaryPath), StrPtr(targetPath), _
        MOVEFILE_REPLACE_EXISTING Or MOVEFILE_WRITE_THROUGH) = 0 Then
        On Error Resume Next
        Kill temporaryPath
        On Error GoTo 0
        Err.Raise vbObjectError + 2004, CONTRACT_ID, _
            "Atomic snapshot replacement failed."
    End If
    controlSheet.Range("B2").Value2 = sequence
    controlSheet.Range("B3").Value2 = captureId
    controlSheet.Range("B4").Value2 = exportedAt
End Sub

Private Function SnapshotHeader() As String
    SnapshotHeader = "schema_version,contract_id,source,exporter," & _
        "workbook_contract_version,read_only,orders_allowed," & _
        "external_orders_submitted,capture_id,sequence,exported_at," & _
        "ticker,current_price,bid,ask,volume,trading_status," & _
        "quote_timestamp,bid_timestamp,ask_timestamp"
End Function

Private Function SnapshotRow(ByVal sheet As Worksheet, ByVal rowNumber As Long, _
    ByVal captureId As String, ByVal sequence As Long, _
    ByVal exportedAt As String) As String
    Dim values(0 To 19) As String
    values(0) = "1"
    values(1) = CONTRACT_ID
    values(2) = SOURCE_ID
    values(3) = EXPORTER_ID
    values(4) = WORKBOOK_CONTRACT_VERSION
    values(5) = "true"
    values(6) = "false"
    values(7) = "0"
    values(8) = captureId
    values(9) = CStr(sequence)
    values(10) = exportedAt
    values(11) = RequiredText(sheet.Cells(rowNumber, "A").Value2, "ticker")
    values(12) = RequiredNumber(sheet.Cells(rowNumber, "B").Value2, "current_price")
    values(13) = RequiredNumber(sheet.Cells(rowNumber, "C").Value2, "bid")
    values(14) = RequiredNumber(sheet.Cells(rowNumber, "D").Value2, "ask")
    values(15) = RequiredInteger(sheet.Cells(rowNumber, "E").Value2, "volume")
    values(16) = RequiredText(sheet.Cells(rowNumber, "F").Value2, "trading_status")
    values(17) = FormatJstTimestamp(sheet.Cells(rowNumber, "G").Value)
    values(18) = FormatJstTimestamp(sheet.Cells(rowNumber, "H").Value)
    values(19) = FormatJstTimestamp(sheet.Cells(rowNumber, "I").Value)
    SnapshotRow = JoinCsv(values)
End Function

Private Function RequiredText(ByVal value As Variant, ByVal fieldName As String) As String
    If IsError(value) Or Len(Trim$(CStr(value))) = 0 Then
        Err.Raise vbObjectError + 2010, CONTRACT_ID, fieldName & " is blank or invalid."
    End If
    RequiredText = Trim$(CStr(value))
End Function

Private Function RequiredNumber(ByVal value As Variant, ByVal fieldName As String) As String
    If IsError(value) Or Not IsNumeric(value) Or CDbl(value) <= 0 Then
        Err.Raise vbObjectError + 2011, CONTRACT_ID, fieldName & " must be positive."
    End If
    RequiredNumber = Replace$(Format$(CDbl(value), "0.############"), ",", ".")
End Function

Private Function RequiredInteger(ByVal value As Variant, ByVal fieldName As String) As String
    If IsError(value) Or Not IsNumeric(value) Or CDbl(value) < 0 Or _
        CDbl(value) <> Fix(CDbl(value)) Then
        Err.Raise vbObjectError + 2012, CONTRACT_ID, fieldName & " must be a non-negative integer."
    End If
    RequiredInteger = Format$(CDbl(value), "0")
End Function

Private Function FormatJstTimestamp(ByVal value As Variant) As String
    If IsError(value) Or Not IsDate(value) Then
        Err.Raise vbObjectError + 2013, CONTRACT_ID, "RSS timestamp is missing or invalid."
    End If
    FormatJstTimestamp = Format$(CDate(value), "yyyy-mm-dd\THH:nn:ss") & "+09:00"
End Function

Private Function JoinCsv(ByRef values() As String) As String
    Dim index As Long
    Dim result As String
    For index = LBound(values) To UBound(values)
        If index > LBound(values) Then result = result & ","
        result = result & CsvCell(values(index))
    Next index
    JoinCsv = result
End Function

Private Function CsvCell(ByVal value As String) As String
    CsvCell = """" & Replace$(value, """", """""") & """"
End Function

Private Sub EnsureFolder(ByVal path As String)
    If Len(Dir$(path, vbDirectory)) = 0 Then MkDir path
End Sub

Private Sub WriteUtf8File(ByVal path As String, ByVal content As String)
    Dim stream As Object
    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 2
    stream.Charset = "utf-8"
    stream.Open
    stream.WriteText content
    stream.SaveToFile path, 2
    stream.Close
End Sub
