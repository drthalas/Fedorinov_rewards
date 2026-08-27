(() => {
  "use strict";

  const STORAGE_KEY = "fedorinov-person-edit-photo-draft-v1";
  const MAX_AGE_MS = 5 * 60 * 1000;

  function editForm() {
    return document.querySelector("form[data-person-edit-draft]");
  }

  function formState(form) {
    const values = {};
    const checked = {};
    form.querySelectorAll("input[name], select[name], textarea[name]").forEach((control) => {
      if (control.disabled || control.type === "hidden" || control.type === "file") return;
      if (control.type === "checkbox") {
        checked[control.name] = Boolean(control.checked);
        values[control.name] = control.value;
        return;
      }
      if (control.type === "radio") {
        if (!Object.prototype.hasOwnProperty.call(checked, control.name)) checked[control.name] = "";
        if (!control.checked) return;
        checked[control.name] = control.value;
      }
      values[control.name] = control.value;
    });
    return { values, checked };
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

  function captureForPerson(personId) {
    const form = editForm();
    if (!form || String(form.dataset.personId || "") !== String(personId || "")) return false;
    const state = formState(form);
    try {
      window.sessionStorage.setItem(storageKey(form.dataset.personId), JSON.stringify({
        pathname: window.location.pathname,
        personId: String(form.dataset.personId || ""),
        values: state.values,
        checked: state.checked,
        savedAt: Date.now(),
      }));
      return true;
    } catch (error) {
      return false;
    }
  }

  function captureForPhoto(trigger) {
    if (!trigger || trigger.getAttribute("data-entity-type") !== "person") return false;
    return captureForPerson(trigger.getAttribute("data-entity-id"));
  }

  function captureForPhotoForm(photoForm) {
    if (!photoForm || String(photoForm.dataset.personId || "") === "") return false;
    return captureForPerson(photoForm.dataset.personId);
  }

  function hasPhotoResult() {
    const params = new URLSearchParams(window.location.search || "");
    return params.get("status") === "photo_updated" ||
      params.get("status") === "photo_cleared" ||
      params.get("media_cleanup") === "failed";
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
      let restored = false;
      if (control.type === "checkbox" && snapshot.checked && Object.prototype.hasOwnProperty.call(snapshot.checked, control.name)) {
        control.checked = Boolean(snapshot.checked[control.name]);
        restored = true;
      } else if (control.type === "radio" && snapshot.checked && Object.prototype.hasOwnProperty.call(snapshot.checked, control.name)) {
        control.checked = String(snapshot.checked[control.name]) === String(control.value);
        restored = true;
      } else if (Object.prototype.hasOwnProperty.call(snapshot.values, control.name)) {
        control.value = String(snapshot.values[control.name]);
        restored = true;
      }
      if (!restored) return;
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
    if (form.matches("form[data-person-photo-upload]") || form.matches("form[data-person-photo-mutation]")) {
      captureForPhotoForm(form);
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
