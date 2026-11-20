@echo off
rem Body Debugger scan: writes body_debug_report.txt next to this file. Changes nothing in the game.
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.8 or newer is needed: https://www.python.org/downloads/
  pause
  exit /b 1
)
if "%~1"=="" (
  python -I body_debug_scan.py
) else (
  python -I body_debug_scan.py "%~1"
)
if errorlevel 1 (
  echo.
  echo The scan failed. If your game is not in the default Steam, GOG or Epic folder, drag your Cyberpunk 2077
  echo folder onto this file, or put this folder inside your game folder and run it from there.
) else (
  start "" notepad "%~dp0body_debug_report.txt"
)
pause
