"""Only actual unresolved choices; verified additions are explicit import items."""
from contextlib import closing, nullcontext
import hmac

from . import biography_enrichment as bio, manual_import_review as manual
from . import enrichment_evidence as evidence
from .dates import format_birth_year_input


def detail(settings, token, row_number, *, connection=None, record=None):
    with (closing(bio._connection(settings.rewards_db_path)) if connection is None else nullcontext(connection)) as connection:
        record, values, snapshot, original, row, current = manual._validated(connection,settings,token,row_number,record=record)
    proof = evidence.analyze(snapshot,values,current)
    resolved = record['_progress']['decisions']
    proposals = {'biography':values.get('biography',''),'birthday':proof['year'],'fio':proof['fio']}
    automatic = {}
    fields = {}
    blockers = list(proof['problems'])
    information = []
    year = format_birth_year_input(current['birthday'])
    year_conflict = bool(proof['year']) and proof['year']!=year
    ordinary = row['kind']==bio.READY and not proof['problems'] and not year_conflict
    allowed_status = bio.key(values.get('status')) in {'найдено','требует проверки','биография подтверждена','подтверждено','confirmed','requires review','requires verification'}
    trusted = proof['auto_verified'] and allowed_status
    if proof['year'] and not proof['valid_year']:
        blockers.append('Год в источнике указан неверно. Исправьте предложение в файле.')
        trusted = False
    if not proof['problems']:
        if year_conflict and 'birthday' not in resolved:
            if trusted and year=='1945' and proof['valid_year']:
                automatic['birthday'] = proof['year']
            elif proof['verified'] and proof['valid_year']:
                fields['birthday'] = {'label':'Год рождения','current':year,'proposed':proof['year'],
                    'reason':'Исходный год не является заглушкой 1945. Выберите, какой год оставить.' if year!='1945' else 'Этот источник требует личной сверки. Выберите год вручную.',
                    'sources':proof['sources'],'recommendation':'Сопоставьте сведения источника с карточкой кавалера.'}
            else:
                blockers.append('Для изменения года не хватает сверки полного ФИО, точной награды и номера.')
        elif year=='1945' and proof['year']=='1945' and proof['verified']:
            information.append('Источник подтверждает 1945 год. Он останется без изменений.')
        text = proposals['biography']
        if not bio.blank(text):
            if not bio.blank(current['biography']):
                information.append('Биография уже импортирована. Повторно записываться не будет.' if resolved.get('biography')=='accept' else 'Существующая биография сохранена. Замена заполненного текста в этом импорте не выполняется.')
            elif len(text)>2500:
                blockers.append('Биография длиннее 2 500 символов. Сократите её в файле.')
            elif (trusted or ordinary) and 'biography' not in resolved:
                automatic['biography'] = text
            elif 'biography' not in resolved:
                blockers.append('Для добавления биографии не хватает подтверждения личности или источника.')
    if proof['problems']:
        blockers.append('ФИО, год и биография из этого источника не будут перенесены. Уточните личность и загрузите проверенные сведения заново.')
    active = set(automatic)|set(fields)
    events = record['_progress']['events']
    confirmed = bool(events) and not active and not blockers
    state = 'confirmed' if confirmed else 'manual' if fields else 'blocked' if blockers and not automatic else 'ready' if automatic else 'unchanged'
    if events and fields:
        status = 'Частично подтверждено'
    else:
        status = {'confirmed':'Подтверждено','manual':'Нужен выбор года','blocked':'Нужны подтверждения','ready':'Готово к импорту','unchanged':'Без изменений'}[state]
    reason = 'Все решения сохранены. Повторная проверка не требуется.' if confirmed else (
        'Будут добавлены: '+', '.join(manual.FIELDS[n].lower() for n in automatic)+'.' if automatic else '')
    if fields:
        reason += ' Год рождения нужно выбрать вручную.'
    if blockers:
        reason += ' '+blockers[0]
    if state=='unchanged':
        reason = information[0] if information else 'Подходящих изменений в файле нет.'
    return {'token':token,'row_number':row_number,'person_id':snapshot['person']['person_id'],
            'fio':evidence.display_fio(current['fio']),'raw_fio':current['fio'],'award_context':proof['award_context'],
            'fields':fields,'automatic':automatic,'blockers':blockers,'information':information,
            'proposals':proposals,'current':current,'source':proof['source'],'sources':proof['sources'],'notes':proof['notes'],
            'source_fio':proof['fio'],'identity_supported':proof['verified'],'ambiguous':bool(proof['problems']),
            'confirmed':confirmed,'state':state,'status':status,'reason':reason.strip(),
            'events':events,'ordinary':ordinary,
            'receipt':events[-1]['operation'] if events else None,
            'revision':bio._sign(settings,bio.canonical({'kind':'enrichment-review-v3','token':token,'row':row_number,
                                                       'current':current,'resolved':resolved,'receipt':events[-1]['operation'] if events else None}))}


def row_plan(settings, token, row_number, decisions, *, expected=None, mode='review'):
    review = detail(settings,token,row_number)
    if review['confirmed'] or set(decisions)-set(review['automatic'])-set(review['fields']):
        raise bio.ValidationError('Эти поля уже подтверждены или недоступны. Обновите список.')
    if expected is not None and review['current']!=expected:
        raise bio.ValidationError('Карточка изменилась после проверки. Откройте её заново.')
    values = {'actor':'Пользователь приложения','identity_confirm':'yes'}
    for name in manual.FIELDS:
        values[name+'_decision'] = decisions.get(name,'pending')
        values[name+'_proposal'] = review['proposals'][name]
        values[name+'_source'] = review['source']
        values[name+'_evidence'] = review['notes'] or 'Принадлежность биографии подтверждена автором файла и явным импортом пользователя.'
    active = list(set(review['automatic'])|set(review['fields']))
    plan_token, plan = manual.prepare(settings,token,row_number,values,review_fields=active,
        identity_pending=bool(review['blockers']),expected_fields=review['current'],expected_receipt=review['receipt'])
    plan.pop('signature')
    plan.update(workflow_version=3,mode=mode)
    plan['signature'] = bio._sign(settings,bio.canonical(plan))
    bio._save(settings,plan_token,plan)
    return plan_token,plan


def prepare(settings, token, row_number, submitted):
    review = detail(settings,token,row_number)
    if review['confirmed']:
        raise bio.ValidationError('Этот кавалер уже подтверждён. Повторная запись не требуется.')
    if not hmac.compare_digest(str(submitted.get('review_revision','')),review['revision']):
        raise bio.ValidationError('Карточка изменилась после проверки. Откройте кавалера заново; ничего не записано.')
    if any(str(k).endswith('_choice') and v and str(k)[:-7] not in review['fields'] for k,v in submitted.items()):
        raise bio.ValidationError('Это поле больше не требует ручного выбора. Откройте актуальную проверку заново.')
    decisions = {n:'accept' for n in review['automatic']}
    for name in review['fields']:
        choice = submitted.get(name+'_choice','')
        if choice not in {'','current','proposed'}:
            raise bio.ValidationError('Неизвестный вариант. Откройте кавалера заново.')
        if choice:
            decisions[name] = 'accept' if choice=='proposed' else 'reject'
    if not decisions:
        raise bio.ValidationError('Нет выбранных изменений. Можно пропустить кавалера.')
    return row_plan(settings,token,row_number,decisions,expected=review['current'],mode='review' if review['fields'] else 'import')


def complete(event):
    names = event.get('review_fields',list(manual.FIELDS))
    return not event.get('identity_pending',False) and all(event['fields'][n]['decision']!='pending' for n in names)


def friendly_error(exc):
    message = str(exc)
    if any(word in message for word in ('служебные данные','Подпись','подписи','План проверки повреждён')):
        return 'Не удалось проверить исходный файл. Скачайте новую выгрузку и перенесите только найденные сведения.'
    if 'устарели' in message or 'после проверки' in message or 'вне этого импорта' in message:
        return 'Карточка изменена вне этого импорта. Обновите файл и проверьте сведения заново; ничего не записано.'
    return message
