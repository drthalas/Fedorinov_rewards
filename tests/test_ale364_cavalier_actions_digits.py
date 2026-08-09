from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Ale364CavalierActionsContractTests(unittest.TestCase):
    def test_both_action_sets_use_the_same_canonical_macros(self) -> None:
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        self.assertEqual(template.count("open_person_catalog(selected_person"), 2)
        self.assertEqual(template.count("archive_person_catalog(selected_person"), 2)
        self.assertEqual(template.count("person_booklet_action(selected_person"), 2)
        self.assertIn('action="/persons/{{ person.id }}/open-folder"', template)
        self.assertIn('action="/persons/{{ person.id }}/archive-folder.zip"', template)
        self.assertIn('href="/persons/{{ person.id }}/booklet?', template)

    def test_open_folder_has_one_feedback_lifecycle_owner(self) -> None:
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        macro = template.split("{% macro open_person_catalog", 1)[1].split("endmacro", 1)[0]
        self.assertIn("data-open-folder", macro)
        self.assertIn('data-write-pending-label="Открываем каталог…"', macro)
        self.assertNotIn("data-write-feedback", macro)

        lifecycle = (ROOT / "backend/app/static/transition_lifecycle.js").read_text(encoding="utf-8")
        self.assertIn('form.matches("[data-open-folder]")', lifecycle)
        self.assertIn("feedback.begin", lifecycle)
        self.assertIn("feedback.finish", lifecycle)

    def test_digit_index_is_inside_the_person_list_and_uses_group_fragment_urls(self) -> None:
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        list_start = template.index('data-person-list data-active-letter=')
        list_end = template.index("{% for person in persons %}", list_start)
        index_markup = template[list_start:list_end]
        self.assertIn('class="legacy-person-indexes"', index_markup)
        self.assertIn('class="legacy-alphabet-index"', index_markup)
        self.assertIn('class="legacy-digit-index"', index_markup)
        self.assertIn('data-letter-url="{{ item.url }}"', index_markup)
        self.assertIn('data-person-digit="{{ item.digit }}"', index_markup)
        self.assertNotIn(">0</button>", index_markup)

    def test_toolbar_layout_has_no_horizontal_overflow_prone_six_column_grid(self) -> None:
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")
        toolbar = styles.split(".legacy-rewards-theme .legacy-toolbar {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", toolbar)
        self.assertNotIn("repeat(6", toolbar)


if __name__ == "__main__":
    unittest.main()
