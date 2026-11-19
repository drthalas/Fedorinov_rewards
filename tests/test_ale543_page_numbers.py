"""Combined page references use final page offsets, including a multipage contents."""
from io import BytesIO
import re
import sqlite3
import unittest

from pypdf import PdfReader

from backend.app.services.booklets import generate_person_booklet_pdf
from tests import test_ale474_summary_booklets as fixture


def footer_numbers(page):
    numbers = []

    def collect(text, cm, tm, font, size):
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        if 0 <= y < 25 and text.strip():
            numbers.extend(text.split())

    page.extract_text(visitor_text=collect)
    return numbers


class CombinedPageNumberTests(unittest.TestCase):
    _create_db = fixture.SummaryBookletsTests._create_db
    setUp = fixture.SummaryBookletsTests.setUp
    tearDown = fixture.SummaryBookletsTests.tearDown
    wait = fixture.SummaryBookletsTests.wait
    snapshot = fixture.SummaryBookletsTests.snapshot

    def test_multipage_contents_variable_blocks_and_one_continuous_footer(self):
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "update person set biography=? where id=1",
                ('\n\n'.join(f'Раздел {i:03}. Подробная биография и наградные документы. ' * 8
                             for i in range(75)),),
            )
            for index in range(80):
                person_id = 1000 + index
                connection.execute(
                    "insert into person(id,fio,birthday,id_rank) values(?,?,?,1)",
                    (person_id, f'Кавалер {index:04}', '1900'),
                )
                connection.execute(
                    "insert into rewards(id,person_id,id_name,number) values(?,?,1,?)",
                    (person_id, person_id, f'MAP-{index:04}'),
                )
        job = self.jobs.start(self.settings, self.snapshot())
        self.assertEqual(self.wait(job)['state'], 'ready')
        pdf = PdfReader(BytesIO(self.jobs.content(self.settings, job['id'])))
        texts = [page.extract_text() for page in pdf.pages]
        block_starts = [i for i, text in enumerate(texts) if 'БУКЛЕТ КАВАЛЕРА' in text]
        contents_pages = block_starts[0]
        self.assertGreater(contents_pages, 1)
        self.assertEqual(len(block_starts), 85)
        self.assertGreater(max(b - a for a, b in zip(block_starts, block_starts[1:])), 1)
        self.assertIn('Страница', '\n'.join(texts[:contents_pages]))
        for number, page in enumerate(pdf.pages, 1):
            self.assertEqual(footer_numbers(page), [str(number)], f'Page {number}')
        contents = '\n'.join(texts[:contents_pages])
        for index in range(80):
            fio = f'Кавалер {index:04}'
            matched = re.search(rf'{re.escape(fio)}\s+1900\s+капитан\s+MAP-{index:04}\s+(\d+)', contents)
            self.assertIsNotNone(matched, fio)
            number = int(matched[1])
            self.assertGreater(number, contents_pages)
            self.assertIn('БУКЛЕТ КАВАЛЕРА', texts[number - 1])
            self.assertIn(fio, texts[number - 1])
        self.assertTrue(all(len(text.strip()) > 5 for text in texts))

    def test_individual_booklet_keeps_local_page_numbers(self):
        result = generate_person_booklet_pdf(self.settings, 1, self.root / 'individual.pdf')
        pdf = PdfReader(result.path)
        for number, page in enumerate(pdf.pages, 1):
            self.assertEqual(footer_numbers(page), [str(number)])
