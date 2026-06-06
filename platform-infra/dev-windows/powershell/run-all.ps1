<#
run:
.\run-all.ps1 to start auth + radio + artsy by default
.\run-all.ps1 -SkipArtsy if you only want auth + radio
#>

param(
    [switch]$SkipSeed,
    [switch]$IncludeArtsy,
    [switch]$SkipArtsy,
    [int]$RadioPort = 5000,
    [int]$ArtsyPort = 5600,
    [string]$AuthServiceUrl = 'http://127.0.0.1:5100',
    [string]$RadioClientId = 'radio-app',
    [string]$RadioClientSecret = 'dev-secret',
    [string]$ArtsyClientId = 'neera-app',
    [string]$ArtsyClientSecret = 'dev-secret',
    [string]$LogRoot = '',
    [string]$LogSessionId = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $LogRoot) {
    $LogRoot = Get-DefaultLogRoot
}

if (-not $LogSessionId) {
    $LogSessionId = New-LogSessionId
}

$runAllLog = Start-ScriptLog `
    -LogRoot $LogRoot `
    -CategoryPath 'platform-infra/dev-windows/powershell' `
    -ScriptName $MyInvocation.MyCommand.Name `
    -SessionId $LogSessionId

try {
    $shouldLaunchArtsy = $true
    if ($PSBoundParameters.ContainsKey('IncludeArtsy')) {
        $shouldLaunchArtsy = [bool]$IncludeArtsy
    }
    if ($SkipArtsy) {
        $shouldLaunchArtsy = $false
    }

    Write-Host "[run-all] Logs root: $LogRoot"
    Write-Host "[run-all] Session id: $LogSessionId"
    Write-Host "[run-all] This script log: $runAllLog"
    Write-Host "[run-all] Launch app-artsy: $shouldLaunchArtsy"

    if (-not $SkipSeed) {
        & (Join-Path $PSScriptRoot 'seed-all.ps1') `
            -RadioPort $RadioPort `
            -RadioClientId $RadioClientId `
            -RadioClientSecret $RadioClientSecret `
            -IncludeArtsy:$shouldLaunchArtsy `
            -ArtsyPort $ArtsyPort `
            -ArtsyClientId $ArtsyClientId `
            -ArtsyClientSecret $ArtsyClientSecret `
            -LogRoot $LogRoot `
            -LogSessionId $LogSessionId
    }

    Write-Host '[run-all] Launching service-auth in a new window...'
    Start-PowerShellScriptWindow -ScriptPath (Join-Path $PSScriptRoot 'run-server.ps1') -ScriptArgs @(
        '-LogRoot', $LogRoot,
        '-LogSessionId', $LogSessionId
    )

    Write-Host '[run-all] Launching app-radio in a new window...'
    Start-PowerShellScriptWindow -ScriptPath (Join-Path $PSScriptRoot 'run-client.ps1') -ScriptArgs @(
        '-App', 'radio',
        '-AuthMode', 'sso',
        '-AuthServiceUrl', $AuthServiceUrl,
        '-AuthClientId', $RadioClientId,
        '-AuthClientSecret', $RadioClientSecret,
        '-Port', $RadioPort,
        '-LogRoot', $LogRoot,
        '-LogSessionId', $LogSessionId
    )

    if ($shouldLaunchArtsy) {
        Write-Host '[run-all] Launching app-artsy in a new window...'
        Start-PowerShellScriptWindow -ScriptPath (Join-Path $PSScriptRoot 'run-client.ps1') -ScriptArgs @(
            '-App', 'artsy',
            '-AuthMode', 'sso',
            '-AuthServiceUrl', $AuthServiceUrl,
            '-AuthClientId', $ArtsyClientId,
            '-AuthClientSecret', $ArtsyClientSecret,
            '-Port', $ArtsyPort,
            '-LogRoot', $LogRoot,
            '-LogSessionId', $LogSessionId
        )
    }
    else {
        Write-Host '[run-all] Skipping app-artsy launch.'
    }

    Write-Host '[run-all] All processes were started in separate PowerShell windows.'
}
finally {
    Stop-ScriptLog
}
