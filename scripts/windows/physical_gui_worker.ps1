$ErrorActionPreference = 'Stop'

$state = Join-Path $env:LOCALAPPDATA 'FedorinovGate\PhysicalGui'
$requestPath = Join-Path $state 'request.json'
$statusPath = Join-Path $state 'status.json'
$errorPath = Join-Path $state 'error.txt'
New-Item -ItemType Directory -Path $state -Force | Out-Null
Remove-Item -LiteralPath $errorPath -Force -ErrorAction SilentlyContinue

try {
    if (-not (Test-Path -LiteralPath $requestPath)) {
        throw "Missing GUI request: $requestPath"
    }

    $request = Get-Content -LiteralPath $requestPath -Raw | ConvertFrom-Json
    $url = [string]$request.url
    $cdpPort = [int]$request.cdp_port
    if ($url -notmatch '^http://127\.0\.0\.1:\d+(/|$)') {
        throw 'Only localhost HTTP URLs are allowed.'
    }
    if ($cdpPort -lt 1024 -or $cdpPort -gt 65535) {
        throw 'Invalid CDP port.'
    }

    $profile = Join-Path $state 'edge-profile'
    $edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
    if (-not (Test-Path -LiteralPath $edge)) {
        throw 'Microsoft Edge not found.'
    }

    $arguments = @(
        "--remote-debugging-port=$cdpPort",
        '--remote-debugging-address=127.0.0.1',
        '--remote-allow-origins=*',
        "--user-data-dir=`"$profile`"",
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-features=msEdgeFirstRunExperience,msStartupBoost',
        '--new-window',
        '--start-maximized',
        "`"$url`""
    )
    $process = Start-Process -FilePath $edge -ArgumentList $arguments -PassThru

    [ordered]@{
        state = 'started'
        pid = $process.Id
        session_id = $process.SessionId
        url = $url
        cdp_port = $cdpPort
        profile = $profile
        started_at = (Get-Date).ToString('o')
        user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
        interactive = [Environment]::UserInteractive
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statusPath -Encoding UTF8

    $process.WaitForExit()
    [ordered]@{
        state = 'exited'
        pid = $process.Id
        session_id = $process.SessionId
        exit_code = $process.ExitCode
        url = $url
        cdp_port = $cdpPort
        exited_at = (Get-Date).ToString('o')
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statusPath -Encoding UTF8
} catch {
    ($_ | Format-List * -Force | Out-String) |
        Set-Content -LiteralPath $errorPath -Encoding UTF8
    [ordered]@{
        state = 'failed'
        failed_at = (Get-Date).ToString('o')
        message = $_.Exception.Message
    } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    throw
}
