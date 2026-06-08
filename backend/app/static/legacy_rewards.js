document.addEventListener("DOMContentLoaded", () => {
  let clickTimer = null;

  const normalize = (value) => (value || "").toLocaleLowerCase("ru-RU").trim();
  const quickSearch = document.querySelector("[data-person-quick-search]");
  const personRows = Array.from(document.querySelectorAll("[data-person-name]"));
  const emptySearch = document.querySelector("[data-person-empty]");
  const selectedPersonRow = document.querySelector("[data-selected-person-row]");
  const personList = document.querySelector("[data-person-list]");

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

  const scrollSelectedPersonIntoList = () => {
    if (!selectedPersonRow || !personList) {
      return;
    }

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const containerRect = personList.getBoundingClientRect();
        const rowRect = selectedPersonRow.getBoundingClientRect();
        const margin = 8;
        const fullyVisible = rowRect.top >= containerRect.top + margin
          && rowRect.bottom <= containerRect.bottom - margin;

        if (!fullyVisible) {
          const targetTop = personList.scrollTop
            + rowRect.top
            - containerRect.top
            - ((personList.clientHeight - selectedPersonRow.offsetHeight) / 2);
          personList.scrollTop = Math.max(0, targetTop);
        }

        window.requestAnimationFrame(() => {
          const adjustedContainerRect = personList.getBoundingClientRect();
          const adjustedRowRect = selectedPersonRow.getBoundingClientRect();
          if (adjustedRowRect.top < adjustedContainerRect.top + margin) {
            personList.scrollTop -= (adjustedContainerRect.top + margin) - adjustedRowRect.top;
          } else if (adjustedRowRect.bottom > adjustedContainerRect.bottom - margin) {
            personList.scrollTop += adjustedRowRect.bottom - (adjustedContainerRect.bottom - margin);
          }
        });
      });
    });
  };

  if (selectedPersonRow) {
    scrollSelectedPersonIntoList();
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
