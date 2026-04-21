@echo off
setlocal EnableExtensions DisableDelayedExpansion

for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
set "DISPATCHER_SCRIPT=%REPO_ROOT%\scripts\mimolo_short_commands.ps1"

if not exist "%DISPATCHER_SCRIPT%" (
    echo Dispatcher script not found:
    echo   "%DISPATCHER_SCRIPT%"
    exit /b 1
)

if defined MIMOLO_SHORT_COMMANDS_BIN_DIR (
    set "INSTALL_DIR=%MIMOLO_SHORT_COMMANDS_BIN_DIR%"
) else (
    if not defined LOCALAPPDATA (
        echo LOCALAPPDATA is not defined.
        exit /b 1
    )
    set "INSTALL_DIR=%LOCALAPPDATA%\bin"
)

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%" >nul 2>nul
    if errorlevel 1 (
        echo Failed to create install directory:
        echo   "%INSTALL_DIR%"
        exit /b 1
    )
)

set "COMMAND_LIST=pymolo pymolo-help pymolo-dash pymolo-ops pymolo-report pymolo-activity pymolo-blips pymolo-bliplive"
set "LEGACY_COMMAND_LIST=mimolo mimolo-help mimolo-dash mimolo-ops mimolo-report mimolo-activity mimolo-blips mimolo-bliplive mimolo-short-commands"

for %%N in (%COMMAND_LIST%) do (
    call :write_wrapper "%INSTALL_DIR%\%%N.bat" "%DISPATCHER_SCRIPT%" "%%N"
    if errorlevel 1 exit /b %ERRORLEVEL%
)

if /I "%MIMOLO_REMOVE_LEGACY_MIMOLO_WRAPPERS%"=="1" (
    for %%N in (%LEGACY_COMMAND_LIST%) do (
        call :remove_legacy_wrapper "%INSTALL_DIR%\%%N.bat"
        if errorlevel 1 exit /b %ERRORLEVEL%
    )
) else (
    call :report_legacy_wrapper_policy
)

if /I "%MIMOLO_SKIP_PATH_UPDATE%"=="1" (
    echo Skipped user PATH update because MIMOLO_SKIP_PATH_UPDATE=1.
) else (
    call :ensure_user_path "%INSTALL_DIR%"
    if errorlevel 1 exit /b %ERRORLEVEL%
)

echo Installed commands in:
echo   "%INSTALL_DIR%"
echo.
for %%N in (%COMMAND_LIST%) do echo   %%N.bat
echo.
echo Examples:
echo   pymolo --help
echo   pymolo-dash
echo   pymolo-report
echo   pymolo-activity
echo   pymolo-blips
echo   pymolo-bliplive
echo   pymolo-ops --status
echo   pymolo-ops --stop
echo.
echo Before first use on a new profile, verify your security-tool exclusions are
echo present for Python, Poetry, pip, pipx, uv, and repo working paths.
echo.
echo If your terminal was already open, start a new terminal to pick up PATH changes.
exit /b 0

:write_wrapper
set "TARGET=%~1"
set "DISPATCHER=%~2"
set "SHIM_NAME=%~3"
> "%TARGET%" (
    echo @echo off
    echo setlocal EnableExtensions DisableDelayedExpansion
    echo set "MIMOLO_DISPATCHER=%DISPATCHER%"
    echo if not exist "%%MIMOLO_DISPATCHER%%" ^(
    echo     echo MiMoLo dispatcher not found:
    echo     echo   "%%MIMOLO_DISPATCHER%%"
    echo     exit /b 1
    echo ^)
    echo powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%%MIMOLO_DISPATCHER%%" -Shim "%SHIM_NAME%" %%*
    echo exit /b %%ERRORLEVEL%%
)
if errorlevel 1 (
    echo Failed to write wrapper:
    echo   "%TARGET%"
    exit /b 1
)
exit /b 0

:remove_legacy_wrapper
set "LEGACY_WRAPPER=%~1"
if not exist "%LEGACY_WRAPPER%" exit /b 0

del /q "%LEGACY_WRAPPER%" >nul 2>nul
if exist "%LEGACY_WRAPPER%" (
    echo Failed to remove legacy wrapper:
    echo   "%LEGACY_WRAPPER%"
    exit /b 1
)

echo Removed legacy wrapper:
echo   "%LEGACY_WRAPPER%"
exit /b 0

:report_legacy_wrapper_policy
echo Skipped removal of mimolo*.bat wrappers.
echo This avoids deleting canonical command names that may belong to the Rust version.
echo To remove old Python-era mimolo wrappers explicitly, rerun with:
echo   set MIMOLO_REMOVE_LEGACY_MIMOLO_WRAPPERS=1
exit /b 0

:ensure_user_path
set "TARGET_BIN_DIR=%~1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$target = [IO.Path]::GetFullPath($env:TARGET_BIN_DIR);" ^
  "try {" ^
  "  $userPath = [Environment]::GetEnvironmentVariable('Path', 'User');" ^
  "  $parts = @();" ^
  "  if (-not [string]::IsNullOrWhiteSpace($userPath)) {" ^
  "    foreach ($entry in ($userPath -split ';')) {" ^
  "      if (-not [string]::IsNullOrWhiteSpace($entry)) { $parts += $entry }" ^
  "    }" ^
  "  };" ^
  "  $normalize = { param([string]$p) ([Environment]::ExpandEnvironmentVariables($p)).Trim().TrimEnd('\') };" ^
  "  $exists = $false; foreach ($part in $parts) { if ((& $normalize $part) -ieq (& $normalize $target)) { $exists = $true; break } };" ^
  "  if ($exists) { exit 0 }" ^
  "  $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $target } else { $userPath.TrimEnd(';') + ';' + $target };" ^
  "  [Environment]::SetEnvironmentVariable('Path', $newPath, 'User');" ^
  "  exit 10" ^
  "} catch {" ^
  "  Write-Error $_;" ^
  "  exit 1" ^
  "}"
set "PATH_UPDATE_EXIT=%ERRORLEVEL%"

if "%PATH_UPDATE_EXIT%"=="10" (
    echo Added user PATH entry:
    echo   "%TARGET_BIN_DIR%"
) else if "%PATH_UPDATE_EXIT%"=="0" (
    echo User PATH already contains:
    echo   "%TARGET_BIN_DIR%"
) else (
    echo Failed to update user PATH. PowerShell exit code: %PATH_UPDATE_EXIT%
    exit /b %PATH_UPDATE_EXIT%
)

echo ;%PATH%; | findstr /I /C:";%TARGET_BIN_DIR%;" >nul
if errorlevel 1 set "PATH=%PATH%;%TARGET_BIN_DIR%"
exit /b 0
