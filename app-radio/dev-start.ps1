param(
    [switch]$SkipInstall,
    [switch]$SkipSetup,
    [ValidateSet('local', 'sso')]
    [string]$AuthMode = 'local',
    [string]$AuthServiceUrl = 'http://127.0.0.1:5100',
    [string]$AuthClientId = 'radio-app',
    [string]$AuthClientSecret = 'dev-secret',
    [string]$DatabaseUrl = 'postgresql+psycopg://radio_app:radio_app_db_2026_dev_secret@127.0.0.1:5432/radio_db'
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

if (-not $DatabaseUrl) {
    throw 'DatabaseUrl cannot be empty. Provide a PostgreSQL DSN.'
}

$env:FLASK_SQLALCHEMY_DATABASE_URI = $DatabaseUrl
$env:FLASK_AUTH_MODE = $AuthMode

Write-Host '[dev-start] Using PostgreSQL database URL from FLASK_SQLALCHEMY_DATABASE_URI.'

if ($AuthMode -eq 'sso') {
    $env:FLASK_AUTH_SERVICE_URL = $AuthServiceUrl
    $env:FLASK_AUTHLIB_CLIENT_ID = $AuthClientId
    $env:FLASK_AUTHLIB_CLIENT_SECRET = $AuthClientSecret
    Write-Host "[dev-start] AUTH_MODE=sso"
    Write-Host "[dev-start] AUTH_SERVICE_URL=$AuthServiceUrl"
}
else {
    Write-Host '[dev-start] AUTH_MODE=local'
}

if (-not $SkipSetup) {
    Write-Host '[dev-start] Running setup (tables/default accounts/feeds)...'
    & $venvPython -m flask --app devradio setup
}
else {
    Write-Host '[dev-start] Skipping setup step.'
}

Write-Host '[dev-start] Starting DevRadio at http://127.0.0.1:5000'
& $venvPython -m flask --app devradio run
