(() => {
  "use strict";

  function initialize() {
    document.querySelectorAll("[data-bio-file-picker]").forEach((area) => {
      const input = area.querySelector("input[type=file]");
      const button = area.querySelector("[data-bio-choose]");
      const filename = area.querySelector("[data-bio-file-name]");
      const error = area.querySelector("[data-bio-file-error]");
      if (!input || !button || !filename || !error) return;
      const update = () => {
        filename.textContent = input.files.length ? input.files[0].name : "";
        filename.hidden = !filename.textContent;
        error.textContent = "";
        error.hidden = true;
        button.removeAttribute("aria-invalid");
      };
      button.addEventListener("click", () => input.click());
      input.addEventListener("change", update);
      input.addEventListener("cancel", update);
      input.addEventListener("invalid", (event) => {
        event.preventDefault();
        error.textContent = "Выберите файл данных в формате .xlsx.";
        error.hidden = false;
        button.setAttribute("aria-invalid", "true");
        button.focus();
      });
      if (input.form) input.form.addEventListener("reset", () => queueMicrotask(update));
      // The visible native button is replaced by an equivalently labelled,
      // keyboard-operable button; the input stays enabled for multipart/validity.
      input.tabIndex = -1;
      input.setAttribute("aria-hidden", "true");
      area.dataset.bioPickerReady = "true";
      button.hidden = false;
      update();
    });

    document.querySelectorAll("[data-bio-result-link]").forEach((link) => {
      const group = document.getElementById(link.getAttribute("aria-controls"));
      if (!group || !group.classList.contains("bio-result-group")) return;
      const summary = group.querySelector("summary");
      const synchronize = () => link.setAttribute("aria-expanded", String(group.open));
      group.addEventListener("toggle", synchronize);
      link.addEventListener("click", (event) => {
        if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        group.open = true;
        const rows = group.querySelector(".bio-results");
        if (rows) rows.scrollTop = 0;
        if (summary) summary.focus({ preventScroll: true });
        group.scrollIntoView({ block: "start", behavior: "auto" });
        synchronize();
      });
      synchronize();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
