# Run MT5 test as administrator
$scriptPath = Join-Path $PSScriptRoot "_mt5_test.py"
$pythonPath = "python"

Start-Process -FilePath $pythonPath -ArgumentList $scriptPath -Verb RunAs -Wait
