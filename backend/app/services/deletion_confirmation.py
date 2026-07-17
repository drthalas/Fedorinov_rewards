from dataclasses import dataclass
import os
from pathlib import Path

from ..config import Settings
from .media_lifecycle import (
    MANAGED_IMAGE_EXTENSIONS,
    MediaLifecycleError,
    MediaReferenceExclusion,
    managed_image_reference_count_in_connection,
    normalize_managed_image_path,
)


@dataclass(frozen=True)
class MediaDeletePreview:
    linked_media_count: int
    folder_item_count: int = 0
    preserved_shared_reference_count: int = 0
    block_reason: str | None = None


def folder_item_count(folder: Path) -> int:
    if not folder.exists() or not folder.is_dir():
        return 0
    count = 0
    for _, directories, files in os.walk(folder, followlinks=False):
        count += len(directories) + len(files)
    return count


def _path_is_inside_prefix(path: str, prefix: str | None) -> bool:
    if not prefix:
        return False
    safe_prefix = prefix.rstrip("/")
    return path == safe_prefix or path.startswith(safe_prefix + "/")


def _owned_folder_block_reason(
    connection,
    settings: Settings,
    folder: Path | None,
    *,
    excluded_rows: tuple[MediaReferenceExclusion, ...],
) -> str | None:
    if folder is None or not folder.exists():
        return None
    if folder.is_symlink() or not folder.is_dir():
        return "Точный каталог сущности не прошёл безопасную проверку."
    for entry in sorted(folder.rglob("*"), key=lambda item: item.as_posix()):
        if entry.is_symlink():
            return "В точном каталоге сущности обнаружена символическая ссылка."
        if entry.is_dir():
            continue
        if not entry.is_file() or entry.stat(follow_symlinks=False).st_nlink != 1:
            return "В точном каталоге сущности обнаружен неоднозначный файл."
        if entry.suffix.lower() not in MANAGED_IMAGE_EXTENSIONS:
            continue
        relative_path = entry.relative_to(settings.rewards_data_dir).as_posix()
        try:
            reference_count = managed_image_reference_count_in_connection(
                connection,
                settings,
                relative_path,
                excluded_rows=excluded_rows,
            )
        except MediaLifecycleError:
            return "Файл в точном каталоге сущности не прошёл безопасную проверку."
        if reference_count:
            return "Внешняя запись ссылается на файл внутри точного каталога удаляемой сущности."
    return None


def media_delete_preview(
    connection,
    settings: Settings,
    reference_paths: tuple[object, ...],
    *,
    excluded_rows: tuple[MediaReferenceExclusion, ...],
    owned_folder: Path | None = None,
    owned_relative_prefix: str | None = None,
) -> MediaDeletePreview:
    raw_paths = tuple(path for path in reference_paths if path not in {None, ""})
    normalized_paths: set[str] = set()
    try:
        for path in raw_paths:
            normalized_paths.add(normalize_managed_image_path(settings, path))
    except MediaLifecycleError:
        return MediaDeletePreview(
            linked_media_count=len(raw_paths),
            folder_item_count=folder_item_count(owned_folder) if owned_folder is not None else 0,
            block_reason="Путь к связанному изображению не прошёл безопасную проверку.",
        )

    shared_paths = {
        path
        for path in normalized_paths
        if managed_image_reference_count_in_connection(
            connection,
            settings,
            path,
            excluded_rows=excluded_rows,
        )
        > 0
    }
    outside_owned = {
        path
        for path in normalized_paths - shared_paths
        if owned_relative_prefix and not _path_is_inside_prefix(path, owned_relative_prefix)
    }
    shared_outside_owned = {
        path
        for path in shared_paths
        if not owned_relative_prefix or not _path_is_inside_prefix(path, owned_relative_prefix)
    }
    folder_block_reason = _owned_folder_block_reason(
        connection,
        settings,
        owned_folder,
        excluded_rows=excluded_rows,
    )
    return MediaDeletePreview(
        linked_media_count=len(raw_paths),
        folder_item_count=folder_item_count(owned_folder) if owned_folder is not None else 0,
        preserved_shared_reference_count=len(shared_outside_owned),
        block_reason=(
            folder_block_reason
            or (
                "Несвязанный с другими записями файл находится вне точного каталога удаляемой сущности."
                if outside_owned
                else None
            )
        ),
    )


def confirmation_message(
    action: str,
    *,
    child_counts: tuple[tuple[str, int], ...] = (),
    media: MediaDeletePreview | None = None,
    block_reason: str | None = None,
) -> str:
    details = [f"{label}: {count}" for label, count in child_counts]
    if media is not None:
        details.append(f"связанных материалов: {media.linked_media_count}")
        if media.folder_item_count:
            details.append(f"файлов и папок: {media.folder_item_count}")
        if media.preserved_shared_reference_count:
            details.append(f"общих файлов будет сохранено: {media.preserved_shared_reference_count}")
        block_reason = block_reason or media.block_reason
    summary = "; ".join(details)
    if summary:
        summary = summary[0].upper() + summary[1:]
    if block_reason:
        prefix = f"Удаление недоступно: {block_reason}"
        return f"{prefix} {summary}." if summary else prefix
    return f"{action} {summary}." if summary else action
