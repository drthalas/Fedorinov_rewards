from __future__ import annotations

from pathlib import Path

from PIL import Image as PILImage

from ..config import Settings
from .booklets import (
    BookletError, BookletPDFResult, _booklet_output_dir, _p, _photo_entries,
    _register_booklet_serif, person_booklet_context, person_booklet_filename,
)
from .photos import PhotoField


def booklet2_context(settings: Settings, person_id: int, return_to: str = "") -> dict[str, object]:
    context = person_booklet_context(settings, person_id, return_to)
    identity = {item["field"]: item for item in context["identity_photos"]}
    documents = list(context["person_documents"])
    portrait = identity.pop("person_foto", None)
    lead_document = documents.pop(0) if documents else None
    inset = identity.pop("main_foto", None)
    media = [*documents, *identity.values()]
    for item in [*context["identity_photos"], *context["person_documents"], *[photo for group in context["reward_photo_groups"] for photo in group["photos"]]]:
        with PILImage.open(item["resolved_path"]) as image:
            item["ratio"] = image.width / image.height
            item["wide"] = item["ratio"] >= 1.4
    rank = _photo_entries(settings, context["person"], [PhotoField("rank_image_path", "Звание / специальность", "")])[0]
    remaining = list(media)
    rows = []
    while remaining:
        first = remaining.pop(0)
        pair = [first]
        if remaining and not (first["wide"] and remaining[0]["wide"]):
            pair.append(remaining.pop(0))
        fractions = (.4, .6) if len(pair) == 2 and pair[1]["wide"] else (.6, .4)
        rows.append({"photos": pair, "fractions": fractions})
    return {
        **context,
        "rank_insignia": rank if rank["available"] else None,
        "portrait": portrait,
        "lead_document": lead_document,
        "inset_photo": inset,
        "editorial_media": media,
        "editorial_rows": rows,
        "award_icons": [group["reference"] for group in context["reward_photo_groups"] if group["reference"]["available"]],
        "biography_parts": [part for part in str(context["person"].get("biography") or "").splitlines() if part.strip()],
    }


def booklet2_filename(settings: Settings, person_id: int) -> str:
    return person_booklet_filename(settings, person_id).replace("_booklet_", "_booklet2_")


def generate_booklet2_pdf(settings: Settings, person_id: int, output_path: Path | None = None) -> BookletPDFResult:
    context = booklet2_context(settings, person_id)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import BalancedColumns, Flowable, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from .summary_pdf import _summary_pdf_image
    except ImportError as exc:
        raise BookletError("PDF-библиотека reportlab не установлена.") from exc

    output_path = output_path.resolve() if output_path else _booklet_output_dir(settings) / booklet2_filename(settings, person_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    regular, bold = _register_booklet_serif(pdfmetrics, TTFont)
    ink = colors.HexColor("#292a25")
    caption = ParagraphStyle("EditorialCaption", fontName=regular, fontSize=8, leading=10, textColor=ink)
    photo_caption = ParagraphStyle("EditorialPhotoCaption", parent=caption, alignment=1)
    body = ParagraphStyle("EditorialBody", fontName=regular, fontSize=10, leading=12, textColor=ink, alignment=4, spaceAfter=5)
    title = ParagraphStyle("EditorialTitle", fontName=bold, fontSize=21, leading=23, textColor=ink)
    heading = ParagraphStyle("EditorialHeading", fontName=bold, fontSize=12, leading=14, textColor=ink, spaceAfter=6, keepWithNext=True)
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=13*mm, bottomMargin=13*mm, title=f"Буклет 2 - {context['person'].get('fio') or person_id}")
    cache = {}

    class PaperPhoto(Flowable):
        def __init__(self, entry, width, height, angle=0):
            Flowable.__init__(self)
            self.photo = _summary_pdf_image(entry["resolved_path"], Image, width-12, height-12, cache)
            self.caption = Paragraph(_p(entry["label"]), photo_caption)
            self.caption_width = self.photo.drawWidth + 6
            self.caption_height = self.caption.wrap(self.caption_width, 10_000)[1]
            self.width = width
            self.paper_height = self.photo.drawHeight + 12
            self.height = self.paper_height + self.caption_height + 3
            self.angle = angle

        def draw(self):
            canvas = self.canv
            w, h = self.photo.drawWidth+6, self.photo.drawHeight+6
            x = (self.width-w)/2
            canvas.saveState()
            canvas.translate(0, self.caption_height+3)
            canvas.translate(self.width/2, self.paper_height/2)
            canvas.rotate(self.angle)
            canvas.translate(-self.width/2, -self.paper_height/2)
            for offset, alpha in ((3, .04), (2, .07), (1, .1)):
                canvas.setFillColor(colors.black)
                canvas.setFillAlpha(alpha)
                canvas.rect(x+offset, 3-offset, w, h, fill=1, stroke=0)
            canvas.setFillAlpha(1)
            canvas.setFillColor(colors.HexColor("#f0eee4"))
            canvas.rect(x, 3, w, h, fill=1, stroke=0)
            self.photo.drawOn(canvas, x+3, 6)
            canvas.restoreState()
            self.caption.drawOn(canvas, (self.width-self.caption_width)/2, 0)

    def photo(entry, width, height, angle=0):
        return [PaperPhoto(entry, width, height, angle)]

    def pair(entries, fractions=(.4, .6), height=91*mm):
        entries = [entry for entry in entries if entry]
        if not entries:
            return []
        widths = [doc.width] if len(entries) == 1 else [doc.width*fraction for fraction in fractions]
        cells = [photo(entry, width-8, height, -.4 if index == 0 else .3) for index, (entry, width) in enumerate(zip(entries, widths))]
        table = Table([cells], colWidths=widths)
        table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
        return [table, Spacer(1, 8)]

    person = context["person"]
    identity = [Paragraph("Буклет кавалера", caption), Paragraph(_p(person.get("fio")), title), Paragraph(_p(" · ".join(str(v) for v in (person.get("rank_name"), context["birth_line"]) if v)), caption)]
    insignia = _summary_pdf_image(context["rank_insignia"]["resolved_path"], Image, 15*mm, 17*mm, cache) if context["rank_insignia"] else ""
    icons = [_summary_pdf_image(entry["resolved_path"], Image, 8*mm, 14*mm, cache) for entry in context["award_icons"][:7]]
    ribbon = Table([icons], colWidths=[9*mm]*len(icons)) if icons else ""
    if ribbon:
        ribbon.setStyle(TableStyle([("LEFTPADDING", (0,0), (-1,-1), 0), ("RIGHTPADDING", (0,0), (-1,-1), 0)]))
    head = Table([[insignia, identity, ribbon]], colWidths=[18*mm if insignia else 0, doc.width-(18*mm if insignia else 0)-65*mm, 65*mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
    story = [head, *pair([context["portrait"], context["lead_document"]])]
    biography = [Paragraph(_p(part), body) for part in str(person.get("biography") or "").splitlines() if part.strip()]
    if context["inset_photo"]:
        insert_at = max(1, (len(biography)+1)//2) if biography else 0
        biography[insert_at:insert_at] = photo(context["inset_photo"], doc.width/2-24, 68*mm, .4)
    if biography:
        story.extend([BalancedColumns(biography, nCols=2, innerPadding=8, needed=80*mm, spaceAfter=10), Spacer(1, 5)])
    for row in context["editorial_rows"]:
        story.extend(pair(row["photos"], row["fractions"], height=82*mm))
    if context["reward_photo_groups"]:
        story.append(Paragraph("Награды", heading))
        for group in context["reward_photo_groups"]:
            reference = group["reference"]
            icon = _summary_pdf_image(reference["resolved_path"], Image, 7*mm, 9*mm, cache) if reference["available"] else ""
            row = Table([[icon, Paragraph(_p(group["title"]), body)]], colWidths=[11*mm, doc.width-11*mm])
            row.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
            story.append(row)
        story.append(Spacer(1, 8))
    for group in context["reward_photo_groups"]:
        if not group["photos"]:
            continue
        story.append(Paragraph(_p(group["title"]), heading))
        for index in range(0, len(group["photos"]), 2):
            story.extend(pair(group["photos"][index:index+2], (.46, .54), height=85*mm))
    for link in context["links"]:
        if link["value"]:
            text = f'<link href="{_p(link["url"])}">{_p(link["value"])}</link>' if link["url"] else _p(link["value"])
            story.append(Paragraph(f'{_p(link["label"])}: {text}', body))
    if person.get("comment"):
        story.extend([Spacer(1, 5), Paragraph(_p(person["comment"]), body)])

    tile = ImageReader(str(Path(__file__).resolve().parents[1]/"static"/"booklet-paper-v1.png"))

    def page(canvas, document):
        canvas.saveState()
        if not canvas.hasForm("EditorialPaper"):
            canvas.beginForm("EditorialPaper", 0, 0, *A4)
            for y in range(0, int(A4[1])+1, 48):
                for x in range(0, int(A4[0])+1, 48):
                    canvas.drawImage(tile, x, y, width=48, height=48)
            canvas.endForm()
        canvas.doForm("EditorialPaper")
        canvas.setStrokeColor(colors.HexColor("#8c887b"))
        canvas.setLineWidth(.45)
        canvas.rect(9*mm, 9*mm, A4[0]-18*mm, A4[1]-18*mm, stroke=1, fill=0)
        canvas.setFillColor(ink)
        canvas.setFont(regular, 8)
        canvas.drawCentredString(A4[0]/2, 5*mm, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
    return BookletPDFResult(output_path, output_path.name)
