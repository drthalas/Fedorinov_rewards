from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Ale345WritePerformanceUxTests(unittest.TestCase):
    def test_person_and_shared_photo_forms_opt_into_write_feedback(self) -> None:
        person = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")
        photos = (ROOT / "backend/app/templates/photo_management.html").read_text(encoding="utf-8")
        clipboard = (ROOT / "backend/app/static/clipboard_paste.js").read_text(encoding="utf-8")
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")

        self.assertIn('data-write-pending-label="Сохраняем…"', person)
        self.assertIn('data-write-pending-label="Сохраняем фото…"', photos)
        self.assertIn('data-write-pending-label="Удаляем…"', photos)
        self.assertIn('data-write-compact="true"', photos)
        self.assertIn("input.form.requestSubmit()", clipboard)
        self.assertNotIn("input.form.submit()", clipboard)
        self.assertIn("write_feedback.js", base)
        self.assertIn("write_feedback.js", legacy_base)
        self.assertIn(".write-operation-overlay", styles)
        self.assertIn('[data-write-busy="true"]', styles)

    def test_static_cache_key_covers_new_write_feedback_assets(self) -> None:
        templates = (ROOT / "backend/app/routers/templates.py").read_text(encoding="utf-8")
        self.assertIn('STATIC_ASSET_VERSION = "20260807-ale354-alphabet-lifecycle-corrective-2"', templates)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_write_feedback_is_immediate_blocks_duplicates_and_recovers_after_error(self) -> None:
        script_path = ROOT / "backend/app/static/write_feedback.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const documentListeners = {};
const windowListeners = {};

function element() {
  return {
    attrs: {}, dataset: {}, hidden: false, textContent: "", className: "", disabled: false,
    children: [], isConnected: true,
    setAttribute(name, value) { this.attrs[name] = String(value); },
    getAttribute(name) { return Object.prototype.hasOwnProperty.call(this.attrs, name) ? this.attrs[name] : null; },
    removeAttribute(name) { delete this.attrs[name]; },
    append(...items) { this.children.push(...items); },
    querySelector(selector) {
      if (selector === "[data-write-operation-message]") {
        return this.children.find((item) => item.dataset.writeOperationMessage === "true") || null;
      }
      return null;
    },
    querySelectorAll() { return []; },
  };
}

const button = element();
button.type = "submit";
button.textContent = "Сохранить";
button.setAttribute("aria-label", "Сохранить карточку");
const form = element();
form.dataset.writePendingLabel = "Сохраняем…";
form.matches = (selector) => selector === "form[data-write-feedback]";
form.querySelectorAll = (selector) => selector === "button, input[type='submit']" ? [button] : [];
form.querySelector = (selector) => {
  if (selector === "button[type='submit'], input[type='submit']") return button;
  return null;
};
form.closest = () => null;

global.window = global;
window.setTimeout = () => 1;
window.clearTimeout = () => {};
window.addEventListener = (type, callback) => { windowListeners[type] = callback; };
global.document = {
  body: { append(node) { node.isConnected = true; } },
  createElement: element,
  addEventListener(type, callback) { documentListeners[type] = callback; },
};

eval(source);

function submitEvent() {
  return {
    target: form, submitter: button, defaultPrevented: false, prevented: false, stopped: false,
    preventDefault() { this.defaultPrevented = true; this.prevented = true; },
    stopImmediatePropagation() { this.stopped = true; },
  };
}

const first = submitEvent();
documentListeners.submit(first);
const immediate = {
  prevented: first.prevented,
  busy: form.dataset.writeSubmitting,
  formAriaBusy: form.attrs["aria-busy"],
  buttonDisabled: button.disabled,
  buttonText: button.textContent,
  buttonBusy: button.dataset.writeBusy,
};

const duplicate = submitEvent();
documentListeners.submit(duplicate);

window.FedorinovWriteFeedback.finish(form, { state: "error", message: "Не удалось сохранить." });
const recovered = {
  busy: form.dataset.writeSubmitting || null,
  formAriaBusy: form.attrs["aria-busy"] || null,
  buttonDisabled: button.disabled,
  buttonText: button.textContent,
  buttonBusy: button.dataset.writeBusy || null,
  buttonAriaLabel: button.attrs["aria-label"],
};

window.FedorinovWriteFeedback.begin(form, button, "Сохраняем…");
windowListeners.pageshow();
const pageshow = {
  busy: form.dataset.writeSubmitting || null,
  buttonDisabled: button.disabled,
  buttonText: button.textContent,
};

process.stdout.write(JSON.stringify({
  immediate,
  duplicate: { prevented: duplicate.prevented, stopped: duplicate.stopped },
  recovered,
  pageshow,
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale345_write_feedback_runner.js"
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
                "immediate": {
                    "prevented": False,
                    "busy": "true",
                    "formAriaBusy": "true",
                    "buttonDisabled": True,
                    "buttonText": "Сохраняем…",
                    "buttonBusy": "true",
                },
                "duplicate": {"prevented": True, "stopped": True},
                "recovered": {
                    "busy": None,
                    "formAriaBusy": None,
                    "buttonDisabled": False,
                    "buttonText": "Сохранить",
                    "buttonBusy": None,
                    "buttonAriaLabel": "Сохранить карточку",
                },
                "pageshow": {
                    "busy": None,
                    "buttonDisabled": False,
                    "buttonText": "Сохранить",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
