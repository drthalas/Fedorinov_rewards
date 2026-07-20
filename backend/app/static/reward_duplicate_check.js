(function () {
  const DEBOUNCE_MS = 400;

  function setStatus(status, state, message, existingUrl) {
    if (!status) {
      return;
    }
    status.hidden = !message;
    status.className = "reward-duplicate-status";
    if (state === "free") {
      status.classList.add("notice", "notice-success");
    } else if (state === "duplicate") {
      status.classList.add("notice", "notice-error");
    } else {
      status.classList.add("secondary");
    }
    status.replaceChildren(document.createTextNode(message || ""));
    if (message && existingUrl) {
      status.appendChild(document.createTextNode(" "));
      const link = document.createElement("a");
      link.href = existingUrl;
      link.textContent = "Открыть карточку кавалера";
      status.appendChild(link);
    }
  }

  function buildUrl(nameSelect, numberInput, currentRewardId) {
    const url = new URL("/rewards/check-duplicate", window.location.origin);
    url.searchParams.set("id_name", nameSelect.value || "");
    url.searchParams.set("number", numberInput.value || "");
    if (currentRewardId) {
      url.searchParams.set("current_reward_id", currentRewardId);
    }
    return url;
  }

  function initForm(form) {
    if (!form || form.dataset.rewardDuplicateInitialized === "true") {
      return;
    }
    const nameSelect = form.querySelector("[data-guide-role='name']");
    const numberInput = form.querySelector("[data-reward-number]");
    const status = form.querySelector("[data-reward-duplicate-status]");
    if (!nameSelect || !numberInput || !status) {
      return;
    }
    form.dataset.rewardDuplicateInitialized = "true";

    let timer = 0;
    let requestToken = 0;
    const editing = Boolean(form.dataset.currentRewardId);
    const initialNumber = String(numberInput.value || "").trim();
    let numberChanged = false;

    function scheduleCheck() {
      window.clearTimeout(timer);
      const token = ++requestToken;
      const number = String(numberInput.value || "").trim();
      const nameId = String(nameSelect.value || "").trim();
      if (editing && (!numberChanged || number === initialNumber)) {
        numberChanged = false;
        setStatus(status, "neutral", "");
        return;
      }
      if (!number) {
        setStatus(status, "neutral", "");
        return;
      }
      if (!nameId) {
        setStatus(status, "neutral", "Выберите наименование награды для проверки номера");
        return;
      }
      timer = window.setTimeout(async () => {
        try {
          const response = await fetch(buildUrl(nameSelect, numberInput, form.dataset.currentRewardId || ""), {
            headers: { "Accept": "application/json" },
          });
          if (!response.ok) {
            throw new Error("duplicate check failed");
          }
          const result = await response.json();
          if (token !== requestToken) {
            return;
          }
          if (result.duplicate) {
            setStatus(
              status,
              "duplicate",
              result.message || "Такая награда с этим номером уже есть в базе",
              result.existing_url || ""
            );
          } else if (result.message) {
            setStatus(status, result.message === "Номер свободен" ? "free" : "neutral", result.message);
          } else {
            setStatus(status, "neutral", "");
          }
        } catch (_error) {
          if (token === requestToken) {
            setStatus(status, "neutral", "Не удалось проверить номер сейчас.");
          }
        }
      }, DEBOUNCE_MS);
    }

    numberInput.addEventListener("input", () => {
      numberChanged = String(numberInput.value || "").trim() !== initialNumber;
      scheduleCheck();
    });
    nameSelect.addEventListener("change", () => {
      if (!editing || numberChanged) {
        scheduleCheck();
      }
    });
    setStatus(status, "neutral", "");
  }

  function initAll(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-reward-duplicate-check]").forEach(initForm);
  }

  document.addEventListener("DOMContentLoaded", () => initAll(document));
  document.addEventListener("legacy:content-updated", (event) => {
    initAll(event && event.detail && event.detail.root ? event.detail.root : document);
  });
})();
