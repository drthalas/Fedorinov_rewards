# Windows physical release gate

The physical Windows laptop is the production-like acceptance contour. It does not replace fast branch-level checks in the Windows VM.

## Fixture selection

- Use `synthetic-small` for repeated lifecycle, failure, rollback, destructive, and media-write checks.
- Use `sergey-full` for one targeted exact-candidate heavy-data smoke and performance comparison.

The full fixture is persistent local private data. Follow `FULL_DATASET_FIXTURE.md`; never attach it or its private manifest to Linear, GitHub, CI, or release artifacts.

## Exact candidate gate

Before publication:

1. Identify the exact candidate ZIP and checksum.
2. Record the selected fixture profile.
3. Prepare a fresh DB-only run state.
4. Capture master and run fingerprints.
5. Launch through Explorer and the normal BAT.
6. Verify one backend, runtime identity, version, install root, browser UX, and ordinary/heavy navigation.
7. Open representative media without modifying it.
8. Perform metadata-only create/edit on the writable run DB when `sergey-full` is selected.
9. Shut down and relaunch normally.
10. Recheck master fingerprints and SQLite health.

The full-data result is a physical-laptop observation. It must not be presented as a measured result from Sergey's actual PC.

If the physical gate is unavailable, report the untested delta, reason, residual risk, and exact follow-up plan. Do not silently substitute VM evidence.
