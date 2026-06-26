function internalFallback(value) {
  const fallback = value || "/";
  if (!fallback.startsWith("/") || fallback.startsWith("//") || fallback.includes("\\")) {
    return "/";
  }
  try {
    const url = new URL(fallback, window.location.origin);
    if (url.origin !== window.location.origin) {
      return "/";
    }
    return `${url.pathname}${url.search}${url.hash}`;
  } catch (error) {
    return "/";
  }
}

function goBackOrFallback(fallback) {
  const target = internalFallback(fallback);
  const referrer = document.referrer || "";
  const hasInternalHistory = window.history.length > 1 && referrer.startsWith(window.location.origin);
  if (hasInternalHistory) {
    window.history.back();
    return;
  }
  window.location.href = target;
}

document.addEventListener("click", (event) => {
  const button = event.target instanceof HTMLElement ? event.target.closest("[data-history-back]") : null;
  if (!button) {
    return;
  }
  event.preventDefault();
  goBackOrFallback(button.getAttribute("data-history-fallback"));
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") {
    return;
  }
  if (document.querySelector(".photo-lightbox.is-open")) {
    return;
  }

  const returnLink = document.querySelector("[data-escape-back]");
  if (!returnLink) {
    return;
  }

  const href = returnLink.getAttribute("href");
  if (!href) {
    return;
  }

  event.preventDefault();
  window.location.href = internalFallback(href);
});
