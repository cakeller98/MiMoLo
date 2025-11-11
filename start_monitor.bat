@echo off
REM Launch MiMoLo monitor with Poetry environment (Windows)
REM Usage: start_monitor.bat [options]

cd /d "%~dp0"

poetry run python -m mimolo.cli monitor %*
