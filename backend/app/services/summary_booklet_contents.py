"""Contents from the exact filtered membership snapshot of a combined booklet."""
from .booklets import _register_booklet_serif
from .display import format_birth_year
from html import escape


def generate_contents_pdf(rows, output_path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font, bold = _register_booklet_serif(pdfmetrics, TTFont)
    ink, rule = colors.HexColor('#302d27'), colors.HexColor('#9d9584')
    body = ParagraphStyle('ContentsBody', fontName=font, fontSize=10, leading=13, textColor=ink)
    heading = ParagraphStyle('ContentsHeading', parent=body, fontName=bold)
    title = ParagraphStyle('ContentsTitle', parent=heading, fontSize=23, leading=26, spaceAfter=14)
    p = lambda value, style=body: Paragraph(escape(str(value or '—')), style)
    data = [[p(value, heading) for value in ('ФИО', 'Год рождения', 'Звание', 'Номер ордена')]]
    for row in rows:
        data.append([p(row.get('fio')), p(format_birth_year(row.get('birthday'))),
                     p(row.get('rank_name')), p(', '.join(str(n) for n in row.get('pdf_reward_numbers') or ()) )])
    table = Table(data, colWidths=[78*mm, 25*mm, 43*mm, 36*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LINEBELOW', (0,0), (-1,0), .7, rule),
        ('LINEBELOW', (0,1), (-1,-1), .3, rule),
        ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    doc = SimpleDocTemplate(str(output_path), pagesize=A4, leftMargin=14*mm,
        rightMargin=14*mm, topMargin=12*mm, bottomMargin=12*mm, title='Содержание буклета')

    def paper(canvas, document):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#e2dfd5'))
        canvas.rect(0, 0, *A4, fill=1, stroke=0)
        canvas.setStrokeColor(rule)
        canvas.rect(8*mm, 8*mm, A4[0]-16*mm, A4[1]-16*mm, fill=0)
        canvas.setFont(font, 8)
        canvas.setFillColor(ink)
        canvas.drawCentredString(A4[0]/2, 5*mm, str(document.page))
        canvas.restoreState()

    doc.build([p('Содержание буклета', title), table, Spacer(1, 10),
               p(f'Всего кавалеров: {len(rows)}', heading)], onFirstPage=paper, onLaterPages=paper)
