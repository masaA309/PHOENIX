VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ThisWorkbook"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit

Private Sub Workbook_Open()
    Dim step44ErrorNumber As Long
    Dim step44ErrorSource As String
    Dim step44ErrorDescription As String
    Dim orderBridgeErrorNumber As Long
    Dim orderBridgeErrorSource As String
    Dim orderBridgeErrorDescription As String
    Dim startupErrorMessage As String

    On Error Resume Next
    StartPhoenixStep44ReceiverScheduler
    step44ErrorNumber = Err.Number
    step44ErrorSource = Err.Source
    step44ErrorDescription = Err.Description
    Err.Clear
    On Error GoTo 0

    On Error Resume Next
    StartPhoenixRssOrderBridgeScheduler
    orderBridgeErrorNumber = Err.Number
    orderBridgeErrorSource = Err.Source
    orderBridgeErrorDescription = Err.Description
    Err.Clear
    On Error GoTo 0

    If step44ErrorNumber <> 0 Then
        startupErrorMessage = startupErrorMessage & "Step44 start failed (" & CStr(step44ErrorNumber) & "): " & step44ErrorSource & " - " & step44ErrorDescription
    End If
    If orderBridgeErrorNumber <> 0 Then
        If Len(startupErrorMessage) > 0 Then startupErrorMessage = startupErrorMessage & " | "
        startupErrorMessage = startupErrorMessage & "Order Bridge start failed (" & CStr(orderBridgeErrorNumber) & "): " & orderBridgeErrorSource & " - " & orderBridgeErrorDescription
    End If
    If Len(startupErrorMessage) > 0 Then
        Err.Raise vbObjectError + 9101, "ThisWorkbook.Workbook_Open", startupErrorMessage
    End If
End Sub

Private Sub Workbook_BeforeClose(Cancel As Boolean)
    Dim orderBridgeErrorNumber As Long
    Dim orderBridgeErrorSource As String
    Dim orderBridgeErrorDescription As String
    Dim step44ErrorNumber As Long
    Dim step44ErrorSource As String
    Dim step44ErrorDescription As String
    Dim closeErrorMessage As String

    On Error Resume Next
    StopPhoenixRssOrderBridgeScheduler
    orderBridgeErrorNumber = Err.Number
    orderBridgeErrorSource = Err.Source
    orderBridgeErrorDescription = Err.Description
    Err.Clear
    On Error GoTo 0

    On Error Resume Next
    StopPhoenixStep44ReceiverScheduler
    step44ErrorNumber = Err.Number
    step44ErrorSource = Err.Source
    step44ErrorDescription = Err.Description
    Err.Clear
    On Error GoTo 0

    If orderBridgeErrorNumber <> 0 Then
        closeErrorMessage = closeErrorMessage & "Order Bridge stop failed (" & CStr(orderBridgeErrorNumber) & "): " & orderBridgeErrorSource & " - " & orderBridgeErrorDescription
    End If
    If step44ErrorNumber <> 0 Then
        If Len(closeErrorMessage) > 0 Then closeErrorMessage = closeErrorMessage & " | "
        closeErrorMessage = closeErrorMessage & "Step44 stop failed (" & CStr(step44ErrorNumber) & "): " & step44ErrorSource & " - " & step44ErrorDescription
    End If
    If Len(closeErrorMessage) > 0 Then
        Err.Raise vbObjectError + 9102, "ThisWorkbook.Workbook_BeforeClose", closeErrorMessage
    End If
End Sub
