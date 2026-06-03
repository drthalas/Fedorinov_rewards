$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

function Test-Python311 {
    param(
        [string]$Executable,
        [string[]]$ExecutableArgs = @()
    )

    try {
        $callArgs = @()
        $callArgs += $ExecutableArgs
        $callArgs += @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)")
        & $Executable @callArgs *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$script:PythonExe = $null
$script:PythonArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python311 -Executable "py" -ExecutableArgs @("-3")) {
        $script:PythonExe = "py"
        $script:PythonArgs = @("-3")
    }
}

if (-not $script:PythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python311 -Executable "python") {
        $script:PythonExe = "python"
        $script:PythonArgs = @()
    }
}

if (-not $script:PythonExe) {
    Write-Host "Установите Python 3.11+ и отметьте Add Python to PATH"
    Read-Host "Нажмите Enter для выхода"
    exit 1
}

function Invoke-PreviewPython {
    $callArgs = @()
    $callArgs += $script:PythonArgs
    $callArgs += $args
    & $script:PythonExe @callArgs
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.windows.example" ".env"
    Start-Process notepad ".env"
    Write-Host "Укажите REWARDS_DATA_DIR и запустите снова"
    Read-Host "Нажмите Enter для выхода"
    exit 1
}

Get-Content ".env" | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
        return
    }
    $parts = $line.Split("=", 2)
    [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim(), "Process")
}

$dataDir = [Environment]::GetEnvironmentVariable("REWARDS_DATA_DIR", "Process")
if (-not $dataDir) {
    Write-Host "Укажите REWARDS_DATA_DIR в .env и запустите снова"
    Read-Host "Нажмите Enter для выхода"
    exit 1
}

if ($dataDir -ieq "C:\Path\To\Rewards") {
    Write-Host "Замените REWARDS_DATA_DIR=C:\Path\To\Rewards на реальный путь к папке Rewards"
    Read-Host "Нажмите Enter для выхода"
    exit 1
}

$appPort = [Environment]::GetEnvironmentVariable("APP_PORT", "Process")
if (-not $appPort) {
    $appPort = "8080"
    [Environment]::SetEnvironmentVariable("APP_PORT", $appPort, "Process")
}
[Environment]::SetEnvironmentVariable("APP_HOST", "127.0.0.1", "Process")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Создаю локальное Python-окружение .venv..."
    Invoke-PreviewPython -m venv .venv
}

Write-Host "Устанавливаю зависимости..."
& ".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"

Write-Host "Запускаю Fedorinov Rewards Web Preview..."
Write-Host "Откройте: http://127.0.0.1:$appPort"
Start-Process "http://127.0.0.1:$appPort"
& ".venv\Scripts\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port $appPort

Write-Host "Сервер остановлен."
Read-Host "Нажмите Enter для выхода"
