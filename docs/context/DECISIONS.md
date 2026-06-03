# Decisions

## Separate Application Code and User Data

The application code and the user data are separate.

The real owner database remains local on the owner's computer. The current `/Users/hermes/Desktop/Rewards` directory is only a safe development sample.

Future local installations must allow the user to connect their own local Rewards data folder through a data source settings screen.

The application must not upload, sync, or commit the SQLite database, photos, generated files, `.env` files, keys, tokens, or other real local data.

## Stage 2A Read-Only Mirror Structure

The Stage 2A backend uses FastAPI routers, Jinja2 templates, and small sqlite3 repository modules.

SQLite access stays read-only through `mode=ro`. SQL queries are parameterized where user input is involved.

Media access goes through a `/media` endpoint that resolves paths under `REWARDS_DATA_DIR` only and falls back to `default/nofoto.jpg` when a referenced image is absent.

The web mirror intentionally displays the old application structure first. Redesign, editing, exports, uploads, backups, and DataSourceManager UI are deferred.

## Stage 3A Development Write-Mode Discipline

Development may enable write mode only on a safe local development data root, currently `/Users/hermes/LocalData/FedorinovRewards/Rewards`.

Production and owner data remain protected until backup, restore, and validation workflows are mature.

The full functional mirror should reproduce legacy write operations, but every write stage must use backup-first discipline. Future write routes must require explicit `WRITE_MODE=true`, use guarded write connections, and check that a recent backup exists before changing SQLite or media files.

Audit logging for future write actions should avoid personal data and write to local files outside Git.

## Windows Portable Preview First

The first owner Windows launch uses a portable ZIP, not an installer.

The package contains code, startup scripts, and documentation only. Owner data, SQLite databases, photos, backups, `.env`, `.venv`, legacy sources, reports, archives, and binaries remain outside the package.

Python 3.11+ is an acceptable prerequisite for the first preview. A dedicated installer, launcher, updater, or bundled runtime can be considered later after owner QA confirms the preview workflow.

Windows preview defaults stay read-only with `READ_ONLY=true` and `WRITE_MODE=false`. Temporary write-mode button checks require a backup first and must use local `.env` only.
