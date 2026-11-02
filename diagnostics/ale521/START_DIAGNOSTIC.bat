@echo off
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
powershell.exe -NoLogo -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0launcher.ps1"
if errorlevel 1 pause
endlocal
