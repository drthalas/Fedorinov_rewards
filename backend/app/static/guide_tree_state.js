(() => {
  "use strict";

  const guidesPath = "/guides";

  function init() {
    const stateRoot = document.querySelector("[data-guide-state-root]");
    const tree = document.querySelector("[data-guide-tree]");
    if (!stateRoot || !tree || window.location.pathname !== guidesPath) return;

    const rankFilter = stateRoot.querySelector("[data-guide-rank-filter]");
    const rankRows = Array.from(stateRoot.querySelectorAll("[data-guide-rank-row]"));
    if (rankFilter) {
      rankFilter.addEventListener("input", () => {
        const query = rankFilter.value.trim().toLocaleLowerCase("ru");
        rankRows.forEach((row) => {
          row.hidden = Boolean(query) && !String(row.dataset.guideRankName || "").includes(query);
        });
      });
    }

    const detailsNodes = Array.from(tree.querySelectorAll("details[data-guide-key]"));

    function setActiveDetails(details) {
      detailsNodes.forEach((candidate) => {
        if (candidate === details) candidate.setAttribute("data-guide-active", "");
        else candidate.removeAttribute("data-guide-active");
      });
    }

    function stateUrl(focusOverride) {
      const url = new URL(window.location.href);
      const openKeys = detailsNodes
        .filter((details) => details.open)
        .map((details) => details.dataset.guideKey)
        .filter(Boolean);

      if (openKeys.length) url.searchParams.set("open", openKeys.join(","));
      else url.searchParams.delete("open");

      if (focusOverride !== undefined) {
        if (focusOverride) url.searchParams.set("focus", focusOverride);
        else url.searchParams.delete("focus");
      }
      url.searchParams.delete("status");
      return `${url.pathname}${url.search}${url.hash}`;
    }

    detailsNodes.forEach((details) => {
      details.addEventListener("toggle", () => {
        if (details.open) setActiveDetails(details);
        else if (details.hasAttribute("data-guide-active")) setActiveDetails(null);
        window.history.replaceState(null, "", stateUrl(""));
      });
    });

    stateRoot.addEventListener("click", (event) => {
      const link = event.target.closest("a[data-guide-action]");
      if (!link) return;
      const target = new URL(link.href, window.location.origin);
      target.searchParams.set("return_to", stateUrl(link.dataset.guideFocus || ""));
      link.href = `${target.pathname}${target.search}${target.hash}`;
    }, true);

    stateRoot.addEventListener("submit", (event) => {
      const form = event.target.closest("form[data-guide-action]");
      if (!form) return;
      const returnInput = form.querySelector('input[name="return_to"]');
      if (returnInput) returnInput.value = stateUrl(form.dataset.guideFocus || "");
    }, true);

    const focused = tree.querySelector("[data-guide-focus-target]");
    if (focused) {
      setActiveDetails(focused.querySelector(":scope > details[data-guide-key]"));
      window.requestAnimationFrame(() => focused.scrollIntoView({ block: "center" }));
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
