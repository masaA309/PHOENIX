$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ignorePath = Join-Path $root ".gitignore"
$entries = @(
    ".env", "state/*.json", "state/*.lock", "logs/scheduler/",
    "reports/v7_environment_report.json", "reports/v7_environment_report.txt",
    "reports/v7_operations_report.json", "reports/v7_operations_report.txt",
    "reports/v7_run_history.jsonl", "reports/v7_performance_summary.json",
    "reports/v7_performance_summary.txt",
    "reports/v7_decision_diagnostics.json", "reports/v7_decision_diagnostics.txt",
    "reports/v7_portfolio_guard.json", "reports/v7_portfolio_guard.txt",
    "reports/v7_market_data_guard.json", "reports/v7_market_data_guard.txt",
    "reports/v7_readiness_gate.json", "reports/v7_readiness_gate.txt"
)
$existing = if (Test-Path $ignorePath) { Get-Content $ignorePath } else { @() }
foreach ($entry in $entries) {
    if ($existing -notcontains $entry) { Add-Content -Path $ignorePath -Value $entry -Encoding utf8; $existing += $entry }
}
Write-Host "PHOENIX v7 runtime ignore rules are ready."
