import copy
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from scripts.sergey_intake import Store,Intake,dispatch_one,analysis_one,contract
from scripts.sergey_delivery import DeliveryStore,DeliveryBlocked
from scripts.sergey_navigation import load,render,show,transition
from scripts.sergey_preview import PreviewWorker,Facade,enqueue_created,job_id,row
from scripts.sergey_preview_executor import proposed_files,allowed
from scripts.sergey_production import ProductionRunner
from tests.test_sergey_analyst import FakeEngine,ready
from tests.test_sergey_intake import FakeTelegram


class Bot(FakeTelegram):
    def call(self,method,payload):
        self.sent.append((method,copy.deepcopy(payload)))
        return {'message_id':payload.get('message_id',1000+len(self.sent))}


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.path=Path(self.t.name)/'intake.sqlite3';self.s=Store(self.path)
        self.s.set_meta('navigation_enabled','1');self.s.set_meta('owner_preview_only','1');self.s.set_meta('owner_preview_owner','22')
        self.engine=Intake(self.s,11,22,contextual=True,menu_ui=True);self.seq=0;self.bot=Bot()
    def tearDown(self):self.s.db.close();self.t.cleanup()
    def drain(self):
        for _ in range(100):
            if not dispatch_one(self.s,self.bot,None):break
    def send(self,text):
        self.seq+=1;self.engine.process({'update_id':self.seq,'message':{'message_id':self.seq,'from':{'id':22},'chat':{'id':22,'type':'private'},'text':text}});self.drain()
    def cb(self,inner,raw=False):
        n=load(self.s,22);self.seq+=1
        self.engine.process({'update_id':self.seq,'callback_query':{'id':str(self.seq),'from':{'id':22},'data':inner if raw else f"n:{n['generation']}:{inner}",
            'message':{'message_id':n['message_id'],'chat':{'id':22,'type':'private'}}}});self.drain()
    def test_root_creation_add_back_menu_preserves_content_and_uses_one_message(self):
        self.send('Меню');root=load(self.s,22);self.assertFalse(root['stack']);self.cb('m:new');self.send('Личная задача Owner')
        before=copy.deepcopy(self.s.current(22));d=self.s.current(22);self.cb(f"u:add:{d['id']}:{d['revision']}")
        self.assertEqual(load(self.s,22)['view']['name'],'input');self.cb('m:back');self.send('Меню')
        self.assertEqual(self.s.current(22),before)
        self.cb('m:new');d=self.s.current(22);self.cb(f"u:resume:{d['id']}:{d['revision']}")
        self.assertEqual(self.s.current(22),before)
        self.assertTrue(any(method=='editMessageReplyMarkup' and p['message_id']==root['message_id'] for method,p in self.bot.sent))
        self.assertTrue(any(method=='editMessageText' for method,_ in self.bot.sent))
        self.assertEqual([b['text'] for rows in __import__('scripts.sergey_navigation',fromlist=['MENU']).MENU['keyboard'] for b in rows],['Меню'])
    def test_back_restores_list_and_then_root_without_cancelling_draft(self):
        self.send('Меню');self.cb('m:new');self.send('Материал');d=self.s.current(22);before=copy.deepcopy(d)
        self.send('Меню');self.cb('m:tasks');self.cb(f"q:card:{d['id']}:active_0")
        self.assertEqual(load(self.s,22)['view']['name'],'card');self.cb('m:back');self.assertEqual(load(self.s,22)['view']['name'],'list')
        self.cb('m:back');self.assertEqual(load(self.s,22)['view']['name'],'root');self.assertEqual(self.s.current(22),before)
    def test_stale_generation_and_raw_history_buttons_do_not_change_workflow(self):
        self.send('Меню');self.cb('m:new');self.send('Материал');d=copy.deepcopy(self.s.current(22));n=load(self.s,22)
        old=f"n:{n['generation']}:u:cancel:{d['id']}:{d['revision']}";self.send('Меню');self.cb(old,raw=True)
        self.assertEqual(self.s.current(22),d);self.cb(f"u:cancel:{d['id']}:{d['revision']}",raw=True);self.assertEqual(self.s.current(22),d)
        self.s.db.close();self.s=Store(self.path);self.engine=Intake(self.s,11,22,contextual=True,menu_ui=True)
        self.assertIsNotNone(load(self.s,22)['message_id']);self.assertEqual(self.s.current(22),d)
    def test_async_progress_does_not_replace_menu_or_list(self):
        from scripts.sergey_navigation import emit
        self.send('Меню');self.cb('m:new');self.send('Материал');d=self.s.current(22);self.send('Меню');before=copy.deepcopy(load(self.s,22))
        emit(self.s,22,'async-result','Анализ готов',[[{'text':'Создать задачу','callback_data':'create:'+d['id']+':'+str(d['revision'])}]],async_draft=d)
        self.drain();self.assertEqual(load(self.s,22),before)
        self.assertEqual(self.bot.sent[-1][0],'sendMessage');self.assertNotIn('reply_markup',self.bot.sent[-1][1])
    def test_old_production_approval_is_blocked_even_when_wrapped(self):
        self.send('Меню');self.cb('prod:yes:old');self.assertFalse(self.s.meta('production_approval'))
        fake=type('Never',(),{'local':lambda *a: (_ for _ in ()).throw(AssertionError('production mutation'))})()
        runner=ProductionRunner(DeliveryStore(Path(self.t.name)/'delivery.sqlite3'),self.s,fake,{})
        self.assertFalse(runner.tick({'id':'old-job'}));runner.state.db.close()


class Linear:
    def __init__(self):self.issues={};self.updates=[];self.comments=[]
    def add(self,d,p):
        self.issues[d['id']]={'id':str(uuid.UUID(d['id'])),'identifier':'ALE-'+str(800+len(self.issues)),'description':p['description'],'title':p['title'],
            'state':{'id':'queue','type':'backlog','name':'Backlog'},'creator':{'id':'0b34be60-67c7-46a0-925c-607afdc3180d'},'team':{'id':'cc0f1982-1457-48af-967b-d56a672ee8ae'},'project':{'id':'d7ae5979-8aa5-4bc9-a6ee-479c898e15c2'}}
        return {**self.issues[d['id']],'url':'https://linear.app/test/'+d['id']}
    def call(self,q,v):
        target=next(x for x in self.issues.values() if x['id']==v['id'])
        if 'commentCreate' in q:self.comments.append({'id':str(len(self.comments)),'body':v['b']});return {'commentCreate':{'success':True,'comment':self.comments[-1]}}
        if 'comments{' in q:return {'issue':{'comments':{'nodes':self.comments}}}
        if 'issueUpdate' in q:
            self.updates.append(copy.deepcopy(v))
            if 's' in v:target['state']={'id':v['s'],'type':'completed' if v['s']=='accepted' else 'started','name':v['s']}
            if 'd' in v:target['description']=v['d'];target['title']=v['t']
            return {'issueUpdate':{'success':True}}
        return {'issue':copy.deepcopy(target)}
    def find(self,identifier):return next(x for x in self.issues.values() if x['id']==identifier)


class Adapter:
    def __init__(self,worker,r):self.worker=worker;self.r=r;self.calls=[]
    def implement(self,job):self.calls.append('implement');return {'source_head':'head'+self.r['draft_id'][:4]+str(self.r['revision']),'worktree':'TEMP','url':'https://preview.invalid'}
    def deploy(self,job):self.calls.append('deploy');return {'deployment_id':'dep'+self.r['draft_id'][:4]+str(self.r['revision'])}
    def verify(self,job):self.calls.append('verify');b=json.loads(job['body']);return {'deployed_head':b['source_head']}
    def status(self):return {'latestDeployment':{'id':json.loads(row(self.worker.intake,self.r['draft_id'])['body'])['deployment_id']}}
    def http(self,path):return 200,json.dumps({'source_head':json.loads(row(self.worker.intake,self.r['draft_id'])['body'])['deployed_head']}).encode()
    def cancel(self):pass


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.root=Path(self.t.name);self.s=Store(self.root/'intake.sqlite3');self.s.set_meta('owner_preview_mode','nonce');self.s.set_meta('owner_preview_owner','22');self.s.set_meta('owner_preview_only','1')
        self.s.set_meta('owner_preview_base',json.dumps({'head':'base','current_deployment':'seed','composition':['ALE-533']}))
        self.w=PreviewWorker.__new__(PreviewWorker);self.w.intake=self.s;self.w.state=DeliveryStore(self.root/'delivery.sqlite3');self.w.owner='worker1';self.w.next_poll=0
        self.w.config={'owner_id':22,'mode_id':'nonce','origin':'https://preview.invalid','linear_states':{x:x for x in ['queue','working','review','accepted']}};self.w.linear=Linear();self.w.adapters={};self.action_seq=500
        def adapter(r):
            key=job_id(r)
            if key not in self.w.adapters:self.w.adapters[key]=Adapter(self.w,r)
            return self.w.adapters[key]
        self.w.adapter=adapter
    def tearDown(self):self.s.db.close();self.w.state.db.close();self.t.cleanup()
    def new(self,tier='T1',test=False,user=22):
        d={'id':uuid.uuid4().hex,'user_id':user,'role':'owner','ui_version':1,'owner_preview_mode':'nonce','confirmation_update':42,'analyst_transfer_update':41,'description_finished_update':40,
            'state':'created','revision':3,'tier':tier,'tier_reason':'TEMP','test_only':test,'request':'Synthetic TEMP specification','sources':[{'message_id':1,'update_id':1,'text':'TEST/ALE-528' if test else 'TEMP isolated requirement'}],
            'answers':{'screen':'help','actual':'old','expected':'new','frozen':'rest','acceptance':'read','surface':'только документация'}}
        self.s.save(d);p=contract(d);result=self.w.linear.add(d,p);enqueue_created(self.s,d,p,result);return d
    def to_review(self,d):
        for _ in range(5):self.w.next_poll=0;self.w.tick()
        self.assertEqual(row(self.s,d['id'])['stage'],'review')
    def action(self,d,action):
        self.action_seq+=1;r=row(self.s,d['id']);token=json.loads(r['body'])['review_token'];engine=Intake(self.s,11,22,contextual=True,menu_ui=True)
        engine.process({'update_id':self.action_seq,'callback_query':{'id':'x','from':{'id':22},'data':'p:'+action+':'+token,'message':{'message_id':999,'chat':{'id':22,'type':'private'}}}})
    def test_several_tasks_one_active_review_holds_and_accept_preserves_base(self):
        a=self.new();b=self.new('T2');c=self.new('T3');self.to_review(a)
        self.assertEqual(row(self.s,b['id'])['stage'],'queued');self.assertEqual(row(self.s,c['id'])['stage'],'needs_owner')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM preview_queue WHERE active=1').fetchone()[0],1)
        self.action(a,'accept');self.w.tick();self.assertEqual(row(self.s,a['id'])['stage'],'accepted')
        accepted=json.loads(self.s.meta('owner_preview_base'))['head'];self.w.tick();self.assertEqual(json.loads(row(self.s,b['id'])['body'])['base_head'],accepted)
        self.assertIn(self.w.linear.issues[a['id']]['identifier'],json.loads(row(self.s,b['id'])['body'])['composition'])
    def test_test_foreign_and_historical_sources_never_enter_queue(self):
        a=self.new(test=True);b=self.new(user=11);self.assertIsNone(row(self.s,a['id']));self.assertIsNone(row(self.s,b['id']))
        d=self.new();self.s.db.execute("UPDATE preview_queue SET stage='cancelled' WHERE draft_id=?",(d['id'],));self.w.tick();self.assertEqual(row(self.s,d['id'])['stage'],'cancelled')
    def test_corrections_keep_issue_branch_and_block_other_deployment(self):
        a=self.new();b=self.new();self.to_review(a);old=row(self.s,a['id']);branch=json.loads(old['body'])['branch'];self.action(a,'fix')
        self.assertEqual(row(self.s,a['id'])['stage'],'feedback');self.w.tick();self.assertEqual(row(self.s,b['id'])['stage'],'queued')
        self.assertEqual(self.s.current(22)['id'],a['id']);self.assertEqual(self.s.current(22)['feedback_for'],a['id']);self.assertIsNone(self.s.current(22)['analyst_transfer_update'])
        self.assertEqual(json.loads(row(self.s,a['id'])['body'])['branch'],branch)

    def test_full_feedback_confirmation_updates_same_linear_issue_and_new_preview_revision(self):
        a=self.new();self.to_review(a);original_issue=row(self.s,a['id'])['issue_id'];branch=json.loads(row(self.s,a['id'])['body'])['branch']
        self.action(a,'fix');engine=Intake(self.s,11,22,contextual=True,menu_ui=True);seq=1000
        def send(text):
            nonlocal seq
            seq+=1;engine.process({'update_id':seq,'message':{'message_id':seq,'from':{'id':22},'chat':{'id':22,'type':'private'},'text':text}})
        def callback(action):
            nonlocal seq
            seq+=1;d=self.s.current(22);engine.process({'update_id':seq,'callback_query':{'id':str(seq),'from':{'id':22},'message':{'message_id':seq,'chat':{'id':22,'type':'private'}},'data':f"u:{action}:{d['id']}:{d['revision']}"}})
        send('Доработать только документацию; остальное сохранить.');callback('finish');callback('send');analysis_one(self.s,FakeEngine())
        d=self.s.current(22);seq+=1;engine.process({'update_id':seq,'callback_query':{'id':str(seq),'from':{'id':22},'message':{'message_id':seq,'chat':{'id':22,'type':'private'}},'data':f"create:{d['id']}:{d['revision']}"}})
        bot=Bot()
        for _ in range(100):
            if not dispatch_one(self.s,bot,self.w.linear):break
        r=row(self.s,a['id']);self.assertEqual(r['revision'],2);self.assertEqual(r['issue_id'],original_issue);self.assertEqual(json.loads(r['body'])['branch'],branch)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM outbox WHERE kind='linear'").fetchone()[0],0)
        self.to_review(a);self.assertEqual(row(self.s,a['id'])['revision'],2)

    def test_cancel_feedback_does_not_cancel_existing_task_or_drop_other_draft(self):
        a=self.new();self.to_review(a);other={'id':uuid.uuid4().hex,'user_id':22,'role':'owner','state':'collecting','request':'other','answers':{},'sources':[],'revision':1,'ui_version':1}
        self.s.save(other);self.s.set_meta('current:22',other['id']);self.action(a,'fix')
        engine=Intake(self.s,11,22,contextual=True,menu_ui=True);engine.process({'update_id':999,'message':{'message_id':999,'from':{'id':22},'chat':{'id':22,'type':'private'},'text':'/cancel'}})
        self.assertEqual(row(self.s,a['id'])['stage'],'review');self.assertEqual(self.s.current(22)['id'],other['id']);self.assertEqual(self.s.current(22)['sources'],[])

    def test_restart_fences_old_worker_and_does_not_claim_second_job(self):
        a=self.new();b=self.new();first=self.w.claim();self.assertIsNotNone(first)
        self.w.owner='worker2';self.assertIsNone(self.w.claim());self.s.db.execute('UPDATE preview_queue SET lease_until=0 WHERE draft_id=?',(a['id'],))
        second=self.w.claim();self.assertGreater(second['fence'],first['fence']);self.assertEqual(second['draft_id'],a['id'])
        old=Facade(self.w,first)
        with self.assertRaises(DeliveryBlocked):old.guard({'fence':first['fence']})
    def test_cancelled_linear_issue_is_skipped_without_implementation(self):
        a=self.new();self.w.linear.issues[a['id']]['state']['type']='canceled';self.w.tick();self.assertEqual(row(self.s,a['id'])['stage'],'cancelled');self.assertEqual(self.w.adapters,{})
    def test_restart_recovers_checkpoint_report_without_repeating_delivery_or_uncertain_send(self):
        a=self.new();self.to_review(a);key='preview-ready:'+job_id(row(self.s,a['id']))
        calls=list(self.w.adapters[job_id(row(self.s,a['id']))].calls)
        self.s.db.execute('DELETE FROM outbox WHERE key=?',(key,));self.w.reconcile_notifications()
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM outbox WHERE key=?',(key,)).fetchone()[0],1)
        self.s.db.execute("UPDATE outbox SET status='uncertain' WHERE key=?",(key,));self.w.reconcile_notifications();self.w.next_poll=0;self.w.tick()
        self.assertEqual(self.s.db.execute('SELECT status FROM outbox WHERE key=?',(key,)).fetchone()[0],'uncertain')
        self.assertEqual(self.w.adapters[job_id(row(self.s,a['id']))].calls,calls)
    def test_product_path_and_actual_diff_guards_block_protected_effects(self):
        work=self.root/'source';(work/'backend/app/static').mkdir(parents=True);(work/'backend/app/static/view.js').write_text('old();')
        with self.assertRaises(DeliveryBlocked):proposed_files(work,[{'path':'backend/app/static/view.js','old':'old();','new':"fetch('https://evil.invalid');"}])
        self.assertFalse(allowed('backend/app/version.py'));self.assertFalse(allowed('scripts/sergey_production.py'))
        files,_,tier=proposed_files(work,[{'path':'backend/app/static/view.js','old':'old();','new':'render();'}]);self.assertEqual(tier,'T2')
        with self.assertRaises(DeliveryBlocked):proposed_files(work,[{'path':'backend/app/static/view.js','old':'old();','new':'UPDATE person SET fio=1'}])
