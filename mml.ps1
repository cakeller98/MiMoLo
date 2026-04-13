# Launch MiMoLo Control/Operations dev targets with a shared IPC path.
# Usage:
#   .\mml.ps1 [command]
#   .\mml.ps1 --no-cache [command]
#   .\mml.ps1 --rebuild-dist [command]
#   .\mml.ps1 --dev [command]
#   .\mml.ps1 operations -- --once
#   .\mml.ps1 all-proto
#   .\mml.ps1 all-control
#   .\mml.ps1 bundle-app -- --target proto

param(
    [switch]$NoCache,
    [switch]$Dev,
    [string]$Command = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRest
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not $env:TEMP) {
    $env:TEMP = [System.IO.Path]::GetTempPath()
}

$IsWindowsPlatform = $false
$IsMacOSPlatform = $false
if ($PSVersionTable.PSVersion.Major -ge 6) {
    $IsWindowsPlatform = [bool]$IsWindows
    $IsMacOSPlatform = [bool]$IsMacOS
}
else {
    $IsWindowsPlatform = ($env:OS -eq "Windows_NT")
    $IsMacOSPlatform = $false
}

function Get-MimoloPersistentRoot {
    if ($IsWindowsPlatform) {
        $base = $env:APPDATA
        if ([string]::IsNullOrWhiteSpace($base)) {
            $base = Join-Path $HOME "AppData\Roaming"
        }
    }
    elseif ($IsMacOSPlatform) {
        $base = Join-Path $HOME "Library/Application Support"
    }
    else {
        $base = $env:XDG_DATA_HOME
        if ([string]::IsNullOrWhiteSpace($base)) {
            $base = Join-Path $HOME ".local/share"
        }
    }

    return Join-Path $base "mimolo"
}

function Get-MimoloRuntimeRoot {
    if ($IsWindowsPlatform) {
        $base = $env:LOCALAPPDATA
        if ([string]::IsNullOrWhiteSpace($base)) {
            $base = Join-Path $HOME "AppData\Local"
        }
        return Join-Path $base "mimolo\run"
    }

    return Join-Path (Get-MimoloPersistentRoot) "run"
}

$ConfigFile = Join-Path $PSScriptRoot "mml.toml"
$DefaultCommand = "all"
$DefaultStack = "proto"
$SocketWaitSeconds = 8
$PortableRootDefault = Join-Path $PSScriptRoot "temp_debug"
$ConfigPortableRoot = ""
$ConfigDeployAgentsDefault = ""
$ConfigReleaseAgentsPath = ""
$ConfigBundleTargetDefault = ""
$ConfigBundleOutDir = ""
$ConfigBundleVersionDefault = ""
$ConfigBundleAppNameProto = ""
$ConfigBundleAppNameControl = ""
$ConfigBundleBundleIdProto = ""
$ConfigBundleBundleIdControl = ""
$ConfigBundleDevModeDefault = ""
$DefaultIpcMode = "auto"
$PersistentRoot = Get-MimoloPersistentRoot
$RuntimeRoot = Get-MimoloRuntimeRoot
$DefaultIpcPath = Join-Path $RuntimeRoot "operations.sock"
$DefaultOpsLogPath = Join-Path (Join-Path $PersistentRoot "logs") "operations.log"

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
    $configOpsLogPath = Get-TomlValue -Path $ConfigFile -Key "operations_log_path" -Fallback ""
    if (-not [string]::IsNullOrWhiteSpace($configOpsLogPath)) {
        $script:DefaultOpsLogPath = $configOpsLogPath
    }
    $script:ConfigPortableRoot = Get-TomlValue -Path $ConfigFile -Key "portable_root" -Fallback ""
    $script:ConfigDeployAgentsDefault = Get-TomlValue -Path $ConfigFile -Key "deploy_agents_default" -Fallback ""
    $script:ConfigReleaseAgentsPath = Get-TomlValue -Path $ConfigFile -Key "release_agents_path" -Fallback ""
    $script:ConfigBundleTargetDefault = Get-TomlValue -Path $ConfigFile -Key "bundle_target_default" -Fallback ""
    $script:ConfigBundleOutDir = Get-TomlValue -Path $ConfigFile -Key "bundle_out_dir" -Fallback ""
    $script:ConfigBundleVersionDefault = Get-TomlValue -Path $ConfigFile -Key "bundle_version_default" -Fallback ""
    $script:ConfigBundleAppNameProto = Get-TomlValue -Path $ConfigFile -Key "bundle_app_name_proto" -Fallback ""
    $script:ConfigBundleAppNameControl = Get-TomlValue -Path $ConfigFile -Key "bundle_app_name_control" -Fallback ""
    $script:ConfigBundleBundleIdProto = Get-TomlValue -Path $ConfigFile -Key "bundle_bundle_id_proto" -Fallback ""
    $script:ConfigBundleBundleIdControl = Get-TomlValue -Path $ConfigFile -Key "bundle_bundle_id_control" -Fallback ""
    $script:ConfigBundleDevModeDefault = Get-TomlValue -Path $ConfigFile -Key "bundle_dev_mode_default" -Fallback ""
}

function Get-SlowpokeRoot {
    param([string]$IpcPath)

    return "$IpcPath.slowpoke"
}

function Get-SlowpokePaths {
    param([string]$Root)

    return @{
        Root = $Root
        ControlToOps = Join-Path $Root "control_to_ops"
        OpsToControl = Join-Path $Root "ops_to_control"
    }
}

function Test-SamePath {
    param(
        [string]$Left,
        [string]$Right
    )

    if ([string]::IsNullOrWhiteSpace($Left) -or [string]::IsNullOrWhiteSpace($Right)) {
        return $false
    }

    try {
        $leftPath = [System.IO.Path]::GetFullPath($Left)
        $rightPath = [System.IO.Path]::GetFullPath($Right)
        return [string]::Equals($leftPath, $rightPath, [System.StringComparison]::OrdinalIgnoreCase)
    }
    catch {
        return [string]::Equals($Left, $Right, [System.StringComparison]::OrdinalIgnoreCase)
    }
}

function Resolve-IpcMode {
    if (-not [string]::IsNullOrWhiteSpace($env:MIMOLO_IPC_MODE)) {
        return $env:MIMOLO_IPC_MODE.Trim().ToLowerInvariant()
    }

    $probeArgs = @(
        "run",
        "python",
        "-c",
        "import socket,sys; sys.exit(0 if hasattr(socket, 'AF_UNIX') else 1)"
    )

    & poetry @probeArgs *> $null
    if ($LASTEXITCODE -eq 0) {
        return "unix"
    }

    return "slowpoke"
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

function Get-PortableRoot {
    $candidate = if (-not [string]::IsNullOrWhiteSpace($ConfigPortableRoot)) { $ConfigPortableRoot } else { $PortableRootDefault }
    if ([System.IO.Path]::IsPathRooted($candidate)) {
        return $candidate
    }
    return Join-Path $PSScriptRoot $candidate
}

function Run-Prepare {
    param([string[]]$PrepareArgs)

    $deployScript = Join-Path $PSScriptRoot "scripts/deploy_portable.ps1"
    if (-not (Test-Path -LiteralPath $deployScript)) {
        throw "[dev-stack] missing deploy script: $deployScript"
    }

    $portableRoot = Get-PortableRoot
    $invokeArgs = @("-PortableRoot", $portableRoot)

    if (
        -not [string]::IsNullOrWhiteSpace($ConfigDeployAgentsDefault) `
        -and ($PrepareArgs -notcontains "-Agents")
    ) {
        $agents = $ConfigDeployAgentsDefault.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
        if ($agents.Count -gt 0) {
            $invokeArgs += @("-Agents")
            $invokeArgs += $agents
        }
    }

    $hasSourceListArg = ($PrepareArgs -contains "-SourceListPath") -or ($PrepareArgs -contains "--source-list")
    if (
        -not [string]::IsNullOrWhiteSpace($env:MIMOLO_RELEASE_AGENTS_PATH) `
        -and (-not $hasSourceListArg)
    ) {
        $invokeArgs += @("-SourceListPath", $env:MIMOLO_RELEASE_AGENTS_PATH)
    }

    if ($PrepareArgs.Count -gt 0) {
        $invokeArgs += $PrepareArgs
    }

    & $deployScript @invokeArgs
}

function Invoke-Cleanup {
    Write-Host "[dev-stack] Cleaning development artifacts..."
    $removedPortable = 0
    $removedDist = 0
    $removedPyCache = 0

    $portableRoot = Get-PortableRoot
    $repoRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
    $portableRootResolved = [System.IO.Path]::GetFullPath($portableRoot)
    if ($portableRootResolved.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $portableRootResolved) {
            Remove-Item -LiteralPath $portableRootResolved -Recurse -Force
            $removedPortable = 1
        }
    }
    else {
        Write-Host "[dev-stack] Skipping portable root outside repo: $portableRootResolved"
    }

    $distDirs = Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -Directory -Filter "dist" -ErrorAction SilentlyContinue
    foreach ($dir in $distDirs) {
        if ($dir.FullName -match '[\\/]node_modules[\\/]') {
            continue
        }
        if (Test-Path -LiteralPath $dir.FullName) {
            Remove-Item -LiteralPath $dir.FullName -Recurse -Force
            $removedDist += 1
        }
    }

    $pycacheDirs = Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue
    foreach ($dir in $pycacheDirs) {
        if (Test-Path -LiteralPath $dir.FullName) {
            Remove-Item -LiteralPath $dir.FullName -Recurse -Force
            $removedPyCache += 1
        }
    }

    Write-Host "[dev-stack] Cleanup done: portable_root_removed=$removedPortable dist_removed=$removedDist pycache_removed=$removedPyCache"
}

function Invoke-NoCachePreflight {
    if (-not $NoCache.IsPresent) {
        return
    }
    Write-Host "[dev-stack] --no-cache requested: cleaning and rebuilding portable artifacts..."
    Invoke-Cleanup
    Run-Prepare
}

function Get-LatestWriteTimeUtc {
    param(
        [string[]]$Paths
    )

    $latest = [datetime]::MinValue
    foreach ($path in $Paths) {
        if (-not (Test-Path -LiteralPath $path)) {
            continue
        }
        $items = Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction SilentlyContinue
        foreach ($item in $items) {
            if ($item.LastWriteTimeUtc -gt $latest) {
                $latest = $item.LastWriteTimeUtc
            }
        }
    }
    return $latest
}

function Test-NodeTargetNeedsBuild {
    param(
        [string]$DistMainPath,
        [string[]]$SourcePaths
    )

    if (-not (Test-Path -LiteralPath $DistMainPath)) {
        return $true
    }

    $distInfo = Get-Item -LiteralPath $DistMainPath
    $latestSourceWrite = Get-LatestWriteTimeUtc -Paths $SourcePaths
    return $latestSourceWrite -gt $distInfo.LastWriteTimeUtc
}

Load-LauncherConfig

# Back-compat parse if user passes global flags positionally.
if ($Command -eq "--no-cache" -or $Command -eq "--rebuild-dist" -or $Command -eq "--dev") {
    if ($Command -eq "--dev") {
        $Dev = $true
    }
    else {
        $NoCache = $true
    }
    if ($ArgsRest.Count -gt 0) {
        $Command = $ArgsRest[0]
        if ($ArgsRest.Count -gt 1) {
            $ArgsRest = $ArgsRest[1..($ArgsRest.Count - 1)]
        }
        else {
            $ArgsRest = @()
        }
    }
    else {
        $Command = ""
    }
}

if ($ArgsRest.Count -gt 0) {
    $filtered = @()
    foreach ($arg in $ArgsRest) {
        if ($arg -eq "--no-cache" -or $arg -eq "--rebuild-dist") {
            $NoCache = $true
            continue
        }
        if ($arg -eq "--dev") {
            $Dev = $true
            continue
        }
        $filtered += $arg
    }
    $ArgsRest = $filtered
}

$LegacyDefaultIpcPath = Join-Path $env:TEMP "mimolo\operations.sock"
$LegacyDefaultOpsLogPath = Join-Path $env:TEMP "mimolo\operations.log"

if ((-not $env:MIMOLO_IPC_PATH) -or (Test-SamePath -Left $env:MIMOLO_IPC_PATH -Right $LegacyDefaultIpcPath)) {
    $env:MIMOLO_IPC_PATH = $DefaultIpcPath
}
if (-not $env:MIMOLO_IPC_MODE) {
    $env:MIMOLO_IPC_MODE = Resolve-IpcMode
}
if (
    (-not $env:MIMOLO_IPC_SLOWPOKE_ROOT) -or
    (Test-SamePath -Left $env:MIMOLO_IPC_SLOWPOKE_ROOT -Right (Get-SlowpokeRoot -IpcPath $LegacyDefaultIpcPath))
) {
    $env:MIMOLO_IPC_SLOWPOKE_ROOT = Get-SlowpokeRoot -IpcPath $env:MIMOLO_IPC_PATH
}
if ((-not $env:MIMOLO_OPS_LOG_PATH) -or (Test-SamePath -Left $env:MIMOLO_OPS_LOG_PATH -Right $LegacyDefaultOpsLogPath)) {
    $env:MIMOLO_OPS_LOG_PATH = $DefaultOpsLogPath
}
if (-not $env:MIMOLO_REPO_ROOT) {
    $env:MIMOLO_REPO_ROOT = $PSScriptRoot
}
if (-not $env:MIMOLO_RELEASE_AGENTS_PATH) {
    if (-not [string]::IsNullOrWhiteSpace($ConfigReleaseAgentsPath)) {
        if ([System.IO.Path]::IsPathRooted($ConfigReleaseAgentsPath)) {
            $env:MIMOLO_RELEASE_AGENTS_PATH = $ConfigReleaseAgentsPath
        }
        else {
            $env:MIMOLO_RELEASE_AGENTS_PATH = Join-Path $PSScriptRoot $ConfigReleaseAgentsPath
        }
    }
    else {
        $env:MIMOLO_RELEASE_AGENTS_PATH = Join-Path $PSScriptRoot "mimolo/agents/sources.json"
    }
}
if ($Dev.IsPresent) {
    $env:MIMOLO_CONTROL_DEV_MODE = "1"
}
elseif (-not $env:MIMOLO_CONTROL_DEV_MODE) {
    $env:MIMOLO_CONTROL_DEV_MODE = "0"
}

if ($env:MIMOLO_IPC_PATH.Length -gt 100) {
    Write-Host "[dev-stack] IPC path too long ($($env:MIMOLO_IPC_PATH.Length) > 100); falling back to $DefaultIpcPath"
    $env:MIMOLO_IPC_PATH = $DefaultIpcPath
}

$ipcDir = Split-Path -Parent $env:MIMOLO_IPC_PATH
if ($ipcDir) {
    New-Item -ItemType Directory -Path $ipcDir -Force | Out-Null
}
$slowpokePaths = Get-SlowpokePaths -Root $env:MIMOLO_IPC_SLOWPOKE_ROOT
$slowpokeParent = Split-Path -Parent $slowpokePaths.Root
if ($slowpokeParent) {
    New-Item -ItemType Directory -Path $slowpokeParent -Force | Out-Null
}
$opsLogDir = Split-Path -Parent $env:MIMOLO_OPS_LOG_PATH
if ($opsLogDir) {
    New-Item -ItemType Directory -Path $opsLogDir -Force | Out-Null
}

if ([string]::IsNullOrWhiteSpace($Command)) {
    $Command = $DefaultCommand
}
$Command = Resolve-AllCommand -InputCommand $Command.ToLowerInvariant()

function Show-Usage {
    $displayPortableRoot = if ([string]::IsNullOrWhiteSpace($ConfigPortableRoot)) { "./temp_debug" } else { $ConfigPortableRoot }
    $displaySeedAgents = if ([string]::IsNullOrWhiteSpace($ConfigDeployAgentsDefault)) { "<all from source list>" } else { $ConfigDeployAgentsDefault }
    $displayReleaseAgentsPath = if ([string]::IsNullOrWhiteSpace($ConfigReleaseAgentsPath)) { "./mimolo/agents/sources.json" } else { $ConfigReleaseAgentsPath }
    $displayBundleTarget = if ([string]::IsNullOrWhiteSpace($ConfigBundleTargetDefault)) { "proto" } else { $ConfigBundleTargetDefault }
    $displayBundleOutDir = if ([string]::IsNullOrWhiteSpace($ConfigBundleOutDir)) { "./temp_debug/bundles/macos" } else { $ConfigBundleOutDir }
    $displayBundleVersion = if ([string]::IsNullOrWhiteSpace($ConfigBundleVersionDefault)) { "<package version>" } else { $ConfigBundleVersionDefault }
    $displayBundleNameProto = if ([string]::IsNullOrWhiteSpace($ConfigBundleAppNameProto)) { "mimolo-proto (v<package_version>).app" } else { $ConfigBundleAppNameProto }
    $displayBundleNameControl = if ([string]::IsNullOrWhiteSpace($ConfigBundleAppNameControl)) { "MiMoLo.app" } else { $ConfigBundleAppNameControl }
    $displayBundleIdProto = if ([string]::IsNullOrWhiteSpace($ConfigBundleBundleIdProto)) { "com.mimolo.control.proto.dev" } else { $ConfigBundleBundleIdProto }
    $displayBundleIdControl = if ([string]::IsNullOrWhiteSpace($ConfigBundleBundleIdControl)) { "com.mimolo.control.dev" } else { $ConfigBundleBundleIdControl }
    $displayBundleDevMode = if ([string]::IsNullOrWhiteSpace($ConfigBundleDevModeDefault)) { "<inherit launcher env/--dev>" } else { $ConfigBundleDevModeDefault }

    Write-Host "MiMoLo Control Dev Launcher"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  [no command] Use default_command from mml.toml"
    Write-Host "  --no-cache  Global flag: cleanup and rebuild portable artifacts before launch"
    Write-Host "  --rebuild-dist Alias for --no-cache"
    Write-Host "  --dev       Global flag: enable developer-mode plugin zip install in Control/proto"
    Write-Host "  prepare     Build/sync portable bin artifacts and seed default agents"
    Write-Host "  cleanup     Remove temp_debug, all dist folders, and all __pycache__ folders"
    Write-Host "  bundle-app  Build macOS .app bundle via scripts/bundle_app.sh"
    Write-Host "  ps          List running MiMoLo-related processes (dev diagnostics)"
    Write-Host "  env         Show current MIMOLO_IPC_PATH and launch commands"
    Write-Host "  operations  Launch Operations (orchestrator): poetry run python -m mimolo.cli ops"
    Write-Host "  control     Launch Electron Control app (mimolo-control)"
    Write-Host "  proto       Launch Control IPC prototype (mimolo/control_proto)"
    Write-Host "  all         Alias to all-proto or all-control (default_stack in mml.toml)"
    Write-Host "  all-proto   Launch Operations in background, wait for IPC socket, then launch proto"
    Write-Host "  all-control Launch Operations in background, then launch Control app"
    Write-Host "  help        Show this message"
    Write-Host ""
    Write-Host "Defaults from mml.toml:"
    Write-Host "  default_command=$DefaultCommand"
    Write-Host "  default_stack=$DefaultStack"
    Write-Host "  socket_wait_seconds=$SocketWaitSeconds"
    Write-Host "  ipc_mode=$env:MIMOLO_IPC_MODE"
    Write-Host "  portable_root=$displayPortableRoot"
    Write-Host "  deploy_agents_default=$displaySeedAgents"
    Write-Host "  release_agents_path=$displayReleaseAgentsPath"
    Write-Host "  bundle_target_default=$displayBundleTarget"
    Write-Host "  bundle_out_dir=$displayBundleOutDir"
    Write-Host "  bundle_version_default=$displayBundleVersion"
    Write-Host "  bundle_app_name_proto=$displayBundleNameProto"
    Write-Host "  bundle_app_name_control=$displayBundleNameControl"
    Write-Host "  bundle_bundle_id_proto=$displayBundleIdProto"
    Write-Host "  bundle_bundle_id_control=$displayBundleIdControl"
    Write-Host "  bundle_dev_mode_default=$displayBundleDevMode"
}

function Launch-Operations {
    param([string[]]$OpsArgs)
    Write-Host "[dev-stack] MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
    Write-Host "[dev-stack] MIMOLO_IPC_MODE=$env:MIMOLO_IPC_MODE"
    Write-Host "[dev-stack] MIMOLO_IPC_SLOWPOKE_ROOT=$env:MIMOLO_IPC_SLOWPOKE_ROOT"
    Write-Host "[dev-stack] MIMOLO_OPS_LOG_PATH=$env:MIMOLO_OPS_LOG_PATH"
    poetry run python -m mimolo.cli ops @OpsArgs
}

function Show-MimoloProcesses {
    $pattern = [regex]::new("mimolo\.cli (ops|monitor)|mimolo-control|control_proto|mml\.(sh|ps1)|MiMoLo", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    Write-Host "[dev-stack] MiMoLo-related processes:"

    if ($IsWindowsPlatform) {
        $rows = Get-CimInstance Win32_Process | Where-Object {
            $cmd = if ($null -eq $_.CommandLine) { "" } else { $_.CommandLine }
            $name = if ($null -eq $_.Name) { "" } else { $_.Name }
            $cmd.Contains($PSScriptRoot) -or $pattern.IsMatch($cmd) -or $pattern.IsMatch($name)
        } | Select-Object ProcessId, ParentProcessId, Name, CommandLine

        if ($null -eq $rows -or $rows.Count -eq 0) {
            Write-Host "[dev-stack] no matching processes found."
            return
        }
        $rows | Format-Table -AutoSize
        return
    }

    try {
        $raw = & ps -axo pid,ppid,stat,etime,command
    }
    catch {
        Write-Host "[dev-stack] unable to query process table (permission denied or unsupported environment)."
        return
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[dev-stack] unable to query process table."
        return
    }
    $matches = $raw | Where-Object {
        $_ -match [regex]::Escape($PSScriptRoot) -or $pattern.IsMatch($_)
    }
    if ($null -eq $matches -or $matches.Count -eq 0) {
        Write-Host "[dev-stack] no matching processes found."
        return
    }
    $matches
}

function Launch-Control {
    Push-Location "mimolo-control"
    try {
        npx --no-install electron --version *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[dev-stack] Electron runtime missing for mimolo-control; running npm ci..."
            npm ci
            if ($LASTEXITCODE -ne 0) {
                throw "[dev-stack] npm ci failed in mimolo-control"
            }
        }
    }
    finally {
        Pop-Location
    }

    $controlMain = Join-Path $PSScriptRoot "mimolo-control/dist/main.js"
    $controlNeedsBuild = Test-NodeTargetNeedsBuild -DistMainPath $controlMain -SourcePaths @(
        (Join-Path $PSScriptRoot "mimolo-control/src"),
        (Join-Path $PSScriptRoot "mimolo-control/package.json"),
        (Join-Path $PSScriptRoot "mimolo-control/tsconfig.json")
    )
    if ($controlNeedsBuild) {
        Write-Host "[dev-stack] Building mimolo-control..."
        Push-Location "mimolo-control"
        try {
            npm run build
            if ($LASTEXITCODE -ne 0) {
                throw "[dev-stack] mimolo-control build failed"
            }
        }
        finally {
            Pop-Location
        }
    }

    if (-not (Test-Path -LiteralPath $controlMain)) {
        throw "[dev-stack] mimolo-control did not produce dist/main.js"
    }

    Write-Host "[dev-stack] MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
    Write-Host "[dev-stack] MIMOLO_IPC_MODE=$env:MIMOLO_IPC_MODE"
    Write-Host "[dev-stack] MIMOLO_CONTROL_DEV_MODE=$env:MIMOLO_CONTROL_DEV_MODE"
    Push-Location "mimolo-control"
    try {
        npm run start
        if ($LASTEXITCODE -ne 0) {
            throw "[dev-stack] mimolo-control start failed"
        }
    }
    finally {
        Pop-Location
    }
}

function Launch-Proto {
    Push-Location "mimolo-control"
    try {
        npx --no-install electron --version *> $null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[dev-stack] Electron runtime missing for control_proto launch; running npm ci in mimolo-control..."
            npm ci
            if ($LASTEXITCODE -ne 0) {
                throw "[dev-stack] npm ci failed in mimolo-control"
            }
        }
    }
    finally {
        Pop-Location
    }

    $protoTsc = Join-Path $PSScriptRoot "mimolo/control_proto/node_modules/.bin/tsc.cmd"
    if (-not (Test-Path -LiteralPath $protoTsc)) {
        Write-Host "[dev-stack] TypeScript toolchain missing for control_proto; running npm ci in mimolo/control_proto..."
        Push-Location "mimolo/control_proto"
        try {
            npm ci
            if ($LASTEXITCODE -ne 0) {
                throw "[dev-stack] npm ci failed in mimolo/control_proto"
            }
        }
        finally {
            Pop-Location
        }
    }

    $protoMain = Join-Path $PSScriptRoot "mimolo/control_proto/dist/main.js"
    $protoNeedsBuild = Test-NodeTargetNeedsBuild -DistMainPath $protoMain -SourcePaths @(
        (Join-Path $PSScriptRoot "mimolo/control_proto/src"),
        (Join-Path $PSScriptRoot "mimolo/control_proto/package.json"),
        (Join-Path $PSScriptRoot "mimolo/control_proto/tsconfig.json")
    )
    if ($protoNeedsBuild) {
        Write-Host "[dev-stack] Building control_proto..."
        Push-Location "mimolo/control_proto"
        try {
            npm run build
            if ($LASTEXITCODE -ne 0) {
                throw "[dev-stack] control_proto build failed"
            }
        }
        finally {
            Pop-Location
        }
    }

    if (-not (Test-Path -LiteralPath $protoMain)) {
        throw "[dev-stack] control_proto did not produce dist/main.js"
    }

    Write-Host "[dev-stack] MIMOLO_IPC_PATH=$env:MIMOLO_IPC_PATH"
    Write-Host "[dev-stack] MIMOLO_IPC_MODE=$env:MIMOLO_IPC_MODE"
    Write-Host "[dev-stack] MIMOLO_IPC_SLOWPOKE_ROOT=$env:MIMOLO_IPC_SLOWPOKE_ROOT"
    Write-Host "[dev-stack] MIMOLO_OPS_LOG_PATH=$env:MIMOLO_OPS_LOG_PATH"
    Write-Host "[dev-stack] MIMOLO_CONTROL_DEV_MODE=$env:MIMOLO_CONTROL_DEV_MODE"
    Push-Location "mimolo/control_proto"
    try {
        npm run start
        if ($LASTEXITCODE -ne 0) {
            throw "[dev-stack] control_proto start failed"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-BundleApp {
    param([string[]]$BundleArgs)

    $bundleScript = Join-Path $PSScriptRoot "scripts/bundle_app.ps1"
    if (-not (Test-Path -LiteralPath $bundleScript)) {
        throw "[dev-stack] missing bundle script: $bundleScript"
    }
    & $bundleScript @BundleArgs
}

function Wait-ForIpcSocket {
    param(
        [int]$TimeoutSeconds,
        [System.Diagnostics.Process]$OperationsProcess = $null
    )

    function Test-IpcPingUnix {
        $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
        if (-not $pythonCmd) {
            $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
        }

        if (-not $pythonCmd) {
            # If Python is unavailable, fall back to socket-file existence only.
            return $true
        }

        $pythonCode = 'import socket,sys
p=sys.argv[1]
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.settimeout(0.25)
s.connect(p)
s.sendall(b"{\"cmd\":\"ping\"}\n")
data=s.recv(4096).decode("utf-8","ignore")
s.close()
sys.exit(0 if "\"ok\": true" in data or "\"ok\":true" in data else 1)'

        & $pythonCmd.Source -c $pythonCode $env:MIMOLO_IPC_PATH *> $null
        return ($LASTEXITCODE -eq 0)
    }

    function Test-IpcPingSlowpoke {
        $paths = Get-SlowpokePaths -Root $env:MIMOLO_IPC_SLOWPOKE_ROOT
        if (-not (Test-Path $paths.ControlToOps) -or -not (Test-Path $paths.OpsToControl)) {
            return $false
        }

        $requestId = "launcher-ping-$([guid]::NewGuid().ToString('N'))"
        $tempPath = Join-Path $paths.ControlToOps "$requestId.tmp"
        $requestPath = Join-Path $paths.ControlToOps "$requestId.json"
        $requestPayload = @{
            cmd = "ping"
            request_id = $requestId
        } | ConvertTo-Json -Compress

        Set-Content -LiteralPath $tempPath -Value $requestPayload -NoNewline
        Move-Item -LiteralPath $tempPath -Destination $requestPath -Force

        $deadline = (Get-Date).AddSeconds(1)
        while ((Get-Date) -lt $deadline) {
            $responseFiles = Get-ChildItem -LiteralPath $paths.OpsToControl -Filter "*.json" -File -ErrorAction SilentlyContinue | Sort-Object Name
            foreach ($responseFile in $responseFiles) {
                try {
                    $raw = Get-Content -LiteralPath $responseFile.FullName -Raw
                    $payload = $raw | ConvertFrom-Json
                    Remove-Item -LiteralPath $responseFile.FullName -Force -ErrorAction SilentlyContinue
                    if ($payload.request_id -eq $requestId -and $payload.ok -eq $true) {
                        return $true
                    }
                }
                catch {
                    Remove-Item -LiteralPath $responseFile.FullName -Force -ErrorAction SilentlyContinue
                }
            }
            Start-Sleep -Milliseconds 100
        }

        return $false
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($env:MIMOLO_IPC_MODE -eq "slowpoke") {
            if (Test-IpcPingSlowpoke) {
                return $true
            }
        }
        elseif ((Test-Path $env:MIMOLO_IPC_PATH) -and (Test-IpcPingUnix)) {
            return $true
        }
        if ($null -ne $OperationsProcess -and $OperationsProcess.HasExited) {
            Write-Host "[dev-stack] Operations exited before socket became ready."
            return $false
        }
        Start-Sleep -Milliseconds 200
    }

    if ($env:MIMOLO_IPC_MODE -eq "slowpoke") {
        if (Test-IpcPingSlowpoke) {
            return $true
        }
    }
    elseif (Test-Path $env:MIMOLO_IPC_PATH) {
        return $true
    }

    if ($env:MIMOLO_IPC_MODE -eq "slowpoke") {
        Write-Host "[dev-stack] IPC slowpoke transport not ready after ${TimeoutSeconds}s: $env:MIMOLO_IPC_SLOWPOKE_ROOT"
    }
    else {
        Write-Host "[dev-stack] IPC socket not ready after ${TimeoutSeconds}s: $env:MIMOLO_IPC_PATH"
    }
    Write-Host "[dev-stack] Operations may not expose IPC yet in current runtime."
    return $false
}

function Run-AllTarget {
    param(
        [ValidateSet("control", "proto")]
        [string]$Target,
        [string[]]$OpsArgs
    )

    Write-Host "[dev-stack] Starting Operations in background..."
    if (Wait-ForIpcSocket -TimeoutSeconds 1) {
        Write-Host "[dev-stack] Existing Operations instance detected; reusing current IPC endpoint."
        if ($Target -eq "proto") {
            Write-Host "[dev-stack] Launching proto..."
            Launch-Proto
            return
        }

        Write-Host "[dev-stack] Launching Control app..."
        Launch-Control
        return
    }

    $opsArguments = @("run", "python", "-m", "mimolo.cli", "ops") + $OpsArgs
    if ($Target -eq "proto") {
        try {
            Set-Content -Path $env:MIMOLO_OPS_LOG_PATH -Value ""
        }
        catch {
            Write-Host "[dev-stack] Operations log is busy; preserving existing file: $env:MIMOLO_OPS_LOG_PATH"
        }
        Write-Host "[dev-stack] Operations log file: $env:MIMOLO_OPS_LOG_PATH"
        $opsProc = Start-Process -FilePath "poetry" -ArgumentList $opsArguments -PassThru -RedirectStandardOutput $env:MIMOLO_OPS_LOG_PATH
    }
    else {
        $opsProc = Start-Process -FilePath "poetry" -ArgumentList $opsArguments -PassThru
    }

    $autoStopOnExit = $env:MML_AUTOSTOP_ON_EXIT -eq "1"
    if (-not $autoStopOnExit) {
        Write-Host "[dev-stack] Operations will remain running after Control exits (set MML_AUTOSTOP_ON_EXIT=1 to restore auto-stop)."
    }

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
        if ($autoStopOnExit -and -not $opsProc.HasExited) {
            Write-Host "[dev-stack] MML_AUTOSTOP_ON_EXIT=1 -> stopping Operations (pid=$($opsProc.Id))..."
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
        Write-Host "MIMOLO_IPC_MODE=$env:MIMOLO_IPC_MODE"
        Write-Host ('$env:MIMOLO_IPC_MODE="' + $env:MIMOLO_IPC_MODE + '"')
        Write-Host "MIMOLO_IPC_SLOWPOKE_ROOT=$env:MIMOLO_IPC_SLOWPOKE_ROOT"
        Write-Host ('$env:MIMOLO_IPC_SLOWPOKE_ROOT="' + $env:MIMOLO_IPC_SLOWPOKE_ROOT + '"')
        Write-Host "MIMOLO_OPS_LOG_PATH=$env:MIMOLO_OPS_LOG_PATH"
        Write-Host ('$env:MIMOLO_OPS_LOG_PATH="' + $env:MIMOLO_OPS_LOG_PATH + '"')
        Write-Host "MIMOLO_REPO_ROOT=$env:MIMOLO_REPO_ROOT"
        Write-Host ('$env:MIMOLO_REPO_ROOT="' + $env:MIMOLO_REPO_ROOT + '"')
        Write-Host "MIMOLO_RELEASE_AGENTS_PATH=$env:MIMOLO_RELEASE_AGENTS_PATH"
        Write-Host ('$env:MIMOLO_RELEASE_AGENTS_PATH="' + $env:MIMOLO_RELEASE_AGENTS_PATH + '"')
        Write-Host "default_command=$DefaultCommand"
        Write-Host "default_stack=$DefaultStack"
        Write-Host "socket_wait_seconds=$SocketWaitSeconds"
        Write-Host "control_dev_mode=$env:MIMOLO_CONTROL_DEV_MODE"
        Write-Host "deploy_agents_default=$(if ([string]::IsNullOrWhiteSpace($ConfigDeployAgentsDefault)) { '<all from source list>' } else { $ConfigDeployAgentsDefault })"
        Write-Host "release_agents_path=$(if ([string]::IsNullOrWhiteSpace($ConfigReleaseAgentsPath)) { './mimolo/agents/sources.json' } else { $ConfigReleaseAgentsPath })"
        Write-Host "bundle_target_default=$(if ([string]::IsNullOrWhiteSpace($ConfigBundleTargetDefault)) { 'proto' } else { $ConfigBundleTargetDefault })"
        Write-Host "bundle_out_dir=$(if ([string]::IsNullOrWhiteSpace($ConfigBundleOutDir)) { './temp_debug/bundles/macos' } else { $ConfigBundleOutDir })"
        Write-Host "bundle_version_default=$ConfigBundleVersionDefault"
        Write-Host "bundle_app_name_proto=$ConfigBundleAppNameProto"
        Write-Host "bundle_app_name_control=$ConfigBundleAppNameControl"
        Write-Host "bundle_bundle_id_proto=$(if ([string]::IsNullOrWhiteSpace($ConfigBundleBundleIdProto)) { 'com.mimolo.control.proto.dev' } else { $ConfigBundleBundleIdProto })"
        Write-Host "bundle_bundle_id_control=$(if ([string]::IsNullOrWhiteSpace($ConfigBundleBundleIdControl)) { 'com.mimolo.control.dev' } else { $ConfigBundleBundleIdControl })"
        Write-Host "bundle_dev_mode_default=$ConfigBundleDevModeDefault"
        Write-Host "no_cache_supported=true"
        Write-Host ""
        Write-Host "Launch commands:"
        Write-Host "  .\mml.ps1"
        Write-Host "  .\mml.ps1 prepare"
        Write-Host "  .\mml.ps1 cleanup"
        Write-Host "  .\mml.ps1 --no-cache [command]"
        Write-Host "  .\mml.ps1 --rebuild-dist [command]"
        Write-Host "  .\mml.ps1 --dev [command]"
        Write-Host "  .\mml.ps1 operations"
        Write-Host "  .\mml.ps1 ps"
        Write-Host "  .\mml.ps1 control"
        Write-Host "  .\mml.ps1 proto"
        Write-Host "  .\mml.ps1 all-proto"
        Write-Host "  .\mml.ps1 all-control"
        Write-Host "  .\mml.ps1 bundle-app -- --target proto"
    }
    "operations" {
        Invoke-NoCachePreflight
        Launch-Operations -OpsArgs $ArgsRest
    }
    "ps" {
        Show-MimoloProcesses
    }
    "processes" {
        Show-MimoloProcesses
    }
    "prepare" {
        if ($NoCache.IsPresent) {
            Write-Host "[dev-stack] --no-cache requested: cleaning before prepare..."
            Invoke-Cleanup
        }
        Run-Prepare -PrepareArgs $ArgsRest
    }
    "cleanup" {
        Invoke-Cleanup
    }
    "bundle-app" {
        Invoke-NoCachePreflight
        Invoke-BundleApp -BundleArgs $ArgsRest
    }
    "control" {
        Invoke-NoCachePreflight
        Launch-Control
    }
    "proto" {
        Invoke-NoCachePreflight
        Launch-Proto
    }
    "all" {
        Invoke-NoCachePreflight
        if ($DefaultStack -eq "control") {
            Run-AllTarget -Target "control" -OpsArgs $ArgsRest
        }
        else {
            Run-AllTarget -Target "proto" -OpsArgs $ArgsRest
        }
    }
    "all-proto" {
        Invoke-NoCachePreflight
        Run-AllTarget -Target "proto" -OpsArgs $ArgsRest
    }
    "all-control" {
        Invoke-NoCachePreflight
        Run-AllTarget -Target "control" -OpsArgs $ArgsRest
    }
    Default {
        Write-Error "Unknown command: $Command"
        Show-Usage
        exit 2
    }
}
