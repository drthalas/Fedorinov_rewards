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
    guide_owned_image,
    recorded_delete_plan,
    recover_delete_operation,
)
from ..services.guide_images import normalize_guide_image_path
from ..services.deletion_confirmation import MediaDeletePreview, confirmation_message, media_delete_preview
from ..services.write_guard import ensure_dangerous_action_allowed, ensure_write_allowed


GUIDE_LEVELS = {0, 1, 2, 3, 4}
LEVEL_USAGE_FIELDS = {
    0: "id_gos",
    1: "id_catigory",
    2: "id_sub_catigory",
    3: "id_name",
}


class GuideValidationError(ValueError):
    pass


class GuideDeleteBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class RankGuideData:
    name: str
    image_path: str | None = None


@dataclass(frozen=True)
class GuideLevelData:
    level: int
    name: str
    parent_id: int
    rating_rank: int | None = None
    image_path: str | None = None


@dataclass(frozen=True)
class RankDeletePreview:
    used_count: int
    media: MediaDeletePreview

    @property
    def blocked(self) -> bool:
        return self.used_count > 0 or self.media.block_reason is not None


@dataclass(frozen=True)
class GuideDeletePreview:
    child_count: int
    usage_count: int
    media: MediaDeletePreview

    @property
    def blocked(self) -> bool:
        return self.child_count > 0 or self.usage_count > 0 or self.media.block_reason is not None


def _name_from_mapping(values: dict[str, object]) -> str:
    name = str(values.get("name") or "").strip()
    if not name:
        raise GuideValidationError("Заполните название.")
    return name


def rank_data_from_mapping(values: dict[str, object]) -> RankGuideData:
    return RankGuideData(name=_name_from_mapping(values))


def _validate_level(level: int) -> int:
    if level not in GUIDE_LEVELS:
        raise GuideValidationError("Некорректный уровень справочника.")
    return level


def _optional_int(value: object, default: int | None = None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError as exc:
        raise GuideValidationError("Некорректный родительский элемент.") from exc


def _rating_rank_from_mapping(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        rating_rank = int(text)
    except ValueError as exc:
        raise GuideValidationError("Рейтинг должен быть положительным целым числом.") from exc
    if rating_rank <= 0:
        raise GuideValidationError("Рейтинг должен быть положительным целым числом.")
    return rating_rank


def guide_level_data_from_mapping(level: int, values: dict[str, object]) -> GuideLevelData:
    safe_level = _validate_level(level)
    name = _name_from_mapping(values)
    if safe_level == 0:
        parent_id = -1
    else:
        parent_id = _optional_int(values.get("parent_id"))
        if parent_id is None:
            raise GuideValidationError("Выберите родительский элемент.")
    return GuideLevelData(
        level=safe_level,
        name=name,
        parent_id=parent_id,
        rating_rank=_rating_rank_from_mapping(values.get("rating_rank")),
    )


def _guide_level_columns(connection, level: int) -> set[str]:
    return {row["name"] for row in connection.execute(f"pragma table_info(guide_lev_{level})").fetchall()}


def _ensure_guide_metadata_columns(connection, level: int) -> None:
    columns = _guide_level_columns(connection, level)
    if "rating_rank" not in columns:
        connection.execute(f"alter table guide_lev_{level} add column rating_rank integer")
    if "image_path" not in columns:
        connection.execute(f"alter table guide_lev_{level} add column image_path text")


def _validated_image_path(value: object) -> str | None:
    if value is None or value == "":
        return None
    try:
        return normalize_guide_image_path(value)
    except ValueError as exc:
        raise GuideValidationError(str(exc)) from exc


def _validated_rating_rank(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise GuideValidationError("Рейтинг должен быть положительным целым числом.")
    try:
        rating_rank = int(value)
    except (TypeError, ValueError) as exc:
        raise GuideValidationError("Рейтинг должен быть положительным целым числом.") from exc
    if str(value).strip() != str(rating_rank) or rating_rank <= 0:
        raise GuideValidationError("Рейтинг должен быть положительным целым числом.")
    return rating_rank


def _rank_exists(connection, rank_id: int) -> bool:
    return connection.execute("select 1 from guide where id = ?", (rank_id,)).fetchone() is not None


def _ensure_rank_image_column(connection) -> None:
    columns = {row["name"] for row in connection.execute("pragma table_info(guide)").fetchall()}
    if "image_path" not in columns:
        connection.execute("alter table guide add column image_path text")


def _guide_item_exists(connection, level: int, item_id: int) -> bool:
    _validate_level(level)
    return connection.execute(f"select 1 from guide_lev_{level} where id = ?", (item_id,)).fetchone() is not None


def _validate_parent(connection, data: GuideLevelData) -> None:
    if data.level == 0:
        return
    if not _guide_item_exists(connection, data.level - 1, data.parent_id):
        raise GuideValidationError("Родительский элемент не найден.")


def create_rank(settings: Settings, data: RankGuideData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        _ensure_rank_image_column(connection)
        image_path = _validated_image_path(data.image_path)
        cursor = connection.execute("insert into guide (name, image_path) values (?, ?)", (data.name, image_path))
        rank_id = int(cursor.lastrowid)
        connection.commit()
    log_action("create", "guide_rank", rank_id, {"fields": ["name", "image_path"], "has_image": bool(image_path)})
    return rank_id


def update_rank(settings: Settings, rank_id: int, data: RankGuideData) -> None:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        _ensure_rank_image_column(connection)
        image_path = _validated_image_path(data.image_path)
        cursor = connection.execute(
            "update guide set name = ?, image_path = ? where id = ?",
            (data.name, image_path, rank_id),
        )
        if cursor.rowcount == 0:
            raise GuideValidationError("Звание/специальность не найдены.")
        connection.commit()
    log_action("update", "guide_rank", rank_id, {"fields": ["name", "image_path"], "has_image": bool(image_path)})


CONFIRM_REQUIRED_MESSAGE = "Действие требует подтверждения."


def _row_signature(row) -> tuple[tuple[str, object], ...]:
    return tuple((key, row[key]) for key in row.keys())


def _recover_missing_delete(
    settings: Settings,
    operation_id: str,
    entity_type: str,
    entity_id: int,
) -> DeletionExecutionResult:
    try:
        recorded = recorded_delete_plan(settings, operation_id)
    except DeletionLifecycleError as exc:
        raise GuideDeleteBlockedError("Некорректный идентификатор операции удаления.") from exc
    if recorded is None or recorded.entity_type != entity_type or recorded.entity_ids != (entity_id,):
        raise GuideValidationError("Элемент справочника не найден.")
    try:
        return recover_delete_operation(settings, operation_id)
    except DeletionLifecycleError as exc:
        raise GuideDeleteBlockedError(
            "Не удалось безопасно завершить удаление. Повторите действие или проверьте журнал."
        ) from exc


def _rank_unused(connection, rank_id: int) -> None:
    used = connection.execute("select count(*) as count from person where id_rank = ?", (rank_id,)).fetchone()["count"]
    if int(used) > 0:
        raise GuideDeleteBlockedError("Нельзя удалить: значение используется в карточках награждённых.")


def _rank_delete_preview_in_connection(connection, settings: Settings, rank_id: int) -> RankDeletePreview:
    row = connection.execute("select * from guide where id = ?", (rank_id,)).fetchone()
    if row is None:
        raise GuideValidationError("Звание/специальность не найдены.")
    columns = set(row.keys())
    image_path = row["image_path"] if "image_path" in columns else None
    used_count = int(
        connection.execute("select count(*) as count from person where id_rank = ?", (rank_id,)).fetchone()["count"]
    )
    media = media_delete_preview(
        connection,
        settings,
        (image_path,),
        excluded_rows=(MediaReferenceExclusion("guide", rank_id),),
    )
    if image_path not in {None, ""}:
        try:
            normalize_guide_image_path(image_path)
        except ValueError:
            media = MediaDeletePreview(
                media.linked_media_count,
                media.folder_item_count,
                media.preserved_shared_reference_count,
                "Путь изображения звания не прошёл безопасную проверку.",
            )
    return RankDeletePreview(used_count, media)


def rank_delete_preview(settings: Settings, rank_id: int) -> RankDeletePreview:
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        return _rank_delete_preview_in_connection(connection, settings, rank_id)


def rank_delete_previews(settings: Settings, rank_ids: tuple[int, ...]) -> dict[int, RankDeletePreview]:
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        return {
            rank_id: _rank_delete_preview_in_connection(connection, settings, rank_id)
            for rank_id in rank_ids
        }


def rank_delete_confirmation_message(preview: RankDeletePreview) -> str:
    block_reason = (
        f"звание используется в карточках кавалеров ({preview.used_count})"
        if preview.used_count
        else preview.media.block_reason
    )
    return confirmation_message(
        "Удалить звание/специальность?",
        media=preview.media,
        block_reason=block_reason,
    )


def delete_rank(
    settings: Settings,
    rank_id: int,
    confirm: bool = False,
    *,
    operation_id: str | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> DeletionExecutionResult:
    ensure_dangerous_action_allowed(settings)
    if not confirm:
        raise GuideValidationError(CONFIRM_REQUIRED_MESSAGE)
    operation_id = str(operation_id or uuid4().hex)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = connection.execute("select * from guide where id = ?", (rank_id,)).fetchone()
        if row is None:
            return _recover_missing_delete(settings, operation_id, "guide_rank", rank_id)
        _rank_unused(connection, rank_id)
        snapshot = _row_signature(row)
        image_path = dict(snapshot).get("image_path")

    try:
        owned_paths = (guide_owned_image(settings, image_path),) if image_path not in {None, ""} else ()
        plan = build_delete_plan(
            settings,
            operation_id=operation_id,
            entity_type="guide_rank",
            entity_ids=(rank_id,),
            expected_row_counts=(RowCountExpectation("guide", "id", rank_id, 1),),
            reference_paths=(image_path,) if image_path not in {None, ""} else (),
            excluded_rows=(MediaReferenceExclusion("guide", rank_id),),
            owned_paths=owned_paths,
        )
    except DeletionLifecycleError as exc:
        raise GuideDeleteBlockedError("Нельзя безопасно удалить изображение звания/специальности.") from exc

    def delete_database_row(connection) -> None:
        current = connection.execute("select * from guide where id = ?", (rank_id,)).fetchone()
        if current is None or _row_signature(current) != snapshot:
            raise GuideDeleteBlockedError("Звание/специальность изменились во время подготовки удаления.")
        _rank_unused(connection, rank_id)
        connection.execute("delete from guide where id = ?", (rank_id,))

    try:
        result = execute_delete_plan(settings, plan, delete_database_row, fault_hook=fault_hook)
    except GuideDeleteBlockedError:
        raise
    except DeletionLifecycleError as exc:
        raise GuideDeleteBlockedError("Нельзя безопасно удалить изображение звания/специальности.") from exc
    log_action(
        "delete",
        "guide_rank",
        rank_id,
        {
            "blocked_if_used_by_person": True,
            "operation_id": result.operation_id,
            "status": result.status,
            "staged_paths": result.staged_paths,
            "preserved_shared_references": result.preserved_shared_references,
        },
    )
    return result


def create_guide_level_item(settings: Settings, data: GuideLevelData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        _validate_parent(connection, data)
        _ensure_guide_metadata_columns(connection, data.level)
        rating_rank = _validated_rating_rank(data.rating_rank)
        image_path = _validated_image_path(data.image_path)
        cursor = connection.execute(
            f"insert into guide_lev_{data.level} (idl, name, rating_rank, image_path) values (?, ?, ?, ?)",
            (data.parent_id, data.name, rating_rank, image_path),
        )
        item_id = int(cursor.lastrowid)
        connection.commit()
    log_action(
        "create",
        f"guide_lev_{data.level}",
        item_id,
        {
            "level": data.level,
            "parent_id": data.parent_id,
            "fields": ["idl", "name", "rating_rank", "image_path"],
            "has_image": bool(image_path),
        },
    )
    return item_id


def update_guide_level_item(settings: Settings, level: int, item_id: int, data: GuideLevelData) -> None:
    safe_level = _validate_level(level)
    if data.level != safe_level:
        raise GuideValidationError("Некорректный уровень справочника.")
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        _validate_parent(connection, data)
        _ensure_guide_metadata_columns(connection, safe_level)
        rating_rank = _validated_rating_rank(data.rating_rank)
        image_path = _validated_image_path(data.image_path)
        cursor = connection.execute(
            f"update guide_lev_{safe_level} set idl = ?, name = ?, rating_rank = ?, image_path = ? where id = ?",
            (data.parent_id, data.name, rating_rank, image_path, item_id),
        )
        if cursor.rowcount == 0:
            raise GuideValidationError("Элемент справочника не найден.")
        connection.commit()
    log_action(
        "update",
        f"guide_lev_{safe_level}",
        item_id,
        {"level": safe_level, "fields": ["idl", "name", "rating_rank", "image_path"]},
    )


def clear_guide_level_image(settings: Settings, level: int, item_id: int) -> str | None:
    safe_level = _validate_level(level)
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if not _guide_item_exists(connection, safe_level, item_id):
            raise GuideValidationError("Элемент справочника не найден.")
        _ensure_guide_metadata_columns(connection, safe_level)
        row = connection.execute(f"select image_path from guide_lev_{safe_level} where id = ?", (item_id,)).fetchone()
        image_path = str(row["image_path"] or "") if row is not None else ""
        connection.execute(f"update guide_lev_{safe_level} set image_path = null where id = ?", (item_id,))
        connection.commit()
    log_action("guide_image_cleared", f"guide_lev_{safe_level}", item_id, {"image_path_cleared": True})
    return image_path or None


def _usage_count(connection, level: int, item_id: int) -> int:
    if level in LEVEL_USAGE_FIELDS:
        field = LEVEL_USAGE_FIELDS[level]
        rewards = connection.execute(f"select count(*) as count from rewards where {field} = ?", (item_id,)).fetchone()["count"]
        marks = connection.execute(f"select count(*) as count from mark where {field} = ?", (item_id,)).fetchone()["count"]
        return int(rewards) + int(marks)
    if level == 4:
        row = connection.execute("select name from guide_lev_4 where id = ?", (item_id,)).fetchone()
        if row is None:
            return 0
        name = str(row["name"] or "")
        if not name:
            return 0
        pattern = f"%{name}%"
        rewards = connection.execute("select count(*) as count from rewards where id_link like ?", (pattern,)).fetchone()["count"]
        marks = connection.execute("select count(*) as count from mark where id_link like ?", (pattern,)).fetchone()["count"]
        return int(rewards) + int(marks)
    return 0


def _assert_guide_item_deletable(connection, level: int, item_id: int) -> None:
    if level < 4:
        child_count = connection.execute(
            f"select count(*) as count from guide_lev_{level + 1} where idl = ?",
            (item_id,),
        ).fetchone()["count"]
        if int(child_count) > 0:
            raise GuideDeleteBlockedError("Нельзя удалить: у элемента есть дочерние записи.")
    if _usage_count(connection, level, item_id) > 0:
        raise GuideDeleteBlockedError("Нельзя удалить: значение используется в наградах или знаках.")


def _guide_delete_preview_in_connection(
    connection,
    settings: Settings,
    level: int,
    item_id: int,
) -> GuideDeletePreview:
    safe_level = _validate_level(level)
    table = f"guide_lev_{safe_level}"
    row = connection.execute(f"select * from {table} where id = ?", (item_id,)).fetchone()
    if row is None:
        raise GuideValidationError("Элемент справочника не найден.")
    child_count = 0
    if safe_level < 4:
        child_count = int(
            connection.execute(
                f"select count(*) as count from guide_lev_{safe_level + 1} where idl = ?",
                (item_id,),
            ).fetchone()["count"]
        )
    usage_count = _usage_count(connection, safe_level, item_id)
    image_path = row["image_path"] if safe_level == 3 and "image_path" in row.keys() else None
    media = media_delete_preview(
        connection,
        settings,
        (image_path,),
        excluded_rows=(MediaReferenceExclusion(table, item_id),),
    )
    if image_path not in {None, ""}:
        try:
            normalize_guide_image_path(image_path)
        except ValueError:
            media = MediaDeletePreview(
                media.linked_media_count,
                media.folder_item_count,
                media.preserved_shared_reference_count,
                "Путь изображения элемента не прошёл безопасную проверку.",
            )
    return GuideDeletePreview(child_count, usage_count, media)


def guide_delete_preview(settings: Settings, level: int, item_id: int) -> GuideDeletePreview:
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        return _guide_delete_preview_in_connection(connection, settings, level, item_id)


def guide_delete_previews(
    settings: Settings,
    item_keys: tuple[tuple[int, int], ...],
) -> dict[str, GuideDeletePreview]:
    with closing(open_readonly_connection(settings.rewards_db_path)) as connection:
        return {
            f"{level}-{item_id}": _guide_delete_preview_in_connection(connection, settings, level, item_id)
            for level, item_id in item_keys
        }


def guide_delete_confirmation_message(preview: GuideDeletePreview) -> str:
    if preview.child_count:
        block_reason = f"у элемента есть дочерние записи ({preview.child_count})"
    elif preview.usage_count:
        block_reason = f"значение используется в наградах или знаках ({preview.usage_count})"
    else:
        block_reason = preview.media.block_reason
    return confirmation_message(
        "Удалить элемент справочника?",
        media=preview.media,
        block_reason=block_reason,
    )


def delete_guide_level_item(
    settings: Settings,
    level: int,
    item_id: int,
    confirm: bool = False,
    *,
    operation_id: str | None = None,
    fault_hook: Callable[[str], None] | None = None,
) -> DeletionExecutionResult:
    safe_level = _validate_level(level)
    ensure_dangerous_action_allowed(settings)
    if not confirm:
        raise GuideValidationError(CONFIRM_REQUIRED_MESSAGE)
    operation_id = str(operation_id or uuid4().hex)
    table = f"guide_lev_{safe_level}"
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        row = connection.execute(f"select * from {table} where id = ?", (item_id,)).fetchone()
        if row is None:
            return _recover_missing_delete(settings, operation_id, table, item_id)
        _assert_guide_item_deletable(connection, safe_level, item_id)
        snapshot = _row_signature(row)
        image_path = dict(snapshot).get("image_path") if safe_level == 3 else None

    try:
        owned_paths = (guide_owned_image(settings, image_path),) if image_path not in {None, ""} else ()
        plan = build_delete_plan(
            settings,
            operation_id=operation_id,
            entity_type=table,
            entity_ids=(item_id,),
            expected_row_counts=(RowCountExpectation(table, "id", item_id, 1),),
            reference_paths=(image_path,) if image_path not in {None, ""} else (),
            excluded_rows=(MediaReferenceExclusion(table, item_id),),
            owned_paths=owned_paths,
        )
    except DeletionLifecycleError as exc:
        raise GuideDeleteBlockedError("Нельзя безопасно удалить изображение элемента справочника.") from exc

    def delete_database_row(connection) -> None:
        current = connection.execute(f"select * from {table} where id = ?", (item_id,)).fetchone()
        if current is None or _row_signature(current) != snapshot:
            raise GuideDeleteBlockedError("Элемент справочника изменился во время подготовки удаления.")
        _assert_guide_item_deletable(connection, safe_level, item_id)
        connection.execute(f"delete from {table} where id = ?", (item_id,))

    try:
        result = execute_delete_plan(settings, plan, delete_database_row, fault_hook=fault_hook)
    except GuideDeleteBlockedError:
        raise
    except DeletionLifecycleError as exc:
        raise GuideDeleteBlockedError("Нельзя безопасно удалить изображение элемента справочника.") from exc
    log_action(
        "delete",
        table,
        item_id,
        {
            "level": safe_level,
            "cascade_deleted": False,
            "operation_id": result.operation_id,
            "status": result.status,
            "staged_paths": result.staged_paths,
            "preserved_shared_references": result.preserved_shared_references,
        },
    )
    return result
