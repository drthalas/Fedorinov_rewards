from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CascadingGuidesJsTests(unittest.TestCase):
    def test_category_change_populates_subcategories_and_names(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not installed")

        script_path = ROOT / "backend" / "app" / "static" / "cascading_guides.js"
        runner = textwrap.dedent(
            f"""
            const fs = require("fs");
            const vm = require("vm");

            class FakeOption {{
              constructor(text, value) {{
                this.textContent = text;
                this.value = String(value);
                this.selected = false;
              }}
            }}

            class FakeSelect {{
              constructor(role) {{
                this.role = role;
                this.options = [new FakeOption("—", "")];
                this.listeners = {{}};
                this._value = "";
              }}
              appendChild(option) {{
                this.options.push(option);
                if (option.selected) {{
                  this._value = option.value;
                }}
              }}
              replaceChildren() {{
                this.options = [];
                this._value = "";
              }}
              addEventListener(name, callback) {{
                this.listeners[name] = callback;
              }}
              dispatch(name) {{
                this.listeners[name]();
              }}
              get value() {{
                return this._value;
              }}
              set value(nextValue) {{
                const value = String(nextValue || "");
                this._value = value;
                this.options.forEach((option) => {{
                  option.selected = option.value === value;
                }});
              }}
            }}

            const cascadeData = {{
              countries: [{{ id: 1, idl: -1, name: "СССР" }}],
              categories: [
                {{ id: 2, idl: 1, name: "Боевые" }},
                {{ id: 90, idl: 999, name: "Лишняя категория" }}
              ],
              subcategories: [
                {{ id: 3, idl: 2, name: "Ордена" }},
                {{ id: 91, idl: 999, name: "Лишняя подкатегория" }}
              ],
              names: [
                {{ id: 4, idl: 3, name: "Орден Красной Звезды" }},
                {{ id: 92, idl: 999, name: "Лишнее наименование" }}
              ]
            }};
            const roles = {{
              country: new FakeSelect("country"),
              category: new FakeSelect("category"),
              subcategory: new FakeSelect("subcategory"),
              name: new FakeSelect("name")
            }};
            const container = {{
              querySelector(selector) {{
                if (selector === "script[data-guide-cascade-options]") {{
                  return {{ textContent: JSON.stringify(cascadeData) }};
                }}
                const match = selector.match(/data-guide-role='([^']+)'/);
                return match ? roles[match[1]] : null;
              }}
            }};
            global.Option = FakeOption;
            global.document = {{
              addEventListener(_name, callback) {{
                callback();
              }},
              querySelectorAll(selector) {{
                return selector === ".guide-cascade" ? [container] : [];
              }}
            }};

            vm.runInThisContext(fs.readFileSync({json.dumps(str(script_path))}, "utf8"));
            roles.country.value = "1";
            roles.country.dispatch("change");
            roles.category.value = "2";
            roles.category.dispatch("change");
            roles.subcategory.value = "3";
            roles.subcategory.dispatch("change");
            const result = {{
              categories: roles.category.options.map((option) => option.value),
              subcategories: roles.subcategory.options.map((option) => option.value),
              names: roles.name.options.map((option) => option.value),
              selectedCategory: roles.category.value,
              selectedSubcategory: roles.subcategory.value
            }};
            process.stdout.write(JSON.stringify(result));
            """
        )
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "cascade_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(["node", str(runner_path)], check=True, capture_output=True, text=True)

        result = json.loads(completed.stdout)
        self.assertEqual(result["categories"], ["", "2"])
        self.assertEqual(result["subcategories"], ["", "3"])
        self.assertEqual(result["names"], ["", "4"])
        self.assertEqual(result["selectedCategory"], "2")
        self.assertEqual(result["selectedSubcategory"], "3")


if __name__ == "__main__":
    unittest.main()
