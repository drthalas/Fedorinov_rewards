from pathlib import Path

from .common import fetch_all, fetch_one


def list_persons(db_path: Path) -> list[dict[str, object]]:
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
        """,
    )


def get_person(db_path: Path, person_id: int) -> dict[str, object] | None:
    return fetch_one(
        db_path,
        """
        select
            p.id,
            p.fio,
            p.birthday,
            p.id_rank,
            g.name as rank_name,
            p.person_foto,
            p.main_foto,
            p.rewards_foto,
            p.book1_foto,
            p.book2_foto,
            p.card1_foto,
            p.card2_foto,
            p.link1,
            p.link2,
            p.comment
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
        {"label": "Главное фото", "path": person.get("main_foto")},
        {"label": "Фото кавалера", "path": person.get("person_foto")},
        {"label": "Общее фото наград", "path": person.get("rewards_foto")},
        {"label": "Фото книжки 1", "path": person.get("book1_foto")},
        {"label": "Фото книжки 2", "path": person.get("book2_foto")},
        {"label": "Фото карточки 1", "path": person.get("card1_foto")},
        {"label": "Фото карточки 2", "path": person.get("card2_foto")},
    ]
    for reward in rewards:
        reward_name = reward.get("name") or f"Награда #{reward.get('id')}"
        items.extend(
            [
                {"label": f"{reward_name}: аверс", "path": reward.get("front_foto")},
                {"label": f"{reward_name}: реверс", "path": reward.get("back_foto")},
                {"label": f"{reward_name}: книжка 1", "path": reward.get("book1_foto")},
                {"label": f"{reward_name}: книжка 2", "path": reward.get("book2_foto")},
                {"label": f"{reward_name}: наградной лист", "path": reward.get("reward_list")},
            ]
        )
    return items
