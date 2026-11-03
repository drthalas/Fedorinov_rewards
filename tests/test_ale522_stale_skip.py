"""Row-local stale is skippable only after complete original authenticity."""
from contextlib import closing
from io import BytesIO
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import json,sqlite3,unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import biography_enrichment as b,enrichment_workflow as f,manual_import_review as m,enrichment_import_jobs as j
from tests import test_ale513_manual_import_review as fixture

BASE='/data-maintenance/enrichment/biographies'

class StaleSkipTests(unittest.TestCase):
    setUp=fixture.ManualReviewTests.setUp
    execute=fixture.ManualReviewTests.execute
    query=fixture.ManualReviewTests.query

    def content(self):
        rows=[]
        for entry in b.read_rows(b.export_workbook(self.settings,'',20)):
            v=entry['values'];s=json.loads(v['snapshot']);pid=v['person_id']
            v.update({'biography':'Подтверждённая TEMP биография '+pid,'source_url':'https://warheroes.ru/hero/hero.asp?Hero_id='+pid,'status':'Требует проверки',
                'ФИО в карточке':v['ФИО'].replace('Петр','Пётр'),'Год в карточке':v['Год рождения'],'Награда в карточке':'Орден Трудовой Славы I степени',
                'Номер в карточке':str(s['person']['awards'][0]['number']),'Идентификация':'Личность подтверждена: тот же кавалер',
                'notes':f"Проверены полное ФИО, точная I степень №{s['person']['awards'][0]['number']} и источник."})
            rows.append([v.get(h,'') for h in b.HEADERS])
        return b._workbook(b.HEADERS,rows)

    def setup_people(self):
        self.execute("delete from rewards;delete from person; insert into person(id,fio,birthday,id_rank) values(1,'Сидоров Петр Иванович','1918',10),(2,'Петров Иван Сергеевич','1920',10),(3,'Иванов Павел Иванович','1922',10); insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(1,1,2,3,4,18),(2,1,2,3,4,19),(3,1,2,3,4,20)")
        return self.content()

    def plan(self,token,revision=None):
        view=f.workspace(self.settings,token)
        return f.prepare_workspace(self.settings,token,revision or view['revision'],[])

    def test_one_stale_source_fio_mixed_commit_history_retry_and_fresh_recovery(self):
        raw=self.setup_people();self.execute("update person set fio='Правка Owner Иван Сергеевич' where id=2")
        token,_=b.preview(self.settings,raw);before=self.db.read_bytes();view=f.workspace(self.settings,token)
        self.assertFalse(view['fatal']);self.assertEqual((view['eligible'],view['stale_skipped']),(2,1))
        row=view['buckets']['insufficient'][0];self.assertEqual(row['state'],'stale');self.assertEqual(row['guard']['fields'],['ФИО'])
        operation,plan=self.plan(token);self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(plan['summary']['fields']['fio'],1);self.assertEqual(plan['stale_skipped'],1)
        result=f.commit_import(self.settings,operation)
        self.assertEqual((result['saved'],result['biographies'],result['names'],result['stale_skipped']),(2,2,1,1))
        self.assertEqual(self.query('select fio,biography from person where id=2'),[('Правка Owner Иван Сергеевич',None)])
        self.assertEqual(self.query("select count(*) from logs where action like 'manual_import_review:%'"),[(2,)])
        self.assertEqual(f.commit_import(self.settings,operation),result)
        self.assertEqual(j.ImportJobs().status(self.settings,operation)['result']['stale_skipped'],1)
        again,_=b.preview(self.settings,raw);self.assertTrue(f.completed_preview(self.settings,again,f.workspace(self.settings,again))['already_done'])
        fresh,_=b.preview(self.settings,self.content());operation,_=self.plan(fresh);r=f.commit_import(self.settings,operation)
        self.assertEqual(r['saved'],1);self.assertIsNotNone(self.query('select biography from person where id=2')[0][0])

    def test_multiple_all_stale_deleted_and_no_empty_transaction(self):
        raw=self.setup_people();self.execute("update person set birthday='1930' where id=1;update rewards set number=99 where person_id=2;delete from rewards where person_id=3;delete from person where id=3")
        token,_=b.preview(self.settings,raw);view=f.workspace(self.settings,token)
        self.assertFalse(view['fatal']);self.assertEqual(view['stale_skipped'],3);self.assertEqual(view['eligible'],0)
        self.assertEqual([r['guard']['fields'] for r in view['rows']],[['Год рождения'],['Награды и номера'],['Кавалер удалён']])
        before=self.db.read_bytes();op,plan=self.plan(token);self.assertIsNone(op)
        done=f.completed_preview(self.settings,token,view);self.assertTrue(done['all_stale']);self.assertEqual(done['summary']['stale_skipped'],3)
        with TestClient(app) as client:
            html=client.get(BASE+'/preview/'+token).text;self.assertIn('Все карточки пропущены',html)
        self.assertEqual(self.db.read_bytes(),before);self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_changed_outside_file_is_irrelevant_and_all_signed_identity_fields_are_checked(self):
        raw=self.setup_people()
        entries=b.read_rows(raw);single=b._workbook(b.HEADERS,[[entries[0]['values'].get(h,'') for h in b.HEADERS]])
        token,_=b.preview(self.settings,single);op,_=self.plan(token)
        self.execute("update person set fio='Внешняя правка' where id=2")
        self.assertEqual(f.commit_import(self.settings,op)['saved'],1)
        self.execute('delete from logs;update person set biography=null')
        for sql,label in [("update person set fio='Другое ФИО' where id=1",'ФИО'),("update person set birthday='1900' where id=1",'Год рождения'),('update person set id_rank=2 where id=1','Звание'),('update rewards set number=998 where person_id=1','Награды и номера')]:
            with self.subTest(label=label):
                current=self.content();self.execute(sql);t,_=b.preview(self.settings,current);v=f.workspace(self.settings,t)
                self.assertFalse(v['fatal']);self.assertIn(label,v['rows'][0]['guard']['fields'])

    def test_trust_error_cannot_hide_behind_local_stale_even_deleted_or_tampered_id(self):
        raw=self.setup_people();entries=b.read_rows(raw);original=entries[0]['values']
        self.execute("update person set fio='Изменено' where id=1")
        for updates,code in [({'snapshot_signature':'0'*64},'signature_invalid'),({'ФИО':'Подменено'},'protected_field_changed'),({'person_id':'999'},'protected_field_changed')]:
            with self.subTest(code=code):
                values={**original,**updates};bad=b._workbook(b.HEADERS,[[values.get(h,'') for h in b.HEADERS]]+[[e['values'].get(h,'') for h in b.HEADERS] for e in entries[1:]])
                token,_=b.preview(self.settings,bad);v=f.workspace(self.settings,token);self.assertTrue(v['fatal']);self.assertEqual(v['fatal_failures'][0]['code'],code)
                with self.assertRaises(b.ValidationError):self.plan(token)
        for mutate in [lambda s:s['person'].pop('id_rank'),lambda s:s['person']['awards'][0].pop('country'),lambda s:s.update(selection=[1,2,3,4,5]),lambda s:s['person'].update(fio=['invalid'])]:
            values=dict(original);snapshot=json.loads(values['snapshot']);mutate(snapshot);values['snapshot']=b.canonical(snapshot);values['snapshot_signature']=b._sign(self.settings,values['snapshot'])
            token,_=b.preview(self.settings,b._workbook(b.HEADERS,[[values.get(h,'') for h in b.HEADERS]]));self.assertEqual(f.workspace(self.settings,token)['fatal_failures'][0]['code'],'snapshot_invalid')
        duplicate=b._workbook(b.HEADERS,[[original.get(h,'') for h in b.HEADERS]]*2);t,_=b.preview(self.settings,duplicate);self.assertTrue(f.workspace(self.settings,t)['fatal'])

    def test_change_before_confirmation_replans_and_restored_confirmation_refreshes(self):
        raw=self.setup_people();token,_=b.preview(self.settings,raw);view=f.workspace(self.settings,token)
        self.execute("update person set birthday='1930' where id=2")
        operation,plan=self.plan(token,view['revision']);self.assertTrue(plan['summary']['refreshed']);self.assertEqual(plan['summary']['people'],2)
        self.execute('update rewards set number=777 where person_id=3')
        refreshed=f.confirmation(self.settings,operation)
        self.assertNotEqual(refreshed['operation'],operation);self.assertEqual(refreshed['batch_plan']['summary']['people'],1)
        self.assertEqual(refreshed['batch_plan']['summary']['stale_skipped'],2)
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])
        self.assertEqual(f.commit_import(self.settings,refreshed['operation'])['saved'],1)

    def test_after_confirmation_identity_or_bio_change_rolls_back_entire_transaction(self):
        raw=self.setup_people();token,_=b.preview(self.settings,raw);operation,_=self.plan(token)
        self.execute("update person set fio='Конкурентная правка' where id=3")
        with self.assertRaisesRegex(b.ValidationError,'Все изменения отменены'):f.commit_import(self.settings,operation)
        self.assertEqual(self.query('select count(*) from person where biography is not null'),[(0,)])
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])
        raw=self.content();token,_=b.preview(self.settings,raw);operation,_=self.plan(token)
        self.execute("update person set biography='Ручной BIO' where id=3")
        with self.assertRaises(b.ValidationError):f.commit_import(self.settings,operation)
        self.assertEqual(self.query('select count(*) from person where biography is not null'),[(1,)])
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_skip_set_and_subset_cannot_be_changed_by_client_or_untrusted_original(self):
        raw=self.setup_people();self.execute("update person set fio='Пропустить' where id=3");token,_=b.preview(self.settings,raw);op,plan=self.plan(token)
        changed=dict(plan);changed['stale_skipped']=0;b._save(self.settings,op,changed)
        with self.assertRaises(b.ValidationError):f.commit_import(self.settings,op)
        op,_=self.plan(token);record=b.load_preview(self.settings,token);record['entries'][-1]['values']['ФИО']='Подмена';b._save(self.settings,token,record)
        with self.assertRaises(b.ValidationError):f.commit_import(self.settings,op)
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_all_stale_after_preview_returns_no_commit_form(self):
        raw=self.setup_people();token,_=b.preview(self.settings,raw);view=f.workspace(self.settings,token)
        self.execute("update person set birthday='1930'")
        before=self.db.read_bytes()
        with TestClient(app) as client:
            response=client.post(BASE+'/workspace/'+token+'/plan',data={'revision':view['revision'],'operations':'[]'})
            self.assertEqual(response.status_code,200);self.assertIn('data-no-import',response.text)
            self.assertIn('Изменённых карточек пропущено: 3',response.text);self.assertNotIn('data-import-start',response.text)
        self.assertEqual(self.db.read_bytes(),before);self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_legacy_bio_only_endpoint_keeps_safe_subset_and_receipts(self):
        raw=self.setup_people();entries=b.read_rows(raw)
        for entry in entries:entry['values']['status']='confirmed'
        raw=b._workbook(b.HEADERS,[[e['values'].get(h,'') for h in b.HEADERS] for e in entries])
        token,_=b.preview(self.settings,raw)
        self.execute("update person set fio='Сохранённая ручная правка' where id=2")
        f.commit_ordinary(self.settings,token)
        self.assertEqual(self.query('select count(*) from person where biography is not null'),[(2,)])
        self.assertEqual(self.query('select fio,biography from person where id=2'),[('Сохранённая ручная правка',None)])
        self.assertEqual(f.completed_preview(self.settings,token)['summary']['stale_skipped'],1)

    def test_ui_two_tabs_skip_fields_confirmation_counts_and_reload_summary(self):
        raw=self.setup_people();self.execute("update person set birthday='1900' where id=2");token,_=b.preview(self.settings,raw)
        with TestClient(app) as client:
            html=client.get(BASE+'/preview/'+token).text
            self.assertEqual(html.count('role="tab"'),2);self.assertIn('Карточка изменена после выгрузки — пропущена',html);self.assertIn('Год рождения',html);self.assertNotIn('Импорт остановлен:',html)
            op,plan=self.plan(token);confirmation=client.get(BASE+'/confirm/'+op).text;self.assertIn('из-за изменений карточек: 1',confirmation)
            f.commit_import(self.settings,op);html=client.get(BASE+'/preview/'+token).text;self.assertIn('Изменённых карточек пропущено',html)
            self.assertEqual(f.completed_preview(self.settings,token)['summary']['stale_skipped'],1)

if __name__=='__main__':unittest.main()
