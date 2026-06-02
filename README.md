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
REWARDS_DATA_DIR=/Users/hermes/Desktop/Rewards
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
