import asyncio
import hashlib
from pathlib import Path
import re
import sqlite3
import unittest
from unittest.mock import patch

from backend.app.routers import persons
from backend.app.routers.templates import templates
from backend.app.services.booklet2 import booklet2_context, generate_booklet2_pdf
from backend.app.services.booklets import person_booklet_context
from tests import test_ale419_booklet_dossier as fixture
from tests.test_person_booklet import FakeRequest


class Booklet2Tests(unittest.TestCase):
    _create_db = fixture.BookletDossierTests._create_db
    setUp = fixture.BookletDossierTests.setUp
    tearDown = fixture.BookletDossierTests.tearDown

    def test_reuses_all_media_roles_and_ranked_awards_without_writes(self):
        before = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        old = person_booklet_context(self.settings, 1)
        new = booklet2_context(self.settings, 1)
        all_person = [new['portrait'], new['lead_document'], new['inset_photo'], *new['editorial_media']]
        self.assertCountEqual([i['field'] for i in all_person if i], [i['field'] for i in [*old['identity_photos'], *old['person_documents']]])
        normalized = [{**group, 'photos': [{key: value for key, value in photo.items() if key not in {'ratio', 'wide'}} for photo in group['photos']]} for group in new['reward_photo_groups']]
        self.assertEqual(normalized, old['reward_photo_groups'])
        self.assertEqual(before, hashlib.sha256(self.db_path.read_bytes()).hexdigest())

    def test_separate_route_template_and_pdf(self):
        request = FakeRequest(path='/persons/1/booklet2')
        response = persons.person_booklet2(request, 1, return_to='https://invalid.example')
        self.assertEqual(response.status_code, 200)
        html = response.body.decode()
        self.assertIn('/persons/1/booklet2.pdf', html)
        self.assertIn('editorial-sheet', html)
        self.assertIn('href="/persons/1"', html)
        self.assertNotIn('booklet-document', html)
        old = persons.person_booklet(FakeRequest(), 1).body.decode()
        self.assertIn('booklet-document', old)
        self.assertNotIn('booklet2.css', old)
        pdf = asyncio.run(persons.person_booklet2_pdf(FakeRequest(), 1))
        self.assertEqual(pdf.media_type, 'application/pdf')
        self.assertIn('_booklet2_', pdf.filename)
        content = Path(pdf.path).read_bytes()
        self.assertTrue(content.startswith(b'%PDF'))
        self.assertIn(b'/Subtype /Form', content)
        for box in re.findall(rb'/MediaBox\s*\[([^]]+)\]', content):
            values = list(map(float, box.split()))
            self.assertAlmostEqual(values[2], 595.2756, places=2)
            self.assertAlmostEqual(values[3], 841.8898, places=2)

    def test_missing_media_collapses_and_long_biography_paginates(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("update person set person_foto=null, card1_foto=null, biography=?", ('Биография кавалера. ' * 1500,))
        context = booklet2_context(self.settings, 1)
        html = templates.env.get_template('person_booklet2.html').render(request=FakeRequest(), settings=self.settings, pdf_filename='test.pdf', **context)
        self.assertNotIn('src="None"', html)
        self.assertIsNone(context['portrait'])
        result = generate_booklet2_pdf(self.settings, 1, self.root/'long.pdf')
        self.assertGreater(len(re.findall(rb'/Type /Page\b', result.path.read_bytes())), 3)

    def test_save_cancel_does_not_generate(self):
        with patch.object(persons, 'choose_save_path', side_effect=persons.SaveDialogCancelled), patch.object(persons, 'generate_booklet2_pdf') as generate:
            result = asyncio.run(persons.person_booklet2_pdf(FakeRequest({'save_dialog': '1'}), 1))
        self.assertEqual(result.status_code, 303)
        self.assertIn('/booklet2?', result.headers['location'])
        generate.assert_not_called()

    def test_rank_insignia_uses_existing_reference(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute('alter table guide add column image_path text')
            db.execute("update guide set image_path='Source/1/portrait.png'")
        self.assertEqual(booklet2_context(self.settings, 1)['rank_insignia']['path'], 'Source/1/portrait.png')


if __name__ == '__main__':
    unittest.main()
