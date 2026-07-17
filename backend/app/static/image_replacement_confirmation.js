(function () {
  "use strict";

  var dialog = null;
  var pendingAction = null;
  var pendingTrigger = null;

  function focusWithoutScroll(element) {
    if (!element || typeof element.focus !== "function") return;
    try {
      element.focus({ preventScroll: true });
    } catch (error) {
      element.focus();
    }
  }

  function isOccupied(element) {
    return element && element.getAttribute("data-image-slot-occupied") === "true";
  }

  function setOccupied(element, occupied) {
    if (!element) return;
    element.setAttribute("data-image-slot-occupied", occupied ? "true" : "false");
  }

  function closeDialog(restoreFocus) {
    if (!dialog) return;
    var trigger = pendingTrigger;
    dialog.hidden = true;
    pendingAction = null;
    pendingTrigger = null;
    if (restoreFocus) focusWithoutScroll(trigger);
  }

  function cancelReplacement() {
    closeDialog(true);
  }

  function confirmReplacement() {
    var action = pendingAction;
    closeDialog(false);
    if (typeof action === "function") action();
  }

  function trapFocus(event) {
    if (!dialog || dialog.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      cancelReplacement();
      return;
    }
    if (event.key !== "Tab") return;
    var controls = dialog.querySelectorAll("button");
    if (!controls.length) return;
    var first = controls[0];
    var last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("div");
    dialog.className = "image-replace-dialog";
    dialog.hidden = true;
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "image-replace-dialog-title");
    dialog.setAttribute("aria-describedby", "image-replace-dialog-description");
    dialog.innerHTML = [
      '<div class="image-replace-dialog-panel">',
      '<h2 id="image-replace-dialog-title">Заменить изображение?</h2>',
      '<p id="image-replace-dialog-description">После успешной замены старый файл будет удалён, если он больше нигде не используется.</p>',
      '<div class="image-replace-dialog-actions">',
      '<button type="button" class="secondary-button" data-image-replace-cancel>Отмена</button>',
      '<button type="button" data-image-replace-confirm>Заменить</button>',
      "</div>",
      "</div>",
    ].join("");
    dialog.querySelector("[data-image-replace-cancel]").addEventListener("click", cancelReplacement);
    dialog.querySelector("[data-image-replace-confirm]").addEventListener("click", confirmReplacement);
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) cancelReplacement();
    });
    document.addEventListener("keydown", trapFocus, true);
    document.body.appendChild(dialog);
    return dialog;
  }

  function run(trigger, action) {
    if (!isOccupied(trigger)) {
      action();
      return false;
    }
    var activeDialog = ensureDialog();
    pendingTrigger = trigger;
    pendingAction = action;
    activeDialog.hidden = false;
    focusWithoutScroll(activeDialog.querySelector("[data-image-replace-cancel]"));
    return true;
  }

  window.FedorinovImageReplacement = Object.freeze({
    isOccupied: isOccupied,
    run: run,
    setOccupied: setOccupied,
  });
})();
