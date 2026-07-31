# Full dataset fixture

## Purpose

`sergey-full` is a persistent private performance and release-confidence
fixture. `synthetic-small` remains the default for routine functional,
destructive, and media-write tests.

The full fixture contains private data. Never commit, upload, attach, quote, or
publish its file names, records, comments, links, photographs, manifests, or
directory listing. GitHub, Linear, CI artifacts, screenshots, logs, and cloud
storage are not approved destinations.

## Canonical storage

Keep only these three durable copies:

1. Mac mini canonical archive:
   `<mac-home>/Desktop/Rewards_Polkovod.zip`
2. Windows VM local NTFS fixture:
   `C:\FedorinovGate\Data\sergey-full`
3. Physical Windows gate local NTFS fixture:
   `C:\FedorinovGate\Data\sergey-full`

The Mac mini does not retain an extracted full master after both Windows
fixtures pass full verification. The canonical ZIP is read-only and is the
only Mac-side full copy.

Each Windows fixture has this layout:

```text
sergey-full\
  master\                  protected DB and media snapshot
  state\
    baseline\              verified baseline SQLite copy
    runs\<run-id>\database\MyDatabase.sqlite
```

There is one full media tree per Windows machine. A run copies only SQLite and
references media from `master`; it must not clone, mirror, or hard-link a
second full media tree.

The accepted opaque snapshot identity is:

```text
archive SHA256: 67774757b4b0f70583d16796daf60e982a381ad0a59fd88dd8f18687599ffb3d
tree files: 59909
tree bytes: 59024478493
tree fingerprint: d8b9d2ff61bde5d74456592305a1b92d01ad2e9cd651b4ebdb0f2a1412c38144
database SHA256: 4d909db82abcd38fee0f862bd859d72e922a8ab0203ec2c6eb5dced6a33bfe2d
```

These values identify the accepted private snapshot; they do not disclose its
records or file names.

## Verification gate

Before using or cleaning a fixture, record outside the repository:

- archive or tree SHA/fingerprint;
- aggregate file count and bytes;
- master DB SHA;
- SQLite `integrity_check`;
- foreign-key violations;
- aggregate media count and bytes;
- a deterministic image decode sample;
- free space;
- active process references.

Compare opaque fingerprints and aggregate counts only. A mismatch is a hard
stop. Do not repair, synchronize, or delete automatically when a master differs
from the accepted fixture.

The canonical ZIP check must validate its expected SHA and central directory.
The Windows check must read the full tree after initial materialization, after
storage cleanup, and whenever corruption is suspected. Quick DB/media-count
checks are sufficient between unchanged read-only runs.

## Run and reset

For a writable metadata smoke:

1. verify the master and `state\baseline` DB;
2. select an ASCII run ID;
3. copy only `state\baseline\MyDatabase.sqlite` to
   `state\runs\<run-id>\database\MyDatabase.sqlite`;
4. make only the run DB writable;
5. verify run DB SHA, SQLite integrity, and foreign keys;
6. point `REWARDS_DATA_DIR` to `master`;
7. point `REWARDS_DB_PATH` to the run DB;
8. disable update checks.

Reset repeats steps 3-5. It does not delete media and does not use
`robocopy /MIR`, recursive synchronization, orphan cleanup, or a full-tree
copy. Use `synthetic-small` for upload, replacement, entity deletion, rollback,
and failure-safety tests.

## Cleanup

Allowed cleanup candidates are:

- the verified Mac extracted copy after both Windows masters pass;
- Windows transport ZIPs and temporary extraction directories;
- stale generated run directories, browser profiles, logs, and reports;
- duplicate full media trees proven identical to the surviving master.

Before deletion:

1. verify the canonical archive and both surviving masters;
2. verify baseline and run DB health;
3. confirm no active process references the candidate;
4. resolve the exact path and ensure it is inside an approved fixture/gate root;
5. prove the path is not the only healthy dataset or required candidate.

Delete exact paths only. Never run global orphan cleanup or broad recursive
cleanup. Afterward, record free-space change and repeat fingerprint, DB health,
media decode, reset-to-baseline, and public-package smoke where available.

## Contour policy

Use the VM for repeatable branch-level performance comparisons. Compare only
against prior measurements from the same VM and classify the result as
`improved`, `stable`, or `degraded`.

Use the physical gate for the exact release-candidate artifact before
publication. Keep physical observations separate from VM-relative metrics and
from assumptions about another user's computer.

The minimum privacy-safe baseline includes startup, main/list, ordinary card,
heavy card, guides, search, summary, one media request, and shutdown/relaunch.
Store raw timings and host manifests only in machine-local private control
storage.

## Recovery

If a Windows master is unhealthy, preserve it and stop. Restore only from the
canonical archive after verifying archive SHA, destination free space, and path
safety. Materialize locally on NTFS, verify the full extracted fingerprint,
protect the master, create a DB-only baseline, and delete only the temporary
transport archive.

If the Mac archive is unhealthy or missing, do not treat either Windows
working copy as disposable. Report the condition and obtain an Owner-approved
backup plan before changing storage.

## Normalization record

The 2026-07 normalization retained the canonical Mac archive and one verified
Windows master/state layout per contour. It removed:

- the Mac extracted full tree (about 55 GiB allocated);
- the physical-gate transport archive (58,231,736,639 bytes);
- five obsolete physical-gate rehearsal/run directories (289,386,753 bytes);
- obsolete VM runtime logs and generated local audit output.

Observed free space increased from about 87 GiB to 142 GiB on the Mac and from
about 66.1 GB to 124.6 GB on the physical gate. The VM cleanup reclaimed only
small generated output; its full master was already unique.

After cleanup, both Windows masters retained the accepted tree and DB
fingerprints, SQLite integrity was `ok`, foreign-key violations were zero,
64/64 sampled images decoded, and each writable run DB was reset to the
accepted baseline SHA. Physical power-loss recovery remains intentionally
untested without separate authorization.
