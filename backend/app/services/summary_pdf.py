from __future__ import annotations

from dataclasses import dataclass
from html import escape
from io import BytesIO
from pathlib import Path
import re
from typing import Iterable
import unicodedata

from ..config import Settings
from ..repositories.summary import (
    SUMMARY_CSV_HEADERS,
    SUMMARY_MATRIX_PHOTO_COLUMNS,
    SUMMARY_MATRIX_REWARD_PHOTO_COLUMNS,
    SummaryFilters,
    summary_guide_options,
    summary_matrix,
    summary_rows,
    summary_totals,
)
from .display import format_birth_year, format_date, format_money
from .media import resolve_media


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


def normalize_summary_pdf_media_fields(values: Iterable[str] | str | None) -> tuple[str, ...]:
    allowed = {
        field
        for field, _label in (*SUMMARY_MATRIX_PHOTO_COLUMNS, *SUMMARY_MATRIX_REWARD_PHOTO_COLUMNS)
        if field != "person_foto"
    }
    raw_values = values.split(",") if isinstance(values, str) else values or ()
    selected: list[str] = []
    for raw_value in raw_values:
        field = str(raw_value or "").strip()
        if field in allowed and field not in selected:
            selected.append(field)
    return tuple(selected)


def normalize_summary_pdf_sort(value: object) -> str:
    return "reward_number" if str(value or "").strip() == "reward_number" else "fio"


def _fio_sort_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return normalized.replace("ё", "е")


def _reward_number_sort_key(value: object) -> tuple[tuple[int, object], ...]:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part)
        for part in re.split(r"(\d+)", normalized)
        if part
    )


def sort_summary_pdf_rows(rows: Iterable[dict[str, object]], sort_by: object) -> list[dict[str, object]]:
    selected_sort = normalize_summary_pdf_sort(sort_by)
    rows_list = list(rows)
    if selected_sort == "fio":
        return sorted(rows_list, key=lambda row: (_fio_sort_key(row.get("fio")), int(row.get("id") or 0)))

    def number_key(row: dict[str, object]) -> tuple[object, ...]:
        numbers = [str(value).strip() for value in row.get("pdf_reward_numbers") or [] if str(value).strip()]
        if not numbers:
            return (1, (), _fio_sort_key(row.get("fio")), int(row.get("id") or 0))
        first = min(numbers, key=_reward_number_sort_key)
        return (0, _reward_number_sort_key(first), _fio_sort_key(row.get("fio")), int(row.get("id") or 0))

    return sorted(rows_list, key=number_key)


def generate_summary_matrix_pdf(
    settings: Settings,
    filters: SummaryFilters,
    media_fields: Iterable[str] | str | None = None,
    include_reward_number: object = False,
    sort_by: object = "fio",
) -> SummaryPDFResult:
    matrix = summary_matrix(settings.rewards_db_path, filters)
    selected_fields = normalize_summary_pdf_media_fields(media_fields)
    photo_labels = dict((*SUMMARY_MATRIX_PHOTO_COLUMNS, *SUMMARY_MATRIX_REWARD_PHOTO_COLUMNS))
    columns = [(field, photo_labels[field]) for field in selected_fields]
    show_reward_number = str(include_reward_number or "").strip().lower() in {"1", "true", "on", "yes"}

    if len(columns) + 1 + int(show_reward_number) > SUMMARY_MATRIX_MAX_COLUMNS:
        raise SummaryPDFTooWide("Таблица слишком широкая для PDF. Используйте фильтры или XLSX.")
    return _build_summary_cards_pdf(
        settings,
        filters,
        matrix,
        columns,
        include_reward_number=show_reward_number,
        sort_by=normalize_summary_pdf_sort(sort_by),
    )


def _build_summary_cards_pdf(
    settings: Settings,
    filters: SummaryFilters,
    matrix: dict[str, object],
    columns: list[tuple[str, str]],
    *,
    include_reward_number: bool,
    sort_by: str,
) -> SummaryPDFResult:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A3, A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise SummaryPDFError("PDF-библиотека reportlab не установлена.") from exc

    buffer = BytesIO()
    visible_column_count = len(columns) + 1 + int(include_reward_number)
    page_size = landscape(A4 if visible_column_count <= 3 else A3)
    margin = 10 * mm
    font_name = _register_pdf_font(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    styles.add(ParagraphStyle(name="CardHeader", parent=styles["BodyText"], fontName=font_name, fontSize=10, leading=12))
    styles.add(ParagraphStyle(name="CardBody", parent=styles["BodyText"], fontName=font_name, fontSize=10, leading=12))
    styles.add(ParagraphStyle(name="CardFilters", parent=styles["BodyText"], fontName=font_name, fontSize=11, leading=14))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title="Сводная таблица",
    )
    story: list[object] = []
    guide_image = _summary_pdf_header_image(
        settings,
        matrix.get("selected_reward_image_path"),
        Image,
        38 * mm,
        38 * mm,
    )
    if guide_image is not None:
        story.extend([guide_image, Spacer(1, 6)])
    story.extend(
        [
            Paragraph(_p(_filters_text(settings.rewards_db_path, filters)), styles["CardFilters"]),
            Spacer(1, 8),
        ]
    )
    header = [Paragraph("Кавалер", styles["CardHeader"])]
    if include_reward_number:
        header.append(Paragraph("Номер награды", styles["CardHeader"]))
    header.extend(Paragraph(_p(label), styles["CardHeader"]) for _field, label in columns)
    table_data: list[list[object]] = [header]
    for row in sort_summary_pdf_rows(matrix.get("rows") or [], sort_by):
        paths = row.get("photo_paths") or {}
        identity = ", ".join(
            value
            for value in (
                str(row.get("fio") or "—"),
                str(row.get("rank_name") or "—"),
                format_birth_year(row.get("birthday")),
            )
            if value and value != "—"
        )
        cells: list[object] = [
            _summary_pdf_image_cell(
                settings,
                paths.get("person_foto"),
                identity,
                styles["CardBody"],
                Paragraph,
                Image,
                Spacer,
                48 * mm,
                36 * mm,
            )
        ]
        if include_reward_number:
            cells.append(
                Paragraph(
                    _p(", ".join(str(value) for value in row.get("pdf_reward_numbers") or []) or "—"),
                    styles["CardBody"],
                )
            )
        reward_paths = row.get("reward_photo_paths") or {}
        for field, _label in columns:
            raw_paths = reward_paths.get(field) if field in dict(SUMMARY_MATRIX_REWARD_PHOTO_COLUMNS) else paths.get(field)
            cells.append(
                _summary_pdf_images_cell(
                    settings,
                    raw_paths,
                    styles["CardBody"],
                    Paragraph,
                    Image,
                    Spacer,
                    40 * mm,
                    36 * mm,
                )
            )
        table_data.append(cells)

    available_width = page_size[0] - margin * 2
    card_width = min(58 * mm, available_width)
    remaining_count = len(columns) + int(include_reward_number)
    media_width = (available_width - card_width) / remaining_count if remaining_count else 0
    widths = [card_width]
    if include_reward_number:
        widths.append(min(38 * mm, media_width))
        remaining_width = available_width - card_width - widths[-1]
        photo_width = remaining_width / len(columns) if columns else 0
        widths.extend([photo_width] * len(columns))
    else:
        widths.extend([media_width] * len(columns))
    table = Table(table_data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8ead7")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return SummaryPDFResult(content=buffer.getvalue(), filename="summary_matrix.pdf")


def _summary_pdf_image_cell(settings, raw_path, heading, style, Paragraph, Image, Spacer, max_width, max_height):
    content: list[object] = []
    if heading:
        content.extend([Paragraph(_p(heading), style), Spacer(1, 4)])
    resolution = resolve_media(settings, raw_path)
    if resolution.fallback:
        content.append(Paragraph("Нет фото", style))
        return content
    try:
        image = Image(resolution.serving_path)
        image._restrictSize(max_width, max_height)
        content.append(image)
    except Exception:
        content.append(Paragraph("Нет фото", style))
    return content


def _summary_pdf_images_cell(settings, raw_paths, style, Paragraph, Image, Spacer, max_width, max_height):
    values = raw_paths if isinstance(raw_paths, (list, tuple)) else [raw_paths]
    content: list[object] = []
    for raw_path in values:
        resolution = resolve_media(settings, raw_path)
        if resolution.fallback:
            continue
        try:
            image = Image(resolution.serving_path)
            image._restrictSize(max_width, max_height)
            if content:
                content.append(Spacer(1, 4))
            content.append(image)
        except Exception:
            continue
    return content or [Paragraph("Нет фото", style)]


def _summary_pdf_header_image(settings, raw_path, Image, max_width, max_height):
    resolution = resolve_media(settings, raw_path)
    if resolution.fallback:
        return None
    try:
        image = Image(resolution.serving_path)
        image._restrictSize(max_width, max_height)
        image.hAlign = "LEFT"
        return image
    except Exception:
        return None


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
