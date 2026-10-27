"""Focused export lifecycle, single picker guards and whole-database statistics."""
from io import BytesIO
import threading
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from backend.app.main import app
from backend.app.services import biography_enrichment as bio, enrichment_export_jobs as exports, enrichment_workflow as flow
from tests import test_ale513_workspace as fixture

BASE='/data-maintenance/enrichment/biographies'

class ExportWorkspaceTests(unittest.TestCase):
    setUp=fixture.WorkspaceTests.setUp
    execute=fixture.WorkspaceTests.execute
    query=fixture.WorkspaceTests.query
    mixed=fixture.WorkspaceTests.mixed

    def test_measured_export_packaging_ready_reconnect_and_signed_download(self):
        self.mixed(); before=self.db.read_bytes(); jobs=exports.ExportJobs(); op='a'*64
        entered=threading.Event(); release=threading.Event(); original=bio.export_workbook; observed=[]
        def controlled(settings,selection,limit,progress):
            def report(phase,done,total):
                observed.append((phase,done,total));progress(phase,done,total)
                if phase=='Формируем файл XLSX…':entered.set();self.assertTrue(release.wait(5))
            return original(settings,selection,limit,report)
        with patch.object(bio,'export_workbook',side_effect=controlled):
            self.assertEqual(jobs.start(self.settings,op,'',5)['state'],'queued')
            self.assertTrue(entered.wait(3)); status=jobs.status(self.settings,op)
            self.assertEqual((status['done'],status['total']),(5,5));self.assertIsNone(status['percent'])
            self.assertEqual(status['phase'],'Формируем файл XLSX…')
            with self.assertRaises(bio.ValidationError):jobs.download(self.settings,op)
            self.assertEqual(jobs.start(self.settings,op,'',5)['state'],'running')
            with self.assertRaises(bio.ValidationError):jobs.start(self.settings,op,'',4)
            release.set();jobs.futures[jobs._key(self.settings,op)].result(5)
        self.assertIn(('Подготавливаем записи…',1,5),observed)
        restored=exports.ExportJobs();self.assertEqual(restored.status(self.settings,op)['percent'],100)
        content=restored.download(self.settings,op); wb=load_workbook(BytesIO(content))
        self.assertEqual(wb[bio.METADATA_SHEET].sheet_state,'hidden');self.assertEqual(len(wb.active[1]),7);wb.close()
        for row in bio.read_rows(content):bio._snapshot(self.settings,row['values'])
        with patch.object(exports,'jobs',restored),TestClient(app) as client:
            r=client.get(BASE+'/export/operations/'+op+'/file');self.assertEqual(r.content,content)
            self.assertIn('attachment',r.headers['content-disposition'])
        self.assertEqual(self.db.read_bytes(),before)
        path=restored._path(self.settings,restored._key(self.settings,op));path.write_bytes(b'changed')
        with self.assertRaises(bio.ValidationError):restored.download(self.settings,op)

    def test_export_failure_interruption_and_single_picker(self):
        jobs=exports.ExportJobs();op='b'*64
        with patch.object(bio,'export_workbook',side_effect=bio.ValidationError('Нет пустых биографий.')):
            jobs.start(self.settings,op,'',20);jobs.futures[jobs._key(self.settings,op)].result(3)
        self.assertEqual(jobs.status(self.settings,op)['state'],'failed')
        key=jobs._key(self.settings,'c'*64);bio._save(self.settings,key,dict(created=__import__('time').time(),state='running'))
        self.assertEqual(exports.ExportJobs().status(self.settings,'c'*64)['state'],'interrupted')
        with TestClient(app) as client:
            html=client.get(BASE).text
            self.assertIn('<h1>Наполнение данных</h1>',html)
            self.assertEqual(html.count('type="file"'),1);self.assertNotIn('name="original"',html)
            self.assertNotIn('Исходная выгрузка для прежнего формата',html)
            self.assertLess(html.index('data-population>'),html.index('data-export-block>'))
            self.assertLess(html.index('data-export-block>'),html.index('id="import-block-title"'))
            self.assertNotIn('<details',html[html.index('data-export-block>'):html.index('class="bio-import-block"')])
            self.assertEqual(client.post(BASE+'/export/start',data={'operation':'e'*64,'limit':5},headers={'origin':'https://other.invalid'}).status_code,403)

    def test_unsafe_legacy_and_tampered_signed_snapshot_never_become_ready(self):
        token=self.mixed();rows=bio.read_rows(self.content)
        values=rows[0]['values']; values['snapshot']='';values['snapshot_signature']=''
        unsafe=bio._workbook(bio.HEADERS,[[values.get(h,'') for h in bio.HEADERS]])
        before=self.db.read_bytes()
        with TestClient(app) as client:
            r=client.post(BASE+'/preview',files={'file':('old.xlsx',unsafe)})
            self.assertIn('Скачайте актуальный шаблон',r.text)
        t,_=bio.preview(self.settings,unsafe);self.assertEqual(flow.workspace(self.settings,t)['counts']['ready'],0)
        values['snapshot']='{}';values['snapshot_signature']='bad'
        t,_=bio.preview(self.settings,bio._workbook(bio.HEADERS,[[values.get(h,'') for h in bio.HEADERS]]))
        self.assertEqual(flow.workspace(self.settings,t)['counts']['ready'],0)
        self.assertEqual(self.db.read_bytes(),before)

    def test_population_counts_unique_people_blank_semantics_and_committed_update(self):
        token=self.mixed();self.execute("insert into rewards(person_id,id_gos,id_catigory,id_sub_catigory,id_name,number) values(1,1,2,3,4,900);update person set biography='   ' where id=2;update person set biography='' where id=3;")
        # Only biography whitespace changed; signed identity and import subset are preserved.
        before=bio.population_statistics(self.settings)
        self.assertEqual(before,{'total':8,'filled':0,'empty':8})
        self.assertEqual({k:bio.statistics(self.settings)[k] for k in before},before)
        # The changed reward makes row 1 stale: build the normal fresh preview for commit.
        self.execute("delete from rewards where number=900;update person set biography=null;")
        token,_=bio.preview(self.settings,self.content);before=bio.population_statistics(self.settings)
        view=flow.workspace(self.settings,token);op,_=flow.prepare_workspace(self.settings,token,view['revision'],[])
        result=flow.commit_import(self.settings,op)
        with TestClient(app) as client:
            after=client.get(BASE+'/statistics').json()
            self.assertEqual(after['filled']-before['filled'],flow.result_summary(result)['biographies'])
            self.assertEqual(after['total'],before['total']);self.assertEqual(after['empty']+after['filled'],after['total'])
            html=client.get(BASE+'/preview/'+token).text
            self.assertIn('data-population-total>'+str(after['total']),html)
            self.assertIn('data-export-block',html);self.assertIn('data-import-success',html)

if __name__=='__main__':unittest.main()
