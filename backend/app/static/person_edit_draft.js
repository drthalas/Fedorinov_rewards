(() => {
  "use strict";

  const STORAGE_KEY = "fedorinov-person-edit-photo-draft-v1";
  const MAX_AGE_MS = 5 * 60 * 1000;

  function editForm() {
    return document.querySelector("form[data-person-edit-draft]");
  }

  function formValues(form) {
    const values = {};
    form.querySelectorAll("input[name], select[name], textarea[name]").forEach((control) => {
      if (control.disabled || control.type === "hidden" || control.type === "file") return;
      if ((control.type === "checkbox" || control.type === "radio") && !control.checked) return;
      values[control.name] = control.value;
    });
    return values;
  }

  function storageKey(personId) {
    return `${STORAGE_KEY}:${String(personId || "")}`;
  }

  function clearSnapshot(personId) {
    const activeForm = editForm();
    const activePersonId = personId || (activeForm && activeForm.dataset.personId) || "";
    if (!activePersonId) return;
    try {
      window.sessionStorage.removeItem(storageKey(activePersonId));
    } catch (error) {
      // Draft preservation is a progressive enhancement; form actions remain available.
    }
  }

  function captureForPhoto(trigger) {
    if (!trigger || trigger.getAttribute("data-entity-type") !== "person") return false;
    const form = editForm();
    if (!form || String(form.dataset.personId || "") !== trigger.getAttribute("data-entity-id")) return false;
    try {
      window.sessionStorage.setItem(storageKey(form.dataset.personId), JSON.stringify({
        pathname: window.location.pathname,
        personId: String(form.dataset.personId || ""),
        values: formValues(form),
        savedAt: Date.now(),
      }));
      return true;
    } catch (error) {
      return false;
    }
  }

  function hasPhotoResult() {
    const params = new URLSearchParams(window.location.search || "");
    return params.get("status") === "photo_updated" || params.get("media_cleanup") === "failed";
  }

  function restoreAfterPhoto(form) {
    if (!form || !hasPhotoResult()) return false;
    let snapshot;
    try {
      snapshot = JSON.parse(window.sessionStorage.getItem(storageKey(form.dataset.personId)) || "null");
    } catch (error) {
      clearSnapshot(form.dataset.personId);
      return false;
    }
    clearSnapshot(form.dataset.personId);
    if (
      !snapshot ||
      snapshot.pathname !== window.location.pathname ||
      snapshot.personId !== String(form.dataset.personId || "") ||
      Date.now() - Number(snapshot.savedAt || 0) > MAX_AGE_MS ||
      !snapshot.values
    ) {
      return false;
    }
    form.querySelectorAll("input[name], select[name], textarea[name]").forEach((control) => {
      if (!Object.prototype.hasOwnProperty.call(snapshot.values, control.name)) return;
      control.value = String(snapshot.values[control.name]);
      control.dispatchEvent(new Event("input", { bubbles: true }));
      control.dispatchEvent(new Event("change", { bubbles: true }));
    });
    return true;
  }

  function focusWithoutScroll(element) {
    if (!element || typeof element.focus !== "function") return;
    try {
      element.focus({ preventScroll: true });
    } catch (error) {
      element.focus();
    }
  }

  function initBiography(form) {
    const source = form && form.querySelector("[data-biography-draft]");
    const trigger = form && form.querySelector("[data-biography-expand]");
    const dialog = document.querySelector("[data-biography-dialog]");
    const expanded = dialog && dialog.querySelector("[data-biography-expanded-draft]");
    if (!source || !trigger || !dialog || !expanded) return;

    let draftValue = source.value;

    function setDraft(value, origin) {
      draftValue = String(value || "");
      if (origin !== source && source.value !== draftValue) source.value = draftValue;
      if (origin !== expanded && expanded.value !== draftValue) expanded.value = draftValue;
    }

    function close() {
      if (dialog.hidden) return;
      setDraft(expanded.value, expanded);
      dialog.hidden = true;
      document.body.classList.remove("biography-editor-open");
      trigger.setAttribute("aria-expanded", "false");
      focusWithoutScroll(trigger);
    }

    function open() {
      setDraft(source.value, source);
      dialog.hidden = false;
      document.body.classList.add("biography-editor-open");
      trigger.setAttribute("aria-expanded", "true");
      focusWithoutScroll(expanded);
    }

    source.addEventListener("input", () => setDraft(source.value, source));
    expanded.addEventListener("input", () => setDraft(expanded.value, expanded));
    trigger.addEventListener("click", open);
    dialog.querySelectorAll("[data-biography-close]").forEach((button) => button.addEventListener("click", close));
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) close();
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    });
    form.addEventListener("submit", () => setDraft(draftValue, expanded));
    setDraft(source.value, source);
  }

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form || !form.matches) return;
    if (form.matches("form[data-person-photo-upload]")) {
      const trigger = form.querySelector("[data-person-photo-trigger]");
      captureForPhoto(trigger);
    } else if (form.matches("form[data-person-edit-draft]")) {
      clearSnapshot();
    }
  });

  document.addEventListener("click", (event) => {
    const target = event.target && event.target.closest ? event.target.closest("a[data-escape-back]") : null;
    if (target && editForm()) clearSnapshot();
  });

  function init() {
    const form = editForm();
    restoreAfterPhoto(form);
    initBiography(form);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  window.FedorinovPersonEditDraft = Object.freeze({ captureForPhoto, clear: clearSnapshot });
})();
