[CmdletBinding()]
param(
    [string]$TaskName = "PHOENIX-v7-Paper",

    [ValidatePattern("^\d{2}:\d{2}$")]
    [string]$At = "08:30",

    [string]$PythonPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module ScheduledTasks -ErrorAction Stop

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EntryScript = Join-Path $Root "scheduled_entry_v7.py"
$VerifyScript = Join-Path $Root "verify_v7_step8.py"
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

function Resolve-PhoenixPython {
    param(
        [string]$RequestedPython
    )

    if (-not [string]::IsNullOrWhiteSpace($RequestedPython)) {
        if (-not (Test-Path -LiteralPath $RequestedPython -PathType Leaf)) {
            throw "Requested Python was not found: $RequestedPython"
        }
        return (Resolve-Path -LiteralPath $RequestedPython).Path
    }

    if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
        return (Resolve-Path -LiteralPath $VenvPython).Path
    }

    $Command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $Command) {
        $Command = Get-Command python -ErrorAction SilentlyContinue
    }
    if ($null -eq $Command) {
        throw "Python executable was not found."
    }
    return $Command.Source
}

if (-not (Test-Path -LiteralPath $EntryScript -PathType Leaf)) {
    throw "Entry script was not found: $EntryScript"
}
if (-not (Test-Path -LiteralPath $VerifyScript -PathType Leaf)) {
    throw "Verify script was not found: $VerifyScript"
}

$PythonExe = Resolve-PhoenixPython -RequestedPython $PythonPath

Write-Output "Running PHOENIX Step8 environment verification."
& $PythonExe -X utf8 $VerifyScript --skip-tests
if ($LASTEXITCODE -ne 0) {
    throw "Step8 verification failed. Scheduled task was not installed."
}

$TriggerTime = [DateTime]::ParseExact(
    $At,
    "HH:mm",
    [System.Globalization.CultureInfo]::InvariantCulture
)
$Arguments = '-X utf8 "{0}"' -f $EntryScript

$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument $Arguments `
    -WorkingDirectory $Root

$Trigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $TriggerTime

$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "PHOENIX v7 scheduler with environment safety gate" `
    -Force | Out-Null

$RegisteredTask = Get-ScheduledTask `
    -TaskName $TaskName `
    -ErrorAction Stop

Write-Output "Scheduled task installed."
Write-Output "TaskName: $($RegisteredTask.TaskName)"
Write-Output "State: $($RegisteredTask.State)"
Write-Output "RunTime: $At"
Write-Output "Python: $PythonExe"
Write-Output "Entry: $EntryScript"
