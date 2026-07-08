from __future__ import annotations

from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path

from ..repositories.summary import (
    SUMMARY_CSV_HEADERS,
    SummaryFilters,
    summary_guide_options,
    summary_matrix,
    summary_rows,
    summary_totals,
)
from .display import format_birth_year, format_date, format_money


SUMMARY_MATRIX_MAX_COLUMNS = 130


class SummaryPDFError(ValueError):
    pass


class SummaryPDFTooWide(SummaryPDFError):
    pass


@dataclass(frozen=True)
class SummaryPDFResult:
    content: bytes
    filename: str


def generate_summary_pdf(db_path: Path, filters: SummaryFilters) -> SummaryPDFResult:
    rows = summary_rows(db_path, filters)
    totals = summary_totals(rows)
    story_rows = [
        [
            row.get("country") or "—",
            row.get("category") or "—",
            row.get("subcategory") or "—",
            row.get("name") or "—",
            row.get("total") or 0,
            row.get("in_stock") or 0,
            row.get("not_in_stock") or 0,
            format_money(row.get("price_purchase_sum")),
            format_money(row.get("price_now_sum")),
            format_date(row.get("last_purchase_date")),
        ]
        for row in rows
    ]
    story_rows.append(
        [
            "Итого",
            "",
            "",
            "",
            totals["total"],
            totals["in_stock"],
            totals["not_in_stock"],
            format_money(totals["price_purchase_sum"]),
            format_money(totals["price_now_sum"]),
            "—",
        ]
    )
    return _build_pdf(
        title="Свод по наградам",
        filters=filters,
        db_path=db_path,
        headers=SUMMARY_CSV_HEADERS,
        rows=story_rows,
        filename="summary.pdf",
        compact=False,
    )


def generate_summary_matrix_pdf(db_path: Path, filters: SummaryFilters) -> SummaryPDFResult:
    matrix = summary_matrix(db_path, filters)
    photo_columns = list(matrix.get("photo_columns") or [])
    reward_columns = list(matrix.get("reward_columns") or [])
    show_numbers = bool(matrix.get("show_numbers"))

    headers = ["ФИО", "Звание / специальность", "Год рождения"]
    headers.extend(str(column["label"]) for column in photo_columns)
    headers.extend(str(column["name"]) for column in reward_columns)
    if show_numbers:
        headers.append("Номера")
    headers.append("Итого наград")

    if len(headers) > SUMMARY_MATRIX_MAX_COLUMNS:
        raise SummaryPDFTooWide("Таблица слишком широкая для PDF. Используйте фильтры или CSV.")

    story_rows = []
    for row in matrix.get("rows") or []:
        photo_flags = row.get("photo_flags") or {}
        reward_counts = row.get("reward_counts") or {}
        values = [row.get("fio") or "—", row.get("rank_name") or "—", format_birth_year(row.get("birthday"))]
        values.extend(int(photo_flags.get(column["field"], 0)) for column in photo_columns)
        values.extend(int(reward_counts.get(int(column["id"]), 0)) for column in reward_columns)
        if show_numbers:
            values.append(row.get("numbers") or "")
        values.append(int(row.get("row_total") or 0))
        story_rows.append(values)

    totals = ["Итого", f"Кавалеров: {matrix.get('person_total') or 0}", ""]
    photo_totals = matrix.get("photo_totals") or {}
    reward_totals = matrix.get("reward_totals") or {}
    totals.extend(int(photo_totals.get(column["field"], 0)) for column in photo_columns)
    totals.extend(int(reward_totals.get(int(column["id"]), 0)) for column in reward_columns)
    if show_numbers:
        totals.append("")
    totals.append(int(matrix.get("reward_total") or 0))
    story_rows.append(totals)

    return _build_pdf(
        title="Шахматка по кавалерам",
        filters=filters,
        db_path=db_path,
        headers=headers,
        rows=story_rows,
        filename="summary_matrix.pdf",
        compact=True,
    )


def _build_pdf(
    *,
    title: str,
    filters: SummaryFilters,
    db_path: Path,
    headers: list[str],
    rows: list[list[object]],
    filename: str,
    compact: bool,
) -> SummaryPDFResult:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A3, A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise SummaryPDFError("PDF-библиотека reportlab не установлена.") from exc

    buffer = BytesIO()
    page_size = _page_size(len(headers), compact, landscape(A3), landscape(A4))
    margin = 8 * mm if compact else 10 * mm
    font_name = _register_pdf_font(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    body_size = 5 if compact else 7
    styles.add(ParagraphStyle(name="SummaryTitle", parent=styles["Title"], fontName=font_name, fontSize=16, leading=19))
    styles.add(ParagraphStyle(name="SummaryBody", parent=styles["BodyText"], fontName=font_name, fontSize=body_size, leading=body_size + 2))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=title,
    )

    story: list[object] = [
        Paragraph(_p(title), styles["SummaryTitle"]),
        Paragraph(_p(_filters_text(db_path, filters)), styles["SummaryBody"]),
        Spacer(1, 6),
    ]
    table_data = [[Paragraph(_p(header), styles["SummaryBody"]) for header in headers]]
    table_data.extend([[Paragraph(_p(value), styles["SummaryBody"]) for value in row] for row in rows])
    widths = _column_widths(len(headers), page_size[0] - margin * 2, compact)
    table = Table(table_data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), body_size),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8ead7")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#eef7ee")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return SummaryPDFResult(content=buffer.getvalue(), filename=filename)


def _page_size(column_count: int, compact: bool, a3_landscape: tuple[float, float], a4_landscape: tuple[float, float]) -> tuple[float, float]:
    if not compact:
        return a4_landscape
    min_width = max(a3_landscape[0], 220 + column_count * 24)
    return (min_width, a3_landscape[1])


def _column_widths(column_count: int, available_width: float, compact: bool) -> list[float]:
    if column_count <= 0:
        return []
    if not compact:
        weights = [1.2, 1.1, 1.1, 1.5, 0.55, 0.65, 0.7, 0.9, 0.9, 0.9]
        total = sum(weights)
        return [available_width * weight / total for weight in weights[:column_count]]
    first_columns = min(3, column_count)
    fixed = [80, 70, 54][:first_columns]
    remaining_count = column_count - first_columns
    remaining_width = max(remaining_count * 20, available_width - sum(fixed))
    if remaining_count <= 0:
        return fixed
    return fixed + [remaining_width / remaining_count] * remaining_count


def _filters_text(db_path: Path, filters: SummaryFilters) -> str:
    options = summary_guide_options(db_path)
    parts = [
        ("Страна", _lookup_name(options["countries"], filters.country_id)),
        ("Категория", _lookup_name(options["categories"], filters.category_id)),
        ("Подкатегория", _lookup_name(options["subcategories"], filters.subcategory_id)),
        ("Наименование", _lookup_name(options["names"], filters.name_id)),
        ("Дополнительно", _lookup_name(options["extras"], filters.extra)),
    ]
    visible = [f"{label}: {value}" for label, value in parts if value]
    visible.append(f"Знаки: {'да' if filters.include_marks else 'нет'}")
    return "Фильтры: " + ("; ".join(visible) if visible else "все записи")


def _lookup_name(rows: list[dict[str, object]], value: object) -> str:
    if value is None or value == "":
        return ""
    text = str(value)
    for row in rows:
        if str(row.get("id")) == text:
            return str(row.get("name") or "").strip()
    return text


def _register_pdf_font(pdfmetrics, TTFont) -> str:
    for path in _font_candidates():
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("SummaryFont", str(path)))
                return "SummaryFont"
            except Exception:
                continue
    return "Helvetica"


def _font_candidates() -> list[Path]:
    return [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def _p(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return escape(text) if text else "—"
