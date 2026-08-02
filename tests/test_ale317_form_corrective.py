from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import subprocess
import unittest
from urllib.parse import parse_qs, urlsplit

from backend.app.routers import persons as persons_router


ROOT = Path(__file__).resolve().parents[1]


class Ale317FormCorrectiveTests(unittest.TestCase):
    def test_created_person_selection_is_added_only_to_legacy_rewards_return(self) -> None:
        target = persons_router._person_created_edit_url(
            42,
            "/legacy?tab=rewards&rank_id=7&person_id=3",
            person_rank_id=7,
        )
        query = parse_qs(urlsplit(target).query)
        self.assertEqual(query["created"], ["1"])
        self.assertEqual(
            query["return_to"],
            ["/legacy?tab=rewards&rank_id=7&person_id=42"],
        )

        standalone = persons_router._person_created_edit_url(42, "/persons?page=2")
        self.assertEqual(parse_qs(urlsplit(standalone).query)["return_to"], ["/persons?page=2"])
        unsafe = persons_router._person_created_edit_url(42, "https://example.test/legacy?tab=rewards")
        self.assertNotIn("return_to", parse_qs(urlsplit(unsafe).query))

    def test_created_person_return_removes_only_filters_that_hide_the_new_row(self) -> None:
        reward_filtered = persons_router._person_created_edit_url(
            42,
            "/legacy?tab=rewards&rank_id=7&country_id=3&category_id=9&person_id=3",
            person_rank_id=7,
        )
        reward_return = parse_qs(urlsplit(reward_filtered).query)["return_to"][0]
        reward_query = parse_qs(urlsplit(reward_return).query)
        self.assertEqual(reward_query["person_id"], ["42"])
        self.assertEqual(reward_query["rank_id"], ["7"])
        self.assertNotIn("country_id", reward_query)
        self.assertNotIn("category_id", reward_query)

        rank_filtered = persons_router._person_created_edit_url(
            42,
            "/legacy?tab=rewards&rank_id=8",
            person_rank_id=7,
        )
        rank_return = parse_qs(urlsplit(rank_filtered).query)["return_to"][0]
        rank_query = parse_qs(urlsplit(rank_return).query)
        self.assertEqual(rank_query, {"tab": ["rewards"], "person_id": ["42"]})

    def test_birth_year_contract_is_exactly_1800_through_1999(self) -> None:
        template = (ROOT / "backend/app/templates/person_form.html").read_text(encoding="utf-8")
        validation = (ROOT / "backend/app/static/person_form_validation.js").read_text(encoding="utf-8")

        self.assertIn('pattern="(18|19)[0-9]{2}"', template)
        self.assertIn('data-min-year="{{ birth_year_min }}"', template)
        self.assertIn('data-max-year="{{ birth_year_max }}"', template)
        self.assertIn("Number(value) < minimum || Number(value) > maximum", validation)
        self.assertIn("Год рождения должен быть от ${minimum} до ${maximum}.", validation)

    def test_all_edit_forms_use_shared_validation_and_global_autocomplete_policy(self) -> None:
        templates = [
            "person_form.html",
            "reward_form.html",
            "mark_form.html",
            "guide_level_form.html",
            "rank_form.html",
        ]
        for filename in templates:
            with self.subTest(filename=filename):
                source = (ROOT / "backend/app/templates" / filename).read_text(encoding="utf-8")
                self.assertIn("data-managed-validation", source)
                self.assertIn('autocomplete="off"', source)

        policy = (ROOT / "backend/app/static/form_behavior.js").read_text(encoding="utf-8")
        base = (ROOT / "backend/app/templates/base.html").read_text(encoding="utf-8")
        legacy_base = (ROOT / "backend/app/templates/legacy_base.html").read_text(encoding="utf-8")
        self.assertIn('scope.querySelectorAll("form")', policy)
        self.assertIn("AUTOCOMPLETE_SELECTOR", policy)
        self.assertIn("Заполните обязательные поля", policy)
        self.assertIn("form.noValidate = true", policy)
        self.assertIn("form_behavior.js", base)
        self.assertIn("form_behavior.js", legacy_base)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_managed_required_error_targets_custom_select_and_clears(self) -> None:
        script_path = ROOT / "backend/app/static/form_behavior.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const elements = new Map();
const listeners = {};
let focused = "";

function classes(values) {
  const state = new Set(values || []);
  return {
    contains(value) { return state.has(value); },
    toggle(value, enabled) { enabled ? state.add(value) : state.delete(value); },
  };
}

const button = {
  classList: classes(["styled-select-button"]),
  attrs: {},
  setAttribute(name, value) { this.attrs[name] = value; },
  focus() { focused = "styled-select-button"; },
  scrollIntoView() {},
};
const wrapper = {
  classList: classes(["styled-select"]),
  querySelector() { return button; },
  insertAdjacentElement(_where, element) { elements.set(element.id, element); },
};
const control = {
  name: "id_name",
  type: "select-one",
  required: true,
  disabled: false,
  willValidate: true,
  value: "",
  validity: { valid: false, valueMissing: true, customError: false },
  validationMessage: "",
  dataset: {},
  attrs: {},
  nextElementSibling: wrapper,
  addEventListener(type, callback) { listeners[type] = callback; },
  getAttribute(name) { return this.attrs[name] || ""; },
  setAttribute(name, value) { this.attrs[name] = value; },
};
const form = {
  dataset: {},
  elements: [control],
  summary: null,
  attrs: {},
  noValidate: false,
  querySelector(selector) { return selector === "[data-managed-form-summary]" ? this.summary : null; },
  querySelectorAll(selector) {
    if (selector === "input[required], select[required], textarea[required]") return [control];
    return [];
  },
  setAttribute(name, value) { this.attrs[name] = value; },
  addEventListener(type, callback) { listeners[`form:${type}`] = callback; },
  dispatchEvent() {},
  contains(element) { return elements.has(element.id); },
  prepend(element) { this.summary = element; elements.set(element.id || "summary", element); },
};

function createdElement() {
  return {
    id: "",
    className: "",
    dataset: {},
    attrs: {},
    hidden: false,
    textContent: "",
    classList: classes([]),
    setAttribute(name, value) { this.attrs[name] = value; },
  };
}

let ready = null;
global.window = global;
global.CustomEvent = class { constructor(type) { this.type = type; } };
global.document = {
  addEventListener(type, callback) { if (type === "DOMContentLoaded") ready = callback; },
  querySelectorAll(selector) {
    if (selector === "form" || selector === "form[data-managed-validation]") return [form];
    if (selector.includes("input:not")) return [control];
    return [];
  },
  createElement: createdElement,
  getElementById(id) { return elements.get(id) || null; },
};
eval(source);
ready();
let prevented = false;
listeners["form:submit"]({ preventDefault() { prevented = true; } });
const afterSubmit = {
  prevented,
  noValidate: form.noValidate,
  formAutocomplete: form.attrs.autocomplete,
  controlAutocomplete: control.attrs.autocomplete,
  summary: form.summary.textContent,
  summaryHidden: form.summary.hidden,
  errorHidden: elements.get(control.dataset.managedErrorId).hidden,
  buttonInvalid: button.attrs["aria-invalid"],
  focused,
};
control.value = "4";
control.validity = { valid: true, valueMissing: false, customError: false };
listeners.change();
process.stdout.write(JSON.stringify({
  afterSubmit,
  afterCorrection: {
    summaryHidden: form.summary.hidden,
    errorHidden: elements.get(control.dataset.managedErrorId).hidden,
    buttonInvalid: button.attrs["aria-invalid"],
  },
}));
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "form_behavior_runner.js"
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
                "afterSubmit": {
                    "prevented": True,
                    "noValidate": True,
                    "formAutocomplete": "off",
                    "controlAutocomplete": "off",
                    "summary": "Заполните обязательные поля",
                    "summaryHidden": False,
                    "errorHidden": False,
                    "buttonInvalid": "true",
                    "focused": "styled-select-button",
                },
                "afterCorrection": {
                    "summaryHidden": True,
                    "errorHidden": True,
                    "buttonInvalid": "false",
                },
            },
        )

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_reward_create_number_validation_is_order_independent(self) -> None:
        script_path = ROOT / "backend/app/static/reward_duplicate_check.js"
        runner = r'''
const fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
let message = "";
let validity = "";
const status = {
  hidden: true,
  className: "",
  classList: { add() {} },
  replaceChildren(node) { message = node.value; },
  appendChild() {},
};
const nameSelect = { value: "", addEventListener(type, callback) { listeners[`name:${type}`] = callback; } };
const numberInput = {
  value: "",
  addEventListener(type, callback) { listeners[`number:${type}`] = callback; },
  setCustomValidity(value) { validity = value; },
  setAttribute() {},
};
const form = {
  dataset: { currentRewardId: "" },
  querySelector(selector) {
    if (selector === "[data-guide-role='name']") return nameSelect;
    if (selector === "[data-reward-number]") return numberInput;
    if (selector === "[data-reward-duplicate-status]") return status;
    return null;
  },
};
let ready = null;
const nativeSetTimeout = global.setTimeout;
global.window = global;
window.location = { origin: "http://127.0.0.1" };
window.setTimeout = (callback) => nativeSetTimeout(callback, 2);
window.clearTimeout = global.clearTimeout;
global.document = {
  addEventListener(type, callback) { if (type === "DOMContentLoaded") ready = callback; },
  querySelectorAll() { return [form]; },
  createTextNode(value) { return { value }; },
  createElement() { return {}; },
};
const requests = [];
global.fetch = async (url) => {
  requests.push(String(url));
  return { ok: true, async json() { return { duplicate: false, message: "Номер свободен" }; } };
};
eval(source);

(async () => {
  ready();
  numberInput.value = "AB12";
  listeners["number:input"]();
  const invalid = { message, validity, requests: requests.length };
  numberInput.value = "120";
  listeners["number:input"]();
  const numberFirst = { message, validity, requests: requests.length };
  nameSelect.value = "4";
  listeners["name:change"]();
  await new Promise((resolve) => nativeSetTimeout(resolve, 8));
  const afterName = { message, validity, requests: requests.length, url: requests[0] };
  numberInput.value = "121";
  listeners["number:input"]();
  await new Promise((resolve) => nativeSetTimeout(resolve, 8));
  process.stdout.write(JSON.stringify({ invalid, numberFirst, afterName, classificationFirstRequests: requests.length }));
})().catch((error) => { console.error(error); process.exit(1); });
'''
        with TemporaryDirectory() as tmp:
            runner_path = Path(tmp) / "reward_create_order_runner.js"
            runner_path.write_text(runner, encoding="utf-8")
            completed = subprocess.run(
                ["node", str(runner_path), str(script_path)],
                check=True,
                capture_output=True,
                text=True,
            )

        result = json.loads(completed.stdout)
        self.assertEqual(result["invalid"], {"message": "Укажите номер цифрами.", "validity": "Укажите номер цифрами.", "requests": 0})
        self.assertEqual(
            result["numberFirst"],
            {"message": "Для проверки занятости выберите наименование награды.", "validity": "", "requests": 0},
        )
        self.assertEqual(result["afterName"]["message"], "Номер свободен")
        self.assertEqual(result["afterName"]["requests"], 1)
        self.assertIn("id_name=4", result["afterName"]["url"])
        self.assertIn("number=120", result["afterName"]["url"])
        self.assertEqual(result["classificationFirstRequests"], 2)


if __name__ == "__main__":
    unittest.main()
