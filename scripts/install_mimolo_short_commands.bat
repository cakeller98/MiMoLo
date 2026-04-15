@echo off
setlocal EnableExtensions DisableDelayedExpansion

for %%I in ("%~dp0..") do set "REPO_ROOT=%%~fI"
set "SOURCE_SCRIPT=%REPO_ROOT%\scripts\print_last_jsonl.ps1"

if not exist "%SOURCE_SCRIPT%" (
    echo Source script not found:
    echo   "%SOURCE_SCRIPT%"
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

if defined MIMOLO_SHORT_COMMAND_WRAPPER (
    set "WRAPPER_NAME=%MIMOLO_SHORT_COMMAND_WRAPPER%"
) else (
    set "WRAPPER_NAME=mimolo-short-commands.bat"
)

set "TARGET_WRAPPER=%INSTALL_DIR%\%WRAPPER_NAME%"

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%" >nul 2>nul
    if errorlevel 1 (
        echo Failed to create install directory:
        echo   "%INSTALL_DIR%"
        exit /b 1
    )
)

call :write_wrapper "%TARGET_WRAPPER%" "%SOURCE_SCRIPT%"
if errorlevel 1 exit /b %ERRORLEVEL%

if /I "%MIMOLO_SKIP_PATH_UPDATE%"=="1" (
    echo Skipped user PATH update because MIMOLO_SKIP_PATH_UPDATE=1.
) else (
    call :ensure_user_path "%INSTALL_DIR%"
    if errorlevel 1 exit /b %ERRORLEVEL%
)

echo Installed:
echo   "%TARGET_WRAPPER%"
echo.
echo Run it like:
echo   %WRAPPER_NAME% --glh
echo   %WRAPPER_NAME% --lines 5
echo.
echo If your terminal was already open, start a new terminal to pick up PATH changes.
exit /b 0

:write_wrapper
set "TARGET=%~1"
set "SOURCE=%~2"
> "%TARGET%" (
    echo @echo off
    echo setlocal EnableExtensions DisableDelayedExpansion
    echo set "MIMOLO_SCRIPT=%SOURCE%"
    echo if not exist "%%MIMOLO_SCRIPT%%" ^(
    echo     echo MiMoLo script not found:
    echo     echo   "%%MIMOLO_SCRIPT%%"
    echo     exit /b 1
    echo ^)
    echo powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%%MIMOLO_SCRIPT%%" %%*
    echo exit /b %%ERRORLEVEL%%
)
if errorlevel 1 (
    echo Failed to write wrapper:
    echo   "%TARGET%"
    exit /b 1
)
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
