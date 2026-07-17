(() => {
  "use strict";

  const EXIT_DURATION_MS = 180;
  const DEFAULT_SUCCESS_TIMEOUT_MS = 4000;

  function cleanConsumedQueryMarkers(toasts) {
    const keys = new Set();
    toasts.forEach((toast) => {
      String(toast.dataset.appToastQueryKeys || "")
        .split(",")
        .map((key) => key.trim())
        .filter(Boolean)
        .forEach((key) => keys.add(key));
    });
    if (!keys.size) return;

    const cleanUrl = new URL(window.location.href);
    let changed = false;
    keys.forEach((key) => {
      if (!cleanUrl.searchParams.has(key)) return;
      cleanUrl.searchParams.delete(key);
      changed = true;
    });
    if (!changed) return;
    window.history.replaceState(
      window.history.state,
      "",
      `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`,
    );
  }

  function initToast(toast) {
    let removed = false;
    let timer = null;
    const close = () => {
      if (removed) return;
      removed = true;
      if (timer !== null) window.clearTimeout(timer);
      toast.classList.add("is-leaving");
      window.setTimeout(() => toast.remove(), EXIT_DURATION_MS);
    };
    const closeButton = toast.querySelector("[data-app-toast-close]");
    if (closeButton) closeButton.addEventListener("click", close);
    const timeout = Number.parseInt(
      toast.dataset.appToastTimeout || String(DEFAULT_SUCCESS_TIMEOUT_MS),
      10,
    );
    timer = window.setTimeout(
      close,
      Number.isFinite(timeout) && timeout > 0 ? timeout : DEFAULT_SUCCESS_TIMEOUT_MS,
    );
  }

  function init() {
    const toasts = Array.from(document.querySelectorAll("[data-app-toast]"));
    if (!toasts.length) return;
    cleanConsumedQueryMarkers(toasts);
    toasts.forEach(initToast);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
