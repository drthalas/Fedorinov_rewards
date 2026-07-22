@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if "%PYTHON_CMD%"=="" (
    where python >nul 2>nul
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if "%PYTHON_CMD%"=="" (
    echo Для восстановления нужен Python 3.11 или новее.
    echo Сделайте фотографию этого окна и отправьте Александру.
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
%PYTHON_CMD% "service\recovery_v206.py" --service-dir "service"
set "RECOVERY_EXIT=%ERRORLEVEL%"
if not "%RECOVERY_EXIT%"=="0" (
    echo.
    echo Восстановление не завершено. Ничего не удаляйте.
    echo Сделайте фотографию этого окна и отправьте Александру.
    pause
    exit /b %RECOVERY_EXIT%
)

echo.
echo Готово. Версия 2.0.6 запущена.
echo Старую папку и временную recovery-папку пока не удаляйте.
pause
exit /b 0
