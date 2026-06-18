param(
    [string]$Action = "start"
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectRoot "scripts" "live_bot_4_ticker.py"
$LogPath = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogPath "live_bot.log"

if (-not (Test-Path $LogPath)) {
    New-Item -ItemType Directory -Path $LogPath -Force | Out-Null
}

function Start-Bot {
    Write-Host "=== STARTING LIVE BOT ===" -ForegroundColor Cyan
    Write-Host "Log: $LogFile" -ForegroundColor Gray
    $env:PYTHONIOENCODING='utf-8'
    python $ScriptPath *>> $LogFile
}

function Stop-Bot {
    Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -match "live_bot_4_ticker"
    } | Stop-Process -Force
    Write-Host "Bot stopped" -ForegroundColor Yellow
}

switch ($Action) {
    "start" { Start-Bot }
    "stop"  { Stop-Bot }
    "log"   { Get-Content -Path $LogFile -Tail 50 -Wait }
    default { Write-Host "Usage: .\run_live_bot.ps1 [start|stop|log]" }
}
