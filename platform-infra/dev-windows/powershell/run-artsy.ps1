param(
    [ValidateSet('local', 'sso')]
    [string]$AuthMode = 'sso',
    [string]$AuthServiceUrl = 'http://127.0.0.1:5100',
    [string]$AuthClientId = 'curio-app',
    [string]$AuthClientSecret = 'dev-secret',
    [int]$Port = 5600
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

& (Join-Path $PSScriptRoot 'run-client.ps1') `
    -App 'artsy' `
    -AuthMode $AuthMode `
    -AuthServiceUrl $AuthServiceUrl `
    -AuthClientId $AuthClientId `
    -AuthClientSecret $AuthClientSecret `
    -Port $Port
