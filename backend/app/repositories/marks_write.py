from contextlib import closing
from dataclasses import dataclass

from ..config import Settings
from ..db import open_write_connection
from ..services.audit import log_action
from ..services.write_guard import ensure_write_allowed


MARK_FIELDS = (
    "id_gos",
    "id_catigory",
    "id_sub_catigory",
    "id_name",
    "id_link",
    "number",
    "instock",
    "date_purchase",
    "price_purchase",
    "price_now",
    "front_foto",
    "back_foto",
    "book1_foto",
    "book2_foto",
)


class MarkValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MarkWriteData:
    id_gos: int | None = None
    id_catigory: int | None = None
    id_sub_catigory: int | None = None
    id_name: int | None = None
    id_link: str | None = None
    number: int | None = None
    instock: bool = False
    date_purchase: str | None = None
    price_purchase: int | None = None
    price_now: int | None = None
    front_foto: str | None = None
    back_foto: str | None = None
    book1_foto: str | None = None
    book2_foto: str | None = None


def _empty_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _optional_int(values: dict[str, object], key: str) -> int | None:
    value = _empty_to_none(values.get(key))
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MarkValidationError(f"Некорректное числовое поле: {key}") from exc


def _checkbox(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes", "да"}


def mark_data_from_mapping(values: dict[str, object]) -> MarkWriteData:
    return MarkWriteData(
        id_gos=_optional_int(values, "id_gos"),
        id_catigory=_optional_int(values, "id_catigory"),
        id_sub_catigory=_optional_int(values, "id_sub_catigory"),
        id_name=_optional_int(values, "id_name"),
        id_link=_empty_to_none(values.get("id_link")),
        number=_optional_int(values, "number"),
        instock=_checkbox(values.get("instock")),
        date_purchase=_empty_to_none(values.get("date_purchase")),
        price_purchase=_optional_int(values, "price_purchase"),
        price_now=_optional_int(values, "price_now"),
        front_foto=_empty_to_none(values.get("front_foto")),
        back_foto=_empty_to_none(values.get("back_foto")),
        book1_foto=_empty_to_none(values.get("book1_foto")),
        book2_foto=_empty_to_none(values.get("book2_foto")),
    )


def _as_params(data: MarkWriteData) -> tuple[object, ...]:
    return tuple(getattr(data, field) for field in MARK_FIELDS)


def create_mark(settings: Settings, data: MarkWriteData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        cursor = connection.execute(
            """
            insert into mark (
                id_gos, id_catigory, id_sub_catigory, id_name, id_link,
                number, instock, date_purchase, price_purchase, price_now,
                front_foto, back_foto, book1_foto, book2_foto
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            _as_params(data),
        )
        mark_id = int(cursor.lastrowid)
        connection.commit()
    log_action("create", "mark", mark_id, {"fields": list(MARK_FIELDS)})
    return mark_id


def update_mark(settings: Settings, mark_id: int, data: MarkWriteData) -> None:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        cursor = connection.execute(
            """
            update mark
            set id_gos = ?, id_catigory = ?, id_sub_catigory = ?, id_name = ?, id_link = ?,
                number = ?, instock = ?, date_purchase = ?, price_purchase = ?, price_now = ?,
                front_foto = ?, back_foto = ?, book1_foto = ?, book2_foto = ?
            where id = ?
            """,
            (*_as_params(data), mark_id),
        )
        if cursor.rowcount == 0:
            raise MarkValidationError("Знак не найден")
        connection.commit()
    log_action("update", "mark", mark_id, {"fields": list(MARK_FIELDS)})


def delete_mark(settings: Settings, mark_id: int, confirm: bool = False) -> None:
    ensure_write_allowed(settings)
    if not confirm:
        raise MarkValidationError("Удаление требует confirm=true")
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        cursor = connection.execute("delete from mark where id = ?", (mark_id,))
        if cursor.rowcount == 0:
            raise MarkValidationError("Знак не найден")
        connection.commit()
    log_action("delete", "mark", mark_id, {"media_deleted": False})
