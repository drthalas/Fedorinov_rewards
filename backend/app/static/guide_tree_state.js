(() => {
  "use strict";

  const guidesPath = "/guides";

  function normalizeSearchText(value) {
    const text = String(value || "");
    const normalized = typeof text.normalize === "function" ? text.normalize("NFKC") : text;
    return normalized.toLocaleLowerCase("ru").replace(/ё/g, "е").trim();
  }

  function matchesSearchText(value, query) {
    const index = value.indexOf(query);
    if (index < 0) return false;
    const romanSuffix = query.match(/(?:^|[\s-])([ivxlcdm]+)$/i);
    if (!romanSuffix) return true;
    const nextCharacter = value.charAt(index + query.length);
    return !/[ivxlcdm]/i.test(nextCharacter);
  }

  function init() {
    const stateRoot = document.querySelector("[data-guide-state-root]");
    const tree = document.querySelector("[data-guide-tree]");
    if (!stateRoot || !tree || window.location.pathname !== guidesPath) return;

    const rankFilter = stateRoot.querySelector("[data-guide-rank-filter]");
    const rankRows = Array.from(stateRoot.querySelectorAll("[data-guide-rank-row]"));
    if (rankFilter) {
      rankFilter.addEventListener("input", () => {
        const query = normalizeSearchText(rankFilter.value);
        rankRows.forEach((row) => {
          row.hidden = Boolean(query) && !matchesSearchText(normalizeSearchText(row.dataset.guideRankName), query);
        });
      });
    }

    const detailsNodes = Array.from(tree.querySelectorAll("details[data-guide-key]"));
    const treeFilter = tree.querySelector("[data-guide-tree-filter]");
    const treeFilterClear = tree.querySelector("[data-guide-tree-filter-clear]");
    const treeEmpty = tree.querySelector("[data-guide-tree-empty]");
    const treeNodes = Array.from(tree.querySelectorAll("[data-guide-tree-node]"));
    let savedOpenState = null;

    function directDetails(node) {
      return Array.from(node.children).find((child) => child.matches("details[data-guide-key]")) || null;
    }

    function directChildNodes(details) {
      const list = Array.from(details.children).find((child) => child.matches("ul.tree-list"));
      return list ? Array.from(list.children).filter((child) => child.matches("[data-guide-tree-node]")) : [];
    }

    function showSubtree(node) {
      node.hidden = false;
      const details = directDetails(node);
      if (!details) return;
      directChildNodes(details).forEach(showSubtree);
    }

    function filterTreeNode(node, query) {
      const details = directDetails(node);
      const children = details ? directChildNodes(details) : [];
      const ownMatch = matchesSearchText(normalizeSearchText(node.dataset.guideSearchName), query);
      let childMatch = false;
      children.forEach((child) => {
        childMatch = filterTreeNode(child, query) || childMatch;
      });
      if (ownMatch) children.forEach(showSubtree);
      const visible = ownMatch || childMatch;
      node.hidden = !visible;
      if (details && visible && children.length) details.open = true;
      return visible;
    }

    function restoreTree() {
      treeNodes.forEach((node) => {
        node.hidden = false;
        const details = directDetails(node);
        if (details && savedOpenState) details.open = Boolean(savedOpenState.get(details.dataset.guideKey));
      });
      savedOpenState = null;
      if (treeEmpty) treeEmpty.hidden = true;
      if (treeFilterClear) treeFilterClear.hidden = true;
      window.history.replaceState(null, "", stateUrl(""));
    }

    function applyTreeFilter() {
      if (!treeFilter) return;
      const query = normalizeSearchText(treeFilter.value);
      if (!query) {
        restoreTree();
        return;
      }
      if (!savedOpenState) {
        savedOpenState = new Map(detailsNodes.map((details) => [details.dataset.guideKey, details.open]));
      }
      const roots = treeNodes.filter((node) => !node.parentElement.closest("[data-guide-tree-node]"));
      const hasMatch = roots.reduce((matched, node) => filterTreeNode(node, query) || matched, false);
      if (treeEmpty) treeEmpty.hidden = hasMatch;
      if (treeFilterClear) treeFilterClear.hidden = false;
    }

    if (treeFilter) treeFilter.addEventListener("input", applyTreeFilter);
    if (treeFilterClear && treeFilter) {
      treeFilterClear.addEventListener("click", () => {
        treeFilter.value = "";
        restoreTree();
        treeFilter.focus();
      });
    }

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
        if (treeFilter && normalizeSearchText(treeFilter.value)) return;
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
