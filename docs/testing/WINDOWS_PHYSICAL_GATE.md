# Windows Physical Gate Runbook

## Назначение

Physical Windows host используется как production-like ручной Owner gate для exact release candidate. Это не основной dev-host и не замена Windows VM. Удалённые проверки выполняются с Mac mini без сохранения паролей, текущих DHCP-адресов или приватных host identity values в репозитории.

Каноническая команда:

```sh
ssh fedorinov-win-gate
```

Не подключаться к сохранённому IP из старого отчёта или prompt. Текущий IP считается временным runtime evidence.

## Схема доступа

Mac mini содержит machine-local SSH configuration:

- alias: `fedorinov-win-gate`;
- key: `~/.ssh/fedorinov_win_gate`;
- proxy helper: `~/.local/bin/fedorinov-win-gate-proxy`;
- discovery identity: `~/.config/fedorinov-win-gate/discovery.env` with mode `600`;
- last validated address: `~/.cache/fedorinov-win-gate/ip` with mode `600`;
- pinned ED25519 host key in `~/.ssh/known_hosts`.

The committed helper is [discover_physical_windows_gate.sh](../../scripts/testing/discover_physical_windows_gate.sh). Discovery order is:

1. validate the cached address against the pinned SSH host key;
2. if cache fails, resolve mDNS and inspect current ARP, then validate the key;
3. only then populate ARP and scan the Mac mini local `/24`, validating every
   candidate against the pin.

An address is never accepted by IP, hostname, MAC, or an open port alone. The ED25519 host key must match. The repository stores neither the expected key nor the adapter identity.

The helper preserves stdin before candidate loops because it is also the SSH
`ProxyCommand`: final `nc` must read the OpenSSH transport stream, not the
candidate file. Cache is checked before blocking mDNS/subnet discovery so the
relay stays inside `ConnectTimeout`. For the normal cached `ProxyCommand` path,
the helper opens no separate banner or `ssh-keyscan` sessions: the outer
OpenSSH process performs the pinned `StrictHostKeyChecking`/`HostKeyAlias`
verification on the relayed connection. Explicit `--preflight` and
`--discover` retain banner and key classification. This avoids pre-auth probe
amplification during repeated unattended checks.

Failure states are distinct: `SSH_READY`, `HOST_REACHABLE_SSHD_UNAVAILABLE`,
`SSH_BANNER_TIMEOUT`, `HOST_KEY_MISMATCH`, `HOST_NOT_FOUND` and
`LOCAL_LAN_UNAVAILABLE`. Never translate a single failed probe into `offline`;
until these layers are classified, status is `connectivity unresolved`.

The recurring ALE-382 incident had separate host and client causes:

- Windows entered real S3 on AC; Kernel-Power recorded `Button or Lid`. SSH and
  RDP were consequently unreachable until wake.
- The former fallback required an SSH host key before it could report any host
  and collapsed a reachable host with a missing/slow banner into `not found`.
- Candidate-loop stdin replaced the SSH `ProxyCommand` transport, while an
  mDNS pipeline subshell inherited cleanup and could delete the shared scan
  directory early.
- Normal cached connections also opened banner and `ssh-keyscan` probes before
  every real handshake. Repeated health checks amplified OpenSSH pre-auth
  traffic and caused intermittent banner delay without sleep or service drift.

These layers must remain independently observable. A banner timeout does not
prove sleep, and a healthy Windows service does not prove that the Mac relay is
correct.

Machine-local configuration shape:

```sh
GATE_HOST_KEY_ALIAS='<machine-local-known-hosts-alias>'
GATE_MAC_PATTERN='<machine-local-adapter-pattern>'
GATE_INTERFACE='en0'
GATE_MDNS_NAME='<machine-local-hostname>.local'
```

Do not add passwords, private keys, current IPs, or the real identity values to this file in Git.

## Availability Policy

On AC power the dedicated gate must retain:

- standby timeout `0` (`Never`);
- hibernate timeout `0`, hibernation disabled;
- hybrid sleep disabled;
- unattended sleep disabled;
- lid close action `Do nothing`;
- inactivity lock timeout `0`;
- screen saver disabled;
- active Wi-Fi adapter power-off disabled;
- `sshd` and `TermService` set to `Automatic` and `Running`;
- SSH, RDP, and ICMP firewall access restricted to the trusted private LAN.

The display may turn off. Display timeout is not a gate failure while the host remains awake and SSH/RDP are reachable.

The corporate SCCM power policy is the proven source of drift: its actual machine policy reapplies a 75-minute AC standby timeout and screen settings. Disabling `CcmExec` alone is not durable because the `Configuration Manager Health Evaluation` scheduled task restores its startup type and starts the service. With explicit Owner approval, that task is disabled, and `CcmExec` plus `SccmLauncher` are `Disabled/Stopped` on this dedicated test host. SCCM is not uninstalled. Do not disable another SCCM component or remove the SCCM client without separate Owner approval. Kaspersky, BI.Zone, Windows Firewall, UAC, domain/Entra state, SSH, and RDP must not be disabled.

ALE-382 added `FedorinovRewards-Physical-Access-Watchdog` after event evidence
showed recurring real S3 sleep on AC with reason `Button or Lid`. The SYSTEM task
runs at startup and every five minutes. Its repair allowlist is only six AC power
values (sleep, hibernate timeout, hybrid, unattended, lid and sleep button),
`sshd`/`TermService` `Automatic/Running`, and `sshd` restart recovery. It never
changes battery/DC, firewall, profile, router, UAC, endpoint protection or
corporate state. Running the task while DC-powered does not change any DC power
value; it keeps the two access services observable while all power writes still
target the inactive AC indexes only. Network/profile/corporate drift is
report-only. Startup waits
conditionally up to 60 seconds for IPv4 readiness, without a blind sleep.

The installer first writes a machine-local rollback snapshot under
`C:\ProgramData\FedorinovGate\PhysicalAccess`; never publish that snapshot.

Install only after explicit Owner authorization, from an elevated PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\windows\install_physical_access_watchdog.ps1
```

Before accepting the result, verify the snapshot exists, the task principal is
`SYSTEM`, both triggers exist, the last task result is `0`, and the six captured
DC values still match the snapshot. Do not infer or normalize battery values.

## Verification

Connection and identity:

```sh
ssh -o BatchMode=yes fedorinov-win-gate hostname
~/.local/bin/fedorinov-win-gate-proxy --discover 22
```

Windows service and power checks run through the alias:

```powershell
Get-Service CcmExec,SccmLauncher,sshd,TermService
powercfg /getactivescheme
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
powercfg /query SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE
powercfg /query SCHEME_CURRENT SUB_SLEEP HYBRIDSLEEP
powercfg /query SCHEME_CURRENT SUB_BUTTONS LIDACTION
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' InactivityTimeoutSecs
Get-ItemProperty 'HKCU:\Control Panel\Desktop' ScreenSaveActive,ScreenSaverIsSecure
```

After a reboot, connect through the alias before any interactive login. Record boot time, current IP as evidence only, `quser`, service states, and effective power settings. A gate is not PASS merely because desired registry values exist before reboot.

Required proof after access changes: two full reboot cycles with SSH before
interactive login; first boot-trigger result `0`; authorized RDP plus
Explorer/DWM/visible Edge; disconnect/reconnect; controlled adapter reconnect;
and idle beyond the historical failure interval followed by discovery, event,
task-history and effective-setting checks.

During repeated checks, normal `ssh fedorinov-win-gate` uses the cached relay
and the outer OpenSSH host-key pin. Use `--preflight` for explicit banner/key/RDP
classification; do not call it multiple times inside one logical check. A
healthy repeated gate should not create several unauthenticated SSH sessions
per command.

For an idle gate, disconnect all remote sessions, wait beyond the former enforcement interval and across the next SCCM health-evaluation trigger, then prove:

- uptime advanced without Kernel-Power sleep/wake events;
- no automatic lock event occurred;
- SSH, TCP/3389 protocol negotiation, and ICMP are reachable;
- power, service, and NIC values did not drift.

An interval that ends before the next health-evaluation task run is not sufficient evidence, even when it exceeds 75 minutes.

## Controlled Address-Change Gate

Use this gate only with explicit Owner approval. Confirm that the candidate has no ICMP response, ARP owner, or expected service ports before assigning it. Windows must retain DHCP and the primary address throughout.

```text
netsh interface ipv4 set interface interface=<index> dhcpstaticipcoexistence=enabled store=active
netsh interface ipv4 add address name=<index> address=<temporary-address>/24 store=active skipassource=true
```

Wait until `Get-NetIPAddress` reports `AddressState=Preferred`. Put the alternate endpoint only in the machine-local discovery cache, connect with `ssh fedorinov-win-gate`, and confirm the server endpoint through `SSH_CONNECTION`.

Cleanup runs through the primary DHCP endpoint:

```text
netsh interface ipv4 delete address name=<index> address=<temporary-address> store=active
netsh interface ipv4 set interface interface=<index> dhcpstaticipcoexistence=disabled store=active
```

After cleanup, intentionally leave the removed endpoint in cache once. The canonical alias must reject it by connection failure, rediscover the current DHCP endpoint, validate the pinned host key, and rewrite the cache. Confirm DHCP remains enabled, only the primary address remains, and the default gateway is unchanged.

## Recovery

If the alias fails:

1. Run `~/.local/bin/fedorinov-win-gate-proxy --discover 22`.
2. Verify the Mac mini is on the trusted LAN.
3. Check that the pinned host key still exists; never accept a changed key automatically.
4. Inspect mDNS, ARP, then the limited local `/24`; do not scan the internet.
5. Ask Owner before changing router DHCP settings, host addressing, corporate protection, or using physical access.

Restore the previous SCCM enforcement state in elevated PowerShell:

```powershell
Enable-ScheduledTask `
    -TaskPath '\Microsoft\Configuration Manager\' `
    -TaskName 'Configuration Manager Health Evaluation'
Set-Service CcmExec -StartupType Automatic
Start-Service CcmExec
Set-Service SccmLauncher -StartupType Disabled
Stop-Service SccmLauncher -Force -ErrorAction SilentlyContinue
```

Restore the pre-change user/session and AC values when rolling back the dedicated always-on policy:

```powershell
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 4500
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP HYBRIDSLEEP 0
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
Set-ItemProperty 'HKCU:\Control Panel\Desktop' ScreenSaveActive '1'
Set-ItemProperty 'HKCU:\Control Panel\Desktop' ScreenSaverIsSecure '0'
Set-ItemProperty 'HKCU:\Control Panel\Desktop' ScreenSaveTimeOut '600'
```

Re-enable `Allow the computer to turn off this device` only through the active adapter's exact `MSPower_DeviceEnable` record, then reboot and verify connectivity. Do not use broad process, adapter, firewall, or security changes as recovery shortcuts.

Rollback only the ALE-382 watchdog with its captured values:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\ProgramData\FedorinovGate\PhysicalAccess\rollback_physical_access_watchdog.ps1
```

This unregisters only the task-owned watchdog and restores captured AC values,
original service start/running states and original `sshd` recovery registry
bytes. It does not infer defaults or touch DC/network/security policy.
