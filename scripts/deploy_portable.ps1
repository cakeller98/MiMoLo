# Portable deploy utility (PowerShell, cross-platform)
# Works on macOS/Windows/Linux with PowerShell 7.5+

[CmdletBinding()]
param(
    [string]$PortableRoot = "",
    [string]$DataDir = "",
    [string]$BinDir = "",
    [string]$RuntimeConfigPath = "",
    [string]$ConfigSourcePath = "",
    [string[]]$Agents = @(),
    [string]$SourceListPath = "",
    [switch]$NoBuild,
    [switch]$ForceSync
)

$ErrorActionPreference = "Stop"

function Resolve-DefaultPath {
    param(
        [string]$Value,
        [string]$Fallback
    )
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $Fallback
    }
    return $Value
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Should-CopyFile {
    param(
        [string]$SourcePath,
        [string]$DestinationPath
    )
    if (-not (Test-Path -LiteralPath $DestinationPath)) {
        return $true
    }
    $src = Get-Item -LiteralPath $SourcePath
    $dst = Get-Item -LiteralPath $DestinationPath
    if ($src.Length -ne $dst.Length) {
        return $true
    }
    return ($src.LastWriteTimeUtc -gt $dst.LastWriteTimeUtc)
}

function Sync-File {
    param(
        [string]$SourcePath,
        [string]$DestinationPath
    )
    Ensure-Directory -Path (Split-Path -Parent $DestinationPath)
    if (Should-CopyFile -SourcePath $SourcePath -DestinationPath $DestinationPath) {
        Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath -Force
    }
}

function Test-ExcludedPath {
    param(
        [string]$RelativePath,
        [string[]]$ExcludedDirectoryNames,
        [string[]]$ExcludedFilePatterns
    )
    $parts = $RelativePath -split '[\\/]'
    foreach ($part in $parts) {
        if ($ExcludedDirectoryNames -contains $part) {
            return $true
        }
    }
    foreach ($pattern in $ExcludedFilePatterns) {
        if ($RelativePath -like $pattern) {
            return $true
        }
    }
    return $false
}

function Sync-Directory {
    param(
        [string]$SourceDir,
        [string]$DestinationDir,
        [string[]]$ExcludedDirectoryNames = @(),
        [string[]]$ExcludedFilePatterns = @(),
        [switch]$Force
    )
    Ensure-Directory -Path $DestinationDir

    if ($Force.IsPresent -and (Test-Path -LiteralPath $DestinationDir)) {
        Remove-Item -LiteralPath $DestinationDir -Recurse -Force
        Ensure-Directory -Path $DestinationDir
    }

    $sourceFiles = @{}
    $srcRoot = (Resolve-Path -LiteralPath $SourceDir).Path
    $dstRoot = (Resolve-Path -LiteralPath $DestinationDir).Path

    Get-ChildItem -LiteralPath $SourceDir -Recurse -File | ForEach-Object {
        $relative = [System.IO.Path]::GetRelativePath($srcRoot, $_.FullName)
        if (Test-ExcludedPath -RelativePath $relative -ExcludedDirectoryNames $ExcludedDirectoryNames -ExcludedFilePatterns $ExcludedFilePatterns) {
            return
        }
        $sourceFiles[$relative] = $_.FullName
        $targetPath = Join-Path $dstRoot $relative
        Ensure-Directory -Path (Split-Path -Parent $targetPath)
        if (Should-CopyFile -SourcePath $_.FullName -DestinationPath $targetPath) {
            Copy-Item -LiteralPath $_.FullName -Destination $targetPath -Force
        }
    }

    Get-ChildItem -LiteralPath $DestinationDir -Recurse -File | ForEach-Object {
        $relative = [System.IO.Path]::GetRelativePath($dstRoot, $_.FullName)
        if (-not $sourceFiles.ContainsKey($relative)) {
            Remove-Item -LiteralPath $_.FullName -Force
        }
    }

    Get-ChildItem -LiteralPath $DestinationDir -Recurse -Directory |
        Sort-Object FullName -Descending |
        ForEach-Object {
            if (-not (Get-ChildItem -LiteralPath $_.FullName -Force | Select-Object -First 1)) {
                Remove-Item -LiteralPath $_.FullName -Force
            }
        }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $scriptDir "..")).Path
Set-Location $repoRoot

$portableRootDefault = Join-Path $repoRoot "temp_debug"
$PortableRoot = Resolve-DefaultPath -Value $PortableRoot -Fallback $portableRootDefault

$defaultDataDir = if ($env:MIMOLO_DATA_DIR) { $env:MIMOLO_DATA_DIR } else { Join-Path $PortableRoot "user_home/mimolo" }
$defaultBinDir = if ($env:MIMOLO_BIN_DIR) { $env:MIMOLO_BIN_DIR } else { Join-Path $PortableRoot "bin" }
$defaultRuntimeConfig = if ($env:MIMOLO_RUNTIME_CONFIG_PATH) { $env:MIMOLO_RUNTIME_CONFIG_PATH } else { Join-Path $defaultDataDir "operations/mimolo.portable.toml" }
$defaultConfigSource = if ($env:MIMOLO_CONFIG_SOURCE_PATH) { $env:MIMOLO_CONFIG_SOURCE_PATH } else { Join-Path $repoRoot "mimolo.toml" }
$defaultSourceListPath = if ($env:MIMOLO_RELEASE_AGENTS_PATH) { $env:MIMOLO_RELEASE_AGENTS_PATH } else { Join-Path $repoRoot "mimolo/agents/sources.json" }

$DataDir = Resolve-DefaultPath -Value $DataDir -Fallback $defaultDataDir
$BinDir = Resolve-DefaultPath -Value $BinDir -Fallback $defaultBinDir
$RuntimeConfigPath = Resolve-DefaultPath -Value $RuntimeConfigPath -Fallback $defaultRuntimeConfig
$ConfigSourcePath = Resolve-DefaultPath -Value $ConfigSourcePath -Fallback $defaultConfigSource
$SourceListPath = Resolve-DefaultPath -Value $SourceListPath -Fallback $defaultSourceListPath
if (-not [System.IO.Path]::IsPathRooted($SourceListPath)) {
    $SourceListPath = Join-Path $repoRoot $SourceListPath
}

Ensure-Directory -Path $PortableRoot
Ensure-Directory -Path $DataDir
Ensure-Directory -Path $BinDir
Ensure-Directory -Path (Split-Path -Parent $RuntimeConfigPath)

if (-not (Test-Path -LiteralPath $ConfigSourcePath)) {
    throw "[deploy] missing config source: $ConfigSourcePath"
}
if (-not (Test-Path -LiteralPath $SourceListPath)) {
    throw "[deploy] missing source list: $SourceListPath"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "[deploy] missing node runtime; cannot run pack-agent"
}

if (-not (Test-Path -LiteralPath $RuntimeConfigPath)) {
    Copy-Item -LiteralPath $ConfigSourcePath -Destination $RuntimeConfigPath -Force
    Write-Host "[deploy] seeded runtime config: $RuntimeConfigPath"
}

if (-not $NoBuild.IsPresent) {
    Write-Host "[deploy] building control_proto..."
    Push-Location (Join-Path $repoRoot "mimolo/control_proto")
    try {
        & npm run build | Out-Null
    }
    finally {
        Pop-Location
    }
}

Write-Host "[deploy] syncing runtime artifacts..."
Sync-File -SourcePath (Join-Path $repoRoot "mml.sh") -DestinationPath (Join-Path $BinDir "mml.sh")
Sync-File -SourcePath (Join-Path $repoRoot "mml.ps1") -DestinationPath (Join-Path $BinDir "mml.ps1")
Sync-File -SourcePath (Join-Path $repoRoot "scripts/bundle_app.sh") -DestinationPath (Join-Path $BinDir "scripts/bundle_app.sh")
Sync-File -SourcePath (Join-Path $repoRoot "scripts/bundle_app.ps1") -DestinationPath (Join-Path $BinDir "scripts/bundle_app.ps1")
Sync-File -SourcePath (Join-Path $repoRoot "mml.toml") -DestinationPath (Join-Path $BinDir "mml.toml")
Sync-File -SourcePath (Join-Path $repoRoot "pyproject.toml") -DestinationPath (Join-Path $BinDir "pyproject.toml")
if (Test-Path -LiteralPath (Join-Path $repoRoot "poetry.lock")) {
    Sync-File -SourcePath (Join-Path $repoRoot "poetry.lock") -DestinationPath (Join-Path $BinDir "poetry.lock")
}
Sync-File -SourcePath (Join-Path $repoRoot "mimolo.toml") -DestinationPath (Join-Path $BinDir "mimolo.default.toml")

Sync-Directory `
    -SourceDir (Join-Path $repoRoot "mimolo/control_proto/dist") `
    -DestinationDir (Join-Path $BinDir "control_proto/dist") `
    -ExcludedDirectoryNames @() `
    -ExcludedFilePatterns @() `
    -Force:$ForceSync

Sync-Directory `
    -SourceDir (Join-Path $repoRoot "mimolo") `
    -DestinationDir (Join-Path $BinDir "runtime/mimolo") `
    -ExcludedDirectoryNames @("__pycache__", ".mypy_cache", ".pytest_cache") `
    -ExcludedFilePatterns @("*.pyc", "*.pyo", ".DS_Store") `
    -Force:$ForceSync

try {
    & chmod +x (Join-Path $BinDir "mml.sh") 2>$null | Out-Null
    & chmod +x (Join-Path $BinDir "scripts/bundle_app.sh") 2>$null | Out-Null
}
catch {
    # chmod may not exist on Windows.
}

$agentsCsv = ""
if ($Agents -and $Agents.Count -gt 0) {
    $agentsCsv = ($Agents | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }) -join ","
}
Write-Host "[deploy] source list: $SourceListPath"
Write-Host "[deploy] ensuring plugin archives from source list..."
$utilsDir = Join-Path $repoRoot "mimolo/utils"
$packScript = Join-Path $utilsDir "dist/pack-agent.js"
if (-not (Test-Path -LiteralPath $utilsDir)) {
    throw "[deploy] missing utils dir: $utilsDir"
}
if (-not (Test-Path -LiteralPath (Join-Path $utilsDir "node_modules"))) {
    Write-Host "[deploy] installing mimolo/utils npm deps..."
    Push-Location $utilsDir
    try {
        & npm ci | Out-Null
    }
    finally {
        Pop-Location
    }
}
if (-not (Test-Path -LiteralPath $packScript)) {
    Write-Host "[deploy] building mimolo/utils pack tool..."
    Push-Location $utilsDir
    try {
        & npm run build | Out-Null
    }
    finally {
        Pop-Location
    }
}
Push-Location $utilsDir
try {
    & node dist/pack-agent.js --source-list $SourceListPath
}
finally {
    Pop-Location
}

if ([string]::IsNullOrWhiteSpace($agentsCsv)) {
    Write-Host "[deploy] seeding agents: <all from source list>"
}
else {
    Write-Host "[deploy] seeding agents: $agentsCsv"
}

$seedPython = @'
from __future__ import annotations

import json
import sys
from pathlib import Path

from mimolo.core.plugin_store import PluginStore

repo_root = Path(sys.argv[1])
data_dir = Path(sys.argv[2])
agents_csv = sys.argv[3]
source_list_path = Path(sys.argv[4])

repo_dir = repo_root / "mimolo" / "agents" / "repository"
if not source_list_path.exists():
    raise SystemExit(f"[deploy] missing source list: {source_list_path}")
if not repo_dir.exists():
    raise SystemExit(f"[deploy] missing repository dir: {repo_dir}")

sources_doc = json.loads(source_list_path.read_text(encoding="utf-8"))
source_rows = sources_doc.get("sources", [])
if not isinstance(source_rows, list):
    raise SystemExit(f"[deploy] source list has invalid shape: {source_list_path}")
source_versions: dict[str, str] = {}
source_order: list[str] = []
for row in source_rows:
    if isinstance(row, dict):
        plugin_id = str(row.get("id", "")).strip()
        version = str(row.get("ver", "")).strip()
        if plugin_id and version:
            source_versions[plugin_id] = version
            source_order.append(plugin_id)

agent_ids = [x.strip() for x in agents_csv.split(",") if x.strip()]
if not agent_ids:
    agent_ids = source_order
if not agent_ids:
    raise SystemExit("[deploy] no agent ids resolved from source list")

store = PluginStore(data_dir)
for agent_id in agent_ids:
    version = source_versions.get(agent_id)
    if not version:
        raise SystemExit(
            f"[deploy] source list does not define a version for agent id: {agent_id}"
        )
    zip_path = repo_dir / f"{agent_id}_v{version}.zip"
    if not zip_path.exists():
        raise SystemExit(f"[deploy] missing archive for {agent_id}")

    ok, detail, payload = store.install_plugin_archive(
        zip_path,
        "agents",
        require_newer=True,
    )
    if ok:
        print(
            f"[deploy] installed {payload.get('plugin_id')}@{payload.get('version')} -> {payload.get('path')}"
        )
        continue
    if detail in {"version_already_installed", "not_newer_than_installed"}:
        print(f"[deploy] unchanged {agent_id}: {detail}")
        continue
    raise SystemExit(f"[deploy] failed {agent_id}: {detail}")

store.write_registry_cache()
'@

& poetry run python -c $seedPython $repoRoot $DataDir $agentsCsv $SourceListPath

$manifestPath = Join-Path $BinDir "deploy-manifest.json"
$seededAgentsDefault = @(
    if ($Agents -and $Agents.Count -gt 0) {
        $Agents
    }
    else {
        "*"
    }
)
$manifest = [ordered]@{
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    bin_dir = [System.IO.Path]::GetFullPath($BinDir)
    data_dir = [System.IO.Path]::GetFullPath($DataDir)
    runtime_config_path = [System.IO.Path]::GetFullPath($RuntimeConfigPath)
    seeded_agents_default = $seededAgentsDefault
    source_list_path = [System.IO.Path]::GetFullPath($SourceListPath)
    deployment_model = "portable"
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
Write-Host "[deploy] wrote $manifestPath"
Write-Host "[deploy] done."
