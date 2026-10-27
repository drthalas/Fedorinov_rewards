"""Only changed operation states, transaction progress and committed summaries."""
from contextlib import closing
from concurrent.futures import Future
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path
import json,sqlite3,threading,time,unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import biography_enrichment as b,enrichment_workflow as f,enrichment_import_jobs as jobs_module,manual_import_review as manual
from tests import test_ale513_workspace as fixture

class ImportStateTests(unittest.TestCase):
 setUp=fixture.WorkspaceTests.setUp
 execute=fixture.WorkspaceTests.execute
 query=fixture.WorkspaceTests.query
 mixed=fixture.WorkspaceTests.mixed
 def plan(self):
  token=self.mixed();view=f.workspace(self.settings,token);op,plan=f.prepare_workspace(self.settings,token,view['revision'],[]);return token,op,plan
 def test_real_row_progress_commit_boundary_and_actual_summary(self):
  token,op,plan=self.plan();jobs=jobs_module.ImportJobs();entered=threading.Event();release=threading.Event();original=manual.apply_plan;calls=0
  def controlled(*args,**kwargs):
   nonlocal calls
   calls+=1
   if calls==2:entered.set();self.assertTrue(release.wait(5))
   return original(*args,**kwargs)
  with patch.object(manual,'apply_plan',side_effect=controlled):
   first=jobs.start(self.settings,op);self.assertEqual(first['state'],'queued');self.assertTrue(entered.wait(3))
   status=jobs.status(self.settings,op);self.assertEqual((status['done'],status['total']),(1,6));self.assertLess(status['percent'],100)
   self.assertEqual(self.query('select count(*) from person where biography is not null'),[(0,)])
   self.assertEqual(jobs.start(self.settings,op)['operation'],op)
   release.set();jobs.futures[jobs._key(self.settings,op)].result(5)
  status=jobs.status(self.settings,op);self.assertEqual(status['state'],'succeeded');self.assertEqual(status['percent'],100)
  self.assertEqual({k:status['result'][k] for k in ['saved','biographies','years','skipped']},{'saved':6,'biographies':6,'years':2,'skipped':2})
  self.assertEqual(self.query("select count(*) from logs where action like 'enrichment_import:%'"),[(1,)])
  self.assertEqual(jobs.start(self.settings,op)['result'],status['result'])
 def test_failed_job_is_not_success_and_rolls_back(self):
  token,op,plan=self.plan();jobs=jobs_module.ImportJobs()
  self.execute("create trigger fail_audit before insert on logs begin select raise(abort,'TEMP failure');end")
  jobs.start(self.settings,op);jobs.futures[jobs._key(self.settings,op)].result(5)
  status=jobs.status(self.settings,op);self.assertEqual(status['state'],'failed');self.assertLess(status['percent'],100)
  self.assertEqual(self.query('select count(*) from person where biography is not null'),[(0,)])
 def test_reconnect_uses_receipt_and_unknown_private_success_is_not_trusted(self):
  token,op,plan=self.plan();jobs=jobs_module.ImportJobs();key=jobs._key(self.settings,op)
  b._save(self.settings,key,{'created':time.time(),'state':'succeeded','operation':op,'percent':100,'done':6,'total':6})
  self.assertEqual(jobs.status(self.settings,op)['state'],'interrupted');self.assertLess(jobs.status(self.settings,op)['percent'],100)
  result=f.commit_import(self.settings,op)
  status=jobs_module.ImportJobs().status(self.settings,op);self.assertEqual(status['state'],'succeeded');self.assertEqual(status['result']['saved'],6)
  self.assertEqual(jobs_module.ImportJobs().start(self.settings,op)['state'],'succeeded')
 def test_success_server_restore_and_list_never_resubmit(self):
  token,op,plan=self.plan();f.commit_import(self.settings,op)
  with TestClient(app) as client:
   html=client.get('/data-maintenance/enrichment/biographies/preview/'+token).text
   self.assertIn('data-import-success',html);self.assertIn('Импорт завершён',html)
   self.assertIn('<div data-import-preview hidden>',html)
   self.assertNotIn('Файл проверен. Решения будут записаны',html)
   self.assertIn('Биографий добавлено',html)
   self.assertEqual(client.get('/data-maintenance/enrichment/biographies/import/operations/'+op).json()['result']['years'],2)
   self.assertEqual(client.post('/data-maintenance/enrichment/biographies/import/start',data={'operation':op}).status_code,409)
   again,_=b.preview(self.settings,self.content)
   self.assertTrue(f.completed_preview(self.settings,again,f.workspace(self.settings,again))['already_done'])

if __name__=='__main__':unittest.main()
