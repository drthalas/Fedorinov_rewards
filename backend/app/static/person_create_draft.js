(function () {
  "use strict";

  function jsonRequest(url, options) {
    return fetch(url, options).then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok !== true) {
        throw new Error(payload.message || "Не удалось сохранить черновик.");
      }
      return payload;
    });
  }

  function setBusy(control, busy) {
    if (!control) return;
    control.disabled = busy;
    control.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function initDraft(root) {
    const scopes = root.querySelectorAll("[data-person-draft]");
    if (!scopes.length) return;
    const token = scopes[0].dataset.draftToken;
    if (!token) return;

    root.querySelectorAll("[data-draft-cancel-link]").forEach((link) => {
      link.addEventListener("click", async (event) => {
        event.preventDefault();
        const target = link.href;
        setBusy(link, true);
        try {
          const body = new URLSearchParams({ return_to: new URL(target).pathname + new URL(target).search });
          await fetch(`/persons/new/draft/${token}/cancel`, { method: "POST", body });
        } finally {
          window.location.href = target;
        }
      });
    });

    root.querySelectorAll("[data-draft-photo-trigger]").forEach((button) => {
      const card = button.closest("[data-draft-photo-card]");
      const input = card && card.querySelector("[data-draft-photo-input]");
      if (!input) return;
      button.addEventListener("click", () => input.click());
      input.addEventListener("change", async () => {
        const file = input.files && input.files[0];
        if (!file) return;
        const error = card.querySelector("[data-draft-photo-error]");
        const form = new FormData();
        form.append("photo_field", input.dataset.photoField || "");
        form.append("file", file);
        setBusy(button, true);
        if (error) error.hidden = true;
        try {
          const payload = await jsonRequest(`/persons/new/draft/${token}/photos`, { method: "POST", body: form });
          const image = card.querySelector("[data-draft-photo-image]");
          const placeholder = card.querySelector("[data-draft-photo-placeholder]");
          const clear = card.querySelector("[data-draft-photo-clear]");
          image.src = `${payload.url}?v=${Date.now()}`;
          image.hidden = false;
          placeholder.hidden = true;
          clear.hidden = false;
          card.classList.remove("placeholder-card");
        } catch (failure) {
          if (error) { error.textContent = failure.message; error.hidden = false; }
        } finally {
          input.value = "";
          setBusy(button, false);
        }
      });
    });

    root.querySelectorAll("[data-draft-photo-clear]").forEach((button) => {
      button.addEventListener("click", async () => {
        const card = button.closest("[data-draft-photo-card]");
        setBusy(button, true);
        try {
          await jsonRequest(`/persons/new/draft/${token}/photos/${button.dataset.photoField}/clear`, { method: "POST" });
          card.querySelector("[data-draft-photo-image]").hidden = true;
          card.querySelector("[data-draft-photo-placeholder]").hidden = false;
          card.classList.add("placeholder-card");
          button.hidden = true;
        } finally {
          setBusy(button, false);
        }
      });
    });

    const open = root.querySelector("[data-draft-reward-open]");
    const form = root.querySelector("[data-draft-reward-form]");
    const close = root.querySelector("[data-draft-reward-close]");
    const rows = root.querySelector("[data-draft-reward-rows]");
    const table = root.querySelector("[data-draft-reward-table]");
    if (open && form && rows && table) {
      open.addEventListener("click", () => { form.hidden = false; form.querySelector("select").focus(); });
      close.addEventListener("click", () => { form.reset(); form.hidden = true; });
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const submit = form.querySelector("button[type='submit']");
        const error = form.querySelector("[data-draft-reward-error]");
        setBusy(submit, true);
        if (error) error.hidden = true;
        try {
          const payload = await jsonRequest(`/persons/new/draft/${token}/rewards`, { method: "POST", body: new FormData(form) });
          const row = document.createElement("tr");
          row.dataset.draftRewardIndex = String(payload.index);
          row.innerHTML = `<td></td><td></td><td><button class="mini-button danger" type="button" data-draft-reward-remove>×</button></td>`;
          row.cells[0].textContent = payload.name;
          row.cells[1].textContent = payload.number == null ? "—" : String(payload.number);
          rows.appendChild(row);
          table.hidden = false;
          form.reset();
          form.hidden = true;
        } catch (failure) {
          if (error) { error.textContent = failure.message; error.hidden = false; }
        } finally {
          setBusy(submit, false);
        }
      });
      rows.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-draft-reward-remove]");
        const row = button && button.closest("[data-draft-reward-index]");
        if (!row) return;
        setBusy(button, true);
        try {
          await jsonRequest(`/persons/new/draft/${token}/rewards/${row.dataset.draftRewardIndex}/remove`, { method: "POST" });
          row.remove();
          Array.from(rows.children).forEach((item, index) => { item.dataset.draftRewardIndex = String(index); });
          if (!rows.children.length) table.hidden = true;
        } finally {
          setBusy(button, false);
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => initDraft(document));
})();
