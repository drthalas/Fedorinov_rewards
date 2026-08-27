from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PersonTextEditorTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_create_and_edit_markup_use_two_compact_text_editor_controls(self) -> None:
        template = self.read("backend/app/templates/person_form.html")
        script = self.read("backend/app/static/person_edit_draft.js")

        self.assertEqual(template.count('data-person-text-editor="'), 2)
        self.assertEqual(template.count("data-person-text-toggle"), 2)
        self.assertEqual(template.count("data-person-text-source"), 2)
        self.assertEqual(template.count('data-person-text-dialog="'), 2)
        self.assertEqual(template.count("data-person-text-expanded"), 2)
        self.assertIn("Краткая биография", template)
        self.assertIn("Комментарий / заметки", template)
        self.assertIn('name="biography"', template)
        self.assertIn('name="comment"', template)
        self.assertNotIn("Развернуть", template)
        self.assertNotIn("Развернуть", script)
        self.assertNotIn('class="sr-only"', template)
        self.assertEqual(template.count("Открыть увеличенный редактор:"), 2)
        self.assertNotIn('{% if mode == "edit" %}\n          <button class="biography-expand-button"', template)

    def test_control_is_a_borderless_inline_icon_without_button_chrome(self) -> None:
        styles = self.read("backend/app/static/styles.css")
        rule = styles.split(".cavalier-page-theme .person-text-expand-button {", 1)[1].split("}", 1)[0]

        self.assertIn(".person-text-expand-button", styles)
        self.assertIn("width: 16px;", rule)
        self.assertIn("height: 16px;", rule)
        self.assertIn("border: 0;", rule)
        self.assertIn("background: transparent;", rule)
        self.assertIn("box-shadow: none;", rule)
        self.assertNotIn("26px", rule)
        self.assertIn(".person-text-field-heading", styles)
        self.assertIn("align-items: center;", styles)
        self.assertIn("justify-content: flex-start;", styles)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_two_editors_keep_independent_live_drafts(self) -> None:
        script_path = ROOT / "backend/app/static/person_edit_draft.js"
        runner = r'''
const fs = require("fs");
const sourceCode = fs.readFileSync(process.argv[2], "utf8");
const documentListeners = {};

function interactive(value = "") {
  return {
    value, hidden: false, dataset: {}, listeners: {}, attributes: {},
    addEventListener(type, callback) { this.listeners[type] = callback; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    focus() { this.focused = true; },
  };
}

function editor(key, initial) {
  const source = interactive(initial);
  source.name = key;
  source.type = "textarea";
  source.disabled = false;
  source.checked = true;
  source.dispatchEvent = () => {};
  const trigger = interactive();
  trigger.dataset.personTextLabel = key;
  const expanded = interactive();
  const close = interactive();
  const dialog = interactive();
  dialog.hidden = true;
  dialog.dataset.personTextDialog = key;
  dialog.querySelector = (selector) => selector === "[data-person-text-expanded]" ? expanded : null;
  dialog.querySelectorAll = (selector) => selector === "[data-person-text-close]" ? [close] : [];
  const field = interactive();
  field.dataset.personTextEditor = key;
  field.querySelector = (selector) => ({
    "[data-person-text-source]": source,
    "[data-person-text-toggle]": trigger,
  }[selector] || null);
  return { key, source, trigger, expanded, close, dialog, field };
}

const biography = editor("biography", "Bio initial");
const comment = editor("comment", "Comment initial");
const form = interactive();
form.dataset = { personId: "42" };
form.querySelectorAll = (selector) => {
  if (selector === "[data-person-text-editor]") return [biography.field, comment.field];
  if (selector === "input[name], select[name], textarea[name]") return [biography.source, comment.source];
  return [];
};

global.window = global;
window.location = { pathname: "/persons/42/edit", search: "" };
window.sessionStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
global.document = {
  readyState: "loading",
  body: { classList: { add() {}, remove() {} } },
  querySelector(selector) {
    if (selector === "form[data-person-form]") return form;
    if (selector === "form[data-person-edit-draft]") return form;
    const match = selector.match(/^\[data-person-text-dialog="(.+)"\]$/);
    if (match && match[1] === "biography") return biography.dialog;
    if (match && match[1] === "comment") return comment.dialog;
    return null;
  },
  addEventListener(type, callback) { documentListeners[type] = callback; },
};

eval(sourceCode);
documentListeners.DOMContentLoaded();

biography.trigger.listeners.click();
biography.expanded.value = "Bio expanded draft";
biography.expanded.listeners.input();
biography.close.listeners.click();

comment.trigger.listeners.click();
comment.expanded.value = "Comment expanded draft";
comment.expanded.listeners.input();
comment.close.listeners.click();

biography.source.value = "Bio changed collapsed";
biography.source.listeners.input();
biography.trigger.listeners.click();

process.stdout.write(JSON.stringify({
  biographySource: biography.source.value,
  biographyExpanded: biography.expanded.value,
  commentSource: comment.source.value,
  commentExpanded: comment.expanded.value,
  biographyOpen: biography.dialog.hidden === false,
  commentOpen: comment.dialog.hidden === false,
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "person_text_editor_runner.js"
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
                "biographySource": "Bio changed collapsed",
                "biographyExpanded": "Bio changed collapsed",
                "commentSource": "Comment expanded draft",
                "commentExpanded": "Comment expanded draft",
                "biographyOpen": True,
                "commentOpen": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
