from dataclasses import dataclass
from contextlib import closing

from ..config import Settings
from ..db import open_write_connection
from ..services.audit import log_action
from ..services.write_guard import ensure_dangerous_action_allowed, ensure_write_allowed


REWARD_FIELDS = (
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
    "reward_list",
)


class RewardValidationError(ValueError):
    pass


@dataclass(frozen=True)
class RewardWriteData:
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
    reward_list: str | None = None


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
        raise RewardValidationError(f"Некорректное числовое поле: {key}") from exc


def _checkbox(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes", "да"}


def reward_data_from_mapping(values: dict[str, object]) -> RewardWriteData:
    return RewardWriteData(
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
        reward_list=_empty_to_none(values.get("reward_list")),
    )


def _as_params(data: RewardWriteData) -> tuple[object, ...]:
    return tuple(getattr(data, field) for field in REWARD_FIELDS)


def _person_exists(connection, person_id: int) -> bool:
    row = connection.execute("select 1 from person where id = ?", (person_id,)).fetchone()
    return row is not None


def create_reward(settings: Settings, person_id: int, data: RewardWriteData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if not _person_exists(connection, person_id):
            raise RewardValidationError("Награжденный не найден")
        cursor = connection.execute(
            """
            insert into rewards (
                person_id, id_gos, id_catigory, id_sub_catigory, id_name, id_link,
                number, instock, date_purchase, price_purchase, price_now,
                front_foto, back_foto, book1_foto, book2_foto, reward_list
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (person_id, *_as_params(data)),
        )
        reward_id = int(cursor.lastrowid)
        connection.commit()
    log_action("create", "reward", reward_id, {"person_id": person_id, "fields": list(REWARD_FIELDS)})
    return reward_id


def update_reward(settings: Settings, reward_id: int, data: RewardWriteData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = connection.execute("select person_id from rewards where id = ?", (reward_id,)).fetchone()
        if row is None:
            raise RewardValidationError("Награда не найдена")
        person_id = int(row["person_id"])
        cursor = connection.execute(
            """
            update rewards
            set id_gos = ?, id_catigory = ?, id_sub_catigory = ?, id_name = ?, id_link = ?,
                number = ?, instock = ?, date_purchase = ?, price_purchase = ?, price_now = ?,
                front_foto = ?, back_foto = ?, book1_foto = ?, book2_foto = ?, reward_list = ?
            where id = ?
            """,
            (*_as_params(data), reward_id),
        )
        if cursor.rowcount == 0:
            raise RewardValidationError("Награда не найдена")
        connection.commit()
    log_action("update", "reward", reward_id, {"fields": list(REWARD_FIELDS)})
    return person_id


def delete_reward(settings: Settings, reward_id: int, confirm: bool = False) -> int:
    ensure_dangerous_action_allowed(settings)
    if not confirm:
        raise RewardValidationError("Действие требует подтверждения.")
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = connection.execute("select person_id from rewards where id = ?", (reward_id,)).fetchone()
        if row is None:
            raise RewardValidationError("Награда не найдена")
        person_id = int(row["person_id"])
        connection.execute("delete from rewards where id = ?", (reward_id,))
        connection.commit()
    log_action("delete", "reward", reward_id, {"person_id": person_id, "media_deleted": False})
    return person_id
