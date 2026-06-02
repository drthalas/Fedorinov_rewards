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

The application code and user data are separate. The `/Users/hermes/Desktop/Rewards` path is only the current development sample data location, not a permanent production path.

During the first stages, the application can read `REWARDS_DATA_DIR` from `.env`. The code should stay structured so this configuration can later be replaced by a DataSourceManager without rewriting repositories, media handling, or routes.

Expected data layout:

- `database/MyDatabase.sqlite`
- `Source/`
- `SourceMark/`
- `default/`

## DataSourceManager

Future local installations need a DataSourceManager component for connecting the owner's real local Rewards data folder.

Responsibilities:

- store the current path to the local data folder;
- validate the folder structure;
- check `database/MyDatabase.sqlite`;
- check `Source/`, `SourceMark/`, and `default/`;
- open SQLite only in read-only mode during early stages;
- show the user the current connection status;
- save the selected path in local configuration;
- keep database and photo files local;
- never upload, sync, or commit user data.

The owner's production database and photos remain on the owner's computer. GitHub stores code and documentation only.

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
