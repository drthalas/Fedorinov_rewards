(function () {
  "use strict";

  const AUTOCOMPLETE_SELECTOR = [
    "input:not([type='hidden']):not([type='file']):not([type='checkbox']):not([type='radio'])",
    "textarea",
    "select",
  ].join(",");
  let errorCounter = 0;

  function describedError(form, control) {
    const describedBy = String(control.getAttribute("aria-describedby") || "").trim();
    for (const id of describedBy.split(/\s+/).filter(Boolean)) {
      const element = document.getElementById(id);
      if (element && form.contains(element) && element.classList.contains("field-error")) {
        return element;
      }
    }
    return null;
  }

  function visibleControl(control) {
    const styled = control.nextElementSibling;
    if (styled && styled.classList.contains("styled-select")) {
      return styled.querySelector(".styled-select-button") || styled;
    }
    return control;
  }

  function fieldError(form, control) {
    let error = describedError(form, control);
    if (error) {
      return error;
    }
    const existingId = control.dataset.managedErrorId;
    if (existingId) {
      error = document.getElementById(existingId);
      if (error) {
        return error;
      }
    }
    error = document.createElement("p");
    error.id = `managed-field-error-${++errorCounter}`;
    error.className = "field-error";
    error.dataset.fieldErrorFor = control.name || "field";
    error.hidden = true;
    const anchor = control.nextElementSibling && control.nextElementSibling.classList.contains("styled-select")
      ? control.nextElementSibling
      : control;
    anchor.insertAdjacentElement("afterend", error);
    control.dataset.managedErrorId = error.id;
    const describedBy = String(control.getAttribute("aria-describedby") || "").trim();
    control.setAttribute("aria-describedby", [describedBy, error.id].filter(Boolean).join(" "));
    return error;
  }

  function summaryFor(form) {
    let summary = form.querySelector("[data-managed-form-summary]");
    if (summary) {
      return summary;
    }
    summary = document.createElement("p");
    summary.className = "notice notice-error managed-form-summary";
    summary.dataset.managedFormSummary = "true";
    summary.setAttribute("role", "alert");
    summary.textContent = "Заполните обязательные поля";
    summary.hidden = true;
    form.prepend(summary);
    return summary;
  }

  function requiredMissing(control) {
    if (!control.required || control.disabled) {
      return false;
    }
    if (control.type === "checkbox") {
      return !control.checked;
    }
    if (control.type === "radio") {
      const form = control.form;
      const group = form ? Array.from(form.elements).filter((item) => item.type === "radio" && item.name === control.name) : [control];
      return !group.some((item) => item.checked);
    }
    return !String(control.value || "").trim();
  }

  function validationMessage(control) {
    if (requiredMissing(control)) {
      return "Обязательное поле.";
    }
    if (control.validity && !control.validity.valid) {
      if (control.validity.customError && control.validationMessage) {
        return control.validationMessage;
      }
      return control.dataset.validationMessage || "Проверьте значение.";
    }
    return "";
  }

  function renderFieldState(form, control, message) {
    const target = visibleControl(control);
    const error = fieldError(form, control);
    control.setAttribute("aria-invalid", message ? "true" : "false");
    target.setAttribute("aria-invalid", message ? "true" : "false");
    target.classList.toggle("form-field-invalid", Boolean(message));
    error.textContent = message;
    error.hidden = !message;
  }

  function requiredControls(form) {
    return Array.from(form.querySelectorAll("input[required], select[required], textarea[required]"));
  }

  function validationControls(form) {
    return Array.from(form.elements).filter((control) => control.willValidate && !control.disabled);
  }

  function validateForm(form, options) {
    const settings = options || {};
    form.dispatchEvent(new CustomEvent("managed-form:validate"));
    const invalid = [];
    let hasMissingRequired = false;
    validationControls(form).forEach((control) => {
      const message = validationMessage(control);
      if (message || control.getAttribute("aria-invalid") === "true") {
        renderFieldState(form, control, message);
      }
      if (message) {
        hasMissingRequired = hasMissingRequired || requiredMissing(control);
        invalid.push(control);
      }
    });
    const summary = summaryFor(form);
    summary.textContent = hasMissingRequired ? "Заполните обязательные поля" : "Проверьте введённые данные.";
    summary.hidden = invalid.length === 0;
    if (invalid.length && settings.focus !== false) {
      visibleControl(invalid[0]).focus({ preventScroll: true });
      visibleControl(invalid[0]).scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    return invalid.length === 0;
  }

  function clearCorrectedField(form, control) {
    if (requiredMissing(control) || (control.validity && !control.validity.valid)) {
      return;
    }
    renderFieldState(form, control, "");
    if (!validationControls(form).some((item) => item.getAttribute("aria-invalid") === "true")) {
      summaryFor(form).hidden = true;
    }
  }

  function initManagedForm(form) {
    if (form.dataset.managedValidationReady === "true") {
      return;
    }
    form.dataset.managedValidationReady = "true";
    form.noValidate = true;
    summaryFor(form);
    validationControls(form).forEach((control) => {
      fieldError(form, control);
      control.addEventListener("input", () => clearCorrectedField(form, control));
      control.addEventListener("change", () => clearCorrectedField(form, control));
    });
    form.addEventListener("invalid", (event) => event.preventDefault(), true);
    form.addEventListener("submit", (event) => {
      if (!validateForm(form)) {
        event.preventDefault();
      }
    });
  }

  function applyAutocompletePolicy(root) {
    const scope = root || document;
    scope.querySelectorAll("form").forEach((form) => form.setAttribute("autocomplete", "off"));
    scope.querySelectorAll(AUTOCOMPLETE_SELECTOR).forEach((control) => control.setAttribute("autocomplete", "off"));
  }

  function initAll(root) {
    const scope = root || document;
    applyAutocompletePolicy(scope);
    scope.querySelectorAll("form[data-managed-validation]").forEach(initManagedForm);
  }

  window.FedorinovFormBehavior = { initAll, validateForm };
  document.addEventListener("DOMContentLoaded", () => initAll(document));
  document.addEventListener("legacy:content-updated", (event) => {
    initAll(event && event.detail && event.detail.root ? event.detail.root : document);
  });
})();
