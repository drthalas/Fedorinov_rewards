param(
    [string]$WatchdogTaskName = 'FedorinovRewards-Physical-Access-Watchdog',
    [string]$GuiTaskName = 'FedorinovRewards-Physical-GUI'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$failures = [System.Collections.Generic.List[string]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

foreach ($serviceName in @('sshd', 'TermService')) {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if (-not $service) { $failures.Add("service-missing:$serviceName"); continue }
    if ($service.Status -ne 'Running') { $failures.Add("service-stopped:$serviceName") }
    if ($service.StartType -ne 'Automatic') { $failures.Add("service-not-automatic:$serviceName") }
}
foreach ($port in @(22, 3389)) {
    if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
        $failures.Add("listener-missing:$port")
    }
}

$profile = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $profile) { $failures.Add('network-profile-missing') }
elseif ($profile.NetworkCategory -ne 'Private') { $failures.Add("network-profile:$($profile.NetworkCategory)") }

$watchdog = Get-ScheduledTask -TaskName $WatchdogTaskName -ErrorAction SilentlyContinue
if (-not $watchdog) { $failures.Add('watchdog-task-missing') }
elseif ($watchdog.State -eq 'Disabled') { $failures.Add('watchdog-task-disabled') }
$watchdogStatus = 'C:\ProgramData\FedorinovGate\PhysicalAccess\status.json'
if (-not (Test-Path -LiteralPath $watchdogStatus)) { $failures.Add('watchdog-status-missing') }
else {
    $status = Get-Content -LiteralPath $watchdogStatus -Raw | ConvertFrom-Json
    if (-not $status.healthy) { $failures.Add('watchdog-reports-drift') }
    if ((Get-Date) - [datetime]$status.checked_at -gt (New-TimeSpan -Minutes 10)) {
        $failures.Add('watchdog-status-stale')
    }
}

$sleepEvents = @(Get-WinEvent -FilterHashtable @{
    LogName = 'System'
    ProviderName = 'Microsoft-Windows-Kernel-Power'
    Id = 42
    StartTime = (Get-Date).AddHours(-24)
} -ErrorAction SilentlyContinue)
if ($sleepEvents.Count -gt 0) { $warnings.Add("sleep-events-24h:$($sleepEvents.Count)") }

$explorers = @(Get-Process explorer -ErrorAction SilentlyContinue)
$dwms = @(Get-Process dwm -ErrorAction SilentlyContinue)
$guiTask = Get-ScheduledTask -TaskName $GuiTaskName -ErrorAction SilentlyContinue
$interactiveReady = [bool]($explorers.Count -gt 0 -and $dwms.Count -gt 0 -and $guiTask)
if (-not $interactiveReady) { $warnings.Add('gui-unavailable') }

[ordered]@{
    checked_at = (Get-Date).ToString('o')
    healthy = ($failures.Count -eq 0)
    interactive_ready = $interactiveReady
    failures = @($failures)
    warnings = @($warnings)
    boot_time = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('o')
    watchdog_last_run = if ($watchdog) { (Get-ScheduledTaskInfo -TaskName $WatchdogTaskName).LastRunTime.ToString('o') } else { $null }
    sessions = (query session | Out-String).Trim()
} | ConvertTo-Json -Depth 5

if ($failures.Count -gt 0) { exit 1 }
