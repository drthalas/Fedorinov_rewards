from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import csv
import io

from ..db import open_readonly_connection, row_to_dict
from ..services.display import format_date
from .guides import guide_cascade_data, guide_cascade_options, guide_name_sort_key, list_guide_level


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

SUMMARY_MATRIX_PHOTO_COLUMNS = [
    ("person_foto", "Фото кавалера"),
    ("main_foto", "Главное фото"),
    ("rewards_foto", "Общее фото наград"),
    ("book1_foto", "Фото наградной книжки, сторона 1"),
    ("book2_foto", "Фото наградной книжки, сторона 2"),
    ("card1_foto", "Фото учётной карточки, страница 1"),
    ("card2_foto", "Фото учётной карточки, страница 2"),
]


def summary_guide_options(db_path: Path) -> dict[str, list[dict[str, object]]]:
    return {
        "countries": list_guide_level(db_path, 0),
        "categories": list_guide_level(db_path, 1),
        "subcategories": list_guide_level(db_path, 2),
        "names": sorted(list_guide_level(db_path, 3), key=guide_name_sort_key),
        "extras": list_guide_level(db_path, 4),
    }


def summary_filter_options(db_path: Path, filters: SummaryFilters | None = None) -> dict[str, list[dict[str, object]]]:
    filters = filters or SummaryFilters()
    cascade = guide_cascade_options(
        db_path,
        country_id=filters.country_id,
        category_id=filters.category_id,
        subcategory_id=filters.subcategory_id,
    )
    return {
        "countries": cascade["gos"],
        "categories": cascade["categories"],
        "subcategories": cascade["subcategories"],
        "names": sorted(cascade["names"], key=guide_name_sort_key),
        "extras": list_guide_level(db_path, 4),
    }


def summary_filter_cascade(db_path: Path) -> dict[str, list[dict[str, object]]]:
    cascade = guide_cascade_data(db_path)
    return {
        **cascade,
        "names": sorted(cascade["names"], key=guide_name_sort_key),
    }


def parse_optional_int(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def parse_bool_flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"true", "on", "1", "yes"}


def normalized_summary_filters(
    country_id: object = None,
    category_id: object = None,
    subcategory_id: object = None,
    name_id: object = None,
    extra: str = "",
    include_marks: object = False,
) -> SummaryFilters:
    return SummaryFilters(
        country_id=parse_optional_int(country_id),
        category_id=parse_optional_int(category_id),
        subcategory_id=parse_optional_int(subcategory_id),
        name_id=parse_optional_int(name_id),
        extra=str(extra or "").strip(),
        include_marks=parse_bool_flag(include_marks),
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


def _filters_active(filters: SummaryFilters) -> bool:
    return any(
        value is not None
        for value in (filters.country_id, filters.category_id, filters.subcategory_id, filters.name_id)
    ) or bool(filters.extra)


def _has_value(value: object) -> int:
    return 1 if str(value or "").strip() else 0


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


def summary_table(rows: list[dict[str, object]]) -> tuple[list[str], list[list[object]]]:
    values = [
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
        for row in rows
    ]
    return list(SUMMARY_CSV_HEADERS), values


def summary_csv_text(rows: list[dict[str, object]]) -> str:
    headers, values = summary_table(rows)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(headers)
    writer.writerows(values)
    return output.getvalue()


def _sort_matrix_rows(rows: list[dict[str, object]], sort_by: str, sort_dir: str) -> list[dict[str, object]]:
    direction = "desc" if sort_dir == "desc" else "asc"
    sort_key = str(sort_by or "fio")

    def text_key(value: object) -> str:
        return str(value or "").casefold()

    def row_value(row: dict[str, object]) -> object:
        if sort_key == "fio":
            return text_key(row.get("fio"))
        if sort_key == "rank_name":
            return text_key(row.get("rank_name"))
        if sort_key == "birthday":
            return str(row.get("birthday") or "")
        if sort_key == "row_total":
            return int(row.get("row_total") or 0)
        if sort_key == "numbers":
            return text_key(row.get("numbers"))
        if sort_key.startswith("photo:"):
            field = sort_key.split(":", 1)[1]
            return int((row.get("photo_flags") or {}).get(field, 0))
        if sort_key.startswith("reward:"):
            try:
                reward_id = int(sort_key.split(":", 1)[1])
            except ValueError:
                return 0
            return int((row.get("reward_counts") or {}).get(reward_id, 0))
        return text_key(row.get("fio"))

    return sorted(rows, key=lambda row: (row_value(row), text_key(row.get("fio")), int(row.get("id") or 0)), reverse=direction == "desc")


def summary_matrix(db_path: Path, filters: SummaryFilters, sort_by: str = "fio", sort_dir: str = "asc") -> dict[str, object]:
    with closing(open_readonly_connection(db_path)) as connection:
        extra_name = _extra_name(connection, filters.extra)
        reward_where, reward_params = _where_clause("r", filters, extra_name)
        active_filters = _filters_active(filters)
        column_rows = connection.execute(
            f"""
            select
                coalesce(r.id_name, 0) as id,
                coalesce(nullif(g3.name, ''), '—') as name
            from rewards r
            left join guide_lev_3 g3 on g3.id = r.id_name
            {reward_where}
            group by coalesce(r.id_name, 0), coalesce(nullif(g3.name, ''), '—')
            order by name
            """,
            tuple(reward_params),
        ).fetchall()
        reward_columns = [row_to_dict(row) for row in column_rows]
        reward_column_ids = [int(row["id"]) for row in reward_columns]

        person_where = ""
        person_params: list[object] = []
        if active_filters:
            exists_where, exists_params = _where_clause("rx", filters, extra_name)
            person_where = f"where p.id in (select distinct rx.person_id from rewards rx {exists_where})"
            person_params.extend(exists_params)

        person_rows_sql = connection.execute(
            f"""
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
                p.card2_foto
            from person p
            left join guide g on g.id = p.id_rank
            {person_where}
            order by p.fio
            """,
            tuple(person_params),
        ).fetchall()

        count_rows = connection.execute(
            f"""
            select
                r.person_id,
                coalesce(r.id_name, 0) as name_id,
                count(*) as count,
                group_concat(nullif(trim(cast(r.number as text)), ''), ', ') as numbers
            from rewards r
            {reward_where}
            group by r.person_id, coalesce(r.id_name, 0)
            """,
            tuple(reward_params),
        ).fetchall()

    counts: dict[tuple[int, int], int] = {}
    numbers: dict[tuple[int, int], str] = {}
    for row in count_rows:
        key = (int(row["person_id"]), int(row["name_id"]))
        counts[key] = int(row["count"] or 0)
        numbers[key] = str(row["numbers"] or "").strip()

    photo_totals = {field: 0 for field, _label in SUMMARY_MATRIX_PHOTO_COLUMNS}
    reward_totals = {column_id: 0 for column_id in reward_column_ids}
    person_rows: list[dict[str, object]] = []
    selected_name_id = filters.name_id
    for person_row in person_rows_sql:
        person = row_to_dict(person_row)
        person_id = int(person["id"])
        photo_flags = {field: int(_has_value(person.get(field))) for field, _label in SUMMARY_MATRIX_PHOTO_COLUMNS}
        for field, value in photo_flags.items():
            photo_totals[field] += int(value)
        reward_counts = {column_id: counts.get((person_id, column_id), 0) for column_id in reward_column_ids}
        for column_id, value in reward_counts.items():
            reward_totals[column_id] += int(value)
        person_rows.append(
            {
                "id": person_id,
                "fio": person.get("fio") or "—",
                "rank_name": person.get("rank_name") or "—",
                "birthday": person.get("birthday") or "",
                "photo_flags": photo_flags,
                "reward_counts": reward_counts,
                "numbers": numbers.get((person_id, selected_name_id), "") if selected_name_id is not None else "",
                "row_total": sum(int(value) for value in reward_counts.values()),
            }
        )

    sorted_person_rows = _sort_matrix_rows(person_rows, sort_by, sort_dir)

    return {
        "photo_columns": [{"field": field, "label": label} for field, label in SUMMARY_MATRIX_PHOTO_COLUMNS],
        "reward_columns": reward_columns,
        "rows": sorted_person_rows,
        "photo_totals": photo_totals,
        "reward_totals": reward_totals,
        "person_total": len(person_rows),
        "reward_total": sum(int(value) for value in reward_totals.values()),
        "show_numbers": selected_name_id is not None,
        "wide_warning": len(reward_columns) > 12,
        "include_marks_note": filters.include_marks,
    }


def summary_matrix_table(matrix: dict[str, object]) -> tuple[list[str], list[list[object]]]:
    photo_columns = list(matrix.get("photo_columns") or [])
    reward_columns = list(matrix.get("reward_columns") or [])
    show_numbers = bool(matrix.get("show_numbers"))
    headers = ["ФИО", "Звание / специальность", "Дата рождения"]
    headers.extend(str(column["label"]) for column in photo_columns)
    headers.extend(str(column["name"]) for column in reward_columns)
    if show_numbers:
        headers.append("Номера")
    headers.append("Итого наград")
    values = []
    for row in matrix.get("rows") or []:
        row_values = [row.get("fio") or "—", row.get("rank_name") or "—", format_date(row.get("birthday"))]
        photo_flags = row.get("photo_flags") or {}
        reward_counts = row.get("reward_counts") or {}
        row_values.extend(int(photo_flags.get(column["field"], 0)) for column in photo_columns)
        row_values.extend(int(reward_counts.get(int(column["id"]), 0)) for column in reward_columns)
        if show_numbers:
            row_values.append(row.get("numbers") or "")
        row_values.append(int(row.get("row_total") or 0))
        values.append(row_values)
    totals = ["Итого", f"Кавалеров: {matrix.get('person_total') or 0}", ""]
    photo_totals = matrix.get("photo_totals") or {}
    reward_totals = matrix.get("reward_totals") or {}
    totals.extend(int(photo_totals.get(column["field"], 0)) for column in photo_columns)
    totals.extend(int(reward_totals.get(int(column["id"]), 0)) for column in reward_columns)
    if show_numbers:
        totals.append("")
    totals.append(int(matrix.get("reward_total") or 0))
    values.append(totals)
    return headers, values


def summary_matrix_csv_text(matrix: dict[str, object]) -> str:
    headers, values = summary_matrix_table(matrix)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(headers)
    writer.writerows(values)
    return output.getvalue()
