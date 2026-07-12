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

    def test_person_media_editor_is_inline_and_has_no_next_actions(self) -> None:
        form = self.read("backend/app/templates/person_form.html")
        photo_management = self.read("backend/app/templates/photo_management.html")
        script = self.read("backend/app/static/clipboard_paste.js")
        styles = self.read("backend/app/static/styles.css")

        self.assertNotIn("Следующие действия", form)
        self.assertNotIn("Добавить фото и документы", form)
        self.assertNotIn("Добавить награду", form)
        self.assertIn('id="{{ photo_entity_type }}-photo-management"', photo_management)
        self.assertIn('action="/photos/upload"', photo_management)
        self.assertIn('data-photo-file-trigger', photo_management)
        self.assertIn('data-photo-file-input', photo_management)
        self.assertIn("input.click()", script)
        self.assertIn("form.submit()", script)
        self.assertIn("Добавить фото или документ", photo_management)
        self.assertIn("Изменить описание", photo_management)
        self.assertIn("Удалить карточку", photo_management)
        self.assertIn("Вставить изображение из буфера", photo_management)
        self.assertIn(".cavalier-page-theme .person-edit-photos .photo-manage-section", styles)
        self.assertIn("margin-top: 0", styles.split("ALE-250 corrective pass", 1)[1])


if __name__ == "__main__":
    unittest.main()
