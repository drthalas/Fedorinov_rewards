from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest

from jinja2 import Environment


ROOT = Path(__file__).resolve().parents[1]


class Ale281ImageReplacementConfirmationTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def render_photo_controls(self, entity_type: str) -> str:
        template = Environment(autoescape=True).from_string(
            self.read("backend/app/templates/photo_management.html")
        )
        return template.render(
            mode="edit",
            settings=type("Settings", (), {"write_mode": True})(),
            request=type(
                "Request",
                (),
                {"url": type("Url", (), {"path": f"/{entity_type}/42/edit"})()},
            )(),
            return_to="",
            photo_controls=[
                {"field": "front_foto", "label": "Пустой слот", "path": None},
                {"field": "back_foto", "label": "Занятый слот", "path": "Source/42/back.jpg"},
            ],
            photo_manage_compact=False,
            photo_entity_type=entity_type,
            photo_entity_id=42,
            has_media_path=bool,
            photo_view_url=lambda path, label, return_to: "/photo/view",
            media_url=lambda path: "/media",
        )

    def test_all_managed_photo_surfaces_mark_empty_and_occupied_slots(self) -> None:
        for entity_type in ("person", "reward", "mark"):
            with self.subTest(entity_type=entity_type):
                rendered = self.render_photo_controls(entity_type)
                expected_markers = 2 if entity_type == "mark" else 1
                self.assertEqual(rendered.count('data-image-slot-occupied="false"'), expected_markers)
                self.assertEqual(rendered.count('data-image-slot-occupied="true"'), expected_markers)
                self.assertEqual(rendered.count("data-photo-plus-trigger"), 2)

    def test_shared_confirmation_is_accessible_and_cancel_cannot_run_action(self) -> None:
        script = self.read("backend/app/static/image_replacement_confirmation.js")
        self.assertIn('dialog.setAttribute("role", "dialog")', script)
        self.assertIn('dialog.setAttribute("aria-modal", "true")', script)
        self.assertIn('event.key === "Escape"', script)
        self.assertIn("event.stopImmediatePropagation()", script)
        self.assertIn('document.addEventListener("keydown", trapFocus, true)', script)
        self.assertIn("cancelReplacement();", script)
        self.assertIn("focusWithoutScroll(trigger)", script)
        self.assertIn("if (!isOccupied(trigger))", script)
        self.assertIn("pendingAction = action", script)
        self.assertIn('dialog.querySelector("[data-image-replace-confirm]")', script)

        cancel = script.split("function cancelReplacement()", 1)[1].split(
            "function confirmReplacement()", 1
        )[0]
        self.assertNotIn("pendingAction()", cancel)
        self.assertNotIn("action()", cancel)
        confirm = script.split("function confirmReplacement()", 1)[1].split(
            "function trapFocus", 1
        )[0]
        self.assertIn('if (typeof action === "function") action()', confirm)

    def test_shared_confirmation_state_machine_executes_empty_cancel_confirm_and_escape(self) -> None:
        script_path = ROOT / "backend" / "app" / "static" / "image_replacement_confirmation.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
function control(name) {
  return {
    name,
    attrs: {},
    listeners: {},
    focus() { document.activeElement = this; },
    getAttribute(key) { return this.attrs[key] ?? null; },
    setAttribute(key, value) { this.attrs[key] = String(value); },
    addEventListener(type, callback) { this.listeners[type] = callback; },
  };
}
const cancel = control("cancel");
const confirm = control("confirm");
const dialog = {
  hidden: true,
  attrs: {},
  listeners: {},
  setAttribute(key, value) { this.attrs[key] = String(value); },
  addEventListener(type, callback) { this.listeners[type] = callback; },
  querySelector(selector) { return selector.includes("cancel") ? cancel : confirm; },
  querySelectorAll() { return [cancel, confirm]; },
  set innerHTML(_value) {},
};
global.window = global;
global.document = {
  activeElement: null,
  body: { appendChild() {} },
  createElement() { return dialog; },
  addEventListener(type, callback, capture) { listeners[type] = { callback, capture }; },
};
eval(source);
let actions = 0;
const empty = control("empty");
empty.setAttribute("data-image-slot-occupied", "false");
const occupied = control("occupied");
occupied.setAttribute("data-image-slot-occupied", "true");
FedorinovImageReplacement.run(empty, () => { actions += 1; });
const emptyResult = { actions, hidden: dialog.hidden };
FedorinovImageReplacement.run(occupied, () => { actions += 1; });
const beforeCancel = { actions, hidden: dialog.hidden };
cancel.listeners.click();
const afterCancel = { actions, hidden: dialog.hidden, focused: document.activeElement === occupied };
FedorinovImageReplacement.run(occupied, () => { actions += 1; });
confirm.listeners.click();
const afterConfirm = { actions, hidden: dialog.hidden };
FedorinovImageReplacement.run(occupied, () => { actions += 1; });
const escape = { key: "Escape", prevented: false, stopped: false, preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; } };
listeners.keydown.callback(escape);
const afterEscape = { actions, hidden: dialog.hidden, focused: document.activeElement === occupied, prevented: escape.prevented, stopped: escape.stopped, capture: listeners.keydown.capture };
process.stdout.write(JSON.stringify({ emptyResult, beforeCancel, afterCancel, afterConfirm, afterEscape }));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale281_confirmation_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        self.assertEqual(result["emptyResult"], {"actions": 1, "hidden": True})
        self.assertEqual(result["beforeCancel"], {"actions": 1, "hidden": False})
        self.assertEqual(result["afterCancel"], {"actions": 1, "hidden": True, "focused": True})
        self.assertEqual(result["afterConfirm"], {"actions": 2, "hidden": True})
        self.assertEqual(
            result["afterEscape"],
            {
                "actions": 2,
                "hidden": True,
                "focused": True,
                "prevented": True,
                "stopped": True,
                "capture": True,
            },
        )

    def test_clipboard_first_flows_run_only_after_shared_confirmation(self) -> None:
        clipboard = self.read("backend/app/static/clipboard_paste.js")
        inline = clipboard.split("function bindInlinePhotoTrigger(button)", 1)[1].split(
            "window.FedorinovClipboardImages", 1
        )[0]
        self.assertIn("confirmation.run(button, beginPhotoFlow)", inline)
        self.assertIn("imageBlobFromClipboardWithTimeout(2000)", inline)
        self.assertLess(
            inline.index("confirmation.run(button, beginPhotoFlow)"),
            inline.index("beginPhotoFlow();", inline.index("confirmation.run(button, beginPhotoFlow)")),
        )
        self.assertIn("confirmation.run(button, beginClipboardPaste)", clipboard)

        preview = self.read("backend/app/static/guide_image_preview.js")
        rank = preview.split("function initRankImageEditor(editor)", 1)[1]
        self.assertIn("confirmation.run(trigger, beginRankImageFlow)", rank)
        rank_flow = rank.split("async function beginRankImageFlow()", 1)[1].split(
            'trigger.addEventListener("click"', 1
        )[0]
        self.assertLess(rank_flow.index("helper.readWithTimeout"), rank_flow.index("openFilePicker()"))

    def test_rank_and_guide_occupied_state_share_the_same_mechanism(self) -> None:
        rank_form = self.read("backend/app/templates/rank_form.html")
        guide_form = self.read("backend/app/templates/guide_level_form.html")
        preview = self.read("backend/app/static/guide_image_preview.js")

        self.assertIn('data-image-slot-occupied="{{ \'true\' if has_rank_image else \'false\' }}"', rank_form)
        self.assertIn('data-image-slot-occupied="{{ \'true\' if item.image_path else \'false\' }}"', guide_form)
        guide = preview.split("function initForm(form)", 1)[1].split(
            "function initRankImageEditor", 1
        )[0]
        self.assertIn("confirmation.run(input", guide)
        self.assertIn("event.preventDefault()", guide)
        self.assertIn("allowConfirmedPicker = true", guide)
        self.assertIn("input.click()", guide)
        self.assertIn("setInputOccupied(true)", guide)
        self.assertIn("setTriggerOccupied(true)", preview)
        self.assertIn("setTriggerOccupied(false)", preview)

    def test_shared_script_loads_before_clipboard_and_guide_handlers(self) -> None:
        for template_path in (
            "backend/app/templates/base.html",
            "backend/app/templates/legacy_base.html",
        ):
            with self.subTest(template=template_path):
                template = self.read(template_path)
                self.assertLess(
                    template.index("image_replacement_confirmation.js"),
                    template.index("clipboard_paste.js"),
                )
        base = self.read("backend/app/templates/base.html")
        self.assertLess(base.index("image_replacement_confirmation.js"), base.index("guide_image_preview.js"))


if __name__ == "__main__":
    unittest.main()
