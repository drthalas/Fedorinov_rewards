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

After checking the artifacts, do not publish yet. Complete the Tier 4 Windows VM gate and the manual physical Windows Owner gate described below. Only after Owner PASS and separate publication authorization, run the workflow again with:

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

## Windows updater gates

Every Tier 4 updater/recovery release uses two different Windows gates:

1. **Windows VM automated gate.** Codex runs the complete exact-user updater/recovery flow on the existing mutable Sergey fixture. It must verify package/SHA, BAT parsing, startup/reboot, backup, data preservation, strict runtime identity, single backend, repeated launch, unrelated-port protection, forced failure and rollback. The exact cycle count and any clean-baseline restore are defined by the release issue.
2. **Physical Windows manual Owner gate.** Owner starts the current standard BAT, sees the exact candidate, clicks `Обновить`, and follows the same visible flow available to Sergey. Codex prepares the isolated candidate channel and collects evidence after Owner action, but does not prelaunch the candidate, replace files manually, or duplicate the complete automated updater flow on physical Windows.

Do not copy or reset the full Sergey dataset for routine release preparation. The permanent VM fixture remains mutable; restore it only when it is broken, a clean baseline is explicitly required, or the exact updater/recovery scenario requires restore evidence.

Do not publish GitHub Release, production `latest.json`, or Telegram before the physical Owner gate passes and a separate release command authorizes publication. If physical Windows is unavailable, report the unexecuted gate and residual risk; do not silently replace it with another automated run.

## Telegram release notification

After a successful publication, prepare the Telegram release notification on the Mac mini. The Telegram bot token stays local and is not stored in GitHub Actions.

Before sending, review `release_notes/X.Y.Z.md` and make sure it covers all user-visible release changes, not only the last technical task. The notification should mention the real owner-facing improvements in plain language.

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

Manual local publication is still available after the Tier 4 VM gate, physical Owner PASS, and separate publication authorization, but GitHub Actions is preferred. Local publication uses local GitHub CLI authentication on the developer machine:

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
