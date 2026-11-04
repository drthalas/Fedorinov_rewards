"""TEMP-only terminal navigation: receipt truth, recovery and empty quick search."""
from unittest.mock import patch
import json,sqlite3,unittest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.services import biography_enrichment as bio,enrichment_workflow as flow
from tests import test_ale513_review_choices as fixture
from tests.test_ale523 import complete_ui_schema

BASE='/data-maintenance/enrichment/biographies'

class TerminalNavigationTests(unittest.TestCase):
    setUp=fixture.ImportWorkflowTests.setUp
    execute=fixture.ImportWorkflowTests.execute
    query=fixture.ImportWorkflowTests.query
    content=fixture.ImportWorkflowTests.content
    preview=fixture.ImportWorkflowTests.preview

    def committed(self):
        token,_=self.preview();view=flow.workspace(self.settings,token)
        operation,_=flow.prepare_workspace(self.settings,token,view['revision'],[])
        result=flow.commit_import(self.settings,operation)
        return token,operation,result

    def test_completed_navigation_never_loads_original_or_plan_or_classifier(self):
        token,operation,result=self.committed();before=self.db.read_bytes()
        original=bio.load_preview
        def load(settings,key):
            self.assertNotIn(key,[token,operation]);return original(settings,key)
        with patch.object(bio,'load_preview',side_effect=load),patch.object(flow,'workspace',side_effect=AssertionError('revalidation')),TestClient(app) as client:
            for _ in range(2):
                response=client.get(BASE+'/preview/'+token)
                self.assertEqual(response.status_code,200);self.assertIn('Импорт завершён',response.text)
                self.assertNotIn('data-review-row=',response.text);self.assertNotIn('data-import-plan',response.text)
                self.assertIn('type="file"',response.text);self.assertIn('Полный отчёт',response.text)
        self.assertEqual(before,self.db.read_bytes())
        self.assertEqual(bio.load_preview(self.settings,token)['state'],'preview')
        self.assertEqual(flow.committed_result(self.settings,operation),result)
        self.assertTrue((self.root/'signing.key').exists())

    def test_disposable_summary_loss_and_write_failure_keep_durable_recovery(self):
        token,operation,result=self.committed()
        (self.root/(flow._terminal_key(self.settings,token)+'.json')).unlink()
        with patch.object(flow,'workspace',side_effect=AssertionError('classifier')):
            value=flow.terminal_preview(self.settings,token)
        self.assertEqual(value['summary']['saved'],1)
        self.assertEqual(flow.commit_import(self.settings,operation),result)
        self.assertEqual(self.query("select count(*) from logs where action like 'enrichment_import:%'"),[(1,)])
        # A new committed operation remains successful if derived state is unwritable.
        self.execute('delete from logs;update person set biography=null')
        token,_=self.preview();view=flow.workspace(self.settings,token)
        op,_=flow.prepare_workspace(self.settings,token,view['revision'],[])
        with patch.object(flow,'_save_terminal',side_effect=OSError('TEMP failure')):
            result=flow.commit_import(self.settings,op)
        self.assertEqual(result['saved'],1);self.assertIsNotNone(flow.committed_result(self.settings,op))

    def test_cache_cannot_claim_success_without_receipt_and_failure_keeps_resume(self):
        token,operation,_=self.committed();self.execute('delete from logs')
        with TestClient(app) as client:
            response=client.get(BASE+'/preview/'+token)
            self.assertEqual(response.status_code,503);self.assertIn('data-resume-error',response.text)
            self.assertIn('data-import-success hidden',response.text)
            self.assertIn('Повторить загрузку',response.text)
        with self.assertRaises(bio.ValidationError):flow.terminal_preview(self.settings,token)

    def test_active_preview_and_explicit_full_report_still_validate(self):
        token,_=self.preview()
        with patch.object(flow,'workspace',wraps=flow.workspace) as workspace,TestClient(app) as client:
            response=client.get(BASE+'/preview/'+token)
            self.assertEqual(response.status_code,200);self.assertIn('data-import-plan',response.text);workspace.assert_called_once()
        view=flow.workspace(self.settings,token);op,_=flow.prepare_workspace(self.settings,token,view['revision'],[]);flow.commit_import(self.settings,op)
        with patch.object(flow,'workspace',wraps=flow.workspace) as workspace,TestClient(app) as client:
            response=client.get(BASE+'/preview/'+token+'?details=true')
            self.assertEqual(response.status_code,200);workspace.assert_called_once()
            self.assertIn('data-import-plan',response.text)

    def test_statistics_failure_does_not_show_zero_and_summary_retry_is_available(self):
        token,_,_=self.committed()
        with patch.object(bio,'statistics',side_effect=sqlite3.OperationalError('TEMP')),TestClient(app) as client:
            response=client.get(BASE+'/preview/'+token)
            self.assertEqual(response.status_code,503);self.assertIn('data-population-total>—',response.text)
            self.assertIn('Импорт завершён',response.text)

    def test_search_zero_found_clear_keep_total_separate(self):
        complete_ui_schema(self.db)
        with TestClient(app) as client:
            empty=client.get('/legacy?tab=rewards&person_q=уапавир').text
            self.assertIn('Найдено: 0 · Всего: 1 записей',empty)
            self.assertIn('Ничего не найдено',empty);self.assertIn('Попробуйте изменить запрос',empty)
            self.assertIn('class="legacy-person-indexes" hidden',empty)
            self.assertNotIn('data-person-name=',empty)
            found=client.get('/legacy?tab=rewards&person_q=Ермакова').text
            self.assertIn('Найдено: 1 · Всего: 1 записей',found);self.assertIn('data-person-name=',found)
            clear=client.get('/legacy?tab=rewards').text
            self.assertNotIn('class="legacy-person-indexes" hidden',clear);self.assertIn('data-person-name=',clear)

if __name__=='__main__':unittest.main()
