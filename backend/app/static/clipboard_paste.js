(function () {
  "use strict";

  function setStatus(button, text) {
    var container = button.closest(".photo-manage-actions");
    var status = container ? container.querySelector(".clipboard-paste-status") : null;
    if (status) {
      status.textContent = text;
    }
  }

  function extensionFromType(type) {
    if (type === "image/png") {
      return ".png";
    }
    if (type === "image/webp") {
      return ".webp";
    }
    return ".jpg";
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
          return { blob: blob, type: type };
        }
      }
    }
    throw new Error("В буфере обмена нет изображения.");
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-clipboard-paste]").forEach(function (button) {
      button.addEventListener("click", async function () {
        var originalText = button.textContent;
        button.disabled = true;
        setStatus(button, "Читаем буфер обмена...");
        try {
          var image = await imageBlobFromClipboard();
          var extension = extensionFromType(image.type);
          var form = new FormData();
          var returnUrl = button.getAttribute("data-return-url") || window.location.pathname;
          form.append("entity_type", button.getAttribute("data-entity-type") || "");
          form.append("entity_id", button.getAttribute("data-entity-id") || "");
          form.append("photo_field", button.getAttribute("data-photo-field") || "");
          form.append("return_url", returnUrl);
          form.append("file", image.blob, "clipboard" + extension);
          setStatus(button, "Сохраняем фото...");
          var response = await fetch("/photos/upload", {
            method: "POST",
            body: form,
            credentials: "same-origin"
          });
          if (!response.ok) {
            var text = await response.text();
            throw new Error(text || "Не удалось сохранить фото из буфера.");
          }
          window.location.href = returnUrl;
        } catch (error) {
          setStatus(button, error && error.message ? error.message : "Не удалось вставить фото из буфера.");
          button.disabled = false;
          button.textContent = originalText;
        }
      });
    });
  });
})();
