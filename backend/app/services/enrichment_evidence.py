"""Source assertions are separate from, and never modify, signed originals."""
import re
from urllib.parse import urlsplit, parse_qs

from . import biography_enrichment as bio
from .dates import format_birth_year_input, normalize_birth_year_input


def sources(raw):
    result = []
    for url in raw.splitlines():
        try:
            host = urlsplit(url).hostname or ''
        except ValueError:
            host = ''
        result.append({'name':'Герои страны' if host.removeprefix('www.')=='warheroes.ru' else host or 'Источник', 'url':url})
    return result


def summary_assertions(values, snapshot):
    """Strict GSS-II identity compatibility for seven-column research summaries.

    Never infer a birth-year correction from prose. Explicit source year/caveats
    belong in validated proposal columns; the signed originals remain immutable.
    """
    if values.get('ФИО в карточке') or values.get('Награда в карточке'):return values
    body=bio.text(values.get('biography'));intro=body.split('(',1)[0].strip()
    names=intro.split()
    if len(names)!=3 or not all(re.fullmatch(r'[А-Яа-яЁё-]+',n) for n in names):return values
    current=bio.key(snapshot['person']['fio']).split()
    if len(current)!=3 or sorted(map(bio.key,names))!=sorted(current):return values
    if not re.search(r'дважды\s+герой\s+советского\s+союза',body,re.I):return values
    selected=[a for a in snapshot['person']['awards'] if all(a[bio.IDS[i]]==v for i,v in enumerate(snapshot['selection']))]
    award=next((a for a in selected if bio.key(a['award'])=='герой советского союза ii'),None)
    if not award or not award['number']:return values
    exact=re.search(r'втор(?:ой|ая|ую)\s+медал[ьиью]+[^.\n]{0,55}золотая[^.\n]{0,30}звезда[^.\n]{0,20}№\s*'+re.escape(str(award['number']))+r'(?!\d)',body,re.I)
    if not exact:return values
    result=dict(values)
    result.update({'ФИО в карточке':snapshot['person']['fio'],'Награда в карточке':award['award'],
        'Номер в карточке':str(award['number']),'notes':'В тексте источника: полное ФИО, дважды ГСС, '+exact.group(0)+'.',
        'Идентификация':'Полное ФИО и точная вторая Звезда подтверждены текстом','_evidence_origin':'biography-summary'})
    return result


def identity_name(value):
    value=re.sub(r'\([^)]*\)','',bio.key(value))
    # Documented patronymic variants; used only with exact award/serial + year.
    return ' '.join({'артемьевич':'артемович'}.get(x,x) for x in value.split())

def analyze(snapshot, values, current):
    fio = bio.text(values.get('ФИО в карточке'))
    year = bio.text(values.get('Год в карточке'))
    award = bio.key(values.get('Награда в карточке'))
    notes = bio.text(values.get('notes'))
    source = bio.text(values.get('source_url'))
    statement = bio.key(values.get('Идентификация'))
    selected = [a for a in snapshot['person']['awards'] if all(a[bio.IDS[i]]==v for i,v in enumerate(snapshot['selection']))]
    labour = [a for a in selected if 'трудов' in bio.key(a['award']) and 'слав' in bio.key(a['award']) and re.search(r'\b(?:i|1)\b',bio.key(a['award']))]
    relevant = labour or selected
    matched = [a for a in relevant if bio.key(a['award'])==award]
    def full_name(value):
        plain = re.sub(r'\([^)]*\)','',bio.text(value))
        return len([w for w in re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*",plain,re.UNICODE) if len(w)>1])>=2
    same_fio = full_name(fio) and full_name(current['fio']) and bio.key(fio)==bio.key(current['fio'])
    variant = full_name(fio) and full_name(current['fio']) and identity_name(fio)==identity_name(current['fio'])
    supplied_serial = bio.text(values.get('Номер в карточке'))
    numbered = [a for a in matched if a['number'] not in (None,'',0,'0')]
    serial_match = any((supplied_serial and supplied_serial==str(a['number'])) or re.search(
        r'(?:№|номер\s*)\s*'+re.escape(str(a['number']))+r'(?!\d)',notes,re.I) for a in numbered)
    negative = bool(re.search(r'не подтвержд|не установ|не совпад|сомнен|требует проверк|не проверен',statement))
    negative = negative or bool(re.search(r'(?:личность|идентификация)\s+(?:не подтвержд|не установ|требует проверк|оста[её]тся на проверке)|фио\s+не\s+(?:совпад|подтвержд)',bio.key(notes)))
    problems = []
    if not full_name(current['fio']) or fio and not full_name(fio):
        problems.append('Для надёжной сверки нужно полное ФИО. Одной фамилии или инициалов недостаточно.')
    if negative or fio and not same_fio:
        problems.append('ФИО в источнике не подтверждает, что это тот же кавалер.')
    if award and not matched:
        problems.append('Награда или степень в источнике отличается от выбранной награды.')
    if supplied_serial and matched and not any(supplied_serial==str(a['number']) for a in numbered):
        problems.append('Номер награды в источнике не совпадает.')
    valid_source = False
    warheroes = False
    try:
        urls = source.splitlines()
        valid_source = bool(urls) and len(source)<=4000 and all(urlsplit(u).scheme in {'http','https'} and urlsplit(u).hostname
            and not urlsplit(u).username and not urlsplit(u).password for u in urls)
        warheroes = valid_source and all((urlsplit(u).hostname or '').removeprefix('www.')=='warheroes.ru'
            and urlsplit(u).path=='/hero/hero.asp' and any(str(x).isdigit() and int(x)>0 for k,v in parse_qs(urlsplit(u).query).items() if k.casefold()=='hero_id' for x in v) for u in urls)
    except ValueError:
        pass
    valid_year = False
    if year:
        try:
            normalize_birth_year_input(year,required=True)
            valid_year = True
        except ValueError:
            pass
    current_year = format_birth_year_input(current['birthday'])
    rank = bio.key(values.get('Звание в карточке'))
    # Without a serial, require two additional matching source attributes. A
    # generic civilian rank and placeholder 1945 cannot corroborate identity.
    corroborated = not numbered and bool(matched) and valid_year and year==current_year and year!='1945' and rank not in {'','гражданский','неизвестно'} and rank==bio.key(snapshot['person']['rank'])
    variant_verified = variant and serial_match and valid_year and year==current_year
    material = bool(re.search(r'другой (?:человек|кавалер)|не тот (?:человек|кавалер)|номер не совпад|награда не совпад',bio.key(notes+' '+statement)))
    if (variant_verified or same_fio and serial_match) and not material:
        problems=[p for p in problems if not p.startswith('ФИО в источнике')]
    verified = bool(valid_source and not problems and not material and (same_fio or variant_verified) and matched and len(notes)>=10 and (serial_match or corroborated))
    # An omitted parenthesized surname can be reviewed, never auto-approved.
    # Exact signed award/serial and matching birth year independently corroborate
    # the alias. Unrelated names, different awards/serials and contrary evidence
    # cannot be overridden by an Owner checkbox.
    plain = lambda name: bio.key(re.sub(r'\([^)]*\)', '', name))
    alias = full_name(fio) and full_name(current['fio']) and plain(fio)==plain(current['fio'])
    contradiction = bool(re.search(r'другой (?:человек|кавалер)|не тот (?:человек|кавалер)|номер не совпад|награда не совпад', bio.key(notes)))
    manual_identity = bool(warheroes and matched and serial_match and alias and valid_year and bool(current_year)
                           and len(notes)>=10 and not contradiction
                           and not (supplied_serial and not any(supplied_serial==str(a['number']) for a in numbered)))
    return {'fio':fio,'year':year,'valid_year':valid_year,'year_reliable':bio.key(values.get('Год подтверждён','да'))=='да','source':source,'notes':notes,
            'sources':sources(source),'same_fio':same_fio,'verified':verified,'auto_verified':verified and warheroes,
            'problems':problems,'selected':selected,'serial_match':bool(serial_match),'manual_identity':manual_identity,
            'award_context':' · '.join(dict.fromkeys(f'{a["award"]} №{a["number"]}' for a in selected))}


def display_fio(value):
    value = bio.text(value)
    return value.title() if value and value==value.upper() else value or 'ФИО не указано'
