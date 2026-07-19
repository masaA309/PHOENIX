[CmdletBinding()]
param(
    [string]$TaskName = "PHOENIX-v7-Paper"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module ScheduledTasks -ErrorAction Stop

$ExistingTask = Get-ScheduledTask `
    -TaskName $TaskName `
    -ErrorAction SilentlyContinue

if ($null -eq $ExistingTask) {
    Write-Output "Scheduled task does not exist: $TaskName"
    exit 0
}

Unregister-ScheduledTask `
    -TaskName $TaskName `
    -Confirm:$false `
    -ErrorAction Stop

Write-Output "Scheduled task removed: $TaskName"
