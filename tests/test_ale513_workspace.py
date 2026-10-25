"""Single screen staging and atomic import. SQLite/media fixtures are TEMP only."""
from contextlib import closing
from io import BytesIO
from pathlib import Path
import sqlite3
import unittest
from fastapi.testclient import TestClient
from tests import test_ale513_manual_import_review as fixtures
from backend.app.main import app
from backend.app.services import biography_enrichment as bio, enrichment_workflow as flow, manual_review_choices as choices


class WorkspaceTests(unittest.TestCase):
    setUp=fixtures.ManualReviewTests.setUp
    execute=fixtures.ManualReviewTests.execute
    query=fixtures.ManualReviewTests.query

    def mixed(self, count=7):
        self.execute("update person set birthday='1954';delete from rewards where person_id!=11095;")
        with closing(sqlite3.connect(self.db)) as c:
            for n in range(1,count+1):
                year='1945' if n in [1,3] else '1932' if n==5 else '1918'
                c.execute('insert into person(id,fio,birthday,id_rank) values(?,?,?,10)',(n,f'Тестов Человек Номер{n}',year))
                c.execute('insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(?,1,2,3,4,?)',(n,10+n))
            c.commit()
        rows=[]
        for entry in bio.read_rows(bio.export_workbook(self.settings,'',5000)):
            v=entry['values'];pid=int(v['person_id']);year=v['Год рождения']
            source_year='1930' if pid==1 else '1931' if pid==5 else year
            serial='725' if pid==11095 else str(10+pid)
            v.update(biography='Проверенная биография кавалера.',source_url=f'https://warheroes.ru/hero/hero.asp?Hero_id={pid}',status='Требует проверки',
                notes=f'Полное ФИО, точная I степень №{serial}, год {source_year} сверены с карточкой.',
                **{'ФИО в карточке':'Ермакова Мария Владимировна' if pid==11095 else v['ФИО'],
                   'Год в карточке':source_year,'Награда в карточке':'Орден Трудовой Славы I степени',
                   'Идентификация':'Личность не подтверждена' if pid==11095 else 'Подтверждена'})
            if pid==6:v.update(biography='',source_url='',notes='')
            if pid==7:v['notes']='В источнике только другая награда №999; ФИО не подтверждено.'
            rows.append([v.get(h,'') for h in bio.HEADERS])
        self.content=bio._workbook(bio.HEADERS,rows)
        return bio.preview(self.settings,self.content)[0]

    def submit(self,token,row,**values):
        d=choices.detail(self.settings,token,row)
        return flow.stage(self.settings,token,row,{'review_revision':d['revision'],**values})

    def test_buckets_and_independent_staging_no_writes_until_one_import(self):
        token=self.mixed();view=flow.workspace(self.settings,token)
        self.assertEqual(view['counts'],{'ready':4,'manual':2,'insufficient':2})
        before=self.db.read_bytes()
        year=next(r for r in view['buckets']['manual'] if str(r['person_id'])=='5')
        alias=next(r for r in view['buckets']['manual'] if str(r['person_id'])=='11095')
        op,_=self.submit(token,year['row'],birthday_choice='proposed')
        other,plan=self.submit(token,alias['row'],identity_choice='same',fio_choice='current')
        self.assertNotIn('fio',plan['writes']);self.assertIn('biography',plan['writes'])
        stages=[op,other];view=flow.workspace(self.settings,token,stages)
        self.assertEqual(view['accepted'],2)
        batch,plan=flow.prepare_workspace(self.settings,token,view['revision'],stages)
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(plan['summary']['fields'],{'biography':6,'birthday':2,'fio':0})
        with self.assertRaises(bio.ValidationError):flow.commit_review(self.settings,op)
        result=flow.commit_import(self.settings,batch)
        self.assertEqual(result['saved'],6)
        self.assertEqual(self.query('select birthday from person where id=1'),[('1930',)])
        self.assertEqual(self.query('select birthday from person where id=3'),[('1945',)])
        self.assertEqual(self.query('select birthday from person where id=5'),[('1931',)])
        self.assertEqual(self.query('select fio from person where id=11095'),[('Ермакова (Зайцева) Мария Владимировна',)])
        self.assertTrue(choices.detail(self.settings,token,alias['row'])['confirmed'])
        self.assertEqual(flow.commit_import(self.settings,batch),result)
        self.assertEqual(flow.workspace(self.settings,token)['counts'],{'ready':0,'manual':0,'insufficient':2})
        history=flow.history_view(__import__('backend.app.services.manual_import_review',fromlist=['durable_history']).durable_history(self.settings,11095))
        self.assertEqual(history[0]['fields'][0]['label'],'Принадлежность источника')

    def test_identity_decline_never_imports_source_and_rename_is_independent(self):
        token=self.mixed();v=flow.workspace(self.settings,token);row=v['buckets']['manual'][-1]['row']
        op,p=self.submit(token,row,identity_choice='different',fio_choice='proposed')
        self.assertEqual(p['writes'],[])
        # Only the rejected source decision is audited for this person.
        view=flow.workspace(self.settings,token,[op]);batch,_=flow.prepare_workspace(self.settings,token,view['revision'],[op]);flow.commit_import(self.settings,batch)
        self.assertEqual(self.query('select biography from person where id=11095'),[(None,)])
        self.assertTrue(choices.detail(self.settings,token,row)['confirmed'])

    def test_supported_rename_uses_signed_receipt_and_frozen_awards(self):
        token=self.mixed();row=flow.workspace(self.settings,token)['buckets']['manual'][-1]['row']
        op,p=self.submit(token,row,identity_choice='same',fio_choice='proposed')
        self.assertEqual(set(p['writes']),{'biography','fio'})
        view=flow.workspace(self.settings,token,[op]);batch,_=flow.prepare_workspace(self.settings,token,view['revision'],[op]);flow.commit_import(self.settings,batch)
        self.assertEqual(self.query('select fio from person where id=11095'),[('Ермакова Мария Владимировна',)])
        self.assertEqual(self.query('select number from rewards where person_id=11095'),[(725,)])
        self.assertTrue(choices.detail(self.settings,token,row)['confirmed'])

    def test_identity_and_other_year_are_independent_manual_decisions(self):
        token=self.mixed();record=bio.load_preview(self.settings,token)
        row=next(e for e in record['entries'] if e['values']['person_id']=='11095')
        row['values']['Год в карточке']='1953';row['values']['notes']='Полное ФИО, I степень №725, год1953 сверены с карточкой.';bio._save(self.settings,token,record)
        d=choices.detail(self.settings,token,row['row'])
        self.assertEqual(set(d['fields']),{'fio','birthday'})
        op,plan=self.submit(token,row['row'],identity_choice='same',fio_choice='current',birthday_choice='proposed')
        self.assertEqual(set(plan['writes']),{'biography','birthday'})
        self.assertEqual(plan['fields']['fio']['decision'],'reject')
        self.assertEqual(self.query('select birthday from person where id=11095'),[('1954',)])

    def test_wrong_award_serial_hmac_and_stale_cannot_be_overridden(self):
        token=self.mixed();v=flow.workspace(self.settings,token)
        bad=next(r for r in v['buckets']['insufficient'] if str(r['person_id'])=='7')
        with self.assertRaises(bio.ValidationError):self.submit(token,bad['row'],identity_choice='same',fio_choice='proposed')
        row=v['buckets']['manual'][0]['row'];op,_=self.submit(token,row,birthday_choice='proposed')
        self.execute("update person set biography='Чужая правка' where id=5")
        with self.assertRaises(bio.ValidationError):flow.workspace(self.settings,token,[op])
        self.assertTrue(flow.workspace(self.settings,token)['fatal'])
        record=bio.load_preview(self.settings,token);record['entries'][0]['values']['snapshot_signature']='0'*64;bio._save(self.settings,token,record)
        self.assertTrue(flow.workspace(self.settings,token)['fatal'])
        with self.assertRaises(bio.ValidationError):flow.prepare_workspace(self.settings,token,flow.workspace(self.settings,token)['revision'],[])

    def test_stages_are_bound_to_file_and_summary_and_revalidated_at_commit(self):
        token=self.mixed();row=flow.workspace(self.settings,token)['buckets']['manual'][0]['row'];op,_=self.submit(token,row,birthday_choice='current')
        other=bio.preview(self.settings,self.content)[0]
        with self.assertRaises(bio.ValidationError):flow.workspace(self.settings,other,[op])
        view=flow.workspace(self.settings,token,[op])
        with self.assertRaises(bio.ValidationError):flow.prepare_workspace(self.settings,token,view['revision'],[])
        batch,_=flow.prepare_workspace(self.settings,token,view['revision'],[op]);before=self.query('select birthday,biography from person order by id')
        self.execute("create trigger fail_audit before insert on logs begin select raise(abort,'TEMP failure');end")
        with self.assertRaises(sqlite3.IntegrityError):flow.commit_import(self.settings,batch)
        self.assertEqual(self.query('select birthday,biography from person order by id'),before)

    def test_http_single_screen_and_stage_endpoint_no_sqlite_write(self):
        token=self.mixed();before=self.db.read_bytes();base='/data-maintenance/enrichment/biographies'
        with TestClient(app) as client:
            html=client.get(base+'/preview/'+token).text
            self.assertEqual(html.count('role="tab"'),3)
            for clutter in ['Проверить файл','Загрузить другой файл','Закрыть файл','Скачать отчёт','Как подготовить данные']:self.assertNotIn(clutter,html)
            self.assertEqual(html.count('>Импортировать</button>'),1)
            self.assertIn('data-maintenance-back',html)
            self.assertIn('enrichment_navigation.js',client.get('/data-maintenance').text)
            row=flow.workspace(self.settings,token)['buckets']['manual'][0]['row'];revision=choices.detail(self.settings,token,row)['revision']
            response=client.post(f'{base}/review/{token}/{row}/stage',data={'review_revision':revision,'birthday_choice':'current'})
            self.assertEqual(response.status_code,200);self.assertIn('data-staged-operation',response.text)
            self.assertEqual(self.db.read_bytes(),before)
            response=client.post(base+'/preview',files={'file':('mixed.xlsx',self.content)})
            self.assertEqual(response.status_code,200)

if __name__=='__main__':unittest.main()
