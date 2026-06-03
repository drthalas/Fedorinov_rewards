from pathlib import Path

from .common import fetch_one


def get_reward(db_path: Path, reward_id: int) -> dict[str, object] | None:
    return fetch_one(
        db_path,
        """
        select
            r.id,
            r.person_id,
            p.fio,
            r.id_gos,
            g0.name as gos,
            r.id_catigory,
            g1.name as category,
            r.id_sub_catigory,
            g2.name as subcategory,
            r.id_name,
            g3.name as name,
            r.id_link,
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
        left join person p on p.id = r.person_id
        left join guide_lev_0 g0 on g0.id = r.id_gos
        left join guide_lev_1 g1 on g1.id = r.id_catigory
        left join guide_lev_2 g2 on g2.id = r.id_sub_catigory
        left join guide_lev_3 g3 on g3.id = r.id_name
        where r.id = ?
        """,
        (reward_id,),
    )


def reward_photo_items(reward: dict[str, object]) -> list[dict[str, object]]:
    return [
        {"label": "Фото награды: аверс", "path": reward.get("front_foto")},
        {"label": "Фото награды: реверс", "path": reward.get("back_foto")},
        {"label": "Фото книжки 1", "path": reward.get("book1_foto")},
        {"label": "Фото книжки 2", "path": reward.get("book2_foto")},
        {"label": "Наградной лист", "path": reward.get("reward_list")},
    ]
