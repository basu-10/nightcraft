# setup.ps1 — one-time setup for seeksage_webapp (run from repo root or seeksage_webapp/)
# Usage: .\seeksage_webapp\setup.ps1

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $scriptDir "backend"
$frontendDir = Join-Path $scriptDir "frontend"

Write-Host "=== SeekSage Webapp Setup ===" -ForegroundColor Cyan

# ── Backend ──────────────────────────────────────────────────────────────────
Write-Host "`n[1/4] Creating Python venv..." -ForegroundColor Yellow
Push-Location $backendDir
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
else {
    Write-Host "  .venv already exists, skipping."
}

Write-Host "[2/4] Installing Python requirements..." -ForegroundColor Yellow
& ".\.venv\Scripts\python" -m pip install -r requirements.txt --quiet

Write-Host "[3/4] Running DB migrations..." -ForegroundColor Yellow
$env:FLASK_APP = "run.py"
& ".\.venv\Scripts\python" -m flask db upgrade

Write-Host "[4/4] Seeding database..." -ForegroundColor Yellow
& ".\.venv\Scripts\python" scripts/seed_db.py
Pop-Location

# ── Frontend ──────────────────────────────────────────────────────────────────
Write-Host "`n[5/5] Installing frontend npm packages..." -ForegroundColor Yellow
Push-Location $frontendDir
npm install
Pop-Location

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Run .\seeksage_webapp\start.ps1 to start the app." -ForegroundColor Cyan
