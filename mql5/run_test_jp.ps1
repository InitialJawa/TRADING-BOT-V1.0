$mt5Dir = "C:\Program Files\MetaTrader 5"
$exe = Join-Path $mt5Dir "metatester64.exe"

# Kill existing metatester processes
Get-Process -Name "metatester64" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$args = @(
    "/test:jp225m_g_m15"
    "/symbol:JP225m"
    "/period:M15"
    "/model:0"
    "/from:2026.06.01"
    "/to:2026.06.18"
    "/deposit:10000"
    "/leverage:100"
)

Write-Output "Launching tester..."
$p = Start-Process -FilePath $exe -ArgumentList $args -NoNewWindow -PassThru
Start-Sleep -Seconds 10
if (!$p.HasExited) {
    Write-Output "Tester still running, force kill..."
    $p.Kill()
}
Write-Output "Done"
