from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import unittest

from backend.app.repositories.rewards_write import reward_data_from_mapping


ROOT = Path(__file__).resolve().parents[1]


class RewardReferenceCascadeTests(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_template_exposes_reference_filters_and_keeps_link_readonly(self) -> None:
        template = self.read("backend/app/templates/reward_form.html")

        self.assertIn('name="reference_country_id"', template)
        self.assertIn('name="reference_category_id"', template)
        self.assertIn('name="reference_subcategory_id"', template)
        self.assertIn('name="id_name"', template)
        self.assertIn("data-reward-reference-link", template)
        self.assertNotIn('name="id_link"', template)
        self.assertIn('readonly aria-readonly="true"', template)

    def test_filter_values_cannot_override_canonical_reward_lineage(self) -> None:
        data = reward_data_from_mapping(
            {
                "reference_country_id": "999",
                "reference_category_id": "998",
                "reference_subcategory_id": "997",
                "id_name": "42",
                "id_link": "https://forged.invalid/",
                "number": "7",
            }
        )

        self.assertEqual(data.id_name, 42)
        self.assertIsNone(data.id_gos)
        self.assertIsNone(data.id_catigory)
        self.assertIsNone(data.id_sub_catigory)
        self.assertIsNone(data.id_link)

    def test_cascade_filters_names_and_derives_reference_link(self) -> None:
        script_path = ROOT / "backend/app/static/reward_reference_fields.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
let ready;
class FakeOption {
  constructor(text, value) { this.textContent = text; this.value = String(value); this.selected = false; }
}
class FakeSelect {
  constructor(value = "") { this.value = String(value); this.options = []; this.dataset = {}; this.listeners = {}; }
  addEventListener(type, callback) { this.listeners[type] = callback; }
  replaceChildren(...children) { this.options = children; this.value = ""; }
  appendChild(option) { this.options.push(option); if (option.selected) this.value = option.value; }
  change(value) { this.value = String(value); this.listeners.change(); }
}
global.Option = FakeOption;
const country = new FakeSelect();
const category = new FakeSelect();
const subcategory = new FakeSelect();
const name = new FakeSelect();
const link = { value: "" };
const references = [
  { id_gos: 1, gos: "СССР", id_catigory: 10, category: "Боевые", id_sub_catigory: 100, subcategory: "Ордена", id_name: 1000, name: "Орден Кутузова I степени", id_link: "https://reference.example/kutuzov" },
  { id_gos: 1, gos: "СССР", id_catigory: 10, category: "Боевые", id_sub_catigory: 101, subcategory: "Медали", id_name: 1001, name: "Медаль За отвагу", id_link: "" },
  { id_gos: 2, gos: "Россия", id_catigory: 20, category: "Государственные", id_sub_catigory: 200, subcategory: "Ордена", id_name: 2000, name: "Орден Мужества", id_link: "https://reference.example/courage" },
];
const jsonNode = { textContent: JSON.stringify(references) };
const form = {
  dataset: {},
  querySelector(selector) {
    return {
      "script[data-reward-reference-options]": jsonNode,
      "[data-guide-role='name']": name,
      "[data-reward-reference-filter='country']": country,
      "[data-reward-reference-filter='category']": category,
      "[data-reward-reference-filter='subcategory']": subcategory,
      "[data-reward-reference-link]": link,
    }[selector] || null;
  },
};
const documentRoot = {
  matches() { return false; },
  querySelectorAll(selector) { return selector === "[data-reward-reference-derived]" ? [form] : []; },
  addEventListener(type, callback) { if (type === "DOMContentLoaded") ready = callback; },
};
global.document = documentRoot;
eval(source);
ready();
country.change("1");
category.change("10");
subcategory.change("100");
const filteredNames = name.options.filter((option) => option.value).map((option) => option.textContent);
name.change("1000");
process.stdout.write(JSON.stringify({
  countries: country.options.filter((option) => option.value).map((option) => option.textContent),
  categories: category.options.filter((option) => option.value).map((option) => option.textContent),
  subcategories: subcategory.options.filter((option) => option.value).map((option) => option.textContent),
  filteredNames,
  link: link.value,
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "reward_reference_cascade_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )

        result = json.loads(completed.stdout)
        self.assertEqual(result["countries"], ["Россия", "СССР"])
        self.assertEqual(result["categories"], ["Боевые"])
        self.assertEqual(result["subcategories"], ["Медали", "Ордена"])
        self.assertEqual(result["filteredNames"], ["Орден Кутузова I степени"])
        self.assertEqual(result["link"], "https://reference.example/kutuzov")


if __name__ == "__main__":
    unittest.main()
