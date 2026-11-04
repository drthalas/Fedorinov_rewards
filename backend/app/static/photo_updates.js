/* Notify other open galleries only after a confirmed photo mutation. */
(() => {
  "use strict";
  if (!document.querySelector("[data-person-gallery], [data-photo-editor-slot]")) return;
  let channel;
  const connect = () => {
    try { channel = new BroadcastChannel("fedorinov:photo-updates"); channel.onmessage = changed; } catch (_) {}
  };
  const changed = () => window.dispatchEvent(new Event("photos:changed"));
  const notify = () => { changed(); channel?.postMessage("saved"); };
  connect();
  window.addEventListener("pagehide", () => { channel?.close(); channel = null; });
  window.addEventListener("pageshow", event => { if (event.persisted) connect(); });
  document.addEventListener("photo-editor:saved", event => {
    if (event.target.closest('[data-photo-edit-kind="draft"]')) return;
    notify();
  });
  document.addEventListener("submit", async event => {
    const form = event.target;
    if (!form.matches('form.photo-upload-form[action="/photos/upload"]')) return;
    event.preventDefault();
    const data = new FormData(form), feedback = window.FedorinovWriteFeedback;
    if (!feedback?.begin(form, event.submitter, "Сохраняем фото…")) return;
    window.FedorinovPersonEditDraft?.captureForPhoto(form.querySelector("[data-photo-plus-trigger]"));
    const error = form.closest(".photo-manage-actions").querySelector("[data-photo-source-error]");
    error.hidden = true;
    try {
      const response = await fetch(form.action, { method: "POST", body: data, credentials: "same-origin" });
      const target = new URL(response.url, location.href);
      const confirmed = ["photo_updated", "photo_cleared"].includes(target.searchParams.get("status")) || target.searchParams.get("media_cleanup") === "failed";
      if (!response.ok || !response.redirected || !confirmed) throw new Error();
      notify();
      location.assign(target.href);
    } catch (_) {
      // Keep the previous image/placeholder. A lost response is not evidence
      // of either success or rollback; never repeat an upload automatically.
      error.textContent = "Не удалось подтвердить сохранение фото. Обновите страницу для проверки; файл повторно не отправлялся.";
      error.hidden = false;
      feedback.finish(form, { state: "error" });
      form.querySelector('input[type="file"]').value = "";
    }
  });
  // Capture the confirmed redirect before transient toasts consume its marker.
  const params = new URLSearchParams(location.search);
  if (["photo_updated", "photo_cleared"].includes(params.get("status")) || params.get("media_cleanup") === "failed") notify();
})();
