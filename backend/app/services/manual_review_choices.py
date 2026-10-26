"""Only actual unresolved choices; verified additions are explicit import items."""
from contextlib import closing, nullcontext
import hmac

from . import biography_enrichment as bio, manual_import_review as manual
from . import enrichment_evidence as evidence
from .dates import format_birth_year_input


def detail(settings, token, row_number, *, connection=None, record=None, identity_choice=None):
    if identity_choice:raise bio.ValidationError('Импорт больше не принимает ручные решения о личности или ФИО.')
    with (closing(bio._connection(settings.rewards_db_path)) if connection is None else nullcontext(connection)) as connection:
        record, values, snapshot, original, row, current = manual._validated(connection,settings,token,row_number,record=record)
    values=evidence.summary_assertions(values,snapshot)
    proof=evidence.analyze(snapshot,values,current)
    resolved=record['_progress']['decisions'];events=record['_progress']['events']
    automatic={};blockers=[];information=[]
    year=format_birth_year_input(current['birthday'])
    proposed_year=proof['year'];year_conflict=bool(proposed_year) and proposed_year!=year
    text=values.get('biography','')
    ordinary=row['kind']==bio.READY and not proof['problems'] and not year_conflict
    allowed=bio.key(values.get('status')) in {'найдено','требует проверки','биография подтверждена','подтверждено','confirmed','requires review','requires verification'}
    trusted=proof['auto_verified'] and allowed
    declined=any(e.get('identity_decision')=='different' for e in events)
    if declined:blockers.append('Источник ранее отклонён. Для новых сведений нужна свежая выгрузка.')
    elif year_conflict:
        if not proof['valid_year']:blockers.append('В предложении источника неверный год.')
        elif not proof['year_reliable']:information.append('Год источника спорный; текущий год сохранён.')
        elif trusted and 'birthday' not in resolved:automatic['birthday']=proposed_year
        elif not trusted:blockers.append('Для замены года нет достоверной сверки полного ФИО, точной награды и номера.')
    if not declined and not bio.blank(text):
        if not bio.blank(current['biography']):information.append('Биография уже заполнена и не будет перезаписана.')
        elif len(text)>2500:blockers.append('Текст длиннее 2 500 символов. Нужна подготовленная краткая биография.')
        elif (trusted or ordinary) and 'biography' not in resolved:automatic['biography']=text
        else:blockers.append(proof['problems'][0] if proof['problems'] else 'Нет отдельного подтверждения полного ФИО, точной награды и номера источником.')
    if not automatic and not blockers:
        if bio.blank(text) and bio.blank(current['biography']):blockers.append('В XLSX нет текста биографии. Одна ссылка не содержит подготовленного текста для импорта.')
        elif not proposed_year or proposed_year==year or not proof['year_reliable']:
            information.append('Фактических изменений нет: биография заполнена или год уже совпадает.')
    confirmed=bool(events) and not automatic and not blockers
    state='confirmed' if confirmed else 'ready' if automatic else 'blocked' if blockers else 'unchanged'
    status={'confirmed':'Подтверждено','ready':'Готово к импорту','blocked':'Недостаточно данных','unchanged':'Без изменений'}[state]
    reason=('Будут добавлены: '+', '.join(manual.FIELDS[n].lower() for n in automatic)+'.') if automatic else (blockers[0] if blockers else information[-1])
    return {'token':token,'row_number':row_number,'person_id':snapshot['person']['person_id'],
        'fio':evidence.display_fio(current['fio']),'raw_fio':current['fio'],'award_context':proof['award_context'],
        'fields':{},'automatic':automatic,'blockers':blockers,'information':information,
        'proposals':{'biography':text,'birthday':proposed_year,'fio':proof['fio']},'current':current,
        'source':proof['source'],'sources':proof['sources'],'notes':proof['notes'],
        'identity_required':False,'identity_decision':None,'source_fio':proof['fio'],'identity_supported':proof['verified'],
        'ambiguous':bool(proof['problems']),'confirmed':confirmed,'state':state,'status':status,'reason':reason,
        'events':events,'ordinary':ordinary,'receipt':events[-1]['operation'] if events else None,
        'revision':bio._sign(settings,bio.canonical({'kind':'enrichment-auto-v5','token':token,'row':row_number,
            'current':current,'resolved':resolved,'receipt':events[-1]['operation'] if events else None}))}


def row_plan(settings, token, row_number, decisions, *, expected=None, mode='review', identity_choice=None):
    review = detail(settings,token,row_number,identity_choice=identity_choice)
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
    if identity_choice:plan['identity_decision']=identity_choice
    plan['signature'] = bio._sign(settings,bio.canonical(plan))
    bio._save(settings,plan_token,plan)
    return plan_token,plan


def prepare(settings, token, row_number, submitted):
    raise bio.ValidationError('Ручное подтверждение строк удалено. Используйте общий импорт проверенных дополнений.')


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
