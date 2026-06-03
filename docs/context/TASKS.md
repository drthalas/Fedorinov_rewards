# Tasks

## Stage 2A

Status: accepted / done.

Scope:

- Minimal read-only web mirror pages.
- Repository layer using SQLite `mode=ro`.
- Safe media endpoint with fallback image behavior.
- Dashboard, persons, person detail, photos, rewards, marks, guides, search, and health pages.

QA result:

- Hermes QA accepted Stage 2A.
- All target pages returned HTTP 200.
- Broken images: 0.
- Real media displayed from the stable dev data root.

Bugfix status:

- Media resolver and template media URL generation fixed for POSIX and Windows-style photo paths.
- Media endpoint now handles HEAD checks and avoids hanging on unreadable local files.
- Minimal media resolver tests added.

Dev data stabilization:

- Desktop sample data can block on read in the current environment.
- Use `/Users/hermes/LocalData/FedorinovRewards/Rewards` as the stable non-Desktop dev data root for local QA.
- Keep the stable copy outside Git and keep `.env` uncommitted.

## Stage 2B

Status: done.

Scope:

- UX and readability polish for the read-only mirror.
- Keep Stage 2B read-only.
- Format boolean values, dates, prices, and empty fields in templates.
- Add basic pagination for `/persons` and `/marks`.
- Limit `/search` results to the first 25 records per group with counts.
- Make `/guides` easier to read with collapsible tree sections.

Next:

- Hermes QA Stage 2B.

Editing status:

- Blocked until backup, migration, and editing architecture is designed.

## Stage 2C

Status: done.

Scope:

- Windows portable preview package for owner QA.
- Double-click Windows launch scripts for `.bat` and PowerShell.
- Windows `.env` template with read-only defaults.
- Russian Windows preview runbook and owner checklist.
- Package builder and package safety checker.

Next:

- Owner Windows preview QA.

## Stage 3A

Status: done.

Scope:

- Backup script for the safe development data root.
- Backup validation script.
- Explicit `WRITE_MODE=false` default.
- Guarded SQLite write connection helper for future CRUD routes.
- Backup freshness helper for future write gates.
- Local audit log helper for future changes.
- UI mode indicator for read-only vs development write mode.
- Legacy feature gap map for full functional mirror planning.

Rule:

- All write stages require a fresh backup first.

## Stage 3B

Status: done.

Scope:

- Person CRUD foundation on the safe dev data root.
- Enforce `WRITE_MODE=true` and recent backup checks before any write route.
- Keep production/owner data protected until backup/restore validation is mature.
- Create, update, and delete person records from the web UI in development write mode.
- Block person delete while rewards still reference the person.

## Stage 3C

Status: done.

Scope:

- Reward CRUD foundation on the safe dev data root.
- Create, update, and delete rewards from the web UI in development write mode.
- Enforce `WRITE_MODE=true` and recent backup checks before reward writes.
- Delete only `rewards` rows and leave media folders/files untouched.
- Keep media upload/replacement deferred until Stage 3F.

## Stage 3D

Status: done.

Scope:

- Mark CRUD foundation on the safe dev data root.
- Create, update, and delete standalone marks from the web UI in development write mode.
- Enforce `WRITE_MODE=true` and recent backup checks before mark writes.
- Delete only `mark` rows and leave `SourceMark` folders/files untouched.
- Keep media upload/replacement deferred until Stage 3F.

## Stage 3E

Status: done.

Scope:

- Legacy desktop layout mirror as a separate `/legacy` route.
- Top legacy tabs for rewards, search, marks, summary, and about.
- Left person list plus selected person's reward table, links/comment block, booklet placeholder, and photo block.
- Marks tab with standalone mark list, selected mark card, photo block, and write-mode-gated CRUD links.
- Basic summary counts/sums.
- Existing standalone routes remain unchanged.

Next:

- Rebuild Windows preview package with `/legacy`.
- Owner QA for legacy-style desktop mirror.

Deferred:

- Guides CRUD.
- Photo upload/replace/delete.
- PDF/CSV export parity.
- Full legacy filters and svod matrix parity.

## Backlog / Future

- Implement DataSourceManager.
- Implement Settings -> Data Source screen.
- Implement local config storage for selected data directory.
- Add validation report for connected database and media folders.
- Implement Guides CRUD with backup/write-mode gates.
- Implement Photo upload/replace/delete.
- Implement PDF export parity.
- Improve pagination, protected-field display controls, media diagnostics UI, and test coverage.
