(() => {
  "use strict";

  const root = document.documentElement;
  let revealScheduled = false;

  function revealReadyDocument() {
    if (revealScheduled) return;
    revealScheduled = true;
    window.requestAnimationFrame(() => {
      root.classList.remove("document-loading");
      root.dataset.documentReady = "true";
      document.dispatchEvent(new CustomEvent("document-transition:ready"));
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", revealReadyDocument, { once: true });
  } else {
    revealReadyDocument();
  }

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) revealReadyDocument();
  });
})();
