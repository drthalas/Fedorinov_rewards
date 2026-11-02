"""Focused diagnostics, unchanged guards, key lifecycle and payload-only recovery."""
from contextlib import closing
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import json,sqlite3,unittest,hashlib
from openpyxl import load_workbook
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import Settings
from backend.app.services import biography_enrichment as b,enrichment_workflow as f,enrichment_recovery as recovery
from scripts.diagnose_enrichment_import import diagnose
from tests import test_ale513_workspace as fixture

BASE='/data-maintenance/enrichment/biographies'

class ImportDiagnosticsTests(unittest.TestCase):
    setUp=fixture.WorkspaceTests.setUp
    execute=fixture.WorkspaceTests.execute
    query=fixture.WorkspaceTests.query
    mixed=fixture.WorkspaceTests.mixed

    def fresh(self):return b.export_workbook(self.settings,'',5000)
    def test_valid_roundtrip_and_unchanged_signature_protected_stale_guards(self):
        token=self.mixed();before=self.db.read_bytes()
        with patch.object(b,'_state_path',return_value=self.root):
            d=diagnose(self.settings,self.content,state_root=self.root)
            self.assertFalse(d['fatal']);self.assertEqual(d['prepared'],6)
            self.assertEqual(self.db.read_bytes(),before)
            self.execute("update person set fio='Изменённая карточка' where id=1")
            d=diagnose(self.settings,self.content,state_root=self.root)
            self.assertTrue(d['fatal']);self.assertEqual(d['failure_counts'],{'stale_identity':1});self.assertEqual(d['hmac_valid_rows'],8)
            self.assertEqual(d['guard_failures'][0]['person_id'],'1');self.assertIn('ФИО',d['guard_failures'][0]['fields'])
            self.assertIn('stale_identity',f.workspace(self.settings,token)['guard_counts'])
        self.execute("update person set fio='Тестов Человек Номер1' where id=1")
        row=b.read_rows(self.content)[0]['values']
        for key,value,code in [('snapshot_signature','0'*64,'signature_invalid'),('snapshot_signature','не подпись','signature_invalid'),('snapshot','','snapshot_missing'),('snapshot_signature','','signature_missing'),('ФИО','Чужая фамилия','protected_field_changed')]:
            with self.subTest(code=code):
                v=dict(row);v[key]=value;data=b._workbook(b.HEADERS,[[v.get(h,'') for h in b.HEADERS]])
                t,_=b.preview(self.settings,data);view=f.workspace(self.settings,t)
                self.assertTrue(view['fatal']);self.assertEqual(view['guard_counts'],{code:1})
                with self.assertRaises(b.ValidationError):f.prepare_workspace(self.settings,t,view['revision'],[])

    def test_readonly_diagnosis_reports_missing_and_unicode_signature_without_new_state(self):
        self.mixed();values=dict(b.read_rows(self.content)[0]['values'])
        for name,value,code in [('snapshot','','snapshot_missing'),('snapshot_signature','','signature_missing'),('snapshot_signature','не подпись','signature_invalid')]:
            with self.subTest(code=code):
                row=dict(values);row[name]=value
                data=b._workbook(b.HEADERS,[[row.get(h,'') for h in b.HEADERS]])
                before=self.db.read_bytes();key=(self.root/'signing.key').read_bytes()
                d=diagnose(self.settings,data,state_root=self.root)
                self.assertEqual(d['failure_counts'],{code:1});self.assertEqual(d['hmac_invalid_rows'],1)
                self.assertEqual(self.db.read_bytes(),before);self.assertEqual((self.root/'signing.key').read_bytes(),key)

    def test_fatal_ui_and_report_preserve_reason_and_never_promise_import(self):
        token=self.mixed();self.execute("update rewards set number=991 where person_id=1")
        with TestClient(app) as client:
            html=client.get(BASE+'/preview/'+token).text
            self.assertIn('Импорт остановлен: строк с ошибками проверки — 1.',html)
            self.assertIn('Подготовлены изменения',html);self.assertNotIn('Файл проверен.',html)
            self.assertNotIn('К импорту: биографий',html)
            report=client.get(BASE+'/report/'+token).json()
            self.assertFalse(report['import_allowed']);self.assertEqual(report['guard_counts'],{'stale_identity':1})
            self.assertEqual(report['guard_failures'][0]['person_id'],'1')
            self.assertIn('Награды и номера',report['guard_failures'][0]['fields'])
            serialized=json.dumps(report)
            self.assertNotIn('snapshot_signature',serialized);self.assertNotIn('signing.key',serialized)
            self.assertNotIn('Проверенная биография кавалера.',serialized)

    def test_concurrent_fields_revision_and_signed_malformed_snapshot_stay_blocked(self):
        token=self.mixed();view=f.workspace(self.settings,token)
        self.execute("update person set biography='Ручное изменение после preview' where id=1")
        changed=f.workspace(self.settings,token)
        self.assertEqual(changed['guard_counts'],{'concurrent_fields':1})
        with self.assertRaises(b.ValidationError):f.prepare_workspace(self.settings,token,view['revision'],[])
        self.assertEqual(self.query('select biography from person where id=1'),[('Ручное изменение после preview',)])
        values=dict(b.read_rows(self.content)[0]['values']);values['snapshot']=b.canonical({'version':2,'person':{'person_id':1}})
        values['snapshot_signature']=b._sign(self.settings,values['snapshot'])
        with self.assertRaises(b.ImportGuardError) as error:b._snapshot(self.settings,values)
        self.assertEqual(error.exception.code,'snapshot_invalid')

    def test_key_restart_update_cleanup_and_db_path_are_distinct(self):
        # Reproduce actual lifecycle in a separate TEMP namespace, no REAL key.
        with TemporaryDirectory() as folder,patch.object(b.tempfile,'gettempdir',return_value=folder),patch.object(b,'_state',side_effect=lambda settings: real_state(settings)):
            real_state=lambda s: self.make_state(b._state_path(s))
            data=self.fresh();values=b.read_rows(data)[0]['values'];s=self.settings
            path=b._state_path(s)/'signing.key';key=path.read_bytes()
            self.assertEqual(b._snapshot(s,values)['version'],2);self.assertEqual(path.read_bytes(),key)
            updated=s.model_copy(update={'app_install_dir':Path(folder)/'updated-install'})
            self.assertEqual(b._snapshot(updated,values)['version'],2);self.assertEqual(path.read_bytes(),key)
            moved=s.model_copy(update={'rewards_db_path':Path(folder)/'moved.sqlite'})
            with self.assertRaises(b.ValidationError):b._snapshot(moved,values)
            path.unlink();before=set(Path(folder).rglob('*'))
            d=diagnose(s,data);self.assertEqual(d['signing_key_state'],'missing')
            self.assertEqual(d['failure_counts'],{'signing_key_unavailable':len(d['results'])})
            self.assertEqual(set(Path(folder).rglob('*')),before)  # Diagnostic never creates replacement key.
            with self.assertRaises(b.ValidationError):b._snapshot(s,values)  # Existing release generates a different key.
            self.assertNotEqual(path.read_bytes(),key)

    @staticmethod
    def make_state(path):path.mkdir(parents=True,exist_ok=True);return path

    def test_recovery_authenticates_fresh_export_preserves_hidden_and_bio_and_commits_temp(self):
        token=self.mixed();fresh=self.fresh();before=self.db.read_bytes()
        with patch.object(b,'_state_path',return_value=self.root):
            out,report=recovery.recover(self.settings,self.content,fresh,expected_research_sha256=hashlib.sha256(self.content).hexdigest())
            self.assertEqual(report['biographies_copied'],7);self.assertFalse(report['review']);self.assertEqual(self.db.read_bytes(),before)
            with ZipFile(BytesIO(fresh)) as a,ZipFile(BytesIO(out)) as z:
                self.assertEqual(a.read('xl/worksheets/sheet2.xml'),z.read('xl/worksheets/sheet2.xml'))
            originals={e['values']['person_id']:e['values'] for e in b.read_rows(self.content)}
            for entry in b.read_rows(out):
                v=entry['values'];self.assertEqual(v['biography'],originals[v['person_id']]['biography']);b._snapshot(self.settings,v)
            t,_=b.preview(self.settings,out);view=f.workspace(self.settings,t)
            op,_=f.prepare_workspace(self.settings,t,view['revision'],[]);saved=f.commit_import(self.settings,op)
            self.assertEqual(saved['biographies'],6)
            # The exact same operation remains idempotent.
            self.assertEqual(f.commit_import(self.settings,op),saved)

    def test_recovery_changed_card_review_and_bad_fresh_signature_fail_closed(self):
        token=self.mixed();self.execute("update person set fio='Исправленное полное ФИО' where id=1")
        fresh=self.fresh()
        with patch.object(b,'_state_path',return_value=self.root):
            out,report=recovery.recover(self.settings,self.content,fresh,expected_research_sha256=hashlib.sha256(self.content).hexdigest())
            self.assertEqual(report['review'][0]['person_id'],'1');self.assertIn('fio',report['review'][0]['fields'])
            v=next(e['values'] for e in b.read_rows(out) if e['values']['person_id']=='1');self.assertFalse(v['biography'])
            with self.assertRaises(b.ValidationError):recovery.recover(self.settings,self.content,fresh,expected_research_sha256='0'*64)
            w=load_workbook(BytesIO(fresh));headers={c.value:c.column for c in w[b.METADATA_SHEET][1]};w[b.METADATA_SHEET].cell(2,headers['snapshot_signature'],'0'*64)
            stream=BytesIO();w.save(stream);w.close()
            with self.assertRaises(b.ValidationError):recovery.recover(self.settings,self.content,stream.getvalue(),expected_research_sha256=hashlib.sha256(self.content).hexdigest())

if __name__=='__main__':unittest.main()
