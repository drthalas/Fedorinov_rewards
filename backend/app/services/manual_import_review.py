"""Explicit field review; immutable TEMP plans and transactional legacy-log audit.

No schema creation, source workbook rewriting or relaxed import guards.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import hmac
import hashlib
import copy
import re
import secrets
import time
import unicodedata
from urllib.parse import urlsplit

from ..db import open_write_connection
from . import biography_enrichment as bio
from .dates import normalize_birth_year_input
from .dates import format_birth_year_input
from .write_guard import ensure_write_allowed

FIELDS = {'biography': 'Биография', 'birthday': 'Год рождения', 'fio': 'ФИО'}
DECISIONS = {'accept': 'Принять', 'reject': 'Отклонить', 'pending': 'Оставить на проверке'}
AUDIT_PREFIX = 'manual_import_review:'
_UNSET = object()


def _stored_year_equal(left, right):
    # SQLite DATE/NUMERIC columns store a submitted four-digit year as INTEGER.
    # This is deliberately narrower than date normalization: no full-date or
    # floating-point substitutions can pass this comparison.
    if type(left)==int and isinstance(right,str) and re.fullmatch(r'[0-9]{4}',right):
        return left==int(right)
    if type(right)==int and isinstance(left,str) and re.fullmatch(r'[0-9]{4}',left):
        return right==int(left)
    return type(left)==type(right) and left==right


def _same_state(left, right, allow_year_affinity=False):
    if not isinstance(left,dict) or not isinstance(right,dict) or left.keys()!=right.keys():
        return left==right
    return all(_stored_year_equal(left[n],right[n]) if n=='birthday' and allow_year_affinity else left[n]==right[n] for n in left)


def _receipt_signature(settings, event):
    return bio._sign(settings, 'enrichment-receipt-v1:' + bio.canonical(event))


def _source_digest(record, values):
    source = values if values.get('snapshot') else record['originals'].get(values.get('person_id'), {})
    return hashlib.sha256(source.get('snapshot', '').encode()).hexdigest()


def progress(connection, settings, record, values, snapshot, row_number):
    """Only our authenticated, contiguous receipts can advance a signed export.

    The original snapshot is never rewritten or re-signed. Every frozen identity
    attribute and all three expected live fields remain checked against SQLite.
    """
    pid = snapshot['person']['person_id']
    expected_identity = copy.deepcopy(snapshot['person'])
    baseline = record.get('initial_fields', {}).get(str(row_number))
    expected = dict(baseline) if baseline else None
    decisions = {}
    events = []
    if '_receipt_events' not in record:
        record['_receipt_events'] = []
        if connection.execute("select 1 from sqlite_master where type='table' and name='logs'").fetchone():
            for row in connection.execute('select comment from logs where action like ? and instr(comment,?)>0 order by rowid',
                                          (AUDIT_PREFIX+'%', record['file_sha256'])):
                try:
                    record['_receipt_events'].append(json.loads(row['comment']))
                except (ValueError, TypeError):
                    continue
    if record['_receipt_events']:
        for event in record['_receipt_events']:
            if not isinstance(event, dict) or event.get('person_id') != pid or event.get('file_sha256') != record['file_sha256']:
                continue
            signature = event.get('receipt_signature', '')
            unsigned = {k:v for k,v in event.items() if k != 'receipt_signature'}
            valid = isinstance(signature, str) and hmac.compare_digest(signature, _receipt_signature(settings, unsigned))
            # Existing feature receipts can be authenticated against their saved
            # immutable plan. An unverifiable old log never relaxes a guard.
            if not valid and not signature:
                try:
                    plan = bio.load_preview(settings, event['operation'])
                    signed = plan.pop('signature', '')
                    valid = hmac.compare_digest(signed, bio._sign(settings, bio.canonical(plan))) and all(
                        event.get(k) == plan.get(k) for k in ('identity','expected','fields','file_sha256','person_id','row_number'))
                except (bio.ValidationError, KeyError, TypeError):
                    valid = False
            if not valid:
                raise bio.ValidationError('Историю этой строки не удалось подтвердить. Нужна новая выгрузка.')
            if event.get('source_snapshot_digest', _source_digest(record, values)) != _source_digest(record, values):
                raise bio.ValidationError('История относится к другой выгрузке. Нужна новая проверка.')
            if not _same_state(event['identity'],expected_identity, bool(events)):
                raise bio.ValidationError('Последовательность изменений карточки нарушена. Нужна новая выгрузка.')
            if not events:
                # Re-uploading the identical workbook starts at the same receipt
                # chain, not at today's already-updated values.
                expected = dict(event['expected'])
            elif not _same_state(event['expected'],expected, True):
                raise bio.ValidationError('Поля изменялись вне этого импорта. Нужна новая выгрузка.')
            expected = {n:event['fields'][n]['after'] for n in FIELDS}
            expected_identity['fio'] = expected['fio']
            expected_identity['birthday'] = expected['birthday']
            for n in event.get('review_fields', FIELDS):
                if event['fields'][n]['decision'] != 'pending':
                    decisions[n] = event['fields'][n]['decision']
            events.append(event)
    return {'identity':expected_identity, 'expected':expected, 'decisions':decisions, 'events':events}


def _audit_available(connection):
    columns = {r['name'] for r in connection.execute('pragma table_info(logs)')}
    if not {'datetime', 'action', 'comment'} <= columns:
        raise bio.ValidationError('В этой базе нет совместимого журнала logs. Проверка остановлена: требуется решение владельца о миграции; схема не изменена.')


def _fields(connection, person_id):
    row = connection.execute('select biography,birthday,fio from person where id=?', (person_id,)).fetchone()
    if row is None:
        raise bio.ValidationError('Кавалер отсутствует. Загрузите свежую выгрузку.')
    return dict(row)


def _validated(connection, settings, token, row_number, *, record=None):
    record = bio.load_preview(settings, token) if record is None else record
    if record.get('state') == 'commit_pending':
        raise bio.ValidationError('Исход предыдущей записи не подтверждён. Загрузите файл для новой проверки текущей базы.')
    entries = [e for e in record['entries'] if e['row'] == row_number]
    if len(entries) != 1:
        raise bio.ValidationError('Строка не найдена. Загрузите файл заново.')
    entry = entries[0]
    values = entry['values']
    raw_id = values.get('person_id', '')
    if entry['invalid'] or not re.fullmatch(r'[1-9][0-9]{0,18}', raw_id) or int(raw_id) > 2**63-1:
        raise bio.ValidationError('Повреждённая строка или ID. Исправьте файл и загрузите заново.')
    person_id = int(raw_id)
    if person_id in record['duplicates']:
        raise bio.ValidationError('Повторяющийся ID: оставьте одну согласованную строку и загрузите файл заново.')
    snapshot = bio._snapshot(settings, values if values.get('snapshot') else record['originals'].get(raw_id, {}))
    if values.get('_format') == 'visible-7-v2' and (snapshot['version'] != 2 or snapshot.get('contract') != 'visible-7-v2'):
        raise bio.ValidationError('Подпись относится к другому формату. Нужна новая выгрузка.')
    own = progress(connection, settings, record, values, snapshot, row_number)
    live = bio._identity(connection, person_id)
    if not _same_state(own['identity'],live,bool(own['events'])):
        labels = {'person_id':'ID кавалера', 'fio':'ФИО', 'birthday':'Год рождения', 'id_rank':'Звание', 'rank':'Звание', 'awards':'Награды и номера'}
        changed = ', '.join(dict.fromkeys(labels[n] for n in own['identity'] if live is None or own['identity'][n] != live.get(n)))
        raise bio.ValidationError(f'ID {person_id}: исходные данные устарели; изменены поля: {changed}. Скачайте свежие данные и повторите проверку.')
    original = bio._original(snapshot)
    for name, expected in original.items():
        if bio.key(values.get(name)) != bio.key(expected):
            raise bio.ValidationError(f'Изменено исходное поле «{name}». Принять такую строку нельзя. Восстановите исходную выгрузку; предложения вводите в панели проверки.')
    _audit_available(connection)
    row = next(r for r in record['rows'] if r['row'] == row_number)
    current = _fields(connection, person_id)
    if own['expected'] is not None and not _same_state(current,own['expected'],bool(own['events'])):
        raise bio.ValidationError('Поля изменены после проверки вне этого импорта. Нужна новая выгрузка.')
    if own['events']:
        own['identity'] = live
        own['expected'] = current
    record['_progress'] = own
    return record, values, snapshot, original, row, current


def history(connection, person_id=None):
    events = []
    for row in connection.execute('select comment from logs where action like ? order by rowid desc', (AUDIT_PREFIX+'%',)):
        try:
            event = json.loads(row['comment'])
            if person_id is None or event.get('person_id') == person_id:
                events.append(event)
        except (ValueError, TypeError, AttributeError):
            continue
        if len(events) >= 20:
            break
    return events


def durable_history(settings, person_id=None):
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        _audit_available(connection)
        return history(connection, person_id)


def summaries(settings, file_sha256):
    """Present durable outcomes on a reloaded preview without reclassifying import."""
    result = {}
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        if not connection.execute("select 1 from sqlite_master where type='table' and name='logs'").fetchone():
            return result  # Ordinary imports remain compatible with minimal DBs.
        for row in connection.execute('select comment from logs where action like ? and instr(comment,?)>0 order by rowid desc',
                                      (AUDIT_PREFIX+'%', file_sha256)):
            event = json.loads(row['comment'])
            if event.get('file_sha256') == file_sha256 and event['row_number'] not in result:
                parts = [FIELDS[n]+': '+('сохранено' if n in event['writes'] else 'подтверждено без изменения')
                         if f['decision'] == 'accept' else FIELDS[n]+': '+{'reject':'Отклонено', 'pending':'Оставлено на проверке'}[f['decision']]
                         for n, f in event['fields'].items() if n in event.get('review_fields', FIELDS)]
                prefix = 'Ручная проверка · '
                if 'review_fields' in event:
                    unresolved = event['identity_pending'] or any(event['fields'][n]['decision'] == 'pending' for n in event['review_fields'])
                    prefix = 'Нужна дальнейшая проверка. ' if unresolved else 'Выбор сохранён. '
                result[event['row_number']] = prefix + ' · '.join(parts)
    return result


def reviewed_history(settings, token, row_number):
    """History remains readable after an approved rename makes the export stale."""
    record = bio.load_preview(settings, token)
    entry = next((e for e in record['entries'] if e['row'] == row_number), None)
    if entry is None:
        raise bio.ValidationError('Строка не найдена.')
    values = entry['values']
    snapshot = bio._snapshot(settings, values if values.get('snapshot') else record['originals'].get(values.get('person_id'), {}))
    if str(snapshot['person']['person_id']) != values.get('person_id'):
        raise bio.ValidationError('ID не соответствует подписи.')
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        _audit_available(connection)
        return history(connection, snapshot['person']['person_id'])


def review(settings, token, row_number):
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        record, values, snapshot, original, row, current = _validated(connection, settings, token, row_number)
        proposals = {'biography': values.get('biography', ''), 'fio': values.get('ФИО в карточке', ''),
                     'birthday': values.get('Год в карточке', '')}
        reasons = {
            'biography': row['reason'] + (' Существующий текст заменяется только отдельным принятием биографии.' if not bio.blank(current['biography']) else ''),
            'fio': 'ФИО источника отличается.' if proposals['fio'] and proposals['fio'] != current['fio'] else 'Отдельного предложения ФИО нет; псевдоним или отсутствие фамилии в источнике сами по себе не подтверждают переименование.',
            'birthday': (f'Год источника «{proposals["birthday"]}» отличается от года в базе «{bio._year(current["birthday"])}».'
                if proposals['birthday'] and proposals['birthday'] != bio._year(current['birthday']) else
                '1945 может быть настоящим годом или подстановкой старого импорта; требуется подтверждение источником.'
                if bio._year(current['birthday']) == '1945' else 'Отдельного предложения года нет; его можно ввести вручную после проверки источника.')}
        return {'token': token, 'row_number': row_number, 'person_id': snapshot['person']['person_id'],
                'identity': snapshot['person'], 'status': values.get('status', ''), 'reason': row['reason'],
                'current': current, 'proposals': proposals, 'reasons': reasons,
                'original': {'biography': '', 'fio': original['ФИО'], 'birthday': original['Год рождения']},
                'source': values.get('source_url', ''), 'history': history(connection, snapshot['person']['person_id'])}


def _valid_source(value):
    try:
        urls = value.splitlines()
        return bool(urls) and len(value) <= 4000 and all(urlsplit(u).scheme in {'https', 'http'} and urlsplit(u).hostname
            and not urlsplit(u).username and not urlsplit(u).password for u in urls)
    except ValueError:
        return False


def prepare(settings, token, row_number, submitted, *, review_fields=None, identity_pending=False, expected_fields=None, expected_receipt=_UNSET):
    # Preparing decisions is read-only for SQLite, including rejected/pending fields.
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        record, values, snapshot, original, row, current = _validated(connection, settings, token, row_number)
    if expected_fields is not None and current != expected_fields:
        raise bio.ValidationError('Карточка изменилась после проверки. Откройте кавалера заново; ничего не записано.')
    last = record['_progress']['events'][-1]['operation'] if record['_progress']['events'] else None
    if expected_receipt is not _UNSET and expected_receipt != last:
        raise bio.ValidationError('Решение уже изменилось. Обновите список перед сохранением.')
    actor = bio.text(submitted.get('actor'))
    if actor not in {'Owner', 'Сергей', 'Пользователь приложения'}:
        raise bio.ValidationError('Укажите, кто проверил сведения: Owner или Сергей.')
    fields = {}
    for name, label in FIELDS.items():
        decision = submitted.get(name+'_decision', 'pending')
        if decision not in DECISIONS:
            raise bio.ValidationError(f'{label}: неизвестное решение.')
        proposed = str(submitted.get(name+'_proposal', ''))
        source = bio.text(submitted.get(name+'_source'))
        evidence = bio.text(submitted.get(name+'_evidence'))
        limit = (2500 if name == 'biography' else 250) if decision == 'accept' else 32000
        if len(proposed) > limit or len(evidence) > 2500 or len(source) > 4000:
            raise bio.ValidationError(f'{label}: превышен лимит текста; данные не обрезаны.')
        if decision == 'accept':
            if not _valid_source(source) or len(evidence) < 10:
                raise bio.ValidationError(f'{label}: нужны полный http/https URL и конкретное подтверждение из источника (не менее 10 символов).')
            if name == 'biography' and bio.blank(proposed):
                raise bio.ValidationError('Биография: пустой текст нельзя принять.')
            if name == 'birthday':
                try:
                    proposed = normalize_birth_year_input(proposed, required=True)
                except ValueError as exc:
                    raise bio.ValidationError(str(exc)) from exc
            if name == 'fio':
                proposed = proposed.strip()
                if len(proposed) < 5 or len(proposed.split()) < 2 or not any(c.isalpha() for c in proposed) or any(
                        not (c.isalpha() or c in " '-’().") for c in proposed):
                    raise bio.ValidationError('ФИО: укажите полное имя, без цифр, ссылок и управляющих символов.')
            if name in {'birthday', 'fio'} and submitted.get('identity_confirm') != 'yes':
                raise bio.ValidationError('Для года/ФИО подтвердите личную проверку источника и точной награды с номером. Неподтверждённый вариант фамилии недостаточен.')
        if any(unicodedata.category(c) == 'Cc' and c not in '\n\r\t' for c in proposed+evidence):
            raise bio.ValidationError(f'{label}: управляющие символы недопустимы.')
        after = proposed if decision == 'accept' else current[name]
        if name == 'birthday' and decision == 'accept' and proposed == format_birth_year_input(current[name]):
            after = current[name]  # Confirming a year must not erase a legacy full date.
        fields[name] = {'before': current[name], 'proposed': proposed, 'decision': decision,
                        'after': after, 'source': source, 'evidence': evidence}
    plan_token = secrets.token_hex(32)
    plan = {'created': time.time(), 'state': 'manual_plan', 'token': token, 'row_number': row_number,
            'person_id': snapshot['person']['person_id'], 'identity': record['_progress']['identity'], 'expected': current,
            'expected_receipt':record['_progress']['events'][-1]['operation'] if record['_progress']['events'] else None,
            'actor': actor, 'fields': fields, 'file_sha256': record['file_sha256'],
            'source_snapshot_digest':_source_digest(record, values),
            'writes': [n for n, f in fields.items() if f['decision'] == 'accept' and f['before'] != f['after']]}
    if review_fields is not None:
        if any(n not in FIELDS for n in review_fields):
            raise bio.ValidationError('Неизвестное поле проверки.')
        plan.update(review_fields=review_fields, identity_pending=identity_pending)
    # A new immutable plan per submission prevents parallel tabs from changing what
    # the confirmation screen will commit. Integrity is rechecked at commit.
    plan['signature'] = bio._sign(settings, bio.canonical(plan))
    bio._save(settings, plan_token, plan)
    return plan_token, plan


def check_plan(connection, settings, plan, *, record=None):
    record, _, _, _, _, current = _validated(connection, settings, plan['token'], plan['row_number'], record=record)
    if record['file_sha256'] != plan['file_sha256']:
        raise bio.ValidationError('План относится к другому файлу.')
    if current != plan['expected'] or record['_progress']['identity'] != plan['identity']:
        raise bio.ValidationError('Карточка изменилась после проверки. Ничего не записано; обновите данные.')
    last = record['_progress']['events'][-1]['operation'] if record['_progress']['events'] else None
    if last != plan.get('expected_receipt'):
        raise bio.ValidationError('Решение по кавалеру уже изменилось. Обновите список; ничего не записано.')
    return record


def apply_plan(connection, settings, plan, operation, *, record=None):
    """Apply one already-confirmed plan inside the caller's transaction."""
    record = check_plan(connection, settings, plan, record=record)
    changed = {n:f['after'] for n,f in plan['fields'].items() if f['decision'] == 'accept' and f['before'] != f['after']}
    if changed:
        names = [n for n in FIELDS if n in changed]
        cursor = connection.execute('update person set '+','.join(n+'=?' for n in names)+' where id=?',
                                    [changed[n] for n in names]+[plan['person_id']])
        if cursor.rowcount != 1:
            raise bio.ValidationError('База отклонила запись. Все изменения отменены.')
    after = {n:f['after'] for n,f in plan['fields'].items()}
    stored = _fields(connection, plan['person_id'])
    if not _same_state(stored,after,True):
        raise bio.ValidationError('База не сохранила выбранные значения. Все изменения отменены.')
    accepted_fields = copy.deepcopy(plan['fields'])
    for name in FIELDS:
        accepted_fields[name]['after'] = stored[name]
    event = {**plan, 'state':'manual_committed', 'time':datetime.now(timezone.utc).isoformat(),
             'operation':operation, 'writes':list(changed),'fields':accepted_fields}
    event['receipt_signature'] = _receipt_signature(settings, event)
    connection.execute('insert into logs(datetime,action,comment) values(?,?,?)',
                       (event['time'], AUDIT_PREFIX+operation, bio.canonical(event)))
    record.setdefault('_receipt_events',[]).append(event)
    return event


def commit(settings, plan_token):
    ensure_write_allowed(settings)
    plan = bio.load_preview(settings, plan_token)
    signature = plan.pop('signature', '')
    if plan.get('state') != 'manual_plan' or not hmac.compare_digest(signature, bio._sign(settings, bio.canonical(plan))):
        raise bio.ValidationError('План проверки повреждён. Повторите проверку строки.')
    action = AUDIT_PREFIX+plan_token
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        connection.execute('begin immediate')
        try:
            _audit_available(connection)
            previous = connection.execute('select comment from logs where action=?', (action,)).fetchone()
            if previous:
                return json.loads(previous['comment'])
            event = apply_plan(connection, settings, plan, plan_token)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return event
