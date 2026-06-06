(function () {
  function filenameFromContentDisposition(headerValue) {
    if (!headerValue) {
      return "";
    }
    const utfMatch = headerValue.match(/filename\*=UTF-8''([^;]+)/i);
    if (utfMatch) {
      try {
        return decodeURIComponent(utfMatch[1].trim());
      } catch (error) {
        return utfMatch[1].trim();
      }
    }
    const plainMatch = headerValue.match(/filename="?([^";]+)"?/i);
    return plainMatch ? plainMatch[1].trim() : "";
  }

  function extensionFromFilename(filename) {
    const index = filename.lastIndexOf(".");
    return index >= 0 ? filename.slice(index).toLowerCase() : "";
  }

  function pickerTypes(filename, mimeType) {
    const extension = extensionFromFilename(filename);
    const cleanMimeType = (mimeType || "application/octet-stream").split(";")[0].trim() || "application/octet-stream";
    const descriptionByExtension = {
      ".zip": "ZIP-архив",
      ".pdf": "PDF",
      ".csv": "CSV",
    };
    if (!extension) {
      return [];
    }
    return [
      {
        description: descriptionByExtension[extension] || "Файл",
        accept: {
          [cleanMimeType]: [extension],
        },
      },
    ];
  }

  function setMessage(form, message, kind) {
    const targetSelector = form.getAttribute("data-save-as-status");
    let target = targetSelector ? document.querySelector(targetSelector) : null;
    if (!target) {
      target = form.querySelector("[data-save-as-inline-status]");
    }
    if (!target) {
      target = document.createElement("div");
      target.setAttribute("data-save-as-inline-status", "");
      target.className = "save-as-status";
      form.appendChild(target);
    }
    target.textContent = message || "";
    target.classList.remove("notice-success", "notice-error");
    if (kind === "success") {
      target.classList.add("notice-success");
    } else if (kind === "error") {
      target.classList.add("notice-error");
    }
  }

  async function writeWithFilePicker(blob, filename) {
    const handle = await window.showSaveFilePicker({
      suggestedName: filename || "download",
      types: pickerTypes(filename, blob.type),
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
  }

  function fallbackDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || "download";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1000);
  }

  async function saveResponse(form) {
    const method = (form.getAttribute("method") || "get").toUpperCase();
    let url = form.getAttribute("action") || window.location.href;
    const options = {
      method,
      credentials: "same-origin",
    };
    const formData = new FormData(form);
    if (method === "GET") {
      const query = new URLSearchParams(formData);
      const separator = url.indexOf("?") >= 0 ? "&" : "?";
      const queryText = query.toString();
      if (queryText) {
        url += separator + queryText;
      }
    } else {
      options.body = formData;
    }

    const response = await fetch(url, options);
    if (!response.ok) {
      let message = "Не удалось подготовить файл.";
      try {
        const data = await response.json();
        message = data.detail || message;
      } catch (error) {
        const text = await response.text();
        if (text) {
          message = text;
        }
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const headerFilename = filenameFromContentDisposition(response.headers.get("Content-Disposition"));
    const filename = headerFilename || form.getAttribute("data-save-as-filename") || "download";
    await writeWithFilePicker(blob, filename);
    return filename;
  }

  document.addEventListener("submit", async function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-save-as-form")) {
      return;
    }
    if (!("showSaveFilePicker" in window)) {
      window.alert("Ваш браузер не поддерживает выбор места сохранения. Файл будет скачан обычным способом.");
      return;
    }

    event.preventDefault();
    const submitter = event.submitter;
    if (submitter) {
      submitter.disabled = true;
    }
    setMessage(form, "Подготовка файла...", "");
    try {
      await saveResponse(form);
      setMessage(form, "Файл сохранён.", "success");
    } catch (error) {
      if (error && error.name === "AbortError") {
        setMessage(form, "Сохранение отменено.", "");
      } else {
        setMessage(form, error && error.message ? error.message : "Не удалось сохранить файл.", "error");
      }
    } finally {
      if (submitter) {
        submitter.disabled = false;
      }
    }
  });

  window.FedorinovSaveAs = {
    fallbackDownload,
    filenameFromContentDisposition,
  };
})();
