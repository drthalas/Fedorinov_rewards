(function () {
  "use strict";

  function parseReferences(form) {
    const script = form.querySelector("script[data-reward-reference-options]");
    if (!script) {
      return [];
    }
    try {
      const references = JSON.parse(script.textContent || "[]");
      return Array.isArray(references) ? references : [];
    } catch (_error) {
      return [];
    }
  }

  function initRewardReferenceFields(form) {
    if (!form || form.dataset.rewardReferenceReady === "true") {
      return;
    }
    const nameSelect = form.querySelector("[data-guide-role='name']");
    if (!nameSelect) {
      return;
    }
    form.dataset.rewardReferenceReady = "true";
    const references = new Map(
      parseReferences(form).map((reference) => [String(reference.id_name), reference])
    );

    function updateDerivedFields() {
      const reference = references.get(String(nameSelect.value || "")) || {};
      form.querySelectorAll("[data-reward-reference-field]").forEach((field) => {
        const key = field.dataset.rewardReferenceField;
        field.value = reference[key] == null ? "" : String(reference[key]);
      });
    }

    nameSelect.addEventListener("change", updateDerivedFields);
    updateDerivedFields();
  }

  function initAll(scope) {
    if (scope.matches && scope.matches("[data-reward-reference-derived]")) {
      initRewardReferenceFields(scope);
    }
    scope.querySelectorAll("[data-reward-reference-derived]").forEach(initRewardReferenceFields);
  }

  document.addEventListener("DOMContentLoaded", () => initAll(document));
  document.addEventListener("legacy:content-updated", (event) => initAll(event.target || document));
})();
