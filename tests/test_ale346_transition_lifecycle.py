from pathlib import Path
from tempfile import TemporaryDirectory
import asyncio
import json
import re
import shutil
import subprocess
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import patch

from backend.app.routers.persons import person_open_folder
from backend.app.services.person_files import PersonFilesError


ROOT = Path(__file__).resolve().parents[1]


class FakeRequest:
    def __init__(self, values: dict[str, object], *, ajax: bool = False):
        self._body = urlencode(values).encode("utf-8")
        self.headers = {"x-requested-with": "XMLHttpRequest"} if ajax else {}

    async def body(self) -> bytes:
        return self._body


class Ale346TransitionLifecycleTests(unittest.TestCase):
    def test_all_crud_forms_use_shared_feedback_or_specialized_non_navigation_flow(self) -> None:
        templates = ROOT / "backend/app/templates"
        exceptions = ("data-save-as-form", "data-update-form")
        uncovered: list[str] = []
        for path in sorted(templates.glob("*.html")):
            source = path.read_text(encoding="utf-8")
            for match in re.finditer(r"<form\b[^>]*\bmethod=[\"']post[\"'][^>]*>", source, re.IGNORECASE | re.DOTALL):
                opening_tag = match.group(0)
                if "data-write-feedback" in opening_tag or any(marker in opening_tag for marker in exceptions):
                    continue
                number = source.count("\n", 0, match.start()) + 1
                uncovered.append(f"{path.name}:{number}")
        self.assertEqual(uncovered, [])

    def test_shared_transition_assets_and_stable_workspace_overlay_are_enabled(self) -> None:
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")
        legacy = (ROOT / "backend/app/static/legacy_rewards.js").read_text(encoding="utf-8")
        styles = (ROOT / "backend/app/static/styles.css").read_text(encoding="utf-8")
        curtain = (ROOT / "backend/app/templates/_document_transition_curtain.html").read_text(encoding="utf-8")
        document_transition = (ROOT / "backend/app/static/document_transition.js").read_text(encoding="utf-8")

        self.assertIn("transition_lifecycle.js", base)
        self.assertIn("transition_lifecycle.js", legacy_base)
        self.assertIn('class="document-loading"', base)
        self.assertIn('class="document-loading"', legacy_base)
        self.assertIn("_document_transition_curtain.html", base)
        self.assertIn("_document_transition_curtain.html", legacy_base)
        self.assertIn("document_transition.js", base)
        self.assertIn("document_transition.js", legacy_base)
        self.assertIn("data-document-transition-curtain", curtain)
        self.assertIn("DOMContentLoaded", document_transition)
        self.assertIn("requestAnimationFrame", document_transition)
        self.assertNotIn("setTimeout", document_transition)
        self.assertIn("html:not(.document-loading) .document-transition-curtain", styles)
        self.assertIn("cavaliers-empty-state-awards-optimized.jpg", styles)
        self.assertNotIn("@view-transition", styles)
        self.assertNotIn("::view-transition-old(root)", styles)
        self.assertIn("legacy-workspace-state", styles)
        self.assertIn("target.append(state)", legacy)
        self.assertNotIn("target.replaceChildren(state)", legacy)
        self.assertIn('row.addEventListener("click", (event) => {\n        event.preventDefault();\n        showLoadingState();', legacy)
        self.assertIn("saveLegacyState", legacy)
        self.assertIn('window.addEventListener("pageshow", resetDeleteSubmissions)', (ROOT / "backend/app/static/confirm_submit.js").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_document_curtain_remains_until_dom_ready_and_next_frame(self) -> None:
        script_path = ROOT / "backend/app/static/document_transition.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const documentListeners = {};
const windowListeners = {};
const frames = [];
const events = [];

const root = {
  classList: {
    values: new Set(["document-loading"]),
    remove(value) { this.values.delete(value); },
    contains(value) { return this.values.has(value); },
  },
  dataset: {},
};

global.CustomEvent = class { constructor(type) { this.type = type; } };
global.document = {
  readyState: "loading",
  documentElement: root,
  addEventListener(type, callback) { documentListeners[type] = callback; },
  dispatchEvent(event) { events.push(event.type); },
};
global.window = global;
window.addEventListener = (type, callback) => { windowListeners[type] = callback; };
window.requestAnimationFrame = (callback) => { frames.push(callback); };

eval(source);
const beforeReady = root.classList.contains("document-loading");
documentListeners.DOMContentLoaded();
const afterDomReady = root.classList.contains("document-loading");
frames.shift()();
const afterFrame = root.classList.contains("document-loading");

process.stdout.write(JSON.stringify({
  beforeReady,
  afterDomReady,
  afterFrame,
  ready: root.dataset.documentReady,
  events,
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale346_document_transition_runner.js"
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
                "beforeReady": True,
                "afterDomReady": True,
                "afterFrame": False,
                "ready": "true",
                "events": ["document-transition:ready"],
            },
        )

    def test_open_folder_ajax_keeps_redirect_fallback_and_returns_entity_notice(self) -> None:
        settings = SimpleNamespace(rewards_db_path=Path("/tmp/ale346-test.sqlite"))
        with (
            patch("backend.app.routers.persons.get_settings", return_value=settings),
            patch("backend.app.routers.persons.get_person", return_value={"id": 7}),
            patch("backend.app.routers.persons.open_person_folder") as opener,
        ):
            ajax_response = asyncio.run(
                person_open_folder(FakeRequest({"return_to": "/legacy?tab=rewards&person_id=7"}, ajax=True), 7)
            )
            fallback_response = asyncio.run(
                person_open_folder(FakeRequest({"return_to": "/legacy?tab=rewards&person_id=7"}), 7)
            )

        self.assertEqual(ajax_response.status_code, 200)
        self.assertEqual(json.loads(ajax_response.body), {"ok": True, "message": "Каталог кавалера открыт."})
        self.assertEqual(fallback_response.status_code, 303)
        self.assertIn("status=folder_opened", fallback_response.headers["location"])
        self.assertEqual(opener.call_count, 2)

    def test_open_folder_ajax_error_is_finite_and_does_not_redirect(self) -> None:
        with (
            patch(
                "backend.app.routers.persons.get_settings",
                return_value=SimpleNamespace(rewards_db_path=Path("/tmp/ale346-test.sqlite")),
            ),
            patch("backend.app.routers.persons.get_person", return_value={"id": 7}),
            patch("backend.app.routers.persons.open_person_folder", side_effect=PersonFilesError("missing")),
        ):
            response = asyncio.run(person_open_folder(FakeRequest({}, ajax=True), 7))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.body), {"ok": False, "message": "Каталог кавалера не найден."})

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_transition_js_preserves_scroll_and_open_folder_has_no_navigation_or_duplicate(self) -> None:
        script_path = ROOT / "backend/app/static/transition_lifecycle.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const documentListeners = {};
const windowListeners = {};
const storage = {};
const feedbackCalls = [];
let fetchCount = 0;
let resolveFetch;

class Element {
  closest(selector) { return selector === "a[href]" ? this : null; }
  hasAttribute() { return false; }
}
class HTMLFormElement extends Element {}
global.Element = Element;
global.HTMLFormElement = HTMLFormElement;
global.FormData = class { constructor(form) { this.form = form; } };

const personList = { scrollTop: 245, dataset: {} };
const quickSearch = { value: "owner" };
const form = new HTMLFormElement();
form.action = "http://127.0.0.1:18192/persons/7/open-folder";
form.method = "post";
form.dataset = { writePendingLabel: "Открываем каталог…" };
form.matches = (selector) => selector === "[data-open-folder]";

global.window = global;
window.location = {
  href: "http://127.0.0.1:18192/legacy?tab=rewards&person_id=7&status=old",
  origin: "http://127.0.0.1:18192",
};
window.sessionStorage = {
  setItem(key, value) { storage[key] = value; },
  getItem(key) { return storage[key] || null; },
};
window.setTimeout = () => 1;
window.clearTimeout = () => {};
window.addEventListener = (type, callback) => { windowListeners[type] = callback; };
window.FedorinovWriteFeedback = {
  begin(target, submitter, message) { feedbackCalls.push(["begin", message]); return true; },
  finish(target, options) { feedbackCalls.push(["finish", options.state, options.message]); },
  showStatus(message, state) { feedbackCalls.push(["show", message, state]); },
};
window.fetch = () => {
  fetchCount += 1;
  return new Promise((resolve) => { resolveFetch = resolve; });
};
global.document = {
  documentElement: { dataset: {} },
  querySelector(selector) {
    if (selector === "[data-person-list]" || selector === ".legacy-sidebar .legacy-list") return personList;
    if (selector === "[data-person-quick-search]") return quickSearch;
    return null;
  },
  addEventListener(type, callback) {
    if (!documentListeners[type]) documentListeners[type] = [];
    documentListeners[type].push(callback);
  },
};

eval(source);
window.FedorinovTransitionLifecycle.saveLegacyState();
personList.scrollTop = 0;
quickSearch.value = "";
window.FedorinovTransitionLifecycle.restoreLegacyState(document);

const rewardsLink = new Element();
rewardsLink.href = "http://127.0.0.1:18192/legacy?tab=rewards";
rewardsLink.target = "";
rewardsLink.dataset = {};
window.location.href = "http://127.0.0.1:18192/legacy?tab=about";
documentListeners.click[0]({
  target: rewardsLink,
  defaultPrevented: false,
  button: 0,
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
});
window.location.href = "http://127.0.0.1:18192/legacy?tab=rewards&person_id=7&status=old";

function submitEvent() {
  return {
    target: form,
    submitter: null,
    defaultPrevented: false,
    stopped: false,
    preventDefault() { this.defaultPrevented = true; },
    stopImmediatePropagation() { this.stopped = true; },
  };
}

const first = submitEvent();
documentListeners.submit[0](first);
const duplicate = submitEvent();
documentListeners.submit[0](duplicate);
resolveFetch({ ok: true, json: async () => ({ ok: true, message: "Каталог кавалера открыт." }) });

setImmediate(() => {
  process.stdout.write(JSON.stringify({
    restoredScroll: personList.scrollTop,
    restoredSearch: quickSearch.value,
    scrollRestored: personList.dataset.scrollRestored,
    firstPrevented: first.defaultPrevented,
    duplicatePrevented: duplicate.defaultPrevented,
    duplicateStopped: duplicate.stopped,
    fetchCount,
    href: window.location.href,
    feedbackCalls,
    rewardsHref: rewardsLink.href,
  }));
});
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale346_transition_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )

        result = json.loads(completed.stdout)
        self.assertEqual(result["restoredScroll"], 245)
        self.assertEqual(result["restoredSearch"], "owner")
        self.assertEqual(result["scrollRestored"], "true")
        self.assertTrue(result["firstPrevented"])
        self.assertTrue(result["duplicatePrevented"])
        self.assertTrue(result["duplicateStopped"])
        self.assertEqual(result["fetchCount"], 1)
        self.assertEqual(result["href"], "http://127.0.0.1:18192/legacy?tab=rewards&person_id=7&status=old")
        self.assertEqual(result["rewardsHref"], "/legacy?tab=rewards&person_id=7")
        self.assertEqual(
            result["feedbackCalls"],
            [
                ["show", "Открываем…", "pending"],
                ["begin", "Открываем каталог…"],
                ["finish", "success", "Каталог кавалера открыт."],
            ],
        )

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_explicit_person_selection_wins_over_stored_state_on_pageshow(self) -> None:
        script_path = ROOT / "backend/app/static/transition_lifecycle.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const mode = process.argv[3];
const documentListeners = {};
const windowListeners = {};
const currentPersonId = mode === "created" ? "42" : mode === "existing" ? "7" : "";
const href = `http://127.0.0.1:18199/legacy?tab=rewards${currentPersonId ? `&person_id=${currentPersonId}` : ""}`;
const storageKey = "fedorinov:legacy-list-state:/legacy?tab=rewards";
const storage = {
  [storageKey]: JSON.stringify({
    personListScrollTop: 245,
    sidebarListScrollTop: 245,
    quickSearch: "old",
    selectedPersonId: "7",
  }),
};

class Element {}
class HTMLFormElement extends Element {}
global.Element = Element;
global.HTMLFormElement = HTMLFormElement;
global.FormData = class {};

const personList = { scrollTop: 900, dataset: {} };
const quickSearch = { value: "" };
const selectedRow = currentPersonId ? { dataset: { personName: mode === "created" ? "Новый кавалер" : "Old owner" } } : null;

global.window = global;
window.location = { href, origin: "http://127.0.0.1:18199" };
window.sessionStorage = {
  setItem(key, value) { storage[key] = value; },
  getItem(key) { return storage[key] || null; },
};
window.addEventListener = (type, callback) => {
  if (!windowListeners[type]) windowListeners[type] = [];
  windowListeners[type].push(callback);
};
global.document = {
  documentElement: { dataset: {} },
  querySelector(selector) {
    if (selector === "[data-person-list]" || selector === ".legacy-sidebar .legacy-list") return personList;
    if (selector === "[data-person-quick-search]") return quickSearch;
    if (selector === "[data-selected-person-row]") return selectedRow;
    return null;
  },
  addEventListener(type, callback) {
    if (!documentListeners[type]) documentListeners[type] = [];
    documentListeners[type].push(callback);
  },
};

eval(source);
documentListeners.DOMContentLoaded[0]();
const afterDom = {
  scrollTop: personList.scrollTop,
  quickSearch: quickSearch.value,
  scrollRestored: personList.dataset.scrollRestored || "",
  selectionPriority: personList.dataset.selectionPriority || "",
};
if (mode === "created") personList.scrollTop = 777;
windowListeners.pageshow[0]({ persisted: true });
const afterPageShow = {
  scrollTop: personList.scrollTop,
  quickSearch: quickSearch.value,
  scrollRestored: personList.dataset.scrollRestored || "",
  selectionPriority: personList.dataset.selectionPriority || "",
};
process.stdout.write(JSON.stringify({ afterDom, afterPageShow }));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale346_selection_priority_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            results = {}
            for mode in ("created", "existing", "deleted"):
                completed = subprocess.run(
                    ["node", str(runner_path), str(script_path), mode],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                results[mode] = json.loads(completed.stdout)

        self.assertEqual(
            results["created"],
            {
                "afterDom": {
                    "scrollTop": 900,
                    "quickSearch": "",
                    "scrollRestored": "",
                    "selectionPriority": "true",
                },
                "afterPageShow": {
                    "scrollTop": 777,
                    "quickSearch": "",
                    "scrollRestored": "",
                    "selectionPriority": "true",
                },
            },
        )
        for mode in ("existing", "deleted"):
            self.assertEqual(results[mode]["afterDom"]["scrollTop"], 245)
            self.assertEqual(results[mode]["afterDom"]["quickSearch"], "old")
            self.assertEqual(results[mode]["afterDom"]["scrollRestored"], "true")
            self.assertEqual(results[mode]["afterDom"]["selectionPriority"], "")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_selected_person_scrolls_only_after_render_and_commits_new_state(self) -> None:
        script_path = ROOT / "backend/app/static/legacy_rewards.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const documentListeners = {};
const windowListeners = {};
const frames = [];
let savedStates = 0;

const row = {
  hidden: false,
  isConnected: true,
  dataset: {
    personName: "Новый кавалер",
    selectUrl: "/legacy?tab=rewards&person_id=42",
    deselectUrl: "/legacy?tab=rewards",
    detailUrl: "/persons/42",
  },
  classList: { toggle() {}, contains() { return true; } },
  attrs: { "aria-selected": "true" },
  addEventListener() {},
  getAttribute(name) { return this.attrs[name] || ""; },
  setAttribute(name, value) { this.attrs[name] = value; },
  getBoundingClientRect() { return { top: 900, bottom: 930 }; },
};
const personList = {
  scrollTop: 0,
  dataset: { selectionPriority: "true" },
  clientHeight: 400,
  addEventListener() {},
  focus() {},
  getBoundingClientRect() { return { top: 100, bottom: 500 }; },
};

global.HTMLElement = class {};
global.CustomEvent = class { constructor(type, options) { this.type = type; this.detail = options && options.detail; } };
global.window = global;
window.location = { href: "http://127.0.0.1:18199/legacy?tab=rewards&person_id=42", origin: "http://127.0.0.1:18199", pathname: "/legacy", search: "?tab=rewards&person_id=42" };
window.requestAnimationFrame = (callback) => { frames.push(callback); };
window.addEventListener = (type, callback) => { windowListeners[type] = callback; };
window.FedorinovTransitionLifecycle = { saveLegacyState() { savedStates += 1; } };
global.document = {
  querySelector(selector) {
    if (selector === "[data-person-list]") return personList;
    if (selector === "[data-selected-person-row]") return row;
    if (selector === ".legacy-list-row.selected-row") return row;
    return null;
  },
  querySelectorAll(selector) { return selector === "[data-person-name]" ? [row] : []; },
  addEventListener(type, callback) { documentListeners[type] = callback; },
  dispatchEvent() {},
};

eval(source);
documentListeners.DOMContentLoaded();
const beforeFrame = {
  scrollTop: personList.scrollTop,
  selectionPriority: personList.dataset.selectionPriority,
  savedStates,
};
frames.shift()();
const afterFrame = {
  scrollTop: personList.scrollTop,
  selectionPriority: personList.dataset.selectionPriority || "",
  scrollRestored: personList.dataset.scrollRestored || "",
  savedStates,
};
process.stdout.write(JSON.stringify({ beforeFrame, afterFrame }));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "ale346_post_render_scroll_runner.js"
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
                "beforeFrame": {"scrollTop": 0, "selectionPriority": "true", "savedStates": 0},
                "afterFrame": {
                    "scrollTop": 438,
                    "selectionPriority": "",
                    "scrollRestored": "",
                    "savedStates": 1,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
