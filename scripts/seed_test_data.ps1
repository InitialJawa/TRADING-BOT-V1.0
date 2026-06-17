param(
    [string]$Drawdown = "8.4",
    [string]$Sharpe = "0.55",
    [string]$MT5Connected = "true",
    [string]$BacktestResult = "PASS",
    [string]$HeartbeatStatus = "OK"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "Seeding test data..." -ForegroundColor Cyan
Write-Host "  Drawdown: $Drawdown%"
Write-Host "  Sharpe: $Sharpe"
Write-Host "  MT5: $MT5Connected"
Write-Host "  Backtest: $BacktestResult"
Write-Host "  Heartbeat: $HeartbeatStatus"

python -c @"
from src.state_manager import StateManager
state = StateManager()
state.upsert_metric('portfolio_drawdown', $Drawdown)
state.upsert_metric('rolling_sharpe_7d', $Sharpe)
state.upsert_metric('last_heartbeat', '$((Get-Date).ToUniversalTime().ToString('o'))')
state.upsert_strategy('adaptive', 'ACTIVE')
state.upsert_strategy('trend_re', 'ACTIVE')
state.log_backtest('adaptive', '$BacktestResult')
print('Test data seeded successfully')
"@

Write-Host "Done." -ForegroundColor Green
