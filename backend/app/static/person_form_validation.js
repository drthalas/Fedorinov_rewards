(function () {
  "use strict";

  const REQUIRED_MESSAGE = "Укажите год рождения.";
  const FORMAT_MESSAGE = "Укажите год рождения в формате ГГГГ.";

  function initForm(form) {
    if (!form || form.dataset.personFormInitialized === "true") {
      return;
    }
    const input = form.querySelector("[data-birth-year]");
    const error = form.querySelector("[data-birth-year-error]");
    if (!input || !error) {
      return;
    }
    form.dataset.personFormInitialized = "true";

    const validate = () => {
      const value = String(input.value || "").trim();
      const minimum = Number(input.dataset.minYear || 1800);
      const maximum = Number(input.dataset.maxYear || 1999);
      const original = String(input.dataset.originalYear || "").trim();
      const unchangedLegacyYear = value === original
        && /^\d{4}$/.test(value)
        && (Number(value) < minimum || Number(value) > maximum);
      let message = "";
      if (!value) {
        message = REQUIRED_MESSAGE;
      } else if (!/^\d{4}$/.test(value)) {
        message = FORMAT_MESSAGE;
      } else if (!unchangedLegacyYear && (Number(value) < minimum || Number(value) > maximum)) {
        message = `Год рождения должен быть от ${minimum} до ${maximum}.`;
      }
      input.setCustomValidity(message);
      input.setAttribute("aria-invalid", message ? "true" : "false");
      error.textContent = message;
      error.hidden = !message;
      return !message;
    };

    input.addEventListener("input", validate);
    input.addEventListener("blur", validate);
    input.addEventListener("invalid", validate);
    form.addEventListener("managed-form:validate", validate);
    form.addEventListener("submit", (event) => {
      if (!validate()) {
        event.preventDefault();
        input.focus();
      }
    });
  }

  function initAll(root) {
    (root || document).querySelectorAll("[data-person-form]").forEach(initForm);
  }

  document.addEventListener("DOMContentLoaded", () => initAll(document));
  document.addEventListener("legacy:content-updated", (event) => {
    initAll(event && event.detail && event.detail.root ? event.detail.root : document);
  });
})();
