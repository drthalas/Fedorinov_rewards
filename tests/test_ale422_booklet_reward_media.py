import hashlib
from pathlib import Path
import re
import sqlite3
import unittest
from unittest.mock import patch
from urllib.parse import quote

from PIL import Image

from backend.app.routers import persons
from backend.app.services import summary_pdf
from backend.app.services.booklet2 import generate_booklet2_pdf
from backend.app.services.booklets import generate_person_booklet_pdf, person_booklet_context
from tests import test_ale419_booklet_dossier as dossier
from tests.test_person_booklet import FakeRequest


SLOTS = ("front_foto", "back_foto", "book1_foto", "book2_foto", "reward_list")


class BookletRewardMediaTests(unittest.TestCase):
    _create_db = dossier.BookletDossierTests._create_db
    tearDown = dossier.BookletDossierTests.tearDown

    def setUp(self):
        dossier.BookletDossierTests.setUp(self)
        self.clear_reward_media()
        for index, slot in enumerate(SLOTS):
            Image.new("RGB", (120 + index * 20, 180), "#778899").save(self.root / self.slot_path(slot))

    @staticmethod
    def slot_path(slot):
        return f"Source/1/detail-{slot}.png"

    def clear_reward_media(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("update rewards set " + ", ".join(f"{slot}=null" for slot in SLOTS))

    def set_media(self, reward_id, **values):
        self.assertTrue(set(values).issubset(SLOTS))
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "update rewards set " + ", ".join(f"{slot}=?" for slot in values) + " where id=?",
                [*values.values(), reward_id],
            )

    def assert_both_flows(self, expected_ids):
        from reportlab.platypus import Paragraph, Table

        before = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        context = person_booklet_context(self.settings, 1)
        groups = context["reward_photo_groups"]
        self.assertEqual([g["reward"]["id"] for g in groups], [12, 13, 11, 10, 14])
        selected = [g for g in groups if g["reward"]["id"] in expected_ids]
        self.assertEqual([g["reward"]["id"] for g in selected], expected_ids)
        expected_paths = [p["path"] for g in selected for p in g["photos"]]
        all_titles = [g["title"] for g in groups]

        flows = (
            ("booklet", persons.person_booklet, generate_person_booklet_pdf, "booklet-reward", "BookletReward"),
            ("booklet2", persons.person_booklet2, generate_booklet2_pdf, "editorial-award", "EditorialHeading"),
        )
        for flow, route, generate, detail_class, style in flows:
            with self.subTest(flow=flow):
                html = route(FakeRequest(path=f"/persons/1/{flow}"), 1).body.decode()
                upper_ids = re.findall(r'<li data-reward-id="(\d+)">', html)
                self.assertEqual(upper_ids, ["12", "13", "11", "10", "14"])
                details = re.findall(
                    rf'<(?:article|section) class="{detail_class}" data-reward-id="(\d+)">(.*?)</(?:article|section)>',
                    html, re.S,
                )
                self.assertEqual([int(id_) for id_, _ in details], expected_ids)
                detail_html = "".join(body for _, body in details)
                self.assertEqual(detail_html.count("<img "), len(expected_paths))
                self.assertEqual(detail_html.count("<figcaption>"), len(expected_paths) if flow == "booklet" else 0)
                for path in expected_paths:
                    self.assertIn(quote(path, safe=""), detail_html)
                for group in groups:
                    expected_count = 2 if group["reward"]["id"] in expected_ids else 1
                    self.assertEqual(html.count(group["title"]), expected_count)

                paragraphs, frames = [], []
                original_paragraph, original_table = Paragraph.__init__, Table.__init__

                def paragraph_init(paragraph, text, paragraph_style=None, *args, **kwargs):
                    original_paragraph(paragraph, text, paragraph_style, *args, **kwargs)
                    paragraphs.append((paragraph.style.name, paragraph.getPlainText()))

                def table_init(table, data, *args, **kwargs):
                    if kwargs.get("repeatRows") == 1:
                        frames.append(len(data))
                    original_table(table, data, *args, **kwargs)

                with (
                    patch.object(Paragraph, "__init__", paragraph_init),
                    patch.object(Table, "__init__", table_init),
                    patch.object(summary_pdf, "_summary_pdf_image", wraps=summary_pdf._summary_pdf_image) as render_image,
                ):
                    result = generate(self.settings, 1, self.root / f"{flow}-details.pdf")
                self.assertTrue(result.path.read_bytes().startswith(b"%PDF"))
                detail_titles = [text for name, text in paragraphs if name == style and text in all_titles]
                self.assertEqual(detail_titles, [g["title"] for g in selected])
                for group in groups:
                    self.assertEqual(
                        [text for _, text in paragraphs].count(group["title"]),
                        2 if group["reward"]["id"] in expected_ids else 1,
                    )
                rendered_details = [Path(call.args[0]).name for call in render_image.call_args_list if Path(call.args[0]).name.startswith("detail-")]
                self.assertEqual(rendered_details, [Path(path).name for path in expected_paths])
                if flow == "booklet":
                    self.assertTrue(all(count > 1 for count in frames), "no header-only PDF frames")
                    if not expected_ids:
                        self.assertEqual(frames, [])
                else:
                    self.assertFalse(any(name == "EditorialPhotoCaption" for name, _ in paragraphs))
        self.assertEqual(before, hashlib.sha256(self.db_path.read_bytes()).hexdigest())

    def test_all_empty_keeps_full_index_but_no_detail_headers_or_frames(self):
        self.assert_both_flows([])

    def test_each_single_reward_slot_is_sufficient(self):
        for slot in SLOTS:
            with self.subTest(slot=slot):
                self.clear_reward_media()
                self.set_media(12, **{slot: self.slot_path(slot)})
                self.assert_both_flows([12])

    def test_reference_only_is_not_reward_level_media(self):
        context = person_booklet_context(self.settings, 1)
        self.assertTrue(any(g["reference"]["available"] for g in context["reward_photo_groups"]))
        self.assert_both_flows([])

    def test_mixed_rewards_and_multiple_slots_keep_relative_order_and_mapping(self):
        self.set_media(12, **{slot: self.slot_path(slot) for slot in SLOTS})
        self.set_media(11, reward_list=self.slot_path("reward_list"))
        self.set_media(14, back_foto=self.slot_path("back_foto"))
        self.assert_both_flows([12, 11, 14])

    def test_unavailable_corrupt_and_unsafe_slots_do_not_create_details(self):
        (self.root / "Source/1/broken.jpg").write_bytes(b"not an image")
        self.set_media(12, front_foto="Source/1/missing.jpg", back_foto="Source/1/broken.jpg",
                       book1_foto="../outside.png", book2_foto="", reward_list="Source/1")
        self.assert_both_flows([])
        self.set_media(12, book2_foto=self.slot_path("book2_foto"))
        self.assert_both_flows([12])


if __name__ == "__main__":
    unittest.main()
