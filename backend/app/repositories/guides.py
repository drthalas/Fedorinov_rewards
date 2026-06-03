from pathlib import Path

from .common import fetch_all


def list_rank_guide(db_path: Path) -> list[dict[str, object]]:
    return fetch_all(db_path, "select id, name from guide order by id")


def list_guide_level(db_path: Path, level: int) -> list[dict[str, object]]:
    if level not in {0, 1, 2, 3, 4}:
        raise ValueError("guide level must be between 0 and 4")
    return fetch_all(db_path, f"select id, idl, name from guide_lev_{level} order by id")


def guide_tree(db_path: Path) -> list[dict[str, object]]:
    levels = {
        level: fetch_all(db_path, f"select id, idl, name from guide_lev_{level} order by id")
        for level in range(5)
    }

    def children(level: int, parent_id: int) -> list[dict[str, object]]:
        nodes: list[dict[str, object]] = []
        for row in levels[level]:
            if row.get("idl") != parent_id:
                continue
            node = {
                "id": row.get("id"),
                "name": row.get("name"),
                "level": level,
                "children": children(level + 1, int(row["id"])) if level < 4 else [],
            }
            nodes.append(node)
        return nodes

    return children(0, -1)
