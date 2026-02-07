# Launch MiMoLo Control/Operations dev targets with a shared IPC path.
# Usage:
#   .\start_control_dev.ps1 env
#   .\start_control_dev.ps1 operations -- --once
#   .\start_control_dev.ps1 control
#   .\start_control_dev.ps1 proto
#   .\start_control_dev.ps1 all

param(
    [string]$Command = "help",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:MIMOLO_IPC_PATH) {
    $env:MIMOLO_IPC_PATH = Join-Path $env:TEMP "mimolo\operations.sock"
}

$ipcDir = Split-Path -Parent $env:MIMOLO_IPC_PATH
if ($ipcDir) {
    New-Item -ItemType Directory -Path $ipcDir -Force | Out-Null
}

function Show-Usage {
    Write-Host "MiMoLo Control Dev Launcher"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  env         Show current MIMOLO_IPC_PATH and launch commands"
    Write-Host "  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli monitor"
    Write-Host "  control     Launch Electron Control app (mimolo-control)"
    Write-Host "  proto       Launch Control IPC prototype (mimolo/control_proto)"
    Write-Host "  all         Launch Operations in background, then launch Control app"
    Write-Host "  help        Show this message"
}

function Launch-Operations {
    param([string[]]$MonitorArgs)
    Write-Host "[dev-stack] MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
    poetry run python -m mimolo.cli monitor @MonitorArgs
}

function Launch-Control {
    Write-Host "[dev-stack] MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
    Push-Location "mimolo-control"
    try {
        npm run start
    }
    finally {
        Pop-Location
    }
}

function Launch-Proto {
    Write-Host "[dev-stack] MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
    Push-Location "mimolo/control_proto"
    try {
        npm run start
    }
    finally {
        Pop-Location
    }
}

switch ($Command.ToLowerInvariant()) {
    "help" {
        Show-Usage
    }
    "env" {
        Write-Host "MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
        Write-Host ""
        Write-Host "Launch commands:"
        Write-Host "  .\start_control_dev.ps1 operations"
        Write-Host "  .\start_control_dev.ps1 control"
        Write-Host "  .\start_control_dev.ps1 proto"
    }
    "operations" {
        Launch-Operations -MonitorArgs $ArgsRest
    }
    "control" {
        Launch-Control
    }
    "proto" {
        Launch-Proto
    }
    "all" {
        Write-Host "[dev-stack] Starting Operations in background..."
        $opsProc = Start-Process -FilePath "poetry" -ArgumentList @("run", "python", "-m", "mimolo.cli", "monitor") -PassThru
        try {
            Write-Host "[dev-stack] Operations started (pid=$($opsProc.Id))"
            Write-Host "[dev-stack] Launching Control app..."
            Launch-Control
        }
        finally {
            if (-not $opsProc.HasExited) {
                Write-Host "[dev-stack] Stopping Operations (pid=$($opsProc.Id))..."
                Stop-Process -Id $opsProc.Id -Force
            }
        }
    }
    Default {
        Write-Error "Unknown command: $Command"
        Show-Usage
        exit 2
    }
}
