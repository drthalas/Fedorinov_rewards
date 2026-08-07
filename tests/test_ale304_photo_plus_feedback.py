from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Ale304PhotoPlusFeedbackTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_shared_helper_owns_feedback_and_bounded_clipboard_budget(self) -> None:
        clipboard = self.read("backend/app/static/clipboard_paste.js")
        rank = self.read("backend/app/static/guide_image_preview.js")
        styles = self.read("backend/app/static/styles.css")

        self.assertIn("var CLIPBOARD_ATTEMPT_TIMEOUT_MS = 500;", clipboard)
        self.assertIn("var CLIPBOARD_ATTEMPT_HARD_CEILING_MS = 1000;", clipboard)
        self.assertIn("beginFeedback: beginClipboardFeedback", clipboard)
        self.assertIn("endFeedback: endClipboardFeedback", clipboard)
        self.assertIn('trigger.dataset.clipboardPending = "true"', clipboard)
        self.assertIn('trigger.setAttribute("aria-busy", "true")', clipboard)
        self.assertIn('trigger.setAttribute("aria-label", "Проверяем буфер…")', clipboard)
        self.assertIn("if (!beginClipboardFeedback(button)) return;", clipboard)
        self.assertNotIn("freshImageBlobFromClipboardWithTimeout(2000)", clipboard)
        self.assertNotIn("helper.readWithTimeout(1200)", rank)
        self.assertIn("helper.beginFeedback(trigger)", rank)
        self.assertIn("helper.endFeedback(trigger)", rank)
        self.assertIn('[data-photo-plus-trigger][data-clipboard-pending="true"]', styles)
        self.assertIn("@keyframes photo-clipboard-spin", styles)

    def test_feedback_lifecycle_is_idempotent_and_restores_accessibility(self) -> None:
        script_path = ROOT / "backend/app/static/clipboard_paste.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
global.window = global;
global.location = { href: "http://127.0.0.1/persons/1/edit", pathname: "/persons/1/edit", search: "" };
global.sessionStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
global.document = { addEventListener() {}, querySelectorAll() { return []; } };
global.URL = URL;
global.URLSearchParams = URLSearchParams;
eval(source);

const attrs = new Map([["aria-label", "Добавить фотографию"], ["title", "Добавить фотографию"]]);
const button = {
  dataset: {},
  disabled: false,
  getAttribute(name) { return attrs.has(name) ? attrs.get(name) : null; },
  setAttribute(name, value) { attrs.set(name, String(value)); },
  removeAttribute(name) { attrs.delete(name); },
};
const api = FedorinovClipboardImages;
const first = api.beginFeedback(button);
const second = api.beginFeedback(button);
const pending = { disabled: button.disabled, busy: attrs.get("aria-busy"), label: attrs.get("aria-label"), marker: button.dataset.clipboardPending };
api.endFeedback(button);
const restored = { disabled: button.disabled, busy: attrs.has("aria-busy"), label: attrs.get("aria-label"), title: attrs.get("title"), marker: button.dataset.clipboardPending || "" };
api.endFeedback(button);
process.stdout.write(JSON.stringify({ first, second, pending, restored }));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "feedback_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            json.loads(completed.stdout),
            {
                "first": True,
                "second": False,
                "pending": {
                    "disabled": True,
                    "busy": "true",
                    "label": "Проверяем буфер…",
                    "marker": "true",
                },
                "restored": {
                    "disabled": False,
                    "busy": False,
                    "label": "Добавить фотографию",
                    "title": "Добавить фотографию",
                    "marker": "",
                },
            },
        )

    def test_static_cache_key_changes_with_photo_feedback(self) -> None:
        templates = self.read("backend/app/routers/templates.py")
        self.assertIn('STATIC_ASSET_VERSION = "20260807-ale361-post-create-layout-1"', templates)


if __name__ == "__main__":
    unittest.main()
