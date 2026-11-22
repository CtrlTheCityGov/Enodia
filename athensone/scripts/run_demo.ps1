# Windows: start AthensOne for the presentation (run from the athensone folder in PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1
$env:MOCK = "1"; $env:DEMO_MODE = "1"; if (-not $env:STOA_TODAY) { $env:STOA_TODAY = "2026-11-22" }
$port = if ($env:PORT) { $env:PORT } else { "8000" }
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
Write-Host "Operator Console: http://127.0.0.1:$port/web/operator.html"
Write-Host "Citizen Map:      http://127.0.0.1:$port/web/citizen.html"
Start-Job -ScriptBlock { param($p) for ($i=0; $i -lt 30; $i++) { Start-Sleep 1
  try { Invoke-RestMethod -Method Post "http://127.0.0.1:$p/api/admin/demo-seed" | Out-Null; break } catch {} } } -ArgumentList $port | Out-Null
& $py -m uvicorn app.main:app --host 127.0.0.1 --port $port
