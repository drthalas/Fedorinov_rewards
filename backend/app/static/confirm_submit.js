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
    control.disabled = true;
    control.setAttribute("aria-disabled", "true");
  });
}

const DELETE_PREVIEW_TIMEOUT_MS = 15000;
const DELETE_PREVIEW_ERROR = "Не удалось проверить возможность удаления. Повторите попытку.";

function setDeletePreview(form, preview) {
  form.dataset.confirmMessage = String(preview.message || "Подтвердите удаление.");
  form.dataset.confirmBlocked = preview.blocked === true ? "true" : "false";
  setInputValue(form, "delete_operation_id", String(preview.operation_id || ""));
}

async function loadDeletePreview(form) {
  const url = form.dataset.confirmPreviewUrl;
  if (!url) {
    return;
  }
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), DELETE_PREVIEW_TIMEOUT_MS);
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
    const preview = await response.json();
    if (!preview || typeof preview.message !== "string" || typeof preview.blocked !== "boolean" || typeof preview.operation_id !== "string") {
      throw new Error("Invalid delete preview response.");
    }
    setDeletePreview(form, preview);
  } catch (_error) {
    setDeletePreview(form, {
      message: DELETE_PREVIEW_ERROR,
      blocked: true,
      operation_id: "",
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
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
let dialogResult = "cancel";

function focusableDialogControls(dialog) {
  return Array.from(dialog.querySelectorAll("button:not([hidden]):not([disabled])"));
}

function closeDeleteConfirmation(dialog, result = "cancel") {
  dialogResult = result;
  if (typeof dialog.close === "function" && dialog.open) {
    dialog.close();
  } else {
    dialog.removeAttribute("open");
    dialog.dispatchEvent(new Event("close"));
  }
}

function openDeleteConfirmation(form, submitter) {
  const dialog = document.querySelector(".delete-confirmation-dialog") || createDeleteConfirmationDialog();
  const blocked = form.dataset.confirmBlocked === "true";
  const title = dialog.querySelector("#delete-confirmation-title");
  const message = dialog.querySelector("#delete-confirmation-message");
  const cancelButton = dialog.querySelector("[data-delete-confirmation-cancel]");
  const confirmButton = dialog.querySelector("[data-delete-confirmation-confirm]");

  activeDeleteForm = form;
  activeDeleteSubmitter = submitter || null;
  activeDeleteTrigger = submitter || document.activeElement;
  dialogResult = "cancel";
  setDeleteConfirmation(form, false);

  title.textContent = form.dataset.confirmTitle || "Подтверждение удаления";
  message.textContent = form.dataset.confirmMessage || "Подтвердите действие.";
  confirmButton.hidden = blocked;
  confirmButton.disabled = blocked;
  cancelButton.textContent = blocked ? "Закрыть" : "Отмена";
  dialog.classList.toggle("delete-confirmation-blocked", blocked);

  if (dialog.open) {
    cancelButton.focus();
    return;
  }
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.setAttribute("open", "");
  }
  (blocked ? cancelButton : confirmButton).focus();
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
      disableDeleteSubmitters(form);
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    const submitter = event.submitter;
    if (!form.dataset.confirmPreviewUrl) {
      openDeleteConfirmation(form, submitter);
      return;
    }
    if (form.dataset.deletePreviewLoading === "true") {
      return;
    }
    form.dataset.deletePreviewLoading = "true";
    if (submitter instanceof HTMLElement) {
      submitter.setAttribute("aria-busy", "true");
    }
    loadDeletePreview(form).then(() => {
      openDeleteConfirmation(form, submitter);
    }).finally(() => {
      delete form.dataset.deletePreviewLoading;
      if (submitter instanceof HTMLElement) {
        submitter.removeAttribute("aria-busy");
      }
    });
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
  if (dialogResult === "cancel" && activeDeleteTrigger instanceof HTMLElement) {
    activeDeleteTrigger.focus();
  }
  activeDeleteForm = null;
  activeDeleteSubmitter = null;
  activeDeleteTrigger = null;
}, true);
