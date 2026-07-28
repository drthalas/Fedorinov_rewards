param(
    [Parameter(Mandatory = $true)][string]$RunRoot,
    [Parameter(Mandatory = $true)][int]$AppPort,
    [string]$GateRoot = "C:\FedorinovGate"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "WindowsGate.Common.psm1") -Force
$resolvedRoot = Assert-GateChildPath -Path $RunRoot -GateRoot $GateRoot
$installRoot = Join-Path $resolvedRoot "Install"
$identity = Get-RuntimeIdentity -Port $AppPort -TimeoutSeconds 2
if ((Resolve-NormalizedPath ([string]$identity.install_root)) -ine (Resolve-NormalizedPath $installRoot)) {
    throw "Runtime identity belongs to a different installation."
}
$backends = @(Get-AppOwnedBackendProcesses $installRoot)
if ($backends.Count -ne 1) {
    throw "Expected exactly one app-owned backend for this installation."
}
if ([int]$backends[0].ProcessId -ne [int]$identity.pid) {
    throw "Runtime identity PID does not match the app-owned process."
}

Stop-Process -Id ([int]$identity.pid)
$deadline = [DateTime]::UtcNow.AddSeconds(15)
while (Get-Process -Id ([int]$identity.pid) -ErrorAction SilentlyContinue) {
    if ([DateTime]::UtcNow -ge $deadline) {
        throw "The confirmed app-owned backend did not stop within 15 seconds."
    }
    Start-Sleep -Milliseconds 200
}
try {
    $remaining = Get-RuntimeIdentity -Port $AppPort -TimeoutSeconds 1
}
catch {
    $remaining = $null
}
if ($remaining) {
    throw "Runtime identity is still available after stopping the confirmed backend."
}

[pscustomobject]@{
    stopped = $true
    pid = [int]$identity.pid
    install_root = $installRoot
    port = $AppPort
} | ConvertTo-Json -Compress
