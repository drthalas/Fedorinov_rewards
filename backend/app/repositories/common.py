from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
import sqlite3

from ..db import open_readonly_connection, row_to_dict


TABLES_TO_COUNT = [
    "person",
    "rewards",
    "mark",
    "guide",
    "guide_lev_0",
    "guide_lev_1",
    "guide_lev_2",
    "guide_lev_3",
    "guide_lev_4",
]


def fetch_all(db_path: Path, query: str, params: Iterable[object] = ()) -> list[dict[str, object]]:
    with closing(open_readonly_connection(db_path)) as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [row_to_dict(row) for row in rows if row is not None]


def fetch_one(db_path: Path, query: str, params: Iterable[object] = ()) -> dict[str, object] | None:
    with closing(open_readonly_connection(db_path)) as connection:
        row = connection.execute(query, tuple(params)).fetchone()
    return row_to_dict(row)


def table_counts(db_path: Path, tables: list[str] | None = None) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    selected = tables or TABLES_TO_COUNT
    with closing(open_readonly_connection(db_path)) as connection:
        existing = {
            row["name"]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
        for table in selected:
            if table not in existing:
                counts[table] = None
                continue
            counts[table] = connection.execute(f'select count(*) as count from "{table}"').fetchone()["count"]
    return counts


def db_readable(db_path: Path) -> bool:
    try:
        with closing(open_readonly_connection(db_path)) as connection:
            connection.execute("select 1").fetchone()
        return True
    except sqlite3.Error:
        return False
