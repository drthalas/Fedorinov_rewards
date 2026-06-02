# Changelog

## Stage 2A QA Accepted

- Hermes QA passed for Stage 2A.
- All target pages returned HTTP 200.
- Broken images: 0.
- Real media displayed from the stable dev data root.
- Stable dev data root: `/Users/hermes/LocalData/FedorinovRewards/Rewards`.

## Dev Data Root Stabilization

- Documented that Desktop-hosted sample data can block on read in the current environment.
- Recommended `~/LocalData/FedorinovRewards/Rewards` as the stable non-Desktop development data root when a readable local copy is available.
- Kept real data, `.env`, and copied media/database files outside Git.

## Stage 2A Media Resolver Bugfix

- Fixed media URL generation by centralizing `/media` links in a Jinja helper.
- Improved media path normalization for URL-decoded paths, Windows backslashes, allowed roots, and absolute paths inside `REWARDS_DATA_DIR`.
- Added `HEAD /media` support for diagnostics.
- Added timeout-based media reads so unreadable local files fall back instead of hanging image requests.
- Added minimal tests for the read-only media resolver.

## Stage 2A Minimal Read-Only Web Mirror

- Added FastAPI routers for dashboard, persons, rewards, marks, guides, search, health, and media.
- Added read-only sqlite3 repository modules.
- Added safe media resolver and `/media` endpoint with `default/nofoto.jpg` fallback.
- Added Jinja2 templates and simple CSS for the legacy mirror pages.
- Kept SQLite access read-only and local data outside Git.
