param(
    [switch]$SkipInstall,
    [switch]$Seed,
    [string]$DatabaseUrl = 'postgresql://postgres:postgres@localhost:5432/nightcraft_auth',
    [string]$Username = 'devuser',
    [string]$Email = 'devuser@example.com',
    [string]$Password = 'devpass123',
    [string]$ClientId = 'radio-app',
    [string]$ClientSecret = 'dev-secret',
    [string]$RedirectUri = 'http://127.0.0.1:5000/auth/callback'
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE"
    }
}

$venvDir = Join-Path $scriptDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host '[dev-start] Creating virtual environment...'
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvDir
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvDir
    }
    else {
        throw 'Python was not found. Install Python 3 first, then rerun this script.'
    }
}

if (-not $SkipInstall) {
    Write-Host '[dev-start] Installing requirements...'
    Invoke-Checked -Action 'pip upgrade' -Command { & $venvPython -m pip install --upgrade pip }
    Invoke-Checked -Action 'requirements install' -Command { & $venvPython -m pip install -r (Join-Path $scriptDir 'requirements.txt') }
}
else {
    Write-Host '[dev-start] Skipping requirements installation.'
}

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw 'DatabaseUrl cannot be empty. Provide a PostgreSQL DATABASE_URL.'
}

Write-Host "[dev-start] Using DATABASE_URL=$DatabaseUrl"
$env:DATABASE_URL = $DatabaseUrl

if ($Seed) {
    Write-Host "[dev-start] Seeding dev user/client with redirect URI: $RedirectUri"
    Invoke-Checked -Action 'seed-dev' -Command {
        & $venvPython -m flask --app run.py seed-dev `
            --username $Username `
            --email $Email `
            --password $Password `
            --client-id $ClientId `
            --client-secret $ClientSecret `
            --redirect-uri $RedirectUri
    }
}

Write-Host '[dev-start] Starting service-auth at http://127.0.0.1:5100'
& $venvPython run.py
