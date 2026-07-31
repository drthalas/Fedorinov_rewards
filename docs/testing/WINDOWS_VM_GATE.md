# Windows VM gate

The UTM Windows VM is the fast branch-level Windows test surface. It is not a
substitute for physical release acceptance.

## Role

Use the VM for:

- Windows command and BAT parsing;
- updater and recovery simulations;
- repeated lifecycle loops;
- branch-level browser checks;
- deterministic TEMP DB/media fixtures.

Use the physical gate for the exact release-candidate artifact before
publication.

## VM lifecycle

The project VM uses UTM shared networking and a local disk image. The VM is not
marked suspended. Although UTM is configured to keep running after its last
window closes, the current audit observed the VM stop when the console window
was closed. Keep the console open or minimized during normal use. The
identity-scoped Mac watchdog checks the exact VM every 60 seconds and restored
it to `started` in 26 seconds during the post-reboot controlled test. Key-based
SSH returned after 36 seconds. This is recovery through a guest restart, not
continuous execution.

Guest AC sleep is disabled:

```powershell
powercfg /change standby-timeout-ac 0
powercfg /q SCHEME_CURRENT SUB_SLEEP STANDBYIDLE
```

The expected AC setting index is `0x00000000`. Display blanking may remain
enabled because it does not suspend the guest.

The Mac LaunchAgent responsible for starting the VM after login is documented
in [MAC_MINI_TEST_ORCHESTRATOR.md](MAC_MINI_TEST_ORCHESTRATOR.md).

## Headless access

The guest is Windows Home, so it cannot act as a supported Microsoft RDP host.
The intended unattended command channel is Windows OpenSSH Server using a
dedicated key from the Mac mini.

Required state:

- `OpenSSH.Server~~~~0.0.1.0` installed as a Windows Optional Feature;
- `sshd` installed, `Running`, and `Automatic`;
- `OpenSSH-Server-In-TCP` disabled;
- `FedorinovVM-SSHD-MacOnly` enabled for TCP/22, Public profile, with remote
  address limited to the UTM host gateway;
- a dedicated public key in the target test account;
- password authentication retained only as an Owner-managed fallback;
- no password or private key in the repository;
- SMB and WinRM disabled unless a later task provides a specific need and
  authorization.

Verify from Windows:

```powershell
Get-Service sshd
Get-NetTCPConnection -State Listen -LocalPort 22
Get-NetFirewallRule -Name "FedorinovVM-SSHD-MacOnly" |
  Get-NetFirewallAddressFilter
Get-NetConnectionProfile
```

Verify from the Mac:

```bash
ssh -o BatchMode=yes fedorinov-win-vm \
  'powershell.exe -NoProfile -Command "Write-Output $env:COMPUTERNAME; whoami; exit 0"'
```

Use a stable SSH alias rather than a raw NAT address. UTM shared-network
addresses can change after a reboot.

### OpenSSH installation and rollback

Install `OpenSSH.Server~~~~0.0.1.0` only as the Windows Optional Feature. The
current VM's Windows Update SLS request failed with `0x80072efd`, so the
accepted fallback used the matching Windows 11 ARM64 Features on Demand CAB
from `delivery.mp.microsoft.com`. Its canonical package metadata came from the
existing Windows ARM64 install media:

```text
OpenSSH-Server-Package~31bf3856ad364e35~arm64~~.cab
SHA256 c4896f71c9a7793b0ac4bcf7876fa98097b3285d15a1560d5f4b2064ed50a4d1
```

The CAB must report `Valid` from `Get-AuthenticodeSignature`. Install it from
an elevated PowerShell:

```powershell
Get-FileHash C:\FoD\OpenSSH-Server-Package~31bf3856ad364e35~arm64~~.cab `
  -Algorithm SHA256
Get-AuthenticodeSignature `
  C:\FoD\OpenSSH-Server-Package~31bf3856ad364e35~arm64~~.cab
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 `
  -Source C:\FoD -LimitAccess
Set-Service sshd -StartupType Automatic
Start-Service sshd
```

The dedicated inbound rule must permit TCP/22 only from the UTM host gateway
(`192.168.64.1` on the current shared network). Disable the broad
`OpenSSH-Server-In-TCP` rule if the feature creates it. Keep password
authentication only as an Owner-managed fallback; the normal channel is the
dedicated Mac key.

Configure the current Public VM network from elevated PowerShell:

```powershell
New-NetFirewallRule `
  -Name FedorinovVM-SSHD-MacOnly `
  -DisplayName FedorinovVM-SSHD-MacOnly `
  -Enabled True `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 22 `
  -RemoteAddress 192.168.64.1 `
  -Action Allow `
  -Profile Public
Disable-NetFirewallRule -Name OpenSSH-Server-In-TCP
```

The administrator public key is stored in:

```text
C:\ProgramData\ssh\administrators_authorized_keys
```

Its ACL must contain only Local System (`S-1-5-18`) and Builtin
Administrators (`S-1-5-32-544`) with full control and inheritance removed.
The Mac private key remains machine-local. The pinned VM host key is stored in
a dedicated known-hosts file and is not accepted with
`StrictHostKeyChecking=no`.

```powershell
icacls.exe C:\ProgramData\ssh\administrators_authorized_keys `
  /inheritance:r `
  /grant *S-1-5-18:F `
  /grant *S-1-5-32-544:F
Restart-Service sshd
```

Rollback from an elevated PowerShell:

```powershell
Disable-NetFirewallRule -Name "FedorinovVM-SSHD-MacOnly"
Stop-Service sshd
Set-Service sshd -StartupType Disabled
Remove-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
```

Remove only the dedicated VM public-key entry and Mac SSH alias. Do not remove
unrelated keys or change the physical Windows gate.

## Reboot gate

A VM reboot gate is PASS only when all of these succeed after the same reboot:

1. UTM reports the same VM identity in `started` state.
2. Windows completes startup without an active UTM window.
3. `sshd` starts automatically.
4. Key-based SSH succeeds from the Mac.
5. The expected hostname, user, OS build, and VM network identity match.
6. A TEMP application runtime can start and return strict runtime identity.

Console visibility alone is not headless access evidence.

The full Mac reboot gate passed with the same VM UUID, automatic Windows boot,
`sshd` in `Running/Automatic`, and key-based SSH before any manual Mac login.
The subsequent 30-minute idle gate preserved the Mac and VM boot identities.

## Idle gate

Record the VM boot time and SSH service PID, wait 30-60 minutes with the UTM
window minimized, then repeat the SSH identity check. Any guest sleep, paused
VM, lost listener, or changed identity is a failure.

## Baseline and reset

Keep two reset levels distinct:

1. Application reset removes only the named TEMP DB/media/runtime roots created
   for the current test. It must verify every target path before deletion and
   must not touch persistent fixtures, project source, or Windows configuration.
2. VM reset restores a known UTM snapshot only after a clean Windows shutdown.
   Create or refresh that snapshot only when SSH, firewall scope, guest sleep,
   boot identity, and a smoke runtime have passed.

Never copy or replace the live QCOW2 disk. Before restoring an OS-level
baseline, record the VM UUID, snapshot name, Windows build, SSH host-key
fingerprint, and current project checkout. After restore, repeat the reboot gate
and confirm that the dedicated host key still matches.

If no verified snapshot exists, stop and repair the current VM through SSH or
the UTM console. Do not improvise a destructive reset.

## Full performance fixture

The persistent `sergey-full` fixture uses the normalized layout documented in
[FULL_DATASET_FIXTURE.md](FULL_DATASET_FIXTURE.md). On the VM it has exactly
one local NTFS media tree:

```text
C:\FedorinovGate\Data\sergey-full\master
C:\FedorinovGate\Data\sergey-full\state
```

The application reads media from `master` and uses only a DB copy under
`state\runs\<run-id>`. Do not create a second full media tree for a run. Before
and after a relevant performance comparison, verify the master fingerprint,
SQLite integrity, foreign keys, and the selected run DB baseline SHA.

Transport ZIPs, temporary extraction directories, generated logs, and stale
runs are not persistent fixture components. Delete them only after the master
and baseline DB have passed verification and no process references the target.
Never delete `master` or the only healthy `state\baseline` copy.

## Safety

- Use only TEMP DB/media for write tests.
- Do not expose SSH outside the private test network.
- Do not enable unsupported RDP wrappers.
- Do not enable SMB or WinRM only to satisfy a checklist.
- Do not broad-kill Windows or application processes.
- Keep private keys and host-specific evidence outside Git.
