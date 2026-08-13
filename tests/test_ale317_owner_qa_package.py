from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import unittest
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.routers import legacy as legacy_router


ROOT = Path(__file__).resolve().parents[1]


class _Request:
    headers = {"x-requested-with": "XMLHttpRequest"}


class Ale317OwnerQaPackageTests(unittest.TestCase):
    def test_ajax_person_card_skips_full_legacy_list_queries(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "database" / "MyDatabase.sqlite"
            db_path.parent.mkdir(parents=True)
            db_path.touch()
            settings = Settings(
                rewards_data_dir=root,
                rewards_db_path=db_path,
                read_only=False,
                write_mode=True,
            )
            person = {"id": 77, "fio": "AJAX Person", "birthday": "1945", "id_rank": 1}
            captured: dict[str, object] = {}

            def template_response(_request, name, context):
                captured.update(context)
                return {"name": name, "context": context}

            with (
                patch.object(legacy_router, "get_settings", return_value=settings),
                patch.object(legacy_router, "get_person", return_value=person),
                patch.object(legacy_router, "list_person_rewards", return_value=[]),
                patch.object(legacy_router, "person_folder_image_items", return_value=[]),
                patch.object(legacy_router.templates, "TemplateResponse", side_effect=template_response),
                patch.object(legacy_router, "list_legacy_reward_person_group") as full_list,
                patch.object(legacy_router, "legacy_rewards_filter_options") as filter_options,
                patch.object(legacy_router, "legacy_rewards_filter_cascade") as filter_cascade,
                patch.object(legacy_router, "legacy_rewards_totals") as totals,
                patch.object(legacy_router, "list_marks") as marks,
            ):
                result = legacy_router.legacy_index(_Request(), tab="rewards", person_id=77)

            self.assertEqual(result["name"], "legacy.html")
            self.assertEqual(captured["selected_person"]["id"], 77)
            self.assertEqual(captured["persons"], [])
            full_list.assert_not_called()
            filter_options.assert_not_called()
            filter_cascade.assert_not_called()
            totals.assert_not_called()
            marks.assert_not_called()

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_reward_edit_duplicate_check_waits_for_actual_number_change(self) -> None:
        script_path = ROOT / "backend/app/static/reward_duplicate_check.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
const status = {
  hidden: true,
  className: "",
  classList: { add() {} },
  replaceChildren() {},
  appendChild() {},
};
const nameSelect = { value: "2", addEventListener(type, callback) { listeners[`name:${type}`] = callback; } };
const numberInput = {
  value: "100",
  addEventListener(type, callback) { listeners[`number:${type}`] = callback; },
  setCustomValidity() {},
  setAttribute() {},
};
const form = {
  dataset: { currentRewardId: "10" },
  querySelector(selector) {
    if (selector === "[data-guide-role='name']") return nameSelect;
    if (selector === "[data-reward-number]") return numberInput;
    if (selector === "[data-reward-duplicate-status]") return status;
    return null;
  },
};
let ready = null;
let requests = [];
const nativeSetTimeout = global.setTimeout;
const nativeClearTimeout = global.clearTimeout;
global.window = global;
window.location = { origin: "http://127.0.0.1" };
window.setTimeout = (callback) => nativeSetTimeout(callback, 2);
window.clearTimeout = nativeClearTimeout;
global.document = {
  addEventListener(type, callback) { if (type === "DOMContentLoaded") ready = callback; },
  querySelectorAll() { return [form]; },
  createTextNode(value) { return { value }; },
  createElement() { return {}; },
};
global.fetch = async (url) => {
  requests.push(String(url));
  return { ok: true, async json() { return { duplicate: false, message: "Номер свободен" }; } };
};
eval(source);

(async () => {
  ready();
  const initial = requests.length;
  listeners["name:change"]();
  await new Promise((resolve) => nativeSetTimeout(resolve, 8));
  const afterNameOnly = requests.length;
  numberInput.value = "100";
  listeners["number:input"]();
  await new Promise((resolve) => nativeSetTimeout(resolve, 8));
  const afterSame = requests.length;
  numberInput.value = "101";
  listeners["number:input"]();
  await new Promise((resolve) => nativeSetTimeout(resolve, 8));
  const afterChange = requests.length;
  numberInput.value = "100";
  listeners["number:input"]();
  await new Promise((resolve) => nativeSetTimeout(resolve, 8));
  process.stdout.write(JSON.stringify({
    initial,
    afterNameOnly,
    afterSame,
    afterChange,
    afterRestore: requests.length,
    statusHidden: status.hidden,
  }));
})().catch((error) => { console.error(error); process.exit(1); });
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "reward_duplicate_runner.js"
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
                "initial": 0,
                "afterNameOnly": 0,
                "afterSame": 0,
                "afterChange": 1,
                "afterRestore": 1,
                "statusHidden": True,
            },
        )

    def test_person_form_requires_year_and_disables_autocomplete(self) -> None:
        template = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")
        validation = (ROOT / "backend/app/static/person_form_validation.js").read_text(encoding="utf-8")

        self.assertIn('autocomplete="off" data-managed-validation data-person-form', template)
        self.assertIn('name="birthday"', template)
        self.assertIn("required autocomplete=\"off\"", template)
        self.assertIn('data-original-year="{{ person.birthday|format_birth_year_input }}"', template)
        self.assertIn("unchangedLegacyYear", validation)
        self.assertIn("Укажите год рождения.", validation)
        self.assertIn('input.addEventListener("invalid", validate)', validation)

    def test_static_cache_key_covers_new_scripts(self) -> None:
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        templates = (ROOT / "backend/app/routers/templates.py").read_text(encoding="utf-8")

        self.assertIn("person_form_validation.js", base)
        self.assertIn("form_behavior.js", base)
        self.assertIn('STATIC_ASSET_VERSION = "20260813-ale383-corrective-1"', templates)


if __name__ == "__main__":
    unittest.main()
