from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..config import Settings
from ..db import open_readonly_connection, open_write_connection
from .audit import log_action
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

PERSON_MEDIA_TITLE_MAX = 160
PERSON_MEDIA_DESCRIPTION_MAX = 1000
PERSON_MEDIA_FILE_FIELD = PhotoField("file_path", "Дополнительный материал", "Material")


def _person_media_table_exists(connection) -> bool:
    row = connection.execute(
        "select 1 from sqlite_master where type = 'table' and name = 'person_media'"
    ).fetchone()
    return row is not None


def _ensure_person_media_table(connection) -> None:
    connection.execute(
        """
        create table if not exists person_media (
            id integer primary key autoincrement,
            person_id integer not null,
            photo_field text,
            title text not null,
            description text,
            file_path text,
            sort_order integer not null default 0,
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp,
            foreign key (person_id) references person(id) on delete cascade,
            unique (person_id, photo_field)
        )
        """
    )
    connection.execute(
        "create index if not exists idx_person_media_person on person_media(person_id, sort_order, id)"
    )


def _clean_media_text(value: object, field_name: str, max_length: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise PhotoValidationError(f"{field_name} обязательно")
    if len(text) > max_length:
        raise PhotoValidationError(f"{field_name} длиннее {max_length} символов")
    return text


def person_photo_controls(db_path: Path, person: dict[str, object]) -> list[dict[str, object]]:
    person_id = int(person.get("id") or 0)
    metadata: dict[str, dict[str, object]] = {}
    dynamic: list[dict[str, object]] = []
    with closing(open_readonly_connection(db_path)) as connection:
        if _person_media_table_exists(connection):
            rows = connection.execute(
                """
                select id, person_id, photo_field, title, description, file_path, sort_order
                from person_media
                where person_id = ?
                order by sort_order, id
                """,
                (person_id,),
            ).fetchall()
            for row in rows:
                item = dict(row)
                if item.get("photo_field"):
                    metadata[str(item["photo_field"])] = item
                else:
                    dynamic.append(
                        {
                            "id": item["id"],
                            "field": PERSON_MEDIA_FILE_FIELD.field,
                            "label": item["title"],
                            "description": item.get("description") or "",
                            "path": item.get("file_path"),
                            "is_dynamic": True,
                        }
                    )

    controls: list[dict[str, object]] = []
    for field in PERSON_PHOTO_FIELDS:
        override = metadata.get(field.field, {})
        controls.append(
            {
                "id": override.get("id"),
                "field": field.field,
                "label": override.get("title") or field.label,
                "default_label": field.label,
                "description": override.get("description") or "",
                "path": person.get(field.field),
                "is_dynamic": False,
            }
        )
    controls.extend(dynamic)
    return controls


def create_person_media(settings: Settings, person_id: int, title: object, description: object = "") -> int:
    ensure_write_allowed(settings)
    clean_title = _clean_media_text(title, "Название", PERSON_MEDIA_TITLE_MAX, required=True)
    clean_description = _clean_media_text(description, "Описание", PERSON_MEDIA_DESCRIPTION_MAX)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if _entity_row(connection, "person", person_id) is None:
            raise PhotoValidationError("Награжденный не найден")
        _ensure_person_media_table(connection)
        sort_order = connection.execute(
            "select coalesce(max(sort_order), 99) + 1 from person_media where person_id = ?",
            (person_id,),
        ).fetchone()[0]
        cursor = connection.execute(
            """
            insert into person_media (person_id, title, description, sort_order)
            values (?, ?, ?, ?)
            """,
            (person_id, clean_title, clean_description or None, sort_order),
        )
        connection.commit()
        media_id = int(cursor.lastrowid)
    log_action("person_media_created", "person", person_id, {"media_id": media_id})
    return media_id


def update_person_media(
    settings: Settings,
    person_id: int,
    title: object,
    description: object = "",
    *,
    media_id: int | None = None,
    photo_field: str = "",
) -> None:
    ensure_write_allowed(settings)
    clean_title = _clean_media_text(title, "Название", PERSON_MEDIA_TITLE_MAX, required=True)
    clean_description = _clean_media_text(description, "Описание", PERSON_MEDIA_DESCRIPTION_MAX)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if _entity_row(connection, "person", person_id) is None:
            raise PhotoValidationError("Награжденный не найден")
        _ensure_person_media_table(connection)
        if media_id is not None:
            cursor = connection.execute(
                """
                update person_media
                set title = ?, description = ?, updated_at = current_timestamp
                where id = ? and person_id = ? and photo_field is null
                """,
                (clean_title, clean_description or None, media_id, person_id),
            )
            if cursor.rowcount != 1:
                raise PhotoValidationError("Карточка материала не найдена")
        else:
            _field_config("person", photo_field)
            sort_order = next(
                index for index, field in enumerate(PERSON_PHOTO_FIELDS) if field.field == photo_field
            )
            connection.execute(
                """
                insert into person_media (person_id, photo_field, title, description, sort_order)
                values (?, ?, ?, ?, ?)
                on conflict(person_id, photo_field) do update set
                    title = excluded.title,
                    description = excluded.description,
                    updated_at = current_timestamp
                """,
                (person_id, photo_field, clean_title, clean_description or None, sort_order),
            )
        connection.commit()
    log_action(
        "person_media_updated",
        "person",
        person_id,
        {"media_id": media_id, "photo_field": photo_field or None},
    )


def delete_person_media(settings: Settings, person_id: int, media_id: int) -> None:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if not _person_media_table_exists(connection):
            raise PhotoValidationError("Карточка материала не найдена")
        cursor = connection.execute(
            "delete from person_media where id = ? and person_id = ? and photo_field is null",
            (media_id, person_id),
        )
        if cursor.rowcount != 1:
            raise PhotoValidationError("Карточка материала не найдена")
        connection.commit()
    log_action(
        "person_media_deleted",
        "person",
        person_id,
        {"media_id": media_id, "physical_file_deleted": False},
    )


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
    if entity_type == "person_media" and photo_field == PERSON_MEDIA_FILE_FIELD.field:
        return PERSON_MEDIA_FILE_FIELD
    for item in _fields_for(entity_type):
        if item.field == photo_field:
            return item
    raise PhotoValidationError("Некорректное поле фото")


def _extension(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise PhotoValidationError("Разрешены только .jpg, .jpeg, .png, .webp")
    return suffix


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _entity_row(connection, entity_type: str, entity_id: int):
    if entity_type == "person":
        return connection.execute("select id from person where id = ?", (entity_id,)).fetchone()
    if entity_type == "reward":
        return connection.execute("select id, person_id from rewards where id = ?", (entity_id,)).fetchone()
    if entity_type == "mark":
        return connection.execute("select id from mark where id = ?", (entity_id,)).fetchone()
    if entity_type == "person_media":
        if not _person_media_table_exists(connection):
            return None
        return connection.execute(
            "select id, person_id from person_media where id = ? and photo_field is null",
            (entity_id,),
        ).fetchone()
    raise PhotoValidationError("Некорректный тип объекта")


def _relative_dir(entity_type: str, entity_id: int, row) -> Path:
    if entity_type == "person":
        return Path("Source") / str(entity_id)
    if entity_type == "reward":
        return Path("Source") / str(row["person_id"]) / str(entity_id)
    if entity_type == "mark":
        return Path("SourceMark") / str(entity_id)
    if entity_type == "person_media":
        return Path("Source") / str(row["person_id"]) / "Materials"
    raise PhotoValidationError("Некорректный тип объекта")


def _table_name(entity_type: str) -> str:
    if entity_type == "person":
        return "person"
    if entity_type == "reward":
        return "rewards"
    if entity_type == "mark":
        return "mark"
    if entity_type == "person_media":
        return "person_media"
    raise PhotoValidationError("Некорректный тип объекта")


def save_photo(
    settings: Settings,
    entity_type: str,
    entity_id: int,
    photo_field: str,
    filename: str,
    content: bytes,
) -> str:
    ensure_write_allowed(settings)
    field = _field_config(entity_type, photo_field)
    extension = _extension(filename)
    if not content:
        raise PhotoValidationError("Файл пустой")
    if len(content) > MAX_PHOTO_BYTES:
        raise PhotoValidationError("Файл больше 25 MB")

    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = _entity_row(connection, entity_type, entity_id)
        if row is None:
            raise PhotoValidationError("Объект не найден")
        relative_dir = _relative_dir(entity_type, entity_id, row)
        target_dir = settings.rewards_data_dir / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{field.stem}{entity_id}" if entity_type == "person_media" else field.stem
        filename = f"{stem}_{_timestamp()}{extension}"
        target_path = target_dir / filename
        target_path.write_bytes(content)
        relative_path = (relative_dir / filename).as_posix()
        table = _table_name(entity_type)
        connection.execute(f"update {table} set {field.field} = ? where id = ?", (relative_path, entity_id))
        connection.commit()

    log_action("photo_uploaded", entity_type, entity_id, {"field": field.field, "bytes": len(content)})
    return relative_path


def clear_photo(settings: Settings, entity_type: str, entity_id: int, photo_field: str) -> None:
    ensure_write_allowed(settings)
    field = _field_config(entity_type, photo_field)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = _entity_row(connection, entity_type, entity_id)
        if row is None:
            raise PhotoValidationError("Объект не найден")
        table = _table_name(entity_type)
        connection.execute(f"update {table} set {field.field} = null where id = ?", (entity_id,))
        connection.commit()
    log_action("photo_field_cleared", entity_type, entity_id, {"field": field.field, "physical_file_deleted": False})
