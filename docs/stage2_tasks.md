# Stage 2 Tasks

Stage 2 implements a read-only web mirror. Each task must preserve `READ_ONLY=true`, SQLite `mode=ro`, and safe local media access.

## Repositories Layer

- Goal: Add Python repository functions for person, reward, mark, guide, and aggregate reads.
- Files that can change: `backend/app/db.py`, new `backend/app/repositories.py`, focused tests.
- Done when: Queries return typed dictionaries/models without writing to SQLite.
- Do not: Add insert/update/delete, reuse legacy SQL string concatenation, print personal data in logs.

## Media Path Resolver

- Goal: Normalize media paths from database values and constrain them to `REWARDS_DATA_DIR`.
- Files that can change: new `backend/app/media.py`, tests.
- Done when: Relative, Windows-style, and empty paths resolve safely or return fallback metadata.
- Do not: Serve arbitrary absolute paths, copy files, modify media folders.

## Safe Media Endpoint

- Goal: Serve local images through a controlled endpoint.
- Files that can change: `backend/app/main.py`, `backend/app/media.py`, tests.
- Done when: Existing allowed files render and missing files fall back to `default/nofoto.jpg`.
- Do not: Expose raw filesystem paths, allow path traversal, commit images.

## Templates Base Layout

- Goal: Add shared server-rendered template shell.
- Files that can change: new `backend/app/templates/`, `backend/app/main.py`, optional static CSS.
- Done when: All pages share navigation and readable local-first layout.
- Do not: Build a marketing page or add unrelated frontend framework.

## Dashboard

- Goal: Implement `/` dashboard with safe counts and environment status.
- Files that can change: `backend/app/main.py`, repositories, templates, tests.
- Done when: Counts match diagnostic scripts and no personal fields are displayed.
- Do not: Show names, comments, links, or raw paths.

## Persons List

- Goal: Implement `/persons`.
- Files that can change: routes, repositories, templates, tests.
- Done when: List displays ids, rank labels, reward counts, and safe media indicators.
- Do not: Add editing controls or expose full personal details outside protected UI.

## Person Details

- Goal: Implement `/persons/{id}`.
- Files that can change: routes, repositories, templates, tests.
- Done when: Detail shows safe person summary, related rewards, and protected metadata section.
- Do not: Mutate `person`, open local folders, or show raw paths.

## Rewards List and Details

- Goal: Implement reward views for person rewards and `/rewards/{id}`.
- Files that can change: routes, repositories, templates, tests.
- Done when: Classification joins resolve and media presence is visible.
- Do not: Implement reward add/edit/delete or duplicate-number writes.

## Marks List and Details

- Goal: Implement `/marks` and `/marks/{id}`.
- Files that can change: routes, repositories, templates, tests.
- Done when: Standalone marks can be browsed and opened read-only.
- Do not: Add mark editing, media upload, or PDF export.

## Guides Tree

- Goal: Implement `/guides`.
- Files that can change: routes, repositories, templates, tests.
- Done when: `guide` and `guide_lev_0` through `guide_lev_4` display as a navigable read-only tree.
- Do not: Add guide mutation or backfill behavior.

## Search

- Goal: Implement `/search` across persons, rewards, and marks.
- Files that can change: routes, repositories, templates, tests.
- Done when: Search returns safe result rows and links to detail pages.
- Do not: Log raw queries containing personal data or show comments/links by default.

## Photo Fallback `nofoto`

- Goal: Use `default/nofoto.jpg` when expected media is absent.
- Files that can change: media resolver, media endpoint, templates, tests.
- Done when: Missing media does not break pages and fallback is contained within `REWARDS_DATA_DIR`.
- Do not: Commit fallback image from local data.

## Tests

- Goal: Add tests for read-only DB connections, repositories, media resolver, and health.
- Files that can change: new `tests/`, `backend/requirements.txt` if test dependencies are needed.
- Done when: Tests pass without touching real data or writing to SQLite.
- Do not: Include real database rows, photos, secrets, or generated reports.

## Health Checks

- Goal: Extend `/health` with table availability and media root checks.
- Files that can change: `backend/app/main.py`, config, repositories, tests.
- Done when: Health stays safe and reports only booleans/counts.
- Do not: Print table rows, names, comments, links, or raw missing photo names.

## README Update

- Goal: Document Stage 2 local run and read-only mirror usage.
- Files that can change: `README.md`, related docs.
- Done when: A developer can run diagnostics and the backend without risking data writes.
- Do not: Add instructions that copy local data into the repo or push without confirmation.
