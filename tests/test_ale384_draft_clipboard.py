from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DraftClipboardFlowTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_person_and_reward_draft_controls_use_shared_clipboard_first_flow(self) -> None:
        person_template = self.read("backend/app/templates/person_form.html")
        reward_template = self.read("backend/app/templates/reward_form.html")
        draft_script = self.read("backend/app/static/person_create_draft.js")
        clipboard_script = self.read("backend/app/static/clipboard_paste.js")

        self.assertIn("data-draft-photo-trigger", person_template)
        self.assertIn("data-draft-photo-trigger", reward_template)
        self.assertIn("window.FedorinovClipboardImages", draft_script)
        handler = draft_script.split('button.addEventListener("click", async () => {', 1)[1].split(
            'input.addEventListener("change"', 1
        )[0]
        self.assertLess(handler.index("helper.readWithTimeout"), handler.index("input.click()"))
        self.assertLess(handler.index("uploadDraftPhoto"), handler.index("helper.consumePending"))
        self.assertIn("helper.clearPending(clipboardImage.fingerprint)", handler)
        self.assertIn("helper.endFeedback(button)", handler)
        self.assertIn("consumePending: consumePendingClipboardImage", clipboard_script)

    def test_empty_denied_or_consumed_clipboard_falls_back_to_file_picker(self) -> None:
        script = self.read("backend/app/static/person_create_draft.js")
        handler = script.split('button.addEventListener("click", async () => {', 1)[1].split(
            'input.addEventListener("change"', 1
        )[0]

        self.assertIn("catch (_error)", handler)
        fallback = handler.split("catch (_error)", 1)[1].split("return;", 1)[0]
        self.assertIn("helper.endFeedback(button)", fallback)
        self.assertIn("input.click()", fallback)

    def test_file_upload_keeps_the_same_draft_endpoint_and_render_update(self) -> None:
        script = self.read("backend/app/static/person_create_draft.js")

        self.assertIn('form.append("photo_field", photoField || "")', script)
        self.assertIn('form.append("file", file, file.name || "clipboard.jpg")', script)
        self.assertIn('return jsonRequest(photoBase, { method: "POST", body: form })', script)
        self.assertIn("applyDraftPhoto(card, payload)", script)


if __name__ == "__main__":
    unittest.main()
