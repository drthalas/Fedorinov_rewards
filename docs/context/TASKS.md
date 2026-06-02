# Tasks

## Stage 2A

Status: implemented in the local repository.

Scope:

- Minimal read-only web mirror pages.
- Repository layer using SQLite `mode=ro`.
- Safe media endpoint with fallback image behavior.
- Dashboard, persons, person detail, photos, rewards, marks, guides, search, and health pages.

Remaining validation:

- Keep all future Stage 2B changes read-only until editing/backups are explicitly designed.

Bugfix status:

- Media resolver and template media URL generation fixed for POSIX and Windows-style photo paths.
- Media endpoint now handles HEAD checks and avoids hanging on unreadable local files.
- Minimal media resolver tests added.

Dev data stabilization:

- Desktop sample data can block on read in the current environment.
- Prefer `~/LocalData/FedorinovRewards/Rewards` as the stable non-Desktop dev data root when a readable local copy is available.
- Keep the stable copy outside Git and keep `.env` uncommitted.

## Backlog / Future

- Implement DataSourceManager.
- Implement Settings -> Data Source screen.
- Implement local config storage for selected data directory.
- Add validation report for connected database and media folders.
- Stage 2B: improve pagination, protected-field display controls, media diagnostics UI, and test coverage.
