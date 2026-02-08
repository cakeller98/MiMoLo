# MiMoLo macOS bundle wrapper for PowerShell launcher users.
# Delegates to scripts/bundle_app.sh.

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsRest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundleScript = Join-Path $scriptDir "bundle_app.sh"

if (-not (Test-Path -LiteralPath $bundleScript)) {
    throw "[bundle] missing script: $bundleScript"
}

if ($IsWindows) {
    throw "[bundle] bundle-app is currently macOS-only."
}

if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
    throw "[bundle] bash is required to run bundle_app.sh."
}

& bash $bundleScript @ArgsRest
