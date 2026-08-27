from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import math
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from ..repositories.summary import summary_matrix_table, summary_table


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIN_COLUMN_WIDTH = 10.0
MAX_COLUMN_WIDTH = 44.0
EXCEL_CELL_TEXT_LIMIT = 32767

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
_CORE_NS = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"
_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_APP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

ET.register_namespace("", _MAIN_NS)
ET.register_namespace("r", _REL_NS)
ET.register_namespace("cp", _CORE_NS)
ET.register_namespace("dc", _DC_NS)
ET.register_namespace("dcterms", _DCTERMS_NS)
ET.register_namespace("xsi", _XSI_NS)


def _tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _column_name(index: int) -> str:
    name = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _clean_text(value: object) -> str:
    text = str(value or "")
    cleaned = "".join(
        character
        for character in text
        if character in "\t\n\r"
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
    )
    return cleaned[:EXCEL_CELL_TEXT_LIMIT]


def _display_width(value: object) -> int:
    lines = _clean_text(value).splitlines() or [""]
    return max(sum(2 if ord(character) > 255 else 1 for character in line) for line in lines)


def _column_widths(headers: list[str], rows: list[list[object]]) -> list[float]:
    widths: list[float] = []
    for index, header in enumerate(headers):
        content_width = max(
            [_display_width(header), *(_display_width(row[index]) for row in rows if index < len(row))],
            default=0,
        )
        widths.append(min(MAX_COLUMN_WIDTH, max(MIN_COLUMN_WIDTH, float(content_width + 2))))
    return widths


def _content_types() -> bytes:
    root = ET.Element(_tag(_CONTENT_NS, "Types"))
    ET.SubElement(root, _tag(_CONTENT_NS, "Default"), Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(root, _tag(_CONTENT_NS, "Default"), Extension="xml", ContentType="application/xml")
    ET.SubElement(root, _tag(_CONTENT_NS, "Override"), PartName="/xl/workbook.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
    ET.SubElement(root, _tag(_CONTENT_NS, "Override"), PartName="/xl/worksheets/sheet1.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    ET.SubElement(root, _tag(_CONTENT_NS, "Override"), PartName="/xl/styles.xml", ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml")
    ET.SubElement(root, _tag(_CONTENT_NS, "Override"), PartName="/docProps/core.xml", ContentType="application/vnd.openxmlformats-package.core-properties+xml")
    ET.SubElement(root, _tag(_CONTENT_NS, "Override"), PartName="/docProps/app.xml", ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml")
    return _xml_bytes(root)


def _package_relationships() -> bytes:
    root = ET.Element(_tag(_PACKAGE_REL_NS, "Relationships"))
    ET.SubElement(root, _tag(_PACKAGE_REL_NS, "Relationship"), Id="rId1", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", Target="xl/workbook.xml")
    ET.SubElement(root, _tag(_PACKAGE_REL_NS, "Relationship"), Id="rId2", Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties", Target="docProps/core.xml")
    ET.SubElement(root, _tag(_PACKAGE_REL_NS, "Relationship"), Id="rId3", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties", Target="docProps/app.xml")
    return _xml_bytes(root)


def _workbook() -> bytes:
    root = ET.Element(_tag(_MAIN_NS, "workbook"))
    sheets = ET.SubElement(root, _tag(_MAIN_NS, "sheets"))
    ET.SubElement(sheets, _tag(_MAIN_NS, "sheet"), {"name": "Сводная таблица", "sheetId": "1", _tag(_REL_NS, "id"): "rId1"})
    return _xml_bytes(root)


def _workbook_relationships() -> bytes:
    root = ET.Element(_tag(_PACKAGE_REL_NS, "Relationships"))
    ET.SubElement(root, _tag(_PACKAGE_REL_NS, "Relationship"), Id="rId1", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", Target="worksheets/sheet1.xml")
    ET.SubElement(root, _tag(_PACKAGE_REL_NS, "Relationship"), Id="rId2", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles", Target="styles.xml")
    return _xml_bytes(root)


def _styles() -> bytes:
    root = ET.Element(_tag(_MAIN_NS, "styleSheet"))
    fonts = ET.SubElement(root, _tag(_MAIN_NS, "fonts"), count="2")
    font = ET.SubElement(fonts, _tag(_MAIN_NS, "font"))
    ET.SubElement(font, _tag(_MAIN_NS, "sz"), val="11")
    ET.SubElement(font, _tag(_MAIN_NS, "name"), val="Calibri")
    header_font = ET.SubElement(fonts, _tag(_MAIN_NS, "font"))
    ET.SubElement(header_font, _tag(_MAIN_NS, "b"))
    ET.SubElement(header_font, _tag(_MAIN_NS, "color"), rgb="FFF0DDBA")
    ET.SubElement(header_font, _tag(_MAIN_NS, "sz"), val="11")
    ET.SubElement(header_font, _tag(_MAIN_NS, "name"), val="Calibri")
    fills = ET.SubElement(root, _tag(_MAIN_NS, "fills"), count="3")
    ET.SubElement(ET.SubElement(fills, _tag(_MAIN_NS, "fill")), _tag(_MAIN_NS, "patternFill"), patternType="none")
    ET.SubElement(ET.SubElement(fills, _tag(_MAIN_NS, "fill")), _tag(_MAIN_NS, "patternFill"), patternType="gray125")
    header_fill = ET.SubElement(ET.SubElement(fills, _tag(_MAIN_NS, "fill")), _tag(_MAIN_NS, "patternFill"), patternType="solid")
    ET.SubElement(header_fill, _tag(_MAIN_NS, "fgColor"), rgb="FF33291E")
    ET.SubElement(header_fill, _tag(_MAIN_NS, "bgColor"), indexed="64")
    borders = ET.SubElement(root, _tag(_MAIN_NS, "borders"), count="1")
    border = ET.SubElement(borders, _tag(_MAIN_NS, "border"))
    for side in ("left", "right", "top", "bottom", "diagonal"):
        ET.SubElement(border, _tag(_MAIN_NS, side))
    cell_style_xfs = ET.SubElement(root, _tag(_MAIN_NS, "cellStyleXfs"), count="1")
    ET.SubElement(cell_style_xfs, _tag(_MAIN_NS, "xf"), numFmtId="0", fontId="0", fillId="0", borderId="0")
    cell_xfs = ET.SubElement(root, _tag(_MAIN_NS, "cellXfs"), count="3")
    ET.SubElement(cell_xfs, _tag(_MAIN_NS, "xf"), numFmtId="0", fontId="0", fillId="0", borderId="0", xfId="0")
    header_xf = ET.SubElement(cell_xfs, _tag(_MAIN_NS, "xf"), numFmtId="0", fontId="1", fillId="2", borderId="0", xfId="0", applyFont="1", applyFill="1", applyAlignment="1")
    ET.SubElement(header_xf, _tag(_MAIN_NS, "alignment"), wrapText="1", vertical="center")
    wrap_xf = ET.SubElement(cell_xfs, _tag(_MAIN_NS, "xf"), numFmtId="0", fontId="0", fillId="0", borderId="0", xfId="0", applyAlignment="1")
    ET.SubElement(wrap_xf, _tag(_MAIN_NS, "alignment"), wrapText="1", vertical="top")
    cell_styles = ET.SubElement(root, _tag(_MAIN_NS, "cellStyles"), count="1")
    ET.SubElement(cell_styles, _tag(_MAIN_NS, "cellStyle"), name="Normal", xfId="0", builtinId="0")
    return _xml_bytes(root)


def _worksheet(headers: list[str], rows: list[list[object]]) -> bytes:
    root = ET.Element(_tag(_MAIN_NS, "worksheet"))
    views = ET.SubElement(root, _tag(_MAIN_NS, "sheetViews"))
    view = ET.SubElement(views, _tag(_MAIN_NS, "sheetView"), workbookViewId="0")
    ET.SubElement(view, _tag(_MAIN_NS, "pane"), ySplit="1", topLeftCell="A2", activePane="bottomLeft", state="frozen")
    columns = ET.SubElement(root, _tag(_MAIN_NS, "cols"))
    for index, width in enumerate(_column_widths(headers, rows), start=1):
        ET.SubElement(columns, _tag(_MAIN_NS, "col"), min=str(index), max=str(index), width=f"{width:.2f}", customWidth="1")
    sheet_data = ET.SubElement(root, _tag(_MAIN_NS, "sheetData"))
    all_rows = [headers, *rows]
    for row_index, values in enumerate(all_rows, start=1):
        row_node = ET.SubElement(sheet_data, _tag(_MAIN_NS, "row"), r=str(row_index))
        for column_index, value in enumerate(values, start=1):
            reference = f"{_column_name(column_index)}{row_index}"
            style = "1" if row_index == 1 else "2"
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                cell = ET.SubElement(row_node, _tag(_MAIN_NS, "c"), r=reference, s=style, t="n")
                ET.SubElement(cell, _tag(_MAIN_NS, "v")).text = str(value)
            else:
                cell = ET.SubElement(row_node, _tag(_MAIN_NS, "c"), r=reference, s=style, t="inlineStr")
                inline = ET.SubElement(cell, _tag(_MAIN_NS, "is"))
                text = ET.SubElement(inline, _tag(_MAIN_NS, "t"))
                text.set(_tag("http://www.w3.org/XML/1998/namespace", "space"), "preserve")
                text.text = _clean_text(value)
    if headers:
        last_column = _column_name(len(headers))
        ET.SubElement(root, _tag(_MAIN_NS, "autoFilter"), ref=f"A1:{last_column}{max(1, len(all_rows))}")
    return _xml_bytes(root)


def _core_properties() -> bytes:
    root = ET.Element(_tag(_CORE_NS, "coreProperties"))
    ET.SubElement(root, _tag(_DC_NS, "creator")).text = "Fedorinov Rewards"
    created = ET.SubElement(root, _tag(_DCTERMS_NS, "created"), {_tag(_XSI_NS, "type"): "dcterms:W3CDTF"})
    created.text = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return _xml_bytes(root)


def _app_properties() -> bytes:
    root = ET.Element(_tag(_APP_NS, "Properties"))
    ET.SubElement(root, _tag(_APP_NS, "Application")).text = "Fedorinov Rewards"
    return _xml_bytes(root)


def workbook_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("_rels/.rels", _package_relationships())
        archive.writestr("docProps/core.xml", _core_properties())
        archive.writestr("docProps/app.xml", _app_properties())
        archive.writestr("xl/workbook.xml", _workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships())
        archive.writestr("xl/styles.xml", _styles())
        archive.writestr("xl/worksheets/sheet1.xml", _worksheet(headers, rows))
    return output.getvalue()


def summary_xlsx_bytes(rows: list[dict[str, object]]) -> bytes:
    headers, values = summary_table(rows)
    return workbook_bytes(headers, values)


def summary_matrix_xlsx_bytes(matrix: dict[str, object]) -> bytes:
    headers, values = summary_matrix_table(matrix)
    return workbook_bytes(headers, values)
