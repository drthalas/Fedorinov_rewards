from io import BytesIO
import gc
import sqlite3
import time
import unittest
from threading import Event
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
        self.assertEqual(len(actual.pages), len(expected.pages))
        for left, right in zip(actual.pages, expected.pages):
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
        self.assertTrue(all(p.extract_text().count('БУКЛЕТ КАВАЛЕРА') <= 1 for p in reader.pages))

    def test_double_start_progress_failure_cleanup_and_retry(self):
        entered, release = Event(), Event()
        def fail(*args, **kwargs):
            kwargs['output_path'].write_bytes(b'partial')
            entered.set()
            release.wait(5)
            raise OSError('test failure')
        token = self.snapshot()
        with patch('backend.app.services.summary_booklets.generate_person_booklet_pdf', side_effect=fail), self.assertLogs('backend.app.services.summary_booklets', level='ERROR'):
            job = self.jobs.start(self.settings, token)
            self.assertTrue(entered.wait(5))
            second = self.jobs.start(self.settings, token)
            self.assertEqual(second['id'], job['id'])
            self.assertEqual(second['completed'], 0)
            with self.assertRaises(SummaryBookletError):
                self.jobs.content(self.settings, job['id'])
            release.set()
            self.assertEqual(self.wait(job)['state'], 'failed')
        self.assertIsNone(self.jobs.active(self.settings))
        retry = self.jobs.start(self.settings, token)
        self.assertNotEqual(retry['id'], job['id'])
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
