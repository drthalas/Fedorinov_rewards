from contextlib import closing
from pathlib import Path

from ..db import open_readonly_connection


_REFERENCE_SELECT = """
    select
        g0.id as id_gos,
        g0.name as gos,
        g1.id as id_catigory,
        g1.name as category,
        g2.id as id_sub_catigory,
        g2.name as subcategory,
        g3.id as id_name,
        g3.name as name,
        nullif((
            select group_concat(link.name, ' ')
            from (
                select name
                from guide_lev_4
                where idl = g3.id
                order by id
            ) as link
        ), '') as id_link
    from guide_lev_3 as g3
    join guide_lev_2 as g2 on g2.id = g3.idl
    join guide_lev_1 as g1 on g1.id = g2.idl
    join guide_lev_0 as g0 on g0.id = g1.idl
"""


def reward_reference_from_connection(connection, name_id: int) -> dict[str, object] | None:
    row = connection.execute(_REFERENCE_SELECT + " where g3.id = ?", (name_id,)).fetchone()
    return dict(row) if row is not None else None


def get_reward_reference(db_path: Path, name_id: int) -> dict[str, object] | None:
    with closing(open_readonly_connection(db_path)) as connection:
        return reward_reference_from_connection(connection, name_id)


def list_reward_references(db_path: Path) -> list[dict[str, object]]:
    with closing(open_readonly_connection(db_path)) as connection:
        return [dict(row) for row in connection.execute(_REFERENCE_SELECT + " order by g3.id").fetchall()]
