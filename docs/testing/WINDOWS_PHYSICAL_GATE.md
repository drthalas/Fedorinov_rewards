# Fedorinov Rewards Physical Windows Gate

The physical host is a pre-publication release acceptance gate. It complements,
but does not replace, branch tests and the fast Windows VM checks.

## Order of work

1. Stabilize the feature branch and run its required tests.
2. Validate Windows-specific behavior on the fast VM when relevant.
3. Produce one release-candidate ZIP without publishing it.
4. Record its filename, version, commit SHA, exact size, SHA256, and source.
5. Import those exact bytes into the physical gate.
6. Run automated SSH checks and headed RDP checks against the same bytes.
7. Publish only after the physical gate passes.

Never rebuild between physical acceptance and publication.

## Layout

`C:\FedorinovGate` contains:

- `Control`: repository scripts and verified control prerequisites.
- `Intake`: immutable candidate bytes plus `candidate.json`.
- `Baselines\CLEAN_WINDOWS_BASELINE`: audited host metadata.
- `Baselines\PREVIOUS_PUBLIC_VERSION_BASELINE`: extracted previous public
  package and immutable synthetic data master.
- `Runs`: one writable product/data copy per gate run.
- `Evidence`: machine-readable run results and logs.
- `Scenarios` and `Paths`: one/multiple/invalid/stale/clean installation and
  space/Cyrillic path fixtures.

Desktop and Downloads have dedicated `Fedorinov Gate` directories. No private
Owner or Sergey data belongs anywhere under this root.

## One-time initialization

Run from an elevated PowerShell only for host preparation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\FedorinovGate\Control\Initialize-WindowsPhysicalGate.ps1
```

This creates folders and captures a non-secret host profile. It does not disable
security software, modify user data, or install a product release.

## Exact candidate intake

Transfer the already built candidate ZIP, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\FedorinovGate\Control\Import-ReleaseCandidate.ps1 `
  -ArchivePath C:\FedorinovGate\Transfer\FedorinovRewards_WebPreview_vX.Y.Z.zip `
  -Version X.Y.Z `
  -CommitSha 0123456789abcdef0123456789abcdef01234567 `
  -ExpectedSize 1234567 `
  -ExpectedSha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef `
  -Source "pre-publication release workflow"
```

The script rejects mismatched names, versions, sizes, hashes, and commit SHAs,
then re-hashes the copied bytes. `candidate.json` is the acceptance identity.

## Baseline

Create a baseline from an exact previous public ZIP and a synthetic data root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\FedorinovGate\Control\New-WindowsGateBaseline.ps1 `
  -PreviousPublicArchive C:\FedorinovGate\Transfer\previous.zip `
  -PreviousVersion X.Y.Z `
  -ExpectedArchiveSize 1234567 `
  -ExpectedArchiveSha256 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef `
  -SyntheticDataPath C:\FedorinovGate\Transfer\SyntheticRewards
```

The baseline records install and data tree fingerprints. The master data files
are marked read-only. Every run copies the master into a unique writable folder.
No gate run writes to the master.

## Reset

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\FedorinovGate\Control\Reset-WindowsPhysicalGate.ps1 `
  -PreviousVersion X.Y.Z `
  -RunId rc-X.Y.Z-01 `
  -AppPort 18090
```

Reset verifies both baseline fingerprints before copying. Existing run folders
are never replaced by default. `-ReplaceExisting` is allowed only when no
app-owned backend is running from that exact run. The script never scans or
kills unrelated processes.

Start or stop a prepared run with strict identity checks:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\FedorinovGate\Control\Start-WindowsGateRun.ps1 `
  -RunRoot C:\FedorinovGate\Runs\rc-X.Y.Z-01 `
  -ExpectedVersion X.Y.Z `
  -AppPort 18090

powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\FedorinovGate\Control\Stop-WindowsGateRun.ps1 `
  -RunRoot C:\FedorinovGate\Runs\rc-X.Y.Z-01 `
  -AppPort 18090
```

Stop requires matching HTTP install-root and PID identity before terminating
that exact backend.

Windows OpenSSH closes processes tied to a completed remote job. For an
SSH-driven smoke, pass `-Hold` and keep that SSH command active for the duration
of the checks. A persistent headed runtime must be launched from the RDP/console
session with the normal BAT; a detached SSH child is not accepted as evidence.

## Automated SSH gate

`Invoke-WindowsPhysicalGate.ps1` restores a unique run, verifies the exact
candidate, serves only its local manifest/ZIP, starts the previous public build
through `start_windows.bat`, and checks strict runtime identity.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File C:\FedorinovGate\Control\Invoke-WindowsPhysicalGate.ps1 `
  -CandidateManifest C:\FedorinovGate\Intake\X.Y.Z\candidate.json `
  -PreviousVersion X.Y.Z `
  -RunId rc-X.Y.Z-01 `
  -AppPort 18090 `
  -FeedPort 18089 `
  -ApplyUpdate
```

Required automated evidence:

- exact candidate filename, size, SHA256, commit, and source;
- previous and final runtime identity;
- exactly one app-owned backend before and after update;
- backup, staging, update, restart, and repeated-launch state;
- DB/media tree fingerprint before and after program update;
- no stale app-owned backend;
- forced-failure rollback for the same candidate;
- five consecutive happy-path passes for updater releases.

Do not use `Stop-Process -Name python`, `taskkill /IM`, port-wide kills, or any
other broad process termination.

## Headed RDP gate

Use RDP after automated checks and test the same accepted bytes:

```bash
scripts/windows-gate/Open-WindowsGateRdp.sh
```

The Mac launcher uses the stable mDNS hostname, retrieves the dedicated test
credential from the login Keychain, sends it to FreeRDP through standard input,
and pins the audited RDP certificate. It never places the password in the
repository or process command line. An already active different Windows console
user can cause Windows to require an interactive takeover confirmation; sign
out that test-only console session before starting unattended RDP.

1. Extract the candidate under Desktop and double-click its normal BAT.
2. Repeat under Downloads, a path with spaces, and a Cyrillic path.
3. Confirm visible command-window behavior and browser launch.
4. Exercise update/recovery confirmation and cancellation.
5. Exercise folder picker with one installation, multiple installations,
   invalid target, and cancellation.
6. Confirm SmartScreen, Kaspersky, UAC, and Windows notifications are not hidden
   or bypassed.
7. Confirm the version and runtime identity in the opened product.
8. Close and launch again with the normal BAT; exactly one backend must remain.
9. Sign out and reconnect, then repeat a normal BAT launch.
10. Reboot and verify both SSH and RDP access before the final BAT launch.

Headed checks are release-specific evidence. Source inspection, mocks, SSH-only
process starts, and direct HTTP calls do not replace them.

## Recovery access

1. Primary: `ssh fedorinov-win-gate` using the dedicated key.
2. Fallback: run `scripts/windows-gate/Open-WindowsGateRdp.sh`. NLA, the pinned
   RDP certificate, and the dedicated credential from the Mac mini login
   Keychain remain required.
3. If SSH fails but RDP works, verify `sshd` is Running/Automatic and the
   administrator authorized-key ACL before restarting only `sshd`.
4. If RDP fails but SSH works, verify `TermService`, NLA, the listener, and the
   Kaspersky-managed network policy.
5. If both fail, use the laptop console. Do not weaken UAC, Kaspersky, NLA, or
   authentication policy remotely.

## Evidence retention

Commit scripts and generic documentation only. Keep these machine-local:

- passwords and private keys;
- downloaded release ZIPs and extracted installs;
- synthetic DB/media;
- logs, screenshots, browser output, and RDP recordings;
- host-specific candidate manifests and run evidence.

Each Linear release issue should include exact artifact identity, run IDs,
automated results, headed results, residual gaps, and whether the physical gate
is a release blocker.
