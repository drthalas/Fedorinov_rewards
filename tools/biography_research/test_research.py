import copy
import importlib.util
import tempfile
import unittest
import zipfile
import sqlite3
import hashlib
import sys
import json
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0,str(Path(__file__).parent))
spec=importlib.util.spec_from_file_location('research',Path(__file__).with_name('research.py'))
research=importlib.util.module_from_spec(spec);spec.loader.exec_module(research)
spec=importlib.util.spec_from_file_location('selector',Path(__file__).with_name('select_sample.py'))
selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)


class ResearchContractTests(unittest.TestCase):
    def test_infrastructure_error_is_retryable(self):
        self.assertFalse(research.research_complete({'status':'Ошибка источника'}))
        self.assertFalse(research.research_complete({'status':'Не исследовано — BLOCKED'}))
        self.assertFalse(research.research_complete({'status':'Готово к проверке','attempt_state':'infrastructure_blocked'}))
    def test_genuine_completed_results_are_preserved(self):
        self.assertTrue(research.research_complete({'status':'Готово к проверке'}))
        self.assertTrue(research.research_complete({'status':'Ошибка источника','attempt_state':'completed'}))
    def test_subprocess_model_and_no_api_fallback(self):
        import runner
        from unittest.mock import patch
        c=runner.command('gpt-6-sol','private','schema','last')
        self.assertEqual(c[c.index('-m')+1],'gpt-6-sol')
        with patch.dict('os.environ',{'OPENAI_API_KEY':'synthetic','CODEX_API_KEY':'synthetic'}):
            self.assertNotIn('OPENAI_API_KEY',runner.subscription_environment())
            self.assertNotIn('CODEX_API_KEY',runner.subscription_environment())
    def test_internal_database_ids_not_sent(self):
        row={**self.row(),'person_id':'987654321','sample_order':'4','Иерархия ID':'1 / 1 / 1 / 12','Текущая биография':''}
        payload=research.research_payload(row)
        self.assertEqual(payload['person_id'],'row-4')
        self.assertNotIn('Иерархия ID',payload)
        self.assertNotIn('Текущая биография',payload)
        self.assertNotIn('987654321',research.prompt(row))
    def test_actual_resume_retries_infrastructure_and_skips_completed(self):
        import runner
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);input_file=root/'input.xlsx';input_file.write_bytes(b'synthetic input')
            (root/'compatibility').mkdir()
            (root/'compatibility/smoke-test-model.summary.json').write_text(json.dumps({'model':'test-model','auth_mode':'ChatGPT','status':'PASS'}))
            (root/'progress.json').write_text(json.dumps({'001':{'status':'Ошибка источника','biography':'','attempt_state':'infrastructure_blocked'}}))
            row={**self.row(),'Текущая биография':''}
            result=self.result();result['person_id']='row-001';url=result['source_urls'][0]
            def fake_run(command,**kwargs):
                Path(command[command.index('-o')+1]).write_text(json.dumps(result))
                kwargs['stdout'].write(json.dumps({'type':'item.completed','item':{'type':'web_search','action':{'type':'open_page','url':url},'results':[{'type':'text_result','url':url,'title':'Synthetic document'}]}})+'\n')
                kwargs['stdout'].write(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}})+'\n')
                return type('Process',(),{'returncode':0})()
            with patch.object(research,'load_xlsx',return_value=[row]),patch.object(research.subprocess,'run',side_effect=fake_run) as invocation:
                progress,_=research.run(input_file,root,1,model='test-model')
                self.assertEqual(invocation.call_count,1)
                self.assertEqual(progress['001']['attempt_state'],'completed')
                research.run(input_file,root,1,model='test-model')
                self.assertEqual(invocation.call_count,1)
                input_file.write_bytes(b'changed synthetic input')
                with self.assertRaisesRegex(ValueError,'Frozen input changed'):
                    research.run(input_file,root,1,model='test-model')
    def test_offset45_requires_matching_five_person_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);input_file=root/'input.xlsx';input_file.write_bytes(b'synthetic input')
            (root/'compatibility').mkdir()
            (root/'compatibility/smoke-test-model.summary.json').write_text(json.dumps({'model':'test-model','auth_mode':'ChatGPT','status':'PASS'}))
            with patch.object(research,'load_xlsx',return_value=[self.row()]*50):
                with self.assertRaisesRegex(ValueError,'five-person'):
                    research.run(input_file,root,45,offset=5,model='test-model')
    def row(self):return {'person_id':'001','Год рождения':'1910','Награда':'Александра Невского'}
    def result(self):
        url='https://pamyat-naroda.ru/heroes/example'
        return {'person_id':'001','biography':'Краткая подтверждённая биография. Второй факт.',
          'status':'Готово к проверке','source_urls':[url],
          'identity':[{'attribute':'award','source_value':'орден Александра Невского','url':url,'explanation':'synthetic test'},
            {'attribute':'rank','source_value':'капитан','url':url,'explanation':'synthetic test'}],
          'evidence':[{'claim':'Факт1','url':url,'support':'synthetic test'},{'claim':'Факт2','url':url,'support':'synthetic test'}],'notes':''}
    def test_name_only_does_not_pass(self):
        r=self.result();r['identity']=[]
        with self.assertRaisesRegex(ValueError,'FIO-only'):research.validate(r,self.row())
    def test_ambiguous_biography_must_be_empty(self):
        r=self.result();r['status']='Требует проверки'
        with self.assertRaises(ValueError):research.validate(r,self.row())
        r['biography']='';research.validate(r,self.row())
    def test_unsupported_source_is_rejected(self):
        r=self.result();r['source_urls']=['https://pamyat-naroda.ru.bad.example/heroes/1']
        with self.assertRaises(ValueError):research.validate(r,self.row())
    def test_1945_not_sufficient(self):
        row=self.row();row['Год рождения']='1945'
        r=self.result();r['identity'][1]['attribute']='birth'
        with self.assertRaises(ValueError):research.validate(r,row)
    def test_lookalike_award_rejected(self):
        r=self.result();r['identity'][0]['source_value']='Александра Невского II'
        with self.assertRaises(ValueError):research.validate(r,self.row())
    def test_fact_evidence_required(self):
        r=self.result();r['evidence']=[]
        with self.assertRaises(ValueError):research.validate(r,self.row())
    def test_wrong_row_rejected(self):
        r=self.result();r['person_id']='002'
        with self.assertRaises(ValueError):research.validate(r,self.row())
    def test_length_limit(self):
        r=self.result();r['biography']='я'*601
        with self.assertRaises(ValueError):research.validate(r,self.row())
    def test_xlsx_leading_zeros_and_duplicate_fio_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.xlsx'
            xml='''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
              <row r="1"><c r="A1" t="inlineStr"><is><t>person_id</t></is></c><c r="B1" t="inlineStr"><is><t>ФИО</t></is></c><c r="C1" t="inlineStr"><is><t>Награда</t></is></c><c r="D1" t="inlineStr"><is><t>Номер</t></is></c></row>
              <row r="2"><c r="A2" t="inlineStr"><is><t>001</t></is></c><c r="B2" t="inlineStr"><is><t>Тест</t></is></c><c r="C2" t="inlineStr"><is><t>Тест</t></is></c><c r="D2" t="inlineStr"><is><t>00042</t></is></c></row>
              <row r="3"><c r="A3" t="inlineStr"><is><t>002</t></is></c><c r="B3" t="inlineStr"><is><t>Тест</t></is></c><c r="C3" t="inlineStr"><is><t>Тест</t></is></c></row>
              </sheetData></worksheet>'''
            with zipfile.ZipFile(p,'w') as z:z.writestr('xl/worksheets/sheet1.xml',xml)
            rows=research.load_xlsx(p)
            self.assertEqual(rows[0]['person_id'],'001');self.assertEqual(rows[0]['Номер'],'00042')
            self.assertEqual(len(rows),2);self.assertEqual(rows[1]['Номер'],'')
            xml=xml.replace('<t>00042</t>','<t>00042</t>').replace('<c r="D2" t="inlineStr">','<c r="D2" t="inlineStr"><f>HYPERLINK("x")</f>')
            with zipfile.ZipFile(p,'w') as z:z.writestr('xl/worksheets/sheet1.xml',xml)
            with self.assertRaisesRegex(ValueError,'Formula'):research.load_xlsx(p)
    def test_seeded_exact_award_sampling_is_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'synthetic.sqlite';c=sqlite3.connect(db)
            c.executescript('''CREATE TABLE person(id INTEGER PRIMARY KEY,fio TEXT,birthday TEXT,id_rank INTEGER,link1 TEXT,link2 TEXT,biography TEXT);
              CREATE TABLE rewards(id INTEGER PRIMARY KEY,person_id INTEGER,id_gos INTEGER,id_catigory INTEGER,id_sub_catigory INTEGER,id_name INTEGER,number TEXT,id_link TEXT);
              CREATE TABLE guide(id INTEGER PRIMARY KEY,name TEXT);
              CREATE TABLE guide_lev_0(id INTEGER PRIMARY KEY,name TEXT);
              CREATE TABLE guide_lev_1(id INTEGER PRIMARY KEY,name TEXT);
              CREATE TABLE guide_lev_2(id INTEGER PRIMARY KEY,name TEXT);
              CREATE TABLE guide_lev_3(id INTEGER PRIMARY KEY,name TEXT);''')
            c.execute('INSERT INTO guide VALUES(1,?)',('Тест',))
            for table,name in (('guide_lev_0','СССР'),('guide_lev_1','Боевые'),('guide_lev_2','Ордена')):
                c.execute(f'INSERT INTO {table} VALUES(1,?)',(name,))
            c.executemany('INSERT INTO guide_lev_3 VALUES(?,?)',[(12,'Александра Невского'),(13,'Александра Невского II')])
            for i in range(1,63):
                c.execute('INSERT INTO person VALUES(?,?,?,?,?,?,?)',(i,'Synthetic person','1920-01-01',1,'','',None if i<61 else ('filled' if i==61 else '\u00a0')))
                c.execute('INSERT INTO rewards VALUES(?,?,?,?,?,?,?,?)',(i,i,1,1,1,13 if i==62 else 12,'00042',''))
            c.execute('INSERT INTO rewards VALUES(1001,1,1,1,1,12,?,?)',('00043',''))
            c.commit();c.close()
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            first=selector.sample(db,20261009491);second=selector.sample(db,20261009491)
            self.assertEqual(first['metadata']['pool_count'],60)
            self.assertEqual(first['metadata']['unique_ids'],50)
            self.assertEqual(first['rows'],second['rows'])
            self.assertNotIn('62',[r['person_id'] for r in first['rows']])
            self.assertNotIn('61',[r['person_id'] for r in first['rows']])
            self.assertEqual(before,hashlib.sha256(db.read_bytes()).hexdigest())
            self.assertFalse(Path(str(db)+'-wal').exists())
            Path(str(db)+'-wal').touch()
            with self.assertRaisesRegex(ValueError,'sidecars'):selector.sample(db,1)


if __name__=='__main__':unittest.main()
