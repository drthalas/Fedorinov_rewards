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

  function draftPhotoError(card) {
    return card && card.querySelector("[data-draft-photo-error]");
  }

  function clearDraftPhotoError(card) {
    const error = draftPhotoError(card);
    if (!error) return;
    error.textContent = "";
    error.hidden = true;
  }

  function showDraftPhotoError(card, message) {
    const error = draftPhotoError(card);
    if (!error) return;
    error.textContent = message || "Не удалось сохранить фотографию.";
    error.hidden = false;
  }

  function applyDraftPhoto(card, payload) {
    const image = card.querySelector("[data-draft-photo-image]");
    const placeholder = card.querySelector("[data-draft-photo-placeholder]");
    const clear = card.querySelector("[data-draft-photo-clear]");
    image.src = `${payload.url}?v=${Date.now()}`;
    image.hidden = false;
    placeholder.hidden = true;
    clear.hidden = false;
    card.classList.remove("placeholder-card");
  }

  async function uploadDraftPhoto(photoBase, photoField, file) {
    const form = new FormData();
    form.append("photo_field", photoField || "");
    form.append("file", file, file.name || "clipboard.jpg");
    return jsonRequest(photoBase, { method: "POST", body: form });
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
      const photoScope = button.closest("[data-draft-photo-base]");
      const photoBase = photoScope && photoScope.dataset.draftPhotoBase;
      if (!input || !photoBase) return;
      button.addEventListener("click", async () => {
        const helper = window.FedorinovClipboardImages;
        if (!helper || typeof helper.readWithTimeout !== "function") {
          input.click();
          return;
        }
        if (!helper.beginFeedback(button)) return;
        clearDraftPhotoError(card);
        let clipboardImage;
        try {
          clipboardImage = await helper.readWithTimeout(helper.attemptTimeoutMs);
        } catch (_error) {
          helper.endFeedback(button);
          input.click();
          return;
        }
        helper.rememberPending(clipboardImage, []);
        try {
          const payload = await uploadDraftPhoto(photoBase, button.dataset.photoField, clipboardImage.blob);
          helper.consumePending(clipboardImage.fingerprint);
          applyDraftPhoto(card, payload);
        } catch (failure) {
          helper.clearPending(clipboardImage.fingerprint);
          showDraftPhotoError(card, failure.message);
        } finally {
          helper.endFeedback(button);
        }
      });
      input.addEventListener("change", async () => {
        const file = input.files && input.files[0];
        if (!file) return;
        setBusy(button, true);
        clearDraftPhotoError(card);
        try {
          const payload = await uploadDraftPhoto(photoBase, input.dataset.photoField, file);
          applyDraftPhoto(card, payload);
        } catch (failure) {
          showDraftPhotoError(card, failure.message);
        } finally {
          input.value = "";
          setBusy(button, false);
        }
      });
    });

    root.querySelectorAll("[data-draft-photo-clear]").forEach((button) => {
      button.addEventListener("click", async () => {
        const card = button.closest("[data-draft-photo-card]");
        const photoScope = button.closest("[data-draft-photo-base]");
        const photoBase = photoScope && photoScope.dataset.draftPhotoBase;
        const error = card && card.querySelector("[data-draft-photo-error]");
        if (!photoBase) return;
        setBusy(button, true);
        if (error) error.hidden = true;
        try {
          await jsonRequest(`${photoBase}/${button.dataset.photoField}/clear`, { method: "POST" });
          card.querySelector("[data-draft-photo-image]").hidden = true;
          card.querySelector("[data-draft-photo-placeholder]").hidden = false;
          card.classList.add("placeholder-card");
          button.hidden = true;
        } catch (failure) {
          if (error) { error.textContent = failure.message; error.hidden = false; }
        } finally {
          setBusy(button, false);
        }
      });
    });

    const rows = root.querySelector("[data-draft-reward-rows]");
    const table = root.querySelector("[data-draft-reward-table]");
    if (rows && table) {
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
