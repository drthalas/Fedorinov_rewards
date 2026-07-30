# Full dataset fixture

## Profiles

- `synthetic-small`: default for routine functional, destructive, media-write, and repeated checks.
- `sergey-full`: persistent private fixture for heavy performance comparison, read-heavy regression, and release confidence.

The full fixture is private test data. Never commit, upload, attach, archive into CI output, or quote its file names, person data, comments, links, or media structure.

## Storage model

Keep one immutable source archive and one read-only extracted master in the Mac-side private data vault. Each Windows contour may have one persistent local NTFS master:

```text
<private fixture root>/
  master/                 read-only DB/media snapshot
  state/
    baseline/             one small baseline SQLite copy
    runs/<run-id>/        writable SQLite copy for a test run
```

The application uses:

```text
REWARDS_DATA_DIR=<private fixture root>/master
REWARDS_DB_PATH=<private fixture root>/state/runs/<run-id>/database/MyDatabase.sqlite
READ_ONLY=false
WRITE_MODE=true
UPDATE_CHECK_ENABLED=false
```

This layout does not copy the media tree per run. Metadata-only create/edit smoke may use the run DB. Media upload, media replacement, entity deletion, and broad cleanup must use `synthetic-small`; they are not permitted against `sergey-full`.

Exact paths, private manifests, file lists, and fingerprints stay outside the repository. Committed and Linear evidence must contain aggregate counts and opaque root fingerprints only.

Canonical cross-platform fingerprints ignore only macOS `.DS_Store`, which is absent from the source archive. Windows metadata present in the archive remains part of the fixture fingerprint.

Counts and timings describe the accepted fixture snapshot only. They are not facts about the current contents or absolute performance of Sergey's working computer.

## Inventory and fingerprints

Create the private manifest outside the repository:

```bash
python scripts/full_dataset_fixture.py inventory \
  --root "<private extracted master>" \
  --private-manifest "<private control directory>/sergey-full.private-fixture.json" \
  --full-fingerprint \
  --sample-size 64
```

Quick verification checks DB SHA, SQLite integrity/FK health, and aggregate media counts/bytes:

```bash
python scripts/full_dataset_fixture.py verify \
  --private-manifest "<private control directory>/sergey-full.private-fixture.json"
```

Use `--full` before initial acceptance, after materialization, and after any suspicious run. It reads every file and may take several minutes.

## Run preparation and reset

Preview the exact database-only reset:

```bash
python scripts/full_dataset_fixture.py prepare-run \
  --master-root "<private master>" \
  --state-root "<private state root>" \
  --run-id "candidate-smoke"
```

Apply only after the preview confirms `copy_scope: database-only`:

```bash
python scripts/full_dataset_fixture.py prepare-run \
  --master-root "<private master>" \
  --state-root "<private state root>" \
  --run-id "candidate-smoke" \
  --apply
```

The command never deletes a media directory. It creates or replaces only the selected run DB from the verified read-only baseline DB, explicitly removes inherited immutable flags from that copy, and grants owner-write only to the run DB. Do not use broad `robocopy /MIR`, orphan cleanup, or recursive delete as a reset mechanism.

On Windows, `scripts/windows_full_dataset_fixture.ps1` provides the same inspect, reset-preview, run preparation, and master ACL operations. Run `ProtectMaster -Apply` only after the materialized copy and its private manifest have passed verification. The ACL gives the gate identity read/execute access and SYSTEM full access; the owner can restore the ACL deliberately, but the normal application process cannot write the master.

## Contour policy

### Windows VM

Use local NTFS storage for regular branch-level comparisons:

- cold and warm startup;
- main/list load;
- search/filter;
- ordinary and heavy card open;
- media open;
- shutdown/relaunch.

Compare against the previous baseline from the same VM. Report `improved`, `stable`, or `degraded` with timings and environment notes. VM-relative metrics are not an absolute SLA for Sergey's computer.

### Physical Windows gate

Use the exact candidate artifact and the local persistent fixture for production-like release acceptance:

- Explorer extraction and normal BAT launch;
- browser-visible main/card/search/media smoke;
- single-backend lifecycle;
- candidate version/runtime identity;
- DB/media fingerprints before and after;
- shutdown and repeated normal launch.

Keep destructive and media-write acceptance on `synthetic-small`. A release must not be published merely because the VM baseline passed.

## Baseline record

For every relevant task or release, record:

- contour and hardware/runtime identity;
- package/commit;
- fixture fingerprint ID, never its paths or file list;
- cold start and HTTP-ready time;
- warm restart and HTTP-ready time;
- main/list, search/filter, card, and media-open timing;
- metadata-only create/edit smoke on a fresh run DB;
- shutdown/relaunch result;
- antivirus/indexer state when known;
- comparison with the previous baseline in the same contour.

Physical-gate observations and VM-relative timings must be separate from any statement about Sergey's actual computer.

With an already running local runtime, collect a sanitized HTTP baseline:

```bash
python scripts/full_dataset_baseline.py \
  --base-url "http://127.0.0.1:<port>" \
  --db "<private state root>/runs/<run-id>/database/MyDatabase.sqlite" \
  --label "<contour-and-candidate>"
```

The output contains only operation names, aggregate timings, response sizes, status codes, and the heavy-record reward count. Store raw output in the contour's private control directory, not in the repository.

## Space and transfer gate

Before the one-time materialization:

1. Verify archive SHA and central directory.
2. Require free space for the extracted master plus at least 10% working margin.
3. Measure transfer throughput with a non-sensitive temporary file.
4. Prefer transfer of one archive followed by local extraction over copying tens of thousands of files.
5. Remove only the verified temporary transfer archive after extraction; retain the immutable source archive.
6. Stop and propose an external SSD or larger VM disk when capacity or expected time is not acceptable.

After transferring the verified archive to a dedicated Windows `incoming` directory, preview local extraction without exposing its top-level private name:

```bash
python scripts/full_dataset_fixture.py extract \
  --archive "<private incoming archive>" \
  --destination "<private fixture root>/master" \
  --expected-sha256 "<recorded archive SHA256>" \
  --strip-single-root
```

Repeat with `--apply` only when checksum, path safety, and `space_ok` pass. Verify the materialized master before deleting only the temporary Windows transport archive.
