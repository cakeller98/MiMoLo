#!/usr/bin/env bash
# Launch MiMoLo monitor with Poetry environment
# Usage: ./start_monitor.sh [options]

set -e

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Activate poetry environment and run monitor
poetry run python -m mimolo.cli monitor "$@"
