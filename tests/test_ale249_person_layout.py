import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Ale249PersonLayoutTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_standalone_cavalier_pages_scroll_inside_fixed_shell(self) -> None:
        styles = self.read("backend/app/static/styles.css")
        ale249 = styles.split("ALE-249: standalone cavalier pages", 1)[1]

        self.assertIn("body.guide-theme.cavalier-page-theme .page", ale249)
        self.assertIn("overflow-y: auto", ale249)
        self.assertIn("overflow-x: hidden", ale249)
        self.assertIn("scrollbar-gutter: stable", ale249)

    def test_person_card_links_are_readable_without_ellipsis(self) -> None:
        styles = self.read("backend/app/static/styles.css")
        ale249 = styles.split("ALE-249: standalone cavalier pages", 1)[1]
        template = self.read("backend/app/templates/person_detail.html")

        self.assertIn("grid-template-columns: minmax(0, 1fr)", ale249)
        self.assertIn("text-overflow: clip", ale249)
        self.assertIn("white-space: normal", ale249)
        self.assertIn("color: #d8d0c3", ale249)
        self.assertIn("color: #b9aa94", ale249)
        self.assertIn(">Форум коллекционеров</a>", template)
        self.assertIn(">Показать все фото</a>", template)

    def test_add_person_hides_rank_guide_helpers_but_keeps_rank_field(self) -> None:
        template = self.read("backend/app/templates/person_form.html")

        self.assertNotIn("Открыть справочник", template)
        self.assertNotIn("Добавить звание", template)
        self.assertIn('select name="id_rank"', template)
        self.assertIn("data-styled-select", template)
        self.assertIn("required", template)


if __name__ == "__main__":
    unittest.main()
