@echo off
setlocal EnableExtensions EnableDelayedExpansion

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
    echo Установите Python 3.11+ и отметьте Add Python to PATH
    pause
    exit /b 1
)

if not exist ".env" (
    copy ".env.windows.example" ".env" >nul
    start "" notepad ".env"
    echo Укажите REWARDS_DATA_DIR и запустите снова
    pause
    exit /b 1
)

for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    set "ENV_KEY=%%A"
    set "ENV_VALUE=%%B"
    if not "!ENV_KEY!"=="" if not "!ENV_KEY:~0,1!"=="#" set "!ENV_KEY!=!ENV_VALUE!"
)

if not defined REWARDS_DATA_DIR (
    echo Укажите REWARDS_DATA_DIR в .env и запустите снова
    pause
    exit /b 1
)

if /I "!REWARDS_DATA_DIR!"=="C:\Path\To\Rewards" (
    echo Замените REWARDS_DATA_DIR=C:\Path\To\Rewards на реальный путь к папке Rewards
    pause
    exit /b 1
)

if not defined APP_PORT set "APP_PORT=8080"
set "APP_HOST=127.0.0.1"

if not exist ".venv\Scripts\python.exe" (
    echo Создаю локальное Python-окружение .venv...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo Не удалось создать .venv
        pause
        exit /b 1
    )
)

echo Устанавливаю зависимости...
".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 (
    echo Не удалось установить зависимости
    pause
    exit /b 1
)

echo Запускаю Fedorinov Rewards Web Preview...
echo Откройте: http://127.0.0.1:%APP_PORT%
start "" "http://127.0.0.1:%APP_PORT%"
".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port %APP_PORT%

echo Сервер остановлен.
pause
