(() => {
  "use strict";
  const key = "fedorinov:search-return";
  const current = new URL(location.href);
  if (current.pathname !== "/search" && !(current.pathname === "/legacy" && current.searchParams.get("tab") === "search")) return;
  function canonical(value) {
    const url = new URL(value, location.origin);
    ["status", "message", "error", "media_cleanup"].forEach((name) => url.searchParams.delete(name));
    url.searchParams.sort();
    return url.pathname + url.search;
  }
  const scrollContainers = () => [...document.querySelectorAll(".table-wrap, .legacy-table-wrap, .legacy-search-tab")];
  function rowScroller(row) {
    for (let parent = row.parentElement; parent; parent = parent.parentElement) {
      if (parent.scrollHeight > parent.clientHeight && /auto|scroll/.test(getComputedStyle(parent).overflowY)) return parent;
    }
    return null;
  }
  function restore() {
    document.querySelectorAll("[data-search-return-selected]").forEach((row) => {
      row.classList.remove("selected-row", "search-return-selected");
      row.removeAttribute("data-search-return-selected");
      row.removeAttribute("aria-current");
      row.querySelector("[data-search-return-marker]")?.remove();
    });
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || "null");
      const token = location.hash.startsWith("#search-return-") ? location.hash.slice(1) : history.state?.searchReturn;
      if (!saved || saved.token !== token || saved.url !== canonical(location.href)) return;
      const rows = [...document.querySelectorAll("[data-search-row]")];
      const row = rows.find((item) => item.dataset.searchRow === saved.row);
      scrollContainers().forEach((wrap, index) => {
        const scroll = saved.wraps[index];
        if (scroll) { wrap.scrollTop = scroll.top; wrap.scrollLeft = scroll.left; }
      });
      window.scrollTo(saved.x, saved.y);
      // Keep the stable row at its old viewport position; missing rows use saved scroll.
      if (row) {
        row.classList.add("selected-row", "search-return-selected");
        row.setAttribute("data-search-return-selected", "");
        row.setAttribute("aria-current", "true");
        const marker = document.createElement("span");
        marker.className = "visually-hidden";
        marker.setAttribute("data-search-return-marker", "");
        marker.textContent = "Последняя открытая строка. ";
        row.querySelector("td")?.prepend(marker);
        const delta = row.getBoundingClientRect().top - saved.top;
        const wrap = rowScroller(row);
        if (wrap && wrap.scrollHeight > wrap.clientHeight) wrap.scrollTop += delta;
        else window.scrollBy(0, delta);
      }
    } catch (_) { /* Storage/history may be unavailable. Navigation still works. */ }
  }
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-search-row] a[href]");
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = new URL(link.href);
    if (!/^\/(persons|rewards)\/\d+$/.test(target.pathname)) return;
    const row = link.closest("[data-search-row]");
    const token = `search-return-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    try {
      sessionStorage.setItem(key, JSON.stringify({ token, url: canonical(location.href), row: row.dataset.searchRow,
        top: row.getBoundingClientRect().top, x: scrollX, y: scrollY,
        wraps: scrollContainers().map((wrap) => ({ top: wrap.scrollTop, left: wrap.scrollLeft })) }));
      const back = new URL(location.href); back.hash = token;
      history.replaceState({ ...history.state, searchReturn: token }, "", back.pathname + back.search + back.hash);
      target.searchParams.set("return_to", back.pathname + back.search + back.hash);
      link.href = target.href;
    } catch (_) { /* Keep the existing return_to. */ }
  }, true);
  const schedule = () => requestAnimationFrame(() => requestAnimationFrame(restore));
  window.addEventListener("pageshow", schedule);
  window.addEventListener("load", schedule);
})();
