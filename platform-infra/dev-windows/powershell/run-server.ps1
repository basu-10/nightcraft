param(
	[string]$LogRoot = '',
	[string]$LogSessionId = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

. (Join-Path $PSScriptRoot 'common.ps1')

$repoRoot = Get-RepoRoot
$serviceAuthPath = Join-Path $repoRoot 'service-auth'
$servicePython = Get-VenvPython -AppPath $serviceAuthPath

$logFile = Start-ScriptLog `
	-LogRoot $LogRoot `
	-CategoryPath 'service-auth' `
	-ScriptName $MyInvocation.MyCommand.Name `
	-SessionId $LogSessionId

try {
	Write-Host "[run-server] Log file: $logFile"
	Write-Host '[run-server] Starting service-auth at http://127.0.0.1:5100'
	Set-Location $serviceAuthPath
	& $servicePython run.py
}
finally {
	Stop-ScriptLog
}
