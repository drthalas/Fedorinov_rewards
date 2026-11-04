"""Focused ALE-523: statistics, one name audit, and moved import entry; TEMP only."""
from contextlib import closing
from unittest.mock import patch
import json,os,sqlite3,time,unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import biography_enrichment as b,fio_corrections as f,enrichment_workflow as flow
from tests import test_ale513_manual_import_review as fixture
from tests import test_ale475_person_import as import_fixture

BASE='/data-maintenance/enrichment/biographies'


def complete_ui_schema(db):
    with closing(sqlite3.connect(db)) as c:
        person={r[1] for r in c.execute('pragma table_info(person)')}
        for name in ['main_foto','rewards_foto','book1_foto','book2_foto','card1_foto','card2_foto','link1','link2']:
            if name not in person:c.execute('alter table person add column '+name+' text')
        rewards={r[1] for r in c.execute('pragma table_info(rewards)')}
        for name in ['back_foto','book1_foto','book2_foto','reward_list','date_purchase','price_purchase','price_now']:
            if name not in rewards:c.execute('alter table rewards add column '+name+' text')
        c.execute('create table if not exists mark as select * from rewards where 0');c.commit()


class Ale523Tests(unittest.TestCase):
    execute=fixture.ManualReviewTests.execute
    query=fixture.ManualReviewTests.query
    def setUp(self):
        fixture.ManualReviewTests.setUp(self)
        self.settings=self.settings.model_copy(update={'update_backup_dir':self.root/'backups'})
        env=patch.dict(os.environ,{'UPDATE_BACKUP_DIR':str(self.root/'backups'),'REWARDS_AUDIT_LOG':str(self.root/'audit.log')})
        env.start();self.addCleanup(env.stop)
        complete_ui_schema(self.db)

    def test_without_awards_identifiable_name_not_number_and_unique_bio_subsets(self):
        self.execute("delete from rewards;delete from person;insert into person(id,fio,biography) values(1,'Первый',null),(2,'Второй','Есть BIO'),(3,'Третий','  '),(4,'Четвёртый','Есть BIO');insert into guide_lev_3(id,idl,name) values(8,3,'  ');insert into rewards(person_id,id_name,number) values(2,null,9),(2,999,10),(2,8,11),(3,4,null),(4,4,20),(4,5,21),(999,4,90),(null,4,91)")
        before=self.db.read_bytes();expected={'total':4,'filled':2,'empty':2,'without_awards':2}
        self.assertEqual(b.population_statistics(self.settings),expected)
        self.assertEqual({k:b.statistics(self.settings)[k] for k in expected},expected)
        with TestClient(app) as client:
            self.assertEqual(client.get(BASE+'/statistics').json(),expected)
            html=client.get(BASE).text;self.assertIn('data-population-without-awards>2',html)
        self.assertEqual(before,self.db.read_bytes())
        self.execute('delete from rewards;delete from person')
        self.assertEqual(b.population_statistics(self.settings),{'total':0,'empty':0,'filled':0,'without_awards':0})

    def test_population_failure_does_not_fake_zero(self):
        with patch.object(b,'statistics',side_effect=sqlite3.OperationalError('TEMP unavailable')),TestClient(app) as client:
            response=client.get(BASE);self.assertEqual(response.status_code,503)
            self.assertIn('data-population-without-awards>—',response.text)

    def test_case_matrix_preserves_unicode_punctuation_initials_and_null(self):
        matrix={'РОМАНОВ':'Романов','рОмАнОв':'Романов','иВАН':'Иван','АННА-МАРИЯ':'Анна-Мария','ПЕТРОВ-СИДОРОВ':'Петров-Сидоров',
            '  ЁЛКИН  АЛЁНА ':'  Ёлкин  Алёна ','ИВАНОВ (ПЕТРОВ) И.И.':'Иванов (Петров) И.И.',
            'Иванов и.и.':'Иванов И.И.',"Д’АРТАНЬЯН":"Д’Артаньян","О'НЕЙЛ":"О'Нейл",'ОʼНЕЙЛ':'ОʼНейл',
            'ИВА\u0301Н':'Ива\u0301н','ӘЛІМ\u00a0ҚАСЫМ':'Әлім\u00a0Қасым','kИРИЛЛ':'Кирилл'}
        for before,after in matrix.items():
            with self.subTest(before=before):
                result=f.classify({'fio':before});self.assertTrue(result['safe']);self.assertEqual(result['after']['fio'],after)
        for name in ['Иванов Иван Иванович','И.И.','Анна-Мария','Ёлкин Алёна','',None]:
            self.assertIsNone(f.classify({'fio':name}))
        result=f.classify({'surname':'РОМАНОВ','first_name':'иВАН','patronymic':None})
        self.assertEqual(result['after'],{'surname':'Романов','first_name':'Иван','patronymic':None})

    def test_ambiguous_and_latin_exclusions_preserve_entire_record(self):
        for name in ['ACE','JOHN SMITH','ИВАН Sидоров','Иван bорисов','Иван hанов','Иван sидоров','ИВАНОВ (ПЕТРОВ','ИВАНОВ ((ПЕТРОВ))','ИВАНОВ ()','ИВАНОВ Ив.','АННА--МАРИЯ','ИВАН/ПЕТР','ИВАН\nПЕТР','ΙΒΑΝ','Иван Ḁ']:
            with self.subTest(name=name):
                row={'fio':name,'first_name':'ИВАН'} if any('CYRILLIC' in __import__('unicodedata').name(c,'') for c in name) else {'fio':name}
                result=f.classify(row);self.assertFalse(result['safe']);self.assertEqual(result['after'],row);self.assertTrue(result['reason'])
        self.assertFalse(f.classify({'fio':'ИВАН','surname':123})['safe'])
        self.assertEqual(len(f.PAIRS),20);self.assertNotIn('b',f.PAIRS);self.assertNotIn('h',f.PAIRS);self.assertNotIn('s',f.PAIRS)

    def audit_people(self):
        self.execute("delete from rewards;delete from person;insert into person(id,fio,birthday,biography,comment) values(1,'РОМАНОВ','1918','BIO','сохранить'),(2,'kИРИЛЛ','1920','BIO','сохранить'),(3,'Cидоров','1922','BIO','сохранить'),(4,'Иванов','1924','BIO','сохранить'),(5,'John Smith','1926','BIO','сохранить'),(6,null,'1928','BIO','сохранить')")
        return f.audit(self.settings)

    def test_one_audit_dedups_reasons_backup_history_search_and_reaudit(self):
        audit=self.audit_people();self.assertEqual((audit['checked'],audit['safe_records'],audit['homoglyph_records'],audit['case_records'],audit['both_records'],audit['skipped']),(6,3,2,2,1,1))
        before=self.db.read_bytes();f.load_audit(self.settings,audit['audit_token']);self.assertEqual(self.db.read_bytes(),before)
        frozen=self.query('select id,birthday,biography,comment from person');rewards=self.query('select * from rewards')
        event=f.apply(self.settings,audit['audit_token'],'a'*64)
        self.assertEqual((event['records'],event['homoglyph_records'],event['case_records']),(3,2,2))
        self.assertEqual(self.query('select id,birthday,biography,comment from person'),frozen);self.assertEqual(self.query('select * from rewards'),rewards)
        self.assertEqual(event,f.apply(self.settings,audit['audit_token'],'a'*64));self.assertEqual(self.query('select count(*) from logs'),[(1,)])
        change=next(x for x in event['changes'] if x['id']==2);self.assertEqual(change['before']['fio'],'kИРИЛЛ');self.assertEqual(change['after']['fio'],'Кирилл');self.assertEqual(len(change['reasons']),2)
        with sqlite3.connect(event['backup']['path']) as c:self.assertEqual(c.execute('select fio from person where id=1').fetchone()[0],'РОМАНОВ')
        with TestClient(app) as client:self.assertIn('Романов',client.get('/search?q=Романов&scope=persons').text)
        again=f.audit(self.settings);self.assertEqual((again['safe_records'],again['skipped']),(0,1));self.assertEqual(again['latin_records'],1)

    def test_split_actual_name_columns_case_and_null(self):
        self.execute("alter table person add column surname text;alter table person add column first_name text;alter table person add column patronymic text;update person set fio=null,surname='РОМАНОВ',first_name='иВАН',patronymic=null")
        audit=f.audit(self.settings);event=f.apply(self.settings,audit['audit_token'],'b'*64)
        self.assertEqual(event['records'],1);self.assertEqual(self.query('select fio,surname,first_name,patronymic from person'),[(None,'Романов','Иван',None)])

    def test_changed_after_case_audit_tamper_readonly_and_atomic_rollback(self):
        audit=self.audit_people();self.execute("update person set fio='Ручная правка' where id=1")
        with self.assertRaises(b.ValidationError):f.apply(self.settings,audit['audit_token'],'c'*64)
        self.assertEqual(self.query('select fio from person where id=1'),[('Ручная правка',)])
        audit=f.audit(self.settings);before=self.db.read_bytes()
        with self.assertRaises(Exception):f.apply(self.settings.model_copy(update={'read_only':True}),audit['audit_token'],'d'*64)
        self.assertEqual(before,self.db.read_bytes())
        plan=b.load_preview(self.settings,audit['audit_token']);plan['case_records']=999;b._save(self.settings,audit['audit_token'],plan)
        with self.assertRaises(b.ValidationError):f.apply(self.settings,audit['audit_token'],'d'*64)
        self.execute("update person set fio='РОМАНОВ' where id=1;create trigger fail_case_audit before insert on logs begin select raise(abort,'TEMP audit fail');end")
        audit=f.audit(self.settings);names=self.query('select fio from person order by id')
        with self.assertRaises(sqlite3.IntegrityError):f.apply(self.settings,audit['audit_token'],'e'*64)
        self.assertEqual(self.query('select fio from person order by id'),names);self.assertEqual(self.query('select count(*) from logs'),[(0,)])

    def test_correction_reconnect_has_cause_counts_without_duplicate_writes(self):
        audit=self.audit_people();op='f'*64;event=f.apply(self.settings,audit['audit_token'],op)
        b._save(self.settings,op,{'created':time.time(),'state':'running','kind':'apply','job_id':op,'percent':99,'audit_token':audit['audit_token']})
        result=f.CorrectionJobs().status(self.settings,op)
        self.assertEqual(result['state'],'succeeded');self.assertEqual(result['result']['case_records'],2);self.assertEqual(result['result']['skipped'],1)
        self.assertEqual(self.query('select count(*) from logs'),[(1,)])

    def test_menu_import_back_on_all_states_and_existing_pipeline_guards(self):
        with TestClient(app) as client:
            menu=client.get('/data-maintenance?menu=1').text
            for label in ['Наполнение данных','Исправление данных','Оптимизация изображений','Импорт новых кавалеров']:self.assertIn(label,menu)
            self.assertEqual(menu.count('class="cavalier-form-card bio-module'),4)
            legacy=client.get('/legacy?tab=rewards');self.assertEqual(legacy.status_code,200);self.assertNotIn('href="/persons/import"',legacy.text)
            urls=['/persons/import','/persons/import?id_name=4','/persons/import?id_name=999']
            for url in urls:
                response=client.get(url);self.assertIn('<title>Импорт новых кавалеров</title>',response.text);self.assertIn('href="/data-maintenance?menu=1">← Назад',response.text)
                self.assertIn('class="active" href="/data-maintenance" data-maintenance-nav',response.text)
            content=import_fixture.xlsx([import_fixture.row(725),import_fixture.row(9905)])
            for n in range(2):
                response=client.post('/persons/import',data={'id_name':'4','confirm':'yes'},files={'file':('new.xlsx',content)})
                self.assertEqual(response.status_code,200);self.assertIn('href="/data-maintenance?menu=1">← Назад',response.text)
            self.assertEqual(self.query('select count(*) from person'),[(2,)])
            self.assertEqual(self.query('select birthday,id_rank,biography from person where id!=11095'),[('1945',10,None)])
            failure=client.post('/persons/import',data={'id_name':'4','confirm':'yes'},files={'file':('bad.txt',b'bad')});self.assertEqual(failure.status_code,400);self.assertIn('href="/data-maintenance?menu=1">← Назад',failure.text)
        with patch.dict(os.environ,{'READ_ONLY':'true'}),TestClient(app) as client:
            self.assertNotIn('href="/persons/import"',client.get('/data-maintenance?menu=1').text)
            self.assertEqual(client.get('/persons/import').status_code,403)
            self.assertEqual(client.post('/persons/import',data={'id_name':'4','confirm':'yes'},files={'file':('new.xlsx',content)}).status_code,403)

    def test_case_fix_keeps_accepted_row_local_stale_and_other_ready_rows(self):
        self.execute("delete from rewards;delete from person;insert into person(id,fio,birthday,id_rank) values(1,'РОМАНОВ ИВАН ИВАНОВИЧ','1918',10),(2,'Петров Иван Сергеевич','1920',10);insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(1,1,2,3,4,18),(2,1,2,3,4,19)")
        rows=[]
        for entry in b.read_rows(b.export_workbook(self.settings,'',20)):
            v=entry['values'];s=json.loads(v['snapshot']);serial=str(s['person']['awards'][0]['number'])
            v.update({'biography':'Подготовленная TEMP биография.','source_url':'https://warheroes.ru/hero/hero.asp?Hero_id='+v['person_id'],'status':'confirmed','ФИО в карточке':v['ФИО'],'Год в карточке':v['Год рождения'],'Награда в карточке':'Орден Трудовой Славы I степени','Идентификация':'Личность подтверждена','notes':'Подтверждены ФИО и точный орден I степени №'+serial})
            rows.append([v.get(h,'') for h in b.HEADERS])
        token,_=b.preview(self.settings,b._workbook(b.HEADERS,rows));self.assertEqual(flow.workspace(self.settings,token)['eligible'],2)
        audit=f.audit(self.settings);f.apply(self.settings,audit['audit_token'],'9'*64)
        view=flow.workspace(self.settings,token);self.assertFalse(view['fatal']);self.assertEqual((view['eligible'],view['stale_skipped']),(1,1))

    def test_standardization_page_preview_pagination_and_readonly_control(self):
        self.execute('delete from rewards;delete from person')
        with sqlite3.connect(self.db) as c:c.executemany('insert into person(id,fio) values(?,?)',[(n,'РОМАНОВ') for n in range(1,53)])
        audit=f.audit(self.settings)
        with TestClient(app) as client:
            page=client.get('/data-maintenance/corrections').text;self.assertIn('Стандартизация ФИО',page);self.assertIn('Исправляет латинские двойники и регистр букв в ФИО',page)
            preview=client.get('/data-maintenance/corrections/preview/'+audit['audit_token']).text;self.assertEqual(preview.count('№ '),50);self.assertIn('Регистр:',preview);self.assertIn('Следующая',preview)
        with patch.dict(os.environ,{'READ_ONLY':'true'}),TestClient(app) as client:self.assertIn('data-can-write="false"',client.get('/data-maintenance/corrections').text)

if __name__=='__main__':unittest.main()
