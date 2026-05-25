param(
    [ValidateSet('radio', 'artsy')]
    [string]$App = 'radio',
    [ValidateSet('local', 'sso')]
    [string]$AuthMode = 'sso',
    [string]$AuthServiceUrl = 'http://127.0.0.1:5100',
    [string]$AuthClientId = '',
    [string]$AuthClientSecret = 'dev-secret',
    [int]$Port = 0,
    [string]$LogRoot = '',
    [string]$LogSessionId = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'common.ps1')

$repoRoot = Get-RepoRoot
$appRadioPath = Join-Path $repoRoot 'app-radio'
$appArtsyPath = Join-Path $repoRoot 'app-artsy'

if ($App -eq 'artsy') {
    $appPath = $appArtsyPath
    $appScript = Join-Path $appArtsyPath 'dev-start.ps1'
    $logCategoryPath = 'app-artsy'
    if (-not $AuthClientId) {
        $AuthClientId = 'curio-app'
    }
    if ($Port -le 0) {
        $Port = 5600
    }
}
else {
    $appPath = $appRadioPath
    $appScript = Join-Path $appRadioPath 'dev-start.ps1'
    $logCategoryPath = 'app-radio'
    if (-not $AuthClientId) {
        $AuthClientId = 'radio-app'
    }
    if ($Port -le 0) {
        $Port = 5000
    }
}

$logFile = Start-ScriptLog `
    -LogRoot $LogRoot `
    -CategoryPath $logCategoryPath `
    -ScriptName $MyInvocation.MyCommand.Name `
    -SessionId $LogSessionId

try {
    Write-Host "[run-client] Log file: $logFile"
    Write-Host "[run-client] Starting app-$App in $AuthMode mode on port $Port"
    Set-Location $appPath
    if ($App -eq 'artsy') {
        & $appScript -AuthMode $AuthMode -AuthServiceUrl $AuthServiceUrl -AuthClientId $AuthClientId -AuthClientSecret $AuthClientSecret -Port $Port
    }
    else {
        & $appScript -AuthMode $AuthMode -AuthServiceUrl $AuthServiceUrl -AuthClientId $AuthClientId -AuthClientSecret $AuthClientSecret
    }
}
finally {
    Stop-ScriptLog
}
