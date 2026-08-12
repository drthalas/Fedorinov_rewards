from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
from typing import Callable
import unicodedata
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
    person_owned_directory,
    recorded_delete_plan,
    recover_delete_operation,
)
from ..services.dates import (
    BIRTH_YEAR_MAXIMUM,
    BIRTH_YEAR_MINIMUM,
    format_birth_year_input,
    normalize_birth_year_input,
)
from ..services.person_files import ensure_person_folder, safe_person_folder
from ..services.deletion_confirmation import (
    MediaDeletePreview,
    confirmation_message,
    folder_item_count,
    media_delete_preview,
)
from ..services.write_guard import ensure_dangerous_action_allowed, ensure_write_allowed


PERSON_BASE_FIELDS = ("fio", "birthday", "id_rank", "link1", "link2", "comment")
PERSON_OPTIONAL_FIELDS = ("biography",)
DUPLICATE_PERSON_MESSAGE = "Кавалер с такими ФИО, годом рождения и званием уже существует."


class PersonValidationError(ValueError):
    def __init__(self, message: str, *, field: str | None = None):
        super().__init__(message)
        self.field = field


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


@dataclass(frozen=True)
class PersonDeletePreview:
    reward_count: int
    person_media_count: int
    database_media_reference_count: int
    folder_item_count: int
    preserved_shared_reference_count: int = 0
    block_reason: str | None = None


@dataclass(frozen=True)
class PersonDeleteResult:
    operation: DeletionExecutionResult
    preview: PersonDeletePreview | None = None


@dataclass(frozen=True)
class _PersonDeleteSnapshot:
    person: tuple[tuple[str, object], ...]
    rewards: tuple[tuple[tuple[str, object], ...], ...]
    person_media: tuple[tuple[tuple[str, object], ...], ...]

    @property
    def reward_ids(self) -> tuple[int, ...]:
        return tuple(int(dict(row)["id"]) for row in self.rewards)

    @property
    def person_media_ids(self) -> tuple[int, ...]:
        return tuple(int(dict(row)["id"]) for row in self.person_media)

    @property
    def reference_paths(self) -> tuple[object, ...]:
        references: list[object] = []
        person = dict(self.person)
        references.extend(person.get(field) for field in PERSON_IMAGE_FIELDS if field in person)
        for raw_row in self.rewards:
            row = dict(raw_row)
            references.extend(row.get(field) for field in REWARD_IMAGE_FIELDS if field in row)
        for raw_row in self.person_media:
            row = dict(raw_row)
            if "file_path" in row:
                references.append(row.get("file_path"))
        return tuple(value for value in references if value not in {None, ""})


PERSON_IMAGE_FIELDS = (
    "person_foto",
    "main_foto",
    "rewards_foto",
    "book1_foto",
    "book2_foto",
    "card1_foto",
    "card2_foto",
)
REWARD_IMAGE_FIELDS = ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list")


def _empty_to_none(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def person_data_from_mapping(
    values: dict[str, object],
    *,
    existing_birthday: object = None,
) -> PersonWriteData:
    fio = str(values.get("fio") or "").strip()
    if not fio:
        raise PersonValidationError("Заполните ФИО.")

    raw_birthday = values.get("birthday")
    submitted_year = "" if raw_birthday is None else str(raw_birthday).strip()
    existing_year = format_birth_year_input(existing_birthday)
    preserves_legacy_year = bool(
        existing_year.isdigit()
        and len(existing_year) == 4
        and submitted_year == existing_year
        and not BIRTH_YEAR_MINIMUM <= int(existing_year) <= BIRTH_YEAR_MAXIMUM
    )
    if preserves_legacy_year:
        birthday = str(existing_birthday)
    else:
        try:
            birthday = normalize_birth_year_input(
                raw_birthday,
                required=True,
            )
        except ValueError as exc:
            raise PersonValidationError(str(exc), field="birthday") from exc

    rank_value = _empty_to_none(values.get("id_rank"))
    if rank_value is None:
        raise PersonValidationError("Выберите звание / специальность.")
    try:
        id_rank = int(rank_value) if rank_value is not None else None
    except (TypeError, ValueError) as exc:
        raise PersonValidationError("Некорректное звание/специальность") from exc

    return PersonWriteData(
        fio=fio,
        birthday=birthday,
        id_rank=id_rank,
        link1=_empty_to_none(values.get("link1")),
        link2=_empty_to_none(values.get("link2")),
        comment=_empty_to_none(values.get("comment")),
        biography=_empty_to_none(values.get("biography")),
    )


def _person_columns(connection) -> set[str]:
    return {row["name"] for row in connection.execute("pragma table_info(person)").fetchall()}


def _ensure_biography_column(connection) -> None:
    if "biography" not in _person_columns(connection):
        connection.execute("alter table person add column biography text")


def _active_fields(connection) -> tuple[str, ...]:
    columns = _person_columns(connection)
    optional = tuple(field for field in PERSON_OPTIONAL_FIELDS if field in columns)
    return (*PERSON_BASE_FIELDS, *optional)


def _as_params(data: PersonWriteData, fields: tuple[str, ...]) -> tuple[object, ...]:
    optional_text_fields = {"link1", "link2", "comment", "biography"}
    return tuple(
        _empty_to_none(getattr(data, field)) if field in optional_text_fields else getattr(data, field)
        for field in fields
    )


def _person_identity_name(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.split()).casefold()


def _find_person_duplicate(connection, data: PersonWriteData) -> int | None:
    expected_name = _person_identity_name(data.fio)
    expected_year = format_birth_year_input(data.birthday)
    rows = connection.execute(
        "select id, fio, birthday from person where id_rank = ? order by id",
        (data.id_rank,),
    ).fetchall()
    for row in rows:
        if _person_identity_name(row["fio"]) != expected_name:
            continue
        if format_birth_year_input(row["birthday"]) == expected_year:
            return int(row["id"])
    return None


def _validate_person_duplicate(connection, data: PersonWriteData) -> None:
    if _find_person_duplicate(connection, data) is not None:
        raise PersonValidationError(DUPLICATE_PERSON_MESSAGE)


def _validate_person_data(data: PersonWriteData, *, existing_birthday: object = None) -> None:
    if not data.fio.strip():
        raise PersonValidationError("Заполните ФИО.")
    submitted_year = format_birth_year_input(data.birthday)
    existing_year = format_birth_year_input(existing_birthday)
    preserves_legacy_year = bool(
        existing_year.isdigit()
        and len(existing_year) == 4
        and submitted_year == existing_year
        and not BIRTH_YEAR_MINIMUM <= int(existing_year) <= BIRTH_YEAR_MAXIMUM
    )
    if not preserves_legacy_year:
        try:
            normalize_birth_year_input(
                submitted_year,
                required=True,
            )
        except ValueError as exc:
            raise PersonValidationError(str(exc), field="birthday") from exc
    if data.id_rank is None:
        raise PersonValidationError("Выберите звание / специальность.")


def create_person_in_connection(connection, settings: Settings, data: PersonWriteData) -> tuple[int, Path | None, tuple[str, ...]]:
    _validate_person_data(data)
    _ensure_biography_column(connection)
    _validate_person_duplicate(connection, data)
    fields = _active_fields(connection)
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    cursor = connection.execute(
        f"insert into person ({columns}) values ({placeholders})",
        _as_params(data, fields),
    )
    person_id = int(cursor.lastrowid)
    folder = safe_person_folder(settings, person_id)
    folder_existed = folder.exists()
    ensure_person_folder(settings, person_id)
    return person_id, None if folder_existed else folder, fields


def create_person(settings: Settings, data: PersonWriteData) -> int:
    ensure_write_allowed(settings)
    created_folder = None
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        connection.execute("begin immediate")
        try:
            person_id, created_folder, fields = create_person_in_connection(connection, settings, data)
            connection.commit()
        except Exception:
            connection.rollback()
            if created_folder is not None:
                try:
                    created_folder.rmdir()
                except OSError:
                    pass
            raise
    log_action("create", "person", person_id, {"fields": list(fields)})
    return person_id


def update_person(settings: Settings, person_id: int, data: PersonWriteData) -> None:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        existing = connection.execute("select birthday from person where id = ?", (person_id,)).fetchone()
        if existing is None:
            raise PersonValidationError("Награжденный не найден.")
        _validate_person_data(data, existing_birthday=existing["birthday"])
        _ensure_biography_column(connection)
        fields = _active_fields(connection)
        assignments = ", ".join(f"{field} = ?" for field in fields)
        connection.execute(
            f"update person set {assignments} where id = ?",
            (*_as_params(data, fields), person_id),
        )
        connection.commit()
    log_action("update", "person", person_id, {"fields": list(fields)})


CONFIRM_REQUIRED_MESSAGE = "Действие требует подтверждения."


def _row_signature(row) -> tuple[tuple[str, object], ...]:
    return tuple((key, row[key]) for key in row.keys())


def _table_exists(connection, table: str) -> bool:
    return connection.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table,),
    ).fetchone() is not None


def _person_delete_snapshot(connection, person_id: int) -> _PersonDeleteSnapshot | None:
    person = connection.execute("select * from person where id = ?", (person_id,)).fetchone()
    if person is None:
        return None
    rewards = connection.execute(
        "select * from rewards where person_id = ? order by id",
        (person_id,),
    ).fetchall()
    person_media = (
        connection.execute(
            "select * from person_media where person_id = ? order by id",
            (person_id,),
        ).fetchall()
        if _table_exists(connection, "person_media")
        else []
    )
    return _PersonDeleteSnapshot(
        _row_signature(person),
        tuple(_row_signature(row) for row in rewards),
        tuple(_row_signature(row) for row in person_media),
    )


def person_delete_preview(settings: Settings, person_id: int) -> PersonDeletePreview:
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        snapshot = _person_delete_snapshot(connection, person_id)
        if snapshot is not None:
            exclusions = [MediaReferenceExclusion("person", person_id)]
            exclusions.extend(MediaReferenceExclusion("rewards", reward_id) for reward_id in snapshot.reward_ids)
            exclusions.extend(MediaReferenceExclusion("person_media", media_id) for media_id in snapshot.person_media_ids)
            media = media_delete_preview(
                connection,
                settings,
                snapshot.reference_paths,
                excluded_rows=tuple(exclusions),
                owned_folder=settings.rewards_data_dir / "Source" / str(person_id),
                owned_relative_prefix=f"Source/{person_id}",
            )
    if snapshot is None:
        raise PersonValidationError("Награжденный не найден.")
    return PersonDeletePreview(
        reward_count=len(snapshot.rewards),
        person_media_count=len(snapshot.person_media),
        database_media_reference_count=media.linked_media_count,
        folder_item_count=media.folder_item_count,
        preserved_shared_reference_count=media.preserved_shared_reference_count,
        block_reason=media.block_reason,
    )


def person_delete_confirmation_message(preview: PersonDeletePreview) -> str:
    return confirmation_message(
        "Удалить кавалера и все связанные данные?",
        child_counts=(
            ("наград", preview.reward_count),
            ("дополнительных материалов", preview.person_media_count),
        ),
        media=MediaDeletePreview(
            linked_media_count=preview.database_media_reference_count,
            folder_item_count=preview.folder_item_count,
            preserved_shared_reference_count=preview.preserved_shared_reference_count,
            block_reason=preview.block_reason,
        ),
    )


def delete_person_with_result(
    settings: Settings,
    person_id: int,
    confirm: bool = False,
    *,
    operation_id: str | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> PersonDeleteResult:
    ensure_dangerous_action_allowed(settings)
    if not confirm:
        raise PersonValidationError(CONFIRM_REQUIRED_MESSAGE)
    operation_id = str(operation_id or uuid4().hex)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        snapshot = _person_delete_snapshot(connection, person_id)
        if snapshot is None:
            try:
                recorded = recorded_delete_plan(settings, operation_id)
            except DeletionLifecycleError as exc:
                raise PersonDeleteBlockedError("Некорректный идентификатор операции удаления.") from exc
            if recorded is None or recorded.entity_type != "person" or recorded.entity_ids != (person_id,):
                raise PersonValidationError("Награжденный не найден.")
            try:
                recovered = recover_delete_operation(settings, operation_id)
            except DeletionLifecycleError as exc:
                raise PersonDeleteBlockedError(
                    "Не удалось безопасно завершить удаление кавалера. Повторите действие или проверьте журнал."
                ) from exc
            return PersonDeleteResult(recovered)

    preview = PersonDeletePreview(
        reward_count=len(snapshot.rewards),
        person_media_count=len(snapshot.person_media),
        database_media_reference_count=len(snapshot.reference_paths),
        folder_item_count=folder_item_count(settings.rewards_data_dir / "Source" / str(person_id)),
    )
    exclusions = [MediaReferenceExclusion("person", person_id)]
    exclusions.extend(MediaReferenceExclusion("rewards", reward_id) for reward_id in snapshot.reward_ids)
    exclusions.extend(MediaReferenceExclusion("person_media", media_id) for media_id in snapshot.person_media_ids)
    expected_counts = [
        RowCountExpectation("person", "id", person_id, 1),
        RowCountExpectation("rewards", "person_id", person_id, len(snapshot.rewards)),
    ]
    if snapshot.person_media:
        expected_counts.append(
            RowCountExpectation("person_media", "person_id", person_id, len(snapshot.person_media))
        )

    try:
        plan = build_delete_plan(
            settings,
            operation_id=operation_id,
            entity_type="person",
            entity_ids=(person_id,),
            expected_row_counts=tuple(expected_counts),
            reference_paths=snapshot.reference_paths,
            excluded_rows=tuple(exclusions),
            owned_paths=(person_owned_directory(person_id),),
        )
    except DeletionLifecycleError as exc:
        raise PersonDeleteBlockedError(
            "Нельзя безопасно удалить кавалера: путь к материалам не прошёл проверку."
        ) from exc

    def delete_database_rows(connection) -> None:
        current = _person_delete_snapshot(connection, person_id)
        if current != snapshot:
            raise PersonDeleteBlockedError("Данные кавалера изменились во время подготовки удаления.")
        connection.execute("delete from rewards where person_id = ?", (person_id,))
        if _table_exists(connection, "person_media"):
            connection.execute("delete from person_media where person_id = ?", (person_id,))
        cursor = connection.execute("delete from person where id = ?", (person_id,))
        if cursor.rowcount != 1:
            raise PersonValidationError("Награжденный не найден.")

    try:
        operation = execute_delete_plan(settings, plan, delete_database_rows, fault_hook=fault_hook)
    except PersonDeleteBlockedError:
        raise
    except DeletionLifecycleError as exc:
        raise PersonDeleteBlockedError(
            "Нельзя безопасно удалить кавалера: обнаружены внешние ссылки или неоднозначные материалы."
        ) from exc
    log_action(
        "delete",
        "person",
        person_id,
        {
            "operation_id": operation.operation_id,
            "status": operation.status,
            "rewards_deleted": preview.reward_count,
            "person_media_deleted": preview.person_media_count,
            "database_media_references": preview.database_media_reference_count,
            "folder_items": preview.folder_item_count,
            "staged_paths": operation.staged_paths,
            "preserved_shared_references": operation.preserved_shared_references,
        },
    )
    return PersonDeleteResult(operation, preview)


def delete_person(settings: Settings, person_id: int, confirm: bool = False) -> None:
    delete_person_with_result(settings, person_id, confirm=confirm)
