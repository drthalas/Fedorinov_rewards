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
- TCP/22 and TCP/3389 reachable only on the trusted test network;
- AC and battery standby disabled during a gate run.

Verify:

```bash
ssh -o BatchMode=yes fedorinov-win-gate \
  "powershell.exe -NoProfile -Command \"hostname; whoami; Get-Service sshd,TermService\""
nc -G 3 -zv <physical-gate-host> 3389
```

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

For the idle gate, leave the laptop untouched for 30-60 minutes and repeat both
SSH and RDP probes. A screen lock is acceptable; sleep or loss of both remote
channels is not.

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
