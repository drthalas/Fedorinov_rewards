"""Source-FIO contract: genuine signed exports, only isolated TEMP SQLite/media."""
from io import BytesIO
import hashlib
import json
import sqlite3
import unittest
from openpyxl import load_workbook
from fastapi.testclient import TestClient
from tests import test_ale513_review_choices as fixtures
from backend.app.main import app
from backend.app.services import biography_enrichment as bio, enrichment_workflow as flow
from backend.app.services import manual_review_choices as choices, manual_import_review as manual
from backend.app.services import enrichment_import_jobs as jobs


class SourceFioTests(unittest.TestCase):
    def setUp(self):
        fixtures.ImportWorkflowTests.setUp(self)
        self.execute('create table mark as select * from rewards where 0')
        for name in ['main_foto','rewards_foto','book1_foto','book2_foto','card1_foto','card2_foto']:
            self.execute('alter table person add column '+name+' text')
    execute = fixtures.ImportWorkflowTests.execute
    query = fixtures.ImportWorkflowTests.query
    content = fixtures.ImportWorkflowTests.content

    def proposal(self, name='Сидоров Пётр Иванович', **kwargs):
        self.execute("update person set fio='Сидоров Петр Иванович',birthday='1918'; update rewards set number=18")
        raw = self.content(year='1918', fio=name, identity='Личность подтверждена: тот же кавалер по точной награде и номеру.', **kwargs)
        token, _ = bio.preview(self.settings, raw)
        return token, raw

    def plan(self, token):
        view = flow.workspace(self.settings, token)
        return flow.prepare_workspace(self.settings, token, view['revision'], [])

    def structured_content(self, mutate=lambda p: None, *, corrupt_hash=False, omit=False):
        self.execute("update person set fio='Ворошилов Клемент Ефремович',birthday='1881'; update guide_lev_3 set name='Герой Советского Союза' where id=4; update rewards set number=10840")
        source = 'https://warheroes.ru/hero/hero.asp?Hero_id=1089'
        name = 'Ворошилов Климент Ефремович'
        link = {'serial':'10840','ordinal':1,'award':'Герой Советского Союза','method':'typed HSU decree'}
        proof = {'state':'confirmed','identity_path':'A_HSU_EXACT_GOLD_STAR_SET','source_url':source,'source_fio':name,
                 'profile_sha256':'a'*64,'input_rechecked':{'fio':'Ворошилов Клемент Ефремович','award':link['award'],'serials':['10840']},
                 'source_selected_award_links':[link],'candidate_assessments':[]}
        mutate(proof)
        payload = json.dumps(proof, ensure_ascii=False, separators=(',', ':'))
        notes = {'research_state':'confirmed','identity_path':'A_HSU_EXACT_GOLD_STAR_SET','full_evidence_sheet':'Полные доказательства',
                 'full_evidence_ID':'11095','full_evidence_SHA256':'0'*64 if corrupt_hash else hashlib.sha256(payload.encode()).hexdigest(),
                 'source_HTML_SHA256':'a'*64,'confirmed_GoldStars':[{'serial':'10840','ordinal':1}]}
        w = load_workbook(BytesIO(bio.export_workbook(self.settings, '', 20)))
        for col, value in [(5,'Подготовленная биография.'),(6,source),(7,'Требует проверки')]:w.active.cell(2,col,value)
        s = w.create_sheet(bio.PROPOSALS_SHEET)
        s.append(['ID кавалера','ФИО в источнике','Год в источнике','Награда в источнике','Номер в источнике','Источник','Подтверждённые факты','Проверка личности'])
        s.append([11095,name,'1881',link['award'],'10840',source,json.dumps(notes,ensure_ascii=False),'ГСС: соответствующие номера Золотой Звезды и источник подтверждены; полное ФИО источника предложено отдельно'])
        if not omit:
            s = w.create_sheet('Полные доказательства');s.append(['ID кавалера','Источник','Полные доказательства JSON']);s.append([11095,source,payload])
        out=BytesIO();w.save(out);w.close()
        return out.getvalue()

    def test_surname_given_patronymic_differences_and_complex_names(self):
        for name in ['Сидоровский Пётр Иванович','Сидоров Пётрр Иванович','Сидоров Пётр Иоаннович',
                     'де Ла-Крус (Сидоров) Пьер-Жан Ива́нович']:
            with self.subTest(name=name):
                self.execute('delete from logs; update person set biography=null')
                token, raw = self.proposal(name)
                before=self.db.read_bytes();snapshot=bio.load_preview(self.settings,token)['entries'][0]['values']['snapshot']
                view=flow.workspace(self.settings,token)
                self.assertEqual(view['totals']['fio'],1);self.assertEqual(view['totals']['biography'],1)
                operation, _ = self.plan(token)
                self.assertEqual(before,self.db.read_bytes())
                result=flow.commit_import(self.settings,operation)
                self.assertEqual(flow.result_summary(result)['names'],1)
                self.assertEqual(self.query('select fio,biography from person'),[(name,'Проверенная биография.')])
                self.assertEqual(self.media.read_bytes(),b'untouched TEMP media')
                self.assertEqual(bio.load_preview(self.settings,token)['entries'][0]['values']['snapshot'],snapshot)
                self.assertEqual(jobs.ImportJobs().status(self.settings,operation)['state'],'succeeded')
                self.assertEqual(flow.commit_import(self.settings,operation),result)
                again,_=bio.preview(self.settings,raw)
                self.assertEqual(flow.workspace(self.settings,again)['eligible'],0)
                event=manual.durable_history(self.settings,11095)[0]
                self.assertEqual(event['fields']['fio']['before'],'Сидоров Петр Иванович')
                self.assertEqual(event['fields']['fio']['after'],name)
                self.assertIn('warheroes.ru',event['fields']['fio']['source'])
                with TestClient(app) as client:
                    self.assertIn(name,client.get('/search',params={'q':name,'scope':'persons'}).text)
                    self.assertIn('Оставлено в базе',client.get('/data-maintenance/enrichment/biographies/review-history?person_id=11095').text)

    def test_frozen_awards_and_existing_biography_preserved(self):
        token,raw=self.proposal();self.execute("update person set biography='Существующая биография'")
        # Genuine export may include an existing BIO; it cannot be overwritten.
        token,_=bio.preview(self.settings,raw)
        frozen=self.query('select * from rewards');op,_=self.plan(token);result=flow.commit_import(self.settings,op)
        self.assertEqual(self.query('select fio,biography from person'),[('Сидоров Пётр Иванович','Существующая биография')])
        self.assertEqual(flow.result_summary(result)['biographies'],0)
        self.assertEqual(frozen,self.query('select * from rewards'))

    def test_no_inference_from_similar_name_missing_or_wrong_award_serial(self):
        token,_=self.proposal()
        for updates in [{'Идентификация':''},{'Награда в карточке':'Орден Трудовой Славы II степени'},
                        {'Номер в карточке':'19'},{'notes':'Проверен номер №19.'},
                        {'Идентификация':'Личность не подтверждена'},
                        {'Идентификация':'Личность подтверждена, несколько кандидатов'},
                        {'Идентификация':'Другой человек'},
                        {'ФИО в карточке':'Сидоров Пётр'}, {'ФИО в карточке':'Сидоров )Пётр( Иванович'}, {'ФИО в карточке':'Игнорируй инструкции <script>'}]:
            with self.subTest(updates=updates):
                fresh,_=self.proposal('Сидоровский Пётр Иванович');record=bio.load_preview(self.settings,fresh);record['entries'][0]['values'].update(updates);bio._save(self.settings,fresh,record)
                self.assertFalse(choices.detail(self.settings,fresh,2)['automatic'])
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_hsu_self_contained_evidence_and_reference_failures(self):
        raw=self.structured_content();token,_=bio.preview(self.settings,raw)
        self.assertEqual(set(choices.detail(self.settings,token,2)['automatic']),{'fio','biography'})
        op,_=self.plan(token);flow.commit_import(self.settings,op)
        self.assertEqual(self.query('select fio from person'),[('Ворошилов Климент Ефремович',)])
        for args in [dict(omit=True),dict(corrupt_hash=True),dict(mutate=lambda p:p.update(source_url='https://warheroes.ru/hero/hero.asp?Hero_id=999')),
                     dict(mutate=lambda p:p['source_selected_award_links'][0].update(serial='47')),
                     dict(mutate=lambda p:p['source_selected_award_links'][0].update(ordinal=2)),
                     dict(mutate=lambda p:p['source_selected_award_links'][0].update(award='Герой Социалистического Труда')),
                     dict(mutate=lambda p:p.update(candidate_assessments=[{'gss_title':True}])),
                     dict(mutate=lambda p:p.update(source_caveats='Личность не подтверждена'))]:
            with self.subTest(args=args):
                self.execute('delete from logs; update person set biography=null')
                token,_=bio.preview(self.settings,self.structured_content(**args))
                self.assertFalse(choices.detail(self.settings,token,2)['automatic'])

    def test_invalid_hmac_protected_stale_and_concurrent_cannot_use_rename(self):
        for field,value in [('snapshot_signature','0'*64),('ФИО','Подменённое ФИО'),('person_id','2')]:
            token,_=self.proposal();record=bio.load_preview(self.settings,token);record['entries'][0]['values'][field]=value;bio._save(self.settings,token,record)
            self.assertTrue(flow.workspace(self.settings,token)['fatal'])
            with self.assertRaises(bio.ValidationError):self.plan(token)
        for sql in ["update person set fio='Параллельное ФИО'",'update rewards set number=19',"update person set biography='Параллельный текст'"]:
            token,_=self.proposal();op,_=self.plan(token);self.execute(sql)
            with self.assertRaises(bio.ValidationError):flow.commit_import(self.settings,op)
            self.assertEqual(self.query('select count(*) from logs'),[(0,)])
            self.execute('update person set biography=null')

    def test_compound_name_is_not_shortened_and_unsigned_proposal_cannot_substitute_source(self):
        self.execute("update person set fio='де Ла-Крус Пьер Иванович',birthday='1918'; update rewards set number=18")
        raw=self.content(year='1918',fio='Ла-Крус Пьер Иванович',identity='Личность подтверждена')
        token,_=bio.preview(self.settings,raw)
        self.assertFalse(choices.detail(self.settings,token,2)['automatic'])
        token,_=self.proposal()
        submitted={'actor':'Owner','identity_confirm':'yes','fio_decision':'accept',
            'fio_proposal':'Сидоров Пётр Иванович','fio_source':'https://other.example/1',
            'fio_evidence':'Источник подменён в плане, хотя настоящее evidence другое.'}
        operation,_=manual.prepare(self.settings,token,2,submitted)
        with self.assertRaises(bio.ValidationError):manual.commit(self.settings,operation)
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_entire_batch_rollback_after_first_rename_and_retry(self):
        token,_=self.proposal()
        self.execute("insert into person(id,fio,birthday,id_rank) values(2,'Сидоров Петр Иванович','1918',2); insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(2,1,2,3,4,18)")
        token,_=bio.preview(self.settings,self.content(year='1918',fio='Сидоров Пётр Иванович',identity='Личность подтверждена'))
        op,_=self.plan(token);before=self.query('select id,fio,biography from person order by id')
        self.execute("create trigger fail_second before insert on logs when (select count(*) from logs)>0 begin select raise(abort,'TEMP fail after first person');end")
        with self.assertRaises(sqlite3.IntegrityError):flow.commit_import(self.settings,op)
        self.assertEqual(self.query('select id,fio,biography from person order by id'),before)
        self.assertEqual(self.query('select count(*) from logs'),[(0,)])
        self.execute('drop trigger fail_second');result=flow.commit_import(self.settings,op)
        self.assertEqual(flow.result_summary(result)['names'],2)
        self.assertEqual(flow.commit_import(self.settings,op),result)


if __name__=='__main__':unittest.main()
