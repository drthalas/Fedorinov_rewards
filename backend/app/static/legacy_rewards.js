(function () {
  "use strict";

  const TYPEAHEAD_RESET_MS = 3200;
  const TYPEAHEAD_NAVIGATION_DELAY_MS = 2600;
  const CLICK_NAVIGATION_DELAY_MS = 160;
  const LOADING_TEXT = "Загрузка карточки кавалера…";
  const ERROR_TEXT = "Не удалось загрузить карточку кавалера. Попробуйте выбрать кавалера ещё раз.";

  let activeFetchController = null;

  const normalize = (value) => (value || "").toLocaleLowerCase("ru-RU").replace(/ё/g, "е").trim();

  const isTextInputTarget = (target) => {
    if (!(target instanceof HTMLElement)) {
      return false;
    }
    return Boolean(target.closest("input, textarea, select, [contenteditable='true']"));
  };

  const workspace = () => document.querySelector("[data-legacy-person-workspace]");

  const showWorkspaceState = (className, text, role) => {
    const target = workspace();
    if (!target) {
      return;
    }
    target.setAttribute("aria-busy", className === "legacy-loading-state" ? "true" : "false");
    const state = document.createElement("div");
    state.className = className;
    state.setAttribute("role", role || "status");
    state.textContent = text;
    target.replaceChildren(state);
  };

  const showLoadingState = () => showWorkspaceState("legacy-loading-state", LOADING_TEXT, "status");
  const showErrorState = () => showWorkspaceState("legacy-error-state", ERROR_TEXT, "alert");

  const replaceRewardsLayout = (html, focusList) => {
    const parser = new DOMParser();
    const nextDocument = parser.parseFromString(html, "text/html");
    const nextLayout = nextDocument.querySelector("[data-legacy-rewards-layout]");
    const currentLayout = document.querySelector("[data-legacy-rewards-layout]");
    if (!nextLayout || !currentLayout) {
      throw new Error("Rewards layout was not found in response.");
    }
    currentLayout.replaceWith(nextLayout);
    document.dispatchEvent(new CustomEvent("legacy:content-updated", { detail: { root: nextLayout } }));
    initLegacyRewards(nextLayout);
    if (focusList) {
      const nextList = nextLayout.querySelector("[data-person-list]");
      if (nextList) {
        nextList.focus({ preventScroll: true });
      }
    }
  };

  const navigateToUrl = (url, options) => {
    if (!url) {
      return;
    }
    const settings = options || {};
    if (!window.fetch || !window.DOMParser || !window.history) {
      window.location.href = url;
      return;
    }

    if (activeFetchController) {
      activeFetchController.abort();
    }
    const controller = new AbortController();
    activeFetchController = controller;
    showLoadingState();

    window.fetch(url, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
      signal: controller.signal,
    }).then((response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      return response.text();
    }).then((html) => {
      replaceRewardsLayout(html, Boolean(settings.focusList));
      if (settings.updateHistory !== false) {
        window.history.pushState({ legacyRewardsUrl: url }, "", url);
      }
    }).catch((error) => {
      if (error && error.name === "AbortError") {
        return;
      }
      showErrorState();
    }).finally(() => {
      if (activeFetchController === controller) {
        activeFetchController = null;
      }
    });
  };

  function initLegacyRewards(root) {
    const scope = root || document;
    const personList = scope.querySelector("[data-person-list]");
    const quickSearch = scope.querySelector("[data-person-quick-search]");
    const personRows = Array.from(scope.querySelectorAll("[data-person-name]"));
    const emptySearch = scope.querySelector("[data-person-empty]");
    const selectedPersonRow = scope.querySelector("[data-selected-person-row]");
    let clickTimer = null;
    let typeaheadBuffer = "";
    let typeaheadTimer = null;
    let typeaheadNavigateTimer = null;

    const visiblePersonRows = () => personRows.filter((row) => !row.hidden);

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

    const currentPersonRow = () => scope.querySelector(".legacy-list-row.selected-row") || selectedPersonRow;

    const markPendingSelection = (row) => {
      personRows.forEach((personRow) => {
        personRow.classList.toggle("selected-row", personRow === row);
        personRow.setAttribute("aria-selected", personRow === row ? "true" : "false");
      });
      scrollRowIntoList(row);
    };

    const navigateToPersonRow = (row, options) => {
      if (!row || !row.dataset.selectUrl) {
        return;
      }
      markPendingSelection(row);
      navigateToUrl(row.dataset.selectUrl, options);
    };

    const clearTypeahead = () => {
      typeaheadBuffer = "";
      if (typeaheadTimer) {
        window.clearTimeout(typeaheadTimer);
        typeaheadTimer = null;
      }
      if (typeaheadNavigateTimer) {
        window.clearTimeout(typeaheadNavigateTimer);
        typeaheadNavigateTimer = null;
      }
    };

    const scheduleTypeaheadReset = () => {
      if (typeaheadTimer) {
        window.clearTimeout(typeaheadTimer);
      }
      typeaheadTimer = window.setTimeout(() => {
        typeaheadBuffer = "";
        typeaheadTimer = null;
      }, TYPEAHEAD_RESET_MS);
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
        navigateToPersonRow(row, { focusList: true });
      }, TYPEAHEAD_NAVIGATION_DELAY_MS);
    };

    const updateTypeaheadSelection = () => {
      const query = normalize(typeaheadBuffer);
      if (!query) {
        return false;
      }
      const match = visiblePersonRows().find((row) => normalize(row.dataset.personName).startsWith(query));
      if (match) {
        scheduleTypeaheadNavigation(match);
      }
      return Boolean(match);
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
      clearTypeahead();
      const current = currentPersonRow();
      const currentIndex = rows.indexOf(current);
      const startIndex = currentIndex >= 0 ? currentIndex : (offset < 0 ? rows.length : -1);
      const nextIndex = Math.min(rows.length - 1, Math.max(0, startIndex + offset));
      navigateToPersonRow(rows[nextIndex], { focusList: true });
    };

    const navigateToEdge = (edge) => {
      const rows = visiblePersonRows();
      if (!rows.length) {
        return;
      }
      clearTypeahead();
      navigateToPersonRow(edge === "end" ? rows[rows.length - 1] : rows[0], { focusList: true });
    };

    const handleTypeahead = (event) => {
      if (event.key === "Escape") {
        clearTypeahead();
        return true;
      }
      if (event.key === "Backspace" && typeaheadBuffer) {
        event.preventDefault();
        typeaheadBuffer = typeaheadBuffer.slice(0, -1);
        scheduleTypeaheadReset();
        updateTypeaheadSelection();
        return true;
      }
      if (event.key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) {
        return false;
      }
      const key = normalize(event.key);
      if (!key) {
        return false;
      }

      typeaheadBuffer += key;
      scheduleTypeaheadReset();
      updateTypeaheadSelection();
      return true;
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

    if (quickSearch && quickSearch.dataset.legacyRewardsBound !== "true") {
      quickSearch.dataset.legacyRewardsBound = "true";
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

    personRows.forEach((row) => {
      if (row.dataset.legacyRewardsBound === "true") {
        return;
      }
      row.dataset.legacyRewardsBound = "true";
      row.addEventListener("click", (event) => {
        event.preventDefault();
        if (clickTimer) {
          window.clearTimeout(clickTimer);
        }
        clickTimer = window.setTimeout(() => {
          navigateToPersonRow(row, { focusList: true });
        }, CLICK_NAVIGATION_DELAY_MS);
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

    if (personList && personList.dataset.legacyRewardsBound !== "true") {
      personList.dataset.legacyRewardsBound = "true";
      personList.addEventListener("keydown", handlePersonListKeydown);
      personList.addEventListener("click", () => {
        personList.focus({ preventScroll: true });
      });
    }

    if (selectedPersonRow) {
      scrollSelectedPersonIntoList();
    }
  }

  document.addEventListener("DOMContentLoaded", () => initLegacyRewards(document));
  window.addEventListener("popstate", () => {
    if (window.location.pathname === "/legacy" && window.location.search.includes("tab=rewards")) {
      navigateToUrl(window.location.pathname + window.location.search, { focusList: false, updateHistory: false });
    }
  });
})();
