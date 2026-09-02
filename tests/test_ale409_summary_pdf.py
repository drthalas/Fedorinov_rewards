from pathlib import Path
import unittest

from backend.app.repositories.summary import SUMMARY_MATRIX_PHOTO_COLUMNS
from backend.app.services.summary_pdf import normalize_summary_pdf_media_fields


ROOT = Path(__file__).resolve().parents[1]


class SummaryPDFOptionsTests(unittest.TestCase):
    def test_media_selection_is_allowlisted_ordered_and_unique(self) -> None:
        selected = normalize_summary_pdf_media_fields(
            "rewards_foto,person_foto,../../secret,book1_foto,rewards_foto"
        )
        self.assertEqual(selected, ("rewards_foto", "book1_foto"))
        self.assertNotIn("person_foto", selected)

    def test_all_optional_matrix_media_fields_are_selectable(self) -> None:
        optional = [field for field, _label in SUMMARY_MATRIX_PHOTO_COLUMNS if field != "person_foto"]
        self.assertEqual(normalize_summary_pdf_media_fields(optional), tuple(optional))

    def test_matrix_pdf_uses_confirmed_modal_before_save_form_submit(self) -> None:
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")
        script = (ROOT / "backend/app/static/summary_pdf_options.js").read_text(encoding="utf-8")

        self.assertIn("data-summary-pdf-options-dialog", template)
        self.assertIn("data-summary-pdf-options-open", template)
        self.assertIn("data-summary-pdf-options-cancel", template)
        self.assertIn("data-summary-pdf-options-confirm", template)
        self.assertIn('<span>Кавалер</span>', template)
        self.assertIn("checked disabled", template)
        self.assertIn('column.field != "person_foto"', template)
        self.assertIn("event.preventDefault()", script)
        self.assertIn("form.requestSubmit(trigger)", script)
        self.assertIn("closeDialog();\n    form.requestSubmit(trigger);", script)
        self.assertIn("summary_pdf_options.js", legacy_base)

    def test_matrix_pdf_renderer_has_no_legacy_matrix_title_or_total_column(self) -> None:
        source = (ROOT / "backend/app/services/summary_pdf.py").read_text(encoding="utf-8")
        card_builder = source.split("def _build_summary_cards_pdf", 1)[1].split("def _summary_pdf_image_cell", 1)[0]

        self.assertIn('Paragraph("Кавалер"', card_builder)
        self.assertIn('Paragraph("Нет фото"', source)
        self.assertNotIn("Шахматка по кавалерам", card_builder)
        self.assertNotIn("Итого наград", card_builder)
        self.assertNotIn("reward_counts", card_builder)


if __name__ == "__main__":
    unittest.main()
