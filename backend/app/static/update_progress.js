(function () {
  "use strict";

  var POLL_INTERVAL_MS = 750;
  var UPDATE_TIMEOUT_MS = 15 * 60 * 1000;

  function setHidden(element, hidden) {
    if (element) {
      element.hidden = hidden;
    }
  }

  function updateSteps(progress, currentStep, status) {
    var items = Array.prototype.slice.call(progress.querySelectorAll("[data-update-step]"));
    var currentSeen = false;
    items.forEach(function (item) {
      var step = item.getAttribute("data-update-step");
      item.classList.remove("is-current", "is-done", "is-error");
      if (status === "error") {
        item.classList.add("is-error");
        return;
      }
      if (step === currentStep) {
        item.classList.add(status === "success" ? "is-done" : "is-current");
        currentSeen = true;
      } else if (!currentSeen) {
        item.classList.add("is-done");
      }
    });
  }

  function renderStatus(progress, data) {
    var message = progress.querySelector("[data-update-message]");
    var error = progress.querySelector("[data-update-error]");
    updateSteps(progress, data.step || "checking", data.status || "running");
    if (message) {
      message.textContent = data.message || "";
    }
    if (error) {
      error.textContent = data.error || "";
      setHidden(error, !data.error);
    }
  }

  function delay(milliseconds) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, milliseconds);
    });
  }

  async function fetchJson(url, options) {
    var response = await fetch(url, options || { headers: { "Accept": "application/json" } });
    if (!response.ok) {
      var body = await response.json().catch(function () { return {}; });
      var failure = new Error(body.error || body.detail || "HTTP " + response.status);
      failure.httpStatus = response.status;
      throw failure;
    }
    return response.json();
  }

  async function waitForFinishedUpdate(progress) {
    var deadline = Date.now() + UPDATE_TIMEOUT_MS;
    while (Date.now() < deadline) {
      try {
        var status = await fetchJson("/updates/status", {
          headers: { "Accept": "application/json", "Cache-Control": "no-store" },
          cache: "no-store",
        });
        renderStatus(progress, status);
        if (status.status === "error") {
          return status;
        }
        if (status.status === "success") {
          var identity = await fetchJson("/runtime/identity", {
            headers: { "Accept": "application/json", "Cache-Control": "no-store" },
            cache: "no-store",
          });
          if (identity.managed) {
            return status;
          }
        }
      } catch (error) {
        // The backend is intentionally unavailable for a short bounded restart window.
      }
      await delay(POLL_INTERVAL_MS);
    }
    return {
      status: "error",
      step: "error",
      message: "Приложение не перезапустилось вовремя.",
      error: "Повторно запустите start_windows.bat. Перезагрузка Windows не требуется.",
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.querySelector("[data-update-form]");
    var progress = document.querySelector("[data-update-progress]");
    if (!form || !progress || !window.fetch) {
      return;
    }

    var button = form.querySelector("button[type='submit']");
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      if (button) {
        button.disabled = true;
      }
      progress.hidden = false;
      renderStatus(progress, {
        status: "running",
        step: "checking",
        message: "Идёт обновление. Приложение перезапустится автоматически.",
      });

      var scheduled = false;
      try {
        var body = new URLSearchParams(new FormData(form));
        var result = await fetchJson(form.action, {
          method: "POST",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          },
          body: body.toString(),
        });
        scheduled = Boolean(result.ok && result.scheduled);
      } catch (error) {
        // A disconnect can race with the intentional backend stop; status polling decides the outcome.
        scheduled = !error.httpStatus;
      }

      if (scheduled) {
        var finalStatus = await waitForFinishedUpdate(progress);
        renderStatus(progress, finalStatus);
        if (finalStatus.status === "success") {
          await delay(500);
          window.location.replace("/legacy?tab=about&check_updates=1");
          return;
        }
      } else {
        renderStatus(progress, {
          status: "error",
          step: "error",
          message: "Не удалось запустить обновление.",
          error: "Повторите попытку.",
        });
      }
      if (button) {
        button.disabled = false;
      }
    });
  });
})();
