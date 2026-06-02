# Fedorinov_rewards

Fedorinov_rewards is a new modernization project for the legacy Windows Rewards / "Nagrady" application. The first goal is to build a safe web mirror of the existing behavior before any functional improvements.

This repository contains only the new project skeleton, documentation, diagnostics, and a read-only backend prototype. Legacy application sources and real local data are not committed here.

## Safety Rules

- Do not commit SQLite databases, photos, PDFs, archives, EXE/DLL files, `.env`, tokens, or keys.
- Do not commit `Source/`, `SourceMark/`, `database/`, or `legacy/_external/`.
- Do not modify `/Users/hermes/Desktop/Rewards`.
- Do not run legacy `.exe` files.
- First-stage diagnostics and backend access are read-only.

## Local Data

Create `.env` from `.env.example` if needed:

```sh
cp .env.example .env
```

The expected local data location is:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards
```

Expected files and folders:

- `database/MyDatabase.sqlite`
- `Source/`
- `SourceMark/`
- `default/nofoto.jpg`
- `default/times.ttf`

## Legacy Sources

Legacy repositories are fetched into ignored directories:

```sh
scripts/fetch_legacy_sources.sh
```

The script clones:

- `https://github.com/erypalovyury/rewards`
- `https://github.com/erypalovyury/activation-rewards`

They are stored under `legacy/_external/` and must not be committed.

## Diagnostics

Run read-only database inspection:

```sh
python scripts/inspect_local_data.py
```

Run read-only media link inspection:

```sh
python scripts/check_media_links.py
```

The scripts do not print names, comments, links, or personal database records.

## Backend

Install backend dependencies:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
```

Run the local FastAPI backend:

```sh
scripts/run_dev.sh
```

The app starts on `127.0.0.1:8080` by default. The first stage is read-only and uses SQLite with `mode=ro`.

## Stage 2A Read-Only Mirror

The minimal web mirror is available at:

- `/` - dashboard and table counts
- `/persons` - awarded persons list
- `/persons?page=1&page_size=25` - awarded persons list with basic pagination
- `/persons/{id}` - awarded person card
- `/persons/{id}/photos` - person and reward photo gallery
- `/rewards/{id}` - reward card
- `/marks` - standalone marks list
- `/marks?page=1&page_size=25` - standalone marks list with basic pagination
- `/marks/{id}` - mark card
- `/guides` - read-only guide tree
- `/search` - simple search by name/title/number
- `/health` - environment diagnostics

Start the backend on the Mac mini:

```sh
cd ~/Projects/Fedorinov_Rewards/Fedorinov_rewards
scripts/run_dev.sh
```

The backend binds to `127.0.0.1:8080`.

Open it from a MacBook through an SSH tunnel:

```sh
ssh -N -L 8080:127.0.0.1:8080 hermes-mini
```

Then open:

```text
http://127.0.0.1:8080
```

The mirror is read-only. It must not modify `/Users/hermes/Desktop/Rewards`, write to SQLite, copy media files, or run legacy executables.

Stage 2B keeps the same read-only mirror and improves readability only: dates are shown as `DD.MM.YYYY`, prices as rubles, stock values as badges, guide sections are collapsible, and search results are limited to the first 25 items per group.
