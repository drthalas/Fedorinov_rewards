document.addEventListener("DOMContentLoaded", () => {
  let clickTimer = null;

  document.querySelectorAll("[data-select-url][data-detail-url]").forEach((row) => {
    row.addEventListener("click", (event) => {
      event.preventDefault();
      if (clickTimer) {
        window.clearTimeout(clickTimer);
      }
      clickTimer = window.setTimeout(() => {
        window.location.href = row.dataset.selectUrl;
      }, 180);
    });

    row.addEventListener("dblclick", (event) => {
      event.preventDefault();
      if (clickTimer) {
        window.clearTimeout(clickTimer);
        clickTimer = null;
      }
      window.location.href = row.dataset.detailUrl;
    });
  });
});
