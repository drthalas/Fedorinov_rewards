"""ALE-534 Telegram menu, durable multipart drafts and private task views."""
from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import time
import uuid

try:
    from .sergey_intake import safe_text
except ImportError:
    from sergey_intake import safe_text

CREATE='Создать задачу';MINE='Мои задачи'
MENU={'keyboard':[[{'text':'Меню'}]],'is_persistent':True,'one_time_keyboard':False,'resize_keyboard':True}
OPEN={'collecting','review','review_wait','asking','answer_wait','analyzing','analysis_failed','summary'}
TIERS={'T1':'небольшая локальная правка','T2':'узкое изменение поведения','T3':'сложная задача — нужен Owner','T4':'данные/системная область — нужен Owner'}
PAGE_SIZE=5


def keyboard(d,actions):
    return [[{'text':label,'callback_data':f"u:{action}:{d['id']}:{d['revision']}"}] for label,action in actions]


def all_ready(d):return bool(d['sources']) and all(s.get('media_status','ready')=='ready' for s in d['sources'])


def source(message,update_id,text):
    media=None
    if message.get('photo'):media={**message['photo'][-1],'kind':'photo'}
    elif message.get('voice') or message.get('audio'):media={**(message.get('voice') or message['audio']),'kind':'voice' if message.get('voice') else 'audio'}
    elif message.get('document'):
        doc=message['document'];mime=doc.get('mime_type','')
        if mime in {'image/png','image/jpeg','image/webp'}:media={**doc,'kind':'photo'}
        elif mime.startswith('audio/'):media={**doc,'kind':'audio-document'}
    text=safe_text(text or str(message.get('caption','')))
    if not text and not media:raise ValueError('Пришлите текст, voice/аудио или PNG/JPEG/WebP.')
    if len(text)>4000:raise ValueError('Одна текстовая часть — до 4000 символов. Остальное пришлите следующей частью.')
    if media and (media.get('file_size',0)>15*1024*1024 or media.get('duration',0)>180):
        raise ValueError('Одна часть: до 15 МБ, аудио до 3 минут. Остальные части сохранены.')
    result={'message_id':message['message_id'],'update_id':update_id,'text':text or ('[Скриншот]' if media['kind']=='photo' else '[Голосовое сообщение]'),
            'media_status':'pending' if media else 'ready'}
    if media:result.update(media=media,caption=text)
    if message.get('reply_to_message'):result['reply_to_message_id']=message['reply_to_message'].get('message_id')
    return result


def receipt(d):
    pending=sum(s.get('media_status')=='pending' for s in d['sources']);errors=sum(s.get('media_status')=='error' for s in d['sources'])
    return f"Частей: {len(d['sources'])}. Обработка: {pending}, с ошибкой: {errors}. Всё сохранено."


def material_review(d,full=False):
    lines=['Собранное описание',receipt(d)]
    for n,s in enumerate(d['sources'],1):
        kind=s.get('media',{}).get('kind','text');text=s.get('text','')
        if s.get('media_status')=='pending':text='Обрабатывается…'
        elif s.get('media_status')=='error':text='Не удалось обработать ('+s.get('media_error','media_failed')+'). Остальные части сохранены.'
        limit=max(45,min(650,2700//max(1,len(d['sources']))-30))
        if not full and len(text)>limit:text=text[:limit]+'… (раскрыть)'
        lines.append(f'\n{n}. {kind}: '+text)
    lines.append('\nЭто проверка материалов. Передача аналитику и создание задачи подтверждаются отдельно.')
    return '\n'.join(lines)


def review_actions(d):
    actions=[]
    if all_ready(d) and not d.get('analyst_transfer_update'):actions.append(('Всё верно, передать аналитику','send'))
    elif d.get('analyst_transfer_update'):actions.append(('Продолжить','resume'))
    if any(s.get('media_status')=='error' for s in d['sources']):
        actions.append(('Повторить обработку ошибок','retry'))
        actions.extend((f'Убрать часть {n}',f"drop_{s['update_id']}") for n,s in enumerate(d['sources'],1) if s.get('media_status')=='error')
    actions.extend([('Раскрыть материалы','more'),('Добавить ещё','add'),('Отменить','cancel')])
    return keyboard(d,actions)


def collection_actions(d):return keyboard(d,[('Добавить ещё','add'),('Закончить описание','finish'),('Отменить','cancel')])


def show_draft(d,send):
    if d['state'] in {'review','review_wait'} or (d['state']=='answer_wait' and any(p.get('media_status')=='error' for p in d['sources'])):
        text=material_review(d)
        send(text[:3800],review_actions(d))
    elif d['state']=='collecting':
        send(receipt(d)+'\nОтправьте ещё voice, текст или screenshot; когда всё описано — «Закончить описание».',collection_actions(d))
    elif d['state']=='summary':
        try:from .sergey_intake import summary,buttons
        except ImportError:from sergey_intake import summary,buttons
        send(summary(d),buttons(d))
    elif d['state']=='asking':
        send('Уточнение по заявке '+d['id'][:8]+':\n'+'\n'.join(d.get('analysis',{}).get('questions',[]))+'\nОтветьте текстом, voice или screenshot.',keyboard(d,[('Отменить','cancel')]))
    else:send('Заявка '+d['id'][:8]+': '+d['state']+'. Материалы сохранены.',keyboard(d,[('Продолжить','resume')]))


def handle(intake,update,message,callback,user_id,text):
    s=intake.store;update_id=update['update_id'];d=s.current(user_id);sequence=0;prefix=''
    def send(body,inline=None,menu=False):
        nonlocal sequence,prefix
        if s.meta('navigation_enabled')=='1':
            try:from . import sergey_navigation as nav
            except ImportError:import sergey_navigation as nav
            if menu:prefix=body
            elif prefix:body=prefix+'\n\n'+body;prefix=''
            if callback or text in {CREATE,MINE,'/new','/mytasks','/help','Помощь','/status','/cancel'} or menu:nav.render(s,user_id,body,inline)
            else:nav.emit(s,user_id,f'ui-reply:{update_id}:{sequence}',body,inline,async_draft=s.current(user_id))
            sequence+=1;return
        payload={'chat_id':user_id,'text':body}
        if menu:payload['reply_markup']=MENU
        elif inline:payload['reply_markup']={'inline_keyboard':inline}
        s.enqueue(f'ui-reply:{update_id}:{sequence}','telegram',payload);sequence+=1
    def new():
        draft={'id':uuid.uuid4().hex,'user_id':user_id,'role':intake.roles[user_id],'ui_version':1,'request':'','answers':{},'sources':[],
               'revision':1,'state':'collecting','created_at':time.time()}
        s.set_meta(f'current:{user_id}',draft['id']);s.save(draft)
        send('Новый черновик сохранён. Пришлите одно или несколько voice, текст и screenshots в любом сочетании. '
             'Записью/паузой аудио управляет Telegram. После отправки всех частей нажмите «Закончить описание». '
             'Пароли и токены не присылайте.',menu=True)
        send('Аналитик ещё не запущен. '+receipt(draft),collection_actions(draft))
    readonly=text in {'/start','/help','Помощь',MINE,'/mytasks','/status'} or (callback and (callback.get('data','').startswith('q:') or callback.get('data','').startswith('u:resume:')))
    if s.meta('paused')=='1' and not readonly:
        send('Приём на паузе Owner. Черновик сохранён; новые части и подтверждения пока не принимаются.');return True
    if text in {'/start','/help','Помощь'}:
        send('Создать задачу → отправить части → Закончить описание → проверить материалы → передать аналитику → '
             'ответить на уточнения → отдельно подтвердить создание Linear. «Мои задачи» показывает ваши заявки и их статус. '
             'Меню сохраняет черновик. Запись voice выполняется средствами Telegram.',menu=True)
        return True
    if text in {CREATE,'/new'}:
        if d and d['state'] in OPEN|{'confirmed'}:
            send('У вас уже есть сохранённая заявка. Продолжите её; отмена доступна только до создания Linear.',menu=True)
            actions=[('Продолжить','resume')]
            if d['state'] in OPEN:actions.append(('Отменить черновик','cancel'))
            send(receipt(d),keyboard(d,actions))
        else:new()
        return True
    if text in {MINE,'/mytasks'} or (callback and callback.get('data','').startswith('q:')):
        group='active';page=0;selected=None;force=text=='/mytasks'
        if callback:
            parts=callback['data'].split(':')
            try:
                if len(parts)!=4:raise ValueError()
                if parts[1]=='list':group=parts[2];page=int(parts[3])
                elif parts[1] in {'card','refresh'}:
                    selected=parts[2];group,num=parts[3].rsplit('_',1);page=int(num);force=parts[1]=='refresh'
                    if not s.db.execute('SELECT 1 FROM drafts WHERE id=? AND user_id=?',(selected,user_id)).fetchone():raise ValueError()
                else:raise ValueError()
                if group not in {'active','completed'} or page<0 or page>10000:raise ValueError()
            except (ValueError,TypeError):send('Эта карточка недоступна. Откройте «Мои задачи».');return True
        send('Обновляю ваши задачи. Текущий черновик сохранён.',menu=True)
        payload={'user_id':user_id,'group':group,'page':page,'selected':selected,'force':force}
        if s.meta('navigation_enabled')=='1':
            try:from .sergey_navigation import load as nav_load
            except ImportError:from sergey_navigation import load as nav_load
            payload['nav_generation']=nav_load(s,user_id)['generation']
        s.enqueue(f'ui-read:{update_id}','ui_read',payload)
        return True
    if callback and callback.get('data','').startswith('u:'):
        parts=callback['data'].split(':')
        if len(parts)!=4 or not d or parts[2]!=d['id'] or parts[3]!=str(d['revision']):
            send('Кнопка устарела; черновик сохранён. Нажмите «Создать задачу» → «Продолжить».');return True
        action=parts[1]
        if action=='resume':show_draft(d,send);return True
        if action=='cancel' and d['state'] in OPEN:
            if d.get('feedback_for'):
                try:from .sergey_preview import cancel_feedback
                except ImportError:from sergey_preview import cancel_feedback
                cancel_feedback(s,d,update_id);send('Замечания отменены; сама задача и её preview сохранены. Откройте карточку задачи.');return True
            d.update(state='cancelled',revision=d['revision']+1);s.save(d)
            s.db.execute("UPDATE material_jobs SET status='cancelled' WHERE draft_id=? AND status IN ('pending','running')",(d['id'],))
            send('Черновик отменён. Можно создать новую задачу.',menu=True);return True
        if action=='more' or re.fullmatch(r'more_\d+',action):
            content=material_review(d,full=True);pages=max(1,(len(content)+3199)//3200)
            page=min(int(action[5:]) if action.startswith('more_') else 0,pages-1)
            nav=[]
            if page:nav.append(('← Материалы',f'more_{page-1}'))
            if page+1<pages:nav.append(('Материалы →',f'more_{page+1}'))
            send(f'Материалы {page+1}/{pages}\n'+content[page*3200:(page+1)*3200],keyboard(d,nav) if nav else None)
            return True
        if d['state'] not in {'collecting','review','review_wait','answer_wait'}:
            send('Этот шаг уже завершён. Черновик и подтверждения сохранены.');return True
        if action=='add':
            d.update(state='answer_wait' if d.get('analyst_transfer_update') else 'collecting');s.save(d)
            if d.get('analyst_transfer_update'):send('Пришлите дополнительный ответ на уточнение; все предыдущие части сохранены.')
            else:show_draft(d,send)
        elif action=='finish':
            if d.get('analyst_transfer_update'):
                send('Описание уже передано. Ответы связаны с текущим уточнением.');return True
            if not d['sources']:send('Черновик пуст. Сначала пришлите описание.',collection_actions(d));return True
            d.update(state='review' if not any(x.get('media_status')=='pending' for x in d['sources']) else 'review_wait',
                     description_finished_update=update_id);s.save(d);show_draft(d,send)
        elif action=='send':
            if d['state']!='review' or not all_ready(d):send('Нужно дождаться обработки или исправить ошибку части. Все материалы сохранены.');return True
            d.update(state='analyzing',analyst_transfer_update=update_id)
            s.save(d);s.queue_analysis(d);send('Материалы переданы аналитику. Создание Linear потребует отдельного подтверждения.')
        elif action=='retry':
            for part in d['sources']:
                if part.get('media_status')=='error':
                    changed=s.db.execute("UPDATE material_jobs SET status='pending',updated=? WHERE id=? AND status='failed' AND attempts<3",(time.time(),f"{d['id']}:{part['update_id']}")).rowcount
                    if changed:part['media_status']='pending';part.pop('media_error',None)
            d.update(state='answer_wait' if d.get('analyst_transfer_update') else 'review_wait',revision=d['revision']+1);s.save(d)
            send('Повторяются только доступные неудавшиеся части (до 3 попыток). Если лимит исчерпан — уберите часть и пришлите замену.',review_actions(d))
        elif re.fullmatch(r'drop_\d+',action):
            target=int(action[5:]);removed=[x for x in d['sources'] if x['update_id']==target and x.get('media_status')=='error']
            if not removed:send('Эту часть нельзя удалить этой кнопкой.');return True
            d.setdefault('discarded_sources',[]).extend(removed);d['sources']=[x for x in d['sources'] if x not in removed]
            s.db.execute("UPDATE material_jobs SET status='cancelled' WHERE id=?",(f"{d['id']}:{target}",))
            d.update(state=('analyzing' if all_ready(d) else 'answer_wait') if d.get('analyst_transfer_update') else 'review',revision=d['revision']+1)
            s.save(d)
            if d['state']=='analyzing':s.queue_analysis(d)
            show_draft(d,send)
        else:send('Кнопка недоступна на текущем шаге.')
        return True
    if callback:return False  # Existing final create/edit/cancel and exact build/release guards stay canonical.
    if text=='/status':
        if d:show_draft(d,send)
        else:send('Нет текущего черновика. Выберите действие.',menu=True)
        return True
    if text=='/cancel':
        if d and d['state'] in OPEN:
            if d.get('feedback_for'):
                try:from .sergey_preview import cancel_feedback
                except ImportError:from sergey_preview import cancel_feedback
                cancel_feedback(s,d,update_id);send('Замечания отменены, задача не отменялась.');return True
            d.update(state='cancelled',revision=d['revision']+1);s.save(d);send('Черновик отменён.',menu=True)
        else:send('Нет неподтверждённого черновика. Подтверждённые задачи доступны в «Мои задачи».',menu=True)
        return True
    if text=='/retry':return False
    if re.match(r'^/[a-z_]+(?:@\w+)?(?:\s|$)',text):send('Команды: /new, /mytasks, /help, /status, /cancel.',menu=True);return True
    if not d or d['state'] in {'created','cancelled'}:
        send('Сначала нажмите «Создать задачу». После этого можно отправить несколько частей.',menu=True);return True
    if d['state']=='confirmed':send('Создание уже подтверждено; ожидается запись Linear. Черновик не изменяется.');return True
    if not d.get('ui_version'):return False
    try:part=source(message,update_id,text)
    except ValueError as error:send(str(error));return True
    if len(d['sources'])>=30:send('Достигнут лимит 30 частей. Закончите описание или отмените черновик.');return True
    if part.get('media',{}).get('kind')=='photo' and sum(x.get('media',{}).get('kind')=='photo' for x in d['sources'])>=4:
        send('На заявку — до четырёх screenshots. Остальные материалы сохранены.');return True
    answering=bool(d.get('analyst_transfer_update'))
    if answering and d.get('question_round',0)>0:
        part['question_round']=d.get('question_round',0);part['question_prompt']=d.get('analysis',{}).get('questions',[])
    d['test_only']=d.get('test_only',False) or 'TEST/ALE-528' in part['text']
    d['sources'].append(part);d['request']=d['request'] or part['text'];d['revision']+=1
    d['state']=('answer_wait' if any(x.get('media_status')=='pending' for x in d['sources']) else 'analyzing') if answering else 'collecting'
    s.save(d)
    if part.get('media'):
        s.db.execute('INSERT INTO material_jobs(id,draft_id,source_update,status,attempts,updated) VALUES(?,?,?,?,?,?)',
                     (f"{d['id']}:{update_id}",d['id'],update_id,'pending',0,time.time()))
    if answering:
        if all_ready(d):s.queue_analysis(d)
        send('Ответ связан с уточнением заявки. '+receipt(d))
    else:send('Часть принята. '+receipt(d),collection_actions(d))
    return True


def recover_material(store):
    with store.transaction():
        rows=store.db.execute("SELECT * FROM material_jobs WHERE status='running'").fetchall()
        for row in rows:
            status='pending' if row['attempts']<3 else 'failed'
            store.db.execute('UPDATE material_jobs SET status=?,updated=? WHERE id=?',(status,time.time(),row['id']))
            if status=='failed':
                entry=store.db.execute('SELECT body FROM drafts WHERE id=?',(row['draft_id'],)).fetchone()
                if entry:
                    d=json.loads(entry[0])
                    for part in d['sources']:
                        if part['update_id']==row['source_update']:part.update(media_status='error',media_error='interrupted_limit')
                    store.save(d)


def material_one(store,engine):
    with store.transaction():
        if store.meta('paused')=='1':return False
        job=store.db.execute("SELECT * FROM material_jobs WHERE status='pending' ORDER BY rowid LIMIT 1").fetchone()
        if not job:return False
        store.db.execute("UPDATE material_jobs SET status='running',attempts=attempts+1,updated=? WHERE id=?",(time.time(),job['id']))
        row=store.db.execute('SELECT body FROM drafts WHERE id=?',(job['draft_id'],)).fetchone();d=json.loads(row[0]) if row else None
        part=next((p for p in d['sources'] if p['update_id']==job['source_update']),None) if d else None
    prepared=None;error=None
    if not part or d['state']=='cancelled':
        store.db.execute("UPDATE material_jobs SET status='cancelled' WHERE id=?",(job['id'],));return True
    try:
        processed,_=engine.prepare({'id':d['id'],'sources':[part]});prepared=processed['sources'][0]
    except Exception as exc:error=str(exc) if re.fullmatch('[a-z_]{1,60}',str(exc)) else 'media_processing_failed'
    with store.transaction():
        row=store.db.execute('SELECT body FROM drafts WHERE id=?',(job['draft_id'],)).fetchone();current=json.loads(row[0]) if row else None
        part=next((p for p in current['sources'] if p['update_id']==job['source_update']),None) if current else None
        if not part or current['state']=='cancelled':
            store.db.execute("UPDATE material_jobs SET status='cancelled' WHERE id=?",(job['id'],));return True
        if prepared:
            part.update(prepared);part['text']=safe_text(part['text']);part.update(media_status='ready');part.pop('media_error',None)
            current['test_only']=current.get('test_only',False) or 'TEST/ALE-528' in part['text']
        else:part.update(media_status='error',media_error=error)
        store.db.execute('UPDATE material_jobs SET status=?,error=?,updated=? WHERE id=?',('done' if prepared else 'failed',error,time.time(),job['id']))
        current['revision']+=1
        if current['state']=='review_wait' and not any(p.get('media_status')=='pending' for p in current['sources']):current['state']='review'
        if current['state']=='answer_wait' and all_ready(current):current['state']='analyzing'
        store.save(current)
        if current['state']=='analyzing' and all_ready(current):store.queue_analysis(current)
        text=('Часть обработана. ' if prepared else 'Ошибка одной части; остальные сохранены. ')+receipt(current)
        actions=review_actions(current) if current['state'] in {'review','review_wait'} else collection_actions(current)
        if current['state'] in {'analyzing','asking'} or (current['state']=='answer_wait' and not error):
            actions=keyboard(current,[('Продолжить','resume'),('Отменить','cancel')])
        if current['state']=='answer_wait' and error:actions=review_actions(current)
        if current['state']=='collecting' and error:text+=' Нажмите «Закончить описание», чтобы повторить или убрать ошибочную часть.'
        if current['state']=='review':text=material_review(current)[:3800]
        if store.meta('navigation_enabled')=='1':
            try:from .sergey_navigation import emit
            except ImportError:from sergey_navigation import emit
            emit(store,current['user_id'],'material-result:'+job['id']+':'+str(job['attempts']+1),text,actions,async_draft=current)
        else:store.enqueue('material-result:'+job['id']+':'+str(job['attempts']+1),'telegram',{'chat_id':current['user_id'],'text':text,'reply_markup':{'inline_keyboard':actions}})
    return True


def local_stage(store,d,remote):
    if store.meta('owner_preview_only')=='1':
        try:from .sergey_preview import card
        except ImportError:from sergey_preview import card
        preview=card(store,d)
        if preview:return preview[:4]
    if d['state']!='created':
        names={'collecting':('Черновик','Добавьте части или закончите описание.'),'review':('Проверка материалов','Подтвердите передачу аналитику.'),
               'review_wait':('Обработка материалов','Дождитесь обработки; ошибочную часть можно повторить или убрать.'),'asking':('Уточнение','Ответьте на вопрос аналитика.'),
               'analyzing':('Аналитик работает','Дождитесь результата.'),'answer_wait':('Обработка ответа','Дождитесь обработки ответа.'),
               'summary':('Итоговая постановка','Подтвердите создание задачи или уточните.'),'confirmed':('Запись в Linear','Подтверждено; ожидается ответ Linear.'),
               'analysis_failed':('Анализ остановлен','Добавьте уточнение или /retry.'),'cancelled':('Отменено','Действий не требуется.')}
        title,action=names.get(d['state'],('Неизвестный локальный шаг','Обновите карточку.'))
        return title,action,d['state']=='cancelled',{}
    issue_type=(remote or {}).get('state',{}).get('type');links={}
    path=store.meta('delivery_state_path')
    if path and Path(path).is_file():
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
            db.row_factory=sqlite3.Row
            if db.execute('PRAGMA application_id').fetchone()[0]!=0x414C4435:raise RuntimeError('Wrong delivery state')
            job=db.execute('SELECT * FROM jobs WHERE issue_id=? ORDER BY rowid DESC LIMIT 1',((remote or {}).get('identifier',''),)).fetchone()
            if job:
                body=json.loads(job['body']);links['railway']=body.get('url')
                production=db.execute("SELECT status,body FROM operations WHERE job_id=? AND kind='production'",(job['id'],)).fetchone()
                if production:
                    p=json.loads(production['body'])
                    if production['status']=='complete':
                        links['release']='https://github.com/drthalas/Fedorinov_rewards/releases/tag/v'+p['binding']['version']
                        if issue_type=='canceled':return 'Отменено в Linear; релиз ранее опубликован','Новых действий не требуется.',True,links
                        return 'Выпущено '+p['binding']['version'],'Можно обновить программу.',True,links
                    if production['status']=='blocked':return 'Публикация остановлена: '+p.get('blocker','нужна сверка'),'Требуется Owner; неизвестные отправки не повторяются.',False,links
                    return 'Публикация','Дождитесь результата сервиса.',False,links
                physical=db.execute("SELECT status,body FROM operations WHERE job_id=? AND kind='candidate_physical_pilot'",(job['id'],)).fetchone()
                if issue_type=='canceled':return 'Отменено','Действий не требуется.',True,links
                if physical:return 'Кандидат / Windows','Дождитесь результата или выполните личное действие в сообщении с exact сборкой.',False,links
                stages={'preview_ready':'Проверка на стенде','implementing':'В работе','deploying':'Развёртывание стенда','deployed':'Проверка стенда','claimed':'Очередь'}
                if job['status']=='blocked':return 'Остановлено: '+body.get('blocker','нужна сверка'),'Требуется Owner.',False,links
                if job['status']=='cancelled':return 'Отменено','Действий не требуется.',True,links
                return stages.get(job['stage'],'В работе'),'Для приёмки используйте сообщение бота с привязанной сборкой.',False,links
    if issue_type=='canceled':return 'Отменено','Действий не требуется.',True,links
    if issue_type=='completed':return 'Завершено в Linear','Публикация этой задачи не подтверждена отдельным receipt.',True,links
    test=any('TEST/ALE-528' in p['text'] for p in d['sources'])
    if issue_type=='started':return 'В работе / на проверке по Linear',('TEST: исполнение/release запрещены.' if test else 'Следите за обновлениями; этап автоматического исполнения не подтверждён.'),False,links
    return 'Зарегистрировано в Linear',('TEST: исполнение/release запрещены.' if test else 'Ожидается разрешение Owner; общая очередь выключена.'),False,links


def task_read(store,payload,linear,key):
    user=payload['user_id'];drafts=[json.loads(r[0]) for r in store.db.execute('SELECT body FROM drafts WHERE user_id=? ORDER BY rowid DESC',(user,))]
    cached={r['draft_id']:(json.loads(r['body']),r['fetched']) for r in store.db.execute('SELECT * FROM task_cache WHERE user_id=?',(user,))}
    stale=set();now=time.time()
    needed=[d for d in drafts if d.get('issue_id') and (payload.get('force') or d['id'] not in cached or now-cached[d['id']][1]>60)]
    try:
        if needed and linear is None:raise RuntimeError('Linear unavailable')
        for start in range(0,len(needed),20):
            batch=needed[start:start+20];variables={f'i{n}':d['issue_id'] for n,d in enumerate(batch)}
            query='query('+','.join('$'+k+':String!' for k in variables)+'){'+''.join(f'r{n}:issue(id:$i{n})'+'{id identifier title url updatedAt state{name type}}' for n in range(len(batch)))+'}'
            data=linear.call(query,variables)
            for n,d in enumerate(batch):
                value=data.get('r'+str(n))
                if not value or value.get('id')!=d['issue_id']:stale.add(d['id']);continue
                cached[d['id']]=(value,now)
    except Exception:stale.update(d['id'] for d in needed)
    entries=[]
    for d in drafts:
        remote,fetched=cached.get(d['id'],(None,0));stage,action,terminal,links=local_stage(store,d,remote)
        if d['id'] in stale:stage+=' (Linear временно недоступен; данные могут устареть)'
        entries.append((d,remote,fetched,stage,action,terminal,links))
    selected=next((e for e in entries if e[0]['id']==payload.get('selected')),None)
    group=payload['group'];page=payload['page'];buttons=[]
    if selected:
        d,remote,fetched,stage,action,_,links=selected
        title=(remote or {}).get('title') or d.get('analysis',{}).get('title') or d['request'][:100] or 'Черновик'
        identity=(remote or {}).get('identifier') or 'Черновик '+d['id'][:8]
        tier=d.get('tier');text=identity+' · '+title+'\n'+(tier+' — '+TIERS.get(tier,'') if tier else 'Tier ещё не определён')+'\nСтатус: '+stage+'\nОжидаемое действие: '+action
        if remote:text+='\nLinear: '+remote['state']['name']+'; обновлено '+remote['updatedAt']
        else:text+='\nЛокально обновлено: '+time.strftime('%d.%m.%Y %H:%M UTC',time.gmtime(d.get('updated_at',d.get('created_at',0)))) if d.get('updated_at',d.get('created_at')) else '\nДата прежней записи неизвестна.'
        if fetched:text+='\nСверено с Linear: '+time.strftime('%d.%m.%Y %H:%M UTC',time.gmtime(fetched))
        for label,url in [('Linear',d.get('issue_url')),('Railway',links.get('railway')),('Release',links.get('release'))]:
            if url and url.startswith('https://'):buttons.append([{'text':label,'url':url}])
        if d['state'] in OPEN and store.meta(f'current:{user}')==d['id']:
            buttons.append([{'text':'Продолжить заявку','callback_data':f"u:resume:{d['id']}:{d['revision']}"}])
        if d['state'] in OPEN and store.meta('navigation_enabled')=='1' and store.meta(f'current:{user}')!=d['id']:
            buttons.append([{'text':'Продолжить заявку','callback_data':f"u:resume:{d['id']}:{d['revision']}"}])
        if store.meta('owner_preview_only')=='1':
            try:from .sergey_preview import card
            except ImportError:from sergey_preview import card
            preview=card(store,d)
            if preview:buttons.extend(preview[4]);text+=preview[5]
        buttons.extend([[{'text':'Обновить','callback_data':f"q:refresh:{d['id']}:{group}_{page}"}],
                        [{'text':'Назад','callback_data':f'q:list:{group}:{page}'}]])
    else:
        shown=[e for e in entries if e[5]==(group=='completed')];page=min(page,max(0,(len(shown)-1)//PAGE_SIZE))
        mode='Owner-очередь до Railway включена. Релизные стадии выключены.' if store.meta('owner_preview_only')=='1' else 'Общая очередь выключена.'
        text=('Активные' if group=='active' else 'Завершённые')+f' · {len(shown)}\nСтраница {page+1}. Только ваши заявки.\n'+mode
        timestamps=[e[2] for e in shown if e[2]]
        if timestamps:text+='\nLinear сверялся: '+time.strftime('%d.%m.%Y %H:%M UTC',time.gmtime(min(timestamps)))
        for d,remote,_,stage,_,_,_ in shown[page*PAGE_SIZE:(page+1)*PAGE_SIZE]:
            label=((remote or {}).get('identifier') or d['id'][:8])+' · '+stage
            buttons.append([{'text':label[:64],'callback_data':f"q:card:{d['id']}:{group}_{page}"}])
        if not shown:text+='\nЗаявок в этом разделе нет.'
        nav=[]
        if page>0:nav.append({'text':'←','callback_data':f'q:list:{group}:{page-1}'})
        if (page+1)*PAGE_SIZE<len(shown):nav.append({'text':'→','callback_data':f'q:list:{group}:{page+1}'})
        if nav:buttons.append(nav)
        buttons.append([{'text':'Активные','callback_data':'q:list:active:0'},{'text':'Завершённые','callback_data':'q:list:completed:0'}])
    with store.transaction():
        for draft_id,(remote,fetched) in cached.items():
            store.db.execute('INSERT OR REPLACE INTO task_cache VALUES(?,?,?,?)',(draft_id,user,json.dumps(remote),fetched))
        if store.meta('navigation_enabled')=='1':
            try:from .sergey_navigation import task_result
            except ImportError:from sergey_navigation import task_result
            task_result(store,user,payload,safe_text(text),buttons,key)
        else:store.enqueue('ui-read-result:'+key,'telegram',{'chat_id':user,'text':safe_text(text[:3900]),'reply_markup':{'inline_keyboard':buttons}})
    return {'read_complete':True}
