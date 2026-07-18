(() => {
  "use strict";

  const allowedExtensions = new Set(["jpg", "jpeg", "png", "webp"]);
  const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
  const maxBytes = 5 * 1024 * 1024;
  const rankScanMaxDimension = 1600;
  const rankOutputMaxDimension = 2400;
  const rankBackgroundTolerance = 24;

  function imageExtensionForType(type) {
    if (type === "image/png") return "png";
    if (type === "image/webp") return "webp";
    return "jpg";
  }

  function canvasToBlob(canvas, type) {
    const outputType = allowedTypes.has(type) ? type : "image/png";
    const quality = outputType === "image/png" ? undefined : 0.92;
    return new Promise((resolve) => canvas.toBlob(resolve, outputType, quality));
  }

  function loadImageFile(file) {
    return new Promise((resolve, reject) => {
      const source = URL.createObjectURL(file);
      const candidate = new Image();
      candidate.onload = () => {
        URL.revokeObjectURL(source);
        resolve(candidate);
      };
      candidate.onerror = () => {
        URL.revokeObjectURL(source);
        reject(new Error("Image decode failed"));
      };
      candidate.src = source;
    });
  }

  function rankContentBounds(context, width, height) {
    const pixels = context.getImageData(0, 0, width, height).data;
    const corners = [
      0,
      (width - 1) * 4,
      (height - 1) * width * 4,
      ((height - 1) * width + width - 1) * 4,
    ];
    const background = [0, 1, 2].map((channel) => (
      corners.reduce((sum, offset) => sum + pixels[offset + channel], 0) / corners.length
    ));
    let left = width;
    let top = height;
    let right = -1;
    let bottom = -1;

    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const offset = (y * width + x) * 4;
        const alpha = pixels[offset + 3];
        if (alpha <= 16) continue;
        const differs = Math.max(
          Math.abs(pixels[offset] - background[0]),
          Math.abs(pixels[offset + 1] - background[1]),
          Math.abs(pixels[offset + 2] - background[2]),
        ) > rankBackgroundTolerance;
        if (!differs) continue;
        left = Math.min(left, x);
        top = Math.min(top, y);
        right = Math.max(right, x);
        bottom = Math.max(bottom, y);
      }
    }
    if (right < left || bottom < top) return null;
    return { left, top, right, bottom };
  }

  async function normalizeRankImage(file) {
    const sourceImage = await loadImageFile(file);
    const sourceWidth = sourceImage.naturalWidth;
    const sourceHeight = sourceImage.naturalHeight;
    if (!sourceWidth || !sourceHeight) return file;

    const scanScale = Math.min(1, rankScanMaxDimension / Math.max(sourceWidth, sourceHeight));
    const scanWidth = Math.max(1, Math.round(sourceWidth * scanScale));
    const scanHeight = Math.max(1, Math.round(sourceHeight * scanScale));
    const scanCanvas = document.createElement("canvas");
    scanCanvas.width = scanWidth;
    scanCanvas.height = scanHeight;
    const scanContext = scanCanvas.getContext("2d", { willReadFrequently: true });
    if (!scanContext) return file;
    scanContext.drawImage(sourceImage, 0, 0, scanWidth, scanHeight);
    const bounds = rankContentBounds(scanContext, scanWidth, scanHeight);
    if (!bounds) return file;

    const contentWidth = bounds.right - bounds.left + 1;
    const contentHeight = bounds.bottom - bounds.top + 1;
    const padding = Math.max(4, Math.round(Math.max(contentWidth, contentHeight) * 0.05));
    const padded = {
      left: Math.max(0, bounds.left - padding),
      top: Math.max(0, bounds.top - padding),
      right: Math.min(scanWidth - 1, bounds.right + padding),
      bottom: Math.min(scanHeight - 1, bounds.bottom + padding),
    };
    const cropWidthRatio = (padded.right - padded.left + 1) / scanWidth;
    const cropHeightRatio = (padded.bottom - padded.top + 1) / scanHeight;
    if (cropWidthRatio > 0.92 && cropHeightRatio > 0.92) return file;

    const sourceX = Math.floor(padded.left / scanScale);
    const sourceY = Math.floor(padded.top / scanScale);
    const sourceCropWidth = Math.min(sourceWidth - sourceX, Math.ceil((padded.right - padded.left + 1) / scanScale));
    const sourceCropHeight = Math.min(sourceHeight - sourceY, Math.ceil((padded.bottom - padded.top + 1) / scanScale));
    const outputScale = Math.min(1, rankOutputMaxDimension / Math.max(sourceCropWidth, sourceCropHeight));
    const outputWidth = Math.max(1, Math.round(sourceCropWidth * outputScale));
    const outputHeight = Math.max(1, Math.round(sourceCropHeight * outputScale));
    const outputCanvas = document.createElement("canvas");
    outputCanvas.width = outputWidth;
    outputCanvas.height = outputHeight;
    const outputContext = outputCanvas.getContext("2d");
    if (!outputContext) return file;
    outputContext.drawImage(
      sourceImage,
      sourceX,
      sourceY,
      sourceCropWidth,
      sourceCropHeight,
      0,
      0,
      outputWidth,
      outputHeight,
    );
    const outputType = allowedTypes.has(file.type) ? file.type : "image/png";
    const blob = await canvasToBlob(outputCanvas, outputType);
    if (!blob || blob.size > maxBytes) return file;
    const baseName = file.name.replace(/\.[^.]+$/, "") || "rank-insignia";
    return new File([blob], `${baseName}.${imageExtensionForType(outputType)}`, {
      type: outputType,
      lastModified: file.lastModified || Date.now(),
    });
  }

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
    let allowConfirmedPicker = false;

    function setInputOccupied(occupied) {
      const confirmation = window.FedorinovImageReplacement;
      if (confirmation && typeof confirmation.setOccupied === "function") {
        confirmation.setOccupied(input, occupied);
      } else {
        input.setAttribute("data-image-slot-occupied", occupied ? "true" : "false");
      }
    }

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
      setInputOccupied(Boolean(currentSrc));
    }

    input.addEventListener("click", (event) => {
      if (allowConfirmedPicker) {
        allowConfirmedPicker = false;
        return;
      }
      const confirmation = window.FedorinovImageReplacement;
      if (!confirmation || typeof confirmation.run !== "function" || !confirmation.isOccupied(input)) return;
      event.preventDefault();
      confirmation.run(input, () => {
        allowConfirmedPicker = true;
        input.click();
      });
    });

    input.addEventListener("cancel", () => {
      try {
        input.focus({ preventScroll: true });
      } catch (error) {
        input.focus();
      }
    });

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
      setInputOccupied(true);
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
    const error = editor.querySelector("[data-rank-image-error]");
    if (!input || !trigger || !clear || !clearValue || !preview || !image || !placeholder || !error) return;

    let objectUrl = "";
    function setTriggerOccupied(occupied) {
      const confirmation = window.FedorinovImageReplacement;
      if (confirmation && typeof confirmation.setOccupied === "function") {
        confirmation.setOccupied(trigger, occupied);
      } else {
        trigger.setAttribute("data-image-slot-occupied", occupied ? "true" : "false");
      }
    }
    function revokeObjectUrl() {
      if (!objectUrl) return;
      URL.revokeObjectURL(objectUrl);
      objectUrl = "";
    }

    function showError(message) {
      error.textContent = message;
      error.hidden = false;
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
      trigger.setAttribute("aria-label", "Заменить изображение погона");
      trigger.title = "Заменить изображение погона";
      setTriggerOccupied(true);
      return true;
    }

    function assignInputFile(file) {
      if (!window.DataTransfer) return false;
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      return true;
    }

    async function useFile(file) {
      const normalizedFile = await normalizeRankImage(file);
      if (!assignInputFile(normalizedFile)) return false;
      return showFile(normalizedFile);
    }

    function openFilePicker() {
      trigger.disabled = false;
      clearError();
      try {
        input.click();
      } catch (error) {
        showError("Не удалось открыть выбор файла.");
      }
    }

    async function assignClipboardImage(clipboardImage) {
      if (!window.DataTransfer || !window.File) return false;
      const type = allowedTypes.has(clipboardImage.type) ? clipboardImage.type : "image/jpeg";
      const file = new File([clipboardImage.blob], `clipboard.${imageExtensionForType(type)}`, { type });
      return useFile(file);
    }

    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file) return;
      const helper = window.FedorinovClipboardImages;
      if (helper && typeof helper.clearPending === "function") helper.clearPending();
      trigger.disabled = true;
      try {
        if (!await useFile(file)) throw new Error("Image assignment unavailable");
      } catch (error) {
        showError("Не удалось прочитать выбранное изображение.");
      } finally {
        trigger.disabled = false;
      }
    });

    input.addEventListener("cancel", () => {
      trigger.disabled = false;
      try {
        trigger.focus({ preventScroll: true });
      } catch (error) {
        trigger.focus();
      }
    });

    async function beginRankImageFlow() {
      trigger.disabled = true;
      try {
        const helper = window.FedorinovClipboardImages;
        if (!helper || typeof helper.readWithTimeout !== "function") throw new Error("Clipboard API unavailable");
        const clipboardImage = await helper.readWithTimeout(1200);
        if (!await assignClipboardImage(clipboardImage)) throw new Error("Clipboard assignment unavailable");
        if (typeof helper.rememberPending === "function") {
          helper.rememberPending(clipboardImage, [
            "status=rank_created",
            "status=rank_updated",
            "status=media_cleanup_failed",
          ]);
        }
        trigger.disabled = false;
      } catch (error) {
        openFilePicker();
      }
    }

    trigger.addEventListener("click", () => {
      const confirmation = window.FedorinovImageReplacement;
      if (confirmation && typeof confirmation.run === "function") {
        confirmation.run(trigger, beginRankImageFlow);
        return;
      }
      beginRankImageFlow();
    });

    clear.addEventListener("click", () => {
      revokeObjectUrl();
      input.value = "";
      clearValue.value = "true";
      image.hidden = true;
      image.removeAttribute("src");
      placeholder.hidden = false;
      clear.hidden = true;
      trigger.setAttribute("aria-label", "Добавить изображение погона");
      trigger.title = "Добавить изображение погона";
      setTriggerOccupied(false);
      clearError();
      const helper = window.FedorinovClipboardImages;
      if (helper && typeof helper.clearPending === "function") helper.clearPending();
    });

    window.addEventListener("beforeunload", revokeObjectUrl, { once: true });
  }

  function init() {
    document.querySelectorAll("form.guide-item-form").forEach(initForm);
    document.querySelectorAll("[data-rank-image-editor]").forEach(initRankImageEditor);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
