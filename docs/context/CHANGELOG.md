# Changelog

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
