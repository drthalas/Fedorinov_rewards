"""Source assertions are separate from, and never modify, signed originals."""
import re
import json
import hashlib
import unicodedata
from urllib.parse import urlsplit, parse_qs

from . import biography_enrichment as bio
from . import structured_enrichment_evidence as contract
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
    if values.get('_full_evidence') or values.get('ФИО в карточке') or values.get('Награда в карточке'):return values
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

def source_name(value, current=''):
    """person stores one fio string: preserve compound names and Unicode as-is.

    Do not guess component boundaries or silently erase a known patronymic.
    Parenthesized surname variants are retained, never flattened into tokens.
    """
    value = bio.text(value)
    if not 5 <= len(value) <= 250 or any(not (c.isalpha() or unicodedata.category(c).startswith('M') or c in " '-’()") for c in value):
        return False
    if value.count('(') != value.count(')') or value.count('(') > 1 or '(' in value and value.index(')') < value.index('('):
        return False
    words = re.sub(r'\([^)]*\)', '', value).split()
    old_words = re.sub(r'\([^)]*\)', '', bio.text(current)).split()
    return len(words) >= max(2, len(old_words)) and all(sum(c.isalpha() for c in w) >= 2 for w in words)


def _hsu_evidence(snapshot, values, relevant):
    """HSU3489 v1: exact selected Gold Star set, ordinal, ID/source/digest.

    Hashes establish internal consistency only, not a trusted research signer.
    No inference from an arbitrary medal number or a name's edit distance.
    """
    try:
        notes = json.loads(values.get('notes', ''))
    except (ValueError, TypeError, RecursionError):
        return False, None
    if not isinstance(notes, dict) or notes.get('full_evidence_sheet') != 'Полные доказательства':
        return False, None
    problem = 'Нет согласованных полных доказательств личности, выбранной награды и её номера.'
    try:
        attached = values['_full_evidence'];raw = attached['json'];proof = json.loads(raw)
        if not isinstance(proof, dict):return False, problem
        pid = str(snapshot['person']['person_id'])
        if str(notes.get('full_evidence_ID')) != pid or hashlib.sha256(raw.encode()).hexdigest() != notes.get('full_evidence_SHA256'):
            return False, problem
        if attached['source'] != values['source_url'] or proof.get('source_url') != values['source_url'] or proof.get('source_fio') != values.get('ФИО в карточке'):
            return False, problem
        if proof.get('state') != 'confirmed' or notes.get('research_state') != 'confirmed' or proof.get('identity_path') != 'A_HSU_EXACT_GOLD_STAR_SET' or notes.get('identity_path') != proof['identity_path']:
            return False, problem
        if proof.get('profile_sha256') != notes.get('source_HTML_SHA256') or not re.fullmatch('[0-9a-f]{64}', proof.get('profile_sha256', '')):
            return False, problem
        if re.search(r'личность не подтвержд|другой человек|неразреш[её]н|несколько кандидатов', bio.key(proof.get('source_caveats', ''))):
            return False, 'В доказательствах есть неразрешённое противоречие личности.'
        original = proof['input_rechecked']
        if bio.key(original['fio']) != bio.key(snapshot['person']['fio']):return False, problem
        selected = {(bio.key(a['award']), str(a['number'])) for a in relevant}
        if not selected or any(a[0] not in {'герой советского союза', 'герой советского союза ii', 'герой советского союза iii'} or a[1] in {'', 'None', '0'} for a in selected):
            return False, problem
        if set(map(str, original['serials'])) != {a[1] for a in selected} or bio.key(original['award']) not in {a[0] for a in selected}:
            return False, problem
        for candidate in proof.get('candidate_assessments', []):
            # A documented other award/serial resolves a rejected candidate.
            # An unexamined candidate or another exact match stays unresolved.
            other = {(bio.key(a['award']), str(a['serial'])) for a in candidate.get('public_award_links', [])}
            ruled_out = candidate.get('gss_title') is False or bool(other) and not (other & selected)
            if not ruled_out:
                return False, 'Несколько неразрешённых кандидатов: требуется проверка личности.'
        links = proof['source_selected_award_links']
        if not links or {(bio.key(a['award']), str(a['serial'])) for a in links} != selected:return False, problem
        for link in links:
            ordinal = {'герой советского союза':1, 'герой советского союза ii':2, 'герой советского союза iii':3}[bio.key(link['award'])]
            if type(link.get('ordinal')) is not int or link['ordinal'] != ordinal or not link.get('method'):
                return False, problem
        if {(str(a['serial']), a['ordinal']) for a in notes['confirmed_GoldStars']} != {(str(a['serial']), a['ordinal']) for a in links}:
            return False, problem
        return True, None
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        return False, problem


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
    typed = contract.validate(snapshot, values, _hsu_evidence)
    structured = bool(typed and typed.valid)
    structured_problem = typed.reason if typed else None
    if structured_problem:
        problems.append(structured_problem)
    # Explicit same-person assertion is required for a differing source name.
    # A generic 'ФИО совпали' and a serial alone cannot authorize a rename.
    explicit = bool(re.search(r'личность подтверждена|тот же кавалер|идентичность подтверждена', statement))
    ambiguous = bool(re.search(r'несколько кандидатов|неразреш[её]н|неоднознач|другой кандидат', bio.key(notes+' '+statement)))
    name_complete = source_name(fio, current['fio'])
    if (structured or explicit) and fio and not name_complete:
        problems.append('ФИО источника неполно или неоднозначно; известные части имени не будут удалены.')
    source_identity = bool(warheroes and matched and serial_match and not negative and not material and not ambiguous
                           and len(notes)>=10 and (structured or explicit and not structured_problem)
                           and name_complete)
    if source_identity:
        problems = [p for p in problems if not p.startswith(('ФИО в источнике', 'Для надёжной сверки'))]
    if (variant_verified or same_fio and serial_match) and not material:
        problems=[p for p in problems if not p.startswith('ФИО в источнике')]
    problems.sort(key=lambda p: p.startswith('ФИО в источнике'))
    verified = bool(valid_source and not problems and not material and (same_fio or variant_verified or source_identity) and matched and len(notes)>=10 and (serial_match or corroborated))
    if typed and typed.category == 'glory-i':
        # The typed links are the sole serial evidence. In B the signed number
        # is an input identifier, even though it appears in the JSON notes.
        serial_match = typed.serial_confirmed
        identity_denied = bool(re.search(r'личность не подтвержд|фио не совпад|тот же кавалер не подтвержд',
                                         statement))
        verified = bool(typed.valid and warheroes and not identity_denied and not material
                        and not ambiguous and name_complete)
        source_identity = verified and serial_match
        if verified:
            problems = []
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
            'sources':sources(source),'same_fio':same_fio,'source_fio_verified':source_identity and verified,'verified':verified,'auto_verified':verified and warheroes,
            'problems':problems,'selected':selected,'serial_match':bool(serial_match),'manual_identity':manual_identity if typed is None else False,
            'evidence':typed,
            'award_context':' · '.join(dict.fromkeys(f'{a["award"]} №{a["number"]}' for a in selected))}


def display_fio(value):
    value = bio.text(value)
    return value.title() if value and value==value.upper() else value or 'ФИО не указано'
