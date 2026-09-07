from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
import re

from ..config import Settings
from ..repositories.persons import get_person, list_person_rewards
from .display import format_birth_year, format_bool, format_date, format_money, has_media_path, safe_external_url
from .media import resolve_media
from .person_files import _safe_filename
from .photos import PERSON_PHOTO_FIELDS, REWARD_PHOTO_FIELDS, PhotoField


class BookletError(ValueError):
    pass


@dataclass(frozen=True)
class BookletPDFResult:
    path: Path
    filename: str


def person_archive_profile_data(
    settings: Settings,
    person_id: int,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise BookletError("Награжденный не найден.")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    generated_at = generated_at or datetime.now()

    person_rows = _visible_rows(
        [
            ("ФИО", person.get("fio")),
            ("Год рождения", _formatted_if_present(person.get("birthday"), format_birth_year)),
            ("Звание / специальность", person.get("rank_name")),
            ("Дата формирования", generated_at.strftime("%d.%m.%Y")),
        ]
    )
    reward_entries = []
    for reward in rewards:
        reward_entries.append(
            {
                "title": _visible_text(reward.get("name")) or "Награда",
                "rows": _visible_rows(
                    [
                        ("Государство", reward.get("gos")),
                        ("Категория", reward.get("category")),
                        ("Подкатегория", reward.get("subcategory")),
                        ("Наименование", reward.get("name")),
                        ("Номер", reward.get("number")),
                        ("Наличие", _formatted_if_present(reward.get("instock"), format_bool, "В наличии", "Нет")),
                        ("Дата покупки", _formatted_if_present(reward.get("date_purchase"), format_date)),
                        ("Цена покупки", _formatted_if_present(reward.get("price_purchase"), format_money)),
                        ("Текущая цена", _formatted_if_present(reward.get("price_now"), format_money)),
                    ]
                ),
            }
        )

    links = [
        ("Память народа", _visible_text(person.get("link1"))),
        ("Форум коллекционеров", _visible_text(person.get("link2"))),
    ]
    return {
        "person": person,
        "person_rows": person_rows,
        "biography": _visible_text(person.get("biography")),
        "comment": _visible_text(person.get("comment")),
        "links": [(label, value) for label, value in links if value],
        "rewards": reward_entries,
    }


def generate_person_archive_profile_pdf(settings: Settings, person_id: int) -> bytes:
    profile = person_archive_profile_data(settings, person_id)
    person = profile["person"]

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise BookletError("PDF-библиотека reportlab не установлена.") from exc

    buffer = BytesIO()
    font_name = _register_pdf_font(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    styles.add(ParagraphStyle(name="ProfileTitle", parent=styles["Title"], fontName=font_name, fontSize=20, leading=24))
    styles.add(ParagraphStyle(name="ProfileHeading", parent=styles["Heading2"], fontName=font_name, fontSize=13, leading=16))
    styles.add(ParagraphStyle(name="ProfileBody", parent=styles["BodyText"], fontName=font_name, fontSize=9, leading=12))

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Профиль кавалера - {person.get('fio') or person_id}",
    )
    story: list[object] = [
        Paragraph("Профиль кавалера", styles["ProfileTitle"]),
        Paragraph(_p(person.get("fio")), styles["Heading1"]),
        _profile_table(profile["person_rows"], Paragraph, Table, TableStyle, colors, styles),
    ]
    _add_profile_text_block(story, styles, Paragraph, "Краткая биография", profile["biography"])
    _add_profile_text_block(story, styles, Paragraph, "Комментарий / заметки", profile["comment"])
    if profile["links"]:
        story.append(Paragraph("Ссылки", styles["ProfileHeading"]))
        for label, value in profile["links"]:
            story.append(Paragraph(f"{_p(label)}: {_p(value)}", styles["ProfileBody"]))

    rewards = profile["rewards"]
    if rewards:
        story.append(Spacer(1, 10))
        story.append(Paragraph("Награды", styles["Heading1"]))
        for index, reward in enumerate(rewards, start=1):
            story.append(Paragraph(f"{index}. {_p(reward['title'])}", styles["ProfileHeading"]))
            if reward["rows"]:
                story.append(_profile_table(reward["rows"], Paragraph, Table, TableStyle, colors, styles))
            story.append(Spacer(1, 6))

    doc.build(story)
    return buffer.getvalue()


def person_booklet_context(settings: Settings, person_id: int, return_to: str = "") -> dict[str, object]:
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise BookletError("Награжденный не найден.")
    rewards = list_person_rewards(settings.rewards_db_path, person_id, ranked=True)
    photos = _photo_entries(settings, person, PERSON_PHOTO_FIELDS)
    by_field = {photo["field"]: photo for photo in photos}
    groups = []
    for reward in rewards:
        reference = _photo_entries(settings, reward, [PhotoField("reward_image_path", "Изображение награды", "")])[0]
        groups.append({
            "reward": reward,
            "title": f"{reward.get('name') or 'Награда'}, № {reward.get('number') or '—'}",
            "reference": reference,
            "photos": [photo for photo in _photo_entries(settings, reward, REWARD_PHOTO_FIELDS) if photo["available"]],
        })
    return {
        "person": person,
        "rewards": rewards,
        "birth_line": f"{format_birth_year(person['birthday'])} года рождения" if person.get("birthday") else "",
        "person_photos": photos,
        "identity_photos": [by_field[field] for field in ("person_foto", "main_foto", "rewards_foto") if by_field[field]["available"]],
        "person_documents": [by_field[field] for field in ("card1_foto", "card2_foto", "book1_foto", "book2_foto") if by_field[field]["available"]],
        "reward_photo_groups": groups,
        "links": _person_links(person),
        "return_to": return_to,
    }


def generate_person_booklet_pdf(settings: Settings, person_id: int, output_path: Path | None = None) -> BookletPDFResult:
    context = person_booklet_context(settings, person_id)
    person = context["person"]

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from .summary_pdf import _summary_pdf_image
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

    font_name, bold_font = _register_booklet_serif(pdfmetrics, TTFont)
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = font_name
    ink = colors.HexColor("#302d27")
    rule = colors.HexColor("#b8ac95")
    styles.add(ParagraphStyle(name="BookletTitle", parent=styles["Title"], fontName=bold_font, fontSize=23, leading=26, alignment=0, textColor=ink))
    styles.add(ParagraphStyle(name="BookletHeading", parent=styles["Heading2"], fontName=bold_font, fontSize=13, leading=16, spaceBefore=12, spaceAfter=7, textColor=ink))
    styles.add(ParagraphStyle(name="BookletBody", parent=styles["BodyText"], fontName=font_name, fontSize=10, leading=13, textColor=ink))
    styles.add(ParagraphStyle(name="BookletCaption", parent=styles["BookletBody"], fontSize=8, leading=10, textColor=colors.HexColor("#655d4f")))
    styles.add(ParagraphStyle(name="BookletReward", parent=styles["BookletHeading"], borderWidth=0.5, borderColor=rule, borderPadding=6, spaceBefore=16))

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
    image_cache = {}

    def gallery(entries, columns=2, max_height=80 * mm):
        if not entries:
            return
        columns = min(columns, len(entries))
        width = doc.width / columns
        cells = []
        for entry in entries:
            try:
                photo = _summary_pdf_image(entry["resolved_path"], Image, width - 12, max_height, image_cache)
            except (OSError, ValueError):
                continue
            cells.append([photo, Spacer(1, 4), Paragraph(_p(entry["label"]), styles["BookletCaption"])])
        for offset in range(0, len(cells), columns):
            row = cells[offset:offset + columns]
            row += [""] * (columns - len(row))
            table = Table([row], colWidths=[width] * columns, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.append(table)

    story.append(Paragraph("БУКЛЕТ КАВАЛЕРА", styles["BookletCaption"]))
    story.append(Paragraph(_p(person.get("fio")), styles["BookletTitle"]))
    identity = [str(value) for value in (person.get("rank_name"), context["birth_line"]) if value]
    if identity:
        story.append(Paragraph(_p(" · ".join(identity)), styles["BookletBody"]))
    story.append(Spacer(1, 10))
    gallery(context["identity_photos"], columns=3, max_height=70 * mm)

    story.append(Paragraph("Все награды кавалера", styles["BookletHeading"]))
    for group in context["reward_photo_groups"]:
        reference = group["reference"]
        photo = ""
        if reference["available"]:
            try:
                photo = _summary_pdf_image(reference["resolved_path"], Image, 14 * mm, 16 * mm, image_cache)
            except (OSError, ValueError):
                pass
        row = Table([[photo, Paragraph(_p(group["title"]), styles["BookletBody"])]], colWidths=[18 * mm, doc.width - 18 * mm])
        row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, rule), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.append(row)
    if not context["rewards"]:
        story.append(Paragraph("Награды не найдены.", styles["BookletBody"]))
    _add_text_block(story, styles, Paragraph, "Краткая биография", person.get("biography"))
    if context["person_documents"]:
        story.append(Paragraph("Документы кавалера", styles["BookletHeading"]))
        gallery(context["person_documents"])
    for group in context["reward_photo_groups"]:
        story.append(Paragraph(_p(group["title"]), styles["BookletReward"]))
        gallery(group["photos"])
    _add_links(story, styles, Paragraph, context["links"])
    _add_text_block(story, styles, Paragraph, "Комментарий / заметки", person.get("comment"))

    def paper(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#f7f3e9"))
        canvas.rect(0, 0, *A4, fill=1, stroke=0)
        canvas.setStrokeColor(rule)
        canvas.setLineWidth(0.5)
        canvas.rect(8 * mm, 8 * mm, A4[0] - 16 * mm, A4[1] - 16 * mm, fill=0)
        canvas.setFont(font_name, 8)
        canvas.setFillColor(ink)
        canvas.drawCentredString(A4[0] / 2, 5 * mm, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=paper, onLaterPages=paper)
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
                try:
                    from PIL import Image
                    with Image.open(resolution.serving_path) as image:
                        image.verify()
                    entry["available"] = True
                    entry["resolved_path"] = resolution.serving_path
                except (OSError, ValueError):
                    entry["missing"] = True
                    entry["reason"] = "Файл изображения повреждён или не поддерживается"
        entries.append(entry)
    return entries


def _person_links(person: dict[str, object]) -> list[dict[str, str]]:
    links = [
        {"label": "Память народа", "value": str(person.get("link1") or "")},
        {"label": "Форум коллекционеров", "value": str(person.get("link2") or "")},
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


def _register_booklet_serif(pdfmetrics, TTFont) -> tuple[str, str]:
    for regular, bold in [
        ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
        ("/System/Library/Fonts/Supplemental/Times New Roman.ttf", "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
    ]:
        if Path(regular).is_file() and Path(bold).is_file():
            try:
                pdfmetrics.registerFont(TTFont("BookletSerif", regular))
                pdfmetrics.registerFont(TTFont("BookletSerifBold", bold))
                return "BookletSerif", "BookletSerifBold"
            except (OSError, ValueError):
                continue
    font = _register_pdf_font(pdfmetrics, TTFont)
    return font, font


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


def _add_profile_text_block(story: list[object], styles, Paragraph, title: str, value: object) -> None:
    if isinstance(value, str) and value.strip():
        story.append(Paragraph(title, styles["ProfileHeading"]))
        for paragraph in re.split(r"\n{2,}", value.strip()):
            story.append(Paragraph(_p(paragraph).replace("\n", "<br/>"), styles["ProfileBody"]))


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


def _profile_table(rows, Paragraph, Table, TableStyle, colors, styles):
    table = Table(
        [[Paragraph(_p(label), styles["ProfileBody"]), Paragraph(_p(value), styles["ProfileBody"])] for label, value in rows],
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


def _visible_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if not text or text == "—" or text.lower() == "none" else text


def _visible_rows(rows: list[tuple[str, object]]) -> list[tuple[str, str]]:
    visible = []
    for label, value in rows:
        text = _visible_text(value)
        if text:
            visible.append((label, text))
    return visible


def _formatted_if_present(value: object, formatter, *args) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    return _visible_text(formatter(value, *args))


def _p(value: object) -> str:
    if value is None:
        return "—"
    text = str(value).strip()
    return escape(text) if text else "—"
