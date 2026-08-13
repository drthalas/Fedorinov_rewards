param(
    [ValidateSet('Deploy', 'Status', 'Restore')]
    [string]$Action,
    [string]$SpecPath = 'C:\FedorinovGate\OwnerCandidateChannel\deploy-spec.json'
)

$ErrorActionPreference = 'Stop'
$TaskName = 'FedorinovRewards-Owner-Candidate-Channel'

function Read-EnvLines([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Public Current .env is missing: $Path"
    }
    return [System.Collections.Generic.List[string]](Get-Content -LiteralPath $Path)
}

function Get-EnvValue($Lines, [string]$Name) {
    foreach ($line in $Lines) {
        if ($line -match ('^\s*' + [regex]::Escape($Name) + '\s*=\s*(.*)$')) {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Set-EnvValue([string]$Path, [string]$Name, [string]$Value) {
    $lines = Read-EnvLines $Path
    $found = $false
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match ('^\s*' + [regex]::Escape($Name) + '\s*=')) {
            $lines[$index] = "$Name=$Value"
            $found = $true
        }
    }
    if (-not $found) {
        $lines.Add("$Name=$Value")
    }
    $temporary = "$Path.ale387.tmp"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($temporary, $lines, $encoding)
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Get-InstalledVersion([string]$InstallRoot) {
    $launcher = Join-Path $InstallRoot 'start_windows.bat'
    $versionPath = Join-Path $InstallRoot 'backend\app\version.py'
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "Public Current launcher is missing: $launcher"
    }
    if (-not (Test-Path -LiteralPath $versionPath -PathType Leaf)) {
        throw "Public Current version marker is missing: $versionPath"
    }
    $versionText = Get-Content -LiteralPath $versionPath -Raw
    if ($versionText -notmatch 'APP_VERSION\s*=\s*"([^"]+)"') {
        throw "Cannot parse Public Current version: $versionPath"
    }
    return $Matches[1]
}

function Stop-ChannelListener([int]$Port, [string]$ChannelRoot) {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if (-not $process -or [string]$process.CommandLine -notlike "*$ChannelRoot*") {
            throw "Port $Port is owned by a process outside the Owner candidate channel."
        }
        & taskkill.exe /PID $listener.OwningProcess /T /F | Out-Null
    }
}

function Stop-ChannelTask([int]$Port, [string]$ChannelRoot, [bool]$Unregister) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    }
    Stop-ChannelListener -Port $Port -ChannelRoot $ChannelRoot
    if ($task -and $Unregister) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
}

function Wait-Channel([string]$HealthUrl, [string]$ExpectedVersion, [string]$ExpectedSha) {
    $deadline = (Get-Date).AddSeconds(20)
    do {
        try {
            $response = Invoke-RestMethod -UseBasicParsing -TimeoutSec 2 -Uri $HealthUrl
            if ([string]$response.version -eq $ExpectedVersion -and [string]$response.sha256 -eq $ExpectedSha) {
                return
            }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    } while ((Get-Date) -lt $deadline)
    throw "Owner candidate channel did not become healthy: $HealthUrl"
}

function Read-State([string]$ChannelRoot) {
    $statePath = Join-Path $ChannelRoot 'channel-state.json'
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        throw "Owner candidate channel state is missing: $statePath"
    }
    return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
}

if ($Action -eq 'Deploy') {
    $spec = Get-Content -LiteralPath $SpecPath -Raw | ConvertFrom-Json
    $channelRoot = [string]$spec.channel_root
    $installRoot = [string]$spec.public_install_root
    $port = [int]$spec.candidate_port
    $incoming = Split-Path -Parent $SpecPath
    $envPath = Join-Path $installRoot '.env'
    $candidateUrl = "http://127.0.0.1:$port/latest.json"
    $healthUrl = "http://127.0.0.1:$port/healthz"
    $active = Join-Path $channelRoot 'active'
    $next = Join-Path $channelRoot 'active.next'
    $previous = Join-Path $channelRoot 'active.previous'
    $statePath = Join-Path $channelRoot 'channel-state.json'

    $installedVersion = Get-InstalledVersion $installRoot
    if ($installedVersion -ne [string]$spec.expected_public_version) {
        throw "Public Current version mismatch: expected $($spec.expected_public_version), got $installedVersion"
    }
    $envLines = Read-EnvLines $envPath
    $currentManifestUrl = Get-EnvValue $envLines 'UPDATE_MANIFEST_URL'
    $productionManifestUrl = [string]$spec.production_manifest_url
    if (Test-Path -LiteralPath $statePath -PathType Leaf) {
        $previousState = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ([string]$previousState.production_manifest_url -ne $productionManifestUrl) {
            throw 'Stored production manifest URL does not match the deployment specification.'
        }
        if ($currentManifestUrl -notin @($productionManifestUrl, [string]$previousState.candidate_manifest_url)) {
            throw "Public Current uses an unexpected manifest URL: $currentManifestUrl"
        }
    } elseif ($currentManifestUrl -ne $productionManifestUrl) {
        throw "Initial Public Current manifest is not the canonical production URL: $currentManifestUrl"
    }

    $artifactPath = Join-Path $incoming ([string]$spec.candidate_filename)
    $manifestPath = Join-Path $incoming 'latest.json'
    $serverPath = Join-Path $incoming 'owner_candidate_channel_server.py'
    $configurePath = Join-Path $incoming 'configure_owner_candidate_channel.ps1'
    $verifierPath = Join-Path $incoming 'verify_owner_candidate_visibility.py'
    $handoffPath = Join-Path $incoming 'verify_owner_candidate_handoff.ps1'
    foreach ($required in @($artifactPath, $manifestPath, $serverPath, $configurePath, $verifierPath, $handoffPath)) {
        if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
            throw "Candidate channel input is missing: $required"
        }
    }
    $artifactSha = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($artifactSha -ne [string]$spec.candidate_sha256) {
        throw "Candidate artifact SHA mismatch: $artifactSha"
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ([string]$manifest.version -ne [string]$spec.candidate_version -or
        [string]$manifest.sha256 -ne [string]$spec.candidate_sha256 -or
        [string]$manifest.download_url -ne "http://127.0.0.1:$port/$($spec.candidate_filename)") {
        throw 'Candidate manifest does not match the deployment specification.'
    }

    $pythonCandidates = @(
        'C:\FedorinovGate\tools\Python311-x64\python.exe',
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
    )
    $python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (-not $python) {
        throw 'Canonical Python runtime for the Owner candidate channel was not found.'
    }

    New-Item -ItemType Directory -Path $channelRoot -Force | Out-Null
    Stop-ChannelTask -Port $port -ChannelRoot $channelRoot -Unregister $true
    Remove-Item -LiteralPath $next -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $next -Force | Out-Null
    Copy-Item -LiteralPath $artifactPath -Destination (Join-Path $next ([string]$spec.candidate_filename))
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $next 'latest.json')
    Copy-Item -LiteralPath $serverPath -Destination (Join-Path $next 'owner_candidate_channel_server.py')
    Copy-Item -LiteralPath $configurePath -Destination (Join-Path $channelRoot 'configure_owner_candidate_channel.ps1') -Force
    Copy-Item -LiteralPath $verifierPath -Destination (Join-Path $channelRoot 'verify_owner_candidate_visibility.py') -Force
    Copy-Item -LiteralPath $handoffPath -Destination (Join-Path $channelRoot 'verify_owner_candidate_handoff.ps1') -Force

    Remove-Item -LiteralPath $previous -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $active -PathType Container) {
        Move-Item -LiteralPath $active -Destination $previous
    }
    Move-Item -LiteralPath $next -Destination $active

    try {
        $taskAction = New-ScheduledTaskAction -Execute $python -Argument ('"{0}" --root "{1}" --port {2}' -f (Join-Path $active 'owner_candidate_channel_server.py'), $active, $port)
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
        Start-ScheduledTask -TaskName $TaskName
        Wait-Channel -HealthUrl $healthUrl -ExpectedVersion ([string]$spec.candidate_version) -ExpectedSha ([string]$spec.candidate_sha256)
    } catch {
        Stop-ChannelTask -Port $port -ChannelRoot $channelRoot -Unregister $true
        Remove-Item -LiteralPath $active -Recurse -Force -ErrorAction SilentlyContinue
        if (Test-Path -LiteralPath $previous -PathType Container) {
            Move-Item -LiteralPath $previous -Destination $active
        }
        throw
    }

    Set-EnvValue -Path $envPath -Name 'UPDATE_MANIFEST_URL' -Value $candidateUrl
    $state = [ordered]@{
        schema_version = 1
        public_install_root = $installRoot
        expected_public_version = [string]$spec.expected_public_version
        production_manifest_url = $productionManifestUrl
        candidate_manifest_url = $candidateUrl
        candidate_version = [string]$spec.candidate_version
        candidate_sha256 = [string]$spec.candidate_sha256
        candidate_filename = [string]$spec.candidate_filename
        candidate_commit = [string]$spec.candidate_commit
        candidate_port = $port
        deployed_at = (Get-Date).ToString('o')
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statePath -Encoding UTF8
    Remove-Item -LiteralPath $previous -Recurse -Force -ErrorAction SilentlyContinue
    [pscustomobject]@{
        action = 'deployed'
        public_version = $installedVersion
        candidate_version = [string]$spec.candidate_version
        candidate_sha256 = $artifactSha
        manifest_url = $candidateUrl
        health = 'PASS'
        task = $TaskName
        task_state = [string](Get-ScheduledTask -TaskName $TaskName).State
    } | ConvertTo-Json -Compress
    exit 0
}

$channelRoot = Split-Path -Parent $SpecPath
$state = Read-State $channelRoot
$installRoot = [string]$state.public_install_root
$envPath = Join-Path $installRoot '.env'
$port = [int]$state.candidate_port
$installedVersion = Get-InstalledVersion $installRoot
$manifestUrl = Get-EnvValue (Read-EnvLines $envPath) 'UPDATE_MANIFEST_URL'

if ($Action -eq 'Restore') {
    Set-EnvValue -Path $envPath -Name 'UPDATE_MANIFEST_URL' -Value ([string]$state.production_manifest_url)
    Stop-ChannelTask -Port $port -ChannelRoot $channelRoot -Unregister $true
    [pscustomobject]@{
        action = 'restored'
        installed_version = $installedVersion
        manifest_url = [string]$state.production_manifest_url
        candidate_task_present = [bool](Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)
    } | ConvertTo-Json -Compress
    exit 0
}

$health = $null
try {
    $health = Invoke-RestMethod -UseBasicParsing -TimeoutSec 3 -Uri "http://127.0.0.1:$port/healthz"
} catch {}
[pscustomobject]@{
    action = 'status'
    installed_version = $installedVersion
    manifest_url = $manifestUrl
    candidate_version = [string]$state.candidate_version
    candidate_sha256 = [string]$state.candidate_sha256
    task_state = [string](Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue).State
    listener_pid = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess)
    health_version = if ($health) { [string]$health.version } else { $null }
    health_sha256 = if ($health) { [string]$health.sha256 } else { $null }
} | ConvertTo-Json -Compress
