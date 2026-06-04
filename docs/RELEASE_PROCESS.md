# Release Process

## Overview

Each public GitHub Release should contain two assets:

- `FedorinovRewards_WebPreview_vX.Y.Z.zip`
- `latest.json`

The application checks the latest release manifest at:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

Owner-side update checks do not require a GitHub token.

## Prepare a version

1. Update the version in `backend/app/version.py`.
2. Add human-readable release notes in `release_notes/X.Y.Z.md`.
3. Keep notes clear for the owner. Avoid internal terms and local paths.

Check the current version:

```sh
python3 scripts/print_version.py
```

## Build release assets

```sh
python3 scripts/build_release_package.py
```

Expected generated files:

```text
dist/FedorinovRewards_WebPreview_vX.Y.Z.zip
dist/latest.json
```

`latest.json` contains version, release date, public ZIP URL, SHA256, and notes.

## Safety check

```sh
python3 scripts/check_package_safety.py dist/FedorinovRewards_WebPreview_vX.Y.Z.zip
```

The ZIP must not contain:

- `.env`
- `.venv`
- `database/`
- `Source/`
- `SourceMark/`
- backups
- logs
- `docs/reports/`
- `legacy/_external/`
- photos
- PDFs
- EXE/DLL files
- nested ZIP files

## Dry-run publication

### GitHub Actions

Recommended release path:

1. Push the committed version to `main`.
2. Open GitHub -> Actions -> Manual Release.
3. Click `Run workflow`.
4. Enter the version from `backend/app/version.py`.
5. Run first with:

```text
publish=false
```

The workflow builds:

```text
dist/FedorinovRewards_WebPreview_vX.Y.Z.zip
dist/latest.json
```

and uploads both files as workflow artifacts without creating a GitHub Release.

After checking the artifacts, run the workflow again with:

```text
publish=true
```

The workflow creates:

```text
tag: vX.Y.Z
title: Награды и награждённые vX.Y.Z
```

and uploads the ZIP plus `latest.json` as release assets. The workflow refuses to overwrite an existing release.

The workflow uses the standard GitHub Actions `GITHUB_TOKEN` only inside GitHub Actions. The owner's computer does not need a GitHub token.

After publication, the application checks:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

After the owner opens `О программе` and clicks `Проверить обновления`, the app can show the new version. If the new version is newer than the installed version, the owner can click `Обновить`. The updater downloads the ZIP from the public release, checks SHA256, creates an application backup, preserves `.env`, replaces application files, and asks the owner to restart the app manually.

### Local dry-run

```sh
python3 scripts/publish_github_release.py --dry-run
```

Dry-run prints the tag, title, notes path, and assets without creating a GitHub Release.

## Local publish release

Manual local publication is still available, but GitHub Actions is preferred. Local publication uses local GitHub CLI authentication on the developer machine:

```sh
python3 scripts/publish_github_release.py
```

If `gh` is missing or not authenticated, run `gh auth login` locally. Do not paste or commit GitHub tokens into project files.

The release tag is:

```text
vX.Y.Z
```

The release title is:

```text
Награды и награждённые vX.Y.Z
```

## Data safety

Release assets contain application code only. They must not include owner data.

Updates and release packaging must not touch:

- `database/`
- `Source/`
- `SourceMark/`
- `default/`
- `.env`
- backups
- owner data folders
