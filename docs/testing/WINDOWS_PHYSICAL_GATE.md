# Physical Windows gate

The physical Windows laptop is the production-like release acceptance surface.
It complements the fast UTM VM and must test the exact candidate bytes that
will be published.

## Access

- Primary unattended command channel: `ssh fedorinov-win-gate`.
- Headed channel: RDP with the dedicated test account and pinned host identity.
- Fallback: physical laptop console.

The Mac SSH alias uses a dedicated key. Passwords and private keys remain in
machine-local credential storage and must never be committed.

After a Mac orchestrator reboot, test both the SSH alias and its pinned trusted
LAN address. A sleeping or disconnected physical laptop is `UNAVAILABLE`, not
a PASS; retry when the network returns and require the same pinned host
identity before running a release gate.

Current required service state:

- `sshd`: `Running`, `Automatic`;
- `TermService`: `Running`, `Automatic`;
- on the dedicated physical gate only, `CcmExec` and `SccmLauncher`:
  `Stopped`, `Disabled`, under explicit Owner authorization;
- Windows Firewall enabled for every profile;
- TCP/22, TCP/3389, UDP/3389, and diagnostic ICMP echo allowed only from the
  trusted LAN on the active `Private` profile;
- previous broad SSH/RDP rules disabled;
- RDP Network Level Authentication enabled;
- AC standby, hybrid sleep, and hibernation disabled;
- AC lid-close action set to `Do nothing`;
- AC unattended sleep disabled;
- automatic screen saver and inactivity lock disabled for the gate accounts;
- display timeout may remain enabled;
- DC standby retained as a battery safety fallback;
- password protection remains in force after a manual lock.

The SCCM client remains installed. Do not disable any other SCCM component and
do not disable Kaspersky, BI.Zone, Windows Firewall, UAC, SSH, or RDP. If
`CcmExec` or `SccmLauncher` returns to `Running`/`Automatic`, or another SCCM
component starts enforcing the old power or screen-saver policy, stop the gate
and collect evidence. Removing the SCCM client requires new Owner approval.

The recorded drift source was Microsoft Configuration Manager, confirmed by
`CCM_PowerConfig`, `PwrMgmt.log`, and the SCCM user-logon package that restored
the screen saver. Local GPO, domain/Entra/MDM enrollment, scheduled tasks,
HP utilities, Kaspersky, and BI.Zone were audited and did not own these values.
Do not repeat broad policy changes when diagnosing a recurrence: first prove
which component changed the effective value and timestamp it against SCCM
policy activity.

The physical gate is unattended only while connected to AC power. Closing the
lid must not suspend it on AC. Do not disable the DC safety timeout merely to
extend unattended availability after mains power is lost.

The physical gate uses the dedicated plan `Fedorinov Physical Gate Always On`
with GUID `a1e34300-4c3a-4d18-8430-000000000001`. Its accepted AC settings are:

```powershell
$plan = 'a1e34300-4c3a-4d18-8430-000000000001'
$sleep = '238c9fa8-0aad-41ed-83f4-97be242c8f20'
$unattended = '7bc4a2f9-d8fc-4469-b07b-33eb785aaca0'
powercfg /setacvalueindex $plan sub_sleep standbyidle 0
powercfg /setacvalueindex $plan sub_sleep hibernateidle 0
powercfg /setacvalueindex $plan sub_sleep hybridsleep 0
powercfg /setacvalueindex $plan $sleep $unattended 0
powercfg /setacvalueindex $plan sub_buttons lidaction 0
powercfg /setactive $plan
powercfg /hibernate off
```

The machine-local corrective state and rollback are kept outside the
repository:

```text
C:\FedorinovGate\State\ale343-power-policy
```

The state directory contains the pre-change JSON snapshot, exported original
power plan, and rollback script. To restore the exact recorded service startup
types/states, screen-saver values, inactivity policy, original active plan,
and hibernation state, run from an elevated terminal:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  C:\FedorinovGate\State\ale343-power-policy\ROLLBACK.ps1
```

Rollback must report `ALE343_ROLLBACK_COMPLETE`. Verify the restored values
before allowing SCCM to manage the laptop again. Do not use rollback as a
reason to weaken firewall or endpoint protection.

The active physical adapter must report `WakeOnMagicPacket=Enabled` and
`WakeOnPattern=Enabled`. If the driver reports selective suspend or
sleep-on-disconnect as unsupported, record that as the effective protection;
do not edit undocumented device registry values.

Verify:

```bash
ssh -o BatchMode=yes fedorinov-win-gate \
  "powershell.exe -NoProfile -Command \"hostname; whoami; Get-Service sshd,TermService\""
nc -G 3 -zv <physical-gate-host> 3389
```

ICMP is diagnostic evidence only. Some trusted WLAN or endpoint policies may
drop echo even when the host rule is correct. SSH plus the RDP listener and
service identity remain the authoritative unattended-access gate; never widen
SSH/RDP firewall scope to compensate for missing ping replies.

## Release gate

1. Stabilize the feature and run Mac/Linux checks.
2. Run Windows-specific branch checks in the UTM VM.
3. Build one release-candidate artifact without publishing it.
4. Record filename, version, commit, size, and SHA256.
5. Transfer those exact bytes to the physical gate.
6. Run automated SSH checks and headed RDP checks against the same bytes.
7. Publish GitHub Release, `latest.json`, and Telegram only after PASS.

Never rebuild between physical acceptance and publication.

Required headed evidence includes:

- Explorer extraction and double-click launch;
- normal BAT behavior;
- browser UX;
- updater/recovery flow when applicable;
- one app-owned backend;
- DB/media fingerprints before and after;
- forced failure and rollback;
- repeated normal launch;
- access after sign-out and reboot.

## Reboot and idle checks

After a Windows reboot:

1. Wait for TCP/22 without opening an RDP session.
2. Verify key-based SSH, host identity, boot time, and automatic `sshd`.
3. Verify TCP/3389 and complete an RDP login.
4. Confirm the expected test account and clean application state.

For the idle gate, keep an authenticated RDP session open and leave the laptop
untouched for at least 90 minutes on AC. Do not poll the host during the idle
interval. Use a host-local `SYSTEM` collector to record the active power plan,
AC values, service state, session state, sleep events, lock events, and SCCM
power-log metadata. After the full interval, require:

- no sleep or hibernate event;
- no automatic lock event and the same RDP session still active;
- unchanged dedicated power plan and AC values;
- `CcmExec` and `SccmLauncher` still stopped and disabled;
- `sshd` and `TermService` still running and automatic;
- SSH authentication, RDP authentication, and ICMP response from the trusted
  LAN;
- no renewed SCCM power-log activity.

Also verify persistence after `gpupdate /force`, reboot, sign-out/sign-in, and
manual lock/unlock. Check across the former SCCM enforcement windows near
09:00 and 17:00 local time, or use a controlled SCCM policy trigger while both
authorized services are disabled. A blocked trigger plus unchanged plan and
unchanged `PwrMgmt.log` is acceptable evidence; it does not authorize deleting
or modifying the SCCM client.

For rollback after the laptop stops serving as a dedicated AC-powered gate,
use the recorded machine-local `ROLLBACK.ps1`; do not invent replacement
defaults. Do not roll back by disabling Windows Firewall or reenabling broad
`Any` SSH/RDP rules.

## Recovery access

1. Use the SSH alias first.
2. If SSH fails but RDP works, inspect only `sshd`, its listener, and its
   firewall rule.
3. If RDP fails but SSH works, inspect `TermService`, NLA, the listener, and the
   trusted-network firewall rule.
4. If both fail, use the local console. Do not remotely weaken UAC, security
   software, NLA, or authentication policy.

Do not broad-kill processes. Confirm product, PID, install root, port, token,
version, and HTTP identity before stopping an app-owned backend.

## Evidence and privacy

Commit generic scripts and documentation only. Keep these machine-local:

- credentials and private keys;
- candidate ZIPs and extracted installs;
- DB/media fixtures;
- logs, screenshots, RDP recordings, and host manifests.

Do not upload Owner or Sergey data to GitHub, Linear, CI artifacts, or external
cloud storage.

## Full performance fixture

The physical gate keeps one local NTFS `sergey-full` fixture:

```text
C:\FedorinovGate\Data\sergey-full\master
C:\FedorinovGate\Data\sergey-full\state
```

Use the exact candidate artifact with a DB-only writable run under
`state\runs\<run-id>`. The full media tree remains shared and read-only. Media
uploads, replacements, destructive entity tests, broad cleanup, and orphan
scans remain restricted to `synthetic-small`.

After initial materialization and verification, remove the Windows transport
archive and temporary extraction directory. Keep only one current packaged
baseline run when it is required for smoke; old candidate/rehearsal runs and
their browser profiles are stale artifacts. Before deleting any candidate,
confirm that it is inside the dedicated gate root, is not active, and is not
the only healthy fixture or current release-candidate evidence.

Reset means copying only the verified baseline SQLite file to the named run DB,
then checking its SHA, `integrity_check`, and foreign keys. It never means
recopying or mirroring the full media tree. See
[FULL_DATASET_FIXTURE.md](FULL_DATASET_FIXTURE.md).
