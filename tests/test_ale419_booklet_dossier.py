import hashlib
import sqlite3
import unittest
from unittest.mock import patch

from PIL import Image

from backend.app.repositories.persons import list_person_rewards
from backend.app.routers import persons as persons_router
from backend.app.routers.templates import templates
from backend.app.services.booklets import generate_person_booklet_pdf, person_booklet_context
from tests import test_person_booklet as fixture
from tests.test_person_booklet import FakeRequest


class BookletDossierTests(unittest.TestCase):
    _create_db = fixture.PersonBookletTests._create_db
    tearDown = fixture.PersonBookletTests.tearDown

    def setUp(self):
        fixture.PersonBookletTests.setUp(self)
        self.settings = persons_router.get_settings()
        for name, size in [("portrait", (200, 400)), ("landscape", (600, 200)), ("document", (300, 450))]:
            Image.new("RGB", size, "#ad9670").save(self.root / "Source" / "1" / f"{name}.png")
        with sqlite3.connect(self.db_path) as db:
            db.execute("alter table guide_lev_3 add column rating_rank integer")
            db.execute("alter table guide_lev_3 add column image_path text")
            db.execute("update guide_lev_3 set name='Без рейтинга', image_path='Source/1/portrait.png'")
            db.executemany("insert into guide_lev_3(id,idl,name,rating_rank) values (?,0,?,?)", [(2, "Вторая", 2), (3, "Первая", 1), (4, "Равный рейтинг", 1)])
            db.executemany("insert into rewards(id,person_id,id_name,number) values (?,1,?,?)", [(11, 2, "B"), (12, 3, "A"), (13, 4, "C"), (14, 1, "D")])
            db.execute("update person set main_foto='Source/1/landscape.png', rewards_foto='Source/1/portrait.png', card1_foto='Source/1/document.png', card2_foto='Source/1/document.png', book1_foto='Source/1/document.png', book2_foto='Source/1/document.png', link2='https://example.com/forum'")
            db.execute("update rewards set front_foto='Source/1/portrait.png', back_foto='Source/1/landscape.png', book1_foto='Source/1/document.png', book2_foto='Source/1/document.png', reward_list='Source/1/document.png' where id=12")

    def test_rating_order_is_booklet_only_and_shared_by_sections(self):
        context = person_booklet_context(self.settings, 1)
        expected = [12, 13, 11, 10, 14]
        self.assertEqual([row["id"] for row in context["rewards"]], expected)
        self.assertEqual([group["reward"]["id"] for group in context["reward_photo_groups"]], expected)
        self.assertEqual([row["id"] for row in list_person_rewards(self.db_path, 1)], [10, 11, 12, 13, 14])

    def test_photo_roles_and_reference_binding(self):
        context = person_booklet_context(self.settings, 1)
        self.assertEqual([p["field"] for p in context["identity_photos"]], ["person_foto", "main_foto", "rewards_foto"])
        self.assertEqual([p["field"] for p in context["person_documents"]], ["card1_foto", "card2_foto", "book1_foto", "book2_foto"])
        group = context["reward_photo_groups"][0]
        self.assertEqual([p["field"] for p in group["photos"]], ["front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list"])
        self.assertEqual(group["photos"][2]["label"], "Дополнительный документ 1")
        reference = context["reward_photo_groups"][3]["reference"]
        self.assertTrue(reference["available"])
        self.assertEqual(reference["path"], "Source/1/portrait.png")

    def test_corrupt_and_missing_media_are_not_printable_placeholders(self):
        (self.root / "Source" / "1" / "broken.jpg").write_bytes(b"not an image")
        with sqlite3.connect(self.db_path) as db:
            db.execute("update rewards set front_foto='Source/1/broken.jpg', back_foto='Source/1/missing.jpg' where id=12")
        context = person_booklet_context(self.settings, 1)
        self.assertEqual(len(context["reward_photo_groups"][0]["photos"]), 3)
        rendered = templates.env.get_template("person_booklet.html").render(request=FakeRequest(), pdf_filename="test.pdf", **context)
        self.assertNotIn("broken.jpg", rendered)
        self.assertNotIn("missing.jpg", rendered)
        self.assertNotIn("booklet-missing-photo", rendered)

    def test_html_pdf_same_hierarchy_and_bounded_multipage_images(self):
        from reportlab.platypus import SimpleDocTemplate, Table, Paragraph, Image as PDFImage
        from reportlab.lib.pagesizes import A4
        context = person_booklet_context(self.settings, 1)
        rendered = templates.env.get_template("person_booklet.html").render(request=FakeRequest(), pdf_filename="test.pdf", **context)
        headings = ["Все награды кавалера", "Краткая биография", "Документы кавалера", 'class="booklet-reward"', "Ссылки", "Комментарий / заметки"]
        self.assertEqual([rendered.index(h) for h in headings], sorted(rendered.index(h) for h in headings))
        self.assertIn("1910 года рождения", rendered)
        self.assertNotIn("<dl", rendered)
        self.assertNotIn("Цена покупки", rendered)
        self.assertNotIn("Главное фото", rendered)
        text, images = [], []
        original = SimpleDocTemplate.build

        def collect(item):
            if isinstance(item, Paragraph):
                text.append(item.getPlainText())
            elif isinstance(item, PDFImage):
                images.append(item)
            elif isinstance(item, Table):
                if item.repeatRows == 1:
                    item.wrap(516, 700)
                    fragments = item.split(516, 80)
                    self.assertTrue(not fragments or all(len(part._cellvalues) > 1 for part in fragments))
                for row in item._cellvalues:
                    for cell in row:
                        collect(cell)
            elif isinstance(item, (tuple, list)):
                for child in item:
                    collect(child)

        def capture(doc, story, *args, **kwargs):
            self.assertEqual(doc.pagesize, A4)
            collect(story)
            return original(doc, story, *args, **kwargs)

        before = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        with patch.object(SimpleDocTemplate, "build", capture):
            result = generate_person_booklet_pdf(self.settings, 1, self.root / "dossier.pdf")
        self.assertEqual(before, hashlib.sha256(self.db_path.read_bytes()).hexdigest())
        self.assertTrue(result.path.read_bytes().startswith(b"%PDF"))
        self.assertIn("1910 года рождения", " ".join(text))
        sequence = ["Все награды кавалера", "Краткая биография", "Документы кавалера", "Ссылки", "Комментарий / заметки"]
        self.assertEqual([text.index(h) for h in sequence], sorted(text.index(h) for h in sequence))
        self.assertGreater(len(images), 12)
        for image in images:
            self.assertLessEqual(image.drawHeight, 80 * 72 / 25.4 + 0.01)
            self.assertLessEqual(image.drawWidth, 260)
            self.assertAlmostEqual(image.drawWidth / image.drawHeight, image.imageWidth / image.imageHeight)
