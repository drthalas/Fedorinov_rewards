(() => {
  "use strict";
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-import-file-input]").forEach((input) => {
      const area = input.closest(".person-import-file");
      const button = area.querySelector("[data-import-file-button]");
      const filename = area.querySelector("[data-import-file-name]");
      const updateName = () => {
        filename.textContent = input.files.length ? input.files[0].name : "Файл не выбран";
        delete filename.dataset.error;
      };
      button.addEventListener("click", () => input.click());
      input.addEventListener("change", updateName);
      input.addEventListener("invalid", (event) => {
        event.preventDefault();
        filename.textContent = "Выберите Excel-файл.";
        filename.dataset.error = "true";
        button.focus();
      });
      input.form.addEventListener("reset", () => requestAnimationFrame(updateName));
      input.tabIndex = -1;
      input.setAttribute("aria-hidden", "true");
      area.dataset.filePickerReady = "true";
      button.hidden = false;
      filename.hidden = false;
      updateName();
    });
  });
})();
