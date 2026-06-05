from dataclasses import dataclass
from contextlib import closing

from ..config import Settings
from ..db import open_write_connection
from ..services.audit import log_action
from ..services.write_guard import ensure_dangerous_action_allowed, ensure_write_allowed


PERSON_BASE_FIELDS = ("fio", "birthday", "id_rank", "link1", "link2", "comment")
PERSON_OPTIONAL_FIELDS = ("biography",)


class PersonValidationError(ValueError):
    pass


class PersonDeleteBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersonWriteData:
    fio: str
    birthday: str | None = None
    id_rank: int | None = None
    link1: str | None = None
    link2: str | None = None
    comment: str | None = None
    biography: str | None = None


def _empty_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def person_data_from_mapping(values: dict[str, object]) -> PersonWriteData:
    fio = str(values.get("fio") or "").strip()
    if not fio:
        raise PersonValidationError("ФИО обязательно")

    rank_value = _empty_to_none(values.get("id_rank"))
    try:
        id_rank = int(rank_value) if rank_value is not None else None
    except (TypeError, ValueError) as exc:
        raise PersonValidationError("Некорректное звание/специальность") from exc

    return PersonWriteData(
        fio=fio,
        birthday=_empty_to_none(values.get("birthday")),
        id_rank=id_rank,
        link1=_empty_to_none(values.get("link1")),
        link2=_empty_to_none(values.get("link2")),
        comment=_empty_to_none(values.get("comment")),
        biography=_empty_to_none(values.get("biography")),
    )


def _person_columns(connection) -> set[str]:
    return {row["name"] for row in connection.execute("pragma table_info(person)").fetchall()}


def _active_fields(connection) -> tuple[str, ...]:
    columns = _person_columns(connection)
    optional = tuple(field for field in PERSON_OPTIONAL_FIELDS if field in columns)
    return (*PERSON_BASE_FIELDS, *optional)


def _as_params(data: PersonWriteData, fields: tuple[str, ...]) -> tuple[object, ...]:
    return tuple(getattr(data, field) for field in fields)


def create_person(settings: Settings, data: PersonWriteData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        fields = _active_fields(connection)
        columns = ", ".join(fields)
        placeholders = ", ".join("?" for _ in fields)
        cursor = connection.execute(
            f"insert into person ({columns}) values ({placeholders})",
            _as_params(data, fields),
        )
        person_id = int(cursor.lastrowid)
        connection.commit()
    log_action("create", "person", person_id, {"fields": list(fields)})
    return person_id


def update_person(settings: Settings, person_id: int, data: PersonWriteData) -> None:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        fields = _active_fields(connection)
        assignments = ", ".join(f"{field} = ?" for field in fields)
        cursor = connection.execute(
            f"update person set {assignments} where id = ?",
            (*_as_params(data, fields), person_id),
        )
        if cursor.rowcount == 0:
            raise PersonValidationError("Награжденный не найден")
        connection.commit()
    log_action("update", "person", person_id, {"fields": list(fields)})


CONFIRM_REQUIRED_MESSAGE = "Действие требует подтверждения."


def delete_person(settings: Settings, person_id: int, confirm: bool = False) -> None:
    ensure_dangerous_action_allowed(settings)
    if not confirm:
        raise PersonValidationError(CONFIRM_REQUIRED_MESSAGE)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        reward_count = connection.execute(
            "select count(*) as count from rewards where person_id = ?",
            (person_id,),
        ).fetchone()["count"]
        if int(reward_count) > 0:
            raise PersonDeleteBlockedError("Нельзя удалить: у награжденного есть награды")

        cursor = connection.execute("delete from person where id = ?", (person_id,))
        if cursor.rowcount == 0:
            raise PersonValidationError("Награжденный не найден")
        connection.commit()
    log_action("delete", "person", person_id, {"blocked_if_rewards": True})
