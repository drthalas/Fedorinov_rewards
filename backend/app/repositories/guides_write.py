from contextlib import closing
from dataclasses import dataclass

from ..config import Settings
from ..db import open_write_connection
from ..services.audit import log_action
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


@dataclass(frozen=True)
class GuideLevelData:
    level: int
    name: str
    parent_id: int


def _name_from_mapping(values: dict[str, object]) -> str:
    name = str(values.get("name") or "").strip()
    if not name:
        raise GuideValidationError("Название обязательно")
    return name


def rank_data_from_mapping(values: dict[str, object]) -> RankGuideData:
    return RankGuideData(name=_name_from_mapping(values))


def _validate_level(level: int) -> int:
    if level not in GUIDE_LEVELS:
        raise GuideValidationError("Некорректный уровень справочника")
    return level


def _optional_int(value: object, default: int | None = None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError as exc:
        raise GuideValidationError("Некорректный родительский элемент") from exc


def guide_level_data_from_mapping(level: int, values: dict[str, object]) -> GuideLevelData:
    safe_level = _validate_level(level)
    name = _name_from_mapping(values)
    if safe_level == 0:
        parent_id = -1
    else:
        parent_id = _optional_int(values.get("parent_id"))
        if parent_id is None:
            raise GuideValidationError("Выберите родительский элемент")
    return GuideLevelData(level=safe_level, name=name, parent_id=parent_id)


def _rank_exists(connection, rank_id: int) -> bool:
    return connection.execute("select 1 from guide where id = ?", (rank_id,)).fetchone() is not None


def _guide_item_exists(connection, level: int, item_id: int) -> bool:
    _validate_level(level)
    return connection.execute(f"select 1 from guide_lev_{level} where id = ?", (item_id,)).fetchone() is not None


def _validate_parent(connection, data: GuideLevelData) -> None:
    if data.level == 0:
        return
    if not _guide_item_exists(connection, data.level - 1, data.parent_id):
        raise GuideValidationError("Родительский элемент не найден")


def create_rank(settings: Settings, data: RankGuideData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        cursor = connection.execute("insert into guide (name) values (?)", (data.name,))
        rank_id = int(cursor.lastrowid)
        connection.commit()
    log_action("create", "guide_rank", rank_id, {"fields": ["name"]})
    return rank_id


def update_rank(settings: Settings, rank_id: int, data: RankGuideData) -> None:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        cursor = connection.execute("update guide set name = ? where id = ?", (data.name, rank_id))
        if cursor.rowcount == 0:
            raise GuideValidationError("Звание/специальность не найдены")
        connection.commit()
    log_action("update", "guide_rank", rank_id, {"fields": ["name"]})


def delete_rank(settings: Settings, rank_id: int) -> None:
    ensure_dangerous_action_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if not _rank_exists(connection, rank_id):
            raise GuideValidationError("Звание/специальность не найдены")
        used = connection.execute("select count(*) as count from person where id_rank = ?", (rank_id,)).fetchone()["count"]
        if int(used) > 0:
            raise GuideDeleteBlockedError("Нельзя удалить: значение используется в карточках награждённых.")
        connection.execute("delete from guide where id = ?", (rank_id,))
        connection.commit()
    log_action("delete", "guide_rank", rank_id, {"blocked_if_used_by_person": True})


def create_guide_level_item(settings: Settings, data: GuideLevelData) -> int:
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        _validate_parent(connection, data)
        cursor = connection.execute(
            f"insert into guide_lev_{data.level} (idl, name) values (?, ?)",
            (data.parent_id, data.name),
        )
        item_id = int(cursor.lastrowid)
        connection.commit()
    log_action("create", f"guide_lev_{data.level}", item_id, {"level": data.level, "parent_id": data.parent_id})
    return item_id


def update_guide_level_item(settings: Settings, level: int, item_id: int, data: GuideLevelData) -> None:
    safe_level = _validate_level(level)
    if data.level != safe_level:
        raise GuideValidationError("Некорректный уровень справочника")
    ensure_write_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        _validate_parent(connection, data)
        cursor = connection.execute(
            f"update guide_lev_{safe_level} set idl = ?, name = ? where id = ?",
            (data.parent_id, data.name, item_id),
        )
        if cursor.rowcount == 0:
            raise GuideValidationError("Элемент справочника не найден")
        connection.commit()
    log_action("update", f"guide_lev_{safe_level}", item_id, {"level": safe_level, "fields": ["idl", "name"]})


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


def delete_guide_level_item(settings: Settings, level: int, item_id: int) -> None:
    safe_level = _validate_level(level)
    ensure_dangerous_action_allowed(settings)
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        if not _guide_item_exists(connection, safe_level, item_id):
            raise GuideValidationError("Элемент справочника не найден")
        if safe_level < 4:
            child_count = connection.execute(
                f"select count(*) as count from guide_lev_{safe_level + 1} where idl = ?",
                (item_id,),
            ).fetchone()["count"]
            if int(child_count) > 0:
                raise GuideDeleteBlockedError("Нельзя удалить: у элемента есть дочерние записи.")
        if _usage_count(connection, safe_level, item_id) > 0:
            raise GuideDeleteBlockedError("Нельзя удалить: значение используется в наградах или знаках.")
        connection.execute(f"delete from guide_lev_{safe_level} where id = ?", (item_id,))
        connection.commit()
    log_action("delete", f"guide_lev_{safe_level}", item_id, {"level": safe_level, "cascade_deleted": False})
