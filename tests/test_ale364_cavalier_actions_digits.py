from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Ale364CavalierActionsContractTests(unittest.TestCase):
    def test_both_action_sets_use_the_same_canonical_macros(self) -> None:
        legacy = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        detail = (ROOT / "backend/app/templates/person_detail.html").read_text(encoding="utf-8")
        macros = (ROOT / "backend/app/templates/_person_file_actions.html").read_text(encoding="utf-8")
        self.assertEqual(legacy.count("open_person_catalog(selected_person"), 1)
        self.assertEqual(detail.count("open_person_catalog(person"), 1)
        self.assertEqual(detail.count("archive_person_catalog(person"), 1)
        self.assertEqual(detail.count("person_booklet_action(person"), 1)
        self.assertIn('action="/persons/{{ person.id }}/open-folder"', macros)
        self.assertIn('action="/persons/{{ person.id }}/archive-folder.zip"', macros)
        self.assertIn('href="/persons/{{ person.id }}/booklet?', macros)

    def test_main_toolbar_remains_baseline_and_actions_follow_edit_delete_on_detail(self) -> None:
        legacy = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        detail = (ROOT / "backend/app/templates/person_detail.html").read_text(encoding="utf-8")
        toolbar = legacy.split('<div class="legacy-toolbar">', 1)[1].split("</div>", 1)[0]
        self.assertIn("legacy-action-add", toolbar)
        self.assertIn("legacy-action-edit", toolbar)
        self.assertIn("legacy-action-delete", toolbar)
        self.assertNotIn("open_person_catalog", toolbar)
        self.assertNotIn("archive_person_catalog", toolbar)
        self.assertNotIn("person_booklet_action", toolbar)
        actions = detail.split('<div class="actions person-detail-actions">', 1)[1].split("</div>", 1)[0]
        self.assertLess(actions.index("Изменить"), actions.index("Удалить"))
        self.assertLess(actions.index("Удалить"), actions.index("open_person_catalog"))
        self.assertLess(actions.index("open_person_catalog"), actions.index("archive_person_catalog"))
        self.assertLess(actions.index("archive_person_catalog"), actions.index("person_booklet_action"))

    def test_open_folder_has_one_feedback_lifecycle_owner(self) -> None:
        template = (ROOT / "backend/app/templates/_person_file_actions.html").read_text(encoding="utf-8")
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
        self.assertLess(index_markup.index('class="legacy-digit-index"'), index_markup.index('class="legacy-alphabet-index"'))
        self.assertIn('data-letter-url="{{ item.url }}"', index_markup)
        self.assertIn('data-person-digit="{{ item.digit }}"', index_markup)
        self.assertNotIn(">0</button>", index_markup)

    def test_toolbar_layout_matches_accepted_three_action_baseline(self) -> None:
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")
        toolbar = styles.split(".legacy-rewards-theme .legacy-toolbar {", 1)[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", toolbar)
        self.assertNotIn("repeat(6", toolbar)

    def test_group_navigation_does_not_replace_card_with_loading_message(self) -> None:
        script = (ROOT / "backend/app/static/legacy_rewards.js").read_text(encoding="utf-8")
        group_handler = script.split("alphabetLetters.forEach", 1)[1].split("personRows.forEach", 1)[0]
        self.assertIn("showLoading: false", group_handler)
        self.assertIn("settings.showLoading !== false", script)

    def test_standalone_person_actions_stay_on_one_row(self) -> None:
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")
        block = styles.split(".compact-person-detail .person-detail-actions {", 1)[1].split("}", 1)[0]
        self.assertIn("flex-wrap: nowrap", block)
        self.assertIn("overflow-x: auto", block)


if __name__ == "__main__":
    unittest.main()
