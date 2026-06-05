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

- Historical Stage 3 rule: early write stages required a fresh backup first. After owner QA, ordinary writes use working mode defaults; dangerous actions remain separately protected.

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
- Photo writes require `WRITE_MODE=true` and the guarded write pipeline; working preview defaults do not require a backup before every ordinary photo save.
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
- Windows preview defaults to editable working preview mode. Ordinary saves are enabled; dangerous actions remain separately protected.

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
- Write-mode guard before every guide write; dangerous guide deletes remain separately protected.
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

## Iteration 3: Summary Matrix By Persons And Rewards

Status: done/current.

Scope:

- Added the default `Шахматка по кавалерам` mode to `/legacy?tab=summary`.
- Rows are decorated persons; columns are reward names selected by the existing guide filters.
- Person photo/document columns show `1` when a field has a linked photo/path and `0` when empty.
- Reward cells show the count of matching rewards for that person, so duplicate rewards show `2+` instead of only `1`.
- A highlighted totals row sums person photo/document columns and reward columns.
- Added `/summary_matrix.csv` with UTF-8 BOM for Excel, Russian headers, matrix values, and totals.
- Kept the previous aggregate table as `summary_mode=aggregate` with `/summary.csv`.

Next:

- Owner QA for examples such as country/category/name matrix filters.
- Sticky first columns remain deferred UX polish; cascading guide selects are implemented in the later required-fields iteration.
- Further refine reward number columns after owner QA if more detail is needed.

## Iteration 4: Person Folder Archive And Photo Controls

Status: done/current.

Scope:

- Added `Открыть каталог` on the legacy rewards screen for the selected person. It opens only `Source/{person_id}` inside `REWARDS_DATA_DIR`.
- Added `Архивировать` on the legacy rewards screen. It creates a ZIP of the selected person's folder under `REWARDS_DATA_DIR/archives/` and never deletes source files.
- Archive creation excludes `.env`, logs, backups, nested ZIP, EXE, DLL, database, `Source` root, and `SourceMark` paths.
- Added audit logging for `person_folder_archived` with person id and archive filename only.
- Enhanced the inline photo lightbox with zoom in/out, reset, wheel zoom, and mouse drag panning.
- Enabled `Вставить из буфера` in write-mode photo controls using the existing guarded `/photos/upload` endpoint.

Next:

- Owner QA on Windows for OS folder opening and browser clipboard support.
- PDF/booklet generation remains the next dedicated iteration.
- Physical photo deletion remains deferred.

## Iteration 5: Person Booklet PDF

Status: done/current.

Scope:

- Added `Сформировать буклет` for the selected person on `/legacy?tab=rewards&person_id=...`.
- Added `/persons/{person_id}/booklet` as a printable booklet preview without the normal web navigation shell.
- Added PDF download through POST `/persons/{person_id}/booklet.pdf` using `reportlab`.
- Booklets include person details, rank, birth date, biography, comments, safe links, person photos/documents, and all rewards with key fields and reward photos.
- Generated PDF files are saved under `REWARDS_DATA_DIR/generated/booklets/` and ignored by Git.
- Missing or unsafe image paths are handled without crashing.

Next:

- Owner QA for booklet layout and PDF output on Windows.
- Tune booklet visual layout after the owner checks printed/PDF examples.
- Summary PDF remains a separate future export task.

## v0.1.2 Working Write Mode Release

Status: done/current.

Scope:

- Enabled permanent working write-mode defaults for owner package configuration.
- Ordinary create/update operations, photo upload/unlink, guide edits, biography/comment/link/price/number edits no longer require a fresh backup before every save.
- Dangerous actions remain protected by explicit confirmation and `REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS=true`.
- Version bumped to `0.1.2`.
- Added `release_notes/0.1.2.md`.

Next:

- Publish v0.1.2 through Manual Release workflow.
- Confirm public `latest.json` and send release Telegram notification.

## Iteration: Cascading Guides And Required Fields

Status: done/current.

Scope:

- Added cascading guide selects for reward and mark forms: country narrows categories, category narrows subcategories, and subcategory narrows names.
- Added the same cascade to the main `/legacy?tab=rewards` filter block.
- Required person fields are now checked before writing: full name, birth date, and rank/specialty.
- Required reward/mark guide name is now checked before writing so empty rewards or marks cannot be created.
- Person birth date and purchase dates accept/display the owner-facing `ДД.ММ.ГГГГ` format and are normalized before storage.
- New reward and mark forms default `Дата покупки` to the current date.
- Reward and mark edit preserve existing guide ids if a form omits guide fields, preventing accidental guide clearing.

Next:

- Hermes QA for add/edit person, reward, and mark flows on the dev data root.
- Owner QA for cascading guide behavior in the Windows package after the next release.

## Iteration: Search Columns, Suggestions, And Return Navigation

Status: done/current.

Scope:

- Search person results now use user-facing columns and a row number instead of exposing the database id as the first column.
- Person search results show photo/document presence flags as `1`/`0`, matching the summary matrix convention.
- Search category `rewards` is labeled for users as `Наименование награды`.
- Search value inputs keep browser history autocomplete disabled while adding database-backed datalist suggestions.
- Person suggestions come from awarded person names; reward and mark suggestions come from guide names.
- Search result links pass `return_to` to person, reward, and mark detail pages so the user can return to the current search results.

Next:

- Hermes QA for search result columns, datalist suggestions, and return navigation from search detail pages.

## v0.1.2 Final QA Blockers

Status: done/current.

Scope:

- Polished form validation messages before release QA so user-facing errors stay Russian and non-technical.
- Added regression coverage for preserving entered form values and selected cascading guides after validation errors.
- Fixed cascading guide dropdowns in reward forms, mark forms, and the legacy rewards filters.
- Category changes now correctly populate subcategories; subcategory changes now correctly populate names.
- Confirmed release notes include the full owner-facing v0.1.2 change list.

Next:

- Publish v0.1.2 after release package safety check and Manual Release workflow dry-run.
- Send Telegram release notification only after public `latest.json` is verified.

## Backlog / Future

- Implement DataSourceManager.
- Implement Settings -> Data Source screen.
- Implement local config storage for selected data directory.
- Add validation report for connected database and media folders.
- Validate Clipboard API photo paste on owner Windows browsers and keep file-upload fallback.
- Implement physical photo delete only after restore workflow is mature.
- Implement summary PDF export parity.
- Improve pagination, protected-field display controls, media diagnostics UI, and test coverage.
