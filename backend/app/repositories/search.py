from __future__ import annotations

from pathlib import Path
from time import perf_counter

from .common import fetch_all


VALID_SCOPES = {"all", "persons", "rewards", "marks"}
VALID_MODES = {"contains", "starts", "exact"}
DEFAULT_LIMIT = 25


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


def _limited(rows: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    return rows[: max(0, limit)]


def _empty_result(query: str, scope: str, mode: str, limit: int, elapsed_ms: float = 0.0) -> dict[str, object]:
    counts = {"persons": 0, "rewards": 0, "marks": 0}
    return {
        "query": query,
        "scope": scope,
        "mode": mode,
        "limit": limit,
        "elapsed_ms": elapsed_ms,
        "counts": counts,
        "total": 0,
        "persons": [],
        "rewards": [],
        "marks": [],
    }


def _person_rows(db_path: Path) -> list[dict[str, object]]:
    return fetch_all(
        db_path,
        """
        select p.id, p.fio, p.birthday, g.name as rank_name
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
            g0.name as gos,
            g1.name as category,
            g2.name as subcategory,
            g3.name as name,
            r.id_link,
            r.number,
            r.instock
        from rewards r
        left join person p on p.id = r.person_id
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


def search_all(
    db_path: Path,
    query: str,
    limit: int = DEFAULT_LIMIT,
    scope: str = "all",
    mode: str = "contains",
) -> dict[str, object]:
    started = perf_counter()
    cleaned_query = query.strip()
    cleaned_scope = _clean_scope(scope)
    cleaned_mode = _clean_mode(mode)
    safe_limit = max(1, min(int(limit), 100))
    needle = _normalize(cleaned_query)
    if not needle:
        return _empty_result(cleaned_query, cleaned_scope, cleaned_mode, safe_limit)

    persons: list[dict[str, object]] = []
    rewards: list[dict[str, object]] = []
    marks: list[dict[str, object]] = []

    if cleaned_scope in {"all", "persons"}:
        persons = [
            row
            for row in _person_rows(db_path)
            if _row_matches(row, ("fio", "birthday", "rank_name"), needle, cleaned_mode)
        ]

    if cleaned_scope in {"all", "rewards"}:
        rewards = [
            row
            for row in _reward_rows(db_path)
            if _row_matches(
                row,
                ("number", "name", "gos", "category", "subcategory", "fio", "id_link"),
                needle,
                cleaned_mode,
            )
        ]

    if cleaned_scope in {"all", "marks"}:
        marks = [
            row
            for row in _mark_rows(db_path)
            if _row_matches(row, ("number", "name", "gos", "category", "subcategory", "id_link"), needle, cleaned_mode)
        ]

    counts = {"persons": len(persons), "rewards": len(rewards), "marks": len(marks)}
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    return {
        "query": cleaned_query,
        "scope": cleaned_scope,
        "mode": cleaned_mode,
        "limit": safe_limit,
        "elapsed_ms": elapsed_ms,
        "counts": counts,
        "total": sum(counts.values()),
        "persons": _limited(persons, safe_limit),
        "rewards": _limited(rewards, safe_limit),
        "marks": _limited(marks, safe_limit),
    }
