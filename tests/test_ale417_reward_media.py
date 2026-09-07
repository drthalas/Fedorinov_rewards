from pathlib import Path
import unittest

from backend.app.services.photos import REWARD_PHOTO_FIELDS, PERSON_PHOTO_FIELDS
from backend.app.services.summary_pdf import normalize_summary_pdf_media_fields

ROOT = Path(__file__).resolve().parents[1]


class RewardMediaPresentationTests(unittest.TestCase):
    def test_hidden_legacy_stock_value_is_preserved(self):
        template = (ROOT / "backend/app/templates/reward_form.html").read_text(encoding="utf-8")
        self.assertNotIn('name="instock" type="checkbox"', template)
        self.assertNotIn("В наличии", template)
        self.assertIn('name="instock" type="hidden" value="{{ \'true\' if reward.instock else \'\' }}"', template)

    def test_only_reward_document_labels_change(self):
        reward = {item.field: item for item in REWARD_PHOTO_FIELDS}
        person = {item.field: item for item in PERSON_PHOTO_FIELDS}
        self.assertEqual(reward["book1_foto"].label, "Дополнительный документ 1")
        self.assertEqual(reward["book2_foto"].label, "Дополнительный документ 2")
        self.assertEqual(reward["book1_foto"].stem, "книжка_1")
        self.assertEqual(person["book1_foto"].label, "Фото наградной книжки, сторона 1")
        self.assertEqual(reward["reward_list"].label, "Наградной лист")

    def test_grouped_selector_maps_existing_slots_without_collisions(self):
        selector = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8").split('data-summary-pdf-options-dialog', 1)[1].split('</dialog>', 1)[0]
        for value, label in (
            ("front_foto,back_foto", "Фото награды"),
            ("reward_book1_foto,reward_book2_foto", "Фото дополнительных документов"),
            ("reward_list", "Фото наградного листа"),
        ):
            self.assertIn(f'value="{value}"', selector)
            self.assertIn(label, selector)
            self.assertEqual(normalize_summary_pdf_media_fields(value), tuple(value.split(",")))
        self.assertNotIn('value="front_foto"', selector)
        self.assertNotIn('value="back_foto"', selector)
