import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from backend.app.repositories.summary import normalized_summary_filters
from backend.app.routers.legacy import SUMMARY_PAGE_SIZE, _summary_pagination_context


ROOT = Path(__file__).resolve().parents[1]


class SearchSessionAndSummaryPaginationTests(unittest.TestCase):
    def test_templates_scope_session_state_to_search_only(self) -> None:
        nav = (ROOT / "backend/app/templates/_user_nav.html").read_text(encoding="utf-8")
        legacy = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")

        self.assertIn("data-search-nav", nav)
        self.assertIn("data-search-reset", legacy)
        self.assertIn("search_session_state.js", base)
        self.assertIn("search_session_state.js", legacy_base)
        self.assertNotIn("data-summary-nav", nav)
        self.assertNotIn("data-summary-reset", legacy)
        self.assertNotIn("summary_session_state.js", base + legacy_base)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_search_results_page_survives_tab_navigation_and_reset_clears_it(self) -> None:
        script_path = ROOT / "backend/app/static/search_session_state.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const storage = {};
const documentListeners = {};
const windowListeners = {};

function link() {
  return {
    href: "/legacy?tab=search",
    dataset: {},
    listeners: {},
    addEventListener(type, callback) { this.listeners[type] = callback; },
  };
}
const searchNav = link();
const reset = link();

global.window = global;
window.location = {
  origin: "http://127.0.0.1:18080",
  href: "http://127.0.0.1:18080/legacy?tab=search&q=Кут&scope=rewards&mode=starts&page=3",
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
    if (selector === "[data-search-nav]") return [searchNav];
    if (selector === "[data-search-reset]") return [reset];
    return [];
  },
};

eval(source);
documentListeners.DOMContentLoaded();
const saved = storage["fedorinov:search-session-url"];
const restoredHref = searchNav.href;
window.location.href = "http://127.0.0.1:18080/legacy?tab=rewards";
windowListeners.pageshow();
const repeatedHref = searchNav.href;
reset.listeners.click();
windowListeners.pagehide();
process.stdout.write(JSON.stringify({ saved, restoredHref, repeatedHref, resetHref: searchNav.href, storage }));
'''
        with TemporaryDirectory() as temp_dir:
            runner_path = Path(temp_dir) / "search_state_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        result = json.loads(completed.stdout)
        expected = "/legacy?tab=search&q=%D0%9A%D1%83%D1%82&scope=rewards&mode=starts&page=3"
        self.assertEqual(result["saved"], expected)
        self.assertTrue(result["restoredHref"].endswith(expected))
        self.assertTrue(result["repeatedHref"].endswith(expected))
        self.assertTrue(result["resetHref"].endswith("/legacy?tab=search"))
        self.assertEqual(result["storage"], {})

    def test_summary_pagination_limits_rows_and_preserves_filter_and_sort(self) -> None:
        filters = normalized_summary_filters(country_id="7", include_marks="true")
        row_slice, pager = _summary_pagination_context(
            filters,
            "matrix",
            137,
            2,
            matrix_sort="birthday",
            matrix_dir="desc",
        )

        self.assertEqual(SUMMARY_PAGE_SIZE, 50)
        self.assertEqual((row_slice.start, row_slice.stop), (50, 100))
        self.assertEqual((pager["page"], pager["pages"]), (2, 3))
        self.assertEqual((pager["range_start"], pager["range_end"]), (51, 100))
        for key in ("first_url", "prev_url", "next_url", "last_url"):
            self.assertIn("country_id=7", pager[key])
            self.assertIn("include_marks=true", pager[key])
            self.assertIn("matrix_sort=birthday", pager[key])
            self.assertIn("matrix_dir=desc", pager[key])

    def test_summary_template_renders_only_paged_rows(self) -> None:
        router = (ROOT / "backend/app/routers/legacy.py").read_text(encoding="utf-8")
        template = (ROOT / "backend/app/templates/legacy.html").read_text(encoding="utf-8")

        self.assertIn('context["summary_matrix"] = {**matrix, "rows": visible_rows}', router)
        self.assertIn('context["summary_rows"] = rows[row_slice]', router)
        self.assertIn('if active_summary_mode == "matrix":', router)
        self.assertIn("summary_pagination_controls(summary_pagination)", template)
        self.assertIn("row.detail_url", template)


if __name__ == "__main__":
    unittest.main()
