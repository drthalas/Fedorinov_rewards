"""Owner's explicit upper/lower pairs through detection, preview and write."""
from contextlib import closing
import sqlite3,unittest,re
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.routers import fio_corrections as router
from backend.app.services import fio_corrections as f
from tests import test_ale520_fio_corrections as fixture

class CaseMatrixTests(unittest.TestCase):
 setUp=fixture.FioTests.setUp
 rows=fixture.FioTests.rows
 query=fixture.FioTests.query
 def test_full_explicit_matrix_in_all_actual_name_fields(self):
  upper=list(zip('ABCEHKMOPTXY','АВСЕНКМОРТХУ'));lower=list(zip('acekopxy','асекорху'))
  self.assertEqual(set(f.PAIRS.items()),set(upper+lower));self.assertEqual(len(f.PAIRS),20)
  with sqlite3.connect(self.db) as c:c.executescript('alter table person add column last_name text;alter table person add column first_name text;alter table person add column patronymic text;')
  expected={}
  for i,(a,z) in enumerate(upper+lower,1):
   self.rows([(i,'Иван '+a+'-Ёлкин')]);expected[i]='Иван '+z+'-Ёлкин'
   with sqlite3.connect(self.db) as c:c.execute('update person set last_name=?,first_name=?,patronymic=? where id=?',('Фам'+a,'Имя'+a,'Отч'+a,i))
  self.rows([(30,'Ниkолаев'),(31,'НиKолаев'),(32,'Иван Kk Cc Oo'),(100,'Иван S'),(101,'Иван s'),(102,'Иван bC'),(103,'Иван hO'),(104,'John Smith'),(105,'Иван ZC')])
  expected.update({30:'Николаев',31:'НиКолаев',32:'Иван Кк Сс Оо'})
  audit=f.audit(self.s);plan=f.load_audit(self.s,audit['audit_token'])
  self.assertEqual(audit['safe_records'],23);self.assertEqual(audit['skipped'],6)
  for row in plan['rows']:
   if row['safe']:self.assertEqual(row['after']['fio'],expected[row['id']])
  with patch.object(router,'get_settings',return_value=self.s),TestClient(app) as client:
   response=client.get('/data-maintenance/corrections/preview/'+audit['audit_token'])
   self.assertEqual(response.status_code,200)
   marked=set(re.findall(r'<mark>(.*?)</mark>',response.text))
   self.assertTrue(set(f.PAIRS)<=marked);self.assertTrue(set(f.PAIRS.values())<=marked)
  f.apply(self.s,audit['audit_token'],'a'*64)
  for pid,text in expected.items():self.assertEqual(self.query('select fio from person where id='+str(pid)),[(text,)])
  for i,(a,z) in enumerate(upper+lower,1):self.assertEqual(self.query('select last_name,first_name,patronymic from person where id='+str(i)),[('Фам'+z,'Имя'+z,'Отч'+z)])
  self.assertEqual(self.query('select fio from person where id=102'),[('Иван bC',)])
  self.assertEqual(f.audit(self.s)['safe_records'],0)

 def test_fully_latin_supported_pairs_have_no_cyrillic_context(self):
  self.rows([(1,'Kk Cc Oo')]);a=f.audit(self.s)
  self.assertEqual((a['safe_records'],a['skipped']),(0,1))
  p=f.load_audit(self.s,a['audit_token']);self.assertEqual(p['rows'][0]['before'],p['rows'][0]['after'])
  self.assertIn('нет кириллического контекста',p['rows'][0]['reason'])

if __name__=='__main__':unittest.main()
