param(
    [int]$Interval = 900
)

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "AI Risk & Operations Manager - Cycle Runner" -ForegroundColor Cyan
Write-Host "Interval: ${Interval}s per cycle" -ForegroundColor Gray
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

while ($true) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$timestamp] Starting cycle..." -ForegroundColor Yellow
    python -m src.main
    Write-Host "[$timestamp] Cycle complete. Waiting ${Interval}s..." -ForegroundColor Yellow
    Write-Host "----------------------------------------"
    Start-Sleep -Seconds $Interval
}
