Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-NormalizedPath {
    param([Parameter(Mandatory = $true)][string]$Path)

    return [System.IO.Path]::GetFullPath($Path).TrimEnd("\")
}

function Assert-GateChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$GateRoot,
        [switch]$AllowRoot
    )

    $resolvedRoot = Resolve-NormalizedPath $GateRoot
    $resolvedPath = Resolve-NormalizedPath $Path
    if ($AllowRoot -and $resolvedPath -ieq $resolvedRoot) {
        return $resolvedPath
    }
    if (-not $resolvedPath.StartsWith("$resolvedRoot\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the Windows gate root: $resolvedPath"
    }
    return $resolvedPath
}

function Get-FileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-TreeInventory {
    param([Parameter(Mandatory = $true)][string]$Path)

    $root = Resolve-NormalizedPath $Path
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw "Directory does not exist: $root"
    }
    $items = @()
    foreach ($file in Get-ChildItem -LiteralPath $root -File -Recurse | Sort-Object FullName) {
        if (($file.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Reparse points are not allowed in gate data: $($file.FullName)"
        }
        $relative = $file.FullName.Substring($root.Length).TrimStart("\").Replace("\", "/")
        $items += [ordered]@{
            path = $relative
            bytes = $file.Length
            sha256 = Get-FileSha256 $file.FullName
        }
    }
    return $items
}

function Get-TreeFingerprint {
    param([Parameter(Mandatory = $true)][string]$Path)

    $inventory = @(Get-TreeInventory $Path)
    $lines = foreach ($item in $inventory) {
        "{0}`t{1}`t{2}" -f $item.path, $item.bytes, $item.sha256
    }
    $payload = [System.Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($sha.ComputeHash($payload))).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Write-AtomicJson {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Path
    )

    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temporary = "$Path.tmp-$([Guid]::NewGuid().ToString('N'))"
    try {
        $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
        Move-Item -LiteralPath $temporary -Destination $Path -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Read-CandidateManifest {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Candidate manifest does not exist: $Path"
    }
    $manifest = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($name in @("filename", "version", "commit_sha", "size_bytes", "sha256", "source")) {
        if (-not $manifest.PSObject.Properties.Name.Contains($name) -or -not $manifest.$name) {
            throw "Candidate manifest is missing '$name'."
        }
    }
    if ($manifest.commit_sha -notmatch "^[0-9a-f]{40}$") {
        throw "Candidate commit SHA must contain exactly 40 lowercase hex characters."
    }
    if ($manifest.sha256 -notmatch "^[0-9a-f]{64}$") {
        throw "Candidate SHA256 must contain exactly 64 lowercase hex characters."
    }
    if ([long]$manifest.size_bytes -le 0) {
        throw "Candidate size must be positive."
    }
    return $manifest
}

function Assert-CandidateArtifact {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)][string]$ArchivePath
    )

    $manifest = Read-CandidateManifest $ManifestPath
    $archive = Get-Item -LiteralPath $ArchivePath
    if ($archive.Name -cne [string]$manifest.filename) {
        throw "Candidate filename mismatch: $($archive.Name) != $($manifest.filename)"
    }
    if ($archive.Length -ne [long]$manifest.size_bytes) {
        throw "Candidate size mismatch: $($archive.Length) != $($manifest.size_bytes)"
    }
    $sha = Get-FileSha256 $archive.FullName
    if ($sha -cne [string]$manifest.sha256) {
        throw "Candidate SHA256 mismatch: $sha != $($manifest.sha256)"
    }
    return $manifest
}

function Get-AppOwnedBackendProcesses {
    param([Parameter(Mandatory = $true)][string]$InstallRoot)

    $resolvedRoot = Resolve-NormalizedPath $InstallRoot
    $processes = @()
    foreach ($process in Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'") {
        $command = [string]$process.CommandLine
        if (
            $command -and
            $command.IndexOf($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $command.IndexOf("runtime_server.py", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
        ) {
            $processes += $process
        }
    }
    return $processes
}

function Get-RuntimeIdentity {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 2
    )

    return Invoke-RestMethod `
        -Method Get `
        -Uri "http://127.0.0.1:$Port/runtime/identity" `
        -TimeoutSec $TimeoutSeconds
}

function Wait-RuntimeIdentity {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][string]$Version,
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [int]$TimeoutSeconds = 120
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $resolvedRoot = Resolve-NormalizedPath $InstallRoot
    $lastError = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        try {
            $identity = Get-RuntimeIdentity -Port $Port -TimeoutSeconds 2
            if (
                [string]$identity.version -ceq $Version -and
                (Resolve-NormalizedPath ([string]$identity.install_root)) -ieq $resolvedRoot -and
                [int]$identity.port -eq $Port -and
                [int]$identity.pid -gt 0 -and
                [string]$identity.instance_token
            ) {
                return $identity
            }
            $lastError = "Runtime identity did not match expected version/install root/port."
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Runtime identity was not confirmed within $TimeoutSeconds seconds. Last error: $lastError"
}

Export-ModuleMember -Function @(
    "Assert-CandidateArtifact",
    "Assert-GateChildPath",
    "Get-AppOwnedBackendProcesses",
    "Get-FileSha256",
    "Get-RuntimeIdentity",
    "Get-TreeFingerprint",
    "Get-TreeInventory",
    "Read-CandidateManifest",
    "Resolve-NormalizedPath",
    "Wait-RuntimeIdentity",
    "Write-AtomicJson"
)
