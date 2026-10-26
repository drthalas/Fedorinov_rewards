"""Focused risk checks; all SQLite writes/backups are in TemporaryDirectory."""
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json,sqlite3,time,unittest
from backend.app.config import Settings
from backend.app.services import fio_corrections as f, biography_enrichment as bio, enrichment_workflow as flow
from backend.app.services.data_operation_lock import exclusive
from backend.app.services.write_guard import WriteBlockedError

class FioTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory(prefix='ale520-TEMP-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.db=self.root/'fixture.sqlite'
  self.s=Settings(rewards_db_path=self.db,rewards_data_dir=self.root,update_backup_dir=self.root/'backups')
  with sqlite3.connect(self.db) as c:c.executescript('create table person(id integer primary key,fio text,birthday text,biography text);create table rewards(id integer,person_id integer,number text);create table logs(datetime text,action text,comment text);')
 def rows(self,records):
  with sqlite3.connect(self.db) as c:c.executemany('insert into person(id,fio,birthday,biography) values(?,?,"1918","frozen bio")',records)
 def query(self,q):
  with sqlite3.connect(self.db) as c:return c.execute(q).fetchall()
 def test_exact_pairs_context_and_unsupported_skip_entire_record(self):
  self.assertEqual(len(f.PAIRS),19)
  for a,b in zip('ABCEHKMOPTXYaceopxy','АВСЕНКМОРТХУасеорху'):
   r=f.classify({'fio':'Иван '+a+' ё- (имя)'});self.assertTrue(r['safe']);self.assertEqual(r['after']['fio'],'Иван '+b+' ё- (имя)')
  for v in ['John Smith','ACE','Иван Sидоров','Иван Iванов','Иван Ḁ','Иван sC']:
   r=f.classify({'fio':v});self.assertFalse(r['safe']);self.assertEqual(r['before'],r['after'])
  for v in [None,'','Иван Ёлкин','  -()']:self.assertIsNone(f.classify({'fio':v}))
 def test_all_records_multiple_fields_readonly_and_counts(self):
  with sqlite3.connect(self.db) as c:c.executescript('alter table person add column last_name text;alter table person add column first_name text;alter table person add column patronymic text;')
  self.rows([(i,'Ивaнов') for i in range(1,153)]+[(153,'John Smith'),(154,None)])
  with sqlite3.connect(self.db) as c:c.execute('update person set last_name="Пeтров",first_name="Олeг",patronymic="Иванович" where id=152')
  before=self.db.read_bytes();samples=[];r=f.audit(self.s,lambda phase,n,total:samples.append((n,total)))
  self.assertEqual(self.db.read_bytes(),before);self.assertEqual(r['checked'],154);self.assertEqual(r['safe_records'],152);self.assertEqual(r['skipped'],1)
  plan=f.load_audit(self.s,r['audit_token']);self.assertEqual(plan['rows'][-2]['id'],152);self.assertEqual(plan['rows'][-2]['after']['first_name'],'Олег');self.assertEqual(samples[-1],(154,154))
 def test_backup_commit_repeat_reaudit_search_and_frozen_fields(self):
  self.rows([(1,'Cидоров Пeтр'),(2,'Иван Иванов')]);before=self.query('select id,birthday,biography from person')
  a=f.audit(self.s);op='a'*64;result=f.apply(self.s,a['audit_token'],op)
  self.assertEqual(self.query('select fio from person where id=1'),[('Сидоров Петр',)])
  self.assertEqual(self.query("select id from person where fio like 'Сидоров%'"),[(1,)])
  self.assertEqual(self.query('select id,birthday,biography from person'),before);self.assertEqual(result['characters'],2)
  self.assertEqual(f.apply(self.s,a['audit_token'],op),result);self.assertEqual(self.query('select count(*) from logs'),[(1,)])
  with sqlite3.connect(result['backup']['path']) as c:self.assertEqual(c.execute('select fio from person where id=1').fetchone()[0],'Cидоров Пeтр')
  a=f.audit(self.s);self.assertEqual((a['latin_records'],a['safe_records']),(0,0))
 def test_backup_failure_stale_and_late_change_are_no_write(self):
  self.rows([(1,'Ивaнов')]);a=f.audit(self.s);before=self.db.read_bytes()
  with patch.object(f,'verified_backup',side_effect=OSError('TEMP backup denied')):
   with self.assertRaises(bio.ValidationError):f.apply(self.s,a['audit_token'],'b'*64)
  self.assertEqual(self.db.read_bytes(),before)
  with sqlite3.connect(self.db) as c:c.execute('insert into person(id,fio) values(2,"Новый")')
  with self.assertRaises(bio.ValidationError):f.apply(self.s,a['audit_token'],'c'*64)
  self.assertEqual(self.query('select fio from person where id=1'),[('Ивaнов',)])
  a=f.audit(self.s);original=f.verified_backup
  def late(*args):
   r=original(*args)
   with sqlite3.connect(self.db) as c:c.execute('update person set fio="Другая правка" where id=1')
   return r
  with patch.object(f,'verified_backup',side_effect=late):
   with self.assertRaises(bio.ValidationError):f.apply(self.s,a['audit_token'],'d'*64)
  self.assertEqual(self.query('select fio from person where id=1'),[('Другая правка',)])
 def test_atomic_rollback_and_shared_import_lock(self):
  self.rows([(1,'Ивaнов'),(2,'Cергеев')]);a=f.audit(self.s)
  with sqlite3.connect(self.db) as c:c.executescript("create trigger fail_second before update on person when old.id=2 begin select raise(abort,'TEMP late failure');end;")
  before=self.query('select fio from person order by id')
  with self.assertRaises(sqlite3.IntegrityError):f.apply(self.s,a['audit_token'],'e'*64)
  self.assertEqual(self.query('select fio from person order by id'),before);self.assertEqual(self.query('select count(*) from logs'),[(0,)])
  with exclusive(self.s):
   with self.assertRaises(WriteBlockedError):f.apply(self.s,a['audit_token'],'f'*64)
   with self.assertRaises(WriteBlockedError):flow.commit_import(self.s,'f'*64)
 def test_lost_start_response_recovers_committed_receipt_without_audit_file(self):
  self.rows([(1,'Cидоров')]);a=f.audit(self.s);request='lost-response-00001';op=bio._sign(self.s,'fio-job-v1:apply:'+request)
  f.apply(self.s,a['audit_token'],op)
  bio._save(self.s,op,{'created':time.time(),'state':'running','kind':'apply','audit_token':a['audit_token'],'job_id':op,'phase':'Сохранение','percent':99,'done':1,'total':1})
  (bio._state(self.s)/(a['audit_token']+'.json')).unlink()
  state=f.CorrectionJobs().start(self.s,'apply',request,a['audit_token'])
  self.assertEqual(state['state'],'succeeded');self.assertEqual(state['result']['records'],1)
  self.assertEqual(self.query('select count(*) from logs'),[(1,)])
  with self.assertRaises(WriteBlockedError):f.apply(self.s.model_copy(update={'read_only':True}),a['audit_token'],op)

 def test_jobs_real_progress_duplicate_restart_receipt_and_tamper(self):
  self.rows([(i,'Ивaнов') for i in range(1,802)])
  jobs=f.CorrectionJobs();j=jobs.start(self.s,'audit','audit-request-00001')
  same=jobs.start(self.s,'audit','audit-request-00001');self.assertEqual(same['job_id'],j['job_id'])
  deadline=time.monotonic()+10
  while (r:=jobs.status(self.s,j['job_id']))['state'] in {'queued','running'}:
   self.assertLess(time.monotonic(),deadline);self.assertLess(r['percent'],100);time.sleep(.005)
  self.assertEqual(r['state'],'succeeded');self.assertEqual(r['result']['checked'],801)
  token=r['result']['audit_token'];plan=bio.load_preview(self.s,token);plan['rows'][0]['after']['fio']='Подмена';bio._save(self.s,token,plan)
  with self.assertRaises(bio.ValidationError):f.apply(self.s,token,'1'*64)
  a=f.audit(self.s);op='2'*64;event=f.apply(self.s,a['audit_token'],op)
  bio._save(self.s,op,{'created':time.time(),'state':'running','kind':'apply','job_id':op,'phase':'Сохранение','percent':99,'done':800,'total':801})
  from concurrent.futures import Future
  recovering=f.CorrectionJobs();recovering.futures[op]=Future();recovering.futures[op].set_result(None)
  recovered=recovering.status(self.s,op);self.assertEqual(recovered['state'],'succeeded');self.assertEqual(recovered['result']['records'],801)
  bio._save(self.s,'3'*64,{'created':time.time(),'state':'running','kind':'audit','job_id':'3'*64,'phase':'Аудит','percent':50,'done':400,'total':801})
  self.assertEqual(f.CorrectionJobs().status(self.s,'3'*64)['state'],'interrupted')

if __name__=='__main__':unittest.main()
