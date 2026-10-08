from io import BytesIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from pypdf import PdfReader

from backend.app.repositories.summary import normalized_summary_filters, summary_matrix
from backend.app.services.summary_booklet_contents import contents_selection, generate_contents_pdf, reward_heading
from tests import test_ale474_summary_booklets as fixture


class HeadingTests(unittest.TestCase):
    def test_safe_forms_and_exact_neutral_names(self):
        for name, expected in (
            ('Орден Славы I степени', 'Кавалеры ордена Славы I степени'),
            ('Медаль «За отвагу»', 'Награждённые медалью «За отвагу»'),
            ('Знак «Почётный работник»', 'Кавалеры и награждённые — Знак «Почётный работник»'),
            ('Медаль юбилейная «50 лет»', 'Кавалеры и награждённые — Медаль юбилейная «50 лет»'),
            ('Орден Красное Знамя', 'Кавалеры и награждённые — Орден Красное Знамя'),
        ):
            with self.subTest(name=name):
                self.assertEqual(reward_heading(name), expected)

    def test_long_heading_and_table_pagination(self):
        name = 'Знак «' + 'Историческое памятное наименование ' * 8 + 'III степени»'
        rows = [dict(fio=f'Кавалер {i:04d}', pdf_reward_numbers=[f'MATCH-{i:04d}']) for i in range(180)]
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'long.pdf'
            generate_contents_pdf(rows, path, dict(title=reward_heading(name), context='Категория: Памятные знаки'))
            texts = [p.extract_text() for p in PdfReader(path).pages]
        self.assertIn('III степени»', ' '.join(texts[0].split()))
        self.assertLess(texts[0].index('III степени»'), texts[0].index('Содержание буклета'))
        self.assertIn(rows[0]['fio'], texts[0])
        for text in texts:
            self.assertIn('ФИО', text)
            self.assertIn('Номер ордена', text)
        text = '\n'.join(texts)
        for row in rows:
            self.assertEqual(text.count(row['fio']), 1)
            self.assertEqual(text.count(row['pdf_reward_numbers'][0]), 1)
        self.assertEqual(sorted([r['fio'] for r in rows], key=text.index), [r['fio'] for r in rows])
        self.assertIn('Всего кавалеров: 180', text)


class SelectionTests(unittest.TestCase):
    _create_db = fixture.SummaryBookletsTests._create_db
    setUp = fixture.SummaryBookletsTests.setUp
    tearDown = fixture.SummaryBookletsTests.tearDown
    wait = fixture.SummaryBookletsTests.wait

    def test_snapshot_freezes_selected_name_with_matching_rows(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("update guide_lev_3 set name='Орден Славы I степени' where id=3")
        filters = normalized_summary_filters(name_id=3)
        matrix = summary_matrix(self.db_path, filters)
        selection = contents_selection(self.db_path, matrix, filters)
        token = self.jobs.snapshot(self.settings, matrix['rows'], selection)
        selection['title'] = 'Изменённый объект'
        with sqlite3.connect(self.db_path) as db:
            db.execute("update guide_lev_3 set name='Медаль «Другая»' where id=3")
        job = self.jobs.start(self.settings, token)
        self.assertEqual(self.wait(job)['state'], 'ready')
        first = PdfReader(BytesIO(self.jobs.content(self.settings, job['id']))).pages[0].extract_text()
        self.assertIn('Кавалеры ордена Славы I степени', ' '.join(first.split()))
        self.assertNotIn('Другая', first)
        self.assertNotIn('Изменённый объект', first)
        self.assertIn('\nA\n', first)
        self.assertNotIn('\nB\n', first)

    def test_multiple_and_empty_selection_never_invent_one_reward(self):
        filters = normalized_summary_filters()
        matrix = summary_matrix(self.db_path, filters)
        selection = contents_selection(self.db_path, matrix, filters)
        self.assertEqual(selection['title'], 'Кавалеры и награждённые по выбранным наградам')
        self.assertIn('без ограничений', selection['context'])
        filters = normalized_summary_filters(name_id=999)
        matrix = summary_matrix(self.db_path, filters)
        token = self.jobs.snapshot(self.settings, matrix['rows'], contents_selection(self.db_path, matrix, filters))
        with self.assertRaisesRegex(ValueError, 'нет кавалеров'):
            self.jobs.start(self.settings, token)
