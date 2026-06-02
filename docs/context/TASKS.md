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

Status: next.

Scope:

- UX and readability polish for the read-only mirror.
- Keep Stage 2B read-only.

Editing status:

- Blocked until backup, migration, and editing architecture is designed.

## Backlog / Future

- Implement DataSourceManager.
- Implement Settings -> Data Source screen.
- Implement local config storage for selected data directory.
- Add validation report for connected database and media folders.
- Improve pagination, protected-field display controls, media diagnostics UI, and test coverage.
