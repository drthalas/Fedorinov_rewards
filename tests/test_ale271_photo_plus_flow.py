from pathlib import Path
import unittest

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


class Ale271PhotoPlusFlowTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def render_photo_controls(self, entity_type: str) -> str:
        template = Environment(autoescape=True).from_string(
            self.read("backend/app/templates/photo_management.html")
        )
        return template.render(
            mode="edit",
            settings=type("Settings", (), {"write_mode": True})(),
            request=type("Request", (), {"url": type("Url", (), {"path": f"/{entity_type}/42/edit"})()})(),
            return_to="",
            photo_controls=[
                {"field": "front_foto", "label": "Лицевая сторона", "path": None},
                {"field": "back_foto", "label": "Оборотная сторона", "path": "Source/42/back.jpg"},
            ],
            photo_manage_compact=False,
            photo_entity_type=entity_type,
            photo_entity_id=42,
            has_media_path=bool,
            photo_view_url=lambda path, label, return_to: "/photo/view",
            media_url=lambda path: "/media",
        )

    def test_person_reward_and_mark_compact_plus_use_shared_handler(self) -> None:
        for entity_type, marker in (
            ("person", "data-person-photo-trigger"),
            ("reward", "data-reward-photo-trigger"),
            ("mark", "data-mark-photo-trigger"),
        ):
            with self.subTest(entity_type=entity_type):
                rendered = self.render_photo_controls(entity_type)
                self.assertEqual(rendered.count("data-photo-plus-trigger"), 2)
                self.assertEqual(rendered.count(marker), 2)
                self.assertEqual(rendered.count('type="file"'), 2)
                self.assertEqual(rendered.count("data-photo-source-error"), 2)
                self.assertNotIn("clipboard-paste-status", rendered)
                self.assertNotIn("onchange=", rendered)

        script = self.read("backend/app/static/clipboard_paste.js")
        self.assertIn(
            'document.querySelectorAll("[data-photo-plus-trigger]").forEach(bindInlinePhotoTrigger)',
            script,
        )

    def test_managed_flow_rechecks_clipboard_after_picker_cancel(self) -> None:
        script = self.read("backend/app/static/clipboard_paste.js")
        handler = script.split("function bindInlinePhotoTrigger(button)", 1)[1].split(
            'document.addEventListener("DOMContentLoaded"', 1
        )[0]
        picker = script.split("function openPersonFilePicker(button)", 1)[1].split(
            "function bindInlinePhotoTrigger(button)", 1
        )[0]

        self.assertNotIn("shouldOpenFilePicker", script)
        self.assertNotIn("markFilePickerNext", script)
        self.assertNotIn("resetPhotoPlusMode", script)
        self.assertNotIn("photoPlusMode", script)
        self.assertNotIn("file-next", script)
        self.assertLess(handler.index("imageBlobFromClipboardWithTimeout"), handler.index("openPersonFilePicker(button)"))
        self.assertIn("normalizedPageSearch(window.location.search)", script)
        self.assertIn("normalizedPageSearch(state.search)", script)
        self.assertIn("input.click();", picker)
        self.assertNotIn("showPicker", picker)
        self.assertIn('input.addEventListener("cancel", onCancel)', picker)
        self.assertIn('input.addEventListener("change", onChange)', picker)
        self.assertIn("input.removeEventListener", picker)

        cancel_handler = picker.split("function onCancel()", 1)[1].split("function onChange()", 1)[0]
        self.assertIn("restorePhotoInteraction()", cancel_handler)
        self.assertNotIn("photoPlusMode", cancel_handler)
        change_handler = picker.split("function onChange()", 1)[1].split('input.addEventListener("cancel"', 1)[0]
        self.assertIn("input.form.submit()", change_handler)

    def test_rank_rechecks_clipboard_after_picker_cancel(self) -> None:
        script = self.read("backend/app/static/guide_image_preview.js")
        rank_form = self.read("backend/app/templates/rank_form.html")
        rank_editor = script.split("function initRankImageEditor(editor)", 1)[1]
        rank_flow = rank_editor.split("async function beginRankImageFlow()", 1)[1].split(
            'trigger.addEventListener("click"', 1
        )[0]

        self.assertNotIn("pickerNext", rank_editor)
        self.assertIn("input.click();", rank_editor)
        self.assertNotIn("showPicker", rank_editor)
        self.assertLess(
            rank_flow.index("helper.readWithTimeout"),
            rank_flow.index("openFilePicker()"),
        )
        self.assertIn("confirmation.run(trigger, beginRankImageFlow)", rank_editor)
        cancel_handler = rank_editor.split('input.addEventListener("cancel"', 1)[1].split("});", 1)[0]
        self.assertNotIn("pickerNext", cancel_handler)
        self.assertNotIn("data-rank-image-status", rank_form)

    def test_obsolete_state_helper_and_visible_technical_statuses_are_removed(self) -> None:
        clipboard_script = self.read("backend/app/static/clipboard_paste.js")
        rank_script = self.read("backend/app/static/guide_image_preview.js")
        photo_template = self.read("backend/app/templates/photo_management.html")
        rank_template = self.read("backend/app/templates/rank_form.html")
        self.assertFalse((ROOT / "backend/app/static/photo_plus_flow.js").exists())
        for template_path in ("backend/app/templates/base.html", "backend/app/templates/legacy_base.html"):
            template = self.read(template_path)
            self.assertNotIn("photo_plus_flow.js", template)

        for technical_text in (
            "Выберите файл...",
            "Выберите изображение…",
            "Проверяем буфер обмена…",
            "Подготавливаем изображение…",
            "Загружаем фотографию...",
            "Сохраняем фото...",
        ):
            self.assertNotIn(technical_text, clipboard_script)
            self.assertNotIn(technical_text, rank_script)
        self.assertNotIn("clipboard-paste-status", photo_template)
        self.assertNotIn("rank-insignia-status", rank_template)


if __name__ == "__main__":
    unittest.main()
