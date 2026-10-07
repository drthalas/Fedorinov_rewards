from io import BytesIO
import sqlite3
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from pypdf import PdfReader
from backend.app.main import app
from backend.app.repositories.summary import normalized_summary_filters
from backend.app.services.summary_booklets import SummaryBookletError
from backend.app.services.summary_pdf import generate_summary_matrix_pdf
from backend.app.services.summary_pdf_jobs import SummaryPDFJobs
from tests import test_ale474_summary_booklets as fixture


class SummaryPDFJobTests(unittest.TestCase):
    _create_db = fixture.SummaryBookletsTests._create_db
    tearDown = fixture.SummaryBookletsTests.tearDown
    wait = fixture.SummaryBookletsTests.wait
    wait_state = fixture.SummaryBookletsTests.wait_state

    def setUp(self):
        fixture.SummaryBookletsTests.setUp(self)
        self.jobs = SummaryPDFJobs()
        with sqlite3.connect(self.db_path) as db:
            db.execute("create table guide_lev_4(id integer primary key,idl integer,name text)")

    def test_zero_one_multiple_and_output_parity(self):
        with self.assertRaises(SummaryBookletError):
            self.jobs.prepare(self.settings, normalized_summary_filters(name_id='999'))
        for filters in [normalized_summary_filters(name_id='3'), normalized_summary_filters()]:
            for orientation in ['portrait', 'landscape']:
                job = self.jobs.prepare(self.settings, filters, 'main_foto,front_foto,book1_foto', 'true', 'reward_number', orientation)
                state = self.wait(job)
                self.assertEqual((state['state'], state['completed'], state['total'], state['percent']),
                                 ('ready', 1 if filters.name_id else 5, 1 if filters.name_id else 5, 100))
                baseline = generate_summary_matrix_pdf(self.settings, filters, 'main_foto,front_foto,book1_foto', 'true', 'reward_number', orientation)
                left = PdfReader(BytesIO(self.jobs.content(self.settings, job['id'])))
                right = PdfReader(BytesIO(baseline.content))
                self.assertEqual(len(left.pages), len(right.pages))
                for a,b in zip(left.pages,right.pages):
                    self.assertEqual(a.mediabox,b.mediabox)
                    self.assertEqual(a.extract_text(),b.extract_text())
                    self.assertEqual(a.get_contents().get_data(),b.get_contents().get_data())
                    self.assertEqual(len(a.images),len(b.images))

    def test_real_pause_play_stop_cleanup_double_start_restart(self):
        with sqlite3.connect(self.db_path) as db:
            for i in range(10,400):
                db.execute('insert into person(id,fio) values (?,?)',(i,f'Тест {i:04d}'))
        filters = normalized_summary_filters()
        job = self.jobs.prepare(self.settings, filters)
        self.jobs.control(self.settings, job['id'], 'pause')
        paused = self.wait_state(job, {'paused'})
        time.sleep(.3)
        frozen = self.jobs.status(self.settings, job['id'])
        self.assertEqual((frozen['completed'],frozen['total'],frozen['percent']),
                         (paused['completed'],paused['total'],paused['percent']))
        self.assertEqual(self.jobs.prepare(self.settings, filters)['id'],job['id'])
        self.jobs.control(self.settings,job['id'],'resume')
        self.assertEqual(self.wait_state(job,{'ready'})['percent'],100)
        job = self.jobs.prepare(self.settings,filters)
        self.jobs.control(self.settings,job['id'],'pause')
        self.wait_state(job,{'paused'})
        directory = self.jobs.jobs[job['id']].directory.name
        self.jobs.control(self.settings,job['id'],'stop')
        self.assertEqual(self.wait_state(job,{'stopped'})['state'],'stopped')
        from pathlib import Path
        self.assertFalse(Path(directory).exists())
        with self.assertRaises(SummaryBookletError):self.jobs.content(self.settings,job['id'])
        self.assertIsNone(self.jobs.active(self.settings))
        retry = self.jobs.prepare(self.settings,normalized_summary_filters(name_id='3'))
        self.assertNotEqual(retry['id'],job['id'])
        self.assertEqual(self.wait(retry)['state'],'ready')

    def test_worker_error_cleanup_retry_and_http_save_open_contract(self):
        with patch('backend.app.routers.legacy.summary_pdf_jobs', self.jobs), TestClient(app) as client:
            start = client.post('/summary/pdf-jobs',data={'name_id':'3','include_reward_number':'true'})
            self.assertEqual(start.status_code,200)
            job=start.json();self.assertEqual(self.wait(job)['state'],'ready')
            self.assertEqual(client.get('/summary/pdf-jobs/'+job['id']).json()['percent'],100)
            response=client.get('/summary/pdf-jobs/'+job['id']+'/file')
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.content.startswith(b'%PDF-'))
            self.assertIn('X-Fedorinov-Open-Copy-Token',response.headers)
            self.assertEqual(client.get('/summary/pdf-jobs/unknown').status_code,404)
            self.assertEqual(client.post('/summary/pdf-jobs',data={'name_id':'999'}).status_code,400)
        payload = self.jobs.jobs[job['id']].payload.copy()
        payload['matrix'] = dict(rows=[dict(id=1,photo_paths='invalid')])
        self.jobs.snapshots['broken']=(self.jobs.database(self.settings),payload,time.monotonic())
        broken = self.jobs.start(self.settings,'broken')
        self.assertEqual(self.wait(broken)['state'],'failed')
        self.assertIsNone(self.jobs.jobs[broken['id']].directory)
        self.assertIsNone(self.jobs.active(self.settings))
        with self.assertRaises(SummaryBookletError):self.jobs.content(self.settings,broken['id'])
        retry = self.jobs.prepare(self.settings,normalized_summary_filters(name_id='3'))
        self.assertEqual(self.wait(retry)['state'],'ready')


if __name__ == '__main__':unittest.main()
