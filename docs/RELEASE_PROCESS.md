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

## Owner candidate stage

После accepted product/VM gate release-candidate stage работает из exact accepted
feature/release HEAD. До Owner updater/product PASS этот HEAD не интегрируется в
`main`: `main` продолжает представлять последнюю Owner-accepted production line.

На candidate branch:

1. Зафиксировать exact accepted HEAD и ancestry.
2. Подготовить next patch version и release metadata.
3. Собрать exact ZIP и выполнить только необходимые version/manifest/SHA/package/parity/static checks.
4. Не повторять full suite, Windows VM или product regression без конкретного mismatch/blocker.
5. Опубликовать exact ZIP в постоянный LAN-only Owner channel на Mac mini:

```sh
python3 scripts/publish_owner_candidate_channel.py \
  --artifact dist/FedorinovRewards_WebPreview_vX.Y.Z.zip \
  --manifest dist/latest.json \
  --candidate-commit EXACT_ACCEPTED_FEATURE_OR_RELEASE_HEAD \
  --candidate-version X.Y.Z \
  --candidate-sha256 EXACT_SHA256 \
  --candidate-size EXACT_SIZE \
  --public-version CURRENT_PUBLIC_VERSION
```

Этот этап не подключается к physical Windows, не меняет его `.env`, не запускает
runtime/Edge и не проверяет updater visibility. Permanent Owner `Public Current`
настраивается на stable endpoint один раз по отдельному разрешению. См.
`docs/OWNER_CANDIDATE_CHANNEL.md`.

Если Owner отклоняет candidate, исправления продолжаются вне `main`, после чего
публикуется новый exact candidate. Revert rejected candidate в `main` не нужен.

## Owner PASS, controlled merge and publication

Только после manual Owner updater/product PASS и отдельного разрешения:

1. Интегрировать exact accepted candidate HEAD в `main` через разрешённый PR/merge/FF.
2. Проверить ancestry, local/remote parity и совпадение resulting tree с accepted candidate tree.
3. При conflict, tree drift или artifact mismatch остановиться; не публиковать и не пересобирать молча.
4. Не повторять full suite, Windows VM, physical updater или product acceptance, уже пройденные exact candidate.
5. Использовать тот же проверенный artifact без пересборки для tag/GitHub Release, production `latest.json`, public byte/SHA parity и Telegram.

Это короткая publication stage по ALE-379. Maintenance permanent `Public Current`
не блокирует publication и оформляется отдельно при необходимости.

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

Этот раздел применяется только после Owner PASS и controlled integration exact
candidate в `main`. Recommended publication path:

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

Before publishing a release that contains runtime-lifecycle changes, run the packaged test on native Windows. The gate must prove that old PIDs are dead, one backend remains, `/runtime/identity` matches the release version and install root, a repeated launcher does not create a duplicate, an unrelated port owner is untouched, and rollback restores one valid old backend.

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
