import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment


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
        self.assertIn('/static/assets/cavaliers/cavaliers-empty-state-awards-optimized.jpg', styles)
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

    def test_person_photo_editor_uses_only_compact_fixed_slot_controls(self) -> None:
        form = self.read("backend/app/templates/person_form.html")
        photo_management = self.read("backend/app/templates/photo_management.html")
        photos_service = self.read("backend/app/services/photos.py")
        photos_router = self.read("backend/app/routers/photos.py")
        styles = self.read("backend/app/static/styles.css")

        self.assertNotIn("Следующие действия", form)
        self.assertNotIn("Добавить фото и документы", form)
        self.assertNotIn("Добавить награду", form)
        self.assertIn('id="{{ photo_entity_type }}-photo-management"', photo_management)
        self.assertIn('action="/photos/upload"', photo_management)
        self.assertIn("data-mark-photo-trigger", photo_management)
        self.assertIn('id="{{ file_input_id }}"', photo_management)
        self.assertIn('type="file"', photo_management)
        self.assertNotIn("onchange=", photo_management)
        self.assertIn("data-photo-source-error", photo_management)
        self.assertIn('name="entity_id" value="{{ photo_entity_id }}"', photo_management)
        self.assertIn('name="photo_field" value="{{ photo.field }}"', photo_management)
        self.assertIn('>+</button>', photo_management)
        self.assertIn('>×</button>', photo_management)
        self.assertNotIn("Добавить файл", photo_management)
        self.assertNotIn("Изменить описание", photo_management)
        self.assertNotIn("Добавить фото или документ", photo_management)
        self.assertNotIn("Удалить карточку", photo_management)
        self.assertNotIn('name="title"', photo_management)
        self.assertNotIn('name="description"', photo_management)
        self.assertNotIn("person_media", photos_service)
        self.assertNotIn("/media/create", photos_router)
        self.assertIn(".cavalier-page-theme .person-edit-photos .photo-manage-section", styles)
        self.assertIn("margin-top: 0", styles.split("ALE-250 corrective pass", 1)[1])

    def test_person_photo_editor_uses_one_clipboard_first_trigger_and_hides_empty_slot_delete(self) -> None:
        template = Environment(autoescape=True).from_string(
            self.read("backend/app/templates/photo_management.html")
        )
        rendered = template.render(
            mode="edit",
            settings=SimpleNamespace(write_mode=True),
            request=SimpleNamespace(url=SimpleNamespace(path="/persons/77/edit")),
            return_to="",
            photo_controls=[
                {"field": "person_foto", "label": "Фото кавалера", "path": None},
                {"field": "main_foto", "label": "Главное фото", "path": "Source/77/main.jpg"},
            ],
            photo_manage_compact=True,
            photo_entity_type="person",
            photo_entity_id=77,
            has_media_path=bool,
            photo_view_url=lambda path, label, return_to: "/photo/view",
            media_url=lambda path: "/media",
        )

        self.assertIn('aria-label="Добавить фотографию: Фото кавалера"', rendered)
        self.assertIn('aria-label="Заменить фотографию: Главное фото"', rendered)
        self.assertEqual(rendered.count('aria-label="Удалить фотографию:'), 1)
        self.assertEqual(rendered.count('type="file"'), 2)
        self.assertIn('value="77"', rendered)
        self.assertIn('value="person_foto"', rendered)
        self.assertIn('value="main_foto"', rendered)
        self.assertIn("Фото кавалера", rendered)
        self.assertIn("Главное фото", rendered)
        self.assertNotIn("Вставить", rendered)
        self.assertEqual(rendered.count("data-person-photo-trigger"), 2)
        self.assertIn('data-file-input-id="photo-file-person-77-person_foto"', rendered)
        self.assertIn('data-file-input-id="photo-file-person-77-main_foto"', rendered)
        self.assertNotIn("Добавить фото или документ", rendered)


if __name__ == "__main__":
    unittest.main()
