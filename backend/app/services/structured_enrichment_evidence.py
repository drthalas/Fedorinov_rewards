"""Versioned research assertions, selected by the authenticated award scope."""
from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import re

from . import biography_enrichment as bio

GLORY_A = 'A_SLAVA_I_EXACT_SERIAL'
GLORY_B = 'B_SLAVA_I_FULL_FIO_CONTEXT'
HSU_A = 'A_HSU_EXACT_GOLD_STAR_SET'
GSS_NAMES = {'герой советского союза', 'герой советского союза ii', 'герой советского союза iii'}
GLORY_NAMES = {'орден славы 1 степени', 'орден славы i степени'}
GLORY_CLAUSE = r'орден[а-яё]*\s+славы\s+(?:1|i)(?![i\d])[-–]?(?:й|я|ой)?\s+степен[а-яё]*'


def selected_awards(snapshot):
    return [award for award in snapshot['person']['awards']
            if all(award[field] == value for field, value in zip(bio.IDS, snapshot['selection']))]


def category(awards):
    names = {bio.key(award['award']) for award in awards}
    if names and names <= GSS_NAMES:
        return 'hsu'
    if names and names <= GLORY_NAMES:
        return 'glory-i'
    return 'unsupported'


@dataclass(frozen=True)
class Evidence:
    category: str
    version: int | None
    path: str = ''
    code: str = 'verified'
    reason: str = ''

    @property
    def valid(self):
        return self.code == 'verified'

    @property
    def serial_confirmed(self):
        return self.valid and self.path in {GLORY_A, HSU_A}


class InvalidEvidence(ValueError):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code = code


def require(condition, code, reason):
    if not condition:
        raise InvalidEvidence(code, reason)


def _positive_serial(value):
    serial = bio.text(value)
    return serial if re.fullmatch(r'[1-9][0-9]*', serial) else ''


def _name_context(original, source):
    names = [bio.key(re.sub(r'\([^)]*\)', '', name)).split() for name in (original, source)]
    left, right = names
    if min(len(left), len(right)) < 2:
        return False
    return (set(left) <= set(right) or set(right) <= set(left)
            or (SequenceMatcher(None, left[0], right[0], autojunk=False).ratio() >= .82
                and SequenceMatcher(None, left[1], right[1], autojunk=False).ratio() >= .85))


def _glory_link(link, headers):
    serial = _positive_serial(link['serial'])
    if bio.key(link['award']) not in GLORY_NAMES or type(link['degree']) is not int or link['degree'] != 1 or not serial:
        return False
    if type(link.get('paragraph')) is not int or link['paragraph'] <= 0:
        return False
    if link['method'] == 'explicit Glory I serial in typed award clause':
        return bool(re.search(GLORY_CLAUSE + r'[ \t(–—-]{0,12}№\s*' + serial + r'(?!\d)',
                              link.get('quote', ''), re.I))
    if link['method'] == 'order header matched by exact date to typed Glory I decree':
        date = link['date']
        if not re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', date):
            return False
        numbers = {_positive_serial(h.get('serial')) for h in headers
                   if h.get('date') == date and bio.key(h.get('label')) == 'орден' and h.get('serial')}
        return numbers == {serial}
    return False


def _glory(snapshot, values, notes, proof, awards, path):
    person = snapshot['person']
    original = proof['input_rechecked']
    signed = {_positive_serial(a['number']) for a in awards}
    scope = proof['award_proofs']
    require(len(scope) == 1, 'award_linkage', 'В доказательствах нужна одна выбранная награда I степени.')
    scope = scope[0]
    require(bio.key(original['award']) in GLORY_NAMES and bio.key(scope['selected_award']) in GLORY_NAMES
            and bio.key(values.get('Награда в карточке')) in GLORY_NAMES
            and bio.key(original['fio']) == bio.key(person['fio'])
            and bio.text(original['year']) == bio._year(person['birthday'])
            and {_positive_serial(n) for n in original['serials']} == signed
            and {_positive_serial(n) for n in scope['selected_serials']} == signed,
            'award_linkage', 'Исходные ФИО, год, награда I степени или её номера расходятся с подписанной выгрузкой.')
    year = bio.text(proof['source_year'])
    reliable = proof['source_year_reliable']
    require(type(reliable) is bool and reliable is notes['birth_year_reliable']
            and year == bio.text(values.get('Год в карточке'))
            and reliable == (bio.key(values.get('Год подтверждён')) == 'да'),
            'year_evidence', 'Предложение года расходится с доказательствами источника.')

    for other in proof['candidate_assessments']:
        require(isinstance(other, dict) and bool(other.get('source_fio')) and bool(other.get('source_url')),
                'ambiguous_identity', 'Недостаточно сведений об альтернативной карточке.')
        if other['source_url'] == proof['source_url']:
            continue
        exact = any(bio.key(link.get('award')) in GLORY_NAMES and _positive_serial(link.get('serial')) in signed - {''}
                    for link in other.get('public_award_links', []))
        same_name_year = (bio.key(other['source_fio']) == bio.key(person['fio'])
                          and bio.text(other.get('source_year')) == bio._year(person['birthday']))
        require(not (exact or same_name_year), 'ambiguous_identity',
                'Альтернативная карточка с тем же номером или ФИО и годом требует сверки.')

    links = proof['source_selected_award_links']
    public = proof['public_award_links']
    confirmed = notes['confirmed_Glory_I']
    require(public == scope['public_links'], 'award_linkage', 'Связи награды в источнике расходятся между доказательствами.')
    supplied = {_positive_serial(value) for value in bio.text(values.get('Номер в карточке')).split('|')}
    if path == GLORY_A:
        require(bool(signed) and '' not in signed and bool(links)
                and {_positive_serial(link['serial']) for link in links} == signed == supplied
                and all(link in public for link in links)
                and {_positive_serial(link['serial']) for link in public} == signed
                and all(_glory_link(link, proof['all_source_headers']) for link in public),
                'serial_evidence', 'Номер именно ордена Славы I степени не подтверждён связью с источником.')
        fields = ('award', 'serial', 'degree', 'date', 'method')
        require([{k: link[k] for k in fields} for link in links] == confirmed,
                'serial_evidence', 'Сводка номеров I степени расходится с полными доказательствами.')
        require(_name_context(person['fio'], proof['source_fio']), 'name_context',
                'Точный номер найден, но расхождение ФИО требует сверки.')
    else:
        require(not (links or public or confirmed or bio.text(values.get('Номер в карточке'))),
                'serial_evidence', 'Контекстный путь B требует отдельной проверки, если заявлен номер I степени.')
        actual_other = {(bio.key(a['award']), _positive_serial(a['number']))
                        for a in person['awards'] if bio.key(a['award']) in {
                            'орден славы 2 степени', 'орден славы 3 степени',
                            'орден славы ii степени', 'орден славы iii степени'}}
        checked_other = {(bio.key(a['award']), _positive_serial(a['serial']))
                         for a in scope['other_typed_awards']}
        rank = bio.key(person['rank'])
        independent_awards = {(name, serial) for name, serial in actual_other & checked_other if serial}
        corroborated = (scope['rank_match'] is True and rank not in {'', 'гражданский', 'неизвестно'}
                        or len(independent_awards) >= 2)
        require(bio.key(proof['source_fio']) == bio.key(person['fio'])
                and reliable and year == bio._year(person['birthday']) and year not in {'', '1945'}
                and corroborated, 'name_context',
                'Без номера I степени требуются полное совпадение ФИО, достоверный год и независимый контекст.')


def validate(snapshot, values, hsu_validator):
    """Legacy unversioned BIO7/HSU envelopes are recognized as their own v1."""
    try:
        notes = json.loads(values.get('notes', ''))
    except (TypeError, ValueError, RecursionError):
        notes = None
    attached = values.get('_full_evidence')
    if attached is None and not (isinstance(notes, dict) and 'full_evidence_sheet' in notes):
        return None
    awards = selected_awards(snapshot)
    kind = category(awards)
    version = None
    path = ''
    try:
        require(kind != 'unsupported', 'unsupported_category', 'Категория подписанной награды не поддерживает эту схему доказательств.')
        require(isinstance(notes, dict) and notes.get('full_evidence_sheet') == 'Полные доказательства',
                'evidence_envelope', 'Ссылка на полные доказательства отсутствует или повреждена.')
        require(isinstance(attached, dict), 'evidence_envelope', 'Строка полных доказательств отсутствует.')
        raw = attached['json']
        proof = json.loads(raw)
        require(isinstance(proof, dict), 'evidence_envelope', 'Неверная структура полных доказательств.')
        declared_version = notes.get('evidence_version', 1)
        version = declared_version if type(declared_version) is int else None
        require(type(version) is int and version == 1 and type(proof.get('evidence_version', 1)) is int
                and proof.get('evidence_version', 1) == version
                and ('evidence_version' in notes) == ('evidence_version' in proof),
                'unsupported_version', 'Версия полных доказательств неизвестна или расходится между листами.')
        require(all(item.get('evidence_category', kind) == kind for item in (notes, proof)),
                'unsupported_category', 'Категория доказательств расходится с подписанной наградой.')
        require(str(notes['full_evidence_ID']) == str(snapshot['person']['person_id'])
                and hashlib.sha256(raw.encode()).hexdigest() == notes['full_evidence_SHA256'],
                'evidence_digest', 'ID или SHA-256 полных доказательств не совпадает.')
        declared_path = proof.get('identity_path') or ''
        require(isinstance(declared_path, str), 'unsupported_version', 'Неизвестная схема проверки личности.')
        path = declared_path
        require(notes.get('identity_path', '') == path and notes['research_state'] == proof['state'],
                'evidence_envelope', 'Путь проверки личности расходится между листами.')
        require(attached['source'] == values['source_url'] == proof['source_url']
                and proof['source_fio'] == values.get('ФИО в карточке'),
                'source_mismatch', 'Источник или ФИО расходится между листами.')
        paths = {HSU_A} if kind == 'hsu' else {GLORY_A, GLORY_B}
        require(not path or path in paths, 'unsupported_version',
                'Схема проверки личности не поддерживается для подписанной категории.')
        require(proof['state'] == 'confirmed', 'research_review', 'В исследовании личность оставлена на проверке.')
        require(path in paths,
                'unsupported_version', 'Схема проверки личности не поддерживается для подписанной категории.')
        require(re.fullmatch(r'[a-f0-9]{64}', proof['profile_sha256'])
                and proof['profile_sha256'] == notes['source_HTML_SHA256'],
                'source_digest', 'SHA-256 карточки источника расходится между листами.')
        require(not re.search(r'личность не подтвержд|другой человек|неразреш[её]н|несколько кандидатов',
                              bio.key(proof.get('source_caveats', ''))),
                'ambiguous_identity', 'В доказательствах есть неразрешённое противоречие личности.')
        if kind == 'hsu':
            ok, reason = hsu_validator(snapshot, values, awards)
            require(ok, 'hsu_evidence', reason)
        else:
            _glory(snapshot, values, notes, proof, awards, path)
        return Evidence(kind, version, path)
    except InvalidEvidence as exc:
        return Evidence(kind, version, path, exc.code, str(exc))
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, IndexError):
        return Evidence(kind, version, path, 'evidence_envelope', 'Повреждена структура полных доказательств.')
