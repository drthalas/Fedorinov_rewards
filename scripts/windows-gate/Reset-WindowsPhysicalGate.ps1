param(
    [Parameter(Mandatory = $true)][string]$PreviousVersion,
    [Parameter(Mandatory = $true)][ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")][string]$RunId,
    [int]$AppPort = 18090,
    [string]$GateRoot = "C:\FedorinovGate",
    [switch]$ReplaceExisting
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "WindowsGate.Common.psm1") -Force
$resolvedRoot = Assert-GateChildPath -Path $GateRoot -GateRoot $GateRoot -AllowRoot
$baseline = Join-Path $resolvedRoot "Baselines\PREVIOUS_PUBLIC_VERSION_BASELINE\$PreviousVersion"
$manifestPath = Join-Path $baseline "baseline.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Baseline manifest does not exist: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$installMaster = Join-Path $baseline "Install"
$dataMaster = Join-Path $baseline "DataMaster"
if ((Get-TreeFingerprint $installMaster) -cne [string]$manifest.install_fingerprint) {
    throw "Immutable install baseline fingerprint changed."
}
if ((Get-TreeFingerprint $dataMaster) -cne [string]$manifest.data_fingerprint) {
    throw "Immutable data baseline fingerprint changed."
}

$runRoot = Join-Path $resolvedRoot "Runs\$RunId"
Assert-GateChildPath -Path $runRoot -GateRoot $resolvedRoot | Out-Null
if (Test-Path -LiteralPath $runRoot) {
    if (-not $ReplaceExisting) {
        throw "Run already exists. Use a new RunId or pass -ReplaceExisting."
    }
    $existingInstall = Join-Path $runRoot "Install"
    if (@(Get-AppOwnedBackendProcesses $existingInstall).Count -gt 0) {
        throw "An app-owned backend is still running from the run being reset."
    }
    Remove-Item -LiteralPath $runRoot -Recurse -Force
}

$staging = Join-Path $resolvedRoot "Runs\.staging-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $staging | Out-Null
try {
    Copy-Item -LiteralPath $installMaster -Destination (Join-Path $staging "Install") -Recurse
    Copy-Item -LiteralPath $dataMaster -Destination (Join-Path $staging "Data") -Recurse
    Get-ChildItem -LiteralPath (Join-Path $staging "Data") -File -Recurse | ForEach-Object {
        $_.IsReadOnly = $false
    }
    $install = Join-Path $staging "Install"
    $data = Join-Path $staging "Data"
    $finalData = Join-Path $runRoot "Data"
    $envLines = @(
        "REWARDS_DATA_DIR=$finalData",
        "REWARDS_DB_PATH=$(Join-Path $finalData 'database\MyDatabase.sqlite')",
        "APP_HOST=127.0.0.1",
        "APP_PORT=$AppPort",
        "READ_ONLY=false",
        "WRITE_MODE=true",
        "UPDATE_CHECK_ENABLED=true"
    )
    [System.IO.File]::WriteAllLines((Join-Path $install ".env"), $envLines, [System.Text.UTF8Encoding]::new($false))
    $runManifest = [ordered]@{
        schema = 1
        run_id = $RunId
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        previous_version = $PreviousVersion
        app_port = $AppPort
        baseline_install_fingerprint = [string]$manifest.install_fingerprint
        baseline_data_fingerprint = [string]$manifest.data_fingerprint
        run_data_fingerprint = Get-TreeFingerprint $data
    }
    Write-AtomicJson -Value $runManifest -Path (Join-Path $staging "run.json")
    Move-Item -LiteralPath $staging -Destination $runRoot
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

[pscustomobject]@{
    run_root = $runRoot
    install_root = Join-Path $runRoot "Install"
    data_root = Join-Path $runRoot "Data"
    app_port = $AppPort
    baseline_data_fingerprint = [string]$manifest.data_fingerprint
} | ConvertTo-Json -Compress
