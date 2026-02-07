# Launch MiMoLo monitor with Poetry environment (PowerShell)
# Usage: .\start_monitor.ps1 [options]

$ErrorActionPreference = "Stop"

# Change to script directory
Set-Location $PSScriptRoot

# Run monitor with poetry
poetry run python -m mimolo.cli monitor $args
