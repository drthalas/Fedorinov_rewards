from pathlib import Path

from .common import fetch_all, fetch_one


def _count(db_path: Path, query: str, params: tuple[object, ...]) -> int:
    row = fetch_one(db_path, query, params)
    return int(row["count"]) if row else 0


def search_all(db_path: Path, query: str, limit: int = 25) -> dict[str, object]:
    like = f"%{query.strip()}%"
    counts = {
        "persons": _count(db_path, "select count(*) as count from person p where p.fio like ?", (like,)),
        "rewards": _count(
            db_path,
            """
            select count(*) as count
            from rewards r
            left join guide_lev_3 g3 on g3.id = r.id_name
            where g3.name like ? or cast(r.number as text) like ?
            """,
            (like, like),
        ),
        "marks": _count(
            db_path,
            """
            select count(*) as count
            from mark m
            left join guide_lev_3 g3 on g3.id = m.id_name
            where g3.name like ? or cast(m.number as text) like ?
            """,
            (like, like),
        ),
    }

    persons = fetch_all(
        db_path,
        """
        select p.id, p.fio, p.birthday, g.name as rank_name
        from person p
        left join guide g on g.id = p.id_rank
        where p.fio like ?
        order by p.id
        limit ?
        """,
        (like, limit),
    )
    rewards = fetch_all(
        db_path,
        """
        select r.id, r.person_id, p.fio, g3.name as name, r.number, r.instock
        from rewards r
        left join person p on p.id = r.person_id
        left join guide_lev_3 g3 on g3.id = r.id_name
        where g3.name like ? or cast(r.number as text) like ?
        order by r.id
        limit ?
        """,
        (like, like, limit),
    )
    marks = fetch_all(
        db_path,
        """
        select m.id, g3.name as name, m.number, m.instock
        from mark m
        left join guide_lev_3 g3 on g3.id = m.id_name
        where g3.name like ? or cast(m.number as text) like ?
        order by m.id
        limit ?
        """,
        (like, like, limit),
    )
    return {"persons": persons, "rewards": rewards, "marks": marks, "counts": counts, "limit": limit}
