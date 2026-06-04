from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MarkFormLabelTests(unittest.TestCase):
    def test_mark_form_uses_mark_guide_label(self) -> None:
        template = (ROOT / "backend" / "app" / "templates" / "mark_form.html").read_text(encoding="utf-8")
        self.assertIn("Открыть справочник знаков", template)
        self.assertNotIn("Открыть справочник наград", template)


if __name__ == "__main__":
    unittest.main()
