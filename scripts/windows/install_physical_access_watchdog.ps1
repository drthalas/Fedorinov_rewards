param(
    [string]$TaskName = 'FedorinovRewards-Physical-Access-Watchdog',
    [string]$InstallRoot = 'C:\ProgramData\FedorinovGate\PhysicalAccess'
)

$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'physical_access_watchdog.ps1'
if (-not (Test-Path -LiteralPath $source)) {
    throw "Missing watchdog source: $source"
}

New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
$target = Join-Path $InstallRoot 'physical_access_watchdog.ps1'
$rollbackScript = Join-Path $InstallRoot 'rollback_physical_access_watchdog.ps1'
$rollbackPath = Join-Path $InstallRoot 'rollback-before-install.json'
if (-not (Test-Path -LiteralPath $rollbackPath)) {
    $scheme = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes').ActivePowerScheme
    $settings = @(
        @('238c9fa8-0aad-41ed-83f4-97be242c8f20', '29f6c1db-86da-48c5-9fdb-f2b67b1f44da'),
        @('238c9fa8-0aad-41ed-83f4-97be242c8f20', '9d7815a6-7ee4-497e-8888-515a05f02364'),
        @('238c9fa8-0aad-41ed-83f4-97be242c8f20', '94ac6d29-73ce-41a6-809f-6363ba21b47e'),
        @('238c9fa8-0aad-41ed-83f4-97be242c8f20', '7bc4a2f9-d8fc-4469-b07b-33eb785aaca0'),
        @('4f971e89-eebd-4455-a8de-9e59040e7347', '5ca83367-6e45-459f-a27b-476b1d01c936'),
        @('4f971e89-eebd-4455-a8de-9e59040e7347', '96996bc0-ad50-47ec-923b-6f41874dd9eb')
    )
    $power = foreach ($setting in $settings) {
        $path = "HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\$scheme\$($setting[0])\$($setting[1])"
        $value = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
        [ordered]@{
            subgroup = $setting[0]
            setting = $setting[1]
            ac = $value.ACSettingIndex
            dc = $value.DCSettingIndex
        }
    }
    $services = foreach ($serviceName in @('sshd', 'TermService')) {
        $service = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"
        [ordered]@{
            name = $serviceName
            start_mode = $service.StartMode
            state = $service.State
        }
    }
    $failureRegistry = Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Services\sshd' `
        -ErrorAction SilentlyContinue
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    $taskXml = if ($existingTask) { Export-ScheduledTask -TaskName $TaskName } else { $null }
    [ordered]@{
        captured_at = (Get-Date).ToString('o')
        active_scheme = $scheme
        services = @($services)
        sshd_failure_actions_base64 = if ($failureRegistry.FailureActions) {
            [Convert]::ToBase64String($failureRegistry.FailureActions)
        } else { $null }
        sshd_failure_on_non_crash = $failureRegistry.FailureActionsOnNonCrashFailures
        watchdog_preexisting = [bool]$existingTask
        watchdog_xml = $taskXml
        power = @($power)
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $rollbackPath -Encoding UTF8
}
Copy-Item -LiteralPath $source -Destination $target -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'rollback_physical_access_watchdog.ps1') `
    -Destination $rollbackScript -Force

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$target`""
$startup = New-ScheduledTaskTrigger -AtStartup
$periodic = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal `
    -UserId 'SYSTEM' `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger @($startup, $periodic) `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

& sc.exe failure sshd reset= 86400 actions= restart/5000/restart/15000/restart/30000 | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not configure sshd recovery actions.' }
& sc.exe failureflag sshd 1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not enable sshd non-crash recovery.' }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $target
Start-ScheduledTask -TaskName $TaskName
$deadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 250
    $task = Get-ScheduledTask -TaskName $TaskName
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
} while ($task.State -eq 'Running' -and (Get-Date) -lt $deadline)
if ($task.State -eq 'Running') { throw 'Watchdog task did not finish within 30 seconds.' }
if ($info.LastTaskResult -ne 0) {
    throw "Watchdog task failed with result $($info.LastTaskResult)."
}
[ordered]@{
    task = $task.TaskName
    state = [string]$task.State
    principal = $task.Principal.UserId
    run_level = [string]$task.Principal.RunLevel
    triggers = $task.Triggers.Count
    last_run = $info.LastRunTime.ToString('o')
    last_result = $info.LastTaskResult
    script_sha256 = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
} | ConvertTo-Json -Compress
