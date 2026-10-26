"""Explicit, atomic file import plus resumable field review. No migrations."""
from contextlib import closing
from datetime import datetime
import hmac
import json
import secrets
import time

from ..db import open_write_connection
from . import biography_enrichment as bio, manual_import_review as manual, manual_review_choices as choices
from . import enrichment_evidence as evidence
from .dates import format_birth_year_input
from .write_guard import ensure_write_allowed

BATCH_PREFIX = 'enrichment_import:'


def stage(settings, token, row_number, submitted):
    raise bio.ValidationError('Ручные решения удалены. Доступен только общий импорт проверенных данных.')


def workspace(settings, token, operations=()):
    if operations:raise bio.ValidationError('План относится к прежнему ручному интерфейсу. Загрузите файл заново.')
    view=present(settings,token)
    buckets={'ready':[],'insufficient':[]};unchanged=[]
    totals={n:0 for n in manual.FIELDS}
    for row in view['rows']:
        if row['state']=='confirmed':continue
        if row['state']=='unchanged':unchanged.append(row);continue
        bucket='ready' if row['automatic'] else 'insufficient'
        row.update(bucket=bucket,staged=None)
        for name in row['automatic']:totals[name]+=1
        buckets[bucket].append(row)
    view.update(buckets=buckets,counts={k:len(v) for k,v in buckets.items()},unchanged=unchanged,
        totals=totals,accepted=0,eligible=len(buckets['ready']),operations=[],
        fatal=any(r['review'] is None for r in view['rows']),
        revision=bio._sign(settings,bio.canonical({'kind':'workspace-v5','base':view['revision']})))
    return view


def prepare_workspace(settings, token, revision, operations):
    view=workspace(settings,token,operations)
    if view['fatal'] or not hmac.compare_digest(str(revision),view['revision']):
        raise bio.ValidationError('Файл или карточки изменились. Получите свежую выгрузку; ничего не записано.')
    plans=[]
    for row in view['buckets']['ready']:
        _,plan=choices.row_plan(settings,token,row['row'],{n:'accept' for n in row['automatic']},expected=row['review']['current'],mode='import')
        plans.append(plan)
    if not plans:raise bio.ValidationError('Новых подтверждённых изменений нет. Повторная запись не требуется.')
    return _store_batch(settings,token,view['filename'],plans,
        {'fields':view['totals'],'ready':len(plans),'accepted':0,'skipped':len(view['rows'])-len(plans),'people':len(plans)})


def present(settings, token):
    record = bio.load_preview(settings,token)
    rows = []
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        for original in record['rows']:
            row = dict(original)
            try:
                review = choices.detail(settings,token,row['row'],connection=connection,record=record)
                row.update(review=review, fio=review['fio'],state=review['state'],status=review['status'],reason=review['reason'])
            except bio.ValidationError as exc:
                row.update(review=None,state='blocked',status='Нужна новая проверка',reason=choices.friendly_error(exc))
            row['fio'] = evidence.display_fio(row['fio'])
            row['automatic'] = row['review']['automatic'] if row['review'] else {}
            row['changes'] = [{'name':n,'label':manual.FIELDS[n], 'before':row['review']['current'][n], 'after':v}
                              for n,v in row['automatic'].items()]
            row['can_review'] = bool(row['review'] and row['state'] not in {'confirmed','unchanged'})
            row['action'] = ('Продолжить проверку' if row['review'] and row['review']['events'] else
                             'Объяснение' if row['state']=='blocked' else 'Проверить')
            rows.append(row)
    ready = [r for r in rows if r['automatic']]
    revision = bio._sign(settings,bio.canonical({'kind':'file-import-view','token':token,
        'rows':[(r['row'],r['review']['revision'] if r['review'] else r['reason']) for r in rows]}))
    return {'token':token,'created':record['created'],'file_sha256':record['file_sha256'],
            'filename':record.get('filename','Загруженный файл'),'rows':rows,'ready':len(ready),
            'change_count':sum(len(r['automatic']) for r in ready),
            'confirmed':sum(r['state']=='confirmed' for r in rows),
            'pending':sum(r['state'] in {'manual','blocked'} for r in rows),'revision':revision}


def prepare_import(settings, token, revision, exclude=()):
    view = present(settings,token)
    if not hmac.compare_digest(str(revision),view['revision']):
        raise bio.ValidationError('Данные изменились после проверки. Обновите список перед импортом.')
    plans = []
    excluded = {str(n) for n in exclude}
    for row in view['rows']:
        if not row['automatic'] or str(row['row']) in excluded:
            continue
        _, plan = choices.row_plan(settings,token,row['row'],{n:'accept' for n in row['automatic']},
                                   expected=row['review']['current'],mode='import')
        plans.append(plan)
    if not plans:
        raise bio.ValidationError('Готовых изменений нет. Повторная запись не требуется.')
    return _store_batch(settings,token,view['filename'],plans)


def _store_batch(settings, token, filename, plans, summary=None):
    operation = secrets.token_hex(32)
    plan = {'created':time.time(),'state':'file_import_plan','token':token,'rows':plans,'filename':filename}
    if summary is not None:plan['summary']=summary
    plan['signature'] = bio._sign(settings,bio.canonical(plan))
    bio._save(settings,operation,plan)
    return operation,plan


def commit_ordinary(settings, token):
    """Old confirmation endpoint keeps its BIO-only, previously-ready subset.

    It cannot silently approve new automatic year changes from an old UI. The
    same transactional receipts keep subsequent UI refreshes truthful.
    """
    ensure_write_allowed(settings)
    record = bio.load_preview(settings,token)
    eligible = {r['row'] for r in record['rows'] if r['kind']==bio.READY}
    plans = []
    for row in present(settings,token)['rows']:
        if row['row'] not in eligible or row['state']=='confirmed':
            continue
        if not row['review'] or 'biography' not in row['automatic']:
            raise bio.ValidationError('Готовая строка изменилась. Обновите список перед импортом.')
        _,plan = choices.row_plan(settings,token,row['row'],{'biography':'accept'},expected=row['review']['current'],mode='import')
        plans.append(plan)
    if plans:
        operation,_ = _store_batch(settings,token,record.get('filename','Загруженный файл'),plans)
        commit_import(settings,operation)
    return record


def commit_import(settings, operation):
    from .data_operation_lock import exclusive
    with exclusive(settings):return _commit_import(settings,operation)


def _commit_import(settings, operation):
    ensure_write_allowed(settings)
    plan = bio.load_preview(settings,operation)
    signature = plan.pop('signature','')
    if plan.get('state')!='file_import_plan' or not hmac.compare_digest(signature,bio._sign(settings,bio.canonical(plan))):
        raise bio.ValidationError('Подтверждение импорта повреждено. Откройте список заново.')
    with closing(open_write_connection(settings.rewards_db_path,settings.write_mode)) as connection:
        connection.execute('begin immediate')
        try:
            manual._audit_available(connection)
            old = connection.execute('select comment from logs where action=?',(BATCH_PREFIX+operation,)).fetchone()
            if old:
                return json.loads(old['comment'])
            record = bio.load_preview(settings,plan['token'])
            events = []
            for index, signed in enumerate(plan['rows']):
                child = dict(signed)
                child_signature = child.pop('signature','')
                if child.get('token')!=plan['token'] or not hmac.compare_digest(child_signature,bio._sign(settings,bio.canonical(child))):
                    raise bio.ValidationError('Подтверждение строки повреждено. Импорт отменён.')
                events.append(manual.apply_plan(connection,settings,child,operation+'-'+str(index),record=record))
            result = {'created':plan['created'],'operation':operation,'events':events,
                      'saved':sum(bool(e['writes']) for e in events),'fields_saved':sum(len(e['writes']) for e in events)}
            connection.execute('insert into logs(datetime,action,comment) values(?,?,?)',
                (events[0]['time'],BATCH_PREFIX+operation,bio.canonical(result)))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    return result


def commit_review(settings, operation):
    raise bio.ValidationError('Построчное сохранение удалено. Подтвердите общий импорт заново.')


def result_state(settings, event):
    try:
        return choices.detail(settings,event['token'],event['row_number'])
    except bio.ValidationError:
        return {'confirmed':False,'fio':evidence.display_fio(event['identity']['fio']),
                'reason':'Решение сохранено, но затем карточка изменилась вне этого импорта. Обновите выгрузку перед дальнейшей проверкой.'}


def confirmation(settings, operation):
    signed = bio.load_preview(settings,operation)
    plan = dict(signed)
    signature = plan.pop('signature','')
    if not hmac.compare_digest(signature,bio._sign(settings,bio.canonical(plan))):
        raise bio.ValidationError('Подтверждение повреждено. Откройте список заново.')
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        manual._audit_available(connection)
        batch = plan.get('state')=='file_import_plan'
        prefix = BATCH_PREFIX if batch else manual.AUDIT_PREFIX
        old = connection.execute('select comment from logs where action=?',(prefix+operation,)).fetchone()
        if old:
            event = json.loads(old['comment'])
            return {'batch_result':event} if batch else {'event':event,'updated':result_state(settings,event)}
        if not batch and plan.get('workflow_version')!=3:
            raise bio.ValidationError('Откройте проверку в текущей версии приложения заново.')
        children = plan['rows'] if batch else [signed]
        record = bio.load_preview(settings,plan['token'])
        for child_signed in children:
            child = dict(child_signed); child_mac = child.pop('signature','')
            if not hmac.compare_digest(child_mac,bio._sign(settings,bio.canonical(child))):
                raise bio.ValidationError('Подтверждение строки повреждено.')
            manual.check_plan(connection,settings,child,record=record)
    return {'batch_plan':signed,'operation':operation} if batch else {'plan':signed,'plan_token':operation}


def report(settings, token):
    view = present(settings,token)
    rows = []
    for row in view['rows']:
        review = row['review']
        actions = history_view(list(reversed(review['events']))) if review else []
        rows.append([row['person_id'],row['fio'],row['status'],row['reason'],
                     format_birth_year_input(review['current']['birthday']) if review else '',
                     review['current']['biography'] if review else '',row['source_url'],
                     '\n'.join(a['when']+' · '+a['action']+' · '+', '.join(f['label']+': '+f['decision'] for f in a['fields']) for a in actions)])
    return bio._workbook(['№ кавалера','ФИО','Статус','Объяснение','Текущий год','Биография в базе','Источник','Сохранённые действия'],rows)


def history_view(events):
    actions = []
    for event in events:
        try:
            when = datetime.fromisoformat(event['time']).astimezone().strftime('%d.%m.%Y %H:%M')
        except (KeyError,ValueError):
            when = 'Время не указано'
        fields = []
        for name in event.get('review_fields',manual.FIELDS):
            field = event['fields'][name]
            if field['decision']=='pending' or all(bio.blank(field.get(n)) for n in ['before','proposed','after']):
                continue
            before, proposed, after = (field.get(n) for n in ['before','proposed','after'])
            if name=='birthday':
                before, after = format_birth_year_input(before),format_birth_year_input(after)
            fields.append({'name':name,'label':manual.FIELDS[name],'before':before,'proposed':proposed,'after':after,
                           'decision':'Отклонено предложение' if field['decision']=='reject' else 'Сохранено' if name in event['writes'] else 'Подтверждено без изменения',
                           'source':field['source']})
        if event.get('identity_decision'):
            fields.insert(0,{'name':'identity','label':'Принадлежность источника','before':'Не подтверждена',
                'proposed':'Тот же кавалер' if event['identity_decision']=='same' else 'Другой или не подтверждённый кавалер',
                'after':'Подтверждена' if event['identity_decision']=='same' else 'Источник отклонён',
                'decision':'Решение пользователя','source':event['fields']['fio']['source']})
        if fields:
            actions.append({'when':when,'actor':'Владелец' if event.get('actor')=='Owner' else event.get('actor','Пользователь приложения'),
                            'fio':evidence.display_fio(event['identity']['fio']),'person_id':event['person_id'],
                            'action':'Импорт' if event.get('mode')=='import' else 'Ручное подтверждение','fields':fields})
    return actions
