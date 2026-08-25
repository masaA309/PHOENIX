Attribute VB_Name = "PHOENIX_VBA_DEPLOY_BOOTSTRAP"
Option Explicit

#If VBA7 Then
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
#Else
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
#End If

Private Const BOOT_MODULE_NAME As String = "PHOENIX_VBA_DEPLOY_BOOTSTRAP"
Private Const BOOT_TARGET_WORKBOOK_NAME As String = "PHOENIX_RSS_PRODUCTION.xlsm"
Private Const BOOT_TARGET_ORDER_BRIDGE As String = "PHOENIX_RSS_ORDER_BRIDGE"
Private Const BOOT_TARGET_THISWORKBOOK As String = "ThisWorkbook"
Private Const BOOT_CANONICAL_WORKBOOK_RELATIVE As String = "runtime\v7_rss_production\PHOENIX_RSS_PRODUCTION.xlsm"
Private Const BOOT_BOOTSTRAP_MANIFEST_RELATIVE As String = "runtime\v7_rss_production\PHOENIX_RSS_PRODUCTION.bootstrap_manifest.txt"
Private Const BOOT_BOOTSTRAP_BACKUP_RELATIVE As String = "backup\v7_rss_bootstrap\PHOENIX_RSS_PRODUCTION.bootstrap_backup.xlsm"
Private Const BOOT_ONEDRIVE_WEB_PREFIX As String = "https://d.docs.live.net/"
Private Const BOOT_RSA_AES_PROV_TYPE As Long = 24
Private Const BOOT_CRYPT_VERIFYCONTEXT As Long = &HF0000000
Private Const BOOT_CALG_SHA_256 As Long = &H800C&
Private Const BOOT_HP_HASHVAL As Long = &H2

Public Sub RunPhoenixVbaDeployBootstrap()
    Dim repositoryRoot As String
    Dim canonicalWorkbookPath As String
    Dim manifestPath As String
    Dim backupPath As String
    Dim sourceBodies As Object
    Dim manifest As Object
    Dim projectSnapshot As Object
    Dim vbproject As Object
    Dim originalEnableEvents As Boolean
    Dim originalDisplayAlerts As Boolean
    Dim originalScreenUpdating As Boolean
    Dim mutated As Boolean
    Dim failureNumber As Long
    Dim failureSource As String
    Dim failureDescription As String
    Dim rollbackSucceeded As Boolean

    On Error GoTo BOOT_Fail

    repositoryRoot = BOOT_FindRepositoryRoot(ThisWorkbook.Path)
    canonicalWorkbookPath = BOOT_CanonicalWorkbookPath(repositoryRoot)
    manifestPath = BOOT_BootstrapManifestPath(repositoryRoot)
    backupPath = BOOT_BootstrapBackupPath(repositoryRoot)
    BOOT_AssertCanonicalWorkbookIdentity canonicalWorkbookPath
    BOOT_AssertWorkbookReady

    Set vbproject = ThisWorkbook.VBProject
    BOOT_AssertBootstrapComponentUniqueness vbproject
    Set sourceBodies = BOOT_LoadSourceBodies(repositoryRoot)
    Set manifest = BOOT_LoadBootstrapManifest(manifestPath)
    BOOT_AssertPreparedArtifacts repositoryRoot, canonicalWorkbookPath, backupPath, manifest, sourceBodies
    Set projectSnapshot = BOOT_SnapshotProjectBodies(vbproject)

    originalEnableEvents = Application.EnableEvents
    originalDisplayAlerts = Application.DisplayAlerts
    originalScreenUpdating = Application.ScreenUpdating

    Application.EnableEvents = False
    Application.DisplayAlerts = False
    Application.ScreenUpdating = False

    BOOT_ApplyTargetBodies vbproject, sourceBodies
    mutated = True

    BOOT_VerifyDeployment vbproject, projectSnapshot, sourceBodies

    ThisWorkbook.Save
    If Not ThisWorkbook.Saved Then
        Err.Raise vbObjectError + 9102, BOOT_MODULE_NAME, "Workbook save did not complete"
    End If

    Debug.Print "DEPLOYED: YES"
    Debug.Print "BACKUP: " & backupPath
    GoTo BOOT_CleanExit

BOOT_Fail:
    failureNumber = Err.Number
    failureSource = Err.Source
    failureDescription = Err.Description

    If mutated Then
        On Error Resume Next
        BOOT_RestoreTargetBodies vbproject, projectSnapshot
        If Err.Number = 0 Then
            BOOT_VerifyRollback vbproject, projectSnapshot
        End If
        rollbackSucceeded = (Err.Number = 0)
        If Err.Number <> 0 Or Not rollbackSucceeded Then
            failureNumber = vbObjectError + 9103
            failureSource = BOOT_MODULE_NAME
            If Len(Err.Description) > 0 Then
                failureDescription = "Rollback failed: " & Err.Description
            Else
                failureDescription = "Rollback failed."
            End If
        End If
        On Error GoTo 0
    End If

    Debug.Print "DEPLOYED: NO"
    Err.Raise failureNumber, failureSource, failureDescription

BOOT_CleanExit:
    On Error Resume Next
    Application.EnableEvents = originalEnableEvents
    Application.DisplayAlerts = originalDisplayAlerts
    Application.ScreenUpdating = originalScreenUpdating
    On Error GoTo 0
End Sub

Private Function BOOT_CanonicalWorkbookPath(ByVal repositoryRoot As String) As String
    BOOT_CanonicalWorkbookPath = repositoryRoot & "\runtime\v7_rss_production\" & BOOT_TARGET_WORKBOOK_NAME
End Function

Private Function BOOT_BootstrapManifestPath(ByVal repositoryRoot As String) As String
    BOOT_BootstrapManifestPath = repositoryRoot & "\" & Replace$(BOOT_BOOTSTRAP_MANIFEST_RELATIVE, "/", "\")
End Function

Private Function BOOT_BootstrapBackupPath(ByVal repositoryRoot As String) As String
    BOOT_BootstrapBackupPath = repositoryRoot & "\" & Replace$(BOOT_BOOTSTRAP_BACKUP_RELATIVE, "/", "\")
End Function

Private Sub BOOT_AssertCanonicalWorkbookIdentity(ByVal canonicalWorkbookPath As String)
    Dim workbookPath As String

    If StrComp(ThisWorkbook.Name, BOOT_TARGET_WORKBOOK_NAME, vbTextCompare) <> 0 Then
        Err.Raise vbObjectError + 9104, BOOT_MODULE_NAME, "Workbook name mismatch: " & ThisWorkbook.Name
    End If

    workbookPath = BOOT_NormalizeRepositoryStartPath(ThisWorkbook.FullName)
    If StrComp(workbookPath, BOOT_NormalizeRepositoryStartPath(canonicalWorkbookPath), vbTextCompare) <> 0 Then
        Err.Raise vbObjectError + 9105, BOOT_MODULE_NAME, "Workbook path mismatch: " & workbookPath
    End If
End Sub

Private Sub BOOT_AssertWorkbookReady()
    If Len(ThisWorkbook.Path) = 0 Then
        Err.Raise vbObjectError + 9106, BOOT_MODULE_NAME, "Workbook must be saved before running the bootstrap"
    End If
    If ThisWorkbook.ReadOnly Then
        Err.Raise vbObjectError + 9107, BOOT_MODULE_NAME, "Workbook is read-only"
    End If
End Sub

Private Function BOOT_LoadBootstrapManifest(ByVal manifestPath As String) As Object
    Dim manifest As Object
    Dim rawLine As Variant
    Dim lineText As String
    Dim key As String
    Dim value As String
    Dim manifestText As String

    If Not BOOT_FileExists(manifestPath) Then
        Err.Raise vbObjectError + 9108, BOOT_MODULE_NAME, "Missing bootstrap manifest: " & manifestPath
    End If

    Set manifest = CreateObject("Scripting.Dictionary")
    manifest.CompareMode = 1
    manifestText = BOOT_ReadUtf8TextFile(manifestPath)
    For Each rawLine In Split(Replace$(Replace$(manifestText, vbCrLf, vbLf), vbCr, vbLf), vbLf)
        lineText = Trim$(CStr(rawLine))
        If Len(lineText) = 0 Then
            GoTo BOOT_LoadManifestNextLine
        End If
        If Left$(lineText, 1) = "#" Then
            GoTo BOOT_LoadManifestNextLine
        End If
        If InStr(1, lineText, "=", vbBinaryCompare) = 0 Then
            Err.Raise vbObjectError + 9109, BOOT_MODULE_NAME, "Invalid bootstrap manifest line: " & lineText
        End If
        key = Trim$(Left$(lineText, InStr(1, lineText, "=", vbBinaryCompare) - 1))
        value = Trim$(Mid$(lineText, InStr(1, lineText, "=", vbBinaryCompare) + 1))
        manifest(key) = value
BOOT_LoadManifestNextLine:
    Next rawLine

    Set BOOT_LoadBootstrapManifest = manifest
End Function

Private Sub BOOT_AssertPreparedArtifacts(ByVal repositoryRoot As String, ByVal canonicalWorkbookPath As String, ByVal backupPath As String, ByVal manifest As Object, ByVal sourceBodies As Object)
    Dim workbookPath As String

    BOOT_AssertBootstrapManifest manifest, canonicalWorkbookPath, backupPath
    workbookPath = BOOT_NormalizeRepositoryStartPath(ThisWorkbook.FullName)
    BOOT_AssertCurrentWorkbookHash workbookPath, BOOT_ManifestValue(manifest, "workbook_sha256")
    BOOT_AssertBackupHash backupPath, BOOT_ManifestValue(manifest, "backup_sha256")
    BOOT_AssertSourceHashes repositoryRoot, manifest
    If Not BOOT_FilesAreByteIdentical(workbookPath, backupPath) Then
        Err.Raise vbObjectError + 9110, BOOT_MODULE_NAME, "Prepared backup is not byte-identical to the workbook"
    End If

    BOOT_AssertContains CStr(sourceBodies(BOOT_TARGET_ORDER_BRIDGE)), "Public Sub RunPhoenixRssOrderBridgeConsumer()", "bridge source"
    BOOT_AssertContains CStr(sourceBodies(BOOT_TARGET_THISWORKBOOK)), "Private Sub Workbook_Open()", "ThisWorkbook source"
End Sub

Private Sub BOOT_AssertBootstrapManifest(ByVal manifest As Object, ByVal canonicalWorkbookPath As String, ByVal backupPath As String)
    BOOT_AssertManifestField manifest, "schema_version", "1", False
    BOOT_AssertManifestField manifest, "workbook_name", BOOT_TARGET_WORKBOOK_NAME, False
    BOOT_AssertManifestField manifest, "workbook_path", canonicalWorkbookPath, True
    BOOT_AssertManifestField manifest, "workbook_sha256", "", False, True
    BOOT_AssertManifestField manifest, "backup_path", backupPath, True
    BOOT_AssertManifestField manifest, "backup_sha256", "", False, True
    BOOT_AssertManifestField manifest, "source_order_bridge_path", "vba\PHOENIX_RSS_ORDER_BRIDGE.bas", True
    BOOT_AssertManifestField manifest, "source_thisworkbook_path", "vba\ThisWorkbook.cls", True
    BOOT_AssertManifestField manifest, "bridge_armed", "False", False
    BOOT_AssertManifestField manifest, "real_order_calls", "absent", False

    If StrComp(BOOT_ManifestValue(manifest, "workbook_sha256"), BOOT_ManifestValue(manifest, "backup_sha256"), vbBinaryCompare) <> 0 Then
        Err.Raise vbObjectError + 9111, BOOT_MODULE_NAME, "Bootstrap manifest workbook and backup hashes do not match"
    End If
    If Len(BOOT_ManifestValue(manifest, "source_order_bridge_sha256")) = 0 Then
        Err.Raise vbObjectError + 9112, BOOT_MODULE_NAME, "Bootstrap manifest is missing the bridge source hash"
    End If
    If Len(BOOT_ManifestValue(manifest, "source_thisworkbook_sha256")) = 0 Then
        Err.Raise vbObjectError + 9113, BOOT_MODULE_NAME, "Bootstrap manifest is missing the ThisWorkbook source hash"
    End If
End Sub

Private Sub BOOT_AssertCurrentWorkbookHash(ByVal workbookPath As String, ByVal expectedSha256 As String)
    Dim currentSha256 As String

    currentSha256 = BOOT_FileSha256Hex(workbookPath)
    If StrComp(currentSha256, expectedSha256, vbBinaryCompare) <> 0 Then
        Err.Raise vbObjectError + 9114, BOOT_MODULE_NAME, "Current workbook SHA-256 mismatch"
    End If
End Sub

Private Sub BOOT_AssertBackupHash(ByVal backupPath As String, ByVal expectedSha256 As String)
    Dim backupSha256 As String

    backupSha256 = BOOT_FileSha256Hex(backupPath)
    If StrComp(backupSha256, expectedSha256, vbBinaryCompare) <> 0 Then
        Err.Raise vbObjectError + 9115, BOOT_MODULE_NAME, "Prepared backup SHA-256 mismatch"
    End If
End Sub

Private Sub BOOT_AssertSourceHashes(ByVal repositoryRoot As String, ByVal manifest As Object)
    Dim bridgePath As String
    Dim thisWorkbookPath As String

    bridgePath = repositoryRoot & "\vba\PHOENIX_RSS_ORDER_BRIDGE.bas"
    thisWorkbookPath = repositoryRoot & "\vba\ThisWorkbook.cls"

    If StrComp(BOOT_FileSha256Hex(bridgePath), BOOT_ManifestValue(manifest, "source_order_bridge_sha256"), vbBinaryCompare) <> 0 Then
        Err.Raise vbObjectError + 9116, BOOT_MODULE_NAME, "Bootstrap manifest bridge source SHA-256 is stale or invalid"
    End If
    If StrComp(BOOT_FileSha256Hex(thisWorkbookPath), BOOT_ManifestValue(manifest, "source_thisworkbook_sha256"), vbBinaryCompare) <> 0 Then
        Err.Raise vbObjectError + 9117, BOOT_MODULE_NAME, "Bootstrap manifest ThisWorkbook SHA-256 is stale or invalid"
    End If
End Sub

Private Sub BOOT_AssertBootstrapComponentUniqueness(ByVal vbproject As Object)
    Dim component As Object
    Dim componentName As String
    Dim exactMatches As Long
    Dim prefixMatches As Long

    For Each component In vbproject.VBComponents
        componentName = BOOT_ComponentName(component)
        If StrComp(componentName, BOOT_MODULE_NAME, vbTextCompare) = 0 Then
            exactMatches = exactMatches + 1
        End If
        If Len(componentName) >= Len(BOOT_MODULE_NAME) Then
            If StrComp(Left$(componentName, Len(BOOT_MODULE_NAME)), BOOT_MODULE_NAME, vbTextCompare) = 0 Then
                prefixMatches = prefixMatches + 1
            End If
        End If
    Next component

    If exactMatches <> 1 Or prefixMatches <> 1 Then
        Err.Raise vbObjectError + 9118, BOOT_MODULE_NAME, "Bootstrap module duplicate or auto-rename detected"
    End If
End Sub

Private Sub BOOT_AssertManifestField(ByVal manifest As Object, ByVal key As String, ByVal expectedValue As String, ByVal normalizePath As Boolean, Optional ByVal allowAnyNonEmpty As Boolean = False)
    Dim actualValue As String

    actualValue = BOOT_ManifestValue(manifest, key)
    If allowAnyNonEmpty Then
        If Len(actualValue) = 0 Then
            Err.Raise vbObjectError + 9116, BOOT_MODULE_NAME, "Bootstrap manifest value is empty: " & key
        End If
        Exit Sub
    End If

    If normalizePath Then
        If StrComp(BOOT_NormalizePath(actualValue), BOOT_NormalizePath(expectedValue), vbTextCompare) <> 0 Then
            Err.Raise vbObjectError + 9117, BOOT_MODULE_NAME, "Bootstrap manifest mismatch for " & key & ": " & actualValue
        End If
    ElseIf StrComp(actualValue, expectedValue, vbBinaryCompare) <> 0 Then
        Err.Raise vbObjectError + 9118, BOOT_MODULE_NAME, "Bootstrap manifest mismatch for " & key & ": " & actualValue
    End If
End Sub

Private Function BOOT_ManifestValue(ByVal manifest As Object, ByVal key As String) As String
    If Not manifest.Exists(key) Then
        Err.Raise vbObjectError + 9119, BOOT_MODULE_NAME, "Bootstrap manifest key missing: " & key
    End If
    BOOT_ManifestValue = Trim$(CStr(manifest(key)))
End Function

Private Function BOOT_LoadSourceBodies(ByVal repositoryRoot As String) As Object
    Dim sourceBodies As Object
    Dim bridgePath As String
    Dim thisWorkbookPath As String
    Dim bridgeBody As String
    Dim thisWorkbookBody As String

    bridgePath = repositoryRoot & "\vba\PHOENIX_RSS_ORDER_BRIDGE.bas"
    thisWorkbookPath = repositoryRoot & "\vba\ThisWorkbook.cls"

    If Not BOOT_FileExists(bridgePath) Then
        Err.Raise vbObjectError + 9110, BOOT_MODULE_NAME, "Missing VBA source file: " & bridgePath
    End If
    If Not BOOT_FileExists(thisWorkbookPath) Then
        Err.Raise vbObjectError + 9111, BOOT_MODULE_NAME, "Missing VBA source file: " & thisWorkbookPath
    End If

    bridgeBody = BOOT_ExtractVbaCodeBody(BOOT_ReadUtf8TextFile(bridgePath))
    thisWorkbookBody = BOOT_ExtractVbaCodeBody(BOOT_ReadUtf8TextFile(thisWorkbookPath))

    BOOT_ValidateBridgeSource bridgeBody
    BOOT_ValidateThisWorkbookSource thisWorkbookBody

    Set sourceBodies = CreateObject("Scripting.Dictionary")
    sourceBodies.CompareMode = 1
    sourceBodies.Add BOOT_TARGET_ORDER_BRIDGE, bridgeBody
    sourceBodies.Add BOOT_TARGET_THISWORKBOOK, thisWorkbookBody
    Set BOOT_LoadSourceBodies = sourceBodies
End Function

Private Sub BOOT_ValidateBridgeSource(ByVal bridgeBody As String)
    BOOT_AssertContains bridgeBody, "Option Explicit", "bridge source"
    BOOT_AssertContains bridgeBody, "Option Private Module", "bridge source"
    BOOT_AssertContains bridgeBody, "Public Sub RunPhoenixRssOrderBridgeConsumer()", "bridge source"
    BOOT_AssertContains bridgeBody, "Public Sub StartPhoenixRssOrderBridgeScheduler()", "bridge source"
    BOOT_AssertContains bridgeBody, "Public Sub StopPhoenixRssOrderBridgeScheduler()", "bridge source"
    BOOT_AssertContains bridgeBody, "Private Const OBR_BRIDGE_ARMED As Boolean = False", "bridge source"
    BOOT_AssertContains bridgeBody, "OBR_ReadBridgeReadyState readyState", "bridge source"
    BOOT_AssertContains bridgeBody, "If Not readyState.Ready Then GoTo CleanExit", "bridge source"
    BOOT_AssertContains bridgeBody, "Application.OnTime", "bridge source"
    BOOT_AssertContains bridgeBody, "Schedule:=True", "bridge source"
    BOOT_AssertContains bridgeBody, "Schedule:=False", "bridge source"
    BOOT_AssertNotContains bridgeBody, "RssStockOrder_V(", "bridge source"
    BOOT_AssertNotContains bridgeBody, "RssCancelOrder_V(", "bridge source"
End Sub

Private Sub BOOT_ValidateThisWorkbookSource(ByVal workbookBody As String)
    BOOT_AssertContains workbookBody, "Option Explicit", "ThisWorkbook source"
    BOOT_AssertContains workbookBody, "Private Sub Workbook_Open()", "ThisWorkbook source"
    BOOT_AssertContains workbookBody, "Private Sub Workbook_BeforeClose(Cancel As Boolean)", "ThisWorkbook source"
    BOOT_AssertContains workbookBody, "StartPhoenixStep44ReceiverScheduler", "ThisWorkbook source"
    BOOT_AssertContains workbookBody, "StopPhoenixStep44ReceiverScheduler", "ThisWorkbook source"
    BOOT_AssertContains workbookBody, "StartPhoenixRssOrderBridgeScheduler", "ThisWorkbook source"
    BOOT_AssertContains workbookBody, "StopPhoenixRssOrderBridgeScheduler", "ThisWorkbook source"
    BOOT_AssertContainsOrdered workbookBody, "Private Sub Workbook_Open()", "StartPhoenixStep44ReceiverScheduler", "ThisWorkbook source"
    BOOT_AssertContainsOrdered workbookBody, "StartPhoenixStep44ReceiverScheduler", "StartPhoenixRssOrderBridgeScheduler", "ThisWorkbook source"
    BOOT_AssertContainsOrdered workbookBody, "Private Sub Workbook_BeforeClose(Cancel As Boolean)", "StopPhoenixRssOrderBridgeScheduler", "ThisWorkbook source"
    BOOT_AssertContainsOrdered workbookBody, "StopPhoenixRssOrderBridgeScheduler", "StopPhoenixStep44ReceiverScheduler", "ThisWorkbook source"
End Sub

Private Sub BOOT_AssertContainsOrdered(ByVal text As String, ByVal firstNeedle As String, ByVal secondNeedle As String, ByVal context As String)
    Dim firstIndex As Long
    Dim secondIndex As Long

    firstIndex = InStr(1, text, firstNeedle, vbTextCompare)
    secondIndex = InStr(firstIndex + Len(firstNeedle), text, secondNeedle, vbTextCompare)
    If firstIndex = 0 Or secondIndex = 0 Then
        Err.Raise vbObjectError + 9112, BOOT_MODULE_NAME, "Required order missing in " & context & ": " & firstNeedle & " -> " & secondNeedle
    End If
End Sub

Private Sub BOOT_ApplyTargetBodies(ByVal vbproject As Object, ByVal sourceBodies As Object)
    Dim targetNames As Variant
    Dim index As Long
    Dim componentName As String
    Dim component As Object

    targetNames = BOOT_TargetComponentNames()
    For index = LBound(targetNames) To UBound(targetNames)
        componentName = CStr(targetNames(index))
        Set component = BOOT_FindComponent(vbproject, componentName)
        BOOT_SetComponentBody component, CStr(sourceBodies(componentName))
    Next index
End Sub

Private Sub BOOT_RestoreTargetBodies(ByVal vbproject As Object, ByVal projectSnapshot As Object)
    Dim targetNames As Variant
    Dim index As Long
    Dim componentName As String
    Dim component As Object

    targetNames = BOOT_TargetComponentNames()
    For index = LBound(targetNames) To UBound(targetNames)
        componentName = CStr(targetNames(index))
        If Not projectSnapshot.Exists(componentName) Then
            Err.Raise vbObjectError + 9113, BOOT_MODULE_NAME, "Missing rollback snapshot for component: " & componentName
        End If
        Set component = BOOT_FindComponent(vbproject, componentName)
        BOOT_SetComponentBody component, CStr(projectSnapshot(componentName))
    Next index
End Sub

Private Sub BOOT_VerifyRollback(ByVal vbproject As Object, ByVal projectSnapshot As Object)
    Dim componentName As Variant
    Dim currentBody As String

    For Each componentName In projectSnapshot.Keys
        currentBody = BOOT_GetComponentBody(BOOT_FindComponent(vbproject, CStr(componentName)))
        If StrComp(Trim$(currentBody), Trim$(CStr(projectSnapshot(componentName))), vbBinaryCompare) <> 0 Then
            Err.Raise vbObjectError + 9120, BOOT_MODULE_NAME, "Rollback verification failed for component: " & CStr(componentName)
        End If
    Next componentName
End Sub

Private Sub BOOT_VerifyDeployment(ByVal vbproject As Object, ByVal projectSnapshot As Object, ByVal sourceBodies As Object)
    Dim targetNames As Variant
    Dim componentName As Variant
    Dim currentBody As String

    targetNames = BOOT_TargetComponentNames()
    For Each componentName In targetNames
        currentBody = BOOT_GetComponentBody(BOOT_FindComponent(vbproject, CStr(componentName)))
        If StrComp(Trim$(currentBody), Trim$(CStr(sourceBodies(componentName))), vbBinaryCompare) <> 0 Then
            Err.Raise vbObjectError + 9114, BOOT_MODULE_NAME, "Target module mismatch after update: " & CStr(componentName)
        End If
    Next componentName

    For Each componentName In projectSnapshot.Keys
        If Not sourceBodies.Exists(CStr(componentName)) Then
            currentBody = BOOT_GetComponentBody(BOOT_FindComponent(vbproject, CStr(componentName)))
            If StrComp(Trim$(currentBody), Trim$(CStr(projectSnapshot(componentName))), vbBinaryCompare) <> 0 Then
                Err.Raise vbObjectError + 9115, BOOT_MODULE_NAME, "Non-target VBComponent changed unexpectedly: " & CStr(componentName)
            End If
        End If
    Next componentName
End Sub

Private Function BOOT_SnapshotProjectBodies(ByVal vbproject As Object) As Object
    Dim projectSnapshot As Object
    Dim component As Object

    Set projectSnapshot = CreateObject("Scripting.Dictionary")
    projectSnapshot.CompareMode = 1
    For Each component In vbproject.VBComponents
        projectSnapshot.Add BOOT_ComponentName(component), BOOT_GetComponentBody(component)
    Next component
    Set BOOT_SnapshotProjectBodies = projectSnapshot
End Function

Private Function BOOT_FindComponent(ByVal vbproject As Object, ByVal componentName As String) As Object
    Dim component As Object

    For Each component In vbproject.VBComponents
        If StrComp(BOOT_ComponentName(component), componentName, vbTextCompare) = 0 Then
            Set BOOT_FindComponent = component
            Exit Function
        End If
    Next component

    Err.Raise vbObjectError + 9116, BOOT_MODULE_NAME, "VBComponent not found: " & componentName
End Function

Private Function BOOT_ComponentName(ByVal component As Object) As String
    BOOT_ComponentName = Trim$(CStr(component.Name))
End Function

Private Function BOOT_GetComponentBody(ByVal component As Object) As String
    Dim codeModule As Object
    Dim lineCount As Long

    Set codeModule = component.CodeModule
    lineCount = CLng(codeModule.CountOfLines)
    If lineCount <= 0 Then Exit Function
    BOOT_GetComponentBody = BOOT_ExtractVbaCodeBody(CStr(codeModule.Lines(1, lineCount)))
End Function

Private Sub BOOT_SetComponentBody(ByVal component As Object, ByVal body As String)
    Dim codeModule As Object
    Dim lineCount As Long
    Dim normalizedBody As String

    Set codeModule = component.CodeModule
    lineCount = CLng(codeModule.CountOfLines)
    If lineCount > 0 Then
        codeModule.DeleteLines 1, lineCount
    End If

    normalizedBody = Trim$(body)
    If Len(normalizedBody) > 0 Then
        codeModule.InsertLines 1, Replace$(normalizedBody, vbLf, vbCrLf)
    End If
End Sub

Private Function BOOT_TargetComponentNames() As Variant
    BOOT_TargetComponentNames = Array(BOOT_TARGET_ORDER_BRIDGE, BOOT_TARGET_THISWORKBOOK)
End Function

Private Function BOOT_ExtractVbaCodeBody(ByVal text As String) As String
    Dim normalizedText As String
    Dim lines() As String
    Dim index As Long
    Dim lineText As String
    Dim started As Boolean
    Dim bodyLines() As String
    Dim bodyCount As Long

    normalizedText = Replace$(Replace$(text, vbCrLf, vbLf), vbCr, vbLf)
    lines = Split(normalizedText, vbLf)
    ReDim bodyLines(0 To UBound(lines))

    For index = LBound(lines) To UBound(lines)
        lineText = RTrim$(lines(index))
        If Not started Then
            If Len(Trim$(lineText)) = 0 Then
                GoTo BOOT_ExtractNextLine
            End If
            If BOOT_IsHeaderLine(lineText) Then
                GoTo BOOT_ExtractNextLine
            End If
            started = True
        End If
        If Not BOOT_IsHeaderLine(lineText) Then
            bodyLines(bodyCount) = lineText
            bodyCount = bodyCount + 1
        End If
BOOT_ExtractNextLine:
    Next index

    If bodyCount = 0 Then Exit Function
    ReDim Preserve bodyLines(0 To bodyCount - 1)
    BOOT_ExtractVbaCodeBody = Join(bodyLines, vbLf)
End Function

Private Function BOOT_IsHeaderLine(ByVal lineText As String) As Boolean
    Dim token As String

    token = UCase$(Trim$(lineText))
    If Len(token) = 0 Then Exit Function
    If Left$(token, 9) = "ATTRIBUTE " Then
        BOOT_IsHeaderLine = True
    ElseIf Left$(token, 8) = "VERSION " Then
        BOOT_IsHeaderLine = True
    ElseIf token = "BEGIN" Or token = "END" Then
        BOOT_IsHeaderLine = True
    End If
End Function

Private Sub BOOT_AssertContains(ByVal text As String, ByVal needle As String, ByVal context As String)
    If InStr(1, text, needle, vbTextCompare) = 0 Then
        Err.Raise vbObjectError + 9117, BOOT_MODULE_NAME, "Missing required marker in " & context & ": " & needle
    End If
End Sub

Private Sub BOOT_AssertNotContains(ByVal text As String, ByVal needle As String, ByVal context As String)
    If InStr(1, text, needle, vbTextCompare) > 0 Then
        Err.Raise vbObjectError + 9118, BOOT_MODULE_NAME, "Forbidden marker found in " & context & ": " & needle
    End If
End Sub

Private Function BOOT_ReadUtf8TextFile(ByVal pathText As String) As String
    Dim stream As Object

    Set stream = CreateObject("ADODB.Stream")
    stream.Type = 1
    stream.Open
    stream.LoadFromFile pathText
    stream.Position = 0
    stream.Type = 2
    stream.Charset = "utf-8"
    BOOT_ReadUtf8TextFile = stream.ReadText(-1)
    stream.Close
End Function

Private Function BOOT_FileExists(ByVal pathText As String) As Boolean
    If Len(pathText) = 0 Then Exit Function
    BOOT_FileExists = Len(Dir$(pathText)) > 0
End Function

Private Function BOOT_FileSha256Hex(ByVal pathText As String) As String
    Dim fileBytes() As Byte
    Dim fileSize As Long
    Dim hashBytes(0 To 31) As Byte
    Dim hashLength As Long
    Dim hProv As LongPtr
    Dim hHash As LongPtr
    Dim providerName As String
    Dim errorNumber As Long
    Dim errorSource As String
    Dim errorDescription As String

    On Error GoTo BOOT_FileSha256Hex_Fail

    If Not BOOT_FileExists(pathText) Then
        Err.Raise vbObjectError + 9120, BOOT_MODULE_NAME, "Missing file for SHA-256: " & pathText
    End If

    fileSize = FileLen(pathText)
    If fileSize > 0 Then
        fileBytes = BOOT_ReadBinaryFile(pathText)
    End If

    providerName = "Microsoft Enhanced RSA and AES Cryptographic Provider"
    If CryptAcquireContextW(hProv, 0, StrPtr(providerName), BOOT_RSA_AES_PROV_TYPE, BOOT_CRYPT_VERIFYCONTEXT) = 0 Then
        If CryptAcquireContextW(hProv, 0, 0, BOOT_RSA_AES_PROV_TYPE, BOOT_CRYPT_VERIFYCONTEXT) = 0 Then
            Err.Raise vbObjectError + 9121, BOOT_MODULE_NAME, "SHA-256 context acquisition failed"
        End If
    End If

    If CryptCreateHash(hProv, BOOT_CALG_SHA_256, 0, 0, hHash) = 0 Then
        Err.Raise vbObjectError + 9122, BOOT_MODULE_NAME, "SHA-256 hash creation failed"
    End If

    If fileSize > 0 Then
        If CryptHashData(hHash, fileBytes(0), fileSize, 0) = 0 Then
            Err.Raise vbObjectError + 9123, BOOT_MODULE_NAME, "SHA-256 hash update failed"
        End If
    End If

    hashLength = 32
    If CryptGetHashParam(hHash, BOOT_HP_HASHVAL, hashBytes(0), hashLength, 0) = 0 Then
        Err.Raise vbObjectError + 9124, BOOT_MODULE_NAME, "SHA-256 digest read failed"
    End If

    BOOT_FileSha256Hex = BOOT_BytesToHexLower(hashBytes)

BOOT_FileSha256Hex_CleanExit:
    If hHash <> 0 Then CryptDestroyHash hHash
    If hProv <> 0 Then CryptReleaseContext hProv, 0
    If errorNumber <> 0 Then
        On Error GoTo 0
        Err.Raise errorNumber, errorSource, errorDescription
    End If
    Exit Function

BOOT_FileSha256Hex_Fail:
    errorNumber = Err.Number
    errorSource = Err.Source
    errorDescription = Err.Description
    Resume BOOT_FileSha256Hex_CleanExit
End Function

Private Function BOOT_FilesAreByteIdentical(ByVal firstPath As String, ByVal secondPath As String) As Boolean
    Dim firstBytes() As Byte
    Dim secondBytes() As Byte

    If Not BOOT_FileExists(firstPath) Or Not BOOT_FileExists(secondPath) Then Exit Function
    If FileLen(firstPath) <> FileLen(secondPath) Then Exit Function
    If FileLen(firstPath) = 0 Then
        BOOT_FilesAreByteIdentical = True
        Exit Function
    End If

    firstBytes = BOOT_ReadBinaryFile(firstPath)
    secondBytes = BOOT_ReadBinaryFile(secondPath)
    BOOT_FilesAreByteIdentical = BOOT_BinaryArraysEqual(firstBytes, secondBytes)
End Function

Private Function BOOT_BytesToHexLower(ByRef bytes() As Byte) As String
    Dim index As Long
    Dim hexText As String

    For index = LBound(bytes) To UBound(bytes)
        hexText = hexText & Right$("0" & Hex$(bytes(index)), 2)
    Next index
    BOOT_BytesToHexLower = LCase$(hexText)
End Function

Private Function BOOT_ReadBinaryFile(ByVal pathText As String) As Byte()
    Dim fileNumber As Integer
    Dim bytes() As Byte
    Dim fileSize As Long

    fileSize = FileLen(pathText)
    If fileSize <= 0 Then Exit Function

    fileNumber = FreeFile
    Open pathText For Binary Access Read As #fileNumber
    ReDim bytes(0 To fileSize - 1)
    Get #fileNumber, , bytes
    Close #fileNumber
    BOOT_ReadBinaryFile = bytes
End Function

Private Function BOOT_BinaryArraysEqual(ByRef firstBytes() As Byte, ByRef secondBytes() As Byte) As Boolean
    Dim index As Long

    If UBound(firstBytes) <> UBound(secondBytes) Then Exit Function
    For index = LBound(firstBytes) To UBound(firstBytes)
        If firstBytes(index) <> secondBytes(index) Then Exit Function
    Next index
    BOOT_BinaryArraysEqual = True
End Function

Private Function BOOT_FindRepositoryRoot(ByVal startPath As String) As String
    Dim currentPath As String
    Dim parentPath As String
    Dim fso As Object

    If Len(startPath) = 0 Then
        Err.Raise vbObjectError + 9120, BOOT_MODULE_NAME, "Workbook must be saved before running the bootstrap"
    End If

    currentPath = BOOT_NormalizeRepositoryStartPath(startPath)
    Set fso = CreateObject("Scripting.FileSystemObject")
    Do
        If BOOT_RepositoryLooksValid(currentPath) Then
            BOOT_FindRepositoryRoot = currentPath
            Exit Function
        End If
        parentPath = fso.GetParentFolderName(currentPath)
        If Len(parentPath) = 0 Or parentPath = currentPath Then Exit Do
        currentPath = parentPath
    Loop

    Err.Raise vbObjectError + 9121, BOOT_MODULE_NAME, "Unable to resolve the PHOENIX repository root"
End Function

Private Function BOOT_NormalizeRepositoryStartPath(ByVal startPath As String) As String
    Dim rawPath As String
    Dim firstSlash As Long
    Dim relativePath As String

    rawPath = Trim$(startPath)
    If Len(rawPath) = 0 Then Exit Function
    If StrComp(Left$(rawPath, Len(BOOT_ONEDRIVE_WEB_PREFIX)), BOOT_ONEDRIVE_WEB_PREFIX, vbTextCompare) <> 0 Then
        BOOT_NormalizeRepositoryStartPath = BOOT_NormalizePath(rawPath)
        Exit Function
    End If

    firstSlash = InStr(Len(BOOT_ONEDRIVE_WEB_PREFIX) + 1, rawPath, "/", vbBinaryCompare)
    If firstSlash = 0 Then
        Err.Raise vbObjectError + 9122, BOOT_MODULE_NAME, "Unable to map OneDrive web path to a local folder"
    End If

    relativePath = Mid$(rawPath, firstSlash + 1)
    If Len(relativePath) = 0 Then
        Err.Raise vbObjectError + 9122, BOOT_MODULE_NAME, "Unable to map OneDrive web path to a local folder"
    End If

    BOOT_NormalizeRepositoryStartPath = BOOT_OneDriveLocalRoot() & "\" & Replace$(relativePath, "/", "\")
End Function

Private Function BOOT_OneDriveLocalRoot() As String
    Dim candidate As String
    Dim fso As Object

    candidate = BOOT_NormalizePath(Environ$("OneDrive"))
    If Len(candidate) > 0 Then
        BOOT_OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = BOOT_NormalizePath(Environ$("OneDriveConsumer"))
    If Len(candidate) > 0 Then
        BOOT_OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = BOOT_NormalizePath(Environ$("OneDriveCommercial"))
    If Len(candidate) > 0 Then
        BOOT_OneDriveLocalRoot = candidate
        Exit Function
    End If

    candidate = BOOT_NormalizePath(Environ$("USERPROFILE"))
    If Len(candidate) > 0 Then
        candidate = candidate & "\OneDrive"
        Set fso = CreateObject("Scripting.FileSystemObject")
        If fso.FolderExists(candidate) Then
            BOOT_OneDriveLocalRoot = candidate
            Exit Function
        End If
    End If

    Err.Raise vbObjectError + 9123, BOOT_MODULE_NAME, "Unable to resolve the local OneDrive root"
End Function

Private Function BOOT_RepositoryLooksValid(ByVal rootPath As String) As Boolean
    BOOT_RepositoryLooksValid = _
        BOOT_FileExists(rootPath & "\run_phoenix.py") And _
        BOOT_FileExists(rootPath & "\AGENTS.md") And _
        BOOT_FileExists(rootPath & "\phoenix_core\__init__.py")
End Function

Private Function BOOT_NormalizePath(ByVal pathText As String) As String
    BOOT_NormalizePath = Replace$(Trim$(pathText), "/", "\")
End Function
