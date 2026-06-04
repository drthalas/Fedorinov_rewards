from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import csv
import io

from ..db import open_readonly_connection, row_to_dict
from .guides import list_guide_level


@dataclass(frozen=True)
class SummaryFilters:
    country_id: int | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    name_id: int | None = None
    extra: str = ""
    include_marks: bool = False


SUMMARY_CSV_HEADERS = [
    "Страна",
    "Категория",
    "Подкатегория",
    "Наименование",
    "Всего",
    "В наличии",
    "Нет в наличии",
    "Цена покупки",
    "Текущая цена",
    "Последняя дата приобретения",
]


def summary_guide_options(db_path: Path) -> dict[str, list[dict[str, object]]]:
    return {
        "countries": list_guide_level(db_path, 0),
        "categories": list_guide_level(db_path, 1),
        "subcategories": list_guide_level(db_path, 2),
        "names": list_guide_level(db_path, 3),
        "extras": list_guide_level(db_path, 4),
    }


def _int_filter(value: int | None) -> int | None:
    if value is None or value <= 0:
        return None
    return value


def normalized_summary_filters(
    country_id: int | None = None,
    category_id: int | None = None,
    subcategory_id: int | None = None,
    name_id: int | None = None,
    extra: str = "",
    include_marks: bool = False,
) -> SummaryFilters:
    return SummaryFilters(
        country_id=_int_filter(country_id),
        category_id=_int_filter(category_id),
        subcategory_id=_int_filter(subcategory_id),
        name_id=_int_filter(name_id),
        extra=str(extra or "").strip(),
        include_marks=include_marks,
    )


def _extra_name(connection, extra: str) -> str | None:
    if not extra:
        return None
    try:
        extra_id = int(extra)
    except ValueError:
        return None
    row = connection.execute("select name from guide_lev_4 where id = ?", (extra_id,)).fetchone()
    if row is None:
        return None
    name = str(row["name"] or "").strip()
    return name or None


def _where_clause(alias: str, filters: SummaryFilters, extra_name: str | None) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    field_filters = [
        ("id_gos", filters.country_id),
        ("id_catigory", filters.category_id),
        ("id_sub_catigory", filters.subcategory_id),
        ("id_name", filters.name_id),
    ]
    for field, value in field_filters:
        if value is not None:
            clauses.append(f"{alias}.{field} = ?")
            params.append(value)
    if extra_name:
        clauses.append(f"coalesce({alias}.id_link, '') like ?")
        params.append(f"%{extra_name}%")
    if not clauses:
        return "", params
    return "where " + " and ".join(clauses), params


def _source_query(table: str, alias: str, label: str, where_sql: str) -> tuple[str, list[object]]:
    return f"""
        select
            ? as source_type,
            {alias}.id_gos as country_id,
            g0.name as country,
            {alias}.id_catigory as category_id,
            g1.name as category,
            {alias}.id_sub_catigory as subcategory_id,
            g2.name as subcategory,
            {alias}.id_name as name_id,
            g3.name as name,
            {alias}.instock,
            {alias}.price_purchase,
            {alias}.price_now,
            {alias}.date_purchase
        from {table} {alias}
        left join guide_lev_0 g0 on g0.id = {alias}.id_gos
        left join guide_lev_1 g1 on g1.id = {alias}.id_catigory
        left join guide_lev_2 g2 on g2.id = {alias}.id_sub_catigory
        left join guide_lev_3 g3 on g3.id = {alias}.id_name
        {where_sql}
    """, [label]


def summary_rows(db_path: Path, filters: SummaryFilters) -> list[dict[str, object]]:
    with closing(open_readonly_connection(db_path)) as connection:
        extra_name = _extra_name(connection, filters.extra)
        reward_where, reward_params = _where_clause("r", filters, extra_name)
        reward_query, reward_label = _source_query("rewards", "r", "Награды", reward_where)
        source_queries = [reward_query]
        params: list[object] = [*reward_label, *reward_params]

        if filters.include_marks:
            mark_where, mark_params = _where_clause("m", filters, extra_name)
            mark_query, mark_label = _source_query("mark", "m", "Знаки", mark_where)
            source_queries.append(mark_query)
            params.extend([*mark_label, *mark_params])

        union_sql = "\nunion all\n".join(source_queries)
        query = f"""
            select
                country_id,
                coalesce(country, '—') as country,
                category_id,
                coalesce(category, '—') as category,
                subcategory_id,
                coalesce(subcategory, '—') as subcategory,
                name_id,
                coalesce(name, '—') as name,
                count(*) as total,
                sum(case when lower(cast(instock as text)) in ('true', '1') then 1 else 0 end) as in_stock,
                count(*) - sum(case when lower(cast(instock as text)) in ('true', '1') then 1 else 0 end) as not_in_stock,
                coalesce(sum(cast(price_purchase as integer)), 0) as price_purchase_sum,
                coalesce(sum(cast(price_now as integer)), 0) as price_now_sum,
                max(date_purchase) as last_purchase_date
            from ({union_sql}) summary_source
            group by country_id, country, category_id, category, subcategory_id, subcategory, name_id, name
            order by country, category, subcategory, name
        """
        rows = connection.execute(query, tuple(params)).fetchall()
    return [row_to_dict(row) for row in rows if row is not None]


def summary_totals(rows: list[dict[str, object]]) -> dict[str, int]:
    totals = {
        "total": 0,
        "in_stock": 0,
        "not_in_stock": 0,
        "price_purchase_sum": 0,
        "price_now_sum": 0,
    }
    for row in rows:
        for key in totals:
            totals[key] += int(row.get(key) or 0)
    return totals


def summary_csv_text(rows: list[dict[str, object]]) -> str:
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(SUMMARY_CSV_HEADERS)
    for row in rows:
        writer.writerow(
            [
                row.get("country") or "—",
                row.get("category") or "—",
                row.get("subcategory") or "—",
                row.get("name") or "—",
                row.get("total") or 0,
                row.get("in_stock") or 0,
                row.get("not_in_stock") or 0,
                row.get("price_purchase_sum") or 0,
                row.get("price_now_sum") or 0,
                row.get("last_purchase_date") or "",
            ]
        )
    return output.getvalue()
