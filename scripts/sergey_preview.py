"""Owner-only multi-task preview pilot. Queue ends at Railway acceptance, never release."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

try:
    from .sergey_intake import Store,Linear,contract,safe_text,equivalent_linear_description,ApiError
    from .sergey_delivery import DeliveryStore,DeliveryBlocked,contract_hash,private_json
    from .sergey_navigation import render,transition,show,load as nav_load
except ImportError:
    from sergey_intake import Store,Linear,contract,safe_text,equivalent_linear_description,ApiError
    from sergey_delivery import DeliveryStore,DeliveryBlocked,contract_hash,private_json
    from sergey_navigation import render,transition,show,load as nav_load

SCHEMA='''CREATE TABLE IF NOT EXISTS preview_queue(
 draft_id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,issue_id TEXT NOT NULL,identifier TEXT NOT NULL,
 revision INTEGER NOT NULL,contract_revision INTEGER NOT NULL,contract_hash TEXT NOT NULL,
 stage TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 0,owner TEXT,fence INTEGER NOT NULL DEFAULT 0,
 lease_until REAL NOT NULL DEFAULT 0,body TEXT NOT NULL,updated REAL NOT NULL);
 CREATE UNIQUE INDEX IF NOT EXISTS one_owner_preview ON preview_queue(active) WHERE active=1;'''
STAGES={'queued':'В очереди','planning':'Подготовка реализации','implementing':'В работе','deploying':'Развёртывание Railway','verifying':'Проверка Railway','review':'Проверка на стенде','feedback':'Нужны исправления','revision_sync':'Сохранение новой постановки','accept_requested':'Фиксация приёмки','accepted':'Принято на Railway','needs_owner':'Требует решения Owner','blocked':'Остановлено','cancelled':'Отменено'}
TERMINAL={'accepted','cancelled'}


def row(s,draft_id):
    r=s.db.execute('SELECT * FROM preview_queue WHERE draft_id=?',(draft_id,)).fetchone()
    return dict(r) if r else None


def job_id(r):return f"owner-preview:{r['draft_id']}:r{r['revision']}"


def enqueue_created(s,d,payload,result):
    if (not s.meta('owner_preview_mode') or d.get('owner_preview_mode')!=s.meta('owner_preview_mode') or d['role']!='owner'
            or d['user_id']!=int(s.meta('owner_preview_owner','0'))
            or d.get('state')!='created' or not d.get('ui_version') or not d.get('confirmation_update') or not d.get('analyst_transfer_update')
            or payload.get('test_only') or d.get('test_only') or any('TEST/ALE-528' in x['text'] for x in d['sources'])):return
    stage='queued' if d['tier'] in {'T1','T2'} else 'needs_owner'
    body={'mode':s.meta('owner_preview_mode'),'tier':d['tier'],'contract':payload['description'],'confirmation_update':d['confirmation_update'],
          'branch':'preview/'+d['id'],'url':result['url'],'history':[],'owner_decisions':[]}
    s.db.execute('INSERT OR IGNORE INTO preview_queue(draft_id,user_id,issue_id,identifier,revision,contract_revision,contract_hash,stage,body,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                 (d['id'],d['user_id'],result['id'],result['identifier'],1,d['revision'],contract_hash(payload['description']),stage,json.dumps(body),time.time()))


def card(s,d):
    r=row(s,d['id'])
    if not r:
        candidates=json.loads(s.meta('owner_preview_adoptions','{}'))
        if d['id'] in candidates:return 'Ожидает выбора Owner','Включите ранее подтверждённую задачу в текущий preview-пилот.',False,{},[[{'text':'Включить в Owner-пилот','callback_data':'p:adopt:'+d['id']}]],''
        return None
    b=json.loads(r['body']);title=STAGES[r['stage']];action='Дождитесь сервиса.'
    cached=s.db.execute('SELECT body FROM task_cache WHERE draft_id=? AND user_id=?',(d['id'],d['user_id'])).fetchone()
    cancelled=cached and json.loads(cached[0])['state']['type']=='canceled'
    if cancelled:return 'Отменено в Linear','Сервис сверяет остановку; новых действий не требуется.',True,{'railway':b.get('preview_url')},[],''
    if r['stage']=='queued':action='Ждёт завершения проверки текущего общего стенда.'
    elif r['stage']=='review':action='Откройте Railway и примите сборку либо пришлите замечания.'
    elif r['stage']=='feedback':action='Добавьте замечания и явно закончите описание; затем подтвердите новую постановку.'
    elif r['stage']=='accepted':action='Preview принят. Candidate/Windows/production отключены.'
    elif r['stage']=='needs_owner':action='Нужно решение Owner; автоматическое исполнение T3/T4/защищённых изменений запрещено.'
    elif r['stage']=='blocked':title+=': '+b.get('blocker','нужна сверка');action='Требуется сверка Owner; подтверждённые действия не повторяются.'
    links={'railway':b.get('preview_url')};actions=[]
    token=b.get('review_token')
    if r['stage']=='review' and token:
        actions=[[{'text':'Принять на стенде','callback_data':'p:accept:'+token}],[{'text':'Нужны исправления','callback_data':'p:fix:'+token}]]
    elif r['stage']=='feedback':actions=[[{'text':'Продолжить замечания','callback_data':f"u:resume:{d['id']}:{d['revision']}"}]]
    elif r['stage']=='needs_owner':actions=[[{'text':'Решение Owner','callback_data':'p:decision:'+r['draft_id']}]]
    elif r['stage']=='blocked':actions=[[{'text':'Повторить сверку','callback_data':'p:reconcile:'+r['draft_id']}]]
    extra=''
    if b.get('deployed_head'):extra=f"\nПодтверждённый стенд r{b.get('verified_revision',r['revision'])} HEAD {b['deployed_head']}\nСостав: "+', '.join(b.get('composition',[]))
    return title,action,r['stage'] in TERMINAL,links,actions,extra


def feedback_screen(s,user,draft_id):
    d=s.current(user);r=row(s,draft_id)
    if not r:return 'Заявка недоступна.',[]
    if r['stage']=='needs_owner':return 'Требуется решение Owner. Можно уточнить постановку до безопасного T1/T2. Защищённые области в этом режиме не разрешаются.',[[{'text':'Уточнить постановку','callback_data':'p:refine:'+draft_id}]]
    try:from .sergey_ui import show_draft
    except ImportError:from sergey_ui import show_draft
    out=[];show_draft(d,lambda text,inline=None:out.append((text,inline)))
    return out[-1] if out else ('Замечания сохранены.',[])


def begin_feedback(s,user,r,update_id):
    d=json.loads(s.db.execute('SELECT body FROM drafts WHERE id=? AND user_id=?',(r['draft_id'],user)).fetchone()[0]);b=json.loads(r['body'])
    d.setdefault('dialogue_history',[]).append({'revision':d['revision'],'analysis':copy.deepcopy(d.get('analysis')),'analyst_transfer_update':d.get('analyst_transfer_update'),
        'confirmation_update':d.get('confirmation_update'),'preview_revision':r['revision'],'deployed_head':b.get('deployed_head'),'feedback_requested_update':update_id,
        'sources':copy.deepcopy(d['sources']),'answers':copy.deepcopy(d['answers']),'from_stage':r['stage'],'active':r['active'],'other_current':s.meta(f'current:{user}')})
    d.update(state='collecting',feedback_for=r['draft_id'],analyst_transfer_update=None,description_finished_update=None)
    d['feedback_context']={'preview_revision':r['revision'],'head':b.get('deployed_head'),'task':b['contract']}
    s.save(d);s.set_meta(f'current:{user}',d['id'])
    s.db.execute("UPDATE preview_queue SET stage='feedback',body=?,updated=? WHERE draft_id=?",(json.dumps(b),time.time(),r['draft_id']))
    transition(s,user,{'name':'stage','feedback_job':r['draft_id']})
    try:from .sergey_ui import collection_actions
    except ImportError:from sergey_ui import collection_actions
    render(s,user,'Опишите замечания voice/текстом/screenshots. Предыдущие материалы остаются в контексте. Новая issue не создаётся. После ввода — «Закончить описание».',
           collection_actions(d))


def cancel_feedback(s,d,update_id):
    r=row(s,d['id']);snapshot=d['dialogue_history'][-1];body=json.loads(r['body'])
    snapshot['cancelled_at']=time.time();snapshot['cancel_update']=update_id;snapshot['cancelled_feedback_sources']=copy.deepcopy(d['sources'])
    d.update(state='created',analysis=copy.deepcopy(snapshot['analysis']),sources=copy.deepcopy(snapshot['sources']),answers=copy.deepcopy(snapshot['answers']),
             analyst_transfer_update=snapshot['analyst_transfer_update'],revision=d['revision']+1)
    d.pop('feedback_for',None);d.pop('feedback_context',None);s.save(d)
    s.db.execute("UPDATE analysis_jobs SET status='superseded' WHERE draft_id=? AND status='pending'",(d['id'],))
    s.db.execute("UPDATE material_jobs SET status='cancelled' WHERE draft_id=? AND status IN ('pending','running')",(d['id'],))
    body['review_token']=uuid.uuid4().hex
    s.db.execute('UPDATE preview_queue SET stage=?,active=?,body=?,updated=? WHERE draft_id=?',(snapshot['from_stage'],snapshot['active'],json.dumps(body),time.time(),d['id']))
    other=snapshot.get('other_current')
    if other and other!=d['id'] and s.db.execute('SELECT 1 FROM drafts WHERE id=? AND user_id=?',(other,d['user_id'])).fetchone():s.set_meta(f"current:{d['user_id']}",other)


def handle_feedback(intake,update,message,callback,user,text):
    s=intake.store
    if not callback or not callback.get('data','').startswith('p:'):return False
    if intake.roles[user]!='owner':return True
    parts=callback['data'].split(':')
    if len(parts)!=3:return True
    action,token=parts[1:]
    if action=='adopt':
        candidates=json.loads(s.meta('owner_preview_adoptions','{}'));candidate=candidates.get(token)
        saved=s.db.execute('SELECT body FROM drafts WHERE id=? AND user_id=?',(token,user)).fetchone()
        if not candidate or not saved:return True
        d=json.loads(saved[0])
        if d['state']!='created' or d['revision']!=candidate['contract_revision']:return True
        d['owner_preview_mode']=s.meta('owner_preview_mode');d['preview_adoption_update']=update['update_id'];s.save(d)
        enqueue_created(s,d,candidate['payload'],candidate['result']);candidates.pop(token);s.set_meta('owner_preview_adoptions',json.dumps(candidates))
        render(s,user,'Ранее подтверждённая задача включена в Owner preview-пилот.');return True
    if action=='reconcile':
        r=row(s,token)
        if not r or r['user_id']!=user or r['stage']!='blocked':return True
        b=json.loads(r['body']);stage=b.get('blocked_stage')
        if stage not in {'queued','planning','implementing','deploying','verifying','accept_requested'}:return True
        b.pop('blocker',None);s.db.execute('UPDATE preview_queue SET stage=?,owner=NULL,lease_until=0,body=?,updated=? WHERE draft_id=?',(stage,json.dumps(b),time.time(),token))
        render(s,user,'Сверяю тот же checkpoint. Подтверждённые операции не повторяются.');return True
    if action in {'decision','refine'}:
        r=row(s,token)
        if not r or r['user_id']!=user or r['stage']!='needs_owner':return True
        if action=='refine':begin_feedback(s,user,r,update['update_id'])
        else:transition(s,user,{'name':'preview_feedback','job_id':token});show(s,user)
        return True
    match=s.db.execute("SELECT * FROM preview_queue WHERE user_id=? AND json_extract(body,'$.review_token')=?",(user,token)).fetchone()
    if not match:return True
    r=dict(match);b=json.loads(r['body'])
    if r['stage']!='review':return True
    if action=='fix':begin_feedback(s,user,r,update['update_id'])
    elif action=='accept':
        b['acceptance_request']={'update_id':update['update_id'],'head':b['deployed_head'],'deployment_id':b['deployment_id'],'preview_revision':r['revision'],'at':time.time()}
        s.db.execute("UPDATE preview_queue SET stage='accept_requested',body=?,updated=? WHERE draft_id=? AND stage='review'",(json.dumps(b),time.time(),r['draft_id']))
        render(s,user,'Проверяю exact сборку и фиксирую приёмку Railway. Это не разрешает выпуск.')
    return True


def confirm_revision(s,d,update_id):
    r=row(s,d['feedback_for'])
    if not r or r['stage']!='feedback' or r['user_id']!=d['user_id']:raise ValueError('feedback_scope_changed')
    d['feedback_confirmation_update']=update_id;d['state']='confirmed';s.save(d)
    payload=contract(d);payload['description']+='\n\n## Owner preview corrections\n'+f"Preview revision {r['revision']} → {r['revision']+1}. Explicit feedback confirmation update_id={update_id}. Candidate/Windows/main/production disabled.\n"
    s.enqueue(f"preview-revision:{d['id']}:{d['revision']}",'linear_revision',{'draft_id':d['id'],'id':r['issue_id'],'description':payload['description'],'title':payload['title'],'tier':d['tier'],'contract_revision':d['revision'],'preview_revision':r['revision']+1})
    s.db.execute("UPDATE preview_queue SET stage='revision_sync',updated=? WHERE draft_id=?",(time.time(),r['draft_id']))


def complete_revision(s,payload):
    d=json.loads(s.db.execute('SELECT body FROM drafts WHERE id=?',(payload['draft_id'],)).fetchone()[0]);r=row(s,d['id']);b=json.loads(r['body'])
    b['history'].append({'revision':r['revision'],'contract_hash':r['contract_hash'],'head':b.get('deployed_head'),'deployment_id':b.get('deployment_id')})
    b.update(contract=payload['description'],tier=payload['tier'],base_head=b.get('deployed_head') or b.get('base_head'));b.pop('review_token',None)
    stage='queued' if payload['tier'] in {'T1','T2'} else 'needs_owner'
    s.db.execute('UPDATE preview_queue SET revision=?,contract_revision=?,contract_hash=?,stage=?,owner=NULL,lease_until=0,body=?,updated=? WHERE draft_id=?',
        (payload['preview_revision'],payload['contract_revision'],contract_hash(payload['description']),stage,json.dumps(b),time.time(),d['id']))
    d['state']='created';s.save(d)


class Facade:
    def __init__(self,worker,r):self.worker=worker;self.r=r
    def operation(self,*a,**k):return self.worker.state.operation(*a,**k)
    def event(self,*a):return self.worker.state.event(*a)
    def guard(self,job):
        current=row(self.worker.intake,self.r['draft_id'])
        if (not current or current['owner']!=self.worker.owner or current['fence']!=job['fence'] or current['revision']!=self.r['revision'] or current['lease_until']<=time.time()):raise DeliveryBlocked('preview_lease_lost')
        if self.worker.intake.meta('paused')=='1' or self.worker.intake.meta('delivery_paused')=='1':raise DeliveryBlocked('paused')
        issue=self.worker.issue(current)
        if issue['state']['type']=='canceled' and not getattr(self,'allow_cancelled_reconcile',False):raise DeliveryBlocked('preview_issue_cancelled')


class PreviewWorker:
    def __init__(self,config):
        self.config=config;self.intake=Store(Path(config['intake_state']));self.state=DeliveryStore(Path(config['delivery_state']))
        self.owner=uuid.uuid4().hex;self.stop=threading.Event();self.adapters={};self.next_poll=0
        if config.get('general_queue') is not False or config.get('release') is not False or config.get('capabilities')!=['implement','railway_preview']:
            raise DeliveryBlocked('owner_preview_capability_violation')
        self.credentials=private_json(Path(config['credentials']));self.linear=Linear(self.credentials['linear_api_key'],{})
        if int(self.credentials['owner_user_id'])!=config['owner_id']:raise DeliveryBlocked('preview_owner_identity_changed')
        template=private_json(Path(config['template_config']))
        for proof_path in Path(template['work_root']).glob('*/build-r*/access/access.json'):
            proof=json.loads(proof_path.read_text())
            if proof.get('closed'):continue
            local=Path(proof['local_key'])
            if local.parent!=Path.home()/'.ssh' or not re.fullmatch('ale528-owner-preview-[a-f0-9]{32}',local.name):raise DeliveryBlocked('unknown_preview_access_record')
            result=subprocess.run([shutil.which('railway') or '/opt/homebrew/bin/railway','ssh','keys','remove',proof['fingerprint']],capture_output=True,timeout=40)
            if result.returncode:raise DeliveryBlocked('railway_temporary_access_cleanup_required')
            for path in [local,local.with_suffix('.pub'),proof_path.parent/'temporary-key',proof_path.parent/'temporary-key.pub']:path.unlink(missing_ok=True)
            proof['closed']=True;proof_path.write_text(json.dumps(proof))
    def cancel(self):
        self.stop.set()
        for adapter in self.adapters.values():adapter.cancel()
    def claim(self):
        with self.intake.transaction():
            r=self.intake.db.execute('SELECT * FROM preview_queue WHERE active=1').fetchone()
            if not r:r=self.intake.db.execute("SELECT * FROM preview_queue WHERE stage='queued' AND active=0 AND user_id=? AND json_extract(body,'$.mode')=? ORDER BY rowid LIMIT 1",(self.config['owner_id'],self.config['mode_id'])).fetchone()
            if not r:return None
            r=dict(r)
            if r['user_id']!=self.config['owner_id'] or json.loads(r['body'])['mode']!=self.config['mode_id']:raise DeliveryBlocked('preview_mode_job_mismatch')
            if r['stage'] in {'feedback','review','needs_owner','revision_sync'}:return r
            if r['owner']!=self.owner and r['lease_until']>time.time():return None
            self.intake.db.execute('UPDATE preview_queue SET active=1,owner=?,fence=fence+?,lease_until=? WHERE draft_id=?',
                (self.owner,0 if r['owner']==self.owner else 1,time.time()+30,r['draft_id']))
            return row(self.intake,r['draft_id'])
    def heartbeat(self):
        s=Store(Path(self.config['intake_state']))
        try:
            while not self.stop.wait(5):s.db.execute('UPDATE preview_queue SET lease_until=? WHERE owner=? AND active=1 AND lease_until>?',(time.time()+30,self.owner,time.time()))
        finally:s.db.close()
    def update(self,r,stage,body=None,active=None):
        return self.intake.db.execute('UPDATE preview_queue SET stage=?,body=?,active=?,updated=? WHERE draft_id=? AND revision=? AND fence=? AND stage=?',
            (stage,json.dumps(body if body is not None else json.loads(r['body'])),r['active'] if active is None else active,time.time(),r['draft_id'],r['revision'],r['fence'],r['stage'])).rowcount==1
    def issue(self,r):
        i=self.linear.call('query($id:String!){issue(id:$id){id identifier description title state{id type name} creator{id} team{id} project{id}}}',{'id':r['issue_id']})['issue']
        if not i or i['id']!=r['issue_id'] or i['identifier']!=r['identifier']:raise DeliveryBlocked('preview_linear_identity_changed')
        if contract_hash(i['description'])!=r['contract_hash']:raise DeliveryBlocked('preview_linear_contract_changed')
        if (i.get('creator',{}).get('id')!='0b34be60-67c7-46a0-925c-607afdc3180d' or i.get('team',{}).get('id')!='cc0f1982-1457-48af-967b-d56a672ee8ae' or i.get('project',{}).get('id')!='d7ae5979-8aa5-4bc9-a6ee-479c898e15c2'):raise DeliveryBlocked('preview_linear_provenance_changed')
        return i
    def sync(self,r,name):
        issue=self.issue(r);target=self.config['linear_states'][name]
        if issue['state']['id']!=target:self.linear.call('mutation($id:String!,$s:String!){issueUpdate(id:$id,input:{stateId:$s}){success}}',{'id':r['issue_id'],'s':target})
    def comment(self,r,label,text):
        kind='preview-comment:'+label;key=job_id(r);op=self.state.operation(key,kind);marker='Owner preview receipt '+key+' '+label
        if op and op['status']=='done':return
        data=self.linear.call('query($id:String!){issue(id:$id){comments{nodes{id body}}}}',{'id':r['issue_id']})['issue']['comments']['nodes']
        found=[c for c in data if marker in c['body']]
        if found:self.state.operation(key,kind,'done',{'id':found[0]['id']});return
        if op:raise DeliveryBlocked('linear_preview_comment_uncertain')
        self.state.operation(key,kind,'intent',{'at':time.time()})
        result=self.linear.call('mutation($id:String!,$b:String!){commentCreate(input:{issueId:$id,body:$b}){success comment{id}}}',{'id':r['issue_id'],'b':text+'\n\n'+marker})['commentCreate']
        if not result.get('success'):raise DeliveryBlocked('linear_preview_comment_unconfirmed')
        self.state.operation(key,kind,'done',{'id':result['comment']['id']})
    def adapter(self,r):
        key=job_id(r)
        if key not in self.adapters:
            try:from .sergey_preview_executor import DynamicPreviewAdapter
            except ImportError:from sergey_preview_executor import DynamicPreviewAdapter
            body=json.loads(r['body']);base=json.loads(self.intake.meta('owner_preview_base'))
            c=copy.deepcopy(private_json(Path(self.config['template_config'])))
            c.update(expected_deployment=base['current_deployment'],origin=self.config['origin'],playwright_module=self.config['playwright_module'],test_python=self.config['test_python'],dependency_dir=self.config.get('dependency_dir',''),accepted_base_head=body.get('original_base') or base['head'])
            c['pilot']={'issue_id':r['identifier'],'issue_uuid':r['issue_id'],'draft_id':r['draft_id'],'revision':r['revision'],'contract_hash':r['contract_hash'],'base_head':body['base_head'],
                        'tier':body['tier'],'description':body['contract'],'branch':body['branch']}
            a=DynamicPreviewAdapter(Facade(self,r),c,self.credentials);self.adapters[key]=a
        return self.adapters[key]
    def tick(self):
        self.intake.set_meta('owner_preview_worker_heartbeat',str(time.time()));self.intake.set_meta('owner_preview_worker_mode',self.config['mode_id'])
        if self.intake.meta('owner_preview_only')!='1' or self.intake.meta('owner_preview_mode')!=self.config['mode_id']:return
        self.reconcile_notifications()
        counts={x['stage']:x['n'] for x in self.intake.db.execute('SELECT stage,count(*) n FROM preview_queue WHERE user_id=? GROUP BY stage',(self.config['owner_id'],))}
        active=self.intake.db.execute('SELECT identifier,stage FROM preview_queue WHERE active=1').fetchone()
        self.intake.set_meta('delivery_status','Owner preview pilot. '+(active['identifier']+' · '+STAGES[active['stage']] if active else 'Активного delivery нет.')+f" В очереди: {counts.get('queued',0)}. Требуют Owner: {counts.get('needs_owner',0)}. Candidate/Windows/main/production и очередь Сергея выключены.")
        if self.intake.meta('paused')=='1' or self.intake.meta('delivery_paused')=='1':return
        if time.time()<getattr(self,'retry_after',0):return
        r=self.claim()
        if not r:return
        body=json.loads(r['body']);stage=r['stage']
        if stage=='revision_sync':return
        try:
            if stage in {'feedback','review','needs_owner','revision_sync','blocked'} and time.time()<self.next_poll:return
            if stage in {'feedback','review','needs_owner','revision_sync','blocked'}:self.next_poll=time.time()+10
            issue=self.issue(r)
            if issue['state']['type']=='canceled':
                deployment=self.state.operation(job_id(r),'deployment')
                if deployment and deployment['status']=='started':
                    a=self.adapter(r);a.state.allow_cancelled_reconcile=True
                    try:result=a.deploy({'id':job_id(r),'owner':r['owner'],'fence':r['fence'],'body':r['body']})
                    finally:a.state.allow_cancelled_reconcile=False
                    if not result:return
                    base=json.loads(self.intake.meta('owner_preview_base'));base.update(current_deployment=result['deployment_id'],current_head=body['source_head']);self.intake.set_meta('owner_preview_base',json.dumps(base))
                self.update(r,'cancelled',active=0);return
            if stage in {'feedback','review','needs_owner','revision_sync','blocked'}:return
            if issue['state']['type']=='completed' and stage=='queued':self.update(r,'cancelled',active=0);return
            if stage=='queued':
                base=json.loads(self.intake.meta('owner_preview_base'))
                if not body.get('deployed_head'):body['base_head']=base['head'];body['original_base']=base['head']
                body['composition']=base['composition']+[r['identifier']]
                self.update(r,'planning',body);self.sync(r,'working');return
            a=self.adapter(r);job={'id':job_id(r),'owner':r['owner'],'fence':r['fence'],'body':json.dumps(body)}
            if stage in {'planning','implementing'}:
                self.sync(r,'working')
                body.update(a.implement(job));self.update(r,'deploying',body)
            elif stage=='deploying':
                result=a.deploy(job)
                if result:body.update(result);self.update(r,'verifying',body)
            elif stage=='verifying':
                body.update(a.verify(job));body['verified_revision']=r['revision'];body['preview_url']=self.config['origin']+body.get('preview_path','/legacy?tab=about');body['review_token']=uuid.uuid4().hex
                base=json.loads(self.intake.meta('owner_preview_base'));base.update(current_deployment=body['deployment_id'],current_head=body['deployed_head']);self.intake.set_meta('owner_preview_base',json.dumps(base))
                self.sync(r,'review');self.update(r,'review',body)
                self.intake.enqueue('preview-ready:'+job_id(r),'telegram',{'chat_id':r['user_id'],'text':r['identifier']+f" · Railway r{r['revision']} готов к проверке.\n{body['preview_url']}\nHEAD {body['deployed_head']}\nСостав: "+', '.join(body['composition'])+'\nОткройте «Меню» → «Мои задачи» → карточку: «Принять на стенде» / «Нужны исправления». Candidate/Windows/main/production отключены.'})
            elif stage=='accept_requested':
                request=body['acceptance_request'];current=a.status();status,raw=a.http('/preview/identity')
                if status!=200 or json.loads(raw).get('source_head')!=request['head'] or current['latestDeployment']['id']!=request['deployment_id']:raise DeliveryBlocked('accepted_preview_no_longer_deployed')
                self.comment(r,'accepted','Принято на Railway Owner через Telegram. Preview r'+str(r['revision'])+'; HEAD '+request['head']+'.\nЭто не production и не разрешение candidate/updater/release.')
                self.sync(r,'accepted');base=json.loads(self.intake.meta('owner_preview_base'));base.update(head=request['head'],composition=body['composition']);self.intake.set_meta('owner_preview_base',json.dumps(base))
                body['accepted_at']=time.time();self.update(r,'accepted',body,active=0)
                self.intake.enqueue('preview-accepted:'+job_id(r),'telegram',{'chat_id':r['user_id'],'text':r['identifier']+' · Принято на Railway. Следующая задача может занять общий стенд. Релизные стадии выключены.'})
        except ApiError:
            self.retry_after=time.time()+10
            self.intake.set_meta('owner_preview_status','Linear временно недоступен; тот же checkpoint сохранён')
        except Exception as error:
            code=str(error) if re.fullmatch('[a-z_]+',str(error)) else 'preview_operation_failed'
            if code=='paused':return
            body['blocker']=code;body['blocked_stage']=stage;need_owner=code in {'actual_diff_requires_owner_decision','protected_or_invalid_product_path','protected_or_network_change_requires_owner'}
            if not self.update(r,'needs_owner' if need_owner else 'blocked',body,active=0 if need_owner and not body.get('deployed_head') else r['active']):return
            self.intake.enqueue('preview-blocker:'+job_id(r)+':'+code,'telegram',{'chat_id':r['user_id'],'text':r['identifier']+' · '+('Требует решения Owner: ' if need_owner else 'Остановлено: ')+code+'. Подтверждённые стадии сохранены; детали и действия в «Мои задачи».'})
    def reconcile_notifications(self):
        # Restore the report after a crash between checkpoint commit and outbox insert.
        # INSERT OR IGNORE preserves known sends and uncertain outcomes.
        for saved in self.intake.db.execute("SELECT * FROM preview_queue WHERE user_id=? AND json_extract(body,'$.mode')=?",(self.config['owner_id'],self.config['mode_id'])).fetchall():
            r=dict(saved);body=json.loads(r['body']);stage=r['stage'];key=None;text=None
            if stage=='planning':
                key='preview-start:'+job_id(r);text=r['identifier']+' · Начинаю реализацию и focused-проверки. Затем Railway; candidate/Windows/main/production выключены.'
            elif stage=='review':
                key='preview-ready:'+job_id(r);text=r['identifier']+f" · Railway r{r['revision']} готов к проверке.\n{body['preview_url']}\nHEAD {body['deployed_head']}\nСостав: "+', '.join(body['composition'])+'\nОткройте «Меню» → «Мои задачи» → карточку: «Принять на стенде» / «Нужны исправления». Candidate/Windows/main/production отключены.'
            elif stage=='accepted':
                key='preview-accepted:'+job_id(r);text=r['identifier']+' · Принято на Railway. Следующая задача может занять общий стенд. Релизные стадии выключены.'
            elif stage in {'blocked','needs_owner'} and body.get('blocker'):
                code=body['blocker'];key='preview-blocker:'+job_id(r)+':'+code;text=r['identifier']+' · '+('Требует решения Owner: ' if stage=='needs_owner' else 'Остановлено: ')+code+'. Подтверждённые стадии сохранены; детали и действия в «Мои задачи».'
            if key:self.intake.enqueue(key,'telegram',{'chat_id':r['user_id'],'text':text})
    def run(self):
        thread=threading.Thread(target=self.heartbeat,daemon=True);thread.start()
        try:
            while not self.stop.is_set():
                try:self.tick()
                except Exception:self.intake.set_meta('owner_preview_status','Ошибка проверки очереди; данные сохранены')
                self.stop.wait(2)
        finally:self.cancel();thread.join(timeout=6)
