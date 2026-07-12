import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Ale250UiPolishTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_marks_render_number_only_when_meaningful(self) -> None:
        template = self.read("backend/app/templates/legacy.html")

        self.assertIn("{% if mark.number %}<small>№ {{ mark.number }}</small>{% endif %}", template)
        self.assertIn(
            "{% if selected_mark.number %}<p class=\"secondary\">№ {{ selected_mark.number }}</p>{% endif %}",
            template,
        )
        self.assertIn(
            "{% if selected_mark.number %}<dt>Номер</dt><dd>{{ selected_mark.number }}</dd>{% endif %}",
            template,
        )
        self.assertNotIn("<dt>Номер</dt><dd>{{ selected_mark.number|dash }}</dd>", template)

    def test_summary_uses_full_heading_without_decorative_rule(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        styles = self.read("backend/app/static/styles.css")

        summary = template.split('{% elif tab == "summary" %}', 1)[1].split('{% elif tab == "about" %}', 1)[0]
        ale250 = styles.split("ALE-250: scoped polish", 1)[1]
        self.assertIn("<h1>Сводная таблица</h1>", summary)
        self.assertNotIn("<h1>Свод.таблица</h1>", summary)
        self.assertIn(".legacy-summary-tab > h1", ale250)
        self.assertIn("border-bottom: 0", ale250)
        self.assertIn(".legacy-summary-tab > h1::after", ale250)
        self.assertIn("content: none", ale250)

    def test_rewards_empty_state_keeps_artwork_without_overlay_copy(self) -> None:
        template = self.read("backend/app/templates/legacy.html")
        styles = self.read("backend/app/static/styles.css")

        self.assertIn('data-cavalier-empty-state aria-label="Кавалеры"', template)
        self.assertNotIn("Выберите кавалера из списка слева", template)
        self.assertNotIn("После выбора откроется карточка", template)
        self.assertNotIn("legacy-empty-state-copy", template)
        self.assertIn('/static/assets/cavaliers/empty-hero.jpg', styles)
        self.assertIn("{% if selected_person %}", template)

    def test_edit_person_removes_helpers_and_birth_hint(self) -> None:
        template = self.read("backend/app/templates/person_form.html")

        self.assertNotIn("Открыть справочник", template)
        self.assertNotIn("Добавить звание", template)
        self.assertNotIn("Текущее значение:", template)
        self.assertIn('select name="id_rank" data-styled-select required', template)
        self.assertIn('value="{{ person.birthday|format_birth_year_input }}"', template)

    def test_current_specialty_value_uses_light_form_color(self) -> None:
        styles = self.read("backend/app/static/styles.css")

        ale250 = styles.split("ALE-250: scoped polish", 1)[1]
        self.assertIn(".cavalier-page-theme .cavalier-form-card .styled-select-value", ale250)
        self.assertIn("color: #d2cabd", ale250)
        self.assertIn("font-weight: 400", ale250)

    def test_photo_action_targets_existing_person_edit_flow(self) -> None:
        form = self.read("backend/app/templates/person_form.html")
        photo_management = self.read("backend/app/templates/photo_management.html")
        styles = self.read("backend/app/static/styles.css")

        self.assertIn('href="{{ form_return_path }}#person-photo-management"', form)
        self.assertIn('id="{{ photo_entity_type }}-photo-management" tabindex="-1"', photo_management)
        self.assertIn('action="/photos/upload"', photo_management)
        self.assertIn('name="entity_id" value="{{ photo_entity_id }}"', photo_management)
        self.assertIn(".cavalier-page-theme .photo-manage-section:target", styles)
        self.assertIn("scroll-margin-top: 88px", styles)


if __name__ == "__main__":
    unittest.main()
