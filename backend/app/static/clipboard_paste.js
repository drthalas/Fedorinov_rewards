(function () {
  "use strict";

  var PHOTO_INTERACTION_STORAGE_KEY = "fedorinov-photo-interaction";
  var CLIPBOARD_PENDING_STORAGE_KEY = "fedorinov-clipboard-image-pending-v1";
  var CLIPBOARD_CONSUMED_STORAGE_KEY = "fedorinov-clipboard-image-consumed-v1";
  var CLIPBOARD_PENDING_MAX_AGE_MS = 5 * 60 * 1000;
  var CLIPBOARD_ATTEMPT_TIMEOUT_MS = 500;
  var CLIPBOARD_ATTEMPT_HARD_CEILING_MS = 1000;
  var clipboardFeedbackState = new WeakMap();

  function beginClipboardFeedback(trigger) {
    if (!trigger || clipboardFeedbackState.has(trigger)) return false;
    clipboardFeedbackState.set(trigger, {
      ariaLabel: trigger.getAttribute("aria-label"),
      title: trigger.getAttribute("title"),
    });
    trigger.dataset.clipboardPending = "true";
    trigger.setAttribute("aria-busy", "true");
    trigger.setAttribute("aria-label", "Проверяем буфер…");
    trigger.setAttribute("title", "Проверяем буфер…");
    trigger.disabled = true;
    return true;
  }

  function endClipboardFeedback(trigger) {
    if (!trigger) return;
    var state = clipboardFeedbackState.get(trigger);
    delete trigger.dataset.clipboardPending;
    trigger.removeAttribute("aria-busy");
    trigger.disabled = false;
    if (!state) return;
    if (state.ariaLabel === null) trigger.removeAttribute("aria-label");
    else trigger.setAttribute("aria-label", state.ariaLabel);
    if (state.title === null) trigger.removeAttribute("title");
    else trigger.setAttribute("title", state.title);
    clipboardFeedbackState.delete(trigger);
  }

  function readStoredJson(key) {
    try {
      var raw = window.sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      return null;
    }
  }

  function removeStoredValue(key) {
    try {
      window.sessionStorage.removeItem(key);
    } catch (error) {
      // Clipboard consume-once state is a progressive enhancement.
    }
  }

  function storeJson(key, value) {
    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (error) {
      return false;
    }
  }

  function bytesToHex(bytes) {
    var parts = [];
    for (var i = 0; i < bytes.length; i += 1) {
      parts.push(bytes[i].toString(16).padStart(2, "0"));
    }
    return parts.join("");
  }

  async function fingerprintImageBlob(blob) {
    if (!window.crypto || !window.crypto.subtle || typeof blob.arrayBuffer !== "function") {
      throw new Error("Clipboard fingerprint unavailable");
    }
    var digest = await window.crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
    return bytesToHex(new Uint8Array(digest));
  }

  function isConsumedFingerprint(fingerprint) {
    var consumed = readStoredJson(CLIPBOARD_CONSUMED_STORAGE_KEY);
    return Boolean(fingerprint && consumed && consumed.fingerprint === fingerprint);
  }

  function rememberPendingClipboardImage(image, successMarkers) {
    if (!image || !image.fingerprint) return false;
    return storeJson(CLIPBOARD_PENDING_STORAGE_KEY, {
      fingerprint: image.fingerprint,
      successMarkers: Array.isArray(successMarkers) ? successMarkers : [],
      savedAt: Date.now()
    });
  }

  function clearPendingClipboardImage(fingerprint) {
    var pending = readStoredJson(CLIPBOARD_PENDING_STORAGE_KEY);
    if (!pending || !fingerprint || pending.fingerprint === fingerprint) {
      removeStoredValue(CLIPBOARD_PENDING_STORAGE_KEY);
    }
  }

  function consumePendingClipboardImage(fingerprint) {
    var pending = readStoredJson(CLIPBOARD_PENDING_STORAGE_KEY);
    if (!pending || pending.fingerprint !== fingerprint) return false;
    storeJson(CLIPBOARD_CONSUMED_STORAGE_KEY, {
      fingerprint: fingerprint,
      consumedAt: Date.now()
    });
    removeStoredValue(CLIPBOARD_PENDING_STORAGE_KEY);
    return true;
  }

  function urlHasSuccessMarker(url, markers) {
    for (var i = 0; i < markers.length; i += 1) {
      var marker = String(markers[i] || "");
      var separator = marker.indexOf("=");
      if (separator <= 0) continue;
      var key = marker.slice(0, separator);
      var value = marker.slice(separator + 1);
      if (url.searchParams.get(key) === value) return true;
    }
    return false;
  }

  function settlePendingClipboardImage(urlValue) {
    var pending = readStoredJson(CLIPBOARD_PENDING_STORAGE_KEY);
    if (!pending) return false;
    if (Date.now() - Number(pending.savedAt || 0) > CLIPBOARD_PENDING_MAX_AGE_MS) {
      removeStoredValue(CLIPBOARD_PENDING_STORAGE_KEY);
      return false;
    }
    var url;
    try {
      url = new URL(urlValue, window.location.href);
    } catch (error) {
      removeStoredValue(CLIPBOARD_PENDING_STORAGE_KEY);
      return false;
    }
    if (urlHasSuccessMarker(url, pending.successMarkers || [])) {
      return consumePendingClipboardImage(pending.fingerprint);
    }
    removeStoredValue(CLIPBOARD_PENDING_STORAGE_KEY);
    return false;
  }

  function photoSourceError(button) {
    var container = button.closest(".photo-manage-actions");
    return container ? container.querySelector("[data-photo-source-error]") : null;
  }

  function clearSourceError(button) {
    var error = photoSourceError(button);
    if (!error) return;
    error.textContent = "";
    error.hidden = true;
  }

  function showSourceError(button, text) {
    var error = photoSourceError(button);
    if (!error) return;
    error.textContent = text;
    error.hidden = false;
  }

  function loadImage(blob) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(blob);
      var image = new Image();
      image.onload = function () {
        URL.revokeObjectURL(url);
        resolve(image);
      };
      image.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error("Не удалось подготовить JPEG из буфера. Используйте кнопку +."));
      };
      image.src = url;
    });
  }

  async function jpegBlobFromClipboardBlob(blob) {
    var source = window.createImageBitmap ? await window.createImageBitmap(blob) : await loadImage(blob);
    var width = source.width || source.naturalWidth;
    var height = source.height || source.naturalHeight;
    if (!width || !height) {
      if (source.close) {
        source.close();
      }
      throw new Error("Не удалось подготовить JPEG из буфера. Используйте кнопку +.");
    }
    var canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    var context = canvas.getContext("2d");
    if (!context) {
      if (source.close) {
        source.close();
      }
      throw new Error("Не удалось подготовить JPEG из буфера. Используйте кнопку +.");
    }
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(source, 0, 0);
    if (source.close) {
      source.close();
    }
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (jpegBlob) {
        if (!jpegBlob) {
          reject(new Error("Не удалось подготовить JPEG из буфера. Используйте кнопку +."));
          return;
        }
        resolve(jpegBlob);
      }, "image/jpeg", 0.85);
    });
  }

  async function imageBlobFromClipboard() {
    if (!navigator.clipboard || !navigator.clipboard.read) {
      throw new Error("Вставка из буфера недоступна в этом браузере. Используйте кнопку +.");
    }
    var items = await navigator.clipboard.read();
    for (var i = 0; i < items.length; i += 1) {
      var item = items[i];
      for (var j = 0; j < item.types.length; j += 1) {
        var type = item.types[j];
        if (type.indexOf("image/") === 0) {
          var blob = await item.getType(type);
          var fingerprint = await fingerprintImageBlob(blob);
          var jpegBlob = await jpegBlobFromClipboardBlob(blob);
          return { blob: jpegBlob, type: "image/jpeg", fingerprint: fingerprint };
        }
      }
    }
    throw new Error("В буфере обмена нет изображения.");
  }

  function imageBlobFromClipboardWithTimeout(timeoutMs) {
    return new Promise(function (resolve, reject) {
      var requestedTimeout = Number(timeoutMs) || CLIPBOARD_ATTEMPT_TIMEOUT_MS;
      var boundedTimeout = Math.min(Math.max(1, requestedTimeout), CLIPBOARD_ATTEMPT_HARD_CEILING_MS);
      var timeout = window.setTimeout(function () {
        reject(new Error("Буфер обмена не ответил вовремя."));
      }, boundedTimeout);
      imageBlobFromClipboard().then(function (image) {
        window.clearTimeout(timeout);
        resolve(image);
      }, function (error) {
        window.clearTimeout(timeout);
        reject(error);
      });
    });
  }

  async function freshImageBlobFromClipboardWithTimeout(timeoutMs) {
    var image = await imageBlobFromClipboardWithTimeout(timeoutMs);
    if (isConsumedFingerprint(image.fingerprint)) {
      var error = new Error("Clipboard image already consumed");
      error.code = "clipboard-image-consumed";
      throw error;
    }
    return image;
  }

  function photoPageScroller() {
    return document.querySelector("main.page");
  }

  function normalizedPageSearch(search) {
    return new URLSearchParams(search || "").toString();
  }

  function rememberPhotoInteraction(button) {
    var page = photoPageScroller();
    var state = {
      pathname: window.location.pathname,
      search: normalizedPageSearch(window.location.search),
      entityType: button.getAttribute("data-entity-type") || "",
      entityId: button.getAttribute("data-entity-id") || "",
      photoField: button.getAttribute("data-photo-field") || "",
      windowScrollY: window.scrollY,
      pageScrollTop: page ? page.scrollTop : 0,
      savedAt: Date.now()
    };
    try {
      window.sessionStorage.setItem(PHOTO_INTERACTION_STORAGE_KEY, JSON.stringify(state));
    } catch (error) {
      // Scroll restoration is a progressive enhancement; upload still works without storage.
    }
  }

  function savedPhotoTrigger(state) {
    var triggers = document.querySelectorAll("[data-file-input-id][data-entity-type][data-entity-id][data-photo-field]");
    for (var i = 0; i < triggers.length; i += 1) {
      var trigger = triggers[i];
      if (
        trigger.getAttribute("data-entity-type") === state.entityType &&
        trigger.getAttribute("data-entity-id") === state.entityId &&
        trigger.getAttribute("data-photo-field") === state.photoField
      ) {
        return trigger;
      }
    }
    return null;
  }

  function takePhotoInteraction() {
    var raw;
    try {
      raw = window.sessionStorage.getItem(PHOTO_INTERACTION_STORAGE_KEY);
      if (!raw) {
        return null;
      }
      window.sessionStorage.removeItem(PHOTO_INTERACTION_STORAGE_KEY);
      var state = JSON.parse(raw);
      if (
        state.pathname !== window.location.pathname ||
        normalizedPageSearch(state.search) !== normalizedPageSearch(window.location.search) ||
        Date.now() - Number(state.savedAt || 0) > 30000
      ) {
        return null;
      }
      return state;
    } catch (error) {
      return null;
    }
  }

  function restorePhotoInteraction() {
    var state = takePhotoInteraction();
    if (!state) {
      return;
    }
    var trigger = savedPhotoTrigger(state);
    if (!trigger) {
      return;
    }
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        var page = photoPageScroller();
        if (page) {
          page.scrollTop = Number(state.pageScrollTop || 0);
        }
        window.scrollTo(0, Number(state.windowScrollY || 0));
        try {
          trigger.focus({ preventScroll: true });
        } catch (error) {
          trigger.focus();
        }
      });
    });
  }

  async function uploadClipboardImage(button, image, reloadSamePage) {
    var form = new FormData();
    var returnUrl = button.getAttribute("data-return-url") || window.location.pathname;
    form.append("entity_type", button.getAttribute("data-entity-type") || "");
    form.append("entity_id", button.getAttribute("data-entity-id") || "");
    form.append("photo_field", button.getAttribute("data-photo-field") || "");
    form.append("return_url", returnUrl);
    form.append("file", image.blob, "clipboard.jpg");
    var writeForm = button.closest("form[data-write-feedback]");
    var writeFeedback = window.FedorinovWriteFeedback;
    if (writeForm && writeFeedback && typeof writeFeedback.begin === "function") {
      if (!writeFeedback.begin(writeForm, button, "Сохраняем фото…")) {
        throw new Error("Сохранение фотографии уже выполняется.");
      }
    }
    var personDraft = window.FedorinovPersonEditDraft;
    if (personDraft && typeof personDraft.captureForPhoto === "function") {
      personDraft.captureForPhoto(button);
    }
    rememberPendingClipboardImage(image, ["status=photo_updated", "media_cleanup=failed"]);
    var response;
    try {
      response = await fetch("/photos/upload", {
        method: "POST",
        body: form,
        credentials: "same-origin"
      });
    } catch (error) {
      clearPendingClipboardImage(image.fingerprint);
      if (writeForm && writeFeedback && typeof writeFeedback.finish === "function") {
        writeFeedback.finish(writeForm, { state: "error", message: "Не удалось сохранить фотографию." });
      }
      throw error;
    }
    if (!response.ok) {
      clearPendingClipboardImage(image.fingerprint);
      if (writeForm && writeFeedback && typeof writeFeedback.finish === "function") {
        writeFeedback.finish(writeForm, { state: "error", message: "Не удалось сохранить фотографию." });
      }
      throw new Error("Не удалось сохранить фото из буфера.");
    }
    var responseUrl = new URL(response.url, window.location.href);
    if (!response.redirected || !urlHasSuccessMarker(responseUrl, ["status=photo_updated", "media_cleanup=failed"])) {
      clearPendingClipboardImage(image.fingerprint);
      if (writeForm && writeFeedback && typeof writeFeedback.finish === "function") {
        writeFeedback.finish(writeForm, { state: "error", message: "Не удалось подтвердить сохранение фото." });
      }
      throw new Error("Не удалось подтвердить сохранение фото из буфера.");
    }
    consumePendingClipboardImage(image.fingerprint);
    var target = new URL(returnUrl, window.location.href);
    if (reloadSamePage && target.pathname === window.location.pathname && target.search === window.location.search) {
      window.history.replaceState(null, "", target.pathname + target.search + target.hash);
      window.location.reload();
      return;
    }
    window.location.href = returnUrl;
  }

  function openPersonFilePicker(button) {
    var inputId = button.getAttribute("data-file-input-id") || "";
    var input = inputId ? document.getElementById(inputId) : null;
    endClipboardFeedback(button);
    if (!(input instanceof HTMLInputElement)) {
      showSourceError(button, "Не удалось открыть выбор файла.");
      return false;
    }
    clearSourceError(button);
    rememberPhotoInteraction(button);

    function cleanup() {
      input.removeEventListener("cancel", onCancel);
      input.removeEventListener("change", onChange);
    }

    function onCancel() {
      cleanup();
      clearSourceError(button);
      restorePhotoInteraction();
    }

    function onChange() {
      cleanup();
      if (input.files && input.files.length) {
        rememberPhotoInteraction(button);
        clearSourceError(button);
        if (input.form) input.form.requestSubmit();
      } else {
        clearSourceError(button);
        restorePhotoInteraction();
      }
    }

    input.addEventListener("cancel", onCancel);
    input.addEventListener("change", onChange);
    try {
      input.click();
      return true;
    } catch (error) {
      cleanup();
      console.warn("Photo file picker did not open", error);
      showSourceError(button, "Не удалось открыть выбор файла.");
      return false;
    }
  }

  function bindInlinePhotoTrigger(button) {
    async function beginPhotoFlow() {
      if (!beginClipboardFeedback(button)) return;
      rememberPhotoInteraction(button);
      clearSourceError(button);
      var image;
      try {
        image = await freshImageBlobFromClipboardWithTimeout(CLIPBOARD_ATTEMPT_TIMEOUT_MS);
      } catch (error) {
        openPersonFilePicker(button);
        return;
      }
      try {
        await uploadClipboardImage(button, image, true);
      } catch (error) {
        endClipboardFeedback(button);
        rememberPhotoInteraction(button);
        showSourceError(button, error && error.message ? error.message : "Не удалось сохранить фотографию.");
        restorePhotoInteraction();
      }
    }

    button.addEventListener("click", function (event) {
      event.preventDefault();
      var confirmation = window.FedorinovImageReplacement;
      if (confirmation && typeof confirmation.run === "function") {
        confirmation.run(button, beginPhotoFlow);
        return;
      }
      beginPhotoFlow();
    });
  }

  window.FedorinovClipboardImages = Object.freeze({
    readWithTimeout: freshImageBlobFromClipboardWithTimeout,
    attemptTimeoutMs: CLIPBOARD_ATTEMPT_TIMEOUT_MS,
    beginFeedback: beginClipboardFeedback,
    endFeedback: endClipboardFeedback,
    rememberPending: rememberPendingClipboardImage,
    clearPending: clearPendingClipboardImage,
    consumePending: consumePendingClipboardImage,
    isConsumed: function (image) {
      return Boolean(image && isConsumedFingerprint(image.fingerprint));
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    settlePendingClipboardImage(window.location.href);
    document.querySelectorAll("[data-clipboard-paste]").forEach(function (button) {
      async function beginClipboardPaste() {
        if (!beginClipboardFeedback(button)) return;
        clearSourceError(button);
        try {
          var image = await imageBlobFromClipboard();
          await uploadClipboardImage(button, image, false);
        } catch (error) {
          endClipboardFeedback(button);
          showSourceError(button, error && error.message ? error.message : "Не удалось вставить фото из буфера.");
        }
      }

      button.addEventListener("click", function () {
        var confirmation = window.FedorinovImageReplacement;
        if (confirmation && typeof confirmation.run === "function") {
          confirmation.run(button, beginClipboardPaste);
          return;
        }
        beginClipboardPaste();
      });
    });

    document.querySelectorAll("[data-photo-plus-trigger]").forEach(bindInlinePhotoTrigger);

    restorePhotoInteraction();
  });

})();
