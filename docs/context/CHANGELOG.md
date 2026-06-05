# Changelog

## Search Columns, Suggestions, And Return Navigation

- Reworked person search results to hide the technical database id and show a row number instead.
- Added person photo/document presence columns to search results using `1`/`0`.
- Renamed the user-facing rewards search category to `Наименование награды`.
- Added database-backed datalist suggestions for person names and guide names while keeping browser history autocomplete disabled.
- Search result links now pass a safe `return_to` to person, reward, and mark detail pages.
- Detail pages show a direct return link back to search results when opened from search.

## Cascading Guides And Required Fields

- Added cascading guide selects in reward and mark forms so names are limited to the selected country/category/subcategory branch.
- Added cascading guide filters to the main `Награды` tab.
- Blocked empty person creation/update by requiring full name, birth date, and rank/specialty before any database write.
- Blocked empty reward and mark creation/update by requiring a selected name.
- Switched owner-facing birth and purchase date inputs to `ДД.ММ.ГГГГ` while preserving normalized storage.
- Defaulted purchase date to today's date for new rewards and new marks.
- Preserved existing reward and mark guide ids during edit if guide fields are omitted by the form.

## v0.1.2 Working Write Mode Release

- Bumped the application version to `0.1.2`.
- Enabled working write-mode defaults for the Windows owner package: `READ_ONLY=false`, `WRITE_MODE=true`, and `REQUIRE_BACKUP_BEFORE_WRITE=false`.
- Added `REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS=true` for separately protecting dangerous actions such as deletes.
- Changed write guard messages to Russian user-facing text.
- Documented that ordinary edits no longer require a fresh backup before every save, while dangerous actions remain protected.
- Added `release_notes/0.1.2.md` with owner-facing notes for summary matrix, archive/catalog actions, photo controls, PDF booklet, and working write mode.

## Iteration 5 Person Booklet PDF

- Replaced the legacy `Сформировать буклет` placeholder with a working person booklet preview.
- Added `/persons/{person_id}/booklet` printable layout with person details, biography, links, person photos/documents, and rewards.
- Added POST `/persons/{person_id}/booklet.pdf` to generate and download a PDF when `reportlab` is installed.
- Generated PDFs are written under the local data root `generated/booklets/` and remain outside Git.
- Missing or unsafe image paths do not crash booklet rendering; unavailable images are skipped or shown as not found.

## Iteration 4 Person Folder And Photo Controls

- Added legacy rewards actions to open the selected person's local `Source/{person_id}` folder.
- Added safe person-folder ZIP archive creation under the local data `archives/` folder.
- Added audit logging for person-folder archives without personal text values.
- Enhanced the inline photo lightbox with zoom in, zoom out, reset, mouse drag panning, and wheel zoom.
- Enabled `Вставить из буфера` in write-mode photo controls using the browser Clipboard API and the existing guarded upload endpoint.
- Kept physical media deletion, PDF/booklet generation, and automatic OS-level archive cleanup deferred.

## Iteration 3 Summary Matrix By Persons And Rewards

- Added a default `Шахматка по кавалерам` mode to `/legacy?tab=summary`.
- Matrix rows are decorated persons, reward names become columns, and values show `0`, `1`, or duplicate counts.
- Added person photo/document presence columns and a highlighted totals row.
- Added `/summary_matrix.csv` export with UTF-8 BOM for Excel while keeping the existing aggregate `/summary.csv`.
- Kept PDF export disabled and cascading select narrowing deferred.

## v0.1.1 Release Notes Correction

- Expanded `release_notes/0.1.1.md` to include all owner-facing improvements from the release: rewards filters, totals, search, contextual guides, return navigation, and update progress.
- Added release notification correction mode for sending an explicit follow-up when a prior release notification was incomplete.
- Updated release process documentation to require reviewing full user-visible release notes before sending Telegram notifications.

## Stage 4B.1 Update Progress and Release Notifications

- Bumped application version to `0.1.1` for the owner updater test release.
- Added visible update progress UI after clicking `Обновить`.
- Added `/updates/status` with current update status, step, message, timestamps, and error.
- Added protection against starting a second update while one update is already running.
- Added `release_notes/0.1.1.md`.
- Added Telegram release notification generator and sender using the existing local colorizer/SAVBot configuration.
- Kept real GitHub Release publication and real Telegram sending behind separate confirmation.

## Daily Telegram Report Timezone Scheduling Fix

- Changed scheduled daily Telegram reports to use `Europe/Moscow` explicitly instead of the Mac mini local timezone.
- Added `--scheduled` mode to send only inside the configured Moscow 09:00 window.
- Added dedupe checks against `logs/daily_reports.jsonl` so hourly/interval launchd wakeups do not send duplicates.
- Updated the launchd template to run every 15 minutes and let the script decide whether it is time to send.
- Added scheduled dry-run diagnostics that report Moscow time, target time, window status, and whether a send would happen.
- No Telegram messages are sent by the scheduled dry-run.

## Stage 4B One-Click Update Installer

- Added safe updater service for public GitHub Release ZIP installation.
- Added POST-only `/updates/apply` route with confirmation.
- Added update button in `/legacy?tab=about` when a newer version is available.
- Updater verifies SHA256, validates ZIP structure, rejects forbidden paths, creates an app backup, and copies only allowed application files.
- `.env`, database, media folders, backups, logs, and owner data are preserved.
- Added CLI helpers `scripts/check_update.py` and `scripts/apply_update.py`.
- Kept automatic restart deferred; users are instructed to restart the app manually.

## Stage 4A.2 Manual GitHub Release Workflow

- Added `.github/workflows/manual_release.yml` for manual release packaging and publishing.
- Workflow runs only through `workflow_dispatch`; releases are not published on push.
- Workflow validates input version against `APP_VERSION`, builds versioned ZIP and `latest.json`, runs safety checks, validates manifest content, and uploads artifacts.
- `publish=false` performs dry-run artifact build only.
- `publish=true` publishes the GitHub Release with standard GitHub Actions `GITHUB_TOKEN`.

## Stage 4A.1 GitHub Release Package Publishing

- Added `scripts/print_version.py` for the current app name/version.
- Added `scripts/build_release_package.py` to generate versioned Windows ZIP assets and `dist/latest.json`.
- Added `release_notes/0.1.0.md` for human-readable release notes.
- Added `scripts/publish_github_release.py` with dry-run support and local `gh` CLI checks.
- Added release process documentation and tests for manifest safety, SHA256 matching, and publish dry-run.
- Kept real GitHub Release publication disabled unless explicitly confirmed.

## Stage 4A Public GitHub Update Checker

- Added a single application version source and `/version`.
- Added token-free `/updates/check` using the public GitHub Release `latest.json` manifest.
- Added update status UI to `/legacy?tab=about` with a disabled Stage 4B install placeholder.
- Added example update manifest and a Stage 4B one-click updater plan.
- Updated Windows/help documentation to explain that update checks do not upload database, photos, or owner data.
- Kept Stage 4A check-only: no ZIP download and no installation.

## Stage 3J Summary Table and CSV Export

- Reworked `/legacy?tab=summary` from basic counts into a filterable summary matrix.
- Added filters for country, category, subcategory, name, extra/link level, and optional standalone marks.
- Added compact green matrix styling with totals, stock counts, purchase/current price sums, and last purchase date.
- Added read-only `/summary.csv` export with UTF-8 BOM and the same filters as the UI.
- Kept PDF export as a disabled placeholder for the next export stage.
- Added tests for summary filters, mark inclusion, CSV output, route registration, and parameter placeholders.

## Stage 3I Form Parity and Biography

- Added an idempotent migration script for a separate `person.biography` column.
- Updated person create/edit to group main data, links, short biography, comments, and photo controls.
- Renamed `link1` and `link2` in the UI to the owner-facing labels for `Память народа` and `Форум коллекционеров`.
- Updated reward and mark forms to group guide fields, purchase fields, and photo controls more like the old Windows dialogs.
- Updated person detail and the legacy rewards tab to show `Краткая биография`.
- Updated account-card photo labels to `Фото учётной карточки, страница 1/2`.
- Kept photo upload/clear controls behind `WRITE_MODE=true` and the existing backup-first guard.
- Added tests for the biography migration, biography persistence, form labels, and photo controls.

## Stage 3H Guides CRUD

- Added guarded add/edit/delete support for the rank/specialty guide used by person cards.
- Added guarded add/edit/delete support for award/mark tree levels `guide_lev_0` through `guide_lev_4`.
- Kept all guide writes behind `WRITE_MODE=true` and the existing backup-first guard.
- Blocked rank deletion when the rank is used by person records.
- Blocked tree node deletion when a node has children or is referenced by rewards/marks.
- Updated `/guides` with write-mode-only toolbar actions, edit/delete forms, and safe return navigation.
- Added guide links from person, reward, mark, and legacy forms back to `/guides`.
- Added unit tests for guide writes, protected deletes, write-mode blocking, and return URL safety.

## Daily Telegram Reports

- Added a safe daily Telegram report generator for the project name `Награды и награждённые`.
- Added a sender that uses the existing colorizer/SAVBot Telegram bot token without committing or printing the token.
- Added dry-run support, copy-only test-send support, local ignored configuration, and ignored JSONL send logs.
- Added a launchd plist example for daily 09:00 delivery on the Mac mini.
- Documented that the first real send to Sergey requires separate confirmation.

## Legacy Shell Cleanup And Photo Lightbox

- Moved `/legacy` to a dedicated `legacy_base.html` layout so the primary working interface no longer renders inside the global web navigation shell.
- Kept only the legacy tabs (`Награды`, `Поиск`, `Знаки`, `Свод.таблица`, `О программе`) and compact mode status in the main legacy UI.
- Added a shared inline photo lightbox for standalone pages and `/legacy`.
- Photo clicks now open an enlarged image over the current page without changing URL or leaving the selected legacy tab.
- Kept `/photo/view` as a fallback/technical route.

## Legacy UI Primary Interface

- Changed `/` to redirect to `/legacy?tab=rewards`.
- Updated top navigation so the legacy mirror is presented as the main application, not a separate mode.
- Added safe `return_to` navigation for person, reward, mark, and photo flows opened from `/legacy`.
- Person, reward, and mark create/edit/delete actions now return to the relevant legacy tab when `return_to` is present.
- Updated mode text to Russian user-facing labels: `Рабочий режим` and `Режим просмотра`.
- Changed Windows preview defaults to `READ_ONLY=false`, `WRITE_MODE=true`, with `REQUIRE_BACKUP_BEFORE_WRITE=true` still enabled.
- Kept `write_guard`, backup-first policy, and audit logging intact.

## Stage 3G Search Rewrite

- Replaced the old SQLite `LIKE`-only search with a shared repository for `/search` and `/legacy?tab=search`.
- Fixed lowercase and partial Cyrillic search by using Python Unicode normalization with `casefold()`.
- Search now covers persons, rewards, and marks with joined guide names and owner names where appropriate.
- Added `scope=all/persons/rewards/marks` and `mode=contains/starts/exact`.
- Updated `/search` UI with legacy-like category, condition, value, search, and reset controls.
- Updated legacy search tab with matching controls, grouped tables, counts, and clickable rows.
- Added read-only `/search.csv` export with UTF-8 BOM for Excel compatibility.
- Added tests for Cyrillic partial search, lowercase search, reward/mark number search, empty query behavior, quote handling, and legacy route registration.

## Stage 3F Photo Viewer and Photo Management

- Added clickable photos and a large `/photo/view` viewer that uses the existing safe `/media` endpoint.
- Added slideshow navigation to `/persons/{id}/photos` while keeping the photo grid.
- Updated legacy rewards photo block to show `Фото кавалера`, `Главное фото`, and `Общее фото наград`.
- Replaced technical photo path labels with owner-facing Russian labels.
- Added write-mode-only photo upload/replace controls to person, reward, and mark edit forms.
- Added write-mode-only photo clear/unlink controls that clear SQLite fields without deleting physical files.
- Added guarded `/photos/upload` and `/photos/clear` endpoints with backup-first enforcement, field whitelists, extension checks, and 25 MB file limit.
- Added `python-multipart` dependency for browser file upload.
- Added `docs/photo_management_plan.md` and unit tests for photo upload/clear on temporary SQLite data.

## Windows Media Endpoint Bugfix

- Replaced `/media` subprocess file reads with cross-platform `FileResponse` serving.
- Added explicit Python read-check before serving real media or falling back.
- Added `/media-debug?path=...` diagnostics for input path, normalized path, resolved absolute path, data root, existence, file/readability flags, suffix, and fallback reason.
- Added tests for POSIX paths, Windows backslash paths, URL-encoded backslash paths, and traversal rejection.
- Rebuilt the Windows preview package with the media fix and `/legacy` interface included.

## Stage 3E Legacy Desktop Layout Mirror

- Added separate `/legacy` route for a desktop-style mirror of the old Windows main form.
- Added legacy-style tabs for `Награды`, `Поиск`, `Знаки`, `Свод.таблица`, and `О программе`.
- Added rewards tab layout with left person list, selected person reward table, links/comment block, booklet placeholder, and photo block.
- Added marks tab layout with standalone mark list, selected mark detail, photo block, and write-mode-gated CRUD links.
- Added basic summary counts and price/stock aggregates.
- Kept existing `/persons`, `/rewards`, `/marks`, `/guides`, `/search`, and CRUD routes unchanged.
- Added `docs/legacy_ui_inventory.md` for the legacy desktop UI inventory.
- Kept PDF export, photo upload/replace/delete, Guides CRUD, and full svod/filter parity deferred.
- Stage 3E QA passed.
- Fixed explicit `HEAD /legacy` support for QA checks.
- Rebuilt the Windows preview package with the `/legacy` route and templates included.

## Stage 2C Windows Portable Preview Package

- Added Windows `.bat` and PowerShell launch scripts for portable preview startup.
- Added `.env.windows.example` with read-only defaults and owner data path instructions.
- Added Russian Windows preview runbook and owner checklist.
- Added package builder for `dist/FedorinovRewards_WebPreview_v0.1.zip`.
- Added package safety checker that blocks real data, backups, `.env`, `.venv`, media, archives, binaries, legacy sources, and local reports.
- Documented that the Windows preview is code-only and owner data remains outside the package.

## Iteration 2 Search UX and Contextual Guides

- Disabled browser autocomplete in normal and legacy search forms.
- Empty search with a selected category now shows all records in that category, while empty `all` search stays guarded.
- Search UI now shows the first 50 results and displays shown-vs-total counts.
- Specific search categories render only their own result table.
- Form guide links now jump to rank or guide-tree blocks and preserve return back to the form.
- Guide delete-blocked messages are more specific.
- Database-backed search suggestions remain deferred.

## Iteration 1 Legacy Rewards Filters and Totals

- Added main `Награды` filters for rank/specialty and reward guide levels.
- Added filtered totals at the bottom of the main rewards screen.
- Added double-click from the person list to the person card.
- Made URL fields clickable only when they are safe `http`/`https` links.
- Added Escape navigation back from edit forms without breaking photo modal Escape behavior.
- Kept APP_VERSION at `0.1.1`; no release was published and no Telegram release notification was sent.

## Stage 3D Mark CRUD

- Added guarded mark create/edit/delete repository functions using parameterized SQL.
- Added write-mode and recent-backup enforcement before mark writes.
- Added web routes and forms for `/marks/new`, `/marks/{mark_id}/edit`, and `/marks/{mark_id}/delete`.
- Added write-mode-only mark add/edit/delete buttons while keeping read-only mode locked down.
- Kept photo fields as readonly text and did not upload, replace, or delete media files.
- Added audit logging for mark create/update/delete actions without personal text values.
- Added unit tests for disabled write mode, create, update, delete, media folder preservation, and quote handling.

## Stage 3C Reward CRUD

- Added guarded reward create/edit/delete repository functions using parameterized SQL.
- Added write-mode and recent-backup enforcement before reward writes.
- Added web routes and forms for `/persons/{person_id}/rewards/new`, `/rewards/{reward_id}/edit`, and `/rewards/{reward_id}/delete`.
- Added write-mode-only reward add/edit/delete buttons while keeping read-only mode locked down.
- Kept photo fields as readonly text and did not upload, replace, or delete media files.
- Added audit logging for reward create/update/delete actions without personal data.
- Added unit tests for disabled write mode, create, update, delete, media folder preservation, quote handling, and nonexistent person validation.

## Stage 3B Person CRUD

- Added guarded person create/edit/delete repository functions using parameterized SQL.
- Added write-mode checks and recent-backup enforcement before person writes.
- Added web routes and forms for `/persons/new`, `/persons/{id}/edit`, and `/persons/{id}/delete`.
- Added write-mode-only buttons on person list/detail pages while keeping read-only mode locked down.
- Blocked person delete when rewards still reference that person.
- Added audit logging for person create/update/delete actions.
- Added unit tests for disabled write mode, create, update, delete, delete-with-rewards blocking, and quoted text handling.

## Stage 3A Backup and Write-Mode Foundation

- Added `scripts/backup_dev_data.py` to create safe local backups outside Git.
- Added `scripts/check_backup.py` for read-only backup zip validation.
- Added `WRITE_MODE=false` and `REQUIRE_BACKUP_BEFORE_WRITE=true` environment flags.
- Added guarded SQLite write connection support for future CRUD routes while keeping existing viewer routes read-only.
- Added backup freshness and audit service foundations for future write gates.
- Added a read-only/write-mode UI indicator in the base layout.
- Added `docs/legacy_feature_gap.md` and updated roadmap/context docs for Stage 3B+ CRUD planning.

## Stage 2B UX Readability Polish

- Added centralized display helpers for dates, money, booleans, empty values, media presence, and pagination metadata.
- Replaced technical boolean/date/price output in templates with human-readable labels, `DD.MM.YYYY` dates, and ruble formatting.
- Added basic pagination to `/persons` and `/marks` with `page` and `page_size` query parameters.
- Limited `/search` to the first 25 results per group and added per-group counts, preserved query text, empty-query guidance, and no-results messaging.
- Improved placeholder photo styling and added "Нет фото" captions when a media field is empty.
- Made `/guides` easier to scan with collapsible nested `details` sections.
- Kept Stage 2B read-only; editing remains blocked until backup/migration architecture is defined.

## Stage 2A QA Accepted

- Hermes QA passed for Stage 2A.
- All target pages returned HTTP 200.
- Broken images: 0.
- Real media displayed from the stable dev data root.
- Stable dev data root: `/Users/hermes/LocalData/FedorinovRewards/Rewards`.

## Dev Data Root Stabilization

- Documented that Desktop-hosted sample data can block on read in the current environment.
- Recommended `~/LocalData/FedorinovRewards/Rewards` as the stable non-Desktop development data root when a readable local copy is available.
- Kept real data, `.env`, and copied media/database files outside Git.

## Stage 2A Media Resolver Bugfix

- Fixed media URL generation by centralizing `/media` links in a Jinja helper.
- Improved media path normalization for URL-decoded paths, Windows backslashes, allowed roots, and absolute paths inside `REWARDS_DATA_DIR`.
- Added `HEAD /media` support for diagnostics.
- Added timeout-based media reads so unreadable local files fall back instead of hanging image requests.
- Added minimal tests for the read-only media resolver.

## Stage 2A Minimal Read-Only Web Mirror

- Added FastAPI routers for dashboard, persons, rewards, marks, guides, search, health, and media.
- Added read-only sqlite3 repository modules.
- Added safe media resolver and `/media` endpoint with `default/nofoto.jpg` fallback.
- Added Jinja2 templates and simple CSS for the legacy mirror pages.
- Kept SQLite access read-only and local data outside Git.
