"""Explicit, atomic file import plus resumable field review. No migrations."""
from contextlib import closing, nullcontext
from collections import Counter
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


def workspace(settings, token, operations=(), *, connection=None, record=None, progress=lambda *args:None):
    if operations:raise bio.ValidationError('План относится к прежнему ручному интерфейсу. Загрузите файл заново.')
    view=present(settings,token,connection=connection,record=record,progress=progress)
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
        fatal=any(r['review'] is None and r['state']!='stale' for r in view['rows']),
        stale_skipped=sum(r['state']=='stale' for r in view['rows']),
        fatal_failures=[{'row':r['row'],'person_id':r['person_id'],**r['guard']} for r in view['rows'] if r.get('guard') and r['state']!='stale'],
        guard_failures=[{'row':r['row'],'person_id':r['person_id'],**r['guard']} for r in view['rows'] if r.get('guard')],
        guard_counts=dict(Counter(r['guard']['code'] for r in view['rows'] if r.get('guard'))),
        revision=bio._sign(settings,bio.canonical({'kind':'workspace-v5','base':view['revision']})))
    return view


def prepare_workspace(settings, token, revision, operations, *, progress=lambda *args:None, metrics=None):
    metrics={} if metrics is None else metrics
    started=time.perf_counter();progress('Читаем загруженный файл…',0,None)
    record=bio.load_preview(settings,token)
    metrics['read_seconds']=time.perf_counter()-started
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        # One read-only snapshot; final commit still revalidates the immutable subset
        # under BEGIN IMMEDIATE against the then-current cards and receipts.
        started=time.perf_counter()
        view=workspace(settings,token,operations,connection=connection,record=record,progress=progress)
        metrics['revalidation_seconds']=time.perf_counter()-started
        if view['fatal']:
            reason=view['fatal_failures'][0]['display_reason']
            raise bio.ValidationError(reason+' Импорт остановлен; ничего не записано. Получите свежую выгрузку и перенесите найденные сведения.')
        refreshed=not hmac.compare_digest(str(revision),view['revision'])
        plans=[];ready=view['buckets']['ready'];started=time.perf_counter()
        progress('Готовим планы строк…',0,len(ready))
        for index,row in enumerate(ready):
            _,plan=choices.row_plan(settings,token,row['row'],{n:'accept' for n in row['automatic']},
                expected=row['review']['current'],mode='import',connection=connection,record=record)
            plans.append(plan);progress('Готовим планы строк…',index+1,len(ready))
        metrics['row_plans_seconds']=time.perf_counter()-started
        summary={'fields':view['totals'],'ready':len(plans),'accepted':0,'skipped':len(view['rows'])-len(plans),
                 'stale_skipped':view['stale_skipped'],'people':len(plans),'refreshed':refreshed}
        if not plans:
            if view['stale_skipped']:
                return None, {'summary':summary,'skipped_reasons':_skipped_rows(view,plans)}
            raise bio.ValidationError('Новых подтверждённых изменений нет. Повторная запись не требуется.')
        progress('Сохраняем план проверки…',0,None);started=time.perf_counter()
        result=_store_batch(settings,token,view['filename'],plans,summary,view=view)
        metrics['serialization_seconds']=time.perf_counter()-started
        return result


def present(settings, token, *, connection=None, record=None, progress=lambda *args:None):
    record = bio.load_preview(settings,token) if record is None else record
    rows = []
    progress('Проверяем карточки…',0,len(record['rows']))
    with (closing(bio._connection(settings.rewards_db_path)) if connection is None else nullcontext(connection)) as connection:
        for index,original in enumerate(record['rows']):
            row = dict(original)
            row['guard'] = None
            try:
                review = choices.detail(settings,token,row['row'],connection=connection,record=record)
                row.update(review=review, fio=review['fio'],state=review['state'],status=review['status'],reason=review['reason'])
            except manual.RowStaleError as exc:
                reason=str(exc)
                row.update(review=None,state='stale',status='Карточка изменена после выгрузки — пропущена',reason=reason,
                    guard={'code':exc.code,'fields':exc.fields,'reason':reason,'display_reason':reason,'row_local':True,'live_revision':exc.live_revision})
            except bio.ValidationError as exc:
                reason=str(exc) if isinstance(exc,bio.ImportGuardError) else choices.friendly_error(exc)
                row.update(review=None,state='blocked',status='Проверка остановлена',reason=reason,
                    guard={'code':getattr(exc,'code','guard_unknown'),'fields':getattr(exc,'fields',[]),'reason':reason,'display_reason':reason.removeprefix(f"ID {row['person_id']}: " )})
            row['fio'] = evidence.display_fio(row['fio'])
            row['automatic'] = row['review']['automatic'] if row['review'] else {}
            row['changes'] = [{'name':n,'label':manual.FIELDS[n], 'before':row['review']['current'][n], 'after':v}
                              for n,v in row['automatic'].items()]
            row['can_review'] = bool(row['review'] and row['state'] not in {'confirmed','unchanged'})
            row['action'] = ('Продолжить проверку' if row['review'] and row['review']['events'] else
                             'Объяснение' if row['state']=='blocked' else 'Проверить')
            rows.append(row)
            progress('Проверяем карточки…',index+1,len(record['rows']))
    ready = [r for r in rows if r['automatic']]
    revision = bio._sign(settings,bio.canonical({'kind':'file-import-view','token':token,
        'rows':[(r['row'],r['review']['revision'] if r['review'] else r.get('guard') or r['reason']) for r in rows]}))
    return {'token':token,'created':record['created'],'file_sha256':record['file_sha256'],
            'filename':record.get('filename','Загруженный файл'),'rows':rows,'ready':len(ready),
            'change_count':sum(len(r['automatic']) for r in ready),
            'confirmed':sum(r['state']=='confirmed' for r in rows),
            'pending':sum(r['state'] in {'manual','blocked','stale'} for r in rows),'revision':revision}


def prepare_import(settings, token, revision, exclude=()):
    view = present(settings,token)
    if workspace(settings,token)['fatal']:raise bio.ValidationError('Подлинность файла не подтверждена. Импорт остановлен.')
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


def _skipped_rows(view, plans):
    selected={str(p['person_id']) for p in plans}
    return [{'person_id':r['person_id'],'fio':r['fio'],'reason':r['reason'],
             'stale':r['state']=='stale','fields':r['guard']['fields'] if r.get('guard') else []}
            for r in view['rows'] if str(r['person_id']) not in selected and r['state']!='confirmed']


def _store_batch(settings, token, filename, plans, summary=None, *, view=None):
    operation = secrets.token_hex(32)
    plan = {'created':time.time(),'state':'file_import_plan','token':token,'rows':plans,'filename':filename}
    view=workspace(settings,token) if view is None else view
    if view['fatal']:raise bio.ValidationError('Подлинность файла не подтверждена. Импорт остановлен.')
    plan.update(workspace_revision=view['revision'],stale_skipped=view['stale_skipped'],skipped_reasons=_skipped_rows(view,plans))
    if summary is None:
        summary={'fields':{n:sum(n in p['writes'] for p in plans) for n in manual.FIELDS},'ready':len(plans),
                 'people':len(plans),'accepted':0,'skipped':len(view['rows'])-len(plans),'stale_skipped':view['stale_skipped']}
    plan['summary']=summary
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
    view=workspace(settings,token)
    if view['fatal']:raise bio.ValidationError('Подлинность файла не подтверждена. Импорт остановлен.')
    for row in view['rows']:
        if row['state']=='stale':continue
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


def commit_import(settings, operation, progress=lambda *args:None):
    from .data_operation_lock import exclusive
    with exclusive(settings):return _commit_import(settings,operation,progress)


def _commit_import(settings, operation, progress=lambda *args:None):
    ensure_write_allowed(settings)
    plan = bio.load_preview(settings,operation)
    signature = plan.pop('signature','')
    if plan.get('state')!='file_import_plan' or not hmac.compare_digest(signature,bio._sign(settings,bio.canonical(plan))):
        raise bio.ValidationError('Подтверждение импорта повреждено. Откройте список заново.')
    progress('Импортируем данные…',0,len(plan['rows']))
    with closing(open_write_connection(settings.rewards_db_path,settings.write_mode)) as connection:
        connection.execute('begin immediate')
        try:
            manual._audit_available(connection)
            old = connection.execute('select comment from logs where action=?',(BATCH_PREFIX+operation,)).fetchone()
            if old:
                return json.loads(old['comment'])
            record = bio.load_preview(settings,plan['token'])
            # Re-authenticate every original, never disguise a trust error as a skip.
            for row in record['rows']:manual.validated_original(settings,record,row['row'])
            events = []
            for index, signed in enumerate(plan['rows']):
                child = dict(signed)
                child_signature = child.pop('signature','')
                if child.get('token')!=plan['token'] or not hmac.compare_digest(child_signature,bio._sign(settings,bio.canonical(child))):
                    raise bio.ValidationError('Подтверждение строки повреждено. Импорт отменён.')
                events.append(manual.apply_plan(connection,settings,child,operation+'-'+str(index),record=record))
                progress('Импортируем данные…',index+1,len(plan['rows']))
            result = {'created':plan['created'],'operation':operation,'events':events,
                      'saved':len({e['person_id'] for e in events if e['writes']}),'fields_saved':sum(len(e['writes']) for e in events),
                      'token':plan['token'],'file_sha256':record['file_sha256'],
                      'biographies':sum('biography' in e['writes'] for e in events),
                      'years':sum('birthday' in e['writes'] for e in events),
                      'names':sum('fio' in e['writes'] for e in events),
                      'skipped':len(record['rows'])-len({e['person_id'] for e in events if e['writes']}),
                      'stale_skipped':plan.get('stale_skipped',0),
                      'skipped_reasons':plan.get('skipped_reasons',[])}
            connection.execute('insert into logs(datetime,action,comment) values(?,?,?)',
                (events[0]['time'],BATCH_PREFIX+operation,bio.canonical(result)))
            progress('Сохраняем изменения…',len(plan['rows']),len(plan['rows']))
            connection.commit()
        except manual.RowStaleError as exc:
            connection.rollback()
            raise bio.ValidationError('Карточки изменились после подтверждения. Все изменения отменены. Обновите проверку и подтвердите импорт заново.') from exc
        except BaseException:
            connection.rollback()
            raise
    return result


def committed_result(settings,operation):
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        manual._audit_available(connection)
        row=connection.execute('select comment from logs where action=?',(BATCH_PREFIX+operation,)).fetchone()
        return json.loads(row[0]) if row else None


def result_summary(result, total_rows=None):
    events=result.get('events',[])
    return {'saved':len({e['person_id'] for e in events if e['writes']}),
            'biographies':sum('biography' in e['writes'] for e in events),
            'years':sum('birthday' in e['writes'] for e in events),
            'names':sum('fio' in e['writes'] for e in events),
            'stale_skipped':result.get('stale_skipped',0),
            'skipped':result.get('skipped',max(0,total_rows-len({e['person_id'] for e in events if e['writes']})) if total_rows is not None else 0),'skipped_reasons':result.get('skipped_reasons',[])}


def completed_preview(settings,token,view=None):
    record=bio.load_preview(settings,token)
    with closing(bio._connection(settings.rewards_db_path)) as connection:
        manual._audit_available(connection)
        for row in connection.execute('select comment from logs where action like ? order by rowid desc',(BATCH_PREFIX+'%',)):
            result=json.loads(row[0]);same_token=result.get('token')==token or any(e.get('token')==token for e in result.get('events',[]))
            same_file=view is not None and not view['fatal'] and not view['eligible'] and view['confirmed'] and any(e.get('file_sha256')==record['file_sha256'] for e in result.get('events',[]))
            if same_token or same_file:return {'operation':result['operation'],'summary':result_summary(result,len(record['rows'])),'already_done':bool(same_file and not same_token)}
    if view is not None and not view['fatal'] and not view['eligible'] and view['stale_skipped']:
        return {'operation':None,'no_changes':True,'all_stale':view['stale_skipped']==len(record['rows']),
                'summary':{'saved':0,'biographies':0,'years':0,'names':0,'stale_skipped':view['stale_skipped'],
                           'skipped':len(record['rows']),'skipped_reasons':_skipped_rows(view,[])}}
    if view is not None and not view['fatal'] and not view['eligible'] and view.get('unchanged') and not view['counts']['insufficient']:
        return {'operation':None,'no_changes':True,'summary':{'saved':0,'biographies':0,'years':0,'names':0,'skipped':len(record['rows']),'skipped_reasons':[]}}
    return None


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
            if not batch or not plan.get('workspace_revision'):
                manual.check_plan(connection,settings,child,record=record)
    if batch and plan.get('workspace_revision'):
        view=workspace(settings,plan['token'])
        if view['revision']!=plan['workspace_revision']:
            new_operation,new_plan=prepare_workspace(settings,plan['token'],plan['workspace_revision'],[])
            if new_operation is None:return {'no_changes':new_plan}
            return {'batch_plan':new_plan,'operation':new_operation}
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
