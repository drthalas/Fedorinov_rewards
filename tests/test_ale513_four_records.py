"""Portable TEMP fixtures reproduce the four exported records, not REAL writes."""
from contextlib import closing
from io import BytesIO
import sqlite3,unittest
from openpyxl import load_workbook
from tests import test_ale513_manual_import_review as fixture
from backend.app.services import biography_enrichment as b,enrichment_workflow as f

class FourRecordsTests(unittest.TestCase):
 setUp=fixture.ManualReviewTests.setUp
 execute=fixture.ManualReviewTests.execute
 query=fixture.ManualReviewTests.query
 def test_original_handoff_gaps_and_compatible_evidence_copy(self):
  self.execute("delete from rewards;delete from person;update guide_lev_3 set name='Герой Советского Союза II' where id=4")
  people=[(294,'Ковпак Сидор Артемович','1887',16),(321,'Ворошилов Клемент Ефремович','1881',47),(342,'Ворожейкин Арсений Васильевич','1912',28),(378,'Черняховский Иван Данилович','1906',30)]
  with closing(sqlite3.connect(self.db)) as c:
   for pid,fio,year,serial in people:
    c.execute('insert into person(id,fio,birthday,id_rank) values(?,?,?,10)',(pid,fio,year))
    c.execute('insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(?,1,2,3,4,?)',(pid,serial))
   c.commit()
  original=b.export_workbook(self.settings,'',20);w=load_workbook(BytesIO(original));s=w.active
  for row,p in enumerate(people,2):
   pid=p[0];s.cell(row,6,f'https://warheroes.ru/hero/hero.asp?Hero_id={pid}');s.cell(row,7,'Требует проверки')
   if pid in [342,378]:
    name='Арсений Васильевич Ворожейкин' if pid==342 else 'Иван Данилович Черняховский'
    year='1914' if pid==342 else '1907';s.cell(row,5,f'{name} (9 ноября {year} — 23 мая 2001) — дважды Герой Советского Союза. Награждён второй медалью «Золотая Звезда» № {p[3]}.')
  o=BytesIO();w.save(o);t,_=b.preview(self.settings,o.getvalue());v=f.workspace(self.settings,t)
  self.assertEqual(v['counts'],{'ready':2,'insufficient':2})
  self.assertTrue(all('birthday' not in r['automatic'] for r in v['buckets']['ready']))
  s.cell(2,5,'Ковпак Сидор Артемьевич — советский партизанский командир. Родился в 1887 году.')
  props=w.create_sheet(b.PROPOSALS_SHEET);props.append(['ID кавалера','ФИО в источнике','Год в источнике','Награда в источнике','Номер в источнике','Источник','Подтверждённые факты','Год подтверждён'])
  for pid,fio,year,serial in [people[0],people[2],people[3]]:
   sfio='Ковпак Сидор Артемьевич' if pid==294 else fio;syear='1914' if pid==342 else '1907' if pid==378 else year
   props.append([pid,sfio,syear,'Герой Советского Союза II',str(serial),f'https://warheroes.ru/hero/hero.asp?Hero_id={pid}',f'Полное ФИО, точное II награждение, вторая Звезда №{serial}.','нет' if pid==342 else 'да'])
  o=BytesIO();w.save(o);w.close();t,_=b.preview(self.settings,o.getvalue());v=f.workspace(self.settings,t)
  self.assertEqual(v['counts'],{'ready':3,'insufficient':1})
  original_fio=self.query('select id,fio from person order by id');op,plan=f.prepare_workspace(self.settings,t,v['revision'],[])
  self.assertEqual(plan['summary']['fields'],{'biography':3,'birthday':1,'fio':0})
  f.commit_import(self.settings,op)
  self.assertEqual(self.query('select id,fio from person order by id'),original_fio)
  self.assertEqual(self.query('select birthday from person where id=342'),[('1912',)])
  self.assertEqual(self.query('select birthday from person where id=378'),[('1907',)])
  self.assertEqual(self.query('select biography from person where id=321'),[(None,)])
