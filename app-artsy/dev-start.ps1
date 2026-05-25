param(
    [switch]$SkipInstall,
    [switch]$ForceSetup,
    [ValidateSet('local', 'sso')]
    [string]$AuthMode = 'local',
    [string]$DatabaseUrl = 'postgresql://postgres:postgres@localhost:5432/nightcraft_curio',
    [string]$AuthServiceUrl = 'http://127.0.0.1:5100',
    [string]$AuthClientId = 'curio-app',
    [string]$AuthClientSecret = 'dev-secret',
    [int]$Port = 5600
)

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

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
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r (Join-Path $scriptDir 'requirements.txt')
}
else {
    Write-Host '[dev-start] Skipping requirements installation.'
}

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw 'DatabaseUrl cannot be empty. Provide a PostgreSQL DATABASE_URL.'
}

Write-Host "[dev-start] Using DATABASE_URL=$DatabaseUrl"
$env:DATABASE_URL = $DatabaseUrl

if ($ForceSetup) {
    Write-Host '[dev-start] Running setup (forced)...'
    & $venvPython -m flask --app curio setup
}
else {
    Write-Host '[dev-start] Running setup (idempotent)...'
    & $venvPython -m flask --app curio setup
}

$env:FLASK_AUTH_MODE = $AuthMode
if ($AuthMode -eq 'sso') {
    $env:FLASK_AUTH_SERVICE_URL = $AuthServiceUrl
    $env:FLASK_AUTHLIB_CLIENT_ID = $AuthClientId
    $env:FLASK_AUTHLIB_CLIENT_SECRET = $AuthClientSecret
    Write-Host '[dev-start] AUTH_MODE=sso'
    Write-Host "[dev-start] AUTH_SERVICE_URL=$AuthServiceUrl"
}
else {
    Write-Host '[dev-start] AUTH_MODE=local'
}

Write-Host "[dev-start] Starting Curio at http://127.0.0.1:$Port"
& $venvPython -m flask --app curio run --port $Port
