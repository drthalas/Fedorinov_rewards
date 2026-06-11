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

  function mimeTypeForFilename(filename) {
    const extension = extensionFromFilename(filename);
    if (extension === ".pdf") {
      return "application/pdf";
    }
    if (extension === ".zip") {
      return "application/zip";
    }
    if (extension === ".csv") {
      return "text/csv";
    }
    return "application/octet-stream";
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

  async function openSaveFilePicker(filename, mimeType) {
    return await window.showSaveFilePicker({
      suggestedName: filename || "download",
      types: pickerTypes(filename, mimeType),
    });
  }

  async function writeFileHandle(handle, blob) {
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

  function requestFromForm(form) {
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
    return { url, options };
  }

  function filenameFromRequest(form, url) {
    const explicit = form.getAttribute("data-save-as-filename");
    if (explicit) {
      return explicit;
    }
    try {
      const path = new URL(url, window.location.href).pathname;
      const lastSegment = path.split("/").filter(Boolean).pop() || "";
      if (lastSegment.indexOf(".") >= 0) {
        return lastSegment;
      }
    } catch (error) {
      // Keep the generic fallback below.
    }
    return "download";
  }

  async function fetchFileResponse(request) {
    const { url, options } = request;
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
    return response;
  }

  async function responseBlobAndFilename(response, fallbackFilename) {
    const blob = await response.blob();
    const headerFilename = filenameFromContentDisposition(response.headers.get("Content-Disposition"));
    const filename = fallbackFilename || headerFilename || "download";
    return { blob, filename };
  }

  async function saveResponse(fileHandle, request, pickerFilename) {
    const response = await fetchFileResponse(request);
    const { blob, filename } = await responseBlobAndFilename(response, pickerFilename);
    await writeFileHandle(fileHandle, blob);
    return filename;
  }

  async function downloadWithFallback(form, request, fallbackFilename) {
    setMessage(form, "Подготовка обычной загрузки файла...", "");
    const response = await fetchFileResponse(request);
    const { blob, filename } = await responseBlobAndFilename(response, fallbackFilename);
    fallbackDownload(blob, filename);
    return filename;
  }

  function saveDialogErrorMessage(error) {
    if (error && error.name === "AbortError") {
      return "Сохранение отменено.";
    }
    if (
      error &&
      (
        error.name === "SecurityError" ||
        String(error.message || "").indexOf("Must be handling a user gesture") >= 0
      )
    ) {
      console.warn("Save As file picker failed", error);
      return "Не удалось открыть окно сохранения. Попробуйте обычную загрузку файла или другой браузер.";
    }
    return "";
  }

  document.addEventListener("submit", async function (event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-save-as-form")) {
      return;
    }
    event.preventDefault();
    const request = requestFromForm(form);
    const pickerFilename = filenameFromRequest(form, request.url);
    const submitter = event.submitter;
    if (submitter) {
      submitter.disabled = true;
    }

    if (!("showSaveFilePicker" in window)) {
      setMessage(form, "Ваш браузер не поддерживает выбор места сохранения. Файл будет скачан обычным способом.", "");
      try {
        await downloadWithFallback(form, request, pickerFilename);
        setMessage(form, "Файл скачан обычным способом. Проверьте папку загрузок браузера.", "success");
      } catch (error) {
        setMessage(form, error && error.message ? error.message : "Не удалось скачать файл.", "error");
      } finally {
        if (submitter) {
          submitter.disabled = false;
        }
      }
      return;
    }

    const pickerMimeType = form.getAttribute("data-save-as-mime") || mimeTypeForFilename(pickerFilename);
    let fileHandle;
    try {
      fileHandle = await openSaveFilePicker(pickerFilename, pickerMimeType);
    } catch (error) {
      const message = saveDialogErrorMessage(error) || "Не удалось открыть окно сохранения. Попробуйте обычную загрузку файла или другой браузер.";
      if (error && error.name === "AbortError") {
        setMessage(form, message, "");
      } else {
        setMessage(form, message, "error");
        try {
          await downloadWithFallback(form, request, pickerFilename);
          setMessage(form, "Файл скачан обычным способом. Проверьте папку загрузок браузера.", "success");
        } catch (fallbackError) {
          setMessage(form, fallbackError && fallbackError.message ? fallbackError.message : "Не удалось скачать файл.", "error");
        }
      }
      if (submitter) {
        submitter.disabled = false;
      }
      return;
    }

    setMessage(form, "Подготовка файла...", "");
    try {
      await saveResponse(fileHandle, request, pickerFilename);
      setMessage(form, "Файл сохранён. Откройте его из выбранной папки.", "success");
    } catch (error) {
      const message = saveDialogErrorMessage(error);
      if (message === "Сохранение отменено.") {
        setMessage(form, message, "");
      } else {
        setMessage(form, message || (error && error.message ? error.message : "Не удалось сохранить файл."), "error");
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
    filenameFromRequest,
    downloadWithFallback,
    mimeTypeForFilename,
  };
})();
