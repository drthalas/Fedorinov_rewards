[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Inspect", "ProtectMaster", "PrepareRun", "ResetDryRun")]
    [string]$Action,

    [Parameter(Mandatory = $true)]
    [string]$MasterRoot,

    [string]$StateRoot,
    [string]$RunId = "owner-qa",
    [string]$Python = "python",
    [string]$ToolPath = "",
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

function Resolve-StrictPath([string]$PathValue) {
    return [System.IO.Path]::GetFullPath($PathValue)
}

function Assert-DedicatedRoots {
    $master = Resolve-StrictPath $MasterRoot
    if (-not (Test-Path -LiteralPath $master -PathType Container)) {
        throw "Master root does not exist."
    }
    $masterItem = Get-Item -LiteralPath $master
    if ($masterItem.Name -ne "master" -or $masterItem.Parent.Name -ne "sergey-full") {
        throw "Master root must be the dedicated sergey-full\\master directory."
    }
    if ($StateRoot) {
        $state = Resolve-StrictPath $StateRoot
        if ($state -eq $master -or $state.StartsWith($master + [System.IO.Path]::DirectorySeparatorChar)) {
            throw "State root must be outside the read-only master."
        }
        if ((Split-Path -Parent $state) -ne $masterItem.Parent.FullName) {
            throw "State root must be a sibling of the dedicated master directory."
        }
    }
}

Assert-DedicatedRoots

if (-not $ToolPath) {
    $ToolPath = Join-Path $PSScriptRoot "full_dataset_fixture.py"
}
if (-not (Test-Path -LiteralPath $ToolPath -PathType Leaf)) {
    throw "Fixture tool is missing."
}

switch ($Action) {
    "Inspect" {
        & $Python $ToolPath inventory --root $MasterRoot --sample-size 32
        if ($LASTEXITCODE -ne 0) {
            throw "Fixture inventory failed."
        }
    }
    "ProtectMaster" {
        if (-not $Apply) {
            [pscustomobject]@{
                Action = "ProtectMaster"
                Apply = $false
                Scope = "master-root-only"
                MasterRoot = $MasterRoot
            } | ConvertTo-Json
            break
        }
        $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls.exe $MasterRoot /inheritance:r | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to disable inherited master ACL entries."
        }
        & icacls.exe $MasterRoot /grant:r "${identity}:(OI)(CI)RX" "*S-1-5-18:(OI)(CI)F" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to set the read-only master ACL."
        }
        $children = Join-Path $MasterRoot "*"
        & icacls.exe $children /reset /T /C | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to propagate the read-only master ACL."
        }
        [pscustomobject]@{
            Action = "ProtectMaster"
            Apply = $true
            Scope = "master-root-only"
            Identity = $identity
        } | ConvertTo-Json
    }
    "PrepareRun" {
        if (-not $StateRoot) {
            throw "StateRoot is required for PrepareRun."
        }
        $arguments = @(
            $ToolPath,
            "prepare-run",
            "--master-root", $MasterRoot,
            "--state-root", $StateRoot,
            "--run-id", $RunId
        )
        if ($Apply) {
            $arguments += "--apply"
        }
        & $Python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Run preparation failed."
        }
    }
    "ResetDryRun" {
        if (-not $StateRoot) {
            throw "StateRoot is required for ResetDryRun."
        }
        & $Python $ToolPath prepare-run `
            --master-root $MasterRoot `
            --state-root $StateRoot `
            --run-id $RunId
        if ($LASTEXITCODE -ne 0) {
            throw "Reset dry-run failed."
        }
    }
}
