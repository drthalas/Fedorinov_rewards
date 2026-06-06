# Fedorinov_rewards

Fedorinov_rewards is a new modernization project for the legacy Windows Rewards / "Nagrady" application. The first goal is to build a safe web mirror of the existing behavior before any functional improvements.

This repository contains only the new project skeleton, documentation, diagnostics, and a read-only backend prototype. Legacy application sources and real local data are not committed here.

## Проектный контекст для Codex

Перед новой задачей Codex должен начинать с постоянной памяти проекта:

```text
docs/context/CODEX_START_HERE.md
```

Там зафиксированы контекст проекта, архитектура, roadmap, релизы, QA baseline, принятые решения и правила ведения Linear.

## Safety Rules

- Do not commit SQLite databases, photos, PDFs, archives, EXE/DLL files, `.env`, tokens, or keys.
- Do not commit `Source/`, `SourceMark/`, `database/`, or `legacy/_external/`.
- Do not modify `/Users/hermes/Desktop/Rewards`.
- Do not run legacy `.exe` files.
- First-stage diagnostics and backend access are read-only.

## Local Data

Create `.env` from `.env.example` if needed:

```sh
cp .env.example .env
```

The expected local data location is:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards
```

Expected files and folders:

- `database/MyDatabase.sqlite`
- `Source/`
- `SourceMark/`
- `default/nofoto.jpg`
- `default/times.ttf`

## Legacy Sources

Legacy repositories are fetched into ignored directories:

```sh
scripts/fetch_legacy_sources.sh
```

The script clones:

- `https://github.com/erypalovyury/rewards`
- `https://github.com/erypalovyury/activation-rewards`

They are stored under `legacy/_external/` and must not be committed.

## Diagnostics

Run read-only database inspection:

```sh
python scripts/inspect_local_data.py
```

Run read-only media link inspection:

```sh
python scripts/check_media_links.py
```

The scripts do not print names, comments, links, or personal database records.

## Backend

Install backend dependencies:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
```

Run the local FastAPI backend:

```sh
scripts/run_dev.sh
```

The app starts on `127.0.0.1:8080` by default. Opening `http://127.0.0.1:8080` redirects to the primary legacy-style working interface at `/legacy?tab=rewards`. The legacy interface uses its own single shell with the old-style tabs as the main navigation, not a nested web-preview page.

## Stage 2A Read-Only Mirror

The primary interface is:

- `/` - redirects to `/legacy?tab=rewards`
- `/legacy?tab=rewards` - main rewards workspace
- `/legacy?tab=search` - legacy-style search
- `/legacy?tab=marks` - standalone marks workspace
- `/legacy?tab=summary` - filtered summary matrix with counts, stock, prices, and CSV export
- `/legacy?tab=about` - preview status

Supporting/technical routes remain available:

- `/dashboard` - diagnostics dashboard and table counts
- `/persons` - awarded persons list
- `/persons?page=1&page_size=25` - awarded persons list with basic pagination
- `/persons/{id}` - awarded person card
- `/persons/{id}/photos` - person and reward photo gallery
- `/rewards/{id}` - reward card
- `/marks` - standalone marks list
- `/marks?page=1&page_size=25` - standalone marks list with basic pagination
- `/marks/{id}` - mark card
- `/guides` - guide tree and write-mode guide maintenance
- `/search` - simple search by name/title/number
- `/health` - environment diagnostics
- `/version` - current application name and version
- `/updates/check` - public GitHub Release update check

The main rewards workspace supports filters above the person list:

- `rank_id` - rank/specialty from the rank guide.
- `country_id` - reward country.
- `category_id` - reward category.
- `subcategory_id` - reward subcategory.
- `name_id` - reward name.

Filters can be combined, for example rank plus a specific reward name. The totals panel at the bottom of the rewards workspace reflects the current filtered selection. Person rows use single click to select and double click to open the person card.

The v0.1.2 release also includes the latest owner-feedback polish: the person list is sorted alphabetically, has a quick left-side search, the reward list scrolls inside its own block, photo cards use equal frames, and long names, links, biographies, and comments wrap correctly in person cards.

The reward guide filters now cascade in the UI: selecting a country limits categories, selecting a category limits subcategories, and selecting a subcategory limits reward names. Empty filter parameters still mean `Все` and do not produce validation errors.

Person, reward, and mark write forms validate required fields before writing to SQLite:

- person: full name, birth date, and rank/specialty;
- reward: selected reward name;
- mark: selected mark name.

Birth date and purchase date inputs use `ДД.ММ.ГГГГ` in the UI. New rewards and marks default `Дата покупки` to today's date.

Search supports legacy-like query parameters:

- `q` - search value.
- `scope` - `all`, `persons`, `rewards`, or `marks`.
- `mode` - `contains`, `starts`, or `exact`.

Examples:

```text
/search?q=Андрос&scope=persons&mode=contains
/search?q=орден&scope=rewards&mode=contains
/legacy?tab=search&q=андреев&scope=all&mode=contains
/search.csv?q=Андрос&scope=all&mode=contains
```

The search is read-only, supports lowercase Cyrillic matching, groups results by persons/rewards/marks, and limits each group to the first 50 UI results.

Search fields disable browser history autocomplete. If `q` is empty and `scope=persons`, `scope=rewards`, or `scope=marks`, the UI shows the first 50 records from that selected category. If `scope=all` and `q` is empty, the UI shows guidance instead of loading everything.

The search value field now provides database-backed suggestions while keeping browser history autocomplete disabled:

- `scope=persons` suggests awarded person names;
- `scope=rewards` is shown to the user as `Наименование награды` and suggests guide names;
- `scope=marks` suggests guide names.

Person search results use user-facing columns: row number, full name, rank/specialty, birth date, and `1`/`0` photo/document flags. Links opened from search carry a safe `return_to`, so the detail page can return to the same search result set.

Guide links from person, reward, and mark forms are contextual: rank fields open the rank/specialty guide block, and reward/mark fields open the shared reward/mark guide tree. The guide page preserves `return_to`, so after adding or editing a guide value the user can return to the form.

Summary supports read-only filter parameters:

- `country_id`
- `category_id`
- `subcategory_id`
- `name_id`
- `extra`
- `include_marks=true`

Examples:

```text
/legacy?tab=summary
/legacy?tab=summary&summary_mode=matrix&country_id=1
/legacy?tab=summary&summary_mode=aggregate&include_marks=true
/summary_matrix.csv?country_id=1
/summary.csv?include_marks=true
```

The default summary mode is the person/reward matrix: rows are decorated persons, reward names become columns, photo/document presence is shown as `1`/`0`, duplicate rewards are counted as `2+`, and totals are shown at the bottom. The main CSV buttons open a system save dialog and write the current CSV to the selected path. The older GET routes `/summary_matrix.csv` and `/summary.csv` remain as technical fallback exports with the same CSV structure.

Start the backend on the Mac mini:

```sh
cd ~/Projects/Fedorinov_Rewards/Fedorinov_rewards
scripts/run_dev.sh
```

The backend binds to `127.0.0.1:8080`.

Open it from a MacBook through an SSH tunnel:

```sh
ssh -N -L 8080:127.0.0.1:8080 hermes-mini
```

Then open:

```text
http://127.0.0.1:8080
```

The root URL opens the legacy UI. Forms launched from legacy buttons carry a safe `return_to` value, so save/delete actions return to the same legacy tab and selected record when possible.

Displayed photos open in an inline lightbox over the current page. Closing the lightbox keeps the user in the same tab and selected record. The older `/photo/view` route remains available only as a fallback/technical viewer.

Displayed URL fields are clickable only for safe `http`/`https` links and open in a new tab. Edit forms support Escape as a shortcut for the existing `Вернуться` action; when the photo lightbox is open, Escape closes the photo instead.

Stage 2B keeps the same read-only mirror and improves readability only: dates are shown as `DD.MM.YYYY`, prices as rubles, stock values as badges, guide sections are collapsible, and search results are limited to the first 25 items per group.

The legacy-style desktop mirror is available at:

- `/legacy?tab=rewards` - old main rewards tab structure with person list, selected rewards, links, booklet placeholder, and photos.
- `/legacy?tab=search` - grouped search in the legacy tab shell.
- `/legacy?tab=marks` - standalone marks tab with selected mark detail.
- `/legacy?tab=summary` - default person × rewards matrix with photo/document flags, totals, filters, and CSV export; aggregate summary remains available from the mode switch.
- `/legacy?tab=about` - preview status, mode, data directory, and commit.

CRUD buttons inside `/legacy` are visible only in development write mode and reuse the existing guarded person, reward, and mark routes.

## Working Write Mode

After owner QA passed, the Windows preview defaults to working edit mode:

```sh
READ_ONLY=false
WRITE_MODE=true
REQUIRE_BACKUP_BEFORE_WRITE=false
REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS=true
```

Ordinary create/update operations, guide edits, photo upload/unlink, biography, links, prices, and numbers can be saved without creating a backup before every action. Dangerous actions such as deletes and migrations remain separately protected with confirmation and backup-sensitive guards. Make regular backups before serious work:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/backup_dev_data.py
python3 scripts/check_backup.py ~/LocalData/FedorinovRewards/backups/Rewards_backup_YYYYMMDD_HHMMSS.zip
```

To disable editing:

```sh
READ_ONLY=true
WRITE_MODE=false
```

Current development write-mode CRUD:

- Person create/edit/delete.
- Reward create/edit/delete for rewards attached to a person.
- Mark create/edit/delete for standalone marks.
- Rank/specialty guide create/edit/delete on `/guides`.
- Award/mark tree guide create/edit/delete on `/guides` for `guide_lev_0` through `guide_lev_4`.
- Person, reward, and mark forms are grouped closer to the old Windows dialogs with owner-facing labels.
- Person edit includes a separate `Краткая биография` field after the biography migration is applied.
- Click any displayed photo to open the large photo viewer.
- Photo clicks open an inline modal/lightbox without leaving the current page; the viewer supports zoom in, zoom out, reset, mouse drag panning, wheel zoom, Escape close, and previous/next navigation.
- `/persons/{id}/photos` includes a gallery and previous/next slideshow.
- Person, reward, and mark edit forms include photo upload/replace controls in `WRITE_MODE=true`.
- Photo clear/unlink removes only the SQLite field value. It does not delete the physical file.
- Browser clipboard paste is available in write mode through the same guarded upload pipeline. If the browser does not expose image clipboard access on localhost, use the `+` file upload button.
- The legacy rewards screen can open the selected person's local `Source/{person_id}` folder and create a ZIP archive of that folder after the user selects a save path. Source files are not deleted.

Photo upload/clear remains behind `WRITE_MODE=true`. With the working preview defaults, these ordinary photo operations do not require a fresh backup before every save, but regular backups are still recommended.

Guide deletes are protected: ranks used by person cards cannot be deleted, and tree nodes cannot be deleted while they have child nodes or are referenced by rewards/marks. Person, reward, and mark forms include links back to the guide page so new guide values can be managed before returning to the edit flow.

To add the dedicated biography column to a backed-up development database:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/migrate_add_person_biography.py --dry-run
WRITE_MODE=true REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/migrate_add_person_biography.py --apply
```

Never commit `.env`, backups, SQLite databases, `Source/`, `SourceMark/`, photos, PDFs, archives, EXE/DLL files, or real owner data.

## Update Checker

The application version is defined in `backend/app/version.py`.

Current version:

```text
0.1.0
```

Version routes:

```text
/version
/updates/check
```

The update checker reads a public GitHub Release manifest:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

No GitHub token is required because releases are public. The checker and updater do not upload or read owner data, photos, `database/`, `Source/`, or `SourceMark/`.

Relevant environment settings:

```text
UPDATE_CHECK_ENABLED=true
UPDATE_MANIFEST_URL=https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
UPDATE_TIMEOUT_SECONDS=10
APP_INSTALL_DIR=
UPDATE_BACKUP_DIR=updates/backups
UPDATE_DOWNLOAD_DIR=updates/downloads
UPDATE_EXTRACT_DIR=updates/extracted
```

One-click update installation is available from `/legacy?tab=about` after checking updates. When a newer release is available, the app shows an `Обновить` button. The page shows progress steps while the update runs: checking, downloading, verifying, backing up, installing, and done. Status is also available at `/updates/status`.

The updater downloads the release ZIP, verifies SHA256, creates an application backup under `updates/backups`, preserves `.env`, and copies only allowed application files. It does not touch `database/`, `Source/`, `SourceMark/`, `default/`, backups, logs, or owner data. Automatic restart is deferred; after a successful update, close the launch window and start the app again.

CLI helpers:

```sh
python3 scripts/check_update.py
python3 scripts/apply_update.py --dry-run
python3 scripts/apply_update.py --apply
```

`apply_update.py` defaults to dry-run unless `--apply` is passed.

## Release Package

Release assets are generated from the current `APP_VERSION`:

```sh
python3 scripts/print_version.py
python3 scripts/build_release_package.py
python3 scripts/check_package_safety.py dist/FedorinovRewards_WebPreview_vX.Y.Z.zip
python3 scripts/publish_github_release.py --dry-run
```

Generated release assets:

- `dist/FedorinovRewards_WebPreview_vX.Y.Z.zip`
- `dist/latest.json`

Real GitHub Release publication is done only after confirmation:

```sh
python3 scripts/publish_github_release.py
```

Publication uses local `gh` CLI authentication on the developer machine. Do not commit GitHub tokens. See `docs/RELEASE_PROCESS.md`.

Release Telegram notifications are sent from the Mac mini through the existing colorizer/SAVBot setup, not from GitHub Actions:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --dry-run
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --send-test-to-copy-only
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --send
```

Real notifications require separate confirmation. Tokens and chat ids remain local.

Preferred publication path is the manual GitHub Actions workflow:

```text
.github/workflows/manual_release.yml
```

Run it from GitHub -> Actions -> Manual Release. First use `publish=false` to build and inspect artifacts. Run again with `publish=true` only when the release is ready. Releases are not published automatically on push.

## Windows Portable Preview

The first Windows owner preview is a portable ZIP, not an installer. It contains application code, startup scripts, and Windows runbook documents only. Owner data, SQLite databases, photos, backups, `.env`, `.venv`, legacy sources, and generated reports are not included.

Build the preview package:

```sh
python3 scripts/build_windows_preview_package.py
python3 scripts/check_package_safety.py dist/FedorinovRewards_WebPreview_v0.1.zip
```

The package is written to:

```text
dist/FedorinovRewards_WebPreview_v0.1.zip
```

On Windows:

1. Unpack the ZIP.
2. Install Python 3.11+ with `Add Python to PATH`.
3. Run `start_windows.bat`.
4. On first run, edit `.env` and set `REWARDS_DATA_DIR` to the local Rewards data folder.
5. Run `start_windows.bat` again and open `http://127.0.0.1:8080`.

Windows preview defaults are now the working preview mode:

```text
READ_ONLY=false
WRITE_MODE=true
REQUIRE_BACKUP_BEFORE_WRITE=false
REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS=true
APP_HOST=127.0.0.1
APP_PORT=8080
```

Ordinary editing is enabled without requiring a fresh backup before every save. Dangerous actions such as deletes remain protected by confirmation and backup-sensitive guards. Make regular backups before serious work. To disable editing in local `.env`, set `READ_ONLY=true` and `WRITE_MODE=false`.

## Daily Telegram Reports

Daily progress reports for the project name `Награды и награждённые` can be generated and sent through the existing colorizer/SAVBot Telegram bot.

Preview the report without sending anything:

```sh
python3 scripts/send_daily_report.py --dry-run
```

Send a confirmed test only to the copy recipient:

```sh
python3 scripts/send_daily_report.py --send-test-to-copy-only
```

Local configuration is kept in ignored `.env.daily-report`. The sender can read the existing colorizer bot token from `~/Projects/picture-colorizer/.env` without printing it. Scheduled delivery is timezone-aware and defaults to `REPORT_TIMEZONE=Europe/Moscow`, `REPORT_SEND_HOUR=9`, and a 15-minute send window. The launchd template wakes the script every 15 minutes and the script sends only inside the Moscow 09:00 window:

```text
deploy/launchd/com.fedorinov.daily-report.plist.example
```

See `docs/DAILY_TELEGRAM_REPORTS.md` for setup, safety rules, and launchd enable/disable commands.

## Person Booklets

The selected person can be exported as a booklet from the main rewards screen or the person card:

```text
/legacy?tab=rewards&person_id=...
/persons/{id}/booklet
```

The booklet preview is printable and has a `Сохранить PDF` button. The button opens a system save dialog and writes the PDF to the selected path. The app reports the saved path after success. In browser/headless environments where a native save dialog is unavailable, use browser print-to-PDF as a fallback.

The booklet includes person details, biography, links, person photos/documents, and all rewards with their key fields and photos. Missing photos do not stop generation.
