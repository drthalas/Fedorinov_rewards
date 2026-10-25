(() => {
  "use strict";

  function initialize() {
    const dialog = document.getElementById("bio-manual-dialog");
    const content = dialog?.querySelector("[data-manual-content]");
    let opener = null;
    let draft = null;
    const notice = document.querySelector("[data-review-list-result]");
    function announce(message) {
      if (!notice) return;
      notice.textContent = message;
      notice.hidden = false;
    }
    function updateChoices() {
      const form = content?.querySelector("[data-manual-plan]");
      if (!form) return;
      const save = form.querySelector("[data-review-save]");
      if (save) save.disabled = !form.querySelector("input[type=radio]:checked");
      form.querySelectorAll("[data-review-field]").forEach((field) => {
        field.querySelector("[data-review-reset]").hidden = !field.querySelector("input:checked");
      });
    }
    function focusPanel() {
      if (!content.querySelector("h2")) {
        const heading = document.createElement("h2");
        heading.id = "bio-manual-title";
        heading.tabIndex = -1;
        heading.textContent = "Проверка строки";
        content.prepend(heading);
      }
      content.querySelector("h2").focus();
      dialog.scrollTop = 0;
    }
    async function loadPanel(url, options) {
      const response = await fetch(url, { ...options, credentials: "same-origin" });
      if (!response.headers.get("content-type")?.includes("text/html")) throw new Error("Неожиданный ответ сервера");
      content.innerHTML = await response.text();
      focusPanel();
      updateChoices();
      return response;
    }
    async function openPerson(button) {
      opener = button;
      draft = null;
      if (!dialog.open) dialog.showModal();
      content.textContent = "Открываем кавалера…";
      try { await loadPanel(button.dataset.manualOpen); }
      catch { content.textContent = "Не удалось открыть проверку. Вернитесь к списку и попробуйте ещё раз."; focusPanel(); }
    }
    function advance(message) {
      announce(message);
      const people = Array.from(document.querySelectorAll("[data-manual-person]"));
      const current = people.indexOf(opener);
      const following = [...people.slice(current + 1), ...people.slice(0, Math.max(0, current))];
      const next = following.find((button) => button.dataset.reviewResolved !== "true");
      if (next) void openPerson(next);
      else dialog.close();
    }
    document.querySelectorAll("[data-manual-open]").forEach((button) => {
      button.addEventListener("click", () => void openPerson(button));
    });
    dialog?.addEventListener("close", () => opener?.focus({ preventScroll: true }));
    dialog?.querySelector("[data-manual-close]").addEventListener("click", () => dialog.close());
    content?.addEventListener("change", updateChoices);
    content?.addEventListener("click", (event) => {
      const option = event.target.closest(".review-option");
      if (option && !event.target.closest("input, label, details, button, a")) {
        const radio = option.querySelector("input[type=radio]");
        if (radio && !radio.disabled) radio.click();
      }
      if (event.target.closest("[data-manual-close]")) { dialog.close(); return; }
      if (event.target.closest("[data-manual-skip]")) { advance("Кавалер пропущен. Данные не изменены."); return; }
      if (event.target.closest("[data-manual-next]")) { advance("Выбор сохранён. Можно проверить следующего кавалера."); return; }
      const reset = event.target.closest("[data-review-reset]");
      if (reset) {
        reset.closest("[data-review-field]").querySelectorAll("input[type=radio]").forEach((input) => { input.checked = false; });
        updateChoices();
        return;
      }
      if (!event.target.closest("[data-manual-undo]") || !draft) return;
      content.replaceChildren(...draft);
      draft = null;
      focusPanel();
      updateChoices();
    });
    content?.addEventListener("submit", async (event) => {
      const form = event.target;
      if (form.matches("[data-manual-history]")) {
        event.preventDefault();
        const url = new URL(form.action);
        const id = new FormData(form).get("person_id");
        if (id) url.searchParams.set("person_id", id);
        try { await loadPanel(url); }
        catch { content.prepend("История недоступна. Закройте панель и повторите попытку."); }
        return;
      }
      if (!form.matches("[data-manual-plan], [data-manual-commit]")) return;
      event.preventDefault();
      const data = new FormData(form);
      const isPlan = form.matches("[data-manual-plan]");
      const prior = Array.from(content.childNodes);
      const submit = form.querySelector("button[type=submit]");
      submit.disabled = true;
      try {
        const response = await loadPanel(form.action, { method: "POST", body: data });
        if (isPlan) draft = prior;
        if (!response.ok) {
          // Restore the actual form nodes, retaining all typed proposals/decisions.
          const errors = Array.from(content.querySelectorAll("[role=alert]"));
          content.replaceChildren(...prior);
          content.prepend(...errors);
          content.querySelector("[role=alert]")?.setAttribute("tabindex", "-1");
          content.querySelector("[role=alert]")?.focus();
        } else if (content.querySelector("[data-manual-result]") && opener) {
          const status = opener.closest("tr")?.querySelector("[data-manual-row-status]");
          if (status) {
            status.textContent = content.querySelector("[data-manual-result]").textContent;
            status.hidden = false;
          }
          opener.dataset.reviewResolved = content.querySelector("[data-manual-result]").dataset.reviewComplete;
          announce(content.querySelector("[data-manual-result]").textContent);
        }
      } catch {
        content.replaceChildren(...prior);
        const error = document.createElement("p");
        error.setAttribute("role", "alert");
        error.textContent = "Связь прервана. Повторите этот же запрос: история предотвращает повторную запись. Решения сохранены в форме.";
        content.prepend(error);
      } finally { submit.disabled = false; }
    });

    document.querySelectorAll("[data-bio-file-picker]").forEach((area) => {
      const input = area.querySelector("input[type=file]");
      const filename = area.querySelector("[data-bio-file-name]");
      const error = area.querySelector("[data-bio-file-error]");
      if (!input || !filename || !error) return;
      const update = () => {
        filename.textContent = input.files.length ? input.files[0].name : "";
        filename.hidden = !filename.textContent;
        error.textContent = "";
        error.hidden = true;
        input.removeAttribute("aria-invalid");
      };
      input.addEventListener("change", update);
      input.addEventListener("cancel", update);
      input.addEventListener("invalid", (event) => {
        event.preventDefault();
        error.textContent = "Выберите файл данных в формате .xlsx.";
        error.hidden = false;
        input.setAttribute("aria-invalid", "true");
        input.focus();
      });
      if (input.form) input.form.addEventListener("reset", () => queueMicrotask(update));
      update();
    });

    document.querySelectorAll("[data-bio-result-link]").forEach((link) => {
      const group = document.getElementById(link.getAttribute("aria-controls"));
      if (!group || !group.classList.contains("bio-result-group")) return;
      const summary = group.querySelector("summary");
      const synchronize = () => link.setAttribute("aria-expanded", String(group.open));
      group.addEventListener("toggle", synchronize);
      link.addEventListener("click", (event) => {
        if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        group.open = true;
        const rows = group.querySelector(".bio-results");
        if (rows) rows.scrollTop = 0;
        if (summary) summary.focus({ preventScroll: true });
        group.scrollIntoView({ block: "start", behavior: "auto" });
        synchronize();
      });
      synchronize();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
