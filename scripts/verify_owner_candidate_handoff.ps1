param(
    [string]$ChannelRoot = 'C:\FedorinovGate\OwnerCandidateChannel'
)

$ErrorActionPreference = 'Stop'
$statePath = Join-Path $ChannelRoot 'channel-state.json'
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$publicRoot = [string]$state.public_install_root
$publicTask = 'FedorinovRewards-Public-Current'
$guiTask = 'FedorinovRewards-Physical-GUI'
$cdpPort = 9237
$appPort = 8080
$appUrl = "http://127.0.0.1:$appPort"
$guiState = Join-Path $env:LOCALAPPDATA 'FedorinovGate\PhysicalGui'
$profile = Join-Path $guiState 'edge-profile'
$requestPath = Join-Path $guiState 'request.json'
$screenshotPath = Join-Path $ChannelRoot 'evidence\candidate-visible.png'
$resultPath = Join-Path $ChannelRoot 'evidence\candidate-visible.json'

function Get-PublicIdentity {
    try {
        return Invoke-RestMethod -UseBasicParsing -TimeoutSec 3 -Uri "$appUrl/runtime/identity"
    } catch {
        return $null
    }
}

$identity = Get-PublicIdentity
if ($identity) {
    if ([string]$identity.version -ne [string]$state.expected_public_version -or
        [string]$identity.install_root -ine $publicRoot) {
        throw 'Port 8080 is not the expected Public Current runtime.'
    }
} else {
    if (Get-NetTCPConnection -State Listen -LocalPort $appPort -ErrorAction SilentlyContinue) {
        throw 'Port 8080 is listening but does not expose the expected runtime identity.'
    }
    Start-ScheduledTask -TaskName $publicTask
}

$deadline = (Get-Date).AddSeconds(120)
do {
    $identity = Get-PublicIdentity
    if ($identity -and
        [string]$identity.version -eq [string]$state.expected_public_version -and
        [string]$identity.install_root -ieq $publicRoot) {
        break
    }
    Start-Sleep -Milliseconds 500
} while ((Get-Date) -lt $deadline)
if (-not $identity) {
    throw 'Public Current did not become ready.'
}

$manifestLine = Get-Content -LiteralPath (Join-Path $publicRoot '.env') |
    Where-Object { $_ -match '^UPDATE_MANIFEST_URL=' } |
    Select-Object -First 1
if (($manifestLine -replace '^UPDATE_MANIFEST_URL=', '') -ne [string]$state.candidate_manifest_url) {
    throw 'Public Current is not pointed at the Owner candidate channel.'
}

$guiTaskObject = Get-ScheduledTask -TaskName $guiTask -ErrorAction Stop
Stop-ScheduledTask -TaskName $guiTask -ErrorAction SilentlyContinue
$profileProcesses = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { [string]$_.CommandLine -like "*$profile*" })
foreach ($process in $profileProcesses) {
    & taskkill.exe /PID $process.ProcessId /T /F | Out-Null
}
if (Get-NetTCPConnection -State Listen -LocalPort $cdpPort -ErrorAction SilentlyContinue) {
    throw "CDP port $cdpPort is still occupied after canonical GUI cleanup."
}

New-Item -ItemType Directory -Path $guiState -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $screenshotPath) -Force | Out-Null
[ordered]@{
    url = "$appUrl/legacy?tab=about"
    cdp_port = $cdpPort
} | ConvertTo-Json | Set-Content -LiteralPath $requestPath -Encoding UTF8
Start-ScheduledTask -TaskName $guiTask

$deadline = (Get-Date).AddSeconds(45)
do {
    try {
        Invoke-RestMethod -UseBasicParsing -TimeoutSec 2 -Uri "http://127.0.0.1:$cdpPort/json/version" | Out-Null
        break
    } catch {
        Start-Sleep -Milliseconds 250
    }
} while ((Get-Date) -lt $deadline)
if (-not (Get-NetTCPConnection -State Listen -LocalPort $cdpPort -ErrorAction SilentlyContinue)) {
    throw 'Canonical headed Edge did not expose its loopback CDP endpoint.'
}

$pythonCandidates = @(
    'C:\FedorinovGate\tools\Python311-x64\python.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $python) {
    throw 'Canonical Python runtime for physical visibility verification was not found.'
}
$verifier = Join-Path $ChannelRoot 'verify_owner_candidate_visibility.py'
$arguments = @(
    $verifier,
    '--endpoint', "http://127.0.0.1:$cdpPort",
    '--app-url', $appUrl,
    '--current-version', [string]$state.expected_public_version,
    '--candidate-version', [string]$state.candidate_version,
    '--candidate-sha256', [string]$state.candidate_sha256,
    '--screenshot', $screenshotPath
)
$output = & $python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Physical candidate visibility verifier failed: $output"
}
$visibility = $output | ConvertFrom-Json
$output | Set-Content -LiteralPath $resultPath -Encoding UTF8
$afterIdentity = Get-PublicIdentity
if (-not $afterIdentity -or [string]$afterIdentity.version -ne [string]$state.expected_public_version) {
    throw 'Public Current version changed during the non-destructive visibility gate.'
}

[pscustomobject]@{
    action = 'physical-visibility'
    public_version = [string]$afterIdentity.version
    public_pid = [int]$afterIdentity.pid
    public_port = [int]$afterIdentity.port
    candidate_version_visible = [bool]$visibility.candidate_version_visible
    candidate_sha_visible = [bool]$visibility.candidate_sha_visible
    update_form_visible = [bool]$visibility.update_form_visible
    update_not_applied = [bool]$visibility.update_not_applied
    headed_edge_task_state = [string](Get-ScheduledTask -TaskName $guiTask).State
    screenshot = $screenshotPath
} | ConvertTo-Json -Compress
