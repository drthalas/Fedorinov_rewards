"""Explicit field review; immutable TEMP plans and transactional legacy-log audit.

No schema creation, source workbook rewriting or relaxed import guards.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
import hmac
import re
import secrets
import time
import unicodedata
from urllib.parse import urlsplit

from ..db import open_write_connection
from . import biography_enrichment as bio
from .dates import normalize_birth_year_input
from .write_guard import ensure_write_allowed

FIELDS = {'biography': 'Биография', 'birthday': 'Год рождения', 'fio': 'ФИО'}
DECISIONS = {'accept': 'Принять', 'reject': 'Отклонить', 'pending': 'Оставить на проверке'}
AUDIT_PREFIX = 'manual_import_review:'


def _audit_available(connection):
    columns = {r['name'] for r in connection.execute('pragma table_info(logs)')}
    if not {'datetime', 'action', 'comment'} <= columns:
        raise bio.ValidationError('В этой базе нет совместимого журнала logs. Проверка остановлена: требуется решение владельца о миграции; схема не изменена.')


def _fields(connection, person_id):
    row = connection.execute('select biography,birthday,fio from person where id=?', (person_id,)).fetchone()
    if row is None:
        raise bio.ValidationError('Кавалер отсутствует. Загрузите свежую выгрузку.')
    return dict(row)


def _validated(connection, settings, token, row_number):
    record = bio.load_preview(settings, token)
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
    live = bio._identity(connection, person_id)
    if snapshot['person'] != live:
        labels = {'person_id':'ID кавалера', 'fio':'ФИО', 'birthday':'Год рождения', 'id_rank':'Звание', 'rank':'Звание', 'awards':'Награды и номера'}
        changed = ', '.join(dict.fromkeys(labels[n] for n in snapshot['person'] if live is None or snapshot['person'][n] != live.get(n)))
        raise bio.ValidationError(f'ID {person_id}: исходные данные устарели; изменены поля: {changed}. Скачайте свежие данные и повторите проверку.')
    original = bio._original(snapshot)
    for name, expected in original.items():
        if bio.key(values.get(name)) != bio.key(expected):
            raise bio.ValidationError(f'Изменено исходное поле «{name}». Принять такую строку нельзя. Восстановите исходную выгрузку; предложения вводите в панели проверки.')
    _audit_available(connection)
    row = next(r for r in record['rows'] if r['row'] == row_number)
    return record, values, snapshot, original, row, _fields(connection, person_id)


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
                         for n, f in event['fields'].items()]
                result[event['row_number']] = 'Ручная проверка · '+ ' · '.join(parts)
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


def prepare(settings, token, row_number, submitted):
    # Preparing decisions is read-only for SQLite, including rejected/pending fields.
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        record, values, snapshot, original, row, current = _validated(connection, settings, token, row_number)
    actor = bio.text(submitted.get('actor'))
    if actor not in {'Owner', 'Сергей'}:
        raise bio.ValidationError('Укажите, кто проверил сведения: Owner или Сергей.')
    fields = {}
    for name, label in FIELDS.items():
        decision = submitted.get(name+'_decision', 'pending')
        if decision not in DECISIONS:
            raise bio.ValidationError(f'{label}: неизвестное решение.')
        proposed = str(submitted.get(name+'_proposal', ''))
        source = bio.text(submitted.get(name+'_source'))
        evidence = bio.text(submitted.get(name+'_evidence'))
        if len(proposed) > (2500 if name == 'biography' else 250) or len(evidence) > 2500 or len(source) > 4000:
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
        fields[name] = {'before': current[name], 'proposed': proposed, 'decision': decision,
                        'after': proposed if decision == 'accept' else current[name], 'source': source, 'evidence': evidence}
    plan_token = secrets.token_hex(32)
    plan = {'created': time.time(), 'state': 'manual_plan', 'token': token, 'row_number': row_number,
            'person_id': snapshot['person']['person_id'], 'identity': snapshot['person'], 'expected': current,
            'actor': actor, 'fields': fields, 'file_sha256': record['file_sha256'],
            'writes': [n for n, f in fields.items() if f['decision'] == 'accept' and f['before'] != f['after']]}
    # A new immutable plan per submission prevents parallel tabs from changing what
    # the confirmation screen will commit. Integrity is rechecked at commit.
    plan['signature'] = bio._sign(settings, bio.canonical(plan))
    bio._save(settings, plan_token, plan)
    return plan_token, plan


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
            _, _, snapshot, _, _, current = _validated(connection, settings, plan['token'], plan['row_number'])
            if current != plan['expected'] or snapshot['person'] != plan['identity']:
                changed_fields = ', '.join(FIELDS[n] for n in FIELDS if current[n] != plan['expected'][n])
                raise bio.ValidationError(f'ID {plan["person_id"]}: поля изменены после проверки: {changed_fields}. Ничего не сохранено; обновите данные и проверьте строку заново.')
            changed = {n: f['after'] for n, f in plan['fields'].items() if f['decision'] == 'accept' and f['before'] != f['after']}
            if changed:
                # Column names are a fixed server allowlist, never request keys.
                names = [n for n in FIELDS if n in changed]
                cursor = connection.execute('update person set '+','.join(n+'=?' for n in names)+' where id=?',
                                            [changed[n] for n in names]+[plan['person_id']])
                if cursor.rowcount != 1:
                    raise bio.ValidationError('Запись отклонена. Все изменения отменены.')
            event = {**plan, 'state': 'manual_committed', 'time': datetime.now(timezone.utc).isoformat(),
                     'operation': plan_token, 'writes': list(changed)}
            connection.execute('insert into logs(datetime,action,comment) values(?,?,?)', (event['time'], action, bio.canonical(event)))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return event
