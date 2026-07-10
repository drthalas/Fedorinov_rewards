from pathlib import Path

from .common import fetch_all, fetch_one


def list_rank_guide(db_path: Path) -> list[dict[str, object]]:
    rows = fetch_all(db_path, "select id, name from guide order by id")
    return sorted(rows, key=lambda row: (str(row.get("name") or "").casefold().replace("ё", "е"), int(row.get("id") or 0)))


def get_rank_guide_item(db_path: Path, rank_id: int) -> dict[str, object] | None:
    return fetch_one(db_path, "select id, name from guide where id = ?", (rank_id,))


def _guide_level_select(db_path: Path, level: int) -> str:
    columns = {row["name"] for row in fetch_all(db_path, f"pragma table_info(guide_lev_{level})")}
    rating_rank = "rating_rank" if "rating_rank" in columns else "null"
    image_path = "image_path" if "image_path" in columns else "null"
    return f"select id, idl, name, {rating_rank} as rating_rank, {image_path} as image_path from guide_lev_{level}"


def list_guide_level(db_path: Path, level: int) -> list[dict[str, object]]:
    if level not in {0, 1, 2, 3, 4}:
        raise ValueError("guide level must be between 0 and 4")
    return fetch_all(db_path, _guide_level_select(db_path, level) + " order by id")


def list_guide_level_children(db_path: Path, level: int, parent_id: int | None) -> list[dict[str, object]]:
    if level not in {1, 2, 3, 4}:
        raise ValueError("child guide level must be between 1 and 4")
    if parent_id is None:
        return []
    return fetch_all(db_path, _guide_level_select(db_path, level) + " where idl = ? order by id", (parent_id,))


def get_guide_level_item(db_path: Path, level: int, item_id: int) -> dict[str, object] | None:
    if level not in {0, 1, 2, 3, 4}:
        raise ValueError("guide level must be between 0 and 4")
    return fetch_one(db_path, _guide_level_select(db_path, level) + " where id = ?", (item_id,))


def guide_level_item_lineage(db_path: Path, level: int, item_id: int) -> list[dict[str, object]]:
    if level not in {0, 1, 2, 3, 4}:
        raise ValueError("guide level must be between 0 and 4")
    lineage: list[dict[str, object]] = []
    current_level = level
    current_id = item_id
    while current_level >= 0:
        item = get_guide_level_item(db_path, current_level, current_id)
        if item is None:
            return []
        lineage.append({**item, "level": current_level})
        if current_level == 0:
            break
        current_id = int(item.get("idl") or 0)
        current_level -= 1
    lineage.reverse()
    return lineage


def guide_cascade_data(db_path: Path) -> dict[str, list[dict[str, object]]]:
    return {
        "countries": list_guide_level(db_path, 0),
        "categories": list_guide_level(db_path, 1),
        "subcategories": list_guide_level(db_path, 2),
        "names": list_guide_level(db_path, 3),
    }


def guide_cascade_options(
    db_path: Path,
    *,
    country_id: int | None = None,
    category_id: int | None = None,
    subcategory_id: int | None = None,
) -> dict[str, list[dict[str, object]]]:
    return {
        "gos": list_guide_level(db_path, 0),
        "categories": list_guide_level_children(db_path, 1, country_id),
        "subcategories": list_guide_level_children(db_path, 2, category_id),
        "names": list_guide_level_children(db_path, 3, subcategory_id),
    }


def guide_tree(db_path: Path) -> list[dict[str, object]]:
    levels = {
        level: fetch_all(db_path, _guide_level_select(db_path, level) + " order by id")
        for level in range(5)
    }

    def children(level: int, parent_id: int, ancestor_keys: tuple[str, ...] = ()) -> list[dict[str, object]]:
        nodes: list[dict[str, object]] = []
        for row in levels[level]:
            if row.get("idl") != parent_id:
                continue
            guide_key = f"{level}-{row.get('id')}"
            node = {
                "id": row.get("id"),
                "name": row.get("name"),
                "level": level,
                "guide_key": guide_key,
                "ancestor_keys": ancestor_keys,
                "rating_rank": row.get("rating_rank"),
                "image_path": row.get("image_path"),
                "children": children(level + 1, int(row["id"]), (*ancestor_keys, guide_key)) if level < 4 else [],
            }
            nodes.append(node)
        return nodes

    return children(0, -1)
