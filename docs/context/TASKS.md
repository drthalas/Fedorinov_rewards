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

- Send rebuilt Windows preview package to owner.
- Owner Windows preview QA.

QA:

- Stage 3E QA passed.
- `HEAD /legacy` fixed.
- Windows ZIP with `/legacy` rebuilt.
- Windows media endpoint bugfix applied for owner preview.
- Windows ZIP rebuilt with media fix.

Deferred:

- Guides CRUD.
- PDF/CSV export parity.
- Full legacy filters and svod matrix parity.

## Stage 3F

Status: done.

Scope:

- Clickable photos and large photo viewer for standalone and `/legacy` pages.
- Person photo gallery slideshow with previous/next navigation.
- Legacy rewards tab photo block now shows person photo, main photo, and rewards photo.
- Human-readable photo labels replace technical photo path labels.
- Development write-mode photo upload/replace and clear/unlink controls for person, reward, and mark edit forms.
- Photo writes require `WRITE_MODE=true` and the existing backup-first guard.
- Physical media files are not deleted when photo fields are cleared.

Next:

- Hermes / owner QA for Stage 3F photo workflow.
- Rebuild Windows preview package after QA if needed.

Deferred:

- Full browser clipboard paste implementation.
- Physical media deletion workflow.
- Guides CRUD.
- PDF/CSV export parity.

## Stage 3G

Status: done.

Scope:

- Reworked `/search` and `/legacy?tab=search` to use one shared search repository.
- Fixed case-insensitive Cyrillic partial search with Python Unicode normalization.
- Added legacy-like filters: search category, condition, value, search button, and reset button.
- Added `scope=all/persons/rewards/marks` and `mode=contains/starts/exact`.
- Added grouped counts and first-25 result limits per group.
- Added read-only `/search.csv` export for current search results.

Next:

- Hermes / owner QA for search behavior.
- Guides CRUD or remaining legacy UI parity items.

## Legacy UI Primary Interface

Status: done.

Scope:

- `/` redirects to `/legacy?tab=rewards`.
- Legacy UI is the primary user workflow; standalone pages remain as supporting/technical pages.
- Top navigation no longer presents Legacy UI as a separate mode.
- Forms opened from `/legacy` carry safe `return_to` values and redirect back to the legacy tab/selected record after save/delete.
- Windows preview defaults to editable working preview mode with backup-first guard enabled.

Next:

- QA navigation/back flow from legacy tabs through person/reward/mark forms.

## Legacy UI Shell And Photo Modal

Status: done.

Scope:

- `/legacy` now uses a dedicated legacy shell without the global web navigation.
- Legacy tabs are the only top-level navigation inside the main working interface.
- The legacy workspace fills the page instead of appearing as a nested card inside the web preview layout.
- Photo clicks now open an inline modal/lightbox over the current page.
- The existing `/photo/view` route remains only as a fallback/technical route.

Next:

- QA legacy shell and photo modal behavior.

## Daily Telegram Reports

Status: done.

Scope:

- Daily Russian progress report generator for the project name "Награды и награждённые".
- Telegram sender uses the existing colorizer/SAVBot token from `picture-colorizer`.
- Primary recipient is Sergey; copy recipient is Alexander.
- Dry-run mode prints the safe report text and masked recipient ids without sending messages.
- Launchd template schedules the report every day at 09:00.
- Real tokens, chat ids, and send logs stay outside Git.

Next:

- Confirm the first real send policy before enabling daily primary sends.
- Optional one-time test send to Alexander only after explicit confirmation.

## Stage 3H

Status: done/current.

Scope:

- Guide CRUD for ranks/specialties in `guide`.
- Guide CRUD for the award/mark tree levels `guide_lev_0` through `guide_lev_4`.
- Write-mode and backup-first guard before every guide write.
- Delete protections for rank values used by person cards.
- Delete protections for tree nodes with children or references from rewards/marks.
- Supporting `/guides` page now provides legacy-style add/edit/delete actions in write mode.
- Person, reward, and mark forms link back to the relevant guide page with safe return navigation.

Next:

- Hermes QA for guide editing and protected delete behavior.
- Decide next parity stage: biography/form field parity, PDF export, or remaining summary table parity.

## Stage 3I

Status: done/current.

Scope:

- Person, reward, and mark edit forms are closer to the old Windows dialog structure.
- Person form now has blocks for main data, links, short biography, comments, and photos.
- Reward and mark forms now group guide fields, purchase fields, and photo controls.
- `link1` and `link2` are shown as owner-facing labels for "Память народа" and "Форум коллекционеров".
- Person `biography` is a separate SQLite column added through an idempotent guarded migration.
- Person detail and legacy rewards tab display the short biography.
- Photo controls remain the existing write-mode `+`, `×`, and disabled clipboard-paste placeholder.

Next:

- Hermes QA for form readability and biography workflow.
- Decide next parity stage: PDF export, summary table parity, or remaining legacy form details.

## Stage 3J

Status: done.

Scope:

- Legacy summary tab now has guide-level filters for country, category, subcategory, name, and extra/link level.
- Summary tab can include standalone marks when `include_marks=true`.
- Added compact green matrix-style summary rows with totals, stock counts, purchase/current prices, and last purchase date.
- Added read-only `/summary.csv` export using the same filters and UTF-8 BOM for Excel compatibility.
- PDF export remains a disabled placeholder for a later dedicated PDF stage.

Next:

- Hermes QA for summary filters and CSV export.
- Next parity candidate: PDF export for summary/person booklet.

## Stage 4A

Status: done.

Scope:

- Added a single application version source.
- Added `/version` for current app name/version.
- Added `/updates/check` to check a public GitHub Release manifest.
- Added update status UI to `/legacy?tab=about`.
- Added example `latest.json` manifest and Stage 4B update plan.
- Kept update checking token-free and read-only: no ZIP download, no installation, no owner data access.

Next:

- Publish the first GitHub Release with Windows portable ZIP and `latest.json`.
- Stage 4B: one-click updater with download, SHA256 validation, application backup, `.env` preservation, replacement, restart, and rollback.

## Stage 4A.1

Status: done.

Scope:

- Added release package builder for versioned Windows ZIP assets.
- Added generated `dist/latest.json` manifest with version, public download URL, SHA256, date, and notes.
- Added release notes file for `0.1.0`.
- Added GitHub Release publish script with `--dry-run` and local `gh` CLI checks.
- Documented the release process and kept real publication behind explicit confirmation.

Next:

- Publish the first public GitHub Release after explicit confirmation.
- Stage 4B: one-click updater.

## Stage 4A.2

Status: done.

Scope:

- Added a manual GitHub Actions release workflow.
- Release workflow is triggered only by `workflow_dispatch`, never automatically on push.
- Workflow validates input version against `APP_VERSION`.
- Workflow builds versioned ZIP and `latest.json`, runs package safety checks, validates manifest fields, and uploads artifacts.
- With `publish=false`, workflow performs a dry-run artifact build only.
- With `publish=true`, workflow publishes a GitHub Release using standard GitHub Actions `GITHUB_TOKEN`.

Next:

- First release `v0.1.0` has been published.
- Continue with one-click updater QA.

## Stage 4B

Status: done.

Scope:

- Added one-click update installer behind POST `/updates/apply`.
- Updater downloads public release ZIP, verifies SHA256, validates package structure, creates app backup, and copies only allowed application files.
- `.env`, owner data, database, media folders, backups, logs, and local update folders are preserved.
- `/legacy?tab=about` shows an `Обновить` form only when a newer version is available.
- Added CLI helpers: `scripts/check_update.py` and `scripts/apply_update.py`.
- Auto-restart is deferred; the user is told to restart the app manually.

Next:

- Owner QA on Windows with a newer test release.
- Improve rollback reporting and optional restart helper after Windows QA.

## Stage 4B.1

Status: done/current.

Scope:

- Bumped `APP_VERSION` to `0.1.1` for owner updater QA.
- Added update progress status persisted in `updates/update_status.json`.
- Added `/updates/status`.
- Updated the `О программе` update form to show progress steps while update installation runs.
- Blocked duplicate update starts while one update is already running.
- Added release notes for `0.1.1`.
- Added Telegram release notification generator and sender using the existing colorizer/SAVBot setup.
- Added dry-run and copy-only test modes for release notifications.

Next:

- Build and inspect the `v0.1.1` release package.
- Publish real GitHub Release `v0.1.1` only after confirmation.
- Send real Telegram release notification only after confirmation.
- Owner QA: update from bootstrap `0.1.0` to `0.1.1`.

## Daily Telegram Report Timezone Scheduling

Status: done/current.

Scope:

- Diagnosed that the previous launchd schedule used the Mac mini local timezone instead of Moscow time.
- Added `--scheduled` mode with explicit `REPORT_TIMEZONE=Europe/Moscow`.
- Added `REPORT_SEND_HOUR`, `REPORT_SEND_MINUTE`, and `REPORT_SEND_WINDOW_MINUTES`.
- Added duplicate protection so frequent launchd wakeups do not resend the same daily report.
- Updated the launchd template to run every 15 minutes and let the script decide whether it is inside the Moscow 09:00 window.

Next:

- Observe the next scheduled run at 09:00 Europe/Moscow.
- Keep real send logs local and ignored.

## Iteration 1: Legacy Rewards Filters and Totals

Status: done/current.

Scope:

- Added filters above the main `Награды` person list: rank/specialty, country, category, subcategory, and reward name.
- Filters can be combined, including rank plus reward name, to find people matching both conditions.
- Added totals for the current filtered result: people, rewards, stock counts, purchase/current price sums, and latest purchase date.
- Added double-click behavior on the person list: single click selects a person, double click opens the person card.
- Made displayed URL fields clickable only for safe `http`/`https` links.
- Added Escape-as-back behavior on edit forms while keeping Escape reserved for the photo modal when it is open.

Next:

- QA the main `Награды` screen with owner examples such as rank plus specific reward.
- Add dependent/cascading selects later so country narrows category, category narrows subcategory, and subcategory narrows reward names.

## Iteration 2: Search UX and Contextual Guides

Status: done/current.

Scope:

- Disabled browser autocomplete on `/search` and `/legacy?tab=search` search fields.
- Changed empty-query search behavior: `scope=persons`, `scope=rewards`, and `scope=marks` show all records in the selected category; `scope=all` still shows guidance instead of loading everything.
- Increased search UI limit to the first 50 results and show how many rows are displayed out of total matches.
- Specific search scopes render only their own table instead of empty tables for other groups.
- Updated person/reward/mark forms so guide links open the relevant guide block and preserve return back to the form.
- Improved guide delete-blocked messages for used ranks, nodes with children, and nodes used by rewards/marks.

Next:

- Owner QA for empty category searches and form-to-guide return flow.
- Database-backed live search suggestions/datalist remain deferred.

## Backlog / Future

- Implement DataSourceManager.
- Implement Settings -> Data Source screen.
- Implement local config storage for selected data directory.
- Add validation report for connected database and media folders.
- Implement full Clipboard API photo paste.
- Implement physical photo delete only after restore workflow is mature.
- Implement PDF export parity.
- Improve pagination, protected-field display controls, media diagnostics UI, and test coverage.
