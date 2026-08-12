param(
    [string]$GuiTaskName = 'FedorinovRewards-Physical-GUI'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Get-ProcessOwner {
    param([Microsoft.Management.Infrastructure.CimInstance]$Process)

    $owner = Invoke-CimMethod -InputObject $Process -MethodName GetOwner
    if ($owner.ReturnValue -ne 0) {
        return $null
    }
    return "$($owner.Domain)\$($owner.User)"
}

$explorers = @(
    Get-CimInstance Win32_Process -Filter "Name='explorer.exe'" |
        ForEach-Object {
            [ordered]@{
                pid = $_.ProcessId
                session_id = $_.SessionId
                owner = Get-ProcessOwner $_
            }
        }
)
$dwms = @(Get-Process dwm -ErrorAction SilentlyContinue | Select-Object Id, SessionId)
$winlogons = @(Get-Process winlogon -ErrorAction SilentlyContinue | Select-Object Id, SessionId)
$services = @(Get-Service sshd, TermService | Select-Object Name, Status, StartType)
$task = Get-ScheduledTask -TaskName $GuiTaskName -ErrorAction SilentlyContinue

[ordered]@{
    checked_at = (Get-Date).ToString('o')
    host = $env:COMPUTERNAME
    sessions = (query session | Out-String).Trim()
    explorers = $explorers
    dwm_sessions = @($dwms | ForEach-Object SessionId | Sort-Object -Unique)
    winlogon_sessions = @($winlogons | ForEach-Object SessionId | Sort-Object -Unique)
    services = $services
    rdp_listener = [bool](Get-NetTCPConnection -LocalPort 3389 -State Listen -ErrorAction SilentlyContinue)
    gui_task = if ($task) {
        [ordered]@{
            name = $task.TaskName
            state = [string]$task.State
            user = $task.Principal.UserId
            logon_type = [string]$task.Principal.LogonType
            run_level = [string]$task.Principal.RunLevel
            action = "$($task.Actions.Execute) $($task.Actions.Arguments)"
        }
    } else { $null }
    interactive_ready = [bool]($explorers.Count -gt 0 -and $task)
} | ConvertTo-Json -Depth 7
