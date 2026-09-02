(function () {
  const trigger = document.querySelector("[data-summary-pdf-options-open]");
  const dialog = document.querySelector("[data-summary-pdf-options-dialog]");
  const form = document.querySelector("#summary-pdf-save-form");
  const selectedInput = form && form.querySelector("[data-summary-pdf-media-columns]");
  if (!(trigger instanceof HTMLButtonElement) || !(dialog instanceof HTMLDialogElement) || !(form instanceof HTMLFormElement) || !(selectedInput instanceof HTMLInputElement)) {
    return;
  }

  const closeDialog = function () {
    if (dialog.open && typeof dialog.close === "function") {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
    trigger.focus();
  };

  trigger.addEventListener("click", function (event) {
    event.preventDefault();
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  });

  dialog.querySelector("[data-summary-pdf-options-cancel]").addEventListener("click", closeDialog);
  dialog.querySelector("[data-summary-pdf-options-confirm]").addEventListener("click", function () {
    selectedInput.value = Array.from(dialog.querySelectorAll("[data-summary-pdf-media-option]:checked"))
      .map(function (input) { return input.value; })
      .join(",");
    closeDialog();
    form.requestSubmit(trigger);
  });
  dialog.addEventListener("cancel", function (event) {
    event.preventDefault();
    closeDialog();
  });
})();
