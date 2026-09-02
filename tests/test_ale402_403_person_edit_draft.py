from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PersonEditDraftTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_edit_form_has_scoped_biography_dialog_and_photo_draft_contract(self) -> None:
        template = self.read("backend/app/templates/person_form.html")
        photo_template = self.read("backend/app/templates/photo_management.html")
        base = self.read("backend/app/templates/base.html")
        templates_router = self.read("backend/app/routers/templates.py")

        self.assertIn('data-person-edit-draft data-person-id="{{ person.id }}"', template)
        self.assertEqual(template.count("data-person-text-toggle"), 2)
        self.assertEqual(template.count("data-person-text-source"), 2)
        self.assertEqual(template.count('data-person-text-dialog="'), 2)
        self.assertEqual(template.count("data-person-text-expanded"), 2)
        self.assertIn("data-person-photo-upload", photo_template)
        self.assertEqual(photo_template.count("data-person-photo-mutation"), 2)
        self.assertLess(base.index("person_edit_draft.js"), base.index("clipboard_paste.js"))
        self.assertIn('STATIC_ASSET_VERSION = "20260902-ale411-clipboard-draft"', templates_router)

    def test_biography_container_is_large_scrollable_and_scoped(self) -> None:
        styles = self.read("backend/app/static/styles.css")

        self.assertIn(".biography-editor-dialog[hidden]", styles)
        self.assertIn("width: min(920px, calc(100vw - 48px));", styles)
        self.assertIn("height: min(76vh, 720px);", styles)
        self.assertIn("overflow-y: auto;", styles)
        self.assertIn("body.biography-editor-open", styles)

    def test_clipboard_and_file_picker_share_person_draft_capture(self) -> None:
        controller = self.read("backend/app/static/person_edit_draft.js")
        clipboard = self.read("backend/app/static/clipboard_paste.js")

        self.assertIn('form.matches("form[data-person-photo-upload]")', controller)
        self.assertIn("personDraft.captureForPhoto(button)", clipboard)
        self.assertIn('params.get("status") === "photo_updated"', controller)
        self.assertIn('params.get("status") === "photo_cleared"', controller)
        self.assertIn('params.get("media_cleanup") === "failed"', controller)
        self.assertIn("responseUrl.pathname + responseUrl.search + responseUrl.hash", clipboard)
        self.assertNotIn("localStorage", controller)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_multiple_text_fields_survive_repeated_photo_redirects(self) -> None:
        script_path = ROOT / "backend/app/static/person_edit_draft.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
const storage = new Map();

function control(name, value, type = "text") {
  return {
    name, value, type, disabled: false, checked: true,
    events: [],
    dispatchEvent(event) { this.events.push(event.type); },
  };
}

const controls = [
  control("fio", "Draft Name"),
  control("birthday", "1901"),
  control("id_rank", "7", "select-one"),
  control("link1", "https://draft.example/one"),
  control("biography", "Draft biography\nsecond paragraph", "textarea"),
  control("comment", "Draft comment", "textarea"),
  control("active", "1", "checkbox"),
  control("return_to", "/legacy", "hidden"),
];
controls.find((item) => item.name === "active").checked = false;
const form = {
  dataset: { personId: "42" },
  querySelectorAll(selector) {
    if (selector === "input[name], select[name], textarea[name]") return controls;
    return [];
  },
  querySelector() { return null; },
  addEventListener() {},
};
const trigger = {
  getAttribute(name) {
    return { "data-entity-type": "person", "data-entity-id": "42" }[name] || "";
  },
};

global.window = global;
window.location = { pathname: "/persons/42/edit", search: "" };
window.sessionStorage = {
  getItem(key) { return storage.has(key) ? storage.get(key) : null; },
  setItem(key, value) { storage.set(key, String(value)); },
  removeItem(key) { storage.delete(key); },
};
global.document = {
  readyState: "loading",
  body: { classList: { add() {}, remove() {} } },
  querySelector(selector) {
    if (selector === "form[data-person-edit-draft]") return form;
    return null;
  },
  addEventListener(type, callback) { listeners[type] = callback; },
};

eval(source);
const api = window.FedorinovPersonEditDraft;
const firstCapture = api.captureForPhoto(trigger);
controls.forEach((item) => { if (item.type !== "hidden") item.value = `persisted-${item.name}`; });
controls.find((item) => item.name === "active").checked = true;
window.location.search = "?status=photo_updated";
listeners.DOMContentLoaded();
const afterFirst = Object.fromEntries(controls.filter((item) => item.type !== "hidden").map((item) => [item.name, item.value]));
const activeAfterFirst = controls.find((item) => item.name === "active").checked;

controls.find((item) => item.name === "fio").value = "Second draft name";
controls.find((item) => item.name === "biography").value = "Second draft biography";
controls.find((item) => item.name === "comment").value = "Second draft comment";
window.location.search = "";
const secondCapture = api.captureForPhoto(trigger);
controls.forEach((item) => { if (item.type !== "hidden") item.value = `old-${item.name}`; });
window.location.search = "?media_cleanup=failed";
listeners.DOMContentLoaded();
const afterSecond = Object.fromEntries(controls.filter((item) => item.type !== "hidden").map((item) => [item.name, item.value]));

process.stdout.write(JSON.stringify({ firstCapture, secondCapture, afterFirst, afterSecond, activeAfterFirst, storageEmpty: storage.size === 0 }));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "person_edit_draft_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )

        result = json.loads(completed.stdout)
        self.assertTrue(result["firstCapture"])
        self.assertTrue(result["secondCapture"])
        self.assertEqual(result["afterFirst"]["fio"], "Draft Name")
        self.assertEqual(result["afterFirst"]["biography"], "Draft biography\nsecond paragraph")
        self.assertEqual(result["afterFirst"]["comment"], "Draft comment")
        self.assertFalse(result["activeAfterFirst"])
        self.assertEqual(result["afterSecond"]["fio"], "Second draft name")
        self.assertEqual(result["afterSecond"]["biography"], "Second draft biography")
        self.assertEqual(result["afterSecond"]["comment"], "Second draft comment")
        self.assertTrue(result["storageEmpty"])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_clear_photo_submit_captures_and_restores_the_whole_draft(self) -> None:
        script_path = ROOT / "backend/app/static/person_edit_draft.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
const storage = new Map();
function control(name, value, type = "text", checked = true) {
  return { name, value, type, checked, disabled: false, dispatchEvent() {} };
}
const controls = [
  control("fio", "Unsaved name"),
  control("biography", "Unsaved biography", "textarea"),
  control("comment", "Unsaved comment", "textarea"),
  control("instock", "1", "checkbox", false),
];
const editForm = {
  dataset: { personId: "42" },
  querySelectorAll(selector) { return selector === "input[name], select[name], textarea[name]" ? controls : []; },
  querySelector() { return null; },
  addEventListener() {},
};
const clearForm = {
  dataset: { personId: "42" },
  matches(selector) { return selector === "form[data-person-photo-mutation]"; },
};
global.window = global;
window.location = { pathname: "/persons/42/edit", search: "" };
window.sessionStorage = {
  getItem(key) { return storage.get(key) || null; },
  setItem(key, value) { storage.set(key, String(value)); },
  removeItem(key) { storage.delete(key); },
};
global.document = {
  readyState: "loading",
  body: { classList: { add() {}, remove() {} } },
  querySelector(selector) { return selector === "form[data-person-edit-draft]" ? editForm : null; },
  addEventListener(type, callback) { listeners[type] = callback; },
};
eval(source);
listeners.submit({ target: clearForm });
controls[0].value = "Persisted name";
controls[1].value = "Persisted biography";
controls[2].value = "Persisted comment";
controls[3].checked = true;
window.location.search = "?status=photo_cleared";
listeners.DOMContentLoaded();
process.stdout.write(JSON.stringify({
  fio: controls[0].value,
  biography: controls[1].value,
  comment: controls[2].value,
  instock: controls[3].checked,
  storageEmpty: storage.size === 0,
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "person_edit_clear_photo_runner.js"
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
                "fio": "Unsaved name",
                "biography": "Unsaved biography",
                "comment": "Unsaved comment",
                "instock": False,
                "storageEmpty": True,
            },
        )

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_restore_runs_before_later_defer_scripts_consume_success_query(self) -> None:
        script_path = ROOT / "backend/app/static/person_edit_draft.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const key = "fedorinov-person-edit-photo-draft-v1:42";
const storage = new Map([[key, JSON.stringify({
  pathname: "/persons/42/edit",
  personId: "42",
  values: { fio: "Draft before transient cleanup", biography: "Draft biography" },
  savedAt: Date.now(),
})]]);
function control(name, value) {
  return {
    name, value, type: "text", disabled: false, checked: true,
    dispatchEvent() {},
  };
}
const controls = [control("fio", "Persisted name"), control("biography", "Persisted biography")];
const form = {
  dataset: { personId: "42" },
  querySelectorAll(selector) { return selector === "input[name], select[name], textarea[name]" ? controls : []; },
  querySelector() { return null; },
  addEventListener() {},
};
global.window = global;
window.location = { pathname: "/persons/42/edit", search: "?status=photo_updated" };
window.sessionStorage = {
  getItem(storageKey) { return storage.get(storageKey) || null; },
  setItem(storageKey, value) { storage.set(storageKey, String(value)); },
  removeItem(storageKey) { storage.delete(storageKey); },
};
global.document = {
  readyState: "interactive",
  body: { classList: { add() {}, remove() {} } },
  querySelector(selector) {
    if (selector === "form[data-person-edit-draft]") return form;
    return null;
  },
  addEventListener() {},
};
eval(source);
process.stdout.write(JSON.stringify({
  fio: controls[0].value,
  biography: controls[1].value,
  storageEmpty: storage.size === 0,
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "person_edit_defer_race_runner.js"
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
                "fio": "Draft before transient cleanup",
                "biography": "Draft biography",
                "storageEmpty": True,
            },
        )

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_biography_main_and_expanded_editors_share_one_live_draft(self) -> None:
        script_path = ROOT / "backend/app/static/person_edit_draft.js"
        runner = r'''
const fs = require("fs");
const sourceCode = fs.readFileSync(process.argv[2], "utf8");
const documentListeners = {};

function interactive(value = "") {
  return {
    value,
    listeners: {},
    attributes: {},
    addEventListener(type, callback) { this.listeners[type] = callback; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    focus() { this.focused = true; },
  };
}

const source = interactive("Persisted biography");
source.name = "biography";
source.type = "textarea";
source.disabled = false;
source.checked = true;
source.dispatchEvent = () => {};
const trigger = interactive();
trigger.dataset = { personTextLabel: "Краткая биография" };
trigger.querySelector = () => null;
const expanded = interactive();
const close = interactive();
const dialog = interactive();
dialog.hidden = true;
dialog.querySelector = (selector) => selector === "[data-person-text-expanded]" ? expanded : null;
dialog.querySelectorAll = (selector) => selector === "[data-person-text-close]" ? [close] : [];
const field = interactive();
field.dataset = { personTextEditor: "biography" };
field.querySelector = (selector) => ({
  "[data-person-text-source]": source,
  "[data-person-text-toggle]": trigger,
}[selector] || null);
const form = interactive();
form.dataset = { personId: "42" };
form.querySelector = () => null;
form.querySelectorAll = (selector) => {
  if (selector === "[data-person-text-editor]") return [field];
  if (selector === "input[name], select[name], textarea[name]") return [source];
  return [];
};

global.window = global;
window.location = { pathname: "/persons/42/edit", search: "" };
window.sessionStorage = { getItem() { return null; }, setItem() {}, removeItem() {} };
global.document = {
  readyState: "loading",
  body: { classList: { add(value) { this.value = value; }, remove() { this.value = ""; } } },
  querySelector(selector) {
    if (selector === "form[data-person-form]") return form;
    if (selector === "form[data-person-edit-draft]") return form;
    if (selector === '[data-person-text-dialog="biography"]') return dialog;
    return null;
  },
  addEventListener(type, callback) { documentListeners[type] = callback; },
};

eval(sourceCode);
documentListeners.DOMContentLoaded();
source.value = "Main draft\nparagraph two";
source.listeners.input();
trigger.listeners.click();
const openedValue = expanded.value;
expanded.value = "Expanded draft\nparagraph two\nparagraph three";
expanded.listeners.input();
close.listeners.click();
const valueAfterClose = source.value;
source.value = "Main changed again";
source.listeners.input();
trigger.listeners.click();
const reopenedValue = expanded.value;

process.stdout.write(JSON.stringify({
  openedValue,
  valueAfterClose,
  reopenedValue,
  dialogOpen: dialog.hidden === false,
  ariaExpanded: trigger.attributes["aria-expanded"],
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "biography_draft_runner.js"
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
                "openedValue": "Main draft\nparagraph two",
                "valueAfterClose": "Expanded draft\nparagraph two\nparagraph three",
                "reopenedValue": "Main changed again",
                "dialogOpen": True,
                "ariaExpanded": "true",
            },
        )


if __name__ == "__main__":
    unittest.main()
