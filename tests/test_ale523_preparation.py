"""Focused ALE-523 preparation lifecycle; genuine signed TEMP XLSX/SQLite only."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
import json,sqlite3,time,unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import biography_enrichment as b,enrichment_workflow as f,enrichment_import_jobs as j
from backend.app.routers import biography_enrichment as router
from tests import test_ale522_stale_skip as stale_fixture

class PreparationTests(unittest.TestCase):
    setUp=stale_fixture.StaleSkipTests.setUp
    execute=stale_fixture.StaleSkipTests.execute
    query=stale_fixture.StaleSkipTests.query
    content=stale_fixture.StaleSkipTests.content
    setup_people=stale_fixture.StaleSkipTests.setup_people
    def jobs(self):
        life=j.ImportJobs();self.addCleanup(life.pool.shutdown,wait=True)
        return j.PreparationJobs(life)
    def source(self):
        token,_=b.preview(self.settings,self.setup_people());return token,f.workspace(self.settings,token)['revision']
    def start(self,jobs,token,revision,request='1'*32,render=router._render_prepared):
        return jobs.start(self.settings,token,revision,request,render)
    def finish(self,jobs,item):
        jobs.futures[item['job']].result(timeout=10)
        return jobs.status(self.settings,item['job'])
    def test_delayed_progress_coalesces_double_request_and_other_request_read_only(self):
        token,rev=self.source();jobs=self.jobs();entered=Event();release=Event();original=f.prepare_workspace;before=self.db.read_bytes()
        def delayed(*a,progress,**kw):
            def observe(phase,done,total):
                progress(phase,done,total)
                if phase=='Проверяем карточки…' and done==1:entered.set();release.wait(5)
            return original(*a,progress=observe,**kw)
        with patch.object(f,'prepare_workspace',side_effect=delayed) as calls:
            item=self.start(jobs,token,rev);self.assertTrue(entered.wait(3))
            status=jobs.status(self.settings,item['job']);self.assertEqual((status['state'],status['done'],status['total']),('running',1,3));self.assertLess(status['percent'],100)
            self.assertEqual(self.start(jobs,token,rev)['job'],item['job'])
            self.assertEqual(self.start(jobs,token,rev,'2'*32)['job'],item['job']);self.assertEqual(calls.call_count,1)
            self.assertEqual(self.db.read_bytes(),before)
            (self.root/(item['job']+'.json')).unlink()
            self.assertEqual(self.start(jobs,token,rev)['state'],'unknown')
            self.assertEqual(self.start(jobs,token,rev,'3'*32)['job'],item['job']);self.assertEqual(calls.call_count,1)
            release.set();done=self.finish(jobs,item)
        self.assertEqual(done['state'],'succeeded');self.assertEqual(done['percent'],100)
        html=jobs.result(self.settings,item['job']);self.assertIn('Подтвердите импорт',html);self.assertIn('type="checkbox"',html)
        self.assertEqual(self.db.read_bytes(),before);self.assertEqual(self.start(jobs,token,rev)['job'],item['job'])
        self.assertEqual(self.start(jobs,token,rev,'2'*32)['job'],item['job'])
    def test_100_waits_for_render_and_result_persistence_then_commit_idempotent(self):
        token,rev=self.source();jobs=self.jobs();entered=Event();release=Event();before=self.db.read_bytes()
        def render(plan,op):entered.set();release.wait(5);return router._render_prepared(plan,op)
        item=self.start(jobs,token,rev,render=render);self.assertTrue(entered.wait(3))
        status=jobs.status(self.settings,item['job']);self.assertEqual(status['phase'],'Подготавливаем сводку…');self.assertIsNone(status['percent'])
        with self.assertRaises(b.ValidationError):jobs.result(self.settings,item['job'])
        self.assertEqual(self.db.read_bytes(),before);release.set();done=self.finish(jobs,item)
        result=f.commit_import(self.settings,done['operation']);self.assertEqual(result['saved'],3)
        self.assertEqual(f.commit_import(self.settings,done['operation']),result);self.assertEqual(self.query("select count(*) from logs where action like 'enrichment_import:%'"),[(1,)])
    def test_stale_before_prepare_skips_and_current_bio_after_prepare_rolls_back(self):
        token,rev=self.source();jobs=self.jobs();self.execute("update person set fio='Правка Owner' where id=2")
        before=self.db.read_bytes();done=self.finish(jobs,self.start(jobs,token,rev));plan=b.load_preview(self.settings,done['operation'])
        self.assertEqual(plan['summary']['stale_skipped'],1);self.assertEqual(len(plan['rows']),2);self.assertTrue(plan['summary']['refreshed']);self.assertEqual(self.db.read_bytes(),before)
        self.execute("update person set biography='Ручная BIO' where id=3")
        with self.assertRaises(b.ValidationError):f.commit_import(self.settings,done['operation'])
        self.assertEqual(self.query('select count(*) from logs'),[(0,)]);self.assertEqual(self.query('select biography from person where id=1'),[(None,)])
    def test_hmac_and_protected_guards_are_fatal_even_with_stale(self):
        raw=self.setup_people();entries=b.read_rows(raw);self.execute("update person set fio='Правка Owner' where id=1");jobs=self.jobs()
        for field,value in [('snapshot_signature','0'*64),('ФИО','Подмена')]:
            rows=[dict(e['values']) for e in entries];rows[0][field]=value
            token,_=b.preview(self.settings,b._workbook(b.HEADERS,[[v.get(h,'') for h in b.HEADERS] for v in rows]));rev=f.workspace(self.settings,token)['revision'];before=self.db.read_bytes()
            done=self.finish(jobs,self.start(jobs,token,rev));self.assertEqual(done['state'],'failed');self.assertIn('выгруз',done['error']);self.assertNotIn('operation',done if done.get('operation') else {})
            self.assertEqual(self.db.read_bytes(),before)
    def test_server_failure_known_retry_new_request_preserves_file(self):
        token,rev=self.source();jobs=self.jobs();before=self.db.read_bytes()
        with patch.object(f,'prepare_workspace',side_effect=RuntimeError('/private/secret/token')):
            item=self.start(jobs,token,rev);done=self.finish(jobs,item)
        self.assertEqual(done['state'],'failed');self.assertNotIn('/private',done['error']);self.assertIn('Повторите',done['error'])
        self.assertEqual(self.start(jobs,token,rev)['state'],'failed')
        retry=self.start(jobs,token,rev,'2'*32);self.assertNotEqual(retry['job'],item['job']);self.assertEqual(self.finish(jobs,retry)['state'],'succeeded')
        self.assertEqual(len(b.load_preview(self.settings,token)['rows']),3);self.assertEqual(self.db.read_bytes(),before)
    def test_database_errors_and_render_exception_safe_no_success(self):
        token,rev=self.source();jobs=self.jobs();before=self.db.read_bytes()
        for index,exc in enumerate([sqlite3.OperationalError('database is locked'),sqlite3.OperationalError('unable to open /private/db'),OSError('/private/file'),b.ValidationError('Карточка изменилась после проверки. Ничего не записано.')]):
            with patch.object(f,'prepare_workspace',side_effect=exc):
                done=self.finish(jobs,self.start(jobs,token,rev,str(index)*32))
            self.assertEqual(done['state'],'failed');self.assertNotIn('/private',done['error']);self.assertIn('запис',done['error'])
        def render(*a):raise RuntimeError('secret')
        done=self.finish(jobs,self.start(jobs,token,rev,'f'*32,render));self.assertEqual(done['state'],'failed');self.assertIsNone(done['percent']);self.assertEqual(self.db.read_bytes(),before)
    def test_restart_missing_status_and_corrupt_result_never_succeed_silently(self):
        token,rev=self.source();jobs=self.jobs();done=self.finish(jobs,self.start(jobs,token,rev));key=done['job'];before=self.db.read_bytes()
        fresh=self.jobs();self.assertEqual(fresh.status(self.settings,key)['state'],'succeeded');self.assertIn('Подтвердите',fresh.result(self.settings,key))
        self.assertEqual(fresh.status(self.settings,'0'*64)['state'],'unknown')
        resultkey=jobs._key(self.settings,'result:'+key);record=b.load_preview(self.settings,resultkey);record['html']='Подмена';b._save(self.settings,resultkey,record)
        with self.assertRaises(b.ValidationError):fresh.result(self.settings,key)
        item=jobs._load(self.settings,key);item.update(state='running',percent=50);jobs._save(self.settings,key,item)
        self.assertEqual(fresh.status(self.settings,key)['state'],'interrupted');self.assertEqual(self.db.read_bytes(),before)
    def test_bounded_workers_reject_third_workspace_without_writes(self):
        raw=self.setup_people();jobs=self.jobs();entered=Event();release=Event();original=f.prepare_workspace;before=self.db.read_bytes()
        def delayed(*a,**kw):entered.set();release.wait(5);return original(*a,**kw)
        with patch.object(f,'prepare_workspace',side_effect=delayed):
            items=[]
            for n in range(2):
                token,_=b.preview(self.settings,raw);rev=f.workspace(self.settings,token)['revision'];items.append(self.start(jobs,token,rev))
            self.assertTrue(entered.wait(3));token,_=b.preview(self.settings,raw);rev=f.workspace(self.settings,token)['revision']
            try:
                with self.assertRaisesRegex(b.ValidationError,'занят'):self.start(jobs,token,rev)
                self.assertEqual(len(jobs.futures),2);self.assertEqual(self.db.read_bytes(),before)
            finally:release.set()
            for item in items:self.assertEqual(self.finish(jobs,item)['state'],'succeeded')
    def test_routes_origin_status_failure_and_explicit_final_confirmation(self):
        token,rev=self.source();jobs=self.jobs();before=self.db.read_bytes()
        with patch.object(router.import_jobs,'preparations',jobs),TestClient(app) as client:
            data={'revision':rev,'request_id':'1'*32}
            self.assertEqual(client.post(router.BASE+'/workspace/'+token+'/prepare',data=data,headers={'origin':'http://evil.invalid'}).status_code,403)
            item=client.post(router.BASE+'/workspace/'+token+'/prepare',data=data).json();done=self.finish(jobs,item)
            self.assertEqual(client.get(router.BASE+'/prepare/operations/'+item['job']).json()['state'],'succeeded')
            self.assertEqual(client.get(router.BASE+'/prepare/operations/'+item['job']+'/result').status_code,200)
            with patch.object(jobs,'status',side_effect=OSError('privatepath')):
                response=client.get(router.BASE+'/prepare/operations/'+item['job']);self.assertEqual(response.status_code,503);self.assertNotIn('privatepath',response.text)
            self.assertEqual(client.post(router.BASE+'/import/start',data={'operation':done['operation']}).status_code,409)
        self.assertEqual(self.db.read_bytes(),before)
    def test_shared_read_snapshot_keeps_source_fio_year_and_one_preview_load(self):
        raw=self.setup_people();entries=b.read_rows(raw);entries[0]['values']['Год в карточке']='1930'
        token,_=b.preview(self.settings,b._workbook(b.HEADERS,[[e['values'].get(h,'') for h in b.HEADERS] for e in entries]));rev=f.workspace(self.settings,token)['revision'];phases=[];before=self.db.read_bytes()
        with patch.object(b,'load_preview',wraps=b.load_preview) as load,patch.object(b,'_connection',wraps=b._connection) as connections:
            op,plan=f.prepare_workspace(self.settings,token,rev,[],progress=lambda *x:phases.append(x))
        self.assertEqual(load.call_count,1);self.assertEqual(connections.call_count,1)
        self.assertIn(('Проверяем карточки…',3,3),phases);self.assertIn(('Готовим планы строк…',3,3),phases)
        self.assertEqual(plan['summary']['fields']['fio'],2);self.assertEqual(plan['summary']['fields']['birthday'],1);self.assertEqual(self.db.read_bytes(),before)
        result=f.commit_import(self.settings,op);self.assertEqual((result['names'],result['years']),(2,1))

if __name__=='__main__':unittest.main()
