from pathlib import Path

from .common import fetch_all, fetch_one


def count_marks(db_path: Path) -> int:
    row = fetch_one(db_path, "select count(*) as count from mark")
    return int(row["count"]) if row else 0


def list_marks(db_path: Path, limit: int = 25, offset: int = 0) -> list[dict[str, object]]:
    return fetch_all(
        db_path,
        """
        select
            m.id,
            g0.name as gos,
            g1.name as category,
            g2.name as subcategory,
            g3.name as name,
            m.number,
            m.instock,
            m.price_now,
            m.front_foto,
            m.back_foto,
            coalesce(nullif(m.front_foto, ''), nullif(m.back_foto, '')) as thumbnail_path
        from mark m
        left join guide_lev_0 g0 on g0.id = m.id_gos
        left join guide_lev_1 g1 on g1.id = m.id_catigory
        left join guide_lev_2 g2 on g2.id = m.id_sub_catigory
        left join guide_lev_3 g3 on g3.id = m.id_name
        order by m.id
        limit ? offset ?
        """,
        (limit, offset),
    )


def get_mark(db_path: Path, mark_id: int) -> dict[str, object] | None:
    return fetch_one(
        db_path,
        """
        select
            m.id,
            g0.name as gos,
            g1.name as category,
            g2.name as subcategory,
            g3.name as name,
            m.id_link,
            m.number,
            m.instock,
            m.date_purchase,
            m.price_purchase,
            m.price_now,
            m.front_foto,
            m.back_foto,
            m.book1_foto,
            m.book2_foto
        from mark m
        left join guide_lev_0 g0 on g0.id = m.id_gos
        left join guide_lev_1 g1 on g1.id = m.id_catigory
        left join guide_lev_2 g2 on g2.id = m.id_sub_catigory
        left join guide_lev_3 g3 on g3.id = m.id_name
        where m.id = ?
        """,
        (mark_id,),
    )


def mark_photo_items(mark: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"label": "Фото знака: аверс", "path": mark.get("front_foto")},
        {"label": "Фото знака: реверс", "path": mark.get("back_foto")},
        {"label": "Фото книжки 1", "path": mark.get("book1_foto")},
        {"label": "Фото книжки 2", "path": mark.get("book2_foto")},
    ]
