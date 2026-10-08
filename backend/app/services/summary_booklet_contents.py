"""Contents from the exact filtered membership snapshot of a combined booklet."""
from .booklets import _register_booklet_serif
from .display import format_birth_year
from html import escape


def _unquote_name(name):
    """Remove only quotation marks enclosing the entire name."""
    pairs = {'«': '»', '"': '"', '“': '”'}
    while len(name) > 1 and pairs.get(name[0]) == name[-1]:
        opening, closing = name[0], name[-1]
        if opening == closing:
            if name.count(opening) != 2:
                break
        else:
            depth = 0
            for index, char in enumerate(name):
                depth += (char == opening) - (char == closing)
                if depth == 0 and index < len(name) - 1:
                    break
            else:
                name = name[1:-1].strip()
                continue
            break
        name = name[1:-1].strip()
    return name


def _reward_kind(label):
    import re
    for pattern, instrumental in ((r'Ордена?', 'орденом'),
                                  (r'Медал[ьи]', 'медалью'),
                                  (r'Знак[и]?', 'знаком')):
        if re.match(r'^' + pattern + r'\b', label, re.IGNORECASE):
            return instrumental
    return None


def reward_heading(name, kind=None):
    """Quote the official name and inflect only a recognized award kind."""
    import re
    exact = str(name or '').strip()
    display = _unquote_name(exact)
    leading = re.fullmatch(r'(Орден|Медаль|Знак)\s+(.+)', display, re.IGNORECASE)
    if leading:
        named_kind = _reward_kind(leading[1])
        # A different hierarchy kind may mean the word belongs to the title.
        if kind and kind != named_kind:
            return f'Награждённые — {exact}'
        kind = named_kind
        display = _unquote_name(leading[2])
    if kind and display:
        # Preserve meaningful inner quotations using Russian nested quote marks.
        display = display.translate(str.maketrans({'«': '„', '»': '“', '“': '„', '”': '“'}))
        display = re.sub(r'"([^"]+)"', r'„\1“', display)
        return f'Награждённые {kind} «{display}»'
    return f'Награждённые — {exact}'


def contents_selection(db_path, matrix, filters):
    """Use the actual filtered columns; never choose a person's other reward."""
    from ..repositories.guides import guide_level_item_lineage
    columns = matrix.get('reward_columns') or []
    title = 'Награждённые'
    if matrix.get('rows') and len(columns) == 1:
        column = columns[0]
        name = str(column.get('name') or '').strip()
        if name and name != '—':
            lineage = guide_level_item_lineage(db_path, 3, int(column.get('id') or 0))
            kinds = {_reward_kind(item['name']) for item in lineage if item['level'] in (1, 2)} - {None}
            title = reward_heading(name, kinds.pop() if len(kinds) == 1 else None)
    return dict(title=title)


def generate_contents_pdf(rows, output_path, selection=None):
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
    theme = ParagraphStyle('ContentsTheme', parent=title, fontSize=28, leading=32, alignment=1, keepWithNext=True)
    title.keepWithNext = True
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

    selection = selection or dict(title='Награждённые')
    intro = [p(selection['title'], theme)] if rows else []
    doc.build([*intro, p('Содержание буклета', title), table, Spacer(1, 10),
               p(f'Всего кавалеров: {len(rows)}', heading)], onFirstPage=paper, onLaterPages=paper)
