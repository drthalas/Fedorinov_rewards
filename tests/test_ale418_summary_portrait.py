from pathlib import Path
from itertools import product
from tempfile import TemporaryDirectory
import re
import unittest
from unittest.mock import patch

from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Image, SimpleDocTemplate, Table

from backend.app.config import Settings
from backend.app.repositories.summary import normalized_summary_filters
from backend.app.services.summary_pdf import _build_summary_cards_pdf, SUMMARY_PDF_CELL_PADDING, normalize_summary_pdf_orientation


class SummaryPortraitTests(unittest.TestCase):
    def test_orientation_default_and_selector_contract(self):
        for value in (None, "", "invalid", "portrait"):
            self.assertEqual(normalize_summary_pdf_orientation(value), "portrait")
        self.assertEqual(normalize_summary_pdf_orientation("landscape"), "landscape")
        html = (Path(__file__).resolve().parents[1] / 'backend/app/templates/legacy.html').read_text()
        inputs = re.findall(r'<input[^>]+name="pdf_orientation"[^>]*>', html)
        self.assertEqual(len(inputs), 2)
        self.assertTrue(all('type="radio"' in item and 'form="summary-pdf-save-form"' in item for item in inputs))
        self.assertIn('value="portrait"', inputs[0])
        self.assertIn('checked', inputs[0])
        self.assertNotIn('checked', inputs[1])

    def test_route_forwards_orientation_without_affecting_sort(self):
        from backend.app.routers import legacy
        with patch.object(legacy, 'get_settings') as settings, patch.object(legacy, 'generate_summary_matrix_pdf') as generate, patch.object(legacy, '_pdf_download_response'):
            settings.return_value.db_exists = True
            legacy.summary_matrix_pdf(pdf_orientation='landscape', pdf_sort='reward_number')
            self.assertEqual(generate.call_args.kwargs['orientation'], 'landscape')
            self.assertEqual(generate.call_args.kwargs['sort_by'], 'reward_number')

    def test_real_multipage_pdf_contains_mixed_ratios_in_final_column_bounds(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Source').mkdir()
            paths = []
            for index, size in enumerate(((1600, 100), (100, 1600), (700, 700))):
                path = root / 'Source' / f'{index}.jpg'
                PILImage.new('RGB', size, (80, 100, 120)).save(path)
                paths.append(str(path.relative_to(root)))
            settings = Settings(rewards_data_dir=root, rewards_db_path=root / 'unused.sqlite')
            rows = [{
                'id': index, 'fio': f'Кавалер {index:02d}', 'rank_name': 'Генерал', 'birthday': '1901',
                'pdf_reward_numbers': [str(30-index)],
                'photo_paths': {'person_foto': paths[index % 3], 'book1_foto': paths[0], 'book2_foto': paths[1]},
                'reward_photo_paths': {'front_foto': paths, 'back_foto': paths[::-1]},
            } for index in range(18)]
            matrix = {'rows': rows, 'selected_reward_name': 'Орден Тестовый'}
            captured = []
            build = SimpleDocTemplate.build

            def capture(doc, story, **kwargs):
                captured.append(next(item for item in story if isinstance(item, Table)))
                return build(doc, story, **kwargs)

            widths_by_orientation = {}
            for orientation, sort in product(('portrait', 'landscape'), ('fio', 'reward_number')):
                with patch.object(SimpleDocTemplate, 'build', capture):
                    result = _build_summary_cards_pdf(settings, normalized_summary_filters(name_id=1), matrix,
                        [('book1_foto', 'Книжка 1'), ('book2_foto', 'Книжка 2'), ('front_foto', 'Аверс'), ('back_foto', 'Реверс')],
                        include_reward_number=True, sort_by=sort, orientation=orientation)
                boxes = re.findall(rb'/MediaBox\s*\[([^]]+)\]', result.content)
                self.assertTrue(boxes)
                for box in boxes:
                    _, _, width, height = map(float, box.split())
                    expected = landscape(A4) if orientation == 'landscape' else A4
                    self.assertAlmostEqual(width, expected[0], places=2)
                    self.assertAlmostEqual(height, expected[1], places=2)
                self.assertGreater(len(re.findall(rb'/Type /Page\b', result.content)), 1)
                table = captured[-1]
                widths_by_orientation[orientation] = table._colWidths
                for row in table._cellvalues[1:]:
                    for col, cell in enumerate(row):
                        for item in cell if isinstance(cell, list) else []:
                            if isinstance(item, Image):
                                self.assertLessEqual(item.drawWidth + SUMMARY_PDF_CELL_PADDING, table._colWidths[col] + 0.01)
                                self.assertAlmostEqual(item.drawWidth/item.drawHeight, item.imageWidth/item.imageHeight)
                                self.assertLessEqual(item.drawHeight, 50 * 72 / 25.4)
                first = table._cellvalues[1][0]
                self.assertIn('1901 г.р.', first[1].text)
                self.assertIn('Bold', first[0].style.fontName)
                self.assertEqual(first[0].text, 'Кавалер 00' if sort == 'fio' else 'Кавалер 17')
            self.assertGreater(widths_by_orientation['landscape'][-1], widths_by_orientation['portrait'][-1])
