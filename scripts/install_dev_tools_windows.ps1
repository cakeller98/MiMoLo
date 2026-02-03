# NOTE:
# - This script is per-user and intended to be run in a GUI session.
# - Some installers (notably Python) may trigger UAC prompts and require
#   approval from an admin account. Windows Hello prompts are GUI-only.

param(
    [ValidateSet("3.11","3.12","3.13")]
    [string]$PythonVersion = "3.11"
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

# Resolve pipx Scripts path and ensure it is on PATH for this session.
$pipxUserBase = & $pythonExe -c "import site; print(site.getuserbase())"
$pipxScripts = Join-Path $pipxUserBase "Scripts"
$pipxExe = Join-Path $pipxScripts "pipx.exe"

if (-not (Test-Path $pipxExe)) {
    throw "pipx.exe not found at $pipxExe. Verify pipx installation succeeded."
}

if (-not ($env:Path -split ';' | Where-Object { $_ -eq $pipxScripts })) {
    $env:Path = "$pipxScripts;$env:Path"
}

& $pipxExe ensurepath | Out-Null

Write-Host "Installing Poetry via pipx (per Poetry docs)..."
$poetryInstalled = & $pipxExe list | Select-String -Pattern "poetry" -SimpleMatch
if (-not $poetryInstalled) {
    & $pipxExe install poetry
} else {
    Write-Host "Poetry already installed via pipx."
}

Write-Host "Verifying installs..."
& $pythonExe -V
& $pipxExe --version
& poetry --version
& uv --version
& nvm --version
