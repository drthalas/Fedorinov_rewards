from pathlib import Path
from tempfile import TemporaryDirectory
import re
import unittest
from unittest.mock import patch

from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Image, SimpleDocTemplate, Table

from backend.app.config import Settings
from backend.app.repositories.summary import normalized_summary_filters
from backend.app.services.summary_pdf import _build_summary_cards_pdf, SUMMARY_PDF_CELL_PADDING


class SummaryPortraitTests(unittest.TestCase):
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

            for sort in ('fio', 'reward_number'):
                with patch.object(SimpleDocTemplate, 'build', capture):
                    result = _build_summary_cards_pdf(settings, normalized_summary_filters(name_id=1), matrix,
                        [('book1_foto', 'Книжка 1'), ('book2_foto', 'Книжка 2'), ('front_foto', 'Аверс'), ('back_foto', 'Реверс')],
                        include_reward_number=True, sort_by=sort)
                boxes = re.findall(rb'/MediaBox\s*\[([^]]+)\]', result.content)
                self.assertTrue(boxes)
                for box in boxes:
                    _, _, width, height = map(float, box.split())
                    self.assertAlmostEqual(width, A4[0], places=2)
                    self.assertAlmostEqual(height, A4[1], places=2)
                self.assertGreater(len(re.findall(rb'/Type /Page\b', result.content)), 1)
                table = captured[-1]
                for row in table._cellvalues[1:]:
                    for col, cell in enumerate(row):
                        for item in cell if isinstance(cell, list) else []:
                            if isinstance(item, Image):
                                self.assertLessEqual(item.drawWidth + SUMMARY_PDF_CELL_PADDING, table._colWidths[col] + 0.01)
                                self.assertAlmostEqual(item.drawWidth/item.drawHeight, item.imageWidth/item.imageHeight)
                first = table._cellvalues[1][0]
                self.assertIn('1901 г.р.', first[1].text)
                self.assertIn('Bold', first[0].style.fontName)
                self.assertEqual(first[0].text, 'Кавалер 00' if sort == 'fio' else 'Кавалер 17')
