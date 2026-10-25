"""A small, server-owned choice model over the existing signed review pipeline."""
from contextlib import closing
import json
import hmac
import re
from urllib.parse import urlsplit

from . import biography_enrichment as bio, manual_import_review as manual
from .dates import format_birth_year_input


def _sources(raw):
    result = []
    for url in raw.splitlines():
        try:
            host = urlsplit(url).hostname or ''
        except ValueError:
            host = ''
        name = 'Герои страны' if host.removeprefix('www.') == 'warheroes.ru' else host
        result.append({'name': name or 'Источник в файле', 'url': url})
    return result


def detail(settings, token, row_number):
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        record, values, snapshot, original, row, current = manual._validated(connection, settings, token, row_number)
    proposals = {'biography': values.get('biography', ''), 'birthday': values.get('Год в карточке', ''),
                 'fio': values.get('ФИО в карточке', '')}
    source_fio = bio.key(proposals['fio'])
    same_fio = bool(source_fio) and source_fio == bio.key(current['fio'])
    source_award = bio.key(values.get('Награда в карточке'))
    notes = bio.text(values.get('notes'))
    awards = snapshot['person']['awards']
    selected = [a for a in awards if all(a[bio.IDS[i]] == v for i, v in enumerate(snapshot['selection']))]
    labour_first = [a for a in selected if 'трудов' in bio.key(a['award']) and 'слав' in bio.key(a['award'])
                    and re.search(r'\b(?:i|1)\b', bio.key(a['award']))]
    matched_awards = [a for a in labour_first or selected if source_award == bio.key(a['award'])]
    # A number in the evidence must refer to a matching award, not another award
    # belonging to the same person. No inference from an arbitrary year/number.
    serial_match = any(a['number'] not in (None, '', 0, '0') and re.search(
        r'(?:№|номер\s*)\s*'+re.escape(str(a['number']))+r'(?!\d)', notes, re.I) for a in matched_awards)
    identity_statement = bio.key(values.get('Идентификация'))
    alias_confirmed = identity_statement == 'личность подтверждена по награде и номеру' and serial_match
    award_conflict = bool(source_award) and not matched_awards
    explicitly_unresolved = bool(re.search(r'не подтвержд|не установ|не совпад|сомнен', identity_statement))
    ambiguous = award_conflict or explicitly_unresolved or bool(source_fio and not same_fio and not alias_confirmed)
    valid_source = manual._valid_source(values.get('source_url', ''))
    supported_identity = valid_source and not ambiguous and serial_match and (same_fio or alias_confirmed) and len(notes) >= 10
    fields = {}
    for name, label in manual.FIELDS.items():
        proposed = proposals[name]
        before = format_birth_year_input(current[name]) if name == 'birthday' else current[name] or ''
        uncertain_year = name == 'birthday' and before in ('', '1945')
        needed = (not bio.blank(proposed) and proposed != before) or uncertain_year
        if not needed:
            continue
        allowed = valid_source and not ambiguous and not bio.blank(proposed)
        if name in {'birthday', 'fio'}:
            allowed = allowed and supported_identity
        if name == 'biography':
            allowed = allowed and len(proposed) <= 2500
        reason = ('В файле другой год рождения.' if name == 'birthday' and proposed and proposed != before else
                  'Год 1945 нужно подтвердить: он мог быть подставлен при старом импорте.' if uncertain_year else
                  'В источнике другое написание ФИО.' if name == 'fio' else
                  'Биография в базе пуста.' if not before else 'В файле предложен другой текст биографии.')
        if ambiguous:
            recommendation = 'Личность не подтверждена. Оставьте текущее значение и уточните источник.'
        elif not allowed:
            recommendation = 'Пока оставьте текущее значение: подтверждения в источнике недостаточно.'
        elif name == 'birthday' and proposed == before:
            recommendation = f'Источник подтверждает {before}. Рекомендуем оставить этот год.'
        elif supported_identity:
            recommendation = 'Рекомендуем вариант источника: ФИО, награда и номер подтверждены в файле.'
        else:
            recommendation = 'Сравните текст с источником. При сомнениях оставьте текущее значение.'
        fields[name] = {'label': label, 'current': before, 'proposed': proposed, 'reason': reason,
                        'allowed': bool(allowed), 'recommendation': recommendation,
                        'recommended': 'proposed' if allowed and supported_identity and proposed != before else 'current',
                        'sources': _sources(values.get('source_url', ''))}
    return {'token': token, 'row_number': row_number, 'person_id': snapshot['person']['person_id'],
            'fio': current['fio'], 'award_context': ' · '.join(dict.fromkeys(
                f'{a["award"]} №{a["number"]}' for a in selected)), 'fields': fields,
            'ambiguous': ambiguous, 'identity_supported': supported_identity,
            'source': values.get('source_url', ''), 'notes': notes,
            'current': current, 'proposals': proposals,
            'revision': bio._sign(settings, bio.canonical({'kind':'review-choice-view', 'token':token,
                                                         'row':row_number, 'current':current}))}


def prepare(settings, token, row_number, submitted):
    review = detail(settings, token, row_number)
    if not hmac.compare_digest(str(submitted.get('review_revision', '')), review['revision']):
        raise bio.ValidationError('Карточка изменилась после проверки. Вернитесь к списку и откройте кавалера заново; ничего не записано.')
    selected = {n: submitted.get(n+'_choice', '') for n in review['fields']}
    if not any(selected.values()):
        raise bio.ValidationError('Выберите вариант хотя бы для одного поля или пропустите кавалера.')
    values = {'actor': 'Пользователь приложения', 'identity_confirm': 'yes'}
    for name in manual.FIELDS:
        choice = selected.get(name, '')
        if choice not in {'', 'current', 'proposed'}:
            raise bio.ValidationError('Неизвестный вариант. Откройте кавалера заново.')
        if choice == 'proposed' and not review['fields'][name]['allowed']:
            raise bio.ValidationError('Источник не подтверждает личность или значение. Оставьте текущее значение и уточните сведения.')
        values[name+'_decision'] = {'': 'pending', 'current': 'reject', 'proposed': 'accept'}[choice]
        values[name+'_proposal'] = review['proposals'][name]
        values[name+'_source'] = review['source']
        values[name+'_evidence'] = review['notes'] or 'Пользователь выбрал вариант источника и отдельно подтвердил его принадлежность этому кавалеру.'
    identity_pending = review['ambiguous'] or any(n in {'birthday', 'fio'} and not selected[n] for n in selected)
    if 'birthday' in selected and review['current']['birthday'] and format_birth_year_input(review['current']['birthday']) == '1945':
        identity_pending = identity_pending or not review['identity_supported']
    return manual.prepare(settings, token, row_number, values,
                          review_fields=list(review['fields']), identity_pending=bool(identity_pending),
                          expected_fields=review['current'])


def complete(event):
    names = event.get('review_fields', list(manual.FIELDS))
    return not event.get('identity_pending', False) and all(event['fields'][n]['decision'] != 'pending' for n in names)


def finished_rows(settings, file_sha256):
    latest = {}
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        if not connection.execute("select 1 from sqlite_master where type='table' and name='logs'").fetchone():
            return []
        for row in connection.execute('select comment from logs where action like ? and instr(comment,?)>0 order by rowid desc',
                                      (manual.AUDIT_PREFIX+'%', file_sha256)):
            try:
                event = json.loads(row['comment'])
                if event.get('file_sha256') == file_sha256:
                    latest.setdefault(event['row_number'], event)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
    return [number for number, event in latest.items() if 'review_fields' in event and complete(event)]


def friendly_error(exc):
    message = str(exc)
    if any(word in message for word in ('служебные данные', 'Подпись', 'подписи', 'План проверки повреждён')):
        return 'Не удалось проверить исходный файл. Скачайте новую выгрузку и перенесите только найденные сведения.'
    if 'устарели' in message or 'после проверки' in message:
        return 'Карточка изменилась после выгрузки или проверки. Обновите файл и выберите варианты заново; ничего не записано.'
    return message
