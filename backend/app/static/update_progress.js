(function () {
  "use strict";

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

  async function pollStatus(progress) {
    var response = await fetch("/updates/status", { headers: { "Accept": "application/json" } });
    if (!response.ok) {
      return null;
    }
    var data = await response.json();
    renderStatus(progress, data);
    return data;
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
        message: "Идёт обновление. Не закрывайте окно.",
      });

      var pollTimer = window.setInterval(function () {
        pollStatus(progress).then(function (data) {
          if (data && data.status !== "running") {
            window.clearInterval(pollTimer);
          }
        }).catch(function () {});
      }, 1500);

      try {
        var body = new URLSearchParams(new FormData(form));
        var response = await fetch(form.action, {
          method: "POST",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          },
          body: body.toString(),
        });
        var result = await response.json();
        window.clearInterval(pollTimer);
        var finalStatus = await pollStatus(progress);
        if (!finalStatus || finalStatus.status === "running") {
          renderStatus(progress, {
            status: result.ok ? "success" : "error",
            step: result.ok ? "success" : "error",
            message: result.message || result.error || "",
            error: result.ok ? null : result.error,
          });
        }
      } catch (error) {
        window.clearInterval(pollTimer);
        renderStatus(progress, {
          status: "error",
          step: "error",
          message: "Не удалось выполнить обновление.",
          error: String(error && error.message ? error.message : error),
        });
      } finally {
        if (button) {
          button.disabled = false;
        }
      }
    });
  });
})();
