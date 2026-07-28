param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$CommitSha,
    [Parameter(Mandatory = $true)][long]$ExpectedSize,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [Parameter(Mandatory = $true)][string]$Source,
    [string]$GateRoot = "C:\FedorinovGate"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "WindowsGate.Common.psm1") -Force
$resolvedRoot = Assert-GateChildPath -Path $GateRoot -GateRoot $GateRoot -AllowRoot
$archive = Get-Item -LiteralPath $ArchivePath
if ($archive.Extension -cne ".zip") {
    throw "Release candidate must be a ZIP archive."
}
if ($Version -notmatch "^\d+\.\d+\.\d+$") {
    throw "Version must use MAJOR.MINOR.PATCH format."
}
if ($CommitSha -notmatch "^[0-9a-f]{40}$") {
    throw "Commit SHA must contain exactly 40 lowercase hex characters."
}
if ($ExpectedSha256 -notmatch "^[0-9a-f]{64}$") {
    throw "Expected SHA256 must contain exactly 64 lowercase hex characters."
}
if ($archive.Length -ne $ExpectedSize) {
    throw "Candidate size mismatch: $($archive.Length) != $ExpectedSize"
}
$actualSha = Get-FileSha256 $archive.FullName
if ($actualSha -cne $ExpectedSha256) {
    throw "Candidate SHA256 mismatch: $actualSha != $ExpectedSha256"
}

$intake = Join-Path $resolvedRoot "Intake\$Version"
Assert-GateChildPath -Path $intake -GateRoot $resolvedRoot | Out-Null
New-Item -ItemType Directory -Force -Path $intake | Out-Null
$destination = Join-Path $intake $archive.Name
Copy-Item -LiteralPath $archive.FullName -Destination $destination -Force
if ((Get-FileSha256 $destination) -cne $ExpectedSha256) {
    throw "Transferred candidate bytes do not match the accepted artifact."
}

$manifest = [ordered]@{
    schema = 1
    imported_at_utc = [DateTime]::UtcNow.ToString("o")
    filename = $archive.Name
    version = $Version
    commit_sha = $CommitSha
    size_bytes = $ExpectedSize
    sha256 = $ExpectedSha256
    source = $Source
}
$manifestPath = Join-Path $intake "candidate.json"
Write-AtomicJson -Value $manifest -Path $manifestPath
Assert-CandidateArtifact -ManifestPath $manifestPath -ArchivePath $destination | Out-Null

[pscustomobject]@{
    manifest = $manifestPath
    archive = $destination
    size_bytes = $ExpectedSize
    sha256 = $ExpectedSha256
} | ConvertTo-Json -Compress
