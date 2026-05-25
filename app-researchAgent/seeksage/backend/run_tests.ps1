#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run the SeekSage backend test suite.

.DESCRIPTION
    Activates the venv, sets PYTHONPATH, and runs pytest.
    Pass arguments through to pytest: e.g. .\run_tests.ps1 -Live -Coverage

.PARAMETER Suite
    Which suite to run:
      unit         — fast isolated tests only (default)
      integration  — unit + integration (needs app context)
      live         — unit + integration + live (needs OPENROUTER_API_KEY)
      all          — everything

.PARAMETER Coverage
    Generate an HTML coverage report in tests/htmlcov/

.PARAMETER Verbose
    Pass -v -s to pytest (show stdout / print() output)

.PARAMETER Filter
    Pytest -k expression to select specific tests, e.g. "TestToolCache"

.PARAMETER Durations
    Show N slowest tests (default 10)

.EXAMPLE
    .\run_tests.ps1
    .\run_tests.ps1 -Suite live
    .\run_tests.ps1 -Suite unit -Coverage
    .\run_tests.ps1 -Filter "TestToolCache or test_record_fields" -Verbose
#>

param(
    [ValidateSet("unit", "integration", "live", "all")]
    [string]$Suite = "integration",

    [switch]$Coverage,
    [switch]$Verbose,
    [string]$Filter = "",
    [int]$Durations = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$TestDir = Join-Path $ScriptDir "tests"

if (-not (Test-Path $VenvPython)) {
    Write-Error "venv not found at $VenvPython. Run setup.ps1 first."
    exit 1
}

# Load .env.test into this shell so OPENROUTER_API_KEY etc. are available
$EnvTestFile = Join-Path $TestDir ".env.test"
if (Test-Path $EnvTestFile) {
    Get-Content $EnvTestFile | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
            Write-Host "  env: $key=***" -ForegroundColor DarkGray
        }
    }
}

# Build marker expression
$markerExpr = switch ($Suite) {
    "unit" { "unit" }
    "integration" { "unit or integration" }
    "live" { "unit or integration or live" }
    "all" { "" }     # no filter — run everything
}

# Build pytest args list
$args = @(
    "-m", $markerExpr,
    "--durations=$Durations"
)

if ($Coverage) {
    $args += @(
        "--cov=app",
        "--cov-report=term-missing",
        "--cov-report=html:tests/htmlcov",
        "--cov-fail-under=0"    # set to e.g. 70 to enforce minimum coverage
    )
}

if ($Verbose) {
    $args += @("-v", "-s")
}

if ($Filter) {
    $args += @("-k", $Filter)
}

# Set PYTHONPATH so `from app import ...` resolves
$env:PYTHONPATH = $ScriptDir

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "  SeekSage Backend Test Suite" -ForegroundColor Cyan
Write-Host "  Suite   : $Suite" -ForegroundColor Cyan
Write-Host "  Markers : $markerExpr" -ForegroundColor Cyan
if ($Filter) { Write-Host "  Filter  : $Filter" -ForegroundColor Cyan }
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

& $VenvPython -m pytest $args

$exitCode = $LASTEXITCODE
if ($exitCode -eq 0) {
    Write-Host ""
    Write-Host "All tests passed." -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "Tests FAILED (exit code $exitCode)." -ForegroundColor Red
}

exit $exitCode
