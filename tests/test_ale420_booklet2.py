import asyncio
import hashlib
from pathlib import Path
import re
import sqlite3
import unittest
from unittest.mock import patch
from urllib.parse import quote

from backend.app.routers import persons
from backend.app.routers.templates import templates
from backend.app.services.booklet2 import booklet2_context, generate_booklet2_pdf
from backend.app.services.booklets import generate_person_booklet_pdf, person_booklet_context
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

    def test_booklet2_has_no_photo_captions_and_preserves_media(self):
        from reportlab.platypus import Paragraph
        context = booklet2_context(self.settings, 1)
        photos = [p for p in [context['portrait'], context['lead_document'], context['inset_photo'], *context['editorial_media'], *[p for group in context['reward_photo_groups'] for p in group['photos']]] if p]
        html = persons.person_booklet2(FakeRequest(path='/persons/1/booklet2'), 1).body.decode()
        self.assertNotIn('<figcaption', html)
        figures = re.findall(r'<figure\b[^>]*>(.*?)</figure>', html, re.S)
        self.assertEqual(len(figures), len(photos))
        for figure, entry in zip(figures, photos):
            self.assertIn(quote(entry['path'], safe=''), figure)
            self.assertIn(f'alt="{entry["label"]}"', figure)
            self.assertEqual(re.sub(r'<[^>]+>', '', figure).strip(), '')
        old = persons.person_booklet(FakeRequest(), 1).body.decode()
        self.assertEqual(old.count('<figcaption'), len(photos))

        paragraphs = []
        original = Paragraph.__init__

        def capture(paragraph, text, style=None, *args, **kwargs):
            paragraphs.append(text)
            return original(paragraph, text, style, *args, **kwargs)

        with patch.object(Paragraph, '__init__', capture):
            generate_booklet2_pdf(self.settings, 1, self.root/'no-captions.pdf')
        for entry in photos:
            self.assertNotIn(entry['label'], paragraphs)
        self.assertIn('Награды', paragraphs)
        for group in context['reward_photo_groups']:
            self.assertIn(group['title'], paragraphs)

    def test_ordinary_pdf_captions_remain_centered_under_their_images(self):
        from reportlab.platypus import Image, Paragraph
        original_image, original_paragraph = Image.draw, Paragraph.draw
        for generate in (generate_person_booklet_pdf,):
            images, captions = [], []

            def point(canvas, x, y):
                a, b, c, d, e, f = canvas._currentMatrix
                return a*x+c*y+e, b*x+d*y+f

            def image_draw(image):
                images.append((point(image.canv, image.drawWidth/2, image.drawHeight/2)[0], point(image.canv, image.drawWidth/2, 0)[1], image.drawWidth))
                return original_image(image)

            def paragraph_draw(paragraph):
                if paragraph.style.name in {'BookletPhotoCaption', 'EditorialPhotoCaption'}:
                    center_x, bottom, width = images[-1]
                    caption_top = point(paragraph.canv, paragraph.width/2, paragraph.height)
                    self.assertEqual(paragraph.style.alignment, 1)
                    self.assertAlmostEqual(center_x, caption_top[0], delta=.1)
                    self.assertGreater(bottom, caption_top[1])
                    self.assertLess(bottom-caption_top[1], 12)
                    self.assertLessEqual(paragraph.width, width+6.01)
                    captions.append(paragraph.getPlainText())
                return original_paragraph(paragraph)

            with self.subTest(flow=generate.__name__), patch.object(Image, 'draw', image_draw), patch.object(Paragraph, 'draw', paragraph_draw):
                generate(self.settings, 1, self.root/'captions.pdf')
            context = person_booklet_context(self.settings, 1)
            expected = [p['label'] for p in [*context['identity_photos'], *context['person_documents'], *[p for group in context['reward_photo_groups'] for p in group['photos']]]]
            self.assertCountEqual(captions, expected)


if __name__ == '__main__':
    unittest.main()
