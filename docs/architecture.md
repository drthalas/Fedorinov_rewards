# Architecture

The target architecture is a local-first web application for modernizing the Rewards / "Nagrady" workflow.

## First Stage

- FastAPI backend.
- SQLite opened in read-only mode.
- Local browser interface served from the backend.
- Diagnostics for database tables and media links.
- No database writes.
- No modification of local media files.

## Backend

The backend is responsible for configuration, read-only database access, diagnostics, and web routes. SQLite must be opened through a URI with `mode=ro` during the first stage.

## Local Data

The application reads from `REWARDS_DATA_DIR`, expected to point to `/Users/hermes/Desktop/Rewards` during local testing.

Expected data layout:

- `database/MyDatabase.sqlite`
- `Source/`
- `SourceMark/`
- `default/`

## Media Service

Future media service routes should serve and validate files from `Source/`, `SourceMark/`, and `default/` without exposing arbitrary filesystem paths.

## Web Interface

The first web layer can use server-rendered templates to mirror the old interface. A fuller frontend can be introduced later when the legacy behavior and data model are mapped.

## Future Capabilities

Planned later stages include:

- backup workflows;
- schema migrations;
- editing with explicit safeguards;
- PDF export;
- improved search and gallery views;
- local deployment;
- optional tunnel access;
- AI-assisted features.

Data remains local. Code and documentation evolve through GitHub.
