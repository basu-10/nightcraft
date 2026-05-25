# start.ps1 — start Flask backend + Vite frontend in separate terminal windows
# Usage: .\seeksage_webapp\start.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $scriptDir "backend"
$frontendDir = Join-Path $scriptDir "frontend"

Write-Host "=== Starting SeekSage Webapp ===" -ForegroundColor Cyan

# ── Backend ──────────────────────────────────────────────────────────────────
Write-Host "`nStarting Flask backend (http://localhost:5000)..." -ForegroundColor Yellow
$backendCmd = "Set-Location '$backendDir'; `$env:FLASK_APP='run.py'; `$env:FLASK_DEBUG='1'; .\.venv\Scripts\python run.py; Read-Host 'Press Enter to close'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# ── Frontend ──────────────────────────────────────────────────────────────────
Write-Host "Starting Vite frontend (http://localhost:5173)..." -ForegroundColor Yellow
$frontendCmd = "Set-Location '$frontendDir'; npm run dev; Read-Host 'Press Enter to close'"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd

Write-Host "`nBoth servers are starting in separate windows." -ForegroundColor Green
Write-Host "Backend: http://localhost:5000" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:5173" -ForegroundColor Cyan
