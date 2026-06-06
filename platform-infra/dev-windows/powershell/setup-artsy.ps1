param(
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'common.ps1')

$repoRoot = Get-RepoRoot
$appArtsyPath = Join-Path $repoRoot 'app-artsy'

if (-not $SkipInstall) {
    Write-Host '[setup-artsy] Installing app-artsy dependencies...'
    Install-Requirements -AppPath $appArtsyPath
}
else {
    Write-Host '[setup-artsy] SkipInstall provided. Skipping pip install steps.'
}

Write-Host '[setup-artsy] Running app-artsy setup command...'
$artsyPython = Get-VenvPython -AppPath $appArtsyPath
Invoke-Checked -Action 'app-artsy setup' -Command { & $artsyPython -m flask --app neera setup }

Write-Host '[setup-artsy] Setup complete.'
