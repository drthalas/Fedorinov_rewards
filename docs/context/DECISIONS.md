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

The full functional mirror should reproduce legacy write operations through guarded write routes. Early write stages used backup-first discipline for every write; after owner QA passed, ordinary writes may run with `REQUIRE_BACKUP_BEFORE_WRITE=false`, while dangerous actions keep separate backup-sensitive protection.

Audit logging for future write actions should avoid personal data and write to local files outside Git.

## Windows Portable Preview First

The first owner Windows launch uses a portable ZIP, not an installer.

The package contains code, startup scripts, and documentation only. Owner data, SQLite databases, photos, backups, `.env`, `.venv`, legacy sources, reports, archives, and binaries remain outside the package.

Python 3.11+ is an acceptable prerequisite for the first preview. A dedicated installer, launcher, updater, or bundled runtime can be considered later after owner QA confirms the preview workflow.

Windows preview originally started read-only. After the legacy UI became the primary workflow and owner QA passed, the preview defaults moved to visible working buttons with ordinary edit saves enabled.

## Legacy UI Primary Workflow

The legacy desktop mirror is now the primary user interface. Opening `/` redirects to `/legacy?tab=rewards`.

The existing standalone pages such as `/persons`, `/marks`, `/search`, `/dashboard`, and detail pages remain available as supporting and technical routes, but the owner-facing workflow should start from `/legacy`.

The Windows portable preview defaults to editable working mode with `READ_ONLY=false` and `WRITE_MODE=true`.

After owner QA passed, ordinary write operations no longer require a fresh backup before every save: `REQUIRE_BACKUP_BEFORE_WRITE=false`.

Dangerous actions remain separately protected with `REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS=true`, explicit confirmations, guarded write routes, and audit logging. This covers delete person/reward/mark/guide actions and future high-risk operations.

Forms opened from `/legacy` must carry a sanitized internal `return_to` URL so successful create/update/delete actions return to the correct legacy tab and selected record.

## Daily Telegram Reports

Daily progress reports are sent through the existing colorizer/SAVBot Telegram bot instead of creating a separate bot.

The report is addressed to Sergey as the primary recipient at 09:00, with the same report copied to Alexander for quality control.

Report text uses the public project name "Награды и награждённые" and avoids internal implementation terms, local paths, database contents, photos, tokens, and personal data.

The Telegram bot token, real chat ids, real launchd plist, `.env.daily-report`, and send logs remain local and are not committed. The first real send to Sergey requires separate confirmation before enabling primary delivery.

Scheduled delivery must use `Europe/Moscow` explicitly. `launchd` uses the Mac mini local timezone, so it should only wake the script at a regular interval; `scripts/send_daily_report.py --scheduled` decides whether current Moscow time is inside the configured 09:00 send window and skips duplicates using the local send log.

## Person Biography Field

The short biography is stored as a separate `person.biography` SQLite column instead of overloading the existing `person.comment` field.

The column is added by an idempotent migration script. The migration supports dry-run, requires explicit apply, and remains a dangerous/schema action that requires write mode plus a fresh backup when the guard is enabled.

Application reads tolerate databases that do not yet have the column, but saving biography text requires the migration to have been applied.

## Public GitHub Release Update Checks

Application updates are checked through a public GitHub Release manifest at:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

No GitHub token is needed or stored on the owner's computer. The update checker only reads public version metadata and does not download or install ZIP files in Stage 4A.

The manifest must include version, public download URL, SHA256, release date, and user-facing notes. Owner data remains separate from application code and must not be touched by update checks or future update installation.

One-click installation is deferred to Stage 4B and must preserve `.env`, avoid database/media folders, validate SHA256, create an application backup, and support rollback.

## GitHub Release Package Publishing

Release packages are published through public GitHub Releases in `drthalas/Fedorinov_rewards`.

Each release should include:

- versioned Windows portable ZIP;
- `latest.json` manifest.

`latest.json` is a generated release asset, not a committed real manifest. It must contain the public ZIP URL, SHA256, version, release date, and owner-facing notes.

GitHub tokens are never committed. Publishing can use local `gh` CLI authentication on the developer machine, while owner-side update checks remain token-free.

Owner data, `.env`, database, media folders, backups, logs, and generated reports are not included in release assets.

## Manual GitHub Actions Release Workflow

GitHub Releases are published manually through a `workflow_dispatch` GitHub Actions workflow, not automatically on push.

The workflow has a dry-run mode (`publish=false`) that builds and uploads artifacts without creating a release. Real publication requires `publish=true` and uses the standard GitHub Actions `GITHUB_TOKEN` inside GitHub Actions.

The workflow validates the requested release version against `backend/app/version.py`, refuses missing release notes, and refuses to overwrite an existing GitHub Release.

Owner-side update checks still do not require any token.

## One-Click Updater Safety

The application may install public GitHub Release ZIP updates only through an explicit POST action with user confirmation.

The updater must verify SHA256 from `latest.json`, validate ZIP structure, reject forbidden paths, create an application backup, preserve `.env`, and copy only allowed application files.

The updater must not touch owner data, SQLite databases, `Source`, `SourceMark`, `default`, backups, logs, `.venv`, local reports, or local update folders.

Automatic restart is deferred. After a successful update, the user closes the launch window and starts the application again.

The update UI should show progress while an update is running. Progress is stored locally in `updates/update_status.json` and exposed through `/updates/status`; this ignored local status file must not contain owner data.

Release Telegram notifications are sent from the Mac mini through the existing colorizer/SAVBot setup after separate confirmation. GitHub Actions can show the local command to run, but it does not send Telegram messages because the Telegram token stays local.
