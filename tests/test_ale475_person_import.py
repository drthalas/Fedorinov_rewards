from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import sqlite3
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.config import Settings
from backend.app.db import open_write_connection
from backend.app.main import app
from backend.app.services import person_import as importer
from backend.app.services.write_guard import WriteBlockedError

HEADERS = ['Фамилия', 'Имя', 'Отчество', 'Номер ордена', 'Дата рождения', 'Звание']


def xlsx(rows, headers=HEADERS):
    workbook = Workbook()
    workbook.active.append(headers)
    for row in rows:
        workbook.active.append(row)
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def row(number=100, birth=None, rank=None, surname='Иванов'):
    return [surname, 'Иван', 'Иванович', number, birth, rank]


def create_database(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript('''
            create table guide (id integer primary key, name text);
            insert into guide values (10, 'Красноармеец'), (2, 'Капитан');
            create table person (id integer primary key autoincrement, fio text, birthday text, id_rank integer,
                                 comment text, biography text, person_foto text);
            create table rewards (id integer primary key autoincrement, person_id integer references person(id),
                id_gos integer, id_catigory integer, id_sub_catigory integer, id_name integer, id_link text,
                number integer, instock boolean, front_foto text);
            insert into person (id, fio, birthday, id_rank, comment) values (1, 'Иванов Иван Иванович', '1945', 10, 'Не менять');
            insert into rewards (id, person_id, id_name, number) values (1, 1, 4, 99);
        ''')
        for level in range(5):
            connection.execute(f'create table guide_lev_{level} (id integer primary key, idl integer, name text)')
        connection.execute("insert into guide_lev_0 values (1, -1, 'СССР')")
        connection.execute("insert into guide_lev_1 values (2, 1, 'Ордена')")
        connection.execute("insert into guide_lev_2 values (3, 2, 'Боевые')")
        connection.execute("insert into guide_lev_3 values (4, 3, 'Орден Славы I степени'), (5, 3, 'Орден Славы II степени')")
        connection.execute("insert into guide_lev_4 values (1, 4, 'https://example.org/reward')")
        connection.commit()


class PersonImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'test.sqlite'
        create_database(self.db)
        self.settings = Settings(rewards_data_dir=self.root, rewards_db_path=self.db, write_mode=True, read_only=False)
        self.env = patch.dict(os.environ, {
            'REWARDS_DATA_DIR': str(self.root), 'REWARDS_DB_PATH': str(self.db),
            'REWARDS_AUDIT_LOG': str(self.root / 'audit.log'), 'WRITE_MODE': 'true', 'READ_ONLY': 'false',
            'UPDATE_CHECK_ENABLED': 'false',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def query(self, sql, params=()):
        with closing(sqlite3.connect(self.db)) as connection:
            return connection.execute(sql, params).fetchall()

    def execute(self, sql):
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript(sql)
            connection.commit()

    def run_import(self, rows, name_id=4, headers=HEADERS):
        return importer.import_persons(self.settings, name_id, xlsx(rows, headers))

    def assert_counts(self, result, added, skipped, errors):
        self.assertEqual((result.added, result.skipped, len(result.errors)), (added, skipped, errors))

    def test_new_number_same_fio_creates_new_person_and_reference_without_media(self):
        baseline = self.query('select * from person where id=1'), self.query('select * from rewards where id=1')
        self.assert_counts(self.run_import([row()]), 1, 0, 0)
        self.assertEqual(self.query('select fio,birthday,id_rank,person_foto from person where id=2'), [('Иванов Иван Иванович','1945',10,None)])
        self.assertEqual(self.query('select person_id,id_gos,id_catigory,id_sub_catigory,id_name,number,id_link,instock,front_foto from rewards where id=2'), [(2,1,2,3,4,100,'https://example.org/reward',0,None)])
        self.assertEqual(baseline, (self.query('select * from person where id=1'), self.query('select * from rewards where id=1')))
        self.assertFalse((self.root / 'Source').exists())
        self.assertFalse((self.root / 'SourceMark').exists())

    def test_existing_number_skips_even_invalid_person_data(self):
        self.assert_counts(self.run_import([row(99, 'bad', 'unknown', '')]), 0, 1, 0)
        self.assertEqual(self.query('select count(*) from person'), [(1,)])

    def test_later_invalid_row_with_successful_in_file_number_is_skipped(self):
        self.assert_counts(self.run_import([row(100), row(100,2000,'unknown'),row(100,birth='=1')]),1,2,0)

    def test_existing_number_skips_formulas_in_unneeded_person_fields(self):
        self.assert_counts(self.run_import([row(99,birth='=1')]),0,1,0)

    def test_same_number_in_different_award_is_not_duplicate(self):
        self.assert_counts(self.run_import([row(99)], name_id=5), 1, 0, 0)

    def test_repeat_and_in_file_duplicates(self):
        rows = [row(100), row('0100'), row(101)]
        self.assert_counts(self.run_import(rows), 2, 1, 0)
        self.assert_counts(self.run_import(rows), 0, 3, 0)

    def test_lookup_matches_actual_award_number_not_person_position(self):
        self.execute('insert into rewards(person_id,id_name,number) values (1,4,777)')
        self.assert_counts(self.run_import([row(777), row(888)]), 1, 1, 0)

    def test_valid_dates_and_year_boundaries(self):
        values = [None, '', '  ', '12.05.1918', datetime(1919,6,7), '1920-07-08', 1800, 1999, 1941.0]
        self.assert_counts(self.run_import([row(i+100,value) for i,value in enumerate(values)]), len(values),0,0)
        self.assertEqual(self.query('select birthday from person where id>1 order by id'), [(x,) for x in ['1945','1945','1945','1918','1919','1920','1800','1999','1941']])

    def test_invalid_nonempty_birth_values_are_errors_not_defaults(self):
        values = ['n/a',1799,2000,'31.02.1918','1918garbage',True,1945.5]
        result = self.run_import([row(i+100,value) for i,value in enumerate(values)])
        self.assert_counts(result,0,0,len(values))
        self.assertEqual([error['row'] for error in result.errors], list(range(2,9)))
        self.assertEqual(self.query('select count(*) from person'), [(1,)])

    def test_rank_mapping_uses_existing_guide_only(self):
        result = self.run_import([row(100,rank='Капитан'),row(101,rank='  капитан  '),row(102,rank='Генерал'),row(103)])
        self.assert_counts(result,3,0,1)
        self.assertEqual(self.query('select id_rank from person where id>1 order by id'), [(2,),(2,),(10,)])
        self.assertEqual(self.query('select count(*) from guide'), [(2,)])

    def test_missing_or_ambiguous_fallback_stops_before_any_write(self):
        for change in ["delete from guide where id=10", "insert into guide values(10,'Красноармеец'),(11,'Красноармеец')"]:
            self.execute(change)
            with self.assertRaisesRegex(importer.ImportValidationError,'Красноармеец'):
                self.run_import([row(100,rank='Капитан'),row(101)])
            self.assertEqual(self.query('select count(*) from person'),[(1,)])

    def test_unknown_or_ambiguous_rank_is_failed_row(self):
        self.execute("insert into guide values(3, 'Капитан')")
        self.assert_counts(self.run_import([row(rank='Капитан')]),0,0,1)

    def test_required_names_and_numbers(self):
        rows = [row(number=x) for x in [None,'','abc',2.5,True,2**64]] + [row(900,surname=''),row(901,surname=123)]
        self.assert_counts(self.run_import(rows),0,0,len(rows))

    def test_blank_patronymic_and_optional_columns(self):
        self.assert_counts(self.run_import([['Петров','Петр',None,100]],headers=HEADERS[:4]),1,0,0)
        self.assertEqual(self.query('select fio,birthday,id_rank from person where id>1'), [('Петров Петр','1945',10)])

    def test_number_normalization_preserves_manual_semantics(self):
        self.assert_counts(self.run_import([row('  +100 '),row(100.0),row(0),row(-1)]),3,1,0)

    def test_missing_duplicate_headers_and_empty_sheet_are_global_errors(self):
        for content in [xlsx([row()],HEADERS[1:]),xlsx([row()],HEADERS+['Номер награды']),xlsx([])]:
            with self.assertRaises(importer.ImportValidationError):
                importer.import_persons(self.settings,4,content)
        self.assertEqual(self.query('select count(*) from person'),[(1,)])

    def test_invalid_and_truncated_xlsx(self):
        for content in [b'',b'not an XLSX',xlsx([row()])[:100]]:
            with self.assertRaises(importer.ImportValidationError):
                importer.import_persons(self.settings,4,content)
        self.assertEqual(self.query('select count(*) from person'),[(1,)])

    def test_late_malformed_xml_cannot_partially_import(self):
        good = ZipFile(BytesIO(xlsx([row(),row(101)])))
        bad = BytesIO()
        with ZipFile(bad,'w',ZIP_DEFLATED) as output:
            for name in good.namelist():
                data = good.read(name)
                output.writestr(name, data[:-30] if name=='xl/worksheets/sheet1.xml' else data)
        good.close()
        with self.assertRaises(importer.ImportValidationError):
            importer.import_persons(self.settings,4,bad.getvalue())
        self.assertEqual(self.query('select count(*) from person'),[(1,)])

    def test_invalid_reference_before_write(self):
        with self.assertRaisesRegex(importer.ImportValidationError,'награда'):
            self.run_import([row()],name_id=999)
        self.assertEqual(self.query('select count(*) from person'),[(1,)])

    def test_formulas_and_excel_errors_fail_with_row_numbers(self):
        result = self.run_import([row(100,birth='=1900+1'),row(101,rank='#VALUE!'),row(102)])
        self.assert_counts(result,1,0,2)
        self.assertEqual([error['row'] for error in result.errors],[2,3])

    def test_mixed_summary_and_existing_rows_unchanged(self):
        before = self.query('select * from person'),self.query('select * from rewards')
        result = self.run_import([row(100),row(99),row(101,2000),row(102,rank='unknown')])
        self.assert_counts(result,1,1,2)
        self.assertEqual(before,(self.query('select * from person where id=1'),self.query('select * from rewards where id=1')))

    def test_reward_constraint_rolls_back_person_but_continues_other_rows(self):
        self.execute("create trigger reject_number before insert on rewards when new.number=100 begin select raise(ABORT,'test'); end;")
        self.assert_counts(self.run_import([row(100),row(101)]),1,0,1)
        self.assertEqual(self.query('select count(*) from person'),[(2,)])
        self.assertEqual(self.query('select number from rewards order by id'),[(99,),(101,)])

    def test_fatal_write_failure_rolls_back_entire_batch(self):
        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, params=()):
                if 'insert into rewards' in sql.lower() and params[-2]==101:
                    raise sqlite3.OperationalError('simulated IO error')
                return super().execute(sql,params)
        def failing_open(*args):
            connection=sqlite3.connect(self.db, factory=FailingConnection)
            connection.row_factory=sqlite3.Row
            return connection
        with patch.object(importer,'open_write_connection',failing_open):
            with self.assertRaises(sqlite3.OperationalError):
                self.run_import([row(100),row(101)])
        self.assertEqual(self.query('select count(*) from person'),[(1,)])
        self.assertEqual(self.query('select count(*) from rewards'),[(1,)])

    def test_concurrent_imports_serialize_lookup_and_insert(self):
        content=xlsx([row(i) for i in range(100,150)])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _: importer.import_persons(self.settings,4,content),range(2)))
        self.assertEqual(sorted((r.added,r.skipped) for r in results),[(0,50),(50,0)])
        self.assertEqual(self.query('select count(*) from person'),[(51,)])

    def test_write_guard(self):
        with self.assertRaises(WriteBlockedError):
            importer.import_persons(self.settings.model_copy(update={'read_only':True}),4,xlsx([row()]))

    def test_limits_reject_before_write(self):
        for constant,value,content in [('MAX_UPLOAD_BYTES',10,xlsx([row()])),('MAX_UNPACKED_BYTES',10,xlsx([row()])),('MAX_ROWS',1,xlsx([row(),row(101)])),('MAX_COLUMNS',2,xlsx([row()]))]:
            with patch.object(importer,constant,value), self.assertRaises(importer.ImportValidationError):
                importer.import_persons(self.settings,4,content)
        self.assertEqual(self.query('select count(*) from person'),[(1,)])

    def test_http_flow_real_multipart_confirmation_and_summary(self):
        with TestClient(app) as client:
            choice=client.get('/persons/import')
            self.assertEqual(choice.status_code,200)
            self.assertIn('Кавалеров какого ордена',choice.text)
            self.assertNotIn('type="file"',choice.text)
            upload=client.get('/persons/import?id_name=4')
            self.assertIn('type="file"',upload.text)
            self.assertNotIn('type="file"',client.get('/persons/import?id_name=999').text)
            content=xlsx([row(100),row(99),row(101,2001)])
            denied=client.post('/persons/import',data={'id_name':'4'},files={'file':('test.xlsx',content)})
            self.assertEqual(denied.status_code,400)
            self.assertEqual(self.query('select count(*) from person'),[(1,)])
            response=client.post('/persons/import',data={'id_name':'4','confirm':'yes'},files={'file':('test.xlsx',content)})
            self.assertEqual(response.status_code,200)
            for text in ['Добавлено: 1','Пропущено — номер уже есть: 1','Ошибки: 1','<td>4</td>']:
                self.assertIn(text,response.text)

    def test_http_database_failure_reports_rollback(self):
        with TestClient(app) as client, patch.object(importer,'open_write_connection',side_effect=sqlite3.OperationalError('test')):
            response=client.post('/persons/import',data={'id_name':'4','confirm':'yes'},files={'file':('test.xlsx',xlsx([row()]))})
        self.assertEqual(response.status_code,503)
        self.assertIn('Все изменения этого файла отменены',response.text)
        self.assertEqual(self.query('select count(*) from person'),[(1,)])

    def test_http_bad_extension_and_disabled_writes(self):
        with TestClient(app) as client:
            self.assertEqual(client.post('/persons/import',data={'id_name':'4','confirm':'yes'},files={'file':('test.xls',xlsx([row()]))}).status_code,400)
            with patch.dict(os.environ,{'READ_ONLY':'true'}):
                self.assertEqual(client.get('/persons/import').status_code,403)
                self.assertEqual(client.post('/persons/import',data={'id_name':'4','confirm':'yes'},files={'file':('test.xlsx',xlsx([row()]))}).status_code,403)

    def test_5000_rows_performance_and_constant_lookup_count(self):
        content=xlsx([row(i,1918,'Капитан') for i in range(10000,15000)])
        statements=[]
        def tracked_open(*args):
            connection=open_write_connection(*args)
            connection.set_trace_callback(statements.append)
            return connection
        elapsed=[]
        with patch.object(importer,'open_write_connection',tracked_open):
            for expected in [(5000,0,0),(0,5000,0)]:
                start=time.perf_counter()
                result=importer.import_persons(self.settings,4,content)
                elapsed.append(time.perf_counter()-start)
                self.assert_counts(result,*expected)
        scans=[sql for sql in statements if sql.startswith('select trim(cast(number as text))')]
        self.assertEqual(len(scans),2)
        self.assertFalse(any('select' in sql.lower() and 'from person' in sql.lower() for sql in statements))
        self.assertEqual(self.query('select count(*) from person'),[(5001,)])
        self.assertLess(max(elapsed),20)
        print('ALE475_PERFORMANCE '+json.dumps({'rows':5000,'xlsx_bytes':len(content),'first_seconds':elapsed[0],'repeat_seconds':elapsed[1],'number_scans_per_import':1}))


if __name__=='__main__':
    unittest.main()
