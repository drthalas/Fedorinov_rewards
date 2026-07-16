from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ..config import Settings
from ..db import open_write_connection
from .audit import log_action
from .media_lifecycle import MediaCleanupResult, cleanup_unreferenced_image, discard_uncommitted_image
from .write_guard import ensure_write_allowed


MAX_PHOTO_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class PhotoValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PhotoField:
    field: str
    label: str
    stem: str


@dataclass(frozen=True)
class PhotoMutationResult:
    path: str | None
    cleanup: MediaCleanupResult


PERSON_PHOTO_FIELDS = (
    PhotoField("person_foto", "Фото кавалера", "FotoPerson"),
    PhotoField("main_foto", "Главное фото", "FotoMain"),
    PhotoField("rewards_foto", "Общее фото наград", "FotoAllMedal"),
    PhotoField("book1_foto", "Фото наградной книжки, сторона 1", "FotoBook1"),
    PhotoField("book2_foto", "Фото наградной книжки, сторона 2", "FotoBook2"),
    PhotoField("card1_foto", "Фото учётной карточки, страница 1", "FotoCard1"),
    PhotoField("card2_foto", "Фото учётной карточки, страница 2", "FotoCard2"),
)
REWARD_PHOTO_FIELDS = (
    PhotoField("front_foto", "Фото награды: аверс", "FotoFront"),
    PhotoField("back_foto", "Фото награды: реверс", "FotoBack"),
    PhotoField("book1_foto", "Фото книжки, сторона 1", "FotoBook1"),
    PhotoField("book2_foto", "Фото книжки, сторона 2", "FotoBook2"),
    PhotoField("reward_list", "Наградной лист", "RewardList"),
)
MARK_PHOTO_FIELDS = (
    PhotoField("front_foto", "Фото знака: аверс", "FotoFront"),
    PhotoField("back_foto", "Фото знака: реверс", "FotoBack"),
    PhotoField("book1_foto", "Фото книжки, сторона 1", "FotoBook1"),
    PhotoField("book2_foto", "Фото книжки, сторона 2", "FotoBook2"),
)

PHOTO_FIELDS = {
    "person": PERSON_PHOTO_FIELDS,
    "reward": REWARD_PHOTO_FIELDS,
    "mark": MARK_PHOTO_FIELDS,
}


def photo_items(entity_type: str, row: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"field": item.field, "label": item.label, "path": row.get(item.field)}
        for item in _fields_for(entity_type)
    ]


def _fields_for(entity_type: str) -> tuple[PhotoField, ...]:
    try:
        return PHOTO_FIELDS[entity_type]
    except KeyError as exc:
        raise PhotoValidationError("Некорректный тип объекта") from exc


def _field_config(entity_type: str, photo_field: str) -> PhotoField:
    for item in _fields_for(entity_type):
        if item.field == photo_field:
            return item
    raise PhotoValidationError("Некорректное поле фото")


def _extension(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise PhotoValidationError("Разрешены только .jpg, .jpeg, .png, .webp")
    return suffix


def _matches_image_signature(extension: str, content: bytes) -> bool:
    if extension in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == ".webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _entity_row(connection, entity_type: str, entity_id: int):
    if entity_type == "person":
        return connection.execute("select id from person where id = ?", (entity_id,)).fetchone()
    if entity_type == "reward":
        return connection.execute("select id, person_id from rewards where id = ?", (entity_id,)).fetchone()
    if entity_type == "mark":
        return connection.execute("select id from mark where id = ?", (entity_id,)).fetchone()
    raise PhotoValidationError("Некорректный тип объекта")


def _relative_dir(entity_type: str, entity_id: int, row) -> Path:
    if entity_type == "person":
        return Path("Source") / str(entity_id)
    if entity_type == "reward":
        return Path("Source") / str(row["person_id"]) / str(entity_id)
    if entity_type == "mark":
        return Path("SourceMark") / str(entity_id)
    raise PhotoValidationError("Некорректный тип объекта")


def _table_name(entity_type: str) -> str:
    if entity_type == "person":
        return "person"
    if entity_type == "reward":
        return "rewards"
    if entity_type == "mark":
        return "mark"
    raise PhotoValidationError("Некорректный тип объекта")


def _allowed_roots(entity_type: str) -> frozenset[str]:
    if entity_type in {"person", "reward"}:
        return frozenset({"Source"})
    if entity_type == "mark":
        return frozenset({"SourceMark"})
    raise PhotoValidationError("Некорректный тип объекта")


def save_photo(
    settings: Settings,
    entity_type: str,
    entity_id: int,
    photo_field: str,
    filename: str,
    content: bytes,
) -> str:
    return str(save_photo_with_result(settings, entity_type, entity_id, photo_field, filename, content).path)


def save_photo_with_result(
    settings: Settings,
    entity_type: str,
    entity_id: int,
    photo_field: str,
    filename: str,
    content: bytes,
) -> PhotoMutationResult:
    ensure_write_allowed(settings)
    field = _field_config(entity_type, photo_field)
    extension = _extension(filename)
    if not content:
        raise PhotoValidationError("Файл пустой")
    if len(content) > MAX_PHOTO_BYTES:
        raise PhotoValidationError("Файл больше 25 MB")
    if not _matches_image_signature(extension, content):
        raise PhotoValidationError("Файл не является корректным изображением выбранного типа")

    relative_path: str | None = None
    old_path: object = None
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = _entity_row(connection, entity_type, entity_id)
        if row is None:
            raise PhotoValidationError("Объект не найден")
        table = _table_name(entity_type)
        current = connection.execute(
            f"select {field.field} as photo_path from {table} where id = ?",
            (entity_id,),
        ).fetchone()
        old_path = current["photo_path"] if current is not None else None
        relative_dir = _relative_dir(entity_type, entity_id, row)
        target_dir = settings.rewards_data_dir / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{field.stem}_{_timestamp()}_{uuid4().hex}{extension}"
        target_path = target_dir / filename
        relative_path = (relative_dir / filename).as_posix()
        try:
            target_path.write_bytes(content)
            connection.execute(f"update {table} set {field.field} = ? where id = ?", (relative_path, entity_id))
            connection.commit()
        except Exception:
            connection.rollback()
            discard_uncommitted_image(settings, relative_path, allowed_roots=_allowed_roots(entity_type))
            raise

    cleanup = cleanup_unreferenced_image(settings, old_path, allowed_roots=_allowed_roots(entity_type))
    log_action(
        "photo_uploaded",
        entity_type,
        entity_id,
        {"field": field.field, "bytes": len(content), "old_file_cleanup": cleanup.status},
    )
    return PhotoMutationResult(relative_path, cleanup)


def clear_photo(settings: Settings, entity_type: str, entity_id: int, photo_field: str) -> None:
    clear_photo_with_result(settings, entity_type, entity_id, photo_field)


def clear_photo_with_result(
    settings: Settings,
    entity_type: str,
    entity_id: int,
    photo_field: str,
) -> PhotoMutationResult:
    ensure_write_allowed(settings)
    field = _field_config(entity_type, photo_field)
    old_path: object = None
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = _entity_row(connection, entity_type, entity_id)
        if row is None:
            raise PhotoValidationError("Объект не найден")
        table = _table_name(entity_type)
        current = connection.execute(
            f"select {field.field} as photo_path from {table} where id = ?",
            (entity_id,),
        ).fetchone()
        old_path = current["photo_path"] if current is not None else None
        connection.execute(f"update {table} set {field.field} = null where id = ?", (entity_id,))
        connection.commit()
    cleanup = cleanup_unreferenced_image(settings, old_path, allowed_roots=_allowed_roots(entity_type))
    log_action(
        "photo_field_cleared",
        entity_type,
        entity_id,
        {"field": field.field, "old_file_cleanup": cleanup.status},
    )
    return PhotoMutationResult(None, cleanup)
