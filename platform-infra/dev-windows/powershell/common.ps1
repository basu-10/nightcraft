Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Action
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Action failed with exit code $LASTEXITCODE"
    }
}

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
}

function Get-DefaultLogRoot {
    param(
        [string]$RepoRoot = (Get-RepoRoot)
    )

    return (Join-Path $RepoRoot 'dev-logs')
}

function New-LogSessionId {
    return (Get-Date -Format 'yyyyMMdd-HHmmss')
}

function Start-ScriptLog {
    param(
        [string]$LogRoot,
        [Parameter(Mandatory = $true)]
        [string]$CategoryPath,
        [Parameter(Mandatory = $true)]
        [string]$ScriptName,
        [string]$SessionId
    )

    if (-not $LogRoot) {
        $LogRoot = Get-DefaultLogRoot
    }

    if (-not $SessionId) {
        $SessionId = New-LogSessionId
    }

    $normalizedScriptName = [System.IO.Path]::GetFileNameWithoutExtension($ScriptName)
    $logDir = Join-Path $LogRoot (Join-Path $CategoryPath $normalizedScriptName)
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null

    $logFile = Join-Path $logDir ("$SessionId-$PID.log")
    $transcriptVar = Get-Variable -Name ScriptTranscriptActive -Scope Global -ErrorAction SilentlyContinue
    $transcriptActive = $false
    if ($transcriptVar) {
        $transcriptActive = [bool]$transcriptVar.Value
    }

    if (-not $transcriptActive) {
        Start-Transcript -Path $logFile -Append | Out-Null
        $global:ScriptTranscriptActive = $true
        $global:ScriptTranscriptPath = $logFile
    }

    return $logFile
}

function Stop-ScriptLog {
    $transcriptVar = Get-Variable -Name ScriptTranscriptActive -Scope Global -ErrorAction SilentlyContinue
    $transcriptActive = $false
    if ($transcriptVar) {
        $transcriptActive = [bool]$transcriptVar.Value
    }

    if ($transcriptActive) {
        Stop-Transcript | Out-Null
        $global:ScriptTranscriptActive = $false
        $global:ScriptTranscriptPath = $null
    }
}

function Get-VenvPython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AppPath
    )

    $venvPython = Join-Path $AppPath '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv (Join-Path $AppPath '.venv')
        }
        elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv (Join-Path $AppPath '.venv')
        }
        else {
            throw 'Python was not found. Install Python 3 and rerun.'
        }
    }

    return $venvPython
}

function Install-Requirements {
    param(
        [Parameter(Mandatory = $true)]
        [string]$AppPath
    )

    $venvPython = Get-VenvPython -AppPath $AppPath
    Invoke-Checked -Action 'pip upgrade' -Command { & $venvPython -m pip install --upgrade pip }
    Invoke-Checked -Action 'requirements install' -Command { & $venvPython -m pip install -r (Join-Path $AppPath 'requirements.txt') }
}

function Start-PowerShellScriptWindow {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath,
        [string[]]$ScriptArgs = @(),
        [bool]$KeepOpen = $true
    )

    $encodedArgs = @()
    if ($KeepOpen) {
        $encodedArgs += '-NoExit'
    }

    $encodedArgs += @('-ExecutionPolicy', 'Bypass', '-File', $ScriptPath) + $ScriptArgs

    $quotedArgs = foreach ($arg in $encodedArgs) {
        if ($arg -match '[\s"]') {
            '"' + ($arg -replace '"', '`"') + '"'
        }
        else {
            $arg
        }
    }

    Start-Process -FilePath 'powershell.exe' -ArgumentList ($quotedArgs -join ' ') | Out-Null
}
