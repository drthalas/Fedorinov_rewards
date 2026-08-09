from dataclasses import dataclass
from contextlib import closing
from pathlib import Path
import unicodedata

from ..db import open_readonly_connection, row_to_dict
from .common import fetch_all, fetch_one
from .guides import guide_cascade_data, guide_cascade_options, list_rank_guide
from .summary import parse_optional_int


@dataclass(frozen=True)
class LegacyRewardsFilters:
    rank_id: int | None = None
    country_id: int | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    name_id: int | None = None


@dataclass(frozen=True)
class LegacyRewardsSort:
    field: str = "fio"
    direction: str = "asc"


LEGACY_REWARDS_SORT_FIELDS = {"fio", "birthday", "rank_name", "rewards_count"}
LEGACY_PERSON_ALPHABET = tuple("АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
LEGACY_PERSON_DIGITS = tuple("123456789")
LEGACY_PERSON_GROUPS = LEGACY_PERSON_ALPHABET + LEGACY_PERSON_DIGITS


def normalized_legacy_rewards_sort(
    sort_by: str | None = None,
    sort_dir: str | None = None,
) -> LegacyRewardsSort:
    field = str(sort_by or "fio").strip()
    if field not in LEGACY_REWARDS_SORT_FIELDS:
        field = "fio"
    direction = "desc" if str(sort_dir or "").strip().lower() == "desc" else "asc"
    return LegacyRewardsSort(field=field, direction=direction)


def person_name_sort_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return normalized.replace("ё", "е")


def person_name_initial(value: object) -> str:
    key = person_name_sort_key(value)
    if not key:
        return ""
    initial = key[0].upper()
    return initial if initial in LEGACY_PERSON_GROUPS else ""


def normalized_legacy_rewards_letter(value: object) -> str:
    return person_name_initial(value)


def _sort_legacy_reward_persons(
    rows: list[dict[str, object]],
    sorting: LegacyRewardsSort,
) -> list[dict[str, object]]:
    alphabetical = sorted(
        rows,
        key=lambda row: (person_name_sort_key(row.get("fio")), int(row.get("id") or 0)),
    )
    if sorting.field == "fio":
        return list(reversed(alphabetical)) if sorting.direction == "desc" else alphabetical

    if sorting.field == "rewards_count":
        value_key = lambda row: int(row.get("rewards_count") or 0)
    elif sorting.field == "birthday":
        value_key = lambda row: str(row.get("birthday") or "").strip()
    else:
        value_key = lambda row: person_name_sort_key(row.get("rank_name"))
    return sorted(alphabetical, key=value_key, reverse=sorting.direction == "desc")


def normalized_legacy_rewards_filters(
    rank_id: str | int | None = None,
    country_id: str | int | None = None,
    category_id: str | int | None = None,
    subcategory_id: str | int | None = None,
    name_id: str | int | None = None,
) -> LegacyRewardsFilters:
    return LegacyRewardsFilters(
        rank_id=parse_optional_int(rank_id),
        country_id=parse_optional_int(country_id),
        category_id=parse_optional_int(category_id),
        subcategory_id=parse_optional_int(subcategory_id),
        name_id=parse_optional_int(name_id),
    )


def legacy_rewards_filter_options(
    db_path: Path,
    filters: LegacyRewardsFilters | None = None,
) -> dict[str, list[dict[str, object]]]:
    filters = filters or LegacyRewardsFilters()
    cascade = guide_cascade_options(
        db_path,
        country_id=filters.country_id,
        category_id=filters.category_id,
        subcategory_id=filters.subcategory_id,
    )
    return {
        "ranks": list_rank_guide(db_path),
        "countries": cascade["gos"],
        "categories": cascade["categories"],
        "subcategories": cascade["subcategories"],
        "names": cascade["names"],
    }


def legacy_rewards_filter_cascade(db_path: Path) -> dict[str, list[dict[str, object]]]:
    return guide_cascade_data(db_path)


def _reward_filter_clauses(filters: LegacyRewardsFilters, alias: str = "r") -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filters.country_id is not None:
        clauses.append(f"{alias}.id_gos = ?")
        params.append(filters.country_id)
    if filters.category_id is not None:
        clauses.append(f"{alias}.id_catigory = ?")
        params.append(filters.category_id)
    if filters.subcategory_id is not None:
        clauses.append(f"{alias}.id_sub_catigory = ?")
        params.append(filters.subcategory_id)
    if filters.name_id is not None:
        clauses.append(f"{alias}.id_name = ?")
        params.append(filters.name_id)
    return clauses, params


def _person_where(filters: LegacyRewardsFilters) -> tuple[list[str], list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filters.rank_id is not None:
        clauses.append("p.id_rank = ?")
        params.append(filters.rank_id)

    reward_clauses, reward_params = _reward_filter_clauses(filters, "rf")
    if reward_clauses:
        clauses.append(
            "exists (select 1 from rewards rf where rf.person_id = p.id and "
            + " and ".join(reward_clauses)
            + ")"
        )
        params.extend(reward_params)
    return clauses, params


def _where_sql(clauses: list[str]) -> str:
    return " where " + " and ".join(clauses) if clauses else ""


def list_legacy_reward_persons(
    db_path: Path,
    filters: LegacyRewardsFilters,
    sorting: LegacyRewardsSort | None = None,
) -> list[dict[str, object]]:
    clauses, params = _person_where(filters)
    rows = fetch_all(
        db_path,
        f"""
        select
            p.id,
            p.fio,
            p.birthday,
            g.name as rank_name,
            p.main_foto,
            p.person_foto,
            coalesce(p.main_foto, p.person_foto, '') as thumbnail_path,
            count(r.id) as rewards_count
        from person p
        left join guide g on g.id = p.id_rank
        left join rewards r on r.person_id = p.id
        {_where_sql(clauses)}
        group by p.id
        """,
        params,
    )
    return _sort_legacy_reward_persons(rows, sorting or LegacyRewardsSort())


def _register_person_name_functions(connection) -> None:
    connection.create_function("person_name_key", 1, person_name_sort_key, deterministic=True)
    connection.create_function("person_name_initial", 1, person_name_initial, deterministic=True)


def list_legacy_reward_person_group(
    db_path: Path,
    filters: LegacyRewardsFilters,
    sorting: LegacyRewardsSort | None = None,
    *,
    letter: object = "",
    query: object = "",
) -> list[dict[str, object]]:
    clauses, params = _person_where(filters)
    normalized_query = person_name_sort_key(query)
    normalized_letter = normalized_legacy_rewards_letter(letter)
    if normalized_query:
        clauses.append("instr(person_name_key(p.fio), ?) > 0")
        params.append(normalized_query)
    elif normalized_letter:
        clauses.append("person_name_initial(p.fio) = ?")
        params.append(normalized_letter)
    else:
        return []

    with closing(open_readonly_connection(db_path)) as connection:
        _register_person_name_functions(connection)
        rows = connection.execute(
            f"""
            select
                p.id,
                p.fio,
                p.birthday,
                g.name as rank_name,
                p.main_foto,
                p.person_foto,
                coalesce(p.main_foto, p.person_foto, '') as thumbnail_path,
                count(r.id) as rewards_count
            from person p
            left join guide g on g.id = p.id_rank
            left join rewards r on r.person_id = p.id
            {_where_sql(clauses)}
            group by p.id
            """,
            tuple(params),
        ).fetchall()
    return _sort_legacy_reward_persons(
        [row_to_dict(row) for row in rows if row is not None],
        sorting or LegacyRewardsSort(),
    )


def legacy_rewards_group_counts(
    db_path: Path,
    filters: LegacyRewardsFilters,
) -> dict[str, int]:
    clauses, params = _person_where(filters)
    clauses.append("person_name_initial(p.fio) <> ''")
    with closing(open_readonly_connection(db_path)) as connection:
        _register_person_name_functions(connection)
        rows = connection.execute(
            f"""
            select person_name_initial(p.fio) as letter, count(*) as person_count
            from person p
            {_where_sql(clauses)}
            group by person_name_initial(p.fio)
            """,
            tuple(params),
        ).fetchall()
    counts = {group: 0 for group in LEGACY_PERSON_GROUPS}
    for row in rows:
        letter = str(row["letter"] or "")
        if letter in counts:
            counts[letter] = int(row["person_count"] or 0)
    return counts


def legacy_rewards_alphabet_counts(
    db_path: Path,
    filters: LegacyRewardsFilters,
) -> dict[str, int]:
    counts = legacy_rewards_group_counts(db_path, filters)
    return {letter: counts[letter] for letter in LEGACY_PERSON_ALPHABET}


def legacy_rewards_totals(db_path: Path, filters: LegacyRewardsFilters) -> dict[str, object]:
    person_clauses, person_params = _person_where(filters)
    reward_clauses, reward_params = _reward_filter_clauses(filters, "r")
    reward_where = " and " + " and ".join(reward_clauses) if reward_clauses else ""
    params = [*person_params, *reward_params]

    return fetch_one(
        db_path,
        f"""
        with filtered_persons as (
            select p.id
            from person p
            {_where_sql(person_clauses)}
        )
        select
            (select count(*) from filtered_persons) as persons_total,
            count(r.id) as rewards_total,
            coalesce(sum(case when lower(cast(r.instock as text)) in ('true', '1', 'yes', 'да') then 1 else 0 end), 0) as in_stock,
            coalesce(sum(case when lower(cast(r.instock as text)) in ('false', '0', 'no', 'нет') then 1 else 0 end), 0) as not_in_stock,
            coalesce(sum(cast(r.price_purchase as integer)), 0) as price_purchase_sum,
            coalesce(sum(cast(r.price_now as integer)), 0) as price_now_sum,
            max(r.date_purchase) as last_purchase_date
        from rewards r
        join filtered_persons fp on fp.id = r.person_id
        where 1 = 1
        {reward_where}
        """,
        params,
    ) or {
        "persons_total": 0,
        "rewards_total": 0,
        "in_stock": 0,
        "not_in_stock": 0,
        "price_purchase_sum": 0,
        "price_now_sum": 0,
        "last_purchase_date": None,
    }
