function setInputValue(form, name, value) {
  const input = form.querySelector(`input[name="${name}"]`);
  if (input) {
    input.value = value;
  }
}

document.addEventListener(
  "submit",
  (event) => {
    const form = event.target instanceof HTMLFormElement ? event.target : null;
    if (!form || !form.matches("[data-confirm-submit]")) {
      return;
    }

    const message = form.dataset.confirmMessage || "Подтвердите действие.";
    if (!window.confirm(message)) {
      setInputValue(form, "confirm", "");
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }

    setInputValue(form, "confirm", "true");
    if (form.dataset.confirmSubmit === "reward-delete") {
      setInputValue(form, "delete_reward_confirm", "true");
    }
  },
  true
);
