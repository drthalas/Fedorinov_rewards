from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
import re

from ..config import Settings
from ..repositories.persons import get_person, list_person_rewards
from .display import format_birth_year, format_bool, format_date, format_money, has_media_path, safe_external_url
from .media import resolve_media
from .person_files import _safe_filename
from .photos import PERSON_PHOTO_FIELDS, REWARD_PHOTO_FIELDS


class BookletError(ValueError):
    pass


@dataclass(frozen=True)
class BookletPDFResult:
    path: Path
    filename: str


def person_booklet_context(settings: Settings, person_id: int, return_to: str = "") -> dict[str, object]:
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise BookletError("Награжденный не найден.")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    return {
        "person": person,
        "rewards": rewards,
        "person_photos": _photo_entries(settings, person, PERSON_PHOTO_FIELDS),
        "reward_photo_groups": [
            {
                "reward": reward,
                "photos": _photo_entries(settings, reward, REWARD_PHOTO_FIELDS),
            }
            for reward in rewards
        ],
        "links": _person_links(person),
        "return_to": return_to,
    }


def generate_person_booklet_pdf(settings: Settings, person_id: int, output_path: Path | None = None) -> BookletPDFResult:
    context = person_booklet_context(settings, person_id)
    person = context["person"]
    rewards = context["rewards"]
    person_photos = context["person_photos"]
    reward_photo_groups = context["reward_photo_groups"]

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise BookletError("PDF-библиотека reportlab не установлена. Используйте печать страницы буклета в PDF.") from exc

    if output_path is None:
        output_dir = _booklet_output_dir(settings)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = person_booklet_filename(settings, person_id)
        output_path = output_dir / filename
    else:
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        filename = output_path.name

    font_name = _register_pdf_font(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    styles.add(ParagraphStyle(name="BookletTitle", parent=styles["Title"], fontName=font_name, fontSize=20, leading=24))
    styles.add(ParagraphStyle(name="BookletHeading", parent=styles["Heading2"], fontName=font_name, fontSize=13, leading=16))
    styles.add(ParagraphStyle(name="BookletBody", parent=styles["BodyText"], fontName=font_name, fontSize=9, leading=12))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Буклет кавалера - {person.get('fio') or person_id}",
    )
    story: list[object] = []

    story.append(Paragraph("Буклет кавалера", styles["BookletTitle"]))
    story.append(Paragraph(_p(person.get("fio")), styles["Heading1"]))
    story.append(_key_value_table(
        [
            ("ФИО", person.get("fio")),
            ("Звание / специальность", person.get("rank_name")),
            ("Год рождения", format_birth_year(person.get("birthday"))),
        ],
        Paragraph,
        Table,
        TableStyle,
        colors,
        styles,
    ))
    _add_text_block(story, styles, Paragraph, "Краткая биография", person.get("biography"))
    _add_text_block(story, styles, Paragraph, "Комментарий / заметки", person.get("comment"))
    _add_links(story, styles, Paragraph, context["links"])
    _add_photos(story, styles, Paragraph, Image, person_photos)

    if rewards:
        story.append(PageBreak())
        story.append(Paragraph("Награды", styles["Heading1"]))
    for index, reward in enumerate(rewards, start=1):
        story.append(Paragraph(f"{index}. {_p(reward.get('name') or 'Награда')}", styles["BookletHeading"]))
        story.append(_key_value_table(
            [
                ("Государство", reward.get("gos")),
                ("Категория", reward.get("category")),
                ("Подкатегория", reward.get("subcategory")),
                ("Наименование", reward.get("name")),
                ("Номер", reward.get("number")),
                ("Наличие", format_bool(reward.get("instock"), "В наличии", "Нет")),
                ("Дата покупки", format_date(reward.get("date_purchase"))),
                ("Цена покупки", format_money(reward.get("price_purchase"))),
                ("Текущая цена", format_money(reward.get("price_now"))),
            ],
            Paragraph,
            Table,
            TableStyle,
            colors,
            styles,
        ))
        photo_group = reward_photo_groups[index - 1]
        _add_photos(story, styles, Paragraph, Image, photo_group["photos"])
        story.append(Spacer(1, 8))

    if not rewards:
        story.append(Paragraph("Награды не найдены.", styles["BookletBody"]))

    doc.build(story)
    return BookletPDFResult(path=output_path, filename=filename)


def person_booklet_filename(settings: Settings, person_id: int) -> str:
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise BookletError("Награжденный не найден.")
    return f"{_safe_filename(str(person.get('fio') or 'person'))}_{person_id}_booklet_{_timestamp()}.pdf"


def _booklet_output_dir(settings: Settings) -> Path:
    data_root = settings.rewards_data_dir.resolve()
    output_dir = (settings.rewards_data_dir / "generated" / "booklets").resolve()
    try:
        output_dir.relative_to(data_root)
    except ValueError as exc:
        raise BookletError("Папка буклетов находится вне папки данных") from exc
    return output_dir


def _photo_entries(settings: Settings, row: dict[str, object], fields) -> list[dict[str, object]]:
    entries = []
    for field in fields:
        raw_path = row.get(field.field)
        entry = {
            "field": field.field,
            "label": field.label,
            "path": raw_path,
            "available": False,
            "missing": False,
            "reason": "",
            "resolved_path": "",
        }
        if has_media_path(raw_path):
            resolution = resolve_media(settings, raw_path)
            if resolution.fallback:
                entry["missing"] = True
                entry["reason"] = resolution.fallback_reason or "Файл изображения не найден"
            else:
                entry["available"] = True
                entry["resolved_path"] = resolution.serving_path
        entries.append(entry)
    return entries


def _person_links(person: dict[str, object]) -> list[dict[str, str]]:
    links = [
        {"label": 'Ссылка на сайт "Память народа"', "value": str(person.get("link1") or "")},
        {"label": 'Ссылка на сайт "Форум коллекционеров"', "value": str(person.get("link2") or "")},
    ]
    for link in links:
        link["url"] = safe_external_url(link["value"])
    return links


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _register_pdf_font(pdfmetrics, TTFont) -> str:
    for path in _font_candidates():
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont("BookletFont", str(path)))
                return "BookletFont"
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


def _add_text_block(story: list[object], styles, Paragraph, title: str, value: object) -> None:
    if isinstance(value, str) and value.strip():
        story.append(Paragraph(title, styles["BookletHeading"]))
        for paragraph in re.split(r"\n{2,}", value.strip()):
            story.append(Paragraph(_p(paragraph).replace("\n", "<br/>"), styles["BookletBody"]))


def _add_links(story: list[object], styles, Paragraph, links: object) -> None:
    visible = [link for link in links if link.get("value")]
    if not visible:
        return
    story.append(Paragraph("Ссылки", styles["BookletHeading"]))
    for link in visible:
        value = link.get("url") or link.get("value")
        story.append(Paragraph(f"{_p(link.get('label'))}: {_p(value)}", styles["BookletBody"]))


def _add_photos(story: list[object], styles, Paragraph, Image, entries: object) -> None:
    visible = [entry for entry in entries if entry.get("available") or entry.get("missing")]
    if not visible:
        return
    story.append(Paragraph("Фото и документы", styles["BookletHeading"]))
    for entry in visible:
        story.append(Paragraph(_p(entry.get("label")), styles["BookletBody"]))
        if entry.get("available"):
            try:
                image = Image(str(entry["resolved_path"]))
                image._restrictSize(120 * 2.83465, 80 * 2.83465)
                story.append(image)
            except Exception:
                story.append(Paragraph("Файл изображения не найден", styles["BookletBody"]))
        else:
            story.append(Paragraph("Файл изображения не найден", styles["BookletBody"]))


def _key_value_table(rows, Paragraph, Table, TableStyle, colors, styles):
    table = Table(
        [[Paragraph(_p(label), styles["BookletBody"]), Paragraph(_p(value), styles["BookletBody"])] for label, value in rows],
        colWidths=[150, 360],
    )
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _p(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return escape(text) if text else "—"
