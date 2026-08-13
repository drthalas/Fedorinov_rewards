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
    const countrySelect = form.querySelector("[data-reward-reference-filter='country']");
    const categorySelect = form.querySelector("[data-reward-reference-filter='category']");
    const subcategorySelect = form.querySelector("[data-reward-reference-filter='subcategory']");
    if (!nameSelect || !countrySelect || !categorySelect || !subcategorySelect) {
      return;
    }
    form.dataset.rewardReferenceReady = "true";
    const referenceRows = parseReferences(form);
    const references = new Map(referenceRows.map((reference) => [String(reference.id_name), reference]));
    const collator = new Intl.Collator("ru-RU", { sensitivity: "base" });

    function sortedUniqueRows(rows, idKey, nameKey) {
      const unique = new Map();
      rows.forEach((row) => {
        const id = String(row[idKey] == null ? "" : row[idKey]);
        if (id && !unique.has(id)) {
          unique.set(id, { id, name: String(row[nameKey] || "—") });
        }
      });
      return Array.from(unique.values()).sort((left, right) => collator.compare(left.name, right.name));
    }

    function rebuildSelect(select, rows, selectedValue) {
      select.replaceChildren(new Option("—", ""));
      rows.forEach((row) => {
        const option = new Option(row.name, row.id);
        option.selected = row.id === String(selectedValue || "");
        select.appendChild(option);
      });
    }

    function updateDerivedFields() {
      const reference = references.get(String(nameSelect.value || "")) || {};
      const link = form.querySelector("[data-reward-reference-link]");
      if (link) link.value = reference.id_link == null ? "" : String(reference.id_link);
    }

    function refreshCategories(selectedValue) {
      const rows = referenceRows.filter((row) => String(row.id_gos) === String(countrySelect.value || ""));
      rebuildSelect(categorySelect, sortedUniqueRows(rows, "id_catigory", "category"), selectedValue);
    }

    function refreshSubcategories(selectedValue) {
      const rows = referenceRows.filter((row) => String(row.id_catigory) === String(categorySelect.value || ""));
      rebuildSelect(subcategorySelect, sortedUniqueRows(rows, "id_sub_catigory", "subcategory"), selectedValue);
    }

    function refreshNames(selectedValue) {
      const rows = referenceRows.filter((row) => String(row.id_sub_catigory) === String(subcategorySelect.value || ""));
      rebuildSelect(nameSelect, sortedUniqueRows(rows, "id_name", "name"), selectedValue);
      updateDerivedFields();
    }

    countrySelect.addEventListener("change", () => {
      refreshCategories("");
      refreshSubcategories("");
      refreshNames("");
    });
    categorySelect.addEventListener("change", () => {
      refreshSubcategories("");
      refreshNames("");
    });
    subcategorySelect.addEventListener("change", () => refreshNames(""));
    nameSelect.addEventListener("change", updateDerivedFields);

    const selectedReference = references.get(String(nameSelect.value || "")) || {};
    const initialCountry = countrySelect.dataset.initialValue || selectedReference.id_gos || "";
    const initialCategory = categorySelect.dataset.initialValue || selectedReference.id_catigory || "";
    const initialSubcategory = subcategorySelect.dataset.initialValue || selectedReference.id_sub_catigory || "";
    const initialName = nameSelect.value || selectedReference.id_name || "";
    rebuildSelect(countrySelect, sortedUniqueRows(referenceRows, "id_gos", "gos"), initialCountry);
    refreshCategories(initialCategory);
    refreshSubcategories(initialSubcategory);
    refreshNames(initialName);
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
