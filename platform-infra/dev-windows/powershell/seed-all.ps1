param(
    [string]$Username = 'devuser',
    [string]$Email = 'devuser@example.com',
    [string]$Password = 'devpass123',
    [Alias('ClientId')]
    [string]$RadioClientId = 'radio-app',
    [Alias('ClientSecret')]
    [string]$RadioClientSecret = 'dev-secret',
    [int]$RadioPort = 5000,
    [switch]$IncludeArtsy,
    [string]$ArtsyClientId = 'curio-app',
    [string]$ArtsyClientSecret = 'dev-secret',
    [int]$ArtsyPort = 5600,
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
    Write-Host "[seed-all] Log file: $logFile"

    $repoRoot = Get-RepoRoot
    $serviceAuthPath = Join-Path $repoRoot 'service-auth'
    $null = Install-Requirements -AppPath $serviceAuthPath
    $servicePython = Get-VenvPython -AppPath $serviceAuthPath
    $radioRedirectUri = "http://127.0.0.1:$RadioPort/auth/callback"

    Write-Host "[seed-all] Seeding service-auth for app-radio redirect URI: $radioRedirectUri"
    Invoke-Checked -Action 'service-auth seed-dev' -Command {
        & $servicePython -m flask --app (Join-Path $serviceAuthPath 'run.py') seed-dev `
            --username $Username `
            --email $Email `
            --password $Password `
            --client-id $RadioClientId `
            --client-secret $RadioClientSecret `
            --redirect-uri $radioRedirectUri
    }

    if ($IncludeArtsy) {
        $artsyRedirectUri = "http://127.0.0.1:$ArtsyPort/auth/callback"
        Write-Host "[seed-all] Seeding service-auth for app-artsy redirect URI: $artsyRedirectUri"
        Invoke-Checked -Action 'service-auth seed-dev (curio)' -Command {
            & $servicePython -m flask --app (Join-Path $serviceAuthPath 'run.py') seed-dev `
                --username $Username `
                --email $Email `
                --password $Password `
                --client-id $ArtsyClientId `
                --client-secret $ArtsyClientSecret `
                --redirect-uri $artsyRedirectUri
        }

        $artsyPath = Join-Path $repoRoot 'app-artsy'
        $null = Install-Requirements -AppPath $artsyPath
        $artsyPython = Get-VenvPython -AppPath $artsyPath

        Write-Host '[seed-all] Seeding Curio catalog items for app-artsy'
        Invoke-Checked -Action 'app-artsy seed-catalog' -Command {
            & $artsyPython -m flask --app (Join-Path $artsyPath 'run.py') seed-catalog
        }
    }

    Write-Host '[seed-all] Seed complete.'
}
finally {
    Stop-ScriptLog
}
