(() => {
  "use strict";

  const allowedExtensions = new Set(["jpg", "jpeg", "png", "webp"]);
  const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
  const maxBytes = 5 * 1024 * 1024;

  function initForm(form) {
    const input = form.querySelector("[data-guide-image-input]");
    const preview = form.querySelector("[data-guide-image-preview]");
    const image = form.querySelector("[data-guide-image-preview-image]");
    const placeholder = form.querySelector("[data-guide-image-preview-placeholder]");
    const error = form.querySelector("[data-guide-image-preview-error]");
    const uploadName = form.querySelector("[data-guide-upload-name]");
    if (!input || !preview || !image || !placeholder || !error) return;

    const currentSrc = preview.dataset.currentSrc || "";
    let objectUrl = "";

    function revokeObjectUrl() {
      if (!objectUrl) return;
      URL.revokeObjectURL(objectUrl);
      objectUrl = "";
    }

    function showError(message) {
      revokeObjectUrl();
      image.hidden = true;
      image.removeAttribute("src");
      placeholder.hidden = false;
      error.textContent = message;
      error.hidden = false;
      input.setCustomValidity(message);
    }

    function resetPreview() {
      revokeObjectUrl();
      error.textContent = "";
      error.hidden = true;
      input.setCustomValidity("");
      if (currentSrc) {
        image.src = currentSrc;
        image.hidden = false;
        placeholder.hidden = true;
      } else {
        image.hidden = true;
        image.removeAttribute("src");
        placeholder.hidden = false;
      }
    }

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) {
        if (uploadName) uploadName.textContent = "Выберите файл или перетащите его сюда";
        resetPreview();
        return;
      }

      const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
      if (!allowedExtensions.has(extension) || (file.type && !allowedTypes.has(file.type))) {
        if (uploadName) uploadName.textContent = "Выберите поддерживаемое изображение";
        showError("Выберите изображение JPG, JPEG, PNG или WebP.");
        return;
      }
      if (file.size > maxBytes) {
        if (uploadName) uploadName.textContent = "Файл превышает допустимый размер";
        showError("Размер изображения не должен превышать 5 MB.");
        return;
      }

      revokeObjectUrl();
      input.setCustomValidity("");
      error.textContent = "";
      error.hidden = true;
      if (uploadName) uploadName.textContent = file.name;
      objectUrl = URL.createObjectURL(file);
      image.onload = () => {
        image.hidden = false;
        placeholder.hidden = true;
      };
      image.onerror = () => showError("Не удалось прочитать выбранное изображение.");
      image.src = objectUrl;
    });

    form.addEventListener("reset", () => window.requestAnimationFrame(resetPreview));
    window.addEventListener("beforeunload", revokeObjectUrl, { once: true });
  }

  function init() {
    document.querySelectorAll("form.guide-item-form").forEach(initForm);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
