(function () {
  "use strict";

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
    setStatus(button, "");
    if (input instanceof HTMLInputElement) {
      input.click();
    }
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

    document.querySelectorAll("[data-person-photo-trigger]").forEach(function (button) {
      button.addEventListener("click", async function () {
        button.disabled = true;
        setStatus(button, "Проверяем буфер обмена...");
        var image;
        try {
          image = await imageBlobFromClipboard();
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
        }
      });
    });
  });
})();
