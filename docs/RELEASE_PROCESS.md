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

## Exact release candidate gate

Development Windows VM gates are defined by the task tier and remain part of the
feature workflow. Once the change has passed its required VM checks and physical
Owner product acceptance, do not repeat the full VM updater gate by default at
the release stage.

After the accepted integration is merged:

1. Record the accepted integration HEAD and verify its ancestry in `main`.
2. Build one exact versioned candidate from merged `main`.
3. Run the required automated release suite, manifest/SHA checks, package safety,
   and repository parity checks.
4. Prepare physical Windows from the current public production version and its
   ordinary `start_windows.bat`.
5. Use the UI updater to install the exact merged candidate and verify its SHA,
   backup, install, restart, version/runtime identity, DB/media preservation, one
   app-owned backend, and repeated BAT launch.
6. Run forced-failure and rollback at this stage only when updater/recovery code
   changed or the Owner explicitly requires that gate.
7. Publish only after the physical exact-candidate gate passes and publication is
   authorized.

Pre-merge physical product acceptance does not replace this post-merge package
gate. The physical gate may be performed by the Owner or by Codex with explicit
authorization for that release.

The physical host keeps `Fedorinov Rewards - Public Current` on the Owner's
Desktop as the canonical installation of the latest published production
version. A candidate always uses a separate task-owned run directory and must
not overwrite this folder before publication. After public ZIP and manifest
parity are verified, refresh the Desktop baseline from that exact public
artifact, update its version/SHA marker, preserve its external data pointers,
and verify the ordinary `start_windows.bat` again. Do not copy Sergey-full media
into the application folder.

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

After the owner opens `О программе` and clicks `Проверить обновления`, the app can show the new version. If the new version is newer than the installed version, the owner can click `Обновить`. The separate bootstrap downloads and verifies the ZIP, creates an application backup, stops only identity-confirmed application backends, preserves `.env`, replaces application files, and starts exactly one verified backend from the updated install root.

Before publishing a release that contains runtime-lifecycle changes, extend the physical packaged gate to prove that old PIDs are dead, one backend remains, `/runtime/identity` matches the release version and install root, a repeated launcher does not create a duplicate, an unrelated port owner is untouched, and rollback restores one valid old backend.

## Telegram release notification

After a successful publication, prepare the Telegram release notification on the Mac mini. The Telegram bot token stays local and is not stored in GitHub Actions.

Before sending, review `release_notes/X.Y.Z.md` and make sure it covers all user-visible release changes, not only the last technical task. The notification should mention the real owner-facing improvements in plain language.

The canonical update instructions come from
`scripts/generate_release_telegram_message.py`. The normal post-update path is
automatic restart. Mention `start_windows.bat` only as a fallback when the
application does not reopen automatically; never require a manual BAT restart
after every successful update.

First preview the message:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --dry-run
```

After separate confirmation, send a test only to Alexander:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --send-test-to-copy-only
```

After separate confirmation for the real release notification, send to Sergey and copy Alexander:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --send
```

If an incomplete notification was already sent, send a corrected follow-up only after explicit confirmation:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --dry-run --correction
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --send --correction
```

Do not send release notifications automatically from GitHub Actions. The workflow can print a local command reminder, but real Telegram messages are sent only from the Mac mini after confirmation.

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
