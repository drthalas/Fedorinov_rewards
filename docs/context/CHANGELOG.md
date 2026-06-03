# Changelog

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
