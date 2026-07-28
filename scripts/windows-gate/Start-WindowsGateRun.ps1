param(
    [Parameter(Mandatory = $true)][string]$RunRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][int]$AppPort,
    [string]$GateRoot = "C:\FedorinovGate",
    [switch]$OpenBrowser,
    [switch]$Hold
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "WindowsGate.Common.psm1") -Force
$resolvedRoot = Assert-GateChildPath -Path $RunRoot -GateRoot $GateRoot
$installRoot = Join-Path $resolvedRoot "Install"
$launcher = Join-Path $installRoot "start_windows.bat"
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "Normal Windows launcher does not exist: $launcher"
}
if (@(Get-AppOwnedBackendProcesses $installRoot).Count -ne 0) {
    throw "An app-owned backend is already running from this gate run."
}

$evidenceRoot = Join-Path $GateRoot "Evidence\$(Split-Path -Leaf $resolvedRoot)"
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$outLog = Join-Path $evidenceRoot "start.out.log"
$errLog = Join-Path $evidenceRoot "start.err.log"
$arguments = @("/d", "/c", "`"$launcher`"")
$process = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList $arguments `
    -WorkingDirectory $installRoot `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

$identity = Wait-RuntimeIdentity `
    -Port $AppPort `
    -Version $ExpectedVersion `
    -InstallRoot $installRoot `
    -TimeoutSeconds 300
$backends = @(Get-AppOwnedBackendProcesses $installRoot)
if ($backends.Count -ne 1 -or [int]$backends[0].ProcessId -ne [int]$identity.pid) {
    throw "Exactly one strictly identified app-owned backend was not confirmed."
}
if ($OpenBrowser) {
    Start-Process "http://127.0.0.1:$AppPort/legacy?tab=rewards"
}

$result = [ordered]@{
    started_at_utc = [DateTime]::UtcNow.ToString("o")
    run_root = $resolvedRoot
    install_root = $installRoot
    launcher_pid = $process.Id
    backend_pid = [int]$identity.pid
    version = [string]$identity.version
    build_id = [string]$identity.build_id
    instance_token = [string]$identity.instance_token
    port = [int]$identity.port
    url = "http://127.0.0.1:$AppPort/legacy?tab=rewards"
}
Write-AtomicJson -Value $result -Path (Join-Path $evidenceRoot "start.json")
$result | ConvertTo-Json -Compress
if ($Hold) {
    Wait-Process -Id ([int]$identity.pid)
}
