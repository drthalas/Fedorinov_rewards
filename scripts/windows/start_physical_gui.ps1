param(
    [string]$Url = 'http://127.0.0.1:8080/legacy?tab=rewards',
    [int]$CdpPort = 19375,
    [string]$TaskName = 'FedorinovRewards-Physical-GUI'
)

$ErrorActionPreference = 'Stop'
$state = Join-Path $env:LOCALAPPDATA 'FedorinovGate\PhysicalGui'
$profile = Join-Path $state 'edge-profile'
New-Item -ItemType Directory -Path $state -Force | Out-Null

$previous = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$profile*" }
foreach ($process in $previous) {
    Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
}

$task = Get-ScheduledTask -TaskName $TaskName
if ($task.State -eq 'Running') {
    Stop-ScheduledTask -TaskName $TaskName
    $stopDeadline = (Get-Date).AddSeconds(10)
    do {
        $task = Get-ScheduledTask -TaskName $TaskName
        if ($task.State -ne 'Running') {
            break
        }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $stopDeadline)
    if ($task.State -eq 'Running') {
        throw 'Canonical GUI task did not stop within 10 seconds.'
    }
}

[ordered]@{
    url = $Url
    cdp_port = $CdpPort
    requested_at = (Get-Date).ToString('o')
} | ConvertTo-Json | Set-Content (Join-Path $state 'request.json') -Encoding UTF8

Remove-Item (Join-Path $state 'status.json') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $state 'error.txt') -Force -ErrorAction SilentlyContinue

$run = & schtasks.exe /Run /TN $TaskName 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "schtasks run failed: $run"
}

$deadline = (Get-Date).AddSeconds(30)
do {
    try {
        $version = Invoke-RestMethod "http://127.0.0.1:$CdpPort/json/version" -TimeoutSec 2
        $status = Get-Content (Join-Path $state 'status.json') -Raw | ConvertFrom-Json
        $sessionId = [int]$status.session_id
        if ($sessionId -le 0) {
            throw "Browser is not in an interactive user session: $sessionId"
        }

        $edge = Get-Process -Id ([int]$status.pid) -ErrorAction Stop
        if ($edge.SessionId -ne $sessionId) {
            throw "Browser session mismatch: status=$sessionId process=$($edge.SessionId)"
        }
        if (-not (Get-Process explorer -ErrorAction SilentlyContinue |
                Where-Object SessionId -eq $sessionId)) {
            throw "Explorer is missing from browser session $sessionId"
        }
        if (-not (Get-Process dwm -ErrorAction SilentlyContinue |
                Where-Object SessionId -eq $sessionId)) {
            throw "DWM is missing from browser session $sessionId"
        }

        [ordered]@{
            ready = $true
            browser = $version.Browser
            session_id = $sessionId
            explorer = $true
            dwm = $true
            status = $status
        } | ConvertTo-Json -Depth 6
        exit 0
    } catch {
        Start-Sleep -Milliseconds 300
    }
} while ((Get-Date) -lt $deadline)

$statusText = if (Test-Path (Join-Path $state 'status.json')) {
    Get-Content (Join-Path $state 'status.json') -Raw
} else { '' }
$errorText = if (Test-Path (Join-Path $state 'error.txt')) {
    Get-Content (Join-Path $state 'error.txt') -Raw
} else { '' }
$query = (& schtasks.exe /Query /TN $TaskName /V /FO LIST 2>&1 | Out-String).Trim()
throw "GUI not ready. status=$statusText error=$errorText task=$query"
