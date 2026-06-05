(function () {
  function parseSuggestions(form) {
    const script = form.querySelector("script[data-search-suggestions]");
    if (!script) {
      return {};
    }
    try {
      return JSON.parse(script.textContent || "{}");
    } catch (_error) {
      return {};
    }
  }

  function rebuildDatalist(datalist, values) {
    datalist.replaceChildren();
    (values || []).forEach((value) => {
      const text = String(value || "").trim();
      if (!text) {
        return;
      }
      const option = document.createElement("option");
      option.value = text;
      datalist.appendChild(option);
    });
  }

  function initForm(form) {
    const suggestions = parseSuggestions(form);
    const scope = form.querySelector("select[name='scope']");
    const input = form.querySelector("input[name='q']");
    if (!scope || !input || !input.getAttribute("list")) {
      return;
    }
    const datalist = document.getElementById(input.getAttribute("list"));
    if (!datalist) {
      return;
    }
    function update() {
      rebuildDatalist(datalist, suggestions[scope.value] || []);
    }
    scope.addEventListener("change", update);
    update();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".search-suggestions-form").forEach(initForm);
  });
})();
