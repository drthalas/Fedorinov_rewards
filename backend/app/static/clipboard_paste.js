(function () {
  "use strict";

  var PHOTO_INTERACTION_STORAGE_KEY = "fedorinov-photo-interaction";

  function setStatus(button, text) {
    var container = button.closest(".photo-manage-actions");
    var status = container ? container.querySelector(".clipboard-paste-status") : null;
    if (status) {
      status.textContent = text;
    }
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
          var jpegBlob = await jpegBlobFromClipboardBlob(blob);
          return { blob: jpegBlob, type: "image/jpeg" };
        }
      }
    }
    throw new Error("В буфере обмена нет изображения.");
  }

  function imageBlobFromClipboardWithTimeout(timeoutMs) {
    return new Promise(function (resolve, reject) {
      var timeout = window.setTimeout(function () {
        reject(new Error("Буфер обмена не ответил вовремя."));
      }, timeoutMs);
      imageBlobFromClipboard().then(function (image) {
        window.clearTimeout(timeout);
        resolve(image);
      }, function (error) {
        window.clearTimeout(timeout);
        reject(error);
      });
    });
  }

  function photoPageScroller() {
    return document.querySelector("main.page");
  }

  function rememberPhotoInteraction(button) {
    var page = photoPageScroller();
    var state = {
      pathname: window.location.pathname,
      search: window.location.search,
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
        state.search !== window.location.search ||
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
    var response = await fetch("/photos/upload", {
      method: "POST",
      body: form,
      credentials: "same-origin"
    });
    if (!response.ok) {
      var text = await response.text();
      throw new Error(text || "Не удалось сохранить фото из буфера.");
    }
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
    button.disabled = false;
    if (!(input instanceof HTMLInputElement)) {
      setStatus(button, "Не удалось открыть выбор файла.");
      return false;
    }
    setStatus(button, "Выберите файл...");
    input.addEventListener("cancel", function onCancel() {
      setStatus(button, "");
      restorePhotoInteraction();
    }, { once: true });
    input.addEventListener("change", function onChange() {
      if (input.files && input.files.length) {
        rememberPhotoInteraction(button);
        setStatus(button, "Загружаем фотографию...");
      } else {
        setStatus(button, "");
        restorePhotoInteraction();
      }
    }, { once: true });
    try {
      if (typeof input.showPicker === "function") {
        input.showPicker();
      } else {
        input.click();
      }
      return true;
    } catch (error) {
      try {
        input.click();
        return true;
      } catch (fallbackError) {
        console.warn("Photo file picker did not open", fallbackError || error);
        setStatus(button, "Не удалось открыть выбор файла.");
        return false;
      }
    }
  }

  function bindInlinePhotoTrigger(button) {
    button.addEventListener("click", async function (event) {
      event.preventDefault();
      rememberPhotoInteraction(button);
      button.disabled = true;
      setStatus(button, "Проверяем буфер обмена...");
      var image;
      try {
        image = await imageBlobFromClipboardWithTimeout(2000);
      } catch (error) {
        openPersonFilePicker(button);
        return;
      }
      try {
        setStatus(button, "Сохраняем фото...");
        await uploadClipboardImage(button, image, true);
      } catch (error) {
        setStatus(button, error && error.message ? error.message : "Не удалось сохранить фотографию.");
        button.disabled = false;
        restorePhotoInteraction();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-clipboard-paste]").forEach(function (button) {
      button.addEventListener("click", async function () {
        var originalText = button.textContent;
        button.disabled = true;
        setStatus(button, "Читаем буфер обмена...");
        try {
          var image = await imageBlobFromClipboard();
          setStatus(button, "Сохраняем фото...");
          await uploadClipboardImage(button, image, false);
        } catch (error) {
          setStatus(button, error && error.message ? error.message : "Не удалось вставить фото из буфера.");
          button.disabled = false;
          button.textContent = originalText;
        }
      });
    });

    document.querySelectorAll("[data-person-photo-trigger]").forEach(bindInlinePhotoTrigger);
    document.querySelectorAll("[data-reward-photo-trigger]").forEach(bindInlinePhotoTrigger);

    restorePhotoInteraction();
  });

})();
