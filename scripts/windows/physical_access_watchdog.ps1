param(
    [string]$StateRoot = 'C:\ProgramData\FedorinovGate\PhysicalAccess'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
$statusPath = Join-Path $StateRoot 'status.json'
$historyPath = Join-Path $StateRoot 'history.jsonl'
$repairs = [System.Collections.Generic.List[string]]::new()
$failures = [System.Collections.Generic.List[string]]::new()

function Set-PowerValue {
    param(
        [string]$Subgroup,
        [string]$Setting,
        [int]$Value
    )

    $scheme = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes').ActivePowerScheme
    $settingPath = "HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\$scheme\$Subgroup\$Setting"
    $current = Get-ItemProperty -Path $settingPath -ErrorAction SilentlyContinue
    if ($current -and $current.ACSettingIndex -eq $Value) {
        return
    }
    & powercfg.exe /setacvalueindex SCHEME_CURRENT $Subgroup $Setting $Value | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "powercfg failed for $Subgroup/$Setting"
    }
    $repairs.Add("power-ac:$Subgroup/$Setting=$Value")
}

function Ensure-ServiceReady {
    param([string]$Name)

    $service = Get-Service -Name $Name -ErrorAction Stop
    if ($service.StartType -ne 'Automatic') {
        Set-Service -Name $Name -StartupType Automatic
        $repairs.Add("service:$Name:automatic")
    }
    if ($service.Status -ne 'Running') {
        Start-Service -Name $Name
        $repairs.Add("service:$Name:started")
    }
}

try {
    $sleepGroup = '238c9fa8-0aad-41ed-83f4-97be242c8f20'
    $buttonGroup = '4f971e89-eebd-4455-a8de-9e59040e7347'
    Set-PowerValue $sleepGroup '29f6c1db-86da-48c5-9fdb-f2b67b1f44da' 0
    Set-PowerValue $sleepGroup '9d7815a6-7ee4-497e-8888-515a05f02364' 0
    Set-PowerValue $sleepGroup '94ac6d29-73ce-41a6-809f-6363ba21b47e' 0
    Set-PowerValue $sleepGroup '7bc4a2f9-d8fc-4469-b07b-33eb785aaca0' 0
    Set-PowerValue $buttonGroup '5ca83367-6e45-459f-a27b-476b1d01c936' 0
    Set-PowerValue $buttonGroup '96996bc0-ad50-47ec-923b-6f41874dd9eb' 0
    & powercfg.exe /setactive SCHEME_CURRENT | Out-Null

    Ensure-ServiceReady sshd
    Ensure-ServiceReady TermService

    $networkDeadline = (Get-Date).AddSeconds(60)
    do {
        $profile = Get-NetConnectionProfile -ErrorAction SilentlyContinue |
            Where-Object { [string]$_.IPv4Connectivity -ne 'Disconnected' } |
            Select-Object -First 1
        if ($profile) { break }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $networkDeadline)
    if (-not $profile -or [string]$profile.IPv4Connectivity -eq 'Disconnected') {
        $failures.Add('network:no-ipv4-connectivity')
    }
    if ($profile -and [string]$profile.NetworkCategory -ne 'Private') {
        $failures.Add("network:unexpected-profile:$($profile.NetworkCategory)")
    }

    foreach ($port in @(22, 3389)) {
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
            $failures.Add("listener:missing:$port")
        }
    }

    foreach ($ruleName in @(
        'FedorinovGate-SSH-LAN',
        'FedorinovGate-RDP-TCP-LAN',
        'FedorinovGate-RDP-UDP-LAN'
    )) {
        $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if (-not $rule -or [string]$rule.Enabled -ne 'True') {
            $failures.Add("firewall:missing-or-disabled:$ruleName")
        } else {
            $address = $rule | Get-NetFirewallAddressFilter -ErrorAction SilentlyContinue
            if (-not $address -or $address.RemoteAddress -contains 'Any') {
                $failures.Add("firewall:unbounded-remote-scope:$ruleName")
            }
        }
    }

    foreach ($corporateService in @('CcmExec', 'SccmLauncher')) {
        $service = Get-Service -Name $corporateService -ErrorAction SilentlyContinue
        if ($service -and ($service.Status -ne 'Stopped' -or $service.StartType -ne 'Disabled')) {
            $failures.Add("corporate-drift:service:$corporateService")
        }
    }
    $healthTask = Get-ScheduledTask -TaskName 'Configuration Manager Health Evaluation' -ErrorAction SilentlyContinue
    if ($healthTask -and $healthTask.State -ne 'Disabled') {
        $failures.Add('corporate-drift:configuration-manager-health-task')
    }
} catch {
    $failures.Add("watchdog:$($_.Exception.Message)")
}

$payload = [ordered]@{
    checked_at = (Get-Date).ToString('o')
    healthy = ($failures.Count -eq 0)
    repairs = @($repairs)
    failures = @($failures)
    boot_time = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('o')
    sshd = [string](Get-Service sshd -ErrorAction SilentlyContinue).Status
    term_service = [string](Get-Service TermService -ErrorAction SilentlyContinue).Status
    network_profile = [string](Get-NetConnectionProfile -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty NetworkCategory)
}
$json = $payload | ConvertTo-Json -Compress
$json | Set-Content -LiteralPath $statusPath -Encoding UTF8
$json | Add-Content -LiteralPath $historyPath -Encoding UTF8

if ($failures.Count -gt 0) {
    Write-Error ($failures -join '; ')
    exit 1
}
$json
