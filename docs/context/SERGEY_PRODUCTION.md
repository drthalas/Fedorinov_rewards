# ALE-528 / ALE-533: exact-artifact production pilot

Framework branch continues from `130d2d6`; product stays on its separate candidate line.
The new ACTIVE permits preparation only until an actual Owner production callback.
No product tests, Windows gate, backup/media scan or ZIP build are repeated here.

## Accepted artifact

- Issue/revision: ALE-533 r2.
- Accepted product: `62c4307c60d3078a97c23bfc1f73059c2f4aba65`.
- Package: `c6ff156f3c2212dd27ec416a15b82c56f4963db8`, version 2.0.33.
- ZIP: `FedorinovRewards_WebPreview_v2.0.33.zip`, 1,468,737 bytes.
- SHA256: `7312f48f8ed9cc0fd0cee8fcfcffaaae9fb96cbef27292fd29e3aada0b261a9e`.
- Physical updater PASS is reused from private evidence; no new Windows execution.
- Baseline production/main: `41f36c28fe98c19f364a1efa22e501b4df67edcd`, stable v2.0.32.

Preflight verifies actual remote refs/latest and absence of a conflicting version, local candidate tree,
source/package ancestry, only accepted copy + minimal version metadata delta, ZIP/manifest/gate SHA,
current Linear descriptions and the standard sender's two recipient identities/history.
Framework code never enters the product tree, ZIP or main.

## Approval and running service

`scripts/sergey_production.py prepare --config data/sergey-delivery/production.json` performs read-only
preparation. The protected descriptor binds issue/revision, product/package/tree, version/ZIP SHA/size,
public manifest SHA, physical PASS receipt SHA, current Linear scope hashes, expected main/latest,
and standard sender/recipient/journal identities. Credentials are resolved in memory from existing
protected configuration; token values are not copied to the descriptor/state/logs.

The existing intake and delivery LaunchAgents run the integration. The delivery service's existing
single process lock and one active pilot slot serialize execution; no general production queue is added.
Worker binding + fresh heartbeat are required before CLI `arm` can send the real button.

The Owner receives **«Опубликовать 2.0.33 Сергею»** with an explicit summary of a real public release,
main update, unchanged accepted ZIP, public manifest and standard messages to both people. Callback
`prod:yes:<token>` is private-chat/Owner allowlisted, bound to the actual sent message receipt, fingerprint
and a 24-hour waiting window. Old/foreign/repeated/deferred/expired callbacks do not start publication.
Pause/cancel controls remain effective. The callback only saves permission; the live service continues
without another chat prompt. Nobody presses this production button for Owner.

## Ordered durable publication

1. Persist the production run and actual callback before any production mutation.
2. Controlled main fast-forward with exact old-ref CAS (`--force-with-lease` after ancestry proof).
   Unexpected main or branch policy rejection blocks; no history rewrite or branch-policy bypass.
3. Create only the exact tag, then an owned **draft** release using the existing publisher helpers.
4. Upload the already accepted ZIP and production `latest.json`; no build and never `--clobber`.
   Existing assets are downloaded and compared before adoption; mismatches block.
5. Verify both draft assets again, then publish stable/latest. A release record and durable intent exist
   before this step can change public latest.
6. Download public latest and ZIP anonymously; require exact local manifest and ZIP byte/SHA parity.
7. Standard sender/generator and the existing production notification journal deliver primary Sergey
   and copy Owner with separate API message IDs. Only missing confirmed deliveries may be sent.
8. Close ALE-533 after release + both notifications; ALE-528 remains Needs Test.
   General queue stays disabled after this pilot, pending separate system acceptance.

Each mutation has a persisted intent and remote reconciliation. Ref updates/CAS, unique tag and
non-clobber uploads have bounded safe replay after negative reconciliation. Unknown draft creation
with no positive remote record blocks. Read-only transient failures retry for a bounded time.
Already applied remote effects are adopted after restart; no second release or notification is inferred
from a lost local checkpoint. A conflicting tag/archive/foreign draft is never overwritten.

The existing `logs/release_notifications.jsonl` in the canonical production workspace stays authoritative.
The framework extends its normal append function with fsync and per-recipient intent/sent/uncertain
records under a journal lock, while reusing `daily.send_message` and the standard message generator.
Known sent records are reused. If Telegram may have delivered but there is no positive journal receipt,
the worker reports a concrete blocker and never blindly resends. Bot API has no sent-message history
lookup. Owner receives a separate bot completion/blocker report, itself deduplicated by binding.
The completion report is recovered even if the process stopped after marking the release complete.

## Checks and evidence

Focused tests use TEMP SQLite/journals/repos and replaced APIs only. They cover interruptions after
merge/tag/draft/upload/manifest/publish/each notification, reopen and duplicate callback, missing completion
report, transient read retry/pause, matching versus conflicting assets, wrong tag/main, uncertain send,
positive journal reconciliation, real TEMP Git CAS against concurrent main, anonymous public parity,
and automatic delivery ticks after an intake callback with no manual runner invocation.
Final checks: **81 framework tests + 11 existing release-notification tests = 92 PASS**.
The existing release-notification tests are also retained. Product/full suite/VM/physical gates are not
rerun. Test SQLite ResourceWarnings remain an existing non-failure limitation.

Protected config/state/evidence live in ignored `data/sergey-delivery/production*`; test/browser artifacts,
real journal/configuration and credentials are not committed. CLI `status` shows approval state;
`/delivery_status` includes scoped production progress while the global queue/release flags stay false.
Publication execution wall time is persisted separately from implementation/preparation time and included
in the final bot report. Before Owner presses the button the STOP is READY FOR OWNER PRODUCTION APPROVAL.
After that the service's STOP is RELEASE PUBLISHED — OWNER/SERGEY NOTIFIED, or an exact blocker.

## Recovery complete — 08.11.2026

**RELEASE PUBLISHED — OWNER/SERGEY NOTIFIED**:
[v2.0.33](https://github.com/drthalas/Fedorinov_rewards/releases/tag/v2.0.33).
Remote main and v2.0.33 tag point to the same accepted package HEAD `c6ff156f3c2212dd27ec416a15b82c56f4963db8`.
The accepted ZIP is unchanged: SHA256 `7312f48f8ed9cc0fd0cee8fcfcffaaae9fb96cbef27292fd29e3aada0b261a9e`,
1,468,737 bytes. Anonymous latest/manifest/ZIP byte parity passed.
Standard journal confirms Sergey **sent / message_id 674**, Owner **sent / message_id 675**.
The bot's separate completion report is message **83**. ALE-533 is Done, ALE-528 remains Needs Test;
the general queue remains disabled.

The real production callback was update `915725227` on approval message `80`. The run stopped at
stage index 2, `record`, with `record_outcome_uncertain_no_retry`. This was **not Telegram uncertainty**.
Merge/tag already had positive receipts. The owned draft already existed, with no assets; public latest
was still 2.0.32 and there were no 2.0.33 notification journal rows.

The cause was the read-after-create probe: the implementation queried the published-release-by-tag
endpoint, which returned HTTP 404 for the draft. The create call had returned to the code, but no
positive record receipt was persisted because this lookup returned no result. Original raw CLI
stdout/stderr were not retained, so no unrecorded HTTP create status is claimed. The diagnosis was
reproduced read-only: tag lookup 404, while authenticated releases listing and release-by-id returned
the exact owned draft with its binding marker. This distinction is documented in the
[GitHub release API](https://docs.github.com/en/rest/releases/releases#list-releases).

Fix `6382207` uses authenticated paginated listing plus exact release-by-id lookup, rejects duplicate
records and retains the ownership marker check. Command diagnostics now retain only safe operation,
endpoint, exit/HTTP codes and timestamps: no raw output, token-bearing URLs or credentials.
One new focused TEMP regression reproduces the hidden draft and recovers a persisted record intent
without another create, merge, tag or notification. All **18 production tests PASS** for the corrective
iteration; product, package build and Windows gates were not rerun.

Owner's new recovery header is separately pinned; stripping that exact header must produce the old
approved scope hash. The original binding, artifact, callback and run start were preserved. While the
worker was blocked it was briefly unloaded for atomic receipt adoption, then restarted with the fix.
The existing `record` intent was retained as a confirmed reconciled receipt and the same run resumed
at stage 2. No execution or notification journal was reset.

The same draft was then used for exactly two uploads and one stable publish. Recovery command
diagnostics contain no new release create; merge/tag were not replayed. The service completed the
missing public parity, independent standard deliveries and Linear closure automatically.
Remaining execution after receipt adoption took **76.60 s**. The original run's **1857.04 s wall time**
includes the blocked interval and recovery wait; it is not active publication processing time.

Private evidence, ignored Git and mode 0600:
`data/sergey-delivery/production/recovery-before.json`, `recovery-complete-evidence.json`,
`command-diagnostics.jsonl`, plus the unchanged candidate and physical PASS receipts.
The bot/services and existing Windows runtime/Edge were preserved. No new Owner approval was requested.
