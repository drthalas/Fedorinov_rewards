param(
    [string]$GateRoot = "C:\FedorinovGate"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "WindowsGate.Common.psm1") -Force
$resolvedRoot = Assert-GateChildPath -Path $GateRoot -GateRoot $GateRoot -AllowRoot

$directories = @(
    "Control",
    "Control\Installers",
    "Intake",
    "Baselines\CLEAN_WINDOWS_BASELINE",
    "Baselines\PREVIOUS_PUBLIC_VERSION_BASELINE",
    "MasterData",
    "Runs",
    "Evidence",
    "Scenarios\One Installation",
    "Scenarios\Multiple Installations",
    "Scenarios\Invalid Target",
    "Scenarios\Stale Installation",
    "Scenarios\Clean Installation",
    "Paths\Path With Spaces",
    "Paths\Путь с кириллицей"
)
foreach ($relative in $directories) {
    New-Item -ItemType Directory -Force -Path (Join-Path $resolvedRoot $relative) | Out-Null
}
New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE "Desktop\Fedorinov Gate") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $env:USERPROFILE "Downloads\Fedorinov Gate") | Out-Null

$os = Get-CimInstance Win32_OperatingSystem
$computer = Get-CimInstance Win32_ComputerSystem
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$profile = [ordered]@{
    schema = 1
    captured_at_utc = [DateTime]::UtcNow.ToString("o")
    hostname = $env:COMPUTERNAME
    windows_caption = $os.Caption
    windows_version = $os.Version
    windows_build = $os.BuildNumber
    architecture = $os.OSArchitecture
    memory_bytes = [long]$computer.TotalPhysicalMemory
    system_drive = [string]$disk.DeviceID
    system_drive_bytes = [long]$disk.Size
    system_drive_free_bytes = [long]$disk.FreeSpace
    filesystem = [string]$disk.FileSystem
    ui_culture = [Globalization.CultureInfo]::CurrentUICulture.Name
    culture = [Globalization.CultureInfo]::CurrentCulture.Name
    timezone = (Get-TimeZone).Id
    powershell = $PSVersionTable.PSVersion.ToString()
    sshd_status = (Get-Service sshd).Status.ToString()
    sshd_start_type = (Get-Service sshd).StartType.ToString()
    rdp_status = (Get-Service TermService).Status.ToString()
    rdp_start_type = (Get-Service TermService).StartType.ToString()
    gate_root = $resolvedRoot
    reset_mechanism = "scripted-product-and-synthetic-data-reset"
}
$profilePath = Join-Path $resolvedRoot "Baselines\CLEAN_WINDOWS_BASELINE\host-profile.json"
Write-AtomicJson -Value $profile -Path $profilePath

[pscustomobject]@{
    gate_root = $resolvedRoot
    host_profile = $profilePath
    directories = $directories.Count + 2
} | ConvertTo-Json -Compress
