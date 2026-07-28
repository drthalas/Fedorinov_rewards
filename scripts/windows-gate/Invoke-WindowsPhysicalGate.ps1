param(
    [Parameter(Mandatory = $true)][string]$CandidateManifest,
    [Parameter(Mandatory = $true)][string]$PreviousVersion,
    [Parameter(Mandatory = $true)][ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")][string]$RunId,
    [int]$AppPort = 18090,
    [int]$FeedPort = 18089,
    [string]$GateRoot = "C:\FedorinovGate",
    [switch]$ApplyUpdate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Import-Module (Join-Path $PSScriptRoot "WindowsGate.Common.psm1") -Force
$resolvedRoot = Assert-GateChildPath -Path $GateRoot -GateRoot $GateRoot -AllowRoot
$candidate = Read-CandidateManifest $CandidateManifest
$candidateArchive = Join-Path (Split-Path -Parent $CandidateManifest) ([string]$candidate.filename)
Assert-CandidateArtifact -ManifestPath $CandidateManifest -ArchivePath $candidateArchive | Out-Null

$resetScript = Join-Path $PSScriptRoot "Reset-WindowsPhysicalGate.ps1"
$resetJson = & $resetScript `
    -PreviousVersion $PreviousVersion `
    -RunId $RunId `
    -AppPort $AppPort `
    -GateRoot $resolvedRoot
$run = $resetJson | ConvertFrom-Json
$installRoot = [string]$run.install_root
$dataRoot = [string]$run.data_root
$beforeData = Get-TreeFingerprint $dataRoot

$feedRoot = Join-Path ([string]$run.run_root) "CandidateFeed"
New-Item -ItemType Directory -Force -Path $feedRoot | Out-Null
Copy-Item -LiteralPath $candidateArchive -Destination (Join-Path $feedRoot $candidate.filename)
$latest = [ordered]@{
    version = [string]$candidate.version
    released_at = [DateTime]::UtcNow.ToString("yyyy-MM-dd")
    download_url = "http://127.0.0.1:$FeedPort/$($candidate.filename)"
    sha256 = [string]$candidate.sha256
    notes = @("Physical Windows gate candidate")
}
Write-AtomicJson -Value $latest -Path (Join-Path $feedRoot "latest.json")
Add-Content -LiteralPath (Join-Path $installRoot ".env") -Encoding UTF8 -Value "UPDATE_MANIFEST_URL=http://127.0.0.1:$FeedPort/latest.json"

$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Gate control Python 3.11 is not installed at the expected app-owned path."
}
$evidenceRoot = Join-Path $resolvedRoot "Evidence\$RunId"
New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
$feedOutLog = Join-Path $evidenceRoot "candidate-feed.out.log"
$feedErrLog = Join-Path $evidenceRoot "candidate-feed.err.log"
$launcherOutLog = Join-Path $evidenceRoot "launcher.out.log"
$launcherErrLog = Join-Path $evidenceRoot "launcher.err.log"
$feedProcess = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "http.server", "$FeedPort", "--bind", "127.0.0.1", "--directory", $feedRoot) `
    -RedirectStandardOutput $feedOutLog `
    -RedirectStandardError $feedErrLog `
    -PassThru `
    -WindowStyle Hidden
try {
    $launcher = Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/d", "/c", "`"$(Join-Path $installRoot 'start_windows.bat')`"") `
        -WorkingDirectory $installRoot `
        -RedirectStandardOutput $launcherOutLog `
        -RedirectStandardError $launcherErrLog `
        -PassThru
    $oldIdentity = Wait-RuntimeIdentity `
        -Port $AppPort `
        -Version $PreviousVersion `
        -InstallRoot $installRoot `
        -TimeoutSeconds 300
    if (@(Get-AppOwnedBackendProcesses $installRoot).Count -ne 1) {
        throw "Exactly one app-owned backend was not confirmed before update."
    }

    $result = [ordered]@{
        run_id = $RunId
        previous_identity = $oldIdentity
        candidate_version = [string]$candidate.version
        candidate_sha256 = [string]$candidate.sha256
        candidate_commit = [string]$candidate.commit_sha
        update_applied = $false
        final_identity = $oldIdentity
    }
    if ($ApplyUpdate) {
        Invoke-RestMethod `
            -Method Post `
            -Uri "http://127.0.0.1:$AppPort/updates/apply" `
            -ContentType "application/x-www-form-urlencoded" `
            -Headers @{Accept = "application/json"} `
            -Body "confirm_update=true" | Out-Null
        $newIdentity = Wait-RuntimeIdentity `
            -Port $AppPort `
            -Version ([string]$candidate.version) `
            -InstallRoot $installRoot `
            -TimeoutSeconds 300
        if (@(Get-AppOwnedBackendProcesses $installRoot).Count -ne 1) {
            throw "Exactly one app-owned backend was not confirmed after update."
        }
        $result.update_applied = $true
        $result.final_identity = $newIdentity
    }

    $afterData = Get-TreeFingerprint $dataRoot
    if ($afterData -cne $beforeData) {
        throw "DB/media fingerprint changed during package lifecycle gate."
    }
    $result.data_fingerprint_before = $beforeData
    $result.data_fingerprint_after = $afterData
    $result.launcher_pid = $launcher.Id
    $result.feed_pid = $feedProcess.Id
    $result.evidence_root = $evidenceRoot
    Write-AtomicJson -Value $result -Path (Join-Path $evidenceRoot "result.json")
    $result | ConvertTo-Json -Depth 12 -Compress
}
finally {
    if ($feedProcess -and -not $feedProcess.HasExited) {
        Stop-Process -Id $feedProcess.Id -Force
    }
}
