document.addEventListener("DOMContentLoaded", () => {
  let clickTimer = null;
  let typeaheadBuffer = "";
  let typeaheadTimer = null;
  let typeaheadNavigateTimer = null;

  const normalize = (value) => (value || "").toLocaleLowerCase("ru-RU").replace(/ё/g, "е").trim();
  const quickSearch = document.querySelector("[data-person-quick-search]");
  const personRows = Array.from(document.querySelectorAll("[data-person-name]"));
  const emptySearch = document.querySelector("[data-person-empty]");
  const selectedPersonRow = document.querySelector("[data-selected-person-row]");
  const personList = document.querySelector("[data-person-list]");

  const applyPersonSearch = () => {
    const query = normalize(quickSearch ? quickSearch.value : "");
    let visibleCount = 0;
    let firstMatch = null;
    personRows.forEach((row) => {
      const name = normalize(row.dataset.personName);
      const visible = !query || name.includes(query);
      row.hidden = !visible;
      row.classList.remove("quick-search-match-row");
      if (visible) {
        visibleCount += 1;
        if (!firstMatch) {
          firstMatch = row;
        }
      }
    });
    if (emptySearch) {
      emptySearch.hidden = visibleCount !== 0;
    }
    if (query && firstMatch) {
      firstMatch.classList.add("quick-search-match-row");
      scrollRowIntoList(firstMatch);
    }
    return firstMatch;
  };

  if (quickSearch) {
    quickSearch.addEventListener("input", applyPersonSearch);
    quickSearch.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        const firstMatch = applyPersonSearch();
        if (firstMatch && firstMatch.dataset.selectUrl) {
          event.preventDefault();
          navigateToPersonRow(firstMatch);
        }
      } else if (event.key === "Escape") {
        quickSearch.value = "";
        applyPersonSearch();
      }
    });
  }

  const visiblePersonRows = () => personRows.filter((row) => !row.hidden);

  const currentPersonRow = () => document.querySelector(".legacy-list-row.selected-row") || selectedPersonRow;

  const scrollRowIntoList = (row) => {
    if (!row || !personList) {
      return;
    }

    const containerRect = personList.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const margin = 8;
    const fullyVisible = rowRect.top >= containerRect.top + margin
      && rowRect.bottom <= containerRect.bottom - margin;

    if (!fullyVisible) {
      const targetTop = personList.scrollTop
        + rowRect.top
        - containerRect.top
        - ((personList.clientHeight - row.offsetHeight) / 2);
      personList.scrollTop = Math.max(0, targetTop);
    }
  };

  const markPendingSelection = (row) => {
    personRows.forEach((personRow) => {
      personRow.classList.toggle("selected-row", personRow === row);
      personRow.setAttribute("aria-selected", personRow === row ? "true" : "false");
    });
    scrollRowIntoList(row);
  };

  const navigateToPersonRow = (row) => {
    if (!row || !row.dataset.selectUrl) {
      return;
    }
    markPendingSelection(row);
    window.location.href = row.dataset.selectUrl;
  };

  const scheduleTypeaheadNavigation = (row) => {
    if (!row || !row.dataset.selectUrl) {
      return;
    }
    markPendingSelection(row);
    if (typeaheadNavigateTimer) {
      window.clearTimeout(typeaheadNavigateTimer);
    }
    typeaheadNavigateTimer = window.setTimeout(() => {
      window.location.href = row.dataset.selectUrl;
    }, 260);
  };

  const pageStep = () => {
    const firstVisible = visiblePersonRows()[0];
    if (!firstVisible || !personList) {
      return 1;
    }
    const rowHeight = Math.max(1, firstVisible.getBoundingClientRect().height || firstVisible.offsetHeight || 1);
    return Math.max(1, Math.floor(personList.clientHeight / rowHeight) - 1);
  };

  const navigateByOffset = (offset) => {
    const rows = visiblePersonRows();
    if (!rows.length) {
      return;
    }
    const current = currentPersonRow();
    const currentIndex = rows.indexOf(current);
    const startIndex = currentIndex >= 0 ? currentIndex : (offset < 0 ? rows.length : -1);
    const nextIndex = Math.min(rows.length - 1, Math.max(0, startIndex + offset));
    navigateToPersonRow(rows[nextIndex]);
  };

  const navigateToEdge = (edge) => {
    const rows = visiblePersonRows();
    if (!rows.length) {
      return;
    }
    navigateToPersonRow(edge === "end" ? rows[rows.length - 1] : rows[0]);
  };

  const handleTypeahead = (event) => {
    if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) {
      return false;
    }
    const key = normalize(event.key);
    if (!key) {
      return false;
    }

    if (typeaheadTimer) {
      window.clearTimeout(typeaheadTimer);
    }
    typeaheadBuffer += key;
    typeaheadTimer = window.setTimeout(() => {
      typeaheadBuffer = "";
      typeaheadTimer = null;
    }, 900);

    const query = normalize(typeaheadBuffer);
    const match = visiblePersonRows().find((row) => normalize(row.dataset.personName).startsWith(query));
    if (match) {
      scheduleTypeaheadNavigation(match);
    }
    return true;
  };

  const isTextInputTarget = (target) => {
    if (!(target instanceof HTMLElement)) {
      return false;
    }
    return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
  };

  const handlePersonListKeydown = (event) => {
    if (isTextInputTarget(event.target)) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      navigateByOffset(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      navigateByOffset(-1);
    } else if (event.key === "PageDown") {
      event.preventDefault();
      navigateByOffset(pageStep());
    } else if (event.key === "PageUp") {
      event.preventDefault();
      navigateByOffset(-pageStep());
    } else if (event.key === "Home") {
      event.preventDefault();
      navigateToEdge("start");
    } else if (event.key === "End") {
      event.preventDefault();
      navigateToEdge("end");
    } else if (handleTypeahead(event)) {
      event.preventDefault();
    }
  };

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

        // Do not auto-focus the list after page load: the visible search field is the primary quick-search path.
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

  if (personList) {
    personList.addEventListener("keydown", handlePersonListKeydown);
    personList.addEventListener("click", () => {
      personList.focus({ preventScroll: true });
    });
  }
});
