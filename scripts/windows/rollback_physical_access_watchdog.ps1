param(
    [string]$TaskName = 'FedorinovRewards-Physical-Access-Watchdog',
    [string]$InstallRoot = 'C:\ProgramData\FedorinovGate\PhysicalAccess'
)

$ErrorActionPreference = 'Stop'
$snapshotPath = Join-Path $InstallRoot 'rollback-before-install.json'
if (-not (Test-Path -LiteralPath $snapshotPath)) {
    throw "Rollback snapshot is missing: $snapshotPath"
}
$snapshot = Get-Content -LiteralPath $snapshotPath -Raw | ConvertFrom-Json

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
if ($snapshot.watchdog_preexisting -and $snapshot.watchdog_xml) {
    Register-ScheduledTask -TaskName $TaskName -Xml ([string]$snapshot.watchdog_xml) -Force | Out-Null
}

foreach ($setting in $snapshot.power) {
    & powercfg.exe /setacvalueindex $snapshot.active_scheme $setting.subgroup $setting.setting `
        ([int]$setting.ac) | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not restore AC power value $($setting.setting)." }
}
& powercfg.exe /setactive $snapshot.active_scheme | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not reactivate the original power scheme.' }

foreach ($serviceSnapshot in $snapshot.services) {
    $startupType = switch ([string]$serviceSnapshot.start_mode) {
        'Auto' { 'Automatic' }
        'Manual' { 'Manual' }
        'Disabled' { 'Disabled' }
        default { throw "Unknown original service start mode: $($serviceSnapshot.start_mode)" }
    }
    Set-Service -Name $serviceSnapshot.name -StartupType $startupType
    if ($serviceSnapshot.state -eq 'Running') {
        Start-Service -Name $serviceSnapshot.name
    } else {
        Stop-Service -Name $serviceSnapshot.name -Force -ErrorAction SilentlyContinue
    }
}

$serviceKey = 'HKLM:\SYSTEM\CurrentControlSet\Services\sshd'
if ($snapshot.sshd_failure_actions_base64) {
    Set-ItemProperty -Path $serviceKey -Name FailureActions `
        -Value ([Convert]::FromBase64String([string]$snapshot.sshd_failure_actions_base64))
} else {
    Remove-ItemProperty -Path $serviceKey -Name FailureActions -ErrorAction SilentlyContinue
}
if ($null -ne $snapshot.sshd_failure_on_non_crash) {
    Set-ItemProperty -Path $serviceKey -Name FailureActionsOnNonCrashFailures `
        -Value ([int]$snapshot.sshd_failure_on_non_crash)
} else {
    Remove-ItemProperty -Path $serviceKey -Name FailureActionsOnNonCrashFailures `
        -ErrorAction SilentlyContinue
}

[ordered]@{
    rolled_back_at = (Get-Date).ToString('o')
    task_restored = [bool]$snapshot.watchdog_preexisting
    active_scheme = [string]$snapshot.active_scheme
    services = @($snapshot.services | ForEach-Object { $_.name })
} | ConvertTo-Json -Compress
