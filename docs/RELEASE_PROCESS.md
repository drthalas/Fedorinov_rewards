# Release Process

Обязательный порядок тестовых контуров и pre-publication policy определены в
[`docs/testing/RELEASE_GATE_WORKFLOW.md`](testing/RELEASE_GATE_WORKFLOW.md).

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

Record the candidate filename, release commit, byte size, and SHA256 before
transferring it to the Physical Windows Gate. Publication must use those exact
accepted bytes.

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

Run the applicable Mac/Linux and Windows VM gates before preparing the final
candidate. After package safety, test the exact candidate on the Physical
Windows Gate before creating a public tag, GitHub Release, `latest.json`, or
Telegram notification.

The physical gate covers real Explorer/double-click behavior, the normal BAT,
browser UX, updater/recovery, data fingerprints, single-backend identity, and
rollback according to release scope. A VM PASS does not replace this gate.

### GitHub Actions

The existing workflow builds fresh bytes on every invocation. A separate
`publish=false` run followed by `publish=true` is eligible only when SHA256
evidence proves that the publish run produced the exact artifact already
accepted on the physical gate. Do not assume reproducibility.

If exact byte parity cannot be established, use the local path that publishes
the already accepted `dist` artifact or stop and create a pipeline follow-up
issue. Do not publish first to make the artifact available for testing.

GitHub Actions path:

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

Before every publication, run the exact candidate through the required Physical
Windows Gate. Scope determines the depth, but updater/recovery or
runtime-lifecycle changes must prove that old PIDs are dead, one backend remains,
`/runtime/identity` matches the release version and install root, a repeated
launcher does not create a duplicate, an unrelated port owner is untouched, and
rollback restores one valid old backend.

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

Manual local publication uses local GitHub CLI authentication on the developer
machine:

```sh
python3 scripts/publish_github_release.py
```

For an exact candidate accepted before publication, this local path is the
current usable path when it publishes the same verified files from `dist`.

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
