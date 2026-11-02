"""Offline payload transfer onto a NEW authentic export; never re-sign old data.

No route or SQLite writer. The source research digest must be approved separately.
Only allowed payload cells/claims are copied; every fresh hidden byte is retained.
"""
from collections import Counter
from contextlib import closing
from io import BytesIO
from zipfile import ZipFile
import hashlib
import hmac
import json
import re
from xml.etree import ElementTree as ET
from . import biography_enrichment as bio

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
CLAIMS={'ID кавалера':'person_id','ФИО в источнике':'ФИО в карточке','Год в источнике':'Год в карточке',
        'Награда в источнике':'Награда в карточке','Номер в источнике':'Номер в карточке','Источник':'source_url',
        'Подтверждённые факты':'notes','Проверка личности':'Идентификация','Год подтверждён':'Год подтверждён'}


def _cell(row, reference, value):
    tag='{'+NS+'}'; cell=next((c for c in row if c.get('r')==reference),None)
    if cell is None:cell=ET.SubElement(row,tag+'c',{'r':reference})
    for child in list(cell):cell.remove(child)
    cell.set('t','inlineStr');text=ET.SubElement(ET.SubElement(cell,tag+'is'),tag+'t')
    text.set('{http://www.w3.org/XML/1998/namespace}space','preserve');text.text=value or ''


def recover(settings, research, fresh, *, expected_research_sha256):
    if not expected_research_sha256 or hashlib.sha256(research).hexdigest()!=expected_research_sha256:
        raise bio.ValidationError('Исследовательский файл не совпал с утверждённым SHA256. Перенос остановлен.')
    source=bio.read_rows(research);target=bio.read_rows(fresh)
    source_counts=Counter(e['values']['person_id'] for e in source);target_counts=Counter(e['values']['person_id'] for e in target)
    if any(n!=1 for n in source_counts.values()) or any(n!=1 for n in target_counts.values()):
        raise bio.ValidationError('Повторяющиеся ID. Для переноса нужны однозначные строки.')
    try:secret=(bio._state_path(settings)/'signing.key').read_bytes()
    except OSError as exc:raise bio.ValidationError('Ключ свежей выгрузки недоступен. Перенос нельзя подтвердить.') from exc
    if len(secret)!=32:raise bio.ValidationError('Ключ свежей выгрузки повреждён. Перенос остановлен.')
    copied={};review=[];source_by_id={e['values']['person_id']:e for e in source}
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        for entry in target:
            v=entry['values'];pid=v['person_id'];serialized=v.get('snapshot','');signature=v.get('snapshot_signature','')
            expected=hmac.new(secret,serialized.encode(),hashlib.sha256).hexdigest()
            if entry['invalid'] or v.get('_format')!='visible-7-v2' or not serialized or not re.fullmatch(r'[a-f0-9]{64}',signature) or not hmac.compare_digest(signature,expected):
                raise bio.ValidationError('Подпись свежей выгрузки не подтверждена. Нельзя переносить данные.')
            snapshot=json.loads(serialized)
            if snapshot.get('version')!=2 or snapshot.get('contract')!='visible-7-v2':
                raise bio.ValidationError('Нужна актуальная подписанная выгрузка.')
            original=bio._original(snapshot)
            if any(bio.key(v.get(k))!=bio.key(val) for k,val in original.items()):
                raise bio.ValidationError('Защищённые поля свежей выгрузки изменены.')
            if bio._identity(connection,int(pid))!=snapshot['person']:
                raise bio.ValidationError('Свежая выгрузка уже устарела. Перенос остановлен.')
            if any(v.get(k) for k in ['biography','source_url','status','ФИО в карточке','Год в карточке']):
                raise bio.ValidationError('Для переноса нужна чистая свежая выгрузка без заполненных данных.')
            old=source_by_id.get(pid)
            if old is None:continue
            ov=old['values']
            try:previous=json.loads(ov['snapshot'])['person']
            except (KeyError,ValueError,TypeError) as exc:raise bio.ValidationError('Нет исходной личности исследовательской строки.') from exc
            fields=[n for n in snapshot['person'] if previous.get(n)!=snapshot['person'][n]]
            if json.loads(ov['snapshot']).get('selection')!=snapshot.get('selection'):fields.append('selection')
            if old['invalid'] or fields or len(ov.get('biography',''))>2500:
                review.append({'person_id':pid,'fields':fields,'reason':'Личность или награды изменились; нужен отдельный review.' if fields else 'Строка требует проверки формата.'})
                continue
            if any(bio.key(ov.get(k))!=bio.key(val) for k,val in bio._original(json.loads(ov['snapshot'])).items()):
                review.append({'person_id':pid,'reason':'Защищённые значения исследовательской строки отличаются.'});continue
            copied[pid]={'target_row':entry['row'],'values':ov}
    review.extend({'person_id':pid,'reason':'ID отсутствует в свежей выгрузке.'} for pid in source_by_id if pid not in target_counts)
    with ZipFile(BytesIO(fresh)) as archive:
        members={info.filename:archive.read(info.filename) for info in archive.infolist()}
        workbook=ET.fromstring(members['xl/workbook.xml']);sheets=workbook.find('{'+NS+'}sheets')
        if any(s.get('name')==bio.PROPOSALS_SHEET for s in sheets):
            raise bio.ValidationError('Свежая выгрузка уже содержит предложения. Нужна чистая выгрузка.')
        sheet=ET.fromstring(members['xl/worksheets/sheet1.xml']);rows={int(r.get('r')):r for r in sheet.find('{'+NS+'}sheetData')}
        for item in copied.values():
            number=item['target_row'];v=item['values']
            for letter,key in [('E','biography'),('F','source_url'),('G','status')]:_cell(rows[number],letter+str(number),v.get(key,''))
        replacements={'xl/worksheets/sheet1.xml':ET.tostring(sheet,encoding='utf-8',xml_declaration=True)}
        proposal_items=[(pid,item['values']) for pid,item in copied.items() if any(item['values'].get(k) for k in ['ФИО в карточке','Год в карточке','notes','Номер в карточке'])]
        if proposal_items:
            claims=ET.Element('{'+NS+'}worksheet');data=ET.SubElement(claims,'{'+NS+'}sheetData')
            for index,values in enumerate([[*CLAIMS]]+[[v.get(key,'да' if key=='Год подтверждён' else '') if key!='person_id' else pid for key in CLAIMS.values()] for pid,v in proposal_items],1):
                row=ET.SubElement(data,'{'+NS+'}row',{'r':str(index)})
                for col,value in enumerate(values):_cell(row,chr(65+col)+str(index),value)
            relationships=ET.fromstring(members['xl/_rels/workbook.xml.rels'])
            used={r.get('Id') for r in relationships};n=1
            while 'rId'+str(n) in used:n+=1
            rid='rId'+str(n);i=1
            while 'xl/worksheets/sheet'+str(i)+'.xml' in members:i+=1
            path='xl/worksheets/sheet'+str(i)+'.xml'
            ET.SubElement(sheets,'{'+NS+'}sheet',{'name':bio.PROPOSALS_SHEET,'sheetId':str(max(int(s.get('sheetId')) for s in sheets)+1),'{'+REL+'}id':rid})
            ET.SubElement(relationships,'{'+PKG+'}Relationship',{'Id':rid,'Type':REL+'/worksheet','Target':'/'+path})
            types=ET.fromstring(members['[Content_Types].xml'])
            ET.SubElement(types,'{'+CT+'}Override',{'PartName':'/'+path,'ContentType':'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
            replacements.update({path:ET.tostring(claims,encoding='utf-8',xml_declaration=True),'xl/workbook.xml':ET.tostring(workbook,encoding='utf-8',xml_declaration=True),'xl/_rels/workbook.xml.rels':ET.tostring(relationships,encoding='utf-8',xml_declaration=True),'[Content_Types].xml':ET.tostring(types,encoding='utf-8',xml_declaration=True)})
        output=BytesIO()
        with ZipFile(output,'w') as result:
            for info in archive.infolist():result.writestr(info,replacements.pop(info.filename,members[info.filename]))
            for name,value in replacements.items():result.writestr(name,value)
    content=output.getvalue();checked=bio.read_rows(content);baseline={e['values']['person_id']:e['values'] for e in target}
    for entry in checked:
        v=entry['values'];old=baseline[v['person_id']]
        for field in [*bio._original(json.loads(old['snapshot'])),'snapshot','snapshot_signature']:
            if v.get(field)!=old.get(field):raise RuntimeError('Recovery changed a protected field')
    report={'research_sha256':expected_research_sha256,'fresh_sha256':hashlib.sha256(fresh).hexdigest(),
            'recovery_sha256':hashlib.sha256(content).hexdigest(),'rows_copied':len(copied),
            'biographies_copied':sum(not bio.blank(i['values'].get('biography')) for i in copied.values()),
            'biographies_preserved_in_source':sum(not bio.blank(i['values'].get('biography')) for i in source),
            'review':review,'database_writes':0,'old_file_resigned':False,'hidden_preserved':True}
    return content,report
