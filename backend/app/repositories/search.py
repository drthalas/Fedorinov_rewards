from __future__ import annotations

from pathlib import Path
from math import ceil
from time import perf_counter

from .common import fetch_all


VALID_SCOPES = {"all", "persons", "rewards", "reward_numbers", "marks"}
VALID_MODES = {"contains", "starts", "exact"}
DEFAULT_LIMIT = 50
MAX_LIMIT = 10000


def _normalize(value: object) -> str:
    text = str(value or "").strip().casefold()
    return text.replace("ё", "е")


def _clean_scope(scope: str) -> str:
    return scope if scope in VALID_SCOPES else "all"


def _clean_mode(mode: str) -> str:
    return mode if mode in VALID_MODES else "contains"


def _matches(value: object, needle: str, mode: str) -> bool:
    haystack = _normalize(value)
    if not haystack:
        return False
    if mode == "exact":
        return haystack == needle
    if mode == "starts":
        return haystack.startswith(needle)
    return needle in haystack


def _row_matches(row: dict[str, object], fields: tuple[str, ...], needle: str, mode: str) -> bool:
    return any(_matches(row.get(field), needle, mode) for field in fields)


def _slice_groups(
    groups: list[list[dict[str, object]]],
    offset: int,
    limit: int,
) -> list[list[dict[str, object]]]:
    remaining_offset = max(0, offset)
    remaining_limit = max(0, limit)
    sliced_groups: list[list[dict[str, object]]] = []
    for rows in groups:
        if remaining_limit <= 0:
            sliced_groups.append([])
            continue
        if remaining_offset >= len(rows):
            remaining_offset -= len(rows)
            sliced_groups.append([])
            continue
        selected = rows[remaining_offset : remaining_offset + remaining_limit]
        sliced_groups.append(selected)
        remaining_limit -= len(selected)
        remaining_offset = 0
    return sliced_groups


def _sort_rows(rows: list[dict[str, object]], sort_by: str, sort_dir: str) -> list[dict[str, object]]:
    clean_sort = str(sort_by or "").strip()
    clean_dir = "desc" if str(sort_dir or "").strip().lower() == "desc" else "asc"
    if not clean_sort:
        return rows

    numeric_fields = {
        "id",
        "number",
        "price_purchase",
        "price_now",
        "instock",
        "person_foto_flag",
        "main_foto_flag",
        "rewards_foto_flag",
        "book1_foto_flag",
        "book2_foto_flag",
        "card1_foto_flag",
        "card2_foto_flag",
        "person_book1_foto_flag",
        "person_book2_foto_flag",
        "person_card1_foto_flag",
        "person_card2_foto_flag",
        "front_foto_flag",
        "back_foto_flag",
        "reward_list_flag",
    }

    def sortable(row: dict[str, object]) -> object:
        value = row.get(clean_sort)
        if clean_sort in numeric_fields:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0
        return str(value or "").casefold()

    return sorted(rows, key=lambda row: (sortable(row), str(row.get("fio") or "").casefold(), int(row.get("id") or 0)), reverse=clean_dir == "desc")


def _pagination(total: int, limit: int, requested_page: int) -> dict[str, int]:
    page_size = max(1, min(int(limit), MAX_LIMIT))
    page_count = max(1, ceil(total / page_size)) if total else 1
    page = max(1, min(int(requested_page), page_count))
    offset = (page - 1) * page_size if total else 0
    return {
        "page": page,
        "pages": page_count,
        "page_size": page_size,
        "offset": offset,
        "range_start": offset + 1 if total else 0,
        "range_end": min(total, offset + page_size) if total else 0,
        "total": total,
    }


def _empty_result(query: str, scope: str, mode: str, limit: int, elapsed_ms: float = 0.0, sort_by: str = "", sort_dir: str = "asc", page: int = 1) -> dict[str, object]:
    counts = {"persons": 0, "rewards": 0, "marks": 0}
    pagination = _pagination(0, limit, page)
    return {
        "query": query,
        "scope": scope,
        "mode": mode,
        "sort_by": str(sort_by or "").strip(),
        "sort_dir": "desc" if str(sort_dir or "").strip().lower() == "desc" else "asc",
        "limit": limit,
        "elapsed_ms": elapsed_ms,
        "counts": counts,
        "total": 0,
        "page": pagination["page"],
        "pages": pagination["pages"],
        "page_size": pagination["page_size"],
        "offset": pagination["offset"],
        "range_start": pagination["range_start"],
        "range_end": pagination["range_end"],
        "persons": [],
        "rewards": [],
        "marks": [],
    }


def _person_rows(db_path: Path) -> list[dict[str, object]]:
    return fetch_all(
        db_path,
        """
        select
            p.id,
            p.fio,
            p.birthday,
            g.name as rank_name,
            p.person_foto,
            p.main_foto,
            p.rewards_foto,
            p.book1_foto,
            p.book2_foto,
            p.card1_foto,
            p.card2_foto,
            case when nullif(trim(coalesce(p.person_foto, '')), '') is null then 0 else 1 end as person_foto_flag,
            case when nullif(trim(coalesce(p.main_foto, '')), '') is null then 0 else 1 end as main_foto_flag,
            case when nullif(trim(coalesce(p.rewards_foto, '')), '') is null then 0 else 1 end as rewards_foto_flag,
            case when nullif(trim(coalesce(p.book1_foto, '')), '') is null then 0 else 1 end as book1_foto_flag,
            case when nullif(trim(coalesce(p.book2_foto, '')), '') is null then 0 else 1 end as book2_foto_flag,
            case when nullif(trim(coalesce(p.card1_foto, '')), '') is null then 0 else 1 end as card1_foto_flag,
            case when nullif(trim(coalesce(p.card2_foto, '')), '') is null then 0 else 1 end as card2_foto_flag
        from person p
        left join guide g on g.id = p.id_rank
        order by p.id
        """,
    )


def _reward_rows(db_path: Path) -> list[dict[str, object]]:
    return fetch_all(
        db_path,
        """
        select
            r.id,
            r.person_id,
            p.fio,
            p.birthday,
            guide.name as rank_name,
            g0.name as gos,
            g1.name as category,
            g2.name as subcategory,
            g3.name as name,
            r.id_link,
            r.number,
            r.instock,
            r.date_purchase,
            r.price_purchase,
            r.price_now,
            p.book1_foto as person_book1_foto,
            p.book2_foto as person_book2_foto,
            p.card1_foto as person_card1_foto,
            p.card2_foto as person_card2_foto,
            r.front_foto,
            r.back_foto,
            r.book1_foto as reward_book1_foto,
            r.book2_foto as reward_book2_foto,
            r.reward_list,
            case when nullif(trim(coalesce(p.book1_foto, '')), '') is null then 0 else 1 end as person_book1_foto_flag,
            case when nullif(trim(coalesce(p.book2_foto, '')), '') is null then 0 else 1 end as person_book2_foto_flag,
            case when nullif(trim(coalesce(p.card1_foto, '')), '') is null then 0 else 1 end as person_card1_foto_flag,
            case when nullif(trim(coalesce(p.card2_foto, '')), '') is null then 0 else 1 end as person_card2_foto_flag,
            case when nullif(trim(coalesce(r.front_foto, '')), '') is null then 0 else 1 end as front_foto_flag,
            case when nullif(trim(coalesce(r.back_foto, '')), '') is null then 0 else 1 end as back_foto_flag,
            case when nullif(trim(coalesce(r.book1_foto, '')), '') is null then 0 else 1 end as reward_book1_foto_flag,
            case when nullif(trim(coalesce(r.book2_foto, '')), '') is null then 0 else 1 end as reward_book2_foto_flag,
            case when nullif(trim(coalesce(r.reward_list, '')), '') is null then 0 else 1 end as reward_list_flag
        from rewards r
        left join person p on p.id = r.person_id
        left join guide on guide.id = p.id_rank
        left join guide_lev_0 g0 on g0.id = r.id_gos
        left join guide_lev_1 g1 on g1.id = r.id_catigory
        left join guide_lev_2 g2 on g2.id = r.id_sub_catigory
        left join guide_lev_3 g3 on g3.id = r.id_name
        order by r.id
        """,
    )


def _mark_rows(db_path: Path) -> list[dict[str, object]]:
    return fetch_all(
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
            m.instock
        from mark m
        left join guide_lev_0 g0 on g0.id = m.id_gos
        left join guide_lev_1 g1 on g1.id = m.id_catigory
        left join guide_lev_2 g2 on g2.id = m.id_sub_catigory
        left join guide_lev_3 g3 on g3.id = m.id_name
        order by m.id
        """,
    )


def search_suggestions(db_path: Path, limit: int = 250) -> dict[str, list[str]]:
    safe_limit = max(1, min(int(limit), 500))
    persons = [
        str(row["fio"])
        for row in fetch_all(
            db_path,
            "select fio from person where nullif(trim(coalesce(fio, '')), '') is not null order by fio limit ?",
            (safe_limit,),
        )
    ]
    rewards = [
        str(row["name"])
        for row in fetch_all(
            db_path,
            """
            select distinct g3.name
            from rewards r
            join guide_lev_3 g3 on g3.id = r.id_name
            where nullif(trim(coalesce(g3.name, '')), '') is not null
            order by g3.name
            limit ?
            """,
            (safe_limit,),
        )
    ]
    marks = [
        str(row["name"])
        for row in fetch_all(
            db_path,
            """
            select distinct g3.name
            from mark m
            join guide_lev_3 g3 on g3.id = m.id_name
            where nullif(trim(coalesce(g3.name, '')), '') is not null
            order by g3.name
            limit ?
            """,
            (safe_limit,),
        )
    ]
    return {
        "all": [],
        "persons": persons,
        "rewards": rewards,
        "reward_numbers": [],
        "marks": marks,
    }


def search_all(
    db_path: Path,
    query: str,
    limit: int = DEFAULT_LIMIT,
    page: int = 1,
    scope: str = "all",
    mode: str = "contains",
    sort_by: str = "",
    sort_dir: str = "asc",
) -> dict[str, object]:
    started = perf_counter()
    cleaned_query = query.strip()
    cleaned_scope = _clean_scope(scope)
    cleaned_mode = _clean_mode(mode)
    safe_limit = max(1, min(int(limit), MAX_LIMIT))
    requested_page = max(1, int(page or 1))
    needle = _normalize(cleaned_query)
    persons: list[dict[str, object]] = []
    rewards: list[dict[str, object]] = []
    marks: list[dict[str, object]] = []

    if not needle and cleaned_scope == "all":
        return _empty_result(cleaned_query, cleaned_scope, cleaned_mode, safe_limit, sort_by=sort_by, sort_dir=sort_dir, page=requested_page)

    if cleaned_scope in {"all", "persons"}:
        person_rows = _person_rows(db_path)
        persons = person_rows if not needle else [
            row
            for row in person_rows
            if _row_matches(row, ("fio", "birthday", "rank_name"), needle, cleaned_mode)
        ]
        persons = _sort_rows(persons, sort_by, sort_dir)

    if cleaned_scope in {"all", "rewards", "reward_numbers"}:
        reward_rows = _reward_rows(db_path)
        if cleaned_scope == "reward_numbers":
            rewards = [] if not needle else [
                row
                for row in reward_rows
                if _row_matches(row, ("number",), needle, cleaned_mode)
            ]
        else:
            rewards = reward_rows if not needle else [
                row
                for row in reward_rows
                if _row_matches(
                    row,
                    ("number", "name", "gos", "category", "subcategory", "fio", "id_link"),
                    needle,
                    cleaned_mode,
                )
            ]
        rewards = _sort_rows(rewards, sort_by, sort_dir)

    if cleaned_scope in {"all", "marks"}:
        mark_rows = _mark_rows(db_path)
        marks = mark_rows if not needle else [
            row
            for row in mark_rows
            if _row_matches(row, ("number", "name", "gos", "category", "subcategory", "id_link"), needle, cleaned_mode)
        ]
        marks = _sort_rows(marks, sort_by, sort_dir)

    counts = {"persons": len(persons), "rewards": len(rewards), "marks": len(marks)}
    total = sum(counts.values())
    pagination = _pagination(total, safe_limit, requested_page)
    persons_page, rewards_page, marks_page = _slice_groups([persons, rewards, marks], pagination["offset"], safe_limit)
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    return {
        "query": cleaned_query,
        "scope": cleaned_scope,
        "mode": cleaned_mode,
        "sort_by": str(sort_by or "").strip(),
        "sort_dir": "desc" if str(sort_dir or "").strip().lower() == "desc" else "asc",
        "limit": safe_limit,
        "elapsed_ms": elapsed_ms,
        "counts": counts,
        "total": total,
        "page": pagination["page"],
        "pages": pagination["pages"],
        "page_size": pagination["page_size"],
        "offset": pagination["offset"],
        "range_start": pagination["range_start"],
        "range_end": pagination["range_end"],
        "persons": persons_page,
        "rewards": rewards_page,
        "marks": marks_page,
    }
