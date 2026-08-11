from dataclasses import dataclass, replace
from contextlib import closing
from typing import Callable
from uuid import uuid4

from ..config import Settings
from ..db import open_readonly_connection, open_write_connection
from ..services.audit import log_action
from ..services.deletion_lifecycle import (
    DeletionExecutionResult,
    DeletionLifecycleError,
    MediaReferenceExclusion,
    RowCountExpectation,
    build_delete_plan,
    execute_delete_plan,
    recorded_delete_plan,
    recover_delete_operation,
    reward_owned_directory,
)
from ..services.dates import normalize_date_input
from ..services.deletion_confirmation import MediaDeletePreview, confirmation_message, media_delete_preview
from ..services.write_guard import ensure_dangerous_action_allowed, ensure_write_allowed
from .reward_reference import reward_reference_from_connection


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


class RewardDeleteBlockedError(RewardValidationError):
    pass


DUPLICATE_REWARD_MESSAGE = (
    "Награда с таким наименованием и номером уже есть в базе. "
    "Проверьте номер или откройте существующую запись."
)


NUMERIC_FIELD_ERRORS = {
    "id_name": "Выберите корректное наименование награды.",
    "number": "Укажите корректный номер награды.",
    "price_purchase": "Укажите корректную цену покупки.",
    "price_now": "Укажите корректную текущую цену.",
}


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


@dataclass(frozen=True)
class RewardDeleteResult:
    person_id: int
    operation: DeletionExecutionResult


@dataclass(frozen=True)
class RewardDeletePreview:
    person_id: int
    media: MediaDeletePreview


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
        raise RewardValidationError(NUMERIC_FIELD_ERRORS.get(key, "Укажите корректное числовое значение.")) from exc


def _checkbox(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes", "да"}


def reward_data_from_mapping(values: dict[str, object]) -> RewardWriteData:
    try:
        date_purchase = normalize_date_input(values.get("date_purchase"))
    except ValueError as exc:
        raise RewardValidationError(str(exc)) from exc
    return RewardWriteData(
        id_name=_optional_int(values, "id_name"),
        number=_optional_int(values, "number"),
        instock=_checkbox(values.get("instock")),
        date_purchase=date_purchase,
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


def _validate_required_name(data: RewardWriteData) -> None:
    if data.id_name is None:
        raise RewardValidationError("Выберите наименование награды.")
    if data.date_purchase:
        try:
            normalize_date_input(data.date_purchase)
        except ValueError as exc:
            raise RewardValidationError(str(exc)) from exc


def _preserve_existing_name(data: RewardWriteData, existing_row) -> RewardWriteData:
    if data.id_name is not None or existing_row["id_name"] is None:
        return data
    return replace(data, id_name=int(existing_row["id_name"]))


def _with_reference_fields(connection, data: RewardWriteData) -> RewardWriteData:
    if data.id_name is None:
        raise RewardValidationError("Выберите наименование награды.")
    reference = reward_reference_from_connection(connection, data.id_name)
    if reference is None:
        raise RewardValidationError("Выбранное наименование отсутствует в справочнике наград.")
    return replace(
        data,
        id_gos=int(reference["id_gos"]),
        id_catigory=int(reference["id_catigory"]),
        id_sub_catigory=int(reference["id_sub_catigory"]),
        id_link=str(reference["id_link"]) if reference.get("id_link") not in {None, ""} else None,
    )


def _person_exists(connection, person_id: int) -> bool:
    row = connection.execute("select 1 from person where id = ?", (person_id,)).fetchone()
    return row is not None


def _duplicate_payload(row) -> dict[str, object]:
    return {
        "existing_reward_id": int(row["existing_reward_id"]),
        "existing_person_id": int(row["existing_person_id"]) if row["existing_person_id"] is not None else None,
        "existing_person_name": str(row["existing_person_name"] or ""),
        "existing_url": f"/persons/{int(row['existing_person_id'])}" if row["existing_person_id"] is not None else "",
    }


def _find_reward_duplicate(connection, id_name: int | None, number: int | None, current_reward_id: int | None = None) -> dict[str, object] | None:
    if id_name is None or number is None:
        return None
    conditions = [
        "r.id_name = ?",
        "trim(cast(r.number as text)) = ?",
    ]
    params: list[object] = [id_name, str(number).strip()]
    if current_reward_id is not None:
        conditions.append("r.id != ?")
        params.append(current_reward_id)
    row = connection.execute(
        f"""
        select
            r.id as existing_reward_id,
            r.person_id as existing_person_id,
            p.fio as existing_person_name
        from rewards r
        left join person p on p.id = r.person_id
        where {" and ".join(conditions)}
        order by r.id
        limit 1
        """,
        tuple(params),
    ).fetchone()
    return _duplicate_payload(row) if row is not None else None


def reward_duplicate_message(duplicate: dict[str, object] | None) -> str:
    if not duplicate:
        return ""
    person_name = str(duplicate.get("existing_person_name") or "").strip()
    person_id = duplicate.get("existing_person_id")
    reward_id = duplicate.get("existing_reward_id")
    if person_name and person_id and reward_id:
        return f"{DUPLICATE_REWARD_MESSAGE} Существующая запись: {person_name}, кавалер #{person_id}, награда #{reward_id}."
    if person_id and reward_id:
        return f"{DUPLICATE_REWARD_MESSAGE} Существующая запись: кавалер #{person_id}, награда #{reward_id}."
    return DUPLICATE_REWARD_MESSAGE


def check_reward_duplicate(settings: Settings, id_name: int | None, number: int | None, current_reward_id: int | None = None) -> dict[str, object] | None:
    if id_name is None or number is None:
        return None
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        return _find_reward_duplicate(connection, id_name, number, current_reward_id)


def _validate_unique_reward_number(connection, data: RewardWriteData, current_reward_id: int | None = None) -> None:
    duplicate = _find_reward_duplicate(connection, data.id_name, data.number, current_reward_id)
    if duplicate:
        raise RewardValidationError(reward_duplicate_message(duplicate))


def create_reward(settings: Settings, person_id: int, data: RewardWriteData) -> int:
    ensure_write_allowed(settings)
    _validate_required_name(data)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if not _person_exists(connection, person_id):
            raise RewardValidationError("Награжденный не найден.")
        data = _with_reference_fields(connection, data)
        _validate_unique_reward_number(connection, data)
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
        row = connection.execute(
            "select person_id, id_name from rewards where id = ?",
            (reward_id,),
        ).fetchone()
        if row is None:
            raise RewardValidationError("Награда не найдена.")
        person_id = int(row["person_id"])
        data = _preserve_existing_name(data, row)
        _validate_required_name(data)
        data = _with_reference_fields(connection, data)
        _validate_unique_reward_number(connection, data, reward_id)
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
            raise RewardValidationError("Награда не найдена.")
        connection.commit()
    log_action("update", "reward", reward_id, {"fields": list(REWARD_FIELDS)})
    return person_id


def reward_delete_preview(settings: Settings, reward_id: int) -> RewardDeletePreview:
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        row = connection.execute(
            "select person_id, front_foto, back_foto, book1_foto, book2_foto, reward_list "
            "from rewards where id = ?",
            (reward_id,),
        ).fetchone()
        if row is None:
            raise RewardValidationError("Награда не найдена.")
        person_id = int(row["person_id"])
        media = media_delete_preview(
            connection,
            settings,
            tuple(row[field] for field in ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list")),
            excluded_rows=(MediaReferenceExclusion("rewards", reward_id),),
            owned_folder=settings.rewards_data_dir / "Source" / str(person_id) / str(reward_id),
            owned_relative_prefix=f"Source/{person_id}/{reward_id}",
        )
    return RewardDeletePreview(person_id, media)


def reward_delete_confirmation_message(preview: RewardDeletePreview) -> str:
    return confirmation_message(
        "Удалить награду и принадлежащие ей материалы?",
        media=preview.media,
    )


def delete_reward_with_result(
    settings: Settings,
    reward_id: int,
    confirm: bool = False,
    *,
    operation_id: str | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> RewardDeleteResult:
    ensure_dangerous_action_allowed(settings)
    if not confirm:
        raise RewardValidationError("Действие требует подтверждения.")
    operation_id = str(operation_id or uuid4().hex)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = connection.execute(
            "select person_id, front_foto, back_foto, book1_foto, book2_foto, reward_list "
            "from rewards where id = ?",
            (reward_id,),
        ).fetchone()
        if row is None:
            try:
                recorded = recorded_delete_plan(settings, operation_id)
            except DeletionLifecycleError as exc:
                raise RewardDeleteBlockedError("Некорректный идентификатор операции удаления.") from exc
            if (
                recorded is None
                or recorded.entity_type != "reward"
                or len(recorded.entity_ids) != 2
                or recorded.entity_ids[0] != reward_id
            ):
                raise RewardValidationError("Награда не найдена.")
            try:
                recovered = recover_delete_operation(settings, operation_id)
            except DeletionLifecycleError as exc:
                raise RewardDeleteBlockedError(
                    "Не удалось безопасно завершить удаление награды. Повторите действие или проверьте журнал."
                ) from exc
            return RewardDeleteResult(recorded.entity_ids[1], recovered)
        person_id = int(row["person_id"])
        media_values = tuple(row[field] for field in ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list"))

    try:
        plan = build_delete_plan(
            settings,
            operation_id=operation_id,
            entity_type="reward",
            entity_ids=(reward_id, person_id),
            expected_row_counts=(RowCountExpectation("rewards", "id", reward_id, 1),),
            reference_paths=media_values,
            excluded_rows=(MediaReferenceExclusion("rewards", reward_id),),
            owned_paths=(reward_owned_directory(person_id, reward_id),),
        )
    except DeletionLifecycleError as exc:
        raise RewardDeleteBlockedError(
            "Нельзя безопасно удалить награду: путь к материалам не прошёл проверку."
        ) from exc

    def delete_database_row(connection) -> None:
        current = connection.execute(
            "select person_id, front_foto, back_foto, book1_foto, book2_foto, reward_list "
            "from rewards where id = ?",
            (reward_id,),
        ).fetchone()
        if current is None or int(current["person_id"]) != person_id:
            raise RewardDeleteBlockedError("Награда изменилась во время подготовки удаления.")
        current_media = tuple(
            current[field] for field in ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list")
        )
        if current_media != media_values:
            raise RewardDeleteBlockedError("Материалы награды изменились во время подготовки удаления.")
        connection.execute("delete from rewards where id = ?", (reward_id,))

    try:
        operation = execute_delete_plan(settings, plan, delete_database_row, fault_hook=fault_hook)
    except RewardDeleteBlockedError:
        raise
    except DeletionLifecycleError as exc:
        raise RewardDeleteBlockedError(
            "Нельзя безопасно удалить награду: обнаружены внешние ссылки или неоднозначные материалы."
        ) from exc
    log_action(
        "delete",
        "reward",
        reward_id,
        {
            "person_id": person_id,
            "operation_id": operation.operation_id,
            "status": operation.status,
            "staged_paths": operation.staged_paths,
            "preserved_shared_references": operation.preserved_shared_references,
        },
    )
    return RewardDeleteResult(person_id, operation)


def delete_reward(settings: Settings, reward_id: int, confirm: bool = False) -> int:
    return delete_reward_with_result(settings, reward_id, confirm=confirm).person_id
