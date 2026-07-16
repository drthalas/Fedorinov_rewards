import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


class Ale262RewardEditUiTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def render_reward_photo_controls(self) -> str:
        template = Environment(autoescape=True).from_string(
            self.read("backend/app/templates/photo_management.html")
        )
        return template.render(
            mode="edit",
            settings=SimpleNamespace(write_mode=True),
            request=SimpleNamespace(url=SimpleNamespace(path="/rewards/42/edit")),
            return_to="/rewards/42",
            photo_controls=[
                {"field": "front_foto", "label": "Фото награды: аверс", "path": None},
                {"field": "back_foto", "label": "Фото награды: реверс", "path": "Source/7/42/back.jpg"},
            ],
            photo_manage_compact=False,
            photo_entity_type="reward",
            photo_entity_id=42,
            has_media_path=bool,
            photo_view_url=lambda path, label, return_to: "/photo/view",
            media_url=lambda path: "/media",
        )

    def test_reward_edit_has_only_inline_photo_actions_and_neutral_guide_link(self) -> None:
        form = self.read("backend/app/templates/reward_form.html")

        self.assertNotIn("Следующие действия", form)
        self.assertNotIn("Редактировать фото и документы", form)
        self.assertNotIn("Добавить ещё награду", form)
        self.assertIn('class="reward-guide-link"', form)
        self.assertIn("Открыть справочник наград", form)

    def test_reward_slots_use_compact_clipboard_first_buttons(self) -> None:
        rendered = self.render_reward_photo_controls()

        self.assertEqual(rendered.count("data-reward-photo-trigger"), 2)
        self.assertIn('type="button"', rendered)
        self.assertIn('data-file-input-id="photo-file-reward-42-front_foto"', rendered)
        self.assertIn('data-file-input-id="photo-file-reward-42-back_foto"', rendered)
        self.assertIn('name="entity_type" value="reward"', rendered)
        self.assertIn('name="entity_id" value="42"', rendered)
        self.assertIn('name="photo_field" value="front_foto"', rendered)
        self.assertIn('name="photo_field" value="back_foto"', rendered)
        self.assertIn('accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp"', rendered)
        self.assertEqual(rendered.count('aria-label="Удалить фотографию:'), 1)
        self.assertNotIn("data-clipboard-paste", rendered)
        self.assertNotIn("Вставить из буфера", rendered)

    def test_reward_trigger_prevents_navigation_and_restores_scroll_and_focus(self) -> None:
        script = self.read("backend/app/static/clipboard_paste.js")
        handler = script.split("function bindInlinePhotoTrigger(button)", 1)[1].split(
            'document.addEventListener("DOMContentLoaded"', 1
        )[0]

        self.assertIn("event.preventDefault()", handler)
        self.assertIn("rememberPhotoInteraction(button)", handler)
        self.assertLess(
            handler.index("await imageBlobFromClipboardWithTimeout(2000)"),
            handler.index("await uploadClipboardImage"),
        )
        self.assertIn("openPersonFilePicker(button)", handler)
        self.assertIn('document.querySelectorAll("[data-photo-plus-trigger]").forEach(bindInlinePhotoTrigger)', script)
        self.assertIn("page.scrollTop = Number(state.pageScrollTop", script)
        self.assertIn("window.scrollTo(0, Number(state.windowScrollY", script)
        self.assertIn("trigger.focus({ preventScroll: true })", script)
        self.assertIn('input.addEventListener("cancel"', script)
        self.assertIn('input.addEventListener("change"', script)

    def test_reward_controls_and_guide_link_are_scoped_in_dark_theme(self) -> None:
        styles = self.read("backend/app/static/styles.css")
        scoped = styles.split("ALE-262: keep reward photo actions compact", 1)[1]

        self.assertIn(".cavalier-reward-form-page .reward-guide-link", scoped)
        self.assertIn("color: #d8d0c3", scoped)
        self.assertIn(".cavalier-reward-form-page .photo-icon-button", scoped)
        self.assertIn("width: 28px", scoped)
        self.assertIn("height: 28px", scoped)


if __name__ == "__main__":
    unittest.main()
