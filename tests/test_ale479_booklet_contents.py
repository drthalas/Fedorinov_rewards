from io import BytesIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from pypdf import PdfReader
from backend.app.repositories.summary import normalized_summary_filters
from backend.app.services.summary_booklet_contents import generate_contents_pdf
from tests import test_ale474_summary_booklets as fixture


class ContentsSelectionTests(unittest.TestCase):
    _create_db = fixture.SummaryBookletsTests._create_db
    setUp = fixture.SummaryBookletsTests.setUp
    tearDown = fixture.SummaryBookletsTests.tearDown
    wait = fixture.SummaryBookletsTests.wait
    snapshot = fixture.SummaryBookletsTests.snapshot
    def test_matching_numbers_are_frozen_and_exclude_other_rewards(self):
        token = self.snapshot(normalized_summary_filters(name_id='3'))
        with sqlite3.connect(self.db_path) as db:
            db.execute("update rewards set number='AFTER SNAPSHOT' where id=12")
        job = self.jobs.start(self.settings, token)
        self.assertEqual(self.wait(job)['state'], 'ready')
        text = PdfReader(BytesIO(self.jobs.content(self.settings, job['id']))).pages[0].extract_text()
        for heading in ('ФИО', 'Год рождения', 'Звание', 'Номер ордена', 'Всего кавалеров: 1'):
            self.assertIn(heading, ' '.join(text.split()))
        self.assertIn('\nA\n', text)
        self.assertNotIn('AFTER SNAPSHOT', text)
        self.assertNotIn('\nB\n', text)
        self.assertNotIn('\nC\n', text)
        self.assertNotIn('\nD\n', text)


class ContentsPaginationTests(unittest.TestCase):
    def test_large_table_repeats_headers_preserves_all_rows_and_total(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'contents.pdf'
            rows = [dict(fio=f'Кавалер {i:04d}', birthday='1900-01-01', rank_name='Подполковник',
                         pdf_reward_numbers=[f'MATCH-{i:04d}']) for i in range(180)]
            generate_contents_pdf(rows, path)
            reader = PdfReader(path)
            self.assertGreater(len(reader.pages), 1)
            texts = [page.extract_text() for page in reader.pages]
            for text in texts:
                self.assertIn('ФИО', text)
                self.assertIn('Номер ордена', text)
            text = '\n'.join(texts)
            for row in rows:
                self.assertEqual(text.count(row['fio']), 1)
                self.assertEqual(text.count(row['pdf_reward_numbers'][0]), 1)
            self.assertIn('Всего кавалеров: 180', text)
            self.assertEqual(sorted([r['fio'] for r in rows], key=text.index), [r['fio'] for r in rows])


if __name__ == '__main__':
    unittest.main()
