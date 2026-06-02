# Changelog

## Stage 2A Minimal Read-Only Web Mirror

- Added FastAPI routers for dashboard, persons, rewards, marks, guides, search, health, and media.
- Added read-only sqlite3 repository modules.
- Added safe media resolver and `/media` endpoint with `default/nofoto.jpg` fallback.
- Added Jinja2 templates and simple CSS for the legacy mirror pages.
- Kept SQLite access read-only and local data outside Git.
