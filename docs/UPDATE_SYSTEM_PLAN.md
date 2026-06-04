# Update System Plan

## Stage 4A: public update check

The application checks a public GitHub Release manifest:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

No GitHub token is required. The manifest contains only version metadata, a public ZIP URL, SHA256, release date, and user-facing notes.

Stage 4A does not download or install updates. It only shows whether a newer version exists.

## Stage 4A.1: GitHub Release publishing

Release packaging creates two generated assets:

- `dist/FedorinovRewards_WebPreview_vX.Y.Z.zip`
- `dist/latest.json`

The manifest points to the public ZIP asset in the matching GitHub Release and includes SHA256 plus user-facing release notes.

Publication uses the developer machine's local `gh` CLI authentication. GitHub tokens are not stored in the repository and are not needed on the owner's computer.

See `docs/RELEASE_PROCESS.md` for build, safety check, dry-run, and publication commands.

## Stage 4B: one-click updater

Implemented one-click update flow:

1. Download the preview ZIP into a temporary folder.
2. Verify the downloaded ZIP SHA256 against `latest.json`.
3. Create a backup of the current application folder.
4. Preserve local configuration files, especially `.env`.
5. Replace only application code, templates, scripts, and documentation.
6. Show a clear result telling the user to restart the application manually.

Stage 4B.1 adds visible progress while the update runs:

- `checking`: проверяем новую версию;
- `downloading`: скачиваем обновление;
- `verifying`: проверяем файл;
- `backing_up`: создаём резервную копию;
- `installing`: устанавливаем обновление;
- `success` / `error`: показываем результат.

The current status is stored locally in `updates/update_status.json` and exposed through `GET /updates/status`. A second update request is blocked while one update is already running.

Automatic restart is deferred. The owner should close the `start_windows.bat` window and start it again after a successful update.

If file replacement fails, the updater attempts to restore files from the application backup and returns a clear error.

The updater has two entry points:

- UI: `О программе -> Проверить обновления -> Обновить`
- CLI: `python3 scripts/apply_update.py --dry-run` or `python3 scripts/apply_update.py --apply`

## Data safety

The updater must not touch:

- `database/`
- `Source/`
- `SourceMark/`
- `default/`
- `.env`
- `.env.daily-report`
- backups
- owner/user data folders
- generated local logs
- `updates/`

Owner data remains local and separate from application code.

## Release notifications

Release Telegram notifications are generated from `latest.json` or `release_notes/X.Y.Z.md` and sent through the same local colorizer/SAVBot setup as daily reports.

- Sergey receives the main notification.
- Alexander receives a copy.
- Dry-run is required before real sending.
- Real sending requires separate confirmation.
- Telegram tokens and real chat ids stay local and ignored by Git.
