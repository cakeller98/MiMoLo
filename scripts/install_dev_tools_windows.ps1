# NOTE:
# - This script is per-user and intended to be run in a GUI session.
# - Some installers (notably Python) may trigger UAC prompts and require
#   approval from an admin account. Windows Hello prompts are GUI-only.
# - nvm-windows creates symlinks. Either run `nvm use` as admin or enable
#   Developer Mode to allow symlinks without elevation.

param(
    [ValidateSet("3.11","3.12","3.13")]
    [string]$PythonVersion = "3.11",
    [switch]$Validate
)

$ErrorActionPreference = "Stop"

function Test-WingetInstalled {
    param([string]$Id)
    $result = winget list --id $Id 2>$null
    return ($result -match $Id)
}

function Ensure-WingetPackage {
    param([string]$Id)
    if (Test-WingetInstalled $Id) {
        Write-Host "Already installed: $Id"
        return
    }
    Write-Host "Installing: $Id"
    winget install -e --id $Id --scope user --accept-package-agreements --accept-source-agreements
}

function Add-ToUserPath {
    param([string]$Dir)
    if (-not (Test-Path $Dir)) {
        return
    }
    $userPath = [Environment]::GetEnvironmentVariable("Path","User")
    if (-not $userPath) {
        $userPath = ""
    }
    $parts = $userPath -split ';'
    if ($parts -notcontains $Dir) {
        $newPath = ($parts + $Dir) -join ';'
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    }
    if (-not ($env:Path -split ';' | Where-Object { $_ -eq $Dir })) {
        $env:Path = "$Dir;$env:Path"
    }
}

if (-not $Validate) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget not found. Install App Installer (Microsoft Store) and re-run."
    }
    Write-Host "Installing dev tools (per-user)..."

    Write-Host "Installing nvm-windows (portable, per-user)..."
    Ensure-WingetPackage "Python.Python.$PythonVersion"
    Ensure-WingetPackage "astral-sh.uv"

    Write-Host "Configuring nvm-windows environment variables (per-user install)..."
    $nvmHome = Join-Path $env:LOCALAPPDATA "Programs\nvm"
    $nvmSymlink = Join-Path $env:LOCALAPPDATA "Programs\nodejs"

    if (-not (Test-Path $nvmHome)) {
        New-Item -ItemType Directory -Force -Path $nvmHome | Out-Null
    }
    if (Test-Path $nvmSymlink) {
        Write-Host "Removing existing NVM_SYMLINK path so nvm can create a symlink..."
        Remove-Item -Recurse -Force $nvmSymlink
    }

    $nvmExe = Join-Path $nvmHome "nvm.exe"
    if (-not (Test-Path $nvmExe)) {
        $repo = "coreybutler/nvm-windows"
        $latest = Invoke-RestMethod "https://api.github.com/repos/$repo/releases/latest"
        $asset = $latest.assets | Where-Object { $_.name -eq "nvm-noinstall.zip" } | Select-Object -First 1
        if (-not $asset) {
            throw "nvm-noinstall.zip not found in latest release assets."
        }
        $zipPath = Join-Path $env:TEMP "nvm-noinstall.zip"
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $nvmHome -Force
    } else {
        Write-Host "nvm.exe already present at $nvmExe"
    }

    $settingsPath = Join-Path $nvmHome "settings.txt"
    if (-not (Test-Path $settingsPath)) {
        @(
            "root: $nvmHome",
            "path: $nvmSymlink",
            "arch: 64",
            "proxy: none"
        ) | Set-Content -Path $settingsPath -Encoding ASCII
    }

    [Environment]::SetEnvironmentVariable("NVM_HOME", $nvmHome, "User")
    [Environment]::SetEnvironmentVariable("NVM_SYMLINK", $nvmSymlink, "User")
    Add-ToUserPath $nvmHome
    Add-ToUserPath $nvmSymlink

    Write-Host "Installing pipx (per pipx Windows instructions)..."
    $pythonExe = "py"
    $null = & $pythonExe -V 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Python launcher 'py' not found. Ensure Python $PythonVersion is installed and on PATH."
    }

    & $pythonExe -m pip show pipx 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & $pythonExe -m pip install --user pipx
    } else {
        Write-Host "pipx already installed for this user."
    }

    Write-Host "Ensuring pipx path (using module invocation)..."
    & $pythonExe -m pipx ensurepath | Out-Null

    Write-Host "Installing Poetry via pipx (per Poetry docs)..."
    $poetryInstalled = & $pythonExe -m pipx list | Select-String -Pattern "poetry" -SimpleMatch
    if (-not $poetryInstalled) {
        & $pythonExe -m pipx install poetry
    } else {
        Write-Host "Poetry already installed via pipx."
    }

    Write-Host "Installing Node.js 24 and TypeScript (tsc)..."
    & nvm install 24
    & nvm use 24
    & npm install -g typescript
} else {
    Write-Host "Validate mode: skipping installs; checking PATH and tool availability..."
}

if (-not $pythonExe) {
    $pythonExe = "py"
}
if (-not $nvmHome) {
    $nvmHome = Join-Path $env:LOCALAPPDATA "Programs\nvm"
}

function Test-Command {
    param([string]$Name, [string]$Args = "")
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "Missing: $Name"
        return
    }
    if ($Args) {
        & $Name $Args
    } else {
        & $Name --version
    }
}

Write-Host "Verifying installs..."
& $pythonExe -V
& $pythonExe -m pipx --version
Test-Command "poetry"
Test-Command "uv"
Test-Command "nvm"
Test-Command "tsc"

Write-Host ""
Write-Host "Note: If Poetry or pipx are not on PATH in new shells, restart your terminal."
Write-Host "pipx executable path is under the user base Scripts directory."
Write-Host "Note: nvm-windows installed as portable per-user under $nvmHome."
