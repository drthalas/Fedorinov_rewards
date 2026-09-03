from pathlib import Path
import unittest
from unittest.mock import patch

from backend.app.repositories.summary import normalized_summary_filters
from backend.app.services.summary_pdf import (
    SUMMARY_PDF_IMAGE_DPI,
    normalize_summary_pdf_media_fields,
    _summary_pdf_header_text,
)


ROOT = Path(__file__).resolve().parents[1]


class SummaryPDFLayoutTests(unittest.TestCase):
    def test_selector_groups_both_document_sides(self) -> None:
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        selector = template.split("data-summary-pdf-options-dialog", 1)[1].split("</dialog>", 1)[0]

        self.assertIn('value="book1_foto,book2_foto"', selector)
        self.assertIn('<span>Фото наградной книжки</span>', selector)
        self.assertIn('value="card1_foto,card2_foto"', selector)
        self.assertIn('<span>Фото учётной карточки</span>', selector)
        self.assertIn(
            'column.field not in ["person_foto", "book1_foto", "book2_foto", "card1_foto", "card2_foto"]',
            selector,
        )
        self.assertIn("summary_matrix.reward_photo_columns", selector)

    def test_grouped_values_expand_to_existing_media_slots_in_order(self) -> None:
        self.assertEqual(
            normalize_summary_pdf_media_fields(
                "book1_foto,book2_foto,card1_foto,card2_foto,front_foto,back_foto"
            ),
            (
                "book1_foto",
                "book2_foto",
                "card1_foto",
                "card2_foto",
                "front_foto",
                "back_foto",
            ),
        )

    def test_selected_reward_header_contains_only_name_and_actual_row_count(self) -> None:
        filters = normalized_summary_filters(name_id="17")
        matrix = {
            "selected_reward_name": "Орден Победы",
            "rows": [{"id": 1}, {"id": 2}, {"id": 3}],
        }

        header = _summary_pdf_header_text(Path("unused.sqlite"), filters, matrix)

        self.assertEqual(header, "Орден Победы (всего: 3)")
        for legacy_label in ("Фильтры:", "Страна:", "Категория:", "Подкатегория:", "Наименование:"):
            self.assertNotIn(legacy_label, header)

    def test_non_specific_reward_keeps_existing_filter_header(self) -> None:
        filters = normalized_summary_filters()
        with patch("backend.app.services.summary_pdf._filters_text", return_value="existing filters"):
            self.assertEqual(
                _summary_pdf_header_text(Path("unused.sqlite"), filters, {"rows": []}),
                "existing filters",
            )

    def test_landscape_and_accepted_render_profile_remain_frozen(self) -> None:
        source = (ROOT / "backend/app/services/summary_pdf.py").read_text(encoding="utf-8")

        self.assertIn("page_size = landscape(A4 if visible_column_count <= 3 else A3)", source)
        self.assertEqual(SUMMARY_PDF_IMAGE_DPI, 200)
        self.assertIn("subsampling=0", source)
        self.assertIn("image._restrictSize(safe_width, safe_height)", source)


if __name__ == "__main__":
    unittest.main()
