# Fedorinov_rewards

Fedorinov_rewards is a new modernization project for the legacy Windows Rewards / "Nagrady" application. The first goal is to build a safe web mirror of the existing behavior before any functional improvements.

This repository contains only the new project skeleton, documentation, diagnostics, and a read-only backend prototype. Legacy application sources and real local data are not committed here.

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

The app starts on `127.0.0.1:8080` by default. Opening `http://127.0.0.1:8080` redirects to the primary legacy-style working interface at `/legacy?tab=rewards`.

## Stage 2A Read-Only Mirror

The primary interface is:

- `/` - redirects to `/legacy?tab=rewards`
- `/legacy?tab=rewards` - main rewards workspace
- `/legacy?tab=search` - legacy-style search
- `/legacy?tab=marks` - standalone marks workspace
- `/legacy?tab=summary` - basic summary counts and price/stock totals
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
- `/guides` - read-only guide tree
- `/search` - simple search by name/title/number
- `/health` - environment diagnostics

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

The search is read-only, supports lowercase Cyrillic matching, groups results by persons/rewards/marks, and limits each group to the first 25 UI results.

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

Stage 2B keeps the same read-only mirror and improves readability only: dates are shown as `DD.MM.YYYY`, prices as rubles, stock values as badges, guide sections are collapsible, and search results are limited to the first 25 items per group.

The legacy-style desktop mirror is available at:

- `/legacy?tab=rewards` - old main rewards tab structure with person list, selected rewards, links, booklet placeholder, and photos.
- `/legacy?tab=search` - grouped search in the legacy tab shell.
- `/legacy?tab=marks` - standalone marks tab with selected mark detail.
- `/legacy?tab=summary` - basic summary counts and price/stock totals.
- `/legacy?tab=about` - preview status, mode, data directory, and commit.

CRUD buttons inside `/legacy` are visible only in development write mode and reuse the existing guarded person, reward, and mark routes.

## Development Write Mode

Write mode is for the local development stand only. Keep owner preview and production-style runs in read-only mode:

```sh
WRITE_MODE=false
```

Before enabling write mode, create and validate a fresh backup:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/backup_dev_data.py
python3 scripts/check_backup.py ~/LocalData/FedorinovRewards/backups/Rewards_backup_YYYYMMDD_HHMMSS.zip
```

Run development write mode explicitly when testing CRUD:

```sh
WRITE_MODE=true REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards scripts/run_dev.sh
```

Current development write-mode CRUD:

- Person create/edit/delete.
- Reward create/edit/delete for rewards attached to a person.
- Mark create/edit/delete for standalone marks.
- Click any displayed photo to open the large photo viewer.
- `/persons/{id}/photos` includes a gallery and previous/next slideshow.
- Person, reward, and mark edit forms include photo upload/replace controls in `WRITE_MODE=true`.
- Photo clear/unlink removes only the SQLite field value. It does not delete the physical file.
- Browser clipboard paste is prepared as a disabled control and documented for a later Clipboard API implementation.

Photo upload/clear remains guarded by the same backup-first rule as CRUD. Keep owner preview read-only unless testing on a backed-up copied data folder.

Never commit `.env`, backups, SQLite databases, `Source/`, `SourceMark/`, photos, PDFs, archives, EXE/DLL files, or real owner data.

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
REQUIRE_BACKUP_BEFORE_WRITE=true
APP_HOST=127.0.0.1
APP_PORT=8080
```

Backup-first protection remains enabled. Before editing real data, create and validate a backup. To disable editing in local `.env`, set `READ_ONLY=true` and `WRITE_MODE=false`.
