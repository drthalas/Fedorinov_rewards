from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Ale356MarksEmptyStateStyleTests(unittest.TestCase):
    def test_marks_empty_states_use_scoped_dark_gold_styles(self) -> None:
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('class="legacy-empty legacy-marks-empty">Нет знаков.</div>', template)
        self.assertIn('class="notice legacy-marks-placeholder">Выберите знак.</div>', template)
        self.assertIn(".legacy-marks-tab .legacy-marks-placeholder", styles)
        self.assertIn("color: #bdb4a6", styles)
        self.assertIn("border-color: #514737", styles)
        self.assertIn("background: linear-gradient(180deg, #191a17, #151613)", styles)
        self.assertIn("box-shadow: inset 3px 0 0 #8d6a3e", styles)
        self.assertIn(".legacy-marks-tab .legacy-marks-empty", styles)
        self.assertIn("color: #a79d8d", styles)

    def test_marks_style_fix_does_not_change_empty_state_layout(self) -> None:
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")
        placeholder_block = styles.split(".legacy-marks-tab .legacy-marks-placeholder", 1)[1].split("}", 1)[0]
        empty_block = styles.split(".legacy-marks-tab .legacy-marks-empty", 1)[1].split("}", 1)[0]

        for property_name in ("margin:", "padding:", "width:", "height:", "position:", "display:"):
            self.assertNotIn(property_name, placeholder_block)
            self.assertNotIn(property_name, empty_block)


if __name__ == "__main__":
    unittest.main()
