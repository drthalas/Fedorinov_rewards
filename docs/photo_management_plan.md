# Photo Management Plan

Stage 3F adds safe photo viewing and development write-mode photo management for the legacy mirror. Real owner media remains local and must never be committed to Git.

## Storage Model

Existing photo fields store relative paths inside the local Rewards data folder:

- Person photos: `Source/{person_id}/...`
- Reward photos: `Source/{person_id}/{reward_id}/...`
- Mark photos: `SourceMark/{mark_id}/...`
- Fallback image: `default/nofoto.jpg`

The web UI serves media through `/media?path=...`. Absolute paths are not shown in templates, and the media resolver keeps path traversal protection enabled.

## Fields

Person fields:

- `person_foto` - Фото кавалера
- `main_foto` - Главное фото
- `rewards_foto` - Общее фото наград
- `book1_foto` - Фото наградной книжки, сторона 1
- `book2_foto` - Фото наградной книжки, сторона 2
- `card1_foto` - Фото учётной карточки, страница 1
- `card2_foto` - Фото учётной карточки, страница 2

Reward fields:

- `front_foto` - Фото награды: аверс
- `back_foto` - Фото награды: реверс
- `book1_foto` - Фото книжки, сторона 1
- `book2_foto` - Фото книжки, сторона 2
- `reward_list` - Наградной лист

Mark fields:

- `front_foto` - Фото знака: аверс
- `back_foto` - Фото знака: реверс
- `book1_foto` - Фото книжки, сторона 1
- `book2_foto` - Фото книжки, сторона 2

## Upload / Replace

Photo upload is available only when `WRITE_MODE=true`. In the working preview defaults, ordinary photo upload does not require a fresh backup before every save because `REQUIRE_BACKUP_BEFORE_WRITE=false`; regular backups are still recommended before serious work.

The upload endpoint accepts only approved entity types and photo fields. It accepts image files with these extensions:

- `.jpg`
- `.jpeg`
- `.png`
- `.webp`

The size limit is 25 MB. Uploaded files are saved with a generated safe filename based on the target field and a timestamp. Existing files are not overwritten.

After the file is saved, the matching SQLite photo field is updated with the new relative path. The audit log records the entity type, entity id, field name, and byte count without personal text values.

## Clear / Unlink

Photo clear uses `/photos/clear` and is available only in `WRITE_MODE=true` through the same guarded write pipeline.

Clear only removes the database field value. It does not delete the physical file from disk. Physical deletion is deferred until backup/restore validation and owner expectations are confirmed.

## Clipboard Paste

The “Вставить из буфера” control is active in write mode and uses the browser Clipboard API:

1. Read image blobs with `navigator.clipboard.read()`.
2. Convert the image blob to multipart upload data.
3. Send it to the same guarded `/photos/upload` endpoint.
4. Keep the same size/type validation and guarded write pipeline.

If the browser does not support image clipboard reads, or blocks clipboard access for the current local page, the UI shows a clear fallback message and the user can use the `+` file upload button. Localhost is generally treated as a secure context by modern browsers, but this must be confirmed during Windows owner QA.

## Person Folder Archive

The legacy rewards screen can open and archive the selected person's local folder:

- Folder: `Source/{person_id}` under `REWARDS_DATA_DIR`.
- Open folder uses the local OS file manager and never accepts arbitrary paths from the browser.
- Archive creates `REWARDS_DATA_DIR/archives/<fio>_<id>_YYYYMMDD_HHMMSS.zip`.
- Only the selected person's folder is archived. The database, `Source` root, `SourceMark`, backups, logs, `.env`, nested ZIP files, EXE, and DLL files are excluded.
- Source files are not deleted.

## Backup Rule

All photo write operations require the same safety discipline as CRUD:

- Work only on a safe local dev data root.
- Keep regular backups before serious work.
- Disable editing with `READ_ONLY=true` and `WRITE_MODE=false` when needed.
- Never commit database files, `Source/`, `SourceMark/`, generated backups, or real photos.
