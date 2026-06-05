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
      const keepCategory = changedRole === "init" ? category.value : "";
      const keepSubcategory = changedRole === "init" ? subcategory.value : "";
      const keepName = changedRole === "init" ? name.value : "";

      if (changedRole === "country") {
        category.value = "";
        subcategory.value = "";
        name.value = "";
      }
      if (changedRole === "category") {
        subcategory.value = "";
        name.value = "";
      }
      if (changedRole === "subcategory") {
        name.value = "";
      }

      rebuildSelect(category, rowsFor(options, "category", country.value), keepCategory);
      rebuildSelect(subcategory, rowsFor(options, "subcategory", category.value), keepSubcategory);
      rebuildSelect(name, rowsFor(options, "name", subcategory.value), keepName);
    }

    country.addEventListener("change", () => refresh("country"));
    category.addEventListener("change", () => refresh("category"));
    subcategory.addEventListener("change", () => refresh("subcategory"));
    refresh("init");
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".guide-cascade").forEach(initCascade);
  });
})();
