import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from scripts.sergey_intake import Intake,Store,analysis_one,dispatch_one,ApiError
from scripts.sergey_ui import material_one,recover_material,task_read,MENU
from tests.test_sergey_analyst import FakeEngine,ready
from tests.test_sergey_intake import FakeTelegram


class MediaEngine(FakeEngine):
    def __init__(self):super().__init__();self.parts=[];self.fail=False
    def prepare(self,d):
        self.parts.append(copy.deepcopy(d));d=copy.deepcopy(d)
        if self.fail:raise RuntimeError('transcription_failed')
        for s in d['sources']:
            s['attachment_sha256']='a'*64
            if s.get('media',{}).get('kind')!='photo':
                s['transcription']={'text':'только документация, остальное сохранить'}
                s['text']=s.get('caption','')+'\n'+s['transcription']['text']
        return d,[]


class UIFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.path=self.root/'intake.sqlite3'
        self.s=Store(self.path);self.intake=Intake(self.s,11,22,contextual=True,menu_ui=True);self.seq=0;self.engine=MediaEngine()
    def tearDown(self):self.s.db.close();self.temp.cleanup()
    def send(self,text=None,user=22,**fields):
        self.seq+=1;m={'message_id':self.seq,'from':{'id':user},'chat':{'type':'private','id':user},**fields}
        if text is not None:m['text']=text
        update={'update_id':self.seq,'message':m};self.intake.process(update);return update
    def cb(self,action,d=None,user=22):
        d=d or self.s.current(user);self.seq+=1
        update={'update_id':self.seq,'callback_query':{'id':str(self.seq),'from':{'id':user},
                'message':{'message_id':999,'chat':{'type':'private','id':user}},'data':f"u:{action}:{d['id']}:{d['revision']}"}}
        self.intake.process(update);return update
    def count(self,table,where='1=1'):return self.s.db.execute('SELECT count(*) FROM '+table+' WHERE '+where).fetchone()[0]
    def media(self):
        while material_one(self.s,self.engine):pass
    def start(self):self.send('Создать задачу')
    def reopen(self):
        self.s.db.close();self.s=Store(self.path);self.intake=Intake(self.s,11,22,contextual=True,menu_ui=True)
    def test_two_voice_text_screenshot_need_both_explicit_confirmations_and_one_issue(self):
        self.start();u=self.send(caption='TEST/ALE-528 synthetic voice',voice={'file_id':'v1','duration':3});self.intake.process(u)
        self.send(voice={'file_id':'v2','duration':3});self.send('Остальной текст сохранить');self.send(photo=[{'file_id':'png','file_size':42}])
        self.assertEqual(len(self.s.current(22)['sources']),4);self.assertEqual(self.count('analysis_jobs'),0)
        self.cb('finish');self.assertEqual(self.s.current(22)['state'],'review_wait')
        self.cb('send');self.assertEqual(self.count('analysis_jobs'),0)
        self.media();self.assertEqual(self.s.current(22)['state'],'review');self.assertEqual(self.count('analysis_jobs'),0)
        self.cb('send');self.assertEqual(self.count('analysis_jobs'),1)
        self.engine.result={**ready(),'ready':False,'questions':['Какое новое название?']};analysis_one(self.s,self.engine)
        self.send('Новое название «Награды». Только документация. Проверка: открыть и увидеть название.')
        self.engine.result=ready();analysis_one(self.s,self.engine);d=self.s.current(22)
        self.assertEqual(d['state'],'summary');self.assertEqual(d['sources'][-1]['question_round'],1)
        self.assertEqual(len(d['sources']),5)
        self.seq+=1;update={'update_id':self.seq,'callback_query':{'id':str(self.seq),'from':{'id':22},'message':{'message_id':100,'chat':{'id':22,'type':'private'}},'data':f"create:{d['id']}:{d['revision']}"}}
        self.intake.process(update);self.intake.process(update);update=copy.deepcopy(update);update['update_id']+=1;self.intake.process(update)
        self.assertEqual(self.count('outbox',"kind='linear'"),1)
        payload=json.loads(self.s.db.execute("SELECT payload FROM outbox WHERE kind='linear'").fetchone()[0]);self.assertTrue(payload['test_only']);self.assertIn('явная передача аналитику',payload['description'])
    def test_menus_new_existing_and_stale_buttons_do_not_become_requirements(self):
        self.start();self.send('Описание');self.cb('finish');old=copy.deepcopy(self.s.current(22));self.cb('add');self.send('Вторая часть')
        self.cb('send',old);self.assertEqual(self.count('analysis_jobs'),0)
        identity=self.s.current(22)['id'];self.send('Мои задачи');self.send('Создать задачу');self.send('/help')
        self.assertEqual(self.s.current(22)['id'],identity);self.assertEqual(len(self.s.current(22)['sources']),2)
        menu=[json.loads(r[0])['reply_markup'] for r in self.s.db.execute("SELECT payload FROM outbox WHERE kind='telegram'") if 'is_persistent' in json.loads(r[0]).get('reply_markup',{})]
        self.assertTrue(menu);self.assertTrue(menu[0]['is_persistent']);self.assertFalse(menu[0]['one_time_keyboard'])
    def test_media_error_retry_preserves_other_parts_and_only_retries_failed_part(self):
        self.start();self.send('TEST/ALE-528 text');self.send(voice={'file_id':'v','duration':2});self.cb('finish')
        self.engine.fail=True;material_one(self.s,self.engine)
        d=self.s.current(22);self.assertEqual(d['sources'][0]['text'],'TEST/ALE-528 text');self.assertEqual(d['sources'][1]['media_status'],'error')
        self.cb('retry');self.engine.fail=False;self.media();d=self.s.current(22)
        self.assertEqual(d['state'],'review');self.assertEqual(len(d['sources']),2);self.assertEqual(self.count('analysis_jobs'),0)
    def test_remove_failed_test_part_cannot_remove_test_execution_guard(self):
        self.start();self.send('Описание без marker');self.send(caption='TEST/ALE-528',voice={'file_id':'bad','duration':2});self.cb('finish');self.engine.fail=True;material_one(self.s,self.engine)
        d=self.s.current(22);self.cb('drop_'+str(d['sources'][1]['update_id']));self.assertTrue(self.s.current(22)['test_only']);self.assertEqual(len(self.s.current(22)['sources']),1)
    def test_restart_preserves_pending_parts_and_recovers_only_read_only_job(self):
        self.start();self.send(voice={'file_id':'v','duration':2});self.send('Текст')
        with patch.object(self.engine,'prepare',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):material_one(self.s,self.engine)
        identity=self.s.current(22)['id'];self.reopen();recover_material(self.s);self.media()
        self.assertEqual(self.s.current(22)['id'],identity);self.assertEqual(len(self.s.current(22)['sources']),2)
        self.assertEqual(self.count('analysis_jobs'),0);self.assertEqual(self.s.db.execute('SELECT attempts FROM material_jobs').fetchone()[0],2)
    def test_cancel_during_media_does_not_resurrect_or_start_analysis(self):
        self.start();self.send(voice={'file_id':'v','duration':2})
        def process(d):self.send('/cancel');return d,[]
        with patch.object(self.engine,'prepare',side_effect=process):material_one(self.s,self.engine)
        self.assertEqual(self.s.current(22)['state'],'cancelled');self.assertEqual(self.count('analysis_jobs'),0)
    def test_pause_and_allowlist_prevent_new_parts_and_analysis_transfer(self):
        self.start();self.send('Описание');self.s.set_meta('paused','1');self.send('Не сохранять');self.cb('finish')
        self.assertEqual(len(self.s.current(22)['sources']),1);self.assertEqual(self.s.current(22)['state'],'collecting')
        self.send('Создать задачу',user=99);self.assertIsNone(self.s.current(99))
    def test_failed_voice_answer_can_retry_without_losing_initial_materials(self):
        self.start();self.send('TEST/ALE-528 описание');self.cb('finish');self.cb('send');self.engine.result={**ready(),'ready':False,'questions':['Как назвать?']};analysis_one(self.s,self.engine)
        self.send(voice={'file_id':'answer','duration':2});self.engine.fail=True;material_one(self.s,self.engine)
        self.assertEqual(self.s.current(22)['state'],'answer_wait');self.cb('retry');self.engine.fail=False;self.media()
        d=self.s.current(22);self.assertEqual(d['state'],'analyzing');self.assertEqual(len(d['sources']),2);self.assertEqual(d['sources'][-1]['question_round'],1)
    def test_empty_draft_cannot_finish_or_transfer(self):
        self.start();self.cb('finish');self.cb('send');self.assertEqual(self.count('analysis_jobs'),0)

    def test_long_review_keeps_all_parts_and_expansion_is_paged_without_message_flood(self):
        from scripts.sergey_ui import material_review
        self.start()
        for n in range(4):self.send(str(n)+' '+('Длинный текст. '*250))
        self.cb('finish');d=self.s.current(22);brief=material_review(d)
        self.assertLess(len(brief),3800)
        for n in range(1,5):self.assertIn(f'{n}. text:',brief)
        self.cb('more');count=self.s.db.execute("SELECT count(*) FROM outbox WHERE key LIKE ?",(f'ui-reply:{self.seq}:%',)).fetchone()[0];self.assertEqual(count,1)
        self.cb('more_1');self.assertEqual(len(self.s.current(22)['sources']),4);self.assertEqual(self.count('analysis_jobs'),0)


class TasksTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.s=Store(Path(self.temp.name)/'intake.sqlite3');self.api_ids=[]
        self.records={}
        for n in range(10):
            ident=uuid.uuid4().hex;issue=str(uuid.UUID(ident));self.s.save({'id':ident,'user_id':22,'role':'owner','state':'created','issue_id':issue,'issue_url':'https://linear.app/test/'+str(n),'request':'Own '+str(n),'sources':[{'text':'TEST/ALE-528'}],'tier':'T1','revision':1})
            self.records[issue]={'id':issue,'identifier':'TEST-'+str(n),'title':'Own '+str(n),'url':'https://linear.app/test/'+str(n),'updatedAt':'2026-11-08T12:00:00Z','state':{'name':'Canceled' if n<3 else 'Backlog','type':'canceled' if n<3 else 'backlog'}}
        self.foreign=uuid.uuid4().hex;self.s.save({'id':self.foreign,'user_id':11,'state':'created','issue_id':str(uuid.UUID(self.foreign)),'request':'PRIVATE OTHER','sources':[],'revision':1})
    def tearDown(self):self.s.db.close();self.temp.cleanup()
    def call(self,query,variables):
        self.api_ids.extend(variables.values());return {'r'+str(n):self.records[v] for n,v in enumerate(variables.values())}
    def test_lists_paginate_and_cards_refresh_cache_without_foreign_context(self):
        api=type('API',(),{'call':lambda _,q,v:self.call(q,v)})()
        p={'user_id':22,'group':'active','page':0,'selected':None,'force':True}
        task_read(self.s,p,api,'one');msg=json.loads(self.s.db.execute("SELECT payload FROM outbox WHERE key='ui-read-result:one'").fetchone()[0]);self.assertIn('7',msg['text']);self.assertNotIn('PRIVATE OTHER',msg['text']);self.assertNotIn(str(uuid.UUID(self.foreign)),self.api_ids)
        buttons=msg['reply_markup']['inline_keyboard'];self.assertEqual(len([b for row in buttons for b in row if b.get('callback_data','').startswith('q:card:')]),5)
        own=self.s.db.execute('SELECT id FROM drafts WHERE user_id=22 LIMIT 1').fetchone()[0]
        with patch.object(api,'call',side_effect=ApiError('offline')):task_read(self.s,{**p,'selected':own,'force':True},api,'offline')
        text=json.loads(self.s.db.execute("SELECT payload FROM outbox WHERE key='ui-read-result:offline'").fetchone()[0])['text'];self.assertIn('данные могут устареть',text)
    def test_foreign_card_callback_is_rejected_before_any_linear_read(self):
        engine=Intake(self.s,11,22,contextual=True,menu_ui=True)
        engine.process({'update_id':1,'callback_query':{'id':'1','from':{'id':22},'message':{'message_id':3,'chat':{'id':22,'type':'private'}},'data':f'q:card:{self.foreign}:active_0'}})
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM outbox WHERE kind='ui_read'").fetchone()[0],0)
    def test_read_only_refresh_recovers_without_duplicate_reply(self):
        p={'user_id':22,'group':'active','page':0,'selected':None,'force':False};self.s.enqueue('read','ui_read',p);item=self.s.claim()
        api=type('API',(),{'call':lambda _,q,v:self.call(q,v)})();task_read(self.s,p,api,item['key'])
        self.s.recover();telegram=FakeTelegram();dispatch_one(self.s,telegram,api)
        self.assertEqual(self.s.db.execute("SELECT count(*) FROM outbox WHERE key='ui-read-result:read'").fetchone()[0],1)
