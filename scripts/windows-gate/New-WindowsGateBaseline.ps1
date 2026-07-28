param(
    [Parameter(Mandatory = $true)][string]$PreviousPublicArchive,
    [Parameter(Mandatory = $true)][string]$PreviousVersion,
    [Parameter(Mandatory = $true)][long]$ExpectedArchiveSize,
    [Parameter(Mandatory = $true)][string]$ExpectedArchiveSha256,
    [Parameter(Mandatory = $true)][string]$SyntheticDataPath,
    [string]$GateRoot = "C:\FedorinovGate"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "WindowsGate.Common.psm1") -Force
$resolvedRoot = Assert-GateChildPath -Path $GateRoot -GateRoot $GateRoot -AllowRoot
$archive = Get-Item -LiteralPath $PreviousPublicArchive
if ($archive.Length -ne $ExpectedArchiveSize) {
    throw "Previous public archive size mismatch."
}
if ((Get-FileSha256 $archive.FullName) -cne $ExpectedArchiveSha256) {
    throw "Previous public archive SHA256 mismatch."
}
if (-not (Test-Path -LiteralPath $SyntheticDataPath -PathType Container)) {
    throw "Synthetic data root does not exist: $SyntheticDataPath"
}

$baseline = Join-Path $resolvedRoot "Baselines\PREVIOUS_PUBLIC_VERSION_BASELINE\$PreviousVersion"
Assert-GateChildPath -Path $baseline -GateRoot $resolvedRoot | Out-Null
if (Test-Path -LiteralPath $baseline) {
    throw "Baseline already exists and is immutable: $baseline"
}
$staging = Join-Path $resolvedRoot "Baselines\.staging-$([Guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $staging | Out-Null
try {
    Expand-Archive -LiteralPath $archive.FullName -DestinationPath (Join-Path $staging "archive") -Force
    $roots = @(Get-ChildItem -LiteralPath (Join-Path $staging "archive") -Directory)
    if ($roots.Count -ne 1) {
        throw "Release archive must contain exactly one root directory."
    }
    $install = Join-Path $staging "Install"
    Move-Item -LiteralPath $roots[0].FullName -Destination $install
    foreach ($required in @("start_windows.bat", "start_windows.ps1", "backend\requirements.txt", "scripts\runtime_server.py")) {
        if (-not (Test-Path -LiteralPath (Join-Path $install $required) -PathType Leaf)) {
            throw "Previous public package is missing $required."
        }
    }
    $data = Join-Path $staging "DataMaster"
    Copy-Item -LiteralPath $SyntheticDataPath -Destination $data -Recurse
    $db = Join-Path $data "database\MyDatabase.sqlite"
    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) {
        throw "Synthetic data master is missing database\MyDatabase.sqlite."
    }

    $manifest = [ordered]@{
        schema = 1
        created_at_utc = [DateTime]::UtcNow.ToString("o")
        previous_version = $PreviousVersion
        archive_filename = $archive.Name
        archive_size_bytes = $archive.Length
        archive_sha256 = $ExpectedArchiveSha256
        install_fingerprint = Get-TreeFingerprint $install
        data_fingerprint = Get-TreeFingerprint $data
        data_files = @(Get-TreeInventory $data).Count
        reset_mechanism = "copy-immutable-master-to-unique-run"
    }
    Write-AtomicJson -Value $manifest -Path (Join-Path $staging "baseline.json")
    Move-Item -LiteralPath $staging -Destination $baseline
    Get-ChildItem -LiteralPath (Join-Path $baseline "DataMaster") -File -Recurse | ForEach-Object {
        $_.IsReadOnly = $true
    }
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

[pscustomobject]@{
    baseline = $baseline
    previous_version = $PreviousVersion
    install_fingerprint = $manifest.install_fingerprint
    data_fingerprint = $manifest.data_fingerprint
} | ConvertTo-Json -Compress
