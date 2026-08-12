import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SummarySessionStateTests(unittest.TestCase):
    def test_templates_expose_session_state_contract(self) -> None:
        nav = (ROOT / "backend/app/templates/_user_nav.html").read_text(encoding="utf-8")
        legacy = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")
        self.assertIn("data-summary-nav", nav)
        self.assertIn("data-summary-filter-form", legacy)
        self.assertIn("data-summary-reset", legacy)
        self.assertIn("summary_session_state.js", base)
        self.assertIn("summary_session_state.js", legacy_base)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_applied_state_survives_navigation_and_reset_clears_it(self) -> None:
        script_path = ROOT / "backend/app/static/summary_session_state.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const storage = {};
const documentListeners = {};
const windowListeners = {};

function link() {
  return {
    href: "/legacy?tab=summary",
    dataset: {},
    listeners: {},
    addEventListener(type, callback) { this.listeners[type] = callback; },
  };
}
const firstNav = link();
const reset = link();

global.window = global;
window.location = {
  origin: "http://127.0.0.1:18080",
  href: "http://127.0.0.1:18080/legacy?tab=summary&summary_applied=1&country_id=7&include_marks=true&summary_mode=matrix",
};
window.sessionStorage = {
  getItem(key) { return storage[key] || null; },
  setItem(key, value) { storage[key] = value; },
  removeItem(key) { delete storage[key]; },
};
window.addEventListener = (type, callback) => { windowListeners[type] = callback; };
global.document = {
  addEventListener(type, callback) { documentListeners[type] = callback; },
  querySelectorAll(selector) {
    if (selector === "[data-summary-nav]") return [firstNav];
    if (selector === "[data-summary-reset]") return [reset];
    return [];
  },
};

eval(source);
documentListeners.DOMContentLoaded();
const saved = storage["fedorinov:summary-session-url"];
const restoredHref = firstNav.href;
window.location.href = "http://127.0.0.1:18080/legacy?tab=rewards";
windowListeners.pageshow();
const repeatedHref = firstNav.href;
reset.listeners.click();
windowListeners.pagehide();
process.stdout.write(JSON.stringify({ saved, restoredHref, repeatedHref, resetHref: firstNav.href, storage }));
'''
        with TemporaryDirectory() as temp_dir:
            runner_path = Path(temp_dir) / "summary_state_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        expected = "/legacy?tab=summary&summary_applied=1&country_id=7&include_marks=true&summary_mode=matrix"
        self.assertEqual(result["saved"], expected)
        self.assertTrue(result["restoredHref"].endswith(expected))
        self.assertTrue(result["repeatedHref"].endswith(expected))
        self.assertTrue(result["resetHref"].endswith("/legacy?tab=summary"))
        self.assertEqual(result["storage"], {})

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_unapplied_summary_does_not_replace_stored_result(self) -> None:
        source = (ROOT / "backend/app/static/summary_session_state.js").read_text(encoding="utf-8")
        self.assertIn('url.searchParams.get("summary_applied") !== "1"', source)
        self.assertNotIn("localStorage", source)


if __name__ == "__main__":
    unittest.main()
