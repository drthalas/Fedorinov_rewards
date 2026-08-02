(() => {
  "use strict";

  const activeForms = new Set();
  const formStates = new WeakMap();
  let overlay = null;
  let overlayTimer = null;

  function ensureOverlay() {
    if (overlay && overlay.isConnected !== false) return overlay;
    overlay = document.createElement("div");
    overlay.className = "write-operation-overlay";
    overlay.dataset.writeOperationOverlay = "true";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.setAttribute("aria-atomic", "true");
    overlay.hidden = true;

    const spinner = document.createElement("span");
    spinner.className = "write-operation-spinner";
    spinner.setAttribute("aria-hidden", "true");
    const message = document.createElement("span");
    message.dataset.writeOperationMessage = "true";
    overlay.append(spinner, message);
    document.body.append(overlay);
    return overlay;
  }

  function showOverlay(message, state = "pending") {
    const element = ensureOverlay();
    if (overlayTimer !== null) {
      window.clearTimeout(overlayTimer);
      overlayTimer = null;
    }
    element.dataset.writeOperationState = state;
    element.querySelector("[data-write-operation-message]").textContent = message;
    element.hidden = false;
  }

  function hideOverlay() {
    if (overlay) overlay.hidden = true;
  }

  function showStatus(message, state = "pending") {
    showOverlay(message || "Выполняем…", state);
  }

  function hideStatus() {
    hideOverlay();
  }

  function relatedControls(form) {
    const controls = new Set(form.querySelectorAll("button, input[type='submit']"));
    const photoCard = form.closest && form.closest(".photo-manage-card");
    if (photoCard) {
      photoCard.querySelectorAll("button, input[type='submit']").forEach((control) => controls.add(control));
    }
    return Array.from(controls);
  }

  function feedbackError(form) {
    const local = form.querySelector("[data-write-feedback-error]");
    if (local) return local;
    const actions = form.closest && form.closest(".photo-manage-actions");
    return actions ? actions.querySelector("[data-photo-source-error]") : null;
  }

  function clearError(form) {
    const error = feedbackError(form);
    if (!error) return;
    error.textContent = "";
    error.hidden = true;
  }

  function begin(form, submitter, message) {
    if (!form || formStates.has(form)) return false;
    const pendingMessage = message || form.dataset.writePendingLabel || "Сохраняем…";
    const controls = relatedControls(form).map((control) => ({
      control,
      disabled: Boolean(control.disabled),
      ariaDisabled: control.getAttribute("aria-disabled"),
    }));
    const activeSubmitter = submitter || form.querySelector("button[type='submit'], input[type='submit']");
    const submitterText = activeSubmitter && "textContent" in activeSubmitter ? activeSubmitter.textContent : null;
    const submitterAriaLabel = activeSubmitter ? activeSubmitter.getAttribute("aria-label") : null;

    formStates.set(form, { controls, submitter: activeSubmitter, submitterText, submitterAriaLabel });
    activeForms.add(form);
    clearError(form);
    form.dataset.writeSubmitting = "true";
    form.setAttribute("aria-busy", "true");
    controls.forEach(({ control }) => {
      control.disabled = true;
      control.setAttribute("aria-disabled", "true");
    });
    if (activeSubmitter) {
      activeSubmitter.dataset.writeBusy = "true";
      activeSubmitter.setAttribute("aria-label", pendingMessage);
      if (activeSubmitter.dataset.writeCompact !== "true" && "textContent" in activeSubmitter) {
        activeSubmitter.textContent = pendingMessage;
      }
    }
    showOverlay(pendingMessage, "pending");
    return true;
  }

  function restore(form) {
    const state = formStates.get(form);
    if (!state) return;
    state.controls.forEach(({ control, disabled, ariaDisabled }) => {
      control.disabled = disabled;
      if (ariaDisabled === null) control.removeAttribute("aria-disabled");
      else control.setAttribute("aria-disabled", ariaDisabled);
    });
    if (state.submitter) {
      delete state.submitter.dataset.writeBusy;
      if (state.submitterAriaLabel === null) state.submitter.removeAttribute("aria-label");
      else state.submitter.setAttribute("aria-label", state.submitterAriaLabel);
      if (state.submitter.dataset.writeCompact !== "true" && state.submitterText !== null) {
        state.submitter.textContent = state.submitterText;
      }
    }
    delete form.dataset.writeSubmitting;
    form.removeAttribute("aria-busy");
    formStates.delete(form);
    activeForms.delete(form);
  }

  function finish(form, options = {}) {
    restore(form);
    const message = String(options.message || "");
    const state = options.state === "error" ? "error" : "success";
    if (!message) {
      hideOverlay();
      return;
    }
    if (state === "error") {
      const error = feedbackError(form);
      if (error) {
        error.textContent = message;
        error.hidden = false;
      }
    }
    showOverlay(message, state);
    overlayTimer = window.setTimeout(hideOverlay, state === "error" ? 8000 : 4000);
  }

  function resetAll() {
    Array.from(activeForms).forEach(restore);
    hideOverlay();
  }

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form || !form.matches || !form.matches("form[data-write-feedback]")) return;
    if (formStates.has(form)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    if (event.defaultPrevented) return;
    begin(form, event.submitter || null);
  });

  window.addEventListener("pageshow", resetAll);
  window.FedorinovWriteFeedback = Object.freeze({ begin, finish, hideStatus, resetAll, showStatus });
})();
