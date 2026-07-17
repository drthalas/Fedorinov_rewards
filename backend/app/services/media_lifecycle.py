from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote

from ..config import Settings
from ..db import open_write_connection
from .audit import log_action
from .write_guard import ensure_write_allowed


MANAGED_IMAGE_ROOTS = frozenset({"Source", "SourceMark", "GuideImages"})
MANAGED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


class MediaLifecycleError(ValueError):
    pass


@dataclass(frozen=True)
class MediaReferenceField:
    table: str
    column: str


@dataclass(frozen=True)
class MediaReferenceExclusion:
    table: str
    row_id: int


@dataclass(frozen=True)
class MediaCleanupResult:
    status: str
    path: str | None = None
    reference_count: int = 0
    error: str | None = None

    @property
    def warning_required(self) -> bool:
        return self.status in {"blocked", "failed"}


REFERENCE_FIELDS = (
    *(MediaReferenceField("person", field) for field in (
        "person_foto",
        "main_foto",
        "rewards_foto",
        "book1_foto",
        "book2_foto",
        "card1_foto",
        "card2_foto",
    )),
    *(MediaReferenceField("rewards", field) for field in (
        "front_foto",
        "back_foto",
        "book1_foto",
        "book2_foto",
        "reward_list",
    )),
    *(MediaReferenceField("mark", field) for field in (
        "front_foto",
        "back_foto",
        "book1_foto",
        "book2_foto",
    )),
    MediaReferenceField("guide", "image_path"),
    *(MediaReferenceField(f"guide_lev_{level}", "image_path") for level in range(5)),
    MediaReferenceField("person_media", "file_path"),
)


def _fully_unquote(value: str) -> str:
    decoded = value
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def normalize_managed_image_path(
    settings: Settings,
    raw_path: object,
    *,
    allowed_roots: frozenset[str] = MANAGED_IMAGE_ROOTS,
) -> str:
    if not isinstance(raw_path, str):
        raise MediaLifecycleError("Некорректный путь изображения.")
    value = _fully_unquote(raw_path).strip().replace("\\", "/")
    if not value or "\x00" in value:
        raise MediaLifecycleError("Некорректный путь изображения.")
    windows_path = PureWindowsPath(value)
    candidate = Path(value)
    if windows_path.drive or value.startswith("//"):
        raise MediaLifecycleError("Абсолютный или сетевой путь изображения запрещён.")

    if candidate.is_absolute():
        try:
            candidate = candidate.resolve().relative_to(settings.rewards_data_dir.resolve())
        except ValueError as exc:
            raise MediaLifecycleError("Изображение находится вне каталога данных.") from exc

    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise MediaLifecycleError("Недопустимый путь изображения.")
    if len(candidate.parts) < 2 or candidate.parts[0] not in allowed_roots:
        raise MediaLifecycleError("Изображение находится вне разрешённого системного каталога.")
    if candidate.suffix.lower() not in MANAGED_IMAGE_EXTENSIONS:
        raise MediaLifecycleError("Недопустимый тип управляемого изображения.")

    relative_path = candidate.as_posix()
    root = (settings.rewards_data_dir / candidate.parts[0]).resolve()
    lexical_target = settings.rewards_data_dir / candidate
    current = settings.rewards_data_dir.resolve()
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise MediaLifecycleError("Символические ссылки в управляемом media-пути запрещены.")
    target = lexical_target.resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise MediaLifecycleError("Изображение находится вне разрешённого системного каталога.") from exc
    return relative_path


def _available_reference_fields(connection) -> tuple[MediaReferenceField, ...]:
    tables = {
        str(row["name"])
        for row in connection.execute("select name from sqlite_master where type = 'table'").fetchall()
    }
    available: list[MediaReferenceField] = []
    columns_by_table: dict[str, set[str]] = {}
    for field in REFERENCE_FIELDS:
        if field.table not in tables:
            continue
        columns = columns_by_table.get(field.table)
        if columns is None:
            columns = {
                str(row["name"])
                for row in connection.execute(f"pragma table_info({field.table})").fetchall()
            }
            columns_by_table[field.table] = columns
        if field.column in columns:
            available.append(field)
    return tuple(available)


def managed_image_reference_count_in_connection(
    connection,
    settings: Settings,
    raw_path: object,
    *,
    excluded_rows: tuple[MediaReferenceExclusion, ...] = (),
) -> int:
    normalized_path = normalize_managed_image_path(settings, raw_path)
    excluded = {(item.table, int(item.row_id)) for item in excluded_rows}
    count = 0
    for field in _available_reference_fields(connection):
        columns = {
            str(row["name"])
            for row in connection.execute(f"pragma table_info({field.table})").fetchall()
        }
        if "id" not in columns:
            continue
        rows = connection.execute(
            f"select id as row_id, {field.column} as media_path from {field.table} "
            f"where {field.column} is not null and trim({field.column}) != ''"
        ).fetchall()
        for row in rows:
            if (field.table, int(row["row_id"])) in excluded:
                continue
            try:
                candidate = normalize_managed_image_path(settings, row["media_path"])
            except MediaLifecycleError:
                continue
            if candidate == normalized_path:
                count += 1
    return count


def _reference_count(connection, settings: Settings, normalized_path: str) -> int:
    return managed_image_reference_count_in_connection(connection, settings, normalized_path)


def managed_image_reference_count(settings: Settings, raw_path: object) -> int:
    normalized_path = normalize_managed_image_path(settings, raw_path)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        connection.execute("begin immediate")
        try:
            count = _reference_count(connection, settings, normalized_path)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return count


def cleanup_unreferenced_image(
    settings: Settings,
    raw_path: object,
    *,
    allowed_roots: frozenset[str] = MANAGED_IMAGE_ROOTS,
) -> MediaCleanupResult:
    ensure_write_allowed(settings)
    if raw_path is None or raw_path == "":
        return MediaCleanupResult("empty")
    try:
        normalized_path = normalize_managed_image_path(settings, raw_path, allowed_roots=allowed_roots)
    except MediaLifecycleError as exc:
        result = MediaCleanupResult("blocked", error=str(exc))
        log_action("media_cleanup_blocked", "managed_image", None, {"path": str(raw_path), "error": str(exc)})
        return result

    try:
        with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
            connection.execute("begin immediate")
            try:
                count = _reference_count(connection, settings, normalized_path)
                if count:
                    connection.commit()
                    result = MediaCleanupResult("shared", normalized_path, count)
                else:
                    target = settings.rewards_data_dir / normalized_path
                    if not target.exists():
                        connection.commit()
                        result = MediaCleanupResult("missing", normalized_path)
                    elif not target.is_file():
                        connection.rollback()
                        result = MediaCleanupResult("blocked", normalized_path, error="Media-путь не является файлом.")
                    else:
                        target.unlink()
                        connection.commit()
                        result = MediaCleanupResult("deleted", normalized_path)
            except Exception:
                connection.rollback()
                raise
    except Exception as exc:
        result = MediaCleanupResult("failed", normalized_path, error=str(exc))

    log_action(
        "media_cleanup",
        "managed_image",
        None,
        {
            "path": result.path,
            "status": result.status,
            "reference_count": result.reference_count,
            "error": result.error,
        },
    )
    return result


def discard_uncommitted_image(
    settings: Settings,
    raw_path: object,
    *,
    allowed_roots: frozenset[str] = MANAGED_IMAGE_ROOTS,
) -> MediaCleanupResult:
    ensure_write_allowed(settings)
    if raw_path is None or raw_path == "":
        return MediaCleanupResult("empty")
    try:
        normalized_path = normalize_managed_image_path(settings, raw_path, allowed_roots=allowed_roots)
        target = settings.rewards_data_dir / normalized_path
        if not target.exists():
            result = MediaCleanupResult("missing", normalized_path)
        elif not target.is_file():
            result = MediaCleanupResult("blocked", normalized_path, error="Media-путь не является файлом.")
        else:
            target.unlink()
            result = MediaCleanupResult("deleted", normalized_path)
    except (OSError, MediaLifecycleError) as exc:
        result = MediaCleanupResult("failed", error=str(exc))
    log_action(
        "media_candidate_discard",
        "managed_image",
        None,
        {"path": result.path or str(raw_path), "status": result.status, "error": result.error},
    )
    return result
