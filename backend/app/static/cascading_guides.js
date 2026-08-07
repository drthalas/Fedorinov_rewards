(function () {
  function parseOptions(container) {
    const script = container.querySelector("script[data-guide-cascade-options]");
    if (!script) {
      return null;
    }
    try {
      return JSON.parse(script.textContent || "{}");
    } catch (_error) {
      return null;
    }
  }

  function optionText(row) {
    const value = row && row.name != null ? String(row.name).trim() : "";
    return value || "—";
  }

  function rowsFor(options, role, parentValue) {
    if (role === "country") {
      return options.countries || [];
    }
    const parentId = parentValue ? Number(parentValue) : null;
    if (!parentId) {
      return [];
    }
    const source = role === "category"
      ? options.categories || []
      : role === "subcategory"
        ? options.subcategories || []
        : options.names || [];
    return source.filter((row) => Number(row.idl) === parentId);
  }

  function rebuildSelect(select, rows, selectedValue) {
    const placeholder = select.options.length ? select.options[0].textContent : "—";
    select.replaceChildren();
    select.appendChild(new Option(placeholder || "—", ""));
    rows.forEach((row) => {
      const value = String(row.id);
      const option = new Option(optionText(row), value);
      if (selectedValue && selectedValue === value) {
        option.selected = true;
      }
      select.appendChild(option);
    });
  }

  function initCascade(container) {
    const state = container.dataset || {};
    if (state.guideCascadeInitialized === "true") {
      return;
    }
    const options = parseOptions(container);
    if (!options) {
      return;
    }
    const country = container.querySelector("[data-guide-role='country']");
    const category = container.querySelector("[data-guide-role='category']");
    const subcategory = container.querySelector("[data-guide-role='subcategory']");
    const name = container.querySelector("[data-guide-role='name']");
    if (!country || !category || !subcategory || !name) {
      return;
    }

    function refresh(changedRole) {
      const selectedCategory = changedRole === "country" ? "" : category.value;
      const selectedSubcategory = changedRole === "country" || changedRole === "category" ? "" : subcategory.value;
      const selectedName = changedRole === "country" || changedRole === "category" || changedRole === "subcategory" ? "" : name.value;

      rebuildSelect(category, rowsFor(options, "category", country.value), selectedCategory);
      rebuildSelect(subcategory, rowsFor(options, "subcategory", selectedCategory), selectedSubcategory);
      rebuildSelect(name, rowsFor(options, "name", selectedSubcategory), selectedName);
    }

    country.addEventListener("change", () => refresh("country"));
    category.addEventListener("change", () => refresh("category"));
    subcategory.addEventListener("change", () => refresh("subcategory"));
    if (container.dataset) {
      container.dataset.guideCascadeInitialized = "true";
    }
    refresh("init");
  }

  function initAll(root) {
    const scope = root || document;
    if (scope.matches && scope.matches(".guide-cascade")) {
      initCascade(scope);
    }
    scope.querySelectorAll(".guide-cascade").forEach(initCascade);
  }

  document.addEventListener("DOMContentLoaded", () => initAll(document));
  document.addEventListener("legacy:content-updated", (event) => initAll(event && event.detail && event.detail.root ? event.detail.root : document));
})();
