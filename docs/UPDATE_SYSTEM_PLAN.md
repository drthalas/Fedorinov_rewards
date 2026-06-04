# Update System Plan

## Stage 4A: public update check

The application checks a public GitHub Release manifest:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

No GitHub token is required. The manifest contains only version metadata, a public ZIP URL, SHA256, release date, and user-facing notes.

Stage 4A does not download or install updates. It only shows whether a newer version exists.

## Stage 4B: one-click updater

Future one-click update flow:

1. Download the preview ZIP into a temporary folder.
2. Verify the downloaded ZIP SHA256 against `latest.json`.
3. Create a backup of the current application folder.
4. Preserve local configuration files, especially `.env`.
5. Replace only application code, templates, scripts, and documentation.
6. Restart the local application.
7. Roll back to the previous application folder if update validation fails.

## Data safety

The updater must not touch:

- `database/`
- `Source/`
- `SourceMark/`
- `default/`
- `.env`
- backups
- owner/user data folders
- generated local logs

Owner data remains local and separate from application code.
