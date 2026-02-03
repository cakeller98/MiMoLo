# NOTE:
# - This script is per-user and intended to be run in a GUI session.
# - Some installers (notably Python) may trigger UAC prompts and require
#   approval from an admin account. Windows Hello prompts are GUI-only.

param(
    [ValidateSet("3.11","3.12","3.13")]
    [string]$PythonVersion = "3.11"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget not found. Install App Installer (Microsoft Store) and re-run."
}

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

Write-Host "Installing dev tools (per-user)..."

Ensure-WingetPackage "CoreyButler.NVMforWindows"
Ensure-WingetPackage "Python.Python.$PythonVersion"
Ensure-WingetPackage "astral-sh.uv"

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
Write-Host "Installing Poetry via pipx (per Poetry docs)..."
$poetryInstalled = & $pythonExe -m pipx list | Select-String -Pattern "poetry" -SimpleMatch
if (-not $poetryInstalled) {
    & $pythonExe -m pipx install poetry
} else {
    Write-Host "Poetry already installed via pipx."
}

Write-Host "Verifying installs..."
& $pythonExe -V
& $pythonExe -m pipx --version
& poetry --version
& uv --version
& nvm --version

Write-Host ""
Write-Host "Note: If Poetry or pipx are not on PATH in new shells, restart your terminal."
Write-Host "pipx executable path is under the user base Scripts directory."
