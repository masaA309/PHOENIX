param(
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = $PSScriptRoot
$Timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$BackupDirectory = Join-Path `
    $ProjectRoot `
    ('_cleanup_backup\' + $Timestamp)

# Cleanup candidates.
# Files referenced by other Python files will be skipped.
$Candidates = @(
    'daily_report_v2.py',
    'nikkei225_report.py',
    'chart.py',
    'ranking.py',
    'stock.py',
    'test.py',
    'nikkei225.csv'
)

function Write-Section {
    param(
        [string]$Title
    )

    Write-Host ''
    Write-Host ('=' * 70)
    Write-Host $Title
    Write-Host ('=' * 70)
}

function Get-ProjectPythonFiles {
    $files = Get-ChildItem `
        -LiteralPath $ProjectRoot `
        -Recurse `
        -File `
        -Filter '*.py'

    return @(
        $files | Where-Object {
            $_.FullName -notlike '*\.venv\*' -and
            $_.FullName -notlike '*\__pycache__\*' -and
            $_.FullName -notlike '*\_cleanup_backup\*'
        }
    )
}

function Find-PythonReferences {
    param(
        [System.IO.FileInfo]$TargetFile
    )

    if ($TargetFile.Extension -ne '.py') {
        return @()
    }

    $moduleName = [System.IO.Path]::GetFileNameWithoutExtension(
        $TargetFile.Name
    )

    $escapedModule = [regex]::Escape($moduleName)
    $escapedFileName = [regex]::Escape($TargetFile.Name)

    $patterns = @(
        ('(?m)^\s*import\s+' + $escapedModule + '(?:\s|$)'),
        ('(?m)^\s*from\s+' + $escapedModule + '\s+import\s+'),
        (
            '(?m)^\s*from\s+modules\.' +
            $escapedModule +
            '\s+import\s+'
        ),
        $escapedFileName
    )

    $references = @()

    foreach ($pythonFile in Get-ProjectPythonFiles) {
        if ($pythonFile.FullName -eq $TargetFile.FullName) {
            continue
        }

        try {
            $content = Get-Content `
                -LiteralPath $pythonFile.FullName `
                -Raw

            foreach ($pattern in $patterns) {
                if ($content -match $pattern) {
                    $references += $pythonFile.FullName
                    break
                }
            }
        }
        catch {
            Write-Warning (
                'Could not read: ' +
                $pythonFile.FullName
            )
        }
    }

    return @(
        $references |
        Sort-Object -Unique
    )
}

function Get-RelativePath {
    param(
        [string]$FullPath
    )

    $prefix = $ProjectRoot.TrimEnd('\') + '\'

    if (
        $FullPath.StartsWith(
            $prefix,
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        return $FullPath.Substring($prefix.Length)
    }

    return $FullPath
}

Write-Section 'PHOENIX CLEANUP'

Write-Host ('Project: ' + $ProjectRoot)

if (-not $Execute) {
    Write-Host ''
    Write-Host 'CHECK MODE'
    Write-Host 'No files will be moved or deleted.'
}

$safeCandidates = @()
$skippedCandidates = @()

foreach ($relativePath in $Candidates) {
    $fullPath = Join-Path `
        $ProjectRoot `
        $relativePath

    if (
        -not (
            Test-Path `
                -LiteralPath $fullPath `
                -PathType Leaf
        )
    ) {
        Write-Host (
            '[NOT FOUND] ' +
            $relativePath
        )

        continue
    }

    $targetFile = Get-Item `
        -LiteralPath $fullPath

    $references = @()

    if ($targetFile.Extension -eq '.py') {
        $references = @(
            Find-PythonReferences `
                -TargetFile $targetFile
        )
    }

    if ($references.Count -gt 0) {
        Write-Host ''
        Write-Host (
            '[SKIP - REFERENCED] ' +
            $relativePath
        )

        foreach ($reference in $references) {
            $displayPath = Get-RelativePath `
                -FullPath $reference

            Write-Host (
                '  - ' +
                $displayPath
            )
        }

        $skippedCandidates += $relativePath
        continue
    }

    Write-Host (
        '[CANDIDATE] ' +
        $relativePath
    )

    $safeCandidates += $relativePath
}

Write-Section 'RESULT'

if ($safeCandidates.Count -eq 0) {
    Write-Host 'No safe cleanup candidates found.'
}
else {
    Write-Host 'Safe cleanup candidates:'

    foreach ($candidate in $safeCandidates) {
        Write-Host (
            '  - ' +
            $candidate
        )
    }
}

if ($skippedCandidates.Count -gt 0) {
    Write-Host ''
    Write-Host 'Referenced files skipped:'

    foreach ($candidate in $skippedCandidates) {
        Write-Host (
            '  - ' +
            $candidate
        )
    }
}

if (-not $Execute) {
    Write-Host ''
    Write-Host 'Check mode completed.'
    Write-Host ''
    Write-Host 'Run this command to move safe files:'
    Write-Host '  .\cleanup_phoenix.ps1 -Execute'
    exit 0
}

if ($safeCandidates.Count -eq 0) {
    Write-Host ''
    Write-Host 'Nothing to move.'
    exit 0
}

Write-Section 'MOVE FILES'

New-Item `
    -ItemType Directory `
    -Path $BackupDirectory `
    -Force |
    Out-Null

Write-Host (
    'Backup directory: ' +
    $BackupDirectory
)

foreach ($relativePath in $safeCandidates) {
    $sourcePath = Join-Path `
        $ProjectRoot `
        $relativePath

    if (
        -not (
            Test-Path `
                -LiteralPath $sourcePath `
                -PathType Leaf
        )
    ) {
        Write-Host (
            '[NOT FOUND] ' +
            $relativePath
        )

        continue
    }

    $destinationPath = Join-Path `
        $BackupDirectory `
        $relativePath

    $destinationParent = Split-Path `
        -Parent `
        $destinationPath

    New-Item `
        -ItemType Directory `
        -Path $destinationParent `
        -Force |
        Out-Null

    Move-Item `
        -LiteralPath $sourcePath `
        -Destination $destinationPath `
        -Force

    Write-Host (
        '[MOVED] ' +
        $relativePath
    )
}

Write-Section 'COMPLETE'

Write-Host 'Files were moved, not permanently deleted.'
Write-Host (
    'Backup: ' +
    $BackupDirectory
)
Write-Host ''
Write-Host 'Run these checks:'
Write-Host '  python run_phoenix.py'
Write-Host '  git status'