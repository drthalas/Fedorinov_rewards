from io import BytesIO
import gc
import sqlite3
import time
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.repositories.summary import normalized_summary_filters, summary_matrix
from backend.app.services.booklets import generate_person_booklet_pdf
from backend.app.services.summary_booklets import SummaryBookletError, SummaryBookletJobs
from tests import test_ale419_booklet_dossier as dossier


class SummaryBookletsTests(unittest.TestCase):
    _create_db = dossier.BookletDossierTests._create_db

    def setUp(self):
        dossier.BookletDossierTests.setUp(self)
        self.jobs = SummaryBookletJobs()
        with sqlite3.connect(self.db_path) as db:
            db.executemany("insert into person(id,fio) values (?,?)", [(2, 'Яковлев'), (3, 'Ёлкин'), (4, 'Егоров'), (5, 'Андреев')])

    def tearDown(self):
        for job in self.jobs.jobs.values():
            if job.directory:
                job.directory.cleanup()
        # The shared legacy fixture leaves committed SQLite handles for GC.
        # Windows cannot unlink its temp DB until these handles are closed.
        gc.collect()
        dossier.BookletDossierTests.tearDown(self)

    def wait(self, job):
        deadline = time.monotonic() + 30
        progress = []
        while time.monotonic() < deadline:
            state = self.jobs.status(self.settings, job['id'])
            progress.append(state['completed'])
            if state['state'] != 'running':
                self.assertEqual(progress, sorted(progress))
                return state
            time.sleep(.01)
        self.fail('Job did not finish')

    def snapshot(self, filters=None):
        matrix = summary_matrix(self.db_path, filters or normalized_summary_filters())
        return self.jobs.snapshot(self.settings, matrix['rows'])

    def test_empty_expired_and_wrong_database(self):
        token = self.jobs.snapshot(self.settings, [])
        for value in [token, 'unknown']:
            with self.assertRaises(SummaryBookletError):
                self.jobs.start(self.settings, value)
        token = self.snapshot()
        other = self.settings.model_copy(update={'rewards_db_path': self.root / 'other.sqlite'})
        with self.assertRaises(SummaryBookletError):
            self.jobs.start(other, token)
        with patch('backend.app.services.summary_booklets.TTL', -1):
            with self.assertRaises(SummaryBookletError):
                self.jobs.start(self.settings, token)

    def test_one_matches_ordinary_pdf_every_page(self):
        token = self.snapshot(normalized_summary_filters(name_id='1'))
        job = self.jobs.start(self.settings, token)
        state = self.wait(job)
        self.assertEqual((state['state'], state['completed'], state['percent']), ('ready', 1, 100))
        ordinary = generate_person_booklet_pdf(self.settings, 1, self.root / 'ordinary.pdf')
        expected = PdfReader(ordinary.path)
        actual = PdfReader(BytesIO(self.jobs.content(self.settings, job['id'])))
        self.assertIn('Содержание буклета', actual.pages[0].extract_text())
        self.assertEqual(len(actual.pages), len(expected.pages) + 1)
        for left, right in zip(actual.pages[1:], expected.pages):
            self.assertEqual(left.extract_text(), right.extract_text())
            self.assertEqual(left.get_contents().get_data(), right.get_contents().get_data())
            self.assertEqual(len(left.images), len(right.images))

    def test_membership_snapshot_alphabet_and_page_separation(self):
        token = self.snapshot()
        with sqlite3.connect(self.db_path) as db:
            db.execute("insert into person(id,fio) values (6,'Новый после Показать')")
        job = self.jobs.start(self.settings, token)
        self.assertEqual(self.wait(job)['state'], 'ready')
        reader = PdfReader(BytesIO(self.jobs.content(self.settings, job['id'])))
        titles = [p.extract_text().split('БУКЛЕТ КАВАЛЕРА\n')[1].split('\n')[0]
                  for p in reader.pages if 'БУКЛЕТ КАВАЛЕРА\n' in p.extract_text()]
        self.assertEqual(titles, ['Андреев', 'Егоров', 'Ёлкин', 'Иванов Иван', 'Яковлев'])
        contents = reader.pages[0].extract_text()
        self.assertEqual(sorted(titles, key=contents.index), titles)
        self.assertIn('Всего кавалеров: 5', contents)
        self.assertNotIn('Новый после Показать', contents)
        self.assertTrue(all(p.extract_text().count('БУКЛЕТ КАВАЛЕРА') <= 1 for p in reader.pages))

    def wait_state(self, job, expected):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            state = self.jobs.status(self.settings, job['id'])
            if state['state'] in expected:
                return state
            time.sleep(.01)
        self.fail('Expected state ' + str(expected))

    def test_pause_resume_stop_cleanup_and_fresh_start(self):
        # Rich ordinary booklets give control requests real in-flight work.
        with sqlite3.connect(self.db_path) as db:
            columns = [r[1] for r in db.execute('pragma table_info(person)')]
            for ident in range(10, 30):
                values = ['?' if c in ('id', 'fio') else c for c in columns]
                db.execute('insert into person select ' + ','.join(values) + ' from person where id=1',
                           (ident, 'Тест ' + str(ident)))
        token = self.snapshot()
        job = self.jobs.start(self.settings, token)
        self.jobs.control(self.settings, job['id'], 'pause')
        paused = self.wait_state(job, {'paused'})
        time.sleep(.3)
        self.assertEqual(self.jobs.status(self.settings, job['id'])['completed'], paused['completed'])
        self.assertEqual(self.jobs.start(self.settings, token)['id'], job['id'])
        self.assertEqual(self.jobs.active(self.settings)['id'], job['id'])
        self.jobs.control(self.settings, job['id'], 'resume')
        deadline = time.monotonic() + 10
        while self.jobs.status(self.settings, job['id'])['completed'] <= paused['completed']:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)
        self.jobs.control(self.settings, job['id'], 'pause')
        advanced = self.wait_state(job, {'paused'})
        self.assertGreater(advanced['completed'], paused['completed'])
        directory = self.jobs.jobs[job['id']].directory.name
        self.jobs.control(self.settings, job['id'], 'stop')
        self.assertEqual(self.wait_state(job, {'stopped'})['state'], 'stopped')
        from pathlib import Path
        self.assertFalse(Path(directory).exists())
        self.assertIsNone(self.jobs.active(self.settings))
        with self.assertRaises(SummaryBookletError):
            self.jobs.content(self.settings, job['id'])
        retry = self.jobs.start(self.settings, self.snapshot(normalized_summary_filters(name_id='1')))
        self.assertNotEqual(retry['id'], job['id'])
        self.assertEqual(self.wait(retry)['state'], 'ready')

    def test_running_stop_and_failure_retry(self):
        token = self.snapshot()
        job = self.jobs.start(self.settings, token)
        self.jobs.control(self.settings, job['id'], 'stop')
        self.assertEqual(self.wait_state(job, {'stopped'})['state'], 'stopped')
        with sqlite3.connect(self.db_path) as db:
            db.execute('alter table person rename to person_unavailable')
        try:
            failed = self.jobs.start(self.settings, token)
            self.assertEqual(self.wait(failed)['state'], 'failed')
            self.assertIsNone(self.jobs.jobs[failed['id']].directory)
            self.assertIsNone(self.jobs.active(self.settings))
        finally:
            with sqlite3.connect(self.db_path) as db:
                db.execute('alter table person_unavailable rename to person')
        retry = self.jobs.start(self.settings, token)
        self.assertEqual(self.wait(retry)['state'], 'ready')

    def test_http_job_and_download_native_copy(self):
        with patch('backend.app.routers.legacy.summary_booklet_jobs', self.jobs), TestClient(app) as client:
            response = client.post('/summary/booklets', data={'snapshot': self.snapshot()})
            self.assertEqual(response.status_code, 200)
            job = response.json()
            self.assertEqual(self.wait(job)['state'], 'ready')
            self.assertEqual(client.get('/summary/booklets/' + job['id']).json()['percent'], 100)
            pdf = client.get('/summary/booklets/' + job['id'] + '/file')
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b'%PDF-'))
            self.assertIn('X-Fedorinov-Open-Copy-Token', pdf.headers)
            self.assertEqual(client.get('/summary/booklets/unknown').status_code, 404)


if __name__ == '__main__':
    unittest.main()
