(function () {
  "use strict";

  const root = document.querySelector("[data-media-optimization]");
  if (!root) return;

  const statusUrl = root.dataset.statusUrl;
  const message = root.querySelector("[data-operation-message]");
  const progress = root.querySelector("[data-operation-progress]");
  const percent = root.querySelector("[data-operation-percent]");
  const label = root.querySelector("[data-operation-label]");
  const detail = root.querySelector("[data-operation-detail]");
  const cancelForm = root.querySelector("[data-cancel-form]");
  let pollTimer = null;
  let observedRunning = root.querySelector("[data-operation-state]")?.dataset.operationState === "running";

  root.querySelectorAll("[data-optimization-form]:not([data-cancel-form]) button").forEach((button) => {
    button.dataset.defaultDisabled = String(button.disabled);
  });

  function showMessage(text, isError) {
    if (!message) return;
    message.textContent = text;
    message.hidden = !text;
    message.classList.toggle("is-error", Boolean(isError));
    message.classList.toggle("is-success", Boolean(text) && !isError);
  }

  function setFormsDisabled(disabled) {
    root.querySelectorAll("[data-optimization-form]:not([data-cancel-form]) button").forEach((button) => {
      button.disabled = disabled || button.dataset.defaultDisabled === "true";
    });
  }

  function updateOperation(snapshot) {
    const operation = snapshot.operation || { state: "idle" };
    const running = operation.state === "running";
    const value = Number(operation.percent || 0);
    if (progress) progress.value = value;
    if (percent) percent.textContent = `${value}%`;
    if (detail) {
      detail.textContent = operation.total
        ? `Обработано ${operation.processed || 0} из ${operation.total}`
        : "Статус обновляется автоматически.";
    }
    if (label) {
      if (running) label.textContent = "Операция выполняется. Можно оставить этот экран открытым.";
      else if (operation.state === "complete") label.textContent = "Операция завершена.";
      else if (["cancelled", "interrupted"].includes(operation.state)) {
        label.textContent = operation.message || "Операция остановлена безопасно. Запустите действие заново.";
      }
      else if (operation.state === "error") label.textContent = operation.message || "Операция завершилась с ошибкой.";
      else label.textContent = "Нет активной операции.";
    }
    if (cancelForm) cancelForm.hidden = !running;
    setFormsDisabled(running);
    if (running) observedRunning = true;
    if (!running && observedRunning) {
      window.location.reload();
      return;
    }
    if (running) schedulePoll();
  }

  async function readStatus() {
    try {
      const response = await fetch(statusUrl, { cache: "no-store", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      showMessage("", false);
      updateOperation(await response.json());
    } catch (error) {
      setFormsDisabled(observedRunning);
      showMessage("Не удалось обновить статус. Повторите попытку.", true);
      if (observedRunning) schedulePoll();
    }
  }

  function schedulePoll() {
    if (pollTimer !== null) return;
    pollTimer = window.setTimeout(() => {
      pollTimer = null;
      readStatus();
    }, 1000);
  }

  root.querySelectorAll("[data-optimization-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const button = form.querySelector("button[type='submit']");
      const oldText = button ? button.textContent : "";
      if (button) {
        button.disabled = true;
        button.textContent = form.dataset.pendingLabel || "Выполняем…";
      }
      showMessage(form.dataset.pendingLabel || "Выполняем…", false);
      try {
        const response = await fetch(form.action, { method: "POST", body: new FormData(form) });
        const finalUrl = new URL(response.url, window.location.href);
        const error = finalUrl.searchParams.get("error");
        if (!response.ok || error) throw new Error(error || `HTTP ${response.status}`);
        if (form.hasAttribute("data-reload-after")) {
          window.location.reload();
          return;
        }
        observedRunning = !form.hasAttribute("data-cancel-form");
        await readStatus();
      } catch (error) {
        showMessage(error.message || "Операция не запущена. Повторите попытку.", true);
        if (button) {
          button.textContent = oldText;
          button.disabled = false;
        }
      } finally {
        if (button && !observedRunning) {
          button.textContent = oldText;
          button.disabled = false;
        }
      }
    });
  });

  if (observedRunning) schedulePoll();
})();
