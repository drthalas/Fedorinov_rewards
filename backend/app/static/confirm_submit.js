function setInputValue(form, name, value) {
  const input = form.querySelector(`input[name="${name}"]`);
  if (input) {
    input.value = value;
  }
}

function setDeleteConfirmation(form, confirmed) {
  const value = confirmed ? "true" : "";
  setInputValue(form, "confirm", value);
  if (form.dataset.confirmSubmit === "reward-delete") {
    setInputValue(form, "delete_reward_confirm", value);
  } else if (form.dataset.confirmSubmit === "person-delete") {
    setInputValue(form, "delete_person_confirm", value);
  }
}

function disableDeleteSubmitters(form) {
  form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((control) => {
    if (!control.disabled) {
      control.dataset.deleteDisabledBySubmit = "true";
    }
    control.disabled = true;
    control.setAttribute("aria-disabled", "true");
  });
}

function resetDeleteSubmissions() {
  document.querySelectorAll("form[data-delete-submitting]").forEach((form) => {
    delete form.dataset.deleteSubmitting;
    form.querySelectorAll('[data-delete-disabled-by-submit="true"]').forEach((control) => {
      control.disabled = false;
      control.removeAttribute("aria-disabled");
      delete control.dataset.deleteDisabledBySubmit;
    });
  });
}

const DELETE_PREFLIGHT_TIMEOUT_MS = 15000;
const DELETE_PREFLIGHT_LOADING = "Проверяем возможность удаления…";
const DELETE_PREFLIGHT_ERROR = "Не удалось проверить возможность удаления. Повторите попытку.";

function setDeletePreview(form, preview) {
  form.dataset.confirmMessage = String(preview.message || "Подтвердите удаление.");
  form.dataset.confirmBlocked = preview.blocked === true || preview.allowed === false ? "true" : "false";
  setInputValue(form, "delete_operation_id", String(preview.operation_id || ""));
}

function validateDeletePreview(form, preview) {
  const expectedType = String(form.dataset.deleteEntityType || "");
  const expectedId = String(form.dataset.deleteEntityId || "");
  if (
    !preview
    || typeof preview.message !== "string"
    || typeof preview.blocked !== "boolean"
    || typeof preview.allowed !== "boolean"
    || typeof preview.operation_id !== "string"
    || String(preview.entity_type || "") !== expectedType
    || String(preview.entity_id ?? "") !== expectedId
  ) {
    throw new Error("Invalid delete preflight response.");
  }
  return preview;
}

function createDeleteConfirmationDialog() {
  const dialog = document.createElement("dialog");
  dialog.className = "delete-confirmation-dialog";
  dialog.setAttribute("role", "alertdialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "delete-confirmation-title");
  dialog.setAttribute("aria-describedby", "delete-confirmation-message");

  const panel = document.createElement("div");
  panel.className = "delete-confirmation-panel";

  const title = document.createElement("h2");
  title.id = "delete-confirmation-title";

  const message = document.createElement("p");
  message.id = "delete-confirmation-message";

  const actions = document.createElement("div");
  actions.className = "delete-confirmation-actions";

  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.className = "button secondary-button";
  cancelButton.dataset.deleteConfirmationCancel = "";
  cancelButton.textContent = "Отмена";

  const confirmButton = document.createElement("button");
  confirmButton.type = "button";
  confirmButton.className = "button-danger";
  confirmButton.dataset.deleteConfirmationConfirm = "";
  confirmButton.textContent = "Удалить";

  actions.append(cancelButton, confirmButton);
  panel.append(title, message, actions);
  dialog.append(panel);
  document.body.append(dialog);
  return dialog;
}

let activeDeleteForm = null;
let activeDeleteSubmitter = null;
let activeDeleteTrigger = null;
let activeDeleteRequest = null;
let deleteRequestSequence = 0;
let dialogResult = "cancel";

function focusableDialogControls(dialog) {
  return Array.from(dialog.querySelectorAll("button:not([hidden]):not([disabled])"));
}

function abortActiveDeleteRequest() {
  if (!activeDeleteRequest) {
    return;
  }
  activeDeleteRequest.controller.abort();
  window.clearTimeout(activeDeleteRequest.timeoutId);
  if (activeDeleteRequest.submitter instanceof HTMLElement) {
    activeDeleteRequest.submitter.removeAttribute("aria-busy");
  }
  delete activeDeleteRequest.form.dataset.deletePreviewLoading;
  activeDeleteRequest = null;
}

function closeDeleteConfirmation(dialog, result = "cancel") {
  dialogResult = result;
  if (result === "cancel") {
    abortActiveDeleteRequest();
  }
  if (typeof dialog.close === "function" && dialog.open) {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
    dialog.dispatchEvent(new Event("close"));
  }
}

function renderDeleteConfirmation(dialog, form, state = "ready") {
  const loading = state === "loading";
  const blocked = loading || form.dataset.confirmBlocked === "true";
  const title = dialog.querySelector("#delete-confirmation-title");
  const message = dialog.querySelector("#delete-confirmation-message");
  const cancelButton = dialog.querySelector("[data-delete-confirmation-cancel]");
  const confirmButton = dialog.querySelector("[data-delete-confirmation-confirm]");

  title.textContent = form.dataset.confirmTitle || "Подтверждение удаления";
  message.textContent = loading ? DELETE_PREFLIGHT_LOADING : (form.dataset.confirmMessage || "Подтвердите действие.");
  confirmButton.hidden = blocked;
  confirmButton.disabled = blocked;
  cancelButton.textContent = loading ? "Отмена" : (blocked ? "Закрыть" : "Отмена");
  dialog.classList.toggle("delete-confirmation-blocked", blocked && !loading);
  dialog.classList.toggle("delete-confirmation-loading", loading);
  dialog.setAttribute("aria-busy", loading ? "true" : "false");

  if (!loading) {
    (blocked ? cancelButton : confirmButton).focus();
  }
}

function openDeleteConfirmation(form, submitter, state = "ready") {
  const dialog = document.querySelector(".delete-confirmation-dialog") || createDeleteConfirmationDialog();
  activeDeleteForm = form;
  activeDeleteSubmitter = submitter || null;
  activeDeleteTrigger = submitter || document.activeElement;
  dialogResult = "cancel";
  setDeleteConfirmation(form, false);
  renderDeleteConfirmation(dialog, form, state);

  if (!dialog.open) {
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }
  const cancelButton = dialog.querySelector("[data-delete-confirmation-cancel]");
  if (state === "loading" && cancelButton instanceof HTMLElement) {
    cancelButton.focus();
  }
  return dialog;
}

async function loadDeletePreflight(form, submitter, dialog) {
  abortActiveDeleteRequest();
  const url = form.dataset.confirmPreviewUrl;
  if (!url) {
    return;
  }
  const sequence = ++deleteRequestSequence;
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, DELETE_PREFLIGHT_TIMEOUT_MS);
  activeDeleteRequest = { controller, form, sequence, submitter, timeoutId };
  form.dataset.deletePreviewLoading = "true";
  setDeletePreview(form, { message: DELETE_PREFLIGHT_LOADING, blocked: true, allowed: false, operation_id: "" });
  if (submitter instanceof HTMLElement) {
    submitter.setAttribute("aria-busy", "true");
  }

  try {
    const response = await window.fetch(url, {
      headers: {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const preview = validateDeletePreview(form, await response.json());
    if (!activeDeleteRequest || activeDeleteRequest.sequence !== sequence || activeDeleteForm !== form) {
      return;
    }
    setDeletePreview(form, preview);
    renderDeleteConfirmation(dialog, form, "ready");
  } catch (error) {
    const superseded = !activeDeleteRequest || activeDeleteRequest.sequence !== sequence || activeDeleteForm !== form;
    if (superseded || (controller.signal.aborted && !timedOut)) {
      return;
    }
    setDeletePreview(form, {
      message: DELETE_PREFLIGHT_ERROR,
      blocked: true,
      allowed: false,
      operation_id: "",
    });
    renderDeleteConfirmation(dialog, form, "error");
  } finally {
    window.clearTimeout(timeoutId);
    if (activeDeleteRequest && activeDeleteRequest.sequence === sequence) {
      activeDeleteRequest = null;
      delete form.dataset.deletePreviewLoading;
      if (submitter instanceof HTMLElement) {
        submitter.removeAttribute("aria-busy");
      }
      dialog.setAttribute("aria-busy", "false");
    }
  }
}

document.addEventListener(
  "submit",
  (event) => {
    const form = event.target instanceof HTMLFormElement ? event.target : null;
    if (!form || !form.matches("[data-confirm-submit]")) {
      return;
    }

    if (form.dataset.deleteSubmitting === "true") {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    if (form.dataset.deleteConfirmed === "true") {
      delete form.dataset.deleteConfirmed;
      form.dataset.deleteSubmitting = "true";
      if (!form.matches("[data-write-feedback]")) {
        disableDeleteSubmitters(form);
      }
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    const submitter = event.submitter;
    if (!form.dataset.confirmPreviewUrl) {
      openDeleteConfirmation(form, submitter);
      return;
    }

    setDeletePreview(form, { message: DELETE_PREFLIGHT_LOADING, blocked: true, allowed: false, operation_id: "" });
    const dialog = openDeleteConfirmation(form, submitter, "loading");
    void loadDeletePreflight(form, submitter, dialog);
  },
  true
);

document.addEventListener("click", (event) => {
  const dialog = event.target instanceof Element ? event.target.closest(".delete-confirmation-dialog") : null;
  if (!dialog) {
    return;
  }
  if (event.target.closest("[data-delete-confirmation-cancel]")) {
    if (activeDeleteForm) {
      setDeleteConfirmation(activeDeleteForm, false);
    }
    closeDeleteConfirmation(dialog, "cancel");
    return;
  }
  if (event.target.closest("[data-delete-confirmation-confirm]") && activeDeleteForm) {
    const form = activeDeleteForm;
    const submitter = activeDeleteSubmitter;
    setDeleteConfirmation(form, true);
    form.dataset.deleteConfirmed = "true";
    activeDeleteForm = null;
    activeDeleteSubmitter = null;
    activeDeleteTrigger = null;
    closeDeleteConfirmation(dialog, "confirm");
    form.requestSubmit(submitter || undefined);
  }
});

document.addEventListener("cancel", (event) => {
  const dialog = event.target instanceof HTMLDialogElement ? event.target : null;
  if (!dialog || !dialog.matches(".delete-confirmation-dialog")) {
    return;
  }
  event.preventDefault();
  if (activeDeleteForm) {
    setDeleteConfirmation(activeDeleteForm, false);
  }
  closeDeleteConfirmation(dialog, "cancel");
}, true);

document.addEventListener("keydown", (event) => {
  const dialog = document.querySelector(".delete-confirmation-dialog[open]");
  if (!dialog) {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    event.stopImmediatePropagation();
    if (activeDeleteForm) {
      setDeleteConfirmation(activeDeleteForm, false);
    }
    closeDeleteConfirmation(dialog, "cancel");
    return;
  }
  if (event.key !== "Tab") {
    return;
  }
  const controls = focusableDialogControls(dialog);
  if (!controls.length) {
    event.preventDefault();
    return;
  }
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}, true);

document.addEventListener("close", (event) => {
  const dialog = event.target instanceof HTMLDialogElement ? event.target : null;
  if (!dialog || !dialog.matches(".delete-confirmation-dialog")) {
    return;
  }
  abortActiveDeleteRequest();
  if (dialogResult === "cancel" && activeDeleteTrigger instanceof HTMLElement) {
    activeDeleteTrigger.focus();
  }
  activeDeleteForm = null;
  activeDeleteSubmitter = null;
  activeDeleteTrigger = null;
}, true);

window.addEventListener("pageshow", resetDeleteSubmissions);
