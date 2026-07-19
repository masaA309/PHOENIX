[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$GitIgnore = Join-Path $Root ".gitignore"

$RequiredEntries = @(
    ".venv/",
    "__pycache__/",
    "*.py[cod]",
    ".pytest_cache/",
    "runtime/",
    "logs/scheduler/",
    "reports/v7_environment_report.json"
)

$Lines = @()
if (Test-Path -LiteralPath $GitIgnore -PathType Leaf) {
    $Lines = @([System.IO.File]::ReadAllLines($GitIgnore))
}

foreach ($Entry in $RequiredEntries) {
    if (-not ($Lines -contains $Entry)) {
        $Lines += $Entry
    }
}

$Content = ($Lines -join [Environment]::NewLine).TrimEnd()
$Content += [Environment]::NewLine
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText(
    $GitIgnore,
    $Content,
    $Utf8NoBom
)

Write-Output "Runtime exclusions are ready."
Write-Output "File: $GitIgnore"
