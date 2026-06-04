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
  window.location.href = href;
});
