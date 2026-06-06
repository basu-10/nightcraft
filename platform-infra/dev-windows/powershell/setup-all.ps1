param(
    [switch]$SkipInstall,
    [string]$LogRoot = '',
    [string]$LogSessionId = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'common.ps1')

$logFile = Start-ScriptLog `
    -LogRoot $LogRoot `
    -CategoryPath 'platform-infra/dev-windows/powershell' `
    -ScriptName $MyInvocation.MyCommand.Name `
    -SessionId $LogSessionId

try {
    Write-Host "[setup-all] Log file: $logFile"

    $repoRoot = Get-RepoRoot
    $serviceAuthPath = Join-Path $repoRoot 'service-auth'
    $appRadioPath = Join-Path $repoRoot 'app-radio'
    $appArtsyPath = Join-Path $repoRoot 'app-artsy'

    if (-not $SkipInstall) {
        Write-Host '[setup-all] Installing service-auth dependencies...'
        Install-Requirements -AppPath $serviceAuthPath

        Write-Host '[setup-all] Installing app-radio dependencies...'
        Install-Requirements -AppPath $appRadioPath

        Write-Host '[setup-all] Installing app-artsy dependencies...'
        Install-Requirements -AppPath $appArtsyPath
    }
    else {
        Write-Host '[setup-all] SkipInstall provided. Skipping pip install steps.'
    }

    Write-Host '[setup-all] Running app-radio setup command...'
    $radioPython = Get-VenvPython -AppPath $appRadioPath
    & $radioPython -m flask --app devradio setup

    Write-Host '[setup-all] Running app-artsy setup command...'
    $artsyPython = Get-VenvPython -AppPath $appArtsyPath
    & $artsyPython -m flask --app neera setup

    Write-Host '[setup-all] Setup complete.'
}
finally {
    Stop-ScriptLog
}
