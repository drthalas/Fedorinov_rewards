#!/usr/bin/env python3
"""Generate deterministic, synthetic Sergey-scale benchmark data under TEMP only."""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import random
import sqlite3
import tempfile
import time


DEFAULT_SEED = 3020718
PERSON_COUNT = 13_573
REWARD_COUNT = 24_189
PROFILE_NAMES = ("sergey-count-matched", "sergey-stress")

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGP8z4AATAxEcQAz0i0Ase8BBzXJf8sAAAAASUVORK5CYII="
)


@dataclass(frozen=True)
class ProfileSpec:
    name: str
    heavy_counts: tuple[int, ...]
    heavy_unique_media: bool


PROFILES = {
    "sergey-count-matched": ProfileSpec(
        name="sergey-count-matched",
        heavy_counts=(300, 150, 75),
        heavy_unique_media=False,
    ),
    "sergey-stress": ProfileSpec(
        name="sergey-stress",
        heavy_counts=(1_200, 800, 500, 300),
        heavy_unique_media=True,
    ),
}


SCHEMA = """
create table guide (
    id integer primary key autoincrement,
    name varchar,
    image_path text
);
create table guide_lev_0 (id integer primary key autoincrement, idl integer, name varchar);
create table guide_lev_1 (id integer primary key autoincrement, idl integer, name varchar);
create table guide_lev_2 (id integer primary key autoincrement, idl integer, name varchar);
create table guide_lev_3 (
    id integer primary key autoincrement,
    idl integer,
    name varchar,
    rating_rank integer,
    image_path text
);
create table guide_lev_4 (id integer primary key autoincrement, idl integer, name varchar);
create table person (
    id integer primary key autoincrement,
    fio varchar,
    birthday date,
    id_rank integer,
    person_foto varchar,
    main_foto varchar,
    rewards_foto varchar,
    book1_foto varchar,
    book2_foto varchar,
    card1_foto varchar,
    card2_foto varchar,
    link1 varchar,
    link2 varchar,
    comment text,
    biography text
);
create table rewards (
    id integer primary key autoincrement,
    person_id integer,
    id_gos integer,
    id_catigory integer,
    id_sub_catigory integer,
    id_name integer,
    number integer,
    instock boolean,
    date_purchase date,
    price_purchase integer,
    price_now integer,
    front_foto varchar,
    back_foto varchar,
    id_link text null default null,
    book1_foto varchar,
    book2_foto varchar,
    reward_list varchar
);
create table mark (
    id integer primary key autoincrement,
    id_gos integer,
    id_catigory integer,
    id_sub_catigory integer,
    id_name integer,
    number integer,
    instock boolean,
    date_purchase date,
    price_purchase integer,
    price_now integer,
    front_foto varchar,
    back_foto varchar,
    id_link text null default null,
    book1_foto varchar,
    book2_foto varchar
);
create table person_media (
    id integer primary key autoincrement,
    person_id integer not null,
    photo_field text,
    title text not null,
    description text,
    file_path text,
    sort_order integer not null default 0,
    created_at text not null default current_timestamp,
    updated_at text not null default current_timestamp,
    foreign key (person_id) references person(id) on delete cascade,
    unique (person_id, photo_field)
);
create index idx_person_media_person on person_media(person_id, sort_order, id);
"""


def _temp_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    allowed_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    if not any(resolved != root and root in resolved.parents for root in allowed_roots):
        allowed = ", ".join(str(root) for root in sorted(allowed_roots))
        raise ValueError(f"Output root must be a unique child of an allowed TEMP root: {allowed}")
    if resolved.exists():
        raise FileExistsError(f"Output root already exists: {resolved}")
    return resolved


def _write_image(root: Path, relative: str) -> None:
    normalized = relative.replace("\\", "/")
    target = root / normalized
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PNG_BYTES)


def _reward_distribution(
    spec: ProfileSpec,
    person_count: int,
    reward_count: int,
    seed: int,
) -> tuple[list[int], list[int]]:
    if person_count < len(spec.heavy_counts) + 4:
        raise ValueError("person_count is too small for the selected profile")
    if reward_count < sum(spec.heavy_counts) + 7:
        raise ValueError("reward_count is too small for the selected profile")

    rng = random.Random(seed)
    counts = [0] * (person_count + 1)
    counts[1] = 0
    counts[2] = 2
    counts[3] = 5
    heavy_ids = list(range(person_count, person_count - len(spec.heavy_counts), -1))
    for person_id, count in zip(heavy_ids, spec.heavy_counts, strict=True):
        counts[person_id] = count

    reserved = {1, 2, 3, *heavy_ids}
    choices = (0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 4)
    adjustable = [person_id for person_id in range(1, person_count + 1) if person_id not in reserved]
    rng.shuffle(adjustable)
    for person_id in adjustable:
        counts[person_id] = choices[rng.randrange(len(choices))]

    difference = reward_count - sum(counts)
    cursor = 0
    while difference:
        person_id = adjustable[cursor % len(adjustable)]
        cursor += 1
        if difference > 0 and counts[person_id] < 5:
            counts[person_id] += 1
            difference -= 1
        elif difference < 0 and counts[person_id] > 0:
            counts[person_id] -= 1
            difference += 1
    return counts, heavy_ids


def _guide_rows() -> dict[str, list[tuple[object, ...]]]:
    countries = [(index, -1, f"Тестовая страна {index:02d}") for index in range(1, 5)]
    categories = [
        (index, ((index - 1) % len(countries)) + 1, f"Тестовая категория {index:02d}")
        for index in range(1, 13)
    ]
    subcategories = [
        (index, ((index - 1) % len(categories)) + 1, f"Тестовая подкатегория {index:02d}")
        for index in range(1, 25)
    ]
    names = [
        (
            index,
            ((index - 1) % len(subcategories)) + 1,
            f"Тестовая награда {index:03d}",
            index % 10,
            f"GuideImages/награда-{index:03d}.png" if index % 17 == 0 else None,
        )
        for index in range(1, 121)
    ]
    links = [
        (index, ((index - 1) % len(names)) + 1, f"Тестовая ссылка {index:03d}")
        for index in range(1, 81)
    ]
    ranks = [
        (
            index,
            f"Тестовое звание {index:02d}",
            f"GuideImages/звание-{index:02d}.png" if index in {1, 7, 13} else None,
        )
        for index in range(1, 21)
    ]
    return {
        "ranks": ranks,
        "countries": countries,
        "categories": categories,
        "subcategories": subcategories,
        "names": names,
        "links": links,
    }


def _person_media_path(person_id: int) -> tuple[str | None, bool]:
    if person_id == 2:
        return "Source/2/обычный-портрет.png", True
    if person_id % 503 == 0:
        return "Source/benchmark-shared/shared.png", True
    if person_id % 777 == 0:
        return f"Source\\{person_id}\\портрет.png", True
    if person_id % 307 == 0:
        return f"Source/{person_id}/missing.png", False
    if person_id % 97 == 0:
        return f"Source/{person_id}/портрет.png", True
    return None, False


def _reward_media_path(
    spec: ProfileSpec,
    person_id: int,
    reward_id: int,
    ordinal: int,
    heavy_ids: set[int],
) -> tuple[str | None, bool]:
    if person_id in heavy_ids:
        if ordinal % 113 == 0:
            return "Source/benchmark-shared/shared.png", True
        if ordinal % 71 == 0:
            return f"Source\\{person_id}\\награда-{ordinal:04d}.png", ordinal % 142 == 0
        if spec.heavy_unique_media or ordinal % 3 == 0:
            return f"Source/{person_id}/награда-{ordinal:04d}.png", ordinal % 50 == 0
    if reward_id % 1009 == 0:
        return "Source/benchmark-shared/shared.png", True
    if reward_id % 613 == 0:
        return f"Source/{person_id}/missing-reward-{reward_id}.png", False
    return None, False


def _relationship_health(connection: sqlite3.Connection) -> dict[str, int]:
    checks = {
        "reward_person_missing": "select count(*) from rewards r left join person p on p.id=r.person_id where p.id is null",
        "person_rank_missing": "select count(*) from person p left join guide g on g.id=p.id_rank where p.id_rank is not null and g.id is null",
        "reward_country_missing": "select count(*) from rewards r left join guide_lev_0 g on g.id=r.id_gos where g.id is null",
        "reward_category_missing": "select count(*) from rewards r left join guide_lev_1 g on g.id=r.id_catigory where g.id is null",
        "reward_subcategory_missing": "select count(*) from rewards r left join guide_lev_2 g on g.id=r.id_sub_catigory where g.id is null",
        "reward_name_missing": "select count(*) from rewards r left join guide_lev_3 g on g.id=r.id_name where g.id is null",
        "person_media_person_missing": "select count(*) from person_media m left join person p on p.id=m.person_id where p.id is null",
    }
    return {name: int(connection.execute(sql).fetchone()[0]) for name, sql in checks.items()}


def _tree_fingerprint(root: Path) -> str:
    digest = sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def generate_profile(
    profile: str,
    output_root: Path,
    *,
    seed: int = DEFAULT_SEED,
    person_count: int = PERSON_COUNT,
    reward_count: int = REWARD_COUNT,
) -> dict[str, object]:
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile: {profile}")
    spec = PROFILES[profile]
    root = _temp_root(output_root)
    started = time.perf_counter()
    root.mkdir(parents=True)
    db_path = root / "database/MyDatabase.sqlite"
    db_path.parent.mkdir(parents=True)

    counts, heavy_ids = _reward_distribution(spec, person_count, reward_count, seed)
    guides = _guide_rows()
    heavy_set = set(heavy_ids)
    first_reward_by_person: dict[int, int] = {}
    written_media: set[str] = set()

    with closing(sqlite3.connect(db_path)) as connection:
        connection.execute("pragma foreign_keys=on")
        connection.executescript(SCHEMA)
        connection.executemany("insert into guide (id,name,image_path) values (?,?,?)", guides["ranks"])
        connection.executemany("insert into guide_lev_0 (id,idl,name) values (?,?,?)", guides["countries"])
        connection.executemany("insert into guide_lev_1 (id,idl,name) values (?,?,?)", guides["categories"])
        connection.executemany("insert into guide_lev_2 (id,idl,name) values (?,?,?)", guides["subcategories"])
        connection.executemany(
            "insert into guide_lev_3 (id,idl,name,rating_rank,image_path) values (?,?,?,?,?)",
            guides["names"],
        )
        connection.executemany("insert into guide_lev_4 (id,idl,name) values (?,?,?)", guides["links"])

        person_rows: list[tuple[object, ...]] = []
        person_media_rows: list[tuple[object, ...]] = []
        for person_id in range(1, person_count + 1):
            media_path, exists = _person_media_path(person_id)
            if media_path and exists:
                written_media.add(media_path)
            person_rows.append(
                (
                    person_id,
                    f"Тестовый Кавалер {person_id:05d}",
                    f"{1930 + person_id % 70:04d}-01-01",
                    (person_id % len(guides["ranks"])) + 1,
                    media_path,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    f"Синтетический комментарий {person_id:05d}",
                    f"Синтетическая биография для benchmark-записи {person_id:05d}.",
                )
            )
            if person_id == 2 or person_id % 500 == 0:
                additional_path = (
                    "Source/benchmark-shared/shared.png"
                    if person_id % 1_000 == 0
                    else f"Source/{person_id}/дополнительное-фото.png"
                )
                written_media.add(additional_path)
                person_media_rows.append(
                    (
                        person_id,
                        f"additional_{person_id}",
                        "Синтетический материал",
                        "Benchmark fixture",
                        additional_path,
                        0,
                        "2026-01-01T00:00:00",
                        "2026-01-01T00:00:00",
                    )
                )
        connection.executemany(
            """
            insert into person (
                id,fio,birthday,id_rank,person_foto,main_foto,rewards_foto,
                book1_foto,book2_foto,card1_foto,card2_foto,link1,link2,comment,biography
            ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            person_rows,
        )
        connection.executemany(
            """
            insert into person_media (
                person_id,photo_field,title,description,file_path,sort_order,created_at,updated_at
            ) values (?,?,?,?,?,?,?,?)
            """,
            person_media_rows,
        )

        reward_rows: list[tuple[object, ...]] = []
        reward_id = 0
        for person_id in range(1, person_count + 1):
            for ordinal in range(1, counts[person_id] + 1):
                reward_id += 1
                first_reward_by_person.setdefault(person_id, reward_id)
                name_id = ((reward_id - 1) % len(guides["names"])) + 1
                subcategory_id = int(guides["names"][name_id - 1][1])
                category_id = int(guides["subcategories"][subcategory_id - 1][1])
                country_id = int(guides["categories"][category_id - 1][1])
                media_path, exists = _reward_media_path(
                    spec,
                    person_id,
                    reward_id,
                    ordinal,
                    heavy_set,
                )
                if media_path and exists:
                    written_media.add(media_path)
                reward_rows.append(
                    (
                        reward_id,
                        person_id,
                        country_id,
                        category_id,
                        subcategory_id,
                        name_id,
                        reward_id % 10_000,
                        reward_id % 2,
                        f"202{reward_id % 6}-01-01",
                        reward_id % 500,
                        reward_id % 700,
                        media_path,
                        None,
                        None,
                        None,
                        None,
                        None,
                    )
                )
                if len(reward_rows) >= 5_000:
                    connection.executemany(
                        """
                        insert into rewards (
                            id,person_id,id_gos,id_catigory,id_sub_catigory,id_name,number,
                            instock,date_purchase,price_purchase,price_now,front_foto,back_foto,
                            id_link,book1_foto,book2_foto,reward_list
                        ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        reward_rows,
                    )
                    reward_rows.clear()
        if reward_rows:
            connection.executemany(
                """
                insert into rewards (
                    id,person_id,id_gos,id_catigory,id_sub_catigory,id_name,number,
                    instock,date_purchase,price_purchase,price_now,front_foto,back_foto,
                    id_link,book1_foto,book2_foto,reward_list
                ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                reward_rows,
            )

        mark_rows: list[tuple[object, ...]] = []
        for mark_id in range(1, 201):
            name_id = ((mark_id - 1) % len(guides["names"])) + 1
            subcategory_id = int(guides["names"][name_id - 1][1])
            category_id = int(guides["subcategories"][subcategory_id - 1][1])
            country_id = int(guides["categories"][category_id - 1][1])
            image_path = f"SourceMark/{mark_id}/лицевая.png" if mark_id % 20 == 0 else None
            if image_path:
                written_media.add(image_path)
            mark_rows.append(
                (
                    mark_id,
                    country_id,
                    category_id,
                    subcategory_id,
                    name_id,
                    mark_id,
                    mark_id % 2,
                    "2026-01-01",
                    mark_id,
                    mark_id * 2,
                    image_path,
                    None,
                    None,
                    None,
                    None,
                )
            )
        connection.executemany(
            """
            insert into mark (
                id,id_gos,id_catigory,id_sub_catigory,id_name,number,instock,date_purchase,
                price_purchase,price_now,front_foto,back_foto,id_link,book1_foto,book2_foto
            ) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            mark_rows,
        )

        connection.commit()
        integrity = str(connection.execute("pragma integrity_check").fetchone()[0])
        fk_violations = len(connection.execute("pragma foreign_key_check").fetchall())
        relationship_health = _relationship_health(connection)
        actual_persons = int(connection.execute("select count(*) from person").fetchone()[0])
        actual_rewards = int(connection.execute("select count(*) from rewards").fetchone()[0])

    written_media.update(
        path
        for _, _, path in guides["ranks"]
        if path
    )
    written_media.update(
        str(row[4])
        for row in guides["names"]
        if row[4]
    )
    for relative in sorted(written_media):
        _write_image(root, relative)

    elapsed = time.perf_counter() - started
    distribution = Counter(counts[1:])
    manifest: dict[str, object] = {
        "profile": profile,
        "seed": seed,
        "persons": actual_persons,
        "rewards": actual_rewards,
        "marks": 200,
        "guide_assumptions": {
            "ranks": len(guides["ranks"]),
            "countries": len(guides["countries"]),
            "categories": len(guides["categories"]),
            "subcategories": len(guides["subcategories"]),
            "names": len(guides["names"]),
            "links": len(guides["links"]),
            "note": "Synthetic assumptions; Sergey marks/guides/media counts are unknown.",
        },
        "reward_distribution": {str(key): value for key, value in sorted(distribution.items())},
        "heavy_persons": [
            {"id": person_id, "rewards": counts[person_id]}
            for person_id in heavy_ids
        ],
        "fixture_ids": {
            "zero_person": 1,
            "ordinary_person": 2,
            "many_person": 3,
            "heavy_person": heavy_ids[0],
            "ordinary_reward": first_reward_by_person[2],
            "many_reward": first_reward_by_person[3],
            "heavy_reward": first_reward_by_person[heavy_ids[0]],
            "mark": 20,
            "blocked_rank": 1,
            "guide_country": 1,
            "guide_category": 1,
            "guide_subcategory": 1,
            "guide_name": 1,
        },
        "integrity_check": integrity,
        "foreign_key_violations": fk_violations,
        "relationship_health": relationship_health,
        "generation_seconds": round(elapsed, 6),
        "db_bytes": db_path.stat().st_size,
        "db_sha256": sha256(db_path.read_bytes()).hexdigest(),
        "media_files": len(written_media),
        "tree_fingerprint": _tree_fingerprint(root),
    }
    if actual_persons != person_count or actual_rewards != reward_count:
        raise RuntimeError(f"Unexpected counts: persons={actual_persons}, rewards={actual_rewards}")
    if integrity != "ok" or fk_violations or any(relationship_health.values()):
        raise RuntimeError(
            f"Generated database failed health checks: integrity={integrity}, "
            f"fk={fk_violations}, relationships={relationship_health}"
        )
    (root / "benchmark_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILE_NAMES, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate_profile(args.profile, args.output_root, seed=args.seed)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
