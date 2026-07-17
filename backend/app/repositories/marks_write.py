from contextlib import closing
from dataclasses import dataclass
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
    mark_owned_directory,
    recorded_delete_plan,
    recover_delete_operation,
)
from ..services.dates import normalize_date_input
from ..services.deletion_confirmation import MediaDeletePreview, confirmation_message, media_delete_preview
from ..services.write_guard import ensure_dangerous_action_allowed, ensure_write_allowed


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


class MarkDeleteBlockedError(MarkValidationError):
    pass


NUMERIC_FIELD_ERRORS = {
    "id_gos": "Выберите корректное государство.",
    "id_catigory": "Выберите корректную категорию.",
    "id_sub_catigory": "Выберите корректную подкатегорию.",
    "id_name": "Выберите корректное наименование знака.",
    "number": "Укажите корректный номер знака.",
    "price_purchase": "Укажите корректную цену покупки.",
    "price_now": "Укажите корректную текущую цену.",
}


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


@dataclass(frozen=True)
class MarkDeleteResult:
    operation: DeletionExecutionResult


@dataclass(frozen=True)
class MarkDeletePreview:
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
        raise MarkValidationError(NUMERIC_FIELD_ERRORS.get(key, "Укажите корректное числовое значение.")) from exc


def _checkbox(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes", "да"}


def mark_data_from_mapping(values: dict[str, object]) -> MarkWriteData:
    try:
        date_purchase = normalize_date_input(values.get("date_purchase"))
    except ValueError as exc:
        raise MarkValidationError(str(exc)) from exc
    return MarkWriteData(
        id_gos=_optional_int(values, "id_gos"),
        id_catigory=_optional_int(values, "id_catigory"),
        id_sub_catigory=_optional_int(values, "id_sub_catigory"),
        id_name=_optional_int(values, "id_name"),
        id_link=_empty_to_none(values.get("id_link")),
        number=_optional_int(values, "number"),
        instock=_checkbox(values.get("instock")),
        date_purchase=date_purchase,
        price_purchase=_optional_int(values, "price_purchase"),
        price_now=_optional_int(values, "price_now"),
        front_foto=_empty_to_none(values.get("front_foto")),
        back_foto=_empty_to_none(values.get("back_foto")),
        book1_foto=_empty_to_none(values.get("book1_foto")),
        book2_foto=_empty_to_none(values.get("book2_foto")),
    )


def _as_params(data: MarkWriteData) -> tuple[object, ...]:
    return tuple(getattr(data, field) for field in MARK_FIELDS)


def _validate_required_name(data: MarkWriteData) -> None:
    if data.id_name is None:
        raise MarkValidationError("Выберите наименование знака.")
    if data.date_purchase:
        try:
            normalize_date_input(data.date_purchase)
        except ValueError as exc:
            raise MarkValidationError(str(exc)) from exc


def _preserve_existing_guide_ids(data: MarkWriteData, existing_row) -> MarkWriteData:
    values = {field: getattr(data, field) for field in MARK_FIELDS}
    for field in ("id_gos", "id_catigory", "id_sub_catigory", "id_name"):
        if values[field] is None and existing_row[field] is not None:
            values[field] = existing_row[field]
    return MarkWriteData(**values)


def create_mark(settings: Settings, data: MarkWriteData) -> int:
    ensure_write_allowed(settings)
    _validate_required_name(data)
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
        existing_row = connection.execute(
            "select id_gos, id_catigory, id_sub_catigory, id_name from mark where id = ?",
            (mark_id,),
        ).fetchone()
        if existing_row is None:
            raise MarkValidationError("Знак не найден.")
        data = _preserve_existing_guide_ids(data, existing_row)
        _validate_required_name(data)
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
            raise MarkValidationError("Знак не найден.")
        connection.commit()
    log_action("update", "mark", mark_id, {"fields": list(MARK_FIELDS)})


def mark_delete_preview(settings: Settings, mark_id: int) -> MarkDeletePreview:
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        row = connection.execute(
            "select front_foto, back_foto, book1_foto, book2_foto from mark where id = ?",
            (mark_id,),
        ).fetchone()
        if row is None:
            raise MarkValidationError("Знак не найден.")
        media = media_delete_preview(
            connection,
            settings,
            tuple(row[field] for field in ("front_foto", "back_foto", "book1_foto", "book2_foto")),
            excluded_rows=(MediaReferenceExclusion("mark", mark_id),),
            owned_folder=settings.rewards_data_dir / "SourceMark" / str(mark_id),
            owned_relative_prefix=f"SourceMark/{mark_id}",
        )
    return MarkDeletePreview(media)


def mark_delete_confirmation_message(preview: MarkDeletePreview) -> str:
    return confirmation_message("Удалить знак и принадлежащие ему материалы?", media=preview.media)


def delete_mark_with_result(
    settings: Settings,
    mark_id: int,
    confirm: bool = False,
    *,
    operation_id: str | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> MarkDeleteResult:
    ensure_dangerous_action_allowed(settings)
    if not confirm:
        raise MarkValidationError("Действие требует подтверждения.")
    operation_id = str(operation_id or uuid4().hex)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = connection.execute(
            "select front_foto, back_foto, book1_foto, book2_foto from mark where id = ?",
            (mark_id,),
        ).fetchone()
        if row is None:
            try:
                recorded = recorded_delete_plan(settings, operation_id)
            except DeletionLifecycleError as exc:
                raise MarkDeleteBlockedError("Некорректный идентификатор операции удаления.") from exc
            if recorded is None or recorded.entity_type != "mark" or recorded.entity_ids != (mark_id,):
                raise MarkValidationError("Знак не найден.")
            try:
                recovered = recover_delete_operation(settings, operation_id)
            except DeletionLifecycleError as exc:
                raise MarkDeleteBlockedError(
                    "Не удалось безопасно завершить удаление знака. Повторите действие или проверьте журнал."
                ) from exc
            return MarkDeleteResult(recovered)
        media_values = tuple(row[field] for field in ("front_foto", "back_foto", "book1_foto", "book2_foto"))

    try:
        plan = build_delete_plan(
            settings,
            operation_id=operation_id,
            entity_type="mark",
            entity_ids=(mark_id,),
            expected_row_counts=(RowCountExpectation("mark", "id", mark_id, 1),),
            reference_paths=media_values,
            excluded_rows=(MediaReferenceExclusion("mark", mark_id),),
            owned_paths=(mark_owned_directory(mark_id),),
        )
    except DeletionLifecycleError as exc:
        raise MarkDeleteBlockedError(
            "Нельзя безопасно удалить знак: путь к материалам не прошёл проверку."
        ) from exc

    def delete_database_row(connection) -> None:
        current = connection.execute(
            "select front_foto, back_foto, book1_foto, book2_foto from mark where id = ?",
            (mark_id,),
        ).fetchone()
        if current is None:
            raise MarkDeleteBlockedError("Знак изменился во время подготовки удаления.")
        current_media = tuple(
            current[field] for field in ("front_foto", "back_foto", "book1_foto", "book2_foto")
        )
        if current_media != media_values:
            raise MarkDeleteBlockedError("Материалы знака изменились во время подготовки удаления.")
        connection.execute("delete from mark where id = ?", (mark_id,))

    try:
        operation = execute_delete_plan(settings, plan, delete_database_row, fault_hook=fault_hook)
    except MarkDeleteBlockedError:
        raise
    except DeletionLifecycleError as exc:
        raise MarkDeleteBlockedError(
            "Нельзя безопасно удалить знак: обнаружены внешние ссылки или неоднозначные материалы."
        ) from exc
    log_action(
        "delete",
        "mark",
        mark_id,
        {
            "operation_id": operation.operation_id,
            "status": operation.status,
            "staged_paths": operation.staged_paths,
            "preserved_shared_references": operation.preserved_shared_references,
        },
    )
    return MarkDeleteResult(operation)


def delete_mark(settings: Settings, mark_id: int, confirm: bool = False) -> None:
    delete_mark_with_result(settings, mark_id, confirm=confirm)
