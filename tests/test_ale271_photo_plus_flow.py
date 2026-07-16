import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import textwrap
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

    def test_state_machine_is_per_control_and_resets_to_clipboard_first(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not installed")

        script_path = ROOT / "backend" / "app" / "static" / "photo_plus_flow.js"
        runner = textwrap.dedent(
            f"""
            const fs = require("fs");
            const vm = require("vm");
            global.window = {{}};
            vm.runInThisContext(fs.readFileSync({json.dumps(str(script_path))}, "utf8"));
            const flow = window.FedorinovPhotoPlusFlow;
            const current = {{}};
            const neighbor = {{}};
            const result = {{ initial: flow.mode(current), neighborInitial: flow.mode(neighbor) }};
            flow.markClipboardSuccess(current);
            result.afterClipboard = flow.mode(current);
            result.shouldPick = flow.shouldOpenFilePicker(current);
            result.neighborAfterClipboard = flow.mode(neighbor);
            flow.reset(current);
            result.afterClear = flow.mode(current);
            result.shouldPickAfterClear = flow.shouldOpenFilePicker(current);
            process.stdout.write(JSON.stringify(result));
            """
        )
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "photo_plus_flow_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(["node", str(runner_path)], check=True, capture_output=True, text=True)

        result = json.loads(completed.stdout)
        self.assertEqual(result["initial"], "clipboard-first")
        self.assertEqual(result["afterClipboard"], "file-next")
        self.assertTrue(result["shouldPick"])
        self.assertEqual(result["neighborInitial"], "clipboard-first")
        self.assertEqual(result["neighborAfterClipboard"], "clipboard-first")
        self.assertEqual(result["afterClear"], "clipboard-first")
        self.assertFalse(result["shouldPickAfterClear"])

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

        script = self.read("backend/app/static/clipboard_paste.js")
        self.assertIn(
            'document.querySelectorAll("[data-photo-plus-trigger]").forEach(bindInlinePhotoTrigger)',
            script,
        )

    def test_managed_flow_preserves_file_next_for_one_upload_reload(self) -> None:
        script = self.read("backend/app/static/clipboard_paste.js")
        handler = script.split("function bindInlinePhotoTrigger(button)", 1)[1].split(
            'document.addEventListener("DOMContentLoaded"', 1
        )[0]

        self.assertIn("flow.shouldOpenFilePicker(button)", handler)
        self.assertIn("flow.markClipboardSuccess(button)", handler)
        self.assertIn('rememberPhotoInteraction(button, "file-next")', handler)
        self.assertIn('state.photoPlusMode === "file-next"', script)
        self.assertIn("flow.reset(button)", handler)
        self.assertIn("flow.reset(button);\n        }\n        rememberPhotoInteraction(button);", handler)
        self.assertLess(handler.index("flow.shouldOpenFilePicker(button)"), handler.index("imageBlobFromClipboardWithTimeout"))

        cancel_handler = script.split('input.addEventListener("cancel"', 1)[1].split("}, { once: true });", 1)[0]
        self.assertNotIn("flow.reset", cancel_handler)

    def test_rank_uses_shared_state_only_after_success_and_resets_on_clear(self) -> None:
        script = self.read("backend/app/static/guide_image_preview.js")
        rank_editor = script.split("function initRankImageEditor(editor)", 1)[1]

        self.assertIn("window.FedorinovPhotoPlusFlow", rank_editor)
        self.assertIn("plusFlow.shouldOpenFilePicker(trigger)", rank_editor)
        self.assertIn("plusFlow.markClipboardSuccess(trigger)", rank_editor)
        self.assertIn("plusFlow.reset(trigger)", rank_editor)
        self.assertNotIn("clipboardAttempted", rank_editor)
        self.assertLess(
            rank_editor.index("assignClipboardImage(clipboardImage)"),
            rank_editor.index("plusFlow.markClipboardSuccess(trigger)"),
        )
        cancel_handler = rank_editor.split('input.addEventListener("cancel"', 1)[1].split("});", 1)[0]
        self.assertNotIn("plusFlow.reset", cancel_handler)

    def test_helper_loads_before_clipboard_and_rank_integrations(self) -> None:
        for template_path in ("backend/app/templates/base.html", "backend/app/templates/legacy_base.html"):
            template = self.read(template_path)
            self.assertLess(template.index("photo_plus_flow.js"), template.index("clipboard_paste.js"))
        base = self.read("backend/app/templates/base.html")
        self.assertLess(base.index("photo_plus_flow.js"), base.index("guide_image_preview.js"))


if __name__ == "__main__":
    unittest.main()
