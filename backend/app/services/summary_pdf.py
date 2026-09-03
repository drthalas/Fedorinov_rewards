from __future__ import annotations

from dataclasses import dataclass
from html import escape
from io import BytesIO
from math import ceil
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
SUMMARY_PDF_IMAGE_DPI = 200
SUMMARY_PDF_JPEG_QUALITY = 92
SUMMARY_PDF_CELL_PADDING = 8
SUMMARY_PDF_IMAGE_SPACING = 4


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
    font_name, bold_font_name = _register_pdf_font_pair(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    styles.add(ParagraphStyle(name="CardHeader", parent=styles["BodyText"], fontName=bold_font_name, fontSize=11, leading=13))
    styles.add(ParagraphStyle(name="CardIdentity", parent=styles["BodyText"], fontName=bold_font_name, fontSize=11.5, leading=14))
    styles.add(ParagraphStyle(name="CardBody", parent=styles["BodyText"], fontName=font_name, fontSize=10.5, leading=12.5))
    styles.add(ParagraphStyle(name="CardFilters", parent=styles["BodyText"], fontName=bold_font_name, fontSize=12, leading=15))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title="Сводная таблица",
    )
    available_width = page_size[0] - margin * 2
    widths = _summary_pdf_column_widths(
        available_width,
        len(columns),
        include_reward_number,
        mm,
    )
    card_width = widths[0]
    photo_widths = widths[2:] if include_reward_number else widths[1:]
    image_cache: dict[tuple[str, int, int], bytes] = {}
    story: list[object] = []
    guide_image = _summary_pdf_header_image(
        settings,
        matrix.get("selected_reward_image_path"),
        Image,
        38 * mm,
        38 * mm,
        image_cache,
    )
    if guide_image is not None:
        story.extend([guide_image, Spacer(1, 6)])
    story.extend(
        [
            Paragraph(
                _p(_summary_pdf_header_text(settings.rewards_db_path, filters, matrix)),
                styles["CardFilters"],
            ),
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
                styles["CardIdentity"],
                Paragraph,
                Image,
                Spacer,
                min(48 * mm, card_width - SUMMARY_PDF_CELL_PADDING),
                36 * mm,
                image_cache,
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
        for column_index, (field, _label) in enumerate(columns):
            raw_paths = reward_paths.get(field) if field in dict(SUMMARY_MATRIX_REWARD_PHOTO_COLUMNS) else paths.get(field)
            cells.append(
                _summary_pdf_images_cell(
                    settings,
                    raw_paths,
                    styles["CardBody"],
                    Paragraph,
                    Image,
                    Spacer,
                    min(40 * mm, photo_widths[column_index] - SUMMARY_PDF_CELL_PADDING),
                    50 * mm,
                    image_cache,
                )
            )
        table_data.append(cells)

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


def _summary_pdf_column_widths(available_width, media_count, include_reward_number, mm):
    card_width = min(58 * mm, available_width)
    remaining_count = media_count + int(include_reward_number)
    media_width = (available_width - card_width) / remaining_count if remaining_count else 0
    widths = [card_width]
    if include_reward_number:
        number_width = min(38 * mm, media_width)
        widths.append(number_width)
        remaining_width = available_width - card_width - number_width
        photo_width = remaining_width / media_count if media_count else 0
        widths.extend([photo_width] * media_count)
    else:
        widths.extend([media_width] * media_count)
    return widths


def _summary_pdf_image_cell(
    settings,
    raw_path,
    heading,
    style,
    Paragraph,
    Image,
    Spacer,
    max_width,
    max_height,
    image_cache,
):
    content: list[object] = []
    if heading:
        content.extend([Paragraph(_p(heading), style), Spacer(1, 4)])
    resolution = resolve_media(settings, raw_path)
    if resolution.fallback:
        content.append(Paragraph("Нет фото", style))
        return content
    try:
        image = _summary_pdf_image(
            resolution.serving_path,
            Image,
            max_width,
            max_height,
            image_cache,
        )
        content.append(image)
    except Exception:
        content.append(Paragraph("Нет фото", style))
    return content


def _summary_pdf_images_cell(
    settings,
    raw_paths,
    style,
    Paragraph,
    Image,
    Spacer,
    max_width,
    max_total_height,
    image_cache,
):
    values = raw_paths if isinstance(raw_paths, (list, tuple)) else [raw_paths]
    paths = []
    for raw_path in values:
        resolution = resolve_media(settings, raw_path)
        if not resolution.fallback:
            paths.append(resolution.serving_path)
    if not paths:
        return [Paragraph("Нет фото", style)]

    content: list[object] = []
    per_image_height = _summary_pdf_per_image_height(max_total_height, len(paths))
    for path in paths:
        try:
            image = _summary_pdf_image(
                path,
                Image,
                max_width,
                per_image_height,
                image_cache,
            )
            if content:
                content.append(Spacer(1, SUMMARY_PDF_IMAGE_SPACING))
            content.append(image)
        except Exception:
            continue
    return content or [Paragraph("Нет фото", style)]


def _summary_pdf_per_image_height(max_total_height, image_count):
    if image_count <= 0:
        return 0
    return max(
        1,
        (max_total_height - SUMMARY_PDF_IMAGE_SPACING * (image_count - 1)) / image_count,
    )


def _summary_pdf_header_image(settings, raw_path, Image, max_width, max_height, image_cache):
    resolution = resolve_media(settings, raw_path)
    if resolution.fallback:
        return None
    try:
        image = _summary_pdf_image(
            resolution.serving_path,
            Image,
            max_width,
            max_height,
            image_cache,
        )
        image.hAlign = "LEFT"
        return image
    except Exception:
        return None


def _summary_pdf_image(path, Image, max_width, max_height, image_cache):
    safe_width = max(1, float(max_width))
    safe_height = max(1, float(max_height))
    pixel_width = max(1, ceil(safe_width * SUMMARY_PDF_IMAGE_DPI / 72))
    pixel_height = max(1, ceil(safe_height * SUMMARY_PDF_IMAGE_DPI / 72))
    cache_key = (str(path).casefold(), pixel_width, pixel_height)
    content = image_cache.get(cache_key)
    if content is None:
        content = _pdf_ready_image_bytes(Path(path), pixel_width, pixel_height)
        image_cache[cache_key] = content
    image = Image(BytesIO(content))
    image._restrictSize(safe_width, safe_height)
    return image


def _pdf_ready_image_bytes(path: Path, pixel_width: int, pixel_height: int) -> bytes:
    from PIL import Image as PILImage
    from PIL import ImageOps

    with PILImage.open(path) as source:
        image = ImageOps.exif_transpose(source)
        image.load()
        image.thumbnail((pixel_width, pixel_height), PILImage.Resampling.LANCZOS)
        buffer = BytesIO()
        has_alpha = "A" in image.getbands() or "transparency" in image.info
        if has_alpha:
            image.save(buffer, format="PNG", compress_level=3)
        else:
            image.convert("RGB").save(
                buffer,
                format="JPEG",
                quality=SUMMARY_PDF_JPEG_QUALITY,
                subsampling=0,
                optimize=False,
            )
        return buffer.getvalue()


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


def _summary_pdf_header_text(
    db_path: Path,
    filters: SummaryFilters,
    matrix: dict[str, object],
) -> str:
    selected_reward_name = str(matrix.get("selected_reward_name") or "").strip()
    if filters.name_id is not None and selected_reward_name:
        return f"{selected_reward_name} (всего: {len(matrix.get('rows') or [])})"
    return _filters_text(db_path, filters)


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


def _register_pdf_font_pair(pdfmetrics, TTFont) -> tuple[str, str]:
    for regular_path, bold_path in _font_pair_candidates():
        if not regular_path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont("SummaryFont", str(regular_path)))
            if bold_path.exists():
                pdfmetrics.registerFont(TTFont("SummaryFontBold", str(bold_path)))
                return "SummaryFont", "SummaryFontBold"
            return "SummaryFont", "SummaryFont"
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


def _font_candidates() -> list[Path]:
    return [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/tahoma.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def _font_pair_candidates() -> list[tuple[Path, Path]]:
    return [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("C:/Windows/Fonts/tahoma.ttf"), Path("C:/Windows/Fonts/tahomabd.ttf")),
        (Path("/Library/Fonts/Arial.ttf"), Path("/Library/Fonts/Arial Bold.ttf")),
        (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    ]


def _p(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return escape(text) if text else "—"
