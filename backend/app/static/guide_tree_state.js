(() => {
  "use strict";

  const guidesPath = "/guides";

  function init() {
    const stateRoot = document.querySelector("[data-guide-state-root]");
    const tree = document.querySelector("[data-guide-tree]");
    if (!stateRoot || !tree || window.location.pathname !== guidesPath) return;

    const detailsNodes = Array.from(tree.querySelectorAll("details[data-guide-key]"));

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
        window.history.replaceState(null, "", stateUrl());
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

    const focused = tree.querySelector(".guide-node-focus");
    if (focused) {
      window.requestAnimationFrame(() => focused.scrollIntoView({ block: "center" }));
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
