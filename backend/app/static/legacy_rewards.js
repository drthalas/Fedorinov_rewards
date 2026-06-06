document.addEventListener("DOMContentLoaded", () => {
  let clickTimer = null;

  const normalize = (value) => (value || "").toLocaleLowerCase("ru-RU").trim();
  const quickSearch = document.querySelector("[data-person-quick-search]");
  const personRows = Array.from(document.querySelectorAll("[data-person-name]"));
  const emptySearch = document.querySelector("[data-person-empty]");

  const applyPersonSearch = () => {
    const query = normalize(quickSearch ? quickSearch.value : "");
    let visibleCount = 0;
    personRows.forEach((row) => {
      const name = normalize(row.dataset.personName);
      const visible = !query || name.includes(query);
      row.hidden = !visible;
      if (visible) {
        visibleCount += 1;
      }
    });
    if (emptySearch) {
      emptySearch.hidden = visibleCount !== 0;
    }
  };

  if (quickSearch) {
    quickSearch.addEventListener("input", applyPersonSearch);
  }

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
