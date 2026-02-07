# Launch MiMoLo Control/Operations dev targets with a shared IPC path.
# Usage:
#   .\start_control_dev.ps1 [command]
#   .\start_control_dev.ps1 operations -- --once
#   .\start_control_dev.ps1 all-proto
#   .\start_control_dev.ps1 all-control

param(
    [string]$Command = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:TEMP) {
    $env:TEMP = [System.IO.Path]::GetTempPath()
}

$ConfigFile = Join-Path $PSScriptRoot "control_dev.toml"
$DefaultCommand = "all"
$DefaultStack = "proto"
$SocketWaitSeconds = 8
$DefaultIpcPath = Join-Path $env:TEMP "mimolo\operations.sock"

function Get-TomlValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Fallback
    )

    if (-not (Test-Path $Path)) {
        return $Fallback
    }

    $line = Get-Content -Path $Path | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if (-not $line) {
        return $Fallback
    }

    $value = ($line -split "=", 2)[1].Trim()
    $value = $value.Trim('"')

    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Fallback
    }

    return $value
}

function Load-LauncherConfig {
    $script:DefaultCommand = Get-TomlValue -Path $ConfigFile -Key "default_command" -Fallback $DefaultCommand
    $script:DefaultStack = Get-TomlValue -Path $ConfigFile -Key "default_stack" -Fallback $DefaultStack
    $socketValue = Get-TomlValue -Path $ConfigFile -Key "socket_wait_seconds" -Fallback "$SocketWaitSeconds"
    $script:SocketWaitSeconds = [int]$socketValue
    $configIpcPath = Get-TomlValue -Path $ConfigFile -Key "ipc_path" -Fallback ""
    if (-not [string]::IsNullOrWhiteSpace($configIpcPath)) {
        $script:DefaultIpcPath = $configIpcPath
    }
}

function Resolve-AllCommand {
    param([string]$InputCommand)

    if ($InputCommand -ne "all") {
        return $InputCommand
    }

    if ($DefaultStack -eq "control") {
        return "all-control"
    }

    return "all-proto"
}

Load-LauncherConfig

if (-not $env:MIMOLO_IPC_PATH) {
    $env:MIMOLO_IPC_PATH = $DefaultIpcPath
}

$ipcDir = Split-Path -Parent $env:MIMOLO_IPC_PATH
if ($ipcDir) {
    New-Item -ItemType Directory -Path $ipcDir -Force | Out-Null
}

if ([string]::IsNullOrWhiteSpace($Command)) {
    $Command = $DefaultCommand
}
$Command = Resolve-AllCommand -InputCommand $Command.ToLowerInvariant()

function Show-Usage {
    Write-Host "MiMoLo Control Dev Launcher"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  [no command] Use default_command from control_dev.toml"
    Write-Host "  env         Show current MIMOLO_IPC_PATH and launch commands"
    Write-Host "  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli monitor"
    Write-Host "  control     Launch Electron Control app (mimolo-control)"
    Write-Host "  proto       Launch Control IPC prototype (mimolo/control_proto)"
    Write-Host "  all         Alias to all-proto or all-control (default_stack in control_dev.toml)"
    Write-Host "  all-proto   Launch Operations in background, wait for IPC socket, then launch proto"
    Write-Host "  all-control Launch Operations in background, then launch Control app"
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

function Wait-ForIpcSocket {
    param(
        [int]$TimeoutSeconds,
        [System.Diagnostics.Process]$OperationsProcess
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path $env:MIMOLO_IPC_PATH) {
            return $true
        }
        if ($OperationsProcess.HasExited) {
            Write-Host "[dev-stack] Operations exited before socket became ready."
            return $false
        }
        Start-Sleep -Milliseconds 200
    }

    if (Test-Path $env:MIMOLO_IPC_PATH) {
        return $true
    }

    Write-Host "[dev-stack] IPC socket not ready after ${TimeoutSeconds}s: $env:MIMOLO_IPC_PATH"
    Write-Host "[dev-stack] Operations may not expose IPC yet in current runtime."
    return $false
}

function Run-AllTarget {
    param(
        [ValidateSet("control", "proto")]
        [string]$Target,
        [string[]]$MonitorArgs
    )

    Write-Host "[dev-stack] Starting Operations in background..."
    $opsArguments = @("run", "python", "-m", "mimolo.cli", "monitor") + $MonitorArgs
    $opsProc = Start-Process -FilePath "poetry" -ArgumentList $opsArguments -PassThru

    try {
        Write-Host "[dev-stack] Operations started (pid=$($opsProc.Id))"

        if ($Target -eq "proto") {
            Write-Host "[dev-stack] Waiting for IPC socket..."
            if (-not (Wait-ForIpcSocket -TimeoutSeconds $SocketWaitSeconds -OperationsProcess $opsProc)) {
                exit 1
            }
            Write-Host "[dev-stack] IPC socket ready."
            Write-Host "[dev-stack] Launching proto..."
            Launch-Proto
            return
        }

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

switch ($Command) {
    "help" {
        Show-Usage
    }
    "env" {
        Write-Host "MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
        Write-Host ('$env:MIMOLO_IPC_PATH="' + $env:MIMOLO_IPC_PATH + '"')
        Write-Host "default_command=$DefaultCommand"
        Write-Host "default_stack=$DefaultStack"
        Write-Host "socket_wait_seconds=$SocketWaitSeconds"
        Write-Host ""
        Write-Host "Launch commands:"
        Write-Host "  .\start_control_dev.ps1"
        Write-Host "  .\start_control_dev.ps1 operations"
        Write-Host "  .\start_control_dev.ps1 control"
        Write-Host "  .\start_control_dev.ps1 proto"
        Write-Host "  .\start_control_dev.ps1 all-proto"
        Write-Host "  .\start_control_dev.ps1 all-control"
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
        if ($DefaultStack -eq "control") {
            Run-AllTarget -Target "control" -MonitorArgs $ArgsRest
        }
        else {
            Run-AllTarget -Target "proto" -MonitorArgs $ArgsRest
        }
    }
    "all-proto" {
        Run-AllTarget -Target "proto" -MonitorArgs $ArgsRest
    }
    "all-control" {
        Run-AllTarget -Target "control" -MonitorArgs $ArgsRest
    }
    Default {
        Write-Error "Unknown command: $Command"
        Show-Usage
        exit 2
    }
}
