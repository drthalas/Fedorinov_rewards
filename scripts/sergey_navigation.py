"""One editable Telegram navigation surface; input history and workflow state stay intact."""
import copy
import json
import time

MENU={'keyboard':[[{'text':'Меню'}]],'is_persistent':True,'one_time_keyboard':False,'resize_keyboard':True}
DRAFT_VIEWS={'stage','input','review','materials'}


def enabled(s):return s.meta('navigation_enabled')=='1'
def load(s,user):return json.loads(s.meta('nav:'+str(user),'null')) or {'generation':0,'message_id':None,'view':{'name':'root'},'stack':[],'render':0}
def save(s,user,state):s.set_meta('nav:'+str(user),json.dumps(state,ensure_ascii=False))


def renew_surface(s,user):
    n=load(s,user)
    if n.get('message_id'):
        n.setdefault('retired',[]).append(n['message_id']);n['message_id']=None;n.pop('sent_content',None);save(s,user,n)


def transition(s,user,view,replace=False,root=False):
    n=load(s,user)
    if root:n['stack']=[]
    elif not replace and n['view']!=view:n['stack'].append(n['view'])
    n['view']=view;n['generation']+=1;save(s,user,n)
    return n


def render(s,user,text,buttons=None):
    n=load(s,user);rows=copy.deepcopy(buttons or [])
    rows=[[b for b in row if b.get('text')!='Назад'] for row in rows];rows=[r for r in rows if r]
    if n['stack']:rows.append([{'text':'Назад','callback_data':'m:back'}])
    for row in rows:
        for button in row:
            if 'callback_data' in button:
                button['callback_data']=f"n:{n['generation']}:"+button['callback_data']
                if len(button['callback_data'].encode())>64:raise ValueError('navigation_callback_too_long')
    n['render']+=1;n['desired']={'text':text[:3900],'reply_markup':{'inline_keyboard':rows}}
    save(s,user,n)
    s.enqueue(f"nav:{user}:{n['generation']}:{n['render']}",'ui_screen',{'user_id':user,'generation':n['generation'],'render':n['render']})


def root(s,user):
    renew_surface(s,user)
    transition(s,user,{'name':'root'},root=True)
    render(s,user,'Меню\nВыберите действие. Черновик и ответы сохраняются.',[
        [{'text':'Создать задачу','callback_data':'m:new'}],
        [{'text':'Мои задачи','callback_data':'m:tasks'}]])


def install(s,user):
    if s.meta('nav_keyboard:'+str(user))!='v2':
        s.enqueue('nav-keyboard:'+str(user),'telegram',{'chat_id':user,'text':'Внизу доступна одна кнопка «Меню». Она не отменяет черновик.','reply_markup':MENU})
        s.set_meta('nav_keyboard:'+str(user),'v2')
    # Only known bot messages, never delete input history. Invalid callbacks are rejected immediately.
    for row in s.db.execute("SELECT key,payload,result FROM outbox WHERE kind='telegram' AND status='sent'").fetchall():
        p=json.loads(row['payload']);r=json.loads(row['result'] or '{}')
        if p.get('chat_id')==user and p.get('reply_markup',{}).get('inline_keyboard') and r.get('message_id'):
            s.enqueue(f"nav-strip:{user}:{r['message_id']}",'telegram_markup',{'chat_id':user,'message_id':r['message_id'],'reply_markup':{'inline_keyboard':[]}})


def unwrap(s,user,query):
    data=query.get('data','');n=load(s,user)
    if not data.startswith('n:'):return None
    parts=data.split(':',2)
    if len(parts)!=3 or parts[1]!=str(n['generation']):return None
    if query['message'].get('message_id')!=n['message_id']:return None
    return parts[2]


def go_back(s,user):
    n=load(s,user)
    if not n['stack']:root(s,user);return
    n['view']=n['stack'].pop();n['generation']+=1;save(s,user,n);show(s,user)


def show(s,user):
    try:from . import sergey_ui as ui
    except ImportError:import sergey_ui as ui
    n=load(s,user);view=n['view'];name=view['name'];d=s.current(user)
    if name=='root':
        render(s,user,'Меню\nЧерновик и ответы сохранены.',[[{'text':ui.CREATE,'callback_data':'m:new'}],[{'text':ui.MINE,'callback_data':'m:tasks'}]])
    elif name in {'list','card'}:
        render(s,user,'Обновляю ваши задачи…')
        s.enqueue(f"nav-read:{user}:{n['generation']}",'ui_read',{'user_id':user,'group':view.get('group','active'),'page':view.get('page',0),'selected':view.get('selected'),'force':True,'nav_generation':n['generation']})
    elif name=='preview_feedback':
        try:from .sergey_preview import feedback_screen
        except ImportError:from sergey_preview import feedback_screen
        text,actions=feedback_screen(s,user,view['job_id']);render(s,user,text,actions)
    elif d:
        def send(text,inline=None,**kwargs):render(s,user,text,inline)
        if name=='input' or (name=='stage' and d['state'] in {'review','review_wait'}):render(s,user,'Добавьте voice, текст или screenshot. Возврат/меню ничего не отменяют.\n'+ui.receipt(d),ui.collection_actions(d) if not d.get('analyst_transfer_update') else ui.keyboard(d,[('Отменить','cancel')]))
        elif name=='review':render(s,user,ui.material_review(d),ui.review_actions(d))
        else:ui.show_draft(d,send)
    else:render(s,user,'Нет текущего черновика. Вернитесь в меню.')


def before(s,user,text,callback):
    """Translate navigation to existing UI actions, without touching draft/consent revisions."""
    if callback:
        inner=unwrap(s,user,callback)
        if inner is None:
            old=callback.get('message',{}).get('message_id')
            if old and old!=load(s,user)['message_id']:
                s.enqueue(f'nav-stale-strip:{user}:{old}','telegram_markup',{'chat_id':user,'message_id':old,'reply_markup':{'inline_keyboard':[]}})
            show(s,user);return True,text,callback
        callback=copy.deepcopy(callback);callback['data']=inner
        if inner=='m:back':go_back(s,user);return True,text,callback
        if inner=='m:new':text='Создать задачу';callback=None
        elif inner=='m:tasks':text='Мои задачи';callback=None
        elif inner.startswith('p:'):return False,text,callback
        elif inner.startswith('q:'):
            p=inner.split(':')
            if p[1]=='list':view={'name':'list','group':p[2],'page':int(p[3])}
            else:
                group,num=p[3].rsplit('_',1);view={'name':'card','selected':p[2],'group':group,'page':int(num)}
            transition(s,user,view,replace=load(s,user)['view']['name']==view['name'])
        elif inner.startswith('u:add:') or inner.startswith('edit:'):
            transition(s,user,{'name':'input'});show(s,user);return True,text,callback
        elif inner.startswith('u:finish:'):transition(s,user,{'name':'review'})
        elif inner.startswith('u:more'):
            transition(s,user,{'name':'materials'},replace=load(s,user)['view']['name']=='materials')
        elif inner.startswith(('u:resume:','u:send:','create:','cancel:','u:cancel:')):
            if inner.startswith('u:resume:'):
                target=inner.split(':')[2]
                if s.db.execute('SELECT 1 FROM drafts WHERE id=? AND user_id=?',(target,user)).fetchone():s.set_meta(f'current:{user}',target)
            if inner.startswith(('u:send:','u:resume:')) and load(s,user)['view']['name']!='stage':transition(s,user,{'name':'stage'})
            if load(s,user)['view']['name'] not in DRAFT_VIEWS:transition(s,user,{'name':'stage'})
    if text in {'Меню','/menu','/start'}:install(s,user);root(s,user);return True,text,callback
    if text=='Назад':go_back(s,user);return True,text,callback
    if text in {'Создать задачу','/new'}:transition(s,user,{'name':'stage'})
    elif text in {'Мои задачи','/mytasks'}:transition(s,user,{'name':'list','group':'active','page':0})
    elif text in {'/help','Помощь'}:transition(s,user,{'name':'help'})
    return False,text,callback


def emit(s,user,key,text,inline=None,*,async_draft=None):
    n=load(s,user)
    if async_draft is not None:
        current=s.current(user)
        active=(current and current['id']==async_draft['id'] and n['view']['name'] in DRAFT_VIEWS
                and n['view']['name']!='materials' and not(n['view']['name']=='review' and async_draft.get('analyst_transfer_update')))
        if not active:
            s.enqueue(key,'telegram',{'chat_id':user,'text':text[:3500]+'\nПродолжить можно через «Меню» → «Создать задачу».'});return
    elif n['view']['name'] in {'root','list','card','materials'} and not inline:
        # A received part/progress acknowledgement must not replace the selected section.
        s.enqueue(key,'telegram',{'chat_id':user,'text':text[:3900]});return
    if key.startswith('ui-reply:') and n['view']['name'] in DRAFT_VIEWS:renew_surface(s,user)
    render(s,user,text,inline)


def task_result(s,user,payload,text,buttons,key):
    if payload.get('nav_generation')!=load(s,user)['generation']:return
    render(s,user,text,buttons)


def dispatch_screen(s,bot,item,payload):
    user=payload['user_id'];n=load(s,user)
    if payload['generation']!=n['generation'] or payload['render']!=n['render']:return {'skipped':True}
    desired=n['desired'];encoded=json.dumps(desired,sort_keys=True)
    for message_id in n.get('retired',[]):
        try:bot.call('editMessageReplyMarkup',{'chat_id':user,'message_id':message_id,'reply_markup':{'inline_keyboard':[]}})
        except Exception as error:
            if not any(x in getattr(error,'api_description','').lower() for x in ['message is not modified','message to edit not found']):raise
    if n.get('sent_content')==encoded:return {'message_id':n['message_id'],'unchanged':True}
    if n['message_id']:
        try:result=bot.call('editMessageText',{'chat_id':user,'message_id':n['message_id'],**desired})
        except Exception as error:
            if 'message is not modified' not in getattr(error,'api_description','').lower():raise
            result={'message_id':n['message_id']}
    else:result=bot.call('sendMessage',{'chat_id':user,**desired})
    with s.transaction():
        latest=load(s,user);latest['message_id']=result['message_id'];latest['sent_content']=encoded;latest['retired']=[];save(s,user,latest)
    return {'message_id':result['message_id']}
