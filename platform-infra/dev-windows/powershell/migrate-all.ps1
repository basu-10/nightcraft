Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'common.ps1')

$repoRoot = Get-RepoRoot
$serviceAuthPath = Join-Path $repoRoot 'service-auth'
$appRadioPath = Join-Path $repoRoot 'app-radio'
$appArtsyPath = Join-Path $repoRoot 'app-artsy'
$null = Install-Requirements -AppPath $serviceAuthPath
$servicePython = Get-VenvPython -AppPath $serviceAuthPath
$null = Install-Requirements -AppPath $appRadioPath
$null = Install-Requirements -AppPath $appArtsyPath
$radioPython = Get-VenvPython -AppPath $appRadioPath
$artsyPython = Get-VenvPython -AppPath $appArtsyPath

Write-Host '[migrate-all] Applying service-auth migrations...'
Invoke-Checked -Action 'service-auth db upgrade' -Command { & $servicePython -m flask --app (Join-Path $serviceAuthPath 'run.py') db upgrade }

Write-Host '[migrate-all] Syncing app-radio schema/setup...'
Invoke-Checked -Action 'app-radio setup' -Command { & $radioPython -m flask --app devradio setup }

Write-Host '[migrate-all] Syncing app-artsy schema/setup...'
Invoke-Checked -Action 'app-artsy setup' -Command { & $artsyPython -m flask --app neera setup }

Write-Host '[migrate-all] Migrations applied.'
