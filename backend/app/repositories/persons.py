from contextlib import closing
from pathlib import Path

from .common import fetch_all, fetch_one
from ..db import open_readonly_connection
from ..services.photos import PERSON_PHOTO_FIELDS, REWARD_PHOTO_FIELDS


def person_has_biography(db_path: Path) -> bool:
    with closing(open_readonly_connection(db_path)) as connection:
        columns = {row["name"] for row in connection.execute("pragma table_info(person)").fetchall()}
    return "biography" in columns


def rank_guide_has_image(db_path: Path) -> bool:
    with closing(open_readonly_connection(db_path)) as connection:
        columns = {row["name"] for row in connection.execute("pragma table_info(guide)").fetchall()}
    return "image_path" in columns


def count_persons(db_path: Path) -> int:
    row = fetch_one(db_path, "select count(*) as count from person")
    return int(row["count"]) if row else 0


def list_persons(db_path: Path, limit: int = 25, offset: int = 0) -> list[dict[str, object]]:
    return fetch_all(
        db_path,
        """
        select
            p.id,
            p.fio,
            p.birthday,
            g.name as rank_name,
            p.main_foto,
            p.person_foto,
            coalesce(nullif(p.main_foto, ''), nullif(p.person_foto, '')) as thumbnail_path,
            count(r.id) as rewards_count
        from person p
        left join guide g on g.id = p.id_rank
        left join rewards r on r.person_id = p.id
        group by p.id
        order by p.id
        limit ? offset ?
        """,
        (limit, offset),
    )


def get_person(db_path: Path, person_id: int) -> dict[str, object] | None:
    biography_expr = "p.biography" if person_has_biography(db_path) else "null"
    rank_image_expr = "g.image_path" if rank_guide_has_image(db_path) else "null"
    return fetch_one(
        db_path,
        f"""
        select
            p.id,
            p.fio,
            p.birthday,
            p.id_rank,
            g.name as rank_name,
            {rank_image_expr} as rank_image_path,
            p.person_foto,
            p.main_foto,
            p.rewards_foto,
            p.book1_foto,
            p.book2_foto,
            p.card1_foto,
            p.card2_foto,
            p.link1,
            p.link2,
            p.comment,
            {biography_expr} as biography
        from person p
        left join guide g on g.id = p.id_rank
        where p.id = ?
        """,
        (person_id,),
    )


def list_person_rewards(db_path: Path, person_id: int) -> list[dict[str, object]]:
    return fetch_all(
        db_path,
        """
        select
            r.id,
            r.person_id,
            g0.name as gos,
            g1.name as category,
            g2.name as subcategory,
            g3.name as name,
            r.number,
            r.instock,
            r.date_purchase,
            r.price_purchase,
            r.price_now,
            r.front_foto,
            r.back_foto,
            r.book1_foto,
            r.book2_foto,
            r.reward_list
        from rewards r
        left join guide_lev_0 g0 on g0.id = r.id_gos
        left join guide_lev_1 g1 on g1.id = r.id_catigory
        left join guide_lev_2 g2 on g2.id = r.id_sub_catigory
        left join guide_lev_3 g3 on g3.id = r.id_name
        where r.person_id = ?
        order by r.id
        """,
        (person_id,),
    )


def person_photo_items(person: dict[str, object], rewards: list[dict[str, object]]) -> list[dict[str, object]]:
    items = [
        {"field": item.field, "label": item.label, "path": person.get(item.field)}
        for item in PERSON_PHOTO_FIELDS
    ]
    for reward in rewards:
        reward_name = reward.get("name") or f"Награда #{reward.get('id')}"
        for item in REWARD_PHOTO_FIELDS:
            items.append({"field": item.field, "label": f"{reward_name}: {item.label}", "path": reward.get(item.field)})
    return items
