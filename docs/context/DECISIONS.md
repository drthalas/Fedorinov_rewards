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
