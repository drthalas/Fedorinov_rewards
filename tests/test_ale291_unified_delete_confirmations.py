from pathlib import Path
import unittest

from backend.app.services.deletion_confirmation import MediaDeletePreview, confirmation_message


ROOT = Path(__file__).resolve().parents[1]


class Ale291UnifiedDeleteConfirmationTests(unittest.TestCase):
    def test_all_entity_delete_surfaces_use_the_shared_contract(self) -> None:
        templates = {
            name: (ROOT / "backend" / "app" / "templates" / name).read_text()
            for name in ("person_detail.html", "reward_detail.html", "mark_detail.html", "legacy.html", "guides.html")
        }

        self.assertIn('data-confirm-submit="person-delete"', templates["person_detail.html"])
        self.assertIn('data-confirm-submit="reward-delete"', templates["reward_detail.html"])
        self.assertIn('data-confirm-submit="mark-delete"', templates["mark_detail.html"])
        self.assertIn('data-confirm-submit="rank-delete"', templates["guides.html"])
        self.assertIn('data-confirm-submit="guide-delete"', templates["guides.html"])
        for template in templates.values():
            for form in template.split("<form")[1:]:
                if "data-confirm-submit" not in form:
                    continue
                opening_tag = form.split(">", 1)[0]
                self.assertIn("data-confirm-title=", opening_tag)
                self.assertIn("data-confirm-message=", opening_tag)
                self.assertIn("data-confirm-blocked=", opening_tag)
        self.assertNotIn("window.confirm(", templates["guides.html"])

    def test_dialog_is_modal_accessible_cancelable_and_double_submit_safe(self) -> None:
        script = (ROOT / "backend" / "app" / "static" / "confirm_submit.js").read_text()
        styles = (ROOT / "backend" / "app" / "static" / "styles.css").read_text()

        self.assertIn('document.createElement("dialog")', script)
        self.assertIn('dialog.setAttribute("role", "alertdialog")', script)
        self.assertIn('dialog.setAttribute("aria-modal", "true")', script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn('event.stopImmediatePropagation()', script)
        self.assertIn('event.key !== "Tab"', script)
        self.assertIn('setDeleteConfirmation(activeDeleteForm, false)', script)
        self.assertIn('activeDeleteTrigger.focus()', script)
        self.assertIn('form.dataset.deleteSubmitting === "true"', script)
        self.assertIn('disableDeleteSubmitters(form)', script)
        self.assertIn('form.requestSubmit(submitter || undefined)', script)
        self.assertIn('confirmButton.hidden = blocked', script)
        self.assertIn('confirmButton.disabled = blocked', script)
        self.assertIn('.delete-confirmation-dialog::backdrop', styles)
        self.assertIn('.delete-confirmation-dialog [hidden]', styles)
        self.assertIn('display: none !important', styles)

    def test_preflight_message_distinguishes_counts_shared_media_and_blocks(self) -> None:
        allowed = confirmation_message(
            "Удалить сущность?",
            child_counts=(("дочерних записей", 2),),
            media=MediaDeletePreview(3, 4, 1),
        )
        blocked = confirmation_message(
            "Удалить сущность?",
            media=MediaDeletePreview(1, 1, 0, "обнаружена внешняя ссылка"),
        )

        self.assertEqual(
            allowed,
            "Удалить сущность? Дочерних записей: 2; связанных материалов: 3; файлов и папок: 4; "
            "общих файлов будет сохранено: 1.",
        )
        self.assertTrue(blocked.startswith("Удаление недоступно:"))
        self.assertIn("обнаружена внешняя ссылка", blocked)


if __name__ == "__main__":
    unittest.main()
