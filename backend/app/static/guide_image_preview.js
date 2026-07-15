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

  function initRankImageEditor(editor) {
    const input = editor.querySelector("[data-rank-image-input]");
    const trigger = editor.querySelector("[data-rank-image-trigger]");
    const clear = editor.querySelector("[data-rank-image-clear]");
    const clearValue = editor.querySelector("[data-rank-image-clear-value]");
    const preview = editor.querySelector("[data-rank-image-preview]");
    const image = editor.querySelector("[data-rank-image-preview-image]");
    const placeholder = editor.querySelector("[data-rank-image-preview-placeholder]");
    const status = editor.querySelector("[data-rank-image-status]");
    const error = editor.querySelector("[data-rank-image-error]");
    if (!input || !trigger || !clear || !clearValue || !preview || !image || !placeholder || !status || !error) return;

    let objectUrl = "";

    function revokeObjectUrl() {
      if (!objectUrl) return;
      URL.revokeObjectURL(objectUrl);
      objectUrl = "";
    }

    function showError(message) {
      error.textContent = message;
      error.hidden = false;
      status.textContent = "";
      input.setCustomValidity(message);
    }

    function clearError() {
      error.textContent = "";
      error.hidden = true;
      input.setCustomValidity("");
    }

    function showFile(file) {
      const extension = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
      if (!allowedExtensions.has(extension) || (file.type && !allowedTypes.has(file.type))) {
        showError("Выберите изображение JPG, JPEG, PNG или WebP.");
        return false;
      }
      if (file.size > maxBytes) {
        showError("Размер изображения не должен превышать 5 MB.");
        return false;
      }
      revokeObjectUrl();
      clearError();
      clearValue.value = "";
      objectUrl = URL.createObjectURL(file);
      image.onload = () => {
        image.hidden = false;
        placeholder.hidden = true;
        clear.hidden = false;
      };
      image.onerror = () => showError("Не удалось прочитать выбранное изображение.");
      image.src = objectUrl;
      status.textContent = file.name;
      return true;
    }

    function openFilePicker() {
      status.textContent = "Выберите изображение…";
      trigger.disabled = false;
      try {
        if (typeof input.showPicker === "function") input.showPicker();
        else input.click();
      } catch (error) {
        try {
          input.click();
        } catch (fallbackError) {
          showError("Не удалось открыть выбор файла.");
        }
      }
    }

    function assignClipboardImage(clipboardImage) {
      if (!window.DataTransfer || !window.File) return false;
      const file = new File([clipboardImage.blob], "clipboard.jpg", { type: clipboardImage.type || "image/jpeg" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) {
        status.textContent = "";
        return;
      }
      showFile(file);
    });

    trigger.addEventListener("click", async () => {
      trigger.disabled = true;
      status.textContent = "Проверяем буфер обмена…";
      try {
        const helper = window.FedorinovClipboardImages;
        if (!helper || typeof helper.readWithTimeout !== "function") throw new Error("Clipboard API unavailable");
        const clipboardImage = await helper.readWithTimeout(1200);
        if (!assignClipboardImage(clipboardImage)) throw new Error("Clipboard assignment unavailable");
        trigger.disabled = false;
      } catch (error) {
        openFilePicker();
      }
    });

    clear.addEventListener("click", () => {
      revokeObjectUrl();
      input.value = "";
      clearValue.value = "true";
      image.hidden = true;
      image.removeAttribute("src");
      placeholder.hidden = false;
      clear.hidden = true;
      status.textContent = "Изображение будет удалено после сохранения.";
      clearError();
    });

    window.addEventListener("beforeunload", revokeObjectUrl, { once: true });
  }

  function init() {
    document.querySelectorAll("form.guide-item-form").forEach(initForm);
    document.querySelectorAll("[data-rank-image-editor]").forEach(initRankImageEditor);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
